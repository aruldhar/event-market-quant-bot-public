"""Checkpoint-16 Candidate-C full-development preprocessing freeze and final fit.

This module is deliberately offline-only. It consumes only the already outcome-exposed
Checkpoint-13 train+validation development rows through the validated Checkpoint-15
Candidate-C interfaces. The locked-test partition is never selected, scored, summarized,
or labeled here.

Checkpoint 16 has two ordered stages:

1. Freeze and fingerprint the exact full-development preprocessing/provenance state.
2. After that freeze validates, perform exactly one final Candidate-C fit at lambda=0.01
   on all 231 exposed development events and serialize the final inference artifact.

There is no network client and no execution path in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_b_evaluation import (
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_PREOUTCOME_RUN_ID,
    FROZEN_SPLIT_FINGERPRINT,
)
from .kxbtcd_candidate_b_failure_analysis import (
    CP13_RUN_ID,
    KxbtcdCandidateBFailureAnalysisError,
    load_canonical_development_predictions,
)
from .kxbtcd_candidate_c_development import (
    DEFAULT_WEEK_MAP_PATH,
    EXPECTED_DEVELOPMENT_EVENTS,
    EXPECTED_DEVELOPMENT_ROWS,
    FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
    CandidateCObservation,
    FeatureScaler,
    KxbtcdCandidateCDevelopmentError,
    _market_logit,
    _sigmoid,
    build_candidate_c_observations,
    compute_fit_fold_scaler,
    fit_candidate_c_fold,
    load_and_validate_frozen_week_map,
)
from .kxbtcd_candidate_c_predeclaration import CANDIDATE_ID, candidate_c_predeclaration


class KxbtcdCandidateCFinalFitError(RuntimeError):
    """Raised when a Checkpoint-16 freeze/final-fit invariant is violated."""


SELECTED_LAMBDA = Decimal("0.01")
EXPECTED_WEEK_MAP_FINGERPRINT = "6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4"
FULL_DEVELOPMENT_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_c_full_development_freeze.v1"
FINAL_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_c_final_model.v1"
FINAL_FIT_ATTEMPT_SCHEMA_VERSION = "kxbtcd_candidate_c_final_fit_attempt.v1"
DEFAULT_FULL_DEVELOPMENT_FREEZE_PATH = Path("configs/kxbtcd_candidate_c_full_development_freeze.json")
DEFAULT_FINAL_MODEL_PATH = Path("configs/kxbtcd_candidate_c_final_model.json")
DEFAULT_ATTEMPT_RECEIPT_PATH = Path("data/analysis/kxbtcd_candidate_c_final_fit/final_fit_attempt.json")
FEATURE_ORDER = ("market_logit", "spread", "market_logit_x_spread")
COEFFICIENT_ORDER = ("intercept", "market_logit_z", "spread_z", "market_logit_x_spread_z")


def _error(message: str) -> None:
    raise KxbtcdCandidateCFinalFitError(message)


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        _error("attempted to serialize a non-finite Checkpoint-16 value")
    return format(value, ".17g")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve(repo: Path, path: str | Path) -> Path:
    target = Path(path)
    return target if target.is_absolute() else repo / target


def _load_full_development_observations(
    repository_root: str | Path = ".",
    *,
    week_map_path: str | Path = DEFAULT_WEEK_MAP_PATH,
) -> tuple[tuple[CandidateCObservation, ...], dict[str, Any]]:
    repo = Path(repository_root).resolve()
    week_mapping, week_document = load_and_validate_frozen_week_map(
        week_map_path,
        repository_root=repo,
        require_matches_current_frozen_development=True,
    )
    if week_document.get("week_map_fingerprint") != EXPECTED_WEEK_MAP_FINGERPRINT:
        _error("Checkpoint-16 week-map fingerprint does not match the frozen Checkpoint-15 map")
    try:
        predictions, cp13_provenance = load_canonical_development_predictions(repo)
    except KxbtcdCandidateBFailureAnalysisError as exc:
        raise KxbtcdCandidateCFinalFitError(
            f"could not load canonical exposed development predictions: {exc}"
        ) from exc
    observations = build_candidate_c_observations(predictions, week_mapping, enforce_canonical_counts=True)
    if any(row.block not in {0, 1, 2, 3, 4} for row in observations):
        _error("full-development observations contain a block outside B0-B4")
    if len(observations) != EXPECTED_DEVELOPMENT_ROWS:
        _error("full-development row count changed")
    if len({row.event_ticker for row in observations}) != EXPECTED_DEVELOPMENT_EVENTS:
        _error("full-development event count changed")
    return observations, {
        "week_map": week_document,
        "cp13": cp13_provenance,
    }


def _frozen_model_rules() -> dict[str, Any]:
    spec = candidate_c_predeclaration()
    model = spec["model"]
    return {
        "feature_order": list(FEATURE_ORDER),
        "feature_definitions": {
            "market_logit": "ln(clip(q_market,0.001,0.999)/(1-clip(q_market,0.001,0.999)))",
            "spread": "yes_ask - yes_bid",
            "market_logit_x_spread": "market_logit * spread",
        },
        "standardization": {
            "rule": "unweighted row-level mean and population standard deviation over all full-development rows",
            "ddof": 0,
            "event_weighting_applied_to_preprocessing": False,
        },
        "objective": {
            "rule": "mean_over_fit_events(mean_binary_log_loss_within_event) + lambda/2 * sum(non_intercept_beta^2)",
            "event_weighting": "each event contributes equal total weight; rows within an event split that event weight equally",
            "intercept_penalized": False,
            "non_intercept_coefficients_penalized": True,
        },
        "optimizer": dict(model["optimizer"]),
        "selected_lambda": "0.01",
        "lambda_selection_status": "frozen_from_checkpoint_15_no_search_permitted",
    }


def build_full_development_freeze_document(
    rows: Sequence[CandidateCObservation],
    *,
    scaler: FeatureScaler | None = None,
    enforce_canonical_counts: bool = True,
) -> dict[str, Any]:
    observations = tuple(rows)
    if not observations:
        _error("cannot freeze preprocessing from an empty development set")
    if enforce_canonical_counts:
        if len(observations) != EXPECTED_DEVELOPMENT_ROWS:
            _error("Checkpoint-16 freeze requires exactly 5,364 development rows")
        if len({row.event_ticker for row in observations}) != EXPECTED_DEVELOPMENT_EVENTS:
            _error("Checkpoint-16 freeze requires exactly 231 development events")
        if {row.block for row in observations} != {0, 1, 2, 3, 4}:
            _error("Checkpoint-16 freeze requires development blocks B0-B4")
    if any(row.block not in {0, 1, 2, 3, 4} for row in observations):
        _error("Checkpoint-16 freeze refuses rows outside development blocks B0-B4")

    scaler = scaler or compute_fit_fold_scaler(observations)
    payload = {
        "schema_version": FULL_DEVELOPMENT_FREEZE_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
        "week_map_fingerprint": EXPECTED_WEEK_MAP_FINGERPRINT,
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "cp13_exposed_development_run_id": CP13_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "development_event_count": len({row.event_ticker for row in observations}),
        "development_row_count": len(observations),
        "development_blocks": ["B0", "B1", "B2", "B3", "B4"],
        "locked_test_outcomes_opened": 0,
        "locked_test_evaluation_performed": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "rules": _frozen_model_rules(),
        "scaler": {
            "feature_order": list(FEATURE_ORDER),
            "means": [_float_text(value) for value in scaler.means],
            "population_stds": [_float_text(value) for value in scaler.population_stds],
        },
    }
    document = dict(payload)
    document["full_development_freeze_fingerprint"] = _canonical_sha256(payload)
    return document


def _scaler_from_freeze(document: Mapping[str, Any]) -> FeatureScaler:
    scaler = document.get("scaler")
    if not isinstance(scaler, Mapping):
        _error("full-development freeze is missing scaler state")
    if tuple(scaler.get("feature_order", ())) != FEATURE_ORDER:
        _error("full-development freeze feature order changed")
    try:
        means = tuple(float(value) for value in scaler["means"])
        stds = tuple(float(value) for value in scaler["population_stds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise KxbtcdCandidateCFinalFitError("invalid scaler numeric state") from exc
    if len(means) != 3 or len(stds) != 3:
        _error("full-development freeze scaler must contain exactly three features")
    if any(not math.isfinite(value) for value in means + stds):
        _error("full-development freeze scaler contains non-finite values")
    if any(value <= 0.0 for value in stds):
        _error("full-development freeze scaler standard deviations must be positive")
    return FeatureScaler(means=means, population_stds=stds)


def validate_full_development_freeze_document(
    document: Mapping[str, Any],
    *,
    rows: Sequence[CandidateCObservation] | None = None,
    enforce_canonical_counts: bool = True,
) -> FeatureScaler:
    if not isinstance(document, Mapping):
        _error("full-development freeze root must be an object")
    if document.get("schema_version") != FULL_DEVELOPMENT_FREEZE_SCHEMA_VERSION:
        _error("full-development freeze schema version mismatch")
    expected_identity = {
        "candidate_id": CANDIDATE_ID,
        "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
        "week_map_fingerprint": EXPECTED_WEEK_MAP_FINGERPRINT,
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "cp13_exposed_development_run_id": CP13_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
    }
    for key, expected in expected_identity.items():
        if document.get(key) != expected:
            _error(f"full-development freeze {key} mismatch")
    if document.get("rules") != _frozen_model_rules():
        _error("full-development freeze model/preprocessing rules changed")
    if document.get("locked_test_outcomes_opened") != 0:
        _error("full-development freeze indicates locked-test outcome access")
    if document.get("locked_test_evaluation_performed") is not False:
        _error("full-development freeze indicates locked-test evaluation")
    if document.get("network_requests") != 0:
        _error("full-development freeze indicates network access")
    if document.get("execution_enabled") is not False or document.get("orders_placed") != 0:
        _error("full-development freeze violates the read-only boundary")
    if enforce_canonical_counts:
        if document.get("development_event_count") != EXPECTED_DEVELOPMENT_EVENTS:
            _error("full-development freeze event count mismatch")
        if document.get("development_row_count") != EXPECTED_DEVELOPMENT_ROWS:
            _error("full-development freeze row count mismatch")
    if document.get("development_blocks") != ["B0", "B1", "B2", "B3", "B4"]:
        _error("full-development freeze block scope changed")

    payload = {key: document[key] for key in document if key != "full_development_freeze_fingerprint"}
    if document.get("full_development_freeze_fingerprint") != _canonical_sha256(payload):
        _error("full-development freeze fingerprint mismatch")
    scaler = _scaler_from_freeze(document)

    if rows is not None:
        expected = build_full_development_freeze_document(
            rows,
            enforce_canonical_counts=enforce_canonical_counts,
        )
        if dict(document) != expected:
            _error("stored full-development freeze differs from the current deterministic derivation")
    return scaler


def write_or_validate_full_development_freeze(
    path: str | Path = DEFAULT_FULL_DEVELOPMENT_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
    week_map_path: str | Path = DEFAULT_WEEK_MAP_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    observations, _ = _load_full_development_observations(repo, week_map_path=week_map_path)
    derived = build_full_development_freeze_document(observations)
    validate_full_development_freeze_document(derived, rows=observations)
    target = _resolve(repo, path)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise KxbtcdCandidateCFinalFitError(f"could not read existing freeze {target}: {exc}") from exc
        validate_full_development_freeze_document(existing, rows=observations)
        if existing != derived:
            _error("existing full-development freeze differs from deterministic derivation; refusing overwrite")
        return target, dict(existing)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(derived, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    return target, derived


def load_and_validate_full_development_freeze(
    path: str | Path = DEFAULT_FULL_DEVELOPMENT_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
    week_map_path: str | Path = DEFAULT_WEEK_MAP_PATH,
) -> tuple[dict[str, Any], tuple[CandidateCObservation, ...], FeatureScaler]:
    repo = Path(repository_root).resolve()
    target = _resolve(repo, path)
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateCFinalFitError(f"could not read full-development freeze {target}: {exc}") from exc
    observations, _ = _load_full_development_observations(repo, week_map_path=week_map_path)
    scaler = validate_full_development_freeze_document(document, rows=observations)
    return dict(document), observations, scaler


@dataclass(frozen=True)
class FinalModelFitResult:
    document: dict[str, Any]
    iterations: int
    fit_objective: float


def fit_final_candidate_c_model(
    rows: Sequence[CandidateCObservation],
    freeze_document: Mapping[str, Any],
    *,
    enforce_canonical_counts: bool = True,
) -> FinalModelFitResult:
    observations = tuple(rows)
    scaler = validate_full_development_freeze_document(
        freeze_document,
        rows=observations,
        enforce_canonical_counts=enforce_canonical_counts,
    )
    fit = fit_candidate_c_fold(
        observations,
        lambda_value=SELECTED_LAMBDA,
        fold_index=0,
        fit_blocks=(0, 1, 2, 3, 4),
        score_block=-1,
        scaler=scaler,
    )
    if not fit.converged:
        _error("final Candidate-C fit did not converge")
    coefficient_values = [_float_text(value) for value in fit.coefficients]
    payload = {
        "schema_version": FINAL_MODEL_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
        "week_map_fingerprint": EXPECTED_WEEK_MAP_FINGERPRINT,
        "full_development_freeze_fingerprint": freeze_document["full_development_freeze_fingerprint"],
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "cp13_exposed_development_run_id": CP13_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "development_event_count": len({row.event_ticker for row in observations}),
        "development_row_count": len(observations),
        "selected_lambda": "0.01",
        "feature_order": list(FEATURE_ORDER),
        "coefficient_order": list(COEFFICIENT_ORDER),
        "coefficients": coefficient_values,
        "scaler": dict(freeze_document["scaler"]),
        "inference": {
            "q_market_clip_lower": "0.001",
            "q_market_clip_upper": "0.999",
            "linear_predictor": "beta0 + beta1*z_market_logit + beta2*z_spread + beta3*z_market_logit_x_spread",
            "output": "sigmoid(linear_predictor)",
        },
        "fit": {
            "optimizer": dict(_frozen_model_rules()["optimizer"]),
            "objective": dict(_frozen_model_rules()["objective"]),
            "iterations": fit.iterations,
            "converged": True,
            "fit_objective": _float_text(fit.fit_objective),
        },
        "locked_test_outcomes_opened": 0,
        "locked_test_evaluation_performed": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["final_model_fingerprint"] = _canonical_sha256(payload)
    return FinalModelFitResult(document=document, iterations=fit.iterations, fit_objective=fit.fit_objective)


def validate_final_model_document(
    document: Mapping[str, Any],
    *,
    enforce_canonical_counts: bool = True,
) -> None:
    if not isinstance(document, Mapping):
        _error("final model root must be an object")
    if document.get("schema_version") != FINAL_MODEL_SCHEMA_VERSION:
        _error("final model schema version mismatch")
    if document.get("candidate_id") != CANDIDATE_ID:
        _error("final model candidate ID mismatch")
    if document.get("candidate_c_predeclaration_fingerprint") != FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT:
        _error("final model predeclaration fingerprint mismatch")
    if document.get("week_map_fingerprint") != EXPECTED_WEEK_MAP_FINGERPRINT:
        _error("final model week-map fingerprint mismatch")
    expected_identity = {
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "cp13_exposed_development_run_id": CP13_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
    }
    for key, expected in expected_identity.items():
        if document.get(key) != expected:
            _error(f"final model {key} mismatch")
    if enforce_canonical_counts:
        if document.get("development_event_count") != EXPECTED_DEVELOPMENT_EVENTS:
            _error("final model development event count mismatch")
        if document.get("development_row_count") != EXPECTED_DEVELOPMENT_ROWS:
            _error("final model development row count mismatch")
    if document.get("selected_lambda") != "0.01":
        _error("final model lambda changed")
    if tuple(document.get("feature_order", ())) != FEATURE_ORDER:
        _error("final model feature order changed")
    if tuple(document.get("coefficient_order", ())) != COEFFICIENT_ORDER:
        _error("final model coefficient order changed")
    coefficients = document.get("coefficients")
    if not isinstance(coefficients, list) or len(coefficients) != 4:
        _error("final model must contain exactly four coefficients")
    try:
        coefficient_values = [float(value) for value in coefficients]
    except (TypeError, ValueError) as exc:
        raise KxbtcdCandidateCFinalFitError("final model coefficients are invalid") from exc
    if any(not math.isfinite(value) for value in coefficient_values):
        _error("final model contains non-finite coefficients")
    _scaler_from_freeze(document)
    fit = document.get("fit")
    if not isinstance(fit, Mapping) or fit.get("converged") is not True:
        _error("final model fit state is not converged")
    if fit.get("optimizer") != _frozen_model_rules()["optimizer"]:
        _error("final model optimizer rules changed")
    if fit.get("objective") != _frozen_model_rules()["objective"]:
        _error("final model objective rules changed")
    if document.get("locked_test_outcomes_opened") != 0 or document.get("locked_test_evaluation_performed") is not False:
        _error("final model indicates locked-test access")
    if document.get("network_requests") != 0:
        _error("final model indicates network access")
    if document.get("execution_enabled") is not False or document.get("orders_placed") != 0:
        _error("final model violates read-only execution boundary")
    payload = {key: document[key] for key in document if key != "final_model_fingerprint"}
    if document.get("final_model_fingerprint") != _canonical_sha256(payload):
        _error("final model fingerprint mismatch")


def predict_with_final_model(
    q_market: float,
    spread: float,
    document: Mapping[str, Any],
    *,
    enforce_canonical_counts: bool = True,
) -> float:
    """Pure inference from the frozen final artifact; no source/network access."""
    validate_final_model_document(document, enforce_canonical_counts=enforce_canonical_counts)
    q = float(q_market)
    s = float(spread)
    if not math.isfinite(q) or not 0.0 <= q <= 1.0:
        _error("q_market must be finite and inside [0,1]")
    if not math.isfinite(s) or s < 0.0:
        _error("spread must be finite and nonnegative")
    market_logit = _market_logit(q)
    raw = (market_logit, s, market_logit * s)
    scaler = _scaler_from_freeze(document)
    z = scaler.transform(raw)
    beta = [float(value) for value in document["coefficients"]]
    linear = math.fsum((beta[0], beta[1] * z[0], beta[2] * z[1], beta[3] * z[2]))
    return _sigmoid(linear)



def validate_final_artifact_bundle(
    freeze_document: Mapping[str, Any],
    final_document: Mapping[str, Any],
    attempt_document: Mapping[str, Any],
) -> None:
    """Validate the frozen scaler, final model, and one-time attempt receipt as one bundle."""
    validate_full_development_freeze_document(freeze_document)
    validate_final_model_document(final_document)
    if final_document.get("full_development_freeze_fingerprint") != freeze_document.get(
        "full_development_freeze_fingerprint"
    ):
        _error("final model is not bound to the validated full-development freeze")
    if final_document.get("scaler") != freeze_document.get("scaler"):
        _error("final model scaler differs from the validated pre-fit freeze")
    if not isinstance(attempt_document, Mapping):
        _error("final-fit attempt receipt root must be an object")
    if attempt_document.get("schema_version") != FINAL_FIT_ATTEMPT_SCHEMA_VERSION:
        _error("final-fit attempt receipt schema mismatch")
    if attempt_document.get("status") != "fit_completed":
        _error("final-fit attempt receipt is not completed")
    if attempt_document.get("candidate_id") != CANDIDATE_ID:
        _error("final-fit attempt candidate mismatch")
    if attempt_document.get("selected_lambda") != "0.01":
        _error("final-fit attempt lambda mismatch")
    if attempt_document.get("full_development_freeze_fingerprint") != freeze_document.get(
        "full_development_freeze_fingerprint"
    ):
        _error("final-fit attempt is not bound to the validated freeze")
    if attempt_document.get("final_model_fingerprint") != final_document.get("final_model_fingerprint"):
        _error("final-fit attempt is not bound to the validated final model")
    if attempt_document.get("locked_test_outcomes_opened") != 0:
        _error("final-fit attempt indicates locked-test outcome access")
    if attempt_document.get("network_requests") != 0:
        _error("final-fit attempt indicates network access")
    if attempt_document.get("execution_enabled") is not False or attempt_document.get("orders_placed") != 0:
        _error("final-fit attempt violates the read-only boundary")

def _create_attempt_receipt(path: Path, *, freeze_fingerprint: str) -> dict[str, Any]:
    if path.exists():
        _error(
            f"final-fit attempt receipt already exists at {path}; refusing a second Checkpoint-16 fit attempt"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": FINAL_FIT_ATTEMPT_SCHEMA_VERSION,
        "status": "fit_started",
        "candidate_id": CANDIDATE_ID,
        "selected_lambda": "0.01",
        "full_development_freeze_fingerprint": freeze_fingerprint,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pid": os.getpid(),
        "locked_test_outcomes_opened": 0,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)
    return document


def _complete_attempt_receipt(path: Path, attempt: Mapping[str, Any], *, final_model_fingerprint: str) -> None:
    completed = dict(attempt)
    completed["status"] = "fit_completed"
    completed["completed_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    completed["final_model_fingerprint"] = final_model_fingerprint
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(completed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def perform_one_time_final_fit(
    *,
    repository_root: str | Path = ".",
    freeze_path: str | Path = DEFAULT_FULL_DEVELOPMENT_FREEZE_PATH,
    final_model_path: str | Path = DEFAULT_FINAL_MODEL_PATH,
    attempt_receipt_path: str | Path = DEFAULT_ATTEMPT_RECEIPT_PATH,
    week_map_path: str | Path = DEFAULT_WEEK_MAP_PATH,
) -> tuple[Path, Path, FinalModelFitResult]:
    repo = Path(repository_root).resolve()
    final_path = _resolve(repo, final_model_path)
    attempt_path = _resolve(repo, attempt_receipt_path)
    if final_path.exists():
        _error(f"final model already exists at {final_path}; refusing a second final fit")
    freeze_document, observations, _ = load_and_validate_full_development_freeze(
        freeze_path,
        repository_root=repo,
        week_map_path=week_map_path,
    )
    attempt = _create_attempt_receipt(
        attempt_path,
        freeze_fingerprint=str(freeze_document["full_development_freeze_fingerprint"]),
    )
    result = fit_final_candidate_c_model(observations, freeze_document)
    validate_final_model_document(result.document)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp = final_path.with_suffix(final_path.suffix + ".tmp")
    temp.write_text(json.dumps(result.document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(final_path)
    _complete_attempt_receipt(
        attempt_path,
        attempt,
        final_model_fingerprint=str(result.document["final_model_fingerprint"]),
    )
    return final_path, attempt_path, result
