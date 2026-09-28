from decimal import Decimal
from pathlib import Path

from src.kxbtcd_candidate_e_reliability_shrinkage_entry_v2 import (
    EXPECTED_PREDECLARATION_FINGERPRINT,
    adjusted_side_probability,
    adjust_base_side_state,
    market_anchor_side_probability,
    validate_predeclaration,
)


def _base(side="YES", p="0.90", bid="0.79", ask="0.81"):
    qprice = ask if side == "YES" else str(Decimal("1") - Decimal(bid))
    sfair = p if side == "YES" else str(Decimal("1") - Decimal(p))
    return {
        "strategy_id": "kxbtcd_candidate_e_quoted_entry_hold_v1",
        "stage": "H2",
        "state_id": "E|M|TTC55|q50",
        "event_ticker": "E",
        "event_close_time_utc": "2026-01-01T01:00:00Z",
        "market_ticker": "M",
        "structural_role": "q50",
        "ttc_target_minutes": "55",
        "decision_time_utc": "2026-01-01T00:05:00Z",
        "side": side,
        "candidate_probability": p,
        "side_fair_probability": sfair,
        "yes_bid": bid,
        "yes_ask": ask,
        "quoted_purchase_price": qprice,
        "standard_entry_fee": "0.02",
        "net_edge_per_contract": "0.07",
    }


def test_predeclaration_valid():
    doc = validate_predeclaration()
    assert doc["strategy_v2_predeclaration_fingerprint"] == EXPECTED_PREDECLARATION_FINGERPRINT


def test_midpoint_shrinkage_yes():
    p_adj, q_yes, q_side = adjusted_side_probability(
        side="YES", candidate_probability="0.90",
        yes_bid="0.79", yes_ask="0.81", alpha="0.50"
    )
    assert q_yes == Decimal("0.80")
    assert q_side == Decimal("0.80")
    assert p_adj == Decimal("0.850")


def test_midpoint_shrinkage_no_is_symmetric():
    p_adj, q_yes, q_side = adjusted_side_probability(
        side="NO", candidate_probability="0.10",
        yes_bid="0.19", yes_ask="0.21", alpha="0.50"
    )
    # Candidate NO = .90; market midpoint NO = .80.
    assert q_yes == Decimal("0.20")
    assert q_side == Decimal("0.80")
    assert p_adj == Decimal("0.850")


def test_alpha_one_exactly_restores_candidate_side_probability():
    row = _base()
    adjusted = adjust_base_side_state(row, alpha=Decimal("1.00"))
    assert Decimal(adjusted["adjusted_side_probability"]) == Decimal("0.90")
    # 0.90 fair - 0.81 ask - 0.02 fee = 0.07, exactly Strategy-v1 edge.
    assert Decimal(adjusted["adjusted_net_edge_per_contract"]) == Decimal("0.07")


def test_lower_alpha_reduces_edge_when_shrinking_toward_midpoint():
    row = _base()
    a1 = Decimal(adjust_base_side_state(row, alpha=Decimal("1.00"))["adjusted_net_edge_per_contract"])
    a75 = Decimal(adjust_base_side_state(row, alpha=Decimal("0.75"))["adjusted_net_edge_per_contract"])
    a50 = Decimal(adjust_base_side_state(row, alpha=Decimal("0.50"))["adjusted_net_edge_per_contract"])
    a25 = Decimal(adjust_base_side_state(row, alpha=Decimal("0.25"))["adjusted_net_edge_per_contract"])
    assert a1 > a75 > a50 > a25


def _selection_rows_for_reproduction():
    v1 = []
    v2 = []
    for i in range(2570):
        enter = i < 820
        base = {
            "event_ticker": f"E{i:04d}",
            "event_close_time_utc": f"2026-01-{1 + i//100:02d}T00:00:00Z",
            "stage": "H1_OOF" if i < 1070 else ("H2" if i < 1820 else "H3"),
            "action": "ENTER" if enter else "ABSTAIN",
            "ttc_target_minutes": "55" if enter else "",
            "decision_time_utc": "2026-01-01T00:05:00Z" if enter else "",
            "market_ticker": f"M{i:04d}" if enter else "",
            "structural_role": "q50" if enter else "",
            "side": "YES" if enter else "",
        }
        v1.append(dict(base))
        v2.append(dict(base))
    return v1, v2


def test_alpha1_reproduction_guard_detects_choice_mutation():
    from src.kxbtcd_candidate_e_reliability_shrinkage_entry_v2 import (
        ReliabilityShrinkageError, assert_alpha1_reproduces_v1,
    )
    v1, v2 = _selection_rows_for_reproduction()
    assert_alpha1_reproduces_v1(v1_zero_rows=v1, alpha1_rows=v2)
    v2[0]["market_ticker"] = "MUTATED"
    try:
        assert_alpha1_reproduces_v1(v1_zero_rows=v1, alpha1_rows=v2)
    except ReliabilityShrinkageError as exc:
        assert "chosen state mismatch" in str(exc)
    else:
        raise AssertionError("expected exact-reproduction guard to fail")


def test_first_qualifying_anchor_precedes_later_larger_edge():
    from src.kxbtcd_candidate_e_reliability_shrinkage_entry_v2 import (
        STRATEGY_ID, select_alpha_events,
    )
    rows = []
    for i in range(2570):
        stage = "H1_OOF" if i < 1070 else ("H2" if i < 1820 else "H3")
        event = f"E{i:04d}"
        rows.append({
            "strategy_id": STRATEGY_ID, "alpha": "1", "event_ticker": event,
            "event_close_time_utc": f"2026-02-{1 + i//100:02d}T00:00:00Z",
            "stage": stage, "ttc_target_minutes": "55",
            "decision_time_utc": "2026-02-01T00:05:00Z",
            "market_ticker": f"A{i:04d}", "structural_role": "q50", "side": "YES",
            "candidate_probability": "0.8", "market_midpoint_yes_probability": "0.7",
            "candidate_side_probability": "0.8", "adjusted_side_probability": "0.8",
            "quoted_purchase_price": "0.7", "standard_entry_fee": "0.02",
            "adjusted_net_edge_per_contract": "0.01",
        })
    # For event 0, a later T-50 opportunity has a much larger edge; frozen policy
    # still chooses the first qualifying T-55 anchor.
    rows.append({
        **rows[0],
        "ttc_target_minutes": "50",
        "decision_time_utc": "2026-02-01T00:10:00Z",
        "market_ticker": "LATER-BIGGER",
        "adjusted_net_edge_per_contract": "0.20",
    })
    selected = select_alpha_events(rows, alpha=Decimal("1.00"))
    first = {r["event_ticker"]: r for r in selected}["E0000"]
    assert first["ttc_target_minutes"] == "55"
    assert first["market_ticker"] == "A0000"
