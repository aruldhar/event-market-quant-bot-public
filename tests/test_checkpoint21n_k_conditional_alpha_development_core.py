from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1_development import (
    attach_labels, project_development_labels, select_lambda, ConditionalAlphaDevelopmentError
)
import pytest

def feature(state, stage="H1_OOF", event="E1", market="M1"):
    return {
        "schema_version":"kxbtcd_candidate_e_conditional_alpha_feature_row.v1",
        "candidate_id":"kxbtcd_candidate_e_conditional_alpha_reliability.v1",
        "stage":stage,"state_id":state,"event_ticker":event,
        "event_close_time_utc":"2026-01-01T00:00:00Z","market_ticker":market,
        "structural_role":"q50","ttc_target_minutes":"55",
        "decision_time_utc":"2025-12-31T23:05:00Z",
        "candidate_probability":"0.6","market_midpoint_yes_probability":"0.5",
        "yes_bid":"0.49","yes_ask":"0.51",
        "abs_candidate_market_disagreement":"0.1","spread_t":"0.02",
        "abs_r_5m":"3.0","ttc_minutes":"55",
    }

def test_attach_labels_exact_state():
    f=[feature("S1")]
    labels=[{"stage":"H1_OOF","state_id":"S1","event_ticker":"E1","market_ticker":"M1","outcome":1}]
    out=attach_labels(f,labels,enforce_frozen_counts=False)
    assert out[0]["outcome"]==1

def test_attach_labels_rejects_extra_state():
    f=[feature("S1")]
    labels=[{"stage":"H1_OOF","state_id":"S2","event_ticker":"E1","market_ticker":"M1","outcome":1}]
    with pytest.raises(ConditionalAlphaDevelopmentError):
        attach_labels(f,labels,enforce_frozen_counts=False)

def test_lambda_exact_tie_prefers_larger():
    rows=[{"lambda":0.001,"pooled_H2_H3_event_equal_log_loss":0.1},
          {"lambda":0.01,"pooled_H2_H3_event_equal_log_loss":0.1},
          {"lambda":0.1,"pooled_H2_H3_event_equal_log_loss":0.2},
          {"lambda":1.0,"pooled_H2_H3_event_equal_log_loss":0.3},
          {"lambda":10.0,"pooled_H2_H3_event_equal_log_loss":0.4}]
    assert select_lambda(rows)==0.01
