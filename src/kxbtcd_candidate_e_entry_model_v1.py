"""Frozen Checkpoint-21L Model-2 mechanics for Candidate-E Entry Model v1.

This module is deliberately network-free and execution-free.  It implements the
frozen residual-logistic model family, event-equal preprocessing/metrics,
deterministic damped-Newton optimization, and rolling-origin development tuning.

It does not discover inputs, open C3, access the protected historical reserve,
calculate Strategy-v1 P&L, or place/cancel any order.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from statistics import median
from typing import Any, Mapping, Sequence

MODEL_ID = "kxbtcd_candidate_e_entry_residual_logistic.v1"
CANDIDATE_E_ID = "kxbtcd_btc_distance_offset_logistic.v1"
ROW_SCHEMA_VERSION = "kxbtcd_candidate_e_entry_model_v1_feature_row.v1"
EVENT_MAP_SCHEMA_VERSION = "kxbtcd_candidate_e_entry_model_v1_development_event.v1"

CONTINUOUS_FEATURES = (
    "r_5m",
    "spread_t",
    "mid_move_1m",
    "spread_change_1m",
    "bid_range_1m",
    "ask_range_1m",
    "log1p_volume_1m",
    "log1p_open_interest",
    "log1p_trade_count_5m",
    "log1p_contracts_5m",
    "taker_imbalance_5m",
)
TTC_LEVELS = (55, 50, 45, 40, 35, 30)
TTC_REFERENCE = 55
TTC_INDICATORS = (50, 45, 40, 35, 30)
STRUCTURAL_ROLES = ("q10", "q30", "q50", "q70", "q90")
STRUCTURAL_ROLE_REFERENCE = "q50"
STRUCTURAL_ROLE_INDICATORS = ("q10", "q30", "q70", "q90")
PARAMETER_NAMES = (
    "intercept",
    *CONTINUOUS_FEATURES,
    *(f"ttc_{value}" for value in TTC_INDICATORS),
    *(f"role_{value}" for value in STRUCTURAL_ROLE_INDICATORS),
)
if len(PARAMETER_NAMES) != 21:  # frozen scientific contract guard
    raise RuntimeError("Model-2 v1 must have exactly 21 learned coefficients")

LAMBDA_GRID = (0.001, 0.01, 0.1, 1.0, 10.0)
DEVELOPMENT_STAGES = ("H1_OOF", "H2", "H3")
EXPECTED_DEVELOPMENT_EVENT_COUNTS = {"H1_OOF": 1070, "H2": 750, "H3": 750}
EXPECTED_DEVELOPMENT_ROW_COUNTS = {"H1_OOF": 31656, "H2": 22354, "H3": 22409}
EXPECTED_DEVELOPMENT_EVENTS = 2570
EXPECTED_DEVELOPMENT_ROWS = 76419
EXPECTED_TUNING_SCORE_EVENTS = 1500

MAX_ITERATIONS = 100
GRADIENT_L2_TOLERANCE = 1e-8
ARMIJO_CONSTANT = 1e-4
INITIAL_STEP_SCALE = 1.0
REJECTED_STEP_MULTIPLIER = 0.5
MINIMUM_STEP_SCALE = 2.0 ** -40
MINIMUM_SCALE_STD = 1e-12


class CandidateEEntryModelV1Error(RuntimeError):
    """Raised when a frozen Model-2 v1 invariant is violated."""


def _error(message: str) -> None:
    raise CandidateEEntryModelV1Error(message)


def _finite_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise CandidateEEntryModelV1Error(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _error(f"{name} must be integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CandidateEEntryModelV1Error(f"{name} must be integer") from exc
    if str(value).strip() not in {str(result), f"{result}.0"} and not isinstance(value, int):
        # CSV text such as "55" is normal; reject ambiguous truncation like 55.2.
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


def canonical_rows_fingerprint(rows: Sequence[Mapping[str, Any]], *, key: str = "state_id") -> str:
    """Fingerprint flat CSV-like rows independent of Python scalar types.

    Materialization creates numeric Python values, while independent validation
    reads the persisted CSV back as text.  Normalizing every scalar to the exact
    text form used by ``csv.DictWriter`` makes the scientific fingerprint stable
    across that required write/read boundary instead of accidentally binding it
    to an in-memory type representation.
    """
    normalized = [
        {str(field): ("" if value is None else str(value)) for field, value in row.items()}
        for row in rows
    ]
    if key:
        try:
            normalized.sort(key=lambda row: row[key])
        except KeyError as exc:
            raise CandidateEEntryModelV1Error(f"fingerprint row missing key {key!r}") from exc
    return canonical_sha256(normalized)


def stable_sigmoid(value: float) -> float:
    if not math.isfinite(value):
        _error("sigmoid input must be finite")
    if value >= 0.0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def candidate_offset(probability: Any) -> float:
    p = _finite_float(probability, "candidate_probability")
    if not 0.0 < p < 1.0:
        _error("candidate_probability must satisfy 0 < p < 1; clipping is prohibited")
    value = math.log(p) - math.log1p(-p)
    if not math.isfinite(value):
        _error("Candidate-E logit offset became non-finite")
    return value


def binary_log_loss_from_logit(logit: float, outcome: int) -> float:
    if outcome not in (0, 1):
        _error("outcome must be 0 or 1")
    if not math.isfinite(logit):
        _error("prediction logit must be finite")
    # softplus(logit) - y*logit, written branch-stably.
    if logit >= 0.0:
        softplus = logit + math.log1p(math.exp(-logit))
    else:
        softplus = math.log1p(math.exp(logit))
    result = softplus - float(outcome) * logit
    if not math.isfinite(result):
        _error("binary log loss became non-finite")
    return result


def binary_log_loss(probability: Any, outcome: int) -> float:
    return binary_log_loss_from_logit(candidate_offset(probability), outcome)


def brier_score(probability: Any, outcome: int) -> float:
    p = _finite_float(probability, "probability")
    if not 0.0 <= p <= 1.0:
        _error("probability must be inside [0,1]")
    if outcome not in (0, 1):
        _error("outcome must be 0 or 1")
    return (p - float(outcome)) ** 2


@dataclass(frozen=True)
class EventEqualScaler:
    means: tuple[float, ...]
    stds: tuple[float, ...]

    def as_dict(self) -> dict[str, dict[str, float]]:
        return {
            name: {"mean": self.means[index], "std": self.stds[index]}
            for index, name in enumerate(CONTINUOUS_FEATURES)
        }


@dataclass(frozen=True)
class PreparedFitRow:
    state_id: str
    event_ticker: str
    stage: str
    outcome: int
    candidate_probability: float
    offset: float
    weight: float
    x: tuple[float, ...]


@dataclass(frozen=True)
class ResidualFit:
    lambda_value: float
    coefficients: tuple[float, ...]
    scaler: EventEqualScaler
    iterations: int
    objective: float

    def coefficients_by_name(self) -> dict[str, float]:
        return dict(zip(PARAMETER_NAMES, self.coefficients))


@dataclass(frozen=True)
class DevelopmentEvaluation:
    selected_lambda: float
    lambda_scores: tuple[dict[str, Any], ...]
    fold_fits: tuple[dict[str, Any], ...]
    full_development_fit: ResidualFit


def _validate_feature_categories(row: Mapping[str, Any], index: int | str) -> tuple[int, str]:
    ttc = _int(row.get("ttc_target_minutes"), f"row[{index}].ttc_target_minutes")
    role = str(row.get("structural_role", ""))
    if ttc not in TTC_LEVELS:
        _error(f"row[{index}] unexpected ttc_target_minutes={ttc}")
    if role not in STRUCTURAL_ROLES:
        _error(f"row[{index}] unexpected structural_role={role!r}")
    return ttc, role


def _continuous_vector(row: Mapping[str, Any], index: int | str) -> tuple[float, ...]:
    return tuple(
        _finite_float(row.get(name), f"row[{index}].{name}")
        for name in CONTINUOUS_FEATURES
    )


def validate_feature_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    allowed_stages: Sequence[str] = DEVELOPMENT_STAGES,
    enforce_frozen_counts: bool = True,
) -> None:
    if not rows:
        _error("Model-2 feature rows are empty")
    allowed = set(allowed_stages)
    seen_states: set[str] = set()
    event_stage: dict[str, str] = {}
    event_close: dict[str, str] = {}
    stage_rows: dict[str, int] = {stage: 0 for stage in allowed_stages}
    stage_events: dict[str, set[str]] = {stage: set() for stage in allowed_stages}
    for index, row in enumerate(rows):
        if row.get("schema_version") != ROW_SCHEMA_VERSION:
            _error(f"row[{index}] feature schema mismatch")
        if row.get("model_id") != MODEL_ID:
            _error(f"row[{index}] model_id mismatch")
        if "outcome" in row:
            _error("outcome field is prohibited in outcome-blind feature materialization")
        stage = str(row.get("stage", ""))
        if stage not in allowed:
            _error(f"row[{index}] stage {stage!r} is not authorized for this materialization")
        state_id = str(row.get("state_id", ""))
        event = str(row.get("event_ticker", ""))
        market = str(row.get("market_ticker", ""))
        close = str(row.get("event_close_time_utc", ""))
        if not state_id or not event or not market or not close:
            _error(f"row[{index}] identity fields must be non-empty")
        if state_id in seen_states:
            _error(f"duplicate Model-2 state_id {state_id}")
        seen_states.add(state_id)
        prior = event_stage.setdefault(event, stage)
        if prior != stage:
            _error(f"event {event} crosses development stages")
        prior_close = event_close.setdefault(event, close)
        if prior_close != close:
            _error(f"event {event} has inconsistent close timestamp")
        _validate_feature_categories(row, index)
        _continuous_vector(row, index)
        candidate_offset(row.get("candidate_probability"))
        stage_rows[stage] += 1
        stage_events[stage].add(event)
    if enforce_frozen_counts:
        if len(rows) != EXPECTED_DEVELOPMENT_ROWS:
            _error(f"development row count changed: {len(rows)} != {EXPECTED_DEVELOPMENT_ROWS}")
        if len(event_stage) != EXPECTED_DEVELOPMENT_EVENTS:
            _error(f"development event count changed: {len(event_stage)} != {EXPECTED_DEVELOPMENT_EVENTS}")
        for stage in DEVELOPMENT_STAGES:
            if stage_rows[stage] != EXPECTED_DEVELOPMENT_ROW_COUNTS[stage]:
                _error(
                    f"{stage} row count changed: {stage_rows[stage]} != "
                    f"{EXPECTED_DEVELOPMENT_ROW_COUNTS[stage]}"
                )
            if len(stage_events[stage]) != EXPECTED_DEVELOPMENT_EVENT_COUNTS[stage]:
                _error(
                    f"{stage} event count changed: {len(stage_events[stage])} != "
                    f"{EXPECTED_DEVELOPMENT_EVENT_COUNTS[stage]}"
                )


def build_development_event_map(
    rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], ...]:
    validate_feature_rows(rows, enforce_frozen_counts=enforce_frozen_counts)
    by_event: dict[str, tuple[str, str]] = {}
    row_count: dict[str, int] = {}
    for row in rows:
        event = str(row["event_ticker"])
        value = (str(row["stage"]), str(row["event_close_time_utc"]))
        if event in by_event and by_event[event] != value:
            _error(f"event {event} has inconsistent stage/close time")
        by_event[event] = value
        row_count[event] = row_count.get(event, 0) + 1

    result: list[dict[str, Any]] = []
    stage_order = {stage: index for index, stage in enumerate(DEVELOPMENT_STAGES)}
    ordered = sorted(
        by_event.items(),
        key=lambda item: (stage_order[item[1][0]], item[1][1], item[0]),
    )
    stage_index = {stage: 0 for stage in DEVELOPMENT_STAGES}
    for event, (stage, close) in ordered:
        result.append(
            {
                "schema_version": EVENT_MAP_SCHEMA_VERSION,
                "model_id": MODEL_ID,
                "stage": stage,
                "stage_event_index_zero_based": stage_index[stage],
                "event_ticker": event,
                "event_close_time_utc": close,
                "row_count": row_count[event],
            }
        )
        stage_index[stage] += 1

    # Strict stage chronology: every event in an earlier development stage must
    # close before every event in the next stage.
    for left, right in zip(DEVELOPMENT_STAGES, DEVELOPMENT_STAGES[1:]):
        left_close = [row["event_close_time_utc"] for row in result if row["stage"] == left]
        right_close = [row["event_close_time_utc"] for row in result if row["stage"] == right]
        if not left_close or not right_close:
            _error(f"missing events for chronology check {left}->{right}")
        if max(left_close) >= min(right_close):
            _error(f"development stage chronology is not strict at {left}->{right}")
    return tuple(result)


def event_equal_weights(rows: Sequence[Mapping[str, Any]]) -> tuple[float, ...]:
    counts: dict[str, int] = {}
    for row in rows:
        event = str(row.get("event_ticker", ""))
        if not event:
            _error("event_equal_weights requires event_ticker")
        counts[event] = counts.get(event, 0) + 1
    if not counts:
        _error("event_equal_weights received no events")
    event_count = len(counts)
    weights = tuple(1.0 / (event_count * counts[str(row["event_ticker"])]) for row in rows)
    if not math.isclose(math.fsum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
        _error("event-equal weights do not sum to 1")
    return weights


def fit_event_equal_scaler(rows: Sequence[Mapping[str, Any]]) -> EventEqualScaler:
    weights = event_equal_weights(rows)
    vectors = [_continuous_vector(row, index) for index, row in enumerate(rows)]
    means: list[float] = []
    stds: list[float] = []
    for feature_index, name in enumerate(CONTINUOUS_FEATURES):
        mean_value = sum(w * vector[feature_index] for w, vector in zip(weights, vectors))
        variance = sum(
            w * (vector[feature_index] - mean_value) ** 2
            for w, vector in zip(weights, vectors)
        )
        if not math.isfinite(mean_value) or not math.isfinite(variance):
            _error(f"{name} scaling statistic became non-finite")
        if variance < 0.0 and abs(variance) <= 1e-15:
            variance = 0.0
        if variance < 0.0:
            _error(f"{name} weighted variance became negative")
        std = math.sqrt(variance)
        if not math.isfinite(std) or std <= MINIMUM_SCALE_STD:
            _error(f"{name} fit-partition standard deviation <= 1e-12")
        means.append(mean_value)
        stds.append(std)
    return EventEqualScaler(tuple(means), tuple(stds))


def design_vector(row: Mapping[str, Any], scaler: EventEqualScaler) -> tuple[float, ...]:
    if len(scaler.means) != len(CONTINUOUS_FEATURES) or len(scaler.stds) != len(CONTINUOUS_FEATURES):
        _error("scaler dimension mismatch")
    values = _continuous_vector(row, row.get("state_id", "?"))
    z = tuple((value - mean) / std for value, mean, std in zip(values, scaler.means, scaler.stds))
    if any(not math.isfinite(value) for value in z):
        _error("standardized continuous feature became non-finite")
    ttc, role = _validate_feature_categories(row, row.get("state_id", "?"))
    vector = (
        1.0,
        *z,
        *(1.0 if ttc == level else 0.0 for level in TTC_INDICATORS),
        *(1.0 if role == level else 0.0 for level in STRUCTURAL_ROLE_INDICATORS),
    )
    if len(vector) != 21:
        _error("design vector is not 21-dimensional")
    return tuple(vector)


def attach_development_labels(
    feature_rows: Sequence[Mapping[str, Any]],
    label_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, Any], ...]:
    """Attach already-exposed development labels only after feature materialization.

    Label rows are keyed strictly by state_id.  Outcomes never participate in
    feature eligibility, formula computation, chronology, or fingerprinting.
    """
    validate_feature_rows(feature_rows, enforce_frozen_counts=enforce_frozen_counts)
    labels: dict[str, int] = {}
    market_label: dict[tuple[str, str], int] = {}
    for index, source in enumerate(label_rows):
        state_id = str(source.get("state_id", ""))
        event = str(source.get("event_ticker", ""))
        market = str(source.get("market_ticker", ""))
        if not state_id or not event or not market:
            _error(f"label row[{index}] identity is incomplete")
        outcome = _int(source.get("outcome"), f"label row[{index}].outcome")
        if outcome not in (0, 1):
            _error(f"label row[{index}] outcome must be 0 or 1")
        if state_id in labels and labels[state_id] != outcome:
            _error(f"state {state_id} has conflicting labels")
        labels[state_id] = outcome
        key = (event, market)
        if key in market_label and market_label[key] != outcome:
            _error(f"market {event}/{market} has inconsistent outcome across decision states")
        market_label[key] = outcome
    feature_ids = {str(row["state_id"]) for row in feature_rows}
    if set(labels) != feature_ids:
        missing = sorted(feature_ids - set(labels))[:3]
        extra = sorted(set(labels) - feature_ids)[:3]
        _error(f"label state set mismatch; missing={missing}, extra={extra}")
    labeled: list[dict[str, Any]] = []
    for row in feature_rows:
        item = dict(row)
        item["outcome"] = labels[str(row["state_id"])]
        labeled.append(item)
    return tuple(labeled)


def prepare_fit_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    scaler: EventEqualScaler | None = None,
) -> tuple[EventEqualScaler, tuple[PreparedFitRow, ...]]:
    if not rows:
        _error("fit partition is empty")
    local_scaler = scaler if scaler is not None else fit_event_equal_scaler(rows)
    weights = event_equal_weights(rows)
    prepared: list[PreparedFitRow] = []
    for index, (row, weight) in enumerate(zip(rows, weights)):
        outcome = _int(row.get("outcome"), f"row[{index}].outcome")
        if outcome not in (0, 1):
            _error(f"row[{index}] outcome must be 0 or 1")
        p = _finite_float(row.get("candidate_probability"), f"row[{index}].candidate_probability")
        prepared.append(
            PreparedFitRow(
                state_id=str(row["state_id"]),
                event_ticker=str(row["event_ticker"]),
                stage=str(row["stage"]),
                outcome=outcome,
                candidate_probability=p,
                offset=candidate_offset(p),
                weight=weight,
                x=design_vector(row, local_scaler),
            )
        )
    return local_scaler, tuple(prepared)


def _objective_gradient_hessian(
    rows: Sequence[PreparedFitRow],
    beta: Sequence[float],
    lambda_value: float,
    *,
    need_hessian: bool = True,
) -> tuple[float, list[float], list[list[float]] | None]:
    if len(beta) != 21:
        _error("Model-2 coefficient vector must have dimension 21")
    if lambda_value not in LAMBDA_GRID:
        _error(f"lambda {lambda_value!r} is outside the frozen grid")
    objective = 0.5 * lambda_value * sum(value * value for value in beta)
    gradient = [lambda_value * value for value in beta]
    hessian = None
    if need_hessian:
        hessian = [[0.0] * 21 for _ in range(21)]
        for j in range(21):
            hessian[j][j] = lambda_value

    for row in rows:
        linear = row.offset + sum(b * x for b, x in zip(beta, row.x))
        objective += row.weight * binary_log_loss_from_logit(linear, row.outcome)
        p = stable_sigmoid(linear)
        residual_scale = row.weight * (p - row.outcome)
        for j, xj in enumerate(row.x):
            gradient[j] += residual_scale * xj
        if hessian is not None:
            variance_scale = row.weight * p * (1.0 - p)
            # Accumulate only lower triangle, then mirror.
            for j, xj in enumerate(row.x):
                scaled = variance_scale * xj
                for k in range(j + 1):
                    hessian[j][k] += scaled * row.x[k]
    if hessian is not None:
        for j in range(21):
            for k in range(j):
                hessian[k][j] = hessian[j][k]
    if not math.isfinite(objective) or any(not math.isfinite(value) for value in gradient):
        _error("Model-2 objective/gradient became non-finite")
    if hessian is not None and any(
        not math.isfinite(value) for row in hessian for value in row
    ):
        _error("Model-2 Hessian became non-finite")
    return objective, gradient, hessian


def dense_cholesky_solve(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    n = len(rhs)
    if n == 0 or len(matrix) != n or any(len(row) != n for row in matrix):
        _error("Cholesky system dimension mismatch")
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            value = float(matrix[i][j]) - sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                if not math.isfinite(value) or value <= 0.0:
                    _error("non-positive/non-finite Cholesky diagonal")
                lower[i][j] = math.sqrt(value)
            else:
                diagonal = lower[j][j]
                if not math.isfinite(diagonal) or diagonal <= 0.0:
                    _error("invalid Cholesky diagonal")
                lower[i][j] = value / diagonal
    y = [0.0] * n
    for i in range(n):
        y[i] = (float(rhs[i]) - sum(lower[i][k] * y[k] for k in range(i))) / lower[i][i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (
            y[i] - sum(lower[k][i] * x[k] for k in range(i + 1, n))
        ) / lower[i][i]
    if any(not math.isfinite(value) for value in x):
        _error("Cholesky solution became non-finite")
    return x


def fit_prepared_rows(
    rows: Sequence[PreparedFitRow],
    *,
    lambda_value: float,
    scaler: EventEqualScaler,
) -> ResidualFit:
    if lambda_value not in LAMBDA_GRID:
        _error(f"lambda {lambda_value!r} is outside the frozen grid")
    beta = [0.0] * 21
    for iteration in range(MAX_ITERATIONS + 1):
        objective, gradient, hessian = _objective_gradient_hessian(
            rows, beta, lambda_value, need_hessian=True
        )
        gradient_norm = math.sqrt(sum(value * value for value in gradient))
        if not math.isfinite(gradient_norm):
            _error("gradient norm became non-finite")
        if gradient_norm <= GRADIENT_L2_TOLERANCE:
            return ResidualFit(
                lambda_value=lambda_value,
                coefficients=tuple(beta),
                scaler=scaler,
                iterations=iteration,
                objective=objective,
            )
        if iteration >= MAX_ITERATIONS:
            break
        assert hessian is not None
        step = dense_cholesky_solve(hessian, gradient)
        directional = sum(g * s for g, s in zip(gradient, step))
        if not math.isfinite(directional) or directional <= 0.0:
            _error("Newton direction is not a descent direction")
        scale = INITIAL_STEP_SCALE
        accepted = False
        while scale >= MINIMUM_STEP_SCALE:
            proposal = [value - scale * delta for value, delta in zip(beta, step)]
            proposal_objective, _, _ = _objective_gradient_hessian(
                rows, proposal, lambda_value, need_hessian=False
            )
            if proposal_objective <= objective - ARMIJO_CONSTANT * scale * directional:
                beta = proposal
                accepted = True
                break
            scale *= REJECTED_STEP_MULTIPLIER
        if not accepted:
            _error("Model-2 damped Newton line search failed closed")
    _error("Model-2 damped Newton optimization did not converge within 100 iterations")
    raise AssertionError


def fit_residual_logistic(
    rows: Sequence[Mapping[str, Any]],
    *,
    lambda_value: float,
) -> ResidualFit:
    scaler, prepared = prepare_fit_rows(rows)
    return fit_prepared_rows(prepared, lambda_value=lambda_value, scaler=scaler)


def predict_probability(row: Mapping[str, Any], fit: ResidualFit) -> float:
    linear = candidate_offset(row.get("candidate_probability")) + sum(
        beta * value for beta, value in zip(fit.coefficients, design_vector(row, fit.scaler))
    )
    result = stable_sigmoid(linear)
    if not 0.0 <= result <= 1.0 or not math.isfinite(result):
        _error("Model-2 prediction became invalid")
    return result


def event_equal_metrics(
    rows: Sequence[Mapping[str, Any]],
    *,
    probability_key: str,
) -> tuple[float, float, dict[str, dict[str, float]]]:
    by_event: dict[str, list[tuple[float, float]]] = {}
    for index, row in enumerate(rows):
        event = str(row.get("event_ticker", ""))
        if not event:
            _error(f"metric row[{index}] missing event_ticker")
        outcome = _int(row.get("outcome"), f"metric row[{index}].outcome")
        p = _finite_float(row.get(probability_key), f"metric row[{index}].{probability_key}")
        if not 0.0 < p < 1.0:
            _error("Model-2/Candidate-E evaluation probability must satisfy 0 < p < 1")
        by_event.setdefault(event, []).append((binary_log_loss(p, outcome), brier_score(p, outcome)))
    if not by_event:
        _error("metric calculation received no rows")
    per_event: dict[str, dict[str, float]] = {}
    for event, values in by_event.items():
        per_event[event] = {
            "log_loss": sum(value[0] for value in values) / len(values),
            "brier": sum(value[1] for value in values) / len(values),
        }
    pooled_log_loss = sum(value["log_loss"] for value in per_event.values()) / len(per_event)
    pooled_brier = sum(value["brier"] for value in per_event.values()) / len(per_event)
    return pooled_log_loss, pooled_brier, per_event


def score_rows(rows: Sequence[Mapping[str, Any]], fit: ResidualFit) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["model2_probability"] = predict_probability(row, fit)
        result.append(item)
    return tuple(result)


def select_lambda(lambda_scores: Sequence[Mapping[str, Any]]) -> float:
    if {float(row["lambda"]) for row in lambda_scores} != set(LAMBDA_GRID):
        _error("lambda-score set does not equal the frozen grid")
    normalized = []
    for row in lambda_scores:
        value = float(row["lambda"])
        loss = _finite_float(row.get("pooled_event_equal_log_loss"), "lambda pooled log loss")
        normalized.append((loss, -value, value))
    normalized.sort()
    return normalized[0][2]


def _stage_subset(rows: Sequence[Mapping[str, Any]], stages: Sequence[str]) -> list[Mapping[str, Any]]:
    allowed = set(stages)
    result = [row for row in rows if str(row.get("stage")) in allowed]
    if not result:
        _error(f"no rows for stages {tuple(stages)}")
    return result


def evaluate_development_rolling_origin(
    labeled_rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> DevelopmentEvaluation:
    """Execute only the frozen H1_OOF->H2 and H1_OOF+H2->H3 tuning protocol.

    The caller controls when this function is invoked.  Checkpoint 21M uses it
    only on synthetic fixtures to validate machinery; real development fitting
    should occur only after the outcome-blind preparation freeze is accepted.
    """
    feature_projection = [{k: v for k, v in row.items() if k != "outcome"} for row in labeled_rows]
    build_development_event_map(feature_projection, enforce_frozen_counts=enforce_frozen_counts)
    for index, row in enumerate(labeled_rows):
        outcome = _int(row.get("outcome"), f"labeled row[{index}].outcome")
        if outcome not in (0, 1):
            _error("development outcome must be 0 or 1")

    fold_specs = (
        (1, ("H1_OOF",), "H2"),
        (2, ("H1_OOF", "H2"), "H3"),
    )
    scores_by_lambda: dict[float, list[dict[str, Any]]] = {value: [] for value in LAMBDA_GRID}
    fold_fits: list[dict[str, Any]] = []
    for fold, fit_stages, score_stage in fold_specs:
        fit_rows = _stage_subset(labeled_rows, fit_stages)
        score_partition = _stage_subset(labeled_rows, (score_stage,))
        scaler, prepared = prepare_fit_rows(fit_rows)
        for lambda_value in LAMBDA_GRID:
            fit = fit_prepared_rows(prepared, lambda_value=lambda_value, scaler=scaler)
            scored = score_rows(score_partition, fit)
            for row in scored:
                scores_by_lambda[lambda_value].append(dict(row))
            fold_fits.append(
                {
                    "fold": fold,
                    "fit_stages": list(fit_stages),
                    "score_stage": score_stage,
                    "lambda": lambda_value,
                    "iterations": fit.iterations,
                    "objective": fit.objective,
                    "coefficients": list(fit.coefficients),
                    "scaler": fit.scaler.as_dict(),
                }
            )

    lambda_scores: list[dict[str, Any]] = []
    for lambda_value in LAMBDA_GRID:
        rows = scores_by_lambda[lambda_value]
        if enforce_frozen_counts and len({str(row["event_ticker"]) for row in rows}) != EXPECTED_TUNING_SCORE_EVENTS:
            _error("pooled H2+H3 tuning score event count changed")
        loss, brier, _ = event_equal_metrics(rows, probability_key="model2_probability")
        lambda_scores.append(
            {
                "lambda": lambda_value,
                "pooled_event_equal_log_loss": loss,
                "pooled_event_equal_brier": brier,
            }
        )
    selected = select_lambda(lambda_scores)
    full_fit = fit_residual_logistic(labeled_rows, lambda_value=selected)
    return DevelopmentEvaluation(
        selected_lambda=selected,
        lambda_scores=tuple(lambda_scores),
        fold_fits=tuple(fold_fits),
        full_development_fit=full_fit,
    )


def model2_vs_candidate_e_diagnostics(
    scored_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    model_loss, model_brier, model_events = event_equal_metrics(
        scored_rows, probability_key="model2_probability"
    )
    base_loss, base_brier, base_events = event_equal_metrics(
        scored_rows, probability_key="candidate_probability"
    )
    if set(model_events) != set(base_events):
        _error("Model-2 and Candidate-E event sets differ")
    deltas = {
        event: base_events[event]["log_loss"] - model_events[event]["log_loss"]
        for event in model_events
    }
    return {
        "model2_event_equal_log_loss": model_loss,
        "candidate_e_event_equal_log_loss": base_loss,
        "candidate_e_minus_model2_log_loss": base_loss - model_loss,
        "model2_event_equal_brier": model_brier,
        "candidate_e_event_equal_brier": base_brier,
        "candidate_e_minus_model2_brier": base_brier - model_brier,
        "median_event_candidate_e_minus_model2_log_loss": median(deltas.values()),
    }


__all__ = [
    "ARMIJO_CONSTANT",
    "CANDIDATE_E_ID",
    "CONTINUOUS_FEATURES",
    "CandidateEEntryModelV1Error",
    "DEVELOPMENT_STAGES",
    "DevelopmentEvaluation",
    "EVENT_MAP_SCHEMA_VERSION",
    "EventEqualScaler",
    "EXPECTED_DEVELOPMENT_EVENT_COUNTS",
    "EXPECTED_DEVELOPMENT_EVENTS",
    "EXPECTED_DEVELOPMENT_ROW_COUNTS",
    "EXPECTED_DEVELOPMENT_ROWS",
    "GRADIENT_L2_TOLERANCE",
    "LAMBDA_GRID",
    "MODEL_ID",
    "PARAMETER_NAMES",
    "ROW_SCHEMA_VERSION",
    "ResidualFit",
    "STRUCTURAL_ROLES",
    "TTC_LEVELS",
    "attach_development_labels",
    "binary_log_loss",
    "build_development_event_map",
    "candidate_offset",
    "canonical_rows_fingerprint",
    "canonical_sha256",
    "dense_cholesky_solve",
    "design_vector",
    "evaluate_development_rolling_origin",
    "event_equal_metrics",
    "event_equal_weights",
    "fit_event_equal_scaler",
    "fit_residual_logistic",
    "model2_vs_candidate_e_diagnostics",
    "predict_probability",
    "select_lambda",
    "stable_sigmoid",
    "validate_feature_rows",
]
