from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_quoted_entry_hold_v1_economics import (
    CANDIDATE_ID,
    CONFIG_PATH,
    EXPECTED_AUDIT_FINGERPRINT,
    DevelopmentEconomicsError,
    build_development_economic_evaluation,
    build_outcome_map,
    realized_side_payout,
    realized_trade_scenario,
    standard_entry_fee,
    validate_economics_predeclaration,
    validate_selection_rows,
)


def _selection(threshold: str, i: int, *, action: str = "ENTER", price: str = "0.4") -> dict[str, str]:
    stage = "H1_OOF" if i < 1070 else ("H2" if i < 1820 else "H3")
    event = f"E{i:04d}"
    market = f"M{i:04d}"
    return {
        "schema_version": "kxbtcd_candidate_e_quoted_entry_threshold_event_selection.v1",
        "strategy_id": "kxbtcd_candidate_e_quoted_entry_hold_v1",
        "threshold_dollars": threshold,
        "event_ticker": event,
        "event_close_time_utc": f"2026-01-{1 + (i // 24) % 28:02d}T{i % 24:02d}:00:00Z",
        "action": action,
        "stage": stage,
        "ttc_target_minutes": "55" if action == "ENTER" else "",
        "decision_time_utc": "2026-01-01T00:05:00Z" if action == "ENTER" else "",
        "market_ticker": market if action == "ENTER" else "",
        "structural_role": "q50" if action == "ENTER" else "",
        "side": "YES" if action == "ENTER" else "",
        "candidate_probability": "0.8" if action == "ENTER" else "",
        "quoted_purchase_price": price if action == "ENTER" else "",
        "standard_entry_fee": "0.02" if action == "ENTER" else "",
        "net_edge_per_contract": "0.38" if action == "ENTER" else "",
    }


def _full_synthetic(win: bool = True):
    thresholds = ("0", "0.01", "0.02", "0.03", "0.05")
    rows = []
    outcomes = {}
    for threshold in thresholds:
        for i in range(2570):
            row = _selection(threshold, i)
            rows.append(row)
            outcome = 1 if win else 0
            outcomes[(row["stage"], row["event_ticker"], row["market_ticker"])] = outcome
    return rows, outcomes


def test_predeclaration_validates_and_binds_audit() -> None:
    document = validate_economics_predeclaration(CONFIG_PATH)
    assert document["opportunity_audit_binding"]["audit_fingerprint"] == EXPECTED_AUDIT_FINGERPRINT
    assert document["strategy_policies"]["diagnostic_only_thresholds_dollars"] == [0.05]


def test_standard_fee_uses_ceiling_to_cent() -> None:
    assert standard_entry_fee(Decimal("0.50")) == Decimal("0.02")
    assert standard_entry_fee(Decimal("0.10")) == Decimal("0.01")


def test_realized_payout_and_base_pnl() -> None:
    assert realized_side_payout("YES", 1) == Decimal("1")
    assert realized_side_payout("NO", 1) == Decimal("0")
    result = realized_trade_scenario(
        side="YES", outcome=1, quoted_purchase_price="0.40", stress=Decimal("0")
    )
    assert result["valid"] is True
    assert result["fee"] == Decimal("0.02")
    assert result["capital_deployed"] == Decimal("0.42")
    assert result["pnl"] == Decimal("0.58")


def test_stress_above_one_fails_closed_without_capping() -> None:
    result = realized_trade_scenario(
        side="YES", outcome=1, quoted_purchase_price="0.995", stress=Decimal("0.01")
    )
    assert result["valid"] is False
    assert result["purchase_price"] is None
    assert result["pnl"] is None


def test_selection_validation_rejects_duplicate_threshold_event() -> None:
    row = _selection("0.01", 0)
    with pytest.raises(DevelopmentEconomicsError):
        validate_selection_rows([row, dict(row)], enforce_frozen_counts=False)


def test_outcome_projection_requires_consistency_for_same_market() -> None:
    row1 = {
        "schema_version": "kxbtcd_candidate_e_h1_oof_prediction.v1",
        "candidate_id": CANDIDATE_ID,
        "state_id": "s1",
        "event_ticker": "E",
        "market_ticker": "M",
        "outcome": "1",
    }
    row2 = dict(row1, state_id="s2", outcome="0")
    with pytest.raises(DevelopmentEconomicsError):
        build_outcome_map(
            {"H1_OOF": [row1, row2], "H2": [], "H3": []},
            enforce_frozen_counts=False,
        )


def test_full_development_evaluation_selects_higher_threshold_on_exact_metric_tie() -> None:
    rows, outcomes = _full_synthetic(win=True)
    evaluation, scenarios, scores = build_development_economic_evaluation(rows, outcomes)
    assert evaluation["selection"]["status"] == "PASS_THRESHOLD_SELECTED"
    assert evaluation["selection"]["selected_threshold"] == "0.03"
    assert evaluation["threshold_results"]["0.05"]["selection_eligible"] is False
    assert evaluation["threshold_results"]["0.05"]["development_gate_pass"] is True
    assert len(scenarios) == 2570 * 5 * 4
    assert len(scores) == 5


def test_full_development_evaluation_fails_when_all_entries_lose() -> None:
    rows, outcomes = _full_synthetic(win=False)
    evaluation, _, _ = build_development_economic_evaluation(rows, outcomes)
    assert evaluation["selection"]["status"] == "FAIL_NO_THRESHOLD"
    assert evaluation["selection"]["selected_threshold"] == ""


def test_module_contains_no_network_or_order_surface() -> None:
    paths = (
        Path("src/kxbtcd_candidate_e_quoted_entry_hold_v1_economics.py"),
        Path("evaluate_kxbtcd_candidate_e_quoted_entry_hold_v1_development_economics.py"),
    )
    forbidden = (
        "import requests",
        "import websockets",
        "create_order",
        "cancel_order",
        "/portfolio/",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text
