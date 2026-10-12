"""Exact, synthetic checks for judgment-to-controller feedback.

Nothing in this module calls a model, trains a learner, or runs an improvement
loop.  It types the channel by which a judgment reaches the process that
produces the next controller, and keeps the resulting *readout gap* separate
from baseline gain, robust regret, discrimination gap, and exploitability.

Three access classes order that channel.  ``sealed`` returns nothing,
``score_only`` returns an aggregate count, ``item_level`` returns per-item
outcomes.  Each is a deterministic coarsening of the next, so the finite
data-processing inequality used for observation-only Hide applies to what the
loop can learn about its own failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import product
from math import comb

from spiral_ln.evaluation_game_testbed import _pushforward, _tv

ACCESS_CLASSES = ("sealed", "score_only", "item_level")
ROLES = ("selection", "readout")
EVENT_KINDS = ("score_query", "item_feedback", "readout")


def access_kernel(access: str, items: int) -> dict[str, dict[str, Q]]:
    """Deterministic feedback kernel from per-item outcome records.

    A record is a string of ``0``/``1`` of length ``items``.  The kernel says
    what reaches the loop, not what the evaluator stores.
    """

    if access not in ACCESS_CLASSES:
        raise ValueError("unknown access class")
    if type(items) is not int or items < 1:
        raise ValueError("items must be a positive integer")
    kernel = {}
    for bits in product("01", repeat=items):
        record = "".join(bits)
        if access == "sealed":
            image = "sealed"
        elif access == "score_only":
            image = f"score={record.count('1')}"
        else:
            image = record
        kernel[record] = {image: Q(1)}
    return kernel


def access_order_fixture() -> dict[str, object]:
    """Two controllers with equal scores and different failures.

    Item-level feedback separates them completely; score-only feedback cannot
    separate them at all.  A second pair with different scores is separated by
    both, and no pair is separated through a sealed set.
    """

    same_score = ({"10": Q(1)}, {"01": Q(1)})
    different_score = ({"11": Q(1)}, {"00": Q(1)})
    gaps = {}
    for name, (left, right) in (("same_score", same_score),
                                ("different_score", different_score)):
        gaps[name] = {
            access: _tv(_pushforward(left, access_kernel(access, 2)),
                        _pushforward(right, access_kernel(access, 2)))
            for access in ACCESS_CLASSES
        }
    ordered = all(g["sealed"] <= g["score_only"] <= g["item_level"] for g in gaps.values())
    return {"operator_type": "judgment_to_controller_feedback_kernel",
            "gaps": gaps, "access_classes_ordered_by_coarsening": ordered,
            "acts_between_generations": True, "changes_recorded_evidence": False}


def _binomial_pmf(n: int, p: Q) -> list[Q]:
    return [Q(comb(n, j)) * p**j * (1 - p)**(n - j) for j in range(n + 1)]


def selection_inflation(items: int, candidates: int, p: Q) -> dict[str, Q]:
    """Exact one-generation over-report from keeping the best-scoring candidate.

    Every candidate has the same true success probability ``p`` on each of
    ``items`` independent selection items, and candidates are independent.  The
    reported value is the selected candidate's score on those same items; the
    readout value is its expected score on untouched items, which is ``p``.
    This isolates the selection term.  It says nothing about real gains,
    persistence across generations, or correlated candidates.
    """

    if type(items) is not int or type(candidates) is not int or items < 1 or candidates < 1:
        raise ValueError("items and candidates must be positive integers")
    if not 0 <= p <= 1:
        raise ValueError("p must be a probability")
    pmf = _binomial_pmf(items, p)
    cumulative, running = [], Q(0)
    for mass in pmf:
        running += mass
        cumulative.append(running)
    expected_max = sum(
        j * (cumulative[j]**candidates - (cumulative[j - 1]**candidates if j else Q(0)))
        for j in range(items + 1)
    )
    reported = expected_max / items
    return {"expected_reported": reported, "readout_value": p,
            "readout_gap": reported - p}


def observed_accuracy(clean_accuracy: Q, flip: Q) -> Q:
    """Accuracy against observed labels when labels flip independently."""

    if not 0 <= clean_accuracy <= 1 or not 0 <= flip <= 1:
        raise ValueError("probabilities required")
    return clean_accuracy * (1 - flip) + (1 - clean_accuracy) * flip


def noise_ceiling(flip: Q) -> Q:
    """Best observed-label accuracy available to a predictor that cannot see
    which labels flipped."""

    if not 0 <= flip <= 1:
        raise ValueError("flip must be a probability")
    return max(flip, 1 - flip)


def memorized_selection_score(clean_accuracy: Q, flip: Q, patch_share: Q) -> Q:
    """Selection-set score after memorizing a share of its observed labels.

    The memorized items are chosen independently of whether the controller
    already got them right, so the remainder keep the base observed accuracy.
    Memorized items score one.  Collateral effects of a patch on other items
    are assumed absent, which a real learner need not satisfy.
    """

    if not 0 <= patch_share <= 1:
        raise ValueError("patch share must lie in [0, 1]")
    base = observed_accuracy(clean_accuracy, flip)
    return patch_share + (1 - patch_share) * base


def targeted_patch_selection_score(clean_accuracy: Q, flip: Q, patch_share: Q) -> Q:
    """Selection-set score after memorizing failed items only.

    This is what item-level feedback supplies: each patch turns one failed
    item into a pass and leaves every other item unchanged.  ``patch_share``
    is measured against the whole set and cannot exceed the failure share.
    """

    base = observed_accuracy(clean_accuracy, flip)
    if not 0 <= patch_share <= 1 - base:
        raise ValueError("patch share must lie between zero and the failure share")
    return base + patch_share


def ceiling_detection_threshold(clean_accuracy: Q, flip: Q) -> Q:
    """Share of the set, memorized independently of outcomes, above which the
    selection score exceeds the noise ceiling.

    Below this share the ceiling check is silent however much was memorized.
    """

    base = observed_accuracy(clean_accuracy, flip)
    if base >= 1:
        raise ValueError("base observed accuracy must be below one")
    return max(Q(0), (noise_ceiling(flip) - base) / (1 - base))


def targeted_ceiling_detection_threshold(clean_accuracy: Q, flip: Q) -> Q:
    """Share of the set, patched on failed items only, above which the
    selection score exceeds the noise ceiling.

    As a share of the failed items this equals ``ceiling_detection_threshold``;
    as a share of the set it is smaller by the failure share.
    """

    base = observed_accuracy(clean_accuracy, flip)
    if base >= 1:
        raise ValueError("base observed accuracy must be below one")
    return max(Q(0), noise_ceiling(flip) - base)


def failed_item_noise_share(clean_accuracy: Q, flip: Q) -> Q:
    """Probability that an item the base predictor fails has a flipped label.

    The predictor errs on the clean label independently of the flip.  It fails
    the observed label either by being right about a flipped item or wrong
    about an unflipped one.
    """

    wrong_because_flipped = flip * clean_accuracy
    wrong_unflipped = (1 - flip) * (1 - clean_accuracy)
    if wrong_because_flipped + wrong_unflipped == 0:
        raise ValueError("the predictor never fails an observed label")
    return wrong_because_flipped / (wrong_because_flipped + wrong_unflipped)


def noise_ceiling_fixture() -> dict[str, Q]:
    clean, flip = Q(4, 5), Q(1, 10)
    base = observed_accuracy(clean, flip)
    targeted = targeted_ceiling_detection_threshold(clean, flip)
    return {
        "clean_accuracy": clean, "flip_probability": flip,
        "base_observed_accuracy": base,
        "noise_ceiling": noise_ceiling(flip),
        "score_half_memorized": memorized_selection_score(clean, flip, Q(1, 2)),
        "score_fully_memorized": memorized_selection_score(clean, flip, Q(1)),
        "ceiling_detection_threshold": ceiling_detection_threshold(clean, flip),
        "targeted_threshold_share_of_set": targeted,
        "targeted_threshold_share_of_failures": targeted / (1 - base),
        "score_all_failures_patched": targeted_patch_selection_score(clean, flip, 1 - base),
        "failed_item_noise_share": failed_item_noise_share(clean, flip),
    }


@dataclass(frozen=True)
class EvalSet:
    set_id: str
    role: str
    access: str
    item_ids: tuple[str, ...]


@dataclass(frozen=True)
class LoopEvent:
    generation: int
    set_id: str
    kind: str
    item_ids: tuple[str, ...] = ()


def audit_ledger(sets, events, readout_budget, exhaustion_bound):
    """Check a multi-generation feedback ledger against its declarations.

    Malformed declarations raise.  Breaches of a well-formed declaration are
    recorded, and move the affected endpoint to ``not_evaluated``, because a
    breach is a finding about the run and should survive into its report.

    A ``score_query`` or ``item_feedback`` event means the result reached the
    loop.  A ``readout`` event means the experimenter read a sealed set; if a
    loop-affecting decision followed, that reading is itself adaptive, so the
    number of readouts is budgeted.  Identifiers detect recorded overlap only.
    They cannot certify that two differently named items are independent.
    """

    if not sets:
        raise ValueError("at least one evaluation set must be declared")
    if type(readout_budget) is not int or readout_budget < 1:
        raise ValueError("readout budget must be a positive integer")
    if not exhaustion_bound > 0:
        raise ValueError("exhaustion bound must be positive")
    declared, owner = {}, {}
    for item in sets:
        if (not item.set_id or item.role not in ROLES or item.access not in ACCESS_CLASSES
                or not item.item_ids or len(set(item.item_ids)) != len(item.item_ids)):
            raise ValueError("invalid evaluation set declaration")
        if item.set_id in declared:
            raise ValueError("duplicate set identifier")
        if item.role == "readout" and item.access != "sealed":
            raise ValueError("a readout set must be declared sealed")
        for identifier in item.item_ids:
            if identifier in owner:
                raise ValueError("selection/readout identifiers overlap")
            owner[identifier] = item.set_id
        declared[item.set_id] = item
    if not any(item.role == "readout" for item in sets):
        raise ValueError("no readout set declared")

    state = {
        set_id: {"role": item.role, "declared_access": item.access,
                 "size": len(item.item_ids), "score_queries": 0, "patches": 0,
                 "distinct_patched": set(), "readouts": [], "retired_at": None,
                 "breaches": []}
        for set_id, item in declared.items()
    }
    previous = None
    for event in events:
        if (type(event.generation) is not int or event.generation < 0
                or event.kind not in EVENT_KINDS or event.set_id not in declared):
            raise ValueError("invalid loop event")
        if previous is not None and event.generation < previous:
            raise ValueError("events must be ordered by generation")
        previous = event.generation
        target, record = declared[event.set_id], state[event.set_id]
        if event.kind == "readout":
            if target.role != "readout":
                raise ValueError("readout events apply to readout sets only")
            record["readouts"].append(event.generation)
            if len(record["readouts"]) > readout_budget:
                record["breaches"].append(f"readout budget exceeded at generation {event.generation}")
            continue
        if event.kind == "item_feedback":
            if not event.item_ids or not set(event.item_ids) <= set(target.item_ids):
                raise ValueError("item feedback must name items of its own set")
        if target.role == "readout":
            record["breaches"].append(
                f"{event.kind} exposed the readout set at generation {event.generation}")
            continue
        if record["retired_at"] is not None:
            record["breaches"].append(f"used after retirement at generation {event.generation}")
        allowed = ACCESS_CLASSES.index(target.access)
        needed = ACCESS_CLASSES.index("item_level" if event.kind == "item_feedback" else "score_only")
        if needed > allowed:
            record["breaches"].append(
                f"{event.kind} exceeds declared {target.access} access at generation {event.generation}")
        if event.kind == "score_query":
            record["score_queries"] += 1
        else:
            record["patches"] += len(event.item_ids)
            record["distinct_patched"].update(event.item_ids)
            if (record["retired_at"] is None
                    and Q(record["patches"], record["size"]) > exhaustion_bound):
                record["retired_at"] = event.generation

    report = {"selection": {}, "readout": {},
              "identifier_scope": "recorded overlap only; independence is not certified"}
    for set_id, record in state.items():
        if record["role"] == "selection":
            report["selection"][set_id] = {
                "declared_access": record["declared_access"], "size": record["size"],
                "score_queries": record["score_queries"], "patches": record["patches"],
                "distinct_patched": len(record["distinct_patched"]),
                "patch_share": Q(record["patches"], record["size"]),
                "retired_at_generation": record["retired_at"],
                "breaches": tuple(record["breaches"]),
                "selection_scores_usable_as_endpoints": False,
            }
        else:
            report["readout"][set_id] = {
                "size": record["size"], "readouts": len(record["readouts"]),
                "readout_generations": tuple(record["readouts"]),
                "breaches": tuple(record["breaches"]),
                "endpoint_status": "not_evaluated" if record["breaches"] else "evaluable",
            }
    report["declarations_respected"] = not any(
        entry["breaches"] for group in ("selection", "readout")
        for entry in report[group].values())
    return report


def divergence_flags(points, margin):
    """Compare selection-set and readout-set gains between permitted readouts.

    ``points`` are ``(generation, selection_score, readout_score)`` at strictly
    increasing generations.  A flag voids claims resting on the selection set.
    It does not void the sealed readout.
    """

    points = list(points)
    if len(points) < 2:
        raise ValueError("at least two readout points required")
    if not margin >= 0:
        raise ValueError("margin must be nonnegative")
    rows = []
    for (g0, s0, r0), (g1, s1, r1) in zip(points, points[1:]):
        if type(g0) is not int or type(g1) is not int or g1 <= g0:
            raise ValueError("generations must be strictly increasing integers")
        if not all(0 <= value <= 1 for value in (s0, r0, s1, r1)):
            raise ValueError("scores must lie in [0, 1]")
        divergence = (s1 - s0) - (r1 - r0)
        rows.append({"from_generation": g0, "to_generation": g1,
                     "selection_gain": s1 - s0, "readout_gain": r1 - r0,
                     "divergence": divergence, "readout_gap_at_end": s1 - r1,
                     "flagged": divergence > margin})
    return rows


def run_ledger_fixture() -> dict[str, object]:
    """One respected ledger and one breached ledger over the same declarations."""

    selection = EvalSet("S", "selection", "score_only", tuple(f"s{i}" for i in range(8)))
    readout = EvalSet("R", "readout", "sealed", tuple(f"r{i}" for i in range(8)))
    clean_events = (
        LoopEvent(0, "R", "readout"),
        LoopEvent(1, "S", "score_query"), LoopEvent(1, "S", "score_query"),
        LoopEvent(2, "S", "score_query"), LoopEvent(2, "R", "readout"),
    )
    breached_events = clean_events + (
        LoopEvent(3, "S", "item_feedback", ("s0", "s1")),
        LoopEvent(4, "R", "score_query"),
    )
    return {"respected": audit_ledger((selection, readout), clean_events, 3, Q(1, 2)),
            "breached": audit_ledger((selection, readout), breached_events, 3, Q(1, 2))}


def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    order = access_order_fixture()
    smallest = selection_inflation(1, 2, Q(1, 2))
    ladder = {n: selection_inflation(n, 2, Q(1, 2))["readout_gap"] for n in (1, 4, 16, 64)}
    widening = {k: selection_inflation(4, k, Q(1, 2))["readout_gap"] for k in (1, 2, 4, 16)}
    noise = noise_ceiling_fixture()
    ledgers = run_ledger_fixture()
    flags = divergence_flags(((0, Q(7, 10), Q(7, 10)), (50, Q(4, 5), Q(37, 50)),
                              (100, Q(83, 100), Q(73, 100))), Q(1, 50))
    checks = {
        "item_level_separates_equal_scores_and_score_only_does_not":
            order["gaps"]["same_score"] == {"sealed": Q(0), "score_only": Q(0), "item_level": Q(1)},
        "access_classes_ordered": order["access_classes_ordered_by_coarsening"],
        "two_candidates_one_item_gap_is_quarter": smallest["readout_gap"] == Q(1, 4),
        "single_candidate_has_no_selection_gap": widening[1] == 0,
        "selection_gap_shrinks_with_items": ladder[1] > ladder[4] > ladder[16] > ladder[64] > 0,
        "selection_gap_grows_with_candidates": widening[1] < widening[2] < widening[4] < widening[16],
        "full_memorization_exceeds_noise_ceiling":
            noise["score_fully_memorized"] == 1 > noise["noise_ceiling"],
        "half_memorization_stays_below_ceiling":
            noise["score_half_memorized"] < noise["noise_ceiling"],
        "ceiling_check_threshold_is_eight_thirteenths":
            noise["ceiling_detection_threshold"] == Q(8, 13),
        "targeted_patching_crosses_at_four_twentyfifths_of_set":
            noise["targeted_threshold_share_of_set"] == Q(4, 25)
            and noise["targeted_threshold_share_of_failures"] == noise["ceiling_detection_threshold"],
        "failed_items_enriched_for_flipped_labels":
            noise["failed_item_noise_share"] == Q(4, 13) > noise["flip_probability"],
        "respected_ledger_leaves_readout_evaluable":
            ledgers["respected"]["declarations_respected"]
            and ledgers["respected"]["readout"]["R"]["endpoint_status"] == "evaluable",
        "breached_ledger_withholds_endpoint":
            ledgers["breached"]["readout"]["R"]["endpoint_status"] == "not_evaluated"
            and bool(ledgers["breached"]["selection"]["S"]["breaches"]),
        "selection_scores_never_endpoints":
            not ledgers["respected"]["selection"]["S"]["selection_scores_usable_as_endpoints"],
        "divergence_flags_fire_when_selection_outruns_readout":
            [row["flagged"] for row in flags] == [True, True]
            and flags[1]["readout_gain"] < 0 < flags[1]["selection_gain"],
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "access_order": order,
            "selection_inflation": {"one_item_two_candidates": smallest,
                                    "gap_by_items_two_candidates": ladder,
                                    "gap_by_candidates_four_items": widening},
            "noise_ceiling": noise, "ledger": ledgers, "divergence": flags}
