"""Record repeated orderbook snapshots for one Kalshi market to CSV.

Example:
    python record_orderbook.py --ticker MARKET-TICKER --seconds 300 --interval 2

This is read-only and does not place orders.
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

from src.config import DEFAULT_MANIFEST_ROOT, DEFAULT_RUNTIME_EVENT_ROOT
from src.kalshi_public import (
    EndpointValidationError,
    KalshiPublicAPIError,
    KalshiPublicClient,
    SourcedOrderbook,
    extract_best_prices,
)
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError


ORDERBOOK_CSV_FIELDS = [
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "observed_at_utc",
    "ticker",
    "yes_bid",
    "yes_ask",
    "yes_spread",
    "no_bid",
    "no_ask",
    "no_spread",
]


def money(value: object) -> str:
    return "" if value is None else str(value)


def build_orderbook_row(
    *,
    run_id: str,
    ticker: str,
    observed_at_utc: str,
    sourced_orderbook: SourcedOrderbook,
) -> dict[str, str]:
    """Build one derived CSV row with exact raw-record lineage."""

    prices = extract_best_prices(sourced_orderbook.orderbook)
    raw_record = sourced_orderbook.raw_record

    return {
        "run_id": run_id,
        "raw_source": raw_record.source,
        "raw_session_id": raw_record.session_id,
        "raw_request_id": raw_record.request_id,
        "observed_at_utc": observed_at_utc,
        "ticker": ticker,
        "yes_bid": money(prices.yes_bid),
        "yes_ask": money(prices.yes_ask),
        "yes_spread": money(prices.yes_spread),
        "no_bid": money(prices.no_bid),
        "no_ask": money(prices.no_ask),
        "no_spread": money(prices.no_spread),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", required=True, help="Exact Kalshi market ticker")
    parser.add_argument(
        "--seconds",
        type=int,
        default=300,
        help="Total recording time in seconds (default: 300)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between REST snapshots (default: 2.0)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output CSV path",
    )
    args = parser.parse_args()

    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds for this learning script")
    return args


def main() -> None:
    args = parse_args()
    client = KalshiPublicClient()

    safe_ticker = "".join(
        char if char.isalnum() or char in "-_" else "_" for char in args.ticker
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output or Path("logs") / f"{safe_ticker}_{timestamp}.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = CollectionRunManifest(
        collector_name="record_orderbook",
        arguments={
            "ticker": args.ticker,
            "seconds": args.seconds,
            "interval": args.interval,
            "output": output_path,
        },
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
        collector_name="record_orderbook",
        started_at_utc=manifest.started_at_utc,
    )
    client.attach_runtime_event_logger(runtime_events)

    successful_rows = 0
    request_failures = 0
    try:
        runtime_events.emit(
            "collector.started",
            severity="info",
            message="Order-book recorder started",
            context={
                "ticker": args.ticker,
                "seconds": args.seconds,
                "interval": args.interval,
                "output": output_path,
            },
        )

        print(f"Recording {args.ticker} every {args.interval:g}s for {args.seconds}s")
        print(f"Derived CSV output: {output_path}")
        print(f"Raw API archive root: {client.raw_recorder.root_dir}")
        print(f"Runtime event log: {runtime_events.output_path}")
        print(f"Run manifest: {manifest.manifest_path}\n")

        deadline = time.monotonic() + args.seconds
        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=ORDERBOOK_CSV_FIELDS)
            writer.writeheader()

            while time.monotonic() < deadline:
                started = time.monotonic()
                observed_at = datetime.now(timezone.utc).isoformat()

                try:
                    sourced_orderbook = client.get_orderbook_with_lineage(
                        args.ticker
                    )
                    row = build_orderbook_row(
                        run_id=manifest.run_id,
                        ticker=args.ticker,
                        observed_at_utc=observed_at,
                        sourced_orderbook=sourced_orderbook,
                    )
                    writer.writerow(row)
                    csv_file.flush()
                    successful_rows += 1

                    print(
                        f"{observed_at} | YES {row['yes_bid']} / {row['yes_ask']} "
                        f"spread={row['yes_spread']}"
                    )
                except EndpointValidationError:
                    raise
                except KalshiPublicAPIError as exc:
                    request_failures += 1
                    runtime_events.emit(
                        "collector.iteration.failed",
                        severity="warning",
                        message=(
                            "Order-book polling iteration failed and the bounded "
                            "collector will continue"
                        ),
                        context={
                            "ticker": args.ticker,
                            "observed_at_utc": observed_at,
                            "request_failures": request_failures,
                            "will_continue": True,
                        },
                        error={"type": type(exc).__name__, "message": str(exc)},
                    )
                    print(f"{observed_at} | request failed: {exc}")

                elapsed = time.monotonic() - started
                time.sleep(max(0.0, args.interval - elapsed))

        runtime_events.emit(
            "collector.completed",
            severity="info",
            message="Order-book recording workload completed",
            context={
                "ticker": args.ticker,
                "successful_csv_rows": successful_rows,
                "request_failures": request_failures,
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=client.raw_recorder.written_paths,
            derived_csv_files=[output_path],
            runtime_event_files=runtime_events.written_paths,
            result={
                "successful_csv_rows": successful_rows,
                "request_failures": request_failures,
                "orders_placed": 0,
            },
        )
    except BaseException as exc:
        event_write_failure: RuntimeEventWriteError | None = None
        if not isinstance(exc, RuntimeEventWriteError):
            try:
                runtime_events.emit(
                    "collector.failed",
                    severity="critical",
                    message="Order-book recorder terminated",
                    context={
                        "ticker": args.ticker,
                        "successful_csv_rows": successful_rows,
                        "request_failures": request_failures,
                        "orders_placed": 0,
                    },
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            except RuntimeEventWriteError as log_exc:
                event_write_failure = log_exc

        failure = event_write_failure or exc
        try:
            manifest.fail(
                failure,
                raw_files=client.raw_recorder.written_paths,
                derived_csv_files=[output_path],
                runtime_event_files=runtime_events.written_paths,
                result={
                    "successful_csv_rows": successful_rows,
                    "request_failures": request_failures,
                    "orders_placed": 0,
                    "original_failure_type": type(exc).__name__,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from failure
        if event_write_failure is not None:
            raise event_write_failure from exc
        raise

    print("\nFinished. No orders were placed.")
    print(f"Completed manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (KalshiPublicAPIError, RunManifestError, RuntimeEventWriteError) as exc:
        raise SystemExit(f"Collection error: {exc}") from exc
