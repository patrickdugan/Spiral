"""Deterministic branch-local research registry; proof verification happens upstream.

An explicitly synthetic DAG models duplicate policy under alternate histories.
No mining, fork-choice weights, wallet or live-chain operations are implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Iterable

from pow_lab import artifact_id, chain_terms, digest

POLICIES = ("exact", "overlap", "suffix")


@dataclass(frozen=True)
class Claim:
    family: str
    terms: tuple[int, ...]

    @classmethod
    def from_center(cls, center: int, family: str, length: int) -> "Claim":
        return cls(family, tuple(chain_terms(center, family, length)))

    def __post_init__(self) -> None:
        if self.family not in ("cunningham1", "cunningham2", "bitwin"):
            raise ValueError("invalid family")
        if type(self.terms) is not tuple or len(self.terms) not in range(2, 7):
            raise ValueError("invalid chain length")
        if any(type(n) is not int for n in self.terms):
            raise ValueError("invalid term type")
        center = self.terms[0] + (1 if self.family != "cunningham2" else -1)
        if tuple(chain_terms(center, self.family, len(self.terms))) != self.terms:
            raise ValueError("invalid recurrence")

    @property
    def key(self) -> str:
        return artifact_id(self.family, list(self.terms))


def is_contiguous_subchain(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    if len(a) > len(b):
        a, b = b, a
    return any(tuple(b[i:i + len(a)]) == a for i in range(len(b) - len(a) + 1))


def clash(a: Claim, b: Claim, policy: str) -> bool:
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    if policy == "exact":
        return a.key == b.key
    if policy == "overlap":
        return bool(set(a.terms) & set(b.terms))
    return a.family == b.family and is_contiguous_subchain(a.terms, b.terms)


class ClaimRejected(ValueError):
    pass


@dataclass(frozen=True)
class Block:
    identifier: str
    parent: str | None
    claims: tuple[Claim, ...]
    height: int


class BranchRegistry:
    """Append branches with ancestor-local checks; choose a canonical tip explicitly.

    Claims stand for previously accepted proofs: arithmetic and proof bytes
    are not validated here. Fork choice, chainwork and incentive compatibility
    deliberately remain out of scope.
    """

    def __init__(self, policy: str = "exact") -> None:
        if policy not in POLICIES:
            raise ValueError("unknown policy")
        self.policy = policy
        self.blocks = {"genesis": Block("genesis", None, (), 0)}
        self.tip = "genesis"

    def history(self, tip: str) -> list[Block]:
        if tip not in self.blocks:
            raise ValueError("unknown tip")
        out = []
        while tip != "genesis":
            block = self.blocks[tip]
            out.append(block)
            tip = block.parent
        return list(reversed(out))

    def branch_claims(self, tip: str) -> list[Claim]:
        return [claim for block in self.history(tip) for claim in block.claims]

    def append(self, parent: str, label: str, claims: Iterable[Claim]) -> str:
        if parent not in self.blocks:
            raise ValueError("unknown parent")
        if type(label) is not str or not label.isascii() or not 1 <= len(label) <= 64:
            raise ValueError("invalid block label")
        candidate = tuple(islice(iter(claims), 17))
        if len(candidate) > 16 or any(type(claim) is not Claim for claim in candidate):
            raise ValueError("invalid claims")
        previous = self.branch_claims(parent)
        for claim in candidate:
            if any(clash(claim, older, self.policy) for older in previous):
                raise ClaimRejected("duplicate or overlapping claim on this ancestry")
            previous.append(claim)
        identifier = digest(["spiral/pow/branch/v1", parent, label, [c.key for c in candidate]])
        if identifier in self.blocks:
            raise ValueError("already appended identical block")
        self.blocks[identifier] = Block(identifier, parent, candidate, self.blocks[parent].height + 1)
        return identifier

    def select_tip(self, tip: str) -> dict:
        before = self.branch_claims(self.tip)
        after = self.branch_claims(tip)
        self.tip = tip
        prev_keys, now_keys = {c.key for c in before}, {c.key for c in after}
        return {"tip": tip, "height": self.blocks[tip].height,
                "rolled_back": sorted(prev_keys - now_keys),
                "activated": sorted(now_keys - prev_keys),
                "active_keys": sorted(now_keys)}


def fixture_report() -> dict:
    older = Claim.from_center(6, "cunningham1", 4)
    suffix = Claim.from_center(12, "cunningham1", 3)
    registry = BranchRegistry("exact")
    side_a = Claim.from_center(30, "cunningham2", 2)  # 31, 61
    side_b = Claim.from_center(42, "cunningham1", 2)  # 41, 83
    a = registry.append("genesis", "branch-A", [older, side_a])
    b = registry.append("genesis", "branch-B", [older, side_b])
    selection_a = registry.select_tip(a)
    selection_b = registry.select_tip(b)
    reuses_work = registry.append(a, "work-reused-suffix", [suffix])
    rejected_exact = False
    try:
        registry.append(a, "duplicate-on-same-branch", [older])
    except ClaimRejected:
        rejected_exact = True
    overlap = BranchRegistry("overlap")
    x = overlap.append("genesis", "full", [older])
    rejected_overlap = False
    try:
        overlap.append(x, "suffix", [suffix])
    except ClaimRejected:
        rejected_overlap = True
    return {"schema": "spiral-pow-reorg-v1", "evidence_class": "bounded_synthetic",
            "same_artifact_allowed_on_forks": True,
            "active_count_after_A": len(selection_a["active_keys"]),
            "active_count_after_B": len(selection_b["active_keys"]),
            "distinct_keys_after_suffix": len(registry.branch_claims(reuses_work)),
            "exact_duplicate_same_branch_rejected": rejected_exact,
            "overlap_suffix_rejected": rejected_overlap,
            "cross_branch_rolled_back": len(selection_b["rolled_back"]),
            "cross_branch_activated": len(selection_b["activated"])}
