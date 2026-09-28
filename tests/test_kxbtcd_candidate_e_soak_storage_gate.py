import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

import src.kxbtcd_candidate_e_soak_storage_gate as storage_gate
from src.kxbtcd_candidate_e_soak_storage_gate import (
    ABSOLUTE_FLOOR_BYTES,
    SCHEMA_VERSION,
    SoakStorageGateError,
    freeze_storage_gate_receipt_from_verified_archive,
    required_free_bytes,
    validate_storage_gate_receipt,
)


def test_formula_preserves_absolute_floor():
    assert required_free_bytes(compressed_bytes_per_hour=1, raw_bytes_per_hour=1) == ABSOLUTE_FLOOR_BYTES


def test_formula_rejects_invalid_empirical_rate():
    with pytest.raises(SoakStorageGateError):
        required_free_bytes(compressed_bytes_per_hour=-1, raw_bytes_per_hour=1)


def test_receipt_rejects_image_mismatch_before_24h(tmp_path):
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "accepted_shakedown_run_id": "r12",
        "canonical_image_digest": "sha256:" + "a" * 64,
        "shakedown_summary_sha256": "b" * 64,
        "compressed_bytes_per_hour": 1,
        "raw_bytes_per_hour": 1,
        "required_free_bytes": ABSOLUTE_FLOOR_BYTES,
        "available_free_bytes_at_freeze": ABSOLUTE_FLOOR_BYTES,
    }
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(SoakStorageGateError, match="image mismatch"):
        validate_storage_gate_receipt(receipt_path=path, archive_root=tmp_path,
            canonical_image_digest="sha256:" + "c" * 64)


def test_archive_recovery_freezes_gate_from_receipt_bound_terminal_evidence(tmp_path, monkeypatch):
    run_id = "r28"
    digest = "sha256:" + "a" * 64
    manifest = tmp_path / "raw" / "manifests" / f"{run_id}.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"restored": true}', encoding="utf-8")
    summary = tmp_path / "telemetry" / run_id / "summary.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps({
        "run_id": run_id, "measurement_complete": True,
        "safety_invariant_status": "PASS", "orders": 0,
        "production_writes": 0, "signals": 0,
        "whole_attempt_bytes_per_hour": {
            "compressed_bytes_written": 10, "raw_bytes_written": 20,
        },
    }), encoding="utf-8")
    receipt = tmp_path / "archive-receipt.json"
    receipt.write_text(json.dumps({
        "schema_version": "candidate_e_soak_offsite_archive.v1", "run_id": run_id,
        "artifacts": [
            {"relative_path": f"raw/manifests/{run_id}.json",
             "byte_count": manifest.stat().st_size,
             "sha256": sha256(manifest.read_bytes()).hexdigest()},
            {"relative_path": f"telemetry/{run_id}/summary.json",
             "byte_count": summary.stat().st_size,
             "sha256": sha256(summary.read_bytes()).hexdigest()},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(storage_gate, "validate_soak_run_manifest", lambda *_args, **_kwargs: {
        "run_id": run_id, "lifecycle_state": "TERMINAL",
        "measurement_complete": True, "safety_invariant_status": "PASS",
        "docker_image_digest": digest,
    })
    monkeypatch.setattr(storage_gate.shutil, "disk_usage", lambda _path: SimpleNamespace(
        free=ABSOLUTE_FLOOR_BYTES))

    output = tmp_path / "gate.json"
    result = freeze_storage_gate_receipt_from_verified_archive(
        shakedown_summary_path=summary, shakedown_manifest_path=manifest,
        archive_receipt_path=receipt, archive_root=tmp_path,
        canonical_image_digest=digest, output_path=output,
    )

    assert output.is_file()
    assert result["accepted_shakedown_run_id"] == run_id


def test_archive_recovery_rejects_evidence_not_bound_to_receipt(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    summary = tmp_path / "summary.json"
    manifest.write_text("{}", encoding="utf-8")
    summary.write_text("{}", encoding="utf-8")
    receipt = tmp_path / "archive-receipt.json"
    receipt.write_text(json.dumps({
        "schema_version": "candidate_e_soak_offsite_archive.v1", "run_id": "r28",
        "artifacts": [],
    }), encoding="utf-8")
    monkeypatch.setattr(storage_gate, "validate_soak_run_manifest", lambda *_args, **_kwargs: {
        "run_id": "r28",
    })

    with pytest.raises(SoakStorageGateError, match="lacks required"):
        freeze_storage_gate_receipt_from_verified_archive(
            shakedown_summary_path=summary, shakedown_manifest_path=manifest,
            archive_receipt_path=receipt, archive_root=tmp_path,
            canonical_image_digest="sha256:" + "a" * 64,
            output_path=tmp_path / "gate.json",
        )
