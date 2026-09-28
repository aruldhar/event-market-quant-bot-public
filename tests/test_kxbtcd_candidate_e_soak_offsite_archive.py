import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_soak_offsite_archive import (
    OffsiteArchiveError,
    build_terminal_run_inventory,
    upload_terminal_run_archive,
)


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.uploads = []

    def get_bucket_versioning(self, *, Bucket):
        return {"Status": "Enabled"}

    def get_public_access_block(self, *, Bucket):
        return {"PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        }}

    def get_bucket_encryption(self, *, Bucket):
        return {"ServerSideEncryptionConfiguration": {"Rules": [{
            "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
        }]}}

    def upload_fileobj(self, source, bucket, key, extra):
        body = source.read()
        self.uploads.append((bucket, key, extra))
        self.objects[key] = (body, extra["Metadata"])

    def head_object(self, *, Bucket, Key):
        body, metadata = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": metadata, "VersionId": "version-1"}


def _paths(tmp_path):
    raw = tmp_path / "raw"
    telemetry = tmp_path / "telemetry"
    shadow = tmp_path / "live-shadow"
    run_id = "run-1"
    (raw / "manifests").mkdir(parents=True)
    (telemetry / run_id).mkdir(parents=True)
    (shadow / run_id).mkdir(parents=True)
    (raw / "manifests" / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "lifecycle_state": "TERMINAL", "measurement_complete": True,
    }), encoding="utf-8")
    (raw / "kalshi_production_ws").mkdir()
    (raw / "kalshi_production_ws" / f"20260910T040000Z__{run_id}.jsonl.zst").write_bytes(
        b"compressed-raw-evidence"
    )
    (telemetry / run_id / "source_events.jsonl").write_text('{"event":"x"}\n', encoding="utf-8")
    (shadow / run_id / "latest_causal_snapshot.json").write_text("{}", encoding="utf-8")
    ledger = tmp_path / "live_shadow_simulation.sqlite3"
    ledger.write_bytes(b"sqlite-ledger")
    return run_id, raw, telemetry, shadow, ledger


def test_terminal_inventory_contains_raw_telemetry_shadow_and_ledger(tmp_path):
    run_id, raw, telemetry, shadow, ledger = _paths(tmp_path)
    inventory = build_terminal_run_inventory(
        run_id=run_id, raw_root=raw, telemetry_root=telemetry,
        live_shadow_root=shadow, shadow_ledger_path=ledger,
    )
    assert [item.relative_path for item in inventory] == [
        "raw/kalshi_production_ws/20260910T040000Z__run-1.jsonl.zst",
        "raw/manifests/run-1.json", "telemetry/run-1/source_events.jsonl",
        "live-shadow/run-1/latest_causal_snapshot.json",
        "shadow-ledger/live_shadow_simulation.sqlite3",
    ]
    assert all(len(item.sha256) == 64 for item in inventory)


def test_archive_rejects_a_nonterminal_run_before_upload(tmp_path):
    run_id, raw, telemetry, shadow, ledger = _paths(tmp_path)
    (raw / "manifests" / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id, "lifecycle_state": "RUNNING", "measurement_complete": None,
    }), encoding="utf-8")
    client = FakeS3()
    with pytest.raises(OffsiteArchiveError, match="completed terminal"):
        upload_terminal_run_archive(
            client=client, bucket="private-bucket", prefix="candidate-e", run_id=run_id,
            raw_root=raw, telemetry_root=telemetry, live_shadow_root=shadow,
            shadow_ledger_path=ledger, receipt_path=tmp_path / "receipt.json",
        )
    assert client.uploads == []


def test_archive_rejects_a_bucket_without_complete_public_access_block(tmp_path):
    class UnsafeS3(FakeS3):
        def get_public_access_block(self, *, Bucket):
            return {"PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True, "IgnorePublicAcls": True,
                "BlockPublicPolicy": False, "RestrictPublicBuckets": True,
            }}

    run_id, raw, telemetry, shadow, ledger = _paths(tmp_path)
    client = UnsafeS3()
    with pytest.raises(OffsiteArchiveError, match="public access block"):
        upload_terminal_run_archive(
            client=client, bucket="private-bucket", prefix="candidate-e", run_id=run_id,
            raw_root=raw, telemetry_root=telemetry, live_shadow_root=shadow,
            shadow_ledger_path=ledger, receipt_path=tmp_path / "receipt.json",
        )
    assert client.uploads == []


def test_archive_rejects_an_active_shadow_ledger(tmp_path):
    run_id, raw, telemetry, shadow, ledger = _paths(tmp_path)
    Path(f"{ledger}-wal").write_bytes(b"active")
    with pytest.raises(OffsiteArchiveError, match="ledger is still active"):
        build_terminal_run_inventory(
            run_id=run_id, raw_root=raw, telemetry_root=telemetry,
            live_shadow_root=shadow, shadow_ledger_path=ledger,
        )


def test_archive_uploads_and_verifies_all_artifacts_with_a_receipt(tmp_path):
    run_id, raw, telemetry, shadow, ledger = _paths(tmp_path)
    receipt_path = tmp_path / "receipts" / "run-1.json"
    client = FakeS3()
    result = upload_terminal_run_archive(
        client=client, bucket="private-bucket", prefix="candidate-e", run_id=run_id,
        raw_root=raw, telemetry_root=telemetry, live_shadow_root=shadow,
        shadow_ledger_path=ledger, receipt_path=receipt_path,
    )
    assert result["schema_version"] == "candidate_e_soak_offsite_archive.v1"
    assert len(result["artifacts"]) == 5
    assert all(item["s3_key"].startswith("candidate-e/runs/run-1/") for item in result["artifacts"])
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == result
    upload_count = len(client.uploads)
    retry = upload_terminal_run_archive(
        client=client, bucket="private-bucket", prefix="candidate-e", run_id=run_id,
        raw_root=raw, telemetry_root=telemetry, live_shadow_root=shadow,
        shadow_ledger_path=ledger, receipt_path=receipt_path,
    )
    assert retry == result
    assert len(client.uploads) == upload_count
