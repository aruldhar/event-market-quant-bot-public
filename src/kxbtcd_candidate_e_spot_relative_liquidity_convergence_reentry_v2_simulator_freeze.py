"""Checkpoint 21N-Y-A implementation-freeze validator."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_predeclaration import (
    EXPECTED_PREDECLARATION_FINGERPRINT,
    validate_predeclaration,
)

DEFAULT_FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_implementation_freeze.json"
)
EXPECTED_IMPLEMENTATION_FINGERPRINT = "b8f66b2f392df2c8711e7d6e25e64c54921b16f8f7866c243a6375aaec778949"
EXPECTED_PREDECLARATION_FINGERPRINT = "3e44c6ce3b9e420db3cf0dd52c2b64030ae99901c491d9cf0bc15617930ef8ae"
EXPECTED_21N_R_IMPLEMENTATION_FINGERPRINT = "6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf"
EXPECTED_SOURCE_BINDING_FINGERPRINT = "8cf8ead70da5f56def1a0d67619b2cda75316e6345383e8ebdcf79f9c4cf62b7"


class V2ImplementationFreezeError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise V2ImplementationFreezeError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("implementation_fingerprint", None)
    raw = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_freeze(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)

    predecl = validate_predeclaration(repo)
    if predecl.get("predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        _fail("V2 predeclaration fingerprint mismatch")

    path = repo / DEFAULT_FREEZE_PATH
    if not path.is_file():
        _fail(f"V2 implementation freeze missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))

    if (
        payload.get("schema_version")
        != "kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_implementation_freeze.v1"
    ):
        _fail("implementation-freeze schema mismatch")

    if payload.get("implementation_fingerprint") != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        _fail("implementation fingerprint field changed")
    if canonical_fingerprint(payload) != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        _fail("implementation canonical fingerprint changed")
    if payload.get("predeclaration_fingerprint") != EXPECTED_PREDECLARATION_FINGERPRINT:
        _fail("implementation/predeclaration binding changed")
    if (
        payload.get("inherited_21n_r_implementation_fingerprint")
        != EXPECTED_21N_R_IMPLEMENTATION_FINGERPRINT
    ):
        _fail("21N-R implementation binding changed")
    if (
        payload.get("july10_source_binding_fingerprint")
        != EXPECTED_SOURCE_BINDING_FINGERPRINT
    ):
        _fail("July 10 source binding changed")

    files = payload.get("implementation_files")
    if not isinstance(files, Mapping) or len(files) != 2:
        _fail("expected exactly two frozen implementation files")
    for relative_path, expected_hash in files.items():
        file_path = repo / str(relative_path)
        if not file_path.is_file():
            _fail(f"implementation file missing: {relative_path}")
        observed = _sha256(file_path)
        if observed != expected_hash:
            _fail(
                f"implementation file changed: {relative_path} "
                f"expected={expected_hash} observed={observed}"
            )

    contract = payload.get("implementation_contract", {})
    if contract.get("maximum_markets_per_window") != 11:
        _fail("dynamic universe maximum changed")
    if contract.get("liquidity_defines_window_membership") is not False:
        _fail("liquidity must not define ATM-window membership")
    if contract.get("path_runner_included_but_not_executed") is not True:
        _fail("Y-A must freeze runner before executing it")
    if contract.get("path_runner_requires_this_freeze") is not True:
        _fail("path runner must be freeze-gated")
    if contract.get("full_623_ticker_source_set_still_validated_before_path_run") is not True:
        _fail("full source-set validation must remain enabled")

    safety = payload.get("evidence_and_safety", {})
    expected = {
        "real_july10_nonstructural_candidate_e_scoring_before_freeze": False,
        "july10_v2_paths_run_before_freeze": False,
        "july10_v2_outcomes_accessed": False,
        "fresh_24_event_source_materialization_run": False,
        "fresh_24_event_outcomes_accessed": False,
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
    for key, expected_value in expected.items():
        if safety.get(key) != expected_value:
            _fail(f"Y-A safety invariant changed: {key}")

    return payload
