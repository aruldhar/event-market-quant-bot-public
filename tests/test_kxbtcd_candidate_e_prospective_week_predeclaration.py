from src.kxbtcd_candidate_e_prospective_week_predeclaration import validate_predeclaration

def test_validates():
    p = validate_predeclaration(".")
    assert p["prospective_primary_policy"]["primary_net_edge_threshold_dollars"] == "0.02"
    assert p["prospective_window"]["duration_hours"] == 168

def test_reentry_is_exact_v2_shape():
    p = validate_predeclaration(".")
    q = p["prospective_primary_policy"]
    assert q["max_reentries_per_event"] == 1
    assert q["rearm_after_full_first_exit"]["full_first_exit_required"] is True
    assert q["second_entry_same_timestamp_as_rearm_forbidden"] is True

def test_coinbase_semantics_are_frozen():
    p = validate_predeclaration(".")
    s = p["source_contract"]
    assert s["required_btc_source"] == "Coinbase"
    assert s["no_future_interpolation"] is True
    assert s["no_carry_forward"] is True

def test_e2_cannot_select_primary():
    p = validate_predeclaration(".")
    assert p["e2_result_closeout"]["official_result_immutable"] is True
    assert p["prospective_primary_policy"]["threshold_selection_basis"].endswith("not_july10_pnl")

def test_no_execution_authorization():
    p = validate_predeclaration(".")
    s = p["safety"]
    assert s["order_submission_code_added"] is False
    assert s["demo_orders_authorized"] is False
    assert s["real_money_orders_authorized"] is False
