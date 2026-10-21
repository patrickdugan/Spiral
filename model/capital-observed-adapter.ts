// Read-only adapter for the actually executed fixture. The collector is the
// trust boundary for Core/CLN/database authenticity and preimage verification.
// A redacted observation can be hashed and reconciled, not re-verify a secret.
import { btcToMsat, msat } from "./capital-adapter.ts";
import { integer, sum } from "./capital.ts";
import assert from "node:assert/strict";

export const EXECUTED_BARK = "8f5d8c4f4afae87c8e4b3c6fb26fe06e9ae50e6a";
export const EXECUTED_GENESIS = "0f9188f13cb7b2c71f2a335e3a4fc328bf5beb436012afca590b1a11466e2206";
export const EXECUTABLE_PINS: Record<string, string> = {
  bitcoind: "dae69848ae9aaadcc3aa697d1c92b1283273a59c8d87b220b29ddc2813e25eb6",
  lightningd: "cf814f01f69b857ec1cfb48a907b78d33179c803b6e5f3cff50fbf495d4a38a2",
  captaind: "38881e672f06751180f485e4d927487c4bd90363da69449ffee4ba57fde7212a",
  watchmand: "aab9ae7d301be8a8a3e2864cce7315ec7644bfae5679915da966543e0e55ed17",
  bark: "ce12ba616bdd1a7f97ddcfeb070f44e79308842b529456e5b3947f1332fcdbaf",
};
export interface ObservedHeader { height: number; hash: string; previousblockhash?: string; confirmations: number }
export interface ObservedTransaction {
  txid: string; blockhash?: string; confirmations?: number; in_active_chain?: boolean;
  vin: { txid: string; vout: number }[];
  vout: { n: number; value: string; scriptPubKey: { hex: string } }[];
}
export interface ObservedTransactionRecord { transaction: ObservedTransaction; previous_outputs: Record<string, ObservedTransaction["vout"][number]> }
export class ObservedRegtestAdapter {
  readonly headers: ObservedHeader[];
  constructor(identity: { genesis: string; executables: { binary: string; version: string; sha256: string }[] }, source: { revision: string }, headers: ObservedHeader[]) {
    assert.equal(identity.genesis, EXECUTED_GENESIS, "unexpected executed chain"); assert.equal(source.revision, EXECUTED_BARK, "unsupported executed Bark revision");
    for (const [binary, sha256] of Object.entries(EXECUTABLE_PINS)) {
      const records = identity.executables.filter(e => e.binary === binary); assert.equal(records.length, 1, "ambiguous executable");
      assert.equal(records[0].sha256, sha256, `unsupported executable ${binary}`);
      if (["bark", "captaind", "watchmand"].includes(binary)) assert.ok(records[0].version.includes(EXECUTED_BARK), "binary/source mismatch");
    }
    assert.equal(headers[0]?.hash, EXECUTED_GENESIS, "header genesis mismatch");
    for (let i = 0; i < headers.length; i++) {
      assert.equal(headers[i].height, i); assert.ok(headers[i].confirmations > 0);
      if (i) assert.equal(headers[i].previousblockhash, headers[i - 1].hash, "noncontiguous canonical headers");
    }
    this.headers = structuredClone(headers);
  }
  transaction(record: ObservedTransactionRecord) {
    const tx = record.transaction;
    assert.ok(tx.blockhash && tx.in_active_chain === true, "confirmed active-chain transaction required");
    const header = this.headers.find(h => h.hash === tx.blockhash); assert.ok(header, "transaction block missing from canonical capture");
    assert.ok(tx.confirmations && tx.confirmations > 0, "transaction not confirmed");
    const inputs = tx.vin.map(v => `${v.txid}:${integer(v.vout)}`);
    assert.equal(new Set(inputs).size, inputs.length, "duplicate input");
    assert.deepEqual([...inputs].sort(), Object.keys(record.previous_outputs).sort(), "input amount provenance mismatch");
    const outputs = tx.vout.map(o => ({ asset_id: `${tx.txid}:${integer(o.n)}`, amount: btcToMsat(o.value), output_index: o.n }));
    assert.equal(new Set(outputs.map(o => o.output_index)).size, outputs.length, "duplicate output index");
    const totalIn = sum(inputs.map(id => btcToMsat(record.previous_outputs[id].value))), totalOut = sum(outputs.map(o => o.amount));
    assert.ok(totalIn >= totalOut, "transaction creates value");
    return { input_ids: inputs, outputs, fee: totalIn - totalOut, inclusion_height: header.height, inclusion_hash: header.hash };
  }
  settlement(attempt: { payment_hash: string; amount_msat: number; final_amount_msat: number; user_fee_sat: number; lightning_htlc_subscription_id: number | null },
    proof: { payment_hash: string; preimage_sha256_verified: string }, pays: { pays: { payment_hash: string; status: string; amount_msat: number; amount_sent_msat: number }[] }) {
    assert.equal(attempt.lightning_htlc_subscription_id, null, "intra-Ark payment unsupported");
    assert.match(attempt.payment_hash, /^[0-9a-f]{64}$/); assert.equal(proof.payment_hash, attempt.payment_hash);
    assert.equal(proof.preimage_sha256_verified, attempt.payment_hash, "collector preimage attestation mismatch");
    const entries = pays.pays.filter(p => p.payment_hash === attempt.payment_hash); assert.equal(entries.length, 1, "ambiguous CLN payment");
    const pay = entries[0]; assert.equal(pay.status, "complete");
    assert.equal(msat(pay.amount_msat), msat(attempt.amount_msat)); assert.equal(msat(pay.amount_sent_msat), msat(attempt.final_amount_msat));
    const fee = integer(msat(pay.amount_sent_msat) - msat(pay.amount_msat));
    const holderFee = integer(attempt.user_fee_sat * 1000); assert.ok(holderFee >= fee, "routing subsidy unsupported");
    return { delivered: msat(pay.amount_msat), fee, service_fee: holderFee - fee, holder_fee: holderFee };
  }
}
