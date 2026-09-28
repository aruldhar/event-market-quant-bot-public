"""Checkpoint-20B Candidate-E H1 result closeout.

This module validates the already-completed H1 evaluation and encodes the frozen
selection decision. It does not collect outcomes, fit/refit a model, open H2/H3,
or enable execution.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .run_validation import validate_run_manifest

RUN_ID = "collect_kxbtcd_candidate_e_h1_20260817T213832954574Z_d3fb6dbf"
MANIFEST_PATH = Path(
    "data/manifests/2026/08/17/"
    "collect_kxbtcd_candidate_e_h1_20260817T213832954574Z_d3fb6dbf.json"
)
DERIVED_DIR = Path("data/derived/kxbtcd_candidate_e_h1_evaluation/2026/08/17")
SUMMARY_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h1_summary.json"
FOLD_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h1_fold_scores.csv"
COEFFICIENT_PATH = DERIVED_DIR / f"{RUN_ID}_candidate_e_h1_coefficients.csv"
ATTEMPT_PATH = Path("data/analysis/kxbtcd_candidate_e_h1_evaluation/h1_attempt.json")

FAMILY_ID = "kxbtcd_independent_btc_offset_successor.v1"
DISTANCE_ID = "kxbtcd_btc_distance_offset_logistic.v1"
MOMENTUM_ID = "kxbtcd_btc_distance_momentum_offset_logistic.v1"

H1_EVALUATION_FINGERPRINT = (
    "cbbca76de2dd87edd6c6bc4f21ae1005fbd1402a3bb85374e7699c8fb5fb7d14"
)
COHORT_MAP_FINGERPRINT = (
    "09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa"
)
ROW_UNIVERSE_FINGERPRINT = (
    "e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5"
)
EXPECTED_RESULT_FINGERPRINT = (
    "3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906"
)
EXPECTED_SOURCE_COMMIT = "8fd298c3400365df247c4e55032408a12fabe195"

EXPECTED_SUMMARY = {
    "schema_version": "kxbtcd_candidate_e_h1_evaluation_summary.v1",
    "family_id": FAMILY_ID,
    "h1_evaluation_fingerprint": H1_EVALUATION_FINGERPRINT,
    "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
    "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
    "H1_event_count": 1500,
    "H1_row_count": 36314,
    "OOF_scored_event_count": 1070,
    "distance_raw_event_equal_log_loss": "0.10494755188081126",
    "distance_candidate_event_equal_log_loss": "0.03379679620851983",
    "distance_raw_minus_candidate_log_loss": "0.071150755672291427",
    "distance_raw_event_equal_brier": "0.020374750709011895",
    "distance_candidate_event_equal_brier": "0.0090293992615540601",
    "distance_raw_minus_candidate_brier": "0.011345351447457835",
    "distance_median_event_log_loss_delta": "0.044861126287211117",
    "distance_raw_gate_passed": True,
    "momentum_raw_event_equal_log_loss": "0.10494755188081126",
    "momentum_candidate_event_equal_log_loss": "0.033794328892189064",
    "momentum_raw_minus_candidate_log_loss": "0.0711532229886222",
    "momentum_raw_event_equal_brier": "0.020374750709011895",
    "momentum_candidate_event_equal_brier": "0.0090268882138988659",
    "momentum_raw_minus_candidate_brier": "0.011347862495113029",
    "momentum_median_event_log_loss_delta": "0.044907202508890312",
    "momentum_raw_gate_passed": True,
    "nested_distance_minus_momentum_log_loss": "2.4673163307592505e-06",
    "nested_distance_minus_momentum_brier": "2.5110476552184929e-06",
    "nested_median_event_log_loss_delta": "3.6902389728145054e-05",
    "momentum_nested_complexity_gate_passed": False,
    "selection": DISTANCE_ID,
    "H1_permanently_development_exposed": True,
    "H2_outcomes_opened": False,
    "H3_outcomes_opened": False,
    "posthoc_repair_performed": False,
    "feature_change_performed": False,
    "execution_enabled": False,
    "orders_placed": 0,
}

EXPECTED_FOLD_LOG_LOSSES = {
    (DISTANCE_ID, "B2"): ("0.093684502220090865", "0.029051861012645085"),
    (DISTANCE_ID, "B3"): ("0.12302918031242148", "0.047419469633196702"),
    (DISTANCE_ID, "B4"): ("0.11679455386971177", "0.046742849808794153"),
    (DISTANCE_ID, "B5"): ("0.099600791943792746", "0.031252646282291463"),
    (DISTANCE_ID, "B6"): ("0.091628731058039634", "0.014517154305671688"),
    (MOMENTUM_ID, "B2"): ("0.093684502220090865", "0.029095643179052749"),
    (MOMENTUM_ID, "B3"): ("0.12302918031242148", "0.047474599718853823"),
    (MOMENTUM_ID, "B4"): ("0.11679455386971177", "0.046667401094384733"),
    (MOMENTUM_ID, "B5"): ("0.099600791943792746", "0.031262413260748696"),
    (MOMENTUM_ID, "B6"): ("0.091628731058039634", "0.014471587207905503"),
}

EXPECTED_COEFFICIENTS = {
    (DISTANCE_ID, "B2"): ("0.0081323383310510297", ""),
    (DISTANCE_ID, "B3"): ("0.0095589432277629807", ""),
    (DISTANCE_ID, "B4"): ("0.010172158015085328", ""),
    (DISTANCE_ID, "B5"): ("0.010887612715427673", ""),
    (DISTANCE_ID, "B6"): ("0.011430502474609366", ""),
    (MOMENTUM_ID, "B2"): ("0.0081814345452425261", "-0.0046668713049018524"),
    (MOMENTUM_ID, "B3"): ("0.0095989058569614649", "-0.0043868382514955905"),
    (MOMENTUM_ID, "B4"): ("0.01019923586183839", "-0.0039735264782275017"),
    (MOMENTUM_ID, "B5"): ("0.010918049920250599", "-0.0043955867905513439"),
    (MOMENTUM_ID, "B6"): ("0.011460281132241925", "-0.0042615767375541423"),
}


class CandidateEH1ResultCloseoutError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise CandidateEH1ResultCloseoutError(message)


def _resolve(repo: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo / path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEH1ResultCloseoutError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be an object: {path}")
    return value


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as exc:
        raise CandidateEH1ResultCloseoutError(f"could not read CSV {path}: {exc}") from exc


def canonical_summary_fingerprint(summary: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(summary), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    if dict(summary) != EXPECTED_SUMMARY:
        missing = sorted(set(EXPECTED_SUMMARY) - set(summary))
        extra = sorted(set(summary) - set(EXPECTED_SUMMARY))
        changed = sorted(
            key for key in set(EXPECTED_SUMMARY) & set(summary)
            if summary[key] != EXPECTED_SUMMARY[key]
        )
        _error(
            "H1 summary differs from frozen result; "
            f"missing={missing}, extra={extra}, changed={changed}"
        )
    fingerprint = canonical_summary_fingerprint(summary)
    if fingerprint != EXPECTED_RESULT_FINGERPRINT:
        _error(f"H1 result fingerprint changed: {fingerprint}")
    return dict(summary)


def validate_fold_rows(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != 10:
        _error(f"expected 10 H1 fold rows, found {len(rows)}")
    seen: set[tuple[str, str]] = set()
    momentum_wins = 0
    by_key: dict[tuple[str, str], Mapping[str, str]] = {}
    for row in rows:
        key = (str(row.get("candidate_id")), str(row.get("score_block")))
        if key in seen:
            _error(f"duplicate H1 fold row {key}")
        seen.add(key)
        by_key[key] = row
        expected = EXPECTED_FOLD_LOG_LOSSES.get(key)
        if expected is None:
            _error(f"unexpected H1 fold identity {key}")
        if (row.get("raw_log_loss"), row.get("candidate_log_loss")) != expected:
            _error(f"H1 fold log loss changed for {key}")

    if set(by_key) != set(EXPECTED_FOLD_LOG_LOSSES):
        _error("H1 fold identity set changed")

    for block in ("B2", "B3", "B4", "B5", "B6"):
        d = float(by_key[(DISTANCE_ID, block)]["candidate_log_loss"])
        m = float(by_key[(MOMENTUM_ID, block)]["candidate_log_loss"])
        if m < d:
            momentum_wins += 1
    if momentum_wins != 2:
        _error(f"nested block-win count changed: expected 2, found {momentum_wins}")


def validate_coefficients(rows: Sequence[Mapping[str, str]]) -> None:
    if len(rows) != 10:
        _error(f"expected 10 H1 coefficient rows, found {len(rows)}")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (str(row.get("candidate_id")), str(row.get("score_block")))
        if key in seen:
            _error(f"duplicate H1 coefficient row {key}")
        seen.add(key)
        expected = EXPECTED_COEFFICIENTS.get(key)
        if expected is None:
            _error(f"unexpected H1 coefficient identity {key}")
        observed = (str(row.get("beta_distance", "")), str(row.get("beta_momentum", "")))
        if observed != expected:
            _error(f"H1 coefficients changed for {key}: {observed} != {expected}")
        if str(row.get("converged", "")).lower() != "true":
            _error(f"H1 fit did not converge for {key}")
        if float(row["beta_distance"]) <= 0.0:
            _error(f"distance coefficient is not positive for {key}")


def validate_manifest(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    path = _resolve(repo, MANIFEST_PATH)
    result = validate_run_manifest(path, repository_root=repo)
    if result.get("run_id") != RUN_ID:
        _error("H1 manifest run ID mismatch")
    if result.get("collector") != "collect_kxbtcd_candidate_e_h1":
        _error("H1 manifest collector mismatch")
    if result.get("status") != "completed":
        _error("H1 manifest is not completed")
    if result.get("git_commit") != EXPECTED_SOURCE_COMMIT:
        _error("H1 manifest source commit mismatch")
    if result.get("git_worktree_dirty") is not False:
        _error("H1 run did not start from a clean worktree")

    manifest = _read_json(path)
    result_payload = manifest.get("result")
    if not isinstance(result_payload, Mapping):
        _error("H1 manifest result payload missing")
    if result_payload.get("h1_result_fingerprint") != EXPECTED_RESULT_FINGERPRINT:
        _error("H1 manifest result fingerprint mismatch")
    if result_payload.get("H2_outcomes_opened") is not False:
        _error("H1 manifest indicates H2 exposure")
    if result_payload.get("H3_outcomes_opened") is not False:
        _error("H1 manifest indicates H3 exposure")
    if result_payload.get("execution_enabled") is not False or result_payload.get("orders_placed") != 0:
        _error("H1 manifest violates execution boundary")
    return dict(result)


def validate_attempt(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    attempt = _read_json(_resolve(repo, ATTEMPT_PATH))
    expected = {
        "status": "h1_evaluation_completed",
        "h1_evaluation_fingerprint": H1_EVALUATION_FINGERPRINT,
        "H1_permanently_development_exposed": True,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
        "result_fingerprint": EXPECTED_RESULT_FINGERPRINT,
    }
    for key, value in expected.items():
        if attempt.get(key) != value:
            _error(f"H1 attempt receipt {key} mismatch")
    return attempt


def load_and_validate_result(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    validate_manifest(repo)
    summary = validate_summary(_read_json(_resolve(repo, SUMMARY_PATH)))
    validate_fold_rows(_read_csv(_resolve(repo, FOLD_PATH)))
    validate_coefficients(_read_csv(_resolve(repo, COEFFICIENT_PATH)))
    validate_attempt(repo)
    return summary


def advancement_decision(summary: Mapping[str, Any]) -> dict[str, Any]:
    validate_summary(summary)
    return {
        "family_id": FAMILY_ID,
        "H1_result": "PASS",
        "selected_candidate_id": DISTANCE_ID,
        "distance_raw_gate_passed": True,
        "momentum_raw_gate_passed": True,
        "momentum_nested_complexity_gate_passed": False,
        "nested_score_block_win_count": 2,
        "H1_permanently_development_exposed": True,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "posthoc_H1_repair_authorized": False,
        "next_authorized_work": (
            "fit the selected Distance specification exactly once on all H1 events and "
            "freeze the H2-only validation procedure before any H2 outcome access"
        ),
        "execution_authorized": False,
    }


__all__ = [
    "CandidateEH1ResultCloseoutError",
    "DISTANCE_ID",
    "EXPECTED_RESULT_FINGERPRINT",
    "EXPECTED_SUMMARY",
    "RUN_ID",
    "advancement_decision",
    "canonical_summary_fingerprint",
    "load_and_validate_result",
    "validate_coefficients",
    "validate_fold_rows",
    "validate_summary",
]
