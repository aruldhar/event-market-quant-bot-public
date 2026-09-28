"""Raw-first, resumable collector for the frozen Candidate-E execution archive.

Checkpoint 21K-B2 is read-only.  The immutable Kalshi raw JSONL archive remains
the source of truth; a local SQLite database is only a transactional resume
index and normalized working cache.

No strategy P&L is calculated here.  No orders, cancellations, transfers,
paper execution, demo execution, or real-money execution exist in this module.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .kxbtcd_candidate_e_execution_archive_predeclaration import (
    EXPECTED_ALLOWLIST_FINGERPRINT,
    EXPECTED_ARCHIVE_FINGERPRINT,
    EXPECTED_EVENTS,
    EXPECTED_MARKETS,
    EXPECTED_ROWS,
    recompute_allowlist,
)

ARCHIVE_ID = "kxbtcd_candidate_e_reusable_execution_archive.v1"
SERIES_TICKER = "KXBTCD"
DEFAULT_MARKET_BATCH_SIZE = 20
DEFAULT_TRADE_PAGE_LIMIT = 1000
DEFAULT_MAX_TRADE_PAGES = 100
DEFAULT_MAX_CURSOR_PAGES = 100
DEFAULT_MAX_CANDLE_PERIODS_PER_REQUEST = 5000
DEFAULT_CUTOFF_REFRESH_MARKETS = 250

ALLOWED_GET_PATH_PREFIXES = (
    "/historical/cutoff",
    "/historical/markets",
    "/historical/trades",
    "/markets",
    "/events",
    "/series",
)
FORBIDDEN_PATH_FRAGMENTS = (
    "/portfolio",
    "/orders",
    "/order_groups",
    "/communications",
    "/transfers",
)


class ExecutionArchiveCollectionError(RuntimeError):
    """Raised when the frozen archive cannot be collected without ambiguity."""


class RawRef(Protocol):
    source: str
    session_id: str
    request_id: str


class JsonResponse(Protocol):
    payload: Any
    raw_record: RawRef


class JsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        top_level_container: str = "object",
    ) -> JsonResponse: ...


@dataclass(frozen=True)
class Cutoffs:
    market_settled_ts: datetime
    trades_created_ts: datetime
    orders_updated_ts: datetime
    market_positions_last_updated_ts: datetime | None


@dataclass(frozen=True)
class ArchiveScope:
    scope_id: str
    allowlist: tuple[dict[str, str], ...]
    events: tuple[str, ...]
    markets: tuple[str, ...]
    event_by_market: dict[str, str]
    stage_by_market: dict[str, str]
    is_full: bool


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionArchiveCollectionError(f"{field} must be non-empty RFC3339 text")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionArchiveCollectionError(f"{field} is not valid RFC3339: {value!r}") from exc
    if dt.tzinfo is None:
        raise ExecutionArchiveCollectionError(f"{field} must include timezone")
    return dt.astimezone(timezone.utc)


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionArchiveCollectionError(f"{field} must be non-empty text")
    return value.strip()


def _text_or_blank(value: Any) -> str:
    return "" if value is None else str(value)


def _raw_lineage(response: JsonResponse) -> dict[str, str]:
    return {
        "raw_source": response.raw_record.source,
        "raw_session_id": response.raw_record.session_id,
        "raw_request_id": response.raw_record.request_id,
    }


def load_frozen_scope(
    repository_root: str | Path = ".",
    *,
    max_markets: int | None = None,
) -> ArchiveScope:
    rows, _stats = recompute_allowlist(repository_root)
    observed = _sha256_json(rows)
    if observed != EXPECTED_ALLOWLIST_FINGERPRINT:
        raise ExecutionArchiveCollectionError(
            f"allow-list fingerprint changed: {observed} != {EXPECTED_ALLOWLIST_FINGERPRINT}"
        )
    if len(rows) != EXPECTED_MARKETS:
        raise ExecutionArchiveCollectionError(
            f"allow-list market count changed: {len(rows)} != {EXPECTED_MARKETS}"
        )
    if max_markets is not None and max_markets <= 0:
        raise ValueError("max_markets must be positive when supplied")

    selected = rows if max_markets is None else rows[:max_markets]
    event_by_market: dict[str, str] = {}
    stage_by_market: dict[str, str] = {}
    for row in selected:
        ticker = row["market_ticker"]
        event = row["event_ticker"]
        stage = row["stage"]
        if ticker in event_by_market:
            raise ExecutionArchiveCollectionError(f"duplicate market in selected scope: {ticker}")
        event_by_market[ticker] = event
        stage_by_market[ticker] = stage

    events = tuple(sorted(set(event_by_market.values())))
    markets = tuple(sorted(event_by_market))
    full = max_markets is None
    scope_id = "full" if full else f"smoke_{len(markets)}"
    if full:
        if len(events) != EXPECTED_EVENTS or len(markets) != EXPECTED_MARKETS:
            raise ExecutionArchiveCollectionError("full scope aggregate counts changed")
    return ArchiveScope(
        scope_id=scope_id,
        allowlist=tuple(selected),
        events=events,
        markets=markets,
        event_by_market=event_by_market,
        stage_by_market=stage_by_market,
        is_full=full,
    )


class ResumeStore:
    """Transactional resume cache.

    Raw HTTP JSONL files remain source-of-truth.  This database merely records
    complete, validated tasks and their normalized payloads so interrupted
    collection can resume without replaying already-complete requests.
    """

    LEGACY_SCHEMA_VERSION = "kxbtcd_execution_archive_resume.v1"
    SCHEMA_VERSION = "kxbtcd_execution_archive_resume.v2"

    def __init__(
        self,
        path: str | Path,
        *,
        scope_id: str,
        archive_fingerprint: str = EXPECTED_ARCHIVE_FINGERPRINT,
        allowlist_fingerprint: str = EXPECTED_ALLOWLIST_FINGERPRINT,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS archive_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS archive_task (
                task_key TEXT PRIMARY KEY,
                task_kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                completed_at_utc TEXT NOT NULL
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS archive_raw_session (
                source TEXT NOT NULL,
                session_id TEXT NOT NULL,
                first_task_key TEXT NOT NULL,
                PRIMARY KEY(source, session_id)
            )
            """
        )
        self.conn.commit()

        schema = self._meta_get("schema_version")
        if schema is None:
            self.conn.execute(
                "INSERT INTO archive_meta(key,value) VALUES (?,?)",
                ("schema_version", self.SCHEMA_VERSION),
            )
        elif schema == self.LEGACY_SCHEMA_VERSION:
            self._backfill_raw_sessions()
            self.conn.execute(
                "UPDATE archive_meta SET value=? WHERE key='schema_version'",
                (self.SCHEMA_VERSION,),
            )
        elif schema != self.SCHEMA_VERSION:
            raise ExecutionArchiveCollectionError(
                f"resume database schema_version mismatch: {schema!r} "
                f"not in {{{self.LEGACY_SCHEMA_VERSION!r}, {self.SCHEMA_VERSION!r}}}"
            )

        expected = {
            "archive_id": ARCHIVE_ID,
            "archive_fingerprint": archive_fingerprint,
            "allowlist_fingerprint": allowlist_fingerprint,
            "scope_id": scope_id,
        }
        for key, value in expected.items():
            existing = self._meta_get(key)
            if existing is None:
                self.conn.execute(
                    "INSERT INTO archive_meta(key,value) VALUES (?,?)",
                    (key, value),
                )
            elif existing != value:
                raise ExecutionArchiveCollectionError(
                    f"resume database {key} mismatch: {existing!r} != {value!r}"
                )
        self.conn.commit()
        self._backfill_raw_sessions()

    def _meta_get(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM archive_meta WHERE key=?", (key,)
        ).fetchone()
        return None if row is None else str(row[0])

    @staticmethod
    def _extract_raw_sessions(value: Any) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()

        def visit(item: Any) -> None:
            if isinstance(item, Mapping):
                source = item.get("raw_source")
                session = item.get("raw_session_id")
                request = item.get("raw_request_id")
                if (
                    isinstance(source, str)
                    and source.strip()
                    and isinstance(session, str)
                    and session.strip()
                    and isinstance(request, str)
                    and request.strip()
                ):
                    found.add((source.strip(), session.strip()))
                for child in item.values():
                    visit(child)
            elif isinstance(item, list):
                for child in item:
                    visit(child)

        visit(value)
        return found

    def _record_raw_sessions(self, task_key: str, payload: Mapping[str, Any]) -> None:
        for source, session_id in sorted(self._extract_raw_sessions(payload)):
            self.conn.execute(
                """
                INSERT OR IGNORE INTO archive_raw_session(
                    source,session_id,first_task_key
                ) VALUES (?,?,?)
                """,
                (source, session_id, task_key),
            )

    def _backfill_raw_sessions(self) -> None:
        rows = self.conn.execute(
            "SELECT task_key,payload_json,payload_sha256 FROM archive_task"
        ).fetchall()
        with self.conn:
            for task_key, payload_json, digest in rows:
                encoded = str(payload_json)
                observed = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                if observed != str(digest):
                    raise ExecutionArchiveCollectionError(
                        f"resume payload digest mismatch for {task_key}"
                    )
                value = json.loads(encoded)
                if not isinstance(value, dict):
                    raise ExecutionArchiveCollectionError(
                        f"resume payload for {task_key} must be an object"
                    )
                self._record_raw_sessions(str(task_key), value)

    def raw_sessions(self) -> tuple[dict[str, str], ...]:
        rows = self.conn.execute(
            """
            SELECT source,session_id
            FROM archive_raw_session
            ORDER BY source,session_id
            """
        ).fetchall()
        return tuple(
            {"source": str(source), "session_id": str(session_id)}
            for source, session_id in rows
        )

    def has(self, task_key: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM archive_task WHERE task_key=?", (task_key,)
            ).fetchone()
            is not None
        )

    def get(self, task_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload_json,payload_sha256 FROM archive_task WHERE task_key=?",
            (task_key,),
        ).fetchone()
        if row is None:
            return None
        payload_json, digest = str(row[0]), str(row[1])
        observed = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        if observed != digest:
            raise ExecutionArchiveCollectionError(
                f"resume payload digest mismatch for {task_key}"
            )
        value = json.loads(payload_json)
        if not isinstance(value, dict):
            raise ExecutionArchiveCollectionError(
                f"resume payload for {task_key} must be an object"
            )
        return value

    def put(self, task_key: str, task_kind: str, payload: Mapping[str, Any]) -> None:
        encoded = _canonical_json(dict(payload))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        existing = self.conn.execute(
            "SELECT task_kind,payload_sha256 FROM archive_task WHERE task_key=?",
            (task_key,),
        ).fetchone()
        if existing is not None:
            if str(existing[0]) != task_kind or str(existing[1]) != digest:
                raise ExecutionArchiveCollectionError(
                    f"completed resume task changed: {task_key}"
                )
            with self.conn:
                self._record_raw_sessions(task_key, payload)
            return
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO archive_task(
                    task_key,task_kind,payload_json,payload_sha256,completed_at_utc
                ) VALUES (?,?,?,?,?)
                """,
                (task_key, task_kind, encoded, digest, _utc_now_text()),
            )
            self._record_raw_sessions(task_key, payload)

    def values(self, task_kind: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT task_key,payload_json,payload_sha256
            FROM archive_task
            WHERE task_kind=?
            ORDER BY task_key
            """,
            (task_kind,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for key, payload_json, digest in rows:
            encoded = str(payload_json)
            if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != str(digest):
                raise ExecutionArchiveCollectionError(
                    f"resume payload digest mismatch for {key}"
                )
            value = json.loads(encoded)
            if not isinstance(value, dict):
                raise ExecutionArchiveCollectionError(f"invalid resume payload for {key}")
            result.append(value)
        return result

    def count(self, task_kind: str | None = None) -> int:
        if task_kind is None:
            return int(self.conn.execute("SELECT COUNT(*) FROM archive_task").fetchone()[0])
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM archive_task WHERE task_kind=?", (task_kind,)
            ).fetchone()[0]
        )

    def close(self) -> None:
        self.conn.close()


class PacedClient:
    """Small wrapper adding conservative spacing between successful reads."""

    def __init__(
        self,
        client: JsonClient,
        *,
        delay_seconds: float,
        sleep_fn=time.sleep,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be nonnegative")
        self.client = client
        self.delay_seconds = delay_seconds
        self.sleep_fn = sleep_fn

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        top_level_container: str = "object",
    ) -> JsonResponse:
        _assert_read_only_path(path)
        result = self.client.get_json(
            path, params=params, top_level_container=top_level_container
        )
        if self.delay_seconds:
            self.sleep_fn(self.delay_seconds)
        return result


def _assert_read_only_path(path: str) -> None:
    if not path.startswith("/"):
        raise ExecutionArchiveCollectionError("API path must start with '/'")
    if any(fragment in path for fragment in FORBIDDEN_PATH_FRAGMENTS):
        raise ExecutionArchiveCollectionError(f"forbidden write/account path: {path}")
    if not any(path.startswith(prefix) for prefix in ALLOWED_GET_PATH_PREFIXES):
        raise ExecutionArchiveCollectionError(f"unapproved archive GET path: {path}")


def fetch_cutoffs(client: JsonClient) -> dict[str, Any]:
    response = client.get_json("/historical/cutoff")
    payload = response.payload
    if not isinstance(payload, Mapping):
        raise ExecutionArchiveCollectionError("historical cutoff response must be object")
    required = ("market_settled_ts", "trades_created_ts", "orders_updated_ts")
    parsed: dict[str, datetime | None] = {}
    for key in required:
        parsed[key] = _parse_utc(payload.get(key), f"cutoff.{key}")
    optional = payload.get("market_positions_last_updated_ts")
    parsed["market_positions_last_updated_ts"] = (
        None if optional in (None, "") else _parse_utc(optional, "cutoff.market_positions_last_updated_ts")
    )
    return {
        "market_settled_ts": parsed["market_settled_ts"].isoformat(),
        "trades_created_ts": parsed["trades_created_ts"].isoformat(),
        "orders_updated_ts": parsed["orders_updated_ts"].isoformat(),
        "market_positions_last_updated_ts": (
            "" if parsed["market_positions_last_updated_ts"] is None
            else parsed["market_positions_last_updated_ts"].isoformat()
        ),
        **_raw_lineage(response),
    }


def cutoffs_from_payload(payload: Mapping[str, Any]) -> Cutoffs:
    optional = payload.get("market_positions_last_updated_ts")
    return Cutoffs(
        market_settled_ts=_parse_utc(payload.get("market_settled_ts"), "cutoff.market_settled_ts"),
        trades_created_ts=_parse_utc(payload.get("trades_created_ts"), "cutoff.trades_created_ts"),
        orders_updated_ts=_parse_utc(payload.get("orders_updated_ts"), "cutoff.orders_updated_ts"),
        market_positions_last_updated_ts=(
            None if optional in (None, "") else _parse_utc(optional, "cutoff.market_positions_last_updated_ts")
        ),
    )


def fetch_series_bundle(client: JsonClient) -> dict[str, Any]:
    series_response = client.get_json(f"/series/{SERIES_TICKER}")
    if not isinstance(series_response.payload, Mapping):
        raise ExecutionArchiveCollectionError("series response must be object")
    series = series_response.payload.get("series")
    if not isinstance(series, Mapping):
        raise ExecutionArchiveCollectionError("series.series must be object")
    if _required_text(series.get("ticker"), "series.ticker") != SERIES_TICKER:
        raise ExecutionArchiveCollectionError("series ticker mismatch")

    fee_response = client.get_json(
        "/series/fee_changes",
        params={"series_ticker": SERIES_TICKER, "show_historical": "true"},
    )
    if not isinstance(fee_response.payload, Mapping):
        raise ExecutionArchiveCollectionError("series fee response must be object")
    changes = fee_response.payload.get("series_fee_change_arr")
    if not isinstance(changes, list):
        raise ExecutionArchiveCollectionError("series_fee_change_arr must be list")
    normalized_changes: list[dict[str, Any]] = []
    for index, row in enumerate(changes):
        if not isinstance(row, Mapping):
            raise ExecutionArchiveCollectionError(f"series fee change {index} must be object")
        ticker = _required_text(row.get("series_ticker"), f"series_fee[{index}].series_ticker")
        if ticker != SERIES_TICKER:
            raise ExecutionArchiveCollectionError("series fee ticker mismatch")
        normalized_changes.append({**dict(row), **_raw_lineage(fee_response)})
    return {
        "series": {**dict(series), **_raw_lineage(series_response)},
        "fee_changes": normalized_changes,
    }


def _paginate(
    client: JsonClient,
    *,
    path: str,
    params: Mapping[str, Any],
    container: str,
    max_pages: int,
) -> list[tuple[Mapping[str, Any], JsonResponse]]:
    if max_pages <= 0:
        raise ValueError("max_pages must be positive")
    cursor = ""
    seen_cursors: set[str] = set()
    result: list[tuple[Mapping[str, Any], JsonResponse]] = []
    for _ in range(max_pages):
        page_params = dict(params)
        if cursor:
            page_params["cursor"] = cursor
        response = client.get_json(path, params=page_params)
        if not isinstance(response.payload, Mapping):
            raise ExecutionArchiveCollectionError(f"{path} response must be object")
        items = response.payload.get(container)
        if not isinstance(items, list):
            raise ExecutionArchiveCollectionError(f"{path}.{container} must be list")
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise ExecutionArchiveCollectionError(
                    f"{path}.{container}[{index}] must be object"
                )
            result.append((item, response))
        next_cursor = response.payload.get("cursor", "")
        if next_cursor is None:
            next_cursor = ""
        if not isinstance(next_cursor, str):
            raise ExecutionArchiveCollectionError(f"{path}.cursor must be text")
        if not next_cursor:
            return result
        if next_cursor in seen_cursors:
            raise ExecutionArchiveCollectionError(
                f"cursor loop detected for {path}: {next_cursor!r}"
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise ExecutionArchiveCollectionError(
        f"{path} still had cursor after max_pages={max_pages}"
    )


def fetch_event_bundle(
    client: JsonClient,
    *,
    event_ticker: str,
    max_pages: int = DEFAULT_MAX_CURSOR_PAGES,
) -> dict[str, Any]:
    response = client.get_json(f"/events/{event_ticker}")
    if not isinstance(response.payload, Mapping):
        raise ExecutionArchiveCollectionError("event response must be object")
    event = response.payload.get("event")
    if not isinstance(event, Mapping):
        raise ExecutionArchiveCollectionError("event.event must be object")
    if _required_text(event.get("event_ticker"), "event.event_ticker") != event_ticker:
        raise ExecutionArchiveCollectionError("event ticker mismatch")
    if _required_text(event.get("series_ticker"), "event.series_ticker") != SERIES_TICKER:
        raise ExecutionArchiveCollectionError(
            f"event {event_ticker} is not in {SERIES_TICKER}"
        )
    fee_pages = _paginate(
        client,
        path="/events/fee_changes",
        params={"event_ticker": event_ticker, "limit": 1000},
        container="event_fee_changes",
        max_pages=max_pages,
    )
    changes: list[dict[str, Any]] = []
    for item, fee_response in fee_pages:
        if _required_text(item.get("event_ticker"), "event_fee.event_ticker") != event_ticker:
            raise ExecutionArchiveCollectionError("event fee ticker mismatch")
        changes.append({**dict(item), **_raw_lineage(fee_response)})
    return {
        "event": {**dict(event), **_raw_lineage(response)},
        "fee_changes": changes,
    }


def _fetch_market_tier_pages(
    client: JsonClient,
    *,
    tier: str,
    tickers: Sequence[str],
    max_pages: int = 10,
) -> list[tuple[Mapping[str, Any], JsonResponse]]:
    if tier not in {"historical", "live"}:
        raise ValueError("tier must be historical or live")
    path = "/historical/markets" if tier == "historical" else "/markets"
    return _paginate(
        client,
        path=path,
        params={"tickers": ",".join(tickers), "limit": 1000},
        container="markets",
        max_pages=max_pages,
    )


def fetch_market_metadata_batch(
    client: JsonClient,
    *,
    tickers: Sequence[str],
    expected_event_by_market: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    requested = tuple(tickers)
    if not requested:
        return {}
    if len(set(requested)) != len(requested):
        raise ExecutionArchiveCollectionError("metadata batch contains duplicate ticker")
    allowed = set(requested)
    observed: dict[str, list[tuple[str, Mapping[str, Any], JsonResponse]]] = {
        ticker: [] for ticker in requested
    }
    for tier in ("historical", "live"):
        for market, response in _fetch_market_tier_pages(
            client, tier=tier, tickers=requested
        ):
            ticker = _required_text(market.get("ticker"), "market.ticker")
            if ticker not in allowed:
                raise ExecutionArchiveCollectionError(
                    f"market metadata returned out-of-batch ticker {ticker}"
                )
            observed[ticker].append((tier, market, response))

    result: dict[str, dict[str, Any]] = {}
    for ticker in requested:
        hits = observed[ticker]
        if len(hits) != 1:
            raise ExecutionArchiveCollectionError(
                f"market {ticker} must resolve to exactly one tier; observed {len(hits)}"
            )
        tier, market, response = hits[0]
        event_ticker = _required_text(market.get("event_ticker"), "market.event_ticker")
        expected_event = expected_event_by_market.get(ticker)
        if event_ticker != expected_event:
            raise ExecutionArchiveCollectionError(
                f"market {ticker} event mismatch: {event_ticker} != {expected_event}"
            )
        open_dt = _parse_utc(market.get("open_time"), "market.open_time")
        close_dt = _parse_utc(market.get("close_time"), "market.close_time")
        if not open_dt < close_dt:
            raise ExecutionArchiveCollectionError(
                f"market {ticker} requires open_time < close_time"
            )
        settlement_text = _text_or_blank(market.get("settlement_ts"))
        result[ticker] = {
            "ticker": ticker,
            "event_ticker": event_ticker,
            "observed_route_tier": tier,
            "open_time": open_dt.isoformat(),
            "close_time": close_dt.isoformat(),
            "settlement_ts": settlement_text,
            "status": _text_or_blank(market.get("status")),
            "market_type": _text_or_blank(market.get("market_type")),
            "price_level_structure": _text_or_blank(market.get("price_level_structure")),
            "floor_strike": _text_or_blank(market.get("floor_strike")),
            "cap_strike": _text_or_blank(market.get("cap_strike")),
            "functional_strike": _text_or_blank(market.get("functional_strike")),
            "settlement_value_dollars": _text_or_blank(market.get("settlement_value_dollars")),
            "volume_fp": _decimal_text(market.get("volume_fp"), "market.volume_fp"),
            **_raw_lineage(response),
        }
    return result


def effective_market_route(metadata: Mapping[str, Any], cutoffs: Cutoffs) -> str:
    settlement = metadata.get("settlement_ts")
    if isinstance(settlement, str) and settlement.strip():
        settlement_dt = _parse_utc(settlement, "market.settlement_ts")
        return "historical" if settlement_dt < cutoffs.market_settled_ts else "live"
    route = metadata.get("observed_route_tier")
    if route not in {"historical", "live"}:
        raise ExecutionArchiveCollectionError("market route unresolved")
    return str(route)


def _decimal_text(value: Any, field: str) -> str:
    if value is None or value == "":
        return ""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ExecutionArchiveCollectionError(f"{field} must be decimal text") from exc
    if not dec.is_finite():
        raise ExecutionArchiveCollectionError(f"{field} must be finite")
    return format(dec, "f")


def _nested_price(
    candle: Mapping[str, Any],
    family: str,
    field: str,
    component: str,
) -> str:
    obj = candle.get(field)
    if obj is None:
        return ""
    if not isinstance(obj, Mapping):
        raise ExecutionArchiveCollectionError(f"candle.{field} must be object/null")
    suffix = "" if family == "historical" else "_dollars"
    return _decimal_text(obj.get(component + suffix), f"candle.{field}.{component}{suffix}")


def normalize_candles(
    response: JsonResponse,
    *,
    ticker: str,
    route_tier: str,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    if not isinstance(response.payload, Mapping):
        raise ExecutionArchiveCollectionError("candle response must be object")
    if _required_text(response.payload.get("ticker"), "candles.ticker") != ticker:
        raise ExecutionArchiveCollectionError("candle ticker mismatch")
    candles = response.payload.get("candlesticks")
    if not isinstance(candles, list):
        raise ExecutionArchiveCollectionError("candlesticks must be list")
    family = "historical" if route_tier == "historical" else "live"
    volume_key = "volume" if family == "historical" else "volume_fp"
    oi_key = "open_interest" if family == "historical" else "open_interest_fp"
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise ExecutionArchiveCollectionError(f"candles[{index}] must be object")
        end_period_ts = candle.get("end_period_ts")
        if not isinstance(end_period_ts, int) or isinstance(end_period_ts, bool):
            raise ExecutionArchiveCollectionError("candle.end_period_ts must be integer")
        if not start_ts <= end_period_ts <= end_ts:
            raise ExecutionArchiveCollectionError(
                f"candle {end_period_ts} outside requested [{start_ts},{end_ts}]"
            )
        if end_period_ts in seen:
            raise ExecutionArchiveCollectionError(
                f"duplicate candle end_period_ts {end_period_ts} for {ticker}"
            )
        seen.add(end_period_ts)
        row: dict[str, Any] = {
            "market_ticker": ticker,
            "route_tier": route_tier,
            "end_period_ts": end_period_ts,
            "volume_fp": _decimal_text(candle.get(volume_key), f"candle.{volume_key}"),
            "open_interest_fp": _decimal_text(candle.get(oi_key), f"candle.{oi_key}"),
            **_raw_lineage(response),
        }
        for field in ("yes_bid", "yes_ask"):
            for component in ("open", "low", "high", "close"):
                row[f"{field}_{component}_dollars"] = _nested_price(
                    candle, family, field, component
                )
        for component in ("open", "low", "high", "close", "mean", "previous"):
            row[f"price_{component}_dollars"] = _nested_price(
                candle, family, "price", component
            )
        rows.append(row)
    rows.sort(key=lambda item: int(item["end_period_ts"]))
    return rows


def _candle_request_windows(
    start_ts: int,
    end_ts: int,
    *,
    max_periods: int = DEFAULT_MAX_CANDLE_PERIODS_PER_REQUEST,
) -> tuple[tuple[int, int], ...]:
    if max_periods <= 0:
        raise ValueError("max_periods must be positive")
    if start_ts >= end_ts:
        raise ExecutionArchiveCollectionError(
            "candle lifecycle requires start_ts < end_ts"
        )

    max_span_seconds = max_periods * 60
    windows: list[tuple[int, int]] = []
    window_start = start_ts

    while window_start < end_ts:
        window_end = min(end_ts, window_start + max_span_seconds)
        windows.append((window_start, window_end))
        if window_end >= end_ts:
            break
        window_start = window_end

    return tuple(windows)


def _merge_candle_rows(
    *,
    ticker: str,
    chunks: Sequence[Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    by_period: dict[int, dict[str, Any]] = {}
    lineage_fields = {"raw_source", "raw_session_id", "raw_request_id"}

    for rows in chunks:
        for raw_row in rows:
            row = dict(raw_row)
            end_period_ts = row.get("end_period_ts")
            if not isinstance(end_period_ts, int) or isinstance(end_period_ts, bool):
                raise ExecutionArchiveCollectionError(
                    "normalized candle end_period_ts must be integer"
                )

            existing = by_period.get(end_period_ts)
            if existing is None:
                by_period[end_period_ts] = row
                continue

            compare_fields = (set(existing) | set(row)) - lineage_fields
            if any(
                existing.get(field) != row.get(field)
                for field in compare_fields
            ):
                raise ExecutionArchiveCollectionError(
                    f"inconsistent duplicate candle end_period_ts "
                    f"{end_period_ts} for {ticker}"
                )

    return [by_period[key] for key in sorted(by_period)]


def fetch_candles(
    client: JsonClient,
    *,
    metadata: Mapping[str, Any],
    cutoffs: Cutoffs,
    max_periods_per_request: int = DEFAULT_MAX_CANDLE_PERIODS_PER_REQUEST,
) -> dict[str, Any]:
    ticker = _required_text(metadata.get("ticker"), "metadata.ticker")
    open_dt = _parse_utc(metadata.get("open_time"), "metadata.open_time")
    close_dt = _parse_utc(metadata.get("close_time"), "metadata.close_time")
    start_ts = int(open_dt.timestamp())
    end_ts = int(close_dt.timestamp())
    route = effective_market_route(metadata, cutoffs)
    path = (
        f"/historical/markets/{ticker}/candlesticks"
        if route == "historical"
        else f"/series/{SERIES_TICKER}/markets/{ticker}/candlesticks"
    )

    windows = _candle_request_windows(
        start_ts,
        end_ts,
        max_periods=max_periods_per_request,
    )

    normalized_chunks: list[list[dict[str, Any]]] = []
    request_windows: list[dict[str, Any]] = []

    for window_start, window_end in windows:
        response = client.get_json(
            path,
            params={
                "start_ts": window_start,
                "end_ts": window_end,
                "period_interval": 1,
            },
        )

        normalized_chunks.append(
            normalize_candles(
                response,
                ticker=ticker,
                route_tier=route,
                start_ts=window_start,
                end_ts=window_end,
            )
        )

        request_windows.append(
            {
                "start_ts": window_start,
                "end_ts": window_end,
                **_raw_lineage(response),
            }
        )

    rows = _merge_candle_rows(
        ticker=ticker,
        chunks=normalized_chunks,
    )

    return {
        "ticker": ticker,
        "route_tier": route,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "request_count": len(request_windows),
        "request_windows": request_windows,
        "rows": rows,
    }

def trade_routes_for_window(
    open_dt: datetime,
    close_dt: datetime,
    cutoffs: Cutoffs,
) -> tuple[str, ...]:
    cutoff = cutoffs.trades_created_ts
    if close_dt < cutoff:
        return ("historical",)
    if open_dt > cutoff:
        return ("live",)
    return ("historical", "live")


def _normalize_trade(
    trade: Mapping[str, Any],
    *,
    response: JsonResponse,
    expected_ticker: str,
    route_tier: str,
) -> dict[str, Any]:
    ticker = _required_text(trade.get("ticker"), "trade.ticker")
    if ticker != expected_ticker:
        raise ExecutionArchiveCollectionError(
            f"trade ticker mismatch {ticker} != {expected_ticker}"
        )
    trade_id = _required_text(trade.get("trade_id"), "trade.trade_id")
    return {
        "trade_id": trade_id,
        "market_ticker": ticker,
        "route_tier": route_tier,
        "created_time": _required_text(trade.get("created_time"), "trade.created_time"),
        "count_fp": _decimal_text(trade.get("count_fp"), "trade.count_fp"),
        "yes_price_dollars": _decimal_text(
            trade.get("yes_price_dollars"), "trade.yes_price_dollars"
        ),
        "no_price_dollars": _decimal_text(
            trade.get("no_price_dollars"), "trade.no_price_dollars"
        ),
        "taker_side": _text_or_blank(trade.get("taker_side")),
        "taker_outcome_side": _text_or_blank(trade.get("taker_outcome_side")),
        "taker_book_side": _text_or_blank(trade.get("taker_book_side")),
        "is_block_trade": _text_or_blank(trade.get("is_block_trade")),
        **_raw_lineage(response),
    }


def fetch_trades(
    client: JsonClient,
    *,
    metadata: Mapping[str, Any],
    cutoffs: Cutoffs,
    max_pages: int = DEFAULT_MAX_TRADE_PAGES,
) -> dict[str, Any]:
    ticker = _required_text(metadata.get("ticker"), "metadata.ticker")
    open_dt = _parse_utc(metadata.get("open_time"), "metadata.open_time")
    close_dt = _parse_utc(metadata.get("close_time"), "metadata.close_time")
    lifecycle_min_ts = int(open_dt.timestamp())
    lifecycle_max_ts = int(close_dt.timestamp())
    # Docs describe min_ts/max_ts as "after"/"before" filters without spelling
    # out boundary inclusivity. Query a one-second cushion, then filter locally
    # to the exact lifecycle so trades exactly at open/close cannot be lost.
    min_ts = lifecycle_min_ts - 1
    max_ts = lifecycle_max_ts + 1
    routes = trade_routes_for_window(open_dt, close_dt, cutoffs)
    by_id: dict[str, dict[str, Any]] = {}
    duplicate_count = 0

    for route in routes:
        path = "/historical/trades" if route == "historical" else "/markets/trades"
        pages = _paginate(
            client,
            path=path,
            params={
                "ticker": ticker,
                "min_ts": min_ts,
                "max_ts": max_ts,
                "limit": DEFAULT_TRADE_PAGE_LIMIT,
            },
            container="trades",
            max_pages=max_pages,
        )
        for trade, response in pages:
            normalized = _normalize_trade(
                trade,
                response=response,
                expected_ticker=ticker,
                route_tier=route,
            )
            created_dt = _parse_utc(normalized["created_time"], "trade.created_time")
            if created_dt < open_dt or created_dt > close_dt:
                continue
            trade_id = normalized["trade_id"]
            existing = by_id.get(trade_id)
            if existing is not None:
                duplicate_count += 1
                compare_fields = (
                    "market_ticker",
                    "created_time",
                    "count_fp",
                    "yes_price_dollars",
                    "no_price_dollars",
                )
                if any(existing[k] != normalized[k] for k in compare_fields):
                    raise ExecutionArchiveCollectionError(
                        f"inconsistent duplicate trade_id {trade_id}"
                    )
                continue
            by_id[trade_id] = normalized

    rows = sorted(
        by_id.values(),
        key=lambda row: (row["created_time"], row["trade_id"]),
    )
    return {
        "ticker": ticker,
        "routes": list(routes),
        "min_ts": lifecycle_min_ts,
        "max_ts": lifecycle_max_ts,
        "request_min_ts": min_ts,
        "request_max_ts": max_ts,
        "duplicate_trade_ids_removed": duplicate_count,
        "rows": rows,
    }


def _atomic_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


ALLOWLIST_FIELDS = ("stage", "event_ticker", "market_ticker")
MARKET_FIELDS = (
    "stage", "ticker", "event_ticker", "observed_route_tier", "open_time",
    "close_time", "settlement_ts", "status", "market_type",
    "price_level_structure", "floor_strike", "cap_strike", "functional_strike",
    "settlement_value_dollars", "volume_fp", "raw_source", "raw_session_id", "raw_request_id",
)
CANDLE_FIELDS = (
    "stage", "event_ticker", "market_ticker", "route_tier", "end_period_ts",
    "yes_bid_open_dollars", "yes_bid_low_dollars", "yes_bid_high_dollars",
    "yes_bid_close_dollars", "yes_ask_open_dollars", "yes_ask_low_dollars",
    "yes_ask_high_dollars", "yes_ask_close_dollars", "price_open_dollars",
    "price_low_dollars", "price_high_dollars", "price_close_dollars",
    "price_mean_dollars", "price_previous_dollars", "volume_fp",
    "open_interest_fp", "raw_source", "raw_session_id", "raw_request_id",
)
TRADE_FIELDS = (
    "stage", "event_ticker", "trade_id", "market_ticker", "route_tier",
    "created_time", "count_fp", "yes_price_dollars", "no_price_dollars",
    "taker_side", "taker_outcome_side", "taker_book_side", "is_block_trade",
    "raw_source", "raw_session_id", "raw_request_id",
)
EVENT_FIELDS = (
    "event_ticker", "series_ticker", "title", "sub_title", "strike_date",
    "strike_period", "fee_type_override", "fee_multiplier_override",
    "last_updated_ts", "raw_source", "raw_session_id", "raw_request_id",
)
EVENT_FEE_FIELDS = (
    "id", "event_ticker", "series_ticker", "fee_type_override",
    "fee_multiplier_override", "scheduled_ts", "raw_source", "raw_session_id",
    "raw_request_id",
)
SERIES_FIELDS = (
    "ticker", "frequency", "title", "category", "fee_type", "fee_multiplier",
    "last_updated_ts", "raw_source", "raw_session_id", "raw_request_id",
)
SERIES_FEE_FIELDS = (
    "id", "series_ticker", "fee_type", "fee_multiplier", "scheduled_ts",
    "raw_source", "raw_session_id", "raw_request_id",
)
COVERAGE_FIELDS = (
    "stage", "event_ticker", "market_ticker", "route_tier",
    "expected_one_minute_periods", "observed_candle_periods",
    "missing_candle_periods", "candles_with_two_sided_close",
    "trade_count", "trade_route_count", "duplicate_trade_ids_removed",
)


def _expected_periods(open_time: str, close_time: str) -> int:
    seconds = (_parse_utc(close_time, "close_time") - _parse_utc(open_time, "open_time")).total_seconds()
    if seconds <= 0:
        raise ExecutionArchiveCollectionError("invalid market lifecycle")
    return max(0, int(math.floor(seconds / 60.0)))


def materialize_archive_csvs(
    store: ResumeStore,
    scope: ArchiveScope,
    *,
    output_dir: str | Path,
    file_prefix: str,
) -> dict[str, Path]:
    output = Path(output_dir)
    required_global = ("series_bundle",)
    for key in required_global:
        if not store.has(key):
            raise ExecutionArchiveCollectionError(f"missing completed task {key}")
    for event in scope.events:
        if not store.has(f"event:{event}"):
            raise ExecutionArchiveCollectionError(f"missing event task {event}")
    for ticker in scope.markets:
        for kind in ("market", "candles", "trades"):
            if not store.has(f"{kind}:{ticker}"):
                raise ExecutionArchiveCollectionError(f"missing {kind} task {ticker}")

    paths = {
        "allowlist": output / f"{file_prefix}_archive_allowlist.csv",
        "markets": output / f"{file_prefix}_archive_market_metadata.csv",
        "candles": output / f"{file_prefix}_archive_candles_1m.csv",
        "trades": output / f"{file_prefix}_archive_trades.csv",
        "events": output / f"{file_prefix}_archive_event_metadata.csv",
        "event_fees": output / f"{file_prefix}_archive_event_fee_changes.csv",
        "series": output / f"{file_prefix}_archive_series_metadata.csv",
        "series_fees": output / f"{file_prefix}_archive_series_fee_changes.csv",
        "coverage": output / f"{file_prefix}_archive_coverage.csv",
    }

    _atomic_csv(paths["allowlist"], ALLOWLIST_FIELDS, scope.allowlist)

    market_rows: list[dict[str, Any]] = []
    candle_rows: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []

    for ticker in scope.markets:
        stage = scope.stage_by_market[ticker]
        event = scope.event_by_market[ticker]
        market = store.get(f"market:{ticker}")
        candles = store.get(f"candles:{ticker}")
        trades = store.get(f"trades:{ticker}")
        assert market is not None and candles is not None and trades is not None

        market_rows.append({"stage": stage, **market})
        two_sided = 0
        for row in candles.get("rows", []):
            if row.get("yes_bid_close_dollars") and row.get("yes_ask_close_dollars"):
                two_sided += 1
            candle_rows.append({"stage": stage, "event_ticker": event, **row})
        for row in trades.get("rows", []):
            trade_rows.append({"stage": stage, "event_ticker": event, **row})

        expected = _expected_periods(str(market["open_time"]), str(market["close_time"]))
        observed = len(candles.get("rows", []))
        coverage_rows.append(
            {
                "stage": stage,
                "event_ticker": event,
                "market_ticker": ticker,
                "route_tier": candles.get("route_tier", ""),
                "expected_one_minute_periods": expected,
                "observed_candle_periods": observed,
                "missing_candle_periods": max(0, expected - observed),
                "candles_with_two_sided_close": two_sided,
                "trade_count": len(trades.get("rows", [])),
                "trade_route_count": len(trades.get("routes", [])),
                "duplicate_trade_ids_removed": trades.get("duplicate_trade_ids_removed", 0),
            }
        )

    _atomic_csv(paths["markets"], MARKET_FIELDS, market_rows)
    _atomic_csv(paths["candles"], CANDLE_FIELDS, candle_rows)
    _atomic_csv(paths["trades"], TRADE_FIELDS, trade_rows)
    _atomic_csv(paths["coverage"], COVERAGE_FIELDS, coverage_rows)

    event_rows: list[dict[str, Any]] = []
    event_fee_rows: list[dict[str, Any]] = []
    for event in scope.events:
        bundle = store.get(f"event:{event}")
        assert bundle is not None
        event_rows.append(bundle["event"])
        event_fee_rows.extend(bundle.get("fee_changes", []))
    _atomic_csv(paths["events"], EVENT_FIELDS, event_rows)
    _atomic_csv(paths["event_fees"], EVENT_FEE_FIELDS, event_fee_rows)

    series_bundle = store.get("series_bundle")
    assert series_bundle is not None
    _atomic_csv(paths["series"], SERIES_FIELDS, [series_bundle["series"]])
    _atomic_csv(paths["series_fees"], SERIES_FEE_FIELDS, series_bundle.get("fee_changes", []))
    return paths


def resolve_raw_files_for_sessions(
    raw_root: str | Path,
    source_sessions: Sequence[Mapping[str, str]],
    *,
    require_all: bool = True,
) -> tuple[Path, ...]:
    """Resolve every raw JSONL file contributing to a resumed archive.

    A RawJsonlRecorder session can span UTC midnight, so more than one JSONL
    file can legitimately share a session_id in different date directories.
    Successful finalization therefore includes every matching file.
    """

    root = Path(raw_root)
    resolved: set[Path] = set()
    missing: list[str] = []

    for item in source_sessions:
        source = _required_text(item.get("source"), "source_session.source")
        session_id = _required_text(
            item.get("session_id"), "source_session.session_id"
        )
        if source != "kalshi_public_rest":
            raise ExecutionArchiveCollectionError(
                f"unexpected raw source for execution archive: {source!r}"
            )
        if Path(session_id).name != session_id:
            raise ExecutionArchiveCollectionError(
                f"unsafe raw session_id: {session_id!r}"
            )
        matches = tuple(root.rglob(f"{session_id}.jsonl"))
        if not matches:
            missing.append(session_id)
            continue
        resolved.update(path.resolve() for path in matches)

    if missing and require_all:
        raise ExecutionArchiveCollectionError(
            "raw lineage file missing for contributing session(s): "
            + ", ".join(sorted(missing))
        )
    return tuple(sorted(resolved))


def merge_source_sessions(
    *groups: Sequence[Mapping[str, str]],
) -> tuple[dict[str, str], ...]:
    merged: dict[tuple[str, str], dict[str, str]] = {}
    for group in groups:
        for item in group:
            source = _required_text(item.get("source"), "source_session.source")
            session_id = _required_text(
                item.get("session_id"), "source_session.session_id"
            )
            merged[(source, session_id)] = {
                "source": source,
                "session_id": session_id,
            }
    return tuple(merged[key] for key in sorted(merged))


def batch_values(values: Sequence[str], size: int) -> Iterable[tuple[str, ...]]:
    if size <= 0:
        raise ValueError("batch size must be positive")
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])
