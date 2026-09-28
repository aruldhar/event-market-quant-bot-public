from dataclasses import dataclass

import pytest

from src.kxbtcd_candidate_c_terminal_transport_repair import (
    LiveFirstHistoricalFallbackClient,
    TerminalTransportRepairError,
)
from src.public_census_http import PublicCensusHttpError


@dataclass(frozen=True)
class FakeRaw:
    source: str = "test"
    session_id: str = "session"
    request_id: str = "request"


@dataclass(frozen=True)
class FakeResponse:
    payload: dict
    raw_record: FakeRaw = FakeRaw()


class FakeClient:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = []

    def get_json(self, path, *, params=None):
        self.calls.append((path, params))
        action = self.behavior[path]
        if isinstance(action, BaseException):
            raise action
        return action


def _response(ticker="KXBTCD-TEST-T1"):
    return FakeResponse(
        payload={
            "market": {
                "ticker": ticker,
                "event_ticker": "KXBTCD-TEST",
                "status": "finalized",
                "result": "yes",
            }
        }
    )


def test_live_tier_success_does_not_call_historical():
    frozen_path = "/historical/markets/KXBTCD-TEST-T1"
    live_path = "/markets/KXBTCD-TEST-T1"
    response = _response()
    base = FakeClient({live_path: response})
    client = LiveFirstHistoricalFallbackClient(base)

    actual = client.get_json(frozen_path)

    assert actual is response
    assert base.calls == [(live_path, None)]
    assert client.live_requests == 1
    assert client.historical_fallback_requests == 0


def test_http_404_on_live_falls_back_to_original_historical_path():
    frozen_path = "/historical/markets/KXBTCD-TEST-T1"
    live_path = "/markets/KXBTCD-TEST-T1"
    response = _response()
    base = FakeClient(
        {
            live_path: PublicCensusHttpError(
                "GET https://example/markets/KXBTCD-TEST-T1 returned HTTP 404"
            ),
            frozen_path: response,
        }
    )
    client = LiveFirstHistoricalFallbackClient(base)

    actual = client.get_json(frozen_path)

    assert actual is response
    assert base.calls == [(live_path, None), (frozen_path, None)]
    assert client.live_requests == 1
    assert client.historical_fallback_requests == 1


def test_non_404_live_failure_fails_closed_without_historical_retry():
    frozen_path = "/historical/markets/KXBTCD-TEST-T1"
    live_path = "/markets/KXBTCD-TEST-T1"
    base = FakeClient(
        {
            live_path: PublicCensusHttpError(
                "GET https://example/markets/KXBTCD-TEST-T1 returned HTTP 500"
            ),
        }
    )
    client = LiveFirstHistoricalFallbackClient(base)

    with pytest.raises(PublicCensusHttpError, match="HTTP 500"):
        client.get_json(frozen_path)

    assert base.calls == [(live_path, None)]
    assert client.live_requests == 1
    assert client.historical_fallback_requests == 0


def test_non_market_path_is_forwarded_unchanged():
    path = "/historical/cutoff"
    response = _response()
    base = FakeClient({path: response})
    client = LiveFirstHistoricalFallbackClient(base)

    actual = client.get_json(path)

    assert actual is response
    assert base.calls == [(path, None)]
    assert client.live_requests == 0
    assert client.historical_fallback_requests == 0


def test_malformed_frozen_market_path_fails_closed():
    base = FakeClient({})
    client = LiveFirstHistoricalFallbackClient(base)

    with pytest.raises(TerminalTransportRepairError):
        client.get_json("/historical/markets/")
