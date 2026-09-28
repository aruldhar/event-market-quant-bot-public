"""Checkpoint 21N-Z-F network-free read-only source runtime core.

This is the deterministic state layer that the later AWS network workers wrap.

Invariants:
- every source payload is archived before JSON parsing or state transformation;
- source connection generations come from the accepted reconnect controller;
- Kalshi subscriptions cover the entire strategy-independent current event;
- sequence gaps invalidate book readiness;
- Coinbase gap/recovery semantics remain owned by CoinbaseMinuteBuilder;
- reconnect backoff resets only after actual readiness PASS;
- no Candidate-E signal, P&L, settlement, broker, order, or write path exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any, Mapping

from .kxbtcd_candidate_e_b5_r2_live_reconnect import (
    ReconnectGenerationController,
)
from .kxbtcd_candidate_e_coinbase_rest_seed import (
    BoundCoinbaseRestCandleSeed,
    bind_rest_candle_seed,
    evaluate_coinbase_with_rest_seed,
)
from .kxbtcd_candidate_e_prospective_live_collector import (
    CoinbaseCompletedCandleUnavailable,
    EventLadder,
    build_ladders_from_markets,
    completed_minute_target,
    parse_coinbase_completed_candle,
)
from .kxbtcd_candidate_e_soak_segment_manager import (
    HourlySourceSegmentManager,
    RecoverySummary,
    SourceBoundJournalAdapter,
)
from .kxbtcd_candidate_e_soak_source_lifecycle import (
    EventRolloverDecision,
    ReconnectBackoff,
    ReconnectDecision,
    choose_current_event_ladder,
    classify_event_rollover,
)
from .kxbtcd_candidate_e_v2_rest_candle_readiness import (
    V2BoundRestCandle,
    bind_v2_rest_candle,
    evaluate_v2_rest_candle,
)


COINBASE_WS_SOURCE = "coinbase_exchange_ws"
COINBASE_REST_SOURCE = "coinbase_exchange_rest"
KALSHI_WS_SOURCE = "kalshi_production_ws"
KALSHI_REST_SOURCE = "kalshi_production_rest"

ARCHIVE_SOURCES = (
    COINBASE_WS_SOURCE,
    COINBASE_REST_SOURCE,
    KALSHI_WS_SOURCE,
    KALSHI_REST_SOURCE,
)


class SoakRuntimeCoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class EventDiscoveryResult:
    current_event: EventLadder
    prior_event_ticker: str | None
    rollover_required: bool
    reason: str


@dataclass(frozen=True)
class ArchiveRecoveryResult:
    by_source: Mapping[str, RecoverySummary]


def _payload_object(
    raw_text: str,
    *,
    context: str,
) -> Mapping[str, Any]:
    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise SoakRuntimeCoreError(
            f"{context} raw payload is invalid JSON"
        ) from exc

    if not isinstance(value, Mapping):
        raise SoakRuntimeCoreError(
            f"{context} raw payload root must be an object"
        )

    return value


class SoakSourceRuntimeCore:
    """Own read-only source state for one OS process/runtime session."""

    def __init__(
        self,
        *,
        runtime_session_id: str,
        archive_root: str | Path,
        fsync_interval_ns: int = 1_000_000_000,
        metric_producers=None,
        observability=None,
        live_shadow_snapshot_publisher=None,
        live_shadow_settlement_publisher=None,
        monotonic_ns=time.monotonic_ns,
    ) -> None:
        session = str(runtime_session_id).strip()

        if not session:
            raise SoakRuntimeCoreError(
                "runtime_session_id must be non-empty"
            )

        self.runtime_session_id = session
        self.archive_root = Path(archive_root)
        self.metric_producers = metric_producers
        self.observability = observability
        # Optional one-way exporter.  It is intentionally not part of source
        # readiness and any failure is isolated from the evidence collector.
        self.live_shadow_snapshot_publisher = live_shadow_snapshot_publisher
        self.live_shadow_settlement_publisher = live_shadow_settlement_publisher
        self._monotonic_ns = monotonic_ns

        self.connections = ReconnectGenerationController(
            runtime_session_id=session
        )

        self._managers = {
            source: HourlySourceSegmentManager(
                self.archive_root,
                source=source,
                segment_instance_id=session,
                fsync_interval_ns=fsync_interval_ns,
            )
            for source in ARCHIVE_SOURCES
        }

        self._journals = {
            source: SourceBoundJournalAdapter(
                manager
            )
            for source, manager
            in self._managers.items()
        }
        if self.metric_producers is not None:
            self.metric_producers.storage_totals = self.storage_totals

        self.coinbase_backoff = ReconnectBackoff()
        self.kalshi_backoff = ReconnectBackoff()

        self.current_event: EventLadder | None = None
        self._pending_live_shadow_settlement_tickers: set[str] = set()
        self.discovery_runtime_session_id: str | None = None
        self.coinbase_rest_seed: (
            BoundCoinbaseRestCandleSeed | None
        ) = None
        # Frozen V2 consumes an independently polled exact completed candle.
        # Unlike ``coinbase_rest_seed``, this input deliberately has no
        # WebSocket-generation identity and is never cleared on WS reconnect.
        self.v2_coinbase_rest_candle: V2BoundRestCandle | None = None
        self._last_coinbase_received_ns = None
        self._last_kalshi_ping_sent_ns = None
        self._closed = False

    def _increment_metric(self, name, amount=1):
        if self.metric_producers is not None:
            self.metric_producers.increment(name, amount)

    def storage_totals(self):
        return (
            sum(manager.total_raw_bytes_written for manager in self._managers.values()),
            sum(manager.total_compressed_bytes_written for manager in self._managers.values()),
        )

    def fsync_due_raw_segments(self, *, now_monotonic_ns: int) -> int:
        """Service every active source segment during idle worker iterations."""
        if self._closed:
            raise SoakRuntimeCoreError("runtime core already closed")
        return sum(manager.fsync_if_due(now_monotonic_ns) for manager in self._managers.values())

    def _record_latency(self, name, started_ns, ended_ns):
        if self.observability is not None:
            self.observability.record_latency(name, started_ns=int(started_ns), ended_ns=int(ended_ns))

    def record_rest_latency(self, *, started_ns, ended_ns):
        self._record_latency("rest_request_duration", started_ns, ended_ns)

    def manager(
        self,
        source: str,
    ) -> HourlySourceSegmentManager:
        try:
            return self._managers[source]
        except KeyError as exc:
            raise SoakRuntimeCoreError(
                f"unknown runtime source: {source}"
            ) from exc

    def journal(
        self,
        source: str,
    ) -> SourceBoundJournalAdapter:
        try:
            return self._journals[source]
        except KeyError as exc:
            raise SoakRuntimeCoreError(
                f"unknown runtime source: {source}"
            ) from exc

    def recover_archives(
        self,
    ) -> ArchiveRecoveryResult:
        if self._closed:
            raise SoakRuntimeCoreError(
                "runtime core already closed"
            )

        recovered = {
            source: manager.recover_existing_segments()
            for source, manager
            in self._managers.items()
        }

        return ArchiveRecoveryResult(
            by_source=recovered
        )

    def discover_current_event_from_raw(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        now_timestamp_ms: int,
        request_identity: Mapping[
            str, Any
        ] | None = None,
    ) -> EventDiscoveryResult:
        """Persist exact Kalshi REST response before selecting any event."""

        self.manager(
            KALSHI_REST_SOURCE
        ).append(
            transport="https_rest",
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            request_identity=request_identity,
        )
        self._increment_metric("kalshi_snapshot_count", 0)

        return self.bind_persisted_kalshi_discovery_response(
            raw_text=raw_text,
            now_timestamp_ms=now_timestamp_ms,
        )


    def bind_persisted_kalshi_discovery_response(
        self,
        *,
        raw_text: str,
        now_timestamp_ms: int,
    ) -> EventDiscoveryResult:
        """Select/bind an already raw-persisted Kalshi markets response.

        Callers MUST persist the exact HTTP response before invoking this
        method. A paginated response is deliberately rejected because one
        page cannot prove the complete selected KXBTCD event ladder.
        """
        payload = _payload_object(
            raw_text,
            context="Kalshi market discovery",
        )

        # A nonempty cursor proves this /markets response is only a page
        # of the requested KXBTCD universe. Selection from a partial page
        # is forbidden because it could omit markets from the current event.
        cursor = payload.get("cursor")

        if cursor is not None and str(cursor).strip():
            raise SoakRuntimeCoreError(
                "Kalshi market discovery response is paginated/incomplete"
            )


        ladders = build_ladders_from_markets(
            payload
        )

        selected = choose_current_event_ladder(
            ladders,
            now_timestamp_ms=now_timestamp_ms,
        )

        prior = self.current_event

        if prior is None:
            result = EventDiscoveryResult(
                current_event=selected,
                prior_event_ticker=None,
                rollover_required=False,
                reason="INITIAL_EVENT_DISCOVERY",
            )
        else:
            decision: EventRolloverDecision = (
                classify_event_rollover(
                    current_event_ticker=(
                        prior.event_ticker
                    ),
                    current_event_close_timestamp_ms=(
                        prior.close_timestamp_ms
                    ),
                    now_timestamp_ms=(
                        now_timestamp_ms
                    ),
                    rediscovered_current_event_ticker=(
                        selected.event_ticker
                    ),
                )
            )

            result = EventDiscoveryResult(
                current_event=selected,
                prior_event_ticker=(
                    prior.event_ticker
                ),
                rollover_required=(
                    decision.rollover_required
                ),
                reason=decision.reason,
            )

        if result.rollover_required and prior is not None:
            self._pending_live_shadow_settlement_tickers.update(
                market.market_ticker for market in prior.markets
            )
        self.current_event = selected
        self.discovery_runtime_session_id = (
            self.runtime_session_id
        )

        if result.rollover_required:
            self._increment_metric("event_rollover_count")

        return result

    def pending_live_shadow_settlement_tickers(self) -> tuple[str, ...]:
        """Return prior-event markets awaiting an official final result."""
        return tuple(sorted(self._pending_live_shadow_settlement_tickers))

    def queue_live_shadow_settlement_tickers(self, market_tickers) -> None:
        """Register known shadow markets for a bounded read-only closeout probe."""
        if self._closed:
            raise SoakRuntimeCoreError("runtime core already closed")
        tickers = tuple(market_tickers)
        if any(not isinstance(ticker, str) or not ticker.strip() for ticker in tickers):
            raise SoakRuntimeCoreError("Kalshi settlement ticker is invalid")
        self._pending_live_shadow_settlement_tickers.update(tickers)

    def bind_persisted_kalshi_market_settlement_response(
        self, *, raw_text: str, market_ticker: str, received_utc: str,
    ) -> bool:
        """Publish only final Kalshi outcome evidence already archived raw-first."""
        payload = _payload_object(raw_text, context="Kalshi final market")
        market = payload.get("market")
        if not isinstance(market, Mapping):
            raise SoakRuntimeCoreError("Kalshi final market response lacks market object")
        if market.get("ticker") != market_ticker:
            raise SoakRuntimeCoreError("Kalshi final market response ticker mismatch")
        status = market.get("status")
        result = market.get("result")
        if status != "finalized":
            return False
        if result not in {"yes", "no"}:
            raise SoakRuntimeCoreError("Kalshi finalized market result is invalid")
        if market_ticker not in self._pending_live_shadow_settlement_tickers:
            return False
        publisher = self.live_shadow_settlement_publisher
        if publisher is None:
            return False
        from .kxbtcd_candidate_e_live_shadow_settlement import OfficialKalshiSettlement
        published = publisher.publish(OfficialKalshiSettlement(
            market_ticker=market_ticker,
            official_market_status=status,
            official_market_result=result,
            observed_utc=received_utc,
        ))
        self._pending_live_shadow_settlement_tickers.discard(market_ticker)
        return published

    def bind_persisted_coinbase_rest_seed_candle(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        decision_epoch_s: int,
    ) -> BoundCoinbaseRestCandleSeed:
        """Parse/bind a candle whose HTTP body is already raw-persisted."""

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise SoakRuntimeCoreError(
                "Coinbase REST seed payload is invalid JSON"
            ) from exc

        target_start, _ = completed_minute_target(
            int(decision_epoch_s)
        )

        minute = parse_coinbase_completed_candle(
            payload,
            target_start_s=target_start,
            available_monotonic_ns=(
                received_monotonic_ns
            ),
            raw_received_utc=received_utc,
        )

        binding = self.connections.current_coinbase

        if binding is None or not binding.connected:
            raise SoakRuntimeCoreError(
                "Coinbase REST seed requires current open generation"
            )

        bound = bind_rest_candle_seed(
            runtime_session_id=(
                self.runtime_session_id
            ),
            connection_generation=(
                binding.generation
            ),
            minute=minute,
        )

        self.coinbase_rest_seed = bound
        return bound

    def ingest_coinbase_rest_seed_candle(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        decision_epoch_s: int,
        request_identity: Mapping[
            str, Any
        ] | None = None,
    ) -> BoundCoinbaseRestCandleSeed:
        """Persist and bind one exact required 60-second REST candle."""

        self.manager(
            COINBASE_REST_SOURCE
        ).append(
            transport="https_rest",
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            request_identity=request_identity,
        )

        # Parsing/binding occurs only after raw append/flush returns.
        return self.bind_persisted_coinbase_rest_seed_candle(
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            decision_epoch_s=decision_epoch_s,
        )

    def ingest_v2_coinbase_rest_candle(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        target_minute_start_s: int,
        request_identity: Mapping[str, Any] | None = None,
    ) -> V2BoundRestCandle:
        """Persist and bind V2's independently polled exact candle.

        The target interval is frozen by the caller before the HTTP request;
        it is never inferred from receipt time, which can cross a minute
        boundary while the request is in flight.
        """
        self.persist_v2_coinbase_rest_candle_response(
            raw_text=raw_text,
            received_monotonic_ns=received_monotonic_ns,
            received_utc=received_utc,
            request_identity=request_identity,
        )
        return self.bind_persisted_v2_coinbase_rest_candle(
            raw_text=raw_text,
            received_monotonic_ns=received_monotonic_ns,
            received_utc=received_utc,
            target_minute_start_s=target_minute_start_s,
        )

    def persist_v2_coinbase_rest_candle_response(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        request_identity: Mapping[str, Any] | None = None,
    ) -> None:
        """Durably append the exact V2 candle HTTP response before handling it."""
        self.manager(COINBASE_REST_SOURCE).append(
            transport="https_rest",
            raw_text=raw_text,
            received_monotonic_ns=received_monotonic_ns,
            received_utc=received_utc,
            request_identity=request_identity,
        )

    def bind_persisted_v2_coinbase_rest_candle(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        target_minute_start_s: int,
    ) -> V2BoundRestCandle:
        """Parse and bind a V2 candle after its raw HTTP body is durable."""
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise SoakRuntimeCoreError(
                "V2 Coinbase REST payload is invalid JSON"
            ) from exc
        try:
            minute = parse_coinbase_completed_candle(
                payload,
                target_start_s=int(target_minute_start_s),
                available_monotonic_ns=int(received_monotonic_ns),
                raw_received_utc=str(received_utc),
            )
            bound = bind_v2_rest_candle(
                runtime_session_id=self.runtime_session_id,
                minute=minute,
            )
        except CoinbaseCompletedCandleUnavailable:
            raise
        except Exception as exc:
            if isinstance(exc, SoakRuntimeCoreError):
                raise
            raise SoakRuntimeCoreError(
                "V2 Coinbase REST candle is invalid"
            ) from exc
        self.v2_coinbase_rest_candle = bound
        return bound

    def evaluate_v2_coinbase_rest_candle(
        self,
        *,
        decision_epoch_s: int,
        now_monotonic_ns: int,
    ):
        return evaluate_v2_rest_candle(
            candle=self.v2_coinbase_rest_candle,
            runtime_session_id=self.runtime_session_id,
            decision_epoch_s=int(decision_epoch_s),
            now_monotonic_ns=int(now_monotonic_ns),
        )

    def open_coinbase_generation(
        self,
        *,
        opened_monotonic_ns: int,
    ):
        if self._closed:
            raise SoakRuntimeCoreError(
                "runtime core already closed"
            )

        binding = self.connections.open_coinbase(
            opened_monotonic_ns=(
                opened_monotonic_ns
            )
        )
        if self.metric_producers is not None:
            self.metric_producers.generation_opened("coinbase", binding.generation)
        if self.observability is not None:
            self.observability.record_source_event(source="coinbase", event="generation_open", generation=binding.generation,
                monotonic_ns=opened_monotonic_ns)
        return binding

    def open_kalshi_generation(
        self,
        *,
        opened_monotonic_ns: int,
    ):
        if self._closed:
            raise SoakRuntimeCoreError(
                "runtime core already closed"
            )

        event = self.current_event

        if event is None:
            raise SoakRuntimeCoreError(
                "Kalshi generation requires current event discovery"
            )

        tickers = tuple(
            market.market_ticker
            for market in event.markets
        )

        if not tickers:
            raise SoakRuntimeCoreError(
                "current event ladder is empty"
            )

        binding = self.connections.open_kalshi(
            subscribed_tickers=tickers,
            opened_monotonic_ns=(
                opened_monotonic_ns
            ),
        )
        if self.metric_producers is not None:
            self.metric_producers.generation_opened("kalshi", binding.generation)
        if self.observability is not None:
            self.observability.record_source_event(source="kalshi", event="generation_open", generation=binding.generation,
                monotonic_ns=opened_monotonic_ns, event_ticker=event.event_ticker)
        return binding

    def ingest_coinbase_ws_frame(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
    ) -> Mapping[str, Any]:
        # RAW FIRST.
        self.manager(
            COINBASE_WS_SOURCE
        ).append(
            transport="wss",
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            request_identity={
                "product_id": "BTC-USD",
            },
        )
        self._increment_metric("coinbase_message_count")
        if self._last_coinbase_received_ns is not None:
            self._record_latency("coinbase_receive_interarrival", self._last_coinbase_received_ns, received_monotonic_ns)
        self._last_coinbase_received_ns = received_monotonic_ns
        persisted_ns = int(self._monotonic_ns())
        self._record_latency("receive_to_raw_persist_duration", received_monotonic_ns, persisted_ns)

        payload = _payload_object(
            raw_text,
            context="Coinbase WebSocket",
        )

        binding = self.connections.current_coinbase

        if binding is None or not binding.connected:
            raise SoakRuntimeCoreError(
                "Coinbase frame has no current open generation"
            )

        result = binding.builder.apply_ws(
            payload,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
        )
        if payload.get("type") == "heartbeat":
            self._increment_metric("coinbase_heartbeat_count")
        self._record_latency(
            "raw_persist_to_parse_apply_duration",
            persisted_ns,
            int(self._monotonic_ns()),
        )
        return result

    def ingest_kalshi_ws_frame(
        self,
        *,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
    ) -> Mapping[str, Any]:
        # RAW FIRST.
        self.manager(
            KALSHI_WS_SOURCE
        ).append(
            transport="wss",
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            request_identity={
                "channel": "orderbook_delta",
            },
        )
        persisted_ns = int(self._monotonic_ns())
        self._record_latency(
            "receive_to_raw_persist_duration",
            received_monotonic_ns,
            persisted_ns,
        )

        payload = _payload_object(
            raw_text,
            context="Kalshi WebSocket",
        )

        binding = self.connections.current_kalshi

        if binding is None or not binding.connected:
            raise SoakRuntimeCoreError(
                "Kalshi frame has no current open generation"
            )

        result = binding.cache.apply_message(payload)
        kind = payload.get("type")
        if kind == "orderbook_snapshot":
            self._increment_metric("kalshi_snapshot_count")
        elif kind == "orderbook_delta":
            self._increment_metric("kalshi_delta_count")
        if result.get("gap"):
            self._increment_metric("kalshi_sequence_gap_count")
            if self.observability is not None:
                self.observability.record_source_event(source="kalshi", event="sequence_gap", generation=binding.generation,
                    monotonic_ns=received_monotonic_ns, event_ticker=self.current_event.event_ticker if self.current_event else None)
        self._record_latency(
            "raw_persist_to_parse_apply_duration",
            persisted_ns,
            int(self._monotonic_ns()),
        )
        publisher = self.live_shadow_snapshot_publisher
        if publisher is not None:
            try:
                publisher.publish_if_due(
                    core=self, received_utc=received_utc,
                    received_monotonic_ns=int(received_monotonic_ns),
                )
            except Exception:
                # Dashboard simulation is optional instrumentation.  Its
                # filesystem failure may be surfaced by its own health view,
                # but must not corrupt, block, or fail the raw evidence soak.
                pass
        return result

    def record_kalshi_pong(
        self,
        *,
        pong_monotonic_ns: int,
    ) -> None:
        binding = self.connections.current_kalshi

        if binding is None or not binding.connected:
            raise SoakRuntimeCoreError(
                "Kalshi Pong has no current open generation"
            )

        self.connections.record_kalshi_pong(
            generation=binding.generation,
            pong_monotonic_ns=pong_monotonic_ns,
        )
        self._increment_metric("kalshi_pong_successes")
        if self._last_kalshi_ping_sent_ns is not None:
            self._record_latency("kalshi_ping_pong_rtt", self._last_kalshi_ping_sent_ns, pong_monotonic_ns)
        if self.observability is not None:
            self.observability.record_source_event(source="kalshi", event="pong", generation=binding.generation,
                monotonic_ns=pong_monotonic_ns, event_ticker=self.current_event.event_ticker if self.current_event else None)

    def record_kalshi_ping_sent(self, *, ping_monotonic_ns: int) -> None:
        binding = self.connections.current_kalshi
        if binding is None or not binding.connected:
            raise SoakRuntimeCoreError("Kalshi Ping has no current open generation")
        self._last_kalshi_ping_sent_ns = int(ping_monotonic_ns)
        self._increment_metric("kalshi_ping_attempts")
        if self.observability is not None:
            self.observability.record_source_event(source="kalshi", event="ping", generation=binding.generation,
                monotonic_ns=ping_monotonic_ns, event_ticker=self.current_event.event_ticker if self.current_event else None)

    def record_kalshi_pong_timeout(self, *, observed_monotonic_ns: int) -> None:
        binding = self.connections.current_kalshi
        if binding is None or not binding.connected:
            raise SoakRuntimeCoreError("Kalshi Pong timeout has no current open generation")
        self._increment_metric("kalshi_pong_timeouts")
        if self.observability is not None:
            self.observability.record_source_event(source="kalshi", event="pong_timeout", generation=binding.generation,
                monotonic_ns=observed_monotonic_ns, event_ticker=self.current_event.event_ticker if self.current_event else None)

    def evaluate_coinbase(
        self,
        *,
        decision_epoch_s: int,
        now_monotonic_ns: int,
    ):
        binding = self.connections.current_coinbase

        if binding is None:
            raise SoakRuntimeCoreError(
                "Coinbase generation is not open"
            )

        base = self.connections.evaluate_coinbase(
            binding=binding,
            decision_epoch_s=decision_epoch_s,
            now_monotonic_ns=now_monotonic_ns,
        )

        return evaluate_coinbase_with_rest_seed(
            base_evidence=base,
            seed=self.coinbase_rest_seed,
            runtime_session_id=(
                self.runtime_session_id
            ),
            current_connection_generation=(
                binding.generation
            ),
            now_monotonic_ns=now_monotonic_ns,
        )

    def evaluate_kalshi(
        self,
        *,
        now_timestamp_ms: int,
        now_monotonic_ns: int,
    ):
        binding = self.connections.current_kalshi
        event = self.current_event

        if binding is None or event is None:
            raise SoakRuntimeCoreError(
                "Kalshi readiness lacks generation/event"
            )

        discovery_session = (
            self.discovery_runtime_session_id
        )

        if discovery_session is None:
            raise SoakRuntimeCoreError(
                "Kalshi readiness lacks discovery session"
            )

        return self.connections.evaluate_kalshi(
            binding=binding,
            current_event=event,
            discovery_runtime_session_id=(
                discovery_session
            ),
            now_ms=now_timestamp_ms,
            now_monotonic_ns=now_monotonic_ns,
        )

    def record_source_failure(
        self,
        source_family: str,
        *,
        observed_monotonic_ns: int,
        reconnect_reason: str | None = None,
    ) -> ReconnectDecision:
        if source_family == "coinbase":
            decision = self.coinbase_backoff.record_failure(
                observed_monotonic_ns=(
                    observed_monotonic_ns
                )
            )
            self._increment_metric("coinbase_reconnect_attempts")
            binding = self.connections.current_coinbase
            if self.observability is not None and binding is not None:
                self.observability.record_source_event(source="coinbase", event="reconnect_attempt",
                    generation=binding.generation, monotonic_ns=observed_monotonic_ns)
            return decision

        if source_family == "kalshi":
            decision = self.kalshi_backoff.record_failure(
                observed_monotonic_ns=(
                    observed_monotonic_ns
                )
            )
            self._increment_metric("kalshi_reconnect_attempts")
            binding = self.connections.current_kalshi
            if self.observability is not None and binding is not None:
                self.observability.record_source_event(source="kalshi", event="reconnect_attempt",
                    generation=binding.generation, monotonic_ns=observed_monotonic_ns,
                    event_ticker=self.current_event.event_ticker if self.current_event else None,
                    reconnect_reason=reconnect_reason)
            return decision

        raise SoakRuntimeCoreError(
            "unknown source family"
        )

    def record_kalshi_transport_error(self, *, failure_class: str, observed_monotonic_ns: int) -> None:
        binding = self.connections.current_kalshi
        if self.observability is not None and binding is not None:
            self.observability.record_source_event(source="kalshi", event="transport_error",
                generation=binding.generation, monotonic_ns=observed_monotonic_ns,
                event_ticker=self.current_event.event_ticker if self.current_event else None,
                failure_class=failure_class)

    def mark_source_ready(
        self,
        source_family: str,
    ) -> None:
        if source_family == "coinbase":
            recovering = self.coinbase_backoff.consecutive_failures > 0
            self.coinbase_backoff.readiness_passed()
            if recovering:
                self._increment_metric("coinbase_recovery_count")
                self._increment_metric("coinbase_reconnect_successes")
            return

        if source_family == "kalshi":
            recovering = self.kalshi_backoff.consecutive_failures > 0
            self.kalshi_backoff.readiness_passed()
            if recovering:
                self._increment_metric("kalshi_recovery_count")
                self._increment_metric("kalshi_reconnect_successes")
            return

        raise SoakRuntimeCoreError(
            "unknown source family"
        )

    def source_retry_allowed(
        self,
        source_family: str,
        *,
        now_monotonic_ns: int,
    ) -> bool:
        if source_family == "coinbase":
            return self.coinbase_backoff.retry_allowed(
                now_monotonic_ns=now_monotonic_ns
            )

        if source_family == "kalshi":
            return self.kalshi_backoff.retry_allowed(
                now_monotonic_ns=now_monotonic_ns
            )

        raise SoakRuntimeCoreError(
            "unknown source family"
        )

    def close(self) -> None:
        if self._closed:
            return

        for manager in self._managers.values():
            manager.close()

        self._closed = True
