"""Checkpoint 21I-A/21I-B Candidate-E final historical champion fit.

21I-A freezes the exact offline deterministic fit procedure after C1/C2/C3
have all passed. 21I-B may then fit one final historical parameter estimate on
the complete outcome-exposed H1+H2+H3+C1+C2+C3 pool.

This module performs no network requests and has no execution path.
The remaining 4,676-event historical reserve is outside the fit contract.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping

from .kxbtcd_candidate_e_c3_evaluation import load_and_validate_c3_frozen_data
from .kxbtcd_candidate_e_c3_preparation import (
    DISTANCE_CANDIDATE_ID,
    FAMILY_ID,
    _build_c2_observations,
    _build_prior_observations,
)
from .kxbtcd_candidate_e_h1_evaluation import (
    CandidateEObservation,
    fit_candidate_e,
)
from .kxbtcd_candidate_e_predeclaration import candidate_e_predeclaration

CP21I_A_PARENT_RECEIPT_COMMIT = "933c93044b6967b00825f226bbf597316c4b6e03"
CP21H_B_CHECKPOINT_COMMIT = "ba5d62ddeaf0a5a9bdf32282f04569e388a49990"

PARENT_21A_PROTOCOL_FINGERPRINT = (
    "88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00"
)
PARENT_H3_RESULT_FINGERPRINT = (
    "436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54"
)
C1_RESULT_FINGERPRINT = (
    "5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19"
)
C2_RESULT_FINGERPRINT = (
    "ee6cd30b32a9445096f25934d67dfa34046504ee83889947be8c8a40377a8f62"
)
C3_RESULT_FINGERPRINT = (
    "b37d5f5f299cf338a2bdf730f114a61b1bea25f3af820c21f81bd1fe13072b08"
)
C3_RESULT_CLOSEOUT_FINGERPRINT = (
    "2a9ff681973608f2cdd44371eda8bf4208021610e4f3e74f887a173de1447ede"
)
CHAMPION_R2_FINGERPRINT = (
    "2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964"
)

H1_EVENT_COUNT = 1500
H2_EVENT_COUNT = 750
H3_EVENT_COUNT = 750
C1_EVENT_COUNT = 500
C2_EVENT_COUNT = 500
C3_EVENT_COUNT = 500

H1_ROW_COUNT = 36314
H2_ROW_COUNT = 22354
H3_ROW_COUNT = 22409
C1_ROW_COUNT = 14887
C2_ROW_COUNT = 14007
C3_ROW_COUNT = 13549
C3_MARKET_COUNT = 2470

FINAL_EVENT_COUNT = (
    H1_EVENT_COUNT + H2_EVENT_COUNT + H3_EVENT_COUNT
    + C1_EVENT_COUNT + C2_EVENT_COUNT + C3_EVENT_COUNT
)
FINAL_ROW_COUNT = (
    H1_ROW_COUNT + H2_ROW_COUNT + H3_ROW_COUNT
    + C1_ROW_COUNT + C2_ROW_COUNT + C3_ROW_COUNT
)

STRICT_UNTOUCHED_TAIL_REMAINING = 4676
STRICT_UNTOUCHED_TAIL_FLOOR = 4500
STRICT_UNTOUCHED_TAIL_BUFFER = (
    STRICT_UNTOUCHED_TAIL_REMAINING - STRICT_UNTOUCHED_TAIL_FLOOR
)

IMPLEMENTATION_FREEZE_SCHEMA_VERSION = (
    "kxbtcd_candidate_e_final_fit_implementation_freeze.v1"
)
FINAL_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_e_champion_final.v1"

C3_RESULT_CLOSEOUT_PATH = Path(
    "configs/kxbtcd_candidate_e_c3_result_closeout.json"
)
IMPLEMENTATION_FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_e_final_fit_implementation_freeze.json"
)
FINAL_MODEL_PATH = Path(
    "configs/kxbtcd_candidate_e_champion_final.json"
)
LAST_CLOSEOUT_PATH = Path("docs/LAST_CHECKPOINT_CLOSEOUT.json")

IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_final_fit.py",
    "fit_kxbtcd_candidate_e_final_champion.py",
)

REQUIRED_21I_A_CLOSEOUT_PATHS = frozenset(
    {
        "configs/kxbtcd_candidate_e_final_fit_implementation_freeze.json",
        "docs/KXBTCD_CANDIDATE_E_FINAL_HISTORICAL_FIT.md",
        "fit_kxbtcd_candidate_e_final_champion.py",
        "freeze_kxbtcd_candidate_e_final_fit_implementation.py",
        "scripts/apply_checkpoint21i_a_docs.py",
        "src/kxbtcd_candidate_e_final_fit.py",
        "tests/test_kxbtcd_candidate_e_final_fit.py",
        "validate_kxbtcd_candidate_e_final_fit_implementation_freeze.py",
    }
)

FREEZE_BUNDLE_UNTRACKED_PATHS = frozenset(
    {
        *REQUIRED_21I_A_CLOSEOUT_PATHS,
        "README_CHECKPOINT21I_A.txt",
    }
)


class CandidateEFinalFitError(RuntimeError):
    """Raised when the final historical fit contract fails closed."""


def _error(message: str) -> None:
    raise CandidateEFinalFitError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEFinalFitError(
            f"could not read JSON {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be object: {path}")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return tuple(reader.fieldnames or ()), tuple(
                dict(row) for row in reader
            )
    except OSError as exc:
        raise CandidateEFinalFitError(
            f"could not read CSV {path}: {exc}"
        ) from exc


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _float_text(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0.0 else "-inf"
    return format(value, ".17g")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        _error(
            f"git {' '.join(args)} failed: "
            f"{detail or completed.returncode}"
        )
    return completed.stdout.strip()


def _implementation_sha256s(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"final-fit implementation file missing: {relative}")
        result[relative] = _sha256_file(path)
    return result


def validate_c3_result_closeout(
    repository_root: str | Path = ".",
    *,
    verify_lineage_files: bool = True,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    document = _read_json(repo / C3_RESULT_CLOSEOUT_PATH)

    expected = {
        "schema_version": "kxbtcd_candidate_e_c3_result_closeout.v1",
        "checkpoint_id": "21H-B",
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "c3_result_fingerprint": C3_RESULT_FINGERPRINT,
        "c3_result_closeout_fingerprint": C3_RESULT_CLOSEOUT_FINGERPRINT,
        "C3_event_count": C3_EVENT_COUNT,
        "C3_row_count": C3_ROW_COUNT,
        "C3_market_count": C3_MARKET_COUNT,
        "C3_permanently_exposed": True,
        "C3_validation_passed": True,
        "model_parameters_fitted_on_C3": False,
        "candidate_selection_on_C3_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "posthoc_repair_performed": False,
        "remaining_historical_reserve_accessed": False,
        "exposed_historical_fit_pool_event_count": FINAL_EVENT_COUNT,
        "exposed_historical_fit_pool_row_count": FINAL_ROW_COUNT,
        "strict_untouched_tail_remaining": STRICT_UNTOUCHED_TAIL_REMAINING,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"C3 result closeout {key} mismatch")

    payload = {
        key: document[key]
        for key in document
        if key != "c3_result_closeout_fingerprint"
    }
    if _canonical_sha256(payload) != C3_RESULT_CLOSEOUT_FINGERPRINT:
        _error("C3 result closeout canonical fingerprint mismatch")

    if verify_lineage_files:
        pairs = (
            ("manifest_path", "manifest_sha256"),
            ("attempt_path", "attempt_sha256"),
            ("block_scores_path", "block_scores_sha256"),
            ("event_scores_path", "event_scores_sha256"),
            ("outcomes_path", "outcomes_sha256"),
            ("predictions_path", "predictions_sha256"),
            ("summary_path", "summary_sha256"),
        )
        for path_key, sha_key in pairs:
            relative = document.get(path_key)
            expected_sha = document.get(sha_key)
            if not isinstance(relative, str) or not relative:
                _error(f"C3 closeout missing {path_key}")
            if not isinstance(expected_sha, str) or len(expected_sha) != 64:
                _error(f"C3 closeout missing/invalid {sha_key}")
            path = repo / relative
            if not path.is_file():
                _error(f"C3 lineage file missing: {relative}")
            if _sha256_file(path) != expected_sha:
                _error(f"C3 lineage hash mismatch: {relative}")
    return document


def _validate_21h_b_receipt(repo: Path) -> dict[str, Any]:
    receipt = _read_json(repo / LAST_CLOSEOUT_PATH)
    if receipt.get("checkpoint_commit") != CP21H_B_CHECKPOINT_COMMIT:
        _error("latest closeout does not record exact Checkpoint-21H-B commit")
    if receipt.get("checkpoint_message") != (
        "Checkpoint 21H-B: close Candidate-E C3 historical confirmation"
    ):
        _error("latest closeout Checkpoint-21H-B message changed")
    committed = set(receipt.get("committed_paths") or ())
    required = {
        C3_RESULT_CLOSEOUT_PATH.as_posix(),
        "docs/AI_HANDOFF.md",
        "docs/BACKLOG.md",
        "docs/DECISIONS.md",
        "docs/EXPERIMENT_LOG.md",
        "docs/LEARNING_GUIDE.md",
        "docs/PROJECT_STATE.md",
    }
    if not required.issubset(committed):
        _error("latest closeout does not contain full C3 result closeout")
    safety = receipt.get("safety")
    if not isinstance(safety, Mapping):
        _error("latest closeout safety record missing")
    for key in (
        "blocked_path_check",
        "high_confidence_secret_scan",
        "staged_diff_check",
        "staged_path_exact_match",
    ):
        if safety.get(key) != "PASS":
            _error(f"latest Checkpoint-21H-B safety field {key} did not PASS")
    return receipt


def assert_21h_b_parent_baseline_for_freeze(
    repository_root: str | Path = ".",
) -> str:
    """Require exact clean synchronized 21H-B receipt before 21I-A freeze."""
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("Checkpoint-21I-A freeze requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if (
        head != CP21I_A_PARENT_RECEIPT_COMMIT
        or remote != CP21I_A_PARENT_RECEIPT_COMMIT
    ):
        _error(
            "Checkpoint-21I-A parent mismatch; expected "
            f"HEAD == origin/main == {CP21I_A_PARENT_RECEIPT_COMMIT}, "
            f"got HEAD={head}, origin/main={remote}"
        )
    if _git(repo, "diff", "--name-only"):
        _error("tracked unstaged changes existed before 21I-A freeze")
    if _git(repo, "diff", "--cached", "--name-only"):
        _error("staged changes existed before 21I-A freeze")

    status = _git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    unexpected: list[str] = []
    for raw in status.splitlines():
        if not raw:
            continue
        code = raw[:2]
        path = raw[3:].replace("\\", "/")
        if code != "??" or path not in FREEZE_BUNDLE_UNTRACKED_PATHS:
            unexpected.append(raw)
    if unexpected:
        _error(
            "unexpected worktree state before 21I-A freeze; "
            f"first unexpected line: {unexpected[0]}"
        )

    _validate_21h_b_receipt(repo)
    validate_c3_result_closeout(repo, verify_lineage_files=True)
    return head


def build_implementation_freeze_document(
    repository_root: str | Path = ".",
    *,
    source_baseline_commit: str,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    validate_c3_result_closeout(repo, verify_lineage_files=True)
    fit_contract = candidate_e_predeclaration()["fit_contract"]

    payload = {
        "schema_version": IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21I-A",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "parent_c3_result_fingerprint": C3_RESULT_FINGERPRINT,
        "parent_c3_result_closeout_fingerprint": (
            C3_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "source_baseline_commit": source_baseline_commit,
        "final_fit_contract": {
            "stages": ["H1", "H2", "H3", "C1", "C2", "C3"],
            "event_count": FINAL_EVENT_COUNT,
            "row_count": FINAL_ROW_COUNT,
            "all_outcomes_previously_exposed": True,
            "candidate_id": DISTANCE_CANDIDATE_ID,
            "free_parameter_count": 1,
            "feature": "btc_strike_log_distance_bps.v1",
            "beta_momentum": None,
            "feature_selection": False,
            "hyperparameter_search": False,
            "candidate_selection": False,
            "fresh_validation_claim": False,
            "optimizer": fit_contract["optimizer"],
        },
        "reserve_policy": {
            "strict_untouched_tail_remaining": (
                STRICT_UNTOUCHED_TAIL_REMAINING
            ),
            "strict_untouched_tail_floor": STRICT_UNTOUCHED_TAIL_FLOOR,
            "strict_untouched_tail_buffer": STRICT_UNTOUCHED_TAIL_BUFFER,
            "reserve_rows_used_in_fit": 0,
            "reserve_outcomes_accessed": False,
            "additional_historical_materialization_allowed": False,
        },
        "implementation_sha256s": _implementation_sha256s(repo),
        "final_fit_performed_at_freeze": False,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["implementation_freeze_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_implementation_freeze_document(
    document: Mapping[str, Any],
    *,
    repository_root: str | Path = ".",
    verify_parent: bool = True,
    verify_implementation_hashes: bool = True,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    expected = {
        "schema_version": IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21I-A",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "parent_c3_result_fingerprint": C3_RESULT_FINGERPRINT,
        "parent_c3_result_closeout_fingerprint": (
            C3_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "source_baseline_commit": CP21I_A_PARENT_RECEIPT_COMMIT,
        "final_fit_performed_at_freeze": False,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"final-fit implementation freeze {key} mismatch")

    fit = document.get("final_fit_contract")
    if not isinstance(fit, Mapping):
        _error("final fit contract missing")
    if (
        fit.get("event_count"),
        fit.get("row_count"),
        fit.get("candidate_id"),
        fit.get("free_parameter_count"),
        fit.get("feature_selection"),
        fit.get("hyperparameter_search"),
        fit.get("candidate_selection"),
        fit.get("fresh_validation_claim"),
    ) != (
        FINAL_EVENT_COUNT,
        FINAL_ROW_COUNT,
        DISTANCE_CANDIDATE_ID,
        1,
        False,
        False,
        False,
        False,
    ):
        _error("final fit contract changed")
    if fit.get("stages") != ["H1", "H2", "H3", "C1", "C2", "C3"]:
        _error("final fit stage identity changed")
    if fit.get("beta_momentum") is not None:
        _error("final fit unexpectedly permits momentum")

    reserve = document.get("reserve_policy")
    if not isinstance(reserve, Mapping):
        _error("final fit reserve policy missing")
    if (
        reserve.get("strict_untouched_tail_remaining"),
        reserve.get("strict_untouched_tail_floor"),
        reserve.get("strict_untouched_tail_buffer"),
        reserve.get("reserve_rows_used_in_fit"),
        reserve.get("reserve_outcomes_accessed"),
        reserve.get("additional_historical_materialization_allowed"),
    ) != (
        STRICT_UNTOUCHED_TAIL_REMAINING,
        STRICT_UNTOUCHED_TAIL_FLOOR,
        STRICT_UNTOUCHED_TAIL_BUFFER,
        0,
        False,
        False,
    ):
        _error("final fit reserve policy changed")

    if verify_implementation_hashes:
        if document.get("implementation_sha256s") != _implementation_sha256s(repo):
            _error("final-fit implementation bytes differ from frozen hashes")

    if verify_parent:
        validate_c3_result_closeout(repo, verify_lineage_files=True)

    payload = {
        key: document[key]
        for key in document
        if key != "implementation_freeze_fingerprint"
    }
    if document.get("implementation_freeze_fingerprint") != _canonical_sha256(
        payload
    ):
        _error("final-fit implementation fingerprint mismatch")
    return dict(document)


def write_or_validate_implementation_freeze(
    repository_root: str | Path = ".",
    path: str | Path = IMPLEMENTATION_FREEZE_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    baseline = assert_21h_b_parent_baseline_for_freeze(repo)
    target = Path(path)
    if not target.is_absolute():
        target = repo / target

    document = build_implementation_freeze_document(
        repo,
        source_baseline_commit=baseline,
    )
    validate_implementation_freeze_document(
        document,
        repository_root=repo,
    )
    if target.exists():
        existing = _read_json(target)
        validate_implementation_freeze_document(
            existing,
            repository_root=repo,
        )
        if existing != document:
            _error(
                "existing final-fit implementation freeze differs; "
                "refusing overwrite"
            )
        return target, existing
    _write_json_atomic(target, document)
    return target, document


def load_and_validate_implementation_freeze(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    return validate_implementation_freeze_document(
        _read_json(repo / IMPLEMENTATION_FREEZE_PATH),
        repository_root=repo,
    )


def assert_runtime_checkout_is_frozen_21i_a(
    repository_root: str | Path = ".",
) -> tuple[str, dict[str, Any]]:
    """Require clean synchronized main carrying safely closed 21I-A bytes."""
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("final historical fit requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != remote:
        _error(
            "final historical fit requires HEAD == origin/main; "
            f"HEAD={head}, origin/main={remote}"
        )
    if _git(repo, "status", "--porcelain"):
        _error("final historical fit requires a clean worktree")

    receipt = _read_json(repo / LAST_CLOSEOUT_PATH)
    if receipt.get("baseline_commit") != CP21I_A_PARENT_RECEIPT_COMMIT:
        _error(
            "latest closeout is not the direct Checkpoint-21I-A child "
            "of accepted 21H-B receipt"
        )
    if receipt.get("checkpoint_message") != (
        "Checkpoint 21I-A: freeze Candidate-E final historical fit"
    ):
        _error("latest closeout message is not Checkpoint 21I-A")
    committed = set(receipt.get("committed_paths") or ())
    missing = REQUIRED_21I_A_CLOSEOUT_PATHS - committed
    if missing:
        _error(
            "latest closeout does not contain required 21I-A paths: "
            f"{sorted(missing)}"
        )
    safety = receipt.get("safety")
    if not isinstance(safety, Mapping):
        _error("latest closeout safety record missing")
    if (
        safety.get("staged_diff_check") != "PASS"
        or safety.get("high_confidence_secret_scan") != "PASS"
    ):
        _error("latest Checkpoint-21I-A closeout safety checks did not pass")

    freeze = load_and_validate_implementation_freeze(repo)
    return head, freeze


def _build_c3_observations(repo: Path) -> tuple[CandidateEObservation, ...]:
    closeout = validate_c3_result_closeout(
        repo,
        verify_lineage_files=True,
    )
    frozen = load_and_validate_c3_frozen_data(repo)

    _, outcome_rows = _read_csv(repo / str(closeout["outcomes_path"]))
    labels: dict[str, int] = {}
    for index, row in enumerate(outcome_rows):
        if row.get("stage") != "C3":
            _error(f"C3 outcome row {index} stage changed")
        market = str(row.get("market_ticker") or "")
        if not market or market in labels:
            _error(f"C3 outcome row {index} duplicate/blank market")
        outcome = int(row["outcome"])
        if outcome not in {0, 1}:
            _error("C3 outcome is not binary")
        labels[market] = outcome

    if len(labels) != C3_MARKET_COUNT:
        _error(f"C3 label count changed: {len(labels)}")

    observations: list[CandidateEObservation] = []
    events: set[str] = set()
    state_ids: set[str] = set()

    for index, row in enumerate(frozen.preoutcome_rows):
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if market not in labels:
            _error(
                f"C3 preoutcome row {index} references missing label {market}"
            )
        state_id = (
            f"C3|{event}|{market}|"
            f"TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in state_ids:
            _error(f"duplicate C3 final-fit state identity {state_id}")
        state_ids.add(state_id)
        events.add(event)

        q_market = float(row["q_market"])
        d_btc = float(row["d_BTC"])
        r_5m = float(row["r_5m"])
        if not all(
            math.isfinite(value)
            for value in (q_market, d_btc, r_5m)
        ):
            _error(f"C3 preoutcome row {index} has non-finite model input")

        observations.append(
            CandidateEObservation(
                state_id=state_id,
                event_ticker=event,
                market_ticker=market,
                block_id=f"C3_{row['block_id']}",
                structural_role=str(row["structural_role"]),
                ttc_target_minutes=int(row["ttc_target_minutes"]),
                outcome=labels[market],
                q_market=q_market,
                d_btc=d_btc,
                r_5m=r_5m,
            )
        )

    if len(observations) != C3_ROW_COUNT:
        _error(
            f"C3 final-fit observation row count changed: "
            f"{len(observations)}"
        )
    if len(events) != C3_EVENT_COUNT:
        _error(
            f"C3 final-fit event count changed: {len(events)}"
        )
    return tuple(observations)


def build_final_model_document(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    """Fit unchanged Distance champion on all 4,500 already-exposed events."""
    repo = Path(repository_root).resolve()
    _, freeze = assert_runtime_checkout_is_frozen_21i_a(repo)
    c3_closeout = validate_c3_result_closeout(
        repo,
        verify_lineage_files=True,
    )

    _, prior = _build_prior_observations(repo)
    c2 = _build_c2_observations(repo)
    c3 = _build_c3_observations(repo)
    observations = tuple(prior) + tuple(c2) + tuple(c3)

    if len(observations) != FINAL_ROW_COUNT:
        _error(
            f"final historical row count changed: "
            f"{len(observations)} != {FINAL_ROW_COUNT}"
        )
    event_count = len({row.event_ticker for row in observations})
    if event_count != FINAL_EVENT_COUNT:
        _error(
            f"final historical event count changed: "
            f"{event_count} != {FINAL_EVENT_COUNT}"
        )

    fit = fit_candidate_e(
        observations,
        candidate_id=DISTANCE_CANDIDATE_ID,
        fold=0,
        fit_blocks=("H1", "H2", "H3", "C1", "C2", "C3"),
        score_block="POST_HISTORICAL_CONFIRMATION",
    )
    if (
        not fit.converged
        or not math.isfinite(fit.beta_distance)
        or fit.beta_distance <= 0.0
    ):
        _error(
            "Champion-Final fit did not produce a finite positive "
            "distance coefficient"
        )
    if fit.beta_momentum is not None:
        _error("Champion-Final unexpectedly fit momentum")

    payload = {
        "schema_version": FINAL_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "21I-B",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "parent_c3_result_fingerprint": C3_RESULT_FINGERPRINT,
        "parent_c3_result_closeout_fingerprint": (
            C3_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "implementation_freeze_fingerprint": freeze[
            "implementation_freeze_fingerprint"
        ],
        "fit_scope": {
            "stages": ["H1", "H2", "H3", "C1", "C2", "C3"],
            "event_count": FINAL_EVENT_COUNT,
            "row_count": FINAL_ROW_COUNT,
            "all_outcomes_previously_exposed": True,
            "fresh_validation_claim": False,
            "strict_untouched_tail_rows_used": 0,
            "strict_untouched_tail_outcomes_accessed": False,
        },
        "model": {
            "formula": (
                "logit(p)=market_logit_offset + beta_distance*d_BTC"
            ),
            "market_logit_offset_clip": "0.001",
            "feature": "btc_strike_log_distance_bps.v1",
            "beta_distance": _float_text(fit.beta_distance),
            "beta_momentum": None,
            "free_parameter_count": 1,
        },
        "fit_contract": candidate_e_predeclaration()["fit_contract"],
        "fit_result": {
            "iterations": fit.iterations,
            "converged": True,
            "fit_objective": _float_text(fit.fit_objective),
        },
        "lineage": {
            "c3_result_closeout_path": C3_RESULT_CLOSEOUT_PATH.as_posix(),
            "c3_result_closeout_sha256": _sha256_file(
                repo / C3_RESULT_CLOSEOUT_PATH
            ),
            "c3_outcomes_path": str(c3_closeout["outcomes_path"]),
            "c3_outcomes_sha256": str(c3_closeout["outcomes_sha256"]),
            "implementation_freeze_path": IMPLEMENTATION_FREEZE_PATH.as_posix(),
            "implementation_freeze_sha256": _sha256_file(
                repo / IMPLEMENTATION_FREEZE_PATH
            ),
        },
        "specification_changed_after_C3": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "candidate_selection_performed": False,
        "remaining_historical_reserve_accessed": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["champion_final_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_final_model_document(
    document: Mapping[str, Any],
    *,
    implementation_freeze: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = {
        "schema_version": FINAL_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "21I-B",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "parent_c3_result_fingerprint": C3_RESULT_FINGERPRINT,
        "parent_c3_result_closeout_fingerprint": (
            C3_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "specification_changed_after_C3": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "candidate_selection_performed": False,
        "remaining_historical_reserve_accessed": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"Champion-Final {key} mismatch")

    scope = document.get("fit_scope")
    if not isinstance(scope, Mapping):
        _error("Champion-Final fit scope missing")
    if (
        scope.get("event_count"),
        scope.get("row_count"),
        scope.get("all_outcomes_previously_exposed"),
        scope.get("fresh_validation_claim"),
        scope.get("strict_untouched_tail_rows_used"),
        scope.get("strict_untouched_tail_outcomes_accessed"),
    ) != (
        FINAL_EVENT_COUNT,
        FINAL_ROW_COUNT,
        True,
        False,
        0,
        False,
    ):
        _error("Champion-Final fit scope changed")

    model = document.get("model")
    if not isinstance(model, Mapping):
        _error("Champion-Final model section missing")
    try:
        beta = float(model.get("beta_distance"))
    except (TypeError, ValueError) as exc:
        raise CandidateEFinalFitError(
            "Champion-Final beta_distance is not numeric"
        ) from exc
    if (
        not math.isfinite(beta)
        or beta <= 0.0
        or model.get("beta_momentum") is not None
        or model.get("free_parameter_count") != 1
    ):
        _error("Champion-Final coefficient state invalid")

    fit = document.get("fit_result")
    if (
        not isinstance(fit, Mapping)
        or fit.get("converged") is not True
    ):
        _error("Champion-Final fit did not converge")

    if implementation_freeze is not None:
        if document.get("implementation_freeze_fingerprint") != (
            implementation_freeze.get("implementation_freeze_fingerprint")
        ):
            _error("Champion-Final implementation-freeze lineage mismatch")

    payload = {
        key: document[key]
        for key in document
        if key != "champion_final_fingerprint"
    }
    if document.get("champion_final_fingerprint") != _canonical_sha256(payload):
        _error("Champion-Final fingerprint mismatch")
    return dict(document)


def write_or_validate_final_model(
    repository_root: str | Path = ".",
    path: str | Path = FINAL_MODEL_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    _, freeze = assert_runtime_checkout_is_frozen_21i_a(repo)
    target = Path(path)
    if not target.is_absolute():
        target = repo / target

    document = build_final_model_document(repo)
    validate_final_model_document(
        document,
        implementation_freeze=freeze,
    )
    if target.exists():
        existing = _read_json(target)
        validate_final_model_document(
            existing,
            implementation_freeze=freeze,
        )
        if existing != document:
            _error(
                "existing Champion-Final artifact differs; "
                "refusing overwrite"
            )
        return target, existing
    _write_json_atomic(target, document)
    return target, document


__all__ = [
    "CHAMPION_R2_FINGERPRINT",
    "C3_RESULT_CLOSEOUT_FINGERPRINT",
    "CandidateEFinalFitError",
    "FINAL_EVENT_COUNT",
    "FINAL_MODEL_PATH",
    "FINAL_ROW_COUNT",
    "IMPLEMENTATION_FREEZE_PATH",
    "STRICT_UNTOUCHED_TAIL_REMAINING",
    "build_final_model_document",
    "load_and_validate_implementation_freeze",
    "validate_c3_result_closeout",
    "validate_final_model_document",
    "validate_implementation_freeze_document",
    "write_or_validate_final_model",
    "write_or_validate_implementation_freeze",
]
