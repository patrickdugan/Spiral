// LayerTree as a settlement object: cost tables, the throughput assumption [C], and the capital terms the
// paper's proposal (paper/layertree_insertions.md) adds. Cost tables only; no predicate is implemented.
//
// Source: Osuntokun, "LayerTree: A Shared Bitcoin UTXO with an O(1) Unilateral Exit", draft dated
// 2026-10-15, commit ba8422e, and the repository lightninglabs/layertree at that commit. Witness weights
// are the measured figures of spec/scripts/sizes.md (total witness WU: script, witness data and a
// 129-byte control block). Transaction sizes follow the draft's model (spec 11, paper appendix "How the
// numbers are made"): a 946 WU skeleton with one payout, 774 WU without a payout, 550 WU for FULL's
// fee-from-payout exit, 172 WU per further payout, vB = ceil(WU / 4) once per transaction. The model
// leaves out witness item counts and length prefixes (10.5 vB on a FULL D = 16 exit, 10 CCV, 42.5 MID,
// 44.75 MIN) and the baselines omit anchors and fee children; every figure here inherits both omissions.
// The exit is one transaction and O(D) bytes; nothing here is O(1) in bytes.

export type Tier = "FULL" | "MID" | "MIN" | "CCV";

export const SKELETON_WU = { withPayout: 946, noPayout: 774, feeFromPayout: 550, perExtraPayout: 172 } as const;

export const vbOf = (wu: number): number => Math.ceil(wu / 4);

/** Whole-transaction vB on the draft's model. `payouts` is the number of P2TR payouts (0 for a carve, join or update). */
export function txVb(witnessWU: number, payouts: number, feeFromPayout = false): number {
  if (feeFromPayout) {
    if (payouts !== 1) throw new Error("fee-from-payout is the single-payout owner exit");
    return vbOf(witnessWU + SKELETON_WU.feeFromPayout);
  }
  const skeleton = payouts === 0 ? SKELETON_WU.noPayout : SKELETON_WU.withPayout + SKELETON_WU.perExtraPayout * (payouts - 1);
  return vbOf(witnessWU + skeleton);
}

/** Measured total witness weight (WU) from spec/scripts/sizes.md at ba8422e. Dense profile unless the key says sparse. */
export const WITNESS_WU = {
  FULL: {
    EXIT_1: { 8: 2100, 12: 2616, 16: 3132, 20: 3648 } as Record<number, number>,
    EXIT_1_TOWER_D16: 3238,
    EXIT_2_D16: 5617,
    JOIN_0_D8: 1940,   // walks eight levels: the draft's basis for the 256-slot JOIN_8 estimate
    JOIN_0_D16: 2972,
    JOIN_2_D16: 2713,
    UPDATE_D16: 3346,
    UPDATE_X_D16: 3417,
    CLAIM_D16: 5696,
    CLAIM_H_D16: 5736,
    CLAIM_X_D16: 5767,
    SPLIT_D16: 5568,
    EVICT_SUBTREE_4_D16: 7539,   // 16 positions, 13 occupied in the measured tree
    EVICT_SUBTREE_6_D16: 22681,  // 64 positions, 51 occupied
    DETACH_8_D16: 2174,
    SPARSE_EXIT_1_D32: 5602,         // six-leaf tree
    SPARSE_EXIT_1_D32_65536: 6176,   // a member of a 2^16-leaf sparse tree
  },
  MID: { EXIT_1_D16: 4474 },
  MIN: { EXIT_1_D16: 4944 },
  CCV: { EXIT_1_D16: 2683 },
} as const;

/** The draft's transaction-tree baseline: D transactions of about 150 vB and a 111 vB claim; anchors omitted. */
export const txTreeExitVb = (depth: number): number => 150 * depth + 111;

export const BARE_P2TR_SPEND_VB = 111;
export const BATCH_OUTPUT_VB = 43;
export const SELF_FUNDED_INPUT_VB = 58;

/** The draft's simple taproot channel on the same model (its Table "A simple taproot channel"). */
export const LIGHTNING_VB = { fundingAlone: 154, cooperativeClose: 154, commitment: 240, anchorChild: 152, sweep: 138 } as const;
export const lightningForceCloseVb = (): number => LIGHTNING_VB.commitment + LIGHTNING_VB.anchorChild + LIGHTNING_VB.sweep; // 530

/** Table 5 of the short draft: one exit by variant, model vB. */
export function table5(): Record<string, number> {
  const F = WITNESS_WU.FULL;
  return {
    "bare P2TR spend": BARE_P2TR_SPEND_VB,
    "one P2TR output inside a batch": BATCH_OUTPUT_VB,
    "FULL EXIT_1": txVb(F.EXIT_1[16]!, 1),
    "FULL, fee taken from the payout": txVb(F.EXIT_1[16]!, 1, true),
    "FULL, D = 8": txVb(F.EXIT_1[8]!, 1),
    "FULL, D = 20": txVb(F.EXIT_1[20]!, 1),
    "FULL tower exit": txVb(F.EXIT_1_TOWER_D16, 1),
    "FULL sparse D = 32, six-leaf tree": txVb(F.SPARSE_EXIT_1_D32, 1),
    "FULL sparse D = 32, 2^16 members": txVb(F.SPARSE_EXIT_1_D32_65536, 1),
    "MID": txVb(WITNESS_WU.MID.EXIT_1_D16, 1),
    "MIN": txVb(WITNESS_WU.MIN.EXIT_1_D16, 1),
    "CCV": txVb(WITNESS_WU.CCV.EXIT_1_D16, 1),
    "radix-2 transaction-tree exit (model)": txTreeExitVb(16),
  };
}

/** Per-operation sizes the proposal quotes (Table 7 and the operations section), all at D = 16 FULL. */
export function operationVb(): Record<string, number> {
  const F = WITNESS_WU.FULL;
  const evict4 = txVb(F.EVICT_SUBTREE_4_D16, 13);
  const evict6 = txVb(F.EVICT_SUBTREE_6_D16, 51);
  return {
    EXIT_1: txVb(F.EXIT_1[16]!, 1),
    EXIT_2: txVb(F.EXIT_2_D16, 2),
    "EXIT_2 marginal second exit": vbOf(F.EXIT_2_D16 - F.EXIT_1[16]! + SKELETON_WU.perExtraPayout),
    JOIN_0: txVb(F.JOIN_0_D16, 0),
    JOIN_2: txVb(F.JOIN_2_D16, 0),
    "JOIN_8 (estimate, 256 slots)": txVb(F.JOIN_0_D8, 0),
    UPDATE: txVb(F.UPDATE_D16, 0),
    "UPDATE^x": txVb(F.UPDATE_X_D16, 0),
    CLAIM: txVb(F.CLAIM_D16, 0),
    "CLAIM^h": txVb(F.CLAIM_H_D16, 0),
    "CLAIM^x": txVb(F.CLAIM_X_D16, 0),
    SPLIT: txVb(F.SPLIT_D16, 0),
    "renewal alone (UPDATE + SPLIT)": txVb(F.UPDATE_D16, 0) + txVb(F.SPLIT_D16, 0),
    "EVICT_SUBTREE_4 (13 leaves)": evict4,
    "EVICT_SUBTREE_4 per leaf": evict4 / 13,
    "EVICT_SUBTREE_6 (51 leaves)": evict6,
    "EVICT_SUBTREE_6 per leaf": evict6 / 51,
    "DETACH_8": vbOf(F.DETACH_8_D16 + SKELETON_WU.noPayout + SKELETON_WU.perExtraPayout), // a second tree output
    "CLAIM^x then exact exit (credit-leaf fallback)": txVb(F.CLAIM_X_D16, 0) + txVb(F.EXIT_1[16]!, 1),
  };
}

/**
 * Table 10 of the short draft: lifetime on-chain bytes per member, entry plus exit, by how the member
 * leaves. Entry is a 43 vB output in a shared transaction, or a share of a 256-slot operator-funded graft
 * (the JOIN_8 estimate over 256), plus the member's 58 vB input when self-funded. Rows are rounded to the
 * nearest vB as the draft prints them. Ark enters and leaves as outputs of round transactions whose shared
 * overhead the draft leaves out; its unilateral exit is the transaction-tree unroll of its round.
 */
export function table10(): Record<string, { never: number; batch: number; alone: number }> {
  const op = operationVb();
  const graftShare = op["JOIN_8 (estimate, 256 slots)"]! / 256;
  const sweep = op["EVICT_SUBTREE_6 per leaf"]!;
  const exit1 = op.EXIT_1!;
  const r = Math.round;
  return {
    "LayerTree, operator-funded": { never: r(graftShare), batch: r(graftShare + sweep), alone: r(graftShare + exit1) },
    "LayerTree, self-funded": { never: r(graftShare + SELF_FUNDED_INPUT_VB), batch: r(graftShare + SELF_FUNDED_INPUT_VB + sweep), alone: r(graftShare + SELF_FUNDED_INPUT_VB + exit1) },
    "Lightning channel": { never: BATCH_OUTPUT_VB + LIGHTNING_VB.cooperativeClose, batch: BATCH_OUTPUT_VB + LIGHTNING_VB.cooperativeClose, alone: BATCH_OUTPUT_VB + lightningForceCloseVb() },
    "Ark, round of 256": { never: 2 * BATCH_OUTPUT_VB, batch: 2 * BATCH_OUTPUT_VB, alone: BATCH_OUTPUT_VB + txTreeExitVb(8) },
    "Ark, round of 65,536": { never: 2 * BATCH_OUTPUT_VB, batch: 2 * BATCH_OUTPUT_VB, alone: BATCH_OUTPUT_VB + txTreeExitVb(16) },
    "bare UTXO": { never: LIGHTNING_VB.fundingAlone, batch: LIGHTNING_VB.fundingAlone, alone: LIGHTNING_VB.fundingAlone },
  };
}

// ---- Assumption [C]: contention on the one output ------------------------------------------------------

/** κ, spends of one output that confirm per block, as the draft states it: policy, not consensus. */
export const KAPPA = { preCore31ChainLimits: 25, clusterMempool: 64, descendantAttached: 1 } as const;

/** Δ(q) = Δ_L (⌈(β + q) / κ⌉ + 1): blocks until an honest spend with q queued ahead confirms, under [C]. */
export function confirmationBlocks(q: number, beta: number, kappa: number, deltaL = 1): number {
  if (kappa < 1) throw new Error("kappa >= 1");
  return deltaL * (Math.ceil((beta + q) / kappa) + 1);
}

/** Blocks for n cooperating single exits to drain through one output at κ per block. */
export const drainBlocks = (n: number, kappa: number): number => Math.ceil(n / kappa);

/** Channel leaves that may close in one window: β + q ≤ (G_exit − 1) κ with Δ_L = 1 (the draft's budget). */
export const channelLeavesPerWindow = (gExit: number, kappa: number, beta: number): number => (gExit - 1) * kappa - beta;

/**
 * Contention attack for the warden model: a corrupt member carves its own balance back and forth, each
 * carve one spend of the tree output that conserves value and costs only its fee. To hold an honest spend
 * out of a block the attacker must have κ spends confirm ahead of it at no less than the honest bid, so the
 * attacker's bytes per block of delay are κ × carve vB; divided by the honest exit's vB this is the price
 * ratio β buys. SPLIT (owner alone, 1,586 vB) is the cheapest carve that needs no operator; CLAIM on a
 * self-issued voucher is 1,618 vB.
 */
export function contentionCost(kappa: number, carveVb: number, honestVb: number): { attackerVbPerBlock: number; ratioToHonest: number } {
  const attackerVbPerBlock = kappa * carveVb;
  return { attackerVbPerBlock, ratioToHonest: attackerVbPerBlock / honestVb };
}

// ---- Fees and floors --------------------------------------------------------------------------------------

export const P2TR_DUST_SAT = 330;

/** Smallest leaf for which the exit is not a loss: the draft's two floors (spec/fee-analysis.md). */
export function minimumLeafSat(vb: number, feeRateSatPerVb: number, endogenous: boolean): number {
  const fee = vb * feeRateSatPerVb;
  return endogenous ? fee + P2TR_DUST_SAT + 1 : Math.max(fee, P2TR_DUST_SAT) + 1;
}

/** The unilateral paths and whether each needs a confirmed fee coin of the member's own (draft Table E.4). */
export function feeCoinTable(feeRates: number[]): Array<{ path: string; feeCoin: boolean; vb: number; fees: number[] }> {
  const op = operationVb();
  const rows: Array<[string, boolean, number]> = [
    ["EXIT_1, fee from the payout (FULL only)", false, table5()["FULL, fee taken from the payout"]!],
    ["EXIT_1 or exact exit, fee input", true, op.EXIT_1!],
    ["channel-leaf force close", true, 1681],   // the draft's figure; its components (exit, update, settlement, two anchor children) are not in sizes.md
    ["CLAIM^x then exact exit", true, op["CLAIM^x then exact exit (credit-leaf fallback)"]!],
  ];
  return rows.map(([path, feeCoin, vb]) => ({ path, feeCoin, vb, fees: feeRates.map((f) => vb * f) }));
}

// ---- The capital terms the proposal adds ------------------------------------------------------------------

export interface LayerTreeParams {
  depth: number;
  tier: Tier;
  members: number;
  /** blocks between credit-leaf top-ups (plain receive) or the settle window (pending-leaf receive); operator-chosen */
  topUpPeriodBlocks: number;
  /** blocks a lease runs before renewal; operator-chosen at entry */
  leasePeriodBlocks: number;
  /** expected receipts into a member's credit leaf per block, sat */
  receiptRatePerBlock: number;
  /** provisioning margin over expected receipts in one period */
  margin: number;
  /** who funds a graft: the operator fronts the cohort's value, or each member brings a 58 vB input and signs */
  funding: "operator" | "self";
  /** blocks an operator-funded graft's value stays outstanding before members pay (0 when members prepay by voucher) */
  graftOutstandingBlocks: number;
  /** value grafted per member, sat (only matters when funding is "operator") */
  graftValuePerMember: number;
  kappa: number;
  beta: number;
}

/** Bytes the draft prices per leaf for the two recurring operations; inputs, since their rewrite variants are not in sizes.md. */
export const RECURRING_VB = { creditLeafTopUpInCohort: 122, leaseRenewalInCohort: 151, leaseRenewalAlone: 2616 } as const;

/**
 * Locked capital per member under the proposal's accounting: the operator's pre-funded credit leaf, sized to
 * one top-up period of receipts with a margin, held continuously (it is refilled, not released), plus the
 * graft value the operator fronts while it is outstanding, time-averaged over the horizon. Nothing is
 * fronted at a spend. The pooled tier on the operator's own Lightning channels is common to every object
 * and, as in the paper's tables, is not charged here.
 */
export function lockedPerMember(p: LayerTreeParams, horizonBlocks: number): { creditLeaf: number; graft: number; total: number } {
  const creditLeaf = (1 + p.margin) * p.receiptRatePerBlock * p.topUpPeriodBlocks;
  const graft = p.funding === "operator" ? (p.graftValuePerMember * Math.min(p.graftOutstandingBlocks, horizonBlocks)) / horizonBlocks : 0;
  return { creditLeaf, graft, total: creditLeaf + graft };
}

/** On-chain bytes per member per block for the recurring operations: top-ups and lease renewals, batched per cohort. */
export function bytesPerMemberPerBlock(p: LayerTreeParams): number {
  return RECURRING_VB.creditLeafTopUpInCohort / p.topUpPeriodBlocks + RECURRING_VB.leaseRenewalInCohort / p.leasePeriodBlocks;
}

/** Exit bytes for the object's row of the paper's table, by tier and depth (FULL at any measured depth; other tiers at 16). */
export function exitVb(tier: Tier, depth: number): number {
  if (tier === "FULL") {
    const wu = WITNESS_WU.FULL.EXIT_1[depth];
    if (wu === undefined) throw new Error(`FULL EXIT_1 not measured at D = ${depth}`);
    return txVb(wu, 1);
  }
  if (depth !== 16) throw new Error(`${tier} measured at D = 16 only`);
  return txVb(WITNESS_WU[tier].EXIT_1_D16, 1);
}

/** MIN has no vouchers and no channel leaves, so no credit-leaf receive; the proposal's receive term does not exist there. */
export const tierHostsVouchers = (tier: Tier): boolean => tier !== "MIN";

/** Blocks in a year at ten minutes each: 365 * 144. */
export const BLOCKS_PER_YEAR = 52_560;

/** Annual cost in sat of a member's recurring on-chain bytes at a fee rate in sat/vB. */
export function annualByteCostSat(bytesPerMemberPerBlock: number, feeSatPerVb: number): number {
  return bytesPerMemberPerBlock * BLOCKS_PER_YEAR * feeSatPerVb;
}

/**
 * The receipt rate (sat per round) at which the carry of the capital a credit leaf saves equals the leaf's
 * annual byte cost. The saving scales with receipts: `savedCapitalPerUnitReceipt` is (channel stock - P_a)
 * per sat-per-round of receipts, read off a grid cell (the zero-drift cell at 100 sat a round gives
 * (104,094 - 3,000) / 100 under the oracle rule and (38,112 - 3,000) / 100 under the trailing rule).
 * Below the break-even the bytes cost more than the capital they free; above it the leaf pays.
 */
export function breakEvenReceiptRate(
  bytesPerMemberPerBlock: number, feeSatPerVb: number, costOfCapitalPerYear: number, savedCapitalPerUnitReceipt: number,
): number {
  return annualByteCostSat(bytesPerMemberPerBlock, feeSatPerVb) / (costOfCapitalPerYear * savedCapitalPerUnitReceipt);
}
