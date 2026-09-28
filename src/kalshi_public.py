"""Small read-only client for Kalshi's public market-data endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import requests

from .config import (
    BTC_KEYWORDS,
    DEFAULT_PAGE_LIMIT,
    DEFAULT_RAW_LOG_ROOT,
    DEFAULT_TIMEOUT_SECONDS,
    KALSHI_PUBLIC_BASE_URL,
)
from .raw_json_log import RawJsonlRecorder, RawLogWriteError
from .runtime_events import (
    RuntimeEventLogger,
    raw_record_correlation,
)


class KalshiPublicAPIError(RuntimeError):
    """Raised when a public Kalshi API request fails or returns malformed data."""


class EndpointValidationError(KalshiPublicAPIError):
    """Raised when an archived payload violates an endpoint-specific shape."""


@dataclass(frozen=True)
class RawRecordReference:
    """Identity of one successfully persisted raw API exchange."""

    source: str
    session_id: str
    request_id: str


@dataclass(frozen=True)
class SourcedApiResponse:
    """Parsed endpoint payload paired with its exact raw-record identity."""

    payload: dict[str, Any]
    raw_record: RawRecordReference


@dataclass(frozen=True)
class SourcedOrderbook:
    """Order-book data paired with the raw API record that produced it."""

    orderbook: dict[str, Any]
    raw_record: RawRecordReference


@dataclass(frozen=True)
class BestPrices:
    """Best bid and ask prices for both outcomes, expressed in dollars."""

    yes_bid: Decimal | None
    yes_ask: Decimal | None
    no_bid: Decimal | None
    no_ask: Decimal | None

    @property
    def yes_spread(self) -> Decimal | None:
        if self.yes_bid is None or self.yes_ask is None:
            return None
        return self.yes_ask - self.yes_bid

    @property
    def no_spread(self) -> Decimal | None:
        if self.no_bid is None or self.no_ask is None:
            return None
        return self.no_ask - self.no_bid


class KalshiPublicClient:
    """Read-only wrapper around Kalshi's public REST endpoints.

    Raw response logging is enabled by default. A successful response is not
    returned to downstream transformation code unless its raw exchange record
    has first been persisted.
    """

    def __init__(
        self,
        base_url: str = KALSHI_PUBLIC_BASE_URL,
        *,
        raw_log_root: str | Path = DEFAULT_RAW_LOG_ROOT,
        raw_recorder: RawJsonlRecorder | None = None,
        runtime_events: RuntimeEventLogger | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "kalshi-btc-bot-learning-project/0.2"})
        self.raw_recorder = raw_recorder or RawJsonlRecorder(
            raw_log_root,
            source_name="kalshi_public_rest",
        )
        self.runtime_events = runtime_events

    def attach_runtime_event_logger(self, logger: RuntimeEventLogger) -> None:
        """Attach the run logger before any network request is attempted."""

        self.runtime_events = logger

    def _emit_runtime_event(
        self,
        event_name: str,
        *,
        severity: str,
        message: str,
        context: dict[str, Any] | None = None,
        raw_record: RawRecordReference | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self.runtime_events is None:
            return
        correlation = None
        if raw_record is not None:
            correlation = raw_record_correlation(
                source=raw_record.source,
                session_id=raw_record.session_id,
                request_id=raw_record.request_id,
            )
        self.runtime_events.emit(
            event_name,
            severity=severity,
            message=message,
            context=context,
            correlation=correlation,
            error=error,
        )

    def _raw_reference(self, request_id: str) -> RawRecordReference:
        return RawRecordReference(
            source=self.raw_recorder.source_name,
            session_id=self.raw_recorder.session_id,
            request_id=request_id,
        )

    def _get_with_lineage(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> SourcedApiResponse:
        url = f"{self.base_url}{path}"
        request_context = self.raw_recorder.begin_request(
            method="GET",
            base_url=self.base_url,
            path=path,
            params=params,
        )

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            received_at_utc, received_monotonic_ns = (
                self.raw_recorder.capture_receive_time()
            )
            try:
                self.raw_recorder.record_transport_error(
                    context=request_context,
                    received_at_utc=received_at_utc,
                    received_monotonic_ns=received_monotonic_ns,
                    exc=exc,
                )
            except RawLogWriteError as log_exc:
                self._emit_runtime_event(
                    "api.raw.persistence.failed",
                    severity="critical",
                    message="A transport failure occurred and its raw record could not be saved",
                    context={
                        "method": "GET",
                        "path": path,
                        "request_id": request_context.request_id,
                        "failure_stage": "transport",
                    },
                    error={
                        "type": type(log_exc).__name__,
                        "message": str(log_exc),
                    },
                )
                raise KalshiPublicAPIError(
                    f"GET {url} failed and its raw error record could not be saved: "
                    f"{log_exc}"
                ) from log_exc

            raw_record = self._raw_reference(request_context.request_id)
            self._emit_runtime_event(
                "api.request.failed",
                severity="warning",
                message="Public API request failed before an HTTP response arrived",
                context={
                    "method": "GET",
                    "path": path,
                    "failure_stage": "transport",
                    "retryable": True,
                    "elapsed_monotonic_ns": (
                        received_monotonic_ns
                        - request_context.started_monotonic_ns
                    ),
                },
                raw_record=raw_record,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise KalshiPublicAPIError(f"GET {url} failed: {exc}") from exc

        received_at_utc, received_monotonic_ns = (
            self.raw_recorder.capture_receive_time()
        )

        payload: Any | None = None
        json_parse_error: str | None = None
        try:
            payload = response.json()
        except ValueError as exc:
            json_parse_error = str(exc)

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
        elif not isinstance(payload, dict):
            error = {
                "stage": "shape_validation",
                "type": "UnexpectedJSONShape",
                "message": "Expected the top-level JSON value to be an object",
            }

        try:
            self.raw_recorder.record_response(
                context=request_context,
                response=response,
                received_at_utc=received_at_utc,
                received_monotonic_ns=received_monotonic_ns,
                parsed_json=payload,
                json_parse_error=json_parse_error,
                error=error,
            )
        except RawLogWriteError as exc:
            self._emit_runtime_event(
                "api.raw.persistence.failed",
                severity="critical",
                message="An HTTP response arrived but its required raw record could not be saved",
                context={
                    "method": "GET",
                    "path": path,
                    "request_id": request_context.request_id,
                    "status_code": response.status_code,
                    "failure_stage": "raw_persistence",
                },
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            raise KalshiPublicAPIError(
                f"GET {url} returned data, but the required raw record could not "
                f"be saved: {exc}"
            ) from exc

        raw_record = self._raw_reference(request_context.request_id)
        elapsed_monotonic_ns = (
            received_monotonic_ns - request_context.started_monotonic_ns
        )
        if error is None:
            self._emit_runtime_event(
                "api.request.succeeded",
                severity="info",
                message="Public API response was archived and passed transport-level validation",
                context={
                    "method": "GET",
                    "path": path,
                    "status_code": response.status_code,
                    "elapsed_monotonic_ns": elapsed_monotonic_ns,
                },
                raw_record=raw_record,
            )
        else:
            retryable = (
                error["stage"] == "http_status"
                and _is_retryable_http_status(response.status_code)
            )
            self._emit_runtime_event(
                "api.request.failed",
                severity="warning" if retryable else "error",
                message="Public API response was archived but failed request validation",
                context={
                    "method": "GET",
                    "path": path,
                    "status_code": response.status_code,
                    "failure_stage": error["stage"],
                    "retryable": retryable,
                    "elapsed_monotonic_ns": elapsed_monotonic_ns,
                },
                raw_record=raw_record,
                error={"type": error["type"], "message": error["message"]},
            )

        if not response.ok:
            try:
                response.raise_for_status()
            except requests.RequestException as exc:
                raise KalshiPublicAPIError(f"GET {url} failed: {exc}") from exc

        if json_parse_error is not None:
            raise KalshiPublicAPIError(f"GET {url} did not return valid JSON")

        if not isinstance(payload, dict):
            raise KalshiPublicAPIError(f"GET {url} returned an unexpected JSON shape")

        return SourcedApiResponse(
            payload=payload,
            raw_record=raw_record,
        )

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return only the parsed payload for existing callers."""

        return self._get_with_lineage(path, params=params).payload

    def list_open_markets(
        self,
        *,
        series_ticker: str | None = None,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """Return open markets, optionally limited to one recurring series.

        Args:
            series_ticker:
                Stable Kalshi series identifier, such as ``KXBTC15M``.
                When provided, Kalshi filters the response server-side.
            max_pages:
                Safety guard preventing malformed pagination from creating
                an infinite request loop.

        Returns:
            A list of open Kalshi market objects.
        """

        markets: list[dict[str, Any]] = []
        cursor: str | None = None

        for _ in range(max_pages):
            params: dict[str, Any] = {
                "status": "open",
                "limit": DEFAULT_PAGE_LIMIT,
            }

            if series_ticker:
                params["series_ticker"] = series_ticker

            if cursor:
                params["cursor"] = cursor

            response = self._get_with_lineage("/markets", params=params)
            payload = response.payload
            page_markets = payload.get("markets")

            if not isinstance(page_markets, list):
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="list_open_markets",
                    validation_code="markets_field_not_list",
                    field="markets",
                    expected="list",
                    actual=page_markets,
                )

            for index, market in enumerate(page_markets):
                if not isinstance(market, dict):
                    self._raise_endpoint_validation(
                        response=response,
                        endpoint="list_open_markets",
                        validation_code="market_item_not_object",
                        field=f"markets[{index}]",
                        expected="object",
                        actual=market,
                    )
                markets.append(market)

            cursor = payload.get("cursor")
            if cursor is not None and not isinstance(cursor, str):
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="list_open_markets",
                    validation_code="cursor_not_text_or_null",
                    field="cursor",
                    expected="text or null",
                    actual=cursor,
                )
            if not cursor:
                break

        return markets

    def get_market(self, ticker: str) -> dict[str, Any]:
        response = self._get_with_lineage(f"/markets/{ticker}")
        market = response.payload.get("market")
        if not isinstance(market, dict):
            self._raise_endpoint_validation(
                response=response,
                endpoint="get_market",
                validation_code="market_field_not_object",
                field="market",
                expected="object",
                actual=market,
            )
        return market

    def get_orderbook_with_lineage(self, ticker: str) -> SourcedOrderbook:
        """Return an order book and the exact raw record that produced it."""

        response = self._get_with_lineage(f"/markets/{ticker}/orderbook")
        orderbook = response.payload.get("orderbook_fp")
        if not isinstance(orderbook, dict):
            self._raise_endpoint_validation(
                response=response,
                endpoint="get_orderbook",
                validation_code="orderbook_field_not_object",
                field="orderbook_fp",
                expected="object",
                actual=orderbook,
            )

        for side_name in ("yes_dollars", "no_dollars"):
            self._validate_orderbook_side(
                response=response,
                orderbook=orderbook,
                side_name=side_name,
            )

        return SourcedOrderbook(
            orderbook=orderbook,
            raw_record=response.raw_record,
        )

    def get_orderbook(self, ticker: str) -> dict[str, Any]:
        """Return only the order-book data for existing callers."""

        return self.get_orderbook_with_lineage(ticker).orderbook

    def _validate_orderbook_side(
        self,
        *,
        response: SourcedApiResponse,
        orderbook: dict[str, Any],
        side_name: str,
    ) -> None:
        levels = orderbook.get(side_name)
        if levels is None:
            return
        if not isinstance(levels, list):
            self._raise_endpoint_validation(
                response=response,
                endpoint="get_orderbook",
                validation_code="orderbook_side_not_list",
                field=f"orderbook_fp.{side_name}",
                expected="list",
                actual=levels,
            )
        for index, level in enumerate(levels):
            if not isinstance(level, list) or len(level) != 2:
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="get_orderbook",
                    validation_code="orderbook_level_invalid_shape",
                    field=f"orderbook_fp.{side_name}[{index}]",
                    expected="two-item price and quantity array",
                    actual=level,
                )
            if not all(isinstance(value, str) for value in level):
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="get_orderbook",
                    validation_code="orderbook_level_not_fixed_point_strings",
                    field=f"orderbook_fp.{side_name}[{index}]",
                    expected="fixed-point price and quantity strings",
                    actual=level,
                )
            try:
                price = Decimal(level[0])
                quantity = Decimal(level[1])
            except (InvalidOperation, ValueError):
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="get_orderbook",
                    validation_code="orderbook_level_not_numeric",
                    field=f"orderbook_fp.{side_name}[{index}]",
                    expected="numeric fixed-point strings",
                    actual=level,
                )
            if not price.is_finite() or not quantity.is_finite():
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="get_orderbook",
                    validation_code="orderbook_level_not_finite",
                    field=f"orderbook_fp.{side_name}[{index}]",
                    expected="finite numeric price and quantity values",
                    actual=level,
                )

    def _raise_endpoint_validation(
        self,
        *,
        response: SourcedApiResponse,
        endpoint: str,
        validation_code: str,
        field: str,
        expected: str,
        actual: Any,
    ) -> None:
        message = (
            f"Endpoint {endpoint} field {field!r} expected {expected}; "
            f"observed {type(actual).__name__}"
        )
        self._emit_runtime_event(
            "endpoint.validation.failed",
            severity="error",
            message=message,
            context={
                "endpoint": endpoint,
                "validation_code": validation_code,
                "field": field,
                "expected": expected,
                "actual_type": type(actual).__name__,
            },
            raw_record=response.raw_record,
            error={
                "type": "EndpointValidationError",
                "message": message,
            },
        )
        raise EndpointValidationError(message)


def _is_retryable_http_status(status_code: int) -> bool:
    return status_code in {408, 425, 429} or 500 <= status_code < 600


def is_bitcoin_market(market: dict[str, Any]) -> bool:
    """Heuristic filter for Bitcoin-related markets."""

    searchable_fields: Iterable[Any] = (
        market.get("ticker"),
        market.get("event_ticker"),
        market.get("series_ticker"),
        market.get("title"),
        market.get("subtitle"),
        market.get("yes_sub_title"),
        market.get("no_sub_title"),
    )
    text = " ".join(str(value) for value in searchable_fields if value).lower()
    return any(keyword in text for keyword in BTC_KEYWORDS)


def extract_best_prices(orderbook: dict[str, Any]) -> BestPrices:
    """Convert Kalshi's bid-only orderbook into best bid/ask quotes.

    Kalshi returns ascending arrays of [price_dollars, count_fp].
    The highest bid is therefore the final element. A YES ask is the
    complement of the best NO bid, and vice versa.
    """

    yes_levels = orderbook.get("yes_dollars") or []
    no_levels = orderbook.get("no_dollars") or []

    yes_bid = Decimal(yes_levels[-1][0]) if yes_levels else None
    no_bid = Decimal(no_levels[-1][0]) if no_levels else None
    yes_ask = Decimal("1.0000") - no_bid if no_bid is not None else None
    no_ask = Decimal("1.0000") - yes_bid if yes_bid is not None else None

    return BestPrices(
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
    )
