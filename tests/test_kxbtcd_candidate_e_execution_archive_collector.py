from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sqlite3

import pytest

from src.kxbtcd_candidate_e_execution_archive_collector import (
    Cutoffs,
    ExecutionArchiveCollectionError,
    PacedClient,
    ResumeStore,
    effective_market_route,
    merge_source_sessions,
    resolve_raw_files_for_sessions,
    fetch_event_bundle,
    fetch_market_metadata_batch,
    fetch_trades,
    normalize_candles,
    trade_routes_for_window,
)


@dataclass(frozen=True)
class Ref:
    source: str = "kalshi_public_rest"
    session_id: str = "session"
    request_id: str = "request"


@dataclass(frozen=True)
class Resp:
    payload: object
    raw_record: Ref = Ref()


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, path, *, params=None, top_level_container="object"):
        self.calls.append((path, dict(params or {})))
        if not self.responses:
            raise AssertionError("unexpected request")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return Resp(item, Ref(request_id=f"r{len(self.calls)}"))


def cutoff(ts="2026-05-01T00:00:00+00:00"):
    dt = datetime.fromisoformat(ts)
    return Cutoffs(dt, dt, dt, None)


def test_resume_store_is_transactional_and_scope_bound(tmp_path):
    path = tmp_path / "resume.sqlite"
    store = ResumeStore(path, scope_id="smoke_5")
    store.put("task:a", "x", {"value": 1})
    assert store.has("task:a")
    assert store.get("task:a") == {"value": 1}
    store.close()

    reopened = ResumeStore(path, scope_id="smoke_5")
    assert reopened.get("task:a") == {"value": 1}
    reopened.close()

    with pytest.raises(ExecutionArchiveCollectionError, match="scope_id mismatch"):
        ResumeStore(path, scope_id="full")


def test_paced_client_allows_only_read_archive_paths():
    fake = FakeClient([{"ok": True}, {"trades": [], "cursor": ""}])
    paced = PacedClient(fake, delay_seconds=0)
    assert paced.get_json("/historical/cutoff").payload == {"ok": True}
    assert paced.get_json("/historical/trades").payload == {
        "trades": [],
        "cursor": "",
    }
    with pytest.raises(ExecutionArchiveCollectionError, match="forbidden"):
        paced.get_json("/portfolio/orders")


def test_market_metadata_must_resolve_exactly_one_tier():
    ticker = "KXBTCD-E-M"
    event = "KXBTCD-E"
    historical = {
        "markets": [{
            "ticker": ticker,
            "event_ticker": event,
            "open_time": "2026-01-01T00:00:00Z",
            "close_time": "2026-01-01T01:00:00Z",
            "settlement_ts": "2026-01-01T01:01:00Z",
        }],
        "cursor": "",
    }
    live = {"markets": [], "cursor": ""}
    client = FakeClient([historical, live])
    result = fetch_market_metadata_batch(
        client,
        tickers=[ticker],
        expected_event_by_market={ticker: event},
    )
    assert result[ticker]["observed_route_tier"] == "historical"

    dup = FakeClient([historical, historical])
    with pytest.raises(ExecutionArchiveCollectionError, match="exactly one tier"):
        fetch_market_metadata_batch(
            dup,
            tickers=[ticker],
            expected_event_by_market={ticker: event},
        )


def test_effective_market_route_uses_current_cutoff_not_stale_observed_tier():
    meta = {
        "settlement_ts": "2026-01-01T01:01:00Z",
        "observed_route_tier": "live",
    }
    assert effective_market_route(meta, cutoff()) == "historical"


def test_normalize_historical_and_live_candles():
    historical = Resp({
        "ticker": "M",
        "candlesticks": [{
            "end_period_ts": 60,
            "yes_bid": {"open": "0.40", "low": "0.39", "high": "0.41", "close": "0.40"},
            "yes_ask": {"open": "0.42", "low": "0.41", "high": "0.43", "close": "0.42"},
            "price": {"open": "0.41", "low": "0.40", "high": "0.42", "close": "0.41", "mean": "0.41", "previous": "0.40"},
            "volume": "10.00",
            "open_interest": "12.00",
        }],
    })
    rows = normalize_candles(
        historical, ticker="M", route_tier="historical", start_ts=0, end_ts=60
    )
    assert rows[0]["yes_bid_close_dollars"] == "0.40"
    assert rows[0]["volume_fp"] == "10.00"

    live = Resp({
        "ticker": "M",
        "candlesticks": [{
            "end_period_ts": 60,
            "yes_bid": {"open_dollars": "0.40", "low_dollars": "0.39", "high_dollars": "0.41", "close_dollars": "0.40"},
            "yes_ask": {"open_dollars": "0.42", "low_dollars": "0.41", "high_dollars": "0.43", "close_dollars": "0.42"},
            "price": {"open_dollars": "0.41", "low_dollars": "0.40", "high_dollars": "0.42", "close_dollars": "0.41", "mean_dollars": "0.41", "previous_dollars": "0.40"},
            "volume_fp": "10.00",
            "open_interest_fp": "12.00",
        }],
    })
    rows = normalize_candles(
        live, ticker="M", route_tier="live", start_ts=0, end_ts=60
    )
    assert rows[0]["yes_ask_high_dollars"] == "0.43"


def test_trade_routes_straddling_cutoff_use_both_tiers():
    c = cutoff()
    before = datetime(2026, 4, 30, 23, 59, tzinfo=timezone.utc)
    after = datetime(2026, 5, 1, 0, 1, tzinfo=timezone.utc)
    assert trade_routes_for_window(before, after, c) == ("historical", "live")


def test_trade_pagination_deduplicates_cross_tier_trade_ids():
    metadata = {
        "ticker": "M",
        "open_time": "2026-04-30T23:59:00Z",
        "close_time": "2026-05-01T00:01:00Z",
    }
    trade = {
        "trade_id": "T1",
        "ticker": "M",
        "count_fp": "1.00",
        "yes_price_dollars": "0.40",
        "no_price_dollars": "0.60",
        "created_time": "2026-05-01T00:00:00Z",
    }
    client = FakeClient([
        {"trades": [trade], "cursor": ""},
        {"trades": [trade], "cursor": ""},
    ])
    result = fetch_trades(client, metadata=metadata, cutoffs=cutoff())
    assert len(result["rows"]) == 1
    assert result["duplicate_trade_ids_removed"] == 1


def test_cursor_loop_fails_closed_for_event_fee_history():
    event = {
        "event": {
            "event_ticker": "KXBTCD-E",
            "series_ticker": "KXBTCD",
        }
    }
    client = FakeClient([
        event,
        {"event_fee_changes": [], "cursor": "same"},
        {"event_fee_changes": [], "cursor": "same"},
    ])
    with pytest.raises(ExecutionArchiveCollectionError, match="cursor loop"):
        fetch_event_bundle(client, event_ticker="KXBTCD-E")


def test_event_fee_override_history_preserves_null_clear():
    event = {
        "event": {
            "event_ticker": "KXBTCD-E",
            "series_ticker": "KXBTCD",
            "fee_type_override": None,
            "fee_multiplier_override": None,
        }
    }
    fee = {
        "event_fee_changes": [{
            "id": "F",
            "event_ticker": "KXBTCD-E",
            "series_ticker": "KXBTCD",
            "fee_type_override": None,
            "fee_multiplier_override": None,
            "scheduled_ts": "2026-01-01T00:00:00Z",
        }],
        "cursor": "",
    }
    client = FakeClient([event, fee])
    result = fetch_event_bundle(client, event_ticker="KXBTCD-E")
    assert result["fee_changes"][0]["fee_type_override"] is None
    assert result["fee_changes"][0]["fee_multiplier_override"] is None


def test_trade_boundary_cushion_filters_back_to_exact_lifecycle():
    metadata = {
        "ticker": "M",
        "open_time": "2026-05-01T00:00:00Z",
        "close_time": "2026-05-01T00:01:00Z",
    }
    c = Cutoffs(
        datetime(2026, 4, 1, tzinfo=timezone.utc),
        datetime(2026, 4, 1, tzinfo=timezone.utc),
        datetime(2026, 4, 1, tzinfo=timezone.utc),
        None,
    )
    rows = [
        {
            "trade_id": "BEFORE",
            "ticker": "M",
            "count_fp": "1.00",
            "yes_price_dollars": "0.40",
            "no_price_dollars": "0.60",
            "created_time": "2026-04-30T23:59:59Z",
        },
        {
            "trade_id": "OPEN",
            "ticker": "M",
            "count_fp": "1.00",
            "yes_price_dollars": "0.40",
            "no_price_dollars": "0.60",
            "created_time": "2026-05-01T00:00:00Z",
        },
        {
            "trade_id": "CLOSE",
            "ticker": "M",
            "count_fp": "1.00",
            "yes_price_dollars": "0.40",
            "no_price_dollars": "0.60",
            "created_time": "2026-05-01T00:01:00Z",
        },
        {
            "trade_id": "AFTER",
            "ticker": "M",
            "count_fp": "1.00",
            "yes_price_dollars": "0.40",
            "no_price_dollars": "0.60",
            "created_time": "2026-05-01T00:01:01Z",
        },
    ]
    client = FakeClient([{"trades": rows, "cursor": ""}])
    result = fetch_trades(client, metadata=metadata, cutoffs=c)
    assert [row["trade_id"] for row in result["rows"]] == ["OPEN", "CLOSE"]
    assert client.calls[0][1]["min_ts"] == int(datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc).timestamp()) - 1
    assert client.calls[0][1]["max_ts"] == int(datetime(2026, 5, 1, 0, 1, tzinfo=timezone.utc).timestamp()) + 1


def test_resume_store_indexes_nested_raw_sessions(tmp_path):
    store = ResumeStore(tmp_path / "resume.sqlite", scope_id="smoke_5")
    payload = {
        "event": {
            "raw_source": "kalshi_public_rest",
            "raw_session_id": "session_a",
            "raw_request_id": "request_1",
        },
        "rows": [
            {
                "raw_source": "kalshi_public_rest",
                "raw_session_id": "session_b",
                "raw_request_id": "request_2",
            }
        ],
    }
    store.put("event:E", "event", payload)
    assert store.raw_sessions() == (
        {"source": "kalshi_public_rest", "session_id": "session_a"},
        {"source": "kalshi_public_rest", "session_id": "session_b"},
    )
    store.close()


def test_resume_store_migrates_v1_and_backfills_raw_sessions(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE archive_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        """
        CREATE TABLE archive_task (
            task_key TEXT PRIMARY KEY,
            task_kind TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            completed_at_utc TEXT NOT NULL
        )
        """
    )
    meta = {
        "schema_version": "kxbtcd_execution_archive_resume.v1",
        "archive_id": "kxbtcd_candidate_e_reusable_execution_archive.v1",
        "archive_fingerprint": "4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea",
        "allowlist_fingerprint": "85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1",
        "scope_id": "smoke_5",
    }
    conn.executemany(
        "INSERT INTO archive_meta(key,value) VALUES (?,?)", meta.items()
    )
    payload = {
        "raw_source": "kalshi_public_rest",
        "raw_session_id": "legacy_session",
        "raw_request_id": "legacy_request",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO archive_task(
            task_key,task_kind,payload_json,payload_sha256,completed_at_utc
        ) VALUES (?,?,?,?,?)
        """,
        ("cutoff_snapshot:old", "cutoff_snapshot", encoded, digest, "2026-08-18T00:00:00Z"),
    )
    conn.commit()
    conn.close()

    store = ResumeStore(path, scope_id="smoke_5")
    assert store.raw_sessions() == (
        {"source": "kalshi_public_rest", "session_id": "legacy_session"},
    )
    schema = store.conn.execute(
        "SELECT value FROM archive_meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert schema == "kxbtcd_execution_archive_resume.v2"
    store.close()


def test_resolve_raw_files_for_sessions_includes_cross_day_files(tmp_path):
    root = tmp_path / "raw"
    a = root / "2026" / "08" / "17"
    b = root / "2026" / "08" / "18"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "session_a.jsonl").write_text("{}\n", encoding="utf-8")
    (b / "session_a.jsonl").write_text("{}\n", encoding="utf-8")
    (b / "session_b.jsonl").write_text("{}\n", encoding="utf-8")

    sessions = merge_source_sessions(
        ({"source": "kalshi_public_rest", "session_id": "session_a"},),
        ({"source": "kalshi_public_rest", "session_id": "session_b"},),
    )
    files = resolve_raw_files_for_sessions(root, sessions)
    assert len(files) == 3

    with pytest.raises(ExecutionArchiveCollectionError, match="raw lineage file missing"):
        resolve_raw_files_for_sessions(
            root,
            ({"source": "kalshi_public_rest", "session_id": "missing"},),
        )
