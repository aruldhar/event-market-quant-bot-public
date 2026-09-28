from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.kxbtcd_candidate_e_h3_evaluation as mod


def test_checkpoint20h_frozen_parent_identities():
    assert mod.CP20H_PARENT_RECEIPT_COMMIT == (
        "932d275cba192f1f8cad1259bb7a2642dd0f6e3a"
    )
    assert mod.FINAL_H1_H2_MODEL_FINGERPRINT == (
        "1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842"
    )
    assert mod.H3_VALIDATION_FINGERPRINT == (
        "a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197"
    )
    assert (mod.H3_EVENT_COUNT, mod.H3_ROW_COUNT, mod.H3_MARKET_COUNT) == (
        750,
        22409,
        3750,
    )


def test_h3_prediction_uses_positive_distance_in_expected_direction():
    beta = 0.013805016135330063
    at_strike = mod.predict_h3_probability(
        q_market=0.5,
        d_btc=0.0,
        beta_distance=beta,
    )
    above = mod.predict_h3_probability(
        q_market=0.5,
        d_btc=100.0,
        beta_distance=beta,
    )
    below = mod.predict_h3_probability(
        q_market=0.5,
        d_btc=-100.0,
        beta_distance=beta,
    )
    assert below < at_strike < above
    assert at_strike == pytest.approx(0.5)


def test_h3_evaluator_contains_no_candidate_fit_call():
    source = inspect.getsource(mod)
    assert "fit_candidate_e(" not in source
    assert "model_parameters_fitted_on_H3" in source


def test_h3_gate_requires_four_of_five_and_latest_win():
    assert mod.passes_h3_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[0.01, 0.02, -0.001, 0.03, 0.04],
        median_event_raw_minus_candidate_log_loss=0.002,
        final_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )
    assert not mod.passes_h3_validation_gate(
        pooled_raw_minus_candidate_log_loss=0.01,
        pooled_raw_minus_candidate_brier=0.001,
        block_raw_minus_candidate_log_loss=[0.01, 0.02, 0.03, 0.04, -0.001],
        median_event_raw_minus_candidate_log_loss=0.002,
        final_model_valid=True,
        structural_coverage_ok=True,
        policy_firewall_ok=True,
    )


def test_h1_h2_identity_is_hard_denied():
    with pytest.raises(mod.CandidateEH3EvaluationError):
        mod.assert_not_h1_h2_identity(
            h1_h2_events=frozenset({"OLD-EVENT"}),
            h1_h2_markets=frozenset({"OLD-MARKET"}),
            event_ticker="OLD-EVENT",
            market_ticker="OTHER",
        )
    with pytest.raises(mod.CandidateEH3EvaluationError):
        mod.assert_not_h1_h2_identity(
            h1_h2_events=frozenset({"OLD-EVENT"}),
            h1_h2_markets=frozenset({"OLD-MARKET"}),
            event_ticker="OTHER",
            market_ticker="OLD-MARKET",
        )


def test_h1_h2_identity_sets_are_derived_from_frozen_stage_rows():
    universe = SimpleNamespace(
        cohort_rows=tuple(
            {"stage": "H1" if i < 1500 else "H2", "event_ticker": f"E{i}"}
            for i in range(2250)
        ),
        preoutcome_rows=tuple(
            {"stage": "H1" if i < 5 else "H2", "market_ticker": f"M{i}"}
            for i in range(10)
        ),
    )
    events, markets = mod._h1_h2_identity_sets(universe)
    assert len(events) == 2250
    assert len(markets) == 10


def test_collector_cli_exposes_only_resume_control():
    source = Path("collect_kxbtcd_candidate_e_h3.py").read_text(encoding="utf-8")
    assert "--resume-from-manifest" in source
    assert "--ticker" not in source
    assert "--partition" not in source
    assert "--candidate" not in source
    assert "--beta" not in source


def test_implementation_freeze_hashes_only_data_exposing_path():
    assert mod.H3_IMPLEMENTATION_FILES == (
        "src/kxbtcd_candidate_e_h3_evaluation.py",
        "collect_kxbtcd_candidate_e_h3.py",
    )
