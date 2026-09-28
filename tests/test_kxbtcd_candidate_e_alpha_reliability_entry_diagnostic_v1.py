from copy import deepcopy
from decimal import Decimal

import pytest

import src.kxbtcd_candidate_e_alpha_reliability_entry_diagnostic_v1 as diag


def row(
    *,
    state,
    event,
    stage="H2",
    ttc=55,
    market="M1",
    role="q50",
    p_e=0.70,
    alpha=0.4,
    bid=0.58,
    ask=0.60,
    outcome=1,
):
    return {
        "schema_version": diag.PARENT_PREDICTION_SCHEMA,
        "candidate_id": diag.PARENT_CANDIDATE_ID,
        "selected_lambda": "0.001",
        "fold": "1" if stage == "H2" else "2",
        "stage": stage,
        "state_id": state,
        "event_ticker": event,
        "event_close_time_utc": f"2026-01-{int(event[-1]) if event[-1].isdigit() else 1:02d}T12:00:00Z",
        "market_ticker": market,
        "structural_role": role,
        "ttc_target_minutes": str(ttc),
        "decision_time_utc": "2026-01-01T11:00:00Z",
        "outcome": str(outcome),
        "candidate_probability": str(p_e),
        "market_midpoint_yes_probability": str((bid + ask) / 2),
        "global_alpha_0_50_probability": "0.65",
        "conditional_alpha": str(alpha),
        "adjusted_yes_probability": "0.66",
        "yes_bid": str(bid),
        "yes_ask": str(ask),
    }


def test_candidate_e_selection_ignores_alpha_and_adjusted_probability():
    rows = [
        row(state="s1", event="E1", ttc=55, market="A", p_e=0.70, alpha=0.05, bid=0.58, ask=0.60),
        row(state="s2", event="E1", ttc=55, market="B", p_e=0.70, alpha=0.99, bid=0.54, ask=0.56),
    ]
    # B has the larger Candidate-E YES edge and must be chosen regardless of alpha.
    chosen = diag.select_candidate_e_entries(rows, enforce_frozen_counts=False)
    assert len(chosen) == 1
    assert chosen[0]["market_ticker"] == "B"
    assert chosen[0]["conditional_alpha"] == "0.99"


def test_first_qualifying_anchor_precedes_later_larger_edge():
    rows = [
        row(state="s1", event="E1", ttc=55, market="EARLY", p_e=0.70, bid=0.63, ask=0.64),
        row(state="s2", event="E1", ttc=50, market="LATE", p_e=0.90, bid=0.50, ask=0.51),
    ]
    chosen = diag.select_candidate_e_entries(rows, enforce_frozen_counts=False)
    assert chosen[0]["market_ticker"] == "EARLY"
    assert chosen[0]["ttc_target_minutes"] == "55"


def test_quartile_assignment_is_outcome_blind_and_equal_count():
    rows = [
        row(state=f"s{i}", event=f"E{i}", alpha=0.1 * i, outcome=i % 2)
        for i in range(1, 9)
    ]
    d1 = diag.select_candidate_e_entries(rows, enforce_frozen_counts=False)
    q1 = diag.assign_alpha_quartiles(d1)

    flipped = deepcopy(rows)
    for r in flipped:
        r["outcome"] = "0" if r["outcome"] == "1" else "1"
    d2 = diag.select_candidate_e_entries(flipped, enforce_frozen_counts=False)
    q2 = diag.assign_alpha_quartiles(d2)

    a1 = {r["event_ticker"]: r["alpha_quartile"] for r in q1}
    a2 = {r["event_ticker"]: r["alpha_quartile"] for r in q2}
    assert a1 == a2
    assert list(a1.values()).count("Q1") == 2
    assert list(a1.values()).count("Q4") == 2


def test_quartile_remainder_goes_to_earlier_groups():
    rows = [
        row(state=f"s{i}", event=f"E{i}", alpha=0.1 * i)
        for i in range(1, 7)
    ]
    decisions = diag.assign_alpha_quartiles(
        diag.select_candidate_e_entries(rows, enforce_frozen_counts=False)
    )
    counts = {q: 0 for q in diag.QUARTILES}
    for r in decisions:
        counts[r["alpha_quartile"]] += 1
    assert counts == {"Q1": 2, "Q2": 2, "Q3": 1, "Q4": 1}


def test_realized_pnl_recomputes_fee_after_plus_one_cent_stress():
    decision = {
        "action": "ENTER",
        "event_ticker": "E1",
        "quoted_purchase_price": "0.60",
        "outcome_yes": "1",
        "side": "YES",
    }
    base = diag.realized_pnl(decision, Decimal("0.00"))
    stressed = diag.realized_pnl(decision, Decimal("0.01"))
    assert base == Decimal("1") - Decimal("0.60") - diag.standard_entry_fee(Decimal("0.60"))
    assert stressed == Decimal("1") - Decimal("0.61") - diag.standard_entry_fee(Decimal("0.61"))


def test_spearman_known_orderings_and_ties():
    assert diag.spearman_rank_correlation([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert diag.spearman_rank_correlation([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert diag.spearman_rank_correlation([1, 1, 1], [1, 2, 3]) is None


def test_closeout_gate_rejects_pre_n_b_receipt(tmp_path):
    p = tmp_path / "receipt.json"
    p.write_text(
        '{"schema":"checkpoint_closeout_receipt.v1","checkpoint_message":"Checkpoint 21N-N-A — x","committed_paths":[],"safety":{}}',
        encoding="utf-8",
    )
    with pytest.raises(diag.AlphaEntryDiagnosticError, match="not Checkpoint 21N-N-B"):
        diag.validate_n_b_closeout_receipt(p)


def test_predeclaration_validator_matches_frozen_contract():
    doc = diag.validate_predeclaration()
    assert doc["predeclaration_fingerprint"] == diag.EXPECTED_PREDECLARATION_FINGERPRINT
    assert doc["valuation_policy"]["conditional_adjusted_probability_used_for_valuation"] is False
