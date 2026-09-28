from decimal import Decimal

import pytest

from src.kxbtcd_candidate_e_coinbase_ws_minute_builder import (
    CoinbaseMinuteBuilder,
    CoinbaseMinuteBuilderError,
    _rest_trade,
    _ws_trade,
)


def _ws(
    *,
    trade_id=100,
    sequence=500,
    price="80835.85",
    size="0.00000012",
    side="buy",
    time="2026-09-04T04:00:55.243769Z",
):
    return _ws_trade({
        "type": "match",
        "product_id": "BTC-USD",
        "trade_id": trade_id,
        "sequence": sequence,
        "price": price,
        "size": size,
        "side": side,
        "time": time,
    })


def _rest(
    *,
    trade_id=100,
    price="80835.85000000",
    size="0.00000012",
    side="buy",
    time="2026-09-04T04:00:55.243770Z",
):
    return _rest_trade({
        "trade_id": trade_id,
        "price": price,
        "size": size,
        "side": side,
        "time": time,
    })


def test_trade_parsers_preserve_size_and_side():
    ws = _ws()
    rest = _rest()

    assert ws.size == Decimal("0.00000012")
    assert ws.side == "buy"

    assert rest.size == Decimal("0.00000012")
    assert rest.side == "buy"


def test_ws_then_compatible_rest_is_corroborative_noop():
    builder = CoinbaseMinuteBuilder()

    ws = _ws()
    rest = _rest()

    assert builder._record_trade(ws) is True
    assert builder._record_trade(rest) is False

    # Critical: REST did not replace the canonical WS object.
    assert builder._trade_by_id[100] is ws
    assert (
        builder._trade_by_id[100].source_time_us
        == ws.source_time_us
    )
    assert (
        builder._trade_by_id[100].evidence_source
        == "coinbase_ws_match"
    )


def test_rest_then_compatible_ws_is_corroborative_noop():
    builder = CoinbaseMinuteBuilder()

    rest = _rest()
    ws = _ws()

    assert builder._record_trade(rest) is True
    assert builder._record_trade(ws) is False

    # First accepted evidence remains canonical in either direction.
    assert builder._trade_by_id[100] is rest
    assert (
        builder._trade_by_id[100].evidence_source
        == "coinbase_rest_recovery"
    )


def test_two_microsecond_cross_transport_difference_fails():
    builder = CoinbaseMinuteBuilder()

    builder._record_trade(
        _ws(
            time="2026-09-04T04:00:55.243769Z",
        )
    )

    with pytest.raises(
        CoinbaseMinuteBuilderError
    ):
        builder._record_trade(
            _rest(
                time="2026-09-04T04:00:55.243771Z",
            )
        )


def test_one_microsecond_crossing_minute_boundary_fails():
    builder = CoinbaseMinuteBuilder()

    builder._record_trade(
        _ws(
            time="2026-09-04T04:00:59.999999Z",
        )
    )

    with pytest.raises(
        CoinbaseMinuteBuilderError
    ):
        builder._record_trade(
            _rest(
                time="2026-09-04T04:01:00.000000Z",
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price", "80835.86"),
        ("size", "0.00000013"),
        ("side", "sell"),
    ],
)
def test_cross_transport_economic_conflict_fails(
    field,
    value,
):
    builder = CoinbaseMinuteBuilder()

    builder._record_trade(
        _ws()
    )

    kwargs = {
        "price": "80835.85000000",
        "size": "0.00000012",
        "side": "buy",
    }
    kwargs[field] = value

    with pytest.raises(
        CoinbaseMinuteBuilderError
    ):
        builder._record_trade(
            _rest(**kwargs)
        )


def test_same_transport_duplicate_remains_exact():
    builder = CoinbaseMinuteBuilder()

    first = _ws(
        time="2026-09-04T04:00:55.243769Z",
    )

    same = _ws(
        time="2026-09-04T04:00:55.243769Z",
    )

    builder._record_trade(first)
    assert builder._record_trade(same) is False

    different = _ws(
        time="2026-09-04T04:00:55.243770Z",
    )

    with pytest.raises(
        CoinbaseMinuteBuilderError
    ):
        builder._record_trade(different)
