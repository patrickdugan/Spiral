#!/usr/bin/env python3
"""CBM-SHZ-01 commercial analysis: endogenous liquidity prices, pooling economies, services.

1. Min-cost-flow duals on the restricted payout graph of every clearing round: the shadow
   price of one more unit of directional capacity, in sat per BTC-day, against the
   competitive rental rate r/365.
2. Pooling and natural monopoly: per-pool versus global portfolio margin and clearing
   costs; k independent pools, k interoperable pools, one pool; the rent a single clearing
   network could charge before fragmented or interoperable alternatives undercut it.
3. Services: break-even pricing in bps per trade and sat per BTC-day for each service, LP
   annualised return at break-even and at the customer ceiling, break-even daily volume.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cbm import sim  # noqa: E402
from cbm.flow import mincost_duals  # noqa: E402

SAT = 1e8


def build(s, reg):
    rng = np.random.default_rng(s.seed)
    trade_minutes = int(s.horizon_days * 1440)
    slack_blocks = s.to_self_delay_blocks + s.challenge_blocks + 2 * s.confirmations
    minutes = trade_minutes + int(s.maturity_h * 60) + int(max(s.settle_period_h, s.proof_batch_h) * 60 + s.proof_latency_h * 60) \
        + slack_blocks * sim.SEC_PER_BLOCK // 60 + 60
    px, d = sim.price_path(s, reg, rng, minutes, None)
    tr = sim.trades(s, d, rng, trade_minutes)
    c = sim.contracts(s, tr, px, rng)
    c["P_path"] = px
    return c, minutes


def duals(s, reg):
    """Shadow prices of directional payout capacity under scarcity."""
    c, _ = build(s, reg)
    rounds = []
    sim.clearing_rounds(s, c, restricted=True, collect=rounds)
    period_days = s.settle_period_h / 24
    rent_sat_per_btc_day = s.lp_rate / 365 * SAT
    # Two substitutes for missing capacity, priced per BTC of deficit:
    #   lp      an LP advances the shortfall for one period at its own rate;
    #   no_lp   the creditor waits for the unilateral fallback path (to_self_delay plus
    #           confirmations) and bears its own funding cost over that wait.
    wait_days = (s.to_self_delay_blocks + s.confirmations) * sim.SEC_PER_BLOCK / sim.DAY + period_days
    substitutes = {"lp": s.lp_rate * period_days / 365, "no_lp": s.funding_rate * wait_days / 365}
    out_rows = {}
    for name, deficit_cost in substitutes.items():
        binding, prices, deficits = 0, [], []
        for vb, present, dem in rounds:
            if dem.sum() <= 0:
                continue
            U = present.astype(float) * 1e9
            out = mincost_duals(vb, U, dem, cost_edge=0.0, deficit_cost=deficit_cost)
            vp = out["vault_price"]
            deficits.append(out["deficit"])
            if (vp > 1e-15).any():
                binding += 1
                prices.extend((vp[vp > 1e-15] / period_days * SAT).tolist())
        out_rows[name] = dict(rounds_with_binding_vault=binding,
                              vault_shadow_price_sat_per_btc_day=dict(mean=float(np.mean(prices)) if prices else 0.0,
                                                                      max=float(np.max(prices)) if prices else 0.0),
                              total_deficit_btc=float(np.sum(deficits)))
    return dict(scenario=dict(vault_edge_density=s.vault_edge_density, vault_budget_frac=s.vault_budget_frac, lp_rate=s.lp_rate),
                rounds=len(rounds), competitive_rental_sat_per_btc_day=rent_sat_per_btc_day, by_substitute=out_rows)


def pooling(s, reg):
    """Per-router versus global portfolio margin (capital pooling across routers)."""
    c, minutes = build(s, reg)
    per_router, imp_r = sim.portfolio_margin(s, c, by_router=True, minutes=minutes, series=True)
    glob, imp_g = sim.portfolio_margin(s, c, by_router=False, minutes=minutes, series=True)
    per_contract = float((2 * c["m"] * (c["t1"] - c["t0"]) / sim.DAY).sum())
    return dict(per_contract_margin_btc_days=per_contract, pm_per_router_btc_days=float(per_router.sum() / 1440),
                pm_global_btc_days=float(glob.sum() / 1440), impaired_per_router_btc=imp_r, impaired_global_btc=imp_g,
                V_btc=c["V_btc"])


def fragmentation(s, reg):
    """k clearing pools computed from the simulated obligations.

    Routers are partitioned into k pools; a contract belongs to its router's pool. Per round:
      monopoly     one pool nets every party's obligations;
      independent  each pool nets separately, so a party active in several pools pays and
                   receives gross across them;
      interop      parties net across pools; pools settle their pool-level balances with
                   one transfer per creditor pool per round.
    Provider cost per pool: one Nova/SP1 proof per batch, the clearing transaction bytes,
    and a BitVM3 bond of bond_ratio x that pool's own peak LP advance (peaks do not add:
    the sum of pool peaks exceeds the pooled peak). Costs in bps of matched volume.
    """
    c, minutes = build(s, reg)
    V = c["V_btc"]
    period = int(s.settle_period_h * 3600)
    batch = int(max(s.proof_batch_h, s.settle_period_h) * 3600)
    lp_rel = (sim.round_up(c["t1"], batch) + int(s.proof_latency_h * 3600)
              + (s.challenge_blocks + s.confirmations) * sim.SEC_PER_BLOCK)
    rb = c["t1"] // period
    on = ~c["offline"]
    n_batches = int(math.ceil(s.horizon_days * 24 / max(s.proof_batch_h, s.settle_period_h)))
    proof_btc_per_batch = s.guest_a_gpu_h * s.gpu_usd_per_h / s.btc_usd
    rows = []
    for k in (1, 2, 4, 8):
        if k > s.n_routers:
            break
        pool = c["router"] % k

        def nets(keys):
            allk = np.concatenate([np.stack([rb[on], keys[0][on], c["creditor"][on]], 1),
                                   np.stack([rb[on], keys[1][on], c["debtor"][on]], 1)])
            amt = np.concatenate([c["owed"][on], -c["owed"][on]])
            u, inv = np.unique(allk, axis=0, return_inverse=True)
            net = np.bincount(inv.ravel(), weights=amt)
            return u, net

        u, net = nets((pool, pool))                     # per (round, pool, party)
        flow_indep = float(net[net > 0].sum())
        n_out = int((net > 1e-15).sum()); n_in = int((net < -1e-15).sum())
        zero = np.zeros_like(pool)
        u1, net1 = nets((zero, zero))                   # per (round, party): cross-pool netting
        flow_interop = float(net1[net1 > 0].sum())
        n_out_i = int((net1 > 1e-15).sum()); n_in_i = int((net1 < -1e-15).sum())
        rounds = len(np.unique(rb[on]))
        vb_indep = 11 * rounds * k + 57.5 * n_in + 43 * n_out
        vb_interop = 11 * rounds * k + 57.5 * n_in_i + 43 * n_out_i + rounds * max(k - 1, 0) * 154
        # Bonds: per-pool peak of LP advances in flight.
        bond_peak = 0.0
        for p in range(k):
            sel = pool == p
            diff = np.zeros(minutes + 1)
            np.add.at(diff, np.clip(c["t1"][sel] // 60, 0, minutes), 2 * c["m"][sel])
            np.add.at(diff, np.clip(lp_rel[sel] // 60, 0, minutes), -2 * c["m"][sel])
            bond_peak += float(np.cumsum(diff).max())
        bond_cost = s.lp_rate * s.bond_ratio * bond_peak * (minutes / 1440) / 365
        proof = k * n_batches * proof_btc_per_batch
        fee = s.feerate / SAT
        cost_indep = proof + vb_indep * fee + bond_cost
        cost_interop = proof + vb_interop * fee + bond_cost
        rows.append(dict(pools=k, net_flow_independent_btc=flow_indep, net_flow_interop_btc=flow_interop,
                         sum_of_pool_bond_peaks_btc=bond_peak, proof_btc=proof,
                         chain_vb_independent=vb_indep, chain_vb_interop=vb_interop,
                         cost_independent_bps=1e4 * cost_indep / V, cost_interoperable_bps=1e4 * cost_interop / V))
    mono = rows[0]["cost_independent_bps"]
    for r in rows:
        r["rent_cap_vs_independent_bps"] = r["cost_independent_bps"] - mono
        r["rent_cap_vs_interoperable_bps"] = r["cost_interoperable_bps"] - mono
    return rows

def services(s, out):
    """Break-even prices of each service under competitive entry (price = cost incl. r)."""
    V = out["matched_btc"]
    A, B, C, D, E = (out["arch"][k] for k in "ABCDE")
    rent_rate = s.lp_rate / 365 * SAT  # sat per BTC-day at the competitive return
    res = {}
    rd = B["capital_btc_days_by_owner"].get("router_operators", 0.0)
    res["directional_liquidity_leasing"] = dict(
        capital_btc_days=rd, price_sat_per_btc_day=rent_rate,
        bps_per_trade=1e4 * s.lp_rate * rd / 365 / V)
    lp = D["capital_btc_days_by_owner"].get("lp", 0.0)
    bond = D["capital_btc_days_by_owner"].get("operator", 0.0)
    lp_cost = s.lp_rate * (lp + bond) / 365
    res["short_duration_settlement_credit"] = dict(
        lp_btc_days=lp, bond_btc_days=bond, breakeven_bps=1e4 * lp_cost / V,
        customer_capital_btc_days_freed=C["capital_btc_days_by_owner"].get("traders", 0) - D["capital_btc_days_by_owner"].get("traders", 0),
        customer_value_bps_at_trader_rate=1e4 * s.funding_rate * (C["capital_btc_days_by_owner"].get("traders", 0) - D["capital_btc_days_by_owner"].get("traders", 0)) / 365 / V,
        lp_annual_return_at_customer_value=(s.funding_rate * (C["capital_btc_days_by_owner"].get("traders", 0) - D["capital_btc_days_by_owner"].get("traders", 0))
                                            / max(lp + bond, 1e-12)))
    res["capital_efficient_clearing"] = dict(fee_ceiling_bps=C["fee_ceiling_bps_vs_A"], provider_cost_bps=C["provider_cost_bps"],
                                             surplus_bps=C["surplus_bps_vs_A"], feasible=C["fee_feasible_vs_A"])
    res["proof_generation"] = dict(cost_btc=D.get("proof_cost_btc", 0.0), bps=1e4 * D.get("proof_cost_btc", 0.0) / V,
                                   batches=D.get("proof_batches"), usd_per_batch=s.guest_a_gpu_h * s.gpu_usd_per_h)
    # Break-even daily volume for fixed federation/oracle costs (SHZ-LV base: $850/day).
    fed_usd = 850.0
    for name, bps in (("at_clearing_surplus", C["surplus_bps_vs_A"]), ("at_1bp", 1.0), ("at_0.1bp", 0.1)):
        res.setdefault("oracle_attestation_breakeven_daily_volume_usd", {})[name] = (fed_usd / (bps / 1e4)) if bps > 0 else None
    res["cross_router_execution"] = dict(note="contestable: sustainable markup <= switching cost (Lean sustainable_markup); "
                                              "SHZ-LV measured ex-post latency value 0.004-0.04 bp per decision")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sweeps", type=Path, default=HERE / "results" / "sweeps.json")
    ap.add_argument("--regimes", type=Path, default=HERE / "data" / "lighter_regimes.json")
    ap.add_argument("--output", type=Path, default=HERE / "results" / "commercial.json")
    a = ap.parse_args()
    reg = sim.load_regimes(a.regimes)
    sw = json.loads(a.sweeps.read_text())
    base = sim.Scenario(**{k: v for k, v in sw["base"].items()})
    base_out = sw["cells"]["base"][0]
    res = dict(schema="cbm-shz-01/commercial/v1")
    res["duals"] = [duals(replace(base, vault_edge_density=de, vault_budget_frac=bf, horizon_days=2.0), reg)
                    for de, bf in ((1.0, 1.0), (0.5, 1.0), (0.5, 0.9), (0.25, 0.7))]
    res["pooling"] = {f"routers={r}": pooling(replace(base, n_routers=r, horizon_days=2.0), reg) for r in (1, 4, 16)}
    res["fragmentation"] = fragmentation(replace(base, n_routers=8, horizon_days=2.0), reg)
    res["services"] = services(base, base_out)
    a.output.write_text(json.dumps(res, indent=1, default=float) + "\n")
    print(json.dumps({k: res[k] for k in ("duals", "pooling", "fragmentation")}, indent=1, default=float)[:4000])
    print(json.dumps(res["services"], indent=1, default=float))


if __name__ == "__main__":
    main()
