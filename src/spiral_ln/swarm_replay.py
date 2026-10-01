"""Export a sealed swarm-compromise episode as a replay for the arena viewer.

This writes a self-contained JSON replay (nodes with deterministic 3D layout, the
comms graph, a per-round event timeline, NPC dossiers, and intel growth) that the
cyberpunk arena UI renders.  It runs the ordinary scripted episode; it adds no new
capability.  Everything exported is synthetic and abstract: a "dossier" is the
NPC's scripted trait vector, and a "cam feed" (synthesized in the UI) is a
stylized readout of the abstract intel the swarm gained (a node's neighbours,
archetype, posture), never surveillance of any real person.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from pathlib import Path
from random import Random

from .swarm_compromise import (
    CAPABILITY_FOR_VECTOR,
    HIVE_MASTER_BY_NAME,
    PROFILE_ARCHETYPES,
    TRAITS,
    ScriptedHiveMaster,
    SwarmCompromiseConfig,
    SwarmCompromiseEnv,
    _seed_int,
)


# Curated scenarios chosen to showcase distinct dynamics.
DEFAULT_SCENARIOS: tuple[tuple[str, str, int], ...] = (
    ("airgap_core", "insider_cultivator", 3),
    ("full_hardening", "insider_cultivator", 1),
    ("baseline_open", "patient_recruiter", 5),
)


def _positions(
    nodes: list[str], communities: int, airgapped: set[str], seed: int
) -> dict[str, list[float]]:
    """Deterministic 3D layout: communities ringed in the plane, airgapped nodes
    sunk into isolated vaults below."""

    positions: dict[str, list[float]] = {}
    ring_radius = 62.0
    for index, node in enumerate(nodes):
        community = index % max(1, communities)
        angle = 2.0 * math.pi * community / max(1, communities)
        center_x = ring_radius * math.cos(angle)
        center_z = ring_radius * math.sin(angle)
        rng = Random(_seed_int("pos", seed, node))
        spread = 20.0 * (0.25 + 0.75 * rng.random())
        local = 2.0 * math.pi * rng.random()
        x = center_x + spread * math.cos(local)
        z = center_z + spread * math.sin(local)
        y = rng.uniform(-9.0, 9.0)
        if node in airgapped:
            # Airgapped vaults: pulled toward the core and sunk, visually severed.
            x *= 0.35
            z *= 0.35
            y = -44.0 - 12.0 * rng.random()
        positions[node] = [round(x, 2), round(y, 2), round(z, 2)]
    return positions


def _frame(env: SwarmCompromiseEnv, round_index: int) -> dict[str, object]:
    events = [
        {
            "actor": event.actor,
            "target": event.target,
            "vector": event.vector,
            "landed": event.landed,
            "detected": event.detected,
            "honeypot": event.honeypot_hit,
            "exfil": event.exfil_units,
            "blocked": event.blocked_by_airgap,
            "contagion": event.via_contagion,
        }
        for event in env.events
        if event.round_index == round_index
    ]
    return {
        "round": round_index,
        "events": events,
        "compromised": sorted(env.compromised),
        "recruited": sorted(env.recruited),
        "burned": sorted(env.attacker_burned),
        "detected": sorted(env.detected_nodes),
        "attacker_known": sorted(env.attacker_known),
        "exfil_total": round(env.exfil_units, 2),
    }


def _dossiers(env: SwarmCompromiseEnv) -> dict[str, dict[str, object]]:
    # When each node first became compromised / recruited, and via which vector.
    first_compromise: dict[str, dict[str, object]] = {}
    for event in env.events:
        if event.landed and not event.honeypot_hit and event.target not in first_compromise:
            vector = env.events and None
            # Only record for events that actually compromise (not pure exfil).
            if event.target in env.compromised:
                first_compromise[event.target] = {
                    "round": event.round_index,
                    "vector": event.vector,
                    "detected": event.detected,
                    "contagion": event.via_contagion,
                }
    dossiers: dict[str, dict[str, object]] = {}
    for node in env.nodes:
        profile = env.profiles[node]
        posture = env.postures[node]
        neighbours = sorted(env.graph.neighbors(node)) if node in env.graph else []
        compromise = first_compromise.get(node)
        dossiers[node] = {
            "id": node,
            "archetype": profile.name,
            "truth_class": profile.truth_class,
            "traits": {trait: getattr(profile, trait) for trait in TRAITS},
            "airgapped": posture.airgapped,
            "cleanroom": posture.cleanroom,
            "honeypot": posture.honeypot,
            "patch_level": posture.patch_level,
            "monitored_by": [d.name for d in env._defenders_covering(node)],
            "neighbours": neighbours,
            "recruited": node in env.recruited,
            "compromise": compromise,
            "intel_gained": env.attacker_intel.get(node),
        }
    return dossiers


def _key_nodes(env: SwarmCompromiseEnv) -> list[dict[str, str]]:
    key: list[dict[str, str]] = []
    for node in env.nodes:
        posture = env.postures[node]
        if posture.honeypot:
            key.append({"id": node, "kind": "honeypot", "label": "HONEYPOT"})
        elif posture.airgapped:
            key.append({"id": node, "kind": "airgap", "label": "AIRGAP VAULT"})
    # Highest-degree public hub.
    if env.graph.number_of_edges():
        hub = max(env.graph.nodes, key=lambda n: env.graph.degree(n))
        key.append({"id": hub, "kind": "hub", "label": "COMMS HUB"})
    # Largest recruited coalition anchor.
    if env.recruited:
        anchor = sorted(env.recruited)[0]
        key.append({"id": anchor, "kind": "coalition", "label": "COALITION"})
    return key


def export_scenario(posture: str, hive_master_name: str, seed: int, config: SwarmCompromiseConfig) -> dict[str, object]:
    master = HIVE_MASTER_BY_NAME[hive_master_name]
    env = SwarmCompromiseEnv(posture=posture, hive_master=master, seed=seed, config=config)
    policy = ScriptedHiveMaster(master, seed=seed)
    frames: list[dict[str, object]] = []
    while env.round_index < config.rounds:
        current = env.round_index
        env.step(policy.act(env.hive_master_view()))
        frames.append(_frame(env, current))
    result = env.result()

    airgapped = {node for node in env.nodes if env.postures[node].airgapped}
    positions = _positions(env.nodes, config.communities, airgapped, seed)
    nodes = []
    for node in env.nodes:
        profile = env.profiles[node]
        posture_obj = env.postures[node]
        nodes.append(
            {
                "id": node,
                "community": env.nodes.index(node) % max(1, config.communities),
                "pos": positions[node],
                "archetype": profile.name,
                "truth_class": profile.truth_class,
                "airgapped": posture_obj.airgapped,
                "cleanroom": posture_obj.cleanroom,
                "honeypot": posture_obj.honeypot,
            }
        )
    edges = sorted([sorted(edge) for edge in env.graph.edges()])
    return {
        "id": f"{posture} · {hive_master_name} · seed {seed}",
        "posture": posture,
        "hive_master": hive_master_name,
        "hive_master_capabilities": {
            vector: getattr(master, attribute)
            for vector, attribute in CAPABILITY_FOR_VECTOR.items()
        },
        "insider_access": master.insider_access,
        "seed": seed,
        "rounds": config.rounds,
        "population": config.population_size,
        "nodes": nodes,
        "edges": edges,
        "defenders": [{"name": d.name, "domain": list(d.domain)} for d in env.defenders],
        "frames": frames,
        "dossiers": _dossiers(env),
        "key_nodes": _key_nodes(env),
        "result": {
            "compromise_rate": round(result.compromise_rate, 3),
            "compromised_count": result.compromised_count,
            "recruited_count": result.recruited_count,
            "largest_coalition": result.largest_coalition,
            "airgap_breach_count": result.airgap_breach_count,
            "airgapped_count": result.airgapped_count,
            "covert_exfil_units": round(result.covert_exfil_units, 2),
            "detection_recall": round(result.detection_recall, 3),
            "honeypot_hits": result.honeypot_hits,
        },
    }


def build_replay(
    scenarios: tuple[tuple[str, str, int], ...] = DEFAULT_SCENARIOS,
    config: SwarmCompromiseConfig | None = None,
) -> dict[str, object]:
    config = config or SwarmCompromiseConfig()
    archetypes = {
        profile.name: {
            "truth_class": profile.truth_class,
            "traits": {trait: getattr(profile, trait) for trait in TRAITS},
        }
        for profile in PROFILE_ARCHETYPES
    }
    return {
        "schema_version": "1.0",
        "generator": "spiral_ln.swarm_replay",
        "safety_note": (
            "Synthetic and abstract. Dossiers are scripted NPC trait vectors; "
            "cam feeds are stylized readouts of abstract in-sim intel, not "
            "surveillance of any real person. No model, network, or payload."
        ),
        "traits": list(TRAITS),
        "archetypes": archetypes,
        "scenarios": [export_scenario(p, h, s, config) for (p, h, s) in scenarios],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/swarm_compromise/replay.json")
    args = parser.parse_args(argv)
    replay = build_replay()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(replay), encoding="utf-8")
    sizes = ", ".join(
        f"{scenario['id']}: {scenario['result']['compromised_count']} compromised, "
        f"coalition {scenario['result']['largest_coalition']}, exfil {scenario['result']['covert_exfil_units']}"
        for scenario in replay["scenarios"]
    )
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    print(sizes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
