"""Executable argument contract for the observed read-only soak."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

from .kxbtcd_candidate_e_soak_package import build_observed_components
from .kxbtcd_candidate_e_soak_runtime_assembly import run_assembled_read_only_soak


def parse_soak_invocation(argv=None):
    parser = argparse.ArgumentParser(description="Run the observed read-only soak")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--git-head", required=True)
    parser.add_argument("--docker-image-digest", required=True)
    parser.add_argument("--active-seconds", type=int, choices=(3600, 86400), required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--telemetry-root", required=True)
    parser.add_argument("--clock-evidence-path", required=True)
    parser.add_argument("--storage-gate-receipt")
    parser.add_argument("--live-shadow-output")
    parser.add_argument("--live-shadow-settlements-output")
    parser.add_argument("--enable-read-only-live", action="store_true")
    args = parser.parse_args(argv)
    if args.active_seconds == 86400 and not args.storage_gate_receipt:
        parser.error("--storage-gate-receipt is required for 86400 seconds")
    if args.active_seconds == 3600 and args.storage_gate_receipt:
        parser.error("--storage-gate-receipt is only valid for 86400 seconds")
    return args


def dispatch_soak_invocation(*, argv, run_preflight, run_live):
    """Execute preflight by default; pass validated arguments to live assembly."""
    args = parse_soak_invocation(argv)
    if not args.enable_read_only_live:
        return run_preflight(args)
    return run_live(args)


def run_validated_live_assembly(*, args, utc_now_text, run_coinbase_supervisor,
                                 run_kalshi_supervisor, sample_readiness, components=None):
    """Build real package components then enter the mandatory observed lifecycle."""
    if components is None:
        core, producers, observer = build_observed_components(
            runtime_session_id=args.run_id, archive_root=args.archive_root,
            telemetry_root=Path(args.telemetry_root) / args.run_id,
            clock_evidence_path=args.clock_evidence_path,
            utc_now_text=utc_now_text)
    else:
        core, producers, observer = components
    return run_assembled_read_only_soak(
        core=core, producers=producers, observability=observer,
        run_coinbase_supervisor=run_coinbase_supervisor,
        run_kalshi_supervisor=run_kalshi_supervisor, sample_readiness=sample_readiness,
        manifest_path=str(args.archive_root) + "/manifests/" + args.run_id + ".json",
        run_id=args.run_id, git_head=args.git_head,
        docker_image_digest=args.docker_image_digest,
        host_boot_id=producers.sample(__import__("time").monotonic_ns())["linux_boot_id"],
        requested_active_duration_seconds=args.active_seconds,
        initial_filesystem_free_bytes=shutil.disk_usage(args.archive_root).free,
        utc_now_text=utc_now_text)


def run_composed_live_assembly(*, args, utc_now_text, http_session, repo_root,
                               supervisor_factory, readiness_factory):
    """Build all source/readiness dependencies from the one preflighted core."""
    core, producers, observer = build_observed_components(
        runtime_session_id=args.run_id, archive_root=args.archive_root,
        telemetry_root=Path(args.telemetry_root) / args.run_id,
        clock_evidence_path=args.clock_evidence_path,
        utc_now_text=utc_now_text)
    if args.live_shadow_output:
        from .kxbtcd_candidate_e_live_shadow_snapshot_publisher import LiveShadowSnapshotPublisher
        core.live_shadow_snapshot_publisher = LiveShadowSnapshotPublisher(
            run_id=args.run_id, output_path=args.live_shadow_output)
    if getattr(args, "live_shadow_settlements_output", None):
        from .kxbtcd_candidate_e_live_shadow_settlement_feed import LiveShadowSettlementPublisher
        core.live_shadow_settlement_publisher = LiveShadowSettlementPublisher(
            run_id=args.run_id, output_path=args.live_shadow_settlements_output)
    # A prior failed/ungraceful attempt can leave valid raw JSONL without its
    # closed descriptor. Verify and recover that evidence before any new live
    # transport is allowed to open.
    core.recover_archives()
    coinbase, kalshi = supervisor_factory(core=core, http_session=http_session, repo_root=repo_root)
    readiness = readiness_factory(core=core, producers=producers, expected_boot_id=producers.sample(__import__("time").monotonic_ns())["linux_boot_id"])
    return run_validated_live_assembly(args=args, utc_now_text=utc_now_text,
        run_coinbase_supervisor=coinbase, run_kalshi_supervisor=kalshi,
        sample_readiness=readiness, components=(core, producers, observer))


def main(argv=None):
    """Run preflight by default; assemble sources only with explicit consent."""
    args = parse_soak_invocation(argv)
    from datetime import datetime, timezone
    utc_now_text = lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not args.enable_read_only_live:
        core, _, _ = build_observed_components(runtime_session_id=args.run_id,
            archive_root=args.archive_root, telemetry_root=Path(args.telemetry_root) / args.run_id,
            clock_evidence_path=args.clock_evidence_path, utc_now_text=utc_now_text)
        core.close()
        return 0
    if args.active_seconds == 86400:
        from .kxbtcd_candidate_e_soak_storage_gate import validate_storage_gate_receipt
        validate_storage_gate_receipt(receipt_path=args.storage_gate_receipt,
            archive_root=args.archive_root,
            canonical_image_digest=args.docker_image_digest)
    import requests
    from .kxbtcd_candidate_e_soak_live_dependencies import build_read_only_supervisors
    from .kxbtcd_candidate_e_soak_live_readiness import build_live_readiness_sampler
    run_composed_live_assembly(args=args, utc_now_text=utc_now_text,
        http_session=requests.Session(), repo_root=".",
        supervisor_factory=build_read_only_supervisors,
        readiness_factory=build_live_readiness_sampler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
