from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("configs/kxbtcd_candidate_e_executable_convergence_liquidation_v1_predeclaration.json")
EXPECTED_SCHEMA = "kxbtcd_candidate_e_executable_convergence_liquidation_v1_predeclaration.v1"
EXPECTED_STRATEGY = "kxbtcd_candidate_e_executable_convergence_liquidation_v1"
EXPECTED_PARENT_RECEIPT = "21bb2bb6d38295411aa8381dc176e5841072e422"
EXPECTED_CHAMPION = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"

def canonical_fingerprint(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("predeclaration_fingerprint", None)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def load_predeclaration(path: Path | str = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("predeclaration must be a JSON object")
    return payload

def validate_predeclaration(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != EXPECTED_SCHEMA:
        raise ValueError("unexpected schema_version")
    if payload.get("strategy_id") != EXPECTED_STRATEGY:
        raise ValueError("unexpected strategy_id")
    if payload["parent_checkpoint"]["receipt_commit"] != EXPECTED_PARENT_RECEIPT:
        raise ValueError("parent receipt mismatch")
    if payload["candidate_e"]["champion_final_fingerprint"] != EXPECTED_CHAMPION:
        raise ValueError("Champion-Final fingerprint mismatch")
    if canonical_fingerprint(payload) != payload.get("predeclaration_fingerprint"):
        raise ValueError("predeclaration fingerprint mismatch")
    if payload["candidate_universe"]["structural_roles"] != ["q10","q30","q50","q70","q90"]:
        raise ValueError("structural role menu changed")
    if payload["candidate_universe"]["anchor_order_ttc_minutes"] != [55,50,45,40,35,30]:
        raise ValueError("TTC grid changed")
    if payload["decision_state"]["edge_threshold_dollars"] != ["0.00","0.01","0.02","0.03","0.05"]:
        raise ValueError("edge-margin menu changed")
    if payload["entry_execution"]["latency_ms"] != [0,500,1000]:
        raise ValueError("latency menu changed")
    if payload["decision_state"]["planned_contracts"] != "1.00":
        raise ValueError("planned size changed")
    if payload["candidate_e"]["refit_allowed"]:
        raise ValueError("Candidate E refit must remain disabled")
    if payload["candidate_e"]["post_entry_probability_recomputation_for_exit_allowed"]:
        raise ValueError("exit target must remain entry-time frozen")
    lp = payload["liquidation_policy"]
    if lp["frozen_target_per_contract"] != "entry_time_side_fair_probability":
        raise ValueError("liquidation target changed")
    if lp["exit_attempt_count"] != 1 or not lp["no_retry_after_partial_or_missed_exit"]:
        raise ValueError("liquidation retry contract changed")
    if lp["gap_before_trigger"] != "primary_liquidation_branch_source_unavailable":
        raise ValueError("gap handling changed")
    ev = payload["evidence_scope"]
    if ev["independent_event_count"] != 4:
        raise ValueError("unexpected independent event count")
    if ev["strategy_outcomes_accessed_before_predeclaration"] or ev["strategy_pnl_calculated_before_predeclaration"]:
        raise ValueError("outcome/P&L firewall violated")
    if ev["may_select_winning_policy_from_four_events"]:
        raise ValueError("four-event winner selection must remain disabled")
    for key in ("orders_submitted","paper_broker","demo_execution","real_money_execution",
                "predexon_purchase_authorized_by_this_checkpoint","c1_c2_c3_or_protected_reserve_access"):
        if payload["safety"][key]:
            raise ValueError(f"safety flag unexpectedly enabled: {key}")
