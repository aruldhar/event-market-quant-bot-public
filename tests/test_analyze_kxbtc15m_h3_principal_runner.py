from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_principal_runner import (
    minimum_principal_recovery_sale,
    simulate_policies,
    summarize,
    verify_rows,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
OPEN = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
CLOSE = OPEN + timedelta(seconds=900)
TICKER = "KXBTC15M-26AUG131515-15"


def book(yes_bid: str, yes_ask: str, quantity: str = "1000") -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal(quantity)),),
        no_levels=((Decimal("1") - Decimal(yes_ask), Decimal(quantity)),),
    )


def snapshot(elapsed: float, yes_bid: str, yes_ask: str) -> Snapshot:
    return Snapshot(
        observed_at=OPEN + timedelta(seconds=elapsed),
        request_id=str(elapsed),
        book=book(yes_bid, yes_ask),
    )


def path():
    return [
        snapshot(600.0, "0.90", "0.92"),
        snapshot(601.1, "0.90", "0.92"),
        snapshot(610.0, "0.98", "0.99"),
        snapshot(611.1, "0.98", "0.99"),
        snapshot(889.0, "0.97", "0.98"),
        snapshot(890.1, "0.97", "0.98"),
    ]


def test_minimum_sale_recovers_cash_and_leaves_runner():
    levels = book("0.98", "0.99").bid_levels("YES")
    execution = minimum_principal_recovery_sale(
        levels, Decimal("108"), Decimal("99.50")
    )
    assert execution.sell_inflow >= Decimal("99.50")
    assert execution.quantity < Decimal("108")
    if execution.quantity > 1:
        from analyze_kxbtc15m_bounded_simulation import sell_quantity
        prior = sell_quantity(levels, execution.quantity - 1)
        assert prior.sell_inflow < Decimal("99.50")


def test_runner_policies_recover_principal_and_use_same_target_snapshot():
    rows, first = simulate_policies(
        snapshots=path(), close_time=CLOSE, winning_side="YES",
        ticker=TICKER, segment="earlier_64",
    )
    baseline, preclose, settlement = rows
    assert first["exit_reason"] == "protected_profit_target"
    assert all(row["principal_recovered"] for row in rows)
    assert preclose["full_exit_execution_time"] == baseline["full_exit_execution_time"]
    assert Decimal(settlement["principal_sale_inflow"]) >= Decimal(settlement["cash_deployed"])
    assert Decimal(preclose["runner_contracts"]) > 0
    assert Decimal(settlement["pnl"]) >= 0
    verify_rows(rows)


def test_losing_runner_cannot_lose_recovered_initial_cash():
    rows, _first = simulate_policies(
        snapshots=path(), close_time=CLOSE, winning_side="NO",
        ticker=TICKER, segment="earlier_64",
    )
    settlement = rows[2]
    assert settlement["runner_won"] is False
    assert Decimal(settlement["pnl"]) >= 0
    assert settlement["full_capital_loss"] is False


def test_summary_reports_paired_runner_increment():
    rows = []
    for ticker in (TICKER, "KXBTC15M-26AUG131530-30"):
        for policy, pnl in (
            ("full_protected_50pct_cash_exit", "4"),
            ("principal_runner_preclose", "5"),
            ("principal_runner_settlement", "6"),
        ):
            rows.append({
                "ticker": ticker,
                "diagnostic_segment": "earlier_64",
                "policy": policy,
                "status": "completed",
                "pnl": pnl,
                "profitable": True,
                "principal_recovered": True,
                "runner_fraction_of_position": "0.05" if policy != "full_protected_50pct_cash_exit" else "",
                "runner_won": True if policy != "full_protected_50pct_cash_exit" else "",
                "full_capital_loss": False,
            })
    result = summarize(rows)
    settlement = next(
        row for row in result
        if row["segment"] == "all_96"
        and row["policy"] == "principal_runner_settlement"
    )
    assert settlement["mean_incremental_pnl_vs_full_exit"] == 2
    assert settlement["mean_runner_fraction"] == 0.05
