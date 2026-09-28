from src.kxbtcd_candidate_e_coinbase_cross_transport_identity import (
    compare_ws_rest_trade_identity,
)


def _trade(
    *,
    trade_id=100,
    price="80923.31",
    size="0.00000026",
    side="buy",
    time="2026-09-04T03:54:47.742718Z",
):
    return {
        "trade_id": trade_id,
        "price": price,
        "size": size,
        "side": side,
        "time": time,
    }


def test_exact_cross_transport_identity_matches():
    result = compare_ws_rest_trade_identity(
        _trade(),
        _trade(
            price="80923.31000000",
            size="0.000000260000",
        ),
    )

    assert result.compatible is True
    assert result.timestamp_delta_us == 0


def test_one_microsecond_same_minute_is_compatible():
    result = compare_ws_rest_trade_identity(
        _trade(
            time="2026-09-04T03:54:47.742718Z",
        ),
        _trade(
            price="80923.31000000",
            time="2026-09-04T03:54:47.742719Z",
        ),
    )

    assert result.compatible is True
    assert result.timestamp_delta_us == 1
    assert (
        result.timestamp_within_tolerance
        is True
    )
    assert result.same_utc_minute is True


def test_two_microseconds_fails_closed():
    result = compare_ws_rest_trade_identity(
        _trade(
            time="2026-09-04T03:54:47.742718Z",
        ),
        _trade(
            time="2026-09-04T03:54:47.742720Z",
        ),
    )

    assert result.compatible is False
    assert (
        result.timestamp_within_tolerance
        is False
    )


def test_one_microsecond_crossing_minute_boundary_fails_closed():
    result = compare_ws_rest_trade_identity(
        _trade(
            time="2026-09-04T03:54:59.999999Z",
        ),
        _trade(
            time="2026-09-04T03:55:00.000000Z",
        ),
    )

    assert result.timestamp_delta_us == 1
    assert (
        result.timestamp_within_tolerance
        is True
    )
    assert result.same_utc_minute is False
    assert result.compatible is False


def test_economic_identity_mismatch_fails_closed():
    price = compare_ws_rest_trade_identity(
        _trade(),
        _trade(price="80923.32"),
    )
    assert price.compatible is False
    assert price.price_equal is False

    size = compare_ws_rest_trade_identity(
        _trade(),
        _trade(size="0.00000027"),
    )
    assert size.compatible is False
    assert size.size_equal is False

    side = compare_ws_rest_trade_identity(
        _trade(),
        _trade(side="sell"),
    )
    assert side.compatible is False
    assert side.side_equal is False

    trade_id = compare_ws_rest_trade_identity(
        _trade(),
        _trade(trade_id=101),
    )
    assert trade_id.compatible is False
    assert trade_id.trade_id_equal is False
