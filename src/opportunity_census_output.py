"""Derived writing for event identities and source-native contract snapshots."""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .opportunity_census_adapters import (
    CONTRACT_SNAPSHOT_COLUMNS,
    CONTRACT_SNAPSHOT_SCHEMA_VERSION,
    DISCOVERY_COLUMNS,
    DISCOVERY_SCHEMA_VERSION,
)


class CensusOutputError(RuntimeError):
    """Raised when normalized census output cannot be written safely."""


def write_discovery_csv(
    output_path: str | Path,
    rows: Iterable[Mapping[str, Any]],
) -> Path:
    """Atomically write normalized event discovery rows with a fixed schema."""
    return _write_fixed_csv(
        output_path,
        rows,
        columns=DISCOVERY_COLUMNS,
        schema_version=DISCOVERY_SCHEMA_VERSION,
        row_kind="Discovery",
    )


def write_contract_snapshot_csv(
    output_path: str | Path,
    rows: Iterable[Mapping[str, Any]],
) -> Path:
    """Atomically write source-native contract snapshot rows with a fixed schema."""
    return _write_fixed_csv(
        output_path,
        rows,
        columns=CONTRACT_SNAPSHOT_COLUMNS,
        schema_version=CONTRACT_SNAPSHOT_SCHEMA_VERSION,
        row_kind="Contract snapshot",
    )


def _write_fixed_csv(
    output_path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    columns: tuple[str, ...],
    schema_version: str,
    row_kind: str,
) -> Path:
    path = Path(output_path)
    rows_list = [dict(row) for row in rows]
    for index, row in enumerate(rows_list):
        if set(row) != set(columns):
            raise CensusOutputError(
                f"{row_kind} row {index} columns do not match census schema"
            )
        if row["schema_version"] != schema_version:
            raise CensusOutputError(
                f"{row_kind} row {index} has unsupported schema version"
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex[:8]}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns))
            writer.writeheader()
            writer.writerows(rows_list)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except (OSError, csv.Error, TypeError, ValueError) as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise CensusOutputError(f"Could not write census CSV: {exc}") from exc
    return path.resolve()
