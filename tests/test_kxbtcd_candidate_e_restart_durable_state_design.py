from copy import deepcopy
import pytest

from src.kxbtcd_candidate_e_restart_durable_state_design import (
    RestartDurableStateDesignError,
    canonical_fingerprint,
    validate_design,
    validate_payload,
)

def canonical():
    return dict(validate_design("."))

def mutate_and_fail(mutator):
    p = deepcopy(canonical())
    mutator(p)
    p["design_fingerprint"] = canonical_fingerprint(p)
    with pytest.raises(RestartDurableStateDesignError):
        validate_payload(p, enforce_expected_fingerprint=False)

def test_canonical_design_validates():
    p = validate_design(".")
    assert p["scope"]["current_execution_mode"] == "disabled"

def test_no_cohort_extension():
    mutate_and_fail(lambda p: p["cohort_contract"].__setitem__("cohort_end_extension_allowed", True))

def test_no_backfill():
    mutate_and_fail(lambda p: p["downtime_contract"].__setitem__("missed_decisions_backfilled", True))

def test_sqlite_full_required():
    mutate_and_fail(lambda p: p["sqlite_contract"]["pragmas"].__setitem__("synchronous", "NORMAL"))

def test_old_kalshi_cache_forbidden():
    mutate_and_fail(lambda p: p["kalshi_restart_contract"].__setitem__("restore_old_book_cache", True))

def test_old_coinbase_freshness_forbidden():
    mutate_and_fail(lambda p: p["coinbase_restart_contract"].__setitem__("restore_old_heartbeat_freshness", True))

def test_exact_arm_commit_required():
    mutate_and_fail(lambda p: p["armed_code_identity_contract"].__setitem__("restart_current_git_commit_must_equal_arm_commit_exactly", False))

def test_ready_requires_coinbase_continuity():
    def edit(p):
        p["restart_state_machine"]["ready_requires_all"].remove("coinbase_continuity_proven")
    mutate_and_fail(edit)

def test_execution_stays_disabled():
    mutate_and_fail(lambda p: p["scope"].__setitem__("real_money_execution_authorized", True))

def test_zero_tolerance_acceptance():
    mutate_and_fail(lambda p: p["z_e_b_acceptance_invariants"].__setitem__("backfilled_downtime_live_decisions", 1))
