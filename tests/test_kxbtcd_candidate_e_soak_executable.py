import pytest

from src import kxbtcd_candidate_e_soak_executable as executable
from src.kxbtcd_candidate_e_soak_executable import dispatch_soak_invocation, parse_soak_invocation


def test_executable_requires_immutable_identity_and_explicit_duration():
    args = parse_soak_invocation([
        "--run-id", "shakedown", "--git-head", "a" * 40,
        "--docker-image-digest", "sha256:" + "b" * 64,
        "--active-seconds", "3600", "--archive-root", "raw",
        "--telemetry-root", "telemetry", "--clock-evidence-path", "clock",
    ])
    assert args.active_seconds == 3600
    assert not args.enable_read_only_live


def test_executable_rejects_unfrozen_duration():
    with pytest.raises(SystemExit):
        parse_soak_invocation(["--run-id", "x", "--git-head", "x", "--docker-image-digest", "x",
                               "--active-seconds", "1", "--archive-root", "x", "--telemetry-root", "x",
                               "--clock-evidence-path", "x"])


def test_executable_requires_storage_receipt_for_canonical_24h():
    with pytest.raises(SystemExit):
        parse_soak_invocation(["--run-id", "x", "--git-head", "a" * 40,
            "--docker-image-digest", "sha256:" + "b" * 64, "--active-seconds", "86400",
            "--archive-root", "x", "--telemetry-root", "x", "--clock-evidence-path", "x"])


def test_executable_dispatches_validated_arguments_only_after_live_flag():
    base = ["--run-id", "shakedown", "--git-head", "a" * 40,
            "--docker-image-digest", "sha256:" + "b" * 64, "--active-seconds", "3600",
            "--archive-root", "raw", "--telemetry-root", "telemetry", "--clock-evidence-path", "clock"]
    calls = []
    dispatch_soak_invocation(argv=base, run_preflight=lambda args: calls.append(("preflight", args.run_id)),
                             run_live=lambda args: calls.append(("live", args.run_id)))
    dispatch_soak_invocation(argv=base + ["--enable-read-only-live"],
                             run_preflight=lambda args: calls.append(("preflight", args.run_id)),
                             run_live=lambda args: calls.append(("live", args.run_id)))
    assert calls == [("preflight", "shakedown"), ("live", "shakedown")]


def test_validated_live_assembly_uses_package_and_observed_lifecycle(monkeypatch, tmp_path):
    args = parse_soak_invocation(["--run-id", "run", "--git-head", "a" * 40,
        "--docker-image-digest", "sha256:" + "b" * 64, "--active-seconds", "3600",
        "--archive-root", str(tmp_path), "--telemetry-root", str(tmp_path / "telemetry"),
        "--clock-evidence-path", "clock"])
    producer = type("Producer", (), {"sample": lambda self, now: {"linux_boot_id": "boot"}})()
    monkeypatch.setattr(executable, "build_observed_components", lambda **kw: ("core", producer, "observer"))
    monkeypatch.setattr(executable.shutil, "disk_usage", lambda path: type("Disk", (), {"free": 9})())
    captured = {}
    monkeypatch.setattr(executable, "run_assembled_read_only_soak", lambda **kw: captured.update(kw) or "done")
    assert executable.run_validated_live_assembly(args=args, utc_now_text=lambda: "utc",
        run_coinbase_supervisor="cb", run_kalshi_supervisor="ka", sample_readiness="ready") == "done"
    assert captured["host_boot_id"] == "boot"
    assert captured["requested_active_duration_seconds"] == 3600


def test_main_without_live_flag_runs_only_preflight(monkeypatch, tmp_path):
    closed = []
    core = type("Core", (), {"close": lambda self: closed.append(True)})()
    monkeypatch.setattr(executable, "build_observed_components", lambda **kwargs: (core, None, None))
    args = ["--run-id", "run", "--git-head", "a" * 40,
        "--docker-image-digest", "sha256:" + "b" * 64, "--active-seconds", "3600",
        "--archive-root", str(tmp_path), "--telemetry-root", str(tmp_path / "telemetry"),
        "--clock-evidence-path", "clock"]
    assert executable.main(args) == 0
    assert closed == [True]


def test_composed_live_assembly_recovers_prior_raw_evidence_before_sources(monkeypatch, tmp_path):
    args = parse_soak_invocation([
        "--run-id", "run", "--git-head", "a" * 40,
        "--docker-image-digest", "sha256:" + "b" * 64,
        "--active-seconds", "3600", "--archive-root", str(tmp_path),
        "--telemetry-root", str(tmp_path / "telemetry"),
        "--clock-evidence-path", "clock", "--enable-read-only-live",
    ])
    calls = []
    core = type("Core", (), {"recover_archives": lambda self: calls.append("recover")})()
    producer = type("Producer", (), {"sample": lambda self, now: {"linux_boot_id": "boot"}})()
    monkeypatch.setattr(executable, "build_observed_components", lambda **kw: (core, producer, "observer"))
    monkeypatch.setattr(executable, "run_validated_live_assembly", lambda **kw: "done")

    def supervisors(**kwargs):
        assert calls == ["recover"]
        return "coinbase", "kalshi"

    assert executable.run_composed_live_assembly(
        args=args, utc_now_text=lambda: "utc", http_session=object(), repo_root=".",
        supervisor_factory=supervisors, readiness_factory=lambda **kw: "readiness") == "done"
