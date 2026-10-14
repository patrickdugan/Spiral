from functools import lru_cache
from fractions import Fraction as Q
from itertools import permutations, product
from math import ceil

import pytest

from spiral_ln.evaluation_game_feedback import (
    EvalSet, LoopEvent, access_kernel, ceiling_detection_threshold,
    targeted_ceiling_detection_threshold,
)
from spiral_ln.evaluation_feedback_lattice import (
    CategoryFeedbackEvent, all_category_maps, all_partitions, audit_category_ledger,
    below, category_channel, category_counts, category_order_fixture,
    ceiling_cost_fixture, channel_kernel, conditional_hit_probability,
    crossing_error_bound, expected_gain_per_patch, expected_hits_after,
    expected_patches_adaptive, expected_patches_static, expected_score_crossing,
    greedy_schedule, hits_needed, item_level_partition, join, lattice_fixture,
    leak_class, meet, partition_from_kernel, rational_simplex, records, refines,
    render_partition, score_only_partition, sealed_partition, small_set_fixture,
    tv_through, validate_categories, validate_category_counts, validate_partition,
    verify,
)
from spiral_ln.evaluation_feedback_lattice import (
    category_lattice_fixture, greedy_vs_optimal_fixture, intersection_graph,
    intersection_graph_is_forest, join_failure_witness, last_failure_positions_sum,
    optimal_adaptive_value, optimal_first_choices,
)
from spiral_ln.evaluation_feedback_lattice import (
    adaptive_states, first_patch_values, greedy_failures, index_rule_fixture,
    preference_reversals, rate_violations,
)
from spiral_ln.evaluation_feedback_lattice import (
    best_finishers, conjecture_refutations, one_hit_fixture, one_hit_value,
    pair_commutation_check, policy_structure_fixture, two_patch_value,
)
from spiral_ln.evaluation_feedback_lattice import commit_until_hit_fixture, commit_until_hit_value
from spiral_ln.evaluation_feedback_lattice import single_failure_fixture, single_failure_value
from spiral_ln.evaluation_feedback_lattice import (
    commit_boundary_fixture, commit_first_value, first_hit_law, switch_after_miss,
    switch_identity_fixture, two_category_commit_fixture, two_hit_first_choices,
    two_hit_fixture, two_hit_score, two_hit_score_closed_form, two_hit_scores, two_hit_value,
)


# --- two hits in closed form; where committing until a hit stops being optimal --

def _optimal_by_item_sets(categories, hits_needed):
    """Independent optimum: recursion over concrete unpatched item sets, every
    category tried at every step, each unpatched item equally likely."""
    counts = validate_category_counts(categories)
    failed = [frozenset(range(failures)) for _, failures in counts]

    @lru_cache(maxsize=None)
    def value(remaining, left):
        if remaining == 0:
            return Q(0)
        best = None
        for index, items in enumerate(left):
            if not items & failed[index]:
                continue
            expected = Q(1)
            for item in items:
                following = list(left)
                following[index] = items - {item}
                expected += Q(1, len(items)) * value(remaining - (item in failed[index]), tuple(following))
            best = expected if best is None else min(best, expected)
        return best

    return value(hits_needed, tuple(frozenset(range(size)) for size, _ in counts))


def test_first_hit_law_matches_patch_orders_and_has_the_finisher_mean():
    for size in range(1, 9):
        for failures in range(1, size + 1):
            law = first_hit_law(size, failures)
            assert sum(p for _, p in law) == 1
            assert sum(t * p for t, p in law) == Q(size + 1, failures + 1)
    orders = sorted(set(permutations([1] * 2 + [0] * 3)))
    for t, p in first_hit_law(5, 2):
        assert Q(sum(order.index(1) + 1 == t for order in orders), len(orders)) == p
    with pytest.raises(ValueError):
        first_hit_law(3, 0)


def test_two_hit_value_is_the_optimum_and_its_minimizers_the_optimal_first_patches():
    for required, state in adaptive_states(5, 3):
        if required != 2:
            continue
        values = first_patch_values(2, state)
        best = min(values.values())
        assert two_hit_value(state) == best == commit_until_hit_value(state, 2)
        assert set(two_hit_first_choices(state)) == {c for c, v in values.items() if v == best}
    for state in (((2, 1), (3, 2), (4, 2)), ((1, 1), (3, 1), (4, 3)), ((2, 2), (4, 1), (4, 2))):
        assert two_hit_value(state) == _optimal_by_item_sets(state, 2)
    big = ((9, 3), (12, 2), (15, 6), (20, 5))
    assert two_hit_value(big) == optimal_adaptive_value(big, 2)


def test_two_hit_closed_form_matches_the_sum():
    for size in range(1, 11):
        for failures in range(1, size + 1):
            for best_other in [None] + [Q(k, 3) for k in range(1, 31)]:
                if failures == 1 and best_other is None:
                    continue
                assert two_hit_score(size, failures, best_other) == two_hit_score_closed_form(size, failures, best_other)
    assert two_hit_score(4, 2, Q(3, 2)) == Q(37, 12) and two_hit_score(2, 1, Q(5, 3)) == Q(19, 6)
    assert two_hit_score(6, 3, None) == Q(7, 4) + Q(7, 4)  # alone: finisher, then the same finisher in mean


def test_two_hit_scores_reproduce_the_greedy_and_index_witnesses():
    assert two_hit_scores(((2, 1), (4, 2))) == {(2, 1): Q(19, 6), (4, 2): Q(37, 12)}
    # A second (2,1) lowers the first one's best other finisher from 5/3 to 3/2 and reverses the order.
    assert two_hit_scores(((2, 1), (2, 1), (4, 2))) == {(2, 1): Q(3), (4, 2): Q(37, 12)}
    assert two_hit_first_choices(((2, 1), (2, 1), (4, 1), (4, 2))) == ((2, 1),)
    assert two_hit_first_choices(((2, 1), (3, 1), (3, 1), (4, 2))) == ((4, 2),)
    assert two_hit_first_choices(((1, 1), (2, 1), (4, 2))) == ((1, 1), (2, 1))
    assert two_hit_first_choices(((2, 1), (5, 2))) == ((5, 2),)
    assert two_hit_value(((2, 1), (5, 2))) == Q(69, 20)


@pytest.mark.parametrize("args", [(3, 0, None), (3, 1, None), (0, 0, 1), (3, 4, 2), (3.0, 1, 2)])
def test_two_hit_score_rejects_malformed(args):
    with pytest.raises(ValueError):
        two_hit_score(*args)
    with pytest.raises(ValueError):
        two_hit_score_closed_form(*args)


def test_two_hit_value_rejects_too_few_failures():
    with pytest.raises(ValueError):
        two_hit_value(((3, 1), (4, 0)))


def test_switch_identity_holds_and_is_nonnegative_at_two_hits():
    report = switch_identity_fixture(4, 3)
    assert report["identity_failures"] == 0 and report["pairs_checked"] > 1000
    assert report["two_hit_negative_slack"] == 0 and report["two_hit_profitable_switches"] == 0
    assert report["most_negative_slack"] < 0  # beyond two hits the slack can be negative
    assert report["single_failure_first_rows"] > 0 and report["single_failure_delta_above_half"] == 0
    row = switch_after_miss(2, ((2, 1), (4, 2)), (4, 2), (2, 1))
    assert row["identity_holds"] and row["slack"] >= 0
    assert row["commit_first"] == Q(37, 12) and row["commit_second"] == Q(19, 6)
    assert commit_first_value(2, ((2, 1), (4, 2)), (4, 2)) == Q(37, 12)


def test_switch_after_miss_rejects_malformed():
    state = ((2, 1), (4, 2))
    with pytest.raises(ValueError):
        switch_after_miss(2, state, (1, 1), (2, 1))
    with pytest.raises(ValueError):
        switch_after_miss(2, ((2, 2), (4, 2)), (2, 2), (4, 2))
    with pytest.raises(ValueError):
        switch_after_miss(2, state, (4, 2), (4, 2))
    with pytest.raises(ValueError):
        switch_after_miss(0, state, (4, 2), (2, 1))
    with pytest.raises(ValueError):
        commit_first_value(2, state, (3, 1))


def test_commit_until_hit_fails_from_three_hits_on():
    report = commit_boundary_fixture()
    witness = report["three_hit_witness"]
    assert witness["optimal"] == Q(1055429, 205920) and witness["committed"] == Q(351823, 68640)
    assert witness["gap"] == Q(1, 5148) and report["three_hit_witness_holds"]
    assert witness["switch_after_miss"]["slack"] == Q(-2291, 205920)
    assert report["padding_preserves_the_gap"]
    assert [row["hits_needed"] for row in report["padded"]] == [4, 5, 6]
    largest = report["largest_gap_found"]
    assert largest["optimal"] == Q(7477604, 479655) and largest["committed"] == Q(22463159, 1438965)
    assert largest["relative_gap"] == Q(30347, 22432812) > Q(1, 1000)
    assert report["largest_gap_exceeds_one_part_in_a_thousand"]
    grid = commit_until_hit_fixture(6, 3)
    assert all(hits >= 3 for hits, _ in grid["suboptimal_by_hits_needed"])


def test_single_failure_categories_take_the_smallest():
    assert single_failure_value(((3, 1), (5, 1), (4, 1)), 2) == Q(9, 2)
    assert single_failure_value(((3, 1), (5, 1), (4, 1)), 2) == _optimal_by_item_sets(((3, 1), (5, 1), (4, 1)), 2)
    assert single_failure_value(((3, 1),), 0) == 0
    report = single_failure_fixture(6, 4)
    assert report["states"] > 0 and report["closed_form_mismatches"] == 0
    with pytest.raises(ValueError):
        single_failure_value(((3, 2), (4, 1)), 1)
    with pytest.raises(ValueError):
        single_failure_value(((3, 1),), 2)


def test_at_most_two_failures_per_category_commit_is_optimal_on_the_grid():
    capped = adaptive_states(6, 3, max_failures=2)
    assert all(failures <= 2 for _, state in capped for _, failures in state)
    assert len(capped) < len(adaptive_states(6, 3))
    report = commit_until_hit_fixture(7, 3, max_failures=2)
    assert report["commit_until_hit_suboptimal"] == 0
    with pytest.raises(ValueError):
        adaptive_states(4, 2, max_failures=0)


def test_two_categories_commit_until_hit_is_optimal_on_the_grid():
    report = two_category_commit_fixture(6)
    assert report["commit_until_hit_gaps"] == 0
    assert report["optimal_patch_not_optimal_after_its_miss"] == 0
    assert report["negative_switch_slacks"] == 0 and report["switch_slacks_checked"] > 0
    small = two_hit_fixture(4, 3)
    assert small["value_mismatches"] == small["first_choice_mismatches"] == 0
    assert small["closed_form_mismatches"] == 0 and small["larger_states_agree"]


def test_commit_until_hit_bounds_and_witness():
    for required, state in adaptive_states(5, 3):
        committed = commit_until_hit_value(state, required)
        assert committed >= optimal_adaptive_value(state, required)
        if required == 1:
            assert committed == one_hit_value(state)
    state = ((4, 2), (4, 2), (6, 3))
    assert optimal_adaptive_value(state, 4) == Q(763, 120)
    assert commit_until_hit_value(state, 4) == Q(509, 80) > Q(763, 120)
    report = commit_until_hit_fixture(6, 3)
    assert report["one_hit_always_commits"]
    assert report["largest_relative_gap"] < Q(1, 1000)


def test_one_hit_closed_form_matches_the_dynamic_programme():
    for required, state in adaptive_states(6, 3):
        if required != 1:
            continue
        assert optimal_adaptive_value(state, 1) == one_hit_value(state)
        values = first_patch_values(1, state)
        best = min(values.values())
        assert all(values[c] == best for c in best_finishers(state))
    with pytest.raises(ValueError):
        one_hit_value(((3, 0),))
    # The minimum runs over categories with failures: read over every category it would be 2.
    spent = ((1, 0), (10, 1))
    assert one_hit_value(spent) == optimal_adaptive_value(spent, 1) == Q(11, 2)
    assert min(Q(n + 1, f + 1) for n, f in spent) == 2
    assert one_hit_fixture(4, 2)["zero_failure_category_excluded"]["holds"]


def test_one_hit_highest_rate_is_not_the_rule():
    values = first_patch_values(1, ((2, 1), (16, 9)))
    assert values[(2, 1)] == Q(3, 2) < values[(16, 9)] == Q(53, 32)
    assert one_hit_value(((2, 1), (16, 9))) == Q(3, 2) and best_finishers(((2, 1), (16, 9))) == ((2, 1),)
    small = first_patch_values(1, ((2, 1), (7, 4)))
    assert small[(7, 4)] == Q(8, 5) > small[(2, 1)] == Q(3, 2)
    report = one_hit_fixture(6, 3)
    assert report["closed_form_mismatches"] == 0 and report["best_finisher_not_optimal_first"] == 0
    assert report["rate_versus_finisher_witness"]["highest_rate_first_is_worse"]


def test_grid_regularities_fail_beyond_the_grid():
    equal = first_patch_values(2, ((3, 2), (6, 4)))
    assert equal[(3, 2)] == Q(13, 5) < equal[(6, 4)] == Q(121, 45)
    lowest = first_patch_values(3, ((5, 3), (8, 5), (9, 6)))
    assert lowest[(5, 3)] == Q(21, 5)
    assert lowest[(5, 3)] < lowest[(8, 5)] == Q(1675, 392)
    assert lowest[(5, 3)] < lowest[(9, 6)] == Q(443, 105)
    report = conjecture_refutations()
    assert report["equal_rates_larger_first"]["refuted"]
    assert report["lowest_rate_never_uniquely_optimal"]["refuted"]


# --- structure of the optimal first patch ------------------------------------

def test_two_patches_in_different_categories_commute():
    for required, state in adaptive_states(4, 3):
        if required < 2:
            continue
        distinct = sorted(set(state))
        for position, first in enumerate(distinct):
            for second in distinct[position + 1:]:
                forward = two_patch_value(required, state, first, second)
                assert forward == two_patch_value(required, state, second, first)
                assert forward >= optimal_adaptive_value(state, required)
    small = pair_commutation_check(4, 3)
    assert small["violations"] == 0 and small["pairs_checked"] > 0


def test_two_patch_value_rejects_malformed():
    state = ((2, 1), (4, 2))
    with pytest.raises(ValueError):
        two_patch_value(1, state, (2, 1), (4, 2))
    with pytest.raises(ValueError):
        two_patch_value(2, state, (2, 1), (2, 1))
    with pytest.raises(ValueError):
        two_patch_value(2, state, (2, 1), (3, 1))


def test_policy_structure_counts_pinned():
    report = policy_structure_fixture(5, 4)
    assert report["commutation"] == {"pairs_checked": 114835, "violations": 0}
    assert report["optimal_outside_extremal_rules"] == 54
    assert report["equal_rates_largest_not_optimal"] == 4
    assert report["equal_rate_witness"]["state"] == ((2, 1), (2, 1), (4, 2))
    assert report["lowest_of_three_rates_uniquely_optimal"] == 0


# --- no index rule --------------------------------------------------------------

def test_adaptive_states_enumeration():
    states = adaptive_states(2, 2)
    assert len(states) == 20
    assert all(1 <= required <= sum(f for _, f in state) for required, state in states)
    assert all(state == tuple(sorted(state)) for _, state in states)
    with pytest.raises(ValueError):
        adaptive_states(0, 1)
    with pytest.raises(ValueError):
        preference_reversals(2, 2, "everything")


def test_first_patch_values_minimum_is_the_optimum():
    for required, state in adaptive_states(4, 3):
        values = first_patch_values(required, state)
        assert min(values.values()) == optimal_adaptive_value(state, required)
        assert set(values) == set(state)
    assert first_patch_values(0, ((2, 1),)) == {}


def test_preference_reversal_witness_exact():
    # Version 0.6's witness ties: (1,1) is optimal too, so a rule ranking it first is optimal there.
    with_unit = first_patch_values(2, ((1, 1), (2, 1), (4, 2)))
    assert with_unit[(2, 1)] < with_unit[(4, 2)] and with_unit[(1, 1)] == with_unit[(2, 1)] == Q(5, 2)
    assert optimal_first_choices(((1, 1), (2, 1), (4, 2)), 2) == ((1, 1), (2, 1))
    # Corrected witness: each preferred category is the unique optimum.
    doubled = first_patch_values(2, ((2, 1), (2, 1), (4, 2)))
    without = first_patch_values(2, ((2, 1), (4, 2)))
    assert doubled[(2, 1)] == 3 < doubled[(4, 2)] == Q(37, 12)
    assert without[(4, 2)] == Q(37, 12) < without[(2, 1)] == Q(19, 6)
    assert optimal_first_choices(((2, 1), (2, 1), (4, 2)), 2) == ((2, 1),)
    assert optimal_first_choices(((2, 1), (4, 2)), 2) == ((4, 2),)
    report = preference_reversals(4, 3, "own_counts")
    assert report["reversals"] >= report["refuting_pairs"] >= 1
    first = report["first_refuting"]
    assert (first["A"], first["B"], first["hits_needed"], first["context"]) == ((2, 1), (4, 2), 2, ())
    assert first["A_uniquely_optimal_in"] == ((2, 1), (2, 1), (4, 2))


def test_lower_rate_witness_exact_and_absent_at_one_hit():
    values = first_patch_values(2, ((2, 1), (5, 2)))
    assert values[(5, 2)] == Q(69, 20) and values[(2, 1)] == Q(7, 2)
    report = rate_violations(5, 4)
    assert report["violations"] >= 1 and report["min_hits_needed"] >= 2
    for required, state in adaptive_states(4, 3):
        if required == 1:
            values = first_patch_values(1, state)
            top = max(Q(f, n) for n, f in state)
            assert any(Q(c[1], c[0]) == top for c, v in values.items() if v == min(values.values()))


def test_index_rule_fixture_and_greedy_count():
    report = index_rule_fixture()
    assert report["unique_optimum_witness"]["holds"] and report["lower_rate_witness"]["holds"]
    assert report["totals_unique_optimum_witness"]["holds"]
    assert report["totals_unique_optimum_witness"]["same_totals_and_category_count"]
    assert report["version_0_6_witnesses_tie"]["holds"]
    contexts = ("own_counts", "with_totals", "with_totals_and_category_count")
    assert [report[c]["reversals"] for c in contexts] == [30, 125, 120]
    assert [report[c]["refuting_pairs"] for c in contexts] == [8, 18, 12]
    totals = report["with_totals_and_category_count"]["first_refuting"]
    assert totals["context"] == (12, 5, 4)
    assert totals["A_uniquely_optimal_in"] == ((2, 1), (2, 1), (4, 1), (4, 2))
    assert totals["B_uniquely_optimal_in"] == ((2, 1), (3, 1), (3, 1), (4, 2))
    assert report["greedy"]["greedy_suboptimal"] == 131 and report["greedy"]["states"] == 33915
    assert greedy_failures(4, 3) == {"states": 1560, "greedy_suboptimal": 6}


# --- meet preservation and the forest criterion -----------------------------

def _item_components(left, right, items):
    """Connected components of the item graph whose edges join items sharing a
    block of either map: the blocks of the finest common coarsening."""
    adjacency = {i: set() for i in range(items)}
    for block in tuple(left) + tuple(right):
        for i in block:
            adjacency[i] |= set(block)
    seen, components = set(), []
    for start in range(items):
        if start in seen:
            continue
        stack, component = [start], set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency[node])
        seen |= component
        components.append(frozenset(component))
    return frozenset(components)


def _margins(blocks, record):
    return tuple(sum(record[i] == "1" for i in block) for block in blocks)


@pytest.mark.parametrize("items", [3, 4, 5])
def test_meet_of_channels_identifies_equal_component_counts(items):
    maps = all_category_maps(items)
    for left, right in product(maps, repeat=2):
        components = _item_components(left, right, items)
        by_counts = {}
        for record in records(items):
            by_counts.setdefault(_margins(sorted(map(sorted, components)), record), []).append(record)
        expected = validate_partition(by_counts.values(), records(items))
        assert meet(category_channel(left, items), category_channel(right, items)) == expected


@pytest.mark.parametrize("items", [3, 4, 5])
def test_join_preserved_exactly_when_margins_determine_cells(items):
    maps = all_category_maps(items)
    for left, right in product(maps, repeat=2):
        cells = validate_categories(render_partition(join(validate_partition(left, range(items)),
                                                          validate_partition(right, range(items)))), items)
        seen = {}
        determined = True
        for record in records(items):
            key = (_margins(left, record), _margins(right, record))
            value = _margins(cells, record)
            if seen.setdefault(key, value) != value:
                determined = False
        assert determined == intersection_graph_is_forest(left, right, items)
        if not determined:
            witness = join_failure_witness(left, right, items)
            first, second = witness["first"], witness["second"]
            assert first != second
            assert _margins(left, first) == _margins(left, second)
            assert _margins(right, first) == _margins(right, second)
            assert _margins(cells, first) != _margins(cells, second)
        else:
            with pytest.raises(ValueError):
                join_failure_witness(left, right, items)


def test_intersection_graph_edges_are_the_cells():
    rows, cols = ((0, 1), (2, 3)), ((0, 2), (1, 3))
    graph = intersection_graph(rows, cols, 4)
    assert graph["edges"] == ((0, 0), (0, 1), (1, 0), (1, 1))
    assert not intersection_graph_is_forest(rows, cols, 4)
    assert intersection_graph_is_forest(rows, ((0, 1, 2), (3,)), 4)
    report = category_lattice_fixture((4,))[4]
    assert report["non_forest_pairs"] == 6 and report["meet_preserved"] == 225


# --- the optimal adaptive policy --------------------------------------------

def _all_states(items):
    for record in records(items):
        total = record.count("0")
        if total == 0:
            continue
        for categories in all_category_maps(items):
            counts = tuple((len(block), sum(record[i] == "0" for i in block)) for block in categories)
            for required in sorted({1, ceil(Q(total, 2)), total}):
                yield counts, required


def test_optimal_adaptive_value_bounds_and_special_cases():
    for counts, required in _all_states(5):
        optimal = optimal_adaptive_value(counts, required)
        greedy = expected_patches_adaptive(counts, required)
        assert optimal <= greedy <= expected_patches_static(counts, required)
        if required == 1:
            assert optimal == greedy
        if required == sum(failures for _, failures in counts):
            assert optimal == greedy == last_failure_positions_sum(counts)
        assert optimal >= required


def test_four_item_greedy_witness_exact():
    four = ((4, 2), (2, 1))
    assert expected_patches_adaptive(four, 2) == Q(19, 6)
    assert optimal_adaptive_value(four, 2) == Q(37, 12)
    assert optimal_first_choices(four, 2) == ((4, 2),)
    assert optimal_first_choices(four, 0) == ()
    assert optimal_adaptive_value(four, 0) == 0
    with pytest.raises(ValueError):
        optimal_adaptive_value(four, 4)
    with pytest.raises(ValueError):
        optimal_adaptive_value(four, -1)


def test_optimal_adaptive_monotone_along_refinement_small():
    items = 5
    maps = all_category_maps(items)
    parts = {m: validate_partition(m, range(items)) for m in maps}
    patterns = [record for record in records(items) if "0" in record]
    for fine, coarse in product(maps, repeat=2):
        if fine == coarse or not refines(parts[fine], parts[coarse]):
            continue
        for record in patterns:
            total = record.count("0")
            for required in sorted({1, ceil(Q(total, 2)), total}):
                counts_fine = tuple((len(b), sum(record[i] == "0" for i in b)) for b in fine)
                counts_coarse = tuple((len(b), sum(record[i] == "0" for i in b)) for b in coarse)
                assert optimal_adaptive_value(counts_fine, required) <= optimal_adaptive_value(counts_coarse, required)


@pytest.mark.parametrize("items, strict_cases", [(4, 0), (5, 0), (6, 180)])
def test_greedy_vs_optimal_fixture_counts(items, strict_cases):
    report = greedy_vs_optimal_fixture(items)
    assert report["optimal_le_greedy_le_static"]
    assert report["greedy_equals_optimal_for_one_hit"]
    assert report["greedy_equals_optimal_equals_closed_form_for_all_hits"]
    assert report["optimal_monotone_along_refinement"]
    assert report["cases_where_greedy_strictly_worse"] == strict_cases
    assert report["four_item_witness"]["greedy"] > report["four_item_witness"]["optimal"]
    if strict_cases:
        assert report["first_witness"]["counts"] == ((4, 2), (2, 1))


# --- independent brute-force helpers -----------------------------------------

def _mass(distribution, element):
    return distribution.get(element, Q(0))


def _tv_by_block_unions(partition, left, right):
    """TV of the pushforwards as the supremum over unions of blocks."""
    blocks = list(partition)
    best = Q(0)
    for mask in product((0, 1), repeat=len(blocks)):
        union = set().union(*(block for block, keep in zip(blocks, mask) if keep))
        best = max(best, abs(sum(_mass(left, x) - _mass(right, x) for x in union)))
    return best


def _same_block(partition, x, y):
    return any(x in block and y in block for block in partition)


def _refines_by_relation(fine, coarse, elements):
    return all(_same_block(coarse, x, y) for x, y in product(elements, repeat=2)
               if _same_block(fine, x, y))


def _static_by_enumeration(categories, hits_needed):
    """Average first-crossing time over every within-category patch order."""
    counts = validate_category_counts(categories)
    order = greedy_schedule(counts)
    per_category = []
    for index in order:
        size, failures = counts[index]
        items = [1] * failures + [0] * (size - failures)  # 1 marks a failed item
        per_category.append(sorted(set(permutations(items))))
    total, weight = Q(0), 0
    for choice in product(*per_category):
        sequence = [bit for block in choice for bit in block]
        hits, time = 0, None
        for step, bit in enumerate(sequence, start=1):
            hits += bit
            if hits >= hits_needed:
                time = step
                break
        total += 0 if time is None else time
        weight += 1
    return total / weight


def _adaptive_by_enumeration(categories, hits_needed):
    """Recursion over concrete item sets with uniformly random unpatched draws."""
    counts = validate_category_counts(categories)
    failed = []
    unpatched = []
    for size, failures in counts:
        failed.append(frozenset(range(failures)))
        unpatched.append(frozenset(range(size)))

    def value(remaining, left):
        if remaining == 0:
            return Q(0)
        best, choice = None, None
        for index, items in enumerate(left):
            if not items:
                continue
            rate = Q(len(items & failed[index]), len(items))
            key = (rate, -len(items), -index)
            if best is None or key > best:
                best, choice = key, index
        items = left[choice]
        expected = Q(1)
        for item in items:
            nxt = list(left)
            nxt[choice] = items - {item}
            expected += Q(1, len(items)) * value(remaining - (item in failed[choice]), tuple(nxt))
        return expected

    return value(hits_needed, tuple(unpatched))


# --- 1. lattice of channels --------------------------------------------------

def test_partition_counts_are_bell_numbers():
    assert [len(all_partitions(range(n))) for n in (1, 2, 3, 4, 5)] == [1, 2, 5, 15, 52]
    assert len(all_partitions(records(2))) == 15


def test_access_classes_sit_at_bottom_middle_top_for_small_n():
    for items in (1, 2, 3):
        sealed, score, item = sealed_partition(items), score_only_partition(items), item_level_partition(items)
        for access, reference in (("sealed", sealed), ("score_only", score), ("item_level", item)):
            assert partition_from_kernel(access_kernel(access, items)) == reference
        assert below(sealed, score) and below(score, item)
        assert len(sealed) == 1 and len(item) == 2 ** items and len(score) == items + 1


def test_refinement_matches_equivalence_relation_inclusion():
    space = records(2)
    partitions = all_partitions(space)
    for fine, coarse in product(partitions, repeat=2):
        assert refines(fine, coarse) == _refines_by_relation(fine, coarse, space)


def test_tv_through_equals_supremum_over_block_unions():
    space = records(2)
    grid = rational_simplex(space, 3)
    for partition in all_partitions(space):
        for left, right in product(grid, repeat=2):
            assert tv_through(partition, left, right) == _tv_by_block_unions(partition, left, right)


def test_lattice_data_processing_law_and_converse_exhaustive_n2():
    space = records(2)
    partitions = all_partitions(space)
    assert len(partitions) == 15
    grid = rational_simplex(space, 3)
    pairs = list(product(grid, repeat=2))
    table = {p: [_tv_by_block_unions(p, a, b) for a, b in pairs] for p in partitions}
    comparable = 0
    for p, q in product(partitions, repeat=2):
        if _refines_by_relation(q, p, space):
            comparable += 1
            assert all(x <= y for x, y in zip(table[p], table[q]))
        else:
            assert any(x > y for x, y in zip(table[p], table[q]))
    assert comparable > 15


def test_join_and_meet_are_lattice_bounds_and_bound_tv():
    space = records(2)
    partitions = all_partitions(space)
    grid = rational_simplex(space, 2)
    pairs = list(product(grid, repeat=2))
    table = {p: [tv_through(p, a, b) for a, b in pairs] for p in partitions}
    for p, q in product(partitions, repeat=2):
        upper, lower = join(p, q), meet(p, q)
        assert upper in table and lower in table
        assert refines(upper, p) and refines(upper, q)
        assert refines(p, lower) and refines(q, lower)
        for r in partitions:
            if refines(r, p) and refines(r, q):
                assert refines(r, upper)
            if refines(p, r) and refines(q, r):
                assert refines(lower, r)
        for tu, tl, tp, tq in zip(table[upper], table[lower], table[p], table[q]):
            assert tu >= max(tp, tq) and tl <= min(tp, tq)


def test_lattice_fixture_reports_every_flag():
    fixture = lattice_fixture(2, 2)
    assert fixture["bell_number"] == 15 and fixture["grid_size"] == 10
    assert fixture["law_holds_on_every_comparable_pair"]
    assert fixture["domination_fails_on_every_noncomparable_pair"]
    assert fixture["join_and_meet_satisfy_lattice_definitions"] and fixture["join_meet_tv_bounds_hold"]
    assert fixture["sealed_is_bottom"] and fixture["item_level_is_top"]
    assert fixture["score_only_strictly_between"] and fixture["existing_access_kernels_match"]
    assert fixture["ordered_pairs_below"] + fixture["ordered_pairs_not_below"] == 225


@pytest.mark.parametrize("blocks, elements", [
    ([["00", "01"], ["01", "10", "11"]], records(2)),
    ([["00", "01"]], records(2)),
    ([[], ["00", "01", "10", "11"]], records(2)),
    ([], records(2)),
    ([["00", "01", "10", "11", "x"]], records(2)),
])
def test_malformed_partitions_rejected(blocks, elements):
    with pytest.raises(ValueError):
        validate_partition(blocks, elements)


def test_mismatched_ground_sets_and_bad_kernels_rejected():
    with pytest.raises(ValueError):
        refines(sealed_partition(2), sealed_partition(3))
    with pytest.raises(ValueError):
        join(sealed_partition(2), sealed_partition(3))
    with pytest.raises(ValueError):
        meet(sealed_partition(2), sealed_partition(3))
    with pytest.raises(ValueError):
        partition_from_kernel({"0": {"a": Q(1, 2), "b": Q(1, 2)}, "1": {"a": Q(1)}})
    with pytest.raises(ValueError):
        records(0)
    with pytest.raises(ValueError):
        rational_simplex(("a",), 0)
    assert channel_kernel(sealed_partition(1)) == {"0": {"0|1": Q(1)}, "1": {"0|1": Q(1)}}


# --- 2. category leakage -----------------------------------------------------

def test_category_endpoints_are_score_only_and_item_level():
    for items in (1, 2, 3, 4):
        assert category_channel([range(items)], items) == score_only_partition(items)
        assert category_channel([[i] for i in range(items)], items) == item_level_partition(items)


def test_category_map_is_order_embedding_by_brute_force():
    for items in (3, 4):
        maps = all_category_maps(items)
        assert len(maps) == {3: 5, 4: 15}[items]
        space = records(items)
        channels = {m: category_channel(m, items) for m in maps}
        parts = {m: validate_partition(m, range(items)) for m in maps}
        for a, b in product(maps, repeat=2):
            assert (_refines_by_relation(channels[a], channels[b], space)
                    == _refines_by_relation(parts[a], parts[b], range(items)))
        assert len(set(channels.values())) == len(maps)


def test_two_incomparable_category_maps_separate_different_pairs():
    channel_a = category_channel(((0, 1), (2,)), 3)
    channel_b = category_channel(((0,), (1, 2)), 3)
    assert not refines(channel_a, channel_b) and not refines(channel_b, channel_a)
    fail0, fail1, fail2 = {"011": Q(1)}, {"101": Q(1)}, {"110": Q(1)}
    assert tv_through(channel_a, fail0, fail1) == 0 and tv_through(channel_b, fail0, fail1) == 1
    assert tv_through(channel_a, fail1, fail2) == 1 and tv_through(channel_b, fail1, fail2) == 0
    fixture = category_order_fixture()["incomparable_pair"]
    assert fixture["neither_refines"] and fixture["A_separates_second_pair_only"]
    assert fixture["B_separates_first_pair_only"]


def test_separate_category_leaks_are_coarser_than_the_refined_leak():
    rows, cols = category_channel(((0, 1), (2, 3)), 4), category_channel(((0, 2), (1, 3)), 4)
    joint = join(rows, cols)
    assert refines(item_level_partition(4), joint) and joint != item_level_partition(4)
    assert _same_block(joint, "1001", "0110")
    assert tv_through(joint, {"1001": Q(1)}, {"0110": Q(1)}) == 0
    fixture = category_order_fixture()
    assert fixture["join_failure"]["joint_leak_strictly_coarser"]
    assert all(fixture["order_embedding_exhaustive"].values())
    assert fixture["join_preserved_pairs"][4] < fixture["ordered_pairs"][4]


@pytest.mark.parametrize("categories, items", [
    (((0, 1), (1, 2)), 3), (((0, 1),), 3), (((0, 1, 2, 3),), 3), (((0, True), (2,)), 3),
    (((0, 1, 2),), 0), (((0, 1, 2),), 3.0),
])
def test_malformed_category_maps_rejected(categories, items):
    with pytest.raises(ValueError):
        validate_categories(categories, items)


def test_category_counts_reads_failures_per_block():
    assert category_counts(((0, 1), (2, 3), (4, 5)), "011000") == ((2, 1), (2, 1), (2, 2))
    assert category_counts(((0, 1), (2, 3), (4, 5)), "011001") == ((2, 1), (2, 1), (2, 1))
    with pytest.raises(ValueError):
        category_counts(((0, 1),), "0x")
    with pytest.raises(ValueError):
        category_counts(((0, 1),), "011")


# --- 3. cost of a leak -------------------------------------------------------

def test_conditional_hit_probability_depletes_but_unconditional_gain_does_not():
    assert conditional_hit_probability(4, 2, 0, 0) == Q(1, 2)
    assert conditional_hit_probability(4, 2, 1, 1) == Q(1, 3)
    assert conditional_hit_probability(4, 2, 1, 0) == Q(2, 3)
    assert conditional_hit_probability(4, 2, 2, 2) == 0
    for size, failures in ((2, 1), (3, 2), (4, 1), (4, 3), (5, 2)):
        items = [1] * failures + [0] * (size - failures)
        orders = sorted(set(permutations(items)))
        for position in range(size):
            assert Q(sum(order[position] for order in orders), len(orders)) == Q(failures, size)
    assert expected_gain_per_patch(((2, 1), (3, 3), (4, 0))) == (Q(1),) * 3 + (Q(1, 2),) * 2 + (Q(0),) * 4


@pytest.mark.parametrize("args", [(4, 2, 4, 2), (4, 2, 1, 2), (4, 2, 3, 0), (4, 5, 0, 0),
                                  (0, 0, 0, 0), (4, 2, 0, -1), (4.0, 2, 0, 0)])
def test_conditional_hit_probability_rejects_inconsistent_histories(args):
    with pytest.raises(ValueError):
        conditional_hit_probability(*args)


def test_greedy_schedule_maximizes_expected_hits_at_every_patch_count():
    categories = ((3, 1), (2, 2), (4, 1), (1, 0))
    assert greedy_schedule(categories) == (1, 0, 2, 3)
    sizes = [size for size, _ in categories]
    for patches in range(sum(sizes) + 1):
        best = max(
            sum(Q(m * failures, size) for m, (size, failures) in zip(allocation, categories))
            for allocation in product(*(range(size + 1) for size in sizes))
            if sum(allocation) == patches)
        assert expected_hits_after(categories, patches) == best
    assert expected_hits_after(categories, Q(5, 2)) == 2 + Q(1, 2) * Q(1, 3)
    with pytest.raises(ValueError):
        expected_hits_after(categories, 11)


def test_fixture_thresholds_recover_the_existing_module():
    need = hits_needed(50, Q(4, 5), Q(1, 10))
    assert need["failures"] == 13 and need["hits_needed"] == 8 and need["hits_needed_integer"] == 8
    assert expected_score_crossing(((50, 13),), 8) / 50 == Q(8, 13) == ceiling_detection_threshold(Q(4, 5), Q(1, 10))
    singles = ((1, 0),) * 37 + ((1, 1),) * 13
    assert expected_score_crossing(singles, 8) / 50 == Q(4, 25) == targeted_ceiling_detection_threshold(Q(4, 5), Q(1, 10))
    assert expected_patches_static(((50, 13),), 8) == Q(204, 7) == expected_patches_adaptive(((50, 13),), 8)
    assert expected_patches_static(singles, 8) == 8 == expected_patches_adaptive(singles, 8)
    with pytest.raises(ValueError):
        hits_needed(49, Q(4, 5), Q(1, 10))
    with pytest.raises(ValueError):
        hits_needed(0, Q(4, 5), Q(1, 10))


def test_ceiling_cost_chain_values_and_monotonicity():
    fixture = ceiling_cost_fixture()
    shares = [row["crossing_share_of_set"] for row in fixture["chain"]]
    assert shares == [Q(8, 13), Q(7, 12), Q(8, 15), Q(1, 2), Q(8, 25), Q(4, 25)]
    statics = [row["expected_patches_static"] for row in fixture["chain"]]
    # 10 blocks of 5: three rate-2/5 blocks give 6 hits in 15 patches, a whole
    # rate-1/5 block gives the seventh in 5 more, and the eighth needs 6/2 on
    # average in the next: 15 + 5 + 3 = 23 (the crossing sits at 15 + 5 + 5).
    assert statics == [Q(204, 7), Q(201, 7), Q(51, 2), Q(23), Q(31, 2), Q(8)]
    assert fixture["crossing_nonincreasing_along_chain"]
    assert fixture["static_nonincreasing_along_chain"] and fixture["adaptive_nonincreasing_along_chain"]
    assert fixture["adaptive_at_most_static_along_chain"] and fixture["crossing_at_least_static_along_chain"]
    assert fixture["chain"][0]["expected_patches_adaptive"] == Q(204, 7)
    assert fixture["chain"][-1]["expected_patches_adaptive"] == 8


def _all_cases(categories):
    sizes = [size for size, _ in categories]
    for pattern in product(*(range(size + 1) for size in sizes)):
        counts = tuple(zip(sizes, pattern))
        total = sum(pattern)
        for required in range(1, total + 1):
            yield counts, required


def test_static_expectation_matches_enumeration_over_patch_orders():
    for base in (((2, 0), (2, 0), (2, 0)), ((3, 0), (2, 0), (1, 0)), ((4, 0), (2, 0))):
        for counts, required in _all_cases(base):
            assert expected_patches_static(counts, required) == _static_by_enumeration(counts, required)


def test_adaptive_expectation_matches_enumeration_over_item_sets():
    for base in (((2, 0), (2, 0), (2, 0)), ((3, 0), (2, 0), (1, 0)), ((4, 0), (2, 0))):
        for counts, required in _all_cases(base):
            adaptive = expected_patches_adaptive(counts, required)
            assert adaptive == _adaptive_by_enumeration(counts, required)
            assert adaptive <= expected_patches_static(counts, required)


def test_crossing_error_identity_and_bound():
    for counts, required in _all_cases(((3, 0), (3, 0), (2, 0))):
        bound = crossing_error_bound(counts, required)
        assert bound["error"] == bound["closed_form_error"]
        assert 0 <= bound["error"] < bound["bound"]
        assert bound["expected_score_crossing"] >= bound["expected_patches_static"]
    assert crossing_error_bound(((4, 2),), 0)["error"] == 0
    assert expected_score_crossing(((4, 2),), 0) == 0 == expected_patches_static(((4, 2),), 0)


def test_crossing_is_monotone_along_refinement_over_all_partitions_of_six():
    items = 6
    maps = all_category_maps(items)
    assert len(maps) == 203
    parts = {m: validate_partition(m, range(items)) for m in maps}
    patterns = [record for record in records(items) if "0" in record]
    crossing = {m: [expected_score_crossing(category_counts(m, r), r.count("0")) for r in patterns]
                for m in maps}
    refining = 0
    for fine, coarse in product(maps, repeat=2):
        if fine != coarse and refines(parts[fine], parts[coarse]):
            refining += 1
            assert all(a <= b for a, b in zip(crossing[fine], crossing[coarse]))
    assert refining > 203
    one_block = maps[0] if len(maps[0]) == 1 else next(m for m in maps if len(m) == 1)
    singles = next(m for m in maps if len(m) == items)
    for record, value in zip(patterns, crossing[one_block]):
        failures = record.count("0")
        assert value == items
        assert crossing[singles][patterns.index(record)] == failures


def test_static_expectation_is_not_monotone_but_crossing_and_adaptive_are_on_the_witness():
    coarse, fine = ((4, 2),), ((2, 1), (2, 1))
    assert expected_patches_static(coarse, 2) == Q(10, 3) < expected_patches_static(fine, 2) == Q(7, 2)
    assert expected_score_crossing(coarse, 2) == 4 == expected_score_crossing(fine, 2)
    assert expected_patches_adaptive(coarse, 2) == Q(10, 3) > expected_patches_adaptive(fine, 2) == 3
    assert _static_by_enumeration(fine, 2) == Q(7, 2)
    assert _adaptive_by_enumeration(fine, 2) == 3


def test_small_set_fixture_flags():
    fixture = small_set_fixture()
    assert fixture["category_maps"] == 203 and fixture["patterns"] == 63
    assert fixture["error_identity_and_bound_hold"] and fixture["adaptive_at_most_static"]
    assert fixture["crossing_monotone_along_refinement"]
    assert fixture["four_item_static_refinement_costs_more"]
    assert fixture["four_item_crossing_and_adaptive_do_not"]
    assert fixture["static_monotone_along_refinement"] is False
    assert fixture["static_witness"] is not None


@pytest.mark.parametrize("categories, required", [
    (((4, 2),), 3), (((4, 2),), -1), (((4, 5),), 1), (((0, 0),), 0), ((), 0), (((4, 2),), 1.5),
    (((4, 2, 1),), 1), (((4.0, 2),), 1), (((4, True),), 1),
])
def test_malformed_cost_inputs_rejected(categories, required):
    with pytest.raises((ValueError, TypeError)):
        expected_patches_static(categories, required)
    with pytest.raises((ValueError, TypeError)):
        expected_patches_adaptive(categories, required)


# --- 4. ledger wrapper -------------------------------------------------------

def _sets():
    return (EvalSet("S", "selection", "score_only", ("s0", "s1", "s2", "s3")),
            EvalSet("R", "readout", "sealed", ("r0", "r1", "r2", "r3")))


def test_leak_class_positions():
    assert leak_class((("a", "b", "c"),), ("a", "b", "c")) == "score_only"
    assert leak_class((("a",), ("b",), ("c",)), ("a", "b", "c")) == "item_level"
    assert leak_class((("a", "b"), ("c",)), ("a", "b", "c")) == "category"
    with pytest.raises(ValueError):
        leak_class((("a", "b"),), ("a", "b", "c"))


def test_category_ledger_records_partition_and_translates_for_base_ledger():
    events = (CategoryFeedbackEvent(1, "S", (("s0", "s1", "s2", "s3"),)),
              CategoryFeedbackEvent(2, "S", (("s0", "s1"), ("s2", "s3"))),
              LoopEvent(3, "R", "readout"))
    report = audit_category_ledger(_sets(), events, 2, Q(1, 2))
    assert report["declarations_respected"]
    assert report["selection"]["S"]["score_queries"] == 3 and report["selection"]["S"]["patches"] == 0
    rows = report["category_feedback"]["S"]["events"]
    assert [row["leak_class"] for row in rows] == ["score_only", "category"]
    assert rows[1]["partition"] == (("s0", "s1"), ("s2", "s3")) and rows[1]["within_declared_categories"] is None
    assert report["readout"]["R"]["endpoint_status"] == "evaluable"


def test_singleton_blocks_count_as_item_feedback_and_breach_score_only():
    events = (CategoryFeedbackEvent(1, "S", (("s0",), ("s1", "s2", "s3"))),)
    report = audit_category_ledger(_sets(), events, 2, Q(1, 2))
    entry = report["selection"]["S"]
    assert entry["patches"] == 1 and entry["score_queries"] == 1
    assert "exceeds declared score_only access" in entry["breaches"][0]
    assert not report["declarations_respected"]


def test_declared_categories_bound_the_leak_in_the_lattice():
    declared = {"S": (("s0", "s1"), ("s2", "s3"))}
    fine = CategoryFeedbackEvent(1, "S", (("s0",), ("s1",), ("s2", "s3")))
    coarse = CategoryFeedbackEvent(1, "S", (("s0", "s1", "s2", "s3"),))
    sets = (EvalSet("S", "selection", "item_level", ("s0", "s1", "s2", "s3")), _sets()[1])
    ok = audit_category_ledger(sets, (coarse,), 2, Q(1), declared)
    assert ok["declarations_respected"] and ok["category_feedback"]["S"]["events"][0]["within_declared_categories"]
    bad = audit_category_ledger(sets, (fine,), 2, Q(1), declared)
    assert not bad["declarations_respected"]
    assert bad["category_feedback"]["S"]["breaches"] == ("category feedback finer than declared categories at generation 1",)
    assert bad["category_feedback"]["S"]["declared_categories"] == (("s0", "s1"), ("s2", "s3"))


def test_category_feedback_on_readout_set_is_a_breach():
    events = (CategoryFeedbackEvent(1, "R", (("r0", "r1"), ("r2", "r3"))),)
    report = audit_category_ledger(_sets(), events, 2, Q(1, 2))
    assert report["readout"]["R"]["endpoint_status"] == "not_evaluated"


@pytest.mark.parametrize("events, declared, message", [
    ((CategoryFeedbackEvent(1, "X", (("s0",),)),), None, "invalid category feedback event"),
    ((CategoryFeedbackEvent(-1, "S", (("s0", "s1", "s2", "s3"),)),), None, "invalid category feedback event"),
    ((CategoryFeedbackEvent(1, "S", (("s0", "s1"),)),), None, "cover exactly"),
    ((CategoryFeedbackEvent(1, "S", (("s0", "s1"), ("s1", "s2", "s3"))),), None, "disjoint"),
    ((LoopEvent(2, "S", "score_query"), CategoryFeedbackEvent(1, "S", (("s0", "s1", "s2", "s3"),))), None, "ordered by generation"),
    ((), {"Z": (("s0",),)}, "unknown set"),
    ((), {"S": (("s0", "s1"),)}, "cover exactly"),
    (("not an event",), None, "invalid category feedback event"),
])
def test_malformed_category_ledgers_raise(events, declared, message):
    with pytest.raises(ValueError, match=message):
        audit_category_ledger(_sets(), events, 2, Q(1, 2), declared)


def test_verify_reports_every_check_passing():
    report = verify()
    assert report["all_passed"] and len(report["checks"]) == 48
    assert report["evidence_status"].startswith("exact_synthetic")
    assert render_partition(sealed_partition(1)) == (("0", "1"),)
