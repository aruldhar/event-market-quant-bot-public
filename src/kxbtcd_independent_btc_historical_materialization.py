"""Checkpoint-19D-A outcome-blind independent-BTC historical materialization audit.

This module is deterministic and side-effect free. It defines the exact audit
contract used to test whether Coinbase/Kraken history can reconstruct simple
BTC state at the already outcome-blind Checkpoint-19C KXBTCD snapshot times.

It does not fetch outcomes, define Candidate E, select quality thresholds, fit a
model, score a model, or authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence

from src.kxbtcd_successor_research_protocol import (
    FROZEN_PROTOCOL_FINGERPRINT,
    validate_protocol,
)


class KxbtcdHistoricalMaterializationError(ValueError):
    """Raised when frozen Checkpoint-19D-A invariants are violated."""


AUDIT_SCHEMA_VERSION = "kxbtcd_independent_btc_historical_materialization_audit.v1"
ROW_SCHEMA_VERSION = "kxbtcd_independent_btc_historical_materialization_row.v1"
EXCLUSION_SCHEMA_VERSION = "kxbtcd_independent_btc_historical_materialization_exclusion.v1"
CHECKPOINT_ID = "19D-A"

PARENT_19C_AUDIT_DESIGN_FINGERPRINT = (
    "4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d"
)
PARENT_19C_RUN_ID = (
    "collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250"
)
EXPECTED_PARENT_SNAPSHOT_COUNT = 288
PARENT_19C_COINBASE_SOURCE_ID = "coinbase.exchange.public_rest.product_book.btc_usd.provisional_19c"
PARENT_19C_KRAKEN_SOURCE_ID = "kraken.spot.public_rest.pretrade.btc_usd.provisional_19c"

COINBASE_SOURCE_ID = "coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1"
COINBASE_BASE_URL = "https://api.exchange.coinbase.com"
COINBASE_CANDLES_PATH = "/products/BTC-USD/candles"
COINBASE_PRODUCT_ID = "BTC-USD"
COINBASE_GRANULARITY_SECONDS = 60
COINBASE_MAX_CANDLES_PER_REQUEST = 300

KRAKEN_SOURCE_ID = "kraken.spot.public_rest.posttrade.btc_usd.v1"
KRAKEN_BASE_URL = "https://api.kraken.com"
KRAKEN_POSTTRADE_PATH = "/0/public/PostTrade"
KRAKEN_SYMBOL = "BTC/USD"
KRAKEN_PAGE_COUNT = 1000
KRAKEN_MAX_PAGES_PER_MINUTE = 100

TARGET_LOOKBACK_SECONDS = 300

FORBIDDEN_KEYS = frozenset(
    {
        "result",
        "outcome",
        "label",
        "y",
        "resolved_yes",
        "settled_yes",
        "settlement_value",
        "settlement_value_dollars",
        "expiration_value",
        "prediction",
        "p_yes",
        "candidate_probability",
        "log_loss",
        "brier",
        "expected_pnl",
        "decision",
        "action",
        "order",
        "order_id",
    }
)

ROW_FIELDS = (
    "schema_version",
    "audit_design_fingerprint",
    "snapshot_index",
    "as_of_utc",
    "target_minute_start_utc",
    "target_minute_end_utc",
    "lookback_minute_start_utc",
    "lookback_minute_end_utc",
    "coinbase_current_available",
    "coinbase_current_price",
    "coinbase_current_raw_observation_refs",
    "coinbase_lookback_available",
    "coinbase_lookback_price",
    "coinbase_lookback_raw_observation_refs",
    "kraken_current_available",
    "kraken_current_price",
    "kraken_current_trade_ts",
    "kraken_current_publication_ts",
    "kraken_current_publication_lag_ms",
    "kraken_current_publication_age_at_decision_ms",
    "kraken_current_raw_observation_refs",
    "kraken_lookback_available",
    "kraken_lookback_price",
    "kraken_lookback_trade_ts",
    "kraken_lookback_publication_ts",
    "kraken_lookback_publication_lag_ms",
    "kraken_lookback_publication_age_at_decision_ms",
    "kraken_lookback_raw_observation_refs",
    "both_current_available",
    "both_lookback_available",
    "current_cross_source_disagreement_bps",
    "lookback_cross_source_disagreement_bps",
    "coinbase_live_bbo_price_19c",
    "kraken_live_bbo_price_19c",
    "coinbase_historical_vs_live_gap_bps",
    "kraken_historical_vs_live_gap_bps",
    "coinbase_live_local_first_seen_age_seconds_19c",
    "kraken_live_local_first_seen_age_seconds_19c",
    "coinbase_live_source_event_age_seconds_19c",
    "kraken_live_best_bid_publication_age_seconds_19c",
    "kraken_live_best_ask_publication_age_seconds_19c",
    "kraken_live_conservative_bbo_publication_age_seconds_19c",
    "historically_reconstructible_current_state",
    "historically_reconstructible_five_minute_pair",
    "exclusion_reasons",
)

EXCLUSION_FIELDS = (
    "schema_version",
    "audit_design_fingerprint",
    "snapshot_index",
    "as_of_utc",
    "reason",
)


@dataclass(frozen=True)
class CoinbaseMinute:
    minute_start_utc: str
    close_price: Decimal
    raw_observation_refs: tuple[str, ...]


@dataclass(frozen=True)
class KrakenTrade:
    price: Decimal
    trade_ts: str
    publication_ts: str


@dataclass(frozen=True)
class KrakenMinute:
    minute_start_utc: str
    selected_price: Decimal | None
    selected_trade_ts: str | None
    selected_publication_ts: str | None
    publication_lag_ms: float | None
    publication_age_at_decision_ms: float | None
    raw_observation_refs: tuple[str, ...]


@dataclass(frozen=True)
class Live19CState:
    snapshot_index: int
    as_of_utc: str
    coinbase_price: Decimal
    kraken_price: Decimal
    coinbase_local_age_seconds: float
    kraken_local_age_seconds: float
    coinbase_source_event_time_utc: str
    kraken_source_event_time_utc: str
    coinbase_raw_observation_ref: str
    kraken_raw_observation_ref: str


def _error(message: str) -> None:
    raise KxbtcdHistoricalMaterializationError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KxbtcdHistoricalMaterializationError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty UTC timestamp text")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise KxbtcdHistoricalMaterializationError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        _error(f"{name} must include timezone")
    parsed = parsed.astimezone(timezone.utc)
    return parsed


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _raw_ref(source: str, session_id: str, request_id: str) -> str:
    for value, name in (
        (source, "source"),
        (session_id, "session_id"),
        (request_id, "request_id"),
    ):
        if not isinstance(value, str) or not value.strip() or ":" in value:
            _error(f"raw {name} must be non-empty text without ':'")
    return f"raw:{source}:{session_id}:{request_id}"


def audit_design_definition() -> dict[str, Any]:
    """Return the exact Checkpoint-19D-A outcome-blind audit design."""

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_fingerprint": FROZEN_PROTOCOL_FINGERPRINT,
        "parent_19c_audit_design_fingerprint": PARENT_19C_AUDIT_DESIGN_FINGERPRINT,
        "parent_19c_run_id": PARENT_19C_RUN_ID,
        "parent_snapshot_count": EXPECTED_PARENT_SNAPSHOT_COUNT,
        "purpose": "outcome_blind_source_quality_and_historical_materialization_audit",
        "candidate_e_formula_frozen": False,
        "candidate_e_fitting_authorized": False,
        "outcome_access_authorized": False,
        "execution_authorized": False,
        "threshold_selection_authorized": False,
        "evidence_cohort_size_selection_authorized": False,
        "sources": {
            "coinbase_historical": {
                "source_id": COINBASE_SOURCE_ID,
                "base_url": COINBASE_BASE_URL,
                "path": COINBASE_CANDLES_PATH,
                "product_id": COINBASE_PRODUCT_ID,
                "granularity_seconds": COINBASE_GRANULARITY_SECONDS,
                "price_semantics": "official_one_minute_bucket_close_last_trade",
                "top_level_json_container": "array",
                "historical_publication_timestamp_available": False,
                "causality_boundary": "fully_completed_bucket_end_no_later_than_decision_time",
                "exact_historical_bbo_reconstruction": False,
            },
            "kraken_historical": {
                "source_id": KRAKEN_SOURCE_ID,
                "base_url": KRAKEN_BASE_URL,
                "path": KRAKEN_POSTTRADE_PATH,
                "symbol": KRAKEN_SYMBOL,
                "page_count": KRAKEN_PAGE_COUNT,
                "max_pages_per_minute": KRAKEN_MAX_PAGES_PER_MINUTE,
                "price_semantics": "last_trade_in_bucket_published_by_decision_time",
                "publication_timestamp_required": True,
                "exact_historical_bbo_reconstruction": False,
            },
        },
        "target_schedule": {
            "source": "exact_parent_19c_kxbtcd_snapshot_as_of_utc_values",
            "current_bucket": "last_fully_completed_UTC_one_minute_bucket",
            "lookback_bucket": "current_bucket_minus_exactly_300_seconds",
            "future_interpolation": False,
            "nearest_absolute_sampling": False,
            "carry_forward_missing_bucket": False,
            "same_minute_future_data": False,
        },
        "live_quality_reanalysis": {
            "use_parent_19c_raw_archives": True,
            "parent_coinbase_source_id": PARENT_19C_COINBASE_SOURCE_ID,
            "parent_kraken_source_id": PARENT_19C_KRAKEN_SOURCE_ID,
            "coinbase_source_event_age": True,
            "kraken_best_bid_publication_age": True,
            "kraken_best_ask_publication_age": True,
            "kraken_conservative_bbo_age": "max_bid_ask_publication_age",
            "local_first_seen_age": "reuse_parent_19c_monotonic_age_fields",
        },
        "descriptive_outputs_only": {
            "materialization_coverage": True,
            "current_cross_source_disagreement_bps": True,
            "lookback_cross_source_disagreement_bps": True,
            "kraken_trade_publication_lag": True,
            "historical_vs_live_price_gap_bps": True,
            "source_event_freshness": True,
        },
        "not_frozen_by_19d_a": [
            "E1_source_id_allow_list",
            "primary_vs_consensus_source_rule",
            "local_first_seen_staleness_threshold",
            "exchange_source_event_freshness_threshold",
            "cross_source_disagreement_threshold",
            "five_minute_alignment_tolerance_beyond_exact_bucket_rule",
            "Candidate_E_formula",
            "Candidate_E_feature_set",
            "E1_E2_E3_event_counts",
            "E1_E2_E3_calendar_coverage",
            "advancement_gate",
        ],
    }


def audit_design_fingerprint() -> str:
    payload = json.dumps(
        audit_design_definition(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# Set after the design object is finalized. validate_audit_design() makes drift fail closed.
FROZEN_AUDIT_DESIGN_FINGERPRINT = "023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c"


def validate_audit_design() -> None:
    validate_protocol()
    design = audit_design_definition()
    for field in (
        "candidate_e_formula_frozen",
        "candidate_e_fitting_authorized",
        "outcome_access_authorized",
        "execution_authorized",
        "threshold_selection_authorized",
        "evidence_cohort_size_selection_authorized",
    ):
        if design[field] is not False:
            _error(f"Checkpoint 19D-A safety invariant changed: {field}")
    if design["target_schedule"]["future_interpolation"] is not False:
        _error("future interpolation must remain prohibited")
    if design["target_schedule"]["carry_forward_missing_bucket"] is not False:
        _error("missing historical buckets must not be carried forward")
    if audit_design_fingerprint() != FROZEN_AUDIT_DESIGN_FINGERPRINT:
        _error("Checkpoint-19D-A audit design fingerprint changed")


def completed_minute_bounds(as_of_utc: str) -> tuple[str, str]:
    """Return the last fully completed UTC minute [start, end)."""

    as_of = _parse_utc(as_of_utc, "as_of_utc")
    floor = as_of.replace(second=0, microsecond=0)
    start = floor - timedelta(minutes=1)
    end = floor
    if end > as_of:
        _error("completed minute ended after decision time")
    return _format_utc(start), _format_utc(end)


def lookback_minute_bounds(as_of_utc: str) -> tuple[str, str]:
    current_start_text, current_end_text = completed_minute_bounds(as_of_utc)
    current_start = _parse_utc(current_start_text, "current_start")
    current_end = _parse_utc(current_end_text, "current_end")
    return (
        _format_utc(current_start - timedelta(seconds=TARGET_LOOKBACK_SECONDS)),
        _format_utc(current_end - timedelta(seconds=TARGET_LOOKBACK_SECONDS)),
    )


def parse_coinbase_candles_payload(
    payload: Any,
    *,
    raw_observation_ref: str,
) -> dict[str, CoinbaseMinute]:
    """Parse official Coinbase Exchange one-minute candle arrays.

    Coinbase documents each row as [time, low, high, open, close, volume].
    The audit uses only the bucket start and close, which is the last trade in
    the completed bucket.
    """

    if not isinstance(payload, list):
        _error("Coinbase candle payload must be a top-level array")
    result: dict[str, CoinbaseMinute] = {}
    for index, item in enumerate(payload):
        if not isinstance(item, list) or len(item) < 5:
            _error(f"Coinbase candle[{index}] must contain at least five values")
        try:
            epoch = int(item[0])
        except (TypeError, ValueError) as exc:
            raise KxbtcdHistoricalMaterializationError(
                f"Coinbase candle[{index}] time must be integer epoch seconds"
            ) from exc
        start = datetime.fromtimestamp(epoch, tz=timezone.utc)
        if start.second != 0 or start.microsecond != 0:
            _error("Coinbase one-minute candle start is not minute-aligned")
        close = _decimal(item[4], f"coinbase candle[{index}].close")
        if close <= 0:
            _error("Coinbase candle close must be positive")
        key = _format_utc(start)
        candidate = CoinbaseMinute(
            minute_start_utc=key,
            close_price=close,
            raw_observation_refs=(raw_observation_ref,),
        )
        prior = result.get(key)
        if prior is not None and prior.close_price != candidate.close_price:
            _error(f"conflicting Coinbase candles for minute {key}")
        result[key] = candidate
    return result


def parse_kraken_posttrade_payload(payload: Any) -> tuple[tuple[KrakenTrade, ...], str | None, int]:
    if not isinstance(payload, Mapping):
        _error("Kraken PostTrade payload must be an object")
    errors = payload.get("error")
    if errors is not None:
        if not isinstance(errors, list):
            _error("Kraken error must be a list")
        if errors:
            _error(f"Kraken PostTrade returned API errors: {errors}")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        _error("Kraken PostTrade result must be an object")
    trades = result.get("trades")
    if not isinstance(trades, list):
        _error("Kraken PostTrade trades must be a list")
    count_raw = result.get("count")
    try:
        count = int(count_raw)
    except (TypeError, ValueError) as exc:
        raise KxbtcdHistoricalMaterializationError("Kraken count must be integer") from exc
    if count != len(trades):
        _error("Kraken count does not match trade list length")
    last_ts = result.get("last_ts")
    if last_ts is not None:
        if not isinstance(last_ts, str):
            _error("Kraken last_ts must be timestamp text when present")
        last_ts = last_ts.strip() or None

    parsed: list[KrakenTrade] = []
    previous_trade_time: datetime | None = None
    for index, trade in enumerate(trades):
        if not isinstance(trade, Mapping):
            _error(f"Kraken trade[{index}] must be an object")
        if trade.get("symbol") != KRAKEN_SYMBOL:
            _error(f"Kraken trade[{index}] symbol mismatch")
        price = _decimal(trade.get("price"), f"kraken trade[{index}].price")
        if price <= 0:
            _error("Kraken trade price must be positive")
        trade_ts = _parse_utc(trade.get("trade_ts"), f"kraken trade[{index}].trade_ts")
        publication_ts = _parse_utc(
            trade.get("publication_ts"), f"kraken trade[{index}].publication_ts"
        )
        if publication_ts < trade_ts:
            _error("Kraken publication_ts cannot precede trade_ts")
        if previous_trade_time is not None and trade_ts < previous_trade_time:
            _error("Kraken trades are not chronological")
        previous_trade_time = trade_ts
        parsed.append(
            KrakenTrade(
                price=price,
                trade_ts=_format_utc(trade_ts),
                publication_ts=_format_utc(publication_ts),
            )
        )
    return tuple(parsed), last_ts, count


def select_kraken_minute(
    trades: Sequence[KrakenTrade],
    *,
    minute_start_utc: str,
    minute_end_utc: str,
    as_of_utc: str,
    raw_observation_refs: Sequence[str],
) -> KrakenMinute:
    start = _parse_utc(minute_start_utc, "minute_start_utc")
    end = _parse_utc(minute_end_utc, "minute_end_utc")
    as_of = _parse_utc(as_of_utc, "as_of_utc")
    if end - start != timedelta(minutes=1):
        _error("Kraken materialization bucket must be exactly one minute")
    if end > as_of:
        _error("Kraken materialization bucket is not fully completed")

    eligible: list[tuple[datetime, datetime, Decimal]] = []
    for trade in trades:
        trade_ts = _parse_utc(trade.trade_ts, "trade.trade_ts")
        publication_ts = _parse_utc(trade.publication_ts, "trade.publication_ts")
        if start <= trade_ts < end and publication_ts <= as_of:
            eligible.append((trade_ts, publication_ts, trade.price))

    refs = tuple(dict.fromkeys(raw_observation_refs))
    if not eligible:
        return KrakenMinute(
            minute_start_utc=_format_utc(start),
            selected_price=None,
            selected_trade_ts=None,
            selected_publication_ts=None,
            publication_lag_ms=None,
            publication_age_at_decision_ms=None,
            raw_observation_refs=refs,
        )

    # Latest execution time wins; publication time breaks an exact trade-time tie.
    trade_ts, publication_ts, price = max(eligible, key=lambda item: (item[0], item[1]))
    return KrakenMinute(
        minute_start_utc=_format_utc(start),
        selected_price=price,
        selected_trade_ts=_format_utc(trade_ts),
        selected_publication_ts=_format_utc(publication_ts),
        publication_lag_ms=(publication_ts - trade_ts).total_seconds() * 1000.0,
        publication_age_at_decision_ms=(as_of - publication_ts).total_seconds() * 1000.0,
        raw_observation_refs=refs,
    )


def parse_live_19c_state(rows_for_snapshot: Sequence[Mapping[str, Any]], *, snapshot_index: int) -> Live19CState:
    if not rows_for_snapshot:
        _error("19C snapshot has no feasibility rows")
    first = rows_for_snapshot[0]
    constant_fields = (
        "as_of_utc",
        "coinbase_price",
        "kraken_price",
        "coinbase_age_seconds",
        "kraken_age_seconds",
        "coinbase_source_event_time_utc",
        "kraken_source_event_time_utc",
        "coinbase_raw_observation_refs",
        "kraken_raw_observation_refs",
    )
    for row in rows_for_snapshot[1:]:
        for field in constant_fields:
            if row.get(field) != first.get(field):
                _error(f"19C snapshot field {field} is not constant across KXBTCD ladder")
    if first.get("coinbase_source_id") != PARENT_19C_COINBASE_SOURCE_ID:
        _error("19C Coinbase source_id mismatch")
    if first.get("kraken_source_id") != PARENT_19C_KRAKEN_SOURCE_ID:
        _error("19C Kraken source_id mismatch")
    cb_refs = first.get("coinbase_raw_observation_refs")
    kr_refs = first.get("kraken_raw_observation_refs")
    if not isinstance(cb_refs, list) or len(cb_refs) != 1:
        _error("19C Coinbase row must carry exactly one raw observation reference")
    if not isinstance(kr_refs, list) or len(kr_refs) != 1:
        _error("19C Kraken row must carry exactly one raw observation reference")
    return Live19CState(
        snapshot_index=snapshot_index,
        as_of_utc=_format_utc(_parse_utc(first.get("as_of_utc"), "19c.as_of_utc")),
        coinbase_price=_decimal(first.get("coinbase_price"), "19c.coinbase_price"),
        kraken_price=_decimal(first.get("kraken_price"), "19c.kraken_price"),
        coinbase_local_age_seconds=float(_decimal(first.get("coinbase_age_seconds"), "19c.coinbase_age_seconds")),
        kraken_local_age_seconds=float(_decimal(first.get("kraken_age_seconds"), "19c.kraken_age_seconds")),
        coinbase_source_event_time_utc=_format_utc(
            _parse_utc(first.get("coinbase_source_event_time_utc"), "19c.coinbase_source_event_time_utc")
        ),
        kraken_source_event_time_utc=_format_utc(
            _parse_utc(first.get("kraken_source_event_time_utc"), "19c.kraken_source_event_time_utc")
        ),
        coinbase_raw_observation_ref=str(cb_refs[0]),
        kraken_raw_observation_ref=str(kr_refs[0]),
    )


def raw_reference_from_record(record: Mapping[str, Any]) -> str:
    if record.get("schema_version") != "raw_http_exchange.v1":
        _error("raw archive record schema mismatch")
    source = record.get("source")
    session_id = record.get("session_id")
    request = record.get("request")
    if not isinstance(source, str) or not source.strip():
        _error("raw archive record missing source")
    if not isinstance(session_id, str) or not session_id.strip():
        _error("raw archive record missing session_id")
    if not isinstance(request, Mapping):
        _error("raw archive record missing request object")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        _error("raw archive record missing request_id")
    return _raw_ref(source, session_id, request_id)


def parse_raw_response_json(record: Mapping[str, Any]) -> Any:
    response = record.get("response")
    if not isinstance(response, Mapping):
        _error("required raw archive record has no HTTP response")
    if int(response.get("status_code", 0)) < 200 or int(response.get("status_code", 0)) >= 300:
        _error("required raw archive record is not a successful HTTP response")
    text = response.get("body_text")
    if not isinstance(text, str):
        _error("raw archive response body_text must be text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise KxbtcdHistoricalMaterializationError("raw archive body_text is not valid JSON") from exc


def coinbase_live_source_event_age_seconds(*, as_of_utc: str, raw_payload: Any) -> float:
    if not isinstance(raw_payload, Mapping):
        _error("19C Coinbase raw payload must be object")
    source_time = _parse_utc(raw_payload.get("time"), "coinbase.time")
    as_of = _parse_utc(as_of_utc, "as_of_utc")
    if source_time > as_of:
        _error("Coinbase source event time occurs after KXBTCD state")
    return (as_of - source_time).total_seconds()


def kraken_live_bbo_publication_ages_seconds(
    *, as_of_utc: str, raw_payload: Any
) -> tuple[float, float, float]:
    if not isinstance(raw_payload, Mapping):
        _error("19C Kraken raw payload must be object")
    errors = raw_payload.get("error")
    if errors is not None and errors != []:
        _error("19C Kraken raw payload contains API errors")
    result = raw_payload.get("result")
    if not isinstance(result, Mapping):
        _error("19C Kraken raw result must be object")
    if "bids" not in result or "asks" not in result:
        children = [value for value in result.values() if isinstance(value, Mapping)]
        matching = [value for value in children if "bids" in value and "asks" in value]
        if len(matching) != 1:
            _error("19C Kraken raw result has ambiguous bid/ask container")
        result = matching[0]
    bids = result.get("bids")
    asks = result.get("asks")
    if not isinstance(bids, list) or not bids or not isinstance(asks, list) or not asks:
        _error("19C Kraken raw top book is missing")
    if not isinstance(bids[0], Mapping) or not isinstance(asks[0], Mapping):
        _error("19C Kraken top levels must be objects")
    bid_ts = _parse_utc(bids[0].get("publication_ts"), "kraken.bid.publication_ts")
    ask_ts = _parse_utc(asks[0].get("publication_ts"), "kraken.ask.publication_ts")
    as_of = _parse_utc(as_of_utc, "as_of_utc")
    if bid_ts > as_of or ask_ts > as_of:
        _error("Kraken top-book publication timestamp occurs after KXBTCD state")
    bid_age = (as_of - bid_ts).total_seconds()
    ask_age = (as_of - ask_ts).total_seconds()
    return bid_age, ask_age, max(bid_age, ask_age)


def disagreement_bps(a: Decimal, b: Decimal) -> float:
    denominator = (a + b) / Decimal("2")
    if denominator <= 0:
        _error("cross-source disagreement denominator must be positive")
    return float(abs(a - b) / denominator * Decimal("10000"))


def historical_vs_live_gap_bps(historical: Decimal, live: Decimal) -> float:
    return disagreement_bps(historical, live)


def materialization_row(
    *,
    live: Live19CState,
    coinbase_current: CoinbaseMinute | None,
    coinbase_lookback: CoinbaseMinute | None,
    kraken_current: KrakenMinute,
    kraken_lookback: KrakenMinute,
    coinbase_live_source_event_age_seconds_19c: float,
    kraken_live_best_bid_publication_age_seconds_19c: float,
    kraken_live_best_ask_publication_age_seconds_19c: float,
    kraken_live_conservative_bbo_publication_age_seconds_19c: float,
) -> dict[str, Any]:
    validate_audit_design()
    current_start, current_end = completed_minute_bounds(live.as_of_utc)
    lookback_start, lookback_end = lookback_minute_bounds(live.as_of_utc)

    cb_current_available = coinbase_current is not None
    cb_lookback_available = coinbase_lookback is not None
    kr_current_available = kraken_current.selected_price is not None
    kr_lookback_available = kraken_lookback.selected_price is not None
    both_current = cb_current_available and kr_current_available
    both_lookback = cb_lookback_available and kr_lookback_available
    reasons: list[str] = []
    if not cb_current_available:
        reasons.append("coinbase_current_completed_minute_missing")
    if not cb_lookback_available:
        reasons.append("coinbase_exact_five_minute_lookback_missing")
    if not kr_current_available:
        reasons.append("kraken_current_completed_minute_missing_or_not_published_by_decision")
    if not kr_lookback_available:
        reasons.append("kraken_exact_five_minute_lookback_missing_or_not_published_by_decision")

    current_disagreement = None
    if both_current:
        assert coinbase_current is not None and kraken_current.selected_price is not None
        current_disagreement = disagreement_bps(
            coinbase_current.close_price, kraken_current.selected_price
        )
    lookback_disagreement = None
    if both_lookback:
        assert coinbase_lookback is not None and kraken_lookback.selected_price is not None
        lookback_disagreement = disagreement_bps(
            coinbase_lookback.close_price, kraken_lookback.selected_price
        )

    cb_gap = None
    if coinbase_current is not None:
        cb_gap = historical_vs_live_gap_bps(coinbase_current.close_price, live.coinbase_price)
    kr_gap = None
    if kraken_current.selected_price is not None:
        kr_gap = historical_vs_live_gap_bps(kraken_current.selected_price, live.kraken_price)

    row = {
        "schema_version": ROW_SCHEMA_VERSION,
        "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
        "snapshot_index": live.snapshot_index,
        "as_of_utc": live.as_of_utc,
        "target_minute_start_utc": current_start,
        "target_minute_end_utc": current_end,
        "lookback_minute_start_utc": lookback_start,
        "lookback_minute_end_utc": lookback_end,
        "coinbase_current_available": cb_current_available,
        "coinbase_current_price": _decimal_text(coinbase_current.close_price if coinbase_current else None),
        "coinbase_current_raw_observation_refs": list(coinbase_current.raw_observation_refs) if coinbase_current else [],
        "coinbase_lookback_available": cb_lookback_available,
        "coinbase_lookback_price": _decimal_text(coinbase_lookback.close_price if coinbase_lookback else None),
        "coinbase_lookback_raw_observation_refs": list(coinbase_lookback.raw_observation_refs) if coinbase_lookback else [],
        "kraken_current_available": kr_current_available,
        "kraken_current_price": _decimal_text(kraken_current.selected_price),
        "kraken_current_trade_ts": kraken_current.selected_trade_ts,
        "kraken_current_publication_ts": kraken_current.selected_publication_ts,
        "kraken_current_publication_lag_ms": kraken_current.publication_lag_ms,
        "kraken_current_publication_age_at_decision_ms": kraken_current.publication_age_at_decision_ms,
        "kraken_current_raw_observation_refs": list(kraken_current.raw_observation_refs),
        "kraken_lookback_available": kr_lookback_available,
        "kraken_lookback_price": _decimal_text(kraken_lookback.selected_price),
        "kraken_lookback_trade_ts": kraken_lookback.selected_trade_ts,
        "kraken_lookback_publication_ts": kraken_lookback.selected_publication_ts,
        "kraken_lookback_publication_lag_ms": kraken_lookback.publication_lag_ms,
        "kraken_lookback_publication_age_at_decision_ms": kraken_lookback.publication_age_at_decision_ms,
        "kraken_lookback_raw_observation_refs": list(kraken_lookback.raw_observation_refs),
        "both_current_available": both_current,
        "both_lookback_available": both_lookback,
        "current_cross_source_disagreement_bps": current_disagreement,
        "lookback_cross_source_disagreement_bps": lookback_disagreement,
        "coinbase_live_bbo_price_19c": _decimal_text(live.coinbase_price),
        "kraken_live_bbo_price_19c": _decimal_text(live.kraken_price),
        "coinbase_historical_vs_live_gap_bps": cb_gap,
        "kraken_historical_vs_live_gap_bps": kr_gap,
        "coinbase_live_local_first_seen_age_seconds_19c": live.coinbase_local_age_seconds,
        "kraken_live_local_first_seen_age_seconds_19c": live.kraken_local_age_seconds,
        "coinbase_live_source_event_age_seconds_19c": coinbase_live_source_event_age_seconds_19c,
        "kraken_live_best_bid_publication_age_seconds_19c": kraken_live_best_bid_publication_age_seconds_19c,
        "kraken_live_best_ask_publication_age_seconds_19c": kraken_live_best_ask_publication_age_seconds_19c,
        "kraken_live_conservative_bbo_publication_age_seconds_19c": kraken_live_conservative_bbo_publication_age_seconds_19c,
        "historically_reconstructible_current_state": both_current,
        "historically_reconstructible_five_minute_pair": both_current and both_lookback,
        "exclusion_reasons": reasons,
    }
    validate_materialization_row(row)
    return row


def validate_materialization_row(row: Mapping[str, Any]) -> None:
    missing = set(ROW_FIELDS) - set(row)
    extra = set(row) - set(ROW_FIELDS)
    if missing:
        _error(f"materialization row missing fields: {sorted(missing)}")
    if extra:
        _error(f"materialization row has extra fields: {sorted(extra)}")
    if FORBIDDEN_KEYS.intersection(row):
        _error("materialization row contains forbidden outcome/model/execution fields")
    if row.get("schema_version") != ROW_SCHEMA_VERSION:
        _error("materialization row schema_version mismatch")
    if row.get("audit_design_fingerprint") != FROZEN_AUDIT_DESIGN_FINGERPRINT:
        _error("materialization row audit fingerprint mismatch")
    if not isinstance(row.get("snapshot_index"), int) or row["snapshot_index"] < 0:
        _error("snapshot_index must be nonnegative integer")
    _parse_utc(row.get("as_of_utc"), "row.as_of_utc")
    current_start = _parse_utc(row.get("target_minute_start_utc"), "row.target_minute_start_utc")
    current_end = _parse_utc(row.get("target_minute_end_utc"), "row.target_minute_end_utc")
    lookback_start = _parse_utc(row.get("lookback_minute_start_utc"), "row.lookback_minute_start_utc")
    lookback_end = _parse_utc(row.get("lookback_minute_end_utc"), "row.lookback_minute_end_utc")
    if current_end - current_start != timedelta(minutes=1):
        _error("current target bucket must be one minute")
    if lookback_end - lookback_start != timedelta(minutes=1):
        _error("lookback bucket must be one minute")
    if current_start - lookback_start != timedelta(seconds=TARGET_LOOKBACK_SECONDS):
        _error("lookback bucket is not exactly five minutes before current bucket")
    reasons = row.get("exclusion_reasons")
    if not isinstance(reasons, list) or any(not isinstance(item, str) or not item for item in reasons):
        _error("exclusion_reasons must be a list of non-empty strings")
    if len(reasons) != len(set(reasons)):
        _error("exclusion_reasons contains duplicates")
    if row.get("historically_reconstructible_five_minute_pair") is True:
        if row.get("both_current_available") is not True or row.get("both_lookback_available") is not True:
            _error("five-minute pair cannot be reconstructible without both current and lookback sources")


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    if not 0 <= probability <= 1:
        _error("percentile probability must be within [0,1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def distribution_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return {
        "count": len(finite),
        "p50": _percentile(finite, 0.50),
        "p90": _percentile(finite, 0.90),
        "p95": _percentile(finite, 0.95),
        "p99": _percentile(finite, 0.99),
        "max": max(finite) if finite else None,
    }


def summarize_materialization(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    validate_audit_design()
    if len(rows) != EXPECTED_PARENT_SNAPSHOT_COUNT:
        _error(
            f"expected {EXPECTED_PARENT_SNAPSHOT_COUNT} materialization rows, got {len(rows)}"
        )
    for row in rows:
        validate_materialization_row(row)
    indices = [int(row["snapshot_index"]) for row in rows]
    if indices != list(range(EXPECTED_PARENT_SNAPSHOT_COUNT)):
        _error("snapshot indices are not exact contiguous parent-19C order")

    def values(name: str) -> list[float]:
        output: list[float] = []
        for row in rows:
            value = row.get(name)
            if value is None:
                continue
            output.append(float(value))
        return output

    summary = {
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_fingerprint": FROZEN_PROTOCOL_FINGERPRINT,
        "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
        "parent_19c_run_id": PARENT_19C_RUN_ID,
        "snapshot_count": len(rows),
        "coinbase_current_coverage_rate": sum(bool(r["coinbase_current_available"]) for r in rows) / len(rows),
        "coinbase_lookback_coverage_rate": sum(bool(r["coinbase_lookback_available"]) for r in rows) / len(rows),
        "kraken_current_coverage_rate": sum(bool(r["kraken_current_available"]) for r in rows) / len(rows),
        "kraken_lookback_coverage_rate": sum(bool(r["kraken_lookback_available"]) for r in rows) / len(rows),
        "both_current_coverage_rate": sum(bool(r["both_current_available"]) for r in rows) / len(rows),
        "both_five_minute_pair_coverage_rate": sum(bool(r["historically_reconstructible_five_minute_pair"]) for r in rows) / len(rows),
        "current_cross_source_disagreement_bps": distribution_summary(values("current_cross_source_disagreement_bps")),
        "lookback_cross_source_disagreement_bps": distribution_summary(values("lookback_cross_source_disagreement_bps")),
        "coinbase_historical_vs_live_gap_bps": distribution_summary(values("coinbase_historical_vs_live_gap_bps")),
        "kraken_historical_vs_live_gap_bps": distribution_summary(values("kraken_historical_vs_live_gap_bps")),
        "kraken_current_publication_lag_ms": distribution_summary(values("kraken_current_publication_lag_ms")),
        "coinbase_live_local_first_seen_age_seconds_19c": distribution_summary(values("coinbase_live_local_first_seen_age_seconds_19c")),
        "kraken_live_local_first_seen_age_seconds_19c": distribution_summary(values("kraken_live_local_first_seen_age_seconds_19c")),
        "coinbase_live_source_event_age_seconds_19c": distribution_summary(values("coinbase_live_source_event_age_seconds_19c")),
        "kraken_live_best_bid_publication_age_seconds_19c": distribution_summary(values("kraken_live_best_bid_publication_age_seconds_19c")),
        "kraken_live_best_ask_publication_age_seconds_19c": distribution_summary(values("kraken_live_best_ask_publication_age_seconds_19c")),
        "kraken_live_conservative_bbo_publication_age_seconds_19c": distribution_summary(values("kraken_live_conservative_bbo_publication_age_seconds_19c")),
        "candidate_e_formula_frozen": False,
        "candidate_e_fitting_performed": False,
        "outcomes_accessed": False,
        "thresholds_selected": False,
        "evidence_cohort_sizes_selected": False,
        "checkpoint17_terminal_used": False,
        "execution_performed": False,
        "orders_placed": 0,
    }
    return summary
