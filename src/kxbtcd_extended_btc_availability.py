
"""Checkpoint-19C extended outcome-blind independent-BTC availability audit."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from typing import Any, Mapping, Sequence

from src.kxbtcd_independent_btc_feasibility import (
    MaterializedBatch,
    ReferenceObservation,
    materialize_kxbtcd_snapshot,
    parse_coinbase_book as _parse_coinbase_book_19b,
    parse_kraken_pretrade as _parse_kraken_pretrade_19b,
    summarize_rows as _summarize_rows_19b,
)
from src.kxbtcd_successor_research_protocol import (
    validate_feasibility_row,
    validate_protocol,
)


class KxbtcdExtendedBtcAvailabilityError(ValueError):
    """Raised when Checkpoint-19C frozen audit invariants are violated."""


AUDIT_SCHEMA_VERSION = "kxbtcd_extended_btc_availability_audit.v1"
EXCLUSION_SCHEMA_VERSION = "kxbtcd_extended_btc_availability_exclusion.v1"
EXTERNAL_CYCLE_SCHEMA_VERSION = "kxbtcd_extended_btc_external_cycle.v1"
SNAPSHOT_SCHEMA_VERSION = "kxbtcd_extended_btc_snapshot_summary.v1"
HOURLY_SCHEMA_VERSION = "kxbtcd_extended_btc_hourly_coverage.v1"
CHECKPOINT_ID = "19C"

PARENT_19B_AUDIT_DESIGN_FINGERPRINT = "41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be"
PARENT_19B_PILOT_RUN_ID = "collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960"

COINBASE_SOURCE_ID = "coinbase.exchange.public_rest.product_book.btc_usd.provisional_19c"
KRAKEN_SOURCE_ID = "kraken.spot.public_rest.pretrade.btc_usd.provisional_19c"

DURATION_SECONDS = 86400
EXTERNAL_INTERVAL_SECONDS = 15.0
KALSHI_INTERVAL_SECONDS = 300.0
FIVE_MINUTE_LOOKBACK_SECONDS = 300

EXTERNAL_CYCLE_FIELDS = (
    "schema_version",
    "audit_design_fingerprint",
    "cycle_index",
    "cycle_completed_utc",
    "coinbase_available",
    "coinbase_source_event_time_utc",
    "coinbase_price",
    "coinbase_raw_observation_ref",
    "coinbase_local_receive_utc",
    "kraken_available",
    "kraken_source_event_time_utc",
    "kraken_price",
    "kraken_raw_observation_ref",
    "kraken_local_receive_utc",
    "cross_source_price_disagreement_bps",
    "external_receive_skew_ms",
)

SNAPSHOT_FIELDS = (
    "schema_version",
    "audit_design_fingerprint",
    "snapshot_index",
    "as_of_utc",
    "kalshi_raw_observation_ref",
    "feasibility_row_count",
    "exclusion_row_count",
    "unique_event_count",
    "unique_market_count",
    "coinbase_available",
    "coinbase_age_seconds",
    "kraken_available",
    "kraken_age_seconds",
    "cross_source_price_disagreement_bps",
    "five_minute_lookback_available_coinbase",
    "coinbase_five_minute_lookback_gap_seconds",
    "five_minute_lookback_available_kraken",
    "kraken_five_minute_lookback_gap_seconds",
    "ttc_0_to_30m_count",
    "ttc_30_to_60m_count",
    "ttc_1_to_4h_count",
    "ttc_4_to_24h_count",
    "ttc_gt_24h_count",
)

EXCLUSION_FIELDS = (
    "schema_version",
    "audit_design_fingerprint",
    "kalshi_raw_observation_ref",
    "event_ticker",
    "market_ticker",
    "as_of_utc",
    "reason",
)

HOURLY_FIELDS = (
    "schema_version",
    "audit_design_fingerprint",
    "utc_hour_start",
    "external_cycle_count",
    "coinbase_success_count",
    "kraken_success_count",
    "both_source_success_count",
    "kalshi_snapshot_count",
    "feasibility_row_count",
    "exclusion_row_count",
)

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


def _error(message: str) -> None:
    raise KxbtcdExtendedBtcAvailabilityError(message)


def audit_design_definition() -> dict[str, Any]:
    return {'schema_version': 'kxbtcd_extended_btc_availability_audit.v1', 'checkpoint_id': '19C', 'protocol_fingerprint': 'b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8', 'parent_19b_audit_design_fingerprint': '41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be', 'parent_19b_pilot_run_id': 'collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960', 'purpose': 'extended_outcome_blind_independent_btc_availability_and_ttc_coverage', 'candidate_e_formula_frozen': False, 'candidate_e_fitting_authorized': False, 'outcome_access_authorized': False, 'execution_authorized': False, 'subsecond_lead_lag_authorized': False, 'sources': {'coinbase': {'source_id': 'coinbase.exchange.public_rest.product_book.btc_usd.provisional_19c', 'status': 'provisional_extended_audit_source_not_E1_frozen', 'endpoint_inherited_from_19b': True, 'instrument_id': 'BTC-USD', 'diagnostic_price': 'best_bid_ask_midpoint'}, 'kraken': {'source_id': 'kraken.spot.public_rest.pretrade.btc_usd.provisional_19c', 'status': 'provisional_extended_audit_source_not_E1_frozen', 'endpoint_inherited_from_19b': True, 'instrument_id': 'BTC/USD', 'diagnostic_price': 'best_bid_ask_midpoint'}, 'kalshi': {'series_ticker': 'KXBTCD', 'open_market_snapshot_inherited_from_19b': True}}, 'collection': {'duration_seconds': 86400, 'external_interval_seconds': 15.0, 'kalshi_interval_seconds': 300.0, 'five_minute_lookback_seconds': 300, 'request_order': 'alternate_coinbase_kraken_order_each_external_cycle; request_KXBTCD_only_after_current_external_attempts', 'missed_cycle_policy': 'do_not_burst_replay; resume_from_current_monotonic_time', 'source_transport_failure_policy': 'record_as_availability_failure_and_continue_when_raw_archive_succeeded', 'schema_or_parse_failure_policy': 'fail_closed', 'raw_persistence_ambiguity_policy': 'fail_closed', 'command_line_cadence_or_duration_override': False}, 'outputs': {'feasibility_rows': True, 'structural_exclusions': True, 'external_cycles': True, 'kxbtcd_snapshot_summary': True, 'hourly_coverage': True, 'summary': True, 'raw_archives': True, 'run_manifest': True, 'runtime_events': True}, 'descriptive_only': {'source_availability': True, 'source_age': True, 'cross_source_disagreement': True, 'receive_skew': True, 'five_minute_lookback_availability': True, 'five_minute_lookback_gap': True, 'utc_hour_coverage': True, 'kxbtcd_ttc_coverage': True}, 'not_frozen_by_19c': ['E1_source_id_selection', 'source_staleness_threshold', 'cross_source_disagreement_threshold', 'consensus_price_formula', 'Candidate_E_formula', 'Candidate_E_feature_set', 'five_minute_return_alignment_tolerance', 'E1_E2_E3_event_counts', 'E1_E2_E3_calendar_coverage', 'advancement_gate']}


def audit_design_fingerprint() -> str:
    payload = json.dumps(
        audit_design_definition(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


FROZEN_AUDIT_DESIGN_FINGERPRINT = "4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d"


def validate_audit_design() -> None:
    validate_protocol()
    design = audit_design_definition()
    for field in (
        "candidate_e_formula_frozen",
        "candidate_e_fitting_authorized",
        "outcome_access_authorized",
        "execution_authorized",
        "subsecond_lead_lag_authorized",
    ):
        if design[field] is not False:
            _error(f"Checkpoint 19C safety invariant changed: {field}")
    if design["collection"]["duration_seconds"] != DURATION_SECONDS:
        _error("19C duration drift")
    if design["collection"]["external_interval_seconds"] != EXTERNAL_INTERVAL_SECONDS:
        _error("19C external cadence drift")
    if design["collection"]["kalshi_interval_seconds"] != KALSHI_INTERVAL_SECONDS:
        _error("19C Kalshi cadence drift")
    if audit_design_fingerprint() != FROZEN_AUDIT_DESIGN_FINGERPRINT:
        _error("Checkpoint-19C audit design fingerprint changed")


def parse_coinbase_book(response: Any) -> ReferenceObservation:
    return replace(_parse_coinbase_book_19b(response), source_id=COINBASE_SOURCE_ID)


def parse_kraken_pretrade(response: Any) -> ReferenceObservation:
    return replace(_parse_kraken_pretrade_19b(response), source_id=KRAKEN_SOURCE_ID)


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def disagreement_bps(a: Decimal, b: Decimal) -> str:
    denominator = (a + b) / Decimal("2")
    if denominator <= 0:
        _error("cross-source midpoint denominator must be positive")
    return _decimal_text(abs(a - b) / denominator * Decimal("10000"))


def external_cycle_row(
    *,
    cycle_index: int,
    cycle_completed_utc: str,
    coinbase: ReferenceObservation | None,
    kraken: ReferenceObservation | None,
) -> dict[str, Any]:
    if cycle_index < 0:
        _error("cycle_index must be nonnegative")
    disagreement = None
    skew_ms = None
    if coinbase is not None and kraken is not None:
        disagreement = disagreement_bps(coinbase.price, kraken.price)
        skew_ms = (
            abs(
                coinbase.local_receive_monotonic_ns
                - kraken.local_receive_monotonic_ns
            )
            / 1_000_000
        )
    row = {
        "schema_version": EXTERNAL_CYCLE_SCHEMA_VERSION,
        "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
        "cycle_index": cycle_index,
        "cycle_completed_utc": cycle_completed_utc,
        "coinbase_available": coinbase is not None,
        "coinbase_source_event_time_utc": (
            coinbase.source_event_time_utc if coinbase else None
        ),
        "coinbase_price": _decimal_text(coinbase.price) if coinbase else None,
        "coinbase_raw_observation_ref": (
            coinbase.raw_observation_ref if coinbase else None
        ),
        "coinbase_local_receive_utc": coinbase.local_receive_utc if coinbase else None,
        "kraken_available": kraken is not None,
        "kraken_source_event_time_utc": (
            kraken.source_event_time_utc if kraken else None
        ),
        "kraken_price": _decimal_text(kraken.price) if kraken else None,
        "kraken_raw_observation_ref": kraken.raw_observation_ref if kraken else None,
        "kraken_local_receive_utc": kraken.local_receive_utc if kraken else None,
        "cross_source_price_disagreement_bps": disagreement,
        "external_receive_skew_ms": skew_ms,
    }
    if set(row) != set(EXTERNAL_CYCLE_FIELDS):
        _error("external cycle row schema drift")
    if FORBIDDEN_KEYS.intersection(row):
        _error("external cycle row leaked forbidden fields")
    return row


def five_minute_lookback_gap_seconds(
    history: Sequence[ReferenceObservation], *, as_of_monotonic_ns: int
) -> float | None:
    target = (
        as_of_monotonic_ns
        - FIVE_MINUTE_LOOKBACK_SECONDS * 1_000_000_000
    )
    eligible = [
        item.local_receive_monotonic_ns
        for item in history
        if item.local_receive_monotonic_ns <= target
    ]
    if not eligible:
        return None
    return (target - max(eligible)) / 1_000_000_000


def materialize_extended_snapshot(
    kalshi_response: Any,
    *,
    coinbase_observation: ReferenceObservation | None,
    kraken_observation: ReferenceObservation | None,
    coinbase_history: Sequence[ReferenceObservation],
    kraken_history: Sequence[ReferenceObservation],
) -> MaterializedBatch:
    validate_audit_design()
    batch = materialize_kxbtcd_snapshot(
        kalshi_response,
        coinbase_observation=coinbase_observation,
        kraken_observation=kraken_observation,
        coinbase_history=coinbase_history,
        kraken_history=kraken_history,
    )
    rows: list[dict[str, Any]] = []
    for original in batch.rows:
        row = dict(original)
        row["state_id"] = "kxbtcd19c:" + str(row["state_id"]).split(":", 1)[-1]
        validate_feasibility_row(row)
        rows.append(row)
    exclusions: list[dict[str, Any]] = []
    for original in batch.exclusions:
        row = {
            "schema_version": EXCLUSION_SCHEMA_VERSION,
            "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
            "kalshi_raw_observation_ref": original["kalshi_raw_observation_ref"],
            "event_ticker": original["event_ticker"],
            "market_ticker": original["market_ticker"],
            "as_of_utc": original["as_of_utc"],
            "reason": original["reason"],
        }
        if set(row) != set(EXCLUSION_FIELDS):
            _error("extended exclusion row schema drift")
        exclusions.append(row)
    return MaterializedBatch(rows=tuple(rows), exclusions=tuple(exclusions))


def snapshot_summary(
    *,
    snapshot_index: int,
    batch: MaterializedBatch,
    coinbase_history: Sequence[ReferenceObservation],
    kraken_history: Sequence[ReferenceObservation],
    as_of_monotonic_ns: int,
) -> dict[str, Any]:
    if not batch.rows:
        _error("successful KXBTCD snapshot produced zero protocol-valid rows")
    first = batch.rows[0]
    for row in batch.rows:
        validate_feasibility_row(row)
        for field in (
            "as_of_utc",
            "coinbase_observation_available",
            "coinbase_age_seconds",
            "kraken_observation_available",
            "kraken_age_seconds",
            "cross_source_price_disagreement_bps",
            "five_minute_lookback_available_coinbase",
            "five_minute_lookback_available_kraken",
        ):
            if row[field] != first[field]:
                _error(
                    f"snapshot-constant field changed within one ladder: {field}"
                )
    raw_refs = first["kalshi_raw_observation_refs"]
    if not isinstance(raw_refs, list) or len(raw_refs) != 1:
        _error("snapshot must carry exactly one Kalshi raw observation reference")
    ttcs = [float(row["time_to_close_seconds"]) for row in batch.rows]
    row = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
        "snapshot_index": snapshot_index,
        "as_of_utc": first["as_of_utc"],
        "kalshi_raw_observation_ref": raw_refs[0],
        "feasibility_row_count": len(batch.rows),
        "exclusion_row_count": len(batch.exclusions),
        "unique_event_count": len({str(x["event_ticker"]) for x in batch.rows}),
        "unique_market_count": len({str(x["market_ticker"]) for x in batch.rows}),
        "coinbase_available": bool(first["coinbase_observation_available"]),
        "coinbase_age_seconds": first["coinbase_age_seconds"],
        "kraken_available": bool(first["kraken_observation_available"]),
        "kraken_age_seconds": first["kraken_age_seconds"],
        "cross_source_price_disagreement_bps": first[
            "cross_source_price_disagreement_bps"
        ],
        "five_minute_lookback_available_coinbase": bool(
            first["five_minute_lookback_available_coinbase"]
        ),
        "coinbase_five_minute_lookback_gap_seconds": (
            five_minute_lookback_gap_seconds(
                coinbase_history, as_of_monotonic_ns=as_of_monotonic_ns
            )
        ),
        "five_minute_lookback_available_kraken": bool(
            first["five_minute_lookback_available_kraken"]
        ),
        "kraken_five_minute_lookback_gap_seconds": (
            five_minute_lookback_gap_seconds(
                kraken_history, as_of_monotonic_ns=as_of_monotonic_ns
            )
        ),
        "ttc_0_to_30m_count": sum(0 < x <= 1800 for x in ttcs),
        "ttc_30_to_60m_count": sum(1800 < x <= 3600 for x in ttcs),
        "ttc_1_to_4h_count": sum(3600 < x <= 14400 for x in ttcs),
        "ttc_4_to_24h_count": sum(14400 < x <= 86400 for x in ttcs),
        "ttc_gt_24h_count": sum(x > 86400 for x in ttcs),
    }
    if set(row) != set(SNAPSHOT_FIELDS):
        _error("snapshot summary schema drift")
    if FORBIDDEN_KEYS.intersection(row):
        _error("snapshot summary leaked forbidden fields")
    return row


def _percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[low]
    weight = pos - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _utc_hour(text: str) -> str:
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    return (
        parsed.replace(minute=0, second=0, microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_hourly_coverage(
    external_cycles: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    buckets: dict[str, dict[str, int]] = {}

    def bucket(hour: str) -> dict[str, int]:
        return buckets.setdefault(
            hour,
            {
                "external_cycle_count": 0,
                "coinbase_success_count": 0,
                "kraken_success_count": 0,
                "both_source_success_count": 0,
                "kalshi_snapshot_count": 0,
                "feasibility_row_count": 0,
                "exclusion_row_count": 0,
            },
        )

    for row in external_cycles:
        b = bucket(_utc_hour(str(row["cycle_completed_utc"])))
        b["external_cycle_count"] += 1
        cb = bool(row["coinbase_available"])
        kr = bool(row["kraken_available"])
        b["coinbase_success_count"] += int(cb)
        b["kraken_success_count"] += int(kr)
        b["both_source_success_count"] += int(cb and kr)

    for row in snapshots:
        b = bucket(_utc_hour(str(row["as_of_utc"])))
        b["kalshi_snapshot_count"] += 1
        b["feasibility_row_count"] += int(row["feasibility_row_count"])
        b["exclusion_row_count"] += int(row["exclusion_row_count"])

    output: list[dict[str, Any]] = []
    for hour in sorted(buckets):
        row = {
            "schema_version": HOURLY_SCHEMA_VERSION,
            "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
            "utc_hour_start": hour,
            **buckets[hour],
        }
        if set(row) != set(HOURLY_FIELDS):
            _error("hourly coverage schema drift")
        output.append(row)
    return tuple(output)


def summarize_extended(
    rows: Sequence[Mapping[str, Any]],
    exclusions: Sequence[Mapping[str, Any]],
    *,
    external_cycles: Sequence[Mapping[str, Any]],
    snapshots: Sequence[Mapping[str, Any]],
    coinbase_attempt_count: int,
    coinbase_success_count: int,
    kraken_attempt_count: int,
    kraken_success_count: int,
    kalshi_attempt_count: int,
    kalshi_success_count: int,
    longest_coinbase_failure_streak: int,
    longest_kraken_failure_streak: int,
    longest_kalshi_failure_streak: int,
) -> dict[str, Any]:
    base = _summarize_rows_19b(
        rows,
        exclusions,
        external_cycle_count=len(external_cycles),
        kalshi_snapshot_count=len(snapshots),
        coinbase_attempt_count=coinbase_attempt_count,
        coinbase_success_count=coinbase_success_count,
        kraken_attempt_count=kraken_attempt_count,
        kraken_success_count=kraken_success_count,
        receive_skew_ms=[
            float(x["external_receive_skew_ms"])
            for x in external_cycles
            if x["external_receive_skew_ms"] is not None
        ],
    )

    disagreement_values = [
        float(x["cross_source_price_disagreement_bps"])
        for x in external_cycles
        if x["cross_source_price_disagreement_bps"] is not None
    ]
    cb_gaps = [
        float(x["coinbase_five_minute_lookback_gap_seconds"])
        for x in snapshots
        if x["coinbase_five_minute_lookback_gap_seconds"] is not None
    ]
    kr_gaps = [
        float(x["kraken_five_minute_lookback_gap_seconds"])
        for x in snapshots
        if x["kraken_five_minute_lookback_gap_seconds"] is not None
    ]

    base.update(
        {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "checkpoint_id": CHECKPOINT_ID,
            "audit_design_fingerprint": FROZEN_AUDIT_DESIGN_FINGERPRINT,
            "parent_19b_audit_design_fingerprint": (
                PARENT_19B_AUDIT_DESIGN_FINGERPRINT
            ),
            "parent_19b_pilot_run_id": PARENT_19B_PILOT_RUN_ID,
            "interpretation": (
                "extended_outcome_blind_availability_only_not_model_evidence"
            ),
            "kalshi_request_success_rate": (
                kalshi_success_count / kalshi_attempt_count
                if kalshi_attempt_count
                else None
            ),
            "external_cycle_both_source_availability_rate": (
                sum(
                    bool(x["coinbase_available"])
                    and bool(x["kraken_available"])
                    for x in external_cycles
                )
                / len(external_cycles)
                if external_cycles
                else None
            ),
            "external_cycle_cross_source_disagreement_bps": {
                "p50": _percentile(disagreement_values, 0.50),
                "p95": _percentile(disagreement_values, 0.95),
                "max": max(disagreement_values) if disagreement_values else None,
            },
            "coinbase_five_minute_lookback_gap_seconds": {
                "p50": _percentile(cb_gaps, 0.50),
                "p95": _percentile(cb_gaps, 0.95),
                "max": max(cb_gaps) if cb_gaps else None,
            },
            "kraken_five_minute_lookback_gap_seconds": {
                "p50": _percentile(kr_gaps, 0.50),
                "p95": _percentile(kr_gaps, 0.95),
                "max": max(kr_gaps) if kr_gaps else None,
            },
            "utc_hour_bucket_count": len(
                build_hourly_coverage(external_cycles, snapshots)
            ),
            "utc_date_count": len(
                {str(x["cycle_completed_utc"])[:10] for x in external_cycles}
            ),
            "longest_consecutive_failure_streaks": {
                "coinbase": longest_coinbase_failure_streak,
                "kraken": longest_kraken_failure_streak,
                "kalshi": longest_kalshi_failure_streak,
            },
            "source_quality_thresholds_frozen": False,
            "consensus_price_formula_frozen": False,
            "candidate_e_formula_frozen": False,
            "candidate_e_fitting_performed": False,
            "evidence_cohort_sizes_frozen": False,
            "outcomes_accessed": False,
            "checkpoint17_terminal_used": False,
            "execution_performed": False,
            "orders_placed": 0,
            "thresholds_selected_from_outcomes": False,
        }
    )
    return base


def public_error_is_raw_persistence_failure(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "raw persistence" in text
        or ("raw-archived" in text and "could not" in text)
    )
