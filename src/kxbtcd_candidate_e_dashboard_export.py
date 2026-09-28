"""Atomic, sanitized export for the isolated private dashboard.

The exporter consumes only the pure dashboard projection.  It never opens a
venue connection or handles a credential, and its output is a one-way display
artifact rather than the trading ledger of record.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Iterable, Mapping

from .kxbtcd_candidate_e_dashboard_projection import (
    DashboardProjectionError,
    project_confirmed_ledger_events,
)
from .kxbtcd_candidate_e_soak_archive import write_json_atomic


class DashboardExportError(ValueError):
    pass


DASHBOARD_SNAPSHOT_SCHEMA_VERSION = "kxbtcd_candidate_e_dashboard_snapshot.v1"
SAFE_TEXT = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")


def _safe_text(value: object) -> str:
    if not isinstance(value, str) or not SAFE_TEXT.fullmatch(value):
        raise DashboardExportError("dashboard text field is invalid")
    if any(marker in value.upper() for marker in ("SECRET", "PRIVATE_KEY", "API_KEY", "TOKEN")):
        raise DashboardExportError("dashboard text contains a credential marker")
    return value


def _utc(value: object) -> str:
    if not isinstance(value, str):
        raise DashboardExportError("dashboard generated UTC is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DashboardExportError("dashboard generated UTC is invalid") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise DashboardExportError("dashboard generated UTC must be explicit UTC")
    return value


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, bool) or isinstance(value, int) or value is None:
        return value
    raise DashboardExportError("dashboard projection value is not serializable")


def build_dashboard_snapshot(*, events: Iterable[Mapping[str, object]], generated_utc: str) -> dict[str, object]:
    """Build a credential-free dashboard document from confirmed ledger facts."""
    try:
        projection = project_confirmed_ledger_events(events)
    except DashboardProjectionError as exc:
        raise DashboardExportError("dashboard projection is invalid") from exc
    trades = []
    for trade in projection.trades:
        trades.append({key: _json_value(value) for key, value in asdict(trade).items()})
    return {
        "schema_version": DASHBOARD_SNAPSHOT_SCHEMA_VERSION,
        "generated_utc": _utc(generated_utc),
        "summary": {
            "total_realized_net_pnl": _json_value(projection.total_realized_net_pnl),
            "closed_trade_count": projection.closed_trade_count,
            "open_position_count": projection.open_position_count,
        },
        "trades": trades,
    }


def export_dashboard_snapshot(*, events: Iterable[Mapping[str, object]], generated_utc: str,
                              output_path: str | Path) -> dict[str, object]:
    """Atomically replace the dashboard-only snapshot after complete projection."""
    output = Path(output_path)
    if output.name != "dashboard_snapshot.json":
        raise DashboardExportError("dashboard output must use the canonical snapshot filename")
    snapshot = build_dashboard_snapshot(events=events, generated_utc=generated_utc)
    write_json_atomic(output, snapshot)
    return snapshot
