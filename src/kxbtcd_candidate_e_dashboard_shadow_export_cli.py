"""CLI boundary for an isolated live-shadow dashboard snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .kxbtcd_candidate_e_dashboard_export import DashboardExportError
from .kxbtcd_candidate_e_dashboard_shadow_export import export_shadow_dashboard_snapshot


def _shadow_events(path: str | Path):
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    raise DashboardExportError("shadow ledger JSONL contains a blank record")
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DashboardExportError("shadow ledger JSONL record is invalid") from exc
    except OSError as exc:
        raise DashboardExportError("shadow ledger JSONL is unreadable") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export an isolated live-shadow dashboard snapshot")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--generated-utc", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    snapshot = export_shadow_dashboard_snapshot(
        events=_shadow_events(args.ledger), generated_utc=args.generated_utc,
        output_path=args.output,
    )
    print(json.dumps({
        "schema_version": snapshot["schema_version"],
        "pnl_basis": snapshot["pnl_basis"],
        "simulated_closed_trade_count": snapshot["summary"]["simulated_closed_trade_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DashboardExportError as exc:
        print("PRIVATE SHADOW DASHBOARD EXPORT: FAIL CLOSED")
        print(f"{type(exc).__name__}: {exc}")
        raise SystemExit(1)
