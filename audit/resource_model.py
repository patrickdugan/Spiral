"""Small reference semantics for Liquidity on Trial, not a Lightning node.

Amounts are integer msat. Prepare reserves gross directional requirements;
settle moves balances; abort releases reservations. Both are atomic. Distinct
channel IDs are retained. No cryptography, fee negotiation, HTLC protocol, or
distributed atomic-commit claim is made.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResourceChannel:
    capacity: int
    left: int
    reserve_left: int = 0
    reserve_right: int = 0
    held_left: int = 0
    held_right: int = 0

    def validate(self) -> None:
        values = (self.capacity, self.left, self.reserve_left, self.reserve_right, self.held_left, self.held_right)
        if any(type(value) is not int for value in values):
            raise ValueError("integer msat required")
        if self.capacity <= 0 or not 0 <= self.left <= self.capacity:
            raise ValueError("invalid capacity/balance")
        if min(self.reserve_left, self.reserve_right, self.held_left, self.held_right) < 0:
            raise ValueError("negative reserve")
        if self.reserve_left + self.held_left > self.left:
            raise ValueError("left reservations exceed balance")
        if self.reserve_right + self.held_right > self.capacity - self.left:
            raise ValueError("right reservations exceed balance")


@dataclass
class ResourceLedger:
    channels: dict[str, ResourceChannel]
    pending: dict[str, dict[tuple[str, int], int]] = field(default_factory=dict)
    consumed_ids: set[str] = field(default_factory=set)

    def prepare(self, operation_id: str, transfers: list[tuple[str, int, int]]) -> None:
        if not operation_id or operation_id in self.pending or operation_id in self.consumed_ids:
            raise ValueError("operation identifier must be fresh")
        if not transfers:
            raise ValueError("empty operation")
        requirements: dict[tuple[str, int], int] = {}
        for channel_id, direction, amount in transfers:
            if type(direction) is not int or direction not in (-1, 1) or type(amount) is not int or amount <= 0:
                raise ValueError("invalid directional amount")
            key = channel_id, direction
            requirements[key] = requirements.get(key, 0) + amount
        # No mutation until ALL requirements are checked. Opposite-direction
        # reservations cannot be netted against uncommitted incoming proceeds.
        for (channel_id, direction), amount in requirements.items():
            channel = self.channels[channel_id]
            channel.validate()
            available = (channel.left - channel.reserve_left - channel.held_left if direction == 1
                         else channel.capacity - channel.left - channel.reserve_right - channel.held_right)
            if amount > available:
                raise ValueError("insufficient gross directional resources")
        for (channel_id, direction), amount in requirements.items():
            channel = self.channels[channel_id]
            if direction == 1:
                channel.held_left += amount
            else:
                channel.held_right += amount
        self.pending[operation_id] = requirements

    def finish(self, operation_id: str, settle: bool) -> None:
        if type(settle) is not bool:
            raise ValueError("settle must be boolean")
        requirements = self.pending[operation_id]
        for (channel_id, direction), amount in requirements.items():
            channel = self.channels[channel_id]
            if direction == 1:
                channel.held_left -= amount
            else:
                channel.held_right -= amount
            if settle:
                channel.left -= direction * amount
        del self.pending[operation_id]
        self.consumed_ids.add(operation_id)
        for channel in self.channels.values():
            channel.validate()


def fee_vector(delivered_msat: int, relay_policies: list[tuple[int, int]]) -> list[int]:
    """Outgoing-edge relay policies from first to last intermediate node.

    Conventional integer fee = base + floor(amount * ppm / 1e6). The first
    result is payer debit, final result recipient credit. No sender self-fee.
    """
    if type(delivered_msat) is not int or delivered_msat <= 0:
        raise ValueError("invalid delivery")
    amounts = [delivered_msat]
    for base, ppm in reversed(relay_policies):
        if type(base) is not int or type(ppm) is not int or min(base, ppm) < 0:
            raise ValueError("invalid fee policy")
        downstream = amounts[-1]
        amounts.append(downstream + base + downstream * ppm // 1_000_000)
    return list(reversed(amounts))
