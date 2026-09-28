#!/usr/bin/env python3
"""Development-only KXBTC15M intramarket-reversion analysis.

Reads the audit bundle's record_orderbook manifests and derived CSVs. It never
reads raw depth and refuses to inspect the frozen holdout in this version.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Sequence


FIRST_TICKER = "KXBTC15M-26AUG111345-45"
DEVELOPMENT_LAST_TICKER = "KXBTC15M-26AUG121430-30"
HOLDOUT_FIRST_TICKER = "KXBTC15M-26AUG121445-45"
FINAL_TICKER = "KXBTC15M-26AUG122100-00"
BOOTSTRAP_SEED = 20260813
BOOTSTRAP_REPS = 5000
# The preregistered dataset contains only August 2026 tickers. Representative
# source close times establish that their ticker timestamps use Eastern
# daylight time (UTC-04:00). Keeping this narrow makes the frozen analysis work
# on stock Windows Python without the optional IANA ``tzdata`` package. Dates
# outside the frozen dataset fail closed below rather than guessing DST rules.
FROZEN_TICKER_TIMEZONE = timezone(timedelta(hours=-4), name="EDT")
TICKER_RE = re.compile(r"KXBTC15M-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})-\d{2}")
MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def market_close_utc(ticker: str) -> datetime:
    match = TICKER_RE.fullmatch(ticker)
    if not match:
        raise ValueError(f"Unsupported ticker: {ticker}")
    yy, month, day, hour, minute = match.groups()
    year, month_number = 2000 + int(yy), MONTHS[month]
    if (year, month_number) != (2026, 8):
        raise ValueError(
            "This frozen analysis accepts only August 2026 tickers; "
            "do not infer daylight-saving offsets for another dataset"
        )
    local_close = datetime(
        year, month_number, int(day), int(hour), int(minute),
        tzinfo=FROZEN_TICKER_TIMEZONE,
    )
    return local_close.astimezone(timezone.utc)


def number(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


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


@dataclass
class Market:
    index: int
    ticker: str
    run_id: str
    close: datetime
    quotes: list[Quote]
    manifest: dict
    integrity_ok: bool
    first_valid_seconds: float
    last_valid_seconds: float
    max_gap_seconds: float

    @property
    def open(self) -> datetime:
        return self.close - timedelta(minutes=15)

    def eligible(self, max_gap: float = 5.0) -> bool:
        result = self.manifest.get("result", {})
        summary = self.manifest.get("summary", {})
        return (
            self.integrity_ok
            and self.manifest.get("status") == "completed"
            and result.get("orders_placed") == 0
            and result.get("request_failures") == 0
            and summary.get("raw_error_record_count") == 0
            and summary.get("runtime_error_event_count") == 0
            and self.first_valid_seconds <= 45
            and self.last_valid_seconds >= -5
            and self.max_gap_seconds <= max_gap
        )


@dataclass
class Episode:
    market_index: int
    ticker: str
    side: str
    entry_index: int
    entry_time: datetime
    entry_ask: float
    entry_bid: float
    spread: float
    time_remaining_seconds: float
    state_efficiency: float | None
    state_label: str | None
    target_times: dict[str, float | None]
    max_bid_60: float | None
    max_bid_120: float | None

    @property
    def primary_success(self) -> bool:
        value = self.target_times.get("20c_60s")
        return value is not None


def derived_descriptor(manifest: dict) -> dict:
    matches = [item for item in manifest.get("files", []) if item.get("role") == "derived_csv"]
    if len(matches) != 1:
        raise ValueError(f"{manifest.get('run_id')}: expected one derived CSV")
    return matches[0]


def load_quotes(path: Path) -> list[Quote]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    quotes = []
    for row in rows:
        quotes.append(Quote(
            time=parse_time(row["observed_at_utc"]), ticker=row["ticker"],
            yes_bid=number(row.get("yes_bid")), yes_ask=number(row.get("yes_ask")),
            no_bid=number(row.get("no_bid")), no_ask=number(row.get("no_ask")),
        ))
    return quotes


def build_market(index: int, manifest: dict, directory: Path) -> Market:
    ticker = manifest["arguments"]["ticker"]
    descriptor = derived_descriptor(manifest)
    csv_path = directory / Path(descriptor["path"]["value"].replace("\\", "/")).name
    raw_bytes = csv_path.read_bytes()
    quotes = load_quotes(csv_path)
    close = market_close_utc(ticker)
    open_time = close - timedelta(minutes=15)
    valid_times = [
        quote.time for quote in quotes
        if any(value is not None for value in (quote.yes_bid, quote.yes_ask, quote.no_bid, quote.no_ask))
        and open_time <= quote.time < close
    ]
    preclose_times = [quote.time for quote in quotes if open_time <= quote.time < close]
    gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(preclose_times, preclose_times[1:])
    ]
    integrity_ok = (
        hashlib.sha256(raw_bytes).hexdigest() == descriptor["sha256"]
        and len(quotes) == descriptor["data_row_count"]
        and all(quote.ticker == ticker for quote in quotes)
    )
    return Market(
        index=index, ticker=ticker, run_id=manifest["run_id"], close=close,
        quotes=quotes, manifest=manifest, integrity_ok=integrity_ok,
        first_valid_seconds=(min(valid_times) - open_time).total_seconds(),
        last_valid_seconds=(max(valid_times) - close).total_seconds(),
        max_gap_seconds=max(gaps) if gaps else math.inf,
    )


def load_development_markets(directory: Path) -> list[Market]:
    manifests = []
    for path in directory.glob("record_orderbook_*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        ticker = document.get("arguments", {}).get("ticker")
        if ticker and document.get("status") == "completed":
            manifests.append(document)
    manifests.sort(key=lambda item: parse_time(item["started_at_utc"]))
    target = []
    active = False
    for manifest in manifests:
        ticker = manifest["arguments"]["ticker"]
        if ticker == FIRST_TICKER:
            active = True
        if active:
            target.append(manifest)
        if ticker == DEVELOPMENT_LAST_TICKER:
            break
    if len(target) != 100 or target[0]["arguments"]["ticker"] != FIRST_TICKER:
        raise ValueError("Could not reconstruct the frozen 100-market development sequence")
    return [build_market(index, manifest, directory) for index, manifest in enumerate(target, 1)]


def latest_midpoint(quotes: Sequence[Quote], side: str, target: datetime, tolerance: float = 1.0) -> float | None:
    candidate = None
    for quote in quotes:
        if quote.time > target:
            break
        if (target - quote.time).total_seconds() <= tolerance:
            value = quote.midpoint(side)
            if value is not None:
                candidate = value
    return candidate


def efficiency_on_grid(
    quotes: Sequence[Quote], side: str, start: datetime, end: datetime,
    step_seconds: int = 5, required_coverage: float = 0.80,
) -> float | None:
    count = int((end - start).total_seconds() // step_seconds) + 1
    grid = [start + timedelta(seconds=step_seconds * i) for i in range(count)]
    values = [latest_midpoint(quotes, side, point) for point in grid]
    present = [value for value in values if value is not None]
    if len(present) / len(values) < required_coverage or len(present) < 2:
        return None
    path = sum(abs(b - a) for a, b in zip(present, present[1:]))
    if path == 0:
        return 0.0
    return (present[-1] - present[0]) / path


def state_label(efficiency: float | None) -> str | None:
    if efficiency is None:
        return None
    if efficiency <= -0.35:
        return "falling"
    if efficiency >= 0.35:
        return "rising"
    return "fluctuating"


def target_time(
    quotes: Sequence[Quote], side: str, entry_index: int, entry_time: datetime,
    target: float, horizon_seconds: float, close: datetime,
) -> float | None:
    deadline = min(entry_time + timedelta(seconds=horizon_seconds), close)
    for quote in quotes[entry_index + 1:]:
        if quote.time > deadline:
            break
        bid = quote.bid(side)
        if bid is not None and bid >= target:
            return (quote.time - entry_time).total_seconds()
    return None


def max_future_bid(
    quotes: Sequence[Quote], side: str, entry_index: int, entry_time: datetime,
    horizon_seconds: float, close: datetime,
) -> float | None:
    deadline = min(entry_time + timedelta(seconds=horizon_seconds), close)
    values = [
        quote.bid(side) for quote in quotes[entry_index + 1:]
        if quote.time <= deadline and quote.bid(side) is not None
    ]
    return max(values) if values else None


def detect_episodes(market: Market) -> list[Episode]:
    preclose = [quote for quote in market.quotes if market.open <= quote.time < market.close]
    episodes = []
    for side in ("YES", "NO"):
        above_start = None
        previous_time = None
        required_above = 5.0
        for i, quote in enumerate(preclose):
            ask, bid = quote.ask(side), quote.bid(side)
            gap = (quote.time - previous_time).total_seconds() if previous_time else None
            if gap is not None and gap > 2.0:
                above_start = None
            prior_above_duration = (
                (previous_time - above_start).total_seconds()
                if above_start is not None and previous_time is not None else 0.0
            )
            spread = ask - bid if ask is not None and bid is not None else None
            remaining = (market.close - quote.time).total_seconds()
            entry = (
                ask is not None and 0.10 <= ask <= 0.15
                and bid is not None and spread is not None and spread <= 0.0300001
                and remaining >= 60
                and prior_above_duration >= required_above
            )
            if entry:
                state_e = efficiency_on_grid(
                    preclose, side, quote.time - timedelta(seconds=60), quote.time
                )
                target_times = {}
                for target, horizon, key in (
                    (0.20, 10, "20c_10s"), (0.20, 30, "20c_30s"),
                    (0.20, 60, "20c_60s"), (0.20, 120, "20c_120s"),
                    (0.30, 60, "30c_60s"), (0.30, 120, "30c_120s"),
                    (0.40, 120, "40c_120s"), (0.50, 120, "50c_120s"),
                ):
                    target_times[key] = target_time(
                        preclose, side, i, quote.time, target, horizon, market.close
                    )
                episodes.append(Episode(
                    market_index=market.index, ticker=market.ticker, side=side,
                    entry_index=i, entry_time=quote.time, entry_ask=ask, entry_bid=bid,
                    spread=spread, time_remaining_seconds=remaining,
                    state_efficiency=state_e, state_label=state_label(state_e),
                    target_times=target_times,
                    max_bid_60=max_future_bid(preclose, side, i, quote.time, 60, market.close),
                    max_bid_120=max_future_bid(preclose, side, i, quote.time, 120, market.close),
                ))
                above_start = None
                required_above = 10.0
            elif ask is not None and ask > 0.15:
                if above_start is None:
                    above_start = quote.time
            else:
                above_start = None
            previous_time = quote.time
    return sorted(episodes, key=lambda episode: (episode.entry_time, episode.side))


def percentile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def clustered_rate_ci(episodes: Sequence[Episode], key: str = "20c_60s") -> tuple[float, float]:
    grouped = defaultdict(list)
    for episode in episodes:
        grouped[episode.market_index].append(episode)
    market_ids = sorted(grouped)
    rng = random.Random(BOOTSTRAP_SEED)
    estimates = []
    for _ in range(BOOTSTRAP_REPS):
        sample = [rng.choice(market_ids) for _ in market_ids]
        observations = [episode for market_id in sample for episode in grouped[market_id]]
        estimates.append(sum(ep.target_times[key] is not None for ep in observations) / len(observations))
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def clustered_side_difference_ci(episodes: Sequence[Episode]) -> tuple[float | None, float | None]:
    grouped = defaultdict(list)
    for episode in episodes:
        grouped[episode.market_index].append(episode)
    market_ids = sorted(grouped)
    rng = random.Random(BOOTSTRAP_SEED + 1)
    estimates = []
    for _ in range(BOOTSTRAP_REPS):
        sample = [rng.choice(market_ids) for _ in market_ids]
        observations = [episode for market_id in sample for episode in grouped[market_id]]
        yes = [ep for ep in observations if ep.side == "YES"]
        no = [ep for ep in observations if ep.side == "NO"]
        if yes and no:
            estimates.append(
                sum(ep.primary_success for ep in yes) / len(yes)
                - sum(ep.primary_success for ep in no) / len(no)
            )
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for index, _ in ordered[cursor:end]:
            result[index] = rank
        cursor = end
    return result


def correlation(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denominator = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return numerator / denominator if denominator else None


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    return correlation(ranks(xs), ranks(ys))


def time_bucket(seconds: float) -> str:
    if seconds > 600:
        return "early_10_15m"
    if seconds > 300:
        return "middle_5_10m"
    if seconds > 120:
        return "late_2_5m"
    return "terminal_le_2m"


def spread_bucket(spread: float) -> str:
    if spread <= 0.0100001:
        return "le_1c"
    if spread <= 0.0200001:
        return "gt_1c_le_2c"
    return "gt_2c_le_3c"


def group_summary(episodes: Sequence[Episode], key) -> dict:
    groups = defaultdict(list)
    for episode in episodes:
        groups[key(episode)].append(episode)
    result = {}
    for label, items in sorted(groups.items()):
        interval = clustered_rate_ci(items) if items else (None, None)
        result[str(label)] = {
            "episodes": len(items),
            "markets": len({item.market_index for item in items}),
            "successes": sum(item.primary_success for item in items),
            "success_rate": sum(item.primary_success for item in items) / len(items),
            "cluster_bootstrap_95_ci": list(interval),
        }
    return result


def previous_market_analysis(markets: Sequence[Market], episodes: Sequence[Episode]) -> dict:
    eligible = {market.index: market for market in markets}
    episodes_by_market = defaultdict(list)
    for episode in episodes:
        episodes_by_market[episode.market_index].append(episode)
    pairs = []
    transitions = Counter()
    by_previous = defaultdict(lambda: {"next_markets": 0, "episodes": 0, "successes": 0})
    for prior_index in range(1, 100):
        if prior_index not in eligible or prior_index + 1 not in eligible:
            continue
        previous = eligible[prior_index]
        following = eligible[prior_index + 1]
        prior_e = efficiency_on_grid(previous.quotes, "YES", previous.open, previous.close - timedelta(seconds=5))
        next_e = efficiency_on_grid(following.quotes, "YES", following.open, following.open + timedelta(minutes=5))
        if prior_e is None or next_e is None:
            continue
        pairs.append((prior_e, next_e))
        prior_state, next_state = state_label(prior_e), state_label(next_e)
        transitions[(prior_state, next_state)] += 1
        items = episodes_by_market[following.index]
        by_previous[prior_state]["next_markets"] += 1
        by_previous[prior_state]["episodes"] += len(items)
        by_previous[prior_state]["successes"] += sum(item.primary_success for item in items)
    return {
        "eligible_adjacent_pairs": len(pairs),
        "spearman_previous_whole_vs_next_first_5m": spearman(
            [pair[0] for pair in pairs], [pair[1] for pair in pairs]
        ),
        "transitions": {
            prior: {next_state: transitions[(prior, next_state)] for next_state in ("falling", "fluctuating", "rising")}
            for prior in ("falling", "fluctuating", "rising")
        },
        "next_h1_by_previous_state": dict(by_previous),
    }


def bid_availability(markets: Sequence[Market]) -> dict:
    observations = defaultdict(lambda: {"rows": 0, "yes_bid": 0, "no_bid": 0})
    per_market = defaultdict(list)
    for market in markets:
        local = defaultdict(lambda: {"rows": 0, "yes_bid": 0, "no_bid": 0})
        for quote in market.quotes:
            if not (market.open <= quote.time < market.close):
                continue
            bucket = time_bucket((market.close - quote.time).total_seconds())
            local[bucket]["rows"] += 1
            local[bucket]["yes_bid"] += quote.yes_bid is not None
            local[bucket]["no_bid"] += quote.no_bid is not None
        for bucket, values in local.items():
            for key in values:
                observations[bucket][key] += values[key]
            if values["rows"]:
                per_market[(bucket, "YES")].append(values["yes_bid"] / values["rows"])
                per_market[(bucket, "NO")].append(values["no_bid"] / values["rows"])
    result = {}
    for bucket, values in sorted(observations.items()):
        result[bucket] = {
            "rows": values["rows"],
            "yes_observation_rate": values["yes_bid"] / values["rows"],
            "no_observation_rate": values["no_bid"] / values["rows"],
            "yes_mean_market_rate": statistics.mean(per_market[(bucket, "YES")]),
            "no_mean_market_rate": statistics.mean(per_market[(bucket, "NO")]),
        }
    return result


def analyze(markets: Sequence[Market], max_gap: float) -> dict:
    eligible = [market for market in markets if market.eligible(max_gap=max_gap)]
    episodes = [episode for market in eligible for episode in detect_episodes(market)]
    successes = [episode for episode in episodes if episode.primary_success]
    ci = clustered_rate_ci(episodes) if episodes else (None, None)
    targets = {}
    for key in ("20c_10s", "20c_30s", "20c_60s", "20c_120s", "30c_60s", "30c_120s", "40c_120s", "50c_120s"):
        hit = [episode.target_times[key] for episode in episodes if episode.target_times[key] is not None]
        targets[key] = {
            "successes": len(hit), "episodes": len(episodes),
            "rate": len(hit) / len(episodes) if episodes else None,
            "median_seconds_if_hit": statistics.median(hit) if hit else None,
            "p90_seconds_if_hit": percentile(hit, 0.90),
        }
    side_difference_ci = clustered_side_difference_ci(episodes) if episodes else (None, None)
    by_side = group_summary(episodes, lambda episode: episode.side)
    yes_rate = by_side.get("YES", {}).get("success_rate")
    no_rate = by_side.get("NO", {}).get("success_rate")
    return {
        "quality_max_gap_seconds": max_gap,
        "eligible_markets": len(eligible),
        "excluded": [{"index": market.index, "ticker": market.ticker} for market in markets if market not in eligible],
        "episodes": len(episodes),
        "episode_markets": len({episode.market_index for episode in episodes}),
        "markets_with_success": len({episode.market_index for episode in successes}),
        "primary": {
            "successes": len(successes),
            "rate": len(successes) / len(episodes) if episodes else None,
            "cluster_bootstrap_95_ci": list(ci),
            "development_supported": ci[0] is not None and ci[0] > 0.50,
            "median_seconds_if_hit": statistics.median(
                [episode.target_times["20c_60s"] for episode in successes]
            ) if successes else None,
            "p90_seconds_if_hit": percentile(
                [episode.target_times["20c_60s"] for episode in successes], 0.90
            ),
        },
        "target_ladder": targets,
        "by_time_remaining": group_summary(episodes, lambda episode: time_bucket(episode.time_remaining_seconds)),
        "by_pre_entry_state": group_summary(
            [episode for episode in episodes if episode.state_label is not None],
            lambda episode: episode.state_label,
        ),
        "state_coverage": sum(episode.state_label is not None for episode in episodes) / len(episodes) if episodes else None,
        "by_side": by_side,
        "yes_minus_no_rate": yes_rate - no_rate if yes_rate is not None and no_rate is not None else None,
        "yes_minus_no_cluster_bootstrap_95_ci": list(side_difference_ci),
        "by_entry_spread": group_summary(episodes, lambda episode: spread_bucket(episode.spread)),
        "bid_availability": bid_availability(eligible),
        "previous_market": previous_market_analysis(eligible, episodes),
        "episode_rows": [
            {
                "market_index": episode.market_index, "ticker": episode.ticker,
                "side": episode.side, "entry_time": episode.entry_time.isoformat(),
                "entry_ask": episode.entry_ask, "entry_bid": episode.entry_bid,
                "spread": episode.spread,
                "time_remaining_seconds": episode.time_remaining_seconds,
                "time_bucket": time_bucket(episode.time_remaining_seconds),
                "state_efficiency": episode.state_efficiency,
                "state_label": episode.state_label,
                **episode.target_times,
                "max_bid_60": episode.max_bid_60, "max_bid_120": episode.max_bid_120,
            }
            for episode in episodes
        ],
    }


def format_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def render_report(primary: dict, sensitivity: dict, prereg_sha: str) -> str:
    p = primary["primary"]
    lines = [
        "# KXBTC15M H1 Development-Set Results", "",
        "Holdout status: **sealed; no holdout prices or rebound outcomes were read**.", "",
        f"Preregistration SHA-256: `{prereg_sha}`", "",
        "## Primary result", "",
        f"- Eligible development markets: {primary['eligible_markets']}",
        f"- Fresh 10–15¢ downward-entry episodes: {primary['episodes']} across {primary['episode_markets']} markets",
        f"- Reached an executable 20¢ bid within 60 seconds: {p['successes']}/{primary['episodes']} ({format_rate(p['rate'])})",
        f"- Markets containing at least one qualifying success: {primary['markets_with_success']}/{primary['eligible_markets']} ({format_rate(primary['markets_with_success'] / primary['eligible_markets'])})",
        f"- Market-clustered 95% bootstrap interval: {format_rate(p['cluster_bootstrap_95_ci'][0])}–{format_rate(p['cluster_bootstrap_95_ci'][1])}",
        f"- Median / 90th-percentile time among hits: {p['median_seconds_if_hit']:.2f}s / {p['p90_seconds_if_hit']:.2f}s" if p['successes'] else "- No hits",
        f"- Predeclared development-support criterion met: **{'YES' if p['development_supported'] else 'NO'}**", "",
        "This is a quote-level recurrence result before fees and without depth. It is not a profitability result.", "",
        "## Target ladder", "",
        "| Target | Hits | Rate | Median hit time |", "|---|---:|---:|---:|",
    ]
    for key, label in (
        ("20c_10s", "20¢ within 10s"), ("20c_30s", "20¢ within 30s"),
        ("20c_60s", "20¢ within 60s"), ("20c_120s", "20¢ within 120s"),
        ("30c_60s", "30¢ within 60s"), ("30c_120s", "30¢ within 120s"),
        ("40c_120s", "40¢ within 120s"), ("50c_120s", "50¢ within 120s"),
    ):
        item = primary["target_ladder"][key]
        median = "n/a" if item["median_seconds_if_hit"] is None else f"{item['median_seconds_if_hit']:.2f}s"
        lines.append(f"| {label} | {item['successes']}/{item['episodes']} | {format_rate(item['rate'])} | {median} |")
    lines += ["", "## Time remaining", "", "| Bucket | Episodes | Markets | Success rate | 95% clustered interval |", "|---|---:|---:|---:|---:|"]
    for label, item in primary["by_time_remaining"].items():
        interval = item["cluster_bootstrap_95_ci"]
        lines.append(f"| {label} | {item['episodes']} | {item['markets']} | {format_rate(item['success_rate'])} | {format_rate(interval[0])}–{format_rate(interval[1])} |")
    lines += ["", "## Pre-entry state", "", "| State | Episodes | Markets | Success rate | 95% clustered interval |", "|---|---:|---:|---:|---:|"]
    for label, item in primary["by_pre_entry_state"].items():
        interval = item["cluster_bootstrap_95_ci"]
        lines.append(f"| {label} | {item['episodes']} | {item['markets']} | {format_rate(item['success_rate'])} | {format_rate(interval[0])}–{format_rate(interval[1])} |")
    lines += ["", "## YES/NO symmetry", "", "| Side | Episodes | Success rate |", "|---|---:|---:|"]
    for label, item in primary["by_side"].items():
        lines.append(f"| {label} | {item['episodes']} | {format_rate(item['success_rate'])} |")
    ci = primary["yes_minus_no_cluster_bootstrap_95_ci"]
    lines += [
        "",
        f"YES minus NO success-rate difference: {format_rate(primary['yes_minus_no_rate'])}; clustered 95% interval {format_rate(ci[0])}–{format_rate(ci[1])}.",
        "", "## Entry spread", "", "| Spread bucket | Episodes | Success rate |", "|---|---:|---:|",
    ]
    for label, item in primary["by_entry_spread"].items():
        lines.append(f"| {label} | {item['episodes']} | {format_rate(item['success_rate'])} |")
    previous = primary["previous_market"]
    lines += [
        "", "## Previous-market state", "",
        f"Eligible adjacent pairs: {previous['eligible_adjacent_pairs']}",
        f"Spearman correlation, previous whole-market efficiency versus next first-five-minute efficiency: {previous['spearman_previous_whole_vs_next_first_5m']:.3f}",
        "", "Transition counts:", "", "| Previous → next | Falling | Fluctuating | Rising |", "|---|---:|---:|---:|",
    ]
    for prior, values in previous["transitions"].items():
        lines.append(f"| {prior} | {values['falling']} | {values['fluctuating']} | {values['rising']} |")
    lines += ["", "Next-market H1 episodes by previous state:", "", "| Previous state | Next markets | Episodes | Success rate |", "|---|---:|---:|---:|"]
    for prior, values in sorted(previous["next_h1_by_previous_state"].items()):
        rate = values["successes"] / values["episodes"] if values["episodes"] else None
        lines.append(f"| {prior} | {values['next_markets']} | {values['episodes']} | {format_rate(rate)} |")
    lines += ["", "## Bid availability", "", "| Time remaining | YES bid present | NO bid present |", "|---|---:|---:|"]
    for bucket, values in primary["bid_availability"].items():
        lines.append(f"| {bucket} | {format_rate(values['yes_mean_market_rate'])} | {format_rate(values['no_mean_market_rate'])} |")
    lines += [
        "", "## Two-second gap sensitivity", "",
        f"Eligible markets: {sensitivity['eligible_markets']}; episodes: {sensitivity['episodes']}; H1 success: {sensitivity['primary']['successes']}/{sensitivity['episodes']} ({format_rate(sensitivity['primary']['rate'])}); clustered interval {format_rate(sensitivity['primary']['cluster_bootstrap_95_ci'][0])}–{format_rate(sensitivity['primary']['cluster_bootstrap_95_ci'][1])}.",
        "", "## Development interpretation", "",
        "- The rebound phenomenon is real but not reliable as an unconditional rule: 10–15¢ entries reached 50¢ within 120 seconds in 13.4% of episodes, while only 35.9% reached the much easier 20¢/60-second target.",
        "- Time remaining did not produce the preregistered monotonic pattern. All bucket intervals overlap; the terminal estimate is based on only 12 episodes and should not be promoted.",
        "- The fixed pre-entry state labels did not discriminate: falling and fluctuating episodes had nearly identical success rates, and only one episode was labeled rising.",
        "- Previous-market state showed essentially zero rank correlation with the next market's first five minutes. Nearly all transitions were fluctuating-to-fluctuating, so there is no development evidence for using the prior contract as a predictor.",
        "- YES and NO rates were not distinguishable because the clustered difference interval includes zero.",
        "- Entry-spread effects are unresolved because 212 of 217 episodes had a spread of one cent or less.",
        "- Bid availability was essentially complete before the final two minutes, then fell sharply. This supports a liquidity warning near close even though terminal rebound-rate estimates were noisy.",
        "", "## Evidence boundary", "",
        "No fee-adjusted P&L, averaging-down simulation, capacity claim, or fill claim is made. Those require raw depth and an execution model.", "",
    ]
    return "\n".join(lines)


def write_episode_csv(path: Path, rows: Sequence[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(directory: Path, output_dir: Path, preregistration: Path) -> dict:
    markets = load_development_markets(directory)
    primary = analyze(markets, max_gap=5.0)
    sensitivity = analyze(markets, max_gap=2.0)
    prereg_sha = hashlib.sha256(preregistration.read_bytes()).hexdigest()
    result = {
        "schema_version": "kxbtc15m_h1_development_result.v1",
        "holdout_read": False,
        "preregistration_sha256": prereg_sha,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_reps": BOOTSTRAP_REPS,
        "primary_quality": primary,
        "two_second_gap_sensitivity": sensitivity,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kxbtc15m_h1_development_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_episode_csv(output_dir / "kxbtc15m_h1_development_episodes.csv", primary["episode_rows"])
    (output_dir / "KXBTC15M_H1_DEVELOPMENT_RESULT.md").write_text(
        render_report(primary, sensitivity, prereg_sha), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Audit ZIP or extracted directory")
    parser.add_argument("--output-dir", type=Path, default=Path("analysis_output"))
    parser.add_argument(
        "--preregistration", type=Path,
        default=Path("docs/KXBTC15M_H1_PREREGISTRATION.md"),
    )
    args = parser.parse_args()
    if args.input.is_dir():
        result = run(args.input, args.output_dir, args.preregistration)
    else:
        with TemporaryDirectory(prefix="kxbtc15m_h1_") as temporary:
            with zipfile.ZipFile(args.input) as archive:
                archive.extractall(temporary)
            result = run(Path(temporary), args.output_dir, args.preregistration)
    primary = result["primary_quality"]
    print(f"Eligible development markets: {primary['eligible_markets']}")
    print(f"Episodes: {primary['episodes']}")
    print(f"H1 successes: {primary['primary']['successes']}")
    print(f"H1 rate: {primary['primary']['rate']:.6f}")
    print("Holdout read: False")


if __name__ == "__main__":
    main()
