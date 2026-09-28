"""Raw-first public HTTP client for venue-neutral census discovery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Callable, Mapping

import requests

from .raw_json_log import RawJsonlRecorder, RawLogWriteError
from .runtime_events import RuntimeEventLogger, raw_record_correlation


class PublicCensusHttpError(RuntimeError):
    """Raised when public census HTTP data cannot be safely archived and parsed."""


@dataclass(frozen=True)
class PublicRawReference:
    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class PublicJsonResponse:
    payload: Any
    raw_record: PublicRawReference
    request_started_at_utc: str
    request_started_monotonic_ns: int
    received_at_utc: str
    received_monotonic_ns: int


class PublicCensusHttpClient:
    """GET-only client that archives every HTTP attempt before returning data.

    HTTP 429 responses are preserved as distinct raw exchanges and retried with
    bounded exponential backoff. Exhausted retries still fail closed. No other
    HTTP status is automatically retried in v1.
    """

    def __init__(
        self,
        *,
        base_url: str,
        source_name: str,
        raw_root: str | Path,
        timeout_seconds: float = 10.0,
        max_rate_limit_retries: int = 4,
        rate_limit_backoff_seconds: float = 0.5,
        raw_recorder: RawJsonlRecorder | None = None,
        runtime_events: RuntimeEventLogger | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("Public census HTTP base_url must use https")
        if max_rate_limit_retries < 0:
            raise ValueError("max_rate_limit_retries must be nonnegative")
        if rate_limit_backoff_seconds < 0:
            raise ValueError("rate_limit_backoff_seconds must be nonnegative")
        self.base_url = base_url.rstrip("/")
        self.source_name = source_name
        self.timeout_seconds = timeout_seconds
        self.max_rate_limit_retries = max_rate_limit_retries
        self.rate_limit_backoff_seconds = rate_limit_backoff_seconds
        self.raw_recorder = raw_recorder or RawJsonlRecorder(
            raw_root, source_name=source_name
        )
        self.runtime_events = runtime_events
        self._sleep = sleep_fn or time.sleep
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "event-market-quant-bot-read-only-census/0.1"}
        )

    def attach_runtime_event_logger(self, logger: RuntimeEventLogger) -> None:
        self.runtime_events = logger

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        top_level_container: str = "object",
    ) -> PublicJsonResponse:
        if not path.startswith("/"):
            raise ValueError("Public census path must start with '/'")
        if top_level_container not in {"object", "array"}:
            raise ValueError(
                "top_level_container must be either 'object' or 'array'"
            )

        url = f"{self.base_url}{path}"
        for attempt_index in range(self.max_rate_limit_retries + 1):
            result, status_code = self._attempt_get_json(
                path=path,
                url=url,
                params=params,
                attempt_index=attempt_index,
                top_level_container=top_level_container,
            )
            if result is not None:
                return result

            # _attempt_get_json returns None only for HTTP 429.
            assert status_code == 429
            if attempt_index >= self.max_rate_limit_retries:
                raise PublicCensusHttpError(
                    f"GET {url} returned HTTP 429 after "
                    f"{attempt_index + 1} archived attempts"
                )

            delay_seconds = self.rate_limit_backoff_seconds * (2 ** attempt_index)
            self._emit(
                "api.request.retry.scheduled",
                severity="warning",
                message="Public census request was rate-limited; retry scheduled",
                context={
                    "method": "GET",
                    "path": path,
                    "status_code": 429,
                    "retry_number": attempt_index + 1,
                    "max_retries": self.max_rate_limit_retries,
                    "delay_seconds": delay_seconds,
                    "retry_policy": "bounded_exponential_backoff",
                },
            )
            self._sleep(delay_seconds)

        raise AssertionError("unreachable public census retry state")

    def _attempt_get_json(
        self,
        *,
        path: str,
        url: str,
        params: Mapping[str, Any] | None,
        attempt_index: int,
        top_level_container: str,
    ) -> tuple[PublicJsonResponse | None, int | None]:
        context = self.raw_recorder.begin_request(
            method="GET",
            base_url=self.base_url,
            path=path,
            params=params,
        )

        try:
            response = self.session.get(
                url, params=dict(params or {}), timeout=self.timeout_seconds
            )
        except requests.RequestException as exc:
            received_at_utc, received_monotonic_ns = (
                self.raw_recorder.capture_receive_time()
            )
            try:
                self.raw_recorder.record_transport_error(
                    context=context,
                    received_at_utc=received_at_utc,
                    received_monotonic_ns=received_monotonic_ns,
                    exc=exc,
                )
            except RawLogWriteError as log_exc:
                self._emit(
                    "api.raw.persistence.failed",
                    severity="critical",
                    message="Public census transport error could not be raw-archived",
                    context={"method": "GET", "path": path},
                    error={"type": type(log_exc).__name__, "message": str(log_exc)},
                )
                raise PublicCensusHttpError(
                    f"GET {url} failed and raw persistence also failed: {log_exc}"
                ) from log_exc
            raw_ref = self._raw_reference(context.request_id)
            self._emit(
                "api.request.failed",
                severity="warning",
                message="Public census request failed before an HTTP response arrived",
                context={"method": "GET", "path": path, "retryable": True},
                raw_ref=raw_ref,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise PublicCensusHttpError(f"GET {url} failed: {exc}") from exc

        received_at_utc, received_monotonic_ns = (
            self.raw_recorder.capture_receive_time()
        )
        payload: Any | None = None
        json_parse_error: str | None = None
        try:
            payload = response.json()
        except ValueError as exc:
            json_parse_error = str(exc)

        expected_top_level_type = (
            dict if top_level_container == "object" else list
        )
        expected_top_level_name = top_level_container

        error: dict[str, Any] | None = None
        if not response.ok:
            error = {
                "stage": "http_status",
                "type": "HTTPError",
                "message": f"HTTP {response.status_code} {response.reason}",
            }
        elif json_parse_error is not None:
            error = {
                "stage": "json_decode",
                "type": "JSONDecodeError",
                "message": json_parse_error,
            }
        elif not isinstance(payload, expected_top_level_type):
            error = {
                "stage": "shape_validation",
                "type": "UnexpectedJSONShape",
                "message": (
                    "Expected top-level JSON "
                    f"{expected_top_level_name}"
                ),
            }

        try:
            self.raw_recorder.record_response(
                context=context,
                response=response,
                received_at_utc=received_at_utc,
                received_monotonic_ns=received_monotonic_ns,
                parsed_json=payload,
                json_parse_error=json_parse_error,
                error=error,
            )
        except RawLogWriteError as exc:
            self._emit(
                "api.raw.persistence.failed",
                severity="critical",
                message="Public census HTTP response could not be raw-archived",
                context={"method": "GET", "path": path, "status_code": response.status_code},
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise PublicCensusHttpError(
                f"GET {url} returned data but raw persistence failed: {exc}"
            ) from exc

        raw_ref = self._raw_reference(context.request_id)
        if error is None:
            self._emit(
                "api.request.succeeded",
                severity="info",
                message="Public census HTTP response was archived",
                context={
                    "method": "GET",
                    "path": path,
                    "status_code": response.status_code,
                    "attempt_index": attempt_index,
                    "elapsed_monotonic_ns": (
                        received_monotonic_ns - context.started_monotonic_ns
                    ),
                },
                raw_ref=raw_ref,
            )
        else:
            retryable_429 = response.status_code == 429
            will_retry = (
                retryable_429 and attempt_index < self.max_rate_limit_retries
            )
            self._emit(
                "api.request.failed",
                severity="warning" if will_retry else "error",
                message="Public census HTTP response was archived but rejected",
                context={
                    "method": "GET",
                    "path": path,
                    "status_code": response.status_code,
                    "attempt_index": attempt_index,
                    "failure_stage": error["stage"],
                    "retryable": retryable_429,
                    "will_retry": will_retry,
                },
                raw_ref=raw_ref,
                error={"type": error["type"], "message": error["message"]},
            )

        if response.status_code == 429:
            return None, 429
        if not response.ok:
            raise PublicCensusHttpError(
                f"GET {url} returned HTTP {response.status_code}"
            )
        if json_parse_error is not None:
            raise PublicCensusHttpError(f"GET {url} did not return valid JSON")
        if not isinstance(payload, expected_top_level_type):
            raise PublicCensusHttpError(
                f"GET {url} returned an unexpected top-level JSON shape"
            )

        return (
            PublicJsonResponse(
                payload=payload,
                raw_record=raw_ref,
                request_started_at_utc=context.started_at_utc,
                request_started_monotonic_ns=context.started_monotonic_ns,
                received_at_utc=received_at_utc,
                received_monotonic_ns=received_monotonic_ns,
            ),
            response.status_code,
        )

    def _raw_reference(self, request_id: str) -> PublicRawReference:
        return PublicRawReference(
            source=self.raw_recorder.source_name,
            session_id=self.raw_recorder.session_id,
            request_id=request_id,
        )

    def _emit(
        self,
        event_name: str,
        *,
        severity: str,
        message: str,
        context: dict[str, Any] | None = None,
        raw_ref: PublicRawReference | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self.runtime_events is None:
            return
        correlation = None
        if raw_ref is not None:
            correlation = raw_record_correlation(
                source=raw_ref.source,
                session_id=raw_ref.session_id,
                request_id=raw_ref.request_id,
            )
        self.runtime_events.emit(
            event_name,
            severity=severity,
            message=message,
            context=context,
            correlation=correlation,
            error=error,
        )
