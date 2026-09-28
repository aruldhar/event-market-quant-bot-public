"""CLI for bounded post-soak public Kalshi settlement observation."""
from __future__ import annotations

import argparse

from .kxbtcd_candidate_e_live_shadow_settlement_closeout import (
    run_live_shadow_settlement_closeout,
    LiveShadowSettlementCloseoutReceipt,
    wait_for_terminal_soak_manifest,
    write_live_shadow_settlement_closeout_receipt,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded read-only live-shadow settlement closeout")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--settlements", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--wait-seconds", type=float, default=3600)
    parser.add_argument("--poll-seconds", type=float, default=10)
    parser.add_argument("--manifest")
    parser.add_argument("--manifest-wait-seconds", type=float)
    args = parser.parse_args(argv)
    if (args.manifest is None) != (args.manifest_wait_seconds is None):
        parser.error("--manifest and --manifest-wait-seconds must be supplied together")
    if args.manifest:
        terminal = wait_for_terminal_soak_manifest(
            manifest_path=args.manifest, run_id=args.run_id,
            wait_seconds=args.manifest_wait_seconds, poll_seconds=args.poll_seconds,
        )
        if not terminal:
            receipt = LiveShadowSettlementCloseoutReceipt(
                args.run_id, "COLLECTOR_NOT_TERMINAL", (),
            )
            write_live_shadow_settlement_closeout_receipt(
                output_path=args.receipt, receipt=receipt,
            )
            return 2
    import requests
    receipt = run_live_shadow_settlement_closeout(
        run_id=args.run_id, store_path=args.store, archive_root=args.archive_root,
        settlements_output=args.settlements, receipt_output=args.receipt,
        session=requests.Session(), wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
    )
    return 0 if receipt.status in {"SETTLED", "NO_OPEN_POSITIONS"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
