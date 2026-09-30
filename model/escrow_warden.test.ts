import { test } from "node:test";
import assert from "node:assert/strict";
import { Escrow, BITVM3_PUBLISHED, safeUnderChallengers, type EscrowParams } from "./escrow.ts";
import { naiveGrossToNet, internalVolumeRatio, attestersOf, benignTrace, coalitionTrace, sample, repeatedCycleShare } from "./warden.ts";

const P: EscrowParams = { ...BITVM3_PUBLISHED, delta: 144, feeRate: 2 };

test("S4: a false assertion is slashed by one honest challenger at a cost independent of the bond", () => {
  const small = new Escrow(10_000, P);
  const large = new Escrow(10_000_000_000, P);
  for (const e of [small, large]) {
    e.assert(100, false);
    assert.ok(e.disprove(120));
    assert.equal(e.state, "slashed");
    assert.equal(e.costs.challengerFees, BITVM3_PUBLISHED.disproveVb * P.feeRate);
  }
  assert.equal(small.costs.challengerFees, large.costs.challengerFees);
  assert.ok(safeUnderChallengers(1) && !safeUnderChallengers(0));
});

test("S4: a true assertion cannot be disproved and releases only after Δ; operator pays Assert and capital lockup", () => {
  const e = new Escrow(500_000, P, 0);
  e.assert(10, true);
  assert.equal(e.disprove(50), false);
  assert.equal(e.state, "claimed");
  assert.equal(e.withdraw(10 + P.delta - 1), false);
  assert.ok(e.withdraw(10 + P.delta));
  assert.equal(e.state, "released");
  assert.equal(e.costs.operatorFees, BITVM3_PUBLISHED.assertVb * P.feeRate);
  assert.equal(e.costs.capitalBlocks, 500_000 * (10 + P.delta));
});

test("S4: the audit's negative-slash and over-release defects cannot arise; the bond is an object with fixed transitions", () => {
  const e = new Escrow(25_000, P);
  assert.throws(() => new Escrow(-1_249, P));
  e.assert(0, true);
  assert.throws(() => e.assert(1, true)); // no double claim
  assert.ok(e.withdraw(P.delta));
  assert.equal(e.withdraw(P.delta + 1), false); // no second release
  assert.equal(e.disprove(P.delta + 1), false); // nothing left to disprove
});

test("S5 statistics on fixtures: naive churn has no stable direction; direct-attester netting saturates on dense benign trade and misses a 4-relay; repeated-cycle share separates", () => {
  const agents = Array.from({ length: 40 }, (_, i) => `n${i}`);
  const benign = benignTrace(agents, 4_000);
  const relay4 = coalitionTrace(agents, ["n0", "n1", "n2", "n3"], 4_000);
  const relay2 = coalitionTrace(agents, ["n0", "n1"], 4_000);
  const claimant = "n0";

  // Naive statistic: large in every world. (Here the relays score higher; in the hive baseline benign scored higher.
  // Either way the direction is fixture-dependent, which is the point.)
  for (const t of [benign, relay4, relay2]) assert.ok(naiveGrossToNet(t) > 5);

  // Direct-attester netting: catches the reciprocal pair; misses the four-member relay (as the hive baseline did);
  // and on dense benign trade the attesting set is almost everyone, so the ratio saturates instead of staying low.
  const ivr = (t: typeof benign) => internalVolumeRatio(t, claimant, attestersOf(t, claimant));
  assert.ok(ivr(relay2) >= 0.99, `2-relay ${ivr(relay2)}`);
  assert.ok(ivr(relay4) < 0.5, `4-relay ${ivr(relay4)}`);
  assert.ok(ivr(benign) > 0.5, `benign saturation ${ivr(benign)}`); // documented failure mode, not a pass condition

  // Repeated-cycle share through the claimant separates both relays from benign at this density.
  assert.ok(repeatedCycleShare(relay4, claimant) >= 0.99);
  assert.ok(repeatedCycleShare(relay2, claimant) >= 0.99);
  assert.ok(repeatedCycleShare(benign, claimant) < 0.2);

  // Partial observation (~12% coverage, O_peer-style) preserves the cycle-share separation on these fixtures
  // because the relays are high-volume; the multiplicity threshold must scale with coverage × volume in general.
  const thin = (t: typeof benign) => sample(t, 0.12);
  assert.ok(repeatedCycleShare(thin(relay4), claimant) >= 0.99);
  assert.ok(repeatedCycleShare(thin(benign), claimant) < 0.2);
});
