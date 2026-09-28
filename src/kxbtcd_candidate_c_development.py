"""Checkpoint-15 KXBTCD Candidate-C rolling-origin development evaluation.

This module implements the exact Candidate-C v2 development protocol frozen in
Checkpoint 14.  It has two deliberately separated stages:

1. derive/freeze the five-block UTC-week map from the outcome-blind Checkpoint-12
   development rows; and
2. only after that map validates, load the already-exposed Checkpoint-13
   train+validation outcomes and run the four rolling-origin score folds.

The 64-event locked test is never labeled, scored, summarized, or fit here.
There is no network client and no execution path in this module.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

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
from .kxbtcd_candidate_c_predeclaration import (
    CANDIDATE_ID,
    CONTRACT_VERSION,
    L2_PENALTY_GRID,
    assign_contiguous_week_blocks,
    candidate_c_predeclaration,
    candidate_c_predeclaration_fingerprint,
    validate_candidate_c_predeclaration,
)


class KxbtcdCandidateCDevelopmentError(RuntimeError):
    """Raised when a frozen Candidate-C development invariant is violated."""


FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT = (
    "d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322"
)
EXPECTED_DEVELOPMENT_EVENTS = 231
EXPECTED_DEVELOPMENT_ROWS = 5364
EXPECTED_DEVELOPMENT_WEEKS = 58
EXPECTED_BLOCK_WEEK_COUNTS = (12, 12, 12, 11, 11)
WEEK_MAP_SCHEMA_VERSION = "kxbtcd_candidate_c_week_block_map.v1"
DEVELOPMENT_EVALUATION_SCHEMA_VERSION = "kxbtcd_candidate_c_development_evaluation.v1"
FOLD_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_c_fold_score.v1"
LAMBDA_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_c_lambda_score.v1"
COEFFICIENT_SCHEMA_VERSION = "kxbtcd_candidate_c_fold_coefficients.v1"
PREDICTION_SCHEMA_VERSION = "kxbtcd_candidate_c_oof_prediction.v1"
CALIBRATION_SCHEMA_VERSION = "kxbtcd_candidate_c_oof_calibration.v1"
DEFAULT_WEEK_MAP_PATH = Path("configs/kxbtcd_candidate_c_week_blocks.json")
CALIBRATION_BIN_EDGES = tuple(i / 10.0 for i in range(11))


@dataclass(frozen=True)
class CandidateCObservation:
    state_id: str
    event_ticker: str
    market_ticker: str
    utc_week_start: str
    block: int
    outcome: int
    q_market: float
    market_logit: float
    spread: float
    market_logit_x_spread: float

    @property
    def raw_features(self) -> tuple[float, float, float]:
        return (self.market_logit, self.spread, self.market_logit_x_spread)


@dataclass(frozen=True)
class FeatureScaler:
    means: tuple[float, float, float]
    population_stds: tuple[float, float, float]

    def transform(self, features: Sequence[float]) -> tuple[float, float, float]:
        if len(features) != 3:
            _error("Candidate-C scaler requires exactly three non-intercept features")
        return tuple(
            (float(features[j]) - self.means[j]) / self.population_stds[j]
            for j in range(3)
        )


@dataclass(frozen=True)
class CandidateCFit:
    lambda_value: Decimal
    fold_index: int
    fit_blocks: tuple[int, ...]
    score_block: int
    coefficients: tuple[float, float, float, float]
    scaler: FeatureScaler
    iterations: int
    converged: bool
    fit_objective: float


@dataclass(frozen=True)
class MetricPair:
    log_loss: float
    brier: float


@dataclass(frozen=True)
class CandidateCDevelopmentEvaluation:
    summary: dict[str, Any]
    fold_score_rows: tuple[dict[str, str], ...]
    lambda_score_rows: tuple[dict[str, str], ...]
    coefficient_rows: tuple[dict[str, str], ...]
    prediction_rows: tuple[dict[str, str], ...]
    calibration_rows: tuple[dict[str, str], ...]


def _error(message: str) -> None:
    raise KxbtcdCandidateCDevelopmentError(message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise KxbtcdCandidateCDevelopmentError(f"{name} must be numeric") from exc
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
        _error("attempted to serialize a non-finite Candidate-C value")
    return format(value, ".17g")


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_predeclaration_frozen() -> None:
    validate_candidate_c_predeclaration()
    observed = candidate_c_predeclaration_fingerprint()
    if observed != FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT:
        _error(
            "Candidate-C predeclaration fingerprint changed: "
            f"{observed} != {FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT}"
        )
    spec = candidate_c_predeclaration()
    if spec["contract_version"] != CONTRACT_VERSION or spec["candidate_id"] != CANDIDATE_ID:
        _error("Candidate-C contract identity changed")
    expected_folds = [
        {"fit_blocks": [0], "score_block": 1},
        {"fit_blocks": [0, 1], "score_block": 2},
        {"fit_blocks": [0, 1, 2], "score_block": 3},
        {"fit_blocks": [0, 1, 2, 3], "score_block": 4},
    ]
    if spec["development_selection_protocol"]["rolling_origin_folds"] != expected_folds:
        _error("Candidate-C rolling-origin folds changed")
    optimizer = spec["model"]["optimizer"]
    if optimizer != {
        "algorithm": "deterministic_damped_Newton",
        "max_iterations": 100,
        "gradient_l2_tolerance": "1e-8",
        "armijo_constant": "1e-4",
        "minimum_step_scale": "2^-40",
        "non_convergence": "fail_closed",
        "singular_hessian": "fail_closed",
    }:
        _error("Candidate-C optimizer contract changed")
    if tuple(spec["model"]["lambda_grid"]) != tuple(L2_PENALTY_GRID):
        _error("Candidate-C lambda grid changed")


def _week_map_payload(weeks: Iterable[str]) -> dict[str, Any]:
    """Build the canonical map payload using only the UTC-week identifiers."""

    _assert_predeclaration_frozen()
    normalized = [_text(week, "utc_week_start") for week in weeks]
    unique_weeks = sorted(set(normalized))
    if len(unique_weeks) != EXPECTED_DEVELOPMENT_WEEKS:
        _error(
            f"development week count changed: {len(unique_weeks)} != {EXPECTED_DEVELOPMENT_WEEKS}"
        )
    mapping = assign_contiguous_week_blocks(unique_weeks)
    entries = [
        {"utc_week_start": week, "block": f"B{mapping[week]}"}
        for week in unique_weeks
    ]
    observed_counts = tuple(
        sum(1 for entry in entries if entry["block"] == f"B{block}")
        for block in range(5)
    )
    if observed_counts != EXPECTED_BLOCK_WEEK_COUNTS:
        _error(
            "development block week counts violate the frozen balanced protocol: "
            f"{observed_counts} != {EXPECTED_BLOCK_WEEK_COUNTS}"
        )
    return {
        "schema_version": WEEK_MAP_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "chronology_unit": "utc_week_start",
        "block_rule": (
            "sort unique development UTC weeks ascending and divide into five contiguous blocks "
            "with week counts differing by at most one; earlier blocks receive any remainder"
        ),
        "development_week_count": len(unique_weeks),
        "block_week_counts": [int(value) for value in observed_counts],
        "week_to_block": entries,
    }


def derive_frozen_week_map(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    """Derive the exact map before any Candidate-C outcome-bearing fit is loaded.

    The frozen Checkpoint-12 dataset contains no labels.  Block assignment reads
    only ``partition`` to select the already-declared development scope and
    ``utc_week_start`` to form the chronology.  No q_market/spread/label value is
    used to decide a block.
    """

    frozen = load_frozen_preoutcome_dataset(repository_root)
    development_rows = [
        row for row in frozen.rows if row["partition"] in {"train", "validation"}
    ]
    if len(development_rows) != EXPECTED_DEVELOPMENT_ROWS:
        _error(
            f"development row count changed: {len(development_rows)} != {EXPECTED_DEVELOPMENT_ROWS}"
        )
    development_events = {row["event_ticker"] for row in development_rows}
    if len(development_events) != EXPECTED_DEVELOPMENT_EVENTS:
        _error(
            "development event count changed: "
            f"{len(development_events)} != {EXPECTED_DEVELOPMENT_EVENTS}"
        )
    payload = _week_map_payload(row["utc_week_start"] for row in development_rows)
    result = dict(payload)
    result["week_map_fingerprint"] = _canonical_sha256(payload)
    result["derivation_outcomes_used"] = False
    result["locked_test_outcomes_opened"] = 0
    return result


def validate_week_map_document(document: Mapping[str, Any]) -> dict[str, int]:
    _assert_predeclaration_frozen()
    if not isinstance(document, Mapping):
        _error("week-map root must be an object")
    required = {
        "schema_version",
        "candidate_id",
        "candidate_c_predeclaration_fingerprint",
        "frozen_preoutcome_run_id",
        "dataset_fingerprint",
        "split_fingerprint",
        "chronology_unit",
        "block_rule",
        "development_week_count",
        "block_week_counts",
        "week_to_block",
        "week_map_fingerprint",
        "derivation_outcomes_used",
        "locked_test_outcomes_opened",
    }
    missing = required - set(document)
    extra = set(document) - required
    if missing or extra:
        _error(f"week-map schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    if document["schema_version"] != WEEK_MAP_SCHEMA_VERSION:
        _error("week-map schema version mismatch")
    if document["candidate_id"] != CANDIDATE_ID:
        _error("week-map candidate ID mismatch")
    if (
        document["candidate_c_predeclaration_fingerprint"]
        != FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT
    ):
        _error("week-map Candidate-C predeclaration fingerprint mismatch")
    if document["frozen_preoutcome_run_id"] != FROZEN_PREOUTCOME_RUN_ID:
        _error("week-map pre-outcome run mismatch")
    if document["dataset_fingerprint"] != FROZEN_DATASET_FINGERPRINT:
        _error("week-map dataset fingerprint mismatch")
    if document["split_fingerprint"] != FROZEN_SPLIT_FINGERPRINT:
        _error("week-map split fingerprint mismatch")
    if document["chronology_unit"] != "utc_week_start":
        _error("week-map chronology unit changed")
    if int(document["development_week_count"]) != EXPECTED_DEVELOPMENT_WEEKS:
        _error("week-map development week count changed")
    if tuple(int(value) for value in document["block_week_counts"]) != EXPECTED_BLOCK_WEEK_COUNTS:
        _error("week-map block counts changed")
    if document["derivation_outcomes_used"] is not False:
        _error("week-map derivation must be outcome-blind")
    if int(document["locked_test_outcomes_opened"]) != 0:
        _error("week-map indicates locked-test outcome access")

    entries = document["week_to_block"]
    if not isinstance(entries, list) or len(entries) != EXPECTED_DEVELOPMENT_WEEKS:
        _error("week-map entries are missing or have the wrong count")
    weeks: list[str] = []
    mapping: dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != {"utc_week_start", "block"}:
            _error(f"week-map entry {index} schema mismatch")
        week = _text(entry["utc_week_start"], f"week_to_block[{index}].utc_week_start")
        block_text = _text(entry["block"], f"week_to_block[{index}].block")
        if block_text not in {"B0", "B1", "B2", "B3", "B4"}:
            _error(f"week-map entry {index} has invalid block {block_text!r}")
        if week in mapping:
            _error(f"duplicate UTC week in week map: {week}")
        weeks.append(week)
        mapping[week] = int(block_text[1:])
    if weeks != sorted(weeks):
        _error("week-map entries are not sorted chronologically by canonical UTC week text")

    expected_payload = _week_map_payload(weeks)
    expected_mapping = {
        entry["utc_week_start"]: int(entry["block"][1:])
        for entry in expected_payload["week_to_block"]
    }
    if mapping != expected_mapping:
        _error("week-map assignments do not follow the frozen contiguous balanced protocol")
    stored_payload = {key: document[key] for key in expected_payload}
    expected_fingerprint = _canonical_sha256(stored_payload)
    if document["week_map_fingerprint"] != expected_fingerprint:
        _error("week-map fingerprint mismatch")
    return mapping


def write_or_validate_frozen_week_map(
    path: str | Path = DEFAULT_WEEK_MAP_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[Path, str]:
    """Atomically create the map once, or validate an existing identical freeze."""

    target = Path(path)
    if not target.is_absolute():
        target = Path(repository_root).resolve() / target
    derived = derive_frozen_week_map(repository_root)
    validate_week_map_document(derived)
    fingerprint = str(derived["week_map_fingerprint"])
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise KxbtcdCandidateCDevelopmentError(
                f"could not read existing week map {target}: {exc}"
            ) from exc
        validate_week_map_document(existing)
        if existing != derived:
            _error(
                "existing Candidate-C week map differs from the outcome-blind derivation; "
                "refusing to overwrite the freeze"
            )
        return target, fingerprint
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(derived, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(target)
    return target, fingerprint


def load_and_validate_frozen_week_map(
    path: str | Path = DEFAULT_WEEK_MAP_PATH,
    *,
    repository_root: str | Path = ".",
    require_matches_current_frozen_development: bool = True,
) -> tuple[dict[str, int], dict[str, Any]]:
    target = Path(path)
    if not target.is_absolute():
        target = Path(repository_root).resolve() / target
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateCDevelopmentError(f"could not read week map {target}: {exc}") from exc
    mapping = validate_week_map_document(document)
    if require_matches_current_frozen_development:
        derived = derive_frozen_week_map(repository_root)
        if document != derived:
            _error("stored week map does not match the current frozen development derivation")
    return mapping, dict(document)


def _market_logit(q_market: float) -> float:
    """Reproduce the frozen CP12 0.001-clipped market-logit transform."""

    if not 0.0 <= q_market <= 1.0:
        _error(f"q_market outside [0,1]: {q_market}")
    q = Decimal(str(q_market))
    clip = Decimal("0.001")
    clipped = min(max(q, clip), Decimal("1") - clip)
    with localcontext() as context:
        context.prec = 34
        value = (clipped / (Decimal("1") - clipped)).ln()
    return float(value)


def build_candidate_c_observations(
    predictions: Sequence[DevelopmentPrediction],
    week_mapping: Mapping[str, int],
    *,
    enforce_canonical_counts: bool = True,
) -> tuple[CandidateCObservation, ...]:
    observations: list[CandidateCObservation] = []
    event_week: dict[str, str] = {}
    seen_states: set[str] = set()
    for index, row in enumerate(predictions):
        if row.partition not in {"train", "validation"}:
            _error(f"refusing non-development Candidate-C row partition {row.partition!r}")
        if row.state_id in seen_states:
            _error(f"duplicate Candidate-C state_id: {row.state_id}")
        seen_states.add(row.state_id)
        if row.utc_week_start not in week_mapping:
            _error(f"development row uses unmapped UTC week {row.utc_week_start}")
        previous_week = event_week.setdefault(row.event_ticker, row.utc_week_start)
        if previous_week != row.utc_week_start:
            _error(f"event {row.event_ticker} spans multiple UTC-week units")
        q = _float(row.q_market, f"predictions[{index}].q_market")
        spread = _float(row.spread, f"predictions[{index}].spread")
        if spread < 0:
            _error(f"predictions[{index}].spread must be nonnegative")
        market_logit = _market_logit(q)
        outcome = int(row.outcome)
        if outcome not in {0, 1}:
            _error(f"predictions[{index}].outcome must be binary")
        observations.append(
            CandidateCObservation(
                state_id=row.state_id,
                event_ticker=row.event_ticker,
                market_ticker=row.market_ticker,
                utc_week_start=row.utc_week_start,
                block=int(week_mapping[row.utc_week_start]),
                outcome=outcome,
                q_market=q,
                market_logit=market_logit,
                spread=spread,
                market_logit_x_spread=market_logit * spread,
            )
        )
    if enforce_canonical_counts:
        if len(observations) != EXPECTED_DEVELOPMENT_ROWS:
            _error(
                f"Candidate-C development row count changed: {len(observations)} != {EXPECTED_DEVELOPMENT_ROWS}"
            )
        event_count = len({row.event_ticker for row in observations})
        if event_count != EXPECTED_DEVELOPMENT_EVENTS:
            _error(
                f"Candidate-C development event count changed: {event_count} != {EXPECTED_DEVELOPMENT_EVENTS}"
            )
        represented_blocks = {row.block for row in observations}
        if represented_blocks != {0, 1, 2, 3, 4}:
            _error(f"Candidate-C development rows do not cover B0-B4: {sorted(represented_blocks)}")
    return tuple(observations)


def compute_fit_fold_scaler(rows: Sequence[CandidateCObservation]) -> FeatureScaler:
    """Ordinary row-level population z-scaling, computed on fit rows only.

    This directly implements the frozen wording: mean and population standard
    deviation are computed from the current fit block(s).  Event weighting is a
    separate objective/metric rule and is not silently applied to preprocessing.
    """

    if not rows:
        _error("cannot compute Candidate-C scaling on an empty fit fold")
    means: list[float] = []
    stds: list[float] = []
    for feature_index in range(3):
        values = [row.raw_features[feature_index] for row in rows]
        mean = math.fsum(values) / len(values)
        variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance)
        if not math.isfinite(mean) or not math.isfinite(std):
            _error("Candidate-C scaling produced a non-finite statistic")
        if std == 0.0:
            _error(f"Candidate-C fit-fold feature {feature_index} has zero variance")
        means.append(mean)
        stds.append(std)
    return FeatureScaler(tuple(means), tuple(stds))


def _event_indices(rows: Sequence[CandidateCObservation]) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        grouped.setdefault(row.event_ticker, []).append(index)
    if not grouped:
        _error("Candidate-C partition contains no events")
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
    return -(y * math.log(p) + (1 - y) * math.log1p(-p))


def _brier(p: float, y: int) -> float:
    return (p - float(y)) ** 2


def _standardized_x(row: CandidateCObservation, scaler: FeatureScaler) -> tuple[float, float, float, float]:
    z = scaler.transform(row.raw_features)
    return (1.0, z[0], z[1], z[2])


def _objective_gradient_hessian(
    rows: Sequence[CandidateCObservation],
    scaler: FeatureScaler,
    beta: Sequence[float],
    lambda_value: float,
) -> tuple[float, list[float], list[list[float]]]:
    grouped = _event_indices(rows)
    event_count = len(grouped)
    row_count_by_event = {event: len(indices) for event, indices in grouped.items()}
    objective = 0.0
    gradient = [0.0] * 4
    hessian = [[0.0] * 4 for _ in range(4)]
    for row in rows:
        x = _standardized_x(row, scaler)
        z = math.fsum(beta[j] * x[j] for j in range(4))
        p = _sigmoid(z)
        weight = 1.0 / (event_count * row_count_by_event[row.event_ticker])
        objective += weight * (_softplus(z) - float(row.outcome) * z)
        residual = p - float(row.outcome)
        curvature = p * (1.0 - p)
        for j in range(4):
            gradient[j] += weight * residual * x[j]
            for k in range(j, 4):
                contribution = weight * curvature * x[j] * x[k]
                hessian[j][k] += contribution
                if k != j:
                    hessian[k][j] += contribution
    objective += 0.5 * lambda_value * math.fsum(beta[j] * beta[j] for j in range(1, 4))
    for j in range(1, 4):
        gradient[j] += lambda_value * beta[j]
        hessian[j][j] += lambda_value
    return objective, gradient, hessian


def _solve_linear_system(matrix: Sequence[Sequence[float]], rhs: Sequence[float]) -> list[float]:
    n = len(rhs)
    augmented = [list(matrix[i]) + [float(rhs[i])] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(augmented[row][col]))
        if abs(augmented[pivot][col]) < 1e-15:
            _error("Candidate-C Newton Hessian is singular")
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
            _error("Candidate-C Newton back-substitution is singular")
        solution[row] = numerator / denominator
    return solution


def fit_candidate_c_fold(
    fit_rows: Sequence[CandidateCObservation],
    *,
    lambda_value: Decimal,
    fold_index: int,
    fit_blocks: Sequence[int],
    score_block: int,
    scaler: FeatureScaler | None = None,
) -> CandidateCFit:
    _assert_predeclaration_frozen()
    allowed_lambdas = tuple(Decimal(value) for value in L2_PENALTY_GRID)
    if lambda_value not in allowed_lambdas:
        _error(f"lambda {lambda_value} is outside the frozen Candidate-C grid")
    rows = tuple(fit_rows)
    if not rows:
        _error("Candidate-C fit fold is empty")
    fit_block_tuple = tuple(int(value) for value in fit_blocks)
    if {row.block for row in rows} - set(fit_block_tuple):
        _error("Candidate-C fit rows include a block outside the declared fit blocks")
    scaler = scaler or compute_fit_fold_scaler(rows)
    beta = [0.0, 0.0, 0.0, 0.0]
    lam = float(lambda_value)
    objective, gradient, hessian = _objective_gradient_hessian(rows, scaler, beta, lam)
    for iteration in range(1, 101):
        gradient_norm = math.sqrt(math.fsum(value * value for value in gradient))
        if gradient_norm <= 1e-8:
            return CandidateCFit(
                lambda_value=lambda_value,
                fold_index=fold_index,
                fit_blocks=fit_block_tuple,
                score_block=int(score_block),
                coefficients=tuple(beta),
                scaler=scaler,
                iterations=iteration - 1,
                converged=True,
                fit_objective=objective,
            )
        newton_step = _solve_linear_system(hessian, gradient)
        directional = math.fsum(gradient[j] * newton_step[j] for j in range(4))
        if not math.isfinite(directional) or directional <= 0.0:
            _error("Candidate-C Newton direction is not a descent direction")
        step_scale = 1.0
        accepted = False
        while step_scale >= 2.0 ** -40:
            candidate = [beta[j] - step_scale * newton_step[j] for j in range(4)]
            candidate_objective, candidate_gradient, candidate_hessian = (
                _objective_gradient_hessian(rows, scaler, candidate, lam)
            )
            if candidate_objective <= objective - 1e-4 * step_scale * directional:
                beta = candidate
                objective = candidate_objective
                gradient = candidate_gradient
                hessian = candidate_hessian
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            _error("Candidate-C damped Newton line search failed")
    _error("Candidate-C optimizer did not converge within 100 iterations")


def _predict(row: CandidateCObservation, fit: CandidateCFit) -> float:
    x = _standardized_x(row, fit.scaler)
    z = math.fsum(fit.coefficients[j] * x[j] for j in range(4))
    return _sigmoid(z)


def event_weighted_metrics(
    rows: Sequence[CandidateCObservation], probabilities: Sequence[float]
) -> MetricPair:
    if len(rows) != len(probabilities):
        _error("Candidate-C rows/probabilities length mismatch")
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
            math.fsum(_brier(probabilities[i], rows[i].outcome) for i in indices) / len(indices)
        )
    return MetricPair(
        log_loss=math.fsum(event_log_losses) / len(event_log_losses),
        brier=math.fsum(event_briers) / len(event_briers),
    )


def _event_sign_counts(
    rows: Sequence[CandidateCObservation],
    raw_probabilities: Sequence[float],
    candidate_probabilities: Sequence[float],
) -> tuple[int, int, int]:
    grouped = _event_indices(rows)
    better = worse = tie = 0
    for event in sorted(grouped):
        indices = grouped[event]
        raw = math.fsum(
            _probability_log_loss(raw_probabilities[i], rows[i].outcome) for i in indices
        ) / len(indices)
        candidate = math.fsum(
            _probability_log_loss(candidate_probabilities[i], rows[i].outcome)
            for i in indices
        ) / len(indices)
        if candidate < raw:
            better += 1
        elif candidate > raw:
            worse += 1
        else:
            tie += 1
    return better, worse, tie


def select_lambda_from_pooled_oof(loss_by_lambda: Mapping[Decimal, float]) -> Decimal:
    expected = {Decimal(value) for value in L2_PENALTY_GRID}
    if set(loss_by_lambda) != expected:
        _error("lambda selection must contain exactly the frozen Candidate-C grid")
    normalized = {
        penalty: Decimal(_float_text(float(loss))) for penalty, loss in loss_by_lambda.items()
    }
    best_loss = min(normalized.values())
    tied = [penalty for penalty, loss in normalized.items() if loss == best_loss]
    return max(tied)


def evaluate_advancement_gate(
    *,
    raw_pooled: MetricPair,
    candidate_pooled: MetricPair,
    per_fold_raw_log_loss: Sequence[float],
    per_fold_candidate_log_loss: Sequence[float],
) -> dict[str, Any]:
    if len(per_fold_raw_log_loss) != 4 or len(per_fold_candidate_log_loss) != 4:
        _error("Candidate-C advancement gate requires exactly four score blocks")
    condition_log_loss = candidate_pooled.log_loss < raw_pooled.log_loss
    condition_brier = candidate_pooled.brier <= raw_pooled.brier
    fold_wins = sum(
        1
        for raw, candidate in zip(per_fold_raw_log_loss, per_fold_candidate_log_loss)
        if candidate < raw
    )
    condition_fold_wins = fold_wins >= 3
    return {
        "pooled_oof_log_loss_strictly_better": condition_log_loss,
        "pooled_oof_brier_no_worse": condition_brier,
        "score_block_log_loss_win_count": fold_wins,
        "at_least_3_of_4_score_blocks_better": condition_fold_wins,
        "passed": condition_log_loss and condition_brier and condition_fold_wins,
    }


def _calibration_rows(
    *,
    rows: Sequence[CandidateCObservation],
    probabilities: Sequence[float],
    model_name: str,
    week_map_fingerprint: str,
    selected_lambda: Decimal,
) -> list[dict[str, str]]:
    if len(rows) != len(probabilities):
        _error("calibration rows/probabilities length mismatch")
    grouped = _event_indices(rows)
    row_weight = {
        index: 1.0 / len(grouped[row.event_ticker]) for index, row in enumerate(rows)
    }
    output: list[dict[str, str]] = []
    for bin_index in range(10):
        lower = CALIBRATION_BIN_EDGES[bin_index]
        upper = CALIBRATION_BIN_EDGES[bin_index + 1]
        selected = [
            i
            for i, probability in enumerate(probabilities)
            if probability >= lower
            and (probability < upper or (bin_index == 9 and probability <= upper))
        ]
        if not selected:
            continue
        weight_sum = math.fsum(row_weight[i] for i in selected)
        mean_prediction = math.fsum(row_weight[i] * probabilities[i] for i in selected) / weight_sum
        observed_rate = math.fsum(row_weight[i] * rows[i].outcome for i in selected) / weight_sum
        output.append(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "candidate_id": CANDIDATE_ID,
                "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
                "week_map_fingerprint": week_map_fingerprint,
                "selected_lambda": _decimal_text(selected_lambda),
                "model": model_name,
                "bin_lower_inclusive": _float_text(lower),
                "bin_upper_inclusive": _float_text(upper),
                "row_count": str(len(selected)),
                "event_count": str(len({rows[i].event_ticker for i in selected})),
                "event_weight_sum": _float_text(weight_sum),
                "event_weighted_mean_prediction": _float_text(mean_prediction),
                "event_weighted_observed_rate": _float_text(observed_rate),
            }
        )
    return output


def evaluate_candidate_c_development(
    observations: Sequence[CandidateCObservation],
    *,
    week_map_fingerprint: str,
    provenance: Mapping[str, Any],
    enforce_canonical_counts: bool = True,
) -> CandidateCDevelopmentEvaluation:
    _assert_predeclaration_frozen()
    rows = tuple(observations)
    if enforce_canonical_counts:
        if len(rows) != EXPECTED_DEVELOPMENT_ROWS:
            _error("Candidate-C evaluation requires the exact 5,364 development rows")
        if len({row.event_ticker for row in rows}) != EXPECTED_DEVELOPMENT_EVENTS:
            _error("Candidate-C evaluation requires the exact 231 development events")
    folds = candidate_c_predeclaration()["development_selection_protocol"]["rolling_origin_folds"]
    lambdas = tuple(Decimal(value) for value in L2_PENALTY_GRID)

    oof_by_lambda: dict[Decimal, list[tuple[CandidateCObservation, float, int]]] = {
        penalty: [] for penalty in lambdas
    }
    fold_score_rows: list[dict[str, str]] = []
    coefficient_rows: list[dict[str, str]] = []
    fits_by_key: dict[tuple[Decimal, int], CandidateCFit] = {}

    for fold_index, fold in enumerate(folds, start=1):
        fit_blocks = tuple(int(value) for value in fold["fit_blocks"])
        score_block = int(fold["score_block"])
        fit_rows = tuple(row for row in rows if row.block in fit_blocks)
        score_rows = tuple(row for row in rows if row.block == score_block)
        if not fit_rows or not score_rows:
            _error(f"rolling fold {fold_index} has an empty fit or score partition")
        scaler = compute_fit_fold_scaler(fit_rows)
        raw_probabilities = [row.q_market for row in score_rows]
        raw_metrics = event_weighted_metrics(score_rows, raw_probabilities)
        for lambda_value in lambdas:
            fit = fit_candidate_c_fold(
                fit_rows,
                lambda_value=lambda_value,
                fold_index=fold_index,
                fit_blocks=fit_blocks,
                score_block=score_block,
                scaler=scaler,
            )
            candidate_probabilities = [_predict(row, fit) for row in score_rows]
            candidate_metrics = event_weighted_metrics(score_rows, candidate_probabilities)
            fits_by_key[(lambda_value, fold_index)] = fit
            for row, probability in zip(score_rows, candidate_probabilities):
                oof_by_lambda[lambda_value].append((row, probability, fold_index))
            fold_score_rows.append(
                {
                    "schema_version": FOLD_SCORE_SCHEMA_VERSION,
                    "candidate_id": CANDIDATE_ID,
                    "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
                    "week_map_fingerprint": week_map_fingerprint,
                    "lambda": _decimal_text(lambda_value),
                    "fold": str(fold_index),
                    "fit_blocks": "+".join(f"B{value}" for value in fit_blocks),
                    "score_block": f"B{score_block}",
                    "fit_row_count": str(len(fit_rows)),
                    "fit_event_count": str(len({row.event_ticker for row in fit_rows})),
                    "score_row_count": str(len(score_rows)),
                    "score_event_count": str(len({row.event_ticker for row in score_rows})),
                    "raw_event_weighted_log_loss": _float_text(raw_metrics.log_loss),
                    "candidate_event_weighted_log_loss": _float_text(candidate_metrics.log_loss),
                    "delta_log_loss_raw_minus_candidate": _float_text(
                        raw_metrics.log_loss - candidate_metrics.log_loss
                    ),
                    "raw_event_weighted_brier": _float_text(raw_metrics.brier),
                    "candidate_event_weighted_brier": _float_text(candidate_metrics.brier),
                    "delta_brier_raw_minus_candidate": _float_text(
                        raw_metrics.brier - candidate_metrics.brier
                    ),
                }
            )
            coefficient_rows.append(
                {
                    "schema_version": COEFFICIENT_SCHEMA_VERSION,
                    "candidate_id": CANDIDATE_ID,
                    "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
                    "week_map_fingerprint": week_map_fingerprint,
                    "lambda": _decimal_text(lambda_value),
                    "fold": str(fold_index),
                    "fit_blocks": "+".join(f"B{value}" for value in fit_blocks),
                    "score_block": f"B{score_block}",
                    "beta0": _float_text(fit.coefficients[0]),
                    "beta1_market_logit_z": _float_text(fit.coefficients[1]),
                    "beta2_spread_z": _float_text(fit.coefficients[2]),
                    "beta3_market_logit_x_spread_z": _float_text(fit.coefficients[3]),
                    "mean_market_logit": _float_text(fit.scaler.means[0]),
                    "mean_spread": _float_text(fit.scaler.means[1]),
                    "mean_market_logit_x_spread": _float_text(fit.scaler.means[2]),
                    "std_market_logit": _float_text(fit.scaler.population_stds[0]),
                    "std_spread": _float_text(fit.scaler.population_stds[1]),
                    "std_market_logit_x_spread": _float_text(fit.scaler.population_stds[2]),
                    "iterations": str(fit.iterations),
                    "converged": "true" if fit.converged else "false",
                    "fit_objective": _float_text(fit.fit_objective),
                }
            )

    lambda_score_rows: list[dict[str, str]] = []
    pooled_metrics_by_lambda: dict[Decimal, MetricPair] = {}
    pooled_raw_by_lambda: dict[Decimal, MetricPair] = {}
    for lambda_value in lambdas:
        entries = sorted(
            oof_by_lambda[lambda_value],
            key=lambda item: (item[0].block, item[0].event_ticker, item[0].state_id),
        )
        oof_rows = [item[0] for item in entries]
        candidate_probabilities = [item[1] for item in entries]
        raw_probabilities = [row.q_market for row in oof_rows]
        if {row.block for row in oof_rows} != {1, 2, 3, 4}:
            _error("pooled Candidate-C OOF rows do not cover score blocks B1-B4")
        raw_metrics = event_weighted_metrics(oof_rows, raw_probabilities)
        candidate_metrics = event_weighted_metrics(oof_rows, candidate_probabilities)
        pooled_metrics_by_lambda[lambda_value] = candidate_metrics
        pooled_raw_by_lambda[lambda_value] = raw_metrics
        lambda_score_rows.append(
            {
                "schema_version": LAMBDA_SCORE_SCHEMA_VERSION,
                "candidate_id": CANDIDATE_ID,
                "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
                "week_map_fingerprint": week_map_fingerprint,
                "lambda": _decimal_text(lambda_value),
                "oof_row_count": str(len(oof_rows)),
                "oof_event_count": str(len({row.event_ticker for row in oof_rows})),
                "raw_event_weighted_log_loss": _float_text(raw_metrics.log_loss),
                "candidate_event_weighted_log_loss": _float_text(candidate_metrics.log_loss),
                "delta_log_loss_raw_minus_candidate": _float_text(
                    raw_metrics.log_loss - candidate_metrics.log_loss
                ),
                "raw_event_weighted_brier": _float_text(raw_metrics.brier),
                "candidate_event_weighted_brier": _float_text(candidate_metrics.brier),
                "delta_brier_raw_minus_candidate": _float_text(
                    raw_metrics.brier - candidate_metrics.brier
                ),
                "selected_lambda": "false",
            }
        )

    selected_lambda = select_lambda_from_pooled_oof(
        {penalty: metrics.log_loss for penalty, metrics in pooled_metrics_by_lambda.items()}
    )
    for row in lambda_score_rows:
        row["selected_lambda"] = "true" if Decimal(row["lambda"]) == selected_lambda else "false"

    selected_entries = sorted(
        oof_by_lambda[selected_lambda],
        key=lambda item: (item[0].block, item[0].event_ticker, item[0].state_id),
    )
    selected_rows = [item[0] for item in selected_entries]
    selected_probabilities = [item[1] for item in selected_entries]
    selected_folds = [item[2] for item in selected_entries]
    raw_probabilities = [row.q_market for row in selected_rows]
    raw_pooled = pooled_raw_by_lambda[selected_lambda]
    candidate_pooled = pooled_metrics_by_lambda[selected_lambda]

    per_fold_raw: list[float] = []
    per_fold_candidate: list[float] = []
    for fold_index in range(1, 5):
        score_rows = [row for row in selected_rows if row.block == fold_index]
        score_candidate = [
            probability
            for row, probability in zip(selected_rows, selected_probabilities)
            if row.block == fold_index
        ]
        score_raw = [row.q_market for row in score_rows]
        raw_metrics = event_weighted_metrics(score_rows, score_raw)
        candidate_metrics = event_weighted_metrics(score_rows, score_candidate)
        per_fold_raw.append(raw_metrics.log_loss)
        per_fold_candidate.append(candidate_metrics.log_loss)
    gate = evaluate_advancement_gate(
        raw_pooled=raw_pooled,
        candidate_pooled=candidate_pooled,
        per_fold_raw_log_loss=per_fold_raw,
        per_fold_candidate_log_loss=per_fold_candidate,
    )
    better, worse, tie = _event_sign_counts(
        selected_rows, raw_probabilities, selected_probabilities
    )

    prediction_rows: list[dict[str, str]] = []
    for row, probability, fold_index in zip(selected_rows, selected_probabilities, selected_folds):
        raw_loss = _probability_log_loss(row.q_market, row.outcome)
        candidate_loss = _probability_log_loss(probability, row.outcome)
        prediction_rows.append(
            {
                "schema_version": PREDICTION_SCHEMA_VERSION,
                "candidate_id": CANDIDATE_ID,
                "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
                "week_map_fingerprint": week_map_fingerprint,
                "selected_lambda": _decimal_text(selected_lambda),
                "fold": str(fold_index),
                "score_block": f"B{row.block}",
                "state_id": row.state_id,
                "event_ticker": row.event_ticker,
                "market_ticker": row.market_ticker,
                "utc_week_start": row.utc_week_start,
                "outcome": str(row.outcome),
                "q_market": _float_text(row.q_market),
                "candidate_c_probability": _float_text(probability),
                "raw_log_loss": _float_text(raw_loss),
                "candidate_c_log_loss": _float_text(candidate_loss),
                "raw_brier": _float_text(_brier(row.q_market, row.outcome)),
                "candidate_c_brier": _float_text(_brier(probability, row.outcome)),
            }
        )

    calibration_rows = _calibration_rows(
        rows=selected_rows,
        probabilities=raw_probabilities,
        model_name="raw_market_midpoint",
        week_map_fingerprint=week_map_fingerprint,
        selected_lambda=selected_lambda,
    ) + _calibration_rows(
        rows=selected_rows,
        probabilities=selected_probabilities,
        model_name=CANDIDATE_ID,
        week_map_fingerprint=week_map_fingerprint,
        selected_lambda=selected_lambda,
    )

    event_counts_by_block = {
        f"B{block}": len({row.event_ticker for row in rows if row.block == block})
        for block in range(5)
    }
    row_counts_by_block = {
        f"B{block}": sum(1 for row in rows if row.block == block) for block in range(5)
    }
    summary = {
        "schema_version": DEVELOPMENT_EVALUATION_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "candidate_c_predeclaration_contract": CONTRACT_VERSION,
        "candidate_c_predeclaration_fingerprint": FROZEN_CANDIDATE_C_PREDECLARATION_FINGERPRINT,
        "week_map_fingerprint": week_map_fingerprint,
        "source_cp13_run_id": CP13_RUN_ID,
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "development_event_count": len({row.event_ticker for row in rows}),
        "development_row_count": len(rows),
        "development_event_counts_by_block": event_counts_by_block,
        "development_row_counts_by_block": row_counts_by_block,
        "oof_score_blocks": ["B1", "B2", "B3", "B4"],
        "selected_lambda": _decimal_text(selected_lambda),
        "raw_pooled_oof_event_weighted_log_loss": raw_pooled.log_loss,
        "candidate_c_pooled_oof_event_weighted_log_loss": candidate_pooled.log_loss,
        "delta_log_loss_raw_minus_candidate_c": raw_pooled.log_loss - candidate_pooled.log_loss,
        "raw_pooled_oof_event_weighted_brier": raw_pooled.brier,
        "candidate_c_pooled_oof_event_weighted_brier": candidate_pooled.brier,
        "delta_brier_raw_minus_candidate_c": raw_pooled.brier - candidate_pooled.brier,
        "per_score_block_raw_log_loss": {
            f"B{index}": per_fold_raw[index - 1] for index in range(1, 5)
        },
        "per_score_block_candidate_c_log_loss": {
            f"B{index}": per_fold_candidate[index - 1] for index in range(1, 5)
        },
        "candidate_c_better_event_count": better,
        "candidate_c_worse_event_count": worse,
        "candidate_c_tie_event_count": tie,
        "development_advancement_gate": gate,
        "eligible_for_later_freeze_final_fit_checkpoint": bool(gate["passed"]),
        "full_development_final_fit_performed": False,
        "full_development_scaler_frozen": False,
        "rolling_origin_model_fit_count": 16,
        "candidate_c_development_fit_performed": True,
        "locked_test_feature_density_inspected_for_design": False,
        "locked_test_outcomes_opened": 0,
        "locked_test_evaluation_performed": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "source_provenance_before_cp15_fit": dict(provenance),
    }
    return CandidateCDevelopmentEvaluation(
        summary=summary,
        fold_score_rows=tuple(fold_score_rows),
        lambda_score_rows=tuple(lambda_score_rows),
        coefficient_rows=tuple(coefficient_rows),
        prediction_rows=tuple(prediction_rows),
        calibration_rows=tuple(calibration_rows),
    )


def load_and_evaluate_candidate_c_development(
    *,
    repository_root: str | Path = ".",
    week_map_path: str | Path = DEFAULT_WEEK_MAP_PATH,
) -> CandidateCDevelopmentEvaluation:
    """Production entrypoint: validate the outcome-blind map first, then load labels."""

    week_mapping, week_document = load_and_validate_frozen_week_map(
        week_map_path,
        repository_root=repository_root,
        require_matches_current_frozen_development=True,
    )
    # This is intentionally after the outcome-blind map verification above.
    predictions, provenance = load_canonical_development_predictions(repository_root)
    if provenance.get("locked_test_outcomes_opened") != 0:
        _error("canonical development provenance does not preserve the locked-test firewall")
    observations = build_candidate_c_observations(predictions, week_mapping)
    return evaluate_candidate_c_development(
        observations,
        week_map_fingerprint=str(week_document["week_map_fingerprint"]),
        provenance=provenance,
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    if not rows:
        _error(f"refusing to write empty Candidate-C CSV: {path.name}")
    fields = list(rows[0].keys())
    for index, row in enumerate(rows):
        if list(row.keys()) != fields:
            _error(f"Candidate-C CSV row {index} schema/order mismatch for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_development_evaluation(
    output_dir: str | Path,
    *,
    evaluation: CandidateCDevelopmentEvaluation,
) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    paths = {
        "summary": target / "candidate_c_development_summary.json",
        "fold_scores": target / "candidate_c_fold_scores.csv",
        "lambda_scores": target / "candidate_c_lambda_scores.csv",
        "coefficients": target / "candidate_c_fold_coefficients.csv",
        "predictions": target / "candidate_c_selected_oof_predictions.csv",
        "calibration": target / "candidate_c_selected_oof_calibration.csv",
    }
    paths["summary"].write_text(
        json.dumps(evaluation.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_csv(paths["fold_scores"], evaluation.fold_score_rows)
    _write_csv(paths["lambda_scores"], evaluation.lambda_score_rows)
    _write_csv(paths["coefficients"], evaluation.coefficient_rows)
    _write_csv(paths["predictions"], evaluation.prediction_rows)
    _write_csv(paths["calibration"], evaluation.calibration_rows)
    return paths


_assert_predeclaration_frozen()
