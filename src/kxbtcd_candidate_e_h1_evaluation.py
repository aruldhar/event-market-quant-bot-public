"""Checkpoint-20 Candidate-E H1 historical development evaluation.

The module deliberately separates two stages:

Stage A (outcome-blind):
* validate the Checkpoint-19H-C Coinbase-primary pre-outcome freeze;
* recompute and require the frozen cohort-map and row-universe fingerprints;
* derive the H1 outcome allow-list only from frozen H1 identities;
* derive H2/H3 hard-deny identity sets from the same frozen universe;
* bind the already-frozen H1 seven-block map and five rolling-origin folds;
* bind the exact two Candidate-E variants and frozen advancement/complexity gates;
* freeze SHA-256 hashes of the implementation that may later expose H1 labels.

Stage B (H1 exposure, only after the Stage-A freeze is committed/pushed):
* require a clean synchronized main checkout before any HTTP client exists;
* permanently mark the full H1 set development-exposed before the first request;
* request only the frozen H1 historical-market allow-list;
* preserve raw responses before semantic use through the existing raw-first client;
* fit/score exactly the two frozen Candidate-E models using the frozen 7-block /
  5-fold rolling-origin procedure;
* apply the frozen raw advancement and nested complexity gates exactly once.

H2 and H3 outcomes are never requested or accepted by this module. There is no
order placement, cancellation, transfer, paper execution, demo execution, or
real-money execution path.
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
from statistics import median
from typing import Any, Callable, Mapping, Protocol, Sequence

from .kxbtcd_candidate_e_coinbase_primary_materialization import (
    COHORT_MAP_FIELDS,
    FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
    FROZEN_CONTRACT_FINGERPRINT,
    PREOUTCOME_ROW_FIELDS,
    validate_block_coverage,
    validate_coinbase_primary_amendment,
)
from .kxbtcd_candidate_e_historical_materialization import canonical_rows_fingerprint
from .kxbtcd_candidate_e_predeclaration import (
    DISTANCE_CANDIDATE_ID,
    FAMILY_ID,
    FROZEN_PREDECLARATION_FINGERPRINT,
    MOMENTUM_CANDIDATE_ID,
    btc_return_5m_bps,
    btc_strike_log_distance_bps,
    candidate_e_predeclaration,
    market_logit_offset,
    passes_nested_complexity_gate,
    passes_raw_advancement_gate,
    select_candidate_e,
    validate_candidate_e_predeclaration,
)


class KxbtcdCandidateEH1EvaluationError(RuntimeError):
    """Raised when any frozen H1 evaluation invariant is violated."""


CP20_COLLECTOR_NAME = "collect_kxbtcd_candidate_e_h1"
H1_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_evaluation_freeze.v1"
H1_OUTCOME_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_outcome.v1"
H1_ATTEMPT_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_attempt.v1"
H1_SUMMARY_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_evaluation_summary.v1"
H1_FOLD_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_fold_score.v1"
H1_COEFFICIENT_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_fold_coefficients.v1"
H1_PREDICTION_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_oof_prediction.v1"
H1_EVENT_SCORE_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_event_score.v1"

FROZEN_COHORT_MAP_FINGERPRINT = "09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa"
FROZEN_ROW_UNIVERSE_FINGERPRINT = "e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5"
FROZEN_EXCLUSION_FINGERPRINT = "dd2877579bb800fc1d15ee3c05754947658dfdb552858d67f39b260e32aaf9c4"

EXPECTED_STAGE_EVENT_COUNTS = {"H1": 1500, "H2": 750, "H3": 750}
EXPECTED_STAGE_ROW_COUNTS = {"H1": 36314, "H2": 22354, "H3": 22409}
EXPECTED_H1_BLOCK_EVENT_COUNTS = {
    "B0": 215,
    "B1": 215,
    "B2": 214,
    "B3": 214,
    "B4": 214,
    "B5": 214,
    "B6": 214,
}
EXPECTED_H1_SCORED_EVENTS = 1070

FROZEN_ROOT = Path("data/derived/kxbtcd_candidate_e_coinbase_primary_materialization/frozen")
DEFAULT_H1_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_h1_evaluation_freeze.json")
DEFAULT_H1_ATTEMPT_PATH = Path("data/analysis/kxbtcd_candidate_e_h1_evaluation/h1_attempt.json")
DERIVED_ROOT = Path("data/derived/kxbtcd_candidate_e_h1_evaluation")

H1_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_h1_evaluation.py",
    "collect_kxbtcd_candidate_e_h1.py",
)

H1_OUTCOME_FIELDS = (
    "schema_version",
    "family_id",
    "h1_evaluation_fingerprint",
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
class OutcomeRequest:
    event_ticker: str
    market_ticker: str


@dataclass(frozen=True)
class FrozenCandidateEUniverse:
    summary: dict[str, Any]
    cohort_rows: tuple[dict[str, Any], ...]
    preoutcome_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CandidateEObservation:
    state_id: str
    event_ticker: str
    market_ticker: str
    block_id: str
    structural_role: str
    ttc_target_minutes: int
    outcome: int
    q_market: float
    d_btc: float
    r_5m: float


@dataclass(frozen=True)
class CandidateEFit:
    candidate_id: str
    fold: int
    fit_blocks: tuple[str, ...]
    score_block: str
    beta_distance: float
    beta_momentum: float | None
    iterations: int
    converged: bool
    fit_objective: float


@dataclass(frozen=True)
class CandidateEEvaluation:
    summary: dict[str, Any]
    fold_rows: tuple[dict[str, str], ...]
    coefficient_rows: tuple[dict[str, str], ...]
    prediction_rows: tuple[dict[str, str], ...]
    event_score_rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class H1Preflight:
    repository_root: Path
    git_head: str
    freeze: dict[str, Any]
    universe: FrozenCandidateEUniverse
    attempt_path: Path


def _error(message: str) -> None:
    raise KxbtcdCandidateEH1EvaluationError(message)


def _resolve(repo: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo / candidate


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


def _implementation_sha256s(repository_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in H1_IMPLEMENTATION_FILES:
        path = repository_root / relative
        if not path.is_file():
            _error(f"H1 implementation file missing: {relative}")
        result[relative] = _sha256_file(path)
    return result


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{name} must be non-empty text")
    return value.strip()


def _float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise KxbtcdCandidateEH1EvaluationError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
    return format(value, ".17g")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KxbtcdCandidateEH1EvaluationError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be object: {path}")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            return fields, [dict(row) for row in reader]
    except OSError as exc:
        raise KxbtcdCandidateEH1EvaluationError(f"could not read CSV {path}: {exc}") from exc


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
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


def assert_clean_synchronized_repository(
    repository_root: str | Path = ".",
    *,
    branch: str = "main",
    remote_ref: str = "origin/main",
) -> str:
    """Fail closed unless Stage B starts from a clean synchronized main checkout."""
    repo = Path(repository_root).resolve()
    observed_branch = _git(repo, "branch", "--show-current")
    if observed_branch != branch:
        _error(f"H1 exposure requires branch {branch!r}; got {observed_branch!r}")
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        _error(
            "H1 exposure requires a completely clean worktree/index; "
            f"first dirty line: {status.splitlines()[0]}"
        )
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", remote_ref)
    if head != remote:
        _error(
            "H1 exposure requires local HEAD == origin/main after a fresh fetch; "
            f"HEAD={head}, {remote_ref}={remote}"
        )
    return head


def _parse_cohort_rows(rows: Sequence[Mapping[str, str]]) -> tuple[dict[str, Any], ...]:
    parsed: list[dict[str, Any]] = []
    integer_fields = {
        "queue_index_zero_based",
        "stage_event_index_zero_based",
        "eligible_anchor_count",
        "common_row_count",
    }
    for index, source in enumerate(rows):
        row: dict[str, Any] = dict(source)
        for field in integer_fields:
            try:
                row[field] = int(row[field])
            except (TypeError, ValueError) as exc:
                raise KxbtcdCandidateEH1EvaluationError(
                    f"cohort row {index} {field} must be integer"
                ) from exc
        parsed.append(row)
    return tuple(parsed)


def _parse_preoutcome_rows(rows: Sequence[Mapping[str, str]]) -> tuple[dict[str, Any], ...]:
    parsed: list[dict[str, Any]] = []
    integer_fields = {
        "queue_index_zero_based",
        "ttc_target_minutes",
        "kalshi_quote_end_period_ts",
        "kalshi_quote_staleness_seconds",
    }
    for index, source in enumerate(rows):
        row: dict[str, Any] = dict(source)
        for field in integer_fields:
            try:
                row[field] = int(row[field])
            except (TypeError, ValueError) as exc:
                raise KxbtcdCandidateEH1EvaluationError(
                    f"preoutcome row {index} {field} must be integer"
                ) from exc
        try:
            refs = json.loads(row["raw_observation_refs"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise KxbtcdCandidateEH1EvaluationError(
                f"preoutcome row {index} raw_observation_refs must be JSON"
            ) from exc
        if not isinstance(refs, list):
            _error(f"preoutcome row {index} raw_observation_refs must be list")
        row["raw_observation_refs"] = refs
        parsed.append(row)
    return tuple(parsed)


def _validate_feature_row(row: Mapping[str, Any], index: int) -> None:
    if row.get("source_amendment_fingerprint") != FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT:
        _error(f"preoutcome row {index} Coinbase-primary amendment mismatch")
    if row.get("stage") not in {"H1", "H2", "H3"}:
        _error(f"preoutcome row {index} has invalid stage")
    if row.get("kraken_current_price") or row.get("kraken_lookback_price"):
        _error(f"preoutcome row {index} unexpectedly contains canonical Kraken price")
    if row.get("current_disagreement_bps") or row.get("lookback_disagreement_bps"):
        _error(f"preoutcome row {index} unexpectedly contains disagreement veto value")
    q = _float(row.get("q_market"), f"preoutcome[{index}].q_market")
    if not 0.0 <= q <= 1.0:
        _error(f"preoutcome row {index} q_market outside [0,1]")
    bid = _float(row.get("yes_bid"), f"preoutcome[{index}].yes_bid")
    ask = _float(row.get("yes_ask"), f"preoutcome[{index}].yes_ask")
    if not (0.0 <= bid <= ask <= 1.0):
        _error(f"preoutcome row {index} invalid YES quote")
    if not math.isclose(q, (bid + ask) / 2.0, rel_tol=0.0, abs_tol=5e-13):
        _error(f"preoutcome row {index} q_market no longer equals raw midpoint")
    spot = _float(row.get("coinbase_current_price"), f"preoutcome[{index}].coinbase_current_price")
    lookback = _float(row.get("coinbase_lookback_price"), f"preoutcome[{index}].coinbase_lookback_price")
    strike = _float(row.get("strike_dollars"), f"preoutcome[{index}].strike_dollars")
    observed_d = _float(row.get("d_BTC"), f"preoutcome[{index}].d_BTC")
    observed_r = _float(row.get("r_5m"), f"preoutcome[{index}].r_5m")
    expected_d = btc_strike_log_distance_bps(spot, strike)
    expected_r = btc_return_5m_bps(spot, lookback)
    if not math.isclose(observed_d, expected_d, rel_tol=1e-12, abs_tol=1e-9):
        _error(f"preoutcome row {index} d_BTC formula mismatch")
    if not math.isclose(observed_r, expected_r, rel_tol=1e-12, abs_tol=1e-9):
        _error(f"preoutcome row {index} r_5m formula mismatch")


def load_and_validate_frozen_universe(
    repository_root: str | Path = ".",
    *,
    frozen_root: str | Path = FROZEN_ROOT,
    validate_features: bool = True,
) -> FrozenCandidateEUniverse:
    """Validate the exact 19H-C pre-outcome universe without opening outcomes."""
    repo = Path(repository_root).resolve()
    validate_candidate_e_predeclaration(repo / "configs/kxbtcd_candidate_e_predeclaration.json")
    validate_coinbase_primary_amendment(
        repo / "configs/kxbtcd_candidate_e_coinbase_primary_amendment.json",
        verify_parent=True,
    )
    root = _resolve(repo, frozen_root)
    summary = _read_json(root / "freeze_summary.json")
    cohort_fields, cohort_raw = _read_csv(root / "cohort_map.csv")
    row_fields, preoutcome_raw = _read_csv(root / "candidate_e_preoutcome_rows.csv")
    if cohort_fields != tuple(COHORT_MAP_FIELDS):
        _error("19H-C cohort-map CSV schema mismatch")
    if row_fields != tuple(PREOUTCOME_ROW_FIELDS):
        _error("19H-C preoutcome-row CSV schema mismatch")
    cohort = _parse_cohort_rows(cohort_raw)
    rows = _parse_preoutcome_rows(preoutcome_raw)

    expected_summary = {
        "checkpoint_id": "19H",
        "parent_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "source_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
        "exclusion_fingerprint": FROZEN_EXCLUSION_FINGERPRINT,
        "required_btc_source": "Coinbase",
        "kraken_required": False,
        "outcomes_accessed": False,
        "candidate_e_fit_performed": False,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "execution_authorized": False,
    }
    for key, expected in expected_summary.items():
        if summary.get(key) != expected:
            _error(f"19H-C freeze summary {key} mismatch")
    if summary.get("eligible_counts") != EXPECTED_STAGE_EVENT_COUNTS:
        _error("19H-C stage event counts changed")
    if int(summary.get("actual_unallocated_tail_events", 0)) != 6231:
        _error("19H-C untouched reserve changed")

    observed_cohort_fp = canonical_rows_fingerprint(cohort)
    observed_rows_fp = canonical_rows_fingerprint(rows)
    if observed_cohort_fp != FROZEN_COHORT_MAP_FINGERPRINT:
        _error(
            "19H-C cohort-map fingerprint mismatch; "
            f"observed={observed_cohort_fp}"
        )
    if observed_rows_fp != FROZEN_ROW_UNIVERSE_FINGERPRINT:
        _error(
            "19H-C row-universe fingerprint mismatch; "
            f"observed={observed_rows_fp}"
        )

    cohort_by_stage = {stage: [row for row in cohort if row["stage"] == stage] for stage in EXPECTED_STAGE_EVENT_COUNTS}
    rows_by_stage = {stage: [row for row in rows if row["stage"] == stage] for stage in EXPECTED_STAGE_ROW_COUNTS}
    for stage, expected in EXPECTED_STAGE_EVENT_COUNTS.items():
        if len(cohort_by_stage[stage]) != expected:
            _error(f"{stage} event count changed: {len(cohort_by_stage[stage])} != {expected}")
        indices = [int(row["stage_event_index_zero_based"]) for row in cohort_by_stage[stage]]
        if indices != list(range(expected)):
            _error(f"{stage} stage_event_index sequence changed")
        chronology = [(row["event_close_time_utc"], row["event_ticker"]) for row in cohort_by_stage[stage]]
        if chronology != sorted(chronology):
            _error(f"{stage} cohort is no longer chronological")
    for stage, expected in EXPECTED_STAGE_ROW_COUNTS.items():
        if len(rows_by_stage[stage]) != expected:
            _error(f"{stage} row count changed: {len(rows_by_stage[stage])} != {expected}")

    block_counts: dict[str, int] = {}
    for row in cohort_by_stage["H1"]:
        block = _text(row.get("block_id"), "H1 block_id")
        block_counts[block] = block_counts.get(block, 0) + 1
    if block_counts != EXPECTED_H1_BLOCK_EVENT_COUNTS:
        _error(f"H1 seven-block event counts changed: {block_counts}")

    event_stage = {row["event_ticker"]: row["stage"] for row in cohort}
    if len(event_stage) != sum(EXPECTED_STAGE_EVENT_COUNTS.values()):
        _error("cohort map contains duplicate event identities")
    for index, row in enumerate(rows):
        stage = event_stage.get(row["event_ticker"])
        if stage != row["stage"]:
            _error(f"preoutcome row {index} event/stage does not match cohort map")
        if validate_features:
            _validate_feature_row(row, index)

    # Reuse the materializer's frozen coverage checker. It intentionally requires
    # H1 B2-B6 plus all H2/H3 blocks and remains outcome-blind.
    validate_block_coverage(cohort, rows)
    return FrozenCandidateEUniverse(summary=summary, cohort_rows=cohort, preoutcome_rows=rows)


def _stage_market_map(universe: FrozenCandidateEUniverse, stage: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in universe.preoutcome_rows:
        if row["stage"] != stage:
            continue
        market = _text(row["market_ticker"], f"{stage} market_ticker")
        event = _text(row["event_ticker"], f"{stage} event_ticker")
        previous = result.setdefault(market, event)
        if previous != event:
            _error(f"market {market} maps to multiple events")
    if not result:
        _error(f"{stage} market identity set is empty")
    return result


def _stage_events(universe: FrozenCandidateEUniverse, stage: str) -> tuple[str, ...]:
    events = tuple(
        _text(row["event_ticker"], f"{stage} event_ticker")
        for row in universe.cohort_rows
        if row["stage"] == stage
    )
    if len(events) != EXPECTED_STAGE_EVENT_COUNTS[stage]:
        _error(f"{stage} event identity count mismatch")
    return events


def _event_identity_fingerprint(events: Sequence[str]) -> str:
    return _canonical_sha256(list(events))


def _market_identity_payload(market_map: Mapping[str, str]) -> list[dict[str, str]]:
    return [
        {"event_ticker": event, "market_ticker": market}
        for market, event in sorted(market_map.items(), key=lambda item: (item[1], item[0]))
    ]


def _market_identity_fingerprint(market_map: Mapping[str, str]) -> str:
    return _canonical_sha256(_market_identity_payload(market_map))


def build_h1_request_plan(universe: FrozenCandidateEUniverse) -> tuple[OutcomeRequest, ...]:
    mapping = _stage_market_map(universe, "H1")
    return tuple(
        OutcomeRequest(event_ticker=item["event_ticker"], market_ticker=item["market_ticker"])
        for item in _market_identity_payload(mapping)
    )


def validate_stage_identity_disjointness(universe: FrozenCandidateEUniverse) -> None:
    event_sets = {stage: set(_stage_events(universe, stage)) for stage in ("H1", "H2", "H3")}
    market_sets = {stage: set(_stage_market_map(universe, stage)) for stage in ("H1", "H2", "H3")}
    for left, right in (("H1", "H2"), ("H1", "H3"), ("H2", "H3")):
        event_overlap = event_sets[left] & event_sets[right]
        market_overlap = market_sets[left] & market_sets[right]
        if event_overlap:
            _error(f"sealed-stage event identity overlap {left}/{right}: {sorted(event_overlap)[:3]}")
        if market_overlap:
            _error(f"sealed-stage market identity overlap {left}/{right}: {sorted(market_overlap)[:3]}")


def _expected_rolling_folds() -> list[dict[str, Any]]:
    return [
        {"fold": 1, "fit_blocks": ["B0", "B1"], "score_block": "B2"},
        {"fold": 2, "fit_blocks": ["B0", "B1", "B2"], "score_block": "B3"},
        {"fold": 3, "fit_blocks": ["B0", "B1", "B2", "B3"], "score_block": "B4"},
        {"fold": 4, "fit_blocks": ["B0", "B1", "B2", "B3", "B4"], "score_block": "B5"},
        {"fold": 5, "fit_blocks": ["B0", "B1", "B2", "B3", "B4", "B5"], "score_block": "B6"},
    ]


def build_h1_evaluation_freeze_document(
    *,
    universe: FrozenCandidateEUniverse,
    source_baseline_commit: str,
    implementation_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    validate_stage_identity_disjointness(universe)
    predeclaration = candidate_e_predeclaration()
    folds = predeclaration["e1_chronological_layout"]["rolling_origin_folds"]
    if folds != _expected_rolling_folds():
        _error("Candidate-E rolling-origin folds changed")
    plan = build_h1_request_plan(universe)
    identity: dict[str, Any] = {}
    for stage in ("H1", "H2", "H3"):
        events = _stage_events(universe, stage)
        markets = _stage_market_map(universe, stage)
        identity[stage] = {
            "event_count": len(events),
            "row_count": EXPECTED_STAGE_ROW_COUNTS[stage],
            "market_count": len(markets),
            "event_identity_fingerprint": _event_identity_fingerprint(events),
            "market_identity_fingerprint": _market_identity_fingerprint(markets),
        }

    payload = {
        "schema_version": H1_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20A",
        "family_id": FAMILY_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
        "exclusion_fingerprint": FROZEN_EXCLUSION_FINGERPRINT,
        "stage_scope": "H1_only",
        "stage_identities": identity,
        "h1_request_plan": [
            {"event_ticker": request.event_ticker, "market_ticker": request.market_ticker}
            for request in plan
        ],
        "sealed_stage_policy": {
            "H2_outcomes_opened_at_freeze": 0,
            "H3_outcomes_opened_at_freeze": 0,
            "H2_event_and_market_identities_hard_denied": True,
            "H3_event_and_market_identities_hard_denied": True,
            "request_plan_may_be_derived_only_from_frozen_H1_rows": True,
            "arbitrary_partition_argument_allowed": False,
            "arbitrary_ticker_argument_allowed": False,
        },
        "outcome_source": {
            "endpoint_template": "/historical/markets/{market_ticker}",
            "required_market_status": "finalized",
            "accepted_results": ["yes", "no"],
            "raw_first_persistence_required": True,
            "authentication_required": False,
        },
        "candidate_menu": [DISTANCE_CANDIDATE_ID, MOMENTUM_CANDIDATE_ID],
        "fit_contract": predeclaration["fit_contract"],
        "rolling_origin_folds": folds,
        "metrics": predeclaration["metrics"],
        "raw_advancement_gate": predeclaration["raw_advancement_gate"],
        "candidate_selection_rule": predeclaration["candidate_selection_rule"],
        "post_h1_policy": {
            "posthoc_feature_change_allowed": False,
            "posthoc_candidate_repair_allowed": False,
            "H1_refit_or_rescore_after_design_result_allowed": False,
            "H2_may_open_only_if_H1_selects_exactly_one_candidate": True,
            "H3_may_open_in_checkpoint_20": False,
        },
        "exposure_policy": {
            "permanently_expose_full_H1_before_first_request": True,
            "fresh_second_H1_attempt_allowed": False,
            "resume_only_after_interruption": True,
            "future_untouched_claim_on_H1_allowed": False,
        },
        "source_baseline_commit": _text(source_baseline_commit, "source_baseline_commit"),
        "implementation_sha256s": {
            key: _text(value, f"implementation_sha256s[{key}]")
            for key, value in sorted(implementation_sha256s.items())
        },
        "procedure_derivation_outcomes_used": False,
        "candidate_e_fit_performed_at_freeze": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    document = dict(payload)
    document["h1_evaluation_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_h1_evaluation_freeze_document(
    document: Mapping[str, Any],
    *,
    universe: FrozenCandidateEUniverse | None = None,
    repository_root: str | Path | None = None,
) -> tuple[OutcomeRequest, ...]:
    expected_identity = {
        "schema_version": H1_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20A",
        "family_id": FAMILY_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
        "exclusion_fingerprint": FROZEN_EXCLUSION_FINGERPRINT,
        "stage_scope": "H1_only",
        "candidate_menu": [DISTANCE_CANDIDATE_ID, MOMENTUM_CANDIDATE_ID],
        "procedure_derivation_outcomes_used": False,
        "candidate_e_fit_performed_at_freeze": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, expected in expected_identity.items():
        if document.get(key) != expected:
            _error(f"H1 evaluation freeze {key} mismatch")

    predeclaration = candidate_e_predeclaration()
    if document.get("fit_contract") != predeclaration["fit_contract"]:
        _error("H1 fit contract changed")
    if document.get("rolling_origin_folds") != _expected_rolling_folds():
        _error("H1 rolling-origin folds changed")
    if document.get("metrics") != predeclaration["metrics"]:
        _error("H1 metrics changed")
    if document.get("raw_advancement_gate") != predeclaration["raw_advancement_gate"]:
        _error("H1 raw advancement gate changed")
    if document.get("candidate_selection_rule") != predeclaration["candidate_selection_rule"]:
        _error("H1 candidate-selection rule changed")

    sealed = document.get("sealed_stage_policy")
    if not isinstance(sealed, Mapping):
        _error("H1 freeze missing sealed-stage policy")
    expected_sealed = {
        "H2_outcomes_opened_at_freeze": 0,
        "H3_outcomes_opened_at_freeze": 0,
        "H2_event_and_market_identities_hard_denied": True,
        "H3_event_and_market_identities_hard_denied": True,
        "request_plan_may_be_derived_only_from_frozen_H1_rows": True,
        "arbitrary_partition_argument_allowed": False,
        "arbitrary_ticker_argument_allowed": False,
    }
    if dict(sealed) != expected_sealed:
        _error("H1 sealed-stage policy changed")

    post = document.get("post_h1_policy")
    if not isinstance(post, Mapping):
        _error("H1 freeze missing post-H1 policy")
    if post.get("posthoc_feature_change_allowed") is not False:
        _error("post-hoc feature change became allowed")
    if post.get("posthoc_candidate_repair_allowed") is not False:
        _error("post-hoc Candidate-E repair became allowed")
    if post.get("H1_refit_or_rescore_after_design_result_allowed") is not False:
        _error("H1 re-score became allowed")
    if post.get("H2_may_open_only_if_H1_selects_exactly_one_candidate") is not True:
        _error("H2 sequential firewall changed")
    if post.get("H3_may_open_in_checkpoint_20") is not False:
        _error("H3 became openable in Checkpoint 20")

    exposure = document.get("exposure_policy")
    if not isinstance(exposure, Mapping):
        _error("H1 freeze missing exposure policy")
    expected_exposure = {
        "permanently_expose_full_H1_before_first_request": True,
        "fresh_second_H1_attempt_allowed": False,
        "resume_only_after_interruption": True,
        "future_untouched_claim_on_H1_allowed": False,
    }
    if dict(exposure) != expected_exposure:
        _error("H1 exposure policy changed")

    identities = document.get("stage_identities")
    if not isinstance(identities, Mapping) or set(identities) != {"H1", "H2", "H3"}:
        _error("H1 freeze stage identities missing")
    for stage in ("H1", "H2", "H3"):
        value = identities[stage]
        if not isinstance(value, Mapping):
            _error(f"H1 freeze {stage} identity descriptor invalid")
        if value.get("event_count") != EXPECTED_STAGE_EVENT_COUNTS[stage]:
            _error(f"H1 freeze {stage} event count changed")
        if value.get("row_count") != EXPECTED_STAGE_ROW_COUNTS[stage]:
            _error(f"H1 freeze {stage} row count changed")
        for field in ("event_identity_fingerprint", "market_identity_fingerprint"):
            digest = value.get(field)
            if not isinstance(digest, str) or len(digest) != 64:
                _error(f"H1 freeze {stage} {field} invalid")
        if not isinstance(value.get("market_count"), int) or value["market_count"] <= 0:
            _error(f"H1 freeze {stage} market_count invalid")

    entries = document.get("h1_request_plan")
    if not isinstance(entries, list) or not entries:
        _error("H1 request plan missing")
    plan: list[OutcomeRequest] = []
    seen_markets: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != {"event_ticker", "market_ticker"}:
            _error(f"H1 request-plan entry {index} schema mismatch")
        event = _text(entry["event_ticker"], f"h1_request_plan[{index}].event_ticker")
        market = _text(entry["market_ticker"], f"h1_request_plan[{index}].market_ticker")
        if market in seen_markets:
            _error(f"duplicate H1 request market {market}")
        seen_markets.add(market)
        plan.append(OutcomeRequest(event_ticker=event, market_ticker=market))
    if plan != sorted(plan, key=lambda item: (item.event_ticker, item.market_ticker)):
        _error("H1 request plan is not canonically sorted")
    if len(plan) != identities["H1"]["market_count"]:
        _error("H1 request-plan count differs from frozen H1 market count")

    implementation = document.get("implementation_sha256s")
    if not isinstance(implementation, Mapping) or set(implementation) != set(H1_IMPLEMENTATION_FILES):
        _error("H1 implementation-file set changed")
    for relative, digest in implementation.items():
        if not isinstance(digest, str) or len(digest) != 64:
            _error(f"invalid H1 implementation hash for {relative}")
    if repository_root is not None:
        repo = Path(repository_root).resolve()
        if dict(implementation) != _implementation_sha256s(repo):
            _error("H1 implementation bytes differ from frozen procedure")

    payload = {key: document[key] for key in document if key != "h1_evaluation_fingerprint"}
    if document.get("h1_evaluation_fingerprint") != _canonical_sha256(payload):
        _error("H1 evaluation procedure fingerprint mismatch")

    if universe is not None:
        validate_stage_identity_disjointness(universe)
        expected = build_h1_evaluation_freeze_document(
            universe=universe,
            source_baseline_commit=_text(document.get("source_baseline_commit"), "source_baseline_commit"),
            implementation_sha256s=dict(document.get("implementation_sha256s", {})),
        )
        if dict(document) != expected:
            _error("stored H1 evaluation freeze differs from deterministic outcome-blind derivation")
    return tuple(plan)


def write_or_validate_h1_evaluation_freeze(
    path: str | Path = DEFAULT_H1_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[Path, dict[str, Any]]:
    """Create the deterministic Stage-A freeze; never opens outcomes or fits a model."""
    repo = Path(repository_root).resolve()
    universe = load_and_validate_frozen_universe(repo)
    head = _git(repo, "rev-parse", "HEAD")
    derived = build_h1_evaluation_freeze_document(
        universe=universe,
        source_baseline_commit=head,
        implementation_sha256s=_implementation_sha256s(repo),
    )
    validate_h1_evaluation_freeze_document(
        derived,
        universe=universe,
        repository_root=repo,
    )
    target = _resolve(repo, path)
    if target.exists():
        existing = _read_json(target)
        validate_h1_evaluation_freeze_document(
            existing,
            universe=universe,
            repository_root=repo,
        )
        if existing != derived:
            _error("existing H1 evaluation freeze differs; refusing overwrite")
        return target, existing
    _write_json_atomic(target, derived)
    return target, derived


def load_and_validate_h1_evaluation_freeze(
    path: str | Path = DEFAULT_H1_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[dict[str, Any], FrozenCandidateEUniverse]:
    repo = Path(repository_root).resolve()
    universe = load_and_validate_frozen_universe(repo)
    document = _read_json(_resolve(repo, path))
    validate_h1_evaluation_freeze_document(
        document,
        universe=universe,
        repository_root=repo,
    )
    return document, universe


def _sealed_identity_sets(universe: FrozenCandidateEUniverse) -> tuple[set[str], set[str]]:
    events = set(_stage_events(universe, "H2")) | set(_stage_events(universe, "H3"))
    markets = set(_stage_market_map(universe, "H2")) | set(_stage_market_map(universe, "H3"))
    return events, markets


def assert_not_sealed_identity(
    *,
    universe: FrozenCandidateEUniverse,
    event_ticker: str,
    market_ticker: str,
) -> None:
    sealed_events, sealed_markets = _sealed_identity_sets(universe)
    if event_ticker in sealed_events:
        _error(f"refusing sealed H2/H3 event identity: {event_ticker}")
    if market_ticker in sealed_markets:
        _error(f"refusing sealed H2/H3 market identity: {market_ticker}")


def matching_prior_h1_manifests(repository_root: str | Path = ".") -> tuple[Path, ...]:
    repo = Path(repository_root).resolve()
    root = repo / "data" / "manifests"
    if not root.exists():
        return ()
    matches: list[Path] = []
    for path in root.rglob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, Mapping):
            continue
        collector = document.get("collector")
        arguments = document.get("arguments")
        if not isinstance(collector, Mapping) or collector.get("name") != CP20_COLLECTOR_NAME:
            continue
        if not isinstance(arguments, Mapping):
            continue
        if arguments.get("cohort_map_fingerprint") != FROZEN_COHORT_MAP_FINGERPRINT:
            continue
        if arguments.get("row_universe_fingerprint") != FROZEN_ROW_UNIVERSE_FINGERPRINT:
            continue
        matches.append(path.resolve())
    return tuple(sorted(matches, key=lambda path: path.stat().st_mtime_ns))


def _create_or_validate_h1_attempt(
    *,
    path: Path,
    freeze: Mapping[str, Any],
    git_head: str,
    resume_manifest: Path | None,
) -> dict[str, Any]:
    fingerprint = _text(freeze.get("h1_evaluation_fingerprint"), "h1_evaluation_fingerprint")
    if path.exists():
        attempt = _read_json(path)
        if resume_manifest is None:
            _error("H1 attempt receipt already exists; fresh second attempts are prohibited")
        if attempt.get("schema_version") != H1_ATTEMPT_SCHEMA_VERSION:
            _error("H1 attempt receipt schema mismatch")
        if attempt.get("h1_evaluation_fingerprint") != fingerprint:
            _error("H1 attempt receipt procedure fingerprint mismatch")
        if attempt.get("H1_permanently_development_exposed") is not True:
            _error("H1 attempt receipt must conservatively mark H1 exposed")
        if attempt.get("status") == "h1_evaluation_completed":
            _error("H1 evaluation already completed; refusing another score")
        return attempt
    if resume_manifest is not None:
        _error("cannot resume H1 without original attempt receipt")
    attempt = {
        "schema_version": H1_ATTEMPT_SCHEMA_VERSION,
        "status": "h1_exposure_authorized",
        "family_id": FAMILY_ID,
        "h1_evaluation_fingerprint": fingerprint,
        "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
        "H1_event_count": EXPECTED_STAGE_EVENT_COUNTS["H1"],
        "H1_row_count": EXPECTED_STAGE_ROW_COUNTS["H1"],
        "H1_permanently_development_exposed": True,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "fresh_second_attempt_allowed": False,
        "started_at_utc": _utc_now_text(),
        "git_head_at_start": git_head,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    _write_json_atomic(path, attempt)
    return attempt


def update_h1_attempt_receipt(
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
    if status == "h1_evaluation_completed":
        updated["completed_at_utc"] = _utc_now_text()
    _write_json_atomic(path, updated)


def h1_preflight(
    *,
    repository_root: str | Path = ".",
    resume_manifest: str | Path | None = None,
) -> H1Preflight:
    """Run all Stage-B fail-closed checks before any HTTP client is constructed."""
    repo = Path(repository_root).resolve()
    git_head = assert_clean_synchronized_repository(repo)
    freeze, universe = load_and_validate_h1_evaluation_freeze(repository_root=repo)
    prior = matching_prior_h1_manifests(repo)
    resume_path = Path(resume_manifest).resolve() if resume_manifest is not None else None
    if resume_path is None:
        if prior:
            _error(f"prior H1 exposure manifest exists; refusing fresh run: {prior[-1]}")
    else:
        if resume_path not in prior:
            _error("resume manifest is not a recognized Checkpoint-20 H1 manifest")
        manifest = _read_json(resume_path)
        if manifest.get("status") == "completed":
            _error("cannot resume a completed H1 evaluation")
        if manifest.get("status") not in {"running", "failed"}:
            _error(f"resume manifest has unsupported status {manifest.get('status')!r}")
    attempt_path = _resolve(repo, DEFAULT_H1_ATTEMPT_PATH)
    _create_or_validate_h1_attempt(
        path=attempt_path,
        freeze=freeze,
        git_head=git_head,
        resume_manifest=resume_path,
    )
    return H1Preflight(
        repository_root=repo,
        git_head=git_head,
        freeze=freeze,
        universe=universe,
        attempt_path=attempt_path,
    )


def _planned_by_market(freeze: Mapping[str, Any]) -> dict[str, OutcomeRequest]:
    plan = validate_h1_evaluation_freeze_document(freeze)
    return {item.market_ticker: item for item in plan}


def validate_h1_outcomes(
    outcomes: Sequence[Mapping[str, str]],
    *,
    freeze: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
    require_complete: bool,
) -> tuple[dict[str, str], ...]:
    planned = _planned_by_market(freeze)
    fingerprint = str(freeze["h1_evaluation_fingerprint"])
    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, source in enumerate(outcomes):
        row = dict(source)
        missing = set(H1_OUTCOME_FIELDS) - set(row)
        extra = set(row) - set(H1_OUTCOME_FIELDS)
        if missing or extra:
            _error(
                f"H1 outcome row {index} schema mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        expected = {
            "schema_version": H1_OUTCOME_SCHEMA_VERSION,
            "family_id": FAMILY_ID,
            "h1_evaluation_fingerprint": fingerprint,
            "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
            "stage": "H1",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                _error(f"H1 outcome row {index} {key} mismatch")
        market = _text(row["market_ticker"], f"outcomes[{index}].market_ticker")
        event = _text(row["event_ticker"], f"outcomes[{index}].event_ticker")
        assert_not_sealed_identity(universe=universe, event_ticker=event, market_ticker=market)
        if market in seen:
            _error(f"duplicate H1 outcome market {market}")
        seen.add(market)
        plan = planned.get(market)
        if plan is None or plan.event_ticker != event:
            _error(f"unplanned H1 outcome identity: {event}/{market}")
        if row["market_status"] != "finalized":
            _error(f"H1 market {market} is not finalized")
        if (row["result_text"], row["outcome"]) not in {("yes", "1"), ("no", "0")}:
            _error(f"H1 result/outcome mismatch for {market}")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            _text(row[field], f"outcomes[{index}].{field}")
        normalized.append(row)
    if require_complete and seen != set(planned):
        missing_markets = sorted(set(planned) - seen)
        _error(f"H1 outcome set incomplete: missing {len(missing_markets)} markets; first={missing_markets[:5]}")
    return tuple(normalized)


def collect_h1_outcomes(
    client: RawFirstJsonClient,
    *,
    freeze: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
    existing_outcomes: Sequence[Mapping[str, str]] = (),
    on_outcome: Callable[[dict[str, str]], None] | None = None,
) -> tuple[dict[str, str], ...]:
    """Collect only the frozen H1 allow-list; H2/H3 identities are hard denied."""
    existing = validate_h1_outcomes(
        existing_outcomes,
        freeze=freeze,
        universe=universe,
        require_complete=False,
    )
    by_market = {row["market_ticker"]: dict(row) for row in existing}
    planned = _planned_by_market(freeze)
    fingerprint = str(freeze["h1_evaluation_fingerprint"])
    for market_ticker in sorted(planned):
        if market_ticker in by_market:
            continue
        plan = planned[market_ticker]
        assert_not_sealed_identity(
            universe=universe,
            event_ticker=plan.event_ticker,
            market_ticker=plan.market_ticker,
        )
        response = client.get_json(f"/historical/markets/{market_ticker}")
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            _error(f"H1 response for {market_ticker} missing market object")
        returned_ticker = _text(market.get("ticker"), "returned market ticker")
        returned_event = _text(market.get("event_ticker"), "returned event_ticker")
        assert_not_sealed_identity(
            universe=universe,
            event_ticker=returned_event,
            market_ticker=returned_ticker,
        )
        if returned_ticker != market_ticker or returned_event != plan.event_ticker:
            _error(f"H1 outcome identity mismatch for requested market {market_ticker}")
        status = _text(market.get("status"), "market status").lower()
        result_text = _text(market.get("result"), "market result").lower()
        if status != "finalized":
            _error(f"H1 market {market_ticker} is not finalized: {status}")
        if result_text not in {"yes", "no"}:
            _error(f"H1 market {market_ticker} unsupported result {result_text!r}")
        row = {
            "schema_version": H1_OUTCOME_SCHEMA_VERSION,
            "family_id": FAMILY_ID,
            "h1_evaluation_fingerprint": fingerprint,
            "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
            "stage": "H1",
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
    ordered = [by_market[market] for market in sorted(planned)]
    return validate_h1_outcomes(
        ordered,
        freeze=freeze,
        universe=universe,
        require_complete=True,
    )


def initialize_h1_outcome_journal(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    _write_csv(path, H1_OUTCOME_FIELDS, ())


def append_h1_outcome_journal(path: Path, row: Mapping[str, Any]) -> None:
    missing = set(H1_OUTCOME_FIELDS) - set(row)
    extra = set(row) - set(H1_OUTCOME_FIELDS)
    if missing or extra:
        _error(f"H1 journal row schema mismatch; missing={sorted(missing)}, extra={sorted(extra)}")
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(H1_OUTCOME_FIELDS), lineterminator="\n")
        writer.writerow({field: row[field] for field in H1_OUTCOME_FIELDS})



def recover_h1_outcomes_from_manifest(
    *,
    freeze: Mapping[str, Any],
    universe: FrozenCandidateEUniverse,
    repository_root: str | Path,
    manifest_path: str | Path,
) -> tuple[dict[str, str], ...]:
    """Recover only the partial journal belonging to the same frozen H1 attempt."""
    repo = Path(repository_root).resolve()
    manifest_target = Path(manifest_path).resolve()
    document = _read_json(manifest_target)
    collector = document.get("collector")
    arguments = document.get("arguments")
    if not isinstance(collector, Mapping) or collector.get("name") != CP20_COLLECTOR_NAME:
        _error("resume manifest collector mismatch")
    if not isinstance(arguments, Mapping):
        _error("resume manifest arguments missing")
    if arguments.get("h1_evaluation_fingerprint") != freeze.get("h1_evaluation_fingerprint"):
        _error("resume manifest H1 procedure fingerprint mismatch")
    if arguments.get("cohort_map_fingerprint") != FROZEN_COHORT_MAP_FINGERPRINT:
        _error("resume manifest cohort fingerprint mismatch")
    if arguments.get("row_universe_fingerprint") != FROZEN_ROW_UNIVERSE_FINGERPRINT:
        _error("resume manifest row-universe fingerprint mismatch")
    run_id = _text(document.get("run_id"), "resume manifest run_id")
    matches = list((repo / DERIVED_ROOT).rglob(f"{run_id}_candidate_e_h1_outcome_journal.csv"))
    if len(matches) != 1:
        _error(f"expected exactly one H1 outcome journal for {run_id}; found {len(matches)}")
    fields, rows = _read_csv(matches[0])
    if fields != H1_OUTCOME_FIELDS:
        _error("resume H1 outcome journal schema mismatch")
    return validate_h1_outcomes(
        rows,
        freeze=freeze,
        universe=universe,
        require_complete=False,
    )

def _clip_logit_probability(q: float) -> float:
    return market_logit_offset(q)


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def _row_log_loss(probability: float, outcome: int) -> float:
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        return math.inf
    if outcome == 1:
        return math.inf if probability <= 0.0 else -math.log(probability)
    return math.inf if probability >= 1.0 else -math.log1p(-probability)


def _row_brier(probability: float, outcome: int) -> float:
    return (probability - float(outcome)) ** 2


def build_h1_observations(
    *,
    universe: FrozenCandidateEUniverse,
    outcomes: Sequence[Mapping[str, str]],
    freeze: Mapping[str, Any],
) -> tuple[CandidateEObservation, ...]:
    valid_outcomes = validate_h1_outcomes(
        outcomes,
        freeze=freeze,
        universe=universe,
        require_complete=True,
    )
    labels = {row["market_ticker"]: int(row["outcome"]) for row in valid_outcomes}
    observations: list[CandidateEObservation] = []
    seen_state_ids: set[str] = set()
    event_block = {
        row["event_ticker"]: row["block_id"]
        for row in universe.cohort_rows
        if row["stage"] == "H1"
    }
    for index, row in enumerate(universe.preoutcome_rows):
        if row["stage"] != "H1":
            continue
        market = str(row["market_ticker"])
        event = str(row["event_ticker"])
        assert_not_sealed_identity(universe=universe, event_ticker=event, market_ticker=market)
        if market not in labels:
            _error(f"H1 row references missing label {market}")
        block = event_block.get(event)
        if block != row["block_id"]:
            _error(f"H1 row block mismatch for {event}")
        state_id = f"{event}|{market}|TTC{int(row['ttc_target_minutes'])}|{row['structural_role']}"
        if state_id in seen_state_ids:
            _error(f"duplicate H1 state identity {state_id}")
        seen_state_ids.add(state_id)
        observations.append(
            CandidateEObservation(
                state_id=state_id,
                event_ticker=event,
                market_ticker=market,
                block_id=str(block),
                structural_role=str(row["structural_role"]),
                ttc_target_minutes=int(row["ttc_target_minutes"]),
                outcome=labels[market],
                q_market=_float(row["q_market"], f"H1 row {index} q_market"),
                d_btc=_float(row["d_BTC"], f"H1 row {index} d_BTC"),
                r_5m=_float(row["r_5m"], f"H1 row {index} r_5m"),
            )
        )
    if len(observations) != EXPECTED_STAGE_ROW_COUNTS["H1"]:
        _error("H1 observation row count changed")
    if len({row.event_ticker for row in observations}) != EXPECTED_STAGE_EVENT_COUNTS["H1"]:
        _error("H1 observation event count changed")
    return tuple(observations)


def _fit_features(observation: CandidateEObservation, candidate_id: str) -> tuple[float, ...]:
    if candidate_id == DISTANCE_CANDIDATE_ID:
        return (observation.d_btc,)
    if candidate_id == MOMENTUM_CANDIDATE_ID:
        return (observation.d_btc, observation.r_5m)
    _error(f"unfrozen Candidate-E candidate {candidate_id}")
    raise AssertionError


def _objective_gradient_hessian(
    observations: Sequence[CandidateEObservation],
    candidate_id: str,
    beta: Sequence[float],
) -> tuple[float, list[float], list[list[float]]]:
    events: dict[str, int] = {}
    for observation in observations:
        events[observation.event_ticker] = events.get(observation.event_ticker, 0) + 1
    if not events:
        _error("Candidate-E fit received no events")
    dimension = len(beta)
    objective = 0.0
    gradient = [0.0] * dimension
    hessian = [[0.0] * dimension for _ in range(dimension)]
    event_scale = 1.0 / float(len(events))
    for observation in observations:
        x = _fit_features(observation, candidate_id)
        if len(x) != dimension:
            _error("Candidate-E fit dimension mismatch")
        weight = event_scale / float(events[observation.event_ticker])
        linear = _clip_logit_probability(observation.q_market) + sum(b * v for b, v in zip(beta, x))
        probability = _sigmoid(linear)
        loss = _row_log_loss(probability, observation.outcome)
        if not math.isfinite(loss):
            return math.inf, [math.nan] * dimension, [[math.nan] * dimension for _ in range(dimension)]
        objective += weight * loss
        residual = probability - observation.outcome
        variance = probability * (1.0 - probability)
        for i in range(dimension):
            gradient[i] += weight * residual * x[i]
            for j in range(dimension):
                hessian[i][j] += weight * variance * x[i] * x[j]
    return objective, gradient, hessian


def _solve_positive_hessian(hessian: Sequence[Sequence[float]], gradient: Sequence[float]) -> list[float]:
    if len(gradient) == 1:
        h = hessian[0][0]
        if not math.isfinite(h) or h <= 0.0:
            _error("Candidate-E Newton Hessian is singular/non-positive")
        return [gradient[0] / h]
    if len(gradient) == 2:
        a, b = hessian[0]
        c, d = hessian[1]
        determinant = a * d - b * c
        scale = max(abs(a * d), abs(b * c), 1.0)
        if not math.isfinite(determinant) or abs(determinant) <= 1e-15 * scale:
            _error("Candidate-E Newton Hessian is singular")
        return [
            (d * gradient[0] - b * gradient[1]) / determinant,
            (-c * gradient[0] + a * gradient[1]) / determinant,
        ]
    _error("Candidate-E optimizer only supports frozen 1D/2D candidates")
    raise AssertionError


def fit_candidate_e(
    observations: Sequence[CandidateEObservation],
    *,
    candidate_id: str,
    fold: int,
    fit_blocks: Sequence[str],
    score_block: str,
) -> CandidateEFit:
    predeclaration = candidate_e_predeclaration()
    optimizer = predeclaration["fit_contract"]["optimizer"]
    if optimizer != {
        "algorithm": "deterministic_damped_Newton",
        "max_iterations": 100,
        "gradient_l2_tolerance": "1e-8",
        "armijo_constant": "1e-4",
        "minimum_step_scale": "2^-40",
        "non_convergence": "fail_closed",
        "singular_hessian": "fail_closed",
    }:
        _error("Candidate-E optimizer contract changed")
    dimension = 1 if candidate_id == DISTANCE_CANDIDATE_ID else 2 if candidate_id == MOMENTUM_CANDIDATE_ID else 0
    if dimension == 0:
        _error(f"unfrozen Candidate-E candidate {candidate_id}")
    beta = [0.0] * dimension
    tolerance = 1e-8
    armijo = 1e-4
    minimum_step = 2.0 ** -40
    last_objective = math.inf
    for iteration in range(0, 101):
        objective, gradient, hessian = _objective_gradient_hessian(observations, candidate_id, beta)
        if not math.isfinite(objective) or any(not math.isfinite(value) for value in gradient):
            _error("Candidate-E fit objective/gradient became non-finite")
        gradient_norm = math.sqrt(sum(value * value for value in gradient))
        if gradient_norm <= tolerance:
            return CandidateEFit(
                candidate_id=candidate_id,
                fold=fold,
                fit_blocks=tuple(fit_blocks),
                score_block=score_block,
                beta_distance=beta[0],
                beta_momentum=beta[1] if dimension == 2 else None,
                iterations=iteration,
                converged=True,
                fit_objective=objective,
            )
        if iteration >= 100:
            break
        step = _solve_positive_hessian(hessian, gradient)
        directional = sum(g * s for g, s in zip(gradient, step))
        if not math.isfinite(directional) or directional <= 0.0:
            _error("Candidate-E Newton direction is not a descent direction")
        scale = 1.0
        accepted = False
        while scale >= minimum_step:
            proposal = [b - scale * s for b, s in zip(beta, step)]
            proposal_objective, _, _ = _objective_gradient_hessian(observations, candidate_id, proposal)
            if math.isfinite(proposal_objective) and proposal_objective <= objective - armijo * scale * directional:
                beta = proposal
                last_objective = proposal_objective
                accepted = True
                break
            scale *= 0.5
        if not accepted:
            _error("Candidate-E damped Newton line search failed closed")
    _error(f"Candidate-E {candidate_id} fold {fold} did not converge; last_objective={last_objective}")
    raise AssertionError


def predict_candidate_e(observation: CandidateEObservation, fit: CandidateEFit) -> float:
    x = _fit_features(observation, fit.candidate_id)
    beta = [fit.beta_distance] if fit.beta_momentum is None else [fit.beta_distance, fit.beta_momentum]
    linear = _clip_logit_probability(observation.q_market) + sum(b * v for b, v in zip(beta, x))
    probability = _sigmoid(linear)
    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        _error("Candidate-E prediction became invalid")
    return probability


def _event_equal_metrics(
    rows: Sequence[Mapping[str, Any]],
    probability_key: str,
) -> tuple[float, float, dict[str, tuple[float, float]]]:
    event_losses: dict[str, list[float]] = {}
    event_briers: dict[str, list[float]] = {}
    for row in rows:
        event = str(row["event_ticker"])
        probability = float(row[probability_key])
        outcome = int(row["outcome"])
        event_losses.setdefault(event, []).append(_row_log_loss(probability, outcome))
        event_briers.setdefault(event, []).append(_row_brier(probability, outcome))
    if not event_losses:
        _error("metric calculation received no events")
    event_metrics: dict[str, tuple[float, float]] = {}
    for event in event_losses:
        losses = event_losses[event]
        briers = event_briers[event]
        event_metrics[event] = (
            sum(losses) / len(losses) if all(math.isfinite(value) for value in losses) else math.inf,
            sum(briers) / len(briers),
        )
    pooled_loss = sum(value[0] for value in event_metrics.values()) / len(event_metrics)
    pooled_brier = sum(value[1] for value in event_metrics.values()) / len(event_metrics)
    return pooled_loss, pooled_brier, event_metrics


def _score_candidate(
    observations: Sequence[CandidateEObservation],
    candidate_id: str,
) -> tuple[list[dict[str, Any]], list[CandidateEFit]]:
    predictions: list[dict[str, Any]] = []
    fits: list[CandidateEFit] = []
    for fold_spec in _expected_rolling_folds():
        fit_blocks = tuple(fold_spec["fit_blocks"])
        score_block = str(fold_spec["score_block"])
        fit_rows = [row for row in observations if row.block_id in fit_blocks]
        score_rows = [row for row in observations if row.block_id == score_block]
        if not fit_rows or not score_rows:
            _error(f"fold {fold_spec['fold']} missing fit/score rows")
        fit = fit_candidate_e(
            fit_rows,
            candidate_id=candidate_id,
            fold=int(fold_spec["fold"]),
            fit_blocks=fit_blocks,
            score_block=score_block,
        )
        fits.append(fit)
        for observation in score_rows:
            predictions.append(
                {
                    "candidate_id": candidate_id,
                    "fold": int(fold_spec["fold"]),
                    "score_block": score_block,
                    "state_id": observation.state_id,
                    "event_ticker": observation.event_ticker,
                    "market_ticker": observation.market_ticker,
                    "structural_role": observation.structural_role,
                    "ttc_target_minutes": observation.ttc_target_minutes,
                    "outcome": observation.outcome,
                    "q_market": observation.q_market,
                    "candidate_probability": predict_candidate_e(observation, fit),
                }
            )
    scored_events = {row["event_ticker"] for row in predictions}
    if len(scored_events) != EXPECTED_H1_SCORED_EVENTS:
        _error(f"H1 OOF scored event count changed: {len(scored_events)}")
    return predictions, fits


def _structural_coverage_ok(predictions: Sequence[Mapping[str, Any]]) -> bool:
    required_roles = {"q10", "q30", "q50", "q70", "q90"}
    required_ttc = {55, 50, 45, 40, 35, 30}
    for block in ("B2", "B3", "B4", "B5", "B6"):
        block_rows = [row for row in predictions if row["score_block"] == block]
        if {row["structural_role"] for row in block_rows} != required_roles:
            return False
        if {int(row["ttc_target_minutes"]) for row in block_rows} != required_ttc:
            return False
    return True


def _candidate_metrics(
    predictions: Sequence[Mapping[str, Any]],
    fits: Sequence[CandidateEFit],
) -> dict[str, Any]:
    raw_loss, raw_brier, raw_events = _event_equal_metrics(predictions, "q_market")
    candidate_loss, candidate_brier, candidate_events = _event_equal_metrics(predictions, "candidate_probability")
    if set(raw_events) != set(candidate_events):
        _error("raw/candidate event sets differ")
    event_deltas = {event: raw_events[event][0] - candidate_events[event][0] for event in raw_events}
    block_deltas: list[float] = []
    block_metrics: dict[str, dict[str, float]] = {}
    for block in ("B2", "B3", "B4", "B5", "B6"):
        block_rows = [row for row in predictions if row["score_block"] == block]
        raw_block_loss, raw_block_brier, _ = _event_equal_metrics(block_rows, "q_market")
        candidate_block_loss, candidate_block_brier, _ = _event_equal_metrics(block_rows, "candidate_probability")
        delta = raw_block_loss - candidate_block_loss
        block_deltas.append(delta)
        block_metrics[block] = {
            "raw_log_loss": raw_block_loss,
            "candidate_log_loss": candidate_block_loss,
            "raw_minus_candidate_log_loss": delta,
            "raw_brier": raw_block_brier,
            "candidate_brier": candidate_block_brier,
            "raw_minus_candidate_brier": raw_block_brier - candidate_block_brier,
        }
    all_fits_valid = (
        len(fits) == 5
        and all(fit.converged for fit in fits)
        and all(math.isfinite(fit.beta_distance) for fit in fits)
        and all(fit.beta_momentum is None or math.isfinite(fit.beta_momentum) for fit in fits)
        and all(math.isfinite(float(row["candidate_probability"])) for row in predictions)
        and all(math.isfinite(value) for value in (raw_loss, raw_brier, candidate_loss, candidate_brier))
    )
    structural_ok = _structural_coverage_ok(predictions)
    median_delta = median(event_deltas.values())
    raw_gate = passes_raw_advancement_gate(
        pooled_log_loss_delta=raw_loss - candidate_loss,
        pooled_brier_delta=raw_brier - candidate_brier,
        score_block_log_loss_deltas=block_deltas,
        median_event_log_loss_delta=median_delta,
        all_fits_valid=all_fits_valid,
        beta_distance_by_fold=[fit.beta_distance for fit in fits],
        structural_coverage_ok=structural_ok,
        policy_firewall_ok=True,
    )
    return {
        "raw_log_loss": raw_loss,
        "raw_brier": raw_brier,
        "candidate_log_loss": candidate_loss,
        "candidate_brier": candidate_brier,
        "pooled_log_loss_delta": raw_loss - candidate_loss,
        "pooled_brier_delta": raw_brier - candidate_brier,
        "block_metrics": block_metrics,
        "block_log_loss_deltas": block_deltas,
        "event_deltas": event_deltas,
        "median_event_log_loss_delta": median_delta,
        "all_fits_valid": all_fits_valid,
        "structural_coverage_ok": structural_ok,
        "raw_gate_passed": raw_gate,
    }


def evaluate_h1(
    *,
    universe: FrozenCandidateEUniverse,
    freeze: Mapping[str, Any],
    outcomes: Sequence[Mapping[str, str]],
) -> CandidateEEvaluation:
    """Fit and score exactly the two frozen Candidate-E variants once on H1."""
    validate_h1_evaluation_freeze_document(freeze, universe=universe)
    observations = build_h1_observations(universe=universe, outcomes=outcomes, freeze=freeze)
    distance_predictions, distance_fits = _score_candidate(observations, DISTANCE_CANDIDATE_ID)
    momentum_predictions, momentum_fits = _score_candidate(observations, MOMENTUM_CANDIDATE_ID)
    distance_by_state = {row["state_id"]: row for row in distance_predictions}
    momentum_by_state = {row["state_id"]: row for row in momentum_predictions}
    if set(distance_by_state) != set(momentum_by_state):
        _error("Candidate-E variants are not scored on identical OOF rows")
    distance_metrics = _candidate_metrics(distance_predictions, distance_fits)
    momentum_metrics = _candidate_metrics(momentum_predictions, momentum_fits)

    comparison_rows: list[dict[str, Any]] = []
    for state_id in sorted(distance_by_state):
        d = distance_by_state[state_id]
        m = momentum_by_state[state_id]
        if (d["event_ticker"], d["market_ticker"], d["outcome"], d["q_market"], d["score_block"]) != (
            m["event_ticker"], m["market_ticker"], m["outcome"], m["q_market"], m["score_block"]
        ):
            _error("Candidate-E variant OOF row identity mismatch")
        comparison_rows.append(
            {
                "event_ticker": d["event_ticker"],
                "score_block": d["score_block"],
                "outcome": d["outcome"],
                "distance_probability": d["candidate_probability"],
                "momentum_probability": m["candidate_probability"],
            }
        )
    distance_loss, distance_brier, distance_events = _event_equal_metrics(comparison_rows, "distance_probability")
    momentum_loss, momentum_brier, momentum_events = _event_equal_metrics(comparison_rows, "momentum_probability")
    event_nested = {
        event: distance_events[event][0] - momentum_events[event][0]
        for event in distance_events
    }
    nested_block_deltas: list[float] = []
    for block in ("B2", "B3", "B4", "B5", "B6"):
        block_rows = [row for row in comparison_rows if row["score_block"] == block]
        d_loss, _, _ = _event_equal_metrics(block_rows, "distance_probability")
        m_loss, _, _ = _event_equal_metrics(block_rows, "momentum_probability")
        nested_block_deltas.append(d_loss - m_loss)
    nested_pass = passes_nested_complexity_gate(
        pooled_log_loss_delta_distance_minus_momentum=distance_loss - momentum_loss,
        pooled_brier_delta_distance_minus_momentum=distance_brier - momentum_brier,
        score_block_log_loss_deltas_distance_minus_momentum=nested_block_deltas,
        median_event_log_loss_delta_distance_minus_momentum=median(event_nested.values()),
    )
    selected = select_candidate_e(
        distance_passes_raw=bool(distance_metrics["raw_gate_passed"]),
        momentum_passes_raw=bool(momentum_metrics["raw_gate_passed"]),
        momentum_passes_complexity=nested_pass,
    )

    fingerprint = str(freeze["h1_evaluation_fingerprint"])
    summary = {
        "schema_version": H1_SUMMARY_SCHEMA_VERSION,
        "family_id": FAMILY_ID,
        "h1_evaluation_fingerprint": fingerprint,
        "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
        "H1_event_count": EXPECTED_STAGE_EVENT_COUNTS["H1"],
        "H1_row_count": EXPECTED_STAGE_ROW_COUNTS["H1"],
        "OOF_scored_event_count": EXPECTED_H1_SCORED_EVENTS,
        "distance_raw_event_equal_log_loss": _float_text(distance_metrics["raw_log_loss"]),
        "distance_candidate_event_equal_log_loss": _float_text(distance_metrics["candidate_log_loss"]),
        "distance_raw_minus_candidate_log_loss": _float_text(distance_metrics["pooled_log_loss_delta"]),
        "distance_raw_event_equal_brier": _float_text(distance_metrics["raw_brier"]),
        "distance_candidate_event_equal_brier": _float_text(distance_metrics["candidate_brier"]),
        "distance_raw_minus_candidate_brier": _float_text(distance_metrics["pooled_brier_delta"]),
        "distance_median_event_log_loss_delta": _float_text(distance_metrics["median_event_log_loss_delta"]),
        "distance_raw_gate_passed": bool(distance_metrics["raw_gate_passed"]),
        "momentum_raw_event_equal_log_loss": _float_text(momentum_metrics["raw_log_loss"]),
        "momentum_candidate_event_equal_log_loss": _float_text(momentum_metrics["candidate_log_loss"]),
        "momentum_raw_minus_candidate_log_loss": _float_text(momentum_metrics["pooled_log_loss_delta"]),
        "momentum_raw_event_equal_brier": _float_text(momentum_metrics["raw_brier"]),
        "momentum_candidate_event_equal_brier": _float_text(momentum_metrics["candidate_brier"]),
        "momentum_raw_minus_candidate_brier": _float_text(momentum_metrics["pooled_brier_delta"]),
        "momentum_median_event_log_loss_delta": _float_text(momentum_metrics["median_event_log_loss_delta"]),
        "momentum_raw_gate_passed": bool(momentum_metrics["raw_gate_passed"]),
        "nested_distance_minus_momentum_log_loss": _float_text(distance_loss - momentum_loss),
        "nested_distance_minus_momentum_brier": _float_text(distance_brier - momentum_brier),
        "nested_median_event_log_loss_delta": _float_text(median(event_nested.values())),
        "momentum_nested_complexity_gate_passed": bool(nested_pass),
        "selection": selected,
        "H1_permanently_development_exposed": True,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "posthoc_repair_performed": False,
        "feature_change_performed": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }

    fold_rows: list[dict[str, str]] = []
    coefficient_rows: list[dict[str, str]] = []
    prediction_rows: list[dict[str, str]] = []
    event_score_rows: list[dict[str, str]] = []
    for candidate_id, predictions, fits, metrics in (
        (DISTANCE_CANDIDATE_ID, distance_predictions, distance_fits, distance_metrics),
        (MOMENTUM_CANDIDATE_ID, momentum_predictions, momentum_fits, momentum_metrics),
    ):
        for fit in fits:
            block = fit.score_block
            bm = metrics["block_metrics"][block]
            fold_rows.append({
                "schema_version": H1_FOLD_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": candidate_id,
                "h1_evaluation_fingerprint": fingerprint,
                "fold": str(fit.fold),
                "fit_blocks": ",".join(fit.fit_blocks),
                "score_block": block,
                "raw_log_loss": _float_text(bm["raw_log_loss"]),
                "candidate_log_loss": _float_text(bm["candidate_log_loss"]),
                "raw_minus_candidate_log_loss": _float_text(bm["raw_minus_candidate_log_loss"]),
                "raw_brier": _float_text(bm["raw_brier"]),
                "candidate_brier": _float_text(bm["candidate_brier"]),
                "raw_minus_candidate_brier": _float_text(bm["raw_minus_candidate_brier"]),
            })
            coefficient_rows.append({
                "schema_version": H1_COEFFICIENT_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": candidate_id,
                "h1_evaluation_fingerprint": fingerprint,
                "fold": str(fit.fold),
                "score_block": fit.score_block,
                "beta_distance": _float_text(fit.beta_distance),
                "beta_momentum": "" if fit.beta_momentum is None else _float_text(fit.beta_momentum),
                "iterations": str(fit.iterations),
                "converged": str(fit.converged).lower(),
                "fit_objective": _float_text(fit.fit_objective),
            })
        for row in predictions:
            prediction_rows.append({
                "schema_version": H1_PREDICTION_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": candidate_id,
                "h1_evaluation_fingerprint": fingerprint,
                "fold": str(row["fold"]),
                "score_block": str(row["score_block"]),
                "state_id": str(row["state_id"]),
                "event_ticker": str(row["event_ticker"]),
                "market_ticker": str(row["market_ticker"]),
                "outcome": str(row["outcome"]),
                "q_market": _float_text(float(row["q_market"])),
                "candidate_probability": _float_text(float(row["candidate_probability"])),
            })
        _, _, raw_events = _event_equal_metrics(predictions, "q_market")
        _, _, candidate_events = _event_equal_metrics(predictions, "candidate_probability")
        event_block = {row["event_ticker"]: row["score_block"] for row in predictions}
        for event in sorted(raw_events):
            event_score_rows.append({
                "schema_version": H1_EVENT_SCORE_SCHEMA_VERSION,
                "family_id": FAMILY_ID,
                "candidate_id": candidate_id,
                "h1_evaluation_fingerprint": fingerprint,
                "event_ticker": event,
                "score_block": str(event_block[event]),
                "raw_log_loss": _float_text(raw_events[event][0]),
                "candidate_log_loss": _float_text(candidate_events[event][0]),
                "raw_minus_candidate_log_loss": _float_text(raw_events[event][0] - candidate_events[event][0]),
                "raw_brier": _float_text(raw_events[event][1]),
                "candidate_brier": _float_text(candidate_events[event][1]),
                "raw_minus_candidate_brier": _float_text(raw_events[event][1] - candidate_events[event][1]),
            })
    return CandidateEEvaluation(
        summary=summary,
        fold_rows=tuple(fold_rows),
        coefficient_rows=tuple(coefficient_rows),
        prediction_rows=tuple(prediction_rows),
        event_score_rows=tuple(event_score_rows),
    )


def h1_result_fingerprint(summary: Mapping[str, Any]) -> str:
    return _canonical_sha256(dict(summary))


def write_h1_evaluation_outputs(
    output_dir: Path,
    *,
    run_id: str,
    outcomes: Sequence[Mapping[str, str]],
    evaluation: CandidateEEvaluation,
    outcome_journal_path: Path,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = output_dir / f"{run_id}_candidate_e_h1_outcomes.csv"
    summary_path = output_dir / f"{run_id}_candidate_e_h1_summary.json"
    folds_path = output_dir / f"{run_id}_candidate_e_h1_fold_scores.csv"
    coefficients_path = output_dir / f"{run_id}_candidate_e_h1_coefficients.csv"
    predictions_path = output_dir / f"{run_id}_candidate_e_h1_oof_predictions.csv"
    events_path = output_dir / f"{run_id}_candidate_e_h1_event_scores.csv"
    _write_csv(outcomes_path, H1_OUTCOME_FIELDS, outcomes)
    summary_path.write_text(json.dumps(evaluation.summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(folds_path, tuple(evaluation.fold_rows[0].keys()), evaluation.fold_rows)
    _write_csv(coefficients_path, tuple(evaluation.coefficient_rows[0].keys()), evaluation.coefficient_rows)
    _write_csv(predictions_path, tuple(evaluation.prediction_rows[0].keys()), evaluation.prediction_rows)
    _write_csv(events_path, tuple(evaluation.event_score_rows[0].keys()), evaluation.event_score_rows)
    return (
        outcome_journal_path,
        outcomes_path,
        summary_path,
        folds_path,
        coefficients_path,
        predictions_path,
        events_path,
    )


__all__ = [
    "CP20_COLLECTOR_NAME",
    "DEFAULT_H1_ATTEMPT_PATH",
    "DEFAULT_H1_FREEZE_PATH",
    "DERIVED_ROOT",
    "DISTANCE_CANDIDATE_ID",
    "FROZEN_COHORT_MAP_FINGERPRINT",
    "FROZEN_ROW_UNIVERSE_FINGERPRINT",
    "H1_OUTCOME_FIELDS",
    "KxbtcdCandidateEH1EvaluationError",
    "MOMENTUM_CANDIDATE_ID",
    "append_h1_outcome_journal",
    "assert_clean_synchronized_repository",
    "assert_not_sealed_identity",
    "build_h1_evaluation_freeze_document",
    "build_h1_observations",
    "build_h1_request_plan",
    "collect_h1_outcomes",
    "evaluate_h1",
    "fit_candidate_e",
    "h1_preflight",
    "h1_result_fingerprint",
    "initialize_h1_outcome_journal",
    "load_and_validate_frozen_universe",
    "load_and_validate_h1_evaluation_freeze",
    "matching_prior_h1_manifests",
    "predict_candidate_e",
    "recover_h1_outcomes_from_manifest",
    "update_h1_attempt_receipt",
    "validate_h1_evaluation_freeze_document",
    "validate_h1_outcomes",
    "validate_stage_identity_disjointness",
    "write_h1_evaluation_outputs",
    "write_or_validate_h1_evaluation_freeze",
]
