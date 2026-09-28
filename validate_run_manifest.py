"""Validate one completed collection-run manifest and all referenced files."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.config import DEFAULT_MANIFEST_ROOT
from src.run_validation import (
    RunValidationError,
    find_latest_manifest,
    validate_run_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        help="Manifest JSON path; defaults to the newest manifest",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path("."),
        help="Repository root used to resolve repository-relative artifact paths",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest_path = args.manifest or find_latest_manifest(DEFAULT_MANIFEST_ROOT)
    result = validate_run_manifest(
        manifest_path,
        repository_root=args.repository_root,
    )
    summary = result["summary"]

    print(f"Manifest: {result['manifest_path']}")
    print(f"Run ID: {result['run_id']}")
    print(f"Collector: {result['collector']}")
    print(f"Status: {result['status']}")
    print(f"Git commit: {result['git_commit'] or 'unavailable'}")
    print(f"Git worktree dirty at start: {result['git_worktree_dirty']}")
    print(f"Raw files: {summary['raw_file_count']}")
    print(f"Raw records: {summary['raw_record_count']}")
    print(f"Raw error records: {summary['raw_error_record_count']}")
    print(f"Derived CSV files: {summary['derived_csv_count']}")
    print(f"Derived rows: {summary['derived_row_count']}")
    if "runtime_event_count" in summary:
        print(f"Runtime event files: {summary['runtime_event_file_count']}")
        print(f"Runtime events: {summary['runtime_event_count']}")
        print(f"Runtime error events: {summary['runtime_error_event_count']}")
    print("Validation: PASS")


if __name__ == "__main__":
    try:
        main()
    except RunValidationError as exc:
        raise SystemExit(f"Validation: FAIL\n{exc}") from exc
