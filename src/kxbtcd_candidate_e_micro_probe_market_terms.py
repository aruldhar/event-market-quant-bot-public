"""Offline evidence receipt for market terms required by a future micro probe."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Mapping


class MicroProbeMarketTermsError(ValueError):
    pass


@dataclass(frozen=True)
class MicroProbeMarketTermsReceipt:
    market_ticker: str
    observed_utc: str
    market_response_sha256: str
    fractional_trading_enabled: bool
    quantity_increment_contracts: Decimal
    price_grid_evidence_id: str
    fee_schedule_id: str
    fee_schedule_response_sha256: str
    fee_schedule_effective_utc: str


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise MicroProbeMarketTermsError("market-terms identity field is blank")
    return value


def _sha256(payload: Mapping[str, object], key: str) -> str:
    value = _required_text(payload, key).lower()
    if not _SHA256.fullmatch(value):
        raise MicroProbeMarketTermsError("market-terms evidence hash is invalid")
    return value


def validate_micro_probe_market_terms(payload: Mapping[str, object]) -> MicroProbeMarketTermsReceipt:
    """Validate reviewed facts only; this module cannot access a venue or submit orders."""
    required = (
        "market_ticker", "observed_utc", "market_response_sha256",
        "fractional_trading_enabled", "quantity_increment_contracts",
        "price_grid_evidence_id", "fee_schedule_id",
        "fee_schedule_response_sha256", "fee_schedule_effective_utc",
    )
    if any(key not in payload for key in required):
        raise MicroProbeMarketTermsError("missing required market-terms fields")
    if payload["fractional_trading_enabled"] is not True:
        raise MicroProbeMarketTermsError("target market does not prove fractional trading")
    try:
        increment = Decimal(str(payload["quantity_increment_contracts"]))
    except (InvalidOperation, ValueError) as exc:
        raise MicroProbeMarketTermsError("market quantity increment is invalid") from exc
    if not increment.is_finite() or increment <= 0 or Decimal("0.01") % increment != 0:
        raise MicroProbeMarketTermsError("target market does not prove the 0.01 quantity increment")
    return MicroProbeMarketTermsReceipt(
        market_ticker=_required_text(payload, "market_ticker"),
        observed_utc=_required_text(payload, "observed_utc"),
        market_response_sha256=_sha256(payload, "market_response_sha256"),
        fractional_trading_enabled=True,
        quantity_increment_contracts=increment,
        price_grid_evidence_id=_required_text(payload, "price_grid_evidence_id"),
        fee_schedule_id=_required_text(payload, "fee_schedule_id"),
        fee_schedule_response_sha256=_sha256(payload, "fee_schedule_response_sha256"),
        fee_schedule_effective_utc=_required_text(payload, "fee_schedule_effective_utc"),
    )
