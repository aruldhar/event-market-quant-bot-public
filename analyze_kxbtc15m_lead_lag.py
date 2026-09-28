#!/usr/bin/env python3
"""Audit whether KXBTC15M order-book changes lead Kalshi chart changes.

This is an outcome-blind development-market timing diagnostic.  It aligns the
latest order-book observation available at or before each one-second Kalshi
chart timestamp, examines first differences at fixed lags, and studies chart
responses around large order-book jumps.  It does not use outcomes, external
BTC data, authentication, order placement, or any holdout market.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import math
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Mapping, Sequence

from analyze_kxbtc15m_bounded_simulation import write_csv
from analyze_kxbtc15m_h3_delta_risk import ChartSeries, load_chart_series
from audit_kxbtc15m_raw_depth import (
    AuditError,
    DevelopmentMarket,
    assess_market,
    market_close_utc,
    parse_time,
    safe_extract_zip,
    select_development_manifests,
)


EXPECTED_ELIGIBLE_MARKETS = 96
MAX_BOOK_AGE_SECONDS = 2.0
MIN_GRID_POINTS_PER_MARKET = 150
LAGS = tuple(range(-10, 16))
EVENT_OFFSETS = tuple(range(-10, 16))
EVENT_THRESHOLDS_CENTS = (2.0, 5.0)
EVENT_COOLDOWN_SECONDS = 5


class LeadLagError(RuntimeError):
    """Raised when an input or causal-alignment invariant fails."""


@dataclass(frozen=True)
class BookPoint:
    observed_at: datetime
    yes_bid: float


@dataclass(frozen=True)
class GridPoint:
    ticker: str
    market_index: int
    diagnostic_segment: str
    observed_at: datetime
    seconds_remaining: float
    time_phase: str
    book_observed_at: datetime
    book_age_seconds: float
    yes_bid: float
    chart_value: float
    chart_delta_from_target: float
    book_change_cents: float | None
    chart_change_usd: float | None


PHASES = (
    "all_final_5m",
    "05_240_300s",
    "04_180_240s",
    "03_120_180s",
    "02_60_120s",
    "01_final_0_60s",
)


def time_phase(seconds_remaining: float) -> str:
    if not 0 <= seconds_remaining <= 300:
        raise LeadLagError(f"seconds_remaining outside final five minutes: {seconds_remaining}")
    if seconds_remaining > 240:
        return "05_240_300s"
    if seconds_remaining > 180:
        return "04_180_240s"
    if seconds_remaining > 120:
        return "03_120_180s"
    if seconds_remaining > 60:
        return "02_60_120s"
    return "01_final_0_60s"


def diagnostic_segment(eligible_ordinal: int) -> str:
    return "earlier_64" if eligible_ordinal <= 64 else "later_32"


def _decimal(value: Any, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise LeadLagError(f"invalid {label}: {value!r}") from exc
    if not parsed.is_finite():
        raise LeadLagError(f"non-finite {label}: {value!r}")
    return parsed


def load_book_points(market: DevelopmentMarket) -> list[BookPoint]:
    points: list[BookPoint] = []
    prior_time: datetime | None = None
    for row in market.rows:
        bid_text = str(row.get("yes_bid", ""))
        if not bid_text:
            continue
        bid = _decimal(bid_text, "yes_bid")
        if not Decimal("0") <= bid <= Decimal("1"):
            raise LeadLagError(f"{market.ticker}: invalid YES bid {bid}")
        observed = parse_time(str(row["observed_at_utc"]))
        if prior_time is not None and observed <= prior_time:
            raise LeadLagError(f"{market.ticker}: order-book timestamps are not increasing")
        prior_time = observed
        points.append(BookPoint(observed, float(bid)))
    if not points:
        raise LeadLagError(f"{market.ticker}: no YES best bids")
    return points


def build_market_grid(
    market: DevelopmentMarket,
    chart: ChartSeries,
    *,
    eligible_ordinal: int,
    max_book_age_seconds: float = MAX_BOOK_AGE_SECONDS,
) -> list[GridPoint]:
    """Causally align book state to chart seconds and calculate first differences."""

    books = load_book_points(market)
    book_times = [point.observed_at for point in books]
    close = market_close_utc(market.ticker)
    start = close - timedelta(seconds=300)
    raw: list[tuple[datetime, float, BookPoint, float, float]] = []
    for chart_point in chart.points:
        when = chart_point.observed_at
        if not start <= when <= close:
            continue
        index = bisect.bisect_right(book_times, when) - 1
        if index < 0:
            continue
        book = books[index]
        age = (when - book.observed_at).total_seconds()
        if age < 0:
            raise LeadLagError("causal as-of alignment selected a future quote")
        if age > max_book_age_seconds:
            continue
        remaining = (close - when).total_seconds()
        raw.append((when, remaining, book, float(chart_point.value), float(chart.target)))

    if len(raw) < MIN_GRID_POINTS_PER_MARKET:
        raise LeadLagError(
            f"{market.ticker}: only {len(raw)} causally aligned final-five-minute seconds"
        )

    output: list[GridPoint] = []
    previous: tuple[datetime, float, BookPoint, float, float] | None = None
    segment = diagnostic_segment(eligible_ordinal)
    for item in raw:
        when, remaining, book, chart_value, target = item
        book_change: float | None = None
        chart_change: float | None = None
        if previous is not None and (when - previous[0]).total_seconds() == 1:
            book_change = 100.0 * (book.yes_bid - previous[2].yes_bid)
            chart_change = chart_value - previous[3]
        output.append(
            GridPoint(
                ticker=market.ticker,
                market_index=market.index,
                diagnostic_segment=segment,
                observed_at=when,
                seconds_remaining=remaining,
                time_phase=time_phase(remaining),
                book_observed_at=book.observed_at,
                book_age_seconds=(when - book.observed_at).total_seconds(),
                yes_bid=book.yes_bid,
                chart_value=chart_value,
                chart_delta_from_target=chart_value - target,
                book_change_cents=book_change,
                chart_change_usd=chart_change,
            )
        )
        previous = item
    return output


def _in_phase(point: GridPoint, phase: str) -> bool:
    return phase == "all_final_5m" or point.time_phase == phase


def lag_pairs(points: Sequence[GridPoint], phase: str, lag_seconds: int) -> list[tuple[float, float]]:
    """Return book-change/chart-change pairs; positive lag means book leads chart."""

    by_time = {point.observed_at: point for point in points}
    pairs: list[tuple[float, float]] = []
    for source in points:
        if source.book_change_cents is None or not _in_phase(source, phase):
            continue
        chart_point = by_time.get(source.observed_at + timedelta(seconds=lag_seconds))
        if (
            chart_point is None
            or chart_point.chart_change_usd is None
            or not _in_phase(chart_point, phase)
        ):
            continue
        pairs.append((source.book_change_cents, chart_point.chart_change_usd))
    return pairs


def pearson(pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(pairs) < 10:
        return None
    left = [item[0] for item in pairs]
    right = [item[1] for item in pairs]
    left_mean, right_mean = statistics.mean(left), statistics.mean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in pairs)
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    if left_ss <= 0 or right_ss <= 0:
        return None
    return numerator / math.sqrt(left_ss * right_ss)


def direction_agreement(pairs: Sequence[tuple[float, float]]) -> float | None:
    nonzero = [(x, y) for x, y in pairs if abs(x) > 1e-12 and abs(y) > 1e-12]
    if not nonzero:
        return None
    return statistics.mean((x > 0) == (y > 0) for x, y in nonzero)


def _bootstrap_mean(values: Sequence[float], seed: str) -> tuple[float, float]:
    if len(values) < 2:
        return math.nan, math.nan
    rng = random.Random(seed)
    samples = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2_000)]
    samples.sort()
    return samples[49], samples[1949]


def segment_markets(
    grids: Mapping[str, Sequence[GridPoint]], segment: str
) -> dict[str, Sequence[GridPoint]]:
    if segment == "all_96":
        return dict(grids)
    wanted = "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
    return {
        ticker: points for ticker, points in grids.items()
        if points and points[0].diagnostic_segment == wanted
    }


def summarize_lags(grids: Mapping[str, Sequence[GridPoint]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        selected = segment_markets(grids, segment)
        for phase in PHASES:
            for lag in LAGS:
                correlations: list[float] = []
                agreements: list[float] = []
                total_pairs = 0
                nonzero_pairs = 0
                for points in selected.values():
                    pairs = lag_pairs(points, phase, lag)
                    total_pairs += len(pairs)
                    nonzero_pairs += sum(
                        abs(x) > 1e-12 and abs(y) > 1e-12 for x, y in pairs
                    )
                    correlation = pearson(pairs)
                    agreement = direction_agreement(pairs)
                    if correlation is not None:
                        correlations.append(correlation)
                    if agreement is not None:
                        agreements.append(agreement)
                low, high = _bootstrap_mean(correlations, f"{segment}|{phase}|{lag}")
                rows.append({
                    "segment": segment,
                    "time_phase": phase,
                    "lag_seconds": lag,
                    "lag_interpretation": (
                        "orderbook_leads_chart" if lag > 0 else
                        "chart_leads_orderbook" if lag < 0 else "same_second"
                    ),
                    "markets_in_segment": len(selected),
                    "markets_with_correlation": len(correlations),
                    "observation_pairs": total_pairs,
                    "nonzero_direction_pairs": nonzero_pairs,
                    "equal_market_mean_correlation": statistics.mean(correlations) if correlations else math.nan,
                    "median_market_correlation": statistics.median(correlations) if correlations else math.nan,
                    "cluster_bootstrap_ci_low": low,
                    "cluster_bootstrap_ci_high": high,
                    "equal_market_mean_direction_agreement": statistics.mean(agreements) if agreements else math.nan,
                    "holdout_read": False,
                    "outcomes_used": False,
                    "external_btc_data_used": False,
                    "authenticated_data_used": False,
                })
    return rows


def select_events(points: Sequence[GridPoint], threshold_cents: float) -> list[GridPoint]:
    selected: list[GridPoint] = []
    prior_event: datetime | None = None
    for point in points:
        if point.book_change_cents is None or abs(point.book_change_cents) < threshold_cents:
            continue
        if prior_event is not None and (point.observed_at - prior_event).total_seconds() < EVENT_COOLDOWN_SECONDS:
            continue
        selected.append(point)
        prior_event = point.observed_at
    return selected


def event_rows(grids: Mapping[str, Sequence[GridPoint]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ticker, points in grids.items():
        by_time = {point.observed_at: point for point in points}
        for threshold in EVENT_THRESHOLDS_CENTS:
            for event_number, event in enumerate(select_events(points, threshold), start=1):
                direction = 1.0 if float(event.book_change_cents) > 0 else -1.0
                for offset in EVENT_OFFSETS:
                    response = by_time.get(event.observed_at + timedelta(seconds=offset))
                    if response is None or response.chart_change_usd is None:
                        continue
                    signed = direction * response.chart_change_usd
                    rows.append({
                        "ticker": ticker,
                        "market_index": event.market_index,
                        "diagnostic_segment": event.diagnostic_segment,
                        "threshold_cents": threshold,
                        "event_number_within_market": event_number,
                        "event_time": event.observed_at.isoformat(),
                        "event_time_phase": event.time_phase,
                        "event_seconds_remaining": event.seconds_remaining,
                        "book_change_cents": event.book_change_cents,
                        "response_offset_seconds": offset,
                        "chart_change_usd": response.chart_change_usd,
                        "direction_aligned_chart_change_usd": signed,
                        "same_direction": signed > 0,
                        "holdout_read": False,
                        "outcomes_used": False,
                    })
    return rows


def summarize_events(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
        wanted_segment = None if segment == "all_96" else (
            "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
        )
        for phase in PHASES:
            for threshold in EVENT_THRESHOLDS_CENTS:
                for offset in EVENT_OFFSETS:
                    selected = [
                        row for row in rows
                        if float(row["threshold_cents"]) == threshold
                        and int(row["response_offset_seconds"]) == offset
                        and (wanted_segment is None or row["diagnostic_segment"] == wanted_segment)
                        and (phase == "all_final_5m" or row["event_time_phase"] == phase)
                    ]
                    values = [float(row["direction_aligned_chart_change_usd"]) for row in selected]
                    event_keys = {(row["ticker"], row["event_number_within_market"]) for row in selected}
                    output.append({
                        "segment": segment,
                        "time_phase": phase,
                        "threshold_cents": threshold,
                        "response_offset_seconds": offset,
                        "events": len(event_keys),
                        "markets": len({row["ticker"] for row in selected}),
                        "mean_direction_aligned_chart_change_usd": statistics.mean(values) if values else math.nan,
                        "median_direction_aligned_chart_change_usd": statistics.median(values) if values else math.nan,
                        "same_direction_rate": statistics.mean(value > 0 for value in values) if values else math.nan,
                        "holdout_read": False,
                        "outcomes_used": False,
                    })
    return output


def best_lag_rows(summary: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    for phase in PHASES:
        candidates = [
            row for row in summary
            if row["segment"] == "all_96" and row["time_phase"] == phase
            and not math.isnan(float(row["equal_market_mean_correlation"]))
        ]
        if candidates:
            output.append(max(candidates, key=lambda row: float(row["equal_market_mean_correlation"])))
    return output


def best_event_rows(summary: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    output: list[Mapping[str, Any]] = []
    for threshold in EVENT_THRESHOLDS_CENTS:
        candidates = [
            row for row in summary
            if row["segment"] == "all_96" and row["time_phase"] == "all_final_5m"
            and float(row["threshold_cents"]) == threshold
            and not math.isnan(float(row["mean_direction_aligned_chart_change_usd"]))
        ]
        if candidates:
            output.append(max(candidates, key=lambda row: float(row["mean_direction_aligned_chart_change_usd"])))
    return output


def _number(value: Any, digits: int = 4) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return "n/a" if math.isnan(parsed) else f"{parsed:.{digits}f}"


def markdown_report(
    grids: Mapping[str, Sequence[GridPoint]],
    lag_summary: Sequence[Mapping[str, Any]],
    event_summary: Sequence[Mapping[str, Any]],
) -> str:
    points = [point for market in grids.values() for point in market]
    coverage = [len(market) for market in grids.values()]
    lines = [
        "# KXBTC15M Kalshi chart/order-book lead-lag audit",
        "",
        "**Outcome-blind development timing study; holdout sealed.**",
        "",
        f"Eligible markets: {len(grids)}. Causally aligned one-second points in the final five minutes: {len(points)}.",
        f"Per-market aligned coverage: minimum {min(coverage)}, median {statistics.median(coverage):.0f}, maximum {max(coverage)} of 301 possible seconds.",
        "The order-book value is the executable YES best bid from the latest observation at or before each chart second. Quotes older than two seconds are not carried forward, and missing seconds remain missing.",
        "",
        "Positive lag means an order-book change occurs first and the chart change is measured later. Negative lag means the chart occurs first.",
        "",
        "## Full final-five-minute lag curve",
        "",
        "| Lag | Interpretation | Equal-market mean correlation | Clustered 95% CI | Direction agreement | Markets |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in lag_summary:
        if row["segment"] != "all_96" or row["time_phase"] != "all_final_5m":
            continue
        lines.append(
            f"| {int(row['lag_seconds']):+d}s | {row['lag_interpretation']} | "
            f"{_number(row['equal_market_mean_correlation'])} | "
            f"{_number(row['cluster_bootstrap_ci_low'])} to {_number(row['cluster_bootstrap_ci_high'])} | "
            f"{_number(100 * float(row['equal_market_mean_direction_agreement']), 1)}% | "
            f"{int(row['markets_with_correlation'])} |"
        )
    lines.extend([
        "",
        "## Highest-correlation lag by time phase",
        "",
        "| Time phase | Peak lag | Interpretation | Correlation | 95% CI |",
        "|---|---:|---|---:|---:|",
    ])
    for row in best_lag_rows(lag_summary):
        lines.append(
            f"| {row['time_phase']} | {int(row['lag_seconds']):+d}s | {row['lag_interpretation']} | "
            f"{_number(row['equal_market_mean_correlation'])} | "
            f"{_number(row['cluster_bootstrap_ci_low'])} to {_number(row['cluster_bootstrap_ci_high'])} |"
        )
    lines.extend([
        "",
        "## Chart response after large order-book jumps",
        "",
        "Events within five seconds of an earlier qualifying event are suppressed. The reported offset is where the average chart change, signed to the direction of the contract jump, is largest.",
        "",
        "| Order-book jump | Events | Markets | Peak chart offset | Mean aligned chart change | Same direction |",
        "|---:|---:|---:|---:|---:|---:|",
    ])
    for row in best_event_rows(event_summary):
        lines.append(
            f"| at least {float(row['threshold_cents']):.0f}c | {int(row['events'])} | {int(row['markets'])} | "
            f"{int(row['response_offset_seconds']):+d}s | ${_number(row['mean_direction_aligned_chart_change_usd'])} | "
            f"{_number(100 * float(row['same_direction_rate']), 1)}% |"
        )
    lines.extend([
        "",
        "This audit is descriptive. A correlation peak does not prove that one feed causes the other, and the Kalshi chart is settlement-related data rather than a raw external exchange feed. The earlier/later segment rows and complete phase/lag grid are retained in the CSVs for stability review.",
        "",
        "No outcome, external BTC feed, authentication, order, or holdout observation was used.",
    ])
    return "\n".join(lines) + "\n"


def grid_csv_rows(grids: Mapping[str, Sequence[GridPoint]]) -> Iterable[dict[str, Any]]:
    for points in grids.values():
        for point in points:
            yield {
                "ticker": point.ticker,
                "market_index": point.market_index,
                "diagnostic_segment": point.diagnostic_segment,
                "observed_at_utc": point.observed_at.isoformat(),
                "seconds_remaining": point.seconds_remaining,
                "time_phase": point.time_phase,
                "book_observed_at_utc": point.book_observed_at.isoformat(),
                "book_age_seconds": point.book_age_seconds,
                "yes_bid": point.yes_bid,
                "chart_value": point.chart_value,
                "chart_delta_from_target": point.chart_delta_from_target,
                "book_change_cents": "" if point.book_change_cents is None else point.book_change_cents,
                "chart_change_usd": "" if point.chart_change_usd is None else point.chart_change_usd,
                "holdout_read": False,
                "outcomes_used": False,
                "external_btc_data_used": False,
                "authenticated_data_used": False,
            }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_zip", type=Path)
    parser.add_argument("--live-data-summary-csv", type=Path, required=True)
    parser.add_argument("--live-data-timeseries-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_lead_lag"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    grids: dict[str, list[GridPoint]] = {}
    with TemporaryDirectory(prefix="kxbtc15m_lead_lag_") as temporary:
        root = Path(temporary)
        safe_extract_zip(args.audit_zip, root)
        manifests = select_development_manifests(root)
        markets = [
            assess_market(index, manifest, root)
            for index, manifest in enumerate(manifests, start=1)
        ]
        eligible = [market for market in markets if market.eligible]
        if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
            raise LeadLagError(
                f"expected {EXPECTED_ELIGIBLE_MARKETS} eligible markets; found {len(eligible)}"
            )
        charts = load_chart_series(
            args.live_data_summary_csv,
            args.live_data_timeseries_csv,
            required_tickers={market.ticker for market in eligible},
        )
        if set(charts) != {market.ticker for market in eligible}:
            raise LeadLagError("chart and eligible order-book ticker sets differ")
        for ordinal, market in enumerate(eligible, start=1):
            grids[market.ticker] = build_market_grid(
                market, charts[market.ticker], eligible_ordinal=ordinal
            )
            print(f"[{ordinal:02d}/{EXPECTED_ELIGIBLE_MARKETS}] {market.ticker}")

    lag_summary = summarize_lags(grids)
    events = event_rows(grids)
    event_summary = summarize_events(events)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_lead_lag_grid.csv", list(grid_csv_rows(grids)))
    write_csv(args.output_dir / "kxbtc15m_lead_lag_summary.csv", lag_summary)
    write_csv(args.output_dir / "kxbtc15m_lead_lag_events.csv", events)
    write_csv(args.output_dir / "kxbtc15m_lead_lag_event_summary.csv", event_summary)
    report_path = args.output_dir / "KXBTC15M_LEAD_LAG.md"
    report_path.write_text(
        markdown_report(grids, lag_summary, event_summary), encoding="utf-8"
    )

    total_points = sum(len(points) for points in grids.values())
    coverage = [len(points) for points in grids.values()]
    print("KXBTC15M Kalshi chart/order-book lead-lag audit: PASS")
    print(f"Eligible development markets: {len(grids)}")
    print(f"Causally aligned final-five-minute seconds: {total_points}")
    print(
        "Per-market aligned coverage: "
        f"min {min(coverage)} / median {statistics.median(coverage):.0f} / "
        f"max {max(coverage)} of 301"
    )
    print("Lags tested: chart leads 10s through order book leads 15s")
    print("Large order-book jumps: 2c and 5c")
    print("Outcomes used: no")
    print("External BTC data used: no")
    print("Authenticated data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (AuditError, LeadLagError, OSError, ValueError) as exc:
        raise SystemExit(f"KXBTC15M lead-lag error: {exc}") from exc
