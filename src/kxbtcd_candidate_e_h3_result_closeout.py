"""Checkpoint-20J Candidate-E H3 result closeout.

This module validates the already-completed one-time H3 locked test and records
its frozen PASS decision. It does not collect outcomes, refit on H1+H2+H3,
consume the untouched reserve, alter the model, or enable execution.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .run_validation import validate_run_manifest

RUN_ID = "collect_kxbtcd_candidate_e_h3_20260818T010536143670Z_9a67efb1"
MANIFEST_PATH = Path(
    "data/manifests/2026/08/18/"
    "collect_kxbtcd_candidate_e_h3_20260818T010536143670Z_9a67efb1.json"
)
DERIVED_DIR = Path("data/derived/kxbtcd_candidate_e_h3_evaluation/2026/08/18")
SUMMARY_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h3_summary.json"
BLOCK_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h3_block_scores.csv"
PREDICTION_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h3_predictions.csv"
EVENT_SCORE_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h3_event_scores.csv"
OUTCOMES_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h3_outcomes.csv"
ATTEMPT_PATH = Path("data/analysis/kxbtcd_candidate_e_h3_evaluation/h3_attempt.json")

FAMILY_ID = "kxbtcd_independent_btc_offset_successor.v1"
DISTANCE_ID = "kxbtcd_btc_distance_offset_logistic.v1"

EXPECTED_SOURCE_COMMIT = "990b307272ef3a5f4beef91173532490d5dbd318"
H1_RESULT_FINGERPRINT = (
    "3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906"
)
H2_RESULT_FINGERPRINT = (
    "eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7"
)
FINAL_H1_H2_MODEL_FINGERPRINT = (
    "1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842"
)
H3_VALIDATION_FINGERPRINT = (
    "a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197"
)
H3_IMPLEMENTATION_FINGERPRINT = (
    "6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc"
)
COHORT_MAP_FINGERPRINT = (
    "09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa"
)
ROW_UNIVERSE_FINGERPRINT = (
    "e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5"
)
EXPECTED_RESULT_FINGERPRINT = (
    "436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54"
)

EXPECTED_BETA_DISTANCE = "0.013805016135330063"
EXPECTED_RAW_LOG_LOSS = "0.13793316358637769"
EXPECTED_CANDIDATE_LOG_LOSS = "0.038920564033036092"
EXPECTED_LOG_LOSS_DELTA = "0.099012599553341601"
EXPECTED_RAW_BRIER = "0.027664663135376771"
EXPECTED_CANDIDATE_BRIER = "0.01025442810344244"

H3_EVENT_COUNT = 750
H3_ROW_COUNT = 22409
H3_MARKET_COUNT = 3750
H3_BLOCKS = ("B0", "B1", "B2", "B3", "B4")
H3_EVENTS_PER_BLOCK = 150


class CandidateEH3ResultCloseoutError(RuntimeError):
    """Raised when the permanent H3 result no longer matches the frozen run."""


def _error(message: str) -> None:
    raise CandidateEH3ResultCloseoutError(message)


def _resolve(repo: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo / path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEH3ResultCloseoutError(
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
        raise CandidateEH3ResultCloseoutError(
            f"could not read CSV {path}: {exc}"
        ) from exc


def canonical_summary_fingerprint(summary: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(summary),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_float_text(
    summary: Mapping[str, Any],
    key: str,
    expected: str,
) -> None:
    observed = str(summary.get(key, ""))
    if observed != expected:
        _error(f"H3 summary {key} changed: {observed!r} != {expected!r}")
    try:
        value = float(observed)
    except ValueError as exc:
        raise CandidateEH3ResultCloseoutError(
            f"H3 summary {key} is not numeric"
        ) from exc
    if not math.isfinite(value):
        _error(f"H3 summary {key} is non-finite")


def validate_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    expected_exact = {
        "schema_version": "kxbtcd_candidate_e_h3_evaluation_summary.v1",
        "checkpoint_id": "20I",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_ID,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
        "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
        "h3_implementation_fingerprint": H3_IMPLEMENTATION_FINGERPRINT,
        "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
        "H3_event_count": H3_EVENT_COUNT,
        "H3_row_count": H3_ROW_COUNT,
        "H3_market_count": H3_MARKET_COUNT,
        "beta_distance": EXPECTED_BETA_DISTANCE,
        "block_log_loss_win_count": 5,
        "latest_block_B4_win": True,
        "structural_coverage_ok": True,
        "final_h1_h2_model_valid": True,
        "metrics_finite": True,
        "H3_validation_passed": True,
        "H3_permanently_exposed": True,
        "model_parameters_fitted_on_H3": False,
        "candidate_selection_on_H3_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, expected in expected_exact.items():
        if summary.get(key) != expected:
            _error(
                f"H3 summary {key} mismatch: "
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

    brier_delta = float(summary.get("raw_minus_candidate_brier", "nan"))
    expected_brier_delta = (
        float(summary["raw_event_equal_brier"])
        - float(summary["candidate_event_equal_brier"])
    )
    if not math.isclose(
        brier_delta,
        expected_brier_delta,
        rel_tol=1e-15,
        abs_tol=1e-15,
    ):
        _error("H3 pooled Brier delta is inconsistent with pooled scores")
    if brier_delta < 0.0:
        _error("H3 pooled Brier gate no longer passes")

    median_delta = float(
        summary.get("median_event_raw_minus_candidate_log_loss", "nan")
    )
    if not math.isfinite(median_delta) or median_delta <= 0.0:
        _error("H3 median event log-loss delta is not strictly positive")

    block_deltas = summary.get("block_log_loss_deltas")
    if not isinstance(block_deltas, Mapping):
        _error("H3 block_log_loss_deltas missing")
    if tuple(block_deltas.keys()) != H3_BLOCKS:
        _error(
            "H3 block_log_loss_deltas order/identity changed: "
            f"{tuple(block_deltas.keys())}"
        )
    for block in H3_BLOCKS:
        try:
            delta = float(block_deltas[block])
        except (TypeError, ValueError) as exc:
            raise CandidateEH3ResultCloseoutError(
                f"H3 block {block} log-loss delta is invalid"
            ) from exc
        if not math.isfinite(delta) or delta <= 0.0:
            _error(f"H3 block {block} is no longer a strict log-loss win")

    fingerprint = canonical_summary_fingerprint(summary)
    if fingerprint != EXPECTED_RESULT_FINGERPRINT:
        _error(
            "H3 result fingerprint changed: "
            f"{fingerprint} != {EXPECTED_RESULT_FINGERPRINT}"
        )
    return dict(summary)


def validate_block_rows(
    rows: Sequence[Mapping[str, str]],
    summary: Mapping[str, Any],
) -> None:
    if len(rows) != 5:
        _error(f"expected 5 H3 block-score rows, found {len(rows)}")
    expected_deltas = summary["block_log_loss_deltas"]
    seen: set[str] = set()
    for row in rows:
        block = str(row.get("block_id", ""))
        if block in seen:
            _error(f"duplicate H3 block-score row {block}")
        seen.add(block)
        if block not in H3_BLOCKS:
            _error(f"unexpected H3 block-score identity {block}")
        if row.get("event_count") != str(H3_EVENTS_PER_BLOCK):
            _error(f"H3 block {block} event count changed")
        if row.get("candidate_beats_raw_log_loss") != "true":
            _error(f"H3 block {block} is not recorded as a strict win")
        observed_delta = float(row["raw_minus_candidate_log_loss"])
        if not math.isclose(
            observed_delta,
            float(expected_deltas[block]),
            rel_tol=1e-15,
            abs_tol=1e-15,
        ):
            _error(f"H3 block {block} delta differs from frozen summary")
        if observed_delta <= 0.0:
            _error(f"H3 block {block} no longer passes")
        raw_loss = float(row["raw_log_loss"])
        candidate_loss = float(row["candidate_log_loss"])
        if not math.isclose(
            raw_loss - candidate_loss,
            observed_delta,
            rel_tol=1e-15,
            abs_tol=1e-15,
        ):
            _error(f"H3 block {block} log-loss arithmetic mismatch")
    if seen != set(H3_BLOCKS):
        _error(f"H3 block-score identity set changed: {sorted(seen)}")


def validate_prediction_rows(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != H3_ROW_COUNT:
        _error(f"expected {H3_ROW_COUNT} H3 prediction rows, found {len(rows)}")
    state_ids: set[str] = set()
    events: set[str] = set()
    for index, row in enumerate(rows):
        if row.get("candidate_id") != DISTANCE_ID:
            _error(f"H3 prediction row {index} candidate changed")
        if row.get("h3_validation_fingerprint") != H3_VALIDATION_FINGERPRINT:
            _error(f"H3 prediction row {index} validation fingerprint changed")
        if (
            row.get("final_h1_h2_model_fingerprint")
            != FINAL_H1_H2_MODEL_FINGERPRINT
        ):
            _error(f"H3 prediction row {index} final-model fingerprint changed")
        if row.get("beta_distance") != EXPECTED_BETA_DISTANCE:
            _error(f"H3 prediction row {index} beta_distance changed")
        state_id = str(row.get("state_id", ""))
        if not state_id or state_id in state_ids:
            _error(f"H3 prediction row {index} duplicate/blank state_id")
        state_ids.add(state_id)
        event = str(row.get("event_ticker", ""))
        if not event:
            _error(f"H3 prediction row {index} blank event")
        events.add(event)
        probability = float(row["candidate_probability"])
        if not math.isfinite(probability) or not 0.0 < probability < 1.0:
            _error(f"H3 prediction row {index} candidate probability invalid")
    if len(events) != H3_EVENT_COUNT:
        _error(f"H3 prediction event count changed: {len(events)}")


def validate_event_score_rows(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != H3_EVENT_COUNT:
        _error(
            f"expected {H3_EVENT_COUNT} H3 event-score rows, found {len(rows)}"
        )
    events: set[str] = set()
    blocks: dict[str, int] = {}
    positive_deltas = 0
    for index, row in enumerate(rows):
        event = str(row.get("event_ticker", ""))
        if not event or event in events:
            _error(f"H3 event-score row {index} duplicate/blank event")
        events.add(event)
        block = str(row.get("block_id", ""))
        if block not in H3_BLOCKS:
            _error(f"H3 event-score row {index} invalid block")
        blocks[block] = blocks.get(block, 0) + 1
        delta = float(row["raw_minus_candidate_log_loss"])
        if not math.isfinite(delta):
            _error(f"H3 event-score row {index} non-finite delta")
        if delta > 0.0:
            positive_deltas += 1
    if blocks != {block: H3_EVENTS_PER_BLOCK for block in H3_BLOCKS}:
        _error(f"H3 event-score block counts changed: {blocks}")
    if positive_deltas <= H3_EVENT_COUNT // 2:
        _error(
            "H3 event-score signs no longer support a positive median event delta"
        )


def validate_outcome_rows(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != H3_MARKET_COUNT:
        _error(f"expected {H3_MARKET_COUNT} H3 outcomes, found {len(rows)}")
    markets: set[str] = set()
    for index, row in enumerate(rows):
        market = str(row.get("market_ticker", ""))
        if not market or market in markets:
            _error(f"H3 outcome row {index} duplicate/blank market")
        markets.add(market)
        expected = {
            "family_id": FAMILY_ID,
            "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
            "h3_implementation_fingerprint": H3_IMPLEMENTATION_FINGERPRINT,
            "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
            "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
            "stage": "H3",
            "market_status": "finalized",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                _error(f"H3 outcome row {index} {key} mismatch")
        if (row.get("result_text"), row.get("outcome")) not in {
            ("yes", "1"),
            ("no", "0"),
        }:
            _error(f"H3 outcome row {index} result/outcome mismatch")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            if not str(row.get(field, "")).strip():
                _error(f"H3 outcome row {index} {field} blank")


def validate_manifest(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    path = _resolve(repo, MANIFEST_PATH)
    result = validate_run_manifest(path, repository_root=repo)

    expected_result = {
        "run_id": RUN_ID,
        "collector": "collect_kxbtcd_candidate_e_h3",
        "status": "completed",
        "git_commit": EXPECTED_SOURCE_COMMIT,
        "git_worktree_dirty": False,
    }
    for key, value in expected_result.items():
        if result.get(key) != value:
            _error(
                f"H3 manifest validation {key} mismatch: "
                f"{result.get(key)!r} != {value!r}"
            )

    expected_artifact_summary = {
        "raw_file_count": 1,
        "raw_record_count": 3750,
        "raw_error_record_count": 0,
        "derived_csv_count": 6,
        "derived_row_count": 30707,
        "runtime_event_file_count": 1,
        "runtime_event_count": 3752,
        "runtime_error_event_count": 0,
    }
    if result.get("summary") != expected_artifact_summary:
        _error(
            "H3 manifest artifact summary changed: "
            f"{result.get('summary')!r} != {expected_artifact_summary!r}"
        )

    manifest = _read_json(path)
    payload = manifest.get("result")
    if not isinstance(payload, Mapping):
        _error("H3 manifest result payload missing")
    expected_payload = {
        "h3_result_fingerprint": EXPECTED_RESULT_FINGERPRINT,
        "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
        "h3_implementation_fingerprint": H3_IMPLEMENTATION_FINGERPRINT,
        "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
        "H3_validation_passed": True,
        "H3_permanently_exposed": True,
        "model_parameters_fitted_on_H3": False,
        "candidate_selection_on_H3_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "authentication_used": False,
        "posthoc_repair_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected_payload.items():
        if payload.get(key) != value:
            _error(f"H3 manifest result {key} mismatch")
    if payload.get("new_http_requests") != H3_MARKET_COUNT:
        _error("H3 fresh run HTTP request count changed")
    if payload.get("resume_recovered_outcomes") != 0:
        _error("canonical H3 run unexpectedly reports recovered outcomes")
    return dict(result)


def validate_attempt(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    attempt = _read_json(_resolve(repo, ATTEMPT_PATH))
    expected = {
        "schema_version": "kxbtcd_candidate_e_h3_attempt.v1",
        "checkpoint_id": "20I",
        "candidate_id": DISTANCE_ID,
        "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
        "h3_implementation_fingerprint": H3_IMPLEMENTATION_FINGERPRINT,
        "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
        "status": "h3_evaluation_completed",
        "H3_permanently_exposed": True,
        "fresh_second_H3_attempt_allowed": False,
        "resume_only_after_interruption": True,
        "execution_enabled": False,
        "orders_placed": 0,
        "result_fingerprint": EXPECTED_RESULT_FINGERPRINT,
    }
    for key, value in expected.items():
        if attempt.get(key) != value:
            _error(
                f"H3 attempt receipt {key} mismatch: "
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
        "H3_result": "PASS",
        "candidate_id": DISTANCE_ID,
        "frozen_beta_distance": EXPECTED_BETA_DISTANCE,
        "block_log_loss_win_count": 5,
        "latest_block_B4_win": True,
        "historical_generalization_program": "PASS",
        "H3_permanently_exposed": True,
        "posthoc_H3_repair_authorized": False,
        "posthoc_H3_rescore_authorized": False,
        "next_step": (
            "freeze the post-H3 champion protocol before refitting on H1+H2+H3; "
            "preserve a meaningful portion of the remaining untouched reserve and "
            "separately design read-only prospective shadow confirmation"
        ),
        "execution_enabled": False,
        "orders_placed": 0,
    }
