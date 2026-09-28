"""Outcome-blind raw-first Kalshi Sports historical collection helpers.

The functions in this module are network-client agnostic. Callers provide a
GET-only raw-first client whose response is returned only after the HTTP
exchange has been persisted. The collector never reads the final market
``result`` field; outcome materialization is a later post-staleness step.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .kalshi_historical_validation import (
    HistoricalCutoff,
    HistoricalEndpointValidationError,
    RawFirstJsonClient,
    RawFirstJsonResponse,
    validate_candlestick_payload,
    validate_cutoff_payload,
    validate_events_payload,
    validate_historical_market_list_payload,
)
from .sports_historical_schema import (
    ANCHOR_DAYS,
    ANCHOR_FIELDS,
    CANDLE_FIELDS,
    EVENT_FIELDS,
    MARKET_FIELDS,
    PRE_STALENESS_COLLECTOR_TABLES,
)


class SportsHistoricalCollectionError(RuntimeError):
    """Raised when a complete bounded Sports history sample cannot be built."""


@dataclass(frozen=True)
class SportsHistoricalRows:
    events: tuple[dict[str, str], ...]
    markets: tuple[dict[str, str], ...]
    anchors: tuple[dict[str, str], ...]
    candles: tuple[dict[str, str], ...]
    cutoff: HistoricalCutoff
    cutoff_raw_source: str
    cutoff_raw_session_id: str
    cutoff_raw_request_id: str
    event_pages_scanned: int
    cross_tier_observation_count: int = 0
    cross_tier_market_count: int = 0
    cross_tier_recovery_fetch_count: int = 0
    unclassifiable_event_count: int = 0

    @property
    def selected_event_count(self) -> int:
        return len(self.events)

    @property
    def selected_market_count(self) -> int:
        return len(self.markets)


@dataclass(frozen=True)
class CsvPaths:
    events: Path
    markets: Path
    anchors: Path
    candles: Path

    def all(self) -> tuple[Path, ...]:
        return (self.events, self.markets, self.anchors, self.candles)


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


def collect_sports_historical_rows(
    client: RawFirstJsonClient,
    *,
    run_id: str,
    max_sports_events: int,
    max_event_pages: int = 50,
    max_market_pages_per_tier: int = 5,
    anchor_lookback_hours: int = 24,
) -> SportsHistoricalRows:
    """Collect a bounded outcome-blind Sports sample at 7d/3d/1d anchors.

    Event enumeration uses the normal event surface because Kalshi keeps event
    metadata accessible across the historical cutoff. For each accepted Sports
    event, market discovery explicitly queries both the historical and live
    settled-market tiers and verifies that settlement timestamps agree with the
    captured cutoff. Candlestick routing is based on market settlement time,
    never on the candle timestamp.
    """

    _required_text(run_id, "run_id")
    if max_sports_events <= 0:
        raise ValueError("max_sports_events must be positive")
    if max_event_pages <= 0:
        raise ValueError("max_event_pages must be positive")
    if max_market_pages_per_tier <= 0:
        raise ValueError("max_market_pages_per_tier must be positive")
    if not 1 <= anchor_lookback_hours <= 48:
        raise ValueError("anchor_lookback_hours must be between 1 and 48")

    cutoff_response = client.get_json("/historical/cutoff")
    cutoff = validate_cutoff_payload(cutoff_response.payload)

    events_rows: list[dict[str, str]] = []
    market_rows: list[dict[str, str]] = []
    anchor_rows: list[dict[str, str]] = []
    candle_rows: list[dict[str, str]] = []
    selected_events: set[str] = set()
    selected_markets: set[str] = set()
    cross_tier_observation_count = 0
    cross_tier_market_tickers: set[str] = set()
    cross_tier_recovery_fetch_count = 0
    unclassifiable_event_count = 0
    cursor = ""
    pages_scanned = 0

    for page_index in range(max_event_pages):
        params: dict[str, Any] = {
            "status": "settled",
            "limit": 200,
            "with_nested_markets": "false",
        }
        if cursor:
            params["cursor"] = cursor
        event_response = client.get_json("/events", params=params)
        pages_scanned += 1
        events, cursor = validate_events_payload(
            event_response.payload, require_identity_fields=False
        )

        for event in events:
            category = event.get("category")
            if not isinstance(category, str) or not category.strip():
                unclassifiable_event_count += 1
                continue
            if category != "Sports":
                continue
            event_ticker = _required_text(event.get("event_ticker"), "event.event_ticker")
            if event_ticker in selected_events:
                continue
            series_ticker = _required_text(event.get("series_ticker"), "event.series_ticker")

            historical = _fetch_market_tier(
                client,
                event_ticker=event_ticker,
                tier="historical",
                cutoff=cutoff,
                max_pages=max_market_pages_per_tier,
            )
            live = _fetch_market_tier(
                client,
                event_ticker=event_ticker,
                tier="live",
                cutoff=cutoff,
                max_pages=max_market_pages_per_tier,
            )
            (
                market_candidates,
                event_cross_tier_observations,
                event_cross_tier_tickers,
                event_recovery_fetches,
            ) = _reconcile_market_tiers(
                client,
                event_ticker=event_ticker,
                cutoff=cutoff,
                candidates=historical + live,
            )
            cross_tier_observation_count += event_cross_tier_observations
            cross_tier_market_tickers.update(event_cross_tier_tickers)
            cross_tier_recovery_fetch_count += event_recovery_fetches
            eligible = [
                item
                for item in market_candidates
                if _market_is_baseline_candidate(item[0])
            ]
            if not eligible:
                continue

            _check_market_ticker_uniqueness(eligible, selected_markets)
            events_rows.append(
                build_event_row(run_id=run_id, event=event, response=event_response)
            )
            selected_events.add(event_ticker)

            for market, route_tier, market_response in eligible:
                ticker = _required_text(market.get("ticker"), "market.ticker")
                selected_markets.add(ticker)
                market_rows.append(
                    build_market_row(
                        run_id=run_id,
                        market=market,
                        route_tier=route_tier,
                        response=market_response,
                    )
                )
                close_time = _parse_utc_timestamp(market.get("close_time"), "market.close_time")
                for anchor_name, days_before_close in ANCHOR_DAYS.items():
                    anchor_dt = close_time - timedelta(days=days_before_close)
                    anchor_ts = int(anchor_dt.timestamp())
                    start_ts = anchor_ts - anchor_lookback_hours * 3600
                    candle_response = _fetch_candle_window(
                        client,
                        route_tier=route_tier,
                        series_ticker=series_ticker,
                        ticker=ticker,
                        start_ts=start_ts,
                        end_ts=anchor_ts,
                    )
                    summary = validate_candlestick_payload(
                        candle_response.payload,
                        expected_ticker=ticker,
                        tier=route_tier,
                    )
                    normalized_candles = build_candle_rows(
                        run_id=run_id,
                        ticker=ticker,
                        anchor_name=anchor_name,
                        anchor_ts=anchor_ts,
                        window_start_ts=start_ts,
                        route_tier=route_tier,
                        response=candle_response,
                    )
                    candle_rows.extend(normalized_candles)
                    anchor_rows.append(
                        build_anchor_row(
                            run_id=run_id,
                            ticker=ticker,
                            anchor_name=anchor_name,
                            anchor_ts=anchor_ts,
                            window_start_ts=start_ts,
                            route_tier=route_tier,
                            response=candle_response,
                            normalized_candles=normalized_candles,
                            expected_candle_count=summary.candle_count,
                            expected_quote_pair_count=summary.quote_pair_close_count,
                        )
                    )

            if len(selected_events) >= max_sports_events:
                rows = SportsHistoricalRows(
                    events=tuple(events_rows),
                    markets=tuple(market_rows),
                    anchors=tuple(anchor_rows),
                    candles=tuple(candle_rows),
                    cutoff=cutoff,
                    cutoff_raw_source=cutoff_response.raw_record.source,
                    cutoff_raw_session_id=cutoff_response.raw_record.session_id,
                    cutoff_raw_request_id=cutoff_response.raw_record.request_id,
                    event_pages_scanned=pages_scanned,
                    cross_tier_observation_count=cross_tier_observation_count,
                    cross_tier_market_count=len(cross_tier_market_tickers),
                    cross_tier_recovery_fetch_count=cross_tier_recovery_fetch_count,
                    unclassifiable_event_count=unclassifiable_event_count,
                )
                validate_collected_rows(rows, run_id=run_id)
                return rows

        if not cursor:
            break
    else:
        if cursor:
            raise SportsHistoricalCollectionError(
                "settled-event discovery still had another cursor after "
                f"max_event_pages={max_event_pages}; partial discovery is not accepted"
            )

    raise SportsHistoricalCollectionError(
        f"requested {max_sports_events} Sports events but bounded discovery found "
        f"only {len(selected_events)} with baseline-candidate settled markets"
    )


def build_event_row(
    *,
    run_id: str,
    event: Mapping[str, Any],
    response: RawFirstJsonResponse,
) -> dict[str, str]:
    return {
        **_lineage(run_id, response.raw_record, "metadata"),
        "event_ticker": _required_text(event.get("event_ticker"), "event.event_ticker"),
        "series_ticker": _required_text(event.get("series_ticker"), "event.series_ticker"),
        "category": _required_text(event.get("category"), "event.category"),
        "mutually_exclusive": _bool_or_blank(event.get("mutually_exclusive")),
        "strike_date": _text_or_blank(event.get("strike_date")),
    }


def build_market_row(
    *,
    run_id: str,
    market: Mapping[str, Any],
    route_tier: str,
    response: RawFirstJsonResponse,
) -> dict[str, str]:
    if route_tier not in {"historical", "live"}:
        raise ValueError("market route_tier must be historical or live")
    return {
        **_lineage(run_id, response.raw_record, route_tier),
        "ticker": _required_text(market.get("ticker"), "market.ticker"),
        "event_ticker": _required_text(market.get("event_ticker"), "market.event_ticker"),
        "market_type": _text_or_blank(market.get("market_type")),
        "status": _text_or_blank(market.get("status")),
        "open_time": _required_timestamp_text(market.get("open_time"), "market.open_time"),
        "close_time": _required_timestamp_text(market.get("close_time"), "market.close_time"),
        "settlement_ts": _required_timestamp_text(market.get("settlement_ts"), "market.settlement_ts"),
        "mve_collection_ticker": _text_or_blank(market.get("mve_collection_ticker")),
        "is_provisional": _bool_or_blank(market.get("is_provisional")),
    }


def build_candle_rows(
    *,
    run_id: str,
    ticker: str,
    anchor_name: str,
    anchor_ts: int,
    window_start_ts: int,
    route_tier: str,
    response: RawFirstJsonResponse,
) -> list[dict[str, str]]:
    if route_tier not in {"historical", "live"}:
        raise ValueError("candle route_tier must be historical or live")
    if anchor_name not in ANCHOR_DAYS:
        raise ValueError(f"unsupported anchor_name {anchor_name!r}")

    payload_ticker = _required_text(response.payload.get("ticker"), "candles.ticker")
    if payload_ticker != ticker:
        raise SportsHistoricalCollectionError(
            f"candlestick ticker mismatch: expected {ticker!r}, got {payload_ticker!r}"
        )
    candles = response.payload.get("candlesticks")
    if not isinstance(candles, list):
        raise SportsHistoricalCollectionError("candlesticks must be a list")

    close_key = "close" if route_tier == "historical" else "close_dollars"
    volume_key = "volume" if route_tier == "historical" else "volume_fp"
    oi_key = "open_interest" if route_tier == "historical" else "open_interest_fp"
    family = "historical_plain" if route_tier == "historical" else "live_dollars"
    rows: list[dict[str, str]] = []
    seen_ends: set[int] = set()

    for index, candle in enumerate(candles):
        if not isinstance(candle, Mapping):
            raise SportsHistoricalCollectionError(f"candlesticks[{index}] must be an object")
        end_ts = candle.get("end_period_ts")
        if not isinstance(end_ts, int) or isinstance(end_ts, bool):
            raise SportsHistoricalCollectionError(
                f"candlesticks[{index}].end_period_ts must be an integer"
            )
        if end_ts < window_start_ts or end_ts > anchor_ts:
            raise SportsHistoricalCollectionError(
                f"candlestick end {end_ts} falls outside requested anchor window "
                f"[{window_start_ts}, {anchor_ts}]"
            )
        if end_ts in seen_ends:
            raise SportsHistoricalCollectionError(
                f"duplicate end_period_ts {end_ts} for {ticker} {anchor_name}"
            )
        seen_ends.add(end_ts)

        bid = _mapping_or_none(candle.get("yes_bid"), f"candlesticks[{index}].yes_bid")
        ask = _mapping_or_none(candle.get("yes_ask"), f"candlesticks[{index}].yes_ask")
        price = _mapping_or_none(candle.get("price"), f"candlesticks[{index}].price")
        bid_close = _decimal_text(None if bid is None else bid.get(close_key))
        ask_close = _decimal_text(None if ask is None else ask.get(close_key))
        price_close = _decimal_text(None if price is None else price.get(close_key))
        quote_pair = bool(bid_close and ask_close)
        crossed = False
        if quote_pair:
            crossed = Decimal(bid_close) > Decimal(ask_close)

        rows.append(
            {
                **_lineage(run_id, response.raw_record, route_tier),
                "ticker": ticker,
                "anchor_name": anchor_name,
                "anchor_ts": str(anchor_ts),
                "source_field_family": family,
                "end_period_ts": str(end_ts),
                "period_interval_minutes": "1",
                "yes_bid_close": bid_close,
                "yes_ask_close": ask_close,
                "price_close": price_close,
                "volume": _decimal_text(candle.get(volume_key)),
                "open_interest": _decimal_text(candle.get(oi_key)),
                "quote_pair_present": _bool_text(quote_pair),
                "crossed_close": _bool_text(crossed),
            }
        )

    rows.sort(key=lambda row: int(row["end_period_ts"]))
    return rows


def build_anchor_row(
    *,
    run_id: str,
    ticker: str,
    anchor_name: str,
    anchor_ts: int,
    window_start_ts: int,
    route_tier: str,
    response: RawFirstJsonResponse,
    normalized_candles: Sequence[Mapping[str, str]],
    expected_candle_count: int,
    expected_quote_pair_count: int,
) -> dict[str, str]:
    if len(normalized_candles) != expected_candle_count:
        raise SportsHistoricalCollectionError(
            "normalized candle count does not match validated raw candle count"
        )
    quote_rows = [row for row in normalized_candles if row["quote_pair_present"] == "true"]
    if len(quote_rows) != expected_quote_pair_count:
        raise SportsHistoricalCollectionError(
            "normalized quote-pair count does not match validated raw candle count"
        )
    latest_real = max((int(row["end_period_ts"]) for row in normalized_candles), default=None)
    latest_quote = max((int(row["end_period_ts"]) for row in quote_rows), default=None)
    quote_age = None if latest_quote is None else anchor_ts - latest_quote
    if quote_age is not None and quote_age < 0:
        raise SportsHistoricalCollectionError("latest quote occurs after anchor")

    return {
        **_lineage(run_id, response.raw_record, route_tier),
        "ticker": ticker,
        "anchor_name": anchor_name,
        "anchor_ts": str(anchor_ts),
        "window_start_ts": str(window_start_ts),
        "window_end_ts": str(anchor_ts),
        "candle_count": str(len(normalized_candles)),
        "quote_pair_count": str(len(quote_rows)),
        "latest_real_candle_ts": "" if latest_real is None else str(latest_real),
        "latest_quote_pair_ts": "" if latest_quote is None else str(latest_quote),
        "latest_quote_age_seconds": "" if quote_age is None else str(quote_age),
    }


def validate_collected_rows(rows: SportsHistoricalRows, *, run_id: str) -> dict[str, int]:
    """Validate table relationships and outcome-blind invariants in memory."""

    event_by_ticker: dict[str, Mapping[str, str]] = {}
    for row in rows.events:
        _validate_row_shape(row, EVENT_FIELDS, run_id, "event")
        ticker = row["event_ticker"]
        if ticker in event_by_ticker:
            raise SportsHistoricalCollectionError(f"duplicate event_ticker {ticker!r}")
        if row["category"] != "Sports":
            raise SportsHistoricalCollectionError(f"non-Sports event row {ticker!r}")
        if row["route_tier"] != "metadata":
            raise SportsHistoricalCollectionError("event rows must use metadata route_tier")
        event_by_ticker[ticker] = row

    market_by_ticker: dict[str, Mapping[str, str]] = {}
    for row in rows.markets:
        _validate_row_shape(row, MARKET_FIELDS, run_id, "market")
        ticker = row["ticker"]
        if ticker in market_by_ticker:
            raise SportsHistoricalCollectionError(f"duplicate market ticker {ticker!r}")
        if row["event_ticker"] not in event_by_ticker:
            raise SportsHistoricalCollectionError(f"market {ticker!r} references unknown event")
        if row["market_type"] != "binary":
            raise SportsHistoricalCollectionError(f"market {ticker!r} is not binary")
        if row["status"] != "finalized":
            raise SportsHistoricalCollectionError(f"market {ticker!r} is not finalized")
        if row["mve_collection_ticker"]:
            raise SportsHistoricalCollectionError(f"market {ticker!r} is multivariate/combo")
        settlement = _parse_utc_timestamp(row["settlement_ts"], "settlement_ts")
        expected_tier = (
            "historical" if settlement < rows.cutoff.market_settled_ts else "live"
        )
        if row["route_tier"] != expected_tier:
            raise SportsHistoricalCollectionError(
                f"market {ticker!r} route {row['route_tier']!r} conflicts with cutoff"
            )
        market_by_ticker[ticker] = row

    anchors: dict[tuple[str, str], Mapping[str, str]] = {}
    for row in rows.anchors:
        _validate_row_shape(row, ANCHOR_FIELDS, run_id, "anchor")
        key = (row["ticker"], row["anchor_name"])
        if key in anchors:
            raise SportsHistoricalCollectionError(f"duplicate anchor row {key!r}")
        market = market_by_ticker.get(row["ticker"])
        if market is None:
            raise SportsHistoricalCollectionError(f"anchor {key!r} references unknown market")
        if row["anchor_name"] not in ANCHOR_DAYS:
            raise SportsHistoricalCollectionError(f"unknown anchor name {row['anchor_name']!r}")
        if row["route_tier"] != market["route_tier"]:
            raise SportsHistoricalCollectionError(f"anchor {key!r} route differs from market")
        close_dt = _parse_utc_timestamp(market["close_time"], "close_time")
        expected_anchor = int((close_dt - timedelta(days=ANCHOR_DAYS[row["anchor_name"]])).timestamp())
        if int(row["anchor_ts"]) != expected_anchor:
            raise SportsHistoricalCollectionError(f"anchor {key!r} timestamp does not match close-time formula")
        if int(row["window_end_ts"]) != int(row["anchor_ts"]):
            raise SportsHistoricalCollectionError(f"anchor {key!r} window_end_ts must equal anchor_ts")
        if int(row["window_start_ts"]) >= int(row["window_end_ts"]):
            raise SportsHistoricalCollectionError(f"anchor {key!r} has non-positive window")
        anchors[key] = row

    expected_anchor_names = set(ANCHOR_DAYS)
    for ticker in market_by_ticker:
        actual = {anchor_name for market_ticker, anchor_name in anchors if market_ticker == ticker}
        if actual != expected_anchor_names:
            raise SportsHistoricalCollectionError(
                f"market {ticker!r} anchor set {sorted(actual)!r} does not match predeclared anchors"
            )

    candle_groups: dict[tuple[str, str], list[Mapping[str, str]]] = {key: [] for key in anchors}
    for row in rows.candles:
        _validate_row_shape(row, CANDLE_FIELDS, run_id, "candle")
        key = (row["ticker"], row["anchor_name"])
        anchor = anchors.get(key)
        if anchor is None:
            raise SportsHistoricalCollectionError(f"candle references unknown anchor {key!r}")
        if row["route_tier"] != anchor["route_tier"]:
            raise SportsHistoricalCollectionError(f"candle {key!r} route differs from anchor")
        if row["anchor_ts"] != anchor["anchor_ts"]:
            raise SportsHistoricalCollectionError(f"candle {key!r} anchor_ts differs from anchor row")
        end_ts = int(row["end_period_ts"])
        if not int(anchor["window_start_ts"]) <= end_ts <= int(anchor["window_end_ts"]):
            raise SportsHistoricalCollectionError(f"candle {key!r} lies outside anchor window")
        expected_family = "historical_plain" if row["route_tier"] == "historical" else "live_dollars"
        if row["source_field_family"] != expected_family:
            raise SportsHistoricalCollectionError(f"candle {key!r} source field family mismatch")
        candle_groups[key].append(row)

    for key, anchor in anchors.items():
        group = candle_groups[key]
        ends = [int(row["end_period_ts"]) for row in group]
        if len(ends) != len(set(ends)):
            raise SportsHistoricalCollectionError(f"duplicate candle timestamp in anchor {key!r}")
        quote_rows = [row for row in group if row["quote_pair_present"] == "true"]
        latest_real = max(ends, default=None)
        latest_quote = max((int(row["end_period_ts"]) for row in quote_rows), default=None)
        if int(anchor["candle_count"]) != len(group):
            raise SportsHistoricalCollectionError(f"anchor {key!r} candle_count mismatch")
        if int(anchor["quote_pair_count"]) != len(quote_rows):
            raise SportsHistoricalCollectionError(f"anchor {key!r} quote_pair_count mismatch")
        if anchor["latest_real_candle_ts"] != ("" if latest_real is None else str(latest_real)):
            raise SportsHistoricalCollectionError(f"anchor {key!r} latest_real_candle_ts mismatch")
        if anchor["latest_quote_pair_ts"] != ("" if latest_quote is None else str(latest_quote)):
            raise SportsHistoricalCollectionError(f"anchor {key!r} latest_quote_pair_ts mismatch")
        expected_age = "" if latest_quote is None else str(int(anchor["anchor_ts"]) - latest_quote)
        if anchor["latest_quote_age_seconds"] != expected_age:
            raise SportsHistoricalCollectionError(f"anchor {key!r} latest_quote_age_seconds mismatch")

    for table_name, table_rows in (
        ("events", rows.events),
        ("markets", rows.markets),
        ("anchors", rows.anchors),
        ("candles", rows.candles),
    ):
        if table_name not in PRE_STALENESS_COLLECTOR_TABLES:
            raise AssertionError("unexpected pre-staleness table")
        for row in table_rows:
            if "result" in row:
                raise SportsHistoricalCollectionError(
                    f"outcome-blind table {table_name!r} exposes result"
                )

    return {
        "event_rows": len(rows.events),
        "market_rows": len(rows.markets),
        "anchor_rows": len(rows.anchors),
        "candle_rows": len(rows.candles),
        "anchors_with_quote_pair": sum(
            1 for row in rows.anchors if row["latest_quote_pair_ts"]
        ),
        "anchors_without_quote_pair": sum(
            1 for row in rows.anchors if not row["latest_quote_pair_ts"]
        ),
        "cross_tier_observation_count": rows.cross_tier_observation_count,
        "cross_tier_market_count": rows.cross_tier_market_count,
        "cross_tier_recovery_fetch_count": rows.cross_tier_recovery_fetch_count,
        "unclassifiable_event_count": rows.unclassifiable_event_count,
    }


def write_collected_csvs(
    root: str | Path,
    *,
    run_id: str,
    rows: SportsHistoricalRows,
) -> CsvPaths:
    """Write deterministic pilot-safe CSV tables after row validation."""

    validate_collected_rows(rows, run_id=run_id)
    root_path = Path(root)
    root_path.mkdir(parents=True, exist_ok=True)
    paths = CsvPaths(
        events=root_path / f"{run_id}_events.csv",
        markets=root_path / f"{run_id}_markets.csv",
        anchors=root_path / f"{run_id}_anchors.csv",
        candles=root_path / f"{run_id}_candles.csv",
    )
    _write_csv(paths.events, EVENT_FIELDS, sorted(rows.events, key=lambda r: r["event_ticker"]))
    _write_csv(paths.markets, MARKET_FIELDS, sorted(rows.markets, key=lambda r: (r["event_ticker"], r["ticker"])))
    _write_csv(paths.anchors, ANCHOR_FIELDS, sorted(rows.anchors, key=lambda r: (r["ticker"], -ANCHOR_DAYS[r["anchor_name"]])))
    _write_csv(paths.candles, CANDLE_FIELDS, sorted(rows.candles, key=lambda r: (r["ticker"], -ANCHOR_DAYS[r["anchor_name"]], int(r["end_period_ts"]))))
    return paths


def _fetch_market_tier(
    client: RawFirstJsonClient,
    *,
    event_ticker: str,
    tier: str,
    cutoff: HistoricalCutoff,
    max_pages: int,
) -> list[tuple[dict[str, Any], str, RawFirstJsonResponse]]:
    if tier not in {"historical", "live"}:
        raise ValueError("tier must be historical or live")
    cursor = ""
    collected: list[tuple[dict[str, Any], str, RawFirstJsonResponse]] = []
    for _ in range(max_pages):
        if tier == "historical":
            path = "/historical/markets"
            params: dict[str, Any] = {"event_ticker": event_ticker, "limit": 1000}
        else:
            path = "/markets"
            params = {"event_ticker": event_ticker, "status": "settled", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        response = client.get_json(path, params=params)
        if tier == "historical":
            markets, cursor = validate_historical_market_list_payload(response.payload)
        else:
            markets, cursor = _validate_live_market_list_payload(response.payload)
        for market in markets:
            if market.get("event_ticker") != event_ticker:
                raise SportsHistoricalCollectionError(
                    f"{tier} market response returned a different event_ticker"
                )
            # Do not reject an off-tier list observation here. The raw response is
            # already archived, and reconciliation below will classify it against
            # the captured cutoff and require canonical-tier evidence before use.
            _parse_utc_timestamp(market.get("settlement_ts"), "market.settlement_ts")
            collected.append((dict(market), tier, response))
        if not cursor:
            return collected
    raise SportsHistoricalCollectionError(
        f"{tier} market pagination for {event_ticker} exceeded max_pages={max_pages}"
    )


def _reconcile_market_tiers(
    client: RawFirstJsonClient,
    *,
    event_ticker: str,
    cutoff: HistoricalCutoff,
    candidates: Sequence[tuple[dict[str, Any], str, RawFirstJsonResponse]],
) -> tuple[
    list[tuple[dict[str, Any], str, RawFirstJsonResponse]],
    int,
    set[str],
    int,
]:
    """Return one canonical-tier record per ticker and measure tier anomalies.

    Kalshi's published partition contract says pre-cutoff settled markets belong
    to the historical tier. If a list endpoint nevertheless returns a market on
    the opposite tier, preserve that observation but never derive from it. Use
    an already-observed canonical-tier copy when available; otherwise fetch the
    canonical single-market endpoint. Conflicting identity/timing evidence fails
    closed.
    """

    by_ticker: dict[str, list[tuple[dict[str, Any], str, RawFirstJsonResponse]]] = {}
    for market, observed_tier, response in candidates:
        ticker = _required_text(market.get("ticker"), "market.ticker")
        by_ticker.setdefault(ticker, []).append((market, observed_tier, response))

    canonical: list[tuple[dict[str, Any], str, RawFirstJsonResponse]] = []
    cross_tier_observation_count = 0
    cross_tier_tickers: set[str] = set()
    recovery_fetch_count = 0

    for ticker, observations in by_ticker.items():
        settlement_values = {
            _parse_utc_timestamp(item[0].get("settlement_ts"), "market.settlement_ts")
            for item in observations
        }
        event_values = {
            _required_text(item[0].get("event_ticker"), "market.event_ticker")
            for item in observations
        }
        if event_values != {event_ticker}:
            raise SportsHistoricalCollectionError(
                f"market {ticker!r} has conflicting event identity across tiers"
            )
        if len(settlement_values) != 1:
            raise SportsHistoricalCollectionError(
                f"market {ticker!r} has conflicting settlement_ts across tiers"
            )

        settlement = next(iter(settlement_values))
        expected_tier = "historical" if settlement < cutoff.market_settled_ts else "live"
        canonical_observations = [
            item for item in observations if item[1] == expected_tier
        ]
        off_tier_observations = [
            item for item in observations if item[1] != expected_tier
        ]
        if off_tier_observations:
            cross_tier_observation_count += len(off_tier_observations)
            cross_tier_tickers.add(ticker)

        if len(canonical_observations) > 1:
            raise SportsHistoricalCollectionError(
                f"market {ticker!r} appeared more than once on canonical {expected_tier} tier"
            )

        if canonical_observations:
            canonical.append(canonical_observations[0])
            continue

        recovery_fetch_count += 1
        if expected_tier == "historical":
            response = client.get_json(f"/historical/markets/{ticker}")
        else:
            response = client.get_json(f"/markets/{ticker}")
        market = _validate_single_market_payload(response.payload, tier=expected_tier)
        if _required_text(market.get("ticker"), "market.ticker") != ticker:
            raise SportsHistoricalCollectionError(
                f"canonical {expected_tier} recovery returned the wrong ticker for {ticker!r}"
            )
        if _required_text(market.get("event_ticker"), "market.event_ticker") != event_ticker:
            raise SportsHistoricalCollectionError(
                f"canonical {expected_tier} recovery returned the wrong event for {ticker!r}"
            )
        recovered_settlement = _parse_utc_timestamp(
            market.get("settlement_ts"), "market.settlement_ts"
        )
        recovered_expected_tier = (
            "historical" if recovered_settlement < cutoff.market_settled_ts else "live"
        )
        if recovered_expected_tier != expected_tier:
            raise SportsHistoricalCollectionError(
                f"canonical recovery for {ticker!r} contradicts captured cutoff routing"
            )
        if recovered_settlement != settlement:
            raise SportsHistoricalCollectionError(
                f"canonical recovery for {ticker!r} changed settlement_ts"
            )
        canonical.append((dict(market), expected_tier, response))

    canonical.sort(key=lambda item: _required_text(item[0].get("ticker"), "market.ticker"))
    return (
        canonical,
        cross_tier_observation_count,
        cross_tier_tickers,
        recovery_fetch_count,
    )


def _validate_single_market_payload(
    payload: Mapping[str, Any],
    *,
    tier: str,
) -> dict[str, Any]:
    market = payload.get("market")
    if not isinstance(market, Mapping):
        raise SportsHistoricalCollectionError(
            f"{tier} single-market response field 'market' must be an object"
        )
    _required_text(market.get("ticker"), "market.ticker")
    _required_text(market.get("event_ticker"), "market.event_ticker")
    _parse_utc_timestamp(market.get("open_time"), "market.open_time")
    _parse_utc_timestamp(market.get("close_time"), "market.close_time")
    _parse_utc_timestamp(market.get("settlement_ts"), "market.settlement_ts")
    return dict(market)


def _fetch_candle_window(
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
        raise ValueError("route_tier must be historical or live")
    return client.get_json(path, params=params)


def _validate_live_market_list_payload(
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    markets = payload.get("markets")
    if not isinstance(markets, list):
        raise SportsHistoricalCollectionError("live markets response field 'markets' must be a list")
    cursor = payload.get("cursor")
    if not isinstance(cursor, str):
        raise SportsHistoricalCollectionError("live markets response field 'cursor' must be a string")
    validated: list[dict[str, Any]] = []
    for index, market in enumerate(markets):
        if not isinstance(market, Mapping):
            raise SportsHistoricalCollectionError(f"live markets item {index} must be an object")
        _required_text(market.get("ticker"), f"markets[{index}].ticker")
        _required_text(market.get("event_ticker"), f"markets[{index}].event_ticker")
        _parse_utc_timestamp(market.get("open_time"), f"markets[{index}].open_time")
        _parse_utc_timestamp(market.get("close_time"), f"markets[{index}].close_time")
        _parse_utc_timestamp(market.get("settlement_ts"), f"markets[{index}].settlement_ts")
        validated.append(dict(market))
    return validated, cursor


def _market_is_baseline_candidate(market: Mapping[str, Any]) -> bool:
    """Apply only outcome-free baseline market filters."""

    return (
        market.get("market_type") == "binary"
        and market.get("status") == "finalized"
        and not _text_or_blank(market.get("mve_collection_ticker"))
    )


def _check_market_ticker_uniqueness(
    markets: Sequence[tuple[Mapping[str, Any], str, RawFirstJsonResponse]],
    already_selected: set[str],
) -> None:
    seen = set(already_selected)
    for market, tier, _response in markets:
        ticker = _required_text(market.get("ticker"), "market.ticker")
        if ticker in seen:
            raise SportsHistoricalCollectionError(
                f"duplicate market ticker {ticker!r} across selected events/tiers"
            )
        seen.add(ticker)


def _lineage(run_id: str, raw: _RawReference, route_tier: str) -> dict[str, str]:
    return {
        "run_id": run_id,
        "raw_source": _required_text(raw.source, "raw.source"),
        "raw_session_id": _required_text(raw.session_id, "raw.session_id"),
        "raw_request_id": _required_text(raw.request_id, "raw.request_id"),
        "route_tier": route_tier,
    }


def _validate_row_shape(
    row: Mapping[str, str],
    expected_fields: Sequence[str],
    run_id: str,
    label: str,
) -> None:
    if tuple(row.keys()) != tuple(expected_fields):
        raise SportsHistoricalCollectionError(
            f"{label} row fields do not match schema: {tuple(row.keys())!r}"
        )
    for field in ("run_id", "raw_source", "raw_session_id", "raw_request_id", "route_tier"):
        if not row.get(field):
            raise SportsHistoricalCollectionError(f"{label} row has blank {field}")
    if row["run_id"] != run_id:
        raise SportsHistoricalCollectionError(f"{label} row run_id mismatch")


def _write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fields))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            handle.flush()
    except (OSError, csv.Error) as exc:
        raise SportsHistoricalCollectionError(f"could not write {path}: {exc}") from exc


def _mapping_or_none(value: Any, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SportsHistoricalCollectionError(f"{field} must be an object or null")
    return value


def _decimal_text(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        raise SportsHistoricalCollectionError("boolean cannot be normalized as decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SportsHistoricalCollectionError(f"invalid decimal value {value!r}") from exc
    if not parsed.is_finite():
        raise SportsHistoricalCollectionError(f"non-finite decimal value {value!r}")
    return format(parsed, "f")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SportsHistoricalCollectionError(f"{field} must be non-empty text")
    return value


def _text_or_blank(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _bool_or_blank(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, bool):
        raise SportsHistoricalCollectionError(f"expected boolean or null, got {value!r}")
    return _bool_text(value)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _parse_utc_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SportsHistoricalCollectionError(f"{field} must be non-empty timestamp text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SportsHistoricalCollectionError(f"{field} is not valid ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise SportsHistoricalCollectionError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc)


def _required_timestamp_text(value: Any, field: str) -> str:
    parsed = _parse_utc_timestamp(value, field)
    assert isinstance(value, str)
    return value
