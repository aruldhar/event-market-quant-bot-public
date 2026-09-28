from datetime import datetime, timezone

from analyze_kxbtc15m_h1 import Quote, efficiency_on_grid, market_close_utc, state_label


def quote(seconds, bid, ask):
    base = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    return Quote(base.replace(second=seconds), "T", bid, ask, 1 - ask, 1 - bid)


def test_ticker_close_is_converted_from_eastern_to_utc():
    assert market_close_utc("KXBTC15M-26AUG121430-30") == datetime(
        2026, 8, 12, 18, 30, tzinfo=timezone.utc
    )


def test_frozen_analysis_rejects_dates_outside_august_2026():
    try:
        market_close_utc("KXBTC15M-26SEP121430-30")
    except ValueError as error:
        assert "only August 2026" in str(error)
    else:
        raise AssertionError("Expected the frozen analysis to reject September")


def test_directional_efficiency_identifies_monotone_rise():
    quotes = [quote(second, 0.10 + second / 100, 0.12 + second / 100) for second in range(0, 21, 5)]
    value = efficiency_on_grid(quotes, "YES", quotes[0].time, quotes[-1].time)
    assert value == 1.0
    assert state_label(value) == "rising"


def test_directional_efficiency_identifies_whipsaw():
    values = [0.10, 0.20, 0.10, 0.20, 0.10]
    quotes = [quote(second, value, value + 0.02) for second, value in zip(range(0, 21, 5), values)]
    value = efficiency_on_grid(quotes, "YES", quotes[0].time, quotes[-1].time)
    assert value == 0.0
    assert state_label(value) == "fluctuating"


def test_state_thresholds_are_fixed():
    assert state_label(-0.35) == "falling"
    assert state_label(-0.349) == "fluctuating"
    assert state_label(0.349) == "fluctuating"
    assert state_label(0.35) == "rising"
