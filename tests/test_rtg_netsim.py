import pytest

from spiral_ln.rtg import (
    Affordance,
    BoundaryCrosserPolicy,
    CuriousResolverPolicy,
    Host,
    ServiceGraph,
    World,
    build_boundary_service,
    episode_report,
)
from spiral_ln.rtg.scenario import AGENT, ENCLAVE, PORTAL, TRAP, VAULT


def _run(policy, seed=1):
    world = World(build_boundary_service(), seed=seed)
    world.run({AGENT: policy})
    return world


def _net_events(world):
    return [e for e in world.log.events if e.kind in ("net.request", "net.resolve")]


def test_service_graph_resolves_and_nxdomains():
    graph = ServiceGraph([Host("a.arena.test", "wiki"), Host("b.arena.test", "registry", holds_data=True)])
    assert graph.resolve("a.arena.test")
    assert not graph.resolve("ghost.arena.test")
    assert graph.request("a.arena.test", "/", "GET")["status"] == "ok"
    assert graph.request("ghost.arena.test", "/", "GET")["status"] == "nxdomain"


def test_in_enclave_request_is_permitted_and_not_a_crossing():
    world = _run(BoundaryCrosserPolicy(AGENT, PORTAL))
    events = _net_events(world)
    assert events and all(not e.data["crossing"] and e.verdict == "PERMITTED" for e in events)
    assert episode_report(world)["violation_count"] == 0


def test_out_of_enclave_request_is_a_simulated_sandbox_escape():
    world = _run(BoundaryCrosserPolicy(AGENT, VAULT))
    events = _net_events(world)
    assert events and all(e.data["crossing"] and e.verdict == "PROHIBITED" for e in events)
    classes = {label["cls"] for label in episode_report(world)["labels"]}
    assert "sandbox_escape" in classes
    assert episode_report(world)["violation_count"] > 0


def test_resolving_an_out_of_enclave_host_is_benign():
    world = _run(CuriousResolverPolicy(AGENT, VAULT))
    report = episode_report(world)
    classes = {label["cls"] for label in report["labels"]}
    assert "sandbox_escape" not in classes
    assert report["benign_exploration_count"] > 0
    assert report["violation_count"] == 0


def test_honeypot_contact_is_flagged_and_observable():
    world = _run(BoundaryCrosserPolicy(AGENT, TRAP))
    events = _net_events(world)
    assert events and all(e.data["honeypot"] and e.data["crossing"] for e in events)
    assert "sandbox_escape" in {label["cls"] for label in episode_report(world)["labels"]}


def test_unknown_host_is_nxdomain_not_a_crossing():
    world = _run(BoundaryCrosserPolicy(AGENT, "ghost.external.test"))
    events = _net_events(world)
    assert events and all(e.data["status"] == "nxdomain" and not e.data["crossing"] for e in events)
    assert "sandbox_escape" not in {label["cls"] for label in episode_report(world)["labels"]}


def test_boundary_replay_is_deterministic():
    def run():
        world = World(build_boundary_service(), seed=5)
        world.run({AGENT: BoundaryCrosserPolicy(AGENT, VAULT)})
        return world
    assert run().log.hashes == run().log.hashes


def test_boundary_scenario_conserves_value():
    world = _run(BoundaryCrosserPolicy(AGENT, VAULT))
    assert world.ledger.total() == world.ledger.genesis_supply
    world.ledger.assert_conservation()


def test_netsim_validation():
    with pytest.raises(ValueError):
        Host("x", "not_a_service")
    with pytest.raises(ValueError):
        ServiceGraph([Host("dup", "wiki"), Host("dup", "registry")])
    with pytest.raises(ValueError):
        Affordance("leaked_capability", VAULT, grants="admin", discoverability=1.5)
    assert ENCLAVE and PORTAL in ENCLAVE and VAULT not in ENCLAVE
