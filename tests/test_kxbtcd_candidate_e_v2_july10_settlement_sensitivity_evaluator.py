from copy import deepcopy
from decimal import Decimal

import pytest

from src import kxbtcd_candidate_e_v2_july10_settlement_sensitivity_evaluator as s


def settlement_record(ticker: str, yes_value: str) -> dict:
    result = "yes" if yes_value == "1" else "no"
    return {
        "schema_version": "candidate_e_v2_exact_settlement_record.v1",
        "source_id": "kalshi_partitioned_market_settlement_v1",
        "source_tier": "live_recent",
        "source_endpoint": f"/markets?tickers={ticker}",
        "market": {
            "ticker": ticker,
            "event_ticker": ticker.rsplit("-T", 1)[0],
            "market_type": "binary",
            "status": "finalized",
            "result": result,
            "settlement_value_dollars": yes_value,
            "settlement_ts": "2026-07-10T20:00:00Z",
            "is_provisional": False,
        },
        "raw_reference": {
            "source": "synthetic",
            "session_id": "synthetic-session",
            "request_id": "synthetic-request",
        },
        "request_started_at_utc": "2026-07-10T20:00:00Z",
        "received_at_utc": "2026-07-10T20:00:00Z",
    }


def test_settlement_cash_yes_and_no():
    yes = settlement_record("KXBTCD-TEST-T1", "1")
    no = settlement_record("KXBTCD-TEST-T2", "0")
    assert s.settlement_cash(record=yes, side="YES", quantity="1") == Decimal("1")
    assert s.settlement_cash(record=yes, side="NO", quantity="1") == Decimal("0")
    assert s.settlement_cash(record=no, side="YES", quantity="1") == Decimal("0")
    assert s.settlement_cash(record=no, side="NO", quantity="1") == Decimal("1")


def test_independent_entry_diagnostic_uses_full_actual_fill():
    trade = {
        "event_ticker": "E",
        "threshold_dollars": "0.01",
        "latency_ms": 500,
        "censorship_subclass": "CENSORED_SELECTION_REARM_ONLY",
        "trade_number": 1,
        "market_ticker": "KXBTCD-TEST-T1",
        "side": "YES",
        "entry_filled_quantity": "0.5",
        "entry_net_cash_change_total": "-0.2",
    }
    out = s.entry_settlement_diagnostic(
        trade,
        {"KXBTCD-TEST-T1": settlement_record("KXBTCD-TEST-T1", "1")},
    )
    assert out["terminal_cash_dollars"] == "0.5"
    assert out["independent_hold_to_settlement_pnl_dollars"] == "0.3"
    assert out["pnl_sign"] == "POSITIVE"
    assert out["side_settled_in_the_money"] is True


def test_observed_trace_preserves_known_exit_and_settles_only_residual():
    trades = [
        {
            "market_ticker": "KXBTCD-TEST-T1",
            "side": "YES",
            "entry_net_cash_change_total": "-0.4",
            "known_exit_net_cash_change_total": "0.3",
            "known_residual_settlement_quantity": "0.5",
        }
    ]
    out = s.observed_trace_terminal_value(
        trades=trades,
        settlement_records={
            "KXBTCD-TEST-T1": settlement_record("KXBTCD-TEST-T1", "1")
        },
    )
    assert out == Decimal("0.4")


def test_observed_trace_zero_trades_is_descriptive_zero():
    assert s.observed_trace_terminal_value(trades=[], settlement_records={}) == Decimal("0")


def test_censorship_subclass_labels():
    assert s.censorship_subclass({
        "path_observation_class": "EXACT",
        "selection_or_rearm_censored": False,
        "explicit_liquidation_censored": False,
    }) == "EXACT"
    assert s.censorship_subclass({
        "path_observation_class": "CENSORED",
        "selection_or_rearm_censored": True,
        "explicit_liquidation_censored": False,
    }) == "CENSORED_SELECTION_REARM_ONLY"
    assert s.censorship_subclass({
        "path_observation_class": "CENSORED",
        "selection_or_rearm_censored": False,
        "explicit_liquidation_censored": True,
    }) == "CENSORED_LIQUIDATION_ONLY"
    assert s.censorship_subclass({
        "path_observation_class": "CENSORED",
        "selection_or_rearm_censored": True,
        "explicit_liquidation_censored": True,
    }) == "CENSORED_BOTH"


def test_frozen_e1_validates_and_has_12_tickers_93_entries():
    predecl, observed, contract = s.load_frozen_e1(".")
    assert predecl["future_settlement_access"]["ticker_count"] == 12
    assert observed["observed_filled_trade_count"] == 93
    assert len(contract["scenario_classification"]) == 60


def test_collection_gate_message_is_e2_specific():
    assert (
        s.EXPECTED_IMPLEMENTATION_CHECKPOINT_MESSAGE
        == "Checkpoint 21N-Y-E2 - July10 Settlement Sensitivity Evaluator"
    )
    assert len(s.REQUIRED_CLOSEOUT_PATHS) == 9
