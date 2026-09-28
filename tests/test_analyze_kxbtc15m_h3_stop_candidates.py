from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_h3_stop_candidates import (
    POLICIES,
    SignalState,
    _policy,
    candidate_signal,
    markdown_report,
    summarize_candidates,
)


NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


def signal(
    key: str,
    state: SignalState,
    *,
    seconds: float = 200,
    pnl: str | None = "-1",
    full: bool = True,
    coverage: str | None = None,
    elapsed: float = 0,
):
    return candidate_signal(
        policy=_policy(key),
        state=state,
        observed_at=NOW + timedelta(seconds=elapsed),
        seconds_remaining=seconds,
        full_depth=full,
        executable_pnl=None if pnl is None else Decimal(pnl),
        stress_coverage=None if coverage is None else Decimal(coverage),
    )


def test_policy_surface_is_bounded_and_has_no_hybrid() -> None:
    assert len(POLICIES) == 16
    assert POLICIES[0].key == "baseline_no_stop"
    assert all(policy.family != "hybrid" for policy in POLICIES)
    assert {policy.family for policy in POLICIES} == {
        "baseline", "fixed", "time", "persistent", "hysteresis",
        "late_loss", "lost_depth", "depth_buffer",
    }


def test_fixed_stop_requires_full_executable_breach() -> None:
    state = SignalState()
    assert signal("fixed_15", state, pnl="-14.99") == (False, "")
    assert signal("fixed_15", state, pnl="-15") == (
        True, "fixed_loss_threshold"
    )
    assert signal("fixed_15", state, pnl=None, full=False) == (False, "")


def test_time_exit_uses_seconds_remaining_without_outcome_information() -> None:
    state = SignalState()
    assert signal("fallback_60s", state, seconds=60.1, pnl=None, full=False) == (
        False, ""
    )
    assert signal("fallback_60s", state, seconds=59.9, pnl=None, full=False) == (
        True, "no_target_time_exit"
    )


def test_persistent_stop_resets_after_executable_recovery() -> None:
    state = SignalState()
    assert signal("persistent_15_5s", state, pnl="-16", elapsed=0) == (False, "")
    assert signal("persistent_15_5s", state, pnl="-17", elapsed=4.9) == (False, "")
    assert signal("persistent_15_5s", state, pnl="-14", elapsed=5.0) == (False, "")
    assert state.breach_started_at is None
    assert signal("persistent_15_5s", state, pnl="-16", elapsed=6.0) == (False, "")
    assert signal("persistent_15_5s", state, pnl="-16", elapsed=11.0) == (
        True, "persistent_loss_threshold"
    )


def test_persistent_stop_treats_depth_loss_as_unresolved_risk() -> None:
    state = SignalState()
    assert signal("persistent_20_5s", state, pnl="-21", elapsed=0) == (False, "")
    assert signal(
        "persistent_20_5s", state, pnl=None, full=False, elapsed=5.1
    ) == (True, "persistent_breach_with_depth_loss")


def test_hysteresis_requires_a_later_deteriorating_observation() -> None:
    state = SignalState()
    assert signal("hysteresis_10_20_5", state, pnl="-21", elapsed=0) == (
        False, ""
    )
    assert signal("hysteresis_10_20_5", state, pnl="-19", elapsed=1) == (
        False, ""
    )
    assert signal("hysteresis_10_20_5", state, pnl="-20", elapsed=2) == (
        True, "confirmed_deterioration"
    )
    state = SignalState()
    assert signal("hysteresis_10_20_5", state, pnl="-11", elapsed=0) == (
        False, ""
    )
    assert signal("hysteresis_10_20_5", state, pnl="-4", elapsed=1) == (
        False, ""
    )
    assert state.hysteresis_armed_at is None


def test_late_loss_ladder_tightens_near_close() -> None:
    state = SignalState()
    assert signal("late_loss_ladder", state, seconds=89, pnl="-9") == (False, "")
    assert signal("late_loss_ladder", state, seconds=89, pnl="-10") == (
        True, "late_deep_loss_90s"
    )
    assert signal("late_loss_ladder", state, seconds=59, pnl="-0.01") == (
        True, "late_nonrecovery_60s"
    )
    assert signal(
        "late_loss_ladder", state, seconds=59, pnl=None, full=False
    ) == (True, "late_nonrecovery_60s")


def test_depth_buffer_requires_loss_and_thin_stressed_depth() -> None:
    state = SignalState()
    assert signal(
        "depth_buffer_125", state, pnl="-11", coverage="1.30"
    ) == (False, "")
    assert signal(
        "depth_buffer_125", state, pnl="-9", coverage="1.10"
    ) == (False, "")
    assert signal(
        "depth_buffer_125", state, pnl="-10", coverage="1.24"
    ) == (True, "thin_depth_after_loss")
    assert signal(
        "depth_buffer_125", state, pnl=None, full=False, coverage="0.50"
    ) == (True, "lost_full_position_depth")


def test_summary_separates_loser_savings_from_winner_cost() -> None:
    rows = []
    for policy in POLICIES:
        for ticker, partition, segment, baseline_pnl in (
            ("WIN", "development_96", "earlier_64", 4.0),
            ("LOSS", "opened_26", "opened_26", -100.0),
        ):
            pnl = baseline_pnl
            stopped = False
            if policy.key == "fixed_20":
                pnl = -10.0 if ticker == "WIN" else -20.0
                stopped = True
            rows.append({
                "ticker": ticker,
                "evidence_partition": partition,
                "diagnostic_segment": segment,
                "candidate_policy": policy.key,
                "candidate_display_policy": policy.label,
                "status": "completed",
                "pnl": str(pnl),
                "candidate_stop_signal": stopped,
                "candidate_signal_reason": "fixed_loss_threshold" if stopped else "",
                "candidate_signal_seconds_remaining": "100" if stopped else "",
                "candidate_signal_executable_pnl": "-20" if stopped else "",
                "candidate_fully_liquidated": stopped,
                "candidate_settlement_residual": False,
                "full_capital_loss": False,
                "profitable": pnl > 0,
            })

    summary = next(
        row for row in summarize_candidates(rows)
        if row["group"] == "combined_122" and row["candidate_policy"] == "fixed_20"
    )
    assert summary["loser_savings_vs_baseline"] == 80.0
    assert summary["winner_gross_opportunity_cost"] == 14.0
    assert summary["total_paired_difference_vs_baseline"] == 66.0
    assert summary["strong_standalone_screen"] is True

    report = markdown_report(rows, summarize_candidates(rows))
    assert "| n/a |" in report
    assert "Strong standalone candidates:" in report
