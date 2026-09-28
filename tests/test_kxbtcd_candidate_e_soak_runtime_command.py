import pytest

from src.kxbtcd_candidate_e_soak_runtime_command import (
    SoakRuntimeCommandError,
    dispatch_runtime_command,
)


def test_default_command_runs_only_preflight():
    calls = []
    result = dispatch_runtime_command(
        run_preflight=lambda: calls.append("preflight") or "ok",
        run_read_only_live=lambda: calls.append("live"),
    )
    assert result == "ok"
    assert calls == ["preflight"]


def test_live_mode_requires_explicit_acknowledgement():
    with pytest.raises(SoakRuntimeCommandError, match="requires --enable-read-only-live"):
        dispatch_runtime_command(
            argv=["--mode", "read-only-live"], run_preflight=lambda: None,
            run_read_only_live=lambda: (_ for _ in ()).throw(AssertionError("must not run")),
        )


def test_live_mode_runs_only_after_explicit_acknowledgement():
    calls = []
    dispatch_runtime_command(
        argv=["--mode", "read-only-live", "--enable-read-only-live"],
        run_preflight=lambda: calls.append("preflight"),
        run_read_only_live=lambda: calls.append("live"),
    )
    assert calls == ["live"]
