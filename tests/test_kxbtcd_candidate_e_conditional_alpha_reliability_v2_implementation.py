import math

import pytest

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    _objective_gradient,
    prepare_labeled_fit_rows,
)
from src.kxbtcd_candidate_e_conditional_alpha_reliability_v2 import (
    GRADIENT_L2_TOLERANCE,
    ConditionalAlphaV2Error,
    _objective_gradient_hessian,
    dense_cholesky_solve,
    fit_conditional_alpha_v2,
)


def synthetic_rows():
    rows = []
    ttcs = [55, 50, 45, 40, 35, 30]
    for event_index in range(24):
        q = 0.20 + 0.025 * (event_index % 16)
        shift = 0.06 + 0.01 * ((event_index % 5) - 2)
        p_e = min(0.94, max(0.06, q + (shift if event_index % 2 == 0 else -shift)))
        outcome = 1 if (0.55 * p_e + 0.45 * q) >= 0.5 else 0
        rows.append(
            {
                "state_id": f"s{event_index}",
                "event_ticker": f"e{event_index}",
                "outcome": outcome,
                "market_midpoint_yes_probability": q,
                "candidate_probability": p_e,
                "abs_candidate_market_disagreement": abs(p_e - q),
                "spread_t": 0.01 + 0.002 * (event_index % 4),
                "abs_r_5m": 2.0 + 0.7 * (event_index % 7),
                "ttc_minutes": float(ttcs[event_index % len(ttcs)]),
            }
        )
    return rows


def test_exact_hessian_matches_central_difference_of_gradient():
    _, prepared = prepare_labeled_fit_rows(synthetic_rows())
    gamma = [0.25, -0.10, 0.15, -0.05, 0.08]
    lam = 0.1
    _, _, hessian = _objective_gradient_hessian(prepared, gamma, lam)
    eps = 1e-5

    max_abs = 0.0
    for column in range(5):
        plus = list(gamma)
        minus = list(gamma)
        plus[column] += eps
        minus[column] -= eps
        _, gp = _objective_gradient(prepared, plus, lam)
        _, gm = _objective_gradient(prepared, minus, lam)
        for row in range(5):
            numerical = (gp[row] - gm[row]) / (2.0 * eps)
            max_abs = max(max_abs, abs(hessian[row][column] - numerical))
    assert max_abs < 1e-7


def test_newton_converges_on_synthetic_rows_to_frozen_tolerance():
    fit = fit_conditional_alpha_v2(synthetic_rows(), lambda_value=0.1)
    assert fit.iterations <= 100
    assert fit.gradient_l2_norm <= GRADIENT_L2_TOLERANCE
    assert math.isfinite(fit.objective)
    assert all(math.isfinite(value) for value in fit.gamma)


def test_cholesky_fails_closed_on_non_positive_definite_hessian():
    matrix = [
        [1.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, -1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0],
    ]
    with pytest.raises(ConditionalAlphaV2Error, match="not positive definite"):
        dense_cholesky_solve(matrix, [1.0] * 5)


def test_cholesky_solves_known_spd_system():
    matrix = [
        [4.0, 1.0, 0.0, 0.0, 0.0],
        [1.0, 3.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 2.0, 0.5, 0.0],
        [0.0, 0.0, 0.5, 2.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 5.0],
    ]
    rhs = [1.0, 2.0, 3.0, 4.0, 5.0]
    x = dense_cholesky_solve(matrix, rhs)
    residual = [
        math.fsum(matrix[i][j] * x[j] for j in range(5)) - rhs[i]
        for i in range(5)
    ]
    assert max(abs(value) for value in residual) < 1e-12
