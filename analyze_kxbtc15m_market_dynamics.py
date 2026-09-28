#!/usr/bin/env python3
"""Development-only, full-market KXBTC15M dynamics census.

The analyzer samples entry anchors on a uniform five-second grid across all 15
minutes, then uses every later recorded quote to measure executable-bid gross
recovery and bounded equal-contract pooling mechanics. It is exploratory and
pre-fee: it does not claim strategy profitability, inspect outcomes, or read
the frozen 26-market holdout.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import random
import re
import statistics
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Sequence


FIRST_TICKER = "KXBTC15M-26AUG111345-45"
DEVELOPMENT_LAST_TICKER = "KXBTC15M-26AUG121430-30"
HOLDOUT_FIRST_TICKER = "KXBTC15M-26AUG121445-45"
EXPECTED_DEVELOPMENT_MARKETS = 100
EXPECTED_ELIGIBLE_MARKETS = 96
GRID_SECONDS = 5
GRID_TOLERANCE_SECONDS = 2
DROP_STEPS = (0.02, 0.05, 0.10)
BOOTSTRAP_REPS = 2000
BOOTSTRAP_SEED = 20260814
FROZEN_TICKER_TIMEZONE = timezone(timedelta(hours=-4), name="EDT")
TICKER_RE = re.compile(r"KXBTC15M-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})-\d{2}")
MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


class AnalysisError(RuntimeError):
    """Raised when the frozen analysis cannot proceed safely."""


@dataclass(frozen=True)
class Quote:
    time: datetime
    ticker: str
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None

    def bid(self, side: str) -> float | None:
        return self.yes_bid if side == "YES" else self.no_bid

    def ask(self, side: str) -> float | None:
        return self.yes_ask if side == "YES" else self.no_ask

    def midpoint(self, side: str) -> float | None:
        bid, ask = self.bid(side), self.ask(side)
        return None if bid is None or ask is None else (bid + ask) / 2

    def complete(self) -> bool:
        return all(
            value is not None
            for value in (self.yes_bid, self.yes_ask, self.no_bid, self.no_ask)
        )


@dataclass(frozen=True)
class Market:
    index: int
    ticker: str
    close: datetime
    quotes: tuple[Quote, ...]
    eligible: bool
    exclusion_reasons: tuple[str, ...]

    @property
    def open(self) -> datetime:
        return self.close - timedelta(minutes=15)


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AnalysisError(f"Naive timestamp: {value!r}")
    return parsed.astimezone(timezone.utc)


def market_close_utc(ticker: str) -> datetime:
    match = TICKER_RE.fullmatch(ticker)
    if not match:
        raise AnalysisError(f"Unsupported ticker: {ticker}")
    yy, month, day, hour, minute = match.groups()
    year, month_number = 2000 + int(yy), MONTHS[month]
    if (year, month_number) != (2026, 8):
        raise AnalysisError("Frozen analysis accepts only August 2026 tickers")
    local_close = datetime(
        year, month_number, int(day), int(hour), int(minute),
        tzinfo=FROZEN_TICKER_TIMEZONE,
    )
    return local_close.astimezone(timezone.utc)


def number(value: str | None) -> float | None:
    return None if value is None or value == "" else float(value)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract_zip(source: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise AnalysisError(f"Unsafe ZIP member: {member.filename!r}") from exc
        archive.extractall(root)


def file_by_basename(root: Path, basename: str) -> Path:
    matches = [path for path in root.rglob(basename) if path.is_file()]
    if len(matches) != 1:
        raise AnalysisError(f"Expected one {basename!r}; found {len(matches)}")
    return matches[0]


def derived_descriptor(manifest: dict[str, Any]) -> dict[str, Any]:
    matches = [item for item in manifest.get("files", []) if item.get("role") == "derived_csv"]
    if len(matches) != 1:
        raise AnalysisError(f"{manifest.get('run_id')}: expected one derived CSV")
    return matches[0]


def select_development_manifests(root: Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in root.rglob("record_orderbook_*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("status") == "completed" and document.get("arguments", {}).get("ticker"):
            manifests.append(document)
    manifests.sort(key=lambda item: parse_time(item["started_at_utc"]))
    selected: list[dict[str, Any]] = []
    active = False
    for manifest in manifests:
        ticker = manifest["arguments"]["ticker"]
        if ticker == FIRST_TICKER:
            active = True
        if active:
            selected.append(manifest)
        if ticker == DEVELOPMENT_LAST_TICKER:
            break
    if len(selected) != EXPECTED_DEVELOPMENT_MARKETS:
        raise AnalysisError(
            f"Expected {EXPECTED_DEVELOPMENT_MARKETS} development markets; found {len(selected)}"
        )
    if selected[-1]["arguments"]["ticker"] != DEVELOPMENT_LAST_TICKER:
        raise AnalysisError("Development partition end was not found")
    if any(item["arguments"]["ticker"] == HOLDOUT_FIRST_TICKER for item in selected):
        raise AnalysisError("Holdout ticker entered development partition")
    return selected


def load_quotes(path: Path) -> tuple[list[dict[str, str]], tuple[Quote, ...]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    quotes = tuple(Quote(
        time=parse_time(row["observed_at_utc"]),
        ticker=row["ticker"],
        yes_bid=number(row.get("yes_bid")), yes_ask=number(row.get("yes_ask")),
        no_bid=number(row.get("no_bid")), no_ask=number(row.get("no_ask")),
    ) for row in rows)
    return rows, quotes


def build_market(index: int, manifest: dict[str, Any], root: Path) -> Market:
    ticker = manifest["arguments"]["ticker"]
    descriptor = derived_descriptor(manifest)
    basename = Path(descriptor["path"]["value"].replace("\\", "/")).name
    path = file_by_basename(root, basename)
    rows, quotes = load_quotes(path)
    close = market_close_utc(ticker)
    open_time = close - timedelta(minutes=15)
    reasons: list[str] = []
    if sha256_path(path) != descriptor.get("sha256"):
        reasons.append("derived_sha256_mismatch")
    if len(rows) != descriptor.get("data_row_count"):
        reasons.append("derived_row_count_mismatch")
    if any(row["ticker"] != ticker for row in rows):
        reasons.append("derived_ticker_mismatch")
    if any(row["run_id"] != manifest.get("run_id") for row in rows):
        reasons.append("derived_run_id_mismatch")
    result, summary = manifest.get("result", {}), manifest.get("summary", {})
    if result.get("orders_placed") != 0:
        reasons.append("orders_placed_not_zero")
    if result.get("request_failures") != 0:
        reasons.append("request_failures")
    if summary.get("raw_error_record_count") != 0:
        reasons.append("raw_errors")
    if summary.get("runtime_error_event_count") != 0:
        reasons.append("runtime_errors")
    preclose = [q for q in quotes if open_time <= q.time < close]
    valid = [q.time for q in preclose if any(v is not None for v in (q.yes_bid, q.yes_ask, q.no_bid, q.no_ask))]
    if not valid:
        reasons.append("no_valid_preclose_quotes")
    else:
        if (min(valid) - open_time).total_seconds() > 45:
            reasons.append("late_first_valid_quote")
        if (max(valid) - close).total_seconds() < -5:
            reasons.append("early_last_valid_quote")
    gaps = [(b.time - a.time).total_seconds() for a, b in zip(preclose, preclose[1:])]
    if not gaps or max(gaps) > 5:
        reasons.append("preclose_gap_over_5s")
    return Market(index, ticker, close, quotes, not reasons, tuple(reasons))


def price_band(price: float) -> str:
    if price < 0.10:
        return "00_10c"
    if price < 0.20:
        return "10_20c"
    if price < 0.30:
        return "20_30c"
    if price < 0.40:
        return "30_40c"
    if price < 0.50:
        return "40_50c"
    return "50c_plus"


def elapsed_minute(elapsed_seconds: float) -> int:
    return max(1, min(15, int(elapsed_seconds // 60) + 1))


def time_phase(elapsed_seconds: float) -> str:
    if elapsed_seconds < 300:
        return "01_first_0_5m"
    if elapsed_seconds < 600:
        return "02_middle_5_10m"
    if elapsed_seconds < 780:
        return "03_late_10_13m"
    return "04_terminal_13_15m"


def lower_side(quote: Quote) -> str | None:
    if quote.yes_ask is None or quote.no_ask is None:
        return None
    if math.isclose(quote.yes_ask, quote.no_ask, abs_tol=1e-12):
        return None
    return "YES" if quote.yes_ask < quote.no_ask else "NO"


def grid_indices(market: Market) -> list[tuple[datetime, int]]:
    times = [quote.time for quote in market.quotes]
    selected: list[tuple[datetime, int]] = []
    for step in range(15 * 60 // GRID_SECONDS):
        target = market.open + timedelta(seconds=step * GRID_SECONDS)
        index = bisect.bisect_left(times, target)
        if index >= len(times):
            continue
        delay = (times[index] - target).total_seconds()
        if 0 <= delay <= GRID_TOLERANCE_SECONDS and market.quotes[index].time < market.close:
            selected.append((target, index))
    return selected


def first_gross_recovery(
    quotes: Sequence[Quote], side: str, start_index: int, threshold: float,
    deadline: datetime,
) -> tuple[bool, float | None]:
    start_time = quotes[start_index].time
    for quote in quotes[start_index + 1:]:
        if quote.time > deadline:
            break
        bid = quote.bid(side)
        if bid is not None and bid > threshold + 1e-12:
            return True, (quote.time - start_time).total_seconds()
    return False, None


def evaluate_anchor(market: Market, index: int) -> dict[str, Any] | None:
    entry = market.quotes[index]
    side = lower_side(entry)
    if side is None:
        return None
    entry_ask, entry_bid = entry.ask(side), entry.bid(side)
    if entry_ask is None or entry_bid is None:
        return None
    elapsed = (entry.time - market.open).total_seconds()
    remaining = (market.close - entry.time).total_seconds()
    output: dict[str, Any] = {
        "market_index": market.index,
        "ticker": market.ticker,
        "observed_at_utc": entry.time.isoformat(),
        "elapsed_seconds": elapsed,
        "time_remaining_seconds": remaining,
        "elapsed_minute": elapsed_minute(elapsed),
        "time_phase": time_phase(elapsed),
        "first_five_minutes": elapsed < 300,
        "side": side,
        "entry_ask": entry_ask,
        "entry_bid": entry_bid,
        "entry_spread": entry_ask - entry_bid,
        "entry_price_band": price_band(entry_ask),
        "time_price_cell": f"{time_phase(elapsed)}|{price_band(entry_ask)}",
    }
    for horizon in (30, 60, 120):
        deadline = min(market.close, entry.time + timedelta(seconds=horizon))
        success, seconds = first_gross_recovery(
            market.quotes, side, index, entry_ask, deadline
        )
        output[f"single_recovery_{horizon}s"] = success
        output[f"single_recovery_time_{horizon}s"] = seconds
    success, seconds = first_gross_recovery(
        market.quotes, side, index, entry_ask, market.close
    )
    output["single_recovery_before_close"] = success
    output["single_recovery_time_before_close"] = seconds

    for drop in DROP_STEPS:
        label = f"{int(round(drop * 100)):02d}c"
        add1_index: int | None = None
        add2_index: int | None = None
        for later_index in range(index + 1, len(market.quotes)):
            quote = market.quotes[later_index]
            if quote.time >= market.close:
                break
            ask = quote.ask(side)
            if ask is None:
                continue
            if add1_index is None and ask <= entry_ask - drop + 1e-12:
                add1_index = later_index
                continue
            if add1_index is not None and ask <= entry_ask - 2 * drop + 1e-12:
                add2_index = later_index
                break
        output[f"drop_{label}_triggered"] = add1_index is not None
        if add1_index is None:
            output[f"two_tranche_avg_{label}"] = None
            output[f"two_tranche_recovery_{label}"] = None
            output[f"two_tranche_recovery_time_{label}"] = None
            output[f"second_drop_{label}_triggered"] = False
            output[f"three_tranche_avg_{label}"] = None
            output[f"three_tranche_recovery_{label}"] = None
            output[f"three_tranche_recovery_time_{label}"] = None
            continue
        add1_ask = market.quotes[add1_index].ask(side)
        assert add1_ask is not None
        avg2 = (entry_ask + add1_ask) / 2
        recovered2, recovery2_seconds = first_gross_recovery(
            market.quotes, side, add1_index, avg2, market.close
        )
        output[f"two_tranche_avg_{label}"] = avg2
        output[f"two_tranche_recovery_{label}"] = recovered2
        output[f"two_tranche_recovery_time_{label}"] = recovery2_seconds
        output[f"second_drop_{label}_triggered"] = add2_index is not None
        if add2_index is None:
            output[f"three_tranche_avg_{label}"] = None
            output[f"three_tranche_recovery_{label}"] = None
            output[f"three_tranche_recovery_time_{label}"] = None
            continue
        add2_ask = market.quotes[add2_index].ask(side)
        assert add2_ask is not None
        avg3 = (entry_ask + add1_ask + add2_ask) / 3
        recovered3, recovery3_seconds = first_gross_recovery(
            market.quotes, side, add2_index, avg3, market.close
        )
        output[f"three_tranche_avg_{label}"] = avg3
        output[f"three_tranche_recovery_{label}"] = recovered3
        output[f"three_tranche_recovery_time_{label}"] = recovery3_seconds
    return output


def volatility_rows(market: Market, indices: Sequence[tuple[datetime, int]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for (target_a, index_a), (target_b, index_b) in zip(indices, indices[1:]):
        if (target_b - target_a).total_seconds() != GRID_SECONDS:
            continue
        first, second = market.quotes[index_a], market.quotes[index_b]
        mid_a, mid_b = first.midpoint("YES"), second.midpoint("YES")
        if mid_a is None or mid_b is None:
            continue
        elapsed = (first.time - market.open).total_seconds()
        output.append({
            "market_index": market.index,
            "ticker": market.ticker,
            "observed_at_utc": first.time.isoformat(),
            "elapsed_seconds": elapsed,
            "time_remaining_seconds": (market.close - first.time).total_seconds(),
            "elapsed_minute": elapsed_minute(elapsed),
            "time_phase": time_phase(elapsed),
            "first_five_minutes": elapsed < 300,
            "abs_yes_midpoint_change_5s": abs(mid_b - mid_a),
        })
    return output


def clustered_rate(
    rows: Sequence[dict[str, Any]], field: str, seed_label: str
) -> dict[str, Any]:
    cleaned = [row for row in rows if row[field] is not None]
    values = [bool(row[field]) for row in cleaned]
    by_market: dict[int, list[bool]] = defaultdict(list)
    for row in cleaned:
        by_market[int(row["market_index"])].append(bool(row[field]))
    market_rates = [sum(items) / len(items) for items in by_market.values()]
    market_weighted_rate = (
        None if not market_rates else statistics.fmean(market_rates)
    )
    interval: list[float] | None = None
    if market_rates:
        label_seed = int.from_bytes(
            hashlib.sha256(seed_label.encode("utf-8")).digest()[:8], "big"
        )
        rng = random.Random(BOOTSTRAP_SEED ^ label_seed)
        draws = sorted(
            statistics.fmean(rng.choice(market_rates) for _ in market_rates)
            for _ in range(BOOTSTRAP_REPS)
        )
        interval = [
            draws[int(0.025 * (BOOTSTRAP_REPS - 1))],
            draws[int(0.975 * (BOOTSTRAP_REPS - 1))],
        ]
    return {
        "eligible_rows": len(values),
        "successes": sum(values),
        "row_weighted_rate": None if not values else sum(values) / len(values),
        "contributing_markets": len(market_rates),
        "equal_market_weighted_rate": market_weighted_rate,
        "market_bootstrap_95_ci": interval,
    }


def summarize_anchor_groups(
    rows: Sequence[dict[str, Any]], field: str
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    result: dict[str, dict[str, Any]] = {}
    for label, items in sorted(groups.items()):
        summary = {
            "anchors": len(items),
            "markets": len({item["market_index"] for item in items}),
            "mean_entry_ask": statistics.fmean(item["entry_ask"] for item in items),
            "single_recovery_30s": clustered_rate(
                items, "single_recovery_30s", f"{field}:{label}:single30"
            ),
            "single_recovery_60s": clustered_rate(
                items, "single_recovery_60s", f"{field}:{label}:single60"
            ),
            "single_recovery_120s": clustered_rate(
                items, "single_recovery_120s", f"{field}:{label}:single120"
            ),
            "single_recovery_before_close": clustered_rate(
                items, "single_recovery_before_close", f"{field}:{label}:single_close"
            ),
        }
        for drop in DROP_STEPS:
            drop_label = f"{int(round(drop * 100)):02d}c"
            summary[f"drop_{drop_label}_trigger"] = clustered_rate(
                items,
                f"drop_{drop_label}_triggered",
                f"{field}:{label}:drop:{drop_label}",
            )
            summary[f"two_tranche_{drop_label}_conditional_recovery"] = clustered_rate(
                items,
                f"two_tranche_recovery_{drop_label}",
                f"{field}:{label}:two:{drop_label}",
            )
            summary[f"three_tranche_{drop_label}_conditional_recovery"] = clustered_rate(
                items,
                f"three_tranche_recovery_{drop_label}",
                f"{field}:{label}:three:{drop_label}",
            )
        result[label] = summary
    return result


def summarize_volatility(
    rows: Sequence[dict[str, Any]], field: str
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[field])].append(row)
    return {
        label: {
            "observations": len(items),
            "markets": len({item["market_index"] for item in items}),
            "mean_abs_yes_midpoint_change_5s": statistics.fmean(
                item["abs_yes_midpoint_change_5s"] for item in items
            ),
            "median_abs_yes_midpoint_change_5s": statistics.median(
                item["abs_yes_midpoint_change_5s"] for item in items
            ),
        }
        for label, items in sorted(groups.items())
    }


def markdown_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    minute = result["by_elapsed_minute"]
    volatility = result["volatility_by_elapsed_minute"]
    first_later = result["first_five_vs_later"]
    price = result["by_entry_price_band"]
    phase_price = result["by_time_price_cell"]
    phase_summary = result["by_time_phase"]
    volatility_phase = result["volatility_by_time_phase"]
    lines = [
        "# KXBTC15M full-market development dynamics",
        "",
        "Status: exploratory, development-only, outcome-blind, pre-fee, infinitesimal top-of-book mechanics.",
        "",
        "## Evidence boundary",
        "",
        f"- Eligible development markets: {summary['eligible_markets']}",
        f"- Five-second entry anchors: {summary['anchors']:,}",
        f"- Five-second volatility observations: {summary['volatility_observations']:,}",
        "- Holdout read: **false**",
        "- Exact later recorded quotes, including half-second observations, were searched for recovery.",
        "- No fee-adjusted or material-size profitability claim is made.",
        "",
        "## First five minutes versus later",
        "",
        "| Window | Anchors | Mean entry ask | 60s gross recovery | Before-close gross recovery |",
        "|---|---:|---:|---:|---:|",
    ]
    for label in ("True", "False"):
        item = first_later[label]
        name = "First five minutes" if label == "True" else "Minutes 6–15"
        lines.append(
            f"| {name} | {item['anchors']:,} | {item['mean_entry_ask']:.3f} | "
            f"{item['single_recovery_60s']['equal_market_weighted_rate']:.1%} | "
            f"{item['single_recovery_before_close']['equal_market_weighted_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Minute-by-minute dynamics",
        "",
        "| Elapsed minute | Mean abs YES midpoint move / 5s | Anchors | 60s gross recovery | Before-close gross recovery |",
        "|---:|---:|---:|---:|---:|",
    ])
    for label in sorted(minute, key=int):
        item, vol = minute[label], volatility.get(label, {})
        lines.append(
            f"| {label} | {vol.get('mean_abs_yes_midpoint_change_5s', 0):.4f} | "
            f"{item['anchors']:,} | {item['single_recovery_60s']['equal_market_weighted_rate']:.1%} | "
            f"{item['single_recovery_before_close']['equal_market_weighted_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Entry-price bands",
        "",
        "| Lower-side entry ask | Anchors | 60s gross recovery | Before-close gross recovery |",
        "|---|---:|---:|---:|",
    ])
    for label, item in price.items():
        lines.append(
            f"| {label} | {item['anchors']:,} | "
            f"{item['single_recovery_60s']['equal_market_weighted_rate']:.1%} | "
            f"{item['single_recovery_before_close']['equal_market_weighted_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Pooling mechanics",
        "",
        "For each anchor, equal-contract additions were evaluated after 2¢, 5¢, and 10¢ declines. "
        "Conditional recovery means a later executable bid exceeded the displayed pooled average "
        "after the relevant decline actually occurred. These are overlapping exploratory "
        "counterfactuals, before fees and size; they are not a backtest.",
        "",
        "The machine-readable JSON and anchor CSV contain the complete decline-trigger and "
        "conditional-recovery surfaces by minute and entry-price band.",
        "",
        "| Time phase | 5¢ drop trigger | Two-tranche conditional recovery | Three-tranche conditional recovery |",
        "|---|---:|---:|---:|",
    ])
    for phase_label in (
        "01_first_0_5m", "02_middle_5_10m",
        "03_late_10_13m", "04_terminal_13_15m",
    ):
        item = phase_summary[phase_label]
        lines.append(
            f"| {phase_label} | "
            f"{item['drop_05c_trigger']['equal_market_weighted_rate']:.1%} | "
            f"{item['two_tranche_05c_conditional_recovery']['equal_market_weighted_rate']:.1%} | "
            f"{item['three_tranche_05c_conditional_recovery']['equal_market_weighted_rate']:.1%} |"
        )
    lines.extend([
        "",
        "## Time-by-price control surface",
        "",
        "The following table reports equal-market-weighted 60-second gross recovery, followed "
        "by `anchor count / market count`. A dash means that time/price cell did not occur. "
        "Small cells are descriptive only.",
        "",
        "| Time phase | 0–10¢ | 10–20¢ | 20–30¢ | 30–40¢ | 40–50¢ | 50¢+ |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    bands = ("00_10c", "10_20c", "20_30c", "30_40c", "40_50c", "50c_plus")
    phases = (
        "01_first_0_5m", "02_middle_5_10m",
        "03_late_10_13m", "04_terminal_13_15m",
    )
    for phase_label in phases:
        values = []
        for band in bands:
            cell = phase_price.get(f"{phase_label}|{band}")
            if cell is None:
                values.append("—")
            else:
                cell_rate = cell["single_recovery_60s"]["equal_market_weighted_rate"]
                values.append(
                    "—" if cell_rate is None else
                    f"{cell_rate:.1%} ({cell['anchors']}/{cell['markets']}m)"
                )
        lines.append(f"| {phase_label} | " + " | ".join(values) + " |")
    lines.extend([
        "",
        "## What this exploratory census suggests",
        "",
        f"- The first five minutes were not the highest-volatility phase by this metric: "
        f"mean absolute five-second YES midpoint movement was "
        f"{volatility_phase['01_first_0_5m']['mean_abs_yes_midpoint_change_5s']:.4f} early "
        f"versus {volatility_phase['04_terminal_13_15m']['mean_abs_yes_midpoint_change_5s']:.4f} "
        "in the terminal phase. Terminal coverage is lower and those moves occur during rapid "
        "0/1 convergence, so this is not automatically a better trading window.",
        f"- Gross recoverability was strongest early: the equal-market 60-second rate was "
        f"{phase_summary['01_first_0_5m']['single_recovery_60s']['equal_market_weighted_rate']:.1%}, "
        f"falling to {phase_summary['04_terminal_13_15m']['single_recovery_60s']['equal_market_weighted_rate']:.1%} "
        "in the terminal phase, whose horizon is censored by close.",
        f"- After a 5¢ decline, two equal-contract tranches recovered above their displayed "
        f"pooled average in {phase_summary['01_first_0_5m']['two_tranche_05c_conditional_recovery']['equal_market_weighted_rate']:.1%} "
        f"of early triggered cases versus "
        f"{phase_summary['02_middle_5_10m']['two_tranche_05c_conditional_recovery']['equal_market_weighted_rate']:.1%} "
        "in minutes 6–10. This is the clearest candidate mechanic for depth/fee testing, not a "
        "profitability conclusion.",
        "- Time and price are strongly confounded: the average lower-side ask falls as the "
        "market approaches close. The joint surface must therefore guide rule selection.",
        "",
        "## Next step",
        "",
        "Use these development patterns to select a small bounded rule family, then run the "
        "full-depth fee-aware simulator. Do not open the holdout based on this exploratory census.",
        "",
    ])
    return "\n".join(lines)


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise AnalysisError(f"Refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(root: Path, output_dir: Path) -> dict[str, Any]:
    manifests = select_development_manifests(root)
    markets = [build_market(i, item, root) for i, item in enumerate(manifests, start=1)]
    eligible = [market for market in markets if market.eligible]
    if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
        raise AnalysisError(
            f"Expected {EXPECTED_ELIGIBLE_MARKETS} eligible markets; found {len(eligible)}"
        )
    anchors: list[dict[str, Any]] = []
    vol_rows: list[dict[str, Any]] = []
    for market in eligible:
        indices = grid_indices(market)
        vol_rows.extend(volatility_rows(market, indices))
        for _, index in indices:
            row = evaluate_anchor(market, index)
            if row is not None:
                anchors.append(row)
    result = {
        "schema_version": "kxbtc15m_market_dynamics.v1",
        "analysis_type": "exploratory_development_census",
        "holdout_read": False,
        "outcomes_read": False,
        "fee_adjusted": False,
        "material_size": False,
        "grid_seconds": GRID_SECONDS,
        "drop_steps_dollars": list(DROP_STEPS),
        "bootstrap_reps": BOOTSTRAP_REPS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "summary": {
            "development_markets": len(markets),
            "eligible_markets": len(eligible),
            "excluded_markets": len(markets) - len(eligible),
            "anchors": len(anchors),
            "volatility_observations": len(vol_rows),
        },
        "exclusions": [
            {"market_index": m.index, "ticker": m.ticker, "reasons": list(m.exclusion_reasons)}
            for m in markets if not m.eligible
        ],
        "first_five_vs_later": summarize_anchor_groups(anchors, "first_five_minutes"),
        "by_elapsed_minute": summarize_anchor_groups(anchors, "elapsed_minute"),
        "by_time_phase": summarize_anchor_groups(anchors, "time_phase"),
        "by_entry_price_band": summarize_anchor_groups(anchors, "entry_price_band"),
        "by_time_price_cell": summarize_anchor_groups(anchors, "time_price_cell"),
        "volatility_by_elapsed_minute": summarize_volatility(vol_rows, "elapsed_minute"),
        "volatility_first_five_vs_later": summarize_volatility(
            vol_rows, "first_five_minutes"
        ),
        "volatility_by_time_phase": summarize_volatility(vol_rows, "time_phase"),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "kxbtc15m_market_dynamics_anchors.csv", anchors)
    write_csv(output_dir / "kxbtc15m_market_dynamics_volatility.csv", vol_rows)
    (output_dir / "kxbtc15m_market_dynamics.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "KXBTC15M_MARKET_DYNAMICS.md").write_text(
        markdown_report(result), encoding="utf-8"
    )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_source", type=Path, help="126-market audit ZIP or extracted directory")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("analysis/kxbtc15m_market_dynamics")
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.audit_source.exists():
        raise AnalysisError(f"Audit source does not exist: {args.audit_source}")
    if args.audit_source.is_dir():
        result = analyze(args.audit_source, args.output_dir)
    else:
        with TemporaryDirectory(prefix="kxbtc15m_dynamics_") as temp_dir:
            root = Path(temp_dir)
            safe_extract_zip(args.audit_source, root)
            result = analyze(root, args.output_dir)
    print(f"Eligible development markets: {result['summary']['eligible_markets']}")
    print(f"Five-second anchors: {result['summary']['anchors']}")
    print(f"Holdout read: {result['holdout_read']}")
    print(f"Fee adjusted: {result['fee_adjusted']}")
    print(f"Report: {args.output_dir / 'KXBTC15M_MARKET_DYNAMICS.md'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AnalysisError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Analysis failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
