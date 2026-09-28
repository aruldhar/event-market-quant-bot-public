"""Sequential outcome-blind C2 materialization from the strict post-C1 tail.

There is no arbitrary start-index argument. Progress is reconstructed only from
validated prior C2 chunks. Collection stops exactly at the 500th eligible C2
event and may never cross the absolute Checkpoint-21A reserve boundary.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Mapping

from collect_kxbtcd_candidate_e_coinbase_primary_materialization_chunk import (
    ANCHOR_FIELDS,
    EVENT_FIELDS,
    _materialize_event,
)
from collect_kxbtcd_candidate_e_historical_materialization_chunk import (
    COINBASE_RAW_ROOT,
    _all_raw_paths,
    _parse_utc,
    _write_csv,
)
from src.config import (
    DEFAULT_MANIFEST_ROOT,
    DEFAULT_RAW_LOG_ROOT,
    DEFAULT_RUNTIME_EVENT_ROOT,
    KALSHI_PUBLIC_BASE_URL,
)
from src.kxbtcd_candidate_e_c2_preparation import (
    C2_CHUNK_ROOT,
    C2_COLLECTOR_NAME,
    C2_ELIGIBLE_EVENT_TARGET,
    C2_STRICT_TAIL_START_INDEX,
    MAX_C2_CHUNK_EVENTS,
    PARENT_21A_PROTOCOL_FINGERPRINT,
    R1_MODEL_PATH,
    STRICT_TAIL_MAX_END_EXCLUSIVE,
    CandidateEC2PreparationError,
    _read_json,
    _sha256_file,
    assert_runtime_checkout_is_frozen_21e_a,
    load_and_validate_r1_model,
    validate_candidate_end_index,
)
from src.kxbtcd_candidate_e_coinbase_primary_materialization import (
    FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT,
    FROZEN_CONTRACT_FINGERPRINT,
    PREOUTCOME_ROW_FIELDS,
    load_frozen_untouched_queue,
    validate_coinbase_primary_amendment,
)
from src.kxbtcd_independent_btc_historical_materialization import COINBASE_BASE_URL
from src.public_census_http import PublicCensusHttpClient, PublicCensusHttpError
from src.raw_json_log import RawLogWriteError
from src.run_manifest import CollectionRunManifest, RunManifestError
from src.runtime_events import RuntimeEventLogger, RuntimeEventWriteError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-events", type=int, default=100)
    args = parser.parse_args()
    if args.max_events <= 0 or args.max_events > MAX_C2_CHUNK_EVENTS:
        parser.error(f"--max-events must be in [1,{MAX_C2_CHUNK_EVENTS}]")
    return args


def _sha256(path: Path) -> str:
    return _sha256_file(path)


def _descriptor_by_path(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    files = manifest.get("files")
    if not isinstance(files, list):
        raise CandidateEC2PreparationError("prior C2 manifest files must be list")
    for descriptor in files:
        if not isinstance(descriptor, Mapping):
            continue
        spec = descriptor.get("path")
        if isinstance(spec, Mapping) and spec.get("kind") == "repository_relative":
            value = spec.get("value")
            if isinstance(value, str):
                result[value.replace("\\", "/")] = descriptor
    return result


def _manifest_for_run(repo: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    matches = list((repo / "data" / "manifests").rglob(f"{run_id}.json"))
    if len(matches) != 1:
        raise CandidateEC2PreparationError(
            f"expected exactly one manifest for prior C2 run {run_id}, found {len(matches)}"
        )
    path = matches[0]
    return path, _read_json(path)


def validated_prior_progress(repo: Path) -> tuple[int, int, tuple[int, ...]]:
    event_files = sorted((repo / C2_CHUNK_ROOT).glob("*_events.csv"))
    if not event_files:
        return 0, 0, ()
    all_indices: list[int] = []
    eligible = 0
    seen_runs: set[str] = set()

    for event_path in event_files:
        run_id = event_path.name[: -len("_events.csv")]
        if run_id in seen_runs:
            raise CandidateEC2PreparationError(f"duplicate C2 run id {run_id}")
        seen_runs.add(run_id)
        _, manifest = _manifest_for_run(repo, run_id)
        if manifest.get("status") != "completed":
            raise CandidateEC2PreparationError(f"prior C2 manifest not completed: {run_id}")
        collector = manifest.get("collector")
        arguments = manifest.get("arguments")
        result = manifest.get("result")
        if not isinstance(collector, Mapping) or collector.get("name") != C2_COLLECTOR_NAME:
            raise CandidateEC2PreparationError("prior C2 collector identity mismatch")
        if not isinstance(arguments, Mapping) or not isinstance(result, Mapping):
            raise CandidateEC2PreparationError("prior C2 manifest arguments/result missing")
        if arguments.get("parent_21a_protocol_fingerprint") != PARENT_21A_PROTOCOL_FINGERPRINT:
            raise CandidateEC2PreparationError("prior C2 protocol fingerprint mismatch")
        if result.get("outcomes_accessed") is not False or result.get("orders_placed") != 0:
            raise CandidateEC2PreparationError("prior C2 chunk violated outcome/order firewall")

        descriptors = _descriptor_by_path(manifest)
        relative = event_path.relative_to(repo).as_posix()
        descriptor = descriptors.get(relative)
        if descriptor is None or descriptor.get("sha256") != _sha256(event_path):
            raise CandidateEC2PreparationError(
                f"prior C2 event artifact hash mismatch: {relative}"
            )

        with event_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if int(result.get("processed_events", -1)) != len(rows):
            raise CandidateEC2PreparationError(
                "prior C2 manifest processed-event count mismatch"
            )
        for row in rows:
            index = int(row["queue_index_zero_based"])
            all_indices.append(index)
            if row["eligible_event"].lower() == "true":
                eligible += 1

    all_indices.sort()
    expected = list(
        range(C2_STRICT_TAIL_START_INDEX, C2_STRICT_TAIL_START_INDEX + len(all_indices))
    )
    if all_indices != expected:
        raise CandidateEC2PreparationError(
            "prior C2 chunks are not one exact contiguous strict-tail prefix"
        )
    if len(all_indices) != len(set(all_indices)):
        raise CandidateEC2PreparationError("prior C2 chunks overlap queue indices")
    if eligible > C2_ELIGIBLE_EVENT_TARGET:
        raise CandidateEC2PreparationError(
            "prior C2 chunks materialized beyond the 500th eligible event"
        )
    validate_candidate_end_index(C2_STRICT_TAIL_START_INDEX + len(all_indices))
    return len(all_indices), eligible, tuple(all_indices)


def main() -> None:
    args = parse_args()
    repo = Path(".").resolve()
    git_head, implementation_freeze = assert_runtime_checkout_is_frozen_21e_a(repo)
    validate_coinbase_primary_amendment()
    r1 = load_and_validate_r1_model(repo)
    r1_fingerprint = str(r1["champion_r1_fingerprint"])

    processed_before, eligible_before, _ = validated_prior_progress(repo)
    if eligible_before >= C2_ELIGIBLE_EVENT_TARGET:
        raise CandidateEC2PreparationError(
            "C2 already has 500 eligible materialized events; freeze it instead"
        )

    start_index = C2_STRICT_TAIL_START_INDEX + processed_before
    validate_candidate_end_index(start_index)
    available_before_floor = STRICT_TAIL_MAX_END_EXCLUSIVE - start_index
    if available_before_floor <= 0:
        raise CandidateEC2PreparationError(
            "no C2/C3 candidate runway remains before the 21A hard floor"
        )
    max_to_process = min(args.max_events, available_before_floor)

    queue = load_frozen_untouched_queue()
    if len(queue) < STRICT_TAIL_MAX_END_EXCLUSIVE:
        raise CandidateEC2PreparationError(
            "frozen untouched queue is shorter than 21A contract"
        )

    kalshi = PublicCensusHttpClient(
        base_url=KALSHI_PUBLIC_BASE_URL,
        source_name="kalshi_rest_candidate_e_c2_preoutcome",
        raw_root=DEFAULT_RAW_LOG_ROOT,
        timeout_seconds=15.0,
        max_rate_limit_retries=4,
    )
    coinbase = PublicCensusHttpClient(
        base_url=COINBASE_BASE_URL,
        source_name="coinbase_exchange_rest_candidate_e_c2_preoutcome",
        raw_root=COINBASE_RAW_ROOT,
        timeout_seconds=15.0,
        max_rate_limit_retries=4,
    )

    manifest = CollectionRunManifest(
        collector_name=C2_COLLECTOR_NAME,
        arguments={
            "checkpoint_id": "21E-C",
            "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
            "implementation_freeze_fingerprint": implementation_freeze[
                "implementation_freeze_fingerprint"
            ],
            "champion_r1_fingerprint": r1_fingerprint,
            "historical_contract_fingerprint": FROZEN_CONTRACT_FINGERPRINT,
            "coinbase_primary_amendment_fingerprint": (
                FROZEN_COINBASE_PRIMARY_AMENDMENT_FINGERPRINT
            ),
            "strict_tail_start_index": C2_STRICT_TAIL_START_INDEX,
            "absolute_max_end_index_exclusive": STRICT_TAIL_MAX_END_EXCLUSIVE,
            "start_index": start_index,
            "requested_max_events": args.max_events,
            "eligible_before": eligible_before,
            "eligible_target": C2_ELIGIBLE_EVENT_TARGET,
            "outcomes_accessed": False,
            "candidate_e_fit_performed_during_collection": False,
            "C3_materialized_or_opened": False,
            "execution_enabled": False,
            "orders_placed": 0,
        },
        manifest_root=DEFAULT_MANIFEST_ROOT,
        source_sessions=[
            {
                "source": kalshi.raw_recorder.source_name,
                "session_id": kalshi.raw_recorder.session_id,
            },
            {
                "source": coinbase.raw_recorder.source_name,
                "session_id": coinbase.raw_recorder.session_id,
            },
        ],
        runtime_observability=True,
    )
    runtime = RuntimeEventLogger(
        DEFAULT_RUNTIME_EVENT_ROOT,
        run_id=manifest.run_id,
        collector_name=C2_COLLECTOR_NAME,
        started_at_utc=manifest.started_at_utc,
    )
    for client in (kalshi, coinbase):
        client.attach_runtime_event_logger(runtime)

    C2_CHUNK_ROOT.mkdir(parents=True, exist_ok=True)
    event_path = C2_CHUNK_ROOT / f"{manifest.run_id}_events.csv"
    anchor_path = C2_CHUNK_ROOT / f"{manifest.run_id}_anchors.csv"
    row_path = C2_CHUNK_ROOT / f"{manifest.run_id}_rows.csv"
    event_rows: list[dict[str, Any]] = []
    anchor_rows: list[dict[str, Any]] = []
    common_rows: list[dict[str, Any]] = []
    derived: list[Path] = []
    eligible_now = eligible_before

    try:
        runtime.emit(
            "collector.started",
            severity="info",
            message="Checkpoint-21E-C sequential C2 materialization started",
            context={
                "git_head": git_head,
                "start_index": start_index,
                "eligible_before": eligible_before,
                "eligible_target": C2_ELIGIBLE_EVENT_TARGET,
                "outcomes_accessed": False,
                "C3_materialized_or_opened": False,
                "orders_placed": 0,
            },
        )
        cutoff_response = kalshi.get_json("/historical/cutoff")
        cutoff_text = cutoff_response.payload.get("market_settled_ts")
        if not isinstance(cutoff_text, str):
            raise CandidateEC2PreparationError(
                "historical cutoff missing market_settled_ts"
            )
        cutoff_utc = _parse_utc(cutoff_text)

        for offset in range(max_to_process):
            queue_index = start_index + offset
            validate_candidate_end_index(queue_index + 1)
            event_row, event_anchors, event_common = _materialize_event(
                event=queue[queue_index],
                run_id=manifest.run_id,
                cutoff_utc=cutoff_utc,
                kalshi=kalshi,
                coinbase=coinbase,
            )
            event_rows.append(event_row)
            anchor_rows.extend(event_anchors)
            common_rows.extend(event_common)
            if bool(event_row["eligible_event"]):
                eligible_now += 1
            runtime.emit(
                "materialization.event.completed",
                severity="info",
                message="C2 candidate event materialization completed",
                context={
                    "queue_index_zero_based": queue_index,
                    "event_ticker": event_row["event_ticker"],
                    "eligible_event": event_row["eligible_event"],
                    "c2_eligible_progress": eligible_now,
                },
            )
            if eligible_now == C2_ELIGIBLE_EVENT_TARGET:
                break

        _write_csv(event_path, EVENT_FIELDS, event_rows)
        _write_csv(anchor_path, ANCHOR_FIELDS, anchor_rows)
        _write_csv(row_path, PREOUTCOME_ROW_FIELDS, common_rows)
        derived = [event_path, anchor_path, row_path]
        end_index = start_index + len(event_rows)
        validate_candidate_end_index(end_index)

        result = {
            "parent_21a_protocol_fingerprint": PARENT_21A_PROTOCOL_FINGERPRINT,
            "implementation_freeze_fingerprint": implementation_freeze[
                "implementation_freeze_fingerprint"
            ],
            "champion_r1_fingerprint": r1_fingerprint,
            "start_index": start_index,
            "end_index_exclusive": end_index,
            "processed_events": len(event_rows),
            "eligible_before": eligible_before,
            "eligible_events_in_chunk": eligible_now - eligible_before,
            "eligible_after": eligible_now,
            "eligible_target": C2_ELIGIBLE_EVENT_TARGET,
            "stopped_at_target": eligible_now == C2_ELIGIBLE_EVENT_TARGET,
            "common_rows": len(common_rows),
            "outcomes_accessed": False,
            "candidate_e_fit_performed_during_collection": False,
            "C3_materialized_or_opened": False,
            "execution_enabled": False,
            "orders_placed": 0,
        }
        runtime.emit(
            "collector.completed",
            severity="info",
            message="Checkpoint-21E-C C2 materialization chunk completed",
            context=result,
        )
        manifest.complete(
            raw_files=_all_raw_paths(kalshi, coinbase),
            derived_csv_files=derived,
            runtime_event_files=runtime.written_paths,
            result=result,
        )
    except BaseException as exc:
        try:
            manifest.fail(
                exc,
                raw_files=_all_raw_paths(kalshi, coinbase),
                derived_csv_files=[p for p in derived if p.exists()],
                runtime_event_files=runtime.written_paths,
                result={
                    "start_index": start_index,
                    "processed_events_before_failure": len(event_rows),
                    "eligible_before": eligible_before,
                    "eligible_during_failed_chunk": eligible_now - eligible_before,
                    "outcomes_accessed": False,
                    "C3_materialized_or_opened": False,
                    "execution_enabled": False,
                    "orders_placed": 0,
                },
            )
        except RunManifestError:
            pass
        raise

    print("Checkpoint 21E-C C2 pre-outcome materialization chunk: PASS")
    print(f"Queue range: [{start_index}, {start_index + len(event_rows)})")
    print(f"Events processed this chunk: {len(event_rows)}")
    print(f"C2 eligible progress: {eligible_now}/{C2_ELIGIBLE_EVENT_TARGET}")
    print(f"Stopped at exact target: {eligible_now == C2_ELIGIBLE_EVENT_TARGET}")
    print("C2 outcomes opened: 0")
    print("C3 materialized: 0")
    print("Orders placed: 0")
    print(f"Manifest: {manifest.manifest_path}")


if __name__ == "__main__":
    try:
        main()
    except (
        CandidateEC2PreparationError,
        PublicCensusHttpError,
        RawLogWriteError,
        RunManifestError,
        RuntimeEventWriteError,
    ) as exc:
        raise SystemExit(f"C2 materialization error: {exc}") from exc
