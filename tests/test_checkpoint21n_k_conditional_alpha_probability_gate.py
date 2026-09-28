from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1_development import build_probability_gate

def make(event, stage, outcome):
    return {
        "event_ticker": event,
        "stage": stage,
        "outcome": str(outcome),
        "market_midpoint_yes_probability": "0.5",
        "candidate_probability": "0.5",
        "global_alpha_0_50_probability": "0.5",
        "adjusted_yes_probability": "0.5",
    }

def test_probability_gate_primary_ties_fail():
    rows=[]
    for i in range(1500):
        stage="H2" if i<750 else "H3"
        rows.append(make(f"E{i:04d}", stage, i % 2))
    gate=build_probability_gate(rows)
    assert gate["status"]=="FAIL"
    assert gate["conditions"]["pooled_log_loss_lt_global_alpha_0_50"] is False
    assert gate["conditions"]["H2_log_loss_lt_global_alpha_0_50"] is False
    assert gate["conditions"]["H3_log_loss_lt_global_alpha_0_50"] is False
    assert gate["conditions"]["median_event_log_loss_improvement_gt_zero"] is False
