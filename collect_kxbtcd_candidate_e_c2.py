"""One-time Candidate-E C2 historical confirmation runner.

DO NOT run this command until Checkpoint 21F-A has been safely closed,
committed, pushed, and the repository is freshly verified clean/synchronized.

This command opens only the exact frozen C2 outcome allow-list. It performs no
fitting, tuning, candidate selection, feature change, C3 materialization,
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
from src.kxbtcd_candidate_e_c2_evaluation import (
    CP21F_B_COLLECTOR_NAME,
    CandidateEC2EvaluationError,
    DERIVED_ROOT,
    append_c2_outcome_journal,
    c2_preflight,
    c2_result_fingerprint,
    collect_c2_outcomes,
    evaluate_c2,
    initialize_c2_outcome_journal,
    recover_c2_outcomes_from_manifest,
    update_c2_attempt_receipt,
    write_c2_evaluation_outputs,
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
            "Resume the same permanently exposed C2 attempt after interruption. "
            "Already journaled outcomes are validated and not re-requested."
        ),
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()

    # CRITICAL ORDERING: clean/sync/fingerprint/allow-list/hard-deny checks and
    # the conservative C2 exposure receipt happen before any HTTP client exists.
    preflight = c2_preflight(
        resume_manifest=args.resume_from_manifest
    )
    implementation_freeze = (
        preflight.implementation_freeze
    )
    validation_freeze = (
        preflight.validation_freeze
    )
    attempt = json.loads(
        preflight.attempt_path.read_text(
            encoding="utf-8"
        )
    )

    resume_manifest = (
        args.resume_from_manifest.resolve()
        if args.resume_from_manifest is not None
        else None
    )
    recovered_outcomes = ()
    if resume_manifest is not None:
        recovered_outcomes = (
            recover_c2_outcomes_from_manifest(
                implementation_freeze=implementation_freeze,
                validation_freeze=validation_freeze,
                prior_events=preflight.prior_events,
                prior_markets=preflight.prior_markets,
                repository_root=preflight.repository_root,
                manifest_path=resume_manifest,
            )
        )

    # Network-capable construction begins only after c2_preflight PASS and
    # after the permanent C2 exposure receipt has been written.
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

    identity = implementation_freeze["C2_identity"]
    manifest = CollectionRunManifest(
        collector_name=CP21F_B_COLLECTOR_NAME,
        arguments={
            "c2_validation_fingerprint": validation_freeze[
                "c2_validation_fingerprint"
            ],
            "c2_implementation_fingerprint": implementation_freeze[
                "c2_implementation_fingerprint"
            ],
            "champion_r1_fingerprint": preflight.champion_r1[
                "champion_r1_fingerprint"
            ],
            "partition_scope": "C2_only",
            "C2_event_count": identity[
                "event_count"
            ],
            "C2_row_count": identity[
                "row_count"
            ],
            "C2_market_requests": identity[
                "market_count"
            ],
            "resume_source_manifest": (
                str(resume_manifest)
                if resume_manifest
                else ""
            ),
            "resume_recovered_outcomes": len(
                recovered_outcomes
            ),
            "C2_permanently_exposed": True,
            "authentication_used": False,
            "model_parameters_fitted_on_C2": False,
            "candidate_selection_on_C2_performed": False,
            "feature_change_performed": False,
            "hyperparameter_search_performed": False,
            "C3_materialized_or_opened": False,
            "execution_enabled": False,
        },
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=source_sessions,
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name=CP21F_B_COLLECTOR_NAME,
        started_at_utc=manifest.started_at_utc,
    )
    client.attach_runtime_event_logger(
        runtime
    )

    derived_dir = (
        DERIVED_ROOT
        / manifest.started_at_utc[0:4]
        / manifest.started_at_utc[5:7]
        / manifest.started_at_utc[8:10]
    )
    journal_path = (
        derived_dir
        / (
            f"{manifest.run_id}_"
            "candidate_e_c2_outcome_journal.csv"
        )
    )
    initialize_c2_outcome_journal(
        journal_path
    )
    for row in recovered_outcomes:
        append_c2_outcome_journal(
            journal_path,
            row,
        )

    derived_paths: list[Path] = [
        journal_path
    ]
    outcomes = None
    evaluation = None

    try:
        update_c2_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="c2_exposure_in_progress",
            manifest_path=manifest.manifest_path,
        )
        runtime.emit(
            "collector.started",
            severity="info",
            message=(
                "Candidate-E C2 historical "
                "confirmation started"
            ),
            context={
                "C2_permanently_exposed": True,
                "C2_event_count": identity[
                    "event_count"
                ],
                "C2_row_count": identity[
                    "row_count"
                ],
                "C2_market_requests": identity[
                    "market_count"
                ],
                "model_parameters_fitted_on_C2": False,
                "C3_materialized_or_opened": False,
                "recovered_outcomes": len(
                    recovered_outcomes
                ),
                "orders_placed": 0,
            },
        )

        outcomes = collect_c2_outcomes(
            client,
            implementation_freeze=implementation_freeze,
            validation_freeze=validation_freeze,
            prior_events=preflight.prior_events,
            prior_markets=preflight.prior_markets,
            existing_outcomes=recovered_outcomes,
            on_outcome=lambda row: (
                append_c2_outcome_journal(
                    journal_path,
                    row,
                )
            ),
        )
        evaluation = evaluate_c2(
            outcomes=outcomes,
            implementation_freeze=implementation_freeze,
            validation_freeze=validation_freeze,
            champion_r1=preflight.champion_r1,
            frozen_data=preflight.frozen_data,
            prior_events=preflight.prior_events,
            prior_markets=preflight.prior_markets,
        )

        derived_paths = list(
            write_c2_evaluation_outputs(
                derived_dir,
                run_id=manifest.run_id,
                outcomes=outcomes,
                evaluation=evaluation,
                outcome_journal_path=journal_path,
            )
        )
        result_fp = c2_result_fingerprint(
            evaluation.summary
        )

        runtime.emit(
            "collector.completed",
            severity="info",
            message=(
                "Candidate-E C2 historical "
                "confirmation completed"
            ),
            context={
                "C2_validation_passed": evaluation.summary[
                    "C2_validation_passed"
                ],
                "block_log_loss_win_count": evaluation.summary[
                    "block_log_loss_win_count"
                ],
                "latest_block_B4_win": evaluation.summary[
                    "latest_block_B4_win"
                ],
                "model_parameters_fitted_on_C2": False,
                "C3_materialized_or_opened": False,
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=client.raw_recorder.written_paths,
            derived_csv_files=derived_paths,
            runtime_event_files=runtime.written_paths,
            result={
                **evaluation.summary,
                "c2_result_fingerprint": result_fp,
                "new_http_requests": (
                    len(outcomes)
                    - len(recovered_outcomes)
                ),
                "resume_recovered_outcomes": len(
                    recovered_outcomes
                ),
                "resume_source_manifest": (
                    str(resume_manifest)
                    if resume_manifest
                    else ""
                ),
                "resume_source_manifest_sha256": (
                    _sha256(resume_manifest)
                    if resume_manifest
                    else ""
                ),
                "authentication_used": False,
                "posthoc_repair_performed": False,
                "model_parameters_fitted_on_C2": False,
                "candidate_selection_on_C2_performed": False,
                "feature_change_performed": False,
                "hyperparameter_search_performed": False,
                "C3_materialized_or_opened": False,
                "execution_enabled": False,
                "orders_placed": 0,
            },
        )
        update_c2_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="c2_evaluation_completed",
            manifest_path=manifest.manifest_path,
            result_fingerprint=result_fp,
        )
    except BaseException as exc:
        event_failure: (
            RuntimeEventWriteError | None
        ) = None
        if not isinstance(
            exc,
            RuntimeEventWriteError,
        ):
            try:
                runtime.emit(
                    "collector.failed",
                    severity="critical",
                    message=(
                        "Candidate-E C2 historical "
                        "confirmation interrupted"
                    ),
                    context={
                        "C2_permanently_exposed": True,
                        "outcome_journal": str(
                            journal_path
                        ),
                        "model_parameters_fitted_on_C2": False,
                        "C3_materialized_or_opened": False,
                        "orders_placed": 0,
                    },
                    error={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
            except RuntimeEventWriteError as log_exc:
                event_failure = log_exc

        failure = event_failure or exc
        try:
            manifest.fail(
                failure,
                raw_files=client.raw_recorder.written_paths,
                derived_csv_files=[
                    path
                    for path in derived_paths
                    if path.exists()
                ],
                runtime_event_files=runtime.written_paths,
                result={
                    "c2_validation_fingerprint": validation_freeze[
                        "c2_validation_fingerprint"
                    ],
                    "c2_implementation_fingerprint": implementation_freeze[
                        "c2_implementation_fingerprint"
                    ],
                    "C2_permanently_exposed": True,
                    "outcome_journal": str(
                        journal_path
                    ),
                    "resume_recovered_outcomes": len(
                        recovered_outcomes
                    ),
                    "model_parameters_fitted_on_C2": False,
                    "candidate_selection_on_C2_performed": False,
                    "feature_change_performed": False,
                    "hyperparameter_search_performed": False,
                    "C3_materialized_or_opened": False,
                    "execution_enabled": False,
                    "orders_placed": 0,
                    "original_failure_type": type(
                        exc
                    ).__name__,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from failure

        try:
            update_c2_attempt_receipt(
                preflight.attempt_path,
                attempt,
                status="c2_exposure_interrupted",
                manifest_path=manifest.manifest_path,
            )
        except OSError:
            pass

        if event_failure is not None:
            raise event_failure from exc
        raise

    assert outcomes is not None
    assert evaluation is not None

    print(
        "Candidate-E C2 historical confirmation: COMPLETE"
    )
    print(
        "C2 implementation fingerprint: "
        f"{implementation_freeze['c2_implementation_fingerprint']}"
    )
    print(
        "C2 validation fingerprint: "
        f"{validation_freeze['c2_validation_fingerprint']}"
    )
    print(
        "Champion-R1 fingerprint: "
        f"{preflight.champion_r1['champion_r1_fingerprint']}"
    )
    print(
        "Frozen beta_distance: "
        f"{evaluation.summary['beta_distance']}"
    )
    print(
        f"C2 events: "
        f"{evaluation.summary['C2_event_count']}"
    )
    print(
        f"C2 rows: "
        f"{evaluation.summary['C2_row_count']}"
    )
    print(
        "C2 market labels: "
        f"{evaluation.summary['C2_market_count']}"
    )
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
        "C2 block log-loss wins: "
        f"{evaluation.summary['block_log_loss_win_count']} / 5"
    )
    print(
        "Newest B4 win: "
        + (
            "yes"
            if evaluation.summary[
                "latest_block_B4_win"
            ]
            else "no"
        )
    )
    print(
        "C2 validation gate: "
        + (
            "PASS"
            if evaluation.summary[
                "C2_validation_passed"
            ]
            else "FAIL"
        )
    )
    print(
        "C2 result fingerprint: "
        f"{c2_result_fingerprint(evaluation.summary)}"
    )
    print(
        "Model fit / tuning on C2: no / no"
    )
    print(
        "C3 materialized or opened: no"
    )
    print("Orders placed: 0")
    print(
        f"Derived directory: {derived_dir}"
    )
    print(
        f"Manifest: {manifest.manifest_path}"
    )


if __name__ == "__main__":
    try:
        main()
    except (
        CandidateEC2EvaluationError,
        PublicCensusHttpError,
        RunManifestError,
        RuntimeEventWriteError,
        OSError,
        ValueError,
    ) as exc:
        raise SystemExit(
            f"Candidate-E C2 evaluation error: {exc}"
        ) from exc
