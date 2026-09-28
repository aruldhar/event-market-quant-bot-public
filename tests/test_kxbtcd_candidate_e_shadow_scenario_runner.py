import json
from decimal import Decimal

from src.kxbtcd_candidate_e_shadow_scenario_runner import (
    iter_verified_hybrid_exit_observations,
)
from src.kxbtcd_candidate_e_soak_archive import close_raw_segment
from src.kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import ReconciledPosition
from src.kxbtcd_candidate_e_v2_micro_hybrid_state_machine_offline import HybridProbeState


TICKERS = ("KXBTCD-TEST-T100", "KXBTCD-TEST-T101")


def _frame(payload, ns):
    return {
        "source": "kalshi_production_ws",
        "received_utc": "2026-09-08T00:00:00Z",
        "received_monotonic_ns": ns,
        "raw_text": json.dumps(payload),
    }


def _snapshot(ticker, seq, price):
    return {"type": "orderbook_snapshot", "seq": seq, "msg": {
        "market_ticker": ticker, "yes_dollars_fp": [[price, "0.01"]],
        "no_dollars_fp": [["0.30", "1"]],
    }}


def _closed_descriptor(tmp_path, frames):
    raw_path = tmp_path / "kalshi.jsonl"
    raw_path.write_text(
        "".join(json.dumps(frame) + "\n" for frame in frames), encoding="utf-8"
    )
    close_raw_segment(
        raw_path=raw_path, source="kalshi_production_ws",
        segment_start_utc="2026-09-08T00:00:00Z",
        segment_end_utc="2026-09-08T01:00:00Z", record_count=len(frames),
    )
    return raw_path.with_name(raw_path.name + ".descriptor.json")


def test_runner_verifies_archives_replays_ladder_and_stops_at_first_eligible_exit(tmp_path):
    descriptor = _closed_descriptor(tmp_path, (
        _frame(_snapshot(TICKERS[0], 1, "0.70"), 1),
        _frame(_snapshot(TICKERS[1], 2, "0.71"), 2),
        _frame({"type": "orderbook_delta", "seq": 3, "msg": {
            "market_ticker": TICKERS[0], "side": "yes", "price_dollars": "0.70",
            "delta_fp": "0.01", "ts_ms": 3}}, 3),
        _frame({"type": "orderbook_delta", "seq": 4, "msg": {
            "market_ticker": TICKERS[0], "side": "yes", "price_dollars": "0.80",
            "delta_fp": "0.01", "ts_ms": 4}}, 4),
    ))
    observations = list(iter_verified_hybrid_exit_observations(
        (descriptor,), subscribed_tickers=TICKERS, market_ticker=TICKERS[0],
        position=ReconciledPosition(Decimal("0.01"), Decimal("0")),
        supplied_exit_fee=Decimal("0"), required_total_net_proceeds=Decimal("0.008"),
    ))
    assert [item.state for item in observations] == [
        HybridProbeState.LONG_RESTING_EXIT,
        HybridProbeState.CANCEL_RECONCILIATION_REQUIRED,
    ]
    assert observations[-1].received_monotonic_ns == 4
