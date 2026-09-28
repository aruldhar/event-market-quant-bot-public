from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_b5_r2_live_reconnect import (
    B5R2ReconnectHarnessError,
    KALSHI_CONNECT_PING_INTERVAL_SECONDS,
    KALSHI_CONNECT_PING_TIMEOUT_SECONDS,
    LIVE_GENERATIONS_PER_SOURCE,
    LIVE_NETWORK_ENABLED_BY_DEFAULT,
    ReconnectGenerationController,
    validate_dwell_seconds,
)
from src.kxbtcd_candidate_e_prospective_live_collector import (
    EventLadder,
)
from src.kxbtcd_candidate_e_restart_gate_state_machine import GateStatus
from src.kxbtcd_candidate_e_restart_source_readiness import (
    KALSHI_WS_CLIENT_PING_INTERVAL_SECONDS,
    KALSHI_WS_PONG_TIMEOUT_SECONDS,
)
from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    LadderMarket,
)


SESSION = "runtime-session-b5-r2"


def event():
    return EventLadder(
        event_ticker="KXBTCD-26SEP0407",
        close_time_utc="2026-09-04T07:00:00Z",
        close_timestamp_ms=1788505200000,
        markets=(
            LadderMarket(
                event_ticker="KXBTCD-26SEP0407",
                market_ticker="KXBTCD-26SEP0407-T79999.99",
                strike=Decimal("80000"),
                strike_rank_zero_based=0,
                event_market_count=2,
                historical_structural_role=None,
            ),
            LadderMarket(
                event_ticker="KXBTCD-26SEP0407",
                market_ticker="KXBTCD-26SEP0407-T80999.99",
                strike=Decimal("81000"),
                strike_rank_zero_based=1,
                event_market_count=2,
                historical_structural_role=None,
            ),
        ),
    )


def snapshot(seq, ticker):
    return {
        "type": "orderbook_snapshot",
        "seq": seq,
        "msg": {
            "market_ticker": ticker,
            "yes_dollars_fp": [["0.50", "10"]],
            "no_dollars_fp": [["0.49", "10"]],
        },
    }


def make_kalshi_ready(binding):
    tickers = tuple(m.market_ticker for m in event().markets)
    binding.cache.apply_message({
        "type": "subscribed",
        "msg": {
            "channel": "orderbook_delta",
            "sid": 77,
        },
    })
    binding.cache.apply_message(snapshot(1, tickers[0]))
    binding.cache.apply_message(snapshot(2, tickers[1]))
    assert binding.cache.all_ready()


def test_live_network_is_disabled_by_default():
    assert LIVE_NETWORK_ENABLED_BY_DEFAULT is False
    assert LIVE_GENERATIONS_PER_SOURCE == 2


def test_frozen_kalshi_ping_pong_values_are_reused():
    assert (
        KALSHI_CONNECT_PING_INTERVAL_SECONDS
        == KALSHI_WS_CLIENT_PING_INTERVAL_SECONDS
        == 15
    )
    assert (
        KALSHI_CONNECT_PING_TIMEOUT_SECONDS
        == KALSHI_WS_PONG_TIMEOUT_SECONDS
        == 5
    )


@pytest.mark.parametrize("value", [5, 10, 30])
def test_dwell_seconds_accepts_bounded_values(value):
    assert validate_dwell_seconds(value) == value


@pytest.mark.parametrize("value", [0, 4, 31, 300, True])
def test_dwell_seconds_rejects_out_of_contract_values(value):
    with pytest.raises(B5R2ReconnectHarnessError):
        validate_dwell_seconds(value)


def test_coinbase_reconnect_increments_generation_and_replaces_builder():
    c = ReconnectGenerationController(SESSION)
    first = c.open_coinbase(opened_monotonic_ns=100)
    assert first.generation == 1

    c.close_coinbase(
        generation=first.generation,
        closed_monotonic_ns=200,
    )
    second = c.open_coinbase(opened_monotonic_ns=300)

    assert second.generation == 2
    assert first.builder is not second.builder
    assert c.current_coinbase_generation == 2


def test_coinbase_double_open_is_rejected():
    c = ReconnectGenerationController(SESSION)
    c.open_coinbase(opened_monotonic_ns=100)
    with pytest.raises(B5R2ReconnectHarnessError):
        c.open_coinbase(opened_monotonic_ns=200)


def test_coinbase_disconnect_blocks_immediately():
    c = ReconnectGenerationController(SESSION)
    first = c.open_coinbase(opened_monotonic_ns=100)
    c.close_coinbase(
        generation=1,
        closed_monotonic_ns=200,
    )

    evidence = c.evaluate_coinbase(
        binding=first,
        decision_epoch_s=1788503465,
        now_monotonic_ns=201,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "COINBASE_WEBSOCKET_NOT_CONNECTED"


def test_old_coinbase_builder_rejected_after_reconnect():
    c = ReconnectGenerationController(SESSION)
    first = c.open_coinbase(opened_monotonic_ns=100)
    c.close_coinbase(
        generation=1,
        closed_monotonic_ns=200,
    )
    second = c.open_coinbase(opened_monotonic_ns=300)
    assert second.generation == 2

    evidence = c.evaluate_coinbase(
        binding=first,
        decision_epoch_s=1788503465,
        now_monotonic_ns=301,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == (
        "COINBASE_STATE_NOT_FROM_CURRENT_CONNECTION_GENERATION"
    )


def test_new_coinbase_generation_does_not_inherit_old_state():
    c = ReconnectGenerationController(SESSION)
    first = c.open_coinbase(opened_monotonic_ns=100)
    first.builder.seeded = True
    c.close_coinbase(
        generation=1,
        closed_monotonic_ns=200,
    )
    second = c.open_coinbase(opened_monotonic_ns=300)

    assert second.builder.seeded is False
    assert second.builder.observed_trade_high_water is None
    assert second.builder.last_heartbeat_trade_id is None


def test_kalshi_reconnect_increments_generation_and_replaces_cache():
    c = ReconnectGenerationController(SESSION)
    tickers = tuple(m.market_ticker for m in event().markets)

    first = c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=100,
    )
    c.close_kalshi(
        generation=1,
        closed_monotonic_ns=200,
    )
    second = c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=300,
    )

    assert first.generation == 1
    assert second.generation == 2
    assert first.cache is not second.cache
    assert second.cache.resync_required is True
    assert second.cache.books == {}


def test_kalshi_double_open_is_rejected():
    c = ReconnectGenerationController(SESSION)
    tickers = tuple(m.market_ticker for m in event().markets)
    c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=100,
    )
    with pytest.raises(B5R2ReconnectHarnessError):
        c.open_kalshi(
            subscribed_tickers=tickers,
            opened_monotonic_ns=200,
        )


def test_current_kalshi_without_pong_is_blocked():
    c = ReconnectGenerationController(SESSION)
    tickers = tuple(m.market_ticker for m in event().markets)
    binding = c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=100,
    )
    make_kalshi_ready(binding)

    evidence = c.evaluate_kalshi(
        binding=binding,
        current_event=event(),
        discovery_runtime_session_id=SESSION,
        now_ms=1788503465000,
        now_monotonic_ns=200,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_CURRENT_CONNECTION_PONG_NOT_PROVEN"


def test_current_kalshi_ready_only_after_pong_and_full_snapshot():
    c = ReconnectGenerationController(SESSION)
    tickers = tuple(m.market_ticker for m in event().markets)
    binding = c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=100,
    )
    c.record_kalshi_pong(
        generation=1,
        pong_monotonic_ns=150,
    )

    before_snapshot = c.evaluate_kalshi(
        binding=binding,
        current_event=event(),
        discovery_runtime_session_id=SESSION,
        now_ms=1788503465000,
        now_monotonic_ns=200,
    )
    assert before_snapshot.status == GateStatus.BLOCKED
    assert before_snapshot.reason == "KALSHI_SUBSCRIPTION_SID_MISSING"

    make_kalshi_ready(binding)
    after_snapshot = c.evaluate_kalshi(
        binding=binding,
        current_event=event(),
        discovery_runtime_session_id=SESSION,
        now_ms=1788503465000,
        now_monotonic_ns=200,
    )
    assert after_snapshot.status == GateStatus.PASS


def test_kalshi_disconnect_blocks_immediately():
    c = ReconnectGenerationController(SESSION)
    tickers = tuple(m.market_ticker for m in event().markets)
    binding = c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=100,
    )
    make_kalshi_ready(binding)
    c.record_kalshi_pong(
        generation=1,
        pong_monotonic_ns=150,
    )
    c.close_kalshi(
        generation=1,
        closed_monotonic_ns=180,
    )

    evidence = c.evaluate_kalshi(
        binding=binding,
        current_event=event(),
        discovery_runtime_session_id=SESSION,
        now_ms=1788503465000,
        now_monotonic_ns=181,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == "KALSHI_WEBSOCKET_NOT_CONNECTED"


def test_old_kalshi_cache_rejected_after_reconnect():
    c = ReconnectGenerationController(SESSION)
    tickers = tuple(m.market_ticker for m in event().markets)

    first = c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=100,
    )
    make_kalshi_ready(first)
    c.record_kalshi_pong(
        generation=1,
        pong_monotonic_ns=150,
    )
    c.close_kalshi(
        generation=1,
        closed_monotonic_ns=180,
    )

    second = c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=200,
    )
    c.record_kalshi_pong(
        generation=2,
        pong_monotonic_ns=220,
    )

    evidence = c.evaluate_kalshi(
        binding=first,
        current_event=event(),
        discovery_runtime_session_id=SESSION,
        now_ms=1788503465000,
        now_monotonic_ns=230,
    )
    assert evidence.status == GateStatus.BLOCKED
    assert evidence.reason == (
        "KALSHI_CACHE_NOT_FROM_CURRENT_CONNECTION_GENERATION"
    )

    # Pong on generation 2 doesn't make the fresh generation-2 book ready.
    current = c.evaluate_kalshi(
        binding=second,
        current_event=event(),
        discovery_runtime_session_id=SESSION,
        now_ms=1788503465000,
        now_monotonic_ns=230,
    )
    assert current.status == GateStatus.BLOCKED
    assert current.reason == "KALSHI_SUBSCRIPTION_SID_MISSING"


def test_old_kalshi_pong_cannot_be_attached_to_new_generation():
    c = ReconnectGenerationController(SESSION)
    tickers = tuple(m.market_ticker for m in event().markets)
    c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=100,
    )
    c.record_kalshi_pong(
        generation=1,
        pong_monotonic_ns=150,
    )
    c.close_kalshi(
        generation=1,
        closed_monotonic_ns=180,
    )
    c.open_kalshi(
        subscribed_tickers=tickers,
        opened_monotonic_ns=200,
    )

    with pytest.raises(B5R2ReconnectHarnessError):
        c.record_kalshi_pong(
            generation=1,
            pong_monotonic_ns=220,
        )
