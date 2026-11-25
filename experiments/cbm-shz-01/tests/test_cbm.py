"""CBM-SHZ-01 invariants on small synthetic traces (no archive data, no network)."""
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from cbm import sim  # noqa: E402
from cbm.flow import bipartite_maxflow, cut_condition, mincost_duals  # noqa: E402

REG = sim.load_regimes(HERE / "data" / "lighter_regimes.json")
SMALL = sim.Scenario(horizon_days=0.5, daily_volume_usd=2e6, n_traders=40, n_makers=4, n_routers=2, maturity_h=4.0)


@pytest.fixture(scope="module")
def out():
    return sim.run(SMALL, REG)


def test_frictionless_capital_is_margin_times_duration(out):
    E = out["arch"]["E"]
    rng = np.random.default_rng(SMALL.seed)
    # E locks exactly both margins from open to maturity: BTC-days = sum 2 m T / day, up to grid rounding.
    expected = out["matched_btc"] / SMALL.leverage * 2 * SMALL.maturity_h / 24
    assert E["btc_days"] == pytest.approx(expected, rel=0.03)
    assert E["chain_vb"] == 0 and E["provider_cost_btc"] == 0


def test_net_flow_never_exceeds_gross(out):
    for name, a in out["arch"].items():
        assert a["net_settlement_btc"] <= a["gross_settlement_btc"] + 1e-12, name
    assert out["arch"]["A"]["net_settlement_btc"] == pytest.approx(out["arch"]["A"]["gross_settlement_btc"])


def test_maturity_netting_does_not_reduce_margin_capital(out):
    # C and E net settlement flows but lock the same per-contract margin before maturity:
    # their margin BTC-days differ only by release delays, never below E.
    c_margin = out["arch"]["C"]["by_owner"]["traders"]["margin"]["btc_days"]
    e_margin = out["arch"]["E"]["by_owner"]["traders"]["margin"]["btc_days"]
    assert c_margin >= e_margin - 1e-9
    assert out["arch"]["C"]["net_settlement_btc"] < out["arch"]["C"]["gross_settlement_btc"]


def test_channel_provisioning_dominates_exact_locks(out):
    assert out["arch"]["A"]["btc_days"] >= out["arch"]["E"]["btc_days"]
    assert out["arch"]["B"]["btc_days"] >= out["arch"]["E"]["btc_days"]


def test_lp_advance_moves_capital_to_lp(out):
    D, C = out["arch"]["D"], out["arch"]["C"]
    assert D["reuse_delay_h"]["max"] == 0.0                       # customers repaid at maturity
    assert D["capital_btc_days_by_owner"]["lp"] > 0
    assert D["capital_btc_days_by_owner"]["traders"] <= C["capital_btc_days_by_owner"]["traders"] + 1e-9
    assert D["lp_recovery_delay_h"]["p50"] >= SMALL.challenge_blocks * 600 / 3600


def test_fee_ceiling_identity(out):
    A = out["arch"]["A"]
    for name, a in out["arch"].items():
        head = A["customer_cost_btc"] - a["customer_cost_btc"]
        assert a["fee_feasible_vs_A"] == (head >= a["provider_cost_btc"])
        assert a["fee_ceiling_bps_vs_A"] == pytest.approx(1e4 * head / out["matched_btc"])


def test_portfolio_margin_without_default_has_no_impairment():
    o = sim.run(replace(SMALL, default_prob=0.0), REG)
    assert o["arch"]["C_pm"]["impaired_claims_btc"] == 0.0
    assert o["arch"]["C_pm"]["btc_days"] < o["arch"]["C"]["btc_days"]


def test_gapped_portfolio_margin_backs_claims_when_moves_stay_inside_gap(out):
    # GapBuffer.lean: impairment is possible only on a move larger than g before close-out.
    info = out["arch"]["C_pmg"]["pm_info"]
    if info["moves_exceeding_gap"] == 0:
        assert out["arch"]["C_pmg"]["impaired_claims_btc"] == 0.0
    assert out["arch"]["C_pmg"]["btc_days"] < out["arch"]["C_pm"]["btc_days"]


def test_measured_vault_exit_size_is_used():
    rep = json.loads((HERE / "results" / "regtest_release.json").read_text())
    assert rep["passed"] and sim.EXIT_VB["vault"] == rep["unilateral_exit"]["vsize"]
    assert rep["clearing"]["vsize"] == 11 + 57.5 * rep["clearing"]["inputs"] + 43 * rep["clearing"]["outputs"]


def test_maxflow_matches_cut_condition_on_random_instances():
    rng = np.random.default_rng(0)
    for _ in range(60):
        V, J = rng.integers(1, 4), rng.integers(1, 6)
        C = rng.uniform(0, 5, V)
        U = rng.uniform(0, 4, (V, J)) * (rng.random((V, J)) < 0.6)
        d = rng.uniform(0, 3, J)
        x = bipartite_maxflow(C, U, d)
        holds, gap, _ = cut_condition(C, U, d)
        assert holds == bool(np.allclose(x, d, atol=1e-7))
        # Max-flow/min-cut: the undelivered amount equals the worst cut violation.
        assert d.sum() - x.sum() == pytest.approx(gap, abs=1e-6)


def test_duals_zero_when_slack_and_capped_by_substitute():
    C = np.array([10.0]); U = np.array([[5.0, 5.0]]); d = np.array([1.0, 1.0])
    out = mincost_duals(C, U, d, cost_edge=0.0, deficit_cost=0.3)
    assert out["deficit"] == pytest.approx(0) and np.allclose(out["vault_price"], 0)
    C = np.array([1.0])
    out = mincost_duals(C, U, d, cost_edge=0.0, deficit_cost=0.3)
    assert out["deficit"] == pytest.approx(1.0)
    assert out["vault_price"][0] == pytest.approx(0.3)       # scarce capacity priced at the substitute
