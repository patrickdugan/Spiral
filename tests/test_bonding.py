from spiral_ln.bonding import (
    BondPolicy,
    RewardClaim,
    ServiceRecord,
    settle_bond,
    sybil_invariant_rewards,
)


def test_identity_split_does_not_increase_coalition_reward():
    totals = []
    for count in (1, 2, 8, 32):
        claims = [RewardClaim(str(i), "same-utxo", 100_000, 1.0) for i in range(count)]
        totals.append(sum(sybil_invariant_rewards(claims, 50_000).values()))
    assert totals == [50_000] * 4


def test_flaky_service_is_slashed_more():
    policy = BondPolicy()
    honest = ServiceRecord("h", "h", 10_000, 100, 99, 100, 98, 0)
    flaky = ServiceRecord("f", "f", 10_000, 100, 50, 100, 30, 10)
    assert settle_bond(flaky, policy).slashed > settle_bond(honest, policy).slashed

