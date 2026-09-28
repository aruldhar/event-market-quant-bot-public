from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_soak_storage_gate_restore import (
    StorageGateRestoreError,
    restore_storage_gate_evidence,
)


class FakeS3:
    def __init__(self, objects):
        self.objects = objects

    def head_object(self, *, Bucket, Key):
        body = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": {"sha256": sha256(body).hexdigest()}}

    def get_object(self, *, Bucket, Key):
        return {"Body": BytesIO(self.objects[Key])}


def _artifact(relative, body, run_id="run-1"):
    return {
        "relative_path": relative,
        "s3_key": f"candidate-e/runs/{run_id}/{relative}",
        "byte_count": len(body),
        "sha256": sha256(body).hexdigest(),
        "version_id": "v1",
    }


def _setup(tmp_path):
    run_id = "run-1"
    manifest_body = json.dumps({"artifact_descriptors": [{"path": "raw/kalshi/a.zst"}]}).encode()
    summary_body = b'{"run_id":"run-1"}'
    objects = {
        f"candidate-e/runs/{run_id}/raw/manifests/{run_id}.json": manifest_body,
        f"candidate-e/runs/{run_id}/telemetry/{run_id}/summary.json": summary_body,
    }
    receipt = {
        "schema_version": "candidate_e_soak_offsite_archive.v1",
        "run_id": run_id, "bucket": "private", "prefix": "candidate-e",
        "artifacts": [_artifact("raw/manifests/run-1.json", manifest_body),
                      _artifact("telemetry/run-1/summary.json", summary_body)],
    }
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return run_id, FakeS3(objects), receipt_path


def test_restore_rehydrates_only_terminal_storage_gate_evidence(tmp_path):
    run_id, client, receipt = _setup(tmp_path)
    result = restore_storage_gate_evidence(
        client=client, bucket="private", prefix="candidate-e", run_id=run_id,
        receipt_path=receipt, raw_root=tmp_path / "soak" / "raw",
        telemetry_root=tmp_path / "soak" / "telemetry",
    )
    assert result["restored_relative_paths"] == [
        "raw/manifests/run-1.json", "telemetry/run-1/summary.json",
    ]


def test_restore_rejects_remote_content_that_differs_from_receipt(tmp_path):
    run_id, client, receipt = _setup(tmp_path)
    client.objects[f"candidate-e/runs/{run_id}/telemetry/{run_id}/summary.json"] = b"tampered"
    with pytest.raises(StorageGateRestoreError, match="does not match"):
        restore_storage_gate_evidence(
            client=client, bucket="private", prefix="candidate-e", run_id=run_id,
            receipt_path=receipt, raw_root=tmp_path / "soak" / "raw",
            telemetry_root=tmp_path / "soak" / "telemetry",
        )
    assert not (tmp_path / "soak" / "raw" / "manifests" / "run-1.json").exists()
