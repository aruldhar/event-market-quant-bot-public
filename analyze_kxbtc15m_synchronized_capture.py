#!/usr/bin/env python3
"""Outcome-blind audit of one synchronized KXBTC15M capture.

The audit combines three read-only artifacts captured at the same time:

* Kalshi BRTI WebSocket values;
* public Coinbase and Kraken BTC/USD WebSocket quotes; and
* archived Kalshi KXBTC15M full-depth REST order books.

It validates the capture, corrects local wall-clock timestamps using the NTP
strip-chart measurements, produces a descriptive lead/lag table, and replays
the frozen H3 entry/exit mechanics without reading a market result.

The critical causal rule is that an order book becomes available at the raw
HTTP response ``timing.received_at_utc`` timestamp.  The derived CSV's
``observed_at_utc`` is the request start and is used only for integrity checks.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import (
    LATENCY_SECONDS,
    MAX_BUDGET,
    Snapshot,
    buy_with_budget,
    first_index_at_or_after,
    sell_quantity,
)
from analyze_kxbtc15m_h3_late_convergence import favored_quote
from audit_kxbtc15m_raw_depth import market_close_utc, parse_book, parse_time


SCHEMA = "kxbtc15m_synchronized_capture_audit.v1"
GRID_SECONDS = 5
H3_WINDOW_START_SECONDS = 300
H3_WINDOW_END_SECONDS = 240
MAX_ANCHOR_LAG_SECONDS = 2.0
PROBABILITY_LOW = Decimal("0.90")
PROBABILITY_HIGH_EXCLUSIVE = Decimal("0.98")
TARGET_FRACTION = Decimal("0.50")
PRECLOSE_SECONDS = 10
MAX_CAUSAL_STALENESS_SECONDS = 2.0
MAX_CSV_TO_RAW_REQUEST_START_SECONDS = 5.0
LAGS = tuple(range(-10, 16))


class AuditError(RuntimeError):
    """Raised when synchronized evidence cannot be audited safely."""


@dataclass(frozen=True)
class ClockCorrection:
    first_epoch_ms: int
    last_epoch_ms: int
    before_seconds: float
    after_seconds: float

    def offset_seconds(self, epoch_ms: int) -> float:
        if self.last_epoch_ms <= self.first_epoch_ms:
            return self.before_seconds
        fraction = (epoch_ms - self.first_epoch_ms) / (
            self.last_epoch_ms - self.first_epoch_ms
        )
        fraction = min(1.0, max(0.0, fraction))
        return self.before_seconds + fraction * (
            self.after_seconds - self.before_seconds
        )

    def corrected_epoch_ms(self, epoch_ms: int) -> float:
        # w32tm reports reference_time - local_time.  A positive value means
        # the Windows clock is behind and must be advanced.
        return epoch_ms + 1000.0 * self.offset_seconds(epoch_ms)


@dataclass(frozen=True)
class FeedPoint:
    venue: str
    arrival_ms: float
    source_ms: float | None
    value: float
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class BookPoint:
    snapshot: Snapshot
    raw_request_started_at: datetime
    raw_received_at: datetime
    corrected_received_at: datetime


def iso_to_epoch_ms(value: str) -> float:
    return parse_time(value).timestamp() * 1000.0


def epoch_ms_to_datetime(value: float) -> datetime:
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def descriptor_path(repo_root: Path, descriptor: Mapping[str, Any]) -> Path:
    spec = descriptor.get("path")
    if not isinstance(spec, Mapping):
        raise AuditError("manifest descriptor is missing path metadata")
    value = spec.get("value")
    if not isinstance(value, str) or not value:
        raise AuditError("manifest descriptor path is empty")
    if spec.get("kind") == "repository_relative":
        candidate = (repo_root / Path(value.replace("\\", "/"))).resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError as exc:
            raise AuditError(f"manifest path escapes repository: {value!r}") from exc
        return candidate
    if spec.get("kind") in {"absolute", "filesystem_absolute"}:
        return Path(value).resolve()
    raise AuditError(f"unsupported manifest path kind: {spec.get('kind')!r}")


def verify_descriptor(repo_root: Path, descriptor: Mapping[str, Any]) -> Path:
    path = descriptor_path(repo_root, descriptor)
    if not path.is_file():
        raise AuditError(f"manifest artifact is missing: {path}")
    expected_size = descriptor.get("size_bytes")
    if expected_size is not None and path.stat().st_size != int(expected_size):
        raise AuditError(f"manifest artifact size mismatch: {path}")
    expected_hash = descriptor.get("sha256")
    if expected_hash and sha256_path(path) != expected_hash:
        raise AuditError(f"manifest artifact hash mismatch: {path}")
    return path


def parse_clock_offsets(path: Path) -> list[float]:
    if not path.is_file():
        raise AuditError(f"clock evidence is missing: {path}")
    raw = path.read_bytes()
    # Windows PowerShell 5.1 redirection/Out-File commonly writes UTF-16 LE,
    # whereas PowerShell 7 and Set-Content -Encoding UTF8 write UTF-8.  Accept
    # both without requiring the capture evidence to be rewritten.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw[:256]:
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig", errors="replace")
    offsets: list[float] = []
    pattern = re.compile(r",\s*([+-]\d+(?:\.\d+)?)s\s*$")
    for line in text.splitlines():
        match = pattern.search(line)
        if match:
            offsets.append(float(match.group(1)))
    if not offsets:
        raise AuditError(f"no w32tm offsets found in {path}")
    return offsets


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditError(f"invalid JSON at {path}:{number}") from exc
            if not isinstance(value, dict):
                raise AuditError(f"non-object JSON at {path}:{number}")
            yield value


def newest_summary(directory: Path) -> Path:
    matches = sorted(directory.glob("*_summary.json"), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise AuditError(f"no summary JSON found in {directory}")
    return matches[-1]


def resolve_recorded_path(value: str, *, summary_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidates = [Path.cwd() / path, summary_path.parent / path, summary_path.parent / path.name]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise AuditError(f"recorded artifact path cannot be resolved: {value}")


def load_brti(summary_path: Path) -> tuple[dict[str, Any], list[FeedPoint]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    if summary.get("schema") != "kalshi_brti_websocket_probe.v1":
        raise AuditError("unexpected BRTI summary schema")
    if summary.get("order_code_present") is not False:
        raise AuditError("BRTI probe does not affirm absence of order code")
    raw_path = resolve_recorded_path(str(summary["raw_jsonl"]), summary_path=summary_path)
    provisional: list[tuple[int, int, int, float]] = []
    for record in read_jsonl(raw_path):
        frame = record.get("frame")
        if not isinstance(frame, dict) or frame.get("type") != "cfbenchmarks_value":
            continue
        message = frame.get("msg")
        if not isinstance(message, dict):
            raise AuditError("BRTI value frame is missing msg")
        try:
            data = json.loads(message["data"])
            provisional.append((
                int(record["local_received_at_ms"]),
                int(data["time"]),
                int(message["received_at"]),
                float(data["value"]),
            ))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuditError("malformed BRTI value frame") from exc
    if not provisional:
        raise AuditError("BRTI capture contains no value frames")
    expected = int(summary.get("tick_count", -1))
    if expected != len(provisional):
        raise AuditError(f"BRTI count mismatch: summary={expected}, raw={len(provisional)}")
    if int(summary.get("sequence_gaps", -1)) != 0:
        raise AuditError("BRTI capture contains sequence gaps")
    # Arrival correction is filled after both feed files establish the capture span.
    points = [
        FeedPoint("brti", float(local), float(source), value, value, value)
        for local, source, _kalshi, value in provisional
    ]
    summary["_raw_path"] = str(raw_path)
    return summary, points


def load_external(summary_path: Path) -> tuple[dict[str, Any], list[FeedPoint]]:
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
    if summary.get("schema") != "external_btc_websocket_probe.v1":
        raise AuditError("unexpected external-feed summary schema")
    if summary.get("authentication_used") is not False:
        raise AuditError("external probe unexpectedly reports authentication")
    if summary.get("order_code_present") is not False:
        raise AuditError("external probe does not affirm absence of order code")
    raw_path = resolve_recorded_path(str(summary["raw_jsonl"]), summary_path=summary_path)
    points: list[FeedPoint] = []
    for record in read_jsonl(raw_path):
        if record.get("message_type") != "ticker":
            continue
        venue = str(record.get("venue", ""))
        if venue not in {"coinbase", "kraken"}:
            continue
        bid, ask = record.get("bid"), record.get("ask")
        if bid is None or ask is None:
            continue
        bid_float, ask_float = float(bid), float(ask)
        source_ms: float | None = None
        raw = record.get("raw")
        if venue == "coinbase" and isinstance(raw, dict) and isinstance(raw.get("time"), str):
            source_ms = iso_to_epoch_ms(raw["time"])
        elif venue == "kraken" and isinstance(raw, dict):
            data = raw.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                timestamp = data[0].get("timestamp")
                if isinstance(timestamp, str):
                    source_ms = iso_to_epoch_ms(timestamp)
        points.append(FeedPoint(
            venue=venue,
            arrival_ms=float(record["local_epoch_ms"]),
            source_ms=source_ms,
            value=(bid_float + ask_float) / 2.0,
            bid=bid_float,
            ask=ask_float,
        ))
    if not points:
        raise AuditError("external capture contains no usable ticker quotes")
    summary["_raw_path"] = str(raw_path)
    return summary, points


def discover_orderbook_manifests(capture_root: Path, repo_root: Path) -> list[Path]:
    log_path = capture_root / "logs" / "orderbook.stdout.log"
    if not log_path.is_file():
        raise AuditError(f"order-book stdout log is missing: {log_path}")
    pattern = re.compile(r"^Completed manifest:\s*(.+record_orderbook_.+\.json)\s*$")
    found: list[Path] = []
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        path = Path(value)
        if not path.is_absolute():
            path = repo_root / Path(value.replace("\\", "/"))
        path = path.resolve()
        if path not in found:
            found.append(path)
    if not found:
        raise AuditError("no completed record_orderbook manifests found in capture log")
    return found


def _descriptor(manifest: Mapping[str, Any], role: str) -> Mapping[str, Any]:
    matches = [item for item in manifest.get("files", []) if item.get("role") == role]
    if len(matches) != 1:
        raise AuditError(f"manifest requires exactly one {role} descriptor")
    return matches[0]


def load_orderbooks(
    manifest_paths: Sequence[Path], repo_root: Path, correction: ClockCorrection
) -> tuple[dict[str, list[BookPoint]], list[dict[str, Any]]]:
    markets: dict[str, list[BookPoint]] = {}
    audit_rows: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        if not manifest_path.is_file():
            raise AuditError(f"order-book manifest is missing: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        raw_descriptor = _descriptor(manifest, "raw_api_archive")
        csv_descriptor = _descriptor(manifest, "derived_csv")
        raw_path = verify_descriptor(repo_root, raw_descriptor)
        csv_path = verify_descriptor(repo_root, csv_descriptor)
        if int(raw_descriptor.get("error_record_count", -1)) != 0:
            raise AuditError(f"raw archive reports errors: {raw_path}")
        with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
            csv_rows = list(csv.DictReader(handle))
        expected_rows = int(csv_descriptor.get("data_row_count", -1))
        if expected_rows != len(csv_rows):
            raise AuditError(f"derived CSV row-count mismatch: {csv_path}")
        csv_by_request = {row["raw_request_id"]: row for row in csv_rows}
        if len(csv_by_request) != len(csv_rows):
            raise AuditError(f"duplicate raw_request_id in {csv_path}")
        raw_count = 0
        tickers: set[str] = set()
        csv_to_raw_start_ms: list[float] = []
        for record in read_jsonl(raw_path):
            raw_count += 1
            request = record.get("request")
            timing = record.get("timing")
            if not isinstance(request, dict) or not isinstance(timing, dict):
                raise AuditError(f"raw record lacks request/timing: {raw_path}")
            request_id = str(request.get("request_id", ""))
            row = csv_by_request.get(request_id)
            if row is None:
                raise AuditError(f"raw request is not represented in derived CSV: {request_id}")
            ticker = row["ticker"]
            tickers.add(ticker)
            started = parse_time(str(request["started_at_utc"]))
            received = parse_time(str(timing["received_at_utc"]))
            # The collector records observed_at_utc at the start of its loop,
            # immediately before it invokes the HTTP client.  The raw logger
            # records the request start inside that client call.  They are not
            # required to be identical; raw_request_id is the exact lineage
            # key.  Enforce causal order and a generous sanity bound instead.
            csv_observed = parse_time(row["observed_at_utc"])
            csv_to_raw_start_ms.append(validate_lineage_times(
                request_id=request_id,
                csv_observed=csv_observed,
                started=started,
                received=received,
            ))
            received_epoch = int(round(received.timestamp() * 1000.0))
            corrected = epoch_ms_to_datetime(correction.corrected_epoch_ms(received_epoch))
            book = parse_book(record, ticker)
            point = BookPoint(
                snapshot=Snapshot(corrected, request_id, book),
                raw_request_started_at=started,
                raw_received_at=received,
                corrected_received_at=corrected,
            )
            markets.setdefault(ticker, []).append(point)
        if raw_count != int(raw_descriptor.get("record_count", -1)):
            raise AuditError(f"raw archive row-count mismatch: {raw_path}")
        if raw_count != len(csv_rows):
            raise AuditError(f"raw/derived record-count mismatch: {manifest_path}")
        audit_rows.append({
            "manifest": str(manifest_path),
            "raw_path": str(raw_path),
            "derived_csv": str(csv_path),
            "records": raw_count,
            "tickers": ";".join(sorted(tickers)),
            "median_csv_observation_to_raw_request_start_ms": float_text(
                statistics.median(csv_to_raw_start_ms), 3
            ),
            "maximum_csv_observation_to_raw_request_start_ms": float_text(
                max(csv_to_raw_start_ms), 3
            ),
            "validation": "PASS",
        })
    for ticker, points in markets.items():
        points.sort(key=lambda point: point.snapshot.observed_at)
        if any(
            later.snapshot.observed_at < earlier.snapshot.observed_at
            for earlier, later in zip(points, points[1:])
        ):
            raise AuditError(f"corrected order-book times are not ordered: {ticker}")
    return markets, audit_rows


def apply_clock_correction(
    points: Sequence[FeedPoint], correction: ClockCorrection
) -> list[FeedPoint]:
    return [
        FeedPoint(
            venue=point.venue,
            arrival_ms=correction.corrected_epoch_ms(int(round(point.arrival_ms))),
            source_ms=point.source_ms,
            value=point.value,
            bid=point.bid,
            ask=point.ask,
        )
        for point in points
    ]


def validate_lineage_times(
    *, request_id: str, csv_observed: datetime, started: datetime, received: datetime
) -> float:
    """Validate recorder ordering and return CSV-to-request-start milliseconds."""

    pre_request_seconds = (started - csv_observed).total_seconds()
    if pre_request_seconds < -0.050:
        raise AuditError(f"CSV observation occurs after raw request start: {request_id}")
    if pre_request_seconds > MAX_CSV_TO_RAW_REQUEST_START_SECONDS:
        raise AuditError(f"CSV observation is too far before raw request start: {request_id}")
    if received < started:
        raise AuditError(f"raw response precedes request start: {request_id}")
    return pre_request_seconds * 1000.0


def latest_point(
    points: Sequence[FeedPoint], arrival_times: Sequence[float], target_ms: float
) -> tuple[FeedPoint | None, float | None]:
    index = bisect.bisect_right(arrival_times, target_ms) - 1
    if index < 0:
        return None, None
    point = points[index]
    staleness = (target_ms - point.arrival_ms) / 1000.0
    if staleness < 0 or staleness > MAX_CAUSAL_STALENESS_SECONDS:
        return None, staleness
    return point, staleness


def decimal_text(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def float_text(value: float | None, digits: int = 6) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value:.{digits}f}"


def _latest_feed_fields(
    decision: datetime,
    brti: Sequence[FeedPoint],
    coinbase: Sequence[FeedPoint],
    kraken: Sequence[FeedPoint],
    target: float | None,
    side: str,
) -> dict[str, Any]:
    target_ms = decision.timestamp() * 1000.0
    values: dict[str, tuple[FeedPoint | None, float | None]] = {}
    for name, points in (("brti", brti), ("coinbase", coinbase), ("kraken", kraken)):
        arrivals = [point.arrival_ms for point in points]
        values[name] = latest_point(points, arrivals, target_ms)
    b, b_stale = values["brti"]
    c, c_stale = values["coinbase"]
    k, k_stale = values["kraken"]
    external_values = [point.value for point in (c, k) if point is not None]
    consensus = statistics.mean(external_values) if external_values else None
    delta = None
    if b is not None and target is not None:
        delta = b.value - target if side == "YES" else target - b.value
    return {
        "brti_target_value": float_text(target, 2),
        "decision_brti": float_text(None if b is None else b.value, 2),
        "decision_brti_staleness_seconds": float_text(b_stale),
        "decision_side_aligned_brti_delta_usd": float_text(delta, 2),
        "decision_coinbase_mid": float_text(None if c is None else c.value, 2),
        "decision_coinbase_staleness_seconds": float_text(c_stale),
        "decision_kraken_mid": float_text(None if k is None else k.value, 2),
        "decision_kraken_staleness_seconds": float_text(k_stale),
        "decision_external_consensus": float_text(consensus, 2),
    }


def infer_brti_target(brti: Sequence[FeedPoint], close_time: datetime) -> float | None:
    open_ms = (close_time - timedelta(minutes=15)).timestamp() * 1000.0
    eligible = [
        point for point in brti
        if point.source_ms is not None and point.source_ms <= open_ms
        and open_ms - point.source_ms <= 2000.0
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda point: point.source_ms or -math.inf).value


def protected_target_exit(
    snapshots: Sequence[Snapshot],
    *,
    start_index: int,
    stop_time: datetime,
    side: str,
    quantity: Decimal,
    outflow: Decimal,
    target: Decimal,
) -> tuple[Any | None, datetime | None, int, int]:
    signals = 0
    rejected = 0
    index = start_index
    while index < len(snapshots):
        observed = snapshots[index]
        if observed.observed_at >= stop_time:
            break
        hypothetical = sell_quantity(observed.book.bid_levels(side), quantity)
        if hypothetical.quantity != quantity or hypothetical.sell_inflow - outflow < target:
            index += 1
            continue
        signals += 1
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            observed.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= stop_time:
            rejected += 1
            break
        delayed = sell_quantity(snapshots[delayed_index].book.bid_levels(side), quantity)
        if delayed.quantity == quantity and delayed.sell_inflow - outflow >= target:
            return delayed, snapshots[delayed_index].observed_at, signals, rejected
        rejected += 1
        index = delayed_index + 1
    return None, None, signals, rejected


def delayed_preclose_exit(
    snapshots: Sequence[Snapshot],
    *,
    start_index: int,
    preclose_time: datetime,
    close_time: datetime,
    side: str,
    quantity: Decimal,
) -> tuple[Any | None, datetime | None]:
    index = first_index_at_or_after(snapshots, start_index, preclose_time)
    while index is not None and index < len(snapshots):
        signal = snapshots[index]
        delayed_index = first_index_at_or_after(
            snapshots,
            index + 1,
            signal.observed_at + timedelta(seconds=LATENCY_SECONDS),
        )
        if delayed_index is None or snapshots[delayed_index].observed_at >= close_time:
            break
        execution = sell_quantity(snapshots[delayed_index].book.bid_levels(side), quantity)
        if execution.quantity == quantity:
            return execution, snapshots[delayed_index].observed_at
        index = delayed_index + 1
    return None, None


def find_h3_decision(snapshots: Sequence[Snapshot], close_time: datetime) -> tuple[int, datetime, float] | None:
    grid_start = close_time - timedelta(seconds=H3_WINDOW_START_SECONDS)
    candidates: list[tuple[datetime, int, float]] = []
    # The frozen rule is 240 < seconds_remaining <= 300, so the anchor at
    # exactly 240 seconds is deliberately excluded.
    for offset in range(0, H3_WINDOW_START_SECONDS - H3_WINDOW_END_SECONDS, GRID_SECONDS):
        anchor = grid_start + timedelta(seconds=offset)
        index = first_index_at_or_after(snapshots, 0, anchor)
        if index is None:
            continue
        lag = (snapshots[index].observed_at - anchor).total_seconds()
        if lag < 0 or lag > MAX_ANCHOR_LAG_SECONDS:
            continue
        quote = favored_quote(snapshots[index].book)
        if quote is None:
            continue
        _, midpoint, _ = quote
        if PROBABILITY_LOW <= midpoint < PROBABILITY_HIGH_EXCLUSIVE:
            candidates.append((anchor, index, lag))
    if not candidates:
        return None
    anchor, index, lag = min(candidates, key=lambda item: item[0])
    return index, anchor, lag


def replay_h3_market(
    ticker: str,
    book_points: Sequence[BookPoint],
    brti: Sequence[FeedPoint],
    coinbase: Sequence[FeedPoint],
    kraken: Sequence[FeedPoint],
) -> dict[str, Any]:
    snapshots = [point.snapshot for point in book_points]
    close_time = market_close_utc(ticker)
    target_value = infer_brti_target(brti, close_time)
    base: dict[str, Any] = {
        "ticker": ticker,
        "close_time": close_time.isoformat(),
        "policy": "h3_first_90_98c_protected_50pct_max_preclose_10s",
        "outcome_read": False,
        "order_code_present": False,
        "status": "no_trigger",
        "realized_pnl": "",
    }
    decision = find_h3_decision(snapshots, close_time)
    if decision is None:
        return base
    decision_index, anchor, anchor_lag = decision
    decision_snapshot = snapshots[decision_index]
    quote = favored_quote(decision_snapshot.book)
    assert quote is not None
    side, favored_midpoint, decision_ask = quote
    base.update({
        "status": "entry_not_filled",
        "anchor_time": anchor.isoformat(),
        "anchor_lag_seconds": float_text(anchor_lag),
        "decision_time": decision_snapshot.observed_at.isoformat(),
        "seconds_remaining": float_text((close_time - decision_snapshot.observed_at).total_seconds()),
        "side": side,
        "decision_favored_midpoint": decimal_text(favored_midpoint),
        "decision_favored_ask": decimal_text(decision_ask),
    })
    base.update(_latest_feed_fields(
        decision_snapshot.observed_at, brti, coinbase, kraken, target_value, side
    ))
    entry_index = first_index_at_or_after(
        snapshots,
        decision_index + 1,
        decision_snapshot.observed_at + timedelta(seconds=LATENCY_SECONDS),
    )
    if entry_index is None or snapshots[entry_index].observed_at >= close_time:
        return base
    entry = buy_with_budget(snapshots[entry_index].book.ask_levels(side), MAX_BUDGET)
    if entry.quantity <= 0:
        return base
    quantity = entry.quantity
    outflow = entry.buy_outflow
    maximum_profit = quantity - outflow
    if maximum_profit <= 0:
        base["status"] = "nonpositive_maximum_profit"
        return base
    target_amount = maximum_profit * TARGET_FRACTION
    entry_average = entry.gross / quantity
    preclose_time = close_time - timedelta(seconds=PRECLOSE_SECONDS)
    execution, exit_time, signals, rejected = protected_target_exit(
        snapshots,
        start_index=entry_index + 1,
        stop_time=preclose_time,
        side=side,
        quantity=quantity,
        outflow=outflow,
        target=target_amount,
    )
    exit_reason = "protected_profit_target"
    if execution is None:
        execution, exit_time = delayed_preclose_exit(
            snapshots,
            start_index=entry_index + 1,
            preclose_time=preclose_time,
            close_time=close_time,
            side=side,
            quantity=quantity,
        )
        exit_reason = "preclose_time_exit"
    base.update({
        "entry_execution_time": snapshots[entry_index].observed_at.isoformat(),
        "entry_request_id": snapshots[entry_index].request_id,
        "entry_contracts": decimal_text(quantity),
        "entry_gross": decimal_text(entry.gross),
        "entry_fee": decimal_text(entry.fee),
        "cash_deployed": decimal_text(outflow),
        "entry_average_price": decimal_text(entry_average),
        "maximum_settlement_profit": decimal_text(maximum_profit),
        "target_amount": decimal_text(target_amount),
        "target_signal_count": signals,
        "target_rejected_after_latency_count": rejected,
    })
    if execution is None or exit_time is None:
        base.update({
            "status": "settlement_pending_after_preclose_liquidity_failure",
            "exit_reason": "no_causal_full_depth_exit",
        })
        return base
    pnl = execution.sell_inflow - outflow
    base.update({
        "status": "completed_cash_exit",
        "exit_reason": exit_reason,
        "exit_execution_time": exit_time.isoformat(),
        "exit_gross": decimal_text(execution.gross),
        "exit_fee": decimal_text(execution.fee),
        "exit_average_price": decimal_text(execution.gross / execution.quantity),
        "realized_pnl": decimal_text(pnl),
        "profitable": pnl > 0,
    })
    return base


def latest_book_snapshot(
    points: Sequence[BookPoint], arrival_ms: Sequence[float], target_ms: float
) -> tuple[Snapshot | None, float | None]:
    index = bisect.bisect_right(arrival_ms, target_ms) - 1
    if index < 0:
        return None, None
    snapshot = points[index].snapshot
    stale = target_ms / 1000.0 - snapshot.observed_at.timestamp()
    if stale < 0 or stale > MAX_CAUSAL_STALENESS_SECONDS:
        return None, stale
    return snapshot, stale


def _yes_midpoint(snapshot: Snapshot | None) -> float | None:
    if snapshot is None:
        return None
    quote = favored_quote(snapshot.book)
    # favored_quote does not expose YES midpoint, so calculate from executable
    # YES bid/ask directly.
    yes_bids = snapshot.book.bid_levels("YES")
    yes_asks = snapshot.book.ask_levels("YES")
    if not yes_bids or not yes_asks:
        return None
    return float((yes_bids[-1][0] + yes_asks[0][0]) / Decimal("2"))


def aligned_grid(
    ticker: str,
    points: Sequence[BookPoint],
    brti: Sequence[FeedPoint],
    coinbase: Sequence[FeedPoint],
    kraken: Sequence[FeedPoint],
) -> list[dict[str, Any]]:
    close = market_close_utc(ticker)
    start = close - timedelta(minutes=5)
    book_times = [point.snapshot.observed_at.timestamp() * 1000.0 for point in points]
    feeds = {
        "brti": (brti, [point.arrival_ms for point in brti]),
        "coinbase": (coinbase, [point.arrival_ms for point in coinbase]),
        "kraken": (kraken, [point.arrival_ms for point in kraken]),
    }
    rows: list[dict[str, Any]] = []
    previous: dict[str, float | None] = {
        "brti": None,
        "coinbase": None,
        "kraken": None,
        "external": None,
        "yes_mid": None,
    }
    for second in range(301):
        grid_time = start + timedelta(seconds=second)
        target_ms = grid_time.timestamp() * 1000.0
        feed_values: dict[str, float | None] = {}
        staleness: dict[str, float | None] = {}
        for venue, (venue_points, venue_times) in feeds.items():
            point, stale = latest_point(venue_points, venue_times, target_ms)
            feed_values[venue] = None if point is None else point.value
            staleness[venue] = stale
        external_parts = [feed_values[name] for name in ("coinbase", "kraken") if feed_values[name] is not None]
        external = statistics.mean(external_parts) if external_parts else None
        snapshot, book_stale = latest_book_snapshot(points, book_times, target_ms)
        yes_mid = _yes_midpoint(snapshot)
        current = {
            "brti": feed_values["brti"],
            "coinbase": feed_values["coinbase"],
            "kraken": feed_values["kraken"],
            "external": external,
            "yes_mid": yes_mid,
        }
        changes = {
            f"{name}_change": (
                None if value is None or previous[name] is None else value - previous[name]
            )
            for name, value in current.items()
        }
        rows.append({
            "ticker": ticker,
            "grid_time": grid_time.isoformat(),
            "seconds_remaining": 300 - second,
            "brti": float_text(current["brti"], 2),
            "brti_staleness_seconds": float_text(staleness["brti"]),
            "coinbase_mid": float_text(current["coinbase"], 2),
            "coinbase_staleness_seconds": float_text(staleness["coinbase"]),
            "kraken_mid": float_text(current["kraken"], 2),
            "kraken_staleness_seconds": float_text(staleness["kraken"]),
            "external_consensus": float_text(current["external"], 2),
            "yes_midpoint": float_text(current["yes_mid"], 4),
            "orderbook_staleness_seconds": float_text(book_stale),
            **{name: float_text(value, 8) for name, value in changes.items()},
        })
        previous = current
    return rows


def pearson(pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(pairs) < 10:
        return None
    left = [pair[0] for pair in pairs]
    right = [pair[1] for pair in pairs]
    left_mean, right_mean = statistics.mean(left), statistics.mean(right)
    covariance = sum((x - left_mean) * (y - right_mean) for x, y in pairs)
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    if left_ss <= 0 or right_ss <= 0:
        return None
    return covariance / math.sqrt(left_ss * right_ss)


def lag_rows(aligned: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_market: dict[str, list[Mapping[str, Any]]] = {}
    for row in aligned:
        by_market.setdefault(str(row["ticker"]), []).append(row)
    output: list[dict[str, Any]] = []
    for leader_field, comparison in (
        ("external_change", "external_leads_brti"),
        ("yes_mid_change", "kalshi_orderbook_leads_brti"),
    ):
        for lag in LAGS:
            market_corrs: list[float] = []
            pair_count = 0
            for ticker, rows in by_market.items():
                pairs: list[tuple[float, float]] = []
                for index, row in enumerate(rows):
                    brti_index = index + lag
                    if brti_index < 0 or brti_index >= len(rows):
                        continue
                    left_text = str(row.get(leader_field, ""))
                    right_text = str(rows[brti_index].get("brti_change", ""))
                    if not left_text or not right_text:
                        continue
                    pairs.append((float(left_text), float(right_text)))
                correlation = pearson(pairs)
                if correlation is not None:
                    market_corrs.append(correlation)
                    pair_count += len(pairs)
            output.append({
                "comparison": comparison,
                "lag_seconds": lag,
                "interpretation": (
                    "leader_changes_first" if lag > 0 else
                    "same_second" if lag == 0 else
                    "brti_changes_first"
                ),
                "markets": len(market_corrs),
                "aligned_pairs": pair_count,
                "equal_market_mean_correlation": float_text(
                    statistics.mean(market_corrs) if market_corrs else None, 8
                ),
            })
    return output


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise AuditError(f"refusing empty CSV output: {path}")
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def best_lag(rows: Sequence[Mapping[str, Any]], comparison: str) -> Mapping[str, Any] | None:
    candidates = [
        row for row in rows
        if row["comparison"] == comparison and str(row["equal_market_mean_correlation"])
    ]
    return max(candidates, key=lambda row: float(row["equal_market_mean_correlation"])) if candidates else None


def markdown_report(
    *,
    capture_root: Path,
    correction: ClockCorrection,
    brti_summary: Mapping[str, Any],
    external_summary: Mapping[str, Any],
    manifests: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
    lags: Sequence[Mapping[str, Any]],
) -> str:
    ext_best = best_lag(lags, "external_leads_brti")
    book_best = best_lag(lags, "kalshi_orderbook_leads_brti")
    lines = [
        "# KXBTC15M synchronized live-feed audit",
        "",
        "**Outcome-blind, read-only prospective mechanics audit; frozen holdout sealed.**",
        "",
        f"Capture root: `{capture_root}`",
        "",
        "## Capture integrity",
        "",
        "| Check | Result |",
        "|---|---:|",
        f"| BRTI ticks | {brti_summary.get('tick_count', 'n/a')} |",
        f"| BRTI sequence gaps | {brti_summary.get('sequence_gaps', 'n/a')} |",
        f"| Coinbase ticker messages | {external_summary.get('counts', {}).get('coinbase.ticker', 'n/a')} |",
        f"| Kraken ticker messages | {external_summary.get('counts', {}).get('kraken.ticker', 'n/a')} |",
        f"| Validated order-book manifests | {len(manifests)} |",
        f"| Median clock correction before | {correction.before_seconds * 1000:.1f} ms |",
        f"| Median clock correction after | {correction.after_seconds * 1000:.1f} ms |",
        "| Outcomes read | no |",
        "| Orders placed | no |",
        "",
        "The order-book clock is the corrected raw HTTP response receipt time. Request-start "
        "timestamps are retained only for integrity checks and are never treated as executable availability.",
        "",
        "## Prospective H3 replay",
        "",
        "| Market | Status | Side | Decision | Entry | Exit | Reason | Realized P&L |",
        "|---|---|---|---|---|---|---|---:|",
    ]
    for row in actions:
        lines.append(
            f"| {row['ticker']} | {row['status']} | {row.get('side', '')} | "
            f"{row.get('decision_time', '')} | {row.get('entry_execution_time', '')} | "
            f"{row.get('exit_execution_time', '')} | {row.get('exit_reason', '')} | "
            f"{row.get('realized_pnl', '')} |"
        )
    lines.extend([
        "",
        "A realized P&L is reported only when archived depth supports a complete cash exit. "
        "No settlement result is read to complete an unresolved position.",
        "",
        "## Descriptive lead/lag",
        "",
        "| Comparison | Peak lag | Correlation | Markets |",
        "|---|---:|---:|---:|",
    ])
    for label, row in (("External consensus → BRTI", ext_best), ("Kalshi order book → BRTI", book_best)):
        if row is None:
            lines.append(f"| {label} | n/a | n/a | 0 |")
        else:
            lines.append(
                f"| {label} | {int(row['lag_seconds']):+d}s | "
                f"{row['equal_market_mean_correlation']} | {row['markets']} |"
            )
    lines.extend([
        "",
        "Positive lag means the named leader changes first and BRTI is measured later. "
        "This two-market result is descriptive capture evidence, not a fitted trading rule.",
        "",
        "## Interpretation boundary",
        "",
        "The frozen H3 mechanics are replayed exactly once on these newly captured markets. "
        "This does not open the separate 26-market holdout and does not select or tune a delta threshold. "
        "Clock correction is linearly interpolated between the two NTP checks; a production system must use "
        "a tightly synchronized host and fail closed on clock, sequence, freshness, or depth failures.",
        "",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/kxbtc15m_synchronized_capture"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    capture_root = args.capture_root.resolve()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    brti_summary_path = newest_summary(capture_root / "kalshi_brti")
    external_summary_path = newest_summary(capture_root / "external_btc")
    brti_summary, brti_uncorrected = load_brti(brti_summary_path)
    external_summary, external_uncorrected = load_external(external_summary_path)
    all_local_times = [point.arrival_ms for point in brti_uncorrected + external_uncorrected]
    before = statistics.median(parse_clock_offsets(capture_root / "clock_before.txt"))
    after = statistics.median(parse_clock_offsets(capture_root / "clock_after.txt"))
    correction = ClockCorrection(
        first_epoch_ms=int(min(all_local_times)),
        last_epoch_ms=int(max(all_local_times)),
        before_seconds=before,
        after_seconds=after,
    )
    brti = sorted(apply_clock_correction(brti_uncorrected, correction), key=lambda p: p.arrival_ms)
    external = sorted(apply_clock_correction(external_uncorrected, correction), key=lambda p: p.arrival_ms)
    coinbase = [point for point in external if point.venue == "coinbase"]
    kraken = [point for point in external if point.venue == "kraken"]
    manifest_paths = discover_orderbook_manifests(capture_root, repo_root)
    orderbooks, manifest_rows = load_orderbooks(manifest_paths, repo_root, correction)
    actions = [
        replay_h3_market(ticker, points, brti, coinbase, kraken)
        for ticker, points in sorted(orderbooks.items())
    ]
    aligned = [
        row
        for ticker, points in sorted(orderbooks.items())
        for row in aligned_grid(ticker, points, brti, coinbase, kraken)
    ]
    lags = lag_rows(aligned)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "kxbtc15m_synchronized_capture_manifests.csv", manifest_rows)
    write_csv(output_dir / "kxbtc15m_synchronized_capture_h3_actions.csv", actions)
    write_csv(output_dir / "kxbtc15m_synchronized_capture_aligned_1s.csv", aligned)
    write_csv(output_dir / "kxbtc15m_synchronized_capture_lags.csv", lags)
    report = markdown_report(
        capture_root=capture_root,
        correction=correction,
        brti_summary=brti_summary,
        external_summary=external_summary,
        manifests=manifest_rows,
        actions=actions,
        lags=lags,
    )
    report_path = output_dir / "KXBTC15M_SYNCHRONIZED_CAPTURE.md"
    report_path.write_text(report, encoding="utf-8")
    metadata = {
        "schema": SCHEMA,
        "capture_root": str(capture_root),
        "markets": sorted(orderbooks),
        "clock_correction_before_seconds": before,
        "clock_correction_after_seconds": after,
        "outcomes_read": False,
        "holdout_read": False,
        "orders_placed": False,
        "report": str(report_path),
    }
    (output_dir / "kxbtc15m_synchronized_capture_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print("KXBTC15M synchronized capture audit: PASS")
    print(f"Validated markets: {len(orderbooks)}")
    print(f"BRTI ticks: {len(brti)}")
    print(f"Coinbase quotes: {len(coinbase)}")
    print(f"Kraken quotes: {len(kraken)}")
    print("Outcome read: False")
    print("Holdout read: False")
    print("Orders placed: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, ValueError, KeyError) as exc:
        raise SystemExit(f"KXBTC15M synchronized capture error: {exc}") from exc
