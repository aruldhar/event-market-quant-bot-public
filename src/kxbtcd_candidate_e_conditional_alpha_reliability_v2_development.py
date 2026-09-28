"""Checkpoint 21N-M-C conditional-alpha v2 H-development evaluator wiring.

This module inherits the already-frozen conditional-alpha evidence, metric, gate,
fee, and entry-policy machinery from v1, but routes every learned fit through
the separately frozen v2 exact-Hessian damped-Newton fitter.

21N-M-C is implementation-only. The companion real-data CLI is fail-closed until
this checkpoint itself has been safely closed and pushed.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    DEVELOPMENT_STAGES,
    LAMBDA_GRID,
    PARAMETER_NAMES,
    adjusted_yes_probability,
    canonical_sha256,
)
from .kxbtcd_candidate_e_conditional_alpha_reliability_v1_development import (
    BLOCK_COUNT,
    BLOCK_EVENTS,
    ENTRY_DECISION_FIELDS,
    FEATURE_ROWS_FINGERPRINT,
    FOLDS,
    J_B_PREPARATION_CLOSEOUT_FINGERPRINT,
    LABEL_SOURCE_SHA256S,
    MIN_STAGE_ENTRIES,
    MIN_TOTAL_ENTRIES,
    PREPARATION_FINGERPRINT,
    PREPARED_FEATURE_SHA256,
    ROLLING_PREDICTION_FIELDS,
    SCORE_EVENT_COUNT,
    SCORE_STAGES,
    STRESSES,
    _event_equal_metric,
    _market_outcomes,
    _scenario,
    _subset,
    attach_labels,
    build_probability_gate,
    load_json,
    project_development_labels,
    read_csv,
    select_lambda,
    sha256_file,
    validate_j_b_bindings,
    validate_label_source_hashes,
    write_csv,
)
from .kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    select_entry_events,
)
from .kxbtcd_candidate_e_conditional_alpha_reliability_v2 import (
    ConditionalAlphaV2Error,
    ReliabilityFitV2,
    fit_conditional_alpha_v2,
)

CANDIDATE_ID = "kxbtcd_candidate_e_conditional_alpha_reliability.v2"
PREDECLARATION_FINGERPRINT = "6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8"
V2_IMPLEMENTATION_FINGERPRINT = "459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd"

DEVELOPMENT_EVALUATION_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_v2_development_evaluation.v1"
DEVELOPMENT_RECEIPT_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_v2_development_receipt.v1"
DEVELOPMENT_FAILURE_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_v2_development_failure.v1"
DEVELOPMENT_FAILURE_RECEIPT_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_v2_development_failure_receipt.v1"
ROLLING_PREDICTION_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_v2_rolling_prediction.v1"
ENTRY_DECISION_SCHEMA = "kxbtcd_candidate_e_conditional_alpha_v2_entry_decision.v1"

M_C_REQUIRED_COMMITTED_PATHS = {
    "configs/kxbtcd_candidate_e_conditional_alpha_reliability_v2_development_implementation_freeze.json",
    "docs/KXBTCD_CANDIDATE_E_CONDITIONAL_ALPHA_RELIABILITY_V2_DEVELOPMENT_EVALUATOR.md",
    "evaluate_kxbtcd_candidate_e_conditional_alpha_reliability_v2_development.py",
    "src/kxbtcd_candidate_e_conditional_alpha_reliability_v2_development.py",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v2_development_implementation.py",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v2_development_result.py",
}


class ConditionalAlphaV2DevelopmentError(RuntimeError):
    pass


class ConditionalAlphaV2FitContractError(ConditionalAlphaV2DevelopmentError):
    """Add deterministic fit context without changing the underlying v2 fitter."""

    def __init__(
        self,
        *,
        phase: str,
        lambda_value: float,
        fold: int | None,
        fit_stages: Sequence[str],
        score_stage: str | None,
        original_type: str,
        original_message: str,
    ) -> None:
        self.phase = str(phase)
        self.lambda_value = float(lambda_value)
        self.fold = None if fold is None else int(fold)
        self.fit_stages = tuple(str(x) for x in fit_stages)
        self.score_stage = None if score_stage is None else str(score_stage)
        self.original_type = str(original_type)
        self.original_message = str(original_message)
        fold_text = "none" if self.fold is None else str(self.fold)
        score_text = "none" if self.score_stage is None else self.score_stage
        super().__init__(
            f"phase={self.phase} lambda={self.lambda_value} fold={fold_text} "
            f"fit={'+'.join(self.fit_stages)} score={score_text}: "
            f"{self.original_type}: {self.original_message}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "lambda": self.lambda_value,
            "fold": self.fold,
            "fit_stages": list(self.fit_stages),
            "score_stage": self.score_stage,
            "original_exception_type": self.original_type,
            "original_exception_message": self.original_message,
        }


def _error(message: str) -> None:
    raise ConditionalAlphaV2DevelopmentError(message)


def validate_m_c_closeout_receipt(path: str | Path) -> dict[str, Any]:
    receipt = load_json(path)
    if receipt.get("schema") != "checkpoint_closeout_receipt.v1":
        _error("21N-M-C closeout receipt schema mismatch")
    if not str(receipt.get("checkpoint_message", "")).startswith("Checkpoint 21N-M-C"):
        _error("latest closeout receipt is not Checkpoint 21N-M-C")
    committed = {str(x) for x in receipt.get("committed_paths", ())}
    missing = sorted(M_C_REQUIRED_COMMITTED_PATHS - committed)
    if missing:
        _error("21N-M-C closeout receipt missing required evaluator paths: " + ", ".join(missing))
    safety = receipt.get("safety", {})
    for key in (
        "blocked_path_check",
        "staged_path_exact_match",
        "staged_diff_check",
        "high_confidence_secret_scan",
    ):
        if safety.get(key) != "PASS":
            _error(f"21N-M-C closeout safety.{key} must be PASS")
    if safety.get("remote_synchronized_before_commit") is not True:
        _error("21N-M-C closeout did not record synchronized baseline")
    if safety.get("worktree_clean_after_checkpoint_commit") is not True:
        _error("21N-M-C closeout did not record clean worktree")
    return receipt


def _fit_dict(fit: ReliabilityFitV2) -> dict[str, Any]:
    return {
        "lambda": fit.lambda_value,
        "iterations": fit.iterations,
        "objective": fit.objective,
        "gradient_l2_norm": fit.gradient_l2_norm,
        "total_backtracks": fit.total_backtracks,
        "minimum_accepted_step": fit.minimum_accepted_step,
        "gamma": dict(zip(PARAMETER_NAMES, fit.gamma)),
        "scaler": fit.scaler.as_dict(),
    }


def _fit_with_frozen_context(
    rows: Sequence[Mapping[str, Any]],
    *,
    lambda_value: float,
    phase: str,
    fold: int | None,
    fit_stages: Sequence[str],
    score_stage: str | None,
) -> ReliabilityFitV2:
    try:
        return fit_conditional_alpha_v2(rows, lambda_value=lambda_value)
    except ConditionalAlphaV2Error as exc:
        raise ConditionalAlphaV2FitContractError(
            phase=phase,
            lambda_value=float(lambda_value),
            fold=fold,
            fit_stages=tuple(str(x) for x in fit_stages),
            score_stage=None if score_stage is None else str(score_stage),
            original_type=type(exc).__name__,
            original_message=str(exc),
        ) from exc


def _score_stage(
    rows: Sequence[Mapping[str, Any]],
    fit: ReliabilityFitV2,
    *,
    fold: int,
    selected_lambda: float | None = None,
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for row in rows:
        alpha, p_adj = adjusted_yes_probability(row, scaler=fit.scaler, gamma=fit.gamma)
        q = float(row["market_midpoint_yes_probability"])
        p_e = float(row["candidate_probability"])
        if not (math.isfinite(q) and math.isfinite(p_e)):
            _error("q/pE must be finite")
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


def fit_and_score_fold(
    labeled_rows: Sequence[Mapping[str, Any]],
    *,
    lambda_value: float,
    fold: int,
    fit_stages: Sequence[str],
    score_stage: str,
) -> tuple[ReliabilityFitV2, tuple[dict[str, Any], ...]]:
    fit = _fit_with_frozen_context(
        _subset(labeled_rows, fit_stages),
        lambda_value=lambda_value,
        phase="rolling_origin_lambda_evaluation",
        fold=fold,
        fit_stages=fit_stages,
        score_stage=score_stage,
    )
    scored = _score_stage(_subset(labeled_rows, (score_stage,)), fit, fold=fold)
    return fit, scored


def rolling_origin_lambda_evaluation(
    labeled_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[
    list[dict[str, Any]],
    dict[float, tuple[dict[str, Any], ...]],
    dict[float, list[dict[str, Any]]],
]:
    lambda_scores: list[dict[str, Any]] = []
    predictions: dict[float, tuple[dict[str, Any], ...]] = {}
    fits: dict[float, list[dict[str, Any]]] = {}

    for lam in LAMBDA_GRID:
        pooled: list[dict[str, Any]] = []
        lam_fits: list[dict[str, Any]] = []
        for fold, fit_stages, score_stage in FOLDS:
            fit, scored = fit_and_score_fold(
                labeled_rows,
                lambda_value=lam,
                fold=fold,
                fit_stages=fit_stages,
                score_stage=score_stage,
            )
            pooled.extend(scored)
            lam_fits.append({
                "fold": fold,
                "fit_stages": list(fit_stages),
                "score_stage": score_stage,
                "fit": _fit_dict(fit),
            })

        if enforce_frozen_counts and len({r["event_ticker"] for r in pooled}) != SCORE_EVENT_COUNT:
            _error("pooled rolling-origin score event count changed")

        ll = _event_equal_metric(pooled, "adjusted_yes_probability", "log_loss")
        lambda_scores.append({
            "lambda": lam,
            "pooled_H2_H3_event_equal_log_loss": ll,
        })
        predictions[lam] = tuple(pooled)
        fits[lam] = lam_fits

    return lambda_scores, predictions, fits


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
            phase="selected_lambda_rolling_origin_refit",
            fold=fold,
            fit_stages=fit_stages,
            score_stage=score_stage,
        )
        scored = _score_stage(
            _subset(labeled_rows, (score_stage,)),
            fit,
            fold=fold,
            selected_lambda=selected_lambda,
        )
        pooled.extend(scored)
        fits.append({
            "fold": fold,
            "fit_stages": list(fit_stages),
            "score_stage": score_stage,
            "fit": _fit_dict(fit),
        })
    return tuple(pooled), fits


def build_entry_decisions(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    raw_decisions = select_entry_events([dict(row) for row in rows])
    outcomes = _market_outcomes(rows)
    if len(raw_decisions) != SCORE_EVENT_COUNT:
        _error("entry decision event count changed")

    decisions: list[dict[str, Any]] = []
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


def build_economic_gate(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    decisions = build_entry_decisions(rows)
    scenarios = {format(stress, "f"): _scenario(decisions, stress) for stress in STRESSES}
    base = scenarios["0.00"]
    adverse1 = scenarios["0.01"]
    if not base["valid"]:
        _error("base economic scenario unexpectedly invalid")

    from decimal import Decimal
    conditions = {
        "minimum_total_entries_ge_100": base["entry_count"] >= MIN_TOTAL_ENTRIES,
        "minimum_H2_entries_ge_20": base["entry_count_by_stage"]["H2"] >= MIN_STAGE_ENTRIES,
        "minimum_H3_entries_ge_20": base["entry_count_by_stage"]["H3"] >= MIN_STAGE_ENTRIES,
        "base_pooled_mean_gt_zero": Decimal(base["mean_net_pnl_per_event"]) > 0,
        "plus_1c_scenario_valid": bool(adverse1["valid"]),
        "plus_1c_pooled_mean_gt_zero":
            bool(adverse1["valid"]) and Decimal(adverse1["mean_net_pnl_per_event"]) > 0,
        "base_positive_blocks_ge_4_of_5": int(base["positive_base_block_count"]) >= 4,
        "newest_B4_base_mean_gt_zero":
            Decimal(base["block_mean_net_pnl_per_event"]["B4"]) > 0,
        "H3_base_mean_gt_zero":
            Decimal(base["stage_mean_net_pnl_per_event"]["H3"]) > 0,
    }
    return ({
        "status": "PASS" if all(conditions.values()) else "FAIL",
        "conditions": conditions,
        "scenarios": scenarios,
        "stress_interpretation":
            "quoted-price sensitivity only; not a fill/latency/depth/queue simulation",
    }, decisions)


def full_development_fit(
    labeled_rows: Sequence[Mapping[str, Any]],
    selected_lambda: float,
) -> dict[str, Any]:
    fit = _fit_with_frozen_context(
        labeled_rows,
        lambda_value=selected_lambda,
        phase="full_development_fit",
        fold=None,
        fit_stages=DEVELOPMENT_STAGES,
        score_stage=None,
    )
    return _fit_dict(fit)


def _label_fingerprint(label_rows: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256([
        {
            "stage": row["stage"],
            "state_id": row["state_id"],
            "event_ticker": row["event_ticker"],
            "market_ticker": row["market_ticker"],
            "outcome": int(row["outcome"]),
        }
        for row in sorted(label_rows, key=lambda x: str(x["state_id"]))
    ])


def build_development_evaluation(
    feature_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    labeled = attach_labels(
        feature_rows,
        label_rows,
        enforce_frozen_counts=enforce_frozen_counts,
    )
    lambda_scores, _, all_fold_fits = rolling_origin_lambda_evaluation(
        labeled,
        enforce_frozen_counts=enforce_frozen_counts,
    )
    selected = select_lambda(lambda_scores)
    selected_predictions, selected_fits = _selected_prediction_rows(labeled, selected)

    if enforce_frozen_counts and len({r["event_ticker"] for r in selected_predictions}) != SCORE_EVENT_COUNT:
        _error("selected rolling-origin score event count changed")

    probability_gate = build_probability_gate(selected_predictions)

    economic_gate: dict[str, Any]
    entry_decisions: tuple[dict[str, Any], ...]
    final_fit: dict[str, Any] | None = None

    if probability_gate["status"] != "PASS":
        economic_gate = {
            "status": "NOT_RUN_PROBABILITY_GATE_FAILED",
            "reason":
                "Evidence-minimizing sequential gate: no new conditional-alpha P&L "
                "is opened after a probability-gate failure.",
        }
        entry_decisions = tuple()
        overall = "FAIL_PROBABILITY_GATE"
    else:
        economic_gate, entry_decisions = build_economic_gate(selected_predictions)
        if economic_gate["status"] != "PASS":
            overall = "FAIL_ECONOMIC_GATE"
        else:
            final_fit = full_development_fit(labeled, selected)
            overall = "PASS"

    evaluation = {
        "schema_version": DEVELOPMENT_EVALUATION_SCHEMA,
        "candidate_id": CANDIDATE_ID,
        "predeclaration_fingerprint": PREDECLARATION_FINGERPRINT,
        "v2_implementation_fingerprint": V2_IMPLEMENTATION_FINGERPRINT,
        "preparation_fingerprint": PREPARATION_FINGERPRINT,
        "feature_rows_fingerprint": FEATURE_ROWS_FINGERPRINT,
        "development_label_fingerprint": _label_fingerprint(label_rows),
        "development_events": len({str(r["event_ticker"]) for r in labeled}),
        "development_rows": len(labeled),
        "lambda_grid": list(LAMBDA_GRID),
        "lambda_scores": lambda_scores,
        "selected_lambda": selected,
        "selected_fold_fits": selected_fits,
        "all_lambda_fold_fits": {
            repr(lam): all_fold_fits[lam] for lam in LAMBDA_GRID
        },
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


def build_optimizer_failure_evaluation(
    *,
    feature_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    failure: ConditionalAlphaV2FitContractError,
    selected_lambda: float | None = None,
    probability_gate: Mapping[str, Any] | None = None,
    economic_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    phase = failure.phase
    pre_selection = phase in {
        "rolling_origin_lambda_evaluation",
        "selected_lambda_rolling_origin_refit",
    }
    evaluation = {
        "schema_version": DEVELOPMENT_FAILURE_SCHEMA,
        "candidate_id": CANDIDATE_ID,
        "predeclaration_fingerprint": PREDECLARATION_FINGERPRINT,
        "v2_implementation_fingerprint": V2_IMPLEMENTATION_FINGERPRINT,
        "preparation_fingerprint": PREPARATION_FINGERPRINT,
        "feature_rows_fingerprint": FEATURE_ROWS_FINGERPRINT,
        "development_label_fingerprint": _label_fingerprint(label_rows),
        "development_events": len({str(r["event_ticker"]) for r in feature_rows}),
        "development_rows": len(feature_rows),
        "overall_status": "FAIL_OPTIMIZER_CONTRACT",
        "failure": failure.as_dict(),
        "selected_lambda":
            None if selected_lambda is None else float(selected_lambda),
        "lambda_selection_performed": not pre_selection and selected_lambda is not None,
        "probability_gate":
            {"status": "NOT_RUN_OPTIMIZER_CONTRACT_FAILED"}
            if probability_gate is None else dict(probability_gate),
        "economic_gate":
            {"status": "NOT_RUN_OPTIMIZER_CONTRACT_FAILED"}
            if economic_gate is None else dict(economic_gate),
        "full_development_fit": None,
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
    receipt = {
        "schema_version": DEVELOPMENT_RECEIPT_SCHEMA,
        "candidate_id": CANDIDATE_ID,
        "evaluation_fingerprint": evaluation["evaluation_fingerprint"],
        "overall_status": evaluation["overall_status"],
        "input_sha256s": dict(input_hashes),
        "output_sha256s": {
            "evaluation_sha256": sha256_file(evaluation_path),
            "rolling_predictions_sha256": sha256_file(prediction_path),
            "entry_decisions_sha256":
                None if entry_path is None else sha256_file(entry_path),
        },
        "safety": dict(evaluation["safety"]),
    }
    receipt["receipt_fingerprint"] = canonical_sha256(receipt)
    return receipt


__all__ = [
    "CANDIDATE_ID",
    "ConditionalAlphaV2DevelopmentError",
    "ConditionalAlphaV2FitContractError",
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
    "fit_and_score_fold",
    "load_json",
    "project_development_labels",
    "read_csv",
    "rolling_origin_lambda_evaluation",
    "sha256_file",
    "validate_j_b_bindings",
    "validate_label_source_hashes",
    "validate_m_c_closeout_receipt",
    "write_csv",
]
