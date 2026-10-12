"""Exact limits on a learning loop's training signal, typed as feedback channels.

In the calculus of evaluation design an RL environment is an evaluation
record whose judgment is fed back into the controller roster every
generation: ``Feedback`` applied to the training distribution at the access
class the reward exposes.  This module makes four consequences exact and
finite.  Nothing here calls a model, trains a policy, or runs an environment.

1. Credit assignment is an access class at the step level.  Outcome reward,
   first-failure reward, partial credit and process reward are partitions of
   the step-outcome record, ordered by refinement where they are comparable;
   the number of distinct images bounds what one episode can tell the loop.
2. Score-only access is reconstructible.  A loop that can test patches and
   read a score recovers which items fail by adaptive group testing, and a
   counting bound gives the fewest score queries that could do it, so the
   ledger's ``score_queries`` count bounds the leak.
3. A judge whose errors are correlated with the controller's inflates
   observed accuracy by an exact amount and can reach the noise ceiling
   without any memorization.
4. A finer channel is worth at least as much to the loop's selection
   decision (the garbling direction of Blackwell's ordering), and two
   incomparable channels can each be worth more for some decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as Q
from functools import lru_cache
from itertools import combinations, product
from math import comb

from spiral_ln.evaluation_game_feedback import ACCESS_CLASSES, noise_ceiling, observed_accuracy

CREDIT_KINDS = ("outcome", "first_failure", "count", "process")
JUDGE_KINDS = ("verifier", "learned")


def _image(distribution: dict[str, Q]) -> str:
    if len(distribution) != 1 or sum(distribution.values()) != 1:
        raise ValueError("deterministic kernel required")
    return next(iter(distribution))


# --- 1. credit assignment as a step-level access class -------------------------

def credit_channel(kind: str, steps: int) -> dict[str, dict[str, Q]]:
    """Deterministic reward channel on a step-outcome record of length ``steps``.

    ``outcome`` passes iff every step is correct; ``first_failure`` reports the
    position of the first incorrect step, or pass; ``count`` reports the number
    of correct steps; ``process`` reports the record itself.
    """

    if kind not in CREDIT_KINDS:
        raise ValueError("unknown credit kind")
    if type(steps) is not int or steps < 1:
        raise ValueError("steps must be a positive integer")
    kernel = {}
    for bits in product("01", repeat=steps):
        record = "".join(bits)
        if kind == "outcome":
            image = "pass" if "0" not in record else "fail"
        elif kind == "first_failure":
            image = "pass" if "0" not in record else f"fail@{record.index('0') + 1}"
        elif kind == "count":
            image = f"score={record.count('1')}"
        else:
            image = record
        kernel[record] = {image: Q(1)}
    return kernel


def image_count(kernel: dict[str, dict[str, Q]]) -> int:
    """Number of distinct images of a deterministic channel."""

    if not kernel:
        raise ValueError("empty kernel")
    return len({_image(value) for value in kernel.values()})


def refines(fine: dict[str, dict[str, Q]], coarse: dict[str, dict[str, Q]]) -> bool:
    """True iff ``coarse`` factors through ``fine``: records with equal fine
    images have equal coarse images."""

    if set(fine) != set(coarse):
        raise ValueError("kernels must share a domain")
    seen: dict[str, str] = {}
    for record, image in fine.items():
        coarse_image = _image(coarse[record])
        if seen.setdefault(_image(image), coarse_image) != coarse_image:
            return False
    return True


def episodes_to_distinguish(kernel: dict[str, dict[str, Q]], hypotheses: int) -> int:
    """Fewest episodes of this channel after which ``hypotheses`` alternatives
    could all be told apart.  Counting bound: ``images ** episodes`` outcomes
    must cover the hypotheses.  A one-image channel distinguishes nothing."""

    if type(hypotheses) is not int or hypotheses < 1:
        raise ValueError("hypotheses must be a positive integer")
    images = image_count(kernel)
    if hypotheses == 1:
        return 0
    if images == 1:
        raise ValueError("a one-image channel cannot distinguish hypotheses")
    episodes, reach = 0, 1
    while reach < hypotheses:
        episodes += 1
        reach *= images
    return episodes


# --- 2. reconstructing item-level knowledge from score queries ------------------

def score_query_lower_bound(items: int, failed: int) -> int:
    """Fewest score queries that could identify which ``failed`` of ``items``
    fail, once the failure count is known.

    A query names a subset to patch and returns how many of its items were
    failing, one of ``failed + 1`` values; ``q`` queries distinguish at most
    ``(failed + 1) ** q`` failure sets, and there are ``comb(items, failed)``.
    """

    if type(items) is not int or type(failed) is not int or items < 1 or not 0 <= failed <= items:
        raise ValueError("items must be positive and 0 <= failed <= items")
    targets = comb(items, failed)
    queries, reach = 0, 1
    while reach < targets:
        queries += 1
        reach *= failed + 1
    return queries


def binary_splitting(items: int, failed: frozenset[int]) -> tuple[frozenset[int], int]:
    """Identify the failed set by recursive halving.  Returns the recovered set
    and the number of score queries used, counting the first query that
    reveals the failure count."""

    if type(items) is not int or items < 1 or not failed <= frozenset(range(items)):
        raise ValueError("failed must be a subset of range(items)")
    queries = 0
    found: set[int] = set()

    def count(subset: frozenset[int]) -> int:
        nonlocal queries
        queries += 1
        return len(failed & subset)

    def search(subset: frozenset[int], known: int) -> None:
        if known == 0:
            return
        if known == len(subset):
            found.update(subset)
            return
        ordered = sorted(subset)
        left = frozenset(ordered[: len(ordered) // 2])
        right = frozenset(ordered[len(ordered) // 2:])
        left_count = count(left)
        search(left, left_count)
        search(right, known - left_count)

    everything = frozenset(range(items))
    search(everything, count(everything))
    return frozenset(found), queries


def binary_splitting_worst_case(items: int, failed: int) -> int:
    """Most queries binary splitting uses over every failure set of that size."""

    if type(items) is not int or type(failed) is not int or items < 1 or not 0 <= failed <= items:
        raise ValueError("items must be positive and 0 <= failed <= items")
    worst = 0
    for subset in combinations(range(items), failed):
        recovered, used = binary_splitting(items, frozenset(subset))
        if recovered != frozenset(subset):
            raise AssertionError("binary splitting failed to recover a set")
        worst = max(worst, used)
    return worst


def exact_min_queries(items: int, failed: int) -> int:
    """Minimax number of score queries, after the failure count is known, that
    an adaptive strategy needs to identify the failed set.  Exhaustive over
    strategies; feasible only for small ``items``."""

    if type(items) is not int or type(failed) is not int or not 1 <= items <= 7 or not 0 <= failed <= items:
        raise ValueError("items must lie in 1..7 and 0 <= failed <= items")
    subsets = [frozenset(s) for size in range(1, items) for s in combinations(range(items), size)]

    def counting_bound(candidates: int) -> int:
        queries, reach = 0, 1
        while reach < candidates:
            queries += 1
            reach *= failed + 1
        return queries

    @lru_cache(maxsize=None)
    def solve(candidates: frozenset[frozenset[int]]) -> int:
        if len(candidates) <= 1:
            return 0
        bound = counting_bound(len(candidates))
        best = None
        for subset in subsets:
            groups: dict[int, list[frozenset[int]]] = {}
            for candidate in candidates:
                groups.setdefault(len(candidate & subset), []).append(candidate)
            if len(groups) == 1:
                continue
            worst = 1 + max(solve(frozenset(group)) for group in groups.values())
            if best is None or worst < best:
                best = worst
            if best == bound:
                break
        return best

    return solve(frozenset(frozenset(c) for c in combinations(range(items), failed)))


# --- 3. a judge that shares errors with the judged ----------------------------

def shared_error_bounds(accuracy: Q, judge_error: Q) -> tuple[Q, Q]:
    """Feasible range of ``eps1``, the judge's error rate on items the
    controller gets wrong, given the controller's accuracy and the judge's
    marginal error rate ``judge_error = a * eps0 + (1 - a) * eps1``."""

    if not 0 < accuracy < 1 or not 0 <= judge_error <= 1:
        raise ValueError("accuracy must lie strictly inside (0, 1) and judge_error in [0, 1]")
    low = max(Q(0), (judge_error - accuracy) / (1 - accuracy))
    high = min(Q(1), judge_error / (1 - accuracy))
    return low, high


def observed_accuracy_shared(accuracy: Q, judge_error: Q, eps1: Q) -> Q:
    """Observed accuracy against a binary judge whose error rate is ``eps1`` on
    the controller's wrong answers and ``eps0`` on its right ones, with the
    marginal error held at ``judge_error``.  Binary labels: a wrong judge on a
    wrong answer marks it correct."""

    low, high = shared_error_bounds(accuracy, judge_error)
    if not low <= eps1 <= high:
        raise ValueError("eps1 is infeasible for the marginal judge error")
    eps0 = (judge_error - (1 - accuracy) * eps1) / accuracy
    return accuracy * (1 - eps0) + (1 - accuracy) * eps1


def judge_correlation_inflation(accuracy: Q, judge_error: Q, eps1: Q) -> Q:
    """Observed accuracy under shared errors minus observed accuracy under
    independent errors.  Identity: ``2 (1 - a) (eps1 - judge_error)``."""

    return observed_accuracy_shared(accuracy, judge_error, eps1) - observed_accuracy(accuracy, judge_error)


def ceiling_reachable_without_memorization(accuracy: Q, judge_error: Q) -> bool:
    """True iff some feasible ``eps1`` lifts observed accuracy to the noise
    ceiling ``1 - judge_error``.  That happens exactly at ``eps1 >= 1/2``, so
    the condition is ``judge_error >= (1 - accuracy) / 2``."""

    if not judge_error < Q(1, 2):
        raise ValueError("the ceiling 1 - eps presumes eps below one half")
    _, high = shared_error_bounds(accuracy, judge_error)
    return high >= Q(1, 2)


# --- 4. value of a channel to the loop's selection decision -------------------

def selection_value(kernel: dict[str, dict[str, Q]], types: dict[str, dict[str, Q]],
                    prior: dict[str, Q], utility: dict[str, Q]) -> Q:
    """Bayes value of keeping one of two candidates, each of an independent
    type drawn from ``prior``, after seeing each candidate's channel image.
    ``types`` maps a type to its record distribution; the kept candidate pays
    its type's utility."""

    if set(types) != set(prior) or set(types) != set(utility):
        raise ValueError("types, prior and utility must name the same types")
    if sum(prior.values()) != 1 or any(p < 0 for p in prior.values()):
        raise ValueError("prior must be a distribution")
    for distribution in types.values():
        if sum(distribution.values()) != 1 or any(p < 0 for p in distribution.values()):
            raise ValueError("each type needs a record distribution")
        if not set(distribution) <= set(kernel):
            raise ValueError("records must lie in the kernel's domain")
    gain: dict[tuple[str, str], list[Q]] = {}
    for first, second in product(types, repeat=2):
        for record_1, p_1 in types[first].items():
            for record_2, p_2 in types[second].items():
                weight = prior[first] * p_1 * prior[second] * p_2
                if weight == 0:
                    continue
                observation = (_image(kernel[record_1]), _image(kernel[record_2]))
                entry = gain.setdefault(observation, [Q(0), Q(0)])
                entry[0] += weight * utility[first]
                entry[1] += weight * utility[second]
    return sum((max(entry) for entry in gain.values()), Q(0))


# --- typing an RL setup -------------------------------------------------------

@dataclass(frozen=True)
class TrainingSignal:
    """What an RL setup declares about its training signal, in calculus terms."""

    training_items: int
    steps_per_episode: int
    episode_access: str
    step_credit: str
    judge: str
    judge_error: Q
    judge_shared_error: Q | None
    readout_declared: bool

    def __post_init__(self) -> None:
        if type(self.training_items) is not int or self.training_items < 1:
            raise ValueError("training_items must be a positive integer")
        if self.episode_access not in ACCESS_CLASSES or self.step_credit not in CREDIT_KINDS:
            raise ValueError("unknown access class or credit kind")
        if self.judge not in JUDGE_KINDS:
            raise ValueError("unknown judge kind")
        if self.judge == "verifier" and (self.judge_error != 0 or self.judge_shared_error is not None):
            raise ValueError("a verifier has no error rate to declare")
        if self.judge == "learned" and not 0 <= self.judge_error <= 1:
            raise ValueError("a learned judge needs an error rate in [0, 1]")

    def feedback_signature(self) -> dict[str, object]:
        channel = credit_channel(self.step_credit, self.steps_per_episode)
        return {
            "operator": f"Feedback_{{train,{self.episode_access}}}",
            "selection_set_size": self.training_items,
            "step_channel": self.step_credit,
            "step_images": image_count(channel),
            "score_queries_to_reconstruct_one_failure":
                1 + score_query_lower_bound(self.training_items, 1),
            "judge": self.judge,
            "judge_error": self.judge_error,
            "judge_shared_error": self.judge_shared_error,
            "readout_declared": self.readout_declared,
        }


# --- fixtures and verification ------------------------------------------------

def credit_fixture(steps: int = 3) -> dict[str, object]:
    kernels = {kind: credit_channel(kind, steps) for kind in CREDIT_KINDS}
    order = {f"{fine}>={coarse}": refines(kernels[fine], kernels[coarse])
             for fine in CREDIT_KINDS for coarse in CREDIT_KINDS if fine != coarse}
    return {"steps": steps,
            "images": {kind: image_count(kernels[kind]) for kind in CREDIT_KINDS},
            "refinement": order,
            "episodes_to_identify_failing_steps":
                {kind: episodes_to_distinguish(kernels[kind], 2 ** steps) for kind in CREDIT_KINDS}}


def reconstruction_fixture() -> dict[str, object]:
    cells = {}
    for items in (4, 6):
        for failed in range(0, items + 1):
            lower = score_query_lower_bound(items, failed)
            exact = exact_min_queries(items, failed)
            worst = binary_splitting_worst_case(items, failed) - 1
            cells[f"n={items},f={failed}"] = {"lower_bound": lower, "exact": exact,
                                             "binary_splitting": worst}
    return cells


def judge_fixture() -> dict[str, Q]:
    accuracy, judge_error = Q(4, 5), Q(1, 10)
    low, high = shared_error_bounds(accuracy, judge_error)
    return {"accuracy": accuracy, "judge_error": judge_error,
            "independent_observed": observed_accuracy(accuracy, judge_error),
            "eps1_feasible_low": low, "eps1_feasible_high": high,
            "max_shared_observed": observed_accuracy_shared(accuracy, judge_error, high),
            "max_inflation": judge_correlation_inflation(accuracy, judge_error, high),
            "noise_ceiling": noise_ceiling(judge_error)}


def decision_fixture() -> dict[str, dict[str, Q]]:
    steps = 2
    kernels = {"sealed": {record: {"sealed": Q(1)} for record in credit_channel("process", steps)}}
    kernels.update({kind: credit_channel(kind, steps) for kind in CREDIT_KINDS})
    skilled = {"11": Q(9, 16), "10": Q(3, 16), "01": Q(3, 16), "00": Q(1, 16)}
    unskilled = {"11": Q(1, 16), "10": Q(3, 16), "01": Q(3, 16), "00": Q(9, 16)}
    half, unit = {"a": Q(1, 2), "b": Q(1, 2)}, {"a": Q(1), "b": Q(0)}
    problems = {
        "skill": {"a": skilled, "b": unskilled},
        "position_of_failure": {"a": {"10": Q(1)}, "b": {"01": Q(1)}},
        "number_of_failures": {"a": {"01": Q(1)}, "b": {"00": Q(1)}},
    }
    return {name: {kind: selection_value(kernel, types, half, unit) for kind, kernel in kernels.items()}
            for name, types in problems.items()}


def rl_setups_fixture() -> dict[str, dict[str, object]]:
    rlvr = TrainingSignal(1000, 8, "item_level", "outcome", "verifier", Q(0), None, True)
    learned = TrainingSignal(1000, 8, "item_level", "process", "learned", Q(1, 10), Q(1, 2), False)
    return {"rlvr_outcome_reward": rlvr.feedback_signature(),
            "learned_process_reward": learned.feedback_signature()}


def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    credit = credit_fixture(3)
    recon = reconstruction_fixture()
    judge = judge_fixture()
    decision = decision_fixture()
    setups = rl_setups_fixture()
    steps = credit["steps"]
    checks = {
        "credit_images_are_2_T+1_T+1_2^T":
            [credit["images"][k] for k in CREDIT_KINDS] == [2, steps + 1, steps + 1, 2 ** steps],
        "outcome_coarser_than_every_other_channel":
            all(credit["refinement"][f"{k}>=outcome"] for k in CREDIT_KINDS if k != "outcome"),
        "process_finer_than_every_other_channel":
            all(credit["refinement"][f"process>={k}"] for k in CREDIT_KINDS if k != "process"),
        "count_and_first_failure_incomparable":
            not credit["refinement"]["count>=first_failure"]
            and not credit["refinement"]["first_failure>=count"],
        "outcome_reward_needs_T_episodes_per_T_binary_hypotheses":
            credit["episodes_to_identify_failing_steps"]["outcome"] == steps
            and credit["episodes_to_identify_failing_steps"]["process"] == 1,
        "reconstruction_lower_bound_le_exact_le_binary_splitting":
            all(c["lower_bound"] <= c["exact"] <= c["binary_splitting"] for c in recon.values()),
        "binary_splitting_within_f_times_log2_n_queries":
            all(c["binary_splitting"] <= int(key.split("f=")[1]) * (int(key[2:key.index(",")]) - 1).bit_length()
                for key, c in recon.items()),
        "independent_judge_gives_37_over_50": judge["independent_observed"] == Q(37, 50),
        "maximally_shared_judge_reaches_ceiling_without_memorization":
            judge["max_shared_observed"] == judge["noise_ceiling"] == Q(9, 10)
            and judge["eps1_feasible_high"] == Q(1, 2),
        "judge_inflation_is_4_over_25": judge["max_inflation"] == Q(4, 25),
        "ceiling_reachable_iff_eps_ge_half_the_error_rate":
            ceiling_reachable_without_memorization(Q(4, 5), Q(1, 10))
            and not ceiling_reachable_without_memorization(Q(4, 5), Q(9, 100))
            and ceiling_reachable_without_memorization(Q(9, 10), Q(1, 20)),
        "selection_value_monotone_along_refinement":
            all(v["sealed"] <= v["outcome"] <= v["count"] <= v["process"]
                and v["outcome"] <= v["first_failure"] <= v["process"] for v in decision.values()),
        "count_sufficient_for_exchangeable_steps":
            decision["skill"]["count"] == decision["skill"]["process"] > decision["skill"]["first_failure"],
        "incomparable_channels_each_win_some_decision":
            decision["position_of_failure"]["first_failure"] > decision["position_of_failure"]["count"]
            and decision["number_of_failures"]["count"] > decision["number_of_failures"]["first_failure"],
        "rlvr_setup_types_as_item_level_feedback_with_two_image_steps":
            setups["rlvr_outcome_reward"]["operator"] == "Feedback_{train,item_level}"
            and setups["rlvr_outcome_reward"]["step_images"] == 2,
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "credit": credit, "reconstruction": recon, "judge": judge,
            "decision": decision, "rl_setups": setups}
