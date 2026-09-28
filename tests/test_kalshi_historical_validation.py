from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.kalshi_historical_validation import (
    HistoricalEndpointValidationError,
    LiveSportsCandidate,
    find_historical_sports_candidate,
    find_live_sports_candidate,
    live_probe_window,
    make_report_row,
    validate_candlestick_payload,
    validate_cutoff_payload,
    validate_report_lineage_against_raw,
    validate_trades_payload,
)


@dataclass(frozen=True)
class FakeRawReference:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class FakeResponse:
    payload: dict
    raw_record: FakeRawReference
    request_started_at_utc: str = "2026-08-09T05:00:00.000000Z"
    request_started_monotonic_ns: int = 100
    received_at_utc: str = "2026-08-09T05:00:00.100000Z"
    received_monotonic_ns: int = 200


class FakeClient:
    def __init__(self, responses: list[tuple[str, FakeResponse]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, path: str, *, params=None) -> FakeResponse:
        self.calls.append((path, None if params is None else dict(params)))
        if not self.responses:
            raise AssertionError(f"unexpected request {path}")
        expected_path, response = self.responses.pop(0)
        if path != expected_path:
            raise AssertionError(f"expected {expected_path}, got {path}")
        return response


def response(request_id: str, payload: dict) -> FakeResponse:
    return FakeResponse(
        payload=payload,
        raw_record=FakeRawReference("kalshi_public_rest", "session-1", request_id),
    )


class HistoricalValidationTests(unittest.TestCase):
    def test_cutoff_requires_parseable_routing_timestamps(self) -> None:
        cutoff = validate_cutoff_payload(
            {
                "market_settled_ts": "2026-05-01T00:00:00Z",
                "trades_created_ts": "2026-05-02T00:00:00Z",
                "orders_updated_ts": "2026-05-03T00:00:00Z",
                "market_positions_last_updated_ts": "2026-05-04T00:00:00Z",
            }
        )
        self.assertEqual(cutoff.market_settled_ts.tzinfo, timezone.utc)
        with self.assertRaisesRegex(
            HistoricalEndpointValidationError, "trades_created_ts"
        ):
            validate_cutoff_payload(
                {
                    "market_settled_ts": "2026-05-01T00:00:00Z",
                    "trades_created_ts": "not-a-time",
                    "orders_updated_ts": "2026-05-03T00:00:00Z",
                }
            )

    def test_historical_candidate_uses_cutoff_and_event_category_without_result(self) -> None:
        cutoff = validate_cutoff_payload(
            {
                "market_settled_ts": "2026-05-01T00:00:00Z",
                "trades_created_ts": "2026-05-01T00:00:00Z",
                "orders_updated_ts": "2026-05-01T00:00:00Z",
            }
        )
        list_payload = {
            "markets": [
                {
                    "ticker": "KXSPORT-OLD-A",
                    "event_ticker": "KXSPORT-OLD",
                    "open_time": "2026-04-01T00:00:00Z",
                    "close_time": "2026-04-02T00:00:00Z",
                    "settlement_ts": "2026-04-02T01:00:00Z",
                    "result": "yes",
                }
            ],
            "cursor": "",
        }
        event_payload = {
            "event": {
                "event_ticker": "KXSPORT-OLD",
                "series_ticker": "KXSPORT",
                "category": "Sports",
            }
        }
        market_payload = {"market": dict(list_payload["markets"][0])}
        client = FakeClient(
            [
                ("/historical/markets", response("r1", list_payload)),
                ("/events/KXSPORT-OLD", response("r2", event_payload)),
                (
                    "/historical/markets/KXSPORT-OLD-A",
                    response("r3", market_payload),
                ),
            ]
        )
        candidate = find_historical_sports_candidate(client, cutoff=cutoff)
        self.assertEqual(candidate.ticker, "KXSPORT-OLD-A")
        self.assertEqual(candidate.series_ticker, "KXSPORT")
        self.assertLess(candidate.settlement_ts, cutoff.market_settled_ts)
        # The source payload can contain a result field, but selection does not
        # require or expose it.
        self.assertFalse(hasattr(candidate, "result"))

    def test_historical_market_at_or_after_cutoff_fails_closed(self) -> None:
        cutoff = validate_cutoff_payload(
            {
                "market_settled_ts": "2026-05-01T00:00:00Z",
                "trades_created_ts": "2026-05-01T00:00:00Z",
                "orders_updated_ts": "2026-05-01T00:00:00Z",
            }
        )
        client = FakeClient(
            [
                (
                    "/historical/markets",
                    response(
                        "r1",
                        {
                            "markets": [
                                {
                                    "ticker": "BAD",
                                    "event_ticker": "EVENT",
                                    "open_time": "2026-04-01T00:00:00Z",
                                    "close_time": "2026-04-30T23:00:00Z",
                                    "settlement_ts": "2026-05-01T00:00:00Z",
                                }
                            ],
                            "cursor": "",
                        },
                    ),
                )
            ]
        )
        with self.assertRaisesRegex(
            HistoricalEndpointValidationError, "at or after the captured market cutoff"
        ):
            find_historical_sports_candidate(client, cutoff=cutoff)

    def test_live_candidate_requires_sports_and_nested_market_identity(self) -> None:
        client = FakeClient(
            [
                (
                    "/events",
                    response(
                        "r1",
                        {
                            "events": [
                                {
                                    "event_ticker": "E1",
                                    "series_ticker": "S1",
                                    "category": "Sports",
                                    "markets": [
                                        {
                                            "ticker": "M1",
                                            "status": "active",
                                            "open_time": "2026-08-08T00:00:00Z",
                                            "close_time": "2026-08-10T00:00:00Z",
                                            "volume_24h_fp": "12.50",
                                        }
                                    ],
                                }
                            ],
                            "cursor": "",
                        },
                    ),
                )
            ]
        )
        candidate = find_live_sports_candidate(
            client,
            now_utc=datetime(2026, 8, 9, tzinfo=timezone.utc),
        )
        self.assertEqual(candidate.ticker, "M1")
        self.assertEqual(candidate.series_ticker, "S1")
        self.assertEqual(candidate.volume_24h, Decimal("12.50"))


    def test_live_candidate_prefers_highest_positive_24h_volume(self) -> None:
        client = FakeClient(
            [
                (
                    "/events",
                    response(
                        "r1",
                        {
                            "events": [
                                {
                                    "event_ticker": "E1",
                                    "series_ticker": "S1",
                                    "category": "Sports",
                                    "markets": [
                                        {
                                            "ticker": "LOW",
                                            "status": "active",
                                            "open_time": "2026-08-08T00:00:00Z",
                                            "close_time": "2026-08-10T00:00:00Z",
                                            "volume_24h_fp": "2.00",
                                        },
                                        {
                                            "ticker": "HIGH",
                                            "status": "active",
                                            "open_time": "2026-08-08T00:00:00Z",
                                            "close_time": "2026-08-11T00:00:00Z",
                                            "volume_24h_fp": "99.00",
                                        },
                                    ],
                                }
                            ],
                            "cursor": "",
                        },
                    ),
                )
            ]
        )
        candidate = find_live_sports_candidate(
            client, now_utc=datetime(2026, 8, 9, tzinfo=timezone.utc)
        )
        self.assertEqual(candidate.ticker, "HIGH")
        self.assertEqual(candidate.volume_24h, Decimal("99.00"))

    def test_live_candidate_rejects_zero_volume_fallback(self) -> None:
        client = FakeClient(
            [
                (
                    "/events",
                    response(
                        "r1",
                        {
                            "events": [
                                {
                                    "event_ticker": "E1",
                                    "series_ticker": "S1",
                                    "category": "Sports",
                                    "markets": [
                                        {
                                            "ticker": "M1",
                                            "status": "active",
                                            "open_time": "2026-08-08T00:00:00Z",
                                            "close_time": "2026-08-10T00:00:00Z",
                                            "volume_24h_fp": "0.00",
                                        }
                                    ],
                                }
                            ],
                            "cursor": "",
                        },
                    ),
                )
            ]
        )
        with self.assertRaisesRegex(
            HistoricalEndpointValidationError, "positive 24h volume"
        ):
            find_live_sports_candidate(
                client, now_utc=datetime(2026, 8, 9, tzinfo=timezone.utc)
            )

    def test_live_probe_window_matches_24h_activity_horizon(self) -> None:
        candidate = LiveSportsCandidate(
            ticker="M1",
            event_ticker="E1",
            series_ticker="S1",
            open_time=datetime(2026, 8, 1, tzinfo=timezone.utc),
            close_time=datetime(2026, 8, 10, tzinfo=timezone.utc),
            volume_24h=Decimal("10.00"),
            event_response=response("r1", {}),
        )
        now = datetime(2026, 8, 9, tzinfo=timezone.utc)
        start, end = live_probe_window(candidate, now_utc=now)
        self.assertEqual(end - start, 24 * 60 * 60)

    def test_historical_and_live_candlestick_field_families_remain_distinct(self) -> None:
        historical = validate_candlestick_payload(
            {
                "ticker": "M1",
                "candlesticks": [
                    {
                        "end_period_ts": 10,
                        "yes_bid": {"close": "0.44"},
                        "yes_ask": {"close": "0.46"},
                        "price": {"close": "0.45", "previous": "0.44"},
                        "volume": "10.00",
                    }
                ],
            },
            expected_ticker="M1",
            tier="historical",
        )
        live = validate_candlestick_payload(
            {
                "ticker": "M2",
                "candlesticks": [
                    {
                        "end_period_ts": 20,
                        "yes_bid": {"close_dollars": "0.55"},
                        "yes_ask": {"close_dollars": "0.57"},
                        "price": {
                            "close_dollars": "0.56",
                            "previous_dollars": "0.55",
                        },
                        "volume_fp": "10.00",
                    }
                ],
            },
            expected_ticker="M2",
            tier="live",
        )
        self.assertEqual(historical.quote_pair_close_count, 1)
        self.assertIn("close", historical.observed_bid_fields)
        self.assertEqual(live.quote_pair_close_count, 1)
        self.assertIn("close_dollars", live.observed_bid_fields)

    def test_candlestick_order_is_measured_not_assumed(self) -> None:
        summary = validate_candlestick_payload(
            {
                "ticker": "M1",
                "candlesticks": [
                    {"end_period_ts": 20, "yes_bid": {}, "yes_ask": {}},
                    {"end_period_ts": 10, "yes_bid": {}, "yes_ask": {}},
                    {"end_period_ts": 10, "yes_bid": {}, "yes_ask": {}},
                ],
            },
            expected_ticker="M1",
            tier="historical",
        )
        self.assertEqual(summary.end_period_order, "descending")
        self.assertEqual(summary.duplicate_end_period_count, 1)

    def test_candlesticks_measure_crossed_and_missing_quotes_without_imputation(self) -> None:
        summary = validate_candlestick_payload(
            {
                "ticker": "M1",
                "candlesticks": [
                    {
                        "end_period_ts": 10,
                        "yes_bid": {"close": "0.60"},
                        "yes_ask": {"close": "0.55"},
                    },
                    {
                        "end_period_ts": 20,
                        "yes_bid": {"close": None},
                        "yes_ask": {"close": "0.56"},
                    },
                ],
            },
            expected_ticker="M1",
            tier="historical",
        )
        self.assertEqual(summary.crossed_close_count, 1)
        self.assertEqual(summary.missing_bid_close_count, 1)
        self.assertEqual(summary.quote_pair_close_count, 1)

    def test_trades_validate_identity_and_time_order(self) -> None:
        summary = validate_trades_payload(
            {
                "trades": [
                    {
                        "trade_id": "t1",
                        "ticker": "M1",
                        "count_fp": "1.00",
                        "yes_price_dollars": "0.40",
                        "no_price_dollars": "0.60",
                        "created_time": "2026-04-01T00:00:00Z",
                    },
                    {
                        "trade_id": "t2",
                        "ticker": "M1",
                        "count_fp": "2.00",
                        "yes_price_dollars": "0.41",
                        "no_price_dollars": "0.59",
                        "created_time": "2026-04-01T00:01:00Z",
                    },
                ],
                "cursor": "",
            },
            expected_ticker="M1",
        )
        self.assertEqual(summary.trade_count, 2)
        self.assertEqual(summary.created_time_order, "ascending")
        self.assertEqual(summary.duplicate_created_time_count, 0)

    def test_report_lineage_reconciles_exact_raw_request_and_timing(self) -> None:
        fake = response("request-1", {"ticker": "M1", "candlesticks": []})
        row = make_report_row(
            probe_name="historical_candlesticks_1m",
            route_tier="historical",
            method="GET",
            path="/historical/markets/M1/candlesticks",
            response=fake,
            ticker="M1",
            item_count=0,
        )
        raw_record = {
            "schema_version": "raw_http_exchange.v1",
            "source": "kalshi_public_rest",
            "session_id": "session-1",
            "request": {
                "request_id": "request-1",
                "method": "GET",
                "base_url": "https://external-api.kalshi.com/trade-api/v2",
                "path": "/historical/markets/M1/candlesticks",
                "params": {},
                "started_at_utc": fake.request_started_at_utc,
                "started_monotonic_ns": 100,
            },
            "timing": {
                "received_at_utc": fake.received_at_utc,
                "received_monotonic_ns": 200,
                "elapsed_monotonic_ns": 100,
            },
            "response": {"status_code": 200},
            "source_timestamps": [],
            "error": None,
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "raw.jsonl"
            path.write_text(json.dumps(raw_record) + "\n", encoding="utf-8")
            summary = validate_report_lineage_against_raw([row], [path])
        self.assertEqual(summary["accepted_unique_raw_reference_count"], 1)
        self.assertEqual(summary["raw_error_count"], 0)

    def test_report_lineage_rejects_path_mismatch(self) -> None:
        fake = response("request-1", {})
        row = make_report_row(
            probe_name="cutoff",
            route_tier="historical_control",
            method="GET",
            path="/historical/cutoff",
            response=fake,
        )
        raw_record = {
            "source": "kalshi_public_rest",
            "session_id": "session-1",
            "request": {
                "request_id": "request-1",
                "method": "GET",
                "path": "/wrong",
                "started_at_utc": fake.request_started_at_utc,
            },
            "timing": {
                "received_at_utc": fake.received_at_utc,
                "elapsed_monotonic_ns": 1,
            },
            "response": {"status_code": 200},
            "error": None,
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "raw.jsonl"
            path.write_text(json.dumps(raw_record) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                HistoricalEndpointValidationError, "path does not match"
            ):
                validate_report_lineage_against_raw([row], [path])


if __name__ == "__main__":
    unittest.main()
