import { test } from "node:test";
import assert from "node:assert/strict";
import { SettlementLedger, conservationGap } from "./ledger.ts";

test("S1: cross-class conservation holds at every settled state and with holds during pending intervals", () => {
  const L = new SettlementLedger();
  L.fund("U", "alice", 1_000_000);
  L.fund("U", "server", 5_000_000);

  // U→C funding (k confirmations), U→V board (round), C→E escrow deposit (confirmations), V→C HTLC spend.
  L.initiate({ id: "fund", from: { cls: "U", holder: "alice" }, to: { cls: "C", holder: "alice" }, amount: 400_000, fee: 300, clock: { kind: "confirmations", required: 3 } });
  L.initiate({ id: "board", from: { cls: "U", holder: "alice" }, to: { cls: "V", holder: "alice" }, amount: 200_000, fee: 200, clock: { kind: "round", roundId: "r1" } });
  assert.equal(L.available("U", "alice"), 1_000_000 - 400_300 - 200_200);
  assert.equal(conservationGap(L.snapshot()), 0);

  L.advance(3);
  L.settle("fund");
  assert.equal(L.balance("C", "alice"), 400_000);
  assert.equal(conservationGap(L.snapshot()), 0);

  assert.throws(() => L.settle("board"), /clock/); // round not confirmed
  L.confirmRound("r1");
  L.settle("board");
  assert.equal(L.balance("V", "alice"), 200_000);

  L.initiate({ id: "htlc", from: { cls: "V", holder: "alice" }, to: { cls: "C", holder: "server" }, amount: 50_000, fee: 50, clock: { kind: "htlc" } });
  L.abort("htlc"); // timed out: hold released, nothing moved
  assert.equal(L.balance("V", "alice"), 200_000);
  assert.equal(L.held("V", "alice"), 0);

  L.initiate({ id: "dep", from: { cls: "C", holder: "alice" }, to: { cls: "E", holder: "alice" }, amount: 100_000, fee: 100, clock: { kind: "confirmations", required: 1 } });
  L.advance(1);
  L.settle("dep");
  // Escrow release disproved: slashed leaves the holder sum but stays in the identity.
  L.initiate({ id: "rel", from: { cls: "E", holder: "alice" }, to: { cls: "U", holder: "alice" }, amount: 100_000, fee: 0, clock: { kind: "challenge", delta: 10, disproved: true } });
  L.advance(10);
  L.settle("rel");
  const s = L.snapshot();
  assert.equal(s.slashed, 100_000);
  assert.equal(conservationGap(s), 0);
  assert.equal(L.pending().length, 0);
});

test("S1/L3: a rejected initiation is the identity on ledger state", () => {
  const L = new SettlementLedger();
  L.fund("C", "bob", 1_000);
  const before = JSON.stringify(L.snapshot());
  assert.throws(() => L.initiate({ id: "x", from: { cls: "C", holder: "bob" }, to: { cls: "V", holder: "bob" }, amount: 2_000, fee: 0, clock: { kind: "htlc" } }), /insufficient/);
  assert.equal(JSON.stringify(L.snapshot()), before);
  assert.equal(L.held("C", "bob"), 0);
});
