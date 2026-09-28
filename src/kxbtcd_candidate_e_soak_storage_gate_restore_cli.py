"""CLI for restoring verified shakedown evidence needed by a storage gate."""
from __future__ import annotations

import argparse
import json

from .kxbtcd_candidate_e_soak_storage_gate_restore import restore_storage_gate_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore verified storage-gate evidence from S3")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--telemetry-root", required=True)
    parser.add_argument("--region")
    args = parser.parse_args(argv)
    import boto3
    client = boto3.session.Session(region_name=args.region).client("s3")
    result = restore_storage_gate_evidence(
        client=client, bucket=args.bucket, prefix=args.prefix, run_id=args.run_id,
        receipt_path=args.receipt, raw_root=args.raw_root,
        telemetry_root=args.telemetry_root,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
