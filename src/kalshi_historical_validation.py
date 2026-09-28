"""Read-only validation helpers for Kalshi historical-data routing.

Checkpoint 08 uses these helpers only to validate public endpoint behavior and
raw lineage before any Sports historical dataset collector is accepted.

The module deliberately does not inspect or score final YES/NO outcomes. Raw
responses may contain terminal result fields because Kalshi historical market
objects contain them, but the validation logic never uses those fields.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


VALIDATION_SCHEMA = "kalshi_historical_endpoint_validation.v1"

VALIDATION_REPORT_FIELDS = [
    "schema_version",
    "probe_name",
    "route_tier",
    "method",
    "path",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "request_started_at_utc",
    "received_at_utc",
    "ticker",
    "event_ticker",
    "series_ticker",
    "item_count",
    "validation_state",
    "details_json",
]


class HistoricalEndpointValidationError(RuntimeError):
    """Raised when historical endpoint evidence is malformed or inconsistent."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference
    request_started_at_utc: str
    request_started_monotonic_ns: int
    received_at_utc: str
    received_monotonic_ns: int


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
class HistoricalSportsCandidate:
    ticker: str
    event_ticker: str
    series_ticker: str
    open_time: datetime
    close_time: datetime
    settlement_ts: datetime
    market_response: RawFirstJsonResponse
    event_response: RawFirstJsonResponse
    discovery_response: RawFirstJsonResponse


@dataclass(frozen=True)
class LiveSportsCandidate:
    ticker: str
    event_ticker: str
    series_ticker: str
    open_time: datetime | None
    close_time: datetime
    volume_24h: Decimal
    event_response: RawFirstJsonResponse


@dataclass(frozen=True)
class CandlestickSummary:
    candle_count: int
    quote_pair_close_count: int
    missing_bid_close_count: int
    missing_ask_close_count: int
    crossed_close_count: int
    first_end_period_ts: int | None
    last_end_period_ts: int | None
    end_period_order: str
    duplicate_end_period_count: int
    observed_candle_fields: tuple[str, ...]
    observed_bid_fields: tuple[str, ...]
    observed_ask_fields: tuple[str, ...]
    observed_price_fields: tuple[str, ...]


@dataclass(frozen=True)
class TradeSummary:
    trade_count: int
    first_created_time: datetime | None
    last_created_time: datetime | None
    created_time_order: str
    duplicate_created_time_count: int
    observed_trade_fields: tuple[str, ...]


def validate_cutoff_payload(payload: Mapping[str, Any]) -> HistoricalCutoff:
    """Validate the routing cutoffs documented by Kalshi.

    The market cutoff determines market/candlestick routing. The trade cutoff
    determines trade routing. Other cutoff fields are preserved when present
    but are not used by this Checkpoint-08 probe.
    """

    return HistoricalCutoff(
        market_settled_ts=_parse_utc_timestamp(
            payload.get("market_settled_ts"), "market_settled_ts"
        ),
        trades_created_ts=_parse_utc_timestamp(
            payload.get("trades_created_ts"), "trades_created_ts"
        ),
        orders_updated_ts=_parse_utc_timestamp(
            payload.get("orders_updated_ts"), "orders_updated_ts"
        ),
        market_positions_last_updated_ts=_optional_utc_timestamp(
            payload.get("market_positions_last_updated_ts"),
            "market_positions_last_updated_ts",
        ),
    )


def validate_historical_market_list_payload(
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    markets = payload.get("markets")
    if not isinstance(markets, list):
        raise HistoricalEndpointValidationError(
            "historical markets response field 'markets' must be a list"
        )
    cursor = payload.get("cursor")
    if not isinstance(cursor, str):
        raise HistoricalEndpointValidationError(
            "historical markets response field 'cursor' must be a string"
        )
    validated: list[dict[str, Any]] = []
    for index, market in enumerate(markets):
        if not isinstance(market, dict):
            raise HistoricalEndpointValidationError(
                f"historical markets item {index} must be an object"
            )
        _required_text(market.get("ticker"), f"markets[{index}].ticker")
        _required_text(
            market.get("event_ticker"), f"markets[{index}].event_ticker"
        )
        _parse_utc_timestamp(
            market.get("settlement_ts"), f"markets[{index}].settlement_ts"
        )
        _parse_utc_timestamp(market.get("open_time"), f"markets[{index}].open_time")
        _parse_utc_timestamp(
            market.get("close_time"), f"markets[{index}].close_time"
        )
        validated.append(market)
    return validated, cursor


def validate_historical_market_payload(
    payload: Mapping[str, Any],
    *,
    expected_ticker: str,
    market_cutoff: datetime,
) -> dict[str, Any]:
    market = payload.get("market")
    if not isinstance(market, dict):
        raise HistoricalEndpointValidationError(
            "historical single-market response field 'market' must be an object"
        )
    ticker = _required_text(market.get("ticker"), "market.ticker")
    if ticker != expected_ticker:
        raise HistoricalEndpointValidationError(
            f"historical market ticker mismatch: expected {expected_ticker!r}, got {ticker!r}"
        )
    _required_text(market.get("event_ticker"), "market.event_ticker")
    settlement = _parse_utc_timestamp(market.get("settlement_ts"), "market.settlement_ts")
    if settlement >= market_cutoff:
        raise HistoricalEndpointValidationError(
            "selected historical market does not settle before captured market cutoff"
        )
    _parse_utc_timestamp(market.get("open_time"), "market.open_time")
    _parse_utc_timestamp(market.get("close_time"), "market.close_time")
    return market


def validate_event_payload(
    payload: Mapping[str, Any],
    *,
    expected_event_ticker: str,
) -> dict[str, Any]:
    event = payload.get("event")
    if not isinstance(event, dict):
        raise HistoricalEndpointValidationError(
            "event response field 'event' must be an object"
        )
    event_ticker = _required_text(event.get("event_ticker"), "event.event_ticker")
    if event_ticker != expected_event_ticker:
        raise HistoricalEndpointValidationError(
            f"event ticker mismatch: expected {expected_event_ticker!r}, got {event_ticker!r}"
        )
    _required_text(event.get("series_ticker"), "event.series_ticker")
    _required_text(event.get("category"), "event.category")
    return event


def validate_events_payload(
    payload: Mapping[str, Any],
    *,
    require_identity_fields: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    events = payload.get("events")
    if not isinstance(events, list):
        raise HistoricalEndpointValidationError(
            "events response field 'events' must be a list"
        )
    cursor = payload.get("cursor")
    if not isinstance(cursor, str):
        raise HistoricalEndpointValidationError(
            "events response field 'cursor' must be a string"
        )
    validated: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise HistoricalEndpointValidationError(
                f"events item {index} must be an object"
            )
        if require_identity_fields:
            _required_text(event.get("event_ticker"), f"events[{index}].event_ticker")
            _required_text(event.get("series_ticker"), f"events[{index}].series_ticker")
            _required_text(event.get("category"), f"events[{index}].category")
        validated.append(event)
    return validated, cursor


def find_historical_sports_candidate(
    client: RawFirstJsonClient,
    *,
    cutoff: HistoricalCutoff,
    max_market_pages: int = 3,
    max_event_lookups: int = 40,
) -> HistoricalSportsCandidate:
    """Find one historical Sports market without inspecting its final outcome.

    Historical markets do not themselves provide the category/series metadata
    needed for the Sports research class, so event metadata is fetched from the
    still-live event endpoint. Every request travels through the caller's
    raw-first client before any selection logic runs.
    """

    if max_market_pages <= 0:
        raise ValueError("max_market_pages must be positive")
    if max_event_lookups <= 0:
        raise ValueError("max_event_lookups must be positive")

    cursor = ""
    event_lookups = 0
    seen_events: set[str] = set()

    for _page_index in range(max_market_pages):
        params: dict[str, Any] = {"limit": 100, "mve_filter": "exclude"}
        if cursor:
            params["cursor"] = cursor
        discovery_response = client.get_json("/historical/markets", params=params)
        markets, cursor = validate_historical_market_list_payload(
            discovery_response.payload
        )
        for market in markets:
            settlement_ts = _parse_utc_timestamp(
                market.get("settlement_ts"), "market.settlement_ts"
            )
            if settlement_ts >= cutoff.market_settled_ts:
                raise HistoricalEndpointValidationError(
                    "historical /markets returned a market at or after the captured market cutoff"
                )

            event_ticker = _required_text(
                market.get("event_ticker"), "market.event_ticker"
            )
            if event_ticker in seen_events:
                continue
            seen_events.add(event_ticker)
            if event_lookups >= max_event_lookups:
                raise HistoricalEndpointValidationError(
                    "historical Sports discovery reached max_event_lookups before finding a Sports event"
                )
            event_lookups += 1

            event_response = client.get_json(f"/events/{event_ticker}")
            event = validate_event_payload(
                event_response.payload,
                expected_event_ticker=event_ticker,
            )
            if event.get("category") != "Sports":
                continue

            ticker = _required_text(market.get("ticker"), "market.ticker")
            market_response = client.get_json(f"/historical/markets/{ticker}")
            single_market = validate_historical_market_payload(
                market_response.payload,
                expected_ticker=ticker,
                market_cutoff=cutoff.market_settled_ts,
            )
            if single_market.get("event_ticker") != event_ticker:
                raise HistoricalEndpointValidationError(
                    "historical market/event linkage changed between list and single-market responses"
                )

            return HistoricalSportsCandidate(
                ticker=ticker,
                event_ticker=event_ticker,
                series_ticker=_required_text(
                    event.get("series_ticker"), "event.series_ticker"
                ),
                open_time=_parse_utc_timestamp(
                    single_market.get("open_time"), "market.open_time"
                ),
                close_time=_parse_utc_timestamp(
                    single_market.get("close_time"), "market.close_time"
                ),
                settlement_ts=_parse_utc_timestamp(
                    single_market.get("settlement_ts"), "market.settlement_ts"
                ),
                market_response=market_response,
                event_response=event_response,
                discovery_response=discovery_response,
            )
        if not cursor:
            break

    raise HistoricalEndpointValidationError(
        "no historical Sports market was found inside the bounded validation search"
    )


def find_live_sports_candidate(
    client: RawFirstJsonClient,
    *,
    now_utc: datetime,
    max_event_pages: int = 3,
) -> LiveSportsCandidate:
    """Find one currently live Sports market for live-candlestick validation."""

    now_utc = _ensure_utc(now_utc, "now_utc")
    if max_event_pages <= 0:
        raise ValueError("max_event_pages must be positive")

    cursor = ""
    best: tuple[Decimal, datetime, str, LiveSportsCandidate] | None = None
    for _page_index in range(max_event_pages):
        params: dict[str, Any] = {
            "status": "open",
            "with_nested_markets": "true",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor
        response = client.get_json("/events", params=params)
        events, cursor = validate_events_payload(response.payload)
        for event in events:
            if event.get("category") != "Sports":
                continue
            event_ticker = _required_text(
                event.get("event_ticker"), "event.event_ticker"
            )
            series_ticker = _required_text(
                event.get("series_ticker"), "event.series_ticker"
            )
            markets = event.get("markets")
            if not isinstance(markets, list):
                raise HistoricalEndpointValidationError(
                    f"open Sports event {event_ticker} did not include nested markets"
                )
            for index, market in enumerate(markets):
                if not isinstance(market, dict):
                    raise HistoricalEndpointValidationError(
                        f"event.markets[{index}] must be an object"
                    )
                if market.get("status") != "active":
                    continue
                ticker = _required_text(
                    market.get("ticker"), f"event.markets[{index}].ticker"
                )
                close_time = _parse_utc_timestamp(
                    market.get("close_time"), f"event.markets[{index}].close_time"
                )
                open_time = _optional_utc_timestamp(
                    market.get("open_time"), f"event.markets[{index}].open_time"
                )
                volume = _decimal_or_none(market.get("volume_24h_fp"))
                if (
                    close_time <= now_utc
                    or (open_time is not None and open_time > now_utc)
                    or volume is None
                    or volume <= 0
                ):
                    continue
                candidate = LiveSportsCandidate(
                    ticker=ticker,
                    event_ticker=event_ticker,
                    series_ticker=series_ticker,
                    open_time=open_time,
                    close_time=close_time,
                    volume_24h=volume,
                    event_response=response,
                )
                ranking = (volume, close_time, ticker, candidate)
                if best is None or ranking[:3] > best[:3]:
                    best = ranking
        if not cursor:
            break

    if best is not None:
        return best[3]
    raise HistoricalEndpointValidationError(
        "no currently open Sports market with positive 24h volume was found "
        "inside the bounded validation search"
    )


def validate_candlestick_payload(
    payload: Mapping[str, Any],
    *,
    expected_ticker: str,
    tier: str,
) -> CandlestickSummary:
    """Validate documented historical/live candlestick container behavior.

    Historical and live endpoints currently document different field-name
    families. This validator intentionally keeps them separate instead of
    silently normalizing one into the other.
    """

    if tier not in {"historical", "live"}:
        raise ValueError("tier must be 'historical' or 'live'")
    ticker = _required_text(payload.get("ticker"), "candlesticks.ticker")
    if ticker != expected_ticker:
        raise HistoricalEndpointValidationError(
            f"candlestick ticker mismatch: expected {expected_ticker!r}, got {ticker!r}"
        )
    candles = payload.get("candlesticks")
    if not isinstance(candles, list):
        raise HistoricalEndpointValidationError(
            "candlesticks response field 'candlesticks' must be a list"
        )

    close_key = "close" if tier == "historical" else "close_dollars"
    ends: list[int] = []
    quote_pairs = 0
    missing_bid = 0
    missing_ask = 0
    crossed = 0
    candle_fields: set[str] = set()
    bid_fields: set[str] = set()
    ask_fields: set[str] = set()
    price_fields: set[str] = set()

    for index, candle in enumerate(candles):
        if not isinstance(candle, dict):
            raise HistoricalEndpointValidationError(
                f"candlesticks[{index}] must be an object"
            )
        candle_fields.update(str(key) for key in candle)
        end_period_ts = candle.get("end_period_ts")
        if not isinstance(end_period_ts, int) or isinstance(end_period_ts, bool):
            raise HistoricalEndpointValidationError(
                f"candlesticks[{index}].end_period_ts must be an integer"
            )
        ends.append(end_period_ts)

        bid = _mapping_or_none(candle.get("yes_bid"), f"candlesticks[{index}].yes_bid")
        ask = _mapping_or_none(candle.get("yes_ask"), f"candlesticks[{index}].yes_ask")
        price = _mapping_or_none(candle.get("price"), f"candlesticks[{index}].price")
        if bid is not None:
            bid_fields.update(str(key) for key in bid)
        if ask is not None:
            ask_fields.update(str(key) for key in ask)
        if price is not None:
            price_fields.update(str(key) for key in price)

        bid_close = _decimal_or_none(None if bid is None else bid.get(close_key))
        ask_close = _decimal_or_none(None if ask is None else ask.get(close_key))
        if bid_close is None:
            missing_bid += 1
        if ask_close is None:
            missing_ask += 1
        if bid_close is not None and ask_close is not None:
            quote_pairs += 1
            if bid_close > ask_close:
                crossed += 1

    end_period_order, duplicate_end_period_count = _sequence_order(ends)
    return CandlestickSummary(
        candle_count=len(candles),
        quote_pair_close_count=quote_pairs,
        missing_bid_close_count=missing_bid,
        missing_ask_close_count=missing_ask,
        crossed_close_count=crossed,
        first_end_period_ts=ends[0] if ends else None,
        last_end_period_ts=ends[-1] if ends else None,
        end_period_order=end_period_order,
        duplicate_end_period_count=duplicate_end_period_count,
        observed_candle_fields=tuple(sorted(candle_fields)),
        observed_bid_fields=tuple(sorted(bid_fields)),
        observed_ask_fields=tuple(sorted(ask_fields)),
        observed_price_fields=tuple(sorted(price_fields)),
    )


def validate_trades_payload(
    payload: Mapping[str, Any],
    *,
    expected_ticker: str,
) -> TradeSummary:
    trades = payload.get("trades")
    if not isinstance(trades, list):
        raise HistoricalEndpointValidationError(
            "historical trades response field 'trades' must be a list"
        )
    cursor = payload.get("cursor")
    if not isinstance(cursor, str):
        raise HistoricalEndpointValidationError(
            "historical trades response field 'cursor' must be a string"
        )

    times: list[datetime] = []
    fields: set[str] = set()
    for index, trade in enumerate(trades):
        if not isinstance(trade, dict):
            raise HistoricalEndpointValidationError(
                f"trades[{index}] must be an object"
            )
        fields.update(str(key) for key in trade)
        ticker = _required_text(trade.get("ticker"), f"trades[{index}].ticker")
        if ticker != expected_ticker:
            raise HistoricalEndpointValidationError(
                f"trades[{index}] ticker mismatch: expected {expected_ticker!r}, got {ticker!r}"
            )
        _required_text(trade.get("trade_id"), f"trades[{index}].trade_id")
        times.append(
            _parse_utc_timestamp(trade.get("created_time"), f"trades[{index}].created_time")
        )
        _decimal_or_none(trade.get("count_fp"), required_if_present=True)
        _decimal_or_none(trade.get("yes_price_dollars"), required_if_present=True)
        _decimal_or_none(trade.get("no_price_dollars"), required_if_present=True)

    created_time_order, duplicate_created_time_count = _sequence_order(times)
    return TradeSummary(
        trade_count=len(trades),
        first_created_time=times[0] if times else None,
        last_created_time=times[-1] if times else None,
        created_time_order=created_time_order,
        duplicate_created_time_count=duplicate_created_time_count,
        observed_trade_fields=tuple(sorted(fields)),
    )


def historical_probe_window(candidate: HistoricalSportsCandidate) -> tuple[int, int]:
    """Return a bounded 6-hour schema-probe window ending at market close."""

    end = int(candidate.close_time.timestamp())
    six_hours_before = end - 6 * 60 * 60
    start = max(int(candidate.open_time.timestamp()), six_hours_before)
    if start >= end:
        raise HistoricalEndpointValidationError(
            "historical candidate has no positive pre-close candlestick probe window"
        )
    return start, end


def live_probe_window(
    candidate: LiveSportsCandidate,
    *,
    now_utc: datetime,
) -> tuple[int, int]:
    now_utc = _ensure_utc(now_utc, "now_utc")
    end_dt = min(now_utc, candidate.close_time)
    start_dt = end_dt.replace(microsecond=0)
    # Use a 24-hour schema-validation window so the positive volume_24h
    # selection criterion and the candle probe cover the same activity horizon.
    # This is not a staleness threshold and does not alter experiment anchors.
    start_epoch = int(start_dt.timestamp()) - 24 * 60 * 60
    if candidate.open_time is not None:
        start_epoch = max(start_epoch, int(candidate.open_time.timestamp()))
    end_epoch = int(end_dt.timestamp())
    if start_epoch >= end_epoch:
        # Some just-opened markets may not have a full day of history. A one-minute
        # positive window is enough for an endpoint schema probe.
        start_epoch = max(0, end_epoch - 60)
    return start_epoch, end_epoch


def make_report_row(
    *,
    probe_name: str,
    route_tier: str,
    method: str,
    path: str,
    response: RawFirstJsonResponse,
    ticker: str = "",
    event_ticker: str = "",
    series_ticker: str = "",
    item_count: int | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    raw = response.raw_record
    return {
        "schema_version": VALIDATION_SCHEMA,
        "probe_name": probe_name,
        "route_tier": route_tier,
        "method": method,
        "path": path,
        "raw_source": raw.source,
        "raw_session_id": raw.session_id,
        "raw_request_id": raw.request_id,
        "request_started_at_utc": response.request_started_at_utc,
        "received_at_utc": response.received_at_utc,
        "ticker": ticker,
        "event_ticker": event_ticker,
        "series_ticker": series_ticker,
        "item_count": "" if item_count is None else str(item_count),
        "validation_state": "validated",
        "details_json": json.dumps(
            dict(details or {}), sort_keys=True, separators=(",", ":")
        ),
    }


def write_validation_report(
    path: str | Path,
    rows: Sequence[Mapping[str, str]],
) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=VALIDATION_REPORT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in VALIDATION_REPORT_FIELDS})
        handle.flush()


def validate_report_lineage_against_raw(
    rows: Sequence[Mapping[str, str]],
    raw_paths: Sequence[str | Path],
) -> dict[str, int]:
    """Reconcile each accepted report row to one exact persisted raw exchange."""

    raw_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    raw_record_count = 0
    raw_error_count = 0
    for raw_path in raw_paths:
        path = Path(raw_path)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise HistoricalEndpointValidationError(
                f"could not read raw archive {path}: {exc}"
            ) from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HistoricalEndpointValidationError(
                    f"raw archive {path}:{line_number} is not valid JSON: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise HistoricalEndpointValidationError(
                    f"raw archive {path}:{line_number} is not an object"
                )
            raw_record_count += 1
            source = _required_text(record.get("source"), "raw.source")
            session_id = _required_text(record.get("session_id"), "raw.session_id")
            request = record.get("request")
            if not isinstance(request, dict):
                raise HistoricalEndpointValidationError("raw.request must be an object")
            request_id = _required_text(request.get("request_id"), "raw.request.request_id")
            key = (source, session_id, request_id)
            if key in raw_by_key:
                raise HistoricalEndpointValidationError(
                    f"duplicate raw request identity {key!r}"
                )
            _parse_utc_timestamp(request.get("started_at_utc"), "raw.request.started_at_utc")
            timing = record.get("timing")
            if not isinstance(timing, dict):
                raise HistoricalEndpointValidationError("raw.timing must be an object")
            _parse_utc_timestamp(timing.get("received_at_utc"), "raw.timing.received_at_utc")
            elapsed = timing.get("elapsed_monotonic_ns")
            if not isinstance(elapsed, int) or isinstance(elapsed, bool) or elapsed < 0:
                raise HistoricalEndpointValidationError(
                    "raw.timing.elapsed_monotonic_ns must be a nonnegative integer"
                )
            if record.get("error") is not None:
                raw_error_count += 1
            raw_by_key[key] = record

    referenced: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows):
        key = (
            _required_text(row.get("raw_source"), f"report[{index}].raw_source"),
            _required_text(
                row.get("raw_session_id"), f"report[{index}].raw_session_id"
            ),
            _required_text(
                row.get("raw_request_id"), f"report[{index}].raw_request_id"
            ),
        )
        if key in referenced:
            raise HistoricalEndpointValidationError(
                f"multiple accepted report rows reference the same raw exchange {key!r}"
            )
        referenced.add(key)
        raw = raw_by_key.get(key)
        if raw is None:
            raise HistoricalEndpointValidationError(
                f"report row {index} references unknown raw exchange {key!r}"
            )
        request = raw["request"]
        if request.get("method") != row.get("method"):
            raise HistoricalEndpointValidationError(
                f"report row {index} method does not match raw request"
            )
        if request.get("path") != row.get("path"):
            raise HistoricalEndpointValidationError(
                f"report row {index} path does not match raw request"
            )
        if raw.get("error") is not None:
            raise HistoricalEndpointValidationError(
                f"accepted report row {index} points to a raw record with an error"
            )
        response = raw.get("response")
        if not isinstance(response, dict) or response.get("status_code") != 200:
            raise HistoricalEndpointValidationError(
                f"accepted report row {index} does not point to an HTTP 200 response"
            )
        if request.get("started_at_utc") != row.get("request_started_at_utc"):
            raise HistoricalEndpointValidationError(
                f"report row {index} request UTC does not match raw record"
            )
        timing = raw["timing"]
        if timing.get("received_at_utc") != row.get("received_at_utc"):
            raise HistoricalEndpointValidationError(
                f"report row {index} receive UTC does not match raw record"
            )

    return {
        "raw_record_count": raw_record_count,
        "raw_error_count": raw_error_count,
        "accepted_report_row_count": len(rows),
        "accepted_unique_raw_reference_count": len(referenced),
    }


def _sequence_order(values: Sequence[Any]) -> tuple[str, int]:
    if len(values) < 2:
        return ("single_or_empty", 0)
    duplicate_count = len(values) - len(set(values))
    ascending = all(later >= earlier for earlier, later in zip(values, values[1:]))
    descending = all(later <= earlier for earlier, later in zip(values, values[1:]))
    if ascending and descending:
        order = "constant"
    elif ascending:
        order = "ascending"
    elif descending:
        order = "descending"
    else:
        order = "mixed"
    return order, duplicate_count


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalEndpointValidationError(f"{field} must be a non-empty string")
    return value


def _parse_utc_timestamp(value: Any, field: str) -> datetime:
    text = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalEndpointValidationError(
            f"{field} must be a valid ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise HistoricalEndpointValidationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _optional_utc_timestamp(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    return _parse_utc_timestamp(value, field)


def _ensure_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _mapping_or_none(value: Any, field: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HistoricalEndpointValidationError(f"{field} must be an object or null")
    return value


def _decimal_or_none(
    value: Any,
    *,
    required_if_present: bool = False,
) -> Decimal | None:
    if value is None or value == "":
        return None
    if not isinstance(value, (str, int, float, Decimal)) or isinstance(value, bool):
        if required_if_present:
            raise HistoricalEndpointValidationError(
                f"expected decimal-like value, got {type(value).__name__}"
            )
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HistoricalEndpointValidationError(
            f"invalid decimal-like value {value!r}"
        ) from exc
