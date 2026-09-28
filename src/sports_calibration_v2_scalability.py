"""Outcome-blind scalability gates for the redesigned Sports calibration experiment.

This module consumes only the derived quote/identity tables from the exact-time
historical collector. It must run before any final YES/NO outcome is materialized.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from .historical_feasibility import HistoricalFeasibilityRows
from .historical_feasibility_schema import (
    MIN_EVENT_ANY_QUOTE_COVERAGE,
    MIN_EVENT_BAND_COVERAGE,
    MIN_MARKET_ANY_QUOTE_COVERAGE,
)

SPORTS_V2_SCALABILITY_SCHEMA_VERSION = "sports_calibration_v2_scalability.v1"
SPORTS_V2_SCALABILITY_MIN_EVENTS = 100
SPORTS_V2_MAX_MARKETS_PER_EVENT = 2
SPORTS_V2_SERIES_WARNING_SHARE = Decimal("0.25")
SPORTS_V2_SERIES_BLOCK_SHARE = Decimal("0.50")


class SportsV2ScalabilityError(RuntimeError):
    """Raised when the pre-outcome scalability evidence is invalid."""




def validate_sports_v2_requested_event_count(value: int) -> int:
    """Reject any dedicated scalability run smaller than the frozen 100-event gate."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Sports V2 requested event count must be an integer")
    if value < SPORTS_V2_SCALABILITY_MIN_EVENTS:
        raise ValueError(
            f"Sports V2 requested event count cannot be below {SPORTS_V2_SCALABILITY_MIN_EVENTS}"
        )
    return value

def build_sports_v2_scalability_summary(
    rows: HistoricalFeasibilityRows,
) -> dict[str, Any]:
    """Build the frozen pre-outcome 100-event Sports scalability decision.

    Facts measured here are data availability and concentration only. No final
    result field is permitted anywhere in the input tables.
    """

    _reject_outcomes(rows)

    non_sports_events = [row for row in rows.events if row.get("category") != "Sports"]
    non_sports_markets = [row for row in rows.markets if row.get("category") != "Sports"]
    non_sports_obs = [row for row in rows.observations if row.get("category") != "Sports"]
    if non_sports_events or non_sports_markets or non_sports_obs:
        raise SportsV2ScalabilityError(
            "Sports V2 scalability input must contain Sports-derived rows only"
        )

    sports_summary = next(
        (row for row in rows.category_summary if row.get("category") == "Sports"),
        None,
    )
    if sports_summary is None:
        raise SportsV2ScalabilityError("Sports category summary row is missing")

    event_count = len(rows.events)
    event_tickers = {row["event_ticker"] for row in rows.events}
    if len(event_tickers) != event_count:
        raise SportsV2ScalabilityError("duplicate Sports event_ticker in scalability input")

    series_counts = Counter(row["series_ticker"] for row in rows.events)
    if not series_counts and event_count:
        raise SportsV2ScalabilityError("Sports events are missing series identity")
    ranked_series = sorted(series_counts.items(), key=lambda item: (-item[1], item[0]))
    dominant_series_ticker = ranked_series[0][0] if ranked_series else ""
    dominant_series_event_count = ranked_series[0][1] if ranked_series else 0
    dominant_series_event_share = (
        Decimal(dominant_series_event_count) / Decimal(event_count)
        if event_count
        else Decimal(0)
    )

    event_quote_coverage = _decimal(sports_summary, "event_any_quote_coverage")
    market_quote_coverage = _decimal(sports_summary, "market_any_quote_coverage")
    early = _decimal(sports_summary, "early_event_coverage")
    middle = _decimal(sports_summary, "middle_event_coverage")
    late = _decimal(sports_summary, "late_event_coverage")
    max_event_obs_share = _decimal(sports_summary, "max_event_observation_share")
    top_decile_obs_share = _decimal(sports_summary, "top_decile_event_observation_share")

    sample_target_met = event_count >= SPORTS_V2_SCALABILITY_MIN_EVENTS
    quote_gates_met = (
        event_quote_coverage >= Decimal(str(MIN_EVENT_ANY_QUOTE_COVERAGE))
        and market_quote_coverage >= Decimal(str(MIN_MARKET_ANY_QUOTE_COVERAGE))
        and early >= Decimal(str(MIN_EVENT_BAND_COVERAGE))
        and middle >= Decimal(str(MIN_EVENT_BAND_COVERAGE))
        and late >= Decimal(str(MIN_EVENT_BAND_COVERAGE))
    )
    series_warning = dominant_series_event_share > SPORTS_V2_SERIES_WARNING_SHARE
    series_block = dominant_series_event_share > SPORTS_V2_SERIES_BLOCK_SHARE
    scalability_gate_pass = sample_target_met and quote_gates_met and not series_block

    if not sample_target_met:
        status = "insufficient_event_sample"
    elif not quote_gates_met:
        status = "quote_scalability_gate_failed"
    elif series_block:
        status = "series_concentration_blocked"
    elif series_warning:
        status = "scalability_gate_pass_with_series_warning"
    else:
        status = "scalability_gate_pass"

    return {
        "schema_version": SPORTS_V2_SCALABILITY_SCHEMA_VERSION,
        "category": "Sports",
        "minimum_event_count": SPORTS_V2_SCALABILITY_MIN_EVENTS,
        "event_count": event_count,
        "market_count": len(rows.markets),
        "valid_quote_observation_count": sum(
            1 for row in rows.observations if row.get("valid_quote_observation") == "true"
        ),
        "unique_series_count": len(series_counts),
        "dominant_series_ticker": dominant_series_ticker,
        "dominant_series_event_count": dominant_series_event_count,
        "dominant_series_event_share": _decimal_text(dominant_series_event_share),
        "event_any_quote_coverage": _decimal_text(event_quote_coverage),
        "market_any_quote_coverage": _decimal_text(market_quote_coverage),
        "early_event_coverage": _decimal_text(early),
        "middle_event_coverage": _decimal_text(middle),
        "late_event_coverage": _decimal_text(late),
        "max_event_observation_share": _decimal_text(max_event_obs_share),
        "top_decile_event_observation_share": _decimal_text(top_decile_obs_share),
        "sample_target_met": sample_target_met,
        "quote_gates_met": quote_gates_met,
        "series_concentration_warning": series_warning,
        "series_concentration_block": series_block,
        "scalability_gate_pass": scalability_gate_pass,
        "status": status,
        "outcomes_materialized": False,
        "synthetic_continuity_allowed": False,
        "anchor_substitution_allowed": False,
        "hierarchical_event_weighting_predeclared": True,
    }


def _reject_outcomes(rows: HistoricalFeasibilityRows) -> None:
    for table_name, table in (
        ("events", rows.events),
        ("markets", rows.markets),
        ("windows", rows.windows),
        ("observations", rows.observations),
        ("category_summary", rows.category_summary),
    ):
        for index, row in enumerate(table, start=1):
            if "result" in row:
                raise SportsV2ScalabilityError(
                    f"forbidden outcome field 'result' in {table_name} row {index}"
                )


def _decimal(row: Mapping[str, str], field: str) -> Decimal:
    value = row.get(field)
    if value is None:
        raise SportsV2ScalabilityError(f"Sports summary missing {field}")
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SportsV2ScalabilityError(f"Sports summary {field} is not decimal") from exc


def _decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000000")), "f")
