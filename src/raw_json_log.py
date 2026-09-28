"""Append-only raw HTTP exchange logging for market-data collection.

The raw archive is deliberately written before venue-specific transformation.
Each JSON Lines record contains the request context, local timing, response
metadata, the original response body text, and any transport/HTTP/JSON error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import requests


_SAFE_RESPONSE_HEADER_NAMES = {
    "cache-control",
    "content-length",
    "content-type",
    "date",
    "etag",
    "expires",
    "last-modified",
    "request-id",
    "retry-after",
    "server",
    "traceparent",
    "tracestate",
    "x-request-id",
}
_SAFE_RESPONSE_HEADER_PREFIXES = ("ratelimit-", "x-ratelimit-")
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


class RawLogWriteError(RuntimeError):
    """Raised when a required raw-data record cannot be persisted."""


@dataclass(frozen=True)
class RawRequestContext:
    """Immutable request identity and start-time measurements."""

    request_id: str
    method: str
    base_url: str
    path: str
    params: dict[str, Any]
    started_at_utc: str
    started_monotonic_ns: int


class RawJsonlRecorder:
    """Write one append-only JSON object per HTTP exchange.

    Files are grouped by the UTC date on which the request started. One client
    run uses one session identifier, producing paths such as::

        data/raw/kalshi_rest/2026/08/03/
            kalshi_rest_20260803T080500000000Z_ab12cd34.jsonl

    The recorder is intentionally small and synchronous. If persistence fails,
    it raises ``RawLogWriteError`` so callers do not continue transforming data
    that was not archived.
    """

    SCHEMA_VERSION = "raw_http_exchange.v1"

    def __init__(
        self,
        root_dir: str | Path,
        *,
        source_name: str,
        utc_now: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.source_name = source_name
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._id_factory = id_factory or (lambda: uuid4().hex)

        created_at = self._ensure_utc(self._utc_now())
        compact_time = created_at.strftime("%Y%m%dT%H%M%S%fZ")
        self.session_id = f"{source_name}_{compact_time}_{self._id_factory()[:8]}"
        self._written_paths: set[Path] = set()

    @property
    def written_paths(self) -> tuple[Path, ...]:
        """Return every raw JSONL path successfully written by this session."""

        return tuple(sorted(self._written_paths))

    def begin_request(
        self,
        *,
        method: str,
        base_url: str,
        path: str,
        params: Mapping[str, Any] | None,
    ) -> RawRequestContext:
        """Capture request identity plus wall-clock and monotonic start times."""

        started_at = self._ensure_utc(self._utc_now())
        return RawRequestContext(
            request_id=self._id_factory(),
            method=method.upper(),
            base_url=base_url,
            path=path,
            params=self._json_safe_dict(params or {}),
            started_at_utc=self._format_utc(started_at),
            started_monotonic_ns=self._monotonic_ns(),
        )

    def capture_receive_time(self) -> tuple[str, int]:
        """Capture the local receive wall clock and monotonic clock together."""

        received_at = self._ensure_utc(self._utc_now())
        return self._format_utc(received_at), self._monotonic_ns()

    def record_response(
        self,
        *,
        context: RawRequestContext,
        response: requests.Response,
        received_at_utc: str,
        received_monotonic_ns: int,
        parsed_json: Any | None,
        json_parse_error: str | None,
        error: dict[str, Any] | None,
    ) -> Path:
        """Persist a completed HTTP response, including non-success responses."""

        raw_bytes = response.content
        body_text = response.text
        record = self._base_record(
            context=context,
            received_at_utc=received_at_utc,
            received_monotonic_ns=received_monotonic_ns,
        )
        record["response"] = {
            "status_code": response.status_code,
            "reason": response.reason,
            "url": self._sanitize_url(response.url),
            "headers": self._safe_response_headers(response.headers),
            "body_text": body_text,
            "body_size_bytes": len(raw_bytes),
            "body_sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "json_parse_error": json_parse_error,
        }
        record["source_timestamps"] = extract_source_timestamps(parsed_json)
        record["error"] = error
        return self._append_record(context, record)

    def record_transport_error(
        self,
        *,
        context: RawRequestContext,
        received_at_utc: str,
        received_monotonic_ns: int,
        exc: BaseException,
    ) -> Path:
        """Persist an attempted request that failed before a response arrived."""

        record = self._base_record(
            context=context,
            received_at_utc=received_at_utc,
            received_monotonic_ns=received_monotonic_ns,
        )
        record["response"] = None
        record["source_timestamps"] = []
        record["error"] = {
            "stage": "transport",
            "type": type(exc).__name__,
            "message": str(exc),
        }
        return self._append_record(context, record)

    def _base_record(
        self,
        *,
        context: RawRequestContext,
        received_at_utc: str,
        received_monotonic_ns: int,
    ) -> dict[str, Any]:
        elapsed_ns = received_monotonic_ns - context.started_monotonic_ns
        return {
            "schema_version": self.SCHEMA_VERSION,
            "source": self.source_name,
            "session_id": self.session_id,
            "request": {
                "request_id": context.request_id,
                "method": context.method,
                "base_url": context.base_url,
                "path": context.path,
                "params": context.params,
                "started_at_utc": context.started_at_utc,
                "started_monotonic_ns": context.started_monotonic_ns,
            },
            "timing": {
                "received_at_utc": received_at_utc,
                "received_monotonic_ns": received_monotonic_ns,
                "elapsed_monotonic_ns": elapsed_ns,
            },
        }

    def _append_record(
        self,
        context: RawRequestContext,
        record: dict[str, Any],
    ) -> Path:
        try:
            started_at = datetime.fromisoformat(
                context.started_at_utc.replace("Z", "+00:00")
            )
            output_dir = (
                self.root_dir
                / f"{started_at.year:04d}"
                / f"{started_at.month:02d}"
                / f"{started_at.day:02d}"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{self.session_id}.jsonl"

            serialized = json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            with output_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
            self._written_paths.add(output_path.resolve())
            return output_path
        except (OSError, TypeError, ValueError) as exc:
            raise RawLogWriteError(f"Could not persist raw API record: {exc}") from exc

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("UTC clock function returned a naive datetime")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _format_utc(value: datetime) -> str:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")

    @staticmethod
    def _json_safe_dict(values: Mapping[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in values.items():
            string_key = str(key)
            if RawJsonlRecorder._is_sensitive_name(string_key):
                safe[string_key] = "[REDACTED]"
            else:
                safe[string_key] = RawJsonlRecorder._json_safe_value(value)
        return safe

    @staticmethod
    def _safe_response_headers(
        headers: Mapping[str, Any],
    ) -> dict[str, str]:
        safe: dict[str, str] = {}
        for key, value in headers.items():
            normalized = str(key).lower()
            if (
                normalized in _SAFE_RESPONSE_HEADER_NAMES
                or normalized.startswith(_SAFE_RESPONSE_HEADER_PREFIXES)
            ):
                safe[str(key)] = str(value)
        return safe

    @staticmethod
    def _sanitize_url(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        parts = urlsplit(text)
        safe_query = []
        for key, item in parse_qsl(parts.query, keep_blank_values=True):
            safe_value = (
                "[REDACTED]"
                if RawJsonlRecorder._is_sensitive_name(key)
                else item
            )
            safe_query.append((key, safe_value))
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(safe_query),
                parts.fragment,
            )
        )

    @staticmethod
    def _is_sensitive_name(value: str) -> bool:
        normalized = value.lower().replace("-", "_")
        return any(fragment in normalized for fragment in _SENSITIVE_NAME_FRAGMENTS)

    @staticmethod
    def _json_safe_value(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return RawJsonlRecorder._json_safe_dict(value)
        if isinstance(value, (list, tuple)):
            return [RawJsonlRecorder._json_safe_value(item) for item in value]
        return str(value)


def extract_source_timestamps(payload: Any) -> list[dict[str, Any]]:
    """Index timestamp-like source fields without changing the raw payload.

    This helper is intentionally descriptive rather than interpretive: values
    are copied exactly as supplied, and no attempt is made to decide which
    timestamp is authoritative for settlement or market state.
    """

    found: list[dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}"
                normalized_key = str(key).lower()
                if _looks_like_timestamp_key(normalized_key) and not isinstance(
                    item, (dict, list)
                ):
                    found.append({"json_path": child_path, "value": item})
                visit(item, child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(payload, "$")
    return found


def _looks_like_timestamp_key(key: str) -> bool:
    return (
        key in {"time", "timestamp", "ts"}
        or key.endswith("_time")
        or key.endswith("_timestamp")
        or key.endswith("_ts")
    )
