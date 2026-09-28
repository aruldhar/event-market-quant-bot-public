from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.kxbtcd_candidate_e_reliability_shrinkage_entry_v2_economics import (
    ALL_AUDIT_ALPHAS, ELIGIBLE_ALPHAS, EXPECTED_ENTER_COUNTS,
    EXPECTED_STAGE_ENTER_COUNTS, EXPECTED_TOTAL_EVENTS,
    build_development_economic_evaluation, validate_audit_result_closeout,
    validate_economics_predeclaration, validate_selection_rows,
)


STAGE_RANGES = {
    "H1_OOF": range(0, 1070),
    "H2": range(1070, 1820),
    "H3": range(1820, 2570),
}


def _even_positions(indices, count):
    values = list(indices)
    if count == 0:
        return set()
    if count == 1:
        return {values[len(values)//2]}
    return {
        values[round(i * (len(values) - 1) / (count - 1))]
        for i in range(count)
    }


def _synthetic_selections():
    selected = {}
    for alpha in ALL_AUDIT_ALPHAS:
        chosen = set()
        for stage, indices in STAGE_RANGES.items():
            chosen |= _even_positions(indices, EXPECTED_STAGE_ENTER_COUNTS[alpha][stage])
        assert len(chosen) == EXPECTED_ENTER_COUNTS[alpha]
        selected[alpha] = chosen

    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for alpha in ALL_AUDIT_ALPHAS:
        for i in range(EXPECTED_TOTAL_EVENTS):
            stage = "H1_OOF" if i < 1070 else ("H2" if i < 1820 else "H3")
            enter = i in selected[alpha]
            event = f"E{i:04d}"
            close = (base + timedelta(hours=i)).isoformat().replace("+00:00", "Z")
            rows.append({
                "schema_version": "kxbtcd_candidate_e_reliability_shrinkage_event_selection.v1",
                "strategy_id": "kxbtcd_candidate_e_reliability_shrinkage_entry_v2",
                "alpha": str(alpha),
                "event_ticker": event,
                "event_close_time_utc": close,
                "action": "ENTER" if enter else "ABSTAIN",
                "stage": stage,
                "ttc_target_minutes": "55" if enter else "",
                "decision_time_utc": close if enter else "",
                "market_ticker": f"M{i:04d}_{str(alpha)}" if enter else "",
                "structural_role": "q50" if enter else "",
                "side": "YES" if enter else "",
                "candidate_probability": "0.90" if enter else "",
                "market_midpoint_yes_probability": "0.80" if enter else "",
                "candidate_side_probability": "0.90" if enter else "",
                "adjusted_side_probability": "0.85" if enter else "",
                "quoted_purchase_price": "0.50" if enter else "",
                "standard_entry_fee": "0.02" if enter else "",
                "adjusted_net_edge_per_contract": "0.33" if enter else "",
            })
    return rows


def _outcomes_for(rows, *, winning):
    result = {}
    for row in rows:
        if row["action"] != "ENTER":
            continue
        alpha = Decimal(row["alpha"])
        if alpha not in ELIGIBLE_ALPHAS:
            continue
        result[(row["stage"], row["event_ticker"], row["market_ticker"])] = 1 if winning else 0
    return result


def test_frozen_configs_validate():
    audit = validate_audit_result_closeout()
    econ = validate_economics_predeclaration()
    assert audit["continuation"]["selection_eligible_alphas"] == ["0.50", "0.75"]
    assert econ["alpha_policy"]["outcome_scoring_prohibited_alphas"] == ["0.25", "1.00"]


def test_selection_validator_preserves_exact_frozen_counts():
    rows = _synthetic_selections()
    validated = validate_selection_rows(rows)
    assert len(validated) == 4 * EXPECTED_TOTAL_EVENTS


def test_selection_validator_rejects_accidental_alpha_025_extra_trade():
    rows = _synthetic_selections()
    for row in rows:
        if Decimal(row["alpha"]) == Decimal("0.25") and row["action"] == "ABSTAIN":
            row.update({
                "action": "ENTER", "market_ticker": "EXTRA", "structural_role": "q50",
                "ttc_target_minutes": "55", "side": "YES",
                "quoted_purchase_price": "0.5", "standard_entry_fee": "0.02",
                "adjusted_net_edge_per_contract": "0.1",
            })
            break
    try:
        validate_selection_rows(rows)
    except Exception as exc:
        assert "enter count changed" in str(exc) or "stage entry counts changed" in str(exc)
    else:
        raise AssertionError("expected frozen-count validation failure")


def test_all_winning_synthetic_economics_scores_only_050_and_075_and_selects_075():
    rows = validate_selection_rows(_synthetic_selections())
    evaluation, scenarios, scores = build_development_economic_evaluation(
        rows, _outcomes_for(rows, winning=True)
    )
    assert set(evaluation["alpha_results"]) == {"0.5", "0.75"}
    assert evaluation["scope"]["alpha_0_25_scored"] is False
    assert evaluation["scope"]["alpha_1_scored"] is False
    assert {Decimal(r["alpha"]) for r in scenarios} == {Decimal("0.50"), Decimal("0.75")}
    assert evaluation["alpha_results"]["0.5"]["development_gate_pass"] is True
    assert evaluation["alpha_results"]["0.75"]["development_gate_pass"] is True
    assert evaluation["selection"]["status"] == "PASS_SELECTED_ALPHA"
    assert Decimal(evaluation["selection"]["selected_alpha"]) == Decimal("0.75")
    assert len(scores) == 2


def test_all_losing_synthetic_economics_fails_without_rescue():
    rows = validate_selection_rows(_synthetic_selections())
    evaluation, _, _ = build_development_economic_evaluation(
        rows, _outcomes_for(rows, winning=False)
    )
    assert evaluation["selection"]["status"] == "FAIL_NO_ALPHA"
    assert evaluation["selection"]["selected_alpha"] is None
    assert all(not r["development_gate_pass"] for r in evaluation["alpha_results"].values())
    assert evaluation["safety"]["alpha_0_25_outcome_scored"] is False
    assert evaluation["safety"]["alpha_1_outcome_rescored"] is False
