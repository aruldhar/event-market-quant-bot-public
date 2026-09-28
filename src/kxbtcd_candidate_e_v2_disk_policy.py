"""21N-Y-A2 disk clock adapter; policy body is identical to frozen Y-A.

Only the clock's full-history scan is replaced by indexed top-signature reads.
All economic functions are aliases of the original frozen functions.
"""
from __future__ import annotations
from typing import Mapping, Sequence
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    ContinuousBtcRow,
    Decimal,
    EVENT_CLOSE_UTC,
    LATENCY_MS,
    LadderMarket,
    THRESHOLDS,
    V2EntryAttemptRecord,
    V2PolicyResult,
    V2RearmRecord,
    V2TradePath,
    VerifiedTickerTimeline,
    ZERO,
    _closed_cash_change,
    _evaluate_event_at_timestamp,
    _fail,
    _rearmed,
    epoch_ms,
    materialization_index,
    parse_utc,
    select_signal_at_timestamp,
    simulate_v2_entry,
    simulate_v2_liquidation,
)
from .kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import spot_window
from .kxbtcd_candidate_e_continuous_btc_materialization import scan_bounds_ms, btc_row_for_decision


def decision_clock(*, event_ticker, event_ladder, timelines, btc_rows_or_index):
    index = (btc_rows_or_index if isinstance(btc_rows_or_index, Mapping)
             else materialization_index(btc_rows_or_index))
    lo, hi = scan_bounds_ms(event_ticker)
    minute_boundaries = list(range(lo, hi + 1, 60000))
    times = set(minute_boundaries)
    times.update((lo, hi))
    for interval_start in minute_boundaries:
        if interval_start >= hi:
            break
        btc = btc_row_for_decision(index, event_ticker=event_ticker, decision_timestamp_ms=interval_start)
        if btc is None:
            continue
        interval_end = min(interval_start + 60000, hi)
        window = spot_window(event_ticker=event_ticker, btc_spot=btc.close_price, event_ladder=event_ladder)
        for market in window:
            timeline = timelines.get(market.market_ticker)
            if timeline is None:
                _fail(f"timeline missing for dynamic market {market.market_ticker}")
            for segment in timeline.segments:
                start = max(interval_start, segment.start_timestamp_ms)
                end = min(interval_end, segment.end_timestamp_ms)
                if start > end:
                    continue
                if interval_start < start < interval_end:
                    times.add(start)
                times.update(segment.top_changes(start, interval_end))
    return tuple(sorted(times))


def simulate_policy(
    *,
    event_ticker: str,
    event_ladder: Sequence[LadderMarket],
    timelines: Mapping[str, VerifiedTickerTimeline],
    btc_rows: Sequence[ContinuousBtcRow],
    threshold: Decimal,
    latency_ms: int,
) -> V2PolicyResult:
    threshold = Decimal(str(threshold))
    if threshold not in THRESHOLDS:
        _fail("threshold outside frozen menu")
    if latency_ms not in LATENCY_MS:
        _fail("latency outside frozen scenarios")

    event_close_ms = epoch_ms(parse_utc(EVENT_CLOSE_UTC[event_ticker]))
    btc_index = materialization_index(btc_rows)

    clock = decision_clock(
        event_ticker=event_ticker,
        event_ladder=event_ladder,
        timelines=timelines,
        btc_rows_or_index=btc_index,
    )

    mode = "ARMED_FIRST"
    block_through_ms = -1
    attempts: list[V2EntryAttemptRecord] = []
    trades: list[V2TradePath] = []
    rearm: V2RearmRecord | None = None
    reference: V2Signal | None = None

    for timestamp_ms in clock:
        if timestamp_ms <= block_through_ms:
            continue

        evaluations, current_window, btc_available = _evaluate_event_at_timestamp(
            event_ticker=event_ticker,
            event_ladder=event_ladder,
            timelines=timelines,
            btc_index=btc_index,
            decision_timestamp_ms=timestamp_ms,
            event_close_timestamp_ms=event_close_ms,
        )

        if mode == "WAIT_REARM":
            if reference is None:
                _fail("WAIT_REARM missing reference signal")
            yes, reason = _rearmed(
                evaluations=evaluations,
                current_window=current_window,
                btc_available=btc_available,
                reference=reference,
                threshold=threshold,
            )
            if yes:
                rearm = V2RearmRecord(
                    reference_market_ticker=reference.market_ticker,
                    reference_side=reference.side,
                    rearm_timestamp_ms=timestamp_ms,
                    reason=str(reason),
                )
                mode = "ARMED_SECOND"
                block_through_ms = timestamp_ms
            continue

        if mode not in {"ARMED_FIRST", "ARMED_SECOND"}:
            break

        if not btc_available:
            continue

        signal = select_signal_at_timestamp(
            evaluations,
            threshold=threshold,
        )
        if signal is None:
            continue

        trade_number = 1 if mode == "ARMED_FIRST" else 2
        entry = simulate_v2_entry(
            signal=signal,
            timeline=timelines[signal.market_ticker],
            latency_ms=latency_ms,
        )
        attempts.append(
            V2EntryAttemptRecord(
                trade_number=trade_number,
                signal=signal,
                latency_ms=latency_ms,
                entry=entry,
            )
        )
        block_through_ms = entry.arrival_timestamp_ms

        if (
            not entry.source_available
            or entry.ioc is None
            or entry.ioc.filled_quantity == ZERO
        ):
            continue

        liquidation = simulate_v2_liquidation(
            signal=signal,
            entry=entry,
            timeline=timelines[signal.market_ticker],
            event_close_timestamp_ms=event_close_ms,
        )
        trades.append(
            V2TradePath(
                trade_number=trade_number,
                signal=signal,
                latency_ms=latency_ms,
                entry=entry,
                liquidation=liquidation,
                fully_closed_round_trip_cash_change=_closed_cash_change(
                    entry,
                    liquidation,
                ),
                matched_hold_settlement_quantity=entry.ioc.filled_quantity,
            )
        )

        if trade_number == 2:
            mode = "DONE_MAX_TWO_FILLED_ENTRIES"
            break

        reference = signal
        if (
            liquidation is not None
            and liquidation.status == "EXIT_FULL"
            and liquidation.exit_ioc is not None
            and liquidation.exit_ioc.status == "FULL"
            and liquidation.settlement_fallback_quantity == ZERO
            and liquidation.exit_arrival_timestamp_ms is not None
        ):
            mode = "WAIT_REARM"
            block_through_ms = liquidation.exit_arrival_timestamp_ms
        else:
            mode = "DONE_FIRST_POSITION_NOT_FULLY_EXITED"
            break

    terminal = (
        "NO_FILLED_ENTRY"
        if mode == "ARMED_FIRST"
        else "FIRST_TRADE_FULLY_EXITED_NO_REARM"
        if mode == "WAIT_REARM"
        else "REARMED_NO_SECOND_FILLED_ENTRY"
        if mode == "ARMED_SECOND"
        else mode
    )

    return V2PolicyResult(
        event_ticker=event_ticker,
        threshold=threshold,
        latency_ms=latency_ms,
        decision_clock_count=len(clock),
        entry_attempts=tuple(attempts),
        trades=tuple(trades),
        rearm=rearm,
        terminal_state=terminal,
    )
