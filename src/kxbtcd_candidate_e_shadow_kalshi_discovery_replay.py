"""Recover complete selected KXBTCD ladders from closed Kalshi REST evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Iterator, Mapping

from .kxbtcd_candidate_e_prospective_live_collector import (
    EventLadder,
    build_ladders_from_markets,
)
from .kxbtcd_candidate_e_shadow_archive_reader import ArchivedRawRecord
from .kxbtcd_candidate_e_soak_source_lifecycle import choose_current_event_ladder


class ShadowKalshiDiscoveryReplayError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconstructedEventLadder:
    ladder: EventLadder
    received_utc: str
    received_monotonic_ns: int


def iter_current_event_ladders(
    records: Iterable[ArchivedRawRecord], *, selection_timestamp_ms: int,
) -> Iterator[ReconstructedEventLadder]:
    """Yield only full, successful archived KXBTCD market discovery results."""
    if isinstance(selection_timestamp_ms, bool) or selection_timestamp_ms < 0:
        raise ShadowKalshiDiscoveryReplayError("selection timestamp is invalid")
    for archived in records:
        if archived.source != "kalshi_production_rest":
            raise ShadowKalshiDiscoveryReplayError("replay accepts Kalshi REST records only")
        wrapper = archived.record
        if wrapper.get("source") != "kalshi_production_rest":
            raise ShadowKalshiDiscoveryReplayError("raw wrapper source does not match descriptor")
        received_utc = wrapper.get("received_utc")
        received_ns = wrapper.get("received_monotonic_ns")
        if not isinstance(received_utc, str) or not received_utc:
            raise ShadowKalshiDiscoveryReplayError("raw wrapper is missing receipt UTC")
        if isinstance(received_ns, bool) or not isinstance(received_ns, int) or received_ns < 0:
            raise ShadowKalshiDiscoveryReplayError("raw wrapper has invalid receipt monotonic time")
        request = wrapper.get("request_identity")
        if not isinstance(request, Mapping) or request.get("method") != "GET" or request.get("status_code") != 200:
            raise ShadowKalshiDiscoveryReplayError("discovery response is not successful exact GET")
        raw_text = wrapper.get("raw_text")
        if not isinstance(raw_text, str):
            raise ShadowKalshiDiscoveryReplayError("raw wrapper is missing discovery text")
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ShadowKalshiDiscoveryReplayError("discovery response is invalid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ShadowKalshiDiscoveryReplayError("discovery response root must be object")
        if payload.get("cursor") is not None and str(payload["cursor"]).strip():
            raise ShadowKalshiDiscoveryReplayError("discovery response is paginated/incomplete")
        try:
            ladder = choose_current_event_ladder(
                build_ladders_from_markets(payload),
                now_timestamp_ms=selection_timestamp_ms,
            )
        except Exception as exc:
            raise ShadowKalshiDiscoveryReplayError("discovery response cannot prove current full ladder") from exc
        yield ReconstructedEventLadder(
            ladder=ladder, received_utc=received_utc,
            received_monotonic_ns=received_ns,
        )
