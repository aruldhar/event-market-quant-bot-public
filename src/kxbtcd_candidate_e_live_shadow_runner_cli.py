"""Process-only CLI for the isolated live-shadow simulation service."""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from decimal import Decimal

from .kxbtcd_candidate_e_live_shadow_runner import process_live_shadow_snapshot
from .kxbtcd_candidate_e_live_shadow_micro_simulator import (
    MARKET_UNIVERSES,
    MOVING_ATM_ELEVEN,
    PROFIT_TARGET_MULTIPLIERS,
    STOP_LOSS_FRACTIONS,
)
from .kxbtcd_candidate_e_live_shadow_simulation_store import LiveShadowSimulationStore
from .kxbtcd_candidate_e_live_shadow_snapshot_reader import (
    LiveShadowSnapshotReaderError,
    read_live_shadow_snapshot,
)
from .kxbtcd_candidate_e_live_shadow_settlement_feed import (
    LiveShadowSettlementFeedError,
    read_live_shadow_settlements,
)
from .kxbtcd_candidate_e_live_shadow_settlement_closeout import (
    LiveShadowSettlementCloseoutError,
    read_live_shadow_settlement_closeout_receipt,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the isolated read-only live-shadow simulator")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--dashboard-output")
    parser.add_argument("--dashboard-read-model")
    parser.add_argument("--settlements")
    parser.add_argument("--settlement-closeout-receipt")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--market-universe", choices=sorted(MARKET_UNIVERSES),
                        default=MOVING_ATM_ELEVEN)
    parser.add_argument(
        "--primary-stop-loss", type=Decimal, choices=sorted(STOP_LOSS_FRACTIONS),
        help="dynamic full-book stop loss for edge_002 only (for example 0.20)",
    )
    parser.add_argument(
        "--primary-profit-target", type=Decimal, choices=sorted(PROFIT_TARGET_MULTIPLIERS),
        default=Decimal("1.00"),
        help="retained net-edge multiplier for edge_002 only (1.00, 1.50, or 2.00)",
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    if args.dashboard_output is None and args.dashboard_read_model is None:
        parser.error("at least one dashboard output is required")
    store = LiveShadowSimulationStore(args.store)
    try:
        while True:
            try:
                snapshot = read_live_shadow_snapshot(args.snapshot)
                settlements = ()
                if args.settlements:
                    try:
                        settlements = read_live_shadow_settlements(
                            path=args.settlements, run_id=snapshot.run_id)
                    except LiveShadowSettlementFeedError:
                        # The collector has not published a final result yet.
                        # This is normal, including before the first rollover.
                        settlements = ()
                process_live_shadow_snapshot(
                    store=store,
                    snapshot=snapshot,
                    dashboard_output=args.dashboard_output,
                    dashboard_read_model_output=args.dashboard_read_model,
                    settlements=settlements,
                    market_universe=args.market_universe,
                    stop_loss_fraction=args.primary_stop_loss,
                    profit_target_multiplier=args.primary_profit_target,
                )
                if args.settlement_closeout_receipt:
                    try:
                        read_live_shadow_settlement_closeout_receipt(
                            path=args.settlement_closeout_receipt,
                            run_id=snapshot.run_id,
                        )
                    except LiveShadowSettlementCloseoutError:
                        pass
                    else:
                        return 0
            except LiveShadowSnapshotReaderError as exc:
                if args.once:
                    raise
                print(f"LIVE SHADOW INPUT UNAVAILABLE: {type(exc).__name__}", file=sys.stderr)
            except sqlite3.OperationalError as exc:
                # A concurrent reader (Grafana, an ad-hoc query) can hold the
                # shared read-model DB past the writer's busy timeout. The
                # authoritative store is already committed; the next poll's
                # cursor catch-up replays anything the projection missed.
                if args.once or "locked" not in str(exc):
                    raise
                print(f"LIVE SHADOW READ MODEL BUSY, RETRYING: {exc}", file=sys.stderr)
            if args.once:
                return 0
            time.sleep(args.poll_seconds)
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
