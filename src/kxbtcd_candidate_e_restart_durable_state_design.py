from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

CONFIG_RELATIVE_PATH = "configs/kxbtcd_candidate_e_restart_durable_state_design_v1.json"
EXPECTED_DESIGN_FINGERPRINT = "40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda"
EXPECTED_ARCHITECTURE_FINGERPRINT = "3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7"
EXPECTED_CANDIDATE_FINGERPRINT = "b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc"
EXPECTED_PROSPECTIVE_WEEK_SHA = "60f24fd8424aff93a65006a87e31ef150417f3f393bf0a5de19f65ceeb4f2869"

class RestartDurableStateDesignError(RuntimeError):
    pass

def fail(message: str) -> None:
    raise RestartDurableStateDesignError(message)

def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    p = deepcopy(dict(payload))
    p.pop("design_fingerprint", None)
    return sha256(
        json.dumps(p, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

def validate_payload(payload: Mapping[str, Any], *, enforce_expected_fingerprint: bool = True):
    if payload.get("schema_version") != "kxbtcd_candidate_e_restart_durable_state_design.v1":
        fail("schema changed")
    actual = canonical_fingerprint(payload)
    if payload.get("design_fingerprint") != actual:
        fail("embedded fingerprint mismatch")
    if enforce_expected_fingerprint and actual != EXPECTED_DESIGN_FINGERPRINT:
        fail("frozen design fingerprint changed")

    if payload["frozen_parent_architecture"]["architecture_fingerprint"] != EXPECTED_ARCHITECTURE_FINGERPRINT:
        fail("architecture fingerprint changed")
    if payload["frozen_scientific_bindings"]["candidate_fingerprint"] != EXPECTED_CANDIDATE_FINGERPRINT:
        fail("candidate fingerprint changed")
    if payload["frozen_scientific_bindings"]["prospective_week_sha256"] != EXPECTED_PROSPECTIVE_WEEK_SHA:
        fail("prospective SHA changed")
    if payload["frozen_scientific_bindings"]["duration_hours"] != 168:
        fail("duration changed")
    if payload["frozen_scientific_bindings"]["primary_net_edge_threshold_dollars"] != "0.02":
        fail("threshold changed")

    scope = payload["scope"]
    if scope["current_execution_mode"] != "disabled":
        fail("execution enabled")
    for key in (
        "restart_runtime_implementation_authorized",
        "sqlite_runtime_implementation_authorized",
        "prospective_cohort_arm_authorized",
        "paper_execution_authorized",
        "demo_execution_authorized",
        "real_money_execution_authorized",
        "order_submission_code_authorized",
        "network_activity_in_this_checkpoint",
        "strategy_or_model_retuning_authorized",
    ):
        if scope[key] is not False:
            fail(f"design-only scope changed: {key}")

    cohort = payload["cohort_contract"]
    for key in (
        "cohort_rearm_or_restart_mid_window_allowed",
        "cohort_end_extension_allowed",
        "replace_lost_observation_time_allowed",
        "replace_events_lost_to_downtime_allowed",
        "backfill_missed_live_decisions_allowed",
        "historical_replay_may_be_labeled_as_live_decision",
    ):
        if cohort[key] is not False:
            fail(f"anti-backfill rule changed: {key}")

    if payload["sqlite_contract"]["pragmas"] != {
        "journal_mode": "WAL",
        "synchronous": "FULL",
        "foreign_keys": "ON",
        "busy_timeout_ms": 5000,
        "locking_mode": "NORMAL",
    }:
        fail("SQLite durability pragmas changed")

    if payload["raw_journal_restart_contract"]["append_to_prior_session_raw_segment_allowed"] is not False:
        fail("prior raw segment append became allowed")
    if payload["kalshi_restart_contract"]["restore_old_book_cache"] is not False:
        fail("old Kalshi cache became restorable")
    if payload["coinbase_restart_contract"]["restore_old_heartbeat_freshness"] is not False:
        fail("old Coinbase freshness became restorable")
    if payload["downtime_contract"]["cohort_clock_pauses"] is not False:
        fail("cohort clock may pause")
    if payload["downtime_contract"]["missed_decisions_backfilled"] is not False:
        fail("downtime backfill became allowed")
    if payload["armed_code_identity_contract"]["restart_current_git_commit_must_equal_arm_commit_exactly"] is not True:
        fail("exact arm commit no longer required")

    required_ready = {
        "identity_and_frozen_commit_match",
        "cohort_active_and_before_fixed_end",
        "sqlite_integrity_proven",
        "prior_session_classified",
        "raw_reference_reconciliation_complete",
        "clock_healthy",
        "exact_current_completed_coinbase_minute_available",
        "coinbase_continuity_proven",
        "kalshi_current_event_full_ladder_exact",
        "durable_read_only_strategy_state_reconciled",
        "execution_mode_disabled",
    }
    if set(payload["restart_state_machine"]["ready_requires_all"]) != required_ready:
        fail("READY_READ_ONLY gate changed")
    if payload["restart_state_machine"]["gate_failure_behavior"] != "NO_NEW_SIGNAL":
        fail("gate failure behavior changed")
    if len(payload["z_e_b_required_test_matrix"]) != 17:
        fail("test matrix changed")
    if any(v != 0 for v in payload["z_e_b_acceptance_invariants"].values()):
        fail("zero-tolerance invariant changed")
    return payload

def validate_design(repo_root: str | Path = "."):
    repo = Path(repo_root)
    payload = json.loads((repo / CONFIG_RELATIVE_PATH).read_text(encoding="utf-8"))
    return validate_payload(payload)
