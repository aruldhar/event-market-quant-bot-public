from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src.kxbtcd_candidate_c_development import CandidateCObservation
from src.kxbtcd_candidate_c_final_fit import (
    KxbtcdCandidateCFinalFitError,
    _create_attempt_receipt,
    build_full_development_freeze_document,
    fit_final_candidate_c_model,
    predict_with_final_model,
    validate_full_development_freeze_document,
    validate_final_model_document,
)


def _obs(state: str, event: str, block: int, outcome: int, q: float, spread: float) -> CandidateCObservation:
    logit = math.log(q / (1.0 - q))
    return CandidateCObservation(
        state_id=state,
        event_ticker=event,
        market_ticker=f"M-{state}",
        utc_week_start=f"W{block}",
        block=block,
        outcome=outcome,
        q_market=q,
        market_logit=logit,
        spread=spread,
        market_logit_x_spread=logit * spread,
    )


def _rows() -> tuple[CandidateCObservation, ...]:
    return (
        _obs("a", "E1", 0, 0, 0.20, 0.01),
        _obs("b", "E2", 1, 0, 0.35, 0.04),
        _obs("c", "E3", 2, 1, 0.65, 0.02),
        _obs("d", "E4", 3, 1, 0.80, 0.05),
        _obs("e", "E5", 4, 1, 0.55, 0.03),
        _obs("f", "E6", 4, 0, 0.45, 0.06),
    )


def test_freeze_document_is_deterministic_and_valid() -> None:
    rows = _rows()
    first = build_full_development_freeze_document(rows, enforce_canonical_counts=False)
    second = build_full_development_freeze_document(rows, enforce_canonical_counts=False)
    assert first == second
    scaler = validate_full_development_freeze_document(
        first, rows=rows, enforce_canonical_counts=False
    )
    assert len(scaler.means) == 3
    assert all(value > 0 for value in scaler.population_stds)
    assert first["rules"]["selected_lambda"] == "0.01"


def test_freeze_rejects_post_freeze_lambda_change() -> None:
    document = build_full_development_freeze_document(_rows(), enforce_canonical_counts=False)
    document["rules"]["selected_lambda"] = "0.001"
    with pytest.raises(KxbtcdCandidateCFinalFitError):
        validate_full_development_freeze_document(document, enforce_canonical_counts=False)


def test_final_fit_reuses_frozen_scaler_and_selected_lambda() -> None:
    rows = _rows()
    freeze = build_full_development_freeze_document(rows, enforce_canonical_counts=False)
    result = fit_final_candidate_c_model(rows, freeze, enforce_canonical_counts=False)
    validate_final_model_document(result.document, enforce_canonical_counts=False)
    assert result.document["selected_lambda"] == "0.01"
    assert result.document["scaler"] == freeze["scaler"]
    assert result.document["fit"]["converged"] is True
    assert len(result.document["coefficients"]) == 4


def test_final_model_fingerprint_detects_coefficient_mutation() -> None:
    rows = _rows()
    freeze = build_full_development_freeze_document(rows, enforce_canonical_counts=False)
    result = fit_final_candidate_c_model(rows, freeze, enforce_canonical_counts=False)
    mutated = json.loads(json.dumps(result.document))
    mutated["coefficients"][0] = "999"
    with pytest.raises(KxbtcdCandidateCFinalFitError):
        validate_final_model_document(mutated, enforce_canonical_counts=False)


def test_frozen_artifact_supports_pure_inference() -> None:
    rows = _rows()
    freeze = build_full_development_freeze_document(rows, enforce_canonical_counts=False)
    result = fit_final_candidate_c_model(rows, freeze, enforce_canonical_counts=False)
    p1 = predict_with_final_model(0.60, 0.02, result.document, enforce_canonical_counts=False)
    p2 = predict_with_final_model(0.60, 0.02, result.document, enforce_canonical_counts=False)
    assert 0.0 < p1 < 1.0
    assert p1 == p2


def test_attempt_receipt_is_write_once(tmp_path: Path) -> None:
    path = tmp_path / "attempt.json"
    first = _create_attempt_receipt(path, freeze_fingerprint="abc")
    assert first["status"] == "fit_started"
    with pytest.raises(KxbtcdCandidateCFinalFitError):
        _create_attempt_receipt(path, freeze_fingerprint="abc")
