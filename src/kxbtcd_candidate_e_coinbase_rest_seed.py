"""Checkpoint 21N-Z-F Coinbase startup/reconnect REST-candle seed.

Frozen architecture:
- normal live state comes from Coinbase BTC-USD matches + heartbeat;
- stream gaps are repaired from REST trades;
- startup/reconnect may seed ONLY the exact required completed UTC minute
  from one 60-second Coinbase REST candle.

The candle seed never bypasses bad WS continuity.  It is considered only when
the existing current-generation builder has already proven:
- stream seeded;
- sequence healthy;
- no unresolved recovery;
- fresh heartbeat beyond the minute end;

and its sole remaining reason for blocking is NO_TRADES_IN_MINUTE.

No network access occurs in this module.
"""
from __future__ import annotations

from dataclasses import dataclass

from .kxbtcd_candidate_e_prospective_live_collector import (
    CoinbaseMinuteClose,
)
from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_restart_source_readiness import (
    CoinbaseReadinessEvidence,
)


class CoinbaseRestSeedError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoundCoinbaseRestCandleSeed:
    runtime_session_id: str
    connection_generation: int
    minute: CoinbaseMinuteClose


def bind_rest_candle_seed(
    *,
    runtime_session_id: str,
    connection_generation: int,
    minute: CoinbaseMinuteClose,
) -> BoundCoinbaseRestCandleSeed:
    session = str(runtime_session_id).strip()

    if not session:
        raise CoinbaseRestSeedError(
            "runtime_session_id must be non-empty"
        )

    if (
        isinstance(connection_generation, bool)
        or not isinstance(connection_generation, int)
        or connection_generation <= 0
    ):
        raise CoinbaseRestSeedError(
            "connection_generation must be positive integer"
        )

    if not isinstance(minute, CoinbaseMinuteClose):
        raise CoinbaseRestSeedError(
            "minute must be CoinbaseMinuteClose"
        )

    if minute.minute_end_s != minute.minute_start_s + 60:
        raise CoinbaseRestSeedError(
            "REST candle seed must cover exactly 60 seconds"
        )

    if minute.minute_start_s % 60 != 0:
        raise CoinbaseRestSeedError(
            "REST candle seed must be UTC-minute aligned"
        )

    return BoundCoinbaseRestCandleSeed(
        runtime_session_id=session,
        connection_generation=connection_generation,
        minute=minute,
    )


def evaluate_coinbase_with_rest_seed(
    *,
    base_evidence: CoinbaseReadinessEvidence,
    seed: BoundCoinbaseRestCandleSeed | None,
    runtime_session_id: str,
    current_connection_generation: int | None,
    now_monotonic_ns: int,
) -> CoinbaseReadinessEvidence:
    """Apply the narrow frozen startup/reconnect seed exception.

    The existing WS builder remains authoritative whenever it can produce the
    exact completed minute itself.

    A REST seed cannot override any failure except NO_TRADES_IN_MINUTE.
    """

    if base_evidence.status == GateStatus.PASS:
        return base_evidence

    if base_evidence.builder_status != "NO_TRADES_IN_MINUTE":
        return base_evidence

    if seed is None:
        return base_evidence

    session = str(runtime_session_id).strip()

    if (
        not session
        or seed.runtime_session_id != session
    ):
        return base_evidence

    if (
        current_connection_generation is None
        or isinstance(
            current_connection_generation,
            bool,
        )
        or not isinstance(
            current_connection_generation,
            int,
        )
        or current_connection_generation <= 0
        or seed.connection_generation
        != current_connection_generation
    ):
        return base_evidence

    minute = seed.minute

    if (
        minute.minute_start_s
        != base_evidence.target_minute_start_s
        or minute.minute_end_s
        != base_evidence.target_minute_end_s
    ):
        return base_evidence

    now_ns = int(now_monotonic_ns)

    if (
        minute.available_monotonic_ns < 0
        or now_ns < 0
        or minute.available_monotonic_ns > now_ns
    ):
        return CoinbaseReadinessEvidence(
            status=GateStatus.FATAL,
            reason="COINBASE_REST_SEED_MONOTONIC_INVARIANT_FAILURE",
            target_minute_start_s=(
                base_evidence.target_minute_start_s
            ),
            target_minute_end_s=(
                base_evidence.target_minute_end_s
            ),
            builder_status="REST_CANDLE_SEED_ERROR",
            close_trade_id=None,
            connection_generation=(
                current_connection_generation
            ),
        )

    return CoinbaseReadinessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        target_minute_start_s=(
            base_evidence.target_minute_start_s
        ),
        target_minute_end_s=(
            base_evidence.target_minute_end_s
        ),
        builder_status="REST_CANDLE_SEED",
        # A Coinbase candle does not expose the identity of its closing trade.
        # Do not fabricate one.
        close_trade_id=None,
        connection_generation=(
            current_connection_generation
        ),
    )
