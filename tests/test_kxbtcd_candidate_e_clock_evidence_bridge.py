from src.kxbtcd_candidate_e_clock_evidence_bridge import (
    CLOCK_EVIDENCE_SCHEMA,
    REAL_EVIDENCE_SOURCE,
    evaluate_clock_evidence_file,
    evaluate_clock_evidence_record,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus


BOOT = "0d6faadc-2fae-40bd-aa78-5d86807f8702"
TIME_NS = "time:[4026531834]"
NOW = 10_000_000_000


def tracking(system_time="0.000100000", direction="slow", leap="Normal"):
    return (
        "Reference ID    : A9FEA97B (169.254.169.123)\n"
        "Stratum         : 2\n"
        "Ref time (UTC)  : Fri Sep 04 14:28:31 2026\n"
        f"System time     : {system_time} seconds {direction} of NTP time\n"
        "Last offset     : -0.000000614 seconds\n"
        "RMS offset      : 0.000004227 seconds\n"
        "Frequency       : 1.040 ppm slow\n"
        "Residual freq   : -0.001 ppm\n"
        "Skew            : 0.045 ppm\n"
        "Root delay      : 0.000144519 seconds\n"
        "Root dispersion : 0.000035586 seconds\n"
        "Update interval : 16.2 seconds\n"
        f"Leap status     : {leap}\n"
    )


def record(**overrides):
    value = {
        "schema_version": CLOCK_EVIDENCE_SCHEMA,
        "evidence_source": REAL_EVIDENCE_SOURCE,
        "publisher_instance_id": "publisher-1",
        "captured_utc": "2026-09-04T14:28:39Z",
        "captured_monotonic_ns": NOW - 1_000_000_000,
        "host_boot_id": BOOT,
        "host_time_namespace_id": TIME_NS,
        "chronyc_returncode": 0,
        "chronyc_tracking_raw": tracking(),
        "publisher_status": "PASS",
    }
    value.update(overrides)
    return value


def evaluate(value):
    return evaluate_clock_evidence_record(
        value,
        now_monotonic_ns=NOW,
        current_boot_id=BOOT,
        current_time_namespace_id=TIME_NS,
    )


def test_fresh_real_clock_evidence_passes():
    result = evaluate(record())

    assert result.status == GateStatus.PASS
    assert result.reason == "PASS"
    assert result.evidence_age_ns == 1_000_000_000
    assert result.chrony.status == GateStatus.PASS
    assert result.chrony.absolute_system_time_offset_ms == 0.1


def test_exact_five_second_age_is_allowed():
    result = evaluate(
        record(captured_monotonic_ns=NOW - 5_000_000_000)
    )
    assert result.status == GateStatus.PASS


def test_evidence_older_than_five_seconds_blocks():
    result = evaluate(
        record(captured_monotonic_ns=NOW - 5_000_000_001)
    )
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_STALE"


def test_negative_age_blocks():
    result = evaluate(
        record(captured_monotonic_ns=NOW + 1)
    )
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_NEGATIVE_AGE"


def test_boot_id_mismatch_blocks():
    result = evaluate(record(host_boot_id="other"))
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_BOOT_ID_MISMATCH"


def test_time_namespace_mismatch_blocks():
    result = evaluate(record(host_time_namespace_id="time:[999]"))
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_TIME_NAMESPACE_MISMATCH"


def test_publisher_failure_blocks():
    result = evaluate(record(publisher_status="FAIL"))
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_PUBLISHER_NOT_PASS"


def test_chronyc_nonzero_blocks():
    result = evaluate(record(chronyc_returncode=1))
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_CHRONYC_FAILED"


def test_non_real_evidence_is_fatal():
    result = evaluate(record(evidence_source="synthetic_validation"))
    assert result.status == GateStatus.FATAL
    assert result.reason == "SYNTHETIC_OR_NONPRODUCTION_CLOCK_EVIDENCE"


def test_offset_outside_frozen_250ms_gate_does_not_pass():
    result = evaluate(
        record(
            chronyc_tracking_raw=tracking(
                system_time="0.300000000"
            )
        )
    )

    # The already-accepted parser owns the 250 ms rule.
    assert result.status == GateStatus.BLOCKED
    assert result.chrony.status == GateStatus.BLOCKED


def test_missing_file_blocks(tmp_path):
    result = evaluate_clock_evidence_file(
        tmp_path / "missing.json",
        now_monotonic_ns=NOW,
        current_boot_id=BOOT,
        current_time_namespace_id=TIME_NS,
    )
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_FILE_MISSING"


def test_invalid_json_blocks(tmp_path):
    path = tmp_path / "clock.json"
    path.write_text("{", encoding="utf-8")

    result = evaluate_clock_evidence_file(
        path,
        now_monotonic_ns=NOW,
        current_boot_id=BOOT,
        current_time_namespace_id=TIME_NS,
    )
    assert result.status == GateStatus.BLOCKED
    assert result.reason == "CLOCK_EVIDENCE_JSON_INVALID"
