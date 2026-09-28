from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from src.historical_feasibility import collect_historical_feasibility_rows, write_collected_csvs
from src.historical_feasibility_manifest_validation import validate_historical_feasibility_manifest
from src.historical_feasibility_schema import (
    CANDLE_REQUEST_CHUNK_SECONDS,
    MIN_FEASIBILITY_EVENTS_PER_CATEGORY,
    TARGET_CATEGORIES,
)


@dataclass(frozen=True)
class Ref:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class Resp:
    payload: dict[str, Any]
    raw_record: Ref


class RecordingFakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.index = 0
        self.raw_records: list[dict[str, Any]] = []

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> Resp:
        normalized = dict(params or {})
        key = (path, tuple(sorted(normalized.items())))
        payload = self.routes[key]
        self.index += 1
        request_id = f"r{self.index}"
        self.raw_records.append(
            {
                "schema_version": "raw_http_exchange.v1",
                "source": "kalshi_public_rest",
                "session_id": "s1",
                "request": {
                    "request_id": request_id,
                    "method": "GET",
                    "path": path,
                    "params": normalized,
                },
                "response": {
                    "status_code": 200,
                    "body_text": json.dumps(payload),
                    "json_parse_error": None,
                },
                "error": None,
            }
        )
        return Resp(payload, Ref("kalshi_public_rest", "s1", request_id))


def k(path: str, **params: Any):
    return path, tuple(sorted(params.items()))


def chunk_specs(start_ts: int, end_ts: int):
    current = start_ts
    while current <= end_ts:
        chunk_end = min(current + CANDLE_REQUEST_CHUNK_SECONDS, end_ts)
        yield current, chunk_end
        current = chunk_end + 1


def routes():
    result: dict[Any, dict[str, Any]] = {
        k("/historical/cutoff"): {
            "market_settled_ts": "2026-06-09T00:00:00Z",
            "trades_created_ts": "2026-06-09T00:00:00Z",
            "orders_updated_ts": "2026-06-09T00:00:00Z",
            "market_positions_last_updated_ts": "2026-06-09T00:00:00Z",
        }
    }
    events = []
    for i, category in enumerate(TARGET_CATEGORIES, start=1):
        event_ticker = f"EV{i}"
        series = f"SER{i}"
        ticker = f"MK{i}"
        events.append({"event_ticker": event_ticker, "series_ticker": series, "category": category})
        market = {
            "ticker": ticker,
            "event_ticker": event_ticker,
            "market_type": "binary",
            "status": "finalized",
            "open_time": "2026-05-01T00:00:00Z",
            "close_time": "2026-06-01T00:00:00Z",
            "settlement_ts": "2026-06-01T03:00:00Z",
            "mve_collection_ticker": "",
            "is_provisional": False,
            "result": "yes",
        }
        result[k("/historical/markets", event_ticker=event_ticker, limit=1000)] = {
            "markets": [market], "cursor": ""
        }
        result[k("/markets", event_ticker=event_ticker, limit=1000, status="settled")] = {
            "markets": [], "cursor": ""
        }
        close_ts = int(datetime.fromisoformat("2026-06-01T00:00:00+00:00").timestamp())
        start = close_ts - 7 * 86400
        end = close_ts - 1 * 86400
        candle_specs = [
            (close_ts - days * 86400, bid, ask)
            for days, bid, ask in (
                (6, "0.40", "0.42"),
                (4, "0.50", "0.52"),
                (2, "0.60", "0.62"),
            )
        ]
        for chunk_start, chunk_end in chunk_specs(start, end):
            result[k(
                f"/historical/markets/{ticker}/candlesticks",
                start_ts=chunk_start, end_ts=chunk_end, period_interval=1
            )] = {
                "ticker": ticker,
                "candlesticks": [
                    {
                        "end_period_ts": candle_end,
                        "yes_bid": {"close": bid},
                        "yes_ask": {"close": ask},
                        "price": {"close": "0.50"},
                        "volume": "2.00",
                        "open_interest": "3.00",
                    }
                    for candle_end, bid, ask in candle_specs
                    if chunk_start <= candle_end <= chunk_end
                ],
            }
    result[k("/events", limit=200, status="settled", with_nested_markets="false")] = {
        "events": events, "cursor": ""
    }
    return result


def test_manifest_validator_rebuilds_every_derived_table_from_raw(tmp_path: Path):
    client = RecordingFakeClient(routes())
    rows = collect_historical_feasibility_rows(
        client,
        run_id="run1",
        target_events_per_category=1,
        max_markets_per_event=1,
    )
    derived = tmp_path / "derived"
    paths = write_collected_csvs(derived, run_id="run1", rows=rows)
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text(
        "".join(json.dumps(record) + "\n" for record in client.raw_records),
        encoding="utf-8",
    )
    manifest = {
        "run_id": "run1",
        "status": "completed",
        "collector": {"name": "collect_historical_feasibility"},
        "files": [
            {"role": "raw_api_archive", "path": {"kind": "absolute", "value": str(raw_path)}},
            *[
                {"role": "derived_csv", "path": {"kind": "absolute", "value": str(path)}}
                for path in paths.all()
            ],
        ],
        "result": {
            "market_settled_cutoff": rows.cutoff.market_settled_ts.isoformat(),
            "trades_created_cutoff": rows.cutoff.trades_created_ts.isoformat(),
            "orders_updated_cutoff": rows.cutoff.orders_updated_ts.isoformat(),
            "market_positions_last_updated_cutoff": rows.cutoff.market_positions_last_updated_ts.isoformat(),
            "cutoff_raw_source": rows.cutoff_raw_source,
            "cutoff_raw_session_id": rows.cutoff_raw_session_id,
            "cutoff_raw_request_id": rows.cutoff_raw_request_id,
            "event_pages_scanned": rows.event_pages_scanned,
            "cross_tier_observation_count": rows.cross_tier_observation_count,
            "cross_tier_market_count": rows.cross_tier_market_count,
            "cross_tier_recovery_fetch_count": rows.cross_tier_recovery_fetch_count,
            "unclassifiable_event_count": rows.unclassifiable_event_count,
            "target_events_per_category": rows.target_events_per_category,
            "min_feasibility_events_per_category": MIN_FEASIBILITY_EVENTS_PER_CATEGORY,
            "max_markets_per_event": rows.max_markets_per_event,
            "outcomes_materialized": False,
            "strategy_analysis_run": False,
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    validated = validate_historical_feasibility_manifest(manifest_path)
    assert validated["validation"] == "PASS"
    assert validated["event_rows"] == 4
    assert validated["observation_rows"] == 12
    assert validated["outcomes_materialized"] is False


def sports_routes(count: int = 100):
    result: dict[Any, dict[str, Any]] = {
        k("/historical/cutoff"): {
            "market_settled_ts": "2026-06-09T00:00:00Z",
            "trades_created_ts": "2026-06-09T00:00:00Z",
            "orders_updated_ts": "2026-06-09T00:00:00Z",
            "market_positions_last_updated_ts": "2026-06-09T00:00:00Z",
        }
    }
    events = []
    close_ts = int(datetime.fromisoformat("2026-06-01T00:00:00+00:00").timestamp())
    start = close_ts - 7 * 86400
    end = close_ts - 1 * 86400
    for i in range(count):
        event_ticker = f"SEV{i:03d}"
        series = f"SSER{i:03d}"
        ticker = f"SMK{i:03d}"
        events.append({"event_ticker": event_ticker, "series_ticker": series, "category": "Sports"})
        market = {
            "ticker": ticker,
            "event_ticker": event_ticker,
            "market_type": "binary",
            "status": "finalized",
            "open_time": "2026-05-01T00:00:00Z",
            "close_time": "2026-06-01T00:00:00Z",
            "settlement_ts": "2026-06-01T03:00:00Z",
            "mve_collection_ticker": "",
            "is_provisional": False,
            "result": "yes",
        }
        result[k("/historical/markets", event_ticker=event_ticker, limit=1000)] = {
            "markets": [market], "cursor": ""
        }
        result[k("/markets", event_ticker=event_ticker, limit=1000, status="settled")] = {
            "markets": [], "cursor": ""
        }
        candle_specs = [
            (close_ts - days * 86400, bid, ask)
            for days, bid, ask in (
                (6, "0.40", "0.42"),
                (4, "0.50", "0.52"),
                (2, "0.60", "0.62"),
            )
        ]
        for chunk_start, chunk_end in chunk_specs(start, end):
            result[k(
                f"/historical/markets/{ticker}/candlesticks",
                start_ts=chunk_start, end_ts=chunk_end, period_interval=1
            )] = {
                "ticker": ticker,
                "candlesticks": [
                    {
                        "end_period_ts": candle_end,
                        "yes_bid": {"close": bid},
                        "yes_ask": {"close": ask},
                        "price": {"close": "0.50"},
                        "volume": "2.00",
                        "open_interest": "3.00",
                    }
                    for candle_end, bid, ask in candle_specs
                    if chunk_start <= candle_end <= chunk_end
                ],
            }
    result[k("/events", limit=200, status="settled", with_nested_markets="false")] = {
        "events": events, "cursor": ""
    }
    return result


def test_manifest_validator_rebuilds_sports_v2_scalability_summary(tmp_path: Path):
    from src.sports_calibration_v2_scalability import (
        SPORTS_V2_SCALABILITY_MIN_EVENTS,
        build_sports_v2_scalability_summary,
    )

    client = RecordingFakeClient(sports_routes())
    rows = collect_historical_feasibility_rows(
        client,
        run_id="sportsrun",
        target_events_per_category=100,
        max_markets_per_event=2,
        target_categories=("Sports",),
    )
    scalability = build_sports_v2_scalability_summary(rows)
    derived = tmp_path / "derived"
    paths = write_collected_csvs(derived, run_id="sportsrun", rows=rows)
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text(
        "".join(json.dumps(record) + "\n" for record in client.raw_records),
        encoding="utf-8",
    )
    manifest = {
        "run_id": "sportsrun",
        "status": "completed",
        "collector": {"name": "collect_sports_v2_scalability"},
        "files": [
            {"role": "raw_api_archive", "path": {"kind": "absolute", "value": str(raw_path)}},
            *[
                {"role": "derived_csv", "path": {"kind": "absolute", "value": str(path)}}
                for path in paths.all()
            ],
        ],
        "result": {
            "market_settled_cutoff": rows.cutoff.market_settled_ts.isoformat(),
            "trades_created_cutoff": rows.cutoff.trades_created_ts.isoformat(),
            "orders_updated_cutoff": rows.cutoff.orders_updated_ts.isoformat(),
            "market_positions_last_updated_cutoff": rows.cutoff.market_positions_last_updated_ts.isoformat(),
            "cutoff_raw_source": rows.cutoff_raw_source,
            "cutoff_raw_session_id": rows.cutoff_raw_session_id,
            "cutoff_raw_request_id": rows.cutoff_raw_request_id,
            "event_pages_scanned": rows.event_pages_scanned,
            "cross_tier_observation_count": rows.cross_tier_observation_count,
            "cross_tier_market_count": rows.cross_tier_market_count,
            "cross_tier_recovery_fetch_count": rows.cross_tier_recovery_fetch_count,
            "unclassifiable_event_count": rows.unclassifiable_event_count,
            "target_events_per_category": rows.target_events_per_category,
            "min_feasibility_events_per_category": MIN_FEASIBILITY_EVENTS_PER_CATEGORY,
            "sports_v2_scalability_min_events": SPORTS_V2_SCALABILITY_MIN_EVENTS,
            "max_markets_per_event": rows.max_markets_per_event,
            "collection_categories": ["Sports"],
            "sports_v2_scalability": scalability,
            "outcomes_materialized": False,
            "strategy_analysis_run": False,
        },
    }
    manifest_path = tmp_path / "sports_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    validated = validate_historical_feasibility_manifest(manifest_path)
    assert validated["validation"] == "PASS"
    assert validated["collector_name"] == "collect_sports_v2_scalability"
    assert validated["categories"] == ["Sports"]
    assert validated["event_rows"] == 100
    assert validated["sports_v2_scalability"] == scalability
    assert scalability["status"] == "scalability_gate_pass"
