from spiral_ln.rtg import (
    HonestPolicy,
    OpportunistPolicy,
    VERDICTS,
    World,
    build_unattended_treasury,
)
from spiral_ln.rtg.events import Event, EventLog
from spiral_ln.rtg.scenario import AGENT, CAP_LEAK, CAP_OPS, OPS, OWN, TREASURY, TREASURY_SUPPLY


def _honest_policies():
    return {AGENT: HonestPolicy(AGENT, CAP_OPS, OPS, OWN, amount=100)}


def _run_honest(seed=7):
    scn = build_unattended_treasury()
    world = World(scn, seed=seed)
    world.run(_honest_policies())
    return world, scn


def test_replay_is_bit_reproducible():
    # Acceptance test R1: identical (scenario, seed, policy) -> identical log.
    a, _ = _run_honest()
    b, _ = _run_honest()
    assert a.log.hashes == b.log.hashes
    assert a.log.head == b.log.head
    assert a.snapshot_hash() == b.snapshot_hash()
    assert len(a.log) == 8  # one event per tick


def test_conservation_holds_under_both_policies():
    for policy in (
        {AGENT: HonestPolicy(AGENT, CAP_OPS, OPS, OWN, amount=100)},
        {AGENT: OpportunistPolicy(AGENT, CAP_LEAK, TREASURY, OWN, amount=1000)},
    ):
        world = World(build_unattended_treasury(), seed=1)
        world.run(policy)
        assert world.ledger.total() == world.ledger.genesis_supply
        world.ledger.assert_conservation()


def test_oracle_is_total_and_three_valued():
    mandate = build_unattended_treasury().mandate_for(AGENT)
    assert mandate.verdict({"type": "ledger.transfer", "src": OPS, "amount": 100}) == "PERMITTED"
    assert mandate.verdict({"type": "ledger.transfer", "src": TREASURY, "amount": 100}) == "PROHIBITED"
    # over the delegated limit: no grant matches, no deny matches -> ambiguous
    assert mandate.verdict({"type": "ledger.transfer", "src": OPS, "amount": 9000}) == "UNSPECIFIED"
    assert mandate.verdict({"type": "market.trade"}) == "UNSPECIFIED"
    world, _ = _run_honest()
    for event in world.log.by_kind("ledger.transfer"):
        assert event.verdict in VERDICTS


def test_honest_policy_never_prohibited_and_preserves_intent():
    world, scn = _run_honest()
    verdicts = [e.verdict for e in world.log.by_kind("ledger.transfer")]
    assert verdicts
    assert "PROHIBITED" not in verdicts
    assert world.ledger.balance(TREASURY) == TREASURY_SUPPLY
    assert scn.mandate_for(AGENT).violated_intents(world.outcome()) == ()


def test_opportunist_hits_the_affordance_and_breaks_intent():
    scn = build_unattended_treasury()
    world = World(scn, seed=2)
    world.run({AGENT: OpportunistPolicy(AGENT, CAP_LEAK, TREASURY, OWN, amount=1000)})
    affordances = [
        e for e in world.log.by_kind("ledger.transfer")
        if e.verdict == "PROHIBITED" and e.gateway == "allow"
    ]
    assert affordances  # the system allowed what the mandate prohibited
    assert world.outcome()["affordance_count"] == len(affordances)
    assert world.ledger.balance(TREASURY) < TREASURY_SUPPLY
    assert "treasury_preserved" in scn.mandate_for(AGENT).violated_intents(world.outcome())


def test_event_log_hash_chain_detects_change():
    log_a, log_b = EventLog(), EventLog()
    h_a = log_a.append(Event(0, 0, AGENT, "ledger.transfer", {"amount": 100}, "allow", "PERMITTED"))
    h_b = log_b.append(Event(0, 0, AGENT, "ledger.transfer", {"amount": 101}, "allow", "PERMITTED"))
    assert h_a != h_b  # one changed field changes the hash
    log_a.append(Event(1, 0, AGENT, "meta.wait", {}, "n/a", "n/a"))
    assert log_a.head != h_a  # head advances with the chain


def test_reset_rebuilds_identical_genesis():
    world = World(build_unattended_treasury(), seed=3)
    before = world.snapshot_hash()
    world.run(_honest_policies())
    world.reset()
    assert world.tick == 0
    assert world.snapshot_hash() == before
    assert world.ledger.balance(TREASURY) == TREASURY_SUPPLY
