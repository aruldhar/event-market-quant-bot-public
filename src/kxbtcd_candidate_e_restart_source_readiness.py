"""Checkpoint 21N-Z-E-B4: authoritative current-source readiness adapters.

This module wires already-accepted read-only Coinbase/Kalshi runtime state plus
Linux chrony/boot identity into the frozen Z-E-B3 restart gate state machine.

B4 does NOT:
- arm the prospective cohort;
- create the canonical prospective database;
- compute Candidate-E probabilities or signals;
- place paper/demo/real orders;
- restore source freshness from an older runtime session or connection.

The adapters are pure/read-only with respect to market state. A production
clock helper may invoke the local ``chronyc tracking`` command; it performs no
network request itself.

B4-R1 binds source readiness to both the current runtime session and the
current WebSocket connection generation. Kalshi order-book correctness and
WebSocket transport liveness are deliberately separate gates: protocol
ping/pong proves the connection is alive; it does not refresh book data or
repair sequence state.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import platform
import re
import subprocess
from typing import Any
from uuid import UUID

from src.kxbtcd_candidate_e_coinbase_ws_minute_builder import (
    CoinbaseMinuteBuilder,
    CoinbaseMinuteBuilderError,
)
from src.kxbtcd_candidate_e_prospective_live_collector import (
    EventLadder,
    KalshiBookCache,
    completed_minute_target,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    ClockHealth,
    CohortStatus,
    GateStatus,
    RestartGateSnapshot,
)


PRODUCTION_BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
CHRONYC_COMMAND = ("chronyc", "tracking")

# Frozen in candidate_e_production_shaped_runtime.v1. The client sends a
# WebSocket protocol Ping every 15 seconds and allows 5 seconds for the
# corresponding Pong. A last successful client-Ping/Pong round trip older
# than one full interval plus timeout cannot prove the current connection is
# alive. This is transport liveness only; it does not make an old book fresh.
KALSHI_WS_CLIENT_PING_INTERVAL_SECONDS = 15
KALSHI_WS_PONG_TIMEOUT_SECONDS = 5
KALSHI_WS_MAX_PONG_AGE_NS = (
    (KALSHI_WS_CLIENT_PING_INTERVAL_SECONDS + KALSHI_WS_PONG_TIMEOUT_SECONDS)
    * 1_000_000_000
)

_SYNCHRONIZED_LEAP_STATES = frozenset({
    "Normal",
    "Insert second",
    "Delete second",
})

_SYSTEM_TIME_RE = re.compile(
    r"^\s*System time\s*:\s*"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"seconds\s+(slow|fast)\s+of\s+NTP time\s*$",
    re.IGNORECASE,
)

_LEAP_STATUS_RE = re.compile(
    r"^\s*Leap status\s*:\s*(.*?)\s*$",
    re.IGNORECASE,
)


class RestartSourceReadinessError(RuntimeError):
    pass


@dataclass(frozen=True)
class BootIdentityEvidence:
    status: GateStatus
    boot_id: str | None
    source: str
    validation_only: bool
    reason: str


@dataclass(frozen=True)
class ChronyTrackingEvidence:
    status: GateStatus
    signed_system_time_offset_ms: float | None
    absolute_system_time_offset_ms: float | None
    leap_status: str | None
    reason: str


@dataclass(frozen=True)
class CoinbaseReadinessEvidence:
    status: GateStatus
    reason: str
    target_minute_start_s: int
    target_minute_end_s: int
    builder_status: str
    close_trade_id: int | None
    connection_generation: int | None


@dataclass(frozen=True)
class KalshiTransportLivenessEvidence:
    status: GateStatus
    reason: str
    runtime_session_id: str
    connection_generation: int | None
    last_pong_monotonic_ns: int | None
    evaluated_monotonic_ns: int
    pong_age_ns: int | None


@dataclass(frozen=True)
class KalshiReadinessEvidence:
    status: GateStatus
    reason: str
    event_ticker: str
    expected_tickers: tuple[str, ...]
    generation: int
    last_seq: int | None
    subscription_sid: int | None
    connection_generation: int | None
    transport_reason: str


def _valid_uuid_text(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise RestartSourceReadinessError("boot ID is blank")
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise RestartSourceReadinessError(
            "boot ID must be UUID-compatible"
        ) from exc
    return str(parsed)


def resolve_boot_identity(
    *,
    validation_mode: bool,
    injected_synthetic_boot_id: str | None = None,
    platform_system: str | None = None,
    production_boot_id_path: str | Path = PRODUCTION_BOOT_ID_PATH,
) -> BootIdentityEvidence:
    """Resolve current boot identity without silently crossing environments.

    Windows development tests must use an explicitly injected synthetic UUID.
    Production mode requires Linux and the kernel boot-id file.
    """
    system_name = (
        str(platform_system)
        if platform_system is not None
        else platform.system()
    )

    if validation_mode:
        if injected_synthetic_boot_id is None:
            return BootIdentityEvidence(
                status=GateStatus.BLOCKED,
                boot_id=None,
                source="synthetic_validation",
                validation_only=True,
                reason="SYNTHETIC_BOOT_ID_REQUIRED",
            )
        try:
            boot_id = _valid_uuid_text(injected_synthetic_boot_id)
        except RestartSourceReadinessError:
            return BootIdentityEvidence(
                status=GateStatus.BLOCKED,
                boot_id=None,
                source="synthetic_validation",
                validation_only=True,
                reason="SYNTHETIC_BOOT_ID_INVALID",
            )
        return BootIdentityEvidence(
            status=GateStatus.PASS,
            boot_id=boot_id,
            source="synthetic_validation",
            validation_only=True,
            reason="PASS",
        )

    if injected_synthetic_boot_id is not None:
        return BootIdentityEvidence(
            status=GateStatus.FATAL,
            boot_id=None,
            source="production",
            validation_only=False,
            reason="SYNTHETIC_BOOT_ID_FORBIDDEN_IN_PRODUCTION",
        )

    if system_name != "Linux":
        return BootIdentityEvidence(
            status=GateStatus.BLOCKED,
            boot_id=None,
            source="linux_kernel_boot_id",
            validation_only=False,
            reason="PRODUCTION_REQUIRES_LINUX_BOOT_ID",
        )

    path = Path(production_boot_id_path)
    try:
        raw = path.read_text(encoding="utf-8")
        boot_id = _valid_uuid_text(raw)
    except (OSError, RestartSourceReadinessError):
        return BootIdentityEvidence(
            status=GateStatus.BLOCKED,
            boot_id=None,
            source="linux_kernel_boot_id",
            validation_only=False,
            reason="BOOT_ID_UNAVAILABLE_OR_INVALID",
        )

    return BootIdentityEvidence(
        status=GateStatus.PASS,
        boot_id=boot_id,
        source="linux_kernel_boot_id",
        validation_only=False,
        reason="PASS",
    )


def parse_chronyc_tracking(
    output: str,
) -> ChronyTrackingEvidence:
    """Parse source-grounded chronyc tracking output fail-closed."""
    system_seconds: float | None = None
    system_direction: str | None = None
    leap_status: str | None = None

    for line in str(output).splitlines():
        match = _SYSTEM_TIME_RE.match(line)
        if match is not None:
            try:
                system_seconds = float(match.group(1))
            except ValueError:
                system_seconds = None
            system_direction = match.group(2).lower()
            continue

        match = _LEAP_STATUS_RE.match(line)
        if match is not None:
            leap_status = match.group(1).strip()

    if system_seconds is None or system_direction is None:
        return ChronyTrackingEvidence(
            status=GateStatus.BLOCKED,
            signed_system_time_offset_ms=None,
            absolute_system_time_offset_ms=None,
            leap_status=leap_status,
            reason="CHRONY_SYSTEM_TIME_UNKNOWN",
        )

    if leap_status not in _SYNCHRONIZED_LEAP_STATES:
        return ChronyTrackingEvidence(
            status=GateStatus.BLOCKED,
            signed_system_time_offset_ms=None,
            absolute_system_time_offset_ms=None,
            leap_status=leap_status,
            reason="CHRONY_NOT_SYNCHRONIZED",
        )

    magnitude_ms = abs(system_seconds) * 1000.0
    signed_ms = (
        -magnitude_ms
        if system_direction == "slow"
        else magnitude_ms
    )

    health = ClockHealth.from_signed_offset_ms(signed_ms)

    return ChronyTrackingEvidence(
        status=health.gate_status,
        signed_system_time_offset_ms=signed_ms,
        absolute_system_time_offset_ms=magnitude_ms,
        leap_status=leap_status,
        reason=(
            "PASS"
            if health.gate_status == GateStatus.PASS
            else "CLOCK_OFFSET_EXCEEDS_FROZEN_LIMIT"
        ),
    )


def read_production_chrony_tracking(
    *,
    platform_system: str | None = None,
    timeout_seconds: float = 2.0,
) -> ChronyTrackingEvidence:
    """Read local Linux chrony state.

    The command talks to the local chronyd control interface. B4 does not use
    this helper on Windows validation runs.
    """
    system_name = (
        str(platform_system)
        if platform_system is not None
        else platform.system()
    )
    if system_name != "Linux":
        return ChronyTrackingEvidence(
            status=GateStatus.BLOCKED,
            signed_system_time_offset_ms=None,
            absolute_system_time_offset_ms=None,
            leap_status=None,
            reason="PRODUCTION_CHRONY_REQUIRES_LINUX",
        )

    try:
        result = subprocess.run(
            list(CHRONYC_COMMAND),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=float(timeout_seconds),
        )
    except (OSError, subprocess.TimeoutExpired):
        return ChronyTrackingEvidence(
            status=GateStatus.BLOCKED,
            signed_system_time_offset_ms=None,
            absolute_system_time_offset_ms=None,
            leap_status=None,
            reason="CHRONYC_UNAVAILABLE",
        )

    if result.returncode != 0:
        return ChronyTrackingEvidence(
            status=GateStatus.BLOCKED,
            signed_system_time_offset_ms=None,
            absolute_system_time_offset_ms=None,
            leap_status=None,
            reason="CHRONYC_TRACKING_FAILED",
        )

    return parse_chronyc_tracking(result.stdout)


def _connection_generation(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return int(value)


def evaluate_kalshi_transport_liveness(
    *,
    runtime_session_id: str,
    connection_generation: int | None,
    connected: bool,
    last_pong_monotonic_ns: int | None,
    now_monotonic_ns: int,
) -> KalshiTransportLivenessEvidence:
    """Evaluate only current Kalshi WebSocket transport liveness.

    This implements the already-frozen client Ping/Pong contract:
    15-second client Ping interval plus 5-second Pong timeout.

    A successful Pong proves only that the current transport is alive. It does
    NOT advance Kalshi order-book sequence state, mark a cache ready, refresh
    a market book timestamp, or heal a prior sequence gap.
    """
    session = str(runtime_session_id)
    generation = _connection_generation(connection_generation)
    now_ns = int(now_monotonic_ns)

    base = {
        "runtime_session_id": session,
        "connection_generation": generation,
        "last_pong_monotonic_ns": (
            None
            if last_pong_monotonic_ns is None
            else int(last_pong_monotonic_ns)
        ),
        "evaluated_monotonic_ns": now_ns,
    }

    if not session:
        return KalshiTransportLivenessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_TRANSPORT_RUNTIME_SESSION_MISSING",
            pong_age_ns=None,
            **base,
        )

    if generation is None:
        return KalshiTransportLivenessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_CONNECTION_GENERATION_MISSING_OR_INVALID",
            pong_age_ns=None,
            **base,
        )

    if not connected:
        return KalshiTransportLivenessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_WEBSOCKET_NOT_CONNECTED",
            pong_age_ns=None,
            **base,
        )

    if last_pong_monotonic_ns is None:
        return KalshiTransportLivenessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_CURRENT_CONNECTION_PONG_NOT_PROVEN",
            pong_age_ns=None,
            **base,
        )

    pong_ns = int(last_pong_monotonic_ns)
    if pong_ns < 0 or now_ns < 0 or pong_ns > now_ns:
        return KalshiTransportLivenessEvidence(
            status=GateStatus.FATAL,
            reason="KALSHI_TRANSPORT_MONOTONIC_INVARIANT_FAILURE",
            pong_age_ns=None,
            **base,
        )

    age_ns = now_ns - pong_ns
    if age_ns > KALSHI_WS_MAX_PONG_AGE_NS:
        return KalshiTransportLivenessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_PONG_STALE",
            pong_age_ns=age_ns,
            **base,
        )

    return KalshiTransportLivenessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        pong_age_ns=age_ns,
        **base,
    )


def evaluate_coinbase_readiness(
    *,
    builder: CoinbaseMinuteBuilder,
    runtime_session_id: str,
    builder_runtime_session_id: str,
    current_connection_generation: int | None,
    builder_connection_generation: int | None,
    decision_epoch_s: int,
    now_monotonic_ns: int,
) -> CoinbaseReadinessEvidence:
    """Map the accepted Z-D minute builder into the frozen Coinbase gate.

    The builder must belong to both the current process session and the current
    Coinbase WebSocket connection generation. This prevents a heartbeat/minute
    state that was valid immediately before a reconnect from remaining
    actionable during the new connection.
    """
    target_start, target_end = completed_minute_target(
        int(decision_epoch_s)
    )
    current_generation = _connection_generation(
        current_connection_generation
    )
    builder_generation = _connection_generation(
        builder_connection_generation
    )

    base = {
        "target_minute_start_s": target_start,
        "target_minute_end_s": target_end,
        "connection_generation": current_generation,
    }

    if (
        not runtime_session_id
        or str(builder_runtime_session_id)
        != str(runtime_session_id)
    ):
        return CoinbaseReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="COINBASE_STATE_NOT_FROM_CURRENT_RUNTIME_SESSION",
            builder_status="SESSION_MISMATCH",
            close_trade_id=None,
            **base,
        )

    if (
        current_generation is None
        or builder_generation is None
        or builder_generation != current_generation
    ):
        return CoinbaseReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="COINBASE_STATE_NOT_FROM_CURRENT_CONNECTION_GENERATION",
            builder_status="CONNECTION_GENERATION_MISMATCH",
            close_trade_id=None,
            **base,
        )

    try:
        result = builder.completed_minute(
            minute_start_s=target_start,
            now_monotonic_ns=int(now_monotonic_ns),
        )
    except CoinbaseMinuteBuilderError:
        return CoinbaseReadinessEvidence(
            status=GateStatus.FATAL,
            reason="COINBASE_BUILDER_INVARIANT_FAILURE",
            builder_status="BUILDER_ERROR",
            close_trade_id=None,
            **base,
        )

    status = str(result.get("status", ""))
    if status != "AVAILABLE":
        return CoinbaseReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason=f"COINBASE_{status or 'UNKNOWN'}",
            builder_status=status or "UNKNOWN",
            close_trade_id=None,
            **base,
        )

    state = result.get("state")
    if state is None:
        return CoinbaseReadinessEvidence(
            status=GateStatus.FATAL,
            reason="COINBASE_AVAILABLE_WITHOUT_STATE",
            builder_status=status,
            close_trade_id=None,
            **base,
        )

    if (
        int(state.minute_start_s) != target_start
        or int(state.minute_end_s) != target_end
        or int(state.available_monotonic_ns)
        != int(now_monotonic_ns)
    ):
        return CoinbaseReadinessEvidence(
            status=GateStatus.FATAL,
            reason="COINBASE_COMPLETED_MINUTE_IDENTITY_MISMATCH",
            builder_status=status,
            close_trade_id=getattr(state, "close_trade_id", None),
            **base,
        )

    return CoinbaseReadinessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        builder_status=status,
        close_trade_id=int(state.close_trade_id),
        **base,
    )


def evaluate_kalshi_readiness(
    *,
    cache: KalshiBookCache,
    current_event: EventLadder,
    runtime_session_id: str,
    discovery_runtime_session_id: str,
    cache_runtime_session_id: str,
    cache_connection_generation: int | None,
    transport_liveness: KalshiTransportLivenessEvidence,
    now_ms: int,
) -> KalshiReadinessEvidence:
    """Map current-session/current-connection Kalshi state into its gate.

    Order-book exactness and transport liveness are independent requirements.
    A healthy Pong never repairs a book, resets a sequence, or makes an old
    connection's cache current.
    """
    expected = tuple(
        market.market_ticker
        for market in current_event.markets
    )
    cache_generation = _connection_generation(
        cache_connection_generation
    )

    base_kwargs: dict[str, Any] = {
        "event_ticker": current_event.event_ticker,
        "expected_tickers": expected,
        "generation": int(cache.generation),
        "last_seq": cache.last_seq,
        "subscription_sid": cache.subscription_sid,
        "connection_generation": cache_generation,
        "transport_reason": transport_liveness.reason,
    }

    if (
        not runtime_session_id
        or str(discovery_runtime_session_id)
        != str(runtime_session_id)
        or str(cache_runtime_session_id)
        != str(runtime_session_id)
        or str(transport_liveness.runtime_session_id)
        != str(runtime_session_id)
    ):
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_STATE_NOT_FROM_CURRENT_RUNTIME_SESSION",
            **base_kwargs,
        )

    if transport_liveness.status == GateStatus.FATAL:
        return KalshiReadinessEvidence(
            status=GateStatus.FATAL,
            reason=transport_liveness.reason,
            **base_kwargs,
        )

    if transport_liveness.status != GateStatus.PASS:
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason=transport_liveness.reason,
            **base_kwargs,
        )

    if (
        cache_generation is None
        or transport_liveness.connection_generation is None
        or cache_generation
        != transport_liveness.connection_generation
    ):
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_CACHE_NOT_FROM_CURRENT_CONNECTION_GENERATION",
            **base_kwargs,
        )

    if int(current_event.close_timestamp_ms) <= int(now_ms):
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_CURRENT_EVENT_NOT_FUTURE",
            **base_kwargs,
        )

    if not expected:
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_CURRENT_LADDER_EMPTY",
            **base_kwargs,
        )

    if tuple(cache.subscribed_tickers) != expected:
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_SUBSCRIPTION_NOT_EXACT_CURRENT_LADDER",
            **base_kwargs,
        )

    if cache.subscription_sid is None:
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_SUBSCRIPTION_SID_MISSING",
            **base_kwargs,
        )

    if cache.resync_required:
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_RESYNC_REQUIRED",
            **base_kwargs,
        )

    if not cache.all_ready():
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_FULL_LADDER_NOT_EXACT",
            **base_kwargs,
        )

    if cache.last_seq is None:
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_SEQUENCE_NOT_READY",
            **base_kwargs,
        )

    if set(cache.books) != set(expected):
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_BOOK_SET_MISMATCH",
            **base_kwargs,
        )

    if any(
        (not book.valid)
        or int(book.generation) != int(cache.generation)
        for book in cache.books.values()
    ):
        return KalshiReadinessEvidence(
            status=GateStatus.BLOCKED,
            reason="KALSHI_GENERATION_NOT_EXACT",
            **base_kwargs,
        )

    return KalshiReadinessEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        **base_kwargs,
    )


def build_current_source_gate_snapshot(
    *,
    frozen_identity_status: GateStatus,
    boot_identity: BootIdentityEvidence,
    cohort_status: CohortStatus,
    durability_status: GateStatus,
    clock_evidence: ChronyTrackingEvidence,
    coinbase_evidence: CoinbaseReadinessEvidence,
    kalshi_evidence: KalshiReadinessEvidence,
    strategy_reconciliation_status: GateStatus,
    execution_mode_disabled: bool = True,
) -> RestartGateSnapshot:
    """Combine B4 current-source evidence with already-frozen B1-B3 gates."""
    identity = frozen_identity_status

    if identity == GateStatus.PASS:
        identity = boot_identity.status

    return RestartGateSnapshot(
        identity=identity,
        cohort=cohort_status,
        durability=durability_status,
        clock=clock_evidence.status,
        coinbase=coinbase_evidence.status,
        kalshi=kalshi_evidence.status,
        strategy_reconciliation=strategy_reconciliation_status,
        execution_mode_disabled=bool(execution_mode_disabled),
    )
