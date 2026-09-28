"""Run the one-time Checkpoint-20 Candidate-E H1 development evaluation.

DO NOT run this command until the Checkpoint-20A H1 evaluation freeze has been
committed/pushed and the repository has been freshly fetched, verified clean,
and verified synchronized.

The command is read-only with respect to trading. It performs public historical
market GETs only for the exact pre-frozen H1 allow-list, persists raw responses
first, fits exactly the two predeclared Candidate-E variants, and applies the
frozen H1 gates. H2/H3 identities remain hard denied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from src.config import (
    DEFAULT_MANIFEST_ROOT,
    DEFAULT_RAW_LOG_ROOT,
    DEFAULT_RUNTIME_EVENT_ROOT,
    KALSHI_PUBLIC_BASE_URL,
)
from src.kxbtcd_candidate_e_h1_evaluation import (
    CP20_COLLECTOR_NAME,
    DERIVED_ROOT,
    FROZEN_COHORT_MAP_FINGERPRINT,
    FROZEN_ROW_UNIVERSE_FINGERPRINT,
    KxbtcdCandidateEH1EvaluationError,
    append_h1_outcome_journal,
    collect_h1_outcomes,
    evaluate_h1,
    h1_preflight,
    h1_result_fingerprint,
    initialize_h1_outcome_journal,
    recover_h1_outcomes_from_manifest,
    update_h1_attempt_receipt,
    write_h1_evaluation_outputs,
)
from src.public_census_http import PublicCensusHttpClient, PublicCensusHttpError
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume-from-manifest",
        type=Path,
        default=None,
        help=(
            "Resume the same permanently exposed H1 attempt after interruption. "
            "Already journaled outcomes are validated and not re-requested."
        ),
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()

    # CRITICAL ORDERING: all Git/fingerprint/allow-list/deny-list checks and the
    # conservative H1 exposure receipt happen before a network-capable client is
    # constructed.
    preflight = h1_preflight(resume_manifest=args.resume_from_manifest)
    freeze = preflight.freeze
    attempt = json.loads(preflight.attempt_path.read_text(encoding="utf-8"))

    resume_manifest = args.resume_from_manifest.resolve() if args.resume_from_manifest else None
    recovered_outcomes = ()
    if resume_manifest is not None:
        recovered_outcomes = recover_h1_outcomes_from_manifest(
            freeze=freeze,
            universe=preflight.universe,
            repository_root=preflight.repository_root,
            manifest_path=resume_manifest,
        )

    # Network-capable object creation begins only after h1_preflight PASS.
    client = PublicCensusHttpClient(
        base_url=KALSHI_PUBLIC_BASE_URL,
        source_name="kalshi_public_rest",
        raw_root=DEFAULT_RAW_LOG_ROOT,
        timeout_seconds=15.0,
    )
    source_sessions = [
        {
            "source": client.raw_recorder.source_name,
            "session_id": client.raw_recorder.session_id,
        }
    ]
    h1_identity = freeze["stage_identities"]["H1"]
    manifest = CollectionRunManifest(
        collector_name=CP20_COLLECTOR_NAME,
        arguments={
            "h1_evaluation_fingerprint": freeze["h1_evaluation_fingerprint"],
            "cohort_map_fingerprint": FROZEN_COHORT_MAP_FINGERPRINT,
            "row_universe_fingerprint": FROZEN_ROW_UNIVERSE_FINGERPRINT,
            "partition_scope": "H1_only",
            "H1_event_count": h1_identity["event_count"],
            "H1_row_count": h1_identity["row_count"],
            "H1_market_requests": h1_identity["market_count"],
            "candidate_menu": freeze["candidate_menu"],
            "rolling_origin_fold_count": 5,
            "resume_source_manifest": str(resume_manifest) if resume_manifest else "",
            "resume_recovered_outcomes": len(recovered_outcomes),
            "H2_outcomes_opened": False,
            "H3_outcomes_opened": False,
            "authentication_used": False,
            "posthoc_repair_performed": False,
            "feature_change_performed": False,
            "execution_enabled": False,
        },
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=source_sessions,
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name=CP20_COLLECTOR_NAME,
        started_at_utc=manifest.started_at_utc,
    )
    client.attach_runtime_event_logger(runtime)

    derived_dir = (
        DERIVED_ROOT
        / manifest.started_at_utc[0:4]
        / manifest.started_at_utc[5:7]
        / manifest.started_at_utc[8:10]
    )
    journal_path = derived_dir / f"{manifest.run_id}_candidate_e_h1_outcome_journal.csv"
    initialize_h1_outcome_journal(journal_path)
    for row in recovered_outcomes:
        append_h1_outcome_journal(journal_path, row)

    derived_paths: list[Path] = [journal_path]
    outcomes = None
    evaluation = None
    try:
        update_h1_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="h1_exposure_in_progress",
            manifest_path=manifest.manifest_path,
        )
        runtime.emit(
            "collector.started",
            severity="info",
            message="Checkpoint-20 Candidate-E H1 development evaluation started",
            context={
                "H1_permanently_development_exposed": True,
                "H1_event_count": h1_identity["event_count"],
                "H1_row_count": h1_identity["row_count"],
                "H1_market_requests": h1_identity["market_count"],
                "H2_outcomes_opened": False,
                "H3_outcomes_opened": False,
                "recovered_outcomes": len(recovered_outcomes),
                "orders_placed": 0,
            },
        )

        outcomes = collect_h1_outcomes(
            client,
            freeze=freeze,
            universe=preflight.universe,
            existing_outcomes=recovered_outcomes,
            on_outcome=lambda row: append_h1_outcome_journal(journal_path, row),
        )
        evaluation = evaluate_h1(
            universe=preflight.universe,
            freeze=freeze,
            outcomes=outcomes,
        )
        derived_paths = list(
            write_h1_evaluation_outputs(
                derived_dir,
                run_id=manifest.run_id,
                outcomes=outcomes,
                evaluation=evaluation,
                outcome_journal_path=journal_path,
            )
        )
        result_fp = h1_result_fingerprint(evaluation.summary)
        runtime.emit(
            "collector.completed",
            severity="info",
            message="Checkpoint-20 Candidate-E H1 evaluation completed",
            context={
                "selection": evaluation.summary["selection"],
                "distance_raw_gate_passed": evaluation.summary["distance_raw_gate_passed"],
                "momentum_raw_gate_passed": evaluation.summary["momentum_raw_gate_passed"],
                "momentum_nested_complexity_gate_passed": evaluation.summary[
                    "momentum_nested_complexity_gate_passed"
                ],
                "H2_outcomes_opened": False,
                "H3_outcomes_opened": False,
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=client.raw_recorder.written_paths,
            derived_csv_files=derived_paths,
            runtime_event_files=runtime.written_paths,
            result={
                **evaluation.summary,
                "h1_result_fingerprint": result_fp,
                "new_http_requests": len(outcomes) - len(recovered_outcomes),
                "resume_recovered_outcomes": len(recovered_outcomes),
                "resume_source_manifest": str(resume_manifest) if resume_manifest else "",
                "resume_source_manifest_sha256": _sha256(resume_manifest) if resume_manifest else "",
                "authentication_used": False,
                "posthoc_repair_performed": False,
                "feature_change_performed": False,
                "execution_enabled": False,
                "orders_placed": 0,
            },
        )
        update_h1_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="h1_evaluation_completed",
            manifest_path=manifest.manifest_path,
            result_fingerprint=result_fp,
        )
    except BaseException as exc:
        event_failure: RuntimeEventWriteError | None = None
        if not isinstance(exc, RuntimeEventWriteError):
            try:
                runtime.emit(
                    "collector.failed",
                    severity="critical",
                    message="Checkpoint-20 Candidate-E H1 evaluation interrupted",
                    context={
                        "H1_permanently_development_exposed": True,
                        "H2_outcomes_opened": False,
                        "H3_outcomes_opened": False,
                        "outcome_journal": str(journal_path),
                        "orders_placed": 0,
                    },
                    error={"type": type(exc).__name__, "message": str(exc)},
                )
            except RuntimeEventWriteError as log_exc:
                event_failure = log_exc
        failure = event_failure or exc
        try:
            manifest.fail(
                failure,
                raw_files=client.raw_recorder.written_paths,
                derived_csv_files=[path for path in derived_paths if path.exists()],
                runtime_event_files=runtime.written_paths,
                result={
                    "h1_evaluation_fingerprint": freeze["h1_evaluation_fingerprint"],
                    "H1_permanently_development_exposed": True,
                    "H2_outcomes_opened": False,
                    "H3_outcomes_opened": False,
                    "outcome_journal": str(journal_path),
                    "resume_recovered_outcomes": len(recovered_outcomes),
                    "posthoc_repair_performed": False,
                    "feature_change_performed": False,
                    "execution_enabled": False,
                    "orders_placed": 0,
                    "original_failure_type": type(exc).__name__,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from failure
        try:
            update_h1_attempt_receipt(
                preflight.attempt_path,
                attempt,
                status="h1_exposure_interrupted",
                manifest_path=manifest.manifest_path,
            )
        except OSError:
            pass
        if event_failure is not None:
            raise event_failure from exc
        raise

    assert outcomes is not None
    assert evaluation is not None
    print("Checkpoint-20 Candidate-E H1 evaluation: COMPLETE")
    print(f"H1 evaluation fingerprint: {freeze['h1_evaluation_fingerprint']}")
    print(f"H1 events: {evaluation.summary['H1_event_count']}")
    print(f"H1 rows: {evaluation.summary['H1_row_count']}")
    print(f"OOF scored events: {evaluation.summary['OOF_scored_event_count']}")
    print(f"Distance raw gate: {'PASS' if evaluation.summary['distance_raw_gate_passed'] else 'FAIL'}")
    print(f"Momentum raw gate: {'PASS' if evaluation.summary['momentum_raw_gate_passed'] else 'FAIL'}")
    print(
        "Momentum nested complexity gate: "
        + ("PASS" if evaluation.summary["momentum_nested_complexity_gate_passed"] else "FAIL")
    )
    print(f"Selection: {evaluation.summary['selection']}")
    print("H2 outcomes opened: no")
    print("H3 outcomes opened: no")
    print("Post-hoc repair / feature changes: no / no")
    print("Orders placed: 0")
    print(f"Derived directory: {derived_dir}")
    print(f"Manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        KxbtcdCandidateEH1EvaluationError,
        PublicCensusHttpError,
        RunManifestError,
        RuntimeEventWriteError,
        OSError,
        ValueError,
    ) as exc:
        raise SystemExit(f"Candidate-E Checkpoint-20 H1 error: {exc}") from exc
