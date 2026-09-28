from pathlib import Path
import json

import pytest

from src.kxbtcd_candidate_e_execution_archive_predeclaration import (
    ARCHIVE_ID,
    EXPECTED_ALLOWLIST_FINGERPRINT,
    EXPECTED_ARCHIVE_FINGERPRINT,
    EXPECTED_EVENTS,
    EXPECTED_MARKETS,
    EXPECTED_ROWS,
    canonical_fingerprint,
    validate_predeclaration,
)

CONFIG = Path("configs/kxbtcd_candidate_e_execution_archive_v1.json")

def test_frozen_counts():
    assert EXPECTED_EVENTS == 4070
    assert EXPECTED_MARKETS == 20236
    assert EXPECTED_ROWS == 118862

def test_allowlist_fingerprint_constant():
    assert EXPECTED_ALLOWLIST_FINGERPRINT == "85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1"

def test_archive_id_and_fingerprint():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert doc["archive_id"] == ARCHIVE_ID
    assert doc["archive_predeclaration_fingerprint"] == EXPECTED_ARCHIVE_FINGERPRINT
    payload = {k: v for k, v in doc.items() if k != "archive_predeclaration_fingerprint"}
    assert canonical_fingerprint(payload) == EXPECTED_ARCHIVE_FINGERPRINT

def test_strategy_rules_not_modified():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert doc["parent_strategy"]["strategy_rules_modified_by_this_contract"] is False
    assert doc["collection_scope"]["strategy_pnl_scoring_authorized"] is False
    assert doc["collection_scope"]["model_refit_authorized"] is False

def test_reserve_hard_denied():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    reserve = doc["reserve_policy"]
    assert reserve["reserve_access_allowed"] is False
    assert reserve["reserve_market_discovery_allowed"] is False
    assert reserve["archive_may_expand_to_reserve"] is False

def test_full_lifecycle_one_minute_archive():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    scope = doc["collection_scope"]
    assert scope["market_time_window"] == "full tradable lifecycle from market open_time through close_time"
    assert scope["candlestick_period_minutes"] == 1
    assert scope["collect_one_minute_candlesticks"] is True
    assert scope["collect_trades"] is True

def test_fee_resolution_includes_event_overrides():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    fees = doc["fee_resolution_policy"]
    assert fees["series_schedule_required"] is True
    assert fees["event_override_schedule_required"] is True
    assert fees["event_override_precedence"] is True

def test_future_strategy_reuse_is_explicit():
    doc = json.loads(CONFIG.read_text(encoding="utf-8"))
    reuse = doc["future_strategy_reuse"]
    assert reuse["archive_may_be_reused_by_later_separately_versioned_strategies"] is True
    assert reuse["recollection_not_required_if_future_strategy_inputs_are_within_archive_scope"] is True

def test_network_free_validation_without_allowlist_recompute():
    assert validate_predeclaration(verify_allowlist=False) == EXPECTED_ARCHIVE_FINGERPRINT
