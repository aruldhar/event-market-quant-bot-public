"""Development-only collection and validation for KXBTC15M live chart data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Callable, Mapping, Protocol, Sequence

from .kxbtc15m_development_economics import (
    HOLDOUT_FIRST_TICKER,
    MAX_DEVELOPMENT_INDEX,
    FrozenMarket,
)


TARGET_RE = re.compile(
    r"target\s*price\s*:\s*\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)

SUMMARY_FIELDS = (
    "run_id",
    "market_index",
    "ticker",
    "event_ticker",
    "market_open_time_utc",
    "market_close_time_utc",
    "target_price",
    "target_source_field",
    "market_raw_source",
    "market_raw_session_id",
    "market_raw_request_id",
    "market_received_at_utc",
    "live_raw_source",
    "live_raw_session_id",
    "live_raw_request_id",
    "live_received_at_utc",
    "live_data_type",
    "is_historical",
    "default_range",
    "range_options",
    "coin",
    "maturity_ts_ms",
    "timeseries_point_count",
    "timeseries_first_ts_ms",
    "timeseries_first_time_utc",
    "timeseries_last_ts_ms",
    "timeseries_last_time_utc",
    "interval_min_ms",
    "interval_max_ms",
    "non_one_second_interval_count",
    "duplicate_timestamp_count",
    "preopen_reference_ts_ms",
    "preopen_reference_time_utc",
    "preopen_reference_value",
    "target_minus_preopen_reference",
    "target_matches_rounded_preopen_reference",
    "final_chart_value",
    "audit_only_expiration_value",
    "audit_only_final_matches_expiration_rounded",
    "candlestick_1m_count",
    "holdout_read",
    "authentication_used",
)

TIMESERIES_FIELDS = (
    "run_id",
    "market_index",
    "ticker",
    "event_ticker",
    "target_price",
    "timestamp_ms",
    "observed_at_utc",
    "value",
    "raw_delta_from_target",
    "seconds_from_market_open",
    "seconds_remaining",
    "within_market_window",
    "live_raw_source",
    "live_raw_session_id",
    "live_raw_request_id",
    "live_received_at_utc",
)


class DevelopmentLiveDataError(RuntimeError):
    """Raised when public live-data evidence violates a frozen invariant."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference
    received_at_utc: str


class RawFirstJsonClient(Protocol):
    def get_json(
        self, path: str, *, params: Mapping[str, Any] | None = None
    ) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class LivePoint:
    timestamp_ms: int
    value: Decimal


@dataclass(frozen=True)
class DevelopmentLiveDataCollection:
    summaries: list[dict[str, str]]
    timeseries: list[dict[str, str]]


def parse_target_price(text: Any) -> Decimal:
    """Extract a displayed target such as ``Target Price: $63,792.88``."""

    match = TARGET_RE.search("" if text is None else str(text))
    if match is None:
        raise DevelopmentLiveDataError(
            f"could not parse target price from yes_sub_title: {text!r}"
        )
    return _decimal(match.group(1).replace(",", ""), "target price")


def collect_development_live_data(
    client: RawFirstJsonClient,
    markets: Sequence[FrozenMarket],
    *,
    run_id: str,
    progress: Callable[[int, int, str], None] | None = None,
    market_sink: Callable[[dict[str, str], list[dict[str, str]]], None]
    | None = None,
    retain_timeseries: bool = True,
) -> DevelopmentLiveDataCollection:
    """Archive and validate one-hour chart histories for frozen development markets."""

    summaries: list[dict[str, str]] = []
    point_rows: list[dict[str, str]] = []
    seen_events: set[str] = set()

    for ordinal, frozen in enumerate(markets, start=1):
        _require_development_market(frozen)
        market_response = client.get_json(f"/markets/{frozen.ticker}")
        market = market_response.payload.get("market")
        if not isinstance(market, Mapping):
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: response missing market object"
            )
        if str(market.get("ticker") or "") != frozen.ticker:
            raise DevelopmentLiveDataError(f"{frozen.ticker}: response ticker mismatch")

        event_ticker = str(market.get("event_ticker") or "").strip()
        if not event_ticker.startswith("KXBTC15M-"):
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: invalid event_ticker {event_ticker!r}"
            )
        if event_ticker in seen_events:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: duplicate event_ticker {event_ticker}"
            )
        seen_events.add(event_ticker)

        open_dt = _parse_utc(market.get("open_time"), "open_time", frozen.ticker)
        close_dt = _parse_utc(market.get("close_time"), "close_time", frozen.ticker)
        if close_dt <= open_dt:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: close_time is not after open_time"
            )
        open_ms = _datetime_to_ms(open_dt)
        close_ms = _datetime_to_ms(close_dt)
        target = parse_target_price(market.get("yes_sub_title"))

        live_response = client.get_json(
            f"/live_data/events/{event_ticker}", params={"range": "1h"}
        )
        live_data = live_response.payload.get("live_data")
        if not isinstance(live_data, Mapping):
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: response missing live_data object"
            )
        if str(live_data.get("type") or "").lower() != "crypto":
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: live_data type is not crypto"
            )
        if live_data.get("is_historical") is not True:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: expected historical live_data"
            )
        details = live_data.get("details")
        if not isinstance(details, Mapping):
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: live_data missing details object"
            )
        if str(details.get("coin") or "").upper() != "BTC":
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: live_data coin is not BTC"
            )
        if str(details.get("event_ticker") or "") != event_ticker:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: live_data event_ticker mismatch"
            )

        maturity_ms = _integer(details.get("maturity_ts_ms"), "maturity_ts_ms")
        if maturity_ms != close_ms:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: maturity_ts_ms does not equal market close_time"
            )
        points = _parse_timeseries(details.get("timeseries"), frozen.ticker)
        intervals = [
            right.timestamp_ms - left.timestamp_ms
            for left, right in zip(points, points[1:])
        ]
        duplicate_count = sum(interval == 0 for interval in intervals)
        bad_interval_count = sum(interval != 1000 for interval in intervals)
        if duplicate_count or bad_interval_count:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: timeseries is not a contiguous one-second grid; "
                f"duplicates={duplicate_count}, non_1s_intervals={bad_interval_count}"
            )
        if points[-1].timestamp_ms != maturity_ms:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: final timeseries point does not equal maturity"
            )
        if points[0].timestamp_ms > open_ms - 1000:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: timeseries does not include a pre-open reference"
            )

        preopen = max(
            (point for point in points if point.timestamp_ms < open_ms),
            key=lambda point: point.timestamp_ms,
        )
        if preopen.timestamp_ms != open_ms - 1000:
            raise DevelopmentLiveDataError(
                f"{frozen.ticker}: last pre-open point is not one second before open"
            )
        target_difference = target - preopen.value
        target_matches = target == _cents(preopen.value)
        expiration = _optional_decimal(market.get("expiration_value"))
        final_matches_expiration = (
            expiration is not None and _cents(points[-1].value) == _cents(expiration)
        )

        market_raw = market_response.raw_record
        live_raw = live_response.raw_record
        range_options = live_data.get("range_options")
        range_text = "|".join(str(value) for value in range_options) if isinstance(range_options, list) else ""
        candlesticks = details.get("candlesticks")
        one_minute = candlesticks.get("1M") if isinstance(candlesticks, Mapping) else None

        summaries.append(
            {
                "run_id": run_id,
                "market_index": str(frozen.market_index),
                "ticker": frozen.ticker,
                "event_ticker": event_ticker,
                "market_open_time_utc": _format_utc(open_dt),
                "market_close_time_utc": _format_utc(close_dt),
                "target_price": _number(target),
                "target_source_field": "yes_sub_title",
                "market_raw_source": market_raw.source,
                "market_raw_session_id": market_raw.session_id,
                "market_raw_request_id": market_raw.request_id,
                "market_received_at_utc": market_response.received_at_utc,
                "live_raw_source": live_raw.source,
                "live_raw_session_id": live_raw.session_id,
                "live_raw_request_id": live_raw.request_id,
                "live_received_at_utc": live_response.received_at_utc,
                "live_data_type": str(live_data.get("type") or ""),
                "is_historical": "1",
                "default_range": str(live_data.get("default_range") or ""),
                "range_options": range_text,
                "coin": str(details.get("coin") or ""),
                "maturity_ts_ms": str(maturity_ms),
                "timeseries_point_count": str(len(points)),
                "timeseries_first_ts_ms": str(points[0].timestamp_ms),
                "timeseries_first_time_utc": _ms_to_utc(points[0].timestamp_ms),
                "timeseries_last_ts_ms": str(points[-1].timestamp_ms),
                "timeseries_last_time_utc": _ms_to_utc(points[-1].timestamp_ms),
                "interval_min_ms": str(min(intervals) if intervals else ""),
                "interval_max_ms": str(max(intervals) if intervals else ""),
                "non_one_second_interval_count": str(bad_interval_count),
                "duplicate_timestamp_count": str(duplicate_count),
                "preopen_reference_ts_ms": str(preopen.timestamp_ms),
                "preopen_reference_time_utc": _ms_to_utc(preopen.timestamp_ms),
                "preopen_reference_value": _number(preopen.value),
                "target_minus_preopen_reference": _number(target_difference),
                "target_matches_rounded_preopen_reference": "1" if target_matches else "0",
                "final_chart_value": _number(points[-1].value),
                "audit_only_expiration_value": "" if expiration is None else _number(expiration),
                "audit_only_final_matches_expiration_rounded": "1" if final_matches_expiration else "0",
                "candlestick_1m_count": str(len(one_minute) if isinstance(one_minute, list) else 0),
                "holdout_read": "0",
                "authentication_used": "0",
            }
        )

        market_point_rows: list[dict[str, str]] = []
        for point in points:
            seconds_from_open = Decimal(point.timestamp_ms - open_ms) / Decimal(1000)
            seconds_remaining = Decimal(close_ms - point.timestamp_ms) / Decimal(1000)
            market_point_rows.append(
                {
                    "run_id": run_id,
                    "market_index": str(frozen.market_index),
                    "ticker": frozen.ticker,
                    "event_ticker": event_ticker,
                    "target_price": _number(target),
                    "timestamp_ms": str(point.timestamp_ms),
                    "observed_at_utc": _ms_to_utc(point.timestamp_ms),
                    "value": _number(point.value),
                    "raw_delta_from_target": _number(point.value - target),
                    "seconds_from_market_open": _number(seconds_from_open),
                    "seconds_remaining": _number(seconds_remaining),
                    "within_market_window": "1" if open_ms <= point.timestamp_ms <= close_ms else "0",
                    "live_raw_source": live_raw.source,
                    "live_raw_session_id": live_raw.session_id,
                    "live_raw_request_id": live_raw.request_id,
                    "live_received_at_utc": live_response.received_at_utc,
                }
            )
        if market_sink is not None:
            market_sink(summaries[-1], market_point_rows)
        if retain_timeseries:
            point_rows.extend(market_point_rows)
        if progress is not None:
            progress(ordinal, len(markets), frozen.ticker)

    return DevelopmentLiveDataCollection(summaries=summaries, timeseries=point_rows)


def _parse_timeseries(value: Any, ticker: str) -> tuple[LivePoint, ...]:
    if not isinstance(value, list) or len(value) < 2:
        raise DevelopmentLiveDataError(
            f"{ticker}: timeseries must contain at least two observations"
        )
    points: list[LivePoint] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise DevelopmentLiveDataError(
                f"{ticker}: timeseries item {index} is not an object"
            )
        timestamp = _integer(item.get("t"), f"timeseries[{index}].t")
        observed = _decimal(item.get("v"), f"timeseries[{index}].v")
        points.append(LivePoint(timestamp_ms=timestamp, value=observed))
    if any(right.timestamp_ms <= left.timestamp_ms for left, right in zip(points, points[1:])):
        raise DevelopmentLiveDataError(
            f"{ticker}: timeseries timestamps are not strictly increasing"
        )
    return tuple(points)


def _require_development_market(frozen: FrozenMarket) -> None:
    if (
        frozen.market_index > MAX_DEVELOPMENT_INDEX
        or frozen.market_index < 1
        or frozen.ticker >= HOLDOUT_FIRST_TICKER
    ):
        raise DevelopmentLiveDataError(
            f"refusing non-development market request: {frozen.ticker}"
        )


def _parse_utc(value: Any, field: str, ticker: str) -> datetime:
    text = "" if value is None else str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DevelopmentLiveDataError(
            f"{ticker}: invalid {field} timestamp {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise DevelopmentLiveDataError(f"{ticker}: {field} is timezone-naive")
    return parsed.astimezone(timezone.utc)


def _datetime_to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _integer(value: Any, label: str) -> int:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DevelopmentLiveDataError(f"invalid {label}: {value!r}") from exc
    if not decimal.is_finite() or decimal != decimal.to_integral_value():
        raise DevelopmentLiveDataError(f"invalid integral {label}: {value!r}")
    return int(decimal)


def _decimal(value: Any, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DevelopmentLiveDataError(f"invalid {label}: {value!r}") from exc
    if not parsed.is_finite():
        raise DevelopmentLiveDataError(f"non-finite {label}: {value!r}")
    return parsed


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return _decimal(value, "expiration_value")


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _number(value: Decimal) -> str:
    return format(value, "f")


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ms_to_utc(value: int) -> str:
    return _format_utc(datetime.fromtimestamp(value / 1000, tz=timezone.utc))
