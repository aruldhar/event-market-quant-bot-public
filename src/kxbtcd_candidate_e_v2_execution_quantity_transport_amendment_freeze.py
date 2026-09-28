"""Checkpoint 21N-Y-A1 quantity-transport amendment validator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator_freeze import (
    EXPECTED_IMPLEMENTATION_FINGERPRINT as EXPECTED_PARENT_Y_A_IMPLEMENTATION_FINGERPRINT,
    validate_freeze as validate_parent_y_a_freeze,
)

DEFAULT_AMENDMENT_PATH = Path(
    "configs/kxbtcd_candidate_e_v2_execution_quantity_transport_amendment.json"
)
EXPECTED_AMENDMENT_FINGERPRINT = "2cbd8836045ae811eb4c52d48834953a54b1be3afac094be4cf349b8cac2abce"
EXPECTED_PARENT_Y_A_IMPLEMENTATION_FINGERPRINT = "b8f66b2f392df2c8711e7d6e25e64c54921b16f8f7866c243a6375aaec778949"


class V2QuantityTransportAmendmentValidationError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise V2QuantityTransportAmendmentValidationError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("amendment_fingerprint", None)
    raw = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_amendment(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)

    parent = validate_parent_y_a_freeze(repo)
    if parent.get("implementation_fingerprint") != EXPECTED_PARENT_Y_A_IMPLEMENTATION_FINGERPRINT:
        _fail("parent Y-A implementation fingerprint changed")

    path = repo / DEFAULT_AMENDMENT_PATH
    if not path.is_file():
        _fail(f"Y-A1 amendment missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("schema_version") != "kxbtcd_candidate_e_v2_execution_quantity_transport_amendment.v1":
        _fail("Y-A1 amendment schema changed")
    if payload.get("amendment_fingerprint") != EXPECTED_AMENDMENT_FINGERPRINT:
        _fail("Y-A1 amendment fingerprint field changed")
    if canonical_fingerprint(payload) != EXPECTED_AMENDMENT_FINGERPRINT:
        _fail("Y-A1 canonical fingerprint changed")

    if payload["parent_y_a"]["implementation_fingerprint"] != EXPECTED_PARENT_Y_A_IMPLEMENTATION_FINGERPRINT:
        _fail("Y-A1 parent binding changed")

    observed = payload["observed_failure"]
    if observed["completed_path_artifact_created"] is not False:
        _fail("failed Y-B attempt may not be relabeled as completed")
    if observed["candidate_e_nonstructural_scoring_started"] is not True:
        _fail("Y-B evidence exposure must remain honestly recorded")
    if observed["settlement_outcomes_accessed"] is not False:
        _fail("settlement outcomes must remain closed")

    diag = payload["diagnostic_evidence"]
    if diag["paid_delta_rows_checked"] != 5644964:
        _fail("paid diagnostic row count changed")
    if diag["paid_delta_off_grid_count"] != 0:
        _fail("paid deltas are expected exact-grid")
    if diag["snapshot_levels_checked"] != 13695870:
        _fail("snapshot diagnostic level count changed")
    if diag["snapshot_off_grid_count"] != 763392:
        _fail("snapshot off-grid diagnostic count changed")
    if diag["snapshot_off_grid_within_1e_9_of_cent_count"] != 763392:
        _fail("snapshot tiny-residue count changed")
    if diag["snapshot_materially_off_cent_count"] != 0:
        _fail("materially off-cent snapshot count must remain zero")

    rule = payload["amendment_rule"]
    if rule["quantity_quantum"] != "0.01":
        _fail("quantity quantum changed")
    if rule["maximum_absolute_transport_residue"] != "0.000000001":
        _fail("transport residue tolerance changed")
    if rule["application_boundary"] != "after_verified_replay_reconstruction_before_v2_decision_and_execution_use":
        _fail("transport amendment application boundary changed")

    non_changes = payload["explicit_non_changes"]
    required_false = [
        "raw_snapshot_files_modified",
        "paid_tick_parquet_modified",
        "replay_reconciliation_modified",
        "replay_segment_boundaries_modified",
        "replay_summary_hash_modified",
        "parent_y_a_files_modified",
        "parent_y_a_implementation_fingerprint_modified",
        "candidate_e_modified",
        "atm_plus_minus_5_universe_modified",
        "thresholds_modified",
        "fees_modified",
        "latencies_modified",
        "ioc_quantity_grid_weakened",
        "liquidation_policy_modified",
        "reentry_policy_modified",
    ]
    for key in required_false:
        if non_changes.get(key) is not False:
            _fail(f"forbidden amendment expansion: {key}")

    files = payload["frozen_amendment_files"]
    for relative_path, expected_hash in files.items():
        p = repo / relative_path
        if not p.is_file():
            _fail(f"frozen amendment file missing: {relative_path}")
        if _sha256(p) != expected_hash:
            _fail(f"frozen amendment file changed: {relative_path}")

    safety = payload["safety"]
    expected_safety = {
        "outcomes_accessed": False,
        "strategy_pnl_calculated": False,
        "candidate_e_refit": False,
        "network_requests": 0,
        "predexon_paid_purchases": 0,
        "orders_placed": 0,
        "paper_broker": False,
        "demo_execution": False,
        "real_money_execution": False,
        "protected_reserve_accessed": False,
    }
    for key, expected in expected_safety.items():
        if safety.get(key) != expected:
            _fail(f"safety invariant changed: {key}")

    return payload
