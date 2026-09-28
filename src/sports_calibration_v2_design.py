"""Outcome-blind design helpers for the redesigned Sports calibration experiment.

This module contains no outcome parsing and no calibration scoring.  It freezes
how dense historical quote observations will be weighted *before* any final
YES/NO outcome is materialized.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, getcontext
from typing import Iterable, Mapping

getcontext().prec = 40

VALID_TIME_BANDS = frozenset(
    {"early_5d_to_7d", "middle_3d_to_5d", "late_1d_to_3d"}
)


class SportsCalibrationV2DesignError(ValueError):
    """Raised when outcome-blind observations violate the frozen design contract."""


def hierarchical_observation_weights(
    observations: Iterable[Mapping[str, str]],
    *,
    time_band: str | None = None,
) -> list[dict[str, str]]:
    """Return equal-event/equal-market/equal-observation analytical weights.

    For one analysis subset, let E be contributing events, M_e the contributing
    markets in event e, and N_em the valid observations in market m of event e.
    Each observation receives

        1 / (E * M_e * N_em)

    so every event has equal total influence, every contributing market within
    an event has equal influence, and dense minute-by-minute quoting cannot
    dominate the analysis merely by producing more rows.

    If ``time_band`` is supplied, weights are recomputed inside that band.  This
    is required because event/market coverage differs across time-to-close.
    """

    if time_band is not None and time_band not in VALID_TIME_BANDS:
        raise SportsCalibrationV2DesignError(f"unsupported time band {time_band!r}")

    selected: list[Mapping[str, str]] = []
    for index, row in enumerate(observations, start=1):
        if "result" in row:
            raise SportsCalibrationV2DesignError(
                f"observation {index} contains forbidden outcome field 'result'"
            )
        if row.get("category") != "Sports":
            continue
        if row.get("valid_quote_observation") != "true":
            continue
        if time_band is not None and row.get("time_band") != time_band:
            continue
        event = _required(row.get("event_ticker"), f"observation {index}.event_ticker")
        market = _required(row.get("ticker"), f"observation {index}.ticker")
        _required(row.get("time_to_close_seconds"), f"observation {index}.time_to_close_seconds")
        _required(row.get("q_mid"), f"observation {index}.q_mid")
        # Read identity now so malformed rows fail before grouping.
        _ = event, market
        selected.append(row)

    by_event_market: dict[str, dict[str, list[Mapping[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in selected:
        by_event_market[row["event_ticker"]][row["ticker"]].append(row)

    event_count = len(by_event_market)
    if event_count == 0:
        return []

    output: list[dict[str, str]] = []
    E = Decimal(event_count)
    for event_ticker in sorted(by_event_market):
        markets = by_event_market[event_ticker]
        M = Decimal(len(markets))
        for ticker in sorted(markets):
            rows = markets[ticker]
            N = Decimal(len(rows))
            weight = Decimal(1) / (E * M * N)
            for row in rows:
                output.append(
                    {
                        "event_ticker": event_ticker,
                        "ticker": ticker,
                        "end_period_ts": _required(
                            row.get("end_period_ts"), "observation.end_period_ts"
                        ),
                        "time_to_close_seconds": row["time_to_close_seconds"],
                        "time_band": row.get("time_band", ""),
                        "q_mid": row["q_mid"],
                        "analysis_weight": _decimal_text(weight),
                    }
                )

    return output


def event_weight_totals(weight_rows: Iterable[Mapping[str, str]]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in weight_rows:
        event = _required(row.get("event_ticker"), "weight.event_ticker")
        try:
            weight = Decimal(_required(row.get("analysis_weight"), "weight.analysis_weight"))
        except Exception as exc:  # Decimal raises several numeric subclasses.
            raise SportsCalibrationV2DesignError("analysis_weight is not decimal text") from exc
        if weight <= 0:
            raise SportsCalibrationV2DesignError("analysis_weight must be positive")
        totals[event] += weight
    return dict(totals)


def _required(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SportsCalibrationV2DesignError(f"{field} must be non-empty text")
    return value


def _decimal_text(value: Decimal) -> str:
    # Fixed precision is deterministic and more than sufficient for analytical
    # sample weights while avoiding scientific-notation differences across tools.
    return format(value.quantize(Decimal("0.000000000000000001")), "f")
