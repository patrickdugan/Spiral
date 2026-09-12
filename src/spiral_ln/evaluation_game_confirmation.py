"""Finite synthetic acquisition and exact checks; no model or network access."""

from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import product
from math import comb


STRATA = tuple(product(("easy", "hard"), ("lenient", "strict")))


def optimal_allocation(weights, variances, costs, budget, minimum=1):
    """Exact integer optimum of sum w_h^2 variance_h/n_h under a cost budget.

    Variances refer to independent paired differences, costs to whole pairs.
    Dynamic programming enumerates feasible counts. Inputs must be frozen
    before confirmation; there is no outcome-dependent allocation here.
    """
    if (not weights or len(weights) != len(variances) or len(weights) != len(costs)
            or sum(weights) != 1 or min(weights) <= 0 or min(variances) <= 0):
        raise ValueError("positive weights summing to one and positive variances required")
    if any(type(x) is not int or x < 1 for x in (*costs, budget, minimum)):
        raise ValueError("costs, budget, and minimum must be positive integers")
    states = {0: (Q(0), ())}
    for weight, variance, cost in zip(weights, variances, costs):
        following = {}
        for spent, (objective, counts) in states.items():
            for count in range(minimum, (budget-spent)//cost+1):
                total = spent + count*cost
                candidate = (objective + weight**2*variance/count, counts+(count,))
                if total not in following or candidate < following[total]:
                    following[total] = candidate
        states = following
    if not states:
        raise ValueError("budget cannot cover minimum stratum counts")
    spent, (objective, counts) = min(states.items(), key=lambda item: (item[1], item[0]))
    return {"counts": counts, "spent": spent, "unspent": budget-spent,
            "contrast_variance": objective}


@dataclass(frozen=True)
class MatchedPair:
    pair_id: str
    block_id: str
    split: str
    family: str
    difficulty: str
    grader: str
    negative_control: bool
    control_score: Q
    incentive_score: Q


@dataclass(frozen=True)
class FrozenSelection:
    family: str
    training_blocks: tuple[str, ...]
    training_pairs: tuple[str, ...]


def _blocks(rows):
    """Require complete matched strata and reject duplicate/overlapping blocks."""
    if not rows:
        raise ValueError("rows must be nonempty")
    blocks, seen = {}, set()
    for row in rows:
        if (not row.pair_id or not row.block_id or not row.family
                or row.split not in ("training", "confirmation")
                or type(row.negative_control) is not bool
                or (row.difficulty, row.grader) not in STRATA
                or not 0 <= row.control_score <= 1 or not 0 <= row.incentive_score <= 1):
            raise ValueError("invalid matched pair")
        if row.pair_id in seen:
            raise ValueError("duplicate pair identifier")
        seen.add(row.pair_id)
        group = blocks.setdefault(row.block_id, [])
        if group and (row.split, row.family, row.negative_control) != (
                group[0].split, group[0].family, group[0].negative_control):
            raise ValueError("block crosses split, family, or control boundary")
        group.append(row)
    for group in blocks.values():
        if len(group) != len(STRATA) or {(r.difficulty, r.grader) for r in group} != set(STRATA):
            raise ValueError("each block requires every difficulty/grader stratum exactly once")
    return blocks


def _contrasts(group):
    by_difficulty = {
        d: sum(r.control_score-r.incentive_score for r in group if r.difficulty == d)/2
        for d in ("easy", "hard")
    }
    return ((by_difficulty["easy"]+by_difficulty["hard"])/2,
            by_difficulty["hard"]-by_difficulty["easy"])


def select_training(rows):
    """Select once on training only, with lexical ties and saved source IDs."""
    blocks = _blocks(rows)
    if any(r.split != "training" or r.negative_control for r in rows):
        raise ValueError("selection accepts training targets only")
    values = {}
    for group in blocks.values():
        values.setdefault(group[0].family, []).append(_contrasts(group)[0])
    selected = min(values, key=lambda f: (-sum(values[f])/len(values[f]), f))
    return FrozenSelection(selected, tuple(sorted(blocks)), tuple(sorted(r.pair_id for r in rows)))


def two_sided_sign_p(values):
    """Exact sign-consistency p-value; not a test of the population mean.

    Requires independent blocks and equiprobable signs conditional on a nonzero
    contrast under the null. Ties are discarded; all ties return p=1.
    """
    values = [v for v in values if v != 0]
    n = len(values)
    if not n:
        return Q(1)
    smaller = min(sum(v > 0 for v in values), sum(v < 0 for v in values))
    return min(Q(1), Q(2*sum(comb(n, k) for k in range(smaller+1)), 2**n))


def confirm(selection, rows, alpha=Q(1, 20)):
    """Validate a single selected-family holdout; test two block contrasts.

    The control gate is an exact synthetic-fixture diagnostic. Zero simulated
    control gaps do not certify control equivalence in an observed population.
    """
    blocks = _blocks(rows)
    if not 0 < alpha < 1:
        raise ValueError("alpha must be in (0,1)")
    if set(blocks) & set(selection.training_blocks) or {
            r.pair_id for r in rows} & set(selection.training_pairs):
        raise ValueError("selection/confirmation identifiers overlap")
    if any(r.split != "confirmation" or r.family != selection.family for r in rows):
        raise ValueError("confirmation must use the frozen selected family")
    target = [_contrasts(group) for group in blocks.values() if not group[0].negative_control]
    controls = [r.control_score-r.incentive_score for r in rows if r.negative_control]
    if len(target) < 2 or not controls:
        raise ValueError("at least two target blocks and complete negative controls required")
    results = {}
    for index, name in enumerate(("incentive_response", "incentive_by_difficulty")):
        values = [pair[index] for pair in target]
        p = two_sided_sign_p(values)
        results[name] = {"block_mean": sum(values)/len(values), "block_sign_p": p,
                         "non_tie_blocks": sum(v != 0 for v in values),
                         "reject_sign_null": p <= alpha/2}
    controls_clean = all(gap == 0 for gap in controls)
    return {"family": selection.family, "contrasts": results,
            "alpha_per_test": alpha/2, "target_blocks": len(target),
            "negative_control_blocks": len(blocks)-len(target),
            "fixture_controls_exactly_zero": controls_clean,
            "fixture_interaction_supported": controls_clean and results["incentive_by_difficulty"]["reject_sign_null"],
            "confirmation_pairs": len(rows), "confirmation_score_operations": 2*len(rows),
            "intent_identified": False}


def synthetic_rows(family, split, count, drops, negative=False):
    """Deterministic arithmetic fixtures; block IDs declare intended independence."""
    rows = []
    for index in range(count):
        block = f"{split}:{family}:{negative}:{index}"
        for difficulty, grader in STRATA:
            base = Q(9, 10) if difficulty == "easy" else Q(7, 10)
            base -= Q(1, 10) if grader == "strict" else Q(0)
            gap = drops[0 if difficulty == "easy" else 1]
            rows.append(MatchedPair(f"{block}:{difficulty}:{grader}", block, split,
                                    family, difficulty, grader, negative, base, base-gap))
    return rows


def run_confirmation_fixture():
    training = (synthetic_rows("planning", "training", 8, (Q(1, 10), Q(3, 10)))
                + synthetic_rows("diagnosis", "training", 8, (Q(1, 20), Q(1, 20))))
    selection = select_training(training)
    holdout = (synthetic_rows(selection.family, "confirmation", 12, (Q(1, 10), Q(3, 10)))
               + synthetic_rows(selection.family, "confirmation", 12, (Q(0), Q(0)), True))
    report = confirm(selection, holdout)
    report.update(training_pairs=len(training), training_score_operations=2*len(training),
                  total_score_operations=2*(len(training)+len(holdout)),
                  scope="deterministic synthetic fixture; no empirical error-rate validation")
    return report


def zero_sum_certificate(matrix, row_strategy, column_strategy):
    """Feasible primal/dual bounds for row-maximizing, column-minimizing games."""
    if (not matrix or not matrix[0] or any(len(row) != len(matrix[0]) for row in matrix)
            or len(row_strategy) != len(matrix) or len(column_strategy) != len(matrix[0])):
        raise ValueError("matrix and strategy dimensions must match")
    for strategy in (row_strategy, column_strategy):
        if sum(strategy) != 1 or min(strategy) < 0:
            raise ValueError("strategy must be a probability distribution")
    lower = min(sum(row_strategy[i]*matrix[i][j] for i in range(len(matrix)))
                for j in range(len(matrix[0])))
    upper = max(sum(column_strategy[j]*row[j] for j in range(len(row))) for row in matrix)
    return {"primal_lower_bound": lower, "dual_upper_bound": upper,
            "duality_gap": upper-lower, "optimality_certified": lower == upper}


def adaptation_fixture():
    """Coordination game: reward 1 on equal actions, 0 otherwise for both players.

    The complete Nash set is two pure profiles plus both mixing uniformly.
    Indifference requires opponent probability 1/2, proving the mixed case.
    """
    initial = (0, 1)
    path = [initial]
    for _ in range(4):
        a, b = path[-1]
        path.append((b, a))
    sequential = (initial[1], initial[1])
    return {"equilibrium_set": ((Q(0), Q(0)), (Q(1), Q(1)), (Q(1, 2), Q(1, 2))),
            "equilibrium_coordinates": "probability of action 1 for each player",
            "simultaneous": {"rule": "synchronous best response", "initial": initial,
                             "path": path, "last_payoffs": (0, 0), "period": 2},
            "sequential": {"rule": "row then column best response", "initial": initial,
                           "path": [initial, sequential], "last_payoffs": (1, 1)}}
