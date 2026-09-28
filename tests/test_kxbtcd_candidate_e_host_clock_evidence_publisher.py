import json

import publish_kxbtcd_candidate_e_host_clock_evidence as publisher

from src.kxbtcd_candidate_e_clock_evidence_bridge import (
    evaluate_clock_evidence_file,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import (
    GateStatus,
)


BOOT = "0d6faadc-2fae-40bd-aa78-5d86807f8702"
TIME_NS = "time:[4026531834]"
CAPTURE_NS = 10_000_000_000


def tracking():
    return (
        "Reference ID    : A9FEA97B (169.254.169.123)\n"
        "Stratum         : 2\n"
        "Ref time (UTC)  : Fri Sep 04 14:28:31 2026\n"
        "System time     : 0.000002883 seconds slow of NTP time\n"
        "Last offset     : -0.000000614 seconds\n"
        "RMS offset      : 0.000004227 seconds\n"
        "Frequency       : 1.040 ppm slow\n"
        "Residual freq   : -0.001 ppm\n"
        "Skew            : 0.045 ppm\n"
        "Root delay      : 0.000144519 seconds\n"
        "Root dispersion : 0.000035586 seconds\n"
        "Update interval : 16.2 seconds\n"
        "Leap status     : Normal\n"
    )


def test_build_success_record():
    record = publisher.build_evidence_record(
        publisher_instance_id="publisher-a",
        chronyc_returncode=0,
        chronyc_tracking_raw=tracking(),
        captured_utc="2026-09-04T14:28:39Z",
        captured_monotonic_ns=CAPTURE_NS,
        host_boot_id=BOOT,
        host_time_namespace_id=TIME_NS,
    )

    assert record["publisher_status"] == "PASS"
    assert record["evidence_source"] == "real_host_chronyd"


def test_chronyc_failure_is_explicit_fail_record():
    record = publisher.build_evidence_record(
        publisher_instance_id="publisher-a",
        chronyc_returncode=1,
        chronyc_tracking_raw="",
        captured_utc="2026-09-04T14:28:39Z",
        captured_monotonic_ns=CAPTURE_NS,
        host_boot_id=BOOT,
        host_time_namespace_id=TIME_NS,
    )

    assert record["publisher_status"] == "FAIL"
    assert record["chronyc_returncode"] == 1


def test_atomic_write_replaces_existing_and_leaves_no_temp(tmp_path):
    path = tmp_path / "clock.json"
    path.write_text('{"old":true}\n', encoding="utf-8")

    value = {"new": True}

    publisher.write_json_atomic(path, value)

    assert json.loads(
        path.read_text(encoding="utf-8")
    ) == value

    assert not (
        tmp_path / "clock.json.tmp"
    ).exists()


def test_publish_once_success_is_accepted_by_consumer(tmp_path):
    path = tmp_path / "clock.json"

    publisher.publish_once(
        output_path=path,
        publisher_instance_id="publisher-a",
        chronyc_runner=lambda: (0, tracking()),
        boot_id_reader=lambda: BOOT,
        time_namespace_reader=lambda: TIME_NS,
        utc_reader=lambda: "2026-09-04T14:28:39Z",
        monotonic_ns_reader=lambda: CAPTURE_NS,
    )

    result = evaluate_clock_evidence_file(
        path,
        now_monotonic_ns=CAPTURE_NS + 1_000_000_000,
        current_boot_id=BOOT,
        current_time_namespace_id=TIME_NS,
    )

    assert result.status == GateStatus.PASS


def test_publish_once_chronyc_failure_replaces_old_pass(tmp_path):
    path = tmp_path / "clock.json"

    publisher.publish_once(
        output_path=path,
        publisher_instance_id="publisher-a",
        chronyc_runner=lambda: (0, tracking()),
        boot_id_reader=lambda: BOOT,
        time_namespace_reader=lambda: TIME_NS,
        utc_reader=lambda: "2026-09-04T14:28:39Z",
        monotonic_ns_reader=lambda: CAPTURE_NS,
    )

    publisher.publish_once(
        output_path=path,
        publisher_instance_id="publisher-a",
        chronyc_runner=lambda: (1, ""),
        boot_id_reader=lambda: BOOT,
        time_namespace_reader=lambda: TIME_NS,
        utc_reader=lambda: "2026-09-04T14:28:40Z",
        monotonic_ns_reader=lambda: CAPTURE_NS + 1_000_000_000,
    )

    stored = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert stored["publisher_status"] == "FAIL"

    result = evaluate_clock_evidence_file(
        path,
        now_monotonic_ns=CAPTURE_NS + 2_000_000_000,
        current_boot_id=BOOT,
        current_time_namespace_id=TIME_NS,
    )

    assert result.status == GateStatus.BLOCKED
    assert (
        result.reason
        == "CLOCK_EVIDENCE_PUBLISHER_NOT_PASS"
    )


def test_empty_success_output_is_fail():
    record = publisher.build_evidence_record(
        publisher_instance_id="publisher-a",
        chronyc_returncode=0,
        chronyc_tracking_raw="",
        captured_utc="2026-09-04T14:28:39Z",
        captured_monotonic_ns=CAPTURE_NS,
        host_boot_id=BOOT,
        host_time_namespace_id=TIME_NS,
    )

    assert record["publisher_status"] == "FAIL"
