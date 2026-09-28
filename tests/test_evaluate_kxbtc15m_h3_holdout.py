from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import evaluate_kxbtc15m_h3_holdout as holdout
from audit_kxbtc15m_raw_depth import DevelopmentMarket


def _manifest(ticker: str, minute: int) -> dict:
    return {
        "status": "completed",
        "started_at_utc": f"2026-08-12T18:{minute:02d}:00+00:00",
        "arguments": {"ticker": ticker},
    }


def test_select_holdout_manifests_requires_exact_boundaries(tmp_path: Path) -> None:
    tickers = [holdout.HOLDOUT_FIRST_TICKER]
    tickers.extend(f"KXBTC15M-SYNTH-{index:02d}" for index in range(1, 25))
    tickers.append(holdout.HOLDOUT_LAST_TICKER)
    for index, ticker in enumerate(tickers):
        path = tmp_path / f"record_orderbook_{index:02d}.json"
        path.write_text(json.dumps(_manifest(ticker, index)), encoding="utf-8")

    selected = holdout.select_holdout_manifests(tmp_path)

    assert len(selected) == 26
    assert selected[0]["arguments"]["ticker"] == holdout.HOLDOUT_FIRST_TICKER
    assert selected[-1]["arguments"]["ticker"] == holdout.HOLDOUT_LAST_TICKER


def test_select_holdout_manifests_fails_on_short_sample(tmp_path: Path) -> None:
    for index, ticker in enumerate(
        (holdout.HOLDOUT_FIRST_TICKER, holdout.HOLDOUT_LAST_TICKER)
    ):
        (tmp_path / f"record_orderbook_{index}.json").write_text(
            json.dumps(_manifest(ticker, index)), encoding="utf-8"
        )
    with pytest.raises(holdout.H3HoldoutError, match="expected 26"):
        holdout.select_holdout_manifests(tmp_path)


def _scenario(index: int, *, completed: bool, pnl: float = 1.0) -> dict:
    if not completed:
        return {
            "ticker": f"T{index}",
            "status": "no_trigger",
            "triggered": False,
            "pnl": "",
        }
    return {
        "ticker": f"T{index}",
        "status": "completed",
        "triggered": True,
        "pnl": str(pnl),
        "profitable": pnl > 0,
        "target_filled": True,
        "fallback_used": False,
        "exit_reason": "protected_profit_target",
        "favored_side_won": True,
        "full_capital_loss": pnl <= -90,
    }


def test_summary_passes_only_when_every_preregistered_gate_passes() -> None:
    rows = [_scenario(index, completed=True, pnl=1.0) for index in range(26)]

    result = holdout.summarize_holdout(rows)

    assert result["entry_filled_markets"] == 26
    assert result["mean_pnl_per_eligible_market"] == 1.0
    assert result["bootstrap_ci_low_per_eligible_market"] == 1.0
    assert result["full_capital_losses"] == 0
    assert result["holdout_support_gate_pass"] is True
    assert result["holdout_decision"] == "supported"


def test_summary_counts_no_trade_as_zero_and_can_be_inconclusive() -> None:
    rows = [_scenario(0, completed=True, pnl=1.0)]
    rows.extend(_scenario(index, completed=False) for index in range(1, 26))

    result = holdout.summarize_holdout(rows)

    assert result["mean_pnl_per_eligible_market"] == pytest.approx(1 / 26)
    assert result["minimum_filled_markets_pass"] is False
    assert result["positive_ci_lower_pass"] is False
    assert result["holdout_support_gate_pass"] is False
    assert result["holdout_decision"] == "inconclusive"


def test_summary_with_no_fills_is_serializable_and_not_supported() -> None:
    rows = [_scenario(index, completed=False) for index in range(26)]

    result = holdout.summarize_holdout(rows)

    assert result["mean_pnl_per_eligible_market"] == 0
    assert result["mean_pnl_per_filled_entry"] is None
    assert result["worst_pnl_per_filled_entry"] is None
    assert result["holdout_decision"] == "not_supported"
    json.dumps(result, allow_nan=False)


class _FakeClient:
    def __init__(self, *, status: str = "finalized", result: str = "yes") -> None:
        self.status = status
        self.result = result
        self.calls: list[str] = []

    def get_json(self, path: str):
        self.calls.append(path)
        ticker = path.rsplit("/", 1)[-1]
        return SimpleNamespace(
            payload={
                "market": {
                    "ticker": ticker,
                    "status": self.status,
                    "result": self.result,
                }
            },
            raw_record=SimpleNamespace(
                source="kalshi_public_rest",
                session_id="session",
                request_id=f"request-{ticker}",
            ),
            received_at_utc="2026-08-13T00:00:00.000000Z",
        )


def _markets() -> list[DevelopmentMarket]:
    output = []
    for index in range(26):
        ticker = (
            holdout.HOLDOUT_FIRST_TICKER
            if index == 0
            else holdout.HOLDOUT_LAST_TICKER
            if index == 25
            else f"KXBTC15M-SYNTH-{index:02d}"
        )
        output.append(
            DevelopmentMarket(
                index=101 + index,
                ticker=ticker,
                manifest={},
                csv_path=Path("unused.csv"),
                rows=[],
                eligible=True,
                exclusion_reasons=(),
            )
        )
    return output


def test_collect_outcomes_requests_only_exact_holdout_tickers() -> None:
    client = _FakeClient()

    rows = holdout.collect_outcomes(
        client, _markets(), run_id="run", freeze_sha256="abc"
    )

    assert len(rows) == 26
    assert client.calls == [f"/markets/{market.ticker}" for market in _markets()]
    assert {row["winning_side"] for row in rows} == {"YES"}
    assert all(row["status"] == "finalized" for row in rows)


def test_collect_outcomes_fails_closed_on_unfinalized_market() -> None:
    with pytest.raises(holdout.H3HoldoutError, match="expected finalized yes/no"):
        holdout.collect_outcomes(
            _FakeClient(status="open"),
            _markets(),
            run_id="run",
            freeze_sha256="abc",
        )


def test_fingerprint_is_canonical_and_64_hex_characters() -> None:
    fingerprint = holdout.design_fingerprint()
    assert len(fingerprint) == 64
    assert int(fingerprint, 16) >= 0
    assert fingerprint == holdout.design_fingerprint()
