"""Conservative Coinbase WS/REST trade-identity compatibility.

Empirical D3 evidence observed that Coinbase WebSocket and REST can represent
the same trade ID with:

- numerically identical price;
- numerically identical size;
- identical side;
- timestamp serialization differing by 1 microsecond.

This module does NOT assume Coinbase always behaves that way.

The accepted compatibility envelope is deliberately narrow:

1. exact trade ID;
2. exact numeric price;
3. exact numeric size;
4. exact side;
5. absolute timestamp difference <= 1 microsecond;
6. both timestamps must belong to the same exact UTC minute.

Any larger discrepancy or minute-boundary ambiguity fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping


MAX_CROSS_TRANSPORT_TIMESTAMP_DELTA_US = 1


class CoinbaseCrossTransportIdentityError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class CoinbaseCrossTransportIdentity:
    compatible: bool
    trade_id_equal: bool
    price_equal: bool
    size_equal: bool
    side_equal: bool
    timestamp_delta_us: int
    timestamp_within_tolerance: bool
    same_utc_minute: bool


def _trade_id(
    value: Any,
    name: str,
) -> int:
    if isinstance(value, bool):
        raise CoinbaseCrossTransportIdentityError(
            f"{name} must be integer"
        )

    try:
        result = int(value)
    except Exception as exc:
        raise CoinbaseCrossTransportIdentityError(
            f"{name} must be integer-compatible"
        ) from exc

    if result < 0:
        raise CoinbaseCrossTransportIdentityError(
            f"{name} must be nonnegative"
        )

    return result


def _decimal(
    value: Any,
    name: str,
) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise CoinbaseCrossTransportIdentityError(
            f"{name} must be decimal-compatible"
        ) from exc

    if not result.is_finite():
        raise CoinbaseCrossTransportIdentityError(
            f"{name} must be finite"
        )

    return result


def _epoch_us(
    value: Any,
    name: str,
) -> int:
    text = str(value).strip()

    if not text:
        raise CoinbaseCrossTransportIdentityError(
            f"{name} missing"
        )

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CoinbaseCrossTransportIdentityError(
            f"{name} must be ISO-8601"
        ) from exc

    if dt.tzinfo is None:
        raise CoinbaseCrossTransportIdentityError(
            f"{name} must be timezone-aware"
        )

    dt = dt.astimezone(timezone.utc)

    return (
        int(dt.timestamp()) * 1_000_000
        + dt.microsecond
    )


def compare_ws_rest_trade_identity(
    ws_trade: Mapping[str, Any],
    rest_trade: Mapping[str, Any],
) -> CoinbaseCrossTransportIdentity:
    if not isinstance(ws_trade, Mapping):
        raise CoinbaseCrossTransportIdentityError(
            "WebSocket trade must be an object"
        )

    if not isinstance(rest_trade, Mapping):
        raise CoinbaseCrossTransportIdentityError(
            "REST trade must be an object"
        )

    ws_id = _trade_id(
        ws_trade.get("trade_id"),
        "ws.trade_id",
    )
    rest_id = _trade_id(
        rest_trade.get("trade_id"),
        "rest.trade_id",
    )

    ws_price = _decimal(
        ws_trade.get("price"),
        "ws.price",
    )
    rest_price = _decimal(
        rest_trade.get("price"),
        "rest.price",
    )

    ws_size = _decimal(
        ws_trade.get("size"),
        "ws.size",
    )
    rest_size = _decimal(
        rest_trade.get("size"),
        "rest.size",
    )

    ws_side = str(
        ws_trade.get("side", "")
    )
    rest_side = str(
        rest_trade.get("side", "")
    )

    if not ws_side or not rest_side:
        raise CoinbaseCrossTransportIdentityError(
            "trade side missing"
        )

    ws_us = _epoch_us(
        ws_trade.get("time"),
        "ws.time",
    )
    rest_us = _epoch_us(
        rest_trade.get("time"),
        "rest.time",
    )

    delta_us = (
        rest_us - ws_us
    )

    trade_id_equal = (
        ws_id == rest_id
    )

    price_equal = (
        ws_price == rest_price
    )

    size_equal = (
        ws_size == rest_size
    )

    side_equal = (
        ws_side == rest_side
    )

    timestamp_within_tolerance = (
        abs(delta_us)
        <= MAX_CROSS_TRANSPORT_TIMESTAMP_DELTA_US
    )

    ws_minute = (
        ws_us // 60_000_000
    )
    rest_minute = (
        rest_us // 60_000_000
    )

    same_utc_minute = (
        ws_minute == rest_minute
    )

    compatible = all((
        trade_id_equal,
        price_equal,
        size_equal,
        side_equal,
        timestamp_within_tolerance,
        same_utc_minute,
    ))

    return CoinbaseCrossTransportIdentity(
        compatible=compatible,
        trade_id_equal=trade_id_equal,
        price_equal=price_equal,
        size_equal=size_equal,
        side_equal=side_equal,
        timestamp_delta_us=delta_us,
        timestamp_within_tolerance=
            timestamp_within_tolerance,
        same_utc_minute=
            same_utc_minute,
    )
