from pathlib import Path

from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus
from src import kxbtcd_candidate_e_soak_package as package


def test_compose_uses_read_only_host_clock_file_and_never_mounts_chronyd_socket():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    assert "kxbtcd-clock" in text
    assert "source: /var/lib/kxbtcd-clock" in text
    assert "target: /run/kxbtcd-host" in text
    assert "read_only: true" in text
    assert "chronyd.sock" not in text
    assert "restart: \"no\"" in text
    assert "candidate_e_read_only_runtime" in text
    assert "privileged: false" in text
    assert "cap_drop:" in text
    assert "no-new-privileges:true" in text
    assert "soak_volume_init" in text
    assert "service_completed_successfully" in text
    assert "/run/secrets/kalshi_private_key.pem" in text
    assert "env_file:" in text


def test_live_shadow_dashboard_is_networkless_and_has_no_secrets():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    shadow = text.split("  candidate_e_live_shadow_dashboard:", 1)[1].split(
        "  candidate_e_live_shadow_settlement_closeout:", 1
    )[0]
    assert "image: deploy-candidate_e_read_only_runtime" in shadow
    assert 'user: "10001:10001"' in shadow
    assert "network_mode: none" in shadow
    assert "source: shadow_dashboard" in shadow
    assert "target: /var/lib/kxbtcd-shadow-dashboard" in shadow
    assert "source: shadow_dashboard_read_model" in shadow
    assert "target: /var/lib/kxbtcd-dashboard-read-model" in shadow
    assert "read_only: true" in shadow
    assert "privileged: false" in shadow
    assert "cap_drop:" in shadow
    assert "- ALL" in shadow
    assert "no-new-privileges:true" in shadow
    assert "cap_add:" not in shadow
    assert "/run/secrets" not in shadow
    assert "env_file:" not in shadow
    assert "source: soak_raw" in shadow


def test_shadow_settlement_closeout_has_public_network_but_no_venue_credentials():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    closeout = text.split("  candidate_e_live_shadow_settlement_closeout:", 1)[1].split(
        "  candidate_e_grafana:", 1
    )[0]
    assert "image: deploy-candidate_e_read_only_runtime" in closeout
    assert 'user: "10001:10001"' in closeout
    assert "read_only: true" in closeout
    assert "privileged: false" in closeout
    assert "cap_drop:" in closeout
    assert "- ALL" in closeout
    assert "no-new-privileges:true" in closeout
    assert "/run/secrets" not in closeout
    assert "env_file:" not in closeout
    assert "KALSHI_" not in closeout
    assert "source: soak_raw" in closeout
    assert "source: shadow_dashboard" in closeout
    ledger_mount = closeout.split("source: shadow_dashboard", 1)[1].split("entrypoint:", 1)[0]
    # The closeout code opens SQLite in mode=ro, but its WAL reader needs a
    # writable volume mount for SQLite lock/shared-memory coordination.
    assert "read_only: true" not in ledger_mount


def test_offsite_archive_is_separate_read_only_and_has_no_venue_credentials():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    archive = text.split("  candidate_e_offsite_archive:", 1)[1].split(
        "  candidate_e_grafana:", 1
    )[0]
    assert "image: deploy-candidate_e_read_only_runtime" in archive
    assert 'user: "10001:10001"' in archive
    assert "read_only: true" in archive
    assert "privileged: false" in archive
    assert "cap_drop:" in archive
    assert "- ALL" in archive
    assert "no-new-privileges:true" in archive
    assert "network_mode: none" not in archive
    assert "env_file:" not in archive
    assert "/run/secrets" not in archive
    assert "KALSHI_" not in archive
    assert "source: soak_raw" in archive
    assert "source: shadow_dashboard" in archive
    assert "source: offsite_archive_receipts" in archive


def test_verified_local_prune_is_explicitly_isolated_from_venue_credentials():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    prune = text.split("  candidate_e_verified_local_prune:", 1)[1].split(
        "  candidate_e_grafana:", 1
    )[0]
    assert "image: deploy-candidate_e_read_only_runtime" in prune
    assert 'user: "10001:10001"' in prune
    assert "read_only: true" in prune
    assert "privileged: false" in prune
    assert "cap_drop:" in prune
    assert "- ALL" in prune
    assert "no-new-privileges:true" in prune
    assert "network_mode: none" not in prune
    assert "env_file:" not in prune
    assert "/run/secrets" not in prune
    assert "KALSHI_" not in prune
    assert "source: soak_raw" in prune
    assert "source: offsite_archive_receipts" in prune
    assert "source: shadow_dashboard" not in prune


def test_shadow_dashboard_volume_init_is_minimally_privileged():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    init = text.split("  shadow_dashboard_volume_init:", 1)[1].split(
        "  shadow_dashboard_read_model_volume_init:", 1
    )[0]

    assert "image: busybox:1.36" in init
    assert 'user: "0:0"' in init
    assert "read_only: true" in init
    assert 'restart: "no"' in init
    assert "privileged: false" in init
    assert "network_mode: none" in init
    assert "cap_drop:" in init
    assert "- ALL" in init
    assert "cap_add:" in init
    assert "- CHOWN" in init
    assert "chown -R" not in init
    assert "if [ ! -d" in init
    assert "10001:10001:750" in init
    assert "no-new-privileges:true" in init
    assert "source: shadow_dashboard" in init
    assert "target: /var/lib/kxbtcd-shadow-dashboard" in init
    assert "source: soak_raw" not in init
    assert "/run/secrets" not in init
    assert "env_file:" not in init


def test_shadow_dashboard_read_model_volume_init_is_minimally_privileged():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    init = text.split("  shadow_dashboard_read_model_volume_init:", 1)[1].split(
        "  candidate_e_live_shadow_dashboard:", 1
    )[0]
    assert "image: busybox:1.36" in init
    assert 'user: "0:0"' in init
    assert "read_only: true" in init
    assert 'restart: "no"' in init
    assert "privileged: false" in init
    assert "network_mode: none" in init
    assert "cap_drop:" in init
    assert "- ALL" in init
    assert "cap_add:" in init
    assert "- CHOWN" in init
    assert "chown -R" not in init
    assert "if [ ! -d" in init
    assert "10001:10001:755" in init
    assert "no-new-privileges:true" in init
    assert "source: shadow_dashboard_read_model" in init
    assert "target: /var/lib/kxbtcd-dashboard-read-model" in init
    assert "source: shadow_dashboard\n" not in init
    assert "source: soak_raw" not in init
    assert "/run/secrets" not in init
    assert "env_file:" not in init


def test_grafana_is_localhost_only_read_only_and_has_no_venue_credentials():
    text = Path("deploy/kxbtcd-candidate-e-soak.compose.yaml").read_text(encoding="utf-8")
    grafana = text.split("  candidate_e_grafana:", 1)[1].split("\nvolumes:", 1)[0]
    assert "dockerfile: deploy/kxbtcd-candidate-e-grafana.Dockerfile" in grafana
    assert "image: deploy-candidate_e_grafana:13.2.1" in grafana
    assert 'user: "472:0"' in grafana
    assert "read_only: true" in grafana
    assert "privileged: false" in grafana
    assert "cap_drop:" in grafana
    assert "- ALL" in grafana
    assert "no-new-privileges:true" in grafana
    assert '"127.0.0.1:3000:3000"' in grafana
    assert "dashboard_internal" in grafana
    assert "source: shadow_dashboard_read_model" in grafana
    assert "target: /var/lib/kxbtcd-dashboard-data" in grafana
    assert "read_only: true" in grafana
    assert "/run/secrets/grafana_admin_password" in grafana
    assert "kalshi_private_key" not in grafana
    assert "KALSHI_" not in grafana
    assert "env_file:" not in grafana
    assert "source: soak_raw" not in grafana
    assert "source: shadow_dashboard\n" not in grafana
    assert "cap_add:" not in grafana


def test_grafana_image_and_provisioning_are_version_pinned_and_query_only_by_default():
    dockerfile = Path("deploy/kxbtcd-candidate-e-grafana.Dockerfile").read_text(encoding="utf-8")
    datasource = Path(
        "deploy/grafana/provisioning/datasources/candidate-e-shadow.yaml"
    ).read_text(encoding="utf-8")
    provider = Path(
        "deploy/grafana/provisioning/dashboards/candidate-e-shadow.yaml"
    ).read_text(encoding="utf-8")
    assert "FROM grafana/grafana:13.2.1" in dockerfile
    assert "grafana/grafana-oss" not in dockerfile
    assert "SQLITE_PLUGIN_VERSION=4.0.6" in dockerfile
    assert "frser-sqlite-datasource" in dockerfile
    assert "type: frser-sqlite-datasource" in datasource
    assert "editable: false" in datasource
    assert "/var/lib/kxbtcd-dashboard-data/shadow_dashboard_read_model.sqlite3" in datasource
    assert "allowUiUpdates: false" in provider
    assert "/var/lib/grafana/provisioned-dashboards" in provider


def test_image_drops_root_before_running_package():
    text = Path("deploy/kxbtcd-candidate-e-soak.Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in text
    assert "COPY --chown=10001:10001" in text
    assert "requirements.txt" in text


def test_package_cannot_be_a_hidden_source_launcher():
    text = Path("src/kxbtcd_candidate_e_soak_package.py").read_text(encoding="utf-8")
    assert "run_observed_soak" not in text
    assert "connect(" not in text
    assert "producer.sample" in text
    assert 'required_generation_sources=("kalshi",)' in text
    assert 'readiness_input_contract="v2_exact_rest_candle_and_kalshi"' in text


def test_package_preflight_samples_clock_bridge_before_constructing_runtime(tmp_path, monkeypatch):
    clock = tmp_path / "clock-evidence.json"
    clock.write_text("{}", encoding="utf-8")
    identity = type("Identity", (), {
        "status": GateStatus.PASS,
        "boot_id": "host-boot",
        "time_namespace_id": "time:[1]",
    })()

    class Producer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.sampled_at = None
            self.storage_totals = None

        def sample(self, now_ns):
            self.sampled_at = now_ns
            return {"clock_status": "PASS"}

    monkeypatch.setattr(package, "resolve_production_runtime_identity", lambda: identity)
    monkeypatch.setattr(package, "RuntimeMetricProducers", Producer)
    monkeypatch.setattr(package.time, "monotonic_ns", lambda: 123)

    core, producer, _ = package.build_observed_components(
        runtime_session_id="preflight", archive_root=tmp_path / "raw",
        telemetry_root=tmp_path / "telemetry", clock_evidence_path=clock,
        utc_now_text=lambda: "2026-09-06T00:00:00Z")
    try:
        assert producer.sampled_at == 123
        assert producer.kwargs["clock_evidence_path"] == clock
    finally:
        core.close()


def test_package_preflight_rejects_non_passing_clock_evidence(tmp_path, monkeypatch):
    clock = tmp_path / "clock-evidence.json"
    clock.write_text("{}", encoding="utf-8")
    identity = type("Identity", (), {
        "status": GateStatus.PASS,
        "boot_id": "host-boot",
        "time_namespace_id": "time:[1]",
    })()

    class BlockedProducer:
        def __init__(self, **kwargs):
            pass

        def sample(self, now_ns):
            return {"clock_status": "BLOCKED"}

    monkeypatch.setattr(package, "resolve_production_runtime_identity", lambda: identity)
    monkeypatch.setattr(package, "RuntimeMetricProducers", BlockedProducer)

    try:
        package.build_observed_components(
            runtime_session_id="preflight", archive_root=tmp_path / "raw",
            telemetry_root=tmp_path / "telemetry", clock_evidence_path=clock,
            utc_now_text=lambda: "2026-09-06T00:00:00Z")
    except package.SoakPackageError as exc:
        assert str(exc) == "host clock evidence is not PASS"
    else:
        raise AssertionError("non-passing clock evidence was accepted")
