import json
import threading

import pytest

from src.kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore
from src.kxbtcd_candidate_e_v2_rest_candle_transport import (
    V2RestCandleTransportError,
    V2RestCandlePollingPolicy,
    exact_v2_candle_request,
    fetch_v2_exact_completed_candle,
    run_v2_rest_candle_polling_supervisor,
)


class Response:
    def __init__(self, *, text, status_code=200):
        self.text, self.status_code = text, status_code
        self.checked = False

    def raise_for_status(self):
        self.checked = True
        if self.status_code >= 400:
            raise RuntimeError("HTTP failure")


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, params, timeout))
        return self.response


def test_request_freezes_the_prior_completed_utc_minute():
    request = exact_v2_candle_request(decision_epoch_s=180)
    assert request.target_minute_start_s == 120
    assert request.target_minute_end_s == 180
    assert request.params["start"] == "1970-01-01T00:02:00Z"


def test_fetch_persists_and_binds_exact_candle_without_coinbase_websocket(tmp_path):
    core = SoakSourceRuntimeCore(runtime_session_id="v2-rest", archive_root=tmp_path)
    response = Response(text=json.dumps([[120, 1, 2, 1, 1.5, 3]]))
    result = fetch_v2_exact_completed_candle(
        session=Session(response), core=core, decision_epoch_s=180,
        monotonic_ns=iter((5, 6)).__next__, utc_now_text=lambda: "1970-01-01T00:03:00Z")
    assert result is not None
    assert core.connections.current_coinbase is None
    assert core.evaluate_v2_coinbase_rest_candle(decision_epoch_s=180, now_monotonic_ns=6).status.value == "PASS"
    core.close()


def test_unpublished_exact_candle_is_persisted_but_not_treated_as_websocket_failure(tmp_path):
    core = SoakSourceRuntimeCore(runtime_session_id="v2-rest", archive_root=tmp_path)
    response = Response(text="[]")
    result = fetch_v2_exact_completed_candle(
        session=Session(response), core=core, decision_epoch_s=180,
        monotonic_ns=iter((5, 6)).__next__, utc_now_text=lambda: "1970-01-01T00:03:00Z")
    assert result is None
    raw = core.manager("coinbase_exchange_rest").active_raw_path
    assert raw is not None and json.loads(raw.read_text().splitlines()[0])["raw_text"] == "[]"
    core.close()


def test_http_failure_is_persisted_before_it_raises(tmp_path):
    core = SoakSourceRuntimeCore(runtime_session_id="v2-rest", archive_root=tmp_path)
    response = Response(text="maintenance", status_code=503)
    with pytest.raises(RuntimeError, match="HTTP failure"):
        fetch_v2_exact_completed_candle(
            session=Session(response), core=core, decision_epoch_s=180,
            monotonic_ns=iter((5, 6)).__next__, utc_now_text=lambda: "1970-01-01T00:03:00Z")
    raw = core.manager("coinbase_exchange_rest").active_raw_path
    assert raw is not None and json.loads(raw.read_text().splitlines()[0])["raw_text"] == "maintenance"
    core.close()


def test_rejects_nonpositive_timeout(tmp_path):
    with pytest.raises(V2RestCandleTransportError, match="positive"):
        fetch_v2_exact_completed_candle(session=Session(Response(text="[]")),
            core=SoakSourceRuntimeCore(runtime_session_id="v2-rest", archive_root=tmp_path),
            decision_epoch_s=180, timeout_seconds=0)


def test_polling_policy_bounds_unpublished_candle_attempts_per_minute():
    policy = V2RestCandlePollingPolicy(maximum_attempts_per_minute=2)
    assert policy.allow(decision_epoch_s=180, now_monotonic_ns=1)
    assert not policy.allow(decision_epoch_s=180, now_monotonic_ns=2)
    assert policy.allow(decision_epoch_s=180, now_monotonic_ns=1_000_000_001)
    assert not policy.allow(decision_epoch_s=180, now_monotonic_ns=2_000_000_001)
    assert policy.allow(decision_epoch_s=240, now_monotonic_ns=2_000_000_002)


def test_polling_supervisor_retries_unpublished_candle_then_binds_it(tmp_path):
    core = SoakSourceRuntimeCore(runtime_session_id="v2-rest", archive_root=tmp_path)
    target = 120
    session = type("Session", (), {"responses": [Response(text="[]"), Response(text=json.dumps([[target, 1, 2, 1, 1.5, 3]]))],
        "get": lambda self, *args, **kwargs: self.responses.pop(0)})()
    stop = threading.Event()
    ticks = iter((1, 2, 1_000_000_002, 1_000_000_003, 1_000_000_004,
                  1_000_000_005))
    sleeps = []
    def sleep(_):
        sleeps.append(1)
        if len(sleeps) == 2:
            stop.set()
    run_v2_rest_candle_polling_supervisor(stop_event=stop, session=session, core=core,
        epoch_seconds=lambda: 180, monotonic_ns=lambda: next(ticks), sleep_seconds=sleep,
        utc_now_text=lambda: "1970-01-01T00:03:00Z")
    assert core.evaluate_v2_coinbase_rest_candle(decision_epoch_s=180,
        now_monotonic_ns=1_000_000_005).status.value == "PASS"
    core.close()
