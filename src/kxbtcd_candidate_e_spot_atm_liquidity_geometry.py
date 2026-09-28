"""Checkpoint 21N-W outcome-blind spot/ATM-relative liquidity geometry.

This analysis formalizes an already-exposed exploratory diagnostic on the owned
July 10 Predexon replay. It does not score Candidate E, access outcomes, calculate
settlement P&L, make network requests, make purchases, or place orders.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

import pyarrow.parquet as pq

from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    BACKFILL_ROOT_RELATIVE_PATH,
    EXPECTED_PAID_TICKS_SHA256,
    PAID_TICKS_RELATIVE_PATH,
    collect_paid_tickers,
    parse_kxbtcd_threshold_ticker,
    sha256_file,
)
from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    build_verified_ticker_timeline,
)
from src.predexon_full_ladder_replay import load_backfill_snapshots
from src.kxbtcd_candidate_e_continuous_btc_materialization import (
    EVENT_CLOSE_UTC,
    btc_row_for_decision,
    epoch_ms,
    load_materialization,
    materialization_index,
    parse_utc,
    scan_bounds_ms,
)
from src.kxbtcd_candidate_e_continuous_convergence_reentry_v1_simulator import (
    ttc_bucket,
)
from src.kxbtcd_candidate_e_continuous_july10_source_binding import (
    EXPECTED_BINDING_FINGERPRINT,
    EXPECTED_BTC_RELATIVE_PATH,
    EXPECTED_BTC_SHA256,
    validate_binding,
)
from src.kxbtcd_candidate_e_continuous_july10_result_closeout import (
    EXPECTED_RESULT_CLOSEOUT_FINGERPRINT as EXPECTED_21N_V_CLOSEOUT_FINGERPRINT,
    validate_result_closeout,
)

SCHEMA_VERSION = "kxbtcd_candidate_e_spot_atm_liquidity_geometry.v1"
CHECKPOINT_ID = "21N-W"
ANALYSIS_ID = "kxbtcd_candidate_e_spot_atm_liquidity_geometry.v1"
EXPECTED_EVENT_COUNT = 4
EXPECTED_MINUTE_CROSS_SECTIONS_PER_EVENT = 54
EXPECTED_CROSS_SECTION_COUNT = 216
EXPECTED_TICKER_COUNT = 623
DEFAULT_OUTPUT_RELATIVE_PATH = Path(
    "data/analysis/predexon_credit_efficiency/"
    "july10_candidate_e_spot_atm_liquidity_geometry.json"
)

PAID_COLUMNS = (
    "ticker",
    "timestamp",
    "price_dollars",
    "delta_fp",
    "side",
    "sequence",
)


class SpotAtmLiquidityGeometryError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise SpotAtmLiquidityGeometryError(message)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, Counter):
        return {str(k): int(v) for k, v in sorted(value.items())}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def _classify(state) -> str:
    if not state.yes_bids and not state.yes_asks:
        return "MISSING_BOTH"
    if not state.yes_bids:
        return "MISSING_YES_BID"
    if not state.yes_asks:
        return "MISSING_YES_ASK"
    if state.yes_bids[0].price >= state.yes_asks[0].price:
        return "CROSSED_OR_LOCKED"
    return "VALID_TWO_SIDED"


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def materialize(repo_root: str | Path = ".") -> tuple[dict[str, Any], Path, str]:
    repo = Path(repo_root)

    binding = validate_binding(repo)
    if binding.get("source_binding_fingerprint") != EXPECTED_BINDING_FINGERPRINT:
        _fail("21N-U-B source binding changed")

    closeout_21n_v = validate_result_closeout(repo)
    if (
        closeout_21n_v.get("result_closeout_fingerprint")
        != EXPECTED_21N_V_CLOSEOUT_FINGERPRINT
    ):
        _fail("21N-V closeout changed")

    btc_path = repo / EXPECTED_BTC_RELATIVE_PATH
    if sha256_file(btc_path) != EXPECTED_BTC_SHA256:
        _fail("continuous Coinbase artifact hash changed")
    btc_rows = load_materialization(btc_path)
    btc_index = materialization_index(btc_rows)

    paid_path = repo / PAID_TICKS_RELATIVE_PATH
    if sha256_file(paid_path) != EXPECTED_PAID_TICKS_SHA256:
        _fail("paid Predexon shard hash changed")

    tickers = collect_paid_tickers(paid_path)
    if len(tickers) != EXPECTED_TICKER_COUNT:
        _fail(f"expected {EXPECTED_TICKER_COUNT} tickers, observed {len(tickers)}")

    markets_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ticker in tickers:
        event, strike = parse_kxbtcd_threshold_ticker(ticker)
        markets_by_event[event].append(
            {"ticker": ticker, "strike": Decimal(str(strike))}
        )

    rank_by_ticker: dict[str, int] = {}
    for event in markets_by_event:
        markets_by_event[event].sort(key=lambda x: (x["strike"], x["ticker"]))
        for rank, row in enumerate(markets_by_event[event]):
            row["rank"] = rank
            rank_by_ticker[row["ticker"]] = rank

    cross_sections: dict[tuple[str, int], dict[str, Any]] = {}
    for event in sorted(EVENT_CLOSE_UTC):
        lo, hi = scan_bounds_ms(event)
        close_ms = epoch_ms(parse_utc(EVENT_CLOSE_UTC[event]))
        times = list(range(lo, hi + 1, 60_000))
        if len(times) != EXPECTED_MINUTE_CROSS_SECTIONS_PER_EVENT:
            _fail(f"{event} expected 54 minute cross-sections, observed {len(times)}")

        for timestamp_ms in times:
            btc = btc_row_for_decision(
                btc_index,
                event_ticker=event,
                decision_timestamp_ms=timestamp_ms,
            )
            if btc is None:
                _fail(f"missing frozen Coinbase row for {event} at {timestamp_ms}")
            spot = Decimal(str(btc.close_price))
            ladder = markets_by_event[event]
            atm = min(
                ladder,
                key=lambda x: (
                    abs(x["strike"] - spot),
                    x["strike"],
                    x["ticker"],
                ),
            )
            cross_sections[(event, timestamp_ms)] = {
                "event_ticker": event,
                "timestamp_ms": timestamp_ms,
                "decision_ttc_ms": close_ms - timestamp_ms,
                "ttc_bucket": ttc_bucket(close_ms - timestamp_ms),
                "btc_spot": spot,
                "btc_minute_start_ms": btc.minute_start_ms,
                "btc_minute_end_ms": btc.minute_end_ms,
                "atm_ticker": atm["ticker"],
                "atm_strike": atm["strike"],
                "atm_rank": atm["rank"],
                "statuses": Counter(),
                "valid_two_sided": [],
            }

    if len(cross_sections) != EXPECTED_CROSS_SECTION_COUNT:
        _fail(
            f"expected {EXPECTED_CROSS_SECTION_COUNT} cross-sections, "
            f"observed {len(cross_sections)}"
        )

    paid_rows: dict[str, list[dict[str, Any]]] = {ticker: [] for ticker in tickers}
    parquet_file = pq.ParquetFile(paid_path)
    for batch in parquet_file.iter_batches(
        batch_size=131072,
        columns=list(PAID_COLUMNS),
    ):
        for row in batch.to_pylist():
            paid_rows[str(row["ticker"])].append(row)

    for ticker in paid_rows:
        paid_rows[ticker].sort(
            key=lambda row: (int(row["timestamp"]), int(row["sequence"]))
        )

    for index, ticker in enumerate(sorted(tickers), 1):
        event, strike = parse_kxbtcd_threshold_ticker(ticker)
        strike = Decimal(str(strike))

        snapshots = load_backfill_snapshots(
            repo / BACKFILL_ROOT_RELATIVE_PATH / f"{ticker}_raw_pages.jsonl",
            ticker=ticker,
        )
        timeline = build_verified_ticker_timeline(
            ticker=ticker,
            snapshots=snapshots,
            paid_rows=paid_rows[ticker],
        )

        rank = rank_by_ticker[ticker]
        lo, hi = scan_bounds_ms(event)

        for timestamp_ms in range(lo, hi + 1, 60_000):
            cross = cross_sections[(event, timestamp_ms)]
            segment = timeline.unique_segment_for_interval(timestamp_ms, timestamp_ms)
            if segment is None:
                cross["statuses"]["SOURCE_UNAVAILABLE"] += 1
                continue

            state = segment.state_at(timestamp_ms)
            status = _classify(state)
            cross["statuses"][status] += 1
            if status != "VALID_TWO_SIDED":
                continue

            bid = state.yes_bids[0]
            ask = state.yes_asks[0]
            strike_minus_spot = strike - cross["btc_spot"]
            distance_bps = Decimal(
                str(10000.0 * math.log(float(cross["btc_spot"] / strike)))
            )

            cross["valid_two_sided"].append(
                {
                    "market_ticker": ticker,
                    "strike": strike,
                    "rank": rank,
                    "rank_from_atm": rank - cross["atm_rank"],
                    "abs_rank_from_atm": abs(rank - cross["atm_rank"]),
                    "strike_minus_spot": strike_minus_spot,
                    "abs_strike_minus_spot": abs(strike_minus_spot),
                    "btc_distance_bps": distance_bps,
                    "best_yes_bid": bid.price,
                    "best_yes_ask": ask.price,
                    "best_yes_bid_quantity": bid.quantity,
                    "best_yes_ask_quantity": ask.quantity,
                }
            )

        if index % 50 == 0:
            print(f"processed {index}/{EXPECTED_TICKER_COUNT}")

    event_summary: dict[str, Counter] = defaultdict(Counter)
    bucket_summary: dict[str, Counter] = defaultdict(Counter)
    active_instance_rank_distances: list[int] = []
    active_instance_abs_dollars: list[Decimal] = []
    active_instance_abs_bps: list[Decimal] = []
    details: list[dict[str, Any]] = []

    for key in sorted(cross_sections):
        cross = cross_sections[key]
        event = cross["event_ticker"]
        bucket = cross["ttc_bucket"]
        valid = cross["valid_two_sided"]

        event_summary[event]["cross_sections"] += 1
        bucket_summary[bucket]["cross_sections"] += 1

        detail: dict[str, Any] = {
            "event_ticker": event,
            "timestamp_ms": cross["timestamp_ms"],
            "decision_ttc_ms": cross["decision_ttc_ms"],
            "ttc_bucket": bucket,
            "btc_spot": cross["btc_spot"],
            "atm_ticker": cross["atm_ticker"],
            "atm_strike": cross["atm_strike"],
            "atm_rank": cross["atm_rank"],
            "status_counts": cross["statuses"],
            "valid_two_sided_count": len(valid),
            "atm_two_sided": False,
            "nearest_abs_rank_from_atm": None,
            "nearest_abs_strike_minus_spot": None,
            "band_low_rank_from_atm": None,
            "band_high_rank_from_atm": None,
            "band_center_rank_from_atm": None,
        }

        if not valid:
            details.append(detail)
            continue

        event_summary[event]["any_two_sided"] += 1
        bucket_summary[bucket]["any_two_sided"] += 1

        atm_two_sided = any(
            row["market_ticker"] == cross["atm_ticker"] for row in valid
        )
        if atm_two_sided:
            event_summary[event]["atm_two_sided"] += 1
            bucket_summary[bucket]["atm_two_sided"] += 1
            detail["atm_two_sided"] = True

        valid_sorted = sorted(
            valid,
            key=lambda row: (
                row["abs_rank_from_atm"],
                row["abs_strike_minus_spot"],
                row["market_ticker"],
            ),
        )
        nearest = valid_sorted[0]
        nearest_rank = nearest["abs_rank_from_atm"]
        detail["nearest_abs_rank_from_atm"] = nearest_rank
        detail["nearest_abs_strike_minus_spot"] = nearest["abs_strike_minus_spot"]

        signed_ranks = sorted(row["rank_from_atm"] for row in valid)
        detail["band_low_rank_from_atm"] = min(signed_ranks)
        detail["band_high_rank_from_atm"] = max(signed_ranks)
        detail["band_center_rank_from_atm"] = Decimal(str(median(signed_ranks)))

        for cutoff in (0, 1, 2, 3, 5, 10):
            if nearest_rank <= cutoff:
                event_summary[event][f"nearest_le_{cutoff}"] += 1
                bucket_summary[bucket][f"nearest_le_{cutoff}"] += 1

        for row in valid:
            active_instance_rank_distances.append(row["abs_rank_from_atm"])
            active_instance_abs_dollars.append(row["abs_strike_minus_spot"])
            active_instance_abs_bps.append(abs(row["btc_distance_bps"]))

        details.append(detail)

    active_details = [row for row in details if row["valid_two_sided_count"] > 0]
    nearest_distances = [
        int(row["nearest_abs_rank_from_atm"]) for row in active_details
    ]

    overall = {
        "total_cross_sections": len(details),
        "cross_sections_with_any_valid_two_sided": len(active_details),
        "atm_ticker_two_sided_cross_sections": sum(
            bool(row["atm_two_sided"]) for row in active_details
        ),
        "median_nearest_abs_rank_from_atm": (
            Decimal(str(median(nearest_distances))) if nearest_distances else None
        ),
        "max_nearest_abs_rank_from_atm": (
            max(nearest_distances) if nearest_distances else None
        ),
        "nearest_two_sided_within_rank_counts": {
            str(cutoff): sum(distance <= cutoff for distance in nearest_distances)
            for cutoff in (0, 1, 2, 3, 5, 10)
        },
        "active_ticker_minute_instance_count": len(active_instance_rank_distances),
        "median_active_instance_abs_rank_from_atm": (
            Decimal(str(median(active_instance_rank_distances)))
            if active_instance_rank_distances
            else None
        ),
        "median_active_instance_abs_strike_minus_spot": (
            Decimal(str(median(active_instance_abs_dollars)))
            if active_instance_abs_dollars
            else None
        ),
        "median_active_instance_abs_btc_distance_bps": (
            Decimal(str(median(active_instance_abs_bps)))
            if active_instance_abs_bps
            else None
        ),
        "active_instance_within_rank_counts": {
            str(cutoff): sum(
                distance <= cutoff for distance in active_instance_rank_distances
            )
            for cutoff in (1, 2, 3, 5, 10)
        },
    }

    payload = {
        "schema_version": SCHEMA_VERSION,
        "checkpoint_id": CHECKPOINT_ID,
        "analysis_id": ANALYSIS_ID,
        "evidence_role": "four_event_july10_exploratory_market_universe_geometry_only",
        "parent_21n_v_result_closeout_fingerprint": EXPECTED_21N_V_CLOSEOUT_FINGERPRINT,
        "source_binding_fingerprint": EXPECTED_BINDING_FINGERPRINT,
        "continuous_btc_sha256": EXPECTED_BTC_SHA256,
        "paid_predexon_tick_shard_sha256": EXPECTED_PAID_TICKS_SHA256,
        "design": {
            "event_count": EXPECTED_EVENT_COUNT,
            "minute_cross_sections_per_event": EXPECTED_MINUTE_CROSS_SECTIONS_PER_EVENT,
            "total_cross_sections": EXPECTED_CROSS_SECTION_COUNT,
            "cross_section_schedule": "exact_T_minus_55_through_T_minus_2_inclusive_one_minute_grid",
            "btc_state": "immediately_preceding_fully_completed_coinbase_1m_bucket",
            "atm_definition": (
                "minimum_absolute_strike_minus_causal_btc_spot;"
                "ties_lower_strike_then_ticker"
            ),
            "market_universe": "full_owned_623_ticker_july10_kxbtcd_ladder",
            "two_sided_definition": "verified_yes_bid_and_yes_ask_with_bid_strictly_less_than_ask",
            "candidate_e_scored": False,
        },
        "event_summary": {
            event: dict(summary) for event, summary in sorted(event_summary.items())
        },
        "ttc_bucket_summary": {
            bucket: dict(summary)
            for bucket, summary in sorted(bucket_summary.items())
        },
        "overall": overall,
        "cross_sections": details,
        "interpretation_boundary": {
            "supports_exploratory_spot_atm_relative_liquidity_structure": True,
            "does_not_select_v2_rank_envelope": True,
            "does_not_validate_nonstructural_candidate_e_use": True,
            "does_not_establish_profitability": True,
            "independent_event_count": 4,
        },
        "safety": {
            "candidate_e_scored": False,
            "nonstructural_probability_inference": False,
            "outcomes_accessed": False,
            "settlement_pnl_calculated": False,
            "network_requests": 0,
            "predexon_paid_purchases": 0,
            "orders_placed": 0,
            "paper_broker": False,
            "demo_execution": False,
            "real_money_execution": False,
            "protected_reserve_accessed": False,
        },
    }

    payload = _jsonable(payload)
    raw = _canonical_bytes(payload)
    output_path = repo / DEFAULT_OUTPUT_RELATIVE_PATH
    if output_path.exists() and output_path.read_bytes() != raw:
        _fail(f"refusing non-identical overwrite: {output_path}")
    if not output_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    return payload, output_path, digest


def validate_observed_summary(payload: dict[str, Any]) -> None:
    overall = payload["overall"]
    expected = {
        "total_cross_sections": 216,
        "cross_sections_with_any_valid_two_sided": 177,
        "atm_ticker_two_sided_cross_sections": 62,
        "median_nearest_abs_rank_from_atm": "1",
        "max_nearest_abs_rank_from_atm": 4,
        "active_ticker_minute_instance_count": 755,
        "median_active_instance_abs_rank_from_atm": "3",
        "median_active_instance_abs_strike_minus_spot": "286.25",
    }
    for key, value in expected.items():
        if overall.get(key) != value:
            _fail(f"observed summary mismatch for {key}: {overall.get(key)!r}")

    if overall["nearest_two_sided_within_rank_counts"] != {
        "0": 62,
        "1": 132,
        "2": 161,
        "3": 174,
        "5": 177,
        "10": 177,
    }:
        _fail("nearest-rank count summary mismatch")

    if overall["active_instance_within_rank_counts"] != {
        "1": 199,
        "2": 358,
        "3": 516,
        "5": 735,
        "10": 755,
    }:
        _fail("active-instance rank count summary mismatch")

    expected_any = {
        "KXBTCD-26JUL1013": 40,
        "KXBTCD-26JUL1014": 46,
        "KXBTCD-26JUL1015": 50,
        "KXBTCD-26JUL1016": 41,
    }
    for event, count in expected_any.items():
        if payload["event_summary"][event].get("any_two_sided") != count:
            _fail(f"{event} any-two-sided count mismatch")
