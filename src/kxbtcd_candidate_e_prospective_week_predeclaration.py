"""Checkpoint 21N-Z-A prospective Candidate-E week predeclaration validator."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Mapping

CONFIG_PATH = Path("configs/kxbtcd_candidate_e_prospective_week_predeclaration.json")
EXPECTED_SCHEMA = "kxbtcd_candidate_e_prospective_week_predeclaration.v1"
EXPECTED_MODEL_FINGERPRINT = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
EXPECTED_E2_SETTLEMENT_SHA = "fd830587b393b90f787674bad9a0ecf9a83aac54b4c2410110a97b40533fab46"
EXPECTED_E2_REPORT_SHA = "aff1847d70b9dc945c5575295a3f3d3e0b2ecc54011d37fa30c57aa3e88bdf22"

class ProspectivePredeclarationError(RuntimeError): pass

def require(c: bool, m: str) -> None:
    if not c: raise ProspectivePredeclarationError(m)

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def validate_predeclaration(repo_root: str | Path = ".") -> Mapping[str, Any]:
    repo = Path(repo_root)
    p = load_json(repo / CONFIG_PATH)
    require(p["schema_version"] == EXPECTED_SCHEMA, "schema mismatch")
    require(p["checkpoint_id"] == "21N-Z-A", "checkpoint mismatch")
    require(p["model"]["champion_final_fingerprint"] == EXPECTED_MODEL_FINGERPRINT, "model changed")
    require(p["model"]["refit_during_prospective_window"] is False, "refit forbidden")
    e = p["e2_result_closeout"]
    require(e["settlement_manifest_sha256"] == EXPECTED_E2_SETTLEMENT_SHA, "E2 settlement SHA changed")
    require(e["sensitivity_report_sha256"] == EXPECTED_E2_REPORT_SHA, "E2 report SHA changed")
    require(e["observed_trace_sign_counts"] == {"NEGATIVE":3,"POSITIVE":24,"ZERO":6}, "E2 trace counts changed")
    require(e["independent_entry_hold_pnl_sign_counts"] == {"NEGATIVE":33,"POSITIVE":60}, "E2 entry counts changed")
    q = p["prospective_primary_policy"]
    require(q["primary_net_edge_threshold_dollars"] == "0.02", "primary edge changed")
    require(q["threshold_selection_basis"] == "mechanical_midpoint_of_preexisting_frozen_grid_not_july10_pnl", "edge selection basis changed")
    require(q["max_filled_entries_per_event"] == 2 and q["max_reentries_per_event"] == 1, "entry cap changed")
    require(q["rearm_after_full_first_exit"]["any_of"] == [
        "REFERENCE_LEFT_SPOT_WINDOW",
        "REFERENCE_DEPTH_BELOW_ONE_CONTRACT",
        "REFERENCE_EDGE_BELOW_PRIMARY_THRESHOLD",
    ], "rearm rule changed")
    require(q["exit_rule"]["mechanics"] == "existing_v2_convergence_liquidation_rule", "exit rule changed")
    s = p["source_contract"]
    require(s["required_btc_source"] == "Coinbase", "BTC source changed")
    require(s["btc_current_state"] == "exact_close_of_last_fully_completed_utc_coinbase_one_minute_candle_at_decision_time", "BTC state changed")
    require(p["prospective_window"]["duration_hours"] == 168, "window changed")
    t = p["timing_contract"]
    require(t["artificial_latency_grid_used_for_primary"] is False, "artificial latency grid must remain off")
    z = p["safety"]
    require(z["read_only_checkpoint"] is True, "Z-A must remain read-only")
    require(z["order_submission_code_added"] is False, "order code forbidden")
    require(z["real_money_orders_authorized"] is False, "real-money execution not authorized")
    return p
