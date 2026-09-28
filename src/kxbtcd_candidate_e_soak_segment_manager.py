"""Checkpoint 21N-Z-F UTC-hour raw segment manager.

Wraps RuntimeRawJournal with:
- source-specific UTC-clock-hour segmentation;
- runtime-session-specific filenames so restart fragments cannot collide;
- explicit final partial-segment closure;
- crash recovery of intact raw evidence;
- fail-closed treatment of missing or inconsistent evidence.

No market networking, model logic, outcomes, P&L, or execution exists here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Mapping

from .kxbtcd_candidate_e_runtime_raw_journal import (
    ALLOWED_RUNTIME_SOURCES,
    RuntimeRawJournal,
)
from .kxbtcd_candidate_e_soak_archive import (
    SoakArchiveError,
    close_raw_segment,
    file_sha256,
    validate_closed_segment,
)


RAW_SCHEMA = "candidate_e_runtime_raw_record.v1"

_INSTANCE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
)

_RAW_NAME_RE = re.compile(
    r"^(?P<hour>\d{8}T\d{6}Z)__"
    r"(?P<instance>[A-Za-z0-9][A-Za-z0-9._-]{0,127})"
    r"\.jsonl$"
)


class SoakSegmentManagerError(RuntimeError):
    pass


@dataclass
class _ActiveSegment:
    hour_start: datetime
    raw_path: Path
    journal: RuntimeRawJournal


@dataclass(frozen=True)
class RecoverySummary:
    verified_closed_segments: int
    archived_raw_segments: int
    discarded_temporary_compressed: int
    discarded_temporary_descriptors: int
    discarded_unverified_compressed: int
    deleted_redundant_raw: int


def parse_utc(value: str) -> datetime:
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SoakSegmentManagerError(
            "received_utc must be ISO-8601"
        ) from exc

    if dt.tzinfo is None:
        raise SoakSegmentManagerError(
            "received_utc must be timezone-aware"
        )

    return dt.astimezone(timezone.utc)


def utc_hour_start(value: str) -> datetime:
    dt = parse_utc(value)
    return dt.replace(
        minute=0,
        second=0,
        microsecond=0,
    )


def hour_token(hour_start: datetime) -> str:
    dt = hour_start.astimezone(timezone.utc)
    if (
        dt.minute != 0
        or dt.second != 0
        or dt.microsecond != 0
    ):
        raise SoakSegmentManagerError(
            "segment hour must be UTC-hour aligned"
        )

    return dt.strftime("%Y%m%dT%H0000Z")


def hour_bounds_text(
    hour_start: datetime,
) -> tuple[str, str]:
    start = hour_start.astimezone(timezone.utc)
    end = start + timedelta(hours=1)

    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return

    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _validate_instance_id(value: str) -> str:
    text = str(value).strip()
    if not _INSTANCE_RE.fullmatch(text):
        raise SoakSegmentManagerError(
            "segment_instance_id contains unsafe characters"
        )
    return text


def _parse_raw_filename(
    path: Path,
) -> tuple[datetime, str]:
    match = _RAW_NAME_RE.fullmatch(path.name)
    if match is None:
        raise SoakSegmentManagerError(
            f"unrecognized raw segment filename: {path.name}"
        )

    try:
        hour = datetime.strptime(
            match.group("hour"),
            "%Y%m%dT%H%M%SZ",
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise SoakSegmentManagerError(
            "raw segment hour token invalid"
        ) from exc

    if hour.minute != 0 or hour.second != 0:
        raise SoakSegmentManagerError(
            "raw segment filename is not UTC-hour aligned"
        )

    return hour, match.group("instance")


def _paths_for_raw(
    raw: Path,
) -> dict[str, Path]:
    return {
        "raw": raw,
        "compressed_temp": raw.with_name(
            raw.name + ".zst.tmp"
        ),
        "compressed": raw.with_name(
            raw.name + ".zst"
        ),
        "descriptor_temp": raw.with_name(
            raw.name + ".descriptor.json.tmp"
        ),
        "descriptor": raw.with_name(
            raw.name + ".descriptor.json"
        ),
    }


def _base_raw_from_artifact(
    path: Path,
) -> Path | None:
    name = path.name

    for suffix in (
        ".descriptor.json.tmp",
        ".descriptor.json",
        ".zst.tmp",
        ".zst",
    ):
        if name.endswith(".jsonl" + suffix):
            return path.with_name(
                name[:-len(suffix)]
            )

    if name.endswith(".jsonl"):
        return path

    return None


def inspect_raw_segment(
    raw_path: str | Path,
    *,
    expected_source: str,
    expected_hour_start: datetime,
) -> int:
    """Validate recoverable JSONL and return exact record count."""

    path = Path(raw_path)
    data = path.read_bytes()

    if data and not data.endswith(b"\n"):
        raise SoakSegmentManagerError(
            "raw segment has incomplete trailing record"
        )

    count = 0

    try:
        with path.open(
            "r",
            encoding="utf-8",
            newline="\n",
        ) as f:
            for line in f:
                if not line.strip():
                    raise SoakSegmentManagerError(
                        "raw segment contains blank record"
                    )

                value = json.loads(line)

                if not isinstance(value, dict):
                    raise SoakSegmentManagerError(
                        "raw record root must be object"
                    )

                if value.get("schema_version") != RAW_SCHEMA:
                    raise SoakSegmentManagerError(
                        "raw record schema mismatch"
                    )

                if value.get("source") != expected_source:
                    raise SoakSegmentManagerError(
                        "raw record source mismatch"
                    )

                received = value.get("received_utc")
                if not isinstance(received, str):
                    raise SoakSegmentManagerError(
                        "raw record received_utc missing"
                    )

                if (
                    utc_hour_start(received)
                    != expected_hour_start
                ):
                    raise SoakSegmentManagerError(
                        "raw record lies outside segment UTC hour"
                    )

                count += 1

    except (
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise SoakSegmentManagerError(
            "raw segment JSONL is invalid"
        ) from exc

    return count


def _validate_descriptor_identity(
    value: Mapping[str, Any],
    *,
    source: str,
    hour_start: datetime,
) -> None:
    start, end = hour_bounds_text(hour_start)

    if value.get("source") != source:
        raise SoakSegmentManagerError(
            "closed descriptor source mismatch"
        )

    if value.get("segment_start_utc") != start:
        raise SoakSegmentManagerError(
            "closed descriptor segment start mismatch"
        )

    if value.get("segment_end_utc") != end:
        raise SoakSegmentManagerError(
            "closed descriptor segment end mismatch"
        )


class SourceBoundJournalAdapter:
    """Expose RuntimeRawJournal-style append semantics for one bound source.

    Existing raw-first helpers such as Coinbase REST recovery can reuse this
    adapter without learning about hourly rotation.

    The caller must still supply `source`.  A mismatch is rejected rather than
    silently routing evidence into the wrong archive.
    """

    def __init__(
        self,
        manager: "HourlySourceSegmentManager",
    ) -> None:
        if not isinstance(
            manager,
            HourlySourceSegmentManager,
        ):
            raise SoakSegmentManagerError(
                "journal adapter requires HourlySourceSegmentManager"
            )

        self.manager = manager

    @property
    def source(self) -> str:
        return self.manager.source

    def append(
        self,
        *,
        source: str,
        transport: str,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        request_identity: Mapping[
            str, Any
        ] | None = None,
    ) -> None:
        if source != self.manager.source:
            raise SoakSegmentManagerError(
                "journal adapter source does not match bound source"
            )

        self.manager.append(
            transport=transport,
            raw_text=raw_text,
            received_monotonic_ns=(
                received_monotonic_ns
            ),
            received_utc=received_utc,
            request_identity=request_identity,
        )


class HourlySourceSegmentManager:
    """Own one source's raw journal across UTC-hour boundaries."""

    def __init__(
        self,
        root: str | Path,
        *,
        source: str,
        segment_instance_id: str,
        fsync_interval_ns: int = 1_000_000_000,
    ) -> None:
        if source not in ALLOWED_RUNTIME_SOURCES:
            raise SoakSegmentManagerError(
                f"unsupported runtime source: {source}"
            )

        self.root = Path(root)
        self.source = source
        self.segment_instance_id = (
            _validate_instance_id(
                segment_instance_id
            )
        )

        self.fsync_interval_ns = int(
            fsync_interval_ns
        )

        if self.fsync_interval_ns <= 0:
            raise SoakSegmentManagerError(
                "fsync_interval_ns must be positive"
            )

        self.source_dir = (
            self.root / self.source
        )
        self.source_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._active: _ActiveSegment | None = None
        self._last_monotonic_ns: int | None = None
        self._closed = False
        # Workers share the core's managers.  A UTC-hour rotation must not
        # expose a closing journal to another worker's idle-fsync pass.
        self._operation_lock = threading.RLock()
        self.closed_descriptor_paths: list[Path] = []
        # Cumulative attempt totals survive raw->zstd closure, unlike a disk
        # walk which loses the raw bytes once archival deletion is complete.
        self.total_raw_bytes_written = 0
        self.total_compressed_bytes_written = 0

    @property
    def active_raw_path(self) -> Path | None:
        if self._active is None:
            return None
        return self._active.raw_path

    def _raw_path_for_hour(
        self,
        hour_start: datetime,
    ) -> Path:
        name = (
            f"{hour_token(hour_start)}__"
            f"{self.segment_instance_id}.jsonl"
        )
        return self.source_dir / name

    def _open_hour(
        self,
        hour_start: datetime,
    ) -> None:
        raw = self._raw_path_for_hour(
            hour_start
        )
        paths = _paths_for_raw(raw)

        if any(path.exists() for path in paths.values()):
            raise SoakSegmentManagerError(
                f"segment artifact already exists: {raw.name}"
            )

        journal = RuntimeRawJournal(
            raw,
            fsync_interval_ns=(
                self.fsync_interval_ns
            ),
        )

        self._active = _ActiveSegment(
            hour_start=hour_start,
            raw_path=raw,
            journal=journal,
        )

    def _finalize_active(self) -> Path | None:
        active = self._active
        if active is None:
            return None

        # Explicit frozen closure ordering:
        # flush/fsync, then close before compression.
        active.journal.force_fsync()
        record_count = active.journal.record_count
        active.journal.close()

        start, end = hour_bounds_text(
            active.hour_start
        )

        try:
            close_raw_segment(
                raw_path=active.raw_path,
                source=self.source,
                segment_start_utc=start,
                segment_end_utc=end,
                record_count=record_count,
            )
        except SoakArchiveError as exc:
            raise SoakSegmentManagerError(
                "closed raw segment archival failed"
            ) from exc

        descriptor = active.raw_path.with_name(
            active.raw_path.name
            + ".descriptor.json"
        )

        self.closed_descriptor_paths.append(
            descriptor
        )
        compressed = active.raw_path.with_name(active.raw_path.name + ".zst")
        self.total_compressed_bytes_written += compressed.stat().st_size
        self._active = None
        return descriptor

    def append(
        self,
        *,
        transport: str,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        request_identity: Mapping[
            str, Any
        ] | None = None,
    ) -> None:
        """Append atomically with respect to rotation and idle fsync."""
        with self._operation_lock:
            self._append(
                transport=transport,
                raw_text=raw_text,
                received_monotonic_ns=received_monotonic_ns,
                received_utc=received_utc,
                request_identity=request_identity,
            )

    def _append(
        self,
        *,
        transport: str,
        raw_text: str,
        received_monotonic_ns: int,
        received_utc: str,
        request_identity: Mapping[
            str, Any
        ] | None = None,
    ) -> None:
        if self._closed:
            raise SoakSegmentManagerError(
                "segment manager already closed"
            )

        mono = int(received_monotonic_ns)
        if mono < 0:
            raise SoakSegmentManagerError(
                "received_monotonic_ns must be nonnegative"
            )

        if (
            self._last_monotonic_ns is not None
            and mono < self._last_monotonic_ns
        ):
            raise SoakSegmentManagerError(
                "cross-segment monotonic receive time regressed"
            )

        target_hour = utc_hour_start(
            received_utc
        )

        if self._active is None:
            self._open_hour(target_hour)

        elif target_hour < self._active.hour_start:
            raise SoakSegmentManagerError(
                "UTC segment hour regressed"
            )

        elif target_hour > self._active.hour_start:
            self._finalize_active()
            self._open_hour(target_hour)

        assert self._active is not None

        before = self._active.raw_path.stat().st_size if self._active.raw_path.exists() else 0
        self._active.journal.append(
            source=self.source,
            transport=transport,
            raw_text=raw_text,
            received_monotonic_ns=mono,
            received_utc=received_utc,
            request_identity=request_identity,
        )
        self.total_raw_bytes_written += self._active.raw_path.stat().st_size - before

        self._last_monotonic_ns = mono

    def close(self) -> None:
        with self._operation_lock:
            self._close()

    def _close(self) -> None:
        if self._closed:
            return

        self._finalize_active()
        self._closed = True

    def fsync_if_due(self, now_monotonic_ns: int) -> bool:
        with self._operation_lock:
            return self._fsync_if_due(now_monotonic_ns)

    def _fsync_if_due(self, now_monotonic_ns: int) -> bool:
        """Service the one-second idle durability deadline for this source."""
        if self._closed:
            raise SoakSegmentManagerError("segment manager already closed")
        if self._active is None:
            return False
        try:
            return self._active.journal.fsync_if_due(int(now_monotonic_ns))
        except Exception as exc:
            raise SoakSegmentManagerError("idle raw fsync failed") from exc

    def recover_existing_segments(
        self,
    ) -> RecoverySummary:
        with self._operation_lock:
            return self._recover_existing_segments()

    def _recover_existing_segments(
        self,
    ) -> RecoverySummary:
        """Recover prior process fragments before opening new raw state."""

        if self._active is not None:
            raise SoakSegmentManagerError(
                "cannot recover while an active segment is open"
            )

        if self._closed:
            raise SoakSegmentManagerError(
                "cannot recover after manager close"
            )

        candidates: set[Path] = set()

        for artifact in self.source_dir.glob(
            "*.jsonl*"
        ):
            base = _base_raw_from_artifact(
                artifact
            )
            if base is not None:
                candidates.add(base)

        verified = 0
        archived = 0
        discarded_temp_compressed = 0
        discarded_temp_descriptors = 0
        discarded_unverified_compressed = 0
        deleted_redundant_raw = 0

        for raw in sorted(candidates):
            hour, _ = _parse_raw_filename(raw)
            paths = _paths_for_raw(raw)

            descriptor = paths["descriptor"]
            compressed = paths["compressed"]
            compressed_temp = paths[
                "compressed_temp"
            ]
            descriptor_temp = paths[
                "descriptor_temp"
            ]

            if descriptor.exists():
                try:
                    value = validate_closed_segment(
                        descriptor
                    )
                except SoakArchiveError as exc:
                    raise SoakSegmentManagerError(
                        "closed descriptor/hash validation failed"
                    ) from exc

                _validate_descriptor_identity(
                    value,
                    source=self.source,
                    hour_start=hour,
                )

                if raw.exists():
                    if (
                        raw.stat().st_size
                        != value[
                            "uncompressed_size_bytes"
                        ]
                        or file_sha256(raw)
                        != value[
                            "uncompressed_sha256"
                        ]
                    ):
                        raise SoakSegmentManagerError(
                            "redundant raw copy does not match "
                            "verified descriptor"
                        )

                    raw.unlink()
                    _fsync_directory(
                        raw.parent
                    )
                    deleted_redundant_raw += 1

                if compressed_temp.exists():
                    compressed_temp.unlink()
                    _fsync_directory(
                        compressed_temp.parent
                    )
                    discarded_temp_compressed += 1

                if descriptor_temp.exists():
                    descriptor_temp.unlink()
                    _fsync_directory(
                        descriptor_temp.parent
                    )
                    discarded_temp_descriptors += 1

                verified += 1
                self.closed_descriptor_paths.append(descriptor)
                continue

            # No final descriptor exists. Nothing compressed is
            # authoritative. Recovery is permitted only from intact raw.
            if not raw.exists():
                if (
                    compressed.exists()
                    or compressed_temp.exists()
                    or descriptor_temp.exists()
                ):
                    raise SoakSegmentManagerError(
                        "uncompressed segment missing without "
                        "verified compressed descriptor"
                    )
                continue

            if descriptor_temp.exists():
                descriptor_temp.unlink()
                _fsync_directory(
                    descriptor_temp.parent
                )
                discarded_temp_descriptors += 1

            if compressed_temp.exists():
                compressed_temp.unlink()
                _fsync_directory(
                    compressed_temp.parent
                )
                discarded_temp_compressed += 1

            if compressed.exists():
                compressed.unlink()
                _fsync_directory(
                    compressed.parent
                )
                discarded_unverified_compressed += 1

            record_count = inspect_raw_segment(
                raw,
                expected_source=self.source,
                expected_hour_start=hour,
            )

            start, end = hour_bounds_text(
                hour
            )

            try:
                close_raw_segment(
                    raw_path=raw,
                    source=self.source,
                    segment_start_utc=start,
                    segment_end_utc=end,
                    record_count=record_count,
                )
            except SoakArchiveError as exc:
                raise SoakSegmentManagerError(
                    "recovered raw segment archival failed"
                ) from exc

            archived += 1
            self.closed_descriptor_paths.append(paths["descriptor"])

        return RecoverySummary(
            verified_closed_segments=verified,
            archived_raw_segments=archived,
            discarded_temporary_compressed=(
                discarded_temp_compressed
            ),
            discarded_temporary_descriptors=(
                discarded_temp_descriptors
            ),
            discarded_unverified_compressed=(
                discarded_unverified_compressed
            ),
            deleted_redundant_raw=(
                deleted_redundant_raw
            ),
        )
