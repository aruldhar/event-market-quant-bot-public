import os
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)
from src.kxbtcd_candidate_e_soak_linux_runtime_identity import (
    SoakLinuxRuntimeIdentityError,
    read_linux_time_namespace_id,
    resolve_production_runtime_identity,
)


BOOT = (
    "11111111-2222-3333-4444-555555555555"
)

TIME_NS = "time:[4026531834]"


def test_time_namespace_uses_exact_readlink_representation():
    seen = []

    def fake_readlink(path):
        seen.append(
            str(path)
        )
        return TIME_NS

    value = read_linux_time_namespace_id(
        "/proc/self/ns/time",
        readlink=fake_readlink,
    )

    assert value == TIME_NS

    assert seen == [
        str(
            Path(
                "/proc/self/ns/time"
            )
        )
    ]


def test_time_namespace_only_strips_outer_whitespace():
    value = read_linux_time_namespace_id(
        "/fake/time",
        readlink=lambda _: (
            "  time:[4026531834]\n"
        ),
    )

    assert value == (
        "time:[4026531834]"
    )


def test_blank_time_namespace_is_rejected():
    with pytest.raises(
        SoakLinuxRuntimeIdentityError,
        match="blank",
    ):
        read_linux_time_namespace_id(
            "/fake/time",
            readlink=lambda _: "   ",
        )


def test_unreadable_time_namespace_is_rejected():
    def fail(_):
        raise OSError(
            "synthetic readlink failure"
        )

    with pytest.raises(
        SoakLinuxRuntimeIdentityError,
        match="unavailable",
    ):
        read_linux_time_namespace_id(
            "/fake/time",
            readlink=fail,
        )


def test_production_linux_identity_passes_with_real_shape(
    tmp_path,
):
    boot_path = (
        tmp_path / "boot_id"
    )

    boot_path.write_text(
        BOOT + "\n",
        encoding="utf-8",
    )

    result = (
        resolve_production_runtime_identity(
            platform_system="Linux",
            production_boot_id_path=(
                boot_path
            ),
            time_namespace_path=(
                "/fake/time"
            ),
            readlink=lambda _: TIME_NS,
        )
    )

    assert result.status == (
        GateStatus.PASS
    )

    assert result.reason == "PASS"
    assert result.boot_id == BOOT
    assert (
        result.time_namespace_id
        == TIME_NS
    )

    assert result.boot_source == (
        "linux_kernel_boot_id"
    )


def test_non_linux_production_runtime_blocks(
    tmp_path,
):
    result = (
        resolve_production_runtime_identity(
            platform_system="Windows",
            production_boot_id_path=(
                tmp_path / "unused"
            ),
            time_namespace_path=(
                "/fake/time"
            ),
            readlink=lambda _: TIME_NS,
        )
    )

    assert result.status == (
        GateStatus.BLOCKED
    )

    assert result.reason == (
        "PRODUCTION_REQUIRES_LINUX_BOOT_ID"
    )

    assert result.time_namespace_id is None


def test_invalid_boot_identity_blocks_before_namespace_read(
    tmp_path,
):
    boot_path = (
        tmp_path / "boot_id"
    )

    boot_path.write_text(
        "not-a-uuid\n",
        encoding="utf-8",
    )

    called = {
        "namespace": False,
    }

    def readlink(_):
        called["namespace"] = True
        return TIME_NS

    result = (
        resolve_production_runtime_identity(
            platform_system="Linux",
            production_boot_id_path=(
                boot_path
            ),
            time_namespace_path=(
                "/fake/time"
            ),
            readlink=readlink,
        )
    )

    assert result.status == (
        GateStatus.BLOCKED
    )

    assert result.reason == (
        "BOOT_ID_UNAVAILABLE_OR_INVALID"
    )

    assert not called["namespace"]


def test_missing_time_namespace_blocks_after_valid_boot(
    tmp_path,
):
    boot_path = (
        tmp_path / "boot_id"
    )

    boot_path.write_text(
        BOOT + "\n",
        encoding="utf-8",
    )

    def fail(_):
        raise OSError(
            "synthetic namespace failure"
        )

    result = (
        resolve_production_runtime_identity(
            platform_system="Linux",
            production_boot_id_path=(
                boot_path
            ),
            time_namespace_path=(
                "/fake/time"
            ),
            readlink=fail,
        )
    )

    assert result.status == (
        GateStatus.BLOCKED
    )

    assert result.reason == (
        "TIME_NAMESPACE_UNAVAILABLE_OR_INVALID"
    )

    assert result.boot_id == BOOT
    assert result.time_namespace_id is None
