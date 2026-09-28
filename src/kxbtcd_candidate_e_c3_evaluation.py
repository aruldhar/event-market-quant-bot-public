"""Checkpoint 21H-A/21H-B Candidate-E C3 evaluator implementation.

Checkpoint 21H-A freezes the exact bytes that may later open C3 outcomes.
Checkpoint 21H-B is the one-time final historical C3 outcome evaluation.

Safety invariants:
* C3 is the only allowed outcome identity set.
* H1/H2/H3/C1/C2 event and market identities are hard denied.
* Champion-R2 is applied exactly as frozen; no fitting, tuning, selection,
  feature change, or hyperparameter search is allowed on C3.
* The complete C3 cohort is marked permanently exposed before the first HTTP
  client is constructed.
* A fresh second C3 attempt is prohibited; only a validated resume of the same
  interrupted attempt is allowed.
* The remaining historical reserve is not materialized or outcome-opened.
* There is no order-placement, cancellation, transfer, demo, paper, or
  real-money execution path in this module.
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

from .kxbtcd_candidate_e_c1_evaluation import load_and_validate_c1_frozen_data
from .kxbtcd_candidate_e_c2_evaluation import load_and_validate_c2_frozen_data
from .kxbtcd_candidate_e_c3_preparation import (
    C1_RESULT_FINGERPRINT,
    C2_RESULT_FINGERPRINT,
    C3_ELIGIBLE_EVENT_TARGET,
    C3_EVENTS_PER_SUBBLOCK,
    C3_FROZEN_ROOT,
    C3_SUBBLOCK_COUNT,
    C3_VALIDATION_FREEZE_PATH,
    DISTANCE_CANDIDATE_ID,
    FAMILY_ID,
    PARENT_21A_PROTOCOL_FINGERPRINT,
    PARENT_H3_RESULT_FINGERPRINT,
    load_and_validate_r2_model,
)
from .kxbtcd_candidate_e_h1_evaluation import load_and_validate_frozen_universe
from .kxbtcd_candidate_e_predeclaration import market_logit_offset

CP21H_A_PARENT_RECEIPT_COMMIT = "8e0c94ec66bcb6113afcab465b8a60b11c6acfac"
CP21G_C_CHECKPOINT_COMMIT = "c5243578e5a5dc08013ee13013f96f71f3290ddb"

CHAMPION_R2_FINGERPRINT = "2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964"
CHAMPION_R2_BETA_DISTANCE = "0.014501283346050064"

C3_VALIDATION_FINGERPRINT = "44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0"
C3_COHORT_FINGERPRINT = "08add4c28831c0d460dff706b0cc425550a4d5d3f486d3ec7f14622586101f6b"
C3_ROW_FINGERPRINT = "898400f7401ef9a96a9c1a0a6d2c99479395ff9fb0a13d93ea7c5fbc3dad51db"
C3_ROW_COUNT = 13549
C3_MARKET_COUNT = 2470
C3_MATERIALIZED_IDENTITY_COUNT = 533
C3_STRICT_TAIL_START_INDEX = 4222
C3_STRICT_TAIL_END_EXCLUSIVE = 4755
C3_STRICT_TAIL_REMAINING = 4676
C3_STRICT_TAIL_FLOOR = 4500

C3_BLOCKS = tuple(f"B{i}" for i in range(C3_SUBBLOCK_COUNT))

C3_IMPLEMENTATION_FREEZE_SCHEMA_VERSION = (
    "kxbtcd_candidate_e_c3_evaluator_implementation_freeze.v1"
)
C3_OUTCOME_SCHEMA_VERSION = "kxbtcd_candidate_e_c3_outcome.v1"
C3_ATTEMPT_SCHEMA_VERSION = "kxbtcd_candidate_e_c3_attempt.v1"
C3_SUMMARY_SCHEMA_VERSION = "kxbtcd_candidate_e_c3_evaluation_summary.v1"
C3_BLOCK_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_e_c3_block_score.v1"
C3_PREDICTION_SCHEMA_VERSION = "kxbtcd_candidate_e_c3_prediction.v1"
C3_EVENT_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_e_c3_event_score.v1"

CP21H_B_COLLECTOR_NAME = "collect_kxbtcd_candidate_e_c3"
DEFAULT_C3_IMPLEMENTATION_FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_e_c3_evaluator_implementation_freeze.json"
)
DEFAULT_C3_ATTEMPT_PATH = Path(
    "data/analysis/kxbtcd_candidate_e_c3_evaluation/c3_attempt.json"
)
DERIVED_ROOT = Path("data/derived/kxbtcd_candidate_e_c3_evaluation")
MANIFEST_ROOT = Path("data/manifests")
C3_COHORT_PATH = C3_FROZEN_ROOT / "c3_cohort_map.csv"
C3_ROWS_PATH = C3_FROZEN_ROOT / "c3_preoutcome_rows.csv"
C3_SUMMARY_PATH = C3_FROZEN_ROOT / "c3_preoutcome_freeze_summary.json"

C3_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_c3_evaluation.py",
    "collect_kxbtcd_candidate_e_c3.py",
)

REQUIRED_21H_A_CLOSEOUT_PATHS = frozenset(
    {
        "configs/kxbtcd_candidate_e_c3_evaluator_implementation_freeze.json",
        "collect_kxbtcd_candidate_e_c3.py",
        "freeze_kxbtcd_candidate_e_c3_evaluator_implementation.py",
        "src/kxbtcd_candidate_e_c3_evaluation.py",
        "tests/test_kxbtcd_candidate_e_c3_evaluation.py",
        "validate_kxbtcd_candidate_e_c3_evaluator_implementation_freeze.py",
    }
)

FREEZE_BUNDLE_UNTRACKED_PATHS = frozenset(
    {
        *C3_IMPLEMENTATION_FILES,
        "configs/kxbtcd_candidate_e_c3_evaluator_implementation_freeze.json",
        "freeze_kxbtcd_candidate_e_c3_evaluator_implementation.py",
        "validate_kxbtcd_candidate_e_c3_evaluator_implementation_freeze.py",
        "tests/test_kxbtcd_candidate_e_c3_evaluation.py",
        "docs/KXBTCD_CANDIDATE_E_C3_EVALUATOR_IMPLEMENTATION_FREEZE.md",
        "scripts/apply_checkpoint21h_a_docs.py",
        "README_CHECKPOINT21H_A.txt",
    }
)

EXPECTED_GATE = {
    "beta_distance": "finite, converged, >0",
    "chronological_subblock_log_loss_wins": ">=4/5",
    "median_event_raw_minus_champion_log_loss_delta": ">0",
    "newest_subblock_log_loss_win": True,
    "policy_lineage_source_timing_firewall": "PASS",
    "pooled_raw_minus_champion_event_equal_brier_delta": ">=0",
    "pooled_raw_minus_champion_event_equal_log_loss_delta": ">0",
    "primary_tie": "FAIL",
    "structural_coverage": "all five structural roles and all six TTC targets",
}

C3_OUTCOME_FIELDS = (
    "schema_version",
    "family_id",
    "c3_validation_fingerprint",
    "c3_implementation_fingerprint",
    "champion_r2_fingerprint",
    "c3_cohort_fingerprint",
    "c3_preoutcome_row_fingerprint",
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

C3_BLOCK_SCORE_FIELDS = (
    "schema_version",
    "family_id",
    "candidate_id",
    "c3_validation_fingerprint",
    "champion_r2_fingerprint",
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

C3_PREDICTION_FIELDS = (
    "schema_version",
    "family_id",
    "candidate_id",
    "c3_validation_fingerprint",
    "champion_r2_fingerprint",
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

C3_EVENT_SCORE_FIELDS = (
    "schema_version",
    "family_id",
    "candidate_id",
    "c3_validation_fingerprint",
    "champion_r2_fingerprint",
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


class CandidateEC3EvaluationError(RuntimeError):
    """Raised when a C3 implementation/evaluation invariant fails."""


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
class C3FrozenData:
    cohort_rows: tuple[dict[str, Any], ...]
    preoutcome_rows: tuple[dict[str, Any], ...]
    event_block_map: dict[str, str]
    request_plan: dict[str, str]


@dataclass(frozen=True)
class C3Preflight:
    repository_root: Path
    git_head: str
    implementation_freeze: dict[str, Any]
    validation_freeze: dict[str, Any]
    champion_r2: dict[str, Any]
    frozen_data: C3FrozenData
    prior_events: frozenset[str]
    prior_markets: frozenset[str]
    attempt_path: Path


@dataclass(frozen=True)
class C3Evaluation:
    summary: dict[str, Any]
    block_rows: tuple[dict[str, str], ...]
    prediction_rows: tuple[dict[str, str], ...]
    event_score_rows: tuple[dict[str, str], ...]


def _error(message: str) -> None:
    raise CandidateEC3EvaluationError(message)


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
        raise CandidateEC3EvaluationError(f"could not read JSON {path}: {exc}") from exc
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
        raise CandidateEC3EvaluationError(f"could not read CSV {path}: {exc}") from exc


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
    for relative in C3_IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"C3 evaluator implementation file missing: {relative}")
        result[relative] = _sha256_file(path)
    return result


def _c3_request_plan(validation_freeze: Mapping[str, Any]) -> dict[str, str]:
    raw = validation_freeze.get("c3_outcome_request_plan")
    if not isinstance(raw, list) or len(raw) != C3_MARKET_COUNT:
        _error("C3 request plan count changed")
    plan: dict[str, str] = {}
    events: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {
            "event_ticker",
            "market_ticker",
        }:
            _error(f"C3 request plan entry {index} schema changed")
        event = str(item["event_ticker"])
        market = str(item["market_ticker"])
        if not event or not market:
            _error(f"C3 request plan entry {index} has blank identity")
        if market in plan:
            _error(f"duplicate C3 planned market {market}")
        plan[market] = event
        events.add(event)
    if len(events) != C3_ELIGIBLE_EVENT_TARGET:
        _error(f"C3 request plan event count changed: {len(events)}")
    return plan


def validate_c3_validation_freeze_document(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    expected = {
        "schema_version": "kxbtcd_candidate_e_c3_validation_freeze.v1",
        "checkpoint_id": "21G-C",
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "C3_event_count": C3_ELIGIBLE_EVENT_TARGET,
        "C3_subblocks": list(C3_BLOCKS),
        "C3_events_per_subblock": C3_EVENTS_PER_SUBBLOCK,
        "strict_tail_start_index": C3_STRICT_TAIL_START_INDEX,
        "strict_tail_end_index_exclusive_after_C3": C3_STRICT_TAIL_END_EXCLUSIVE,
        "candidate_identities_materialized_for_C3": C3_MATERIALIZED_IDENTITY_COUNT,
        "strict_untouched_tail_remaining_after_C3": C3_STRICT_TAIL_REMAINING,
        "minimum_strict_untouched_tail_after_all_confirmation": C3_STRICT_TAIL_FLOOR,
        "c3_cohort_fingerprint": C3_COHORT_FINGERPRINT,
        "c3_preoutcome_row_fingerprint": C3_ROW_FINGERPRINT,
        "c3_preoutcome_row_count": C3_ROW_COUNT,
        "c3_unique_market_count": C3_MARKET_COUNT,
        "C3_outcomes_opened": False,
        "candidate_selection_performed": False,
        "feature_or_hyperparameter_change_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
        "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"C3 validation freeze {key} mismatch")
    if document.get("gate") != EXPECTED_GATE:
        _error("C3 frozen gate changed")
    _c3_request_plan(document)
    payload = {
        key: document[key]
        for key in document
        if key != "c3_validation_fingerprint"
    }
    if _canonical_sha256(payload) != C3_VALIDATION_FINGERPRINT:
        _error("C3 validation canonical fingerprint mismatch")
    return dict(document)


def load_and_validate_c3_validation_freeze(
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    return validate_c3_validation_freeze_document(
        _read_json(repo / C3_VALIDATION_FREEZE_PATH)
    )


def _normalized_cohort_rows(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "schema_version": row["schema_version"],
                "stage": row["stage"],
                "block_id": row["block_id"],
                "event_rank_zero_based": int(row["event_rank_zero_based"]),
                "event_ticker": row["event_ticker"],
                "event_close_time_utc": row["event_close_time_utc"],
                "queue_index_zero_based": int(row["queue_index_zero_based"]),
            }
        )
    return normalized


def _normalized_preoutcome_rows(
    rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for source in rows:
        row: dict[str, Any] = dict(source)
        row["c3_event_rank_zero_based"] = int(row["c3_event_rank_zero_based"])
        normalized.append(row)
    return normalized


def load_and_validate_c3_frozen_data(
    repository_root: str | Path = ".",
    *,
    validation_freeze: Mapping[str, Any] | None = None,
) -> C3FrozenData:
    repo = Path(repository_root).resolve()
    freeze = (
        dict(validation_freeze)
        if validation_freeze is not None
        else load_and_validate_c3_validation_freeze(repo)
    )
    plan = _c3_request_plan(freeze)

    summary = _read_json(repo / C3_SUMMARY_PATH)
    if summary != freeze:
        _error("C3 local pre-outcome summary differs from tracked validation freeze")

    _, cohort_rows = _read_csv(repo / C3_COHORT_PATH)
    if len(cohort_rows) != C3_ELIGIBLE_EVENT_TARGET:
        _error(f"C3 cohort row count changed: {len(cohort_rows)}")
    normalized_cohort = _normalized_cohort_rows(cohort_rows)
    if _canonical_sha256(normalized_cohort) != C3_COHORT_FINGERPRINT:
        _error("C3 cohort CSV fingerprint changed")

    event_block: dict[str, str] = {}
    block_counts: dict[str, int] = {block: 0 for block in C3_BLOCKS}
    plan_events = set(plan.values())
    for rank, row in enumerate(normalized_cohort):
        if row["schema_version"] != "kxbtcd_candidate_e_c3_cohort.v1":
            _error("C3 cohort schema changed")
        if row["stage"] != "C3":
            _error("C3 cohort stage changed")
        if row["event_rank_zero_based"] != rank:
            _error("C3 cohort rank is not contiguous")
        expected_block = f"B{rank // C3_EVENTS_PER_SUBBLOCK}"
        if row["block_id"] != expected_block:
            _error(f"C3 cohort block changed at rank {rank}")
        queue_index = int(row["queue_index_zero_based"])
        if not C3_STRICT_TAIL_START_INDEX <= queue_index < C3_STRICT_TAIL_END_EXCLUSIVE:
            _error("C3 cohort queue identity moved outside frozen range")
        event = str(row["event_ticker"])
        if event in event_block:
            _error(f"duplicate C3 cohort event {event}")
        event_block[event] = expected_block
        block_counts[expected_block] += 1
    if block_counts != {block: C3_EVENTS_PER_SUBBLOCK for block in C3_BLOCKS}:
        _error(f"C3 block counts changed: {block_counts}")
    if set(event_block) != plan_events:
        _error("C3 cohort event set differs from outcome request plan")

    _, preoutcome_rows = _read_csv(repo / C3_ROWS_PATH)
    if len(preoutcome_rows) != C3_ROW_COUNT:
        _error(f"C3 pre-outcome row count changed: {len(preoutcome_rows)}")
    normalized_rows = _normalized_preoutcome_rows(preoutcome_rows)
    if _canonical_sha256(normalized_rows) != C3_ROW_FINGERPRINT:
        _error("C3 pre-outcome row fingerprint changed")

    required_roles = {"q10", "q30", "q50", "q70", "q90"}
    required_ttc = {55, 50, 45, 40, 35, 30}
    block_roles: dict[str, set[str]] = {block: set() for block in C3_BLOCKS}
    block_ttc: dict[str, set[int]] = {block: set() for block in C3_BLOCKS}
    observed_markets: dict[str, str] = {}
    state_ids: set[str] = set()
    for index, row in enumerate(normalized_rows):
        if row.get("stage") != "C3":
            _error(f"C3 pre-outcome row {index} stage changed")
        event = str(row.get("event_ticker") or "")
        market = str(row.get("market_ticker") or "")
        block = str(row.get("block_id") or "")
        if event_block.get(event) != block:
            _error(f"C3 row {index} event/block mismatch")
        if plan.get(market) != event:
            _error(f"C3 row {index} market is outside exact request plan")
        rank = int(row["c3_event_rank_zero_based"])
        if rank < 0 or rank >= C3_ELIGIBLE_EVENT_TARGET:
            _error(f"C3 row {index} rank out of range")
        if not all(
            math.isfinite(float(row[field]))
            for field in ("q_market", "d_BTC")
        ):
            _error(f"C3 row {index} has non-finite model input")
        role = str(row["structural_role"])
        ttc = int(row["ttc_target_minutes"])
        block_roles[block].add(role)
        block_ttc[block].add(ttc)
        previous = observed_markets.setdefault(market, event)
        if previous != event:
            _error(f"C3 market maps to multiple events: {market}")
        state_id = f"{event}|{market}|TTC{ttc}|{role}"
        if state_id in state_ids:
            _error(f"duplicate C3 state identity {state_id}")
        state_ids.add(state_id)

    if observed_markets != plan:
        _error("C3 row market/event mapping differs from request plan")
    for block in C3_BLOCKS:
        if block_roles[block] != required_roles:
            _error(f"C3 {block} structural-role coverage changed")
        if block_ttc[block] != required_ttc:
            _error(f"C3 {block} TTC coverage changed")

    return C3FrozenData(
        cohort_rows=tuple(dict(row) for row in normalized_cohort),
        preoutcome_rows=tuple(dict(row) for row in normalized_rows),
        event_block_map=event_block,
        request_plan=plan,
    )


def _prior_exposed_identity_sets(
    repository_root: str | Path = ".",
) -> tuple[frozenset[str], frozenset[str]]:
    repo = Path(repository_root).resolve()
    universe = load_and_validate_frozen_universe(repo)
    c1 = load_and_validate_c1_frozen_data(repo)
    c2 = load_and_validate_c2_frozen_data(repo)

    prior_events = {
        str(row["event_ticker"])
        for row in universe.cohort_rows
    }
    prior_events.update(
        str(row["event_ticker"])
        for row in c1.cohort_rows
    )
    prior_events.update(
        str(row["event_ticker"])
        for row in c2.cohort_rows
    )
    prior_markets = {
        str(row["market_ticker"])
        for row in universe.preoutcome_rows
    }
    prior_markets.update(
        str(row["market_ticker"])
        for row in c1.preoutcome_rows
    )
    prior_markets.update(
        str(row["market_ticker"])
        for row in c2.preoutcome_rows
    )

    if len(prior_events) != 4000:
        _error(
            "H1/H2/H3/C1/C2 hard-deny event count changed: "
            f"{len(prior_events)}"
        )
    if not prior_markets:
        _error("H1/H2/H3/C1/C2 hard-deny market set is empty")
    return frozenset(prior_events), frozenset(prior_markets)


def assert_not_prior_exposed_identity(
    *,
    prior_events: frozenset[str],
    prior_markets: frozenset[str],
    event_ticker: str,
    market_ticker: str,
) -> None:
    if event_ticker in prior_events:
        _error(
            "H1/H2/H3/C1/C2 event identity prohibited in C3 path: "
            f"{event_ticker}"
        )
    if market_ticker in prior_markets:
        _error(
            "H1/H2/H3/C1/C2 market identity prohibited in C3 path: "
            f"{market_ticker}"
        )


def _parent_documents(
    repo: Path,
    *,
    verify_local_frozen_data: bool,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    C3FrozenData | None,
    frozenset[str],
    frozenset[str],
]:
    validation_freeze = load_and_validate_c3_validation_freeze(repo)
    champion = load_and_validate_r2_model(repo)
    if champion.get("champion_r2_fingerprint") != CHAMPION_R2_FINGERPRINT:
        _error("Champion-R2 fingerprint changed")
    if str(champion.get("model", {}).get("beta_distance")) != CHAMPION_R2_BETA_DISTANCE:
        _error("Champion-R2 beta_distance changed")

    frozen_data = (
        load_and_validate_c3_frozen_data(
            repo,
            validation_freeze=validation_freeze,
        )
        if verify_local_frozen_data
        else None
    )
    prior_events, prior_markets = _prior_exposed_identity_sets(repo)

    plan = _c3_request_plan(validation_freeze)
    if set(plan.values()) & set(prior_events):
        _error("C3 event plan overlaps H1/H2/H3/C1/C2 exposed events")
    if set(plan) & set(prior_markets):
        _error("C3 market plan overlaps H1/H2/H3/C1/C2 exposed markets")

    return (
        validation_freeze,
        champion,
        frozen_data,
        prior_events,
        prior_markets,
    )


def _validate_21g_c_receipt(repo: Path) -> dict[str, Any]:
    receipt = _read_json(repo / "docs/LAST_CHECKPOINT_CLOSEOUT.json")
    if receipt.get("checkpoint_commit") != CP21G_C_CHECKPOINT_COMMIT:
        _error("latest closeout does not record the exact Checkpoint-21G-C commit")
    if receipt.get("checkpoint_message") != (
        "Checkpoint 21G-C: freeze Candidate-E C3 pre-outcome cohort"
    ):
        _error("latest closeout Checkpoint-21G-C message changed")
    committed = set(receipt.get("committed_paths") or ())
    required = {
        "configs/kxbtcd_candidate_e_c3_validation_freeze.json",
        "docs/AI_HANDOFF.md",
        "docs/BACKLOG.md",
        "docs/DECISIONS.md",
        "docs/EXPERIMENT_LOG.md",
        "docs/LEARNING_GUIDE.md",
        "docs/PROJECT_STATE.md",
    }
    if not required.issubset(committed):
        _error("latest closeout does not contain the complete C3 pre-outcome freeze")
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
            _error(f"latest Checkpoint-21G-C safety field {key} did not PASS")
    return receipt


def assert_21g_c_parent_baseline_for_freeze(
    repository_root: str | Path = ".",
) -> str:
    """Require exact 21G-C remote baseline before creating evaluator freeze."""
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("Checkpoint-21H-A freeze requires branch main")

    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != CP21H_A_PARENT_RECEIPT_COMMIT or remote != CP21H_A_PARENT_RECEIPT_COMMIT:
        _error(
            "Checkpoint-21H-A parent mismatch; expected HEAD == origin/main == "
            f"{CP21H_A_PARENT_RECEIPT_COMMIT}, got HEAD={head}, origin/main={remote}"
        )

    if _git(repo, "diff", "--name-only"):
        _error("tracked unstaged changes existed before Checkpoint-21H-A freeze")
    if _git(repo, "diff", "--cached", "--name-only"):
        _error("staged changes existed before Checkpoint-21H-A freeze")

    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
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
            "unexpected worktree state before Checkpoint-21H-A freeze; "
            f"first unexpected line: {unexpected[0]}"
        )

    _validate_21g_c_receipt(repo)
    _parent_documents(repo, verify_local_frozen_data=True)
    return head


def build_c3_implementation_freeze_document(
    *,
    repo: Path,
    source_baseline_commit: str,
) -> dict[str, Any]:
    (
        validation_freeze,
        _champion,
        _frozen,
        prior_events,
        prior_markets,
    ) = _parent_documents(repo, verify_local_frozen_data=True)

    payload = {
        "schema_version": C3_IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21H-A",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
        "c3_cohort_fingerprint": C3_COHORT_FINGERPRINT,
        "c3_preoutcome_row_fingerprint": C3_ROW_FINGERPRINT,
        "C3_identity": {
            "event_count": C3_ELIGIBLE_EVENT_TARGET,
            "row_count": C3_ROW_COUNT,
            "market_count": C3_MARKET_COUNT,
            "blocks": {
                block: C3_EVENTS_PER_SUBBLOCK
                for block in C3_BLOCKS
            },
            "candidate_identities_materialized": C3_MATERIALIZED_IDENTITY_COUNT,
            "strict_tail_start_index": C3_STRICT_TAIL_START_INDEX,
            "strict_tail_end_index_exclusive": C3_STRICT_TAIL_END_EXCLUSIVE,
            "strict_untouched_tail_remaining": C3_STRICT_TAIL_REMAINING,
            "strict_untouched_tail_floor": C3_STRICT_TAIL_FLOOR,
            "reserve_floor_buffer": (
                C3_STRICT_TAIL_REMAINING - C3_STRICT_TAIL_FLOOR
            ),
        },
        "H1_H2_H3_C1_C2_hard_deny_identity": {
            "event_count": len(prior_events),
            "market_count": len(prior_markets),
            "event_identity_fingerprint": _canonical_sha256(sorted(prior_events)),
            "market_identity_fingerprint": _canonical_sha256(sorted(prior_markets)),
        },
        "outcome_source": {
            "endpoint_template": "/historical/markets/{market_ticker}",
            "required_market_status": "finalized",
            "accepted_results": ["yes", "no"],
            "raw_first_persistence_required": True,
            "authentication_required": False,
        },
        "evaluation_contract": {
            "benchmark": "raw_kalshi_midpoint",
            "candidate": DISTANCE_CANDIDATE_ID,
            "beta_distance": CHAMPION_R2_BETA_DISTANCE,
            "event_weighting": "equal_total_weight_per_event",
            "within_event_weighting": "equal_weight_per_scored_row",
            "gate": dict(validation_freeze["gate"]),
            "model_parameters_fitted_on_C3": False,
            "candidate_selection_on_C3_allowed": False,
            "feature_change_on_C3_allowed": False,
            "hyperparameter_search_on_C3_allowed": False,
        },
        "exposure_policy": {
            "permanently_expose_full_C3_before_first_request": True,
            "fresh_second_C3_attempt_allowed": False,
            "resume_only_after_interruption": True,
            "future_untouched_claim_on_C3_allowed": False,
            "H1_H2_H3_C1_C2_event_and_market_identities_hard_denied": True,
            "additional_historical_reserve_materialization_allowed": False,
            "remaining_reserve_outcome_access_allowed": False,
        },
        "implementation_sha256s": _implementation_sha256s(repo),
        "source_baseline_commit": source_baseline_commit,
        "procedure_derivation_used_C3_outcomes": False,
        "C3_outcomes_opened_at_freeze": 0,
        "model_fit_performed_at_freeze": False,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["c3_implementation_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_c3_implementation_freeze_document(
    document: Mapping[str, Any],
    *,
    repo: Path,
    verify_parent: bool = True,
    verify_implementation_hashes: bool = True,
    verify_local_frozen_data: bool = False,
) -> dict[str, Any]:
    expected = {
        "schema_version": C3_IMPLEMENTATION_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21H-A",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
        "c3_cohort_fingerprint": C3_COHORT_FINGERPRINT,
        "c3_preoutcome_row_fingerprint": C3_ROW_FINGERPRINT,
        "source_baseline_commit": CP21H_A_PARENT_RECEIPT_COMMIT,
        "procedure_derivation_used_C3_outcomes": False,
        "C3_outcomes_opened_at_freeze": 0,
        "model_fit_performed_at_freeze": False,
        "network_requests_at_freeze": 0,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"C3 implementation freeze {key} mismatch")

    identity = document.get("C3_identity")
    if not isinstance(identity, Mapping):
        _error("C3 implementation identity missing")
    if (
        identity.get("event_count"),
        identity.get("row_count"),
        identity.get("market_count"),
    ) != (
        C3_ELIGIBLE_EVENT_TARGET,
        C3_ROW_COUNT,
        C3_MARKET_COUNT,
    ):
        _error("C3 implementation identity counts changed")
    if identity.get("blocks") != {
        block: C3_EVENTS_PER_SUBBLOCK
        for block in C3_BLOCKS
    }:
        _error("C3 implementation block sizes changed")
    if (
        identity.get("strict_tail_start_index"),
        identity.get("strict_tail_end_index_exclusive"),
        identity.get("strict_untouched_tail_remaining"),
        identity.get("strict_untouched_tail_floor"),
        identity.get("reserve_floor_buffer"),
    ) != (
        C3_STRICT_TAIL_START_INDEX,
        C3_STRICT_TAIL_END_EXCLUSIVE,
        C3_STRICT_TAIL_REMAINING,
        C3_STRICT_TAIL_FLOOR,
        C3_STRICT_TAIL_REMAINING - C3_STRICT_TAIL_FLOOR,
    ):
        _error("C3 implementation reserve identity changed")

    exposure = document.get("exposure_policy")
    if not isinstance(exposure, Mapping):
        _error("C3 exposure policy missing")
    required_exposure = {
        "permanently_expose_full_C3_before_first_request": True,
        "fresh_second_C3_attempt_allowed": False,
        "resume_only_after_interruption": True,
        "future_untouched_claim_on_C3_allowed": False,
        "H1_H2_H3_C1_C2_event_and_market_identities_hard_denied": True,
        "additional_historical_reserve_materialization_allowed": False,
        "remaining_reserve_outcome_access_allowed": False,
    }
    for key, value in required_exposure.items():
        if exposure.get(key) != value:
            _error(f"C3 exposure policy {key} changed")

    evaluation = document.get("evaluation_contract")
    if not isinstance(evaluation, Mapping):
        _error("C3 evaluation contract missing")
    for key in (
        "model_parameters_fitted_on_C3",
        "candidate_selection_on_C3_allowed",
        "feature_change_on_C3_allowed",
        "hyperparameter_search_on_C3_allowed",
    ):
        if evaluation.get(key) is not False:
            _error(f"C3 evaluation contract {key} changed")
    if evaluation.get("gate") != EXPECTED_GATE:
        _error("C3 implementation gate changed")
    if evaluation.get("beta_distance") != CHAMPION_R2_BETA_DISTANCE:
        _error("C3 implementation beta_distance changed")

    if verify_implementation_hashes:
        if document.get("implementation_sha256s") != _implementation_sha256s(repo):
            _error("C3 evaluator implementation bytes differ from frozen hashes")

    if verify_parent:
        (
            validation_freeze,
            champion,
            _,
            prior_events,
            prior_markets,
        ) = _parent_documents(
            repo,
            verify_local_frozen_data=verify_local_frozen_data,
        )
        if validation_freeze["c3_validation_fingerprint"] != C3_VALIDATION_FINGERPRINT:
            _error("C3 implementation validation lineage mismatch")
        if champion["champion_r2_fingerprint"] != CHAMPION_R2_FINGERPRINT:
            _error("C3 implementation model lineage mismatch")
        deny = document.get("H1_H2_H3_C1_C2_hard_deny_identity")
        if not isinstance(deny, Mapping):
            _error("H1/H2/H3/C1/C2 hard-deny identity missing")
        if deny.get("event_count") != len(prior_events):
            _error("H1/H2/H3/C1/C2 hard-deny event count mismatch")
        if deny.get("market_count") != len(prior_markets):
            _error("H1/H2/H3/C1/C2 hard-deny market count mismatch")
        if deny.get("event_identity_fingerprint") != _canonical_sha256(
            sorted(prior_events)
        ):
            _error("H1/H2/H3/C1/C2 hard-deny event fingerprint mismatch")
        if deny.get("market_identity_fingerprint") != _canonical_sha256(
            sorted(prior_markets)
        ):
            _error("H1/H2/H3/C1/C2 hard-deny market fingerprint mismatch")

    payload = {
        key: document[key]
        for key in document
        if key != "c3_implementation_fingerprint"
    }
    if document.get("c3_implementation_fingerprint") != _canonical_sha256(payload):
        _error("C3 implementation fingerprint mismatch")
    return dict(document)


def write_or_validate_c3_implementation_freeze(
    path: str | Path = DEFAULT_C3_IMPLEMENTATION_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    baseline = assert_21g_c_parent_baseline_for_freeze(repo)
    target = Path(path)
    if not target.is_absolute():
        target = repo / target

    document = build_c3_implementation_freeze_document(
        repo=repo,
        source_baseline_commit=baseline,
    )
    validate_c3_implementation_freeze_document(
        document,
        repo=repo,
        verify_parent=True,
        verify_implementation_hashes=True,
        verify_local_frozen_data=True,
    )

    if target.exists():
        existing = _read_json(target)
        validate_c3_implementation_freeze_document(
            existing,
            repo=repo,
            verify_parent=True,
            verify_implementation_hashes=True,
            verify_local_frozen_data=True,
        )
        if existing != document:
            _error("existing C3 evaluator freeze differs; refusing overwrite")
        return target, existing

    _write_json_atomic(target, document)
    return target, document


def validate_c3_implementation_freeze(
    *,
    repository_root: str | Path = ".",
    verify_local_frozen_data: bool = True,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    document = _read_json(repo / DEFAULT_C3_IMPLEMENTATION_FREEZE_PATH)
    return validate_c3_implementation_freeze_document(
        document,
        repo=repo,
        verify_parent=True,
        verify_implementation_hashes=True,
        verify_local_frozen_data=verify_local_frozen_data,
    )


def assert_clean_synchronized_repository(
    repository_root: str | Path = ".",
) -> str:
    """Runtime gate used immediately before committing C3 exposure."""
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("C3 exposure requires branch main")

    status = _git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status:
        _error(
            "C3 exposure requires a completely clean worktree/index; "
            f"first dirty line: {status.splitlines()[0]}"
        )

    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != remote:
        _error(
            "C3 exposure requires HEAD == origin/main after fresh fetch; "
            f"HEAD={head}, origin/main={remote}"
        )

    receipt = _read_json(repo / "docs/LAST_CHECKPOINT_CLOSEOUT.json")
    if receipt.get("baseline_commit") != CP21H_A_PARENT_RECEIPT_COMMIT:
        _error(
            "latest closeout is not the direct Checkpoint-21H-A child "
            "of the accepted 21G-C receipt"
        )
    if receipt.get("checkpoint_message") != (
        "Checkpoint 21H-A: freeze Candidate-E C3 evaluator implementation"
    ):
        _error("latest closeout message is not Checkpoint 21H-A")
    committed = set(receipt.get("committed_paths") or ())
    missing = REQUIRED_21H_A_CLOSEOUT_PATHS - committed
    if missing:
        _error(
            "latest closeout does not contain required Checkpoint-21H-A paths: "
            f"{sorted(missing)}"
        )
    safety = receipt.get("safety")
    if not isinstance(safety, Mapping):
        _error("latest closeout safety record missing")
    if (
        safety.get("staged_diff_check") != "PASS"
        or safety.get("high_confidence_secret_scan") != "PASS"
    ):
        _error("latest Checkpoint-21H-A closeout safety checks did not pass")
    return head


def matching_prior_c3_manifests(
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
        if (
            not isinstance(collector, Mapping)
            or collector.get("name") != CP21H_B_COLLECTOR_NAME
        ):
            continue
        if not isinstance(arguments, Mapping):
            continue
        if arguments.get("c3_validation_fingerprint") != C3_VALIDATION_FINGERPRINT:
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches))


def _create_or_validate_c3_attempt(
    *,
    path: Path,
    implementation_freeze: Mapping[str, Any],
    git_head: str,
    resume_manifest: Path | None,
) -> dict[str, Any]:
    fingerprint = str(
        implementation_freeze["c3_implementation_fingerprint"]
    )
    if path.exists():
        attempt = _read_json(path)
        expected = {
            "schema_version": C3_ATTEMPT_SCHEMA_VERSION,
            "checkpoint_id": "21H-B",
            "candidate_id": DISTANCE_CANDIDATE_ID,
            "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
            "c3_implementation_fingerprint": fingerprint,
            "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
            "C3_permanently_exposed": True,
            "fresh_second_C3_attempt_allowed": False,
            "execution_enabled": False,
            "orders_placed": 0,
        }
        for key, value in expected.items():
            if attempt.get(key) != value:
                _error(f"C3 attempt receipt {key} mismatch")
        if resume_manifest is None:
            _error(
                "C3 attempt receipt already exists; "
                "fresh second C3 attempt is prohibited"
            )
        return attempt

    if resume_manifest is not None:
        _error("cannot resume C3 without an existing C3 exposure receipt")

    attempt = {
        "schema_version": C3_ATTEMPT_SCHEMA_VERSION,
        "checkpoint_id": "21H-B",
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
        "c3_implementation_fingerprint": fingerprint,
        "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "status": "c3_exposure_committed",
        "created_at_utc": _utc_now_text(),
        "git_head_at_exposure": git_head,
        "C3_permanently_exposed": True,
        "fresh_second_C3_attempt_allowed": False,
        "resume_only_after_interruption": True,
        "remaining_reserve_accessed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    _write_json_atomic(path, attempt)
    return attempt


def update_c3_attempt_receipt(
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
    if status == "c3_evaluation_completed":
        updated["completed_at_utc"] = _utc_now_text()
    _write_json_atomic(path, updated)


def c3_preflight(
    *,
    repository_root: str | Path = ".",
    resume_manifest: str | Path | None = None,
) -> C3Preflight:
    repo = Path(repository_root).resolve()

    # Clean/sync, frozen lineage, allow-list, hard-deny, and the permanent
    # exposure receipt all happen before the caller may construct an HTTP client.
    git_head = assert_clean_synchronized_repository(repo)
    implementation_freeze = validate_c3_implementation_freeze(
        repository_root=repo,
        verify_local_frozen_data=True,
    )
    (
        validation_freeze,
        champion,
        frozen_data,
        prior_events,
        prior_markets,
    ) = _parent_documents(
        repo,
        verify_local_frozen_data=True,
    )
    assert frozen_data is not None

    prior = matching_prior_c3_manifests(repo)
    resume_path = (
        Path(resume_manifest).resolve()
        if resume_manifest is not None
        else None
    )
    if resume_path is None:
        if prior:
            _error(
                f"prior C3 exposure manifest exists; refusing fresh run: {prior[-1]}"
            )
    else:
        if resume_path not in prior:
            _error("resume manifest is not a recognized Candidate-E C3 manifest")
        manifest = _read_json(resume_path)
        if manifest.get("status") == "completed":
            _error("cannot resume a completed C3 evaluation")
        if manifest.get("status") not in {"running", "failed"}:
            _error(
                "resume manifest has unsupported status "
                f"{manifest.get('status')!r}"
            )

    attempt_path = repo / DEFAULT_C3_ATTEMPT_PATH
    _create_or_validate_c3_attempt(
        path=attempt_path,
        implementation_freeze=implementation_freeze,
        git_head=git_head,
        resume_manifest=resume_path,
    )

    return C3Preflight(
        repository_root=repo,
        git_head=git_head,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        champion_r2=champion,
        frozen_data=frozen_data,
        prior_events=prior_events,
        prior_markets=prior_markets,
        attempt_path=attempt_path,
    )


def validate_c3_outcomes(
    outcomes: Sequence[Mapping[str, str]],
    *,
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    prior_events: frozenset[str],
    prior_markets: frozenset[str],
    require_complete: bool,
) -> tuple[dict[str, str], ...]:
    plan = _c3_request_plan(validation_freeze)
    impl_fp = str(
        implementation_freeze["c3_implementation_fingerprint"]
    )
    expected_fields = set(C3_OUTCOME_FIELDS)
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []

    for index, source in enumerate(outcomes):
        row = dict(source)
        missing = expected_fields - set(row)
        extra = set(row) - expected_fields
        if missing or extra:
            _error(
                f"C3 outcome row {index} schema mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )

        expected = {
            "schema_version": C3_OUTCOME_SCHEMA_VERSION,
            "family_id": FAMILY_ID,
            "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
            "c3_implementation_fingerprint": impl_fp,
            "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
            "c3_cohort_fingerprint": C3_COHORT_FINGERPRINT,
            "c3_preoutcome_row_fingerprint": C3_ROW_FINGERPRINT,
            "stage": "C3",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                _error(f"C3 outcome row {index} {key} mismatch")

        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        assert_not_prior_exposed_identity(
            prior_events=prior_events,
            prior_markets=prior_markets,
            event_ticker=event,
            market_ticker=market,
        )
        if market in seen:
            _error(f"duplicate C3 outcome market {market}")
        seen.add(market)
        if plan.get(market) != event:
            _error(f"unplanned C3 outcome identity: {event}/{market}")
        if row["market_status"] != "finalized":
            _error(f"C3 market {market} is not finalized")
        if (row["result_text"], row["outcome"]) not in {
            ("yes", "1"),
            ("no", "0"),
        }:
            _error(f"C3 result/outcome mismatch for {market}")
        for field in (
            "raw_source",
            "raw_session_id",
            "raw_request_id",
        ):
            if not str(row[field]).strip():
                _error(f"C3 outcome row {index} {field} is blank")
        normalized.append(row)

    if require_complete and seen != set(plan):
        missing = sorted(set(plan) - seen)
        _error(
            f"C3 outcome set incomplete: missing {len(missing)} markets; "
            f"first={missing[:5]}"
        )
    return tuple(normalized)


def collect_c3_outcomes(
    client: RawFirstJsonClient,
    *,
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    prior_events: frozenset[str],
    prior_markets: frozenset[str],
    existing_outcomes: Sequence[Mapping[str, str]] = (),
    on_outcome: Callable[[dict[str, str]], None] | None = None,
) -> tuple[dict[str, str], ...]:
    existing = validate_c3_outcomes(
        existing_outcomes,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        prior_events=prior_events,
        prior_markets=prior_markets,
        require_complete=False,
    )
    by_market = {
        row["market_ticker"]: dict(row)
        for row in existing
    }
    plan = _c3_request_plan(validation_freeze)
    impl_fp = str(
        implementation_freeze["c3_implementation_fingerprint"]
    )

    for market_ticker in sorted(plan):
        if market_ticker in by_market:
            continue
        event_ticker = plan[market_ticker]
        assert_not_prior_exposed_identity(
            prior_events=prior_events,
            prior_markets=prior_markets,
            event_ticker=event_ticker,
            market_ticker=market_ticker,
        )

        response = client.get_json(
            f"/historical/markets/{market_ticker}"
        )
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            _error(f"C3 response for {market_ticker} missing market object")

        returned_ticker = str(market.get("ticker") or "").strip()
        returned_event = str(market.get("event_ticker") or "").strip()
        if not returned_ticker or not returned_event:
            _error(
                f"C3 response for {market_ticker} missing returned identity"
            )

        assert_not_prior_exposed_identity(
            prior_events=prior_events,
            prior_markets=prior_markets,
            event_ticker=returned_event,
            market_ticker=returned_ticker,
        )
        if returned_ticker != market_ticker or returned_event != event_ticker:
            _error(
                "C3 outcome identity mismatch for requested market "
                f"{market_ticker}"
            )

        status = str(market.get("status") or "").strip().lower()
        result_text = str(market.get("result") or "").strip().lower()
        if status != "finalized":
            _error(
                f"C3 market {market_ticker} is not finalized: {status!r}"
            )
        if result_text not in {"yes", "no"}:
            _error(
                f"C3 market {market_ticker} unsupported result {result_text!r}"
            )

        row = {
            "schema_version": C3_OUTCOME_SCHEMA_VERSION,
            "family_id": FAMILY_ID,
            "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
            "c3_implementation_fingerprint": impl_fp,
            "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
            "c3_cohort_fingerprint": C3_COHORT_FINGERPRINT,
            "c3_preoutcome_row_fingerprint": C3_ROW_FINGERPRINT,
            "stage": "C3",
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

    ordered = [
        by_market[market]
        for market in sorted(plan)
    ]
    return validate_c3_outcomes(
        ordered,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        prior_events=prior_events,
        prior_markets=prior_markets,
        require_complete=True,
    )


def initialize_c3_outcome_journal(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    _write_csv(path, C3_OUTCOME_FIELDS, ())


def append_c3_outcome_journal(
    path: Path,
    row: Mapping[str, Any],
) -> None:
    missing = set(C3_OUTCOME_FIELDS) - set(row)
    extra = set(row) - set(C3_OUTCOME_FIELDS)
    if missing or extra:
        _error(
            f"C3 journal row schema mismatch; "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(C3_OUTCOME_FIELDS),
            lineterminator="\n",
        )
        writer.writerow(
            {
                field: row[field]
                for field in C3_OUTCOME_FIELDS
            }
        )


def recover_c3_outcomes_from_manifest(
    *,
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    prior_events: frozenset[str],
    prior_markets: frozenset[str],
    repository_root: str | Path,
    manifest_path: str | Path,
) -> tuple[dict[str, str], ...]:
    repo = Path(repository_root).resolve()
    target = Path(manifest_path).resolve()
    document = _read_json(target)
    collector = document.get("collector")
    arguments = document.get("arguments")
    if (
        not isinstance(collector, Mapping)
        or collector.get("name") != CP21H_B_COLLECTOR_NAME
    ):
        _error("resume C3 manifest collector mismatch")
    if not isinstance(arguments, Mapping):
        _error("resume C3 manifest arguments missing")
    if arguments.get("c3_validation_fingerprint") != C3_VALIDATION_FINGERPRINT:
        _error("resume C3 manifest validation fingerprint mismatch")
    if (
        arguments.get("c3_implementation_fingerprint")
        != implementation_freeze.get("c3_implementation_fingerprint")
    ):
        _error("resume C3 manifest implementation fingerprint mismatch")

    run_id = str(document.get("run_id") or "").strip()
    if not run_id:
        _error("resume C3 manifest run_id missing")

    matches = list(
        (repo / DERIVED_ROOT).rglob(
            f"{run_id}_candidate_e_c3_outcome_journal.csv"
        )
    )
    if len(matches) != 1:
        _error(
            f"expected exactly one C3 outcome journal for {run_id}; "
            f"found {len(matches)}"
        )

    fields, rows = _read_csv(matches[0])
    if fields != C3_OUTCOME_FIELDS:
        _error("resume C3 outcome journal schema mismatch")
    return validate_c3_outcomes(
        rows,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        prior_events=prior_events,
        prior_markets=prior_markets,
        require_complete=False,
    )


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def predict_c3_probability(
    *,
    q_market: float,
    d_btc: float,
    beta_distance: float,
) -> float:
    if not all(
        math.isfinite(value)
        for value in (q_market, d_btc, beta_distance)
    ):
        _error("C3 prediction received non-finite input")
    if beta_distance <= 0.0:
        _error("C3 frozen beta_distance must be positive")
    return _sigmoid(
        market_logit_offset(q_market)
        + beta_distance * d_btc
    )


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
        event_losses.setdefault(event, []).append(
            _row_log_loss(probability, outcome)
        )
        event_briers.setdefault(event, []).append(
            _row_brier(probability, outcome)
        )

    if not event_losses:
        _error("C3 metric calculation received no events")

    event_metrics: dict[str, tuple[float, float, int]] = {}
    for event in event_losses:
        losses = event_losses[event]
        briers = event_briers[event]
        event_metrics[event] = (
            (
                sum(losses) / len(losses)
                if all(math.isfinite(value) for value in losses)
                else math.inf
            ),
            sum(briers) / len(briers),
            len(losses),
        )

    pooled_loss = (
        sum(value[0] for value in event_metrics.values())
        / len(event_metrics)
    )
    pooled_brier = (
        sum(value[1] for value in event_metrics.values())
        / len(event_metrics)
    )
    return pooled_loss, pooled_brier, event_metrics


def passes_c3_validation_gate(
    *,
    pooled_raw_minus_candidate_log_loss: float,
    pooled_raw_minus_candidate_brier: float,
    block_raw_minus_candidate_log_loss: Sequence[float],
    median_event_raw_minus_candidate_log_loss: float,
    champion_model_valid: bool,
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
        and champion_model_valid
        and structural_coverage_ok
        and policy_firewall_ok
    )


def build_c3_predictions(
    *,
    outcomes: Sequence[Mapping[str, str]],
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    champion_r2: Mapping[str, Any],
    frozen_data: C3FrozenData,
    prior_events: frozenset[str],
    prior_markets: frozenset[str],
) -> tuple[dict[str, Any], ...]:
    valid_outcomes = validate_c3_outcomes(
        outcomes,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        prior_events=prior_events,
        prior_markets=prior_markets,
        require_complete=True,
    )

    champion = dict(champion_r2)
    if champion.get("champion_r2_fingerprint") != CHAMPION_R2_FINGERPRINT:
        _error("C3 prediction model fingerprint mismatch")

    beta = float(champion["model"]["beta_distance"])
    labels = {
        row["market_ticker"]: int(row["outcome"])
        for row in valid_outcomes
    }

    predictions: list[dict[str, Any]] = []
    state_ids: set[str] = set()
    for index, row in enumerate(frozen_data.preoutcome_rows):
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if market not in labels:
            _error(f"C3 pre-outcome row references missing label {market}")
        block = frozen_data.event_block_map.get(event)
        if block != str(row["block_id"]):
            _error(f"C3 pre-outcome row block mismatch for {event}")

        q_market = float(row["q_market"])
        d_btc = float(row["d_BTC"])
        if not all(math.isfinite(value) for value in (q_market, d_btc)):
            _error(f"C3 pre-outcome row {index} has non-finite input")

        state_id = (
            f"{event}|{market}|"
            f"TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in state_ids:
            _error(f"duplicate C3 state identity {state_id}")
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
                "candidate_probability": predict_c3_probability(
                    q_market=q_market,
                    d_btc=d_btc,
                    beta_distance=beta,
                ),
            }
        )

    if len(predictions) != C3_ROW_COUNT:
        _error(f"C3 prediction row count changed: {len(predictions)}")
    if len({row["event_ticker"] for row in predictions}) != C3_ELIGIBLE_EVENT_TARGET:
        _error("C3 prediction event count changed")
    return tuple(predictions)


def _structural_coverage_ok(
    predictions: Sequence[Mapping[str, Any]],
) -> bool:
    required_roles = {"q10", "q30", "q50", "q70", "q90"}
    required_ttc = {55, 50, 45, 40, 35, 30}
    for block in C3_BLOCKS:
        rows = [
            row
            for row in predictions
            if row["block_id"] == block
        ]
        if {str(row["structural_role"]) for row in rows} != required_roles:
            return False
        if {int(row["ttc_target_minutes"]) for row in rows} != required_ttc:
            return False
    return True


def evaluate_c3(
    *,
    outcomes: Sequence[Mapping[str, str]],
    implementation_freeze: Mapping[str, Any],
    validation_freeze: Mapping[str, Any],
    champion_r2: Mapping[str, Any],
    frozen_data: C3FrozenData,
    prior_events: frozenset[str],
    prior_markets: frozenset[str],
) -> C3Evaluation:
    validate_c3_implementation_freeze_document(
        implementation_freeze,
        repo=Path(".").resolve(),
        verify_parent=False,
        verify_implementation_hashes=False,
    )

    predictions = build_c3_predictions(
        outcomes=outcomes,
        implementation_freeze=implementation_freeze,
        validation_freeze=validation_freeze,
        champion_r2=champion_r2,
        frozen_data=frozen_data,
        prior_events=prior_events,
        prior_markets=prior_markets,
    )

    raw_loss, raw_brier, raw_events = _event_equal_metrics(
        predictions,
        "q_market",
    )
    candidate_loss, candidate_brier, candidate_events = _event_equal_metrics(
        predictions,
        "candidate_probability",
    )
    if set(raw_events) != set(candidate_events):
        _error("C3 raw/candidate event sets differ")

    event_deltas = {
        event: raw_events[event][0] - candidate_events[event][0]
        for event in raw_events
    }

    block_metrics: dict[str, dict[str, float]] = {}
    block_deltas: list[float] = []
    block_rows: list[dict[str, str]] = []

    for block in C3_BLOCKS:
        rows = [
            row
            for row in predictions
            if row["block_id"] == block
        ]
        raw_block_loss, raw_block_brier, raw_block_events = _event_equal_metrics(
            rows,
            "q_market",
        )
        cand_block_loss, cand_block_brier, cand_block_events = _event_equal_metrics(
            rows,
            "candidate_probability",
        )
        if (
            len(raw_block_events) != C3_EVENTS_PER_SUBBLOCK
            or set(raw_block_events) != set(cand_block_events)
        ):
            _error(f"C3 block {block} event membership changed")

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
                "schema_version": C3_BLOCK_SCORE_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": DISTANCE_CANDIDATE_ID,
                "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
                "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
                "block_id": block,
                "event_count": str(C3_EVENTS_PER_SUBBLOCK),
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
    beta = float(champion_r2["model"]["beta_distance"])
    champion_valid = (
        champion_r2.get("fit_result", {}).get("converged") is True
        and math.isfinite(beta)
        and beta > 0.0
        and champion_r2.get("champion_r2_fingerprint") == CHAMPION_R2_FINGERPRINT
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
    gate = passes_c3_validation_gate(
        pooled_raw_minus_candidate_log_loss=raw_loss - candidate_loss,
        pooled_raw_minus_candidate_brier=raw_brier - candidate_brier,
        block_raw_minus_candidate_log_loss=block_deltas,
        median_event_raw_minus_candidate_log_loss=median_delta,
        champion_model_valid=champion_valid,
        structural_coverage_ok=structural_ok,
        policy_firewall_ok=finite_metrics,
    )

    prediction_rows: list[dict[str, str]] = []
    for row in predictions:
        prediction_rows.append(
            {
                "schema_version": C3_PREDICTION_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": DISTANCE_CANDIDATE_ID,
                "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
                "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
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
    for event in sorted(raw_events):
        raw_event = raw_events[event]
        candidate_event = candidate_events[event]
        event_score_rows.append(
            {
                "schema_version": C3_EVENT_SCORE_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": DISTANCE_CANDIDATE_ID,
                "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
                "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
                "block_id": frozen_data.event_block_map[event],
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
        "schema_version": C3_SUMMARY_SCHEMA_VERSION,
        "checkpoint_id": "21H-B",
        "family_id": FAMILY_ID,
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
        "parent_h3_result_fingerprint": PARENT_H3_RESULT_FINGERPRINT,
        "parent_c1_result_fingerprint": C1_RESULT_FINGERPRINT,
        "parent_c2_result_fingerprint": C2_RESULT_FINGERPRINT,
        "champion_r2_fingerprint": CHAMPION_R2_FINGERPRINT,
        "c3_validation_fingerprint": C3_VALIDATION_FINGERPRINT,
        "c3_implementation_fingerprint": implementation_freeze[
            "c3_implementation_fingerprint"
        ],
        "c3_cohort_fingerprint": C3_COHORT_FINGERPRINT,
        "c3_preoutcome_row_fingerprint": C3_ROW_FINGERPRINT,
        "C3_event_count": C3_ELIGIBLE_EVENT_TARGET,
        "C3_row_count": C3_ROW_COUNT,
        "C3_market_count": C3_MARKET_COUNT,
        "beta_distance": _float_text(beta),
        "raw_event_equal_log_loss": _float_text(raw_loss),
        "candidate_event_equal_log_loss": _float_text(candidate_loss),
        "raw_minus_candidate_log_loss": _float_text(raw_loss - candidate_loss),
        "raw_event_equal_brier": _float_text(raw_brier),
        "candidate_event_equal_brier": _float_text(candidate_brier),
        "raw_minus_candidate_brier": _float_text(raw_brier - candidate_brier),
        "median_event_raw_minus_candidate_log_loss": _float_text(median_delta),
        "block_log_loss_deltas": {
            block: _float_text(
                block_metrics[block]["raw_minus_candidate_log_loss"]
            )
            for block in C3_BLOCKS
        },
        "block_log_loss_win_count": sum(
            value > 0.0
            for value in block_deltas
        ),
        "latest_block_B4_win": block_deltas[-1] > 0.0,
        "structural_coverage_ok": structural_ok,
        "champion_r2_valid": champion_valid,
        "metrics_finite": finite_metrics,
        "policy_lineage_source_timing_firewall": (
            "PASS" if finite_metrics else "FAIL"
        ),
        "C3_validation_passed": bool(gate),
        "C3_permanently_exposed": True,
        "model_parameters_fitted_on_C3": False,
        "candidate_selection_on_C3_performed": False,
        "feature_change_performed": False,
        "hyperparameter_search_performed": False,
        "remaining_historical_reserve_accessed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }

    return C3Evaluation(
        summary=summary,
        block_rows=tuple(block_rows),
        prediction_rows=tuple(prediction_rows),
        event_score_rows=tuple(event_score_rows),
    )


def c3_result_fingerprint(
    summary: Mapping[str, Any],
) -> str:
    return _canonical_sha256(dict(summary))


def write_c3_evaluation_outputs(
    output_dir: Path,
    *,
    run_id: str,
    outcomes: Sequence[Mapping[str, str]],
    evaluation: C3Evaluation,
    outcome_journal_path: Path,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)

    outcomes_path = output_dir / f"{run_id}_candidate_e_c3_outcomes.csv"
    summary_path = output_dir / f"{run_id}_candidate_e_c3_summary.json"
    blocks_path = output_dir / f"{run_id}_candidate_e_c3_block_scores.csv"
    predictions_path = output_dir / f"{run_id}_candidate_e_c3_predictions.csv"
    events_path = output_dir / f"{run_id}_candidate_e_c3_event_scores.csv"

    _write_csv(outcomes_path, C3_OUTCOME_FIELDS, outcomes)
    summary_path.write_text(
        json.dumps(evaluation.summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(blocks_path, C3_BLOCK_SCORE_FIELDS, evaluation.block_rows)
    _write_csv(predictions_path, C3_PREDICTION_FIELDS, evaluation.prediction_rows)
    _write_csv(events_path, C3_EVENT_SCORE_FIELDS, evaluation.event_score_rows)
    return (
        outcome_journal_path,
        outcomes_path,
        summary_path,
        blocks_path,
        predictions_path,
        events_path,
    )


__all__ = [
    "CP21H_B_COLLECTOR_NAME",
    "CHAMPION_R2_BETA_DISTANCE",
    "C3_ELIGIBLE_EVENT_TARGET",
    "C3_MARKET_COUNT",
    "C3_OUTCOME_FIELDS",
    "C3_ROW_COUNT",
    "C3_STRICT_TAIL_END_EXCLUSIVE",
    "C3_STRICT_TAIL_REMAINING",
    "CandidateEC3EvaluationError",
    "DEFAULT_C3_ATTEMPT_PATH",
    "DEFAULT_C3_IMPLEMENTATION_FREEZE_PATH",
    "DERIVED_ROOT",
    "_create_or_validate_c3_attempt",
    "append_c3_outcome_journal",
    "assert_clean_synchronized_repository",
    "assert_not_prior_exposed_identity",
    "build_c3_predictions",
    "c3_preflight",
    "c3_result_fingerprint",
    "collect_c3_outcomes",
    "evaluate_c3",
    "initialize_c3_outcome_journal",
    "passes_c3_validation_gate",
    "predict_c3_probability",
    "recover_c3_outcomes_from_manifest",
    "update_c3_attempt_receipt",
    "validate_c3_implementation_freeze",
    "validate_c3_implementation_freeze_document",
    "validate_c3_validation_freeze_document",
    "write_c3_evaluation_outputs",
    "write_or_validate_c3_implementation_freeze",
]
