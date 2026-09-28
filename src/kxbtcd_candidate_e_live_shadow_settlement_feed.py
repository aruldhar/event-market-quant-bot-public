"""One-way finalized-market feed from the collector to the shadow sidecar."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

from .kxbtcd_candidate_e_soak_archive import write_json_atomic
from .kxbtcd_candidate_e_live_shadow_settlement import OfficialKalshiSettlement


CANONICAL_SETTLEMENT_FEED_FILENAME = "official_final_settlements.json"
SETTLEMENT_FEED_SCHEMA_VERSION = "kxbtcd_candidate_e_live_shadow_settlement_feed.v1"


class LiveShadowSettlementFeedError(ValueError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveShadowSettlementFeedError(f"{field} is required")
    return value


class LiveShadowSettlementPublisher:
    """Append a de-duplicated sanitized finalized outcome via atomic replace."""

    def __init__(self, *, run_id: str, output_path: str | Path):
        self.run_id = _text(run_id, "run_id")
        self.output_path = Path(output_path)
        if self.output_path.name != CANONICAL_SETTLEMENT_FEED_FILENAME:
            raise LiveShadowSettlementFeedError("settlement feed filename is invalid")
        self._settlements = {
            item.market_ticker: item
            for item in (
                read_live_shadow_settlements(path=self.output_path, run_id=self.run_id)
                if self.output_path.exists() else ()
            )
        }

    def publish(self, settlement: OfficialKalshiSettlement) -> bool:
        settlement.validated_result()
        prior = self._settlements.get(settlement.market_ticker)
        if prior is not None:
            if prior != settlement:
                raise LiveShadowSettlementFeedError("conflicting official market settlement")
            return False
        self._settlements[settlement.market_ticker] = settlement
        write_json_atomic(self.output_path, {
            "schema_version": SETTLEMENT_FEED_SCHEMA_VERSION,
            "run_id": self.run_id,
            "settlements": [{
                "market_ticker": item.market_ticker,
                "official_market_status": item.official_market_status,
                "official_market_result": item.official_market_result,
                "observed_utc": item.observed_utc,
            } for item in self._settlements.values()],
        })
        return True


def read_live_shadow_settlements(*, path: str | Path, run_id: str) -> tuple[OfficialKalshiSettlement, ...]:
    source = Path(path)
    if source.name != CANONICAL_SETTLEMENT_FEED_FILENAME:
        raise LiveShadowSettlementFeedError("settlement feed filename is invalid")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveShadowSettlementFeedError("settlement feed is unreadable") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != SETTLEMENT_FEED_SCHEMA_VERSION:
        raise LiveShadowSettlementFeedError("settlement feed schema is invalid")
    if payload.get("run_id") != run_id:
        raise LiveShadowSettlementFeedError("settlement feed run id is invalid")
    rows = payload.get("settlements")
    if not isinstance(rows, list):
        raise LiveShadowSettlementFeedError("settlement feed rows are invalid")
    result = []
    tickers = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise LiveShadowSettlementFeedError("settlement row is invalid")
        settlement = OfficialKalshiSettlement(
            _text(row.get("market_ticker"), "market_ticker"),
            _text(row.get("official_market_status"), "official_market_status"),
            _text(row.get("official_market_result"), "official_market_result"),
            _text(row.get("observed_utc"), "observed_utc"),
        )
        settlement.validated_result()
        if settlement.market_ticker in tickers:
            raise LiveShadowSettlementFeedError("settlement feed has duplicate ticker")
        tickers.add(settlement.market_ticker)
        result.append(settlement)
    return tuple(result)
