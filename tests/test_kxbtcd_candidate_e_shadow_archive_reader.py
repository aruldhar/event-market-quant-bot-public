import json

import pytest

from src.kxbtcd_candidate_e_shadow_archive_reader import (
    ShadowArchiveReaderError,
    iter_verified_closed_records,
)
from src.kxbtcd_candidate_e_soak_archive import close_raw_segment


def close_segment(tmp_path, *, raw: bytes, count: int, source="kalshi_production_ws"):
    path = tmp_path / "closed.jsonl"
    path.write_bytes(raw)
    close_raw_segment(
        raw_path=path,
        source=source,
        segment_start_utc="2026-09-07T00:00:00Z",
        segment_end_utc="2026-09-07T01:00:00Z",
        record_count=count,
    )
    return path.with_name(path.name + ".descriptor.json")


def test_reader_yields_only_records_from_verified_closed_segment(tmp_path):
    descriptor = close_segment(
        tmp_path,
        raw=(b'{"received_utc":"2026-09-07T00:00:01Z","raw_text":"one"}\n'
             b'{"received_utc":"2026-09-07T00:00:02Z","raw_text":"two"}\n'),
        count=2,
    )
    records = list(iter_verified_closed_records((descriptor,)))
    assert [row.record["raw_text"] for row in records] == ["one", "two"]
    assert {row.source for row in records} == {"kalshi_production_ws"}


def test_reader_rejects_invalid_json_even_when_archive_integrity_is_valid(tmp_path):
    descriptor = close_segment(tmp_path, raw=b'{not-json}\n', count=1)
    with pytest.raises(ShadowArchiveReaderError, match="invalid JSONL"):
        list(iter_verified_closed_records((descriptor,)))


def test_reader_rejects_unterminated_closed_jsonl_record(tmp_path):
    descriptor = close_segment(tmp_path, raw=b'{"raw_text":"one"}', count=1)
    with pytest.raises(ShadowArchiveReaderError, match="unterminated"):
        list(iter_verified_closed_records((descriptor,)))


def test_reader_rejects_descriptor_count_disagreement(tmp_path, monkeypatch):
    descriptor = close_segment(tmp_path, raw=b'{"raw_text":"one"}\n', count=1)
    import src.kxbtcd_candidate_e_shadow_archive_reader as reader

    actual = reader.validate_closed_segment(descriptor)
    monkeypatch.setattr(
        reader,
        "validate_closed_segment",
        lambda _: {**actual, "record_count": 2},
    )
    with pytest.raises(ShadowArchiveReaderError, match="record count mismatch"):
        list(iter_verified_closed_records((descriptor,)))


def test_reader_rejects_non_marketdata_segment_source(tmp_path):
    descriptor = close_segment(
        tmp_path,
        raw=(json.dumps({"raw_text": "one"}) + "\n").encode(),
        count=1,
        source="not_a_market_data_source",
    )
    with pytest.raises(ShadowArchiveReaderError, match="not allowed"):
        list(iter_verified_closed_records((descriptor,)))
