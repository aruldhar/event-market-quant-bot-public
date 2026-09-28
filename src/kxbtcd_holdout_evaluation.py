"""Untouched-holdout outcome collection and scoring for KXBTCD baseline v1.

The analytical design was frozen before development outcomes were opened. This
module does not alter that design. It selects only the frozen holdout partition,
requires proof that the development recovery completed under the same design
fingerprint, and applies the same probability/scoring primitives used by the
frozen development evaluator.
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
    binary_log_loss,
    brier_score,
    design_fingerprint,
    project_nonincreasing_l2,
)
from .kxbtcd_development_evaluation import (
    PreOutcomeFreeze,
    load_latest_preoutcome_freeze,
)


class KxbtcdHoldoutEvaluationError(RuntimeError):
    """Raised when untouched-holdout collection or scoring invariants fail."""


OUTCOME_SCHEMA_VERSION = "kxbtcd_holdout_outcome.v1"
PREDICTION_SCHEMA_VERSION = "kxbtcd_holdout_prediction_score.v1"
CLUSTER_SCORE_SCHEMA_VERSION = "kxbtcd_holdout_cluster_score.v1"
BAND_SCORE_SCHEMA_VERSION = "kxbtcd_holdout_band_score.v1"
SUMMARY_SCHEMA_VERSION = "kxbtcd_holdout_summary.v1"

EXPECTED_DEVELOPMENT_CLUSTERS = 8
EXPECTED_HOLDOUT_CLUSTERS = 4
EXPECTED_PROBES_PER_CLUSTER = 3
EXPECTED_BANDS_PER_CLUSTER = 3
EXPECTED_HOLDOUT_TICKERS = EXPECTED_HOLDOUT_CLUSTERS * EXPECTED_PROBES_PER_CLUSTER
EXPECTED_HOLDOUT_PREDICTIONS = (
    EXPECTED_HOLDOUT_CLUSTERS * EXPECTED_PROBES_PER_CLUSTER * EXPECTED_BANDS_PER_CLUSTER
)
EXPECTED_DEVELOPMENT_LABELS = EXPECTED_DEVELOPMENT_CLUSTERS * EXPECTED_PROBES_PER_CLUSTER
EXPECTED_DEVELOPMENT_PREDICTIONS = (
    EXPECTED_DEVELOPMENT_CLUSTERS * EXPECTED_PROBES_PER_CLUSTER * EXPECTED_BANDS_PER_CLUSTER
)

OUTCOME_FIELDS = (
    "schema_version",
    "experiment_id",
    "design_fingerprint",
    "preoutcome_receipt_sha256",
    "development_recovery_receipt_sha256",
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
    "development_recovery_receipt_sha256",
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
    "development_recovery_receipt_sha256",
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
    "development_recovery_receipt_sha256",
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
    "development_recovery_receipt_sha256",
    "development_cluster_count",
    "holdout_cluster_count",
    "holdout_ticker_count",
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
    "design_fingerprint_unchanged",
    "model_or_metric_change_after_development",
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
class DevelopmentRecoveryEvidence:
    receipt_path: Path
    receipt_sha256: str
    receipt: Mapping[str, Any]


@dataclass(frozen=True)
class HoldoutEvaluation:
    outcomes: tuple[dict[str, str], ...]
    predictions: tuple[dict[str, str], ...]
    cluster_scores: tuple[dict[str, str], ...]
    band_scores: tuple[dict[str, str], ...]
    summary: dict[str, str]


def load_verified_development_recovery(
    freeze: PreOutcomeFreeze,
    repository_root: str | Path = ".",
) -> DevelopmentRecoveryEvidence:
    """Verify development completed without touching the holdout partition."""

    repo = Path(repository_root).resolve()
    root = repo / "data" / "derived" / "kxbtcd_development_evaluation_recovery"
    candidates = sorted(
        root.glob("*_offline_recovery_receipt.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    matches: list[tuple[Path, Mapping[str, Any]]] = []
    for path in candidates:
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("experiment_id") != EXPERIMENT_ID:
            continue
        if receipt.get("design_fingerprint") != design_fingerprint():
            continue
        if receipt.get("preoutcome_receipt_sha256") != freeze.receipt_sha256:
            continue
        if receipt.get("status") != "offline_recovery_complete":
            continue
        matches.append((path.resolve(), receipt))
    if len(matches) != 1:
        raise KxbtcdHoldoutEvaluationError(
            f"expected exactly one matching completed development recovery receipt, found {len(matches)}"
        )
    path, receipt = matches[0]
    safety = receipt.get("safety")
    if not isinstance(safety, Mapping):
        raise KxbtcdHoldoutEvaluationError("development recovery receipt missing safety block")
    if safety.get("api_requests_made") != 0:
        raise KxbtcdHoldoutEvaluationError("development recovery was not offline")
    if safety.get("holdout_outcomes_materialized") is not False:
        raise KxbtcdHoldoutEvaluationError(
            "development recovery receipt does not prove untouched holdout"
        )
    if safety.get("external_predictive_feed_used") is not False:
        raise KxbtcdHoldoutEvaluationError("development recovery used external predictive feed")
    if safety.get("orders_placed") != 0:
        raise KxbtcdHoldoutEvaluationError("development recovery placed orders")
    if receipt.get("development_labels") != EXPECTED_DEVELOPMENT_LABELS:
        raise KxbtcdHoldoutEvaluationError("development recovery label count changed")
    if receipt.get("development_predictions") != EXPECTED_DEVELOPMENT_PREDICTIONS:
        raise KxbtcdHoldoutEvaluationError("development recovery prediction count changed")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise KxbtcdHoldoutEvaluationError("development recovery receipt missing artifacts")
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise KxbtcdHoldoutEvaluationError("development recovery artifact descriptor invalid")
        value = _required(artifact, "path")
        artifact_path = (repo / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
        if not artifact_path.exists():
            raise KxbtcdHoldoutEvaluationError(
                f"development recovery artifact missing: {artifact_path}"
            )
        actual = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual != _required(artifact, "sha256"):
            raise KxbtcdHoldoutEvaluationError("development recovery artifact hash mismatch")
    return DevelopmentRecoveryEvidence(
        receipt_path=path,
        receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        receipt=receipt,
    )


def holdout_request_plan(freeze: PreOutcomeFreeze) -> tuple[dict[str, str], ...]:
    """Return exactly the frozen holdout ticker request set; never development."""

    holdout_rows = [row for row in freeze.cross_sections if row.get("partition") == "holdout"]
    development_tickers = {
        _required(row, "ticker")
        for row in freeze.cross_sections
        if row.get("partition") == "development"
    }
    by_ticker: dict[str, dict[str, str]] = {}
    for row in holdout_rows:
        ticker = _required(row, "ticker")
        identity = {
            "event_ticker": _required(row, "event_ticker"),
            "source_cluster_id": _required(row, "source_cluster_id"),
            "ticker": ticker,
            "probe_role": _required(row, "probe_role"),
            "route_tier": _required(row, "quote_route_tier"),
        }
        current = by_ticker.get(ticker)
        if current is not None and current != identity:
            raise KxbtcdHoldoutEvaluationError(f"holdout ticker {ticker} identity changed")
        by_ticker[ticker] = identity
    if len(by_ticker) != EXPECTED_HOLDOUT_TICKERS:
        raise KxbtcdHoldoutEvaluationError(
            f"expected {EXPECTED_HOLDOUT_TICKERS} unique holdout tickers, found {len(by_ticker)}"
        )
    if set(by_ticker) & development_tickers:
        raise KxbtcdHoldoutEvaluationError("holdout request plan contains development ticker")
    if any(item["route_tier"] not in {"historical", "live"} for item in by_ticker.values()):
        raise KxbtcdHoldoutEvaluationError("holdout request plan has unsupported route tier")
    cluster_ids = {row["source_cluster_id"] for row in by_ticker.values()}
    if len(cluster_ids) != EXPECTED_HOLDOUT_CLUSTERS:
        raise KxbtcdHoldoutEvaluationError("holdout request plan cluster count changed")
    return tuple(sorted(by_ticker.values(), key=lambda row: row["ticker"]))


def collect_holdout_outcomes(
    client: RawFirstJsonClient,
    *,
    freeze: PreOutcomeFreeze,
    development_recovery: DevelopmentRecoveryEvidence,
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in holdout_request_plan(freeze):
        ticker = item["ticker"]
        route_tier = item["route_tier"]
        path = f"/historical/markets/{ticker}" if route_tier == "historical" else f"/markets/{ticker}"
        response = client.get_json(path)
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            raise KxbtcdHoldoutEvaluationError(f"outcome response for {ticker} missing market object")
        if _required(market, "ticker") != ticker:
            raise KxbtcdHoldoutEvaluationError(f"outcome response ticker mismatch for {ticker}")
        if _required(market, "event_ticker") != item["event_ticker"]:
            raise KxbtcdHoldoutEvaluationError(f"outcome response event mismatch for {ticker}")
        status = _required(market, "status").lower()
        if status != "finalized":
            raise KxbtcdHoldoutEvaluationError(f"market {ticker} is not finalized: {status}")
        result_text = _required(market, "result").lower()
        if result_text == "yes":
            outcome = "1"
        elif result_text == "no":
            outcome = "0"
        else:
            raise KxbtcdHoldoutEvaluationError(
                f"market {ticker} has unsupported finalized result {result_text!r}"
            )
        rows.append(
            {
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": freeze.receipt_sha256,
                "development_recovery_receipt_sha256": development_recovery.receipt_sha256,
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
    _validate_holdout_outcomes(rows, freeze, development_recovery)
    return tuple(rows)


def evaluate_holdout(
    *,
    freeze: PreOutcomeFreeze,
    development_recovery: DevelopmentRecoveryEvidence,
    outcomes: Sequence[Mapping[str, str]],
) -> HoldoutEvaluation:
    _validate_holdout_outcomes(outcomes, freeze, development_recovery)
    outcome_by_ticker = {
        _required(row, "ticker"): int(_required(row, "outcome")) for row in outcomes
    }
    holdout_rows = [row for row in freeze.cross_sections if row.get("partition") == "holdout"]
    groups: dict[str, list[Mapping[str, str]]] = {}
    for row in holdout_rows:
        groups.setdefault(_required(row, "cross_section_id"), []).append(row)

    predictions: list[dict[str, str]] = []
    for cross_id, group in sorted(groups.items()):
        ordered = sorted(group, key=lambda row: PROBE_ROLES.index(_required(row, "probe_role")))
        if tuple(_required(row, "probe_role") for row in ordered) != PROBE_ROLES:
            raise KxbtcdHoldoutEvaluationError(
                f"holdout cross-section {cross_id} probe roles changed"
            )
        q_raw = [Decimal(_required(row, "q_raw")) for row in ordered]
        q_mono = list(project_nonincreasing_l2(q_raw))
        labels = [outcome_by_ticker[_required(row, "ticker")] for row in ordered]
        if not (labels[0] >= labels[1] >= labels[2]):
            raise KxbtcdHoldoutEvaluationError(
                f"holdout outcome ladder is not monotone for cross-section {cross_id}: {labels}"
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
                    "development_recovery_receipt_sha256": development_recovery.receipt_sha256,
                    "event_ticker": _required(row, "event_ticker"),
                    "source_cluster_id": _required(row, "source_cluster_id"),
                    "time_band": _required(row, "time_band"),
                    "cross_section_id": cross_id,
                    "selected_end_period_ts": _required(row, "selected_end_period_ts"),
                    "selected_normalized_time_remaining": _required(
                        row, "selected_normalized_time_remaining"
                    ),
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

    if len(predictions) != EXPECTED_HOLDOUT_PREDICTIONS:
        raise KxbtcdHoldoutEvaluationError(
            f"expected {EXPECTED_HOLDOUT_PREDICTIONS} holdout predictions, found {len(predictions)}"
        )
    cluster_scores = _aggregate_by_cluster(
        predictions,
        freeze.receipt_sha256,
        development_recovery.receipt_sha256,
    )
    band_scores = _aggregate_by_band(
        predictions,
        freeze.receipt_sha256,
        development_recovery.receipt_sha256,
    )
    summary = _build_summary(
        predictions,
        cluster_scores,
        freeze,
        development_recovery,
    )
    return HoldoutEvaluation(
        outcomes=tuple(outcomes),
        predictions=tuple(predictions),
        cluster_scores=tuple(cluster_scores),
        band_scores=tuple(band_scores),
        summary=summary,
    )


def write_holdout_evaluation(
    output_dir: str | Path,
    *,
    evaluation: HoldoutEvaluation,
    run_id: str,
) -> tuple[Path, Path, Path, Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = (
        root / f"{run_id}_kxbtcd_holdout_outcomes.csv",
        root / f"{run_id}_kxbtcd_holdout_prediction_scores.csv",
        root / f"{run_id}_kxbtcd_holdout_cluster_scores.csv",
        root / f"{run_id}_kxbtcd_holdout_band_scores.csv",
        root / f"{run_id}_kxbtcd_holdout_summary.csv",
    )
    _write_csv(paths[0], OUTCOME_FIELDS, evaluation.outcomes)
    _write_csv(paths[1], PREDICTION_SCORE_FIELDS, evaluation.predictions)
    _write_csv(paths[2], CLUSTER_SCORE_FIELDS, evaluation.cluster_scores)
    _write_csv(paths[3], BAND_SCORE_FIELDS, evaluation.band_scores)
    _write_csv(paths[4], SUMMARY_FIELDS, (evaluation.summary,))
    return paths


def matching_failed_holdout_manifests(
    freeze: PreOutcomeFreeze,
    development_recovery: DevelopmentRecoveryEvidence,
    repository_root: str | Path = ".",
) -> tuple[Path, ...]:
    repo = Path(repository_root).resolve()
    root = repo / "data" / "manifests"
    matches: list[Path] = []
    for path in root.glob("**/collect_kxbtcd_holdout_outcomes_*.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("status") != "failed":
            continue
        collector = manifest.get("collector")
        if not isinstance(collector, Mapping) or collector.get("name") != "collect_kxbtcd_holdout_outcomes":
            continue
        arguments = manifest.get("arguments")
        if not isinstance(arguments, Mapping):
            continue
        if arguments.get("preoutcome_receipt_sha256") != freeze.receipt_sha256:
            continue
        if arguments.get("development_recovery_receipt_sha256") != development_recovery.receipt_sha256:
            continue
        if arguments.get("design_fingerprint") != design_fingerprint():
            continue
        if arguments.get("partition") != "holdout":
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches, key=lambda p: p.stat().st_mtime_ns))


def matching_completed_holdout_manifests(
    freeze: PreOutcomeFreeze,
    development_recovery: DevelopmentRecoveryEvidence,
    repository_root: str | Path = ".",
) -> tuple[Path, ...]:
    repo = Path(repository_root).resolve()
    root = repo / "data" / "manifests"
    matches: list[Path] = []
    for path in root.glob("**/collect_kxbtcd_holdout_outcomes_*.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("status") != "completed":
            continue
        collector = manifest.get("collector")
        arguments = manifest.get("arguments")
        if not isinstance(collector, Mapping) or not isinstance(arguments, Mapping):
            continue
        if collector.get("name") != "collect_kxbtcd_holdout_outcomes":
            continue
        if arguments.get("preoutcome_receipt_sha256") != freeze.receipt_sha256:
            continue
        if arguments.get("development_recovery_receipt_sha256") != development_recovery.receipt_sha256:
            continue
        if arguments.get("design_fingerprint") != design_fingerprint():
            continue
        if arguments.get("partition") != "holdout":
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches, key=lambda p: p.stat().st_mtime_ns))


def recover_holdout_outcomes_from_failed_manifest(
    *,
    freeze: PreOutcomeFreeze,
    development_recovery: DevelopmentRecoveryEvidence,
    manifest_path: str | Path,
    repository_root: str | Path = ".",
) -> tuple[dict[str, str], ...]:
    """Replay preserved holdout responses with zero API calls after a failed run."""

    repo = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdHoldoutEvaluationError("failed holdout manifest is unreadable") from exc
    if path not in matching_failed_holdout_manifests(
        freeze, development_recovery, repo
    ):
        raise KxbtcdHoldoutEvaluationError(
            "failed manifest does not match the frozen holdout experiment"
        )

    plan = holdout_request_plan(freeze)
    expected_by_path: dict[str, Mapping[str, str]] = {}
    expected_by_ticker = {item["ticker"]: item for item in plan}
    for item in plan:
        endpoint = (
            f"/historical/markets/{item['ticker']}"
            if item["route_tier"] == "historical"
            else f"/markets/{item['ticker']}"
        )
        expected_by_path[endpoint] = item

    development_paths: set[str] = set()
    for row in freeze.cross_sections:
        if row.get("partition") != "development":
            continue
        ticker = _required(row, "ticker")
        route_tier = _required(row, "quote_route_tier")
        endpoint = (
            f"/historical/markets/{ticker}"
            if route_tier == "historical"
            else f"/markets/{ticker}"
        )
        development_paths.add(endpoint)

    raw_descriptors = [
        item
        for item in manifest.get("files", [])
        if isinstance(item, Mapping) and item.get("role") == "raw_api_archive"
    ]
    if not raw_descriptors:
        raise KxbtcdHoldoutEvaluationError("failed holdout run preserved no raw API archive")

    successes: dict[str, Mapping[str, Any]] = {}
    for descriptor in raw_descriptors:
        spec = descriptor.get("path")
        if not isinstance(spec, Mapping):
            raise KxbtcdHoldoutEvaluationError("failed holdout raw descriptor missing path")
        raw_path = _resolve_stored_path(repo, spec)
        actual_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if actual_sha != _required(descriptor, "sha256"):
            raise KxbtcdHoldoutEvaluationError("failed holdout raw archive hash mismatch")
        with raw_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise KxbtcdHoldoutEvaluationError(
                        f"holdout recovery raw archive has blank line {line_number}"
                    )
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise KxbtcdHoldoutEvaluationError(
                        f"holdout recovery raw archive invalid JSON at line {line_number}"
                    ) from exc
                if record.get("schema_version") != "raw_http_exchange.v1":
                    raise KxbtcdHoldoutEvaluationError("holdout recovery raw schema changed")
                request = record.get("request")
                if not isinstance(request, Mapping):
                    raise KxbtcdHoldoutEvaluationError("holdout recovery raw record missing request")
                request_path = _required(request, "path")
                if request_path in development_paths:
                    raise KxbtcdHoldoutEvaluationError(
                        "failed holdout raw archive contains development request"
                    )
                if request_path not in expected_by_path:
                    raise KxbtcdHoldoutEvaluationError(
                        f"failed holdout raw archive contains unexpected request {request_path!r}"
                    )
                response = record.get("response")
                if not isinstance(response, Mapping) or response.get("status_code") != 200:
                    continue
                if record.get("error") is not None:
                    raise KxbtcdHoldoutEvaluationError(
                        f"successful holdout response for {request_path} also carries an error"
                    )
                ticker = expected_by_path[request_path]["ticker"]
                if ticker in successes:
                    raise KxbtcdHoldoutEvaluationError(
                        f"multiple successful preserved responses for holdout ticker {ticker}"
                    )
                successes[ticker] = record

    if set(successes) != set(expected_by_ticker):
        missing = sorted(set(expected_by_ticker) - set(successes))
        raise KxbtcdHoldoutEvaluationError(
            "failed holdout run does not contain one successful preserved response for every "
            f"holdout ticker; missing={missing}"
        )

    rows: list[dict[str, str]] = []
    for ticker in sorted(expected_by_ticker):
        item = expected_by_ticker[ticker]
        record = successes[ticker]
        response = record["response"]
        try:
            payload = json.loads(_required(response, "body_text"))
        except json.JSONDecodeError as exc:
            raise KxbtcdHoldoutEvaluationError(
                f"preserved holdout response body for {ticker} is not valid JSON"
            ) from exc
        market = payload.get("market") if isinstance(payload, Mapping) else None
        if not isinstance(market, Mapping):
            raise KxbtcdHoldoutEvaluationError(
                f"preserved holdout response for {ticker} missing market object"
            )
        if _required(market, "ticker") != ticker:
            raise KxbtcdHoldoutEvaluationError(f"preserved holdout ticker mismatch for {ticker}")
        if _required(market, "event_ticker") != item["event_ticker"]:
            raise KxbtcdHoldoutEvaluationError(f"preserved holdout event mismatch for {ticker}")
        status = _required(market, "status").lower()
        if status != "finalized":
            raise KxbtcdHoldoutEvaluationError(f"holdout market {ticker} is not finalized: {status}")
        result_text = _required(market, "result").lower()
        if result_text == "yes":
            outcome = "1"
        elif result_text == "no":
            outcome = "0"
        else:
            raise KxbtcdHoldoutEvaluationError(
                f"holdout market {ticker} has unsupported finalized result {result_text!r}"
            )
        request = record["request"]
        rows.append(
            {
                "schema_version": OUTCOME_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": freeze.receipt_sha256,
                "development_recovery_receipt_sha256": development_recovery.receipt_sha256,
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
    _validate_holdout_outcomes(rows, freeze, development_recovery)
    return tuple(rows)


def _validate_holdout_outcomes(
    rows: Sequence[Mapping[str, str]],
    freeze: PreOutcomeFreeze,
    development_recovery: DevelopmentRecoveryEvidence,
) -> None:
    plan = holdout_request_plan(freeze)
    expected = {row["ticker"]: row for row in plan}
    if len(rows) != EXPECTED_HOLDOUT_TICKERS:
        raise KxbtcdHoldoutEvaluationError(
            f"expected {EXPECTED_HOLDOUT_TICKERS} holdout labels, found {len(rows)}"
        )
    seen: set[str] = set()
    labels_by_cluster: dict[str, dict[str, int]] = {}
    for row in rows:
        if tuple(row.keys()) != OUTCOME_FIELDS:
            raise KxbtcdHoldoutEvaluationError("holdout outcome fields changed")
        ticker = _required(row, "ticker")
        if ticker in seen or ticker not in expected:
            raise KxbtcdHoldoutEvaluationError(f"unexpected or duplicate holdout ticker {ticker}")
        seen.add(ticker)
        expected_row = expected[ticker]
        for field in ("event_ticker", "source_cluster_id", "probe_role", "route_tier"):
            if _required(row, field) != expected_row[field]:
                raise KxbtcdHoldoutEvaluationError(
                    f"holdout outcome identity mismatch for {ticker}"
                )
        if _required(row, "design_fingerprint") != design_fingerprint():
            raise KxbtcdHoldoutEvaluationError("holdout outcome fingerprint mismatch")
        if _required(row, "preoutcome_receipt_sha256") != freeze.receipt_sha256:
            raise KxbtcdHoldoutEvaluationError("holdout outcome freeze receipt mismatch")
        if (
            _required(row, "development_recovery_receipt_sha256")
            != development_recovery.receipt_sha256
        ):
            raise KxbtcdHoldoutEvaluationError(
                "holdout outcome development-recovery receipt mismatch"
            )
        if _required(row, "market_status") != "finalized":
            raise KxbtcdHoldoutEvaluationError(f"holdout market {ticker} not finalized")
        outcome = _required(row, "outcome")
        result_text = _required(row, "result_text")
        if (result_text, outcome) not in {("yes", "1"), ("no", "0")}:
            raise KxbtcdHoldoutEvaluationError(f"holdout result mapping invalid for {ticker}")
        labels_by_cluster.setdefault(expected_row["source_cluster_id"], {})[
            expected_row["probe_role"]
        ] = int(outcome)
    if len(labels_by_cluster) != EXPECTED_HOLDOUT_CLUSTERS:
        raise KxbtcdHoldoutEvaluationError("holdout outcome cluster count changed")
    for cluster_id, labels in labels_by_cluster.items():
        if set(labels) != set(PROBE_ROLES):
            raise KxbtcdHoldoutEvaluationError(
                f"cluster {cluster_id} missing holdout labels"
            )
        ordered = [labels[role] for role in PROBE_ROLES]
        if not (ordered[0] >= ordered[1] >= ordered[2]):
            raise KxbtcdHoldoutEvaluationError(
                f"cluster {cluster_id} finalized outcomes violate threshold ordering: {ordered}"
            )


def _aggregate_by_cluster(
    predictions: Sequence[Mapping[str, str]],
    preoutcome_sha: str,
    development_recovery_sha: str,
) -> list[dict[str, str]]:
    groups: dict[str, list[Mapping[str, str]]] = {}
    for row in predictions:
        groups.setdefault(_required(row, "source_cluster_id"), []).append(row)
    output: list[dict[str, str]] = []
    for cluster_id, rows in sorted(groups.items()):
        if len(rows) != EXPECTED_PROBES_PER_CLUSTER * EXPECTED_BANDS_PER_CLUSTER:
            raise KxbtcdHoldoutEvaluationError(
                f"holdout cluster {cluster_id} prediction count changed"
            )
        event_ids = {_required(row, "event_ticker") for row in rows}
        if len(event_ids) != 1:
            raise KxbtcdHoldoutEvaluationError(
                f"holdout cluster {cluster_id} event identity changed"
            )
        output.append(
            {
                "schema_version": CLUSTER_SCORE_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": preoutcome_sha,
                "development_recovery_receipt_sha256": development_recovery_sha,
                "event_ticker": next(iter(event_ids)),
                "source_cluster_id": cluster_id,
                "prediction_count": str(len(rows)),
                **_score_stats(rows),
            }
        )
    if len(output) != EXPECTED_HOLDOUT_CLUSTERS:
        raise KxbtcdHoldoutEvaluationError("holdout cluster score count changed")
    return output


def _aggregate_by_band(
    predictions: Sequence[Mapping[str, str]],
    preoutcome_sha: str,
    development_recovery_sha: str,
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for band in TIME_BANDS:
        rows = [row for row in predictions if row.get("time_band") == band]
        clusters = {_required(row, "source_cluster_id") for row in rows}
        if len(clusters) != EXPECTED_HOLDOUT_CLUSTERS:
            raise KxbtcdHoldoutEvaluationError(
                f"band {band} holdout cluster count changed"
            )
        output.append(
            {
                "schema_version": BAND_SCORE_SCHEMA_VERSION,
                "experiment_id": EXPERIMENT_ID,
                "design_fingerprint": design_fingerprint(),
                "preoutcome_receipt_sha256": preoutcome_sha,
                "development_recovery_receipt_sha256": development_recovery_sha,
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
    development_recovery: DevelopmentRecoveryEvidence,
) -> dict[str, str]:
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
        "development_recovery_receipt_sha256": development_recovery.receipt_sha256,
        "development_cluster_count": str(EXPECTED_DEVELOPMENT_CLUSTERS),
        "holdout_cluster_count": str(EXPECTED_HOLDOUT_CLUSTERS),
        "holdout_ticker_count": str(EXPECTED_HOLDOUT_TICKERS),
        "prediction_count": str(len(predictions)),
        "raw_log_loss": _decimal_text(raw_ll),
        "monotone_log_loss": _decimal_text(mono_ll),
        "delta_log_loss": _decimal_text(raw_ll - mono_ll),
        "raw_brier": _decimal_text(raw_br),
        "monotone_brier": _decimal_text(mono_br),
        "delta_brier": _decimal_text(raw_br - mono_br),
        "raw_monotonicity_violation_rate": _decimal_text(violation),
        "mean_absolute_adjustment": _decimal_text(
            sum(adjustments, Decimal(0)) / Decimal(len(adjustments))
        ),
        "max_absolute_adjustment": _decimal_text(max(adjustments)),
        "design_fingerprint_unchanged": "true",
        "model_or_metric_change_after_development": "false",
        "holdout_outcomes_materialized": "true",
        "external_predictive_feed_used": "false",
        "orders_placed": "0",
        "status": "holdout_evaluation_complete",
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
        "raw_monotonicity_violation_rate": _decimal_text(
            _cross_section_violation_rate(rows)
        ),
        "mean_absolute_adjustment": _decimal_text(
            sum(adjustments, Decimal(0)) / Decimal(len(adjustments))
        ),
        "max_absolute_adjustment": _decimal_text(max(adjustments)),
    }


def _cross_section_violation_rate(rows: Sequence[Mapping[str, str]]) -> Decimal:
    by_cross: dict[str, bool] = {}
    for row in rows:
        cross_id = _required(row, "cross_section_id")
        value = _required(row, "cross_section_raw_monotonicity_violation") == "true"
        previous = by_cross.get(cross_id)
        if previous is not None and previous != value:
            raise KxbtcdHoldoutEvaluationError(
                f"cross-section {cross_id} violation flag changed"
            )
        by_cross[cross_id] = value
    if not by_cross:
        raise KxbtcdHoldoutEvaluationError("no holdout cross-sections to aggregate")
    return Decimal(sum(by_cross.values())) / Decimal(len(by_cross))


def _row_strike_anchor(row: Mapping[str, str]) -> str:
    explicit = str(row.get("strike_anchor") or "").strip()
    if explicit:
        return explicit
    values: list[Decimal] = []
    for field in ("functional_strike", "floor_strike", "cap_strike"):
        text = str(row.get(field) or "").strip()
        if text:
            values.append(Decimal(text))
            break
    if not values:
        raise KxbtcdHoldoutEvaluationError(
            f"holdout probe {_required(row, 'ticker')} has no strike coordinate"
        )
    return _decimal_text(values[0])


def _resolve_stored_path(repo: Path, spec: Mapping[str, Any]) -> Path:
    kind = _required(spec, "kind")
    value = _required(spec, "value")
    if kind == "repository_relative":
        path = (repo / value).resolve()
    elif kind == "absolute":
        path = Path(value).resolve()
    else:
        raise KxbtcdHoldoutEvaluationError(f"unsupported stored path kind {kind!r}")
    if not path.exists():
        raise KxbtcdHoldoutEvaluationError(f"referenced raw artifact is missing: {path}")
    return path


def _write_csv(
    path: Path,
    fields: Sequence[str],
    rows: Sequence[Mapping[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _mean_decimal(values: Sequence[str]) -> Decimal:
    if not values:
        raise KxbtcdHoldoutEvaluationError("cannot average empty holdout sequence")
    return sum((Decimal(value) for value in values), Decimal(0)) / Decimal(len(values))


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _required(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if value is None or not str(value).strip():
        raise KxbtcdHoldoutEvaluationError(f"required field {field!r} is missing")
    return str(value).strip()


def _required_attr(obj: Any, field: str) -> str:
    value = getattr(obj, field, None)
    if value is None or not str(value).strip():
        raise KxbtcdHoldoutEvaluationError(f"raw reference field {field!r} is missing")
    return str(value).strip()
