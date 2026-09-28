"""One-time Candidate-E H2 historical validation runner.

DO NOT run this command until Checkpoint 20D has been safely closed, committed,
pushed, and the repository is freshly verified clean/synchronized.

This command opens only the exact frozen H2 outcome allow-list. H3 identities are
hard denied. It performs no fitting, tuning, candidate selection, feature change,
paper execution, demo execution, or real-money execution.
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
from src.kxbtcd_candidate_e_h2_evaluation import (
    CP20E_COLLECTOR_NAME,
    CandidateEH2EvaluationError,
    DERIVED_ROOT,
    append_h2_outcome_journal,
    collect_h2_outcomes,
    evaluate_h2,
    h2_preflight,
    h2_result_fingerprint,
    initialize_h2_outcome_journal,
    recover_h2_outcomes_from_manifest,
    update_h2_attempt_receipt,
    write_h2_evaluation_outputs,
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
            "Resume the same permanently exposed H2 attempt after interruption. "
            "Already journaled outcomes are validated and not re-requested."
        ),
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()

    # CRITICAL ORDERING: clean/sync/fingerprint/allow-list/H3-deny checks and the
    # conservative H2 exposure receipt happen before any HTTP client is created.
    preflight = h2_preflight(resume_manifest=args.resume_from_manifest)
    implementation_freeze = preflight.implementation_freeze
    validation_freeze = preflight.validation_freeze
    attempt = json.loads(preflight.attempt_path.read_text(encoding="utf-8"))

    resume_manifest = (
        args.resume_from_manifest.resolve()
        if args.resume_from_manifest is not None
        else None
    )
    recovered_outcomes = ()
    if resume_manifest is not None:
        recovered_outcomes = recover_h2_outcomes_from_manifest(
            implementation_freeze=implementation_freeze,
            validation_freeze=validation_freeze,
            universe=preflight.universe,
            repository_root=preflight.repository_root,
            manifest_path=resume_manifest,
        )

    # Network-capable object construction begins only after h2_preflight PASS.
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
    h2_identity = implementation_freeze["H2_identity"]
    manifest = CollectionRunManifest(
        collector_name=CP20E_COLLECTOR_NAME,
        arguments={
            "h2_validation_fingerprint": validation_freeze[
                "h2_validation_fingerprint"
            ],
            "h2_implementation_fingerprint": implementation_freeze[
                "h2_implementation_fingerprint"
            ],
            "final_h1_model_fingerprint": preflight.final_model[
                "final_model_fingerprint"
            ],
            "partition_scope": "H2_only",
            "H2_event_count": h2_identity["event_count"],
            "H2_row_count": h2_identity["row_count"],
            "H2_market_requests": h2_identity["market_count"],
            "resume_source_manifest": (
                str(resume_manifest) if resume_manifest else ""
            ),
            "resume_recovered_outcomes": len(recovered_outcomes),
            "H2_permanently_exposed": True,
            "H3_outcomes_opened": False,
            "authentication_used": False,
            "model_parameters_fitted_on_H2": False,
            "candidate_selection_on_H2_performed": False,
            "feature_change_performed": False,
            "hyperparameter_search_performed": False,
            "execution_enabled": False,
        },
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=source_sessions,
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name=CP20E_COLLECTOR_NAME,
        started_at_utc=manifest.started_at_utc,
    )
    client.attach_runtime_event_logger(runtime)

    derived_dir = (
        DERIVED_ROOT
        / manifest.started_at_utc[0:4]
        / manifest.started_at_utc[5:7]
        / manifest.started_at_utc[8:10]
    )
    journal_path = (
        derived_dir
        / f"{manifest.run_id}_candidate_e_h2_outcome_journal.csv"
    )
    initialize_h2_outcome_journal(journal_path)
    for row in recovered_outcomes:
        append_h2_outcome_journal(journal_path, row)

    derived_paths: list[Path] = [journal_path]
    outcomes = None
    evaluation = None

    try:
        update_h2_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="h2_exposure_in_progress",
            manifest_path=manifest.manifest_path,
        )
        runtime.emit(
            "collector.started",
            severity="info",
            message="Candidate-E H2 historical validation started",
            context={
                "H2_permanently_exposed": True,
                "H2_event_count": h2_identity["event_count"],
                "H2_row_count": h2_identity["row_count"],
                "H2_market_requests": h2_identity["market_count"],
                "H3_outcomes_opened": False,
                "model_parameters_fitted_on_H2": False,
                "recovered_outcomes": len(recovered_outcomes),
                "orders_placed": 0,
            },
        )

        outcomes = collect_h2_outcomes(
            client,
            implementation_freeze=implementation_freeze,
            validation_freeze=validation_freeze,
            universe=preflight.universe,
            existing_outcomes=recovered_outcomes,
            on_outcome=lambda row: append_h2_outcome_journal(journal_path, row),
        )
        evaluation = evaluate_h2(
            outcomes=outcomes,
            implementation_freeze=implementation_freeze,
            validation_freeze=validation_freeze,
            final_model=preflight.final_model,
            universe=preflight.universe,
        )
        derived_paths = list(
            write_h2_evaluation_outputs(
                derived_dir,
                run_id=manifest.run_id,
                outcomes=outcomes,
                evaluation=evaluation,
                outcome_journal_path=journal_path,
            )
        )
        result_fp = h2_result_fingerprint(evaluation.summary)

        runtime.emit(
            "collector.completed",
            severity="info",
            message="Candidate-E H2 historical validation completed",
            context={
                "H2_validation_passed": evaluation.summary[
                    "H2_validation_passed"
                ],
                "block_log_loss_win_count": evaluation.summary[
                    "block_log_loss_win_count"
                ],
                "latest_block_B4_win": evaluation.summary[
                    "latest_block_B4_win"
                ],
                "H3_outcomes_opened": False,
                "model_parameters_fitted_on_H2": False,
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=client.raw_recorder.written_paths,
            derived_csv_files=derived_paths,
            runtime_event_files=runtime.written_paths,
            result={
                **evaluation.summary,
                "h2_result_fingerprint": result_fp,
                "new_http_requests": len(outcomes) - len(recovered_outcomes),
                "resume_recovered_outcomes": len(recovered_outcomes),
                "resume_source_manifest": (
                    str(resume_manifest) if resume_manifest else ""
                ),
                "resume_source_manifest_sha256": (
                    _sha256(resume_manifest) if resume_manifest else ""
                ),
                "authentication_used": False,
                "posthoc_repair_performed": False,
                "model_parameters_fitted_on_H2": False,
                "candidate_selection_on_H2_performed": False,
                "feature_change_performed": False,
                "hyperparameter_search_performed": False,
                "execution_enabled": False,
                "orders_placed": 0,
            },
        )
        update_h2_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="h2_evaluation_completed",
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
                    message="Candidate-E H2 historical validation interrupted",
                    context={
                        "H2_permanently_exposed": True,
                        "H3_outcomes_opened": False,
                        "outcome_journal": str(journal_path),
                        "model_parameters_fitted_on_H2": False,
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
                derived_csv_files=[
                    path for path in derived_paths if path.exists()
                ],
                runtime_event_files=runtime.written_paths,
                result={
                    "h2_validation_fingerprint": validation_freeze[
                        "h2_validation_fingerprint"
                    ],
                    "h2_implementation_fingerprint": implementation_freeze[
                        "h2_implementation_fingerprint"
                    ],
                    "H2_permanently_exposed": True,
                    "H3_outcomes_opened": False,
                    "outcome_journal": str(journal_path),
                    "resume_recovered_outcomes": len(recovered_outcomes),
                    "model_parameters_fitted_on_H2": False,
                    "candidate_selection_on_H2_performed": False,
                    "feature_change_performed": False,
                    "hyperparameter_search_performed": False,
                    "execution_enabled": False,
                    "orders_placed": 0,
                    "original_failure_type": type(exc).__name__,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from failure

        try:
            update_h2_attempt_receipt(
                preflight.attempt_path,
                attempt,
                status="h2_exposure_interrupted",
                manifest_path=manifest.manifest_path,
            )
        except OSError:
            pass

        if event_failure is not None:
            raise event_failure from exc
        raise

    assert outcomes is not None
    assert evaluation is not None
    print("Candidate-E H2 historical validation: COMPLETE")
    print(
        "H2 implementation fingerprint: "
        f"{implementation_freeze['h2_implementation_fingerprint']}"
    )
    print(
        "H2 validation fingerprint: "
        f"{validation_freeze['h2_validation_fingerprint']}"
    )
    print(
        "Final H1 model fingerprint: "
        f"{preflight.final_model['final_model_fingerprint']}"
    )
    print(f"Frozen beta_distance: {evaluation.summary['beta_distance']}")
    print(f"H2 events: {evaluation.summary['H2_event_count']}")
    print(f"H2 rows: {evaluation.summary['H2_row_count']}")
    print(
        "Raw event-equal log loss: "
        f"{evaluation.summary['raw_event_equal_log_loss']}"
    )
    print(
        "Distance event-equal log loss: "
        f"{evaluation.summary['candidate_event_equal_log_loss']}"
    )
    print(
        "Raw-minus-Distance log loss: "
        f"{evaluation.summary['raw_minus_candidate_log_loss']}"
    )
    print(
        "Raw event-equal Brier: "
        f"{evaluation.summary['raw_event_equal_brier']}"
    )
    print(
        "Distance event-equal Brier: "
        f"{evaluation.summary['candidate_event_equal_brier']}"
    )
    print(
        "H2 block log-loss wins: "
        f"{evaluation.summary['block_log_loss_win_count']} / 5"
    )
    print(
        "Newest B4 win: "
        + ("yes" if evaluation.summary["latest_block_B4_win"] else "no")
    )
    print(
        "H2 validation gate: "
        + ("PASS" if evaluation.summary["H2_validation_passed"] else "FAIL")
    )
    print(f"H2 result fingerprint: {h2_result_fingerprint(evaluation.summary)}")
    print("H3 outcomes opened: no")
    print("Model fit / tuning on H2: no / no")
    print("Orders placed: 0")
    print(f"Derived directory: {derived_dir}")
    print(f"Manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        CandidateEH2EvaluationError,
        PublicCensusHttpError,
        RunManifestError,
        RuntimeEventWriteError,
        OSError,
        ValueError,
    ) as exc:
        raise SystemExit(f"Candidate-E H2 validation error: {exc}") from exc
