"""Frozen development-only orchestration for Candidate-E Entry Model v1.

This module is intentionally narrow. It binds the accepted outcome-blind
Checkpoint-21M preparation freeze to the already-exposed H1_OOF/H2/H3 labels,
then invokes the frozen D-021L-04 rolling-origin evaluator.

It does not read C1/C2/C3, the protected reserve, Strategy-v1 economics, or any
execution interface.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_entry_model_v1 import (
    CANDIDATE_E_ID,
    DEVELOPMENT_STAGES,
    EXPECTED_DEVELOPMENT_EVENT_COUNTS,
    EXPECTED_DEVELOPMENT_EVENTS,
    EXPECTED_DEVELOPMENT_ROW_COUNTS,
    EXPECTED_DEVELOPMENT_ROWS,
    LAMBDA_GRID,
    MODEL_ID,
    PARAMETER_NAMES,
    CandidateEEntryModelV1Error,
    attach_development_labels,
    canonical_rows_fingerprint,
    canonical_sha256,
    evaluate_development_rolling_origin,
    fit_residual_logistic,
    model2_vs_candidate_e_diagnostics,
    score_rows,
    validate_feature_rows,
)
from .kxbtcd_candidate_e_entry_model_v1_materialization import (
    FEATURE_FIELDS,
    FREEZE_SCHEMA_VERSION,
    H1_PREDICTION_SCHEMA,
    H2_PREDICTION_SCHEMA,
    H3_PREDICTION_SCHEMA,
)

DEVELOPMENT_EVALUATION_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_development_evaluation.v1"
DEVELOPMENT_RECEIPT_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_development_receipt.v1"
EXPECTED_PREPARATION_FINGERPRINT = "2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d"
EXPECTED_FEATURE_ROWS_FINGERPRINT = "a726785e667dc42cef75a7b1f9c0b42ae81a4906b1d72ff5eb0f58ed5083b2a7"
EXPECTED_EVENT_MAP_FINGERPRINT = "36bd74d8576cf8656a4d4a352330fabd2294c322c5cd91854ed47892fe04a266"

# The preparation freeze remains immutable and must retain the original pre-outcome
# core hash. D-021M-05 later accepted exactly one post-outcome numerical repair:
# sum(weights) -> math.fsum(weights) in the invariant check only.
PREPARATION_FROZEN_CORE_SHA256 = "1e56a207e72a96a4425d0c6c6796d9781eac363baef5bb0dab3b3b58daa34a1b"
ACCEPTED_POST_OUTCOME_CORE_SHA256 = "ce54846f85f3d338bc0f3aadd64d8cc8b9828c0c2ac2b5454f97771ec1a89ee1"

PREDICTION_SCHEMAS = {
    "H1_OOF": H1_PREDICTION_SCHEMA,
    "H2": H2_PREDICTION_SCHEMA,
    "H3": H3_PREDICTION_SCHEMA,
}


class CandidateEEntryDevelopmentError(RuntimeError):
    """Raised when the frozen Model-2 development evaluation contract is violated."""


def _error(message: str) -> None:
    raise CandidateEEntryDevelopmentError(message)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        _error(f"JSON object required: {path}")
    return value


def _parse_outcome(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _error(f"{name} must be binary integer")
    text = str(value).strip()
    if text not in {"0", "1", "0.0", "1.0"}:
        _error(f"{name} must be 0 or 1")
    result = int(float(text))
    if result not in (0, 1):
        _error(f"{name} must be 0 or 1")
    return result


def project_exposed_development_labels(
    sources_by_stage: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], ...]:
    """Project only already-exposed Candidate-E development labels.

    H1 may contain the rejected momentum challenger; non-Candidate-E rows are
    ignored exactly as in outcome-blind preparation. No row eligibility is
    derived from the outcome.
    """
    if set(sources_by_stage) != set(DEVELOPMENT_STAGES):
        _error("label sources must be exactly H1_OOF, H2, and H3")

    result: list[dict[str, Any]] = []
    global_states: set[str] = set()
    for stage in DEVELOPMENT_STAGES:
        schema = PREDICTION_SCHEMAS[stage]
        stage_rows: list[dict[str, Any]] = []
        stage_states: set[str] = set()
        stage_events: set[str] = set()
        for index, source in enumerate(sources_by_stage[stage]):
            if source.get("schema_version") != schema:
                _error(f"{stage} label row[{index}] schema mismatch")
            if source.get("candidate_id") != CANDIDATE_E_ID:
                continue
            state = str(source.get("state_id", "")).strip()
            event = str(source.get("event_ticker", "")).strip()
            market = str(source.get("market_ticker", "")).strip()
            if not state or not event or not market:
                _error(f"{stage} label row[{index}] identity is incomplete")
            if state in stage_states:
                _error(f"duplicate {stage} Candidate-E label state_id {state}")
            if state in global_states:
                _error(f"development label state crosses stages: {state}")
            outcome = _parse_outcome(source.get("outcome"), f"{stage} label row[{index}].outcome")
            stage_states.add(state)
            global_states.add(state)
            stage_events.add(event)
            stage_rows.append(
                {
                    "stage": stage,
                    "state_id": state,
                    "event_ticker": event,
                    "market_ticker": market,
                    "outcome": outcome,
                }
            )
        if enforce_frozen_counts:
            if len(stage_rows) != EXPECTED_DEVELOPMENT_ROW_COUNTS[stage]:
                _error(
                    f"{stage} Candidate-E label count changed: {len(stage_rows)} != "
                    f"{EXPECTED_DEVELOPMENT_ROW_COUNTS[stage]}"
                )
            if len(stage_events) != EXPECTED_DEVELOPMENT_EVENT_COUNTS[stage]:
                _error(
                    f"{stage} label event count changed: {len(stage_events)} != "
                    f"{EXPECTED_DEVELOPMENT_EVENT_COUNTS[stage]}"
                )
        result.extend(stage_rows)

    if enforce_frozen_counts:
        if len(result) != EXPECTED_DEVELOPMENT_ROWS:
            _error(f"development label row count changed: {len(result)} != {EXPECTED_DEVELOPMENT_ROWS}")
        if len({row['event_ticker'] for row in result}) != EXPECTED_DEVELOPMENT_EVENTS:
            _error("development label event count changed")
    result.sort(key=lambda row: row["state_id"])
    return tuple(result)


def validate_preparation_binding(
    feature_rows: Sequence[Mapping[str, Any]],
    freeze: Mapping[str, Any],
    *,
    feature_rows_path: str | Path,
    label_source_paths: Mapping[str, str | Path],
    repo_root: str | Path,
) -> None:
    """Fail closed unless inputs exactly bind to the accepted pre-outcome freeze."""
    if freeze.get("schema_version") != FREEZE_SCHEMA_VERSION:
        _error("preparation freeze schema mismatch")
    if freeze.get("model_id") != MODEL_ID:
        _error("preparation freeze model mismatch")
    if freeze.get("preparation_fingerprint") != EXPECTED_PREPARATION_FINGERPRINT:
        _error("preparation fingerprint is not the accepted Checkpoint-21M freeze")
    if freeze.get("feature_rows_fingerprint") != EXPECTED_FEATURE_ROWS_FINGERPRINT:
        _error("feature-row fingerprint is not the accepted Checkpoint-21M freeze")
    if freeze.get("development_event_map_fingerprint") != EXPECTED_EVENT_MAP_FINGERPRINT:
        _error("development event-map fingerprint is not the accepted Checkpoint-21M freeze")

    for key in (
        "outcomes_in_feature_rows",
        "strategy_v1_pnl_calculated",
        "c3_opened_for_model2",
        "protected_reserve_accessed",
        "execution_enabled",
    ):
        if freeze.get(key) is not False:
            _error(f"preparation safety flag changed: {key}={freeze.get(key)!r}")

    validate_feature_rows(feature_rows, enforce_frozen_counts=True)
    if tuple(feature_rows[0].keys()) != tuple(FEATURE_FIELDS):
        _error("persisted feature CSV field order changed")
    if canonical_rows_fingerprint(feature_rows) != EXPECTED_FEATURE_ROWS_FINGERPRINT:
        _error("persisted feature rows do not reproduce the accepted fingerprint")

    prepared_hashes = freeze.get("prepared_output_sha256s")
    if not isinstance(prepared_hashes, dict):
        _error("preparation freeze missing output hashes")
    if sha256_file(feature_rows_path) != prepared_hashes.get("feature_rows"):
        _error("feature CSV hash does not match accepted preparation freeze")

    source_hashes = freeze.get("source_file_sha256s")
    if not isinstance(source_hashes, dict):
        _error("preparation freeze missing source hashes")
    source_key = {"H1_OOF": "h1_predictions", "H2": "h2_predictions", "H3": "h3_predictions"}
    for stage, path in label_source_paths.items():
        if stage not in source_key:
            _error(f"unexpected label source stage {stage}")
        if sha256_file(path) != source_hashes.get(source_key[stage]):
            _error(f"{stage} prediction source hash does not match accepted preparation freeze")

    implementation = freeze.get("implementation_sha256s")
    if not isinstance(implementation, dict):
        _error("preparation freeze missing implementation hashes")
    root = Path(repo_root)
    core_rel = "src/kxbtcd_candidate_e_entry_model_v1.py"

    # Preserve the original preparation receipt exactly. The freeze is not amended
    # or rewritten after outcomes became exposed.
    frozen_core_hash = implementation.get(core_rel)
    if frozen_core_hash != PREPARATION_FROZEN_CORE_SHA256:
        _error("preparation freeze core hash is not the original accepted pre-outcome hash")

    # Separately require the only accepted post-outcome core revision. This is not
    # an allow-any-change escape hatch: any other current core hash fails closed.
    current_core_hash = sha256_file(root / core_rel)
    if current_core_hash != ACCEPTED_POST_OUTCOME_CORE_SHA256:
        _error("current Model-2 core hash is not the accepted D-021M-05 repaired implementation")


def _subset(rows: Sequence[Mapping[str, Any]], stages: Sequence[str]) -> list[Mapping[str, Any]]:
    allowed = set(stages)
    return [row for row in rows if str(row.get("stage")) in allowed]


def _fit_to_dict(fit: Any) -> dict[str, Any]:
    return {
        "lambda": fit.lambda_value,
        "iterations": fit.iterations,
        "objective": fit.objective,
        "coefficients": {name: value for name, value in zip(PARAMETER_NAMES, fit.coefficients)},
        "scaler": fit.scaler.as_dict(),
    }


def build_development_evaluation(
    feature_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> dict[str, Any]:
    """Attach labels and execute the unchanged frozen rolling-origin procedure."""
    labeled = attach_development_labels(
        feature_rows,
        label_rows,
        enforce_frozen_counts=enforce_frozen_counts,
    )
    evaluation = evaluate_development_rolling_origin(
        labeled,
        enforce_frozen_counts=enforce_frozen_counts,
    )
    selected = evaluation.selected_lambda

    scored_selected: list[dict[str, Any]] = []
    selected_stage_diagnostics: dict[str, Any] = {}
    for fit_stages, score_stage in ((('H1_OOF',), 'H2'), (('H1_OOF', 'H2'), 'H3')):
        fit = fit_residual_logistic(_subset(labeled, fit_stages), lambda_value=selected)
        scored = score_rows(_subset(labeled, (score_stage,)), fit)
        scored_selected.extend(dict(row) for row in scored)
        selected_stage_diagnostics[score_stage] = model2_vs_candidate_e_diagnostics(scored)

    pooled_diagnostics = model2_vs_candidate_e_diagnostics(scored_selected)
    label_fingerprint = canonical_sha256(
        [
            {
                "stage": row["stage"],
                "state_id": row["state_id"],
                "event_ticker": row["event_ticker"],
                "market_ticker": row["market_ticker"],
                "outcome": int(row["outcome"]),
            }
            for row in sorted(label_rows, key=lambda item: str(item["state_id"]))
        ]
    )

    return {
        "schema_version": DEVELOPMENT_EVALUATION_SCHEMA,
        "model_id": MODEL_ID,
        "preparation_fingerprint": EXPECTED_PREPARATION_FINGERPRINT,
        "development_feature_rows": len(feature_rows),
        "development_events": len({str(row["event_ticker"]) for row in feature_rows}),
        "development_label_fingerprint": label_fingerprint,
        "lambda_grid": list(LAMBDA_GRID),
        "selected_lambda": selected,
        "lambda_scores": [dict(row) for row in evaluation.lambda_scores],
        "selected_rolling_origin_diagnostics": {
            "H2": selected_stage_diagnostics["H2"],
            "H3": selected_stage_diagnostics["H3"],
            "pooled_H2_H3": pooled_diagnostics,
        },
        "fold_fits": [dict(row) for row in evaluation.fold_fits],
        "full_development_fit": _fit_to_dict(evaluation.full_development_fit),
        "interpretation": {
            "development_selection_only": True,
            "validation_gate_evaluated": False,
            "profitability_claim": False,
        },
        "safety": {
            "c1_c2_opened_for_model2": False,
            "c3_opened_for_model2": False,
            "protected_reserve_accessed": False,
            "strategy_v1_pnl_calculated": False,
            "execution_enabled": False,
        },
    }


def evaluation_fingerprint(evaluation: Mapping[str, Any]) -> str:
    return canonical_sha256(evaluation)


__all__ = [
    "CandidateEEntryDevelopmentError",
    "DEVELOPMENT_EVALUATION_SCHEMA",
    "DEVELOPMENT_RECEIPT_SCHEMA",
    "EXPECTED_PREPARATION_FINGERPRINT",
    "build_development_evaluation",
    "evaluation_fingerprint",
    "load_json",
    "project_exposed_development_labels",
    "sha256_file",
    "validate_preparation_binding",
]
