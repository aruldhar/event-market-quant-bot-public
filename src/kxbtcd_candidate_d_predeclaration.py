"""Checkpoint-18B frozen predeclaration for KXBTCD Candidate D.

This module contains no fitting, scoring, network, or execution path.  Its
purpose is to freeze the exact successor hypothesis and development-screen
protocol before Candidate D is implemented or fit.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

CONTRACT_VERSION = "kxbtcd_candidate_d_predeclaration.v1"
CANDIDATE_ID = "kxbtcd_market_logit_recalibration.v1"
FROZEN_PREDECLARATION_FINGERPRINT = "a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537"

_PREDECLARATION: dict[str, Any] = {'contract_version': 'kxbtcd_candidate_d_predeclaration.v1', 'candidate_id': 'kxbtcd_market_logit_recalibration.v1', 'date_frozen': '2026-08-15', 'evidence_boundary': {'development_event_count': 231, 'development_row_count': 5364, 'development_week_count': 58, 'cp18a_analysis_run': '20260815T231543Z', 'cp18a_review_scope': 'development_only', 'checkpoint17_terminal_result_may_be_used_only_as_historical_fact_of_failure': True, 'checkpoint17_terminal_rows_labels_features_predictions_residuals_slices_prohibited': True}, 'model': {'formula': 'logit(p_D) = market_logit + alpha + delta * market_logit', 'equivalent_formula': 'logit(p_D) = alpha + (1 + delta) * market_logit', 'input_feature': 'q_market_only', 'market_logit_transform': {'q_market_required_range': '[0,1]', 'clip_lower': '0.001', 'clip_upper': '0.999', 'transform': 'ln(q_clipped / (1 - q_clipped))'}, 'parameters': ['alpha', 'delta'], 'raw_midpoint_nested_at': {'alpha': '0', 'delta': '0'}, 'market_logit_slope': '1 + delta', 'feature_scaling': 'none', 'spread_feature': 'prohibited', 'market_logit_x_spread_interaction': 'prohibited', 'other_features': 'prohibited', 'regularization': 'none', 'hyperparameter_grid': [], 'hyperparameter_search': False, 'fit_initialization': {'alpha': '0', 'delta': '0'}, 'optimizer': {'algorithm': 'deterministic_damped_Newton', 'max_iterations': 100, 'gradient_l2_tolerance': '1e-8', 'armijo_constant': '1e-4', 'minimum_step_scale': '2^-40', 'non_convergence': 'fail_closed', 'singular_hessian': 'fail_closed'}}, 'fit_objective': {'loss': 'binary_log_loss', 'event_weighting': 'each event has equal total weight', 'within_event_weighting': 'rows within each event share that event weight equally', 'penalty': 'none'}, 'development_protocol': {'chronology_unit': 'utc_week_start', 'layout_id': '7_contiguous_utc_week_blocks', 'layout_construction_used_outcomes': False, 'block_rule': 'sort the 58 unique development UTC weeks ascending and divide into seven contiguous blocks with week counts differing by at most one; earlier blocks receive the remainder', 'blocks': [{'block': 'B0', 'week_count': 9, 'event_count': 35, 'first_week': '2025-03-17T00:00:00Z', 'last_week': '2025-05-12T00:00:00Z'}, {'block': 'B1', 'week_count': 9, 'event_count': 36, 'first_week': '2025-05-19T00:00:00Z', 'last_week': '2025-07-14T00:00:00Z'}, {'block': 'B2', 'week_count': 8, 'event_count': 32, 'first_week': '2025-07-21T00:00:00Z', 'last_week': '2025-09-08T00:00:00Z'}, {'block': 'B3', 'week_count': 8, 'event_count': 32, 'first_week': '2025-09-15T00:00:00Z', 'last_week': '2025-11-03T00:00:00Z'}, {'block': 'B4', 'week_count': 8, 'event_count': 32, 'first_week': '2025-11-10T00:00:00Z', 'last_week': '2025-12-29T00:00:00Z'}, {'block': 'B5', 'week_count': 8, 'event_count': 32, 'first_week': '2026-01-05T00:00:00Z', 'last_week': '2026-02-23T00:00:00Z'}, {'block': 'B6', 'week_count': 8, 'event_count': 32, 'first_week': '2026-03-02T00:00:00Z', 'last_week': '2026-04-20T00:00:00Z'}], 'rolling_origin_folds': [{'fold': 1, 'fit_blocks': ['B0', 'B1'], 'score_block': 'B2'}, {'fold': 2, 'fit_blocks': ['B0', 'B1', 'B2'], 'score_block': 'B3'}, {'fold': 3, 'fit_blocks': ['B0', 'B1', 'B2', 'B3'], 'score_block': 'B4'}, {'fold': 4, 'fit_blocks': ['B0', 'B1', 'B2', 'B3', 'B4'], 'score_block': 'B5'}, {'fold': 5, 'fit_blocks': ['B0', 'B1', 'B2', 'B3', 'B4', 'B5'], 'score_block': 'B6'}], 'scored_event_count': 160, 'score_block_event_counts': {'B2': 32, 'B3': 32, 'B4': 32, 'B5': 32, 'B6': 32}, 'interpretation': 'development stability screen only; these exposed development events are not an untouched test and cannot establish prospective generalization'}, 'metrics': {'primary': 'pooled_oof_event_weighted_log_loss', 'secondary': 'pooled_oof_event_weighted_brier', 'block_metrics': ['event_weighted_log_loss', 'event_weighted_brier'], 'event_diagnostic': 'raw_minus_candidate_d_event_log_loss_delta', 'event_summary_gate': 'median_event_delta', 'raw_benchmark_probability': 'original q_market midpoint', 'tie_policy_primary': 'fail'}, 'development_advancement_gate': {'all_conditions_required': True, 'conditions': ['pooled raw-minus-D event-weighted log-loss delta > 0', 'pooled raw-minus-D event-weighted Brier delta >= 0', 'D log loss strictly beats raw in at least 4 of 5 score blocks', 'D log loss strictly beats raw in latest score block B6', 'median event-level raw-minus-D log-loss delta > 0', 'all five fits converge and all scored probabilities/metrics are finite', 'all five fitted market-logit slopes (1 + delta) are > 0'], 'development_pass_meaning': 'permission to freeze a final development fit and proceed toward a genuinely new prospective untouched-test design; not validation, profitability evidence, or execution authorization'}, 'instability_and_failure_rules': {'nonpositive_market_logit_slope': 'automatic_fail', 'optimizer_non_convergence': 'automatic_fail', 'singular_hessian': 'automatic_fail', 'nonfinite_parameter_prediction_or_metric': 'automatic_fail', 'missing_or_changed_lineage_or_block_membership': 'automatic_fail', 'terminal_data_access': 'automatic_fail', 'coefficient_drift': 'report_only_no_post_hoc_threshold'}, 'future_untouched_test_boundary': {'checkpoint17_terminal_block_reuse': 'prohibited', 'new_test_membership_must_be_predeclared_before_outcomes_are_opened': True, 'new_test_events_must_be_genuinely_future_relative_to_candidate_d_design_freeze': True, 'preferred_stricter_boundary': 'terminal-eligible event start times should be after the Candidate-D final-model freeze timestamp', 'terminal_sample_size': 'unresolved_until_separately_predeclared_before_collection/scoring'}, 'safety': {'read_only': True, 'network_required_for_development_evaluation': False, 'candidate_d_fit_authorized_by_this_predeclaration': False, 'paper_execution': False, 'demo_execution': False, 'real_money_execution': False, 'orders': False, 'transfers': False}}


def candidate_d_predeclaration() -> dict[str, Any]:
    """Return a defensive JSON round-trip copy of the frozen contract."""
    return json.loads(json.dumps(_PREDECLARATION))


def candidate_d_predeclaration_fingerprint() -> str:
    payload = candidate_d_predeclaration()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_candidate_d_predeclaration() -> str:
    payload = candidate_d_predeclaration()
    if payload["contract_version"] != CONTRACT_VERSION:
        raise RuntimeError("Candidate-D contract version changed")
    if payload["candidate_id"] != CANDIDATE_ID:
        raise RuntimeError("Candidate-D candidate ID changed")
    observed = candidate_d_predeclaration_fingerprint()
    if observed != FROZEN_PREDECLARATION_FINGERPRINT:
        raise RuntimeError(
            "Candidate-D predeclaration fingerprint changed: "
            f"{observed} != {FROZEN_PREDECLARATION_FINGERPRINT}"
        )
    if payload["model"]["hyperparameter_search"] is not False:
        raise RuntimeError("Candidate-D hyperparameter search must remain disabled")
    if payload["model"]["spread_feature"] != "prohibited":
        raise RuntimeError("Candidate-D spread feature must remain prohibited")
    if payload["model"]["market_logit_x_spread_interaction"] != "prohibited":
        raise RuntimeError("Candidate-D interaction must remain prohibited")
    if payload["safety"]["candidate_d_fit_authorized_by_this_predeclaration"] is not False:
        raise RuntimeError("Checkpoint-18B predeclaration must not itself authorize fitting")
    if payload["safety"]["orders"] is not False:
        raise RuntimeError("Candidate-D predeclaration must not authorize orders")
    return observed
