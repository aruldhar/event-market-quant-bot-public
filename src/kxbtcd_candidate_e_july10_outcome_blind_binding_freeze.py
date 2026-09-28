"""Checkpoint 21N-S-A implementation-freeze contract."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .kxbtcd_candidate_e_july10_outcome_blind_binding import (
    EXPECTED_BTC_ANCHOR_COUNT,
    EXPECTED_BTC_SHA256,
    EXPECTED_EVENT_COUNT,
    EXPECTED_EVENT_MARKET_COUNTS,
    EXPECTED_PAID_DELTA_COUNT,
    EXPECTED_PAID_TICKS_SHA256,
    EXPECTED_PAIR_COUNT,
    EXPECTED_REPLAY_SUMMARY_SHA256,
    EXPECTED_ROLE_ANCHOR_STATE_COUNT,
    EXPECTED_SNAPSHOT_COUNT,
    EXPECTED_STRUCTURAL_TICKER_COUNT,
    EXPECTED_TICKER_COUNT,
    IMPLEMENTATION_FINGERPRINT_21N_R,
    STRATEGY_ID,
    validate_21n_r_freeze,
)

FREEZE_PATH = Path(
    "configs/kxbtcd_candidate_e_july10_outcome_blind_binding_implementation_freeze.json"
)
SCHEMA_VERSION = "kxbtcd_candidate_e_july10_outcome_blind_binding_implementation_freeze.v1"
CHECKPOINT_ID = "21N-S-A"
PARENT_CHECKPOINT_COMMIT = "9c58d63e9faab98b486fdcbc374605abd1115d82"
PARENT_RECEIPT_COMMIT = "b6ec6226374f90bae63784aee8cda28b81e7d67b"
IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_july10_outcome_blind_binding.py",
    "src/kxbtcd_candidate_e_july10_outcome_blind_binding_freeze.py",
    "materialize_kxbtcd_candidate_e_july10_outcome_blind_binding.py",
)


class OutcomeBlindBindingFreezeError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise OutcomeBlindBindingFreezeError(message)


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
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()


def build_freeze(repository_root: str | Path = ".") -> dict[str, Any]:
    repo = Path(repository_root)
    parent = validate_21n_r_freeze(repo)
    if parent.get("implementation_fingerprint") != IMPLEMENTATION_FINGERPRINT_21N_R:
        _fail("21N-R implementation fingerprint mismatch")

    hashes: dict[str, str] = {}
    for relative in IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _fail(f"implementation file missing: {relative}")
        hashes[relative] = sha256_file(path)

    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "strategy_id": STRATEGY_ID,
        "parent_21n_r": {
            "checkpoint_commit": PARENT_CHECKPOINT_COMMIT,
            "receipt_commit": PARENT_RECEIPT_COMMIT,
            "simulator_implementation_fingerprint": IMPLEMENTATION_FINGERPRINT_21N_R,
        },
        "implementation_file_sha256s": hashes,
        "frozen_local_source_contract": {
            "btc_materialization_sha256": EXPECTED_BTC_SHA256,
            "paid_predexon_tick_shard_sha256": EXPECTED_PAID_TICKS_SHA256,
            "full_ladder_replay_summary_sha256": EXPECTED_REPLAY_SUMMARY_SHA256,
            "independent_event_count": EXPECTED_EVENT_COUNT,
            "full_ladder_ticker_count": EXPECTED_TICKER_COUNT,
            "event_market_counts": dict(EXPECTED_EVENT_MARKET_COUNTS),
            "structural_ticker_count": EXPECTED_STRUCTURAL_TICKER_COUNT,
            "btc_decision_anchor_count": EXPECTED_BTC_ANCHOR_COUNT,
            "role_anchor_state_count": EXPECTED_ROLE_ANCHOR_STATE_COUNT,
            "paid_delta_count": EXPECTED_PAID_DELTA_COUNT,
            "snapshot_count": EXPECTED_SNAPSHOT_COUNT,
            "pair_count": EXPECTED_PAIR_COUNT,
            "replay_ticker_file_count": EXPECTED_TICKER_COUNT,
            "backfill_ticker_file_count": EXPECTED_TICKER_COUNT,
            "paid_replay_backfill_ticker_sets_must_match_exactly": True,
        },
        "binding_contract": {
            "structural_role_selection": "frozen_numeric_strike_nearest_rank_half_up_over_full_event_ladder",
            "candidate_e_btc_spot_field": "coinbase_current_price",
            "decision_timestamp_field": "decision_time_utc",
            "event_close_timestamp_field": "event_close_time_utc",
            "btc_interpolation_allowed": False,
            "book_interpolation_allowed": False,
            "nearest_book_state_substitution_allowed": False,
            "cross_strike_book_proxy_allowed": False,
            "decision_state_requires_verified_segment": True,
            "runtime_replay_segments_must_equal_frozen_ticker_audit_bounds": True,
            "signal_builder": "21N-R frozen build_signal_candidates",
            "event_selector": "21N-R frozen select_event_signal",
            "scenario_simulator": "21N-R frozen simulate_scenario",
            "thresholds_and_latencies": "inherited_without_change_from_21N-R",
            "materialization_output_is_deterministic": True,
            "nonidentical_existing_output_is_never_overwritten": True,
        },
        "output_firewall": {
            "settlement_label_reader_present": False,
            "realized_pnl_function_present": False,
            "outcome_or_settlement_value_fields_forbidden": True,
            "settlement_fallback_quantity_allowed": True,
            "matched_hold_settlement_quantity_allowed": True,
            "reason_quantities_are_allowed": "position_quantities_only_not_outcome_values",
        },
        "evidence_and_safety": {
            "july10_real_signal_or_path_materialization_run_by_21n_s_a": False,
            "july10_outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "candidate_e_refit": False,
            "model2_used": False,
            "c1_c2_c3_or_protected_reserve_accessed": False,
            "network_requests": 0,
            "new_predexon_purchases": 0,
            "orders_submitted": 0,
            "paper_broker": False,
            "demo_execution": False,
            "real_money_execution": False,
            "four_event_evidence_role": "exploratory_methodology_debug_only",
            "advancement_gate": "none_due_to_four_independent_events",
        },
        "next_checkpoint": {
            "id": "21N-S-B",
            "name": "July 10 Outcome-Blind Strategy Input and Execution-Path Materialization Run",
            "run_only_after_21n_s_a_closeout": True,
            "outcomes_must_remain_closed": True,
            "pnl_must_remain_unrun": True,
            "no_strategy_tuning_from_path_diagnostics": True,
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
        raise OutcomeBlindBindingFreezeError(f"could not read freeze: {exc}") from exc
    if not isinstance(document, dict):
        _fail("freeze root must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        _fail("freeze schema mismatch")
    if document.get("checkpoint_id") != CHECKPOINT_ID:
        _fail("checkpoint mismatch")
    expected = build_freeze(repo)
    if document != expected:
        _fail(
            "implementation freeze mismatch; "
            f"observed={document.get('implementation_fingerprint')}, "
            f"expected={expected.get('implementation_fingerprint')}"
        )
    return document


__all__ = [
    "FREEZE_PATH",
    "SCHEMA_VERSION",
    "CHECKPOINT_ID",
    "IMPLEMENTATION_FILES",
    "OutcomeBlindBindingFreezeError",
    "sha256_file",
    "canonical_fingerprint",
    "build_freeze",
    "validate_freeze",
]
