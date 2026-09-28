import json

import pytest

from src.kxbtcd_candidate_e_soak_archive import file_sha256
from src.kxbtcd_candidate_e_verified_local_prune import (
    VerifiedLocalPruneError,
    prune_verified_local_run,
)


class FakeS3:
    def __init__(self, objects):
        self.objects = objects

    def head_object(self, *, Bucket, Key):
        body = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": {"sha256": file_sha256_from_bytes(body)}}


def file_sha256_from_bytes(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


def paths_and_receipt(tmp_path):
    run_id = "run-1"
    raw, telemetry, shadow = tmp_path / "raw", tmp_path / "telemetry", tmp_path / "shadow"
    raw_file = raw / "manifests" / f"{run_id}.json"
    telemetry_file = telemetry / run_id / "metrics.jsonl"
    shadow_file = shadow / run_id / "latest_causal_snapshot.json"
    for path, body in ((raw_file, b"raw"), (telemetry_file, b"metrics"), (shadow_file, b"shadow")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    ledger = tmp_path / "ledger.sqlite"
    ledger.write_bytes(b"shared-ledger")
    artifacts = []
    for relative, path in (
        (f"raw/manifests/{run_id}.json", raw_file),
        (f"telemetry/{run_id}/metrics.jsonl", telemetry_file),
        (f"live-shadow/{run_id}/latest_causal_snapshot.json", shadow_file),
        ("shadow-ledger/live_shadow_simulation.sqlite3", ledger),
    ):
        body = path.read_bytes()
        artifacts.append({"relative_path": relative, "s3_key": f"candidate-e/runs/{run_id}/{relative}",
                          "byte_count": len(body), "sha256": file_sha256(path)})
    receipt = {"schema_version": "candidate_e_soak_offsite_archive.v1", "run_id": run_id,
               "bucket": "private-bucket", "artifacts": artifacts}
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return raw, telemetry, shadow, receipt_path, ledger, {item["s3_key"]: (
        (raw / "manifests" / f"{run_id}.json").read_bytes() if item["relative_path"].startswith("raw/") else
        (telemetry / run_id / "metrics.jsonl").read_bytes() if item["relative_path"].startswith("telemetry/") else
        (shadow / run_id / "latest_causal_snapshot.json").read_bytes() if item["relative_path"].startswith("live-shadow/") else
        ledger.read_bytes()) for item in artifacts}


def test_verified_prune_requires_confirmation_and_preserves_shared_ledger(tmp_path):
    raw, telemetry, shadow, receipt, ledger, objects = paths_and_receipt(tmp_path)
    with pytest.raises(VerifiedLocalPruneError, match="explicit confirmation"):
        prune_verified_local_run(client=FakeS3(objects), receipt_path=receipt, raw_root=raw,
                                telemetry_root=telemetry, live_shadow_root=shadow, confirm_prune=False)
    result = prune_verified_local_run(client=FakeS3(objects), receipt_path=receipt, raw_root=raw,
                                      telemetry_root=telemetry, live_shadow_root=shadow, confirm_prune=True)
    assert len(result["deleted_relative_paths"]) == 3
    assert result["preserved_shared_relative_paths"] == ["shadow-ledger/live_shadow_simulation.sqlite3"]
    assert not (raw / "manifests" / "run-1.json").exists()
    assert not (telemetry / "run-1" / "metrics.jsonl").exists()
    assert not (shadow / "run-1" / "latest_causal_snapshot.json").exists()
    assert ledger.read_bytes() == b"shared-ledger"


def test_verification_failure_deletes_nothing(tmp_path):
    raw, telemetry, shadow, receipt, ledger, objects = paths_and_receipt(tmp_path)
    objects[next(iter(objects))] = b"tampered"
    with pytest.raises(VerifiedLocalPruneError, match="S3 artifact"):
        prune_verified_local_run(client=FakeS3(objects), receipt_path=receipt, raw_root=raw,
                                telemetry_root=telemetry, live_shadow_root=shadow, confirm_prune=True)
    assert (raw / "manifests" / "run-1.json").exists()
    assert (telemetry / "run-1" / "metrics.jsonl").exists()
    assert (shadow / "run-1" / "latest_causal_snapshot.json").exists()
    assert ledger.exists()
