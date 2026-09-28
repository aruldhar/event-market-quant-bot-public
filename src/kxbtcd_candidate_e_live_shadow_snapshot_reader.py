"""Fail-closed reader for the collector's one-way live-shadow snapshots."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import BookLevel, BookState
from .kxbtcd_candidate_e_live_shadow_snapshot import (
    CANONICAL_SNAPSHOT_FILENAME,
    LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION,
)
from .kxbtcd_candidate_e_prospective_live_collector import CoinbaseMinuteClose, EventLadder
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import LadderMarket
from .kxbtcd_candidate_e_v2_rest_candle_readiness import V2BoundRestCandle


class LiveShadowSnapshotReaderError(ValueError):
    pass


@dataclass(frozen=True)
class LiveShadowCausalState:
    run_id: str
    snapshot_sequence: int
    generated_utc: str
    generated_monotonic_ns: int
    event_ladder: EventLadder
    candle: V2BoundRestCandle
    books: Mapping[str, BookState]


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise LiveShadowSnapshotReaderError(f"{field} must be an object")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveShadowSnapshotReaderError(f"{field} is required")
    return value


def _integer(value: object, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or (positive and value == 0):
        raise LiveShadowSnapshotReaderError(f"{field} is invalid")
    return value


def _decimal(value: object, field: str, *, unit: bool = False, positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise LiveShadowSnapshotReaderError(f"{field} is invalid") from exc
    if not result.is_finite() or result < 0 or (positive and result == 0) or (unit and result > 1):
        raise LiveShadowSnapshotReaderError(f"{field} is invalid")
    return result


def _levels(value: object, field: str) -> tuple[BookLevel, ...]:
    if not isinstance(value, list):
        raise LiveShadowSnapshotReaderError(f"{field} must be a list")
    levels = tuple(BookLevel(
        price=_decimal(_mapping(row, field).get("price"), f"{field}.price", unit=True, positive=True),
        quantity=_decimal(_mapping(row, field).get("quantity"), f"{field}.quantity", positive=True),
    ) for row in value)
    prices = tuple(level.price for level in levels)
    if len(set(prices)) != len(prices):
        raise LiveShadowSnapshotReaderError(f"{field} contains duplicate prices")
    return levels


def parse_live_shadow_snapshot(payload: object) -> LiveShadowCausalState:
    root = _mapping(payload, "shadow snapshot")
    if root.get("schema_version") != LIVE_SHADOW_SNAPSHOT_SCHEMA_VERSION:
        raise LiveShadowSnapshotReaderError("shadow snapshot schema is invalid")
    run_id = _text(root.get("run_id"), "run_id")
    sequence = _integer(root.get("snapshot_sequence"), "snapshot_sequence", positive=True)
    event = _mapping(root.get("event"), "event")
    market_rows = event.get("markets")
    if not isinstance(market_rows, list) or not market_rows:
        raise LiveShadowSnapshotReaderError("event markets are required")
    markets = tuple(LadderMarket(
        event_ticker=_text(event.get("event_ticker"), "event_ticker"),
        market_ticker=_text(_mapping(row, "market").get("market_ticker"), "market_ticker"),
        strike=_decimal(_mapping(row, "market").get("strike"), "strike", positive=True),
        strike_rank_zero_based=_integer(_mapping(row, "market").get("strike_rank_zero_based"), "strike rank"),
        event_market_count=_integer(_mapping(row, "market").get("event_market_count"), "event market count", positive=True),
        historical_structural_role=(
            None if _mapping(row, "market").get("historical_structural_role") is None
            else _text(_mapping(row, "market").get("historical_structural_role"), "historical structural role")
        ),
    ) for row in market_rows)
    ladder = EventLadder(
        event_ticker=_text(event.get("event_ticker"), "event_ticker"),
        close_time_utc=_text(event.get("close_time_utc"), "close_time_utc"),
        close_timestamp_ms=_integer(event.get("close_timestamp_ms"), "close timestamp", positive=True),
        markets=markets,
    )
    candle_row = _mapping(root.get("completed_coinbase_candle"), "completed candle")
    minute_start = _integer(candle_row.get("minute_start_epoch_s"), "candle minute start", positive=True)
    candle = V2BoundRestCandle(run_id, CoinbaseMinuteClose(
        minute_start_s=minute_start, minute_end_s=minute_start + 60,
        close_price=_decimal(candle_row.get("close"), "candle close", positive=True),
        available_monotonic_ns=_integer(candle_row.get("received_monotonic_ns"), "candle receipt"),
        raw_received_utc=_text(candle_row.get("received_utc"), "candle received UTC"),
    ))
    book_rows = root.get("books")
    if not isinstance(book_rows, list):
        raise LiveShadowSnapshotReaderError("books must be a list")
    books = {}
    for row in book_rows:
        record = _mapping(row, "book")
        ticker = _text(record.get("market_ticker"), "book market ticker")
        if ticker in books:
            raise LiveShadowSnapshotReaderError("duplicate snapshot book")
        books[ticker] = BookState(
            timestamp_ms=_integer(record.get("timestamp_ms"), "book timestamp"),
            yes_bids=_levels(record.get("yes_bids"), "yes bids"),
            yes_asks=_levels(record.get("yes_asks"), "yes asks"),
        )
    expected = {market.market_ticker for market in markets}
    if set(books) != expected:
        raise LiveShadowSnapshotReaderError("books do not cover the event ladder")
    return LiveShadowCausalState(
        run_id=run_id, snapshot_sequence=sequence,
        generated_utc=_text(root.get("generated_utc"), "generated UTC"),
        generated_monotonic_ns=_integer(root.get("generated_monotonic_ns"), "generated monotonic"),
        event_ladder=ladder, candle=candle, books=books,
    )


def read_live_shadow_snapshot(path: str | Path) -> LiveShadowCausalState:
    source = Path(path)
    if source.name != CANONICAL_SNAPSHOT_FILENAME:
        raise LiveShadowSnapshotReaderError("shadow snapshot filename is invalid")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveShadowSnapshotReaderError("shadow snapshot is unreadable") from exc
    return parse_live_shadow_snapshot(payload)
