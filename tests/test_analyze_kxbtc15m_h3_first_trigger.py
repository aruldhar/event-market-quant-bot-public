from analyze_kxbtc15m_h3_first_trigger import (
    first_triggers,
    qualifies,
    summarize,
)


def row(ticker, time, probability, segment="earlier_64", pnl="1.0"):
    return {
        "ticker": ticker,
        "market_index": "1",
        "diagnostic_segment": segment,
        "decision_time": time,
        "seconds_remaining": "270",
        "decision_favored_midpoint": str(probability),
        "exit_policy": "target_or_preclose_10s",
        "status": "completed",
        "pnl": pnl,
        "profitable": "True",
        "favored_side_won": "True",
        "target_achieved_after_latency": "True",
        "exit_reason": "profit_target",
        "total_fees": "1.0",
        "holdout_read": "False",
        "external_btc_data_used": "False",
    }


def test_primary_candidate_boundaries_are_frozen():
    assert qualifies(row("A", "1", .90), .90, .98)
    assert qualifies(row("A", "1", .9799), .90, .98)
    assert not qualifies(row("A", "1", .98), .90, .98)


def test_time_window_excludes_240_second_boundary():
    value = row("A", "1", .90)
    value["seconds_remaining"] = "240"
    assert not qualifies(value, .90, .98)


def test_unavailable_favored_side_blank_midpoint_is_skipped():
    value = row("A", "1", .90)
    value["decision_favored_midpoint"] = ""
    value["status"] = "favored_side_unavailable"
    assert not qualifies(value, .90, .98)


def test_first_trigger_selects_one_chronological_row_per_market():
    rows = [
        row("A", "2026-08-12T00:00:10+00:00", .91),
        row("A", "2026-08-12T00:00:05+00:00", .92),
        row("B", "2026-08-12T00:00:06+00:00", .96),
    ]
    selected = first_triggers(
        rows, candidate="primary_90_98c", low=.90, high=.98
    )
    assert len(selected) == 2
    assert selected[0]["decision_time"] == "2026-08-12T00:00:05+00:00"


def test_component_candidates_do_not_duplicate_inside_candidate():
    rows = [row("A", "1", .92), row("A", "2", .96)]
    low = first_triggers(rows, candidate="diagnostic_90_95c", low=.90, high=.95)
    high = first_triggers(rows, candidate="diagnostic_95_98c", low=.95, high=.98)
    assert len(low) == 1
    assert len(high) == 1


def test_summary_separates_earlier_and_later_markets():
    triggers = []
    for candidate in ("primary_90_98c", "diagnostic_90_95c", "diagnostic_95_98c"):
        first = row("A", "1", .92)
        first["candidate"] = candidate
        second = row("B", "2", .96, segment="later_32", pnl="2.0")
        second["candidate"] = candidate
        triggers.extend([first, second])
    result = summarize(triggers)
    assert len(result) == 9
    primary_all = next(
        item for item in result
        if item["candidate"] == "primary_90_98c" and item["segment"] == "all_96"
    )
    assert primary_all["triggered_markets"] == 2
    assert primary_all["mean_pnl_per_triggered_market"] == 1.5
