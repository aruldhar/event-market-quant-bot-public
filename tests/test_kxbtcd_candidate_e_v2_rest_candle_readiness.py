from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_prospective_live_collector import CoinbaseMinuteClose
from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus
from src.kxbtcd_candidate_e_v2_rest_candle_readiness import (
    V2RestCandleReadinessError,
    bind_v2_rest_candle,
    evaluate_v2_rest_candle,
)


SESSION = "v2-rest-test"


def candle(*, start=120, available_ns=5):
    return CoinbaseMinuteClose(minute_start_s=start, minute_end_s=start + 60,
        close_price=Decimal("80000.25"), available_monotonic_ns=available_ns,
        raw_received_utc="2026-09-08T00:03:00Z")


def test_current_exact_rest_candle_passes_without_a_websocket_generation():
    evidence = evaluate_v2_rest_candle(
        candle=bind_v2_rest_candle(runtime_session_id=SESSION, minute=candle()),
        runtime_session_id=SESSION, decision_epoch_s=180, now_monotonic_ns=5)
    assert evidence.status == GateStatus.PASS
    assert evidence.close_price == Decimal("80000.25")


def test_stale_or_missing_rest_candle_blocks_v2_input_readiness():
    missing = evaluate_v2_rest_candle(candle=None, runtime_session_id=SESSION,
        decision_epoch_s=180, now_monotonic_ns=5)
    stale = evaluate_v2_rest_candle(
        candle=bind_v2_rest_candle(runtime_session_id=SESSION, minute=candle(start=60)),
        runtime_session_id=SESSION, decision_epoch_s=180, now_monotonic_ns=5)
    assert missing.status == GateStatus.BLOCKED
    assert stale.status == GateStatus.BLOCKED


def test_mismatched_session_or_future_receipt_fails_closed():
    bound = bind_v2_rest_candle(runtime_session_id=SESSION, minute=candle(available_ns=6))
    mismatch = evaluate_v2_rest_candle(candle=bound, runtime_session_id="other",
        decision_epoch_s=180, now_monotonic_ns=6)
    future = evaluate_v2_rest_candle(candle=bound, runtime_session_id=SESSION,
        decision_epoch_s=180, now_monotonic_ns=5)
    assert mismatch.status == GateStatus.FATAL
    assert future.status == GateStatus.FATAL


def test_binding_rejects_malformed_minute():
    with pytest.raises(V2RestCandleReadinessError, match="aligned"):
        bind_v2_rest_candle(runtime_session_id=SESSION, minute=candle(start=121))
