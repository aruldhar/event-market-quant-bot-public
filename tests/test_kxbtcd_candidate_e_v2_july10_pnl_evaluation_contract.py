from decimal import Decimal
import pytest
from src import kxbtcd_candidate_e_v2_july10_pnl_evaluation_contract as m

def settlement(ticker: str, result: str):
    return {
        "ticker": ticker,
        "market_type": "binary",
        "status": "finalized",
        "settlement_ts": "2026-07-10T20:00:00Z",
        "is_provisional": False,
        "result": result,
        "settlement_value_dollars": "1" if result == "yes" else "0",
    }

def full_trade(entry_cash="-0.7824", exit_cash="0.8305"):
    return {
        "entry": {"ioc": {"status": "FULL", "net_cash_change_total": entry_cash}},
        "signal": {"market_ticker": "KX-TEST", "side": "YES"},
        "liquidation": {
            "status": "EXIT_FULL",
            "exit_ioc": {"status": "FULL", "net_cash_change_total": exit_cash},
            "settlement_fallback_quantity": "0",
        },
    }

def fallback_trade(side="YES", entry_cash="-0.40"):
    return {
        "entry": {"ioc": {"status": "FULL", "net_cash_change_total": entry_cash}},
        "signal": {"market_ticker": "KX-TEST", "side": side},
        "liquidation": {
            "status": "EXIT_MISSED_SETTLEMENT_FALLBACK",
            "exit_ioc": None,
            "settlement_fallback_quantity": "1",
        },
    }

def mini_contract():
    return {"censored_path_accounting": {"pnl_lower_bound_dollars": "-2.0700", "pnl_upper_bound_dollars": "2"}}

def test_exit_full_pnl_uses_net_cash_changes():
    assert m.exact_trade_pnl(full_trade(), {}) == Decimal("0.0481")

def test_yes_settlement_fallback():
    trade = fallback_trade("YES", "-0.40")
    assert m.exact_trade_pnl(trade, {"KX-TEST": settlement("KX-TEST", "yes")}) == Decimal("0.60")
    assert m.exact_trade_pnl(trade, {"KX-TEST": settlement("KX-TEST", "no")}) == Decimal("-0.40")

def test_no_settlement_fallback():
    trade = fallback_trade("NO", "-0.30")
    assert m.exact_trade_pnl(trade, {"KX-TEST": settlement("KX-TEST", "no")}) == Decimal("0.70")
    assert m.exact_trade_pnl(trade, {"KX-TEST": settlement("KX-TEST", "yes")}) == Decimal("-0.30")

def test_nonbinary_or_inconsistent_settlement_fails_closed():
    bad = settlement("KX-TEST", "yes")
    bad["settlement_value_dollars"] = "0"
    with pytest.raises(m.PnlContractError):
        m.validate_binary_settlement(market_ticker="KX-TEST", settlement=bad)
    bad2 = settlement("KX-TEST", "yes")
    bad2["result"] = "scalar"
    bad2["settlement_value_dollars"] = "0.5"
    with pytest.raises(m.PnlContractError):
        m.validate_binary_settlement(market_ticker="KX-TEST", settlement=bad2)

def test_censored_scenario_forbids_point_pnl_and_uses_frozen_interval():
    c = mini_contract()
    assert m.event_interval(path_observation_class="CENSORED", exact_pnl=None, contract=c) == (Decimal("-2.0700"), Decimal("2"))
    with pytest.raises(m.PnlContractError):
        m.event_interval(path_observation_class="CENSORED", exact_pnl="0.1", contract=c)

def test_exact_scenario_collapses_to_point():
    c = mini_contract()
    assert m.event_interval(path_observation_class="EXACT", exact_pnl="0.1234", contract=c) == (Decimal("0.1234"), Decimal("0.1234"))

def test_four_event_robustness_taxonomy():
    pos = m.aggregate_four_event_intervals([(Decimal("0.1"), Decimal("0.2"))] * 4)
    assert pos["classification"] == "ROBUST_POSITIVE"
    neg = m.aggregate_four_event_intervals([(Decimal("-0.3"), Decimal("-0.1"))] * 4)
    assert neg["classification"] == "ROBUST_NEGATIVE"
    inc = m.aggregate_four_event_intervals([
        (Decimal("-2.07"), Decimal("2")),
        (Decimal("0.2"), Decimal("0.2")),
        (Decimal("0.2"), Decimal("0.2")),
        (Decimal("0.2"), Decimal("0.2")),
    ])
    assert inc["classification"] == "INCONCLUSIVE"

def test_exact_policy_pnl_allows_zero_trades():
    assert m.exact_policy_pnl({"trades": []}, {}) == Decimal("0")
