from __future__ import annotations

from decimal import Decimal
import json

import pytest

from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    EXPECTED_BTC_SHA256,
    EXPECTED_PAID_TICKS_SHA256,
    EXPECTED_REPLAY_SUMMARY_SHA256,
    EXPECTED_ROLE_ANCHOR_STATE_COUNT,
    EXPECTED_STRUCTURAL_TICKER_COUNT,
    OutcomeBlindBindingError,
    _materialization_firewall,
    canonical_json_bytes,
    derive_structural_universe,
    iso_utc_to_epoch_ms,
    parse_kxbtcd_threshold_ticker,
)


def _synthetic_full_ladder_tickers() -> list[str]:
    counts = {
        "KXBTCD-26JUL1013": 78,
        "KXBTCD-26JUL1014": 188,
        "KXBTCD-26JUL1015": 188,
        "KXBTCD-26JUL1016": 169,
    }
    out: list[str] = []
    base = 60_000
    for event, count in counts.items():
        for i in range(count):
            out.append(f"{event}-T{base + i * 100}.99")
        base += 30_000
    return out


def test_frozen_local_source_hashes_are_exact() -> None:
    assert EXPECTED_BTC_SHA256 == "022f6c6ce1b697bc67f7137f73e3f18cc0fe0198b347e5154a3063107299fb12"
    assert EXPECTED_PAID_TICKS_SHA256 == "43e9c5d99fb4001b866ae3e60021c8c10123dc1fb6248df96084446face68509"
    assert EXPECTED_REPLAY_SUMMARY_SHA256 == "b37ba7132baf086887e4b33e7c11e9de59decc5f0b387d7e6e5352a2570ebb48"


def test_parse_threshold_ticker_is_exact_decimal() -> None:
    event, strike = parse_kxbtcd_threshold_ticker("KXBTCD-26JUL1013-T64099.99")
    assert event == "KXBTCD-26JUL1013"
    assert strike == Decimal("64099.99")


def test_parse_threshold_ticker_fails_closed() -> None:
    with pytest.raises(OutcomeBlindBindingError):
        parse_kxbtcd_threshold_ticker("KXBTCD-26JUL1013")


def test_utc_timestamp_conversion_is_exact_milliseconds() -> None:
    assert iso_utc_to_epoch_ms("1970-01-01T00:00:01.500Z") == 1500
    assert iso_utc_to_epoch_ms("1970-01-01T00:01:00+00:00") == 60_000


def test_non_utc_timestamp_fails_closed() -> None:
    with pytest.raises(OutcomeBlindBindingError):
        iso_utc_to_epoch_ms("2026-07-10T16:05:00-05:00")


def test_full_ladder_maps_to_exactly_twenty_structural_tickers() -> None:
    rows = derive_structural_universe(_synthetic_full_ladder_tickers())
    assert len(rows) == EXPECTED_STRUCTURAL_TICKER_COUNT == 20
    by_event: dict[str, list[dict]] = {}
    for row in rows:
        by_event.setdefault(str(row["event_ticker"]), []).append(row)
    assert set(by_event) == {
        "KXBTCD-26JUL1013",
        "KXBTCD-26JUL1014",
        "KXBTCD-26JUL1015",
        "KXBTCD-26JUL1016",
    }
    for event_rows in by_event.values():
        assert [r["structural_role"] for r in event_rows] == ["q10", "q30", "q50", "q70", "q90"]


def test_structural_universe_rejects_missing_full_ladder_market() -> None:
    tickers = _synthetic_full_ladder_tickers()
    with pytest.raises(OutcomeBlindBindingError):
        derive_structural_universe(tickers[:-1])


def test_materialization_firewall_rejects_realized_pnl_key() -> None:
    payload = {
        "pnl": "1.00",
        "safety": {
            "outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "candidate_e_refit": False,
            "network_requests": 0,
            "predexon_paid_purchases": 0,
            "orders_placed": 0,
            "paper_broker": False,
            "demo_execution": False,
            "real_money_execution": False,
        },
    }
    with pytest.raises(OutcomeBlindBindingError):
        _materialization_firewall(payload)


def test_materialization_firewall_allows_position_only_settlement_fallback_quantity() -> None:
    payload = {
        "scenario": {
            "settlement_fallback_quantity": "0.25",
            "matched_hold_settlement_quantity": "1",
        },
        "safety": {
            "outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "candidate_e_refit": False,
            "network_requests": 0,
            "predexon_paid_purchases": 0,
            "orders_placed": 0,
            "paper_broker": False,
            "demo_execution": False,
            "real_money_execution": False,
        },
    }
    _materialization_firewall(payload)


def test_canonical_json_is_deterministic() -> None:
    left = canonical_json_bytes({"b": 2, "a": 1})
    right = canonical_json_bytes({"a": 1, "b": 2})
    assert left == right == b'{"a":1,"b":2}\n'


def test_frozen_role_anchor_state_count_is_120() -> None:
    assert EXPECTED_ROLE_ANCHOR_STATE_COUNT == 4 * 6 * 5 == 120
