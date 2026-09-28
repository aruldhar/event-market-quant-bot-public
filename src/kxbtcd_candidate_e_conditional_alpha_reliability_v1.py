"""Checkpoint 21N-J-A conditional-alpha reliability v1 mechanics.

Pure, deterministic, network-free implementation of the exact 21N-I predeclaration.
This module contains model/scaler/optimizer/probability/entry-policy primitives only.
It does not discover project data, attach real outcomes, access C1/C2/C3 or reserve
evidence, calculate realized P&L, or expose any execution surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_conditional_alpha_reliability_v1_predeclaration.json")
CANDIDATE_ID = "kxbtcd_candidate_e_conditional_alpha_reliability.v1"
PARENT_CANDIDATE_E_ID = "kxbtcd_btc_distance_offset_logistic.v1"
EXPECTED_PREDECLARATION_FINGERPRINT = "742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3"

RAW_FEATURES = (
    "abs_candidate_market_disagreement",
    "spread_t",
    "abs_r_5m",
    "ttc_minutes",
)
PARAMETER_NAMES = (
    "gamma_0",
    "gamma_disagreement",
    "gamma_spread",
    "gamma_abs_r5m",
    "gamma_ttc",
)
LAMBDA_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)
DEVELOPMENT_STAGES = ("H1_OOF", "H2", "H3")
EXPECTED_STAGE_EVENTS = {"H1_OOF": 1070, "H2": 750, "H3": 750}
EXPECTED_STAGE_ROWS = {"H1_OOF": 31656, "H2": 22354, "H3": 22409}
EXPECTED_TOTAL_EVENTS = 2570
EXPECTED_TOTAL_ROWS = 76419
TTC_LEVELS = (55, 50, 45, 40, 35, 30)
ANCHOR_ORDER = TTC_LEVELS
STRUCTURAL_ROLES = ("q10", "q30", "q50", "q70", "q90")
SIDES = ("YES", "NO")
SIDE_ORDER = {"YES": 0, "NO": 1}

MAX_ITERATIONS = 500
GRADIENT_L2_TOLERANCE = 1e-8
ARMIJO_CONSTANT = 1e-4
INITIAL_STEP_SCALE = 1.0
REJECTED_STEP_MULTIPLIER = 0.5
MINIMUM_STEP_SCALE = 2.0 ** -40
MINIMUM_SCALE_STD = 1e-12
MINIMUM_CURVATURE = 1e-12
FEE_RATE = Decimal("0.07")
ONE_CENT = Decimal("0.01")


class ConditionalAlphaV1Error(RuntimeError):
    """Raised when a frozen 21N-I contract is violated."""


def _error(message: str) -> None:
    raise ConditionalAlphaV1Error(message)


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConditionalAlphaV1Error(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _error(f"{name} must be integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ConditionalAlphaV1Error(f"{name} must be integer") from exc
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = float(result)
    if numeric != float(result):
        _error(f"{name} must be integer-valued")
    return result


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def validate_predeclaration(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema_version") != "kxbtcd_candidate_e_conditional_alpha_reliability_v1_predeclaration.v1":
        _error("conditional-alpha predeclaration schema mismatch")
    if doc.get("candidate_id") != CANDIDATE_ID:
        _error("conditional-alpha candidate identity mismatch")
    supplied = doc.get("predeclaration_fingerprint")
    copy = dict(doc)
    copy.pop("predeclaration_fingerprint", None)
    if canonical_sha256(copy) != supplied or supplied != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("conditional-alpha predeclaration fingerprint mismatch")
    if tuple(item["name"] for item in doc.get("features", ())) != RAW_FEATURES:
        _error("frozen four-feature vector changed")
    fit = doc.get("fit_contract", {})
    if tuple(float(x) for x in fit.get("lambda_grid", ())) != LAMBDA_GRID:
        _error("lambda grid changed")
    if fit.get("regularized_parameters") != "all_5_including_intercept":
        _error("all five gamma parameters must remain L2-regularized")
    optimizer = fit.get("optimizer", {})
    expected = {
        "algorithm": "deterministic_full_batch_BFGS",
        "max_iterations": MAX_ITERATIONS,
        "gradient_l2_tolerance": "1e-8",
        "armijo_constant": "1e-4",
        "initial_step_scale": "1.0",
        "rejected_step_multiplier": "0.5",
        "minimum_step_scale": "2^-40",
        "positive_curvature_requirement": "y^T s > 1e-12",
        "warm_starts": False,
    }
    for key, value in expected.items():
        if optimizer.get(key) != value:
            _error(f"optimizer contract changed at {key}")
    if doc.get("next_checkpoint", {}).get("fit_authorized_by_21N_I") is not False:
        _error("21N-I must not authorize fitting")
    return doc


def stable_sigmoid(value: Any) -> float:
    x = _finite_float(value, "sigmoid input")
    if x >= 0.0:
        z = math.exp(-x)
        result = 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        result = z / (1.0 + z)
    # The predeclaration requires strict interior alpha. Floating-point saturation
    # to exactly 0/1 is therefore a scientific failure rather than a clipping case.
    if not 0.0 < result < 1.0:
        _error("sigmoid saturated to a non-strict alpha; clipping is prohibited")
    return result


def event_equal_weights(rows: Sequence[Mapping[str, Any]]) -> tuple[float, ...]:
    counts: dict[str, int] = {}
    for row in rows:
        event = str(row.get("event_ticker", "")).strip()
        if not event:
            _error("event_equal_weights requires event_ticker")
        counts[event] = counts.get(event, 0) + 1
    if not counts:
        _error("event_equal_weights received no events")
    total_events = len(counts)
    weights = tuple(
        1.0 / (total_events * counts[str(row["event_ticker"]).strip()])
        for row in rows
    )
    if not math.isclose(math.fsum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
        _error("event-equal weights do not sum to one")
    return weights


@dataclass(frozen=True)
class EventEqualScaler:
    means: tuple[float, float, float, float]
    stds: tuple[float, float, float, float]

    def as_dict(self) -> dict[str, dict[str, float]]:
        return {
            name: {"mean": self.means[i], "std": self.stds[i]}
            for i, name in enumerate(RAW_FEATURES)
        }


def _raw_feature_vector(row: Mapping[str, Any], index: Any = "?") -> tuple[float, float, float, float]:
    values = tuple(_finite_float(row.get(name), f"row[{index}].{name}") for name in RAW_FEATURES)
    if values[0] < 0.0 or values[1] < 0.0 or values[2] < 0.0:
        _error(f"row[{index}] absolute/spread features must be nonnegative")
    ttc = values[3]
    if ttc not in tuple(float(x) for x in TTC_LEVELS):
        _error(f"row[{index}] unexpected TTC {ttc}")
    return values  # type: ignore[return-value]


def validate_materialized_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> None:
    if not rows:
        _error("conditional-alpha materialized rows are empty")
    seen_states: set[str] = set()
    stage_events = {stage: set() for stage in DEVELOPMENT_STAGES}
    stage_rows = {stage: 0 for stage in DEVELOPMENT_STAGES}
    event_stage: dict[str, str] = {}
    for index, row in enumerate(rows):
        if row.get("schema_version") != "kxbtcd_candidate_e_conditional_alpha_feature_row.v1":
            _error(f"row[{index}] schema mismatch")
        if row.get("candidate_id") != CANDIDATE_ID:
            _error(f"row[{index}] candidate_id mismatch")
        forbidden = {"outcome", "realized_pnl", "fill_price", "filled_quantity"}
        if forbidden.intersection(row):
            _error(f"row[{index}] contains prohibited outcome/execution field")
        stage = str(row.get("stage", "")).strip()
        if stage not in DEVELOPMENT_STAGES:
            _error(f"row[{index}] unauthorized stage {stage!r}")
        state = str(row.get("state_id", "")).strip()
        event = str(row.get("event_ticker", "")).strip()
        market = str(row.get("market_ticker", "")).strip()
        if not state or not event or not market:
            _error(f"row[{index}] identity fields must be non-empty")
        if state in seen_states:
            _error(f"duplicate conditional-alpha state_id {state}")
        seen_states.add(state)
        prior = event_stage.setdefault(event, stage)
        if prior != stage:
            _error(f"event {event} crosses development stages")
        _raw_feature_vector(row, index)
        p_e = _finite_float(row.get("candidate_probability"), f"row[{index}].candidate_probability")
        q = _finite_float(row.get("market_midpoint_yes_probability"), f"row[{index}].market_midpoint_yes_probability")
        bid = _finite_float(row.get("yes_bid"), f"row[{index}].yes_bid")
        ask = _finite_float(row.get("yes_ask"), f"row[{index}].yes_ask")
        if not (0.0 <= p_e <= 1.0 and 0.0 <= q <= 1.0 and 0.0 <= bid <= ask <= 1.0):
            _error(f"row[{index}] invalid probability/quote bounds")
        if not math.isclose(q, 0.5 * (bid + ask), rel_tol=0.0, abs_tol=1e-12):
            _error(f"row[{index}] midpoint does not match bid/ask")
        if not math.isclose(
            _finite_float(row.get("abs_candidate_market_disagreement"), "disagreement"),
            abs(p_e - q),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            _error(f"row[{index}] disagreement formula mismatch")
        if not math.isclose(
            _finite_float(row.get("spread_t"), "spread_t"),
            ask - bid,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            _error(f"row[{index}] spread formula mismatch")
        stage_rows[stage] += 1
        stage_events[stage].add(event)
    if enforce_frozen_counts:
        if len(rows) != EXPECTED_TOTAL_ROWS:
            _error(f"development row count changed: {len(rows)} != {EXPECTED_TOTAL_ROWS}")
        if len(event_stage) != EXPECTED_TOTAL_EVENTS:
            _error(f"development event count changed: {len(event_stage)} != {EXPECTED_TOTAL_EVENTS}")
        for stage in DEVELOPMENT_STAGES:
            if stage_rows[stage] != EXPECTED_STAGE_ROWS[stage]:
                _error(f"{stage} row count changed")
            if len(stage_events[stage]) != EXPECTED_STAGE_EVENTS[stage]:
                _error(f"{stage} event count changed")


def fit_event_equal_scaler(rows: Sequence[Mapping[str, Any]]) -> EventEqualScaler:
    weights = event_equal_weights(rows)
    vectors = [_raw_feature_vector(row, i) for i, row in enumerate(rows)]
    means: list[float] = []
    stds: list[float] = []
    for j, name in enumerate(RAW_FEATURES):
        mean = math.fsum(w * x[j] for w, x in zip(weights, vectors))
        variance = math.fsum(w * (x[j] - mean) ** 2 for w, x in zip(weights, vectors))
        if variance < 0.0 and abs(variance) <= 1e-15:
            variance = 0.0
        if not math.isfinite(mean) or not math.isfinite(variance) or variance < 0.0:
            _error(f"{name} scaling statistic invalid")
        std = math.sqrt(variance)
        if not math.isfinite(std) or std <= MINIMUM_SCALE_STD:
            _error(f"{name} fit-partition standard deviation <= 1e-12")
        means.append(mean)
        stds.append(std)
    return EventEqualScaler(tuple(means), tuple(stds))  # type: ignore[arg-type]


def design_vector(row: Mapping[str, Any], scaler: EventEqualScaler) -> tuple[float, float, float, float, float]:
    if len(scaler.means) != 4 or len(scaler.stds) != 4:
        _error("conditional-alpha scaler dimension mismatch")
    values = _raw_feature_vector(row, row.get("state_id", "?"))
    z = tuple((x - mean) / std for x, mean, std in zip(values, scaler.means, scaler.stds))
    if any(not math.isfinite(value) for value in z):
        _error("standardized feature became non-finite")
    return (1.0, *z)  # type: ignore[return-value]


def adjusted_yes_probability(
    row: Mapping[str, Any],
    *,
    scaler: EventEqualScaler,
    gamma: Sequence[float],
) -> tuple[float, float]:
    if len(gamma) != 5 or any(not math.isfinite(float(x)) for x in gamma):
        _error("gamma must contain exactly five finite values")
    x = design_vector(row, scaler)
    eta = math.fsum(float(g) * value for g, value in zip(gamma, x))
    alpha = stable_sigmoid(eta)
    q = _finite_float(row.get("market_midpoint_yes_probability"), "market_midpoint_yes_probability")
    p_e = _finite_float(row.get("candidate_probability"), "candidate_probability")
    if not (0.0 <= q <= 1.0 and 0.0 <= p_e <= 1.0):
        _error("q and Candidate-E probability must be in [0,1]")
    p_adj = q + alpha * (p_e - q)
    lower, upper = sorted((q, p_e))
    if not math.isfinite(p_adj) or p_adj < lower - 1e-15 or p_adj > upper + 1e-15:
        _error("adjusted probability left market/Candidate-E endpoints")
    return alpha, p_adj


@dataclass(frozen=True)
class PreparedFitRow:
    state_id: str
    event_ticker: str
    outcome: int
    weight: float
    q_yes: float
    p_e_yes: float
    x: tuple[float, float, float, float, float]


@dataclass(frozen=True)
class ReliabilityFit:
    lambda_value: float
    gamma: tuple[float, float, float, float, float]
    scaler: EventEqualScaler
    iterations: int
    objective: float

    def gamma_by_name(self) -> dict[str, float]:
        return dict(zip(PARAMETER_NAMES, self.gamma))


def prepare_labeled_fit_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    scaler: EventEqualScaler | None = None,
) -> tuple[EventEqualScaler, tuple[PreparedFitRow, ...]]:
    """Prepare already-authorized labeled rows for a later checkpoint.

    This function is implemented now but 21N-J-A contains no real-data caller.
    """
    if not rows:
        _error("fit partition is empty")
    local_scaler = scaler if scaler is not None else fit_event_equal_scaler(rows)
    weights = event_equal_weights(rows)
    prepared: list[PreparedFitRow] = []
    for i, (row, weight) in enumerate(zip(rows, weights)):
        outcome = _int(row.get("outcome"), f"row[{i}].outcome")
        if outcome not in (0, 1):
            _error(f"row[{i}] outcome must be 0 or 1")
        q = _finite_float(row.get("market_midpoint_yes_probability"), f"row[{i}].q")
        p_e = _finite_float(row.get("candidate_probability"), f"row[{i}].pE")
        if not (0.0 <= q <= 1.0 and 0.0 <= p_e <= 1.0):
            _error(f"row[{i}] q/pE outside [0,1]")
        prepared.append(
            PreparedFitRow(
                state_id=str(row.get("state_id", "")),
                event_ticker=str(row.get("event_ticker", "")),
                outcome=outcome,
                weight=weight,
                q_yes=q,
                p_e_yes=p_e,
                x=design_vector(row, local_scaler),
            )
        )
    return local_scaler, tuple(prepared)


def _objective_gradient(
    rows: Sequence[PreparedFitRow],
    gamma: Sequence[float],
    lambda_value: float,
) -> tuple[float, tuple[float, float, float, float, float]]:
    if len(gamma) != 5:
        _error("gamma dimension must be five")
    if float(lambda_value) not in LAMBDA_GRID:
        _error("lambda is outside frozen grid")
    lam = float(lambda_value)
    objective = 0.5 * lam * math.fsum(float(g) * float(g) for g in gamma)
    gradient = [lam * float(g) for g in gamma]
    for row in rows:
        eta = math.fsum(float(g) * x for g, x in zip(gamma, row.x))
        alpha = stable_sigmoid(eta)
        disagreement = row.p_e_yes - row.q_yes
        p = row.q_yes + alpha * disagreement
        if not 0.0 < p < 1.0:
            _error("fit prediction must be strictly inside (0,1); clipping is prohibited")
        y = float(row.outcome)
        loss = -(y * math.log(p) + (1.0 - y) * math.log1p(-p))
        objective += row.weight * loss
        dloss_dp = (p - y) / (p * (1.0 - p))
        dp_deta = disagreement * alpha * (1.0 - alpha)
        scale = row.weight * dloss_dp * dp_deta
        for j, xj in enumerate(row.x):
            gradient[j] += scale * xj
    if not math.isfinite(objective) or any(not math.isfinite(v) for v in gradient):
        _error("conditional-alpha objective/gradient became non-finite")
    return objective, tuple(gradient)  # type: ignore[return-value]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return math.fsum(float(x) * float(y) for x, y in zip(a, b))


def _matvec(matrix: Sequence[Sequence[float]], vector: Sequence[float]) -> list[float]:
    return [math.fsum(float(x) * float(y) for x, y in zip(row, vector)) for row in matrix]


def _identity(n: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _bfgs_inverse_update(
    h: Sequence[Sequence[float]],
    s: Sequence[float],
    y: Sequence[float],
) -> list[list[float]]:
    ys = _dot(y, s)
    if not math.isfinite(ys) or ys <= MINIMUM_CURVATURE:
        _error("BFGS positive-curvature requirement y^T s > 1e-12 failed")
    rho = 1.0 / ys
    n = len(s)
    # H_next = (I-rho*s*y^T) H (I-rho*y*s^T) + rho*s*s^T
    left = [[(1.0 if i == j else 0.0) - rho * s[i] * y[j] for j in range(n)] for i in range(n)]
    right = [[(1.0 if i == j else 0.0) - rho * y[i] * s[j] for j in range(n)] for i in range(n)]
    tmp = [[math.fsum(left[i][k] * h[k][j] for k in range(n)) for j in range(n)] for i in range(n)]
    nxt = [
        [
            math.fsum(tmp[i][k] * right[k][j] for k in range(n)) + rho * s[i] * s[j]
            for j in range(n)
        ]
        for i in range(n)
    ]
    if any(not math.isfinite(v) for row in nxt for v in row):
        _error("BFGS inverse-Hessian update became non-finite")
    return nxt


def fit_conditional_alpha(
    rows: Sequence[Mapping[str, Any]],
    *,
    lambda_value: float,
) -> ReliabilityFit:
    """Fit the frozen family on an already-authorized labeled partition.

    No 21N-J-A command calls this on project data. Unit tests use synthetic rows only.
    """
    if float(lambda_value) not in LAMBDA_GRID:
        _error("lambda is outside frozen grid")
    scaler, prepared = prepare_labeled_fit_rows(rows)
    gamma = [0.0] * 5
    h = _identity(5)
    objective, gradient_tuple = _objective_gradient(prepared, gamma, float(lambda_value))
    gradient = list(gradient_tuple)
    if math.sqrt(_dot(gradient, gradient)) <= GRADIENT_L2_TOLERANCE:
        return ReliabilityFit(float(lambda_value), tuple(gamma), scaler, 0, objective)  # type: ignore[arg-type]

    for iteration in range(1, MAX_ITERATIONS + 1):
        hg = _matvec(h, gradient)
        direction = [-value for value in hg]
        directional_derivative = _dot(gradient, direction)
        if not math.isfinite(directional_derivative) or directional_derivative >= 0.0:
            _error("BFGS direction is not a finite descent direction")

        step = INITIAL_STEP_SCALE
        accepted = False
        candidate_gamma: list[float] = []
        candidate_objective = math.nan
        candidate_gradient: list[float] = []
        while step >= MINIMUM_STEP_SCALE:
            candidate_gamma = [g + step * d for g, d in zip(gamma, direction)]
            try:
                cand_obj, cand_grad_tuple = _objective_gradient(
                    prepared, candidate_gamma, float(lambda_value)
                )
            except ConditionalAlphaV1Error:
                step *= REJECTED_STEP_MULTIPLIER
                continue
            if cand_obj <= objective + ARMIJO_CONSTANT * step * directional_derivative:
                candidate_objective = cand_obj
                candidate_gradient = list(cand_grad_tuple)
                accepted = True
                break
            step *= REJECTED_STEP_MULTIPLIER
        if not accepted:
            _error("Armijo line search failed before minimum step scale")

        s = [new - old for new, old in zip(candidate_gamma, gamma)]
        y = [new - old for new, old in zip(candidate_gradient, gradient)]
        gamma = candidate_gamma
        objective = candidate_objective
        gradient = candidate_gradient

        gradient_norm = math.sqrt(_dot(gradient, gradient))
        if not math.isfinite(gradient_norm):
            _error("gradient norm became non-finite")
        if gradient_norm <= GRADIENT_L2_TOLERANCE:
            return ReliabilityFit(
                float(lambda_value), tuple(gamma), scaler, iteration, objective  # type: ignore[arg-type]
            )
        h = _bfgs_inverse_update(h, s, y)

    _error("conditional-alpha BFGS did not converge within 500 iterations")


def apply_fit_probability(
    row: Mapping[str, Any],
    fit: ReliabilityFit,
) -> tuple[float, float]:
    return adjusted_yes_probability(row, scaler=fit.scaler, gamma=fit.gamma)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ConditionalAlphaV1Error(f"{name} must be decimal-compatible") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def standard_entry_fee(price: Any) -> Decimal:
    p = _decimal(price, "price")
    if p < 0 or p > 1:
        _error("price must be in [0,1]")
    raw = FEE_RATE * p * (Decimal("1") - p)
    return raw.quantize(ONE_CENT, rounding=ROUND_CEILING)


def select_entry_events(
    state_predictions: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Apply the frozen one-contract first-qualifying-anchor quote screen.

    Input is one row per state with `adjusted_yes_probability` plus the materialized
    quote/identity fields. No settlement outcome is read.
    """
    by_event: dict[str, list[Mapping[str, Any]]] = {}
    for i, row in enumerate(state_predictions):
        stage = str(row.get("stage", ""))
        if stage not in DEVELOPMENT_STAGES:
            _error(f"state prediction[{i}] unauthorized stage")
        event = str(row.get("event_ticker", ""))
        if not event:
            _error(f"state prediction[{i}] missing event")
        by_event.setdefault(event, []).append(row)

    result: list[dict[str, Any]] = []
    for event, rows in by_event.items():
        event_close_values = {str(row.get("event_close_time_utc", "")) for row in rows}
        stage_values = {str(row.get("stage", "")) for row in rows}
        if len(event_close_values) != 1 or len(stage_values) != 1:
            _error(f"event {event} inconsistent metadata")
        chosen: tuple[Decimal, str, int, Mapping[str, Any], str, Decimal, Decimal] | None = None
        for ttc in ANCHOR_ORDER:
            candidates: list[tuple[Decimal, str, int, Mapping[str, Any], str, Decimal, Decimal]] = []
            for row in rows:
                if _int(row.get("ttc_target_minutes"), "ttc") != ttc:
                    continue
                p_yes = _decimal(row.get("adjusted_yes_probability"), "adjusted_yes_probability")
                if p_yes < 0 or p_yes > 1:
                    _error("adjusted_yes_probability must be in [0,1]")
                if not str(row.get("market_ticker", "")).strip():
                    _error("state prediction market_ticker must be non-empty")
                bid = _decimal(row.get("yes_bid"), "yes_bid")
                ask = _decimal(row.get("yes_ask"), "yes_ask")
                if not (Decimal("0") <= bid <= ask <= Decimal("1")):
                    _error("invalid quote")
                for side in SIDES:
                    p_side = p_yes if side == "YES" else Decimal("1") - p_yes
                    price = ask if side == "YES" else Decimal("1") - bid
                    fee = standard_entry_fee(price)
                    edge = p_side - price - fee
                    if edge >= 0:
                        candidates.append(
                            (-edge, str(row.get("market_ticker", "")), SIDE_ORDER[side], row, side, price, fee)
                        )
            if candidates:
                candidates.sort(key=lambda item: (item[0], item[1], item[2]))
                chosen = candidates[0]
                break
        base = {
            "event_ticker": event,
            "event_close_time_utc": next(iter(event_close_values)),
            "stage": next(iter(stage_values)),
        }
        if chosen is None:
            result.append({**base, "action": "ABSTAIN"})
        else:
            neg_edge, _, _, row, side, price, fee = chosen
            result.append(
                {
                    **base,
                    "action": "ENTER",
                    "ttc_target_minutes": str(row["ttc_target_minutes"]),
                    "decision_time_utc": str(row["decision_time_utc"]),
                    "market_ticker": str(row["market_ticker"]),
                    "structural_role": str(row["structural_role"]),
                    "side": side,
                    "adjusted_yes_probability": str(row["adjusted_yes_probability"]),
                    "quoted_purchase_price": format(price, "f"),
                    "standard_entry_fee": format(fee, "f"),
                    "adjusted_net_edge_per_contract": format(-neg_edge, "f"),
                }
            )
    result.sort(key=lambda row: (row["event_close_time_utc"], row["event_ticker"]))
    return tuple(result)


__all__ = [
    "ANCHOR_ORDER",
    "CANDIDATE_ID",
    "ConditionalAlphaV1Error",
    "DEVELOPMENT_STAGES",
    "EXPECTED_PREDECLARATION_FINGERPRINT",
    "EventEqualScaler",
    "LAMBDA_GRID",
    "PARAMETER_NAMES",
    "RAW_FEATURES",
    "ReliabilityFit",
    "adjusted_yes_probability",
    "apply_fit_probability",
    "canonical_sha256",
    "event_equal_weights",
    "fit_conditional_alpha",
    "fit_event_equal_scaler",
    "select_entry_events",
    "stable_sigmoid",
    "standard_entry_fee",
    "validate_materialized_rows",
    "validate_predeclaration",
]
