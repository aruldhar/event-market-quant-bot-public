"""Outcome-blind cross-category Kalshi historical feasibility collector.

Checkpoint 09 asks whether trustworthy quote observations exist before any
strategy or outcome analysis is selected. This module uses real source-returned
1-minute candlesticks in the exact T-7d to T-1d region. It never maps quotes to
7d/3d/1d anchors, never forward-fills, and never reads a final result field.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Protocol, Sequence

from .historical_feasibility_schema import (
    CATEGORY_SUMMARY_FIELDS,
    CATEGORY_SUMMARY_SCHEMA_VERSION,
    CANDLE_REQUEST_CHUNK_SECONDS,
    CONCENTRATION_MAX_EVENT_WARNING,
    CONCENTRATION_TOP_DECILE_WARNING,
    EVENT_FIELDS,
    MARKET_FIELDS,
    MIN_EVENT_ANY_QUOTE_COVERAGE,
    MIN_FEASIBILITY_EVENTS_PER_CATEGORY,
    MIN_EVENT_BAND_COVERAGE,
    MIN_MARKET_ANY_QUOTE_COVERAGE,
    OBSERVATION_FIELDS,
    TARGET_CATEGORIES,
    WINDOW_END_DAYS_BEFORE_CLOSE,
    WINDOW_FIELDS,
    WINDOW_START_DAYS_BEFORE_CLOSE,
)


class HistoricalFeasibilityError(RuntimeError):
    """Raised when the outcome-blind feasibility dataset is internally invalid."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference


class RawFirstJsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class HistoricalCutoff:
    market_settled_ts: datetime
    trades_created_ts: datetime
    orders_updated_ts: datetime
    market_positions_last_updated_ts: datetime | None


@dataclass(frozen=True)
class HistoricalFeasibilityRows:
    events: tuple[dict[str, str], ...]
    markets: tuple[dict[str, str], ...]
    windows: tuple[dict[str, str], ...]
    observations: tuple[dict[str, str], ...]
    category_summary: tuple[dict[str, str], ...]
    cutoff: HistoricalCutoff
    cutoff_raw_source: str
    cutoff_raw_session_id: str
    cutoff_raw_request_id: str
    event_pages_scanned: int
    cross_tier_observation_count: int
    cross_tier_market_count: int
    cross_tier_recovery_fetch_count: int
    unclassifiable_event_count: int
    target_events_per_category: int
    max_markets_per_event: int


@dataclass(frozen=True)
class CsvPaths:
    events: Path
    markets: Path
    windows: Path
    observations: Path
    category_summary: Path

    def all(self) -> tuple[Path, ...]:
        return (
            self.events,
            self.markets,
            self.windows,
            self.observations,
            self.category_summary,
        )


def collect_historical_feasibility_rows(
    client: RawFirstJsonClient,
    *,
    run_id: str,
    target_events_per_category: int = 25,
    max_markets_per_event: int = 2,
    max_event_pages: int = 50,
    max_market_pages_per_tier: int = 5,
    target_categories: Sequence[str] = TARGET_CATEGORIES,
) -> HistoricalFeasibilityRows:
    """Collect a bounded, outcome-blind quote sample for selected categories.

    The default remains the original four-category Checkpoint-09 feasibility
    comparison. A narrowed category set is only a collection-efficiency control;
    it does not change any category's frozen feasibility gates or quote rules.
    """

    _required_text(run_id, "run_id")
    selected_categories = _validate_target_categories(target_categories)
    if target_events_per_category <= 0:
        raise ValueError("target_events_per_category must be positive")
    if max_markets_per_event <= 0:
        raise ValueError("max_markets_per_event must be positive")
    if max_event_pages <= 0:
        raise ValueError("max_event_pages must be positive")
    if max_market_pages_per_tier <= 0:
        raise ValueError("max_market_pages_per_tier must be positive")

    cutoff_response = client.get_json("/historical/cutoff")
    cutoff = _validate_cutoff(cutoff_response.payload)

    event_rows: list[dict[str, str]] = []
    market_rows: list[dict[str, str]] = []
    window_rows: list[dict[str, str]] = []
    observation_rows: list[dict[str, str]] = []
    selected_event_counts = {category: 0 for category in selected_categories}
    selected_event_tickers: set[str] = set()
    selected_market_tickers: set[str] = set()
    cross_tier_observation_count = 0
    cross_tier_market_tickers: set[str] = set()
    cross_tier_recovery_fetch_count = 0
    unclassifiable_event_count = 0
    cursor = ""
    pages_scanned = 0

    for _page_index in range(max_event_pages):
        params: dict[str, Any] = {
            "status": "settled",
            "limit": 200,
            "with_nested_markets": "false",
        }
        if cursor:
            params["cursor"] = cursor
        event_response = client.get_json("/events", params=params)
        pages_scanned += 1
        events, cursor = _validate_event_list(event_response.payload)

        for event in events:
            category = event.get("category")
            if not isinstance(category, str) or not category.strip():
                unclassifiable_event_count += 1
                continue
            if category not in selected_categories:
                continue
            if selected_event_counts[category] >= target_events_per_category:
                continue

            event_ticker = _required_text(event.get("event_ticker"), "event.event_ticker")
            if event_ticker in selected_event_tickers:
                continue
            series_ticker = _required_text(event.get("series_ticker"), "event.series_ticker")

            historical = _fetch_market_tier(
                client,
                event_ticker=event_ticker,
                tier="historical",
                max_pages=max_market_pages_per_tier,
            )
            live = _fetch_market_tier(
                client,
                event_ticker=event_ticker,
                tier="live",
                max_pages=max_market_pages_per_tier,
            )
            reconciled, off_tier_count, off_tier_tickers, recovery_count = _reconcile_market_tiers(
                client,
                event_ticker=event_ticker,
                cutoff=cutoff,
                candidates=historical + live,
            )
            cross_tier_observation_count += off_tier_count
            cross_tier_market_tickers.update(off_tier_tickers)
            cross_tier_recovery_fetch_count += recovery_count

            eligible = [item for item in reconciled if _is_baseline_market(item[0])]
            if not eligible:
                continue
            sampled = _sample_markets(eligible, max_markets_per_event=max_markets_per_event)
            _check_market_uniqueness(sampled, selected_market_tickers)

            event_rows.append(
                build_event_row(run_id=run_id, event=event, response=event_response)
            )
            selected_event_tickers.add(event_ticker)
            selected_event_counts[category] += 1

            for market, route_tier, market_response in sampled:
                ticker = _required_text(market.get("ticker"), "market.ticker")
                selected_market_tickers.add(ticker)
                market_row = build_market_row(
                    run_id=run_id,
                    market=market,
                    category=category,
                    route_tier=route_tier,
                    response=market_response,
                )
                market_rows.append(market_row)

                close_time = _parse_utc(market_row["close_time"], "market.close_time")
                start_dt = close_time - timedelta(days=WINDOW_START_DAYS_BEFORE_CLOSE)
                end_dt = close_time - timedelta(days=WINDOW_END_DAYS_BEFORE_CLOSE)
                start_ts = int(start_dt.timestamp())
                end_ts = int(end_dt.timestamp())
                for chunk_index, request_start_ts, request_end_ts in _candle_request_chunks(
                    start_ts, end_ts
                ):
                    candle_response = _fetch_candles(
                        client,
                        route_tier=route_tier,
                        series_ticker=series_ticker,
                        ticker=ticker,
                        start_ts=request_start_ts,
                        end_ts=request_end_ts,
                    )
                    observations = build_observation_rows(
                        run_id=run_id,
                        ticker=ticker,
                        event_ticker=event_ticker,
                        category=category,
                        close_time=close_time,
                        window_start_ts=start_ts,
                        window_end_ts=end_ts,
                        route_tier=route_tier,
                        response=candle_response,
                    )
                    observation_rows.extend(observations)
                    window_rows.append(
                        build_window_row(
                            run_id=run_id,
                            ticker=ticker,
                            event_ticker=event_ticker,
                            category=category,
                            window_start_ts=start_ts,
                            window_end_ts=end_ts,
                            request_chunk_index=chunk_index,
                            request_start_ts=request_start_ts,
                            request_end_ts=request_end_ts,
                            route_tier=route_tier,
                            response=candle_response,
                            observations=observations,
                        )
                    )

            if all(
                selected_event_counts[category] >= target_events_per_category
                for category in selected_categories
            ):
                cursor = ""
                break

        if not cursor:
            break
    else:
        if cursor:
            raise HistoricalFeasibilityError(
                "settled-event discovery still had another cursor after "
                f"max_event_pages={max_event_pages}; incomplete category feasibility "
                "discovery is not accepted"
            )

    provisional = HistoricalFeasibilityRows(
        events=tuple(event_rows),
        markets=tuple(market_rows),
        windows=tuple(window_rows),
        observations=tuple(observation_rows),
        category_summary=(),
        cutoff=cutoff,
        cutoff_raw_source=cutoff_response.raw_record.source,
        cutoff_raw_session_id=cutoff_response.raw_record.session_id,
        cutoff_raw_request_id=cutoff_response.raw_record.request_id,
        event_pages_scanned=pages_scanned,
        cross_tier_observation_count=cross_tier_observation_count,
        cross_tier_market_count=len(cross_tier_market_tickers),
        cross_tier_recovery_fetch_count=cross_tier_recovery_fetch_count,
        unclassifiable_event_count=unclassifiable_event_count,
        target_events_per_category=target_events_per_category,
        max_markets_per_event=max_markets_per_event,
    )
    validate_collected_rows(provisional, run_id=run_id, require_summary=False)
    summary_rows = build_category_summary_rows(provisional)
    rows = HistoricalFeasibilityRows(
        **{**provisional.__dict__, "category_summary": tuple(summary_rows)}
    )
    validate_collected_rows(rows, run_id=run_id, require_summary=True)
    return rows


def build_event_row(
    *, run_id: str, event: Mapping[str, Any], response: RawFirstJsonResponse
) -> dict[str, str]:
    category = _required_text(event.get("category"), "event.category")
    if category not in TARGET_CATEGORIES:
        raise HistoricalFeasibilityError(f"unsupported target category {category!r}")
    return {
        **_lineage(run_id, response.raw_record, "metadata"),
        "event_ticker": _required_text(event.get("event_ticker"), "event.event_ticker"),
        "series_ticker": _required_text(event.get("series_ticker"), "event.series_ticker"),
        "category": category,
    }


def build_market_row(
    *,
    run_id: str,
    market: Mapping[str, Any],
    category: str,
    route_tier: str,
    response: RawFirstJsonResponse,
) -> dict[str, str]:
    if route_tier not in {"historical", "live"}:
        raise HistoricalFeasibilityError("market route_tier must be historical or live")
    ticker = _required_text(market.get("ticker"), "market.ticker")
    return {
        **_lineage(run_id, response.raw_record, route_tier),
        "ticker": ticker,
        "event_ticker": _required_text(market.get("event_ticker"), "market.event_ticker"),
        "category": category,
        "market_type": _text_or_blank(market.get("market_type")),
        "status": _text_or_blank(market.get("status")),
        "open_time": _required_timestamp_text(market.get("open_time"), "market.open_time"),
        "close_time": _required_timestamp_text(market.get("close_time"), "market.close_time"),
        "settlement_ts": _required_timestamp_text(market.get("settlement_ts"), "market.settlement_ts"),
        "mve_collection_ticker": _text_or_blank(market.get("mve_collection_ticker")),
        "is_provisional": _bool_or_blank(market.get("is_provisional")),
        "selection_hash": _selection_hash(ticker),
    }


def build_observation_rows(
    *,
    run_id: str,
    ticker: str,
    event_ticker: str,
    category: str,
    close_time: datetime,
    window_start_ts: int,
    window_end_ts: int,
    route_tier: str,
    response: RawFirstJsonResponse,
) -> list[dict[str, str]]:
    if route_tier not in {"historical", "live"}:
        raise HistoricalFeasibilityError("candle route_tier must be historical or live")
    payload_ticker = _required_text(response.payload.get("ticker"), "candles.ticker")
    if payload_ticker != ticker:
        raise HistoricalFeasibilityError(
            f"candlestick ticker mismatch: expected {ticker!r}, got {payload_ticker!r}"
        )
    candles = response.payload.get("candlesticks")
    if not isinstance(candles, list):
        raise HistoricalFeasibilityError("candlesticks must be a list")

    close_key = "close" if route_tier == "historical" else "close_dollars"
    volume_key = "volume" if route_tier == "historical" else "volume_fp"
    oi_key = "open_interest" if route_tier == "historical" else "open_interest_fp"
    family = "historical_plain" if route_tier == "historical" else "live_dollars"
    close_ts = int(close_time.timestamp())
    rows: list[dict[str, str]] = []
    seen: set[int] = set()

    for index, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise HistoricalFeasibilityError(f"candlesticks[{index}] must be an object")
        end_ts = candle.get("end_period_ts")
        if not isinstance(end_ts, int) or isinstance(end_ts, bool):
            raise HistoricalFeasibilityError(
                f"candlesticks[{index}].end_period_ts must be integer"
            )
        if not window_start_ts <= end_ts <= window_end_ts:
            raise HistoricalFeasibilityError(
                f"candlestick {end_ts} outside requested feasibility window "
                f"[{window_start_ts}, {window_end_ts}]"
            )
        if end_ts in seen:
            raise HistoricalFeasibilityError(
                f"duplicate end_period_ts {end_ts} for market {ticker}"
            )
        seen.add(end_ts)

        bid_obj = _mapping_or_none(candle.get("yes_bid"), f"candlesticks[{index}].yes_bid")
        ask_obj = _mapping_or_none(candle.get("yes_ask"), f"candlesticks[{index}].yes_ask")
        price_obj = _mapping_or_none(candle.get("price"), f"candlesticks[{index}].price")
        bid = _decimal_or_none(None if bid_obj is None else bid_obj.get(close_key))
        ask = _decimal_or_none(None if ask_obj is None else ask_obj.get(close_key))
        pair_present = bid is not None and ask is not None
        crossed = bool(pair_present and bid > ask)
        exclusion_reason = ""
        valid = False
        q_mid = ""
        spread = ""
        if bid is None and ask is None:
            exclusion_reason = "missing_bid_and_ask"
        elif bid is None:
            exclusion_reason = "missing_bid"
        elif ask is None:
            exclusion_reason = "missing_ask"
        elif bid < 0 or bid > 1 or ask < 0 or ask > 1:
            exclusion_reason = "quote_out_of_range"
        elif bid > ask:
            exclusion_reason = "crossed_quote"
        else:
            valid = True
            q_mid = _decimal_text((bid + ask) / Decimal("2"))
            spread = _decimal_text(ask - bid)

        time_to_close_seconds = close_ts - end_ts
        minimum = WINDOW_END_DAYS_BEFORE_CLOSE * 86400
        maximum = WINDOW_START_DAYS_BEFORE_CLOSE * 86400
        if not minimum <= time_to_close_seconds <= maximum:
            raise HistoricalFeasibilityError(
                f"computed time_to_close_seconds {time_to_close_seconds} outside predeclared range"
            )

        rows.append(
            {
                **_lineage(run_id, response.raw_record, route_tier),
                "ticker": ticker,
                "event_ticker": event_ticker,
                "category": category,
                "source_field_family": family,
                "end_period_ts": str(end_ts),
                "close_time": _format_utc(close_time),
                "time_to_close_seconds": str(time_to_close_seconds),
                "time_band": _time_band(time_to_close_seconds),
                "period_interval_minutes": "1",
                "yes_bid_close": _decimal_text(bid),
                "yes_ask_close": _decimal_text(ask),
                "q_mid": q_mid,
                "spread": spread,
                "price_close": _decimal_text(
                    _decimal_or_none(None if price_obj is None else price_obj.get(close_key))
                ),
                "volume": _decimal_text(_decimal_or_none(candle.get(volume_key))),
                "open_interest": _decimal_text(_decimal_or_none(candle.get(oi_key))),
                "quote_pair_present": _bool_text(pair_present),
                "crossed_close": _bool_text(crossed),
                "valid_quote_observation": _bool_text(valid),
                "exclusion_reason": exclusion_reason,
            }
        )

    rows.sort(key=lambda row: int(row["end_period_ts"]))
    return rows


def build_window_row(
    *,
    run_id: str,
    ticker: str,
    event_ticker: str,
    category: str,
    window_start_ts: int,
    window_end_ts: int,
    request_chunk_index: int,
    request_start_ts: int,
    request_end_ts: int,
    route_tier: str,
    response: RawFirstJsonResponse,
    observations: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    valid = [row for row in observations if row["valid_quote_observation"] == "true"]
    pair = [row for row in observations if row["quote_pair_present"] == "true"]
    crossed = [row for row in observations if row["crossed_close"] == "true"]
    counts = {band: 0 for band in ("early_5d_to_7d", "middle_3d_to_5d", "late_1d_to_3d")}
    for row in valid:
        counts[row["time_band"]] += 1
    return {
        **_lineage(run_id, response.raw_record, route_tier),
        "ticker": ticker,
        "event_ticker": event_ticker,
        "category": category,
        "window_start_ts": str(window_start_ts),
        "window_end_ts": str(window_end_ts),
        "request_chunk_index": str(request_chunk_index),
        "request_start_ts": str(request_start_ts),
        "request_end_ts": str(request_end_ts),
        "window_start_days_before_close": str(WINDOW_START_DAYS_BEFORE_CLOSE),
        "window_end_days_before_close": str(WINDOW_END_DAYS_BEFORE_CLOSE),
        "period_interval_minutes": "1",
        "candle_count": str(len(observations)),
        "quote_pair_count": str(len(pair)),
        "valid_quote_observation_count": str(len(valid)),
        "invalid_quote_observation_count": str(len(observations) - len(valid)),
        "crossed_quote_count": str(len(crossed)),
        "early_valid_count": str(counts["early_5d_to_7d"]),
        "middle_valid_count": str(counts["middle_3d_to_5d"]),
        "late_valid_count": str(counts["late_1d_to_3d"]),
    }


def build_category_summary_rows(rows: HistoricalFeasibilityRows) -> list[dict[str, str]]:
    events_by_category: dict[str, list[Mapping[str, str]]] = {category: [] for category in TARGET_CATEGORIES}
    markets_by_category: dict[str, list[Mapping[str, str]]] = {category: [] for category in TARGET_CATEGORIES}
    valid_by_category: dict[str, list[Mapping[str, str]]] = {category: [] for category in TARGET_CATEGORIES}
    for row in rows.events:
        events_by_category[row["category"]].append(row)
    for row in rows.markets:
        markets_by_category[row["category"]].append(row)
    for row in rows.observations:
        if row["valid_quote_observation"] == "true":
            valid_by_category[row["category"]].append(row)

    output: list[dict[str, str]] = []
    for category in TARGET_CATEGORIES:
        events = events_by_category[category]
        markets = markets_by_category[category]
        valid = valid_by_category[category]
        event_ids = {row["event_ticker"] for row in events}
        market_ids = {row["ticker"] for row in markets}
        event_counts = {event: 0 for event in event_ids}
        market_counts = {ticker: 0 for ticker in market_ids}
        band_events = {band: set() for band in ("early_5d_to_7d", "middle_3d_to_5d", "late_1d_to_3d")}
        for obs in valid:
            event_counts[obs["event_ticker"]] += 1
            market_counts[obs["ticker"]] += 1
            band_events[obs["time_band"]].add(obs["event_ticker"])

        events_with = sum(1 for value in event_counts.values() if value > 0)
        markets_with = sum(1 for value in market_counts.values() if value > 0)
        event_coverage = _ratio(events_with, len(events))
        market_coverage = _ratio(markets_with, len(markets))
        early = _ratio(len(band_events["early_5d_to_7d"]), len(events))
        middle = _ratio(len(band_events["middle_3d_to_5d"]), len(events))
        late = _ratio(len(band_events["late_1d_to_3d"]), len(events))
        all_three = len(
            band_events["early_5d_to_7d"]
            & band_events["middle_3d_to_5d"]
            & band_events["late_1d_to_3d"]
        )
        all_three_coverage = _ratio(all_three, len(events))
        per_event = sorted(event_counts.values())
        med = float(median(per_event)) if per_event else 0.0
        p90 = _percentile_nearest_rank(per_event, 0.90)
        total_valid = len(valid)
        shares = sorted(
            ((count / total_valid) if total_valid else 0.0 for count in event_counts.values()),
            reverse=True,
        )
        max_share = shares[0] if shares else 0.0
        top_n = max(1, math.ceil(len(shares) * 0.10)) if shares else 0
        top_decile_share = sum(shares[:top_n]) if top_n else 0.0
        target_met = len(events) >= MIN_FEASIBILITY_EVENTS_PER_CATEGORY
        feasibility_pass = (
            target_met
            and event_coverage >= MIN_EVENT_ANY_QUOTE_COVERAGE
            and market_coverage >= MIN_MARKET_ANY_QUOTE_COVERAGE
            and early >= MIN_EVENT_BAND_COVERAGE
            and middle >= MIN_EVENT_BAND_COVERAGE
            and late >= MIN_EVENT_BAND_COVERAGE
        )
        concentration_warning = (
            max_share > CONCENTRATION_MAX_EVENT_WARNING
            or top_decile_share > CONCENTRATION_TOP_DECILE_WARNING
        )
        if not target_met:
            status = "insufficient_event_sample"
        elif not feasibility_pass:
            status = "quote_feasibility_gate_failed"
        elif concentration_warning:
            status = "quote_feasibility_pass_with_concentration_warning"
        else:
            status = "quote_feasibility_pass"

        output.append(
            {
                "schema_version": CATEGORY_SUMMARY_SCHEMA_VERSION,
                "category": category,
                "target_event_count": str(MIN_FEASIBILITY_EVENTS_PER_CATEGORY),
                "event_count": str(len(events)),
                "market_count": str(len(markets)),
                "valid_quote_observation_count": str(total_valid),
                "events_with_valid_quote": str(events_with),
                "markets_with_valid_quote": str(markets_with),
                "event_any_quote_coverage": _float_text(event_coverage),
                "market_any_quote_coverage": _float_text(market_coverage),
                "early_event_coverage": _float_text(early),
                "middle_event_coverage": _float_text(middle),
                "late_event_coverage": _float_text(late),
                "events_with_all_three_bands": str(all_three),
                "all_three_band_event_coverage": _float_text(all_three_coverage),
                "median_valid_observations_per_event": _float_text(med),
                "p90_valid_observations_per_event": _float_text(p90),
                "max_event_observation_share": _float_text(max_share),
                "top_decile_event_observation_share": _float_text(top_decile_share),
                "sample_target_met": _bool_text(target_met),
                "quote_feasibility_pass": _bool_text(feasibility_pass),
                "concentration_warning": _bool_text(concentration_warning),
                "status": status,
            }
        )
    return output


def validate_collected_rows(
    rows: HistoricalFeasibilityRows,
    *,
    run_id: str,
    require_summary: bool = True,
) -> dict[str, int]:
    event_ids: set[str] = set()
    event_category: dict[str, str] = {}
    for row in rows.events:
        _validate_exact_fields(row, EVENT_FIELDS, "event")
        _validate_lineage(row, run_id)
        event = _required_text(row["event_ticker"], "event_ticker")
        if event in event_ids:
            raise HistoricalFeasibilityError(f"duplicate event {event}")
        if row["category"] not in TARGET_CATEGORIES:
            raise HistoricalFeasibilityError(f"event {event} has unsupported category")
        event_ids.add(event)
        event_category[event] = row["category"]

    market_ids: set[str] = set()
    market_event: dict[str, str] = {}
    market_category: dict[str, str] = {}
    market_close: dict[str, datetime] = {}
    for row in rows.markets:
        _validate_exact_fields(row, MARKET_FIELDS, "market")
        _validate_lineage(row, run_id)
        ticker = _required_text(row["ticker"], "ticker")
        if ticker in market_ids:
            raise HistoricalFeasibilityError(f"duplicate market {ticker}")
        event = row["event_ticker"]
        if event not in event_ids:
            raise HistoricalFeasibilityError(f"market {ticker} references unknown event")
        if row["category"] != event_category[event]:
            raise HistoricalFeasibilityError(f"market {ticker} category mismatch")
        if row["market_type"] != "binary" or row["status"] != "finalized":
            raise HistoricalFeasibilityError(f"market {ticker} is not finalized binary")
        if row["mve_collection_ticker"]:
            raise HistoricalFeasibilityError(f"market {ticker} is multivariate/combo")
        settlement = _parse_utc(row["settlement_ts"], "settlement_ts")
        expected_tier = "historical" if settlement < rows.cutoff.market_settled_ts else "live"
        if row["route_tier"] != expected_tier:
            raise HistoricalFeasibilityError(f"market {ticker} route tier disagrees with cutoff")
        if row["selection_hash"] != _selection_hash(ticker):
            raise HistoricalFeasibilityError(f"market {ticker} selection hash mismatch")
        market_ids.add(ticker)
        market_event[ticker] = event
        market_category[ticker] = row["category"]
        market_close[ticker] = _parse_utc(row["close_time"], "close_time")

    windows_by_market: dict[str, list[Mapping[str, str]]] = {ticker: [] for ticker in market_ids}
    windows_by_raw: dict[tuple[str, str, str, str], Mapping[str, str]] = {}
    for row in rows.windows:
        _validate_exact_fields(row, WINDOW_FIELDS, "window")
        _validate_lineage(row, run_id)
        ticker = row["ticker"]
        if ticker not in market_ids:
            raise HistoricalFeasibilityError(f"window references unknown market {ticker}")
        if row["event_ticker"] != market_event[ticker] or row["category"] != market_category[ticker]:
            raise HistoricalFeasibilityError(f"window identity mismatch for market {ticker}")
        close_ts = int(market_close[ticker].timestamp())
        expected_start = close_ts - WINDOW_START_DAYS_BEFORE_CLOSE * 86400
        expected_end = close_ts - WINDOW_END_DAYS_BEFORE_CLOSE * 86400
        if int(row["window_start_ts"]) != expected_start or int(row["window_end_ts"]) != expected_end:
            raise HistoricalFeasibilityError(f"window bounds mismatch for market {ticker}")
        raw_key = (ticker, row["raw_source"], row["raw_session_id"], row["raw_request_id"])
        if raw_key in windows_by_raw:
            raise HistoricalFeasibilityError(f"duplicate request-chunk lineage for market {ticker}")
        windows_by_raw[raw_key] = row
        windows_by_market[ticker].append(row)

    for ticker in market_ids:
        actual = sorted(
            windows_by_market[ticker], key=lambda row: int(row["request_chunk_index"])
        )
        close_ts = int(market_close[ticker].timestamp())
        expected_start = close_ts - WINDOW_START_DAYS_BEFORE_CLOSE * 86400
        expected_end = close_ts - WINDOW_END_DAYS_BEFORE_CLOSE * 86400
        expected_chunks = _candle_request_chunks(expected_start, expected_end)
        actual_chunks = [
            (int(row["request_chunk_index"]), int(row["request_start_ts"]), int(row["request_end_ts"]))
            for row in actual
        ]
        if actual_chunks != expected_chunks:
            raise HistoricalFeasibilityError(
                f"request chunks for market {ticker} do not exactly cover the feasibility window"
            )

    obs_by_raw: dict[tuple[str, str, str, str], list[Mapping[str, str]]] = {
        key: [] for key in windows_by_raw
    }
    seen_end_by_market: dict[str, set[int]] = {ticker: set() for ticker in market_ids}
    for row in rows.observations:
        _validate_exact_fields(row, OBSERVATION_FIELDS, "observation")
        _validate_lineage(row, run_id)
        ticker = row["ticker"]
        if ticker not in market_ids:
            raise HistoricalFeasibilityError(f"observation references unknown market {ticker}")
        if row["event_ticker"] != market_event[ticker] or row["category"] != market_category[ticker]:
            raise HistoricalFeasibilityError(f"observation identity mismatch for {ticker}")
        close = _parse_utc(row["close_time"], "observation.close_time")
        if close != market_close[ticker]:
            raise HistoricalFeasibilityError(f"observation close_time mismatch for {ticker}")
        end_period_ts = int(row["end_period_ts"])
        if end_period_ts in seen_end_by_market[ticker]:
            raise HistoricalFeasibilityError(f"duplicate candle end_period_ts {end_period_ts} for {ticker}")
        seen_end_by_market[ticker].add(end_period_ts)
        ttc = int(row["time_to_close_seconds"])
        if ttc != int(close.timestamp()) - end_period_ts:
            raise HistoricalFeasibilityError(f"observation exact time_to_close mismatch for {ticker}")
        if row["time_band"] != _time_band(ttc):
            raise HistoricalFeasibilityError(f"observation time band mismatch for {ticker}")
        if row["valid_quote_observation"] == "true":
            if not row["q_mid"] or not row["spread"] or row["exclusion_reason"]:
                raise HistoricalFeasibilityError(f"valid observation malformed for {ticker}")
        else:
            if row["q_mid"] or row["spread"] or not row["exclusion_reason"]:
                raise HistoricalFeasibilityError(f"invalid observation malformed for {ticker}")
        raw_key = (ticker, row["raw_source"], row["raw_session_id"], row["raw_request_id"])
        if raw_key not in windows_by_raw:
            raise HistoricalFeasibilityError(f"observation for {ticker} has no matching request chunk")
        window = windows_by_raw[raw_key]
        if not int(window["request_start_ts"]) <= end_period_ts <= int(window["request_end_ts"]):
            raise HistoricalFeasibilityError(f"observation for {ticker} falls outside its raw request chunk")
        obs_by_raw[raw_key].append(row)

    for raw_key, window in windows_by_raw.items():
        observations = obs_by_raw[raw_key]
        valid = [row for row in observations if row["valid_quote_observation"] == "true"]
        pairs = [row for row in observations if row["quote_pair_present"] == "true"]
        crossed = [row for row in observations if row["crossed_close"] == "true"]
        expected_counts = {
            "candle_count": len(observations),
            "quote_pair_count": len(pairs),
            "valid_quote_observation_count": len(valid),
            "invalid_quote_observation_count": len(observations) - len(valid),
            "crossed_quote_count": len(crossed),
            "early_valid_count": sum(1 for row in valid if row["time_band"] == "early_5d_to_7d"),
            "middle_valid_count": sum(1 for row in valid if row["time_band"] == "middle_3d_to_5d"),
            "late_valid_count": sum(1 for row in valid if row["time_band"] == "late_1d_to_3d"),
        }
        for field, expected in expected_counts.items():
            if int(window[field]) != expected:
                raise HistoricalFeasibilityError(
                    f"request chunk count {field} mismatch for {window['ticker']}"
                )

    if require_summary:
        if len(rows.category_summary) != len(TARGET_CATEGORIES):
            raise HistoricalFeasibilityError("category summary must contain one row per target category")
        rebuilt = build_category_summary_rows(
            HistoricalFeasibilityRows(**{**rows.__dict__, "category_summary": ()})
        )
        if tuple(rebuilt) != tuple(rows.category_summary):
            raise HistoricalFeasibilityError("category summary does not match collected rows")

    return {
        "event_rows": len(rows.events),
        "market_rows": len(rows.markets),
        "window_rows": len(rows.windows),
        "observation_rows": len(rows.observations),
        "valid_quote_observation_rows": sum(
            1 for row in rows.observations if row["valid_quote_observation"] == "true"
        ),
        "cross_tier_observation_count": rows.cross_tier_observation_count,
        "cross_tier_market_count": rows.cross_tier_market_count,
        "cross_tier_recovery_fetch_count": rows.cross_tier_recovery_fetch_count,
        "unclassifiable_event_count": rows.unclassifiable_event_count,
    }


def write_collected_csvs(
    directory: str | Path,
    *,
    run_id: str,
    rows: HistoricalFeasibilityRows,
) -> CsvPaths:
    base = Path(directory)
    base.mkdir(parents=True, exist_ok=True)
    paths = CsvPaths(
        events=base / f"{run_id}_events.csv",
        markets=base / f"{run_id}_markets.csv",
        windows=base / f"{run_id}_windows.csv",
        observations=base / f"{run_id}_observations.csv",
        category_summary=base / f"{run_id}_category_summary.csv",
    )
    _write_csv(paths.events, EVENT_FIELDS, rows.events)
    _write_csv(paths.markets, MARKET_FIELDS, rows.markets)
    _write_csv(paths.windows, WINDOW_FIELDS, rows.windows)
    _write_csv(paths.observations, OBSERVATION_FIELDS, rows.observations)
    _write_csv(paths.category_summary, CATEGORY_SUMMARY_FIELDS, rows.category_summary)
    return paths


def _validate_target_categories(categories: Sequence[str]) -> tuple[str, ...]:
    if isinstance(categories, (str, bytes)):
        raise ValueError("target_categories must be a sequence of category names")
    normalized: list[str] = []
    seen: set[str] = set()
    for category in categories:
        if category not in TARGET_CATEGORIES:
            raise ValueError(f"unsupported target category {category!r}")
        if category in seen:
            raise ValueError(f"duplicate target category {category!r}")
        seen.add(category)
        normalized.append(category)
    if not normalized:
        raise ValueError("target_categories must not be empty")
    return tuple(normalized)


def _fetch_market_tier(
    client: RawFirstJsonClient,
    *,
    event_ticker: str,
    tier: str,
    max_pages: int,
) -> list[tuple[dict[str, Any], str, RawFirstJsonResponse]]:
    if tier not in {"historical", "live"}:
        raise ValueError("tier must be historical or live")
    path = "/historical/markets" if tier == "historical" else "/markets"
    cursor = ""
    output: list[tuple[dict[str, Any], str, RawFirstJsonResponse]] = []
    for _ in range(max_pages):
        params: dict[str, Any] = {"event_ticker": event_ticker, "limit": 1000}
        if tier == "live":
            params["status"] = "settled"
        if cursor:
            params["cursor"] = cursor
        response = client.get_json(path, params=params)
        markets, cursor = _validate_market_list(response.payload)
        output.extend((market, tier, response) for market in markets)
        if not cursor:
            return output
    raise HistoricalFeasibilityError(
        f"{tier} market pagination for {event_ticker} exceeded max_pages={max_pages}"
    )


def _reconcile_market_tiers(
    client: RawFirstJsonClient,
    *,
    event_ticker: str,
    cutoff: HistoricalCutoff,
    candidates: Sequence[tuple[dict[str, Any], str, RawFirstJsonResponse]],
) -> tuple[
    list[tuple[dict[str, Any], str, RawFirstJsonResponse]], int, set[str], int
]:
    grouped: dict[str, list[tuple[dict[str, Any], str, RawFirstJsonResponse]]] = {}
    off_tier_count = 0
    off_tier_tickers: set[str] = set()
    for market, observed_tier, response in candidates:
        ticker = _required_text(market.get("ticker"), "market.ticker")
        if _required_text(market.get("event_ticker"), "market.event_ticker") != event_ticker:
            raise HistoricalFeasibilityError("market list returned wrong event_ticker")
        settlement = _parse_utc(market.get("settlement_ts"), "market.settlement_ts")
        canonical = "historical" if settlement < cutoff.market_settled_ts else "live"
        if observed_tier != canonical:
            off_tier_count += 1
            off_tier_tickers.add(ticker)
        grouped.setdefault(ticker, []).append((market, observed_tier, response))

    reconciled: list[tuple[dict[str, Any], str, RawFirstJsonResponse]] = []
    recovery_count = 0
    for ticker, copies in grouped.items():
        settlements = {
            _required_timestamp_text(item[0].get("settlement_ts"), "market.settlement_ts")
            for item in copies
        }
        if len(settlements) != 1:
            raise HistoricalFeasibilityError(f"market {ticker} has conflicting settlement timestamps")
        settlement = _parse_utc(next(iter(settlements)), "market.settlement_ts")
        canonical = "historical" if settlement < cutoff.market_settled_ts else "live"
        canonical_copies = [item for item in copies if item[1] == canonical]
        if len(canonical_copies) > 1:
            raise HistoricalFeasibilityError(f"market {ticker} has duplicate canonical-tier copies")
        if canonical_copies:
            reconciled.append(canonical_copies[0])
            continue

        recovery_count += 1
        path = f"/historical/markets/{ticker}" if canonical == "historical" else f"/markets/{ticker}"
        response = client.get_json(path)
        market = response.payload.get("market")
        if not isinstance(market, dict):
            raise HistoricalFeasibilityError(f"canonical recovery for {ticker} did not return market object")
        if _required_text(market.get("ticker"), "market.ticker") != ticker:
            raise HistoricalFeasibilityError(f"canonical recovery ticker mismatch for {ticker}")
        if _required_text(market.get("event_ticker"), "market.event_ticker") != event_ticker:
            raise HistoricalFeasibilityError(f"canonical recovery event mismatch for {ticker}")
        recovered_settlement = _parse_utc(market.get("settlement_ts"), "market.settlement_ts")
        recovered_tier = "historical" if recovered_settlement < cutoff.market_settled_ts else "live"
        if recovered_tier != canonical:
            raise HistoricalFeasibilityError(f"canonical recovery routing conflict for {ticker}")
        reconciled.append((market, canonical, response))

    reconciled.sort(key=lambda item: item[0]["ticker"])
    return reconciled, off_tier_count, off_tier_tickers, recovery_count


def _candle_request_chunks(start_ts: int, end_ts: int) -> list[tuple[int, int, int]]:
    """Split an inclusive analysis window into bounded raw API request chunks.

    Kalshi rejects a 1-minute candlestick request that would span more than
    5,000 candles. A 24-hour chunk spans at most 1,440 one-minute periods.
    Adjacent chunks are non-overlapping in integer Unix-second space so one
    source candle cannot be duplicated merely because of request boundaries.
    """

    if start_ts > end_ts:
        raise ValueError("start_ts must be <= end_ts")
    chunks: list[tuple[int, int, int]] = []
    current = start_ts
    index = 1
    while current <= end_ts:
        chunk_end = min(current + CANDLE_REQUEST_CHUNK_SECONDS, end_ts)
        chunks.append((index, current, chunk_end))
        current = chunk_end + 1
        index += 1
    return chunks


def _fetch_candles(
    client: RawFirstJsonClient,
    *,
    route_tier: str,
    series_ticker: str,
    ticker: str,
    start_ts: int,
    end_ts: int,
) -> RawFirstJsonResponse:
    params: dict[str, Any] = {
        "start_ts": start_ts,
        "end_ts": end_ts,
        "period_interval": 1,
    }
    if route_tier == "historical":
        path = f"/historical/markets/{ticker}/candlesticks"
    elif route_tier == "live":
        path = f"/series/{series_ticker}/markets/{ticker}/candlesticks"
        params["include_latest_before_start"] = "false"
    else:
        raise HistoricalFeasibilityError(f"unsupported route_tier {route_tier!r}")
    return client.get_json(path, params=params)


def _sample_markets(
    items: Sequence[tuple[dict[str, Any], str, RawFirstJsonResponse]],
    *,
    max_markets_per_event: int,
) -> list[tuple[dict[str, Any], str, RawFirstJsonResponse]]:
    return sorted(
        items,
        key=lambda item: (_selection_hash(_required_text(item[0].get("ticker"), "market.ticker")), item[0]["ticker"]),
    )[:max_markets_per_event]


def _check_market_uniqueness(
    items: Sequence[tuple[dict[str, Any], str, RawFirstJsonResponse]],
    existing: set[str],
) -> None:
    local: set[str] = set()
    for market, _tier, _response in items:
        ticker = _required_text(market.get("ticker"), "market.ticker")
        if ticker in existing or ticker in local:
            raise HistoricalFeasibilityError(f"duplicate selected market ticker {ticker}")
        local.add(ticker)


def _is_baseline_market(market: Mapping[str, Any]) -> bool:
    # Deliberately outcome-blind: do not access market['result'].
    return (
        market.get("market_type") == "binary"
        and market.get("status") == "finalized"
        and not _text_or_blank(market.get("mve_collection_ticker"))
    )


def _validate_cutoff(payload: Mapping[str, Any]) -> HistoricalCutoff:
    return HistoricalCutoff(
        market_settled_ts=_parse_utc(payload.get("market_settled_ts"), "market_settled_ts"),
        trades_created_ts=_parse_utc(payload.get("trades_created_ts"), "trades_created_ts"),
        orders_updated_ts=_parse_utc(payload.get("orders_updated_ts"), "orders_updated_ts"),
        market_positions_last_updated_ts=_optional_utc(
            payload.get("market_positions_last_updated_ts"), "market_positions_last_updated_ts"
        ),
    )


def _validate_event_list(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
    events = payload.get("events")
    cursor = payload.get("cursor")
    if not isinstance(events, list) or not isinstance(cursor, str):
        raise HistoricalFeasibilityError("events response must contain list events and text cursor")
    output: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            raise HistoricalFeasibilityError("events response contains non-object item")
        output.append(event)
    return output, cursor


def _validate_market_list(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], str]:
    markets = payload.get("markets")
    cursor = payload.get("cursor")
    if not isinstance(markets, list) or not isinstance(cursor, str):
        raise HistoricalFeasibilityError("market response must contain list markets and text cursor")
    output: list[dict[str, Any]] = []
    for market in markets:
        if not isinstance(market, dict):
            raise HistoricalFeasibilityError("market response contains non-object item")
        _required_text(market.get("ticker"), "market.ticker")
        _required_text(market.get("event_ticker"), "market.event_ticker")
        _required_timestamp_text(market.get("settlement_ts"), "market.settlement_ts")
        output.append(market)
    return output, cursor


def _time_band(time_to_close_seconds: int) -> str:
    day = 86400
    if 5 * day <= time_to_close_seconds <= 7 * day:
        return "early_5d_to_7d"
    if 3 * day <= time_to_close_seconds < 5 * day:
        return "middle_3d_to_5d"
    if 1 * day <= time_to_close_seconds < 3 * day:
        return "late_1d_to_3d"
    raise HistoricalFeasibilityError(
        f"time_to_close_seconds {time_to_close_seconds} outside 1d..7d"
    )


def _selection_hash(ticker: str) -> str:
    return hashlib.sha256(ticker.encode("utf-8")).hexdigest()


def _lineage(run_id: str, raw: _RawReference, route_tier: str) -> dict[str, str]:
    return {
        "run_id": run_id,
        "raw_source": _required_text(raw.source, "raw.source"),
        "raw_session_id": _required_text(raw.session_id, "raw.session_id"),
        "raw_request_id": _required_text(raw.request_id, "raw.request_id"),
        "route_tier": route_tier,
    }


def _validate_lineage(row: Mapping[str, str], run_id: str) -> None:
    if row.get("run_id") != run_id:
        raise HistoricalFeasibilityError("derived row has wrong run_id")
    for field in ("raw_source", "raw_session_id", "raw_request_id", "route_tier"):
        _required_text(row.get(field), field)


def _validate_exact_fields(row: Mapping[str, str], fields: Sequence[str], label: str) -> None:
    if tuple(row.keys()) != tuple(fields):
        raise HistoricalFeasibilityError(
            f"{label} row fields differ from schema: {tuple(row.keys())!r}"
        )


def _mapping_or_none(value: Any, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HistoricalFeasibilityError(f"{field} must be object or null")
    return value


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise HistoricalFeasibilityError("boolean is not a decimal value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HistoricalFeasibilityError(f"invalid decimal value {value!r}") from exc
    if not result.is_finite():
        raise HistoricalFeasibilityError("decimal value must be finite")
    return result


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value, "f")


def _float_text(value: float) -> str:
    return f"{value:.6f}"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _bool_or_blank(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, bool):
        raise HistoricalFeasibilityError("boolean source field must be bool or null")
    return _bool_text(value)


def _text_or_blank(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise HistoricalFeasibilityError(f"{field} must be non-empty text")
    return value


def _required_timestamp_text(value: Any, field: str) -> str:
    parsed = _parse_utc(value, field)
    return _format_utc(parsed)


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise HistoricalFeasibilityError(f"{field} must be timestamp text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalFeasibilityError(f"{field} is invalid timestamp") from exc
    if parsed.tzinfo is None:
        raise HistoricalFeasibilityError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _optional_utc(value: Any, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    return _parse_utc(value, field)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ratio(numerator: int, denominator: int) -> float:
    return (numerator / denominator) if denominator else 0.0


def _percentile_nearest_rank(values: Sequence[int], probability: float) -> float:
    if not values:
        return 0.0
    rank = max(1, math.ceil(probability * len(values)))
    return float(sorted(values)[rank - 1])


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
