"""Raw-first Coinbase BTC-USD REST trade recovery paginator.

Coinbase Exchange returns the latest trades by default.

Recovery has two distinct phases:

1. LATEST VISIBILITY:
   Re-request the unpaginated latest page until REST has reached at least the
   WebSocket/heartbeat recovery target watermark.

2. OLDER COVERAGE:
   Once REST has caught up, follow Coinbase-provided CB-AFTER cursors toward
   older pages only if needed to reach the known pre-gap boundary trade.

Every HTTP response body is persisted before status handling, JSON parsing,
trade inspection, or recovery logic.

Recovery remains fail-closed if either phase cannot be proven within its
bounded limits.

No authentication, Kalshi access, Candidate-E strategy change, or execution
behavior exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import time
from typing import Any, Mapping, Protocol

from .kxbtcd_candidate_e_coinbase_rest_recovery import (
    CoinbaseRestRecoveryEvidence,
    build_recovery_evidence,
)
from .kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournal,
)


COINBASE_EXCHANGE_BASE = (
    "https://api.exchange.coinbase.com"
)
COINBASE_PRODUCT = "BTC-USD"
TRADE_PAGE_LIMIT = 1000

DEFAULT_MAX_LATEST_ATTEMPTS = 10
DEFAULT_LATEST_RETRY_SLEEP_SECONDS = 0.5


class CoinbaseRestPaginatorError(RuntimeError):
    pass


class HttpResponseLike(Protocol):
    status_code: int
    text: str
    headers: Mapping[str, Any]

    def raise_for_status(self) -> None:
        ...


class HttpSessionLike(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any],
        timeout: float,
    ) -> HttpResponseLike:
        ...


@dataclass(frozen=True)
class CoinbaseRestPage:
    page_index: int
    phase: str
    latest_attempt_index: int | None
    after_cursor_used: str | None
    cb_before: str | None
    cb_after: str | None
    row_count: int
    min_trade_id: int | None
    max_trade_id: int | None
    rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class CoinbaseRecoveryFetch:
    evidence: CoinbaseRestRecoveryEvidence
    pages: tuple[CoinbaseRestPage, ...]
    latest_attempt_count: int
    latest_target_watermark_reached: bool


def _cursor(
    headers: Mapping[str, Any],
    name: str,
) -> str | None:
    value = headers.get(name)

    if value is None:
        for key, candidate in headers.items():
            if str(key).lower() == name.lower():
                value = candidate
                break

    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _trade_id(
    row: Mapping[str, Any],
    *,
    context: str,
) -> int:
    value = row.get("trade_id")

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
    ):
        raise CoinbaseRestPaginatorError(
            f"{context}.trade_id must be integer"
        )

    if value < 0:
        raise CoinbaseRestPaginatorError(
            f"{context}.trade_id must be nonnegative"
        )

    return value


def _utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def fetch_recovery_pages(
    *,
    session: HttpSessionLike,
    journal: RuntimeRawJournal,
    start_exclusive_trade_id: int,
    target_inclusive_trade_id: int,
    max_pages: int = 10,
    max_latest_attempts: int =
        DEFAULT_MAX_LATEST_ATTEMPTS,
    latest_retry_sleep_seconds: float =
        DEFAULT_LATEST_RETRY_SLEEP_SECONDS,
    timeout_seconds: float = 10.0,
) -> CoinbaseRecoveryFetch:
    """Recover one frozen WebSocket gap using Coinbase REST.

    IMPORTANT:

    `after` is used only after the latest REST page has reached the target
    watermark. If REST is still behind WebSocket, paging `after` would move
    backward in time and can never find the newer target.

    Therefore target visibility is established first by bounded repeated
    requests of the unpaginated latest page.
    """
    start = int(start_exclusive_trade_id)
    target = int(target_inclusive_trade_id)

    if start < 0 or target <= start:
        raise CoinbaseRestPaginatorError(
            "invalid recovery trade-ID interval"
        )

    if max_pages <= 0:
        raise CoinbaseRestPaginatorError(
            "max_pages must be positive"
        )

    if max_latest_attempts <= 0:
        raise CoinbaseRestPaginatorError(
            "max_latest_attempts must be positive"
        )

    if latest_retry_sleep_seconds < 0:
        raise CoinbaseRestPaginatorError(
            "latest_retry_sleep_seconds "
            "must be nonnegative"
        )

    if timeout_seconds <= 0:
        raise CoinbaseRestPaginatorError(
            "timeout_seconds must be positive"
        )

    url = (
        f"{COINBASE_EXCHANGE_BASE}/products/"
        f"{COINBASE_PRODUCT}/trades"
    )

    all_pages: list[CoinbaseRestPage] = []

    def request_page(
        *,
        phase: str,
        latest_attempt_index: int | None,
        after_cursor: str | None,
    ) -> CoinbaseRestPage:
        params: dict[str, Any] = {
            "limit": TRADE_PAGE_LIMIT,
        }

        if after_cursor is not None:
            params["after"] = after_cursor

        response = session.get(
            url,
            params=params,
            timeout=timeout_seconds,
        )

        recv_ns = time.monotonic_ns()

        cb_before = _cursor(
            response.headers,
            "CB-BEFORE",
        )
        cb_after = _cursor(
            response.headers,
            "CB-AFTER",
        )

        # REQUIRED: exact response is durable before any interpretation.
        journal.append(
            source="coinbase_exchange_rest",
            transport="https_rest",
            raw_text=response.text,
            received_monotonic_ns=recv_ns,
            received_utc=_utc_now_text(),
            request_identity={
                "method": "GET",
                "url": url,
                "params": params,
                "status_code":
                    int(response.status_code),
                "phase": phase,
                "latest_attempt_index":
                    latest_attempt_index,
                "cb_before": cb_before,
                "cb_after": cb_after,
            },
        )

        response.raise_for_status()

        try:
            payload = json.loads(
                response.text
            )
        except json.JSONDecodeError as exc:
            raise CoinbaseRestPaginatorError(
                "Coinbase trades response is not JSON"
            ) from exc

        if not isinstance(payload, list):
            raise CoinbaseRestPaginatorError(
                "Coinbase trades response "
                "must be a list"
            )

        rows: list[Mapping[str, Any]] = []
        trade_ids: list[int] = []

        for row_index, row in enumerate(
            payload
        ):
            if not isinstance(row, Mapping):
                raise CoinbaseRestPaginatorError(
                    f"trade row {row_index} "
                    "must be an object"
                )

            copied = dict(row)

            trade_ids.append(
                _trade_id(
                    copied,
                    context=(
                        f"trade row {row_index}"
                    ),
                )
            )
            rows.append(copied)

        page = CoinbaseRestPage(
            page_index=len(all_pages),
            phase=phase,
            latest_attempt_index=
                latest_attempt_index,
            after_cursor_used=after_cursor,
            cb_before=cb_before,
            cb_after=cb_after,
            row_count=len(rows),
            min_trade_id=(
                min(trade_ids)
                if trade_ids
                else None
            ),
            max_trade_id=(
                max(trade_ids)
                if trade_ids
                else None
            ),
            rows=tuple(rows),
        )

        all_pages.append(page)
        return page

    # ------------------------------------------------------
    # PHASE 1:
    # Wait for REST's latest page to catch up to the frozen
    # WebSocket/heartbeat target.
    # ------------------------------------------------------

    latest_page: CoinbaseRestPage | None = None

    for attempt in range(
        1,
        max_latest_attempts + 1,
    ):
        candidate = request_page(
            phase="latest_visibility",
            latest_attempt_index=attempt,
            after_cursor=None,
        )

        if (
            candidate.max_trade_id is not None
            and candidate.max_trade_id >= target
        ):
            latest_page = candidate
            break

        if attempt < max_latest_attempts:
            time.sleep(
                latest_retry_sleep_seconds
            )

    if latest_page is None:
        # Use only the final latest snapshot for evidence. Earlier latest
        # retries are temporal observations, not consecutive cursor pages.
        final_rows = (
            all_pages[-1].rows
            if all_pages
            else ()
        )

        evidence = build_recovery_evidence(
            pages=[final_rows],
            start_exclusive_trade_id=start,
            target_inclusive_trade_id=target,
        )

        return CoinbaseRecoveryFetch(
            evidence=evidence,
            pages=tuple(all_pages),
            latest_attempt_count=
                max_latest_attempts,
            latest_target_watermark_reached=False,
        )

    # ------------------------------------------------------
    # PHASE 2:
    # REST has reached/passed the target. The latest page is
    # now the first authoritative cursor-coverage page.
    # ------------------------------------------------------

    coverage_pages: list[
        tuple[Mapping[str, Any], ...]
    ] = [
        latest_page.rows,
    ]

    evidence = build_recovery_evidence(
        pages=coverage_pages,
        start_exclusive_trade_id=start,
        target_inclusive_trade_id=target,
    )

    if evidence.coverage_proven:
        return CoinbaseRecoveryFetch(
            evidence=evidence,
            pages=tuple(all_pages),
            latest_attempt_count=
                latest_page.latest_attempt_index or 1,
            latest_target_watermark_reached=True,
        )

    after_cursor = latest_page.cb_after

    if after_cursor is None:
        return CoinbaseRecoveryFetch(
            evidence=evidence,
            pages=tuple(all_pages),
            latest_attempt_count=
                latest_page.latest_attempt_index or 1,
            latest_target_watermark_reached=True,
        )

    seen_after_cursors: set[str] = set()
    coverage_page_count = 1

    while (
        coverage_page_count < max_pages
        and after_cursor is not None
    ):
        if after_cursor in seen_after_cursors:
            raise CoinbaseRestPaginatorError(
                "Coinbase pagination "
                "cursor loop detected"
            )

        seen_after_cursors.add(
            after_cursor
        )

        page = request_page(
            phase="older_pagination",
            latest_attempt_index=None,
            after_cursor=after_cursor,
        )

        coverage_pages.append(
            page.rows
        )
        coverage_page_count += 1

        evidence = build_recovery_evidence(
            pages=coverage_pages,
            start_exclusive_trade_id=start,
            target_inclusive_trade_id=target,
        )

        if evidence.coverage_proven:
            return CoinbaseRecoveryFetch(
                evidence=evidence,
                pages=tuple(all_pages),
                latest_attempt_count=
                    latest_page.latest_attempt_index or 1,
                latest_target_watermark_reached=True,
            )

        next_cursor = page.cb_after

        if next_cursor is None:
            break

        if next_cursor == after_cursor:
            raise CoinbaseRestPaginatorError(
                "Coinbase CB-AFTER cursor "
                "did not advance"
            )

        after_cursor = next_cursor

    return CoinbaseRecoveryFetch(
        evidence=evidence,
        pages=tuple(all_pages),
        latest_attempt_count=
            latest_page.latest_attempt_index or 1,
        latest_target_watermark_reached=True,
    )
