"""Checkpoint-20G Candidate-E H1+H2 final Distance fit and H3 freeze.

This module is deliberately network-free.

After the frozen Distance specification passed H2, Checkpoint 20G does exactly
two research actions:
1. fit that same one-parameter Distance specification once on all permanently
   exposed H1+H2 evidence;
2. freeze the H3-only locked historical test contract from the already-frozen
   outcome-blind H3 identities.

It does not read H3 outcomes, introduce a candidate/feature/hyperparameter,
score H3, or enable any execution path.
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
    fit_candidate_e,
    load_and_validate_frozen_universe,
)
from .kxbtcd_candidate_e_h1_result_closeout import (
    EXPECTED_RESULT_FINGERPRINT as H1_RESULT_FINGERPRINT,
    H1_EVALUATION_FINGERPRINT,
    MANIFEST_PATH as H1_MANIFEST_PATH,
    RUN_ID as H1_RUN_ID,
    load_and_validate_result as load_and_validate_h1_result,
)
from .kxbtcd_candidate_e_h2_result_closeout import (
    EXPECTED_RESULT_FINGERPRINT as H2_RESULT_FINGERPRINT,
    OUTCOMES_PATH as H2_OUTCOMES_PATH,
    load_and_validate_result as load_and_validate_h2_result,
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

EXPECTED_BASELINE_COMMIT = "6341d86c965f1f7df799163b71ff1dcb8b772d4a"
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
FINAL_FIT_EVENT_COUNT = H1_EVENT_COUNT + H2_EVENT_COUNT
FINAL_FIT_ROW_COUNT = H1_ROW_COUNT + H2_ROW_COUNT

H3_BLOCKS = ("B0", "B1", "B2", "B3", "B4")
H3_EVENTS_PER_BLOCK = 150

FINAL_MODEL_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_h2_final_distance_model.v1"
H3_FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_h3_validation_freeze.v1"
FINAL_FIT_ATTEMPT_SCHEMA_VERSION = "kxbtcd_candidate_e_h1_h2_final_fit_attempt.v1"

DEFAULT_FINAL_MODEL_PATH = Path(
    "configs/kxbtcd_candidate_e_h1_h2_final_distance_model.json"
)
DEFAULT_H3_FREEZE_PATH = Path("configs/kxbtcd_candidate_e_h3_validation_freeze.json")
DEFAULT_FINAL_FIT_ATTEMPT_PATH = Path(
    "data/analysis/kxbtcd_candidate_e_h1_h2_final_fit/final_fit_attempt.json"
)

H1_OUTCOMES_PATH = Path(
    "data/derived/kxbtcd_candidate_e_h1_evaluation/2026/08/17/"
    f"{H1_RUN_ID}_candidate_e_h1_outcomes.csv"
)

FIT_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_h1_evaluation.py",
    "src/kxbtcd_candidate_e_h3_preparation.py",
)


class CandidateEH3PreparationError(RuntimeError):
    """Raised when a Checkpoint-20G invariant fails."""


def _error(message: str) -> None:
    raise CandidateEH3PreparationError(message)


def _repo_path(repo: Path, path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else repo / p


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateEH3PreparationError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"JSON root must be an object: {path}")
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
        raise CandidateEH3PreparationError(f"could not read CSV {path}: {exc}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        detail = (completed.stderr or completed.stdout or "").strip()
        _error(f"git {' '.join(args)} failed: {detail or completed.returncode}")
    return completed.stdout.strip()


def assert_expected_repository_baseline(
    repository_root: str | Path = ".",
) -> None:
    """Bind first execution to the cleanly closed Checkpoint-20F receipt.

    Extracted 20G files may be untracked, so only tracked changes/staging are
    prohibited here.
    """
    repo = Path(repository_root).resolve()
    _git(repo, "fetch", "origin")
    if _git(repo, "branch", "--show-current") != "main":
        _error("Checkpoint-20G preparation requires branch main")
    head = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", "origin/main")
    if head != EXPECTED_BASELINE_COMMIT or remote != EXPECTED_BASELINE_COMMIT:
        _error(
            "Checkpoint-20G baseline mismatch; expected HEAD == origin/main == "
            f"{EXPECTED_BASELINE_COMMIT}, got HEAD={head}, origin/main={remote}"
        )
    if _git(repo, "diff", "--name-only"):
        _error("tracked unstaged changes existed before Checkpoint-20G")
    if _git(repo, "diff", "--cached", "--name-only"):
        _error("staged changes existed before Checkpoint-20G")


def _implementation_sha256s(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in FIT_IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"missing final-fit implementation file {relative}")
        result[relative] = _sha256_file(path)
    return result


def _h1_request_plan_from_manifest(repo: Path) -> dict[str, str]:
    # The canonical H1 result validator binds the completed manifest and all
    # derived artifact hashes. The request plan itself remains in the tracked
    # H1 evaluation freeze.
    freeze = _read_json(repo / "configs/kxbtcd_candidate_e_h1_evaluation_freeze.json")
    if freeze.get("h1_evaluation_fingerprint") != H1_EVALUATION_FINGERPRINT:
        _error("H1 evaluation fingerprint changed")
    raw = freeze.get("h1_request_plan")
    if not isinstance(raw, list) or not raw:
        _error("H1 request plan missing")
    plan: dict[str, str] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) != {"event_ticker", "market_ticker"}:
            _error(f"H1 request-plan row {index} schema mismatch")
        event = str(item["event_ticker"])
        market = str(item["market_ticker"])
        if market in plan:
            _error(f"duplicate H1 planned market {market}")
        plan[market] = event
    return plan


def _validate_h1_outcomes(
    repo: Path,
    universe,
) -> tuple[dict[str, str], ...]:
    load_and_validate_h1_result(repo)
    fields, rows = _read_csv(repo / H1_OUTCOMES_PATH)
    required = {
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
    }
    if set(fields) != required or len(fields) != len(required):
        _error("H1 outcome schema changed")
    plan = _h1_request_plan_from_manifest(repo)
    h2_h3_events = {
        str(row["event_ticker"])
        for row in universe.cohort_rows
        if row["stage"] in {"H2", "H3"}
    }
    h2_h3_markets = {
        str(row["market_ticker"])
        for row in universe.preoutcome_rows
        if row["stage"] in {"H2", "H3"}
    }
    seen: set[str] = set()
    valid: list[dict[str, str]] = []
    for index, original in enumerate(rows):
        row = dict(original)
        expected = {
            "schema_version": "kxbtcd_candidate_e_h1_outcome.v1",
            "family_id": "kxbtcd_independent_btc_offset_successor.v1",
            "h1_evaluation_fingerprint": H1_EVALUATION_FINGERPRINT,
            "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
            "stage": "H1",
            "market_status": "finalized",
        }
        for key, value in expected.items():
            if row.get(key) != value:
                _error(f"H1 outcome row {index} {key} mismatch")
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if event in h2_h3_events or market in h2_h3_markets:
            _error("H1 outcome file crosses the H2/H3 identity firewall")
        if market in seen:
            _error(f"duplicate H1 outcome market {market}")
        seen.add(market)
        if plan.get(market) != event:
            _error(f"unplanned H1 outcome identity {event}/{market}")
        if (row.get("result_text"), row.get("outcome")) not in {
            ("yes", "1"),
            ("no", "0"),
        }:
            _error(f"H1 outcome row {index} result/outcome mismatch")
        for field in ("raw_source", "raw_session_id", "raw_request_id"):
            if not str(row.get(field, "")).strip():
                _error(f"H1 outcome row {index} {field} blank")
        valid.append(row)
    if seen != set(plan):
        _error(
            "H1 outcome identity set differs from frozen request plan; "
            f"seen={len(seen)}, planned={len(plan)}"
        )
    return tuple(valid)


def _validate_h2_outcomes(
    repo: Path,
    universe,
) -> tuple[dict[str, str], ...]:
    # The 20F validator verifies every H2 outcome row, result fingerprint,
    # block score, prediction row, event score and completed attempt/manifest.
    load_and_validate_h2_result(repo)
    _, rows = _read_csv(repo / H2_OUTCOMES_PATH)
    if len(rows) != 3750:
        _error(f"H2 outcome label count changed: {len(rows)}")
    h2_events = {
        str(row["event_ticker"])
        for row in universe.cohort_rows
        if row["stage"] == "H2"
    }
    h3_events = {
        str(row["event_ticker"])
        for row in universe.cohort_rows
        if row["stage"] == "H3"
    }
    h3_markets = {
        str(row["market_ticker"])
        for row in universe.preoutcome_rows
        if row["stage"] == "H3"
    }
    valid: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, original in enumerate(rows):
        row = dict(original)
        event = str(row.get("event_ticker", ""))
        market = str(row.get("market_ticker", ""))
        if event not in h2_events:
            _error(f"H2 outcome row {index} event absent from frozen H2 cohort")
        if event in h3_events or market in h3_markets:
            _error("H2 outcome file crosses the H3 identity firewall")
        if market in seen:
            _error(f"duplicate H2 outcome market {market}")
        seen.add(market)
        valid.append(row)
    return tuple(valid)


def _build_h1_h2_observations(
    *,
    repo: Path,
    universe,
) -> tuple[CandidateEObservation, ...]:
    h1 = _validate_h1_outcomes(repo, universe)
    h2 = _validate_h2_outcomes(repo, universe)
    labels: dict[str, int] = {}
    for row in (*h1, *h2):
        market = str(row["market_ticker"])
        if market in labels:
            _error(f"H1/H2 outcome market overlap: {market}")
        labels[market] = int(row["outcome"])

    observations: list[CandidateEObservation] = []
    state_ids: set[str] = set()
    stage_events: dict[str, set[str]] = {"H1": set(), "H2": set()}
    for index, row in enumerate(universe.preoutcome_rows):
        stage = str(row["stage"])
        if stage not in {"H1", "H2"}:
            continue
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if market not in labels:
            _error(f"{stage} preoutcome row references missing label {market}")
        state_id = (
            f"{stage}|{event}|{market}|TTC{int(row['ttc_target_minutes'])}|"
            f"{row['structural_role']}"
        )
        if state_id in state_ids:
            _error(f"duplicate H1+H2 state identity {state_id}")
        state_ids.add(state_id)
        stage_events[stage].add(event)
        try:
            q_market = float(row["q_market"])
            d_btc = float(row["d_BTC"])
            r_5m = float(row["r_5m"])
        except (TypeError, ValueError) as exc:
            raise CandidateEH3PreparationError(
                f"H1+H2 preoutcome numeric parse failed at row {index}"
            ) from exc
        if not all(math.isfinite(v) for v in (q_market, d_btc, r_5m)):
            _error(f"H1+H2 preoutcome row {index} contains non-finite model input")
        observations.append(
            CandidateEObservation(
                state_id=state_id,
                event_ticker=event,
                market_ticker=market,
                block_id=f"{stage}_{row['block_id']}",
                structural_role=str(row["structural_role"]),
                ttc_target_minutes=int(row["ttc_target_minutes"]),
                outcome=labels[market],
                q_market=q_market,
                d_btc=d_btc,
                r_5m=r_5m,
            )
        )

    if len(observations) != FINAL_FIT_ROW_COUNT:
        _error(
            f"H1+H2 final-fit row count changed: "
            f"{len(observations)} != {FINAL_FIT_ROW_COUNT}"
        )
    if len(stage_events["H1"]) != H1_EVENT_COUNT:
        _error("H1 final-fit event count changed")
    if len(stage_events["H2"]) != H2_EVENT_COUNT:
        _error("H2 final-fit event count changed")
    if stage_events["H1"] & stage_events["H2"]:
        _error("H1/H2 event identity overlap")
    if len({row.event_ticker for row in observations}) != FINAL_FIT_EVENT_COUNT:
        _error("H1+H2 total event count changed")
    return tuple(observations)


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
            "checkpoint_id": "20G",
            "candidate_id": DISTANCE_CANDIDATE_ID,
            "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
            "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
            "fresh_second_final_fit_attempt_allowed": False,
            "H3_outcomes_opened": False,
            "execution_enabled": False,
            "orders_placed": 0,
        }
    else:
        expected = {
            "schema_version": FINAL_FIT_ATTEMPT_SCHEMA_VERSION,
            "checkpoint_id": "20G",
            "candidate_id": DISTANCE_CANDIDATE_ID,
            "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
            "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
            "fresh_second_final_fit_attempt_allowed": False,
            "H3_outcomes_opened": False,
            "execution_enabled": False,
            "orders_placed": 0,
        }
        for key, value in expected.items():
            if current.get(key) != value:
                _error(f"H1+H2 final-fit attempt {key} mismatch")
    current["status"] = status
    if final_model_fingerprint is not None:
        current["final_model_fingerprint"] = final_model_fingerprint
    _write_json_atomic(path, current)


def _final_model_payload(
    *,
    beta_distance: float,
    iterations: int,
    fit_objective: float,
    repo: Path,
) -> dict[str, Any]:
    if not math.isfinite(beta_distance) or beta_distance <= 0.0:
        _error("H1+H2 final Distance coefficient must be finite and positive")
    if not isinstance(iterations, int) or not 0 <= iterations <= 100:
        _error("H1+H2 fit iteration count invalid")
    if not math.isfinite(fit_objective):
        _error("H1+H2 fit objective non-finite")
    predecl = candidate_e_predeclaration()
    payload = {
        "schema_version": FINAL_MODEL_SCHEMA_VERSION,
        "checkpoint_id": "20G",
        "family_id": predecl["family_id"],
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "fit_scope": {
            "stages": ["H1", "H2"],
            "H1_event_count": H1_EVENT_COUNT,
            "H1_row_count": H1_ROW_COUNT,
            "H2_event_count": H2_EVENT_COUNT,
            "H2_row_count": H2_ROW_COUNT,
            "total_event_count": FINAL_FIT_EVENT_COUNT,
            "total_row_count": FINAL_FIT_ROW_COUNT,
            "all_H1_and_H2_events_used": True,
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
            "h2_outcomes_path": H2_OUTCOMES_PATH.as_posix(),
            "h2_outcomes_sha256": _sha256_file(repo / H2_OUTCOMES_PATH),
            "h1_manifest_path": H1_MANIFEST_PATH.as_posix(),
            "h1_manifest_sha256": _sha256_file(repo / H1_MANIFEST_PATH),
            "source_baseline_commit": EXPECTED_BASELINE_COMMIT,
            "fit_implementation_sha256s": _implementation_sha256s(repo),
        },
        "specification_frozen_before_H2": True,
        "H2_pass_required_before_this_fit": True,
        "posthoc_H2_feature_change_performed": False,
        "posthoc_H2_candidate_change_performed": False,
        "posthoc_H2_hyperparameter_change_performed": False,
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
        "checkpoint_id": "20G",
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "specification_frozen_before_H2": True,
        "H2_pass_required_before_this_fit": True,
        "posthoc_H2_feature_change_performed": False,
        "posthoc_H2_candidate_change_performed": False,
        "posthoc_H2_hyperparameter_change_performed": False,
        "H3_outcomes_opened": False,
        "execution_enabled": False,
        "orders_placed": 0,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"H1+H2 final model {key} mismatch")

    scope = document.get("fit_scope")
    if not isinstance(scope, Mapping) or dict(scope) != {
        "stages": ["H1", "H2"],
        "H1_event_count": H1_EVENT_COUNT,
        "H1_row_count": H1_ROW_COUNT,
        "H2_event_count": H2_EVENT_COUNT,
        "H2_row_count": H2_ROW_COUNT,
        "total_event_count": FINAL_FIT_EVENT_COUNT,
        "total_row_count": FINAL_FIT_ROW_COUNT,
        "all_H1_and_H2_events_used": True,
        "H3_rows_used": 0,
    }:
        _error("H1+H2 final fit scope changed")

    model = document.get("model")
    if not isinstance(model, Mapping):
        _error("H1+H2 final model section missing")
    if model.get("formula") != "logit(p)=market_logit_offset + beta_distance*d_BTC":
        _error("H1+H2 final model formula changed")
    if model.get("feature") != "btc_strike_log_distance_bps.v1":
        _error("H1+H2 final model feature changed")
    if model.get("beta_momentum") is not None or model.get("free_parameter_count") != 1:
        _error("H1+H2 final model acquired an unauthorized parameter")
    try:
        beta = float(model["beta_distance"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateEH3PreparationError("invalid final beta_distance") from exc
    if not math.isfinite(beta) or beta <= 0.0:
        _error("H1+H2 final beta_distance must be finite and positive")

    fit = document.get("fit_result")
    if not isinstance(fit, Mapping) or fit.get("converged") is not True:
        _error("H1+H2 final fit must be converged")
    if not isinstance(fit.get("iterations"), int) or not 0 <= fit["iterations"] <= 100:
        _error("H1+H2 final fit iteration count invalid")
    try:
        objective = float(fit["fit_objective"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateEH3PreparationError("invalid final fit objective") from exc
    if not math.isfinite(objective):
        _error("H1+H2 final fit objective non-finite")

    if document.get("fit_contract") != candidate_e_predeclaration()["fit_contract"]:
        _error("H1+H2 final fit contract changed")

    lineage = document.get("lineage")
    if not isinstance(lineage, Mapping):
        _error("H1+H2 final model lineage missing")
    if lineage.get("source_baseline_commit") != EXPECTED_BASELINE_COMMIT:
        _error("H1+H2 final model source baseline changed")
    if verify_current_lineage_files:
        expected_hashes = {
            "h1_outcomes_sha256": _sha256_file(repo / H1_OUTCOMES_PATH),
            "h2_outcomes_sha256": _sha256_file(repo / H2_OUTCOMES_PATH),
            "h1_manifest_sha256": _sha256_file(repo / H1_MANIFEST_PATH),
        }
        for key, value in expected_hashes.items():
            if lineage.get(key) != value:
                _error(f"H1+H2 final model lineage {key} changed")
        if lineage.get("fit_implementation_sha256s") != _implementation_sha256s(repo):
            _error("H1+H2 fit implementation bytes changed")

    payload = {
        key: document[key]
        for key in document
        if key != "final_model_fingerprint"
    }
    if document.get("final_model_fingerprint") != _canonical_sha256(payload):
        _error("H1+H2 final model fingerprint mismatch")
    return dict(document)


def fit_or_validate_final_h1_h2_distance_model(
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
            _error("H1+H2 final model exists without completed attempt receipt")
        if attempt.get("final_model_fingerprint") != document.get("final_model_fingerprint"):
            _error("H1+H2 final-fit attempt/model fingerprint mismatch")
        return target, document

    attempt = _load_attempt(attempt_path)
    if attempt is not None and attempt.get("status") == "completed":
        _error("completed H1+H2 final-fit receipt exists but model artifact is missing")

    assert_expected_repository_baseline(repo)
    load_and_validate_h1_result(repo)
    h2_summary = load_and_validate_h2_result(repo)
    if h2_summary.get("H2_validation_passed") is not True:
        _error("H2 did not pass; H1+H2 final fit is not authorized")
    if h2_summary.get("H3_outcomes_opened") is not False:
        _error("H2 result indicates H3 exposure")

    universe = load_and_validate_frozen_universe(repo)
    observations = _build_h1_h2_observations(repo=repo, universe=universe)
    _write_attempt(attempt_path, status="in_progress")

    fit = fit_candidate_e(
        observations,
        candidate_id=DISTANCE_CANDIDATE_ID,
        fold=0,
        fit_blocks=("H1", "H2"),
        score_block="H3",
    )
    if not fit.converged or fit.beta_momentum is not None:
        _error("H1+H2 final Distance fit invalid")

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
    if stage != "H3" or len(rows) != H3_EVENT_COUNT:
        _error(f"H3 event count changed: {len(rows)}")
    if [int(row["stage_event_index_zero_based"]) for row in rows] != list(
        range(H3_EVENT_COUNT)
    ):
        _error("H3 stage event indices are not contiguous")
    return tuple(rows)


def _h3_market_plan(universe) -> tuple[dict[str, str], ...]:
    event_set = {row["event_ticker"] for row in _stage_events(universe, "H3")}
    mapping: dict[str, str] = {}
    for row in universe.preoutcome_rows:
        if row["stage"] != "H3":
            continue
        event = str(row["event_ticker"])
        market = str(row["market_ticker"])
        if event not in event_set:
            _error("H3 preoutcome row event absent from frozen cohort")
        prior = mapping.setdefault(market, event)
        if prior != event:
            _error(f"H3 market maps to multiple events: {market}")
    if not mapping:
        _error("H3 market plan is empty")
    return tuple(
        {"event_ticker": event, "market_ticker": market}
        for market, event in sorted(mapping.items(), key=lambda item: (item[1], item[0]))
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
    return _canonical_sha256(
        [
            {
                "event_ticker": str(row["event_ticker"]),
                "market_ticker": str(row["market_ticker"]),
            }
            for row in plan
        ]
    )


def validate_frozen_h3_block_map(universe) -> None:
    events = _stage_events(universe, "H3")
    counts = Counter(str(row["block_id"]) for row in events)
    expected = {block: H3_EVENTS_PER_BLOCK for block in H3_BLOCKS}
    if dict(counts) != expected:
        _error(f"H3 frozen block sizes changed: {dict(counts)}")
    required_roles = set(STRUCTURAL_ROLES)
    required_ttc = set(TTC_TARGET_MINUTES)
    for block in H3_BLOCKS:
        event_set = {
            str(row["event_ticker"])
            for row in events
            if row["block_id"] == block
        }
        rows = [
            row
            for row in universe.preoutcome_rows
            if row["stage"] == "H3" and row["event_ticker"] in event_set
        ]
        if {str(row["structural_role"]) for row in rows} != required_roles:
            _error(f"H3 block {block} lost structural-role coverage")
        if {int(row["ttc_target_minutes"]) for row in rows} != required_ttc:
            _error(f"H3 block {block} lost TTC coverage")


def build_h3_validation_freeze_document(
    *,
    final_model: Mapping[str, Any],
    universe,
) -> dict[str, Any]:
    model = validate_final_model_document(
        final_model,
        verify_current_lineage_files=False,
    )
    validate_frozen_h3_block_map(universe)
    h3_events = _stage_events(universe, "H3")
    h3_plan = _h3_market_plan(universe)

    payload = {
        "schema_version": H3_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20G",
        "family_id": candidate_e_predeclaration()["family_id"],
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "final_h1_h2_model_fingerprint": model["final_model_fingerprint"],
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "H3_identity": {
            "event_count": H3_EVENT_COUNT,
            "row_count": H3_ROW_COUNT,
            "market_count": len(h3_plan),
            "event_identity_fingerprint": _event_identity_fingerprint(h3_events),
            "market_identity_fingerprint": _market_identity_fingerprint(h3_plan),
            "blocks": {block: H3_EVENTS_PER_BLOCK for block in H3_BLOCKS},
        },
        "h3_request_plan": list(h3_plan),
        "h3_block_map": [
            {
                "event_ticker": str(row["event_ticker"]),
                "stage_event_index_zero_based": int(row["stage_event_index_zero_based"]),
                "block_id": str(row["block_id"]),
            }
            for row in h3_events
        ],
        "validation_contract": {
            "benchmark": "raw_kalshi_midpoint_q_market",
            "candidate_probability": (
                "sigmoid(logit_clip_0.001(q_market) + "
                "frozen_H1_H2_beta_distance*d_BTC)"
            ),
            "model_parameters_fitted_on_H3": False,
            "candidate_selection_on_H3_allowed": False,
            "feature_change_on_H3_allowed": False,
            "hyperparameter_search_on_H3_allowed": False,
            "primary_metric": "pooled_event_equal_log_loss",
            "secondary_metric": "pooled_event_equal_brier",
            "event_weighting": "equal_total_weight_per_event",
            "within_event_weighting": "equal_weight_per_scored_row",
            "block_reporting": "frozen H3 chronological B0-B4, exactly 150 events each",
            "gate": {
                "all_conditions_required": True,
                "conditions": [
                    "pooled raw-minus-candidate event-equal log-loss delta > 0",
                    "pooled raw-minus-candidate event-equal Brier delta >= 0",
                    "candidate strictly beats raw log loss in at least 4 of 5 H3 blocks",
                    "candidate strictly beats raw log loss in latest H3 block B4",
                    "median event-level raw-minus-candidate log-loss delta > 0",
                    "frozen full-H1+H2 model is finite/converged and beta_distance > 0",
                    "all H3 blocks contain all five structural roles and all six TTC targets",
                    "no source-policy, timing, lineage, evidence, outcome-firewall, or execution violation",
                ],
                "ties": "fail_primary",
            },
        },
        "sequential_firewall": {
            "H1_H2_model_specification_closed": True,
            "H1_H2_final_refit_after_this_freeze_allowed": False,
            "H3_outcomes_opened_at_freeze": 0,
            "H3_only_outcome_access_after_implementation_closeout": True,
            "arbitrary_partition_argument_allowed": False,
            "arbitrary_ticker_argument_allowed": False,
            "fresh_second_H3_attempt_allowed": False,
            "resume_only_after_interruption": True,
            "if_H3_PASS": (
                "Candidate E passes the frozen historical generalization program; "
                "only later read-only prospective live confirmation may be designed"
            ),
            "if_H3_FAIL": (
                "Candidate E stops under this specification; no H3 repair, retune, "
                "rescore, or renewed untouched-test claim"
            ),
        },
        "procedure_derivation_used_H3_outcomes": False,
        "H3_outcomes_opened": 0,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "source_baseline_commit": EXPECTED_BASELINE_COMMIT,
    }
    document = dict(payload)
    document["h3_validation_fingerprint"] = _canonical_sha256(payload)
    return document


def validate_h3_validation_freeze_document(
    document: Mapping[str, Any],
    *,
    final_model: Mapping[str, Any],
    universe=None,
) -> dict[str, Any]:
    model = validate_final_model_document(
        final_model,
        verify_current_lineage_files=False,
    )
    expected = {
        "schema_version": H3_FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "20G",
        "candidate_id": DISTANCE_CANDIDATE_ID,
        "candidate_e_predeclaration_fingerprint": FROZEN_PREDECLARATION_FINGERPRINT,
        "historical_materialization_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
        "coinbase_primary_amendment_fingerprint": FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
        "h1_result_fingerprint": H1_RESULT_FINGERPRINT,
        "h2_result_fingerprint": H2_RESULT_FINGERPRINT,
        "final_h1_h2_model_fingerprint": model["final_model_fingerprint"],
        "cohort_map_fingerprint": EXPECTED_COHORT_MAP_FINGERPRINT,
        "row_universe_fingerprint": EXPECTED_ROW_UNIVERSE_FINGERPRINT,
        "procedure_derivation_used_H3_outcomes": False,
        "H3_outcomes_opened": 0,
        "network_requests": 0,
        "execution_enabled": False,
        "orders_placed": 0,
        "source_baseline_commit": EXPECTED_BASELINE_COMMIT,
    }
    for key, value in expected.items():
        if document.get(key) != value:
            _error(f"H3 freeze {key} mismatch")

    identity = document.get("H3_identity")
    if not isinstance(identity, Mapping):
        _error("H3 identity missing")
    if identity.get("event_count") != H3_EVENT_COUNT:
        _error("H3 identity event count changed")
    if identity.get("row_count") != H3_ROW_COUNT:
        _error("H3 identity row count changed")
    if identity.get("blocks") != {
        block: H3_EVENTS_PER_BLOCK for block in H3_BLOCKS
    }:
        _error("H3 identity block sizes changed")

    plan = document.get("h3_request_plan")
    if not isinstance(plan, list) or not plan:
        _error("H3 request plan missing")
    seen: set[str] = set()
    for row in plan:
        if not isinstance(row, Mapping) or set(row) != {"event_ticker", "market_ticker"}:
            _error("H3 request-plan schema changed")
        market = str(row["market_ticker"])
        if market in seen:
            _error(f"duplicate H3 request market {market}")
        seen.add(market)
    if len(seen) != identity.get("market_count"):
        _error("H3 request-plan market count mismatch")

    block_map = document.get("h3_block_map")
    if not isinstance(block_map, list) or len(block_map) != H3_EVENT_COUNT:
        _error("H3 block map missing/wrong length")
    counts = Counter(
        str(row.get("block_id"))
        for row in block_map
        if isinstance(row, Mapping)
    )
    if dict(counts) != {block: H3_EVENTS_PER_BLOCK for block in H3_BLOCKS}:
        _error("H3 block-map counts changed")

    contract = document.get("validation_contract")
    if not isinstance(contract, Mapping):
        _error("H3 validation contract missing")
    for key in (
        "model_parameters_fitted_on_H3",
        "candidate_selection_on_H3_allowed",
        "feature_change_on_H3_allowed",
        "hyperparameter_search_on_H3_allowed",
    ):
        if contract.get(key) is not False:
            _error(f"H3 validation contract {key} changed")

    firewall = document.get("sequential_firewall")
    if not isinstance(firewall, Mapping):
        _error("H3 sequential firewall missing")
    required_true = (
        "H1_H2_model_specification_closed",
        "H3_only_outcome_access_after_implementation_closeout",
        "resume_only_after_interruption",
    )
    for key in required_true:
        if firewall.get(key) is not True:
            _error(f"H3 firewall {key} changed")
    required_false = (
        "H1_H2_final_refit_after_this_freeze_allowed",
        "arbitrary_partition_argument_allowed",
        "arbitrary_ticker_argument_allowed",
        "fresh_second_H3_attempt_allowed",
    )
    for key in required_false:
        if firewall.get(key) is not False:
            _error(f"H3 firewall {key} changed")

    payload = {
        key: document[key]
        for key in document
        if key != "h3_validation_fingerprint"
    }
    if document.get("h3_validation_fingerprint") != _canonical_sha256(payload):
        _error("H3 validation fingerprint mismatch")

    if universe is not None:
        expected_document = build_h3_validation_freeze_document(
            final_model=model,
            universe=universe,
        )
        if dict(document) != expected_document:
            _error("stored H3 freeze differs from deterministic outcome-blind derivation")
    return dict(document)


def write_or_validate_h3_validation_freeze(
    path: str | Path = DEFAULT_H3_FREEZE_PATH,
    *,
    repository_root: str | Path = ".",
    final_model_path: str | Path = DEFAULT_FINAL_MODEL_PATH,
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    final_model = _read_json(_repo_path(repo, final_model_path))
    validate_final_model_document(final_model, repository_root=repo)
    universe = load_and_validate_frozen_universe(repo)
    document = build_h3_validation_freeze_document(
        final_model=final_model,
        universe=universe,
    )
    validate_h3_validation_freeze_document(
        document,
        final_model=final_model,
        universe=universe,
    )
    target = _repo_path(repo, path)
    if target.exists():
        existing = _read_json(target)
        validate_h3_validation_freeze_document(
            existing,
            final_model=final_model,
            universe=universe,
        )
        if existing != document:
            _error("existing H3 freeze differs; refusing overwrite")
        return target, existing
    _write_json_atomic(target, document)
    return target, document


def validate_checkpoint20g_preparation(
    repository_root: str | Path = ".",
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo = Path(repository_root).resolve()
    load_and_validate_h1_result(repo)
    h2 = load_and_validate_h2_result(repo)
    if h2.get("H2_validation_passed") is not True:
        _error("H2 PASS is not validated")

    final_model = _read_json(repo / DEFAULT_FINAL_MODEL_PATH)
    validate_final_model_document(final_model, repository_root=repo)

    attempt = _read_json(repo / DEFAULT_FINAL_FIT_ATTEMPT_PATH)
    if attempt.get("status") != "completed":
        _error("H1+H2 final-fit attempt is not completed")
    if attempt.get("final_model_fingerprint") != final_model.get(
        "final_model_fingerprint"
    ):
        _error("H1+H2 final-fit attempt/model fingerprint mismatch")
    if attempt.get("H3_outcomes_opened") is not False:
        _error("H1+H2 final-fit attempt indicates H3 exposure")

    universe = load_and_validate_frozen_universe(repo)
    freeze = _read_json(repo / DEFAULT_H3_FREEZE_PATH)
    validate_h3_validation_freeze_document(
        freeze,
        final_model=final_model,
        universe=universe,
    )
    return final_model, freeze


__all__ = [
    "CandidateEH3PreparationError",
    "DEFAULT_FINAL_MODEL_PATH",
    "DEFAULT_H3_FREEZE_PATH",
    "DISTANCE_CANDIDATE_ID",
    "EXPECTED_BASELINE_COMMIT",
    "FINAL_FIT_EVENT_COUNT",
    "FINAL_FIT_ROW_COUNT",
    "H1_RESULT_FINGERPRINT",
    "H2_RESULT_FINGERPRINT",
    "H3_BLOCKS",
    "H3_EVENTS_PER_BLOCK",
    "build_h3_validation_freeze_document",
    "fit_or_validate_final_h1_h2_distance_model",
    "validate_checkpoint20g_preparation",
    "validate_final_model_document",
    "validate_frozen_h3_block_map",
    "validate_h3_validation_freeze_document",
    "write_or_validate_h3_validation_freeze",
]
