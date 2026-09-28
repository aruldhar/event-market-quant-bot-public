"""Checkpoint 21N-Z-F crash-safe closed raw-segment archival.

This module owns only the lifecycle of an already-closed raw runtime segment.

It does not:
- open market-data connections;
- select markets;
- compute model features/signals;
- access settlement outcomes;
- place orders;
- delete raw evidence before a verified compressed artifact and descriptor exist.

Closed segments are compressed losslessly with ZSTD and verified by streaming
decompression back to the original raw SHA-256 before raw deletion.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

import pyarrow as pa


COMPRESSION = "zstd"
DESCRIPTOR_SCHEMA = "candidate_e_closed_raw_segment.v1"
COPY_CHUNK_BYTES = 1024 * 1024


class SoakArchiveError(RuntimeError):
    pass


def file_sha256(path: str | Path) -> str:
    p = Path(path)
    h = sha256()

    with p.open("rb") as f:
        for chunk in iter(
            lambda: f.read(COPY_CHUNK_BYTES),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def decompressed_sha256_zstd(
    path: str | Path,
) -> str:
    p = Path(path)
    h = sha256()

    with pa.OSFile(str(p), "rb") as source:
        with pa.CompressedInputStream(
            source,
            COMPRESSION,
        ) as compressed:
            while True:
                chunk = compressed.read(
                    COPY_CHUNK_BYTES
                )
                if not chunk:
                    break
                h.update(chunk)

    return h.hexdigest()


def _fsync_directory(path: Path) -> None:
    # Production deployment is Linux/POSIX. Windows is an offline
    # development/test environment and does not provide the same
    # directory-fsync semantics through this interface.
    if os.name != "posix":
        return

    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_atomic(
    path: str | Path,
    value: dict[str, Any],
) -> None:
    target = Path(path)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = target.with_name(
        target.name + ".tmp"
    )

    if temp.exists():
        raise SoakArchiveError(
            f"temporary descriptor already exists: {temp}"
        )

    payload = (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    with temp.open(
        "x",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp, target)
    _fsync_directory(target.parent)


def _compress_raw_to_temp(
    *,
    raw_path: Path,
    compressed_temp_path: Path,
) -> None:
    if compressed_temp_path.exists():
        raise SoakArchiveError(
            "temporary compressed path already exists"
        )

    with pa.OSFile(
        str(compressed_temp_path),
        "wb",
    ) as sink:
        with pa.CompressedOutputStream(
            sink,
            COMPRESSION,
        ) as compressed:
            with raw_path.open("rb") as raw:
                while True:
                    chunk = raw.read(
                        COPY_CHUNK_BYTES
                    )
                    if not chunk:
                        break
                    compressed.write(chunk)

    # PyArrow close flushes the codec and sink. Reopen the completed
    # temporary file with a writable descriptor solely so fsync works
    # consistently on both Windows validation and Linux production.
    fd = os.open(str(compressed_temp_path), os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def build_closed_segment_descriptor(
    *,
    source: str,
    segment_start_utc: str,
    segment_end_utc: str,
    record_count: int,
    raw_size_bytes: int,
    raw_sha256: str,
    compressed_size_bytes: int,
    compressed_sha256: str,
    compressed_filename: str,
) -> dict[str, Any]:
    if not str(source).strip():
        raise SoakArchiveError(
            "source must be non-empty"
        )

    if (
        isinstance(record_count, bool)
        or not isinstance(record_count, int)
        or record_count < 0
    ):
        raise SoakArchiveError(
            "record_count must be a nonnegative integer"
        )

    return {
        "schema_version": DESCRIPTOR_SCHEMA,
        "source": str(source),
        "segment_start_utc": str(
            segment_start_utc
        ),
        "segment_end_utc": str(
            segment_end_utc
        ),
        "record_count": record_count,
        "uncompressed_size_bytes": int(
            raw_size_bytes
        ),
        "uncompressed_sha256": str(
            raw_sha256
        ),
        "compressed_size_bytes": int(
            compressed_size_bytes
        ),
        "compressed_sha256": str(
            compressed_sha256
        ),
        "compression": COMPRESSION,
        "compressed_filename": str(
            compressed_filename
        ),
    }


def close_raw_segment(
    *,
    raw_path: str | Path,
    source: str,
    segment_start_utc: str,
    segment_end_utc: str,
    record_count: int,
) -> dict[str, Any]:
    """Compress, verify, describe, then delete one closed raw segment.

    The input file must already have been flush/fsync/closed by the
    RuntimeRawJournal owner.
    """
    raw = Path(raw_path)

    if not raw.is_file():
        raise SoakArchiveError(
            f"closed raw segment missing: {raw}"
        )

    compressed = raw.with_name(
        raw.name + ".zst"
    )
    compressed_temp = raw.with_name(
        raw.name + ".zst.tmp"
    )
    descriptor = raw.with_name(
        raw.name + ".descriptor.json"
    )

    if compressed.exists():
        raise SoakArchiveError(
            "final compressed artifact already exists"
        )

    if descriptor.exists():
        raise SoakArchiveError(
            "closed-segment descriptor already exists"
        )

    raw_size = raw.stat().st_size
    raw_sha = file_sha256(raw)

    _compress_raw_to_temp(
        raw_path=raw,
        compressed_temp_path=compressed_temp,
    )

    verified_raw_sha = (
        decompressed_sha256_zstd(
            compressed_temp
        )
    )

    if verified_raw_sha != raw_sha:
        raise SoakArchiveError(
            "compressed segment does not reproduce raw SHA-256"
        )

    compressed_size = (
        compressed_temp.stat().st_size
    )
    compressed_sha = file_sha256(
        compressed_temp
    )

    os.replace(
        compressed_temp,
        compressed,
    )
    _fsync_directory(raw.parent)

    descriptor_value = (
        build_closed_segment_descriptor(
            source=source,
            segment_start_utc=segment_start_utc,
            segment_end_utc=segment_end_utc,
            record_count=record_count,
            raw_size_bytes=raw_size,
            raw_sha256=raw_sha,
            compressed_size_bytes=compressed_size,
            compressed_sha256=compressed_sha,
            compressed_filename=compressed.name,
        )
    )

    write_json_atomic(
        descriptor,
        descriptor_value,
    )

    # Raw deletion is intentionally last.
    raw.unlink()
    _fsync_directory(raw.parent)

    return descriptor_value


def validate_closed_segment(
    descriptor_path: str | Path,
) -> dict[str, Any]:
    descriptor = Path(descriptor_path)

    try:
        value = json.loads(
            descriptor.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise SoakArchiveError(
            "closed-segment descriptor unreadable"
        ) from exc

    if not isinstance(value, dict):
        raise SoakArchiveError(
            "closed-segment descriptor root must be object"
        )

    required = (
        "schema_version",
        "source",
        "segment_start_utc",
        "segment_end_utc",
        "record_count",
        "uncompressed_size_bytes",
        "uncompressed_sha256",
        "compressed_size_bytes",
        "compressed_sha256",
        "compression",
        "compressed_filename",
    )

    if any(k not in value for k in required):
        raise SoakArchiveError(
            "closed-segment descriptor missing required field"
        )

    if value["schema_version"] != DESCRIPTOR_SCHEMA:
        raise SoakArchiveError(
            "closed-segment descriptor schema mismatch"
        )

    if value["compression"] != COMPRESSION:
        raise SoakArchiveError(
            "closed-segment compression mismatch"
        )

    compressed = descriptor.parent / str(
        value["compressed_filename"]
    )

    if not compressed.is_file():
        raise SoakArchiveError(
            "verified compressed artifact missing"
        )

    if (
        compressed.stat().st_size
        != value["compressed_size_bytes"]
    ):
        raise SoakArchiveError(
            "compressed artifact size mismatch"
        )

    if (
        file_sha256(compressed)
        != value["compressed_sha256"]
    ):
        raise SoakArchiveError(
            "compressed artifact SHA-256 mismatch"
        )

    if (
        decompressed_sha256_zstd(compressed)
        != value["uncompressed_sha256"]
    ):
        raise SoakArchiveError(
            "decompressed raw SHA-256 mismatch"
        )

    return value
