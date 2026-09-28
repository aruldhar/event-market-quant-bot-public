"""Resume the interrupted Checkpoint-17 terminal test with transport-only repair.

This command is resume-only. It keeps the original Stage-A terminal freeze,
recovers already opened labels from raw archives, fetches only missing frozen
tickers, and uses the unchanged frozen Candidate-C scorer and primary gate.

Do not run until the transport amendment has been frozen, tested, committed,
pushed, and the repository is freshly verified clean/synchronized.
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
from src.kxbtcd_candidate_c_terminal_evaluation import (
    CP17_COLLECTOR_NAME,
    DERIVED_ROOT,
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_FINAL_MODEL_FINGERPRINT,
    FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
    FROZEN_SPLIT_FINGERPRINT,
    KxbtcdCandidateCTerminalEvaluationError,
    append_terminal_outcome_journal,
    collect_locked_test_outcomes,
    initialize_terminal_outcome_journal,
    score_terminal_locked_test,
    terminal_preflight,
    terminal_result_fingerprint,
    update_attempt_receipt,
    write_terminal_evaluation_outputs,
)
from src.kxbtcd_candidate_c_terminal_transport_repair import (
    DEFAULT_TRANSPORT_AMENDMENT_PATH,
    LiveFirstHistoricalFallbackClient,
    TerminalTransportRepairError,
    recover_terminal_outcomes_from_manifest_chain,
    validate_transport_amendment_document,
)
from src.public_census_http import PublicCensusHttpClient, PublicCensusHttpError
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume-from-manifest",
        type=Path,
        required=True,
        help="Exact failed CP17 terminal manifest to resume.",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    args = parse_args()
    resume_manifest = args.resume_from_manifest.resolve()

    # Fail closed against the ORIGINAL Stage-A freeze before any network object.
    preflight = terminal_preflight(resume_manifest=resume_manifest)
    terminal_freeze = preflight.terminal_freeze
    attempt = json.loads(preflight.attempt_path.read_text(encoding="utf-8"))

    amendment_path = (
        preflight.repository_root / DEFAULT_TRANSPORT_AMENDMENT_PATH
    ).resolve()
    amendment = json.loads(amendment_path.read_text(encoding="utf-8"))
    validate_transport_amendment_document(
        amendment,
        repository_root=preflight.repository_root,
        resume_manifest=resume_manifest,
    )

    recovery = recover_terminal_outcomes_from_manifest_chain(
        terminal_freeze=terminal_freeze,
        repository_root=preflight.repository_root,
        manifest_path=resume_manifest,
    )
    recovered_outcomes = recovery.outcomes

    expected_min = int(amendment["persisted_label_count_before_repair"])
    if len(recovered_outcomes) < expected_min:
        raise TerminalTransportRepairError(
            "raw recovery found fewer labels than were persisted before repair: "
            f"{len(recovered_outcomes)} < {expected_min}"
        )

    # Network-capable objects are created only after original preflight,
    # amendment validation, and raw recovery complete successfully.
    base_client = PublicCensusHttpClient(
        base_url=KALSHI_PUBLIC_BASE_URL,
        source_name="kalshi_public_rest",
        raw_root=DEFAULT_RAW_LOG_ROOT,
        timeout_seconds=15.0,
    )
    client = LiveFirstHistoricalFallbackClient(base_client)
    source_sessions = [
        {
            "source": base_client.raw_recorder.source_name,
            "session_id": base_client.raw_recorder.session_id,
        }
    ]

    manifest = CollectionRunManifest(
        collector_name=CP17_COLLECTOR_NAME,
        arguments={
            "preoutcome_run_id": terminal_freeze["frozen_preoutcome_run_id"],
            "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
            "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
            "full_development_freeze_fingerprint": (
                FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT
            ),
            "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
            "terminal_evaluation_fingerprint": terminal_freeze[
                "terminal_evaluation_fingerprint"
            ],
            "transport_amendment_fingerprint": amendment[
                "transport_amendment_fingerprint"
            ],
            "transport_repair_mode": True,
            "transport_strategy": "live_first_historical_fallback_on_404",
            "partition_scope": "locked_test_only",
            "locked_test_event_count": terminal_freeze["locked_test_event_count"],
            "locked_test_row_count": terminal_freeze["locked_test_row_count"],
            "locked_test_market_requests": terminal_freeze[
                "locked_test_market_request_count"
            ],
            "primary_metric": "event_weighted_log_loss",
            "primary_gate": (
                "candidate_c_event_weighted_log_loss_strictly_less_than_"
                "raw_midpoint_event_weighted_log_loss"
            ),
            "tie_rule": "fail",
            "resume_source_manifest": str(resume_manifest),
            "resume_source_manifest_sha256": _sha256(resume_manifest),
            "resume_recovered_outcomes": len(recovered_outcomes),
            "authentication_used": False,
            "model_refit_performed": False,
            "model_retuned": False,
            "model_recalibrated": False,
            "execution_enabled": False,
        },
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=source_sessions,
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name=CP17_COLLECTOR_NAME,
        started_at_utc=manifest.started_at_utc,
    )
    base_client.attach_runtime_event_logger(runtime)

    derived_dir = (
        DERIVED_ROOT
        / manifest.started_at_utc[0:4]
        / manifest.started_at_utc[5:7]
        / manifest.started_at_utc[8:10]
    )
    journal_path = (
        derived_dir
        / f"{manifest.run_id}_kxbtcd_candidate_c_terminal_outcome_journal.csv"
    )
    initialize_terminal_outcome_journal(journal_path)
    for row in recovered_outcomes:
        append_terminal_outcome_journal(journal_path, row)

    derived_paths: list[Path] = [journal_path]
    outcomes = None
    score = None
    try:
        update_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="terminal_exposure_resume_in_progress",
            manifest_path=manifest.manifest_path,
        )
        runtime.emit(
            "collector.started",
            severity="info",
            message=(
                "Checkpoint-17 terminal evaluation resumed under transport-only "
                "amendment"
            ),
            context={
                "locked_test_permanently_exposed": True,
                "transport_amendment_fingerprint": amendment[
                    "transport_amendment_fingerprint"
                ],
                "resume_recovered_outcomes": len(recovered_outcomes),
                "orders_placed": 0,
            },
        )

        # The original frozen collector function and identity validation remain
        # unchanged. Only its market HTTP path is adapted by the wrapper.
        outcomes = collect_locked_test_outcomes(
            client,
            terminal_freeze=terminal_freeze,
            existing_outcomes=recovered_outcomes,
            on_outcome=lambda row: append_terminal_outcome_journal(
                journal_path, row
            ),
        )

        score = score_terminal_locked_test(
            frozen=preflight.frozen,
            terminal_freeze=terminal_freeze,
            final_model=preflight.final_model,
            outcomes=outcomes,
        )
        derived_paths = list(
            write_terminal_evaluation_outputs(
                derived_dir,
                run_id=manifest.run_id,
                outcomes=outcomes,
                score=score,
                outcome_journal_path=journal_path,
            )
        )
        result_fp = terminal_result_fingerprint(score.summary)

        runtime.emit(
            "collector.completed",
            severity="info",
            message=(
                "Checkpoint-17 resumed terminal evaluation completed under "
                "transport-only amendment"
            ),
            context={
                "locked_test_permanently_exposed": True,
                "terminal_gate_passed": score.gate_passed,
                "transport_amendment_fingerprint": amendment[
                    "transport_amendment_fingerprint"
                ],
                "live_market_requests": client.live_requests,
                "historical_fallback_requests": (
                    client.historical_fallback_requests
                ),
                "orders_placed": 0,
            },
        )
        manifest.complete(
            raw_files=base_client.raw_recorder.written_paths,
            derived_csv_files=derived_paths,
            runtime_event_files=runtime.written_paths,
            result={
                **score.summary,
                "terminal_result_fingerprint": result_fp,
                "transport_amendment_fingerprint": amendment[
                    "transport_amendment_fingerprint"
                ],
                "live_market_requests": client.live_requests,
                "historical_fallback_requests": (
                    client.historical_fallback_requests
                ),
                "new_market_labels": len(outcomes) - len(recovered_outcomes),
                "resume_recovered_outcomes": len(recovered_outcomes),
                "resume_source_manifest": str(resume_manifest),
                "resume_source_manifest_sha256": _sha256(resume_manifest),
                "authentication_used": False,
                "model_refit_performed": False,
                "model_retuned": False,
                "model_recalibrated": False,
                "execution_enabled": False,
                "orders_placed": 0,
            },
        )
        update_attempt_receipt(
            preflight.attempt_path,
            attempt,
            status="terminal_evaluation_completed",
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
                    message=(
                        "Checkpoint-17 transport-repair resume interrupted"
                    ),
                    context={
                        "locked_test_permanently_exposed": True,
                        "transport_amendment_fingerprint": amendment[
                            "transport_amendment_fingerprint"
                        ],
                        "outcome_journal": str(journal_path),
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
                raw_files=base_client.raw_recorder.written_paths,
                derived_csv_files=[
                    path for path in derived_paths if path.exists()
                ],
                runtime_event_files=runtime.written_paths,
                result={
                    "terminal_evaluation_fingerprint": terminal_freeze[
                        "terminal_evaluation_fingerprint"
                    ],
                    "transport_amendment_fingerprint": amendment[
                        "transport_amendment_fingerprint"
                    ],
                    "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
                    "locked_test_permanently_exposed": True,
                    "outcome_journal": str(journal_path),
                    "resume_recovered_outcomes": len(recovered_outcomes),
                    "live_market_requests": client.live_requests,
                    "historical_fallback_requests": (
                        client.historical_fallback_requests
                    ),
                    "model_refit_performed": False,
                    "model_retuned": False,
                    "model_recalibrated": False,
                    "execution_enabled": False,
                    "orders_placed": 0,
                    "original_failure_type": type(exc).__name__,
                },
            )
        except RunManifestError as manifest_exc:
            raise manifest_exc from failure
        try:
            update_attempt_receipt(
                preflight.attempt_path,
                attempt,
                status="terminal_exposure_interrupted",
                manifest_path=manifest.manifest_path,
            )
        except OSError:
            pass
        if event_failure is not None:
            raise event_failure from exc
        raise

    assert outcomes is not None
    assert score is not None
    print(
        "Checkpoint-17 KXBTCD Candidate-C terminal evaluation: COMPLETE "
        "(transport-repair resume)"
    )
    print(
        "Terminal evaluation fingerprint: "
        f"{terminal_freeze['terminal_evaluation_fingerprint']}"
    )
    print(
        "Transport amendment fingerprint: "
        f"{amendment['transport_amendment_fingerprint']}"
    )
    print(f"Final model fingerprint: {FROZEN_FINAL_MODEL_FINGERPRINT}")
    print(f"Recovered labels: {len(recovered_outcomes)}")
    print(f"New market labels: {len(outcomes) - len(recovered_outcomes)}")
    print(f"Live market requests: {client.live_requests}")
    print(
        "Historical fallback requests: "
        f"{client.historical_fallback_requests}"
    )
    print(f"Locked-test events: {score.summary['locked_test_event_count']}")
    print(f"Locked-test rows: {score.summary['locked_test_row_count']}")
    print(
        "Locked-test market labels: "
        f"{score.summary['locked_test_market_label_count']}"
    )
    print(
        "Raw midpoint locked-test event-weighted log loss: "
        f"{score.summary['raw_midpoint_event_weighted_log_loss']}"
    )
    print(
        "Candidate-C locked-test event-weighted log loss: "
        f"{score.summary['candidate_c_event_weighted_log_loss']}"
    )
    print(
        "Delta log loss (raw - Candidate C): "
        f"{score.summary['delta_log_loss_raw_minus_candidate_c']}"
    )
    print(
        "Raw midpoint locked-test event-weighted Brier: "
        f"{score.summary['raw_midpoint_event_weighted_brier']}"
    )
    print(
        "Candidate-C locked-test event-weighted Brier: "
        f"{score.summary['candidate_c_event_weighted_brier']}"
    )
    print(
        "Terminal primary gate: "
        + ("PASS" if score.gate_passed else "FAIL")
    )
    print("Tie rule: fail")
    print("Locked-test set permanently exposed: yes")
    print("Model refit/tune/recalibration: no/no/no")
    print("Orders placed: 0")
    print(f"Derived directory: {derived_dir}")
    print(f"Manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        KxbtcdCandidateCTerminalEvaluationError,
        TerminalTransportRepairError,
        PublicCensusHttpError,
        RunManifestError,
        RuntimeEventWriteError,
        OSError,
        ValueError,
    ) as exc:
        raise SystemExit(
            f"KXBTCD Candidate-C CP17 transport-repair error: {exc}"
        ) from exc
