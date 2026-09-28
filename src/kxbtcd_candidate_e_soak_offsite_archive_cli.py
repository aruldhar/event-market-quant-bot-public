"""CLI for terminal-only Candidate-E evidence archiving to a hardened S3 bucket."""
from __future__ import annotations

import argparse

from .kxbtcd_candidate_e_soak_offsite_archive import upload_terminal_run_archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive one completed Candidate-E run to private S3")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--raw-root", required=True)
    parser.add_argument("--telemetry-root", required=True)
    parser.add_argument("--live-shadow-root", required=True)
    parser.add_argument("--shadow-ledger", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--region")
    parser.add_argument("--sse", choices=("AES256", "aws:kms"), default="AES256")
    parser.add_argument("--kms-key-id")
    args = parser.parse_args(argv)
    if (args.sse == "aws:kms") != bool(args.kms_key_id):
        parser.error("--kms-key-id is required only with --sse aws:kms")
    import boto3
    client = boto3.session.Session(region_name=args.region).client("s3")
    upload_terminal_run_archive(
        client=client, bucket=args.bucket, prefix=args.prefix, run_id=args.run_id,
        raw_root=args.raw_root, telemetry_root=args.telemetry_root,
        live_shadow_root=args.live_shadow_root, shadow_ledger_path=args.shadow_ledger,
        receipt_path=args.receipt, sse=args.sse, kms_key_id=args.kms_key_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
