import csv
from dataclasses import dataclass

import pytest

from src.kxbtc15m_development_economics import (
    DEVELOPMENT_LAST_TICKER,
    DevelopmentEconomicsError,
    FrozenMarket,
    collect_fee_changes,
    collect_outcomes,
    collect_series_snapshot,
    load_frozen_development_markets,
)


@dataclass(frozen=True)
class RawRef:
    source: str = "test"
    session_id: str = "session"
    request_id: str = "request"


@dataclass(frozen=True)
class Response:
    payload: dict
    raw_record: RawRef = RawRef()
    received_at_utc: str = "2026-08-12T12:00:00+00:00"


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get_json(self, path, *, params=None):
        self.calls.append((path, params))
        return self.responses.pop(0)


def write_anchors(path, *, include_holdout=False):
    tickers = [f"KXBTC15M-26AUG11{i:04d}-00" for i in range(1, 96)]
    tickers.append(
        "KXBTC15M-26AUG121445-45" if include_holdout else DEVELOPMENT_LAST_TICKER
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["market_index", "ticker"])
        writer.writeheader()
        for index, ticker in enumerate(tickers, start=1):
            writer.writerow({"market_index": index, "ticker": ticker})


def test_load_frozen_allowlist_exactly_96(tmp_path):
    path = tmp_path / "anchors.csv"
    write_anchors(path)
    markets = load_frozen_development_markets(path)
    assert len(markets) == 96
    assert markets[-1].ticker == DEVELOPMENT_LAST_TICKER


def test_load_frozen_allowlist_rejects_holdout(tmp_path):
    path = tmp_path / "anchors.csv"
    write_anchors(path, include_holdout=True)
    with pytest.raises(DevelopmentEconomicsError, match="holdout"):
        load_frozen_development_markets(path)


def test_collect_outcome_requires_finalized_yes_or_no():
    ticker = "KXBTC15M-26AUG111400-00"
    client = Client([Response({"market": {"ticker": ticker, "status": "finalized", "result": "yes"}})])
    rows = collect_outcomes(client, [FrozenMarket(2, ticker)], run_id="run")
    assert rows[0]["outcome_yes"] == "1"
    assert client.calls == [(f"/markets/{ticker}", None)]


def test_collect_outcome_fails_closed_on_unsettled_market():
    ticker = "KXBTC15M-26AUG111400-00"
    client = Client([Response({"market": {"ticker": ticker, "status": "closed", "result": ""}})])
    with pytest.raises(DevelopmentEconomicsError, match="finalized"):
        collect_outcomes(client, [FrozenMarket(2, ticker)], run_id="run")


def test_series_and_historical_fee_evidence_preserve_full_objects():
    client = Client(
        [
            Response({"series": {"ticker": "KXBTC15M", "fee_type": "quadratic", "fee_multiplier": 1}}),
            Response({"series_fee_change_arr": [{"id": "7", "series_ticker": "KXBTC15M", "fee_type": "flat", "fee_multiplier": 2, "scheduled_ts": "2026-09-01T00:00:00Z", "extra": "preserved"}]}),
        ]
    )
    series = collect_series_snapshot(client, run_id="run")
    changes = collect_fee_changes(client, run_id="run")
    assert series["fee_type"] == "quadratic"
    assert '"extra":"preserved"' in changes[0]["fee_change_json"]
    assert client.calls[1] == (
        "/series/fee_changes",
        {"series_ticker": "KXBTC15M", "show_historical": "true"},
    )
