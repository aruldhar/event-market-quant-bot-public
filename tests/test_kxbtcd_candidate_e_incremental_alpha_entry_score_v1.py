from copy import deepcopy
from decimal import Decimal

import pytest

import src.kxbtcd_candidate_e_incremental_alpha_entry_score_v1 as m


def enter(event, *, edge, alpha, base, plus1, stage="H2", side="YES"):
    return {
        "schema_version": m.PARENT_DECISION_SCHEMA,
        "diagnostic_id": m.PARENT_DIAGNOSTIC_ID,
        "stage": stage,
        "event_ticker": event,
        "event_close_time_utc": f"2026-01-{int(event[-1]) if event[-1].isdigit() else 1:02d}T12:00:00Z",
        "action": "ENTER",
        "ttc_target_minutes": "55",
        "decision_time_utc": "2026-01-01T11:05:00Z",
        "market_ticker": f"M-{event}",
        "structural_role": "q50",
        "side": side,
        "outcome_yes": "1",
        "candidate_probability": "0.70",
        "conditional_alpha": str(alpha),
        "quoted_purchase_price": "0.60",
        "standard_entry_fee": "0.02",
        "candidate_e_net_edge_per_contract": str(edge),
        "alpha_quartile": "Q1",
        "base_realized_net_pnl": str(base),
        "plus_1c_realized_net_pnl": str(plus1),
    }


def population():
    rows = [
        enter("E1", edge=0.01, alpha=0.70, base=-0.20, plus1=-0.21, stage="H2"),
        enter("E2", edge=0.02, alpha=0.80, base=0.10, plus1=0.09, stage="H2"),
        enter("E3", edge=0.03, alpha=0.90, base=0.20, plus1=0.19, stage="H3"),
        enter("E4", edge=0.04, alpha=0.95, base=0.30, plus1=0.29, stage="H3"),
        enter("E5", edge=0.05, alpha=0.72, base=0.15, plus1=0.14, stage="H2"),
        enter("E6", edge=0.06, alpha=0.82, base=0.16, plus1=0.15, stage="H2"),
        enter("E7", edge=0.07, alpha=0.92, base=0.17, plus1=0.16, stage="H3"),
        enter("E8", edge=0.08, alpha=0.97, base=0.18, plus1=0.17, stage="H3"),
    ]
    return rows


def test_beta_zero_is_edge_only_ranking():
    pop = m.extract_population(population(), enforce_frozen_count=False)
    scaler = m.fit_outcome_blind_scaler(pop)
    scored = m.score_population(pop, scaler=scaler, beta=0.0)
    selected = m.select_top(scored, selected_count=2)
    assert [r["event_ticker"] for r in selected] == ["E8", "E7"]


def test_positive_beta_can_change_ranking_via_alpha():
    rows = [
        enter("E1", edge=0.09, alpha=0.55, base=0.0, plus1=0.0),
        enter("E2", edge=0.08, alpha=0.99, base=0.0, plus1=0.0),
        enter("E3", edge=0.01, alpha=0.60, base=0.0, plus1=0.0),
        enter("E4", edge=0.02, alpha=0.65, base=0.0, plus1=0.0),
    ]
    pop = m.extract_population(rows, enforce_frozen_count=False)
    scaler = m.fit_outcome_blind_scaler(pop)
    edge_only = m.select_top(m.score_population(pop, scaler=scaler, beta=0.0), selected_count=1)
    with_alpha = m.select_top(m.score_population(pop, scaler=scaler, beta=2.0), selected_count=1)
    assert edge_only[0]["event_ticker"] == "E1"
    assert with_alpha[0]["event_ticker"] == "E2"


def test_selection_is_outcome_and_pnl_blind():
    pop1 = m.extract_population(population(), enforce_frozen_count=False)
    scaler1 = m.fit_outcome_blind_scaler(pop1)
    s1 = m.select_top(m.score_population(pop1, scaler=scaler1, beta=1.0), selected_count=2)

    flipped = deepcopy(population())
    for row in flipped:
        row["outcome_yes"] = "0"
        row["base_realized_net_pnl"] = str(-Decimal(row["base_realized_net_pnl"]))
        row["plus_1c_realized_net_pnl"] = str(-Decimal(row["plus_1c_realized_net_pnl"]))
    pop2 = m.extract_population(flipped, enforce_frozen_count=False)
    scaler2 = m.fit_outcome_blind_scaler(pop2)
    s2 = m.select_top(m.score_population(pop2, scaler=scaler2, beta=1.0), selected_count=2)

    assert [r["event_ticker"] for r in s1] == [r["event_ticker"] for r in s2]


def test_scaler_uses_population_standard_deviation():
    pop = m.extract_population(population(), enforce_frozen_count=False)
    scaler = m.fit_outcome_blind_scaler(pop)
    edges = [r["candidate_e_net_edge_per_contract"] for r in pop]
    mean = sum(edges) / len(edges)
    expected_sd = (sum((x - mean) ** 2 for x in edges) / len(edges)) ** 0.5
    assert scaler.sd_edge == pytest.approx(expected_sd)


def test_beta_selection_uses_plus_1c_and_smaller_beta_tie():
    def summary(beta, p):
        return {
            "beta": beta,
            "pooled": {"plus_1c_pnl_per_entry": str(p)},
        }
    scores = [
        summary(0.0, 0.01),
        summary(0.25, 0.02),
        summary(0.5, 0.02),
        summary(1.0, 0.00),
        summary(2.0, -0.01),
    ]
    assert m.select_beta(scores) == 0.25


def test_incremental_gate_requires_both_stages_and_stress():
    def s(beta, pooled_base, pooled1, h2, h3):
        return {
            "beta": beta,
            "pooled": {
                "base_pnl_per_entry": str(pooled_base),
                "plus_1c_pnl_per_entry": str(pooled1),
            },
            "H2": {"base_pnl_per_entry": str(h2)},
            "H3": {"base_pnl_per_entry": str(h3)},
        }
    summaries = [
        s(0.0, 0.01, 0.00, 0.01, 0.01),
        s(0.25, 0.03, 0.02, 0.02, 0.02),
        s(0.5, 0.02, 0.01, 0.015, 0.015),
        s(1.0, 0.00, -0.01, 0.00, 0.00),
        s(2.0, -0.01, -0.02, -0.01, -0.01),
    ]
    gate = m.build_incremental_gate(summaries, selected_beta=0.25)
    assert gate["status"] == "INCREMENTAL_ALPHA_SIGNAL"
    assert all(gate["conditions"].values())


def test_closeout_lock_rejects_c_a_receipt(tmp_path):
    p = tmp_path / "receipt.json"
    p.write_text(
        '{"schema":"checkpoint_closeout_receipt.v1","checkpoint_message":"Checkpoint 21N-N-C-A — x","committed_paths":[],"safety":{}}',
        encoding="utf-8",
    )
    with pytest.raises(m.IncrementalAlphaScoreError, match="not Checkpoint 21N-N-C-B"):
        m.validate_c_b_closeout_receipt(p)


def test_frozen_predeclaration_matches():
    doc = m.validate_predeclaration()
    assert doc["predeclaration_fingerprint"] == m.EXPECTED_PREDECLARATION_FINGERPRINT
    assert tuple(doc["beta_tuning"]["grid"]) == m.BETA_GRID
    assert doc["selection_policy"]["selected_count_expected"] == 128
