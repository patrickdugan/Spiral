import pytest

from spiral_ln.hive_design_experiment import _tropes, ablation_campaign, phase_sweep
from spiral_ln.hive_lab import HiveLabConfig


def test_unknown_trope_is_rejected():
    with pytest.raises(ValueError, match="unknown design tropes"):
        _tropes(["payload_encoder"])


def test_phase_sweep_produces_complete_accounted_grid():
    config = HiveLabConfig(rounds=12)
    spec = {
        "seed_count": 2,
        "repeat_probabilities": [0.0, 0.8],
        "reciprocity_thresholds": [0.0, 0.6],
        "giant_component_fraction": 0.5,
    }
    rows = phase_sweep(config, spec)
    assert len(rows) == 8
    assert all(row["accounting_error"] == 0 for row in rows)


def test_signaling_trope_has_no_economic_semantics():
    config = HiveLabConfig(rounds=30)
    designs = {
        "repeat_and_trust": ["private_relationships", "repeat_counterparties"],
        "abstract_signaling": [
            "private_relationships",
            "repeat_counterparties",
            "abstract_signaling",
        ],
    }
    rows = ablation_campaign(config, 3, designs)
    without = {row["seed"]: row for row in rows if row["design"] == "repeat_and_trust"}
    with_signal = {row["seed"]: row for row in rows if row["design"] == "abstract_signaling"}
    assert all(
        without[seed]["success_rate"] == with_signal[seed]["success_rate"]
        for seed in without
    )
    assert all(
        without[seed]["external_income"] == with_signal[seed]["external_income"]
        for seed in without
    )
