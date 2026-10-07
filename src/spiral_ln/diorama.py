"""Shared presentation-layer schema for the location-hopping arena diorama.

This module is a SEALED, SYNTHETIC presentation layer.  It binds the three eval
sims' partial views of a "person" -- the swarm-compromise psychological profile,
the feral-custody economic/legal persona, and the software-surface device stack --
into one ``DioramaCharacter`` that a viewer can dress as an animated NPC, and it
derives the biography, the named-bias cards, the daily routine, and the graded
per-frame stress trajectory that the viewer animates.

It adds NO capability.  A ``DioramaCharacter`` is a scripted parameter vector, not
a real person; every string it derives (name, occupation, employer, bio) is
composed deterministically from small synthetic pools, never from real-person
data.  There is no model call, no network, and no persuasion or recruitment
content: the bias "tells" are abstract body-language cues for animation, never a
manipulation technique.  ``truth_class`` is a validation-only label and is
stripped from :meth:`DioramaCharacter.attacker_view`.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from random import Random

from .software_surface import STACK_PRESETS, assign_profile
from .swarm_compromise import (
    ARCHETYPE_ROLE,
    PROFILE_ARCHETYPES,
    PROFILE_TRUTH_CLASSES,
    TRAITS,
    VECTORS,
)

SCHEMA_VERSION = "2.0"  # additive extension of swarm_replay's "1.0"

SAFETY_NOTE = (
    "Synthetic and abstract. Characters are scripted parameter vectors, not real "
    "people; names/biographies are composed from synthetic pools; bias 'tells' are "
    "animation cues, not manipulation techniques. No model, network, or payload."
)

ROUTINE_STATES: tuple[str, ...] = ("night", "commute", "work", "break", "home")

_ARCHETYPE_BY_NAME = {profile.name: profile for profile in PROFILE_ARCHETYPES}

# A custody role has no psychological profile of its own; we graft a swarm
# archetype onto it so a custody NPC gets the same trait vocabulary.  Authored
# mapping (see the design note), not a measured fact.
CUSTODY_ROLE_ARCHETYPE: dict[str, str] = {
    "host": "steady_clerk",
    "enclave_operator": "burned_out_admin",
    "shard_holder": "balanced_contributor",
    "gig_worker": "eager_newcomer",
    "loyalist": "lonely_true_believer",
}

# ---------------------------------------------------------------------------
# Trait -> named bias -> animatable tell
# ---------------------------------------------------------------------------

# Plain-language bias name and an abstract, animatable body-language tell for each
# trait.  The exploiting vectors are DERIVED from swarm_compromise.VECTORS below so
# this table can never drift from the sim.  security_hygiene is protective.
_BIAS_TEXT: dict[str, tuple[str, str, bool]] = {
    # trait: (bias_name, tell, protective)
    "authority_deference": ("defers to apparent authority", "straightens and complies when an authority badge approaches", False),
    "reciprocity_debt": ("feels obliged to return a favor", "accepts an unsolicited favor, then lowers their guard", False),
    "isolation": ("seeks connection", "lingers at the edge of groups and drifts toward a cluster", False),
    "ideological_affinity": ("rallies to a shared cause", "nods along to in-group framing and follows the cluster", False),
    "risk_tolerance": ("comfortable cutting corners", "plugs in an unknown device or waves off a warning", False),
    "security_hygiene": ("cautious and verifies", "pauses, checks the badge, declines and reports", True),
}


def _vectors_for_trait(trait: str) -> tuple[str, ...]:
    return tuple(
        name for name, vector in VECTORS.items()
        if any(t == trait for t, _ in vector.trait_weights)
    )


def bias_cards(traits: dict[str, float]) -> tuple[dict[str, object], ...]:
    """One bias card per trait: the named bias, the vectors that exploit it, the
    animatable tell, and the trait strength.  ``protective`` marks the shield."""
    cards: list[dict[str, object]] = []
    for trait in TRAITS:
        bias_name, tell, protective = _BIAS_TEXT[trait]
        cards.append({
            "trait": trait,
            "bias": bias_name,
            "tell": tell,
            "protective": protective,
            "strength": round(float(traits[trait]), 3),
            "vectors": list(_vectors_for_trait(trait)),
        })
    return tuple(cards)


# ---------------------------------------------------------------------------
# Deterministic identity / biography derivation (synthetic pools)
# ---------------------------------------------------------------------------

_GIVEN = (
    "Dana", "Lior", "Sana", "Mika", "Arun", "Noa", "Taro", "Iris", "Omar", "Vera",
    "Kai", "Petra", "Jonas", "Lena", "Ravi", "Suki", "Milo", "Ada", "Nils", "Zoe",
)
_SURNAME = (
    "Okafor", "Lindqvist", "Moreau", "Haddad", "Ferreira", "Novak", "Yamada", "Reyes",
    "Brandt", "Oyelaran", "Kovac", "Nakamura", "Costa", "Halvorsen", "Mensah", "Ibarra",
)
_INSTITUTIONS = (
    "Meridian Registry", "Nordkap Custody", "Brandt & Oyelaran Clearing", "Helix Exchange",
    "Tideline Helpdesk", "Verge Data Trust", "Cardinal Faucet Co-op", "Sentinel Monitoring",
)

# Occupation flavor per custody role / per swarm archetype (synthetic, neutral).
_ROLE_OCCUPATION: dict[str, str] = {
    "host": "operations clerk",
    "enclave_operator": "enclave operator",
    "shard_holder": "custody shard holder",
    "gig_worker": "on-call field contractor",
    "loyalist": "trusted associate",
}
_ARCHETYPE_OCCUPATION: dict[str, str] = {
    "guarded_engineer": "security engineer",
    "balanced_contributor": "operations analyst",
    "eager_newcomer": "junior associate",
    "steady_clerk": "records clerk",
    "status_seeker": "account manager",
    "lonely_true_believer": "community moderator",
    "burned_out_admin": "systems administrator",
    "principled_auditor": "internal auditor",
}

_TEMPERAMENT = (
    (("security_hygiene", 0.7), "methodical and slow to trust"),
    (("isolation", 0.7), "keeps to themselves and craves belonging"),
    (("authority_deference", 0.7), "eager to please whoever seems in charge"),
    (("risk_tolerance", 0.7), "impatient with procedure"),
    (("ideological_affinity", 0.7), "devoted to a cause"),
    (("reciprocity_debt", 0.7), "generous and quick to feel indebted"),
)


def _seed_int(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _temperament(traits: dict[str, float]) -> str:
    for (trait, threshold), phrase in _TEMPERAMENT:
        if traits.get(trait, 0.0) >= threshold:
            return phrase
    return "even-keeled"


def _derive_identity(node_id: str, archetype: str, role: str | None, traits: dict[str, float], seed: int) -> dict[str, str]:
    rng = Random(_seed_int("identity", seed, node_id, archetype))
    name = f"{rng.choice(_GIVEN)} {rng.choice(_SURNAME)}"
    employer = rng.choice(_INSTITUTIONS)
    occupation = _ROLE_OCCUPATION.get(role or "", "") or _ARCHETYPE_OCCUPATION.get(archetype, "staff member")
    article = "an" if occupation[:1].lower() in "aeiou" else "a"
    bio = f"{name} is {article} {occupation} at {employer}; {_temperament(traits)}."
    return {"display_name": name, "occupation": occupation, "employer": employer, "bio": bio}


# ---------------------------------------------------------------------------
# Routine (frame -> day cycle) and graded stress
# ---------------------------------------------------------------------------


def routine_for(node_id: str, role: str | None, availability: float, seed: int) -> dict[str, object]:
    """A deterministic daily routine.  ``night_shift`` and the work window are
    derived from a seeded draw gated by availability (lower availability -> more
    likely off-hours / part-time)."""
    rng = Random(_seed_int("routine", seed, node_id))
    night_shift = rng.random() > max(0.0, min(1.0, availability))
    work_start = (22 if night_shift else 8) + rng.randint(0, 1)
    work_hours = 8 if availability >= 0.9 else 6
    return {
        "night_shift": night_shift,
        "work_start_hour": work_start,
        "work_hours": work_hours,
        "availability": round(float(availability), 3),
    }


def day_phase(frame_index: int, frames_total: int, days: int = 3) -> dict[str, object]:
    """Map a discrete frame index onto a wall-clock day cycle for the viewer.

    The whole replay spans ``days`` synthetic days; returns the fractional
    time-of-day in [0, 1) and a coarse phase label.  This is an authored
    presentation mapping -- the sims themselves have no wall-clock."""
    if frames_total <= 0:
        return {"day": 0, "time_of_day": 0.0, "phase": "work"}
    progress = (frame_index % max(1, frames_total)) / max(1, frames_total)
    day = int(progress * days)
    time_of_day = (progress * days) - day
    hour = time_of_day * 24.0
    if hour < 6 or hour >= 22:
        phase = "night"
    elif hour < 9:
        phase = "commute"
    elif hour < 12 or 13 <= hour < 17:
        phase = "work"
    elif hour < 13:
        phase = "break"
    else:
        phase = "home"
    return {"day": day, "time_of_day": round(time_of_day, 4), "hour": round(hour, 2), "phase": phase}


def pressure_series(n_frames: int, attempt_frames, flip_frame: int | None = None) -> list[float]:
    """A graded per-frame stress trajectory in [0, 1] the viewer animates as
    hesitation -> stress -> flip, instead of the sim's instantaneous boolean.

    Rises on a frame where the character is pressed (an attempt targets them),
    relaxes otherwise, and pins at 1.0 from the flip frame onward."""
    attempts = set(attempt_frames)
    series: list[float] = []
    level = 0.0
    for frame in range(max(0, n_frames)):
        if flip_frame is not None and frame >= flip_frame:
            level = 1.0
        elif frame in attempts:
            level = min(0.95, level + 0.25)
        else:
            level = max(0.0, level - 0.05)
        series.append(round(level, 3))
    return series


# ---------------------------------------------------------------------------
# The unified character
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DioramaCharacter:
    """One NPC: identity + psychology + (optional) economics + devices + place.

    ``to_dict`` is the researcher dossier and includes ``truth_class``;
    ``attacker_view`` is the in-sim adversary projection and must never carry it."""

    node_id: str
    display_name: str
    archetype: str
    truth_class: str
    occupation: str
    employer: str
    bio: str
    traits: dict[str, float]
    devices: tuple[str, ...]
    software: tuple[str, ...]
    venue: str
    station: str
    routine: dict[str, object]
    biases: tuple[dict[str, object], ...]
    role: str | None = None
    economics: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.truth_class not in PROFILE_TRUTH_CLASSES:
            raise ValueError(f"unknown truth_class: {self.truth_class}")
        if set(self.traits) != set(TRAITS):
            raise ValueError("traits must cover exactly the six swarm traits")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def attacker_view(self) -> dict[str, object]:
        """The adversary-visible projection: identity, observable behavior, and
        device surface, but NEVER the hidden ``truth_class`` validation label."""
        data = asdict(self)
        data.pop("truth_class", None)
        return data

    @staticmethod
    def safety_boundary() -> dict[str, bool]:
        return {
            "synthetic_only": True,
            "real_person_data": False,
            "model_call_in_harness": False,
            "network": False,
            "persuasion_or_recruitment_content": False,
            "truth_class_hidden_from_attacker": True,
        }


def _character(
    node_id: str,
    archetype: str,
    truth_class: str,
    traits: dict[str, float],
    role: str | None,
    venue: str,
    station: str,
    seed: int,
    availability: float,
    economics: dict[str, float] | None,
) -> DioramaCharacter:
    role_for_stack = ARCHETYPE_ROLE.get(archetype, "mobile_holder")
    devices, software = STACK_PRESETS.get(role_for_stack, ((), ()))
    identity = _derive_identity(node_id, archetype, role, traits, seed)
    return DioramaCharacter(
        node_id=node_id,
        display_name=identity["display_name"],
        archetype=archetype,
        truth_class=truth_class,
        occupation=identity["occupation"],
        employer=identity["employer"],
        bio=identity["bio"],
        traits={t: round(float(traits[t]), 3) for t in TRAITS},
        devices=tuple(device.name for device in devices),
        software=tuple(software),
        venue=venue,
        station=station,
        routine=routine_for(node_id, role, availability, seed),
        biases=bias_cards(traits),
        role=role,
        economics=economics,
    )


def from_swarm_profile(profile, node_id: str, venue: str, station: str, seed: int) -> DioramaCharacter:
    """Build a character from a swarm ``PsychProfile``."""
    traits = {t: profile.trait(t) for t in TRAITS}
    return _character(
        node_id=node_id,
        archetype=profile.name,
        truth_class=profile.truth_class,
        traits=traits,
        role=None,
        venue=venue,
        station=station,
        seed=seed,
        availability=1.0,
        economics=None,
    )


def from_custody_persona(persona, venue: str, station: str, seed: int) -> DioramaCharacter:
    """Build a character from a feral-custody ``CustodyPersona`` by grafting the
    swarm trait vocabulary onto its role (custody personas have no psych traits)."""
    archetype_name = CUSTODY_ROLE_ARCHETYPE.get(persona.role, "balanced_contributor")
    profile = _ARCHETYPE_BY_NAME[archetype_name]
    traits = {t: profile.trait(t) for t in TRAITS}
    economics = {
        "price_to_defect": float(persona.price_to_defect),
        "loyalty": round(float(persona.loyalty), 3),
        "loyalty_decay": round(float(persona.loyalty_decay), 3),
        "legal_pressure_threshold": round(float(persona.legal_pressure_threshold), 3),
        "availability": round(float(persona.availability), 3),
    }
    return _character(
        node_id=persona.id,
        archetype=archetype_name,
        truth_class=profile.truth_class,
        traits=traits,
        role=persona.role,
        venue=venue,
        station=station,
        seed=seed,
        availability=persona.availability,
        economics=economics,
    )
