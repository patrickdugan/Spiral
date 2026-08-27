"""Identity-agnostic bonding and reward primitives for connector services."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable


@dataclass(frozen=True)
class BondPolicy:
    capital_rate: float = 0.10
    failure_rate: float = 0.50
    downtime_rate: float = 0.25
    minimum_bond: int = 1_000

    def required(self, capital: int, service_value: int, risk_score: float) -> int:
        if capital < 0 or service_value < 0 or not 0 <= risk_score <= 1:
            raise ValueError("invalid bond inputs")
        return max(
            self.minimum_bond,
            ceil(self.capital_rate * capital + risk_score * service_value),
        )


@dataclass(frozen=True)
class ServiceRecord:
    connector_id: str
    capital_id: str
    posted_bond: int
    promised_steps: int
    available_steps: int
    attempted_volume: int
    delivered_volume: int
    attributable_failures: int

    @property
    def availability(self) -> float:
        return self.available_steps / max(1, self.promised_steps)

    @property
    def delivery_rate(self) -> float:
        return self.delivered_volume / max(1, self.attempted_volume)


@dataclass(frozen=True)
class BondSettlement:
    released: int
    slashed: int
    score: float


def settle_bond(record: ServiceRecord, policy: BondPolicy = BondPolicy()) -> BondSettlement:
    downtime = 1.0 - record.availability
    failed_share = min(1.0, record.attributable_failures / max(1, record.promised_steps))
    severity = min(1.0, policy.downtime_rate * downtime + policy.failure_rate * failed_share)
    slashed = min(record.posted_bond, ceil(record.posted_bond * severity))
    score = max(0.0, 0.6 * record.delivery_rate + 0.4 * record.availability - severity)
    return BondSettlement(record.posted_bond - slashed, slashed, score)


@dataclass(frozen=True)
class RewardClaim:
    identity_id: str
    capital_id: str
    capital: int
    service_score: float


def sybil_invariant_rewards(claims: Iterable[RewardClaim], pool: int) -> dict[str, int]:
    """Allocate once per economic capital identifier, never once per identity.

    If multiple identities claim the same capital, only the best observed service
    score defines that capital's weight. The resulting capital reward is divided
    among the identities that named it, so splitting an identity cannot increase
    the coalition's aggregate reward.
    """

    claims = list(claims)
    if pool < 0 or any(c.capital < 0 or not 0 <= c.service_score <= 1 for c in claims):
        raise ValueError("invalid reward inputs")
    by_capital: dict[str, list[RewardClaim]] = {}
    for claim in claims:
        by_capital.setdefault(claim.capital_id, []).append(claim)
    weights = {
        capital_id: max(c.capital for c in group) * max(c.service_score for c in group)
        for capital_id, group in by_capital.items()
    }
    total_weight = sum(weights.values())
    rewards = {claim.identity_id: 0 for claim in claims}
    if total_weight == 0:
        return rewards
    assigned = 0
    ordered = sorted(by_capital)
    for index, capital_id in enumerate(ordered):
        group = by_capital[capital_id]
        capital_reward = (
            pool - assigned
            if index == len(ordered) - 1
            else int(pool * weights[capital_id] / total_weight)
        )
        assigned += capital_reward
        share, remainder = divmod(capital_reward, len(group))
        for position, claim in enumerate(sorted(group, key=lambda c: c.identity_id)):
            rewards[claim.identity_id] += share + (1 if position < remainder else 0)
    return rewards


def naive_identity_rewards(claims: Iterable[RewardClaim], reward_per_identity: int) -> dict[str, int]:
    return {claim.identity_id: reward_per_identity for claim in claims}
