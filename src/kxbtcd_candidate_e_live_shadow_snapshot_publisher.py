"""Non-blocking publisher of coherent collector state for live-shadow reads."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .kxbtcd_candidate_e_live_shadow_snapshot import (
    build_live_shadow_snapshot,
    write_live_shadow_snapshot,
)


class LiveShadowSnapshotPublisherError(RuntimeError):
    pass


class LiveShadowSnapshotPublisher:
    """Publish at a bounded cadence after the collector has applied evidence.

    This object is deliberately optional.  Its caller must catch its errors so
    a dashboard-side artifact failure cannot affect a read-only soak's market
    evidence lifecycle.
    """

    def __init__(self, *, run_id: str, output_path: str | Path,
                 minimum_interval_ns: int = 1_000_000_000):
        if not str(run_id).strip() or minimum_interval_ns <= 0:
            raise LiveShadowSnapshotPublisherError("publisher configuration is invalid")
        self.run_id = str(run_id)
        self.output_path = Path(output_path)
        self.minimum_interval_ns = int(minimum_interval_ns)
        self._sequence = 0
        self._last_published_ns: int | None = None

    @staticmethod
    def _timestamp_ms(received_utc: str) -> int:
        try:
            parsed = datetime.fromisoformat(received_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LiveShadowSnapshotPublisherError("publisher received UTC is invalid") from exc
        if parsed.tzinfo is None:
            raise LiveShadowSnapshotPublisherError("publisher received UTC lacks timezone")
        return int(parsed.astimezone(timezone.utc).timestamp() * 1000)

    def publish_if_due(self, *, core, received_utc: str, received_monotonic_ns: int) -> bool:
        """Write only if full causal state exists and the sample cadence allows it."""
        now_ns = int(received_monotonic_ns)
        if self._last_published_ns is not None and now_ns - self._last_published_ns < self.minimum_interval_ns:
            return False
        event = getattr(core, "current_event", None)
        candle = getattr(core, "v2_coinbase_rest_candle", None)
        binding = getattr(getattr(core, "connections", None), "current_kalshi", None)
        if event is None or candle is None or binding is None or not binding.connected or not binding.cache.all_ready():
            return False
        timestamp_ms = self._timestamp_ms(received_utc)
        books = {
            ticker: binding.cache.books[ticker].to_book_state(timestamp_ms)
            for ticker in binding.cache.subscribed_tickers
        }
        snapshot = build_live_shadow_snapshot(
            run_id=self.run_id, snapshot_sequence=self._sequence + 1,
            generated_utc=received_utc, generated_monotonic_ns=now_ns,
            event_ladder=event, candle=candle, books=books,
        )
        write_live_shadow_snapshot(snapshot=snapshot, output_path=self.output_path)
        self._sequence += 1
        self._last_published_ns = now_ns
        return True
