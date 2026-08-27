"""Core state algebra for directional Lightning-channel liquidity.

The model is intentionally bounded.  It represents channel balances, reserves,
fees, and connector rewrites; it does not construct or broadcast transactions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import ceil
from typing import Iterable, Sequence


class ConnectorKind(str, Enum):
    TOPOLOGICAL = "topological"
    CIRCULAR = "circular"
    LEASED = "leased"
    VIRTUAL = "virtual"


@dataclass
class Channel:
    u: str
    v: str
    capacity: int
    balance_uv: int
    base_fee_msat: int = 1_000
    fee_ppm: int = 100
    cltv_delta: int = 40
    reserve: int = 0
    locked_uv: int = 0
    locked_vu: int = 0

    def __post_init__(self) -> None:
        if self.u == self.v:
            raise ValueError("a channel needs distinct endpoints")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        if not 0 <= self.balance_uv <= self.capacity:
            raise ValueError("directional balance must lie within capacity")
        if min(self.reserve, self.locked_uv, self.locked_vu) < 0:
            raise ValueError("reserve and locks cannot be negative")

    @property
    def balance_vu(self) -> int:
        return self.capacity - self.balance_uv

    def balance(self, src: str, dst: str) -> int:
        if (src, dst) == (self.u, self.v):
            return self.balance_uv
        if (src, dst) == (self.v, self.u):
            return self.balance_vu
        raise KeyError(f"{src}->{dst} is not this channel")

    def available(self, src: str, dst: str) -> int:
        locked = self.locked_uv if (src, dst) == (self.u, self.v) else self.locked_vu
        return max(0, self.balance(src, dst) - self.reserve - locked)

    def transfer(self, src: str, dst: str, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if amount > self.available(src, dst):
            raise ValueError("insufficient directional liquidity")
        if (src, dst) == (self.u, self.v):
            self.balance_uv -= amount
        elif (src, dst) == (self.v, self.u):
            self.balance_uv += amount
        else:
            raise KeyError(f"{src}->{dst} is not this channel")

    def fee_msat(self, amount_sat: int) -> int:
        return self.base_fee_msat + ceil(amount_sat * self.fee_ppm / 1_000)

    def copy(self) -> "Channel":
        return Channel(**self.__dict__)


@dataclass
class NetworkState:
    channels: dict[frozenset[str], Channel] = field(default_factory=dict)

    def add_channel(self, channel: Channel, replace: bool = False) -> None:
        key = frozenset((channel.u, channel.v))
        if len(key) != 2:
            raise ValueError("invalid channel endpoints")
        if key in self.channels and not replace:
            raise ValueError("parallel channels are abstracted as one aggregate channel")
        self.channels[key] = channel

    def channel(self, a: str, b: str) -> Channel:
        return self.channels[frozenset((a, b))]

    @property
    def nodes(self) -> set[str]:
        result: set[str] = set()
        for channel in self.channels.values():
            result.update((channel.u, channel.v))
        return result

    @property
    def total_capacity(self) -> int:
        return sum(channel.capacity for channel in self.channels.values())

    def clone(self) -> "NetworkState":
        return NetworkState({key: channel.copy() for key, channel in self.channels.items()})

    def route_feasible(self, path: Sequence[str], amount: int) -> bool:
        return len(path) >= 2 and all(
            self.channel(a, b).available(a, b) >= amount
            for a, b in zip(path, path[1:])
        )

    def route_cost_msat(self, path: Sequence[str], amount: int) -> int:
        return sum(
            self.channel(a, b).fee_msat(amount) for a, b in zip(path, path[1:])
        )

    def apply_route(self, path: Sequence[str], amount: int) -> None:
        if not self.route_feasible(path, amount):
            raise ValueError("route is infeasible")
        before = self.total_capacity
        for a, b in zip(path, path[1:]):
            self.channel(a, b).transfer(a, b, amount)
        if self.total_capacity != before:
            raise AssertionError("payment rewrite changed channel capacity")

    def imbalance_energy(self) -> float:
        """Capacity-weighted squared distance from a 50/50 channel state."""
        total = max(1, self.total_capacity)
        return sum(
            channel.capacity
            * ((channel.balance_uv - channel.capacity / 2) / (channel.capacity / 2)) ** 2
            for channel in self.channels.values()
        ) / total

    def assert_invariants(self) -> None:
        for channel in self.channels.values():
            if channel.balance_uv + channel.balance_vu != channel.capacity:
                raise AssertionError("channel conservation failed")
            if not 0 <= channel.balance_uv <= channel.capacity:
                raise AssertionError("balance escaped channel bounds")
            if channel.locked_uv > channel.balance_uv:
                raise AssertionError("forward lock exceeds balance")
            if channel.locked_vu > channel.balance_vu:
                raise AssertionError("reverse lock exceeds balance")


@dataclass(frozen=True)
class Connector:
    connector_id: str
    kind: ConnectorKind
    endpoints: tuple[str, ...]
    amount: int
    bond: int = 0
    expiry_step: int | None = None
    capital_id: str | None = None

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError("connector amount must be positive")
        if len(self.endpoints) < 2:
            raise ValueError("connector needs at least two endpoints")
        if self.kind == ConnectorKind.CIRCULAR and self.endpoints[0] != self.endpoints[-1]:
            raise ValueError("a circular connector must close its route")


@dataclass(frozen=True)
class GhostPlan:
    """A solver-side contingent edge that must compile to an enforceable action."""

    ghost_id: str
    source: str
    target: str
    amount: int
    mechanism: ConnectorKind
    service_horizon: int
    risk_rate: float

    def required_bond(self, capital_rate: float = 0.10) -> int:
        exposure = self.amount * (capital_rate + self.risk_rate * self.service_horizon)
        return max(1, ceil(exposure))

    def compile(self) -> Connector:
        if self.mechanism not in {ConnectorKind.TOPOLOGICAL, ConnectorKind.LEASED}:
            raise ValueError("a ghost edge compiles only to capital-bearing connectors")
        return Connector(
            connector_id=f"compiled:{self.ghost_id}",
            kind=self.mechanism,
            endpoints=(self.source, self.target),
            amount=self.amount,
            bond=self.required_bond(),
            expiry_step=self.service_horizon if self.mechanism == ConnectorKind.LEASED else None,
            capital_id=f"capital:{self.ghost_id}",
        )


def apply_connector(state: NetworkState, connector: Connector) -> None:
    """Apply a connector rewrite to a state.

    Topological and leased connectors add capital. Circular connectors only move
    existing directional balances. Virtual connectors are declarations and are
    deliberately not executable in the bounded simulator.
    """

    if connector.kind in {ConnectorKind.TOPOLOGICAL, ConnectorKind.LEASED}:
        a, b = connector.endpoints[:2]
        state.add_channel(Channel(a, b, connector.amount, connector.amount // 2))
    elif connector.kind == ConnectorKind.CIRCULAR:
        state.apply_route(connector.endpoints, connector.amount)
    else:
        raise ValueError("virtual connectors require an external settlement adapter")
    state.assert_invariants()


def edge_disjoint(paths: Iterable[Sequence[str]]) -> bool:
    seen: set[frozenset[str]] = set()
    for path in paths:
        for a, b in zip(path, path[1:]):
            edge = frozenset((a, b))
            if edge in seen:
                return False
            seen.add(edge)
    return True

