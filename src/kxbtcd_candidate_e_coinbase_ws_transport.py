"""Public Coinbase BTC-USD WebSocket transport contract.

This module contains transport constants and deterministic message construction.
It contains no authentication and no execution/order behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


COINBASE_WS_URL = "wss://ws-feed.exchange.coinbase.com"
COINBASE_PRODUCT = "BTC-USD"

COINBASE_CHANNELS = ("matches", "heartbeat")

ARCHITECTURE_FINGERPRINT = (
    "3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7"
)


class CoinbaseWsTransportError(RuntimeError):
    pass


def subscription_command() -> dict[str, Any]:
    return {
        "type": "subscribe",
        "product_ids": [COINBASE_PRODUCT],
        "channels": list(COINBASE_CHANNELS),
    }


def source_epoch_seconds(value: Any) -> int:
    text = str(value).strip()

    if not text:
        raise CoinbaseWsTransportError(
            "Coinbase source timestamp missing"
        )

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CoinbaseWsTransportError(
            "Coinbase source timestamp must be ISO-8601"
        ) from exc

    if dt.tzinfo is None:
        raise CoinbaseWsTransportError(
            "Coinbase source timestamp must be timezone-aware"
        )

    return int(dt.astimezone(timezone.utc).timestamp())


def minute_start_for_source_time(value: Any) -> int:
    epoch_s = source_epoch_seconds(value)
    return (epoch_s // 60) * 60
