"""Find currently open Bitcoin-related Kalshi markets.

This script is read-only. It uses public market-data endpoints and has no
ability to access a Kalshi account or place an order.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dateutil import parser as date_parser

from src.config import (
    DEFAULT_MANIFEST_ROOT,
    DEFAULT_RUNTIME_EVENT_ROOT,
    PRIMARY_BTC_SERIES_TICKER,
)
from src.kalshi_public import KalshiPublicAPIError, KalshiPublicClient
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError


def parse_time(value: Any) -> datetime:
    if not value:
        return datetime.max.astimezone()
    try:
        return date_parser.isoparse(str(value))
    except (TypeError, ValueError):
        return datetime.max.astimezone()


def main() -> None:
    client = KalshiPublicClient()
    manifest = CollectionRunManifest(
        collector_name="scan_btc_markets",
        arguments={"series_ticker": PRIMARY_BTC_SERIES_TICKER},
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=[
            {
                "source": client.raw_recorder.source_name,
                "session_id": client.raw_recorder.session_id,
            }
        ],
        runtime_observability=True,
    )
    runtime_events = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name="scan_btc_markets",
        started_at_utc=manifest.started_at_utc,
    )
    client.attach_runtime_event_logger(runtime_events)

    market_count = 0
    try:
        runtime_events.emit(
            "collector.started",
            severity="info",
            message="Bitcoin market discovery collector started",
            context={"series_ticker": PRIMARY_BTC_SERIES_TICKER},
        )

        print(f"Raw API archive root: {client.raw_recorder.root_dir}")
        print(f"Runtime event log: {runtime_events.output_path}")
        print(f"Run manifest: {manifest.manifest_path}")
        print("Fetching open Kalshi markets...\n")

        btc_markets = client.list_open_markets(
            series_ticker=PRIMARY_BTC_SERIES_TICKER
        )
        btc_markets.sort(key=lambda market: parse_time(market.get("close_time")))
        market_count = len(btc_markets)

        if not btc_markets:
            print(
                f"No open markets were found for series "
                f"{PRIMARY_BTC_SERIES_TICKER}."
            )
            print(
                "The series may be temporarily unavailable, paused, "
                "or renamed by Kalshi."
            )
        else:
            print(f"Found {len(btc_markets)} open Bitcoin-related markets:\n")
            for index, market in enumerate(btc_markets, start=1):
                ticker = market.get("ticker", "UNKNOWN")
                title = market.get("title", "")
                subtitle = market.get("subtitle", "")
                close_time = market.get("close_time", "unknown")
                yes_bid = market.get("yes_bid_dollars", "n/a")
                yes_ask = market.get("yes_ask_dollars", "n/a")
                volume = market.get("volume_fp", "n/a")

                print(f"[{index}] {ticker}")
                print(f"    {title}")
                if subtitle:
                    print(f"    {subtitle}")
                print(f"    closes: {close_time}")
                print(
                    f"    quoted YES: bid ${yes_bid} / ask ${yes_ask} "
                    f"| volume {volume}"
                )
                print()

        runtime_events.emit(
            "collector.completed",
            severity="info",
            message="Bitcoin market discovery workload completed",
            context={"markets_found": market_count, "orders_placed": 0},
        )
        manifest.complete(
            raw_files=client.raw_recorder.written_paths,
            runtime_event_files=runtime_events.written_paths,
            result={"markets_found": market_count, "orders_placed": 0},
        )
    except BaseException as exc:
        event_write_failure: RuntimeEventWriteError | None = None
        if not isinstance(exc, RuntimeEventWriteError):
            try:
                runtime_events.emit(
                    "collector.failed",
                    severity="critical",
                    message="Bitcoin market discovery collector terminated",
                    context={"markets_found": market_count, "orders_placed": 0},
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            except RuntimeEventWriteError as log_exc:
                event_write_failure = log_exc

        failure = event_write_failure or exc
        try:
            manifest.fail(
                failure,
                raw_files=client.raw_recorder.written_paths,
                runtime_event_files=runtime_events.written_paths,
                result={
                    "markets_found": market_count,
                    "orders_placed": 0,
                    "original_failure_type": type(exc).__name__,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from failure
        if event_write_failure is not None:
            raise event_write_failure from exc
        raise

    print(f"Completed manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (KalshiPublicAPIError, RunManifestError, RuntimeEventWriteError) as exc:
        raise SystemExit(f"Collection error: {exc}") from exc
