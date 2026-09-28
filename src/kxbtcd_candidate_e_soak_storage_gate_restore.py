"""Restore only verified shakedown evidence needed to freeze a storage gate."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol
import json
import os

from .kxbtcd_candidate_e_soak_offsite_archive import ARCHIVE_SCHEMA_VERSION


class StorageGateRestoreError(RuntimeError):
    pass


class S3Client(Protocol):
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...
    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...


def _safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise StorageGateRestoreError("archive relative path is invalid")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise StorageGateRestoreError("archive relative path is invalid")
    return candidate.as_posix()


def _receipt_index(*, receipt_path: str | Path, bucket: str, prefix: str,
                   run_id: str) -> dict[str, dict[str, Any]]:
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageGateRestoreError("archive receipt is unreadable") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise StorageGateRestoreError("archive receipt schema is invalid")
    if (receipt.get("run_id") != run_id or receipt.get("bucket") != bucket
            or receipt.get("prefix") != prefix.strip("/")):
        raise StorageGateRestoreError("archive receipt identity does not match restore request")
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list):
        raise StorageGateRestoreError("archive receipt artifacts are invalid")
    index: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise StorageGateRestoreError("archive receipt artifact is invalid")
        relative = _safe_relative(artifact.get("relative_path"))
        expected_key = f"{prefix.strip('/')}/runs/{run_id}/{relative}"
        if (relative in index or artifact.get("s3_key") != expected_key
                or not isinstance(artifact.get("byte_count"), int)
                or artifact["byte_count"] < 0
                or not isinstance(artifact.get("sha256"), str)
                or len(artifact["sha256"]) != 64):
            raise StorageGateRestoreError("archive receipt artifact is invalid")
        index[relative] = artifact
    return index


def _target(*, relative: str, raw_root: Path, telemetry_root: Path,
            run_id: str) -> Path:
    if relative.startswith("raw/"):
        return raw_root / relative.removeprefix("raw/")
    expected_summary = f"telemetry/{run_id}/summary.json"
    if relative == expected_summary:
        return telemetry_root / run_id / "summary.json"
    raise StorageGateRestoreError("restore requested an unsupported archive artifact")


def _download_verified(*, client: S3Client, bucket: str, artifact: dict[str, Any],
                       target: Path) -> None:
    try:
        head = client.head_object(Bucket=bucket, Key=artifact["s3_key"])
        response = client.get_object(Bucket=bucket, Key=artifact["s3_key"])
        body = response["Body"].read()
    except Exception as exc:
        raise StorageGateRestoreError("verified archive object cannot be retrieved") from exc
    metadata = head.get("Metadata")
    if (not isinstance(body, bytes) or head.get("ContentLength") != artifact["byte_count"]
            or not isinstance(metadata, dict)
            or metadata.get("sha256") != artifact["sha256"]
            or len(body) != artifact["byte_count"]
            or sha256(body).hexdigest() != artifact["sha256"]):
        raise StorageGateRestoreError("archive object does not match its verified receipt")
    if target.exists() or target.is_symlink():
        raise StorageGateRestoreError("refusing to overwrite local evidence during restore")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".restore-tmp")
    if temporary.exists():
        raise StorageGateRestoreError("restore temporary path already exists")
    try:
        with temporary.open("xb") as destination:
            destination.write(body)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def restore_storage_gate_evidence(*, client: S3Client, bucket: str, prefix: str,
                                  run_id: str, receipt_path: str | Path,
                                  raw_root: str | Path,
                                  telemetry_root: str | Path) -> dict[str, Any]:
    """Restore the minimum hash-verified evidence required for a storage gate.

    This deliberately cannot restore the shadow ledger or arbitrary archived
    files.  A terminal manifest can describe shared historical raw segments,
    while a run-scoped archive intentionally contains only this run's files.
    The storage-gate recovery therefore restores only the manifest and its
    terminal summary, each verified against the existing archive receipt.
    """
    if not isinstance(run_id, str) or not run_id:
        raise StorageGateRestoreError("run id is required")
    raw = Path(raw_root)
    telemetry = Path(telemetry_root)
    index = _receipt_index(receipt_path=receipt_path, bucket=bucket,
                           prefix=prefix, run_id=run_id)
    manifest_relative = f"raw/manifests/{run_id}.json"
    summary_relative = f"telemetry/{run_id}/summary.json"
    if manifest_relative not in index or summary_relative not in index:
        raise StorageGateRestoreError("archive receipt lacks storage-gate evidence")

    restored: list[Path] = []
    try:
        manifest_path = _target(relative=manifest_relative, raw_root=raw,
                                telemetry_root=telemetry, run_id=run_id)
        _download_verified(client=client, bucket=bucket,
                           artifact=index[manifest_relative], target=manifest_path)
        restored.append(manifest_path)
        summary_path = _target(relative=summary_relative, raw_root=raw,
                               telemetry_root=telemetry, run_id=run_id)
        _download_verified(client=client, bucket=bucket,
                           artifact=index[summary_relative], target=summary_path)
        restored.append(summary_path)
    except Exception:
        for path in reversed(restored):
            path.unlink(missing_ok=True)
        raise
    return {
        "run_id": run_id,
        "restored_relative_paths": [
            str(path.relative_to(raw.parent)).replace("\\", "/") for path in restored
        ],
    }
