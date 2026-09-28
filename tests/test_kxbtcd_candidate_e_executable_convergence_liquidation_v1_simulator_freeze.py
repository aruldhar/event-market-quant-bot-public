import copy
import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator_freeze import (
    FREEZE_PATH,
    build_freeze,
    canonical_fingerprint,
    validate_freeze,
)


def test_freeze_matches_recomputed_implementation_contract():
    document = validate_freeze(".")
    assert document == build_freeze(".")
    assert canonical_fingerprint(document) == document["implementation_fingerprint"]


def test_outcome_and_pnl_firewalls_are_frozen():
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    safety = document["evidence_and_safety"]
    assert safety["july10_outcomes_accessed_by_implementation"] is False
    assert safety["strategy_pnl_calculated_by_implementation"] is False
    assert safety["orders_submitted"] == 0
    assert safety["paper_broker"] is False
    assert safety["demo_execution"] is False
    assert safety["real_money_execution"] is False


def test_right_continuous_and_nonimpacting_conventions_are_explicit():
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    runtime = document["frozen_runtime_contract"]
    assert runtime["decision_state_convention"] == "right_continuous_final_reconstructed_state_per_millisecond"
    assert runtime["same_millisecond_transients_exposed"] is False
    assert runtime["future_book_after_counterfactual_ioc"] == "historical_path_exogenous_small_order_nonimpacting_assumption"
    assert runtime["future_book_impact_claimed_observed"] is False


def test_latency_failure_and_exit_rules_cannot_silently_change():
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    runtime = document["frozen_runtime_contract"]
    assert runtime["latency_failure_falls_through_to_later_anchor"] is False
    assert runtime["liquidation_exit_attempt_count"] == 1
    assert runtime["exit_partial_or_missed_remainder"] == "settlement_fallback"
    assert runtime["after_close_book_data_allowed"] is False


def test_fee_amendment_is_bound_into_runtime_freeze():
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    fee = document["fee_accounting_contract"]
    assert fee["trade_fee_component_rounding"] == "ceil_to_0.000001"
    assert fee["direct_member_balance_grid_dollars"] == "0.0001"
    assert fee["rounding_accumulator_scope"] == "one_IOC_order"
    assert fee["accumulator_resets_between_entry_and_exit_orders"] is True


def test_next_checkpoint_remains_outcome_blind():
    document = json.loads(Path(FREEZE_PATH).read_text(encoding="utf-8"))
    nxt = document["next_checkpoint"]
    assert nxt["id"] == "21N-S"
    assert nxt["outcomes_must_remain_closed"] is True
    assert nxt["pnl_must_remain_unrun"] is True
