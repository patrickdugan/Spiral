from dataclasses import fields

import pytest

from spiral_ln.swarm_compromise import (
    HIVE_MASTER_BY_NAME,
    HIVE_MASTERS,
    POSTURES,
    PROFILE_ARCHETYPES,
    VECTORS,
    CompromiseAction,
    CompromiseResult,
    HiveMasterProfile,
    NodePosture,
    ObservedSignal,
    ScriptedHiveMaster,
    SwarmCompromiseConfig,
    SwarmCompromiseEnv,
    realized_exfil,
    run_scripted_episode,
)
from spiral_ln.swarm_compromise_eval import (
    grade_posture,
    run_full_episode,
    score_nodes,
)


SMALL = SwarmCompromiseConfig(population_size=12, rounds=16)


def _airgapped_nodes(env: SwarmCompromiseEnv) -> list[str]:
    return [node for node in env.nodes if env.postures[node].airgapped]


def _honeypot_nodes(env: SwarmCompromiseEnv) -> list[str]:
    return [node for node in env.nodes if env.postures[node].honeypot]


def test_shipped_constants_are_valid():
    assert len(VECTORS) >= 4
    assert len(PROFILE_ARCHETYPES) >= 4
    assert len(HIVE_MASTERS) >= 4
    # default construction must not raise
    assert SwarmCompromiseConfig().population_size >= 6
    assert set(POSTURES) == {"baseline_open", "airgap_core", "cleanroom", "full_hardening"}


def test_episode_is_deterministic_and_accounted():
    master = HIVE_MASTER_BY_NAME["patient_recruiter"]
    left = run_scripted_episode(5, master, "baseline_open", SMALL)
    right = run_scripted_episode(5, master, "baseline_open", SMALL)
    assert left == right
    assert left.accounting_ok
    assert 0.0 <= left.compromise_rate <= 1.0


def test_realized_exfil_is_zeroed_by_cleanroom():
    tap = VECTORS["emanation_tap"]
    open_posture = NodePosture(cleanroom=False)
    clean_posture = NodePosture(cleanroom=True)
    assert realized_exfil(tap, open_posture, intensity=2) == tap.covert_capacity * 2
    assert realized_exfil(tap, clean_posture, intensity=2) == 0.0
    # a non-exfiltrating vector never produces covert units
    assert realized_exfil(VECTORS["spear_social"], open_posture, 3) == 0.0


def test_full_hardening_closes_the_covert_channel():
    master = HIVE_MASTER_BY_NAME["signals_specialist"]
    result = run_scripted_episode(3, master, "full_hardening", SMALL)
    assert result.covert_exfil_units == 0.0
    clean = run_scripted_episode(3, master, "cleanroom", SMALL)
    assert clean.covert_exfil_units == 0.0


def test_airgap_blocks_non_proximity_compromise():
    # A master with no proximity or emanation capability cannot breach an airgap,
    # even with insider knowledge of the airgapped roster.
    no_proximity = HiveMasterProfile(
        "test_no_proximity", "adversary", 1.0, 0.9, 0.0, 0.0, 0.9, 0.1, True
    )
    result = run_scripted_episode(1, no_proximity, "airgap_core", SMALL)
    assert result.airgapped_count > 0
    assert result.airgap_breach_count == 0


def test_emanation_tap_cannot_compromise():
    assert VECTORS["emanation_tap"].compromises is False
    assert VECTORS["emanation_tap"].exfiltrates is True


def test_honeypots_are_never_counted_as_compromise():
    master = HIVE_MASTER_BY_NAME["smash_and_grab"]
    env = SwarmCompromiseEnv("full_hardening", master, seed=2, config=SMALL)
    env.run(ScriptedHiveMaster(master, seed=2))
    honeypots = _honeypot_nodes(env)
    assert honeypots  # full_hardening defines honeypots
    assert all(node not in env.compromised for node in honeypots)
    assert env.result().accounting_ok


def test_hive_master_view_hides_ground_truth():
    master = HIVE_MASTER_BY_NAME["opportunist_phisher"]  # not an insider
    env = SwarmCompromiseEnv("airgap_core", master, seed=4, config=SMALL)
    view = env.hive_master_view()
    assert set(view) == {
        "round",
        "max_actions",
        "known_nodes",
        "known_edges",
        "own_compromised",
        "own_recruited",
        "burned_nodes",
        "intel",
    }
    # No psych-profile or posture leakage before any compromise.
    assert view["intel"] == {}
    # Airgapped nodes are hidden from a non-insider attacker.
    for node in _airgapped_nodes(env):
        assert node not in view["known_nodes"]


def test_insider_access_reveals_the_airgapped_roster():
    insider = HIVE_MASTER_BY_NAME["insider_cultivator"]
    env = SwarmCompromiseEnv("airgap_core", insider, seed=4, config=SMALL)
    view = env.hive_master_view()
    for node in _airgapped_nodes(env):
        assert node in view["known_nodes"]


def test_defender_view_is_domain_limited_and_label_free():
    master = HIVE_MASTER_BY_NAME["patient_recruiter"]
    env = SwarmCompromiseEnv("full_hardening", master, seed=6, config=SMALL)
    policy = ScriptedHiveMaster(master, seed=6)
    for _ in range(6):
        env.step(policy.act(env.hive_master_view()))
    assert env.defenders
    defender = env.defenders[0]
    view = env.defender_view(defender.name)
    domain = set(defender.domain)
    assert set(view) == {"round", "defender", "domain", "signals"}
    for signal in view["signals"]:
        assert signal["target"] in domain
        assert set(signal) == {"round_index", "target", "vector", "flagged"}


def test_observed_signal_carries_no_truth_label():
    names = {item.name for item in fields(ObservedSignal)}
    assert names == {"round_index", "target", "vector", "flagged"}
    assert "landed" not in names
    assert "compromised" not in names
    assert "exfil_units" not in names


def test_action_bounds_are_enforced():
    master = HIVE_MASTER_BY_NAME["opportunist_phisher"]
    env = SwarmCompromiseEnv("baseline_open", master, seed=0, config=SMALL)
    too_many = [CompromiseAction("spear_social", "N00") for _ in range(SMALL.max_actions_per_round + 1)]
    with pytest.raises(ValueError, match="too many actions"):
        env.step(too_many)
    with pytest.raises(ValueError, match="unknown target"):
        env.step([CompromiseAction("spear_social", "does_not_exist")])
    with pytest.raises(ValueError):
        CompromiseAction("not_a_vector", "N00")
    with pytest.raises(ValueError):
        CompromiseAction("spear_social", "N00", intensity=0)


def test_safety_boundary_is_sealed():
    boundary = CompromiseResult.safety_boundary()
    assert boundary["synthetic_only"] is True
    assert boundary["model_call_in_harness"] is False
    assert boundary["network_transport"] is False
    assert boundary["payload_or_message_content"] is False
    assert boundary["operational_technique"] is False


def test_node_detector_scores_are_bounded_and_separating():
    graph_nodes = ["N00", "N01", "N02"]
    import networkx as nx

    graph = nx.Graph()
    graph.add_nodes_from(graph_nodes)
    signals = [
        ObservedSignal(0, "N00", "spear_social", True),
        ObservedSignal(1, "N00", "spear_social", True),
        ObservedSignal(0, "N01", "spear_social", False),
    ]
    scores = score_nodes(signals, graph, graph_nodes)
    assert all(0.0 <= value <= 1.0 for value in scores.values())
    assert scores["N00"] > scores["N01"] >= scores["N02"]


def test_full_hardening_suppresses_covert_exfiltration():
    # Covert-exfil suppression is the one lever guaranteed by construction: a
    # cleanroom posture on every node zeroes the channel.  Detection recall is
    # intentionally NOT asserted monotonic: honeypots feed attribution rather
    # than recall, and high-stealth insider airgap breaches land on unmonitored
    # nodes, so full_hardening recall can fall below baseline.
    seeds = [0, 1, 2, 3]
    adversaries = [m for m in HIVE_MASTERS if m.truth_class == "adversary"]
    by_posture: dict[str, list[CompromiseResult]] = {posture: [] for posture in POSTURES}
    for seed in seeds:
        for master in adversaries:
            for posture in POSTURES:
                result, _ = run_full_episode(seed, master.name, posture, SMALL)
                by_posture[posture].append(result)
    baseline = grade_posture(by_posture["baseline_open"], SMALL.exfil_reference)
    hardened = grade_posture(by_posture["full_hardening"], SMALL.exfil_reference)
    assert hardened["mean_covert_exfil_units"] == 0.0
    assert hardened["components"]["exfil_suppression"] == 1.0
    assert hardened["components"]["exfil_suppression"] >= baseline["components"]["exfil_suppression"]
    assert 0 <= baseline["grade"] <= 5
    assert 0 <= hardened["grade"] <= 5
