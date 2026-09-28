"""Observed read-only soak lifecycle assembly.

Transport construction stays outside this module.  This boundary accepts only
already-built supervisor callables and routes them through the required
manifest/observability lifecycle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .kxbtcd_candidate_e_soak_manifest import DESIGN_FINGERPRINT
from .kxbtcd_candidate_e_soak_observability import close_verified_runtime_archives
from .kxbtcd_candidate_e_soak_orchestrator import run_packaged_observed_soak


class SoakRuntimeAssemblyError(RuntimeError):
    pass


def run_assembled_read_only_soak(*, core, producers, observability,
                                 run_coinbase_supervisor: Callable, run_kalshi_supervisor: Callable,
                                 sample_readiness: Callable, manifest_path, run_id, git_head,
                                 docker_image_digest, host_boot_id,
                                 requested_active_duration_seconds, initial_filesystem_free_bytes,
                                 utc_now_text: Callable, credential_presence=None):
    """Run supervisors only through the frozen observed-manifest lifecycle."""
    if not str(run_id).strip() or not str(host_boot_id).strip():
        raise SoakRuntimeAssemblyError("run identity is required")
    return run_packaged_observed_soak(
        core=core, producers=producers, observability=observability,
        close_runtime_artifacts=lambda: close_verified_runtime_archives(core),
        run_coinbase_supervisor=run_coinbase_supervisor,
        run_kalshi_supervisor=run_kalshi_supervisor,
        manifest_path=manifest_path, run_id=run_id, run_role="read_only_soak",
        design_fingerprint=DESIGN_FINGERPRINT, git_head=git_head,
        docker_image_digest=docker_image_digest, host_boot_id=host_boot_id,
        expected_boot_id=host_boot_id,
        requested_active_duration_seconds=requested_active_duration_seconds,
        initial_filesystem_free_bytes=initial_filesystem_free_bytes,
        sample_readiness=sample_readiness, utc_now_text=utc_now_text,
        credential_presence=credential_presence,
        # Manifests and raw segments live under ``archive_root`` while
        # run-owned telemetry is a sibling directory. Hash both beneath the
        # durable soak-volume root.
        artifact_root=Path(manifest_path).parent.parent.parent,
    )
