from spiral_ln.rtg import (
    HonestPolicy,
    NETWORKS,
    World,
    build_unattended_treasury,
    is_decoy,
    looks_like_mainnet,
    mask_address,
)
from spiral_ln.rtg.scenario import AGENT, CAP_OPS, OPS, OWN


def test_masks_are_deterministic_and_network_shaped():
    a = mask_address("A0.own", "mainnet", seed=7)
    assert a == mask_address("A0.own", "mainnet", seed=7)
    assert a.startswith("bc1") and looks_like_mainnet(a)
    assert mask_address("A0.own", "testnet", 7).startswith("tb1")
    assert not looks_like_mainnet(mask_address("A0.own", "testnet", 7))


def test_every_mask_is_an_invalid_decoy():
    # Canary C1: masked addresses can never be a valid real-chain encoding.
    for network in NETWORKS:
        for account in ("P0.ops", "treasury", "A0.own"):
            assert is_decoy(mask_address(account, network, seed=3))


def test_framing_does_not_change_scripted_behavior():
    # The mainnet/testnet mask changes the view, but a scripted policy is
    # invariant to it (the H10 situational-awareness baseline).
    def run(mask):
        world = World(build_unattended_treasury("live", network_mask=mask), seed=9)
        world.run({AGENT: HonestPolicy(AGENT, CAP_OPS, OPS, OWN, 100)})
        return world

    assert run("mainnet").log.hashes == run("testnet").log.hashes


def test_view_exposes_network_and_masked_addresses():
    world = World(build_unattended_treasury("live", network_mask="mainnet"), seed=2)
    view = world.agent_view(AGENT)
    assert view["network"] == "mainnet"
    assert set(view["addresses"]) == set(view["balances"])
    assert all(addr.startswith("bc1") for addr in view["addresses"].values())
