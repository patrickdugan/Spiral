import { test } from "node:test";
import assert from "node:assert/strict";
import {
  table5, table10, operationVb, txVb, WITNESS_WU, confirmationBlocks, drainBlocks, channelLeavesPerWindow,
  contentionCost, minimumLeafSat, feeCoinTable, lockedPerMember, bytesPerMemberPerBlock, exitVb, tierHostsVouchers,
  KAPPA, annualByteCostSat, breakEvenReceiptRate, type LayerTreeParams,
} from "./layertree.ts";

test("LayerTree cost tables: the draft's Table 5 and Table 10 are reproduced from the measured witness weights and the stated skeleton", () => {
  // Table 5 (short draft, Appendix D): one exit by variant, model vB.
  assert.deepEqual(table5(), {
    "bare P2TR spend": 111,
    "one P2TR output inside a batch": 43,
    "FULL EXIT_1": 1020,
    "FULL, fee taken from the payout": 921,
    "FULL, D = 8": 762,
    "FULL, D = 20": 1149,
    "FULL tower exit": 1046,
    "FULL sparse D = 32, six-leaf tree": 1637,
    "FULL sparse D = 32, 2^16 members": 1781,
    "MID": 1355,
    "MIN": 1473,
    "CCV": 908,
    "radix-2 transaction-tree exit (model)": 2511,
  });
  // Table 3 depths beside them.
  assert.equal(txVb(WITNESS_WU.FULL.EXIT_1[12]!, 1), 891);

  // Table 7 and the operations section.
  const op = operationVb();
  assert.equal(op.EXIT_2, 1684);
  assert.equal(op["EXIT_2 marginal second exit"], 665);
  assert.equal(op.JOIN_0, 937);
  assert.equal(op.JOIN_2, 872);
  assert.equal(op["JOIN_8 (estimate, 256 slots)"], 679);
  assert.equal(op.UPDATE, 1030);
  assert.equal(op["UPDATE^x"], 1048);
  assert.equal(op.CLAIM, 1618);
  assert.equal(op["CLAIM^h"], 1628);
  assert.equal(op["CLAIM^x"], 1636);
  assert.equal(op.SPLIT, 1586);
  assert.equal(op["renewal alone (UPDATE + SPLIT)"], 2616);
  assert.equal(op["EVICT_SUBTREE_4 (13 leaves)"], 2638);
  assert.equal(Math.round(op["EVICT_SUBTREE_4 per leaf"]! * 10) / 10, 202.9);
  assert.equal(op["EVICT_SUBTREE_6 (51 leaves)"], 8057);
  assert.equal(Math.round(op["EVICT_SUBTREE_6 per leaf"]!), 158);
  assert.equal(op.DETACH_8, 780);
  assert.equal(op["CLAIM^x then exact exit (credit-leaf fallback)"], 2656);

  // Table 10: lifetime bytes per member, entry plus exit, as printed.
  assert.deepEqual(table10(), {
    "LayerTree, operator-funded": { never: 3, batch: 161, alone: 1023 },
    "LayerTree, self-funded": { never: 61, batch: 219, alone: 1081 },
    "Lightning channel": { never: 197, batch: 197, alone: 573 },
    "Ark, round of 256": { never: 86, batch: 86, alone: 1354 },
    "Ark, round of 65,536": { never: 86, batch: 86, alone: 2554 },
    "bare UTXO": { never: 154, batch: 154, alone: 154 },
  });
});

test("LayerTree [C], fees and the proposal's capital terms: the draft's worked figures and the floors follow from the stated parameters", () => {
  // [C]: 10,000 cooperating exits take 400 blocks at κ = 25 and 157 at 64; the last of q queued confirms within Δ(q).
  assert.equal(drainBlocks(10_000, KAPPA.preCore31ChainLimits), 400);
  assert.equal(drainBlocks(10_000, KAPPA.clusterMempool), 157);
  assert.equal(confirmationBlocks(0, 0, 25), 1);
  assert.equal(confirmationBlocks(24, 0, 25), 2);
  assert.equal(confirmationBlocks(25, 0, 25), 2);
  assert.equal(confirmationBlocks(0, 50, 25), 3);
  // About 1,775 channel leaves may close in one window with G_exit = 72, κ = 25, β = 0.
  assert.equal(channelLeavesPerWindow(72, 25, 0), 1775);
  // Contention: holding an honest 1,020 vB exit out of one block costs the attacker κ carves at the honest bid.
  const c25 = contentionCost(25, operationVb().SPLIT!, 1020);
  assert.equal(c25.attackerVbPerBlock, 39_650);
  assert.ok(c25.ratioToHonest > 38 && c25.ratioToHonest < 40);
  assert.equal(contentionCost(1, operationVb().SPLIT!, 1020).attackerVbPerBlock, 1586);

  // Floors (spec/fee-analysis.md, D = 16 FULL): exogenous max(fee, dust) + 1; endogenous fee + dust + 1.
  assert.equal(minimumLeafSat(1020, 10, false), 10_201);
  assert.equal(minimumLeafSat(921, 10, true), 9_541);
  assert.equal(minimumLeafSat(1020, 2, false), 2_041);
  assert.equal(minimumLeafSat(921, 50, true), 46_381);
  // The fee-coin table at 2, 10 and 50 sat/vB (draft Table E.4).
  const fc = feeCoinTable([2, 10, 50]);
  assert.deepEqual(fc.map((r) => [r.feeCoin, r.vb, ...r.fees]), [
    [false, 921, 1842, 9210, 46050],
    [true, 1020, 2040, 10200, 51000],
    [true, 1681, 3362, 16810, 84050],
    [true, 2656, 5312, 26560, 132800],
  ]);

  // Capital terms: a credit leaf sized to one period of receipts; the grid's zero-drift receipt rate is 100 sat per round of 6 blocks.
  const p: LayerTreeParams = {
    depth: 16, tier: "FULL", members: 200, topUpPeriodBlocks: 144, leasePeriodBlocks: 4032,
    receiptRatePerBlock: 100 / 6, margin: 0.25, funding: "operator", graftOutstandingBlocks: 0, graftValuePerMember: 0,
    kappa: 25, beta: 0,
  };
  const locked = lockedPerMember(p, 8 * 4032);
  assert.ok(Math.abs(locked.creditLeaf - 3000) < 1e-9);
  assert.equal(locked.graft, 0);
  // Against the oracle channel stock of the same cell (20,818,750 sat over 200 agents), about 35 times less capital...
  assert.ok(20_818_750 / 200 / locked.total > 30);
  // ...bought with about 0.88 vB per member per block on chain, which the paper's duration does not price.
  assert.ok(Math.abs(bytesPerMemberPerBlock(p) - (122 / 144 + 151 / 4032)) < 1e-12);
  // Exit bytes by tier; MIN hosts no vouchers, so the receive term does not exist there.
  assert.equal(exitVb("FULL", 16), 1020);
  assert.equal(exitVb("CCV", 16), 908);
  assert.equal(tierHostsVouchers("MIN"), false);
  assert.throws(() => exitVb("MID", 8));
  // Pricing the bytes (Section 4.4, preregistration): 0.88 vB per member per block is about 46,500 vB a year,
  // 93,000 sat at 2 sat/vB, against a carry of about 2,000 sat a year on the oracle saving at 2 percent in bitcoin
  // terms (a liquidity-lease rate; Bhatia's LNRR examples, 0.18 to 0.25 percent, are an order lower).
  const b = bytesPerMemberPerBlock(p);
  assert.equal(Math.round(annualByteCostSat(b, 1) / 100) * 100, 46_500);
  assert.equal(Math.round(annualByteCostSat(b, 2) / 1000) * 1000, 93_000);
  const savedOracle = (104_094 - 3000) / 100, savedTrailing = (38_112 - 3000) / 100;
  assert.ok(annualByteCostSat(b, 2) / (0.02 * savedOracle * 100) > 45 && annualByteCostSat(b, 2) / (0.02 * savedOracle * 100) < 47);
  assert.equal(Math.round(breakEvenReceiptRate(b, 2, 0.02, savedOracle) / 100) * 100, 4_600);
  assert.equal(Math.round(breakEvenReceiptRate(b, 10, 0.02, savedOracle) / 1000) * 1000, 23_000);
  assert.equal(Math.round(breakEvenReceiptRate(b, 50, 0.02, savedOracle) / 1000) * 1000, 115_000);
  // At an LNRR-scale floor of a quarter of a percent the break-even is eight times higher.
  assert.ok(Math.abs(breakEvenReceiptRate(b, 10, 0.0025, savedOracle) / breakEvenReceiptRate(b, 10, 0.02, savedOracle) - 8) < 1e-9);
  const ratio = breakEvenReceiptRate(b, 10, 0.02, savedTrailing) / breakEvenReceiptRate(b, 10, 0.02, savedOracle);
  assert.ok(ratio > 2.8 && ratio < 3.0);
});
