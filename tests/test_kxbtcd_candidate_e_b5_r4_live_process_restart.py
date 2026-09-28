from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_b5_r4_live_process_restart import (
    CANONICAL_PROSPECTIVE_DB_CREATED,
    COHORT_ARMED,
    DEFAULT_SOURCE_WAIT_SECONDS,
    LIVE_NETWORK_ENABLED_BY_DEFAULT,
    ORDERS_SUBMITTED,
    PRODUCTION_WRITES,
    SIGNALS_COMPUTED,
    B5R4ValidationError,
    classify_manual_pong_attempt,
    manual_ping_payload,
    scan_paths_for_secret_markers,
    validate_final_live_summary,
    validate_source_wait_seconds,
    write_json_atomic,
    read_json_object,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus
from src.kxbtcd_candidate_e_restart_source_readiness import (
    KALSHI_WS_MAX_PONG_AGE_NS,
    evaluate_kalshi_transport_liveness,
)


def valid_summary():
    return {
        "schema_version":
            "candidate_e_b5_r4_live_process_restart_validation.v1",
        "design_fingerprint":
            "17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9",
        "process_1_pid": 101,
        "process_2_pid": 202,
        "process_1_runtime_session_id": "p1",
        "process_2_runtime_session_id": "p2",
        "process_1_prior_shutdown_status": "UNCLEAN_DETECTED",
        "process_2_initial_state": "BLOCKED_COINBASE",
        "process_2_final_state": "READY_READ_ONLY",
        "process_2_pending_examined": 1,
        "process_2_verified": 1,
        "process_2_pending_after": 0,
        "process_2_prior_signal_reusable": False,
        "process_gap_canonical_backfill_allowed": False,
        "execution_mode_disabled": True,
        "process_1_coinbase_reason": "PASS",
        "process_1_kalshi_reason": "PASS",
        "process_2_coinbase_reason": "PASS",
        "process_2_kalshi_reason": "PASS",
        "process_2_coinbase_runtime_session_bound": True,
        "process_2_kalshi_runtime_session_bound": True,
        "raw_secret_marker_hits": 0,
        "canonical_prospective_db_created": False,
        "cohort_armed": False,
        "signals_computed": 0,
        "orders": 0,
        "production_writes": 0,
    }


def test_default_is_zero_network_and_zero_execution():
    assert LIVE_NETWORK_ENABLED_BY_DEFAULT is False
    assert CANONICAL_PROSPECTIVE_DB_CREATED is False
    assert COHORT_ARMED is False
    assert SIGNALS_COMPUTED == 0
    assert ORDERS_SUBMITTED == 0
    assert PRODUCTION_WRITES == 0


@pytest.mark.parametrize("value", [70, 90, 120, 180])
def test_source_wait_accepts_bounded_values(value):
    assert validate_source_wait_seconds(value) == value


@pytest.mark.parametrize("value", [0, 69, 181, 999, True])
def test_source_wait_rejects_out_of_bounds(value):
    with pytest.raises(B5R4ValidationError):
        validate_source_wait_seconds(value)


def test_default_source_wait_is_inside_contract():
    assert validate_source_wait_seconds(
        DEFAULT_SOURCE_WAIT_SECONDS
    ) == DEFAULT_SOURCE_WAIT_SECONDS


def test_secret_scan_zero_for_safe_market_data(tmp_path):
    p = tmp_path / "raw.jsonl"
    p.write_text(
        '{"raw_text":"orderbook_snapshot","market":"KXBTCD"}\n',
        encoding="utf-8",
    )
    result = scan_paths_for_secret_markers([p])
    assert result.files_scanned == 1
    assert result.total_hits == 0


@pytest.mark.parametrize(
    "payload",
    [
        "Authorization: Bearer abc",
        "KALSHI-ACCESS-KEY: abc",
        "KALSHI-ACCESS-SIGNATURE: abc",
        "-----BEGIN " + "PRIVATE KEY-----",
    ],
)
def test_secret_scan_detects_high_confidence_markers(tmp_path, payload):
    p = tmp_path / "artifact.txt"
    p.write_text(payload, encoding="utf-8")
    assert scan_paths_for_secret_markers([p]).total_hits >= 1


def test_atomic_json_write_refuses_existing_file(tmp_path):
    p = tmp_path / "x.json"
    write_json_atomic(p, {"a": 1})
    assert read_json_object(p) == {"a": 1}
    with pytest.raises(B5R4ValidationError):
        write_json_atomic(p, {"a": 2})


def test_valid_final_live_summary_passes():
    validate_final_live_summary(valid_summary())


def test_same_os_process_id_fails():
    x = valid_summary()
    x["process_2_pid"] = x["process_1_pid"]
    with pytest.raises(B5R4ValidationError):
        validate_final_live_summary(x)


def test_same_runtime_session_fails():
    x = valid_summary()
    x["process_2_runtime_session_id"] = (
        x["process_1_runtime_session_id"]
    )
    with pytest.raises(B5R4ValidationError):
        validate_final_live_summary(x)


def test_missing_pending_reconciliation_fails():
    x = valid_summary()
    x["process_2_pending_examined"] = 0
    with pytest.raises(B5R4ValidationError):
        validate_final_live_summary(x)


def test_successor_must_start_blocked():
    x = valid_summary()
    x["process_2_initial_state"] = "READY_READ_ONLY"
    with pytest.raises(B5R4ValidationError):
        validate_final_live_summary(x)


def test_successor_must_finish_ready():
    x = valid_summary()
    x["process_2_final_state"] = "BLOCKED_KALSHI"
    with pytest.raises(B5R4ValidationError):
        validate_final_live_summary(x)


def test_secret_hit_fails_final_summary():
    x = valid_summary()
    x["raw_secret_marker_hits"] = 1
    with pytest.raises(B5R4ValidationError):
        validate_final_live_summary(x)


def test_execution_or_order_activity_fails():
    for key, value in (
        ("execution_mode_disabled", False),
        ("signals_computed", 1),
        ("orders", 1),
        ("production_writes", 1),
    ):
        x = valid_summary()
        x[key] = value
        with pytest.raises(B5R4ValidationError):
            validate_final_live_summary(x)
def test_manual_ping_payload_is_unique_per_attempt():
    first = manual_ping_payload("session-a", 1)
    second = manual_ping_payload("session-a", 2)
    assert first != second
    assert first.startswith(b"b5r4-session-a-")
    assert second.startswith(b"b5r4-session-a-")


def test_successful_manual_pong_is_the_only_result_that_refreshes():
    decision = classify_manual_pong_attempt(
        pong_received=True,
        last_successful_pong_monotonic_ns=1_000,
        observed_monotonic_ns=2_000,
    )
    assert decision.record_successful_pong is True
    assert decision.reason == "PONG_RECEIVED_RECORD_CURRENT_TIME"


def test_missed_manual_pong_with_recent_prior_proof_does_not_abort_or_refresh():
    prior = 1_000_000_000
    now = prior + KALSHI_WS_MAX_PONG_AGE_NS

    decision = classify_manual_pong_attempt(
        pong_received=False,
        last_successful_pong_monotonic_ns=prior,
        observed_monotonic_ns=now,
    )
    assert decision.record_successful_pong is False
    assert decision.reason == (
        "PONG_MISSED_PRIOR_PROOF_WITHIN_FROZEN_AGE"
    )

    evidence = evaluate_kalshi_transport_liveness(
        runtime_session_id="session-a",
        connection_generation=1,
        connected=True,
        last_pong_monotonic_ns=prior,
        now_monotonic_ns=now,
    )
    assert evidence.status == GateStatus.PASS
    assert evidence.reason == "PASS"


def test_missed_manual_pong_becomes_blocked_only_after_frozen_age_expires():
    prior = 1_000_000_000
    now = prior + KALSHI_WS_MAX_PONG_AGE_NS + 1

    decision = classify_manual_pong_attempt(
        pong_received=False,
        last_successful_pong_monotonic_ns=prior,
        observed_monotonic_ns=now,
    )
    assert decision.record_successful_pong is False
    assert decision.reason == "PONG_MISSED_PRIOR_PROOF_STALE"

    evidence = evaluate_kalshi_transport_liveness(
        runtime_session_id="session-a",
        connection_generation=1,
        connected=True,
        last_pong_monotonic_ns=prior,
        now_monotonic_ns=now,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_PONG_STALE"


def test_missed_first_manual_pong_never_fabricates_liveness():
    decision = classify_manual_pong_attempt(
        pong_received=False,
        last_successful_pong_monotonic_ns=None,
        observed_monotonic_ns=5_000,
    )
    assert decision.record_successful_pong is False
    assert decision.reason == "PONG_MISSED_NO_PRIOR_PROOF"

    evidence = evaluate_kalshi_transport_liveness(
        runtime_session_id="session-a",
        connection_generation=1,
        connected=True,
        last_pong_monotonic_ns=None,
        now_monotonic_ns=5_000,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_CURRENT_CONNECTION_PONG_NOT_PROVEN"
