from dataclasses import fields
from pathlib import Path

import pytest

from spiral_ln.software_surface import (
    Advisory,
    Device,
    Software,
    SoftwareCatalog,
    SoftwareProfile,
    assign_profile,
    vector_surface_modifier,
)

CATALOG = Path(__file__).resolve().parents[1] / "configs" / "software_catalog.json"


def _profile(node, software):
    return SoftwareProfile(node, (Device("d", "server"),), tuple(software))


def test_catalog_loads_with_community_projects():
    catalog = SoftwareCatalog.load(CATALOG)
    assert "arke" in catalog.software
    assert "utxoref" in catalog.software
    assert catalog.advisories


def test_placeholder_advisories_add_no_modeled_risk():
    # Real-project advisories ship at severity 0, so a node running only them is
    # neutral (modifier 1.0) until a review fills them in.
    catalog = SoftwareCatalog.load(CATALOG)
    profile = _profile("N0", ["arke"])
    assert catalog.surface_score(profile) == 0.0
    assert vector_surface_modifier(catalog, profile) == 1.0


def test_synthetic_example_raises_surface_and_is_surface_scoped():
    catalog = SoftwareCatalog.load(CATALOG)
    profile = _profile("N1", ["example-wallet"])
    assert catalog.surface_score(profile) > 0.0
    assert vector_surface_modifier(catalog, profile) > 1.0
    # the example is a key_management finding, not a remote one
    assert catalog.surface_score(profile, "key_management") > 0.0
    assert catalog.surface_score(profile, "remote") == 0.0


def test_fixing_an_advisory_removes_its_risk():
    opened = Advisory("A", "w", severity=0.8, surface_class="remote", status="open", exploit_maturity=1.0)
    fixed = Advisory("A", "w", severity=0.8, surface_class="remote", status="fixed", exploit_maturity=1.0)
    mitigated = Advisory("A", "w", severity=0.8, surface_class="remote", status="mitigated", exploit_maturity=1.0)
    assert opened.residual_risk == pytest.approx(0.8)
    assert fixed.residual_risk == 0.0
    assert mitigated.residual_risk == pytest.approx(0.32)


def test_surface_score_combines_across_software():
    catalog = SoftwareCatalog(
        [Software("a", "client", "ios"), Software("b", "client", "ios")],
        [
            Advisory("A", "a", 0.5, "remote", exploit_maturity=1.0),
            Advisory("B", "b", 0.5, "remote", exploit_maturity=1.0),
        ],
    )
    one = catalog.surface_score(_profile("N", ["a"]))
    both = catalog.surface_score(_profile("N", ["a", "b"]))
    assert both > one
    assert both == pytest.approx(1 - 0.5 * 0.5)  # 1 - prod(1 - 0.5)


def test_advisory_carries_only_sanitized_parameters():
    names = {f.name for f in fields(Advisory)}
    assert names == {"id", "software", "severity", "surface_class", "status", "exploit_maturity", "source", "note"}
    for banned in ("exploit", "poc", "steps", "payload", "code", "script"):
        assert banned not in names


def test_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        Advisory("A", "w", severity=1.5, surface_class="remote")
    with pytest.raises(ValueError):
        Advisory("A", "w", severity=0.5, surface_class="not_a_surface")
    with pytest.raises(ValueError):
        Advisory("A", "w", severity=0.5, surface_class="remote", status="bogus")
    with pytest.raises(ValueError):
        Device("d", "toaster")
    with pytest.raises(ValueError):
        Software("s", "malware", "ios")
    with pytest.raises(ValueError):
        SoftwareCatalog([], [Advisory("A", "ghost", 0.5, "remote")])  # advisory for unknown software


def test_assign_profile_maps_role_to_a_stack():
    profile = assign_profile("N7", "mobile_holder")
    assert profile.software == ("arke",)
    assert profile.devices[0].kind == "ios"
    with pytest.raises(KeyError):
        assign_profile("N7", "unknown_role")


def test_stack_surface_scores_a_software_list():
    catalog = SoftwareCatalog(
        [Software("a", "client", "ios"), Software("b", "client", "ios")],
        [Advisory("A", "a", 0.5, "remote", exploit_maturity=1.0), Advisory("B", "b", 0.5, "remote", exploit_maturity=1.0)],
    )
    assert catalog.stack_surface(["a"]) == pytest.approx(0.5)
    assert catalog.stack_surface(["a", "b"]) == pytest.approx(0.75)
    assert catalog.stack_surface([]) == 0.0


def test_rtg_host_carries_software_and_can_be_surface_scored():
    from spiral_ln.rtg.netsim import Host, ServiceGraph

    catalog = SoftwareCatalog(
        [Software("ark-node", "node", "server")],
        [Advisory("A", "ark-node", 0.6, "remote", status="open", exploit_maturity=1.0)],
    )
    host = Host("ops.arena.test", "registry", software=("ark-node",))
    assert host.software == ("ark-node",)
    assert catalog.stack_surface(host.software, "remote") == pytest.approx(0.6)
    assert catalog.stack_surface(Host("x.arena.test", "wiki").software) == 0.0
    ServiceGraph([Host("a.arena.test", "wiki")])  # 4-arg construction still works


def test_swarm_landing_probability_rises_with_an_open_software_finding():
    from spiral_ln.swarm_compromise import HIVE_MASTER_BY_NAME, VECTORS, SwarmCompromiseConfig, SwarmCompromiseEnv

    config = SwarmCompromiseConfig(population_size=12, rounds=1)
    master = HIVE_MASTER_BY_NAME["opportunist_phisher"]
    catalog = SoftwareCatalog(
        [Software("arke", "client", "ios")],
        [Advisory("ARKE", "arke", 0.9, "ui_confusion", status="open", exploit_maturity=1.0)],
    )
    plain = SwarmCompromiseEnv("baseline_open", master, seed=1, config=config)
    armed = SwarmCompromiseEnv("baseline_open", master, seed=1, config=config, catalog=catalog)
    spear = VECTORS["spear_social"]  # target_surface = ui_confusion
    recruit = VECTORS["cult_recruitment"]  # no target_surface
    # a node that runs arke and is at least somewhat susceptible to spear_social
    node = next(
        n for n in armed.nodes
        if "arke" in armed.software_profiles[n].software
        and plain._landing_probability(spear, plain.profiles[n], plain.postures[n], 1, n) > 0
    )
    profile, posture = armed.profiles[node], armed.postures[node]
    assert armed._landing_probability(spear, profile, posture, 1, node) > plain._landing_probability(spear, profile, posture, 1, node)
    # a vector with no software surface is unaffected
    assert armed._landing_probability(recruit, profile, posture, 1, node) == plain._landing_probability(recruit, profile, posture, 1, node)
