from decimal import Decimal

import pytest

from src.kxbtcd_independent_btc_historical_materialization import (
    FROZEN_AUDIT_DESIGN_FINGERPRINT,
    CoinbaseMinute,
    KrakenTrade,
    Live19CState,
    audit_design_fingerprint,
    completed_minute_bounds,
    kraken_live_bbo_publication_ages_seconds,
    lookback_minute_bounds,
    materialization_row,
    parse_coinbase_candles_payload,
    parse_kraken_posttrade_payload,
    select_kraken_minute,
    summarize_materialization,
    validate_audit_design,
)


def test_frozen_19d_a_design_is_outcome_blind_and_unchanged():
    validate_audit_design()
    assert audit_design_fingerprint() == FROZEN_AUDIT_DESIGN_FINGERPRINT
    assert FROZEN_AUDIT_DESIGN_FINGERPRINT == (
        "023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c"
    )


def test_completed_minute_and_exact_five_minute_lookback_never_use_current_minute():
    as_of = "2026-08-16T01:05:38.123456Z"
    assert completed_minute_bounds(as_of) == (
        "2026-08-16T01:04:00.000000Z",
        "2026-08-16T01:05:00.000000Z",
    )
    assert lookback_minute_bounds(as_of) == (
        "2026-08-16T00:59:00.000000Z",
        "2026-08-16T01:00:00.000000Z",
    )


def test_coinbase_candle_parser_uses_documented_close_and_preserves_raw_ref():
    parsed = parse_coinbase_candles_payload(
        [[1786842240, 119000.0, 119100.0, 119020.0, 119080.5, 12.0]],
        raw_observation_ref="raw:coinbase:s:r",
    )
    minute = parsed["2026-08-16T01:04:00.000000Z"]
    assert minute.close_price == Decimal("119080.5")
    assert minute.raw_observation_refs == ("raw:coinbase:s:r",)


def test_kraken_parser_and_selection_require_publication_by_decision_time():
    payload = {
        "error": [],
        "result": {
            "last_ts": "2026-08-16T01:04:59.900000Z",
            "count": 3,
            "trades": [
                {
                    "trade_id": "a",
                    "price": "119000",
                    "quantity": "0.1",
                    "symbol": "BTC/USD",
                    "trade_ts": "2026-08-16T01:04:10.000000Z",
                    "publication_ts": "2026-08-16T01:04:10.100000Z",
                },
                {
                    "trade_id": "b",
                    "price": "119100",
                    "quantity": "0.1",
                    "symbol": "BTC/USD",
                    "trade_ts": "2026-08-16T01:04:59.000000Z",
                    "publication_ts": "2026-08-16T01:05:01.000000Z",
                },
                {
                    "trade_id": "c",
                    "price": "119200",
                    "quantity": "0.1",
                    "symbol": "BTC/USD",
                    "trade_ts": "2026-08-16T01:04:59.900000Z",
                    "publication_ts": "2026-08-16T01:05:45.000000Z",
                },
            ],
        },
    }
    trades, last_ts, count = parse_kraken_posttrade_payload(payload)
    assert count == 3
    assert last_ts == "2026-08-16T01:04:59.900000Z"

    selected = select_kraken_minute(
        trades,
        minute_start_utc="2026-08-16T01:04:00Z",
        minute_end_utc="2026-08-16T01:05:00Z",
        as_of_utc="2026-08-16T01:05:38Z",
        raw_observation_refs=["raw:kraken:s:r"],
    )
    # Trade c happened in the minute but was not published by the decision state.
    # Trade b is therefore the latest causally available trade.
    assert selected.selected_price == Decimal("119100")
    assert selected.selected_trade_ts == "2026-08-16T01:04:59.000000Z"
    assert selected.publication_lag_ms == pytest.approx(2000.0)
    assert selected.publication_age_at_decision_ms == pytest.approx(37000.0)


def test_kraken_live_bbo_freshness_uses_older_side_not_newer_side():
    payload = {
        "error": [],
        "result": {
            "bids": [
                {"price": "119000", "qty": "1", "count": 1, "publication_ts": "2026-08-16T01:05:20Z"}
            ],
            "asks": [
                {"price": "119010", "qty": "1", "count": 1, "publication_ts": "2026-08-16T01:05:37.800000Z"}
            ],
        },
    }
    bid_age, ask_age, conservative = kraken_live_bbo_publication_ages_seconds(
        as_of_utc="2026-08-16T01:05:38Z",
        raw_payload=payload,
    )
    assert bid_age == pytest.approx(18.0)
    assert ask_age == pytest.approx(0.2)
    assert conservative == pytest.approx(18.0)


def _live(index: int) -> Live19CState:
    minute = index % 60
    as_of = f"2026-08-16T01:{minute:02d}:38.000000Z"
    return Live19CState(
        snapshot_index=index,
        as_of_utc=as_of,
        coinbase_price=Decimal("119005"),
        kraken_price=Decimal("119006"),
        coinbase_local_age_seconds=1.0,
        kraken_local_age_seconds=1.1,
        coinbase_source_event_time_utc=as_of,
        kraken_source_event_time_utc=as_of,
        coinbase_raw_observation_ref=f"raw:cb:s:{index}",
        kraken_raw_observation_ref=f"raw:kr:s:{index}",
    )


def test_materialization_row_keeps_sources_separate_and_does_not_create_candidate_features():
    live = _live(0)
    current_start, _ = completed_minute_bounds(live.as_of_utc)
    lookback_start, _ = lookback_minute_bounds(live.as_of_utc)
    cb_current = CoinbaseMinute(current_start, Decimal("119000"), ("raw:cbh:s:c",))
    cb_lookback = CoinbaseMinute(lookback_start, Decimal("118900"), ("raw:cbh:s:l",))
    kr_current = select_kraken_minute(
        [KrakenTrade(Decimal("119002"), "2026-08-16T00:59:50Z", "2026-08-16T00:59:50.100000Z")],
        minute_start_utc=current_start,
        minute_end_utc="2026-08-16T01:00:00Z",
        as_of_utc=live.as_of_utc,
        raw_observation_refs=["raw:krh:s:c"],
    )
    kr_lookback = select_kraken_minute(
        [KrakenTrade(Decimal("118902"), "2026-08-16T00:54:50Z", "2026-08-16T00:54:50.100000Z")],
        minute_start_utc=lookback_start,
        minute_end_utc="2026-08-16T00:55:00Z",
        as_of_utc=live.as_of_utc,
        raw_observation_refs=["raw:krh:s:l"],
    )
    row = materialization_row(
        live=live,
        coinbase_current=cb_current,
        coinbase_lookback=cb_lookback,
        kraken_current=kr_current,
        kraken_lookback=kr_lookback,
        coinbase_live_source_event_age_seconds_19c=0.4,
        kraken_live_best_bid_publication_age_seconds_19c=0.5,
        kraken_live_best_ask_publication_age_seconds_19c=0.2,
        kraken_live_conservative_bbo_publication_age_seconds_19c=0.5,
    )
    assert row["historically_reconstructible_five_minute_pair"] is True
    assert row["exclusion_reasons"] == []
    assert "consensus_price" not in row
    assert "r_5m" not in row
    assert "d_BTC" not in row
    assert "outcome" not in row

def test_kraken_parser_normalizes_blank_last_ts_when_page_does_not_need_pagination():
    payload = {
        "error": [],
        "result": {
            "last_ts": "",
            "count": 0,
            "trades": [],
        },
    }
    trades, last_ts, count = parse_kraken_posttrade_payload(payload)
    assert trades == ()
    assert last_ts is None
    assert count == 0
