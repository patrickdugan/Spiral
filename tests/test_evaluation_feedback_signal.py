from fractions import Fraction as Q
from itertools import combinations, product

import pytest

from spiral_ln.evaluation_game_feedback import observed_accuracy
from spiral_ln.evaluation_feedback_signal import (
    CREDIT_KINDS, TrainingSignal, binary_splitting, binary_splitting_worst_case,
    ceiling_reachable_without_memorization, credit_channel, episodes_to_distinguish,
    exact_min_queries, image_count, judge_correlation_inflation, observed_accuracy_shared,
    refines, score_query_lower_bound, selection_value, shared_error_bounds, verify,
)


def _partition(kernel):
    blocks = {}
    for record, image in kernel.items():
        blocks.setdefault(next(iter(image)), set()).add(record)
    return {frozenset(b) for b in blocks.values()}


def test_refines_matches_partition_containment():
    for steps in (1, 2, 3, 4):
        kernels = {k: credit_channel(k, steps) for k in CREDIT_KINDS}
        for fine, coarse in product(CREDIT_KINDS, repeat=2):
            fine_blocks, coarse_blocks = _partition(kernels[fine]), _partition(kernels[coarse])
            contained = all(any(f <= c for c in coarse_blocks) for f in fine_blocks)
            assert refines(kernels[fine], kernels[coarse]) == contained


def test_credit_image_counts_and_incomparability():
    for steps in (2, 3, 5):
        kernels = {k: credit_channel(k, steps) for k in CREDIT_KINDS}
        assert [image_count(kernels[k]) for k in CREDIT_KINDS] == [2, steps + 1, steps + 1, 2 ** steps]
        assert not refines(kernels["count"], kernels["first_failure"])
        assert not refines(kernels["first_failure"], kernels["count"])
    one = credit_channel("count", 1)
    assert refines(one, credit_channel("first_failure", 1)) and refines(credit_channel("first_failure", 1), one)


def test_episodes_to_distinguish_counting_bound():
    kernel = credit_channel("outcome", 4)
    assert episodes_to_distinguish(kernel, 1) == 0
    assert episodes_to_distinguish(kernel, 2) == 1
    assert episodes_to_distinguish(kernel, 16) == 4
    assert episodes_to_distinguish(kernel, 17) == 5
    sealed = {record: {"sealed": Q(1)} for record in kernel}
    assert episodes_to_distinguish(sealed, 1) == 0
    with pytest.raises(ValueError):
        episodes_to_distinguish(sealed, 2)
    with pytest.raises(ValueError):
        episodes_to_distinguish(kernel, 0)


@pytest.mark.parametrize("args", [("outcome", 0), ("outcome", 2.0), ("reward", 2)])
def test_credit_channel_rejects_malformed(args):
    with pytest.raises(ValueError):
        credit_channel(*args)


def test_binary_splitting_recovers_every_set_and_respects_bounds():
    for items in range(1, 9):
        for failed in range(items + 1):
            lower = score_query_lower_bound(items, failed)
            worst = 0
            for subset in combinations(range(items), failed):
                recovered, used = binary_splitting(items, frozenset(subset))
                assert recovered == frozenset(subset)
                worst = max(worst, used)
            assert worst == binary_splitting_worst_case(items, failed)
            assert lower <= worst - 1


def test_exact_min_queries_between_lower_bound_and_binary_splitting():
    for items in range(1, 7):
        for failed in range(items + 1):
            lower = score_query_lower_bound(items, failed)
            exact = exact_min_queries(items, failed)
            assert lower <= exact <= binary_splitting_worst_case(items, failed) - 1
            if failed in (0, items):
                assert exact == 0


def test_single_failure_is_binary_search():
    for items in (2, 3, 4, 5, 6, 7):
        bits = (items - 1).bit_length()
        assert score_query_lower_bound(items, 1) == bits
        assert exact_min_queries(items, 1) == bits


@pytest.mark.parametrize("args", [(0, 0), (3, 4), (3, -1), (2.0, 1), (8, 1)])
def test_reconstruction_rejects_malformed(args):
    with pytest.raises(ValueError):
        exact_min_queries(*args)


def test_shared_error_identity_and_feasibility():
    grid = [Q(k, 10) for k in range(1, 10)]
    for accuracy in grid:
        for judge_error in [Q(k, 20) for k in range(0, 21)]:
            low, high = shared_error_bounds(accuracy, judge_error)
            assert 0 <= low <= high <= 1
            for step in range(5):
                eps1 = low + (high - low) * Q(step, 4)
                inflation = judge_correlation_inflation(accuracy, judge_error, eps1)
                assert inflation == 2 * (1 - accuracy) * (eps1 - judge_error)
                eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
                assert 0 <= eps0 <= 1
                assert accuracy * eps0 + (1 - accuracy) * eps1 == judge_error
    assert observed_accuracy_shared(Q(4, 5), Q(1, 10), Q(1, 10)) == observed_accuracy(Q(4, 5), Q(1, 10))
    with pytest.raises(ValueError):
        observed_accuracy_shared(Q(4, 5), Q(1, 10), Q(3, 5))
    with pytest.raises(ValueError):
        shared_error_bounds(Q(1), Q(1, 10))


def test_ceiling_reached_exactly_at_eps1_one_half():
    for accuracy in (Q(1, 2), Q(3, 5), Q(4, 5), Q(9, 10)):
        for judge_error in (Q(1, 20), Q(1, 10), Q(1, 4)):
            low, high = shared_error_bounds(accuracy, judge_error)
            reachable = ceiling_reachable_without_memorization(accuracy, judge_error)
            assert reachable == (high >= Q(1, 2)) == (judge_error >= (1 - accuracy) / 2)
            if reachable:
                assert observed_accuracy_shared(accuracy, judge_error, Q(1, 2)) == 1 - judge_error
            for step in range(5):
                eps1 = low + (high - low) * Q(step, 4)
                above = observed_accuracy_shared(accuracy, judge_error, eps1) >= 1 - judge_error
                assert above == (eps1 >= Q(1, 2))
    with pytest.raises(ValueError):
        ceiling_reachable_without_memorization(Q(4, 5), Q(1, 2))


def _value_by_enumerating_rules(kernel, types, prior, utility):
    image = {record: next(iter(kernel[record])) for record in kernel}
    weights = {}
    for first, second in product(types, repeat=2):
        for r1, p1 in types[first].items():
            for r2, p2 in types[second].items():
                key = (image[r1], image[r2])
                weights.setdefault(key, [Q(0), Q(0)])
                weights[key][0] += prior[first] * p1 * prior[second] * p2 * utility[first]
                weights[key][1] += prior[first] * p1 * prior[second] * p2 * utility[second]
    observations = sorted(weights)
    best = None
    for rule in product((0, 1), repeat=len(observations)):
        total = sum((weights[o][choice] for o, choice in zip(observations, rule)), Q(0))
        best = total if best is None or total > best else best
    return best


def test_selection_value_matches_exhaustive_rule_search():
    kernels = {k: credit_channel(k, 2) for k in CREDIT_KINDS}
    types = {"a": {"11": Q(1, 2), "10": Q(1, 4), "00": Q(1, 4)},
             "b": {"01": Q(1, 2), "00": Q(1, 2)}}
    prior, utility = {"a": Q(1, 3), "b": Q(2, 3)}, {"a": Q(1), "b": Q(1, 4)}
    for kernel in kernels.values():
        assert selection_value(kernel, types, prior, utility) == _value_by_enumerating_rules(
            kernel, types, prior, utility)


def test_selection_value_rejects_malformed():
    kernel = credit_channel("count", 2)
    good = {"a": {"11": Q(1)}, "b": {"00": Q(1)}}
    with pytest.raises(ValueError):
        selection_value(kernel, good, {"a": Q(1, 2), "b": Q(1, 3)}, {"a": Q(1), "b": Q(0)})
    with pytest.raises(ValueError):
        selection_value(kernel, {"a": {"111": Q(1)}, "b": {"00": Q(1)}},
                        {"a": Q(1, 2), "b": Q(1, 2)}, {"a": Q(1), "b": Q(0)})
    with pytest.raises(ValueError):
        selection_value(kernel, good, {"a": Q(1, 2), "b": Q(1, 2)}, {"a": Q(1)})


def test_training_signal_typing():
    signal = TrainingSignal(16, 4, "item_level", "outcome", "verifier", Q(0), None, True)
    signature = signal.feedback_signature()
    assert signature["operator"] == "Feedback_{train,item_level}"
    assert signature["step_images"] == 2
    assert signature["score_queries_to_reconstruct_one_failure"] == 1 + 4
    with pytest.raises(ValueError):
        TrainingSignal(16, 4, "item_level", "outcome", "verifier", Q(1, 10), None, True)
    with pytest.raises(ValueError):
        TrainingSignal(16, 4, "public", "outcome", "verifier", Q(0), None, True)
    with pytest.raises(ValueError):
        TrainingSignal(16, 4, "item_level", "outcome", "learned", Q(2), None, True)


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 15
    assert report["evidence_status"].startswith("exact_synthetic")
