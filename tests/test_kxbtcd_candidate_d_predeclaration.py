from src.kxbtcd_candidate_d_predeclaration import (
    CANDIDATE_ID,
    FROZEN_PREDECLARATION_FINGERPRINT,
    candidate_d_predeclaration,
    candidate_d_predeclaration_fingerprint,
    validate_candidate_d_predeclaration,
)


def test_fingerprint_is_frozen():
    assert validate_candidate_d_predeclaration() == FROZEN_PREDECLARATION_FINGERPRINT
    assert candidate_d_predeclaration_fingerprint() == "a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537"


def test_candidate_d_is_calibration_only_and_raw_is_nested():
    spec = candidate_d_predeclaration()
    assert CANDIDATE_ID == "kxbtcd_market_logit_recalibration.v1"
    assert spec["model"]["input_feature"] == "q_market_only"
    assert spec["model"]["spread_feature"] == "prohibited"
    assert spec["model"]["market_logit_x_spread_interaction"] == "prohibited"
    assert spec["model"]["other_features"] == "prohibited"
    assert spec["model"]["raw_midpoint_nested_at"] == {"alpha": "0", "delta": "0"}
    assert spec["model"]["feature_scaling"] == "none"


def test_no_tuning_or_regularization_is_allowed():
    spec = candidate_d_predeclaration()
    assert spec["model"]["regularization"] == "none"
    assert spec["model"]["hyperparameter_grid"] == []
    assert spec["model"]["hyperparameter_search"] is False
    assert spec["model"]["fit_initialization"] == {"alpha": "0", "delta": "0"}


def test_seven_block_layout_and_five_score_folds_are_exact():
    spec = candidate_d_predeclaration()
    protocol = spec["development_protocol"]
    assert [b["week_count"] for b in protocol["blocks"]] == [9, 9, 8, 8, 8, 8, 8]
    assert [b["event_count"] for b in protocol["blocks"]] == [35, 36, 32, 32, 32, 32, 32]
    assert [f["score_block"] for f in protocol["rolling_origin_folds"]] == ["B2", "B3", "B4", "B5", "B6"]
    assert protocol["scored_event_count"] == 160
    assert protocol["layout_construction_used_outcomes"] is False


def test_gate_is_stricter_and_latest_block_is_required():
    spec = candidate_d_predeclaration()
    conditions = spec["development_advancement_gate"]["conditions"]
    assert "D log loss strictly beats raw in at least 4 of 5 score blocks" in conditions
    assert "D log loss strictly beats raw in latest score block B6" in conditions
    assert "median event-level raw-minus-D log-loss delta > 0" in conditions
    assert "all five fitted market-logit slopes (1 + delta) are > 0" in conditions


def test_terminal_firewall_and_execution_boundary_remain_closed():
    spec = candidate_d_predeclaration()
    assert spec["evidence_boundary"]["checkpoint17_terminal_rows_labels_features_predictions_residuals_slices_prohibited"] is True
    assert spec["future_untouched_test_boundary"]["checkpoint17_terminal_block_reuse"] == "prohibited"
    assert spec["safety"]["candidate_d_fit_authorized_by_this_predeclaration"] is False
    assert spec["safety"]["paper_execution"] is False
    assert spec["safety"]["demo_execution"] is False
    assert spec["safety"]["real_money_execution"] is False
    assert spec["safety"]["orders"] is False
