from decimal import Decimal
from pathlib import Path
import json

from src.kxbtcd_candidate_e_live_shadow_snapshot import CANONICAL_SNAPSHOT_FILENAME
from src.kxbtcd_candidate_e_live_shadow_snapshot_publisher import LiveShadowSnapshotPublisher
from src.kxbtcd_candidate_e_prospective_live_collector import CoinbaseMinuteClose, EventLadder, KalshiBookCache, LadderMarket
from src.kxbtcd_candidate_e_v2_rest_candle_readiness import V2BoundRestCandle


class Binding:
    def __init__(self):
        self.connected = True
        self.cache = KalshiBookCache(("T1", "T2"))


class Core:
    def __init__(self):
        self.current_event = EventLadder("KXBTCD-TEST", "2026-09-09T01:00:00Z", 1788915600000, (
            LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 0, 2, "BRR"),
            LadderMarket("KXBTCD-TEST", "T2", Decimal("100000"), 1, 2, "BRR"),
        ))
        self.v2_coinbase_rest_candle = V2BoundRestCandle("run-1", CoinbaseMinuteClose(
            1788915480, 1788915540, Decimal("100000"), 1, "2026-09-09T00:59:01Z"))
        self.connections = type("Connections", (), {"current_kalshi": Binding()})()


def snapshot(ticker, seq):
    return {"type": "orderbook_snapshot", "seq": seq, "msg": {
        "market_ticker": ticker, "yes_dollars_fp": [["0.5", "1"]], "no_dollars_fp": [["0.4", "1"]],
    }}


def test_publisher_requires_complete_ladder_and_rate_limits_atomic_output(tmp_path):
    core = Core()
    output = tmp_path / CANONICAL_SNAPSHOT_FILENAME
    publisher = LiveShadowSnapshotPublisher(run_id="run-1", output_path=output)
    assert publisher.publish_if_due(core=core, received_utc="2026-09-09T00:59:02Z", received_monotonic_ns=2) is False
    core.connections.current_kalshi.cache.apply_message(snapshot("T1", 1))
    core.connections.current_kalshi.cache.apply_message(snapshot("T2", 2))
    assert publisher.publish_if_due(core=core, received_utc="2026-09-09T00:59:02Z", received_monotonic_ns=2) is True
    assert publisher.publish_if_due(core=core, received_utc="2026-09-09T00:59:02Z", received_monotonic_ns=3) is False
    assert json.loads(output.read_text(encoding="utf-8"))["snapshot_sequence"] == 1
    assert publisher.publish_if_due(core=core, received_utc="2026-09-09T00:59:03Z", received_monotonic_ns=1_000_000_002) is True
    assert json.loads(output.read_text(encoding="utf-8"))["snapshot_sequence"] == 2
