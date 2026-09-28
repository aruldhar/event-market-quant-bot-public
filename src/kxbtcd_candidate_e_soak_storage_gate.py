"""Freeze and enforce the empirical free-disk gate before a 24-hour soak.

This module is intentionally offline-only.  It turns a completed one-hour
summary plus its verified manifest into an immutable receipt.  The 24-hour
entry point accepts only a receipt for its exact image digest and rechecks
free space immediately before sources can open.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import shutil

from .kxbtcd_candidate_e_soak_archive import file_sha256, write_json_atomic
from .kxbtcd_candidate_e_soak_manifest import validate_soak_run_manifest
from .kxbtcd_candidate_e_soak_offsite_archive import ARCHIVE_SCHEMA_VERSION


SCHEMA_VERSION = "candidate_e_soak_storage_gate.v1"
ABSOLUTE_FLOOR_BYTES = 10 * 1024 ** 3
RESERVE_BYTES = 2 * 1024 ** 3


class SoakStorageGateError(RuntimeError):
    pass


def required_free_bytes(*, compressed_bytes_per_hour, raw_bytes_per_hour):
    """Apply the frozen B5-R5-B storage formula without rounding down."""
    for value in (compressed_bytes_per_hour, raw_bytes_per_hour):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise SoakStorageGateError("invalid empirical storage rate")
    formula = math.ceil(1.5 * ((24 * compressed_bytes_per_hour) + (2 * raw_bytes_per_hour)) + RESERVE_BYTES)
    return max(ABSOLUTE_FLOOR_BYTES, formula)


def _object(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SoakStorageGateError("storage-gate JSON is unreadable") from exc
    if not isinstance(value, dict):
        raise SoakStorageGateError("storage-gate JSON object required")
    return value


def _freeze_storage_gate_receipt(*, shakedown_summary_path, manifest,
                                 archive_root, canonical_image_digest, output_path):
    summary_path = Path(shakedown_summary_path)
    summary = _object(summary_path)
    if (summary.get("measurement_complete") is not True
            or summary.get("safety_invariant_status") != "PASS"
            or summary.get("orders") != 0
            or summary.get("production_writes") != 0
            or summary.get("signals") != 0):
        raise SoakStorageGateError("shakedown is not safe and complete")
    if (manifest.get("lifecycle_state") != "TERMINAL"
            or manifest.get("measurement_complete") is not True
            or manifest.get("safety_invariant_status") != "PASS"
            or manifest.get("docker_image_digest") != canonical_image_digest
            or summary.get("run_id") != manifest.get("run_id")):
        raise SoakStorageGateError("shakedown identity does not qualify")
    rates = summary.get("whole_attempt_bytes_per_hour")
    if not isinstance(rates, dict):
        raise SoakStorageGateError("shakedown storage rates are missing")
    required = required_free_bytes(
        compressed_bytes_per_hour=rates.get("compressed_bytes_written"),
        raw_bytes_per_hour=rates.get("raw_bytes_written"))
    available = shutil.disk_usage(archive_root).free
    if available < required:
        raise SoakStorageGateError("filesystem is below frozen minimum free disk gate")
    output = Path(output_path)
    if output.exists():
        raise SoakStorageGateError("refusing to replace frozen storage-gate receipt")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "accepted_shakedown_run_id": manifest["run_id"],
        "canonical_image_digest": canonical_image_digest,
        "shakedown_summary_sha256": file_sha256(summary_path),
        "compressed_bytes_per_hour": rates["compressed_bytes_written"],
        "raw_bytes_per_hour": rates["raw_bytes_written"],
        "required_free_bytes": required,
        "available_free_bytes_at_freeze": available,
    }
    write_json_atomic(output, receipt)
    return receipt


def freeze_storage_gate_receipt(*, shakedown_summary_path, shakedown_manifest_path,
                                archive_root, canonical_image_digest, output_path):
    """Validate a complete local shakedown and atomically freeze one receipt."""
    manifest = validate_soak_run_manifest(
        shakedown_manifest_path, artifact_root=Path(archive_root).parent,
        verify_artifacts=True)
    return _freeze_storage_gate_receipt(
        shakedown_summary_path=shakedown_summary_path, manifest=manifest,
        archive_root=archive_root, canonical_image_digest=canonical_image_digest,
        output_path=output_path,
    )


def _verified_archive_artifact(*, receipt: dict[str, object], relative_path: str,
                               local_path: Path) -> None:
    artifacts = receipt.get("artifacts")
    if not isinstance(artifacts, list):
        raise SoakStorageGateError("archive receipt artifacts are invalid")
    matches = [item for item in artifacts if isinstance(item, dict)
               and item.get("relative_path") == relative_path]
    if len(matches) != 1:
        raise SoakStorageGateError("archive receipt lacks required storage-gate evidence")
    artifact = matches[0]
    expected_size, expected_sha = artifact.get("byte_count"), artifact.get("sha256")
    if (not isinstance(expected_size, int) or expected_size < 0
            or not isinstance(expected_sha, str) or len(expected_sha) != 64
            or not local_path.is_file() or local_path.stat().st_size != expected_size
            or file_sha256(local_path) != expected_sha):
        raise SoakStorageGateError("restored storage-gate evidence does not match archive receipt")


def freeze_storage_gate_receipt_from_verified_archive(
    *, shakedown_summary_path, shakedown_manifest_path, archive_receipt_path,
    archive_root, canonical_image_digest, output_path,
):
    """Freeze a gate from receipt-verified, run-scoped restored evidence.

    The manifest's artifact descriptors can include historical shared segments.
    Those do not belong in a run-scoped archive.  The local manifest and
    summary are instead bound to the immutable archive receipt before use.
    """
    summary_path, manifest_path = Path(shakedown_summary_path), Path(shakedown_manifest_path)
    try:
        receipt = json.loads(Path(archive_receipt_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SoakStorageGateError("archive receipt is unreadable") from exc
    if not isinstance(receipt, dict) or receipt.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise SoakStorageGateError("archive receipt schema is invalid")
    manifest = validate_soak_run_manifest(manifest_path, verify_artifacts=False)
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or receipt.get("run_id") != run_id:
        raise SoakStorageGateError("archive receipt run identity does not match manifest")
    _verified_archive_artifact(
        receipt=receipt, relative_path=f"raw/manifests/{run_id}.json",
        local_path=manifest_path,
    )
    _verified_archive_artifact(
        receipt=receipt, relative_path=f"telemetry/{run_id}/summary.json",
        local_path=summary_path,
    )
    return _freeze_storage_gate_receipt(
        shakedown_summary_path=summary_path, manifest=manifest,
        archive_root=archive_root, canonical_image_digest=canonical_image_digest,
        output_path=output_path,
    )


def validate_storage_gate_receipt(*, receipt_path, archive_root, canonical_image_digest):
    """Fail closed unless the immutable receipt matches this 24-hour image."""
    receipt = _object(receipt_path)
    required_fields = {
        "schema_version", "accepted_shakedown_run_id", "canonical_image_digest",
        "shakedown_summary_sha256", "compressed_bytes_per_hour",
        "raw_bytes_per_hour", "required_free_bytes", "available_free_bytes_at_freeze",
    }
    if set(receipt) != required_fields or receipt["schema_version"] != SCHEMA_VERSION:
        raise SoakStorageGateError("invalid storage-gate receipt")
    if receipt["canonical_image_digest"] != canonical_image_digest:
        raise SoakStorageGateError("storage-gate receipt image mismatch")
    expected = required_free_bytes(
        compressed_bytes_per_hour=receipt["compressed_bytes_per_hour"],
        raw_bytes_per_hour=receipt["raw_bytes_per_hour"])
    if receipt["required_free_bytes"] != expected:
        raise SoakStorageGateError("storage-gate receipt formula mismatch")
    available = shutil.disk_usage(archive_root).free
    if available < expected:
        raise SoakStorageGateError("filesystem is below frozen minimum free disk gate")
    return receipt


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Freeze an empirical Candidate-E soak storage gate")
    parser.add_argument("--shakedown-summary", required=True)
    parser.add_argument("--shakedown-manifest", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--canonical-image-digest", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--archive-receipt")
    args = parser.parse_args(argv)
    if args.archive_receipt:
        freeze_storage_gate_receipt_from_verified_archive(
            shakedown_summary_path=args.shakedown_summary,
            shakedown_manifest_path=args.shakedown_manifest,
            archive_receipt_path=args.archive_receipt,
            archive_root=args.archive_root,
            canonical_image_digest=args.canonical_image_digest,
            output_path=args.output)
    else:
        freeze_storage_gate_receipt(
            shakedown_summary_path=args.shakedown_summary,
            shakedown_manifest_path=args.shakedown_manifest,
            archive_root=args.archive_root,
            canonical_image_digest=args.canonical_image_digest,
            output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
