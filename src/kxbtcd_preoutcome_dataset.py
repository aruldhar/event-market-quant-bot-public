"""Outcome-blind KXBTCD dataset builder and frozen Candidate-B specification.

Checkpoint 12 uses this module only to construct auditable pre-outcome rows and
freeze the first learned KXBTCD model specification. It does not fetch labels,
fit coefficients, score outcomes, access a network, or perform execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from typing import Any, Mapping, Sequence

from src.btc_state_feature_contract import (
    CONTRACT_SCHEMA_VERSION as BTC_STATE_CONTRACT_VERSION,
    KXBTCD_CONTEXT_FIELDS,
    STATE_SCHEMA_VERSION,
    contract_fingerprint as btc_state_contract_fingerprint,
    validate_synchronized_state,
)
from src.kxbtcd_chronological_split_contract import (
    CONTRACT_SCHEMA_VERSION as SPLIT_CONTRACT_VERSION,
    EXPERIMENT_FAMILY_ID,
    PARTITIONS,
    SPLIT_ROW_SCHEMA_VERSION,
    TARGET_REGIME_ID,
    design_fingerprint as split_design_fingerprint,
)


class KxbtcdPreoutcomeDatasetError(ValueError):
    """Raised when the pre-outcome dataset/model contract is violated."""


DATASET_CONTRACT_VERSION = "kxbtcd_preoutcome_dataset_contract.v1"
DATASET_ROW_SCHEMA_VERSION = "kxbtcd_preoutcome_dataset_row.v1"
EXCLUSION_ROW_SCHEMA_VERSION = "kxbtcd_preoutcome_exclusion_row.v1"
CANDIDATE_B_MODEL_ID = "kxbtcd_market_context_logistic.v1"

MARKET_LOGIT_CLIP = Decimal("0.001")
STRIKE_ANCHOR_DOLLARS = Decimal("100000")
TIME_TO_CLOSE_SCALE_SECONDS = Decimal("3600")
TIME_TO_CLOSE_TOLERANCE_SECONDS = Decimal("1")
L2_PENALTY_GRID = (
    Decimal("0.01"),
    Decimal("0.1"),
    Decimal("1"),
    Decimal("10"),
)

CANDIDATE_B_FEATURE_NAMES = (
    "market_logit",
    "strike_log_ratio",
    "time_log1p_hours",
)

DATASET_ROW_FIELDS = (
    "schema_version",
    "experiment_family_id",
    "dataset_design_fingerprint",
    "dataset_fingerprint",
    "split_fingerprint",
    "state_contract_fingerprint",
    "candidate_b_spec_fingerprint",
    "state_id",
    "state_view",
    "event_ticker",
    "market_ticker",
    "partition",
    "utc_week_start",
    "event_close_time_utc",
    "as_of_utc",
    "as_of_local_monotonic_ns",
    "alignment_epoch_id",
    "settlement_regime_id",
    "strike_dollars",
    "time_to_close_seconds",
    "yes_bid",
    "yes_ask",
    "spread",
    "q_market",
    "q_market_clipped_for_logit",
    "candidate_b_market_logit",
    "candidate_b_strike_log_ratio",
    "candidate_b_time_log1p_hours",
    "event_row_weight",
    "raw_observation_refs",
)

EXCLUSION_ROW_FIELDS = (
    "schema_version",
    "state_id",
    "state_view",
    "event_ticker",
    "market_ticker",
    "partition",
    "state_quality",
    "exclusion_reasons",
    "raw_observation_refs",
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
        "action",
        "order",
        "order_id",
    }
)


@dataclass(frozen=True)
class PreoutcomeDatasetBuild:
    """Immutable result of one outcome-blind dataset construction."""

    rows: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]
    summary: dict[str, Any]


def _error(message: str) -> None:
    raise KxbtcdPreoutcomeDatasetError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KxbtcdPreoutcomeDatasetError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty UTC timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise KxbtcdPreoutcomeDatasetError(f"{name} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _error(f"{name} must carry UTC timezone information")
    return parsed.astimezone(timezone.utc)


def _require_exact_keys(row: Mapping[str, Any], expected: Sequence[str], name: str) -> None:
    missing = set(expected) - set(row)
    extra = set(row) - set(expected)
    if missing:
        _error(f"{name} missing required fields: {sorted(missing)}")
    if extra:
        _error(f"{name} contains unexpected fields: {sorted(extra)}")


def _reject_forbidden_keys(row: Mapping[str, Any], name: str) -> None:
    leaked = FORBIDDEN_PREOUTCOME_FIELDS.intersection(row)
    if leaked:
        _error(f"{name} contains forbidden outcome/downstream fields: {sorted(leaked)}")


def candidate_b_specification() -> dict[str, Any]:
    """Return the exact first learned KXBTCD baseline specification.

    The specification is intentionally library-independent. A later fitting
    implementation must reproduce this objective and selection policy rather
    than silently substituting defaults from a modeling package.
    """

    return {
        "model_id": CANDIDATE_B_MODEL_ID,
        "product_head": "KXBTCD",
        "task": "binary_settlement_probability",
        "benchmark_a": {
            "name": "raw_market_midpoint",
            "formula": "q_market=(yes_bid+yes_ask)/2",
            "training_required": False,
        },
        "learned_features": [
            {
                "name": "market_logit",
                "formula": "ln(clip(q_market,0.001,0.999)/(1-clip(q_market,0.001,0.999)))",
                "source": "KXBTCD contemporaneous quote context",
            },
            {
                "name": "strike_log_ratio",
                "formula": "ln(strike_dollars/100000)",
                "source": "KXBTCD strike context",
            },
            {
                "name": "time_log1p_hours",
                "formula": "ln(1+time_to_close_seconds/3600)",
                "source": "KXBTCD time context",
            },
        ],
        "external_btc_state_features": [],
        "interactions": [],
        "polynomial_terms": [],
        "model_form": "logistic_regression_with_intercept",
        "linear_predictor": (
            "beta0 + beta1*market_logit + beta2*strike_log_ratio + "
            "beta3*time_log1p_hours"
        ),
        "regularization": {
            "type": "l2",
            "penalize_intercept": False,
            "lambda_grid": [str(value) for value in L2_PENALTY_GRID],
        },
        "training_objective": (
            "mean_over_events(mean_binary_log_loss_within_event) + "
            "lambda/2 * sum(non_intercept_beta_squared)"
        ),
        "class_weighting": "none",
        "row_weighting": "within_each_event_rows_sum_to_one",
        "validation_selection": {
            "metric": "event_weighted_log_loss",
            "choose": "lowest_validation_loss",
            "exact_tie_break": "larger_lambda_stronger_regularization",
        },
        "locked_test_entry_gate": (
            "candidate_validation_event_weighted_log_loss_strictly_less_than_"
            "raw_midpoint_validation_event_weighted_log_loss"
        ),
        "final_refit_if_gate_passes": (
            "refit_selected_lambda_on_train_plus_validation_before_one_locked_test_evaluation"
        ),
        "locked_test_outcomes_opened": False,
        "candidate_c_external_state_augmentation_authorized": False,
        "subsecond_lead_lag_authorized": False,
        "execution_authorized": False,
    }


def candidate_b_spec_fingerprint() -> str:
    payload = json.dumps(
        candidate_b_specification(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def dataset_design_definition() -> dict[str, Any]:
    return {
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "dataset_row_schema_version": DATASET_ROW_SCHEMA_VERSION,
        "btc_state_contract_version": BTC_STATE_CONTRACT_VERSION,
        "btc_state_contract_fingerprint": btc_state_contract_fingerprint(),
        "split_contract_version": SPLIT_CONTRACT_VERSION,
        "split_design_fingerprint": split_design_fingerprint(),
        "experiment_family_id": EXPERIMENT_FAMILY_ID,
        "target_regime_id": TARGET_REGIME_ID,
        "candidate_b_model_id": CANDIDATE_B_MODEL_ID,
        "candidate_b_spec_fingerprint": candidate_b_spec_fingerprint(),
        "time_to_close_consistency_tolerance_seconds": str(
            TIME_TO_CLOSE_TOLERANCE_SECONDS
        ),
        "state_view_rule": "only_historical_reconstructed_states_enter_this_offline_dataset",
        "state_quality_rule": "only_state_quality_usable_enters_dataset_rows",
        "split_rule": "only_split_eligible_for_modeling_true_enters_dataset_rows",
        "event_weight_rule": "each_event_total_row_weight_equals_one",
        "locked_test_rule": "preoutcome_rows_may_exist_but_no_locked_test_labels_are_materialized",
        "raw_lineage_rule": "carry_parent_state_raw_observation_refs",
        "outcome_fields_allowed": False,
        "network_access": False,
        "model_fitting": False,
        "execution_authorized": False,
    }


def dataset_design_fingerprint() -> str:
    payload = json.dumps(
        dataset_design_definition(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_dataset_contract() -> None:
    if "market_ticker" not in KXBTCD_CONTEXT_FIELDS:
        _error("KXBTCD state contract must identify exact market_ticker")
    if candidate_b_specification()["external_btc_state_features"]:
        _error("Candidate B must not contain external BTC-state features")
    if tuple(item["name"] for item in candidate_b_specification()["learned_features"]) != CANDIDATE_B_FEATURE_NAMES:
        _error("Candidate B feature set changed")
    if candidate_b_specification()["execution_authorized"] is not False:
        _error("execution must remain unauthorized")
    for fields, name in (
        (DATASET_ROW_FIELDS, "dataset row"),
        (EXCLUSION_ROW_FIELDS, "exclusion row"),
    ):
        if len(fields) != len(set(fields)):
            _error(f"{name} schema contains duplicate fields")
        leaked = FORBIDDEN_PREOUTCOME_FIELDS.intersection(fields)
        if leaked:
            _error(f"{name} schema contains forbidden fields: {sorted(leaked)}")


def candidate_b_transforms(
    q_market: Any,
    strike_dollars: Any,
    time_to_close_seconds: Any,
) -> dict[str, str]:
    q = _decimal(q_market, "q_market")
    strike = _decimal(strike_dollars, "strike_dollars")
    ttc = _decimal(time_to_close_seconds, "time_to_close_seconds")
    if q < 0 or q > 1:
        _error("q_market must be within [0, 1]")
    if strike <= 0:
        _error("strike_dollars must be positive")
    if ttc < 0:
        _error("time_to_close_seconds must be nonnegative")

    clipped = min(max(q, MARKET_LOGIT_CLIP), Decimal("1") - MARKET_LOGIT_CLIP)
    with localcontext() as context:
        context.prec = 34
        market_logit = (clipped / (Decimal("1") - clipped)).ln()
        strike_log_ratio = (strike / STRIKE_ANCHOR_DOLLARS).ln()
        time_log1p_hours = (
            Decimal("1") + ttc / TIME_TO_CLOSE_SCALE_SECONDS
        ).ln()
    return {
        "q_market": _decimal_text(q),
        "q_market_clipped_for_logit": _decimal_text(clipped),
        "market_logit": _decimal_text(market_logit),
        "strike_log_ratio": _decimal_text(strike_log_ratio),
        "time_log1p_hours": _decimal_text(time_log1p_hours),
    }


def _validate_split_rows(split_rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Mapping[str, Any]], str]:
    if not split_rows:
        _error("split_rows must not be empty")
    by_event: dict[str, Mapping[str, Any]] = {}
    split_fingerprints: set[str] = set()
    for index, row in enumerate(split_rows):
        if not isinstance(row, Mapping):
            _error(f"split_rows[{index}] must be a mapping")
        _reject_forbidden_keys(row, f"split_rows[{index}]")
        if row.get("schema_version") != SPLIT_ROW_SCHEMA_VERSION:
            _error(f"split_rows[{index}] schema_version mismatch")
        if row.get("experiment_family_id") != EXPERIMENT_FAMILY_ID:
            _error(f"split_rows[{index}] experiment family mismatch")
        if row.get("design_fingerprint") != split_design_fingerprint():
            _error(f"split_rows[{index}] design fingerprint mismatch")
        if row.get("settlement_regime_id") != TARGET_REGIME_ID:
            _error(f"split_rows[{index}] settlement regime mismatch")
        ticker = row.get("event_ticker")
        if not isinstance(ticker, str) or not ticker:
            _error(f"split_rows[{index}] event_ticker must be non-empty")
        if ticker in by_event:
            _error(f"duplicate event_ticker in split rows: {ticker}")
        partition = row.get("partition")
        if partition not in {*PARTITIONS, "quarantine"}:
            _error(f"split_rows[{index}] has invalid partition {partition!r}")
        split_fp = row.get("split_fingerprint")
        if not isinstance(split_fp, str) or len(split_fp) != 64:
            _error(f"split_rows[{index}] split_fingerprint is invalid")
        split_fingerprints.add(split_fp)
        by_event[ticker] = row
    if len(split_fingerprints) != 1:
        _error("split rows mix multiple split_fingerprints")
    return by_event, next(iter(split_fingerprints))


def _state_identity(state: Mapping[str, Any]) -> tuple[str, str, str]:
    state_id = state.get("state_id")
    context = state.get("product_context")
    if not isinstance(state_id, str) or not state_id:
        _error("state_id must be non-empty")
    if not isinstance(context, Mapping):
        _error(f"state {state_id} product_context must be a mapping")
    event_ticker = context.get("event_ticker")
    market_ticker = context.get("market_ticker")
    if not isinstance(event_ticker, str) or not event_ticker:
        _error(f"state {state_id} event_ticker must be non-empty")
    if not isinstance(market_ticker, str) or not market_ticker:
        _error(f"state {state_id} market_ticker must be non-empty")
    return state_id, event_ticker, market_ticker


def _validate_time_to_close(state: Mapping[str, Any], split_row: Mapping[str, Any]) -> None:
    state_id = str(state["state_id"])
    as_of = _parse_utc(state["as_of_utc"], f"state {state_id}.as_of_utc")
    close = _parse_utc(split_row["close_time_utc"], f"state {state_id}.event_close_time_utc")
    observed = _decimal(
        state["product_context"]["time_to_close_seconds"],
        f"state {state_id}.time_to_close_seconds",
    )
    computed = Decimal(str((close - as_of).total_seconds()))
    if computed < 0:
        _error(f"state {state_id} occurs after event close")
    if abs(computed - observed) > TIME_TO_CLOSE_TOLERANCE_SECONDS:
        _error(
            f"state {state_id} time_to_close_seconds disagrees with event close by more than "
            f"{TIME_TO_CLOSE_TOLERANCE_SECONDS} second"
        )


def _build_exclusion(
    state: Mapping[str, Any],
    split_row: Mapping[str, Any],
    reasons: Sequence[str],
) -> dict[str, Any]:
    context = state["product_context"]
    return {
        "schema_version": EXCLUSION_ROW_SCHEMA_VERSION,
        "state_id": state["state_id"],
        "state_view": state["state_view"],
        "event_ticker": context["event_ticker"],
        "market_ticker": context["market_ticker"],
        "partition": split_row["partition"],
        "state_quality": state["state_quality"],
        "exclusion_reasons": list(reasons),
        "raw_observation_refs": list(state["raw_observation_refs"]),
    }


def _row_without_weight(
    state: Mapping[str, Any],
    split_row: Mapping[str, Any],
    split_fp: str,
) -> dict[str, Any]:
    context = state["product_context"]
    transforms = candidate_b_transforms(
        context["midpoint"],
        context["strike_dollars"],
        context["time_to_close_seconds"],
    )
    return {
        "schema_version": DATASET_ROW_SCHEMA_VERSION,
        "experiment_family_id": EXPERIMENT_FAMILY_ID,
        "dataset_design_fingerprint": dataset_design_fingerprint(),
        "dataset_fingerprint": "",
        "split_fingerprint": split_fp,
        "state_contract_fingerprint": btc_state_contract_fingerprint(),
        "candidate_b_spec_fingerprint": candidate_b_spec_fingerprint(),
        "state_id": state["state_id"],
        "state_view": state["state_view"],
        "event_ticker": context["event_ticker"],
        "market_ticker": context["market_ticker"],
        "partition": split_row["partition"],
        "utc_week_start": split_row["utc_week_start"],
        "event_close_time_utc": split_row["close_time_utc"],
        "as_of_utc": state["as_of_utc"],
        "as_of_local_monotonic_ns": state["as_of_local_monotonic_ns"],
        "alignment_epoch_id": state["alignment_epoch_id"],
        "settlement_regime_id": context["settlement_regime_id"],
        "strike_dollars": _decimal_text(_decimal(context["strike_dollars"], "strike_dollars")),
        "time_to_close_seconds": _decimal_text(
            _decimal(context["time_to_close_seconds"], "time_to_close_seconds")
        ),
        "yes_bid": _decimal_text(_decimal(context["yes_bid"], "yes_bid")),
        "yes_ask": _decimal_text(_decimal(context["yes_ask"], "yes_ask")),
        "spread": _decimal_text(_decimal(context["spread"], "spread")),
        "q_market": transforms["q_market"],
        "q_market_clipped_for_logit": transforms["q_market_clipped_for_logit"],
        "candidate_b_market_logit": transforms["market_logit"],
        "candidate_b_strike_log_ratio": transforms["strike_log_ratio"],
        "candidate_b_time_log1p_hours": transforms["time_log1p_hours"],
        "event_row_weight": "",
        "raw_observation_refs": list(state["raw_observation_refs"]),
    }


def _dataset_fingerprint(
    rows: Sequence[Mapping[str, Any]], exclusions: Sequence[Mapping[str, Any]]
) -> str:
    payload = {
        "dataset_design_fingerprint": dataset_design_fingerprint(),
        "rows": [
            {key: value for key, value in row.items() if key != "dataset_fingerprint"}
            for row in rows
        ],
        "exclusions": list(exclusions),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_preoutcome_dataset(
    synchronized_states: Sequence[Mapping[str, Any]],
    split_rows: Sequence[Mapping[str, Any]],
) -> PreoutcomeDatasetBuild:
    """Construct Candidate-B-ready pre-outcome rows without opening labels."""

    validate_dataset_contract()
    split_by_event, split_fp = _validate_split_rows(split_rows)
    seen_state_ids: set[str] = set()
    provisional_rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []

    for index, state in enumerate(synchronized_states):
        if not isinstance(state, Mapping):
            _error(f"synchronized_states[{index}] must be a mapping")
        _reject_forbidden_keys(state, f"synchronized_states[{index}]")
        validate_synchronized_state(state)
        state_id, event_ticker, _market_ticker = _state_identity(state)
        if state_id in seen_state_ids:
            _error(f"duplicate state_id in dataset input: {state_id}")
        seen_state_ids.add(state_id)
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            _error(f"state {state_id} schema_version mismatch")
        if state.get("product_head") != "KXBTCD":
            _error(f"state {state_id} is not a KXBTCD state")
        if state.get("state_view") != "historical_reconstructed":
            _error(
                f"state {state_id} must use state_view=historical_reconstructed for "
                "the offline historical Candidate-B dataset"
            )
        if event_ticker not in split_by_event:
            _error(f"state {state_id} event {event_ticker!r} is absent from frozen split")
        split_row = split_by_event[event_ticker]
        context = state["product_context"]
        if context["settlement_regime_id"] != TARGET_REGIME_ID:
            _error(f"state {state_id} settlement regime changed")
        if context["settlement_regime_id"] != split_row["settlement_regime_id"]:
            _error(f"state {state_id} settlement regime disagrees with split row")
        _validate_time_to_close(state, split_row)

        reasons: list[str] = []
        if state["state_quality"] != "usable":
            reasons.append(f"state_quality:{state['state_quality']}")
        if not split_row["eligible_for_modeling"]:
            reasons.append(
                split_row.get("exclusion_reason") or "split_not_eligible_for_modeling"
            )
        if reasons:
            exclusions.append(_build_exclusion(state, split_row, reasons))
            continue

        if split_row["partition"] not in PARTITIONS:
            _error(
                f"state {state_id} is marked modeling-eligible in invalid partition "
                f"{split_row['partition']!r}"
            )
        provisional_rows.append(_row_without_weight(state, split_row, split_fp))

    if not provisional_rows:
        _error("no modeling-eligible KXBTCD states remained after fail-closed filters")

    rows_per_event: dict[str, int] = {}
    for row in provisional_rows:
        rows_per_event[row["event_ticker"]] = rows_per_event.get(row["event_ticker"], 0) + 1
    for row in provisional_rows:
        row["event_row_weight"] = _decimal_text(
            Decimal("1") / Decimal(rows_per_event[row["event_ticker"]])
        )

    provisional_rows.sort(
        key=lambda row: (
            _parse_utc(row["event_close_time_utc"], "event_close_time_utc"),
            row["event_ticker"],
            _parse_utc(row["as_of_utc"], "as_of_utc"),
            row["market_ticker"],
            row["state_id"],
        )
    )
    exclusions.sort(key=lambda row: (row["event_ticker"], row["market_ticker"], row["state_id"]))

    fingerprint = _dataset_fingerprint(provisional_rows, exclusions)
    for row in provisional_rows:
        row["dataset_fingerprint"] = fingerprint
        _require_exact_keys(row, DATASET_ROW_FIELDS, "dataset row")
        _reject_forbidden_keys(row, "dataset row")
    for row in exclusions:
        _require_exact_keys(row, EXCLUSION_ROW_FIELDS, "exclusion row")
        _reject_forbidden_keys(row, "exclusion row")

    partition_row_counts = {partition: 0 for partition in PARTITIONS}
    partition_events = {partition: set() for partition in PARTITIONS}
    for row in provisional_rows:
        partition_row_counts[row["partition"]] += 1
        partition_events[row["partition"]].add(row["event_ticker"])

    summary = {
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "dataset_design_fingerprint": dataset_design_fingerprint(),
        "dataset_fingerprint": fingerprint,
        "state_contract_fingerprint": btc_state_contract_fingerprint(),
        "split_fingerprint": split_fp,
        "candidate_b_spec_fingerprint": candidate_b_spec_fingerprint(),
        "eligible_row_count": len(provisional_rows),
        "excluded_state_count": len(exclusions),
        "partition_row_counts": partition_row_counts,
        "partition_event_counts": {
            partition: len(events) for partition, events in partition_events.items()
        },
        "unique_event_count": len(rows_per_event),
        "locked_test_label_count": 0,
        "model_fit_performed": False,
    }
    return PreoutcomeDatasetBuild(
        rows=tuple(provisional_rows),
        exclusions=tuple(exclusions),
        summary=summary,
    )


def select_candidate_b_lambda(validation_event_weighted_log_loss_by_lambda: Mapping[Any, Any]) -> Decimal:
    """Apply the frozen validation-only hyperparameter selection rule.

    This function does not compute losses or inspect labels; it only applies the
    already-declared rule to caller-supplied aggregate validation scores.
    """

    normalized: dict[Decimal, Decimal] = {}
    for raw_lambda, raw_loss in validation_event_weighted_log_loss_by_lambda.items():
        penalty = _decimal(raw_lambda, "lambda")
        loss = _decimal(raw_loss, f"validation loss for lambda={penalty}")
        if loss < 0:
            _error("validation log loss must be nonnegative")
        normalized[penalty] = loss
    expected = set(L2_PENALTY_GRID)
    if set(normalized) != expected:
        _error(
            "validation selection must contain exactly the frozen lambda grid: "
            f"{[str(value) for value in L2_PENALTY_GRID]}"
        )
    best_loss = min(normalized.values())
    tied = [penalty for penalty, loss in normalized.items() if loss == best_loss]
    return max(tied)


def candidate_b_validation_gate(
    *, raw_midpoint_event_weighted_log_loss: Any, candidate_b_event_weighted_log_loss: Any
) -> bool:
    """Return whether Candidate B is allowed to advance to one locked-test evaluation."""

    raw = _decimal(raw_midpoint_event_weighted_log_loss, "raw midpoint validation log loss")
    candidate = _decimal(candidate_b_event_weighted_log_loss, "Candidate B validation log loss")
    if raw < 0 or candidate < 0:
        _error("validation log loss must be nonnegative")
    return candidate < raw


validate_dataset_contract()
