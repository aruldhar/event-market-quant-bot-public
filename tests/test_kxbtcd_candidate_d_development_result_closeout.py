from src.kxbtcd_candidate_d_development_result_closeout import (
    EXPECTED,
    EXPECTED_GATE,
    EXPECTED_RESULT_FINGERPRINT,
    advancement_decision,
    validate_summary,
)


def canonical_summary():
    summary = dict(EXPECTED)
    summary.update({
        "candidate_id": "kxbtcd_market_logit_recalibration.v1",
        "candidate_d_predeclaration_fingerprint": "a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537",
        "week_map_fingerprint": "ba93f6a063c616a34437d6f9d208e39b85c993868c71ea78db8b40a70ec23dff",
        "evaluation_result_fingerprint": EXPECTED_RESULT_FINGERPRINT,
        "development_advancement_gate": dict(EXPECTED_GATE),
    })
    return summary


def test_exact_completed_fail_result_validates():
    validated = validate_summary(canonical_summary())
    assert validated["development_screen_passed"] is False


def test_decision_rejects_candidate_d_without_post_hoc_repair():
    decision = advancement_decision(canonical_summary())
    assert decision["development_result"] == "FAIL"
    assert decision["advance_candidate_d"] is False
    assert decision["post_hoc_candidate_d_repair_on_same_screen_authorized"] is False
    assert decision["final_development_fit_authorized"] is False
    assert decision["prospective_terminal_evaluation_authorized"] is False


def test_gate_failure_reasons_are_exactly_the_two_predeclared_temporal_failures():
    decision = advancement_decision(canonical_summary())
    assert decision["failure_reasons"] == [
        "fewer_than_4_of_5_score_block_log_loss_wins",
        "latest_B6_log_loss_not_strictly_better",
    ]


def test_rejects_attempt_to_turn_fail_into_pass():
    summary = canonical_summary()
    summary["development_screen_passed"] = True
    try:
        validate_summary(summary)
    except Exception:
        pass
    else:
        raise AssertionError("changed Candidate-D FAIL was not rejected")


def test_rejects_changed_result_fingerprint():
    summary = canonical_summary()
    summary["evaluation_result_fingerprint"] = "0" * 64
    try:
        validate_summary(summary)
    except Exception:
        pass
    else:
        raise AssertionError("changed result fingerprint was not rejected")
