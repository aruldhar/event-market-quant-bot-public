from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.kxbtcd_candidate_e_h2_evaluation as mod
from src.kxbtcd_candidate_e_h2_preparation import passes_h2_validation_gate


def test_checkpoint20d_frozen_parent_identities():
    assert mod.CP20D_PARENT_RECEIPT_COMMIT == (
        "2e3bf78544a0a4194eef8e6546b00113a340bf5e"
    )
    assert mod.FINAL_H1_MODEL_FINGERPRINT == (
        "d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a"
    )
    assert mod.H2_VALIDATION_FINGERPRINT == (
        "57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9"
    )
    assert (mod.H2_EVENT_COUNT, mod.H2_ROW_COUNT, mod.H2_MARKET_COUNT) == (
        750,
        22354,
        3750,
    )


def test_h2_prediction_uses_positive_distance_in_expected_direction():
    beta = 0.012310034918384302
    at_strike = mod.predict_h2_probability(
        q_market=0.5,
        d_btc=0.0,
        beta_distance=beta,
    )
    above = mod.predict_h2_probability(
        q_market=0.5,
        d_btc=100.0,
        beta_distance=beta,
    )
    below = mod.predict_h2_probability(
        q_market=0.5,
        d_btc=-100.0,
        beta_distance=beta,
    )
    assert below < at_strike < above
    assert at_strike == pytest.approx(0.5)


def test_h2_evaluator_contains_no_candidate_fit_call():
    source = inspect.getsource(mod)
    assert "fit_candidate_e(" not in source
    assert "model_parameters_fitted_on_H2" in source


def test_h2_gate_requires_four_of_five_and_latest_win():
    assert passes_h2_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[0.01, 0.02, -0.001, 0.03, 0.04],
        median_event_raw_minus_candidate_log_loss=0.002,
        final_h1_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )
    assert not passes_h2_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[0.01, 0.02, 0.03, 0.04, -0.001],
        median_event_raw_minus_candidate_log_loss=0.002,
        final_h1_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_h3_identity_is_hard_denied():
    with pytest.raises(mod.CandidateEH2EvaluationError):
        mod.assert_not_h3_identity(
            h3_events=frozenset({"H3-EVENT"}),
            h3_markets=frozenset({"H3-MARKET"}),
            event_ticker="H3-EVENT",
            market_ticker="OTHER",
        )
    with pytest.raises(mod.CandidateEH2EvaluationError):
        mod.assert_not_h3_identity(
            h3_events=frozenset({"H3-EVENT"}),
            h3_markets=frozenset({"H3-MARKET"}),
            event_ticker="OTHER",
            market_ticker="H3-MARKET",
        )


def test_h3_identity_sets_are_derived_once_from_frozen_stage_rows():
    universe = SimpleNamespace(
        cohort_rows=(
            {"stage": "H3", "event_ticker": f"E{i}"}
            for i in range(mod.H3_EVENT_COUNT)
        ),
        preoutcome_rows=(
            {"stage": "H3", "market_ticker": f"M{i}"}
            for i in range(10)
        ),
    )
    events, markets = mod._h3_identity_sets(universe)
    assert len(events) == mod.H3_EVENT_COUNT
    assert len(markets) == 10


def test_collector_cli_exposes_only_resume_control():
    source = Path("collect_kxbtcd_candidate_e_h2.py").read_text(encoding="utf-8")
    assert "--resume-from-manifest" in source
    assert "--ticker" not in source
    assert "--partition" not in source
    assert "--candidate" not in source
    assert "--beta" not in source


def test_implementation_freeze_hashes_only_data_exposing_path():
    assert mod.H2_IMPLEMENTATION_FILES == (
        "src/kxbtcd_candidate_e_h2_evaluation.py",
        "collect_kxbtcd_candidate_e_h2.py",
    )
