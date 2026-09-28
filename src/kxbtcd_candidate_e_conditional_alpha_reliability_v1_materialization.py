"""Outcome-blind development-row projection for conditional-alpha reliability v1.

The source of truth is the exact frozen Checkpoint-21M Model-2 feature CSV plus
its preparation-freeze receipt and the same frozen preoutcome quote source.
This module does not attach settlement labels, fit gamma, select lambda, calculate
P&L, access C1/C2/C3/reserve data, or use the network.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_conditional_alpha_reliability_v1 import (
    CANDIDATE_ID,
    DEVELOPMENT_STAGES,
    EXPECTED_PREDECLARATION_FINGERPRINT,
    EXPECTED_STAGE_EVENTS,
    EXPECTED_STAGE_ROWS,
    EXPECTED_TOTAL_EVENTS,
    EXPECTED_TOTAL_ROWS,
    STRUCTURAL_ROLES,
    TTC_LEVELS,
    canonical_sha256,
    validate_materialized_rows,
)

ROW_SCHEMA_VERSION = "kxbtcd_candidate_e_conditional_alpha_feature_row.v1"
FREEZE_SCHEMA_VERSION = "kxbtcd_candidate_e_conditional_alpha_preparation_freeze.v1"
EXPECTED_PARENT_PREPARATION_FINGERPRINT = "2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d"
EXPECTED_PARENT_FEATURE_FILE_SHA256 = "0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c"
PARENT_PREPARATION_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_preparation_freeze.v1"
PARENT_FEATURE_SCHEMA = "kxbtcd_candidate_e_entry_model_v1_feature_row.v1"
PARENT_MODEL_ID = "kxbtcd_candidate_e_entry_residual_logistic.v1"
PREOUTCOME_STAGE = {"H1_OOF": "H1", "H2": "H2", "H3": "H3"}

J_A_REQUIRED_COMMITTED_PATHS = {
    "configs/kxbtcd_candidate_e_conditional_alpha_reliability_v1_implementation_freeze.json",
    "docs/KXBTCD_CANDIDATE_E_CONDITIONAL_ALPHA_RELIABILITY_V1_IMPLEMENTATION.md",
    "prepare_kxbtcd_candidate_e_conditional_alpha_reliability_v1.py",
    "src/kxbtcd_candidate_e_conditional_alpha_reliability_v1.py",
    "src/kxbtcd_candidate_e_conditional_alpha_reliability_v1_materialization.py",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v1_implementation.py",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v1_preparation.py",
}

FEATURE_FIELDS = (
    "schema_version",
    "candidate_id",
    "stage",
    "state_id",
    "event_ticker",
    "event_close_time_utc",
    "market_ticker",
    "structural_role",
    "ttc_target_minutes",
    "decision_time_utc",
    "candidate_probability",
    "market_midpoint_yes_probability",
    "yes_bid",
    "yes_ask",
    "abs_candidate_market_disagreement",
    "spread_t",
    "abs_r_5m",
    "ttc_minutes",
)


class ConditionalAlphaMaterializationError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise ConditionalAlphaMaterializationError(message)


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv(path: str | Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        for i, row in enumerate(rows):
            if set(row) != set(fields):
                _error(f"output row[{i}] schema mismatch")
            writer.writerow({field: row[field] for field in fields})
    temp.replace(target)


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConditionalAlphaMaterializationError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        _error(f"{name} must be finite")
    return result


def _text(value: Any, name: str) -> str:
    text = str(value).strip()
    if not text:
        _error(f"{name} must be non-empty")
    return text


def _state_id(row: Mapping[str, Any]) -> str:
    event = _text(row.get("event_ticker"), "preoutcome.event_ticker")
    market = _text(row.get("market_ticker"), "preoutcome.market_ticker")
    role = _text(row.get("structural_role"), "preoutcome.structural_role")
    if role not in STRUCTURAL_ROLES:
        _error(f"unexpected structural role {role!r}")
    try:
        ttc = int(row.get("ttc_target_minutes"))
    except (TypeError, ValueError) as exc:
        raise ConditionalAlphaMaterializationError("preoutcome TTC must be integer") from exc
    if ttc not in TTC_LEVELS:
        _error(f"unexpected TTC {ttc}")
    return f"{event}|{market}|TTC{ttc}|{role}"


def _preoutcome_index(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if str(row.get("stage", "")) not in {"H1", "H2", "H3"}:
            continue
        state = _state_id(row)
        if state in result:
            _error(f"duplicate preoutcome state {state}")
        result[state] = row
    if not result:
        _error("preoutcome index is empty")
    return result



def validate_j_a_closeout_receipt(path: str | Path) -> dict[str, Any]:
    """Require a safely closed 21N-J-A before the real J-B materializer can run."""
    receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    if receipt.get("schema") != "checkpoint_closeout_receipt.v1":
        _error("J-A closeout receipt schema mismatch")
    message = str(receipt.get("checkpoint_message", ""))
    if not message.startswith("Checkpoint 21N-J-A"):
        _error("latest closeout receipt is not a Checkpoint 21N-J-A closeout")
    committed = {str(item) for item in receipt.get("committed_paths", ())}
    missing = sorted(J_A_REQUIRED_COMMITTED_PATHS - committed)
    if missing:
        _error("J-A closeout receipt is missing implementation paths: " + ", ".join(missing))
    safety = receipt.get("safety", {})
    required_pass = (
        "blocked_path_check",
        "staged_path_exact_match",
        "staged_diff_check",
        "high_confidence_secret_scan",
    )
    for key in required_pass:
        if safety.get(key) != "PASS":
            _error(f"J-A closeout safety.{key} must be PASS")
    if safety.get("remote_synchronized_before_commit") is not True:
        _error("J-A closeout was not synchronized before commit")
    if safety.get("worktree_clean_after_checkpoint_commit") is not True:
        _error("J-A closeout did not record a clean worktree")
    return receipt


def validate_parent_preparation(
    *,
    preparation_freeze_path: str | Path,
    feature_rows_path: str | Path,
    preoutcome_path: str | Path,
) -> dict[str, Any]:
    freeze = json.loads(Path(preparation_freeze_path).read_text(encoding="utf-8"))
    if freeze.get("schema_version") != PARENT_PREPARATION_SCHEMA:
        _error("parent preparation schema mismatch")
    if freeze.get("model_id") != PARENT_MODEL_ID:
        _error("parent preparation model mismatch")
    if freeze.get("preparation_fingerprint") != EXPECTED_PARENT_PREPARATION_FINGERPRINT:
        _error("parent preparation fingerprint mismatch")
    copy = dict(freeze)
    supplied = copy.pop("preparation_fingerprint", None)
    if canonical_sha256(copy) != supplied:
        _error("parent preparation fingerprint does not recompute")
    feature_sha = sha256_file(feature_rows_path)
    if feature_sha != EXPECTED_PARENT_FEATURE_FILE_SHA256:
        _error("parent feature CSV SHA-256 changed")
    if freeze.get("prepared_output_sha256s", {}).get("feature_rows") != feature_sha:
        _error("parent preparation receipt does not bind supplied feature CSV")
    preoutcome_sha = sha256_file(preoutcome_path)
    if freeze.get("source_file_sha256s", {}).get("preoutcome") != preoutcome_sha:
        _error("supplied preoutcome file does not match parent preparation receipt")
    if freeze.get("outcomes_in_feature_rows") is not False:
        _error("parent feature rows must remain outcome-blind")
    return freeze


def validate_parent_feature_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    enforce_frozen_counts: bool = True,
) -> None:
    if not rows:
        _error("parent feature rows are empty")
    seen: set[str] = set()
    stage_rows = {stage: 0 for stage in DEVELOPMENT_STAGES}
    stage_events = {stage: set() for stage in DEVELOPMENT_STAGES}
    event_stage: dict[str, str] = {}
    event_close: dict[str, str] = {}
    for i, row in enumerate(rows):
        if row.get("schema_version") != PARENT_FEATURE_SCHEMA:
            _error(f"parent row[{i}] schema mismatch")
        if row.get("model_id") != PARENT_MODEL_ID:
            _error(f"parent row[{i}] model mismatch")
        if "outcome" in row:
            _error("outcome field is prohibited in parent feature rows")
        stage = str(row.get("stage", ""))
        if stage not in DEVELOPMENT_STAGES:
            _error(f"parent row[{i}] unauthorized stage")
        state = _text(row.get("state_id"), f"parent row[{i}].state_id")
        event = _text(row.get("event_ticker"), f"parent row[{i}].event_ticker")
        if state in seen:
            _error(f"duplicate parent state {state}")
        seen.add(state)
        prior_stage = event_stage.setdefault(event, stage)
        if prior_stage != stage:
            _error(f"parent event {event} crosses development stages")
        close = _text(row.get("event_close_time_utc"), f"parent row[{i}].event_close_time_utc")
        prior_close = event_close.setdefault(event, close)
        if prior_close != close:
            _error(f"parent event {event} has inconsistent close timestamp")
        stage_rows[stage] += 1
        stage_events[stage].add(event)
        for name in ("candidate_probability", "r_5m", "spread_t"):
            _finite(row.get(name), f"parent row[{i}].{name}")
        ttc = int(row.get("ttc_target_minutes"))
        if ttc not in TTC_LEVELS:
            _error(f"parent row[{i}] unexpected TTC")
    if enforce_frozen_counts:
        if len(rows) != EXPECTED_TOTAL_ROWS:
            _error("parent development row count changed")
        if len({event for events in stage_events.values() for event in events}) != EXPECTED_TOTAL_EVENTS:
            _error("parent development event count changed")
        for stage in DEVELOPMENT_STAGES:
            if stage_rows[stage] != EXPECTED_STAGE_ROWS[stage]:
                _error(f"parent {stage} row count changed")
            if len(stage_events[stage]) != EXPECTED_STAGE_EVENTS[stage]:
                _error(f"parent {stage} event count changed")


def materialize_conditional_alpha_rows(
    *,
    parent_feature_rows: Sequence[Mapping[str, Any]],
    preoutcome_rows: Sequence[Mapping[str, Any]],
    enforce_frozen_counts: bool = True,
) -> tuple[dict[str, str], ...]:
    validate_parent_feature_rows(parent_feature_rows, enforce_frozen_counts=enforce_frozen_counts)
    preoutcome = _preoutcome_index(preoutcome_rows)
    result: list[dict[str, str]] = []
    for i, parent in enumerate(parent_feature_rows):
        state = _text(parent.get("state_id"), f"parent row[{i}].state_id")
        source = preoutcome.get(state)
        if source is None:
            _error(f"state {state} missing from preoutcome source")
        stage = _text(parent.get("stage"), f"{state}.stage")
        if source.get("stage") != PREOUTCOME_STAGE[stage]:
            _error(f"{state} preoutcome stage mismatch")
        for field in ("event_ticker", "market_ticker", "structural_role"):
            if str(parent.get(field, "")) != str(source.get(field, "")):
                _error(f"{state} parent/preoutcome {field} mismatch")
        if int(parent.get("ttc_target_minutes")) != int(source.get("ttc_target_minutes")):
            _error(f"{state} parent/preoutcome TTC mismatch")
        yes_bid = _finite(source.get("yes_bid"), f"{state}.yes_bid")
        yes_ask = _finite(source.get("yes_ask"), f"{state}.yes_ask")
        if not (0.0 <= yes_bid <= yes_ask <= 1.0):
            _error(f"{state} invalid/crossed quote")
        parent_spread = _finite(parent.get("spread_t"), f"{state}.spread_t")
        if not math.isclose(parent_spread, yes_ask - yes_bid, rel_tol=0.0, abs_tol=1e-12):
            _error(f"{state} frozen spread does not match preoutcome bid/ask")
        p_e = _finite(parent.get("candidate_probability"), f"{state}.candidate_probability")
        if not 0.0 <= p_e <= 1.0:
            _error(f"{state} Candidate-E probability outside [0,1]")
        q = 0.5 * (yes_bid + yes_ask)
        r5 = _finite(parent.get("r_5m"), f"{state}.r_5m")
        ttc = int(parent.get("ttc_target_minutes"))
        row = {
            "schema_version": ROW_SCHEMA_VERSION,
            "candidate_id": CANDIDATE_ID,
            "stage": stage,
            "state_id": state,
            "event_ticker": _text(parent.get("event_ticker"), f"{state}.event_ticker"),
            "event_close_time_utc": _text(parent.get("event_close_time_utc"), f"{state}.event_close_time_utc"),
            "market_ticker": _text(parent.get("market_ticker"), f"{state}.market_ticker"),
            "structural_role": _text(parent.get("structural_role"), f"{state}.structural_role"),
            "ttc_target_minutes": str(ttc),
            "decision_time_utc": _text(parent.get("decision_time_utc"), f"{state}.decision_time_utc"),
            "candidate_probability": _text(parent.get("candidate_probability"), f"{state}.candidate_probability_text"),
            "market_midpoint_yes_probability": format(q, ".17g"),
            "yes_bid": _text(source.get("yes_bid"), f"{state}.yes_bid_text"),
            "yes_ask": _text(source.get("yes_ask"), f"{state}.yes_ask_text"),
            "abs_candidate_market_disagreement": format(abs(p_e - q), ".17g"),
            "spread_t": _text(parent.get("spread_t"), f"{state}.spread_t_text"),
            "abs_r_5m": format(abs(r5), ".17g"),
            "ttc_minutes": format(float(ttc), ".17g"),
        }
        result.append(row)
    result.sort(
        key=lambda row: (
            DEVELOPMENT_STAGES.index(row["stage"]),
            row["event_close_time_utc"],
            row["event_ticker"],
            -int(row["ttc_target_minutes"]),
            row["market_ticker"],
        )
    )
    validate_materialized_rows(result, enforce_frozen_counts=enforce_frozen_counts)
    return tuple(result)


def canonical_rows_fingerprint(rows: Sequence[Mapping[str, Any]]) -> str:
    normalized = [
        {str(k): ("" if v is None else str(v)) for k, v in row.items()}
        for row in rows
    ]
    normalized.sort(key=lambda row: row["state_id"])
    return canonical_sha256(normalized)


def build_preparation_freeze(
    rows: Sequence[Mapping[str, Any]],
    *,
    parent_preparation_path: str | Path,
    parent_feature_rows_path: str | Path,
    preoutcome_path: str | Path,
    output_feature_rows_path: str | Path,
    implementation_sha256s: Mapping[str, str],
    enforce_frozen_counts: bool = True,
) -> dict[str, Any]:
    validate_materialized_rows(rows, enforce_frozen_counts=enforce_frozen_counts)
    payload: dict[str, Any] = {
        "schema_version": FREEZE_SCHEMA_VERSION,
        "checkpoint_id": "21N-J-B",
        "candidate_id": CANDIDATE_ID,
        "predeclaration_fingerprint": EXPECTED_PREDECLARATION_FINGERPRINT,
        "parent_model2_preparation_fingerprint": EXPECTED_PARENT_PREPARATION_FINGERPRINT,
        "parent_feature_file_sha256": sha256_file(parent_feature_rows_path),
        "parent_preparation_file_sha256": sha256_file(parent_preparation_path),
        "preoutcome_file_sha256": sha256_file(preoutcome_path),
        "feature_contract": list(FEATURE_FIELDS),
        "development_event_counts": dict(EXPECTED_STAGE_EVENTS),
        "development_row_counts": dict(EXPECTED_STAGE_ROWS),
        "feature_rows_fingerprint": canonical_rows_fingerprint(rows),
        "prepared_output_sha256": sha256_file(output_feature_rows_path),
        "implementation_sha256s": dict(sorted(implementation_sha256s.items())),
        "outcomes_attached": False,
        "gamma_fit_performed": False,
        "lambda_selected": False,
        "strategy_pnl_calculated": False,
        "c1_c2_accessed": False,
        "c3_accessed": False,
        "protected_reserve_accessed": False,
        "network_accessed": False,
        "execution_enabled": False,
    }
    payload["preparation_fingerprint"] = canonical_sha256(payload)
    return payload


def validate_preparation_freeze(
    document: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
    output_feature_rows_path: str | Path,
) -> None:
    if document.get("schema_version") != FREEZE_SCHEMA_VERSION:
        _error("conditional-alpha preparation freeze schema mismatch")
    if document.get("candidate_id") != CANDIDATE_ID:
        _error("conditional-alpha preparation candidate mismatch")
    copy = dict(document)
    supplied = copy.pop("preparation_fingerprint", None)
    if canonical_sha256(copy) != supplied:
        _error("conditional-alpha preparation fingerprint mismatch")
    if document.get("predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        _error("conditional-alpha predeclaration lineage mismatch")
    if document.get("parent_model2_preparation_fingerprint") != EXPECTED_PARENT_PREPARATION_FINGERPRINT:
        _error("parent preparation lineage mismatch")
    validate_materialized_rows(rows, enforce_frozen_counts=True)
    if document.get("feature_rows_fingerprint") != canonical_rows_fingerprint(rows):
        _error("conditional-alpha row fingerprint mismatch")
    if document.get("prepared_output_sha256") != sha256_file(output_feature_rows_path):
        _error("conditional-alpha prepared output SHA mismatch")
    for key in (
        "outcomes_attached", "gamma_fit_performed", "lambda_selected",
        "strategy_pnl_calculated", "c1_c2_accessed", "c3_accessed",
        "protected_reserve_accessed", "network_accessed", "execution_enabled",
    ):
        if document.get(key) is not False:
            _error(f"preparation safety flag {key} must be false")


__all__ = [
    "ConditionalAlphaMaterializationError",
    "FEATURE_FIELDS",
    "FREEZE_SCHEMA_VERSION",
    "ROW_SCHEMA_VERSION",
    "build_preparation_freeze",
    "canonical_rows_fingerprint",
    "materialize_conditional_alpha_rows",
    "read_csv",
    "sha256_file",
    "validate_j_a_closeout_receipt",
    "validate_parent_preparation",
    "validate_preparation_freeze",
    "write_csv",
]
