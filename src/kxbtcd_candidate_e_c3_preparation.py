"""Checkpoint 21G-A: Candidate-E C3 preparation contracts.

21G-A freezes implementation bytes only. It performs no Champion-R2 fit,
no C3 materialization, no C3 outcome access, and no execution.

After safe closeout, the frozen implementation may:
1. deterministically refit the unchanged Distance champion on the already
   exposed H1+H2+H3+C1+C2 evidence (4,000 events / 109,971 rows);
2. freeze Champion-R2;
3. only after Champion-R2 is safely closed, sequentially materialize C3
   outcome-blind from the strict historical tail;
4. freeze exactly 500 eligible C3 events into five chronological 100-event
   subblocks without opening C3 outcomes.

The absolute Checkpoint-21A reserve boundary is not reset. C3 begins at queue
index 4222 and may inspect at most 709 candidate identities before the protected
4,500-event untouched-tail floor would be violated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping

PARENT_21F_B_RECEIPT_COMMIT = "05c9b7fca4e399d1f8047514f681691d579839f1"
PARENT_21A_PROTOCOL_FINGERPRINT = "88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00"
PARENT_H3_RESULT_FINGERPRINT = "436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54"
C1_RESULT_FINGERPRINT = "5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19"
C2_RESULT_FINGERPRINT = "ee6cd30b32a9445096f25934d67dfa34046504ee83889947be8c8a40377a8f62"
C2_RESULT_CLOSEOUT_FINGERPRINT = "5660e4d04856f534543f0fdd53a1b687b07666ffd52d59e8e80fcefe6ddc87cf"
CHAMPION_R1_FINGERPRINT = "863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee"

FAMILY_ID = "kxbtcd_independent_btc_offset_successor.v1"
DISTANCE_CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"

UNTOUCHED_QUEUE_EVENT_COUNT = 9431
C3_STRICT_TAIL_START_INDEX = 4222
C3_STRICT_TAIL_EVENT_COUNT_ENTERING = (
    UNTOUCHED_QUEUE_EVENT_COUNT - C3_STRICT_TAIL_START_INDEX
)
C3_ELIGIBLE_EVENT_TARGET = 500
C3_SUBBLOCK_COUNT = 5
C3_EVENTS_PER_SUBBLOCK = 100
MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION = 4500
STRICT_TAIL_MAX_END_EXCLUSIVE = 4931
MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3 = (
    STRICT_TAIL_MAX_END_EXCLUSIVE - C3_STRICT_TAIL_START_INDEX
)
MAX_C3_CHUNK_EVENTS = 100

H1_EVENT_COUNT = 1500
H2_EVENT_COUNT = 750
H3_EVENT_COUNT = 750
C1_EVENT_COUNT = 500
C2_EVENT_COUNT = 500

H1_ROW_COUNT = 36314
H2_ROW_COUNT = 22354
H3_ROW_COUNT = 22409
C1_ROW_COUNT = 14887
C2_ROW_COUNT = 14007

R2_EVENT_COUNT = (
    H1_EVENT_COUNT
    + H2_EVENT_COUNT
    + H3_EVENT_COUNT
    + C1_EVENT_COUNT
    + C2_EVENT_COUNT
)
R2_ROW_COUNT = (
    H1_ROW_COUNT
    + H2_ROW_COUNT
    + H3_ROW_COUNT
    + C1_ROW_COUNT
    + C2_ROW_COUNT
)

IMPLEMENTATION_FREEZE_SCHEMA_VERSION = (
    "kxbtcd_candidate_e_c3_preparation_implementation_freeze.v1"
)
R2_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_e_champion_r2.v1"
C3_VALIDATION_FREEZE_SCHEMA_VERSION = (
    "kxbtcd_candidate_e_c3_validation_freeze.v1"
)

PARENT_PROTOCOL_PATH = Path(
    "configs/kxbtcd_post_h3_champion_lifecycle.v1.json"
)
C2_RESULT_CLOSEOUT_PATH = Path(
    "configs/kxbtcd_candidate_e_c2_result_closeout.json"
)
R1_MODEL_PATH = Path(
    "configs/kxbtcd_candidate_e_champion_r1.json"
)
IMPLEMENTATION_FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_e_c3_preparation_implementation_freeze.json"
)
R2_MODEL_PATH = Path(
    "configs/kxbtcd_candidate_e_champion_r2.json"
)
C3_VALIDATION_FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_e_c3_validation_freeze.json"
)
LAST_CLOSEOUT_PATH = Path(
    "docs/LAST_CHECKPOINT_CLOSEOUT.json"
)

C3_CHUNK_ROOT = Path(
    "data/derived/kxbtcd_candidate_e_c3_preoutcome/chunks"
)
C3_FROZEN_ROOT = Path(
    "data/derived/kxbtcd_candidate_e_c3_preoutcome/frozen"
)
C3_COLLECTOR_NAME = (
    "collect_kxbtcd_candidate_e_c3_materialization_chunk"
)

NEW_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_c3_preparation.py",
    "prepare_kxbtcd_candidate_e_c3.py",
    "collect_kxbtcd_candidate_e_c3_materialization_chunk.py",
    "freeze_kxbtcd_candidate_e_c3_preoutcome.py",
)

DEPENDENCY_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_c2_preparation.py",
    "src/kxbtcd_candidate_e_c2_evaluation.py",
    "src/kxbtcd_candidate_e_c1_evaluation.py",
    "src/kxbtcd_candidate_e_h1_evaluation.py",
    "src/kxbtcd_candidate_e_h3_preparation.py",
    "src/kxbtcd_candidate_e_h3_result_closeout.py",
    "collect_kxbtcd_candidate_e_coinbase_primary_materialization_chunk.py",
    "collect_kxbtcd_candidate_e_historical_materialization_chunk.py",
    "src/kxbtcd_candidate_e_coinbase_primary_materialization.py",
    "src/kxbtcd_candidate_e_historical_materialization.py",
)
IMPLEMENTATION_FILES = (
    NEW_IMPLEMENTATION_FILES
    + DEPENDENCY_IMPLEMENTATION_FILES
)

FREEZE_BUNDLE_UNTRACKED_PATHS = frozenset(
    {
        *NEW_IMPLEMENTATION_FILES,
        "freeze_kxbtcd_candidate_e_c3_preparation_implementation.py",
        "tests/test_kxbtcd_candidate_e_c3_preparation.py",
        "docs/KXBTCD_CANDIDATE_E_C3_PREPARATION_IMPLEMENTATION_FREEZE.md",
        "scripts/apply_checkpoint21g_a_docs.py",
        "README_CHECKPOINT21G_A.txt",
    }
)


class CandidateEC3PreparationError(RuntimeError):
    """Raised when a Checkpoint-21G C3-preparation invariant fails."""


def _error(message: str) -> None:
    raise CandidateEC3PreparationError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise CandidateEC3PreparationError(
            f"could not read JSON {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be object: {path}")
    return value


def _write_json_atomic(
    path: Path,
    value: Mapping[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temp = path.with_suffix(
        path.suffix + ".tmp"
    )
    temp.write_text(
        json.dumps(
            dict(value),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


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
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def _float_text(value: float) -> str:
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return (
            "inf"
            if value > 0
            else "-inf"
        )
    return format(value, ".17g")


def _git(
    repo: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (
            completed.stderr
            or completed.stdout
            or ""
        ).strip()
        _error(
            f"git {' '.join(args)} failed: "
            f"{detail or completed.returncode}"
        )
    return completed.stdout.strip()


def _implementation_sha256s(
    repo: Path,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(
                "C3 preparation implementation/"
                f"dependency missing: {relative}"
            )
        result[relative] = _sha256_file(
            path
        )
    return result


def validate_parent_21f_b_result_closeout(
    repository_root: str | Path = ".",
    *,
    verify_lineage_files: bool = True,
) -> dict[str, Any]:
    repo = Path(
        repository_root
    ).resolve()
    document = _read_json(
        repo / C2_RESULT_CLOSEOUT_PATH
    )

    expected = {
        "schema_version": (
            "kxbtcd_candidate_e_c2_result_closeout.v1"
        ),
        "checkpoint_id": "21F-B",
        "c2_result_fingerprint": (
            C2_RESULT_FINGERPRINT
        ),
        "c2_result_closeout_fingerprint": (
            C2_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "champion_r1_fingerprint": (
            CHAMPION_R1_FINGERPRINT
        ),
        "C2_event_count": C2_EVENT_COUNT,
        "C2_row_count": C2_ROW_COUNT,
        "C2_validation_passed": True,
        "C2_permanently_exposed": True,
        "strict_untouched_tail_remaining": (
            C3_STRICT_TAIL_EVENT_COUNT_ENTERING
        ),
        "model_parameters_fitted_on_C2": False,
        "candidate_selection_on_C2_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "C3_materialized_or_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(
                f"parent C2 result closeout "
                f"{key} mismatch"
            )

    payload = {
        key: document[key]
        for key in document
        if key
        != "c2_result_closeout_fingerprint"
    }
    if (
        _canonical_sha256(payload)
        != C2_RESULT_CLOSEOUT_FINGERPRINT
    ):
        _error(
            "parent C2 result closeout "
            "canonical fingerprint mismatch"
        )

    if verify_lineage_files:
        lineage_pairs = (
            (
                "manifest_path",
                "manifest_sha256",
            ),
            (
                "summary_path",
                "summary_sha256",
            ),
            (
                "block_scores_path",
                "block_scores_sha256",
            ),
            (
                "predictions_path",
                "predictions_sha256",
            ),
            (
                "event_scores_path",
                "event_scores_sha256",
            ),
            (
                "outcomes_path",
                "outcomes_sha256",
            ),
            (
                "attempt_path",
                "attempt_sha256",
            ),
        )
        for path_key, hash_key in lineage_pairs:
            relative = document.get(
                path_key
            )
            expected_hash = document.get(
                hash_key
            )
            if (
                not isinstance(relative, str)
                or not relative
            ):
                _error(
                    "parent C2 closeout missing "
                    f"{path_key}"
                )
            path = repo / relative
            if not path.is_file():
                _error(
                    "parent C2 lineage file "
                    f"missing: {relative}"
                )
            if (
                _sha256_file(path)
                != expected_hash
            ):
                _error(
                    "parent C2 lineage hash "
                    f"mismatch: {relative}"
                )
    return document


def assert_21f_b_parent_baseline_for_implementation_freeze(
    repository_root: str | Path = ".",
) -> str:
    """Require exact clean 21F-B receipt before generating 21G-A freeze.

    New 21G-A bundle files may be untracked. Existing tracked files must be
    clean, and unexpected untracked files fail closed.
    """
    repo = Path(
        repository_root
    ).resolve()

    _git(repo, "fetch", "origin")
    if (
        _git(
            repo,
            "branch",
            "--show-current",
        )
        != "main"
    ):
        _error(
            "Checkpoint-21G-A implementation "
            "freeze requires branch main"
        )

    head = _git(
        repo,
        "rev-parse",
        "HEAD",
    )
    remote = _git(
        repo,
        "rev-parse",
        "origin/main",
    )
    expected = (
        PARENT_21F_B_RECEIPT_COMMIT
    )
    if (
        head != expected
        or remote != expected
    ):
        _error(
            "Checkpoint-21G-A parent mismatch; "
            "expected HEAD == origin/main == "
            f"{expected}, got HEAD={head}, "
            f"origin/main={remote}"
        )

    if _git(
        repo,
        "diff",
        "--name-only",
    ):
        _error(
            "tracked unstaged changes existed "
            "before Checkpoint-21G-A freeze"
        )
    if _git(
        repo,
        "diff",
        "--cached",
        "--name-only",
    ):
        _error(
            "staged changes existed before "
            "Checkpoint-21G-A freeze"
        )

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
        path = (
            raw[3:]
            .replace("\\", "/")
        )
        if (
            code != "??"
            or path
            not in FREEZE_BUNDLE_UNTRACKED_PATHS
        ):
            unexpected.append(raw)
    if unexpected:
        _error(
            "unexpected worktree state before "
            "Checkpoint-21G-A freeze; "
            f"first unexpected line: "
            f"{unexpected[0]}"
        )

    receipt = _read_json(
        repo / LAST_CLOSEOUT_PATH
    )
    if (
        receipt.get("checkpoint_commit")
        != "8d7bb49b8b16ed9c0a276e738d13314ba5dc63c3"
    ):
        _error(
            "latest closeout does not record "
            "the exact 21F-B result commit"
        )
    if (
        receipt.get("checkpoint_message")
        != "Checkpoint 21F-B: record Candidate-E C2 confirmation PASS"
    ):
        _error(
            "latest closeout 21F-B message changed"
        )

    safety = receipt.get("safety")
    if not isinstance(
        safety,
        Mapping,
    ):
        _error(
            "latest closeout safety "
            "record missing"
        )
    for key in (
        "blocked_path_check",
        "high_confidence_secret_scan",
        "staged_diff_check",
        "staged_path_exact_match",
    ):
        if safety.get(key) != "PASS":
            _error(
                "latest 21F-B safety field "
                f"{key} did not PASS"
            )

    validate_parent_21f_b_result_closeout(
        repo,
        verify_lineage_files=True,
    )
    return head


def build_implementation_freeze_document(
    *,
    repository_root: str | Path,
    source_baseline_commit: str,
) -> dict[str, Any]:
    repo = Path(
        repository_root
    ).resolve()
    c2 = (
        validate_parent_21f_b_result_closeout(
            repo,
            verify_lineage_files=True,
        )
    )

    payload = {
        "schema_version": (
            IMPLEMENTATION_FREEZE_SCHEMA_VERSION
        ),
        "checkpoint_id": "21G-A",
        "family_id": FAMILY_ID,
        "candidate_id": (
            DISTANCE_CANDIDATE_ID
        ),
        "parent_21a_protocol_fingerprint": (
            PARENT_21A_PROTOCOL_FINGERPRINT
        ),
        "parent_h3_result_fingerprint": (
            PARENT_H3_RESULT_FINGERPRINT
        ),
        "parent_c1_result_fingerprint": (
            C1_RESULT_FINGERPRINT
        ),
        "parent_c2_result_fingerprint": (
            C2_RESULT_FINGERPRINT
        ),
        "parent_c2_result_closeout_fingerprint": (
            C2_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r1_fingerprint": (
            CHAMPION_R1_FINGERPRINT
        ),
        "source_baseline_commit": (
            source_baseline_commit
        ),
        "implementation_sha256s": (
            _implementation_sha256s(repo)
        ),
        "R2_fit_contract": {
            "specification": (
                DISTANCE_CANDIDATE_ID
            ),
            "fit_stages": [
                "H1",
                "H2",
                "H3",
                "C1",
                "C2",
            ],
            "event_count": R2_EVENT_COUNT,
            "row_count": R2_ROW_COUNT,
            "feature_selection": False,
            "hyperparameter_search": False,
            "C3_rows_used": 0,
            "C3_outcomes_used": 0,
        },
        "C3_materialization_contract": {
            "strict_tail_start_index": (
                C3_STRICT_TAIL_START_INDEX
            ),
            "eligible_event_target": (
                C3_ELIGIBLE_EVENT_TARGET
            ),
            "subblocks": [
                f"B{i}"
                for i
                in range(
                    C3_SUBBLOCK_COUNT
                )
            ],
            "events_per_subblock": (
                C3_EVENTS_PER_SUBBLOCK
            ),
            "absolute_max_end_index_exclusive": (
                STRICT_TAIL_MAX_END_EXCLUSIVE
            ),
            "minimum_strict_untouched_tail_after_all_confirmation": (
                MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
            ),
            "max_candidate_identities_for_C3": (
                MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3
            ),
            "no_arbitrary_start_index": True,
        },
        "parent_C2_scope": {
            "event_count": c2[
                "C2_event_count"
            ],
            "row_count": c2[
                "C2_row_count"
            ],
            "strict_untouched_tail_remaining": (
                c2[
                    "strict_untouched_tail_remaining"
                ]
            ),
        },
        "Champion_R2_fit_performed_at_freeze": False,
        "C3_materialization_performed_at_freeze": False,
        "C3_outcomes_opened_at_freeze": 0,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document[
        "implementation_freeze_fingerprint"
    ] = _canonical_sha256(
        payload
    )
    return document


def validate_implementation_freeze_document(
    document: Mapping[str, Any],
    *,
    repository_root: str | Path = ".",
    verify_implementation_hashes: bool = True,
    verify_parent_lineage: bool = True,
) -> dict[str, Any]:
    repo = Path(
        repository_root
    ).resolve()

    expected = {
        "schema_version": (
            IMPLEMENTATION_FREEZE_SCHEMA_VERSION
        ),
        "checkpoint_id": "21G-A",
        "family_id": FAMILY_ID,
        "candidate_id": (
            DISTANCE_CANDIDATE_ID
        ),
        "parent_21a_protocol_fingerprint": (
            PARENT_21A_PROTOCOL_FINGERPRINT
        ),
        "parent_h3_result_fingerprint": (
            PARENT_H3_RESULT_FINGERPRINT
        ),
        "parent_c1_result_fingerprint": (
            C1_RESULT_FINGERPRINT
        ),
        "parent_c2_result_fingerprint": (
            C2_RESULT_FINGERPRINT
        ),
        "parent_c2_result_closeout_fingerprint": (
            C2_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r1_fingerprint": (
            CHAMPION_R1_FINGERPRINT
        ),
        "source_baseline_commit": (
            PARENT_21F_B_RECEIPT_COMMIT
        ),
        "Champion_R2_fit_performed_at_freeze": False,
        "C3_materialization_performed_at_freeze": False,
        "C3_outcomes_opened_at_freeze": 0,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(
                "C3 implementation freeze "
                f"{key} mismatch"
            )

    fit = document.get(
        "R2_fit_contract"
    )
    if not isinstance(
        fit,
        Mapping,
    ):
        _error(
            "C3 implementation freeze "
            "R2 fit contract missing"
        )
    if (
        fit.get("event_count"),
        fit.get("row_count"),
        fit.get("C3_rows_used"),
        fit.get("C3_outcomes_used"),
    ) != (
        R2_EVENT_COUNT,
        R2_ROW_COUNT,
        0,
        0,
    ):
        _error(
            "C3 R2 fit scope changed"
        )
    if (
        fit.get("fit_stages")
        != [
            "H1",
            "H2",
            "H3",
            "C1",
            "C2",
        ]
    ):
        _error(
            "C3 R2 fit stages changed"
        )
    if (
        fit.get("feature_selection")
        is not False
        or fit.get(
            "hyperparameter_search"
        )
        is not False
    ):
        _error(
            "C3 R2 fit contract "
            "unexpectedly permits "
            "selection/search"
        )

    materialization = (
        document.get(
            "C3_materialization_contract"
        )
    )
    if not isinstance(
        materialization,
        Mapping,
    ):
        _error(
            "C3 materialization "
            "contract missing"
        )
    required_materialization = {
        "strict_tail_start_index": (
            C3_STRICT_TAIL_START_INDEX
        ),
        "eligible_event_target": (
            C3_ELIGIBLE_EVENT_TARGET
        ),
        "events_per_subblock": (
            C3_EVENTS_PER_SUBBLOCK
        ),
        "absolute_max_end_index_exclusive": (
            STRICT_TAIL_MAX_END_EXCLUSIVE
        ),
        "minimum_strict_untouched_tail_after_all_confirmation": (
            MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
        ),
        "max_candidate_identities_for_C3": (
            MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3
        ),
        "no_arbitrary_start_index": True,
    }
    for key, value in (
        required_materialization.items()
    ):
        if (
            materialization.get(key)
            != value
        ):
            _error(
                "C3 materialization contract "
                f"{key} changed"
            )
    if (
        materialization.get(
            "subblocks"
        )
        != [
            f"B{i}"
            for i
            in range(
                C3_SUBBLOCK_COUNT
            )
        ]
    ):
        _error(
            "C3 subblock identities changed"
        )

    if verify_implementation_hashes:
        if (
            document.get(
                "implementation_sha256s"
            )
            != _implementation_sha256s(
                repo
            )
        ):
            _error(
                "C3 implementation bytes "
                "differ from frozen hashes"
            )

    if verify_parent_lineage:
        validate_parent_21f_b_result_closeout(
            repo,
            verify_lineage_files=True,
        )

    payload = {
        key: document[key]
        for key in document
        if key
        != "implementation_freeze_fingerprint"
    }
    if (
        document.get(
            "implementation_freeze_fingerprint"
        )
        != _canonical_sha256(
            payload
        )
    ):
        _error(
            "C3 implementation "
            "freeze fingerprint mismatch"
        )
    return dict(document)


def write_or_validate_implementation_freeze(
    repository_root: str | Path = ".",
    path: str | Path = IMPLEMENTATION_FREEZE_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(
        repository_root
    ).resolve()
    head = (
        assert_21f_b_parent_baseline_for_implementation_freeze(
            repo
        )
    )

    target = Path(path)
    if not target.is_absolute():
        target = repo / target

    document = (
        build_implementation_freeze_document(
            repository_root=repo,
            source_baseline_commit=head,
        )
    )
    validate_implementation_freeze_document(
        document,
        repository_root=repo,
    )

    if target.exists():
        existing = _read_json(
            target
        )
        validate_implementation_freeze_document(
            existing,
            repository_root=repo,
        )
        if existing != document:
            _error(
                "existing C3 implementation "
                "freeze differs; refusing "
                "overwrite"
            )
        return target, existing

    _write_json_atomic(
        target,
        document,
    )
    return target, document


def load_and_validate_implementation_freeze(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(
        repository_root
    ).resolve()
    return validate_implementation_freeze_document(
        _read_json(
            repo
            / IMPLEMENTATION_FREEZE_PATH
        ),
        repository_root=repo,
    )


def assert_runtime_checkout_is_frozen_21g_a(
    repository_root: str | Path = ".",
) -> tuple[str, dict[str, Any]]:
    """Require clean synchronized main carrying safely closed 21G-A bytes."""
    repo = Path(
        repository_root
    ).resolve()
    _git(
        repo,
        "fetch",
        "origin",
    )
    if (
        _git(
            repo,
            "branch",
            "--show-current",
        )
        != "main"
    ):
        _error(
            "C3 preparation runtime "
            "requires branch main"
        )

    head = _git(
        repo,
        "rev-parse",
        "HEAD",
    )
    remote = _git(
        repo,
        "rev-parse",
        "origin/main",
    )
    if head != remote:
        _error(
            "C3 preparation requires "
            "HEAD == origin/main; "
            f"HEAD={head}, "
            f"origin={remote}"
        )

    if _git(
        repo,
        "status",
        "--porcelain",
    ):
        _error(
            "C3 preparation requires "
            "a clean worktree"
        )

    completed = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            PARENT_21F_B_RECEIPT_COMMIT,
            head,
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        _error(
            "current main is not a "
            "descendant of accepted "
            "21F-B receipt"
        )

    freeze = (
        load_and_validate_implementation_freeze(
            repo
        )
    )
    for relative in (
        *NEW_IMPLEMENTATION_FILES,
        IMPLEMENTATION_FREEZE_PATH.as_posix(),
    ):
        completed = subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                relative,
            ],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            _error(
                "frozen 21G-A path is "
                "not tracked on synchronized "
                f"main: {relative}"
            )

    return head, freeze


def _read_csv(
    path: Path,
) -> tuple[
    tuple[str, ...],
    tuple[dict[str, str], ...],
]:
    try:
        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            reader = csv.DictReader(
                handle
            )
            return (
                tuple(
                    reader.fieldnames
                    or ()
                ),
                tuple(
                    dict(row)
                    for row
                    in reader
                ),
            )
    except OSError as exc:
        raise CandidateEC3PreparationError(
            f"could not read CSV "
            f"{path}: {exc}"
        ) from exc


def _build_prior_observations(
    repo: Path,
):
    from src.kxbtcd_candidate_e_c2_preparation import (
        _build_c1_observations,
        _build_h1_h2_h3_observations,
    )

    universe, h123 = (
        _build_h1_h2_h3_observations(
            repo
        )
    )
    c1 = _build_c1_observations(
        repo
    )

    if (
        len(h123)
        != (
            H1_ROW_COUNT
            + H2_ROW_COUNT
            + H3_ROW_COUNT
        )
    ):
        _error(
            "H1/H2/H3 R2 observation "
            "scope changed"
        )
    if len(c1) != C1_ROW_COUNT:
        _error(
            "C1 R2 observation scope "
            "changed"
        )

    return (
        universe,
        tuple(h123)
        + tuple(c1),
    )


def _build_c2_observations(
    repo: Path,
):
    from src.kxbtcd_candidate_e_c2_evaluation import (
        load_and_validate_c2_frozen_data,
    )
    from src.kxbtcd_candidate_e_h1_evaluation import (
        CandidateEObservation,
    )

    closeout = (
        validate_parent_21f_b_result_closeout(
            repo,
            verify_lineage_files=True,
        )
    )
    frozen = (
        load_and_validate_c2_frozen_data(
            repo
        )
    )
    outcomes_path = (
        repo
        / str(
            closeout["outcomes_path"]
        )
    )
    _, outcomes = _read_csv(
        outcomes_path
    )

    labels: dict[str, int] = {}
    for index, row in enumerate(
        outcomes
    ):
        if row.get("stage") != "C2":
            _error(
                f"C2 outcome row {index} "
                "stage changed"
            )
        market = str(
            row.get(
                "market_ticker"
            )
            or ""
        )
        if (
            not market
            or market in labels
        ):
            _error(
                f"C2 outcome row {index} "
                "duplicate/blank market"
            )
        outcome = int(
            row["outcome"]
        )
        if outcome not in {
            0,
            1,
        }:
            _error(
                "C2 outcome is "
                "not binary"
            )
        labels[market] = outcome

    if (
        len(labels)
        != int(
            closeout[
                "C2_market_count"
            ]
        )
    ):
        _error(
            "C2 label count changed"
        )

    observations: list[
        CandidateEObservation
    ] = []
    events: set[str] = set()
    state_ids: set[str] = set()

    for index, row in enumerate(
        frozen.preoutcome_rows
    ):
        event = str(
            row["event_ticker"]
        )
        market = str(
            row["market_ticker"]
        )
        if market not in labels:
            _error(
                "C2 preoutcome row "
                "references missing label "
                f"{market}"
            )

        state_id = (
            f"C2|{event}|{market}|"
            f"TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in state_ids:
            _error(
                "duplicate C2 R2 "
                f"state identity {state_id}"
            )
        state_ids.add(state_id)
        events.add(event)

        q_market = float(
            row["q_market"]
        )
        d_btc = float(
            row["d_BTC"]
        )
        r_5m = float(
            row["r_5m"]
        )
        if not all(
            math.isfinite(value)
            for value
            in (
                q_market,
                d_btc,
                r_5m,
            )
        ):
            _error(
                f"C2 preoutcome row {index} "
                "contains non-finite model input"
            )

        observations.append(
            CandidateEObservation(
                state_id=state_id,
                event_ticker=event,
                market_ticker=market,
                block_id=(
                    f"C2_{row['block_id']}"
                ),
                structural_role=str(
                    row[
                        "structural_role"
                    ]
                ),
                ttc_target_minutes=int(
                    row[
                        "ttc_target_minutes"
                    ]
                ),
                outcome=labels[
                    market
                ],
                q_market=q_market,
                d_btc=d_btc,
                r_5m=r_5m,
            )
        )

    if (
        len(observations)
        != C2_ROW_COUNT
        or len(events)
        != C2_EVENT_COUNT
    ):
        _error(
            "C2 R2 observation "
            "scope changed"
        )
    return tuple(
        observations
    )


def build_r2_model_document(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    """Fit unchanged Distance champion on exposed H1+H2+H3+C1+C2 only."""
    repo = Path(
        repository_root
    ).resolve()
    (
        _,
        implementation_freeze,
    ) = (
        assert_runtime_checkout_is_frozen_21g_a(
            repo
        )
    )
    c2_closeout = (
        validate_parent_21f_b_result_closeout(
            repo,
            verify_lineage_files=True,
        )
    )

    from src.kxbtcd_candidate_e_h1_evaluation import (
        DISTANCE_CANDIDATE_ID as FIT_DISTANCE_ID,
        fit_candidate_e,
    )
    from src.kxbtcd_candidate_e_predeclaration import (
        candidate_e_predeclaration,
    )

    if (
        FIT_DISTANCE_ID
        != DISTANCE_CANDIDATE_ID
    ):
        _error(
            "Distance candidate ID changed"
        )

    _, prior = (
        _build_prior_observations(
            repo
        )
    )
    c2 = _build_c2_observations(
        repo
    )
    observations = (
        tuple(prior)
        + tuple(c2)
    )

    if (
        len(observations)
        != R2_ROW_COUNT
    ):
        _error(
            f"R2 row count changed: "
            f"{len(observations)} "
            f"!= {R2_ROW_COUNT}"
        )
    if (
        len(
            {
                row.event_ticker
                for row
                in observations
            }
        )
        != R2_EVENT_COUNT
    ):
        _error(
            "R2 event count changed"
        )

    fit = fit_candidate_e(
        observations,
        candidate_id=(
            DISTANCE_CANDIDATE_ID
        ),
        fold=0,
        fit_blocks=(
            "H1",
            "H2",
            "H3",
            "C1",
            "C2",
        ),
        score_block="C3",
    )
    if (
        not fit.converged
        or not math.isfinite(
            fit.beta_distance
        )
        or fit.beta_distance <= 0.0
    ):
        _error(
            "Champion-R2 fit did not "
            "produce a finite positive "
            "distance coefficient"
        )
    if fit.beta_momentum is not None:
        _error(
            "Champion-R2 unexpectedly "
            "fit momentum"
        )

    payload = {
        "schema_version": (
            R2_MODEL_SCHEMA_VERSION
        ),
        "checkpoint_id": "21G-B",
        "family_id": FAMILY_ID,
        "candidate_id": (
            DISTANCE_CANDIDATE_ID
        ),
        "parent_21a_protocol_fingerprint": (
            PARENT_21A_PROTOCOL_FINGERPRINT
        ),
        "parent_h3_result_fingerprint": (
            PARENT_H3_RESULT_FINGERPRINT
        ),
        "parent_c1_result_fingerprint": (
            C1_RESULT_FINGERPRINT
        ),
        "parent_c2_result_fingerprint": (
            C2_RESULT_FINGERPRINT
        ),
        "parent_c2_result_closeout_fingerprint": (
            C2_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r1_fingerprint": (
            CHAMPION_R1_FINGERPRINT
        ),
        "implementation_freeze_fingerprint": (
            implementation_freeze[
                "implementation_freeze_fingerprint"
            ]
        ),
        "fit_scope": {
            "stages": [
                "H1",
                "H2",
                "H3",
                "C1",
                "C2",
            ],
            "event_count": (
                R2_EVENT_COUNT
            ),
            "row_count": (
                R2_ROW_COUNT
            ),
            "all_outcomes_previously_exposed": True,
            "C3_rows_used": 0,
            "C3_outcomes_used": 0,
        },
        "model": {
            "formula": (
                "logit(p)=market_logit_offset "
                "+ beta_distance*d_BTC"
            ),
            "market_logit_offset_clip": (
                "0.001"
            ),
            "feature": (
                "btc_strike_log_distance_bps.v1"
            ),
            "beta_distance": _float_text(
                fit.beta_distance
            ),
            "beta_momentum": None,
            "free_parameter_count": 1,
        },
        "fit_contract": (
            candidate_e_predeclaration()[
                "fit_contract"
            ]
        ),
        "fit_result": {
            "iterations": fit.iterations,
            "converged": True,
            "fit_objective": _float_text(
                fit.fit_objective
            ),
        },
        "lineage": {
            "c2_result_closeout_path": (
                C2_RESULT_CLOSEOUT_PATH.as_posix()
            ),
            "c2_result_closeout_sha256": (
                _sha256_file(
                    repo
                    / C2_RESULT_CLOSEOUT_PATH
                )
            ),
            "c2_outcomes_path": str(
                c2_closeout[
                    "outcomes_path"
                ]
            ),
            "c2_outcomes_sha256": str(
                c2_closeout[
                    "outcomes_sha256"
                ]
            ),
            "implementation_freeze_path": (
                IMPLEMENTATION_FREEZE_PATH.as_posix()
            ),
            "implementation_freeze_sha256": (
                _sha256_file(
                    repo
                    / IMPLEMENTATION_FREEZE_PATH
                )
            ),
        },
        "specification_changed_after_C2": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "C3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }

    document = dict(payload)
    document[
        "champion_r2_fingerprint"
    ] = _canonical_sha256(
        payload
    )
    return document


def validate_r2_model_document(
    document: Mapping[str, Any],
    *,
    implementation_freeze: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = {
        "schema_version": (
            R2_MODEL_SCHEMA_VERSION
        ),
        "checkpoint_id": "21G-B",
        "family_id": FAMILY_ID,
        "candidate_id": (
            DISTANCE_CANDIDATE_ID
        ),
        "parent_21a_protocol_fingerprint": (
            PARENT_21A_PROTOCOL_FINGERPRINT
        ),
        "parent_h3_result_fingerprint": (
            PARENT_H3_RESULT_FINGERPRINT
        ),
        "parent_c1_result_fingerprint": (
            C1_RESULT_FINGERPRINT
        ),
        "parent_c2_result_fingerprint": (
            C2_RESULT_FINGERPRINT
        ),
        "parent_c2_result_closeout_fingerprint": (
            C2_RESULT_CLOSEOUT_FINGERPRINT
        ),
        "parent_champion_r1_fingerprint": (
            CHAMPION_R1_FINGERPRINT
        ),
        "specification_changed_after_C2": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "C3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(
                f"Champion-R2 {key} mismatch"
            )

    scope = document.get(
        "fit_scope"
    )
    if not isinstance(
        scope,
        Mapping,
    ):
        _error(
            "Champion-R2 fit scope missing"
        )
    if (
        scope.get("event_count"),
        scope.get("row_count"),
        scope.get("C3_rows_used"),
        scope.get("C3_outcomes_used"),
    ) != (
        R2_EVENT_COUNT,
        R2_ROW_COUNT,
        0,
        0,
    ):
        _error(
            "Champion-R2 fit scope changed"
        )

    model = document.get(
        "model"
    )
    if not isinstance(
        model,
        Mapping,
    ):
        _error(
            "Champion-R2 model section missing"
        )
    try:
        beta = float(
            model.get(
                "beta_distance"
            )
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise CandidateEC3PreparationError(
            "Champion-R2 beta_distance "
            "is not numeric"
        ) from exc

    if (
        not math.isfinite(beta)
        or beta <= 0.0
        or model.get(
            "beta_momentum"
        )
        is not None
    ):
        _error(
            "Champion-R2 coefficient "
            "state is invalid"
        )

    fit = document.get(
        "fit_result"
    )
    if (
        not isinstance(
            fit,
            Mapping,
        )
        or fit.get("converged")
        is not True
    ):
        _error(
            "Champion-R2 fit result "
            "is not converged"
        )

    if (
        implementation_freeze
        is not None
    ):
        if (
            document.get(
                "implementation_freeze_fingerprint"
            )
            != implementation_freeze.get(
                "implementation_freeze_fingerprint"
            )
        ):
            _error(
                "Champion-R2 implementation-"
                "freeze fingerprint mismatch"
            )

    payload = {
        key: document[key]
        for key in document
        if key
        != "champion_r2_fingerprint"
    }
    if (
        document.get(
            "champion_r2_fingerprint"
        )
        != _canonical_sha256(
            payload
        )
    ):
        _error(
            "Champion-R2 fingerprint mismatch"
        )
    return dict(document)


def load_and_validate_r2_model(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(
        repository_root
    ).resolve()
    freeze = (
        load_and_validate_implementation_freeze(
            repo
        )
    )
    return validate_r2_model_document(
        _read_json(
            repo / R2_MODEL_PATH
        ),
        implementation_freeze=freeze,
    )


def write_or_validate_r2_model(
    repository_root: str | Path = ".",
    path: str | Path = R2_MODEL_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(
        repository_root
    ).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = repo / target

    derived = build_r2_model_document(
        repo
    )
    validate_r2_model_document(
        derived,
        implementation_freeze=(
            load_and_validate_implementation_freeze(
                repo
            )
        ),
    )

    if target.exists():
        existing = _read_json(
            target
        )
        validate_r2_model_document(
            existing,
            implementation_freeze=(
                load_and_validate_implementation_freeze(
                    repo
                )
            ),
        )
        if existing != derived:
            _error(
                "existing Champion-R2 "
                "artifact differs; refusing "
                "overwrite/refit ambiguity"
            )
        return target, existing

    _write_json_atomic(
        target,
        derived,
    )
    return target, derived


def c3_subblock_for_eligible_rank(
    rank_zero_based: int,
) -> str:
    if not (
        0
        <= rank_zero_based
        < C3_ELIGIBLE_EVENT_TARGET
    ):
        _error(
            "C3 eligible rank "
            f"out of range: {rank_zero_based}"
        )
    return (
        f"B{rank_zero_based // C3_EVENTS_PER_SUBBLOCK}"
    )


def strict_tail_remaining_after_end_index(
    end_index_exclusive: int,
) -> int:
    if not (
        C3_STRICT_TAIL_START_INDEX
        <= end_index_exclusive
        <= UNTOUCHED_QUEUE_EVENT_COUNT
    ):
        _error(
            "strict-tail end index "
            f"out of range: {end_index_exclusive}"
        )
    return (
        UNTOUCHED_QUEUE_EVENT_COUNT
        - end_index_exclusive
    )


def validate_candidate_end_index(
    end_index_exclusive: int,
) -> None:
    remaining = (
        strict_tail_remaining_after_end_index(
            end_index_exclusive
        )
    )
    if (
        end_index_exclusive
        > STRICT_TAIL_MAX_END_EXCLUSIVE
    ):
        _error(
            "C3 candidate runway would "
            "violate the 21A hard floor; "
            f"end={end_index_exclusive}, "
            f"max={STRICT_TAIL_MAX_END_EXCLUSIVE}, "
            f"remaining={remaining}"
        )
    if (
        remaining
        < MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
    ):
        _error(
            "strict untouched tail fell "
            "below the 21A hard floor"
        )


__all__ = [
    "C3_CHUNK_ROOT",
    "C3_COLLECTOR_NAME",
    "C3_ELIGIBLE_EVENT_TARGET",
    "C3_EVENTS_PER_SUBBLOCK",
    "C3_FROZEN_ROOT",
    "C3_STRICT_TAIL_START_INDEX",
    "C3_SUBBLOCK_COUNT",
    "C3_VALIDATION_FREEZE_PATH",
    "CandidateEC3PreparationError",
    "IMPLEMENTATION_FREEZE_PATH",
    "MAX_C3_CHUNK_EVENTS",
    "MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_FOR_C3",
    "MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION",
    "R2_MODEL_PATH",
    "R2_EVENT_COUNT",
    "R2_ROW_COUNT",
    "STRICT_TAIL_MAX_END_EXCLUSIVE",
    "UNTOUCHED_QUEUE_EVENT_COUNT",
    "_canonical_sha256",
    "_read_json",
    "_sha256_file",
    "_write_json_atomic",
    "assert_runtime_checkout_is_frozen_21g_a",
    "c3_subblock_for_eligible_rank",
    "load_and_validate_implementation_freeze",
    "load_and_validate_r2_model",
    "strict_tail_remaining_after_end_index",
    "validate_candidate_end_index",
    "validate_parent_21f_b_result_closeout",
    "write_or_validate_implementation_freeze",
    "write_or_validate_r2_model",
]
