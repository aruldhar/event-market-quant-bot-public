"""Checkpoint 21N-K conditional-alpha development evaluator orchestration.

This module implements the exact frozen Checkpoint-21N-I H-development procedure
while keeping real project outcomes inaccessible during the implementation-freeze
checkpoint itself.

After 21N-K is safely closed, the companion CLI may consume only the already-
exposed H1_OOF/H2/H3 Candidate-E prediction/outcome artifacts, attach labels by
exact state_id, fit the five frozen lambdas under the two rolling-origin folds,
apply the frozen probability gate, and only if that probability gate passes,
apply the frozen quoted-entry economic gate. The full H1+H2+H3 fit is allowed
only if both development gates pass.

C1/C2, C3, the protected reserve, network access, and execution are prohibited.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    CANDIDATE_ID,
    DEVELOPMENT_STAGES,
    EXPECTED_STAGE_EVENTS,
    EXPECTED_STAGE_ROWS,
    EXPECTED_TOTAL_EVENTS,
    EXPECTED_TOTAL_ROWS,
    LAMBDA_GRID,
    PARAMETER_NAMES,
    PARENT_CANDIDATE_E_ID,
    ReliabilityFit,
    adjusted_yes_probability,
    apply_fit_probability,
    canonical_sha256,
    event_equal_weights,
    fit_conditional_alpha,
    select_entry_events,
    standard_entry_fee,
    validate_materialized_rows,
)
from .kxbtcd_candidate_e_conditional_alpha_reliability_v1_materialization import (
    canonical_rows_fingerprint,
)

PREDECLARATION_FINGERPRINT = "742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3"
J_B_PREPARATION_CLOSEOUT_FINGERPRINT = "f1b0caed9d83d8657bd916422b17dde4e239cbc41a5de880ed78a51217cdffb1"
PREPARATION_FINGERPRINT = "a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46"
FEATURE_ROWS_FINGERPRINT = "590ab13567821839fb0d404ed4813d328fc4e68ee1a61fd39038d3f8624a42fe"
PREPARED_FEATURE_SHA256 = "268c756f82f6be2b53f5fee1f212ad0ecd1d02459547861cc5c3b3623357472f"

LABEL_SOURCE_SHA256S = {
    "H1_OOF": "867a77cbbf034a574983cb6fb301a77614674d3254297f8e15db377d5c34df16",
    "H2": "4aa6efe3c3bdc231fc8289f11fe01e1ad5a65910ae0ea92d2586447fd6b7d3d6",
    "H3": "091affc5ac088aa61db43a5df18f15178bceeea2ee26bd266b61fd059fd08380",
}
LABEL_SCHEMAS = {
    "H1_OOF": "kxbtcd_candidate_e_h1_oof_prediction.v1",
    "H2": "kxbtcd_candidate_e_h2_prediction.v1",
    "H3": "kxbtcd_candidate_e_h3_prediction.v1",
}

PREPARATION_FREEZE_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_preparation_freeze.v1"
PREPARATION_CLOSEOUT_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_reliability_v1_preparation_closeout.v1"
DEVELOPMENT_EVALUATION_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_development_evaluation.v1"
DEVELOPMENT_RECEIPT_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_development_receipt.v1"
ROLLING_PREDICTION_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_rolling_prediction.v1"
ENTRY_DECISION_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_entry_decision.v1"

SCORE_STAGES = ("H2", "H3")
FOLDS = (
    (1, ("H1_OOF",), "H2"),
    (2, ("H1_OOF", "H2"), "H3"),
)
SCORE_EVENT_COUNT = 1500
BLOCK_COUNT = 5
BLOCK_EVENTS = 300
MIN_TOTAL_ENTRIES = 100
MIN_STAGE_ENTRIES = 20
STRESSES = (Decimal("0.00"), Decimal("0.01"), Decimal("0.02"), Decimal("0.03"))

ROLLING_PREDICTION_FIELDS = (
    "schema_version",
    "candidate_id",
    "selected_lambda",
    "fold",
    "stage",
    "state_id",
    "event_ticker",
    "event_close_time_utc",
    "market_ticker",
    "structural_role",
    "ttc_target_minutes",
    "decision_time_utc",
    "outcome",
    "candidate_probability",
    "market_midpoint_yes_probability",
    "global_alpha_0_50_probability",
    "conditional_alpha",
    "adjusted_yes_probability",
    "yes_bid",
    "yes_ask",
)

ENTRY_DECISION_FIELDS = (
    "schema_version",
    "candidate_id",
    "stage",
    "chronological_block",
    "event_ticker",
    "event_close_time_utc",
    "action",
    "ttc_target_minutes",
    "decision_time_utc",
    "market_ticker",
    "structural_role",
    "side",
    "outcome_yes",
    "quoted_purchase_price",
    "standard_entry_fee",
    "adjusted_net_edge_per_contract",
)

K_REQUIRED_COMMITTED_PATHS = {
    "configs/kxbtcd_candidate_e_conditional_alpha_reliability_v1_development_implementation_freeze.json",
    "docs/KXBTCD_CANDIDATE_E_CONDITIONAL_ALPHA_RELIABILITY_V1_DEVELOPMENT_EVALUATOR.md",
    "evaluate_kxbtcd_candidate_e_conditional_alpha_reliability_v1_development.py",
    "src/kxbtcd_candidate_e_conditional_alpha_reliability_v1_development.py",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v1_development_implementation.py",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v1_development_result.py",
}

class ConditionalAlphaDevelopmentError(RuntimeError):
    pass

class ConditionalAlphaFitContractError(ConditionalAlphaDevelopmentError):
    """Contextual wrapper for a frozen fitter failure; never changes fitter behavior."""

    def __init__(
        self,
        *,
        lambda_value: float,
        fold: int,
        fit_stages: Sequence[str],
        score_stage: str,
        original_type: str,
        original_message: str,
    ) -> None:
        self.lambda_value = float(lambda_value)
        self.fold = int(fold)
        self.fit_stages = tuple(str(x) for x in fit_stages)
        self.score_stage = str(score_stage)
        self.original_type = str(original_type)
        self.original_message = str(original_message)
        super().__init__(
            f"lambda={self.lambda_value} fold={self.fold} "
            f"fit={'+'.join(self.fit_stages)} score={self.score_stage}: "
            f"{self.original_type}: {self.original_message}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "lambda": self.lambda_value,
            "fold": self.fold,
            "fit_stages": list(self.fit_stages),
            "score_stage": self.score_stage,
            "original_exception_type": self.original_type,
            "original_exception_message": self.original_message,
        }

def _error(message: str) -> None:
    raise ConditionalAlphaDevelopmentError(message)

def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]

def write_csv(path: str | Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for i, row in enumerate(rows):
            if set(row) != set(fields):
                _error(f"CSV row[{i}] field set mismatch")
            writer.writerow({field: row[field] for field in fields})
    temp.replace(target)

def load_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        _error(f"JSON object required: {path}")
    return value

def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConditionalAlphaDevelopmentError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result

def _parse_outcome(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _error(f"{name} must be binary")
    text = str(value).strip()
    if text not in {"0", "1", "0.0", "1.0"}:
        _error(f"{name} must be 0 or 1")
    return int(float(text))

def validate_k_closeout_receipt(path: str | Path) -> dict[str, Any]:
    receipt = load_json(path)
    if receipt.get("schema") != "checkpoint_closeout_receipt.v1":
        _error("21N-K closeout receipt schema mismatch")
    if not str(receipt.get("checkpoint_message", "")).startswith("Checkpoint 21N-K"):
        _error("latest closeout receipt is not Checkpoint 21N-K")
    committed = {str(x) for x in receipt.get("committed_paths", ())}
    missing = sorted(K_REQUIRED_COMMITTED_PATHS - committed)
    if missing:
        _error("21N-K closeout receipt missing required implementation paths: " + ", ".join(missing))
    safety = receipt.get("safety", {})
    for key in ("blocked_path_check", "staged_path_exact_match", "staged_diff_check", "high_confidence_secret_scan"):
        if safety.get(key) != "PASS":
            _error(f"21N-K closeout safety.{key} must be PASS")
    if safety.get("remote_synchronized_before_commit") is not True:
        _error("21N-K closeout did not record synchronized baseline")
    if safety.get("worktree_clean_after_checkpoint_commit") is not True:
        _error("21N-K closeout did not record clean worktree")
    return receipt

def validate_j_b_bindings(
    *,
    feature_rows: Sequence[Mapping[str, Any]],
    feature_rows_path: str | Path,
    preparation_freeze_path: str | Path,
    preparation_closeout_path: str | Path,
) -> None:
    validate_materialized_rows(feature_rows, enforce_frozen_counts=True)
    if sha256_file(feature_rows_path) != PREPARED_FEATURE_SHA256:
        _error("conditional-alpha prepared feature CSV SHA changed")
    if canonical_rows_fingerprint(feature_rows) != FEATURE_ROWS_FINGERPRINT:
        _error("conditional-alpha feature row fingerprint changed")
    freeze = load_json(preparation_freeze_path)
    if freeze.get("schema_version") != PREPARATION_FREEZE_SCHEMA:
        _error("conditional-alpha preparation freeze schema mismatch")
    if freeze.get("preparation_fingerprint") != PREPARATION_FINGERPRINT:
        _error("conditional-alpha preparation fingerprint changed")
    if freeze.get("feature_rows_fingerprint") != FEATURE_ROWS_FINGERPRINT:
        _error("preparation freeze feature fingerprint mismatch")
    if freeze.get("prepared_output_sha256") != PREPARED_FEATURE_SHA256:
        _error("preparation freeze prepared-output SHA mismatch")
    if freeze.get("outcomes_attached") is not False:
        _error("preparation freeze must remain outcome-blind")
    closeout = load_json(preparation_closeout_path)
    if closeout.get("schema_version") != PREPARATION_CLOSEOUT_SCHEMA:
        _error("J-B preparation-closeout schema mismatch")
    if closeout.get("preparation_closeout_fingerprint") != J_B_PREPARATION_CLOSEOUT_FINGERPRINT:
        _error("J-B preparation-closeout fingerprint mismatch")
    material = closeout.get("materialization_result", {})
    if material.get("preparation_fingerprint") != PREPARATION_FINGERPRINT:
        _error("J-B closeout preparation fingerprint mismatch")
    if material.get("prepared_output_sha256") != PREPARED_FEATURE_SHA256:
        _error("J-B closeout output SHA mismatch")
    if material.get("independent_rematerialization_validation") != "PASS":
        _error("J-B independent rematerialization was not PASS")

def project_development_labels(
    sources_by_stage: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], ...]:
    if set(sources_by_stage) != set(DEVELOPMENT_STAGES):
        _error("label sources must be exactly H1_OOF, H2, and H3")
    result: list[dict[str, Any]] = []
    global_states: set[str] = set()
    for stage in DEVELOPMENT_STAGES:
        rows: list[dict[str, Any]] = []
        states: set[str] = set()
        events: set[str] = set()
        for i, source in enumerate(sources_by_stage[stage]):
            if source.get("schema_version") != LABEL_SCHEMAS[stage]:
                _error(f"{stage} label row[{i}] schema mismatch")
            if source.get("candidate_id") != PARENT_CANDIDATE_E_ID:
                continue
            state = str(source.get("state_id", "")).strip()
            event = str(source.get("event_ticker", "")).strip()
            market = str(source.get("market_ticker", "")).strip()
            if not state or not event or not market:
                _error(f"{stage} label row[{i}] identity incomplete")
            if state in states or state in global_states:
                _error(f"duplicate/cross-stage label state {state}")
            outcome = _parse_outcome(source.get("outcome"), f"{stage} label row[{i}].outcome")
            states.add(state)
            global_states.add(state)
            events.add(event)
            rows.append({
                "stage": stage,
                "state_id": state,
                "event_ticker": event,
                "market_ticker": market,
                "outcome": outcome,
            })
        if enforce_frozen_counts:
            if len(rows) != EXPECTED_STAGE_ROWS[stage]:
                _error(f"{stage} label row count changed")
            if len(events) != EXPECTED_STAGE_EVENTS[stage]:
                _error(f"{stage} label event count changed")
        result.extend(rows)
    if enforce_frozen_counts:
        if len(result) != EXPECTED_TOTAL_ROWS:
            _error("development label row count changed")
        if len({r["event_ticker"] for r in result}) != EXPECTED_TOTAL_EVENTS:
            _error("development label event count changed")
    result.sort(key=lambda x: x["state_id"])
    return tuple(result)

def validate_label_source_hashes(paths_by_stage: Mapping[str, str | Path]) -> None:
    if set(paths_by_stage) != set(DEVELOPMENT_STAGES):
        _error("label path set must be exactly H1_OOF/H2/H3")
    for stage, path in paths_by_stage.items():
        if sha256_file(path) != LABEL_SOURCE_SHA256S[stage]:
            _error(f"{stage} label source SHA mismatch")

def attach_labels(
    feature_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], ...]:
    validate_materialized_rows(feature_rows, enforce_frozen_counts=enforce_frozen_counts)
    labels: dict[str, Mapping[str, Any]] = {}
    for row in label_rows:
        state = str(row.get("state_id", ""))
        if state in labels:
            _error(f"duplicate label state {state}")
        labels[state] = row
    feature_states = {str(row["state_id"]) for row in feature_rows}
    if set(labels) != feature_states:
        missing = len(feature_states - set(labels))
        extra = len(set(labels) - feature_states)
        _error(f"label/feature exact-state mismatch missing={missing} extra={extra}")
    result: list[dict[str, Any]] = []
    for row in feature_rows:
        label = labels[str(row["state_id"])]
        if str(label["stage"]) != str(row["stage"]):
            _error("label stage mismatch")
        if str(label["event_ticker"]) != str(row["event_ticker"]):
            _error("label event mismatch")
        if str(label["market_ticker"]) != str(row["market_ticker"]):
            _error("label market mismatch")
        out = dict(row)
        out["outcome"] = int(label["outcome"])
        result.append(out)
    return tuple(result)

def _subset(rows: Sequence[Mapping[str, Any]], stages: Sequence[str]) -> list[Mapping[str, Any]]:
    allowed = set(stages)
    return [row for row in rows if str(row.get("stage")) in allowed]

def _binary_log_loss(y: int, p: float) -> float:
    if not 0.0 <= p <= 1.0 or not math.isfinite(p):
        _error("probability outside [0,1]")
    if y == 1:
        if p == 0.0:
            return math.inf
        return -math.log(p)
    if p == 1.0:
        return math.inf
    return -math.log1p(-p)

def _brier(y: int, p: float) -> float:
    return (p - float(y)) ** 2

def _event_equal_metric(rows: Sequence[Mapping[str, Any]], probability_field: str, metric: str) -> float:
    weights = event_equal_weights(rows)
    values = []
    for row, weight in zip(rows, weights):
        y = _parse_outcome(row["outcome"], "score outcome")
        p = _finite(row[probability_field], probability_field)
        value = _binary_log_loss(y, p) if metric == "log_loss" else _brier(y, p)
        values.append(weight * value)
    result = math.fsum(values)
    if not math.isfinite(result):
        _error(f"{probability_field} {metric} became non-finite")
    return result

def _fit_dict(fit: ReliabilityFit) -> dict[str, Any]:
    return {
        "lambda": fit.lambda_value,
        "iterations": fit.iterations,
        "objective": fit.objective,
        "gamma": fit.gamma_by_name(),
        "scaler": fit.scaler.as_dict(),
    }

def _score_stage(
    rows: Sequence[Mapping[str, Any]],
    fit: ReliabilityFit,
    *,
    fold: int,
    selected_lambda: float | None = None,
) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        alpha, p_adj = apply_fit_probability(row, fit)
        q = _finite(row["market_midpoint_yes_probability"], "q")
        p_e = _finite(row["candidate_probability"], "pE")
        p50 = q + 0.5 * (p_e - q)
        if not (0.0 < alpha < 1.0):
            _error("conditional alpha left strict interior")
        lo, hi = sorted((q, p_e))
        if not lo - 1e-15 <= p_adj <= hi + 1e-15:
            _error("conditional probability left q/pE endpoints")
        result.append({
            "schema_version": ROLLING_PREDICTION_SCHEMA,
            "candidate_id": CANDIDATE_ID,
            "selected_lambda": "" if selected_lambda is None else repr(float(selected_lambda)),
            "fold": str(fold),
            "stage": str(row["stage"]),
            "state_id": str(row["state_id"]),
            "event_ticker": str(row["event_ticker"]),
            "event_close_time_utc": str(row["event_close_time_utc"]),
            "market_ticker": str(row["market_ticker"]),
            "structural_role": str(row["structural_role"]),
            "ttc_target_minutes": str(row["ttc_target_minutes"]),
            "decision_time_utc": str(row["decision_time_utc"]),
            "outcome": str(int(row["outcome"])),
            "candidate_probability": repr(p_e),
            "market_midpoint_yes_probability": repr(q),
            "global_alpha_0_50_probability": repr(p50),
            "conditional_alpha": repr(alpha),
            "adjusted_yes_probability": repr(p_adj),
            "yes_bid": str(row["yes_bid"]),
            "yes_ask": str(row["yes_ask"]),
        })
    return tuple(result)

def _fit_with_frozen_context(
    rows: Sequence[Mapping[str, Any]],
    *,
    lambda_value: float,
    fold: int,
    fit_stages: Sequence[str],
    score_stage: str,
) -> ReliabilityFit:
    """Call the unchanged frozen fitter and add orchestration context on failure."""
    from .kxbtcd_candidate_e_conditional_alpha_reliability_v1 import ConditionalAlphaV1Error
    try:
        return fit_conditional_alpha(rows, lambda_value=lambda_value)
    except ConditionalAlphaV1Error as exc:
        raise ConditionalAlphaFitContractError(
            lambda_value=lambda_value,
            fold=fold,
            fit_stages=fit_stages,
            score_stage=score_stage,
            original_type=type(exc).__name__,
            original_message=str(exc),
        ) from exc

def rolling_origin_lambda_evaluation(
    labeled_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[float, tuple[dict[str, Any], ...]], dict[float, list[dict[str, Any]]]]:
    lambda_scores: list[dict[str, Any]] = []
    predictions: dict[float, tuple[dict[str, Any], ...]] = {}
    fits: dict[float, list[dict[str, Any]]] = {}
    for lam in LAMBDA_GRID:
        pooled: list[dict[str, Any]] = []
        lam_fits: list[dict[str, Any]] = []
        for fold, fit_stages, score_stage in FOLDS:
            fit_rows = _subset(labeled_rows, fit_stages)
            score_rows = _subset(labeled_rows, (score_stage,))
            fit = _fit_with_frozen_context(
                fit_rows,
                lambda_value=lam,
                fold=fold,
                fit_stages=fit_stages,
                score_stage=score_stage,
            )
            scored = _score_stage(score_rows, fit, fold=fold)
            pooled.extend(scored)
            lam_fits.append({
                "fold": fold,
                "fit_stages": list(fit_stages),
                "score_stage": score_stage,
                "fit": _fit_dict(fit),
            })
        if len({r["event_ticker"] for r in pooled}) != SCORE_EVENT_COUNT:
            _error("pooled rolling-origin score event count changed")
        ll = _event_equal_metric(pooled, "adjusted_yes_probability", "log_loss")
        lambda_scores.append({
            "lambda": lam,
            "pooled_H2_H3_event_equal_log_loss": ll,
        })
        predictions[lam] = tuple(pooled)
        fits[lam] = lam_fits
    return lambda_scores, predictions, fits

def select_lambda(lambda_scores: Sequence[Mapping[str, Any]]) -> float:
    if {float(row["lambda"]) for row in lambda_scores} != set(LAMBDA_GRID):
        _error("lambda score set changed")
    ordered = sorted(
        ((float(row["pooled_H2_H3_event_equal_log_loss"]), -float(row["lambda"]), float(row["lambda"])) for row in lambda_scores),
        key=lambda x: (x[0], x[1]),
    )
    return ordered[0][2]

def _selected_prediction_rows(
    labeled_rows: Sequence[Mapping[str, Any]],
    selected_lambda: float,
) -> tuple[tuple[dict[str, Any], ...], list[dict[str, Any]]]:
    pooled: list[dict[str, Any]] = []
    fits: list[dict[str, Any]] = []
    for fold, fit_stages, score_stage in FOLDS:
        fit = _fit_with_frozen_context(
            _subset(labeled_rows, fit_stages),
            lambda_value=selected_lambda,
            fold=fold,
            fit_stages=fit_stages,
            score_stage=score_stage,
        )
        scored = _score_stage(_subset(labeled_rows, (score_stage,)), fit, fold=fold, selected_lambda=selected_lambda)
        pooled.extend(scored)
        fits.append({
            "fold": fold,
            "fit_stages": list(fit_stages),
            "score_stage": score_stage,
            "fit": _fit_dict(fit),
        })
    return tuple(pooled), fits

def _event_median_improvement(rows: Sequence[Mapping[str, Any]]) -> float:
    by_event: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        by_event.setdefault(str(row["event_ticker"]), []).append(row)
    improvements = []
    for event_rows in by_event.values():
        n = len(event_rows)
        if n == 0:
            _error("empty event in median computation")
        base = math.fsum(
            _binary_log_loss(_parse_outcome(r["outcome"], "outcome"), _finite(r["global_alpha_0_50_probability"], "p50"))
            for r in event_rows
        ) / n
        cond = math.fsum(
            _binary_log_loss(_parse_outcome(r["outcome"], "outcome"), _finite(r["adjusted_yes_probability"], "p_adj"))
            for r in event_rows
        ) / n
        improvements.append(base - cond)
    if len(improvements) != SCORE_EVENT_COUNT:
        _error("event-level improvement count changed")
    result = float(median(improvements))
    if not math.isfinite(result):
        _error("median event improvement non-finite")
    return result

def build_probability_gate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len({r["event_ticker"] for r in rows}) != SCORE_EVENT_COUNT:
        _error("probability gate score event count changed")
    metrics: dict[str, Any] = {"pooled": {}, "by_stage": {}}
    fields = {
        "kalshi_q": "market_midpoint_yes_probability",
        "candidate_e": "candidate_probability",
        "global_alpha_0_50": "global_alpha_0_50_probability",
        "conditional_alpha": "adjusted_yes_probability",
    }
    for label, field in fields.items():
        metrics["pooled"][label] = {
            "log_loss": _event_equal_metric(rows, field, "log_loss"),
            "brier": _event_equal_metric(rows, field, "brier"),
        }
    for stage in SCORE_STAGES:
        stage_rows = [r for r in rows if r["stage"] == stage]
        metrics["by_stage"][stage] = {}
        for label, field in fields.items():
            metrics["by_stage"][stage][label] = {
                "log_loss": _event_equal_metric(stage_rows, field, "log_loss"),
                "brier": _event_equal_metric(stage_rows, field, "brier"),
            }
    med = _event_median_improvement(rows)
    p = metrics["pooled"]
    conditions = {
        "pooled_log_loss_lt_kalshi_q": p["conditional_alpha"]["log_loss"] < p["kalshi_q"]["log_loss"],
        "pooled_log_loss_lt_candidate_e": p["conditional_alpha"]["log_loss"] < p["candidate_e"]["log_loss"],
        "pooled_log_loss_lt_global_alpha_0_50": p["conditional_alpha"]["log_loss"] < p["global_alpha_0_50"]["log_loss"],
        "pooled_brier_le_kalshi_q": p["conditional_alpha"]["brier"] <= p["kalshi_q"]["brier"],
        "pooled_brier_le_candidate_e": p["conditional_alpha"]["brier"] <= p["candidate_e"]["brier"],
        "pooled_brier_le_global_alpha_0_50": p["conditional_alpha"]["brier"] <= p["global_alpha_0_50"]["brier"],
        "H2_log_loss_lt_global_alpha_0_50": metrics["by_stage"]["H2"]["conditional_alpha"]["log_loss"] < metrics["by_stage"]["H2"]["global_alpha_0_50"]["log_loss"],
        "H3_log_loss_lt_global_alpha_0_50": metrics["by_stage"]["H3"]["conditional_alpha"]["log_loss"] < metrics["by_stage"]["H3"]["global_alpha_0_50"]["log_loss"],
        "median_event_log_loss_improvement_gt_zero": med > 0.0,
        "all_fit_prediction_values_finite_and_bounded": True,
        "lineage_and_contamination_checks_pass": True,
    }
    return {
        "status": "PASS" if all(conditions.values()) else "FAIL",
        "conditions": conditions,
        "metrics": metrics,
        "median_event_alpha_0_50_minus_conditional_log_loss": med,
    }

def _market_outcomes(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
    result: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row["event_ticker"]), str(row["market_ticker"]))
        y = _parse_outcome(row["outcome"], "outcome")
        prior = result.setdefault(key, y)
        if prior != y:
            _error(f"inconsistent outcome for {key}")
    return result

def build_entry_decisions(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    states = []
    for row in rows:
        state = dict(row)
        states.append(state)
    raw_decisions = select_entry_events(states)
    outcomes = _market_outcomes(rows)
    if len(raw_decisions) != SCORE_EVENT_COUNT:
        _error("entry decision event count changed")
    decisions = []
    for index, decision in enumerate(raw_decisions):
        block = f"B{index // BLOCK_EVENTS}"
        if index // BLOCK_EVENTS >= BLOCK_COUNT:
            _error("chronological block overflow")
        base = {
            "schema_version": ENTRY_DECISION_SCHEMA,
            "candidate_id": CANDIDATE_ID,
            "stage": str(decision["stage"]),
            "chronological_block": block,
            "event_ticker": str(decision["event_ticker"]),
            "event_close_time_utc": str(decision["event_close_time_utc"]),
        }
        if decision["action"] == "ABSTAIN":
            decisions.append({
                **base,
                "action": "ABSTAIN",
                "ttc_target_minutes": "",
                "decision_time_utc": "",
                "market_ticker": "",
                "structural_role": "",
                "side": "",
                "outcome_yes": "",
                "quoted_purchase_price": "",
                "standard_entry_fee": "",
                "adjusted_net_edge_per_contract": "",
            })
        else:
            key = (str(decision["event_ticker"]), str(decision["market_ticker"]))
            if key not in outcomes:
                _error("selected entry market missing outcome")
            decisions.append({
                **base,
                "action": "ENTER",
                "ttc_target_minutes": str(decision["ttc_target_minutes"]),
                "decision_time_utc": str(decision["decision_time_utc"]),
                "market_ticker": str(decision["market_ticker"]),
                "structural_role": str(decision["structural_role"]),
                "side": str(decision["side"]),
                "outcome_yes": str(outcomes[key]),
                "quoted_purchase_price": str(decision["quoted_purchase_price"]),
                "standard_entry_fee": str(decision["standard_entry_fee"]),
                "adjusted_net_edge_per_contract": str(decision["adjusted_net_edge_per_contract"]),
            })
    counts = {f"B{i}": 0 for i in range(BLOCK_COUNT)}
    for row in decisions:
        counts[row["chronological_block"]] += 1
    if any(v != BLOCK_EVENTS for v in counts.values()):
        _error("chronological blocks are not five contiguous 300-event blocks")
    return tuple(decisions)

def _scenario(decisions: Sequence[Mapping[str, Any]], stress: Decimal) -> dict[str, Any]:
    pnls: list[Decimal] = []
    entry_count = 0
    by_stage = {stage: [] for stage in SCORE_STAGES}
    by_block = {f"B{i}": [] for i in range(BLOCK_COUNT)}
    stage_entries = {stage: 0 for stage in SCORE_STAGES}
    for row in decisions:
        stage = str(row["stage"])
        block = str(row["chronological_block"])
        pnl = Decimal("0")
        if row["action"] == "ENTER":
            entry_count += 1
            stage_entries[stage] += 1
            quoted = Decimal(str(row["quoted_purchase_price"]))
            price = quoted + stress
            if price < 0 or price > 1:
                return {
                    "valid": False,
                    "stress_dollars": format(stress, "f"),
                    "reason": f"stressed purchase price outside [0,1] for event {row['event_ticker']}",
                }
            fee = standard_entry_fee(price)
            y_yes = int(row["outcome_yes"])
            side = str(row["side"])
            win = y_yes if side == "YES" else 1 - y_yes
            pnl = Decimal(win) - price - fee
        pnls.append(pnl)
        by_stage[stage].append(pnl)
        by_block[block].append(pnl)
    total = sum(pnls, Decimal("0"))
    n = Decimal(len(decisions))
    if n != Decimal(SCORE_EVENT_COUNT):
        _error("economic scenario event count changed")
    return {
        "valid": True,
        "stress_dollars": format(stress, "f"),
        "entry_count": entry_count,
        "entry_count_by_stage": stage_entries,
        "total_net_pnl": format(total, "f"),
        "mean_net_pnl_per_event": format(total / n, "f"),
        "stage_mean_net_pnl_per_event": {
            stage: format(sum(vals, Decimal("0")) / Decimal(len(vals)), "f")
            for stage, vals in by_stage.items()
        },
        "block_mean_net_pnl_per_event": {
            block: format(sum(vals, Decimal("0")) / Decimal(len(vals)), "f")
            for block, vals in by_block.items()
        },
        "positive_base_block_count": sum(
            1 for vals in by_block.values()
            if sum(vals, Decimal("0")) / Decimal(len(vals)) > 0
        ) if stress == Decimal("0.00") else None,
    }

def build_economic_gate(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    decisions = build_entry_decisions(rows)
    scenarios = {format(s, "f"): _scenario(decisions, s) for s in STRESSES}
    base = scenarios["0.00"]
    adverse1 = scenarios["0.01"]
    if not base["valid"]:
        _error("base economic scenario unexpectedly invalid")
    conditions = {
        "minimum_total_entries_ge_100": base["entry_count"] >= MIN_TOTAL_ENTRIES,
        "minimum_H2_entries_ge_20": base["entry_count_by_stage"]["H2"] >= MIN_STAGE_ENTRIES,
        "minimum_H3_entries_ge_20": base["entry_count_by_stage"]["H3"] >= MIN_STAGE_ENTRIES,
        "base_pooled_mean_gt_zero": Decimal(base["mean_net_pnl_per_event"]) > 0,
        "plus_1c_scenario_valid": bool(adverse1["valid"]),
        "plus_1c_pooled_mean_gt_zero": bool(adverse1["valid"]) and Decimal(adverse1["mean_net_pnl_per_event"]) > 0,
        "base_positive_blocks_ge_4_of_5": int(base["positive_base_block_count"]) >= 4,
        "newest_B4_base_mean_gt_zero": Decimal(base["block_mean_net_pnl_per_event"]["B4"]) > 0,
        "H3_base_mean_gt_zero": Decimal(base["stage_mean_net_pnl_per_event"]["H3"]) > 0,
    }
    return ({
        "status": "PASS" if all(conditions.values()) else "FAIL",
        "conditions": conditions,
        "scenarios": scenarios,
        "stress_interpretation": "quoted-price sensitivity only; not a fill/latency/depth/queue simulation",
    }, decisions)

def full_development_fit(labeled_rows: Sequence[Mapping[str, Any]], selected_lambda: float) -> dict[str, Any]:
    fit = fit_conditional_alpha(labeled_rows, lambda_value=selected_lambda)
    return _fit_dict(fit)

def build_development_evaluation(
    feature_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    labeled = attach_labels(feature_rows, label_rows, enforce_frozen_counts=enforce_frozen_counts)
    lambda_scores, _, all_fold_fits = rolling_origin_lambda_evaluation(labeled)
    selected = select_lambda(lambda_scores)
    selected_predictions, selected_fits = _selected_prediction_rows(labeled, selected)
    probability_gate = build_probability_gate(selected_predictions)

    economic_gate: dict[str, Any]
    entry_decisions: tuple[dict[str, Any], ...]
    final_fit: dict[str, Any] | None = None

    if probability_gate["status"] != "PASS":
        economic_gate = {
            "status": "NOT_RUN_PROBABILITY_GATE_FAILED",
            "reason": "Evidence-minimizing sequential gate: no new conditional-alpha P&L is opened after a probability-gate failure.",
        }
        entry_decisions = tuple()
        overall = "FAIL_PROBABILITY_GATE"
    else:
        economic_gate, entry_decisions = build_economic_gate(selected_predictions)
        if economic_gate["status"] != "PASS":
            overall = "FAIL_ECONOMIC_GATE"
        else:
            overall = "PASS"
            final_fit = full_development_fit(labeled, selected)

    label_fingerprint = canonical_sha256([
        {
            "stage": row["stage"],
            "state_id": row["state_id"],
            "event_ticker": row["event_ticker"],
            "market_ticker": row["market_ticker"],
            "outcome": int(row["outcome"]),
        }
        for row in sorted(label_rows, key=lambda x: str(x["state_id"]))
    ])

    evaluation = {
        "schema_version": DEVELOPMENT_EVALUATION_SCHEMA,
        "candidate_id": CANDIDATE_ID,
        "predeclaration_fingerprint": PREDECLARATION_FINGERPRINT,
        "preparation_fingerprint": PREPARATION_FINGERPRINT,
        "feature_rows_fingerprint": FEATURE_ROWS_FINGERPRINT,
        "development_label_fingerprint": label_fingerprint,
        "development_events": len({str(r["event_ticker"]) for r in labeled}),
        "development_rows": len(labeled),
        "lambda_grid": list(LAMBDA_GRID),
        "lambda_scores": lambda_scores,
        "selected_lambda": selected,
        "selected_fold_fits": selected_fits,
        "all_lambda_fold_fits": {repr(lam): all_fold_fits[lam] for lam in LAMBDA_GRID},
        "probability_gate": probability_gate,
        "economic_gate": economic_gate,
        "overall_status": overall,
        "full_development_fit": final_fit,
        "sequencing": {
            "probability_gate_first": True,
            "economic_gate_only_if_probability_passes": True,
            "full_development_fit_only_if_both_gates_pass": True,
        },
        "safety": {
            "C1_C2_accessed": False,
            "C3_accessed": False,
            "protected_reserve_accessed": False,
            "network_accessed": False,
            "paper_execution": False,
            "demo_execution": False,
            "real_money_execution": False,
            "orders_submitted": False,
        },
    }
    evaluation["evaluation_fingerprint"] = canonical_sha256(evaluation)
    return evaluation, selected_predictions, entry_decisions

DEVELOPMENT_FAILURE_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_development_failure.v1"
DEVELOPMENT_FAILURE_RECEIPT_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_development_failure_receipt.v1"

def build_optimizer_failure_evaluation(
    *,
    feature_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    failure: ConditionalAlphaFitContractError,
) -> dict[str, Any]:
    """Persist a scientific FAIL without changing or bypassing the frozen optimizer."""
    label_fingerprint = canonical_sha256([
        {
            "stage": row["stage"],
            "state_id": row["state_id"],
            "event_ticker": row["event_ticker"],
            "market_ticker": row["market_ticker"],
            "outcome": int(row["outcome"]),
        }
        for row in sorted(label_rows, key=lambda x: str(x["state_id"]))
    ])
    evaluation = {
        "schema_version": DEVELOPMENT_FAILURE_SCHEMA,
        "candidate_id": CANDIDATE_ID,
        "predeclaration_fingerprint": PREDECLARATION_FINGERPRINT,
        "preparation_fingerprint": PREPARATION_FINGERPRINT,
        "feature_rows_fingerprint": FEATURE_ROWS_FINGERPRINT,
        "development_label_fingerprint": label_fingerprint,
        "development_events": len({str(r["event_ticker"]) for r in feature_rows}),
        "development_rows": len(feature_rows),
        "overall_status": "FAIL_OPTIMIZER_CONTRACT",
        "failure": {
            "phase": "rolling_origin_lambda_evaluation",
            **failure.as_dict(),
        },
        "lambda_selection_performed": False,
        "probability_gate": {"status": "NOT_RUN_OPTIMIZER_CONTRACT_FAILED"},
        "economic_gate": {"status": "NOT_RUN_OPTIMIZER_CONTRACT_FAILED"},
        "full_development_fit": None,
        "sequencing": {
            "stop_immediately_on_required_fit_failure": True,
            "later_lambdas_skipped_after_failure": True,
            "probability_gate_not_run": True,
            "economic_gate_not_run": True,
            "full_development_fit_not_run": True,
        },
        "safety": {
            "C1_C2_accessed": False,
            "C3_accessed": False,
            "protected_reserve_accessed": False,
            "network_accessed": False,
            "paper_execution": False,
            "demo_execution": False,
            "real_money_execution": False,
            "orders_submitted": False,
        },
    }
    evaluation["evaluation_fingerprint"] = canonical_sha256(evaluation)
    return evaluation

def build_failure_receipt(
    *,
    evaluation: Mapping[str, Any],
    evaluation_path: str | Path,
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    receipt = {
        "schema_version": DEVELOPMENT_FAILURE_RECEIPT_SCHEMA,
        "candidate_id": CANDIDATE_ID,
        "evaluation_fingerprint": evaluation["evaluation_fingerprint"],
        "overall_status": evaluation["overall_status"],
        "input_sha256s": dict(input_hashes),
        "output_sha256s": {
            "evaluation_sha256": sha256_file(evaluation_path),
            "rolling_predictions_sha256": None,
            "entry_decisions_sha256": None,
        },
        "safety": dict(evaluation["safety"]),
    }
    receipt["receipt_fingerprint"] = canonical_sha256(receipt)
    return receipt

def build_result_receipt(
    *,
    evaluation: Mapping[str, Any],
    prediction_path: str | Path,
    entry_path: str | Path | None,
    evaluation_path: str | Path,
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    artifacts = {
        "evaluation_sha256": sha256_file(evaluation_path),
        "rolling_predictions_sha256": sha256_file(prediction_path),
        "entry_decisions_sha256": None if entry_path is None else sha256_file(entry_path),
    }
    receipt = {
        "schema_version": DEVELOPMENT_RECEIPT_SCHEMA,
        "candidate_id": CANDIDATE_ID,
        "evaluation_fingerprint": evaluation["evaluation_fingerprint"],
        "overall_status": evaluation["overall_status"],
        "input_sha256s": dict(input_hashes),
        "output_sha256s": artifacts,
        "safety": dict(evaluation["safety"]),
    }
    receipt["receipt_fingerprint"] = canonical_sha256(receipt)
    return receipt

__all__ = [
    "ConditionalAlphaDevelopmentError",
    "ConditionalAlphaFitContractError",
    "DEVELOPMENT_EVALUATION_SCHEMA",
    "DEVELOPMENT_FAILURE_SCHEMA",
    "DEVELOPMENT_FAILURE_RECEIPT_SCHEMA",
    "DEVELOPMENT_RECEIPT_SCHEMA",
    "ENTRY_DECISION_FIELDS",
    "FEATURE_ROWS_FINGERPRINT",
    "J_B_PREPARATION_CLOSEOUT_FINGERPRINT",
    "LABEL_SOURCE_SHA256S",
    "PREPARATION_FINGERPRINT",
    "PREPARED_FEATURE_SHA256",
    "ROLLING_PREDICTION_FIELDS",
    "attach_labels",
    "build_development_evaluation",
    "build_failure_receipt",
    "build_optimizer_failure_evaluation",
    "build_result_receipt",
    "load_json",
    "project_development_labels",
    "read_csv",
    "sha256_file",
    "validate_j_b_bindings",
    "validate_k_closeout_receipt",
    "validate_label_source_hashes",
    "write_csv",
]
