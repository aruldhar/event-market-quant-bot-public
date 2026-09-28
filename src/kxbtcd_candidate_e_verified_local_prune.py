"""Verify archived Candidate-E run evidence before explicitly pruning local copies.

This module is intentionally a terminal-only maintenance operation.  It never
touches the shared shadow ledger, and it verifies every local file and its S3
copy before deleting anything.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
import json

from .kxbtcd_candidate_e_soak_archive import file_sha256
from .kxbtcd_candidate_e_soak_offsite_archive import ARCHIVE_SCHEMA_VERSION


class VerifiedLocalPruneError(RuntimeError):
    pass


class S3ReceiptClient(Protocol):
    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]: ...


def _read_receipt(path: str | Path) -> dict[str, Any]:
    try:
        receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VerifiedLocalPruneError("archive receipt is unreadable") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise VerifiedLocalPruneError("archive receipt schema is invalid")
    if not isinstance(receipt.get("run_id"), str) or not receipt["run_id"]:
        raise VerifiedLocalPruneError("archive receipt run identity is invalid")
    if not isinstance(receipt.get("bucket"), str) or not receipt["bucket"]:
        raise VerifiedLocalPruneError("archive receipt bucket is invalid")
    if not isinstance(receipt.get("artifacts"), list) or not receipt["artifacts"]:
        raise VerifiedLocalPruneError("archive receipt artifact list is invalid")
    return receipt


def _under(root: Path, relative_parts: tuple[str, ...]) -> Path:
    if not relative_parts or any(part in {"", ".", ".."} for part in relative_parts):
        raise VerifiedLocalPruneError("receipt artifact path is invalid")
    candidate = root.joinpath(*relative_parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise VerifiedLocalPruneError("receipt artifact escapes its local root") from exc
    if candidate.is_symlink() or not candidate.is_file():
        raise VerifiedLocalPruneError("local archive artifact is unavailable")
    return candidate


def _local_artifact_path(*, relative_path: str, run_id: str, raw_root: Path,
                         telemetry_root: Path, live_shadow_root: Path) -> Path | None:
    parts = tuple(Path(relative_path).parts)
    if len(parts) >= 2 and parts[0] == "raw":
        return _under(raw_root, parts[1:])
    expected_telemetry = ("telemetry", run_id)
    if parts[:2] == expected_telemetry:
        return _under(telemetry_root / run_id, parts[2:])
    expected_shadow = ("live-shadow", run_id)
    if parts[:2] == expected_shadow:
        return _under(live_shadow_root / run_id, parts[2:])
    if parts[:1] == ("shadow-ledger",):
        # The ledger is shared by multiple runs.  It is archived but never
        # pruned by a run-scoped command.
        return None
    raise VerifiedLocalPruneError("receipt artifact has an unsupported local path")


def verified_prunable_paths(*, client: S3ReceiptClient, receipt_path: str | Path,
                            raw_root: str | Path, telemetry_root: str | Path,
                            live_shadow_root: str | Path) -> tuple[dict[str, Any], tuple[tuple[str, Path], ...]]:
    """Verify all prune candidates first; return no paths if any check fails."""
    receipt = _read_receipt(receipt_path)
    run_id = receipt["run_id"]
    raw, telemetry, shadow = Path(raw_root), Path(telemetry_root), Path(live_shadow_root)
    verified: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for artifact in receipt["artifacts"]:
        if not isinstance(artifact, dict):
            raise VerifiedLocalPruneError("archive receipt artifact is invalid")
        relative_path = artifact.get("relative_path")
        key, expected_sha, expected_bytes = artifact.get("s3_key"), artifact.get("sha256"), artifact.get("byte_count")
        if (not isinstance(relative_path, str) or relative_path in seen or not isinstance(key, str)
                or not isinstance(expected_sha, str) or len(expected_sha) != 64
                or not isinstance(expected_bytes, int) or expected_bytes < 0):
            raise VerifiedLocalPruneError("archive receipt artifact fields are invalid")
        seen.add(relative_path)
        local_path = _local_artifact_path(
            relative_path=relative_path, run_id=run_id, raw_root=raw,
            telemetry_root=telemetry, live_shadow_root=shadow,
        )
        if local_path is None:
            continue
        if local_path.stat().st_size != expected_bytes or file_sha256(local_path) != expected_sha:
            raise VerifiedLocalPruneError("local artifact does not match its archive receipt")
        try:
            remote = client.head_object(Bucket=receipt["bucket"], Key=key)
        except Exception as exc:
            raise VerifiedLocalPruneError("cannot verify archived S3 artifact") from exc
        metadata = remote.get("Metadata")
        if (remote.get("ContentLength") != expected_bytes or not isinstance(metadata, dict)
                or metadata.get("sha256") != expected_sha):
            raise VerifiedLocalPruneError("archived S3 artifact does not match its receipt")
        verified.append((relative_path, local_path))
    return receipt, tuple(verified)


def prune_verified_local_run(*, client: S3ReceiptClient, receipt_path: str | Path,
                             raw_root: str | Path, telemetry_root: str | Path,
                             live_shadow_root: str | Path, confirm_prune: bool) -> dict[str, Any]:
    """Delete only verified, run-scoped local evidence after explicit confirmation."""
    if confirm_prune is not True:
        raise VerifiedLocalPruneError("local evidence pruning requires explicit confirmation")
    receipt, verified = verified_prunable_paths(
        client=client, receipt_path=receipt_path, raw_root=raw_root,
        telemetry_root=telemetry_root, live_shadow_root=live_shadow_root,
    )
    for _, local_path in verified:
        local_path.unlink()
    return {
        "schema_version": "candidate_e_verified_local_prune.v1",
        "run_id": receipt["run_id"],
        "deleted_relative_paths": [relative for relative, _ in verified],
        "preserved_shared_relative_paths": [
            item["relative_path"] for item in receipt["artifacts"]
            if str(item.get("relative_path", "")).startswith("shadow-ledger/")
        ],
    }
