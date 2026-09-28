"""Checkpoint-20C Candidate-E full-H1 Distance fit and H2 validation freeze.

This module is deliberately network-free.

It does exactly two research actions:
1. fit the already-selected Distance specification on all exposed H1 events;
2. freeze the H2-only validation contract from the already-frozen pre-outcome
   H2/H3 identities.

It never reads H2/H3 outcomes, never fits on H2/H3, never changes the selected
candidate, and never enables execution.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_h1_evaluation import (
    CandidateEObservation,
    DISTANCE_CANDIDATE_ID,
    H1_OUTCOME_FIELDS,
    fit_candidate_e,
    load_and_validate_frozen_universe,
    load_and_validate_h1_evaluation_freeze,
)
from .kxbtcd_candidate_e_h1_result_closeout import (
    EXPECTED_RESULT_FINGERPRINT as H1_RESULT_FINGERPRINT,
    RUN_ID as H1_RUN_ID,
    load_and_validate_result,
)
from .kxbtcd_candidate_e_predeclaration import (
    FROZEN_PREDECLARATION_FINGERPRINT,
    candidate_e_predeclaration,
)
from .kxbtcd_candidate_e_coinbase_primary_materialization import (
    FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
)
from .kxbtcd_candidate_e_historical_materialization import (
    FROZEN_CONTRACT_FINGERPRINT,
    STRUCTURAL_ROLES,
    TTC_TARGET_MINUTES,
)

EXPECTED_BASELINE_COMMIT = "c4a65dbac17f6b07acf2723d56a281b339bd1d41"
EXPECTED_H1_EVALUATION_FINGERPRINT = (
    "cbbca76de2dd87edd6c6bc4f21ae1005fbd1402a3bb85374e7699c8fb5fb7d14"
)
EXPECTED_COHORT_MAP_FINGERPRINT = (
    "09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa"
)
EXPECTED_ROW_UNIVERSE_FINGERPRINT = (
    "e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5"
)

H1_EVENT_COUNT = 1500
H1_ROW_COUNT = 36314
H2_EVENT_COUNT = 750
H2_ROW_COUNT = 22354
H3_EVENT_COUNT = 750
H3_ROW_COUNT = 22409
H2_BLOCKS = ("B0", "B1", "B2", "B3", "B4")
H2_EVENTS_PER_BLOCK = 150

FINAL_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_final_distance_model.v1"
H2_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_h2_validation_freeze.v1"
FINAL_FIT_ATTEMPT_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_final_fit_attempt.v1"

DEFAULT_FINAL_MODEL_PATH = Path("configs/kxbtcd_candidate_e_h1_final_distance_model.json")
DEFAULT_H2_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_h2_validation_freeze.json")
DEFAULT_FINAL_FIT_ATTEMPT_PATH = Path(
    "data/analysis/kxbtcd_candidate_e_h1_final_fit/final_fit_attempt.json"
)
H1_OUTCOMES_PATH = Path(
    "data/derived/kxbtcd_candidate_e_h1_evaluation/2026/08/17/"
    f"{H1_RUN_ID}_candidate_e_h1_outcomes.csv"
)
H1_SUMMARY_PATH = Path(
    "data/derived/kxbtcd_candidate_e_h1_evaluation/2026/08/17/"
    f"{H1_RUN_ID}_candidate_e_h1_summary.json"
)

FIT_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_h1_evaluation.py",
    "src/kxbtcd_candidate_e_h2_preparation.py",
)


class CandidateEH2PreparationError(RuntimeError):
    """Raised when any Checkpoint-20C invariant is violated."""


def _error(message: str) -> None:
    raise CandidateEH2PreparationError(message)


def _repo_path(repo: Path, path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else repo / p


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEH2PreparationError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be an object: {path}")
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _read_csv(path: Path) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(reader.fieldnames or ())
            rows = tuple(dict(row) for row in reader)
    except OSError as exc:
        raise CandidateEH2PreparationError(f"could not read CSV {path}: {exc}") from exc
    return fields, rows


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _float_text(value: float) -> str:
    if not math.isfinite(value):
        _error("attempted to serialize non-finite model value")
    return format(value, ".17g")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        _error(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def assert_expected_repository_baseline(repository_root: str | Path = ".") -> None:
    """Require the exact cleanly-closed Checkpoint-20B lineage commit.

    The worktree may already contain the extracted 20C files, so this check binds
    HEAD/origin/main rather than requiring an empty worktree.
    """
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("Checkpoint-20C preparation requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != EXPECTED_BASELINE_COMMIT or remote != EXPECTED_BASELINE_COMMIT:
        _error(
            "Checkpoint-20C baseline mismatch; expected HEAD == origin/main == "
            f"{EXPECTED_BASELINE_COMMIT}, got HEAD={head}, origin/main={remote}"
        )


def _implementation_sha256s(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in FIT_IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"missing fit implementation file {relative}")
        result[relative] = _sha256_file(path)
    return result


def _validate_h1_outcomes_fast(
    outcomes: Sequence[Mapping[str, str]],
    *,
    freeze: Mapping[str, Any],
    universe,
) -> tuple[dict[str, str], ...]:
    """Validate H1 outcomes with H2/H3 deny sets built once.

    The original H1 validator is intentionally conservative but calls the sealed-
    identity helper once per row; that helper reconstructs the full H2/H3 deny
    sets each time. With 6,631 H1 labels this is needlessly quadratic. This
    equivalent validator precomputes those frozen identity sets once, then keeps
    the same allow-list, schema, finalized-result, completeness, and firewall
    checks in a single linear pass.
    """
    fingerprint = str(freeze.get("h1_evaluation_fingerprint", ""))
    if fingerprint != EXPECTED_H1_EVALUATION_FINGERPRINT:
        _error("H1 outcome validation procedure fingerprint changed")

    entries = freeze.get("h1_request_plan")
    if not isinstance(entries, list) or not entries:
        _error("H1 frozen request plan missing")
    planned: dict[str, str] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping) or set(entry) != {"event_ticker", "market_ticker"}:
            _error(f"H1 request-plan entry {index} schema mismatch")
        event = str(entry["event_ticker"])
        market = str(entry["market_ticker"])
        if market in planned:
            _error(f"duplicate H1 planned market {market}")
        planned[market] = event

    sealed_events = {
        str(row["event_ticker"])
        for row in universe.cohort_rows
        if row["stage"] in {"H2", "H3"}
    }
    sealed_markets = {
        str(row["market_ticker"])
        for row in universe.preoutcome_rows
        if row["stage"] in {"H2", "H3"}
    }

    expected_fields = set(H1_OUTCOME_FIELDS)
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, original in enumerate(outcomes):
        row = dict(original)
        missing = expected_fields - set(row)
        extra = set(row) - expected_fields
        if missing or extra:
            _error(
                f"H1 outcome row {index} schema mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )

        expected = {
            "schema_version": "kxbtcd_candidate_e_h1_outcome.v1",
            "family_id": "kxbtcd_independent_btc_offset_successor.v1",
            "h1_evaluation_fingerprint": fingerprint,
            "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
            "stage": "H1",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                _error(f"H1 outcome row {index} {key} mismatch")

        market = str(row["market_ticker"])
        event = str(row["event_ticker"])
        if event in sealed_events:
            _error(f"H1 outcomes contain sealed H2/H3 event identity: {event}")
        if market in sealed_markets:
            _error(f"H1 outcomes contain sealed H2/H3 market identity: {market}")
        if market in seen:
            _error(f"duplicate H1 outcome market {market}")
        seen.add(market)

        planned_event = planned.get(market)
        if planned_event != event:
            _error(f"unplanned H1 outcome identity: {event}/{market}")
        if row["market_status"] != "finalized":
            _error(f"H1 market {market} is not finalized")
        if (row["result_text"], row["outcome"]) not in {("yes", "1"), ("no", "0")}:
            _error(f"H1 result/outcome mismatch for {market}")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            if not str(row[field]).strip():
                _error(f"H1 outcome row {index} {field} is blank")
        normalized.append(row)

    if seen != set(planned):
        missing = sorted(set(planned) - seen)
        extra = sorted(seen - set(planned))
        _error(
            "H1 outcome set does not exactly match frozen allow-list; "
            f"missing={len(missing)}, extra={len(extra)}, first_missing={missing[:5]}"
        )
    return tuple(normalized)


def _build_h1_observations_fast(
    *,
    universe,
    outcomes: Sequence[Mapping[str, str]],
    freeze: Mapping[str, Any],
) -> tuple[CandidateEObservation, ...]:
    valid = _validate_h1_outcomes_fast(outcomes, freeze=freeze, universe=universe)
    labels = {row["market_ticker"]: int(row["outcome"]) for row in valid}
    event_block = {
        str(row["event_ticker"]): str(row["block_id"])
        for row in universe.cohort_rows
        if row["stage"] == "H1"
    }
    observations: list[CandidateEObservation] = []
    seen_state_ids: set[str] = set()
    for index, row in enumerate(universe.preoutcome_rows):
        if row["stage"] != "H1":
            continue
        market = str(row["market_ticker"])
        event = str(row["event_ticker"])
        if market not in labels:
            _error(f"H1 row references missing label {market}")
        block = event_block.get(event)
        if block != str(row["block_id"]):
            _error(f"H1 row block mismatch for {event}")
        state_id = (
            f"{event}|{market}|TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in seen_state_ids:
            _error(f"duplicate H1 state identity {state_id}")
        seen_state_ids.add(state_id)
        try:
            q_market = float(row["q_market"])
            d_btc = float(row["d_BTC"])
            r_5m = float(row["r_5m"])
        except (TypeError, ValueError) as exc:
            raise CandidateEH2PreparationError(
                f"H1 preoutcome numeric parse failed at row {index}"
            ) from exc
        if not all(math.isfinite(value) for value in (q_market, d_btc, r_5m)):
            _error(f"H1 preoutcome row {index} contains non-finite model input")
        observations.append(
            CandidateEObservation(
                state_id=state_id,
                event_ticker=event,
                market_ticker=market,
                block_id=block,
                structural_role=str(row["structural_role"]),
                ttc_target_minutes=int(row["ttc_target_minutes"]),
                outcome=labels[market],
                q_market=q_market,
                d_btc=d_btc,
                r_5m=r_5m,
            )
        )

    if len(observations) != H1_ROW_COUNT:
        _error(f"H1 observation row count changed: {len(observations)}")
    if len({row.event_ticker for row in observations}) != H1_EVENT_COUNT:
        _error("H1 observation event count changed")
    return tuple(observations)


def _load_h1_outcomes_and_universe(repo: Path):
    # First validate the canonical H1 result/manifest/attempt chain.
    summary = load_and_validate_result(repo)
    if summary.get("selection") != DISTANCE_CANDIDATE_ID:
        _error("H1 closeout no longer selects the Distance candidate")
    if summary.get("h1_evaluation_fingerprint") != EXPECTED_H1_EVALUATION_FINGERPRINT:
        _error("H1 evaluation fingerprint changed")
    if summary.get("H2_outcomes_opened") is not False or summary.get("H3_outcomes_opened") is not False:
        _error("H1 closeout indicates H2/H3 exposure")

    freeze, universe = load_and_validate_h1_evaluation_freeze(repository_root=repo)
    if freeze.get("h1_evaluation_fingerprint") != EXPECTED_H1_EVALUATION_FINGERPRINT:
        _error("stored H1 procedure fingerprint changed")

    fields, outcomes = _read_csv(repo / H1_OUTCOMES_PATH)
    if fields != H1_OUTCOME_FIELDS:
        _error("H1 outcome file schema changed")
    valid = _validate_h1_outcomes_fast(
        outcomes,
        freeze=freeze,
        universe=universe,
    )
    return summary, freeze, universe, valid


def _final_model_payload(
    *,
    beta_distance: float,
    iterations: int,
    fit_objective: float,
    repo: Path,
) -> dict[str, Any]:
    if not math.isfinite(beta_distance) or beta_distance <= 0.0:
        _error("full-H1 Distance coefficient must be finite and positive")
    if iterations < 0 or iterations > 100:
        _error("full-H1 fit iteration count invalid")
    if not math.isfinite(fit_objective):
        _error("full-H1 fit objective is non-finite")
    predecl = candidate_e_predeclaration()
    payload = {
        "schema_version": FINAL_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "20C",
        "family_id": predecl["family_id"],
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_evaluation_fingerprint": EXPECTED_H1_EVALUATION_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "fit_scope": {
            "stage": "H1",
            "event_count": H1_EVENT_COUNT,
            "row_count": H1_ROW_COUNT,
            "blocks": ["B0", "B1", "B2", "B3", "B4", "B5", "B6"],
            "all_H1_events_used": True,
            "H2_rows_used": 0,
            "H3_rows_used": 0,
        },
        "model": {
            "formula": "logit(p)=market_logit_offset + beta_distance*d_BTC",
            "market_logit_offset_clip": "0.001",
            "feature": "btc_strike_log_distance_bps.v1",
            "beta_distance": _float_text(beta_distance),
            "beta_momentum": None,
            "free_parameter_count": 1,
        },
        "fit_contract": predecl["fit_contract"],
        "fit_result": {
            "iterations": iterations,
            "converged": True,
            "fit_objective": _float_text(fit_objective),
        },
        "lineage": {
            "h1_outcomes_path": H1_OUTCOMES_PATH.as_posix(),
            "h1_outcomes_sha256": _sha256_file(repo / H1_OUTCOMES_PATH),
            "h1_summary_path": H1_SUMMARY_PATH.as_posix(),
            "h1_summary_sha256": _sha256_file(repo / H1_SUMMARY_PATH),
            "source_baseline_commit": EXPECTED_BASELINE_COMMIT,
            "fit_implementation_sha256s": _implementation_sha256s(repo),
        },
        "selection_frozen_before_full_fit": True,
        "posthoc_H1_feature_change_performed": False,
        "posthoc_H1_candidate_change_performed": False,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    return payload


def validate_final_model_document(
    document: Mapping[str, Any],
    *,
    repository_root: str | Path = ".",
    verify_current_lineage_files: bool = True,
) -> dict[str, Any]:
    repo = Path(repository_root).resolve()
    expected = {
        "schema_version": FINAL_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "20C",
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_evaluation_fingerprint": EXPECTED_H1_EVALUATION_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "selection_frozen_before_full_fit": True,
        "posthoc_H1_feature_change_performed": False,
        "posthoc_H1_candidate_change_performed": False,
        "H2_outcomes_opened": False,
        "H3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"final H1 model {key} mismatch")

    scope = document.get("fit_scope")
    if not isinstance(scope, Mapping):
        _error("final H1 model fit_scope missing")
    if dict(scope) != {
        "stage": "H1",
        "event_count": H1_EVENT_COUNT,
        "row_count": H1_ROW_COUNT,
        "blocks": ["B0", "B1", "B2", "B3", "B4", "B5", "B6"],
        "all_H1_events_used": True,
        "H2_rows_used": 0,
        "H3_rows_used": 0,
    }:
        _error("final H1 model fit scope changed")

    model = document.get("model")
    if not isinstance(model, Mapping):
        _error("final H1 model model section missing")
    if model.get("formula") != "logit(p)=market_logit_offset + beta_distance*d_BTC":
        _error("final H1 model formula changed")
    if model.get("feature") != "btc_strike_log_distance_bps.v1":
        _error("final H1 model feature changed")
    if model.get("beta_momentum") is not None or model.get("free_parameter_count") != 1:
        _error("final H1 model acquired an unauthorized extra parameter")
    try:
        beta = float(model["beta_distance"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateEH2PreparationError("invalid final H1 beta_distance") from exc
    if not math.isfinite(beta) or beta <= 0.0:
        _error("final H1 beta_distance must remain finite and positive")

    fit_result = document.get("fit_result")
    if not isinstance(fit_result, Mapping) or fit_result.get("converged") is not True:
        _error("final H1 fit must be converged")
    if not isinstance(fit_result.get("iterations"), int) or not 0 <= fit_result["iterations"] <= 100:
        _error("final H1 fit iteration count invalid")
    try:
        objective = float(fit_result["fit_objective"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateEH2PreparationError("invalid final H1 objective") from exc
    if not math.isfinite(objective):
        _error("final H1 objective non-finite")

    predecl = candidate_e_predeclaration()
    if document.get("fit_contract") != predecl["fit_contract"]:
        _error("final H1 fit contract changed")

    lineage = document.get("lineage")
    if not isinstance(lineage, Mapping):
        _error("final H1 lineage missing")
    if lineage.get("source_baseline_commit") != EXPECTED_BASELINE_COMMIT:
        _error("final H1 source baseline commit changed")
    if verify_current_lineage_files:
        expected_hashes = {
            "h1_outcomes_sha256": _sha256_file(repo / H1_OUTCOMES_PATH),
            "h1_summary_sha256": _sha256_file(repo / H1_SUMMARY_PATH),
        }
        for key, value in expected_hashes.items():
            if lineage.get(key) != value:
                _error(f"final H1 lineage {key} changed")
        if lineage.get("fit_implementation_sha256s") != _implementation_sha256s(repo):
            _error("final H1 fit implementation bytes changed")

    payload = {key: document[key] for key in document if key != "final_model_fingerprint"}
    if document.get("final_model_fingerprint") != _canonical_sha256(payload):
        _error("final H1 model fingerprint mismatch")
    return dict(document)


def _load_attempt(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _write_attempt(
    path: Path,
    *,
    status: str,
    final_model_fingerprint: str | None = None,
) -> None:
    current = _load_attempt(path)
    if current is None:
        current = {
            "schema_version": FINAL_FIT_ATTEMPT_SCHEMA_VERSION,
            "checkpoint_id": "20C",
            "candidate_id": DISTANCE_CANDIDATE_ID,
            "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
            "fresh_second_final_fit_attempt_allowed": False,
            "H2_outcomes_opened": False,
            "H3_outcomes_opened": False,
            "execution_enabled": False,
            "orders_placed": 0,
        }
    else:
        if current.get("schema_version") != FINAL_FIT_ATTEMPT_SCHEMA_VERSION:
            _error("final-fit attempt receipt schema changed")
        if current.get("candidate_id") != DISTANCE_CANDIDATE_ID:
            _error("final-fit attempt candidate changed")
        if current.get("h1_result_fingerprint") != H1_RESULT_FINGERPRINT:
            _error("final-fit attempt H1 result changed")
        if current.get("fresh_second_final_fit_attempt_allowed") is not False:
            _error("fresh second final-fit attempt became allowed")
        if current.get("H2_outcomes_opened") is not False or current.get("H3_outcomes_opened") is not False:
            _error("final-fit attempt indicates H2/H3 exposure")
    current["status"] = status
    if final_model_fingerprint is not None:
        current["final_model_fingerprint"] = final_model_fingerprint
    _write_json_atomic(path, current)


def fit_or_validate_final_h1_distance_model(
    path: str | Path = DEFAULT_FINAL_MODEL_PATH,
    *,
    repository_root: str | Path = ".",
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    target = _repo_path(repo, path)
    attempt_path = repo / DEFAULT_FINAL_FIT_ATTEMPT_PATH

    if target.exists():
        document = _read_json(target)
        validate_final_model_document(document, repository_root=repo)
        attempt = _load_attempt(attempt_path)
        if not isinstance(attempt, Mapping) or attempt.get("status") != "completed":
            _error("final H1 model exists without completed attempt receipt")
        if attempt.get("final_model_fingerprint") != document.get("final_model_fingerprint"):
            _error("final-fit attempt/model fingerprint mismatch")
        return target, document

    attempt = _load_attempt(attempt_path)
    if attempt is not None and attempt.get("status") == "completed":
        _error("completed final-fit receipt exists but final model artifact is missing")

    assert_expected_repository_baseline(repo)
    _, freeze, universe, outcomes = _load_h1_outcomes_and_universe(repo)
    _write_attempt(attempt_path, status="in_progress")

    observations = _build_h1_observations_fast(
        universe=universe,
        outcomes=outcomes,
        freeze=freeze,
    )
    if len(observations) != H1_ROW_COUNT:
        _error("full-H1 final fit row count changed")
    if len({row.event_ticker for row in observations}) != H1_EVENT_COUNT:
        _error("full-H1 final fit event count changed")
    if {row.block_id for row in observations} != {"B0", "B1", "B2", "B3", "B4", "B5", "B6"}:
        _error("full-H1 final fit block scope changed")

    fit = fit_candidate_e(
        observations,
        candidate_id=DISTANCE_CANDIDATE_ID,
        fold=0,
        fit_blocks=("B0", "B1", "B2", "B3", "B4", "B5", "B6"),
        score_block="H2",
    )
    if not fit.converged or fit.beta_momentum is not None:
        _error("full-H1 final Distance fit invalid")

    payload = _final_model_payload(
        beta_distance=fit.beta_distance,
        iterations=fit.iterations,
        fit_objective=fit.fit_objective,
        repo=repo,
    )
    document = dict(payload)
    document["final_model_fingerprint"] = _canonical_sha256(payload)
    validate_final_model_document(document, repository_root=repo)
    _write_json_atomic(target, document)
    _write_attempt(
        attempt_path,
        status="completed",
        final_model_fingerprint=document["final_model_fingerprint"],
    )
    return target, document


def _stage_events(universe, stage: str) -> tuple[dict[str, Any], ...]:
    rows = [dict(row) for row in universe.cohort_rows if row["stage"] == stage]
    rows.sort(key=lambda row: int(row["stage_event_index_zero_based"]))
    expected = H2_EVENT_COUNT if stage == "H2" else H3_EVENT_COUNT
    if len(rows) != expected:
        _error(f"{stage} event count changed: {len(rows)}")
    if [int(row["stage_event_index_zero_based"]) for row in rows] != list(range(expected)):
        _error(f"{stage} stage event indices are not contiguous")
    return tuple(rows)


def _stage_market_plan(universe, stage: str) -> tuple[dict[str, str], ...]:
    event_set = {row["event_ticker"] for row in _stage_events(universe, stage)}
    mapping: dict[str, str] = {}
    for row in universe.preoutcome_rows:
        if row["stage"] != stage:
            continue
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if event not in event_set:
            _error(f"{stage} preoutcome row event absent from frozen cohort map")
        prior = mapping.setdefault(market, event)
        if prior != event:
            _error(f"{stage} market mapped to multiple events: {market}")
    if not mapping:
        _error(f"{stage} market plan is empty")
    return tuple(
        {"event_ticker": event, "market_ticker": market}
        for market, event in sorted(mapping.items())
    )


def _event_identity_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = [
        {
            "event_ticker": str(row["event_ticker"]),
            "event_close_time_utc": str(row["event_close_time_utc"]),
            "queue_index_zero_based": int(row["queue_index_zero_based"]),
            "stage_event_index_zero_based": int(row["stage_event_index_zero_based"]),
            "block_id": str(row["block_id"]),
        }
        for row in rows
    ]
    return _canonical_sha256(payload)


def _market_identity_fingerprint(plan: Sequence[Mapping[str, str]]) -> str:
    return _canonical_sha256(list(plan))


def validate_frozen_h2_block_map(universe) -> dict[str, int]:
    events = _stage_events(universe, "H2")
    counts = Counter(str(row["block_id"]) for row in events)
    expected = {block: H2_EVENTS_PER_BLOCK for block in H2_BLOCKS}
    if dict(counts) != expected:
        _error(f"H2 frozen block map changed: {dict(counts)}")
    # Strict chronological contiguity: each consecutive 150-event slice is one block.
    observed = [str(row["block_id"]) for row in events]
    expected_sequence = [
        block for block in H2_BLOCKS for _ in range(H2_EVENTS_PER_BLOCK)
    ]
    if observed != expected_sequence:
        _error("H2 B0-B4 blocks are no longer chronologically contiguous")
    return expected


def passes_h2_validation_gate(
    *,
    pooled_raw_minus_candidate_log_loss: float,
    pooled_raw_minus_candidate_brier: float,
    block_raw_minus_candidate_log_loss: Sequence[float],
    median_event_raw_minus_candidate_log_loss: float,
    final_h1_model_valid: bool,
    structural_coverage_ok: bool,
    policy_firewall_ok: bool,
) -> bool:
    deltas = list(block_raw_minus_candidate_log_loss)
    return (
        math.isfinite(pooled_raw_minus_candidate_log_loss)
        and pooled_raw_minus_candidate_log_loss > 0.0
        and math.isfinite(pooled_raw_minus_candidate_brier)
        and pooled_raw_minus_candidate_brier >= 0.0
        and len(deltas) == 5
        and all(math.isfinite(value) for value in deltas)
        and sum(value > 0.0 for value in deltas) >= 4
        and deltas[-1] > 0.0
        and math.isfinite(median_event_raw_minus_candidate_log_loss)
        and median_event_raw_minus_candidate_log_loss > 0.0
        and final_h1_model_valid
        and structural_coverage_ok
        and policy_firewall_ok
    )


def build_h2_validation_freeze_document(
    *,
    final_model: Mapping[str, Any],
    universe,
) -> dict[str, Any]:
    model = validate_final_model_document(
        final_model,
        verify_current_lineage_files=False,
    )
    validate_frozen_h2_block_map(universe)
    h2_events = _stage_events(universe, "H2")
    h3_events = _stage_events(universe, "H3")
    h2_plan = _stage_market_plan(universe, "H2")
    h3_plan = _stage_market_plan(universe, "H3")

    h2_event_set = {row["event_ticker"] for row in h2_events}
    h3_event_set = {row["event_ticker"] for row in h3_events}
    if h2_event_set & h3_event_set:
        _error("H2/H3 event identity overlap")
    h2_markets = {row["market_ticker"] for row in h2_plan}
    h3_markets = {row["market_ticker"] for row in h3_plan}
    if h2_markets & h3_markets:
        _error("H2/H3 market identity overlap")

    predecl = candidate_e_predeclaration()
    payload = {
        "schema_version": H2_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20C",
        "family_id": predecl["family_id"],
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_evaluation_fingerprint": EXPECTED_H1_EVALUATION_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "final_h1_model_fingerprint": model["final_model_fingerprint"],
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "H2_identity": {
            "event_count": H2_EVENT_COUNT,
            "row_count": H2_ROW_COUNT,
            "market_count": len(h2_plan),
            "event_identity_fingerprint": _event_identity_fingerprint(h2_events),
            "market_identity_fingerprint": _market_identity_fingerprint(h2_plan),
            "blocks": {block: H2_EVENTS_PER_BLOCK for block in H2_BLOCKS},
        },
        "H3_deny_identity": {
            "event_count": H3_EVENT_COUNT,
            "row_count": H3_ROW_COUNT,
            "market_count": len(h3_plan),
            "event_identity_fingerprint": _event_identity_fingerprint(h3_events),
            "market_identity_fingerprint": _market_identity_fingerprint(h3_plan),
        },
        "h2_request_plan": list(h2_plan),
        "h2_block_map": [
            {
                "event_ticker": str(row["event_ticker"]),
                "stage_event_index_zero_based": int(row["stage_event_index_zero_based"]),
                "block_id": str(row["block_id"]),
            }
            for row in h2_events
        ],
        "validation_contract": {
            "benchmark": "raw_kalshi_midpoint_q_market",
            "candidate_probability": (
                "sigmoid(logit_clip_0.001(q_market) + "
                "frozen_beta_distance*d_BTC)"
            ),
            "model_parameters_fitted_on_H2": False,
            "candidate_selection_on_H2_allowed": False,
            "feature_change_on_H2_allowed": False,
            "hyperparameter_search_on_H2_allowed": False,
            "primary_metric": "pooled_event_equal_log_loss",
            "secondary_metric": "pooled_event_equal_brier",
            "event_weighting": "equal_total_weight_per_event",
            "within_event_weighting": "equal_weight_per_scored_row",
            "block_reporting": "frozen H2 chronological B0-B4, exactly 150 events each",
            "gate": {
                "all_conditions_required": True,
                "conditions": [
                    "pooled raw-minus-candidate event-equal log-loss delta > 0",
                    "pooled raw-minus-candidate event-equal Brier delta >= 0",
                    "candidate strictly beats raw log loss in at least 4 of 5 H2 blocks",
                    "candidate strictly beats raw log loss in latest H2 block B4",
                    "median event-level raw-minus-candidate log-loss delta > 0",
                    "frozen full-H1 model is finite/converged and beta_distance > 0",
                    "all H2 blocks contain all five structural roles and all six TTC targets",
                    "no source-policy, timing, lineage, evidence, outcome-firewall, or execution violation",
                ],
                "ties": "fail_primary",
            },
        },
        "sequential_firewall": {
            "H1_model_selection_closed": True,
            "H1_refit_after_this_freeze_allowed": False,
            "H2_outcomes_opened_at_freeze": 0,
            "H3_outcomes_opened_at_freeze": 0,
            "H2_only_outcome_access_after_implementation_closeout": True,
            "H3_event_and_market_identities_hard_denied": True,
            "arbitrary_partition_argument_allowed": False,
            "arbitrary_ticker_argument_allowed": False,
            "H3_may_open_if_H2_fails": False,
            "if_H2_PASS": (
                "refit the same fixed Distance specification once on H1+H2, "
                "freeze final parameters, then separately authorize H3"
            ),
            "if_H2_FAIL": "Candidate E stops; H3 remains untouched",
        },
        "procedure_derivation_used_H2_outcomes": False,
        "procedure_derivation_used_H3_outcomes": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "source_baseline_commit": EXPECTED_BASELINE_COMMIT,
    }
    document = dict(payload)
    document["h2_validation_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_h2_validation_freeze_document(
    document: Mapping[str, Any],
    *,
    final_model: Mapping[str, Any],
    universe=None,
) -> dict[str, Any]:
    model = validate_final_model_document(
        final_model,
        verify_current_lineage_files=False,
    )
    expected_identity = {
        "schema_version": H2_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20C",
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_evaluation_fingerprint": EXPECTED_H1_EVALUATION_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "final_h1_model_fingerprint": model["final_model_fingerprint"],
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "procedure_derivation_used_H2_outcomes": False,
        "procedure_derivation_used_H3_outcomes": False,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "source_baseline_commit": EXPECTED_BASELINE_COMMIT,
    }
    for key, value in expected_identity.items():
        if document.get(key) != value:
            _error(f"H2 freeze {key} mismatch")

    h2_identity = document.get("H2_identity")
    h3_identity = document.get("H3_deny_identity")
    if not isinstance(h2_identity, Mapping) or not isinstance(h3_identity, Mapping):
        _error("H2/H3 identity descriptors missing")
    if h2_identity.get("event_count") != H2_EVENT_COUNT or h2_identity.get("row_count") != H2_ROW_COUNT:
        _error("H2 identity counts changed")
    if h3_identity.get("event_count") != H3_EVENT_COUNT or h3_identity.get("row_count") != H3_ROW_COUNT:
        _error("H3 deny counts changed")
    if h2_identity.get("blocks") != {block: H2_EVENTS_PER_BLOCK for block in H2_BLOCKS}:
        _error("H2 frozen block sizes changed")

    plan = document.get("h2_request_plan")
    block_map = document.get("h2_block_map")
    if not isinstance(plan, list) or not plan:
        _error("H2 request plan missing")
    if not isinstance(block_map, list) or len(block_map) != H2_EVENT_COUNT:
        _error("H2 block map missing or wrong length")
    seen_markets: set[str] = set()
    for row in plan:
        if not isinstance(row, Mapping) or set(row) != {"event_ticker", "market_ticker"}:
            _error("H2 request-plan schema changed")
        market = str(row["market_ticker"])
        if market in seen_markets:
            _error(f"duplicate H2 request market {market}")
        seen_markets.add(market)
    if len(seen_markets) != h2_identity.get("market_count"):
        _error("H2 request-plan market count mismatch")

    blocks = Counter(str(row.get("block_id")) for row in block_map if isinstance(row, Mapping))
    if dict(blocks) != {block: H2_EVENTS_PER_BLOCK for block in H2_BLOCKS}:
        _error("H2 block-map counts changed")

    contract = document.get("validation_contract")
    if not isinstance(contract, Mapping):
        _error("H2 validation contract missing")
    if contract.get("model_parameters_fitted_on_H2") is not False:
        _error("H2 fitting became allowed")
    if contract.get("candidate_selection_on_H2_allowed") is not False:
        _error("H2 candidate selection became allowed")
    if contract.get("feature_change_on_H2_allowed") is not False:
        _error("H2 feature changes became allowed")
    if contract.get("hyperparameter_search_on_H2_allowed") is not False:
        _error("H2 hyperparameter search became allowed")

    firewall = document.get("sequential_firewall")
    if not isinstance(firewall, Mapping):
        _error("H2 sequential firewall missing")
    required_false = (
        "H1_refit_after_this_freeze_allowed",
        "arbitrary_partition_argument_allowed",
        "arbitrary_ticker_argument_allowed",
        "H3_may_open_if_H2_fails",
    )
    for key in required_false:
        if firewall.get(key) is not False:
            _error(f"H2 firewall {key} changed")
    if firewall.get("H3_event_and_market_identities_hard_denied") is not True:
        _error("H3 hard deny disabled")
    if firewall.get("H1_model_selection_closed") is not True:
        _error("H1 model selection reopened")

    payload = {key: document[key] for key in document if key != "h2_validation_fingerprint"}
    if document.get("h2_validation_fingerprint") != _canonical_sha256(payload):
        _error("H2 validation fingerprint mismatch")

    if universe is not None:
        expected = build_h2_validation_freeze_document(
            final_model=model,
            universe=universe,
        )
        if dict(document) != expected:
            _error("stored H2 freeze differs from deterministic outcome-blind derivation")
    return dict(document)


def write_or_validate_h2_validation_freeze(
    path: str | Path = DEFAULT_H2_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
    final_model_path: str | Path = DEFAULT_FINAL_MODEL_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    final_model = _read_json(_repo_path(repo, final_model_path))
    validate_final_model_document(final_model, repository_root=repo)
    universe = load_and_validate_frozen_universe(repo)
    document = build_h2_validation_freeze_document(
        final_model=final_model,
        universe=universe,
    )
    validate_h2_validation_freeze_document(
        document,
        final_model=final_model,
        universe=universe,
    )
    target = _repo_path(repo, path)
    if target.exists():
        existing = _read_json(target)
        validate_h2_validation_freeze_document(
            existing,
            final_model=final_model,
            universe=universe,
        )
        if existing != document:
            _error("existing H2 freeze differs; refusing overwrite")
        return target, existing
    _write_json_atomic(target, document)
    return target, document


def validate_checkpoint20c_preparation(
    repository_root: str | Path = ".",
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo = Path(repository_root).resolve()
    # Result chain remains authoritative; this also validates the completed H1 manifest.
    load_and_validate_result(repo)
    final_model = _read_json(repo / DEFAULT_FINAL_MODEL_PATH)
    validate_final_model_document(final_model, repository_root=repo)
    attempt = _read_json(repo / DEFAULT_FINAL_FIT_ATTEMPT_PATH)
    if attempt.get("status") != "completed":
        _error("full-H1 final-fit attempt is not completed")
    if attempt.get("final_model_fingerprint") != final_model.get("final_model_fingerprint"):
        _error("full-H1 final-fit attempt/model fingerprint mismatch")

    universe = load_and_validate_frozen_universe(repo)
    freeze = _read_json(repo / DEFAULT_H2_FREEZE_PATH)
    validate_h2_validation_freeze_document(
        freeze,
        final_model=final_model,
        universe=universe,
    )
    return final_model, freeze


__all__ = [
    "CandidateEH2PreparationError",
    "DEFAULT_FINAL_MODEL_PATH",
    "DEFAULT_H2_FREEZE_PATH",
    "DISTANCE_CANDIDATE_ID",
    "EXPECTED_BASELINE_COMMIT",
    "H1_RESULT_FINGERPRINT",
    "H2_BLOCKS",
    "H2_EVENTS_PER_BLOCK",
    "build_h2_validation_freeze_document",
    "fit_or_validate_final_h1_distance_model",
    "passes_h2_validation_gate",
    "validate_checkpoint20c_preparation",
    "validate_final_model_document",
    "validate_frozen_h2_block_map",
    "validate_h2_validation_freeze_document",
    "write_or_validate_h2_validation_freeze",
]
