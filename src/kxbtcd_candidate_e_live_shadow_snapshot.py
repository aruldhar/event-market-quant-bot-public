"""One-way, sanitized causal inputs for the separate live-shadow simulator.

The read-only collector may publish this atomic snapshot after it has already
persisted and applied public market evidence.  The shadow process only reads
the snapshot file.  It does not share a socket, event loop, credentials, or
mutable collector state with the collector.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from .kxbtcd_candidate_e_soak_archive import write_json_atomic


class LiveShadowSnapshotError(ValueError):
    pass


LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION = "kxbtcd_candidate_e_live_shadow_snapshot.v1"
CANONICAL_SNAPSHOT_FILENAME = "latest_causal_snapshot.json"


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveShadowSnapshotError(f"{field} is required")
    return value


def _decimal_text(value: object, field: str) -> str:
    try:
        decimal = Decimal(str(value))
    except Exception as exc:
        raise LiveShadowSnapshotError(f"{field} must be decimal") from exc
    if not decimal.is_finite() or decimal < 0:
        raise LiveShadowSnapshotError(f"{field} is invalid")
    return format(decimal, "f")


def _levels(levels: object, field: str) -> list[dict[str, str]]:
    if not isinstance(levels, tuple):
        raise LiveShadowSnapshotError(f"{field} must be immutable levels")
    result = []
    for level in levels:
        price = _decimal_text(getattr(level, "price", None), f"{field}.price")
        quantity = _decimal_text(getattr(level, "quantity", None), f"{field}.quantity")
        if Decimal(price) <= 0 or Decimal(price) > 1 or Decimal(quantity) <= 0:
            raise LiveShadowSnapshotError(f"{field} contains invalid level")
        result.append({"price": price, "quantity": quantity})
    return result


def build_live_shadow_snapshot(*, run_id: str, snapshot_sequence: int,
                               generated_utc: str, generated_monotonic_ns: int,
                               event_ladder, candle, books: Mapping[str, object]) -> dict[str, Any]:
    """Build one coherent state sample without raw payloads or credentials.

    The caller must provide all selected event books from one currently valid
    Kalshi generation.  The snapshot intentionally contains only normalized
    public market state and immutable lineage identifiers.
    """
    if isinstance(snapshot_sequence, bool) or not isinstance(snapshot_sequence, int) or snapshot_sequence < 1:
        raise LiveShadowSnapshotError("snapshot_sequence must be positive")
    if isinstance(generated_monotonic_ns, bool) or not isinstance(generated_monotonic_ns, int) or generated_monotonic_ns < 0:
        raise LiveShadowSnapshotError("generated_monotonic_ns must be nonnegative")
    event_ticker = _text(getattr(event_ladder, "event_ticker", None), "event_ticker")
    markets = tuple(getattr(event_ladder, "markets", ()))
    if not markets:
        raise LiveShadowSnapshotError("event ladder is required")
    expected_tickers = tuple(_text(getattr(market, "market_ticker", None), "market_ticker") for market in markets)
    if set(books) != set(expected_tickers):
        raise LiveShadowSnapshotError("snapshot books must cover the complete event ladder")
    candle_minute_start = getattr(getattr(candle, "minute", None), "minute_start_s", None)
    candle_close = getattr(getattr(candle, "minute", None), "close_price", None)
    candle_receipt_ns = getattr(getattr(candle, "minute", None), "available_monotonic_ns", None)
    candle_received_utc = getattr(getattr(candle, "minute", None), "raw_received_utc", None)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in (candle_minute_start, candle_receipt_ns)):
        raise LiveShadowSnapshotError("completed candle timing is invalid")
    normalized_books = []
    for ticker in expected_tickers:
        state = books[ticker]
        timestamp_ms = getattr(state, "timestamp_ms", None)
        if isinstance(timestamp_ms, bool) or not isinstance(timestamp_ms, int) or timestamp_ms < 0:
            raise LiveShadowSnapshotError("book timestamp is invalid")
        normalized_books.append({
            "market_ticker": ticker,
            "timestamp_ms": timestamp_ms,
            "yes_bids": _levels(getattr(state, "yes_bids", None), "yes_bids"),
            "yes_asks": _levels(getattr(state, "yes_asks", None), "yes_asks"),
        })
    return {
        "schema_version": LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION,
        "run_id": _text(run_id, "run_id"),
        "snapshot_sequence": snapshot_sequence,
        "generated_utc": _text(generated_utc, "generated_utc"),
        "generated_monotonic_ns": generated_monotonic_ns,
        "event": {
            "event_ticker": event_ticker,
            "close_time_utc": _text(getattr(event_ladder, "close_time_utc", None), "close_time_utc"),
            "close_timestamp_ms": int(getattr(event_ladder, "close_timestamp_ms", -1)),
            "markets": [{
                "market_ticker": _text(getattr(market, "market_ticker", None), "market_ticker"),
                "strike": _decimal_text(getattr(market, "strike", None), "market strike"),
                "strike_rank_zero_based": int(getattr(market, "strike_rank_zero_based", -1)),
                "event_market_count": int(getattr(market, "event_market_count", -1)),
                "historical_structural_role": getattr(market, "historical_structural_role", None),
            } for market in markets],
        },
        "completed_coinbase_candle": {
            "minute_start_epoch_s": candle_minute_start,
            "close": _decimal_text(candle_close, "candle close"),
            "received_utc": _text(candle_received_utc, "candle received UTC"),
            "received_monotonic_ns": candle_receipt_ns,
        },
        "books": normalized_books,
    }


def write_live_shadow_snapshot(*, snapshot: Mapping[str, Any], output_path: str | Path) -> None:
    output = Path(output_path)
    if output.name != CANONICAL_SNAPSHOT_FILENAME:
        raise LiveShadowSnapshotError("shadow snapshot must use the canonical filename")
    if snapshot.get("schema_version") != LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION:
        raise LiveShadowSnapshotError("shadow snapshot schema is invalid")
    write_json_atomic(output, dict(snapshot))
