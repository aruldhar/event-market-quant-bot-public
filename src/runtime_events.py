"""Structured append-only runtime events for collector observability.

Operational events are intentionally separate from raw API archives. Raw JSONL
preserves source payloads; this module records what the collector did with those
payloads and how the run progressed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping
from uuid import uuid4


_ALLOWED_SEVERITIES = {"info", "warning", "error", "critical"}
_EVENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)+$")
_SENSITIVE_NAME_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "private_key",
    "secret",
    "signature",
    "token",
)


class RuntimeEventWriteError(RuntimeError):
    """Raised when a required runtime event cannot be persisted."""


class RuntimeEventLogger:
    """Write one durable JSON object per operational event.

    One logger belongs to one collection run. Events receive a strictly
    increasing sequence number so their local order does not depend on wall
    clock precision. Every successful append is flushed and fsynced; an append
    failure raises ``RuntimeEventWriteError`` and therefore fails closed.
    """

    SCHEMA_VERSION = "runtime_event.v1"

    def __init__(
        self,
        root_dir: str | Path,
        *,
        run_id: str,
        collector_name: str,
        started_at_utc: str,
        utc_now: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if not run_id:
            raise ValueError("run_id must be non-empty")
        if not collector_name:
            raise ValueError("collector_name must be non-empty")

        self.root_dir = Path(root_dir)
        self.run_id = run_id
        self.collector_name = collector_name
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._sequence = 0
        self._written_paths: set[Path] = set()

        started = datetime.fromisoformat(started_at_utc.replace("Z", "+00:00"))
        started = self._ensure_utc(started)
        self.output_path = (
            self.root_dir
            / f"{started.year:04d}"
            / f"{started.month:02d}"
            / f"{started.day:02d}"
            / f"{run_id}.jsonl"
        )

    @property
    def written_paths(self) -> tuple[Path, ...]:
        """Return runtime-event paths successfully written by this logger."""

        return tuple(sorted(self._written_paths))

    def emit(
        self,
        event_name: str,
        *,
        severity: str,
        message: str,
        context: Mapping[str, Any] | None = None,
        correlation: Mapping[str, Any] | None = None,
        error: Mapping[str, Any] | None = None,
    ) -> Path:
        """Persist one structured event and return its path."""

        if not _EVENT_NAME_PATTERN.fullmatch(event_name):
            raise ValueError(
                "event_name must contain lowercase dot-separated segments"
            )
        if severity not in _ALLOWED_SEVERITIES:
            raise ValueError(f"Unsupported severity: {severity!r}")
        if not isinstance(message, str) or not message:
            raise ValueError("message must be non-empty text")

        occurred_at = self._ensure_utc(self._utc_now())
        next_sequence = self._sequence + 1
        record = {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": self._id_factory(),
            "sequence": next_sequence,
            "event_name": event_name,
            "severity": severity,
            "occurred_at_utc": self._format_utc(occurred_at),
            "occurred_monotonic_ns": self._monotonic_ns(),
            "run_id": self.run_id,
            "collector": self.collector_name,
            "message": message,
            "correlation": _sanitize_mapping(correlation) if correlation else None,
            "context": _sanitize_mapping(context or {}),
            "error": _sanitize_mapping(error) if error else None,
        }

        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            serialized = json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            with self.output_path.open(
                "a",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, TypeError, ValueError) as exc:
            raise RuntimeEventWriteError(
                f"Could not persist runtime event {event_name!r}: {exc}"
            ) from exc

        self._sequence = next_sequence
        self._written_paths.add(self.output_path.resolve())
        return self.output_path

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("UTC clock function returned a naive datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _format_utc(value: datetime) -> str:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def raw_record_correlation(
    *,
    source: str,
    session_id: str,
    request_id: str,
) -> dict[str, str]:
    """Return the portable identifier tuple shared with derived CSV rows."""

    return {
        "raw_source": source,
        "raw_session_id": session_id,
        "raw_request_id": request_id,
    }


def _sanitize_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in values.items():
        string_key = str(key)
        normalized = string_key.lower().replace("-", "_")
        if any(fragment in normalized for fragment in _SENSITIVE_NAME_FRAGMENTS):
            safe[string_key] = "[REDACTED]"
        else:
            safe[string_key] = _json_safe(value)
    return safe


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)
