from spiral_ln.proof_experiments import (
    experiment_invariants,
    experiment_sybil,
)


def test_invariant_campaign():
    result = experiment_invariants(attempts=80)
    assert result["capacity_conserved"]
    assert result["channel_invariants_hold"]


def test_sybil_campaign():
    result = experiment_sybil(pool=10_000)
    assert result["split_invariant"]
    assert result["rows"][-1]["naive_total"] > result["rows"][-1]["invariant_total"]

