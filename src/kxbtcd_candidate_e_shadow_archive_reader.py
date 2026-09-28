"""Read verified, closed soak segments for offline shadow evaluation only.

The reader accepts only descriptor-verified Zstandard JSONL artifacts.  It has
no transport, credential, order, state-store, or write dependency, so it can be
resource-isolated from a running collection or future execution process.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import pyarrow as pa

from .kxbtcd_candidate_e_soak_archive import COMPRESSION, validate_closed_segment


ALLOWED_SOURCES = frozenset(
    {
        "kalshi_production_ws",
        "kalshi_production_rest",
        "coinbase_exchange_ws",
        "coinbase_exchange_rest",
    }
)
READ_CHUNK_BYTES = 1024 * 1024


class ShadowArchiveReaderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArchivedRawRecord:
    source: str
    descriptor_path: Path
    record: dict[str, Any]


def iter_verified_closed_records(
    descriptor_paths: Iterable[str | Path],
) -> Iterator[ArchivedRawRecord]:
    """Yield parsed records from immutable, descriptor-verified closed segments.

    A malformed JSON line, unterminated line, source mismatch, or descriptor
    record-count disagreement stops the entire reader.  This avoids silently
    turning incomplete evidence into a shadow-scenario result.
    """
    for value in descriptor_paths:
        descriptor_path = Path(value)
        descriptor = validate_closed_segment(descriptor_path)
        source = descriptor["source"]
        if source not in ALLOWED_SOURCES:
            raise ShadowArchiveReaderError("closed segment source is not allowed")

        compressed_path = descriptor_path.parent / descriptor["compressed_filename"]
        count = 0
        pending = b""
        with pa.OSFile(str(compressed_path), "rb") as raw:
            with pa.CompressedInputStream(raw, COMPRESSION) as stream:
                while True:
                    chunk = stream.read(READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    pieces = (pending + chunk).split(b"\n")
                    pending = pieces.pop()
                    for line in pieces:
                        if not line:
                            raise ShadowArchiveReaderError("closed segment contains blank JSONL line")
                        try:
                            record = json.loads(line)
                        except (UnicodeError, json.JSONDecodeError) as exc:
                            raise ShadowArchiveReaderError(
                                "closed segment contains invalid JSONL record"
                            ) from exc
                        if not isinstance(record, dict):
                            raise ShadowArchiveReaderError(
                                "closed segment JSONL record must be object"
                            )
                        count += 1
                        yield ArchivedRawRecord(
                            source=source,
                            descriptor_path=descriptor_path,
                            record=record,
                        )

        if pending:
            raise ShadowArchiveReaderError("closed segment ends with unterminated JSONL record")
        if count != descriptor["record_count"]:
            raise ShadowArchiveReaderError("closed segment record count mismatch")
