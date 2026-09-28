"""Checkpoint 21N-W spot/ATM liquidity geometry result closeout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.kxbtcd_candidate_e_continuous_july10_result_closeout import (
    EXPECTED_RESULT_CLOSEOUT_FINGERPRINT as EXPECTED_21N_V_CLOSEOUT_FINGERPRINT,
    validate_result_closeout as validate_21n_v_closeout,
)
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import sha256_file

DEFAULT_CLOSEOUT_PATH = Path(
    "configs/kxbtcd_candidate_e_spot_atm_liquidity_geometry_closeout.json"
)
EXPECTED_RESULT_CLOSEOUT_FINGERPRINT = "04fb52fc5f1b6aa34d7c31d6e174f1519336278fb2e2f09282afc263723d26e5"
EXPECTED_GEOMETRY_ARTIFACT_RELATIVE_PATH = Path("data/analysis/predexon_credit_efficiency/july10_candidate_e_spot_atm_liquidity_geometry.json")
EXPECTED_GEOMETRY_ARTIFACT_SHA256 = "b2448067c525aaaa6e2f076bed321fb9e55621fcb1319f9a2c282d24d1e31393"
EXPECTED_21N_V_FINGERPRINT = "c55bf6ca462cb4c5d0676a11cac9f37541fe001ce0770d7b08f9fe0721eede35"

class SpotAtmLiquidityGeometryCloseoutError(RuntimeError):
    pass

def _fail(message: str) -> None:
    raise SpotAtmLiquidityGeometryCloseoutError(message)

def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("result_closeout_fingerprint", None)
    raw = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def validate_closeout(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)

    parent = validate_21n_v_closeout(repo)
    if parent.get("result_closeout_fingerprint") != EXPECTED_21N_V_FINGERPRINT:
        _fail("21N-V parent closeout changed")

    path = repo / DEFAULT_CLOSEOUT_PATH
    if not path.is_file():
        _fail(f"21N-W closeout missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("schema_version") != "kxbtcd_candidate_e_spot_atm_liquidity_geometry_closeout.v1":
        _fail("21N-W closeout schema changed")
    if payload.get("classification") != "EXPLORATORY_SUPPORT_SPOT_ATM_RELATIVE_LIQUIDITY_STRUCTURE":
        _fail("21N-W classification changed")
    if payload.get("result_closeout_fingerprint") != EXPECTED_RESULT_CLOSEOUT_FINGERPRINT:
        _fail("21N-W result fingerprint field changed")
    if canonical_fingerprint(payload) != EXPECTED_RESULT_CLOSEOUT_FINGERPRINT:
        _fail("21N-W canonical fingerprint changed")

    artifact = repo / EXPECTED_GEOMETRY_ARTIFACT_RELATIVE_PATH
    if not artifact.is_file():
        _fail(f"geometry artifact missing: {artifact}")
    if sha256_file(artifact) != EXPECTED_GEOMETRY_ARTIFACT_SHA256:
        _fail("geometry artifact SHA changed")
    geometry = json.loads(artifact.read_text(encoding="utf-8"))

    if geometry.get("schema_version") != "kxbtcd_candidate_e_spot_atm_liquidity_geometry.v1":
        _fail("geometry artifact schema changed")
    if geometry.get("checkpoint_id") != "21N-W":
        _fail("geometry artifact checkpoint changed")

    observed = payload.get("observed_result", {})
    overall = geometry.get("overall", {})

    exact = {
        "total_cross_sections": 216,
        "cross_sections_with_any_valid_two_sided": 177,
        "atm_ticker_two_sided_cross_sections": 62,
        "median_nearest_abs_rank_from_atm": "1",
        "max_nearest_abs_rank_from_atm": 4,
        "active_ticker_minute_instance_count": 755,
        "median_active_instance_abs_rank_from_atm": "3",
        "median_active_instance_abs_strike_minus_spot": "286.25",
        "median_active_instance_abs_btc_distance_bps": "44.80983821395667",
    }
    for key, expected in exact.items():
        if overall.get(key) != expected:
            _fail(f"geometry observed summary changed: {key}={overall.get(key)!r}")

    if overall.get("nearest_two_sided_within_rank_counts") != observed.get(
        "nearest_two_sided_within_rank_counts"
    ):
        _fail("nearest rank counts differ from closeout")
    if overall.get("active_instance_within_rank_counts") != observed.get(
        "active_instance_within_rank_counts"
    ):
        _fail("active instance rank counts differ from closeout")

    interpretation = payload.get("interpretation", {})
    if interpretation.get("spot_atm_relative_liquidity_structure_supported_exploratorily") is not True:
        _fail("spot/ATM exploratory conclusion changed")
    if interpretation.get("v2_rank_envelope_selected") is not False:
        _fail("21N-W must not select a v2 envelope")
    if interpretation.get("nonstructural_candidate_e_use_validated") is not False:
        _fail("21N-W must not validate nonstructural Candidate E use")
    if interpretation.get("profitability_established") is not False:
        _fail("21N-W must not establish profitability")
    if interpretation.get("independent_event_count") != 4:
        _fail("independent event count changed")

    consequence = payload.get("research_consequence", {})
    if consequence.get("continuous_v1_remains_closed") is not True:
        _fail("continuous v1 must remain closed")
    if consequence.get("modify_continuous_v1_authorized") is not False:
        _fail("continuous v1 modification must remain unauthorized")
    if consequence.get("open_v1_settlement_outcomes_authorized") is not False:
        _fail("v1 outcomes must remain closed")

    safety = payload.get("safety", {})
    expected_safety = {
        "candidate_e_scored": False,
        "candidate_e_refit": False,
        "nonstructural_probability_inference": False,
        "outcomes_accessed": False,
        "settlement_pnl_calculated": False,
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
