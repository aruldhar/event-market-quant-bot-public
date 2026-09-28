"""Checkpoint 21N-Z-E-B5-R2: generation-aware read-only reconnect harness state.

This module is deliberately network-free. It owns only connection-generation
identity and binds live transport lifecycle evidence to the already-frozen B4
Coinbase/Kalshi readiness adapters.

Important:
- every connect/reconnect receives a new positive generation;
- a reconnect creates a fresh Coinbase builder / Kalshi cache;
- explicit disconnect blocks immediately, without waiting for stale timers;
- old-generation state remains unable to pass current readiness;
- Kalshi Pong proves transport liveness only and never repairs book state;
- no model, signal, P&L, paper broker, or execution behavior exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .kxbtcd_candidate_e_coinbase_ws_minute_builder import (
    CoinbaseMinuteBuilder,
)
from .kxbtcd_candidate_e_prospective_live_collector import (
    EventLadder,
    KalshiBookCache,
    completed_minute_target,
)
from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_restart_source_readiness import (
    CoinbaseReadinessEvidence,
    KALSHI_WS_CLIENT_PING_INTERVAL_SECONDS,
    KALSHI_WS_PONG_TIMEOUT_SECONDS,
    KalshiReadinessEvidence,
    KalshiTransportLivenessEvidence,
    evaluate_coinbase_readiness,
    evaluate_kalshi_readiness,
    evaluate_kalshi_transport_liveness,
)


EXPECTED_B5_R1_CHECKPOINT = (
    "b455f8f27916d71ff5a7d01340cf53be8e5842b1"
)
EXPECTED_B5_R1_RECEIPT = (
    "4daa3a0e95994f7d687e4d47023d36563b8ca002"
)

# Frozen by candidate_e_production_shaped_runtime.v1 and B4.
KALSHI_CONNECT_PING_INTERVAL_SECONDS = (
    KALSHI_WS_CLIENT_PING_INTERVAL_SECONDS
)
KALSHI_CONNECT_PING_TIMEOUT_SECONDS = (
    KALSHI_WS_PONG_TIMEOUT_SECONDS
)

LIVE_NETWORK_ENABLED_BY_DEFAULT = False
LIVE_GENERATIONS_PER_SOURCE = 2
MIN_DWELL_SECONDS_PER_GENERATION = 5
MAX_DWELL_SECONDS_PER_GENERATION = 30


class B5R2ReconnectHarnessError(RuntimeError):
    pass


def _ns(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise B5R2ReconnectHarnessError(f"{name} must be an integer")
    if value < 0:
        raise B5R2ReconnectHarnessError(f"{name} must be nonnegative")
    return int(value)


def validate_dwell_seconds(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise B5R2ReconnectHarnessError(
            "dwell seconds must be an integer"
        )
    if not (
        MIN_DWELL_SECONDS_PER_GENERATION
        <= value
        <= MAX_DWELL_SECONDS_PER_GENERATION
    ):
        raise B5R2ReconnectHarnessError(
            "dwell seconds outside bounded B5-R2 range"
        )
    return int(value)


@dataclass
class CoinbaseConnectionBinding:
    runtime_session_id: str
    generation: int
    builder: CoinbaseMinuteBuilder
    opened_monotonic_ns: int
    connected: bool = True
    closed_monotonic_ns: int | None = None


@dataclass
class KalshiConnectionBinding:
    runtime_session_id: str
    generation: int
    cache: KalshiBookCache
    opened_monotonic_ns: int
    connected: bool = True
    last_pong_monotonic_ns: int | None = None
    closed_monotonic_ns: int | None = None


class ReconnectGenerationController:
    """Own source connection generations for one runtime process session."""

    def __init__(self, runtime_session_id: str):
        session = str(runtime_session_id).strip()
        if not session:
            raise B5R2ReconnectHarnessError(
                "runtime_session_id must be non-empty"
            )
        self.runtime_session_id = session
        self._coinbase_generation = 0
        self._kalshi_generation = 0
        self.current_coinbase: CoinbaseConnectionBinding | None = None
        self.current_kalshi: KalshiConnectionBinding | None = None

    @property
    def current_coinbase_generation(self) -> int | None:
        if self.current_coinbase is None:
            return None
        return self.current_coinbase.generation

    @property
    def current_kalshi_generation(self) -> int | None:
        if self.current_kalshi is None:
            return None
        return self.current_kalshi.generation

    def open_coinbase(
        self,
        *,
        opened_monotonic_ns: int,
    ) -> CoinbaseConnectionBinding:
        opened = _ns(opened_monotonic_ns, "opened_monotonic_ns")
        if (
            self.current_coinbase is not None
            and self.current_coinbase.connected
        ):
            raise B5R2ReconnectHarnessError(
                "Coinbase connection already open"
            )
        self._coinbase_generation += 1
        binding = CoinbaseConnectionBinding(
            runtime_session_id=self.runtime_session_id,
            generation=self._coinbase_generation,
            builder=CoinbaseMinuteBuilder(),
            opened_monotonic_ns=opened,
        )
        self.current_coinbase = binding
        return binding

    def close_coinbase(
        self,
        *,
        generation: int,
        closed_monotonic_ns: int,
    ) -> None:
        current = self.current_coinbase
        if (
            current is None
            or generation != current.generation
            or not current.connected
        ):
            raise B5R2ReconnectHarnessError(
                "Coinbase close does not match current open generation"
            )
        closed = _ns(closed_monotonic_ns, "closed_monotonic_ns")
        if closed < current.opened_monotonic_ns:
            raise B5R2ReconnectHarnessError(
                "Coinbase close monotonic time precedes open"
            )
        current.connected = False
        current.closed_monotonic_ns = closed

    def open_kalshi(
        self,
        *,
        subscribed_tickers: Sequence[str],
        opened_monotonic_ns: int,
    ) -> KalshiConnectionBinding:
        opened = _ns(opened_monotonic_ns, "opened_monotonic_ns")
        if (
            self.current_kalshi is not None
            and self.current_kalshi.connected
        ):
            raise B5R2ReconnectHarnessError(
                "Kalshi connection already open"
            )
        self._kalshi_generation += 1
        binding = KalshiConnectionBinding(
            runtime_session_id=self.runtime_session_id,
            generation=self._kalshi_generation,
            cache=KalshiBookCache(subscribed_tickers),
            opened_monotonic_ns=opened,
        )
        self.current_kalshi = binding
        return binding

    def record_kalshi_pong(
        self,
        *,
        generation: int,
        pong_monotonic_ns: int,
    ) -> None:
        current = self.current_kalshi
        if (
            current is None
            or generation != current.generation
            or not current.connected
        ):
            raise B5R2ReconnectHarnessError(
                "Pong does not belong to current open Kalshi generation"
            )
        pong = _ns(pong_monotonic_ns, "pong_monotonic_ns")
        if pong < current.opened_monotonic_ns:
            raise B5R2ReconnectHarnessError(
                "Kalshi Pong precedes connection open"
            )
        if (
            current.last_pong_monotonic_ns is not None
            and pong < current.last_pong_monotonic_ns
        ):
            raise B5R2ReconnectHarnessError(
                "Kalshi Pong monotonic time regressed"
            )
        current.last_pong_monotonic_ns = pong

    def close_kalshi(
        self,
        *,
        generation: int,
        closed_monotonic_ns: int,
    ) -> None:
        current = self.current_kalshi
        if (
            current is None
            or generation != current.generation
            or not current.connected
        ):
            raise B5R2ReconnectHarnessError(
                "Kalshi close does not match current open generation"
            )
        closed = _ns(closed_monotonic_ns, "closed_monotonic_ns")
        if closed < current.opened_monotonic_ns:
            raise B5R2ReconnectHarnessError(
                "Kalshi close monotonic time precedes open"
            )
        current.connected = False
        current.closed_monotonic_ns = closed

    def evaluate_coinbase(
        self,
        *,
        binding: CoinbaseConnectionBinding,
        decision_epoch_s: int,
        now_monotonic_ns: int,
    ) -> CoinbaseReadinessEvidence:
        current = self.current_coinbase
        target_start, target_end = completed_minute_target(
            int(decision_epoch_s)
        )

        if current is None:
            return CoinbaseReadinessEvidence(
                status=GateStatus.BLOCKED,
                reason="COINBASE_WEBSOCKET_NOT_CONNECTED",
                target_minute_start_s=target_start,
                target_minute_end_s=target_end,
                builder_status="NO_CURRENT_CONNECTION",
                close_trade_id=None,
                connection_generation=None,
            )

        # Explicit transport loss blocks immediately. This is stricter than
        # waiting up to the 3-second application heartbeat stale threshold.
        if (
            binding.generation == current.generation
            and not current.connected
        ):
            return CoinbaseReadinessEvidence(
                status=GateStatus.BLOCKED,
                reason="COINBASE_WEBSOCKET_NOT_CONNECTED",
                target_minute_start_s=target_start,
                target_minute_end_s=target_end,
                builder_status="DISCONNECTED",
                close_trade_id=None,
                connection_generation=current.generation,
            )

        return evaluate_coinbase_readiness(
            builder=binding.builder,
            runtime_session_id=self.runtime_session_id,
            builder_runtime_session_id=binding.runtime_session_id,
            current_connection_generation=current.generation,
            builder_connection_generation=binding.generation,
            decision_epoch_s=int(decision_epoch_s),
            now_monotonic_ns=_ns(
                now_monotonic_ns,
                "now_monotonic_ns",
            ),
        )

    def current_kalshi_transport(
        self,
        *,
        now_monotonic_ns: int,
    ) -> KalshiTransportLivenessEvidence:
        current = self.current_kalshi
        if current is None:
            return evaluate_kalshi_transport_liveness(
                runtime_session_id=self.runtime_session_id,
                connection_generation=None,
                connected=False,
                last_pong_monotonic_ns=None,
                now_monotonic_ns=_ns(
                    now_monotonic_ns,
                    "now_monotonic_ns",
                ),
            )
        return evaluate_kalshi_transport_liveness(
            runtime_session_id=self.runtime_session_id,
            connection_generation=current.generation,
            connected=current.connected,
            last_pong_monotonic_ns=current.last_pong_monotonic_ns,
            now_monotonic_ns=_ns(
                now_monotonic_ns,
                "now_monotonic_ns",
            ),
        )

    def evaluate_kalshi(
        self,
        *,
        binding: KalshiConnectionBinding,
        current_event: EventLadder,
        discovery_runtime_session_id: str,
        now_ms: int,
        now_monotonic_ns: int,
    ) -> KalshiReadinessEvidence:
        transport = self.current_kalshi_transport(
            now_monotonic_ns=now_monotonic_ns
        )
        return evaluate_kalshi_readiness(
            cache=binding.cache,
            current_event=current_event,
            runtime_session_id=self.runtime_session_id,
            discovery_runtime_session_id=(
                discovery_runtime_session_id
            ),
            cache_runtime_session_id=binding.runtime_session_id,
            cache_connection_generation=binding.generation,
            transport_liveness=transport,
            now_ms=int(now_ms),
        )
