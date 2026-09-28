"""Checkpoint-19B outcome-blind independent-BTC feasibility audit core.

This module is deterministic and side-effect free.  It parses raw-first public
market-data responses that have already been archived by the caller, builds the
Checkpoint-19A feasibility rows, and summarizes source/timing coverage.

It does not fetch outcomes, fit Candidate E, score a model, or perform any
execution action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from typing import Any, Mapping, Protocol, Sequence

from src.kxbtcd_successor_research_protocol import (
    FROZEN_PROTOCOL_FINGERPRINT,
    FEASIBILITY_ROW_SCHEMA_VERSION,
    validate_feasibility_row,
    validate_protocol,
)


class KxbtcdIndependentBtcFeasibilityError(ValueError):
    """Raised when Checkpoint-19B source-alignment invariants are violated."""


AUDIT_SCHEMA_VERSION = "kxbtcd_independent_btc_feasibility_audit.v1"
EXCLUSION_SCHEMA_VERSION = "kxbtcd_independent_btc_feasibility_exclusion.v1"
CHECKPOINT_ID = "19B"
SERIES_TICKER = "KXBTCD"

# These IDs identify the bounded engineering endpoints used by the feasibility
# audit only.  They are deliberately marked provisional: Checkpoint 19B does
# not freeze an E1 model-feature source ID.
COINBASE_PROVISIONAL_SOURCE_ID = (
    "coinbase.exchange.public_rest.product_book.btc_usd.provisional_19b"
)
KRAKEN_PROVISIONAL_SOURCE_ID = (
    "kraken.spot.public_rest.pretrade.btc_usd.provisional_19b"
)
COINBASE_INSTRUMENT_ID = "BTC-USD"
KRAKEN_INSTRUMENT_ID = "BTC/USD"

COINBASE_BASE_URL = "https://api.exchange.coinbase.com"
COINBASE_BOOK_PATH = "/products/BTC-USD/book"
COINBASE_BOOK_PARAMS = {"level": 1}
KRAKEN_BASE_URL = "https://api.kraken.com"
KRAKEN_PRETRADE_PATH = "/0/public/PreTrade"
KRAKEN_PRETRADE_PARAMS = {"symbol": "BTC/USD"}
KALSHI_MARKETS_PATH = "/markets"
KALSHI_MARKETS_PARAMS = {
    "series_ticker": SERIES_TICKER,
    "status": "open",
    "mve_filter": "exclude",
    "limit": 1000,
}

DEFAULT_DURATION_SECONDS = 420
DEFAULT_EXTERNAL_INTERVAL_SECONDS = 2.0
DEFAULT_KALSHI_INTERVAL_SECONDS = 10.0
FIVE_MINUTE_LOOKBACK_SECONDS = 300
MAX_CONSECUTIVE_SOURCE_FAILURES = 5

EXCLUSION_FIELDS = (
    "schema_version",
    "audit_design_fingerprint",
    "kalshi_raw_observation_ref",
    "event_ticker",
    "market_ticker",
    "as_of_utc",
    "reason",
)

FORBIDDEN_DERIVED_KEYS = frozenset(
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


@dataclass(frozen=True)
class ReferenceObservation:
    """One locally received, raw-lineaged external BTC book midpoint."""

    source_family: str
    source_id: str
    instrument_id: str
    source_event_time_utc: str
    price: Decimal
    raw_observation_ref: str
    local_receive_utc: str
    local_receive_monotonic_ns: int


@dataclass(frozen=True)
class MaterializedBatch:
    rows: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]


def _error(message: str) -> None:
    raise KxbtcdIndependentBtcFeasibilityError(message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KxbtcdIndependentBtcFeasibilityError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _parse_utc(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KxbtcdIndependentBtcFeasibilityError(
            f"{name} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _error(f"{name} must carry UTC timezone information")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _raw_ref(response: RawFirstJsonResponse) -> str:
    return "raw:" + ":".join(
        [
            _text(response.raw_record.source, "raw source"),
            _text(response.raw_record.session_id, "raw session_id"),
            _text(response.raw_record.request_id, "raw request_id"),
        ]
    )


def audit_design_definition() -> dict[str, Any]:
    """Return the exact Checkpoint-19B engineering-audit design.

    This freezes how the feasibility evidence is collected, but intentionally
    does not freeze any Candidate-E feature formula or E1 source-quality gate.
    """

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_fingerprint": FROZEN_PROTOCOL_FINGERPRINT,
        "purpose": "outcome_blind_independent_btc_source_alignment_feasibility",
        "candidate_e_formula_frozen": False,
        "candidate_e_fitting_authorized": False,
        "outcome_access_authorized": False,
        "execution_authorized": False,
        "subsecond_lead_lag_authorized": False,
        "sources": {
            "coinbase": {
                "source_id": COINBASE_PROVISIONAL_SOURCE_ID,
                "status": "provisional_engineering_endpoint_not_E1_frozen",
                "base_url": COINBASE_BASE_URL,
                "path": COINBASE_BOOK_PATH,
                "params": dict(COINBASE_BOOK_PARAMS),
                "instrument_id": COINBASE_INSTRUMENT_ID,
                "diagnostic_price": "best_bid_ask_midpoint",
            },
            "kraken": {
                "source_id": KRAKEN_PROVISIONAL_SOURCE_ID,
                "status": "provisional_engineering_endpoint_not_E1_frozen",
                "base_url": KRAKEN_BASE_URL,
                "path": KRAKEN_PRETRADE_PATH,
                "params": dict(KRAKEN_PRETRADE_PARAMS),
                "instrument_id": KRAKEN_INSTRUMENT_ID,
                "diagnostic_price": "best_bid_ask_midpoint",
            },
            "kalshi": {
                "series_ticker": SERIES_TICKER,
                "path": KALSHI_MARKETS_PATH,
                "params": dict(KALSHI_MARKETS_PARAMS),
            },
        },
        "bounded_collection": {
            "default_duration_seconds": DEFAULT_DURATION_SECONDS,
            "default_external_interval_seconds": DEFAULT_EXTERNAL_INTERVAL_SECONDS,
            "default_kalshi_interval_seconds": DEFAULT_KALSHI_INTERVAL_SECONDS,
            "five_minute_lookback_seconds": FIVE_MINUTE_LOOKBACK_SECONDS,
            "request_order": (
                "alternate_coinbase_kraken_order_each_external_cycle; "
                "request_KXBTCD_only_after_current_external_attempts"
            ),
            "causal_join": (
                "external_local_receive_monotonic_ns <= "
                "kalshi_local_receive_monotonic_ns"
            ),
            "future_interpolation": False,
        },
        "descriptive_outputs": {
            "source_availability": True,
            "local_first_seen_age_seconds": True,
            "cross_source_disagreement_bps": True,
            "five_minute_causal_lookback_coverage": True,
            "KXBTCD_TTC_coverage": True,
            "request_receive_skew_diagnostic": True,
        },
        "not_frozen_by_19B": [
            "E1_source_id_selection",
            "source_staleness_threshold",
            "cross_source_disagreement_threshold",
            "consensus_price_formula",
            "Candidate_E_formula",
            "Candidate_E_feature_set",
            "E1_E2_E3_event_counts",
            "E1_E2_E3_calendar_coverage",
            "advancement_gate",
        ],
        "max_consecutive_source_failures_before_collection_abort": (
            MAX_CONSECUTIVE_SOURCE_FAILURES
        ),
    }


def audit_design_fingerprint() -> str:
    payload = json.dumps(
        audit_design_definition(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# Populated after the design object is finalized.  validate_audit_design() makes
# accidental drift fail closed.
FROZEN_AUDIT_DESIGN_FINGERPRINT = "41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be"


def validate_audit_design() -> None:
    validate_protocol()
    design = audit_design_definition()
    if design["candidate_e_formula_frozen"] is not False:
        _error("Checkpoint 19B must not freeze Candidate E")
    if design["candidate_e_fitting_authorized"] is not False:
        _error("Checkpoint 19B must not fit Candidate E")
    if design["outcome_access_authorized"] is not False:
        _error("Checkpoint 19B must remain outcome-blind")
    if design["execution_authorized"] is not False:
        _error("Checkpoint 19B must remain execution-free")
    if design["subsecond_lead_lag_authorized"] is not False:
        _error("sub-second lead/lag remains unauthorized")
    if audit_design_fingerprint() != FROZEN_AUDIT_DESIGN_FINGERPRINT:
        _error("Checkpoint-19B audit design fingerprint changed")


def _top_book_midpoint(
    *,
    bid_price: Any,
    ask_price: Any,
    name: str,
) -> Decimal:
    bid = _decimal(bid_price, f"{name}.bid")
    ask = _decimal(ask_price, f"{name}.ask")
    if bid <= 0 or ask <= 0 or bid > ask:
        _error(f"{name} top-of-book prices are invalid")
    return (bid + ask) / Decimal("2")


def parse_coinbase_book(response: RawFirstJsonResponse) -> ReferenceObservation:
    """Parse one archived Coinbase Exchange BTC-USD level-1 book snapshot."""

    payload = response.payload
    bids = payload.get("bids")
    asks = payload.get("asks")
    if not isinstance(bids, list) or not bids:
        _error("Coinbase book bids must be a non-empty list")
    if not isinstance(asks, list) or not asks:
        _error("Coinbase book asks must be a non-empty list")
    if not isinstance(bids[0], list) or not bids[0]:
        _error("Coinbase best bid level must be an array")
    if not isinstance(asks[0], list) or not asks[0]:
        _error("Coinbase best ask level must be an array")
    midpoint = _top_book_midpoint(
        bid_price=bids[0][0], ask_price=asks[0][0], name="coinbase"
    )
    source_time = _format_utc(_parse_utc(payload.get("time"), "coinbase.time"))
    if response.received_monotonic_ns < response.request_started_monotonic_ns:
        _error("Coinbase local monotonic timing moved backward")
    return ReferenceObservation(
        source_family="coinbase",
        source_id=COINBASE_PROVISIONAL_SOURCE_ID,
        instrument_id=COINBASE_INSTRUMENT_ID,
        source_event_time_utc=source_time,
        price=midpoint,
        raw_observation_ref=_raw_ref(response),
        local_receive_utc=_format_utc(
            _parse_utc(response.received_at_utc, "coinbase.received_at_utc")
        ),
        local_receive_monotonic_ns=response.received_monotonic_ns,
    )


def _kraken_result(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    errors = payload.get("error")
    if errors is not None:
        if not isinstance(errors, list):
            _error("Kraken error field must be a list")
        if errors:
            _error(f"Kraken returned API errors: {errors}")
    result = payload.get("result")
    if not isinstance(result, Mapping):
        _error("Kraken result must be an object")
    if "bids" in result and "asks" in result:
        return result
    # Tolerate a one-symbol wrapper while preserving the exact raw payload.
    children = [value for value in result.values() if isinstance(value, Mapping)]
    matching = [child for child in children if "bids" in child and "asks" in child]
    if len(matching) == 1:
        return matching[0]
    _error("Kraken result does not contain one unambiguous bid/ask book")


def parse_kraken_pretrade(response: RawFirstJsonResponse) -> ReferenceObservation:
    """Parse one archived Kraken public BTC/USD pre-trade book snapshot."""

    result = _kraken_result(response.payload)
    bids = result.get("bids")
    asks = result.get("asks")
    if not isinstance(bids, list) or not bids:
        _error("Kraken bids must be a non-empty list")
    if not isinstance(asks, list) or not asks:
        _error("Kraken asks must be a non-empty list")
    if not isinstance(bids[0], Mapping) or not isinstance(asks[0], Mapping):
        _error("Kraken best bid/ask levels must be objects")
    midpoint = _top_book_midpoint(
        bid_price=bids[0].get("price"),
        ask_price=asks[0].get("price"),
        name="kraken",
    )
    bid_time = _parse_utc(bids[0].get("publication_ts"), "kraken.bid.publication_ts")
    ask_time = _parse_utc(asks[0].get("publication_ts"), "kraken.ask.publication_ts")
    source_time = _format_utc(max(bid_time, ask_time))
    if response.received_monotonic_ns < response.request_started_monotonic_ns:
        _error("Kraken local monotonic timing moved backward")
    return ReferenceObservation(
        source_family="kraken",
        source_id=KRAKEN_PROVISIONAL_SOURCE_ID,
        instrument_id=KRAKEN_INSTRUMENT_ID,
        source_event_time_utc=source_time,
        price=midpoint,
        raw_observation_ref=_raw_ref(response),
        local_receive_utc=_format_utc(
            _parse_utc(response.received_at_utc, "kraken.received_at_utc")
        ),
        local_receive_monotonic_ns=response.received_monotonic_ns,
    )


def _strike_dollars(market: Mapping[str, Any]) -> Decimal:
    strike_type = market.get("strike_type")
    if strike_type != "greater":
        _error("KXBTCD feasibility market must use strike_type='greater'")
    for key in ("floor_strike", "functional_strike"):
        value = market.get(key)
        if value is None or str(value).strip() == "":
            continue
        try:
            strike = _decimal(value, f"market.{key}")
        except KxbtcdIndependentBtcFeasibilityError:
            continue
        if strike > 0:
            return strike
    _error("KXBTCD market has no positive threshold strike")


def _market_quote(market: Mapping[str, Any]) -> tuple[Decimal, Decimal]:
    bid = _decimal(market.get("yes_bid_dollars"), "market.yes_bid_dollars")
    ask = _decimal(market.get("yes_ask_dollars"), "market.yes_ask_dollars")
    if bid < 0 or ask < 0 or bid > 1 or ask > 1 or bid > ask:
        _error("KXBTCD yes bid/ask are not a valid probability quote")
    # A zero/zero or one/one locked endpoint is a real quoted state; keep it.
    return (bid + ask) / Decimal("2"), ask - bid


def _source_row_values(
    observation: ReferenceObservation | None,
    *,
    family: str,
    as_of_utc: datetime,
    as_of_monotonic_ns: int,
) -> tuple[bool, str | None, str | None, str | None, str | None, list[str]]:
    if observation is None:
        return False, None, None, None, None, []
    if observation.source_family != family:
        _error(f"expected {family} observation, got {observation.source_family}")
    if observation.local_receive_monotonic_ns > as_of_monotonic_ns:
        _error(f"{family} observation was received after the KXBTCD state")
    source_time = _parse_utc(
        observation.source_event_time_utc, f"{family}.source_event_time_utc"
    )
    # Cross-clock surprises are not clamped.  A source timestamp apparently in
    # the future is excluded from the protocol row and remains visible in raw.
    if source_time > as_of_utc:
        return False, None, None, None, None, []
    age_seconds = Decimal(as_of_monotonic_ns - observation.local_receive_monotonic_ns) / Decimal("1000000000")
    return (
        True,
        observation.source_id,
        _format_utc(source_time),
        _decimal_text(observation.price),
        _decimal_text(age_seconds),
        [observation.raw_observation_ref],
    )


def has_five_minute_causal_lookback(
    history: Sequence[ReferenceObservation],
    *,
    as_of_monotonic_ns: int,
) -> bool:
    """Return whether a same-source observation was already known >=5m earlier.

    This is a structural coverage flag only.  It does not freeze a future
    nearest-neighbor tolerance, interpolation rule, or five-minute return feature.
    """

    target_ns = as_of_monotonic_ns - FIVE_MINUTE_LOOKBACK_SECONDS * 1_000_000_000
    return any(item.local_receive_monotonic_ns <= target_ns for item in history)


def _disagreement_bps(a: Decimal, b: Decimal) -> Decimal:
    denominator = (a + b) / Decimal("2")
    if denominator <= 0:
        _error("cross-source midpoint denominator must be positive")
    return abs(a - b) / denominator * Decimal("10000")


def _state_id(raw_ref: str, market_ticker: str, as_of_utc: str) -> str:
    payload = f"{raw_ref}|{market_ticker}|{as_of_utc}"
    return "kxbtcd19b:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _exclusion(
    *,
    kalshi_raw_ref: str,
    as_of_utc: str,
    event_ticker: str,
    market_ticker: str,
    reason: str,
) -> dict[str, Any]:
    row = {
        "schema_version": EXCLUSION_SCHEMA_VERSION,
        "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
        "kalshi_raw_observation_ref": kalshi_raw_ref,
        "event_ticker": event_ticker,
        "market_ticker": market_ticker,
        "as_of_utc": as_of_utc,
        "reason": reason,
    }
    if set(row) != set(EXCLUSION_FIELDS):
        _error("exclusion row schema drift")
    return row


def materialize_kxbtcd_snapshot(
    kalshi_response: RawFirstJsonResponse,
    *,
    coinbase_observation: ReferenceObservation | None,
    kraken_observation: ReferenceObservation | None,
    coinbase_history: Sequence[ReferenceObservation],
    kraken_history: Sequence[ReferenceObservation],
) -> MaterializedBatch:
    """Build protocol-valid feasibility rows from one archived open-market snapshot."""

    validate_audit_design()
    payload = kalshi_response.payload
    markets = payload.get("markets")
    if not isinstance(markets, list):
        _error("Kalshi markets field must be a list")
    cursor = payload.get("cursor", "")
    if cursor is None:
        cursor = ""
    if not isinstance(cursor, str):
        _error("Kalshi market-list cursor must be text")
    if cursor:
        _error("KXBTCD open-market snapshot is paginated; partial snapshots are rejected")

    as_of = _parse_utc(kalshi_response.received_at_utc, "kalshi.received_at_utc")
    as_of_text = _format_utc(as_of)
    as_of_mono = kalshi_response.received_monotonic_ns
    if as_of_mono < kalshi_response.request_started_monotonic_ns:
        _error("Kalshi local monotonic timing moved backward")
    kalshi_ref = _raw_ref(kalshi_response)

    cb = _source_row_values(
        coinbase_observation,
        family="coinbase",
        as_of_utc=as_of,
        as_of_monotonic_ns=as_of_mono,
    )
    kr = _source_row_values(
        kraken_observation,
        family="kraken",
        as_of_utc=as_of,
        as_of_monotonic_ns=as_of_mono,
    )
    cb_available, cb_source_id, cb_time, cb_price, cb_age, cb_refs = cb
    kr_available, kr_source_id, kr_time, kr_price, kr_age, kr_refs = kr
    cb_lookback = cb_available and has_five_minute_causal_lookback(
        coinbase_history, as_of_monotonic_ns=as_of_mono
    )
    kr_lookback = kr_available and has_five_minute_causal_lookback(
        kraken_history, as_of_monotonic_ns=as_of_mono
    )

    disagreement: str | None = None
    if cb_available and kr_available:
        assert coinbase_observation is not None and kraken_observation is not None
        disagreement = _decimal_text(
            _disagreement_bps(coinbase_observation.price, kraken_observation.price)
        )

    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen_tickers: set[str] = set()
    for index, market in enumerate(markets):
        if not isinstance(market, Mapping):
            _error(f"Kalshi markets[{index}] must be an object")
        event_ticker = str(market.get("event_ticker") or "").strip()
        market_ticker = str(market.get("ticker") or "").strip()
        if not event_ticker or not market_ticker:
            exclusions.append(
                _exclusion(
                    kalshi_raw_ref=kalshi_ref,
                    as_of_utc=as_of_text,
                    event_ticker=event_ticker,
                    market_ticker=market_ticker,
                    reason="missing_market_identity",
                )
            )
            continue
        if market_ticker in seen_tickers:
            _error(f"duplicate market ticker in one KXBTCD snapshot: {market_ticker}")
        seen_tickers.add(market_ticker)
        try:
            close_time = _parse_utc(market.get("close_time"), "market.close_time")
            ttc_seconds = Decimal(str((close_time - as_of).total_seconds()))
            if ttc_seconds <= 0:
                raise KxbtcdIndependentBtcFeasibilityError("market_not_future_open_state")
            strike = _strike_dollars(market)
            q_market, spread = _market_quote(market)
        except KxbtcdIndependentBtcFeasibilityError as exc:
            exclusions.append(
                _exclusion(
                    kalshi_raw_ref=kalshi_ref,
                    as_of_utc=as_of_text,
                    event_ticker=event_ticker,
                    market_ticker=market_ticker,
                    reason=str(exc),
                )
            )
            continue

        structurally_usable = cb_available or kr_available
        exclusion_reasons = [] if structurally_usable else ["no_independent_btc_source_available"]
        row = {
            "schema_version": FEASIBILITY_ROW_SCHEMA_VERSION,
            "protocol_fingerprint": FROZEN_PROTOCOL_FINGERPRINT,
            "state_id": _state_id(kalshi_ref, market_ticker, as_of_text),
            "event_ticker": event_ticker,
            "market_ticker": market_ticker,
            "as_of_utc": as_of_text,
            "time_to_close_seconds": _decimal_text(ttc_seconds),
            "strike_dollars": _decimal_text(strike),
            "q_market": _decimal_text(q_market),
            "spread": _decimal_text(spread),
            "kalshi_raw_observation_refs": [kalshi_ref],
            "coinbase_observation_available": cb_available,
            "coinbase_source_id": cb_source_id,
            "coinbase_source_event_time_utc": cb_time,
            "coinbase_price": cb_price,
            "coinbase_age_seconds": cb_age,
            "coinbase_raw_observation_refs": cb_refs,
            "kraken_observation_available": kr_available,
            "kraken_source_id": kr_source_id,
            "kraken_source_event_time_utc": kr_time,
            "kraken_price": kr_price,
            "kraken_age_seconds": kr_age,
            "kraken_raw_observation_refs": kr_refs,
            "cross_source_price_disagreement_bps": disagreement,
            "five_minute_lookback_available_coinbase": bool(cb_lookback),
            "five_minute_lookback_available_kraken": bool(kr_lookback),
            "structurally_usable_for_design": structurally_usable,
            "exclusion_reasons": exclusion_reasons,
        }
        if FORBIDDEN_DERIVED_KEYS.intersection(row):
            _error("feasibility row leaked a forbidden downstream field")
        validate_feasibility_row(row)
        rows.append(row)

    return MaterializedBatch(rows=tuple(rows), exclusions=tuple(exclusions))


def _percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def summarize_rows(
    rows: Sequence[Mapping[str, Any]],
    exclusions: Sequence[Mapping[str, Any]],
    *,
    external_cycle_count: int,
    kalshi_snapshot_count: int,
    coinbase_attempt_count: int,
    coinbase_success_count: int,
    kraken_attempt_count: int,
    kraken_success_count: int,
    receive_skew_ms: Sequence[float] = (),
) -> dict[str, Any]:
    """Return outcome-blind descriptive coverage statistics only."""

    validate_audit_design()
    for row in rows:
        validate_feasibility_row(row)
    if any(FORBIDDEN_DERIVED_KEYS.intersection(item) for item in exclusions):
        _error("exclusion artifact contains a forbidden downstream field")

    def _values(field: str) -> list[float]:
        output: list[float] = []
        for row in rows:
            value = row.get(field)
            if value is not None:
                output.append(float(value))
        return output

    cb_ages = _values("coinbase_age_seconds")
    kr_ages = _values("kraken_age_seconds")
    disagreements = _values("cross_source_price_disagreement_bps")
    ttcs = _values("time_to_close_seconds")
    row_count = len(rows)
    usable_count = sum(bool(row["structurally_usable_for_design"]) for row in rows)
    cb_available = sum(bool(row["coinbase_observation_available"]) for row in rows)
    kr_available = sum(bool(row["kraken_observation_available"]) for row in rows)
    both_available = sum(
        bool(row["coinbase_observation_available"])
        and bool(row["kraken_observation_available"])
        for row in rows
    )
    cb_lookback = sum(
        bool(row["five_minute_lookback_available_coinbase"]) for row in rows
    )
    kr_lookback = sum(
        bool(row["five_minute_lookback_available_kraken"]) for row in rows
    )

    def _rate(count: int, denominator: int) -> float | None:
        return count / denominator if denominator else None

    ttc_band_counts = {
        "0_to_30m": sum(0 < value <= 1800 for value in ttcs),
        "30_to_60m": sum(1800 < value <= 3600 for value in ttcs),
        "1_to_4h": sum(3600 < value <= 14400 for value in ttcs),
        "4_to_24h": sum(14400 < value <= 86400 for value in ttcs),
        "gt_24h": sum(value > 86400 for value in ttcs),
    }

    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_fingerprint": FROZEN_PROTOCOL_FINGERPRINT,
        "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
        "interpretation": "outcome_blind_feasibility_only_not_model_evidence",
        "external_cycle_count": external_cycle_count,
        "kalshi_snapshot_count": kalshi_snapshot_count,
        "feasibility_row_count": row_count,
        "exclusion_row_count": len(exclusions),
        "unique_event_count": len({str(row["event_ticker"]) for row in rows}),
        "unique_market_count": len({str(row["market_ticker"]) for row in rows}),
        "structurally_usable_row_count": usable_count,
        "structurally_usable_row_rate": _rate(usable_count, row_count),
        "coinbase_request_success_rate": _rate(
            coinbase_success_count, coinbase_attempt_count
        ),
        "kraken_request_success_rate": _rate(kraken_success_count, kraken_attempt_count),
        "coinbase_row_availability_rate": _rate(cb_available, row_count),
        "kraken_row_availability_rate": _rate(kr_available, row_count),
        "both_source_row_availability_rate": _rate(both_available, row_count),
        "coinbase_five_minute_lookback_row_rate": _rate(cb_lookback, row_count),
        "kraken_five_minute_lookback_row_rate": _rate(kr_lookback, row_count),
        "coinbase_source_age_seconds": {
            "p50": _percentile(cb_ages, 0.50),
            "p95": _percentile(cb_ages, 0.95),
            "max": max(cb_ages) if cb_ages else None,
        },
        "kraken_source_age_seconds": {
            "p50": _percentile(kr_ages, 0.50),
            "p95": _percentile(kr_ages, 0.95),
            "max": max(kr_ages) if kr_ages else None,
        },
        "cross_source_price_disagreement_bps": {
            "p50": _percentile(disagreements, 0.50),
            "p95": _percentile(disagreements, 0.95),
            "max": max(disagreements) if disagreements else None,
        },
        "external_receive_skew_ms": {
            "p50": _percentile(list(receive_skew_ms), 0.50),
            "p95": _percentile(list(receive_skew_ms), 0.95),
            "max": max(receive_skew_ms) if receive_skew_ms else None,
        },
        "time_to_close_seconds": {
            "min": min(ttcs) if ttcs else None,
            "p50": _percentile(ttcs, 0.50),
            "max": max(ttcs) if ttcs else None,
        },
        "time_to_close_band_row_counts": ttc_band_counts,
        "candidate_e_formula_frozen": False,
        "candidate_e_fitting_performed": False,
        "outcomes_accessed": False,
        "checkpoint17_terminal_used": False,
        "execution_performed": False,
        "orders_placed": 0,
        "thresholds_selected_from_outcomes": False,
    }
