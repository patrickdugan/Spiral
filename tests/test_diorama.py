from spiral_ln import diorama
from spiral_ln.diorama import (
    DioramaCharacter,
    bias_cards,
    day_phase,
    from_custody_persona,
    from_swarm_profile,
    pressure_series,
)
from spiral_ln.feral_custody import CustodyPersona
from spiral_ln.swarm_compromise import PROFILE_ARCHETYPES, TRAITS


def _profile(name="status_seeker"):
    return next(p for p in PROFILE_ARCHETYPES if p.name == name)


def test_character_is_deterministic():
    a = from_swarm_profile(_profile(), "N01", "operations", "desk-1", seed=3)
    b = from_swarm_profile(_profile(), "N01", "operations", "desk-1", seed=3)
    assert a == b
    assert a.display_name and a.employer and a.bio


def test_attacker_view_never_leaks_truth_class():
    char = from_swarm_profile(_profile("principled_auditor"), "N02", "ops", "s", seed=1)
    full = char.to_dict()
    attacker = char.attacker_view()
    assert full["truth_class"] == "insider_benign_confound"
    assert "truth_class" not in attacker
    # the hidden label must not hide anywhere in the attacker projection
    assert "insider_benign_confound" not in str(attacker)


def test_bias_cards_cover_all_traits_and_mark_the_shield():
    cards = bias_cards({t: 0.5 for t in TRAITS})
    assert {c["trait"] for c in cards} == set(TRAITS)
    shield = [c for c in cards if c["protective"]]
    assert [c["trait"] for c in shield] == ["security_hygiene"]
    # exploit vectors are derived from the sim, so authority_deference maps to phishing
    auth = next(c for c in cards if c["trait"] == "authority_deference")
    assert "spear_social" in auth["vectors"]
    iso = next(c for c in cards if c["trait"] == "isolation")
    assert "cult_recruitment" in iso["vectors"]


def test_day_phase_partitions_the_cycle():
    phases = {day_phase(i, 48)["phase"] for i in range(48)}
    assert phases <= {"night", "commute", "work", "break", "home"}
    assert "night" in phases and "work" in phases
    assert day_phase(0, 48)["time_of_day"] == 0.0
    assert 0.0 <= day_phase(10, 48)["time_of_day"] < 1.0


def test_pressure_series_is_bounded_rises_and_pins_at_flip():
    series = pressure_series(10, attempt_frames=[2, 3], flip_frame=5)
    assert len(series) == 10
    assert all(0.0 <= v <= 1.0 for v in series)
    assert series[3] > series[0]  # rose under pressure
    assert series[5] == 1.0 and series[9] == 1.0  # pinned from the flip
    # no flip, no attempts -> stays at zero
    assert pressure_series(5, [], None) == [0.0, 0.0, 0.0, 0.0, 0.0]


def test_custody_character_grafts_traits_and_carries_economics():
    persona = CustodyPersona("sh0", "shard_holder", 15_000, 0.6, 0.02, 800, 0.7, 0.95)
    char = from_custody_persona(persona, "shard_holders", "shard_holder-0", seed=0)
    assert set(char.traits) == set(TRAITS)  # grafted swarm trait vocabulary
    assert char.economics["price_to_defect"] == 15_000
    assert char.role == "shard_holder"
    assert "truth_class" not in char.attacker_view()


def test_safety_boundary_is_sealed():
    b = DioramaCharacter.safety_boundary()
    assert b["synthetic_only"] is True
    assert b["real_person_data"] is False
    assert b["persuasion_or_recruitment_content"] is False
    assert b["truth_class_hidden_from_attacker"] is True
