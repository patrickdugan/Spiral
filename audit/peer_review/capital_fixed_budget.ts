// Frozen-pilot comparison. Run from repository root; entirely offline.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { CapitalForecast, type ForecastConfig } from "../../model/capital-forecast.ts";
import { OBSERVED_TRANSACTION_COSTS as costs } from "../../model/capital-fees.ts";
import { rng } from "../../model/server.ts";
export type Cell = "zero" | "drain" | "accumulate" | "steady";
export interface Demand { height: number; holder: number; direction: "in" | "out"; amount: number }
const directory = "audit/peer_review/capital/";
export const protocol = { version: 1, evidence_class: "single_participant_fee_aware_forecast",
  pilot_seeds: [201, 202, 203, 204, 205, 206, 207, 208], holdout_seeds: Array.from({ length: 24 }, (_, i) => 301 + i),
  cells: ["zero", "drain", "accumulate", "steady"] as Cell[], initial_gross_balance_sat: [0, 250000],
  delays: [6, 144], lifetime: 4320, horizon: 34560, round: 6, refresh_lead: 288, margin: .25,
  minimum_value_delivery_target: .99, pilot_sizing_rule: "1.25 times maximum pilot cash draw, fronting, and directional requirement; no holdout resizing",
  initial_balance_rule: "Each holder starts with the same gross principal in each mechanism; Ark board service fees reduce its claims.",
  receipt_policy: "One fresh single-participant round per accepted receipt; net claim plus 330-sat root overhead, 3857-sat miner fee.",
  refresh_policy: "Each claim refreshes separately at expiry minus 288 or after 99 retained-change hops; failed maintenance retries every six blocks before expiry.",
  sweep_policy: "One transaction per inactive root at expiry plus delay, 1295-sat fee; live claims or net output below 330 prevent recovery.",
  dust_policy: "Fresh round outputs require 330 sats. Retained Arkoor change may be subdust. Receipt dust rejection belongs to this fresh-round policy, not a universal inbound protocol restriction.",
  routing_policy: "Instantaneous direct settled payments, zero route fee; outbound admissibility reserves 90% of holder fee. No rebalance.",
  channel_policy: "One channel per holder or group; group shares directional capacity but cannot spend another holder's balance. No channel rotation or rebalance.",
  channel_open_miner_sat: costs.channelOpenMiner, cpu_cap_seconds: 7200,
  limitations: ["Receipt backing policy has not been observed live; it is a declared fresh-root scenario.",
    "Observed single-participant transaction fees are held constant; pooled tree batching is not estimated.",
    "Six blocks is the recorded detection gap, not an operational distribution; 144 is stress.",
    "Successful settlement is instantaneous. HTLC duration and sat-seconds are unavailable, not measured zero.",
    "Full channel funding includes both parties; operator-only conservation is checked separately.",
    "Fee spend is reported separately from capital-time. Lower remaining assets after miner fees do not establish funding efficiency.",
    "Ratios are comparable only when both mechanisms meet the declared delivery target."] };
export function demand(cell: Cell, seed: number): Demand[] {
  const r = rng(seed), agents = cell === "steady" ? 3 : 200, drift = cell === "drain" ? -30 : cell === "accumulate" ? 60 : 0;
  const pOut = (.02 * 5000 - drift) / 4000, result: Demand[] = [];
  for (let height = 0; height < protocol.horizon; height += protocol.round) for (let holder = 0; holder < agents; holder++) {
    let incoming = 0, outgoing = 0;
    if (cell === "steady") { outgoing = 100 + Math.floor(r() * 10); incoming = 100 + Math.floor(r() * 10); }
    else { if (r() < .02) incoming = 5000; if (r() < pOut) outgoing = 4000; }
    if (incoming) result.push({ height, holder, direction: "in", amount: incoming });
    if (outgoing) result.push({ height, holder, direction: "out", amount: outgoing });
  }
  return result;
}
const hash = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const sourceHashes = () => Object.fromEntries(["model/capital-fees.ts", "model/capital-forecast.ts", "model/server.ts",
  "audit/peer_review/capital_fixed_budget.ts"].map(path => [path,
    createHash("sha256").update(readFileSync(path, "utf8").replaceAll("\r\n", "\n")).digest("hex")]));
export function runArk(events: Demand[], agents: number, initial: number, config: ForecastConfig) {
  const m = new CapitalForecast(config);
  if (initial) for (let a = 0; a < agents; a++) assert.ok(m.board(a, initial).ok);
  const initialHash = m.economicHash();
  for (const e of events) { m.advance(e.height); m.offer(e.holder, e.direction, e.amount); }
  m.advance(protocol.horizon); const report = m.report();
  const funded = config.wallet + config.local + config.remote + agents * initial;
  const integrals = { ...report.integrals_sat_blocks, initialFunding: (BigInt(funded) * BigInt(protocol.horizon)).toString() };
  const normalized = (denominator: number) => Object.fromEntries(Object.entries(integrals).map(([k, v]) => [k, denominator ? Number(v) / denominator : null]));
  return { ...report, initial_state_hash: initialHash, initial_funded_resource_sat: funded,
    // Funding budget is not reduced by fee expenditure or favorable rejection.
    initial_funding_sat_blocks: (BigInt(funded) * BigInt(protocol.horizon)).toString(),
    per_offered_blocks: normalized(report.offered_sat), per_delivered_blocks: normalized(report.delivered_sat),
    opening_miner_fees_sat: costs.channelOpenMiner,
    target_met: report.delivery_rate !== null && report.delivery_rate >= protocol.minimum_value_delivery_target };
}
interface ChannelBudget { local: number[]; remote: number[] }
export function runChannels(events: Demand[], agents: number, initial: number, group: number, budget?: ChannelBudget) {
  const count = Math.ceil(agents / group), balance = Array(agents).fill(initial) as number[];
  const local = Array.from({ length: count }, (_, i) => budget?.local[i] ?? Math.min(group, agents - i * group) * initial + costs.outboundBuffer);
  const remote = Array.from({ length: count }, (_, i) => budget?.remote[i] ?? 1e12);
  const startLocal = [...local], startRemote = [...remote], minimumRemote = [...remote];
  const failures = { holder: 0, outbound: 0, inbound: 0 };
  const initialHash = hash({ local, remote, balance }); let offered = 0, delivered = 0, deliveredEvents = 0;
  const directional = { in_offered: 0, in_delivered: 0, out_offered: 0, out_delivered: 0 };
  for (const e of events) {
    offered += e.amount; const g = Math.floor(e.holder / group);
    directional[`${e.direction}_offered`] += e.amount;
    if (e.direction === "in") {
      if (remote[g] - costs.inboundBuffer < e.amount) { failures.inbound++; continue; }
      remote[g] -= e.amount; local[g] += e.amount; balance[e.holder] += e.amount;
    } else {
      if (balance[e.holder] < e.amount) { failures.holder++; continue; }
      if (local[g] - costs.outboundBuffer < e.amount) { failures.outbound++; continue; }
      local[g] -= e.amount; remote[g] += e.amount; balance[e.holder] -= e.amount;
    }
    minimumRemote[g] = Math.min(minimumRemote[g], remote[g]); delivered += e.amount; deliveredEvents++;
    directional[`${e.direction}_delivered`] += e.amount;
    assert.equal(local[g] + remote[g], startLocal[g] + startRemote[g]);
  }
  const funded = startLocal.reduce((s, x) => s + x, 0) + startRemote.reduce((s, x) => s + x, 0);
  assert.equal(balance.reduce((s, x) => s + x, 0), local.reduce((s, x) => s + x, 0) - count * costs.outboundBuffer);
  return { group_size: group, offered_sat: offered, delivered_sat: delivered, offered_events: events.length, delivered_events: deliveredEvents,
    delivery_rate: delivered / offered, target_met: delivered / offered >= protocol.minimum_value_delivery_target, failures,
    directional_value_sat: directional,
    initial_state_hash: initialHash, terminal_state_hash: hash({ local, remote, balance }),
    initial_funded_resource_sat: funded, initial_funding_sat_blocks: (BigInt(funded) * BigInt(protocol.horizon)).toString(),
    per_offered_blocks: funded * protocol.horizon / offered, per_delivered_blocks: delivered ? funded * protocol.horizon / delivered : null,
    opening_miner_fees_sat: count * costs.channelOpenMiner, routing_fees_sat: 0, rebalance_fees_sat: 0,
    required_initial_local_sat: startLocal,
    required_initial_remote_sat: startRemote.map((v, i) => v - minimumRemote[i] + costs.inboundBuffer),
    terminal: { local, remote, holder_balance_sat: balance.reduce((s, x) => s + x, 0) } };
}
interface BudgetRow { cell: Cell; initial: number; ark: { delay: number; config: ForecastConfig }[]; channels: { group: number; budget: ChannelBudget }[] }
const pilotConfig = (delay: number): ForecastConfig => ({ wallet: 1e12, local: 1e12, remote: 1e12, fronting: 1e12,
  lifetime: protocol.lifetime, refreshLead: protocol.refresh_lead, recoveryDelay: delay });
const pad = (n: number) => Math.ceil(n * (1 + protocol.margin));
function pilot(cell: Cell) {
  const agents = cell === "steady" ? 3 : 200, groups = cell === "steady" ? [1, 3] : [1, 5, 20, 200];
  const rows: BudgetRow[] = [], diagnostics: unknown[] = [];
  for (const initial of protocol.initial_gross_balance_sat) {
    const ark = protocol.delays.map(delay => ({ delay, config: { ...pilotConfig(delay), wallet: 0, local: 0, remote: 0, fronting: 0 } }));
    const channels = groups.map(group => ({ group, budget: { local: Array(Math.ceil(agents / group)).fill(0), remote: Array(Math.ceil(agents / group)).fill(0) } as ChannelBudget }));
    for (const seed of protocol.pilot_seeds) {
      const events = demand(cell, seed), sample: any = { seed, initial, demand_sha256: hash(events), ark: [], channels: [] };
      for (const entry of ark) {
        const r = runArk(events, agents, initial, pilotConfig(entry.delay));
        entry.config.wallet = Math.max(entry.config.wallet, pad(r.peak_cash_draw_sat));
        entry.config.local = Math.max(entry.config.local, pad(r.required_initial_local_sat));
        entry.config.remote = Math.max(entry.config.remote, pad(r.required_initial_remote_sat));
        entry.config.fronting = Math.max(entry.config.fronting, pad(r.peak_fronting_sat));
        assert.equal(r.failures.wallet ?? 0, 0); assert.equal(r.failures.inbound ?? 0, 0); assert.equal(r.failures.outbound ?? 0, 0);
        sample.ark.push({ delay: entry.delay, delivery_rate: r.delivery_rate, failures: r.failures, peak_cash_draw_sat: r.peak_cash_draw_sat,
          peak_fronting_sat: r.peak_fronting_sat, local_required: r.required_initial_local_sat, remote_required: r.required_initial_remote_sat });
      }
      for (const entry of channels) {
        const r = runChannels(events, agents, initial, entry.group);
        entry.budget.local = r.required_initial_local_sat;
        entry.budget.remote = entry.budget.remote.map((v, i) => Math.max(v, pad(r.required_initial_remote_sat[i])));
        sample.channels.push({ group: entry.group, delivery_rate: r.delivery_rate });
      }
      diagnostics.push(sample); console.log(JSON.stringify({ phase: "pilot", cell, initial, seed }));
      guard();
    }
    rows.push({ cell, initial, ark, channels });
  }
  writeFileSync(`${directory}fixed-budget-pilot-${cell}.json`, JSON.stringify({ protocol, protocol_sha256: hash(protocol), source_sha256: sourceHashes(), rows, diagnostics }, null, 2) + "\n");
}
function evaluate(cell: Cell) {
  const bytes = readFileSync(`${directory}fixed-budget-pilot-${cell}.json`), frozen = JSON.parse(bytes.toString());
  assert.equal(frozen.protocol_sha256, hash(protocol), "pilot protocol drift");
  assert.deepEqual(frozen.source_sha256, sourceHashes(), "forecast code changed after pilot freeze");
  const rows: unknown[] = [], agents = cell === "steady" ? 3 : 200;
  for (const budget of frozen.rows as BudgetRow[]) for (const seed of protocol.holdout_seeds) {
    assert.ok(!protocol.pilot_seeds.includes(seed)); const events = demand(cell, seed);
    const ark = budget.ark.map(b => ({ delay: b.delay, result: runArk(events, agents, budget.initial, b.config) }));
    const channels = budget.channels.map(b => runChannels(events, agents, budget.initial, b.group, b.budget));
    const compare = ark.flatMap(a => channels.map(c => ({ delay: a.delay, group: c.group_size,
      both_meet_target: a.result.target_met && c.target_met,
      ark_over_channel_funded_resource: a.result.target_met && c.target_met ? a.result.initial_funded_resource_sat / c.initial_funded_resource_sat : null,
      ark_delivery_rate: a.result.delivery_rate, channel_delivery_rate: c.delivery_rate })));
    rows.push({ seed, initial_gross_holder_sat: budget.initial, demand_sha256: hash(events), ark, channels, compare });
    console.log(JSON.stringify({ phase: "holdout", cell, initial: budget.initial, seed })); guard();
  }
  writeFileSync(`${directory}fixed-budget-result-${cell}.json`, JSON.stringify({ protocol, pilot_file_sha256: createHash("sha256").update(bytes).digest("hex"), rows }, null, 2) + "\n");
}
const started = performance.now();
function guard() { assert.ok(performance.now() - started < protocol.cpu_cap_seconds * 500, "one-hour phase cap; pilot plus holdout limited to two hours"); }
// Keep imports side-effect free for the regression suite.
if (process.argv[1]?.replaceAll("\\", "/").endsWith("/capital_fixed_budget.ts")) {
  const phase = process.argv[2], selected = process.argv[3];
  const cells = selected === "all" ? protocol.cells : [selected as Cell];
  assert.ok(cells.every(c => protocol.cells.includes(c)));
  for (const cell of cells) {
    if (phase === "pilot") pilot(cell); else if (phase === "holdout") evaluate(cell); else throw new Error("select pilot|holdout and cell|all");
  }
}
