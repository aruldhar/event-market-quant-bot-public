"""Outcome-blind chronological split contract for the next KXBTCD baseline.

This module freezes dataset partition semantics before any new KXBTCD labels are
opened or any learned model is fit. It is deterministic, network-free, and
execution-free.

The new experiment is intentionally isolated from Checkpoint 10: all twenty
Checkpoint-10 source events are quarantined, and any event sharing one of their
settlement primitive identifiers is quarantined as well.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from typing import Any, Mapping, Sequence


class KxbtcdChronologicalSplitError(ValueError):
    """Raised when the frozen chronological split contract is violated."""


CONTRACT_SCHEMA_VERSION = "kxbtcd_chronological_split_contract.v1"
SPLIT_ROW_SCHEMA_VERSION = "kxbtcd_chronological_split_row.v1"
EXPERIMENT_FAMILY_ID = "kxbtcd_market_context_probability_baseline.v1"
TARGET_FAMILY = "KXBTCD"
TARGET_REGIME_ID = "brti_60s_simple_mean_untrimmed"

CHECKPOINT10_EXPERIMENT_ID = "kxbtcd_three_probe_monotone_baseline.v1"
CHECKPOINT10_DESIGN_FINGERPRINT = (
    "bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4"
)
CHECKPOINT10_SOURCE_EVENT_COUNT = 20

TRAIN_WEEK_FRACTION = Decimal("0.60")
VALIDATION_WEEK_FRACTION = Decimal("0.20")
LOCKED_TEST_WEEK_FRACTION = Decimal("0.20")
MIN_UNIQUE_WEEK_BLOCKS = 5
EMBARGO_HOURS = 24

PARTITIONS = ("train", "validation", "locked_test")

EVENT_UNIT_FIELDS = (
    "event_ticker",
    "close_time_utc",
    "settlement_regime_id",
    "settlement_primitive_ids",
    "source_lineage_refs",
)

SPLIT_ROW_FIELDS = (
    "schema_version",
    "experiment_family_id",
    "design_fingerprint",
    "split_fingerprint",
    "event_ticker",
    "close_time_utc",
    "utc_week_start",
    "settlement_regime_id",
    "settlement_primitive_ids",
    "source_lineage_refs",
    "partition",
    "embargoed",
    "eligible_for_modeling",
    "exclusion_reason",
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
        "model_output",
        "gross_edge",
        "net_edge",
        "expected_pnl",
        "decision",
        "order_id",
    }
)


def _error(message: str) -> None:
    raise KxbtcdChronologicalSplitError(message)


def frozen_split_contract() -> dict[str, Any]:
    """Return the canonical outcome-blind partition definition."""

    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "experiment_family_id": EXPERIMENT_FAMILY_ID,
        "target_family": TARGET_FAMILY,
        "target_regime_id": TARGET_REGIME_ID,
        "checkpoint10_quarantine": {
            "experiment_id": CHECKPOINT10_EXPERIMENT_ID,
            "design_fingerprint": CHECKPOINT10_DESIGN_FINGERPRINT,
            "required_source_event_count": CHECKPOINT10_SOURCE_EVENT_COUNT,
            "rule": (
                "exclude every Checkpoint-10 source event before partitioning; "
                "also exclude any candidate event whose settlement primitive "
                "intersects a Checkpoint-10 settlement primitive"
            ),
        },
        "partition_unit": "event_ticker_and_settlement_primitive",
        "ordering": "close_time_utc_ascending",
        "block_unit": "UTC ISO week starting Monday 00:00:00Z",
        "week_fractions": {
            "train": str(TRAIN_WEEK_FRACTION),
            "validation": str(VALIDATION_WEEK_FRACTION),
            "locked_test": str(LOCKED_TEST_WEEK_FRACTION),
        },
        "week_count_rule": (
            "train=floor(0.60*n_weeks); validation=floor(0.20*n_weeks); "
            "locked_test=remainder; require every partition nonempty"
        ),
        "minimum_unique_week_blocks": MIN_UNIQUE_WEEK_BLOCKS,
        "embargo_rule": (
            "after assigning whole UTC weeks, exclude events closing in the "
            "first 24 hours beginning at the train->validation boundary and "
            "the validation->locked_test boundary"
        ),
        "embargo_hours": EMBARGO_HOURS,
        "primitive_leakage_rule": (
            "a settlement primitive may not appear in more than one non-quarantined partition"
        ),
        "locked_test_rule": (
            "locked_test labels are opened once only after feature contract, split, "
            "candidate model, hyperparameter search space, metrics, and validation "
            "selection rule are frozen"
        ),
        "outcome_blind_rule": (
            "event units and split outputs must not contain settlement outcomes, labels, "
            "model outputs, economics, or decisions"
        ),
        "weighting_rule_for_later_scoring": (
            "compute loss within each event first, then equal-weight events; do not "
            "treat repeated strike/time rows from one event as independent samples"
        ),
        "primary_metric_for_later_scoring": "event_weighted_log_loss",
        "secondary_metrics_for_later_scoring": [
            "event_weighted_brier",
            "calibration_by_probability_bin",
            "delta_log_loss_vs_raw_midpoint",
            "delta_brier_vs_raw_midpoint",
            "performance_by_time_to_close_bucket",
            "performance_by_moneyness_or_strike_context_bucket_when_predeclared",
            "unique_event_day_week_counts",
        ],
    }


def design_fingerprint() -> str:
    payload = json.dumps(
        frozen_split_contract(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_split_contract() -> None:
    fractions = TRAIN_WEEK_FRACTION + VALIDATION_WEEK_FRACTION + LOCKED_TEST_WEEK_FRACTION
    if fractions != Decimal("1.00"):
        _error("week fractions must sum to 1.00")
    if any(value <= 0 for value in (TRAIN_WEEK_FRACTION, VALIDATION_WEEK_FRACTION, LOCKED_TEST_WEEK_FRACTION)):
        _error("all week fractions must be positive")
    if MIN_UNIQUE_WEEK_BLOCKS < 3:
        _error("minimum week-block count is too small")
    if EMBARGO_HOURS <= 0:
        _error("embargo must be positive")
    if len(EVENT_UNIT_FIELDS) != len(set(EVENT_UNIT_FIELDS)):
        _error("event-unit schema contains duplicate fields")
    if len(SPLIT_ROW_FIELDS) != len(set(SPLIT_ROW_FIELDS)):
        _error("split-row schema contains duplicate fields")
    bad = FORBIDDEN_PREOUTCOME_FIELDS.intersection(EVENT_UNIT_FIELDS)
    if bad:
        _error(f"event-unit schema contains forbidden fields: {sorted(bad)}")
    bad = FORBIDDEN_PREOUTCOME_FIELDS.intersection(SPLIT_ROW_FIELDS)
    if bad:
        _error(f"split-row schema contains forbidden fields: {sorted(bad)}")
    if CHECKPOINT10_EXPERIMENT_ID == EXPERIMENT_FAMILY_ID:
        _error("new experiment family must be distinct from Checkpoint 10")


def _require_exact_keys(row: Mapping[str, Any], expected: Sequence[str], name: str) -> None:
    expected_set = set(expected)
    actual_set = set(row)
    missing = expected_set - actual_set
    extra = actual_set - expected_set
    if missing:
        _error(f"{name} missing required fields: {sorted(missing)}")
    if extra:
        forbidden = FORBIDDEN_PREOUTCOME_FIELDS.intersection(extra)
        if forbidden:
            _error(f"{name} contains forbidden pre-outcome fields: {sorted(forbidden)}")
        _error(f"{name} contains unexpected fields: {sorted(extra)}")


def _nonempty_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or isinstance(value, (str, bytes)):
        _error(f"{name} must be a list/tuple of strings")
    items = tuple(_nonempty_text(item, f"{name} item") for item in value)
    if not allow_empty and not items:
        _error(f"{name} must not be empty")
    if len(items) != len(set(items)):
        _error(f"{name} contains duplicate identifiers")
    return items


def _parse_utc(value: Any, name: str) -> datetime:
    text = _nonempty_text(value, name)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise KxbtcdChronologicalSplitError(f"{name} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _error(f"{name} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_week_start(close_time_utc: str) -> str:
    dt = _parse_utc(close_time_utc, "close_time_utc")
    start = (dt - timedelta(days=dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return _format_utc(start)


def validate_event_unit(row: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        _error("event unit must be a mapping")
    _require_exact_keys(row, EVENT_UNIT_FIELDS, "event unit")
    event_ticker = _nonempty_text(row["event_ticker"], "event_ticker")
    close_dt = _parse_utc(row["close_time_utc"], "close_time_utc")
    regime = _nonempty_text(row["settlement_regime_id"], "settlement_regime_id")
    if regime != TARGET_REGIME_ID:
        _error(
            f"event {event_ticker} is outside frozen settlement regime {TARGET_REGIME_ID!r}"
        )
    primitives = _string_list(row["settlement_primitive_ids"], "settlement_primitive_ids")
    lineage = _string_list(row["source_lineage_refs"], "source_lineage_refs")
    return {
        "event_ticker": event_ticker,
        "close_time_utc": _format_utc(close_dt),
        "settlement_regime_id": regime,
        "settlement_primitive_ids": primitives,
        "source_lineage_refs": lineage,
    }


def partition_week_counts(unique_week_count: int) -> tuple[int, int, int]:
    if not isinstance(unique_week_count, int) or isinstance(unique_week_count, bool):
        _error("unique_week_count must be an integer")
    if unique_week_count < MIN_UNIQUE_WEEK_BLOCKS:
        _error(
            f"need at least {MIN_UNIQUE_WEEK_BLOCKS} unique UTC weeks, "
            f"found {unique_week_count}"
        )
    train = int(Decimal(unique_week_count) * TRAIN_WEEK_FRACTION)
    validation = int(Decimal(unique_week_count) * VALIDATION_WEEK_FRACTION)
    locked_test = unique_week_count - train - validation
    if min(train, validation, locked_test) <= 0:
        _error("week split produced an empty partition")
    return train, validation, locked_test


def _normalize_quarantine(
    checkpoint10_event_tickers: Sequence[str],
    checkpoint10_primitive_ids: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    events = _string_list(
        checkpoint10_event_tickers,
        "checkpoint10_event_tickers",
    )
    if len(events) != CHECKPOINT10_SOURCE_EVENT_COUNT:
        _error(
            f"Checkpoint-10 quarantine must contain exactly {CHECKPOINT10_SOURCE_EVENT_COUNT} "
            f"source event tickers, found {len(events)}"
        )
    primitives = _string_list(
        checkpoint10_primitive_ids,
        "checkpoint10_primitive_ids",
    )
    return tuple(sorted(events)), tuple(sorted(primitives))


def _check_primitive_partition_leakage(rows: Sequence[Mapping[str, Any]]) -> None:
    partitions_by_primitive: dict[str, set[str]] = {}
    for row in rows:
        if not row["eligible_for_modeling"]:
            continue
        for primitive in row["settlement_primitive_ids"]:
            partitions_by_primitive.setdefault(primitive, set()).add(row["partition"])
    leaking = {
        primitive: sorted(partitions)
        for primitive, partitions in partitions_by_primitive.items()
        if len(partitions) > 1
    }
    if leaking:
        _error(f"settlement primitive leakage across partitions: {leaking}")


def _split_fingerprint_payload(
    rows_without_split_fingerprint: Sequence[Mapping[str, Any]],
    quarantine_events: Sequence[str],
    quarantine_primitives: Sequence[str],
) -> dict[str, Any]:
    return {
        "design_fingerprint": design_fingerprint(),
        "checkpoint10_quarantine_event_tickers": list(quarantine_events),
        "checkpoint10_quarantine_primitive_ids": list(quarantine_primitives),
        "rows": [
            {
                key: value
                for key, value in row.items()
                if key != "split_fingerprint"
            }
            for row in rows_without_split_fingerprint
        ],
    }


def build_chronological_split(
    event_units: Sequence[Mapping[str, Any]],
    *,
    checkpoint10_event_tickers: Sequence[str],
    checkpoint10_primitive_ids: Sequence[str],
) -> tuple[dict[str, Any], ...]:
    """Build deterministic pre-outcome KXBTCD event partitions.

    Inputs contain no outcomes. The returned rows include quarantined and
    embargoed events for audit, but only rows with ``eligible_for_modeling``
    true may enter model fitting/evaluation.
    """

    validate_split_contract()
    quarantine_events, quarantine_primitives = _normalize_quarantine(
        checkpoint10_event_tickers,
        checkpoint10_primitive_ids,
    )
    quarantine_event_set = set(quarantine_events)
    quarantine_primitive_set = set(quarantine_primitives)

    normalized: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    for raw in event_units:
        event = validate_event_unit(raw)
        ticker = event["event_ticker"]
        if ticker in seen_events:
            _error(f"duplicate event_ticker in split universe: {ticker}")
        seen_events.add(ticker)
        normalized.append(event)

    normalized.sort(key=lambda row: (_parse_utc(row["close_time_utc"], "close_time_utc"), row["event_ticker"]))

    partition_candidates: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for event in normalized:
        primitive_overlap = quarantine_primitive_set.intersection(event["settlement_primitive_ids"])
        if event["event_ticker"] in quarantine_event_set:
            quarantined.append({**event, "exclusion_reason": "checkpoint10_event_quarantine"})
        elif primitive_overlap:
            quarantined.append({**event, "exclusion_reason": "checkpoint10_primitive_quarantine"})
        else:
            partition_candidates.append(event)

    weeks = sorted({utc_week_start(event["close_time_utc"]) for event in partition_candidates})
    train_count, validation_count, locked_test_count = partition_week_counts(len(weeks))
    assert train_count + validation_count + locked_test_count == len(weeks)

    train_weeks = set(weeks[:train_count])
    validation_weeks = set(weeks[train_count : train_count + validation_count])
    locked_test_weeks = set(weeks[train_count + validation_count :])
    validation_boundary = _parse_utc(min(validation_weeks), "validation_boundary")
    locked_test_boundary = _parse_utc(min(locked_test_weeks), "locked_test_boundary")
    embargo_delta = timedelta(hours=EMBARGO_HOURS)

    fingerprint = design_fingerprint()
    rows: list[dict[str, Any]] = []

    for event in partition_candidates:
        week = utc_week_start(event["close_time_utc"])
        close_dt = _parse_utc(event["close_time_utc"], "close_time_utc")
        if week in train_weeks:
            partition = "train"
        elif week in validation_weeks:
            partition = "validation"
        elif week in locked_test_weeks:
            partition = "locked_test"
        else:  # pragma: no cover - defensive invariant
            _error(f"event week was not assigned: {week}")

        embargoed = (
            validation_boundary <= close_dt < validation_boundary + embargo_delta
            or locked_test_boundary <= close_dt < locked_test_boundary + embargo_delta
        )
        rows.append(
            {
                "schema_version": SPLIT_ROW_SCHEMA_VERSION,
                "experiment_family_id": EXPERIMENT_FAMILY_ID,
                "design_fingerprint": fingerprint,
                "split_fingerprint": "",
                "event_ticker": event["event_ticker"],
                "close_time_utc": event["close_time_utc"],
                "utc_week_start": week,
                "settlement_regime_id": event["settlement_regime_id"],
                "settlement_primitive_ids": list(event["settlement_primitive_ids"]),
                "source_lineage_refs": list(event["source_lineage_refs"]),
                "partition": partition,
                "embargoed": embargoed,
                "eligible_for_modeling": not embargoed,
                "exclusion_reason": "partition_boundary_embargo" if embargoed else "",
            }
        )

    for event in quarantined:
        rows.append(
            {
                "schema_version": SPLIT_ROW_SCHEMA_VERSION,
                "experiment_family_id": EXPERIMENT_FAMILY_ID,
                "design_fingerprint": fingerprint,
                "split_fingerprint": "",
                "event_ticker": event["event_ticker"],
                "close_time_utc": event["close_time_utc"],
                "utc_week_start": utc_week_start(event["close_time_utc"]),
                "settlement_regime_id": event["settlement_regime_id"],
                "settlement_primitive_ids": list(event["settlement_primitive_ids"]),
                "source_lineage_refs": list(event["source_lineage_refs"]),
                "partition": "quarantine",
                "embargoed": False,
                "eligible_for_modeling": False,
                "exclusion_reason": event["exclusion_reason"],
            }
        )

    rows.sort(key=lambda row: (_parse_utc(row["close_time_utc"], "close_time_utc"), row["event_ticker"]))
    _check_primitive_partition_leakage(rows)

    payload = _split_fingerprint_payload(rows, quarantine_events, quarantine_primitives)
    split_fp = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    for row in rows:
        row["split_fingerprint"] = split_fp

    return tuple(rows)


def split_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return audit counts without inspecting any outcomes."""

    counts = {name: 0 for name in (*PARTITIONS, "quarantine")}
    eligible = {name: 0 for name in PARTITIONS}
    embargoed = 0
    unique_weeks_by_partition = {name: set() for name in PARTITIONS}
    for row in rows:
        partition = row.get("partition")
        if partition not in counts:
            _error(f"unknown partition in split row: {partition!r}")
        counts[partition] += 1
        if row.get("embargoed"):
            embargoed += 1
        if partition in PARTITIONS:
            unique_weeks_by_partition[partition].add(row["utc_week_start"])
            if row.get("eligible_for_modeling"):
                eligible[partition] += 1
    return {
        "event_count": len(rows),
        "partition_event_counts": counts,
        "eligible_event_counts": eligible,
        "embargoed_event_count": embargoed,
        "unique_week_counts": {
            name: len(weeks) for name, weeks in unique_weeks_by_partition.items()
        },
        "design_fingerprint": design_fingerprint(),
        "split_fingerprint": rows[0]["split_fingerprint"] if rows else None,
    }


validate_split_contract()
