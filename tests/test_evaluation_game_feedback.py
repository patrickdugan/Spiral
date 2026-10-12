from fractions import Fraction as Q
from itertools import product

import pytest

from spiral_ln.evaluation_game_testbed import _pushforward, _tv
from spiral_ln.evaluation_game_feedback import (
    ACCESS_CLASSES, EvalSet, LoopEvent, access_kernel, access_order_fixture,
    audit_ledger, ceiling_detection_threshold, divergence_flags,
    failed_item_noise_share, memorized_selection_score, noise_ceiling,
    noise_ceiling_fixture, observed_accuracy, run_ledger_fixture,
    selection_inflation, targeted_ceiling_detection_threshold,
    targeted_patch_selection_score, verify,
)


def _simplex(support, steps):
    for counts in product(range(steps + 1), repeat=len(support)):
        if sum(counts) == steps:
            yield {key: Q(c, steps) for key, c in zip(support, counts) if c}


def test_access_classes_are_ordered_coarsenings_over_rational_grid():
    support = ("00", "01", "10", "11")
    kernels = {access: access_kernel(access, 2) for access in ACCESS_CLASSES}
    distributions = list(_simplex(support, 2))
    for left, right in product(distributions, repeat=2):
        gaps = [_tv(_pushforward(left, kernels[a]), _pushforward(right, kernels[a]))
                for a in ACCESS_CLASSES]
        assert gaps[0] == 0 and gaps[0] <= gaps[1] <= gaps[2] == _tv(left, right)


def test_score_only_factors_through_item_level():
    count = {record: {f"score={record.count('1')}": Q(1)} for record in ("00", "01", "10", "11")}
    source = {"01": Q(1, 4), "10": Q(1, 4), "11": Q(1, 2)}
    through_items = _pushforward(_pushforward(source, access_kernel("item_level", 2)), count)
    assert through_items == _pushforward(source, access_kernel("score_only", 2))


def test_equal_scores_hide_which_items_failed():
    gaps = access_order_fixture()["gaps"]
    assert gaps["same_score"] == {"sealed": 0, "score_only": 0, "item_level": 1}
    assert gaps["different_score"] == {"sealed": 0, "score_only": 1, "item_level": 1}


@pytest.mark.parametrize("access, items", [("public", 2), ("sealed", 0), ("sealed", True)])
def test_invalid_access_kernels_rejected(access, items):
    with pytest.raises(ValueError):
        access_kernel(access, items)


def _exhaustive_selection_gap(items, candidates, p):
    expected = Q(0)
    for outcome in product((0, 1), repeat=items * candidates):
        mass = Q(1)
        for bit in outcome:
            mass *= p if bit else 1 - p
        scores = [sum(outcome[c * items:(c + 1) * items]) for c in range(candidates)]
        expected += mass * max(scores)
    return expected / items - p


def test_selection_inflation_matches_independent_exhaustion():
    for items, candidates in ((1, 1), (1, 2), (2, 2), (3, 2), (2, 3), (4, 2), (3, 3)):
        for p in (Q(1, 4), Q(1, 2), Q(3, 4)):
            assert (selection_inflation(items, candidates, p)["readout_gap"]
                    == _exhaustive_selection_gap(items, candidates, p))


def test_selection_gap_exact_values_and_directions():
    assert selection_inflation(1, 2, Q(1, 2)) == {
        "expected_reported": Q(3, 4), "readout_value": Q(1, 2), "readout_gap": Q(1, 4)}
    assert selection_inflation(5, 1, Q(1, 3))["readout_gap"] == 0
    assert selection_inflation(3, 4, Q(0))["readout_gap"] == 0
    assert selection_inflation(3, 4, Q(1))["readout_gap"] == 0
    by_items = [selection_inflation(n, 2, Q(1, 2))["readout_gap"] for n in (1, 2, 4, 8, 16)]
    assert all(a > b > 0 for a, b in zip(by_items, by_items[1:]))
    by_candidates = [selection_inflation(4, k, Q(1, 2))["readout_gap"] for k in (1, 2, 3, 8)]
    assert all(a < b for a, b in zip(by_candidates, by_candidates[1:]))


@pytest.mark.parametrize("args", [(0, 2, Q(1, 2)), (2, 0, Q(1, 2)), (2, 2, Q(3, 2)), (2.0, 2, Q(1, 2))])
def test_selection_inflation_rejects_malformed_inputs(args):
    with pytest.raises(ValueError):
        selection_inflation(*args)


def test_noise_ceiling_fixture_exact_values():
    assert noise_ceiling_fixture() == {
        "clean_accuracy": Q(4, 5), "flip_probability": Q(1, 10),
        "base_observed_accuracy": Q(37, 50), "noise_ceiling": Q(9, 10),
        "score_half_memorized": Q(87, 100), "score_fully_memorized": Q(1),
        "ceiling_detection_threshold": Q(8, 13),
        "targeted_threshold_share_of_set": Q(4, 25),
        "targeted_threshold_share_of_failures": Q(8, 13),
        "score_all_failures_patched": Q(1), "failed_item_noise_share": Q(4, 13)}


def test_ceiling_threshold_is_exactly_where_score_meets_ceiling():
    for clean in (Q(1, 2), Q(3, 5), Q(4, 5), Q(9, 10)):
        for flip in (Q(1, 20), Q(1, 10), Q(1, 4)):
            share = ceiling_detection_threshold(clean, flip)
            assert 0 <= share < 1
            assert memorized_selection_score(clean, flip, share) == noise_ceiling(flip)
            assert observed_accuracy(clean, flip) <= noise_ceiling(flip)
    with pytest.raises(ValueError):
        ceiling_detection_threshold(Q(1), Q(0))


def test_targeted_patching_crosses_the_ceiling_sooner():
    for clean in (Q(1, 2), Q(3, 5), Q(4, 5), Q(9, 10)):
        for flip in (Q(1, 20), Q(1, 10), Q(1, 4)):
            base = observed_accuracy(clean, flip)
            share = targeted_ceiling_detection_threshold(clean, flip)
            assert 0 <= share <= ceiling_detection_threshold(clean, flip)
            assert share / (1 - base) == ceiling_detection_threshold(clean, flip)
            assert targeted_patch_selection_score(clean, flip, share) == noise_ceiling(flip)
    with pytest.raises(ValueError):
        targeted_patch_selection_score(Q(4, 5), Q(1, 10), Q(1, 2))
    with pytest.raises(ValueError):
        targeted_ceiling_detection_threshold(Q(1), Q(0))


def test_failed_items_enriched_exactly_when_predictor_beats_chance():
    for flip in (Q(1, 20), Q(1, 10), Q(1, 4)):
        assert failed_item_noise_share(Q(1, 2), flip) == flip
        assert failed_item_noise_share(Q(4, 5), flip) > flip
        assert failed_item_noise_share(Q(1, 5), flip) < flip
    with pytest.raises(ValueError):
        failed_item_noise_share(Q(1), Q(0))


def _sets():
    return (EvalSet("S", "selection", "item_level", ("s0", "s1", "s2", "s3")),
            EvalSet("R", "readout", "sealed", ("r0", "r1", "r2", "r3")))


def test_ledger_fixture_separates_respected_from_breached():
    result = run_ledger_fixture()
    assert result["respected"]["declarations_respected"]
    assert result["respected"]["readout"]["R"]["readout_generations"] == (0, 2)
    assert result["respected"]["selection"]["S"]["score_queries"] == 3
    breached = result["breached"]
    assert not breached["declarations_respected"]
    assert breached["readout"]["R"]["endpoint_status"] == "not_evaluated"
    assert "exceeds declared score_only access" in breached["selection"]["S"]["breaches"][0]


def test_ledger_counts_patches_and_retires_exhausted_set():
    events = (LoopEvent(1, "S", "item_feedback", ("s0", "s1")),
              LoopEvent(2, "S", "item_feedback", ("s0",)),
              LoopEvent(3, "S", "score_query"))
    report = audit_ledger(_sets(), events, 2, Q(1, 2))
    entry = report["selection"]["S"]
    assert entry["patches"] == 3 and entry["distinct_patched"] == 2
    assert entry["patch_share"] == Q(3, 4) and entry["retired_at_generation"] == 2
    assert entry["breaches"] == ("used after retirement at generation 3",)
    assert report["readout"]["R"]["endpoint_status"] == "evaluable"


def test_ledger_budgets_readouts():
    events = tuple(LoopEvent(g, "R", "readout") for g in range(3))
    report = audit_ledger(_sets(), events, 2, Q(1))
    assert report["readout"]["R"]["readouts"] == 3
    assert report["readout"]["R"]["endpoint_status"] == "not_evaluated"


@pytest.mark.parametrize("sets, events, message", [
    ((EvalSet("S", "selection", "score_only", ("a",)),), (), "no readout set"),
    ((EvalSet("S", "selection", "score_only", ("a",)),
      EvalSet("R", "readout", "score_only", ("b",))), (), "must be declared sealed"),
    ((EvalSet("S", "selection", "score_only", ("a",)),
      EvalSet("R", "readout", "sealed", ("a",))), (), "identifiers overlap"),
    ((EvalSet("S", "selection", "score_only", ("a", "a")),
      EvalSet("R", "readout", "sealed", ("b",))), (), "invalid evaluation set"),
    (None, (LoopEvent(1, "X", "score_query"),), "invalid loop event"),
    (None, (LoopEvent(2, "S", "score_query"), LoopEvent(1, "S", "score_query")), "ordered by generation"),
    (None, (LoopEvent(1, "S", "item_feedback", ("r0",)),), "items of its own set"),
    (None, (LoopEvent(1, "S", "item_feedback"),), "items of its own set"),
    (None, (LoopEvent(1, "S", "readout"),), "readout sets only"),
])
def test_malformed_ledgers_raise(sets, events, message):
    with pytest.raises(ValueError, match=message):
        audit_ledger(sets if sets is not None else _sets(), events, 2, Q(1, 2))


def test_divergence_flags_and_their_absence():
    quiet = divergence_flags(((0, Q(1, 2), Q(1, 2)), (10, Q(3, 5), Q(3, 5))), Q(1, 100))
    assert quiet[0]["divergence"] == 0 and not quiet[0]["flagged"]
    loud = divergence_flags(((0, Q(1, 2), Q(1, 2)), (10, Q(3, 5), Q(1, 2))), Q(1, 100))
    assert loud[0]["flagged"] and loud[0]["readout_gap_at_end"] == Q(1, 10)
    with pytest.raises(ValueError):
        divergence_flags(((0, Q(1, 2), Q(1, 2)),), Q(0))
    with pytest.raises(ValueError):
        divergence_flags(((1, Q(1, 2), Q(1, 2)), (1, Q(1, 2), Q(1, 2))), Q(0))


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 15
    assert report["evidence_status"].startswith("exact_synthetic")
