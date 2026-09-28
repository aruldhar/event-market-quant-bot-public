"""CLI boundary for producing one private dashboard snapshot from JSONL facts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .kxbtcd_candidate_e_dashboard_export import (
    DashboardExportError,
    export_dashboard_snapshot,
)


def _ledger_events(path: str | Path):
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    raise DashboardExportError("ledger JSONL contains a blank record")
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DashboardExportError("ledger JSONL record is invalid") from exc
    except OSError as exc:
        raise DashboardExportError("ledger JSONL is unreadable") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a sanitized private dashboard snapshot")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--generated-utc", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    snapshot = export_dashboard_snapshot(
        events=_ledger_events(args.ledger), generated_utc=args.generated_utc,
        output_path=args.output,
    )
    print(json.dumps({
        "schema_version": snapshot["schema_version"],
        "closed_trade_count": snapshot["summary"]["closed_trade_count"],
        "open_position_count": snapshot["summary"]["open_position_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DashboardExportError as exc:
        print("PRIVATE DASHBOARD EXPORT: FAIL CLOSED")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
