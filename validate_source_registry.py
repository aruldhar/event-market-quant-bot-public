"""Validate the machine-readable source registry without network access."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.source_registry import (
    DEFAULT_SOURCE_REGISTRY_PATH,
    SourceRegistryError,
    load_source_registry,
    summarize_source_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE_REGISTRY_PATH,
        help=f"Registry JSON path (default: {DEFAULT_SOURCE_REGISTRY_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = load_source_registry(args.path)
    summary = summarize_source_registry(registry)
    print(f"Source registry: {args.path}")
    print(f"Schema: {summary['schema']}")
    print(f"Registry ID: {summary['registry_id']}")
    print(f"Sources: {summary['source_count']}")
    print(f"Quality policies: {summary['quality_policy_count']}")
    print(f"Validated sources: {summary['validated_source_count']}")
    print(f"Unresolved sources: {summary['unresolved_source_count']}")
    print(
        "Unresolved settlement sources: "
        f"{summary['unresolved_settlement_source_count']}"
    )
    print("Validation: PASS")


if __name__ == "__main__":
    try:
        main()
    except SourceRegistryError as exc:
        raise SystemExit(f"Source registry validation failed: {exc}") from exc
