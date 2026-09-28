"""Production-shaped append-only runtime raw journal.

Every source payload must be flushed from Python userspace before the caller
transforms it. Durable fsync occurs at least once per configured interval and
again on close or explicit force_fsync().

No credentials, request headers, orders, or execution behavior belong here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from typing import Any, Mapping

from .kxbtcd_candidate_e_raw_journal_security import (
    RawJournalSecurityError,
    sanitize_request_identity,
)


ALLOWED_RUNTIME_SOURCES = frozenset({
    "coinbase_exchange_ws",
    "coinbase_exchange_rest",
    "kalshi_production_ws",
    "kalshi_production_rest",
})


class RuntimeRawJournalError(RuntimeError):
    pass


class RuntimeRawJournal:
    def __init__(
        self,
        path: str | Path,
        *,
        fsync_interval_ns: int = 1_000_000_000,
    ) -> None:
        if fsync_interval_ns <= 0:
            raise RuntimeRawJournalError(
                "fsync_interval_ns must be positive"
            )

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.fsync_interval_ns = int(fsync_interval_ns)
        self._lock = threading.Lock()
        self._file = self.path.open(
            "a",
            encoding="utf-8",
            newline="\n",
        )
        self._last_fsync_ns: int | None = None
        self._last_append_ns: int | None = None
        self._closed = False
        self.record_count = 0

    def append(
        self,
        *,
        source: str,
        transport: str,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        request_identity: Mapping[str, Any] | None = None,
    ) -> None:
        if self._closed:
            raise RuntimeRawJournalError("journal already closed")

        if source not in ALLOWED_RUNTIME_SOURCES:
            raise RuntimeRawJournalError(
                f"unregistered runtime raw source: {source}"
            )

        ns = int(received_monotonic_ns)

        if (
            self._last_append_ns is not None
            and ns < self._last_append_ns
        ):
            raise RuntimeRawJournalError(
                "local monotonic receive time moved backwards"
            )

        try:
            safe_request_identity = sanitize_request_identity(request_identity)
        except RawJournalSecurityError as exc:
            raise RuntimeRawJournalError(str(exc)) from exc

        record = {
            "schema_version": "candidate_e_runtime_raw_record.v1",
            "source": source,
            "transport": str(transport),
            "received_utc": str(received_utc),
            "received_monotonic_ns": ns,
            "request_identity": safe_request_identity,
            "raw_text": str(raw_text),
        }

        line = (
            json.dumps(
                record,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

        with self._lock:
            self._file.write(line)

            # Required architecture invariant:
            # raw payload leaves Python buffering before transformation.
            self._file.flush()

            self.record_count += 1
            self._last_append_ns = ns

            if (
                self._last_fsync_ns is None
                or ns - self._last_fsync_ns
                >= self.fsync_interval_ns
            ):
                os.fsync(self._file.fileno())
                self._last_fsync_ns = ns

    def force_fsync(self) -> None:
        if self._closed:
            raise RuntimeRawJournalError("journal already closed")

        with self._lock:
            self._file.flush()
            os.fsync(self._file.fileno())

            if self._last_append_ns is not None:
                self._last_fsync_ns = self._last_append_ns

    def fsync_if_due(self, now_monotonic_ns: int) -> bool:
        """Durably flush an idle active segment once its deadline arrives."""
        if self._closed:
            raise RuntimeRawJournalError("journal already closed")
        now = int(now_monotonic_ns)
        with self._lock:
            if self._last_fsync_ns is None:
                raise RuntimeRawJournalError("invalid idle fsync monotonic time")
            # Source workers share this journal through the runtime core. A
            # worker can sample ``now`` just before another worker appends and
            # fsyncs the same journal. That ordering is not a clock
            # regression; defer until a later tick rather than failing the
            # read-only soak.
            if now < self._last_fsync_ns:
                return False
            if now - self._last_fsync_ns < self.fsync_interval_ns:
                return False
            self._file.flush()
            os.fsync(self._file.fileno())
            self._last_fsync_ns = now
            return True

    def close(self) -> None:
        if self._closed:
            return

        with self._lock:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._file.close()
            self._closed = True

    def __enter__(self) -> "RuntimeRawJournal":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
