"""Checkpoint 21N-P1 Predexon free sub-cent snapshot backfill helpers.

This module is deliberately outcome-blind and strategy-blind.  It defines
validation, raw-envelope, resumability, and ticker-window helpers for the
already-owned 2026-07-10 Predexon paid-tick shard.

No function here reads settlement outcomes, computes Candidate-E probabilities,
calculates P&L, places orders, or invokes a paid Predexon data-purchase endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pyarrow.parquet as pq


SCHEMA_VERSION = "predexon_subcent_backfill_raw_page.v1"
ENDPOINT_PATH = "/v2/kalshi/orderbooks-subcent"
SOURCE_FILTER = "spine"
PAGE_LIMIT = 2000
EXPECTED_DATE_UTC = "2026-07-10"


class PredexonSubcentBackfillError(RuntimeError):
    """Fail-closed error for sub-cent backfill invariants."""


@dataclass(frozen=True)
class TickerWindow:
    ticker: str
    start_time_ms: int
    end_time_ms: int
    paid_tick_row_count: int


@dataclass(frozen=True)
class ResumeState:
    page_count: int
    snapshot_count: int
    complete: bool
    next_pagination_key: str | None
    last_timestamp_ms: int | None


def body_sha256(body_text: str) -> str:
    return sha256(body_text.encode("utf-8")).hexdigest()


def decode_body(body_text: Any) -> dict[str, Any]:
    if not isinstance(body_text, str) or not body_text:
        raise PredexonSubcentBackfillError("raw page body must be non-empty JSON text")
    try:
        value = json.loads(body_text)
    except json.JSONDecodeError as exc:
        raise PredexonSubcentBackfillError("raw page body is not valid JSON") from exc
    if not isinstance(value, dict):
        raise PredexonSubcentBackfillError("decoded body must be an object")
    snapshots = value.get("snapshots")
    pagination = value.get("pagination")
    if not isinstance(snapshots, list):
        raise PredexonSubcentBackfillError("body.snapshots must be a list")
    if not isinstance(pagination, dict):
        raise PredexonSubcentBackfillError("body.pagination must be an object")
    return value


def validate_snapshot(snapshot: Any, *, ticker: str) -> int:
    if not isinstance(snapshot, dict):
        raise PredexonSubcentBackfillError("snapshot must be an object")
    if snapshot.get("ticker") != ticker:
        raise PredexonSubcentBackfillError(
            f"snapshot ticker mismatch: {snapshot.get('ticker')!r} != {ticker!r}"
        )
    try:
        ts = int(snapshot["timestamp"])
        int(snapshot["sequence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PredexonSubcentBackfillError(
            "snapshot timestamp/sequence must be integer-compatible"
        ) from exc

    for side in ("yes_bids", "yes_asks"):
        levels = snapshot.get(side)
        if not isinstance(levels, list):
            raise PredexonSubcentBackfillError(f"snapshot.{side} must be a list")
        for level in levels:
            if not isinstance(level, dict):
                raise PredexonSubcentBackfillError(f"snapshot.{side} level must be object")
            if not isinstance(level.get("price"), str) or not isinstance(level.get("size"), str):
                raise PredexonSubcentBackfillError(
                    f"snapshot.{side} price/size must be exact text"
                )
    source = snapshot.get("source")
    if not isinstance(source, str) or not source:
        raise PredexonSubcentBackfillError("snapshot.source must be non-empty text")
    return ts


def validate_pagination(
    pagination: Mapping[str, Any],
    *,
    snapshot_count: int,
) -> tuple[bool, str | None]:
    try:
        limit = int(pagination.get("limit"))
        count = int(pagination.get("count"))
    except (TypeError, ValueError) as exc:
        raise PredexonSubcentBackfillError(
            "pagination limit/count must be integer-compatible"
        ) from exc
    if limit != PAGE_LIMIT:
        raise PredexonSubcentBackfillError(
            f"pagination limit changed: {limit} != {PAGE_LIMIT}"
        )
    if count != snapshot_count:
        raise PredexonSubcentBackfillError(
            f"pagination count mismatch: {count} != {snapshot_count}"
        )
    has_more = pagination.get("has_more")
    if not isinstance(has_more, bool):
        raise PredexonSubcentBackfillError("pagination.has_more must be boolean")
    key = pagination.get("pagination_key")
    if has_more:
        if not isinstance(key, str) or not key:
            raise PredexonSubcentBackfillError(
                "has_more=true requires non-empty pagination_key"
            )
        return True, key
    if key is not None:
        raise PredexonSubcentBackfillError(
            "has_more=false requires pagination_key=null"
        )
    return False, None


def validate_raw_record(
    record: Mapping[str, Any],
    *,
    ticker: str,
    expected_page_number: int,
) -> tuple[int, bool, str | None, int | None, int | None]:
    if record.get("schema_version") != SCHEMA_VERSION:
        raise PredexonSubcentBackfillError("raw envelope schema mismatch")
    if record.get("ticker") != ticker:
        raise PredexonSubcentBackfillError("raw envelope ticker mismatch")
    if int(record.get("page_number", -1)) != expected_page_number:
        raise PredexonSubcentBackfillError("raw envelope page number is not contiguous")
    if int(record.get("http_status", -1)) != 200:
        raise PredexonSubcentBackfillError("persisted successful page must have HTTP 200")

    body_text = record.get("body")
    if record.get("body_sha256") != body_sha256(body_text):
        raise PredexonSubcentBackfillError("raw envelope body SHA-256 mismatch")

    value = decode_body(body_text)
    timestamps = [validate_snapshot(x, ticker=ticker) for x in value["snapshots"]]
    if timestamps != sorted(timestamps):
        raise PredexonSubcentBackfillError("snapshots within page are not chronological")

    has_more, next_key = validate_pagination(
        value["pagination"], snapshot_count=len(value["snapshots"])
    )
    first_ts = timestamps[0] if timestamps else None
    last_ts = timestamps[-1] if timestamps else None
    return len(value["snapshots"]), has_more, next_key, first_ts, last_ts


def inspect_resume_file(path: Path, *, ticker: str) -> ResumeState:
    if not path.exists():
        return ResumeState(0, 0, False, None, None)

    page_count = 0
    snapshot_count = 0
    next_key: str | None = None
    prior_last_ts: int | None = None
    complete = False

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if complete:
                raise PredexonSubcentBackfillError(
                    f"{path}: data exists after terminal page"
                )
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PredexonSubcentBackfillError(
                    f"{path}:{line_number} invalid JSON"
                ) from exc
            if not isinstance(record, dict):
                raise PredexonSubcentBackfillError(
                    f"{path}:{line_number} raw envelope must be object"
                )

            page_count += 1
            count, has_more, key, first_ts, last_ts = validate_raw_record(
                record,
                ticker=ticker,
                expected_page_number=page_count,
            )
            if prior_last_ts is not None and first_ts is not None and first_ts < prior_last_ts:
                raise PredexonSubcentBackfillError(
                    f"{path}: timestamps moved backward across pages"
                )
            snapshot_count += count
            prior_last_ts = last_ts if last_ts is not None else prior_last_ts
            next_key = key
            complete = not has_more

    return ResumeState(
        page_count=page_count,
        snapshot_count=snapshot_count,
        complete=complete,
        next_pagination_key=next_key,
        last_timestamp_ms=prior_last_ts,
    )


def append_raw_record(path: Path, record: Mapping[str, Any]) -> None:
    """Append one already-captured raw response and fsync it before parsing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        dict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ) + "\n"
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(payload)
        handle.flush()
        import os
        os.fsync(handle.fileno())


def paid_ticker_windows(parquet_path: Path) -> tuple[TickerWindow, ...]:
    if not parquet_path.is_file():
        raise PredexonSubcentBackfillError(f"paid tick shard missing: {parquet_path}")

    pf = pq.ParquetFile(parquet_path)
    stats: dict[str, list[int]] = {}
    for batch in pf.iter_batches(columns=["ticker", "timestamp"], batch_size=131072):
        tickers = batch.column(0).to_pylist()
        timestamps = batch.column(1).to_pylist()
        for ticker_raw, ts_raw in zip(tickers, timestamps):
            if ticker_raw is None or ts_raw is None:
                raise PredexonSubcentBackfillError("paid tick ticker/timestamp cannot be null")
            ticker = str(ticker_raw)
            if not ticker.startswith("KXBTCD-"):
                continue
            ts = int(ts_raw)
            slot = stats.get(ticker)
            if slot is None:
                stats[ticker] = [ts, ts, 1]
            else:
                if ts < slot[0]:
                    slot[0] = ts
                if ts > slot[1]:
                    slot[1] = ts
                slot[2] += 1

    windows = tuple(
        TickerWindow(
            ticker=ticker,
            start_time_ms=values[0],
            end_time_ms=values[1],
            paid_tick_row_count=values[2],
        )
        for ticker, values in sorted(stats.items())
    )
    if len(windows) != 623:
        raise PredexonSubcentBackfillError(
            f"expected exactly 623 owned KXBTCD tickers, got {len(windows)}"
        )
    if sum(w.paid_tick_row_count for w in windows) != 5_644_964:
        raise PredexonSubcentBackfillError(
            "paid shard row count changed from frozen 5,644,964"
        )
    return windows
