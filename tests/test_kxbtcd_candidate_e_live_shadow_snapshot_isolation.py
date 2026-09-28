from decimal import Decimal
import json

from src.kxbtcd_candidate_e_prospective_live_collector import EventLadder, LadderMarket
from src.kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore


class FailingPublisher:
    def publish_if_due(self, **kwargs):
        raise OSError("dashboard volume unavailable")


def test_shadow_snapshot_publisher_is_optional_and_isolated_from_core(tmp_path):
    core = SoakSourceRuntimeCore(runtime_session_id="shadow-isolated", archive_root=tmp_path,
                                 live_shadow_snapshot_publisher=FailingPublisher())
    core.current_event = EventLadder("KXBTCD-TEST", "2026-09-09T01:00:00Z", 1788915600000, (
        LadderMarket("KXBTCD-TEST", "T1", Decimal("99900"), 0, 1, None),
    ))
    core.discovery_runtime_session_id = "shadow-isolated"
    core.open_kalshi_generation(opened_monotonic_ns=1)
    frame = json.dumps({"type": "orderbook_snapshot", "seq": 1, "msg": {
        "market_ticker": "T1", "yes_dollars_fp": [["0.5", "1"]], "no_dollars_fp": [["0.4", "1"]],
    }})
    # A dashboard output failure happens after raw append and Kalshi cache
    # application; it cannot change the collector's result or make it fatal.
    result = core.ingest_kalshi_ws_frame(raw_text=frame, received_monotonic_ns=2,
                                         received_utc="2026-09-09T00:59:02Z")
    assert result["ready"] is True
    assert core.manager("kalshi_production_ws").total_raw_bytes_written > 0
