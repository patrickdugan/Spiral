import { test } from "node:test";
import assert from "node:assert/strict";
import { demand, protocol, runChannels, type Demand } from "../audit/peer_review/capital_fixed_budget.ts";

test("fixed-budget demand generation is deterministic and pilot seeds are disjoint", () => {
  assert.deepEqual(demand("steady", 201), demand("steady", 201));
  assert.notDeepEqual(demand("steady", 201), demand("steady", 301));
  assert.ok(protocol.holdout_seeds.every(s => !protocol.pilot_seeds.includes(s)));
});
test("pooled directional capacity does not allow spending another holder's balance", () => {
  const events: Demand[] = [{ height: 0, holder: 0, direction: "in", amount: 5000 },
    { height: 0, holder: 1, direction: "out", amount: 4000 }];
  const r = runChannels(events, 2, 0, 2, { local: [9306], remote: [10000] });
  assert.equal(r.delivered_sat, 5000); assert.equal(r.failures.holder, 1);
  assert.equal(r.terminal.holder_balance_sat, 5000);
});
test("fixed channel liquidity failure preserves balance and is included in offered denominator", () => {
  const r = runChannels([{ height: 0, holder: 0, direction: "in", amount: 5000 }], 1, 10000, 1,
    { local: [19306], remote: [9999] });
  assert.equal(r.offered_sat, 5000); assert.equal(r.delivered_sat, 0); assert.equal(r.failures.inbound, 1);
  assert.equal(r.terminal.holder_balance_sat, 10000); assert.equal(r.terminal.remote[0], 9999);
});
