import json

from src.kxbtcd_candidate_e_read_only_soak_acceptance_cli import create_acceptance_receipt


def test_cli_writes_receipt_only_for_accepted_evidence(tmp_path):
    summary = tmp_path / "summary.json"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "receipt.json"
    summary.write_text(json.dumps({
        "run_id": "soak-24h", "measurement_complete": True,
        "safety_invariant_status": "PASS", "execution_mode": "disabled",
        "readiness_input_contract": "v2_exact_rest_candle_and_kalshi",
        "orders": 0, "signals": 0, "production_writes": 0,
    }), encoding="utf-8")
    manifest.write_text(json.dumps({
        "run_id": "soak-24h", "measurement_complete": True,
        "lifecycle_state": "TERMINAL", "operational_classification": "MEASUREMENT_COMPLETE",
        "safety_invariant_status": "PASS",
    }), encoding="utf-8")

    result = create_acceptance_receipt(summary_path=summary, manifest_path=manifest, output_path=output)

    assert result == {"accepted_soak_run_id": "soak-24h"}
    assert json.loads(output.read_text(encoding="utf-8")) == result
