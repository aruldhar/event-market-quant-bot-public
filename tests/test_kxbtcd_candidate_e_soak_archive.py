import json
from pathlib import Path

import pytest

from src.kxbtcd_candidate_e_soak_archive import (
    SoakArchiveError,
    close_raw_segment,
    file_sha256,
    validate_closed_segment,
)


RAW_BYTES = (
    b'{"source":"kalshi","seq":1}\n'
    b'{"source":"coinbase","trade_id":2}\n'
) * 1000


def close_one(tmp_path):
    raw = tmp_path / "kalshi_20260904T140000Z.jsonl"
    raw.write_bytes(RAW_BYTES)

    raw_sha = file_sha256(raw)

    descriptor = close_raw_segment(
        raw_path=raw,
        source="kalshi_production_ws",
        segment_start_utc="2026-09-04T14:00:00Z",
        segment_end_utc="2026-09-04T15:00:00Z",
        record_count=2000,
    )

    return raw, raw_sha, descriptor


def test_close_segment_preserves_exact_raw_sha(tmp_path):
    raw, raw_sha, descriptor = close_one(
        tmp_path
    )

    compressed = Path(
        tmp_path,
        descriptor["compressed_filename"],
    )
    descriptor_path = raw.with_name(
        raw.name + ".descriptor.json"
    )

    assert not raw.exists()
    assert compressed.exists()
    assert descriptor_path.exists()

    assert (
        descriptor["uncompressed_sha256"]
        == raw_sha
    )

    validated = validate_closed_segment(
        descriptor_path
    )

    assert validated == descriptor


def test_descriptor_records_both_sizes_and_hashes(tmp_path):
    raw, _, descriptor = close_one(tmp_path)

    assert descriptor[
        "uncompressed_size_bytes"
    ] == len(RAW_BYTES)

    assert descriptor[
        "compressed_size_bytes"
    ] > 0

    assert len(
        descriptor["uncompressed_sha256"]
    ) == 64

    assert len(
        descriptor["compressed_sha256"]
    ) == 64


def test_compression_is_lossless_not_assumed_by_extension(tmp_path):
    raw, _, descriptor = close_one(tmp_path)

    descriptor_path = raw.with_name(
        raw.name + ".descriptor.json"
    )

    compressed = (
        descriptor_path.parent
        / descriptor["compressed_filename"]
    )

    data = bytearray(
        compressed.read_bytes()
    )

    data[-1] ^= 0x01
    compressed.write_bytes(bytes(data))

    with pytest.raises(
        SoakArchiveError,
        match="compressed artifact SHA-256 mismatch",
    ):
        validate_closed_segment(
            descriptor_path
        )


def test_raw_is_not_deleted_if_compression_verification_fails(
    tmp_path,
    monkeypatch,
):
    import src.kxbtcd_candidate_e_soak_archive as archive

    raw = tmp_path / "raw.jsonl"
    raw.write_bytes(RAW_BYTES)

    monkeypatch.setattr(
        archive,
        "decompressed_sha256_zstd",
        lambda path: "0" * 64,
    )

    with pytest.raises(
        SoakArchiveError,
        match="does not reproduce raw SHA-256",
    ):
        close_raw_segment(
            raw_path=raw,
            source="coinbase_exchange_ws",
            segment_start_utc="2026-09-04T14:00:00Z",
            segment_end_utc="2026-09-04T15:00:00Z",
            record_count=2000,
        )

    assert raw.exists()
    assert not (
        tmp_path / "raw.jsonl.zst"
    ).exists()
    assert not (
        tmp_path / "raw.jsonl.descriptor.json"
    ).exists()


def test_existing_final_compressed_file_fails_closed(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.write_bytes(RAW_BYTES)

    (tmp_path / "raw.jsonl.zst").write_bytes(
        b"unexpected"
    )

    with pytest.raises(
        SoakArchiveError,
        match="final compressed artifact already exists",
    ):
        close_raw_segment(
            raw_path=raw,
            source="kalshi_production_ws",
            segment_start_utc="2026-09-04T14:00:00Z",
            segment_end_utc="2026-09-04T15:00:00Z",
            record_count=1,
        )

    assert raw.exists()


def test_validation_rejects_missing_compressed_artifact(tmp_path):
    raw, _, descriptor = close_one(tmp_path)

    descriptor_path = raw.with_name(
        raw.name + ".descriptor.json"
    )

    compressed = (
        descriptor_path.parent
        / descriptor["compressed_filename"]
    )

    compressed.unlink()

    with pytest.raises(
        SoakArchiveError,
        match="verified compressed artifact missing",
    ):
        validate_closed_segment(
            descriptor_path
        )


def test_descriptor_is_strategy_independent(tmp_path):
    raw, _, descriptor = close_one(tmp_path)

    forbidden = (
        "candidate_probability",
        "signal",
        "pnl",
        "order",
        "fill",
        "settlement",
    )

    text = json.dumps(
        descriptor,
        sort_keys=True,
    ).lower()

    for word in forbidden:
        assert word not in text
