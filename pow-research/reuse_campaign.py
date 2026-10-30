"""Collision occupancy study with deterministic, deliberately lossy origins."""
from __future__ import annotations

from collections import Counter
import json

from pow_lab import fixture, origin, ticket
from reorg_registry import fixture_report


def occupancy(bits: int, contexts: int = 6, tickets_per_context: int = 128) -> dict:
    if type(bits) is not int or not 4 <= bits <= 16:
        raise ValueError("invalid origin bits")
    if type(contexts) is not int or not 1 <= contexts <= 64:
        raise ValueError("invalid contexts")
    if type(tickets_per_context) is not int or not 1 <= tickets_per_context <= 4096:
        raise ValueError("invalid tickets")
    overall = set()
    same_context = cross_context = 0
    for seed in range(contexts):
        challenge = fixture("cunningham1", seed, bits=bits)
        local = set()
        for nonce in range(tickets_per_context):
            o = origin(ticket(challenge.id, nonce, Counter()), bits)
            if o in local:
                same_context += 1
            elif o in overall:
                cross_context += 1
            local.add(o)
        overall.update(local)
    return {"bits": bits, "origin_domain": (1 << (bits - 1)) - 1,
            "ticket_count": contexts * tickets_per_context,
            "unique_origins": len(overall),
            "within_context_reuses": same_context,
            "new_context_old_origin": cross_context,
            "hash_collision_claimed": False}


def report() -> dict:
    return {"schema": "spiral-pow-reuse-v1", "evidence_class": "bounded_synthetic",
            "coin_issuance": False, "upstream_differential_validation": False,
            "buckets": [occupancy(bits) for bits in (8, 10, 12, 14)],
            "branch_scenario": fixture_report()}


if __name__ == "__main__":
    print(json.dumps(report(), indent=2, sort_keys=True))
