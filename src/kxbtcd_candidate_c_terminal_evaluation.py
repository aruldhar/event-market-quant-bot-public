"""Checkpoint-17 Candidate-C one-time terminal locked-test evaluation.

This module separates the checkpoint into two safety stages.

Stage A is outcome-blind:
* validate the Checkpoint-12 frozen pre-outcome dataset;
* validate the Checkpoint-16 preprocessing and final-model artifacts;
* derive the exact locked-test request allow-list from identifiers only;
* freeze/fingerprint the terminal evaluation procedure.

Stage B is terminal exposure:
* require a clean synchronized Git worktree before any HTTP client is created;
* mark the 64-event locked test permanently exposed before the first request;
* request only the pre-frozen locked-test market allow-list;
* preserve every response raw-first;
* score raw midpoint and the frozen Candidate-C model exactly once under the
  already frozen equal-event-weight log-loss/Brier metrics;
* apply the strict primary rule: Candidate-C log loss < raw midpoint log loss.

There is no fitting, tuning, scaling, calibration, feature selection, optimizer,
paper broker, demo execution, order placement, cancellation, transfer, or
real-money execution path in this module.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Callable, Mapping, Protocol, Sequence

from .kxbtcd_candidate_b_evaluation import (
    EXPECTED_PARTITION_EVENT_COUNTS,
    EXPECTED_PARTITION_ROW_COUNTS,
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_PREOUTCOME_RUN_ID,
    FROZEN_SPLIT_FINGERPRINT,
    FrozenPreoutcomeDataset,
    load_frozen_preoutcome_dataset,
)
from .kxbtcd_candidate_c_development import (
    CandidateCObservation,
    _market_logit,
    event_weighted_metrics,
)
from .kxbtcd_candidate_c_final_fit import (
    DEFAULT_FINAL_MODEL_PATH,
    DEFAULT_FULL_DEVELOPMENT_FREEZE_PATH,
    predict_with_final_model,
    validate_final_model_document,
    validate_full_development_freeze_document,
)
from .kxbtcd_candidate_c_predeclaration import CANDIDATE_ID
from .run_manifest import resolve_stored_path


class KxbtcdCandidateCTerminalEvaluationError(RuntimeError):
    """Raised when a Checkpoint-17 terminal-test invariant is violated."""


CP17_COLLECTOR_NAME = "collect_kxbtcd_candidate_c_locked_test"
TERMINAL_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_c_terminal_evaluation_freeze.v1"
TERMINAL_OUTCOME_SCHEMA_VERSION = "kxbtcd_candidate_c_terminal_outcome.v1"
TERMINAL_SUMMARY_SCHEMA_VERSION = "kxbtcd_candidate_c_terminal_summary.v1"
TERMINAL_PREDICTION_SCHEMA_VERSION = "kxbtcd_candidate_c_terminal_prediction.v1"
TERMINAL_ATTEMPT_SCHEMA_VERSION = "kxbtcd_candidate_c_terminal_attempt.v1"

EXPECTED_LOCKED_TEST_EVENTS = EXPECTED_PARTITION_EVENT_COUNTS["locked_test"]
EXPECTED_LOCKED_TEST_ROWS = EXPECTED_PARTITION_ROW_COUNTS["locked_test"]

FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT = (
    "d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3"
)
FROZEN_FINAL_MODEL_FINGERPRINT = (
    "13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f"
)

DEFAULT_TERMINAL_FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_c_terminal_evaluation_freeze.json"
)
DEFAULT_TERMINAL_ATTEMPT_PATH = Path(
    "data/analysis/kxbtcd_candidate_c_terminal_evaluation/terminal_test_attempt.json"
)
DERIVED_ROOT = Path("data/derived/kxbtcd_candidate_c_terminal_evaluation")
TERMINAL_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_c_terminal_evaluation.py",
    "collect_kxbtcd_candidate_c_locked_test.py",
)

TERMINAL_OUTCOME_FIELDS = (
    "schema_version",
    "candidate_id",
    "terminal_evaluation_fingerprint",
    "final_model_fingerprint",
    "preoutcome_run_id",
    "dataset_fingerprint",
    "split_fingerprint",
    "partition",
    "event_ticker",
    "market_ticker",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "market_status",
    "result_text",
    "outcome",
)

TERMINAL_PREDICTION_FIELDS = (
    "schema_version",
    "candidate_id",
    "terminal_evaluation_fingerprint",
    "final_model_fingerprint",
    "dataset_fingerprint",
    "split_fingerprint",
    "partition",
    "state_id",
    "event_ticker",
    "market_ticker",
    "outcome",
    "q_market",
    "spread",
    "candidate_c_probability",
)

TERMINAL_SUMMARY_FIELDS = (
    "schema_version",
    "candidate_id",
    "terminal_evaluation_fingerprint",
    "full_development_freeze_fingerprint",
    "final_model_fingerprint",
    "dataset_fingerprint",
    "split_fingerprint",
    "locked_test_event_count",
    "locked_test_row_count",
    "locked_test_market_label_count",
    "raw_midpoint_event_weighted_log_loss",
    "candidate_c_event_weighted_log_loss",
    "delta_log_loss_raw_minus_candidate_c",
    "raw_midpoint_event_weighted_brier",
    "candidate_c_event_weighted_brier",
    "delta_brier_raw_minus_candidate_c",
    "primary_rule",
    "tie_rule",
    "terminal_gate_passed",
    "locked_test_permanently_exposed",
    "model_refit_performed",
    "model_retuned",
    "model_recalibrated",
    "execution_enabled",
    "orders_placed",
)


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
class TerminalOutcomeRequest:
    event_ticker: str
    market_ticker: str


@dataclass(frozen=True)
class TerminalScore:
    summary: dict[str, str]
    prediction_rows: tuple[dict[str, str], ...]
    gate_passed: bool


@dataclass(frozen=True)
class TerminalPreflight:
    repository_root: Path
    git_head: str
    frozen: FrozenPreoutcomeDataset
    terminal_freeze: dict[str, Any]
    final_model: dict[str, Any]
    attempt_path: Path


def _error(message: str) -> None:
    raise KxbtcdCandidateCTerminalEvaluationError(message)


def _resolve(repo: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo / candidate


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _implementation_sha256s(repository_root: Path) -> dict[str, str]:
    """Hash the exact Stage-B implementation files bound by the procedure freeze."""
    result: dict[str, str] = {}
    for relative in TERMINAL_IMPLEMENTATION_FILES:
        path = repository_root / relative
        if not path.is_file():
            _error(f"terminal implementation file missing: {relative}")
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        _error("terminal evaluation produced a non-finite metric")
    return format(value, ".17g")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise KxbtcdCandidateCTerminalEvaluationError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateCTerminalEvaluationError(
            f"could not read JSON {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be an object: {path}")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _write_csv(
    path: Path,
    fields: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(rows):
            missing = set(fields) - set(row)
            extra = set(row) - set(fields)
            if missing or extra:
                _error(
                    f"CSV row {index} for {path.name} has schema mismatch; "
                    f"missing={sorted(missing)}, extra={sorted(extra)}"
                )
            writer.writerow({field: row[field] for field in fields})


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                _error(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except OSError as exc:
        raise KxbtcdCandidateCTerminalEvaluationError(
            f"could not read CSV {path}: {exc}"
        ) from exc


def _git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        _error(f"git {' '.join(args)} failed: {detail or completed.returncode}")
    return completed.stdout.strip()


def assert_clean_synchronized_repository(
    repository_root: str | Path = ".",
    *,
    branch: str = "main",
    remote_ref: str = "origin/main",
) -> str:
    """Fail closed unless the current local checkout is clean and synchronized.

    This function deliberately does not run ``git fetch`` itself. The operator
    must fetch immediately before the terminal command so the remote-tracking
    ref is fresh; then this verifies branch, clean status, and exact SHA equality.
    """

    repo = Path(repository_root).resolve()
    observed_branch = _git(repo, "branch", "--show-current")
    if observed_branch != branch:
        _error(f"terminal evaluation requires branch {branch!r}; got {observed_branch!r}")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        _error(
            "terminal evaluation requires a completely clean worktree/index; "
            f"first dirty line: {status.splitlines()[0]}"
        )
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", remote_ref)
    if head != remote:
        _error(
            "terminal evaluation requires local HEAD == origin/main after a fresh fetch; "
            f"HEAD={head}, {remote_ref}={remote}"
        )
    return head


def _load_frozen_model_bundle(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    freeze = _read_json(_resolve(repo, DEFAULT_FULL_DEVELOPMENT_FREEZE_PATH))
    final_model = _read_json(_resolve(repo, DEFAULT_FINAL_MODEL_PATH))
    validate_full_development_freeze_document(freeze)
    validate_final_model_document(final_model)
    if (
        freeze.get("full_development_freeze_fingerprint")
        != FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT
    ):
        _error("tracked full-development preprocessing fingerprint changed")
    if final_model.get("final_model_fingerprint") != FROZEN_FINAL_MODEL_FINGERPRINT:
        _error("tracked final Candidate-C model fingerprint changed")
    if (
        final_model.get("full_development_freeze_fingerprint")
        != FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT
    ):
        _error("final model is not bound to the frozen preprocessing fingerprint")
    if final_model.get("scaler") != freeze.get("scaler"):
        _error("final-model scaler differs from the frozen preprocessing artifact")
    return freeze, final_model


def locked_test_rows(
    frozen: FrozenPreoutcomeDataset,
    *,
    enforce_canonical_counts: bool = True,
) -> tuple[dict[str, str], ...]:
    rows = tuple(row for row in frozen.rows if row["partition"] == "locked_test")
    if enforce_canonical_counts:
        if len(rows) != EXPECTED_LOCKED_TEST_ROWS:
            _error(
                f"locked-test row count changed: {len(rows)} != {EXPECTED_LOCKED_TEST_ROWS}"
            )
        events = {row["event_ticker"] for row in rows}
        if len(events) != EXPECTED_LOCKED_TEST_EVENTS:
            _error(
                f"locked-test event count changed: {len(events)} != {EXPECTED_LOCKED_TEST_EVENTS}"
            )
    return rows


def build_locked_test_request_plan_from_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    enforce_canonical_counts: bool = True,
) -> tuple[TerminalOutcomeRequest, ...]:
    """Derive the exact terminal allow-list from identifiers only.

    The request plan does not read q_market, spread, labels, or any other feature.
    It is therefore suitable for the pre-outcome Stage-A freeze.
    """

    if enforce_canonical_counts:
        if len(rows) != EXPECTED_LOCKED_TEST_ROWS:
            _error("terminal request-plan derivation requires exactly 1,014 locked rows")
        event_count = len({_text(row.get("event_ticker"), "event_ticker") for row in rows})
        if event_count != EXPECTED_LOCKED_TEST_EVENTS:
            _error("terminal request-plan derivation requires exactly 64 locked events")

    pairs: set[tuple[str, str]] = set()
    market_event: dict[str, str] = {}
    for index, row in enumerate(rows):
        if row.get("partition") != "locked_test":
            _error(f"request-plan row {index} is not locked_test")
        event = _text(row.get("event_ticker"), f"rows[{index}].event_ticker")
        market = _text(row.get("market_ticker"), f"rows[{index}].market_ticker")
        previous = market_event.setdefault(market, event)
        if previous != event:
            _error(f"market {market} maps to multiple events in the locked partition")
        pairs.add((event, market))
    if not pairs:
        _error("locked-test request plan is empty")
    return tuple(
        TerminalOutcomeRequest(event_ticker=event, market_ticker=market)
        for event, market in sorted(pairs)
    )


def _request_plan_payload(
    plan: Sequence[TerminalOutcomeRequest],
) -> list[dict[str, str]]:
    return [
        {"event_ticker": item.event_ticker, "market_ticker": item.market_ticker}
        for item in plan
    ]


def build_terminal_evaluation_freeze_document(
    *,
    frozen: FrozenPreoutcomeDataset,
    source_baseline_commit: str,
    implementation_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    rows = locked_test_rows(frozen)
    plan = build_locked_test_request_plan_from_rows(rows)
    payload = {
        "schema_version": TERMINAL_FREEZE_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "partition": "locked_test",
        "locked_test_event_count": EXPECTED_LOCKED_TEST_EVENTS,
        "locked_test_row_count": EXPECTED_LOCKED_TEST_ROWS,
        "locked_test_market_request_count": len(plan),
        "request_plan": _request_plan_payload(plan),
        "outcome_source": {
            "endpoint_template": "/historical/markets/{market_ticker}",
            "required_market_status": "finalized",
            "accepted_results": ["yes", "no"],
            "raw_first_persistence_required": True,
            "authentication_required": False,
        },
        "inference": {
            "raw_midpoint_probability": "q_market",
            "candidate_c": "configs/kxbtcd_candidate_c_final_model.json",
            "candidate_inputs": ["q_market", "spread"],
            "fit_allowed": False,
            "retune_allowed": False,
            "recalibration_allowed": False,
            "feature_change_allowed": False,
            "preprocessing_change_allowed": False,
            "optimizer_change_allowed": False,
        },
        "metrics": {
            "primary": "event_weighted_log_loss",
            "secondary": "event_weighted_brier",
            "event_weighting_rule": (
                "compute the arithmetic mean row loss within each locked-test event, "
                "then arithmetic mean across the 64 events"
            ),
            "models_scored_on_identical_rows": True,
        },
        "primary_gate": {
            "rule": (
                "candidate_c_event_weighted_log_loss_strictly_less_than_"
                "raw_midpoint_event_weighted_log_loss"
            ),
            "tie": "fail",
            "secondary_metric_can_override": False,
        },
        "exposure_policy": {
            "permanently_expose_full_64_event_set_before_first_terminal_request": True,
            "fresh_second_terminal_attempt_allowed": False,
            "resume_only_after_interruption": True,
            "post_exposure_redesign_allowed": False,
            "future_untouched_test_claim_on_these_events_allowed": False,
        },
        "source_baseline_commit": _text(source_baseline_commit, "source_baseline_commit"),
        "implementation_sha256s": {
            key: _text(value, f"implementation_sha256s[{key}]")
            for key, value in sorted(implementation_sha256s.items())
        },
        "procedure_derivation_outcomes_used": False,
        "locked_test_feature_density_used_for_design": False,
        "locked_test_outcomes_opened_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["terminal_evaluation_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_terminal_evaluation_freeze_document(
    document: Mapping[str, Any],
    *,
    frozen: FrozenPreoutcomeDataset | None = None,
    repository_root: str | Path | None = None,
) -> tuple[TerminalOutcomeRequest, ...]:
    if document.get("schema_version") != TERMINAL_FREEZE_SCHEMA_VERSION:
        _error("terminal evaluation freeze schema mismatch")
    expected_identity = {
        "candidate_id": CANDIDATE_ID,
        "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "frozen_preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "partition": "locked_test",
        "locked_test_event_count": EXPECTED_LOCKED_TEST_EVENTS,
        "locked_test_row_count": EXPECTED_LOCKED_TEST_ROWS,
        "procedure_derivation_outcomes_used": False,
        "locked_test_feature_density_used_for_design": False,
        "locked_test_outcomes_opened_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, expected in expected_identity.items():
        if document.get(key) != expected:
            _error(f"terminal evaluation freeze {key} mismatch")

    inference = document.get("inference")
    if not isinstance(inference, Mapping):
        _error("terminal evaluation freeze missing inference policy")
    required_false = (
        "fit_allowed",
        "retune_allowed",
        "recalibration_allowed",
        "feature_change_allowed",
        "preprocessing_change_allowed",
        "optimizer_change_allowed",
    )
    for key in required_false:
        if inference.get(key) is not False:
            _error(f"terminal inference policy unexpectedly permits {key}")
    if inference.get("raw_midpoint_probability") != "q_market":
        _error("raw midpoint benchmark changed")
    if inference.get("candidate_inputs") != ["q_market", "spread"]:
        _error("Candidate-C terminal input set changed")

    metrics = document.get("metrics")
    if not isinstance(metrics, Mapping):
        _error("terminal evaluation freeze missing metric policy")
    if metrics.get("primary") != "event_weighted_log_loss":
        _error("terminal primary metric changed")
    if metrics.get("secondary") != "event_weighted_brier":
        _error("terminal secondary metric changed")
    if metrics.get("models_scored_on_identical_rows") is not True:
        _error("terminal models are not frozen to identical scoring rows")

    gate = document.get("primary_gate")
    if not isinstance(gate, Mapping):
        _error("terminal evaluation freeze missing primary gate")
    if gate.get("rule") != (
        "candidate_c_event_weighted_log_loss_strictly_less_than_"
        "raw_midpoint_event_weighted_log_loss"
    ):
        _error("terminal primary gate changed")
    if gate.get("tie") != "fail" or gate.get("secondary_metric_can_override") is not False:
        _error("terminal tie/override rule changed")

    exposure = document.get("exposure_policy")
    if not isinstance(exposure, Mapping):
        _error("terminal evaluation freeze missing exposure policy")
    expected_exposure = {
        "permanently_expose_full_64_event_set_before_first_terminal_request": True,
        "fresh_second_terminal_attempt_allowed": False,
        "resume_only_after_interruption": True,
        "post_exposure_redesign_allowed": False,
        "future_untouched_test_claim_on_these_events_allowed": False,
    }
    for key, expected in expected_exposure.items():
        if exposure.get(key) != expected:
            _error(f"terminal exposure policy {key} changed")

    entries = document.get("request_plan")
    if not isinstance(entries, list) or not entries:
        _error("terminal evaluation request plan is missing")
    plan: list[TerminalOutcomeRequest] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != {"event_ticker", "market_ticker"}:
            _error(f"terminal request-plan entry {index} schema mismatch")
        event = _text(entry["event_ticker"], f"request_plan[{index}].event_ticker")
        market = _text(entry["market_ticker"], f"request_plan[{index}].market_ticker")
        if market in seen:
            _error(f"duplicate terminal request market {market}")
        seen.add(market)
        plan.append(TerminalOutcomeRequest(event_ticker=event, market_ticker=market))
    if plan != sorted(plan, key=lambda item: (item.event_ticker, item.market_ticker)):
        _error("terminal request plan is not canonically sorted")
    if document.get("locked_test_market_request_count") != len(plan):
        _error("terminal request count does not match frozen request plan")

    implementation = document.get("implementation_sha256s")
    if not isinstance(implementation, Mapping):
        _error("terminal evaluation freeze is missing implementation hashes")
    expected_files = set(TERMINAL_IMPLEMENTATION_FILES)
    if set(implementation) != expected_files:
        _error("terminal evaluation implementation-file set changed")
    for relative, digest in implementation.items():
        if not isinstance(digest, str) or len(digest) != 64:
            _error(f"invalid terminal implementation hash for {relative}")

    if repository_root is not None:
        repo = Path(repository_root).resolve()
        observed_hashes = _implementation_sha256s(repo)
        if dict(implementation) != observed_hashes:
            _error(
                "terminal implementation bytes differ from the frozen procedure; "
                "refusing terminal access"
            )

    payload = {
        key: document[key]
        for key in document
        if key != "terminal_evaluation_fingerprint"
    }
    if document.get("terminal_evaluation_fingerprint") != _canonical_sha256(payload):
        _error("terminal evaluation procedure fingerprint mismatch")

    if frozen is not None:
        expected = build_terminal_evaluation_freeze_document(
            frozen=frozen,
            source_baseline_commit=_text(
                document.get("source_baseline_commit"), "source_baseline_commit"
            ),
            implementation_sha256s=dict(
                document.get("implementation_sha256s", {})
            ),
        )
        if dict(document) != expected:
            _error(
                "stored terminal evaluation freeze differs from the current "
                "deterministic outcome-blind derivation"
            )
    return tuple(plan)


def write_or_validate_terminal_evaluation_freeze(
    path: str | Path = DEFAULT_TERMINAL_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    # Stage A may run with uncommitted CP17 code present, so cleanliness is not
    # required here. We bind the procedure to the committed source baseline HEAD.
    head = _git(repo, "rev-parse", "HEAD")
    frozen = load_frozen_preoutcome_dataset(repo)
    _load_frozen_model_bundle(repo)
    derived = build_terminal_evaluation_freeze_document(
        frozen=frozen,
        source_baseline_commit=head,
        implementation_sha256s=_implementation_sha256s(repo),
    )
    validate_terminal_evaluation_freeze_document(
        derived,
        frozen=frozen,
        repository_root=repo,
    )
    target = _resolve(repo, path)
    if target.exists():
        existing = _read_json(target)
        validate_terminal_evaluation_freeze_document(
            existing,
            frozen=frozen,
            repository_root=repo,
        )
        if existing != derived:
            _error(
                "existing terminal evaluation freeze differs from deterministic "
                "derivation; refusing overwrite"
            )
        return target, existing
    _write_json_atomic(target, derived)
    return target, derived


def load_and_validate_terminal_evaluation_freeze(
    path: str | Path = DEFAULT_TERMINAL_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[dict[str, Any], FrozenPreoutcomeDataset, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    frozen = load_frozen_preoutcome_dataset(repo)
    _, final_model = _load_frozen_model_bundle(repo)
    target = _resolve(repo, path)
    document = _read_json(target)
    validate_terminal_evaluation_freeze_document(
        document,
        frozen=frozen,
        repository_root=repo,
    )
    return document, frozen, final_model


def matching_prior_terminal_manifests(
    repository_root: str | Path = ".",
) -> tuple[Path, ...]:
    repo = Path(repository_root).resolve()
    root = repo / "data" / "manifests"
    if not root.exists():
        return ()
    matches: list[Path] = []
    for path in root.rglob("*.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, Mapping):
            continue
        collector = manifest.get("collector")
        arguments = manifest.get("arguments")
        if not isinstance(collector, Mapping) or collector.get("name") != CP17_COLLECTOR_NAME:
            continue
        if not isinstance(arguments, Mapping):
            continue
        if arguments.get("final_model_fingerprint") != FROZEN_FINAL_MODEL_FINGERPRINT:
            continue
        if arguments.get("dataset_fingerprint") != FROZEN_DATASET_FINGERPRINT:
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches, key=lambda p: p.stat().st_mtime_ns))


def _create_or_validate_attempt_receipt(
    *,
    path: Path,
    terminal_freeze: Mapping[str, Any],
    git_head: str,
    resume_manifest: Path | None,
) -> dict[str, Any]:
    fingerprint = _text(
        terminal_freeze.get("terminal_evaluation_fingerprint"),
        "terminal_evaluation_fingerprint",
    )
    if path.exists():
        attempt = _read_json(path)
        if resume_manifest is None:
            _error(
                "terminal-test attempt receipt already exists; fresh second attempts "
                "are prohibited. Use the frozen resume path only after an interrupted run."
            )
        if attempt.get("schema_version") != TERMINAL_ATTEMPT_SCHEMA_VERSION:
            _error("terminal attempt receipt schema mismatch")
        if attempt.get("terminal_evaluation_fingerprint") != fingerprint:
            _error("terminal attempt receipt procedure fingerprint mismatch")
        if attempt.get("final_model_fingerprint") != FROZEN_FINAL_MODEL_FINGERPRINT:
            _error("terminal attempt receipt final-model fingerprint mismatch")
        if attempt.get("locked_test_permanently_exposed") is not True:
            _error("terminal attempt receipt must conservatively mark the test exposed")
        if attempt.get("status") == "terminal_evaluation_completed":
            _error("terminal evaluation is already completed; refusing another score")
        return attempt

    if resume_manifest is not None:
        _error("cannot resume without the original terminal-test attempt receipt")
    attempt = {
        "schema_version": TERMINAL_ATTEMPT_SCHEMA_VERSION,
        "status": "terminal_exposure_authorized",
        "candidate_id": CANDIDATE_ID,
        "terminal_evaluation_fingerprint": fingerprint,
        "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "locked_test_event_count": EXPECTED_LOCKED_TEST_EVENTS,
        "locked_test_row_count": EXPECTED_LOCKED_TEST_ROWS,
        # Conservative policy: once Stage B begins, the entire terminal block is
        # permanently considered exposed even if the first network request fails.
        "locked_test_permanently_exposed": True,
        "fresh_second_attempt_allowed": False,
        "started_at_utc": _utc_now_text(),
        "git_head_at_start": git_head,
        "resume_manifest": "",
        "execution_enabled": False,
        "orders_placed": 0,
    }
    _write_json_atomic(path, attempt)
    return attempt


def update_attempt_receipt(
    path: Path,
    attempt: Mapping[str, Any],
    *,
    status: str,
    manifest_path: str | Path | None = None,
    result_fingerprint: str | None = None,
) -> None:
    updated = dict(attempt)
    updated["status"] = status
    updated["updated_at_utc"] = _utc_now_text()
    if manifest_path is not None:
        updated["latest_manifest"] = str(manifest_path)
    if result_fingerprint is not None:
        updated["result_fingerprint"] = result_fingerprint
    if status == "terminal_evaluation_completed":
        updated["completed_at_utc"] = _utc_now_text()
    _write_json_atomic(path, updated)


def terminal_preflight(
    *,
    repository_root: str | Path = ".",
    resume_manifest: str | Path | None = None,
) -> TerminalPreflight:
    """Run all fail-closed checks before any terminal HTTP client is created."""

    repo = Path(repository_root).resolve()
    git_head = assert_clean_synchronized_repository(repo)
    terminal_freeze, frozen, final_model = load_and_validate_terminal_evaluation_freeze(
        repository_root=repo
    )
    attempt_path = _resolve(repo, DEFAULT_TERMINAL_ATTEMPT_PATH)
    prior = matching_prior_terminal_manifests(repo)
    resume_path = Path(resume_manifest).resolve() if resume_manifest is not None else None

    if resume_path is None:
        if prior:
            _error(
                "prior CP17 terminal exposure manifest(s) exist; refusing a fresh run. "
                f"Latest: {prior[-1]}"
            )
    else:
        if resume_path not in prior:
            _error("resume manifest is not a recognized CP17 terminal manifest")
        manifest = _read_json(resume_path)
        if manifest.get("status") == "completed":
            _error("cannot resume a completed terminal evaluation")
        if manifest.get("status") not in {"running", "failed"}:
            _error(f"resume manifest has unsupported status {manifest.get('status')!r}")

    _create_or_validate_attempt_receipt(
        path=attempt_path,
        terminal_freeze=terminal_freeze,
        git_head=git_head,
        resume_manifest=resume_path,
    )
    return TerminalPreflight(
        repository_root=repo,
        git_head=git_head,
        frozen=frozen,
        terminal_freeze=terminal_freeze,
        final_model=final_model,
        attempt_path=attempt_path,
    )


def _planned_by_market(
    terminal_freeze: Mapping[str, Any],
) -> dict[str, TerminalOutcomeRequest]:
    plan = validate_terminal_evaluation_freeze_document(terminal_freeze)
    return {item.market_ticker: item for item in plan}


def _validate_terminal_outcomes(
    outcomes: Sequence[Mapping[str, str]],
    *,
    terminal_freeze: Mapping[str, Any],
    require_complete: bool,
) -> tuple[dict[str, str], ...]:
    planned = _planned_by_market(terminal_freeze)
    fingerprint = str(terminal_freeze["terminal_evaluation_fingerprint"])
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, source in enumerate(outcomes):
        row = dict(source)
        missing = set(TERMINAL_OUTCOME_FIELDS) - set(row)
        extra = set(row) - set(TERMINAL_OUTCOME_FIELDS)
        if missing or extra:
            _error(
                f"terminal outcome row {index} schema mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        expected_identity = {
            "schema_version": TERMINAL_OUTCOME_SCHEMA_VERSION,
            "candidate_id": CANDIDATE_ID,
            "terminal_evaluation_fingerprint": fingerprint,
            "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
            "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
            "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
            "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
            "partition": "locked_test",
        }
        for key, expected in expected_identity.items():
            if row.get(key) != expected:
                _error(f"terminal outcome row {index} {key} mismatch")
        market = _text(row["market_ticker"], f"outcomes[{index}].market_ticker")
        if market in seen:
            _error(f"duplicate terminal outcome for market {market}")
        seen.add(market)
        plan = planned.get(market)
        if plan is None:
            _error(f"unplanned terminal outcome market {market}")
        if row["event_ticker"] != plan.event_ticker:
            _error(f"terminal outcome event mismatch for {market}")
        if row["market_status"] != "finalized":
            _error(f"terminal outcome market {market} is not finalized")
        if (row["result_text"], row["outcome"]) not in {("yes", "1"), ("no", "0")}:
            _error(f"terminal result/outcome mismatch for {market}")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            _text(row[field], f"outcomes[{index}].{field}")
        normalized.append(row)
    if require_complete and seen != set(planned):
        missing = sorted(set(planned) - seen)
        _error(
            f"terminal outcome set incomplete: missing {len(missing)} markets; "
            f"first={missing[:5]}"
        )
    return tuple(normalized)


def collect_locked_test_outcomes(
    client: RawFirstJsonClient,
    *,
    terminal_freeze: Mapping[str, Any],
    existing_outcomes: Sequence[Mapping[str, str]] = (),
    on_outcome: Callable[[dict[str, str]], None] | None = None,
) -> tuple[dict[str, str], ...]:
    """Collect only the exact pre-frozen locked-test market allow-list."""

    existing = _validate_terminal_outcomes(
        existing_outcomes,
        terminal_freeze=terminal_freeze,
        require_complete=False,
    )
    by_market = {row["market_ticker"]: dict(row) for row in existing}
    planned = _planned_by_market(terminal_freeze)
    fingerprint = str(terminal_freeze["terminal_evaluation_fingerprint"])

    for market_ticker in sorted(planned):
        if market_ticker in by_market:
            continue
        plan = planned[market_ticker]
        response = client.get_json(f"/historical/markets/{market_ticker}")
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            _error(f"terminal outcome response for {market_ticker} missing market object")
        returned_ticker = _text(market.get("ticker"), "returned market ticker")
        returned_event = _text(market.get("event_ticker"), "returned event_ticker")
        if returned_ticker != market_ticker or returned_event != plan.event_ticker:
            _error(f"terminal outcome identity mismatch for {market_ticker}")
        status = _text(market.get("status"), "market status").lower()
        result_text = _text(market.get("result"), "market result").lower()
        if status != "finalized":
            _error(f"terminal market {market_ticker} is not finalized: {status}")
        if result_text not in {"yes", "no"}:
            _error(
                f"terminal market {market_ticker} has unsupported result {result_text!r}"
            )
        row = {
            "schema_version": TERMINAL_OUTCOME_SCHEMA_VERSION,
            "candidate_id": CANDIDATE_ID,
            "terminal_evaluation_fingerprint": fingerprint,
            "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
            "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
            "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
            "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
            "partition": "locked_test",
            "event_ticker": plan.event_ticker,
            "market_ticker": market_ticker,
            "raw_source": _text(response.raw_record.source, "raw source"),
            "raw_session_id": _text(response.raw_record.session_id, "raw session_id"),
            "raw_request_id": _text(response.raw_record.request_id, "raw request_id"),
            "market_status": status,
            "result_text": result_text,
            "outcome": "1" if result_text == "yes" else "0",
        }
        _validate_terminal_outcomes(
            [row],
            terminal_freeze=terminal_freeze,
            require_complete=False,
        )
        by_market[market_ticker] = row
        if on_outcome is not None:
            on_outcome(dict(row))

    rows = tuple(by_market[key] for key in sorted(by_market))
    _validate_terminal_outcomes(
        rows,
        terminal_freeze=terminal_freeze,
        require_complete=True,
    )
    return rows


def initialize_terminal_outcome_journal(path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = _read_csv(target)
        if existing:
            _error(f"refusing to overwrite non-empty terminal outcome journal {target}")
        return target
    _write_csv(target, TERMINAL_OUTCOME_FIELDS, ())
    return target


def append_terminal_outcome_journal(path: str | Path, row: Mapping[str, Any]) -> None:
    target = Path(path)
    missing = set(TERMINAL_OUTCOME_FIELDS) - set(row)
    extra = set(row) - set(TERMINAL_OUTCOME_FIELDS)
    if missing or extra:
        _error(
            f"terminal journal row schema mismatch; missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    with target.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(TERMINAL_OUTCOME_FIELDS), lineterminator="\n"
        )
        writer.writerow({field: row[field] for field in TERMINAL_OUTCOME_FIELDS})
        handle.flush()


def score_terminal_locked_test(
    *,
    frozen: FrozenPreoutcomeDataset,
    terminal_freeze: Mapping[str, Any],
    final_model: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, str]],
    predictor: Callable[[float, float, Mapping[str, Any]], float] = predict_with_final_model,
    enforce_canonical_counts: bool = True,
) -> TerminalScore:
    """Compute the frozen terminal metrics exactly once from complete labels."""

    validated = _validate_terminal_outcomes(
        outcomes,
        terminal_freeze=terminal_freeze,
        require_complete=True,
    )
    label_by_market = {row["market_ticker"]: int(row["outcome"]) for row in validated}
    source_rows = locked_test_rows(
        frozen,
        enforce_canonical_counts=enforce_canonical_counts,
    )
    observations: list[CandidateCObservation] = []
    raw_probabilities: list[float] = []
    candidate_probabilities: list[float] = []
    prediction_rows: list[dict[str, str]] = []
    fingerprint = str(terminal_freeze["terminal_evaluation_fingerprint"])

    for index, row in enumerate(source_rows):
        market = _text(row.get("market_ticker"), f"locked_rows[{index}].market_ticker")
        if market not in label_by_market:
            _error(f"missing terminal label for scoring market {market}")
        q = _float(row.get("q_market"), f"locked_rows[{index}].q_market")
        spread = _float(row.get("spread"), f"locked_rows[{index}].spread")
        if not 0.0 <= q <= 1.0:
            _error(f"locked_rows[{index}].q_market outside [0,1]")
        if spread < 0.0:
            _error(f"locked_rows[{index}].spread is negative")
        outcome = label_by_market[market]
        candidate = float(predictor(q, spread, final_model))
        if not math.isfinite(candidate) or not 0.0 <= candidate <= 1.0:
            _error("frozen Candidate-C inference returned an invalid probability")
        observation = CandidateCObservation(
            state_id=_text(row.get("state_id"), f"locked_rows[{index}].state_id"),
            event_ticker=_text(
                row.get("event_ticker"), f"locked_rows[{index}].event_ticker"
            ),
            market_ticker=market,
            utc_week_start=_text(
                row.get("utc_week_start"), f"locked_rows[{index}].utc_week_start"
            ),
            block=5,
            outcome=outcome,
            q_market=q,
            market_logit=_market_logit(q),
            spread=spread,
            market_logit_x_spread=_market_logit(q) * spread,
        )
        observations.append(observation)
        raw_probabilities.append(q)
        candidate_probabilities.append(candidate)
        prediction_rows.append(
            {
                "schema_version": TERMINAL_PREDICTION_SCHEMA_VERSION,
                "candidate_id": CANDIDATE_ID,
                "terminal_evaluation_fingerprint": fingerprint,
                "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
                "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                "partition": "locked_test",
                "state_id": observation.state_id,
                "event_ticker": observation.event_ticker,
                "market_ticker": observation.market_ticker,
                "outcome": str(outcome),
                "q_market": _float_text(q),
                "spread": _float_text(spread),
                "candidate_c_probability": _float_text(candidate),
            }
        )

    if enforce_canonical_counts:
        if len(observations) != EXPECTED_LOCKED_TEST_ROWS:
            _error("terminal scoring row count changed")
        if len({row.event_ticker for row in observations}) != EXPECTED_LOCKED_TEST_EVENTS:
            _error("terminal scoring event count changed")

    raw = event_weighted_metrics(observations, raw_probabilities)
    candidate = event_weighted_metrics(observations, candidate_probabilities)
    gate_passed = candidate.log_loss < raw.log_loss
    summary = {
        "schema_version": TERMINAL_SUMMARY_SCHEMA_VERSION,
        "candidate_id": CANDIDATE_ID,
        "terminal_evaluation_fingerprint": fingerprint,
        "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "locked_test_event_count": str(len({row.event_ticker for row in observations})),
        "locked_test_row_count": str(len(observations)),
        "locked_test_market_label_count": str(len(validated)),
        "raw_midpoint_event_weighted_log_loss": _float_text(raw.log_loss),
        "candidate_c_event_weighted_log_loss": _float_text(candidate.log_loss),
        "delta_log_loss_raw_minus_candidate_c": _float_text(
            raw.log_loss - candidate.log_loss
        ),
        "raw_midpoint_event_weighted_brier": _float_text(raw.brier),
        "candidate_c_event_weighted_brier": _float_text(candidate.brier),
        "delta_brier_raw_minus_candidate_c": _float_text(raw.brier - candidate.brier),
        "primary_rule": (
            "candidate_c_event_weighted_log_loss_strictly_less_than_"
            "raw_midpoint_event_weighted_log_loss"
        ),
        "tie_rule": "fail",
        "terminal_gate_passed": "true" if gate_passed else "false",
        "locked_test_permanently_exposed": "true",
        "model_refit_performed": "false",
        "model_retuned": "false",
        "model_recalibrated": "false",
        "execution_enabled": "false",
        "orders_placed": "0",
    }
    return TerminalScore(
        summary=summary,
        prediction_rows=tuple(prediction_rows),
        gate_passed=gate_passed,
    )


def write_terminal_evaluation_outputs(
    output_dir: str | Path,
    *,
    run_id: str,
    outcomes: Sequence[Mapping[str, str]],
    score: TerminalScore,
    outcome_journal_path: str | Path | None = None,
) -> tuple[Path, ...]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    outcomes_path = root / f"{run_id}_kxbtcd_candidate_c_terminal_outcomes.csv"
    predictions_path = root / f"{run_id}_kxbtcd_candidate_c_terminal_predictions.csv"
    summary_path = root / f"{run_id}_kxbtcd_candidate_c_terminal_summary.csv"
    _write_csv(outcomes_path, TERMINAL_OUTCOME_FIELDS, outcomes)
    _write_csv(predictions_path, TERMINAL_PREDICTION_FIELDS, score.prediction_rows)
    _write_csv(summary_path, TERMINAL_SUMMARY_FIELDS, [score.summary])
    paths = [outcomes_path, predictions_path, summary_path]
    if outcome_journal_path is not None:
        journal = Path(outcome_journal_path)
        if journal.exists() and journal.resolve() not in {path.resolve() for path in paths}:
            paths.append(journal)
    return tuple(paths)


def terminal_result_fingerprint(summary: Mapping[str, str]) -> str:
    missing = set(TERMINAL_SUMMARY_FIELDS) - set(summary)
    extra = set(summary) - set(TERMINAL_SUMMARY_FIELDS)
    if missing or extra:
        _error(
            f"terminal summary schema mismatch; missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    return _canonical_sha256(dict(summary))


def _raw_paths_for_manifest(
    *,
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> tuple[Path, ...]:
    paths: set[Path] = set()
    files = manifest.get("files")
    if isinstance(files, list):
        for descriptor in files:
            if not isinstance(descriptor, Mapping) or descriptor.get("role") != "raw_api_archive":
                continue
            stored = descriptor.get("path")
            if isinstance(stored, Mapping):
                resolved = resolve_stored_path(stored, repository_root)
                if resolved.is_file():
                    paths.add(resolved)
    sessions = manifest.get("source_sessions")
    if isinstance(sessions, list):
        for session in sessions:
            if not isinstance(session, Mapping):
                continue
            session_id = session.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                continue
            for raw_root in (
                repository_root / "data" / "raw" / "kalshi_rest",
                repository_root / "data" / "raw",
            ):
                if raw_root.exists():
                    paths.update(
                        path
                        for path in raw_root.rglob(f"{session_id}.jsonl")
                        if path.is_file()
                    )
    return tuple(sorted(paths))


def recover_terminal_outcomes_from_manifest(
    *,
    terminal_freeze: Mapping[str, Any],
    repository_root: str | Path,
    manifest_path: str | Path,
) -> tuple[dict[str, str], ...]:
    """Recover already-opened locked labels from raw archives with zero HTTP calls."""

    repo = Path(repository_root).resolve()
    path = Path(manifest_path).resolve()
    manifest = _read_json(path)
    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != CP17_COLLECTOR_NAME:
        _error("resume manifest is not a CP17 terminal collector")
    if manifest.get("status") == "completed":
        _error("terminal resume manifest is already completed")
    if manifest.get("status") not in {"running", "failed"}:
        _error(f"terminal resume manifest status unsupported: {manifest.get('status')!r}")
    arguments = manifest.get("arguments")
    if not isinstance(arguments, Mapping):
        _error("terminal resume manifest missing arguments")
    expected_args = {
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "terminal_evaluation_fingerprint": terminal_freeze[
            "terminal_evaluation_fingerprint"
        ],
    }
    for key, expected in expected_args.items():
        if arguments.get(key) != expected:
            _error(f"terminal resume manifest {key} mismatch")

    planned = _planned_by_market(terminal_freeze)
    recovered: dict[str, dict[str, str]] = {}
    for raw_path in _raw_paths_for_manifest(manifest=manifest, repository_root=repo):
        with raw_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise KxbtcdCandidateCTerminalEvaluationError(
                        f"invalid raw JSON at {raw_path}:{line_number}"
                    ) from exc
                if not isinstance(record, Mapping):
                    continue
                request = record.get("request")
                response = record.get("response")
                if not isinstance(request, Mapping) or not isinstance(response, Mapping):
                    continue
                request_path = request.get("path")
                if not isinstance(request_path, str) or not request_path.startswith(
                    "/historical/markets/"
                ):
                    continue
                ticker = request_path.rsplit("/", 1)[-1]
                plan = planned.get(ticker)
                if plan is None:
                    continue
                if record.get("error") is not None:
                    continue
                try:
                    status_code = int(response.get("status_code"))
                except (TypeError, ValueError):
                    continue
                if not 200 <= status_code < 300:
                    continue
                body_text = response.get("body_text")
                if not isinstance(body_text, str):
                    continue
                try:
                    payload = json.loads(body_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, Mapping):
                    continue
                market = payload.get("market")
                if not isinstance(market, Mapping):
                    continue
                returned_ticker = market.get("ticker")
                returned_event = market.get("event_ticker")
                status = str(market.get("status") or "").lower()
                result_text = str(market.get("result") or "").lower()
                if returned_ticker != ticker or returned_event != plan.event_ticker:
                    _error(f"terminal raw recovery identity mismatch for {ticker}")
                if status != "finalized" or result_text not in {"yes", "no"}:
                    continue
                row = {
                    "schema_version": TERMINAL_OUTCOME_SCHEMA_VERSION,
                    "candidate_id": CANDIDATE_ID,
                    "terminal_evaluation_fingerprint": terminal_freeze[
                        "terminal_evaluation_fingerprint"
                    ],
                    "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
                    "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
                    "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                    "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                    "partition": "locked_test",
                    "event_ticker": plan.event_ticker,
                    "market_ticker": ticker,
                    "raw_source": _text(record.get("source"), "raw recovery source"),
                    "raw_session_id": _text(
                        record.get("session_id"), "raw recovery session_id"
                    ),
                    "raw_request_id": _text(
                        request.get("request_id"), "raw recovery request_id"
                    ),
                    "market_status": status,
                    "result_text": result_text,
                    "outcome": "1" if result_text == "yes" else "0",
                }
                previous = recovered.get(ticker)
                if previous is not None:
                    if (
                        previous["outcome"] != row["outcome"]
                        or previous["result_text"] != row["result_text"]
                    ):
                        _error(f"conflicting terminal recovered outcomes for {ticker}")
                    continue
                recovered[ticker] = row
    rows = tuple(recovered[key] for key in sorted(recovered))
    _validate_terminal_outcomes(
        rows,
        terminal_freeze=terminal_freeze,
        require_complete=False,
    )
    return rows
