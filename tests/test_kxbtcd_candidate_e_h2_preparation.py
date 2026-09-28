from __future__ import annotations

import copy

import pytest

from src.kxbtcd_candidate_e_h2_preparation import (
    CandidateEH2PreparationError,
    DISTANCE_CANDIDATE_ID,
    H2_BLOCKS,
    H2_EVENTS_PER_BLOCK,
    passes_h2_validation_gate,
    validate_final_model_document,
    validate_h2_validation_freeze_document,
)


def test_h2_gate_passes_when_all_frozen_conditions_pass():
    assert passes_h2_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[0.01, 0.02, 0.03, -0.001, 0.04],
        median_event_raw_minus_candidate_log_loss=0.005,
        final_h1_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_h2_gate_fails_with_only_three_block_wins():
    assert not passes_h2_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[0.01, -0.01, 0.03, -0.001, 0.04],
        median_event_raw_minus_candidate_log_loss=0.005,
        final_h1_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_h2_gate_fails_when_latest_block_loses():
    assert not passes_h2_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[0.01, 0.02, 0.03, 0.04, -0.001],
        median_event_raw_minus_candidate_log_loss=0.005,
        final_h1_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_h2_gate_fails_on_negative_pooled_brier_delta():
    assert not passes_h2_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=-1e-9,
        block_raw_minus_candidate_log_loss=[0.01, 0.02, 0.03, 0.04, 0.05],
        median_event_raw_minus_candidate_log_loss=0.005,
        final_h1_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_h2_block_contract_is_exactly_five_by_150():
    assert H2_BLOCKS == ("B0", "B1", "B2", "B3", "B4")
    assert H2_EVENTS_PER_BLOCK == 150


def test_final_model_validator_rejects_unauthorized_momentum_parameter(tmp_path, monkeypatch):
    # Build the smallest structurally valid mock then monkeypatch lineage checks by
    # asking the validator not to verify current files. The test focuses on the
    # candidate-shape firewall.
    import src.kxbtcd_candidate_e_h2_preparation as mod

    predecl = mod.candidate_e_predeclaration()
    payload = {
        "schema_version": mod.FINAL_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "20C",
        "family_id": predecl["family_id"],
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": mod.FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": mod.FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": mod.FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_evaluation_fingerprint": mod.EXPECTED_H1_EVALUATION_FINGERPRINT,
        "h1_result_fingerprint": mod.H1_RESULT_FINGERPRINT,
        "cohort_map_fingerprint": mod.EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": mod.EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "fit_scope": {
            "stage": "H1",
            "event_count": mod.H1_EVENT_COUNT,
            "row_count": mod.H1_ROW_COUNT,
            "blocks": ["B0","B1","B2","B3","B4","B5","B6"],
            "all_H1_events_used": True,
            "H2_rows_used": 0,
            "H3_rows_used": 0,
        },
        "model": {
            "formula": "logit(p)=market_logit_offset + beta_distance*d_BTC",
            "market_logit_offset_clip": "0.001",
            "feature": "btc_strike_log_distance_bps.v1",
            "beta_distance": "0.01",
            "beta_momentum": "0.001",
            "free_parameter_count": 2,
        },
        "fit_contract": predecl["fit_contract"],
        "fit_result": {"iterations": 5, "converged": True, "fit_objective": "0.02"},
        "lineage": {
            "source_baseline_commit": mod.EXPECTED_BASELINE_COMMIT,
        },
        "selection_frozen_before_full_fit": True,
        "posthoc_H1_feature_change_performed": False,
        "posthoc_H1_candidate_change_performed": False,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    payload["final_model_fingerprint"] = mod._canonical_sha256(
        {k: v for k, v in payload.items() if k != "final_model_fingerprint"}
    )
    with pytest.raises(CandidateEH2PreparationError):
        validate_final_model_document(
            payload,
            repository_root=tmp_path,
            verify_current_lineage_files=False,
        )


def test_fast_h1_outcome_validator_precomputes_sealed_sets_once():
    """Regression: the 20C path must not call the old per-row sealed-set validator."""
    import inspect
    import src.kxbtcd_candidate_e_h2_preparation as mod

    source = inspect.getsource(mod._validate_h1_outcomes_fast)
    assert "validate_h1_outcomes(" not in source
    assert "sealed_events =" in source
    assert "sealed_markets =" in source


def test_full_h1_fit_path_uses_fast_observation_builder():
    import inspect
    import src.kxbtcd_candidate_e_h2_preparation as mod

    source = inspect.getsource(mod.fit_or_validate_final_h1_distance_model)
    assert "_build_h1_observations_fast(" in source
    assert "build_h1_observations(" not in source
