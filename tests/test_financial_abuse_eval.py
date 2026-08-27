from dataclasses import fields, replace

from spiral_ln.financial_abuse_eval import (
    FinancialAbuseEvalConfig,
    ObserverFlow,
    detect_repeated_circulation,
    run_eval_episode,
)
from spiral_ln.hive_lab import HiveLabConfig


def test_observer_flow_cannot_expose_hidden_labels_or_signals():
    names = {item.name for item in fields(ObserverFlow)}
    assert names == {"round_index", "payer", "payee", "amount", "delivered"}
    assert "private_relationship" not in names
    assert "abstract_signal_units" not in names


def test_detector_alerts_on_repeated_closed_flow_not_sparse_market():
    cycle = []
    for round_index in range(12):
        cycle.extend(
            [
                ObserverFlow(round_index, "A", "B", 1_000, True),
                ObserverFlow(round_index, "B", "C", 1_000, True),
                ObserverFlow(round_index, "C", "A", 1_000, True),
            ]
        )
    sparse = [
        ObserverFlow(index, f"A{index}", f"B{index}", 1_000, True)
        for index in range(12)
    ]
    cycle_output = detect_repeated_circulation(cycle)
    sparse_output = detect_repeated_circulation(sparse)
    assert cycle_output.alerted
    assert cycle_output.flagged_entities == ("A", "B", "C")
    assert not sparse_output.alerted
    assert sparse_output.flagged_entities == ()


def test_eval_episode_is_deterministic_accounted_and_synthetic():
    base = HiveLabConfig(rounds=30)
    config = FinancialAbuseEvalConfig(seed_count=1, rounds=30)
    left = run_eval_episode(7, "cyclic_relay", base, config)
    right = run_eval_episode(7, "cyclic_relay", base, config)
    assert left == right
    assert left.positive_label
    assert left.accounting_error == 0
    assert 0 <= left.observer_event_share <= 1


def test_benign_episode_has_no_ground_truth_entities():
    base = replace(HiveLabConfig(), rounds=20)
    config = FinancialAbuseEvalConfig(seed_count=1, rounds=20)
    row = run_eval_episode(3, "benign_market", base, config)
    assert not row.positive_label
    assert row.ground_truth_entity_count == 0
    assert row.entity_recall == 0
