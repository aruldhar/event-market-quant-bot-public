#!/usr/bin/env python3
"""Collapse the H3 state grid into one first qualifying trigger per market.

This is a post-diagnostic development confirmation, not a pristine experiment.
The primary candidate combines the two adjacent positive H3 cells observed in
the state audit: 90c <= favored midpoint < 98c with more than 240 and at most
300 seconds remaining.  The exit remains target-or-preclose-10s.

No raw data, external BTC data, or holdout data are opened by this script.  It
only reduces the previously generated development scenario CSV.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence


EXPECTED_SCENARIO_ROWS = 17_280
EXPECTED_MARKETS = 96
EXIT_POLICY = "target_or_preclose_10s"

CANDIDATES = (
    ("primary_90_98c", 0.90, 0.98),
    ("diagnostic_90_95c", 0.90, 0.95),
    ("diagnostic_95_98c", 0.95, 0.98),
)

REQUIRED_FIELDS = {
    "ticker",
    "market_index",
    "diagnostic_segment",
    "decision_time",
    "seconds_remaining",
    "decision_favored_midpoint",
    "exit_policy",
    "status",
    "pnl",
    "profitable",
    "favored_side_won",
    "target_achieved_after_latency",
    "exit_reason",
    "total_fees",
    "holdout_read",
    "external_btc_data_used",
}


class TriggerError(RuntimeError):
    """Raised when the prior H3 output violates the frozen reduction gate."""


def parse_bool(value: Any) -> bool:
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise TriggerError(f"invalid boolean value: {value!r}")


def load_scenarios(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or ())
        missing = REQUIRED_FIELDS - fields
        if missing:
            raise TriggerError(f"scenario CSV missing fields: {sorted(missing)}")
        rows = list(reader)
    if len(rows) != EXPECTED_SCENARIO_ROWS:
        raise TriggerError(
            f"expected {EXPECTED_SCENARIO_ROWS} H3 scenario rows; found {len(rows)}"
        )
    markets = {row["ticker"] for row in rows}
    if len(markets) != EXPECTED_MARKETS:
        raise TriggerError(f"expected {EXPECTED_MARKETS} markets; found {len(markets)}")
    if any(parse_bool(row["holdout_read"]) for row in rows):
        raise TriggerError("H3 scenario input reports a holdout read")
    if any(parse_bool(row["external_btc_data_used"]) for row in rows):
        raise TriggerError("H3 scenario input reports external BTC data")
    return rows


def qualifies(row: Mapping[str, Any], low: float, high: float) -> bool:
    if row["exit_policy"] != EXIT_POLICY:
        return False
    remaining_text = str(row.get("seconds_remaining", "")).strip()
    probability_text = str(row.get("decision_favored_midpoint", "")).strip()
    if not remaining_text or not probability_text:
        return False
    remaining = float(remaining_text)
    probability = float(probability_text)
    return 240 < remaining <= 300 and low <= probability < high


def first_triggers(
    rows: Sequence[Mapping[str, Any]],
    *,
    candidate: str,
    low: float,
    high: float,
) -> list[dict[str, Any]]:
    by_market: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if qualifies(row, low, high):
            by_market.setdefault(str(row["ticker"]), []).append(row)
    output: list[dict[str, Any]] = []
    for ticker, candidates in sorted(by_market.items()):
        first = min(candidates, key=lambda row: str(row["decision_time"]))
        converted = dict(first)
        converted.update({
            "candidate": candidate,
            "candidate_probability_low": low,
            "candidate_probability_high_exclusive": high,
            "first_trigger_in_market": True,
        })
        output.append(converted)
    return output


def percentile(values: Sequence[float], probability: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(probability * len(ordered)) - 1))
    return ordered[index]


def mean_ci(rows: Sequence[Mapping[str, Any]]) -> tuple[float, float, float]:
    values = [float(row["pnl"]) for row in rows]
    if not values:
        return math.nan, math.nan, math.nan
    estimate = statistics.mean(values)
    if len(values) < 2:
        return estimate, math.nan, math.nan
    rng = random.Random(20260813)
    samples = [statistics.mean(rng.choices(values, k=len(values))) for _ in range(2_000)]
    samples.sort()
    return estimate, samples[49], samples[1949]


def summarize_group(
    triggers: Sequence[Mapping[str, Any]],
    *,
    candidate: str,
    segment: str,
) -> dict[str, Any]:
    if segment == "all_96":
        selected = list(triggers)
    else:
        key = "earlier_64" if segment == "earlier_64_diagnostic" else "later_32"
        selected = [row for row in triggers if row["diagnostic_segment"] == key]
    completed = [row for row in selected if row["status"] == "completed"]
    pnl = [float(row["pnl"]) for row in completed]
    mean, low, high = mean_ci(completed)
    return {
        "candidate": candidate,
        "segment": segment,
        "eligible_markets_in_segment": (
            96 if segment == "all_96" else 64 if segment == "earlier_64_diagnostic" else 32
        ),
        "triggered_markets": len(selected),
        "completed_trades": len(completed),
        "mean_pnl_per_triggered_market": mean,
        "mean_pnl_bootstrap_ci_low": low,
        "mean_pnl_bootstrap_ci_high": high,
        "median_pnl": statistics.median(pnl) if pnl else math.nan,
        "pnl_05_quantile": percentile(pnl, 0.05),
        "worst_pnl": min(pnl) if pnl else math.nan,
        "profitable_rate": statistics.mean(parse_bool(row["profitable"]) for row in completed)
        if completed else math.nan,
        "favored_side_win_rate": statistics.mean(parse_bool(row["favored_side_won"]) for row in completed)
        if completed else math.nan,
        "target_hit_rate": statistics.mean(
            parse_bool(row["target_achieved_after_latency"]) for row in completed
        ) if completed else math.nan,
        "settlement_fallback_rate": statistics.mean(
            "settlement" in str(row["exit_reason"]) for row in completed
        ) if completed else math.nan,
        "mean_total_fees": statistics.mean(float(row["total_fees"]) for row in completed)
        if completed else math.nan,
        "holdout_read": False,
        "external_btc_data_used": False,
    }


def summarize(triggers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candidate, _, _ in CANDIDATES:
        subset = [row for row in triggers if row["candidate"] == candidate]
        for segment in ("all_96", "earlier_64_diagnostic", "later_32_diagnostic"):
            output.append(summarize_group(subset, candidate=candidate, segment=segment))
    return output


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise TriggerError(f"refusing empty output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def money(value: float) -> str:
    return "n/a" if math.isnan(value) else f"${value:.2f}"


def percent(value: float) -> str:
    return "n/a" if math.isnan(value) else f"{value:.1%}"


def markdown_report(summary: Sequence[Mapping[str, Any]]) -> str:
    lines = [
        "# KXBTC15M H3 first-trigger confirmation",
        "",
        "**Post-diagnostic development reduction; holdout sealed.**",
        "",
        "The primary rule enters at the first five-second grid observation in each market with "
        "240–300 seconds remaining and a favored midpoint from 90 cents inclusive to 98 cents "
        "exclusive. It reuses the frozen one-second-latency, full-depth, $100, $1-target, and "
        "10-second-preclose exit simulation.",
        "",
        "The 90–95 and 95–98 cent rows are component diagnostics. They are not additional "
        "independent experiments.",
        "",
        "| Candidate | Segment | Triggered markets | Mean P&L | Bootstrap 95% CI | Profitable | Favored side won | Target hit | 5% tail | Worst |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['candidate']} | {row['segment']} | {row['triggered_markets']} | "
            f"{money(float(row['mean_pnl_per_triggered_market']))} | "
            f"{money(float(row['mean_pnl_bootstrap_ci_low']))} to "
            f"{money(float(row['mean_pnl_bootstrap_ci_high']))} | "
            f"{percent(float(row['profitable_rate']))} | "
            f"{percent(float(row['favored_side_win_rate']))} | "
            f"{percent(float(row['target_hit_rate']))} | "
            f"{money(float(row['pnl_05_quantile']))} | "
            f"{money(float(row['worst_pnl']))} |"
        )
    lines.extend([
        "",
        "Because the candidate was selected after reviewing the same 96 development markets, "
        "a positive result is evidence of implementability and stability—not an unbiased edge "
        "estimate. Do not open the existing holdout while other strategy ideas are still being "
        "compared. A surviving rule should later be frozen against prospective markets or the "
        "single final untouched test chosen for the project.",
    ])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenarios_csv", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("analysis/kxbtc15m_h3_first_trigger"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_scenarios(args.scenarios_csv)
    triggers: list[dict[str, Any]] = []
    for candidate, low, high in CANDIDATES:
        triggers.extend(first_triggers(
            rows,
            candidate=candidate,
            low=low,
            high=high,
        ))
    summary = summarize(triggers)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "kxbtc15m_h3_first_triggers.csv", triggers)
    write_csv(args.output_dir / "kxbtc15m_h3_first_trigger_summary.csv", summary)
    report_path = args.output_dir / "KXBTC15M_H3_FIRST_TRIGGER.md"
    report_path.write_text(markdown_report(summary), encoding="utf-8")

    primary = next(
        row for row in summary
        if row["candidate"] == "primary_90_98c" and row["segment"] == "all_96"
    )
    print("KXBTC15M H3 first-trigger confirmation: PASS")
    print(f"Development markets in input: {EXPECTED_MARKETS}")
    print(f"Primary triggered markets: {primary['triggered_markets']}")
    print("Primary entry: first 90-98c favored midpoint with 240-300 seconds remaining")
    print("Exit: $1 net target or executable liquidation 10 seconds before close")
    print("External BTC data used: no")
    print("Holdout read: False")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, TriggerError, ValueError) as exc:
        raise SystemExit(f"H3 first-trigger error: {exc}") from exc
