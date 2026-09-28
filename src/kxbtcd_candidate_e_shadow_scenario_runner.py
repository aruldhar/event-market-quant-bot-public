"""Descriptor-to-observation entry point for offline hybrid scenario testing."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .kxbtcd_candidate_e_shadow_archive_reader import iter_verified_closed_records
from .kxbtcd_candidate_e_shadow_kalshi_replay import reconstruct_kalshi_generation
from .kxbtcd_candidate_e_shadow_micro_hybrid_scenario import (
    ShadowHybridExitObservation,
    evaluate_shadow_hybrid_exit,
)
from .kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import ReconciledPosition


def iter_verified_hybrid_exit_observations(
    descriptor_paths: Iterable[str | Path], *, subscribed_tickers: Sequence[str],
    market_ticker: str, position: ReconciledPosition,
    supplied_exit_fee: Decimal, required_total_net_proceeds: Decimal,
) -> Iterator[ShadowHybridExitObservation]:
    """Evaluate immutable Kalshi WebSocket evidence without writing anything.

    Archive descriptors are verified before parsing.  The replayer then rejects
    gaps or invalid frames, before the frozen scenario evaluator sees a book.
    """
    records = iter_verified_closed_records(descriptor_paths)
    books = reconstruct_kalshi_generation(
        records, subscribed_tickers=subscribed_tickers
    )
    yield from evaluate_shadow_hybrid_exit(
        books,
        market_ticker=market_ticker,
        position=position,
        supplied_exit_fee=supplied_exit_fee,
        required_total_net_proceeds=required_total_net_proceeds,
    )
