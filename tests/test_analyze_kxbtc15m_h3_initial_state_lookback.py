from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_h3_initial_state_lookback import (
    FIRST_EARLIER,
    band_episodes,
    correlation_table,
    entry_context,
    final_episode_start_index,
    first_earlier_context,
    milestone_context,
    path_row,
    relative_state,
    spearman,
    summarize_counterfactuals,
)
from audit_kxbtc15m_raw_depth import ParsedBook


UTC = timezone.utc
OPEN = datetime(2026, 8, 13, 19, 0, tzinfo=UTC)
CLOSE = OPEN + timedelta(seconds=900)
BOUNDARY = CLOSE - timedelta(seconds=300)
TICKER = "KXBTC15M-26AUG131515-15"


def book(yes_bid: str, yes_ask: str) -> ParsedBook:
    return ParsedBook(
        yes_levels=((Decimal(yes_bid), Decimal("1000")),),
        no_levels=((Decimal("1") - Decimal(yes_ask), Decimal("1000")),),
    )


def snapshot(elapsed: float, yes_bid: str, yes_ask: str) -> Snapshot:
    return Snapshot(
        observed_at=OPEN + timedelta(seconds=elapsed),
        request_id=str(elapsed),
        book=book(yes_bid, yes_ask),
    )


def path():
    return [
        snapshot(450.0, "0.70", "0.72"),
        snapshot(480.0, "0.90", "0.92"),
        snapshot(490.0, "0.90", "0.92"),
        snapshot(500.0, "0.98", "0.99"),
        snapshot(530.0, "0.10", "0.12"),
        snapshot(550.0, "0.91", "0.93"),
        snapshot(560.0, "0.91", "0.93"),
        snapshot(570.0, "0.91", "0.93"),
        snapshot(580.0, "0.91", "0.93"),
        snapshot(590.0, "0.91", "0.93"),
        snapshot(599.0, "0.91", "0.93"),
        snapshot(600.2, "0.91", "0.93"),
        snapshot(601.3, "0.98", "0.99"),
    ]


def baseline_row():
    return {
        "side": "YES",
        "decision_time": path()[11].observed_at.isoformat(),
        "seconds_remaining": "299.8",
        "entry_execution_time": path()[12].observed_at.isoformat(),
        "pnl": "4.00",
        "favored_side_won": True,
    }


def test_relative_state_distinguishes_band_excursions_and_side_change():
    snapshots = path()
    assert relative_state(snapshots[0], "YES") == "same_side_below_band"
    assert relative_state(snapshots[1], "YES") == "same_side_in_band"
    assert relative_state(snapshots[3], "YES") == "same_side_above_band"
    assert relative_state(snapshots[4], "YES") == "other_favored_side"


def test_episode_and_final_episode_detection_preserves_native_order():
    snapshots = path()
    episodes = band_episodes(
        snapshots,
        baseline_side="YES",
        start_time=OPEN + timedelta(seconds=450),
        stop_index=11,
    )
    assert len(episodes) == 2
    assert episodes[0]["observations"] == 2
    assert episodes[0]["reaches_baseline_decision"] is False
    assert episodes[1]["observations"] == 7
    assert episodes[1]["reaches_baseline_decision"] is True
    assert final_episode_start_index(snapshots, 11, "YES") == 5


def test_first_earlier_context_uses_first_same_side_band_and_one_second_fill():
    snapshots = path()
    context = first_earlier_context(
        snapshots,
        close_time=CLOSE,
        required_side="YES",
    )
    assert context is not None
    assert context[0] == 1
    assert context[1] == 2
    assert context[2] == "YES"


def test_milestone_context_requires_fill_before_five_minute_boundary():
    snapshots = path()
    valid = milestone_context(
        snapshots,
        episode_start_index=5,
        episode_end_index=11,
        required_side="YES",
        elapsed_seconds=30,
        execution_deadline=BOUNDARY,
    )
    assert valid is not None
    assert valid[0] == 8
    assert valid[1] == 9
    too_late = milestone_context(
        snapshots,
        episode_start_index=5,
        episode_end_index=11,
        required_side="YES",
        elapsed_seconds=45,
        execution_deadline=BOUNDARY,
    )
    assert too_late is None


def test_entry_context_rejects_execution_at_boundary():
    snapshots = [
        snapshot(598.5, "0.91", "0.93"),
        snapshot(600.0, "0.91", "0.93"),
    ]
    assert entry_context(
        snapshots,
        decision_index=0,
        required_side="YES",
        execution_deadline=BOUNDARY,
    ) is None


def test_path_row_reports_episode_age_and_transition_features():
    snapshots = path()
    row, episodes, final_start = path_row(
        ticker=TICKER,
        segment="earlier_64",
        snapshots=snapshots,
        close_time=CLOSE,
        baseline=baseline_row(),
        decision_index=11,
    )
    assert final_start == 5
    assert len(episodes) == 2
    assert row["lookback_band_episode_count"] == 2
    assert row["lookback_band_exit_count"] == 1
    assert row["lookback_side_change_count"] == 2
    assert row["final_episode_age_at_baseline_seconds"] == 50.2
    assert row["final_episode_started_before_5m"] is True


def test_spearman_handles_ties_and_correlation_table_segments():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    rows = []
    for index in range(8):
        row = {
            "diagnostic_segment": "earlier_64" if index < 4 else "later_32",
            "first_earlier_pnl": float(index),
            "first_earlier_increment_vs_baseline": float(index) - 1,
        }
        for feature in (
            "final_episode_age_at_baseline_seconds",
            "lookback_in_band_observation_fraction",
            "lookback_same_side_observation_fraction",
            "lookback_band_episode_count",
            "lookback_side_change_count",
            "first_same_side_band_seconds_remaining",
        ):
            row[feature] = float(index)
        rows.append(row)
    table = correlation_table(rows)
    selected = next(
        row for row in table
        if row["segment"] == "all_35"
        and row["feature"] == "final_episode_age_at_baseline_seconds"
        and row["outcome"] == "first_earlier_pnl"
    )
    assert selected["markets"] == 8
    assert selected["spearman_rho"] == 1.0


def test_counterfactual_summary_counts_no_entry_as_zero_per_selected_market():
    rows = []
    for ticker, pnl in ((TICKER, "3"), ("KXBTC15M-26AUG131530-30", "5")):
        baseline = {
            "ticker": ticker,
            "diagnostic_segment": "earlier_64",
            "policy": "baseline_4_5m_initial_state",
            "status": "completed",
            "entry_filled": True,
            "pnl": pnl,
            "profitable": True,
            "target_filled": True,
            "full_capital_loss": False,
        }
        rows.append(baseline)
        earlier = dict(baseline)
        earlier.update({
            "policy": FIRST_EARLIER,
            "status": "completed" if ticker == TICKER else "no_trigger",
            "entry_filled": ticker == TICKER,
            "pnl": "2" if ticker == TICKER else "",
        })
        rows.append(earlier)
        for policy in (
            "final_episode_start_lookahead",
            "final_episode_after_5s_lookahead",
            "final_episode_after_15s_lookahead",
            "final_episode_after_30s_lookahead",
            "final_episode_after_60s_lookahead",
        ):
            row = dict(earlier)
            row["policy"] = policy
            rows.append(row)
    summary = summarize_counterfactuals(rows)
    selected = next(
        row for row in summary
        if row["segment"] == "all_35" and row["policy"] == FIRST_EARLIER
    )
    assert selected["earlier_entries"] == 1
    assert selected["mean_pnl_per_future_defined_market"] == 1
    assert selected["mean_increment_vs_baseline"] == -3
