from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from typing import Any, Mapping

from src.sports_historical_collector import (
    SportsHistoricalCollectionError,
    collect_sports_historical_rows,
    validate_collected_rows,
    write_collected_csvs,
)
from src.sports_historical_schema import ANCHOR_DAYS, CANDLE_FIELDS, EVENT_FIELDS, MARKET_FIELDS


@dataclass(frozen=True)
class Ref:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class Resp:
    payload: dict[str, Any]
    raw_record: Ref
    request_started_at_utc: str = "2026-08-09T05:30:00.000000Z"
    request_started_monotonic_ns: int = 100
    received_at_utc: str = "2026-08-09T05:30:00.100000Z"
    received_monotonic_ns: int = 200


class FakeClient:
    def __init__(self, routes: Mapping[tuple[str, tuple[tuple[str, Any], ...]], dict[str, Any]]) -> None:
        self.routes = dict(routes)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.index = 0

    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> Resp:
        normalized = dict(params or {})
        self.calls.append((path, normalized))
        key = (path, tuple(sorted(normalized.items())))
        if key not in self.routes:
            raise AssertionError(f"unexpected request {key!r}")
        self.index += 1
        return Resp(
            payload=self.routes[key],
            raw_record=Ref("kalshi_public_rest", "session1", f"r{self.index}"),
        )


def key(path: str, **params: Any) -> tuple[str, tuple[tuple[str, Any], ...]]:
    return path, tuple(sorted(params.items()))


def cutoff_payload() -> dict[str, Any]:
    return {
        "market_settled_ts": "2026-06-09T00:00:00Z",
        "trades_created_ts": "2026-06-09T00:00:00Z",
        "orders_updated_ts": "2026-06-09T00:00:00Z",
        "market_positions_last_updated_ts": "2026-06-09T00:00:00Z",
    }


def sports_event() -> dict[str, Any]:
    return {
        "event_ticker": "EVT1",
        "series_ticker": "SER1",
        "category": "Sports",
        "mutually_exclusive": True,
        "strike_date": "2026-06-01T00:00:00Z",
    }


def hist_market(result: str = "yes") -> dict[str, Any]:
    return {
        "ticker": "MKT1",
        "event_ticker": "EVT1",
        "market_type": "binary",
        "status": "finalized",
        "open_time": "2026-05-20T00:00:00Z",
        "close_time": "2026-06-01T00:00:00Z",
        "settlement_ts": "2026-06-01T03:00:00Z",
        "mve_collection_ticker": "",
        "is_provisional": False,
        "result": result,
    }


def candle_payload(ticker: str, ends: list[int], *, live: bool = False) -> dict[str, Any]:
    close_key = "close_dollars" if live else "close"
    volume_key = "volume_fp" if live else "volume"
    oi_key = "open_interest_fp" if live else "open_interest"
    candles = []
    for i, end in enumerate(ends):
        bid = "0.40" if i == 0 else "0.45"
        ask = "0.42" if i == 0 else "0.44"  # second is crossed
        candles.append(
            {
                "end_period_ts": end,
                "yes_bid": {close_key: bid},
                "yes_ask": {close_key: ask},
                "price": {close_key: "0.41"},
                volume_key: "2.00",
                oi_key: "3.00",
            }
        )
    return {"ticker": ticker, "candlesticks": candles}


def base_routes(*, result: str = "yes", zero_anchor: str | None = "3d") -> dict[Any, dict[str, Any]]:
    close = datetime(2026, 6, 1, tzinfo=timezone.utc)
    routes: dict[Any, dict[str, Any]] = {
        key("/historical/cutoff"): cutoff_payload(),
        key("/events", limit=200, status="settled", with_nested_markets="false"): {
            "events": [
                {
                    "event_ticker": "OTHER",
                    "series_ticker": "OTHER",
                    "category": "Economics",
                },
                sports_event(),
            ],
            "cursor": "",
        },
        key("/historical/markets", event_ticker="EVT1", limit=1000): {
            "markets": [hist_market(result)],
            "cursor": "",
        },
        key("/markets", event_ticker="EVT1", limit=1000, status="settled"): {
            "markets": [],
            "cursor": "",
        },
    }
    for anchor_name, days in ANCHOR_DAYS.items():
        anchor_ts = int((close.timestamp() - days * 86400))
        start = anchor_ts - 24 * 3600
        ends = [] if anchor_name == zero_anchor else [anchor_ts - 120, anchor_ts - 60]
        routes[
            key(
                "/historical/markets/MKT1/candlesticks",
                start_ts=start,
                end_ts=anchor_ts,
                period_interval=1,
            )
        ] = candle_payload("MKT1", ends)
    return routes


class SportsHistoricalCollectorTests(unittest.TestCase):
    def test_collects_event_market_three_anchors_and_preserves_zero_window(self) -> None:
        client = FakeClient(base_routes())
        rows = collect_sports_historical_rows(
            client,
            run_id="run1",
            max_sports_events=1,
            anchor_lookback_hours=24,
        )
        self.assertEqual(rows.selected_event_count, 1)
        self.assertEqual(rows.selected_market_count, 1)
        self.assertEqual(len(rows.anchors), 3)
        self.assertEqual(len(rows.candles), 4)
        three_day = next(row for row in rows.anchors if row["anchor_name"] == "3d")
        self.assertEqual(three_day["candle_count"], "0")
        self.assertEqual(three_day["quote_pair_count"], "0")
        self.assertEqual(three_day["latest_quote_pair_ts"], "")
        self.assertEqual(three_day["latest_quote_age_seconds"], "")

    def test_result_value_does_not_change_pre_staleness_rows(self) -> None:
        yes_rows = collect_sports_historical_rows(
            FakeClient(base_routes(result="yes")),
            run_id="run1",
            max_sports_events=1,
        )
        no_rows = collect_sports_historical_rows(
            FakeClient(base_routes(result="no")),
            run_id="run1",
            max_sports_events=1,
        )
        self.assertEqual(yes_rows.events, no_rows.events)
        self.assertEqual(yes_rows.markets, no_rows.markets)
        self.assertEqual(yes_rows.anchors, no_rows.anchors)
        self.assertEqual(yes_rows.candles, no_rows.candles)
        for table in (yes_rows.events, yes_rows.markets, yes_rows.anchors, yes_rows.candles):
            for row in table:
                self.assertNotIn("result", row)

    def test_crossed_quote_is_measured_not_repaired(self) -> None:
        rows = collect_sports_historical_rows(
            FakeClient(base_routes(zero_anchor=None)),
            run_id="run1",
            max_sports_events=1,
        )
        crossed = [row for row in rows.candles if row["crossed_close"] == "true"]
        self.assertEqual(len(crossed), 3)
        self.assertEqual(crossed[0]["yes_bid_close"], "0.45")
        self.assertEqual(crossed[0]["yes_ask_close"], "0.44")

    def test_historical_candle_requests_use_market_settlement_route(self) -> None:
        client = FakeClient(base_routes())
        collect_sports_historical_rows(client, run_id="run1", max_sports_events=1)
        candle_calls = [call for call in client.calls if call[0].endswith("/candlesticks")]
        self.assertEqual(len(candle_calls), 3)
        self.assertTrue(all(path.startswith("/historical/markets/") for path, _ in candle_calls))
        self.assertTrue(all("include_latest_before_start" not in params for _, params in candle_calls))

    def test_live_market_routes_to_live_candles_with_synthetic_disabled(self) -> None:
        close = datetime(2026, 7, 1, tzinfo=timezone.utc)
        market = hist_market()
        market.update(
            {
                "ticker": "LIVE1",
                "close_time": "2026-07-01T00:00:00Z",
                "settlement_ts": "2026-07-01T03:00:00Z",
            }
        )
        routes = base_routes()
        routes[key("/historical/markets", event_ticker="EVT1", limit=1000)] = {
            "markets": [],
            "cursor": "",
        }
        routes[key("/markets", event_ticker="EVT1", limit=1000, status="settled")] = {
            "markets": [market],
            "cursor": "",
        }
        for anchor_name, days in ANCHOR_DAYS.items():
            anchor_ts = int(close.timestamp() - days * 86400)
            start = anchor_ts - 24 * 3600
            routes[
                key(
                    "/series/SER1/markets/LIVE1/candlesticks",
                    start_ts=start,
                    end_ts=anchor_ts,
                    period_interval=1,
                    include_latest_before_start="false",
                )
            ] = candle_payload("LIVE1", [anchor_ts - 60], live=True)
        # Remove now-unused historical MKT1 candle routes.
        routes = {
            k: v
            for k, v in routes.items()
            if not (k[0] == "/historical/markets/MKT1/candlesticks")
        }
        client = FakeClient(routes)
        rows = collect_sports_historical_rows(client, run_id="run1", max_sports_events=1)
        self.assertEqual(rows.markets[0]["route_tier"], "live")
        self.assertTrue(all(row["source_field_family"] == "live_dollars" for row in rows.candles))
        candle_calls = [call for call in client.calls if call[0].endswith("/candlesticks")]
        self.assertTrue(all(params["include_latest_before_start"] == "false" for _, params in candle_calls))

    def test_duplicate_market_across_tiers_fails_closed(self) -> None:
        routes = base_routes()
        live = hist_market()
        live["settlement_ts"] = "2026-07-01T03:00:00Z"
        # The same ticker appearing in both tiers is internally impossible under one cutoff.
        routes[key("/markets", event_ticker="EVT1", limit=1000, status="settled")] = {
            "markets": [live],
            "cursor": "",
        }
        with self.assertRaises(SportsHistoricalCollectionError):
            collect_sports_historical_rows(
                FakeClient(routes),
                run_id="run1",
                max_sports_events=1,
            )

    def test_off_tier_live_overlap_uses_historical_canonical_copy(self) -> None:
        routes = base_routes()
        # Exact observed production anomaly class: live list repeats a market whose
        # settlement timestamp is before the captured historical cutoff.
        routes[key("/markets", event_ticker="EVT1", limit=1000, status="settled")] = {
            "markets": [hist_market()],
            "cursor": "",
        }
        client = FakeClient(routes)
        rows = collect_sports_historical_rows(client, run_id="run1", max_sports_events=1)
        self.assertEqual(rows.markets[0]["route_tier"], "historical")
        self.assertEqual(rows.cross_tier_observation_count, 1)
        self.assertEqual(rows.cross_tier_market_count, 1)
        self.assertEqual(rows.cross_tier_recovery_fetch_count, 0)
        self.assertTrue(
            all(path.startswith("/historical/markets/") for path, _ in client.calls if path.endswith("/candlesticks"))
        )

    def test_off_tier_only_market_requires_canonical_single_market_recovery(self) -> None:
        routes = base_routes()
        routes[key("/historical/markets", event_ticker="EVT1", limit=1000)] = {
            "markets": [],
            "cursor": "",
        }
        routes[key("/markets", event_ticker="EVT1", limit=1000, status="settled")] = {
            "markets": [hist_market()],
            "cursor": "",
        }
        routes[key("/historical/markets/MKT1")] = {"market": hist_market()}
        client = FakeClient(routes)
        rows = collect_sports_historical_rows(client, run_id="run1", max_sports_events=1)
        self.assertEqual(rows.markets[0]["route_tier"], "historical")
        self.assertEqual(rows.cross_tier_observation_count, 1)
        self.assertEqual(rows.cross_tier_market_count, 1)
        self.assertEqual(rows.cross_tier_recovery_fetch_count, 1)
        self.assertIn(("/historical/markets/MKT1", {}), client.calls)


    def test_blank_category_event_is_skipped_as_unclassifiable(self) -> None:
        routes = base_routes()
        event_key = key(
            "/events", limit=200, status="settled", with_nested_markets="false"
        )
        routes[event_key]["events"].insert(
            0,
            {
                "event_ticker": "UNCAT",
                "series_ticker": "UNCAT",
                "category": "",
            },
        )
        rows = collect_sports_historical_rows(
            FakeClient(routes), run_id="run1", max_sports_events=1
        )
        self.assertEqual(rows.selected_event_count, 1)
        self.assertEqual(rows.unclassifiable_event_count, 1)
        summary = validate_collected_rows(rows, run_id="run1")
        self.assertEqual(summary["unclassifiable_event_count"], 1)

    def test_sports_event_still_requires_identity_fields(self) -> None:
        routes = base_routes()
        event_key = key(
            "/events", limit=200, status="settled", with_nested_markets="false"
        )
        routes[event_key]["events"] = [
            {"event_ticker": "EVT1", "category": "Sports"}
        ]
        with self.assertRaises(SportsHistoricalCollectionError):
            collect_sports_historical_rows(
                FakeClient(routes), run_id="run1", max_sports_events=1
            )

    def test_row_relationship_validator_requires_all_three_predeclared_anchors(self) -> None:
        rows = collect_sports_historical_rows(
            FakeClient(base_routes()),
            run_id="run1",
            max_sports_events=1,
        )
        broken = rows.__class__(
            events=rows.events,
            markets=rows.markets,
            anchors=rows.anchors[:-1],
            candles=tuple(
                row for row in rows.candles if row["anchor_name"] != rows.anchors[-1]["anchor_name"]
            ),
            cutoff=rows.cutoff,
            cutoff_raw_source=rows.cutoff_raw_source,
            cutoff_raw_session_id=rows.cutoff_raw_session_id,
            cutoff_raw_request_id=rows.cutoff_raw_request_id,
            event_pages_scanned=rows.event_pages_scanned,
        )
        with self.assertRaisesRegex(SportsHistoricalCollectionError, "anchor set"):
            validate_collected_rows(broken, run_id="run1")

    def test_csv_writer_uses_exact_schema_headers(self) -> None:
        rows = collect_sports_historical_rows(
            FakeClient(base_routes()),
            run_id="run1",
            max_sports_events=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_collected_csvs(tmp, run_id="run1", rows=rows)
            self.assertTrue(all(path.exists() for path in paths.all()))
            self.assertEqual(paths.events.read_text().splitlines()[0].split(","), list(EVENT_FIELDS))
            self.assertEqual(paths.markets.read_text().splitlines()[0].split(","), list(MARKET_FIELDS))
            self.assertEqual(paths.candles.read_text().splitlines()[0].split(","), list(CANDLE_FIELDS))


if __name__ == "__main__":
    unittest.main()
