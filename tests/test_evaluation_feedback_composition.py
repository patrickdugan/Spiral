import json
from fractions import Fraction as Q
from itertools import accumulate, product
from math import comb

import pytest

from spiral_ln.evaluation_game_feedback import EvalSet, LoopEvent, audit_ledger
from spiral_ln.evaluation_feedback_composition import (
    CANDIDATES, FIELDS, LOCATIONS, Acquisition, Declaration, Game, Item, Judgment,
    Op, Policy, Record, Utility, Acquired, apply, apply_sequence, cap, commutation_alphabet,
    compile_ledger, controller, describe_policy, enumerate_states, feedback,
    first_witness, footprint_audit, footprints_disjoint, grant, hide, item_outcomes,
    judge, ledger_verdict, lookup_policy, make_record, observe, payoff, play, project,
    readout, readout_gap, readout_gap_rescore_fixture, repeat, repeat_carry_fixture,
    rescore, restrict, set_value, typecheck, typing_ledger_equivalence, verify,
)


@pytest.fixture(scope="module")
def report():
    return verify()


@pytest.fixture(scope="module")
def states():
    return enumerate_states()


# --- the executable record ---------------------------------------------------

def test_play_uses_observation_overrides_and_legal_fallback():
    s1 = Item("s1", "S", "right")
    assert play(Game(LOCATIONS, True), lookup_policy("follow"), s1).action == "right"
    assert play(Game(LOCATIONS, False), lookup_policy("follow"), s1).observation == "hidden"
    assert play(Game(LOCATIONS, False), lookup_policy("follow"), s1).action == "left"
    assert play(Game(("left",), True), lookup_policy("follow"), s1).action == "left"
    memorized = lookup_policy("always_left", (("s1", "right"),))
    assert play(Game(LOCATIONS, False), memorized, s1).action == "right"


def test_judgment_handles_redaction_flips_and_cost():
    assert judge(Judgment(), Acquired("s0", "S", "left", "left")) == 1
    assert judge(Judgment(), Acquired("s0", "S", "right", "left")) == 0
    assert judge(Judgment(), Acquired("s0", "S", None, "left")) is None
    assert judge(Judgment(("s0",)), Acquired("s0", "S", "left", "left")) == 0
    assert judge(Judgment((), Q(1)), Acquired("s1", "S", "right", "right")) == 0
    assert judge(Judgment((), Q(1)), Acquired("s0", "S", "right", "left")) == -1


def test_set_values_and_readout_gap():
    assert (set_value(make_record("always_left"), "S"), readout_gap(make_record("always_left"))) == (Q(1, 2), 0)
    assert set_value(make_record("follow"), "S") == set_value(make_record("follow"), "R") == 1
    assert set_value(make_record("follow", revealed=False), "S") == Q(1, 2)
    assert set_value(make_record(redacted=("S",)), "S") is None
    assert readout_gap(make_record(redacted=("S",))) is None
    assert item_outcomes(make_record(), "S") == (("s0", "left", Q(1)), ("s1", "left", Q(0)))
    with pytest.raises(ValueError, match="unknown set"):
        item_outcomes(make_record(), "X")


def test_item_level_feedback_patches_failed_items_only():
    patched = apply(feedback("S", "item_level"), make_record("always_left"))
    assert patched.pi.overrides == (("s1", "right"),) and patched.generation == 1
    untouched = apply(feedback("S", "item_level"), make_record("always_left", flipped=("s1",)))
    assert untouched.pi == lookup_policy("always_left")
    costed = apply(feedback("S", "item_level"), make_record("always_right", judgment_cost=Q(1)))
    assert costed.pi.overrides == (("s0", "left"), ("s1", "left"))


def test_score_only_feedback_takes_strict_improvements_and_keeps_incumbent_on_ties():
    improved = apply(feedback("S", "score_only", CANDIDATES), make_record("always_left"))
    assert improved.pi == lookup_policy("follow") and improved.generation == 1
    tied = apply(feedback("S", "score_only", CANDIDATES), make_record("always_left", revealed=False))
    assert tied.pi == lookup_policy("always_left")
    assert apply(feedback("S", "score_only"), make_record("always_left")).pi == lookup_policy("always_left")


def test_sealed_feedback_only_advances_generation():
    for set_id in ("S", "R"):
        after = apply(feedback(set_id, "sealed"), make_record("always_left"))
        assert after.pi == lookup_policy("always_left") and after.generation == 1


def test_feedback_learns_nothing_from_a_redacted_set():
    redacted = make_record("always_left", redacted=("S",))
    for access in ("item_level", "score_only"):
        after = apply(feedback("S", access, CANDIDATES), redacted)
        assert after.pi == redacted.pi and after.generation == 1


@pytest.mark.parametrize("op, record, message", [
    (feedback("X", "item_level"), make_record(), "undeclared"),
    (feedback("R", "item_level"), make_record(), "readout set"),
    (feedback("R", "score_only", CANDIDATES), make_record(), "readout set"),
    (feedback("S", "item_level"), make_record(selection_access="score_only"), "exceeds the declared access"),
    (feedback("S", "score_only"), make_record(selection_access="sealed"), "exceeds the declared access"),
    (readout("X"), make_record(), "undeclared"),
    (restrict(("right",)), make_record(legal=("left",)), "no legal action"),
])
def test_ill_typed_applications_raise(op, record, message):
    with pytest.raises(ValueError, match=message):
        apply(op, record)


@pytest.mark.parametrize("build", [
    lambda: Game((), True), lambda: Game(("right", "left"), True), lambda: Game(("up",), True),
    lambda: Game(LOCATIONS, 1), lambda: Game(LOCATIONS, True, budget=-1),
    lambda: Game(LOCATIONS, True, horizon=0), lambda: Game(LOCATIONS, True, carry="x"),
    lambda: Game(LOCATIONS, True, utility=Q(1)), lambda: Utility(Q(-1)), lambda: Utility(0.5),
    lambda: Policy((("left", "left"),)), lambda: Policy(lookup_policy("follow").default, (("b", "left"), ("a", "left"))),
    lambda: Policy(lookup_policy("follow").default, (("a", "up"),)), lambda: lookup_policy("x"),
    lambda: Item("", "S", "left"), lambda: Item("s0", "S", "up"),
    lambda: Judgment(("b", "a")), lambda: Judgment((), Q(-1)), lambda: Acquisition(("S", "S")),
    lambda: make_record(generation=-1),
    lambda: Record(Game(LOCATIONS, True), lookup_policy("follow"), (Item("s0", "S", "left"), Item("s0", "S", "left")),
                   Acquisition(), Judgment(), 0, (Declaration("S", "selection", "sealed"),)),
    lambda: Record(Game(LOCATIONS, True), lookup_policy("follow"), (Item("s0", "S", "left"),),
                   Acquisition(), Judgment(), 0, (Declaration("S", "readout", "item_level"),)),
    lambda: Record(Game(LOCATIONS, True), lookup_policy("follow"), (Item("s0", "S", "left"),),
                   Acquisition(), Judgment(), 0, (Declaration("S", "selection", "sealed"), Declaration("R", "readout", "sealed"))),
    lambda: Record(Game(LOCATIONS, True), lookup_policy("follow"), (Item("s0", "S", "left"), Item("r0", "R", "left")),
                   Acquisition(), Judgment(), 0, (Declaration("S", "selection", "sealed"),)),
    lambda: Record(Game(LOCATIONS, True), lookup_policy("follow"), (Item("s0", "S", "left"),),
                   Acquisition(), Judgment(), 0, (Declaration("S", "selection", "sealed"), Declaration("S", "selection", "sealed"))),
    lambda: Record(Game(LOCATIONS, True), lookup_policy("follow"), (Item("s0", "S", "left"),),
                   Acquisition(), Judgment(), 0, (Declaration("S", "owner", "sealed"),)),
])
def test_malformed_records_raise(build):
    with pytest.raises(ValueError):
        build()


@pytest.mark.parametrize("build", [
    lambda: restrict(()), lambda: restrict(("up",)), lambda: grant(-1), lambda: cap(1.5),
    lambda: controller("follow", "x"), lambda: rescore(None, "x"), lambda: payoff(Utility(), "yes"),
    lambda: repeat(0, "reset"), lambda: repeat(1, "x"), lambda: feedback("", "sealed"),
    lambda: feedback("S", "public"), lambda: feedback("S", "item_level", ("x",)), lambda: readout(""),
    lambda: Op("bogus", (), "n", frozenset(), frozenset()),
    lambda: Op("hide", (), "n", frozenset({"nope"}), frozenset()),
])
def test_malformed_operators_raise(build):
    with pytest.raises(ValueError):
        build()


def test_apply_and_project_reject_bad_arguments():
    with pytest.raises(ValueError):
        apply("hide", make_record())
    with pytest.raises(ValueError):
        apply(hide(), "record")
    with pytest.raises(ValueError, match="unknown field"):
        project(make_record(), "claim")


# --- footprints and commutation ----------------------------------------------

def test_footprints_are_sound_on_the_state_space(report, states):
    assert all(f["write_sound"] and f["read_sound"] for f in report["footprints"].values())
    assert len(states) == 384 and len(report["footprints"]) == 13
    for state in states:
        hidden = apply(hide(), state)
        assert [f for f in FIELDS if project(hidden, f) != project(state, f)] in ([], ["game.revealed"])


def test_read_soundness_catches_an_undeclared_read(states):
    """A Grant that claims to read nothing is read-unsound: its output depends on the budget."""

    bogus = Op("grant", (2,), "Grant[2]", frozenset(), frozenset({"game.budget"}))
    assert not footprint_audit((bogus,), states)["Grant[2]"]["read_sound"]
    leaky = Op("hide", (), "Hide", frozenset(), frozenset({"game.budget"}))
    assert not footprint_audit((leaky,), states)["Hide"]["write_sound"]


def test_disjoint_predicate_examples():
    item = feedback("S", "item_level")
    assert footprints_disjoint(grant(2), hide())
    assert footprints_disjoint(payoff(Utility(Q(1)), False), item)
    assert footprints_disjoint(repeat(2, "controller"), item)
    assert not footprints_disjoint(grant(2), cap(5))
    assert not footprints_disjoint(payoff(Utility(Q(1)), True), item)
    assert not footprints_disjoint(feedback("S", "sealed"), item)
    assert not footprints_disjoint(hide(), item)


def test_every_disjoint_pair_commutes(report):
    assert report["commutation"]["disjoint_update_law_holds"]
    assert report["commutation"]["states"] == 384
    assert all(p["commute"] for p in report["commutation"]["pairs"] if p["a"] == p["b"])


EXPECTED_NONCOMMUTING = {
    ("Restrict[left]", "Feedback[S,item_level]"), ("Restrict[left]", "Feedback[S,score_only]"),
    ("Grant[2]", "Cap[5]"),
    ("Hide[player]", "Feedback[S,item_level]"), ("Hide[player]", "Feedback[S,score_only]"),
    ("Observe[redact:S]", "Feedback[S,item_level]"), ("Observe[redact:S]", "Feedback[S,score_only]"),
    ("Controller[follow]", "Feedback[S,item_level]"), ("Controller[follow]", "Feedback[S,score_only]"),
    ("Rescore[flip_s1]", "Payoff[right_cost=1,trains]"),
    ("Rescore[flip_s1]", "Feedback[S,item_level]"), ("Rescore[flip_s1]", "Feedback[S,score_only]"),
    ("Payoff[right_cost=1,trains]", "Feedback[S,item_level]"), ("Payoff[right_cost=1,trains]", "Feedback[S,score_only]"),
    ("Feedback[S,item_level]", "Feedback[S,score_only]"),
}
EXPECTED_COMMUTE_DESPITE_OVERLAP = {
    ("Payoff[right_cost=1]", "Payoff[right_cost=1,trains]"),
    ("Feedback[S,item_level]", "Feedback[S,sealed]"), ("Feedback[S,score_only]", "Feedback[S,sealed]"),
}


def test_commutation_table_matches_expected(report):
    commutation = report["commutation"]
    assert set(map(tuple, commutation["noncommuting"])) == EXPECTED_NONCOMMUTING
    assert set(map(tuple, commutation["commute_despite_overlap"])) == EXPECTED_COMMUTE_DESPITE_OVERLAP
    assert len(commutation["pairs"]) == 13 * 14 // 2
    for pair in commutation["pairs"]:
        if not pair["commute"]:
            assert not pair["footprints_disjoint"] and pair["witness"]["differs_in"]


def test_witnesses_reproduce_in_both_orders(report, states):
    ops = {op.name: op for op in commutation_alphabet()}
    for pair in report["commutation"]["pairs"]:
        if pair["commute"]:
            continue
        a, b = ops[pair["a"]], ops[pair["b"]]
        state = first_witness(a, b, states)
        assert state is not None
        ab, ba = apply(b, apply(a, state)), apply(a, apply(b, state))
        assert [f for f in FIELDS if project(ab, f) != project(ba, f)] == pair["witness"]["differs_in"]
        assert first_witness(b, a, states) == state


def test_required_witnesses_pin_exact_values(report):
    table = {frozenset((p["a"], p["b"])): p["witness"] for p in report["commutation"]["pairs"]}
    item, score = "Feedback[S,item_level]", "Feedback[S,score_only]"
    budget = table[frozenset(("Grant[2]", "Cap[5]"))]
    assert budget["state"]["game.budget"] == 4 and budget["a_then_b"] == {"game.budget": 5}
    assert budget["b_then_a"] == {"game.budget": 6}
    rescored = table[frozenset(("Rescore[flip_s1]", item))]
    assert rescored["a_then_b"] == {"pi": "always_left"} and rescored["b_then_a"] == {"pi": "always_left+s1->right"}
    observed = table[frozenset(("Observe[redact:S]", item))]
    assert observed["a_then_b"] == {"pi": "always_left"} and observed["b_then_a"] == {"pi": "always_left+s1->right"}
    controlled = table[frozenset(("Controller[follow]", item))]
    assert controlled["a_then_b"] == {"pi": "follow+s1->left"} and controlled["b_then_a"] == {"pi": "follow"}
    trained = table[frozenset(("Payoff[right_cost=1,trains]", score))]
    assert trained["a_then_b"] == {"pi": "always_left"} and trained["b_then_a"] == {"pi": "follow"}
    hidden = table[frozenset(("Hide[player]", item))]
    assert hidden["a_then_b"] == {"pi": "follow+s1->right"} and hidden["b_then_a"] == {"pi": "follow"}
    assert table[frozenset(("Payoff[right_cost=1]", item))] is None
    assert table[frozenset(("Repeat[2,controller]", item))] is None


def test_rescore_before_feedback_changes_learning_after_changes_only_readout():
    base, flip, learn = make_record("always_left"), rescore(Judgment(("s1",)), "flip_s1"), feedback("S", "item_level")
    rescored_first, fed_first = apply_sequence((flip, learn), base), apply_sequence((learn, flip), base)
    assert rescored_first.judgment == fed_first.judgment == Judgment(("s1",))
    assert rescored_first.pi == base.pi and fed_first.pi.overrides == (("s1", "right"),)
    assert set_value(rescored_first, "S") == 1 and set_value(fed_first, "S") == Q(1, 2)
    assert apply_sequence((learn, flip), base) != apply_sequence((flip, learn), base)


def test_commutation_does_not_depend_on_pair_order(states):
    ops = commutation_alphabet()
    for a, b in product(ops[:4], ops[-3:]):
        assert (first_witness(a, b, states) is None) == (first_witness(b, a, states) is None)


# --- typing as ledger audit --------------------------------------------------

def _items():
    return make_record().items


def _declarations(access="item_level"):
    return make_record(selection_access=access).declarations


def test_compile_ledger_emits_one_event_per_crossing():
    sequence = (readout("R"), feedback("S", "item_level"), feedback("S", "score_only", CANDIDATES),
                rescore(Judgment(("s1",)), "flip_s1"), feedback("S", "sealed"), readout("R"))
    sets, events = compile_ledger(sequence, _declarations(), _items())
    assert sets == (EvalSet("S", "selection", "item_level", ("s0", "s1")),
                    EvalSet("R", "readout", "sealed", ("r0", "r1")))
    assert events == (LoopEvent(0, "R", "readout"), LoopEvent(0, "S", "item_feedback", ("s0", "s1")),
                      LoopEvent(1, "S", "score_query"), LoopEvent(1, "S", "score_query"),
                      LoopEvent(1, "S", "score_query"), LoopEvent(1, "S", "score_query"),
                      LoopEvent(3, "R", "readout"))
    assert audit_ledger(sets, events, 2, Q(1))["declarations_respected"]


def test_compile_ledger_rejects_bad_input():
    with pytest.raises(ValueError, match="undeclared"):
        compile_ledger((feedback("X", "sealed"),), _declarations(), _items())
    with pytest.raises(ValueError, match="undeclared"):
        compile_ledger((readout("X"),), _declarations(), _items())
    with pytest.raises(ValueError, match="operators"):
        compile_ledger(("readout",), _declarations(), _items())


@pytest.mark.parametrize("sequence, access, expected", [
    ((), "item_level", ()),
    ((feedback("R", "item_level"),), "item_level", ("F-SEL role",)),
    ((feedback("R", "score_only"),), "item_level", ("F-SEL role",)),
    ((feedback("S", "item_level"),), "score_only", ("F-SEL access",)),
    ((feedback("S", "score_only"),), "sealed", ("F-SEL access",)),
    ((feedback("S", "item_level"), feedback("S", "item_level")), "item_level", ()),
    ((feedback("S", "item_level"),) * 3, "item_level", ("F-SEL retired",)),
    ((feedback("S", "item_level"), feedback("S", "item_level"), feedback("S", "score_only")), "item_level", ("F-SEL retired",)),
    ((readout("S"),), "item_level", ("RO role",)),
    ((readout("R"),) * 2, "item_level", ()),
    ((readout("R"),) * 3, "item_level", ("RO budget",)),
    ((feedback("R", "sealed"), rescore(Judgment(("s1",)), "flip_s1")), "item_level", ()),
])
def test_typing_rules_fire_individually(sequence, access, expected):
    result = typecheck(sequence, _declarations(access), _items(), 2, Q(1))
    assert result["well_typed"] == (not expected)
    assert tuple(v.split(": ")[-1] for v in result["violations"]) == expected


def test_strict_sealed_reading_and_malformed_typecheck_arguments():
    sequence = (feedback("R", "sealed"),)
    assert typecheck(sequence, _declarations(), _items(), 2, Q(1))["well_typed"]
    strict = typecheck(sequence, _declarations(), _items(), 2, Q(1), sealed_requires_selection=True)
    assert not strict["well_typed"] and "F-SEALED" in strict["violations"][0]
    for budget, bound in ((0, Q(1)), (2, Q(0)), (2, 0.5), (2.0, Q(1))):
        with pytest.raises(ValueError):
            typecheck(sequence, _declarations(), _items(), budget, bound)
    with pytest.raises(ValueError, match="operators"):
        typecheck(("x",), _declarations(), _items(), 2, Q(1))


def test_ledger_verdicts_cover_three_outcomes():
    assert ledger_verdict((readout("S"),), _declarations(), _items(), 2, Q(1)) == "malformed"
    assert ledger_verdict((feedback("R", "item_level"),), _declarations(), _items(), 2, Q(1)) == "breached"
    assert ledger_verdict((feedback("S", "item_level"),), _declarations(), _items(), 2, Q(1)) == "respected"


def test_typing_matches_ledger_on_all_short_sequences(report):
    typing = report["typing_ledger"]
    assert typing["equivalence_holds"] and typing["mismatches"] == []
    assert typing["sequence_count"] == 3 * (1 + 9 + 81 + 729 + 6561) == 22143
    counts = typing["verdict_counts"]
    assert sum(counts.values()) == typing["sequence_count"]
    assert counts["malformed"] == 3 * (7381 - 4681) == 8100
    assert typing["malformed_iff_readout_of_selection_set"]


def test_strict_sealed_reading_fails_only_on_sealed_feedback_from_the_readout_set(report):
    strict = report["typing_ledger"]["strict_sealed_role"]
    assert not strict["equivalence_holds"] and strict["claim_holds"] and strict["mismatch_count"] == 1414
    assert strict["example"]["sequence"] == ["Feedback[R,sealed]"] and strict["example"]["verdict"] == "respected"


def test_typing_ledger_equivalence_short_run_and_bad_length():
    short = typing_ledger_equivalence(max_length=1)
    assert short["sequence_count"] == 30 and short["equivalence_holds"]
    with pytest.raises(ValueError):
        typing_ledger_equivalence(max_length=-1)


# --- Repeat with a carry map -------------------------------------------------

def _max_distribution(items, count, p):
    if count == 0:
        return {0: Q(1)}
    pmf = [Q(comb(items, j)) * p**j * (1 - p)**(items - j) for j in range(items + 1)]
    cdf = list(accumulate(pmf))
    return {j: cdf[j]**count - (cdf[j - 1]**count if j else Q(0)) for j in range(items + 1)}


@pytest.mark.parametrize("items, candidates, p", [
    (1, 2, Q(1, 2)), (2, 2, Q(1, 2)), (2, 3, Q(1, 3)), (3, 2, Q(1, 4)), (1, 3, Q(2, 3)), (2, 1, Q(1, 2)),
])
def test_repeat_carry_matches_independent_binomial_computation(items, candidates, p):
    fixture = repeat_carry_fixture(items, candidates, p)
    first, fresh = _max_distribution(items, candidates, p), _max_distribution(items, candidates - 1, p)
    doubled = _max_distribution(items, 2 * candidates - 1, p)
    expected_first = sum(Q(j, items) * m for j, m in first.items())
    expected_second = sum(Q(j, items) * m for j, m in doubled.items())
    exceeds = sum(first[a] * sum(m for b, m in fresh.items() if b > a) for a in first)
    assert fixture["carry"]["expected_generation_1"] == expected_first
    assert fixture["carry"]["expected_generation_2"] == expected_second
    assert fixture["carry"]["prob_second_exceeds_first"] == exceeds
    assert fixture["carry"]["prob_first_exceeds_second"] == 0
    assert fixture["reset"]["expected_generation_2"] == expected_first and fixture["reset"]["exchangeable"]
    assert fixture["reset"]["prob_second_exceeds_first"] == fixture["reset"]["prob_first_exceeds_second"]
    assert fixture["carry"]["exchangeable"] == (candidates == 1)
    lower_bound = (1 - p)**(items * candidates) * (1 - (1 - p)**(items * (candidates - 1)))
    assert fixture["carry"]["prob_second_exceeds_first"] >= lower_bound
    assert (fixture["generation_mean_difference"] > 0) == (candidates > 1)


def test_repeat_carry_exact_two_generation_values():
    fixture = repeat_carry_fixture(1, 2, Q(1, 2))
    assert fixture["carry"]["expected_generation_1"] == Q(3, 4)
    assert fixture["carry"]["expected_generation_2"] == Q(7, 8)
    assert fixture["carry"]["generation_mean"] == Q(13, 16) and fixture["reset"]["generation_mean"] == Q(3, 4)
    assert fixture["generation_mean_difference"] == Q(1, 16)
    assert fixture["carry"]["prob_second_exceeds_first"] == Q(1, 8)
    assert fixture["expected_apparent_gain_under_carry"] == Q(1, 8) and fixture["true_value_change"] == 0
    assert fixture["carry"]["rho_generation_1"] == Q(1, 4) and fixture["carry"]["rho_generation_2"] == Q(3, 8)
    assert fixture["one_generation_gap"] == Q(1, 4) and fixture["readout_value"] == Q(1, 2)


@pytest.mark.parametrize("args", [(0, 2, Q(1, 2)), (1, 0, Q(1, 2)), (1, 2, Q(3, 2)), (1, 2, 0.5), (1.0, 2, Q(1, 2))])
def test_repeat_carry_rejects_malformed_inputs(args):
    with pytest.raises(ValueError):
        repeat_carry_fixture(*args)


# --- readout gap under Rescore ----------------------------------------------

def test_readout_gap_rescore_fixture_values():
    fixture = readout_gap_rescore_fixture()
    rows = fixture["rows"]
    assert (rows["base"]["V_s"], rows["base"]["V_r"], rows["base"]["rho"]) == (Q(1, 2), Q(1, 2), 0)
    assert rows["rescore_readout_set"]["rho"] == Q(-1, 2) and not rows["rescore_readout_set"]["pi_changed"]
    assert rows["rescore_selection_set"]["rho"] == rows["feedback_item_level"]["rho"] == Q(1, 2)
    assert rows["rescore_selection_set"]["generation"] == 0 and rows["feedback_item_level"]["generation"] == 1
    assert rows["rescore_selection_set"]["ledger_patches_on_S"] == 0
    assert rows["feedback_item_level"]["ledger_patches_on_S"] == 2
    assert all(row["ledger_declarations_respected"] for row in rows.values())
    assert fixture["rescore_of_readout_changes_rho_without_selection"]
    assert fixture["rescore_of_selection_matches_feedback_rho"] and fixture["ledger_separates_them"]


# --- verify ------------------------------------------------------------------

def test_verify_reports_every_check_passing(report):
    assert report["all_passed"] and len(report["checks"]) == 22
    assert report["evidence_status"].startswith("exact_synthetic")


def test_verify_output_is_json_encodable(report):
    def encode(value):
        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            return str(value)
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        raise TypeError(type(value))
    text = json.dumps(report, default=encode)
    assert '"13/16"' in text and describe_policy(lookup_policy("follow", (("s1", "left"),))) == "follow+s1->left"
