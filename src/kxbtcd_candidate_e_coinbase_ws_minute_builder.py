"""Checkpoint 21N-Z-D1: pure Coinbase completed-minute stream state.

No network access occurs in this module.

Callers MUST preserve the exact raw Coinbase frame/REST response before invoking
this state machine. This module only validates and transforms already-preserved
evidence.

Execution/order behavior is intentionally absent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from .kxbtcd_candidate_e_coinbase_rest_recovery import (
    CoinbaseRestRecoveryEvidence,
)
from .kxbtcd_candidate_e_coinbase_cross_transport_identity import (
    compare_ws_rest_trade_identity,
)


COINBASE_PRODUCT = "BTC-USD"
ARCHITECTURE_FINGERPRINT = (
    "3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7"
)
HEARTBEAT_STALE_NS = 3_000_000_000


class CoinbaseMinuteBuilderError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise CoinbaseMinuteBuilderError(message)


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        fail(f"{name} must be integer")
    if value < 0:
        fail(f"{name} must be nonnegative")
    return value


def _positive_decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise CoinbaseMinuteBuilderError(
            f"{name} must be decimal-compatible"
        ) from exc
    if not result.is_finite() or result <= 0:
        fail(f"{name} must be finite and positive")
    return result


def _source_time(value: Any, name: str = "time") -> tuple[str, int]:
    text = str(value).strip()
    if not text:
        fail(f"{name} missing")
    if text.endswith("Z"):
        parse_text = text[:-1] + "+00:00"
    else:
        parse_text = text
    try:
        dt = datetime.fromisoformat(parse_text)
    except ValueError as exc:
        raise CoinbaseMinuteBuilderError(
            f"{name} must be ISO-8601"
        ) from exc
    if dt.tzinfo is None:
        fail(f"{name} must be timezone-aware")
    dt = dt.astimezone(timezone.utc)
    epoch_seconds = int(dt.timestamp())
    epoch_us = epoch_seconds * 1_000_000 + dt.microsecond
    normalized = dt.isoformat().replace("+00:00", "Z")
    return normalized, epoch_us


@dataclass(frozen=True)
class CoinbaseTrade:
    trade_id: int
    sequence: int | None
    source_time_utc: str
    source_time_us: int
    minute_start_s: int
    price: Decimal
    evidence_source: str
    size: Decimal | None = None
    side: str | None = None


@dataclass(frozen=True)
class CoinbaseCompletedMinute:
    minute_start_s: int
    minute_end_s: int
    close_price: Decimal
    close_trade_id: int
    close_trade_time_utc: str
    heartbeat_trade_id: int
    heartbeat_time_utc: str
    available_monotonic_ns: int


def _trade_side(value: Any) -> str:
    side = str(value)

    if side not in {"buy", "sell"}:
        fail(f"invalid Coinbase trade side: {side!r}")

    return side


def _ws_trade(payload: Mapping[str, Any]) -> CoinbaseTrade:
    product = str(payload.get("product_id", ""))
    if product != COINBASE_PRODUCT:
        fail(f"unexpected Coinbase product: {product!r}")

    message_type = str(payload.get("type", ""))
    if message_type not in {"last_match", "match"}:
        fail("not a Coinbase match message")

    trade_id = _integer(payload.get("trade_id"), "trade_id")
    sequence = _integer(payload.get("sequence"), "sequence")
    source_time_utc, source_time_us = _source_time(payload.get("time"))
    price = _positive_decimal(payload.get("price"), "price")
    size = _positive_decimal(payload.get("size"), "size")
    side = _trade_side(payload.get("side"))

    return CoinbaseTrade(
        trade_id=trade_id,
        sequence=sequence,
        source_time_utc=source_time_utc,
        source_time_us=source_time_us,
        minute_start_s=(source_time_us // 1_000_000 // 60) * 60,
        price=price,
        evidence_source=f"coinbase_ws_{message_type}",
        size=size,
        side=side,
    )


def _rest_trade(payload: Mapping[str, Any]) -> CoinbaseTrade:
    trade_id = _integer(payload.get("trade_id"), "trade_id")
    source_time_utc, source_time_us = _source_time(payload.get("time"))
    price = _positive_decimal(payload.get("price"), "price")
    size = _positive_decimal(payload.get("size"), "size")
    side = _trade_side(payload.get("side"))

    return CoinbaseTrade(
        trade_id=trade_id,
        sequence=None,
        source_time_utc=source_time_utc,
        source_time_us=source_time_us,
        minute_start_s=(source_time_us // 1_000_000 // 60) * 60,
        price=price,
        evidence_source="coinbase_rest_recovery",
        size=size,
        side=side,
    )


class CoinbaseMinuteBuilder:
    """Deterministic BTC-USD completed-minute state machine.

    The stream begins from Coinbase's documented `last_match` baseline.

    A trade-ID discontinuity or a heartbeat whose last_trade_id is ahead of
    locally reconstructed trade evidence causes a fail-closed recovery state.
    REST recovery may clear that state only when every trade ID in the frozen
    recovery interval has exact evidence.
    """

    def __init__(self) -> None:
        self.seeded = False

        self.last_sequence: int | None = None
        self.sequence_healthy = True

        self.observed_trade_high_water: int | None = None
        self.exchange_trade_high_water: int | None = None

        self.last_heartbeat_trade_id: int | None = None
        self.last_heartbeat_source_time_utc: str | None = None
        self.last_heartbeat_source_time_us: int | None = None
        self.last_heartbeat_received_monotonic_ns: int | None = None

        self.recovery_required = False
        self.recovery_from_trade_id: int | None = None
        self.recovery_target_trade_id: int | None = None

        self._trade_by_id: dict[int, CoinbaseTrade] = {}
        self._minute_last_trade: dict[int, CoinbaseTrade] = {}

    def _observe_sequence(self, sequence: int) -> None:
        if self.last_sequence is not None and sequence < self.last_sequence:
            self.sequence_healthy = False
        if self.last_sequence is None or sequence > self.last_sequence:
            self.last_sequence = sequence

    def _record_trade(self, trade: CoinbaseTrade) -> bool:
        prior_same_id = self._trade_by_id.get(trade.trade_id)

        if prior_same_id is not None:
            prior_is_ws = prior_same_id.evidence_source.startswith(
                "coinbase_ws_"
            )
            new_is_ws = trade.evidence_source.startswith(
                "coinbase_ws_"
            )

            prior_is_rest = (
                prior_same_id.evidence_source
                == "coinbase_rest_recovery"
            )
            new_is_rest = (
                trade.evidence_source
                == "coinbase_rest_recovery"
            )

            cross_transport = (
                (prior_is_ws and new_is_rest)
                or (prior_is_rest and new_is_ws)
            )

            if cross_transport:
                if (
                    prior_same_id.size is None
                    or trade.size is None
                    or prior_same_id.side is None
                    or trade.side is None
                ):
                    fail(
                        "cross-transport identity fields missing "
                        f"for trade_id {trade.trade_id}"
                    )

                prior_mapping = {
                    "trade_id": prior_same_id.trade_id,
                    "price": str(prior_same_id.price),
                    "size": str(prior_same_id.size),
                    "side": prior_same_id.side,
                    "time": prior_same_id.source_time_utc,
                }

                new_mapping = {
                    "trade_id": trade.trade_id,
                    "price": str(trade.price),
                    "size": str(trade.size),
                    "side": trade.side,
                    "time": trade.source_time_utc,
                }

                if prior_is_ws:
                    identity = compare_ws_rest_trade_identity(
                        prior_mapping,
                        new_mapping,
                    )
                else:
                    identity = compare_ws_rest_trade_identity(
                        new_mapping,
                        prior_mapping,
                    )

                if not identity.compatible:
                    fail(
                        "conflicting cross-transport evidence "
                        f"for trade_id {trade.trade_id}: "
                        f"price_equal={identity.price_equal}, "
                        f"size_equal={identity.size_equal}, "
                        f"side_equal={identity.side_equal}, "
                        f"timestamp_delta_us="
                        f"{identity.timestamp_delta_us}, "
                        f"same_utc_minute="
                        f"{identity.same_utc_minute}"
                    )

                # Corroboration only. Preserve the first accepted object
                # and therefore preserve its source timestamp/minute state.
                return False

            # Same-transport duplicates remain exact. We do not apply the
            # WS/REST tolerance to two observations from the same transport.
            if (
                prior_same_id.source_time_us
                != trade.source_time_us
                or prior_same_id.minute_start_s
                != trade.minute_start_s
                or prior_same_id.price
                != trade.price
                or prior_same_id.size
                != trade.size
                or prior_same_id.side
                != trade.side
            ):
                fail(
                    f"conflicting evidence for trade_id {trade.trade_id}"
                )

            return False

        self._trade_by_id[trade.trade_id] = trade

        prior_minute = self._minute_last_trade.get(trade.minute_start_s)
        if prior_minute is None or (
            trade.source_time_us,
            trade.trade_id,
        ) > (
            prior_minute.source_time_us,
            prior_minute.trade_id,
        ):
            self._minute_last_trade[trade.minute_start_s] = trade

        if (
            self.observed_trade_high_water is None
            or trade.trade_id > self.observed_trade_high_water
        ):
            self.observed_trade_high_water = trade.trade_id

        return True

    def _mark_recovery(self, start_exclusive: int, target_inclusive: int) -> None:
        if target_inclusive <= start_exclusive:
            return

        if not self.recovery_required:
            self.recovery_from_trade_id = start_exclusive
            self.recovery_target_trade_id = target_inclusive
        else:
            assert self.recovery_from_trade_id is not None
            assert self.recovery_target_trade_id is not None
            self.recovery_from_trade_id = min(
                self.recovery_from_trade_id,
                start_exclusive,
            )
            self.recovery_target_trade_id = max(
                self.recovery_target_trade_id,
                target_inclusive,
            )

        self.recovery_required = True

    def apply_ws(
        self,
        payload: Mapping[str, Any],
        *,
        received_monotonic_ns: int,
    ) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            fail("Coinbase WebSocket payload must be an object")

        message_type = str(payload.get("type", ""))

        if message_type == "subscriptions":
            return {
                "type": "subscriptions",
                "state_changed": False,
            }

        if message_type == "error":
            fail("Coinbase WebSocket returned error message")

        if message_type in {"last_match", "match"}:
            trade = _ws_trade(payload)
            self._observe_sequence(trade.sequence or 0)

            if message_type == "last_match":
                if self.seeded:
                    fail("duplicate last_match seed")
                self.seeded = True
                self._record_trade(trade)

                if (
                    self.exchange_trade_high_water is not None
                    and self.exchange_trade_high_water > trade.trade_id
                ):
                    self._mark_recovery(
                        trade.trade_id,
                        self.exchange_trade_high_water,
                    )

                return {
                    "type": "last_match",
                    "trade_id": trade.trade_id,
                    "recovery_required": self.recovery_required,
                }

            if not self.seeded:
                fail("match received before last_match seed")

            prior_high = self.observed_trade_high_water
            if prior_high is None:
                fail("seeded stream missing trade watermark")

            if trade.trade_id > prior_high + 1:
                self._mark_recovery(prior_high, trade.trade_id)

            if (
                trade.trade_id < prior_high
                and trade.trade_id not in self._trade_by_id
            ):
                self.sequence_healthy = False

            self._record_trade(trade)

            if (
                self.exchange_trade_high_water is None
                or trade.trade_id > self.exchange_trade_high_water
            ):
                self.exchange_trade_high_water = trade.trade_id

            return {
                "type": "match",
                "trade_id": trade.trade_id,
                "recovery_required": self.recovery_required,
            }

        if message_type == "heartbeat":
            product = str(payload.get("product_id", ""))
            if product != COINBASE_PRODUCT:
                fail(f"unexpected Coinbase product: {product!r}")

            sequence = _integer(payload.get("sequence"), "sequence")
            heartbeat_trade_id = _integer(
                payload.get("last_trade_id"),
                "last_trade_id",
            )
            heartbeat_time_utc, heartbeat_time_us = _source_time(
                payload.get("time")
            )

            self._observe_sequence(sequence)

            if (
                self.last_heartbeat_source_time_us is not None
                and heartbeat_time_us < self.last_heartbeat_source_time_us
            ):
                return {
                    "type": "heartbeat",
                    "stale_source_message": True,
                    "recovery_required": self.recovery_required,
                }

            self.last_heartbeat_trade_id = heartbeat_trade_id
            self.last_heartbeat_source_time_utc = heartbeat_time_utc
            self.last_heartbeat_source_time_us = heartbeat_time_us
            self.last_heartbeat_received_monotonic_ns = int(
                received_monotonic_ns
            )

            if (
                self.exchange_trade_high_water is None
                or heartbeat_trade_id > self.exchange_trade_high_water
            ):
                self.exchange_trade_high_water = heartbeat_trade_id

            if self.seeded:
                observed = self.observed_trade_high_water
                if observed is None:
                    fail("seeded stream missing observed trade watermark")
                if heartbeat_trade_id > observed:
                    self._mark_recovery(observed, heartbeat_trade_id)

            return {
                "type": "heartbeat",
                "last_trade_id": heartbeat_trade_id,
                "recovery_required": self.recovery_required,
            }

        fail(f"unexpected Coinbase WebSocket message type: {message_type!r}")
        raise AssertionError

    def apply_rest_recovery(
        self,
        evidence: CoinbaseRestRecoveryEvidence,
    ) -> dict[str, Any]:
        """Apply a cursor-coverage-proven Coinbase REST recovery.

        Numeric trade-ID contiguity is intentionally NOT required.

        The network paginator must prove that its consecutive REST pages
        bracket the exact locally-known pre-gap trade and the exact target
        trade identified by heartbeat/stream evidence.
        """
        if not self.recovery_required:
            return {
                "status": "NO_RECOVERY_REQUIRED",
                "added_trade_count": 0,
            }

        if self.recovery_from_trade_id is None:
            fail("recovery start watermark missing")

        if self.recovery_target_trade_id is None:
            fail("recovery target watermark missing")

        if not isinstance(
            evidence,
            CoinbaseRestRecoveryEvidence,
        ):
            fail("REST recovery evidence has wrong type")

        start = self.recovery_from_trade_id
        target = self.recovery_target_trade_id

        # A heartbeat or later WS trade may extend the missing interval while
        # REST is in flight. Old evidence must never clear a newer gap.
        if (
            evidence.start_exclusive_trade_id != start
            or evidence.target_inclusive_trade_id != target
        ):
            return {
                "status": "RECOVERY_EVIDENCE_STALE",
                "expected_start_trade_id": start,
                "expected_target_trade_id": target,
                "evidence_start_trade_id":
                    evidence.start_exclusive_trade_id,
                "evidence_target_trade_id":
                    evidence.target_inclusive_trade_id,
            }

        if not evidence.coverage_proven:
            return {
                "status": "RECOVERY_INCOMPLETE",
                "boundary_trade_seen":
                    evidence.boundary_trade_seen,
                "target_trade_seen":
                    evidence.target_trade_seen,
                "page_count":
                    evidence.page_count,
                "raw_row_count":
                    evidence.raw_row_count,
            }

        added = 0

        for row in evidence.interval_rows:
            trade = _rest_trade(row)

            if not (
                start < trade.trade_id <= target
            ):
                fail(
                    "REST recovery evidence contains "
                    "trade outside frozen interval"
                )

            if self._record_trade(trade):
                added += 1

        # The exact target must now exist either from WS or REST evidence.
        if target not in self._trade_by_id:
            fail(
                "coverage-proven REST recovery missing target trade"
            )

        self.observed_trade_high_water = max(
            self.observed_trade_high_water or 0,
            target,
        )

        self.recovery_required = False
        self.recovery_from_trade_id = None
        self.recovery_target_trade_id = None

        return {
            "status": "RECOVERY_COMPLETE",
            "added_trade_count": added,
            "page_count": evidence.page_count,
            "raw_row_count": evidence.raw_row_count,
        }

    def completed_minute(
        self,
        *,
        minute_start_s: int,
        now_monotonic_ns: int,
    ) -> dict[str, Any]:
        if minute_start_s % 60 != 0:
            fail("minute_start_s must be UTC-minute aligned")

        if not self.seeded:
            return {"status": "NO_STREAM_SEED"}

        if not self.sequence_healthy:
            return {"status": "SEQUENCE_UNHEALTHY"}

        if self.recovery_required:
            return {
                "status": "RECOVERY_REQUIRED",
                "recovery_from_trade_id": self.recovery_from_trade_id,
                "recovery_target_trade_id": self.recovery_target_trade_id,
            }

        if (
            self.last_heartbeat_received_monotonic_ns is None
            or self.last_heartbeat_source_time_us is None
            or self.last_heartbeat_trade_id is None
            or self.last_heartbeat_source_time_utc is None
        ):
            return {"status": "HEARTBEAT_MISSING"}

        age_ns = (
            int(now_monotonic_ns)
            - self.last_heartbeat_received_monotonic_ns
        )
        if age_ns < 0:
            fail("monotonic clock moved backwards")

        if age_ns > HEARTBEAT_STALE_NS:
            return {
                "status": "HEARTBEAT_STALE",
                "heartbeat_age_ns": age_ns,
            }

        minute_end_s = minute_start_s + 60
        if self.last_heartbeat_source_time_us < minute_end_s * 1_000_000:
            return {"status": "HEARTBEAT_BEFORE_MINUTE_END"}

        trade = self._minute_last_trade.get(minute_start_s)
        if trade is None:
            return {"status": "NO_TRADES_IN_MINUTE"}

        if trade.trade_id > self.last_heartbeat_trade_id:
            return {"status": "HEARTBEAT_BEHIND_TARGET_TRADE"}

        state = CoinbaseCompletedMinute(
            minute_start_s=minute_start_s,
            minute_end_s=minute_end_s,
            close_price=trade.price,
            close_trade_id=trade.trade_id,
            close_trade_time_utc=trade.source_time_utc,
            heartbeat_trade_id=self.last_heartbeat_trade_id,
            heartbeat_time_utc=self.last_heartbeat_source_time_utc,
            available_monotonic_ns=int(now_monotonic_ns),
        )

        return {
            "status": "AVAILABLE",
            "state": state,
        }
