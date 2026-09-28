import pytest

from src.kxbtcd_candidate_e_soak_live_runner_factory import run_gated_read_only_soak
from src.kxbtcd_candidate_e_soak_runtime_command import SoakRuntimeCommandError


def test_composed_runner_preserves_zero_network_default():
    calls = []
    assert run_gated_read_only_soak(argv=[], run_preflight=lambda: calls.append("preflight"),
                                    run_assembled_live=lambda: calls.append("live")) is None
    assert calls == ["preflight"]


def test_composed_runner_requires_live_acknowledgement():
    with pytest.raises(SoakRuntimeCommandError):
        run_gated_read_only_soak(argv=["--mode", "read-only-live"], run_preflight=lambda: None,
                                  run_assembled_live=lambda: (_ for _ in ()).throw(AssertionError()))


def test_composed_runner_invokes_assembled_path_after_acknowledgement():
    calls = []
    run_gated_read_only_soak(argv=["--mode", "read-only-live", "--enable-read-only-live"],
                              run_preflight=lambda: calls.append("preflight"),
                              run_assembled_live=lambda: calls.append("live"))
    assert calls == ["live"]
