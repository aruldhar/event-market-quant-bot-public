from datetime import datetime
import json

import pytest

from src.kxbtcd_candidate_e_soak_coinbase_rest_transport import (
    CoinbaseRestTransportError,
    exact_candle_request,
    fetch_exact_seed_candle,
)
from src.kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseReadOnlyWorkerSession,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    COINBASE_REST_SOURCE,
    SoakSourceRuntimeCore,
)


# Decision occurs just after the 14:09:00-14:10:00 UTC
# completed minute.  The WS generation begins at 14:10:05, so it
# legitimately needs a one-time REST seed for that prior minute.
DECISION_S = int(
    datetime.fromisoformat(
        "2024-09-05T14:10:30+00:00"
    ).timestamp()
)

assert DECISION_S == 1_725_545_430


class FakeResponse:
    def __init__(
        self,
        *,
        status_code,
        text,
        before_raise=None,
    ):
        self.status_code = status_code
        self.text = text
        self.before_raise = before_raise

    def raise_for_status(self):
        if self.before_raise is not None:
            self.before_raise()

        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}"
            )


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(
        self,
        url,
        *,
        params,
        timeout,
    ):
        self.calls.append(
            {
                "url": url,
                "params": dict(params),
                "timeout": timeout,
            }
        )
        return self.response


def prepare_seed_action(tmp_path):
    core = SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
    )

    worker = CoinbaseReadOnlyWorkerSession(
        core
    )

    worker.start_generation(
        opened_monotonic_ns=1_000
    )

    worker.ingest_ws_frame(
        raw_text=json.dumps(
            {
                "type": "last_match",
                "product_id": "BTC-USD",
                "trade_id": 100,
                "sequence": 200,
                "time": "2024-09-05T14:10:05Z",
                "price": "110200",
                "size": "0.01",
                "side": "buy",
            }
        ),
        received_monotonic_ns=2_000,
        received_utc="2024-09-05T14:10:05Z",
        decision_epoch_s=DECISION_S,
    )

    action = worker.ingest_ws_frame(
        raw_text=json.dumps(
            {
                "type": "heartbeat",
                "product_id": "BTC-USD",
                "last_trade_id": 100,
                "sequence": 201,
                "time": "2024-09-05T14:10:06Z",
            }
        ),
        received_monotonic_ns=3_000,
        received_utc="2024-09-05T14:10:06Z",
        decision_epoch_s=DECISION_S,
    )

    assert (
        action.kind
        == "REST_CANDLE_SEED_REQUIRED"
    )

    return core, worker, action


def test_exact_candle_request_is_one_aligned_minute(
    tmp_path,
):
    core, worker, action = (
        prepare_seed_action(tmp_path)
    )

    request = exact_candle_request(
        action
    )

    assert request.params["granularity"] == 60
    assert (
        request.target_minute_end_s
        - request.target_minute_start_s
        == 60
    )
    assert request.target_minute_start_s % 60 == 0
    assert request.params["start"].endswith("Z")
    assert request.params["end"].endswith("Z")
    assert request.url.endswith(
        "/products/BTC-USD/candles"
    )

    core.close()


def test_http_body_is_persisted_before_raise_for_status(
    tmp_path,
):
    core, worker, action = (
        prepare_seed_action(tmp_path)
    )

    body = '{"message":"temporary failure"}'

    observed = {
        "persisted_before_raise": False,
    }

    def before_raise():
        raw = core.manager(
            COINBASE_REST_SOURCE
        ).active_raw_path

        assert raw is not None

        records = [
            json.loads(line)
            for line in raw.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        observed[
            "persisted_before_raise"
        ] = any(
            row["raw_text"] == body
            for row in records
        )

    session = FakeSession(
        FakeResponse(
            status_code=503,
            text=body,
            before_raise=before_raise,
        )
    )

    times = iter(
        [10_000, 11_000]
    )

    with pytest.raises(
        RuntimeError,
        match="HTTP 503",
    ):
        fetch_exact_seed_candle(
            session=session,
            worker=worker,
            action=action,
            decision_epoch_s=(
                DECISION_S
            ),
            monotonic_ns=lambda: next(
                times
            ),
            utc_now_text=lambda: (
                "2024-09-05T14:10:07Z"
            ),
        )

    assert observed[
        "persisted_before_raise"
    ]

    core.close()


def test_successful_exact_candle_transitions_to_ready(
    tmp_path,
):
    core, worker, action = (
        prepare_seed_action(tmp_path)
    )

    target = action.target_minute_start_s

    body = json.dumps(
        [
            [
                target,
                109900,
                110150,
                110000,
                110123.45,
                12.5,
            ]
        ]
    )

    session = FakeSession(
        FakeResponse(
            status_code=200,
            text=body,
        )
    )

    times = iter(
        [10_000, 11_000]
    )

    result = fetch_exact_seed_candle(
        session=session,
        worker=worker,
        action=action,
        decision_epoch_s=DECISION_S,
        monotonic_ns=lambda: next(times),
        utc_now_text=lambda: (
            "2024-09-05T14:10:07Z"
        ),
    )

    assert result.kind == "READY"
    assert len(session.calls) == 1

    call = session.calls[0]

    assert call["params"]["granularity"] == 60

    core.close()


def test_empty_successful_candle_response_is_persisted_then_recoverable(
    tmp_path,
):
    core, worker, action = prepare_seed_action(tmp_path)
    session = FakeSession(FakeResponse(status_code=200, text="[]"))
    times = iter([10_000, 11_000])

    result = fetch_exact_seed_candle(
        session=session,
        worker=worker,
        action=action,
        decision_epoch_s=DECISION_S,
        monotonic_ns=lambda: next(times),
        utc_now_text=lambda: "2024-09-05T14:10:07Z",
    )
    assert result == action

    raw = core.manager(COINBASE_REST_SOURCE).active_raw_path
    assert raw is not None
    assert any(
        row["raw_text"] == "[]"
        for row in (
            json.loads(line)
            for line in raw.read_text(encoding="utf-8").splitlines()
        )
    )
    core.close()


def test_extra_nearby_candle_does_not_replace_exact_target(
    tmp_path,
):
    core, worker, action = (
        prepare_seed_action(tmp_path)
    )

    target = action.target_minute_start_s

    body = json.dumps(
        [
            [
                target - 60,
                1,
                2,
                1,
                1.5,
                3,
            ],
            [
                target,
                109900,
                110150,
                110000,
                110123.45,
                12.5,
            ],
        ]
    )

    session = FakeSession(
        FakeResponse(
            status_code=200,
            text=body,
        )
    )

    times = iter(
        [10_000, 11_000]
    )

    result = fetch_exact_seed_candle(
        session=session,
        worker=worker,
        action=action,
        decision_epoch_s=DECISION_S,
        monotonic_ns=lambda: next(times),
        utc_now_text=lambda: (
            "2024-09-05T14:10:07Z"
        ),
    )

    assert result.kind == "READY"

    core.close()


def test_wrong_action_cannot_issue_candle_request(
    tmp_path,
):
    core, worker, action = (
        prepare_seed_action(tmp_path)
    )

    wrong = type(action)(
        kind="BLOCKED",
        reason="TEST",
        connection_generation=(
            action.connection_generation
        ),
    )

    with pytest.raises(
        CoinbaseRestTransportError,
    ):
        exact_candle_request(
            wrong
        )

    core.close()
