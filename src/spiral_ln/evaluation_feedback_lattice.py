"""Partial leakage as a lattice of deterministic feedback channels.

Nothing in this module calls a model, trains a learner, or runs a loop.  It
extends ``evaluation_game_feedback`` with exact fixtures for feedback channels
that reveal more than a score and less than the items.

1.  A deterministic feedback channel on outcome records ``{0,1}^n`` is a
    function ``f``; two channels carry the same information exactly when they
    have the same kernel partition ``ker f``, so channels are identified with
    partitions of the record set.  The *information order* used throughout is
    ``p <= q`` when ``q`` refines ``p`` (every block of ``q`` lies in a block of
    ``p``).  Under this convention the one-block partition (``sealed``) is the
    bottom and the discrete partition (``item_level``) is the top; ``join`` is
    the common refinement (observing both channels) and ``meet`` is the finest
    common coarsening (connected components of the union of the two
    equivalence relations).  This is the partition lattice with its usual
    orientation reversed.  The lattice data-processing law says total
    variation between two pushforwards is monotone in this order; its converse
    says the order is exactly total-variation domination.

2.  A category map on the item set induces the channel "per-category score
    vector".  The induced map from item partitions to record partitions is an
    order embedding whose image lies between ``score_only`` (one category) and
    ``item_level`` (singleton categories).  It preserves meets, and it
    preserves joins exactly when the bipartite intersection graph of the two
    category maps is a forest: otherwise two category leaks taken together
    are strictly coarser than one leak with the common refinement of the
    categories, and a cycle of the graph yields two records with equal
    margins and different cells.

3.  Under category leakage the loop knows each category's failure count and
    patches at random within a category.  Patches are drawn without
    replacement; a patch on an already-passed item gains nothing.  The
    expected number of failures hit by ``m`` patches in a category of ``n_c``
    items with ``F_c`` failures is exactly ``m F_c / n_c`` (the hypergeometric
    mean), so the expected selection score is exact and the greedy schedule by
    failure rate maximizes it at every patch count.  The patch count at which
    the *expected* score reaches the noise ceiling is a deterministic rational
    ``m*``; the patch count at which the *realized* score first reaches it is a
    stopping time whose exact expectation is a negative-hypergeometric mean,
    never above ``m*``.  Adaptive schedules that re-query the channel after
    every patch are solved exactly by dynamic programming on category counts:
    the greedy one, and the optimal one, which is monotone along refinement
    because a finer-informed loop can imitate any coarser policy.  With one
    hit needed the optimum is the best finisher, ``(n_c+1)/(F_c+1)``
    minimized over the categories with ``F_c >= 1``, in closed form; greedy by rate is optimal when every failure must be hit
    and not in general, not even at one hit.  With two hits needed the
    optimum commits to one category until it hits and is again a closed
    form, computable in time linear in the item count; committing until a
    hit is optimal at every state exactly when at most two hits are needed.

4.  ``audit_category_ledger`` wraps ``audit_ledger`` with a
    ``category_feedback`` event kind that records the partition used.

Boundaries.  Deterministic channels only: a stochastic channel is a Markov
kernel, for which the total-variation contraction still holds
(``_pushforward`` in the testbed), but which has no kernel partition, no
lattice position, and no converse.  Items are independent, and a patch changes
its own item only; a learner with collateral effects, such as the
nearest-neighbour simulation under ``output/eval_reuse_toys``, lies outside
every formula here.  Rational values are exact; nothing is sampled.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q
from functools import lru_cache
from itertools import combinations_with_replacement, product
from math import ceil, comb, floor, lcm

from spiral_ln.evaluation_game_feedback import (
    EvalSet, LoopEvent, access_kernel, audit_ledger, ceiling_detection_threshold,
    noise_ceiling, observed_accuracy, targeted_ceiling_detection_threshold,
)
from spiral_ln.evaluation_game_testbed import _pushforward, _tv

Partition = frozenset  # a frozenset of frozensets


# ---------------------------------------------------------------------------
# 1. Partitions, the information order, and the lattice data-processing law
# ---------------------------------------------------------------------------

def records(items: int) -> tuple[str, ...]:
    """All outcome records on ``items`` items; ``1`` is a pass, ``0`` a failure."""

    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")
    return tuple("".join(bits) for bits in product("01", repeat=items))


def validate_partition(blocks, elements=None) -> Partition:
    """Canonical partition from an iterable of blocks.

    Raises unless the blocks are nonempty and pairwise disjoint and, when
    ``elements`` is given, cover exactly that set.
    """

    canonical, seen = [], set()
    for block in blocks:
        block = frozenset(block)
        if not block:
            raise ValueError("partition blocks must be nonempty")
        if block & seen:
            raise ValueError("partition blocks must be disjoint")
        seen |= block
        canonical.append(block)
    if not canonical:
        raise ValueError("a partition needs at least one block")
    if elements is not None and seen != set(elements):
        raise ValueError("partition must cover exactly the given elements")
    return frozenset(canonical)


def ground(partition: Partition) -> frozenset:
    """The set a partition partitions."""

    return frozenset().union(*partition)


def render_partition(partition: Partition) -> tuple[tuple, ...]:
    """Deterministic rendering: sorted blocks of sorted elements."""

    return tuple(sorted(tuple(sorted(block)) for block in partition))


def partition_from_function(function, elements) -> Partition:
    """Kernel partition ``ker f``: elements with equal images share a block."""

    fibres: dict = {}
    for element in elements:
        fibres.setdefault(function(element), []).append(element)
    return validate_partition(fibres.values(), elements)


def partition_from_kernel(kernel: dict[str, dict[str, Q]]) -> Partition:
    """Kernel partition of a deterministic Markov kernel (point-mass rows)."""

    for row in kernel.values():
        if len(row) != 1 or next(iter(row.values())) != 1:
            raise ValueError("kernel must be deterministic")
    return partition_from_function(lambda record: next(iter(kernel[record])), kernel)


def all_partitions(elements) -> tuple[Partition, ...]:
    """Every partition of a finite set, by restricted growth; Bell(n) of them."""

    elements = tuple(elements)
    if not elements or len(set(elements)) != len(elements):
        raise ValueError("elements must be distinct and nonempty")
    found: list[Partition] = []

    def extend(index: int, blocks: list[list]) -> None:
        if index == len(elements):
            found.append(frozenset(frozenset(block) for block in blocks))
            return
        for block in blocks:
            block.append(elements[index])
            extend(index + 1, blocks)
            block.pop()
        blocks.append([elements[index]])
        extend(index + 1, blocks)
        blocks.pop()

    extend(0, [])
    return tuple(found)


def refines(fine: Partition, coarse: Partition) -> bool:
    """``fine`` refines ``coarse``: each block of ``fine`` lies in a block of ``coarse``."""

    if ground(fine) != ground(coarse):
        raise ValueError("partitions must share a ground set")
    index = {element: number for number, block in enumerate(coarse) for element in block}
    return all(len({index[element] for element in block}) == 1 for block in fine)


def below(coarse: Partition, fine: Partition) -> bool:
    """Information order: ``coarse <= fine`` exactly when ``fine`` refines ``coarse``."""

    return refines(fine, coarse)


def join(left: Partition, right: Partition) -> Partition:
    """Least upper bound in the information order: the common refinement."""

    if ground(left) != ground(right):
        raise ValueError("partitions must share a ground set")
    return frozenset(a & b for a in left for b in right if a & b)


def meet(left: Partition, right: Partition) -> Partition:
    """Greatest lower bound in the information order: the finest common
    coarsening, i.e. the connected components of the union of the two
    equivalence relations."""

    if ground(left) != ground(right):
        raise ValueError("partitions must share a ground set")
    parent = {element: element for element in ground(left)}

    def find(element):
        while parent[element] != element:
            parent[element] = parent[parent[element]]
            element = parent[element]
        return element

    for block in list(left) + list(right):
        anchor = find(next(iter(block)))
        for element in block:
            parent[find(element)] = anchor
    components: dict = {}
    for element in parent:
        components.setdefault(find(element), []).append(element)
    return frozenset(frozenset(block) for block in components.values())


def block_label(block) -> str:
    return "|".join(sorted(map(str, block)))


def channel_kernel(partition: Partition) -> dict[str, dict[str, Q]]:
    """Deterministic kernel of a partition channel, in the testbed's format."""

    return {element: {block_label(block): Q(1)} for block in partition for element in block}


def tv_through(partition: Partition, left: dict[str, Q], right: dict[str, Q]) -> Q:
    """Total variation between two record distributions after the channel."""

    kernel = channel_kernel(partition)
    return _tv(_pushforward(left, kernel), _pushforward(right, kernel))


def sealed_partition(items: int) -> Partition:
    return validate_partition([records(items)])


def score_only_partition(items: int) -> Partition:
    return partition_from_function(lambda record: record.count("1"), records(items))


def item_level_partition(items: int) -> Partition:
    return validate_partition([[record] for record in records(items)])


def rational_simplex(support, steps: int) -> tuple[dict, ...]:
    """Every distribution on ``support`` with masses in multiples of ``1/steps``."""

    if type(steps) is not int or steps < 1:
        raise ValueError("steps must be a positive integer")
    support = tuple(support)
    return tuple(
        {key: Q(count, steps) for key, count in zip(support, counts) if count}
        for counts in product(range(steps + 1), repeat=len(support))
        if sum(counts) == steps
    )


def lattice_fixture(items: int = 2, steps: int = 2) -> dict[str, object]:
    """Exhaustive check of the lattice data-processing law and its converse.

    For every ordered pair of partitions of ``{0,1}^items`` and every pair of
    distributions on the rational grid, total variation through the coarser
    channel is at most that through the finer; for every ordered pair that is
    not comparable in that direction a grid pair witnesses the failure.  The
    join and meet are checked against their lattice definitions.
    """

    space = records(items)
    partitions = all_partitions(space)
    grid = rational_simplex(space, steps)
    pairs = tuple(product(grid, repeat=2))
    table = {p: tuple(tv_through(p, left, right) for left, right in pairs) for p in partitions}
    comparable = incomparable = 0
    law_holds = converse_holds = True
    for p, q in product(partitions, repeat=2):
        if below(p, q):
            comparable += 1
            law_holds &= all(a <= b for a, b in zip(table[p], table[q]))
        else:
            incomparable += 1
            converse_holds &= any(a > b for a, b in zip(table[p], table[q]))
    lattice_ok = bounds_ok = True
    for p, q in product(partitions, repeat=2):
        upper, lower = join(p, q), meet(p, q)
        lattice_ok &= (refines(upper, p) and refines(upper, q)
                       and all(refines(r, upper) for r in partitions
                               if refines(r, p) and refines(r, q)))
        lattice_ok &= (refines(p, lower) and refines(q, lower)
                       and all(refines(lower, r) for r in partitions
                               if refines(p, r) and refines(q, r)))
        bounds_ok &= all(u >= max(a, b) and l <= min(a, b)
                         for u, l, a, b in zip(table[upper], table[lower], table[p], table[q]))
    sealed, score, item = sealed_partition(items), score_only_partition(items), item_level_partition(items)
    return {
        "convention": "p <= q when q refines p; bottom = one block (sealed); top = discrete "
                      "(item_level); join = common refinement; meet = finest common coarsening",
        "items": items, "record_count": len(space), "bell_number": len(partitions),
        "grid_size": len(grid), "distribution_pairs": len(pairs),
        "ordered_pairs_below": comparable, "ordered_pairs_not_below": incomparable,
        "law_holds_on_every_comparable_pair": law_holds,
        "domination_fails_on_every_noncomparable_pair": converse_holds,
        "join_and_meet_satisfy_lattice_definitions": lattice_ok,
        "join_meet_tv_bounds_hold": bounds_ok,
        "sealed_is_bottom": all(below(sealed, p) for p in partitions),
        "item_level_is_top": all(below(p, item) for p in partitions),
        "score_only_strictly_between": below(sealed, score) and below(score, item)
                                       and score not in (sealed, item),
        "existing_access_kernels_match": all(
            partition_from_kernel(access_kernel(access, items)) == reference
            for access, reference in (("sealed", sealed), ("score_only", score), ("item_level", item))),
        "sealed": render_partition(sealed), "score_only": render_partition(score),
        "item_level": render_partition(item),
    }


# ---------------------------------------------------------------------------
# 2. Category leakage: item partitions embed into the channel lattice
# ---------------------------------------------------------------------------

def validate_categories(categories, items: int) -> tuple[tuple[int, ...], ...]:
    """Canonical category map: a partition of ``range(items)`` as sorted blocks."""

    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")
    partition = validate_partition(categories, range(items))
    if any(type(index) is not int for block in partition for index in block):
        raise ValueError("item indices must be integers")
    return tuple(sorted(tuple(sorted(block)) for block in partition))


def category_channel(categories, items: int) -> Partition:
    """Record partition induced by the per-category pass-count vector."""

    blocks = validate_categories(categories, items)
    return partition_from_function(
        lambda record: tuple(sum(record[index] == "1" for index in block) for block in blocks),
        records(items))


def all_category_maps(items: int) -> tuple[tuple[tuple[int, ...], ...], ...]:
    return tuple(validate_categories(p, items) for p in all_partitions(range(items)))


def _item_partition(categories, items: int) -> Partition:
    return validate_partition(validate_categories(categories, items), range(items))


def intersection_graph(left, right, items: int) -> dict[str, object]:
    """Bipartite graph on the blocks of two category maps: an edge joins a
    block of ``left`` to a block of ``right`` when they intersect, so edges
    are the cells of the common refinement."""

    rows, cols = validate_categories(left, items), validate_categories(right, items)
    edges = tuple((a, b) for a, row in enumerate(rows) for b, col in enumerate(cols)
                  if set(row) & set(col))
    return {"rows": rows, "columns": cols, "edges": edges}


def intersection_graph_is_forest(left, right, items: int) -> bool:
    """True iff the intersection graph is acyclic: edges = vertices - components."""

    graph = intersection_graph(left, right, items)
    vertices = [("r", a) for a in range(len(graph["rows"]))] + [("c", b) for b in range(len(graph["columns"]))]
    parent = {v: v for v in vertices}

    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    components = len(vertices)
    for a, b in graph["edges"]:
        ra, rb = find(("r", a)), find(("c", b))
        if ra != rb:
            parent[ra] = rb
            components -= 1
    return len(graph["edges"]) == len(vertices) - components


def intersection_cycle(left, right, items: int):
    """An alternating cycle of blocks ``(A_1, B_1, ..., A_k, B_k)`` in the
    intersection graph, as index pairs, or ``None`` when it is a forest."""

    graph = intersection_graph(left, right, items)
    adjacency: dict = {}
    for a, b in graph["edges"]:
        adjacency.setdefault(("r", a), []).append(("c", b))
        adjacency.setdefault(("c", b), []).append(("r", a))
    seen, parent = {}, {}
    for start in adjacency:
        if start in seen:
            continue
        stack = [(start, None)]
        while stack:
            node, origin = stack.pop()
            if node in seen:
                continue
            seen[node], parent[node] = True, origin
            for neighbour in adjacency[node]:
                if neighbour == origin:
                    continue
                if neighbour in seen:
                    # Close the cycle: walk both back to their common ancestor.
                    path_a, path_b = [node], [neighbour]
                    while path_a[-1] is not None:
                        path_a.append(parent[path_a[-1]])
                    while path_b[-1] is not None:
                        path_b.append(parent[path_b[-1]])
                    common = next(v for v in path_a if v in path_b)
                    cycle = path_a[:path_a.index(common) + 1] + path_b[:path_b.index(common)][::-1]
                    if cycle[0][0] == "c":
                        cycle = cycle[1:] + cycle[:1]
                    return tuple(cycle)
                stack.append((neighbour, node))
    return None


def join_failure_witness(left, right, items: int) -> dict[str, object]:
    """Two records with equal per-category counts under both maps and
    different counts on the common refinement, built from a cycle of the
    intersection graph: passes on the cycle's forward cells in one record and
    on its backward cells in the other."""

    cycle = intersection_cycle(left, right, items)
    if cycle is None:
        raise ValueError("the intersection graph is a forest; no witness exists")
    rows, cols = validate_categories(left, items), validate_categories(right, items)
    forward, backward = [], []
    k = len(cycle) // 2
    for i in range(k):
        a, b = cycle[2 * i][1], cycle[2 * i + 1][1]
        a_next = cycle[(2 * i + 2) % len(cycle)][1]
        forward.append(min(set(rows[a]) & set(cols[b])))
        backward.append(min(set(rows[a_next]) & set(cols[b])))
    first = "".join("1" if index in forward else "0" for index in range(items))
    second = "".join("1" if index in backward else "0" for index in range(items))
    return {"cycle": cycle, "first": first, "second": second}


def category_lattice_fixture(sizes=(3, 4, 5)) -> dict[str, object]:
    """Meet preservation and the forest criterion for joins, exhaustively.

    For every ordered pair of category maps on ``items`` items: the channel of
    the finest common coarsening equals the meet of the channels; the channel
    of the common refinement equals the join of the channels exactly when the
    intersection graph is a forest; and for every non-forest pair the cycle
    witness is confused by the join of the channels and separated by the
    channel of the refinement.
    """

    report = {}
    for items in sizes:
        maps = all_category_maps(items)
        channels = {m: category_channel(m, items) for m in maps}
        parts = {m: _item_partition(m, items) for m in maps}
        meets_kept = joins_kept = forests = agree = witnesses = 0
        for a, b in product(maps, repeat=2):
            meet_kept = category_channel(render_partition(meet(parts[a], parts[b])), items) == meet(channels[a], channels[b])
            join_kept = category_channel(render_partition(join(parts[a], parts[b])), items) == join(channels[a], channels[b])
            forest = intersection_graph_is_forest(a, b, items)
            meets_kept += meet_kept
            joins_kept += join_kept
            forests += forest
            agree += join_kept == forest
            if not forest:
                witness = join_failure_witness(a, b, items)
                refined = category_channel(render_partition(join(parts[a], parts[b])), items)
                joint = join(channels[a], channels[b])
                first, second = {witness["first"]: Q(1)}, {witness["second"]: Q(1)}
                witnesses += (witness["first"] != witness["second"]
                              and tv_through(joint, first, second) == 0
                              and tv_through(refined, first, second) == 1)
        report[items] = {
            "ordered_pairs": len(maps) ** 2, "meet_preserved": meets_kept,
            "join_preserved": joins_kept, "forest_pairs": forests,
            "join_preserved_iff_forest_pairs": agree,
            "non_forest_pairs": len(maps) ** 2 - forests, "cycle_witnesses_valid": witnesses,
        }
    return report


def category_order_fixture() -> dict[str, object]:
    """Order embedding, endpoints, an incomparable pair, and a join failure."""

    endpoints = all(
        category_channel([range(items)], items) == score_only_partition(items)
        and category_channel([[i] for i in range(items)], items) == item_level_partition(items)
        for items in (1, 2, 3, 4))
    embedding, join_kept, meet_kept, pairs = {}, {}, {}, {}
    for items in (3, 4):
        maps = all_category_maps(items)
        channels = {m: category_channel(m, items) for m in maps}
        parts = {m: _item_partition(m, items) for m in maps}
        embedding[items] = all(
            refines(channels[a], channels[b]) == refines(parts[a], parts[b])
            for a, b in product(maps, repeat=2))
        joins = [category_channel(render_partition(join(parts[a], parts[b])), items)
                 == join(channels[a], channels[b]) for a, b in product(maps, repeat=2)]
        meets = [category_channel(render_partition(meet(parts[a], parts[b])), items)
                 == meet(channels[a], channels[b]) for a, b in product(maps, repeat=2)]
        join_kept[items], meet_kept[items], pairs[items] = sum(joins), sum(meets), len(joins)

    # Incomparable categories on three items: {0,1}|{2} against {0}|{1,2}.
    first, second = ((0, 1), (2,)), ((0,), (1, 2))
    channel_a, channel_b = category_channel(first, 3), category_channel(second, 3)
    only_item_0, only_item_1, only_item_2 = {"011": Q(1)}, {"101": Q(1)}, {"110": Q(1)}
    witness_b = {"A": tv_through(channel_a, only_item_0, only_item_1),
                 "B": tv_through(channel_b, only_item_0, only_item_1)}
    witness_a = {"A": tv_through(channel_a, only_item_1, only_item_2),
                 "B": tv_through(channel_b, only_item_1, only_item_2)}

    # Join failure on four items: rows {0,1}|{2,3} and columns {0,2}|{1,3}.
    rows, cols = ((0, 1), (2, 3)), ((0, 2), (1, 3))
    channel_rows, channel_cols = category_channel(rows, 4), category_channel(cols, 4)
    refined = category_channel(render_partition(join(_item_partition(rows, 4), _item_partition(cols, 4))), 4)
    joint = join(channel_rows, channel_cols)
    diagonal = {"1001": Q(1), "0110": Q(1)}
    return {
        "endpoints_are_score_only_and_item_level": endpoints,
        "order_embedding_exhaustive": embedding,
        "category_maps_checked": {items: len(all_category_maps(items)) for items in (3, 4)},
        "join_preserved_pairs": join_kept, "meet_preserved_pairs": meet_kept,
        "ordered_pairs": pairs,
        "incomparable_pair": {
            "A": first, "B": second,
            "neither_refines": not refines(channel_a, channel_b) and not refines(channel_b, channel_a),
            "fail_item_0_vs_fail_item_1": witness_b,
            "fail_item_1_vs_fail_item_2": witness_a,
            "A_separates_second_pair_only": witness_a["A"] == 1 and witness_b["A"] == 0,
            "B_separates_first_pair_only": witness_b["B"] == 1 and witness_a["B"] == 0,
        },
        "join_failure": {
            "rows": rows, "columns": cols,
            "refined_categories_give_item_level": refined == item_level_partition(4),
            "joint_leak_strictly_coarser": refines(refined, joint) and refined != joint,
            "records_confused_by_joint_leak": tuple(sorted(diagonal)),
            "tv_through_joint_leak": tv_through(joint, {"1001": Q(1)}, {"0110": Q(1)}),
            "tv_through_refined_categories": tv_through(refined, {"1001": Q(1)}, {"0110": Q(1)}),
        },
    }


# ---------------------------------------------------------------------------
# 3. Cost of a leak: patches to the noise ceiling under category feedback
# ---------------------------------------------------------------------------

def validate_category_counts(categories) -> tuple[tuple[int, int], ...]:
    """``(size, failures)`` per category with integer size >= 1 and 0 <= failures <= size."""

    counts = []
    for entry in categories:
        if len(entry) != 2:
            raise ValueError("each category is a (size, failures) pair")
        size, failures = entry
        if (type(size) is not int or type(failures) is not int
                or size < 1 or not 0 <= failures <= size):
            raise ValueError("each category needs integer size >= 1 and 0 <= failures <= size")
        counts.append((size, failures))
    if not counts:
        raise ValueError("at least one category required")
    return tuple(counts)


def category_counts(categories, record: str) -> tuple[tuple[int, int], ...]:
    """What the category channel reveals about one record: ``(size, failures)`` per category."""

    if type(record) is not str or set(record) - {"0", "1"}:
        raise ValueError("record must be a string of 0 and 1")
    blocks = validate_categories(categories, len(record))
    return tuple((len(block), sum(record[index] == "0" for index in block)) for block in blocks)


def conditional_hit_probability(size: int, failures: int, patched: int, hits: int) -> Q:
    """Probability that the next random patch in a category hits a still-failed
    item, given ``patched`` earlier patches of which ``hits`` hit.  This is the
    depleting, conditional rate; the unconditional expected gain of every patch
    is ``failures/size``."""

    validate_category_counts(((size, failures),))
    if (type(patched) is not int or type(hits) is not int or hits < 0 or patched < hits
            or patched >= size or hits > failures or patched - hits > size - failures):
        raise ValueError("inconsistent patch history")
    return Q(failures - hits, size - patched)


def _schedule(counts: tuple[tuple[int, int], ...]) -> tuple[int, ...]:
    # Rates compared exactly through a common denominator; ties by index.
    common = lcm(*(size for size, _ in counts))
    return tuple(sorted(range(len(counts)),
                        key=lambda i: (-counts[i][1] * (common // counts[i][0]), i)))


def greedy_schedule(categories) -> tuple[int, ...]:
    """Category indices in patch order: highest failure rate first, ties by index."""

    return _schedule(validate_category_counts(categories))


def expected_gain_per_patch(categories) -> tuple[Q, ...]:
    """Unconditional expected hits of each successive patch under the static
    greedy schedule: ``F_c/n_c`` for every patch spent in category ``c``."""

    counts = validate_category_counts(categories)
    return tuple(Q(counts[i][1], counts[i][0]) for i in _schedule(counts)
                 for _ in range(counts[i][0]))


def expected_hits_after(categories, patches) -> Q:
    """Expected failures hit after ``patches`` patches (rational; linear between
    integers) under the static greedy schedule.  Exact by the hypergeometric mean."""

    gains = expected_gain_per_patch(categories)
    patches = Q(patches)
    if not 0 <= patches <= len(gains):
        raise ValueError("patches must lie between zero and the set size")
    whole = int(patches)
    partial = gains[whole] if whole < len(gains) else Q(0)
    return sum(gains[:whole], Q(0)) + (patches - whole) * partial


def _crossing_segment(categories, hits_needed) -> dict[str, object]:
    counts = validate_category_counts(categories)
    needed = Q(hits_needed)
    if needed < 0:
        raise ValueError("hits needed must be nonnegative")
    if needed > sum(failures for _, failures in counts):
        raise ValueError("ceiling unreachable: more hits needed than failures exist")
    patches_before = hits_before = 0
    for index in _schedule(counts):
        size, failures = counts[index]
        if hits_before + failures >= needed:
            return {"category": index, "patches_before": patches_before,
                    "hits_before": hits_before, "size": size, "failures": failures,
                    "hits_in_segment": needed - hits_before}
        hits_before += failures
        patches_before += size
    raise AssertionError("unreachable")


def _crossing_from_segment(seg: dict[str, object]) -> Q:
    return seg["patches_before"] + seg["hits_in_segment"] * Q(seg["size"], seg["failures"])


def _static_from_segment(seg: dict[str, object]) -> Q:
    return seg["patches_before"] + seg["hits_in_segment"] * Q(seg["size"] + 1, seg["failures"] + 1)


def expected_score_crossing(categories, hits_needed) -> Q:
    """Patch count ``m*`` at which the expected hit count under the static greedy
    schedule reaches ``hits_needed``:
    ``N_<j + H_j n_j / F_j`` with ``j`` the first scheduled category whose
    cumulative failures reach the requirement.  Rational, possibly fractional."""

    if Q(hits_needed) == 0:
        validate_category_counts(categories)
        return Q(0)
    return _crossing_from_segment(_crossing_segment(categories, hits_needed))


def expected_patches_static(categories, hits_needed: int) -> Q:
    """Exact expected number of patches at which the realized hit count first
    reaches ``hits_needed`` under the static greedy schedule:
    ``N_<j + H_j (n_j + 1) / (F_j + 1)``, a negative-hypergeometric mean.  The
    expected-score crossing overstates this by exactly
    ``H_j (n_j - F_j) / (F_j (F_j + 1))``, which is below ``m* / (F_j + 1)``."""

    if type(hits_needed) is not int or hits_needed < 0:
        raise ValueError("hits needed must be a nonnegative integer")
    if hits_needed == 0:
        validate_category_counts(categories)
        return Q(0)
    return _static_from_segment(_crossing_segment(categories, hits_needed))


def crossing_error_bound(categories, hits_needed: int) -> dict[str, Q]:
    """The identity ``m* - E[T_static] = H_j (n_j - F_j) / (F_j (F_j + 1))`` and
    its bound, as a record."""

    if type(hits_needed) is not int or hits_needed < 0:
        raise ValueError("hits needed must be a nonnegative integer")
    if hits_needed == 0:
        validate_category_counts(categories)
        return {"expected_score_crossing": Q(0), "expected_patches_static": Q(0),
                "error": Q(0), "closed_form_error": Q(0), "bound": Q(0)}
    seg = _crossing_segment(categories, hits_needed)
    crossing, static = _crossing_from_segment(seg), _static_from_segment(seg)
    closed = seg["hits_in_segment"] * Q(seg["size"] - seg["failures"],
                                        seg["failures"] * (seg["failures"] + 1))
    return {"expected_score_crossing": crossing, "expected_patches_static": static,
            "error": crossing - static, "closed_form_error": closed,
            "bound": crossing / (seg["failures"] + 1)}


def expected_patches_adaptive(categories, hits_needed: int) -> Q:
    """Exact expected patches when the loop re-queries the category channel
    after every patch and always patches the category with the highest current
    failure rate among its unpatched items (ties: fewest remaining items).

    Dynamic programming on the multiset of ``(remaining, failures_left)`` pairs;
    categories with the same pair are exchangeable, so the choice among them
    does not affect the expectation.
    """

    counts = validate_category_counts(categories)
    if type(hits_needed) is not int or hits_needed < 0:
        raise ValueError("hits needed must be a nonnegative integer")
    if hits_needed > sum(failures for _, failures in counts):
        raise ValueError("ceiling unreachable: more hits needed than failures exist")
    return _adaptive_value(hits_needed, tuple(sorted(pair for pair in counts if pair[1] > 0)))


@lru_cache(maxsize=None)
def _adaptive_value(remaining_hits: int, state: tuple) -> Q:
    """Memoized value of the adaptive greedy schedule from a multiset state.

    The cache is shared across calls because a state means the same thing
    whichever category map produced it.
    """

    if remaining_hits == 0:
        return Q(0)
    chosen = max(state, key=lambda pair: (Q(pair[1], pair[0]), -pair[0]))
    size, failures = chosen
    rest = list(state)
    rest.remove(chosen)
    hit = Q(failures, size)
    after_hit = tuple(sorted(rest + ([(size - 1, failures - 1)] if failures > 1 else [])))
    result = 1 + hit * _adaptive_value(remaining_hits - 1, after_hit)
    if hit < 1:
        after_miss = tuple(sorted(rest + [(size - 1, failures)]))
        result += (1 - hit) * _adaptive_value(remaining_hits, after_miss)
    return result


def _continuation(remaining_hits: int, state: tuple, chosen: tuple, value) -> Q:
    """Expected patches from ``state`` when the next patch goes to ``chosen``
    and ``value`` prices every later state."""

    size, failures = chosen
    rest = list(state)
    rest.remove(chosen)
    hit = Q(failures, size)
    after_hit = tuple(sorted(rest + ([(size - 1, failures - 1)] if failures > 1 else [])))
    result = 1 + hit * value(remaining_hits - 1, after_hit)
    if hit < 1:
        after_miss = tuple(sorted(rest + [(size - 1, failures)]))
        result += (1 - hit) * value(remaining_hits, after_miss)
    return result


@lru_cache(maxsize=None)
def _optimal_value(remaining_hits: int, state: tuple) -> Q:
    """Minimum expected patches over every adaptive policy, by dynamic
    programming over the same multiset states as the greedy schedule."""

    if remaining_hits == 0:
        return Q(0)
    return min(_continuation(remaining_hits, state, chosen, _optimal_value)
               for chosen in set(state))


def _adaptive_state(categories, hits_needed: int) -> tuple:
    counts = validate_category_counts(categories)
    if type(hits_needed) is not int or hits_needed < 0:
        raise ValueError("hits needed must be a nonnegative integer")
    if hits_needed > sum(failures for _, failures in counts):
        raise ValueError("ceiling unreachable: more hits needed than failures exist")
    return tuple(sorted(pair for pair in counts if pair[1] > 0))


def optimal_adaptive_value(categories, hits_needed: int) -> Q:
    """Exact minimum expected number of patches over every adaptive policy
    that re-queries the category channel after each patch and patches a
    uniformly random unpatched item of the category it chooses.

    The greedy rule of ``expected_patches_adaptive`` is one such policy, so
    this value is at most the greedy value; it is strictly below it on some
    states (see ``greedy_vs_optimal_fixture``).
    """

    return _optimal_value(hits_needed, _adaptive_state(categories, hits_needed))


def optimal_first_choices(categories, hits_needed: int) -> tuple[tuple[int, int], ...]:
    """The ``(size, failures)`` pairs an optimal policy may patch first."""

    state = _adaptive_state(categories, hits_needed)
    if hits_needed == 0:
        return ()
    best = _optimal_value(hits_needed, state)
    return tuple(sorted(chosen for chosen in set(state)
                        if _continuation(hits_needed, state, chosen, _optimal_value) == best))


def last_failure_positions_sum(categories) -> Q:
    """``sum_c F_c (n_c + 1) / (F_c + 1)``: the expected patches any policy that
    never patches an exhausted category needs to hit every failure, since the
    patches spent in a category until its last failure are the position of
    that failure in a uniformly random order of the category's items."""

    counts = validate_category_counts(categories)
    return sum((Q(failures * (size + 1), failures + 1) for size, failures in counts if failures), Q(0))


def greedy_vs_optimal_fixture(items: int = 6) -> dict[str, object]:
    """Every failure pattern on a small set against every category map, for
    one hit, half the failures, and all failures.

    Reports whether the optimal adaptive value is at most the greedy adaptive
    value and that at most the static value; whether greedy equals optimal
    when one hit remains (the exchange argument) and when every failure must
    be hit (policy invariance); whether the optimal value is monotone along
    refinement (the simulation argument); and the first state where greedy
    is strictly worse than optimal, with the four-item witness.
    """

    maps = all_category_maps(items)
    parts = {m: _item_partition(m, items) for m in maps}
    cases = []
    for record in records(items):
        total = record.count("0")
        if total == 0:
            continue
        for required in sorted({1, ceil(Q(total, 2)), total}):
            cases.append((record, required))
    values = {}
    ordering_ok = one_hit_ok = all_hits_ok = True
    strict = 0
    witness = None
    for m in maps:
        blocks = validate_categories(m, items)
        rows = []
        for record, required in cases:
            counts = tuple((len(block), sum(record[index] == "0" for index in block))
                           for block in blocks)
            optimal = optimal_adaptive_value(counts, required)
            greedy = expected_patches_adaptive(counts, required)
            static = expected_patches_static(counts, required)
            ordering_ok &= optimal <= greedy <= static
            if required == 1:
                one_hit_ok &= optimal == greedy
            if required == record.count("0"):
                all_hits_ok &= optimal == greedy == last_failure_positions_sum(counts)
            if _greater(greedy, optimal):
                strict += 1
                witness = witness or {"map": m, "record": record, "hits_needed": required,
                                      "counts": counts, "greedy": greedy, "optimal": optimal,
                                      "optimal_first": optimal_first_choices(counts, required)}
            rows.append((optimal, greedy))
        values[m] = rows
    optimal_mono = greedy_mono = True
    refining_pairs = 0
    for fine, coarse in product(maps, repeat=2):
        if fine == coarse or not refines(parts[fine], parts[coarse]):
            continue
        refining_pairs += 1
        for fine_row, coarse_row in zip(values[fine], values[coarse]):
            if _greater(fine_row[0], coarse_row[0]):
                optimal_mono = False
            if _greater(fine_row[1], coarse_row[1]):
                greedy_mono = False
    four = ((4, 2), (2, 1))
    return {
        "items": items, "category_maps": len(maps), "cases_per_map": len(cases),
        "refining_pairs": refining_pairs,
        "optimal_le_greedy_le_static": ordering_ok,
        "greedy_equals_optimal_for_one_hit": one_hit_ok,
        "greedy_equals_optimal_equals_closed_form_for_all_hits": all_hits_ok,
        "cases_where_greedy_strictly_worse": strict, "first_witness": witness,
        "optimal_monotone_along_refinement": optimal_mono,
        "greedy_monotone_along_refinement": greedy_mono,
        "four_item_witness": {
            "counts": four, "hits_needed": 2,
            "greedy": expected_patches_adaptive(four, 2),
            "optimal": optimal_adaptive_value(four, 2),
            "optimal_first": optimal_first_choices(four, 2),
            "greedy_first": (2, 1),
        },
    }


def adaptive_states(max_size: int, max_categories: int, max_failures: int | None = None) -> tuple:
    """Every state the adaptive schedule can face with at most
    ``max_categories`` categories of size at most ``max_size`` (and, when
    given, at most ``max_failures`` failures each): a sorted multiset of
    ``(size, failures)`` pairs with ``1 <= failures <= size`` and a
    requirement from one hit up to every failure."""

    if (type(max_size) is not int or type(max_categories) is not int
            or max_size < 1 or max_categories < 1):
        raise ValueError("max_size and max_categories must be positive integers")
    if max_failures is not None and (type(max_failures) is not int or max_failures < 1):
        raise ValueError("max_failures must be a positive integer")
    cap = max_size if max_failures is None else max_failures
    pairs = [(size, failures) for size in range(1, max_size + 1) for failures in range(1, min(size, cap) + 1)]
    states = []
    for count in range(1, max_categories + 1):
        for combo in combinations_with_replacement(pairs, count):
            state = tuple(sorted(combo))
            total = sum(failures for _, failures in state)
            states.extend((required, state) for required in range(1, total + 1))
    return tuple(states)


def first_patch_values(hits_needed: int, state: tuple) -> dict[tuple[int, int], Q]:
    """Expected patches to ``hits_needed`` hits when the first patch goes to
    each distinct category of ``state`` and every later patch is optimal."""

    state = _adaptive_state(state, hits_needed)
    if hits_needed == 0:
        return {}
    return {chosen: _continuation(hits_needed, state, chosen, _optimal_value) for chosen in set(state)}


def _render_values(values: dict) -> tuple:
    return tuple((category, value) for category, value in sorted(values.items()))


INDEX_CONTEXTS = ("own_counts", "with_totals", "with_totals_and_category_count")


def _index_context(kind: str, state: tuple) -> tuple:
    if kind == "own_counts":
        return ()
    totals = (sum(size for size, _ in state), sum(failures for _, failures in state))
    if kind == "with_totals":
        return totals
    if kind == "with_totals_and_category_count":
        return totals + (len(state),)
    raise ValueError("unknown index context")


def preference_reversals(max_size: int, max_categories: int, context: str = "own_counts") -> dict[str, object]:
    """Pairs of categories ``A, B`` with a requirement (and whatever global
    context an index rule may see) such that patching ``A`` before ``B`` is
    strictly better in one state and strictly worse in another.

    A reversal by itself refutes nothing: in the better-for-``A`` state some
    third category may tie with ``A`` for the optimum, and a rule that ranks
    that category first is optimal there.  A pair *refutes* every index rule
    that scores a category by its own ``(size, failures)``, the requirement
    and that context (ties broken by any fixed order on those inputs) when
    ``A`` is the unique optimal first patch of one state containing ``B`` and
    ``B`` is the unique optimal first patch of another containing ``A``, both
    with the same requirement and context: an optimal rule would have to
    rank ``A`` above ``B`` in the first and ``B`` above ``A`` in the second.
    """

    if context not in INDEX_CONTEXTS:
        raise ValueError("unknown index context")
    states = adaptive_states(max_size, max_categories)
    seen: dict = {}
    unique: dict = {}
    for required, state in states:
        values = first_patch_values(required, state)
        distinct = sorted(values)
        for position, first in enumerate(distinct):
            for second in distinct[position + 1:]:
                sign = (values[first] > values[second]) - (values[first] < values[second])
                key = (first, second, required) + _index_context(context, state)
                seen.setdefault(key, {}).setdefault(sign, (state, values[first], values[second]))
        best = min(values.values())
        optimal = [c for c in distinct if values[c] == best]
        if len(optimal) == 1:
            for other in distinct:
                if other != optimal[0]:
                    key = (optimal[0], other, required) + _index_context(context, state)
                    unique.setdefault(key, (state, best, values[other]))
    reversals = []
    for key, by_sign in seen.items():
        if 1 in by_sign and -1 in by_sign:
            reversals.append({
                "A": key[0], "B": key[1], "hits_needed": key[2], "context": key[3:],
                "A_first_better_in": by_sign[-1][0], "A_first_values": by_sign[-1][1:],
                "B_first_better_in": by_sign[1][0], "B_first_values": by_sign[1][1:],
            })
    reversals.sort(key=lambda row: (row["hits_needed"], row["A"], row["B"], row["context"]))
    refuting = []
    for key, row in unique.items():
        a, b = key[0], key[1]
        mirrored = (b, a) + key[2:]
        if a < b and mirrored in unique:
            refuting.append({
                "A": a, "B": b, "hits_needed": key[2], "context": key[3:],
                "A_uniquely_optimal_in": row[0], "A_values": row[1:],
                "B_uniquely_optimal_in": unique[mirrored][0], "B_values": unique[mirrored][1:],
            })
    refuting.sort(key=lambda row: (row["hits_needed"], row["A"], row["B"], row["context"]))
    return {"max_size": max_size, "max_categories": max_categories, "context": context,
            "states": len(states), "reversals": len(reversals),
            "first": reversals[0] if reversals else None,
            "refuting_pairs": len(refuting), "first_refuting": refuting[0] if refuting else None}


def two_patch_value(hits_needed: int, state: tuple, first: tuple, second: tuple) -> Q:
    """Expected patches when the first patch goes to ``first``, the second to
    ``second`` (a different category, so it is untouched by the first patch),
    and every later patch is optimal.  Needs at least two hits, so the run
    cannot end before the second patch."""

    state = _adaptive_state(state, hits_needed)
    if hits_needed < 2:
        raise ValueError("two ordered patches need at least two hits")
    if first == second or first not in state or second not in state:
        raise ValueError("first and second must be distinct categories of the state")
    size, failures = first
    rest = list(state)
    rest.remove(first)
    hit = Q(failures, size)
    total = Q(0)
    for outcome, probability in ((True, hit), (False, 1 - hit)):
        if probability == 0:
            continue
        remaining = hits_needed - 1 if outcome else hits_needed
        updated = (size - 1, failures - 1) if outcome else (size - 1, failures)
        next_state = tuple(sorted(rest + ([updated] if updated[1] > 0 else [])))
        total += probability * (1 + _continuation(remaining, next_state, second, _optimal_value))
    return total


def pair_commutation_check(max_size: int, max_categories: int) -> dict[str, int]:
    """Over every state with at least two hits needed and every ordered pair
    of distinct categories, compare ``A`` then ``B`` with ``B`` then ``A``."""

    checked = violations = 0
    for required, state in adaptive_states(max_size, max_categories):
        if required < 2:
            continue
        distinct = sorted(set(state))
        for position, first in enumerate(distinct):
            for second in distinct[position + 1:]:
                checked += 1
                if two_patch_value(required, state, first, second) != two_patch_value(required, state, second, first):
                    violations += 1
    return {"pairs_checked": checked, "violations": violations}


def policy_structure_fixture(max_size: int = 5, max_categories: int = 4) -> dict[str, object]:
    """What the enumeration says about the shape of the optimal first patch:
    whether an extremal rule covers it, whether equal rates favour the larger
    category, and whether the lowest of several rates is ever the only
    optimal choice."""

    def rate(pair):
        return Q(pair[1], pair[0])

    def finisher(pair):
        return Q(pair[0] + 1, pair[1] + 1)

    outside_extremal = equal_rate_not_largest = lowest_rate_unique = 0
    extremal_witness = equal_rate_witness = lowest_witness = None
    states = adaptive_states(max_size, max_categories)
    for required, state in states:
        values = first_patch_values(required, state)
        best = min(values.values())
        optimal = {c for c, v in values.items() if v == best}
        distinct = sorted(values)
        extremal = {max(distinct, key=rate), max(distinct, key=lambda c: c[0]),
                    min(distinct, key=finisher), max(distinct, key=finisher)}
        if not optimal & extremal:
            outside_extremal += 1
            extremal_witness = extremal_witness or {"hits_needed": required, "state": state,
                                                    "optimal_first": tuple(sorted(optimal))}
        if required >= 2 and len(distinct) > 1 and len({rate(c) for c in distinct}) == 1:
            largest = max(c[0] for c in distinct)
            if not any(c[0] == largest for c in optimal):
                equal_rate_not_largest += 1
                equal_rate_witness = equal_rate_witness or {"hits_needed": required, "state": state,
                                                            "optimal_first": tuple(sorted(optimal))}
        rates = sorted({rate(c) for c in distinct})
        if len(rates) >= 3 and all(rate(c) == rates[0] for c in optimal):
            lowest_rate_unique += 1
            lowest_witness = lowest_witness or {"hits_needed": required, "state": state}
    return {"states": len(states), "commutation": pair_commutation_check(max_size, max_categories),
            "optimal_outside_extremal_rules": outside_extremal, "extremal_witness": extremal_witness,
            "equal_rates_largest_not_optimal": equal_rate_not_largest, "equal_rate_witness": equal_rate_witness,
            "lowest_of_three_rates_uniquely_optimal": lowest_rate_unique, "lowest_witness": lowest_witness}


def one_hit_value(categories) -> Q:
    """Exact minimum expected patches to one hit: ``min (n_c + 1)/(F_c + 1)``
    over the categories with ``F_c >= 1``.  Read over every category the
    formula is wrong: ``{(1,0),(10,1)}`` costs 11/2, not 2.  Patching a
    category without failures only wastes a patch.

    A miss in a category lowers that category's value from ``(n+1)/(F+1)``
    to ``n/(F+1)``, so the best finisher stays best and an optimal policy
    never switches; sticking with it costs ``(n+1)/(F+1)`` by the identity
    ``1 + (1 - F/n) n/(F+1) = (n+1)/(F+1)``.
    """

    counts = validate_category_counts(categories)
    if not any(failures for _, failures in counts):
        raise ValueError("no failure to hit")
    return min(Q(size + 1, failures + 1) for size, failures in counts if failures)


def best_finishers(categories) -> tuple[tuple[int, int], ...]:
    """The categories attaining ``one_hit_value``: the optimal first patches at one hit."""

    counts = validate_category_counts(categories)
    value = one_hit_value(counts)
    return tuple(sorted({pair for pair in counts if pair[1] and Q(pair[0] + 1, pair[1] + 1) == value}))


def one_hit_fixture(max_size: int = 8, max_categories: int = 4) -> dict[str, object]:
    """Checks the closed form against the dynamic programme on every state,
    and exhibits a state where the highest-rate category is not an optimal
    first patch at one hit."""

    states = [state for required, state in adaptive_states(max_size, max_categories) if required == 1]
    mismatches = sum(_optimal_value(1, state) != one_hit_value(state) for state in states)
    wrong_first = sum(
        not set(best_finishers(state)) <= {c for c, v in first_patch_values(1, state).items()
                                            if v == min(first_patch_values(1, state).values())}
        for state in states)
    witness_state = ((2, 1), (16, 9))
    witness = first_patch_values(1, witness_state)
    spent = ((1, 0), (10, 1))
    return {"states": len(states), "closed_form_mismatches": mismatches,
            "zero_failure_category_excluded": {
                "state": spent, "value": one_hit_value(spent),
                "dynamic_programme": optimal_adaptive_value(spent, 1),
                "minimum_over_every_category": min(Q(n + 1, f + 1) for n, f in spent),
                "holds": one_hit_value(spent) == optimal_adaptive_value(spent, 1) == Q(11, 2)
                         and min(Q(n + 1, f + 1) for n, f in spent) == 2,
            },
            "best_finisher_not_optimal_first": wrong_first,
            "rate_versus_finisher_witness": {
                "state": witness_state, "values": _render_values(witness),
                "rates": (((2, 1), Q(1, 2)), ((16, 9), Q(9, 16))),
                "finishers": (((2, 1), Q(3, 2)), ((16, 9), Q(17, 10))),
                "highest_rate_first_is_worse": witness[(16, 9)] > witness[(2, 1)] == one_hit_value(witness_state),
            }}


@lru_cache(maxsize=None)
def _commit_value(remaining_hits: int, state: tuple) -> Q:
    """Best value over policies that commit to one category until it hits,
    then re-decide; a miss never triggers a switch."""

    if remaining_hits == 0:
        return Q(0)
    best = None
    for chosen in set(state):
        size, failures = chosen
        rest = list(state)
        rest.remove(chosen)
        total, survive = Q(0), Q(1)
        for patch in range(1, size - failures + 2):
            remaining_items = size - (patch - 1)
            hit = Q(failures, remaining_items)
            after = (remaining_items - 1, failures - 1)
            next_state = tuple(sorted(rest + ([after] if after[1] > 0 else [])))
            total += survive * hit * (patch + _commit_value(remaining_hits - 1, next_state))
            survive *= 1 - hit
        if best is None or total < best:
            best = total
    return best


def commit_until_hit_value(categories, hits_needed: int) -> Q:
    """Exact minimum over the commit-until-hit policies; at least the optimum."""

    return _commit_value(hits_needed, _adaptive_state(categories, hits_needed))


def commit_until_hit_fixture(max_size: int = 7, max_categories: int = 3,
                             max_failures: int | None = None) -> dict[str, object]:
    """Where committing to a category until it hits is not optimal, and by how much."""

    states = adaptive_states(max_size, max_categories, max_failures)
    worse = 0
    largest = (Q(0), None)
    first = None
    by_hits: dict[int, int] = {}
    for required, state in states:
        optimal = _optimal_value(required, state)
        committed = _commit_value(required, state)
        if committed < optimal:
            raise AssertionError("commit-until-hit value below the optimum")
        if committed > optimal:
            worse += 1
            by_hits[required] = by_hits.get(required, 0) + 1
            gap = (committed - optimal) / optimal
            if gap > largest[0]:
                largest = (gap, {"hits_needed": required, "state": state, "optimal": optimal, "committed": committed})
            first = first or {"hits_needed": required, "state": state, "optimal": optimal, "committed": committed}
    return {"states": len(states), "commit_until_hit_suboptimal": worse,
            "suboptimal_by_hits_needed": tuple(sorted(by_hits.items())),
            "first_witness": first, "largest_relative_gap": largest[0], "largest_witness": largest[1],
            "one_hit_always_commits": all(_commit_value(1, s) == _optimal_value(1, s)
                                          for r, s in states if r == 1)}


# --- Two hits: commit until the first hit, in closed form ---------------------

def first_hit_law(size: int, failures: int) -> tuple[tuple[int, Q], ...]:
    """Law of the position ``T`` of the first failure when a category of
    ``size`` items with ``failures`` failures is patched in uniformly random
    order: ``P(T = t) = C(size - t, failures - 1) / C(size, failures)`` for
    ``t = 1, ..., size - failures + 1`` (the other failures sit among the
    ``size - t`` later positions)."""

    validate_category_counts(((size, failures),))
    if failures == 0:
        raise ValueError("a category without failures never hits")
    total = comb(size, failures)
    return tuple((t, Q(comb(size - t, failures - 1), total)) for t in range(1, size - failures + 2))


def two_hit_score(size: int, failures: int, best_other=None) -> Q:
    """Expected patches to two hits when the loop commits to this category
    until it hits and then commits to the best finisher:
    ``(n+1)/(F+1) + E[min((n - T + 1)/F, M)]``.

    ``T`` is the first-failure position; after a first hit at ``T`` the
    category has ``n - T`` items and ``F - 1`` failures, so its own finisher
    is ``(n - T + 1)/F`` (spent when ``F = 1``).  ``M`` is the best finisher
    ``(n'+1)/(F'+1)`` among the other categories, ``None`` when there is none.
    """

    validate_category_counts(((size, failures),))
    if best_other is not None:
        best_other = Q(best_other)
    if failures == 0 or (failures == 1 and best_other is None):
        raise ValueError("two hits need two failures")
    total = Q(size + 1, failures + 1)
    for t, probability in first_hit_law(size, failures):
        options = [Q(size - t + 1, failures)] if failures >= 2 else []
        if best_other is not None:
            options.append(best_other)
        total += probability * min(options)
    return total


def two_hit_score_closed_form(size: int, failures: int, best_other=None) -> Q:
    """``two_hit_score`` without the sum.  With ``r = n - T`` the items left
    after the first hit, ``P(r) = C(r, F-1)/C(n, F)``, and the hockey-stick
    identities ``sum_{r<=R} C(r, F-1) = C(R+1, F)`` and
    ``sum_{r<=R} (r+1) C(r, F-1) = F C(R+2, F+1)`` give
    ``E[min((r+1)/F, M)] = (C(R+2, F+1) + M (C(n, F) - C(R+1, F))) / C(n, F)``
    with ``R`` the largest ``r <= n - 1`` such that ``(r+1)/F <= M``."""

    validate_category_counts(((size, failures),))
    if best_other is not None:
        best_other = Q(best_other)
    if failures == 0 or (failures == 1 and best_other is None):
        raise ValueError("two hits need two failures")
    head = Q(size + 1, failures + 1)
    if failures == 1:
        return head + best_other
    total = comb(size, failures)
    if best_other is None:
        cut = size - 1
    else:
        cut = max(failures - 2, min(size - 1, floor(best_other * failures) - 1))
    tail = Q(comb(cut + 2, failures + 1), total)
    if best_other is not None:
        tail += best_other * Q(total - comb(cut + 1, failures), total)
    return head + tail


def two_hit_scores(categories) -> dict[tuple[int, int], Q]:
    """``two_hit_score`` of every distinct category of a state, each against
    the best finisher among the *other* categories."""

    counts = validate_category_counts(categories)
    state = tuple(sorted(pair for pair in counts if pair[1] > 0))
    if sum(failures for _, failures in state) < 2:
        raise ValueError("two hits need two failures")
    scores = {}
    for chosen in set(state):
        rest = list(state)
        rest.remove(chosen)
        best_other = min((Q(size + 1, failures + 1) for size, failures in rest), default=None)
        scores[chosen] = two_hit_score(chosen[0], chosen[1], best_other)
    return scores


def two_hit_value(categories) -> Q:
    """Theorem 11: the minimum expected patches to two hits,
    ``min_c two_hit_score(n_c, F_c, best finisher among the others)``.
    One pass over the categories plus one first-hit law each: time linear in
    the number of items, against the dynamic programme's exponential state
    count."""

    return min(two_hit_scores(categories).values())


def two_hit_first_choices(categories) -> tuple[tuple[int, int], ...]:
    """The categories an optimal policy may patch first at two hits: exactly
    the minimizers of ``two_hit_scores`` (Theorem 11)."""

    scores = two_hit_scores(categories)
    best = min(scores.values())
    return tuple(sorted(c for c, v in scores.items() if v == best))


def commit_first_value(hits_needed: int, state: tuple, chosen: tuple) -> Q:
    """Expected patches when the loop commits to ``chosen`` until it hits and
    plays optimally afterwards."""

    state = _adaptive_state(state, hits_needed)
    if hits_needed == 0 or chosen not in state:
        raise ValueError("chosen must be a category of the state and a hit must be needed")
    size, failures = chosen
    rest = list(state)
    rest.remove(chosen)
    total = Q(0)
    for t, probability in first_hit_law(size, failures):
        after = (size - t, failures - 1)
        following = tuple(sorted(rest + ([after] if after[1] > 0 else [])))
        total += probability * (t + _optimal_value(hits_needed - 1, following))
    return total


def switch_after_miss(hits_needed: int, state: tuple, first: tuple, second: tuple) -> dict[str, object]:
    """Lemma 12, the exact cost of switching after one miss.

    The policy patches ``first`` = (n, F) once; on a hit it plays optimally,
    on a miss it commits to ``second`` until that hits and then plays
    optimally.  With ``p = F/n``, ``s'`` the state after the miss and ``K``
    the commit-then-optimal values,

        switch - K_second(s) = 1/(F+1) + p (K_first'(s') - K_second(s')) + p E[rho] - E[delta],

    where ``delta`` is what one pass removed from ``first`` is worth to the
    optimum with one hit fewer, after ``second``'s first hit, and ``rho`` is
    what the ``T'`` passes that ``first'`` = (n-1, F) misses before its first
    hit are worth to that optimum after ``first``'s hit.
    """

    state = _adaptive_state(state, hits_needed)
    if hits_needed == 0:
        raise ValueError("a hit must be needed")
    size, failures = first
    if first not in state or failures >= size:
        raise ValueError("first must be a category of the state that can miss")
    rest = list(state)
    rest.remove(first)
    if second not in rest:
        raise ValueError("second must be another category of the state")
    p = Q(failures, size)
    reduced = (size - 1, failures)
    missed = tuple(sorted(rest + [reduced]))
    hit_state = tuple(sorted(rest + ([(size - 1, failures - 1)] if failures > 1 else [])))
    k_second_after_miss = commit_first_value(hits_needed, missed, second)
    k_first_after_miss = commit_first_value(hits_needed, missed, reduced)
    switch = 1 + p * _optimal_value(hits_needed - 1, hit_state) + (1 - p) * k_second_after_miss
    k_second = commit_first_value(hits_needed, state, second)
    k_first = commit_first_value(hits_needed, state, first)
    others = list(rest)
    others.remove(second)
    delta = Q(0)
    for t, probability in first_hit_law(*second):
        landed = [(second[0] - t, second[1] - 1)] if second[1] > 1 else []
        with_full = tuple(sorted(others + landed + [first]))
        with_reduced = tuple(sorted(others + landed + [reduced]))
        delta += probability * (_optimal_value(hits_needed - 1, with_full)
                                - _optimal_value(hits_needed - 1, with_reduced))
    rho = Q(0)
    for t, probability in first_hit_law(*reduced):
        shorter = tuple(sorted(rest + ([(size - 1 - t, failures - 1)] if failures > 1 else [])))
        rho += probability * (_optimal_value(hits_needed - 1, hit_state)
                              - _optimal_value(hits_needed - 1, shorter))
    slack = Q(1, failures + 1) + p * rho - delta
    return {"hits_needed": hits_needed, "state": state, "first": first, "second": second,
            "switch": switch, "commit_first": k_first, "commit_second": k_second,
            "commit_first_after_miss": k_first_after_miss,
            "commit_second_after_miss": k_second_after_miss,
            "delta": delta, "rho": rho, "slack": slack,
            "identity_holds": switch - k_second == slack + p * (k_first_after_miss - k_second_after_miss),
            "switch_beats_both_commits": switch < min(k_first, k_second)}


def single_failure_value(categories, hits_needed: int) -> Q:
    """When every category has exactly one failure: the sum of the
    ``hits_needed`` smallest ``(n_c + 1)/2``.  Committing is optimal there
    (Lemma 12 with one pass worth at most 1/2), each commitment spends its
    category at expected cost ``(n_c + 1)/2`` and changes no other, so the
    cheapest categories are taken."""

    counts = validate_category_counts(categories)
    if any(failures != 1 for _, failures in counts):
        raise ValueError("every category must have exactly one failure")
    if type(hits_needed) is not int or not 0 <= hits_needed <= len(counts):
        raise ValueError("hits needed must be an integer between zero and the number of categories")
    return sum(sorted(Q(size + 1, 2) for size, _ in counts)[:hits_needed], Q(0))


def single_failure_fixture(max_size: int = 8, max_categories: int = 4) -> dict[str, object]:
    """The single-failure closed form against the dynamic programme."""

    states = adaptive_states(max_size, max_categories, max_failures=1)
    mismatches = sum(_optimal_value(required, state) != single_failure_value(state, required)
                     for required, state in states)
    return {"states": len(states), "closed_form_mismatches": mismatches}


def two_hit_fixture(max_size: int = 7, max_categories: int = 3) -> dict[str, object]:
    """Theorem 11 against the dynamic programme on every state of the grid,
    the closed form of the score against its sum, and the score as a
    two-number index (own counts and the best other finisher)."""

    states = [state for required, state in adaptive_states(max_size, max_categories) if required == 2]
    value_mismatches = choice_mismatches = commit_mismatches = 0
    for state in states:
        value = two_hit_value(state)
        value_mismatches += _optimal_value(2, state) != value
        commit_mismatches += _commit_value(2, state) != value
        values = first_patch_values(2, state)
        best = min(values.values())
        choice_mismatches += set(two_hit_first_choices(state)) != {c for c, v in values.items() if v == best}
    others = [None] + [Q(k, 4) for k in range(1, 41)]
    closed_checked = closed_mismatches = 0
    for size in range(1, 13):
        for failures in range(1, size + 1):
            for best_other in others:
                if failures == 1 and best_other is None:
                    continue
                closed_checked += 1
                closed_mismatches += (two_hit_score(size, failures, best_other)
                                      != two_hit_score_closed_form(size, failures, best_other))
    larger = (((9, 3), (12, 2), (15, 6), (20, 5)), ((6, 1), (11, 4), (13, 13), (18, 2)),
              ((8, 2), (8, 2), (14, 3), (16, 7)))
    larger_rows = tuple({"state": state, "two_hit_value": two_hit_value(state),
                         "dynamic_programme": optimal_adaptive_value(state, 2),
                         "first_choices": two_hit_first_choices(state)} for state in larger)
    witness = ((2, 1), (4, 2))
    return {"states": len(states), "value_mismatches": value_mismatches,
            "first_choice_mismatches": choice_mismatches,
            "commit_until_hit_mismatches": commit_mismatches,
            "closed_form_checked": closed_checked, "closed_form_mismatches": closed_mismatches,
            "larger_states": larger_rows,
            "larger_states_agree": all(row["two_hit_value"] == row["dynamic_programme"] for row in larger_rows),
            "greedy_witness_scores": _render_values(two_hit_scores(witness)),
            "greedy_witness_reproduced": two_hit_scores(witness) == {(2, 1): Q(19, 6), (4, 2): Q(37, 12)}}


def switch_identity_fixture(max_size: int = 5, max_categories: int = 3) -> dict[str, object]:
    """Lemma 12 on every state of the grid and every ordered pair of distinct
    categories whose first can miss; at two hits the slack is nonnegative,
    which is the whole of Theorem 11's inductive step."""

    checked = failures_of_identity = 0
    two_hit_negative_slack = two_hit_profitable = 0
    single_failure_rows = single_failure_delta_above_half = 0
    profitable_by_hits: dict[int, int] = {}
    worst_slack = None
    for required, state in adaptive_states(max_size, max_categories):
        distinct = sorted(set(state))
        for first in distinct:
            if first[1] >= first[0]:
                continue
            rest = list(state)
            rest.remove(first)
            for second in sorted(set(rest)):
                row = switch_after_miss(required, state, first, second)
                checked += 1
                failures_of_identity += not row["identity_holds"]
                if first[1] == 1:
                    single_failure_rows += 1
                    single_failure_delta_above_half += row["delta"] > Q(1, 2)
                if required == 2:
                    two_hit_negative_slack += row["slack"] < 0
                    two_hit_profitable += row["switch_beats_both_commits"]
                if row["switch_beats_both_commits"]:
                    profitable_by_hits[required] = profitable_by_hits.get(required, 0) + 1
                if worst_slack is None or row["slack"] < worst_slack[0]:
                    worst_slack = (row["slack"], {"hits_needed": required, "state": state,
                                                  "first": first, "second": second})
    return {"pairs_checked": checked, "identity_failures": failures_of_identity,
            "two_hit_negative_slack": two_hit_negative_slack,
            "two_hit_profitable_switches": two_hit_profitable,
            "single_failure_first_rows": single_failure_rows,
            "single_failure_delta_above_half": single_failure_delta_above_half,
            "profitable_switches_by_hits_needed": tuple(sorted(profitable_by_hits.items())),
            "most_negative_slack": worst_slack[0], "most_negative_slack_at": worst_slack[1]}


def two_category_commit_fixture(max_size: int = 8, slack: bool = True) -> dict[str, object]:
    """With two categories, every requirement: is committing until a hit
    optimal, does every optimal first patch stay optimal after it misses, and
    is every Lemma 12 slack nonnegative (which makes a profitable switch
    impossible)?"""

    pairs = [(size, failures) for size in range(1, max_size + 1) for failures in range(1, size + 1)]
    states = checked = commit_gaps = stay_failures = slacks = negative_slacks = 0
    first_gap = None
    for index, left in enumerate(pairs):
        for right in pairs[index:]:
            state = tuple(sorted((left, right)))
            for required in range(1, left[1] + right[1] + 1):
                states += 1
                if _commit_value(required, state) != _optimal_value(required, state):
                    commit_gaps += 1
                    first_gap = first_gap or {"hits_needed": required, "state": state}
                values = first_patch_values(required, state)
                best = min(values.values())
                for chosen, value in values.items():
                    if value != best or chosen[1] >= chosen[0]:
                        continue
                    rest = list(state)
                    rest.remove(chosen)
                    reduced = (chosen[0] - 1, chosen[1])
                    after = first_patch_values(required, tuple(sorted(rest + [reduced])))
                    checked += 1
                    stay_failures += after[reduced] != min(after.values())
                if not slack:
                    continue
                for first, second in {(left, right), (right, left)}:
                    if first[1] < first[0]:
                        slacks += 1
                        negative_slacks += switch_after_miss(required, state, first, second)["slack"] < 0
    return {"max_size": max_size, "states": states, "commit_until_hit_gaps": commit_gaps,
            "first_gap": first_gap, "optimal_patches_followed_by_a_miss": checked,
            "optimal_patch_not_optimal_after_its_miss": stay_failures,
            "switch_slacks_checked": slacks, "negative_switch_slacks": negative_slacks}


def commit_boundary_fixture() -> dict[str, object]:
    """Committing until a hit is optimal at every state exactly when at most
    two hits are needed: Theorems 10 and 11 below, and above a three-hit
    witness that sure-hit padding carries to every larger requirement."""

    three = ((4, 2), (5, 2), (14, 7))
    optimal, committed = optimal_adaptive_value(three, 3), commit_until_hit_value(three, 3)
    after_miss = ((3, 2), (5, 2), (14, 7))
    lemma = switch_after_miss(3, three, (4, 2), (14, 7))
    padded = []
    for copies in (1, 2, 3):
        state = tuple(sorted(three + ((1, 1),) * copies))
        padded.append({"state": state, "hits_needed": 3 + copies,
                       "optimal": optimal_adaptive_value(state, 3 + copies),
                       "committed": commit_until_hit_value(state, 3 + copies)})
    largest = ((10, 2), (12, 2), (19, 3))
    largest_optimal, largest_committed = optimal_adaptive_value(largest, 4), commit_until_hit_value(largest, 4)
    return {
        "largest_gap_found": {
            "state": largest, "hits_needed": 4, "optimal": largest_optimal, "committed": largest_committed,
            "gap": largest_committed - largest_optimal,
            "relative_gap": (largest_committed - largest_optimal) / largest_optimal,
            "optimal_first": optimal_first_choices(largest, 4),
        },
        "largest_gap_exceeds_one_part_in_a_thousand":
            (largest_committed - largest_optimal) / largest_optimal > Q(1, 1000),
        "three_hit_witness": {
            "state": three, "hits_needed": 3, "optimal": optimal, "committed": committed,
            "gap": committed - optimal, "relative_gap": (committed - optimal) / optimal,
            "first_patch_values": _render_values(first_patch_values(3, three)),
            "after_a_miss_in_(4,2)": _render_values(first_patch_values(3, after_miss)),
            "switch_after_miss": lemma,
        },
        "three_hit_witness_holds": (committed - optimal == Q(1, 5148)
                                    and optimal_first_choices(three, 3) == ((4, 2),)
                                    and optimal_first_choices(after_miss, 3) == ((14, 7),)
                                    and lemma["switch_beats_both_commits"] and lemma["slack"] < 0),
        "padded": tuple(padded),
        "padding_preserves_the_gap": all(row["optimal"] == optimal + row["hits_needed"] - 3
                                         and row["committed"] == committed + row["hits_needed"] - 3
                                         for row in padded),
    }


def conjecture_refutations() -> dict[str, object]:
    """Two regularities that hold on the exhaustive grid (sizes at most five)
    and fail just beyond it, each refuted by one exact state.

    Equal rates with the larger category first: in {(3,2),(6,4)} with two
    hits needed the smaller category is strictly better first.  The lowest
    of three or more distinct rates never uniquely optimal: in
    {(5,3),(8,5),(9,6)} with three hits needed the lowest rate, 3/5, is the
    unique optimal first patch.
    """

    equal = first_patch_values(2, ((3, 2), (6, 4)))
    lowest = first_patch_values(3, ((5, 3), (8, 5), (9, 6)))
    rates = {c: Q(c[1], c[0]) for c in lowest}
    return {
        "equal_rates_larger_first": {
            "state": ((3, 2), (6, 4)), "hits_needed": 2, "values": _render_values(equal),
            "refuted": equal[(3, 2)] < equal[(6, 4)],
        },
        "lowest_rate_never_uniquely_optimal": {
            "state": ((5, 3), (8, 5), (9, 6)), "hits_needed": 3, "values": _render_values(lowest),
            "rates": _render_values(rates),
            "refuted": (lowest[(5, 3)] < lowest[(8, 5)] and lowest[(5, 3)] < lowest[(9, 6)]
                        and rates[(5, 3)] < rates[(8, 5)] < rates[(9, 6)]),
        },
    }


def rate_violations(max_size: int, max_categories: int) -> dict[str, object]:
    """States in which every optimal first patch has a strictly lower current
    hit probability than some other category, so no rule that patches a
    highest-rate category can be optimal there."""

    states = adaptive_states(max_size, max_categories)
    found = []
    for required, state in states:
        values = first_patch_values(required, state)
        best = min(values.values())
        top_rate = max(Q(failures, size) for size, failures in values)
        optimal = tuple(sorted(c for c, v in values.items() if v == best))
        if all(Q(c[1], c[0]) < top_rate for c in optimal):
            found.append({"hits_needed": required, "state": state, "optimal_first": optimal,
                          "values": _render_values(values)})
    return {"states": len(states), "violations": len(found),
            "min_hits_needed": min((row["hits_needed"] for row in found), default=None),
            "first": found[0] if found else None}


def greedy_failures(max_size: int, max_categories: int) -> dict[str, object]:
    """States where the greedy first patch is not an optimal first patch."""

    states = adaptive_states(max_size, max_categories)
    failures = 0
    for required, state in states:
        values = first_patch_values(required, state)
        chosen = max(state, key=lambda pair: (Q(pair[1], pair[0]), -pair[0]))
        failures += values[chosen] != min(values.values())
    return {"states": len(states), "greedy_suboptimal": failures}


def index_rule_fixture() -> dict[str, object]:
    """No index rule is optimal, and the optimal first patch need not have
    the highest hit probability."""

    def unique_witness(first_state, second_state, hits):
        """(2,1) the unique optimum of the first state, (4,2) of the second."""
        first, second = first_patch_values(hits, first_state), first_patch_values(hits, second_state)
        return {"A": (2, 1), "B": (4, 2), "hits_needed": hits,
                "A_uniquely_optimal_in": first_state, "A_values": _render_values(first),
                "B_uniquely_optimal_in": second_state, "B_values": _render_values(second),
                "holds": (optimal_first_choices(first_state, hits) == ((2, 1),)
                          and optimal_first_choices(second_state, hits) == ((4, 2),))}

    with_unit = first_patch_values(2, ((1, 1), (2, 1), (4, 2)))
    totals_tie = first_patch_values(3, ((1, 1), (2, 1), (3, 1), (4, 2)))
    lower = first_patch_values(2, ((2, 1), (5, 2)))
    own = unique_witness(((2, 1), (2, 1), (4, 2)), ((2, 1), (4, 2)), 2)
    totals = unique_witness(((2, 1), (2, 1), (4, 1), (4, 2)), ((2, 1), (3, 1), (3, 1), (4, 2)), 2)
    totals["same_totals_and_category_count"] = (
        _index_context("with_totals_and_category_count", totals["A_uniquely_optimal_in"])
        == _index_context("with_totals_and_category_count", totals["B_uniquely_optimal_in"]) == (12, 5, 4))
    totals["holds"] = totals["holds"] and totals["same_totals_and_category_count"]
    return {
        "own_counts": preference_reversals(5, 4, "own_counts"),
        "with_totals": preference_reversals(5, 4, "with_totals"),
        "with_totals_and_category_count": preference_reversals(5, 4, "with_totals_and_category_count"),
        "rate_violations": rate_violations(5, 4),
        "greedy": greedy_failures(5, 4),
        "unique_optimum_witness": own,
        "totals_unique_optimum_witness": totals,
        "version_0_6_witnesses_tie": {
            "own_counts_state": ((1, 1), (2, 1), (4, 2)), "own_counts_values": _render_values(with_unit),
            "own_counts_optimal": optimal_first_choices(((1, 1), (2, 1), (4, 2)), 2),
            "totals_state": ((1, 1), (2, 1), (3, 1), (4, 2)), "totals_values": _render_values(totals_tie),
            "totals_optimal": optimal_first_choices(((1, 1), (2, 1), (3, 1), (4, 2)), 3),
            "holds": (optimal_first_choices(((1, 1), (2, 1), (4, 2)), 2) == ((1, 1), (2, 1))
                      and optimal_first_choices(((1, 1), (2, 1), (3, 1), (4, 2)), 3) == ((1, 1), (4, 2))),
        },
        "lower_rate_witness": {
            "state": ((2, 1), (5, 2)), "hits_needed": 2, "values": _render_values(lower),
            "rates": (((2, 1), Q(1, 2)), ((5, 2), Q(2, 5))),
            "holds": lower[(5, 2)] == Q(69, 20) < lower[(2, 1)] == Q(7, 2),
        },
    }


def hits_needed(items: int, clean_accuracy: Q, flip: Q) -> dict[str, object]:
    """Hits required for the selection score to reach the noise ceiling."""

    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")
    base, ceiling = observed_accuracy(clean_accuracy, flip), noise_ceiling(flip)
    failures = items * (1 - base)
    if failures.denominator != 1:
        raise ValueError("observed accuracy must give an integer failure count on this set size")
    needed = max(Q(0), items * (ceiling - base))
    return {"items": items, "observed_accuracy": base, "noise_ceiling": ceiling,
            "failures": int(failures), "hits_needed": needed,
            "hits_needed_integer": ceil(needed)}


def ceiling_cost_fixture() -> dict[str, object]:
    """Patches to the ceiling along a chain of category maps on 50 items.

    Clean accuracy 4/5 and flip rate 1/10 give observed accuracy 37/50 and
    ceiling 9/10, so 13 of 50 items fail and 8 hits are required.  Failures sit
    at items 0, 4, 8, ..., 48.  The chain coarsens by block size 1, 2, 5, 10,
    25, 50.
    """

    items, clean, flip = 50, Q(4, 5), Q(1, 10)
    need = hits_needed(items, clean, flip)
    required = need["hits_needed_integer"]
    record = "".join("0" if index % 4 == 0 else "1" for index in range(items))
    rows = []
    for size in (50, 25, 10, 5, 2, 1):
        categories = tuple(tuple(range(start, start + size)) for start in range(0, items, size))
        counts = category_counts(categories, record)
        crossing = expected_score_crossing(counts, need["hits_needed"])
        static = expected_patches_static(counts, required)
        adaptive = expected_patches_adaptive(counts, required)
        rows.append({"block_size": size, "categories": len(categories),
                     "counts": counts, "schedule": greedy_schedule(counts),
                     "expected_score_crossing": crossing, "crossing_share_of_set": crossing / items,
                     "expected_patches_static": static, "static_share_of_set": static / items,
                     "expected_patches_adaptive": adaptive, "adaptive_share_of_set": adaptive / items})
    shares = [row["crossing_share_of_set"] for row in rows]
    statics = [row["expected_patches_static"] for row in rows]
    adaptives = [row["expected_patches_adaptive"] for row in rows]
    return {
        "setting": need, "failed_items": tuple(range(0, items, 4)), "chain": rows,
        "score_only_share_matches_random_threshold":
            shares[0] == Q(8, 13) == ceiling_detection_threshold(clean, flip),
        "item_level_share_matches_targeted_threshold":
            shares[-1] == Q(4, 25) == targeted_ceiling_detection_threshold(clean, flip),
        "score_only_expected_patches_closed_form": statics[0] == Q(8 * 51, 14),
        "crossing_nonincreasing_along_chain": all(a >= b for a, b in zip(shares, shares[1:])),
        "static_nonincreasing_along_chain": all(a >= b for a, b in zip(statics, statics[1:])),
        "adaptive_nonincreasing_along_chain": all(a >= b for a, b in zip(adaptives, adaptives[1:])),
        "adaptive_at_most_static_along_chain": all(a <= s for a, s in zip(adaptives, statics)),
        "crossing_at_least_static_along_chain": all(c >= s for c, s in zip(
            (row["expected_score_crossing"] for row in rows), statics)),
    }


def _greater(left: Q, right: Q) -> bool:
    return left.numerator * right.denominator > right.numerator * left.denominator


def small_set_fixture(items: int = 6) -> dict[str, object]:
    """Every failure pattern on a small set against every category map.

    For each category map and each record with at least one failure, the
    requirement is all failures and half of them (rounded up).  Reports whether
    the expected-score crossing, the static expectation, and the adaptive
    expectation are monotone along refinement, and carries the explicit
    four-item witness that the static expectation is not.
    """

    maps = all_category_maps(items)
    parts = {m: _item_partition(m, items) for m in maps}
    patterns = [record for record in records(items) if "0" in record]
    cases = []
    for record in patterns:
        total = record.count("0")
        for required in sorted({total, ceil(Q(total, 2))}):
            cases.append((record, required))
    values = {}
    error_ok = adaptive_le_static = True
    for m in maps:
        rows = []
        blocks = validate_categories(m, items)
        for record, required in cases:
            counts = tuple((len(block), sum(record[index] == "0" for index in block))
                           for block in blocks)
            bound = crossing_error_bound(counts, required)
            adaptive = expected_patches_adaptive(counts, required)
            error_ok &= (bound["error"] == bound["closed_form_error"]
                         and 0 <= bound["error"] < bound["bound"])
            adaptive_le_static &= adaptive <= bound["expected_patches_static"]
            rows.append((bound["expected_score_crossing"], bound["expected_patches_static"], adaptive))
        values[m] = rows
    crossing_mono = static_mono = adaptive_mono = True
    refining_pairs = 0
    static_witness = adaptive_witness = None
    for fine, coarse in product(maps, repeat=2):
        if fine == coarse or not refines(parts[fine], parts[coarse]):
            continue
        refining_pairs += 1
        for (record, required), fine_row, coarse_row in zip(cases, values[fine], values[coarse]):
            # Exact comparisons by cross-multiplication; Fraction ordering is slow.
            if _greater(fine_row[0], coarse_row[0]):
                crossing_mono = False
            if _greater(fine_row[1], coarse_row[1]):
                static_mono = False
                static_witness = static_witness or {"fine_map": fine, "coarse_map": coarse,
                                                    "record": record, "hits_needed": required,
                                                    "fine": fine_row[1], "coarse": coarse_row[1]}
            if _greater(fine_row[2], coarse_row[2]):
                adaptive_mono = False
                adaptive_witness = adaptive_witness or {"fine_map": fine, "coarse_map": coarse,
                                                        "record": record, "hits_needed": required,
                                                        "fine": fine_row[2], "coarse": coarse_row[2]}
    coarse4, fine4 = ((4, 2),), ((2, 1), (2, 1))
    four = {"coarse": coarse4, "fine": fine4, "hits_needed": 2,
            "crossing": (expected_score_crossing(coarse4, 2), expected_score_crossing(fine4, 2)),
            "static": (expected_patches_static(coarse4, 2), expected_patches_static(fine4, 2)),
            "adaptive": (expected_patches_adaptive(coarse4, 2), expected_patches_adaptive(fine4, 2))}
    return {
        "items": items, "category_maps": len(maps), "patterns": len(patterns),
        "cases_per_map": len(cases), "refining_pairs": refining_pairs,
        "error_identity_and_bound_hold": error_ok,
        "adaptive_at_most_static": adaptive_le_static,
        "crossing_monotone_along_refinement": crossing_mono,
        "static_monotone_along_refinement": static_mono,
        "static_witness": static_witness,
        "adaptive_monotone_along_refinement": adaptive_mono,
        "adaptive_witness": adaptive_witness,
        "four_item_static_counterexample": four,
        "four_item_static_refinement_costs_more": four["static"][1] > four["static"][0],
        "four_item_crossing_and_adaptive_do_not": (four["crossing"][1] <= four["crossing"][0]
                                                    and four["adaptive"][1] <= four["adaptive"][0]),
    }


# ---------------------------------------------------------------------------
# 4. Ledger wrapper: a category_feedback event kind
# ---------------------------------------------------------------------------

CATEGORY_EVENT_KIND = "category_feedback"
LEAK_CLASSES = ("score_only", "category", "item_level")


@dataclass(frozen=True)
class CategoryFeedbackEvent:
    generation: int
    set_id: str
    categories: tuple[tuple[str, ...], ...]


def leak_class(categories, item_ids) -> str:
    """Position of a category partition: one block is ``score_only``, all
    singletons is ``item_level``, anything else is ``category``."""

    blocks = validate_partition(categories, item_ids)
    if len(blocks) == 1:
        return "score_only"
    if all(len(block) == 1 for block in blocks):
        return "item_level"
    return "category"


def audit_category_ledger(sets, events, readout_budget, exhaustion_bound,
                          declared_categories=None) -> dict[str, object]:
    """Audit a ledger whose events may include ``CategoryFeedbackEvent``.

    Each category event is translated for ``audit_ledger`` into one
    ``score_query`` per block of two or more items and one ``item_feedback``
    naming the singleton items, because a count on a singleton block is that
    item's outcome.  The base ledger then applies its declared access classes,
    so a singleton block on a ``score_only`` set is a recorded breach.  The
    partition used is recorded here.  ``declared_categories`` maps a set id to
    the finest partition that set may leak; an event finer than it is a
    category breach.  Malformed events raise; breaches are recorded.
    """

    audit_ledger(sets, (), readout_budget, exhaustion_bound)  # validates declarations
    declared = {item.set_id: item for item in sets}
    limits = {}
    for set_id, categories in (declared_categories or {}).items():
        if set_id not in declared:
            raise ValueError("declared categories name an unknown set")
        limits[set_id] = validate_partition(categories, declared[set_id].item_ids)
    translated, rows, breaches = [], {set_id: [] for set_id in declared}, {set_id: [] for set_id in declared}
    for event in events:
        if isinstance(event, LoopEvent):
            translated.append(event)
            continue
        if (not isinstance(event, CategoryFeedbackEvent) or type(event.generation) is not int
                or event.generation < 0 or event.set_id not in declared):
            raise ValueError("invalid category feedback event")
        target = declared[event.set_id]
        partition = validate_partition(event.categories, target.item_ids)
        singles = tuple(sorted(item for block in partition if len(block) == 1 for item in block))
        if singles:
            translated.append(LoopEvent(event.generation, event.set_id, "item_feedback", singles))
        for block in partition:
            if len(block) >= 2:
                translated.append(LoopEvent(event.generation, event.set_id, "score_query"))
        within = None
        if event.set_id in limits:
            within = refines(limits[event.set_id], partition)
            if not within:
                breaches[event.set_id].append(
                    f"category feedback finer than declared categories at generation {event.generation}")
        rows[event.set_id].append({
            "generation": event.generation, "blocks": len(partition),
            "block_sizes": tuple(sorted(len(block) for block in partition)),
            "partition": render_partition(partition),
            "leak_class": leak_class(partition, target.item_ids),
            "within_declared_categories": within,
        })
    report = audit_ledger(sets, translated, readout_budget, exhaustion_bound)
    report["category_feedback"] = {
        set_id: {"events": tuple(rows[set_id]), "breaches": tuple(breaches[set_id]),
                 "declared_categories": render_partition(limits[set_id]) if set_id in limits else None}
        for set_id in declared}
    report["declarations_respected"] = (report["declarations_respected"]
                                        and not any(breaches.values()))
    return report


def category_ledger_fixture() -> dict[str, object]:
    """One ledger within its declared categories and one that leaks finer."""

    selection = EvalSet("S", "selection", "item_level", tuple(f"s{i}" for i in range(6)))
    readout = EvalSet("R", "readout", "sealed", tuple(f"r{i}" for i in range(6)))
    declared = {"S": (("s0", "s1", "s2"), ("s3", "s4", "s5"))}
    respected = (
        CategoryFeedbackEvent(1, "S", (("s0", "s1", "s2", "s3", "s4", "s5"),)),
        CategoryFeedbackEvent(2, "S", (("s0", "s1", "s2"), ("s3", "s4", "s5"))),
        LoopEvent(3, "R", "readout"),
    )
    leaking = respected + (CategoryFeedbackEvent(4, "S", (("s0",), ("s1", "s2"), ("s3", "s4", "s5"))),)
    return {"respected": audit_category_ledger((selection, readout), respected, 2, Q(1, 2), declared),
            "leaking": audit_category_ledger((selection, readout), leaking, 2, Q(1, 2), declared)}


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    lattice = lattice_fixture(2, 2)
    category = category_order_fixture()
    category_lattice = category_lattice_fixture()
    cost = ceiling_cost_fixture()
    small = small_set_fixture()
    policy = greedy_vs_optimal_fixture()
    index = index_rule_fixture()
    structure = policy_structure_fixture()
    refutations = conjecture_refutations()
    one_hit = one_hit_fixture()
    commit = commit_until_hit_fixture()
    two_hit = two_hit_fixture()
    switch = switch_identity_fixture()
    two_category = two_category_commit_fixture()
    boundary = commit_boundary_fixture()
    capped = commit_until_hit_fixture(8, 4, max_failures=2)
    single = single_failure_fixture()
    ledger = category_ledger_fixture()
    four = policy["four_item_witness"]
    checks = {
        "two_hit_optimum_is_the_commit_closed_form_with_its_minimizers_first":
            two_hit["value_mismatches"] == 0 and two_hit["first_choice_mismatches"] == 0
            and two_hit["commit_until_hit_mismatches"] == 0 and two_hit["larger_states_agree"]
            and two_hit["greedy_witness_reproduced"],
        "two_hit_score_hockey_stick_closed_form_matches_its_sum": two_hit["closed_form_mismatches"] == 0,
        "switch_after_miss_identity_exact_and_slack_nonnegative_at_two_hits":
            switch["identity_failures"] == 0 and switch["pairs_checked"] > 0
            and switch["two_hit_negative_slack"] == 0 and switch["two_hit_profitable_switches"] == 0,
        "one_pass_in_a_single_failure_category_worth_at_most_one_half":
            switch["single_failure_first_rows"] > 0 and switch["single_failure_delta_above_half"] == 0,
        "single_failure_categories_cost_the_smallest_half_sizes":
            single["states"] > 0 and single["closed_form_mismatches"] == 0,
        "commit_until_hit_fails_at_three_hits_and_at_every_larger_requirement":
            boundary["three_hit_witness_holds"] and boundary["padding_preserves_the_gap"],
        "commit_until_hit_gap_exceeds_a_tenth_of_a_percent_beyond_the_grid":
            boundary["largest_gap_exceeds_one_part_in_a_thousand"],
        "commit_until_hit_gaps_on_the_grid_need_at_least_three_hits":
            all(hits >= 3 for hits, _ in commit["suboptimal_by_hits_needed"]),
        "two_categories_commit_until_hit_optimal_with_nonnegative_slack_on_the_grid":
            two_category["commit_until_hit_gaps"] == 0
            and two_category["optimal_patch_not_optimal_after_its_miss"] == 0
            and two_category["negative_switch_slacks"] == 0,
        "commit_until_hit_optimal_with_at_most_two_failures_per_category_on_the_grid":
            capped["states"] > 0 and capped["commit_until_hit_suboptimal"] == 0,
        "two_patches_in_different_categories_commute_when_two_hits_remain":
            structure["commutation"]["violations"] == 0 and structure["commutation"]["pairs_checked"] > 0,
        "no_extremal_rule_covers_the_optimal_first_patch":
            structure["optimal_outside_extremal_rules"] > 0 and structure["equal_rates_largest_not_optimal"] > 0,
        "lowest_of_three_rates_never_uniquely_optimal_on_the_grid":
            structure["lowest_of_three_rates_uniquely_optimal"] == 0,
        "both_grid_regularities_refuted_beyond_the_grid":
            refutations["equal_rates_larger_first"]["refuted"]
            and refutations["lowest_rate_never_uniquely_optimal"]["refuted"],
        "one_hit_value_is_the_best_finisher_closed_form":
            one_hit["closed_form_mismatches"] == 0 and one_hit["best_finisher_not_optimal_first"] == 0
            and one_hit["zero_failure_category_excluded"]["holds"],
        "highest_rate_first_not_optimal_at_one_hit_witness":
            one_hit["rate_versus_finisher_witness"]["highest_rate_first_is_worse"],
        "commit_until_hit_not_optimal_beyond_one_hit_but_within_a_tenth_of_a_percent":
            commit["commit_until_hit_suboptimal"] > 0 and commit["one_hit_always_commits"]
            and commit["largest_relative_gap"] < Q(1, 1000),
        "no_index_rule_on_own_counts_and_hits_needed":
            index["own_counts"]["refuting_pairs"] > 0 and index["unique_optimum_witness"]["holds"],
        "no_index_rule_even_with_global_totals":
            index["with_totals"]["refuting_pairs"] > 0
            and index["with_totals_and_category_count"]["refuting_pairs"] > 0
            and index["totals_unique_optimum_witness"]["holds"],
        "version_0_6_index_witnesses_tie_with_a_third_category":
            index["version_0_6_witnesses_tie"]["holds"],
        "optimal_first_patch_can_have_lower_hit_probability":
            index["rate_violations"]["violations"] > 0 and index["lower_rate_witness"]["holds"]
            and index["rate_violations"]["min_hits_needed"] >= 2,
        "meet_preserved_on_every_pair_up_to_five_items":
            all(row["meet_preserved"] == row["ordered_pairs"] for row in category_lattice.values()),
        "join_preserved_iff_intersection_graph_is_forest":
            all(row["join_preserved_iff_forest_pairs"] == row["ordered_pairs"]
                for row in category_lattice.values())
            and category_lattice[4]["non_forest_pairs"] == 6,
        "cycle_witnesses_confused_by_joint_leak_only":
            all(row["cycle_witnesses_valid"] == row["non_forest_pairs"] for row in category_lattice.values()),
        "optimal_at_most_greedy_at_most_static_over_all_203_maps": policy["optimal_le_greedy_le_static"],
        "greedy_optimal_when_one_hit_remains": policy["greedy_equals_optimal_for_one_hit"],
        "all_hits_needed_is_policy_invariant": policy["greedy_equals_optimal_equals_closed_form_for_all_hits"],
        "greedy_adaptive_not_optimal_four_item_witness":
            four["greedy"] == Q(19, 6) and four["optimal"] == Q(37, 12)
            and four["optimal_first"] == ((4, 2),) and policy["cases_where_greedy_strictly_worse"] > 0,
        "optimal_adaptive_monotone_along_refinement": policy["optimal_monotone_along_refinement"],
        "fifteen_partitions_of_two_item_records": lattice["bell_number"] == 15,
        "lattice_data_processing_law_holds_exhaustively": lattice["law_holds_on_every_comparable_pair"],
        "tv_domination_characterizes_the_order": lattice["domination_fails_on_every_noncomparable_pair"],
        "join_and_meet_are_lattice_operations": lattice["join_and_meet_satisfy_lattice_definitions"]
                                                 and lattice["join_meet_tv_bounds_hold"],
        "existing_classes_are_bottom_middle_top":
            lattice["sealed_is_bottom"] and lattice["item_level_is_top"]
            and lattice["score_only_strictly_between"] and lattice["existing_access_kernels_match"],
        "category_map_is_order_embedding": all(category["order_embedding_exhaustive"].values())
                                            and category["endpoints_are_score_only_and_item_level"],
        "category_order_is_partial": category["incomparable_pair"]["neither_refines"]
                                     and category["incomparable_pair"]["A_separates_second_pair_only"]
                                     and category["incomparable_pair"]["B_separates_first_pair_only"],
        "category_map_does_not_preserve_joins": category["join_failure"]["joint_leak_strictly_coarser"]
                                                and category["join_failure"]["tv_through_joint_leak"] == 0
                                                and category["join_failure"]["tv_through_refined_categories"] == 1,
        "score_only_recovers_eight_thirteenths": cost["score_only_share_matches_random_threshold"],
        "item_level_recovers_four_twentyfifths": cost["item_level_share_matches_targeted_threshold"],
        "score_only_expected_patches_is_204_over_7": cost["score_only_expected_patches_closed_form"],
        "crossing_nonincreasing_along_fifty_item_chain": cost["crossing_nonincreasing_along_chain"],
        "expected_patches_nonincreasing_along_fifty_item_chain":
            cost["static_nonincreasing_along_chain"] and cost["adaptive_nonincreasing_along_chain"],
        "crossing_bounds_static_bounds_adaptive_on_chain":
            cost["crossing_at_least_static_along_chain"] and cost["adaptive_at_most_static_along_chain"],
        "crossing_error_identity_and_bound_on_six_items": small["error_identity_and_bound_hold"],
        "crossing_monotone_over_all_203_maps": small["crossing_monotone_along_refinement"],
        "adaptive_at_most_static_over_all_203_maps": small["adaptive_at_most_static"],
        "static_expectation_not_monotone_four_item_witness":
            small["four_item_static_refinement_costs_more"] and small["four_item_crossing_and_adaptive_do_not"],
        "category_ledger_records_partitions_and_breaches":
            ledger["respected"]["declarations_respected"]
            and ledger["respected"]["readout"]["R"]["endpoint_status"] == "evaluable"
            and not ledger["leaking"]["declarations_respected"]
            and bool(ledger["leaking"]["category_feedback"]["S"]["breaches"]),
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "lattice": lattice, "category_order": category, "category_lattice": category_lattice,
            "ceiling_cost": cost, "small_set_enumeration": small, "greedy_vs_optimal": policy,
            "index_rules": index, "policy_structure": structure, "conjecture_refutations": refutations,
            "one_hit": one_hit, "commit_until_hit": commit, "two_hits": two_hit,
            "switch_after_miss": switch, "two_categories": two_category, "commit_boundary": boundary,
            "commit_until_hit_at_most_two_failures": capped, "single_failure": single,
            "category_ledger": ledger}
