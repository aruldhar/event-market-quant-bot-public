"""Orchestrate consecutive public/read-only KXBTC15M order-book captures.

This script does not place orders or use account authentication. It reuses the
repository's existing validated collectors:

1. ``scan_btc_markets.py`` discovers the currently open KXBTC15M market.
2. ``record_orderbook.py`` records that market through its close boundary.
3. ``validate_run_manifest.py`` validates the completed market capture.
4. The cycle repeats for a bounded number of markets or continuously until
   interrupted by the user.

On Windows the orchestrator can keep the system awake while it is active. The
monitor may still turn off. Explicit sleep/hibernate/shutdown, lid-close power
actions, loss of power, or loss of network connectivity cannot be prevented.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import math
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Sequence


_MARKET_LINE = re.compile(r"^\[(?:\d+)\]\s+(KXBTC15M-[^\s]+)\s*$")
_CLOSE_LINE = re.compile(r"^\s*closes:\s*(\S+)\s*$")
_MANIFEST_LINE = re.compile(r"^Completed manifest:\s*(.+?)\s*$")

# Windows SetThreadExecutionState flags.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


class ContinuousCaptureError(RuntimeError):
    """Raised when the orchestration cannot safely continue."""


@dataclass(frozen=True)
class OpenMarket:
    ticker: str
    close_time: datetime


def parse_utc_datetime(value: str) -> datetime:
    """Parse one ISO-8601 timestamp and normalize it to timezone-aware UTC."""

    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include a timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def parse_scan_output(output: str) -> list[OpenMarket]:
    """Extract ticker/close-time pairs from ``scan_btc_markets.py`` output."""

    markets: list[OpenMarket] = []
    pending_ticker: str | None = None

    for line in output.splitlines():
        market_match = _MARKET_LINE.match(line)
        if market_match:
            pending_ticker = market_match.group(1)
            continue

        close_match = _CLOSE_LINE.match(line)
        if close_match and pending_ticker is not None:
            markets.append(
                OpenMarket(
                    ticker=pending_ticker,
                    close_time=parse_utc_datetime(close_match.group(1)),
                )
            )
            pending_ticker = None

    return markets


def select_current_market(
    markets: Sequence[OpenMarket],
    *,
    now_utc: datetime,
    seen_tickers: set[str],
) -> OpenMarket | None:
    """Choose the earliest-closing unseen market that has not yet closed."""

    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    eligible = [
        market
        for market in markets
        if market.ticker not in seen_tickers and market.close_time > now_utc
    ]
    if not eligible:
        return None
    return min(eligible, key=lambda market: market.close_time)


def recording_seconds(
    *,
    close_time: datetime,
    now_utc: datetime,
    post_close_grace_seconds: float,
) -> int:
    """Return a positive whole-second recorder duration through close + grace."""

    if close_time.tzinfo is None or now_utc.tzinfo is None:
        raise ValueError("close_time and now_utc must be timezone-aware")
    if post_close_grace_seconds < 0:
        raise ValueError("post_close_grace_seconds cannot be negative")

    remaining = (close_time - now_utc).total_seconds()
    return max(1, math.ceil(remaining + post_close_grace_seconds))


def parse_completed_manifest(output: str) -> Path:
    """Return the completed-manifest path printed by a child collector."""

    matches = [
        _MANIFEST_LINE.match(line)
        for line in output.splitlines()
        if _MANIFEST_LINE.match(line) is not None
    ]
    if not matches:
        raise ContinuousCaptureError(
            "Recorder exited without printing a completed manifest path"
        )
    return Path(matches[-1].group(1))


def run_and_tee(
    command: Sequence[str],
    *,
    cwd: Path,
    popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> tuple[int, str]:
    """Run one child command, tee combined output, and return code + text."""

    process = popen_factory(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if process.stdout is None:
        raise ContinuousCaptureError("Child process stdout pipe was unavailable")

    captured: list[str] = []
    for line in process.stdout:
        print(line, end="")
        captured.append(line)

    return process.wait(), "".join(captured)


def _set_windows_execution_state(flags: int) -> bool:
    """Set the current Windows thread execution state; return success."""

    if sys.platform != "win32":
        return False
    result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
    return bool(result)


@contextlib.contextmanager
def keep_system_awake(enabled: bool = True) -> Iterator[bool]:
    """Prevent automatic Windows system sleep while this context is active.

    This keeps the *system* awake but does not request that the display remain on.
    Normal execution-state behavior is restored on exit.
    """

    active = False
    if enabled and sys.platform == "win32":
        active = _set_windows_execution_state(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
        if not active:
            raise ContinuousCaptureError(
                "Windows sleep prevention could not be enabled; stopping rather "
                "than risking an unattended collection gap"
            )

    try:
        yield active
    finally:
        if active:
            _set_windows_execution_state(_ES_CONTINUOUS)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--markets",
        type=int,
        default=None,
        help="Stop after this many validated market captures",
    )
    mode.add_argument(
        "--continuous",
        action="store_true",
        help="Run until Ctrl+C instead of stopping after a fixed market count",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Seconds between order-book REST snapshots (default: 0.5)",
    )
    parser.add_argument(
        "--post-close-grace",
        type=float,
        default=2.0,
        help=(
            "Seconds to continue the market recorder past close so the terminal "
            "empty-book transition can be observed (default: 2.0)"
        ),
    )
    parser.add_argument(
        "--discovery-sleep",
        type=float,
        default=2.0,
        help="Seconds between scans when no unseen market is available (default: 2)",
    )
    parser.add_argument(
        "--scan-retries",
        type=int,
        default=30,
        help=(
            "Consecutive failed scans allowed in bounded mode (default: 30). "
            "Continuous mode retries discovery indefinitely."
        ),
    )
    parser.add_argument(
        "--allow-system-sleep",
        action="store_true",
        help=(
            "Do not request Windows to stay awake. By default, Windows automatic "
            "system sleep is inhibited while this script is active."
        ),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root containing the existing collector scripts",
    )
    args = parser.parse_args(argv)

    # Keep the old convenient bounded default when neither mode is supplied.
    if args.markets is None and not args.continuous:
        args.markets = 8

    if args.markets is not None and args.markets <= 0:
        parser.error("--markets must be positive")
    if args.interval < 0.5:
        parser.error("--interval must be at least 0.5 seconds")
    if args.post_close_grace < 0:
        parser.error("--post-close-grace cannot be negative")
    if args.discovery_sleep < 0.5:
        parser.error("--discovery-sleep must be at least 0.5 seconds")
    if args.scan_retries <= 0:
        parser.error("--scan-retries must be positive")
    return args


def should_continue(*, completed_markets: int, continuous: bool, markets: int | None) -> bool:
    """Return whether another market should be collected."""

    if continuous:
        return True
    assert markets is not None
    return completed_markets < markets


def _progress_label(*, completed_markets: int, continuous: bool, markets: int | None) -> str:
    if continuous:
        return f"{completed_markets} validated so far"
    assert markets is not None
    return f"{completed_markets}/{markets}"


def main() -> None:
    args = parse_args()
    repo_root = args.repository_root.resolve()

    required_scripts = (
        "scan_btc_markets.py",
        "record_orderbook.py",
        "validate_run_manifest.py",
    )
    missing = [name for name in required_scripts if not (repo_root / name).is_file()]
    if missing:
        raise ContinuousCaptureError(
            f"Repository root is missing required scripts: {missing}"
        )

    python_executable = sys.executable
    seen_tickers: set[str] = set()
    completed_markets = 0
    consecutive_scan_failures = 0

    print("Event-Market Quant Bot — continuous KXBTC15M read-only capture")
    print(f"Repository: {repo_root}")
    print("Mode: continuous until Ctrl+C" if args.continuous else f"Target validated markets: {args.markets}")
    print(f"Order-book interval: {args.interval:g}s")
    if sys.platform == "win32":
        print(
            "Automatic Windows sleep: allowed by user"
            if args.allow_system_sleep
            else "Automatic Windows sleep: inhibited while collector is active"
        )
    print("No authentication or orders are used.\n")

    with keep_system_awake(enabled=not args.allow_system_sleep):
        try:
            while should_continue(
                completed_markets=completed_markets,
                continuous=args.continuous,
                markets=args.markets,
            ):
                scan_command = [python_executable, "scan_btc_markets.py"]
                scan_code, scan_output = run_and_tee(scan_command, cwd=repo_root)

                if scan_code != 0:
                    consecutive_scan_failures += 1
                    if args.continuous:
                        print(
                            f"Market scan failed ({consecutive_scan_failures} consecutive); "
                            f"continuous mode will retry in {args.discovery_sleep:g}s."
                        )
                    else:
                        print(
                            f"Market scan failed ({consecutive_scan_failures}/"
                            f"{args.scan_retries}); retrying after "
                            f"{args.discovery_sleep:g}s."
                        )
                        if consecutive_scan_failures >= args.scan_retries:
                            raise ContinuousCaptureError(
                                "Market discovery exceeded the allowed consecutive failures"
                            )
                    time.sleep(args.discovery_sleep)
                    continue

                consecutive_scan_failures = 0
                markets = parse_scan_output(scan_output)
                now_utc = datetime.now(timezone.utc)
                current = select_current_market(
                    markets,
                    now_utc=now_utc,
                    seen_tickers=seen_tickers,
                )

                if current is None:
                    print(
                        "No unseen open KXBTC15M market is available yet; "
                        f"rescanning in {args.discovery_sleep:g}s."
                    )
                    time.sleep(args.discovery_sleep)
                    continue

                seconds = recording_seconds(
                    close_time=current.close_time,
                    now_utc=datetime.now(timezone.utc),
                    post_close_grace_seconds=args.post_close_grace,
                )

                next_number = completed_markets + 1
                if args.continuous:
                    print(f"\nStarting market #{next_number}: {current.ticker}")
                else:
                    print(f"\nStarting market {next_number}/{args.markets}: {current.ticker}")
                print(f"Close time: {current.close_time.isoformat()}")
                print(f"Recorder duration: {seconds}s\n")

                record_command = [
                    python_executable,
                    "record_orderbook.py",
                    "--ticker",
                    current.ticker,
                    "--seconds",
                    str(seconds),
                    "--interval",
                    str(args.interval),
                ]
                record_code, record_output = run_and_tee(record_command, cwd=repo_root)
                if record_code != 0:
                    raise ContinuousCaptureError(
                        f"Recorder failed for {current.ticker}; stopping instead of "
                        "silently skipping a market"
                    )

                manifest_path = parse_completed_manifest(record_output)
                validate_command = [
                    python_executable,
                    "validate_run_manifest.py",
                    str(manifest_path),
                ]
                validate_code, _ = run_and_tee(validate_command, cwd=repo_root)
                if validate_code != 0:
                    raise ContinuousCaptureError(
                        f"Manifest validation failed for {current.ticker}; stopping"
                    )

                seen_tickers.add(current.ticker)
                completed_markets += 1
                print(
                    f"\nValidated {current.ticker}. Progress: "
                    f"{_progress_label(completed_markets=completed_markets, continuous=args.continuous, markets=args.markets)}.\n"
                )

        except KeyboardInterrupt:
            print("\nCtrl+C received; continuous capture stopping cleanly.")

    print("Capture session ended.")
    print(f"Validated markets: {completed_markets}")
    print("No orders were placed.")


if __name__ == "__main__":
    try:
        main()
    except ContinuousCaptureError as exc:
        raise SystemExit(f"Continuous capture stopped: {exc}") from exc
