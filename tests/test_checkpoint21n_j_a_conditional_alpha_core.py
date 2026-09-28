from __future__ import annotations

import math
import random

import pytest

from src import kxbtcd_candidate_e_conditional_alpha_reliability_v1 as m


def make_row(
    *,
    i: int,
    event: str,
    ttc: int,
    q: float,
    p_e: float,
    spread: float,
    abs_r5: float,
    outcome: int | None = None,
) -> dict[str, object]:
    bid = q - spread / 2.0
    ask = q + spread / 2.0
    row: dict[str, object] = {
        "schema_version": "kxbtcd_candidate_e_conditional_alpha_feature_row.v1",
        "candidate_id": m.CANDIDATE_ID,
        "stage": "H1_OOF",
        "state_id": f"state-{i}",
        "event_ticker": event,
        "event_close_time_utc": "2026-01-01T00:00:00Z",
        "market_ticker": f"market-{i}",
        "structural_role": "q50",
        "ttc_target_minutes": str(ttc),
        "decision_time_utc": "2025-12-31T23:05:00Z",
        "candidate_probability": repr(p_e),
        "market_midpoint_yes_probability": repr(q),
        "yes_bid": repr(bid),
        "yes_ask": repr(ask),
        "abs_candidate_market_disagreement": repr(abs(p_e - q)),
        "spread_t": repr(spread),
        "abs_r_5m": repr(abs_r5),
        "ttc_minutes": repr(float(ttc)),
    }
    if outcome is not None:
        row["outcome"] = outcome
    return row


def simple_rows(*, labeled: bool = False) -> list[dict[str, object]]:
    specs = [
        ("e1", 55, .40, .62, .02, 3.0, 1),
        ("e1", 50, .42, .60, .04, 5.0, 1),
        ("e2", 45, .60, .38, .06, 7.0, 0),
        ("e2", 40, .58, .40, .08, 9.0, 0),
        ("e3", 35, .45, .55, .10, 11.0, 1),
        ("e3", 30, .47, .53, .12, 13.0, 0),
    ]
    return [
        make_row(
            i=i,
            event=e,
            ttc=ttc,
            q=q,
            p_e=p,
            spread=s,
            abs_r5=r,
            outcome=y if labeled else None,
        )
        for i, (e, ttc, q, p, s, r, y) in enumerate(specs)
    ]


def test_event_equal_weights_give_each_event_equal_total_mass():
    rows = [
        {"event_ticker": "a"},
        {"event_ticker": "b"},
        {"event_ticker": "b"},
        {"event_ticker": "b"},
    ]
    weights = m.event_equal_weights(rows)
    assert math.fsum(weights) == pytest.approx(1.0, abs=1e-15)
    assert weights[0] == pytest.approx(0.5)
    assert math.fsum(weights[1:]) == pytest.approx(0.5)


def test_zero_gamma_means_alpha_half_and_probability_midway_between_q_and_candidate_e():
    rows = simple_rows()
    scaler = m.fit_event_equal_scaler(rows)
    alpha, p_adj = m.adjusted_yes_probability(rows[0], scaler=scaler, gamma=[0.0] * 5)
    q = float(rows[0]["market_midpoint_yes_probability"])
    p_e = float(rows[0]["candidate_probability"])
    assert alpha == pytest.approx(0.5)
    assert p_adj == pytest.approx(q + 0.5 * (p_e - q))
    assert min(q, p_e) <= p_adj <= max(q, p_e)


def test_scaler_is_fit_partition_event_equal_and_four_dimensional():
    rows = simple_rows()
    scaler = m.fit_event_equal_scaler(rows)
    assert len(scaler.means) == 4
    assert len(scaler.stds) == 4
    assert all(math.isfinite(v) for v in (*scaler.means, *scaler.stds))
    assert all(v > 1e-12 for v in scaler.stds)
    vector = m.design_vector(rows[0], scaler)
    assert len(vector) == 5
    assert vector[0] == 1.0


def random_fit_rows() -> list[dict[str, object]]:
    rng = random.Random(1)
    rows: list[dict[str, object]] = []
    ttc_levels = (55, 50, 45, 40, 35, 30)
    for i in range(40):
        event = f"e{i // 2}"
        ttc = ttc_levels[i % len(ttc_levels)]
        q = rng.uniform(.15, .85)
        p_e = max(.03, min(.97, q + rng.uniform(-.25, .25)))
        spread = rng.choice([.02, .04, .06, .08, .10])
        if q - spread / 2 < 0 or q + spread / 2 > 1:
            spread = .02
        abs_r5 = rng.uniform(1, 20)
        outcome = 1 if rng.random() < (q + p_e) / 2 else 0
        rows.append(
            make_row(
                i=i,
                event=event,
                ttc=ttc,
                q=q,
                p_e=p_e,
                spread=spread,
                abs_r5=abs_r5,
                outcome=outcome,
            )
        )
    return rows


def test_bfgs_fit_is_deterministic_on_synthetic_rows_and_uses_no_warm_start():
    rows = random_fit_rows()
    fit1 = m.fit_conditional_alpha(rows, lambda_value=1.0)
    fit2 = m.fit_conditional_alpha(rows, lambda_value=1.0)
    assert fit1.iterations > 0
    assert fit1.iterations == fit2.iterations
    assert fit1.gamma == pytest.approx(fit2.gamma, rel=0.0, abs=1e-14)
    assert fit1.objective == pytest.approx(fit2.objective, rel=0.0, abs=1e-14)
    assert all(math.isfinite(v) for v in fit1.gamma)


def test_analytic_objective_gradient_matches_finite_difference_on_synthetic_rows():
    rows = random_fit_rows()
    scaler, prepared = m.prepare_labeled_fit_rows(rows)
    gamma = [0.03, -0.04, 0.02, 0.01, -0.025]
    _, analytic = m._objective_gradient(prepared, gamma, 0.1)
    epsilon = 1e-6
    for j in range(5):
        plus = list(gamma)
        minus = list(gamma)
        plus[j] += epsilon
        minus[j] -= epsilon
        f_plus, _ = m._objective_gradient(prepared, plus, 0.1)
        f_minus, _ = m._objective_gradient(prepared, minus, 0.1)
        numeric = (f_plus - f_minus) / (2 * epsilon)
        assert analytic[j] == pytest.approx(numeric, rel=2e-5, abs=2e-7)
    assert len(scaler.means) == 4


def test_bfgs_curvature_failure_is_fail_closed_not_skipped_or_reset():
    with pytest.raises(m.ConditionalAlphaV1Error, match="positive-curvature"):
        m._bfgs_inverse_update(m._identity(5), [1e-8] * 5, [1e-8] * 5)


def test_entry_selection_uses_first_qualifying_anchor_and_no_outcome():
    rows = [
        {
            "stage": "H2",
            "event_ticker": "E",
            "event_close_time_utc": "2026-01-01T01:00:00Z",
            "market_ticker": "M55",
            "structural_role": "q50",
            "ttc_target_minutes": "55",
            "decision_time_utc": "2026-01-01T00:05:00Z",
            "yes_bid": "0.49",
            "yes_ask": "0.51",
            "adjusted_yes_probability": "0.50",
        },
        {
            "stage": "H2",
            "event_ticker": "E",
            "event_close_time_utc": "2026-01-01T01:00:00Z",
            "market_ticker": "M50",
            "structural_role": "q50",
            "ttc_target_minutes": "50",
            "decision_time_utc": "2026-01-01T00:10:00Z",
            "yes_bid": "0.50",
            "yes_ask": "0.60",
            "adjusted_yes_probability": "0.80",
        },
    ]
    selected = m.select_entry_events(rows)
    assert len(selected) == 1
    assert selected[0]["action"] == "ENTER"
    assert selected[0]["ttc_target_minutes"] == "50"
    assert selected[0]["side"] == "YES"
    assert "outcome" not in selected[0]
