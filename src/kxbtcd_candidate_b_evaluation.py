"""Checkpoint-13 KXBTCD Candidate-B train/validation evaluation.

This module is intentionally narrow:

* it accepts only the exact Checkpoint-12 frozen pre-outcome run;
* it builds an outcome request allow-list from train/validation rows only;
* it builds an explicit locked-test deny-list before any request is allowed;
* it fits the frozen four-parameter Candidate-B logistic model;
* it selects lambda on validation event-weighted log loss;
* it evaluates the strict validation gate without opening locked-test outcomes.

It does not place, cancel, simulate, or otherwise create orders.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .kxbtcd_preoutcome_dataset import (
    CANDIDATE_B_MODEL_ID,
    DATASET_ROW_FIELDS,
    FORBIDDEN_PREOUTCOME_FIELDS,
    L2_PENALTY_GRID,
    candidate_b_spec_fingerprint,
    candidate_b_validation_gate,
    dataset_design_fingerprint,
    select_candidate_b_lambda,
)
from .kxbtcd_preoutcome_materialization import (
    MATERIALIZATION_CONTRACT_VERSION,
    materialization_fingerprint,
)
from .run_manifest import resolve_stored_path
from .run_validation import RunValidationError, validate_run_manifest


class KxbtcdCandidateBEvaluationError(RuntimeError):
    """Raised when a frozen-data, label, fit, or scoring invariant fails."""


FROZEN_PREOUTCOME_RUN_ID = (
    "collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d"
)
FROZEN_SPLIT_FINGERPRINT = (
    "28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503"
)
FROZEN_DATASET_FINGERPRINT = (
    "d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a"
)
FROZEN_CANDIDATE_B_SPEC_FINGERPRINT = (
    "e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3"
)
FROZEN_DATASET_DESIGN_FINGERPRINT = (
    "adc0e6a05ec6a61c114a7d49cb0ad5e271321fe0e8c3c80b76fed81b98025286"
)
FROZEN_MATERIALIZATION_FINGERPRINT = (
    "f9a2459f81b1bb90e1ff55d099e837cb47c78c6586195759d55b5029d676bdb5"
)

EXPECTED_PARTITION_EVENT_COUNTS = {
    "train": 175,
    "validation": 56,
    "locked_test": 64,
}
EXPECTED_PARTITION_ROW_COUNTS = {
    "train": 4645,
    "validation": 719,
    "locked_test": 1014,
}
EXPECTED_ELIGIBLE_ROWS = 6378
EXPECTED_UNIQUE_EVENTS = 295

OUTCOME_SCHEMA_VERSION = "kxbtcd_candidate_b_outcome.v1"
COEFFICIENT_SCHEMA_VERSION = "kxbtcd_candidate_b_coefficients.v1"
LAMBDA_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_b_lambda_score.v1"
PREDICTION_SCHEMA_VERSION = "kxbtcd_candidate_b_prediction_score.v1"
CALIBRATION_SCHEMA_VERSION = "kxbtcd_candidate_b_calibration.v1"
SLICE_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_b_slice_score.v1"

OUTCOME_FIELDS = (
    "schema_version",
    "model_id",
    "preoutcome_run_id",
    "dataset_fingerprint",
    "split_fingerprint",
    "candidate_b_spec_fingerprint",
    "partition",
    "event_ticker",
    "market_ticker",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "market_status",
    "result_text",
    "outcome",
)

COEFFICIENT_FIELDS = (
    "schema_version",
    "model_id",
    "dataset_fingerprint",
    "split_fingerprint",
    "lambda",
    "beta0",
    "beta1_market_logit",
    "beta2_strike_log_ratio",
    "beta3_time_log1p_hours",
    "iterations",
    "converged",
    "train_objective",
    "train_event_weighted_log_loss",
    "train_event_weighted_brier",
    "validation_event_weighted_log_loss",
    "validation_event_weighted_brier",
    "selected_lambda",
)

LAMBDA_SCORE_FIELDS = (
    "schema_version",
    "model_id",
    "dataset_fingerprint",
    "split_fingerprint",
    "lambda",
    "train_objective",
    "train_event_weighted_log_loss",
    "train_event_weighted_brier",
    "validation_event_weighted_log_loss",
    "validation_event_weighted_brier",
    "validation_delta_log_loss_raw_minus_candidate",
    "validation_delta_brier_raw_minus_candidate",
    "selected_lambda",
)

PREDICTION_FIELDS = (
    "schema_version",
    "model_id",
    "dataset_fingerprint",
    "split_fingerprint",
    "partition",
    "state_id",
    "event_ticker",
    "market_ticker",
    "utc_week_start",
    "event_close_time_utc",
    "time_to_close_seconds",
    "strike_dollars",
    "event_row_weight",
    "outcome",
    "q_market",
    "candidate_b_probability",
    "raw_log_loss",
    "candidate_b_log_loss",
    "raw_brier",
    "candidate_b_brier",
)

CALIBRATION_FIELDS = (
    "schema_version",
    "model_id",
    "dataset_fingerprint",
    "partition",
    "model",
    "bin_lower_inclusive",
    "bin_upper_inclusive",
    "row_count",
    "event_count",
    "event_weight_sum",
    "event_weighted_mean_prediction",
    "event_weighted_observed_rate",
)

SLICE_SCORE_FIELDS = (
    "schema_version",
    "model_id",
    "dataset_fingerprint",
    "partition",
    "slice_type",
    "slice_value",
    "row_count",
    "event_count",
    "raw_event_weighted_log_loss",
    "candidate_event_weighted_log_loss",
    "delta_log_loss_raw_minus_candidate",
    "raw_event_weighted_brier",
    "candidate_event_weighted_brier",
    "delta_brier_raw_minus_candidate",
)

CALIBRATION_BIN_EDGES = tuple(Decimal(i) / Decimal(10) for i in range(11))


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
class OutcomeRequest:
    partition: str
    event_ticker: str
    market_ticker: str


@dataclass(frozen=True)
class FrozenPreoutcomeDataset:
    repository_root: Path
    manifest_path: Path
    manifest: Mapping[str, Any]
    dataset_path: Path
    exclusions_path: Path
    selected_events_path: Path
    selected_markets_path: Path
    rows: tuple[dict[str, str], ...]
    locked_test_market_tickers: frozenset[str]
    request_plan: tuple[OutcomeRequest, ...]
    structural_role_by_market: Mapping[str, str]


@dataclass(frozen=True)
class LabeledObservation:
    partition: str
    state_id: str
    event_ticker: str
    market_ticker: str
    utc_week_start: str
    event_close_time_utc: str
    time_to_close_seconds: float
    strike_dollars: float
    event_row_weight: float
    outcome: int
    q_market: float
    market_logit: float
    strike_log_ratio: float
    time_log1p_hours: float

    @property
    def x(self) -> tuple[float, float, float, float]:
        return (1.0, self.market_logit, self.strike_log_ratio, self.time_log1p_hours)


@dataclass(frozen=True)
class CandidateFit:
    lambda_value: Decimal
    coefficients: tuple[float, float, float, float]
    iterations: int
    converged: bool
    train_objective: float


@dataclass(frozen=True)
class MetricPair:
    log_loss: float
    brier: float


@dataclass(frozen=True)
class CandidateBEvaluation:
    fits: tuple[CandidateFit, ...]
    selected_fit: CandidateFit
    raw_train: MetricPair
    raw_validation: MetricPair
    candidate_train: MetricPair
    candidate_validation: MetricPair
    validation_gate_passed: bool
    prediction_rows: tuple[dict[str, str], ...]
    calibration_rows: tuple[dict[str, str], ...]
    slice_rows: tuple[dict[str, str], ...]
    coefficient_rows: tuple[dict[str, str], ...]
    lambda_score_rows: tuple[dict[str, str], ...]
    summary: dict[str, Any]


def _error(message: str) -> None:
    raise KxbtcdCandidateBEvaluationError(message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be a non-empty string")
    return value.strip()


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KxbtcdCandidateBEvaluationError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _float(value: Any, name: str) -> float:
    result = float(_decimal(value, name))
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _float_text(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return format(value, ".17g")


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                _error(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise KxbtcdCandidateBEvaluationError(f"could not read CSV {path}: {exc}") from exc


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateBEvaluationError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(parsed, Mapping):
        _error(f"JSON root must be an object: {path}")
    return parsed


def _find_exact_manifest(repo: Path) -> Path:
    root = repo / "data" / "manifests"
    candidates = [
        path
        for path in root.rglob(f"{FROZEN_PREOUTCOME_RUN_ID}.json")
        if path.is_file()
    ]
    if len(candidates) != 1:
        _error(
            "expected exactly one manifest for the frozen Checkpoint-12 run "
            f"{FROZEN_PREOUTCOME_RUN_ID}; found {len(candidates)}"
        )
    return candidates[0]


def _artifact_from_manifest(
    *,
    repo: Path,
    manifest: Mapping[str, Any],
    filename: str,
    required: bool = True,
) -> Path | None:
    matches: list[Path] = []
    files = manifest.get("files")
    if not isinstance(files, list):
        _error("frozen pre-outcome manifest has no file list")
    for descriptor in files:
        if not isinstance(descriptor, Mapping):
            continue
        raw_path = descriptor.get("path")
        if not isinstance(raw_path, Mapping):
            continue
        path_value = raw_path.get("value")
        if not isinstance(path_value, str):
            continue
        if Path(path_value).name == filename:
            matches.append(resolve_stored_path(raw_path, repo))
    if not matches and not required:
        return None
    if len(matches) != 1:
        _error(f"expected exactly one frozen artifact named {filename}; found {len(matches)}")
    return matches[0]


def _assert_frozen_contract_identities() -> None:
    if candidate_b_spec_fingerprint() != FROZEN_CANDIDATE_B_SPEC_FINGERPRINT:
        _error("Candidate-B specification fingerprint changed from the Checkpoint-12 freeze")
    if dataset_design_fingerprint() != FROZEN_DATASET_DESIGN_FINGERPRINT:
        _error("pre-outcome dataset design fingerprint changed from the Checkpoint-12 freeze")
    if materialization_fingerprint() != FROZEN_MATERIALIZATION_FINGERPRINT:
        _error("materialization fingerprint changed from the Checkpoint-12 freeze")
    if MATERIALIZATION_CONTRACT_VERSION != "kxbtcd_preoutcome_materialization.v3":
        _error("materialization contract is not frozen v3")
    if tuple(L2_PENALTY_GRID) != (
        Decimal("0.01"),
        Decimal("0.1"),
        Decimal("1"),
        Decimal("10"),
    ):
        _error("Candidate-B lambda grid changed")


def load_frozen_preoutcome_dataset(
    repository_root: str | Path = ".",
) -> FrozenPreoutcomeDataset:
    """Load and validate the exact Checkpoint-12 frozen dataset.

    The generic run-manifest validator is executed before the dataset is read for
    modeling. This catches byte-level artifact changes, missing artifacts, and
    manifest inconsistencies. The function then verifies the experiment-specific
    fingerprints, row/event counts, partition separation, and event weights.
    """

    _assert_frozen_contract_identities()
    repo = Path(repository_root).resolve()
    manifest_path = _find_exact_manifest(repo)
    try:
        validated = validate_run_manifest(manifest_path, repository_root=repo)
    except RunValidationError as exc:
        raise KxbtcdCandidateBEvaluationError(
            f"frozen Checkpoint-12 run manifest failed integrity validation: {exc}"
        ) from exc
    if validated.get("run_id") != FROZEN_PREOUTCOME_RUN_ID:
        _error("validated manifest run ID mismatch")

    manifest = _load_json(manifest_path)
    if manifest.get("run_id") != FROZEN_PREOUTCOME_RUN_ID:
        _error("frozen manifest run ID mismatch")
    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != "collect_kxbtcd_preoutcome_dataset":
        _error("frozen manifest collector identity mismatch")
    if manifest.get("status") != "completed":
        _error("frozen pre-outcome run is not completed")

    result = manifest.get("result")
    if not isinstance(result, Mapping):
        _error("frozen pre-outcome manifest result is missing")
    if result.get("outcomes_materialized") is not False:
        _error("Checkpoint-12 manifest does not prove outcome-blind materialization")
    if result.get("model_fit_performed") is not False:
        _error("Checkpoint-12 manifest unexpectedly records a model fit")
    dataset_summary = result.get("dataset")
    split_summary = result.get("split")
    if not isinstance(dataset_summary, Mapping) or not isinstance(split_summary, Mapping):
        _error("Checkpoint-12 manifest is missing dataset/split summaries")
    if dataset_summary.get("dataset_fingerprint") != FROZEN_DATASET_FINGERPRINT:
        _error("Checkpoint-12 manifest dataset fingerprint mismatch")
    if split_summary.get("split_fingerprint") != FROZEN_SPLIT_FINGERPRINT:
        _error("Checkpoint-12 manifest split fingerprint mismatch")
    if int(dataset_summary.get("eligible_row_count", -1)) != EXPECTED_ELIGIBLE_ROWS:
        _error("Checkpoint-12 manifest eligible row count mismatch")
    if int(dataset_summary.get("unique_event_count", -1)) != EXPECTED_UNIQUE_EVENTS:
        _error("Checkpoint-12 manifest unique event count mismatch")

    expected_dataset_name = f"{FROZEN_PREOUTCOME_RUN_ID}_kxbtcd_preoutcome_dataset.csv"
    expected_exclusions_name = f"{FROZEN_PREOUTCOME_RUN_ID}_kxbtcd_preoutcome_exclusions.csv"
    expected_selected_events_name = f"{FROZEN_PREOUTCOME_RUN_ID}_kxbtcd_selected_events.csv"
    expected_selected_markets_name = f"{FROZEN_PREOUTCOME_RUN_ID}_kxbtcd_selected_markets.csv"
    dataset_path = _artifact_from_manifest(
        repo=repo, manifest=manifest, filename=expected_dataset_name, required=True
    )
    exclusions_path = _artifact_from_manifest(
        repo=repo, manifest=manifest, filename=expected_exclusions_name, required=True
    )
    selected_events_path = _artifact_from_manifest(
        repo=repo,
        manifest=manifest,
        filename=expected_selected_events_name,
        required=True,
    )
    selected_markets_path = _artifact_from_manifest(
        repo=repo,
        manifest=manifest,
        filename=expected_selected_markets_name,
        required=True,
    )
    assert dataset_path is not None
    assert exclusions_path is not None
    assert selected_events_path is not None
    assert selected_markets_path is not None
    rows = _read_csv(dataset_path)
    if len(rows) != EXPECTED_ELIGIBLE_ROWS:
        _error(f"frozen dataset has {len(rows)} rows; expected {EXPECTED_ELIGIBLE_ROWS}")

    expected_fields = tuple(DATASET_ROW_FIELDS)
    seen_states: set[str] = set()
    event_partition: dict[str, str] = {}
    market_partition: dict[str, str] = {}
    events_by_partition = {key: set() for key in EXPECTED_PARTITION_EVENT_COUNTS}
    rows_by_partition = {key: 0 for key in EXPECTED_PARTITION_ROW_COUNTS}
    weight_sums: dict[str, Decimal] = {}

    for index, row in enumerate(rows):
        if tuple(row.keys()) != expected_fields:
            missing = sorted(set(expected_fields) - set(row))
            extra = sorted(set(row) - set(expected_fields))
            _error(
                f"frozen dataset row {index} schema/order mismatch; "
                f"missing={missing}, extra={extra}"
            )
        leaked = FORBIDDEN_PREOUTCOME_FIELDS.intersection(row)
        if leaked:
            _error(f"frozen dataset row {index} contains forbidden outcome fields: {sorted(leaked)}")
        if row["dataset_fingerprint"] != FROZEN_DATASET_FINGERPRINT:
            _error(f"frozen dataset row {index} dataset fingerprint mismatch")
        if row["split_fingerprint"] != FROZEN_SPLIT_FINGERPRINT:
            _error(f"frozen dataset row {index} split fingerprint mismatch")
        if row["candidate_b_spec_fingerprint"] != FROZEN_CANDIDATE_B_SPEC_FINGERPRINT:
            _error(f"frozen dataset row {index} Candidate-B fingerprint mismatch")
        if row["dataset_design_fingerprint"] != FROZEN_DATASET_DESIGN_FINGERPRINT:
            _error(f"frozen dataset row {index} dataset-design fingerprint mismatch")

        state_id = _text(row["state_id"], f"rows[{index}].state_id")
        if state_id in seen_states:
            _error(f"duplicate state_id in frozen dataset: {state_id}")
        seen_states.add(state_id)
        partition = _text(row["partition"], f"rows[{index}].partition")
        if partition not in EXPECTED_PARTITION_ROW_COUNTS:
            _error(f"unexpected partition in frozen dataset: {partition!r}")
        event = _text(row["event_ticker"], f"rows[{index}].event_ticker")
        market = _text(row["market_ticker"], f"rows[{index}].market_ticker")
        previous = event_partition.setdefault(event, partition)
        if previous != partition:
            _error(f"event {event} appears in multiple partitions")
        previous_market = market_partition.setdefault(market, partition)
        if previous_market != partition:
            _error(f"market {market} appears in multiple partitions")
        events_by_partition[partition].add(event)
        rows_by_partition[partition] += 1

        q_market = _decimal(row["q_market"], f"rows[{index}].q_market")
        if q_market < 0 or q_market > 1:
            _error(f"rows[{index}].q_market is outside [0,1]")
        weight = _decimal(row["event_row_weight"], f"rows[{index}].event_row_weight")
        if weight <= 0:
            _error(f"rows[{index}].event_row_weight must be positive")
        weight_sums[event] = weight_sums.get(event, Decimal("0")) + weight

    for partition, expected in EXPECTED_PARTITION_ROW_COUNTS.items():
        if rows_by_partition[partition] != expected:
            _error(
                f"frozen {partition} row count changed: "
                f"{rows_by_partition[partition]} != {expected}"
            )
    for partition, expected in EXPECTED_PARTITION_EVENT_COUNTS.items():
        observed = len(events_by_partition[partition])
        if observed != expected:
            _error(f"frozen {partition} event count changed: {observed} != {expected}")
    if len(event_partition) != EXPECTED_UNIQUE_EVENTS:
        _error("frozen unique event count changed")
    if set(events_by_partition["train"]) & set(events_by_partition["validation"]):
        _error("train/validation event overlap")
    if set(events_by_partition["train"]) & set(events_by_partition["locked_test"]):
        _error("train/locked-test event overlap")
    if set(events_by_partition["validation"]) & set(events_by_partition["locked_test"]):
        _error("validation/locked-test event overlap")
    tolerance = Decimal("1e-24")
    for event, total in weight_sums.items():
        if abs(total - Decimal("1")) > tolerance:
            _error(f"event-row weights for {event} do not sum to one: {total}")

    # Build the deny-set from the complete selected-event/selected-market artifacts,
    # not only from eligible dataset rows. This covers selected locked-test
    # contracts whose quote anchors happened to yield zero modeling rows.
    selected_event_partition: dict[str, str] = {}
    for index, row in enumerate(_read_csv(selected_events_path)):
        event = _text(row.get("event_ticker"), f"selected_events[{index}].event_ticker")
        partition = _text(row.get("partition"), f"selected_events[{index}].partition")
        if partition not in EXPECTED_PARTITION_ROW_COUNTS:
            _error(f"selected event {event} has unexpected partition {partition!r}")
        previous = selected_event_partition.setdefault(event, partition)
        if previous != partition:
            _error(f"selected event {event} appears in multiple partitions")
        if event in event_partition and event_partition[event] != partition:
            _error(f"selected-event partition disagrees with dataset for {event}")

    structural_role_by_market: dict[str, str] = {}
    locked_market_set: set[str] = {
        market for market, partition in market_partition.items() if partition == "locked_test"
    }
    for index, row in enumerate(_read_csv(selected_markets_path)):
        market = _text(row.get("market_ticker"), f"selected_markets[{index}].market_ticker")
        event = _text(row.get("event_ticker"), f"selected_markets[{index}].event_ticker")
        role = _text(row.get("structural_role"), f"selected_markets[{index}].structural_role")
        previous_role = structural_role_by_market.setdefault(market, role)
        if previous_role != role:
            _error(f"market {market} has conflicting structural roles")
        selected_partition = selected_event_partition.get(event)
        if selected_partition is None:
            _error(f"selected market {market} references unknown selected event {event}")
        if selected_partition == "locked_test":
            locked_market_set.add(market)
    locked_markets = frozenset(locked_market_set)

    allowed_requests = tuple(
        OutcomeRequest(partition=partition, event_ticker=event, market_ticker=market)
        for (event, market), partition in sorted(
            {
                (row["event_ticker"], row["market_ticker"]): row["partition"]
                for row in rows
                if row["partition"] in {"train", "validation"}
            }.items(),
            key=lambda item: (item[1], item[0][0], item[0][1]),
        )
    )
    allowed_markets = {item.market_ticker for item in allowed_requests}
    if allowed_markets & locked_markets:
        _error("outcome allow-list overlaps the locked-test deny-list")
    if any(item.partition == "locked_test" for item in allowed_requests):
        _error("locked-test market leaked into outcome request plan")

    return FrozenPreoutcomeDataset(
        repository_root=repo,
        manifest_path=manifest_path,
        manifest=manifest,
        dataset_path=dataset_path,
        exclusions_path=exclusions_path,
        selected_events_path=selected_events_path,
        selected_markets_path=selected_markets_path,
        rows=tuple(rows),
        locked_test_market_tickers=locked_markets,
        request_plan=allowed_requests,
        structural_role_by_market=structural_role_by_market,
    )


def collect_train_validation_outcomes(
    client: RawFirstJsonClient,
    *,
    frozen: FrozenPreoutcomeDataset,
    existing_outcomes: Sequence[Mapping[str, str]] = (),
    on_outcome: Any | None = None,
) -> tuple[dict[str, str], ...]:
    """Collect only missing train/validation outcomes from exact market endpoints.

    ``existing_outcomes`` enables safe continuation after a partial prior run.
    Existing labels are validated first and never re-requested. The callback, if
    supplied, is invoked after each newly validated outcome so a CLI can append a
    durable progress journal before proceeding to the next market.
    """

    existing = _validate_outcomes(existing_outcomes, frozen=frozen, require_complete=False)
    by_market = {row["market_ticker"]: dict(row) for row in existing}
    planned = {item.market_ticker: item for item in frozen.request_plan}

    for item in frozen.request_plan:
        if item.market_ticker in by_market:
            continue
        if item.market_ticker in frozen.locked_test_market_tickers:
            _error(f"refusing to request locked-test market {item.market_ticker}")
        response = client.get_json(f"/historical/markets/{item.market_ticker}")
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            _error(f"outcome response for {item.market_ticker} missing market object")
        returned_ticker = _text(market.get("ticker"), "returned market ticker")
        if returned_ticker != item.market_ticker:
            _error(
                f"outcome response ticker mismatch: expected {item.market_ticker}, "
                f"got {returned_ticker}"
            )
        returned_event = _text(market.get("event_ticker"), "returned event_ticker")
        if returned_event != item.event_ticker:
            _error(
                f"outcome response event mismatch for {item.market_ticker}: "
                f"expected {item.event_ticker}, got {returned_event}"
            )
        status = _text(market.get("status"), "market status").lower()
        if status != "finalized":
            _error(f"market {item.market_ticker} is not finalized: {status}")
        result_text = _text(market.get("result"), "market result").lower()
        if result_text == "yes":
            outcome = "1"
        elif result_text == "no":
            outcome = "0"
        else:
            _error(
                f"market {item.market_ticker} has unsupported finalized result {result_text!r}"
            )
        row = {
            "schema_version": OUTCOME_SCHEMA_VERSION,
            "model_id": CANDIDATE_B_MODEL_ID,
            "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
            "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
            "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
            "candidate_b_spec_fingerprint": FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
            "partition": item.partition,
            "event_ticker": item.event_ticker,
            "market_ticker": item.market_ticker,
            "raw_source": _text(response.raw_record.source, "raw source"),
            "raw_session_id": _text(response.raw_record.session_id, "raw session_id"),
            "raw_request_id": _text(response.raw_record.request_id, "raw request_id"),
            "market_status": status,
            "result_text": result_text,
            "outcome": outcome,
        }
        _validate_outcomes([row], frozen=frozen, require_complete=False)
        by_market[item.market_ticker] = row
        if on_outcome is not None:
            on_outcome(dict(row))

    rows = tuple(by_market[key] for key in sorted(by_market))
    _validate_outcomes(rows, frozen=frozen, require_complete=True)
    if set(by_market) != set(planned):
        _error("outcome collection set differs from exact train/validation request plan")
    return rows


def _validate_outcomes(
    outcomes: Sequence[Mapping[str, str]],
    *,
    frozen: FrozenPreoutcomeDataset,
    require_complete: bool,
) -> tuple[dict[str, str], ...]:
    planned = {item.market_ticker: item for item in frozen.request_plan}
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, source in enumerate(outcomes):
        row = dict(source)
        missing = set(OUTCOME_FIELDS) - set(row)
        extra = set(row) - set(OUTCOME_FIELDS)
        if missing or extra:
            _error(
                f"outcome row {index} schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
            )
        if row["schema_version"] != OUTCOME_SCHEMA_VERSION:
            _error(f"outcome row {index} schema version mismatch")
        if row["model_id"] != CANDIDATE_B_MODEL_ID:
            _error(f"outcome row {index} model ID mismatch")
        if row["preoutcome_run_id"] != FROZEN_PREOUTCOME_RUN_ID:
            _error(f"outcome row {index} pre-outcome run mismatch")
        if row["dataset_fingerprint"] != FROZEN_DATASET_FINGERPRINT:
            _error(f"outcome row {index} dataset fingerprint mismatch")
        if row["split_fingerprint"] != FROZEN_SPLIT_FINGERPRINT:
            _error(f"outcome row {index} split fingerprint mismatch")
        if row["candidate_b_spec_fingerprint"] != FROZEN_CANDIDATE_B_SPEC_FINGERPRINT:
            _error(f"outcome row {index} Candidate-B fingerprint mismatch")
        market = _text(row["market_ticker"], f"outcomes[{index}].market_ticker")
        if market in seen:
            _error(f"duplicate outcome for market {market}")
        seen.add(market)
        if market in frozen.locked_test_market_tickers:
            _error(f"locked-test outcome materialized for {market}")
        plan = planned.get(market)
        if plan is None:
            _error(f"unplanned outcome market {market}")
        if row["partition"] != plan.partition:
            _error(f"outcome partition mismatch for {market}")
        if row["event_ticker"] != plan.event_ticker:
            _error(f"outcome event mismatch for {market}")
        if row["market_status"] != "finalized":
            _error(f"outcome market {market} is not finalized")
        result_text = row["result_text"]
        outcome = row["outcome"]
        if (result_text, outcome) not in {("yes", "1"), ("no", "0")}:
            _error(f"outcome/result mismatch for {market}")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            _text(row[field], f"outcomes[{index}].{field}")
        normalized.append(row)
    if require_complete and seen != set(planned):
        missing = sorted(set(planned) - seen)
        _error(
            f"train/validation outcome set is incomplete: missing {len(missing)} markets; "
            f"first={missing[:5]}"
        )
    return tuple(normalized)


def attach_train_validation_labels(
    *,
    frozen: FrozenPreoutcomeDataset,
    outcomes: Sequence[Mapping[str, str]],
) -> tuple[LabeledObservation, ...]:
    validated = _validate_outcomes(outcomes, frozen=frozen, require_complete=True)
    label_by_market = {row["market_ticker"]: int(row["outcome"]) for row in validated}
    observations: list[LabeledObservation] = []
    for index, row in enumerate(frozen.rows):
        partition = row["partition"]
        if partition == "locked_test":
            continue
        if partition not in {"train", "validation"}:
            _error(f"unexpected modeling partition {partition!r}")
        market = row["market_ticker"]
        if market not in label_by_market:
            _error(f"missing attached label for {market}")
        observations.append(
            LabeledObservation(
                partition=partition,
                state_id=row["state_id"],
                event_ticker=row["event_ticker"],
                market_ticker=market,
                utc_week_start=row["utc_week_start"],
                event_close_time_utc=row["event_close_time_utc"],
                time_to_close_seconds=_float(
                    row["time_to_close_seconds"], f"rows[{index}].time_to_close_seconds"
                ),
                strike_dollars=_float(row["strike_dollars"], f"rows[{index}].strike_dollars"),
                event_row_weight=_float(
                    row["event_row_weight"], f"rows[{index}].event_row_weight"
                ),
                outcome=label_by_market[market],
                q_market=_float(row["q_market"], f"rows[{index}].q_market"),
                market_logit=_float(
                    row["candidate_b_market_logit"], f"rows[{index}].market_logit"
                ),
                strike_log_ratio=_float(
                    row["candidate_b_strike_log_ratio"],
                    f"rows[{index}].strike_log_ratio",
                ),
                time_log1p_hours=_float(
                    row["candidate_b_time_log1p_hours"],
                    f"rows[{index}].time_log1p_hours",
                ),
            )
        )
    observed_rows = {
        key: sum(1 for row in observations if row.partition == key)
        for key in ("train", "validation")
    }
    if observed_rows["train"] != EXPECTED_PARTITION_ROW_COUNTS["train"]:
        _error("labeled train row count mismatch")
    if observed_rows["validation"] != EXPECTED_PARTITION_ROW_COUNTS["validation"]:
        _error("labeled validation row count mismatch")
    return tuple(observations)


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _softplus(z: float) -> float:
    if z > 0:
        return z + math.log1p(math.exp(-z))
    return math.log1p(math.exp(z))


def _log_loss_from_z(z: float, y: int) -> float:
    return _softplus(z) - float(y) * z


def _probability_log_loss(p: float, y: int) -> float:
    if not 0.0 <= p <= 1.0:
        _error(f"probability outside [0,1]: {p}")
    if p == 0.0:
        return 0.0 if y == 0 else math.inf
    if p == 1.0:
        return 0.0 if y == 1 else math.inf
    return -(y * math.log(p) + (1 - y) * math.log1p(-p))


def _brier(p: float, y: int) -> float:
    return (p - float(y)) ** 2


def _event_count(rows: Sequence[LabeledObservation]) -> int:
    return len({row.event_ticker for row in rows})


def _objective_gradient_hessian(
    rows: Sequence[LabeledObservation],
    beta: Sequence[float],
    lambda_value: float,
) -> tuple[float, list[float], list[list[float]]]:
    events = _event_count(rows)
    if events <= 0:
        _error("training partition contains no events")
    objective = 0.0
    gradient = [0.0] * 4
    hessian = [[0.0] * 4 for _ in range(4)]
    inv_events = 1.0 / float(events)
    for row in rows:
        x = row.x
        z = sum(beta[j] * x[j] for j in range(4))
        p = _sigmoid(z)
        weight = row.event_row_weight * inv_events
        objective += weight * _log_loss_from_z(z, row.outcome)
        residual = p - float(row.outcome)
        curvature = p * (1.0 - p)
        for j in range(4):
            gradient[j] += weight * residual * x[j]
            for k in range(j, 4):
                contribution = weight * curvature * x[j] * x[k]
                hessian[j][k] += contribution
                if k != j:
                    hessian[k][j] += contribution
    objective += 0.5 * lambda_value * sum(beta[j] * beta[j] for j in range(1, 4))
    for j in range(1, 4):
        gradient[j] += lambda_value * beta[j]
        hessian[j][j] += lambda_value
    return objective, gradient, hessian


def _solve_linear_system(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    n = len(rhs)
    augmented = [list(matrix[i]) + [float(rhs[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-15:
            _error("Candidate-B Newton Hessian is singular")
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for row in range(col + 1, n):
            factor = augmented[row][col] / pivot_value
            if factor == 0.0:
                continue
            for k in range(col, n + 1):
                augmented[row][k] -= factor * augmented[col][k]
    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        numerator = augmented[row][n] - sum(
            augmented[row][col] * solution[col] for col in range(row + 1, n)
        )
        denominator = augmented[row][row]
        if abs(denominator) < 1e-15:
            _error("Candidate-B Newton back-substitution is singular")
        solution[row] = numerator / denominator
    return solution


def fit_candidate_b(
    train_rows: Sequence[LabeledObservation],
    *,
    lambda_value: Decimal,
    max_iterations: int = 100,
    gradient_tolerance: float = 1e-8,
) -> CandidateFit:
    """Fit one frozen lambda with deterministic damped Newton updates.

    The objective is convex logistic loss plus L2 on beta1-beta3 only. Each row
    enters with its frozen event-row weight and the aggregate is divided by the
    number of training events, exactly reproducing mean-over-events loss.
    """

    if lambda_value not in L2_PENALTY_GRID:
        _error(f"lambda {lambda_value} is outside the frozen grid")
    rows = tuple(row for row in train_rows if row.partition == "train")
    if len(rows) != EXPECTED_PARTITION_ROW_COUNTS["train"]:
        _error("fit_candidate_b requires the exact frozen train row count")
    if _event_count(rows) != EXPECTED_PARTITION_EVENT_COUNTS["train"]:
        _error("fit_candidate_b requires the exact frozen train event count")

    lam = float(lambda_value)
    beta = [0.0, 0.0, 0.0, 0.0]
    objective, gradient, hessian = _objective_gradient_hessian(rows, beta, lam)
    for iteration in range(1, max_iterations + 1):
        gradient_norm = math.sqrt(sum(value * value for value in gradient))
        if gradient_norm <= gradient_tolerance:
            return CandidateFit(
                lambda_value=lambda_value,
                coefficients=tuple(beta),
                iterations=iteration - 1,
                converged=True,
                train_objective=objective,
            )
        newton_step = _solve_linear_system(hessian, gradient)
        directional = sum(gradient[j] * newton_step[j] for j in range(4))
        if not math.isfinite(directional) or directional <= 0:
            _error("Candidate-B Newton direction is not a descent direction")
        step_scale = 1.0
        accepted = False
        while step_scale >= 2.0 ** -40:
            candidate = [beta[j] - step_scale * newton_step[j] for j in range(4)]
            candidate_objective, candidate_gradient, candidate_hessian = (
                _objective_gradient_hessian(rows, candidate, lam)
            )
            if candidate_objective <= objective - 1e-4 * step_scale * directional:
                beta = candidate
                objective = candidate_objective
                gradient = candidate_gradient
                hessian = candidate_hessian
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            _error("Candidate-B damped Newton line search failed")
    _error(f"Candidate-B optimizer did not converge within {max_iterations} iterations")


def _predict(row: LabeledObservation, coefficients: Sequence[float]) -> float:
    z = sum(coefficients[j] * row.x[j] for j in range(4))
    return _sigmoid(z)


def event_weighted_metrics(
    rows: Sequence[LabeledObservation],
    probabilities: Sequence[float],
) -> MetricPair:
    if len(rows) != len(probabilities):
        _error("rows/probabilities length mismatch")
    events = _event_count(rows)
    if events <= 0:
        _error("metric rows contain no events")
    log_loss_total = 0.0
    brier_total = 0.0
    for row, p in zip(rows, probabilities):
        weight = row.event_row_weight / float(events)
        log_loss_total += weight * _probability_log_loss(p, row.outcome)
        brier_total += weight * _brier(p, row.outcome)
    return MetricPair(log_loss=log_loss_total, brier=brier_total)


def _slice_metrics(
    rows: Sequence[LabeledObservation],
    raw_probabilities: Sequence[float],
    candidate_probabilities: Sequence[float],
) -> tuple[MetricPair, MetricPair]:
    """Equal-weight events inside a diagnostic slice.

    We intentionally recompute within-event row weights for the slice instead of
    reusing full-dataset event_row_weight. This makes each represented event
    contribute one unit inside that slice, matching the top-level evaluation
    philosophy.
    """

    if not rows:
        _error("cannot score an empty diagnostic slice")
    if len(rows) != len(raw_probabilities) or len(rows) != len(candidate_probabilities):
        _error("diagnostic slice lengths differ")
    indices_by_event: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        indices_by_event.setdefault(row.event_ticker, []).append(index)
    raw_event_losses: list[float] = []
    candidate_event_losses: list[float] = []
    raw_event_briers: list[float] = []
    candidate_event_briers: list[float] = []
    for event in sorted(indices_by_event):
        indices = indices_by_event[event]
        raw_event_losses.append(
            sum(_probability_log_loss(raw_probabilities[i], rows[i].outcome) for i in indices)
            / len(indices)
        )
        candidate_event_losses.append(
            sum(
                _probability_log_loss(candidate_probabilities[i], rows[i].outcome)
                for i in indices
            )
            / len(indices)
        )
        raw_event_briers.append(
            sum(_brier(raw_probabilities[i], rows[i].outcome) for i in indices) / len(indices)
        )
        candidate_event_briers.append(
            sum(_brier(candidate_probabilities[i], rows[i].outcome) for i in indices)
            / len(indices)
        )
    count = len(indices_by_event)
    return (
        MetricPair(
            log_loss=sum(raw_event_losses) / count,
            brier=sum(raw_event_briers) / count,
        ),
        MetricPair(
            log_loss=sum(candidate_event_losses) / count,
            brier=sum(candidate_event_briers) / count,
        ),
    )


def _calibration_rows(
    *,
    partition: str,
    model_name: str,
    rows: Sequence[LabeledObservation],
    probabilities: Sequence[float],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for bin_index in range(10):
        lower = float(CALIBRATION_BIN_EDGES[bin_index])
        upper = float(CALIBRATION_BIN_EDGES[bin_index + 1])
        selected = [
            i
            for i, p in enumerate(probabilities)
            if p >= lower and (p < upper or (bin_index == 9 and p <= upper))
        ]
        if not selected:
            continue
        weight_sum = sum(rows[i].event_row_weight for i in selected)
        if weight_sum <= 0:
            _error("calibration bin has non-positive weight")
        mean_prediction = sum(
            rows[i].event_row_weight * probabilities[i] for i in selected
        ) / weight_sum
        observed_rate = sum(
            rows[i].event_row_weight * rows[i].outcome for i in selected
        ) / weight_sum
        output.append(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "model_id": CANDIDATE_B_MODEL_ID,
                "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                "partition": partition,
                "model": model_name,
                "bin_lower_inclusive": _float_text(lower),
                "bin_upper_inclusive": _float_text(upper),
                "row_count": str(len(selected)),
                "event_count": str(len({rows[i].event_ticker for i in selected})),
                "event_weight_sum": _float_text(weight_sum),
                "event_weighted_mean_prediction": _float_text(mean_prediction),
                "event_weighted_observed_rate": _float_text(observed_rate),
            }
        )
    return output


def _diagnostic_slice_rows(
    *,
    partition: str,
    rows: Sequence[LabeledObservation],
    raw_probabilities: Sequence[float],
    candidate_probabilities: Sequence[float],
    structural_role_by_market: Mapping[str, str],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []

    def emit(slice_type: str, key_by_index: Mapping[int, str]) -> None:
        keys = sorted(set(key_by_index.values()))
        for key in keys:
            indices = [i for i, value in key_by_index.items() if value == key]
            slice_rows = [rows[i] for i in indices]
            raw = [raw_probabilities[i] for i in indices]
            candidate = [candidate_probabilities[i] for i in indices]
            raw_metrics, candidate_metrics = _slice_metrics(slice_rows, raw, candidate)
            output.append(
                {
                    "schema_version": SLICE_SCORE_SCHEMA_VERSION,
                    "model_id": CANDIDATE_B_MODEL_ID,
                    "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                    "partition": partition,
                    "slice_type": slice_type,
                    "slice_value": key,
                    "row_count": str(len(indices)),
                    "event_count": str(len({row.event_ticker for row in slice_rows})),
                    "raw_event_weighted_log_loss": _float_text(raw_metrics.log_loss),
                    "candidate_event_weighted_log_loss": _float_text(candidate_metrics.log_loss),
                    "delta_log_loss_raw_minus_candidate": _float_text(
                        raw_metrics.log_loss - candidate_metrics.log_loss
                    ),
                    "raw_event_weighted_brier": _float_text(raw_metrics.brier),
                    "candidate_event_weighted_brier": _float_text(candidate_metrics.brier),
                    "delta_brier_raw_minus_candidate": _float_text(
                        raw_metrics.brier - candidate_metrics.brier
                    ),
                }
            )

    emit(
        "time_to_close_seconds",
        {i: str(int(round(row.time_to_close_seconds))) for i, row in enumerate(rows)},
    )
    roles = {
        i: structural_role_by_market[row.market_ticker]
        for i, row in enumerate(rows)
        if row.market_ticker in structural_role_by_market
    }
    if roles:
        emit("structural_strike_role", roles)
    return output


def evaluate_candidate_b(
    *,
    frozen: FrozenPreoutcomeDataset,
    outcomes: Sequence[Mapping[str, str]],
) -> CandidateBEvaluation:
    observations = attach_train_validation_labels(frozen=frozen, outcomes=outcomes)
    train = tuple(row for row in observations if row.partition == "train")
    validation = tuple(row for row in observations if row.partition == "validation")

    raw_train_probabilities = [row.q_market for row in train]
    raw_validation_probabilities = [row.q_market for row in validation]
    raw_train = event_weighted_metrics(train, raw_train_probabilities)
    raw_validation = event_weighted_metrics(validation, raw_validation_probabilities)

    fits: list[CandidateFit] = []
    validation_losses_by_lambda: dict[Decimal, str] = {}
    metrics_by_lambda: dict[Decimal, tuple[MetricPair, MetricPair]] = {}
    predictions_by_lambda: dict[Decimal, tuple[list[float], list[float]]] = {}
    for lambda_value in L2_PENALTY_GRID:
        fit = fit_candidate_b(train, lambda_value=lambda_value)
        train_predictions = [_predict(row, fit.coefficients) for row in train]
        validation_predictions = [_predict(row, fit.coefficients) for row in validation]
        train_metrics = event_weighted_metrics(train, train_predictions)
        validation_metrics = event_weighted_metrics(validation, validation_predictions)
        fits.append(fit)
        metrics_by_lambda[lambda_value] = (train_metrics, validation_metrics)
        predictions_by_lambda[lambda_value] = (train_predictions, validation_predictions)
        validation_losses_by_lambda[lambda_value] = _float_text(validation_metrics.log_loss)

    selected_lambda = select_candidate_b_lambda(validation_losses_by_lambda)
    selected_fit = next(fit for fit in fits if fit.lambda_value == selected_lambda)
    candidate_train, candidate_validation = metrics_by_lambda[selected_lambda]
    selected_train_predictions, selected_validation_predictions = predictions_by_lambda[
        selected_lambda
    ]
    gate = candidate_b_validation_gate(
        raw_midpoint_event_weighted_log_loss=_float_text(raw_validation.log_loss),
        candidate_b_event_weighted_log_loss=_float_text(candidate_validation.log_loss),
    )

    coefficient_rows: list[dict[str, str]] = []
    lambda_score_rows: list[dict[str, str]] = []
    for fit in fits:
        train_metrics, validation_metrics = metrics_by_lambda[fit.lambda_value]
        selected = fit.lambda_value == selected_lambda
        coefficient_rows.append(
            {
                "schema_version": COEFFICIENT_SCHEMA_VERSION,
                "model_id": CANDIDATE_B_MODEL_ID,
                "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                "lambda": _decimal_text(fit.lambda_value),
                "beta0": _float_text(fit.coefficients[0]),
                "beta1_market_logit": _float_text(fit.coefficients[1]),
                "beta2_strike_log_ratio": _float_text(fit.coefficients[2]),
                "beta3_time_log1p_hours": _float_text(fit.coefficients[3]),
                "iterations": str(fit.iterations),
                "converged": _bool_text(fit.converged),
                "train_objective": _float_text(fit.train_objective),
                "train_event_weighted_log_loss": _float_text(train_metrics.log_loss),
                "train_event_weighted_brier": _float_text(train_metrics.brier),
                "validation_event_weighted_log_loss": _float_text(validation_metrics.log_loss),
                "validation_event_weighted_brier": _float_text(validation_metrics.brier),
                "selected_lambda": _bool_text(selected),
            }
        )
        lambda_score_rows.append(
            {
                "schema_version": LAMBDA_SCORE_SCHEMA_VERSION,
                "model_id": CANDIDATE_B_MODEL_ID,
                "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                "lambda": _decimal_text(fit.lambda_value),
                "train_objective": _float_text(fit.train_objective),
                "train_event_weighted_log_loss": _float_text(train_metrics.log_loss),
                "train_event_weighted_brier": _float_text(train_metrics.brier),
                "validation_event_weighted_log_loss": _float_text(validation_metrics.log_loss),
                "validation_event_weighted_brier": _float_text(validation_metrics.brier),
                "validation_delta_log_loss_raw_minus_candidate": _float_text(
                    raw_validation.log_loss - validation_metrics.log_loss
                ),
                "validation_delta_brier_raw_minus_candidate": _float_text(
                    raw_validation.brier - validation_metrics.brier
                ),
                "selected_lambda": _bool_text(selected),
            }
        )

    prediction_rows: list[dict[str, str]] = []
    for partition, rows, candidate_predictions in (
        ("train", train, selected_train_predictions),
        ("validation", validation, selected_validation_predictions),
    ):
        for row, candidate_probability in zip(rows, candidate_predictions):
            prediction_rows.append(
                {
                    "schema_version": PREDICTION_SCHEMA_VERSION,
                    "model_id": CANDIDATE_B_MODEL_ID,
                    "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                    "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                    "partition": partition,
                    "state_id": row.state_id,
                    "event_ticker": row.event_ticker,
                    "market_ticker": row.market_ticker,
                    "utc_week_start": row.utc_week_start,
                    "event_close_time_utc": row.event_close_time_utc,
                    "time_to_close_seconds": _float_text(row.time_to_close_seconds),
                    "strike_dollars": _float_text(row.strike_dollars),
                    "event_row_weight": _float_text(row.event_row_weight),
                    "outcome": str(row.outcome),
                    "q_market": _float_text(row.q_market),
                    "candidate_b_probability": _float_text(candidate_probability),
                    "raw_log_loss": _float_text(
                        _probability_log_loss(row.q_market, row.outcome)
                    ),
                    "candidate_b_log_loss": _float_text(
                        _probability_log_loss(candidate_probability, row.outcome)
                    ),
                    "raw_brier": _float_text(_brier(row.q_market, row.outcome)),
                    "candidate_b_brier": _float_text(
                        _brier(candidate_probability, row.outcome)
                    ),
                }
            )

    calibration_rows: list[dict[str, str]] = []
    slice_rows: list[dict[str, str]] = []
    for partition, rows, raw_probabilities, candidate_probabilities in (
        ("train", train, raw_train_probabilities, selected_train_predictions),
        (
            "validation",
            validation,
            raw_validation_probabilities,
            selected_validation_predictions,
        ),
    ):
        calibration_rows.extend(
            _calibration_rows(
                partition=partition,
                model_name="raw_midpoint",
                rows=rows,
                probabilities=raw_probabilities,
            )
        )
        calibration_rows.extend(
            _calibration_rows(
                partition=partition,
                model_name="candidate_b",
                rows=rows,
                probabilities=candidate_probabilities,
            )
        )
        slice_rows.extend(
            _diagnostic_slice_rows(
                partition=partition,
                rows=rows,
                raw_probabilities=raw_probabilities,
                candidate_probabilities=candidate_probabilities,
                structural_role_by_market=frozen.structural_role_by_market,
            )
        )

    train_days = {row.event_close_time_utc[:10] for row in train}
    validation_days = {row.event_close_time_utc[:10] for row in validation}
    train_weeks = {row.utc_week_start for row in train}
    validation_weeks = {row.utc_week_start for row in validation}
    summary = {
        "schema_version": "kxbtcd_candidate_b_train_validation_summary.v1",
        "model_id": CANDIDATE_B_MODEL_ID,
        "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "candidate_b_spec_fingerprint": FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
        "train_event_count": _event_count(train),
        "train_row_count": len(train),
        "train_day_count": len(train_days),
        "train_week_count": len(train_weeks),
        "validation_event_count": _event_count(validation),
        "validation_row_count": len(validation),
        "validation_day_count": len(validation_days),
        "validation_week_count": len(validation_weeks),
        "raw_train_event_weighted_log_loss": _float_text(raw_train.log_loss),
        "raw_train_event_weighted_brier": _float_text(raw_train.brier),
        "raw_validation_event_weighted_log_loss": _float_text(raw_validation.log_loss),
        "raw_validation_event_weighted_brier": _float_text(raw_validation.brier),
        "selected_lambda": _decimal_text(selected_lambda),
        "candidate_train_event_weighted_log_loss": _float_text(candidate_train.log_loss),
        "candidate_train_event_weighted_brier": _float_text(candidate_train.brier),
        "candidate_validation_event_weighted_log_loss": _float_text(
            candidate_validation.log_loss
        ),
        "candidate_validation_event_weighted_brier": _float_text(
            candidate_validation.brier
        ),
        "validation_delta_log_loss_raw_minus_candidate": _float_text(
            raw_validation.log_loss - candidate_validation.log_loss
        ),
        "validation_delta_brier_raw_minus_candidate": _float_text(
            raw_validation.brier - candidate_validation.brier
        ),
        "validation_gate_rule": "candidate_log_loss_strictly_less_than_raw_midpoint_log_loss",
        "validation_gate_passed": gate,
        "locked_test_outcomes_opened": 0,
        "locked_test_evaluation_performed": False,
        "candidate_c_authorized": False,
        "class_weights_used": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }

    return CandidateBEvaluation(
        fits=tuple(fits),
        selected_fit=selected_fit,
        raw_train=raw_train,
        raw_validation=raw_validation,
        candidate_train=candidate_train,
        candidate_validation=candidate_validation,
        validation_gate_passed=gate,
        prediction_rows=tuple(prediction_rows),
        calibration_rows=tuple(calibration_rows),
        slice_rows=tuple(slice_rows),
        coefficient_rows=tuple(coefficient_rows),
        lambda_score_rows=tuple(lambda_score_rows),
        summary=summary,
    )


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows):
            missing = set(fields) - set(row)
            extra = set(row) - set(fields)
            if missing or extra:
                _error(
                    f"output row {index} for {path.name} has schema mismatch; "
                    f"missing={sorted(missing)}, extra={sorted(extra)}"
                )
            writer.writerow({field: row[field] for field in fields})


def initialize_outcome_journal(path: str | Path) -> Path:
    journal = Path(path)
    journal.parent.mkdir(parents=True, exist_ok=True)
    if journal.exists():
        existing = _read_csv(journal)
        if existing:
            _error(f"refusing to overwrite non-empty outcome journal {journal}")
        return journal
    _write_csv(journal, OUTCOME_FIELDS, ())
    return journal


def append_outcome_journal(path: str | Path, row: Mapping[str, Any]) -> None:
    journal = Path(path)
    missing = set(OUTCOME_FIELDS) - set(row)
    extra = set(row) - set(OUTCOME_FIELDS)
    if missing or extra:
        _error(
            f"outcome journal row schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    with journal.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(OUTCOME_FIELDS), lineterminator="\n")
        writer.writerow({field: row[field] for field in OUTCOME_FIELDS})
        handle.flush()
        # Deliberately rely on Python/OS flush here; raw source persistence remains
        # the immutable source of truth. The journal is a resumability aid.


def load_outcome_journal(
    path: str | Path,
    *,
    frozen: FrozenPreoutcomeDataset,
) -> tuple[dict[str, str], ...]:
    journal = Path(path)
    if not journal.exists():
        return ()
    rows = _read_csv(journal)
    return _validate_outcomes(rows, frozen=frozen, require_complete=False)


def write_candidate_b_evaluation(
    output_dir: str | Path,
    *,
    run_id: str,
    outcomes: Sequence[Mapping[str, str]],
    evaluation: CandidateBEvaluation,
    outcome_journal_path: str | Path | None = None,
) -> tuple[Path, ...]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    outcomes_path = root / f"{run_id}_kxbtcd_candidate_b_outcomes.csv"
    coefficients_path = root / f"{run_id}_kxbtcd_candidate_b_coefficients.csv"
    lambda_scores_path = root / f"{run_id}_kxbtcd_candidate_b_lambda_scores.csv"
    predictions_path = root / f"{run_id}_kxbtcd_candidate_b_predictions.csv"
    calibration_path = root / f"{run_id}_kxbtcd_candidate_b_calibration.csv"
    slices_path = root / f"{run_id}_kxbtcd_candidate_b_slices.csv"
    _write_csv(outcomes_path, OUTCOME_FIELDS, outcomes)
    _write_csv(coefficients_path, COEFFICIENT_FIELDS, evaluation.coefficient_rows)
    _write_csv(lambda_scores_path, LAMBDA_SCORE_FIELDS, evaluation.lambda_score_rows)
    _write_csv(predictions_path, PREDICTION_FIELDS, evaluation.prediction_rows)
    _write_csv(calibration_path, CALIBRATION_FIELDS, evaluation.calibration_rows)
    _write_csv(slices_path, SLICE_SCORE_FIELDS, evaluation.slice_rows)
    paths = [
        outcomes_path,
        coefficients_path,
        lambda_scores_path,
        predictions_path,
        calibration_path,
        slices_path,
    ]
    if outcome_journal_path is not None:
        journal = Path(outcome_journal_path)
        if journal.exists() and journal.resolve() not in {path.resolve() for path in paths}:
            paths.append(journal)
    return tuple(paths)


def outcome_request_summary(frozen: FrozenPreoutcomeDataset) -> dict[str, int]:
    by_partition = {"train": 0, "validation": 0}
    for item in frozen.request_plan:
        by_partition[item.partition] += 1
    return {
        "train_market_requests": by_partition["train"],
        "validation_market_requests": by_partition["validation"],
        "total_market_requests": len(frozen.request_plan),
        "locked_test_market_requests": 0,
        "locked_test_market_deny_count": len(frozen.locked_test_market_tickers),
    }


def frozen_design_summary(frozen: FrozenPreoutcomeDataset) -> dict[str, Any]:
    request_summary = outcome_request_summary(frozen)
    return {
        "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "preoutcome_manifest": str(frozen.manifest_path),
        "dataset_path": str(frozen.dataset_path),
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "candidate_b_spec_fingerprint": FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
        "materialization_fingerprint": FROZEN_MATERIALIZATION_FINGERPRINT,
        "materialization_contract": MATERIALIZATION_CONTRACT_VERSION,
        "train_events": EXPECTED_PARTITION_EVENT_COUNTS["train"],
        "validation_events": EXPECTED_PARTITION_EVENT_COUNTS["validation"],
        "locked_test_events": EXPECTED_PARTITION_EVENT_COUNTS["locked_test"],
        "train_rows": EXPECTED_PARTITION_ROW_COUNTS["train"],
        "validation_rows": EXPECTED_PARTITION_ROW_COUNTS["validation"],
        "locked_test_rows": EXPECTED_PARTITION_ROW_COUNTS["locked_test"],
        **request_summary,
        "locked_test_outcomes_opened": 0,
        "candidate_c_authorized": False,
        "execution_enabled": False,
    }


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_assert_frozen_contract_identities()

CP13_COLLECTOR_NAME = "collect_kxbtcd_candidate_b_train_validation"


def matching_prior_exposure_manifests(
    repository_root: str | Path = ".",
) -> tuple[Path, ...]:
    """Find any earlier CP13 run tied to this exact frozen experiment.

    A prior running, failed, or completed run can already have exposed some
    train/validation labels. Fresh collection must therefore stop and use the
    resume/recovery path rather than blindly re-requesting every market.
    """

    repo = Path(repository_root).resolve()
    root = repo / "data" / "manifests"
    matches: list[Path] = []
    if not root.exists():
        return ()
    for path in root.rglob("*.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, Mapping):
            continue
        collector = manifest.get("collector")
        if not isinstance(collector, Mapping) or collector.get("name") != CP13_COLLECTOR_NAME:
            continue
        arguments = manifest.get("arguments")
        if not isinstance(arguments, Mapping):
            continue
        if arguments.get("preoutcome_run_id") != FROZEN_PREOUTCOME_RUN_ID:
            continue
        if arguments.get("dataset_fingerprint") != FROZEN_DATASET_FINGERPRINT:
            continue
        if arguments.get("split_fingerprint") != FROZEN_SPLIT_FINGERPRINT:
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches, key=lambda path: path.stat().st_mtime_ns))


def _raw_paths_for_manifest(
    *,
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> tuple[Path, ...]:
    paths: set[Path] = set()
    files = manifest.get("files")
    if isinstance(files, list):
        for descriptor in files:
            if not isinstance(descriptor, Mapping) or descriptor.get("role") != "raw_api_archive":
                continue
            stored = descriptor.get("path")
            if isinstance(stored, Mapping):
                resolved = resolve_stored_path(stored, repository_root)
                if resolved.is_file():
                    paths.add(resolved)
    sessions = manifest.get("source_sessions")
    if isinstance(sessions, list):
        for session in sessions:
            if not isinstance(session, Mapping):
                continue
            session_id = session.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                continue
            for root in (
                repository_root / "data" / "raw" / "kalshi_rest",
                repository_root / "data" / "raw",
            ):
                if root.exists():
                    paths.update(path for path in root.rglob(f"{session_id}.jsonl") if path.is_file())
    return tuple(sorted(paths))


def recover_exposed_outcomes_from_manifest(
    *,
    frozen: FrozenPreoutcomeDataset,
    manifest_path: str | Path,
) -> tuple[dict[str, str], ...]:
    """Recover already-exposed train/validation labels from raw archives only.

    This performs zero API requests. It is safe to use before a resume run: every
    successfully exposed market recovered here is supplied as ``existing_outcomes``
    so the collector will not request it again.
    """

    path = Path(manifest_path).resolve()
    manifest = _load_json(path)
    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != CP13_COLLECTOR_NAME:
        _error("resume manifest is not a CP13 Candidate-B train/validation collector")
    status = manifest.get("status")
    if status == "completed":
        _error("resume manifest is already completed; do not duplicate a completed CP13 evaluation")
    if status not in {"running", "failed"}:
        _error(f"resume manifest has unsupported status {status!r}")
    arguments = manifest.get("arguments")
    if not isinstance(arguments, Mapping):
        _error("resume manifest has no arguments")
    expected_arguments = {
        "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "candidate_b_spec_fingerprint": FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
    }
    for key, expected in expected_arguments.items():
        if arguments.get(key) != expected:
            _error(f"resume manifest {key} mismatch")

    planned = {item.market_ticker: item for item in frozen.request_plan}
    recovered: dict[str, dict[str, str]] = {}
    raw_paths = _raw_paths_for_manifest(
        manifest=manifest, repository_root=frozen.repository_root
    )
    for raw_path in raw_paths:
        try:
            handle = raw_path.open("r", encoding="utf-8")
        except OSError as exc:
            raise KxbtcdCandidateBEvaluationError(
                f"could not open raw recovery archive {raw_path}: {exc}"
            ) from exc
        with handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise KxbtcdCandidateBEvaluationError(
                        f"invalid raw JSON at {raw_path}:{line_number}"
                    ) from exc
                if not isinstance(record, Mapping):
                    continue
                request = record.get("request")
                response = record.get("response")
                if not isinstance(request, Mapping) or not isinstance(response, Mapping):
                    continue
                request_path = request.get("path")
                if not isinstance(request_path, str) or not request_path.startswith(
                    "/historical/markets/"
                ):
                    continue
                ticker = request_path.rsplit("/", 1)[-1]
                plan = planned.get(ticker)
                if plan is None:
                    # Raw files can contain only this collector's session, but do
                    # not infer or accept any unplanned market result.
                    continue
                if ticker in frozen.locked_test_market_tickers:
                    _error(f"raw recovery found a locked-test request: {ticker}")
                if record.get("error") is not None:
                    continue
                try:
                    status_code = int(response.get("status_code"))
                except (TypeError, ValueError):
                    continue
                if status_code < 200 or status_code >= 300:
                    continue
                body_text = response.get("body_text")
                if not isinstance(body_text, str):
                    continue
                try:
                    payload = json.loads(body_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, Mapping):
                    continue
                market = payload.get("market")
                if not isinstance(market, Mapping):
                    continue
                returned_ticker = market.get("ticker")
                returned_event = market.get("event_ticker")
                status = str(market.get("status") or "").lower()
                result_text = str(market.get("result") or "").lower()
                if returned_ticker != ticker or returned_event != plan.event_ticker:
                    _error(f"raw recovery identity mismatch for {ticker}")
                if status != "finalized" or result_text not in {"yes", "no"}:
                    continue
                outcome = "1" if result_text == "yes" else "0"
                raw_source = _text(record.get("source"), "raw recovery source")
                raw_session = _text(record.get("session_id"), "raw recovery session_id")
                raw_request = _text(request.get("request_id"), "raw recovery request_id")
                row = {
                    "schema_version": OUTCOME_SCHEMA_VERSION,
                    "model_id": CANDIDATE_B_MODEL_ID,
                    "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
                    "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                    "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                    "candidate_b_spec_fingerprint": FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
                    "partition": plan.partition,
                    "event_ticker": plan.event_ticker,
                    "market_ticker": ticker,
                    "raw_source": raw_source,
                    "raw_session_id": raw_session,
                    "raw_request_id": raw_request,
                    "market_status": status,
                    "result_text": result_text,
                    "outcome": outcome,
                }
                previous = recovered.get(ticker)
                if previous is not None:
                    if previous["outcome"] != outcome or previous["result_text"] != result_text:
                        _error(f"conflicting recovered outcomes for {ticker}")
                    continue
                recovered[ticker] = row
    rows = tuple(recovered[key] for key in sorted(recovered))
    _validate_outcomes(rows, frozen=frozen, require_complete=False)
    return rows
