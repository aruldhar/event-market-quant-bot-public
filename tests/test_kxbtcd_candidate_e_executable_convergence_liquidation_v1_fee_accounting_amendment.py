import copy
import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_fee_accounting_amendment import (
    CONFIG_PATH, canonical_fingerprint, load_amendment, validate_amendment,
)

def test_amendment_validates_and_fingerprint_reproduces():
    doc = load_amendment(CONFIG_PATH)
    validate_amendment(doc)
    assert canonical_fingerprint(doc) == doc["amendment_fingerprint"]

def test_only_fee_accounting_is_amended():
    doc = load_amendment(CONFIG_PATH)
    reason = doc["reason"]
    assert reason["strategy_logic_changed"] is False
    assert reason["candidate_e_changed"] is False
    assert reason["entry_rule_changed"] is False
    assert reason["liquidation_rule_changed"] is False
    assert reason["threshold_menu_changed"] is False
    assert reason["latency_menu_changed"] is False

def test_direct_member_precision_and_six_decimal_trade_fee_are_frozen():
    doc = load_amendment(CONFIG_PATH)
    assert doc["accounting_regime"]["primary_counterfactual_member_type"] == "direct_member"
    assert doc["accounting_regime"]["target_balance_precision_dollars"] == "0.0001"
    assert doc["trade_fee_policy"]["per_synthetic_fill_trade_fee"] == "ceil_to_0.000001(model_fee)"
    assert doc["fill_cash_rounding_policy"]["accumulator_resets_between_orders"] is True

def test_supersession_is_narrow():
    doc = load_amendment(CONFIG_PATH)
    assert set(doc["supersession"]["base_fields_superseded"]) == {
        "fee_and_cash_rounding.trade_fee_rounding",
        "fee_and_cash_rounding.cash_rounding",
        "fee_and_cash_rounding.rounding_accumulator",
    }
    assert doc["supersession"]["all_non_fee_strategy_rules_remain_frozen_under_base_predeclaration"] is True

def test_outcome_and_execution_firewalls_remain_closed():
    doc = load_amendment(CONFIG_PATH)
    assert doc["reason"]["outcomes_accessed_before_amendment"] is False
    assert doc["reason"]["strategy_pnl_calculated_before_amendment"] is False
    for key in (
        "outcomes_accessed", "strategy_pnl_calculated", "orders_submitted",
        "paper_broker", "demo_execution", "real_money_execution",
        "new_predexon_purchase_authorized", "protected_evidence_access_authorized",
    ):
        assert doc["safety"][key] is False

def test_mutation_breaks_fingerprint():
    doc = load_amendment(CONFIG_PATH)
    changed = copy.deepcopy(doc)
    changed["accounting_regime"]["target_balance_precision_dollars"] = "0.01"
    with pytest.raises(Exception, match="balance precision|fingerprint"):
        validate_amendment(changed)
