from decimal import Decimal
from types import SimpleNamespace

import pytest

import src.kxbtcd_candidate_e_prospective_live_collector as live_collector_core

from src.kxbtcd_candidate_e_prospective_live_collector import (
    CoinbaseMinuteClose,
    KalshiBookCache,
    build_ladders_from_markets,
    choose_smoke_ladder,
    completed_minute_target,
    make_snapshot_command,
    make_subscribe_command,
    parse_coinbase_completed_candle,
    select_live_signals,
)

def _markets(close="2026-09-04T02:00:00Z"):
    rows = []
    for i, strike in enumerate((111999.99, 112099.99, 112199.99, 112299.99, 112399.99, 112499.99, 112599.99, 112699.99, 112799.99, 112899.99, 112999.99)):
        rows.append({
            "ticker": f"KXBTCD-26SEP0321-T{strike}",
            "event_ticker": "KXBTCD-26SEP0321",
            "status": "active",
            "close_time": close,
            "floor_strike": strike,
        })
    return {"markets": rows, "cursor": ""}

def _snapshot(ticker, seq, yes=("0.40", "10.00"), no=("0.59", "12.00")):
    return {
        "type": "orderbook_snapshot",
        "sid": 2,
        "seq": seq,
        "msg": {
            "market_ticker": ticker,
            "yes_dollars_fp": [[yes[0], yes[1]]],
            "no_dollars_fp": [[no[0], no[1]]],
        },
    }

def test_snapshot_derives_executable_yes_ask():
    ticker = "KXBTCD-26SEP0321-T112499.99"
    cache = KalshiBookCache([ticker])
    result = cache.apply_message(_snapshot(ticker, 1))
    assert result["ready"] is True
    state = cache.books[ticker].to_book_state(123)
    assert state.yes_bids[0].price == Decimal("0.40")
    assert state.yes_asks[0].price == Decimal("0.41")
    assert state.yes_asks[0].quantity == Decimal("12.00")

def test_snapshot_normalizes_omitted_side_only():
    ticker = "KXBTCD-26SEP0321-T112499.99"

    cache = KalshiBookCache([ticker])
    snapshot = _snapshot(ticker, 1)
    del snapshot["msg"]["no_dollars_fp"]

    result = cache.apply_message(snapshot)
    assert result["ready"] is True
    assert cache.books[ticker].no_bids == {}

    state = cache.books[ticker].to_book_state(123)
    assert state.yes_bids
    assert state.yes_asks == ()

    # Omission is valid; an explicitly malformed/null side is not.
    bad_cache = KalshiBookCache([ticker])
    bad_snapshot = _snapshot(ticker, 1)
    bad_snapshot["msg"]["no_dollars_fp"] = None

    with pytest.raises(Exception):
        bad_cache.apply_message(bad_snapshot)


def test_delta_gap_invalidates_until_new_snapshot():
    ticker = "KXBTCD-26SEP0321-T112499.99"
    cache = KalshiBookCache([ticker])
    cache.apply_message(_snapshot(ticker, 10))
    gap = cache.apply_message({
        "type": "orderbook_delta",
        "sid": 2,
        "seq": 12,
        "msg": {
            "market_ticker": ticker,
            "price_dollars": "0.40",
            "delta_fp": "1.00",
            "side": "yes",
            "ts_ms": 1,
        },
    })
    assert gap["gap"] is True
    assert cache.all_ready() is False
    cache.apply_message(_snapshot(ticker, 13))
    assert cache.all_ready() is True

def test_delta_updates_quantity_and_rejects_negative():
    ticker = "KXBTCD-26SEP0321-T112499.99"
    cache = KalshiBookCache([ticker])
    cache.apply_message(_snapshot(ticker, 1))
    cache.apply_message({
        "type": "orderbook_delta",
        "sid": 2,
        "seq": 2,
        "msg": {"market_ticker": ticker, "price_dollars": "0.40", "delta_fp": "-3.00", "side": "yes", "ts_ms": 2},
    })
    assert cache.books[ticker].yes_bids[Decimal("0.40")] == Decimal("7.00")
    with pytest.raises(Exception):
        cache.apply_message({
            "type": "orderbook_delta",
            "sid": 2,
            "seq": 3,
            "msg": {"market_ticker": ticker, "price_dollars": "0.40", "delta_fp": "-8.00", "side": "yes", "ts_ms": 3},
        })

def test_coinbase_exact_completed_minute_only():
    start, end = completed_minute_target(1200)
    assert (start, end) == (1140, 1200)
    state = parse_coinbase_completed_candle(
        [[1140, 100, 102, 101, 101.5, 12]],
        target_start_s=1140,
        available_monotonic_ns=999,
        raw_received_utc="2026-09-04T00:00:00Z",
    )
    assert state.close_price == Decimal("101.5")
    with pytest.raises(Exception):
        parse_coinbase_completed_candle(
            [[1080, 100, 102, 101, 101.5, 12]],
            target_start_s=1140,
            available_monotonic_ns=999,
            raw_received_utc="2026-09-04T00:00:00Z",
        )

def test_commands_are_read_only():
    s = make_subscribe_command(["KXBTCD-26SEP0321-T112499.99"])
    assert s["cmd"] == "subscribe"
    assert s["params"]["channels"] == ["orderbook_delta"]
    snap = make_snapshot_command(7, ["KXBTCD-26SEP0321-T112499.99"], 99)
    assert snap["cmd"] == "update_subscription"
    assert snap["params"]["action"] == "get_snapshot"

def test_live_signal_uses_frozen_point02_threshold_and_full_window():
    ladders = build_ladders_from_markets(_markets())
    event = ladders[0]
    cache = KalshiBookCache([m.market_ticker for m in event.markets])
    seq = 0
    for market in event.markets:
        seq += 1
        cache.apply_message(_snapshot(market.market_ticker, seq))
    assert cache.all_ready()
    btc = CoinbaseMinuteClose(
        minute_start_s=100,
        minute_end_s=160,
        close_price=Decimal("112500"),
        available_monotonic_ns=1,
        raw_received_utc="2026-09-04T00:00:00Z",
    )
    # 30 minutes before the synthetic close.
    decision_ms = event.close_timestamp_ms - 30 * 60 * 1000
    result = select_live_signals(
        event=event,
        cache=cache,
        btc_state=btc,
        decision_timestamp_ms=decision_ms,
    )
    assert result["status"] == "EVALUABLE"
    assert len(result["atm_window_tickers"]) == 11
    primary = result["primary_signal"]
    if primary is not None:
        assert primary.net_edge >= Decimal("0.02")

def test_git_ancestor_gate_is_stable_across_later_checkpoints(monkeypatch):
    results = iter([
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr=""),
        SimpleNamespace(returncode=128, stdout="", stderr="fatal"),
    ])

    monkeypatch.setattr(
        live_collector_core.subprocess,
        "run",
        lambda *args, **kwargs: next(results),
    )

    assert live_collector_core.git_commit_is_ancestor(".", "closed-zb") is True
    assert live_collector_core.git_commit_is_ancestor(".", "closed-zb") is False

    with pytest.raises(Exception):
        live_collector_core.git_commit_is_ancestor(".", "closed-zb")
