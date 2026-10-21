// Read-only normalization of offline snapshots from pinned upstream interfaces.
// No wallet/daemon mutations and no automatic inference of hidden backing links.
import { createHash } from "node:crypto";
import { digest, integer, sats, sum, type ClaimSpec, type Envelope, type CapitalEvent, type Block } from "./capital.ts";

export const SOURCE_PINS = {
  bark: "683964f59fcb3dde1dcecd6eab23b2a9dd2eee6f",
  bitcoin: "d0f6d9953a15d7c7111d46dcb76ab2bb18e5dee3",
  cln: "8684c68dffb04ab606e526b64d7d60390d1fe7ed",
} as const;
export type SourcePins = { [K in keyof typeof SOURCE_PINS]: string };
function requireEvidence(ok: unknown, error: string): asserts ok { if (!ok) throw new Error(error); }
export function msat(value: number | string): number {
  if (typeof value === "number") return integer(value);
  requireEvidence(/^(0|[1-9][0-9]*)(msat)?$/.test(value), "invalid msat amount"); return integer(Number(value.replace(/msat$/, "")));
}
/** Convert a Core decimal BTC JSON token without floating point multiplication. */
export function btcToMsat(token: string): number {
  requireEvidence(/^(0|[1-9][0-9]*)(\.[0-9]{1,8})?$/.test(token), "BTC requires an exact decimal token with at most 8 places");
  const [whole, fraction = ""] = token.split("."); const value = (BigInt(whole) * 100000000n + BigInt(fraction.padEnd(8, "0"))) * 1000n;
  requireEvidence(value <= BigInt(Number.MAX_SAFE_INTEGER), "BTC amount exceeds safe boundary"); return Number(value);
}
export interface BarkAttempt {
  id: number; payment_hash: string; amount_msat: number | string; final_amount_msat: number | string | null;
  status: "requested" | "submitted" | "succeeded" | "failed"; user_fee_sat: number | null;
  lightning_htlc_subscription_id: number | null;
}
export interface BarkSettlement { payment_hash: string; preimage: string }
export interface ClnPay {
  payment_hash: string; status: "pending" | "complete" | "failed";
  amount_msat?: number | string; amount_sent_msat?: number | string; preimage?: string;
  number_of_parts?: number;
}
export interface ClnChannel {
  channel_id: string; funding_txid: string; funding_outnum: number; state: string;
  to_us_msat: number | string; total_msat: number | string; spendable_msat: number | string; receivable_msat: number | string;
  htlcs?: { direction: "in" | "out"; id: number; amount_msat: number | string; state: string }[];
}
export interface CoreTransaction {
  txid: string; blockhash?: string; confirmations?: number; in_active_chain?: boolean;
  vin: { txid: string; vout: number }[];
  // Capture numeric BTC tokens as strings at the RPC boundary, before JSON.parse loses precision.
  vout: { n: number; value: string; scriptPubKey: { hex: string } }[];
}

export class ReadonlyCapitalAdapter {
  constructor(pins: SourcePins) {
    for (const key of Object.keys(SOURCE_PINS) as (keyof SourcePins)[]) requireEvidence(pins[key] === SOURCE_PINS[key], `unsupported ${key} revision`);
  }
  settlement(envelope: Envelope, operation_id: string, attempt: BarkAttempt, settlement: BarkSettlement | null,
    pays: { pays: ClnPay[] }, change?: ClaimSpec): CapitalEvent {
    requireEvidence(attempt.lightning_htlc_subscription_id === null, "intra-Ark self-payments require a separate adapter");
    requireEvidence(settlement && settlement.payment_hash === attempt.payment_hash, "htlc_settlement row required; attempt status is not authoritative");
    requireEvidence(/^[0-9a-f]{64}$/.test(settlement.preimage) && /^[0-9a-f]{64}$/.test(attempt.payment_hash), "invalid settlement proof encoding");
    const paymentHash = createHash("sha256").update(Buffer.from(settlement.preimage, "hex")).digest("hex");
    requireEvidence(paymentHash === attempt.payment_hash, "preimage does not match payment hash");
    // listpays aggregates MPP. Unfiltered response only: index/start pagination
    // can undercount amount_sent_msat. Ambiguous repeated-hash entries fail closed.
    const matching = pays.pays.filter(p => p.payment_hash === paymentHash);
    requireEvidence(matching.length === 1 && matching[0].status === "complete", "one complete unfiltered CLN listpays entry required");
    const p = matching[0]; requireEvidence(p.amount_msat !== undefined && p.amount_sent_msat !== undefined && attempt.final_amount_msat !== null, "final CLN amounts missing");
    const amount = msat(p.amount_msat), sent = msat(p.amount_sent_msat);
    requireEvidence(amount === msat(attempt.amount_msat) && sent === msat(attempt.final_amount_msat) && sent >= amount, "Bark/CLN amount mismatch");
    requireEvidence(attempt.user_fee_sat !== null, "legacy attempt has unknown holder fee");
    const fee = sent - amount, userFee = sats(attempt.user_fee_sat);
    requireEvidence(userFee >= fee, "routing cost exceeds holder fee; operator subsidy needs explicit allocation");
    const proof = `sha256:${digest({ payment_hash: paymentHash, preimage_verified: true })}`;
    // Preimages are checked in memory and never included in the published event.
    return { ...envelope, event_type: "HTLC_SETTLED", amount,
      evidence_refs: [...envelope.evidence_refs, proof, `bark:${SOURCE_PINS.bark}:lightning_payment_attempt:${attempt.id}`],
      data: { operation_id, fee, service_fee: userFee - fee, preimage_evidence_ref: proof, ...(change ? { change } : {}) } };
  }
  channelSnapshot(channel: ClnChannel) {
    requireEvidence(channel.state === "CHANNELD_NORMAL", "channel is not operational"); integer(channel.funding_outnum);
    const owned = msat(channel.to_us_msat), total = msat(channel.total_msat), spendable = msat(channel.spendable_msat), receivable = msat(channel.receivable_msat);
    requireEvidence(owned <= total && spendable <= owned && receivable <= total, "inconsistent directional capacity");
    const htlcs = channel.htlcs ?? [];
    requireEvidence(new Set(htlcs.map(h => `${h.direction}:${h.id}`)).size === htlcs.length, "duplicate HTLC");
    return { channel_id: channel.channel_id, funding_ref: `${channel.funding_txid}:${channel.funding_outnum}`,
      owned_msat: owned, remote_msat: total - owned, capacity_msat: total, spendable_msat: spendable, receivable_msat: receivable,
      inflight_out_msat: sum(htlcs.filter(h => h.direction === "out").map(h => msat(h.amount_msat))),
      inflight_in_msat: sum(htlcs.filter(h => h.direction === "in").map(h => msat(h.amount_msat))),
      // This is a reconciliation observation, NOT a FUND event. Existing HTLC
      // balances cannot safely be initialized without the prior commitment state.
      can_initialize_quiescent: htlcs.length === 0, evidence_hash: digest(channel) };
  }
  chainSnapshot(genesis: string, headers: { height: number; hash: string; previousblockhash: string; confirmations: number }[], expectedGenesis: string): Block[] {
    requireEvidence(genesis === expectedGenesis, "wrong chain genesis");
    const result: Block[] = []; let previous = genesis;
    for (const h of headers) { requireEvidence(h.height === result.length + 1 && h.previousblockhash === previous && h.confirmations > 0, "noncanonical/incomplete header snapshot");
      result.push({ height: h.height, hash: h.hash, parent_hash: previous }); previous = h.hash; }
    return result;
  }
  sweepConfirmation(envelope: Envelope, sweep_id: string, tx: CoreTransaction, inputAmounts: Record<string, number>,
    outputIndex: number, expectedScript: string, inclusionHeight: number, canonicalHash: string, tipHeight: number): CapitalEvent {
    requireEvidence(tx.blockhash === canonicalHash && tx.in_active_chain === true && tx.confirmations === tipHeight - inclusionHeight + 1 && tx.confirmations > 0, "sweep is not on active chain");
    requireEvidence(envelope.block_height === tipHeight && envelope.txid === tx.txid, "observation/transaction mismatch");
    const ids = tx.vin.map(v => `${v.txid}:${integer(v.vout)}`); requireEvidence(new Set(ids).size === ids.length, "duplicate transaction input");
    requireEvidence(ids.length === Object.keys(inputAmounts).length && ids.every(id => Object.hasOwn(inputAmounts, id)), "unknown sweep inputs");
    const outputs = tx.vout.map(v => btcToMsat(v.value)); requireEvidence(sum(outputs) <= sum(Object.values(inputAmounts)), "transaction creates value");
    // The current reducer supports one owned output at vout 0. Reject other
    // shapes rather than silently misattribute batch sweeps or change outputs.
    requireEvidence(tx.vout.length === 1 && outputIndex === 0 && tx.vout[0].n === 0 && tx.vout[0].scriptPubKey.hex === expectedScript, "unsupported sweep output shape/owner");
    return { ...envelope, event_type: "SWEEP_CONFIRMED", amount: outputs[0], evidence_refs: [...envelope.evidence_refs, `sha256:${digest(tx)}`],
      data: { sweep_id, inclusion_height: inclusionHeight, inclusion_hash: canonicalHash } };
  }
}
