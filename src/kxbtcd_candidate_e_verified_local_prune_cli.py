"""CLI for explicitly pruning local evidence only after S3 verification."""
from __future__ import annotations

import argparse
import json

from .kxbtcd_candidate_e_verified_local_prune import prune_verified_local_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify S3 archive receipt before pruning one local Candidate-E run")
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--telemetry-root", required=True)
    parser.add_argument("--live-shadow-root", required=True)
    parser.add_argument("--region")
    parser.add_argument("--confirm-prune", action="store_true")
    args = parser.parse_args(argv)
    import boto3
    client = boto3.session.Session(region_name=args.region).client("s3")
    result = prune_verified_local_run(
        client=client, receipt_path=args.receipt, raw_root=args.raw_root,
        telemetry_root=args.telemetry_root, live_shadow_root=args.live_shadow_root,
        confirm_prune=args.confirm_prune,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
