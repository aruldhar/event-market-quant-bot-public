"""21N-Y-A3: normalize snapshot quantities BEFORE frozen exact replay.

No paid update is rounded. No negative replay balance is clamped. All inputs
are copied; preserved raw snapshots and earlier replay artifacts stay intact.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from .kxbtcd_candidate_e_v2_execution_quantity_transport_amendment import canonicalize_execution_quantity
from .kxbtcd_candidate_e_v2_disk_timeline import build_disk_timeline, DiskTimeline
from .kxbtcd_candidate_e_july10_outcome_blind_binding import _validate_replay_ticker_artifact
from .predexon_full_ladder_replay import audit_ticker, rows_by_snapshot_pair
from .predexon_segment_safe_replay import build_verified_segments

AUDIT_SCHEMA = "kxbtcd_candidate_e_v2_replay_precision_audit.v1"
QUANTUM = Decimal("0.01")


def quantity(value, *, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{label}: invalid quantity") from error
    if not number.is_finite():
        raise ValueError(f"{label}: quantity must be finite")
    # The inherited Decimal replay has precision 28. Refuse values for which
    # cent arithmetic could silently round rather than infer a new regime.
    if abs(number) >= Decimal("1e20"):
        raise ValueError(f"{label}: quantity outside exact replay range")
    return number


def normalize_snapshots(snapshots):
    output = []
    audit = {"levels_checked": 0, "levels_normalized": 0,
             "zero_levels_removed": 0, "max_absolute_residue": "0", "examples": []}
    maximum = Decimal(0)
    for index, snapshot in enumerate(snapshots):
        copy = dict(snapshot)
        for side in ("yes_bids", "yes_asks"):
            levels = []
            prices = set()
            for level in snapshot[side]:
                price = Decimal(str(level["price"]))
                if not price.is_finite() or not Decimal(0) <= price <= Decimal(100):
                    raise ValueError("invalid snapshot price")
                if price in prices:
                    raise ValueError("duplicate snapshot price level")
                prices.add(price)
                original = quantity(level["size"], label="snapshot")
                with localcontext() as context:
                    context.prec = 50
                    normalized = canonicalize_execution_quantity(original)
                    residue = abs(original - normalized)
                audit["levels_checked"] += 1
                if original != normalized:
                    audit["levels_normalized"] += 1
                    maximum = max(maximum, residue)
                    if len(audit["examples"]) < 20:
                        audit["examples"].append({"snapshot_index": index, "side": side,
                            "price": str(price), "original": str(original), "normalized": str(normalized)})
                if normalized == 0:
                    audit["zero_levels_removed"] += 1
                    continue
                levels.append({**level, "size": str(normalized)})
            copy[side] = levels
        output.append(copy)
    audit["max_absolute_residue"] = str(maximum)
    return output, audit


def validate_paid_quantities(rows):
    for row in rows:
        delta = quantity(row["delta_fp"], label="paid delta")
        if delta % QUANTUM:
            raise ValueError("paid delta is not exactly on 0.01 grid; no rounding permitted")
        price = Decimal(str(row["price_dollars"]))
        if not price.is_finite() or not Decimal(0) <= price <= Decimal(1):
            raise ValueError("invalid paid price")
        if str(row["side"]) not in ("yes", "no"):
            raise ValueError("invalid paid side")


def bounds(segments):
    return [[s.start_timestamp, s.end_timestamp] for s in segments]


def precision_audit(*, ticker, snapshots, paid_rows, baseline_path=None):
    """Audit every pair; exact grid makes zero-tolerance comparison possible."""
    validate_paid_quantities(paid_rows)
    normalized, normalization = normalize_snapshots(snapshots)
    original_summary, original_segments, original_pairs = audit_ticker(
        ticker=ticker, snapshots=snapshots, paid_rows=paid_rows)
    if baseline_path is not None:
        baseline = SimpleNamespace(segments=[SimpleNamespace(start_timestamp_ms=s.start_timestamp,
            end_timestamp_ms=s.end_timestamp) for s in original_segments])
        _validate_replay_ticker_artifact(path=baseline_path, ticker=ticker, timeline=baseline)
    revised_summary, revised_segments, revised_pairs = audit_ticker(
        ticker=ticker, snapshots=normalized, paid_rows=paid_rows)
    exact_segments, exact_pairs = build_verified_segments(
        normalized, rows_by_snapshot_pair(normalized, paid_rows), epsilon=Decimal(0))
    if exact_pairs != revised_pairs or exact_segments != revised_segments:
        raise ValueError("normalized replay differs from strict zero-tolerance audit")
    changed = []
    remaining = []
    for index, (old, new) in enumerate(zip(original_pairs, revised_pairs)):
        detail = {"pair_index": index, "start_timestamp_ms": int(snapshots[index]["timestamp"]),
                  "end_timestamp_ms": int(snapshots[index + 1]["timestamp"])}
        if old != new:
            changed.append({**detail, "before": asdict(old), "after": asdict(new)})
        if not new.exact:
            remaining.append({**detail, "result": asdict(new)})
    report = {"schema_version": AUDIT_SCHEMA, "ticker": ticker,
              "normalization": normalization, "before": asdict(original_summary),
              "after": asdict(revised_summary), "before_bounds": bounds(original_segments),
              "after_bounds": bounds(revised_segments), "changed_pairs": changed,
              "remaining_unreconciled_pairs": remaining,
              "strict_zero_tolerance_verified": True,
              "candidate_e_scored": False, "outcomes_accessed": False,
              "strategy_pnl_calculated": False, "orders_placed": 0, "network_requests": 0}
    return normalized, report


def validate_precision_cache(timeline):
    report = timeline.metadata.get("replay_precision_audit", {})
    if (report.get("schema_version") != AUDIT_SCHEMA or report.get("ticker") != timeline.ticker
            or report.get("strict_zero_tolerance_verified") is not True):
        raise ValueError("missing or invalid precision audit")
    observed = [[s.start_timestamp_ms, s.end_timestamp_ms] for s in timeline.segments]
    if report.get("after_bounds") != observed:
        raise ValueError("precision cache boundaries differ from revised audit")
    for key in ("candidate_e_scored", "outcomes_accessed", "strategy_pnl_calculated"):
        if report.get(key) is not False:
            raise ValueError("precision audit safety mismatch")
    for key in ("orders_placed", "network_requests"):
        if type(report.get(key)) is not int or report[key] != 0:
            raise ValueError("precision audit safety mismatch")
    return report


def build_precision_timeline(*, path: Path, ticker, snapshots, paid_rows, identity,
                             baseline_path=None, progress=lambda message: None):
    if path.exists():
        raise FileExistsError(f"refusing to overwrite cache: {path}")
    progress(f"{ticker}: comparing original and snapshot-normalized replay")
    normalized, report = precision_audit(ticker=ticker, snapshots=snapshots,
        paid_rows=paid_rows, baseline_path=baseline_path)
    # Original disk builder and replay functions operate on a new normalized
    # snapshot view. No function replacement or edits to frozen parents.
    build_disk_timeline(path=path, ticker=ticker, snapshots=normalized,
        paid_rows=paid_rows, identity=identity, progress=progress)
    with sqlite3.connect(path) as connection:
        metadata = json.loads(connection.execute("SELECT payload FROM metadata").fetchone()[0])
        metadata["replay_precision_audit"] = report
        connection.execute("UPDATE metadata SET payload=?", (json.dumps(metadata, sort_keys=True),))
    timeline = DiskTimeline(path)
    try:
        validate_precision_cache(timeline)
    finally:
        timeline.close()
    return report
