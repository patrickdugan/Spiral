"""Roadmap interface for a Liquity-style USD stablecoin on the Cashu/BTC reserve.

Design only. No RGB or Utexo SDK is present in this workspace, so the only
implementation is ``NotConnectedAdapter``. It never returns prices, balances
or transactions. A real adapter must settle in USDT on RGB (via Utexo) and
replace this stub without changing the method signatures.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

Status = Literal['not_connected']

SETTLEMENT_ASSET = 'USDT on RGB (Utexo)'
COLLATERAL = 'Protected Cashu claims backed by the BTC reserve'


@dataclass(frozen=True)
class AdapterResult:
    status: Status
    operation: str
    detail: str
    settlement_asset: str = SETTLEMENT_ASSET
    collateral: str = COLLATERAL
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class StablecoinAdapter(Protocol):
    def quote(self, collateral_sats: int, debt_usd_cents: int) -> AdapterResult:
        """Collateral ratio, fees and liquidation price for a prospective trove."""

    def open_trove(self, claim_id: str, collateral_sats: int, debt_usd_cents: int,
                   rgb_invoice: str) -> AdapterResult:
        """Lock a protected claim as collateral and issue USD debt to an RGB invoice."""

    def redeem(self, amount_usd_cents: int, btc_destination: str) -> AdapterResult:
        """Burn USD units and receive BTC from the lowest-ratio troves at face value."""


class NotConnectedAdapter:
    """The only adapter in this build. Every call refuses without side effects."""

    _detail = 'No RGB/Utexo SDK is installed. Nothing was quoted, issued or redeemed.'

    def _refuse(self, operation: str) -> AdapterResult:
        return AdapterResult('not_connected', operation, self._detail)

    def quote(self, collateral_sats: int, debt_usd_cents: int) -> AdapterResult:
        return self._refuse('quote')

    def open_trove(self, claim_id: str, collateral_sats: int, debt_usd_cents: int,
                   rgb_invoice: str) -> AdapterResult:
        return self._refuse('open_trove')

    def redeem(self, amount_usd_cents: int, btc_destination: str) -> AdapterResult:
        return self._refuse('redeem')


def status(adapter: StablecoinAdapter | None = None) -> dict:
    adapter = adapter or NotConnectedAdapter()
    return {
        'status': 'not_connected',
        'adapter': type(adapter).__name__,
        'settlement_asset': SETTLEMENT_ASSET,
        'collateral': COLLATERAL,
        'operations': ['quote', 'open_trove', 'redeem'],
        'detail': NotConnectedAdapter._detail,
    }
