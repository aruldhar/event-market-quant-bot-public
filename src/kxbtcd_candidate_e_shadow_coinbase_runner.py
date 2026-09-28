"""Descriptor-verified entry point for offline Coinbase candle reconstruction."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from .kxbtcd_candidate_e_shadow_archive_reader import iter_verified_closed_records
from .kxbtcd_candidate_e_shadow_coinbase_candle_replay import (
    ReconstructedCoinbaseCandle,
    iter_exact_completed_candles,
)


def iter_verified_completed_coinbase_candles(
    descriptor_paths: Iterable[str | Path],
) -> Iterator[ReconstructedCoinbaseCandle]:
    """Yield exact completed candles only from immutable verified artifacts."""
    yield from iter_exact_completed_candles(
        iter_verified_closed_records(descriptor_paths)
    )
