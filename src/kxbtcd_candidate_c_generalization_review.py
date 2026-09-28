"""Checkpoint-18A development-only Candidate-C generalization-risk review.

This module is intentionally diagnostic-only.

Allowed evidence:
- the canonical Checkpoint-15 rolling-origin development artifacts;
- the canonical Checkpoint-13 train+validation development predictions/context;
- the frozen Checkpoint-15 outcome-blind week map.

Prohibited evidence:
- Checkpoint-17 terminal prediction rows, labels, residuals, feature slices,
  feature distributions, or any other terminal-test artifact.

The terminal result is not loaded.  No HTTP client is imported, no network
request is made, and no successor model is fit.  Fold prediction-stability
diagnostics reconstruct the already-fitted Checkpoint-15 fold models from their
stored coefficients and scalers.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable, Mapping, Sequence


class KxbtcdCandidateCGeneralizationReviewError(RuntimeError):
    """Raised when a Checkpoint-18A development-only invariant is violated."""


CANONICAL_CP15_ANALYSIS_DIR = Path(
    "data/analysis/kxbtcd_candidate_c_development/20260815T220714Z"
)
CANDIDATE_ID = "kxbtcd_market_spread_interaction_logistic.v1"
EXPECTED_PREDECLARATION_FINGERPRINT = (
    "d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322"
)
EXPECTED_WEEK_MAP_FINGERPRINT = (
    "6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4"
)
EXPECTED_SELECTED_LAMBDA = "0.01"
EXPECTED_DEVELOPMENT_EVENTS = 231
EXPECTED_DEVELOPMENT_ROWS = 5364
EXPECTED_OOF_EVENTS = 184
EXPECTED_OOF_ROWS = 4442
EXPECTED_SCORE_BLOCKS = ("B1", "B2", "B3", "B4")
EXPECTED_BLOCK_EVENT_COUNTS = {"B0": 47, "B1": 48, "B2": 48, "B3": 44, "B4": 44}
EXPECTED_BLOCK_ROW_COUNTS = {"B0": 922, "B1": 1436, "B2": 1426, "B3": 1104, "B4": 476}

SUMMARY_SCHEMA_VERSION = "kxbtcd_candidate_c_generalization_review.v1"
BLOCK_SCHEMA_VERSION = "kxbtcd_candidate_c_generalization_block.v1"
EVENT_SCHEMA_VERSION = "kxbtcd_candidate_c_generalization_event.v1"
WEEK_SCHEMA_VERSION = "kxbtcd_candidate_c_generalization_week.v1"
LEAVE_ONE_BLOCK_SCHEMA_VERSION = "kxbtcd_candidate_c_leave_one_block_out.v1"
COEFFICIENT_SCHEMA_VERSION = "kxbtcd_candidate_c_coefficient_stability.v1"
GRID_SCHEMA_VERSION = "kxbtcd_candidate_c_prediction_stability_grid.v1"
CORRECTION_GRID_SCHEMA_VERSION = "kxbtcd_candidate_c_correction_grid.v1"
CONDITIONING_SCHEMA_VERSION = "kxbtcd_candidate_c_feature_conditioning.v1"
LAMBDA_SCHEMA_VERSION = "kxbtcd_candidate_c_lambda_stability.v1"
PROTOCOL_LAYOUT_SCHEMA_VERSION = "kxbtcd_successor_protocol_layout_candidate.v1"

CP15_FILENAMES = {
    "summary": "candidate_c_development_summary.json",
    "fold_scores": "candidate_c_fold_scores.csv",
    "lambda_scores": "candidate_c_lambda_scores.csv",
    "coefficients": "candidate_c_fold_coefficients.csv",
    "predictions": "candidate_c_selected_oof_predictions.csv",
    "calibration": "candidate_c_selected_oof_calibration.csv",
}


@dataclass(frozen=True)
class DevelopmentContextRow:
    state_id: str
    event_ticker: str
    market_ticker: str
    utc_week_start: str
    block: str
    q_market: float
    spread: float
    market_logit: float
    market_logit_x_spread: float


@dataclass(frozen=True)
class OofRow:
    state_id: str
    event_ticker: str
    market_ticker: str
    utc_week_start: str
    block: str
    outcome: int
    q_market: float
    spread: float
    candidate_probability: float
    raw_log_loss: float
    candidate_log_loss: float
    raw_brier: float
    candidate_brier: float


@dataclass(frozen=True)
class FoldModel:
    fold: int
    fit_blocks: tuple[str, ...]
    score_block: str
    beta0: float
    beta1: float
    beta2: float
    beta3: float
    means: tuple[float, float, float]
    stds: tuple[float, float, float]


@dataclass(frozen=True)
class EventMetric:
    event_ticker: str
    block: str
    utc_week_start: str
    row_count: int
    raw_log_loss: float
    candidate_log_loss: float
    delta_log_loss: float
    raw_brier: float
    candidate_brier: float
    delta_brier: float


@dataclass(frozen=True)
class ReviewResult:
    summary: dict[str, Any]
    block_rows: tuple[dict[str, str], ...]
    event_rows: tuple[dict[str, str], ...]
    week_rows: tuple[dict[str, str], ...]
    leave_one_block_out_rows: tuple[dict[str, str], ...]
    coefficient_rows: tuple[dict[str, str], ...]
    fixed_grid_rows: tuple[dict[str, str], ...]
    correction_grid_rows: tuple[dict[str, str], ...]
    conditioning_rows: tuple[dict[str, str], ...]
    lambda_rows: tuple[dict[str, str], ...]
    protocol_layout_rows: tuple[dict[str, str], ...]


def _error(message: str) -> None:
    raise KxbtcdCandidateCGeneralizationReviewError(message)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise KxbtcdCandidateCGeneralizationReviewError(
            f"{name} must be numeric"
        ) from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        _error("attempted to serialize a non-finite review value")
    return format(value, ".17g")


def _optional_float_text(value: float | None) -> str:
    return "" if value is None else _float_text(value)


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateCGeneralizationReviewError(
            f"could not read JSON {path}: {exc}"
        ) from exc
    if not isinstance(value, Mapping):
        _error(f"JSON root must be an object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                _error(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise KxbtcdCandidateCGeneralizationReviewError(
            f"could not read CSV {path}: {exc}"
        ) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise KxbtcdCandidateCGeneralizationReviewError(
            f"could not hash {path}: {exc}"
        ) from exc
    return digest.hexdigest()


def _clip_market_probability(q: float) -> float:
    if not 0.0 <= q <= 1.0:
        _error(f"q_market outside [0,1]: {q}")
    return min(max(q, 0.001), 0.999)


def _market_logit(q: float) -> float:
    clipped = _clip_market_probability(q)
    return math.log(clipped / (1.0 - clipped))


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _mean(values: Sequence[float]) -> float:
    if not values:
        _error("cannot average an empty sequence")
    return math.fsum(values) / len(values)


def _population_std(values: Sequence[float]) -> float:
    if not values:
        _error("cannot compute standard deviation of an empty sequence")
    mean = _mean(values)
    return math.sqrt(math.fsum((x - mean) ** 2 for x in values) / len(values))


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        _error("cannot compute quantile of an empty sequence")
    if not 0.0 <= probability <= 1.0:
        _error("quantile probability must be in [0,1]")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _trimmed_mean(values: Sequence[float], proportion_each_tail: float = 0.10) -> float:
    if not values:
        _error("cannot compute trimmed mean of an empty sequence")
    ordered = sorted(values)
    trim = int(math.floor(len(ordered) * proportion_each_tail))
    if 2 * trim >= len(ordered):
        _error("trim proportion removed every observation")
    return _mean(ordered[trim : len(ordered) - trim])


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        _error("Pearson correlation requires equal sequences with at least two values")
    lm = _mean(left)
    rm = _mean(right)
    ldev = [x - lm for x in left]
    rdev = [x - rm for x in right]
    denom = math.sqrt(
        math.fsum(x * x for x in ldev) * math.fsum(y * y for y in rdev)
    )
    if denom == 0:
        _error("Pearson correlation is undefined for a zero-variance feature")
    return math.fsum(x * y for x, y in zip(ldev, rdev)) / denom


def _lag1_autocorrelation(values: Sequence[float]) -> float | None:
    if len(values) < 3:
        return None
    left = list(values[:-1])
    right = list(values[1:])
    if _population_std(left) == 0.0 or _population_std(right) == 0.0:
        return None
    return _pearson(left, right)


def positive_lag1_ess_heuristic(unit_count: int, lag1: float | None) -> float | None:
    """Conservative AR(1)-style ESS diagnostic using positive lag-1 dependence only.

    This is not a certified effective sample size.  Negative lag-1 correlation is
    not allowed to inflate the nominal count.
    """
    if unit_count <= 0:
        _error("unit_count must be positive")
    if lag1 is None:
        return None
    if lag1 <= 0:
        return float(unit_count)
    if lag1 >= 1:
        return 1.0
    value = unit_count * (1.0 - lag1) / (1.0 + lag1)
    return min(float(unit_count), max(1.0, value))


def _symmetric_eigenvalues_3x3(matrix: Sequence[Sequence[float]]) -> tuple[float, float, float]:
    """Jacobi eigenvalue iteration for a real symmetric 3x3 matrix."""
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        _error("3x3 eigenvalue helper requires a 3x3 matrix")
    a = [[float(matrix[i][j]) for j in range(3)] for i in range(3)]
    for i in range(3):
        for j in range(3):
            if abs(a[i][j] - a[j][i]) > 1e-12:
                _error("eigenvalue helper requires a symmetric matrix")
    for _ in range(64):
        pairs = ((0, 1), (0, 2), (1, 2))
        p, q = max(pairs, key=lambda pair: abs(a[pair[0]][pair[1]]))
        if abs(a[p][q]) < 1e-14:
            break
        app, aqq, apq = a[p][p], a[q][q], a[p][q]
        tau = (aqq - app) / (2.0 * apq)
        t = math.copysign(1.0, tau) / (abs(tau) + math.sqrt(1.0 + tau * tau))
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c
        for k in range(3):
            if k in (p, q):
                continue
            akp, akq = a[k][p], a[k][q]
            a[k][p] = a[p][k] = c * akp - s * akq
            a[k][q] = a[q][k] = s * akp + c * akq
        a[p][p] = c * c * app - 2.0 * s * c * apq + s * s * aqq
        a[q][q] = s * s * app + 2.0 * s * c * apq + c * c * aqq
        a[p][q] = a[q][p] = 0.0
    return tuple(sorted((a[0][0], a[1][1], a[2][2])))


def _balanced_contiguous_mapping(units: Sequence[str], block_count: int) -> dict[str, int]:
    unique = sorted(set(units))
    if len(unique) < block_count:
        _error("not enough chronology units for requested block count")
    base, remainder = divmod(len(unique), block_count)
    mapping: dict[str, int] = {}
    cursor = 0
    for block in range(block_count):
        count = base + (1 if block < remainder else 0)
        for unit in unique[cursor : cursor + count]:
            mapping[unit] = block
        cursor += count
    if cursor != len(unique):
        _error("balanced block construction did not consume all units")
    return mapping


def protocol_layout_candidates(
    event_week_pairs: Sequence[tuple[str, str]],
    block_counts: Sequence[int] = (6, 7, 8),
) -> tuple[dict[str, str], ...]:
    """Build outcome-blind contiguous block-layout candidates from event/week IDs only."""
    event_to_week: dict[str, str] = {}
    for event, week in event_week_pairs:
        if event in event_to_week and event_to_week[event] != week:
            _error(f"event {event} spans multiple UTC weeks")
        event_to_week[event] = week
    if not event_to_week:
        _error("protocol layout requires at least one event")
    weeks = sorted(set(event_to_week.values()))
    rows: list[dict[str, str]] = []
    for block_count in block_counts:
        mapping = _balanced_contiguous_mapping(weeks, int(block_count))
        week_counts = [
            sum(1 for week in weeks if mapping[week] == block)
            for block in range(block_count)
        ]
        event_counts = [
            sum(1 for week in event_to_week.values() if mapping[week] == block)
            for block in range(block_count)
        ]
        for block in range(block_count):
            block_weeks = [week for week in weeks if mapping[week] == block]
            rows.append(
                {
                    "schema_version": PROTOCOL_LAYOUT_SCHEMA_VERSION,
                    "layout_id": f"{block_count}_contiguous_utc_week_blocks",
                    "block_count": str(block_count),
                    "block": f"B{block}",
                    "week_count": str(week_counts[block]),
                    "event_count": str(event_counts[block]),
                    "first_week": block_weeks[0],
                    "last_week": block_weeks[-1],
                    "outcomes_used_to_construct_layout": "false",
                }
            )
    return tuple(rows)


def raw_space_coefficients(model: FoldModel) -> tuple[float, float, float, float]:
    """Convert stored standardized coefficients to the original feature scale."""
    slopes = tuple(
        beta / std
        for beta, std in zip((model.beta1, model.beta2, model.beta3), model.stds)
    )
    intercept = model.beta0 - math.fsum(
        beta * mean / std
        for beta, mean, std in zip(
            (model.beta1, model.beta2, model.beta3), model.means, model.stds
        )
    )
    return (intercept, slopes[0], slopes[1], slopes[2])


def predict_from_stored_fold(model: FoldModel, q_market: float, spread: float) -> float:
    market_logit = _market_logit(q_market)
    features = (market_logit, spread, market_logit * spread)
    standardized = tuple(
        (feature - mean) / std
        for feature, mean, std in zip(features, model.means, model.stds)
    )
    z = (
        model.beta0
        + model.beta1 * standardized[0]
        + model.beta2 * standardized[1]
        + model.beta3 * standardized[2]
    )
    return _sigmoid(z)


def _validate_cp15_summary(summary: Mapping[str, Any]) -> None:
    if summary.get("candidate_id") != CANDIDATE_ID:
        _error("Checkpoint-15 summary candidate identity mismatch")
    if (
        summary.get("candidate_c_predeclaration_fingerprint")
        != EXPECTED_PREDECLARATION_FINGERPRINT
    ):
        _error("Checkpoint-15 predeclaration fingerprint mismatch")
    if summary.get("week_map_fingerprint") != EXPECTED_WEEK_MAP_FINGERPRINT:
        _error("Checkpoint-15 week-map fingerprint mismatch")
    if str(summary.get("selected_lambda")) != EXPECTED_SELECTED_LAMBDA:
        _error("Checkpoint-15 selected lambda mismatch")
    if int(summary.get("development_event_count", -1)) != EXPECTED_DEVELOPMENT_EVENTS:
        _error("Checkpoint-15 development event count mismatch")
    if int(summary.get("development_row_count", -1)) != EXPECTED_DEVELOPMENT_ROWS:
        _error("Checkpoint-15 development row count mismatch")
    if summary.get("locked_test_outcomes_opened") != 0:
        _error("Checkpoint-15 summary does not preserve the historical zero-terminal-access state")
    if summary.get("locked_test_evaluation_performed") is not False:
        _error("Checkpoint-15 summary unexpectedly indicates terminal evaluation")
    if summary.get("network_requests") != 0:
        _error("Checkpoint-15 development evaluation unexpectedly used network requests")
    if summary.get("execution_enabled") is not False or summary.get("orders_placed") != 0:
        _error("Checkpoint-15 summary violates the read-only boundary")
    event_counts = summary.get("development_event_counts_by_block")
    row_counts = summary.get("development_row_counts_by_block")
    if event_counts != EXPECTED_BLOCK_EVENT_COUNTS:
        _error("Checkpoint-15 block event counts mismatch")
    if row_counts != EXPECTED_BLOCK_ROW_COUNTS:
        _error("Checkpoint-15 block row counts mismatch")


def load_cp15_artifacts(
    analysis_dir: str | Path = CANONICAL_CP15_ANALYSIS_DIR,
    *,
    repository_root: str | Path = ".",
) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]], dict[str, Any]]:
    repo = Path(repository_root).resolve()
    directory = Path(analysis_dir)
    if not directory.is_absolute():
        directory = repo / directory
    paths = {name: directory / filename for name, filename in CP15_FILENAMES.items()}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        _error("missing canonical Checkpoint-15 analysis artifacts: " + ", ".join(missing))

    summary = dict(_load_json(paths["summary"]))
    _validate_cp15_summary(summary)
    tables = {
        name: _read_csv(path)
        for name, path in paths.items()
        if name != "summary"
    }

    selected_fold_scores = [
        row for row in tables["fold_scores"] if row.get("lambda") == EXPECTED_SELECTED_LAMBDA
    ]
    if len(selected_fold_scores) != 4:
        _error("expected four selected-lambda Checkpoint-15 fold-score rows")
    if tuple(sorted(row["score_block"] for row in selected_fold_scores)) != EXPECTED_SCORE_BLOCKS:
        _error("selected-lambda fold scores do not cover B1-B4 exactly")

    selected_coefficients = [
        row for row in tables["coefficients"] if row.get("lambda") == EXPECTED_SELECTED_LAMBDA
    ]
    if len(selected_coefficients) != 4:
        _error("expected four selected-lambda Checkpoint-15 coefficient rows")

    predictions = tables["predictions"]
    if len(predictions) != EXPECTED_OOF_ROWS:
        _error(f"Checkpoint-15 OOF row count changed: {len(predictions)} != {EXPECTED_OOF_ROWS}")
    events = {row.get("event_ticker") for row in predictions}
    if len(events) != EXPECTED_OOF_EVENTS:
        _error(f"Checkpoint-15 OOF event count changed: {len(events)} != {EXPECTED_OOF_EVENTS}")
    if {row.get("score_block") for row in predictions} != set(EXPECTED_SCORE_BLOCKS):
        _error("Checkpoint-15 OOF predictions do not cover B1-B4 exactly")
    if any(row.get("selected_lambda") != EXPECTED_SELECTED_LAMBDA for row in predictions):
        _error("Checkpoint-15 OOF predictions contain a non-selected lambda")
    state_ids = [row.get("state_id") for row in predictions]
    if len(state_ids) != len(set(state_ids)):
        _error("Checkpoint-15 OOF predictions contain duplicate state IDs")

    source = {
        "analysis_dir": str(directory),
        "artifact_sha256": {name: _sha256(path) for name, path in paths.items()},
    }
    return summary, tables, source


def _load_development_context(
    *,
    repository_root: str | Path,
) -> tuple[tuple[DevelopmentContextRow, ...], dict[str, Any]]:
    """Load canonical CP13 development-only context; imports are intentionally lazy."""
    try:
        from .kxbtcd_candidate_b_failure_analysis import (
            load_canonical_development_predictions,
        )
        from .kxbtcd_candidate_c_development import load_and_validate_frozen_week_map
    except ImportError as exc:
        raise KxbtcdCandidateCGeneralizationReviewError(
            f"could not import canonical development loaders: {exc}"
        ) from exc

    predictions, provenance = load_canonical_development_predictions(repository_root)
    if provenance.get("locked_test_outcomes_opened") != 0:
        _error("CP13 development provenance does not preserve its historical terminal firewall")
    if provenance.get("network_requests") != 0:
        _error("canonical CP13 development context unexpectedly reports network use")
    week_mapping, week_document = load_and_validate_frozen_week_map(
        repository_root=repository_root
    )
    if week_document.get("week_map_fingerprint") != EXPECTED_WEEK_MAP_FINGERPRINT:
        _error("tracked week map fingerprint changed")

    rows: list[DevelopmentContextRow] = []
    seen: set[str] = set()
    for prediction in predictions:
        if prediction.partition not in {"train", "validation"}:
            _error(f"refusing non-development CP13 partition {prediction.partition!r}")
        if prediction.state_id in seen:
            _error(f"duplicate CP13 development state ID: {prediction.state_id}")
        seen.add(prediction.state_id)
        if prediction.utc_week_start not in week_mapping:
            _error(f"development row uses an unknown frozen week: {prediction.utc_week_start}")
        q = float(prediction.q_market)
        spread = float(prediction.spread)
        logit = _market_logit(q)
        rows.append(
            DevelopmentContextRow(
                state_id=prediction.state_id,
                event_ticker=prediction.event_ticker,
                market_ticker=prediction.market_ticker,
                utc_week_start=prediction.utc_week_start,
                block=f"B{int(week_mapping[prediction.utc_week_start])}",
                q_market=q,
                spread=spread,
                market_logit=logit,
                market_logit_x_spread=logit * spread,
            )
        )
    if len(rows) != EXPECTED_DEVELOPMENT_ROWS:
        _error("canonical CP13 development context row count changed")
    if len({row.event_ticker for row in rows}) != EXPECTED_DEVELOPMENT_EVENTS:
        _error("canonical CP13 development context event count changed")
    return tuple(rows), dict(provenance)


def _parse_fold_models(coefficient_rows: Sequence[Mapping[str, str]]) -> tuple[FoldModel, ...]:
    selected = [row for row in coefficient_rows if row.get("lambda") == EXPECTED_SELECTED_LAMBDA]
    models: list[FoldModel] = []
    for row in selected:
        fit_blocks = tuple(part for part in row["fit_blocks"].split("+") if part)
        model = FoldModel(
            fold=int(row["fold"]),
            fit_blocks=fit_blocks,
            score_block=row["score_block"],
            beta0=_float(row["beta0"], "beta0"),
            beta1=_float(row["beta1_market_logit_z"], "beta1_market_logit_z"),
            beta2=_float(row["beta2_spread_z"], "beta2_spread_z"),
            beta3=_float(
                row["beta3_market_logit_x_spread_z"],
                "beta3_market_logit_x_spread_z",
            ),
            means=(
                _float(row["mean_market_logit"], "mean_market_logit"),
                _float(row["mean_spread"], "mean_spread"),
                _float(
                    row["mean_market_logit_x_spread"],
                    "mean_market_logit_x_spread",
                ),
            ),
            stds=(
                _float(row["std_market_logit"], "std_market_logit"),
                _float(row["std_spread"], "std_spread"),
                _float(
                    row["std_market_logit_x_spread"],
                    "std_market_logit_x_spread",
                ),
            ),
        )
        if any(std <= 0 for std in model.stds):
            _error(f"fold {model.fold} has a non-positive stored feature standard deviation")
        models.append(model)
    models.sort(key=lambda model: model.fold)
    if [model.fold for model in models] != [1, 2, 3, 4]:
        _error("stored selected-lambda models do not contain folds 1-4 exactly")
    if [model.score_block for model in models] != list(EXPECTED_SCORE_BLOCKS):
        _error("stored selected-lambda models have unexpected score-block ordering")
    return tuple(models)


def _join_oof_rows(
    prediction_rows: Sequence[Mapping[str, str]],
    context_rows: Sequence[DevelopmentContextRow],
) -> tuple[OofRow, ...]:
    context = {row.state_id: row for row in context_rows}
    joined: list[OofRow] = []
    for index, row in enumerate(prediction_rows):
        state_id = _text(row.get("state_id"), f"prediction[{index}].state_id")
        source = context.get(state_id)
        if source is None:
            _error(f"OOF state is absent from canonical development context: {state_id}")
        for field, expected in (
            ("event_ticker", source.event_ticker),
            ("market_ticker", source.market_ticker),
            ("utc_week_start", source.utc_week_start),
            ("score_block", source.block),
        ):
            if row.get(field) != expected:
                _error(f"OOF/context mismatch for {state_id}.{field}")
        q = _float(row.get("q_market"), f"prediction[{index}].q_market")
        if q != source.q_market:
            _error(f"OOF/context q_market mismatch for {state_id}")
        outcome = int(_text(row.get("outcome"), f"prediction[{index}].outcome"))
        if outcome not in {0, 1}:
            _error(f"OOF outcome must be binary for {state_id}")
        joined.append(
            OofRow(
                state_id=state_id,
                event_ticker=source.event_ticker,
                market_ticker=source.market_ticker,
                utc_week_start=source.utc_week_start,
                block=source.block,
                outcome=outcome,
                q_market=q,
                spread=source.spread,
                candidate_probability=_float(
                    row.get("candidate_c_probability"),
                    f"prediction[{index}].candidate_probability",
                ),
                raw_log_loss=_float(row.get("raw_log_loss"), "raw_log_loss"),
                candidate_log_loss=_float(
                    row.get("candidate_c_log_loss"), "candidate_c_log_loss"
                ),
                raw_brier=_float(row.get("raw_brier"), "raw_brier"),
                candidate_brier=_float(
                    row.get("candidate_c_brier"), "candidate_c_brier"
                ),
            )
        )
    return tuple(joined)


def aggregate_event_metrics(rows: Sequence[OofRow]) -> tuple[EventMetric, ...]:
    grouped: dict[str, list[OofRow]] = {}
    for row in rows:
        grouped.setdefault(row.event_ticker, []).append(row)
    output: list[EventMetric] = []
    for event in sorted(grouped):
        event_rows = grouped[event]
        blocks = {row.block for row in event_rows}
        weeks = {row.utc_week_start for row in event_rows}
        if len(blocks) != 1 or len(weeks) != 1:
            _error(f"OOF event {event} spans multiple blocks/weeks")
        raw_ll = _mean([row.raw_log_loss for row in event_rows])
        cand_ll = _mean([row.candidate_log_loss for row in event_rows])
        raw_br = _mean([row.raw_brier for row in event_rows])
        cand_br = _mean([row.candidate_brier for row in event_rows])
        output.append(
            EventMetric(
                event_ticker=event,
                block=next(iter(blocks)),
                utc_week_start=next(iter(weeks)),
                row_count=len(event_rows),
                raw_log_loss=raw_ll,
                candidate_log_loss=cand_ll,
                delta_log_loss=raw_ll - cand_ll,
                raw_brier=raw_br,
                candidate_brier=cand_br,
                delta_brier=raw_br - cand_br,
            )
        )
    return tuple(output)


def _block_rows(events: Sequence[EventMetric]) -> tuple[dict[str, str], ...]:
    positive_total = math.fsum(max(event.delta_log_loss, 0.0) for event in events)
    rows: list[dict[str, str]] = []
    for block in EXPECTED_SCORE_BLOCKS:
        selected = [event for event in events if event.block == block]
        if not selected:
            _error(f"no event metrics for {block}")
        raw_ll = _mean([event.raw_log_loss for event in selected])
        cand_ll = _mean([event.candidate_log_loss for event in selected])
        raw_br = _mean([event.raw_brier for event in selected])
        cand_br = _mean([event.candidate_brier for event in selected])
        positive = math.fsum(max(event.delta_log_loss, 0.0) for event in selected)
        rows.append(
            {
                "schema_version": BLOCK_SCHEMA_VERSION,
                "block": block,
                "event_count": str(len(selected)),
                "row_count": str(sum(event.row_count for event in selected)),
                "raw_event_weighted_log_loss": _float_text(raw_ll),
                "candidate_c_event_weighted_log_loss": _float_text(cand_ll),
                "delta_log_loss_raw_minus_candidate_c": _float_text(raw_ll - cand_ll),
                "raw_event_weighted_brier": _float_text(raw_br),
                "candidate_c_event_weighted_brier": _float_text(cand_br),
                "delta_brier_raw_minus_candidate_c": _float_text(raw_br - cand_br),
                "mean_event_delta_log_loss": _float_text(
                    _mean([event.delta_log_loss for event in selected])
                ),
                "median_event_delta_log_loss": _float_text(
                    statistics.median(event.delta_log_loss for event in selected)
                ),
                "gross_positive_improvement_share": _float_text(
                    positive / positive_total if positive_total > 0 else 0.0
                ),
            }
        )
    return tuple(rows)


def _event_concentration_rows(events: Sequence[EventMetric]) -> tuple[dict[str, str], ...]:
    ordered = sorted(events, key=lambda event: (-event.delta_log_loss, event.event_ticker))
    gross_positive = math.fsum(max(event.delta_log_loss, 0.0) for event in events)
    cumulative_positive = 0.0
    rows: list[dict[str, str]] = []
    for rank, event in enumerate(ordered, start=1):
        positive = max(event.delta_log_loss, 0.0)
        cumulative_positive += positive
        rows.append(
            {
                "schema_version": EVENT_SCHEMA_VERSION,
                "rank_by_delta_log_loss": str(rank),
                "event_ticker": event.event_ticker,
                "block": event.block,
                "utc_week_start": event.utc_week_start,
                "row_count": str(event.row_count),
                "raw_log_loss": _float_text(event.raw_log_loss),
                "candidate_c_log_loss": _float_text(event.candidate_log_loss),
                "delta_log_loss_raw_minus_candidate_c": _float_text(event.delta_log_loss),
                "raw_brier": _float_text(event.raw_brier),
                "candidate_c_brier": _float_text(event.candidate_brier),
                "delta_brier_raw_minus_candidate_c": _float_text(event.delta_brier),
                "gross_positive_improvement_share": _float_text(
                    positive / gross_positive if gross_positive > 0 else 0.0
                ),
                "cumulative_gross_positive_improvement_share": _float_text(
                    cumulative_positive / gross_positive if gross_positive > 0 else 0.0
                ),
            }
        )
    return tuple(rows)


def _week_rows(events: Sequence[EventMetric]) -> tuple[dict[str, str], ...]:
    grouped: dict[str, list[EventMetric]] = {}
    for event in events:
        grouped.setdefault(event.utc_week_start, []).append(event)
    total_events = len(events)
    rows: list[dict[str, str]] = []
    for week in sorted(grouped):
        selected = grouped[week]
        blocks = {event.block for event in selected}
        if len(blocks) != 1:
            _error(f"week {week} spans multiple frozen score blocks")
        raw_ll = _mean([event.raw_log_loss for event in selected])
        cand_ll = _mean([event.candidate_log_loss for event in selected])
        raw_br = _mean([event.raw_brier for event in selected])
        cand_br = _mean([event.candidate_brier for event in selected])
        sum_delta = math.fsum(event.delta_log_loss for event in selected)
        rows.append(
            {
                "schema_version": WEEK_SCHEMA_VERSION,
                "utc_week_start": week,
                "block": next(iter(blocks)),
                "event_count": str(len(selected)),
                "row_count": str(sum(event.row_count for event in selected)),
                "raw_event_weighted_log_loss": _float_text(raw_ll),
                "candidate_c_event_weighted_log_loss": _float_text(cand_ll),
                "delta_log_loss_raw_minus_candidate_c": _float_text(raw_ll - cand_ll),
                "median_event_delta_log_loss": _float_text(
                    statistics.median(event.delta_log_loss for event in selected)
                ),
                "raw_event_weighted_brier": _float_text(raw_br),
                "candidate_c_event_weighted_brier": _float_text(cand_br),
                "delta_brier_raw_minus_candidate_c": _float_text(raw_br - cand_br),
                "contribution_to_pooled_event_weighted_delta": _float_text(
                    sum_delta / total_events
                ),
            }
        )
    return tuple(rows)


def _leave_one_block_out_rows(events: Sequence[EventMetric]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for excluded in EXPECTED_SCORE_BLOCKS:
        remaining = [event for event in events if event.block != excluded]
        rows.append(
            {
                "schema_version": LEAVE_ONE_BLOCK_SCHEMA_VERSION,
                "excluded_block": excluded,
                "remaining_event_count": str(len(remaining)),
                "delta_log_loss_raw_minus_candidate_c": _float_text(
                    _mean([event.delta_log_loss for event in remaining])
                ),
                "delta_brier_raw_minus_candidate_c": _float_text(
                    _mean([event.delta_brier for event in remaining])
                ),
            }
        )
    return tuple(rows)


def _coefficient_rows(models: Sequence[FoldModel]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for model in models:
        raw = raw_space_coefficients(model)
        rows.append(
            {
                "schema_version": COEFFICIENT_SCHEMA_VERSION,
                "fold": str(model.fold),
                "fit_blocks": "+".join(model.fit_blocks),
                "score_block": model.score_block,
                "beta0_standardized": _float_text(model.beta0),
                "beta1_market_logit_z": _float_text(model.beta1),
                "beta2_spread_z": _float_text(model.beta2),
                "beta3_market_logit_x_spread_z": _float_text(model.beta3),
                "raw_space_intercept": _float_text(raw[0]),
                "raw_space_market_logit_slope": _float_text(raw[1]),
                "raw_space_market_logit_excess_vs_raw_midpoint": _float_text(raw[1] - 1.0),
                "raw_space_spread_slope": _float_text(raw[2]),
                "raw_space_interaction_slope": _float_text(raw[3]),
            }
        )
    return tuple(rows)


def _fixed_grid_rows(
    models: Sequence[FoldModel],
    context_rows: Sequence[DevelopmentContextRow],
) -> tuple[dict[str, str], ...]:
    quantiles = (0.10, 0.25, 0.50, 0.75, 0.90)
    q_values = [_quantile([row.q_market for row in context_rows], q) for q in quantiles]
    spread_values = [_quantile([row.spread for row in context_rows], q) for q in quantiles]
    rows: list[dict[str, str]] = []
    for q_index, q_value in enumerate(q_values):
        for spread_index, spread in enumerate(spread_values):
            probabilities = [
                predict_from_stored_fold(model, q_value, spread) for model in models
            ]
            corrections = [probability - q_value for probability in probabilities]
            if all(value > 0 for value in corrections):
                consistency = "all_positive"
            elif all(value < 0 for value in corrections):
                consistency = "all_negative"
            elif all(value == 0 for value in corrections):
                consistency = "all_zero"
            else:
                consistency = "mixed"
            rows.append(
                {
                    "schema_version": GRID_SCHEMA_VERSION,
                    "q_quantile": _float_text(quantiles[q_index]),
                    "spread_quantile": _float_text(quantiles[spread_index]),
                    "q_market": _float_text(q_value),
                    "spread": _float_text(spread),
                    "raw_midpoint_probability": _float_text(q_value),
                    "candidate_c_fold_mean_probability": _float_text(_mean(probabilities)),
                    "candidate_c_fold_min_probability": _float_text(min(probabilities)),
                    "candidate_c_fold_max_probability": _float_text(max(probabilities)),
                    "candidate_c_fold_probability_range": _float_text(
                        max(probabilities) - min(probabilities)
                    ),
                    "candidate_c_fold_probability_std": _float_text(
                        _population_std(probabilities)
                    ),
                    "mean_probability_correction_vs_raw": _float_text(_mean(corrections)),
                    "correction_sign_consistency": consistency,
                    "grid_values_derived_from_development_features_only": "true",
                }
            )
    return tuple(rows)


def _bin_index(value: float, quartiles: tuple[float, float, float]) -> int:
    if value <= quartiles[0]:
        return 0
    if value <= quartiles[1]:
        return 1
    if value <= quartiles[2]:
        return 2
    return 3


def _correction_grid_rows(
    oof_rows: Sequence[OofRow],
    context_rows: Sequence[DevelopmentContextRow],
) -> tuple[dict[str, str], ...]:
    q_quartiles = tuple(
        _quantile([row.q_market for row in context_rows], p)
        for p in (0.25, 0.50, 0.75)
    )
    spread_quartiles = tuple(
        _quantile([row.spread for row in context_rows], p)
        for p in (0.25, 0.50, 0.75)
    )
    grouped: dict[tuple[int, int], list[OofRow]] = {}
    for row in oof_rows:
        grouped.setdefault(
            (_bin_index(row.q_market, q_quartiles), _bin_index(row.spread, spread_quartiles)),
            [],
        ).append(row)

    rows: list[dict[str, str]] = []
    for (q_bin, spread_bin), selected in sorted(grouped.items()):
        by_event: dict[str, list[OofRow]] = {}
        for row in selected:
            by_event.setdefault(row.event_ticker, []).append(row)
        event_mean_correction = [
            _mean([row.candidate_probability - row.q_market for row in event_rows])
            for event_rows in by_event.values()
        ]
        event_mean_confidence_change = [
            _mean(
                [
                    abs(row.candidate_probability - 0.5) - abs(row.q_market - 0.5)
                    for row in event_rows
                ]
            )
            for event_rows in by_event.values()
        ]
        rows.append(
            {
                "schema_version": CORRECTION_GRID_SCHEMA_VERSION,
                "q_market_quartile_bin": f"Q{q_bin + 1}",
                "spread_quartile_bin": f"Q{spread_bin + 1}",
                "row_count": str(len(selected)),
                "event_count": str(len(by_event)),
                "event_weighted_mean_probability_correction": _float_text(
                    _mean(event_mean_correction)
                ),
                "event_weighted_mean_confidence_change": _float_text(
                    _mean(event_mean_confidence_change)
                ),
                "bin_boundaries_derived_from_development_features_only": "true",
                "diagnostic_only_not_successor_feature_definition": "true",
            }
        )
    return tuple(rows)


def _conditioning_rows(
    models: Sequence[FoldModel],
    context_rows: Sequence[DevelopmentContextRow],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for model in models:
        selected = [row for row in context_rows if row.block in set(model.fit_blocks)]
        x1 = [row.market_logit for row in selected]
        x2 = [row.spread for row in selected]
        x3 = [row.market_logit_x_spread for row in selected]
        correlations = (
            _pearson(x1, x2),
            _pearson(x1, x3),
            _pearson(x2, x3),
        )
        matrix = (
            (1.0, correlations[0], correlations[1]),
            (correlations[0], 1.0, correlations[2]),
            (correlations[1], correlations[2], 1.0),
        )
        eigenvalues = _symmetric_eigenvalues_3x3(matrix)
        condition = math.inf if eigenvalues[0] <= 1e-12 else eigenvalues[-1] / eigenvalues[0]
        if not math.isfinite(condition):
            condition_text = "inf"
        else:
            condition_text = _float_text(condition)

        recomputed_means = (_mean(x1), _mean(x2), _mean(x3))
        recomputed_stds = (_population_std(x1), _population_std(x2), _population_std(x3))
        max_mean_error = max(
            abs(left - right) for left, right in zip(recomputed_means, model.means)
        )
        max_std_error = max(
            abs(left - right) for left, right in zip(recomputed_stds, model.stds)
        )
        if max_mean_error > 1e-10 or max_std_error > 1e-10:
            _error(
                f"fold {model.fold} stored scaler does not match canonical development fit rows"
            )
        rows.append(
            {
                "schema_version": CONDITIONING_SCHEMA_VERSION,
                "fold": str(model.fold),
                "fit_blocks": "+".join(model.fit_blocks),
                "fit_event_count": str(len({row.event_ticker for row in selected})),
                "fit_row_count": str(len(selected)),
                "corr_market_logit_spread": _float_text(correlations[0]),
                "corr_market_logit_interaction": _float_text(correlations[1]),
                "corr_spread_interaction": _float_text(correlations[2]),
                "max_abs_off_diagonal_correlation": _float_text(
                    max(abs(value) for value in correlations)
                ),
                "correlation_matrix_min_eigenvalue": _float_text(eigenvalues[0]),
                "correlation_matrix_max_eigenvalue": _float_text(eigenvalues[-1]),
                "correlation_matrix_condition_number": condition_text,
                "stored_scaler_max_abs_mean_reconciliation_error": _float_text(
                    max_mean_error
                ),
                "stored_scaler_max_abs_std_reconciliation_error": _float_text(
                    max_std_error
                ),
            }
        )
    return tuple(rows)


def _lambda_rows(lambda_score_rows: Sequence[Mapping[str, str]]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    observed: set[str] = set()
    for source in lambda_score_rows:
        value = _text(source.get("lambda"), "lambda")
        observed.add(value)
        raw_ll = _float(source.get("raw_event_weighted_log_loss"), "raw log loss")
        candidate_ll = _float(
            source.get("candidate_event_weighted_log_loss"), "candidate log loss"
        )
        raw_br = _float(source.get("raw_event_weighted_brier"), "raw brier")
        candidate_br = _float(
            source.get("candidate_event_weighted_brier"), "candidate brier"
        )
        rows.append(
            {
                "schema_version": LAMBDA_SCHEMA_VERSION,
                "lambda": value,
                "selected": "true" if value == EXPECTED_SELECTED_LAMBDA else "false",
                "raw_event_weighted_log_loss": _float_text(raw_ll),
                "candidate_c_event_weighted_log_loss": _float_text(candidate_ll),
                "delta_log_loss_raw_minus_candidate_c": _float_text(raw_ll - candidate_ll),
                "raw_event_weighted_brier": _float_text(raw_br),
                "candidate_c_event_weighted_brier": _float_text(candidate_br),
                "delta_brier_raw_minus_candidate_c": _float_text(raw_br - candidate_br),
                "strictly_beats_raw_log_loss": "true" if candidate_ll < raw_ll else "false",
            }
        )
    if observed != {"0.01", "0.1", "1", "10"}:
        _error(f"unexpected Checkpoint-15 lambda set: {sorted(observed)}")
    rows.sort(key=lambda row: float(row["lambda"]))
    return tuple(rows)


def _sharpening_summary(oof_rows: Sequence[OofRow]) -> dict[str, float]:
    by_event: dict[str, list[OofRow]] = {}
    for row in oof_rows:
        by_event.setdefault(row.event_ticker, []).append(row)

    event_sharper_fraction: list[float] = []
    event_confidence_change: list[float] = []
    event_abs_adjustment: list[float] = []
    event_cross_fraction: list[float] = []
    for event_rows in by_event.values():
        event_sharper_fraction.append(
            _mean(
                [
                    1.0
                    if abs(row.candidate_probability - 0.5) > abs(row.q_market - 0.5)
                    else 0.0
                    for row in event_rows
                ]
            )
        )
        event_confidence_change.append(
            _mean(
                [
                    abs(row.candidate_probability - 0.5) - abs(row.q_market - 0.5)
                    for row in event_rows
                ]
            )
        )
        event_abs_adjustment.append(
            _mean(
                [abs(row.candidate_probability - row.q_market) for row in event_rows]
            )
        )
        event_cross_fraction.append(
            _mean(
                [
                    1.0
                    if (row.candidate_probability - 0.5) * (row.q_market - 0.5) < 0.0
                    else 0.0
                    for row in event_rows
                ]
            )
        )
    return {
        "event_weighted_fraction_rows_sharpened": _mean(event_sharper_fraction),
        "event_weighted_mean_confidence_change": _mean(event_confidence_change),
        "event_weighted_mean_abs_probability_adjustment": _mean(event_abs_adjustment),
        "event_weighted_fraction_rows_crossing_0_5": _mean(event_cross_fraction),
    }


def analyze_generalization_risk(
    *,
    summary: Mapping[str, Any],
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    source: Mapping[str, Any],
    context_rows: Sequence[DevelopmentContextRow],
    development_provenance: Mapping[str, Any],
) -> ReviewResult:
    _validate_cp15_summary(summary)
    oof_rows = _join_oof_rows(tables["predictions"], context_rows)
    events = aggregate_event_metrics(oof_rows)
    if len(events) != EXPECTED_OOF_EVENTS:
        _error("event aggregation did not reproduce the 184 OOF events")

    pooled_delta = _mean([event.delta_log_loss for event in events])
    pooled_brier_delta = _mean([event.delta_brier for event in events])
    if abs(
        pooled_delta - _float(summary["delta_log_loss_raw_minus_candidate_c"], "summary delta")
    ) > 1e-12:
        _error("OOF event aggregation does not reproduce the frozen pooled log-loss delta")
    if abs(
        pooled_brier_delta - _float(summary["delta_brier_raw_minus_candidate_c"], "summary brier delta")
    ) > 1e-12:
        _error("OOF event aggregation does not reproduce the frozen pooled Brier delta")

    models = _parse_fold_models(tables["coefficients"])
    block_rows = _block_rows(events)
    event_rows = _event_concentration_rows(events)
    week_rows = _week_rows(events)
    leave_rows = _leave_one_block_out_rows(events)
    coefficient_rows = _coefficient_rows(models)
    fixed_grid_rows = _fixed_grid_rows(models, context_rows)
    correction_grid_rows = _correction_grid_rows(oof_rows, context_rows)
    conditioning_rows = _conditioning_rows(models, context_rows)
    lambda_rows = _lambda_rows(tables["lambda_scores"])
    event_week_pairs = sorted(
        {
            (row.event_ticker, row.utc_week_start)
            for row in context_rows
        }
    )
    protocol_rows = protocol_layout_candidates(event_week_pairs)

    deltas = [event.delta_log_loss for event in events]
    positive_events = sorted(
        [event.delta_log_loss for event in events if event.delta_log_loss > 0],
        reverse=True,
    )
    positive_sum = math.fsum(positive_events)
    top_share = {
        f"top_{k}_gross_positive_improvement_share": (
            math.fsum(positive_events[:k]) / positive_sum if positive_sum > 0 else 0.0
        )
        for k in (1, 5, 10)
    }

    weekly_deltas = [
        _float(row["delta_log_loss_raw_minus_candidate_c"], "week delta")
        for row in week_rows
    ]
    lag1 = _lag1_autocorrelation(weekly_deltas)
    week_ess = positive_lag1_ess_heuristic(len(weekly_deltas), lag1)

    raw_coefficients = [raw_space_coefficients(model) for model in models]
    raw_parameter_names = (
        "intercept",
        "market_logit_slope",
        "spread_slope",
        "interaction_slope",
    )
    coefficient_stability: dict[str, dict[str, float]] = {}
    for index, name in enumerate(raw_parameter_names):
        values = [coefficient[index] for coefficient in raw_coefficients]
        coefficient_stability[name] = {
            "min": min(values),
            "max": max(values),
            "range": max(values) - min(values),
            "mean": _mean(values),
            "population_std": _population_std(values),
        }

    grid_ranges = [
        _float(row["candidate_c_fold_probability_range"], "grid range")
        for row in fixed_grid_rows
    ]
    grid_mixed = sum(
        1 for row in fixed_grid_rows if row["correction_sign_consistency"] == "mixed"
    )
    sharpening = _sharpening_summary(oof_rows)

    layout_summaries: dict[str, dict[str, int]] = {}
    for row in protocol_rows:
        layout = row["layout_id"]
        count = int(row["event_count"])
        current = layout_summaries.setdefault(
            layout, {"min_events_per_block": count, "max_events_per_block": count}
        )
        current["min_events_per_block"] = min(current["min_events_per_block"], count)
        current["max_events_per_block"] = max(current["max_events_per_block"], count)

    lambda_improves_count = sum(
        1 for row in lambda_rows if row["strictly_beats_raw_log_loss"] == "true"
    )

    review_summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "review_scope": "development_only",
        "candidate_id": CANDIDATE_ID,
        "candidate_c_predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "week_map_fingerprint": EXPECTED_WEEK_MAP_FINGERPRINT,
        "selected_lambda": EXPECTED_SELECTED_LAMBDA,
        "development_event_count": EXPECTED_DEVELOPMENT_EVENTS,
        "development_row_count": EXPECTED_DEVELOPMENT_ROWS,
        "oof_event_count": EXPECTED_OOF_EVENTS,
        "oof_row_count": EXPECTED_OOF_ROWS,
        "pooled_delta_log_loss_raw_minus_candidate_c": pooled_delta,
        "pooled_delta_brier_raw_minus_candidate_c": pooled_brier_delta,
        "event_delta_distribution": {
            "min": min(deltas),
            "p10": _quantile(deltas, 0.10),
            "p25": _quantile(deltas, 0.25),
            "median": statistics.median(deltas),
            "p75": _quantile(deltas, 0.75),
            "p90": _quantile(deltas, 0.90),
            "max": max(deltas),
            "mean": _mean(deltas),
            "trimmed_mean_10pct_each_tail": _trimmed_mean(deltas, 0.10),
        },
        "improvement_concentration": top_share,
        "weekly_temporal_dependence_diagnostic": {
            "scored_week_count": len(weekly_deltas),
            "lag1_autocorrelation_of_weekly_mean_event_delta": lag1,
            "positive_lag1_ar1_ess_heuristic": week_ess,
            "ess_is_certified": False,
        },
        "coefficient_raw_space_stability": coefficient_stability,
        "prediction_grid_stability": {
            "development_feature_quantile_grid_cells": len(fixed_grid_rows),
            "max_fold_probability_range": max(grid_ranges),
            "median_fold_probability_range": statistics.median(grid_ranges),
            "cells_with_mixed_correction_sign": grid_mixed,
        },
        "sharpening_diagnostic": sharpening,
        "regularization_diagnostic": {
            "frozen_lambda_count": len(lambda_rows),
            "lambda_values_strictly_beating_raw": lambda_improves_count,
            "selected_lambda_is_weakest_frozen_penalty": True,
        },
        "protocol_risk_facts": {
            "candidate_c_feature_hypothesis_was_discovered_from_the_same_231_exposed_development_events": True,
            "cp15_coefficients_were_rolling_origin_out_of_fold": True,
            "cp15_model_family_was_not_untouched_with_respect_to_later_score_blocks": True,
            "cp15_same_oof_blocks_used_for_lambda_selection_and_selected_lambda_advancement_check": True,
            "raw_rows_are_not_treated_as_iid_trials": True,
        },
        "outcome_blind_successor_layout_candidates": layout_summaries,
        "successor_model_fit_performed": False,
        "successor_hyperparameter_search_performed": False,
        "candidate_c_refit_performed": False,
        "terminal_result_artifact_loaded": False,
        "terminal_rows_loaded": 0,
        "terminal_labels_loaded": 0,
        "terminal_features_loaded": 0,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "source_cp15": dict(source),
        "source_cp13_development_provenance": dict(development_provenance),
        "interpretation_boundary": (
            "Diagnostic evidence only. Results may motivate a separately predeclared successor, "
            "but this review does not select, fit, or advance a successor candidate."
        ),
    }

    return ReviewResult(
        summary=review_summary,
        block_rows=block_rows,
        event_rows=event_rows,
        week_rows=week_rows,
        leave_one_block_out_rows=leave_rows,
        coefficient_rows=coefficient_rows,
        fixed_grid_rows=fixed_grid_rows,
        correction_grid_rows=correction_grid_rows,
        conditioning_rows=conditioning_rows,
        lambda_rows=lambda_rows,
        protocol_layout_rows=protocol_rows,
    )


def load_and_analyze_generalization_risk(
    *,
    repository_root: str | Path = ".",
    analysis_dir: str | Path = CANONICAL_CP15_ANALYSIS_DIR,
) -> ReviewResult:
    summary, tables, source = load_cp15_artifacts(
        analysis_dir, repository_root=repository_root
    )
    context_rows, development_provenance = _load_development_context(
        repository_root=repository_root
    )
    return analyze_generalization_risk(
        summary=summary,
        tables=tables,
        source=source,
        context_rows=context_rows,
        development_provenance=development_provenance,
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    if not rows:
        _error(f"refusing to write empty review CSV: {path.name}")
    fields = list(rows[0].keys())
    for index, row in enumerate(rows):
        if list(row.keys()) != fields:
            _error(f"row {index} schema/order mismatch for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_generalization_review(
    output_dir: str | Path,
    *,
    review: ReviewResult,
) -> dict[str, Path]:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    paths = {
        "summary": target / "candidate_c_generalization_review_summary.json",
        "block_stability": target / "candidate_c_block_stability.csv",
        "event_concentration": target / "candidate_c_event_concentration.csv",
        "week_stability": target / "candidate_c_week_stability.csv",
        "leave_one_block_out": target / "candidate_c_leave_one_block_out.csv",
        "coefficient_stability": target / "candidate_c_coefficient_stability.csv",
        "prediction_stability_grid": target / "candidate_c_prediction_stability_grid.csv",
        "correction_grid": target / "candidate_c_correction_grid.csv",
        "feature_conditioning": target / "candidate_c_feature_conditioning.csv",
        "lambda_stability": target / "candidate_c_lambda_stability.csv",
        "protocol_layout_candidates": target / "successor_protocol_layout_candidates.csv",
    }
    paths["summary"].write_text(
        json.dumps(review.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(paths["block_stability"], review.block_rows)
    _write_csv(paths["event_concentration"], review.event_rows)
    _write_csv(paths["week_stability"], review.week_rows)
    _write_csv(paths["leave_one_block_out"], review.leave_one_block_out_rows)
    _write_csv(paths["coefficient_stability"], review.coefficient_rows)
    _write_csv(paths["prediction_stability_grid"], review.fixed_grid_rows)
    _write_csv(paths["correction_grid"], review.correction_grid_rows)
    _write_csv(paths["feature_conditioning"], review.conditioning_rows)
    _write_csv(paths["lambda_stability"], review.lambda_rows)
    _write_csv(paths["protocol_layout_candidates"], review.protocol_layout_rows)
    return paths
