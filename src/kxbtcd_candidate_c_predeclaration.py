"""Checkpoint-14 predeclaration for a future KXBTCD Candidate C.

This module freezes research design only. It does not fit Candidate C, open
locked-test outcomes, perform network access, or enable execution.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable


class KxbtcdCandidateCPredeclarationError(ValueError):
    """Raised when the frozen Candidate-C research contract is violated."""


CONTRACT_VERSION = "kxbtcd_candidate_c_predeclaration.v2"
CANDIDATE_ID = "kxbtcd_market_spread_interaction_logistic.v1"
DEVELOPMENT_BLOCK_COUNT = 5
L2_PENALTY_GRID = ("0.01", "0.1", "1", "10")
CALIBRATION_BIN_WIDTH = "0.10"
CANONICAL_CP13_RUN_ID = "collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631"
FROZEN_PREOUTCOME_RUN_ID = "collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d"
FROZEN_DATASET_FINGERPRINT = "d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a"
FROZEN_SPLIT_FINGERPRINT = "28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503"


def candidate_c_predeclaration() -> dict[str, Any]:
    """Return the exact proposed future-candidate contract.

    Candidate C is intentionally a small extension of Candidate B. The hypothesis
    is that the useful recalibration depends on contemporaneous quoted spread and
    that the spread effect is asymmetric across the market's own probability. It
    does not add a learned time-to-close term because Checkpoint-14 TTC slices were
    directionally positive at every frozen anchor. It does not add external BTC
    feeds, trend indicators, volatility indicators, sub-second lead/lag terms, or
    execution variables.
    """

    return {
        "contract_version": CONTRACT_VERSION,
        "candidate_id": CANDIDATE_ID,
        "status_in_checkpoint_14": "predeclared_not_fit_not_authorized",
        "task": "KXBTCD_binary_settlement_probability",
        "benchmark": {
            "name": "raw_market_midpoint",
            "formula": "q_market=(yes_bid+yes_ask)/2",
        },
        "development_data": {
            "canonical_cp13_run_id": CANONICAL_CP13_RUN_ID,
            "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
            "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
            "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
            "allowed_event_scope": "Checkpoint-13 outcome-exposed train_plus_validation_events_only",
            "original_train_event_count": 175,
            "original_validation_event_count": 56,
            "development_event_count": 231,
            "locked_test_event_count": 64,
            "locked_test_outcomes_allowed": False,
            "locked_test_feature_density_for_design_allowed": False,
        },
        "features": [
            {
                "name": "market_logit",
                "formula": "ln(clip(q_market,0.001,0.999)/(1-clip(q_market,0.001,0.999)))",
                "source": "pre-outcome KXBTCD midpoint",
            },
            {
                "name": "spread",
                "formula": "yes_ask-yes_bid",
                "source": "pre-outcome KXBTCD quote context",
            },
            {
                "name": "market_logit_x_spread",
                "formula": "market_logit*spread",
                "source": "interaction of two pre-outcome KXBTCD variables",
            },
        ],
        "excluded_feature_families": [
            "absolute_strike_term",
            "learned_time_to_close_term",
            "structural_role_one_hot",
            "external_BTC_state",
            "trend_or_momentum_indicators",
            "realized_or_implied_volatility_indicators",
            "subsecond_lead_lag",
            "future_or_settlement_fields",
            "execution_or_PnL_fields",
        ],
        "feature_scaling": {
            "rule": "z_score_each_non_intercept_feature_using_fit_fold_only",
            "variance": "population_variance",
            "zero_variance": "fail_closed",
            "validation_or_future_block_statistics_used": False,
        },
        "model": {
            "form": "logistic_regression_with_intercept",
            "training_objective": (
                "mean_over_fit_events(mean_binary_log_loss_within_event) + "
                "lambda/2 * sum(all_three_non_intercept_standardized_feature_coefficients_squared)"
            ),
            "regularization": "L2_on_all_non_intercept_coefficients",
            "penalize_intercept": False,
            "lambda_grid": list(L2_PENALTY_GRID),
            "class_weights": "none",
            "event_weighting": "each_event_total_weight_equals_one_within_each_fit_or_scored_partition",
            "optimizer": {
                "algorithm": "deterministic_damped_Newton",
                "max_iterations": 100,
                "gradient_l2_tolerance": "1e-8",
                "armijo_constant": "1e-4",
                "minimum_step_scale": "2^-40",
                "non_convergence": "fail_closed",
                "singular_hessian": "fail_closed",
            },
        },
        "development_selection_protocol": {
            "chronology_unit": "utc_week_start",
            "block_rule": (
                "sort unique development UTC weeks ascending and divide them into five contiguous "
                "blocks with week counts differing by at most one; earlier blocks receive any remainder"
            ),
            "block_count": DEVELOPMENT_BLOCK_COUNT,
            "rolling_origin_folds": [
                {"fit_blocks": [0], "score_block": 1},
                {"fit_blocks": [0, 1], "score_block": 2},
                {"fit_blocks": [0, 1, 2], "score_block": 3},
                {"fit_blocks": [0, 1, 2, 3], "score_block": 4},
            ],
            "lambda_selection": (
                "lowest pooled out_of_fold event_weighted_log_loss across score blocks 1-4; "
                "exact tie chooses the larger lambda"
            ),
            "no_random_shuffle": True,
            "pre_fit_freeze_requirement": (
                "derive the exact week-to-block mapping from the frozen 231-event development set "
                "without outcomes, serialize it, and freeze its SHA-256 fingerprint before any Candidate-C fit"
            ),
        },
        "reported_metrics": {
            "primary": "pooled_out_of_fold_event_weighted_log_loss",
            "secondary": [
                "pooled_out_of_fold_event_weighted_Brier",
                "per_fold_event_weighted_log_loss",
                "per_fold_event_weighted_Brier",
                "fixed_0.10_probability_calibration_bins",
                "candidate_minus_raw_event_loss_sign_counts",
            ],
        },
        "development_advancement_gate": {
            "all_required": True,
            "conditions": [
                "selected_candidate_pooled_OOF_log_loss_strictly_less_than_raw_midpoint_OOF_log_loss",
                "selected_candidate_pooled_OOF_Brier_less_than_or_equal_to_raw_midpoint_OOF_Brier",
                "selected_candidate_log_loss_strictly_better_than_raw_midpoint_in_at_least_3_of_4_rolling_score_blocks",
            ],
            "tie_on_primary": "fail",
            "secondary_metrics_cannot_override_primary_failure": True,
        },
        "after_development_gate": {
            "if_fail": "reject_Candidate_C_and_keep_locked_test_outcomes_sealed",
            "if_pass": (
                "freeze_selected_lambda_and_full-development feature-scaling parameters; then a later "
                "explicit checkpoint may authorize one final fit on all 231 development events"
            ),
            "locked_test_access_in_checkpoint_14": False,
        },
        "future_locked_test_rule": {
            "role": "one_time_terminal_evaluation_only_after_candidate_and_final_fit_are_frozen",
            "primary_acceptance": (
                "Candidate_C_locked_test_event_weighted_log_loss_strictly_less_than_raw_midpoint_locked_test_event_weighted_log_loss"
            ),
            "tie": "fail",
            "post_open_redesign_on_same_locked_test": False,
            "if_locked_test_is_opened": (
                "the 64-event block becomes exposed and cannot serve as an untouched test for later candidates"
            ),
        },
        "checkpoint_14_permissions": {
            "candidate_c_fit": False,
            "locked_test_outcome_access": False,
            "network_access_for_diagnostics": False,
            "paper_execution": False,
            "demo_execution": False,
            "real_money_execution": False,
            "order_actions": False,
        },
    }


def candidate_c_predeclaration_fingerprint() -> str:
    payload = json.dumps(
        candidate_c_predeclaration(), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_candidate_c_predeclaration() -> None:
    spec = candidate_c_predeclaration()
    if spec["contract_version"] != CONTRACT_VERSION:
        raise KxbtcdCandidateCPredeclarationError("contract version mismatch")
    if spec["candidate_id"] != CANDIDATE_ID:
        raise KxbtcdCandidateCPredeclarationError("candidate ID mismatch")
    development = spec["development_data"]
    if development["canonical_cp13_run_id"] != CANONICAL_CP13_RUN_ID:
        raise KxbtcdCandidateCPredeclarationError("canonical CP13 run changed")
    if development["frozen_preoutcome_run_id"] != FROZEN_PREOUTCOME_RUN_ID:
        raise KxbtcdCandidateCPredeclarationError("frozen pre-outcome run changed")
    if development["dataset_fingerprint"] != FROZEN_DATASET_FINGERPRINT:
        raise KxbtcdCandidateCPredeclarationError("frozen dataset fingerprint changed")
    if development["split_fingerprint"] != FROZEN_SPLIT_FINGERPRINT:
        raise KxbtcdCandidateCPredeclarationError("frozen split fingerprint changed")
    if development["development_event_count"] != 231:
        raise KxbtcdCandidateCPredeclarationError("development event count changed")
    if development["locked_test_outcomes_allowed"] is not False:
        raise KxbtcdCandidateCPredeclarationError("locked-test outcomes must remain sealed")
    if development["locked_test_feature_density_for_design_allowed"] is not False:
        raise KxbtcdCandidateCPredeclarationError(
            "locked-test feature density must not drive Candidate-C design"
        )
    model = spec["model"]
    if tuple(model["lambda_grid"]) != L2_PENALTY_GRID:
        raise KxbtcdCandidateCPredeclarationError("lambda grid changed")
    optimizer = model["optimizer"]
    if optimizer != {
        "algorithm": "deterministic_damped_Newton",
        "max_iterations": 100,
        "gradient_l2_tolerance": "1e-8",
        "armijo_constant": "1e-4",
        "minimum_step_scale": "2^-40",
        "non_convergence": "fail_closed",
        "singular_hessian": "fail_closed",
    }:
        raise KxbtcdCandidateCPredeclarationError("optimizer contract changed")
    if spec["development_selection_protocol"]["block_count"] != DEVELOPMENT_BLOCK_COUNT:
        raise KxbtcdCandidateCPredeclarationError("development block count changed")
    folds = spec["development_selection_protocol"]["rolling_origin_folds"]
    expected = [
        {"fit_blocks": [0], "score_block": 1},
        {"fit_blocks": [0, 1], "score_block": 2},
        {"fit_blocks": [0, 1, 2], "score_block": 3},
        {"fit_blocks": [0, 1, 2, 3], "score_block": 4},
    ]
    if folds != expected:
        raise KxbtcdCandidateCPredeclarationError("rolling-origin folds changed")
    feature_names = tuple(item["name"] for item in spec["features"])
    if feature_names != (
        "market_logit",
        "spread",
        "market_logit_x_spread",
    ):
        raise KxbtcdCandidateCPredeclarationError("Candidate-C feature set changed")
    permissions = spec["checkpoint_14_permissions"]
    if any(permissions.values()):
        raise KxbtcdCandidateCPredeclarationError(
            "Checkpoint 14 must not authorize fit, test access, network diagnostics, or execution"
        )


def assign_contiguous_week_blocks(
    weeks: Iterable[str], *, block_count: int = DEVELOPMENT_BLOCK_COUNT
) -> dict[str, int]:
    """Assign sorted unique UTC-week identifiers to balanced contiguous blocks."""

    unique = sorted(set(weeks))
    if block_count <= 1:
        raise KxbtcdCandidateCPredeclarationError("block_count must exceed one")
    if len(unique) < block_count:
        raise KxbtcdCandidateCPredeclarationError(
            f"need at least {block_count} unique weeks; found {len(unique)}"
        )
    base, remainder = divmod(len(unique), block_count)
    mapping: dict[str, int] = {}
    cursor = 0
    for block in range(block_count):
        size = base + (1 if block < remainder else 0)
        for week in unique[cursor : cursor + size]:
            mapping[week] = block
        cursor += size
    if cursor != len(unique):
        raise KxbtcdCandidateCPredeclarationError("week-block assignment did not consume all weeks")
    return mapping


validate_candidate_c_predeclaration()
