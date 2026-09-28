from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import src.kxbtcd_candidate_e_h3_preparation as mod


def test_checkpoint20g_parent_and_fit_scope_are_frozen():
    assert mod.EXPECTED_BASELINE_COMMIT == (
        "6341d86c965f1f7df799163b71ff1dcb8b772d4a"
    )
    assert mod.FINAL_FIT_EVENT_COUNT == 2250
    assert mod.FINAL_FIT_ROW_COUNT == 58668
    assert mod.H3_EVENT_COUNT == 750
    assert mod.H3_ROW_COUNT == 22409


def test_checkpoint20g_only_fits_distance_candidate():
    source = inspect.getsource(mod.fit_or_validate_final_h1_h2_distance_model)
    assert "candidate_id=DISTANCE_CANDIDATE_ID" in source
    assert "MOMENTUM_CANDIDATE_ID" not in source


def test_h3_freeze_prohibits_fit_tuning_and_candidate_selection():
    source = inspect.getsource(mod.build_h3_validation_freeze_document)
    assert '"model_parameters_fitted_on_H3": False' in source
    assert '"candidate_selection_on_H3_allowed": False' in source
    assert '"feature_change_on_H3_allowed": False' in source
    assert '"hyperparameter_search_on_H3_allowed": False' in source


def test_h3_freeze_uses_five_equal_chronological_blocks():
    assert mod.H3_BLOCKS == ("B0", "B1", "B2", "B3", "B4")
    assert mod.H3_EVENTS_PER_BLOCK == 150


def test_checkpoint20g_contains_no_network_client_or_h3_outcome_collection():
    source = Path("src/kxbtcd_candidate_e_h3_preparation.py").read_text(
        encoding="utf-8"
    )
    assert "PublicCensusHttpClient" not in source
    assert "collect_h3_outcomes" not in source
    assert "/historical/markets/" not in source


def test_real_checkpoint20g_artifacts_if_present():
    if not mod.DEFAULT_FINAL_MODEL_PATH.exists():
        pytest.skip("20G final model not yet generated")
    model, h3 = mod.validate_checkpoint20g_preparation(".")
    assert model["candidate_id"] == mod.DISTANCE_CANDIDATE_ID
    assert model["fit_scope"]["total_event_count"] == 2250
    assert model["fit_scope"]["H3_rows_used"] == 0
    assert h3["H3_outcomes_opened"] == 0
    assert h3["execution_enabled"] is False
