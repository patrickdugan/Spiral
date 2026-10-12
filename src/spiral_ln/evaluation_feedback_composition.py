"""Composition laws of Feedback with the other evaluation-design operators.

Exact, finite, deterministic.  Nothing in this module calls a model, trains a
learner, or runs an improvement loop.  It builds a tiny executable model of
the record E = <G, Pi, D, Z, J, A, C> of ``paper/evaluation_design_calculus.md``,
gives every operator of that calculus an explicit read/write footprint over
the record's fields, adds Feedback_{s,q} from
``paper/evaluation_feedback_insertions.md`` as one more such operator, and
audits four things:

* commutation of every pair of operators on an enumerated state space,
  against the calculus's disjoint-update law (sufficient, not necessary);
* the typing judgment Gamma |- d : E -> E' for sequences containing Feedback,
  compiled to the ``(sets, events)`` input of ``audit_ledger``;
* the unit of aggregation under Repeat with a carry map;
* the readout gap rho = V^s - V^r under an offline Rescore.

Assumptions and boundaries.  The game is the calculus's two-location game,
played once per item; an item is a prompt whose identifier the player sees
and whose resource location the player sees only when ``revealed``.  The
controller is a lookup policy with per-item overrides, so patching a failed
item is memorization of that item's identifier.  Acquisition Z and judgment
J are deterministic functions.  Aggregation A enters only through the Repeat
fixture and the claim C is not modeled.  Every law below concerns design-time
transformations of the record; none is a statement about what a learned
controller does with the information (calculus, section 5).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction as Q
from itertools import product

from spiral_ln.evaluation_game_feedback import (
    ACCESS_CLASSES, ROLES, EvalSet, LoopEvent, audit_ledger, selection_inflation,
)

LOCATIONS = ("left", "right")
OBSERVATIONS = ("left", "right", "hidden")
CARRY_MAPS = ("reset", "controller")
RULES = ("always_left", "always_right", "follow")
FIELDS = (
    "game.legal", "game.revealed", "game.utility", "game.budget", "game.horizon",
    "game.carry", "pi", "items", "acquisition", "judgment", "generation",
    "declarations",
)
OPERATOR_KINDS = ("restrict", "grant", "cap", "hide", "observe", "controller",
                  "rescore", "payoff", "repeat", "feedback", "readout")
FEEDBACK_READS = frozenset({"game.legal", "game.revealed", "pi", "items",
                            "acquisition", "judgment", "generation", "declarations"})


# --- the record E ----------------------------------------------------------

@dataclass(frozen=True)
class Utility:
    """Assigned trajectory utility U: one unit for finding the resource, less
    ``right_cost`` whenever the player chooses right.  Nothing reads it unless
    a Payoff operator also installs it as the judgment (``trains=True``)."""

    right_cost: Q = Q(0)

    def __post_init__(self):
        if not isinstance(self.right_cost, Q) or self.right_cost < 0:
            raise ValueError("right_cost must be a nonnegative Fraction")


@dataclass(frozen=True)
class Game:
    """G: legal actions, the player's observation channel, utility, a resource
    budget, and the Repeat structure (horizon and reset/carry map)."""

    legal: tuple[str, ...]
    revealed: bool
    utility: Utility = Utility()
    budget: int = 4
    horizon: int = 1
    carry: str = "reset"

    def __post_init__(self):
        if (not self.legal or tuple(sorted(set(self.legal))) != self.legal
                or not set(self.legal) <= set(LOCATIONS)):
            raise ValueError("legal must be a nonempty sorted subset of the locations")
        if type(self.revealed) is not bool:
            raise ValueError("revealed must be a bool")
        if not isinstance(self.utility, Utility):
            raise ValueError("utility must be a Utility")
        if type(self.budget) is not int or self.budget < 0:
            raise ValueError("budget must be a nonnegative integer")
        if type(self.horizon) is not int or self.horizon < 1:
            raise ValueError("horizon must be a positive integer")
        if self.carry not in CARRY_MAPS:
            raise ValueError("unknown carry map")


@dataclass(frozen=True)
class Policy:
    """Pi: a lookup table from observation to action, with per-item overrides
    that take precedence.  An override is a memorized item identifier."""

    default: tuple[tuple[str, str], ...]
    overrides: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if not all(isinstance(pair, tuple) and len(pair) == 2
                   for pair in self.default + self.overrides):
            raise ValueError("policy tables are tuples of pairs")
        if (tuple(o for o, _ in self.default) != OBSERVATIONS
                or any(a not in LOCATIONS for _, a in self.default)):
            raise ValueError("default must map every observation to a location")
        ids = [i for i, _ in self.overrides]
        if ids != sorted(set(ids)) or any(a not in LOCATIONS for _, a in self.overrides):
            raise ValueError("overrides must be sorted, unique, and map to locations")

    def intended(self, item_id: str, observation: str) -> str:
        for identifier, action in self.overrides:
            if identifier == item_id:
                return action
        return dict(self.default)[observation]


def lookup_policy(rule: str, overrides: tuple[tuple[str, str], ...] = ()) -> Policy:
    tables = {"always_left": ("left", "left", "left"),
              "always_right": ("right", "right", "right"),
              "follow": ("left", "right", "left")}
    if rule not in tables:
        raise ValueError("unknown lookup rule")
    return Policy(tuple(zip(OBSERVATIONS, tables[rule])), tuple(overrides))


CANDIDATES = tuple(lookup_policy(rule) for rule in RULES)


@dataclass(frozen=True)
class Item:
    """One game instance of D: an identifier, the set it belongs to, and the
    location of the unit-valued resource."""

    item_id: str
    set_id: str
    resource: str

    def __post_init__(self):
        if not self.item_id or not self.set_id or self.resource not in LOCATIONS:
            raise ValueError("invalid item")


@dataclass(frozen=True)
class Acquisition:
    """Z: the privileged record of each trace, with the player's action removed
    from the records of the named sets.  Redaction is observation-only: it
    acts after play and changes nothing the player saw or received."""

    redacted_sets: tuple[str, ...] = ()

    def __post_init__(self):
        if list(self.redacted_sets) != sorted(set(self.redacted_sets)):
            raise ValueError("redacted sets must be sorted and unique")


@dataclass(frozen=True)
class Judgment:
    """J on an acquired record: one when the recorded action found the
    resource, inverted on ``flipped`` items, less ``right_cost`` when the
    recorded action is right; undefined (None) when the record has no action."""

    flipped: tuple[str, ...] = ()
    right_cost: Q = Q(0)

    def __post_init__(self):
        if list(self.flipped) != sorted(set(self.flipped)):
            raise ValueError("flipped items must be sorted and unique")
        if not isinstance(self.right_cost, Q) or self.right_cost < 0:
            raise ValueError("right_cost must be a nonnegative Fraction")


@dataclass(frozen=True)
class Declaration:
    set_id: str
    role: str
    access: str


@dataclass(frozen=True)
class Record:
    """The record E.  ``generation`` is the index g advanced by Feedback."""

    game: Game
    pi: Policy
    items: tuple[Item, ...]
    acquisition: Acquisition
    judgment: Judgment
    generation: int
    declarations: tuple[Declaration, ...]

    def __post_init__(self):
        if not isinstance(self.game, Game) or not isinstance(self.pi, Policy):
            raise ValueError("game and pi must be a Game and a Policy")
        if not isinstance(self.acquisition, Acquisition) or not isinstance(self.judgment, Judgment):
            raise ValueError("acquisition and judgment must be an Acquisition and a Judgment")
        if not self.items or any(not isinstance(item, Item) for item in self.items):
            raise ValueError("items must be a nonempty tuple of Item")
        ids = [item.item_id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("item identifiers must be unique")
        if not self.declarations or any(not isinstance(d, Declaration) for d in self.declarations):
            raise ValueError("declarations must be a nonempty tuple of Declaration")
        set_ids = [d.set_id for d in self.declarations]
        if len(set(set_ids)) != len(set_ids):
            raise ValueError("duplicate set identifier")
        for d in self.declarations:
            if not d.set_id or d.role not in ROLES or d.access not in ACCESS_CLASSES:
                raise ValueError("invalid declaration")
            if d.role == "readout" and d.access != "sealed":
                raise ValueError("a readout set must be declared sealed")
            if all(item.set_id != d.set_id for item in self.items):
                raise ValueError("every declared set needs at least one item")
        if any(item.set_id not in set_ids for item in self.items):
            raise ValueError("every item must belong to a declared set")
        if type(self.generation) is not int or self.generation < 0:
            raise ValueError("generation must be a nonnegative integer")


def project(record: Record, field: str):
    if field not in FIELDS:
        raise ValueError("unknown field")
    if field.startswith("game."):
        return getattr(record.game, field[5:])
    return getattr(record, field)


# --- play, acquisition, judgment --------------------------------------------

@dataclass(frozen=True)
class Trace:
    item_id: str
    set_id: str
    observation: str
    action: str
    resource: str


@dataclass(frozen=True)
class Acquired:
    item_id: str
    set_id: str
    action: str | None
    resource: str


def play(game: Game, pi: Policy, item: Item) -> Trace:
    """One trajectory.  The fallback for an illegal intended action is the
    first legal action, as the calculus requires a defined fallback."""

    observation = item.resource if game.revealed else "hidden"
    action = pi.intended(item.item_id, observation)
    if action not in game.legal:
        action = game.legal[0]
    return Trace(item.item_id, item.set_id, observation, action, item.resource)


def acquire(acquisition: Acquisition, trace: Trace) -> Acquired:
    action = None if trace.set_id in acquisition.redacted_sets else trace.action
    return Acquired(trace.item_id, trace.set_id, action, trace.resource)


def judge(judgment: Judgment, acquired: Acquired) -> Q | None:
    if acquired.action is None:
        return None
    value = Q(int(acquired.action == acquired.resource))
    if acquired.item_id in judgment.flipped:
        value = 1 - value
    if acquired.action == "right":
        value -= judgment.right_cost
    return value


def item_outcomes(record: Record, set_id: str) -> tuple[tuple[str, str | None, Q | None], ...]:
    """J composed with Z on one set: (item, recorded action, judgment) per item."""

    if set_id not in {d.set_id for d in record.declarations}:
        raise ValueError("unknown set")
    rows = []
    for item in record.items:
        if item.set_id == set_id:
            acquired = acquire(record.acquisition, play(record.game, record.pi, item))
            rows.append((item.item_id, acquired.action, judge(record.judgment, acquired)))
    return tuple(rows)


def set_score(record: Record, set_id: str) -> Q | None:
    """Sum of J over the set's records; None when any record is unjudgeable."""

    judgments = [j for _, _, j in item_outcomes(record, set_id)]
    return None if any(j is None for j in judgments) else sum(judgments, Q(0))


def set_value(record: Record, set_id: str) -> Q | None:
    """V^s: the mean judgment over the set."""

    score = set_score(record, set_id)
    return None if score is None else score / sum(item.set_id == set_id for item in record.items)


def readout_gap(record: Record, selection_id: str = "S", readout_id: str = "R") -> Q | None:
    """rho = V^s - V^r for one controller; None if either value is unjudgeable."""

    left, right = set_value(record, selection_id), set_value(record, readout_id)
    return None if left is None or right is None else left - right


# --- operators with footprints ---------------------------------------------

@dataclass(frozen=True)
class Op:
    """A design-time transformation E -> E' with a declared footprint."""

    kind: str
    params: tuple
    name: str
    reads: frozenset[str]
    writes: frozenset[str]

    def __post_init__(self):
        if self.kind not in OPERATOR_KINDS or not (self.reads | self.writes) <= set(FIELDS):
            raise ValueError("invalid operator")


def restrict(actions: tuple[str, ...]) -> Op:
    """Restrict_B: legal := legal intersected with B."""

    actions = tuple(sorted(set(actions)))
    if not actions or not set(actions) <= set(LOCATIONS):
        raise ValueError("Restrict needs a nonempty set of locations")
    return Op("restrict", (actions,), f"Restrict[{','.join(actions)}]",
              frozenset({"game.legal"}), frozenset({"game.legal"}))


def grant(amount: int) -> Op:
    """Budget: grant ``amount`` units."""

    if type(amount) is not int or amount < 0:
        raise ValueError("grant amount must be a nonnegative integer")
    return Op("grant", (amount,), f"Grant[{amount}]",
              frozenset({"game.budget"}), frozenset({"game.budget"}))


def cap(limit: int) -> Op:
    """Budget: cap the balance at ``limit``."""

    if type(limit) is not int or limit < 0:
        raise ValueError("cap limit must be a nonnegative integer")
    return Op("cap", (limit,), f"Cap[{limit}]",
              frozenset({"game.budget"}), frozenset({"game.budget"}))


def hide() -> Op:
    """Hide_{i,q}, player-facing: the resource location leaves the player's
    observation before action.  This edits G."""

    return Op("hide", (), "Hide[player]", frozenset(), frozenset({"game.revealed"}))


def observe(redacted_sets: tuple[str, ...]) -> Op:
    """Observe_q, observation-only: Z drops the action from the records of the
    named sets after play.  This edits Z and nothing the player sees."""

    redacted = tuple(sorted(set(redacted_sets)))
    return Op("observe", (redacted,), f"Observe[redact:{','.join(redacted) or '-'}]",
              frozenset(), frozenset({"acquisition"}))


def controller(pi: Policy, label: str) -> Op:
    """Controller_pi: replace the controller."""

    if not isinstance(pi, Policy):
        raise ValueError("controller needs a Policy")
    return Op("controller", (pi,), f"Controller[{label}]", frozenset(), frozenset({"pi"}))


def rescore(judgment: Judgment, label: str) -> Op:
    """Rescore_j: replace the judgment offline."""

    if not isinstance(judgment, Judgment):
        raise ValueError("rescore needs a Judgment")
    return Op("rescore", (judgment,), f"Rescore[{label}]", frozenset(), frozenset({"judgment"}))


def payoff(utility: Utility, trains: bool) -> Op:
    """Payoff_u: replace the assigned utility; with ``trains`` the same
    utility is also installed as the judgment the loop will read."""

    if not isinstance(utility, Utility) or type(trains) is not bool:
        raise ValueError("payoff needs a Utility and a bool")
    writes = {"game.utility"} | ({"judgment"} if trains else set())
    suffix = ",trains" if trains else ""
    return Op("payoff", (utility, trains), f"Payoff[right_cost={utility.right_cost}{suffix}]",
              frozenset(), frozenset(writes))


def repeat(horizon: int, carry: str) -> Op:
    """Repeat_{H,m}: declare the horizon and the reset/carry map."""

    if type(horizon) is not int or horizon < 1 or carry not in CARRY_MAPS:
        raise ValueError("repeat needs a positive horizon and a known carry map")
    return Op("repeat", (horizon, carry), f"Repeat[{horizon},{carry}]",
              frozenset(), frozenset({"game.horizon", "game.carry"}))


def feedback(set_id: str, access: str, candidates: tuple[Policy, ...] = ()) -> Op:
    """Feedback_{s,q}: read J composed with Z on ``set_id`` at access ``q`` and
    produce Pi_{g+1}.  ``item_level`` gives the per-item vector and patches
    failed items; ``score_only`` gives the sum for the incumbent and each
    candidate and keeps the best; ``sealed`` gives nothing and only advances
    the generation."""

    if access not in ACCESS_CLASSES or not set_id:
        raise ValueError("feedback needs a set identifier and an access class")
    if any(not isinstance(c, Policy) for c in candidates):
        raise ValueError("candidates must be policies")
    if access == "sealed":
        reads, writes = {"generation", "declarations"}, {"generation"}
    else:
        reads, writes = FEEDBACK_READS, {"pi", "generation"}
    return Op("feedback", (set_id, access, tuple(candidates)), f"Feedback[{set_id},{access}]",
              frozenset(reads), frozenset(writes))


def readout(set_id: str) -> Op:
    """Readout_t: the experimenter reads V^t.  The record is unchanged; the
    ledger records the reading."""

    if not set_id:
        raise ValueError("readout needs a set identifier")
    return Op("readout", (set_id,), f"Readout[{set_id}]",
              frozenset({"game.legal", "game.revealed", "pi", "items", "acquisition",
                         "judgment", "declarations"}), frozenset())


def patch_failures(pi: Policy, outcomes) -> Policy:
    """Item-level update rule: each item judged nonpositive is overridden with
    the other action.  Unjudgeable items are left alone."""

    overrides = dict(pi.overrides)
    for item_id, action, judgment in outcomes:
        if judgment is None or judgment > 0:
            continue
        overrides[item_id] = "right" if action == "left" else "left"
    return Policy(pi.default, tuple(sorted(overrides.items())))


def select_by_score(record: Record, set_id: str, candidates: tuple[Policy, ...]) -> Policy:
    """Score-only update rule: score the incumbent and each candidate on the
    set and keep the first maximizer; a set that yields no score teaches
    nothing and the incumbent stays."""

    best, best_score = record.pi, None
    for candidate in (record.pi,) + tuple(candidates):
        score = set_score(replace(record, pi=candidate), set_id)
        if score is None:
            return record.pi
        if best_score is None or score > best_score:
            best, best_score = candidate, score
    return best


def _feedback(record: Record, set_id: str, access: str, candidates: tuple[Policy, ...]) -> Record:
    declared = {d.set_id: d for d in record.declarations}
    if set_id not in declared:
        raise ValueError("feedback from an undeclared set")
    if access == "sealed":
        return replace(record, generation=record.generation + 1)
    declaration = declared[set_id]
    if declaration.role != "selection":
        raise ValueError("feedback from a readout set is ill-typed")
    if ACCESS_CLASSES.index(declaration.access) < ACCESS_CLASSES.index(access):
        raise ValueError("feedback exceeds the declared access class; the declaration is ill-typed")
    if access == "item_level":
        pi = patch_failures(record.pi, item_outcomes(record, set_id))
    else:
        pi = select_by_score(record, set_id, candidates)
    return replace(record, pi=pi, generation=record.generation + 1)


def apply(op: Op, record: Record) -> Record:
    """Apply one operator.  Every branch is a pure function of the record."""

    if not isinstance(op, Op) or not isinstance(record, Record):
        raise ValueError("apply needs an Op and a Record")
    game = record.game
    if op.kind == "restrict":
        legal = tuple(a for a in game.legal if a in op.params[0])
        if not legal:
            raise ValueError("Restrict would leave no legal action and no fallback is declared")
        return replace(record, game=replace(game, legal=legal))
    if op.kind == "grant":
        return replace(record, game=replace(game, budget=game.budget + op.params[0]))
    if op.kind == "cap":
        return replace(record, game=replace(game, budget=min(game.budget, op.params[0])))
    if op.kind == "hide":
        return replace(record, game=replace(game, revealed=False))
    if op.kind == "observe":
        return replace(record, acquisition=Acquisition(op.params[0]))
    if op.kind == "controller":
        return replace(record, pi=op.params[0])
    if op.kind == "rescore":
        return replace(record, judgment=op.params[0])
    if op.kind == "payoff":
        utility, trains = op.params
        updated = replace(record, game=replace(game, utility=utility))
        return replace(updated, judgment=Judgment((), utility.right_cost)) if trains else updated
    if op.kind == "repeat":
        horizon, carry = op.params
        return replace(record, game=replace(game, horizon=horizon, carry=carry))
    if op.kind == "feedback":
        return _feedback(record, *op.params)
    if op.kind == "readout":
        if op.params[0] not in {d.set_id for d in record.declarations}:
            raise ValueError("readout of an undeclared set")
        return record
    raise ValueError("unknown operator kind")


def apply_sequence(sequence, record: Record) -> Record:
    for op in sequence:
        record = apply(op, record)
    return record


# --- fixtures: items, declarations, state space -----------------------------

def default_items() -> tuple[Item, ...]:
    return (Item("s0", "S", "left"), Item("s1", "S", "right"),
            Item("r0", "R", "left"), Item("r1", "R", "right"))


def default_declarations(selection_access: str = "item_level") -> tuple[Declaration, ...]:
    return (Declaration("S", "selection", selection_access), Declaration("R", "readout", "sealed"))


def make_record(rule: str = "always_left", overrides=(), legal=LOCATIONS, revealed: bool = True,
                right_cost: Q = Q(0), budget: int = 4, horizon: int = 1, carry: str = "reset",
                redacted=(), flipped=(), judgment_cost: Q = Q(0), generation: int = 0,
                selection_access: str = "item_level") -> Record:
    return Record(
        game=Game(tuple(legal), revealed, Utility(right_cost), budget, horizon, carry),
        pi=lookup_policy(rule, overrides), items=default_items(),
        acquisition=Acquisition(tuple(redacted)), judgment=Judgment(tuple(flipped), judgment_cost),
        generation=generation, declarations=default_declarations(selection_access),
    )


def enumerate_states() -> tuple[Record, ...]:
    """384 records: every combination of the varied fields below, with items,
    declarations, horizon, carry, generation and the judgment's cost fixed."""

    return tuple(
        make_record(rule=rule, overrides=overrides, legal=legal, revealed=revealed,
                    right_cost=cost, budget=budget, redacted=redacted, flipped=flipped)
        for legal, revealed, cost, budget, rule, overrides, redacted, flipped in product(
            (LOCATIONS, ("left",)), (True, False), (Q(0), Q(1)), (3, 4), RULES,
            ((), (("s0", "right"),)), ((), ("S",)), ((), ("s1",)))
    )


def commutation_alphabet() -> tuple[Op, ...]:
    return (
        restrict(("left",)), grant(2), cap(5), hide(), observe(("S",)),
        controller(lookup_policy("follow"), "follow"),
        rescore(Judgment(("s1",), Q(0)), "flip_s1"),
        payoff(Utility(Q(1)), trains=False), payoff(Utility(Q(1)), trains=True),
        repeat(2, "controller"),
        feedback("S", "item_level"), feedback("S", "score_only", CANDIDATES),
        feedback("S", "sealed"),
    )


# --- descriptions for receipts ---------------------------------------------

def describe_policy(pi: Policy) -> str:
    rule = next((name for name in RULES if lookup_policy(name).default == pi.default), "custom")
    if pi.overrides:
        rule += "+" + ",".join(f"{item}->{action}" for item, action in pi.overrides)
    return rule


def describe(value):
    if isinstance(value, Policy):
        return describe_policy(value)
    if isinstance(value, Utility):
        return f"right_cost={value.right_cost}"
    if isinstance(value, Acquisition):
        return "redact:" + ",".join(value.redacted_sets) if value.redacted_sets else "full"
    if isinstance(value, Judgment):
        return f"flip:{','.join(value.flipped) or '-'};right_cost={value.right_cost}"
    if isinstance(value, tuple) and value and isinstance(value[0], Item):
        return ";".join(f"{i.item_id}:{i.set_id}:{i.resource}" for i in value)
    if isinstance(value, tuple) and value and isinstance(value[0], Declaration):
        return ";".join(f"{d.set_id}:{d.role}/{d.access}" for d in value)
    if isinstance(value, tuple):
        return ",".join(value)
    return value


def summarize(record: Record) -> dict[str, object]:
    return {field: describe(project(record, field)) for field in FIELDS}


# --- footprint soundness and commutation -----------------------------------

def footprint_audit(ops, states) -> dict[str, dict[str, object]]:
    """Write soundness: fields outside ``writes`` are unchanged on every
    state.  Read soundness: the written fields' new values are a function of
    the read fields' old values across the state space."""

    results = {}
    for op in ops:
        write_sound, read_sound, table = True, True, {}
        for state in states:
            image = apply(op, state)
            if any(project(image, f) != project(state, f) for f in FIELDS if f not in op.writes):
                write_sound = False
            key = tuple(project(state, f) for f in sorted(op.reads))
            written = tuple(project(image, f) for f in sorted(op.writes))
            if table.setdefault(key, written) != written:
                read_sound = False
        results[op.name] = {"reads": sorted(op.reads), "writes": sorted(op.writes),
                            "write_sound": write_sound, "read_sound": read_sound}
    return results


def footprints_disjoint(a: Op, b: Op) -> bool:
    """The disjoint-update law's premise: neither writes what the other reads
    or writes."""

    return not (a.writes & (b.reads | b.writes)) and not (b.writes & (a.reads | a.writes))


def first_witness(a: Op, b: Op, states):
    """First state on which a;b and b;a differ, or None."""

    for state in states:
        if apply(b, apply(a, state)) != apply(a, apply(b, state)):
            return state
    return None


def commutation_audit(ops, states) -> dict[str, object]:
    """Every unordered pair (diagonal included); a;b == b;a is symmetric in
    the pair, so ordered pairs add nothing.  ``a_then_b`` is a applied first."""

    pairs = []
    for index, a in enumerate(ops):
        for b in ops[index:]:
            state = first_witness(a, b, states)
            witness = None
            if state is not None:
                ab, ba = apply(b, apply(a, state)), apply(a, apply(b, state))
                differs = [f for f in FIELDS if project(ab, f) != project(ba, f)]
                witness = {"state": summarize(state), "differs_in": differs,
                           "a_then_b": {f: describe(project(ab, f)) for f in differs},
                           "b_then_a": {f: describe(project(ba, f)) for f in differs}}
            pairs.append({"a": a.name, "b": b.name, "footprints_disjoint": footprints_disjoint(a, b),
                          "commute": witness is None, "witness": witness})
    return {
        "states": len(states), "operators": [op.name for op in ops], "pairs": pairs,
        "disjoint_update_law_holds": all(p["commute"] for p in pairs if p["footprints_disjoint"]),
        "commute_despite_overlap": [(p["a"], p["b"]) for p in pairs
                                    if p["commute"] and not p["footprints_disjoint"] and p["a"] != p["b"]],
        "noncommuting": [(p["a"], p["b"]) for p in pairs if not p["commute"]],
    }


# --- typing as ledger audit ------------------------------------------------

def compile_ledger(sequence, declarations, items):
    """Translate a design expression into ``audit_ledger`` input.

    An item-level Feedback records one ``item_feedback`` event naming every
    item of the set, because the whole vector reached the loop regardless of
    what the update rule did with it.  A score-only Feedback records one
    ``score_query`` per policy scored (incumbent plus candidates).  A sealed
    Feedback transmits nothing and records nothing.  Readout records one
    ``readout``.  Every other operator is outside the channel.
    """

    members = {d.set_id: tuple(i.item_id for i in items if i.set_id == d.set_id)
               for d in declarations}
    sets = tuple(EvalSet(d.set_id, d.role, d.access, members[d.set_id]) for d in declarations)
    events, generation = [], 0
    for op in sequence:
        if not isinstance(op, Op):
            raise ValueError("sequence must consist of operators")
        if op.kind == "feedback":
            set_id, access, candidates = op.params
            if set_id not in members:
                raise ValueError("feedback names an undeclared set")
            if access == "item_level":
                events.append(LoopEvent(generation, set_id, "item_feedback", members[set_id]))
            elif access == "score_only":
                events.extend(LoopEvent(generation, set_id, "score_query")
                              for _ in range(1 + len(candidates)))
            generation += 1
        elif op.kind == "readout":
            if op.params[0] not in members:
                raise ValueError("readout names an undeclared set")
            events.append(LoopEvent(generation, op.params[0], "readout"))
    return sets, tuple(events)


def typecheck(sequence, declarations, items, readout_budget, exhaustion_bound,
              sealed_requires_selection: bool = False) -> dict[str, object]:
    """The judgment Gamma |- d_1; ...; d_k, with Gamma tracking per-set
    cumulative patches, retirement, and readouts.

    (F-SEL)    Feedback_{s,q}, q > sealed: s declared, role(s) = selection,
               access(s) >= q, s not retired.  Gamma' adds |s| patches for
               item_level and retires s once patches/|s| exceeds the bound;
               the crossing step itself is typed.
    (F-SEALED) Feedback_{s,sealed}: typed; Gamma' = Gamma.  With
               ``sealed_requires_selection`` the literal rule role(s) =
               selection is demanded as well.
    (RO)       Readout_t: role(t) = readout, and the count stays within the
               readout budget.
    (NEUTRAL)  every other operator is typed with Gamma' = Gamma.
    """

    if type(readout_budget) is not int or readout_budget < 1:
        raise ValueError("readout budget must be a positive integer")
    if not isinstance(exhaustion_bound, Q) or exhaustion_bound <= 0:
        raise ValueError("exhaustion bound must be a positive Fraction")
    declared = {d.set_id: d for d in declarations}
    sizes = {s: sum(i.set_id == s for i in items) for s in declared}
    patches = {s: 0 for s in declared}
    retired = {s: False for s in declared}
    readouts = {s: 0 for s in declared}
    violations = []
    for index, op in enumerate(sequence):
        if not isinstance(op, Op):
            raise ValueError("sequence must consist of operators")
        if op.kind == "feedback":
            set_id, access, _ = op.params
            if set_id not in declared:
                violations.append(f"{index}:{op.name}: undeclared set")
            elif access == "sealed":
                if sealed_requires_selection and declared[set_id].role != "selection":
                    violations.append(f"{index}:{op.name}: F-SEALED literal role premise")
            elif declared[set_id].role != "selection":
                violations.append(f"{index}:{op.name}: F-SEL role")
            else:
                if ACCESS_CLASSES.index(declared[set_id].access) < ACCESS_CLASSES.index(access):
                    violations.append(f"{index}:{op.name}: F-SEL access")
                if retired[set_id]:
                    violations.append(f"{index}:{op.name}: F-SEL retired")
                if access == "item_level":
                    patches[set_id] += sizes[set_id]
                    if not retired[set_id] and Q(patches[set_id], sizes[set_id]) > exhaustion_bound:
                        retired[set_id] = True
        elif op.kind == "readout":
            set_id = op.params[0]
            if set_id not in declared or declared[set_id].role != "readout":
                violations.append(f"{index}:{op.name}: RO role")
            else:
                readouts[set_id] += 1
                if readouts[set_id] > readout_budget:
                    violations.append(f"{index}:{op.name}: RO budget")
    return {"well_typed": not violations, "violations": tuple(violations)}


def ledger_verdict(sequence, declarations, items, readout_budget, exhaustion_bound) -> str:
    """``respected``, ``breached`` (report with breaches), or ``malformed``
    (``audit_ledger`` raised)."""

    sets, events = compile_ledger(sequence, declarations, items)
    try:
        report = audit_ledger(sets, events, readout_budget, exhaustion_bound)
    except ValueError:
        return "malformed"
    return "respected" if report["declarations_respected"] else "breached"


def ledger_alphabet() -> tuple[Op, ...]:
    return (feedback("S", "item_level"), feedback("S", "score_only", CANDIDATES),
            feedback("S", "sealed"), feedback("R", "item_level"),
            feedback("R", "score_only", CANDIDATES), feedback("R", "sealed"),
            readout("R"), readout("S"), rescore(Judgment(("s1",), Q(0)), "flip_s1"))


def ledger_contexts() -> tuple[tuple[Declaration, ...], ...]:
    return tuple(default_declarations(access) for access in ACCESS_CLASSES)


def typing_ledger_equivalence(max_length: int = 4, readout_budget: int = 2,
                              exhaustion_bound: Q = Q(1)) -> dict[str, object]:
    """Exhaustively compare ``typecheck`` with ``audit_ledger`` over every
    sequence of length at most ``max_length`` from ``ledger_alphabet`` under
    every declaration context."""

    if type(max_length) is not int or max_length < 0:
        raise ValueError("max_length must be a nonnegative integer")
    alphabet, items = ledger_alphabet(), default_items()
    counts = {"respected": 0, "breached": 0, "malformed": 0}
    mismatches, strict_mismatches, sequences = [], [], 0
    malformed_matches_readout_of_selection = True
    for declarations in ledger_contexts():
        for length in range(max_length + 1):
            for sequence in product(alphabet, repeat=length):
                sequences += 1
                verdict = ledger_verdict(sequence, declarations, items, readout_budget, exhaustion_bound)
                counts[verdict] += 1
                typed = typecheck(sequence, declarations, items, readout_budget, exhaustion_bound)
                names = [op.name for op in sequence]
                context = describe(declarations)
                if typed["well_typed"] != (verdict == "respected"):
                    mismatches.append({"context": context, "sequence": names,
                                       "well_typed": typed["well_typed"], "verdict": verdict,
                                       "violations": typed["violations"]})
                strict = typecheck(sequence, declarations, items, readout_budget, exhaustion_bound,
                                   sealed_requires_selection=True)
                if strict["well_typed"] != (verdict == "respected"):
                    strict_mismatches.append({"context": context, "sequence": names,
                                              "verdict": verdict, "violations": strict["violations"]})
                reads_selection = any(op.kind == "readout" and op.params[0] == "S" for op in sequence)
                if (verdict == "malformed") != reads_selection:
                    malformed_matches_readout_of_selection = False
    sealed_from_readout = feedback("R", "sealed").name
    return {
        "alphabet": [op.name for op in alphabet], "max_length": max_length,
        "contexts": [describe(d) for d in ledger_contexts()],
        "readout_budget": readout_budget, "exhaustion_bound": exhaustion_bound,
        "sequence_count": sequences, "verdict_counts": counts,
        "equivalence_holds": not mismatches, "mismatches": mismatches[:10],
        "malformed_iff_readout_of_selection_set": malformed_matches_readout_of_selection,
        "strict_sealed_role": {
            "equivalence_holds": not strict_mismatches,
            "mismatch_count": len(strict_mismatches),
            "every_mismatch_is_a_respected_run_containing": sealed_from_readout,
            "claim_holds": all(m["verdict"] == "respected" and sealed_from_readout in m["sequence"]
                               and all("F-SEALED" in v for v in m["violations"])
                               for m in strict_mismatches),
            "example": strict_mismatches[0] if strict_mismatches else None,
        },
    }


# --- Repeat with a carry map -----------------------------------------------

def _best_score_distribution(items: int, count: int, p: Q) -> dict[int, Q]:
    """Distribution of the best raw score among ``count`` independent
    candidates with ``items`` independent Bernoulli(p) outcomes each, by
    enumerating every outcome matrix.  ``count == 0`` gives the point mass at
    zero, which is neutral under the maximum with a nonnegative score."""

    if count == 0:
        return {0: Q(1)}
    distribution = {}
    for bits in product((0, 1), repeat=items * count):
        mass = Q(1)
        for bit in bits:
            mass *= p if bit else 1 - p
        best = max(sum(bits[c * items:(c + 1) * items]) for c in range(count))
        distribution[best] = distribution.get(best, Q(0)) + mass
    return distribution


def _two_generation_summary(joint: dict[tuple[int, int], Q], items: int) -> dict[str, object]:
    first = sum(Q(a, items) * mass for (a, _), mass in joint.items())
    second = sum(Q(b, items) * mass for (_, b), mass in joint.items())
    return {
        "expected_generation_1": first, "expected_generation_2": second,
        "generation_mean": (first + second) / 2,
        "prob_second_exceeds_first": sum(m for (a, b), m in joint.items() if b > a),
        "prob_first_exceeds_second": sum(m for (a, b), m in joint.items() if a > b),
        "exchangeable": all(joint.get((b, a), Q(0)) == mass for (a, b), mass in joint.items()),
    }


def repeat_carry_fixture(items: int, candidates: int, p: Q) -> dict[str, object]:
    """Two generations of score-only selection on one selection set.

    Generation 1 scores ``candidates`` independent policies, each succeeding
    independently with probability ``p`` on each of ``items`` items, and keeps
    the best.  Under the carry map the kept policy enters generation 2's pool
    with ``candidates - 1`` fresh policies; its score on the same items is
    unchanged because the items and the policy are fixed.  Under the reset
    map generation 2 is an independent block with ``candidates`` fresh
    policies.  The sealed readout value is ``p`` in both generations.
    """

    if type(items) is not int or type(candidates) is not int or items < 1 or candidates < 1:
        raise ValueError("items and candidates must be positive integers")
    if not isinstance(p, Q) or not 0 <= p <= 1:
        raise ValueError("p must be a Fraction in [0, 1]")
    first = _best_score_distribution(items, candidates, p)
    fresh = _best_score_distribution(items, candidates - 1, p)
    carry_joint, reset_joint = {}, {}
    for a, mass_a in first.items():
        for m, mass_m in fresh.items():
            key = (a, max(a, m))
            carry_joint[key] = carry_joint.get(key, Q(0)) + mass_a * mass_m
        for b, mass_b in first.items():
            reset_joint[(a, b)] = mass_a * mass_b
    carry, reset = _two_generation_summary(carry_joint, items), _two_generation_summary(reset_joint, items)
    one_generation = selection_inflation(items, candidates, p)
    doubled = selection_inflation(items, 2 * candidates - 1, p)
    return {
        "items": items, "candidates": candidates, "p": p, "readout_value": p,
        "one_generation_gap": one_generation["readout_gap"],
        "carry": {**carry, "matches_selection_over_2k_minus_1":
                  carry["expected_generation_2"] == doubled["expected_reported"],
                  "rho_generation_1": carry["expected_generation_1"] - p,
                  "rho_generation_2": carry["expected_generation_2"] - p},
        "reset": {**reset, "matches_independent_blocks":
                  reset["generation_mean"] == one_generation["expected_reported"]},
        "generation_mean_difference": carry["generation_mean"] - reset["generation_mean"],
        "expected_apparent_gain_under_carry": carry["expected_generation_2"] - carry["expected_generation_1"],
        "true_value_change": Q(0),
    }


# --- readout gap under Rescore ---------------------------------------------

def readout_gap_rescore_fixture() -> dict[str, object]:
    """rho moves under an offline Rescore with no selection, and a Rescore of
    the selection set reproduces the rho that item-level Feedback produces."""

    base = make_record(rule="always_left")
    designs = {
        "base": (), "rescore_readout_set": (rescore(Judgment(("r1",), Q(0)), "flip_r1"),),
        "rescore_selection_set": (rescore(Judgment(("s1",), Q(0)), "flip_s1"),),
        "feedback_item_level": (feedback("S", "item_level"),),
    }
    rows = {}
    for name, sequence in designs.items():
        record = apply_sequence(sequence, base)
        sets, events = compile_ledger(sequence, base.declarations, base.items)
        ledger = audit_ledger(sets, events, 2, Q(1))
        rows[name] = {
            "design": [op.name for op in sequence],
            "V_s": set_value(record, "S"), "V_r": set_value(record, "R"), "rho": readout_gap(record),
            "generation": record.generation, "pi": describe_policy(record.pi),
            "pi_changed": record.pi != base.pi,
            "ledger_patches_on_S": ledger["selection"]["S"]["patches"],
            "ledger_declarations_respected": ledger["declarations_respected"],
        }
    rescored, patched = rows["rescore_selection_set"], rows["feedback_item_level"]
    readout_row = rows["rescore_readout_set"]
    return {
        "rows": rows,
        "rescore_of_readout_changes_rho_without_selection":
            readout_row["rho"] != rows["base"]["rho"] and not readout_row["pi_changed"]
            and readout_row["generation"] == rows["base"]["generation"],
        "rescore_of_selection_matches_feedback_rho": rescored["rho"] == patched["rho"],
        "ledger_separates_them": rescored["ledger_patches_on_S"] != patched["ledger_patches_on_S"],
    }


# --- verify ------------------------------------------------------------------

def verify() -> dict[str, object]:
    """Run all exact fixtures and return machine-readable checks."""

    ops, states = commutation_alphabet(), enumerate_states()
    footprints = footprint_audit(ops, states)
    commutation = commutation_audit(ops, states)
    typing = typing_ledger_equivalence()
    carry = repeat_carry_fixture(1, 2, Q(1, 2))
    carry_cells = {f"items={n},candidates={k},p={p}": repeat_carry_fixture(n, k, p)
                   for n, k, p in ((1, 2, Q(1, 2)), (2, 2, Q(1, 2)), (2, 3, Q(1, 3)), (1, 1, Q(1, 2)))}
    rescored = readout_gap_rescore_fixture()
    by_name = {op.name: op for op in ops}
    table = {frozenset((p["a"], p["b"])): p for p in commutation["pairs"]}

    def pair(a, b):
        return table[frozenset((by_name[a].name, by_name[b].name))]

    def differs_only_in_pi(entry):
        return not entry["commute"] and entry["witness"]["differs_in"] == ["pi"]

    budget = pair("Grant[2]", "Cap[5]")
    item, score, sealed = "Feedback[S,item_level]", "Feedback[S,score_only]", "Feedback[S,sealed]"
    checks = {
        "all_footprints_sound_on_state_space":
            all(f["write_sound"] and f["read_sound"] for f in footprints.values()),
        "disjoint_footprints_commute_on_every_state": commutation["disjoint_update_law_holds"],
        "some_overlapping_pairs_commute": bool(commutation["commute_despite_overlap"]),
        "grant_and_cap_reproduce_the_calculus_order_effect":
            budget["witness"] is not None and budget["witness"]["differs_in"] == ["game.budget"]
            and {budget["witness"]["a_then_b"]["game.budget"], budget["witness"]["b_then_a"]["game.budget"]} == {5, 6},
        "rescore_then_feedback_differs_from_feedback_then_rescore_only_in_pi":
            differs_only_in_pi(pair("Rescore[flip_s1]", item)),
        "observe_coarsening_then_feedback_differs_only_in_pi":
            differs_only_in_pi(pair("Observe[redact:S]", item)),
        "controller_then_feedback_differs_only_in_pi":
            differs_only_in_pi(pair("Controller[follow]", item)),
        "hide_and_restrict_do_not_commute_with_feedback":
            not pair("Hide[player]", item)["commute"] and not pair("Restrict[left]", item)["commute"],
        "payoff_without_training_commutes_with_feedback":
            pair("Payoff[right_cost=1]", item)["commute"] and pair("Payoff[right_cost=1]", score)["commute"]
            and pair("Payoff[right_cost=1]", item)["footprints_disjoint"],
        "payoff_with_training_does_not_commute_with_feedback":
            differs_only_in_pi(pair("Payoff[right_cost=1,trains]", score))
            and differs_only_in_pi(pair("Payoff[right_cost=1,trains]", item)),
        "repeat_commutes_with_feedback_at_design_time":
            pair("Repeat[2,controller]", item)["commute"] and pair("Repeat[2,controller]", item)["footprints_disjoint"],
        "item_and_score_feedback_do_not_commute": differs_only_in_pi(pair(item, score)),
        "sealed_feedback_commutes_with_item_feedback_despite_shared_generation":
            pair(sealed, item)["commute"] and not pair(sealed, item)["footprints_disjoint"],
        "typing_iff_ledger_respected_on_all_short_sequences": typing["equivalence_holds"],
        "ledger_raises_exactly_on_readout_of_selection_set": typing["malformed_iff_readout_of_selection_set"],
        "literal_sealed_role_premise_is_too_strict":
            not typing["strict_sealed_role"]["equivalence_holds"] and typing["strict_sealed_role"]["claim_holds"],
        "carry_second_generation_is_selection_over_2k_minus_1":
            all(cell["carry"]["matches_selection_over_2k_minus_1"] for cell in carry_cells.values()),
        "carry_generation_mean_exceeds_independent_blocks_by_one_sixteenth":
            carry["generation_mean_difference"] == Q(1, 16) and carry["carry"]["generation_mean"] == Q(13, 16)
            and carry["reset"]["generation_mean"] == Q(3, 4),
        "carry_scores_not_exchangeable_reset_scores_exchangeable":
            not carry["carry"]["exchangeable"] and carry["reset"]["exchangeable"]
            and carry["carry"]["prob_second_exceeds_first"] == Q(1, 8)
            and carry["carry"]["prob_first_exceeds_second"] == 0,
        "single_candidate_carry_has_no_gap":
            carry_cells["items=1,candidates=1,p=1/2"]["generation_mean_difference"] == 0,
        "rescore_of_readout_set_changes_rho_without_selection":
            rescored["rescore_of_readout_changes_rho_without_selection"]
            and rescored["rows"]["rescore_readout_set"]["rho"] == Q(-1, 2),
        "rho_change_does_not_identify_feedback_but_ledger_does":
            rescored["rescore_of_selection_matches_feedback_rho"] and rescored["ledger_separates_them"]
            and rescored["rows"]["feedback_item_level"]["rho"] == Q(1, 2),
    }
    return {"evidence_status": "exact_synthetic_fixtures_not_model_or_agent_evidence",
            "checks": checks, "all_passed": all(checks.values()),
            "footprints": footprints, "commutation": commutation, "typing_ledger": typing,
            "repeat_carry": carry_cells, "readout_gap_rescore": rescored}
