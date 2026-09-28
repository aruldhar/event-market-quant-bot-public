from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_entry_model_v1_validation_closeout import (
    CloseoutError,
    EXPECTED_METRICS,
    MODEL_ID,
    ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT,
    VALIDATION_EVALUATION_FINGERPRINT,
    VALIDATION_PREPARATION_FINGERPRINT,
    DEVELOPMENT_FREEZE_FINGERPRINT,
    validate_attempt,
    validate_summary,
)


def _summary() -> dict:
    result = {
        "model_id": MODEL_ID,
        "development_freeze_fingerprint": DEVELOPMENT_FREEZE_FINGERPRINT,
        "validation_preparation_fingerprint": VALIDATION_PREPARATION_FINGERPRINT,
        "validation_implementation_fingerprint":
            ORIGINAL_VALIDATION_IMPLEMENTATION_FINGERPRINT,
        "validation_evaluation_fingerprint": VALIDATION_EVALUATION_FINGERPRINT,
        "selected_lambda": 0.01,
        "gate_conditions": {
            "pooled_model2_log_loss_strictly_better": False,
            "pooled_model2_brier_not_worse": False,
            "at_least_four_of_five_block_log_loss_wins": False,
            "newest_block_log_loss_win": False,
            "median_event_candidate_e_minus_model2_log_loss_positive": True,
        },
        "profitability_claim": False,
        "strategy_v1_pnl_calculated": False,
        "c3_opened_for_model2": False,
        "protected_reserve_accessed": False,
        "execution_enabled": False,
    }
    result.update(EXPECTED_METRICS)
    return result


def test_frozen_fail_summary_is_accepted():
    validate_summary(_summary())


def test_validation_pass_cannot_be_rewritten():
    value = _summary()
    value["validation_passed"] = True
    with pytest.raises(CloseoutError):
        validate_summary(value)


def test_primary_metric_cannot_change():
    value = _summary()
    value["model2_event_equal_log_loss"] += 1e-9
    with pytest.raises(CloseoutError):
        validate_summary(value)


def test_gate_pattern_cannot_change():
    value = _summary()
    value["gate_conditions"]["newest_block_log_loss_win"] = True
    with pytest.raises(CloseoutError):
        validate_summary(value)


def test_c3_cannot_be_marked_open():
    value = _summary()
    value["c3_opened_for_model2"] = True
    with pytest.raises(CloseoutError):
        validate_summary(value)
