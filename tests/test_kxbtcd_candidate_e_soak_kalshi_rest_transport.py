import json

import pytest

from src.kxbtcd_candidate_e_soak_kalshi_rest_transport import (
    KALSHI_MARKETS_LIMIT,
    discovery_request,
    fetch_current_kxbtcd_event,
    fetch_kalshi_final_market_settlement,
)
from src.kxbtcd_candidate_e_live_shadow_settlement_feed import (
    CANONICAL_SETTLEMENT_FEED_FILENAME,
    LiveShadowSettlementPublisher,
    read_live_shadow_settlements,
)
from src.kxbtcd_candidate_e_soak_runtime_core import (
    KALSHI_REST_SOURCE,
    SoakRuntimeCoreError,
    SoakSourceRuntimeCore,
)


NOW_MS = 1_788_534_000_000


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


def market(
    *,
    event,
    ticker,
    close_time,
):
    return {
        "ticker": ticker,
        "event_ticker": event,
        "status": "active",
        "close_time": close_time,
    }


def complete_payload():
    return {
        "markets": [
            market(
                event="KXBTCD-26SEP0416",
                ticker=(
                    "KXBTCD-26SEP0416-T110000.00"
                ),
                close_time=(
                    "2026-09-04T16:00:00Z"
                ),
            ),
            market(
                event="KXBTCD-26SEP0416",
                ticker=(
                    "KXBTCD-26SEP0416-T111000.00"
                ),
                close_time=(
                    "2026-09-04T16:00:00Z"
                ),
            ),
            market(
                event="KXBTCD-26SEP0417",
                ticker=(
                    "KXBTCD-26SEP0417-T110000.00"
                ),
                close_time=(
                    "2026-09-04T17:00:00Z"
                ),
            ),
        ],
        "cursor": "",
    }


def new_core(tmp_path):
    return SoakSourceRuntimeCore(
        runtime_session_id="runtime-a",
        archive_root=tmp_path,
    )


def test_request_is_strategy_independent_kxbtcd_open_universe():
    url, params = discovery_request()

    assert url.endswith(
        "/markets"
    )

    assert params == {
        "series_ticker": "KXBTCD",
        "status": "open",
        "limit": KALSHI_MARKETS_LIMIT,
    }

    assert KALSHI_MARKETS_LIMIT == 1000


def test_http_failure_body_is_raw_persisted_before_raise(
    tmp_path,
):
    core = new_core(
        tmp_path
    )

    body = '{"error":"temporary"}'

    observed = {
        "persisted": False,
    }

    def before_raise():
        raw = core.manager(
            KALSHI_REST_SOURCE
        ).active_raw_path

        assert raw is not None
        assert raw.exists()

        rows = [
            json.loads(line)
            for line in raw.read_text(
                encoding="utf-8"
            ).splitlines()
        ]

        observed["persisted"] = any(
            row["raw_text"] == body
            for row in rows
        )

    session = FakeSession(
        FakeResponse(
            status_code=503,
            text=body,
            before_raise=before_raise,
        )
    )

    times = iter(
        [1_000, 2_000]
    )

    with pytest.raises(
        RuntimeError,
        match="HTTP 503",
    ):
        fetch_current_kxbtcd_event(
            session=session,
            core=core,
            now_timestamp_ms=NOW_MS,
            monotonic_ns=lambda: next(
                times
            ),
            utc_now_text=lambda: (
                "2026-09-04T15:30:00Z"
            ),
        )

    assert observed["persisted"]

    core.close()


def test_complete_response_selects_earliest_future_event_and_full_ladder(
    tmp_path,
):
    core = new_core(
        tmp_path
    )

    body = json.dumps(
        complete_payload()
    )

    session = FakeSession(
        FakeResponse(
            status_code=200,
            text=body,
        )
    )

    times = iter(
        [1_000, 2_000]
    )

    result = fetch_current_kxbtcd_event(
        session=session,
        core=core,
        now_timestamp_ms=NOW_MS,
        monotonic_ns=lambda: next(
            times
        ),
        utc_now_text=lambda: (
            "2026-09-04T15:30:00Z"
        ),
    )

    assert result.current_event.event_ticker == (
        "KXBTCD-26SEP0416"
    )

    assert {
        market.market_ticker
        for market in result.current_event.markets
    } == {
        "KXBTCD-26SEP0416-T110000.00",
        "KXBTCD-26SEP0416-T111000.00",
    }

    assert result.rollover_required is False

    assert len(session.calls) == 1

    core.close()


def test_nonempty_cursor_is_hard_block_before_event_mutation(
    tmp_path,
):
    core = new_core(
        tmp_path
    )

    payload = complete_payload()
    payload["cursor"] = "next-page-token"

    body = json.dumps(
        payload
    )

    session = FakeSession(
        FakeResponse(
            status_code=200,
            text=body,
        )
    )

    times = iter(
        [1_000, 2_000]
    )

    with pytest.raises(
        SoakRuntimeCoreError,
        match="paginated/incomplete",
    ):
        fetch_current_kxbtcd_event(
            session=session,
            core=core,
            now_timestamp_ms=NOW_MS,
            monotonic_ns=lambda: next(
                times
            ),
            utc_now_text=lambda: (
                "2026-09-04T15:30:00Z"
            ),
        )

    # Incomplete evidence must not install a selected event.
    assert core.current_event is None

    # But the exact incomplete response remains archived.
    raw = core.manager(
        KALSHI_REST_SOURCE
    ).active_raw_path

    assert raw is not None

    record = json.loads(
        raw.read_text(
            encoding="utf-8"
        ).splitlines()[0]
    )

    assert record["raw_text"] == body

    core.close()


def test_existing_raw_api_still_persists_exactly_once(
    tmp_path,
):
    core = new_core(
        tmp_path
    )

    body = json.dumps(
        complete_payload()
    )

    core.discover_current_event_from_raw(
        raw_text=body,
        received_monotonic_ns=1_000,
        received_utc="2026-09-04T15:30:00Z",
        now_timestamp_ms=NOW_MS,
        request_identity={
            "method": "GET",
            "params": {
                "series_ticker": "KXBTCD",
                "status": "open",
            },
        },
    )

    raw = core.manager(
        KALSHI_REST_SOURCE
    ).active_raw_path

    assert raw is not None

    records = raw.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(records) == 1

    core.close()


def test_rollover_final_market_response_is_raw_first_then_publishes_only_finalized_outcome(tmp_path):
    core = new_core(tmp_path)
    core.live_shadow_settlement_publisher = LiveShadowSettlementPublisher(
        run_id="runtime-a", output_path=tmp_path / CANONICAL_SETTLEMENT_FEED_FILENAME,
    )
    core.discover_current_event_from_raw(
        raw_text=json.dumps(complete_payload()), received_monotonic_ns=1,
        received_utc="2026-09-04T15:30:00Z", now_timestamp_ms=NOW_MS,
    )
    core.discover_current_event_from_raw(
        raw_text=json.dumps(complete_payload()), received_monotonic_ns=2,
        received_utc="2026-09-04T16:30:00Z", now_timestamp_ms=NOW_MS + 3_600_000,
    )
    ticker = "KXBTCD-26SEP0416-T110000.00"
    assert ticker in core.pending_live_shadow_settlement_tickers()
    body = json.dumps({"market": {"ticker": ticker, "status": "finalized", "result": "yes"}})
    assert fetch_kalshi_final_market_settlement(
        session=FakeSession(FakeResponse(status_code=200, text=body)), core=core,
        market_ticker=ticker, monotonic_ns=iter((10, 20)).__next__,
        utc_now_text=lambda: "2026-09-04T16:31:00Z",
    ) is True
    settlements = read_live_shadow_settlements(
        path=tmp_path / CANONICAL_SETTLEMENT_FEED_FILENAME, run_id="runtime-a",
    )
    assert settlements[0].official_market_result == "yes"
    assert ticker not in core.pending_live_shadow_settlement_tickers()
    core.close()
