"""Checkpoint 21E-A: Candidate-E C2 preparation contracts.

21E-A freezes implementation bytes only. It performs no Champion-R1 fit,
no C2 materialization, no C2 outcome access, no C3 access, and no execution.

After safe closeout, the frozen implementation may:
1. deterministically refit the unchanged Distance champion on the already
   exposed H1+H2+H3+C1 evidence (3,500 events);
2. freeze Champion-R1;
3. only after Champion-R1 is safely closed, sequentially materialize C2
   outcome-blind from the strict historical tail;
4. freeze exactly 500 eligible C2 events into five chronological 100-event
   subblocks without opening C2 outcomes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping

PARENT_21D_RECEIPT_COMMIT = "8c32e6f28f0bf625487c46be3f6306f409d8cfd4"
PARENT_21A_PROTOCOL_FINGERPRINT = "88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00"
PARENT_H3_RESULT_FINGERPRINT = "436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54"
C1_RESULT_FINGERPRINT = "5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19"
C1_RESULT_CLOSEOUT_FINGERPRINT = "3a66e7d980334474d4d836f80bc2aca56932baab1040fa393dee9764a3ee737e"
CHAMPION_R0_FINGERPRINT = "ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa"

FAMILY_ID = "kxbtcd_independent_btc_offset_successor.v1"
DISTANCE_CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"

UNTOUCHED_QUEUE_EVENT_COUNT = 9431
C2_STRICT_TAIL_START_INDEX = 3706
C2_STRICT_TAIL_EVENT_COUNT_ENTERING = UNTOUCHED_QUEUE_EVENT_COUNT - C2_STRICT_TAIL_START_INDEX
C2_ELIGIBLE_EVENT_TARGET = 500
C2_SUBBLOCK_COUNT = 5
C2_EVENTS_PER_SUBBLOCK = 100
MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION = 4500
STRICT_TAIL_MAX_END_EXCLUSIVE = 4931
MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C2_C3 = (
    STRICT_TAIL_MAX_END_EXCLUSIVE - C2_STRICT_TAIL_START_INDEX
)
MAX_C2_CHUNK_EVENTS = 100

H1_EVENT_COUNT = 1500
H2_EVENT_COUNT = 750
H3_EVENT_COUNT = 750
C1_EVENT_COUNT = 500
H1_ROW_COUNT = 36314
H2_ROW_COUNT = 22354
H3_ROW_COUNT = 22409
C1_ROW_COUNT = 14887
R1_EVENT_COUNT = H1_EVENT_COUNT + H2_EVENT_COUNT + H3_EVENT_COUNT + C1_EVENT_COUNT
R1_ROW_COUNT = H1_ROW_COUNT + H2_ROW_COUNT + H3_ROW_COUNT + C1_ROW_COUNT

IMPLEMENTATION_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_c2_preparation_implementation_freeze.v1"
R1_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_e_champion_r1.v1"
C2_VALIDATION_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_c2_validation_freeze.v1"

PARENT_PROTOCOL_PATH = Path("configs/kxbtcd_post_h3_champion_lifecycle.v1.json")
C1_RESULT_CLOSEOUT_PATH = Path("configs/kxbtcd_candidate_e_c1_result_closeout.json")
C1_VALIDATION_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_c1_validation_freeze.json")
C1_IMPLEMENTATION_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_c1_evaluator_implementation_freeze.json")
R0_MODEL_PATH = Path("configs/kxbtcd_candidate_e_champion_r0.json")
IMPLEMENTATION_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_c2_preparation_implementation_freeze.json")
R1_MODEL_PATH = Path("configs/kxbtcd_candidate_e_champion_r1.json")
C2_VALIDATION_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_c2_validation_freeze.json")
LAST_CLOSEOUT_PATH = Path("docs/LAST_CHECKPOINT_CLOSEOUT.json")

C2_CHUNK_ROOT = Path("data/derived/kxbtcd_candidate_e_c2_preoutcome/chunks")
C2_FROZEN_ROOT = Path("data/derived/kxbtcd_candidate_e_c2_preoutcome/frozen")
C2_COLLECTOR_NAME = "collect_kxbtcd_candidate_e_c2_materialization_chunk"

NEW_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_c2_preparation.py",
    "prepare_kxbtcd_candidate_e_c2.py",
    "collect_kxbtcd_candidate_e_c2_materialization_chunk.py",
    "freeze_kxbtcd_candidate_e_c2_preoutcome.py",
)
DEPENDENCY_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_c1_preparation.py",
    "src/kxbtcd_candidate_e_c1_evaluation.py",
    "src/kxbtcd_candidate_e_h1_evaluation.py",
    "src/kxbtcd_candidate_e_h3_preparation.py",
    "src/kxbtcd_candidate_e_h3_result_closeout.py",
    "collect_kxbtcd_candidate_e_coinbase_primary_materialization_chunk.py",
    "collect_kxbtcd_candidate_e_historical_materialization_chunk.py",
    "src/kxbtcd_candidate_e_coinbase_primary_materialization.py",
    "src/kxbtcd_candidate_e_historical_materialization.py",
)
IMPLEMENTATION_FILES = NEW_IMPLEMENTATION_FILES + DEPENDENCY_IMPLEMENTATION_FILES


class CandidateEC2PreparationError(RuntimeError):
    """Raised when a Checkpoint-21E C2-preparation invariant fails."""


def _error(message: str) -> None:
    raise CandidateEC2PreparationError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEC2PreparationError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be object: {path}")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
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
        return "inf" if value > 0 else "-inf"
    return format(value, ".17g")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        _error(f"git {' '.join(args)} failed: {detail or completed.returncode}")
    return completed.stdout.strip()


def _implementation_sha256s(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"C2 preparation implementation/dependency missing: {relative}")
        result[relative] = _sha256_file(path)
    return result


def validate_parent_21d_result_closeout(
    repository_root: str | Path = ".",
    *,
    verify_lineage_files: bool = True,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    document = _read_json(repo / C1_RESULT_CLOSEOUT_PATH)
    expected = {
        "schema_version": "kxbtcd_candidate_e_c1_result_closeout.v1",
        "checkpoint_id": "21D",
        "c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "c1_result_closeout_fingerprint": C1_RESULT_CLOSEOUT_FINGERPRINT,
        "champion_r0_fingerprint": CHAMPION_R0_FINGERPRINT,
        "C1_event_count": C1_EVENT_COUNT,
        "C1_row_count": C1_ROW_COUNT,
        "C1_validation_passed": True,
        "C1_permanently_exposed": True,
        "strict_untouched_tail_remaining": C2_STRICT_TAIL_EVENT_COUNT_ENTERING,
        "model_parameters_fitted_on_C1": False,
        "candidate_selection_on_C1_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "C2_C3_materialized_or_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"parent C1 result closeout {key} mismatch")

    payload = {k: document[k] for k in document if k != "c1_result_closeout_fingerprint"}
    if _canonical_sha256(payload) != C1_RESULT_CLOSEOUT_FINGERPRINT:
        _error("parent C1 result closeout canonical fingerprint mismatch")

    if verify_lineage_files:
        lineage_pairs = (
            ("manifest_path", "manifest_sha256"),
            ("summary_path", "summary_sha256"),
            ("block_scores_path", "block_scores_sha256"),
            ("predictions_path", "predictions_sha256"),
            ("event_scores_path", "event_scores_sha256"),
            ("outcomes_path", "outcomes_sha256"),
            ("attempt_path", "attempt_sha256"),
        )
        for path_key, hash_key in lineage_pairs:
            relative = document.get(path_key)
            expected_hash = document.get(hash_key)
            if not isinstance(relative, str) or not relative:
                _error(f"parent C1 closeout missing {path_key}")
            path = repo / relative
            if not path.is_file():
                _error(f"parent C1 lineage file missing: {relative}")
            if _sha256_file(path) != expected_hash:
                _error(f"parent C1 lineage hash mismatch: {relative}")
    return document


def assert_21d_parent_baseline_for_implementation_freeze(
    repository_root: str | Path = ".",
) -> str:
    """Require exact clean 21D receipt before generating the 21E-A freeze.

    New 21E-A bundle files may be untracked; existing tracked files must be clean.
    """
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("Checkpoint-21E-A implementation freeze requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != PARENT_21D_RECEIPT_COMMIT or remote != PARENT_21D_RECEIPT_COMMIT:
        _error(
            "Checkpoint-21E-A parent mismatch; expected HEAD == origin/main == "
            f"{PARENT_21D_RECEIPT_COMMIT}, got HEAD={head}, origin/main={remote}"
        )
    if _git(repo, "diff", "--name-only"):
        _error("tracked unstaged changes existed before Checkpoint-21E-A freeze")
    if _git(repo, "diff", "--cached", "--name-only"):
        _error("staged changes existed before Checkpoint-21E-A freeze")
    validate_parent_21d_result_closeout(repo, verify_lineage_files=True)
    return head


def build_implementation_freeze_document(
    *,
    repository_root: str | Path,
    source_baseline_commit: str,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    c1 = validate_parent_21d_result_closeout(repo, verify_lineage_files=True)
    payload = {
        "schema_version": IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21E-A",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c1_result_closeout_fingerprint": C1_RESULT_CLOSEOUT_FINGERPRINT,
        "parent_champion_r0_fingerprint": CHAMPION_R0_FINGERPRINT,
        "source_baseline_commit": source_baseline_commit,
        "implementation_sha256s": _implementation_sha256s(repo),
        "R1_fit_contract": {
            "specification": DISTANCE_CANDIDATE_ID,
            "fit_stages": ["H1", "H2", "H3", "C1"],
            "event_count": R1_EVENT_COUNT,
            "row_count": R1_ROW_COUNT,
            "feature_selection": False,
            "hyperparameter_search": False,
            "C2_rows_used": 0,
            "C2_outcomes_used": 0,
        },
        "C2_materialization_contract": {
            "strict_tail_start_index": C2_STRICT_TAIL_START_INDEX,
            "eligible_event_target": C2_ELIGIBLE_EVENT_TARGET,
            "subblocks": [f"B{i}" for i in range(C2_SUBBLOCK_COUNT)],
            "events_per_subblock": C2_EVENTS_PER_SUBBLOCK,
            "absolute_max_end_index_exclusive": STRICT_TAIL_MAX_END_EXCLUSIVE,
            "minimum_strict_untouched_tail_after_all_confirmation": (
                MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
            ),
            "max_candidate_identities_across_C2_C3": (
                MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C2_C3
            ),
            "no_arbitrary_start_index": True,
            "C3_materialization_authorized": False,
        },
        "parent_C1_scope": {
            "event_count": c1["C1_event_count"],
            "row_count": c1["C1_row_count"],
            "strict_untouched_tail_remaining": c1["strict_untouched_tail_remaining"],
        },
        "Champion_R1_fit_performed_at_freeze": False,
        "C2_materialization_performed_at_freeze": False,
        "C2_outcomes_opened_at_freeze": 0,
        "C3_materialized_or_opened_at_freeze": False,
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
    verify_implementation_hashes: bool = True,
    verify_parent_lineage: bool = True,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    expected = {
        "schema_version": IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21E-A",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c1_result_closeout_fingerprint": C1_RESULT_CLOSEOUT_FINGERPRINT,
        "parent_champion_r0_fingerprint": CHAMPION_R0_FINGERPRINT,
        "source_baseline_commit": PARENT_21D_RECEIPT_COMMIT,
        "Champion_R1_fit_performed_at_freeze": False,
        "C2_materialization_performed_at_freeze": False,
        "C2_outcomes_opened_at_freeze": 0,
        "C3_materialized_or_opened_at_freeze": False,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"C2 implementation freeze {key} mismatch")

    fit = document.get("R1_fit_contract")
    if not isinstance(fit, Mapping):
        _error("C2 implementation freeze R1 fit contract missing")
    if (
        fit.get("event_count"),
        fit.get("row_count"),
        fit.get("C2_rows_used"),
        fit.get("C2_outcomes_used"),
    ) != (R1_EVENT_COUNT, R1_ROW_COUNT, 0, 0):
        _error("C2 R1 fit scope changed")
    if fit.get("feature_selection") is not False or fit.get("hyperparameter_search") is not False:
        _error("C2 R1 fit contract unexpectedly permits selection/search")

    materialization = document.get("C2_materialization_contract")
    if not isinstance(materialization, Mapping):
        _error("C2 materialization contract missing")
    required_materialization = {
        "strict_tail_start_index": C2_STRICT_TAIL_START_INDEX,
        "eligible_event_target": C2_ELIGIBLE_EVENT_TARGET,
        "events_per_subblock": C2_EVENTS_PER_SUBBLOCK,
        "absolute_max_end_index_exclusive": STRICT_TAIL_MAX_END_EXCLUSIVE,
        "minimum_strict_untouched_tail_after_all_confirmation": (
            MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
        ),
        "max_candidate_identities_across_C2_C3": (
            MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C2_C3
        ),
        "no_arbitrary_start_index": True,
        "C3_materialization_authorized": False,
    }
    for key, value in required_materialization.items():
        if materialization.get(key) != value:
            _error(f"C2 materialization contract {key} changed")
    if materialization.get("subblocks") != [f"B{i}" for i in range(C2_SUBBLOCK_COUNT)]:
        _error("C2 subblock identities changed")

    if verify_implementation_hashes:
        if document.get("implementation_sha256s") != _implementation_sha256s(repo):
            _error("C2 implementation bytes differ from frozen hashes")
    if verify_parent_lineage:
        validate_parent_21d_result_closeout(repo, verify_lineage_files=True)

    payload = {k: document[k] for k in document if k != "implementation_freeze_fingerprint"}
    if document.get("implementation_freeze_fingerprint") != _canonical_sha256(payload):
        _error("C2 implementation freeze fingerprint mismatch")
    return dict(document)


def write_or_validate_implementation_freeze(
    repository_root: str | Path = ".",
    path: str | Path = IMPLEMENTATION_FREEZE_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    head = assert_21d_parent_baseline_for_implementation_freeze(repo)
    target = Path(path)
    if not target.is_absolute():
        target = repo / target
    document = build_implementation_freeze_document(
        repository_root=repo,
        source_baseline_commit=head,
    )
    validate_implementation_freeze_document(document, repository_root=repo)
    if target.exists():
        existing = _read_json(target)
        validate_implementation_freeze_document(existing, repository_root=repo)
        if existing != document:
            _error("existing C2 implementation freeze differs; refusing overwrite")
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


def assert_runtime_checkout_is_frozen_21e_a(
    repository_root: str | Path = ".",
) -> tuple[str, dict[str, Any]]:
    """Require clean synchronized main carrying the safely closed 21E-A bytes."""
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("C2 preparation runtime requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != remote:
        _error(f"C2 preparation requires HEAD == origin/main; HEAD={head}, origin={remote}")
    if _git(repo, "status", "--porcelain"):
        _error("C2 preparation requires a clean worktree")
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PARENT_21D_RECEIPT_COMMIT, head],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        _error("current main is not a descendant of the accepted 21D receipt")
    freeze = load_and_validate_implementation_freeze(repo)
    for relative in (*NEW_IMPLEMENTATION_FILES, IMPLEMENTATION_FREEZE_PATH.as_posix()):
        completed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            _error(f"frozen 21E-A path is not tracked on synchronized main: {relative}")
    return head, freeze


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return tuple(reader.fieldnames or ()), tuple(dict(row) for row in reader)
    except OSError as exc:
        raise CandidateEC2PreparationError(f"could not read CSV {path}: {exc}") from exc


def _build_h1_h2_h3_observations(repo: Path):
    from src.kxbtcd_candidate_e_h1_evaluation import (
        CandidateEObservation,
        DISTANCE_CANDIDATE_ID as FIT_DISTANCE_ID,
        load_and_validate_frozen_universe,
    )
    from src.kxbtcd_candidate_e_h3_preparation import _build_h1_h2_observations
    from src.kxbtcd_candidate_e_h3_result_closeout import (
        OUTCOMES_PATH as H3_OUTCOMES_PATH,
        load_and_validate_result as load_and_validate_h3_result,
    )

    if FIT_DISTANCE_ID != DISTANCE_CANDIDATE_ID:
        _error("Distance candidate ID changed")
    universe = load_and_validate_frozen_universe(repo)
    h1_h2 = _build_h1_h2_observations(repo=repo, universe=universe)
    load_and_validate_h3_result(repo)

    fields, h3_outcomes = _read_csv(repo / H3_OUTCOMES_PATH)
    required = {"event_ticker", "market_ticker", "outcome", "stage"}
    if not required.issubset(set(fields)):
        _error("H3 outcomes no longer contain required fields")
    labels: dict[str, int] = {}
    for index, row in enumerate(h3_outcomes):
        if row.get("stage") != "H3":
            _error(f"H3 outcome row {index} stage changed")
        market = str(row.get("market_ticker") or "")
        if not market or market in labels:
            _error(f"H3 outcome row {index} duplicate/blank market")
        outcome = int(row["outcome"])
        if outcome not in {0, 1}:
            _error("H3 outcome is not binary")
        labels[market] = outcome

    h3: list[CandidateEObservation] = []
    h3_events: set[str] = set()
    state_ids: set[str] = set()
    for index, row in enumerate(universe.preoutcome_rows):
        if str(row["stage"]) != "H3":
            continue
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if market not in labels:
            _error(f"H3 preoutcome row references missing label {market}")
        state_id = (
            f"H3|{event}|{market}|TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in state_ids:
            _error(f"duplicate H3 R1 state identity {state_id}")
        state_ids.add(state_id)
        h3_events.add(event)
        q_market = float(row["q_market"])
        d_btc = float(row["d_BTC"])
        r_5m = float(row["r_5m"])
        if not all(math.isfinite(v) for v in (q_market, d_btc, r_5m)):
            _error(f"H3 preoutcome row {index} contains non-finite model input")
        h3.append(
            CandidateEObservation(
                state_id=state_id,
                event_ticker=event,
                market_ticker=market,
                block_id=f"H3_{row['block_id']}",
                structural_role=str(row["structural_role"]),
                ttc_target_minutes=int(row["ttc_target_minutes"]),
                outcome=labels[market],
                q_market=q_market,
                d_btc=d_btc,
                r_5m=r_5m,
            )
        )
    if len(h3) != H3_ROW_COUNT or len(h3_events) != H3_EVENT_COUNT:
        _error("H3 R1 observation scope changed")
    if len(h1_h2) != H1_ROW_COUNT + H2_ROW_COUNT:
        _error("H1+H2 R1 observation scope changed")
    return universe, tuple(h1_h2) + tuple(h3)


def _build_c1_observations(repo: Path):
    from src.kxbtcd_candidate_e_c1_evaluation import load_and_validate_c1_frozen_data
    from src.kxbtcd_candidate_e_h1_evaluation import CandidateEObservation

    closeout = validate_parent_21d_result_closeout(repo, verify_lineage_files=True)
    frozen = load_and_validate_c1_frozen_data(repo)
    outcomes_path = repo / str(closeout["outcomes_path"])
    _, outcomes = _read_csv(outcomes_path)

    labels: dict[str, int] = {}
    for index, row in enumerate(outcomes):
        if row.get("stage") != "C1":
            _error(f"C1 outcome row {index} stage changed")
        market = str(row.get("market_ticker") or "")
        if not market or market in labels:
            _error(f"C1 outcome row {index} duplicate/blank market")
        outcome = int(row["outcome"])
        if outcome not in {0, 1}:
            _error("C1 outcome is not binary")
        labels[market] = outcome
    if len(labels) != int(closeout["C1_market_count"]):
        _error("C1 label count changed")

    observations: list[CandidateEObservation] = []
    events: set[str] = set()
    state_ids: set[str] = set()
    for index, row in enumerate(frozen.preoutcome_rows):
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if market not in labels:
            _error(f"C1 preoutcome row references missing label {market}")
        state_id = (
            f"C1|{event}|{market}|TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in state_ids:
            _error(f"duplicate C1 R1 state identity {state_id}")
        state_ids.add(state_id)
        events.add(event)
        q_market = float(row["q_market"])
        d_btc = float(row["d_BTC"])
        r_5m = float(row["r_5m"])
        if not all(math.isfinite(v) for v in (q_market, d_btc, r_5m)):
            _error(f"C1 preoutcome row {index} contains non-finite model input")
        observations.append(
            CandidateEObservation(
                state_id=state_id,
                event_ticker=event,
                market_ticker=market,
                block_id=f"C1_{row['block_id']}",
                structural_role=str(row["structural_role"]),
                ttc_target_minutes=int(row["ttc_target_minutes"]),
                outcome=labels[market],
                q_market=q_market,
                d_btc=d_btc,
                r_5m=r_5m,
            )
        )
    if len(observations) != C1_ROW_COUNT or len(events) != C1_EVENT_COUNT:
        _error("C1 R1 observation scope changed")
    return tuple(observations)


def build_r1_model_document(repository_root: str | Path = ".") -> dict[str, Any]:
    """Fit unchanged Distance champion on exposed H1+H2+H3+C1 only."""
    repo = Path(repository_root).resolve()
    _, implementation_freeze = assert_runtime_checkout_is_frozen_21e_a(repo)
    c1_closeout = validate_parent_21d_result_closeout(repo, verify_lineage_files=True)

    from src.kxbtcd_candidate_e_h1_evaluation import (
        DISTANCE_CANDIDATE_ID as FIT_DISTANCE_ID,
        fit_candidate_e,
    )
    from src.kxbtcd_candidate_e_predeclaration import candidate_e_predeclaration

    if FIT_DISTANCE_ID != DISTANCE_CANDIDATE_ID:
        _error("Distance candidate ID changed")

    _, prior = _build_h1_h2_h3_observations(repo)
    c1 = _build_c1_observations(repo)
    observations = tuple(prior) + tuple(c1)

    if len(observations) != R1_ROW_COUNT:
        _error(f"R1 row count changed: {len(observations)} != {R1_ROW_COUNT}")
    if len({row.event_ticker for row in observations}) != R1_EVENT_COUNT:
        _error("R1 event count changed")

    fit = fit_candidate_e(
        observations,
        candidate_id=DISTANCE_CANDIDATE_ID,
        fold=0,
        fit_blocks=("H1", "H2", "H3", "C1"),
        score_block="C2",
    )
    if not fit.converged or not math.isfinite(fit.beta_distance) or fit.beta_distance <= 0.0:
        _error("Champion-R1 fit did not produce a finite positive distance coefficient")
    if fit.beta_momentum is not None:
        _error("Champion-R1 unexpectedly fit momentum")

    payload = {
        "schema_version": R1_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "21E-B",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c1_result_closeout_fingerprint": C1_RESULT_CLOSEOUT_FINGERPRINT,
        "parent_champion_r0_fingerprint": CHAMPION_R0_FINGERPRINT,
        "implementation_freeze_fingerprint": implementation_freeze[
            "implementation_freeze_fingerprint"
        ],
        "fit_scope": {
            "stages": ["H1", "H2", "H3", "C1"],
            "event_count": R1_EVENT_COUNT,
            "row_count": R1_ROW_COUNT,
            "all_outcomes_previously_exposed": True,
            "C2_rows_used": 0,
            "C2_outcomes_used": 0,
        },
        "model": {
            "formula": "logit(p)=market_logit_offset + beta_distance*d_BTC",
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
            "c1_result_closeout_path": C1_RESULT_CLOSEOUT_PATH.as_posix(),
            "c1_result_closeout_sha256": _sha256_file(repo / C1_RESULT_CLOSEOUT_PATH),
            "c1_outcomes_path": str(c1_closeout["outcomes_path"]),
            "c1_outcomes_sha256": str(c1_closeout["outcomes_sha256"]),
            "implementation_freeze_path": IMPLEMENTATION_FREEZE_PATH.as_posix(),
            "implementation_freeze_sha256": _sha256_file(repo / IMPLEMENTATION_FREEZE_PATH),
        },
        "specification_changed_after_C1": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "C2_outcomes_opened": False,
        "C3_materialized_or_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["champion_r1_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_r1_model_document(
    document: Mapping[str, Any],
    *,
    implementation_freeze: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = {
        "schema_version": R1_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "21E-B",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c1_result_closeout_fingerprint": C1_RESULT_CLOSEOUT_FINGERPRINT,
        "parent_champion_r0_fingerprint": CHAMPION_R0_FINGERPRINT,
        "specification_changed_after_C1": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "C2_outcomes_opened": False,
        "C3_materialized_or_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"Champion-R1 {key} mismatch")
    scope = document.get("fit_scope")
    if not isinstance(scope, Mapping):
        _error("Champion-R1 fit scope missing")
    if (
        scope.get("event_count"),
        scope.get("row_count"),
        scope.get("C2_rows_used"),
        scope.get("C2_outcomes_used"),
    ) != (R1_EVENT_COUNT, R1_ROW_COUNT, 0, 0):
        _error("Champion-R1 fit scope changed")
    model = document.get("model")
    if not isinstance(model, Mapping):
        _error("Champion-R1 model section missing")
    try:
        beta = float(model.get("beta_distance"))
    except (TypeError, ValueError) as exc:
        raise CandidateEC2PreparationError("Champion-R1 beta_distance is not numeric") from exc
    if not math.isfinite(beta) or beta <= 0.0 or model.get("beta_momentum") is not None:
        _error("Champion-R1 coefficient state is invalid")
    fit = document.get("fit_result")
    if not isinstance(fit, Mapping) or fit.get("converged") is not True:
        _error("Champion-R1 fit result is not converged")
    if implementation_freeze is not None:
        if document.get("implementation_freeze_fingerprint") != implementation_freeze.get(
            "implementation_freeze_fingerprint"
        ):
            _error("Champion-R1 implementation-freeze fingerprint mismatch")
    payload = {k: document[k] for k in document if k != "champion_r1_fingerprint"}
    if document.get("champion_r1_fingerprint") != _canonical_sha256(payload):
        _error("Champion-R1 fingerprint mismatch")
    return dict(document)


def load_and_validate_r1_model(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    freeze = load_and_validate_implementation_freeze(repo)
    return validate_r1_model_document(
        _read_json(repo / R1_MODEL_PATH),
        implementation_freeze=freeze,
    )


def write_or_validate_r1_model(
    repository_root: str | Path = ".",
    path: str | Path = R1_MODEL_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = repo / target
    derived = build_r1_model_document(repo)
    validate_r1_model_document(
        derived,
        implementation_freeze=load_and_validate_implementation_freeze(repo),
    )
    if target.exists():
        existing = _read_json(target)
        validate_r1_model_document(
            existing,
            implementation_freeze=load_and_validate_implementation_freeze(repo),
        )
        if existing != derived:
            _error("existing Champion-R1 artifact differs; refusing overwrite/refit ambiguity")
        return target, existing
    _write_json_atomic(target, derived)
    return target, derived


def c2_subblock_for_eligible_rank(rank_zero_based: int) -> str:
    if not 0 <= rank_zero_based < C2_ELIGIBLE_EVENT_TARGET:
        _error(f"C2 eligible rank out of range: {rank_zero_based}")
    return f"B{rank_zero_based // C2_EVENTS_PER_SUBBLOCK}"


def strict_tail_remaining_after_end_index(end_index_exclusive: int) -> int:
    if not C2_STRICT_TAIL_START_INDEX <= end_index_exclusive <= UNTOUCHED_QUEUE_EVENT_COUNT:
        _error(f"strict-tail end index out of range: {end_index_exclusive}")
    return UNTOUCHED_QUEUE_EVENT_COUNT - end_index_exclusive


def validate_candidate_end_index(end_index_exclusive: int) -> None:
    remaining = strict_tail_remaining_after_end_index(end_index_exclusive)
    if end_index_exclusive > STRICT_TAIL_MAX_END_EXCLUSIVE:
        _error(
            "C2/C3 candidate runway would violate the 21A hard floor; "
            f"end={end_index_exclusive}, max={STRICT_TAIL_MAX_END_EXCLUSIVE}, remaining={remaining}"
        )
    if remaining < MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION:
        _error("strict untouched tail fell below the 21A hard floor")


__all__ = [
    "C2_CHUNK_ROOT",
    "C2_COLLECTOR_NAME",
    "C2_ELIGIBLE_EVENT_TARGET",
    "C2_EVENTS_PER_SUBBLOCK",
    "C2_FROZEN_ROOT",
    "C2_STRICT_TAIL_START_INDEX",
    "C2_SUBBLOCK_COUNT",
    "C2_VALIDATION_FREEZE_PATH",
    "CandidateEC2PreparationError",
    "IMPLEMENTATION_FREEZE_PATH",
    "MAX_C2_CHUNK_EVENTS",
    "MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION",
    "R1_MODEL_PATH",
    "STRICT_TAIL_MAX_END_EXCLUSIVE",
    "UNTOUCHED_QUEUE_EVENT_COUNT",
    "_canonical_sha256",
    "_read_json",
    "_sha256_file",
    "_write_json_atomic",
    "assert_runtime_checkout_is_frozen_21e_a",
    "c2_subblock_for_eligible_rank",
    "load_and_validate_implementation_freeze",
    "load_and_validate_r1_model",
    "strict_tail_remaining_after_end_index",
    "validate_candidate_end_index",
    "validate_parent_21d_result_closeout",
    "write_or_validate_implementation_freeze",
    "write_or_validate_r1_model",
]
