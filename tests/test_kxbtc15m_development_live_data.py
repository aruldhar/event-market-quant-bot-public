from types import SimpleNamespace

import pytest

from src.kxbtc15m_development_economics import FrozenMarket
from src.kxbtc15m_development_live_data import (
    DevelopmentLiveDataError,
    collect_development_live_data,
    parse_target_price,
)


class FakeClient:
    def __init__(self, market_payload, live_payload):
        self.market_payload = market_payload
        self.live_payload = live_payload
        self.calls = []

    def get_json(self, path, *, params=None):
        self.calls.append((path, params))
        payload = self.market_payload if path.startswith("/markets/") else self.live_payload
        suffix = "market" if path.startswith("/markets/") else "live"
        return SimpleNamespace(
            payload=payload,
            raw_record=SimpleNamespace(
                source="kalshi_public_rest",
                session_id="session-1",
                request_id=f"request-{suffix}",
            ),
            received_at_utc="2026-08-13T00:00:00Z",
        )


def payloads():
    ticker = "KXBTC15M-26AUG120200-00"
    event = "KXBTC15M-26AUG120200"
    market = {
        "market": {
            "ticker": ticker,
            "event_ticker": event,
            "yes_sub_title": "Target Price: $100.12",
            "open_time": "2026-08-12T05:45:00Z",
            "close_time": "2026-08-12T05:45:02Z",
            "expiration_value": 100.14,
            "result": "yes",
        }
    }
    live = {
        "live_data": {
            "type": "crypto",
            "is_historical": True,
            "default_range": "15min",
            "range_options": ["5min", "15min", "1h"],
            "details": {
                "coin": "BTC",
                "event_ticker": event,
                "maturity_ts_ms": 1786513502000,
                "timeseries": [
                    {"t": 1786513499000, "v": 100.123},
                    {"t": 1786513500000, "v": 100.13},
                    {"t": 1786513501000, "v": 100.135},
                    {"t": 1786513502000, "v": 100.144},
                ],
                "candlesticks": {"1M": [{"t": 1786513440000}]},
            },
        }
    }
    return market, live


def test_parse_target_price_handles_commas_and_case():
    assert str(parse_target_price("TARGET price: $63,792.88")) == "63792.88"


def test_collection_archives_market_and_one_hour_live_data():
    market, live = payloads()
    client = FakeClient(market, live)

    result = collect_development_live_data(
        client,
        [FrozenMarket(1, "KXBTC15M-26AUG120200-00")],
        run_id="run-1",
    )

    assert client.calls == [
        ("/markets/KXBTC15M-26AUG120200-00", None),
        ("/live_data/events/KXBTC15M-26AUG120200", {"range": "1h"}),
    ]
    assert len(result.summaries) == 1
    assert len(result.timeseries) == 4
    summary = result.summaries[0]
    assert summary["target_matches_rounded_preopen_reference"] == "1"
    assert summary["audit_only_final_matches_expiration_rounded"] == "1"
    assert summary["non_one_second_interval_count"] == "0"
    assert summary["holdout_read"] == "0"
    assert result.timeseries[0]["within_market_window"] == "0"
    assert result.timeseries[-1]["within_market_window"] == "1"
    assert result.timeseries[-1]["raw_delta_from_target"] == "0.024"


def test_target_semantic_mismatch_is_reported_not_rejected():
    market, live = payloads()
    market["market"]["yes_sub_title"] = "Target Price: $99.00"

    result = collect_development_live_data(
        FakeClient(market, live),
        [FrozenMarket(1, "KXBTC15M-26AUG120200-00")],
        run_id="run-1",
    )

    assert result.summaries[0]["target_matches_rounded_preopen_reference"] == "0"


def test_collection_can_stream_timeseries_without_retaining_all_rows():
    market, live = payloads()
    streamed = []

    result = collect_development_live_data(
        FakeClient(market, live),
        [FrozenMarket(1, "KXBTC15M-26AUG120200-00")],
        run_id="run-1",
        market_sink=lambda summary, rows: streamed.append((summary, rows)),
        retain_timeseries=False,
    )

    assert result.timeseries == []
    assert len(streamed) == 1
    assert len(streamed[0][1]) == 4


def test_collection_rejects_a_gap_in_one_second_grid():
    market, live = payloads()
    live["live_data"]["details"]["timeseries"][2]["t"] += 1000

    with pytest.raises(DevelopmentLiveDataError, match="not strictly increasing|not a contiguous"):
        collect_development_live_data(
            FakeClient(market, live),
            [FrozenMarket(1, "KXBTC15M-26AUG120200-00")],
            run_id="run-1",
        )


def test_collection_rejects_nonhistorical_response():
    market, live = payloads()
    live["live_data"]["is_historical"] = False

    with pytest.raises(DevelopmentLiveDataError, match="expected historical"):
        collect_development_live_data(
            FakeClient(market, live),
            [FrozenMarket(1, "KXBTC15M-26AUG120200-00")],
            run_id="run-1",
        )


def test_collection_rejects_maturity_close_mismatch():
    market, live = payloads()
    live["live_data"]["details"]["maturity_ts_ms"] += 1000

    with pytest.raises(DevelopmentLiveDataError, match="maturity_ts_ms"):
        collect_development_live_data(
            FakeClient(market, live),
            [FrozenMarket(1, "KXBTC15M-26AUG120200-00")],
            run_id="run-1",
        )


def test_collection_rejects_event_ticker_mismatch():
    market, live = payloads()
    live["live_data"]["details"]["event_ticker"] = "WRONG"

    with pytest.raises(DevelopmentLiveDataError, match="event_ticker mismatch"):
        collect_development_live_data(
            FakeClient(market, live),
            [FrozenMarket(1, "KXBTC15M-26AUG120200-00")],
            run_id="run-1",
        )


def test_collection_refuses_holdout_before_any_request():
    market, live = payloads()
    client = FakeClient(market, live)

    with pytest.raises(DevelopmentLiveDataError, match="refusing non-development"):
        collect_development_live_data(
            client,
            [FrozenMarket(101, "KXBTC15M-26AUG121445-45")],
            run_id="run-1",
        )

    assert client.calls == []
