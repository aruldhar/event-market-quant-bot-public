"""Checkpoint 21M Candidate-E Entry Model v1 C1+C2 validation evaluator.

This module implements only the already-frozen D-021L-05 statistical gate.

Scientific invariants:
* the development-selected 21 residual coefficients are fixed;
* the development fit's 11-feature scaler is fixed;
* lambda remains 0.01 and is not searched or used for refitting here;
* C1+C2 feature eligibility and five 200-event blocks come only from the
  outcome-blind preparation freeze;
* Candidate-E is the mandatory benchmark;
* the exact finite Candidate-E latent logit sidecar is used as the fixed offset;
* historical probability endpoints are preserved; no clipping is introduced;
* no C3, protected reserve, Strategy-v1 P&L, or execution surface exists.

The real C1/C2 outcome files may be read only by the separately frozen evaluator
CLI after this implementation has been committed and pushed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_entry_model_v1 import (
    CONTINUOUS_FEATURES,
    MODEL_ID,
    PARAMETER_NAMES,
    EventEqualScaler,
    binary_log_loss_from_logit,
    canonical_rows_fingerprint,
    canonical_sha256,
    design_vector,
    stable_sigmoid,
)
from .kxbtcd_candidate_e_entry_model_v1_validation_preparation import (
    EVENT_MAP_FIELDS,
    FEATURE_FIELDS,
    OFFSET_FIELDS,
    VALIDATION_BLOCKS,
    build_validation_event_map,
    validate_feature_rows,
)

PARENT_COMMIT = "0094829553489130915ce65cfee24a48f382597b"

DEVELOPMENT_FREEZE_FINGERPRINT = (
    "a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e"
)
VALIDATION_PREPARATION_FINGERPRINT = (
    "25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22"
)
FEATURE_ROWS_FINGERPRINT = (
    "d5d70331d1ccf6ce823a9820bfefc9267db6f84b13bd0040133dfe759ffae228"
)
OFFSET_ROWS_FINGERPRINT = (
    "7fdc2127c081894be97a96c4c930c06634a96f19cf13d4fd18c5b95458c978c1"
)
EVENT_MAP_FINGERPRINT = (
    "682c3007e2c360d10aada786e83050516990c36c1de87d6988b70c49c38f4199"
)
EXPECTED_ENDPOINT_ROWS = 6
SELECTED_LAMBDA = 0.01

EXPECTED_VALIDATION_ROWS = 28894
EXPECTED_VALIDATION_EVENTS = 1000
EXPECTED_STAGE_ROWS = {"C1": 14887, "C2": 14007}
EXPECTED_STAGE_EVENTS = {"C1": 500, "C2": 500}
EXPECTED_STAGE_MARKETS = {"C1": 2491, "C2": 2441}
EVENTS_PER_BLOCK = 200

C1_RESULT_CLOSEOUT_FINGERPRINT = (
    "3a66e7d980334474d4d836f80bc2aca56932baab1040fa393dee9764a3ee737e"
)
C2_RESULT_CLOSEOUT_FINGERPRINT = (
    "5660e4d04856f534543f0fdd53a1b687b07666ffd52d59e8e80fcefe6ddc87cf"
)
C1_OUTCOMES_SHA256 = (
    "badefb7087de6b07a5c968b78564858e7e9c060652836aba7f366de0788a259b"
)
C2_OUTCOMES_SHA256 = (
    "6a898266ce961b3d812ac1e6c5b430a01e9449bb41d06a42e61e69d2fccf38e6"
)

CORE_SHA256 = (
    "ce54846f85f3d338bc0f3aadd64d8cc8b9828c0c2ac2b5454f97771ec1a89ee1"
)

IMPLEMENTATION_FREEZE_SCHEMA = (
    "kxbtcd_candidate_e_entry_model_v1_validation_implementation_freeze.v1"
)
IMPLEMENTATION_FREEZE_DEFAULT = Path(
    "configs/kxbtcd_candidate_e_entry_model_v1_validation_implementation_freeze.json"
)
ATTEMPT_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_validation_attempt.v1"
SCORED_ROW_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_validation_scored_row.v1"
EVENT_SCORE_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_validation_event_score.v1"
BLOCK_SCORE_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_validation_block_score.v1"
SUMMARY_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_validation_summary.v1"
RECEIPT_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_validation_receipt.v1"

IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_entry_model_v1_validation.py",
    "evaluate_kxbtcd_candidate_e_entry_model_v1_validation.py",
    "validate_kxbtcd_candidate_e_entry_model_v1_validation.py",
    "freeze_kxbtcd_candidate_e_entry_model_v1_validation_implementation.py",
    "validate_kxbtcd_candidate_e_entry_model_v1_validation_implementation_freeze.py",
)
DEPENDENCY_FILES = (
    "src/kxbtcd_candidate_e_entry_model_v1.py",
    "src/kxbtcd_candidate_e_entry_model_v1_validation_preparation.py",
)

SCORED_ROW_FIELDS = (
    "schema_version",
    "model_id",
    "validation_block",
    "stage",
    "state_id",
    "event_ticker",
    "market_ticker",
    "structural_role",
    "ttc_target_minutes",
    "outcome",
    "candidate_logit_offset",
    "candidate_probability",
    "model2_residual_logit",
    "model2_logit",
    "model2_probability",
    "candidate_log_loss",
    "model2_log_loss",
    "candidate_brier",
    "model2_brier",
)
EVENT_SCORE_FIELDS = (
    "schema_version",
    "model_id",
    "validation_block",
    "stage",
    "event_ticker",
    "row_count",
    "candidate_log_loss",
    "model2_log_loss",
    "candidate_minus_model2_log_loss",
    "candidate_brier",
    "model2_brier",
    "candidate_minus_model2_brier",
)
BLOCK_SCORE_FIELDS = (
    "schema_version",
    "model_id",
    "validation_block",
    "event_count",
    "candidate_log_loss",
    "model2_log_loss",
    "candidate_minus_model2_log_loss",
    "candidate_brier",
    "model2_brier",
    "candidate_minus_model2_brier",
    "model2_log_loss_win",
)


class ValidationEvaluationError(RuntimeError):
    """Raised whenever a frozen validation invariant fails closed."""


def _error(message: str) -> None:
    raise ValidationEvaluationError(message)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationEvaluationError(f"could not read JSON {target}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be object: {target}")
    return value


def write_json(path: str | Path, value: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temp.replace(target)


def read_csv(path: str | Path) -> list[dict[str, str]]:
    target = Path(path)
    try:
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                _error(f"{target.name}: empty CSV header")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise ValidationEvaluationError(f"could not read CSV {target}: {exc}") from exc


def write_csv(
    path: str | Path,
    fields: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for index, row in enumerate(rows):
            if set(row) != set(fields):
                _error(
                    f"output row[{index}] schema mismatch for {target.name}; "
                    f"missing={sorted(set(fields)-set(row))}, "
                    f"extra={sorted(set(row)-set(fields))}"
                )
            writer.writerow({field: row[field] for field in fields})
    temp.replace(target)


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationEvaluationError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _int01(value: Any, name: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationEvaluationError(f"{name} must be integer") from exc
    if result not in (0, 1) or str(value).strip() not in {
        "0", "1", "0.0", "1.0"
    }:
        _error(f"{name} must be binary 0/1")
    return result


def validate_development_freeze(
    document: Mapping[str, Any],
) -> tuple[tuple[float, ...], EventEqualScaler]:
    if document.get("schema_version") != (
        "kxbtcd_candidate_e_entry_model_v1_development_freeze.v1"
    ):
        _error("development freeze schema changed")
    if document.get("model_id") != MODEL_ID:
        _error("development freeze model id changed")
    if document.get("development_freeze_fingerprint") != DEVELOPMENT_FREEZE_FINGERPRINT:
        _error("development freeze fingerprint changed")

    selection = document.get("selection")
    if not isinstance(selection, Mapping):
        _error("development selection contract missing")
    if float(selection.get("selected_lambda")) != SELECTED_LAMBDA:
        _error("selected lambda changed")

    fit = document.get("full_development_fit")
    if not isinstance(fit, Mapping):
        _error("full development fit missing")
    if float(fit.get("lambda")) != SELECTED_LAMBDA:
        _error("full development fit lambda changed")

    coefficient_map = fit.get("coefficients")
    if not isinstance(coefficient_map, Mapping):
        _error("development coefficient map missing")
    if set(coefficient_map) != set(PARAMETER_NAMES):
        _error("development coefficient names changed")
    coefficients = tuple(
        _finite_float(coefficient_map[name], f"coefficient.{name}")
        for name in PARAMETER_NAMES
    )

    scaler_map = fit.get("scaler")
    if not isinstance(scaler_map, Mapping):
        _error("development scaler missing")
    if set(scaler_map) != set(CONTINUOUS_FEATURES):
        _error("development scaler feature set changed")
    means: list[float] = []
    stds: list[float] = []
    for name in CONTINUOUS_FEATURES:
        item = scaler_map.get(name)
        if not isinstance(item, Mapping):
            _error(f"development scaler entry missing for {name}")
        mean = _finite_float(item.get("mean"), f"scaler.{name}.mean")
        std = _finite_float(item.get("std"), f"scaler.{name}.std")
        if std <= 1e-12:
            _error(f"scaler.{name}.std <= 1e-12")
        means.append(mean)
        stds.append(std)

    return coefficients, EventEqualScaler(tuple(means), tuple(stds))


def validate_preparation_freeze(
    document: Mapping[str, Any],
) -> None:
    if document.get("schema_version") != (
        "kxbtcd_candidate_e_entry_model_v1_validation_preparation_freeze.v1"
    ):
        _error("validation preparation freeze schema changed")
    if document.get("model_id") != MODEL_ID:
        _error("validation preparation model id changed")
    if document.get("validation_preparation_fingerprint") != VALIDATION_PREPARATION_FINGERPRINT:
        _error("validation preparation fingerprint changed")
    if document.get("feature_rows_fingerprint") != FEATURE_ROWS_FINGERPRINT:
        _error("validation feature fingerprint changed")
    if document.get("validation_offset_rows_fingerprint") != OFFSET_ROWS_FINGERPRINT:
        _error("validation offset fingerprint changed")
    if document.get("validation_event_map_fingerprint") != EVENT_MAP_FINGERPRINT:
        _error("validation event-map fingerprint changed")
    if int(document.get("candidate_probability_endpoint_rows")) != EXPECTED_ENDPOINT_ROWS:
        _error("candidate endpoint-row count changed")

    candidate_e_baseline = document.get("candidate_e_baseline")
    if not isinstance(candidate_e_baseline, Mapping):
        _error("validation preparation Candidate-E baseline contract missing")
    if candidate_e_baseline.get("historical_prediction_csv_rows_read") is not False:
        _error(
            "preparation safety flag "
            "candidate_e_baseline.historical_prediction_csv_rows_read is not false"
        )

    required_false = (
        "c1_c2_outcome_rows_read_for_model2",
        "validation_scores_calculated",
        "c3_opened_for_model2",
        "protected_reserve_accessed",
        "strategy_v1_pnl_calculated",
        "execution_enabled",
    )
    for field in required_false:
        if document.get(field) is not False:
            _error(f"preparation safety flag {field} is not false")


def validate_prepared_artifacts(
    *,
    feature_rows: Sequence[Mapping[str, Any]],
    offset_rows: Sequence[Mapping[str, Any]],
    event_map_rows: Sequence[Mapping[str, Any]],
    preparation_freeze: Mapping[str, Any],
) -> None:
    validate_preparation_freeze(preparation_freeze)

    if len(feature_rows) != EXPECTED_VALIDATION_ROWS:
        _error("validation feature row count changed")
    if len(offset_rows) != EXPECTED_VALIDATION_ROWS:
        _error("validation offset row count changed")
    if len(event_map_rows) != EXPECTED_VALIDATION_EVENTS:
        _error("validation event-map count changed")

    validate_feature_rows(feature_rows)

    if canonical_rows_fingerprint(feature_rows) != FEATURE_ROWS_FINGERPRINT:
        _error("persisted validation feature fingerprint mismatch")
    if canonical_rows_fingerprint(offset_rows) != OFFSET_ROWS_FINGERPRINT:
        _error("persisted validation offset fingerprint mismatch")
    if canonical_rows_fingerprint(event_map_rows, key="event_ticker") != EVENT_MAP_FINGERPRINT:
        _error("persisted validation event-map fingerprint mismatch")

    deterministic_map = build_validation_event_map(feature_rows)
    normalized_persisted = tuple(dict(row) for row in event_map_rows)
    if canonical_rows_fingerprint(
        deterministic_map, key="event_ticker"
    ) != canonical_rows_fingerprint(
        normalized_persisted, key="event_ticker"
    ):
        _error("validation event map differs from deterministic derivation")

    feature_ids = {str(row["state_id"]) for row in feature_rows}
    offset_ids: set[str] = set()
    endpoints = 0
    for index, row in enumerate(offset_rows):
        if set(row) != set(OFFSET_FIELDS):
            _error(f"offset row[{index}] schema changed")
        if row.get("model_id") != MODEL_ID:
            _error(f"offset row[{index}] model id changed")
        state = str(row.get("state_id", ""))
        if not state or state in offset_ids:
            _error(f"offset row[{index}] duplicate/blank state")
        offset_ids.add(state)
        offset = _finite_float(
            row.get("candidate_logit_offset"),
            f"offset[{index}].candidate_logit_offset",
        )
        if stable_sigmoid(offset) in (0.0, 1.0):
            endpoints += 1
    if offset_ids != feature_ids:
        _error("offset/feature state sets differ")
    if endpoints != EXPECTED_ENDPOINT_ROWS:
        _error(f"offset endpoint count changed: {endpoints}")


def validate_result_closeout(
    document: Mapping[str, Any],
    *,
    stage: str,
) -> None:
    if stage == "C1":
        expected_schema = "kxbtcd_candidate_e_c1_result_closeout.v1"
        fingerprint_field = "c1_result_closeout_fingerprint"
        fingerprint = C1_RESULT_CLOSEOUT_FINGERPRINT
        outcome_hash = C1_OUTCOMES_SHA256
        count_field = "C1_market_count"
    elif stage == "C2":
        expected_schema = "kxbtcd_candidate_e_c2_result_closeout.v1"
        fingerprint_field = "c2_result_closeout_fingerprint"
        fingerprint = C2_RESULT_CLOSEOUT_FINGERPRINT
        outcome_hash = C2_OUTCOMES_SHA256
        count_field = "C2_market_count"
    else:
        _error(f"unsupported closeout stage {stage!r}")

    if document.get("schema_version") != expected_schema:
        _error(f"{stage} result closeout schema changed")
    if document.get(fingerprint_field) != fingerprint:
        _error(f"{stage} result closeout fingerprint changed")
    if document.get("outcomes_sha256") != outcome_hash:
        _error(f"{stage} outcomes hash changed")
    if int(document.get(count_field)) != EXPECTED_STAGE_MARKETS[stage]:
        _error(f"{stage} market count changed")
    if document.get("execution_enabled") is not False:
        _error(f"{stage} historical result closeout unexpectedly enabled execution")


def project_outcomes(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_stage: str,
) -> dict[str, tuple[str, int]]:
    expected_count = EXPECTED_STAGE_MARKETS[expected_stage]
    if len(rows) != expected_count:
        _error(
            f"{expected_stage} outcome market count changed: "
            f"{len(rows)} != {expected_count}"
        )
    result: dict[str, tuple[str, int]] = {}
    for index, row in enumerate(rows):
        stage = str(row.get("stage", ""))
        if stage != expected_stage:
            _error(
                f"{expected_stage} outcome row[{index}] stage {stage!r} changed"
            )
        event = str(row.get("event_ticker", ""))
        market = str(row.get("market_ticker", ""))
        if not event or not market:
            _error(f"{expected_stage} outcome row[{index}] identity incomplete")
        outcome = _int01(row.get("outcome"), f"{expected_stage} outcome[{index}]")
        if market in result:
            _error(f"duplicate {expected_stage} outcome market {market}")
        result[market] = (event, outcome)
    return result


def attach_validation_outcomes(
    feature_rows: Sequence[Mapping[str, Any]],
    *,
    c1_outcome_rows: Sequence[Mapping[str, Any]],
    c2_outcome_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    validate_feature_rows(feature_rows)
    labels = {
        "C1": project_outcomes(c1_outcome_rows, expected_stage="C1"),
        "C2": project_outcomes(c2_outcome_rows, expected_stage="C2"),
    }

    selected_markets = {
        stage: {
            str(row["market_ticker"])
            for row in feature_rows
            if str(row["stage"]) == stage
        }
        for stage in ("C1", "C2")
    }
    for stage in ("C1", "C2"):
        if set(labels[stage]) != selected_markets[stage]:
            missing = sorted(selected_markets[stage] - set(labels[stage]))[:3]
            extra = sorted(set(labels[stage]) - selected_markets[stage])[:3]
            _error(
                f"{stage} outcome/feature market set mismatch; "
                f"missing={missing}, extra={extra}"
            )

    labeled: list[dict[str, Any]] = []
    for row in feature_rows:
        stage = str(row["stage"])
        market = str(row["market_ticker"])
        event = str(row["event_ticker"])
        label_event, outcome = labels[stage][market]
        if label_event != event:
            _error(
                f"{stage} outcome event mismatch for {market}: "
                f"{label_event} != {event}"
            )
        item = dict(row)
        item["outcome"] = outcome
        labeled.append(item)
    return tuple(labeled)


def _block_map(
    event_map_rows: Sequence[Mapping[str, Any]],
) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    counts = {block: 0 for block in VALIDATION_BLOCKS}
    for index, row in enumerate(event_map_rows):
        event = str(row.get("event_ticker", ""))
        stage = str(row.get("stage", ""))
        block = str(row.get("validation_block", ""))
        if not event or event in result:
            _error(f"event-map row[{index}] duplicate/blank event")
        if stage not in {"C1", "C2"}:
            _error(f"event-map row[{index}] unauthorized stage {stage!r}")
        if block not in VALIDATION_BLOCKS:
            _error(f"event-map row[{index}] unknown block {block!r}")
        result[event] = (stage, block)
        counts[block] += 1
    if counts != {block: EVENTS_PER_BLOCK for block in VALIDATION_BLOCKS}:
        _error(f"validation block event counts changed: {counts}")
    return result


def _offset_map(
    offset_rows: Sequence[Mapping[str, Any]],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for index, row in enumerate(offset_rows):
        state = str(row.get("state_id", ""))
        if not state or state in result:
            _error(f"offset row[{index}] duplicate/blank state")
        result[state] = _finite_float(
            row.get("candidate_logit_offset"),
            f"offset row[{index}].candidate_logit_offset",
        )
    return result


def score_validation_rows(
    labeled_rows: Sequence[Mapping[str, Any]],
    *,
    offset_rows: Sequence[Mapping[str, Any]],
    event_map_rows: Sequence[Mapping[str, Any]],
    coefficients: Sequence[float],
    scaler: EventEqualScaler,
) -> tuple[dict[str, Any], ...]:
    if len(coefficients) != len(PARAMETER_NAMES):
        _error("fixed development coefficient dimension changed")
    offsets = _offset_map(offset_rows)
    blocks = _block_map(event_map_rows)

    result: list[dict[str, Any]] = []
    for index, row in enumerate(labeled_rows):
        state = str(row.get("state_id", ""))
        event = str(row.get("event_ticker", ""))
        stage = str(row.get("stage", ""))
        market = str(row.get("market_ticker", ""))
        if state not in offsets:
            _error(f"labeled row[{index}] missing finite Candidate-E offset")
        if event not in blocks:
            _error(f"labeled row[{index}] missing validation block")
        map_stage, block = blocks[event]
        if map_stage != stage:
            _error(f"labeled row[{index}] event-map stage mismatch")

        outcome = _int01(row.get("outcome"), f"labeled row[{index}].outcome")
        offset = offsets[state]
        candidate_probability = stable_sigmoid(offset)
        frozen_probability = _finite_float(
            row.get("candidate_probability"),
            f"labeled row[{index}].candidate_probability",
        )
        if not math.isclose(
            candidate_probability,
            frozen_probability,
            rel_tol=0.0,
            abs_tol=1e-15,
        ):
            _error(
                f"state {state} Candidate-E probability does not match "
                "finite-logit sidecar"
            )

        x = design_vector(row, scaler)
        residual = sum(
            float(beta) * value for beta, value in zip(coefficients, x)
        )
        if not math.isfinite(residual):
            _error(f"state {state} residual logit became non-finite")
        model2_logit = offset + residual
        if not math.isfinite(model2_logit):
            _error(f"state {state} Model-2 logit became non-finite")
        model2_probability = stable_sigmoid(model2_logit)

        candidate_loss = binary_log_loss_from_logit(offset, outcome)
        model2_loss = binary_log_loss_from_logit(model2_logit, outcome)
        candidate_brier = (candidate_probability - float(outcome)) ** 2
        model2_brier = (model2_probability - float(outcome)) ** 2

        result.append(
            {
                "schema_version": SCORED_ROW_SCHEMA,
                "model_id": MODEL_ID,
                "validation_block": block,
                "stage": stage,
                "state_id": state,
                "event_ticker": event,
                "market_ticker": market,
                "structural_role": str(row["structural_role"]),
                "ttc_target_minutes": int(row["ttc_target_minutes"]),
                "outcome": outcome,
                "candidate_logit_offset": offset,
                "candidate_probability": candidate_probability,
                "model2_residual_logit": residual,
                "model2_logit": model2_logit,
                "model2_probability": model2_probability,
                "candidate_log_loss": candidate_loss,
                "model2_log_loss": model2_loss,
                "candidate_brier": candidate_brier,
                "model2_brier": model2_brier,
            }
        )

    if len(result) != EXPECTED_VALIDATION_ROWS:
        _error("scored validation row count changed")
    result.sort(
        key=lambda row: (
            VALIDATION_BLOCKS.index(str(row["validation_block"])),
            str(row["event_ticker"]),
            str(row["state_id"]),
        )
    )
    return tuple(result)


def build_event_scores(
    scored_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in scored_rows:
        by_event.setdefault(str(row["event_ticker"]), []).append(row)
    if len(by_event) != EXPECTED_VALIDATION_EVENTS:
        _error("scored validation event count changed")

    result: list[dict[str, Any]] = []
    for event, rows in by_event.items():
        stages = {str(row["stage"]) for row in rows}
        blocks = {str(row["validation_block"]) for row in rows}
        if len(stages) != 1 or len(blocks) != 1:
            _error(f"event {event} crosses stage/block after scoring")
        count = len(rows)
        candidate_loss = sum(float(row["candidate_log_loss"]) for row in rows) / count
        model2_loss = sum(float(row["model2_log_loss"]) for row in rows) / count
        candidate_brier = sum(float(row["candidate_brier"]) for row in rows) / count
        model2_brier = sum(float(row["model2_brier"]) for row in rows) / count
        result.append(
            {
                "schema_version": EVENT_SCORE_SCHEMA,
                "model_id": MODEL_ID,
                "validation_block": next(iter(blocks)),
                "stage": next(iter(stages)),
                "event_ticker": event,
                "row_count": count,
                "candidate_log_loss": candidate_loss,
                "model2_log_loss": model2_loss,
                "candidate_minus_model2_log_loss": candidate_loss - model2_loss,
                "candidate_brier": candidate_brier,
                "model2_brier": model2_brier,
                "candidate_minus_model2_brier": candidate_brier - model2_brier,
            }
        )
    result.sort(
        key=lambda row: (
            VALIDATION_BLOCKS.index(str(row["validation_block"])),
            str(row["event_ticker"]),
        )
    )
    return tuple(result)


def build_block_scores(
    event_scores: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for block in VALIDATION_BLOCKS:
        rows = [
            row for row in event_scores
            if str(row["validation_block"]) == block
        ]
        if len(rows) != EVENTS_PER_BLOCK:
            _error(
                f"{block} event count changed: "
                f"{len(rows)} != {EVENTS_PER_BLOCK}"
            )
        candidate_loss = sum(float(row["candidate_log_loss"]) for row in rows) / len(rows)
        model2_loss = sum(float(row["model2_log_loss"]) for row in rows) / len(rows)
        candidate_brier = sum(float(row["candidate_brier"]) for row in rows) / len(rows)
        model2_brier = sum(float(row["model2_brier"]) for row in rows) / len(rows)
        result.append(
            {
                "schema_version": BLOCK_SCORE_SCHEMA,
                "model_id": MODEL_ID,
                "validation_block": block,
                "event_count": len(rows),
                "candidate_log_loss": candidate_loss,
                "model2_log_loss": model2_loss,
                "candidate_minus_model2_log_loss": candidate_loss - model2_loss,
                "candidate_brier": candidate_brier,
                "model2_brier": model2_brier,
                "candidate_minus_model2_brier": candidate_brier - model2_brier,
                "model2_log_loss_win": model2_loss < candidate_loss,
            }
        )
    return tuple(result)


def build_validation_summary(
    event_scores: Sequence[Mapping[str, Any]],
    block_scores: Sequence[Mapping[str, Any]],
    *,
    implementation_fingerprint: str,
) -> dict[str, Any]:
    if len(event_scores) != EXPECTED_VALIDATION_EVENTS:
        _error("validation summary event count changed")
    if len(block_scores) != len(VALIDATION_BLOCKS):
        _error("validation summary block count changed")

    candidate_loss = sum(float(row["candidate_log_loss"]) for row in event_scores) / len(event_scores)
    model2_loss = sum(float(row["model2_log_loss"]) for row in event_scores) / len(event_scores)
    candidate_brier = sum(float(row["candidate_brier"]) for row in event_scores) / len(event_scores)
    model2_brier = sum(float(row["model2_brier"]) for row in event_scores) / len(event_scores)
    event_deltas = [
        float(row["candidate_minus_model2_log_loss"])
        for row in event_scores
    ]
    block_win_count = sum(
        1 for row in block_scores
        if bool(row["model2_log_loss_win"])
    )
    newest = next(
        row for row in block_scores
        if str(row["validation_block"]) == VALIDATION_BLOCKS[-1]
    )

    conditions = {
        "pooled_model2_log_loss_strictly_better": model2_loss < candidate_loss,
        "pooled_model2_brier_not_worse": model2_brier <= candidate_brier,
        "at_least_four_of_five_block_log_loss_wins": block_win_count >= 4,
        "newest_block_log_loss_win": bool(newest["model2_log_loss_win"]),
        "median_event_candidate_e_minus_model2_log_loss_positive": (
            median(event_deltas) > 0.0
        ),
    }
    passed = all(conditions.values())

    payload: dict[str, Any] = {
        "schema_version": SUMMARY_SCHEMA,
        "checkpoint_id": "21M",
        "model_id": MODEL_ID,
        "development_freeze_fingerprint": DEVELOPMENT_FREEZE_FINGERPRINT,
        "validation_preparation_fingerprint": VALIDATION_PREPARATION_FINGERPRINT,
        "validation_implementation_fingerprint": implementation_fingerprint,
        "selected_lambda": SELECTED_LAMBDA,
        "validation_events": EXPECTED_VALIDATION_EVENTS,
        "validation_rows": EXPECTED_VALIDATION_ROWS,
        "blocks": list(VALIDATION_BLOCKS),
        "events_per_block": EVENTS_PER_BLOCK,
        "candidate_e_event_equal_log_loss": candidate_loss,
        "model2_event_equal_log_loss": model2_loss,
        "candidate_e_minus_model2_log_loss": candidate_loss - model2_loss,
        "candidate_e_event_equal_brier": candidate_brier,
        "model2_event_equal_brier": model2_brier,
        "candidate_e_minus_model2_brier": candidate_brier - model2_brier,
        "median_event_candidate_e_minus_model2_log_loss": median(event_deltas),
        "block_log_loss_win_count": block_win_count,
        "newest_block": VALIDATION_BLOCKS[-1],
        "newest_block_log_loss_win": bool(newest["model2_log_loss_win"]),
        "gate_conditions": conditions,
        "validation_passed": passed,
        "interpretation": (
            "PASS permits a separate fixed-lambda H1_OOF+H2+H3+C1+C2 final-fit "
            "freeze before C3; FAIL permanently rejects Model-2 v1 and keeps C3 sealed."
        ),
        "profitability_claim": False,
        "strategy_v1_pnl_calculated": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "execution_enabled": False,
    }
    payload["validation_evaluation_fingerprint"] = canonical_sha256(payload)
    return payload


def evaluate_validation(
    *,
    feature_rows: Sequence[Mapping[str, Any]],
    offset_rows: Sequence[Mapping[str, Any]],
    event_map_rows: Sequence[Mapping[str, Any]],
    c1_outcome_rows: Sequence[Mapping[str, Any]],
    c2_outcome_rows: Sequence[Mapping[str, Any]],
    development_freeze: Mapping[str, Any],
    preparation_freeze: Mapping[str, Any],
    implementation_fingerprint: str,
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[str, Any],
]:
    validate_prepared_artifacts(
        feature_rows=feature_rows,
        offset_rows=offset_rows,
        event_map_rows=event_map_rows,
        preparation_freeze=preparation_freeze,
    )
    coefficients, scaler = validate_development_freeze(development_freeze)
    labeled = attach_validation_outcomes(
        feature_rows,
        c1_outcome_rows=c1_outcome_rows,
        c2_outcome_rows=c2_outcome_rows,
    )
    scored = score_validation_rows(
        labeled,
        offset_rows=offset_rows,
        event_map_rows=event_map_rows,
        coefficients=coefficients,
        scaler=scaler,
    )
    event_scores = build_event_scores(scored)
    block_scores = build_block_scores(event_scores)
    summary = build_validation_summary(
        event_scores,
        block_scores,
        implementation_fingerprint=implementation_fingerprint,
    )
    return scored, event_scores, block_scores, summary


def build_implementation_freeze(
    *,
    implementation_sha256s: Mapping[str, str],
    dependency_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    if dependency_sha256s.get(
        "src/kxbtcd_candidate_e_entry_model_v1.py"
    ) != CORE_SHA256:
        _error("Model-2 core hash differs from accepted D-021M-05 core")
    if set(implementation_sha256s) != set(IMPLEMENTATION_FILES):
        _error("validation implementation hash set changed")
    if set(dependency_sha256s) != set(DEPENDENCY_FILES):
        _error("validation dependency hash set changed")

    payload: dict[str, Any] = {
        "schema_version": IMPLEMENTATION_FREEZE_SCHEMA,
        "checkpoint_id": "21M",
        "model_id": MODEL_ID,
        "parent_commit": PARENT_COMMIT,
        "development_freeze_fingerprint": DEVELOPMENT_FREEZE_FINGERPRINT,
        "validation_preparation_fingerprint": VALIDATION_PREPARATION_FINGERPRINT,
        "feature_rows_fingerprint": FEATURE_ROWS_FINGERPRINT,
        "validation_offset_rows_fingerprint": OFFSET_ROWS_FINGERPRINT,
        "validation_event_map_fingerprint": EVENT_MAP_FINGERPRINT,
        "candidate_probability_endpoint_rows": EXPECTED_ENDPOINT_ROWS,
        "selected_lambda": SELECTED_LAMBDA,
        "candidate_e_offset_policy": {
            "source": "finite_validation_offset_sidecar",
            "historical_probability_endpoints_preserved": True,
            "clipping": False,
            "log_loss_scored_from_finite_logit": True,
            "brier_probability": "stable_sigmoid(finite_logit)",
        },
        "outcome_sources": {
            "C1": {
                "result_closeout_fingerprint": C1_RESULT_CLOSEOUT_FINGERPRINT,
                "outcomes_sha256": C1_OUTCOMES_SHA256,
                "market_count": EXPECTED_STAGE_MARKETS["C1"],
            },
            "C2": {
                "result_closeout_fingerprint": C2_RESULT_CLOSEOUT_FINGERPRINT,
                "outcomes_sha256": C2_OUTCOMES_SHA256,
                "market_count": EXPECTED_STAGE_MARKETS["C2"],
            },
        },
        "gate": {
            "primary_metric": "event_equal_binary_log_loss",
            "secondary_metric": "event_equal_brier",
            "blocks": list(VALIDATION_BLOCKS),
            "events_per_block": EVENTS_PER_BLOCK,
            "conditions": [
                "pooled_Model2_log_loss < pooled_CandidateE_log_loss",
                "pooled_Model2_brier <= pooled_CandidateE_brier",
                "Model2_log_loss_wins >= 4_of_5_blocks",
                "Model2_wins_newest_block",
                "median_event_CandidateE_minus_Model2_log_loss > 0",
            ],
            "all_conditions_required": True,
            "primary_tie": "FAIL",
            "brier_tie": "PASS",
        },
        "implementation_sha256s": dict(sorted(implementation_sha256s.items())),
        "dependency_sha256s": dict(sorted(dependency_sha256s.items())),
        "scientific_changes_after_development_freeze": False,
        "outcomes_read_during_implementation_freeze": False,
        "validation_scores_calculated": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "strategy_v1_pnl_calculated": False,
        "execution_enabled": False,
    }
    payload["validation_implementation_fingerprint"] = canonical_sha256(payload)
    return payload


ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT = (
    "8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7"
)
VALIDATION_RESUME_REPAIR_PARENT_COMMIT = (
    "918810f97df8edf15bcb904ab4f8e1adf9785089"
)
VALIDATION_RESUME_REPAIR_SCHEMA = (
    "kxbtcd_candidate_e_entry_model_v1_validation_resume_repair_freeze.v1"
)
VALIDATION_RESUME_REPAIR_ID = (
    "D-021M-11_nested_preparation_safety_field_lookup.v1"
)
VALIDATION_RESUME_REPAIR_DEFAULT = Path(
    "configs/kxbtcd_candidate_e_entry_model_v1_validation_resume_repair_freeze.json"
)

ORIGINAL_IMPLEMENTATION_SHA256S = {
    "evaluate_kxbtcd_candidate_e_entry_model_v1_validation.py":
        "71e3a58045b950958e6c407c3f88d1c25120b2772b5163ce44601d7480eaca43",
    "freeze_kxbtcd_candidate_e_entry_model_v1_validation_implementation.py":
        "dd6b27ae2f387b14cc8d84584310a8d125fad5e740450f0089d3cc191358cfd2",
    "src/kxbtcd_candidate_e_entry_model_v1_validation.py":
        "ee551329504d0cc001c363f6c269ac2c34cf04587b1c28d5b626e28a8a791e80",
    "validate_kxbtcd_candidate_e_entry_model_v1_validation.py":
        "a93fe893d99c02b8dac52dbba12e115c7532d893dbf2d5c3b8e06635ea4002b8",
    "validate_kxbtcd_candidate_e_entry_model_v1_validation_implementation_freeze.py":
        "7c44087f475178b3132c458081ce185b876f16fba250ef31ccff5ac77bcccb28",
}
ORIGINAL_DEPENDENCY_SHA256S = {
    "src/kxbtcd_candidate_e_entry_model_v1.py":
        "ce54846f85f3d338bc0f3aadd64d8cc8b9828c0c2ac2b5454f97771ec1a89ee1",
    "src/kxbtcd_candidate_e_entry_model_v1_validation_preparation.py":
        "b5bfd289cd417649b861e9cda28de98f611a613454b32bbb8c17a7774a8b242b",
}


def build_validation_resume_repair_freeze(
    *,
    implementation_sha256s: Mapping[str, str],
    dependency_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    if set(implementation_sha256s) != set(ORIGINAL_IMPLEMENTATION_SHA256S):
        _error("resume-repair implementation hash set changed")
    if set(dependency_sha256s) != set(ORIGINAL_DEPENDENCY_SHA256S):
        _error("resume-repair dependency hash set changed")

    runtime_target = "src/kxbtcd_candidate_e_entry_model_v1_validation.py"
    for path, expected in ORIGINAL_IMPLEMENTATION_SHA256S.items():
        actual = implementation_sha256s.get(path)
        if path == runtime_target:
            if actual == expected:
                _error("resume repair has not changed the validation runtime target")
        elif actual != expected:
            _error(f"unauthorized post-outcome implementation change: {path}")

    if dict(dependency_sha256s) != ORIGINAL_DEPENDENCY_SHA256S:
        _error("post-outcome dependency hashes changed")

    payload: dict[str, Any] = {
        "schema_version": VALIDATION_RESUME_REPAIR_SCHEMA,
        "checkpoint_id": "21M",
        "model_id": MODEL_ID,
        "repair_id": VALIDATION_RESUME_REPAIR_ID,
        "repair_parent_commit": VALIDATION_RESUME_REPAIR_PARENT_COMMIT,
        "original_validation_implementation_fingerprint":
            ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT,
        "validation_implementation_fingerprint":
            ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT,
        "development_freeze_fingerprint": DEVELOPMENT_FREEZE_FINGERPRINT,
        "validation_preparation_fingerprint": VALIDATION_PREPARATION_FINGERPRINT,
        "original_implementation_sha256s":
            dict(sorted(ORIGINAL_IMPLEMENTATION_SHA256S.items())),
        "repaired_implementation_sha256s":
            dict(sorted(implementation_sha256s.items())),
        "dependency_sha256s":
            dict(sorted(dependency_sha256s.items())),
        "repair_scope": {
            "runtime_file": runtime_target,
            "bug":
                "validation preparation stores historical_prediction_csv_rows_read "
                "under candidate_e_baseline but evaluator checked top level",
            "repair":
                "read candidate_e_baseline.historical_prediction_csv_rows_read",
            "model_formula_changed": False,
            "features_changed": False,
            "coefficients_changed": False,
            "scaler_changed": False,
            "lambda_changed": False,
            "validation_blocks_changed": False,
            "metrics_changed": False,
            "gate_changed": False,
        },
        "attempt_resume_contract": {
            "required_status": "OUTCOMES_OPENED_FOR_MODEL2_VALIDATION",
            "required_original_validation_implementation_fingerprint":
                ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT,
            "required_validation_preparation_fingerprint":
                VALIDATION_PREPARATION_FINGERPRINT,
            "fresh_attempt_prohibited": True,
            "same_attempt_path_required": True,
            "same_output_dir_required": True,
        },
        "c1_c2_outcomes_already_opened_for_model2": True,
        "validation_scores_calculated_before_repair": False,
        "result_directory_existed_before_repair": False,
        "outcomes_read_during_repair_freeze": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "strategy_v1_pnl_calculated": False,
        "execution_enabled": False,
    }
    payload["validation_resume_repair_fingerprint"] = canonical_sha256(payload)
    return payload


def validate_implementation_freeze_document(
    document: Mapping[str, Any],
    *,
    implementation_sha256s: Mapping[str, str],
    dependency_sha256s: Mapping[str, str],
) -> None:
    schema = document.get("schema_version")
    if schema == IMPLEMENTATION_FREEZE_SCHEMA:
        expected = build_implementation_freeze(
            implementation_sha256s=implementation_sha256s,
            dependency_sha256s=dependency_sha256s,
        )
    elif schema == VALIDATION_RESUME_REPAIR_SCHEMA:
        expected = build_validation_resume_repair_freeze(
            implementation_sha256s=implementation_sha256s,
            dependency_sha256s=dependency_sha256s,
        )
    else:
        _error(f"unknown validation implementation freeze schema {schema!r}")

    if dict(document) != expected:
        _error("validation implementation freeze differs from deterministic derivation")


def build_receipt(
    *,
    summary: Mapping[str, Any],
    source_sha256s: Mapping[str, str],
    output_sha256s: Mapping[str, str],
    implementation_fingerprint: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "checkpoint_id": "21M",
        "model_id": MODEL_ID,
        "validation_implementation_fingerprint": implementation_fingerprint,
        "validation_preparation_fingerprint": VALIDATION_PREPARATION_FINGERPRINT,
        "development_freeze_fingerprint": DEVELOPMENT_FREEZE_FINGERPRINT,
        "validation_evaluation_fingerprint": summary[
            "validation_evaluation_fingerprint"
        ],
        "validation_passed": bool(summary["validation_passed"]),
        "source_sha256s": dict(sorted(source_sha256s.items())),
        "output_sha256s": dict(sorted(output_sha256s.items())),
        "c1_c2_outcomes_opened_for_model2": True,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "strategy_v1_pnl_calculated": False,
        "execution_enabled": False,
    }
    payload["validation_receipt_fingerprint"] = canonical_sha256(payload)
    return payload


__all__ = [
    "ATTEMPT_SCHEMA",
    "BLOCK_SCORE_FIELDS",
    "C1_OUTCOMES_SHA256",
    "C1_RESULT_CLOSEOUT_FINGERPRINT",
    "C2_OUTCOMES_SHA256",
    "C2_RESULT_CLOSEOUT_FINGERPRINT",
    "CORE_SHA256",
    "DEPENDENCY_FILES",
    "DEVELOPMENT_FREEZE_FINGERPRINT",
    "EVENT_SCORE_FIELDS",
    "FEATURE_ROWS_FINGERPRINT",
    "IMPLEMENTATION_FILES",
    "IMPLEMENTATION_FREEZE_DEFAULT",
    "IMPLEMENTATION_FREEZE_SCHEMA",
    "MODEL_ID",
    "OFFSET_ROWS_FINGERPRINT",
    "PARENT_COMMIT",
    "RECEIPT_SCHEMA",
    "SCORED_ROW_FIELDS",
    "SELECTED_LAMBDA",
    "SUMMARY_SCHEMA",
    "VALIDATION_PREPARATION_FINGERPRINT",
    "ValidationEvaluationError",
    "attach_validation_outcomes",
    "build_implementation_freeze",
    "build_receipt",
    "build_validation_summary",
    "evaluate_validation",
    "project_outcomes",
    "read_csv",
    "read_json",
    "sha256_file",
    "validate_development_freeze",
    "validate_implementation_freeze_document",
    "validate_preparation_freeze",
    "validate_prepared_artifacts",
    "validate_result_closeout",
    "write_csv",
    "write_json",
]
