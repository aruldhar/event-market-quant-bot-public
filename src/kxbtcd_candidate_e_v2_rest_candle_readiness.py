"""Independent, exact-minute Coinbase REST evidence for frozen V2 inputs.

This deliberately has no dependency on a Coinbase WebSocket generation.  V2
uses the completed one-minute candle, while the WebSocket trade archive is a
separate diagnostic/research sidecar.
"""
from __future__ import annotations

from dataclasses import dataclass

from .kxbtcd_candidate_e_prospective_live_collector import (
    CoinbaseMinuteClose,
    completed_minute_target,
)
from .kxbtcd_candidate_e_restart_gate_state_machine import GateStatus


class V2RestCandleReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class V2BoundRestCandle:
    runtime_session_id: str
    minute: CoinbaseMinuteClose


@dataclass(frozen=True)
class V2RestCandleEvidence:
    status: GateStatus
    reason: str
    target_minute_start_s: int
    target_minute_end_s: int
    close_price: object | None
    available_monotonic_ns: int | None


def bind_v2_rest_candle(*, runtime_session_id: str,
                        minute: CoinbaseMinuteClose) -> V2BoundRestCandle:
    session = str(runtime_session_id).strip()
    if not session:
        raise V2RestCandleReadinessError("runtime_session_id must be non-empty")
    if not isinstance(minute, CoinbaseMinuteClose):
        raise V2RestCandleReadinessError("minute must be CoinbaseMinuteClose")
    if minute.minute_start_s % 60 != 0 or minute.minute_end_s != minute.minute_start_s + 60:
        raise V2RestCandleReadinessError("REST candle must cover one aligned minute")
    if minute.available_monotonic_ns < 0:
        raise V2RestCandleReadinessError("REST candle monotonic receipt must be nonnegative")
    return V2BoundRestCandle(runtime_session_id=session, minute=minute)


def evaluate_v2_rest_candle(*, candle: V2BoundRestCandle | None,
                            runtime_session_id: str, decision_epoch_s: int,
                            now_monotonic_ns: int) -> V2RestCandleEvidence:
    target_start, target_end = completed_minute_target(int(decision_epoch_s))
    if candle is None:
        return V2RestCandleEvidence(GateStatus.BLOCKED, "V2_REST_CANDLE_MISSING",
            target_start, target_end, None, None)
    if candle.runtime_session_id != str(runtime_session_id).strip():
        return V2RestCandleEvidence(GateStatus.FATAL, "V2_REST_CANDLE_SESSION_MISMATCH",
            target_start, target_end, None, None)
    minute = candle.minute
    if minute.available_monotonic_ns > int(now_monotonic_ns):
        return V2RestCandleEvidence(GateStatus.FATAL, "V2_REST_CANDLE_MONOTONIC_INVARIANT_FAILURE",
            target_start, target_end, None, None)
    if minute.minute_start_s != target_start or minute.minute_end_s != target_end:
        return V2RestCandleEvidence(GateStatus.BLOCKED, "V2_REST_CANDLE_NOT_CURRENT",
            target_start, target_end, minute.close_price, minute.available_monotonic_ns)
    return V2RestCandleEvidence(GateStatus.PASS, "PASS", target_start, target_end,
        minute.close_price, minute.available_monotonic_ns)
