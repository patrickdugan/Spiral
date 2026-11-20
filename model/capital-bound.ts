/**
 * Enforced finite-budget witness for Capital Bound Moves.
 *
 * Both arms replay exactly the offered trace. Lightning has fixed per-holder channels. Ark has
 * a fixed aggregate channel plus a DISJOINT fronting reserve, whose sum equals Lightning's budget.
 * This partition is an explicit reference-model funding policy, not an Ark balance-sheet claim.
 * Settlement is instantaneous, fees are zero, automatic refresh is disabled, and expired VTXOs
 * cannot fund new spends. The drain covers every possible forfeit sweep under those assumptions.
 * All timestamps, proof markers, and release receipts are synthetic. No network or wallet is used.
 *
 * Run with Node 24: node model/capital-bound.ts --out output/capital-bound
 * Optional: --input scenario.json with the shape of DEFAULT_SCENARIO below.
 */
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ArkServer, type ServerCapitalEvent } from "./server.ts";

export interface FiniteBudgetConfig {
  runId: string;
  holders: string[];
  budgetSat: number;
  frontingSat: number;
  quantumSat: number;
  lifetimeBlocks: number;
  roundInterval: number;
  spendLock: "expiry" | "round";
  arrivalHorizonBlocks: number;
  secondsPerBlock: number;
}

export interface OfferedPayment {
  invoiceId: string;
  atBlock: number;
  holder: string;
  direction: "receive" | "send";
  amountSat: number;
}

/** Merely records a simulation marker; it never calls a prover or changes a capital state. */
export interface ProofMarker { atBlock: number; proofId: string; }
export interface FiniteBudgetScenario {
  config: FiniteBudgetConfig;
  requests: OfferedPayment[];
  proofMarkers?: ProofMarker[];
}
export type LabEvent = { kind: string; height: number; time_s: number; [key: string]: unknown };
export interface PaymentOutcome extends OfferedPayment { settled: boolean; reason?: string; }

const MAX_LOTS = 4096;
const MAX_REQUESTS = 10_000;
const MAX_EVENTS_PER_ARM = 200_000;
const integer = (n: number, field: string, minimum = 0): number => {
  if (!Number.isSafeInteger(n) || n < minimum) throw new Error(`${field} must be a safe integer >= ${minimum}`);
  return n;
};
const name = (s: string, field: string): string => {
  if (typeof s !== "string" || !s.trim()) throw new Error(`${field} must be a nonempty string`);
  return s;
};
const hash = (value: unknown): string => createHash("sha256").update(JSON.stringify(value)).digest("hex");

function validate(scenario: FiniteBudgetScenario): number {
  const c = scenario.config;
  name(c.runId, "runId");
  if (!Array.isArray(c.holders) || !c.holders.length || new Set(c.holders).size !== c.holders.length) {
    throw new Error("holders must be a nonempty list of distinct names");
  }
  c.holders.forEach((h) => name(h, "holder"));
  for (const k of ["budgetSat", "quantumSat", "lifetimeBlocks", "roundInterval", "secondsPerBlock"] as const) integer(c[k], k, 1);
  for (const k of ["frontingSat", "arrivalHorizonBlocks"] as const) integer(c[k], k);
  if (c.frontingSat > c.budgetSat) throw new Error("fronting reserve exceeds total budget");
  if (c.budgetSat % c.quantumSat || c.frontingSat % c.quantumSat) throw new Error("reserves must be multiples of quantumSat");
  if (c.budgetSat / c.quantumSat > MAX_LOTS) throw new Error(`at most ${MAX_LOTS} disjoint reserve lots are supported`);
  if (c.spendLock !== "expiry" && c.spendLock !== "round") throw new Error("unknown spendLock");
  const endBlock = integer(c.arrivalHorizonBlocks + c.lifetimeBlocks, "drain end");
  integer(endBlock * c.secondsPerBlock, "synthetic end time");
  if (!Array.isArray(scenario.requests) || scenario.requests.length > MAX_REQUESTS) throw new Error("too many requests or invalid request list");
  let last = 0;
  let offered = 0;
  const ids = new Set<string>();
  for (const r of scenario.requests) {
    name(r.invoiceId, "invoiceId");
    if (ids.has(r.invoiceId)) throw new Error("duplicate invoiceId");
    ids.add(r.invoiceId);
    integer(r.atBlock, "request height");
    if (r.atBlock < last || r.atBlock > c.arrivalHorizonBlocks) throw new Error("request heights must be ordered and within arrival horizon");
    last = r.atBlock;
    if (!c.holders.includes(r.holder)) throw new Error("unknown holder");
    if (r.direction !== "receive" && r.direction !== "send") throw new Error("unknown payment direction");
    integer(r.amountSat, "amountSat", 1);
    if (r.amountSat % c.quantumSat) throw new Error("payment amounts must be multiples of quantumSat");
    offered = integer(offered + r.amountSat, "total offered value");
  }
  const proofs = new Set<string>();
  for (const marker of scenario.proofMarkers ?? []) {
    name(marker.proofId, "proofId");
    integer(marker.atBlock, "proof marker height");
    if (marker.atBlock > endBlock || proofs.has(marker.proofId)) throw new Error("duplicate or out-of-window proof marker");
    proofs.add(marker.proofId);
  }
  return endBlock;
}

/** Fixed denomination makes each economic reserve one immutable lot in the shared JSONL format. */
class Recorder {
  readonly events: LabEvent[] = [];
  readonly arm: "lightning" | "ark";
  readonly config: FiniteBudgetConfig;
  constructor(arm: "lightning" | "ark", config: FiniteBudgetConfig, offeredTraceHash: string) {
    this.arm = arm;
    this.config = config;
    this.emit("run_start", 0, {
      run_id: `${config.runId}:${arm}`, evidence_level: "simulation", evidence_verified: false,
      arm, offered_trace_sha256: offeredTraceHash, clock: "synthetic_fixed_seconds_per_block",
      application_settlement: "instantaneous_reference_model_acceptance", funding_boundary: "all_disjoint_channel_and_fronting_reserves",
    });
  }
  emit(kind: string, height: number, fields: Record<string, unknown> = {}): void {
    if (this.events.length >= MAX_EVENTS_PER_ARM) throw new Error("simulation event limit reached");
    if (height < (this.events.at(-1)?.height ?? 0)) throw new Error("internal event clock moved backward");
    this.events.push({ ...fields, kind, height, time_s: height * this.config.secondsPerBlock });
  }
  open(id: string, owner: string): void {
    this.emit("lot_open", 0, { lot_id: id, reserve_id: `simulation:${id}`,
      amount_sat: this.config.quantumSat, owner, state: "available" });
  }
  payment(r: OfferedPayment, reason?: string): void {
    if (reason) this.emit("payment_attempt_failed", r.atBlock, { invoice_id: r.invoiceId, reason });
    else this.emit("payment_settled", r.atBlock, { invoice_id: r.invoiceId, amount_sat: r.amountSat,
      receipt: `simulation:${this.arm}:${r.invoiceId}` });
  }
}

function summarize(outcomes: PaymentOutcome[]) {
  return {
    offered_invoices: outcomes.length,
    settled_invoices: outcomes.filter((r) => r.settled).length,
    offered_value_sat: outcomes.reduce((sum, r) => sum + r.amountSat, 0),
    settled_value_sat: outcomes.filter((r) => r.settled).reduce((sum, r) => sum + r.amountSat, 0),
    failure_counts: outcomes.filter((r) => !r.settled).reduce<Record<string, number>>((counts, r) => {
      counts[r.reason!] = (counts[r.reason!] ?? 0) + 1;
      return counts;
    }, {}),
    outcomes,
  };
}

export function runFiniteBudget(scenario: FiniteBudgetScenario) {
  const endBlock = validate(scenario);
  const c = scenario.config;
  const offeredTraceHash = hash(scenario.requests);
  const ln = new Recorder("lightning", c, offeredTraceHash);
  const ark = new Recorder("ark", c, offeredTraceHash);
  const units = c.budgetSat / c.quantumSat;
  const frontUnits = c.frontingSat / c.quantumSat;
  const serverChannelSat = c.budgetSat - c.frontingSat;
  const channelCapacity = new Map(c.holders.map((h) => [h, 0]));
  const lnBalance = new Map(c.holders.map((h) => [h, 0]));
  // Allocate every LN reserve lot once; the stable round-robin rule includes any remainder.
  for (let i = 0; i < units; i++) {
    const holder = c.holders[i % c.holders.length]!;
    channelCapacity.set(holder, channelCapacity.get(holder)! + c.quantumSat);
    ln.open(`ln:channel:${i}`, `channel:${holder}:hub-and-holder`);
  }
  for (let i = 0; i < frontUnits; i++) ark.open(`ark:front:${i}`, "operator-fronting-reserve");
  for (let i = frontUnits; i < units; i++) ark.open(`ark:channel:${i}`, "server-channel:operator-and-peer");
  const occupied = new Set<number>();
  const locks = new Map<string, number[]>();
  const onCapital = (e: Readonly<ServerCapitalEvent>): void => {
    if (e.kind === "fronting_locked") {
      const needed = e.amountSat / c.quantumSat;
      const selected: number[] = [];
      for (let i = 0; i < frontUnits && selected.length < needed; i++) if (!occupied.has(i)) selected.push(i);
      if (!Number.isInteger(needed) || selected.length !== needed || locks.has(e.objectId)) throw new Error("fronting lot conservation failed");
      locks.set(e.objectId, selected);
      for (const i of selected) {
        occupied.add(i);
        ark.emit("lot_state", e.height, { lot_id: `ark:front:${i}`, state: "unavailable",
          cause: "simulation_forfeit_fronted", object_id: e.objectId, recovery_height: e.recoveryHeight });
      }
    } else {
      const selected = locks.get(e.objectId);
      if (!selected || selected.length * c.quantumSat !== e.amountSat) throw new Error("recovery has no matching reserve lock");
      for (const i of selected) {
        if (!occupied.delete(i)) throw new Error("reserve was recovered twice");
        ark.emit("lot_state", e.height, { lot_id: `ark:front:${i}`, state: "available",
          cause: "simulation_release", release_receipt: `simulation:sweep:${e.objectId}:${e.height}` });
      }
      locks.delete(e.objectId);
    }
  };
  const server = new ArkServer(c.frontingSat, { lifetimeBlocks: c.lifetimeBlocks, roundInterval: c.roundInterval,
    refreshLead: Number.NEGATIVE_INFINITY, spendLock: c.spendLock }, onCapital);
  let serverLocalBalance = 0;
  const outcomes = { lightning: [] as PaymentOutcome[], ark: [] as PaymentOutcome[] };
  const requestsAt = new Map<number, OfferedPayment[]>();
  const proofsAt = new Map<number, ProofMarker[]>();
  for (const r of scenario.requests) requestsAt.set(r.atBlock, [...requestsAt.get(r.atBlock) ?? [], r]);
  for (const p of scenario.proofMarkers ?? []) proofsAt.set(p.atBlock, [...proofsAt.get(p.atBlock) ?? [], p]);
  const heights = [...new Set([...requestsAt.keys(), ...proofsAt.keys()])].sort((a, b) => a - b);
  for (const h of heights) {
    if (h > server.height) server.advance(h - server.height);
    for (const marker of proofsAt.get(h) ?? []) {
      ark.emit("proof_verified", h, { proof_id: marker.proofId, verification_kind: "simulation_marker_only" });
    }
    for (const r of requestsAt.get(h) ?? []) {
      for (const recorder of [ln, ark]) recorder.emit("payment_offered", h, {
        invoice_id: r.invoiceId, amount_sat: r.amountSat, purpose: "application", holder: r.holder, direction: r.direction,
      });
      const balance = lnBalance.get(r.holder)!;
      let lnReason: string | undefined;
      if (r.direction === "receive") {
        if (r.amountSat > channelCapacity.get(r.holder)! - balance) lnReason = "channel_inbound_capacity";
        else lnBalance.set(r.holder, balance + r.amountSat);
      } else {
        if (r.amountSat > balance) lnReason = "holder_channel_balance";
        else lnBalance.set(r.holder, balance - r.amountSat);
      }
      ln.payment(r, lnReason);
      outcomes.lightning.push({ ...r, settled: !lnReason, ...(lnReason ? { reason: lnReason } : {}) });
      let arkReason: string | undefined;
      if (r.direction === "receive") {
        if (r.amountSat > serverChannelSat - serverLocalBalance) arkReason = "server_channel_inbound_capacity";
        else {
          server.receive(r.holder, r.amountSat);
          serverLocalBalance += r.amountSat;
        }
      } else {
        const required = server.frontingRequired(r.holder, r.amountSat, { requireUnexpired: true });
        if (required === undefined) arkReason = "unexpired_holder_value";
        else if (r.amountSat > serverLocalBalance) arkReason = "server_channel_outbound_balance";
        else if (required > server.uncommitted) arkReason = "fronting_capacity";
        else {
          if (!server.spendLightning(r.holder, r.amountSat, { requireUnexpired: true })) throw new Error("admitted spend failed");
          serverLocalBalance -= r.amountSat;
        }
      }
      ark.payment(r, arkReason);
      outcomes.ark.push({ ...r, settled: !arkReason, ...(arkReason ? { reason: arkReason } : {}) });
      if (server.committed !== occupied.size * c.quantumSat || !server.aggregateBoundHolds()) throw new Error("budget conservation failed");
    }
  }
  if (endBlock > server.height) server.advance(endBlock - server.height);
  if (server.committed !== 0 || locks.size || occupied.size) throw new Error("full recovery drain did not complete");
  ln.emit("run_end", endBlock);
  ark.emit("run_end", endBlock);
  return {
    summary: {
      schema_version: "capital-bound-finite-budget/v1", evidence_level: "simulation", evidence_verified: false,
      configuration_sha256: hash(c), offered_trace_sha256: offeredTraceHash,
      config: c, end_block: endBlock, drain_blocks: c.lifetimeBlocks,
      funding_policy: { total_per_arm_sat: c.budgetSat, ln_channel_capacity_sat: Object.fromEntries(channelCapacity),
        ark_channel_capacity_sat: serverChannelSat, ark_disjoint_fronting_reserve_sat: c.frontingSat },
      assumptions: ["zero fees", "instantaneous accepted application payments", "fixed denomination", "fixed channel capacity",
        "Ark channel and fronting reserves are disjoint", "automatic refresh disabled", "expired VTXOs ineligible for new spends",
        "spendLock is a model parameter", "fixed synthetic seconds per block", "remaining channel capital stays funded through the drain"],
      limitations: ["no node, transaction, signature, proof, script, mempool, reorg, or finality verification",
        "no route search, HTLC in-flight duration, queue, retry, rebalancing, or dynamic funding",
        "the drain covers fronting locks; remaining holder liabilities and channel exits are not modeled",
        "the disjoint Ark reserve policy requires validation against an actual implementation balance sheet"],
      lightning: summarize(outcomes.lightning), ark: summarize(outcomes.ark),
      terminal_ark_fronting_locked_sat: server.committed,
      terminal_ark_server_channel_local_sat: serverLocalBalance,
      terminal_ark_holder_claims_sat: c.holders.reduce((sum, holder) => sum + server.holderValue(holder), 0),
    },
    events: { lightning: ln.events, ark: ark.events },
  };
}

export const DEFAULT_SCENARIO: FiniteBudgetScenario = {
  config: { runId: "finite-budget-demo", holders: ["a", "b"], budgetSat: 1600, frontingSat: 800, quantumSat: 100,
    lifetimeBlocks: 10, roundInterval: 2, spendLock: "expiry", arrivalHorizonBlocks: 10, secondsPerBlock: 600 },
  requests: [
    { invoiceId: "a-in", atBlock: 0, holder: "a", direction: "receive", amountSat: 500 },
    { invoiceId: "b-in-capacity", atBlock: 0, holder: "b", direction: "receive", amountSat: 400 },
    { invoiceId: "a-out", atBlock: 1, holder: "a", direction: "send", amountSat: 500 },
    { invoiceId: "b-in", atBlock: 2, holder: "b", direction: "receive", amountSat: 400 },
    { invoiceId: "b-out-before-sweep", atBlock: 3, holder: "b", direction: "send", amountSat: 400 },
    { invoiceId: "b-out-after-sweep", atBlock: 10, holder: "b", direction: "send", amountSat: 400 },
  ],
  proofMarkers: [{ proofId: "synthetic-proof-before-sweep", atBlock: 2 }],
};

function main(): void {
  let input: string | undefined;
  let output = "output/capital-bound";
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--out" && args[i + 1]) output = args[++i]!;
    else if (args[i] === "--input" && args[i + 1]) input = args[++i]!;
    else throw new Error("usage: node model/capital-bound.ts [--input scenario.json] [--out directory]");
  }
  const scenario: FiniteBudgetScenario = input ? JSON.parse(readFileSync(input, "utf8")) : DEFAULT_SCENARIO;
  const result = runFiniteBudget(scenario);
  mkdirSync(output, { recursive: true });
  writeFileSync(resolve(output, "scenario.json"), JSON.stringify(scenario, null, 2) + "\n");
  writeFileSync(resolve(output, "summary.json"), JSON.stringify(result.summary, null, 2) + "\n");
  for (const arm of ["lightning", "ark"] as const) {
    writeFileSync(resolve(output, `${arm}.jsonl`), result.events[arm].map((event) => JSON.stringify(event)).join("\n") + "\n");
  }
  console.log(JSON.stringify({ output: resolve(output), ...result.summary }, null, 2));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
