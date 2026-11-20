import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_SCENARIO, runFiniteBudget, type FiniteBudgetScenario } from "./capital-bound.ts";

const scenario = (): FiniteBudgetScenario => structuredClone(DEFAULT_SCENARIO);

test("finite budgets govern both Ark admission gates and retain every offered invoice", () => {
  const r = runFiniteBudget(scenario());
  assert.equal(r.summary.lightning.offered_invoices, 6);
  assert.equal(r.summary.ark.offered_invoices, 6);
  assert.equal(r.summary.lightning.offered_value_sat, 2600);
  assert.equal(r.summary.ark.offered_value_sat, 2600);
  assert.equal(r.summary.lightning.settled_invoices, 6);
  assert.equal(r.summary.ark.settled_invoices, 4);
  assert.equal(r.summary.ark.settled_value_sat, 1800);
  assert.deepEqual(r.summary.ark.failure_counts, { server_channel_inbound_capacity: 1, fronting_capacity: 1 });
  assert.equal(r.summary.ark.outcomes[4]!.settled, false);
  assert.equal(r.summary.ark.outcomes[5]!.settled, true);
  assert.equal(r.summary.terminal_ark_fronting_locked_sat, 0);
  for (const arm of ["lightning", "ark"] as const) {
    assert.equal(r.events[arm].filter((e) => e.kind === "payment_offered").length, 6);
    const funded = r.events[arm].filter((e) => e.kind === "lot_open").reduce((sum, e) => sum + Number(e.amount_sat), 0);
    assert.equal(funded, 1600);
    assert.equal(r.events[arm].at(-1)!.height, 20);
    assert.equal(r.events[arm][0]!.offered_trace_sha256, r.summary.offered_trace_sha256);
  }
});

test("a modeled proof marker cannot release a reserve or enable a rejected spend", () => {
  const withMarker = runFiniteBudget(scenario());
  const without = scenario();
  without.proofMarkers = [];
  const withoutMarker = runFiniteBudget(without);
  assert.deepEqual(withMarker.summary.ark, withoutMarker.summary.ark);
  assert.deepEqual(withMarker.events.ark.filter((e) => e.kind !== "proof_verified"), withoutMarker.events.ark);
  assert.equal(withMarker.events.ark.filter((e) => e.kind === "proof_verified").length, 1);
  assert.equal(withMarker.summary.evidence_level, "simulation");
  assert.equal(withMarker.summary.evidence_verified, false);
});

test("expiry recovery is timestamped at each actual model sweep, including inside the drain", () => {
  const r = runFiniteBudget(scenario());
  const releases = r.events.ark.filter((e) => e.kind === "lot_state" && e.state === "available");
  assert.deepEqual(releases.map((e) => e.height), [10, 10, 10, 10, 10, 12, 12, 12, 12]);
  const paidAt10 = r.events.ark.findIndex((e) => e.kind === "payment_settled" && e.invoice_id === "b-out-after-sweep");
  const firstRecovered = r.events.ark.findIndex((e) => e.kind === "lot_state" && e.state === "available");
  assert.ok(firstRecovered < paidAt10);
  const firstRelock = r.events.ark.findIndex((e) => e.kind === "lot_state" && e.state === "unavailable" && e.height === 10);
  assert.equal(r.events.ark[firstRelock]!.lot_id, r.events.ark[firstRecovered]!.lot_id);
});

test("gross selected input value including change controls fronting admission", () => {
  const s = scenario();
  s.config = { ...s.config, holders: ["a"], budgetSat: 1000, frontingSat: 300 };
  s.requests = [
    { invoiceId: "in", holder: "a", direction: "receive", amountSat: 500, atBlock: 0 },
    { invoiceId: "out", holder: "a", direction: "send", amountSat: 300, atBlock: 1 },
  ];
  const rejected = runFiniteBudget(s);
  assert.equal(rejected.summary.ark.outcomes[1]!.reason, "fronting_capacity");
  assert.equal(rejected.events.ark.filter((e) => e.kind === "lot_state").length, 0);
  assert.equal(rejected.summary.terminal_ark_holder_claims_sat, 500);
  s.config.frontingSat = 500;
  const accepted = runFiniteBudget(s);
  assert.equal(accepted.summary.ark.settled_invoices, 2);
  assert.equal(accepted.events.ark.filter((e) => e.kind === "lot_state" && e.state === "unavailable").length, 5);
  assert.equal(accepted.summary.terminal_ark_holder_claims_sat, 200);
});

test("round-lock experiment recovers at the configured model clock", () => {
  const s = scenario();
  s.config.spendLock = "round";
  const r = runFiniteBudget(s);
  assert.equal(r.summary.ark.outcomes[4]!.settled, true);
  const releases = r.events.ark.filter((e) => e.kind === "lot_state" && e.state === "available");
  assert.deepEqual([...new Set(releases.map((e) => e.height))], [3, 5]);
  assert.equal(r.summary.terminal_ark_fronting_locked_sat, 0);
});

test("expired holder claims cannot be spent by the finite-budget entry point", () => {
  const s = scenario();
  s.config = { ...s.config, holders: ["a"], budgetSat: 1000, frontingSat: 500 };
  s.requests = [
    { invoiceId: "in", holder: "a", direction: "receive", amountSat: 500, atBlock: 0 },
    { invoiceId: "expired-out", holder: "a", direction: "send", amountSat: 500, atBlock: 10 },
  ];
  const r = runFiniteBudget(s);
  assert.equal(r.summary.ark.outcomes[1]!.reason, "unexpired_holder_value");
  assert.equal(r.summary.terminal_ark_holder_claims_sat, 500);
  assert.equal(r.events.ark.filter((e) => e.kind === "lot_state").length, 0);
});

test("zero fronting and a zero server channel fail through their own admission gates", () => {
  const s = scenario();
  s.config.frontingSat = 0;
  const noFront = runFiniteBudget(s);
  assert.ok(noFront.summary.ark.outcomes.filter((r) => r.direction === "send").every((r) => !r.settled));
  s.config.frontingSat = s.config.budgetSat;
  const noChannel = runFiniteBudget(s);
  assert.ok(noChannel.summary.ark.outcomes.every((r) => !r.settled));
  assert.equal(noChannel.summary.ark.failure_counts.server_channel_inbound_capacity, 3);
});

test("invalid amounts, denomination, duplicate invoices, clocks, and unknown holders fail before a run", () => {
  const mutations: Array<(s: FiniteBudgetScenario) => void> = [
    (s) => { s.requests[0]!.amountSat = -1; },
    (s) => { s.requests[0]!.amountSat = 1.5; },
    (s) => { s.requests[0]!.amountSat = 101; },
    (s) => { s.requests[0]!.amountSat = Number.MAX_SAFE_INTEGER + 1; },
    (s) => { s.requests[1]!.invoiceId = s.requests[0]!.invoiceId; },
    (s) => { s.requests[1]!.atBlock = 1; s.requests[2]!.atBlock = 0; },
    (s) => { s.requests[0]!.holder = "unknown"; },
    (s) => { s.config.budgetSat = 1550; },
    (s) => { s.config.frontingSat = 1700; },
    (s) => { s.config.budgetSat = 500_000; },
    (s) => { s.config.arrivalHorizonBlocks = 9; },
    (s) => { s.config.holders = ["a", "a"]; },
    (s) => { s.config.secondsPerBlock = 0; },
    (s) => { s.proofMarkers = [{ atBlock: 21, proofId: "late" }]; },
  ];
  for (const mutate of mutations) {
    const s = scenario();
    mutate(s);
    assert.throws(() => runFiniteBudget(s));
  }
});

test("replay preserves the exact event trace and all offered request identities", () => {
  const first = runFiniteBudget(scenario());
  const second = runFiniteBudget(scenario());
  assert.deepEqual(first, second);
  const lnOffered = first.events.lightning.filter((e) => e.kind === "payment_offered");
  const arkOffered = first.events.ark.filter((e) => e.kind === "payment_offered");
  assert.deepEqual(lnOffered, arkOffered);
});
