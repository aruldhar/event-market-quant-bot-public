"""Verified, terminal-only off-instance archive of Candidate-E soak evidence.

The uploader is deliberately separate from collectors, shadow simulation, and
Grafana. It consumes only completed local artifacts and EC2 instance-role S3
credentials. It never receives venue credentials and cannot place orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import json

from .kxbtcd_candidate_e_soak_archive import file_sha256, write_json_atomic


ARCHIVE_SCHEMA_VERSION = "candidate_e_soak_offsite_archive.v1"


class OffsiteArchiveError(RuntimeError):
    pass


class S3Client(Protocol):
    def get_bucket_versioning(self, *, Bucket: str) -> dict[str, Any]: ...
    def get_public_access_block(self, *, Bucket: str) -> dict[str, Any]: ...
    def get_bucket_encryption(self, *, Bucket: str) -> dict[str, Any]: ...
    def upload_fileobj(self, Fileobj, Bucket: str, Key: str, ExtraArgs: dict[str, Any]) -> None: ...
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class OffsiteArchiveArtifact:
    local_path: Path
    relative_path: str
    byte_count: int
    sha256: str


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OffsiteArchiveError(f"{field} is required")
    return value.strip()


def _safe_relative(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise OffsiteArchiveError("archive artifact escapes its declared root") from exc
    if path.is_symlink() or not path.is_file():
        raise OffsiteArchiveError("archive artifact must be a regular file")
    return relative.as_posix()


def _files_under(*, root: Path, key_prefix: str) -> tuple[tuple[Path, str], ...]:
    if not root.is_dir():
        return ()
    result: list[tuple[Path, str]] = []
    for candidate in sorted(root.rglob("*")):
        if candidate.is_file() and not candidate.is_symlink():
            result.append((candidate, f"{key_prefix}/{_safe_relative(candidate, root)}"))
    return tuple(result)


def _run_raw_files(*, root: Path, run_id: str) -> tuple[tuple[Path, str], ...]:
    """Return every raw artifact whose filename is bound to this run id."""
    if not root.is_dir():
        raise OffsiteArchiveError("raw archive root is unavailable")
    result: list[tuple[Path, str]] = []
    for candidate in sorted(root.rglob("*")):
        if candidate.is_file() and not candidate.is_symlink() and run_id in candidate.name:
            result.append((candidate, "raw/" + _safe_relative(candidate, root)))
    return tuple(result)


def _terminal_manifest(*, raw_root: Path, run_id: str) -> Path:
    path = raw_root / "manifests" / f"{run_id}.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OffsiteArchiveError("terminal run manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("run_id") != run_id:
        raise OffsiteArchiveError("terminal run manifest identity is invalid")
    if manifest.get("lifecycle_state") != "TERMINAL" or manifest.get("measurement_complete") is not True:
        raise OffsiteArchiveError("offsite archive requires a completed terminal run")
    return path


def build_terminal_run_inventory(
    *, run_id: str, raw_root: str | Path, telemetry_root: str | Path,
    live_shadow_root: str | Path, shadow_ledger_path: str | Path,
) -> tuple[OffsiteArchiveArtifact, ...]:
    """Inventory all source evidence needed to reconstruct one completed run."""
    run_id = _text(run_id, "run_id")
    raw = Path(raw_root)
    telemetry = Path(telemetry_root) / run_id
    shadow = Path(live_shadow_root) / run_id
    ledger = Path(shadow_ledger_path)
    _terminal_manifest(raw_root=raw, run_id=run_id)
    if any(Path(f"{ledger}{suffix}").exists() for suffix in ("-wal", "-shm")):
        raise OffsiteArchiveError("shadow ledger is still active; wait for its writer to stop")
    candidates = [
        *_run_raw_files(root=raw, run_id=run_id),
        *_files_under(root=telemetry, key_prefix=f"telemetry/{run_id}"),
        *_files_under(root=shadow, key_prefix=f"live-shadow/{run_id}"),
    ]
    if not ledger.is_file() or ledger.is_symlink():
        raise OffsiteArchiveError("shadow ledger snapshot is unavailable")
    candidates.append((ledger, "shadow-ledger/" + ledger.name))
    seen: set[str] = set()
    artifacts: list[OffsiteArchiveArtifact] = []
    for path, relative_path in candidates:
        if relative_path in seen:
            raise OffsiteArchiveError("archive inventory has duplicate relative paths")
        seen.add(relative_path)
        if not path.is_file() or path.is_symlink():
            raise OffsiteArchiveError("archive inventory contains an invalid artifact")
        artifacts.append(OffsiteArchiveArtifact(
            path, relative_path, path.stat().st_size, file_sha256(path),
        ))
    return tuple(artifacts)


def verify_private_versioned_bucket(*, client: S3Client, bucket: str) -> None:
    bucket = _text(bucket, "bucket")
    if client.get_bucket_versioning(Bucket=bucket).get("Status") != "Enabled":
        raise OffsiteArchiveError("S3 archive bucket versioning is not enabled")
    public = client.get_public_access_block(Bucket=bucket).get("PublicAccessBlockConfiguration")
    if not isinstance(public, dict) or not all(public.get(key) is True for key in (
        "BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets",
    )):
        raise OffsiteArchiveError("S3 archive bucket public access block is incomplete")
    try:
        rules = client.get_bucket_encryption(Bucket=bucket)["ServerSideEncryptionConfiguration"]["Rules"]
        algorithm = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OffsiteArchiveError("S3 archive bucket default encryption is unavailable") from exc
    if algorithm not in {"AES256", "aws:kms"}:
        raise OffsiteArchiveError("S3 archive bucket encryption is unsupported")


def _object_key(*, prefix: str, run_id: str, relative_path: str) -> str:
    clean_prefix = _text(prefix, "prefix").strip("/")
    if ".." in Path(clean_prefix).parts or ".." in Path(relative_path).parts:
        raise OffsiteArchiveError("S3 archive key path is invalid")
    return f"{clean_prefix}/runs/{run_id}/{relative_path}"


def _matching_remote_object(*, client: S3Client, bucket: str, key: str,
                            artifact: OffsiteArchiveArtifact) -> dict[str, Any] | None:
    """Return an already verified object, otherwise let the caller upload it.

    A failed head can mean the object does not exist.  Upload then remains the
    authoritative operation and will expose actual network or authorization
    failures directly.
    """
    try:
        remote = client.head_object(Bucket=bucket, Key=key)
    except Exception:
        return None
    metadata = remote.get("Metadata")
    if (
        remote.get("ContentLength") == artifact.byte_count
        and isinstance(metadata, dict)
        and metadata.get("sha256") == artifact.sha256
    ):
        return remote
    return None


def upload_terminal_run_archive(
    *, client: S3Client, bucket: str, prefix: str, run_id: str,
    raw_root: str | Path, telemetry_root: str | Path,
    live_shadow_root: str | Path, shadow_ledger_path: str | Path,
    receipt_path: str | Path, sse: str = "AES256", kms_key_id: str | None = None,
) -> dict[str, Any]:
    """Upload and verify a terminal run without deleting local artifacts."""
    if sse not in {"AES256", "aws:kms"}:
        raise OffsiteArchiveError("S3 server-side encryption setting is invalid")
    if (sse == "aws:kms") != bool(kms_key_id):
        raise OffsiteArchiveError("KMS key setting does not match encryption mode")
    verify_private_versioned_bucket(client=client, bucket=bucket)
    inventory = build_terminal_run_inventory(
        run_id=run_id, raw_root=raw_root, telemetry_root=telemetry_root,
        live_shadow_root=live_shadow_root, shadow_ledger_path=shadow_ledger_path,
    )
    uploaded: list[dict[str, Any]] = []
    for artifact in inventory:
        key = _object_key(prefix=prefix, run_id=run_id, relative_path=artifact.relative_path)
        safe_bucket = _text(bucket, "bucket")
        verified = _matching_remote_object(
            client=client, bucket=safe_bucket, key=key, artifact=artifact,
        )
        if verified is None:
            extra = {
                "ServerSideEncryption": sse,
                "Metadata": {"sha256": artifact.sha256, "run-id": run_id},
            }
            if kms_key_id:
                extra["SSEKMSKeyId"] = kms_key_id
            with artifact.local_path.open("rb") as source:
                client.upload_fileobj(source, safe_bucket, key, extra)
            verified = client.head_object(Bucket=safe_bucket, Key=key)
            metadata = verified.get("Metadata")
            if (
                verified.get("ContentLength") != artifact.byte_count
                or not isinstance(metadata, dict)
                or metadata.get("sha256") != artifact.sha256
            ):
                raise OffsiteArchiveError("uploaded S3 artifact verification failed")
        uploaded.append({
            "relative_path": artifact.relative_path,
            "s3_key": key,
            "byte_count": artifact.byte_count,
            "sha256": artifact.sha256,
            "version_id": verified.get("VersionId"),
        })
    receipt = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "run_id": _text(run_id, "run_id"),
        "bucket": _text(bucket, "bucket"),
        "prefix": _text(prefix, "prefix").strip("/"),
        "server_side_encryption": sse,
        "artifacts": uploaded,
    }
    write_json_atomic(Path(receipt_path), receipt)
    return receipt
