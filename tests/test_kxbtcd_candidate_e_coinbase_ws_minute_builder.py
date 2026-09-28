from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_coinbase_rest_recovery import (
    build_recovery_evidence,
)

from src.kxbtcd_candidate_e_coinbase_ws_minute_builder import (
    CoinbaseMinuteBuilder,
    CoinbaseMinuteBuilderError,
)


MINUTE = 1788487200  # 2026-09-04T02:00:00Z


def _last_match(
    trade_id=100,
    sequence=1000,
    time="2026-09-04T02:00:20Z",
    price="80870.00",
):
    return {
        "type": "last_match",
        "trade_id": trade_id,
        "sequence": sequence,
        "product_id": "BTC-USD",
        "time": time,
        "price": price,
        "size": "0.01",
        "side": "sell",
    }


def _match(
    trade_id,
    sequence,
    time,
    price,
):
    return {
        "type": "match",
        "trade_id": trade_id,
        "sequence": sequence,
        "product_id": "BTC-USD",
        "time": time,
        "price": price,
        "size": "0.01",
        "side": "sell",
    }


def _heartbeat(
    last_trade_id,
    sequence,
    time="2026-09-04T02:01:01Z",
):
    return {
        "type": "heartbeat",
        "sequence": sequence,
        "last_trade_id": last_trade_id,
        "product_id": "BTC-USD",
        "time": time,
    }


def _rest_trade(trade_id, time, price):
    return {
        "trade_id": trade_id,
        "time": time,
        "price": price,
        "size": "0.01",
        "side": "sell",
    }


def test_last_match_seed_can_be_exact_minute_close():
    b = CoinbaseMinuteBuilder()

    b.apply_ws(
        _last_match(),
        received_monotonic_ns=1_000_000_000,
    )
    b.apply_ws(
        _heartbeat(100, 1001),
        received_monotonic_ns=2_000_000_000,
    )

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=2_500_000_000,
    )

    assert result["status"] == "AVAILABLE"
    state = result["state"]
    assert state.close_price == Decimal("80870.00")
    assert state.close_trade_id == 100


def test_last_source_trade_inside_minute_wins():
    b = CoinbaseMinuteBuilder()

    b.apply_ws(
        _last_match(price="80870.00"),
        received_monotonic_ns=1,
    )
    b.apply_ws(
        _match(
            101,
            1001,
            "2026-09-04T02:00:40Z",
            "80871.00",
        ),
        received_monotonic_ns=2,
    )
    b.apply_ws(
        _match(
            102,
            1002,
            "2026-09-04T02:00:59.900000Z",
            "80872.00",
        ),
        received_monotonic_ns=3,
    )
    b.apply_ws(
        _heartbeat(102, 1003),
        received_monotonic_ns=1_000_000_000,
    )

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )

    assert result["status"] == "AVAILABLE"
    assert result["state"].close_price == Decimal("80872.00")
    assert result["state"].close_trade_id == 102


def test_exact_minute_boundary_belongs_to_next_minute():
    b = CoinbaseMinuteBuilder()

    b.apply_ws(
        _last_match(
            time="2026-09-04T02:00:55Z",
            price="80870",
        ),
        received_monotonic_ns=1,
    )
    b.apply_ws(
        _match(
            101,
            1001,
            "2026-09-04T02:01:00Z",
            "80899",
        ),
        received_monotonic_ns=2,
    )
    b.apply_ws(
        _heartbeat(101, 1002),
        received_monotonic_ns=1_000_000_000,
    )

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )

    assert result["status"] == "AVAILABLE"
    assert result["state"].close_price == Decimal("80870")


def test_trade_id_gap_fails_closed_until_exact_rest_recovery():
    b = CoinbaseMinuteBuilder()

    b.apply_ws(
        _last_match(),
        received_monotonic_ns=1,
    )
    b.apply_ws(
        _match(
            102,
            1002,
            "2026-09-04T02:00:50Z",
            "80872",
        ),
        received_monotonic_ns=2,
    )
    b.apply_ws(
        _heartbeat(102, 1003),
        received_monotonic_ns=1_000_000_000,
    )

    blocked = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )
    assert blocked["status"] == "RECOVERY_REQUIRED"

    incomplete_evidence = build_recovery_evidence(
        pages=[[]],
        start_exclusive_trade_id=100,
        target_inclusive_trade_id=102,
    )

    incomplete = b.apply_rest_recovery(
        incomplete_evidence
    )
    assert incomplete["status"] == "RECOVERY_INCOMPLETE"

    recovered_evidence = build_recovery_evidence(
        pages=[[
            _rest_trade(
                102,
                "2026-09-04T02:00:50Z",
                "80872",
            ),
            _rest_trade(
                101,
                "2026-09-04T02:00:40Z",
                "80871",
            ),
            _rest_trade(
                100,
                "2026-09-04T02:00:20Z",
                "80870",
            ),
        ]],
        start_exclusive_trade_id=100,
        target_inclusive_trade_id=102,
    )

    recovered = b.apply_rest_recovery(
        recovered_evidence
    )
    assert recovered["status"] == "RECOVERY_COMPLETE"

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )
    assert result["status"] == "AVAILABLE"
    assert result["state"].close_trade_id == 102


def test_heartbeat_can_reveal_missing_matches():
    b = CoinbaseMinuteBuilder()

    b.apply_ws(
        _last_match(trade_id=200),
        received_monotonic_ns=1,
    )
    b.apply_ws(
        _heartbeat(202, 1001),
        received_monotonic_ns=1_000_000_000,
    )

    blocked = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )
    assert blocked["status"] == "RECOVERY_REQUIRED"

    recovered_evidence = build_recovery_evidence(
        pages=[[
            _rest_trade(
                202,
                "2026-09-04T02:00:59Z",
                "80872",
            ),
            _rest_trade(
                201,
                "2026-09-04T02:00:40Z",
                "80871",
            ),
            _rest_trade(
                200,
                "2026-09-04T02:00:20Z",
                "80870",
            ),
        ]],
        start_exclusive_trade_id=200,
        target_inclusive_trade_id=202,
    )

    recovered = b.apply_rest_recovery(
        recovered_evidence
    )

    assert recovered["status"] == "RECOVERY_COMPLETE"

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )
    assert result["status"] == "AVAILABLE"
    assert result["state"].close_trade_id == 202
    assert result["state"].close_price == Decimal("80872")


def test_zero_trade_minute_is_missing_not_carry_forward():
    b = CoinbaseMinuteBuilder()

    b.apply_ws(
        _last_match(
            time="2026-09-04T01:59:55Z",
            price="80860",
        ),
        received_monotonic_ns=1,
    )
    b.apply_ws(
        _heartbeat(100, 1001),
        received_monotonic_ns=1_000_000_000,
    )

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )

    assert result["status"] == "NO_TRADES_IN_MINUTE"


def test_stale_heartbeat_disables_completed_minute():
    b = CoinbaseMinuteBuilder()

    b.apply_ws(
        _last_match(),
        received_monotonic_ns=1,
    )
    b.apply_ws(
        _heartbeat(100, 1001),
        received_monotonic_ns=1_000_000_000,
    )

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=4_000_000_001,
    )

    assert result["status"] == "HEARTBEAT_STALE"


def test_schema_and_sequence_fail_closed():
    b = CoinbaseMinuteBuilder()

    with pytest.raises(CoinbaseMinuteBuilderError):
        b.apply_ws(
            _match(
                101,
                1001,
                "2026-09-04T02:00:30Z",
                "80870",
            ),
            received_monotonic_ns=1,
        )

    b.apply_ws(
        _last_match(),
        received_monotonic_ns=2,
    )

    b.apply_ws(
        _heartbeat(100, 999),
        received_monotonic_ns=1_000_000_000,
    )

    result = b.completed_minute(
        minute_start_s=MINUTE,
        now_monotonic_ns=1_500_000_000,
    )
    assert result["status"] == "SEQUENCE_UNHEALTHY"

    wrong = CoinbaseMinuteBuilder()
    bad = _last_match()
    bad["product_id"] = "ETH-USD"

    with pytest.raises(CoinbaseMinuteBuilderError):
        wrong.apply_ws(
            bad,
            received_monotonic_ns=1,
        )
