from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import (
    Fill,
    Snapshot,
    buy_with_budget,
    choose_lower_side,
    quadratic_fee,
    sell_quantity,
    simulate_policy,
)
from audit_kxbtc15m_raw_depth import ParsedBook


def book(*, yes, no):
    return ParsedBook(tuple(yes), tuple(no))


def test_quadratic_fee_is_conservatively_cent_rounded():
    fee = quadratic_fee([Fill(Decimal("0.50"), Decimal("100"))])
    assert fee == Decimal("1.75")


def test_budgeted_buy_never_exceeds_fixed_cash_budget():
    execution = buy_with_budget(
        [(Decimal("0.20"), Decimal("1000"))], Decimal("50.00")
    )
    assert execution.quantity > 0
    assert execution.buy_outflow <= Decimal("50.00")
    assert execution.buy_outflow + Decimal("0.21") > Decimal("50.00")


def test_buy_crosses_asks_lowest_price_first():
    execution = buy_with_budget(
        [(Decimal("0.10"), Decimal("2")), (Decimal("0.20"), Decimal("100"))],
        Decimal("1.00"),
    )
    assert execution.fills[0] == Fill(Decimal("0.10"), Decimal("2"))


def test_sell_crosses_bids_highest_price_first():
    execution = sell_quantity(
        [(Decimal("0.10"), Decimal("100")), (Decimal("0.30"), Decimal("2"))],
        Decimal("3"),
    )
    assert execution.fills[0] == Fill(Decimal("0.30"), Decimal("2"))
    assert execution.quantity == Decimal("3")


def test_choose_lower_executable_side():
    # YES ask = 1 - best NO bid = .30; NO ask = 1 - best YES bid = .70.
    value = book(
        yes=[(Decimal("0.30"), Decimal("100"))],
        no=[(Decimal("0.70"), Decimal("100"))],
    )
    assert choose_lower_side(value) == "YES"


def test_three_buy_ins_respect_same_100_dollar_maximum():
    start = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    values = []
    # YES asks: .30 then .24 then .19; later bid rises enough to exit.
    for seconds, yes_bid, no_bid in [
        (0, ".20", ".70"),
        (1, ".20", ".70"),
        (2, ".18", ".76"),
        (3, ".18", ".76"),
        (4, ".15", ".81"),
        (5, ".15", ".81"),
        (6, ".35", ".64"),
        (7, ".35", ".64"),
    ]:
        values.append(
            Snapshot(
                start + timedelta(seconds=seconds),
                str(seconds),
                book(
                    yes=[(Decimal(yes_bid), Decimal("10000"))],
                    no=[(Decimal(no_bid), Decimal("10000"))],
                ),
            )
        )
    result = simulate_policy(
        snapshots=values,
        decision_index=0,
        close_time=start + timedelta(minutes=15),
        winning_side="YES",
        tranche_count=3,
    )
    assert result["status"] == "completed"
    assert result["tranches_filled"] == 3
    assert result["cash_deployed"] <= 100.0
    assert result["exit_reason"] == "profit_target"
