from src import kxbtcd_candidate_e_soak_runtime_assembly as assembly


def test_assembly_requires_observed_orchestrator_and_verified_closure(monkeypatch, tmp_path):
    captured = {}
    core = object()
    producers = object()
    observer = object()
    monkeypatch.setattr(assembly, "close_verified_runtime_archives", lambda value: [("raw", tmp_path / "raw")])
    monkeypatch.setattr(assembly, "run_packaged_observed_soak", lambda **kwargs: captured.update(kwargs) or "done")
    result = assembly.run_assembled_read_only_soak(
        core=core, producers=producers, observability=observer,
        run_coinbase_supervisor=lambda stop: None, run_kalshi_supervisor=lambda stop: None,
        sample_readiness=lambda now: None, manifest_path=tmp_path / "raw" / "manifests" / "run.json",
        run_id="run", git_head="a" * 40, docker_image_digest="sha256:" + "b" * 64,
        host_boot_id="boot", requested_active_duration_seconds=3600,
        initial_filesystem_free_bytes=1, utc_now_text=lambda: "2026-09-06T00:00:00Z")
    assert result == "done"
    assert captured["core"] is core
    assert captured["expected_boot_id"] == "boot"
    assert captured["artifact_root"] == tmp_path
    assert captured["close_runtime_artifacts"]() == [("raw", tmp_path / "raw")]
