import { test } from "node:test";
import assert from "node:assert/strict";
import { funded, fixtureConfig } from "./capital.fixtures.ts";
import { CapitalAccountingMachine, sats, type CapitalEvent } from "./capital.ts";

// Dependency-free stateful property runner. Each seed generates a command sequence;
// on failure, deletion shrinking finds a 1-minimal command sequence and prints it.
// The predicate distinguishes accepted commands from rejected ones, and asserts
// invariants, rejection identity, idempotence and replay after EVERY command.
function exercise(seed: number, commands: number[]) {
  const t = funded(1 + seed % 500000, seed % 1000);
  for (const command of commands) {
    const s = t.m.snapshot(), op = s.H.operations["pay-1"], hash = t.m.stateHash(), journal = t.m.journal();
    let e: CapitalEvent;
    switch (command % 9) {
      case 0: e = t.event("HTLC_ACCEPTED", { operation_id: "pay-1" }); break;
      case 1: e = t.event("HTLC_FAILED", { operation_id: "pay-1" }); break;
      case 2: e = t.event("RESOLVE_FAILED", { operation_id: "pay-1", path: "revocation" }); break;
      case 3: e = t.event("CANCEL_REQUEST", { operation_id: "pay-1" }); break;
      case 4: e = t.event("HTLC_SETTLED", { operation_id: "pay-1", fee: op.max_fee, preimage_evidence_ref: "property:verified",
        change: { claim_id: "change", claimant: "alice", allocations: { reserve: op.gross - op.delivered - op.max_fee }, expiry_height: s.J.height + 30 } },
        { amount: op.delivered, evidence_refs: ["property:verified"] }); break;
      case 5: e = t.event("TICK", {}, { block_height: s.J.height + command % 5, monotonic_timestamp: (s.J.timestamp ?? 0) + command % 5 * 600 }); break;
      case 6: e = t.event("EXPIRY_REACHED", { operation_id: "pay-1" }); break;
      case 7: e = t.event("ISSUE_VTXO", { claim: { claim_id: `conflict-${t.serial}`, claimant: "eve", allocations: { backing: sats(1001) }, expiry_height: s.J.height + 5 } }, { amount: sats(1001) }); break;
      default: e = t.event("REQUEST_OUTGOING", { ...op, operation_id: `again-${t.serial}` }, { amount: op.delivered }); break;
    }
    let accepted = false;
    try { t.m.apply(e); accepted = true; } catch { /* Invalid generated transitions are expected. */ }
    if (!accepted) { assert.equal(t.m.stateHash(), hash); assert.deepEqual(t.m.journal(), journal); }
    else { const h = t.m.stateHash(); t.m.apply(e); assert.equal(t.m.stateHash(), h); }
    t.m.check(); assert.equal(CapitalAccountingMachine.replay(fixtureConfig, t.m.journal()).stateHash(), t.m.stateHash());
  }
}
export function shrink(commands: number[], fails: (commands: number[]) => boolean): number[] {
  let best = [...commands], changed = true;
  while (changed) { changed = false; for (let i = 0; i < best.length; i++) { const smaller = best.filter((_, j) => i !== j); if (fails(smaller)) { best = smaller; changed = true; break; } } }
  return best;
}
test("stateful properties: 128 seeds x 32 randomized commands, with deletion-shrunk counterexamples", () => {
  for (let seed = 1; seed <= 128; seed++) {
    let state = seed; const commands = Array.from({ length: 32 }, () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state; });
    try { exercise(seed, commands); } catch (error) {
      const minimal = shrink(commands, xs => { try { exercise(seed, xs); return false; } catch { return true; } });
      assert.fail(JSON.stringify({ seed, minimized_commands: minimal, original_error: String(error) }));
    }
  }
});
test("counterexample shrinker removes irrelevant commands", () => {
  assert.deepEqual(shrink([1, 2, 3, 4, 5], xs => xs.includes(2) && xs.includes(5)), [2, 5]);
});
