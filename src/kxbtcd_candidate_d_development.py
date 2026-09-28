"""Checkpoint-18C KXBTCD Candidate-D frozen development evaluation.

This module implements, but does not alter, the Checkpoint-18B predeclaration.
The seven-block map is validated from the frozen pre-outcome dataset before
canonical CP13 development outcomes are loaded.

No network client, terminal-result reader, paper broker, or execution path is
present here.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_b_evaluation import (
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_PREOUTCOME_RUN_ID,
    FROZEN_SPLIT_FINGERPRINT,
    load_frozen_preoutcome_dataset,
)
from .kxbtcd_candidate_b_failure_analysis import (
    CP13_RUN_ID,
    DevelopmentPrediction,
    load_canonical_development_predictions,
)
from .kxbtcd_candidate_d_predeclaration import (
    CANDIDATE_ID,
    FROZEN_PREDECLARATION_FINGERPRINT,
    candidate_d_predeclaration,
    validate_candidate_d_predeclaration,
)


class KxbtcdCandidateDDevelopmentError(RuntimeError):
    """Raised when a frozen Candidate-D development invariant is violated."""


EXPECTED_DEVELOPMENT_ROWS = 5364
EXPECTED_DEVELOPMENT_EVENTS = 231
EXPECTED_DEVELOPMENT_WEEKS = 58
EXPECTED_BLOCK_WEEK_COUNTS = (9, 9, 8, 8, 8, 8, 8)
EXPECTED_BLOCK_EVENT_COUNTS = (35, 36, 32, 32, 32, 32, 32)
EXPECTED_SCORED_EVENTS = 160
DEFAULT_WEEK_MAP_PATH = Path("configs/kxbtcd_candidate_d_week_blocks.json")

SUMMARY_SCHEMA_VERSION = "kxbtcd_candidate_d_development_evaluation.v1"
FOLD_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_d_fold_score.v1"
COEFFICIENT_SCHEMA_VERSION = "kxbtcd_candidate_d_fold_coefficients.v1"
PREDICTION_SCHEMA_VERSION = "kxbtcd_candidate_d_oof_prediction.v1"
EVENT_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_d_event_score.v1"


@dataclass(frozen=True)
class CandidateDObservation:
    partition: str
    state_id: str
    event_ticker: str
    market_ticker: str
    utc_week_start: str
    block: int
    outcome: int
    q_market: float
    market_logit: float


@dataclass(frozen=True)
class CandidateDFit:
    fold_index: int
    fit_blocks: tuple[int, ...]
    score_block: int
    alpha: float
    delta: float
    iterations: int
    converged: bool
    fit_objective: float

    @property
    def market_logit_slope(self) -> float:
        return 1.0 + self.delta


@dataclass(frozen=True)
class MetricPair:
    log_loss: float
    brier: float


@dataclass(frozen=True)
class CandidateDDevelopmentEvaluation:
    summary: dict[str, Any]
    fold_score_rows: tuple[dict[str, str], ...]
    coefficient_rows: tuple[dict[str, str], ...]
    prediction_rows: tuple[dict[str, str], ...]
    event_score_rows: tuple[dict[str, str], ...]


def _error(message: str) -> None:
    raise KxbtcdCandidateDDevelopmentError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise KxbtcdCandidateDDevelopmentError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _float(value: Any, name: str) -> float:
    result = float(_decimal(value, name))
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        _error("attempted to serialize a non-finite Candidate-D value")
    return format(value, ".17g")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateDDevelopmentError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        _error(f"JSON root must be an object: {path}")
    return value


def _assert_predeclaration_frozen() -> dict[str, Any]:
    observed = validate_candidate_d_predeclaration()
    if observed != FROZEN_PREDECLARATION_FINGERPRINT:
        _error("Candidate-D predeclaration fingerprint mismatch")
    spec = candidate_d_predeclaration()
    if spec["candidate_id"] != CANDIDATE_ID:
        _error("Candidate-D ID changed")
    if spec["model"]["hyperparameter_search"] is not False:
        _error("Candidate-D hyperparameter search must remain disabled")
    if spec["model"]["regularization"] != "none":
        _error("Candidate-D regularization changed")
    if spec["model"]["feature_scaling"] != "none":
        _error("Candidate-D scaling changed")
    if spec["model"]["spread_feature"] != "prohibited":
        _error("Candidate-D spread feature changed")
    if spec["model"]["market_logit_x_spread_interaction"] != "prohibited":
        _error("Candidate-D interaction changed")
    expected_folds = [
        {"fold": 1, "fit_blocks": ["B0", "B1"], "score_block": "B2"},
        {"fold": 2, "fit_blocks": ["B0", "B1", "B2"], "score_block": "B3"},
        {"fold": 3, "fit_blocks": ["B0", "B1", "B2", "B3"], "score_block": "B4"},
        {"fold": 4, "fit_blocks": ["B0", "B1", "B2", "B3", "B4"], "score_block": "B5"},
        {"fold": 5, "fit_blocks": ["B0", "B1", "B2", "B3", "B4", "B5"], "score_block": "B6"},
    ]
    if spec["development_protocol"]["rolling_origin_folds"] != expected_folds:
        _error("Candidate-D rolling-origin folds changed")
    optimizer = spec["model"]["optimizer"]
    expected_optimizer = {
        "algorithm": "deterministic_damped_Newton",
        "max_iterations": 100,
        "gradient_l2_tolerance": "1e-8",
        "armijo_constant": "1e-4",
        "minimum_step_scale": "2^-40",
        "non_convergence": "fail_closed",
        "singular_hessian": "fail_closed",
    }
    if optimizer != expected_optimizer:
        _error("Candidate-D optimizer contract changed")
    return spec


def validate_candidate_d_week_map(
    path: str | Path = DEFAULT_WEEK_MAP_PATH,
    *,
    repository_root: str | Path = ".",
    require_matches_frozen_preoutcome: bool = True,
) -> tuple[dict[str, int], dict[str, Any]]:
    """Validate the outcome-blind seven-block map and optionally reconcile it to CP12."""
    spec = _assert_predeclaration_frozen()
    repo = Path(repository_root).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = repo / target
    document = dict(_load_json(target))

    required = {
        "schema_version",
        "candidate_id",
        "candidate_d_predeclaration_fingerprint",
        "chronology_unit",
        "layout_id",
        "block_rule",
        "development_week_count",
        "block_week_counts",
        "block_event_counts",
        "week_to_block",
        "derivation_outcomes_used",
        "terminal_outcomes_used",
        "week_map_fingerprint",
    }
    if set(document) != required:
        _error(
            "Candidate-D week-map schema mismatch; "
            f"missing={sorted(required - set(document))}, extra={sorted(set(document) - required)}"
        )
    if document["schema_version"] != "kxbtcd_candidate_d_week_block_map.v1":
        _error("Candidate-D week-map schema version changed")
    if document["candidate_id"] != CANDIDATE_ID:
        _error("Candidate-D week-map candidate changed")
    if document["candidate_d_predeclaration_fingerprint"] != FROZEN_PREDECLARATION_FINGERPRINT:
        _error("Candidate-D week-map predeclaration fingerprint changed")
    if document["chronology_unit"] != "utc_week_start":
        _error("Candidate-D week-map chronology unit changed")
    if document["layout_id"] != "7_contiguous_utc_week_blocks":
        _error("Candidate-D week-map layout changed")
    if int(document["development_week_count"]) != EXPECTED_DEVELOPMENT_WEEKS:
        _error("Candidate-D development week count changed")
    if tuple(int(x) for x in document["block_week_counts"]) != EXPECTED_BLOCK_WEEK_COUNTS:
        _error("Candidate-D block week counts changed")
    if tuple(int(x) for x in document["block_event_counts"]) != EXPECTED_BLOCK_EVENT_COUNTS:
        _error("Candidate-D block event counts changed")
    if document["derivation_outcomes_used"] is not False:
        _error("Candidate-D week map must be outcome-blind")
    if document["terminal_outcomes_used"] is not False:
        _error("Candidate-D week map indicates terminal outcome use")

    entries = document["week_to_block"]
    if not isinstance(entries, list) or len(entries) != EXPECTED_DEVELOPMENT_WEEKS:
        _error("Candidate-D week-map entries have the wrong count")
    weeks: list[str] = []
    mapping: dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != {"utc_week_start", "block"}:
            _error(f"Candidate-D week-map entry {index} schema mismatch")
        week = str(entry["utc_week_start"])
        block_text = str(entry["block"])
        if block_text not in {f"B{i}" for i in range(7)}:
            _error(f"Candidate-D week-map entry {index} has invalid block")
        if week in mapping:
            _error(f"duplicate Candidate-D UTC week {week}")
        weeks.append(week)
        mapping[week] = int(block_text[1:])
    if weeks != sorted(weeks):
        _error("Candidate-D week-map entries are not chronological")

    payload = {key: document[key] for key in document if key != "week_map_fingerprint"}
    if document["week_map_fingerprint"] != _canonical_sha256(payload):
        _error("Candidate-D week-map fingerprint mismatch")

    declared_blocks = spec["development_protocol"]["blocks"]
    for block_index, declared in enumerate(declared_blocks):
        block_weeks = [week for week in weeks if mapping[week] == block_index]
        if len(block_weeks) != int(declared["week_count"]):
            _error(f"Candidate-D B{block_index} week count differs from predeclaration")
        if block_weeks[0] != declared["first_week"] or block_weeks[-1] != declared["last_week"]:
            _error(f"Candidate-D B{block_index} week range differs from predeclaration")

    if require_matches_frozen_preoutcome:
        frozen = load_frozen_preoutcome_dataset(repo)
        development_rows = [
            row for row in frozen.rows if row["partition"] in {"train", "validation"}
        ]
        if len(development_rows) != EXPECTED_DEVELOPMENT_ROWS:
            _error("frozen pre-outcome development row count changed")
        event_week: dict[str, str] = {}
        for row in development_rows:
            event = row["event_ticker"]
            week = row["utc_week_start"]
            previous = event_week.setdefault(event, week)
            if previous != week:
                _error(f"development event spans multiple UTC weeks: {event}")
        if len(event_week) != EXPECTED_DEVELOPMENT_EVENTS:
            _error("frozen pre-outcome development event count changed")
        observed_weeks = sorted({row["utc_week_start"] for row in development_rows})
        if observed_weeks != weeks:
            _error("Candidate-D week map does not exactly match frozen pre-outcome weeks")
        observed_event_counts = [0] * 7
        for event, week in event_week.items():
            if week not in mapping:
                _error(f"development event week is absent from Candidate-D map: {week}")
            observed_event_counts[mapping[week]] += 1
        if tuple(observed_event_counts) != EXPECTED_BLOCK_EVENT_COUNTS:
            _error(
                "Candidate-D outcome-blind block event counts changed: "
                f"{tuple(observed_event_counts)} != {EXPECTED_BLOCK_EVENT_COUNTS}"
            )

    return mapping, document


def _market_logit(q_market: float) -> float:
    """Frozen 0.001-clipped market-logit transform."""
    if not 0.0 <= q_market <= 1.0:
        _error(f"q_market outside [0,1]: {q_market}")
    q = Decimal(str(q_market))
    clip = Decimal("0.001")
    clipped = min(max(q, clip), Decimal("1") - clip)
    with localcontext() as context:
        context.prec = 34
        value = (clipped / (Decimal("1") - clipped)).ln()
    result = float(value)
    if not math.isfinite(result):
        _error("market logit is non-finite")
    return result


def build_candidate_d_observations(
    predictions: Sequence[DevelopmentPrediction],
    week_mapping: Mapping[str, int],
    *,
    enforce_canonical_counts: bool = True,
) -> tuple[CandidateDObservation, ...]:
    """Discard all non-Candidate-D model features and retain q/outcome/lineage only."""
    _assert_predeclaration_frozen()
    observations: list[CandidateDObservation] = []
    seen_states: set[str] = set()
    event_week: dict[str, str] = {}
    for index, row in enumerate(predictions):
        if row.partition not in {"train", "validation"}:
            _error(f"refusing non-development partition {row.partition!r}")
        if row.state_id in seen_states:
            _error(f"duplicate Candidate-D state_id: {row.state_id}")
        seen_states.add(row.state_id)
        if row.utc_week_start not in week_mapping:
            _error(f"Candidate-D row uses unmapped UTC week {row.utc_week_start}")
        previous = event_week.setdefault(row.event_ticker, row.utc_week_start)
        if previous != row.utc_week_start:
            _error(f"event {row.event_ticker} spans multiple UTC weeks")
        q = _float(row.q_market, f"predictions[{index}].q_market")
        outcome = int(row.outcome)
        if outcome not in {0, 1}:
            _error(f"predictions[{index}].outcome must be binary")
        observations.append(
            CandidateDObservation(
                partition=row.partition,
                state_id=row.state_id,
                event_ticker=row.event_ticker,
                market_ticker=row.market_ticker,
                utc_week_start=row.utc_week_start,
                block=int(week_mapping[row.utc_week_start]),
                outcome=outcome,
                q_market=q,
                market_logit=_market_logit(q),
            )
        )
    if enforce_canonical_counts:
        if len(observations) != EXPECTED_DEVELOPMENT_ROWS:
            _error("Candidate-D development row count changed")
        if len(event_week) != EXPECTED_DEVELOPMENT_EVENTS:
            _error("Candidate-D development event count changed")
        if {row.block for row in observations} != set(range(7)):
            _error("Candidate-D rows do not cover B0-B6")
        event_counts = [
            len({row.event_ticker for row in observations if row.block == block})
            for block in range(7)
        ]
        if tuple(event_counts) != EXPECTED_BLOCK_EVENT_COUNTS:
            _error(
                "Candidate-D development block event counts changed: "
                f"{tuple(event_counts)} != {EXPECTED_BLOCK_EVENT_COUNTS}"
            )
    return tuple(observations)


def _event_indices(rows: Sequence[CandidateDObservation]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(row.event_ticker, []).append(index)
    if not grouped:
        _error("Candidate-D partition contains no events")
    return grouped


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _softplus(z: float) -> float:
    if z > 0:
        return z + math.log1p(math.exp(-z))
    return math.log1p(math.exp(z))


def _probability_log_loss(p: float, y: int) -> float:
    if not 0.0 <= p <= 1.0:
        _error(f"probability outside [0,1]: {p}")
    if p == 0.0:
        return 0.0 if y == 0 else math.inf
    if p == 1.0:
        return 0.0 if y == 1 else math.inf
    value = -(y * math.log(p) + (1 - y) * math.log1p(-p))
    if not math.isfinite(value):
        _error("non-finite log loss")
    return value


def _brier(p: float, y: int) -> float:
    value = (p - float(y)) ** 2
    if not math.isfinite(value):
        _error("non-finite Brier score")
    return value


def _objective_gradient_hessian(
    rows: Sequence[CandidateDObservation],
    beta: Sequence[float],
) -> tuple[float, list[float], list[list[float]]]:
    """Event-weighted log loss with market_logit as a fixed offset."""
    if len(beta) != 2:
        _error("Candidate-D beta must contain alpha and delta")
    grouped = _event_indices(rows)
    event_count = len(grouped)
    row_count_by_event = {event: len(indices) for event, indices in grouped.items()}
    objective = 0.0
    gradient = [0.0, 0.0]
    hessian = [[0.0, 0.0], [0.0, 0.0]]
    for row in rows:
        x = (1.0, row.market_logit)
        z = row.market_logit + beta[0] + beta[1] * row.market_logit
        p = _sigmoid(z)
        weight = 1.0 / (event_count * row_count_by_event[row.event_ticker])
        objective += weight * (_softplus(z) - float(row.outcome) * z)
        residual = p - float(row.outcome)
        curvature = p * (1.0 - p)
        for j in range(2):
            gradient[j] += weight * residual * x[j]
            for k in range(j, 2):
                contribution = weight * curvature * x[j] * x[k]
                hessian[j][k] += contribution
                if k != j:
                    hessian[k][j] += contribution
    if not math.isfinite(objective) or any(not math.isfinite(x) for x in gradient):
        _error("Candidate-D objective/gradient became non-finite")
    if any(not math.isfinite(x) for row in hessian for x in row):
        _error("Candidate-D Hessian became non-finite")
    return objective, gradient, hessian


def _solve_linear_system(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    n = len(rhs)
    augmented = [list(matrix[i]) + [float(rhs[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-15:
            _error("Candidate-D Newton Hessian is singular")
        if pivot != col:
            augmented[col], augmented[pivot] = augmented[pivot], augmented[col]
        pivot_value = augmented[col][col]
        for row in range(col + 1, n):
            factor = augmented[row][col] / pivot_value
            if factor == 0.0:
                continue
            for k in range(col, n + 1):
                augmented[row][k] -= factor * augmented[col][k]
    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        numerator = augmented[row][n] - math.fsum(
            augmented[row][col] * solution[col] for col in range(row + 1, n)
        )
        denominator = augmented[row][row]
        if abs(denominator) < 1e-15:
            _error("Candidate-D Newton back-substitution is singular")
        solution[row] = numerator / denominator
    return solution


def fit_candidate_d_fold(
    fit_rows: Sequence[CandidateDObservation],
    *,
    fold_index: int,
    fit_blocks: Sequence[int],
    score_block: int,
) -> CandidateDFit:
    """Fit the exact two-parameter frozen Candidate-D calibration model."""
    spec = _assert_predeclaration_frozen()
    rows = tuple(fit_rows)
    if not rows:
        _error("Candidate-D fit fold is empty")
    fit_block_tuple = tuple(int(x) for x in fit_blocks)
    if {row.block for row in rows} - set(fit_block_tuple):
        _error("Candidate-D fit rows include a block outside declared fit blocks")

    optimizer = spec["model"]["optimizer"]
    max_iterations = int(optimizer["max_iterations"])
    gradient_tolerance = float(optimizer["gradient_l2_tolerance"])
    armijo = float(optimizer["armijo_constant"])
    min_step = 2.0 ** -40

    beta = [0.0, 0.0]  # alpha, delta; exactly the raw market initialization
    objective, gradient, hessian = _objective_gradient_hessian(rows, beta)

    for iteration in range(1, max_iterations + 1):
        gradient_norm = math.sqrt(math.fsum(value * value for value in gradient))
        if gradient_norm <= gradient_tolerance:
            fit = CandidateDFit(
                fold_index=int(fold_index),
                fit_blocks=fit_block_tuple,
                score_block=int(score_block),
                alpha=beta[0],
                delta=beta[1],
                iterations=iteration - 1,
                converged=True,
                fit_objective=objective,
            )
            if not all(
                math.isfinite(x)
                for x in (fit.alpha, fit.delta, fit.market_logit_slope, fit.fit_objective)
            ):
                _error("Candidate-D fit produced non-finite parameters")
            return fit

        newton_step = _solve_linear_system(hessian, gradient)
        directional = math.fsum(gradient[j] * newton_step[j] for j in range(2))
        if not math.isfinite(directional) or directional <= 0.0:
            _error("Candidate-D Newton direction is not a descent direction")

        step_scale = 1.0
        accepted = False
        while step_scale >= min_step:
            candidate = [beta[j] - step_scale * newton_step[j] for j in range(2)]
            candidate_objective, candidate_gradient, candidate_hessian = (
                _objective_gradient_hessian(rows, candidate)
            )
            if candidate_objective <= objective - armijo * step_scale * directional:
                beta = candidate
                objective = candidate_objective
                gradient = candidate_gradient
                hessian = candidate_hessian
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            _error("Candidate-D damped Newton line search failed")

    _error("Candidate-D optimizer did not converge within 100 iterations")


def predict_candidate_d(row: CandidateDObservation, fit: CandidateDFit) -> float:
    z = fit.alpha + fit.market_logit_slope * row.market_logit
    p = _sigmoid(z)
    if not math.isfinite(p):
        _error("Candidate-D prediction is non-finite")
    return p


def event_weighted_metrics(
    rows: Sequence[CandidateDObservation],
    probabilities: Sequence[float],
) -> MetricPair:
    if len(rows) != len(probabilities):
        _error("Candidate-D rows/probabilities length mismatch")
    grouped = _event_indices(rows)
    event_log_losses: list[float] = []
    event_briers: list[float] = []
    for event in sorted(grouped):
        indices = grouped[event]
        event_log_losses.append(
            math.fsum(_probability_log_loss(probabilities[i], rows[i].outcome) for i in indices)
            / len(indices)
        )
        event_briers.append(
            math.fsum(_brier(probabilities[i], rows[i].outcome) for i in indices)
            / len(indices)
        )
    result = MetricPair(
        log_loss=math.fsum(event_log_losses) / len(event_log_losses),
        brier=math.fsum(event_briers) / len(event_briers),
    )
    if not math.isfinite(result.log_loss) or not math.isfinite(result.brier):
        _error("Candidate-D aggregate metric is non-finite")
    return result


def event_score_rows(
    rows: Sequence[CandidateDObservation],
    raw_probabilities: Sequence[float],
    candidate_probabilities: Sequence[float],
    *,
    week_map_fingerprint: str,
) -> list[dict[str, str]]:
    if not (len(rows) == len(raw_probabilities) == len(candidate_probabilities)):
        _error("Candidate-D event-score inputs differ in length")
    grouped = _event_indices(rows)
    output: list[dict[str, str]] = []
    for event in sorted(grouped):
        indices = grouped[event]
        block_values = {rows[i].block for i in indices}
        week_values = {rows[i].utc_week_start for i in indices}
        if len(block_values) != 1 or len(week_values) != 1:
            _error(f"event {event} crosses Candidate-D block/week units")
        raw_ll = math.fsum(
            _probability_log_loss(raw_probabilities[i], rows[i].outcome) for i in indices
        ) / len(indices)
        candidate_ll = math.fsum(
            _probability_log_loss(candidate_probabilities[i], rows[i].outcome)
            for i in indices
        ) / len(indices)
        raw_brier = math.fsum(
            _brier(raw_probabilities[i], rows[i].outcome) for i in indices
        ) / len(indices)
        candidate_brier = math.fsum(
            _brier(candidate_probabilities[i], rows[i].outcome) for i in indices
        ) / len(indices)
        output.append(
            {
                "schema_version": EVENT_SCORE_SCHEMA_VERSION,
                "candidate_id": CANDIDATE_ID,
                "candidate_d_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
                "week_map_fingerprint": week_map_fingerprint,
                "event_ticker": event,
                "utc_week_start": next(iter(week_values)),
                "score_block": f"B{next(iter(block_values))}",
                "row_count": str(len(indices)),
                "raw_event_log_loss": _float_text(raw_ll),
                "candidate_d_event_log_loss": _float_text(candidate_ll),
                "delta_log_loss_raw_minus_candidate_d": _float_text(raw_ll - candidate_ll),
                "raw_event_brier": _float_text(raw_brier),
                "candidate_d_event_brier": _float_text(candidate_brier),
                "delta_brier_raw_minus_candidate_d": _float_text(raw_brier - candidate_brier),
            }
        )
    return output


def evaluate_advancement_gate(
    *,
    raw_pooled: MetricPair,
    candidate_pooled: MetricPair,
    per_block_raw_log_loss: Sequence[float],
    per_block_candidate_log_loss: Sequence[float],
    median_event_delta: float,
    fits: Sequence[CandidateDFit],
) -> dict[str, Any]:
    if len(per_block_raw_log_loss) != 5 or len(per_block_candidate_log_loss) != 5:
        _error("Candidate-D gate requires exactly five score blocks")
    if len(fits) != 5:
        _error("Candidate-D gate requires exactly five fits")

    pooled_log_loss_better = candidate_pooled.log_loss < raw_pooled.log_loss
    pooled_brier_no_worse = candidate_pooled.brier <= raw_pooled.brier
    block_wins = sum(
        1
        for raw, candidate in zip(per_block_raw_log_loss, per_block_candidate_log_loss)
        if candidate < raw
    )
    at_least_4_of_5 = block_wins >= 4
    latest_b6_better = per_block_candidate_log_loss[-1] < per_block_raw_log_loss[-1]
    median_positive = median_event_delta > 0.0
    fits_converged_finite = all(
        fit.converged
        and all(
            math.isfinite(x)
            for x in (fit.alpha, fit.delta, fit.market_logit_slope, fit.fit_objective)
        )
        for fit in fits
    )
    all_slopes_positive = all(fit.market_logit_slope > 0.0 for fit in fits)

    reasons: list[str] = []
    if not pooled_log_loss_better:
        reasons.append("pooled_log_loss_not_strictly_better")
    if not pooled_brier_no_worse:
        reasons.append("pooled_brier_worse")
    if not at_least_4_of_5:
        reasons.append("fewer_than_4_of_5_score_block_log_loss_wins")
    if not latest_b6_better:
        reasons.append("latest_B6_log_loss_not_strictly_better")
    if not median_positive:
        reasons.append("median_event_log_loss_delta_not_positive")
    if not fits_converged_finite:
        reasons.append("fit_convergence_or_finite_check_failed")
    if not all_slopes_positive:
        reasons.append("nonpositive_market_logit_slope")

    passed = not reasons
    return {
        "pooled_oof_log_loss_strictly_better": pooled_log_loss_better,
        "pooled_oof_brier_no_worse": pooled_brier_no_worse,
        "score_block_log_loss_win_count": block_wins,
        "at_least_4_of_5_score_blocks_better": at_least_4_of_5,
        "latest_B6_log_loss_strictly_better": latest_b6_better,
        "median_event_log_loss_delta_positive": median_positive,
        "all_five_fits_converged_and_finite": fits_converged_finite,
        "all_five_market_logit_slopes_positive": all_slopes_positive,
        "automatic_failure_reasons": reasons,
        "passed": passed,
    }


def evaluate_candidate_d_development(
    repository_root: str | Path = ".",
    *,
    week_map_path: str | Path = DEFAULT_WEEK_MAP_PATH,
) -> CandidateDDevelopmentEvaluation:
    """Execute the frozen five-fold exposed-development stability screen."""
    spec = _assert_predeclaration_frozen()
    repo = Path(repository_root).resolve()

    # Stage 1: outcome-blind chronology validation from the CP12 frozen pre-outcome dataset.
    week_mapping, week_document = validate_candidate_d_week_map(
        week_map_path,
        repository_root=repo,
        require_matches_frozen_preoutcome=True,
    )
    week_map_fingerprint = str(week_document["week_map_fingerprint"])

    # Stage 2: only after chronology is validated, load canonical pre-terminal CP13 outcomes.
    predictions, provenance = load_canonical_development_predictions(repo)
    if int(provenance.get("locked_test_outcomes_opened", -1)) != 0:
        _error("canonical development loader does not prove zero locked-test openings")
    if int(provenance.get("network_requests", -1)) != 0:
        _error("canonical development loader unexpectedly made network requests")
    if provenance.get("execution_enabled") is not False or int(provenance.get("orders_placed", -1)) != 0:
        _error("canonical development loader violates execution boundary")

    observations = build_candidate_d_observations(predictions, week_mapping)
    frozen_folds = spec["development_protocol"]["rolling_origin_folds"]

    fold_score_rows: list[dict[str, str]] = []
    coefficient_rows: list[dict[str, str]] = []
    prediction_rows: list[dict[str, str]] = []
    all_scored_rows: list[CandidateDObservation] = []
    all_raw_probabilities: list[float] = []
    all_candidate_probabilities: list[float] = []
    fits: list[CandidateDFit] = []
    per_block_raw_ll: list[float] = []
    per_block_candidate_ll: list[float] = []

    for fold_spec in frozen_folds:
        fold_index = int(fold_spec["fold"])
        fit_blocks = tuple(int(text[1:]) for text in fold_spec["fit_blocks"])
        score_block = int(fold_spec["score_block"][1:])
        fit_rows = tuple(row for row in observations if row.block in fit_blocks)
        score_rows = tuple(row for row in observations if row.block == score_block)
        if len({row.event_ticker for row in score_rows}) != 32:
            _error(f"Candidate-D B{score_block} score event count changed")

        fit = fit_candidate_d_fold(
            fit_rows,
            fold_index=fold_index,
            fit_blocks=fit_blocks,
            score_block=score_block,
        )
        fits.append(fit)

        raw_probs = [row.q_market for row in score_rows]
        candidate_probs = [predict_candidate_d(row, fit) for row in score_rows]
        raw_metrics = event_weighted_metrics(score_rows, raw_probs)
        candidate_metrics = event_weighted_metrics(score_rows, candidate_probs)
        per_block_raw_ll.append(raw_metrics.log_loss)
        per_block_candidate_ll.append(candidate_metrics.log_loss)

        fold_score_rows.append(
            {
                "schema_version": FOLD_SCORE_SCHEMA_VERSION,
                "candidate_id": CANDIDATE_ID,
                "candidate_d_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
                "week_map_fingerprint": week_map_fingerprint,
                "fold": str(fold_index),
                "fit_blocks": "+".join(f"B{x}" for x in fit_blocks),
                "score_block": f"B{score_block}",
                "fit_event_count": str(len({row.event_ticker for row in fit_rows})),
                "fit_row_count": str(len(fit_rows)),
                "score_event_count": str(len({row.event_ticker for row in score_rows})),
                "score_row_count": str(len(score_rows)),
                "raw_event_weighted_log_loss": _float_text(raw_metrics.log_loss),
                "candidate_d_event_weighted_log_loss": _float_text(candidate_metrics.log_loss),
                "delta_log_loss_raw_minus_candidate_d": _float_text(
                    raw_metrics.log_loss - candidate_metrics.log_loss
                ),
                "raw_event_weighted_brier": _float_text(raw_metrics.brier),
                "candidate_d_event_weighted_brier": _float_text(candidate_metrics.brier),
                "delta_brier_raw_minus_candidate_d": _float_text(
                    raw_metrics.brier - candidate_metrics.brier
                ),
            }
        )
        coefficient_rows.append(
            {
                "schema_version": COEFFICIENT_SCHEMA_VERSION,
                "candidate_id": CANDIDATE_ID,
                "candidate_d_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
                "week_map_fingerprint": week_map_fingerprint,
                "fold": str(fold_index),
                "fit_blocks": "+".join(f"B{x}" for x in fit_blocks),
                "score_block": f"B{score_block}",
                "alpha": _float_text(fit.alpha),
                "delta": _float_text(fit.delta),
                "market_logit_slope_1_plus_delta": _float_text(fit.market_logit_slope),
                "iterations": str(fit.iterations),
                "converged": str(fit.converged).lower(),
                "fit_objective": _float_text(fit.fit_objective),
            }
        )

        for row, raw_p, candidate_p in zip(score_rows, raw_probs, candidate_probs):
            prediction_rows.append(
                {
                    "schema_version": PREDICTION_SCHEMA_VERSION,
                    "candidate_id": CANDIDATE_ID,
                    "candidate_d_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
                    "week_map_fingerprint": week_map_fingerprint,
                    "fold": str(fold_index),
                    "score_block": f"B{score_block}",
                    "partition": row.partition,
                    "state_id": row.state_id,
                    "event_ticker": row.event_ticker,
                    "market_ticker": row.market_ticker,
                    "utc_week_start": row.utc_week_start,
                    "outcome": str(row.outcome),
                    "q_market": _float_text(row.q_market),
                    "market_logit": _float_text(row.market_logit),
                    "candidate_d_probability": _float_text(candidate_p),
                    "raw_log_loss": _float_text(_probability_log_loss(raw_p, row.outcome)),
                    "candidate_d_log_loss": _float_text(
                        _probability_log_loss(candidate_p, row.outcome)
                    ),
                    "raw_brier": _float_text(_brier(raw_p, row.outcome)),
                    "candidate_d_brier": _float_text(_brier(candidate_p, row.outcome)),
                }
            )

        all_scored_rows.extend(score_rows)
        all_raw_probabilities.extend(raw_probs)
        all_candidate_probabilities.extend(candidate_probs)

    if len({row.event_ticker for row in all_scored_rows}) != EXPECTED_SCORED_EVENTS:
        _error("Candidate-D pooled OOF event count changed")

    raw_pooled = event_weighted_metrics(all_scored_rows, all_raw_probabilities)
    candidate_pooled = event_weighted_metrics(all_scored_rows, all_candidate_probabilities)
    event_rows = event_score_rows(
        all_scored_rows,
        all_raw_probabilities,
        all_candidate_probabilities,
        week_map_fingerprint=week_map_fingerprint,
    )
    event_deltas = [float(row["delta_log_loss_raw_minus_candidate_d"]) for row in event_rows]
    median_event_delta = float(median(event_deltas))

    gate = evaluate_advancement_gate(
        raw_pooled=raw_pooled,
        candidate_pooled=candidate_pooled,
        per_block_raw_log_loss=per_block_raw_ll,
        per_block_candidate_log_loss=per_block_candidate_ll,
        median_event_delta=median_event_delta,
        fits=fits,
    )

    slope_values = [fit.market_logit_slope for fit in fits]
    alpha_values = [fit.alpha for fit in fits]
    delta_values = [fit.delta for fit in fits]

    deterministic_result_payload = {
        "candidate_id": CANDIDATE_ID,
        "candidate_d_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "week_map_fingerprint": week_map_fingerprint,
        "raw_pooled_log_loss": _float_text(raw_pooled.log_loss),
        "candidate_d_pooled_log_loss": _float_text(candidate_pooled.log_loss),
        "raw_pooled_brier": _float_text(raw_pooled.brier),
        "candidate_d_pooled_brier": _float_text(candidate_pooled.brier),
        "median_event_delta": _float_text(median_event_delta),
        "gate": gate,
        "coefficients": [
            {
                "fold": fit.fold_index,
                "alpha": _float_text(fit.alpha),
                "delta": _float_text(fit.delta),
                "slope": _float_text(fit.market_logit_slope),
            }
            for fit in fits
        ],
    }

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "candidate_d_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "week_map_fingerprint": week_map_fingerprint,
        "evaluation_result_fingerprint": _canonical_sha256(deterministic_result_payload),
        "review_scope": "exposed_development_stability_screen_only",
        "development_event_count": EXPECTED_DEVELOPMENT_EVENTS,
        "development_row_count": EXPECTED_DEVELOPMENT_ROWS,
        "development_week_count": EXPECTED_DEVELOPMENT_WEEKS,
        "oof_event_count": EXPECTED_SCORED_EVENTS,
        "oof_row_count": len(all_scored_rows),
        "raw_pooled_oof_event_weighted_log_loss": raw_pooled.log_loss,
        "candidate_d_pooled_oof_event_weighted_log_loss": candidate_pooled.log_loss,
        "delta_log_loss_raw_minus_candidate_d": raw_pooled.log_loss - candidate_pooled.log_loss,
        "raw_pooled_oof_event_weighted_brier": raw_pooled.brier,
        "candidate_d_pooled_oof_event_weighted_brier": candidate_pooled.brier,
        "delta_brier_raw_minus_candidate_d": raw_pooled.brier - candidate_pooled.brier,
        "median_event_delta_log_loss_raw_minus_candidate_d": median_event_delta,
        "candidate_d_better_event_count": sum(1 for x in event_deltas if x > 0.0),
        "candidate_d_worse_event_count": sum(1 for x in event_deltas if x < 0.0),
        "candidate_d_tie_event_count": sum(1 for x in event_deltas if x == 0.0),
        "coefficient_stability_report_only": {
            "alpha_min": min(alpha_values),
            "alpha_max": max(alpha_values),
            "alpha_range": max(alpha_values) - min(alpha_values),
            "delta_min": min(delta_values),
            "delta_max": max(delta_values),
            "delta_range": max(delta_values) - min(delta_values),
            "market_logit_slope_min": min(slope_values),
            "market_logit_slope_max": max(slope_values),
            "market_logit_slope_range": max(slope_values) - min(slope_values),
            "post_hoc_threshold_applied": False,
        },
        "development_advancement_gate": gate,
        "development_screen_passed": bool(gate["passed"]),
        "development_pass_meaning": spec["development_advancement_gate"][
            "development_pass_meaning"
        ],
        "source_cp13_development_provenance": provenance,
        "source_frozen_preoutcome": {
            "run_id": FROZEN_PREOUTCOME_RUN_ID,
            "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
            "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
            "week_map_derivation_outcomes_used": False,
        },
        "candidate_d_model_fit_performed": True,
        "candidate_d_fit_count": 5,
        "candidate_d_hyperparameter_search_performed": False,
        "candidate_d_regularization_used": False,
        "candidate_c_refit_performed": False,
        "terminal_result_artifact_loaded": False,
        "terminal_rows_loaded": 0,
        "terminal_labels_loaded": 0,
        "terminal_features_loaded": 0,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "interpretation_boundary": (
            "This is an exposed-development stability screen under the frozen Checkpoint-18B "
            "contract. A PASS does not constitute untouched validation, profitability evidence, "
            "or execution authorization."
        ),
    }

    return CandidateDDevelopmentEvaluation(
        summary=summary,
        fold_score_rows=tuple(fold_score_rows),
        coefficient_rows=tuple(coefficient_rows),
        prediction_rows=tuple(prediction_rows),
        event_score_rows=tuple(event_rows),
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    if not rows:
        _error(f"refusing to write empty Candidate-D CSV: {path}")
    fieldnames = list(rows[0].keys())
    for index, row in enumerate(rows):
        if list(row.keys()) != fieldnames:
            _error(f"Candidate-D CSV row {index} schema/order mismatch")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_candidate_d_development_evaluation(
    evaluation: CandidateDDevelopmentEvaluation,
    *,
    repository_root: str | Path = ".",
) -> dict[str, str]:
    repo = Path(repository_root).resolve()
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = repo / "data" / "analysis" / "kxbtcd_candidate_d_development" / run_stamp
    if output_dir.exists():
        _error(f"Candidate-D output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)

    paths = {
        "fold_scores": output_dir / "candidate_d_fold_scores.csv",
        "fold_coefficients": output_dir / "candidate_d_fold_coefficients.csv",
        "oof_predictions": output_dir / "candidate_d_oof_predictions.csv",
        "event_scores": output_dir / "candidate_d_event_scores.csv",
    }
    _write_csv(paths["fold_scores"], evaluation.fold_score_rows)
    _write_csv(paths["fold_coefficients"], evaluation.coefficient_rows)
    _write_csv(paths["oof_predictions"], evaluation.prediction_rows)
    _write_csv(paths["event_scores"], evaluation.event_score_rows)

    summary = dict(evaluation.summary)
    summary["generated_at_utc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary["artifact_sha256"] = {
        key: _sha256(path) for key, path in paths.items()
    }
    summary_path = output_dir / "candidate_d_development_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return {
        "output_dir": str(output_dir),
        "summary": str(summary_path),
        **{key: str(path) for key, path in paths.items()},
    }
