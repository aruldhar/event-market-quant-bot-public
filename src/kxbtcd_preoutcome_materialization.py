"""Frozen pre-outcome materialization rules for KXBTCD Candidate B.

This module is deliberately network-free and outcome-blind. It freezes how a
future raw-first collector will reduce the validated KXBTCD historical universe
to a bounded offline research dataset before any new labels are opened.

The materialized states use ``state_view='historical_reconstructed'``. Their
historical ``as_of_utc`` comes from the selected source candle. Their local
monotonic timestamp records when the historical payload was reconstructed on
this machine; it is not evidence that the live system observed the state at the
historical instant.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import json
from typing import Any, Mapping, Sequence

from .btc_state_feature_contract import (
    STATE_SCHEMA_VERSION,
    contract_fingerprint as state_contract_fingerprint,
    validate_synchronized_state,
)
from .kxbtcd_chronological_split_contract import (
    PARTITIONS,
    SPLIT_ROW_FIELDS,
    SPLIT_ROW_SCHEMA_VERSION,
    TARGET_REGIME_ID,
    design_fingerprint as split_design_fingerprint,
)
from .kxbtcd_preoutcome_dataset import dataset_design_fingerprint


class KxbtcdPreoutcomeMaterializationError(ValueError):
    """Raised when the frozen materialization contract is violated."""


MATERIALIZATION_CONTRACT_VERSION = "kxbtcd_preoutcome_materialization.v3"
CONSERVATIVE_MODERN_START_UTC = "2025-03-22T17:00:00Z"
REGIME_FRAME_POLICY_ID = "checkpoint10_first_sample_proven_modern_event"
SELECTED_EVENT_SCHEMA_VERSION = "kxbtcd_materialization_selected_event.v1"
SELECTED_MARKET_SCHEMA_VERSION = "kxbtcd_materialization_selected_market.v1"
ANCHOR_SELECTION_SCHEMA_VERSION = "kxbtcd_materialization_anchor_selection.v1"

HISTORICAL_STATE_VIEW = "historical_reconstructed"
MAX_EVENTS_PER_UTC_WEEK = 4
STRUCTURAL_QUANTILES = (
    Decimal("0.10"),
    Decimal("0.30"),
    Decimal("0.50"),
    Decimal("0.70"),
    Decimal("0.90"),
)
TIME_TO_CLOSE_ANCHORS_SECONDS = (
    55 * 60,
    50 * 60,
    45 * 60,
    40 * 60,
    35 * 60,
    30 * 60,
)
PERIOD_INTERVAL_MINUTES = 1
MAX_ANCHOR_STALENESS_SECONDS = 60

NORMALIZED_MARKET_FIELDS = (
    "event_ticker",
    "market_ticker",
    "strike_type",
    "strike_dollars",
    "source_lineage_refs",
)

NORMALIZED_QUOTE_FIELDS = (
    "end_period_ts",
    "valid_quote_observation",
    "yes_bid",
    "yes_ask",
    "midpoint",
    "spread",
    "raw_observation_id",
)

SELECTED_EVENT_FIELDS = (
    "schema_version",
    "materialization_fingerprint",
    "split_fingerprint",
    "event_ticker",
    "partition",
    "utc_week_start",
    "close_time_utc",
    "settlement_regime_id",
    "settlement_primitive_ids",
    "source_lineage_refs",
    "event_selection_hash",
)

SELECTED_MARKET_FIELDS = (
    "schema_version",
    "materialization_fingerprint",
    "event_ticker",
    "market_ticker",
    "structural_role",
    "structural_quantile",
    "strike_dollars",
    "strike_rank_zero_based",
    "event_market_count",
    "source_lineage_refs",
)

ANCHOR_SELECTION_FIELDS = (
    "schema_version",
    "materialization_fingerprint",
    "anchor_seconds",
    "target_utc",
    "selected_end_period_ts",
    "selected_as_of_utc",
    "staleness_seconds",
    "yes_bid",
    "yes_ask",
    "midpoint",
    "spread",
    "raw_observation_id",
)

FORBIDDEN_PREOUTCOME_FIELDS = frozenset(
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
        "gross_edge",
        "net_edge",
        "expected_pnl",
        "decision",
        "order_id",
    }
)


def _error(message: str) -> None:
    raise KxbtcdPreoutcomeMaterializationError(message)


def materialization_definition() -> dict[str, Any]:
    """Return the frozen, outcome-blind historical materialization definition."""

    return {
        "contract_version": MATERIALIZATION_CONTRACT_VERSION,
        "state_contract_fingerprint": state_contract_fingerprint(),
        "split_design_fingerprint": split_design_fingerprint(),
        "dataset_design_fingerprint": dataset_design_fingerprint(),
        "target_regime_id": TARGET_REGIME_ID,
        "universe_rule": (
            "use settled KXBTCD Event strike_date as the outcome-blind chronology only at or "
            "after the first Checkpoint-10 sample-proven modern-regime event; construct provisional "
            "target-regime settlement primitive ids from the frozen modern measurement signature "
            "and strike_date; apply the frozen chronological split and weekly event sampling; then "
            "fetch and semantically validate the complete strike ladder for every selected event, "
            "failing the entire materialization if selected-event regime, close time, or primitive "
            "disagrees with the provisional sampling frame"
        ),
        "regime_frame": {
            "policy_id": REGIME_FRAME_POLICY_ID,
            "conservative_modern_start_utc": CONSERVATIVE_MODERN_START_UTC,
            "boundary_interpretation": (
                "lower bound is the first sample-observed modern KXBTCD event from Checkpoint 10; "
                "it is not claimed to be the exact production rule-change timestamp"
            ),
            "event_chronology_source": "event.strike_date",
            "event_strike_date_validation_evidence": (
                "Checkpoint-12 offline audit: 9737 post-start Events had non-null unique strike_date; "
                "all 25 Checkpoint-10 sampled KXBTCD Events matched independently validated market "
                "close_time exactly with 0-second maximum absolute difference"
            ),
            "unsampled_event_semantics_claimed_proven": False,
            "selected_event_full_ladder_semantic_validation_required": True,
        },
        "event_sampling": {
            "unit": "eligible event after split and embargo",
            "max_events_per_utc_week": MAX_EVENTS_PER_UTC_WEEK,
            "rule": "sha256(event_ticker) ascending within each eligible UTC week",
            "outcome_or_quote_selection": False,
        },
        "market_sampling": {
            "normalized_input": "validated KXBTCD above-threshold markets only",
            "structural_quantiles": [str(value) for value in STRUCTURAL_QUANTILES],
            "rank_rule": "nearest ordinal rank with deterministic half-up rounding",
            "minimum_distinct_markets": len(STRUCTURAL_QUANTILES),
            "outcome_or_quote_selection": False,
        },
        "quote_sampling": {
            "period_interval_minutes": PERIOD_INTERVAL_MINUTES,
            "time_to_close_anchors_seconds": list(TIME_TO_CLOSE_ANCHORS_SECONDS),
            "selection_rule": (
                "latest valid real one-minute quote with end_period_ts <= target; "
                "target - end_period_ts <= 60 seconds"
            ),
            "future_candle_allowed": False,
            "forward_fill_beyond_seconds": MAX_ANCHOR_STALENESS_SECONDS,
        },
        "state_view": HISTORICAL_STATE_VIEW,
        "historical_live_causality_claim": False,
        "raw_first_required": True,
        "state_lineage_rule": "historical state carries both selected-market metadata raw refs and selected quote raw observation id",
        "outcomes_materialized": False,
        "model_fit_performed": False,
        "execution_authorized": False,
    }


def materialization_fingerprint() -> str:
    payload = json.dumps(
        materialization_definition(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_materialization_contract() -> None:
    if MATERIALIZATION_CONTRACT_VERSION != "kxbtcd_preoutcome_materialization.v3":
        _error("unexpected materialization contract version")
    modern_start = _parse_utc(CONSERVATIVE_MODERN_START_UTC, "CONSERVATIVE_MODERN_START_UTC")
    canonical_modern_start = modern_start.isoformat(timespec="seconds").replace("+00:00", "Z")
    if canonical_modern_start != CONSERVATIVE_MODERN_START_UTC:
        _error("conservative modern start must be canonical UTC")
    if materialization_definition()["regime_frame"]["unsampled_event_semantics_claimed_proven"] is not False:
        _error("unsampled event semantics must not be claimed proven")
    if materialization_definition()["regime_frame"]["selected_event_full_ladder_semantic_validation_required"] is not True:
        _error("selected-event full-ladder semantic validation must remain required")
    if MAX_EVENTS_PER_UTC_WEEK <= 0:
        _error("MAX_EVENTS_PER_UTC_WEEK must be positive")
    if len(STRUCTURAL_QUANTILES) != 5 or tuple(sorted(STRUCTURAL_QUANTILES)) != STRUCTURAL_QUANTILES:
        _error("structural quantiles must contain exactly five increasing positions")
    if any(not Decimal("0") < value < Decimal("1") for value in STRUCTURAL_QUANTILES):
        _error("structural quantiles must lie strictly inside (0, 1)")
    if any(value <= 0 for value in TIME_TO_CLOSE_ANCHORS_SECONDS):
        _error("time-to-close anchors must be positive")
    if tuple(sorted(TIME_TO_CLOSE_ANCHORS_SECONDS, reverse=True)) != TIME_TO_CLOSE_ANCHORS_SECONDS:
        _error("time-to-close anchors must be strictly descending")
    if PERIOD_INTERVAL_MINUTES != 1:
        _error("first materialization must use real one-minute source quotes")
    if MAX_ANCHOR_STALENESS_SECONDS != 60:
        _error("first materialization staleness cap changed")
    if materialization_definition()["outcomes_materialized"] is not False:
        _error("outcomes must remain closed")
    if materialization_definition()["model_fit_performed"] is not False:
        _error("model fitting must remain disabled")
    if materialization_definition()["execution_authorized"] is not False:
        _error("execution must remain unauthorized")
    for fields, name in (
        (NORMALIZED_MARKET_FIELDS, "normalized market"),
        (NORMALIZED_QUOTE_FIELDS, "normalized quote"),
        (SELECTED_EVENT_FIELDS, "selected event"),
        (SELECTED_MARKET_FIELDS, "selected market"),
        (ANCHOR_SELECTION_FIELDS, "anchor selection"),
    ):
        if len(fields) != len(set(fields)):
            _error(f"{name} fields contain duplicates")
        leaked = FORBIDDEN_PREOUTCOME_FIELDS.intersection(fields)
        if leaked:
            _error(f"{name} fields contain forbidden fields: {sorted(leaked)}")


def select_weekly_events(
    split_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Select at most four eligible events per UTC week after split/embargo."""

    validate_materialization_contract()
    if not split_rows:
        _error("split_rows must not be empty")

    eligible: list[dict[str, Any]] = []
    split_fingerprints: set[str] = set()
    partition_by_week: dict[str, str] = {}
    seen_events: set[str] = set()

    for index, original in enumerate(split_rows):
        row = _mapping(original, f"split_rows[{index}]")
        _reject_forbidden(row, f"split_rows[{index}]")
        _exact_keys(row, SPLIT_ROW_FIELDS, f"split_rows[{index}]")
        if row["schema_version"] != SPLIT_ROW_SCHEMA_VERSION:
            _error("split row schema_version mismatch")
        if row["design_fingerprint"] != split_design_fingerprint():
            _error("split row design fingerprint mismatch")
        event = _text(row["event_ticker"], "split event_ticker")
        if event in seen_events:
            _error(f"duplicate split event_ticker: {event}")
        seen_events.add(event)
        split_fingerprints.add(_text(row["split_fingerprint"], "split_fingerprint"))

        if not _bool(row["eligible_for_modeling"], "eligible_for_modeling"):
            continue
        partition = _text(row["partition"], "partition")
        if partition not in PARTITIONS:
            _error(f"eligible split row has invalid partition: {partition!r}")
        if row["settlement_regime_id"] != TARGET_REGIME_ID:
            _error("eligible split row settlement regime changed")
        week = _text(row["utc_week_start"], "utc_week_start")
        previous = partition_by_week.setdefault(week, partition)
        if previous != partition:
            _error(f"one UTC week crosses partitions: {week}")
        eligible.append(dict(row))

    if len(split_fingerprints) != 1:
        _error("split rows must carry exactly one split_fingerprint")
    if not eligible:
        _error("no eligible split events available for materialization")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        grouped.setdefault(row["utc_week_start"], []).append(row)

    selected: list[dict[str, Any]] = []
    split_fp = next(iter(split_fingerprints))
    for week in sorted(grouped):
        ranked = sorted(
            grouped[week],
            key=lambda row: (_sha256_text(row["event_ticker"]), row["event_ticker"]),
        )
        for row in ranked[:MAX_EVENTS_PER_UTC_WEEK]:
            output = {
                "schema_version": SELECTED_EVENT_SCHEMA_VERSION,
                "materialization_fingerprint": materialization_fingerprint(),
                "split_fingerprint": split_fp,
                "event_ticker": row["event_ticker"],
                "partition": row["partition"],
                "utc_week_start": row["utc_week_start"],
                "close_time_utc": row["close_time_utc"],
                "settlement_regime_id": row["settlement_regime_id"],
                "settlement_primitive_ids": list(row["settlement_primitive_ids"]),
                "source_lineage_refs": list(row["source_lineage_refs"]),
                "event_selection_hash": _sha256_text(row["event_ticker"]),
            }
            _exact_keys(output, SELECTED_EVENT_FIELDS, "selected event")
            selected.append(output)

    selected.sort(key=lambda row: (row["utc_week_start"], row["event_selection_hash"], row["event_ticker"]))
    return tuple(selected)


def select_structural_markets(
    market_rows: Sequence[Mapping[str, Any]],
    *,
    event_ticker: str,
) -> tuple[dict[str, Any], ...]:
    """Select five outcome/quote-blind structural strike positions for one event."""

    validate_materialization_contract()
    event_ticker = _text(event_ticker, "event_ticker")
    normalized: list[tuple[Decimal, str, dict[str, Any]]] = []
    seen_tickers: set[str] = set()
    seen_strikes: set[Decimal] = set()

    for index, original in enumerate(market_rows):
        row = _mapping(original, f"market_rows[{index}]")
        _reject_forbidden(row, f"market_rows[{index}]")
        _exact_keys(row, NORMALIZED_MARKET_FIELDS, f"market_rows[{index}]")
        if row["event_ticker"] != event_ticker:
            _error("normalized market input mixes event_tickers")
        ticker = _text(row["market_ticker"], "market_ticker")
        if ticker in seen_tickers:
            _error(f"duplicate market_ticker: {ticker}")
        seen_tickers.add(ticker)
        if row["strike_type"] != "greater":
            _error("KXBTCD modern-regime materialization requires strike_type='greater'")
        strike = _decimal(row["strike_dollars"], "strike_dollars")
        if strike <= 0:
            _error("strike_dollars must be positive")
        if strike in seen_strikes:
            _error(f"duplicate strike_dollars within event: {strike}")
        seen_strikes.add(strike)
        refs = _string_list(row["source_lineage_refs"], "source_lineage_refs")
        normalized.append((strike, ticker, {**row, "source_lineage_refs": refs}))

    if len(normalized) < len(STRUCTURAL_QUANTILES):
        _error(
            f"event {event_ticker} needs at least {len(STRUCTURAL_QUANTILES)} distinct markets"
        )
    normalized.sort(key=lambda item: (item[0], item[1]))

    indexes = [_nearest_rank_index(len(normalized), quantile) for quantile in STRUCTURAL_QUANTILES]
    if len(set(indexes)) != len(indexes):
        _error("structural quantile positions collapsed to duplicate market ranks")

    selected: list[dict[str, Any]] = []
    for quantile, index in zip(STRUCTURAL_QUANTILES, indexes):
        strike, ticker, row = normalized[index]
        role = f"q{int(quantile * 100):02d}"
        output = {
            "schema_version": SELECTED_MARKET_SCHEMA_VERSION,
            "materialization_fingerprint": materialization_fingerprint(),
            "event_ticker": event_ticker,
            "market_ticker": ticker,
            "structural_role": role,
            "structural_quantile": str(quantile),
            "strike_dollars": _decimal_text(strike),
            "strike_rank_zero_based": index,
            "event_market_count": len(normalized),
            "source_lineage_refs": list(row["source_lineage_refs"]),
        }
        _exact_keys(output, SELECTED_MARKET_FIELDS, "selected market")
        selected.append(output)
    return tuple(selected)


def select_anchor_observation(
    quote_rows: Sequence[Mapping[str, Any]],
    *,
    close_time_utc: str,
    anchor_seconds: int,
) -> dict[str, Any] | None:
    """Select a real quote at/before a TTC target with at most 60s staleness."""

    validate_materialization_contract()
    if anchor_seconds not in TIME_TO_CLOSE_ANCHORS_SECONDS:
        _error(f"anchor_seconds is not in frozen anchor set: {anchor_seconds}")
    close_dt = _parse_utc(close_time_utc, "close_time_utc")
    target_ts = int(close_dt.timestamp()) - anchor_seconds
    seen_ts: set[int] = set()
    candidates: list[tuple[int, dict[str, Any]]] = []

    for index, original in enumerate(quote_rows):
        row = _mapping(original, f"quote_rows[{index}]")
        _reject_forbidden(row, f"quote_rows[{index}]")
        _exact_keys(row, NORMALIZED_QUOTE_FIELDS, f"quote_rows[{index}]")
        end_ts = _integer(row["end_period_ts"], "end_period_ts")
        if end_ts in seen_ts:
            _error(f"duplicate quote end_period_ts: {end_ts}")
        seen_ts.add(end_ts)
        valid = _bool(row["valid_quote_observation"], "valid_quote_observation")
        if not valid:
            continue
        _validate_quote_values(row)
        if end_ts > target_ts:
            continue
        staleness = target_ts - end_ts
        if staleness > MAX_ANCHOR_STALENESS_SECONDS:
            continue
        candidates.append((end_ts, dict(row)))

    if not candidates:
        return None
    end_ts, row = max(candidates, key=lambda item: item[0])
    staleness = target_ts - end_ts
    output = {
        "schema_version": ANCHOR_SELECTION_SCHEMA_VERSION,
        "materialization_fingerprint": materialization_fingerprint(),
        "anchor_seconds": anchor_seconds,
        "target_utc": _format_epoch(target_ts),
        "selected_end_period_ts": end_ts,
        "selected_as_of_utc": _format_epoch(end_ts),
        "staleness_seconds": staleness,
        "yes_bid": _decimal_text(_decimal(row["yes_bid"], "yes_bid")),
        "yes_ask": _decimal_text(_decimal(row["yes_ask"], "yes_ask")),
        "midpoint": _decimal_text(_decimal(row["midpoint"], "midpoint")),
        "spread": _decimal_text(_decimal(row["spread"], "spread")),
        "raw_observation_id": _text(row["raw_observation_id"], "raw_observation_id"),
    }
    _exact_keys(output, ANCHOR_SELECTION_FIELDS, "anchor selection")
    return output


def build_historical_reconstructed_state(
    *,
    selected_market: Mapping[str, Any],
    selected_anchor: Mapping[str, Any],
    close_time_utc: str,
    raw_receive_monotonic_ns: int,
    alignment_epoch_id: str,
    source_id: str = "kalshi.kxbtcd.candlestick",
) -> dict[str, Any]:
    """Build one offline historical KXBTCD state from a selected real quote."""

    market = _mapping(selected_market, "selected_market")
    anchor = _mapping(selected_anchor, "selected_anchor")
    _exact_keys(market, SELECTED_MARKET_FIELDS, "selected_market")
    _exact_keys(anchor, ANCHOR_SELECTION_FIELDS, "selected_anchor")
    if market["schema_version"] != SELECTED_MARKET_SCHEMA_VERSION:
        _error("selected market schema_version mismatch")
    if anchor["schema_version"] != ANCHOR_SELECTION_SCHEMA_VERSION:
        _error("selected anchor schema_version mismatch")
    if market["materialization_fingerprint"] != materialization_fingerprint():
        _error("selected market materialization fingerprint mismatch")
    if anchor["materialization_fingerprint"] != materialization_fingerprint():
        _error("selected anchor materialization fingerprint mismatch")
    if not isinstance(raw_receive_monotonic_ns, int) or isinstance(raw_receive_monotonic_ns, bool) or raw_receive_monotonic_ns < 0:
        _error("raw_receive_monotonic_ns must be a nonnegative integer")
    alignment_epoch_id = _text(alignment_epoch_id, "alignment_epoch_id")
    source_id = _text(source_id, "source_id")

    close_dt = _parse_utc(close_time_utc, "close_time_utc")
    as_of_dt = _parse_utc(anchor["selected_as_of_utc"], "selected_as_of_utc")
    ttc = int((close_dt - as_of_dt).total_seconds())
    if ttc < 0:
        _error("selected historical quote occurs after event close")
    raw_id = _text(anchor["raw_observation_id"], "raw_observation_id")
    market_lineage = _string_list(market["source_lineage_refs"], "selected_market.source_lineage_refs")
    state_lineage = list(dict.fromkeys([*market_lineage, raw_id]))
    state_id = "state:kxbtcd:historical:" + _sha256_text(
        "|".join(
            [
                market["event_ticker"],
                market["market_ticker"],
                str(anchor["selected_end_period_ts"]),
                raw_id,
            ]
        )
    )[:24]

    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "state_id": state_id,
        "product_head": "KXBTCD",
        "state_view": HISTORICAL_STATE_VIEW,
        "as_of_utc": anchor["selected_as_of_utc"],
        "as_of_local_monotonic_ns": raw_receive_monotonic_ns,
        "alignment_epoch_id": alignment_epoch_id,
        "state_quality": "usable",
        "clock_health_status": "not_required",
        "raw_observation_refs": state_lineage,
        "btc_features": [],
        "source_age_seconds_by_source": {source_id: "0"},
        "product_context": {
            "event_ticker": market["event_ticker"],
            "market_ticker": market["market_ticker"],
            "settlement_regime_id": TARGET_REGIME_ID,
            "strike_dollars": market["strike_dollars"],
            "time_to_close_seconds": str(ttc),
            "yes_bid": anchor["yes_bid"],
            "yes_ask": anchor["yes_ask"],
            "midpoint": anchor["midpoint"],
            "spread": anchor["spread"],
        },
    }
    validate_synchronized_state(state)
    return state


def _nearest_rank_index(count: int, quantile: Decimal) -> int:
    position = Decimal(count - 1) * quantile
    return int((position + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR))


def _validate_quote_values(row: Mapping[str, Any]) -> None:
    bid = _decimal(row["yes_bid"], "yes_bid")
    ask = _decimal(row["yes_ask"], "yes_ask")
    midpoint = _decimal(row["midpoint"], "midpoint")
    spread = _decimal(row["spread"], "spread")
    for value, name in ((bid, "yes_bid"), (ask, "yes_ask"), (midpoint, "midpoint")):
        if value < 0 or value > 1:
            _error(f"{name} must be in [0, 1]")
    if bid > ask:
        _error("yes_bid must not exceed yes_ask")
    tolerance = Decimal("0.000000001")
    if abs(midpoint - (bid + ask) / Decimal("2")) > tolerance:
        _error("midpoint must equal bid/ask midpoint")
    if spread < 0 or abs(spread - (ask - bid)) > tolerance:
        _error("spread must equal yes_ask - yes_bid")
    _text(row["raw_observation_id"], "raw_observation_id")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _error(f"{name} must be a mapping")
    return value


def _exact_keys(row: Mapping[str, Any], fields: Sequence[str], name: str) -> None:
    expected = set(fields)
    observed = set(row)
    if expected != observed:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        _error(f"{name} keys mismatch; missing={missing}, extra={extra}")


def _reject_forbidden(row: Mapping[str, Any], name: str) -> None:
    leaked = FORBIDDEN_PREOUTCOME_FIELDS.intersection(row)
    if leaked:
        _error(f"{name} contains forbidden pre-outcome fields: {sorted(leaked)}")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        _error(f"{name} must be a non-empty list of strings")
    output = [_text(item, f"{name} item") for item in value]
    if len(output) != len(set(output)):
        _error(f"{name} contains duplicates")
    return output


def _bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value == "true":
            return True
        if value == "false":
            return False
    _error(f"{name} must be bool or 'true'/'false'")


def _integer(value: Any, name: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            _error(f"{name} must be an integer")
        return parsed
    _error(f"{name} must be an integer")


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        _error(f"{name} must be numeric")
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _parse_utc(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _error(f"{name} must be ISO-8601 UTC")
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _error(f"{name} must be UTC")
    return parsed.astimezone(timezone.utc)


def _format_epoch(epoch_seconds: int) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


validate_materialization_contract()
