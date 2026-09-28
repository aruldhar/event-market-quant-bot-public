"""Checkpoint-14 offline failure analysis for the completed KXBTCD Candidate B.

The analyzer is deliberately label-firewalled:

* it reads only the canonical Checkpoint-13 train/validation prediction artifact;
* it never requests outcomes or imports an HTTP client;
* it rejects any prediction row outside train/validation;
* it uses the frozen Checkpoint-12 dataset only to join pre-outcome spread and
  structural-role context for those already-exposed development rows;
* it never reports or uses locked-test feature density;
* it does not fit Candidate C or any other model.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .kxbtcd_candidate_b_evaluation import (
    FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_PREOUTCOME_RUN_ID,
    FROZEN_SPLIT_FINGERPRINT,
    PREDICTION_FIELDS,
    load_frozen_preoutcome_dataset,
)
from .kxbtcd_candidate_c_predeclaration import (
    assign_contiguous_week_blocks,
    candidate_c_predeclaration_fingerprint,
)
from .run_manifest import resolve_stored_path
from .run_validation import RunValidationError, validate_run_manifest


class KxbtcdCandidateBFailureAnalysisError(RuntimeError):
    """Raised when Checkpoint-14 diagnostic invariants fail."""


CP13_RUN_ID = "collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631"
CP13_COLLECTOR = "collect_kxbtcd_candidate_b_train_validation"
EXPECTED_DEVELOPMENT_ROWS = 4645 + 719
EXPECTED_DEVELOPMENT_EVENTS = 175 + 56
ANALYSIS_SCHEMA_VERSION = "kxbtcd_candidate_b_failure_analysis.v2"
SLICE_SCHEMA_VERSION = "kxbtcd_candidate_b_failure_slice.v2"
TTC_ANCHORS_SECONDS = (3300, 3000, 2700, 2400, 2100, 1800)

SLICE_FIELDS = (
    "schema_version",
    "slice_type",
    "slice_value",
    "row_count",
    "event_count",
    "raw_event_weighted_log_loss",
    "candidate_b_event_weighted_log_loss",
    "delta_log_loss_raw_minus_candidate_b",
    "raw_event_weighted_brier",
    "candidate_b_event_weighted_brier",
    "delta_brier_raw_minus_candidate_b",
    "candidate_b_better_event_count",
    "candidate_b_worse_event_count",
    "candidate_b_tie_event_count",
)


@dataclass(frozen=True)
class DevelopmentPrediction:
    partition: str
    state_id: str
    event_ticker: str
    market_ticker: str
    utc_week_start: str
    event_close_time_utc: str
    time_to_close_seconds: float
    strike_dollars: float
    spread: float
    structural_role: str
    q_market: float
    candidate_b_probability: float
    outcome: int
    raw_log_loss: float
    candidate_b_log_loss: float
    raw_brier: float
    candidate_b_brier: float


@dataclass(frozen=True)
class SliceMetrics:
    row_count: int
    event_count: int
    raw_log_loss: float
    candidate_log_loss: float
    raw_brier: float
    candidate_brier: float
    better_events: int
    worse_events: int
    tie_events: int


@dataclass(frozen=True)
class FailureAnalysis:
    summary: dict[str, Any]
    slice_rows: tuple[dict[str, str], ...]


def _error(message: str) -> None:
    raise KxbtcdCandidateBFailureAnalysisError(message)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise KxbtcdCandidateBFailureAnalysisError(f"{name} must be numeric") from exc
    if not result.is_finite():
        _error(f"{name} must be finite")
    return result


def _float(value: Any, name: str) -> float:
    result = float(_decimal(value, name))
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _same_float_value(
    left: Any,
    right: Any,
    *,
    left_name: str,
    right_name: str,
) -> bool:
    """Compare values after the same binary-float conversion used by CP13.

    CP13 serializes float-derived numeric fields with ``.17g``. A frozen decimal
    such as ``0.72`` can therefore reappear as ``0.71999999999999997`` even
    though both strings map to the exact same IEEE-754 double. Comparing the
    parsed floats exactly preserves a fail-closed lineage check without treating
    harmless round-trip text differences as data changes.
    """
    return _float(left, left_name) == _float(right, right_name)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _float_text(value: float) -> str:
    return format(value, ".17g")


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateBFailureAnalysisError(f"could not read JSON {path}: {exc}") from exc
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
        raise KxbtcdCandidateBFailureAnalysisError(f"could not read CSV {path}: {exc}") from exc


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_exact_cp13_manifest(repo: Path) -> Path:
    root = repo / "data" / "manifests"
    matches = [path for path in root.rglob(f"{CP13_RUN_ID}.json") if path.is_file()]
    if len(matches) != 1:
        _error(f"expected exactly one canonical CP13 manifest; found {len(matches)}")
    return matches[0]


def _artifact_from_manifest(repo: Path, manifest: Mapping[str, Any], filename: str) -> Path:
    files = manifest.get("files")
    if not isinstance(files, list):
        _error("CP13 manifest has no files list")
    matches: list[Path] = []
    for descriptor in files:
        if not isinstance(descriptor, Mapping):
            continue
        stored = descriptor.get("path")
        if not isinstance(stored, Mapping):
            continue
        value = stored.get("value")
        if isinstance(value, str) and Path(value).name == filename:
            matches.append(resolve_stored_path(stored, repo))
    if len(matches) != 1:
        _error(f"expected exactly one CP13 artifact named {filename}; found {len(matches)}")
    if not matches[0].is_file():
        _error(f"CP13 artifact is missing: {matches[0]}")
    return matches[0]


def load_canonical_development_predictions(
    repository_root: str | Path = ".",
) -> tuple[tuple[DevelopmentPrediction, ...], dict[str, Any]]:
    """Load only canonical CP13 train/validation predictions plus pre-outcome context."""

    repo = Path(repository_root).resolve()
    manifest_path = _find_exact_cp13_manifest(repo)
    try:
        validated = validate_run_manifest(manifest_path, repository_root=repo)
    except RunValidationError as exc:
        raise KxbtcdCandidateBFailureAnalysisError(
            f"canonical CP13 manifest failed integrity validation: {exc}"
        ) from exc
    if validated.get("run_id") != CP13_RUN_ID:
        _error("validated CP13 run ID mismatch")

    manifest = _load_json(manifest_path)
    if manifest.get("run_id") != CP13_RUN_ID or manifest.get("status") != "completed":
        _error("canonical CP13 manifest identity/status mismatch")
    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != CP13_COLLECTOR:
        _error("canonical CP13 collector mismatch")
    result = manifest.get("result")
    if not isinstance(result, Mapping):
        _error("canonical CP13 result is missing")
    if result.get("dataset_fingerprint") != FROZEN_DATASET_FINGERPRINT:
        _error("canonical CP13 dataset fingerprint mismatch")
    if result.get("split_fingerprint") != FROZEN_SPLIT_FINGERPRINT:
        _error("canonical CP13 split fingerprint mismatch")
    if result.get("candidate_b_spec_fingerprint") != FROZEN_CANDIDATE_B_SPEC_FINGERPRINT:
        _error("canonical CP13 Candidate-B fingerprint mismatch")
    if result.get("locked_test_outcomes_opened") != 0:
        _error("CP13 manifest does not prove zero locked-test outcome openings")
    if result.get("locked_test_outcomes_materialized") is not False:
        _error("CP13 manifest indicates locked-test outcomes were materialized")
    if result.get("locked_test_final_refit_performed") is not False:
        _error("CP13 manifest indicates a locked-test final refit")
    if result.get("candidate_c_authorized") is not False:
        _error("CP13 manifest unexpectedly authorizes Candidate C")
    if result.get("execution_enabled") is not False or result.get("orders_placed") != 0:
        _error("CP13 manifest violates read-only execution boundary")

    predictions_name = f"{CP13_RUN_ID}_kxbtcd_candidate_b_predictions.csv"
    predictions_path = _artifact_from_manifest(repo, manifest, predictions_name)
    raw_predictions = _read_csv(predictions_path)
    if len(raw_predictions) != EXPECTED_DEVELOPMENT_ROWS:
        _error(
            f"canonical CP13 prediction row count changed: {len(raw_predictions)} != {EXPECTED_DEVELOPMENT_ROWS}"
        )

    frozen = load_frozen_preoutcome_dataset(repo)
    development_dataset_rows = {
        row["state_id"]: row
        for row in frozen.rows
        if row["partition"] in {"train", "validation"}
    }
    if len(development_dataset_rows) != EXPECTED_DEVELOPMENT_ROWS:
        _error("frozen development dataset row count changed")

    predictions: list[DevelopmentPrediction] = []
    seen_states: set[str] = set()
    development_events: set[str] = set()
    for index, row in enumerate(raw_predictions):
        if tuple(row.keys()) != tuple(PREDICTION_FIELDS):
            _error(f"prediction row {index} schema/order mismatch")
        partition = _text(row["partition"], f"prediction[{index}].partition")
        if partition not in {"train", "validation"}:
            _error(f"refusing non-development prediction partition {partition!r}")
        state_id = _text(row["state_id"], f"prediction[{index}].state_id")
        if state_id in seen_states:
            _error(f"duplicate development prediction state_id: {state_id}")
        seen_states.add(state_id)
        source = development_dataset_rows.get(state_id)
        if source is None:
            _error(f"prediction state is absent from train/validation pre-outcome rows: {state_id}")
        for field in ("event_ticker", "market_ticker", "partition", "utc_week_start"):
            if row[field] != source[field]:
                _error(f"prediction/pre-outcome mismatch for {state_id}.{field}")
        if not _same_float_value(
            row["q_market"],
            source["q_market"],
            left_name="prediction.q_market",
            right_name="preoutcome.q_market",
        ):
            _error(f"prediction/pre-outcome q_market mismatch for {state_id}")
        if not _same_float_value(
            row["time_to_close_seconds"],
            source["time_to_close_seconds"],
            left_name="prediction.ttc",
            right_name="preoutcome.ttc",
        ):
            _error(f"prediction/pre-outcome time-to-close mismatch for {state_id}")
        if not _same_float_value(
            row["strike_dollars"],
            source["strike_dollars"],
            left_name="prediction.strike",
            right_name="preoutcome.strike",
        ):
            _error(f"prediction/pre-outcome strike mismatch for {state_id}")
        market = row["market_ticker"]
        role = frozen.structural_role_by_market.get(market)
        if role is None:
            _error(f"development market has no frozen structural role: {market}")
        outcome = int(row["outcome"])
        if outcome not in {0, 1}:
            _error(f"prediction outcome must be binary for {state_id}")
        development_events.add(row["event_ticker"])
        predictions.append(
            DevelopmentPrediction(
                partition=partition,
                state_id=state_id,
                event_ticker=row["event_ticker"],
                market_ticker=market,
                utc_week_start=row["utc_week_start"],
                event_close_time_utc=row["event_close_time_utc"],
                time_to_close_seconds=_float(row["time_to_close_seconds"], "time_to_close_seconds"),
                strike_dollars=_float(row["strike_dollars"], "strike_dollars"),
                spread=_float(source["spread"], "spread"),
                structural_role=role,
                q_market=_float(row["q_market"], "q_market"),
                candidate_b_probability=_float(
                    row["candidate_b_probability"], "candidate_b_probability"
                ),
                outcome=outcome,
                raw_log_loss=_float(row["raw_log_loss"], "raw_log_loss"),
                candidate_b_log_loss=_float(
                    row["candidate_b_log_loss"], "candidate_b_log_loss"
                ),
                raw_brier=_float(row["raw_brier"], "raw_brier"),
                candidate_b_brier=_float(row["candidate_b_brier"], "candidate_b_brier"),
            )
        )

    if seen_states != set(development_dataset_rows):
        _error("canonical predictions do not exactly cover train+validation state IDs")
    if len(development_events) != EXPECTED_DEVELOPMENT_EVENTS:
        _error(
            f"development event count changed: {len(development_events)} != {EXPECTED_DEVELOPMENT_EVENTS}"
        )

    provenance = {
        "cp13_run_id": CP13_RUN_ID,
        "cp13_manifest": str(manifest_path),
        "cp13_manifest_sha256": _sha256(manifest_path),
        "cp13_predictions": str(predictions_path),
        "cp13_predictions_sha256": _sha256(predictions_path),
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "candidate_b_spec_fingerprint": FROZEN_CANDIDATE_B_SPEC_FINGERPRINT,
        "candidate_c_predeclaration_fingerprint": candidate_c_predeclaration_fingerprint(),
        "network_requests": 0,
        "locked_test_outcomes_opened": 0,
        "candidate_c_fit_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    return tuple(predictions), provenance


def _slice_metrics(rows: Sequence[DevelopmentPrediction]) -> SliceMetrics:
    if not rows:
        _error("cannot score an empty diagnostic slice")
    by_event: dict[str, list[DevelopmentPrediction]] = {}
    for row in rows:
        by_event.setdefault(row.event_ticker, []).append(row)
    raw_ll: list[float] = []
    cand_ll: list[float] = []
    raw_br: list[float] = []
    cand_br: list[float] = []
    better = worse = tie = 0
    for event in sorted(by_event):
        event_rows = by_event[event]
        rll = sum(row.raw_log_loss for row in event_rows) / len(event_rows)
        cll = sum(row.candidate_b_log_loss for row in event_rows) / len(event_rows)
        rbr = sum(row.raw_brier for row in event_rows) / len(event_rows)
        cbr = sum(row.candidate_b_brier for row in event_rows) / len(event_rows)
        raw_ll.append(rll)
        cand_ll.append(cll)
        raw_br.append(rbr)
        cand_br.append(cbr)
        delta = rll - cll
        if delta > 1e-15:
            better += 1
        elif delta < -1e-15:
            worse += 1
        else:
            tie += 1
    count = len(by_event)
    return SliceMetrics(
        row_count=len(rows),
        event_count=count,
        raw_log_loss=sum(raw_ll) / count,
        candidate_log_loss=sum(cand_ll) / count,
        raw_brier=sum(raw_br) / count,
        candidate_brier=sum(cand_br) / count,
        better_events=better,
        worse_events=worse,
        tie_events=tie,
    )


def _slice_row(slice_type: str, slice_value: str, rows: Sequence[DevelopmentPrediction]) -> dict[str, str]:
    metrics = _slice_metrics(rows)
    return {
        "schema_version": SLICE_SCHEMA_VERSION,
        "slice_type": slice_type,
        "slice_value": slice_value,
        "row_count": str(metrics.row_count),
        "event_count": str(metrics.event_count),
        "raw_event_weighted_log_loss": _float_text(metrics.raw_log_loss),
        "candidate_b_event_weighted_log_loss": _float_text(metrics.candidate_log_loss),
        "delta_log_loss_raw_minus_candidate_b": _float_text(
            metrics.raw_log_loss - metrics.candidate_log_loss
        ),
        "raw_event_weighted_brier": _float_text(metrics.raw_brier),
        "candidate_b_event_weighted_brier": _float_text(metrics.candidate_brier),
        "delta_brier_raw_minus_candidate_b": _float_text(
            metrics.raw_brier - metrics.candidate_brier
        ),
        "candidate_b_better_event_count": str(metrics.better_events),
        "candidate_b_worse_event_count": str(metrics.worse_events),
        "candidate_b_tie_event_count": str(metrics.tie_events),
    }


def _q_band(q: float) -> str:
    if not 0.0 <= q <= 1.0:
        _error(f"q_market outside [0,1]: {q}")
    index = min(int(q * 10.0), 9)
    lower = index / 10.0
    upper = (index + 1) / 10.0
    right = "]" if index == 9 else ")"
    return f"[{lower:.1f},{upper:.1f}{right}"


def _spread_band(spread: float) -> str:
    if spread < 0:
        _error("spread must be nonnegative")
    if spread == 0:
        return "0"
    if spread <= 0.01 + 1e-12:
        return "(0,0.01]"
    if spread <= 0.02 + 1e-12:
        return "(0.01,0.02]"
    if spread <= 0.05 + 1e-12:
        return "(0.02,0.05]"
    return ">0.05"


def _ttc_anchor(value: float) -> str:
    nearest = min(TTC_ANCHORS_SECONDS, key=lambda anchor: abs(value - anchor))
    if abs(value - nearest) > 60.000001:
        _error(f"time_to_close_seconds {value} is outside frozen anchor+staleness windows")
    return f"{nearest // 60}m"


def analyze_candidate_b_failure(
    rows: Sequence[DevelopmentPrediction], *, provenance: Mapping[str, Any]
) -> FailureAnalysis:
    """Produce simple aggregate diagnostics; no fitting or hypothesis selection."""

    if not rows:
        _error("development predictions are empty")
    if any(row.partition not in {"train", "validation"} for row in rows):
        _error("failure analysis may use train/validation rows only")
    if len({row.event_ticker for row in rows}) != EXPECTED_DEVELOPMENT_EVENTS:
        _error("failure analysis requires the exact 231 exposed development events")

    output: list[dict[str, str]] = []
    output.append(_slice_row("development", "all_exposed_train_plus_validation", rows))

    for partition in ("train", "validation"):
        selected = [row for row in rows if row.partition == partition]
        output.append(_slice_row("original_partition", partition, selected))

    week_blocks = assign_contiguous_week_blocks(row.utc_week_start for row in rows)
    for block in range(5):
        selected = [row for row in rows if week_blocks[row.utc_week_start] == block]
        output.append(_slice_row("chronological_week_block", f"B{block}", selected))

    for anchor in ("55m", "50m", "45m", "40m", "35m", "30m"):
        selected = [row for row in rows if _ttc_anchor(row.time_to_close_seconds) == anchor]
        if selected:
            output.append(_slice_row("ttc_anchor", anchor, selected))

    for role in ("q10", "q30", "q50", "q70", "q90"):
        selected = [row for row in rows if row.structural_role == role]
        if selected:
            output.append(_slice_row("structural_role", role, selected))

    q_bands = sorted({_q_band(row.q_market) for row in rows})
    for band in q_bands:
        selected = [row for row in rows if _q_band(row.q_market) == band]
        output.append(_slice_row("q_market_band", band, selected))

    spread_order = ("0", "(0,0.01]", "(0.01,0.02]", "(0.02,0.05]", ">0.05")
    for band in spread_order:
        selected = [row for row in rows if _spread_band(row.spread) == band]
        if selected:
            output.append(_slice_row("spread_band", band, selected))

    # Two deliberately narrow cross-tabs test whether the one-dimensional
    # failure patterns are actually the same regime. They remain descriptive
    # diagnostics only: no parameter is fit and no candidate is selected here.
    for q_band in q_bands:
        for spread_band in spread_order:
            selected = [
                row
                for row in rows
                if _q_band(row.q_market) == q_band
                and _spread_band(row.spread) == spread_band
            ]
            if selected:
                output.append(
                    _slice_row(
                        "q_market_band_x_spread_band",
                        f"q={q_band}|spread={spread_band}",
                        selected,
                    )
                )

    for block in range(5):
        for spread_band in spread_order:
            selected = [
                row
                for row in rows
                if week_blocks[row.utc_week_start] == block
                and _spread_band(row.spread) == spread_band
            ]
            if selected:
                output.append(
                    _slice_row(
                        "chronological_week_block_x_spread_band",
                        f"B{block}|spread={spread_band}",
                        selected,
                    )
                )

    overall = _slice_metrics(rows)
    block_summaries = [
        row for row in output if row["slice_type"] == "chronological_week_block"
    ]
    summary = {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        **dict(provenance),
        "development_row_count": len(rows),
        "development_event_count": len({row.event_ticker for row in rows}),
        "development_week_count": len({row.utc_week_start for row in rows}),
        "raw_development_event_weighted_log_loss": _float_text(overall.raw_log_loss),
        "candidate_b_development_event_weighted_log_loss": _float_text(
            overall.candidate_log_loss
        ),
        "development_delta_log_loss_raw_minus_candidate_b": _float_text(
            overall.raw_log_loss - overall.candidate_log_loss
        ),
        "raw_development_event_weighted_brier": _float_text(overall.raw_brier),
        "candidate_b_development_event_weighted_brier": _float_text(
            overall.candidate_brier
        ),
        "development_delta_brier_raw_minus_candidate_b": _float_text(
            overall.raw_brier - overall.candidate_brier
        ),
        "candidate_b_better_event_count": overall.better_events,
        "candidate_b_worse_event_count": overall.worse_events,
        "candidate_b_tie_event_count": overall.tie_events,
        "chronological_block_count": len(block_summaries),
        "diagnostic_dimensions": [
            "original_partition",
            "chronological_week_block",
            "ttc_anchor",
            "structural_role",
            "q_market_band",
            "spread_band",
            "q_market_band_x_spread_band",
            "chronological_week_block_x_spread_band",
        ],
        "interpretation_scope": (
            "development/exploratory diagnostics only; these results cannot promote or fit Candidate C"
        ),
        "locked_test_outcomes_opened": 0,
        "candidate_c_fit_performed": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    return FailureAnalysis(summary=summary, slice_rows=tuple(output))


def write_failure_analysis(
    output_dir: str | Path,
    *,
    analysis: FailureAnalysis,
) -> tuple[Path, Path]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary_path = root / "candidate_b_failure_analysis_summary.json"
    slices_path = root / "candidate_b_failure_analysis_slices.csv"
    summary_path.write_text(
        json.dumps(analysis.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with slices_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SLICE_FIELDS), lineterminator="\n")
        writer.writeheader()
        for row in analysis.slice_rows:
            if set(row) != set(SLICE_FIELDS):
                _error("slice output schema mismatch")
            writer.writerow({field: row[field] for field in SLICE_FIELDS})
    return summary_path, slices_path
