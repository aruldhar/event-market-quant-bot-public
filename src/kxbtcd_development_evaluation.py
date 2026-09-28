"""Development-only outcome collection and scoring for KXBTCD baseline v1.

This module enforces the pre-outcome freeze before materializing labels. It may
request finalized Kalshi results for the frozen development partition only. The
holdout partition is never included in the request set.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


from .kxbtcd_baseline_design import (
    EXPERIMENT_ID,
    PROBE_ROLES,
    TIME_BANDS,
    KxbtcdBaselineDesignError,
    binary_log_loss,
    brier_score,
    design_fingerprint,
    project_nonincreasing_l2,
)


class KxbtcdDevelopmentEvaluationError(RuntimeError):
    """Raised when development-only outcome or scoring invariants fail."""


OUTCOME_SCHEMA_VERSION = "kxbtcd_development_outcome.v1"
PREDICTION_SCHEMA_VERSION = "kxbtcd_development_prediction_score.v1"
CLUSTER_SCORE_SCHEMA_VERSION = "kxbtcd_development_cluster_score.v1"
BAND_SCORE_SCHEMA_VERSION = "kxbtcd_development_band_score.v1"
SUMMARY_SCHEMA_VERSION = "kxbtcd_development_summary.v1"

EXPECTED_DEVELOPMENT_CLUSTERS = 8
EXPECTED_HOLDOUT_CLUSTERS = 4
EXPECTED_PROBES_PER_CLUSTER = 3
EXPECTED_BANDS_PER_CLUSTER = 3
EXPECTED_DEVELOPMENT_TICKERS = (
    EXPECTED_DEVELOPMENT_CLUSTERS * EXPECTED_PROBES_PER_CLUSTER
)
EXPECTED_DEVELOPMENT_PREDICTIONS = (
    EXPECTED_DEVELOPMENT_CLUSTERS
    * EXPECTED_PROBES_PER_CLUSTER
    * EXPECTED_BANDS_PER_CLUSTER
)

OUTCOME_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "preoutcome_receipt_sha256",
    "event_ticker",
    "source_cluster_id",
    "ticker",
    "probe_role",
    "route_tier",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "market_status",
    "result_text",
    "outcome",
)

PREDICTION_SCORE_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "preoutcome_receipt_sha256",
    "event_ticker",
    "source_cluster_id",
    "time_band",
    "cross_section_id",
    "selected_end_period_ts",
    "selected_normalized_time_remaining",
    "ticker",
    "probe_role",
    "strike_anchor",
    "q_raw",
    "q_monotone",
    "outcome",
    "raw_log_loss",
    "monotone_log_loss",
    "delta_log_loss",
    "raw_brier",
    "monotone_brier",
    "delta_brier",
    "absolute_adjustment",
    "cross_section_raw_monotonicity_violation",
)

CLUSTER_SCORE_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "preoutcome_receipt_sha256",
    "event_ticker",
    "source_cluster_id",
    "prediction_count",
    "raw_log_loss",
    "monotone_log_loss",
    "delta_log_loss",
    "raw_brier",
    "monotone_brier",
    "delta_brier",
    "raw_monotonicity_violation_rate",
    "mean_absolute_adjustment",
    "max_absolute_adjustment",
)

BAND_SCORE_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "preoutcome_receipt_sha256",
    "time_band",
    "cluster_count",
    "prediction_count",
    "raw_log_loss",
    "monotone_log_loss",
    "delta_log_loss",
    "raw_brier",
    "monotone_brier",
    "delta_brier",
    "raw_monotonicity_violation_rate",
    "mean_absolute_adjustment",
    "max_absolute_adjustment",
)

SUMMARY_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "preoutcome_receipt_sha256",
    "development_cluster_count",
    "holdout_cluster_count",
    "development_ticker_count",
    "prediction_count",
    "raw_log_loss",
    "monotone_log_loss",
    "delta_log_loss",
    "raw_brier",
    "monotone_brier",
    "delta_brier",
    "raw_monotonicity_violation_rate",
    "mean_absolute_adjustment",
    "max_absolute_adjustment",
    "holdout_outcomes_materialized",
    "external_predictive_feed_used",
    "orders_placed",
    "status",
)


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference


class RawFirstJsonClient(Protocol):
    def get_json(self, path: str, *, params: Mapping[str, Any] | None = None) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class PreOutcomeFreeze:
    receipt_path: Path
    receipt_sha256: str
    receipt: Mapping[str, Any]
    clusters_path: Path
    cross_sections_path: Path
    clusters: tuple[dict[str, str], ...]
    cross_sections: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class DevelopmentEvaluation:
    outcomes: tuple[dict[str, str], ...]
    predictions: tuple[dict[str, str], ...]
    cluster_scores: tuple[dict[str, str], ...]
    band_scores: tuple[dict[str, str], ...]
    summary: dict[str, str]


def load_latest_preoutcome_freeze(repository_root: str | Path = ".") -> PreOutcomeFreeze:
    repo = Path(repository_root).resolve()
    root = repo / "data" / "derived" / "kxbtcd_baseline_preoutcome"
    candidates = sorted(
        root.glob("*_kxbtcd_baseline_preoutcome_receipt.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    if not candidates:
        raise KxbtcdDevelopmentEvaluationError("no KXBTCD pre-outcome freeze receipt found")
    path = candidates[0]
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdDevelopmentEvaluationError("pre-outcome freeze receipt is unreadable") from exc
    if receipt.get("experiment_id") != EXPERIMENT_ID:
        raise KxbtcdDevelopmentEvaluationError("pre-outcome receipt experiment ID mismatch")
    fingerprint = design_fingerprint()
    if receipt.get("design_fingerprint") != fingerprint:
        raise KxbtcdDevelopmentEvaluationError("pre-outcome receipt design fingerprint mismatch")
    if receipt.get("status") != "preoutcome_design_inputs_frozen":
        raise KxbtcdDevelopmentEvaluationError("pre-outcome receipt is not frozen")
    safety = receipt.get("safety")
    if not isinstance(safety, Mapping) or safety.get("outcomes_materialized") is not False:
        raise KxbtcdDevelopmentEvaluationError("pre-outcome receipt does not prove outcome-blind freeze")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise KxbtcdDevelopmentEvaluationError("pre-outcome receipt missing artifacts")
    clusters_path = _verified_receipt_artifact(repo, artifacts, "clusters_csv")
    cross_sections_path = _verified_receipt_artifact(repo, artifacts, "cross_sections_csv")
    clusters = tuple(_read_csv(clusters_path))
    cross_sections = tuple(
        _enrich_cross_sections_with_source_probe_metadata(
            repo=repo,
            receipt=receipt,
            cross_sections=_read_csv(cross_sections_path),
        )
    )
    freeze = PreOutcomeFreeze(
        receipt_path=path,
        receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        receipt=receipt,
        clusters_path=clusters_path,
        cross_sections_path=cross_sections_path,
        clusters=clusters,
        cross_sections=cross_sections,
    )
    validate_preoutcome_freeze(freeze)
    return freeze


def validate_preoutcome_freeze(freeze: PreOutcomeFreeze) -> None:
    fingerprint = design_fingerprint()
    eligible = [row for row in freeze.clusters if row.get("primary_eligible") == "true"]
    dev = [row for row in eligible if row.get("partition") == "development"]
    holdout = [row for row in eligible if row.get("partition") == "holdout"]
    if len(dev) != EXPECTED_DEVELOPMENT_CLUSTERS:
        raise KxbtcdDevelopmentEvaluationError(
            f"expected {EXPECTED_DEVELOPMENT_CLUSTERS} frozen development clusters, found {len(dev)}"
        )
    if len(holdout) != EXPECTED_HOLDOUT_CLUSTERS:
        raise KxbtcdDevelopmentEvaluationError(
            f"expected {EXPECTED_HOLDOUT_CLUSTERS} frozen holdout clusters, found {len(holdout)}"
        )
    dev_ids = {_required(row, "source_cluster_id") for row in dev}
    holdout_ids = {_required(row, "source_cluster_id") for row in holdout}
    if dev_ids & holdout_ids:
        raise KxbtcdDevelopmentEvaluationError("development/holdout cluster overlap")
    for row in freeze.clusters:
        if _required(row, "design_fingerprint") != fingerprint:
            raise KxbtcdDevelopmentEvaluationError("cluster row fingerprint mismatch")
    dev_sections = [row for row in freeze.cross_sections if row.get("partition") == "development"]
    if len(dev_sections) != EXPECTED_DEVELOPMENT_PREDICTIONS:
        raise KxbtcdDevelopmentEvaluationError(
            f"expected {EXPECTED_DEVELOPMENT_PREDICTIONS} development prediction rows, found {len(dev_sections)}"
        )
    if any(row.get("source_cluster_id") not in dev_ids for row in dev_sections):
        raise KxbtcdDevelopmentEvaluationError("development cross-section references non-development cluster")
    groups: dict[str, list[Mapping[str, str]]] = {}
    for row in dev_sections:
        groups.setdefault(_required(row, "cross_section_id"), []).append(row)
    expected_sections = EXPECTED_DEVELOPMENT_CLUSTERS * EXPECTED_BANDS_PER_CLUSTER
    if len(groups) != expected_sections:
        raise KxbtcdDevelopmentEvaluationError(
            f"expected {expected_sections} development cross-sections, found {len(groups)}"
        )
    for cross_id, rows in groups.items():
        roles = tuple(sorted((_required(row, "probe_role") for row in rows), key=PROBE_ROLES.index))
        if roles != PROBE_ROLES:
            raise KxbtcdDevelopmentEvaluationError(f"cross-section {cross_id} probe roles changed")


def development_request_plan(freeze: PreOutcomeFreeze) -> tuple[dict[str, str], ...]:
    """Return the exact frozen development ticker request set; never holdout."""

    dev_rows = [row for row in freeze.cross_sections if row.get("partition") == "development"]
    holdout_tickers = {
        _required(row, "ticker") for row in freeze.cross_sections if row.get("partition") == "holdout"
    }
    by_ticker: dict[str, dict[str, str]] = {}
    for row in dev_rows:
        ticker = _required(row, "ticker")
        current = by_ticker.get(ticker)
        identity = {
            "event_ticker": _required(row, "event_ticker"),
            "source_cluster_id": _required(row, "source_cluster_id"),
            "ticker": ticker,
            "probe_role": _required(row, "probe_role"),
            "route_tier": _required(row, "quote_route_tier"),
        }
        if current is not None and current != identity:
            raise KxbtcdDevelopmentEvaluationError(f"development ticker {ticker} identity changed")
        by_ticker[ticker] = identity
    if len(by_ticker) != EXPECTED_DEVELOPMENT_TICKERS:
        raise KxbtcdDevelopmentEvaluationError(
            f"expected {EXPECTED_DEVELOPMENT_TICKERS} unique development tickers, found {len(by_ticker)}"
        )
    if set(by_ticker) & holdout_tickers:
        raise KxbtcdDevelopmentEvaluationError("development request plan contains holdout ticker")
    if any(item["route_tier"] not in {"historical", "live"} for item in by_ticker.values()):
        raise KxbtcdDevelopmentEvaluationError("development request plan has unsupported route tier")
    return tuple(sorted(by_ticker.values(), key=lambda row: row["ticker"]))


def collect_development_outcomes(
    client: RawFirstJsonClient,
    *,
    freeze: PreOutcomeFreeze,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in development_request_plan(freeze):
        ticker = item["ticker"]
        route_tier = item["route_tier"]
        path = f"/historical/markets/{ticker}" if route_tier == "historical" else f"/markets/{ticker}"
        response = client.get_json(path)
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            raise KxbtcdDevelopmentEvaluationError(f"outcome response for {ticker} missing market object")
        if _required(market, "ticker") != ticker:
            raise KxbtcdDevelopmentEvaluationError(f"outcome response ticker mismatch for {ticker}")
        if _required(market, "event_ticker") != item["event_ticker"]:
            raise KxbtcdDevelopmentEvaluationError(f"outcome response event mismatch for {ticker}")
        status = _required(market, "status").lower()
        if status != "finalized":
            raise KxbtcdDevelopmentEvaluationError(f"market {ticker} is not finalized: {status}")
        result_text = _required(market, "result").lower()
        if result_text == "yes":
            outcome = "1"
        elif result_text == "no":
            outcome = "0"
        else:
            raise KxbtcdDevelopmentEvaluationError(
                f"market {ticker} has unsupported finalized result {result_text!r}"
            )
        rows.append(
            {
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": freeze.receipt_sha256,
                "event_ticker": item["event_ticker"],
                "source_cluster_id": item["source_cluster_id"],
                "ticker": ticker,
                "probe_role": item["probe_role"],
                "route_tier": route_tier,
                "raw_source": _required_attr(response.raw_record, "source"),
                "raw_session_id": _required_attr(response.raw_record, "session_id"),
                "raw_request_id": _required_attr(response.raw_record, "request_id"),
                "market_status": status,
                "result_text": result_text,
                "outcome": outcome,
            }
        )
    _validate_outcomes(rows, freeze)
    return tuple(rows)


def evaluate_development(
    *,
    freeze: PreOutcomeFreeze,
    outcomes: Sequence[Mapping[str, str]],
) -> DevelopmentEvaluation:
    _validate_outcomes(outcomes, freeze)
    outcome_by_ticker = {_required(row, "ticker"): int(_required(row, "outcome")) for row in outcomes}
    dev_rows = [row for row in freeze.cross_sections if row.get("partition") == "development"]
    groups: dict[str, list[Mapping[str, str]]] = {}
    for row in dev_rows:
        groups.setdefault(_required(row, "cross_section_id"), []).append(row)

    predictions: list[dict[str, str]] = []
    for cross_id, group in sorted(groups.items()):
        ordered = sorted(group, key=lambda row: PROBE_ROLES.index(_required(row, "probe_role")))
        q_raw = [Decimal(_required(row, "q_raw")) for row in ordered]
        q_mono = list(project_nonincreasing_l2(q_raw))
        labels = [outcome_by_ticker[_required(row, "ticker")] for row in ordered]
        if not (labels[0] >= labels[1] >= labels[2]):
            raise KxbtcdDevelopmentEvaluationError(
                f"development outcome ladder is not monotone for cross-section {cross_id}: {labels}"
            )
        violation = not (q_raw[0] >= q_raw[1] >= q_raw[2])
        for row, raw_p, mono_p, y in zip(ordered, q_raw, q_mono, labels):
            raw_ll = binary_log_loss(raw_p, y)
            mono_ll = binary_log_loss(mono_p, y)
            raw_br = brier_score(raw_p, y)
            mono_br = brier_score(mono_p, y)
            predictions.append(
                {
                    "schema_version": PREDICTION_SCHEMA_VERSION,
                    "experiment_id": EXPERIMENT_ID,
                    "design_fingerprint": design_fingerprint(),
                    "preoutcome_receipt_sha256": freeze.receipt_sha256,
                    "event_ticker": _required(row, "event_ticker"),
                    "source_cluster_id": _required(row, "source_cluster_id"),
                    "time_band": _required(row, "time_band"),
                    "cross_section_id": cross_id,
                    "selected_end_period_ts": _required(row, "selected_end_period_ts"),
                    "selected_normalized_time_remaining": _required(row, "selected_normalized_time_remaining"),
                    "ticker": _required(row, "ticker"),
                    "probe_role": _required(row, "probe_role"),
                    "strike_anchor": _row_strike_anchor(row),
                    "q_raw": _decimal_text(raw_p),
                    "q_monotone": _decimal_text(mono_p),
                    "outcome": str(y),
                    "raw_log_loss": _decimal_text(raw_ll),
                    "monotone_log_loss": _decimal_text(mono_ll),
                    "delta_log_loss": _decimal_text(raw_ll - mono_ll),
                    "raw_brier": _decimal_text(raw_br),
                    "monotone_brier": _decimal_text(mono_br),
                    "delta_brier": _decimal_text(raw_br - mono_br),
                    "absolute_adjustment": _decimal_text(abs(raw_p - mono_p)),
                    "cross_section_raw_monotonicity_violation": _bool_text(violation),
                }
            )

    if len(predictions) != EXPECTED_DEVELOPMENT_PREDICTIONS:
        raise KxbtcdDevelopmentEvaluationError("development prediction count changed")
    cluster_scores = _aggregate_by_cluster(predictions, freeze.receipt_sha256)
    band_scores = _aggregate_by_band(predictions, freeze.receipt_sha256)
    summary = _build_summary(predictions, cluster_scores, freeze)
    return DevelopmentEvaluation(
        outcomes=tuple(outcomes),
        predictions=tuple(predictions),
        cluster_scores=tuple(cluster_scores),
        band_scores=tuple(band_scores),
        summary=summary,
    )


def write_development_evaluation(
    output_dir: str | Path,
    *,
    evaluation: DevelopmentEvaluation,
    run_id: str,
) -> tuple[Path, Path, Path, Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = (
        root / f"{run_id}_kxbtcd_development_outcomes.csv",
        root / f"{run_id}_kxbtcd_development_prediction_scores.csv",
        root / f"{run_id}_kxbtcd_development_cluster_scores.csv",
        root / f"{run_id}_kxbtcd_development_band_scores.csv",
        root / f"{run_id}_kxbtcd_development_summary.csv",
    )
    _write_csv(paths[0], OUTCOME_FIELDS, evaluation.outcomes)
    _write_csv(paths[1], PREDICTION_SCORE_FIELDS, evaluation.predictions)
    _write_csv(paths[2], CLUSTER_SCORE_FIELDS, evaluation.cluster_scores)
    _write_csv(paths[3], BAND_SCORE_FIELDS, evaluation.band_scores)
    _write_csv(paths[4], SUMMARY_FIELDS, (evaluation.summary,))
    return paths


def _validate_outcomes(rows: Sequence[Mapping[str, str]], freeze: PreOutcomeFreeze) -> None:
    plan = development_request_plan(freeze)
    expected = {row["ticker"]: row for row in plan}
    if len(rows) != EXPECTED_DEVELOPMENT_TICKERS:
        raise KxbtcdDevelopmentEvaluationError(
            f"expected {EXPECTED_DEVELOPMENT_TICKERS} development labels, found {len(rows)}"
        )
    seen: set[str] = set()
    labels_by_cluster: dict[str, dict[str, int]] = {}
    for row in rows:
        if tuple(row.keys()) != OUTCOME_FIELDS:
            raise KxbtcdDevelopmentEvaluationError("development outcome fields changed")
        ticker = _required(row, "ticker")
        if ticker in seen or ticker not in expected:
            raise KxbtcdDevelopmentEvaluationError(f"unexpected or duplicate development ticker {ticker}")
        seen.add(ticker)
        expected_row = expected[ticker]
        for field in ("event_ticker", "source_cluster_id", "probe_role", "route_tier"):
            if _required(row, field) != expected_row[field]:
                raise KxbtcdDevelopmentEvaluationError(f"development outcome identity mismatch for {ticker}")
        if _required(row, "design_fingerprint") != design_fingerprint():
            raise KxbtcdDevelopmentEvaluationError("development outcome fingerprint mismatch")
        if _required(row, "preoutcome_receipt_sha256") != freeze.receipt_sha256:
            raise KxbtcdDevelopmentEvaluationError("development outcome freeze receipt mismatch")
        if _required(row, "market_status") != "finalized":
            raise KxbtcdDevelopmentEvaluationError(f"development market {ticker} not finalized")
        outcome = _required(row, "outcome")
        result_text = _required(row, "result_text")
        if (result_text, outcome) not in {("yes", "1"), ("no", "0")}:
            raise KxbtcdDevelopmentEvaluationError(f"development result mapping invalid for {ticker}")
        labels_by_cluster.setdefault(expected_row["source_cluster_id"], {})[expected_row["probe_role"]] = int(outcome)
    for cluster_id, labels in labels_by_cluster.items():
        if set(labels) != set(PROBE_ROLES):
            raise KxbtcdDevelopmentEvaluationError(f"cluster {cluster_id} missing development labels")
        ordered = [labels[role] for role in PROBE_ROLES]
        if not (ordered[0] >= ordered[1] >= ordered[2]):
            raise KxbtcdDevelopmentEvaluationError(
                f"cluster {cluster_id} finalized outcomes violate threshold ordering: {ordered}"
            )


def _aggregate_by_cluster(
    predictions: Sequence[Mapping[str, str]], receipt_sha: str
) -> list[dict[str, str]]:
    groups: dict[str, list[Mapping[str, str]]] = {}
    for row in predictions:
        groups.setdefault(_required(row, "source_cluster_id"), []).append(row)
    output: list[dict[str, str]] = []
    for cluster_id, rows in sorted(groups.items()):
        if len(rows) != EXPECTED_PROBES_PER_CLUSTER * EXPECTED_BANDS_PER_CLUSTER:
            raise KxbtcdDevelopmentEvaluationError(f"cluster {cluster_id} prediction count changed")
        event_ids = {_required(row, "event_ticker") for row in rows}
        if len(event_ids) != 1:
            raise KxbtcdDevelopmentEvaluationError(f"cluster {cluster_id} event identity changed")
        stats = _score_stats(rows)
        output.append(
            {
                "schema_version": CLUSTER_SCORE_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": receipt_sha,
                "event_ticker": next(iter(event_ids)),
                "source_cluster_id": cluster_id,
                "prediction_count": str(len(rows)),
                **stats,
            }
        )
    if len(output) != EXPECTED_DEVELOPMENT_CLUSTERS:
        raise KxbtcdDevelopmentEvaluationError("cluster score count changed")
    return output


def _aggregate_by_band(
    predictions: Sequence[Mapping[str, str]], receipt_sha: str
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for band in TIME_BANDS:
        rows = [row for row in predictions if row.get("time_band") == band]
        clusters = {_required(row, "source_cluster_id") for row in rows}
        if len(clusters) != EXPECTED_DEVELOPMENT_CLUSTERS:
            raise KxbtcdDevelopmentEvaluationError(f"band {band} development cluster count changed")
        output.append(
            {
                "schema_version": BAND_SCORE_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": receipt_sha,
                "time_band": band,
                "cluster_count": str(len(clusters)),
                "prediction_count": str(len(rows)),
                **_score_stats(rows),
            }
        )
    return output


def _build_summary(
    predictions: Sequence[Mapping[str, str]],
    cluster_scores: Sequence[Mapping[str, str]],
    freeze: PreOutcomeFreeze,
) -> dict[str, str]:
    # Explicit equal-cluster aggregation. Because each cluster has exactly nine
    # predictions, this equals the row mean today but remains semantically tied
    # to the settlement-cluster evaluation unit.
    raw_ll = _mean_decimal([row["raw_log_loss"] for row in cluster_scores])
    mono_ll = _mean_decimal([row["monotone_log_loss"] for row in cluster_scores])
    raw_br = _mean_decimal([row["raw_brier"] for row in cluster_scores])
    mono_br = _mean_decimal([row["monotone_brier"] for row in cluster_scores])
    violation = _cross_section_violation_rate(predictions)
    adjustments = [Decimal(_required(row, "absolute_adjustment")) for row in predictions]
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "design_fingerprint": design_fingerprint(),
        "preoutcome_receipt_sha256": freeze.receipt_sha256,
        "development_cluster_count": str(EXPECTED_DEVELOPMENT_CLUSTERS),
        "holdout_cluster_count": str(EXPECTED_HOLDOUT_CLUSTERS),
        "development_ticker_count": str(EXPECTED_DEVELOPMENT_TICKERS),
        "prediction_count": str(len(predictions)),
        "raw_log_loss": _decimal_text(raw_ll),
        "monotone_log_loss": _decimal_text(mono_ll),
        "delta_log_loss": _decimal_text(raw_ll - mono_ll),
        "raw_brier": _decimal_text(raw_br),
        "monotone_brier": _decimal_text(mono_br),
        "delta_brier": _decimal_text(raw_br - mono_br),
        "raw_monotonicity_violation_rate": _decimal_text(violation),
        "mean_absolute_adjustment": _decimal_text(sum(adjustments, Decimal(0)) / Decimal(len(adjustments))),
        "max_absolute_adjustment": _decimal_text(max(adjustments)),
        "holdout_outcomes_materialized": "false",
        "external_predictive_feed_used": "false",
        "orders_placed": "0",
        "status": "development_evaluation_complete",
    }


def _score_stats(rows: Sequence[Mapping[str, str]]) -> dict[str, str]:
    raw_ll = _mean_decimal([_required(row, "raw_log_loss") for row in rows])
    mono_ll = _mean_decimal([_required(row, "monotone_log_loss") for row in rows])
    raw_br = _mean_decimal([_required(row, "raw_brier") for row in rows])
    mono_br = _mean_decimal([_required(row, "monotone_brier") for row in rows])
    adjustments = [Decimal(_required(row, "absolute_adjustment")) for row in rows]
    return {
        "raw_log_loss": _decimal_text(raw_ll),
        "monotone_log_loss": _decimal_text(mono_ll),
        "delta_log_loss": _decimal_text(raw_ll - mono_ll),
        "raw_brier": _decimal_text(raw_br),
        "monotone_brier": _decimal_text(mono_br),
        "delta_brier": _decimal_text(raw_br - mono_br),
        "raw_monotonicity_violation_rate": _decimal_text(_cross_section_violation_rate(rows)),
        "mean_absolute_adjustment": _decimal_text(sum(adjustments, Decimal(0)) / Decimal(len(adjustments))),
        "max_absolute_adjustment": _decimal_text(max(adjustments)),
    }


def _cross_section_violation_rate(rows: Sequence[Mapping[str, str]]) -> Decimal:
    by_cross: dict[str, bool] = {}
    for row in rows:
        cross_id = _required(row, "cross_section_id")
        value = _required(row, "cross_section_raw_monotonicity_violation") == "true"
        previous = by_cross.get(cross_id)
        if previous is not None and previous != value:
            raise KxbtcdDevelopmentEvaluationError(f"cross-section {cross_id} violation flag changed")
        by_cross[cross_id] = value
    if not by_cross:
        raise KxbtcdDevelopmentEvaluationError("no cross-sections to aggregate")
    return Decimal(sum(by_cross.values())) / Decimal(len(by_cross))



def _enrich_cross_sections_with_source_probe_metadata(
    *,
    repo: Path,
    receipt: Mapping[str, Any],
    cross_sections: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    """Attach immutable strike metadata from the pre-outcome source probe CSV.

    The frozen cross-section CSV was built from quote-observation rows, whose
    schema intentionally omits strike metadata. The source probe CSV is the
    outcome-blind artifact that originally defined q25/q50/q75 ordering, so it
    is the correct source for the threshold coordinate used only for reporting.
    This enrichment is in-memory; it does not alter the frozen receipt or files.
    """

    source_manifest_spec = receipt.get("source_manifest")
    if not isinstance(source_manifest_spec, Mapping):
        raise KxbtcdDevelopmentEvaluationError("pre-outcome receipt missing source_manifest")
    source_manifest_path = _resolve_stored_path(repo, source_manifest_spec)
    expected_manifest_sha = _required(receipt, "source_manifest_sha256")
    actual_manifest_sha = hashlib.sha256(source_manifest_path.read_bytes()).hexdigest()
    if actual_manifest_sha != expected_manifest_sha:
        raise KxbtcdDevelopmentEvaluationError("source quote manifest hash mismatch")
    try:
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdDevelopmentEvaluationError("source quote manifest is unreadable") from exc
    if _required(source_manifest, "run_id") != _required(receipt, "source_run_id"):
        raise KxbtcdDevelopmentEvaluationError("source quote run ID mismatch")
    if source_manifest.get("status") != "completed":
        raise KxbtcdDevelopmentEvaluationError("source quote manifest is not completed")

    probe_path, probe_descriptor = _manifest_derived_file(
        repo, source_manifest, "btc_family_probe_markets"
    )
    expected_probe_sha = _required(probe_descriptor, "sha256")
    actual_probe_sha = hashlib.sha256(probe_path.read_bytes()).hexdigest()
    if actual_probe_sha != expected_probe_sha:
        raise KxbtcdDevelopmentEvaluationError("source probe CSV hash mismatch")

    probe_rows = [row for row in _read_csv(probe_path) if row.get("family") == "KXBTCD"]
    by_ticker: dict[str, Mapping[str, str]] = {}
    for row in probe_rows:
        ticker = _required(row, "ticker")
        if ticker in by_ticker:
            raise KxbtcdDevelopmentEvaluationError(f"duplicate KXBTCD source probe {ticker}")
        by_ticker[ticker] = row

    enriched: list[dict[str, str]] = []
    for original in cross_sections:
        row = dict(original)
        ticker = _required(row, "ticker")
        probe = by_ticker.get(ticker)
        if probe is None:
            raise KxbtcdDevelopmentEvaluationError(
                f"frozen cross-section ticker {ticker} missing from source probe CSV"
            )
        for field in ("event_ticker", "source_cluster_id", "probe_role"):
            if _required(probe, field) != _required(row, field):
                raise KxbtcdDevelopmentEvaluationError(
                    f"source probe identity mismatch for {ticker}: {field}"
                )
        for field in ("strike_type", "floor_strike", "cap_strike", "functional_strike"):
            frozen = str(row.get(field) or "").strip()
            source = str(probe.get(field) or "").strip()
            if frozen and frozen != source:
                raise KxbtcdDevelopmentEvaluationError(
                    f"frozen/source strike metadata conflict for {ticker}: {field}"
                )
            row[field] = source
        row["strike_anchor"] = _strike_anchor(probe)
        enriched.append(row)
    return enriched


def _row_strike_anchor(row: Mapping[str, str]) -> str:
    explicit = str(row.get("strike_anchor") or "").strip()
    if explicit:
        return explicit
    return _strike_anchor(row)


def _strike_anchor(row: Mapping[str, str]) -> str:
    values: dict[str, Decimal | None] = {}
    for field in ("floor_strike", "cap_strike", "functional_strike"):
        text = str(row.get(field) or "").strip()
        values[field] = Decimal(text) if text else None
    floor = values["floor_strike"]
    cap = values["cap_strike"]
    functional = values["functional_strike"]
    if floor is not None and cap is not None:
        return _decimal_text((floor + cap) / Decimal(2))
    if floor is not None:
        return _decimal_text(floor)
    if cap is not None:
        return _decimal_text(cap)
    if functional is not None:
        return _decimal_text(functional)
    raise KxbtcdDevelopmentEvaluationError(
        f"source probe {_required(row, 'ticker')} has no strike coordinate"
    )


def _resolve_stored_path(repo: Path, spec: Mapping[str, Any]) -> Path:
    kind = _required(spec, "kind")
    value = _required(spec, "value")
    if kind == "repository_relative":
        path = (repo / value).resolve()
    elif kind == "absolute":
        path = Path(value).resolve()
    else:
        raise KxbtcdDevelopmentEvaluationError(f"unsupported stored path kind {kind!r}")
    if not path.exists():
        raise KxbtcdDevelopmentEvaluationError(f"referenced artifact is missing: {path}")
    return path


def _manifest_derived_file(
    repo: Path, manifest: Mapping[str, Any], name_fragment: str
) -> tuple[Path, Mapping[str, Any]]:
    matches: list[tuple[Path, Mapping[str, Any]]] = []
    for descriptor in manifest.get("files", []):
        if not isinstance(descriptor, Mapping) or descriptor.get("role") != "derived_csv":
            continue
        spec = descriptor.get("path")
        if not isinstance(spec, Mapping):
            continue
        value = spec.get("value")
        if isinstance(value, str) and name_fragment in value:
            matches.append((_resolve_stored_path(repo, spec), descriptor))
    if len(matches) != 1:
        raise KxbtcdDevelopmentEvaluationError(
            f"expected one source derived file containing {name_fragment!r}, found {len(matches)}"
        )
    return matches[0]


def matching_failed_development_manifests(
    freeze: PreOutcomeFreeze, repository_root: str | Path = "."
) -> tuple[Path, ...]:
    repo = Path(repository_root).resolve()
    root = repo / "data" / "manifests"
    matches: list[Path] = []
    for path in root.glob("**/collect_kxbtcd_development_outcomes_*.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("status") != "failed":
            continue
        collector = manifest.get("collector")
        if not isinstance(collector, Mapping) or collector.get("name") != "collect_kxbtcd_development_outcomes":
            continue
        arguments = manifest.get("arguments")
        if not isinstance(arguments, Mapping):
            continue
        if arguments.get("preoutcome_receipt_sha256") != freeze.receipt_sha256:
            continue
        if arguments.get("design_fingerprint") != design_fingerprint():
            continue
        if arguments.get("partition") != "development":
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches, key=lambda p: p.stat().st_mtime_ns))


def recover_development_outcomes_from_failed_manifest(
    *,
    freeze: PreOutcomeFreeze,
    manifest_path: str | Path,
    repository_root: str | Path = ".",
) -> tuple[dict[str, str], ...]:
    """Replay the already-preserved failed-run responses with zero API calls."""

    repo = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdDevelopmentEvaluationError("failed development manifest is unreadable") from exc
    if path not in matching_failed_development_manifests(freeze, repo):
        raise KxbtcdDevelopmentEvaluationError(
            "failed manifest does not match the frozen development experiment"
        )

    plan = development_request_plan(freeze)
    expected_by_path: dict[str, Mapping[str, str]] = {}
    expected_by_ticker = {item["ticker"]: item for item in plan}
    for item in plan:
        endpoint = (
            f"/historical/markets/{item['ticker']}"
            if item["route_tier"] == "historical"
            else f"/markets/{item['ticker']}"
        )
        expected_by_path[endpoint] = item

    holdout_paths: set[str] = set()
    for row in freeze.cross_sections:
        if row.get("partition") != "holdout":
            continue
        ticker = _required(row, "ticker")
        route_tier = _required(row, "quote_route_tier")
        endpoint = (
            f"/historical/markets/{ticker}"
            if route_tier == "historical"
            else f"/markets/{ticker}"
        )
        holdout_paths.add(endpoint)
    raw_descriptors = [
        item for item in manifest.get("files", [])
        if isinstance(item, Mapping) and item.get("role") == "raw_api_archive"
    ]
    if not raw_descriptors:
        raise KxbtcdDevelopmentEvaluationError("failed run preserved no raw API archive")

    successes: dict[str, Mapping[str, Any]] = {}
    for descriptor in raw_descriptors:
        spec = descriptor.get("path")
        if not isinstance(spec, Mapping):
            raise KxbtcdDevelopmentEvaluationError("failed raw descriptor missing path")
        raw_path = _resolve_stored_path(repo, spec)
        inspection = _inspect_raw_jsonl_for_recovery(raw_path)
        if inspection.get("sha256") != descriptor.get("sha256"):
            raise KxbtcdDevelopmentEvaluationError("failed raw archive hash mismatch")
        with raw_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                request = record.get("request")
                if not isinstance(request, Mapping):
                    raise KxbtcdDevelopmentEvaluationError("raw record missing request")
                request_path = _required(request, "path")
                if request_path in holdout_paths:
                    raise KxbtcdDevelopmentEvaluationError(
                        "failed development raw archive contains holdout request"
                    )
                if request_path not in expected_by_path:
                    raise KxbtcdDevelopmentEvaluationError(
                        f"failed development raw archive contains unexpected request {request_path!r}"
                    )
                response = record.get("response")
                if not isinstance(response, Mapping) or response.get("status_code") != 200:
                    continue
                if record.get("error") is not None:
                    raise KxbtcdDevelopmentEvaluationError(
                        f"successful response for {request_path} also carries an error"
                    )
                ticker = expected_by_path[request_path]["ticker"]
                if ticker in successes:
                    raise KxbtcdDevelopmentEvaluationError(
                        f"multiple successful preserved responses for {ticker}"
                    )
                successes[ticker] = record

    if set(successes) != set(expected_by_ticker):
        missing = sorted(set(expected_by_ticker) - set(successes))
        raise KxbtcdDevelopmentEvaluationError(
            f"failed run does not contain one successful preserved response for every development ticker; missing={missing}"
        )

    rows: list[dict[str, str]] = []
    for ticker in sorted(expected_by_ticker):
        item = expected_by_ticker[ticker]
        record = successes[ticker]
        response = record["response"]
        try:
            payload = json.loads(_required(response, "body_text"))
        except json.JSONDecodeError as exc:
            raise KxbtcdDevelopmentEvaluationError(
                f"preserved response body for {ticker} is not valid JSON"
            ) from exc
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if not isinstance(market, Mapping):
            raise KxbtcdDevelopmentEvaluationError(
                f"preserved outcome response for {ticker} missing market object"
            )
        if _required(market, "ticker") != ticker:
            raise KxbtcdDevelopmentEvaluationError(f"preserved ticker mismatch for {ticker}")
        if _required(market, "event_ticker") != item["event_ticker"]:
            raise KxbtcdDevelopmentEvaluationError(f"preserved event mismatch for {ticker}")
        status = _required(market, "status").lower()
        if status != "finalized":
            raise KxbtcdDevelopmentEvaluationError(f"market {ticker} is not finalized: {status}")
        result_text = _required(market, "result").lower()
        if result_text == "yes":
            outcome = "1"
        elif result_text == "no":
            outcome = "0"
        else:
            raise KxbtcdDevelopmentEvaluationError(
                f"market {ticker} has unsupported finalized result {result_text!r}"
            )
        request = record["request"]
        rows.append(
            {
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": freeze.receipt_sha256,
                "event_ticker": item["event_ticker"],
                "source_cluster_id": item["source_cluster_id"],
                "ticker": ticker,
                "probe_role": item["probe_role"],
                "route_tier": item["route_tier"],
                "raw_source": _required(record, "source"),
                "raw_session_id": _required(record, "session_id"),
                "raw_request_id": _required(request, "request_id"),
                "market_status": status,
                "result_text": result_text,
                "outcome": outcome,
            }
        )
    _validate_outcomes(rows, freeze)
    return tuple(rows)


def _inspect_raw_jsonl_for_recovery(path: Path) -> dict[str, Any]:
    record_count = 0
    error_record_count = 0
    session_ids: set[str] = set()
    request_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise KxbtcdDevelopmentEvaluationError(
                    f"raw recovery archive contains blank line {line_number}"
                )
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise KxbtcdDevelopmentEvaluationError(
                    f"raw recovery archive has invalid JSON at line {line_number}"
                ) from exc
            if record.get("schema_version") != "raw_http_exchange.v1":
                raise KxbtcdDevelopmentEvaluationError("raw recovery schema version changed")
            source = _required(record, "source")
            session = _required(record, "session_id")
            request = record.get("request")
            if not isinstance(request, Mapping):
                raise KxbtcdDevelopmentEvaluationError("raw recovery record missing request object")
            request_id = _required(request, "request_id")
            if request_id in request_ids:
                raise KxbtcdDevelopmentEvaluationError(
                    f"raw recovery archive has duplicate request_id {request_id}"
                )
            if source != "kalshi_public_rest":
                raise KxbtcdDevelopmentEvaluationError(
                    f"unexpected raw recovery source {source!r}"
                )
            request_ids.add(request_id)
            session_ids.add(session)
            record_count += 1
            if record.get("error") is not None:
                error_record_count += 1
    if record_count == 0:
        raise KxbtcdDevelopmentEvaluationError("raw recovery archive is empty")
    return {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "record_count": record_count,
        "error_record_count": error_record_count,
        "session_ids": sorted(session_ids),
    }


def _verified_receipt_artifact(repo: Path, artifacts: Mapping[str, Any], key: str) -> Path:
    entry = artifacts.get(key)
    if not isinstance(entry, Mapping):
        raise KxbtcdDevelopmentEvaluationError(f"pre-outcome receipt missing artifact {key}")
    value = _required(entry, "path")
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    path = path.resolve()
    if not path.exists():
        raise KxbtcdDevelopmentEvaluationError(f"pre-outcome artifact missing: {path}")
    expected = _required(entry, "sha256")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise KxbtcdDevelopmentEvaluationError(f"pre-outcome artifact hash mismatch: {path}")
    return path


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _mean_decimal(values: Sequence[str]) -> Decimal:
    if not values:
        raise KxbtcdDevelopmentEvaluationError("cannot average empty values")
    decimals = [Decimal(value) for value in values]
    return sum(decimals, Decimal(0)) / Decimal(len(decimals))


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _required(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if value is None or not str(value).strip():
        raise KxbtcdDevelopmentEvaluationError(f"required field {field!r} is missing")
    return str(value).strip()


def _required_attr(obj: Any, field: str) -> str:
    value = getattr(obj, field, None)
    if value is None or not str(value).strip():
        raise KxbtcdDevelopmentEvaluationError(f"required raw lineage field {field!r} is missing")
    return str(value).strip()
