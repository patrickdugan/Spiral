"""Leak topology: what the cycles of the block-intersection complex cost.

Nothing in this module calls a model, a judge, a grader or a loop.  It takes
the category channels of ``evaluation_feedback_lattice`` (a category map is a
partition of the items; its channel leaks the pass count of every block) and
makes exact the one invariant the crosswalk note said was shared with the
RSITopology programme: the cycle rank of the bipartite intersection graph.

Setting.  A record says which of ``n`` items passed.  For category maps
``gamma_0, ..., gamma_{k-1}`` the nonempty ``k``-fold intersections of blocks
are the *cells*; ``x_c`` is the number of passes in cell ``c`` and
``0 <= x_c <= s_c`` with ``s_c`` the cell's size.  Observing a set ``S`` of
maps jointly leaks the ``S``-margins of the cell table (pass counts on the
nonempty intersections of blocks of the maps in ``S``).  An observation
pattern is a family ``Delta`` of jointly observed sets, closed under subsets.
The *fibre* is the kernel of the margin map on the rational cell space; its
dimension counts the free parameters that the observation leaves open.

1.  Two maps observed separately (``Delta = {{0}, {1}}``): the margin map is
    the unsigned incidence matrix of the intersection graph ``I``; flipping
    the sign of the column vertices makes it the signed incidence, so the
    fibre is the cycle space ``Z_1(I)``, of rational dimension
    ``beta_1 = |E| - |V| + c``, and its integer points are ``H_1(I; Z)`` with
    the fundamental cycles of any spanning forest as a basis.  Integer fibres
    over realized margins have affine dimension at most ``beta_1``, attain it,
    and are connected by single alternating-cycle swaps.

2.  Cost.  The separate observation plus the counts on a set ``S`` of cells
    recovers the joint one iff the cells outside ``S`` form a forest, so the
    joint leak is the separate leak plus exactly ``beta_1`` cell counts.  For
    independent items the probability that two independent records are
    confused by the separate observation is a sum over the integer cycle
    lattice; the joint observation keeps only its zero term.  Under dilation
    of the cell sizes the collision ratio grows like ``N^(beta_1/2)`` with a
    constant set by a weighted spanning-forest count: the exponent depends on
    ``beta_1`` alone, the finite values do not.

3.  Three or more maps.  For a pattern with a single minimal non-face ``W``
    (after dropping unobserved maps and merging maps the pattern never
    separates) the fibre is the direct sum of the top reduced homology of the
    links of the faces of colour set ``[k] - W`` in the nerve of the block
    cover; this covers every three-map pattern except separate observation.
    For maps observed separately the fibre is the corank of the vertex-facet
    incidence of the nerve (colours not needed), it sits in an exact sequence
    between two graph cycle spaces, and the rank of the connecting map is
    extra data: two supports whose nerves, rank-selected subcomplexes, links
    and merged-colour graphs are homotopy equivalent piece by piece have
    fibres of dimension 0 and 1.  Integrality changes too: for three maps
    observed separately, and even for the homological pattern "every pair
    jointly" (flags of RP^2 with a disk on a projective line), a unit-cell
    leak can vanish while the rational fibre has dimension one.

Every value is an exact integer or ``Fraction``; ranks are computed by exact
fraction-free Gaussian elimination over the rationals.  ``pi`` enters only
through two rational bounds on it.  The lattice module is imported, not
edited.
"""

from __future__ import annotations

import random
from fractions import Fraction as Q
from functools import lru_cache
from itertools import combinations, product
from math import comb, lcm, prod

from spiral_ln.evaluation_feedback_lattice import (
    all_category_maps, category_channel, intersection_graph, item_level_partition, join,
    partition_from_function, records, validate_categories,
)

PI_LOWER = Q(314159265358979, 10 ** 14)
PI_UPPER = Q(314159265358980, 10 ** 14)


# ---------------------------------------------------------------------------
# 0. Exact linear algebra over Q
# ---------------------------------------------------------------------------

def _integer_rows(rows) -> list[list[int]]:
    matrix = []
    for row in rows:
        if all(type(value) is int for value in row):
            matrix.append(list(row))
            continue
        row = [Q(value) for value in row]
        scale = lcm(*(value.denominator for value in row)) if row else 1
        matrix.append([int(value * scale) for value in row])
    return matrix


def rank(rows) -> int:
    """Exact rank over Q of a matrix given as rows of integers or fractions.

    Fraction-free (Bareiss) elimination: every intermediate entry is a minor
    of the original matrix, so each division is exact (Sylvester's identity);
    skipped columns do not enter the minors.
    """

    matrix = [row for row in _integer_rows(rows) if any(row)]
    if not matrix:
        return 0
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise ValueError("rows must have equal length")
    placed, previous = 0, 1
    for column in range(width):
        pivot = next((i for i in range(placed, len(matrix)) if matrix[i][column]), None)
        if pivot is None:
            continue
        matrix[placed], matrix[pivot] = matrix[pivot], matrix[placed]
        head = matrix[placed]
        for i in range(placed + 1, len(matrix)):
            row, factor = matrix[i], matrix[i][column]
            for j in range(column + 1, width):
                row[j] = (row[j] * head[column] - head[j] * factor) // previous
            row[column] = 0
        previous = head[column]
        placed += 1
        if placed == len(matrix):
            break
    return placed


def rank_by_fractions(rows) -> int:
    """Rank by ordinary Gaussian elimination on fractions (cross-check)."""

    matrix = [[Q(value) for value in row] for row in rows]
    placed = 0
    width = len(matrix[0]) if matrix else 0
    for column in range(width):
        pivot = next((i for i in range(placed, len(matrix)) if matrix[i][column]), None)
        if pivot is None:
            continue
        matrix[placed], matrix[pivot] = matrix[pivot], matrix[placed]
        for i in range(placed + 1, len(matrix)):
            factor = matrix[i][column] / matrix[placed][column]
            if factor:
                matrix[i] = [a - factor * b for a, b in zip(matrix[i], matrix[placed])]
        placed += 1
    return placed


def nullspace(rows, columns: int) -> tuple[tuple[Q, ...], ...]:
    """A basis of ``{x in Q^columns : rows x = 0}`` from the reduced row echelon form."""

    matrix = [[Q(value) for value in row] for row in rows]
    pivots: list[int] = []
    placed = 0
    for column in range(columns):
        pivot = next((i for i in range(placed, len(matrix)) if matrix[i][column]), None)
        if pivot is None:
            continue
        matrix[placed], matrix[pivot] = matrix[pivot], matrix[placed]
        inverse = 1 / matrix[placed][column]
        matrix[placed] = [value * inverse for value in matrix[placed]]
        for i in range(len(matrix)):
            if i != placed and matrix[i][column]:
                factor = matrix[i][column]
                matrix[i] = [a - factor * b for a, b in zip(matrix[i], matrix[placed])]
        pivots.append(column)
        placed += 1
    basis = []
    for free in (c for c in range(columns) if c not in pivots):
        vector = [Q(0)] * columns
        vector[free] = Q(1)
        for i, column in enumerate(pivots):
            vector[column] = -matrix[i][free]
        basis.append(tuple(vector))
    return tuple(basis)


def primitive_integer_vector(vector) -> tuple[int, ...]:
    """The primitive integer multiple of a nonzero rational vector, first nonzero entry positive."""

    vector = [Q(value) for value in vector]
    if not any(vector):
        raise ValueError("vector must be nonzero")
    scale = lcm(*(value.denominator for value in vector))
    integers = [int(value * scale) for value in vector]
    divisor = 0
    for value in integers:
        divisor = _gcd(divisor, abs(value))
    integers = [value // divisor for value in integers]
    sign = 1 if next(value for value in integers if value) > 0 else -1
    return tuple(sign * value for value in integers)


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def determinant(matrix) -> Q:
    """Exact determinant of a square matrix of fractions."""

    matrix = [[Q(value) for value in row] for row in matrix]
    size = len(matrix)
    if any(len(row) != size for row in matrix):
        raise ValueError("matrix must be square")
    result = Q(1)
    for column in range(size):
        pivot = next((i for i in range(column, size) if matrix[i][column]), None)
        if pivot is None:
            return Q(0)
        if pivot != column:
            matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
            result = -result
        result *= matrix[column][column]
        for i in range(column + 1, size):
            factor = matrix[i][column] / matrix[column][column]
            if factor:
                matrix[i] = [a - factor * b for a, b in zip(matrix[i], matrix[column])]
    return result


# ---------------------------------------------------------------------------
# 1. Two category maps: the fibre is the cycle space of the intersection graph
# ---------------------------------------------------------------------------

def cell_graph(left, right, items: int) -> dict[str, object]:
    """The intersection graph of two category maps with its cells and their sizes.

    Vertices are the blocks (rows first, then columns); edges are the nonempty
    intersections, listed in the order of ``intersection_graph``.
    """

    graph = intersection_graph(left, right, items)
    rows, columns = graph["rows"], graph["columns"]
    cells = tuple(tuple(sorted(set(rows[a]) & set(columns[b]))) for a, b in graph["edges"])
    return {"items": items, "rows": rows, "columns": columns, "edges": graph["edges"],
            "cells": cells, "sizes": tuple(len(cell) for cell in cells)}


def graph_from_sizes(edges, sizes) -> dict[str, object]:
    """A cell graph given abstractly: edges ``(row, column)`` and positive cell sizes.

    The items are numbered cell by cell, so the result is the cell graph of an
    explicit pair of category maps (``category_maps_of_graph``).
    """

    edges = tuple((int(a), int(b)) for a, b in edges)
    sizes = tuple(sizes)
    if len(edges) != len(sizes) or len(set(edges)) != len(edges) or not edges:
        raise ValueError("need distinct edges with one size each")
    if any(type(s) is not int or s < 1 for s in sizes):
        raise ValueError("cell sizes must be positive integers")
    row_count = max(a for a, _ in edges) + 1
    column_count = max(b for _, b in edges) + 1
    if {a for a, _ in edges} != set(range(row_count)) or {b for _, b in edges} != set(range(column_count)):
        raise ValueError("every row and column index must carry an edge")
    left: list[list[int]] = [[] for _ in range(row_count)]
    right: list[list[int]] = [[] for _ in range(column_count)]
    item = 0
    for (a, b), size in zip(edges, sizes):
        for _ in range(size):
            left[a].append(item)
            right[b].append(item)
            item += 1
    return cell_graph(left, right, item)


def category_maps_of_graph(graph) -> tuple[tuple, tuple]:
    return graph["rows"], graph["columns"]


def _row_count(graph) -> int:
    return len(graph["rows"])


def _vertex_count(graph) -> int:
    return len(graph["rows"]) + len(graph["columns"])


def _endpoints(graph) -> tuple[tuple[int, int], ...]:
    shift = _row_count(graph)
    return tuple((a, shift + b) for a, b in graph["edges"])


def margin_matrix(graph) -> tuple[tuple[int, ...], ...]:
    """Unsigned incidence matrix: rows are blocks, columns are cells."""

    ends = _endpoints(graph)
    return tuple(tuple(int(v in pair) for pair in ends) for v in range(_vertex_count(graph)))


def signed_incidence(graph) -> tuple[tuple[int, ...], ...]:
    """Signed incidence with every cell oriented from its row block to its column block."""

    ends = _endpoints(graph)
    return tuple(tuple(1 if v == a else -1 if v == b else 0 for a, b in ends)
                 for v in range(_vertex_count(graph)))


def _labels(vertex_count: int, pairs) -> tuple[int, ...]:
    parent = list(range(vertex_count))

    def find(v: int) -> int:
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return tuple(find(v) for v in range(vertex_count))


def _is_forest(vertex_count: int, pairs) -> bool:
    pairs = tuple(pairs)
    return len(pairs) == vertex_count - len(set(_labels(vertex_count, pairs)))


def components(graph) -> int:
    return len(set(_labels(_vertex_count(graph), _endpoints(graph))))


def cycle_rank(graph) -> int:
    """``beta_1 = |E| - |V| + c`` of the intersection graph."""

    return len(graph["edges"]) - _vertex_count(graph) + components(graph)


def spanning_forest(graph) -> tuple[int, ...]:
    """Edge indices of a maximal spanning forest, chosen greedily in edge order."""

    parent = list(range(_vertex_count(graph)))

    def find(v: int) -> int:
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    tree = []
    for index, (a, b) in enumerate(_endpoints(graph)):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            tree.append(index)
    return tuple(tree)


def fundamental_cycles(graph) -> tuple[tuple[int, tuple[int, ...]], ...]:
    """For each edge ``f`` off the spanning forest, the alternating vector of
    its fundamental cycle: ``+1`` on ``f``, then ``-1, +1, ...`` along the
    forest path from ``f``'s column back to its row."""

    ends = _endpoints(graph)
    tree = set(spanning_forest(graph))
    adjacency: dict[int, list[tuple[int, int]]] = {v: [] for v in range(_vertex_count(graph))}
    for e in sorted(tree):
        a, b = ends[e]
        adjacency[a].append((b, e))
        adjacency[b].append((a, e))
    parent: dict[int, tuple] = {}
    depth: dict[int, int] = {}
    for root in range(_vertex_count(graph)):
        if root in parent:
            continue
        parent[root], depth[root] = (None, None), 0
        stack = [root]
        while stack:
            v = stack.pop()
            for w, e in adjacency[v]:
                if w not in parent:
                    parent[w], depth[w] = (v, e), depth[v] + 1
                    stack.append(w)

    def path(u: int, v: int) -> list[int]:
        front, back = [], []
        while depth[u] > depth[v]:
            front.append(parent[u][1])
            u = parent[u][0]
        while depth[v] > depth[u]:
            back.append(parent[v][1])
            v = parent[v][0]
        while u != v:
            front.append(parent[u][1])
            u = parent[u][0]
            back.append(parent[v][1])
            v = parent[v][0]
        return front + back[::-1]

    cycles = []
    for f, (a, b) in enumerate(ends):
        if f in tree:
            continue
        vector = [0] * len(ends)
        vector[f] = 1
        for step, e in enumerate(path(b, a)):
            vector[e] = -1 if step % 2 == 0 else 1
        cycles.append((f, tuple(vector)))
    return tuple(cycles)


def simple_cycles(graph) -> tuple[tuple[int, ...], ...]:
    """Every simple cycle as an alternating vector (one sign each), by edge-subset search."""

    ends = _endpoints(graph)
    count = len(ends)
    found = []
    for size in range(4, count + 1, 2):
        for subset in combinations(range(count), size):
            degree: dict[int, int] = {}
            for e in subset:
                for v in ends[e]:
                    degree[v] = degree.get(v, 0) + 1
            if any(d != 2 for d in degree.values()):
                continue
            vector = [0] * count
            edge, sign, vertex = subset[0], 1, ends[subset[0]][1]
            walked = 0
            while True:
                vector[edge] = sign
                walked += 1
                edge = next(e for e in subset if e != edge and vertex in ends[e])
                if vector[edge]:
                    break
                sign = -sign
                vertex = ends[edge][0] if ends[edge][1] == vertex else ends[edge][1]
            if walked == size:
                found.append(tuple(vector))
    return tuple(found)


def fibre_dimension(left, right, items: int) -> int:
    """Rational dimension of the kernel of the margin map on the cell space."""

    graph = cell_graph(left, right, items)
    return len(graph["edges"]) - rank(margin_matrix(graph))


def cell_counts(graph, record: str) -> tuple[int, ...]:
    return tuple(sum(record[i] == "1" for i in cell) for cell in graph["cells"])


def margins_of(graph, counts) -> tuple[int, ...]:
    totals = [0] * _vertex_count(graph)
    for (a, b), value in zip(_endpoints(graph), counts):
        totals[a] += value
        totals[b] += value
    return tuple(totals)


def box(sizes):
    return product(*(range(size + 1) for size in sizes))


def integer_fibres(graph) -> dict[tuple, tuple]:
    """Every realizable cell-count vector, grouped by its margins."""

    fibres: dict[tuple, list] = {}
    for counts in box(graph["sizes"]):
        fibres.setdefault(margins_of(graph, counts), []).append(counts)
    return {key: tuple(value) for key, value in fibres.items()}


def affine_dimension(points) -> int:
    points = list(points)
    return rank([[a - b for a, b in zip(point, points[0])] for point in points[1:]]) if len(points) > 1 else 0


def connected_by_moves(fibre, moves, sizes) -> bool:
    """Whether a fibre is connected under ``x -> x + m`` for moves ``m`` (and negatives) inside the box."""

    fibre = set(fibre)
    start = next(iter(fibre))
    seen, stack = {start}, [start]
    signed = [move for base in moves for move in (base, tuple(-v for v in base))]
    while stack:
        point = stack.pop()
        for move in signed:
            target = tuple(p + m for p, m in zip(point, move))
            if target in fibre and target not in seen:
                seen.add(target)
                stack.append(target)
    return seen == fibre and all(0 <= v <= s for point in fibre for v, s in zip(point, sizes))


def two_map_fixture(record_sizes=(3, 4, 5), rank_sizes=(6,)) -> dict[str, object]:
    """Theorems 1 and 2 on every ordered pair of category maps.

    On ``record_sizes`` the integer fibres are enumerated and compared with
    the record partitions of the lattice module; on ``rank_sizes`` only the
    rational and integral kernel statements are checked.
    """

    report: dict[str, object] = {}
    for items in tuple(record_sizes) + tuple(rank_sizes):
        full = items in record_sizes
        maps = all_category_maps(items)
        channel = {m: category_channel(m, items) for m in maps} if full else {}
        refined: dict = {}
        tally = {"ordered_pairs": 0, "dimension_equals_cycle_rank": 0,
                 "signed_rank_is_vertices_minus_components": 0,
                 "fundamental_cycles_integral_kernel_basis": 0}
        if full:
            tally.update({"max_fibre_affine_dimension_equals_cycle_rank": 0,
                          "fibre_differences_span_kernel": 0,
                          "fibres_connected_by_simple_cycle_swaps": 0,
                          "separate_partition_is_join_of_channels": 0,
                          "joint_partition_is_refined_channel": 0,
                          "class_counts_and_multiplicities_match": 0})
        by_beta: dict[int, int] = {}
        for left, right in product(maps, repeat=2):
            graph = cell_graph(left, right, items)
            beta = cycle_rank(graph)
            by_beta[beta] = by_beta.get(beta, 0) + 1
            edge_count = len(graph["edges"])
            tally["ordered_pairs"] += 1
            tally["dimension_equals_cycle_rank"] += edge_count - rank(margin_matrix(graph)) == beta
            tally["signed_rank_is_vertices_minus_components"] += (
                rank(signed_incidence(graph)) == _vertex_count(graph) - components(graph))
            cycles = fundamental_cycles(graph)
            off_tree = [f for f, _ in cycles]
            basis_ok = (len(cycles) == beta
                        and all(not any(margins_of(graph, vector)) for _, vector in cycles)
                        and all(vector[g] == (1 if g == f else 0) for f, vector in cycles for g in off_tree)
                        and rank([vector for _, vector in cycles]) == beta)
            tally["fundamental_cycles_integral_kernel_basis"] += basis_ok
            if not full:
                continue
            fibres = integer_fibres(graph)
            dims = [affine_dimension(f) for f in fibres.values()]
            tally["max_fibre_affine_dimension_equals_cycle_rank"] += max(dims) == beta
            differences = [[a - b for a, b in zip(x, f[0])] for f in fibres.values() for x in f[1:]]
            tally["fibre_differences_span_kernel"] += rank(differences) == beta if differences else beta == 0
            moves = simple_cycles(graph)
            tally["fibres_connected_by_simple_cycle_swaps"] += all(
                connected_by_moves(f, moves, graph["sizes"]) for f in fibres.values())
            separate = partition_from_function(lambda r: margins_of(graph, cell_counts(graph, r)), records(items))
            joint = partition_from_function(lambda r: cell_counts(graph, r), records(items))
            tally["separate_partition_is_join_of_channels"] += separate == join(channel[left], channel[right])
            key = tuple(sorted(graph["cells"]))
            if key not in refined:
                refined[key] = category_channel(key, items)
            tally["joint_partition_is_refined_channel"] += joint == refined[key]
            multiplicity: dict[tuple, int] = {}
            for record in records(items):
                counts = cell_counts(graph, record)
                multiplicity[counts] = multiplicity.get(counts, 0) + 1
            tally["class_counts_and_multiplicities_match"] += (
                len(separate) == len(fibres)
                and len(joint) == prod(s + 1 for s in graph["sizes"])
                and all(multiplicity[x] == prod(comb(s, v) for s, v in zip(graph["sizes"], x))
                        for f in fibres.values() for x in f))
        tally["pairs_by_cycle_rank"] = dict(sorted(by_beta.items()))
        report[str(items)] = tally
    return report


def _all_pass(report: dict) -> bool:
    for row in report.values():
        pairs = row["ordered_pairs"]
        if any(value != pairs for key, value in row.items() if key not in ("ordered_pairs", "pairs_by_cycle_rank")):
            return False
    return True


# ---------------------------------------------------------------------------
# 2. What the cycles cost
# ---------------------------------------------------------------------------

def completion_report(graph) -> dict[str, object]:
    """For every set ``S`` of cells: do the margins plus the counts on ``S``
    determine every cell count (on the integer box)?  Compared with the
    forest criterion on the cells outside ``S``."""

    ends = _endpoints(graph)
    count = len(ends)
    points = list(box(graph["sizes"]))
    margin = {x: margins_of(graph, x) for x in points}
    agree, determined_sets = True, []
    for size in range(count + 1):
        for subset in combinations(range(count), size):
            seen: dict = {}
            determined = True
            for x in points:
                key = (margin[x], tuple(x[e] for e in subset))
                if seen.setdefault(key, x) != x:
                    determined = False
                    break
            forest = _is_forest(_vertex_count(graph), [ends[e] for e in range(count) if e not in subset])
            agree &= determined == forest
            if determined:
                determined_sets.append(subset)
    smallest = min(len(s) for s in determined_sets)
    return {"agrees_with_forest_criterion": agree, "minimum_size": smallest,
            "minimum_sets": sum(len(s) == smallest for s in determined_sets)}


def maximal_spanning_forests(graph) -> tuple[tuple[int, ...], ...]:
    """Every maximal spanning forest, as a tuple of edge indices (brute force)."""

    ends = _endpoints(graph)
    size = _vertex_count(graph) - components(graph)
    return tuple(subset for subset in combinations(range(len(ends)), size)
                 if _is_forest(_vertex_count(graph), [ends[e] for e in subset]))


def matrix_tree_count(graph) -> int:
    """Number of maximal spanning forests by Kirchhoff's matrix-tree theorem (cited):
    the product over components of a cofactor of the Laplacian ``D D^T``."""

    incidence = signed_incidence(graph)
    vertices = _vertex_count(graph)
    laplacian = [[sum(incidence[u][e] * incidence[v][e] for e in range(len(graph["edges"])))
                  for v in range(vertices)] for u in range(vertices)]
    labels = _labels(vertices, _endpoints(graph))
    total = Q(1)
    for label in sorted(set(labels)):
        members = [v for v in range(vertices) if labels[v] == label][1:]
        if members:
            total *= determinant([[laplacian[u][v] for v in members] for u in members])
    return int(total)


def difference_law(size: int, p: Q) -> dict[int, Q]:
    """Law of ``X - X'`` for independent ``X, X' ~ Binomial(size, p)``."""

    law = [comb(size, j) * p ** j * (1 - p) ** (size - j) for j in range(size + 1)]
    return {k: sum(law[j] * law[j + k] for j in range(size + 1) if 0 <= j + k <= size)
            for k in range(-size, size + 1)}


def cycle_lattice_points(graph):
    """Integer cycle vectors inside the box ``|z_e| <= s_e``, via fundamental coordinates."""

    cycles = fundamental_cycles(graph)
    sizes = graph["sizes"]
    count = len(sizes)
    for coefficients in product(*(range(-sizes[f], sizes[f] + 1) for f, _ in cycles)):
        z = tuple(sum(t * vector[e] for t, (_, vector) in zip(coefficients, cycles)) for e in range(count))
        if all(abs(v) <= s for v, s in zip(z, sizes)):
            yield z


def confusion_lattice_sum(graph, p: Q = Q(1, 2)) -> dict[str, Q]:
    """Theorem 4: the probability that two independent records have equal
    margins, as a sum over the integer cycle lattice, and its zero term."""

    laws = [difference_law(size, Q(p)) for size in graph["sizes"]]
    separate, terms = Q(0), 0
    for z in cycle_lattice_points(graph):
        separate += prod(law[v] for law, v in zip(laws, z))
        terms += 1
    joint = prod(law[0] for law in laws)
    return {"separate": separate, "joint": joint, "excess": separate - joint, "lattice_terms": terms}


def uniform_pair_counts(graph) -> dict[str, int]:
    """Ordered record pairs confused under the uniform prior, by Vandermonde:
    ``sum_z prod_e C(2 s_e, s_e + z_e)``."""

    sizes = graph["sizes"]
    separate = sum(prod(comb(2 * s, s + v) for s, v in zip(sizes, z)) for z in cycle_lattice_points(graph))
    return {"separate": separate, "joint": prod(comb(2 * s, s) for s in sizes)}


def collision_ratio(graph) -> Q:
    """``CP(margins) / CP(cells)`` under the uniform prior: ``sum_z prod_e C(2s_e, s_e+z_e)/C(2s_e, s_e)``.

    Bridges carry ``z_e = 0`` for every cycle vector and contribute a factor 1;
    the integer cycle lattice is the direct sum of those of the biconnected
    blocks, so the ratio is the product of the blocks' ratios.
    """

    counts = uniform_pair_counts(graph)
    return Q(counts["separate"], counts["joint"])


def decimal_string(value, places: int = 8) -> str:
    """Exact truncation of a rational to ``places`` decimals (display only; no float involved)."""

    value = Q(value)
    sign = "-" if value < 0 else ""
    value = abs(value)
    whole, rest = divmod(value.numerator, value.denominator)
    return f"{sign}{whole}.{(rest * 10 ** places) // value.denominator:0{places}d}"


def cycle_graph(length: int, sizes=None) -> dict[str, object]:
    """The even cycle ``C_length`` as a cell graph (rows ``i``, columns ``i`` and ``i-1``)."""

    if length < 4 or length % 2:
        raise ValueError("an intersection cycle has even length at least four")
    half = length // 2
    edges = [edge for i in range(half) for edge in ((i, i), (i, (i - 1) % half))]
    return graph_from_sizes(edges, sizes if sizes is not None else (1,) * length)


def block_fixture() -> dict[str, object]:
    """Collision ratio: single-cycle closed form, size-multiset invariance, bridges, blocks."""

    unit_cycles = {length: collision_ratio(cycle_graph(length)) for length in (4, 6, 8, 10)}
    closed_form = all(value == 1 + Q(2, 2 ** length) for length, value in unit_cycles.items())
    sized = {sizes: collision_ratio(graph_from_sizes(WITNESS_GRAPHS["C4_unit_four_items"][0], sizes))
             for sizes in ((2, 2, 1, 1), (2, 1, 1, 2), (1, 2, 2, 1), (3, 1, 1, 1), (1, 1, 1, 3))}
    rotations_agree = (sized[(2, 2, 1, 1)] == sized[(2, 1, 1, 2)] == sized[(1, 2, 2, 1)]
                       and sized[(3, 1, 1, 1)] == sized[(1, 1, 1, 3)])
    single = {sizes: sum(Q(prod(comb(2 * s, s + t) for s in sizes), prod(comb(2 * s, s) for s in sizes))
                         for t in range(-min(sizes), min(sizes) + 1))
              for sizes in ((2, 2, 1, 1), (3, 1, 1, 1))}
    c4 = unit_cycles[4]
    ratios = {name: collision_ratio(graph_from_sizes(*WITNESS_GRAPHS[name])) for name in (
        "C4_unit_with_pendant_path", "two_C4_sharing_a_vertex_cycle_rank_2", "two_disjoint_C4_cycle_rank_2",
        "K23_unit_cycle_rank_2")}
    return {
        "unit_cycle_ratios": {str(k): v for k, v in unit_cycles.items()},
        "unit_cycle_closed_form_one_plus_two_to_one_minus_length": closed_form,
        "sized_C4_ratios": {"".join(map(str, k)): v for k, v in sized.items()},
        "single_cycle_depends_on_size_multiset_only": rotations_agree,
        "single_cycle_sum_formula": all(single[sizes] == sized[sizes] for sizes in single),
        "bridges_do_not_change_the_ratio": ratios["C4_unit_with_pendant_path"] == c4,
        "vertex_joined_blocks_multiply": ratios["two_C4_sharing_a_vertex_cycle_rank_2"] == c4 * c4,
        "disjoint_blocks_multiply": ratios["two_disjoint_C4_cycle_rank_2"] == c4 * c4,
        "same_cycle_rank_different_ratio": ratios["K23_unit_cycle_rank_2"] != c4 * c4,
        "witness_ratios": ratios,
    }


def _cell_probability(graph, counts, p: Q) -> Q:
    return prod(comb(s, x) * p ** x * (1 - p) ** (s - x) for s, x in zip(graph["sizes"], counts))


def confusion_direct(graph, p: Q = Q(1, 2)) -> dict[str, Q]:
    """The same two probabilities, summed over the integer fibres."""

    p = Q(p)
    fibres = integer_fibres(graph)
    separate = sum(sum(_cell_probability(graph, x, p) for x in f) ** 2 for f in fibres.values())
    joint = sum(_cell_probability(graph, x, p) ** 2 for f in fibres.values() for x in f)
    return {"separate": separate, "joint": joint}


def guessing(graph, p: Q = Q(1, 2)) -> dict[str, Q]:
    """Maximum-a-posteriori success, exactly.

    ``cell_success``: guessing the joint observation (all cell counts) from the
    separate one.  ``record_success_*``: guessing the record from each
    observation.  Records sharing margins share their total, so the per-class
    maximum is ``p^t (1-p)^(n-t)``.
    """

    p = Q(p)
    n = graph["items"]
    fibres = integer_fibres(graph)
    cell_success = sum(max(_cell_probability(graph, x, p) for x in f) for f in fibres.values())

    def record_mass(total: int) -> Q:
        return p ** total * (1 - p) ** (n - total)

    separate = sum(record_mass(sum(f[0])) for f in fibres.values())
    joint = sum(record_mass(sum(x)) for f in fibres.values() for x in f)
    return {"cell_success": cell_success, "cell_error": 1 - cell_success,
            "record_success_separate": separate, "record_success_joint": joint,
            "record_success_gap": joint - separate}


def leak_costs(graph) -> dict[str, object]:
    """Every cost of the cycles for one cell graph, under the uniform prior."""

    fibres = integer_fibres(graph)
    confusion = confusion_lattice_sum(graph)
    guess = guessing(graph)
    completion = completion_report(graph)
    joint_classes = prod(s + 1 for s in graph["sizes"])
    return {
        "items": graph["items"], "sizes": graph["sizes"], "cycle_rank": cycle_rank(graph),
        "fibre_dimension": len(graph["edges"]) - rank(margin_matrix(graph)),
        "joint_classes": joint_classes, "separate_classes": len(fibres),
        "merged_classes": joint_classes - len(fibres),
        "confusion_excess": confusion["excess"],
        "collision_ratio": confusion["separate"] / confusion["joint"],
        "cell_guess_error": guess["cell_error"], "record_guess_gap": guess["record_success_gap"],
        "minimum_completion_size": completion["minimum_size"],
        "minimum_completions": completion["minimum_sets"],
        "largest_fibre": max(len(f) for f in fibres.values()),
    }


WITNESS_GRAPHS = {
    # name: (edges, sizes); every one has cycle rank 1 on six items unless noted
    "C4_unit_four_items": (((0, 0), (0, 1), (1, 0), (1, 1)), (1, 1, 1, 1)),
    "C6_unit": (((0, 0), (0, 2), (1, 0), (1, 1), (2, 1), (2, 2)), (1, 1, 1, 1, 1, 1)),
    "C4_sizes_3111": (((0, 0), (0, 1), (1, 0), (1, 1)), (3, 1, 1, 1)),
    "C4_sizes_2211_same_row": (((0, 0), (0, 1), (1, 0), (1, 1)), (2, 2, 1, 1)),
    "C4_sizes_2112_diagonal": (((0, 0), (0, 1), (1, 0), (1, 1)), (2, 1, 1, 2)),
    "C4_unit_with_pendant_path": (((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (2, 2)), (1, 1, 1, 1, 1, 1)),
    "K23_unit_cycle_rank_2": (((0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)), (1, 1, 1, 1, 1, 1)),
    "two_C4_sharing_a_vertex_cycle_rank_2": (((0, 0), (0, 1), (1, 0), (1, 1), (0, 2), (0, 3), (2, 2), (2, 3)),
                                              (1, 1, 1, 1, 1, 1, 1, 1)),
    "two_disjoint_C4_cycle_rank_2": (((0, 0), (0, 1), (1, 0), (1, 1), (2, 2), (2, 3), (3, 2), (3, 3)),
                                     (1, 1, 1, 1, 1, 1, 1, 1)),
}


def cost_fixture(sizes=(3, 4, 5)) -> dict[str, object]:
    """Theorem 3 and Theorem 4 on every ordered pair, and what depends on more than ``beta_1``."""

    identity = {"pairs": 0, "lattice_sum_equals_direct_uniform": 0, "lattice_sum_equals_direct_one_third": 0,
                "zero_term_is_joint": 0, "vandermonde_pair_counts": 0, "excess_positive_iff_cycle": 0,
                "completion_iff_forest": 0, "minimum_completion_is_cycle_rank": 0,
                "minimum_completions_are_maximal_forests": 0, "matrix_tree_count_matches": 0,
                "cotree_identity_unit_and_size_weights": 0}
    values_by_beta: dict[int, dict[str, set]] = {}
    for items in sizes:
        for left, right in product(all_category_maps(items), repeat=2):
            graph = cell_graph(left, right, items)
            beta = cycle_rank(graph)
            identity["pairs"] += 1
            half, third = confusion_lattice_sum(graph, Q(1, 2)), confusion_lattice_sum(graph, Q(1, 3))
            direct_half, direct_third = confusion_direct(graph, Q(1, 2)), confusion_direct(graph, Q(1, 3))
            identity["lattice_sum_equals_direct_uniform"] += half["separate"] == direct_half["separate"]
            identity["lattice_sum_equals_direct_one_third"] += third["separate"] == direct_third["separate"]
            identity["zero_term_is_joint"] += (half["joint"] == direct_half["joint"]
                                               and third["joint"] == direct_third["joint"])
            counts = uniform_pair_counts(graph)
            identity["vandermonde_pair_counts"] += (Q(counts["separate"], 4 ** items) == half["separate"]
                                                    and Q(counts["joint"], 4 ** items) == half["joint"])
            identity["excess_positive_iff_cycle"] += (half["excess"] > 0) == (beta > 0) == (third["excess"] > 0)
            completion = completion_report(graph)
            forests = maximal_spanning_forests(graph)
            identity["completion_iff_forest"] += completion["agrees_with_forest_criterion"]
            identity["minimum_completion_is_cycle_rank"] += completion["minimum_size"] == beta
            identity["minimum_completions_are_maximal_forests"] += completion["minimum_sets"] == len(forests)
            identity["matrix_tree_count_matches"] += matrix_tree_count(graph) == len(forests)
            identity["cotree_identity_unit_and_size_weights"] += all(
                cotree_identity(graph, weights)["holds"]
                for weights in (graph["sizes"], tuple(Q(1, s) for s in graph["sizes"])))
            row = values_by_beta.setdefault(beta, {key: set() for key in (
                "fibre_dimension", "minimum_completion_size", "lattice_rank", "confusion_excess",
                "collision_ratio", "minimum_completions", "record_guess_gap", "cell_guess_error")})
            guess = guessing(graph)
            row["fibre_dimension"].add(len(graph["edges"]) - rank(margin_matrix(graph)))
            row["minimum_completion_size"].add(completion["minimum_size"])
            row["lattice_rank"].add(len(fundamental_cycles(graph)))
            row["confusion_excess"].add(half["excess"])
            row["collision_ratio"].add(half["separate"] / half["joint"])
            row["minimum_completions"].add(completion["minimum_sets"])
            row["record_guess_gap"].add(guess["record_success_gap"])
            row["cell_guess_error"].add(guess["cell_error"])
    distinct = {str(beta): {key: len(value) for key, value in row.items()}
                for beta, row in sorted(values_by_beta.items())}
    witnesses = {name: leak_costs(graph_from_sizes(*spec)) for name, spec in WITNESS_GRAPHS.items()}
    return {"identities": identity, "distinct_values_by_cycle_rank_up_to_five_items": distinct,
            "witnesses": witnesses}


def cotree_identity(graph, weights) -> dict[str, object]:
    """Cauchy-Binet for the fundamental cycle matrix ``Z``:
    ``det(Z^T diag(w) Z) = sum over complements S of maximal spanning forests of prod_{e in S} w_e``."""

    weights = tuple(Q(w) for w in weights)
    vectors = [vector for _, vector in fundamental_cycles(graph)]
    gram = [[sum(w * u[e] * v[e] for e, w in enumerate(weights)) for v in vectors] for u in vectors]
    value = determinant(gram) if vectors else Q(1)
    edges = range(len(graph["edges"]))
    cotree_sum = sum(prod(weights[e] for e in edges if e not in forest)
                     for forest in maximal_spanning_forests(graph))
    return {"determinant": value, "cotree_sum": cotree_sum, "holds": value == cotree_sum}


def weighted_forest_count(graph, weights) -> Q:
    """``tau_w = sum over maximal spanning forests T of prod_{e in T} w_e``."""

    return sum(prod(Q(weights[e]) for e in forest) for forest in maximal_spanning_forests(graph))


def dilated_collision_ratio(edges, sigma, scale: int) -> Q:
    """``CP(margins)/CP(cells)`` at ``p = 1/2`` with cell sizes ``scale * sigma``."""

    graph = graph_from_sizes(edges, tuple(scale * s for s in sigma))
    counts = uniform_pair_counts(graph)
    return Q(counts["separate"], counts["joint"])


def asymptotic_fixture(cases=None) -> dict[str, object]:
    """Theorem 5's finite trend: ``A_N = R_N^2 tau_sigma / (N^beta prod sigma)`` against ``pi^beta``."""

    cases = cases or {
        "C4_unit": (WITNESS_GRAPHS["C4_unit_four_items"][0], (1, 1, 1, 1), (4, 8, 16, 32, 64)),
        "C4_sigma_1212": (WITNESS_GRAPHS["C4_unit_four_items"][0], (1, 2, 1, 2), (2, 4, 8, 16, 32)),
        "K23_unit": (WITNESS_GRAPHS["K23_unit_cycle_rank_2"][0], (1, 1, 1, 1, 1, 1), (2, 4, 8, 16)),
    }
    report = {}
    for name, (edges, sigma, scales) in cases.items():
        base = graph_from_sizes(edges, sigma)
        beta = cycle_rank(base)
        tau = weighted_forest_count(base, sigma)
        constant = tau / prod(Q(s) for s in sigma)
        values = []
        for scale in scales:
            ratio = dilated_collision_ratio(edges, sigma, scale)
            values.append(ratio * ratio * constant / scale ** beta)
        lower, upper = PI_LOWER ** beta, PI_UPPER ** beta
        report[name] = {
            "cycle_rank": beta, "weighted_forest_count": tau, "scales": scales,
            "limit_constant": f"pi^{beta} = lim R_N^2 * {tau / prod(Q(s) for s in sigma)} / N^{beta}",
            "normalized_values_decimal": tuple(decimal_string(v) for v in values),
            "pi_power_decimal": decimal_string(lower),
            "decreasing": all(a > b for a, b in zip(values, values[1:])),
            "above_pi_power": all(v > upper for v in values),
            "relative_excess_at_largest_scale_below_one_tenth": values[-1] - upper < upper / 10,
            "scaled_excess_decimal": tuple(decimal_string(scale * (v - lower), 4)
                                           for scale, v in zip(scales, values)),
            "determinant_identity": cotree_identity(base, tuple(Q(1, s) for s in sigma))["holds"],
        }
    return report


def ehrhart_counts(graph, scales) -> tuple[int, ...]:
    """Integer tables over margins ``N * M(1)`` with cell sizes ``2N``: the
    points ``1N + Z t`` with ``|Z t| <= N`` coordinatewise."""

    cycles = [vector for _, vector in fundamental_cycles(graph)]
    count = len(graph["edges"])
    results = []
    for scale in scales:
        total = 0
        # the fundamental coordinate of a cycle vector is its value on the off-forest edge
        for t in product(range(-scale, scale + 1), repeat=len(cycles)):
            if all(abs(sum(c * v[e] for c, v in zip(t, cycles))) <= scale for e in range(count)):
                total += 1
        results.append(total)
    return tuple(results)


def _differences(values) -> list:
    return [b - a for a, b in zip(values, values[1:])]


def ehrhart_fixture() -> dict[str, object]:
    """The fibre count under dilation is a polynomial of degree ``beta_1`` (Ehrhart, cited; finite check)."""

    cases = {"C4": WITNESS_GRAPHS["C4_unit_four_items"][0], "C6": WITNESS_GRAPHS["C6_unit"][0],
             "K23": WITNESS_GRAPHS["K23_unit_cycle_rank_2"][0],
             "bowtie": WITNESS_GRAPHS["two_C4_sharing_a_vertex_cycle_rank_2"][0],
             "K33": tuple((a, b) for a in range(3) for b in range(3))}
    report = {}
    for name, edges in cases.items():
        graph = graph_from_sizes(edges, (1,) * len(edges))
        beta = cycle_rank(graph)
        scales = tuple(range(beta + 3))
        counts = ehrhart_counts(graph, scales)
        table = [list(counts)]
        for _ in range(beta + 1):
            table.append(_differences(table[-1]))
        report[name] = {"cycle_rank": beta, "counts": counts,
                        "degree_is_cycle_rank": len(set(table[beta])) == 1 and table[beta][0] != 0
                        and all(v == 0 for v in table[beta + 1]),
                        "leading_difference": table[beta][0]}
    return report


# ---------------------------------------------------------------------------
# 3. Three or more maps: observation patterns, links, and the projection sequence
# ---------------------------------------------------------------------------

def cell_support(maps, items: int) -> dict[tuple[int, ...], int]:
    """Nonempty ``k``-fold intersections as block-index tuples, with their sizes."""

    blocks = [validate_categories(m, items) for m in maps]
    index = [{i: b for b, block in enumerate(bl) for i in block} for bl in blocks]
    support: dict[tuple[int, ...], int] = {}
    for item in range(items):
        cell = tuple(idx[item] for idx in index)
        support[cell] = support.get(cell, 0) + 1
    return dict(sorted(support.items()))


def category_maps_from_support(cells, sizes=None) -> tuple[tuple, int]:
    """Category maps realizing a support: items numbered cell by cell, ``sizes`` per cell (default 1)."""

    cells = sorted(set(map(tuple, cells)))
    if not cells or len({len(c) for c in cells}) != 1:
        raise ValueError("need cells of equal length")
    sizes = tuple(sizes) if sizes is not None else (1,) * len(cells)
    if len(sizes) != len(cells) or any(type(s) is not int or s < 1 for s in sizes):
        raise ValueError("one positive integer size per cell")
    width = len(cells[0])
    blocks: list[dict] = [{} for _ in range(width)]
    item = 0
    for cell, size in zip(cells, sizes):
        for _ in range(size):
            for j in range(width):
                blocks[j].setdefault(cell[j], []).append(item)
            item += 1
    maps = tuple(validate_categories(list(b.values()), item) for b in blocks)
    return maps, item


def project(cells, colours) -> tuple[tuple, ...]:
    return tuple(sorted({tuple(c[j] for j in colours) for c in cells}))


def margin_rows_k(cells, faces) -> list[list[int]]:
    """One row per (face, projected tuple): the margin of the cell table on that face."""

    cells = sorted(cells)
    rows = []
    for face in faces:
        groups: dict[tuple, list[int]] = {}
        for i, c in enumerate(cells):
            groups.setdefault(tuple(c[j] for j in face), []).append(i)
        for key in sorted(groups):
            row = [0] * len(cells)
            for i in groups[key]:
                row[i] = 1
            rows.append(row)
    return rows


def fibre_dimension_k(cells, faces) -> int:
    cells = sorted(set(map(tuple, cells)))
    return len(cells) - rank(margin_rows_k(cells, faces))


def separate_faces(k: int) -> tuple[tuple[int, ...], ...]:
    return tuple((j,) for j in range(k))


def separate_fibre(cells) -> int:
    cells = sorted(set(map(tuple, cells)))
    return fibre_dimension_k(cells, separate_faces(len(cells[0])))


def reduced_betti(facets) -> tuple[int, ...]:
    """Reduced rational Betti numbers of the simplicial complex generated by ``facets``."""

    faces = set()
    for facet in facets:
        facet = tuple(sorted(facet))
        for size in range(1, len(facet) + 1):
            faces.update(combinations(facet, size))
    if not faces:
        raise ValueError("complex must be nonempty")
    top = max(len(f) for f in faces)
    levels = [sorted(f for f in faces if len(f) == d + 1) for d in range(top)]
    index = [{f: i for i, f in enumerate(level)} for level in levels]
    ranks = [1]  # the augmentation C_0 -> Q of a nonempty complex
    for d in range(1, top):
        rows = [[0] * len(levels[d]) for _ in levels[d - 1]]
        for j, face in enumerate(levels[d]):
            for i in range(len(face)):
                rows[index[d - 1][face[:i] + face[i + 1:]]][j] += (-1) ** i
        ranks.append(rank(rows))
    ranks.append(0)
    return tuple(len(levels[d]) - ranks[d] - ranks[d + 1] for d in range(top))


def balanced_facets(cells, colours=None) -> tuple[tuple, ...]:
    """Facets of the nerve of the block cover restricted to ``colours``: vertices are ``(colour, block)``."""

    cells = sorted(set(map(tuple, cells)))
    colours = tuple(range(len(cells[0]))) if colours is None else tuple(colours)
    return tuple(sorted({tuple((j, c[j]) for j in colours) for c in cells}))


def link_slices(cells, faces_colours) -> dict[tuple, tuple]:
    """For each face ``r`` with colour set ``R``, the facets of its link (the slice of cells over ``r``)."""

    cells = sorted(set(map(tuple, cells)))
    k = len(cells[0])
    rest = tuple(j for j in range(k) if j not in faces_colours)
    slices: dict[tuple, set] = {}
    for c in cells:
        slices.setdefault(tuple(c[j] for j in faces_colours), set()).add(tuple((j, c[j]) for j in rest))
    return {r: tuple(sorted(s)) for r, s in sorted(slices.items())}


def single_nonface_facets(k: int, nonface) -> tuple[tuple[int, ...], ...]:
    """Facets of ``Delta = {S : W not a subset of S}``: ``R + (W - w)`` for each ``w`` in ``W``."""

    nonface = tuple(sorted(set(nonface)))
    if not nonface or any(j not in range(k) for j in nonface):
        raise ValueError("the non-face must be a nonempty set of colours")
    rest = [j for j in range(k) if j not in nonface]
    return tuple(sorted(tuple(sorted(rest + [x for x in nonface if x != w])) for w in nonface))


def link_formula(cells, nonface) -> int:
    """Theorem 7: ``sum over faces r of colour set [k]-W of reduced beta_{|W|-1}(lk r)``."""

    cells = sorted(set(map(tuple, cells)))
    k = len(cells[0])
    nonface = tuple(sorted(set(nonface)))
    rest = tuple(j for j in range(k) if j not in nonface)
    return sum(reduced_betti(slice_facets)[len(nonface) - 1]
               for slice_facets in link_slices(cells, rest).values())


@lru_cache(maxsize=None)
def downsets(k: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Every observation pattern on ``k`` maps, by its facets; ``((),)`` is the score-only pattern."""

    subsets = [tuple(s) for size in range(1, k + 1) for s in combinations(range(k), size)]
    found = []
    for mask in range(1 << len(subsets)):
        chosen = [subsets[i] for i in range(len(subsets)) if mask >> i & 1]
        if any(set(a) < set(b) for a in chosen for b in chosen):
            continue
        found.append(tuple(sorted(chosen)) if chosen else ((),))
    return tuple(sorted(found, key=lambda f: (len(f), f)))


def minimal_nonfaces(k: int, facets) -> tuple[tuple[int, ...], ...]:
    def is_face(s) -> bool:
        return any(set(s) <= set(f) for f in facets)

    nonfaces = [s for size in range(1, k + 1) for s in combinations(range(k), size) if not is_face(s)]
    return tuple(s for s in nonfaces if not any(set(t) < set(s) for t in nonfaces))


def reduce_pattern(k: int, facets) -> dict[str, object]:
    """Drop unobserved maps, merge maps the pattern never separates, and classify.

    ``kind`` is ``full`` (the observed maps are seen jointly; the fibre is
    ``|P| - |P_O|``, zero when every map is observed), ``single_nonface``
    (Theorem 7 applies to the reduced pattern) or ``other``.
    """

    facets = tuple(tuple(f) for f in facets)
    observed = tuple(sorted({j for f in facets for j in f}))
    groups: list[list[int]] = []
    for j in observed:
        for group in groups:
            g = group[0]
            if all((j in f) == (g in f) for f in facets):
                group.append(j)
                break
        else:
            groups.append([j])
    position = {j: i for i, group in enumerate(groups) for j in group}
    reduced = tuple(sorted({tuple(sorted({position[j] for j in f})) for f in facets}))
    size = len(groups)
    if any(len(f) == size for f in reduced):
        kind, nonface = "full", None
    else:
        missing = minimal_nonfaces(size, reduced)
        kind, nonface = ("single_nonface", missing[0]) if len(missing) == 1 else ("other", None)
    return {"observed": observed, "groups": tuple(tuple(g) for g in groups), "reduced_facets": reduced,
            "kind": kind, "nonface": nonface}


def homological_fibre(cells, facets):
    """The fibre dimension read off homology when the reduced pattern allows it, else ``None``.

    Unobserved maps add ``|P| - |P_O|`` (reduced zeroth Betti numbers of the
    slices over observed tuples); merged maps act as one map; a single minimal
    non-face gives the link formula.
    """

    cells = sorted(set(map(tuple, cells)))
    pattern = reduce_pattern(len(cells[0]), facets)
    observed = pattern["observed"]
    projected = project(cells, observed)
    extra = len(cells) - len(projected)
    position = {j: i for i, j in enumerate(observed)}
    merged = sorted({tuple(tuple(c[position[j]] for j in group) for group in pattern["groups"])
                     for c in projected})
    if pattern["kind"] == "full":
        return extra
    if pattern["kind"] == "single_nonface":
        return extra + link_formula(merged, pattern["nonface"])
    return None


def full_support_formula(dims, facets) -> int:
    """ANOVA count on the full grid: ``sum over T not in Delta of prod_{j in T} (m_j - 1)``."""

    k = len(dims)
    return sum(prod(dims[j] - 1 for j in t)
               for size in range(1, k + 1) for t in combinations(range(k), size)
               if not any(set(t) <= set(f) for f in facets))


def full_support_fixture(grids=((2, 2, 2), (2, 3, 4), (3, 3, 3), (2, 2, 2, 2), (2, 3, 2, 2))) -> dict[str, object]:
    """Proposition 6 on full supports, every pattern; also its homological reading."""

    report = {}
    for dims in grids:
        cells = tuple(product(*(range(m) for m in dims)))
        patterns = downsets(len(dims))
        matches = sum(fibre_dimension_k(cells, f) == full_support_formula(dims, f) for f in patterns)
        join_betti = all(
            reduced_betti(balanced_facets(cells, t))[len(t) - 1] == prod(dims[j] - 1 for j in t)
            for size in range(1, len(dims) + 1) for t in combinations(range(len(dims)), size))
        report["x".join(map(str, dims))] = {"patterns": len(patterns), "formula_matches": matches,
                                            "top_betti_of_rank_selected_joins": join_betti}
    return report


def supports_in_grid(dims, max_cells=None):
    """Every coordinate-surjective support in a grid (exhaustive)."""

    grid = tuple(product(*(range(m) for m in dims)))
    limit = len(grid) if max_cells is None else max_cells
    for size in range(max(dims), limit + 1):
        for chosen in combinations(grid, size):
            if all(len({c[j] for c in chosen}) == dims[j] for j in range(len(dims))):
                yield chosen


def random_supports(dims, count: int, seed: int):
    """``count`` coordinate-surjective supports drawn with a fixed seed."""

    grid = tuple(product(*(range(m) for m in dims)))
    rng = random.Random(seed)
    produced = 0
    while produced < count:
        chosen = tuple(sorted(rng.sample(grid, rng.randint(max(dims), len(grid)))))
        if all(len({c[j] for c in chosen}) == dims[j] for j in range(len(dims))):
            produced += 1
            yield chosen


def pattern_fixture(exhaustive=((2, 2, 2), (2, 2, 3)),
                    sampled=(((3, 3, 3), 120, 7), ((2, 2, 2, 2), 120, 8), ((2, 3, 2, 3), 60, 9))) -> dict[str, object]:
    """Theorem 7 with the reductions, on every pattern, against the rank computation."""

    report: dict[str, object] = {}
    classification = {}
    for k in (2, 3, 4):
        kinds: dict[str, int] = {}
        uncovered = []
        for facets in downsets(k):
            kind = reduce_pattern(k, facets)["kind"]
            kinds[kind] = kinds.get(kind, 0) + 1
            if kind == "other":
                uncovered.append(facets)
        classification[str(k)] = {"patterns": len(downsets(k)), "kinds": kinds,
                                  "uncovered": tuple(uncovered) if k <= 3 else len(uncovered)}
    report["classification"] = classification
    runs = [(dims, supports_in_grid(dims), "exhaustive") for dims in exhaustive]
    runs += [(dims, random_supports(dims, count, seed), f"random_{count}_seed_{seed}")
             for dims, count, seed in sampled]
    checks = {}
    for dims, supports, label in runs:
        k = len(dims)
        patterns = [f for f in downsets(k) if reduce_pattern(k, f)["kind"] != "other"]
        nonfaces = [w for size in range(1, k + 1) for w in combinations(range(k), size)]
        supports_seen = comparisons = mismatches = direct = direct_mismatches = 0
        for cells in supports:
            supports_seen += 1
            for facets in patterns:
                comparisons += 1
                mismatches += homological_fibre(cells, facets) != fibre_dimension_k(cells, facets)
            for nonface in nonfaces:
                direct += 1
                direct_mismatches += (link_formula(cells, nonface)
                                      != fibre_dimension_k(cells, single_nonface_facets(k, nonface)))
        checks["x".join(map(str, dims))] = {"supports": supports_seen, "patterns": len(patterns),
                                            "comparisons": comparisons, "mismatches": mismatches,
                                            "direct_link_formula_comparisons": direct,
                                            "direct_link_formula_mismatches": direct_mismatches,
                                            "sampling": label}
    report["checks"] = checks
    return report


def projection_sequence(cells, last=None) -> dict[str, object]:
    """Theorem 8 for maps observed separately, with ``last`` the projected-out map.

    ``G`` is the intersection graph of the merged map (all other maps jointly)
    with the last map; ``previous`` the separate fibre of the projected support;
    ``Psi`` sends a fibre vector of the projected support to its sums over the
    components of ``G``.  Returns the three terms and their combination.
    """

    cells = sorted(set(map(tuple, cells)))
    k = len(cells[0])
    last = k - 1 if last is None else last
    order = [j for j in range(k) if j != last] + [last]
    cells = sorted(tuple(c[j] for j in order) for c in cells)
    head = project(cells, range(k - 1))
    tails = sorted({c[-1] for c in cells})
    vertices = len(head) + len(tails)
    pairs = [(head.index(c[:-1]), len(head) + tails.index(c[-1])) for c in cells]
    labels = _labels(vertices, pairs)
    component_ids = sorted(set(labels))
    graph_beta = len(cells) - vertices + len(component_ids)
    if k - 1 >= 2:
        previous = separate_fibre(head)
        basis = nullspace(margin_rows_k(head, separate_faces(k - 1)), len(head))
    else:
        previous, basis = 0, ()
    psi = []
    for vector in basis:
        row = [Q(0)] * len(component_ids)
        for i, value in enumerate(vector):
            row[component_ids.index(labels[i])] += value
        psi.append(row)
    psi_rank = rank(psi) if psi else 0
    return {"graph_cycle_rank": graph_beta, "graph_components": len(component_ids),
            "previous": previous, "psi_rank": psi_rank,
            "formula": graph_beta + previous - psi_rank, "fibre": separate_fibre(cells)}


def projection_fixture(exhaustive=((2, 2, 2), (2, 2, 3)),
                       sampled=(((3, 3, 3), 200, 11), ((2, 2, 2, 2), 200, 12), ((3, 2, 2, 3), 80, 13))) -> dict[str, object]:
    report = {}
    runs = [(dims, supports_in_grid(dims), "exhaustive") for dims in exhaustive]
    runs += [(dims, random_supports(dims, count, seed), f"random_{count}_seed_{seed}")
             for dims, count, seed in sampled]
    for dims, supports, label in runs:
        seen = holds = nonzero_psi = bounds = 0
        for cells in supports:
            seen += 1
            for last in range(len(dims)):
                sequence = projection_sequence(cells, last)
                holds += sequence["formula"] == sequence["fibre"]
                nonzero_psi += sequence["psi_rank"] > 0
                bounds += sequence["psi_rank"] <= min(sequence["previous"], sequence["graph_components"] - 1)
        report["x".join(map(str, dims))] = {"supports": seen, "orders": seen * len(dims),
                                            "formula_holds": holds, "psi_rank_positive": nonzero_psi,
                                            "psi_rank_within_bounds": bounds, "sampling": label}
    return report


def _components_of_facets(facets) -> list[list[tuple]]:
    facets = [tuple(sorted(f)) for f in facets]
    vertices = sorted({v for f in facets for v in f})
    position = {v: i for i, v in enumerate(vertices)}
    labels = _labels(len(vertices), [(position[f[0]], position[v]) for f in facets for v in f[1:]])
    groups: dict[int, list] = {}
    for f in facets:
        groups.setdefault(labels[position[f[0]]], []).append(f)
    return list(groups.values())


def homotopy_profile(facets) -> tuple:
    """Per-component unreduced Betti numbers, sorted.  For a graph this is its homotopy type."""

    profile = []
    for component in _components_of_facets(facets):
        reduced = reduced_betti(component)
        profile.append((reduced[0] + 1,) + reduced[1:])
    return tuple(sorted(profile))


def collapsed_dimension(facets) -> int:
    """Dimension left after elementary collapses (removing a free face with its unique coface)."""

    faces = set()
    for facet in facets:
        facet = tuple(sorted(facet))
        for size in range(1, len(facet) + 1):
            faces.update(combinations(facet, size))
    changed = True
    while changed:
        changed = False
        for face in sorted(faces, key=lambda f: (len(f), f)):
            cofaces = [g for g in faces if len(g) == len(face) + 1 and set(face) <= set(g)]
            if len(cofaces) == 1:
                faces.discard(face)
                faces.discard(cofaces[0])
                changed = True
                break
    return max(len(f) for f in faces) - 1


def natural_family(cells) -> dict[str, object]:
    """Homotopy data of every natural complex of a three-map support.

    The nerve and each rank-selected subcomplex, the links of every face
    (as multisets over faces of each colour set), the three merged-colour
    intersection graphs, and the coloured face numbers.
    """

    cells = sorted(set(map(tuple, cells)))
    k = len(cells[0])
    if k != 3:
        raise ValueError("the family is defined here for three maps")
    family: dict[str, object] = {}
    for size in range(1, k + 1):
        for colours in combinations(range(k), size):
            family["restriction_" + "".join(map(str, colours))] = homotopy_profile(balanced_facets(cells, colours))
            family["faces_" + "".join(map(str, colours))] = len(project(cells, colours))
    for size in (1, 2):
        for colours in combinations(range(k), size):
            family["links_" + "".join(map(str, colours))] = tuple(sorted(
                homotopy_profile(s) for s in link_slices(cells, colours).values()))
    for j in range(k):
        a, b = [x for x in range(k) if x != j]
        family[f"merged_{a}{b}_with_{j}"] = homotopy_profile(
            sorted({((0, (c[a], c[b])), (1, (c[j],))) for c in cells}))
    family["nerve_collapses_to_dimension"] = collapsed_dimension(balanced_facets(cells))
    return family


COUNTEREXAMPLE_ZERO = ((0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 2, 2), (1, 0, 2), (1, 1, 1))
COUNTEREXAMPLE_ONE = ((0, 0, 0), (0, 0, 1), (0, 1, 2), (0, 2, 2), (1, 1, 0), (1, 2, 1))


def counterexample_fixture() -> dict[str, object]:
    """Two supports with matching natural homotopy data and separate fibres 0 and 1."""

    zero, one = natural_family(COUNTEREXAMPLE_ZERO), natural_family(COUNTEREXAMPLE_ONE)
    maps_zero, items_zero = category_maps_from_support(COUNTEREXAMPLE_ZERO)
    maps_one, items_one = category_maps_from_support(COUNTEREXAMPLE_ONE)

    def separate_channel(maps, items):
        return join(join(category_channel(maps[0], items), category_channel(maps[1], items)),
                    category_channel(maps[2], items))

    basis_one = nullspace(margin_rows_k(COUNTEREXAMPLE_ONE, separate_faces(3)), len(COUNTEREXAMPLE_ONE))
    vector = primitive_integer_vector(basis_one[0])
    first = "".join("1" if v > 0 else "0" for v in vector)
    second = "".join("1" if v < 0 else "0" for v in vector)
    channel_one = separate_channel(maps_one, items_one)
    block_of = {r: index for index, block in enumerate(channel_one) for r in block}
    return {
        "zero_separate_observation_is_item_level":
            separate_channel(maps_zero, items_zero) == item_level_partition(items_zero),
        "one_witness_records": (first, second),
        "one_witness_confused_by_separate_observation": first != second and block_of[first] == block_of[second],
        "supports": (COUNTEREXAMPLE_ZERO, COUNTEREXAMPLE_ONE),
        "category_maps": (maps_zero, maps_one), "items": (items_zero, items_one),
        "separate_fibres": (separate_fibre(COUNTEREXAMPLE_ZERO), separate_fibre(COUNTEREXAMPLE_ONE)),
        "families_equal": zero == one, "family": zero,
        "differing_keys": tuple(key for key in zero if zero[key] != one[key]),
        "projection_sequences": (projection_sequence(COUNTEREXAMPLE_ZERO), projection_sequence(COUNTEREXAMPLE_ONE)),
        "fibre_basis_one": tuple(primitive_integer_vector(v) for v in nullspace(
            margin_rows_k(COUNTEREXAMPLE_ONE, separate_faces(3)), len(COUNTEREXAMPLE_ONE))),
        "nerve_incidence_coranks": (nerve_incidence_corank(COUNTEREXAMPLE_ZERO),
                                    nerve_incidence_corank(COUNTEREXAMPLE_ONE)),
        "two_way_fibres": (fibre_dimension_k(COUNTEREXAMPLE_ZERO, ((0, 1), (0, 2), (1, 2))),
                           fibre_dimension_k(COUNTEREXAMPLE_ONE, ((0, 1), (0, 2), (1, 2)))),
        "nerve_reduced_betti": (reduced_betti(balanced_facets(COUNTEREXAMPLE_ZERO)),
                                reduced_betti(balanced_facets(COUNTEREXAMPLE_ONE))),
    }


def nerve_incidence_corank(cells) -> int:
    """``|facets| - rank`` of the vertex-facet incidence of the nerve with the colours erased.

    The one-way margin map *is* this incidence matrix (a block is a vertex, a
    cell a facet), so the separate fibre is a combinatorial invariant of the
    uncoloured nerve; the vertices are renamed here to make that visible.
    """

    facets = [frozenset(f) for f in balanced_facets(cells)]
    rng = random.Random(len(facets))
    names = sorted({v for f in facets for v in f})
    rng.shuffle(names)
    anonymous = {v: i for i, v in enumerate(names)}
    rows = [[int(any(anonymous[u] == i for u in f)) for f in facets] for i in range(len(names))]
    return len(facets) - rank(rows)


def homological_span(cells) -> dict[str, int]:
    """Dimension of the sum of the homological sub-kernels inside the separate fibre (three maps).

    The sub-kernels are the fibres of the finer patterns covered by Theorem 7
    after merging: all pairs jointly (top cycles of the nerve), two pairs
    sharing a map (link cycles), and one pair jointly with the third map
    (merged-colour graph cycles).
    """

    cells = sorted(set(map(tuple, cells)))
    patterns = {"top": ((0, 1), (0, 2), (1, 2))}
    for j in range(3):
        a, b = [x for x in range(3) if x != j]
        patterns[f"links_{j}"] = (tuple(sorted((j, a))), tuple(sorted((j, b))))
        patterns[f"merged_{a}{b}"] = ((a, b), (j,))
    vectors = []
    sizes = {}
    for name, faces in patterns.items():
        basis = nullspace(margin_rows_k(cells, faces), len(cells))
        sizes[name] = len(basis)
        vectors.extend(basis)
    return {"span": rank(vectors) if vectors else 0, "fibre": separate_fibre(cells), **sizes}


NONLOCAL_SUPPORT = ((0, 0, 0), (0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 0))


def nonlocal_fixture(grids=((2, 2, 2), (2, 2, 3))) -> dict[str, object]:
    report = {"witness": NONLOCAL_SUPPORT, "witness_span": homological_span(NONLOCAL_SUPPORT)}
    for dims in grids:
        seen = gaps = 0
        smallest = None
        for cells in supports_in_grid(dims):
            seen += 1
            span = homological_span(cells)
            if span["fibre"] != span["span"]:
                gaps += 1
                smallest = len(cells) if smallest is None else min(smallest, len(cells))
        report["x".join(map(str, dims))] = {"supports": seen, "fibre_exceeds_homological_span": gaps,
                                            "smallest_such_support": smallest}
    return report


def _record_for_counts(cells_items, counts) -> str:
    passing = {item for items, count in zip(cells_items, counts) for item in items[:count]}
    total = sum(len(items) for items in cells_items)
    return "".join("1" if i in passing else "0" for i in range(total))


def _cell_items(cells, sizes):
    """Item lists per cell under the numbering of ``category_maps_from_support``."""

    items, start = [], 0
    for size in sizes:
        items.append(tuple(range(start, start + size)))
        start += size
    return items


def integrality_fixture() -> dict[str, object]:
    """Whether separate observation of three maps is strict depends on cell sizes, not only the support."""

    cells = sorted(NONLOCAL_SUPPORT)
    generator = primitive_integer_vector(nullspace(margin_rows_k(cells, separate_faces(3)), len(cells))[0])
    unit_maps, unit_items = category_maps_from_support(cells)
    separate = join(join(category_channel(unit_maps[0], unit_items), category_channel(unit_maps[1], unit_items)),
                    category_channel(unit_maps[2], unit_items))
    doubled_sizes = tuple(2 if abs(v) == 2 else 1 for v in generator)
    big_maps, big_items = category_maps_from_support(cells, doubled_sizes)
    big_separate = join(join(category_channel(big_maps[0], big_items), category_channel(big_maps[1], big_items)),
                        category_channel(big_maps[2], big_items))
    big_joint = category_channel(tuple(_cell_items(cells, doubled_sizes)), big_items)
    positive = tuple(max(v, 0) for v in generator)
    negative = tuple(max(-v, 0) for v in generator)
    cell_items = _cell_items(cells, doubled_sizes)
    first, second = _record_for_counts(cell_items, positive), _record_for_counts(cell_items, negative)
    block_of = {r: index for index, block in enumerate(big_separate) for r in block}
    joint_of = {r: index for index, block in enumerate(big_joint) for r in block}
    grid_count = strict = loose = 0
    for support in supports_in_grid((2, 2, 2)):
        support = sorted(support)
        if separate_fibre(support) == 0:
            continue
        grid_count += 1
        seen: dict = {}
        is_strict = False
        for table in product((0, 1), repeat=len(support)):
            key = tuple(tuple(sum(t for t, c in zip(table, support) if c[j] == b) for b in (0, 1)) for j in range(3))
            if seen.setdefault(key, table) != table:
                is_strict = True
                break
        strict += is_strict
        loose += not is_strict
    return {
        "support": tuple(cells), "fibre_dimension": separate_fibre(cells), "kernel_generator": generator,
        "unit_cells_items": unit_items,
        "unit_cells_separate_equals_item_level": separate == item_level_partition(unit_items),
        "doubled_sizes": doubled_sizes, "doubled_items": big_items,
        "doubled_separate_strictly_coarser": big_separate != big_joint and all(
            any(block <= other for other in big_separate) for block in big_joint),
        "witness_records": (first, second),
        "witness_confused_by_separate": block_of[first] == block_of[second],
        "witness_separated_by_joint": joint_of[first] != joint_of[second],
        "grid_222_positive_fibre_supports": grid_count,
        "grid_222_unit_cells_strict": strict, "grid_222_unit_cells_not_strict": loose,
    }


RP2_SIX_VERTEX = ((1, 2, 3), (1, 2, 4), (1, 3, 5), (1, 4, 6), (1, 5, 6),
                  (2, 3, 6), (2, 4, 5), (2, 5, 6), (3, 4, 5), (3, 4, 6))


def barycentric_support(triangles) -> tuple[tuple[tuple, ...], tuple[tuple[int, int, int], ...]]:
    """Flags vertex < edge < triangle of a 2-complex, as cells of three category maps
    (vertices, edges, triangles); the nerve of that support is the barycentric subdivision."""

    triangles = tuple(sorted(tuple(sorted(t)) for t in triangles))
    vertices = sorted({v for t in triangles for v in t})
    edges = sorted({e for t in triangles for e in combinations(t, 2)})
    cells = sorted((vertices.index(v), edges.index(e), ti)
                   for ti, t in enumerate(triangles) for e in combinations(t, 2) for v in e)
    return triangles, tuple(cells)


def rp2_fixture(line=(1, 2, 5), apex=7) -> dict[str, object]:
    """Pairwise-joint observation of three maps on the flags of RP^2 with a disk on a projective line."""

    if tuple(sorted(line)) in RP2_SIX_VERTEX:
        raise ValueError("the line must be a non-face 3-cycle")
    a, b, c = sorted(line)
    cone = ((a, b, apex), (a, c, apex), (b, c, apex))
    triangles, cells = barycentric_support(RP2_SIX_VERTEX + cone)
    cone_index = {triangles.index(tuple(sorted(t))) for t in cone}
    pairs = ((0, 1), (0, 2), (1, 2))
    basis = nullspace(margin_rows_k(cells, pairs), len(cells))
    generator = primitive_integer_vector(basis[0]) if len(basis) == 1 else None
    on_cone = [abs(v) for v, cell in zip(generator, cells) if cell[2] in cone_index] if generator else []
    off_cone = [abs(v) for v, cell in zip(generator, cells) if cell[2] not in cone_index] if generator else []
    sizes = tuple(2 if cell[2] in cone_index else 1 for cell in cells)
    maps, items = category_maps_from_support(cells, sizes)
    cell_items = _cell_items(cells, sizes)
    first = _record_for_counts(cell_items, tuple(max(v, 0) for v in generator))
    second = _record_for_counts(cell_items, tuple(max(-v, 0) for v in generator))

    def counts(record, colours):
        table: dict = {}
        for cell, members in zip(cells, cell_items):
            key = tuple(cell[j] for j in colours)
            table[key] = table.get(key, 0) + sum(record[i] == "1" for i in members)
        return table

    return {
        "line": (a, b, c), "cells": len(cells), "items_with_doubled_cone": items,
        "blocks_per_map": tuple(len(m) for m in maps),
        "complex_reduced_betti": reduced_betti(triangles),
        "nerve_reduced_betti": reduced_betti(balanced_facets(cells)),
        "pairwise_fibre_dimension": len(basis),
        "link_formula_value": link_formula(cells, (0, 1, 2)),
        "generator_max_on_cone": max(on_cone) if on_cone else None,
        "generator_min_on_cone": min(on_cone) if on_cone else None,
        "generator_values_off_cone": tuple(sorted(set(off_cone))),
        "unit_cells_pairwise_observation_is_item_level": generator is not None and max(map(abs, generator)) == 2,
        "doubled_cone_witness_same_pairwise_margins": all(counts(first, p) == counts(second, p) for p in pairs),
        "doubled_cone_witness_different_cells": counts(first, (0, 1, 2)) != counts(second, (0, 1, 2)),
    }


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def rank_cross_check(count: int = 400, seed: int = 3) -> dict[str, int]:
    """Bareiss rank against fraction elimination on random small integer matrices."""

    rng = random.Random(seed)
    agree = 0
    for _ in range(count):
        rows, columns = rng.randint(1, 7), rng.randint(1, 7)
        density = rng.choice((0.3, 0.6, 1.0))
        matrix = [[rng.randint(-3, 3) if rng.random() < density else 0 for _ in range(columns)] for _ in range(rows)]
        if rng.random() < 0.3 and rows > 1:
            matrix[-1] = [a + b for a, b in zip(matrix[0], matrix[-2])]
        agree += rank(matrix) == rank_by_fractions(matrix)
    return {"matrices": count, "agree": agree}


def verify() -> dict[str, object]:
    """Run every exact fixture and return machine-readable checks."""

    algebra = rank_cross_check()
    two = two_map_fixture()
    cost = cost_fixture()
    asymptotic = asymptotic_fixture()
    ehrhart = ehrhart_fixture()
    full = full_support_fixture()
    patterns = pattern_fixture()
    sequence = projection_fixture()
    counter = counterexample_fixture()
    nonlocal_ = nonlocal_fixture()
    integral = integrality_fixture()
    rp2 = rp2_fixture()
    blocks = block_fixture()
    incidence = sum(nerve_incidence_corank(cells) == separate_fibre(cells) for cells in supports_in_grid((2, 2, 3)))
    identity = cost["identities"]
    distinct = cost["distinct_values_by_cycle_rank_up_to_five_items"]
    witnesses = cost["witnesses"]
    beta_one = [witnesses[name] for name in ("C6_unit", "C4_sizes_3111", "C4_sizes_2211_same_row",
                                             "C4_sizes_2112_diagonal", "C4_unit_with_pendant_path")]
    seqs = counter["projection_sequences"]
    checks = {
        "bareiss_rank_agrees_with_fraction_elimination": algebra["agree"] == algebra["matrices"],
        "fibre_dimension_equals_cycle_rank_all_pairs_up_to_six_items": _all_pass(two),
        "fundamental_cycles_are_an_integral_kernel_basis":
            all(row["fundamental_cycles_integral_kernel_basis"] == row["ordered_pairs"] for row in two.values()),
        "integer_fibres_attain_affine_dimension_cycle_rank":
            all(row["max_fibre_affine_dimension_equals_cycle_rank"] == row["ordered_pairs"]
                for key, row in two.items() if "max_fibre_affine_dimension_equals_cycle_rank" in row),
        "integer_fibres_connected_by_single_cycle_swaps":
            all(row["fibres_connected_by_simple_cycle_swaps"] == row["ordered_pairs"]
                for row in two.values() if "fibres_connected_by_simple_cycle_swaps" in row),
        "margins_and_cells_reproduce_lattice_channels":
            all(row["separate_partition_is_join_of_channels"] == row["joint_partition_is_refined_channel"]
                == row["ordered_pairs"] for row in two.values() if "joint_partition_is_refined_channel" in row),
        "completion_by_cell_counts_iff_remaining_cells_form_a_forest":
            identity["completion_iff_forest"] == identity["pairs"],
        "minimum_completion_size_is_cycle_rank": identity["minimum_completion_is_cycle_rank"] == identity["pairs"],
        "minimum_completions_are_maximal_spanning_forests":
            identity["minimum_completions_are_maximal_forests"] == identity["matrix_tree_count_matches"]
            == identity["pairs"],
        "confusion_is_a_sum_over_the_integer_cycle_lattice":
            identity["lattice_sum_equals_direct_uniform"] == identity["lattice_sum_equals_direct_one_third"]
            == identity["zero_term_is_joint"] == identity["vandermonde_pair_counts"] == identity["pairs"],
        "confusion_excess_positive_iff_a_cycle": identity["excess_positive_iff_cycle"] == identity["pairs"],
        "dimension_completion_size_lattice_rank_depend_only_on_cycle_rank":
            all(row["fibre_dimension"] == row["minimum_completion_size"] == row["lattice_rank"] == 1
                for row in distinct.values()),
        "confusion_guessing_and_completion_counts_depend_on_more_than_cycle_rank":
            distinct["1"]["confusion_excess"] > 1 and distinct["1"]["collision_ratio"] > 1
            and all(len({w[key] for w in beta_one}) > 1 for key in (
                "confusion_excess", "collision_ratio", "minimum_completions", "record_guess_gap",
                "cell_guess_error", "merged_classes")),
        "collision_ratio_closed_form_on_cycles_and_multiplicative_over_blocks":
            blocks["unit_cycle_closed_form_one_plus_two_to_one_minus_length"]
            and blocks["single_cycle_depends_on_size_multiset_only"] and blocks["single_cycle_sum_formula"]
            and blocks["bridges_do_not_change_the_ratio"] and blocks["vertex_joined_blocks_multiply"]
            and blocks["disjoint_blocks_multiply"] and blocks["same_cycle_rank_different_ratio"],
        "cotree_determinant_identity_all_pairs": identity["cotree_identity_unit_and_size_weights"] == identity["pairs"],
        "collision_ratio_normalized_decreases_to_pi_power_on_trend":
            all(row["decreasing"] and row["above_pi_power"] and row["relative_excess_at_largest_scale_below_one_tenth"]
                and row["determinant_identity"] for row in asymptotic.values()),
        "fibre_count_polynomial_of_degree_cycle_rank": all(row["degree_is_cycle_rank"] for row in ehrhart.values()),
        "full_support_fibre_is_anova_count_and_join_homology":
            all(row["formula_matches"] == row["patterns"] and row["top_betti_of_rank_selected_joins"]
                for row in full.values()),
        "single_nonface_patterns_are_link_homology_after_reduction":
            all(row["mismatches"] == 0 == row["direct_link_formula_mismatches"] and row["comparisons"] > 0
                for row in patterns["checks"].values()),
        "every_three_map_pattern_but_separate_is_homological":
            patterns["classification"]["3"]["uncovered"] == (((0,), (1,), (2,)),)
            and patterns["classification"]["2"]["kinds"].get("other", 0) == 0,
        "projection_sequence_formula_exact":
            all(row["formula_holds"] == row["orders"] == row["psi_rank_within_bounds"] for row in sequence.values())
            and any(row["psi_rank_positive"] > 0 for row in sequence.values()),
        "separate_fibre_not_a_function_of_natural_homotopy_types":
            counter["families_equal"] and counter["separate_fibres"] == (0, 1)
            and counter["zero_separate_observation_is_item_level"]
            and counter["one_witness_confused_by_separate_observation"]
            and counter["family"]["nerve_collapses_to_dimension"] == 1
            and seqs[0]["psi_rank"] == 1 and seqs[1]["psi_rank"] == 0
            and counter["two_way_fibres"] == (0, 0),
        "separate_fibre_has_vectors_outside_every_homological_subkernel":
            nonlocal_["witness_span"]["span"] == 0 and nonlocal_["witness_span"]["fibre"] == 1
            and nonlocal_["2x2x2"]["smallest_such_support"] == 5,
        "three_map_strictness_depends_on_cell_sizes_not_support":
            integral["fibre_dimension"] == 1 and integral["kernel_generator"] == (1, -2, 1, 1, -1)
            and integral["unit_cells_separate_equals_item_level"]
            and integral["doubled_separate_strictly_coarser"]
            and integral["witness_confused_by_separate"] and integral["witness_separated_by_joint"]
            and integral["grid_222_unit_cells_not_strict"] > 0,
        "rp2_cone_fibre_is_homological_but_integral_generator_has_a_two":
            rp2["pairwise_fibre_dimension"] == 1 == rp2["link_formula_value"]
            and rp2["complex_reduced_betti"] == (0, 0, 1) == rp2["nerve_reduced_betti"]
            and rp2["generator_max_on_cone"] == rp2["generator_min_on_cone"] == 2
            and rp2["generator_values_off_cone"] == (1,)
            and rp2["unit_cells_pairwise_observation_is_item_level"]
            and rp2["doubled_cone_witness_same_pairwise_margins"]
            and rp2["doubled_cone_witness_different_cells"],
        "separate_fibre_is_corank_of_uncoloured_nerve_incidence":
            incidence == 3271 and counter["nerve_incidence_coranks"] == (0, 1),
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "rank_cross_check": algebra, "two_maps": two, "cost": cost, "asymptotic": asymptotic,
            "ehrhart": ehrhart, "full_support": full, "patterns": patterns, "projection_sequence": sequence,
            "counterexample": counter, "nonlocal": nonlocal_, "integrality": integral, "rp2_cone": rp2,
            "collision_blocks": blocks,
            "nerve_incidence_identity": {"supports_2x2x3": 3271, "agree": incidence}}
