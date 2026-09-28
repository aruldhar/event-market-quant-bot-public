"""Shared fail-closed source-runtime exception classification.

A source transport outage and a local evidence/invariant failure are not the
same thing.

Recoverable source/transport failures may arm reconnect backoff.

Local failures involving raw persistence, archive integrity, runtime state, or
worker-generation invariants must terminate fail-closed and MUST NOT be
misclassified as network reconnect failures.
"""
from __future__ import annotations

from .kxbtcd_candidate_e_runtime_raw_journal import (
    RuntimeRawJournalError,
)
from .kxbtcd_candidate_e_prospective_live_collector import (
    ProspectiveLiveCollectorError,
)
from .kxbtcd_candidate_e_soak_archive import (
    SoakArchiveError,
)
from .kxbtcd_candidate_e_soak_coinbase_worker import (
    CoinbaseWorkerSessionError,
)
from .kxbtcd_candidate_e_soak_kalshi_worker import (
    KalshiWorkerSessionError,
)
from .kxbtcd_candidate_e_soak_runtime_core import (
    SoakRuntimeCoreError,
)
from .kxbtcd_candidate_e_soak_source_lifecycle import (
    KalshiHourlySuccessorUnavailable,
)
from .kxbtcd_candidate_e_soak_segment_manager import (
    SoakSegmentManagerError,
)


LOCAL_FATAL_TYPES = (
    RuntimeRawJournalError,
    ProspectiveLiveCollectorError,
    SoakArchiveError,
    SoakSegmentManagerError,
    SoakRuntimeCoreError,
    CoinbaseWorkerSessionError,
    KalshiWorkerSessionError,
)


def is_local_fatal_exception(
    exc: BaseException,
) -> bool:
    # A syntactically valid raw discovery response can temporarily omit the
    # next hourly ladder during venue publication.  That is recoverable and
    # must retry under the Kalshi source backoff rather than terminate.
    if isinstance(exc, KalshiHourlySuccessorUnavailable):
        return False
    return isinstance(
        exc,
        LOCAL_FATAL_TYPES,
    )
