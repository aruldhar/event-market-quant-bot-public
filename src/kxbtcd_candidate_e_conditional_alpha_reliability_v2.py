"""Checkpoint 21N-M-B conditional-alpha reliability v2 Newton mechanics.

This module is an optimizer-only successor to conditional-alpha v1.
It deliberately reuses the frozen v1 feature/scaling/objective primitives and
replaces only BFGS with the exact-Hessian damped-Newton contract frozen in 21N-M-A.

No command in this checkpoint fits real project data, selects lambda, scores H2/H3,
calculates P&L, accesses C1/C2/C3 or reserve evidence, or exposes execution.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    ARMIJO_CONSTANT,
    GRADIENT_L2_TOLERANCE,
    INITIAL_STEP_SCALE,
    LAMBDA_GRID,
    MINIMUM_STEP_SCALE,
    REJECTED_STEP_MULTIPLIER,
    ConditionalAlphaV1Error,
    EventEqualScaler,
    PreparedFitRow,
    _dot,
    _objective_gradient,
    prepare_labeled_fit_rows,
    stable_sigmoid,
)

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_conditional_alpha_reliability_v2_predeclaration.json")
CANDIDATE_ID = "kxbtcd_candidate_e_conditional_alpha_reliability.v2"
EXPECTED_PREDECLARATION_FINGERPRINT = "6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8"
MAX_ITERATIONS = 100
PARAMETER_DIMENSION = 5


class ConditionalAlphaV2Error(RuntimeError):
    """Raised when the frozen 21N-M-A v2 optimizer contract is violated."""


def _error(message: str) -> None:
    raise ConditionalAlphaV2Error(message)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def validate_v2_predeclaration(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema_version") != "kxbtcd_candidate_e_conditional_alpha_reliability_v2_predeclaration.v1":
        _error("conditional-alpha v2 predeclaration schema mismatch")
    if doc.get("candidate_id") != CANDIDATE_ID:
        _error("conditional-alpha v2 candidate identity mismatch")
    supplied = doc.get("predeclaration_fingerprint")
    copy = dict(doc)
    copy.pop("predeclaration_fingerprint", None)
    if canonical_sha256(copy) != supplied or supplied != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("conditional-alpha v2 predeclaration fingerprint mismatch")
    if doc.get("status") != "PREDECLARATION_ONLY_NOT_FIT_AUTHORIZED":
        _error("21N-M-A status changed")
    parent = doc.get("parent_v1", {})
    if parent.get("v1_status") != "PERMANENT_FAIL_OPTIMIZER_CONTRACT":
        _error("parent v1 must remain a permanent optimizer-contract failure")
    if parent.get("rescue_or_reclassification") is not False:
        _error("v2 must not rescue or reclassify v1")
    nxt = doc.get("next_checkpoint", {})
    if nxt.get("real_v2_fit_authorized_by_21N_M_A") is not False:
        _error("21N-M-A must not authorize a real v2 fit")
    if nxt.get("lambda_selection_authorized") is not False:
        _error("21N-M-A must not authorize lambda selection")
    if nxt.get("probability_gate_authorized") is not False:
        _error("21N-M-A must not authorize probability scoring")
    if nxt.get("economic_gate_authorized") is not False:
        _error("21N-M-A must not authorize economic scoring")
    optimizer = doc.get("optimizer_v2", {})
    expected = {
        "algorithm": "deterministic_full_batch_exact_hessian_damped_newton",
        "gradient_l2_tolerance": "1e-8",
        "max_iterations": MAX_ITERATIONS,
        "armijo_constant": "1e-4",
        "initial_step_scale": "1.0",
        "rejected_step_multiplier": "0.5",
        "minimum_step_scale": "2^-40",
        "linear_solver": "deterministic dense Cholesky solve H * delta = gradient",
        "hessian_jitter": False,
        "diagonal_loading": False,
        "pseudoinverse": False,
        "fallback_optimizer": None,
        "warm_starts": False,
    }
    for key, value in expected.items():
        if optimizer.get(key) != value:
            _error(f"conditional-alpha v2 optimizer contract changed at {key}")
    return doc


@dataclass(frozen=True)
class ReliabilityFitV2:
    lambda_value: float
    gamma: tuple[float, float, float, float, float]
    scaler: EventEqualScaler
    iterations: int
    objective: float
    gradient_l2_norm: float
    total_backtracks: int
    minimum_accepted_step: float


def _objective_gradient_hessian(
    rows: Sequence[PreparedFitRow],
    gamma: Sequence[float],
    lambda_value: float,
) -> tuple[
    float,
    tuple[float, float, float, float, float],
    tuple[
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
    ],
]:
    """Return the frozen objective, analytic gradient, and exact 5x5 Hessian."""
    if len(gamma) != PARAMETER_DIMENSION:
        _error("gamma dimension must be five")
    if float(lambda_value) not in LAMBDA_GRID:
        _error("lambda is outside frozen grid")
    lam = float(lambda_value)

    try:
        objective, gradient = _objective_gradient(rows, gamma, lam)
    except ConditionalAlphaV1Error as exc:
        raise ConditionalAlphaV2Error(str(exc)) from exc

    hessian = [[0.0] * PARAMETER_DIMENSION for _ in range(PARAMETER_DIMENSION)]
    for j in range(PARAMETER_DIMENSION):
        hessian[j][j] = lam

    for row in rows:
        eta = math.fsum(float(g) * x for g, x in zip(gamma, row.x))
        try:
            alpha = stable_sigmoid(eta)
        except ConditionalAlphaV1Error as exc:
            raise ConditionalAlphaV2Error(str(exc)) from exc

        disagreement = row.p_e_yes - row.q_yes
        p = row.q_yes + alpha * disagreement
        if not 0.0 < p < 1.0:
            _error("fit prediction must be strictly inside (0,1); clipping is prohibited")

        y = float(row.outcome)
        dloss_dp = (p - y) / (p * (1.0 - p))
        d2loss_dp2 = y / (p * p) + (1.0 - y) / ((1.0 - p) * (1.0 - p))
        dp_deta = disagreement * alpha * (1.0 - alpha)
        d2p_deta2 = dp_deta * (1.0 - 2.0 * alpha)
        curvature = row.weight * (
            d2loss_dp2 * dp_deta * dp_deta
            + dloss_dp * d2p_deta2
        )
        if not math.isfinite(curvature):
            _error("conditional-alpha v2 Hessian curvature became non-finite")

        for j, xj in enumerate(row.x):
            for k in range(j + 1):
                hessian[j][k] += curvature * xj * row.x[k]

    for j in range(PARAMETER_DIMENSION):
        for k in range(j):
            hessian[k][j] = hessian[j][k]

    if any(not math.isfinite(value) for matrix_row in hessian for value in matrix_row):
        _error("conditional-alpha v2 Hessian became non-finite")

    result = tuple(tuple(float(value) for value in matrix_row) for matrix_row in hessian)
    return objective, gradient, result  # type: ignore[return-value]


def dense_cholesky_solve(
    matrix: Sequence[Sequence[float]],
    rhs: Sequence[float],
) -> tuple[float, float, float, float, float]:
    """Solve H*delta=rhs by deterministic dense Cholesky with no jitter/fallback."""
    n = PARAMETER_DIMENSION
    if len(matrix) != n or any(len(row) != n for row in matrix) or len(rhs) != n:
        _error("Newton linear system must be exactly 5x5")
    if any(not math.isfinite(float(value)) for row in matrix for value in row):
        _error("Newton Hessian contains non-finite values")
    if any(not math.isfinite(float(value)) for value in rhs):
        _error("Newton RHS contains non-finite values")
    for i in range(n):
        for j in range(n):
            if matrix[i][j] != matrix[j][i]:
                _error("Newton Hessian must be exactly symmetric")

    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            residual = float(matrix[i][j]) - math.fsum(
                lower[i][k] * lower[j][k] for k in range(j)
            )
            if i == j:
                if not math.isfinite(residual) or residual <= 0.0:
                    _error("Newton Hessian is not positive definite; Cholesky failed")
                lower[i][j] = math.sqrt(residual)
            else:
                pivot = lower[j][j]
                if not math.isfinite(pivot) or pivot <= 0.0:
                    _error("Newton Cholesky pivot is invalid")
                lower[i][j] = residual / pivot

    forward = [0.0] * n
    for i in range(n):
        numerator = float(rhs[i]) - math.fsum(lower[i][k] * forward[k] for k in range(i))
        forward[i] = numerator / lower[i][i]

    solution = [0.0] * n
    for i in range(n - 1, -1, -1):
        numerator = forward[i] - math.fsum(lower[k][i] * solution[k] for k in range(i + 1, n))
        solution[i] = numerator / lower[i][i]

    if any(not math.isfinite(value) for value in solution):
        _error("Newton solution became non-finite")
    return tuple(solution)  # type: ignore[return-value]


def fit_conditional_alpha_v2(
    rows: Sequence[Mapping[str, Any]],
    *,
    lambda_value: float,
) -> ReliabilityFitV2:
    """Fit v2 on an already-authorized labeled partition.

    Checkpoint 21N-M-B provides no real-data caller. Tests use synthetic rows only.
    """
    if float(lambda_value) not in LAMBDA_GRID:
        _error("lambda is outside frozen grid")

    try:
        scaler, prepared = prepare_labeled_fit_rows(rows)
    except ConditionalAlphaV1Error as exc:
        raise ConditionalAlphaV2Error(str(exc)) from exc

    gamma = [0.0] * PARAMETER_DIMENSION
    objective, gradient_tuple, hessian = _objective_gradient_hessian(
        prepared, gamma, float(lambda_value)
    )
    gradient = list(gradient_tuple)
    gradient_norm = math.sqrt(_dot(gradient, gradient))
    if not math.isfinite(gradient_norm):
        _error("gradient norm became non-finite")
    if gradient_norm <= GRADIENT_L2_TOLERANCE:
        return ReliabilityFitV2(
            float(lambda_value),
            tuple(gamma),  # type: ignore[arg-type]
            scaler,
            0,
            objective,
            gradient_norm,
            0,
            INITIAL_STEP_SCALE,
        )

    total_backtracks = 0
    minimum_accepted_step = INITIAL_STEP_SCALE

    for iteration in range(1, MAX_ITERATIONS + 1):
        delta = dense_cholesky_solve(hessian, gradient)
        directional = _dot(gradient, delta)
        if not math.isfinite(directional) or directional <= 0.0:
            _error("Newton direction is not a finite descent direction")

        step = INITIAL_STEP_SCALE
        accepted = False
        candidate_gamma: list[float] = []
        candidate_objective = math.nan
        candidate_gradient: tuple[float, float, float, float, float] | None = None
        candidate_hessian = None
        local_backtracks = 0

        while step >= MINIMUM_STEP_SCALE:
            candidate_gamma = [g - step * d for g, d in zip(gamma, delta)]
            if any(not math.isfinite(value) for value in candidate_gamma):
                _error("Newton proposal became non-finite")
            try:
                cand_obj, cand_grad, cand_hess = _objective_gradient_hessian(
                    prepared, candidate_gamma, float(lambda_value)
                )
            except ConditionalAlphaV2Error:
                step *= REJECTED_STEP_MULTIPLIER
                local_backtracks += 1
                continue
            if cand_obj <= objective - ARMIJO_CONSTANT * step * directional:
                candidate_objective = cand_obj
                candidate_gradient = cand_grad
                candidate_hessian = cand_hess
                accepted = True
                break
            step *= REJECTED_STEP_MULTIPLIER
            local_backtracks += 1

        if not accepted or candidate_gradient is None or candidate_hessian is None:
            _error("Armijo line search failed before minimum step scale")

        gamma = candidate_gamma
        objective = candidate_objective
        gradient = list(candidate_gradient)
        hessian = candidate_hessian
        total_backtracks += local_backtracks
        minimum_accepted_step = min(minimum_accepted_step, step)

        gradient_norm = math.sqrt(_dot(gradient, gradient))
        if not math.isfinite(gradient_norm):
            _error("gradient norm became non-finite")
        if gradient_norm <= GRADIENT_L2_TOLERANCE:
            return ReliabilityFitV2(
                float(lambda_value),
                tuple(gamma),  # type: ignore[arg-type]
                scaler,
                iteration,
                objective,
                gradient_norm,
                total_backtracks,
                minimum_accepted_step,
            )

    _error("conditional-alpha v2 Newton did not converge within 100 iterations")
