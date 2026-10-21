import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { CapitalAccountingMachine, checkJournal, digest, type CapitalEvent, type MachineConfig } from "../../model/capital.ts";
import { capitalEventSchema } from "../../model/capital-schema.ts";
import { completeLifecycle, fixtureConfig, funded } from "../../model/capital.fixtures.ts";

const args = process.argv.slice(2);
const json = (path: string, data: unknown) => writeFileSync(path, JSON.stringify(data, null, 2) + "\n");
if (args[0] === "check") {
  const config = JSON.parse(readFileSync(args[1], "utf8")) as MachineConfig;
  const events = readFileSync(args[2], "utf8").trim().split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line)) as CapitalEvent[];
  const result = checkJournal(config, events); console.log(JSON.stringify(result, null, 2)); if (!result.ok || !result.reconciled) process.exitCode = 1;
} else if (args[0] === "build" || args.length === 0) {
  const root = resolve(args[1] ?? "audit/peer_review/capital"); mkdirSync(root, { recursive: true });
  json(resolve(root, "capital-event.schema.json"), capitalEventSchema); json(resolve(root, "config.json"), fixtureConfig);
  const trace = completeLifecycle(), events = trace.m.journal();
  writeFileSync(resolve(root, "lifecycle.jsonl"), events.map(e => JSON.stringify(e)).join("\n") + "\n");
  json(resolve(root, "lifecycle-check.json"), checkJournal(fixtureConfig, events));
  json(resolve(root, "lifecycle-summary.json"), trace.m.report());
  const m = new CapitalAccountingMachine(fixtureConfig), rows = [];
  for (const event of events) {
    m.apply(event); const state = m.snapshot(), report = m.report();
    rows.push({ event_id: event.event_id, event_type: event.event_type, height: event.block_height, seconds: event.monotonic_timestamp,
      fronting_sat: report.outstanding_fronting / 1000, unique_committed_sat: report.stocks.unique_committed / 1000,
      htlc_sat: report.stocks.htlc / 1000, idle_sat: report.stocks.idle / 1000,
      fronting_sat_blocks: Number(report.integrals.fronting.msat_blocks) / 1000,
      unique_sat_blocks: Number(report.integrals.unique_committed.msat_blocks) / 1000,
      backing: state.A.backing?.state, reserve: state.A.reserve?.state, recovered: state.A.recovered?.state ?? "NOT_CREATED" });
  }
  json(resolve(root, "trace.json"), rows);
  const keys = Object.keys(rows[0]); writeFileSync(resolve(root, "trace.csv"), keys.join(",") + "\n" + rows.map(row => keys.map(k => (row as Record<string, unknown>)[k]).join(",")).join("\n") + "\n");
  const failureTraces = [];
  for (const path of ["revocation", "timeout"] as const) {
    const t = funded(); t.add("HTLC_ACCEPTED", { operation_id: "pay-1" }); t.add("HTLC_FAILED", { operation_id: "pay-1" });
    if (path === "timeout") t.chain(5);
    t.add("RESOLVE_FAILED", { operation_id: "pay-1", path, ...(path === "timeout" ? { resolution_height: 4, resolution_hash: "block-4" } : {}) }, path === "timeout" ? { block_hash: "block-5" } : {});
    writeFileSync(resolve(root, `failure-${path}.jsonl`), t.m.journal().map(e => JSON.stringify(e)).join("\n") + "\n");
    failureTraces.push({ path, check: checkJournal(fixtureConfig, t.m.journal()), report: t.m.report() });
  }
  json(resolve(root, "failure-checks.json"), failureTraces);
  const unresolved = completeLifecycle();
  const blocks = Array.from({ length: 15 }, (_, i) => ({ height: i + 1, hash: i < 10 ? `block-${i + 1}` : `fork-${i + 1}`,
    parent_hash: i === 0 ? fixtureConfig.genesis_hash : i <= 10 ? `block-${i}` : `fork-${i}` }));
  unresolved.add("REORG", { blocks }, { block_height: 15, block_hash: "fork-15", monotonic_timestamp: 9600 });
  writeFileSync(resolve(root, "deep-reorg-unresolved.jsonl"), unresolved.m.journal().map(e => JSON.stringify(e)).join("\n") + "\n");
  json(resolve(root, "deep-reorg-status.json"), unresolved.m.report());
  json(resolve(root, "matched-service-status.json"), {
    status: "structural_sensitivity_complete_full_comparison_pending", evidence_class: "implementation_informed_forecast", reference_trace_hash: digest(events),
    reason: "Four paired fee-free sensitivities now apply retained change and explicit recovery delays. The full comparison still needs fees, round overhead, deduplicated underlying assets, disjoint pilot budgets and service-target holdouts. Snapshot detection heights are not precise operational clocks.",
    structural_sensitivity: "audit/peer_review/capital_comparison.md",
    existing_results: "audit/peer_review/model_sensitivity.json remains a reference-model sensitivity; it has not been relabeled or overwritten.",
    reference_lifecycle: { offered_sat: trace.m.report().totals.offered / 1000, delivered_sat: trace.m.report().totals.delivered / 1000,
      delivery_rate: trace.m.report().delivery_rate, outstanding_fronting_sat: trace.m.report().outstanding_fronting / 1000 },
    required_before_rerun: ["Verify source/binary/container pins and actual genesis", "Reconcile complete observed lifecycle and independent reuse",
      "Fit recovery delays per policy, retaining censored cases and recovery fees", "Freeze pilot budgets and service target before holdout seeds",
      "Apply the same offered trace to all objects; publish failures and both volume denominators", "Deduplicate unique asset coverage; do not sum channel and fronting categories"] });
  console.log(JSON.stringify({ artifacts: root, events: events.length, state_hash: trace.m.stateHash(), evidence_class: fixtureConfig.evidence_class }));
} else {
  throw new Error("Usage: capital_artifacts.ts build [directory] | check config.json events.jsonl");
}
