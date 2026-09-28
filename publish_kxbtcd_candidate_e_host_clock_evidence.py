#!/usr/bin/env python3
"""Publish real host chronyd evidence for the Candidate-E read-only runtime.

Production use is Linux-host only.

The publisher:
- has no market credentials;
- has no market-data client;
- has no trading/execution path;
- invokes only local `chronyc -n tracking`;
- records real Linux boot/time-namespace identity;
- atomically replaces one evidence file.

The Docker runtime consumes that file read-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Callable
from uuid import uuid4

CHRONYC_COMMAND = ("chronyc", "-n", "tracking")
CHRONYC_TIMEOUT_SECONDS = 2.0
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")
DEFAULT_TIME_NAMESPACE_PATH = Path("/proc/self/ns/time")
# Kept local so this host-only publisher remains stdlib-only.  Importing the
# container bridge would pull the research runtime and its unrelated optional
# data dependencies into the systemd service.
CLOCK_EVIDENCE_SCHEMA = "candidate_e_host_clock_evidence.v1"
REAL_EVIDENCE_SOURCE = "real_host_chronyd"


class HostClockEvidencePublisherError(RuntimeError):
    pass


def utc_now_text() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def read_host_boot_id(
    path: str | Path = DEFAULT_BOOT_ID_PATH,
) -> str:
    value = Path(path).read_text(encoding="utf-8").strip()
    if not value:
        raise HostClockEvidencePublisherError(
            "Linux boot ID is blank"
        )
    return value


def read_host_time_namespace_id(
    path: str | Path = DEFAULT_TIME_NAMESPACE_PATH,
) -> str:
    value = os.readlink(Path(path))
    value = str(value).strip()
    if not value:
        raise HostClockEvidencePublisherError(
            "Linux time namespace ID is blank"
        )
    return value


def _fsync_directory(path: Path) -> None:
    """Durably persist rename metadata on production POSIX hosts.

    Windows is only an offline development/test environment for this
    publisher; directory fsync is a Linux production requirement.
    """
    if os.name != "posix":
        return

    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json_atomic(
    path: str | Path,
    value: dict,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    temp = target.with_name(target.name + ".tmp")

    payload = (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )

    with temp.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp, target)
    _fsync_directory(target.parent)


def run_chronyc_tracking() -> tuple[int, str]:
    try:
        result = subprocess.run(
            list(CHRONYC_COMMAND),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=CHRONYC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return -1, ""
    except OSError:
        return -2, ""

    return int(result.returncode), str(result.stdout)


def build_evidence_record(
    *,
    publisher_instance_id: str,
    chronyc_returncode: int,
    chronyc_tracking_raw: str,
    captured_utc: str,
    captured_monotonic_ns: int,
    host_boot_id: str,
    host_time_namespace_id: str,
) -> dict:
    return {
        "schema_version": CLOCK_EVIDENCE_SCHEMA,
        "evidence_source": REAL_EVIDENCE_SOURCE,
        "publisher_instance_id": str(
            publisher_instance_id
        ),
        "captured_utc": str(captured_utc),
        "captured_monotonic_ns": int(
            captured_monotonic_ns
        ),
        "host_boot_id": str(host_boot_id),
        "host_time_namespace_id": str(
            host_time_namespace_id
        ),
        "chronyc_returncode": int(
            chronyc_returncode
        ),
        "chronyc_tracking_raw": str(
            chronyc_tracking_raw
        ),
        "publisher_status": (
            "PASS"
            if (
                chronyc_returncode == 0
                and str(chronyc_tracking_raw).strip()
            )
            else "FAIL"
        ),
    }


def publish_once(
    *,
    output_path: str | Path,
    publisher_instance_id: str,
    chronyc_runner: Callable[
        [], tuple[int, str]
    ] = run_chronyc_tracking,
    boot_id_reader: Callable[[], str] = read_host_boot_id,
    time_namespace_reader: Callable[
        [], str
    ] = read_host_time_namespace_id,
    utc_reader: Callable[[], str] = utc_now_text,
    monotonic_ns_reader: Callable[
        [], int
    ] = time.monotonic_ns,
) -> dict:
    """Collect and atomically publish one real host evidence record."""

    # Always attempt to replace prior PASS evidence with explicit FAIL
    # evidence when chronyc itself fails.
    rc, raw = chronyc_runner()

    boot_id = boot_id_reader()
    time_namespace_id = time_namespace_reader()

    record = build_evidence_record(
        publisher_instance_id=publisher_instance_id,
        chronyc_returncode=rc,
        chronyc_tracking_raw=raw,
        captured_utc=utc_reader(),
        captured_monotonic_ns=monotonic_ns_reader(),
        host_boot_id=boot_id,
        host_time_namespace_id=time_namespace_id,
    )

    write_json_atomic(output_path, record)
    return record


def run_forever(
    *,
    output_path: str | Path,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    if interval_seconds <= 0:
        raise HostClockEvidencePublisherError(
            "interval_seconds must be positive"
        )

    publisher_instance_id = (
        "clock-publisher-" + uuid4().hex
    )

    while True:
        cycle_start = time.monotonic()

        try:
            publish_once(
                output_path=output_path,
                publisher_instance_id=publisher_instance_id,
            )
        except Exception as exc:
            # Publication failure must never be hidden.
            # systemd receives the failure and the container will
            # fail closed when existing evidence becomes stale.
            raise HostClockEvidencePublisherError(
                "clock evidence publication failed"
            ) from exc

        elapsed = time.monotonic() - cycle_start
        sleep_seconds = max(
            0.0,
            interval_seconds - elapsed,
        )
        time.sleep(sleep_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        required=True,
        help="Atomic clock-evidence JSON path",
    )

    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Publish exactly one record and exit",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    publisher_instance_id = (
        "clock-publisher-" + uuid4().hex
    )

    if args.once:
        publish_once(
            output_path=args.output,
            publisher_instance_id=publisher_instance_id,
        )
        return 0

    run_forever(
        output_path=args.output,
        interval_seconds=args.interval_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
