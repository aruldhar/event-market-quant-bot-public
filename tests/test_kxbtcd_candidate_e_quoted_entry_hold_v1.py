from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_quoted_entry_hold_v1 import (
    PRIOR_STRATEGY_ID,
    STRATEGY_ID,
    QuotedEntryHoldError,
    build_candidate_side_states,
    net_edge_per_contract,
    quoted_purchase_price,
    select_threshold_events,
    standard_entry_fee,
    validate_predeclaration,
)


def _preoutcome(stage: str, event: str, market: str, ttc: int, role: str, bid: str, ask: str):
    return {
        "stage": stage,
        "event_ticker": event,
        "event_close_time_utc": "2025-01-01T12:00:00Z",
        "market_ticker": market,
        "structural_role": role,
        "ttc_target_minutes": str(ttc),
        "decision_target_utc": f"2025-01-01T11:{60-ttc:02d}:00Z",
        "yes_bid": bid,
        "yes_ask": ask,
    }


def _prediction(schema: str, event: str, market: str, ttc: int, role: str, p: str):
    return {
        "schema_version": schema,
        "candidate_id": "kxbtcd_btc_distance_offset_logistic.v1",
        "state_id": f"{event}|{market}|TTC{ttc}|{role}",
        "event_ticker": event,
        "market_ticker": market,
        "candidate_probability": p,
        # This field is deliberately ignored by the opportunity computation.
        "outcome": "1",
    }


def test_predeclaration_is_distinct_and_supersedes_old_design_before_scoring() -> None:
    document = validate_predeclaration()
    assert document["strategy_id"] == STRATEGY_ID
    assert document["prior_strategy_design"]["strategy_id"] == PRIOR_STRATEGY_ID
    assert document["prior_strategy_design"]["status"] == "superseded_before_economic_scoring"
    assert document["prior_strategy_design"]["strategy_pnl_inspected"] is False


def test_one_contract_fee_uses_upward_cent_rounding() -> None:
    assert standard_entry_fee(price="0.58") == Decimal("0.02")
    assert standard_entry_fee(price="0.01") == Decimal("0.01")
    assert standard_entry_fee(price="0") == Decimal("0.00")


def test_yes_and_no_prices_use_executable_quote_sides() -> None:
    assert quoted_purchase_price(side="YES", yes_bid="0.41", yes_ask="0.43") == Decimal("0.43")
    assert quoted_purchase_price(side="NO", yes_bid="0.41", yes_ask="0.43") == Decimal("0.59")


def test_net_edge_is_after_fee() -> None:
    edge, price, fee = net_edge_per_contract(
        side="YES",
        candidate_probability="0.64",
        yes_bid="0.56",
        yes_ask="0.58",
    )
    assert price == Decimal("0.58")
    assert fee == Decimal("0.02")
    assert edge == Decimal("0.04")


def test_first_qualifying_anchor_wins_even_if_later_edge_is_larger() -> None:
    rows = (
        {
            "stage": "H2", "event_ticker": "E", "event_close_time_utc": "2025-01-01T12:00:00Z",
            "ttc_target_minutes": "55", "market_ticker": "M1", "side": "YES",
            "decision_time_utc": "2025-01-01T11:05:00Z", "structural_role": "q50",
            "candidate_probability": "0.60", "quoted_purchase_price": "0.55",
            "standard_entry_fee": "0.02", "net_edge_per_contract": "0.03",
        },
        {
            "stage": "H2", "event_ticker": "E", "event_close_time_utc": "2025-01-01T12:00:00Z",
            "ttc_target_minutes": "50", "market_ticker": "M2", "side": "YES",
            "decision_time_utc": "2025-01-01T11:10:00Z", "structural_role": "q50",
            "candidate_probability": "0.70", "quoted_purchase_price": "0.60",
            "standard_entry_fee": "0.02", "net_edge_per_contract": "0.08",
        },
    )
    selected = select_threshold_events(rows, threshold=Decimal("0.02"))
    assert len(selected) == 1
    assert selected[0]["action"] == "ENTER"
    assert selected[0]["market_ticker"] == "M1"
    assert selected[0]["ttc_target_minutes"] == "55"


def test_largest_edge_and_deterministic_tie_break_are_within_anchor_only() -> None:
    common = {
        "stage": "H3", "event_ticker": "E", "event_close_time_utc": "2025-01-01T12:00:00Z",
        "ttc_target_minutes": "40", "decision_time_utc": "2025-01-01T11:20:00Z",
        "structural_role": "q50", "candidate_probability": "0.60",
        "quoted_purchase_price": "0.55", "standard_entry_fee": "0.02",
    }
    rows = (
        {**common, "market_ticker": "B", "side": "YES", "net_edge_per_contract": "0.04"},
        {**common, "market_ticker": "A", "side": "NO", "net_edge_per_contract": "0.04"},
        {**common, "market_ticker": "C", "side": "YES", "net_edge_per_contract": "0.03"},
    )
    selected = select_threshold_events(rows, threshold=Decimal("0.03"))
    assert selected[0]["market_ticker"] == "A"
    assert selected[0]["side"] == "NO"


def test_candidate_side_state_build_uses_prediction_probability_and_preoutcome_quote_only() -> None:
    pre = [
        _preoutcome("H1", "E1", "M1", 55, "q50", "0.50", "0.52"),
        _preoutcome("H2", "E2", "M2", 55, "q50", "0.40", "0.42"),
        _preoutcome("H3", "E3", "M3", 55, "q50", "0.30", "0.32"),
    ]
    h1 = [_prediction("kxbtcd_candidate_e_h1_oof_prediction.v1", "E1", "M1", 55, "q50", "0.60")]
    h2 = [_prediction("kxbtcd_candidate_e_h2_prediction.v1", "E2", "M2", 55, "q50", "0.50")]
    h3 = [_prediction("kxbtcd_candidate_e_h3_prediction.v1", "E3", "M3", 55, "q50", "0.40")]
    rows = build_candidate_side_states(
        preoutcome_rows=pre,
        h1_prediction_rows=h1,
        h2_prediction_rows=h2,
        h3_prediction_rows=h3,
        enforce_frozen_counts=False,
    )
    assert len(rows) == 6
    e1_yes = next(row for row in rows if row["event_ticker"] == "E1" and row["side"] == "YES")
    assert e1_yes["candidate_probability"] == "0.6"
    assert e1_yes["yes_ask"] == "0.52"
    # If the ignored outcome field were being used, this result would differ.
    assert e1_yes["net_edge_per_contract"] == "0.06"


def test_crossed_quote_fails_closed() -> None:
    with pytest.raises(QuotedEntryHoldError):
        quoted_purchase_price(side="YES", yes_bid="0.60", yes_ask="0.50")


def test_no_network_or_execution_surface() -> None:
    paths = (
        Path("src/kxbtcd_candidate_e_quoted_entry_hold_v1.py"),
        Path("audit_kxbtcd_candidate_e_quoted_entry_hold_v1_opportunities.py"),
    )
    forbidden = (
        "import requests",
        "import websockets",
        "create_order",
        "cancel_order",
        "/portfolio/",
        "paper broker",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text
