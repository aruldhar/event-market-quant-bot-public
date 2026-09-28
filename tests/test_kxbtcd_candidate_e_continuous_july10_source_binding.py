from __future__ import annotations

from copy import deepcopy

import pytest

from src.kxbtcd_candidate_e_continuous_july10_source_binding import (
    ContinuousSourceBindingError,
    EXPECTED_BINDING_FINGERPRINT,
    EXPECTED_BTC_SHA256,
    binding_definition,
    canonical_fingerprint,
    validate_binding,
)


def test_exact_binding_fingerprint():
    payload = binding_definition()
    assert payload["source_binding_fingerprint"] == EXPECTED_BINDING_FINGERPRINT
    assert canonical_fingerprint(payload) == EXPECTED_BINDING_FINGERPRINT


def test_recovery_keeps_failed_manifest_honest():
    btc = binding_definition()["continuous_btc_materialization"]
    assert btc["collection_manifest_status"] == "failed"
    assert btc["runtime_observed_collector_completed"] is True
    assert btc["runtime_observed_row_count"] == 216
    assert btc["runtime_observed_sha256"] == EXPECTED_BTC_SHA256


def test_recovery_performs_no_coinbase_recollection():
    recovery = binding_definition()["recovery_policy"]
    safety = binding_definition()["safety"]
    assert recovery["coinbase_recollection_performed"] is False
    assert recovery["failed_manifest_rewritten_as_completed"] is False
    assert recovery["derived_artifact_reused"] is True
    assert safety["coinbase_recollection_requests"] == 0


def test_mutated_binding_rejected_even_if_refingerprinted():
    payload = binding_definition()
    changed = deepcopy(payload)
    changed["continuous_btc_materialization"]["row_count"] = 215
    changed["source_binding_fingerprint"] = canonical_fingerprint(changed)
    with pytest.raises(ContinuousSourceBindingError):
        validate_binding(".", changed)


def test_safety_firewall():
    safety = binding_definition()["safety"]
    assert safety["outcomes_accessed"] is False
    assert safety["strategy_pnl_calculated"] is False
    assert safety["candidate_e_refit"] is False
    assert safety["continuous_predexon_strategy_paths_run"] is False
    assert safety["orders_placed"] == 0
