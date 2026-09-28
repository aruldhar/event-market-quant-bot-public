from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import pytest

from src.historical_feasibility import (
    HistoricalFeasibilityError,
    build_category_summary_rows,
    collect_historical_feasibility_rows,
    validate_collected_rows,
)
from src.historical_feasibility_schema import CANDLE_REQUEST_CHUNK_SECONDS, TARGET_CATEGORIES


@dataclass(frozen=True)
class Ref:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class Resp:
    payload: dict[str, Any]
    raw_record: Ref


class FakeClient:
    def __init__(self, routes: Mapping[tuple[str, tuple[tuple[str, Any], ...]], dict[str, Any]]):
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
        return Resp(self.routes[key], Ref("kalshi_public_rest", "s1", f"r{self.index}"))


def key(path: str, **params: Any):
    return path, tuple(sorted(params.items()))


def cutoff():
    return {
        "market_settled_ts": "2026-06-09T00:00:00Z",
        "trades_created_ts": "2026-06-09T00:00:00Z",
        "orders_updated_ts": "2026-06-09T00:00:00Z",
        "market_positions_last_updated_ts": "2026-06-09T00:00:00Z",
    }


def event(category: str, suffix: str):
    return {
        "event_ticker": f"EV{suffix}",
        "series_ticker": f"SER{suffix}",
        "category": category,
    }


def market(category: str, suffix: str, result: str = "yes", live: bool = False):
    close = "2026-07-01T00:00:00Z" if live else "2026-06-01T00:00:00Z"
    settlement = "2026-07-01T03:00:00Z" if live else "2026-06-01T03:00:00Z"
    return {
        "ticker": f"MK{suffix}",
        "event_ticker": f"EV{suffix}",
        "market_type": "binary",
        "status": "finalized",
        "open_time": "2026-05-01T00:00:00Z",
        "close_time": close,
        "settlement_ts": settlement,
        "mve_collection_ticker": "",
        "is_provisional": False,
        "result": result,
    }


def candle_payload(ticker: str, close_ts: int, *, live: bool = False, crossed: bool = False, start_ts: int | None = None, end_ts: int | None = None):
    close_key = "close_dollars" if live else "close"
    volume_key = "volume_fp" if live else "volume"
    oi_key = "open_interest_fp" if live else "open_interest"
    candles = []
    for days, bid, ask in (
        (6, "0.40", "0.42"),
        (4, "0.50", "0.52"),
        (2, "0.60", "0.62"),
    ):
        if crossed and days == 4:
            bid, ask = "0.55", "0.54"
        candle_end = close_ts - days * 86400
        if start_ts is not None and candle_end < start_ts:
            continue
        if end_ts is not None and candle_end > end_ts:
            continue
        candles.append(
            {
                "end_period_ts": candle_end,
                "yes_bid": {close_key: bid},
                "yes_ask": {close_key: ask},
                "price": {close_key: "0.50"},
                volume_key: "2.00",
                oi_key: "3.00",
            }
        )
    return {"ticker": ticker, "candlesticks": candles}


def chunk_specs(start_ts: int, end_ts: int):
    current = start_ts
    index = 1
    while current <= end_ts:
        chunk_end = min(current + CANDLE_REQUEST_CHUNK_SECONDS, end_ts)
        yield index, current, chunk_end
        current = chunk_end + 1
        index += 1


def four_category_routes(*, result: str = "yes", live_category: str | None = None, crossed: bool = False):
    events = []
    routes: dict[Any, dict[str, Any]] = {key("/historical/cutoff"): cutoff()}
    for idx, category in enumerate(TARGET_CATEGORIES, start=1):
        suffix = str(idx)
        events.append(event(category, suffix))
        is_live = category == live_category
        m = market(category, suffix, result=result, live=is_live)
        hist_markets = [] if is_live else [m]
        live_markets = [m] if is_live else []
        routes[key("/historical/markets", event_ticker=f"EV{suffix}", limit=1000)] = {
            "markets": hist_markets,
            "cursor": "",
        }
        routes[key("/markets", event_ticker=f"EV{suffix}", limit=1000, status="settled")] = {
            "markets": live_markets,
            "cursor": "",
        }
        close_dt = datetime.fromisoformat(m["close_time"].replace("Z", "+00:00"))
        close_ts = int(close_dt.timestamp())
        start = close_ts - 7 * 86400
        end = close_ts - 1 * 86400
        for _chunk_index, chunk_start, chunk_end in chunk_specs(start, end):
            if is_live:
                routes[
                    key(
                        f"/series/SER{suffix}/markets/MK{suffix}/candlesticks",
                        start_ts=chunk_start,
                        end_ts=chunk_end,
                        period_interval=1,
                        include_latest_before_start="false",
                    )
                ] = candle_payload(
                    f"MK{suffix}", close_ts, live=True, crossed=crossed,
                    start_ts=chunk_start, end_ts=chunk_end,
                )
            else:
                routes[
                    key(
                        f"/historical/markets/MK{suffix}/candlesticks",
                        start_ts=chunk_start,
                        end_ts=chunk_end,
                        period_interval=1,
                    )
                ] = candle_payload(
                    f"MK{suffix}", close_ts, crossed=crossed,
                    start_ts=chunk_start, end_ts=chunk_end,
                )

    routes[key("/events", limit=200, status="settled", with_nested_markets="false")] = {
        "events": events,
        "cursor": "",
    }
    return routes


def collect(routes):
    return collect_historical_feasibility_rows(
        FakeClient(routes),
        run_id="run1",
        target_events_per_category=1,
        max_markets_per_event=1,
    )


def test_collects_all_four_categories_and_exact_time_to_close():
    rows = collect(four_category_routes())
    assert len(rows.events) == 4
    assert len(rows.markets) == 4
    assert len(rows.windows) == 24
    assert len(rows.observations) == 12
    assert {row["category"] for row in rows.events} == set(TARGET_CATEGORIES)
    one_market = [row for row in rows.observations if row["ticker"] == "MK1"]
    assert [int(row["time_to_close_seconds"]) for row in one_market] == [6 * 86400, 4 * 86400, 2 * 86400]
    assert [row["time_band"] for row in one_market] == [
        "early_5d_to_7d",
        "middle_3d_to_5d",
        "late_1d_to_3d",
    ]
    assert all("anchor" not in key for row in one_market for key in row)
    validate_collected_rows(rows, run_id="run1")


def test_result_value_cannot_change_feasibility_rows():
    yes = collect(four_category_routes(result="yes"))
    no = collect(four_category_routes(result="no"))
    assert yes.events == no.events
    assert yes.markets == no.markets
    assert yes.windows == no.windows
    assert yes.observations == no.observations
    assert yes.category_summary == no.category_summary
    for table in (yes.events, yes.markets, yes.windows, yes.observations, yes.category_summary):
        for row in table:
            assert "result" not in row


def test_crossed_quote_is_preserved_but_not_valid():
    rows = collect(four_category_routes(crossed=True))
    crossed = [row for row in rows.observations if row["crossed_close"] == "true"]
    assert len(crossed) == 4
    assert all(row["valid_quote_observation"] == "false" for row in crossed)
    assert all(row["exclusion_reason"] == "crossed_quote" for row in crossed)
    assert all(row["q_mid"] == "" and row["spread"] == "" for row in crossed)


def test_live_candles_explicitly_disable_synthetic_continuity():
    client = FakeClient(four_category_routes(live_category="Crypto"))
    rows = collect_historical_feasibility_rows(
        client,
        run_id="run1",
        target_events_per_category=1,
        max_markets_per_event=1,
    )
    crypto_market = next(row for row in rows.markets if row["category"] == "Crypto")
    assert crypto_market["route_tier"] == "live"
    live_calls = [
        (path, params)
        for path, params in client.calls
        if path.startswith("/series/") and path.endswith("/candlesticks")
    ]
    assert len(live_calls) == 6
    assert all(call[1]["include_latest_before_start"] == "false" for call in live_calls)
    assert all(call[1]["end_ts"] - call[1]["start_ts"] <= CANDLE_REQUEST_CHUNK_SECONDS for call in live_calls)


def test_historical_candle_window_is_split_below_api_limit():
    client = FakeClient(four_category_routes())
    collect_historical_feasibility_rows(
        client,
        run_id="run1",
        target_events_per_category=1,
        max_markets_per_event=1,
    )
    historical_calls = [
        (path, params) for path, params in client.calls
        if path.startswith("/historical/markets/") and path.endswith("/candlesticks")
    ]
    assert len(historical_calls) == 24
    assert all(params["end_ts"] - params["start_ts"] <= CANDLE_REQUEST_CHUNK_SECONDS for _, params in historical_calls)


def test_smoke_collection_cannot_lower_frozen_25_event_feasibility_gate():
    rows = collect(four_category_routes())
    for summary in rows.category_summary:
        assert summary["target_event_count"] == "25"
        assert summary["sample_target_met"] == "false"
        assert summary["quote_feasibility_pass"] == "false"
        assert summary["status"] == "insufficient_event_sample"
        assert summary["event_any_quote_coverage"] == "1.000000"
        assert summary["early_event_coverage"] == "1.000000"
        assert summary["middle_event_coverage"] == "1.000000"
        assert summary["late_event_coverage"] == "1.000000"


def test_candle_outside_predeclared_window_fails_closed():
    routes = four_category_routes()
    # Replace Sports candle payload with one candle at T-8d.
    close_ts = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp())
    start = close_ts - 7 * 86400
    end = close_ts - 1 * 86400
    _idx, chunk_start, chunk_end = next(iter(chunk_specs(start, end)))
    routes[key("/historical/markets/MK1/candlesticks", start_ts=chunk_start, end_ts=chunk_end, period_interval=1)] = {
        "ticker": "MK1",
        "candlesticks": [
            {
                "end_period_ts": close_ts - 8 * 86400,
                "yes_bid": {"close": "0.40"},
                "yes_ask": {"close": "0.42"},
            }
        ],
    }
    with pytest.raises(HistoricalFeasibilityError):
        collect(routes)


def test_targeted_collection_can_collect_sports_only_without_changing_default_contract():
    client = FakeClient(four_category_routes())
    rows = collect_historical_feasibility_rows(
        client,
        run_id="run1",
        target_events_per_category=1,
        max_markets_per_event=1,
        target_categories=("Sports",),
    )
    assert len(rows.events) == 1
    assert len(rows.markets) == 1
    assert len(rows.windows) == 6
    assert len(rows.observations) == 3
    assert {row["category"] for row in rows.events} == {"Sports"}
    market_calls = [path for path, _params in client.calls if path in {"/historical/markets", "/markets"}]
    assert len(market_calls) == 2
    summaries = {row["category"]: row for row in rows.category_summary}
    assert summaries["Sports"]["event_count"] == "1"
    assert summaries["Crypto"]["event_count"] == "0"


def test_targeted_collection_rejects_unknown_or_duplicate_categories():
    with pytest.raises(ValueError):
        collect_historical_feasibility_rows(
            FakeClient({}), run_id="run1", target_categories=("Not A Category",)
        )
    with pytest.raises(ValueError):
        collect_historical_feasibility_rows(
            FakeClient({}), run_id="run1", target_categories=("Sports", "Sports")
        )
