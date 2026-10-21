import { test } from "node:test";
import assert from "node:assert/strict";
import { CapitalForecast, type ForecastConfig } from "./capital-forecast.ts";
const config: ForecastConfig = { wallet: 1000000, local: 500000, remote: 500000, fronting: 10000000,
  lifetime: 4320, refreshLead: 288, recoveryDelay: 6, minBoard: 0 };

test("forecast calibrates observed retained change and early refresh costs without freeing original backing", () => {
  const m = new CapitalForecast(config); m.advance(113); assert.ok(m.board(0, 100000).ok);
  m.advance(116); assert.ok(m.send(0, 60000).ok);
  assert.equal(m.balance(0), 39115); assert.equal(m.rootStock, 100000); assert.equal(m.W, 60000);
  m.advance(1000); assert.deepEqual(m.refreshHolder(0), [{ ok: true }]);
  assert.equal(m.balance(0), 38652); assert.equal(m.rootStock, 138982); assert.equal(m.W, 98982);
  assert.equal(m.cash, 957161); assert.equal(m.minerFees, 3857);
  m.advance(4438); assert.equal(m.C, 0);
  m.advance(4439); assert.equal(m.C, 98705); assert.equal(m.W, 277);
  assert.equal(m.report().terminal.exhausted_recovery_shortfall_sat, 277);
  assert.equal(m.rootStock, 38982); assert.equal(m.cash, 1055866);
});

test("forecast rejects unaffordable requests atomically, including multi-input fees and routing allowance", () => {
  for (const overrides of [{ wallet: 1 }, { remote: 5000 }]) {
    const m = new CapitalForecast({ ...config, ...overrides }), before = m.economicHash();
    assert.equal(m.receive(0, 5000).ok, false); assert.equal(m.economicHash(), before);
  }
  for (const overrides of [{ local: 69804 }, { fronting: 59999 }]) {
    const m = new CapitalForecast({ ...config, ...overrides }); m.board(0, 100000);
    const before = m.economicHash(); assert.equal(m.send(0, 60000).ok, false); assert.equal(m.economicHash(), before);
  }
  const m = new CapitalForecast(config); m.board(0, 1000); const before = m.economicHash();
  assert.equal(m.send(0, 600).ok, false); assert.equal(m.economicHash(), before);
});

test("forecast coarse and fine integration agree across recovery and recursive refresh events", () => {
  const run = (fine: boolean) => {
    const m = new CapitalForecast(config); m.board(0, 100000); m.send(0, 60000);
    if (fine) for (let h = 1; h <= 9000; h++) m.advance(h); else m.advance(9000);
    return m.report();
  };
  assert.deepEqual(run(false), run(true));
});

test("failed refresh preserves expired holder obligation and prevents recovery", () => {
  const m = new CapitalForecast({ ...config, wallet: 0 }); m.board(0, 100000); m.send(0, 60000);
  m.advance(5000); const r = m.report();
  assert.equal(r.terminal.C_sat, 0); assert.equal(r.terminal.onchain_roots_sat, 100000);
  assert.equal(r.terminal.expired_holder_sat, 39115); assert.equal(r.terminal.W_sat, 60000);
  const before = m.economicHash(); assert.deepEqual(m.send(0, 1000), { ok: false, reason: "expired" });
  assert.equal(m.economicHash(), before);
});

test("confirmed receipts conserve ownership and channel funding while service fees stay inside operator boundary", () => {
  const m = new CapitalForecast(config); m.receive(0, 5000);
  assert.equal(m.local, 505000); assert.equal(m.remote, 495000); assert.equal(m.balance(0), 4890);
  assert.equal(m.rootStock, 5220); assert.equal(m.cash, 990923); assert.equal(m.W, 0);
  m.advance(10); const r = m.report();
  assert.equal(r.holder_service_fees_sat, 110); assert.equal(r.miner_fees_sat, 3857);
  assert.equal(r.integrals_sat_blocks.uniqueCommitted, "10052200");
  assert.equal(r.integrals_sat_blocks.idle, "9909230");
});

test("small receipts remain failed service even under unlimited capital", () => {
  const m = new CapitalForecast(config); const before = m.economicHash();
  assert.deepEqual(m.offer(0, "in", 100), { ok: false, reason: "dust_or_fee" });
  assert.equal(m.economicHash(), before); assert.equal(m.report().delivered_sat, 0);
  assert.equal(m.report().failures.dust_or_fee, 1);
});

test("subdust retained change remains a claim and uneconomic standalone sweeps remain unrecovered", () => {
  const m = new CapitalForecast(config); m.board(0, 1000);
  assert.ok(m.send(0, 500).ok); assert.equal(m.balance(0), 91);
  m.advance(5000); assert.equal(m.C, 0); assert.equal(m.rootStock, 1000);
  assert.equal(m.report().terminal.expired_holder_sat, 91);
  const n = new CapitalForecast(config); n.board(0, 1000);
  assert.ok(n.send(0, 590).ok); assert.equal(n.balance(0), 0);
  n.advance(5000); assert.equal(n.C, 0); assert.equal(n.rootStock, 1000);
  assert.equal(n.report().terminal.uneconomic_single_root_sweep_sat, 1000);
});

test("deterministic randomized forecast reconciles every accepted transition and terminal obligations", () => {
  for (let seed = 1; seed <= 12; seed++) {
    const run = () => {
      const m = new CapitalForecast(config); let s = seed;
      const random = () => (s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32;
      for (let i = 0; i < 5; i++) m.board(i, 20000);
      for (let i = 0; i < 300; i++) {
        m.advance(i * 17); const before = m.economicHash();
        const result = m.offer(Math.floor(random() * 5), random() < .5 ? "in" : "out", 1000 + Math.floor(random() * 4000));
        if (!result.ok) assert.equal(m.economicHash(), before);
        m.audit();
      }
      return m.report();
    };
    assert.deepEqual(run(), run());
  }
});

test("forecast refreshes deep change before its configured exit-depth limit", () => {
  const m = new CapitalForecast({ ...config, exitDepthLimit: 3 }); m.board(0, 100000);
  assert.ok(m.send(0, 1000).ok); m.advance(1); assert.equal(m.minerFees, 0);
  assert.ok(m.send(0, 1000).ok); m.advance(1); assert.equal(m.minerFees, 3857);
  assert.ok(m.W > 2000); assert.equal(m.C, 0); m.audit();
});
