"""Checkpoint-20F Candidate-E H2 result closeout.

This module validates the already-completed one-time H2 validation and records
its frozen PASS decision. It does not collect outcomes, refit on H1+H2, open H3,
change features/candidates, tune anything, or enable execution.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .run_validation import validate_run_manifest

RUN_ID = "collect_kxbtcd_candidate_e_h2_20260817T234947707700Z_a6600041"
MANIFEST_PATH = Path(
    "data/manifests/2026/08/17/"
    "collect_kxbtcd_candidate_e_h2_20260817T234947707700Z_a6600041.json"
)
DERIVED_DIR = Path("data/derived/kxbtcd_candidate_e_h2_evaluation/2026/08/17")
SUMMARY_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h2_summary.json"
BLOCK_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h2_block_scores.csv"
PREDICTION_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h2_predictions.csv"
EVENT_SCORE_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h2_event_scores.csv"
OUTCOMES_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h2_outcomes.csv"
ATTEMPT_PATH = Path("data/analysis/kxbtcd_candidate_e_h2_evaluation/h2_attempt.json")

FAMILY_ID = "kxbtcd_independent_btc_offset_successor.v1"
DISTANCE_ID = "kxbtcd_btc_distance_offset_logistic.v1"

EXPECTED_SOURCE_COMMIT = "87297dbe6fcdb026d28b133bc02d8cc06db9463a"
H1_RESULT_FINGERPRINT = (
    "3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906"
)
FINAL_H1_MODEL_FINGERPRINT = (
    "d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a"
)
H2_VALIDATION_FINGERPRINT = (
    "57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9"
)
H2_IMPLEMENTATION_FINGERPRINT = (
    "0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e"
)
COHORT_MAP_FINGERPRINT = (
    "09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa"
)
ROW_UNIVERSE_FINGERPRINT = (
    "e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5"
)
EXPECTED_RESULT_FINGERPRINT = (
    "eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7"
)

EXPECTED_BETA_DISTANCE = "0.012310034918384302"
EXPECTED_RAW_LOG_LOSS = "0.11774919111369225"
EXPECTED_CANDIDATE_LOG_LOSS = "0.035893546124196762"
EXPECTED_LOG_LOSS_DELTA = "0.081855644989495491"
EXPECTED_RAW_BRIER = "0.022327771656461513"
EXPECTED_CANDIDATE_BRIER = "0.0099357895512881093"

H2_EVENT_COUNT = 750
H2_ROW_COUNT = 22354
H2_MARKET_COUNT = 3750
H2_BLOCKS = ("B0", "B1", "B2", "B3", "B4")
H2_EVENTS_PER_BLOCK = 150


class CandidateEH2ResultCloseoutError(RuntimeError):
    """Raised when the permanent H2 result no longer matches the frozen run."""


def _error(message: str) -> None:
    raise CandidateEH2ResultCloseoutError(message)


def _resolve(repo: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo / path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEH2ResultCloseoutError(
            f"could not read JSON {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be object: {path}")
    return value


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return tuple(reader.fieldnames or ()), tuple(dict(row) for row in reader)
    except OSError as exc:
        raise CandidateEH2ResultCloseoutError(
            f"could not read CSV {path}: {exc}"
        ) from exc


def canonical_summary_fingerprint(summary: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(summary),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_float_text(
    summary: Mapping[str, Any],
    key: str,
    expected: str,
) -> None:
    observed = str(summary.get(key, ""))
    if observed != expected:
        _error(f"H2 summary {key} changed: {observed!r} != {expected!r}")
    try:
        value = float(observed)
    except ValueError as exc:
        raise CandidateEH2ResultCloseoutError(
            f"H2 summary {key} is not numeric"
        ) from exc
    if not math.isfinite(value):
        _error(f"H2 summary {key} is non-finite")


def validate_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    expected_exact = {
        "schema_version": "kxbtcd_candidate_e_h2_evaluation_summary.v1",
        "checkpoint_id": "20E",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_ID,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "final_h1_model_fingerprint": FINAL_H1_MODEL_FINGERPRINT,
        "h2_validation_fingerprint": H2_VALIDATION_FINGERPRINT,
        "h2_implementation_fingerprint": H2_IMPLEMENTATION_FINGERPRINT,
        "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
        "H2_event_count": H2_EVENT_COUNT,
        "H2_row_count": H2_ROW_COUNT,
        "H2_market_count": H2_MARKET_COUNT,
        "beta_distance": EXPECTED_BETA_DISTANCE,
        "block_log_loss_win_count": 5,
        "latest_block_B4_win": True,
        "structural_coverage_ok": True,
        "final_h1_model_valid": True,
        "metrics_finite": True,
        "H2_validation_passed": True,
        "H2_permanently_exposed": True,
        "H3_outcomes_opened": False,
        "model_parameters_fitted_on_H2": False,
        "candidate_selection_on_H2_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, expected in expected_exact.items():
        if summary.get(key) != expected:
            _error(
                f"H2 summary {key} mismatch: "
                f"{summary.get(key)!r} != {expected!r}"
            )

    _require_float_text(summary, "raw_event_equal_log_loss", EXPECTED_RAW_LOG_LOSS)
    _require_float_text(
        summary,
        "candidate_event_equal_log_loss",
        EXPECTED_CANDIDATE_LOG_LOSS,
    )
    _require_float_text(
        summary,
        "raw_minus_candidate_log_loss",
        EXPECTED_LOG_LOSS_DELTA,
    )
    _require_float_text(summary, "raw_event_equal_brier", EXPECTED_RAW_BRIER)
    _require_float_text(
        summary,
        "candidate_event_equal_brier",
        EXPECTED_CANDIDATE_BRIER,
    )

    raw_brier = float(summary["raw_event_equal_brier"])
    candidate_brier = float(summary["candidate_event_equal_brier"])
    expected_brier_delta = raw_brier - candidate_brier
    observed_brier_delta = float(summary.get("raw_minus_candidate_brier", "nan"))
    if not math.isclose(
        observed_brier_delta,
        expected_brier_delta,
        rel_tol=1e-15,
        abs_tol=1e-15,
    ):
        _error("H2 pooled Brier delta is inconsistent with pooled scores")
    if observed_brier_delta < 0.0:
        _error("H2 pooled Brier gate no longer passes")

    median_delta = float(
        summary.get("median_event_raw_minus_candidate_log_loss", "nan")
    )
    if not math.isfinite(median_delta) or median_delta <= 0.0:
        _error("H2 median event log-loss delta is not strictly positive")

    block_deltas = summary.get("block_log_loss_deltas")
    if not isinstance(block_deltas, Mapping):
        _error("H2 block_log_loss_deltas missing")
    if tuple(block_deltas.keys()) != H2_BLOCKS:
        _error(
            "H2 block_log_loss_deltas order/identity changed: "
            f"{tuple(block_deltas.keys())}"
        )
    parsed = []
    for block in H2_BLOCKS:
        try:
            delta = float(block_deltas[block])
        except (TypeError, ValueError) as exc:
            raise CandidateEH2ResultCloseoutError(
                f"H2 block {block} log-loss delta is invalid"
            ) from exc
        if not math.isfinite(delta) or delta <= 0.0:
            _error(f"H2 block {block} is no longer a strict log-loss win")
        parsed.append(delta)
    if len(parsed) != 5:
        _error("H2 block delta count changed")

    fingerprint = canonical_summary_fingerprint(summary)
    if fingerprint != EXPECTED_RESULT_FINGERPRINT:
        _error(
            "H2 result fingerprint changed: "
            f"{fingerprint} != {EXPECTED_RESULT_FINGERPRINT}"
        )
    return dict(summary)


def validate_block_rows(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, Any],
) -> None:
    if len(rows) != 5:
        _error(f"expected 5 H2 block-score rows, found {len(rows)}")
    expected_deltas = summary["block_log_loss_deltas"]
    seen: set[str] = set()
    for row in rows:
        block = str(row.get("block_id", ""))
        if block in seen:
            _error(f"duplicate H2 block-score row {block}")
        seen.add(block)
        if block not in H2_BLOCKS:
            _error(f"unexpected H2 block-score identity {block}")
        if row.get("event_count") != str(H2_EVENTS_PER_BLOCK):
            _error(f"H2 block {block} event count changed")
        if row.get("candidate_beats_raw_log_loss") != "true":
            _error(f"H2 block {block} is not recorded as a strict win")
        observed_delta = float(row["raw_minus_candidate_log_loss"])
        if not math.isclose(
            observed_delta,
            float(expected_deltas[block]),
            rel_tol=1e-15,
            abs_tol=1e-15,
        ):
            _error(f"H2 block {block} delta differs from frozen summary")
        if observed_delta <= 0.0:
            _error(f"H2 block {block} no longer passes")
        raw_loss = float(row["raw_log_loss"])
        candidate_loss = float(row["candidate_log_loss"])
        if not math.isclose(
            raw_loss - candidate_loss,
            observed_delta,
            rel_tol=1e-15,
            abs_tol=1e-15,
        ):
            _error(f"H2 block {block} log-loss arithmetic mismatch")
    if seen != set(H2_BLOCKS):
        _error(f"H2 block-score identity set changed: {sorted(seen)}")


def validate_prediction_rows(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != H2_ROW_COUNT:
        _error(f"expected {H2_ROW_COUNT} H2 prediction rows, found {len(rows)}")
    state_ids: set[str] = set()
    events: set[str] = set()
    for index, row in enumerate(rows):
        if row.get("candidate_id") != DISTANCE_ID:
            _error(f"H2 prediction row {index} candidate changed")
        if row.get("h2_validation_fingerprint") != H2_VALIDATION_FINGERPRINT:
            _error(f"H2 prediction row {index} validation fingerprint changed")
        if row.get("final_h1_model_fingerprint") != FINAL_H1_MODEL_FINGERPRINT:
            _error(f"H2 prediction row {index} final-model fingerprint changed")
        if row.get("beta_distance") != EXPECTED_BETA_DISTANCE:
            _error(f"H2 prediction row {index} beta_distance changed")
        state_id = str(row.get("state_id", ""))
        if not state_id or state_id in state_ids:
            _error(f"H2 prediction row {index} duplicate/blank state_id")
        state_ids.add(state_id)
        event = str(row.get("event_ticker", ""))
        if not event:
            _error(f"H2 prediction row {index} blank event")
        events.add(event)
        probability = float(row["candidate_probability"])
        if not math.isfinite(probability) or not 0.0 < probability < 1.0:
            _error(f"H2 prediction row {index} candidate probability invalid")
    if len(events) != H2_EVENT_COUNT:
        _error(f"H2 prediction event count changed: {len(events)}")


def validate_event_score_rows(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != H2_EVENT_COUNT:
        _error(
            f"expected {H2_EVENT_COUNT} H2 event-score rows, found {len(rows)}"
        )
    events: set[str] = set()
    blocks: dict[str, int] = {}
    positive_event_deltas = 0
    for index, row in enumerate(rows):
        event = str(row.get("event_ticker", ""))
        if not event or event in events:
            _error(f"H2 event-score row {index} duplicate/blank event")
        events.add(event)
        block = str(row.get("block_id", ""))
        if block not in H2_BLOCKS:
            _error(f"H2 event-score row {index} invalid block")
        blocks[block] = blocks.get(block, 0) + 1
        delta = float(row["raw_minus_candidate_log_loss"])
        if not math.isfinite(delta):
            _error(f"H2 event-score row {index} non-finite delta")
        if delta > 0.0:
            positive_event_deltas += 1
    if blocks != {block: H2_EVENTS_PER_BLOCK for block in H2_BLOCKS}:
        _error(f"H2 event-score block counts changed: {blocks}")
    if positive_event_deltas <= H2_EVENT_COUNT // 2:
        _error(
            "H2 event-score signs no longer support a positive median event delta"
        )


def validate_outcome_rows(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != H2_MARKET_COUNT:
        _error(f"expected {H2_MARKET_COUNT} H2 outcomes, found {len(rows)}")
    markets: set[str] = set()
    for index, row in enumerate(rows):
        market = str(row.get("market_ticker", ""))
        if not market or market in markets:
            _error(f"H2 outcome row {index} duplicate/blank market")
        markets.add(market)
        expected = {
            "family_id": FAMILY_ID,
            "h2_validation_fingerprint": H2_VALIDATION_FINGERPRINT,
            "h2_implementation_fingerprint": H2_IMPLEMENTATION_FINGERPRINT,
            "final_h1_model_fingerprint": FINAL_H1_MODEL_FINGERPRINT,
            "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
            "stage": "H2",
            "market_status": "finalized",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                _error(f"H2 outcome row {index} {key} mismatch")
        if (row.get("result_text"), row.get("outcome")) not in {
            ("yes", "1"),
            ("no", "0"),
        }:
            _error(f"H2 outcome row {index} result/outcome mismatch")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            if not str(row.get(field, "")).strip():
                _error(f"H2 outcome row {index} {field} blank")


def validate_manifest(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    path = _resolve(repo, MANIFEST_PATH)
    result = validate_run_manifest(path, repository_root=repo)
    expected_result = {
        "run_id": RUN_ID,
        "collector": "collect_kxbtcd_candidate_e_h2",
        "status": "completed",
        "git_commit": EXPECTED_SOURCE_COMMIT,
        "git_worktree_dirty": False,
    }
    for key, value in expected_result.items():
        if result.get(key) != value:
            _error(
                f"H2 manifest validation {key} mismatch: "
                f"{result.get(key)!r} != {value!r}"
            )

    expected_artifact_summary = {
        "raw_file_count": 1,
        "raw_record_count": 3750,
        "raw_error_record_count": 0,
        "derived_csv_count": 6,
        "derived_row_count": 30652,
        "runtime_event_file_count": 1,
        "runtime_event_count": 3752,
        "runtime_error_event_count": 0,
    }
    if result.get("summary") != expected_artifact_summary:
        _error(
            "H2 manifest artifact summary changed: "
            f"{result.get('summary')!r} != {expected_artifact_summary!r}"
        )

    manifest = _read_json(path)
    payload = manifest.get("result")
    if not isinstance(payload, Mapping):
        _error("H2 manifest result payload missing")
    expected_payload = {
        "h2_result_fingerprint": EXPECTED_RESULT_FINGERPRINT,
        "h2_validation_fingerprint": H2_VALIDATION_FINGERPRINT,
        "h2_implementation_fingerprint": H2_IMPLEMENTATION_FINGERPRINT,
        "final_h1_model_fingerprint": FINAL_H1_MODEL_FINGERPRINT,
        "H2_validation_passed": True,
        "H2_permanently_exposed": True,
        "H3_outcomes_opened": False,
        "model_parameters_fitted_on_H2": False,
        "candidate_selection_on_H2_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "authentication_used": False,
        "posthoc_repair_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected_payload.items():
        if payload.get(key) != value:
            _error(f"H2 manifest result {key} mismatch")
    if payload.get("new_http_requests") != H2_MARKET_COUNT:
        _error("H2 fresh run HTTP request count changed")
    if payload.get("resume_recovered_outcomes") != 0:
        _error("canonical H2 run unexpectedly reports recovered outcomes")
    return dict(result)


def validate_attempt(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    attempt = _read_json(_resolve(repo, ATTEMPT_PATH))
    expected = {
        "schema_version": "kxbtcd_candidate_e_h2_attempt.v1",
        "checkpoint_id": "20E",
        "candidate_id": DISTANCE_ID,
        "h2_validation_fingerprint": H2_VALIDATION_FINGERPRINT,
        "h2_implementation_fingerprint": H2_IMPLEMENTATION_FINGERPRINT,
        "final_h1_model_fingerprint": FINAL_H1_MODEL_FINGERPRINT,
        "status": "h2_evaluation_completed",
        "H2_permanently_exposed": True,
        "fresh_second_H2_attempt_allowed": False,
        "resume_only_after_interruption": True,
        "H3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
        "result_fingerprint": EXPECTED_RESULT_FINGERPRINT,
    }
    for key, value in expected.items():
        if attempt.get(key) != value:
            _error(
                f"H2 attempt receipt {key} mismatch: "
                f"{attempt.get(key)!r} != {value!r}"
            )
    return attempt


def load_and_validate_result(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    validate_manifest(repo)

    summary = validate_summary(_read_json(_resolve(repo, SUMMARY_PATH)))

    _, blocks = _read_csv(_resolve(repo, BLOCK_PATH))
    validate_block_rows(blocks, summary)

    _, predictions = _read_csv(_resolve(repo, PREDICTION_PATH))
    validate_prediction_rows(predictions)

    _, event_scores = _read_csv(_resolve(repo, EVENT_SCORE_PATH))
    validate_event_score_rows(event_scores)

    _, outcomes = _read_csv(_resolve(repo, OUTCOMES_PATH))
    validate_outcome_rows(outcomes)

    validate_attempt(repo)
    return summary


def advancement_decision(summary: Mapping[str, Any]) -> dict[str, Any]:
    validate_summary(summary)
    return {
        "family_id": FAMILY_ID,
        "H2_result": "PASS",
        "selected_candidate_id": DISTANCE_ID,
        "frozen_beta_distance": EXPECTED_BETA_DISTANCE,
        "block_log_loss_win_count": 5,
        "latest_block_B4_win": True,
        "H2_permanently_exposed": True,
        "H3_outcomes_opened": False,
        "posthoc_H2_repair_authorized": False,
        "posthoc_H2_rescore_authorized": False,
        "new_candidate_on_H2_authorized": False,
        "next_step": (
            "fit the same fixed Distance specification exactly once on H1+H2, "
            "freeze that final parameter artifact, then separately freeze the "
            "one-time H3 locked-test procedure before opening H3 outcomes"
        ),
        "execution_enabled": False,
        "orders_placed": 0,
    }
