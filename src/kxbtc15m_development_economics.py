"""Frozen development-only economics inputs for KXBTC15M simulations."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


SERIES_TICKER = "KXBTC15M"
EXPECTED_DEVELOPMENT_MARKETS = 96
MAX_DEVELOPMENT_INDEX = 100
DEVELOPMENT_LAST_TICKER = "KXBTC15M-26AUG121430-30"
HOLDOUT_FIRST_TICKER = "KXBTC15M-26AUG121445-45"

OUTCOME_FIELDS = (
    "run_id",
    "market_index",
    "ticker",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "received_at_utc",
    "status",
    "result",
    "outcome_yes",
    "close_time",
    "settlement_ts",
    "market_fields_json",
)

SERIES_FIELDS = (
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "received_at_utc",
    "series_ticker",
    "fee_type",
    "fee_multiplier",
    "series_json",
)

FEE_CHANGE_FIELDS = (
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "received_at_utc",
    "series_ticker",
    "change_id",
    "fee_type",
    "fee_multiplier",
    "scheduled_ts",
    "fee_change_json",
)


class DevelopmentEconomicsError(RuntimeError):
    """Raised when a development-only economics invariant is violated."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class RawFirstJsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference
    received_at_utc: str


class RawFirstJsonClient(Protocol):
    def get_json(
        self, path: str, *, params: Mapping[str, Any] | None = None
    ) -> RawFirstJsonResponse: ...


@dataclass(frozen=True)
class FrozenMarket:
    market_index: int
    ticker: str


def sha256_path(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_frozen_development_markets(path: str | Path) -> tuple[FrozenMarket, ...]:
    """Derive the exact request allowlist from the frozen dynamics anchors."""

    source = Path(path)
    try:
        with source.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not {"market_index", "ticker"}.issubset(reader.fieldnames or ()):
                raise DevelopmentEconomicsError(
                    "anchors CSV must contain market_index and ticker"
                )
            pairs: set[tuple[int, str]] = set()
            ticker_to_index: dict[str, int] = {}
            index_to_ticker: dict[int, str] = {}
            for row_number, row in enumerate(reader, start=2):
                ticker = (row.get("ticker") or "").strip()
                try:
                    market_index = int(row.get("market_index") or "")
                except ValueError as exc:
                    raise DevelopmentEconomicsError(
                        f"anchors row {row_number} has invalid market_index"
                    ) from exc
                if not ticker.startswith(f"{SERIES_TICKER}-"):
                    raise DevelopmentEconomicsError(
                        f"anchors row {row_number} is outside {SERIES_TICKER}"
                    )
                prior_index = ticker_to_index.setdefault(ticker, market_index)
                prior_ticker = index_to_ticker.setdefault(market_index, ticker)
                if prior_index != market_index or prior_ticker != ticker:
                    raise DevelopmentEconomicsError(
                        "anchors CSV has inconsistent market index/ticker mapping"
                    )
                pairs.add((market_index, ticker))
    except OSError as exc:
        raise DevelopmentEconomicsError(f"could not read anchors CSV: {exc}") from exc

    markets = tuple(FrozenMarket(*pair) for pair in sorted(pairs))
    if len(markets) != EXPECTED_DEVELOPMENT_MARKETS:
        raise DevelopmentEconomicsError(
            f"expected {EXPECTED_DEVELOPMENT_MARKETS} eligible development markets; "
            f"found {len(markets)}"
        )
    if any(not 1 <= market.market_index <= MAX_DEVELOPMENT_INDEX for market in markets):
        raise DevelopmentEconomicsError("development allowlist contains an index outside 1..100")
    if any(market.ticker >= HOLDOUT_FIRST_TICKER for market in markets):
        raise DevelopmentEconomicsError("holdout ticker entered the development allowlist")
    if markets[-1].ticker != DEVELOPMENT_LAST_TICKER:
        raise DevelopmentEconomicsError("development allowlist does not end at the frozen boundary")
    return markets


def collect_outcomes(
    client: RawFirstJsonClient,
    markets: Sequence[FrozenMarket],
    *,
    run_id: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for frozen in markets:
        if frozen.market_index > MAX_DEVELOPMENT_INDEX or frozen.ticker >= HOLDOUT_FIRST_TICKER:
            raise DevelopmentEconomicsError(
                f"refusing non-development market request: {frozen.ticker}"
            )
        response = client.get_json(f"/markets/{frozen.ticker}")
        market = response.payload.get("market")
        if not isinstance(market, Mapping):
            raise DevelopmentEconomicsError(
                f"{frozen.ticker}: response missing market object"
            )
        if market.get("ticker") != frozen.ticker:
            raise DevelopmentEconomicsError(
                f"{frozen.ticker}: response ticker mismatch"
            )
        status = str(market.get("status") or "").lower()
        result = str(market.get("result") or "").lower()
        if status != "finalized":
            raise DevelopmentEconomicsError(
                f"{frozen.ticker}: expected finalized status; got {status!r}"
            )
        if result not in {"yes", "no"}:
            raise DevelopmentEconomicsError(
                f"{frozen.ticker}: expected yes/no result; got {result!r}"
            )
        raw = response.raw_record
        rows.append(
            {
                "run_id": run_id,
                "market_index": str(frozen.market_index),
                "ticker": frozen.ticker,
                "raw_source": raw.source,
                "raw_session_id": raw.session_id,
                "raw_request_id": raw.request_id,
                "received_at_utc": response.received_at_utc,
                "status": status,
                "result": result,
                "outcome_yes": "1" if result == "yes" else "0",
                "close_time": _text(market.get("close_time")),
                "settlement_ts": _text(market.get("settlement_ts")),
                "market_fields_json": json.dumps(
                    sorted(str(key) for key in market), separators=(",", ":")
                ),
            }
        )
    return rows


def collect_series_snapshot(
    client: RawFirstJsonClient, *, run_id: str
) -> dict[str, str]:
    response = client.get_json(f"/series/{SERIES_TICKER}")
    series = response.payload.get("series")
    if not isinstance(series, Mapping):
        raise DevelopmentEconomicsError("series response missing series object")
    observed_ticker = _text(series.get("ticker") or series.get("series_ticker"))
    if observed_ticker != SERIES_TICKER:
        raise DevelopmentEconomicsError(
            f"series response ticker mismatch: {observed_ticker!r}"
        )
    raw = response.raw_record
    return {
        "run_id": run_id,
        "raw_source": raw.source,
        "raw_session_id": raw.session_id,
        "raw_request_id": raw.request_id,
        "received_at_utc": response.received_at_utc,
        "series_ticker": observed_ticker,
        "fee_type": _text(series.get("fee_type")),
        "fee_multiplier": _text(series.get("fee_multiplier")),
        "series_json": json.dumps(series, sort_keys=True, separators=(",", ":")),
    }


def collect_fee_changes(
    client: RawFirstJsonClient, *, run_id: str
) -> list[dict[str, str]]:
    response = client.get_json(
        "/series/fee_changes",
        params={"series_ticker": SERIES_TICKER, "show_historical": "true"},
    )
    records = response.payload.get("series_fee_change_arr")
    if not isinstance(records, list):
        raise DevelopmentEconomicsError(
            "fee-history response missing series_fee_change_arr list"
        )
    raw = response.raw_record
    rows: list[dict[str, str]] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise DevelopmentEconomicsError(
                f"fee-history record {index} is not an object"
            )
        ticker = _text(record.get("series_ticker"))
        if ticker != SERIES_TICKER:
            raise DevelopmentEconomicsError(
                f"fee-history record {index} ticker mismatch: {ticker!r}"
            )
        rows.append(
            {
                "run_id": run_id,
                "raw_source": raw.source,
                "raw_session_id": raw.session_id,
                "raw_request_id": raw.request_id,
                "received_at_utc": response.received_at_utc,
                "series_ticker": ticker,
                "change_id": _text(record.get("id")),
                "fee_type": _text(record.get("fee_type")),
                "fee_multiplier": _text(record.get("fee_multiplier")),
                "scheduled_ts": _text(record.get("scheduled_ts")),
                "fee_change_json": json.dumps(
                    record, sort_keys=True, separators=(",", ":")
                ),
            }
        )
    return rows


def write_csv(path: str | Path, fields: Sequence[str], rows: Sequence[Mapping[str, str]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return target


def _text(value: Any) -> str:
    return "" if value is None else str(value)
