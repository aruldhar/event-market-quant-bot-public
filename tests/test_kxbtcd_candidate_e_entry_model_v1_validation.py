from __future__ import annotations

import math
from pathlib import Path

import pytest

import src.kxbtcd_candidate_e_entry_model_v1_validation as module
from src.kxbtcd_candidate_e_entry_model_v1 import (
    CONTINUOUS_FEATURES,
    EventEqualScaler,
)
from src.kxbtcd_candidate_e_entry_model_v1_validation import (
    ValidationEvaluationError,
    build_block_scores,
    build_validation_summary,
    project_outcomes,
    score_validation_rows,
)

def _event_score(
    *,
    event: str,
    block: str,
    candidate_loss: float,
    model2_loss: float,
    candidate_brier: float,
    model2_brier: float,
):
    return {
        "schema_version": module.EVENT_SCORE_SCHEMA,
        "model_id": module.MODEL_ID,
        "validation_block": block,
        "stage": "C1",
        "event_ticker": event,
        "row_count": 1,
        "candidate_log_loss": candidate_loss,
        "model2_log_loss": model2_loss,
        "candidate_minus_model2_log_loss": candidate_loss - model2_loss,
        "candidate_brier": candidate_brier,
        "model2_brier": model2_brier,
        "candidate_minus_model2_brier": candidate_brier - model2_brier,
    }

def _synthetic_event_scores(
    *,
    losing_blocks=(),
    newest_loses=False,
    brier_worse=False,
    event_delta=0.01,
):
    rows = []
    for block_index, block in enumerate(module.VALIDATION_BLOCKS):
        block_loses = block in set(losing_blocks) or (
            newest_loses and block == module.VALIDATION_BLOCKS[-1]
        )
        for i in range(module.EVENTS_PER_BLOCK):
            candidate_loss = 0.2
            model2_loss = (
                candidate_loss + abs(event_delta)
                if block_loses
                else candidate_loss - abs(event_delta)
            )
            candidate_brier = 0.04
            model2_brier = 0.041 if brier_worse else 0.039
            rows.append(
                _event_score(
                    event=f"{block}-E{i:03d}",
                    block=block,
                    candidate_loss=candidate_loss,
                    model2_loss=model2_loss,
                    candidate_brier=candidate_brier,
                    model2_brier=model2_brier,
                )
            )
    return rows

def test_all_five_gate_conditions_required_and_pass_when_all_true():
    rows = _synthetic_event_scores()
    blocks = build_block_scores(rows)
    summary = build_validation_summary(
        rows,
        blocks,
        implementation_fingerprint="x" * 64,
    )
    assert summary["validation_passed"] is True
    assert summary["block_log_loss_win_count"] == 5
    assert all(summary["gate_conditions"].values())

def test_three_of_five_block_wins_fails():
    rows = _synthetic_event_scores(losing_blocks=("V0", "V1"))
    blocks = build_block_scores(rows)
    summary = build_validation_summary(
        rows,
        blocks,
        implementation_fingerprint="x" * 64,
    )
    assert summary["block_log_loss_win_count"] == 3
    assert summary["validation_passed"] is False

def test_newest_block_loss_fails_even_with_four_other_wins():
    rows = _synthetic_event_scores(newest_loses=True)
    blocks = build_block_scores(rows)
    summary = build_validation_summary(
        rows,
        blocks,
        implementation_fingerprint="x" * 64,
    )
    assert summary["block_log_loss_win_count"] == 4
    assert summary["newest_block_log_loss_win"] is False
    assert summary["validation_passed"] is False

def test_brier_worse_fails():
    rows = _synthetic_event_scores(brier_worse=True)
    blocks = build_block_scores(rows)
    summary = build_validation_summary(
        rows,
        blocks,
        implementation_fingerprint="x" * 64,
    )
    assert summary["gate_conditions"]["pooled_model2_brier_not_worse"] is False
    assert summary["validation_passed"] is False

def test_primary_log_loss_tie_fails_but_brier_tie_is_allowed():
    rows = []
    for block in module.VALIDATION_BLOCKS:
        for i in range(module.EVENTS_PER_BLOCK):
            rows.append(
                _event_score(
                    event=f"{block}-E{i:03d}",
                    block=block,
                    candidate_loss=0.2,
                    model2_loss=0.2,
                    candidate_brier=0.04,
                    model2_brier=0.04,
                )
            )
    blocks = build_block_scores(rows)
    summary = build_validation_summary(
        rows,
        blocks,
        implementation_fingerprint="x" * 64,
    )
    assert summary["gate_conditions"]["pooled_model2_log_loss_strictly_better"] is False
    assert summary["gate_conditions"]["pooled_model2_brier_not_worse"] is True
    assert summary["validation_passed"] is False

def test_project_outcomes_rejects_duplicate_market(monkeypatch):
    monkeypatch.setitem(module.EXPECTED_STAGE_MARKETS, "C1", 2)
    rows = [
        {"stage": "C1", "event_ticker": "E1", "market_ticker": "M", "outcome": "1"},
        {"stage": "C1", "event_ticker": "E1", "market_ticker": "M", "outcome": "1"},
    ]
    with pytest.raises(ValidationEvaluationError):
        project_outcomes(rows, expected_stage="C1")

def test_finite_offset_handles_historical_probability_endpoint(monkeypatch):
    # Minimal one-row scoring fixture for the exact numerical representation rule.
    feature = {
        "schema_version": "kxbtcd_candidate_e_entry_model_v1_feature_row.v1",
        "model_id": module.MODEL_ID,
        "stage": "C2",
        "state_id": "S",
        "event_ticker": "E",
        "event_close_time_utc": "2025-11-28T17:00:00Z",
        "market_ticker": "M",
        "structural_role": "q50",
        "ttc_target_minutes": 55,
        "decision_time_utc": "2025-11-28T16:05:00Z",
        "candidate_probability": 1.0,
        **{name: 0.0 for name in CONTINUOUS_FEATURES},
    }
    offset = {
        "schema_version": "kxbtcd_candidate_e_entry_model_v1_validation_offset.v1",
        "model_id": module.MODEL_ID,
        "stage": "C2",
        "state_id": "S",
        "candidate_logit_offset": 37.87469998298248,
    }
    event_map = {
        "schema_version": "kxbtcd_candidate_e_entry_model_v1_validation_event.v1",
        "model_id": module.MODEL_ID,
        "validation_block": "V4",
        "validation_event_index_zero_based": 999,
        "stage": "C2",
        "stage_event_index_zero_based": 499,
        "event_ticker": "E",
        "event_close_time_utc": "2025-11-28T17:00:00Z",
        "row_count": 1,
    }

    # Only score_validation_rows count check is relaxed for this unit fixture.
    monkeypatch.setattr(module, "EXPECTED_VALIDATION_ROWS", 1)
    monkeypatch.setattr(
        module,
        "_block_map",
        lambda _rows: {"E": ("C2", "V4")},
    )
    scaler = EventEqualScaler(
        tuple(0.0 for _ in CONTINUOUS_FEATURES),
        tuple(1.0 for _ in CONTINUOUS_FEATURES),
    )
    scored = score_validation_rows(
        [{**feature, "outcome": 1}],
        offset_rows=[offset],
        event_map_rows=[event_map],
        coefficients=[0.0] * 21,
        scaler=scaler,
    )
    assert scored[0]["candidate_probability"] == 1.0
    assert math.isfinite(scored[0]["candidate_log_loss"])
    assert scored[0]["candidate_logit_offset"] == pytest.approx(37.87469998298248)

def test_evaluator_has_no_fit_or_retune_call_surface():
    source = Path(
        "src/kxbtcd_candidate_e_entry_model_v1_validation.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        "fit_residual_logistic(",
        "fit_event_equal_scaler(",
        "evaluate_development_rolling_origin(",
        "select_lambda(",
    )
    for needle in forbidden:
        assert needle not in source

def test_evaluator_cli_has_no_c3_reserve_pnl_execution_input():
    source = Path(
        "evaluate_kxbtcd_candidate_e_entry_model_v1_validation.py"
    ).read_text(encoding="utf-8").lower()
    assert "--c3" not in source
    assert "--reserve" not in source
    assert "--pnl" not in source
    assert "--quantity" not in source
    assert "--order" not in source

def test_freeze_script_has_no_outcome_input_surface():
    source = Path(
        "freeze_kxbtcd_candidate_e_entry_model_v1_validation_implementation.py"
    ).read_text(encoding="utf-8").lower()
    assert "--c1-outcomes" not in source
    assert "--c2-outcomes" not in source
    assert "read_csv(" not in source
