from dataclasses import fields

import pytest

from spiral_ln.hive_lab import (
    AgentAction,
    DesignTropes,
    FlowEvent,
    HiveEconomyEnv,
    HiveLabConfig,
    run_hive_lab,
)


def test_lab_is_deterministic_and_accounted():
    left = run_hive_lab(3, "hive_reinvestment")
    right = run_hive_lab(3, "hive_reinvestment")
    assert left == right
    assert left.accounting_error == 0
    assert left.ending_network_capacity >= 0


def test_ordinary_commerce_has_no_private_signaling_or_hive():
    result = run_hive_lab(2, "ordinary_commerce")
    assert result.private_delivered_volume == 0
    assert result.abstract_signal_units == 0
    assert result.hive_count == 0
    assert result.connector_count == 0


def test_private_overlay_emerges_without_live_capabilities():
    result = run_hive_lab(2, "private_unicast")
    assert result.private_flow_share > 0.5
    assert result.largest_hive_size >= 3
    assert result.safety_boundary == {
        "synthetic_only": True,
        "payload_codec": False,
        "wallet_or_node_connection": False,
        "network_transport": False,
        "transaction_broadcast": False,
    }


def test_hive_reinvestment_is_bounded():
    config = HiveLabConfig(max_private_connectors=2)
    env = HiveEconomyEnv("hive_reinvestment", seed=2, config=config)
    result = env.run()
    assert result.connector_count <= 2
    assert result.connector_capital == result.connector_count * config.connector_capital
    assert result.ending_network_capacity == env.initial_network_capacity + result.connector_capital


def test_flow_events_cannot_hold_message_content():
    names = {item.name for item in fields(FlowEvent)}
    assert "payload" not in names
    assert "message" not in names
    assert "bytes" not in names


def test_external_agent_action_uses_bounded_abstract_signal_only():
    config = HiveLabConfig(rounds=1, external_job_probability=0)
    env = HiveEconomyEnv("private_unicast", seed=4, config=config)
    env.step([AgentAction("A0", "B0", 1_000, True, 2)])
    assert len(env.events) == 1
    assert env.events[0].private_relationship
    assert env.events[0].abstract_signal_units in (0, 2)
    assert env.result().accounting_error == 0


def test_disabled_trope_rejects_private_action_without_mutation():
    config = HiveLabConfig(rounds=1, external_job_probability=0)
    env = HiveEconomyEnv("ordinary_commerce", seed=4, config=config)
    with pytest.raises(ValueError, match="private relationships are disabled"):
        env.step([AgentAction("A0", "B0", 1_000, True, 0)])
    assert env.round_index == 0
    assert env.events == []


def test_local_and_observer_views_do_not_expose_hidden_state():
    env = HiveEconomyEnv("private_unicast", seed=4, config=HiveLabConfig(rounds=1))
    env.step([AgentAction("A0", "B0", 1_000, True, 1)])
    local = env.agent_view("A0")
    observer = env.observer_view()
    assert "agent_wealth" not in local
    assert "network" not in local
    assert "private_relationship" not in observer
    assert "abstract_signal_units" not in observer


def test_custom_trope_composition_is_supported():
    tropes = DesignTropes(private_relationships=True, repeat_counterparties=False)
    env = HiveEconomyEnv("private_unicast", seed=1, tropes=tropes)
    assert env.tropes.enabled() == ("private_relationships", "partial_observer")
