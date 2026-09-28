"""Checkpoint 21N-Z-F production Linux runtime identity adapter.

The host clock publisher records two Linux identities:

1. kernel boot ID:
       /proc/sys/kernel/random/boot_id

2. time namespace:
       exact os.readlink("/proc/self/ns/time") text

The runtime container must independently resolve those same identities and
compare them against the host-published clock evidence.

Production behavior is fail-closed:
- Linux is required;
- synthetic boot identity is never accepted;
- missing/invalid boot ID blocks;
- unreadable/blank time namespace blocks.

No network, market credentials, signal, P&L, or execution behavior exists.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
from typing import Callable

from .kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from .kxbtcd_candidate_e_restart_source_readiness import (
    PRODUCTION_BOOT_ID_PATH,
    resolve_boot_identity,
)


DEFAULT_TIME_NAMESPACE_PATH = Path(
    "/proc/self/ns/time"
)


class SoakLinuxRuntimeIdentityError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class RuntimeLinuxIdentityEvidence:
    status: GateStatus
    reason: str
    boot_id: str | None
    time_namespace_id: str | None
    boot_source: str | None


def read_linux_time_namespace_id(
    path: str | Path = DEFAULT_TIME_NAMESPACE_PATH,
    *,
    readlink: Callable[[str | Path], str] = os.readlink,
) -> str:
    """Return the canonical Linux time-namespace identity.

    This intentionally mirrors the host publisher exactly:
    os.readlink(path), converted to str, then stripped.
    """

    try:
        value = readlink(
            Path(path)
        )
    except OSError as exc:
        raise SoakLinuxRuntimeIdentityError(
            "Linux time namespace is unavailable"
        ) from exc

    text = str(
        value
    ).strip()

    if not text:
        raise SoakLinuxRuntimeIdentityError(
            "Linux time namespace ID is blank"
        )

    return text


def resolve_production_runtime_identity(
    *,
    platform_system: str | None = None,
    production_boot_id_path: str | Path = (
        PRODUCTION_BOOT_ID_PATH
    ),
    time_namespace_path: str | Path = (
        DEFAULT_TIME_NAMESPACE_PATH
    ),
    readlink: Callable[
        [str | Path],
        str,
    ] = os.readlink,
) -> RuntimeLinuxIdentityEvidence:
    """Resolve real production Linux boot + time-namespace identity."""

    system_name = (
        str(platform_system)
        if platform_system is not None
        else platform.system()
    )

    boot = resolve_boot_identity(
        validation_mode=False,
        platform_system=system_name,
        production_boot_id_path=(
            production_boot_id_path
        ),
    )

    if boot.status == GateStatus.FATAL:
        return RuntimeLinuxIdentityEvidence(
            status=GateStatus.FATAL,
            reason=boot.reason,
            boot_id=None,
            time_namespace_id=None,
            boot_source=boot.source,
        )

    if boot.status != GateStatus.PASS:
        return RuntimeLinuxIdentityEvidence(
            status=GateStatus.BLOCKED,
            reason=boot.reason,
            boot_id=boot.boot_id,
            time_namespace_id=None,
            boot_source=boot.source,
        )

    try:
        time_namespace_id = (
            read_linux_time_namespace_id(
                time_namespace_path,
                readlink=readlink,
            )
        )
    except SoakLinuxRuntimeIdentityError:
        return RuntimeLinuxIdentityEvidence(
            status=GateStatus.BLOCKED,
            reason=(
                "TIME_NAMESPACE_UNAVAILABLE_OR_INVALID"
            ),
            boot_id=boot.boot_id,
            time_namespace_id=None,
            boot_source=boot.source,
        )

    return RuntimeLinuxIdentityEvidence(
        status=GateStatus.PASS,
        reason="PASS",
        boot_id=boot.boot_id,
        time_namespace_id=(
            time_namespace_id
        ),
        boot_source=boot.source,
    )
