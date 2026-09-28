"""Checkpoint-20H/20I Candidate-E H3 locked-test implementation.

Checkpoint 20H is outcome-blind: it freezes the exact implementation bytes that
may later open H3 labels.

Checkpoint 20I is the one-time H3 exposure/evaluation:
* require a clean synchronized repository whose latest safe closeout contains
  the frozen 20H implementation;
* permanently mark the full H3 set exposed before the first outcome request;
* request only the exact 20G H3 allow-list;
* hard-deny every H1/H2 event and market identity;
* preserve raw responses before semantic use;
* apply the already-frozen H1+H2 Distance coefficient without fitting;
* score raw Kalshi midpoint vs the fixed Distance model on all H3 rows;
* apply the exact frozen H3 gate.

There is no order-placement, cancellation, transfer, demo, paper, or real-money
execution path in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from statistics import median
from typing import Any, Callable, Mapping, Protocol, Sequence

from .kxbtcd_candidate_e_h1_evaluation import (
    FrozenCandidateEUniverse,
    load_and_validate_frozen_universe,
)
from .kxbtcd_candidate_e_h3_preparation import (
    DEFAULT_FINAL_MODEL_PATH,
    DEFAULT_H3_FREEZE_PATH,
    DISTANCE_CANDIDATE_ID,
    H3_BLOCKS,
    H3_EVENTS_PER_BLOCK,
    H3_EVENT_COUNT,
    H3_ROW_COUNT,
    validate_checkpoint20g_preparation,
    validate_final_model_document,
    validate_h3_validation_freeze_document,
)
from .kxbtcd_candidate_e_predeclaration import FAMILY_ID, market_logit_offset

CP20H_PARENT_RECEIPT_COMMIT = "932d275cba192f1f8cad1259bb7a2642dd0f6e3a"
FINAL_H1_H2_MODEL_FINGERPRINT = (
    "1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842"
)
H3_VALIDATION_FINGERPRINT = (
    "a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197"
)
H1_RESULT_FINGERPRINT = (
    "3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906"
)
H2_RESULT_FINGERPRINT = (
    "eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7"
)
COHORT_MAP_FINGERPRINT = (
    "09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa"
)
ROW_UNIVERSE_FINGERPRINT = (
    "e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5"
)

H3_MARKET_COUNT = 3750

CP20I_COLLECTOR_NAME = "collect_kxbtcd_candidate_e_h3"
H3_IMPLEMENTATION_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_implementation_freeze.v1"
H3_OUTCOME_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_outcome.v1"
H3_ATTEMPT_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_attempt.v1"
H3_SUMMARY_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_evaluation_summary.v1"
H3_BLOCK_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_block_score.v1"
H3_PREDICTION_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_prediction.v1"
H3_EVENT_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_event_score.v1"

DEFAULT_H3_IMPLEMENTATION_FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_e_h3_implementation_freeze.json"
)
DEFAULT_H3_ATTEMPT_PATH = Path(
    "data/analysis/kxbtcd_candidate_e_h3_evaluation/h3_attempt.json"
)
DERIVED_ROOT = Path("data/derived/kxbtcd_candidate_e_h3_evaluation")
MANIFEST_ROOT = Path("data/manifests")

H3_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_h3_evaluation.py",
    "collect_kxbtcd_candidate_e_h3.py",
)

REQUIRED_20H_CLOSEOUT_PATHS = frozenset(
    {
        "configs/kxbtcd_candidate_e_h3_implementation_freeze.json",
        "collect_kxbtcd_candidate_e_h3.py",
        "freeze_kxbtcd_candidate_e_h3_implementation.py",
        "src/kxbtcd_candidate_e_h3_evaluation.py",
        "tests/test_kxbtcd_candidate_e_h3_evaluation.py",
        "validate_kxbtcd_candidate_e_h3_implementation_freeze.py",
    }
)

H3_OUTCOME_FIELDS = (
    "schema_version",
    "family_id",
    "h3_validation_fingerprint",
    "h3_implementation_fingerprint",
    "final_h1_h2_model_fingerprint",
    "cohort_map_fingerprint",
    "row_universe_fingerprint",
    "stage",
    "event_ticker",
    "market_ticker",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "market_status",
    "result_text",
    "outcome",
)

H3_BLOCK_SCORE_FIELDS = (
    "schema_version",
    "family_id",
    "candidate_id",
    "h3_validation_fingerprint",
    "final_h1_h2_model_fingerprint",
    "block_id",
    "event_count",
    "raw_log_loss",
    "candidate_log_loss",
    "raw_minus_candidate_log_loss",
    "raw_brier",
    "candidate_brier",
    "raw_minus_candidate_brier",
    "candidate_beats_raw_log_loss",
)

H3_PREDICTION_FIELDS = (
    "schema_version",
    "family_id",
    "candidate_id",
    "h3_validation_fingerprint",
    "final_h1_h2_model_fingerprint",
    "block_id",
    "state_id",
    "event_ticker",
    "market_ticker",
    "structural_role",
    "ttc_target_minutes",
    "outcome",
    "q_market",
    "d_BTC",
    "beta_distance",
    "candidate_probability",
)

H3_EVENT_SCORE_FIELDS = (
    "schema_version",
    "family_id",
    "candidate_id",
    "h3_validation_fingerprint",
    "final_h1_h2_model_fingerprint",
    "block_id",
    "event_ticker",
    "row_count",
    "raw_log_loss",
    "candidate_log_loss",
    "raw_minus_candidate_log_loss",
    "raw_brier",
    "candidate_brier",
    "raw_minus_candidate_brier",
)


class CandidateEH3EvaluationError(RuntimeError):
    """Raised when an H3 implementation/evaluation invariant fails."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference


class RawFirstJsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class H3Preflight:
    repository_root: Path
    git_head: str
    implementation_freeze: dict[str, Any]
    validation_freeze: dict[str, Any]
    final_model: dict[str, Any]
    universe: FrozenCandidateEUniverse
    attempt_path: Path


@dataclass(frozen=True)
class H3Evaluation:
    summary: dict[str, Any]
    block_rows: tuple[dict[str, str], ...]
    prediction_rows: tuple[dict[str, str], ...]
    event_score_rows: tuple[dict[str, str], ...]


def _error(message: str) -> None:
    raise CandidateEH3EvaluationError(message)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEH3EvaluationError(f"could not read JSON {path}: {exc}") from exc
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
            return tuple(reader.fieldnames or ()), tuple(dict(row) for row in reader)
    except OSError as exc:
        raise CandidateEH3EvaluationError(f"could not read CSV {path}: {exc}") from exc


def _write_csv(
    path: Path,
    fields: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for index, source in enumerate(rows):
            row = dict(source)
            missing = set(fields) - set(row)
            extra = set(row) - set(fields)
            if missing or extra:
                _error(
                    f"output row {index} schema mismatch for {path.name}; "
                    f"missing={sorted(missing)}, extra={sorted(extra)}"
                )
            writer.writerow({field: row[field] for field in fields})


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
        _error(f"git {' '.join(args)} failed: {detail or completed.returncode}")
    return completed.stdout.strip()


def _implementation_sha256s(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in H3_IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"H3 implementation file missing: {relative}")
        result[relative] = _sha256_file(path)
    return result


def assert_20g_parent_baseline_for_freeze(
    repository_root: str | Path = ".",
) -> str:
    """Require exact cleanly closed 20G parent before generating 20H freeze.

    New 20H files may be untracked. Existing tracked files must not already be
    modified or staged.
    """
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("Checkpoint-20H implementation freeze requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != CP20H_PARENT_RECEIPT_COMMIT or remote != CP20H_PARENT_RECEIPT_COMMIT:
        _error(
            "Checkpoint-20H parent mismatch; expected HEAD == origin/main == "
            f"{CP20H_PARENT_RECEIPT_COMMIT}, got HEAD={head}, origin/main={remote}"
        )
    if _git(repo, "diff", "--name-only"):
        _error("tracked unstaged changes existed before Checkpoint-20H freeze")
    if _git(repo, "diff", "--cached", "--name-only"):
        _error("staged changes existed before Checkpoint-20H freeze")
    return head


def _parent_documents(
    repo: Path,
) -> tuple[dict[str, Any], dict[str, Any], FrozenCandidateEUniverse]:
    final_model, validation_freeze = validate_checkpoint20g_preparation(repo)
    if final_model.get("final_model_fingerprint") != FINAL_H1_H2_MODEL_FINGERPRINT:
        _error("final H1+H2 model fingerprint changed")
    if validation_freeze.get("h3_validation_fingerprint") != H3_VALIDATION_FINGERPRINT:
        _error("H3 validation fingerprint changed")
    identity = validation_freeze.get("H3_identity")
    if not isinstance(identity, Mapping):
        _error("H3 identity missing")
    if (
        identity.get("event_count"),
        identity.get("row_count"),
        identity.get("market_count"),
    ) != (H3_EVENT_COUNT, H3_ROW_COUNT, H3_MARKET_COUNT):
        _error("H3 frozen identity counts changed")
    universe = load_and_validate_frozen_universe(repo)
    return final_model, validation_freeze, universe


def build_h3_implementation_freeze_document(
    *,
    repo: Path,
    source_baseline_commit: str,
) -> dict[str, Any]:
    final_model, validation_freeze, universe = _parent_documents(repo)
    h1_h2_events, h1_h2_markets = _h1_h2_identity_sets(universe)
    payload = {
        "schema_version": H3_IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20H",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
        "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
        "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
        "H3_identity": dict(validation_freeze["H3_identity"]),
        "H1_H2_hard_deny_identity": {
            "event_count": len(h1_h2_events),
            "market_count": len(h1_h2_markets),
            "event_identity_fingerprint": _canonical_sha256(sorted(h1_h2_events)),
            "market_identity_fingerprint": _canonical_sha256(sorted(h1_h2_markets)),
        },
        "outcome_source": {
            "endpoint_template": "/historical/markets/{market_ticker}",
            "required_market_status": "finalized",
            "accepted_results": ["yes", "no"],
            "raw_first_persistence_required": True,
            "authentication_required": False,
        },
        "evaluation_contract": dict(validation_freeze["validation_contract"]),
        "exposure_policy": {
            "permanently_expose_full_H3_before_first_request": True,
            "fresh_second_H3_attempt_allowed": False,
            "resume_only_after_interruption": True,
            "future_untouched_claim_on_H3_allowed": False,
            "H1_H2_event_and_market_identities_hard_denied": True,
        },
        "implementation_sha256s": _implementation_sha256s(repo),
        "source_baseline_commit": source_baseline_commit,
        "procedure_derivation_used_H3_outcomes": False,
        "H3_outcomes_opened_at_freeze": 0,
        "model_fit_performed_at_freeze": False,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["h3_implementation_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_h3_implementation_freeze_document(
    document: Mapping[str, Any],
    *,
    repo: Path,
    verify_parent: bool = True,
    verify_implementation_hashes: bool = True,
) -> dict[str, Any]:
    expected = {
        "schema_version": H3_IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20H",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
        "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
        "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
        "source_baseline_commit": CP20H_PARENT_RECEIPT_COMMIT,
        "procedure_derivation_used_H3_outcomes": False,
        "H3_outcomes_opened_at_freeze": 0,
        "model_fit_performed_at_freeze": False,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"H3 implementation freeze {key} mismatch")

    identity = document.get("H3_identity")
    if not isinstance(identity, Mapping):
        _error("H3 implementation identity missing")
    if (
        identity.get("event_count"),
        identity.get("row_count"),
        identity.get("market_count"),
    ) != (H3_EVENT_COUNT, H3_ROW_COUNT, H3_MARKET_COUNT):
        _error("H3 implementation identity counts changed")
    if identity.get("blocks") != {
        block: H3_EVENTS_PER_BLOCK for block in H3_BLOCKS
    }:
        _error("H3 block sizes changed in implementation freeze")

    exposure = document.get("exposure_policy")
    if not isinstance(exposure, Mapping):
        _error("H3 exposure policy missing")
    if exposure.get("permanently_expose_full_H3_before_first_request") is not True:
        _error("H3 conservative exposure rule changed")
    if exposure.get("fresh_second_H3_attempt_allowed") is not False:
        _error("fresh second H3 attempt became allowed")
    if exposure.get("resume_only_after_interruption") is not True:
        _error("H3 resume-only policy changed")
    if exposure.get("H1_H2_event_and_market_identities_hard_denied") is not True:
        _error("H1/H2 hard deny was disabled")

    evaluation = document.get("evaluation_contract")
    if not isinstance(evaluation, Mapping):
        _error("H3 evaluation contract missing")
    for key in (
        "model_parameters_fitted_on_H3",
        "candidate_selection_on_H3_allowed",
        "feature_change_on_H3_allowed",
        "hyperparameter_search_on_H3_allowed",
    ):
        if evaluation.get(key) is not False:
            _error(f"H3 evaluation contract {key} changed")

    if verify_implementation_hashes:
        if document.get("implementation_sha256s") != _implementation_sha256s(repo):
            _error("H3 implementation bytes differ from frozen hashes")

    if verify_parent:
        final_model, validation_freeze, universe = _parent_documents(repo)
        if final_model["final_model_fingerprint"] != document["final_h1_h2_model_fingerprint"]:
            _error("H3 implementation final-model lineage mismatch")
        if validation_freeze["h3_validation_fingerprint"] != document["h3_validation_fingerprint"]:
            _error("H3 implementation validation lineage mismatch")
        h1_h2_events, h1_h2_markets = _h1_h2_identity_sets(universe)
        deny = document.get("H1_H2_hard_deny_identity")
        if not isinstance(deny, Mapping):
            _error("H1/H2 hard-deny identity missing")
        if deny.get("event_count") != len(h1_h2_events):
            _error("H1/H2 hard-deny event count mismatch")
        if deny.get("market_count") != len(h1_h2_markets):
            _error("H1/H2 hard-deny market count mismatch")

    payload = {
        key: document[key]
        for key in document
        if key != "h3_implementation_fingerprint"
    }
    if document.get("h3_implementation_fingerprint") != _canonical_sha256(payload):
        _error("H3 implementation fingerprint mismatch")
    return dict(document)


def write_or_validate_h3_implementation_freeze(
    path: str | Path = DEFAULT_H3_IMPLEMENTATION_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    baseline = assert_20g_parent_baseline_for_freeze(repo)
    target = Path(path)
    if not target.is_absolute():
        target = repo / target
    document = build_h3_implementation_freeze_document(
        repo=repo,
        source_baseline_commit=baseline,
    )
    validate_h3_implementation_freeze_document(
        document,
        repo=repo,
        verify_parent=True,
        verify_implementation_hashes=True,
    )
    if target.exists():
        existing = _read_json(target)
        validate_h3_implementation_freeze_document(
            existing,
            repo=repo,
            verify_parent=True,
            verify_implementation_hashes=True,
        )
        if existing != document:
            _error("existing H3 implementation freeze differs; refusing overwrite")
        return target, existing
    _write_json_atomic(target, document)
    return target, document


def validate_h3_implementation_freeze(
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    document = _read_json(repo / DEFAULT_H3_IMPLEMENTATION_FREEZE_PATH)
    return validate_h3_implementation_freeze_document(
        document,
        repo=repo,
        verify_parent=True,
        verify_implementation_hashes=True,
    )


def _h1_h2_identity_sets(
    universe: FrozenCandidateEUniverse,
) -> tuple[frozenset[str], frozenset[str]]:
    events = frozenset(
        str(row["event_ticker"])
        for row in universe.cohort_rows
        if row["stage"] in {"H1", "H2"}
    )
    markets = frozenset(
        str(row["market_ticker"])
        for row in universe.preoutcome_rows
        if row["stage"] in {"H1", "H2"}
    )
    if len(events) != 2250:
        _error(f"H1/H2 event hard-deny count changed: {len(events)}")
    if not markets:
        _error("H1/H2 market hard-deny set is empty")
    return events, markets


def _h3_plan(validation_freeze: Mapping[str, Any]) -> dict[str, str]:
    raw = validation_freeze.get("h3_request_plan")
    if not isinstance(raw, list) or len(raw) != H3_MARKET_COUNT:
        _error("H3 request plan changed")
    plan: dict[str, str] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {"event_ticker", "market_ticker"}:
            _error(f"H3 request plan entry {index} schema changed")
        event = str(item["event_ticker"])
        market = str(item["market_ticker"])
        if market in plan:
            _error(f"duplicate H3 planned market {market}")
        plan[market] = event
    return plan


def assert_not_h1_h2_identity(
    *,
    h1_h2_events: frozenset[str],
    h1_h2_markets: frozenset[str],
    event_ticker: str,
    market_ticker: str,
) -> None:
    if event_ticker in h1_h2_events:
        _error(f"H1/H2 event identity prohibited in H3 path: {event_ticker}")
    if market_ticker in h1_h2_markets:
        _error(f"H1/H2 market identity prohibited in H3 path: {market_ticker}")


def assert_clean_synchronized_repository(
    repository_root: str | Path = ".",
) -> str:
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("H3 exposure requires branch main")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        _error(
            "H3 exposure requires a completely clean worktree/index; "
            f"first dirty line: {status.splitlines()[0]}"
        )
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != remote:
        _error(
            "H3 exposure requires HEAD == origin/main after fresh fetch; "
            f"HEAD={head}, origin/main={remote}"
        )

    receipt = _read_json(repo / "docs/LAST_CHECKPOINT_CLOSEOUT.json")
    if receipt.get("baseline_commit") != CP20H_PARENT_RECEIPT_COMMIT:
        _error("latest closeout is not a direct child of the frozen Checkpoint-20G receipt")
    committed = set(receipt.get("committed_paths") or ())
    missing = REQUIRED_20H_CLOSEOUT_PATHS - committed
    if missing:
        _error(
            "latest closeout does not contain required Checkpoint-20H paths: "
            f"{sorted(missing)}"
        )
    safety = receipt.get("safety")
    if not isinstance(safety, Mapping):
        _error("latest closeout safety record missing")
    if (
        safety.get("staged_diff_check") != "PASS"
        or safety.get("high_confidence_secret_scan") != "PASS"
    ):
        _error("latest Checkpoint-20H closeout safety checks did not pass")
    return head


def matching_prior_h3_manifests(
    repository_root: str | Path = ".",
) -> tuple[Path, ...]:
    repo = Path(repository_root).resolve()
    root = repo / MANIFEST_ROOT
    if not root.exists():
        return ()
    matches: list[Path] = []
    for path in root.rglob("*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        collector = doc.get("collector")
        arguments = doc.get("arguments")
        if not isinstance(collector, Mapping) or collector.get("name") != CP20I_COLLECTOR_NAME:
            continue
        if not isinstance(arguments, Mapping):
            continue
        if arguments.get("h3_validation_fingerprint") != H3_VALIDATION_FINGERPRINT:
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches))


def _create_or_validate_h3_attempt(
    *,
    path: Path,
    implementation_freeze: Mapping[str, Any],
    git_head: str,
    resume_manifest: Path | None,
) -> dict[str, Any]:
    fingerprint = str(implementation_freeze["h3_implementation_fingerprint"])
    if path.exists():
        attempt = _read_json(path)
        expected = {
            "schema_version": H3_ATTEMPT_SCHEMA_VERSION,
            "checkpoint_id": "20I",
            "candidate_id": DISTANCE_CANDIDATE_ID,
            "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
            "h3_implementation_fingerprint": fingerprint,
            "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
            "H3_permanently_exposed": True,
            "fresh_second_H3_attempt_allowed": False,
            "execution_enabled": False,
            "orders_placed": 0,
        }
        for key, value in expected.items():
            if attempt.get(key) != value:
                _error(f"H3 attempt receipt {key} mismatch")
        if resume_manifest is None:
            _error(
                "H3 attempt receipt already exists; fresh second H3 attempt is prohibited"
            )
        return attempt

    if resume_manifest is not None:
        _error("cannot resume H3 without an existing H3 exposure receipt")

    attempt = {
        "schema_version": H3_ATTEMPT_SCHEMA_VERSION,
        "checkpoint_id": "20I",
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
        "h3_implementation_fingerprint": fingerprint,
        "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
        "status": "h3_exposure_committed",
        "created_at_utc": _utc_now_text(),
        "git_head_at_exposure": git_head,
        "H3_permanently_exposed": True,
        "fresh_second_H3_attempt_allowed": False,
        "resume_only_after_interruption": True,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    _write_json_atomic(path, attempt)
    return attempt


def update_h3_attempt_receipt(
    path: Path,
    attempt: Mapping[str, Any],
    *,
    status: str,
    manifest_path: Path | None = None,
    result_fingerprint: str | None = None,
) -> None:
    updated = dict(attempt)
    updated["status"] = status
    updated["updated_at_utc"] = _utc_now_text()
    if manifest_path is not None:
        updated["latest_manifest"] = str(manifest_path)
    if result_fingerprint is not None:
        updated["result_fingerprint"] = result_fingerprint
    if status == "h3_evaluation_completed":
        updated["completed_at_utc"] = _utc_now_text()
    _write_json_atomic(path, updated)


def h3_preflight(
    *,
    repository_root: str | Path = ".",
    resume_manifest: str | Path | None = None,
) -> H3Preflight:
    repo = Path(repository_root).resolve()
    git_head = assert_clean_synchronized_repository(repo)
    implementation_freeze = validate_h3_implementation_freeze(repository_root=repo)
    final_model, validation_freeze = validate_checkpoint20g_preparation(repo)
    universe = load_and_validate_frozen_universe(repo)

    prior = matching_prior_h3_manifests(repo)
    resume_path = Path(resume_manifest).resolve() if resume_manifest is not None else None
    if resume_path is None:
        if prior:
            _error(f"prior H3 exposure manifest exists; refusing fresh run: {prior[-1]}")
    else:
        if resume_path not in prior:
            _error("resume manifest is not a recognized Candidate-E H3 manifest")
        manifest = _read_json(resume_path)
        if manifest.get("status") == "completed":
            _error("cannot resume a completed H3 evaluation")
        if manifest.get("status") not in {"running", "failed"}:
            _error(f"resume manifest has unsupported status {manifest.get('status')!r}")

    attempt_path = repo / DEFAULT_H3_ATTEMPT_PATH
    _create_or_validate_h3_attempt(
        path=attempt_path,
        implementation_freeze=implementation_freeze,
        git_head=git_head,
        resume_manifest=resume_path,
    )
    return H3Preflight(
        repository_root=repo,
        git_head=git_head,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        final_model=final_model,
        universe=universe,
        attempt_path=attempt_path,
    )


def validate_h3_outcomes(
    outcomes: Sequence[Mapping[str, str]],
    *,
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
    require_complete: bool,
) -> tuple[dict[str, str], ...]:
    plan = _h3_plan(validation_freeze)
    impl_fp = str(implementation_freeze["h3_implementation_fingerprint"])
    h1_h2_events, h1_h2_markets = _h1_h2_identity_sets(universe)
    expected_fields = set(H3_OUTCOME_FIELDS)
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []

    for index, source in enumerate(outcomes):
        row = dict(source)
        missing = expected_fields - set(row)
        extra = set(row) - expected_fields
        if missing or extra:
            _error(
                f"H3 outcome row {index} schema mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        expected = {
            "schema_version": H3_OUTCOME_SCHEMA_VERSION,
            "family_id": FAMILY_ID,
            "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
            "h3_implementation_fingerprint": impl_fp,
            "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
            "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
            "stage": "H3",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                _error(f"H3 outcome row {index} {key} mismatch")

        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        assert_not_h1_h2_identity(
            h1_h2_events=h1_h2_events,
            h1_h2_markets=h1_h2_markets,
            event_ticker=event,
            market_ticker=market,
        )
        if market in seen:
            _error(f"duplicate H3 outcome market {market}")
        seen.add(market)
        if plan.get(market) != event:
            _error(f"unplanned H3 outcome identity: {event}/{market}")
        if row["market_status"] != "finalized":
            _error(f"H3 market {market} is not finalized")
        if (row["result_text"], row["outcome"]) not in {("yes", "1"), ("no", "0")}:
            _error(f"H3 result/outcome mismatch for {market}")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            if not str(row[field]).strip():
                _error(f"H3 outcome row {index} {field} is blank")
        normalized.append(row)

    if require_complete and seen != set(plan):
        missing = sorted(set(plan) - seen)
        _error(
            f"H3 outcome set incomplete: missing {len(missing)} markets; first={missing[:5]}"
        )
    return tuple(normalized)


def collect_h3_outcomes(
    client: RawFirstJsonClient,
    *,
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
    existing_outcomes: Sequence[Mapping[str, str]] = (),
    on_outcome: Callable[[dict[str, str]], None] | None = None,
) -> tuple[dict[str, str], ...]:
    existing = validate_h3_outcomes(
        existing_outcomes,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        universe=universe,
        require_complete=False,
    )
    by_market = {row["market_ticker"]: dict(row) for row in existing}
    plan = _h3_plan(validation_freeze)
    impl_fp = str(implementation_freeze["h3_implementation_fingerprint"])
    h1_h2_events, h1_h2_markets = _h1_h2_identity_sets(universe)

    for market_ticker in sorted(plan):
        if market_ticker in by_market:
            continue
        event_ticker = plan[market_ticker]
        assert_not_h1_h2_identity(
            h1_h2_events=h1_h2_events,
            h1_h2_markets=h1_h2_markets,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
        )
        response = client.get_json(f"/historical/markets/{market_ticker}")
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            _error(f"H3 response for {market_ticker} missing market object")
        returned_ticker = str(market.get("ticker") or "").strip()
        returned_event = str(market.get("event_ticker") or "").strip()
        if not returned_ticker or not returned_event:
            _error(f"H3 response for {market_ticker} missing returned identity")
        assert_not_h1_h2_identity(
            h1_h2_events=h1_h2_events,
            h1_h2_markets=h1_h2_markets,
            event_ticker=returned_event,
            market_ticker=returned_ticker,
        )
        if returned_ticker != market_ticker or returned_event != event_ticker:
            _error(f"H3 outcome identity mismatch for requested market {market_ticker}")
        status = str(market.get("status") or "").strip().lower()
        result_text = str(market.get("result") or "").strip().lower()
        if status != "finalized":
            _error(f"H3 market {market_ticker} is not finalized: {status!r}")
        if result_text not in {"yes", "no"}:
            _error(f"H3 market {market_ticker} unsupported result {result_text!r}")

        row = {
            "schema_version": H3_OUTCOME_SCHEMA_VERSION,
            "family_id": FAMILY_ID,
            "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
            "h3_implementation_fingerprint": impl_fp,
            "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
            "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
            "stage": "H3",
            "event_ticker": returned_event,
            "market_ticker": returned_ticker,
            "raw_source": response.raw_record.source,
            "raw_session_id": response.raw_record.session_id,
            "raw_request_id": response.raw_record.request_id,
            "market_status": status,
            "result_text": result_text,
            "outcome": "1" if result_text == "yes" else "0",
        }
        if on_outcome is not None:
            on_outcome(row)
        by_market[market_ticker] = row

    ordered = [by_market[market] for market in sorted(plan)]
    return validate_h3_outcomes(
        ordered,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        universe=universe,
        require_complete=True,
    )


def initialize_h3_outcome_journal(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    _write_csv(path, H3_OUTCOME_FIELDS, ())


def append_h3_outcome_journal(path: Path, row: Mapping[str, Any]) -> None:
    missing = set(H3_OUTCOME_FIELDS) - set(row)
    extra = set(row) - set(H3_OUTCOME_FIELDS)
    if missing or extra:
        _error(
            f"H3 journal row schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(H3_OUTCOME_FIELDS),
            lineterminator="\n",
        )
        writer.writerow({field: row[field] for field in H3_OUTCOME_FIELDS})


def recover_h3_outcomes_from_manifest(
    *,
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
    repository_root: str | Path,
    manifest_path: str | Path,
) -> tuple[dict[str, str], ...]:
    repo = Path(repository_root).resolve()
    target = Path(manifest_path).resolve()
    document = _read_json(target)
    collector = document.get("collector")
    arguments = document.get("arguments")
    if not isinstance(collector, Mapping) or collector.get("name") != CP20I_COLLECTOR_NAME:
        _error("resume H3 manifest collector mismatch")
    if not isinstance(arguments, Mapping):
        _error("resume H3 manifest arguments missing")
    if arguments.get("h3_validation_fingerprint") != H3_VALIDATION_FINGERPRINT:
        _error("resume H3 manifest validation fingerprint mismatch")
    if arguments.get("h3_implementation_fingerprint") != implementation_freeze.get(
        "h3_implementation_fingerprint"
    ):
        _error("resume H3 manifest implementation fingerprint mismatch")
    run_id = str(document.get("run_id") or "").strip()
    if not run_id:
        _error("resume H3 manifest run_id missing")
    matches = list((repo / DERIVED_ROOT).rglob(f"{run_id}_candidate_e_h3_outcome_journal.csv"))
    if len(matches) != 1:
        _error(f"expected exactly one H3 outcome journal for {run_id}; found {len(matches)}")
    fields, rows = _read_csv(matches[0])
    if fields != H3_OUTCOME_FIELDS:
        _error("resume H3 outcome journal schema mismatch")
    return validate_h3_outcomes(
        rows,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        universe=universe,
        require_complete=False,
    )


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def predict_h3_probability(
    *,
    q_market: float,
    d_btc: float,
    beta_distance: float,
) -> float:
    if not all(math.isfinite(value) for value in (q_market, d_btc, beta_distance)):
        _error("H3 prediction received non-finite input")
    if beta_distance <= 0.0:
        _error("H3 frozen beta_distance must be positive")
    return _sigmoid(market_logit_offset(q_market) + beta_distance * d_btc)


def _row_log_loss(probability: float, outcome: int) -> float:
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        return math.inf
    if outcome == 1:
        return math.inf if probability <= 0.0 else -math.log(probability)
    return math.inf if probability >= 1.0 else -math.log1p(-probability)


def _row_brier(probability: float, outcome: int) -> float:
    return (probability - float(outcome)) ** 2


def _event_equal_metrics(
    rows: Sequence[Mapping[str, Any]],
    probability_field: str,
) -> tuple[float, float, dict[str, tuple[float, float, int]]]:
    event_losses: dict[str, list[float]] = {}
    event_briers: dict[str, list[float]] = {}
    for row in rows:
        event = str(row["event_ticker"])
        outcome = int(row["outcome"])
        probability = float(row[probability_field])
        event_losses.setdefault(event, []).append(_row_log_loss(probability, outcome))
        event_briers.setdefault(event, []).append(_row_brier(probability, outcome))
    if not event_losses:
        _error("H3 metric calculation received no events")
    event_metrics: dict[str, tuple[float, float, int]] = {}
    for event in event_losses:
        losses = event_losses[event]
        briers = event_briers[event]
        event_metrics[event] = (
            sum(losses) / len(losses)
            if all(math.isfinite(value) for value in losses)
            else math.inf,
            sum(briers) / len(briers),
            len(losses),
        )
    pooled_loss = sum(value[0] for value in event_metrics.values()) / len(event_metrics)
    pooled_brier = sum(value[1] for value in event_metrics.values()) / len(event_metrics)
    return pooled_loss, pooled_brier, event_metrics


def _structural_coverage_ok(
    predictions: Sequence[Mapping[str, Any]],
) -> bool:
    required_roles = {"q10", "q30", "q50", "q70", "q90"}
    required_ttc = {55, 50, 45, 40, 35, 30}
    for block in H3_BLOCKS:
        block_rows = [row for row in predictions if row["block_id"] == block]
        if {str(row["structural_role"]) for row in block_rows} != required_roles:
            return False
        if {int(row["ttc_target_minutes"]) for row in block_rows} != required_ttc:
            return False
    return True


def _h3_event_block_map(
    validation_freeze: Mapping[str, Any],
) -> dict[str, str]:
    raw = validation_freeze.get("h3_block_map")
    if not isinstance(raw, list) or len(raw) != H3_EVENT_COUNT:
        _error("H3 frozen block map changed")
    mapping: dict[str, str] = {}
    counts: dict[str, int] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            _error("H3 block-map entry invalid")
        event = str(item.get("event_ticker") or "")
        block = str(item.get("block_id") or "")
        if event in mapping:
            _error(f"duplicate H3 block-map event {event}")
        if block not in H3_BLOCKS:
            _error(f"invalid H3 block {block}")
        mapping[event] = block
        counts[block] = counts.get(block, 0) + 1
    if counts != {block: H3_EVENTS_PER_BLOCK for block in H3_BLOCKS}:
        _error(f"H3 block event counts changed: {counts}")
    return mapping


def passes_h3_validation_gate(
    *,
    pooled_raw_minus_candidate_log_loss: float,
    pooled_raw_minus_candidate_brier: float,
    block_raw_minus_candidate_log_loss: Sequence[float],
    median_event_raw_minus_candidate_log_loss: float,
    final_model_valid: bool,
    structural_coverage_ok: bool,
    policy_firewall_ok: bool,
) -> bool:
    values = (
        pooled_raw_minus_candidate_log_loss,
        pooled_raw_minus_candidate_brier,
        median_event_raw_minus_candidate_log_loss,
        *block_raw_minus_candidate_log_loss,
    )
    if any(not math.isfinite(value) for value in values):
        return False
    blocks = list(block_raw_minus_candidate_log_loss)
    return bool(
        pooled_raw_minus_candidate_log_loss > 0.0
        and pooled_raw_minus_candidate_brier >= 0.0
        and len(blocks) == 5
        and sum(delta > 0.0 for delta in blocks) >= 4
        and blocks[-1] > 0.0
        and median_event_raw_minus_candidate_log_loss > 0.0
        and final_model_valid
        and structural_coverage_ok
        and policy_firewall_ok
    )


def build_h3_predictions(
    *,
    outcomes: Sequence[Mapping[str, str]],
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    final_model: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
) -> tuple[dict[str, Any], ...]:
    valid_outcomes = validate_h3_outcomes(
        outcomes,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        universe=universe,
        require_complete=True,
    )
    model = validate_final_model_document(
        final_model,
        repository_root=".",
        verify_current_lineage_files=False,
    )
    beta = float(model["model"]["beta_distance"])
    labels = {row["market_ticker"]: int(row["outcome"]) for row in valid_outcomes}
    event_blocks = _h3_event_block_map(validation_freeze)
    predictions: list[dict[str, Any]] = []
    state_ids: set[str] = set()

    for index, row in enumerate(universe.preoutcome_rows):
        if row["stage"] != "H3":
            continue
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if market not in labels:
            _error(f"H3 preoutcome row references missing label {market}")
        block = event_blocks.get(event)
        if block != str(row["block_id"]):
            _error(f"H3 preoutcome row block mismatch for {event}")
        q_market = float(row["q_market"])
        d_btc = float(row["d_BTC"])
        if not all(math.isfinite(value) for value in (q_market, d_btc)):
            _error(f"H3 preoutcome row {index} has non-finite input")
        state_id = (
            f"{event}|{market}|TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in state_ids:
            _error(f"duplicate H3 state identity {state_id}")
        state_ids.add(state_id)
        predictions.append(
            {
                "block_id": block,
                "state_id": state_id,
                "event_ticker": event,
                "market_ticker": market,
                "structural_role": str(row["structural_role"]),
                "ttc_target_minutes": int(row["ttc_target_minutes"]),
                "outcome": labels[market],
                "q_market": q_market,
                "d_BTC": d_btc,
                "beta_distance": beta,
                "candidate_probability": predict_h3_probability(
                    q_market=q_market,
                    d_btc=d_btc,
                    beta_distance=beta,
                ),
            }
        )

    if len(predictions) != H3_ROW_COUNT:
        _error(f"H3 prediction row count changed: {len(predictions)}")
    if len({row["event_ticker"] for row in predictions}) != H3_EVENT_COUNT:
        _error("H3 prediction event count changed")
    return tuple(predictions)


def evaluate_h3(
    *,
    outcomes: Sequence[Mapping[str, str]],
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    final_model: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
) -> H3Evaluation:
    validate_h3_implementation_freeze_document(
        implementation_freeze,
        repo=Path(".").resolve(),
        verify_parent=False,
        verify_implementation_hashes=False,
    )
    predictions = build_h3_predictions(
        outcomes=outcomes,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        final_model=final_model,
        universe=universe,
    )
    raw_loss, raw_brier, raw_events = _event_equal_metrics(predictions, "q_market")
    candidate_loss, candidate_brier, candidate_events = _event_equal_metrics(
        predictions, "candidate_probability"
    )
    if set(raw_events) != set(candidate_events):
        _error("H3 raw/candidate event sets differ")

    event_deltas = {
        event: raw_events[event][0] - candidate_events[event][0]
        for event in raw_events
    }
    block_metrics: dict[str, dict[str, float]] = {}
    block_deltas: list[float] = []
    block_rows: list[dict[str, str]] = []

    for block in H3_BLOCKS:
        rows = [row for row in predictions if row["block_id"] == block]
        raw_block_loss, raw_block_brier, raw_block_events = _event_equal_metrics(
            rows, "q_market"
        )
        cand_block_loss, cand_block_brier, cand_block_events = _event_equal_metrics(
            rows, "candidate_probability"
        )
        if len(raw_block_events) != H3_EVENTS_PER_BLOCK or set(raw_block_events) != set(
            cand_block_events
        ):
            _error(f"H3 block {block} event membership changed")
        delta = raw_block_loss - cand_block_loss
        block_deltas.append(delta)
        block_metrics[block] = {
            "raw_log_loss": raw_block_loss,
            "candidate_log_loss": cand_block_loss,
            "raw_minus_candidate_log_loss": delta,
            "raw_brier": raw_block_brier,
            "candidate_brier": cand_block_brier,
            "raw_minus_candidate_brier": raw_block_brier - cand_block_brier,
        }
        block_rows.append(
            {
                "schema_version": H3_BLOCK_SCORE_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": DISTANCE_CANDIDATE_ID,
                "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
                "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
                "block_id": block,
                "event_count": str(H3_EVENTS_PER_BLOCK),
                "raw_log_loss": _float_text(raw_block_loss),
                "candidate_log_loss": _float_text(cand_block_loss),
                "raw_minus_candidate_log_loss": _float_text(delta),
                "raw_brier": _float_text(raw_block_brier),
                "candidate_brier": _float_text(cand_block_brier),
                "raw_minus_candidate_brier": _float_text(
                    raw_block_brier - cand_block_brier
                ),
                "candidate_beats_raw_log_loss": str(delta > 0.0).lower(),
            }
        )

    structural_ok = _structural_coverage_ok(predictions)
    median_delta = median(event_deltas.values())
    beta = float(final_model["model"]["beta_distance"])
    final_model_valid = (
        final_model["fit_result"].get("converged") is True
        and math.isfinite(beta)
        and beta > 0.0
    )
    finite_metrics = all(
        math.isfinite(value)
        for value in (
            raw_loss,
            raw_brier,
            candidate_loss,
            candidate_brier,
            median_delta,
            *block_deltas,
        )
    )
    gate = passes_h3_validation_gate(
        pooled_raw_minus_candidate_log_loss=raw_loss - candidate_loss,
        pooled_raw_minus_candidate_brier=raw_brier - candidate_brier,
        block_raw_minus_candidate_log_loss=block_deltas,
        median_event_raw_minus_candidate_log_loss=median_delta,
        final_model_valid=final_model_valid,
        structural_coverage_ok=structural_ok,
        policy_firewall_ok=finite_metrics,
    )

    prediction_rows: list[dict[str, str]] = []
    for row in predictions:
        prediction_rows.append(
            {
                "schema_version": H3_PREDICTION_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": DISTANCE_CANDIDATE_ID,
                "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
                "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
                "block_id": str(row["block_id"]),
                "state_id": str(row["state_id"]),
                "event_ticker": str(row["event_ticker"]),
                "market_ticker": str(row["market_ticker"]),
                "structural_role": str(row["structural_role"]),
                "ttc_target_minutes": str(row["ttc_target_minutes"]),
                "outcome": str(row["outcome"]),
                "q_market": _float_text(float(row["q_market"])),
                "d_BTC": _float_text(float(row["d_BTC"])),
                "beta_distance": _float_text(float(row["beta_distance"])),
                "candidate_probability": _float_text(
                    float(row["candidate_probability"])
                ),
            }
        )

    event_score_rows: list[dict[str, str]] = []
    event_block = {str(row["event_ticker"]): str(row["block_id"]) for row in predictions}
    for event in sorted(raw_events):
        raw_event = raw_events[event]
        candidate_event = candidate_events[event]
        event_score_rows.append(
            {
                "schema_version": H3_EVENT_SCORE_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": DISTANCE_CANDIDATE_ID,
                "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
                "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
                "block_id": event_block[event],
                "event_ticker": event,
                "row_count": str(raw_event[2]),
                "raw_log_loss": _float_text(raw_event[0]),
                "candidate_log_loss": _float_text(candidate_event[0]),
                "raw_minus_candidate_log_loss": _float_text(
                    raw_event[0] - candidate_event[0]
                ),
                "raw_brier": _float_text(raw_event[1]),
                "candidate_brier": _float_text(candidate_event[1]),
                "raw_minus_candidate_brier": _float_text(
                    raw_event[1] - candidate_event[1]
                ),
            }
        )

    summary = {
        "schema_version": H3_SUMMARY_SCHEMA_VERSION,
        "checkpoint_id": "20I",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "final_h1_h2_model_fingerprint": FINAL_H1_H2_MODEL_FINGERPRINT,
        "h3_validation_fingerprint": H3_VALIDATION_FINGERPRINT,
        "h3_implementation_fingerprint": implementation_freeze[
            "h3_implementation_fingerprint"
        ],
        "cohort_map_fingerprint": COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": ROW_UNIVERSE_FINGERPRINT,
        "H3_event_count": H3_EVENT_COUNT,
        "H3_row_count": H3_ROW_COUNT,
        "H3_market_count": H3_MARKET_COUNT,
        "beta_distance": _float_text(beta),
        "raw_event_equal_log_loss": _float_text(raw_loss),
        "candidate_event_equal_log_loss": _float_text(candidate_loss),
        "raw_minus_candidate_log_loss": _float_text(raw_loss - candidate_loss),
        "raw_event_equal_brier": _float_text(raw_brier),
        "candidate_event_equal_brier": _float_text(candidate_brier),
        "raw_minus_candidate_brier": _float_text(raw_brier - candidate_brier),
        "median_event_raw_minus_candidate_log_loss": _float_text(median_delta),
        "block_log_loss_deltas": {
            block: _float_text(block_metrics[block]["raw_minus_candidate_log_loss"])
            for block in H3_BLOCKS
        },
        "block_log_loss_win_count": sum(value > 0.0 for value in block_deltas),
        "latest_block_B4_win": block_deltas[-1] > 0.0,
        "structural_coverage_ok": structural_ok,
        "final_h1_h2_model_valid": final_model_valid,
        "metrics_finite": finite_metrics,
        "H3_validation_passed": bool(gate),
        "H3_permanently_exposed": True,
        "model_parameters_fitted_on_H3": False,
        "candidate_selection_on_H3_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    return H3Evaluation(
        summary=summary,
        block_rows=tuple(block_rows),
        prediction_rows=tuple(prediction_rows),
        event_score_rows=tuple(event_score_rows),
    )


def h3_result_fingerprint(summary: Mapping[str, Any]) -> str:
    return _canonical_sha256(dict(summary))


def write_h3_evaluation_outputs(
    output_dir: Path,
    *,
    run_id: str,
    outcomes: Sequence[Mapping[str, str]],
    evaluation: H3Evaluation,
    outcome_journal_path: Path,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = output_dir / f"{run_id}_candidate_e_h3_outcomes.csv"
    summary_path = output_dir / f"{run_id}_candidate_e_h3_summary.json"
    blocks_path = output_dir / f"{run_id}_candidate_e_h3_block_scores.csv"
    predictions_path = output_dir / f"{run_id}_candidate_e_h3_predictions.csv"
    events_path = output_dir / f"{run_id}_candidate_e_h3_event_scores.csv"

    _write_csv(outcomes_path, H3_OUTCOME_FIELDS, outcomes)
    summary_path.write_text(
        json.dumps(evaluation.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(blocks_path, H3_BLOCK_SCORE_FIELDS, evaluation.block_rows)
    _write_csv(predictions_path, H3_PREDICTION_FIELDS, evaluation.prediction_rows)
    _write_csv(events_path, H3_EVENT_SCORE_FIELDS, evaluation.event_score_rows)
    return (
        outcome_journal_path,
        outcomes_path,
        summary_path,
        blocks_path,
        predictions_path,
        events_path,
    )


__all__ = [
    "CP20I_COLLECTOR_NAME",
    "CandidateEH3EvaluationError",
    "DEFAULT_H3_ATTEMPT_PATH",
    "DEFAULT_H3_IMPLEMENTATION_FREEZE_PATH",
    "DERIVED_ROOT",
    "H3_OUTCOME_FIELDS",
    "append_h3_outcome_journal",
    "assert_clean_synchronized_repository",
    "assert_not_h1_h2_identity",
    "build_h3_predictions",
    "collect_h3_outcomes",
    "evaluate_h3",
    "h3_preflight",
    "h3_result_fingerprint",
    "initialize_h3_outcome_journal",
    "matching_prior_h3_manifests",
    "passes_h3_validation_gate",
    "predict_h3_probability",
    "recover_h3_outcomes_from_manifest",
    "update_h3_attempt_receipt",
    "validate_h3_implementation_freeze",
    "validate_h3_implementation_freeze_document",
    "validate_h3_outcomes",
    "write_h3_evaluation_outputs",
    "write_or_validate_h3_implementation_freeze",
]
