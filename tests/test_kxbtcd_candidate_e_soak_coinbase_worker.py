from datetime import datetime
import json

from src.kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    SoakSourceRuntimeCore,
)


def epoch_s(text):
    return int(
        datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).timestamp()
    )


DECISION_S = epoch_s(
    "2026-09-04T15:10:30Z"
)


def new_worker(tmp_path):
    core = SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
    )

    worker = CoinbaseReadOnlyWorkerSession(
        core
    )

    worker.start_generation(
        opened_monotonic_ns=(
            1_000_000_000
        )
    )

    return core, worker


def last_match(
    trade_id=100,
    sequence=200,
    time_text="2026-09-04T15:10:05Z",
):
    return json.dumps(
        {
            "type": "last_match",
            "product_id": "BTC-USD",
            "trade_id": trade_id,
            "sequence": sequence,
            "time": time_text,
            "price": "110200",
            "size": "0.01",
            "side": "buy",
        }
    )


def heartbeat(
    *,
    last_trade_id=100,
    sequence=201,
    time_text="2026-09-04T15:10:06Z",
):
    return json.dumps(
        {
            "type": "heartbeat",
            "product_id": "BTC-USD",
            "last_trade_id": last_trade_id,
            "sequence": sequence,
            "time": time_text,
        }
    )


def test_worker_requests_exact_rest_seed_when_only_prior_minute_missing(
    tmp_path,
):
    core, worker = new_worker(tmp_path)

    first = worker.ingest_ws_frame(
        raw_text=last_match(),
        received_monotonic_ns=(
            2_000_000_000
        ),
        received_utc="2026-09-04T15:10:05Z",
        decision_epoch_s=DECISION_S,
    )

    assert first.kind == "BLOCKED"

    second = worker.ingest_ws_frame(
        raw_text=heartbeat(),
        received_monotonic_ns=(
            3_000_000_000
        ),
        received_utc="2026-09-04T15:10:06Z",
        decision_epoch_s=DECISION_S,
    )

    assert (
        second.kind
        == "REST_CANDLE_SEED_REQUIRED"
    )

    assert (
        second.target_minute_end_s
        - second.target_minute_start_s
        == 60
    )

    core.close()


def test_exact_seed_transitions_worker_to_ready(
    tmp_path,
):
    core, worker = new_worker(tmp_path)

    worker.ingest_ws_frame(
        raw_text=last_match(),
        received_monotonic_ns=(
            2_000_000_000
        ),
        received_utc="2026-09-04T15:10:05Z",
        decision_epoch_s=DECISION_S,
    )

    worker.ingest_ws_frame(
        raw_text=heartbeat(),
        received_monotonic_ns=(
            3_000_000_000
        ),
        received_utc="2026-09-04T15:10:06Z",
        decision_epoch_s=DECISION_S,
    )

    target_start = (
        (DECISION_S // 60) * 60
    ) - 60

    action = worker.apply_rest_candle_seed(
        raw_text=json.dumps(
            [
                [
                    target_start,
                    109900,
                    110150,
                    110000,
                    110123.45,
                    12.5,
                ]
            ]
        ),
        received_monotonic_ns=(
            3_500_000_000
        ),
        received_utc="2026-09-04T15:10:07Z",
        decision_epoch_s=DECISION_S,
        request_identity={
            "method": "GET",
            "params": {
                "granularity": 60,
            },
        },
    )

    assert action.kind == "READY"
    assert (
        core.coinbase_backoff.consecutive_failures
        == 0
    )

    core.close()


def test_short_lived_recovered_generation_does_not_reset_backoff(tmp_path):
    core, worker = new_worker(tmp_path)
    core.record_source_failure("coinbase", observed_monotonic_ns=1_500_000_000)

    worker.ingest_ws_frame(raw_text=last_match(), received_monotonic_ns=2_000_000_000,
        received_utc="2026-09-04T15:10:05Z", decision_epoch_s=DECISION_S)
    worker.ingest_ws_frame(raw_text=heartbeat(), received_monotonic_ns=3_000_000_000,
        received_utc="2026-09-04T15:10:06Z", decision_epoch_s=DECISION_S)
    target_start = (DECISION_S // 60) * 60 - 60
    action = worker.apply_rest_candle_seed(raw_text=json.dumps([[target_start, 1, 2, 1, 1.5, 3]]),
        received_monotonic_ns=3_500_000_000, received_utc="2026-09-04T15:10:07Z",
        decision_epoch_s=DECISION_S)

    assert action.kind == "READY"
    assert core.coinbase_backoff.consecutive_failures == 1
    worker.ingest_ws_frame(raw_text=heartbeat(sequence=202, time_text="2026-09-04T15:10:34Z"),
        received_monotonic_ns=31_000_000_000, received_utc="2026-09-04T15:10:34Z",
        decision_epoch_s=DECISION_S)
    assert core.coinbase_backoff.consecutive_failures == 0
    core.close()


def test_trade_gap_requests_exact_rest_recovery_interval(
    tmp_path,
):
    core, worker = new_worker(tmp_path)

    worker.ingest_ws_frame(
        raw_text=last_match(),
        received_monotonic_ns=(
            2_000_000_000
        ),
        received_utc="2026-09-04T15:10:05Z",
        decision_epoch_s=DECISION_S,
    )

    action = worker.ingest_ws_frame(
        raw_text=json.dumps(
            {
                "type": "match",
                "product_id": "BTC-USD",
                "trade_id": 103,
                "sequence": 201,
                "time": "2026-09-04T15:10:06Z",
                "price": "110210",
                "size": "0.01",
                "side": "sell",
            }
        ),
        received_monotonic_ns=(
            3_000_000_000
        ),
        received_utc="2026-09-04T15:10:06Z",
        decision_epoch_s=DECISION_S,
    )

    assert (
        action.kind
        == "REST_GAP_RECOVERY_REQUIRED"
    )

    assert (
        action.recovery_from_trade_id
        == 100
    )

    assert (
        action.recovery_target_trade_id
        == 103
    )

    core.close()


def test_disconnect_schedules_frozen_backoff(
    tmp_path,
):
    core, worker = new_worker(tmp_path)

    decision = worker.disconnect(
        closed_monotonic_ns=(
            2_000_000_000
        )
    )

    assert decision.delay_seconds == 1
    assert not (
        core.connections
        .current_coinbase
        .connected
    )

    core.close()


def test_reconnect_gets_fresh_generation_and_clears_old_seed(
    tmp_path,
):
    core, worker = new_worker(tmp_path)

    first_generation = (
        worker.binding.generation
    )

    core.coinbase_rest_seed = object()

    worker.disconnect(
        closed_monotonic_ns=(
            2_000_000_000
        )
    )

    new_binding = worker.start_generation(
        opened_monotonic_ns=(
            3_000_000_000
        )
    )

    assert (
        new_binding.generation
        == first_generation + 1
    )

    assert core.coinbase_rest_seed is None
    assert not new_binding.builder.seeded

    core.close()
