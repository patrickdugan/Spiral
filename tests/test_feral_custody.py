import hashlib
import json
from pathlib import Path

import pytest

from spiral_ln import feral_custody_eval
from spiral_ln.feral_custody import (
    REASSEMBLY_STRATEGIES,
    STRATEGIES,
    CustodyPersona,
    FeralCustodyEnv,
    StrategyConfig,
    build_custody_config,
    default_adversary,
    strategy_reassembles,
)

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "feral_custody.json"


def _run(strategy, objective, budget, seed=1, **overrides):
    config = build_custody_config(strategy, seed=seed, **overrides)
    return FeralCustodyEnv(config, default_adversary(objective, budget), seed=seed).run()


# -- per-strategy deterministic outcomes (one known seed each) --------------


def test_threshold_signing_survives_and_is_not_extracted():
    result = _run("threshold_signing", "key_extraction", 30_000)
    assert result.extraction_events == 0
    assert result.uninterrupted_signing_epochs == result.epochs  # full horizon
    assert result.funds_retained > 0


def test_enclave_resists_key_extraction():
    result = _run("enclave", "key_extraction", 30_000)
    assert result.extraction_events == 0


def test_reassembly_strategies_are_extracted_or_fail():
    for strategy in ("ignorant_multisig", "gig_labor", "loyalist"):
        result = _run(strategy, "key_extraction", 60_000)
        assert result.extraction_events >= 1 or result.denial_events >= 1
        assert result.uninterrupted_signing_epochs < result.epochs


def test_obfuscation_holds_underfunded_breaks_when_funded():
    assert _run("obfuscation", "key_extraction", 30_000).extraction_events == 0  # budget < recovery_cost
    assert _run("obfuscation", "key_extraction", 120_000).extraction_events >= 1  # funded recovery


def test_coerced_signing_hits_single_signers_but_not_threshold():
    enclave = _run("enclave", "coerced_signing", 40_000, legal_pressure=0.5)
    assert enclave.coerced_signatures > 0
    assert enclave.extraction_events == 0  # coercion is not extraction
    threshold = _run("threshold_signing", "coerced_signing", 40_000, legal_pressure=0.5)
    assert threshold.coerced_signatures == 0  # no single signer to coerce


# -- regression guards for the review findings ------------------------------


def test_threshold_collusion_extraction_is_reachable():
    # The collusion-extraction branch must fire when enough hosts are compelled;
    # it was previously dead code preempted by the denial gate.
    result = _run("threshold_signing", "key_extraction", 30_000, legal_pressure=0.8)
    assert result.extraction_events >= 1
    assert result.coerced_signatures == 0  # key_extraction never coerces


def test_reassembly_host_participates_in_the_defection_market():
    # The reassembly host must be resolvable in the market, else the
    # "host defected -> reassembly reached" extraction trigger is dead.
    config = build_custody_config("ignorant_multisig", seed=1, legal_pressure=0.85)
    env = FeralCustodyEnv(config, default_adversary("key_extraction", 30_000), seed=1)
    env.run()
    assert "host0" in env.defected


def test_reinforcement_bonus_is_single_not_double():
    # A bribe equal to price against an 0.8-loyalty persona must yield 0.2, not 0.0
    # (the double-counted +0.6 bug drove it to 0.0 and made reinforced personas
    # un-outbiddable).
    persona = CustodyPersona("x", "shard_holder", 10_000, 0.8, 0.0, 0, 0.5, 1.0)
    assert persona.defection_probability(10_000, 0.0, 0.8) == pytest.approx(0.2)
    assert persona.defection_probability(0, 0.0, 0.8) == pytest.approx(0.03)


# -- the reassembly-window mechanic -----------------------------------------


def test_reassembly_window_present_iff_strategy_requires_it():
    assert REASSEMBLY_STRATEGIES == {"ignorant_multisig", "obfuscation", "loyalist", "gig_labor"}
    for strategy in STRATEGIES:
        env = FeralCustodyEnv(build_custody_config(strategy, seed=0), default_adversary(), seed=0)
        windows = env.reassembly_windows()
        if strategy_reassembles(strategy):
            assert windows and all(w.epoch < env.config.epochs for w in windows)
        else:
            assert windows == []  # enclave and threshold signing have no reassembly moment
    assert FeralCustodyEnv(build_custody_config("threshold_signing", seed=0), default_adversary(), seed=0).reassembly_windows() == []


# -- determinism, accounting, sealing, validation ---------------------------


def test_episode_is_deterministic_and_accounted():
    a = _run("ignorant_multisig", "key_extraction", 60_000, seed=2)
    b = _run("ignorant_multisig", "key_extraction", 60_000, seed=2)
    assert a == b
    assert a.accounting_ok


def test_accounting_holds_across_all_strategies_and_objectives():
    for strategy in STRATEGIES:
        for objective in ("key_extraction", "signing_denial", "coerced_signing"):
            assert _run(strategy, objective, 60_000, legal_pressure=0.3).accounting_ok


def test_safety_boundary_and_no_operational_fields():
    from dataclasses import fields

    from spiral_ln.feral_custody import CustodyEvent, CustodyResult

    boundary = CustodyResult.safety_boundary()
    assert boundary["synthetic_only"] is True
    assert boundary["persuasion_or_recruitment_content"] is False
    assert boundary["real_key_material"] is False
    persona_fields = {f.name for f in fields(CustodyPersona)}
    for banned in ("script", "message", "content", "playbook", "exploit"):
        assert banned not in persona_fields
        assert banned not in {f.name for f in fields(CustodyEvent)}


def test_validation_rejects_bad_configs():
    with pytest.raises(ValueError):
        StrategyConfig(strategy="not_a_strategy")
    with pytest.raises(ValueError):
        StrategyConfig(strategy="ignorant_multisig", threshold_k=9, n_shares=5)  # k > n
    with pytest.raises(ValueError):
        CustodyPersona("p", "shard_holder", price_to_defect=0, loyalty=0.5, loyalty_decay=0.0, loyalty_reinforce_cost=0, legal_pressure_threshold=0.5, availability=1.0)
    with pytest.raises(ValueError):
        CustodyPersona("p", "not_a_role", 1, 0.5, 0.0, 0, 0.5, 1.0)
    with pytest.raises(ValueError):
        default_adversary("not_an_objective")


# -- the benchmark runner ---------------------------------------------------


def test_campaign_runs_and_is_reproducible(tmp_path):
    summary = feral_custody_eval.run_campaign(tmp_path / "a", CONFIG)
    assert summary["accounting_all_ok"] is True
    assert set(summary["by_strategy"]) == set(STRATEGIES)
    assert summary["episode_count"] > 0
    feral_custody_eval.run_campaign(tmp_path / "b", CONFIG)
    for name in ("summary.json", "rows.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
    receipt = json.loads((tmp_path / "a" / "witness_receipt.json").read_text(encoding="utf-8"))
    for name, expected in receipt["artifacts"].items():
        assert hashlib.sha256((tmp_path / "a" / name).read_bytes()).hexdigest() == expected
    assert (tmp_path / "a" / "report.md").stat().st_size > 0
    assert (tmp_path / "a" / "figures" / "strategy_outcomes.png").stat().st_size > 0
