import json
from decimal import Decimal

from src.kxbtcd_candidate_e_shadow_coinbase_runner import (
    iter_verified_completed_coinbase_candles,
)
from src.kxbtcd_candidate_e_soak_archive import close_raw_segment


def test_runner_reads_exact_completed_candle_from_verified_archive(tmp_path):
    raw_path = tmp_path / "coinbase.jsonl"
    raw_path.write_text(json.dumps({
        "source": "coinbase_exchange_rest",
        "received_utc": "2026-09-08T00:01:02Z",
        "received_monotonic_ns": 9,
        "raw_text": "[[1788825600, 1, 2, 1.5, 456, 4]]",
        "request_identity": {"method": "GET", "status_code": 200,
            "params": {"granularity": 60, "start": "2026-09-08T00:00:00Z",
                       "end": "2026-09-08T00:01:00Z"}},
    }) + "\n", encoding="utf-8")
    close_raw_segment(
        raw_path=raw_path, source="coinbase_exchange_rest",
        segment_start_utc="2026-09-08T00:00:00Z",
        segment_end_utc="2026-09-08T01:00:00Z", record_count=1,
    )
    descriptor = raw_path.with_name(raw_path.name + ".descriptor.json")
    rows = list(iter_verified_completed_coinbase_candles((descriptor,)))
    assert [(item.minute_start_epoch_s, item.close) for item in rows] == [
        (1788825600, Decimal("456"))
    ]
