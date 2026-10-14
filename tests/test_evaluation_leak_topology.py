import json
import random
from fractions import Fraction as Q
from itertools import product
from math import comb
from pathlib import Path

import pytest

from spiral_ln.evaluation_feedback_lattice import (
    all_category_maps, category_channel, intersection_graph_is_forest, item_level_partition, join,
)
from spiral_ln.evaluation_leak_topology import (
    COUNTEREXAMPLE_ONE, COUNTEREXAMPLE_ZERO, NONLOCAL_SUPPORT, WITNESS_GRAPHS, affine_dimension,
    asymptotic_fixture, balanced_facets, block_fixture, cell_counts, cell_graph, cell_support,
    category_maps_from_support, collapsed_dimension, collision_ratio, completion_report,
    confusion_direct, confusion_lattice_sum, connected_by_moves, cost_fixture, cotree_identity,
    counterexample_fixture, cycle_graph, cycle_rank, decimal_string, determinant, difference_law,
    downsets, ehrhart_counts, ehrhart_fixture, fibre_dimension, fibre_dimension_k,
    full_support_fixture, full_support_formula, fundamental_cycles, graph_from_sizes, guessing,
    homological_fibre, homological_span, homotopy_profile, integer_fibres, integrality_fixture,
    leak_costs, link_formula, margin_matrix, margins_of, matrix_tree_count, maximal_spanning_forests,
    natural_family, nerve_incidence_corank, nonlocal_fixture, nullspace, pattern_fixture,
    primitive_integer_vector, projection_fixture, projection_sequence, rank, rank_by_fractions,
    reduce_pattern, reduced_betti, rp2_fixture, separate_faces, separate_fibre, signed_incidence,
    simple_cycles, single_nonface_facets, supports_in_grid, two_map_fixture, uniform_pair_counts,
    verify, weighted_forest_count,
)

C4_ROWS, C4_COLUMNS = ((0, 1), (2, 3)), ((0, 2), (1, 3))


def _graph(name):
    return graph_from_sizes(*WITNESS_GRAPHS[name])


# --- 0. exact linear algebra -------------------------------------------------

def test_bareiss_rank_matches_fraction_elimination():
    rng = random.Random(17)
    for _ in range(300):
        rows, columns = rng.randint(1, 6), rng.randint(1, 6)
        matrix = [[rng.randint(-4, 4) for _ in range(columns)] for _ in range(rows)]
        if rows > 2:
            matrix[-1] = [2 * a - b for a, b in zip(matrix[0], matrix[1])]
        assert rank(matrix) == rank_by_fractions(matrix)
    assert rank([[Q(1, 2), Q(1, 3)], [Q(3, 2), 1]]) == 1
    assert rank([]) == 0 and rank([[0, 0], [0, 0]]) == 0


def test_rank_rejects_ragged_rows():
    with pytest.raises(ValueError):
        rank([[1, 2], [1]])


def test_nullspace_is_a_kernel_basis():
    matrix = [[1, 1, 0, 0], [0, 0, 1, 1], [1, 0, 1, 0], [0, 1, 0, 1]]
    basis = nullspace(matrix, 4)
    assert len(basis) == 4 - rank(matrix) == 1
    assert all(sum(a * b for a, b in zip(row, vector)) == 0 for row in matrix for vector in basis)


def test_primitive_vector_and_determinant():
    assert primitive_integer_vector((Q(-1, 2), 1, Q(-1, 2))) == (1, -2, 1)
    with pytest.raises(ValueError):
        primitive_integer_vector((0, 0))
    assert determinant([[2, 1], [7, 4]]) == 1
    assert determinant([[1, 2], [2, 4]]) == 0
    assert determinant([[0, 1], [1, 0]]) == -1


def test_decimal_string_truncates_exactly():
    assert decimal_string(Q(1, 3)) == "0.33333333"
    assert decimal_string(Q(-7, 4), 3) == "-1.750"
    assert decimal_string(Q(22, 7), 2) == "3.14"


# --- 1. two maps ---------------------------------------------------------------

def test_four_cycle_fibre_is_one_dimensional():
    graph = cell_graph(C4_ROWS, C4_COLUMNS, 4)
    assert graph["sizes"] == (1, 1, 1, 1)
    assert cycle_rank(graph) == 1 == fibre_dimension(C4_ROWS, C4_COLUMNS, 4)
    ((edge, vector),) = fundamental_cycles(graph)
    assert sorted(vector) == [-1, -1, 1, 1] and vector[edge] == 1
    assert not any(margins_of(graph, vector))


def test_fibre_dimension_is_cycle_rank_exhaustively_on_four_items():
    for left, right in product(all_category_maps(4), repeat=2):
        graph = cell_graph(left, right, 4)
        assert fibre_dimension(left, right, 4) == cycle_rank(graph)
        assert (cycle_rank(graph) == 0) == intersection_graph_is_forest(left, right, 4)


def test_unsigned_incidence_is_a_sign_twist_of_the_signed_one():
    graph = _graph("K23_unit_cycle_rank_2")
    unsigned, signed = margin_matrix(graph), signed_incidence(graph)
    rows = len(graph["rows"])
    for v, (u_row, s_row) in enumerate(zip(unsigned, signed)):
        sign = 1 if v < rows else -1
        assert tuple(sign * value for value in s_row) == u_row
    assert rank(signed) == rank(unsigned) == len(unsigned) - 1


def test_fundamental_cycles_are_unit_on_their_own_edge():
    graph = _graph("K23_unit_cycle_rank_2")
    cycles = fundamental_cycles(graph)
    off = [f for f, _ in cycles]
    assert len(cycles) == cycle_rank(graph) == 2
    for f, vector in cycles:
        assert all(vector[g] == (1 if g == f else 0) for g in off)
        assert set(vector) <= {-1, 0, 1} and not any(margins_of(graph, vector))


def test_simple_cycle_counts():
    assert len(simple_cycles(_graph("K23_unit_cycle_rank_2"))) == 3
    k33 = graph_from_sizes(tuple((a, b) for a in range(3) for b in range(3)), (1,) * 9)
    assert len(simple_cycles(k33)) == 9 + 6
    assert simple_cycles(_graph("C4_unit_with_pendant_path")) == ((1, -1, 0, -1, 1, 0),)


def test_integer_fibres_attain_cycle_rank():
    graph = _graph("K23_unit_cycle_rank_2")
    fibres = integer_fibres(graph)
    assert max(affine_dimension(f) for f in fibres.values()) == 2
    assert all(affine_dimension(f) <= 2 for f in fibres.values())
    assert sum(len(f) for f in fibres.values()) == 2 ** 6


def test_fibres_need_the_cycle_moves():
    graph = cell_graph(C4_ROWS, C4_COLUMNS, 4)
    fibre = integer_fibres(graph)[(1, 1, 1, 1)]
    assert len(fibre) == 2
    assert not connected_by_moves(fibre, (), graph["sizes"])
    assert connected_by_moves(fibre, simple_cycles(graph), graph["sizes"])


def test_two_map_fixture_small():
    report = two_map_fixture(record_sizes=(3, 4), rank_sizes=(5,))
    for row in report.values():
        pairs = row["ordered_pairs"]
        assert all(value == pairs for key, value in row.items()
                   if key not in ("ordered_pairs", "pairs_by_cycle_rank"))
    assert report["4"]["pairs_by_cycle_rank"] == {0: 219, 1: 6}


def test_cell_counts_and_margins_of_a_record():
    graph = cell_graph(C4_ROWS, C4_COLUMNS, 4)
    assert cell_counts(graph, "1001") == (1, 0, 0, 1)
    assert cell_counts(graph, "0110") == (0, 1, 1, 0)
    assert margins_of(graph, (1, 0, 0, 1)) == margins_of(graph, (0, 1, 1, 0)) == (1, 1, 1, 1)


def test_graph_from_sizes_validation():
    with pytest.raises(ValueError):
        graph_from_sizes(((0, 0), (0, 0)), (1, 1))
    with pytest.raises(ValueError):
        graph_from_sizes(((0, 0), (1, 1)), (1, 0))
    with pytest.raises(ValueError):
        graph_from_sizes(((0, 0), (2, 1)), (1, 1))
    graph = graph_from_sizes(((0, 0), (0, 1), (1, 0), (1, 1)), (3, 1, 1, 1))
    assert graph["items"] == 6 and graph["sizes"] == (3, 1, 1, 1)


# --- 2. cost of the cycles -----------------------------------------------------

def test_completion_needs_cycle_rank_cells():
    four = completion_report(cell_graph(C4_ROWS, C4_COLUMNS, 4))
    assert four == {"agrees_with_forest_criterion": True, "minimum_size": 1, "minimum_sets": 4}
    k23 = completion_report(_graph("K23_unit_cycle_rank_2"))
    assert k23["agrees_with_forest_criterion"] and k23["minimum_size"] == 2 and k23["minimum_sets"] == 12
    forest = completion_report(graph_from_sizes(((0, 0), (0, 1), (1, 1)), (1, 2, 1)))
    assert forest["minimum_size"] == 0 and forest["minimum_sets"] == 1


def test_matrix_tree_counts():
    k33 = graph_from_sizes(tuple((a, b) for a in range(3) for b in range(3)), (1,) * 9)
    assert matrix_tree_count(k33) == len(maximal_spanning_forests(k33)) == 81
    assert matrix_tree_count(_graph("K23_unit_cycle_rank_2")) == 12
    assert matrix_tree_count(_graph("C6_unit")) == 6
    assert matrix_tree_count(_graph("two_disjoint_C4_cycle_rank_2")) == 16


def test_difference_law_and_vandermonde():
    for size in range(1, 6):
        law = difference_law(size, Q(1, 2))
        assert sum(law.values()) == 1
        assert all(law[k] == law[-k] == Q(comb(2 * size, size + k), 4 ** size) for k in range(size + 1))
    assert sum(difference_law(3, Q(2, 7)).values()) == 1


def test_confusion_lattice_sum_matches_direct_count():
    for name in ("C4_sizes_3111", "C6_unit", "K23_unit_cycle_rank_2", "C4_unit_with_pendant_path"):
        graph = _graph(name)
        for p in (Q(1, 2), Q(2, 5)):
            lattice, direct = confusion_lattice_sum(graph, p), confusion_direct(graph, p)
            assert lattice["separate"] == direct["separate"] and lattice["joint"] == direct["joint"]
            assert lattice["excess"] > 0


def test_forest_has_no_excess():
    graph = graph_from_sizes(((0, 0), (0, 1), (1, 1)), (2, 1, 3))
    assert confusion_lattice_sum(graph)["excess"] == 0 and collision_ratio(graph) == 1
    assert guessing(graph)["cell_error"] == 0 and guessing(graph)["record_success_gap"] == 0


def test_four_cycle_costs_exactly():
    graph = cell_graph(C4_ROWS, C4_COLUMNS, 4)
    assert uniform_pair_counts(graph) == {"separate": 18, "joint": 16}
    assert collision_ratio(graph) == Q(9, 8)
    costs = leak_costs(graph)
    assert costs["merged_classes"] == 1 and costs["confusion_excess"] == Q(1, 128)
    assert costs["cell_guess_error"] == Q(1, 16) == costs["record_guess_gap"]


def test_witnesses_with_cycle_rank_one_differ():
    names = ("C6_unit", "C4_sizes_3111", "C4_sizes_2211_same_row", "C4_unit_with_pendant_path")
    costs = {name: leak_costs(_graph(name)) for name in names}
    assert all(c["cycle_rank"] == 1 == c["fibre_dimension"] == c["minimum_completion_size"] for c in costs.values())
    assert costs["C6_unit"]["collision_ratio"] == Q(33, 32)
    assert costs["C4_sizes_3111"]["collision_ratio"] == Q(19, 16)
    assert costs["C4_sizes_2211_same_row"]["collision_ratio"] == Q(11, 9)
    assert costs["C6_unit"]["minimum_completions"] == 6 and costs["C4_sizes_3111"]["minimum_completions"] == 4
    assert len({c["confusion_excess"] for c in costs.values()}) == 4


def test_cotree_identity_with_arbitrary_weights():
    k33 = graph_from_sizes(tuple((a, b) for a in range(3) for b in range(3)), (1,) * 9)
    weights = tuple(Q(e + 1, 3) for e in range(9))
    assert cotree_identity(k33, weights)["holds"]
    assert weighted_forest_count(_graph("C4_unit_four_items"), (1, 2, 1, 2)) == 12


def test_block_fixture():
    report = block_fixture()
    assert all(value for key, value in report.items() if isinstance(value, bool))
    assert report["unit_cycle_ratios"]["8"] == Q(129, 128)


def test_cycle_graph():
    assert cycle_rank(cycle_graph(8)) == 1 and len(cycle_graph(8)["edges"]) == 8
    with pytest.raises(ValueError):
        cycle_graph(5)


def test_asymptotic_trend_small():
    edges = WITNESS_GRAPHS["C4_unit_four_items"][0]
    report = asymptotic_fixture({"C4": (edges, (1, 1, 1, 1), (4, 8, 16))})["C4"]
    assert report["decreasing"] and report["above_pi_power"] and report["determinant_identity"]
    assert report["normalized_values_decimal"][0].startswith("3.4996")


def test_ehrhart_counts_are_polynomials():
    assert ehrhart_counts(_graph("C4_unit_four_items"), range(4)) == (1, 3, 5, 7)
    assert ehrhart_counts(_graph("K23_unit_cycle_rank_2"), range(5)) == tuple(3 * n * n + 3 * n + 1 for n in range(5))
    assert all(row["degree_is_cycle_rank"] for row in ehrhart_fixture().values())


def test_cost_fixture_identities_on_four_items():
    report = cost_fixture(sizes=(3, 4))
    identity = report["identities"]
    assert all(value == identity["pairs"] for value in identity.values())


# --- 3. three or more maps ------------------------------------------------------

def test_support_round_trip():
    maps, items = category_maps_from_support(NONLOCAL_SUPPORT, (1, 2, 1, 1, 1))
    assert items == 6
    assert cell_support(maps, items) == {cell: size for cell, size in zip(sorted(NONLOCAL_SUPPORT), (1, 2, 1, 1, 1))}
    with pytest.raises(ValueError):
        category_maps_from_support(((0, 0), (0, 0, 1)))
    with pytest.raises(ValueError):
        category_maps_from_support(((0, 0),), (0,))


def test_k_map_fibre_reduces_to_two_maps():
    for left, right in product(all_category_maps(4), repeat=2):
        cells = list(cell_support((left, right), 4))
        assert fibre_dimension_k(cells, separate_faces(2)) == fibre_dimension(left, right, 4)


def test_reduced_betti_numbers():
    assert reduced_betti([(0,)]) == (0,)
    assert reduced_betti([(0,), (1,)]) == (1,)
    assert reduced_betti([(0, 1), (1, 2), (2, 3), (0, 3)]) == (0, 1)
    octahedron = balanced_facets(tuple(product(range(2), repeat=3)))
    assert reduced_betti(octahedron) == (0, 0, 1)
    with pytest.raises(ValueError):
        reduced_betti([])


def test_link_formula_on_the_full_cube():
    cube = tuple(product(range(2), repeat=3))
    assert link_formula(cube, (0, 1, 2)) == 1 == fibre_dimension_k(cube, ((0, 1), (0, 2), (1, 2)))
    assert link_formula(cube, (1, 2)) == 2 == fibre_dimension_k(cube, ((0, 1), (0, 2)))
    assert link_formula(cube, (2,)) == 4 == fibre_dimension_k(cube, ((0, 1),))
    assert single_nonface_facets(3, (1, 2)) == ((0, 1), (0, 2))
    with pytest.raises(ValueError):
        single_nonface_facets(3, ())


def test_downsets_and_classification():
    assert [len(downsets(k)) for k in (2, 3, 4)] == [5, 19, 167]
    assert reduce_pattern(3, ((0,), (1,), (2,)))["kind"] == "other"
    merged = reduce_pattern(3, ((0, 1), (2,)))
    assert merged["kind"] == "single_nonface" and merged["groups"] == ((0, 1), (2,))
    assert reduce_pattern(3, ((0, 1), (0, 2)))["nonface"] == (1, 2)
    assert reduce_pattern(3, ((),))["kind"] == "full"
    assert reduce_pattern(3, ((0, 1, 2),))["kind"] == "full"


def test_homological_fibre_on_the_small_grid():
    patterns = [f for f in downsets(3) if reduce_pattern(3, f)["kind"] != "other"]
    for cells in supports_in_grid((2, 2, 2)):
        for facets in patterns:
            assert homological_fibre(cells, facets) == fibre_dimension_k(cells, facets)
    assert homological_fibre(COUNTEREXAMPLE_ONE, separate_faces(3)) is None


def test_pattern_fixture_small():
    report = pattern_fixture(exhaustive=((2, 2, 2),), sampled=(((2, 2, 2, 2), 20, 1),))
    assert all(row["mismatches"] == 0 for row in report["checks"].values())
    assert report["classification"]["3"]["uncovered"] == (((0,), (1,), (2,)),)


def test_full_support_anova():
    cells = tuple(product(range(2), range(3), range(4)))
    for facets in (((0,), (1,), (2,)), ((0, 1), (2,)), ((0, 1), (1, 2)), ((),)):
        assert fibre_dimension_k(cells, facets) == full_support_formula((2, 3, 4), facets)
    assert full_support_formula((2, 3, 4), ((0,), (1,), (2,))) == 24 - 9 + 2
    report = full_support_fixture(grids=((2, 2, 3),))
    assert report["2x2x3"]["formula_matches"] == report["2x2x3"]["patterns"]


def test_projection_sequence_on_the_counterexample():
    zero, one = projection_sequence(COUNTEREXAMPLE_ZERO), projection_sequence(COUNTEREXAMPLE_ONE)
    assert (zero["graph_cycle_rank"], zero["previous"], zero["psi_rank"], zero["fibre"]) == (0, 1, 1, 0)
    assert (one["graph_cycle_rank"], one["previous"], one["psi_rank"], one["fibre"]) == (0, 1, 0, 1)
    for last in range(3):
        sequence = projection_sequence(COUNTEREXAMPLE_ONE, last)
        assert sequence["formula"] == sequence["fibre"] == 1


def test_projection_fixture_small():
    report = projection_fixture(exhaustive=((2, 2, 2),), sampled=(((2, 2, 2, 2), 30, 2),))
    for row in report.values():
        assert row["formula_holds"] == row["orders"] == row["psi_rank_within_bounds"]


def test_counterexample_families_agree_and_fibres_differ():
    assert natural_family(COUNTEREXAMPLE_ZERO) == natural_family(COUNTEREXAMPLE_ONE)
    assert separate_fibre(COUNTEREXAMPLE_ZERO) == 0 and separate_fibre(COUNTEREXAMPLE_ONE) == 1
    report = counterexample_fixture()
    assert report["families_equal"] and report["differing_keys"] == ()
    assert report["nerve_reduced_betti"] == ((0, 3, 0), (0, 3, 0))
    assert report["fibre_basis_one"] == ((1, -1, 1, -1, -1, 1),)
    assert report["zero_separate_observation_is_item_level"]
    assert report["one_witness_records"] == ("101001", "010110")
    assert report["one_witness_confused_by_separate_observation"]
    with pytest.raises(ValueError):
        natural_family(((0, 0), (1, 1)))


def test_homotopy_profile_and_collapse():
    assert homotopy_profile([(0, 1), (1, 2), (0, 2), (3, 4)]) == ((1, 0), (1, 1))
    assert collapsed_dimension([(0, 1, 2)]) == 0
    assert collapsed_dimension(balanced_facets(COUNTEREXAMPLE_ZERO)) == 1
    assert collapsed_dimension(balanced_facets(tuple(product(range(2), repeat=3)))) == 2


def test_nonlocal_fibre_vector():
    span = homological_span(NONLOCAL_SUPPORT)
    assert span["fibre"] == 1 and span["span"] == 0
    report = nonlocal_fixture(grids=((2, 2, 2),))
    assert report["2x2x2"]["smallest_such_support"] == 5


def test_three_map_unit_cells_hide_a_rational_fibre():
    report = integrality_fixture()
    assert report["kernel_generator"] == (1, -2, 1, 1, -1)
    assert report["unit_cells_separate_equals_item_level"]
    assert report["doubled_separate_strictly_coarser"]
    assert report["witness_confused_by_separate"] and report["witness_separated_by_joint"]
    maps, items = category_maps_from_support(NONLOCAL_SUPPORT)
    separate = join(join(category_channel(maps[0], items), category_channel(maps[1], items)),
                    category_channel(maps[2], items))
    assert separate == item_level_partition(items)


def test_nerve_incidence_corank_is_the_separate_fibre():
    for cells in supports_in_grid((2, 2, 2)):
        assert nerve_incidence_corank(cells) == separate_fibre(cells)


def test_rp2_cone():
    report = rp2_fixture()
    assert report["cells"] == 78 and report["items_with_doubled_cone"] == 96
    assert report["complex_reduced_betti"] == (0, 0, 1) == report["nerve_reduced_betti"]
    assert report["pairwise_fibre_dimension"] == 1 == report["link_formula_value"]
    assert report["generator_max_on_cone"] == report["generator_min_on_cone"] == 2
    assert report["generator_values_off_cone"] == (1,)
    assert report["doubled_cone_witness_same_pairwise_margins"]
    assert report["doubled_cone_witness_different_cells"]
    with pytest.raises(ValueError):
        rp2_fixture(line=(1, 2, 3))


# --- receipt and verify ------------------------------------------------------------

def test_verify_all_checks_pass_and_match_the_receipt():
    report = verify()
    assert report["all_passed"]
    assert len(report["checks"]) == 26
    receipt = Path(__file__).resolve().parents[1] / "output" / "evaluation_leak_topology" / "leak_topology_v0_1.json"
    if receipt.exists():
        stored = json.loads(receipt.read_text(encoding="utf-8"))
        assert stored["all_passed"] and set(stored["checks"]) == set(report["checks"])
