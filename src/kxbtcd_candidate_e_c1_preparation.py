"""Checkpoint 21B-A: Champion-R0 and C1 preparation contracts.

This module is deliberately split between two evidence states:

* 21B-A (before closeout): freeze and validate implementation bytes only.
* 21B-B (after the 21B-A closeout): deterministically fit the unchanged
  Candidate-E Distance champion on already-exposed H1+H2+H3 evidence and
  materialize/freeze C1 without opening C1 outcomes.

No function in this module places, cancels, or simulates an order.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

PARENT_21A_RECEIPT_COMMIT = "99b9a5fe0fe1de0c91a6f8786033262cc8b6be7a"
PARENT_21A_PROTOCOL_FINGERPRINT = "88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00"
PARENT_H3_RESULT_FINGERPRINT = "436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54"
H1_RESULT_FINGERPRINT = "3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906"
H2_RESULT_FINGERPRINT = "eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7"

FAMILY_ID = "kxbtcd_independent_btc_offset_successor.v1"
DISTANCE_CANDIDATE_ID = "kxbtcd_btc_distance_offset_logistic.v1"

UNTOUCHED_QUEUE_EVENT_COUNT = 9431
STRICT_TAIL_START_INDEX = 3200
STRICT_TAIL_EVENT_COUNT = 6231
C1_ELIGIBLE_EVENT_TARGET = 500
C1_SUBBLOCK_COUNT = 5
C1_EVENTS_PER_SUBBLOCK = 100
MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION = 4500
MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C1_C2_C3 = (
    STRICT_TAIL_EVENT_COUNT - MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION
)
STRICT_TAIL_MAX_END_EXCLUSIVE = (
    STRICT_TAIL_START_INDEX + MAX_CANDIDATE_IDENTITIES_MATERIALIZABLE_ACROSS_C1_C2_C3
)
MAX_C1_CHUNK_EVENTS = 100

H1_EVENT_COUNT = 1500
H2_EVENT_COUNT = 750
H3_EVENT_COUNT = 750
H1_ROW_COUNT = 36314
H2_ROW_COUNT = 22354
H3_ROW_COUNT = 22409
R0_EVENT_COUNT = H1_EVENT_COUNT + H2_EVENT_COUNT + H3_EVENT_COUNT
R0_ROW_COUNT = H1_ROW_COUNT + H2_ROW_COUNT + H3_ROW_COUNT

IMPLEMENTATION_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_c1_preparation_implementation_freeze.v1"
R0_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_e_champion_r0.v1"
C1_VALIDATION_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_c1_validation_freeze.v1"

PARENT_PROTOCOL_PATH = Path("configs/kxbtcd_post_h3_champion_lifecycle.v1.json")
IMPLEMENTATION_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_c1_preparation_implementation_freeze.json")
R0_MODEL_PATH = Path("configs/kxbtcd_candidate_e_champion_r0.json")
C1_VALIDATION_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_c1_validation_freeze.json")
LAST_CLOSEOUT_PATH = Path("docs/LAST_CHECKPOINT_CLOSEOUT.json")

C1_CHUNK_ROOT = Path("data/derived/kxbtcd_candidate_e_c1_preoutcome/chunks")
C1_FROZEN_ROOT = Path("data/derived/kxbtcd_candidate_e_c1_preoutcome/frozen")
C1_COLLECTOR_NAME = "collect_kxbtcd_candidate_e_c1_materialization_chunk"

NEW_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_c1_preparation.py",
    "prepare_kxbtcd_candidate_e_c1.py",
    "collect_kxbtcd_candidate_e_c1_materialization_chunk.py",
    "freeze_kxbtcd_candidate_e_c1_preoutcome.py",
)
DEPENDENCY_IMPLEMENTATION_FILES = (
    "collect_kxbtcd_candidate_e_coinbase_primary_materialization_chunk.py",
    "collect_kxbtcd_candidate_e_historical_materialization_chunk.py",
    "src/kxbtcd_candidate_e_h1_evaluation.py",
    "src/kxbtcd_candidate_e_h3_preparation.py",
    "src/kxbtcd_candidate_e_h3_result_closeout.py",
    "src/kxbtcd_candidate_e_coinbase_primary_materialization.py",
    "src/kxbtcd_candidate_e_historical_materialization.py",
)
IMPLEMENTATION_FILES = NEW_IMPLEMENTATION_FILES + DEPENDENCY_IMPLEMENTATION_FILES
REQUIRED_21B_A_CLOSEOUT_PATHS = frozenset(
    {
        *NEW_IMPLEMENTATION_FILES,
        IMPLEMENTATION_FREEZE_PATH.as_posix(),
        "freeze_kxbtcd_candidate_e_c1_preparation_implementation.py",
        "docs/KXBTCD_CANDIDATE_E_C1_PREPARATION_IMPLEMENTATION_FREEZE.md",
        "scripts/apply_checkpoint21b_a_docs.py",
        "tests/test_kxbtcd_candidate_e_c1_preparation.py",
    }
)


class CandidateEC1PreparationError(RuntimeError):
    """Raised when a Checkpoint-21B C1-preparation invariant fails."""


def _error(message: str) -> None:
    raise CandidateEC1PreparationError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEC1PreparationError(f"could not read JSON {path}: {exc}") from exc
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


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        _error(f"git {' '.join(args)} failed: {detail or completed.returncode}")
    return completed.stdout.strip()


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        _error("attempted to serialize non-finite model value")
    return format(value, ".17g")


def validate_parent_21a_protocol(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    path = repo / PARENT_PROTOCOL_PATH
    document = _read_json(path)
    fingerprint = _canonical_sha256(document)
    if fingerprint != PARENT_21A_PROTOCOL_FINGERPRINT:
        _error(
            "Checkpoint-21A protocol fingerprint changed: "
            f"{fingerprint} != {PARENT_21A_PROTOCOL_FINGERPRINT}"
        )
    expected = {
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "initial_exposed_events": R0_EVENT_COUNT,
        "strict_untouched_tail_events": STRICT_TAIL_EVENT_COUNT,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"Checkpoint-21A protocol {key} mismatch")
    confirmation = document.get("confirmation")
    if not isinstance(confirmation, Mapping):
        _error("Checkpoint-21A confirmation contract missing")
    expected_confirmation = {
        "eligible_events_per_block": C1_ELIGIBLE_EVENT_TARGET,
        "eligible_events_per_subblock": C1_EVENTS_PER_SUBBLOCK,
        "subblocks_per_block": C1_SUBBLOCK_COUNT,
        "minimum_strict_untouched_tail_after_all_confirmation": MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION,
        "selection": "deterministic chronological next-eligible from frozen tail under unchanged Candidate-E historical eligibility rules",
        "materialize_sequentially": True,
    }
    for key, value in expected_confirmation.items():
        if confirmation.get(key) != value:
            _error(f"Checkpoint-21A confirmation {key} mismatch")
    return document


def assert_21a_parent_baseline_for_implementation_freeze(
    repository_root: str | Path = ".",
) -> str:
    """Require exact 21A receipt before generating the 21B-A freeze.

    Extracted 21B-A files may be untracked, so this check intentionally binds
    HEAD/origin rather than rejecting all untracked files.
    """
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("Checkpoint 21B-A requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != PARENT_21A_RECEIPT_COMMIT or remote != PARENT_21A_RECEIPT_COMMIT:
        _error(
            "Checkpoint-21B-A parent mismatch; expected HEAD == origin/main == "
            f"{PARENT_21A_RECEIPT_COMMIT}, got HEAD={head}, origin/main={remote}"
        )
    validate_parent_21a_protocol(repo)
    return head


def implementation_sha256s(repository_root: str | Path = ".") -> dict[str, str]:
    repo = Path(repository_root).resolve()
    result: dict[str, str] = {}
    for relative in IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"missing Checkpoint-21B-A implementation file: {relative}")
        result[relative] = _sha256_file(path)
    return result


def build_implementation_freeze_document(
    *,
    repository_root: str | Path = ".",
    source_baseline_commit: str,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    validate_parent_21a_protocol(repo)
    payload = {
        "schema_version": IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21B-A",
        "parent_21a_receipt_commit": PARENT_21A_RECEIPT_COMMIT,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "source_baseline_commit": source_baseline_commit,
        "implementation_sha256s": implementation_sha256s(repo),
        "r0_contract": {
            "fit_events": R0_EVENT_COUNT,
            "fit_rows": R0_ROW_COUNT,
            "fit_stages": ["H1", "H2", "H3"],
            "same_frozen_distance_specification": True,
            "candidate_or_feature_selection": False,
        },
        "c1_contract": {
            "strict_tail_start_index": STRICT_TAIL_START_INDEX,
            "strict_tail_events_at_21a": STRICT_TAIL_EVENT_COUNT,
            "eligible_event_target": C1_ELIGIBLE_EVENT_TARGET,
            "subblocks": C1_SUBBLOCK_COUNT,
            "events_per_subblock": C1_EVENTS_PER_SUBBLOCK,
            "maximum_chunk_events": MAX_C1_CHUNK_EVENTS,
            "maximum_end_index_exclusive_across_C1_C2_C3": STRICT_TAIL_MAX_END_EXCLUSIVE,
            "minimum_strict_untouched_tail_after_all_confirmation": MIN_STRICT_UNTOUCHED_TAIL_AFTER_ALL_CONFIRMATION,
            "selection": "first 500 eligible events encountered sequentially from queue index 3200",
            "stop_materialization_immediately_at_500th_eligible_event": True,
        },
        "C1_outcomes_opened": False,
        "C2_C3_materialization_authorized": False,
        "network_requests_during_implementation_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["implementation_freeze_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_implementation_freeze_document(
    document: Mapping[str, Any],
    *,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    expected = {
        "schema_version": IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21B-A",
        "parent_21a_receipt_commit": PARENT_21A_RECEIPT_COMMIT,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "C1_outcomes_opened": False,
        "C2_C3_materialization_authorized": False,
        "network_requests_during_implementation_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"C1 implementation freeze {key} mismatch")
    hashes = document.get("implementation_sha256s")
    if not isinstance(hashes, Mapping) or set(hashes) != set(IMPLEMENTATION_FILES):
        _error("C1 implementation freeze file set changed")
    for relative, digest in hashes.items():
        if not isinstance(digest, str) or len(digest) != 64:
            _error(f"invalid implementation digest for {relative}")
    if repository_root is not None:
        if dict(hashes) != implementation_sha256s(repository_root):
            _error("Checkpoint-21B implementation bytes differ from frozen hashes")
    payload = {key: document[key] for key in document if key != "implementation_freeze_fingerprint"}
    if document.get("implementation_freeze_fingerprint") != _canonical_sha256(payload):
        _error("C1 implementation freeze fingerprint mismatch")
    return dict(document)


def write_or_validate_implementation_freeze(
    repository_root: str | Path = ".",
    path: str | Path = IMPLEMENTATION_FREEZE_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    head = assert_21a_parent_baseline_for_implementation_freeze(repo)
    target = Path(path)
    if not target.is_absolute():
        target = repo / target
    derived = build_implementation_freeze_document(
        repository_root=repo,
        source_baseline_commit=head,
    )
    validate_implementation_freeze_document(derived, repository_root=repo)
    if target.exists():
        existing = _read_json(target)
        validate_implementation_freeze_document(existing, repository_root=repo)
        if existing != derived:
            _error("existing C1 implementation freeze differs; refusing overwrite")
        return target, existing
    _write_json_atomic(target, derived)
    return target, derived


def load_and_validate_implementation_freeze(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    document = _read_json(repo / IMPLEMENTATION_FREEZE_PATH)
    return validate_implementation_freeze_document(document, repository_root=repo)


def assert_runtime_checkout_is_frozen_21b_a(
    repository_root: str | Path = ".",
) -> tuple[str, dict[str, Any]]:
    """Require clean synchronized main carrying the frozen 21B-A implementation.

    The latest receipt may later be the separate Champion-R0 closeout, so this
    check binds the tracked implementation bytes rather than requiring 21B-A to
    remain the most recent checkpoint forever.
    """
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("C1 preparation runtime requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != remote:
        _error(f"C1 preparation requires HEAD == origin/main; HEAD={head}, origin={remote}")
    if _git(repo, "status", "--porcelain"):
        _error("C1 preparation requires a clean worktree")
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PARENT_21A_RECEIPT_COMMIT, head],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        _error("current main is not a descendant of the accepted Checkpoint-21A receipt")
    freeze = load_and_validate_implementation_freeze(repo)
    if freeze.get("source_baseline_commit") != PARENT_21A_RECEIPT_COMMIT:
        _error("21B-A implementation freeze is not bound to the accepted 21A receipt")
    for relative in (*IMPLEMENTATION_FILES, IMPLEMENTATION_FREEZE_PATH.as_posix()):
        completed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", relative],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            _error(f"frozen 21B-A path is not tracked on synchronized main: {relative}")
    return head, freeze


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return tuple(reader.fieldnames or ()), tuple(dict(row) for row in reader)
    except OSError as exc:
        raise CandidateEC1PreparationError(f"could not read CSV {path}: {exc}") from exc


def build_r0_model_document(repository_root: str | Path = ".") -> dict[str, Any]:
    """Fit the unchanged one-parameter Distance champion on exposed H1+H2+H3.

    This function is network-free. It validates the permanent H1/H2/H3 result
    artifacts before using their already-exposed labels.
    """
    repo = Path(repository_root).resolve()
    _, implementation_freeze = assert_runtime_checkout_is_frozen_21b_a(repo)

    from src.kxbtcd_candidate_e_h1_evaluation import (
        CandidateEObservation,
        DISTANCE_CANDIDATE_ID as FIT_DISTANCE_ID,
        fit_candidate_e,
        load_and_validate_frozen_universe,
    )
    from src.kxbtcd_candidate_e_h3_preparation import (
        H1_OUTCOMES_PATH,
        H2_OUTCOMES_PATH,
        _build_h1_h2_observations,
    )
    from src.kxbtcd_candidate_e_predeclaration import candidate_e_predeclaration
    from src.kxbtcd_candidate_e_h3_result_closeout import (
        OUTCOMES_PATH as H3_OUTCOMES_PATH,
        load_and_validate_result as load_and_validate_h3_result,
    )

    if FIT_DISTANCE_ID != DISTANCE_CANDIDATE_ID:
        _error("Distance candidate ID changed")
    universe = load_and_validate_frozen_universe(repo)
    h1_h2 = _build_h1_h2_observations(repo=repo, universe=universe)
    if len(h1_h2) != H1_ROW_COUNT + H2_ROW_COUNT:
        _error("H1+H2 observation row count changed")

    load_and_validate_h3_result(repo)
    fields, h3_outcomes = _read_csv(repo / H3_OUTCOMES_PATH)
    required_fields = {"event_ticker", "market_ticker", "outcome", "stage"}
    if not required_fields.issubset(set(fields)):
        _error("H3 outcome file no longer contains required fields")
    labels: dict[str, int] = {}
    for index, row in enumerate(h3_outcomes):
        if row.get("stage") != "H3":
            _error(f"H3 outcome row {index} stage changed")
        market = str(row.get("market_ticker", ""))
        if not market or market in labels:
            _error(f"H3 outcome row {index} duplicate/blank market")
        try:
            outcome = int(row["outcome"])
        except (TypeError, ValueError) as exc:
            raise CandidateEC1PreparationError("H3 outcome is not binary integer text") from exc
        if outcome not in {0, 1}:
            _error("H3 outcome is not binary")
        labels[market] = outcome

    h3_observations: list[CandidateEObservation] = []
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
            _error(f"duplicate H3 R0 state identity {state_id}")
        state_ids.add(state_id)
        h3_events.add(event)
        try:
            q_market = float(row["q_market"])
            d_btc = float(row["d_BTC"])
            r_5m = float(row["r_5m"])
        except (TypeError, ValueError) as exc:
            raise CandidateEC1PreparationError(
                f"H3 preoutcome numeric parse failed at row {index}"
            ) from exc
        if not all(math.isfinite(v) for v in (q_market, d_btc, r_5m)):
            _error(f"H3 preoutcome row {index} contains non-finite model input")
        h3_observations.append(
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
    if len(h3_observations) != H3_ROW_COUNT or len(h3_events) != H3_EVENT_COUNT:
        _error(
            "H3 R0 observation scope changed: "
            f"events={len(h3_events)}, rows={len(h3_observations)}"
        )

    observations = tuple(h1_h2) + tuple(h3_observations)
    if len(observations) != R0_ROW_COUNT:
        _error(f"R0 row count changed: {len(observations)} != {R0_ROW_COUNT}")
    if len({row.event_ticker for row in observations}) != R0_EVENT_COUNT:
        _error("R0 event count changed")

    fit = fit_candidate_e(
        observations,
        candidate_id=DISTANCE_CANDIDATE_ID,
        fold=0,
        fit_blocks=("H1", "H2", "H3"),
        score_block="C1",
    )
    if not fit.converged or not math.isfinite(fit.beta_distance) or fit.beta_distance <= 0.0:
        _error("Champion-R0 fit did not produce a finite positive distance coefficient")
    if fit.beta_momentum is not None:
        _error("Champion-R0 unexpectedly fit momentum")

    payload = {
        "schema_version": R0_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "21B-B",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "parent_h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "implementation_freeze_fingerprint": implementation_freeze["implementation_freeze_fingerprint"],
        "fit_scope": {
            "stages": ["H1", "H2", "H3"],
            "event_count": R0_EVENT_COUNT,
            "row_count": R0_ROW_COUNT,
            "all_outcomes_previously_exposed": True,
            "C1_rows_used": 0,
            "C1_outcomes_used": 0,
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
            "h1_outcomes_path": H1_OUTCOMES_PATH.as_posix(),
            "h1_outcomes_sha256": _sha256_file(repo / H1_OUTCOMES_PATH),
            "h2_outcomes_path": H2_OUTCOMES_PATH.as_posix(),
            "h2_outcomes_sha256": _sha256_file(repo / H2_OUTCOMES_PATH),
            "h3_outcomes_path": H3_OUTCOMES_PATH.as_posix(),
            "h3_outcomes_sha256": _sha256_file(repo / H3_OUTCOMES_PATH),
            "implementation_freeze_path": IMPLEMENTATION_FREEZE_PATH.as_posix(),
            "implementation_freeze_sha256": _sha256_file(repo / IMPLEMENTATION_FREEZE_PATH),
        },
        "specification_changed_after_H3": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "C1_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["champion_r0_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_r0_model_document(
    document: Mapping[str, Any],
    *,
    implementation_freeze: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = {
        "schema_version": R0_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "21B-B",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "parent_h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "specification_changed_after_H3": False,
        "feature_selection_performed": False,
        "hyperparameter_search_performed": False,
        "C1_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"Champion-R0 {key} mismatch")
    scope = document.get("fit_scope")
    if not isinstance(scope, Mapping):
        _error("Champion-R0 fit scope missing")
    if scope.get("event_count") != R0_EVENT_COUNT or scope.get("row_count") != R0_ROW_COUNT:
        _error("Champion-R0 fit scope counts changed")
    if scope.get("C1_rows_used") != 0 or scope.get("C1_outcomes_used") != 0:
        _error("Champion-R0 fit scope crosses the C1 firewall")
    model = document.get("model")
    if not isinstance(model, Mapping):
        _error("Champion-R0 model section missing")
    try:
        beta = float(model.get("beta_distance"))
    except (TypeError, ValueError) as exc:
        raise CandidateEC1PreparationError("Champion-R0 beta_distance is not numeric") from exc
    if not math.isfinite(beta) or beta <= 0.0 or model.get("beta_momentum") is not None:
        _error("Champion-R0 coefficient state is invalid")
    fit = document.get("fit_result")
    if not isinstance(fit, Mapping) or fit.get("converged") is not True:
        _error("Champion-R0 fit result is not converged")
    if implementation_freeze is not None and document.get("implementation_freeze_fingerprint") != implementation_freeze.get("implementation_freeze_fingerprint"):
        _error("Champion-R0 implementation-freeze fingerprint mismatch")
    payload = {key: document[key] for key in document if key != "champion_r0_fingerprint"}
    if document.get("champion_r0_fingerprint") != _canonical_sha256(payload):
        _error("Champion-R0 fingerprint mismatch")
    return dict(document)


def load_and_validate_r0_model(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    freeze = load_and_validate_implementation_freeze(repo)
    return validate_r0_model_document(
        _read_json(repo / R0_MODEL_PATH),
        implementation_freeze=freeze,
    )


def write_or_validate_r0_model(
    repository_root: str | Path = ".",
    path: str | Path = R0_MODEL_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = repo / target
    derived = build_r0_model_document(repo)
    validate_r0_model_document(derived, implementation_freeze=load_and_validate_implementation_freeze(repo))
    if target.exists():
        existing = _read_json(target)
        validate_r0_model_document(existing, implementation_freeze=load_and_validate_implementation_freeze(repo))
        if existing != derived:
            _error("existing Champion-R0 artifact differs; refusing overwrite/refit ambiguity")
        return target, existing
    _write_json_atomic(target, derived)
    return target, derived


def c1_subblock_for_eligible_rank(rank_zero_based: int) -> str:
    if not 0 <= rank_zero_based < C1_ELIGIBLE_EVENT_TARGET:
        _error(f"C1 eligible rank out of range: {rank_zero_based}")
    return f"B{rank_zero_based // C1_EVENTS_PER_SUBBLOCK}"


def strict_tail_remaining_after_end_index(end_index_exclusive: int) -> int:
    if not STRICT_TAIL_START_INDEX <= end_index_exclusive <= UNTOUCHED_QUEUE_EVENT_COUNT:
        _error(f"strict-tail end index out of range: {end_index_exclusive}")
    return UNTOUCHED_QUEUE_EVENT_COUNT - end_index_exclusive


def validate_candidate_end_index(end_index_exclusive: int) -> None:
    remaining = strict_tail_remaining_after_end_index(end_index_exclusive)
    if end_index_exclusive > STRICT_TAIL_MAX_END_EXCLUSIVE:
        _error(
            "C1/C2/C3 candidate runway would violate the 21A hard floor; "
            f"end={end_index_exclusive}, max={STRICT_TAIL_MAX_END_EXCLUSIVE}, remaining={remaining}"
        )
