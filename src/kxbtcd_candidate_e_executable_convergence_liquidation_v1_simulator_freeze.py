"""Checkpoint 21N-R simulator implementation-freeze contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    AMENDMENT_PATH,
    BASE_PREDECLARATION_FINGERPRINT,
    CHAMPION_FINAL_FINGERPRINT,
    FEE_AMENDMENT_FINGERPRINT,
    FINAL_MODEL_PATH,
    LATENCY_MS,
    PLANNED_QUANTITY,
    STRATEGY_ID,
    STRUCTURAL_ROLES,
    THRESHOLDS,
    validate_frozen_parents,
)

FREEZE_PATH = Path("configs/kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator_implementation_freeze.json")
SCHEMA_VERSION = "kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator_implementation_freeze.v1"
CHECKPOINT_ID = "21N-R"
PARENT_CHECKPOINT_COMMIT = "7a8a041b85f32952a734324d214804ece3c88c88"
PARENT_RECEIPT_COMMIT = "78b86fa0cc18c3a7a232fc65be593229fd7bc092"
IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator.py",
    "src/kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator_freeze.py",
)


class SimulatorImplementationFreezeError(RuntimeError):
    pass


def _error(message: str) -> None:
    raise SimulatorImplementationFreezeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_fingerprint(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("implementation_fingerprint", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def build_freeze(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root)
    validate_frozen_parents(repo)
    hashes = {}
    for relative in IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"implementation file missing: {relative}")
        hashes[relative] = sha256_file(path)

    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "strategy_id": STRATEGY_ID,
        "parent_21n_q1": {
            "checkpoint_commit": PARENT_CHECKPOINT_COMMIT,
            "receipt_commit": PARENT_RECEIPT_COMMIT,
            "base_strategy_predeclaration_fingerprint": BASE_PREDECLARATION_FINGERPRINT,
            "fee_accounting_amendment_fingerprint": FEE_AMENDMENT_FINGERPRINT,
        },
        "champion_final_fingerprint": CHAMPION_FINAL_FINGERPRINT,
        "implementation_file_sha256s": hashes,
        "frozen_runtime_contract": {
            "structural_roles": list(STRUCTURAL_ROLES),
            "anchor_order_ttc_minutes": [55, 50, 45, 40, 35, 30],
            "thresholds_dollars": [format(value, "f") for value in THRESHOLDS],
            "latency_ms": list(LATENCY_MS),
            "planned_quantity_contracts": format(PLANNED_QUANTITY, "f"),
            "decision_state_convention": "right_continuous_final_reconstructed_state_per_millisecond",
            "same_millisecond_transients_exposed": False,
            "decision_best_price_level_must_display_full_planned_quantity": True,
            "latency_failure_falls_through_to_later_anchor": False,
            "entry_order": "IOC_limit_buy_at_decision_time_best_purchase_ask",
            "entry_price_improvement_allowed": True,
            "entry_price_worsening_beyond_limit_allowed": False,
            "entry_partial_and_missed_fills_enabled": True,
            "future_book_after_counterfactual_ioc": "historical_path_exogenous_small_order_nonimpacting_assumption",
            "future_book_impact_claimed_observed": False,
            "liquidation_trigger_scan_first_state": "entry_arrival_state",
            "liquidation_trigger_requires_full_open_quantity_depth": True,
            "liquidation_trigger_target": "net_cash_at_least_entry_time_side_fair_probability_times_open_quantity",
            "liquidation_exit_limit": "worst_bid_consumed_by_trigger_hypothetical_full_liquidation",
            "liquidation_exit_attempt_count": 1,
            "exit_partial_or_missed_remainder": "settlement_fallback",
            "monitoring_end": "event_close_time",
            "after_close_book_data_allowed": False,
            "verified_segment_gap_policy": "source_unavailable_never_skipped",
            "matched_hold_control_quantity": "identical_realized_entry_fill_quantity",
            "realized_pnl_function_present": False,
            "settlement_outcome_reader_present": False,
        },
        "fee_accounting_contract": {
            "numeric_type": "Decimal",
            "trade_fee_model": "0.07*C*P*(1-P)",
            "trade_fee_component_rounding": "ceil_to_0.000001",
            "direct_member_balance_grid_dollars": "0.0001",
            "rounding_accumulator_scope": "one_IOC_order",
            "rounding_rebate_quantum_dollars": "0.0001",
            "accumulator_resets_between_entry_and_exit_orders": True,
            "synthetic_fill_partition": "one_fill_per_consumed_price_level",
        },
        "evidence_and_safety": {
            "july10_outcomes_accessed_by_implementation": False,
            "strategy_pnl_calculated_by_implementation": False,
            "network_requests": 0,
            "orders_submitted": 0,
            "paper_broker": False,
            "demo_execution": False,
            "real_money_execution": False,
            "candidate_e_refit": False,
            "model2_used": False,
            "c1_c2_c3_or_protected_reserve_accessed": False,
            "new_predexon_purchase": False,
            "four_event_july10_evidence_role": "exploratory_methodology_development_only",
            "advancement_gate": "none_due_to_four_independent_events",
        },
        "next_checkpoint": {
            "id": "21N-S",
            "name": "July 10 Outcome-Blind Strategy Input and Execution-Path Materialization",
            "outcomes_must_remain_closed": True,
            "pnl_must_remain_unrun": True,
            "purpose": "bind actual July10 structural roles, BTC anchor states, verified replay states, selected signals, and execution paths before settlement labels",
        },
    }
    document["implementation_fingerprint"] = canonical_fingerprint(document)
    return document


def validate_freeze(
    repository_root: str | Path = ".",
    freeze_path: str | Path = FREEZE_PATH,
) -> dict[str, Any]:
    repo = Path(repository_root)
    path = Path(freeze_path)
    if not path.is_absolute():
        path = repo / path
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SimulatorImplementationFreezeError(f"could not read freeze: {exc}") from exc
    if not isinstance(document, dict):
        _error("freeze root must be object")

    if document.get("schema_version") != SCHEMA_VERSION:
        _error("freeze schema mismatch")
    if document.get("checkpoint_id") != CHECKPOINT_ID:
        _error("checkpoint mismatch")
    if document.get("strategy_id") != STRATEGY_ID:
        _error("strategy mismatch")

    expected = build_freeze(repo)
    if document != expected:
        observed_fp = document.get("implementation_fingerprint")
        expected_fp = expected.get("implementation_fingerprint")
        _error(f"implementation freeze mismatch; observed={observed_fp}, expected={expected_fp}")
    return document
