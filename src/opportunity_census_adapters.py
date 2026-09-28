"""Venue-neutral event-first discovery adapters for opportunity census v1.

The census keeps two derived layers from the same raw response:

1. one event/opportunity row per source event; and
2. source-native contract snapshot rows for markets/contracts nested inside that event.

The second layer preserves quote semantics instead of pretending that every
venue exposes the same notion of bid, ask, probability, fee, or liquidity.
This module performs no network I/O, authentication, ranking, modeling, or
order actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

DISCOVERY_SCHEMA_VERSION = "census_opportunity_identity.v1"
CONTRACT_SNAPSHOT_SCHEMA_VERSION = "census_contract_snapshot.v1"

DISCOVERY_COLUMNS = (
    "schema_version",
    "venue_id",
    "source_opportunity_type",
    "source_opportunity_id",
    "source_event_id",
    "source_series_id",
    "source_ticker",
    "source_title",
    "source_subtitle",
    "source_category",
    "source_subcategory",
    "product_type_source",
    "market_status_source",
    "source_event_time",
    "source_start_time",
    "source_end_time",
    "contract_count_source",
    "volume_source",
    "liquidity_source",
    "open_interest_source",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "local_request_start_utc",
    "local_request_start_monotonic_ns",
    "local_receive_utc",
    "local_receive_monotonic_ns",
)

CONTRACT_SNAPSHOT_COLUMNS = (
    "schema_version",
    "venue_id",
    "source_event_id",
    "source_contract_id",
    "source_contract_ticker",
    "source_contract_title",
    "source_contract_status",
    "source_contract_type",
    "quote_semantics_source",
    "best_bid_source",
    "best_ask_source",
    "last_trade_price_source",
    "yes_bid_source",
    "yes_ask_source",
    "yes_bid_size_source",
    "yes_ask_size_source",
    "no_bid_source",
    "no_ask_source",
    "yes_price_source",
    "no_price_source",
    "reference_probability_source",
    "payout_per_100_source",
    "total_shares_source",
    "volume_source",
    "volume_24h_source",
    "open_interest_source",
    "liquidity_source",
    "fee_coefficient_source",
    "source_start_time",
    "source_end_time",
    "source_updated_time",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "local_request_start_utc",
    "local_request_start_monotonic_ns",
    "local_receive_utc",
    "local_receive_monotonic_ns",
)

SUPPORTED_PUBLIC_DISCOVERY_CANDIDATES = {
    "kalshi",
    "gemini_predictions",
    "polymarket_us",
    "crypto_com_predictions",
}


class CensusAdapterError(RuntimeError):
    """Raised when a documented discovery response violates adapter assumptions."""


@dataclass(frozen=True)
class ObservationContext:
    raw_source: str
    raw_session_id: str
    raw_request_id: str
    request_started_at_utc: str
    request_started_monotonic_ns: int
    received_at_utc: str
    received_monotonic_ns: int


@dataclass(frozen=True)
class PageResult:
    rows: tuple[dict[str, Any], ...]
    next_params: dict[str, Any] | None
    contract_rows: tuple[dict[str, Any], ...] = ()


class DiscoveryAdapter:
    candidate_id: str
    source_name: str
    base_url: str
    raw_root: str
    path: str

    def initial_params(self) -> dict[str, Any]:
        raise NotImplementedError

    def parse_page(
        self,
        payload: Mapping[str, Any],
        *,
        params: Mapping[str, Any],
        observation: ObservationContext,
    ) -> PageResult:
        raise NotImplementedError


class KalshiDiscoveryAdapter(DiscoveryAdapter):
    """Discover open non-MVE Kalshi events and their nested market snapshots."""

    candidate_id = "kalshi"
    source_name = "kalshi_public_rest"
    base_url = "https://external-api.kalshi.com/trade-api/v2"
    raw_root = "data/raw/kalshi_rest"
    path = "/events"

    def initial_params(self) -> dict[str, Any]:
        # Get Events excludes multivariate events and caps pages at 200.
        # Nested markets remain a separate derived layer, so event counts stay
        # event-first even when contract economics are preserved from the same
        # response.
        return {"status": "open", "limit": 200, "with_nested_markets": True}

    def parse_page(self, payload, *, params, observation) -> PageResult:
        events = _list_field(payload, "events", self.candidate_id)
        rows: list[dict[str, Any]] = []
        contract_rows: list[dict[str, Any]] = []
        for index, raw_event in enumerate(events):
            event = _mapping_item(raw_event, self.candidate_id, index)
            event_ticker = _required_text(
                event.get("event_ticker"), f"kalshi.events[{index}].event_ticker"
            )
            markets = event.get("markets")
            if markets is None:
                markets = []
            if not isinstance(markets, list):
                raise CensusAdapterError(
                    f"kalshi.events[{index}].markets must be a list when nested"
                )
            rows.append(
                _row(
                    self.candidate_id,
                    observation,
                    source_opportunity_type="event",
                    source_opportunity_id=event_ticker,
                    source_event_id=event_ticker,
                    source_series_id=event.get("series_ticker"),
                    source_ticker=event_ticker,
                    source_title=event.get("title"),
                    source_subtitle=event.get("sub_title"),
                    source_category=event.get("category"),
                    source_event_time=event.get("strike_date"),
                    contract_count_source=len(markets),
                )
            )
            for midx, raw_market in enumerate(markets):
                market = _mapping_item(
                    raw_market, self.candidate_id, f"{index}.markets[{midx}]"
                )
                ticker = _required_text(
                    market.get("ticker"),
                    f"kalshi.events[{index}].markets[{midx}].ticker",
                )
                contract_rows.append(
                    _contract_row(
                        self.candidate_id,
                        observation,
                        source_event_id=event_ticker,
                        source_contract_id=ticker,
                        source_contract_ticker=ticker,
                        source_contract_title=market.get("title")
                        or market.get("subtitle")
                        or market.get("yes_sub_title"),
                        source_contract_status=market.get("status"),
                        source_contract_type=market.get("market_type"),
                        quote_semantics_source="kalshi_yes_no_binary_market_quotes",
                        yes_bid_source=market.get("yes_bid_dollars"),
                        yes_ask_source=market.get("yes_ask_dollars"),
                        yes_bid_size_source=market.get("yes_bid_size_fp"),
                        yes_ask_size_source=market.get("yes_ask_size_fp"),
                        no_bid_source=market.get("no_bid_dollars"),
                        no_ask_source=market.get("no_ask_dollars"),
                        last_trade_price_source=market.get("last_price_dollars"),
                        volume_source=market.get("volume_fp"),
                        volume_24h_source=market.get("volume_24h_fp"),
                        open_interest_source=market.get("open_interest_fp"),
                        liquidity_source=market.get("liquidity_dollars"),
                        source_start_time=market.get("open_time"),
                        source_end_time=market.get("close_time"),
                        source_updated_time=market.get("updated_time"),
                    )
                )
        cursor = payload.get("cursor")
        if cursor in (None, ""):
            return PageResult(tuple(rows), None, tuple(contract_rows))
        if not isinstance(cursor, str):
            raise CensusAdapterError("kalshi cursor must be text or null")
        next_params = dict(params)
        next_params["cursor"] = cursor
        return PageResult(tuple(rows), next_params, tuple(contract_rows))


class GeminiDiscoveryAdapter(DiscoveryAdapter):
    candidate_id = "gemini_predictions"
    source_name = "gemini_predictions_public_rest"
    base_url = "https://api.gemini.com"
    raw_root = "data/raw/gemini_predictions_rest"
    path = "/v1/prediction-markets/events"

    def initial_params(self) -> dict[str, Any]:
        return {"status": "active", "limit": 500, "offset": 0}

    def parse_page(self, payload, *, params, observation) -> PageResult:
        events = _list_field(payload, "data", self.candidate_id)
        rows: list[dict[str, Any]] = []
        contract_rows: list[dict[str, Any]] = []
        for eidx, raw_event in enumerate(events):
            event = _mapping_item(raw_event, self.candidate_id, eidx)
            event_id = _required_text(event.get("id"), f"gemini.data[{eidx}].id")
            contracts = event.get("contracts")
            if contracts is None:
                contracts = []
            if not isinstance(contracts, list):
                raise CensusAdapterError(f"gemini.data[{eidx}].contracts must be a list")
            subcategory = event.get("subcategory")
            subcategory_name = (
                subcategory.get("name") if isinstance(subcategory, Mapping) else None
            )
            rows.append(
                _row(
                    self.candidate_id,
                    observation,
                    source_opportunity_type="event",
                    source_opportunity_id=event_id,
                    source_event_id=event_id,
                    source_series_id=event.get("series"),
                    source_ticker=event.get("ticker") or event.get("slug"),
                    source_title=event.get("title"),
                    source_category=event.get("category"),
                    source_subcategory=subcategory_name,
                    product_type_source=event.get("type"),
                    market_status_source=event.get("status"),
                    source_event_time=event.get("effectiveDate"),
                    source_start_time=event.get("effectiveDate"),
                    source_end_time=event.get("expiryDate"),
                    contract_count_source=len(contracts),
                    volume_source=event.get("volume"),
                    liquidity_source=event.get("liquidity"),
                )
            )
            for cidx, raw_contract in enumerate(contracts):
                contract = _mapping_item(
                    raw_contract, self.candidate_id, f"{eidx}.contracts[{cidx}]"
                )
                contract_id = _required_text(
                    contract.get("id"),
                    f"gemini.data[{eidx}].contracts[{cidx}].id",
                )
                prices = contract.get("prices")
                if prices is None:
                    prices = {}
                if not isinstance(prices, Mapping):
                    raise CensusAdapterError(
                        f"gemini.data[{eidx}].contracts[{cidx}].prices must be an object"
                    )
                contract_rows.append(
                    _contract_row(
                        self.candidate_id,
                        observation,
                        source_event_id=event_id,
                        source_contract_id=contract_id,
                        source_contract_ticker=contract.get("instrumentSymbol")
                        or contract.get("ticker"),
                        source_contract_title=contract.get("label")
                        or contract.get("abbreviatedName"),
                        source_contract_status=contract.get("status"),
                        source_contract_type=contract.get("marketState"),
                        quote_semantics_source="gemini_contract_best_bid_ask",
                        best_bid_source=prices.get("bestBid"),
                        best_ask_source=prices.get("bestAsk"),
                        last_trade_price_source=prices.get("lastTradePrice"),
                        total_shares_source=contract.get("totalShares"),
                        source_start_time=contract.get("effectiveDate"),
                        source_end_time=contract.get("expiryDate"),
                        source_updated_time=contract.get("updatedAt"),
                    )
                )
        pagination = payload.get("pagination")
        if not isinstance(pagination, Mapping):
            raise CensusAdapterError("gemini pagination must be an object")
        limit = _positive_int(params.get("limit"), "gemini limit")
        offset = _nonnegative_int(params.get("offset"), "gemini offset")
        total = pagination.get("total")
        if total is not None:
            total = _nonnegative_int(total, "gemini pagination.total")
            if offset + len(events) >= total:
                return PageResult(tuple(rows), None, tuple(contract_rows))
        elif len(events) < limit:
            return PageResult(tuple(rows), None, tuple(contract_rows))
        if not events:
            return PageResult(tuple(rows), None, tuple(contract_rows))
        next_params = dict(params)
        next_params["offset"] = offset + limit
        return PageResult(tuple(rows), next_params, tuple(contract_rows))


class PolymarketUSDiscoveryAdapter(DiscoveryAdapter):
    candidate_id = "polymarket_us"
    source_name = "polymarket_us_public_rest"
    base_url = "https://gateway.polymarket.us"
    raw_root = "data/raw/polymarket_us_rest"
    path = "/v1/events"

    def initial_params(self) -> dict[str, Any]:
        return {
            "active": "true",
            "closed": "false",
            "archived": "false",
            "limit": 50,
            "offset": 0,
        }

    def parse_page(self, payload, *, params, observation) -> PageResult:
        events = _list_field(payload, "events", self.candidate_id)
        rows: list[dict[str, Any]] = []
        contract_rows: list[dict[str, Any]] = []
        for index, raw_event in enumerate(events):
            event = _mapping_item(raw_event, self.candidate_id, index)
            event_id = event.get("id")
            if event_id is None:
                raise CensusAdapterError(f"polymarket_us.events[{index}].id is required")
            ticker = event.get("ticker") or event.get("slug")
            if ticker is not None:
                ticker = _required_text(ticker, f"polymarket_us.events[{index}].ticker")
            markets = event.get("markets")
            if markets is None:
                markets = []
            if not isinstance(markets, list):
                raise CensusAdapterError(
                    f"polymarket_us.events[{index}].markets must be a list"
                )
            rows.append(
                _row(
                    self.candidate_id,
                    observation,
                    source_opportunity_type="event",
                    source_opportunity_id=event_id,
                    source_event_id=event_id,
                    source_series_id=event.get("seriesSlug"),
                    source_ticker=ticker,
                    source_title=event.get("title"),
                    source_subtitle=event.get("subtitle"),
                    source_category=event.get("category"),
                    source_subcategory=event.get("subcategory"),
                    market_status_source=_polymarket_status(event),
                    source_event_time=event.get("eventDate") or event.get("startTime"),
                    source_start_time=event.get("startDate") or event.get("startTime"),
                    source_end_time=event.get("endDate"),
                    contract_count_source=len(markets),
                    volume_source=event.get("volume"),
                    liquidity_source=event.get("liquidity"),
                    open_interest_source=event.get("openInterest"),
                )
            )
            for midx, raw_market in enumerate(markets):
                market = _mapping_item(
                    raw_market, self.candidate_id, f"{index}.markets[{midx}]"
                )
                market_id = market.get("id")
                if market_id is None:
                    raise CensusAdapterError(
                        f"polymarket_us.events[{index}].markets[{midx}].id is required"
                    )
                bid = _amount_value(market.get("bestBidQuote"), "bestBidQuote")
                ask = _amount_value(market.get("bestAskQuote"), "bestAskQuote")
                contract_rows.append(
                    _contract_row(
                        self.candidate_id,
                        observation,
                        source_event_id=event_id,
                        source_contract_id=market_id,
                        source_contract_ticker=market.get("slug") or market.get("ticker"),
                        source_contract_title=market.get("question")
                        or market.get("title"),
                        source_contract_status=_polymarket_status(market),
                        source_contract_type=market.get("sportsMarketTypeV2")
                        or market.get("sportsMarketType")
                        or market.get("marketType"),
                        quote_semantics_source="polymarket_us_market_best_bid_ask",
                        best_bid_source=bid,
                        best_ask_source=ask,
                        fee_coefficient_source=market.get("feeCoefficient"),
                        source_start_time=market.get("startDate")
                        or market.get("gameStartTime"),
                        source_end_time=market.get("endDate"),
                        source_updated_time=market.get("updatedAt"),
                    )
                )
        limit = _positive_int(params.get("limit"), "polymarket_us limit")
        offset = _nonnegative_int(params.get("offset"), "polymarket_us offset")
        if len(events) < limit:
            return PageResult(tuple(rows), None, tuple(contract_rows))
        next_params = dict(params)
        next_params["offset"] = offset + limit
        return PageResult(tuple(rows), next_params, tuple(contract_rows))


class CryptoComDiscoveryAdapter(DiscoveryAdapter):
    candidate_id = "crypto_com_predictions"
    source_name = "crypto_com_predictions_public_rest"
    base_url = "https://data-api.crypto.com"
    raw_root = "data/raw/crypto_com_predictions_rest"
    path = "/api/v1/predictions/events"

    def initial_params(self) -> dict[str, Any]:
        return {"status": "active", "limit": 50}

    def parse_page(self, payload, *, params, observation) -> PageResult:
        events = _list_field(payload, "data", self.candidate_id)
        rows: list[dict[str, Any]] = []
        contract_rows: list[dict[str, Any]] = []
        for eidx, raw_event in enumerate(events):
            event = _mapping_item(raw_event, self.candidate_id, eidx)
            event_id = _required_text(event.get("id"), f"crypto_com.data[{eidx}].id")
            contracts = event.get("contracts")
            if contracts is None:
                contracts = []
            if not isinstance(contracts, list):
                raise CensusAdapterError(
                    f"crypto_com.data[{eidx}].contracts must be a list when present"
                )
            count = event.get("contracts_count")
            if count is not None:
                count = _nonnegative_int(count, f"crypto_com.data[{eidx}].contracts_count")
            else:
                count = len(contracts)
            rows.append(
                _row(
                    self.candidate_id,
                    observation,
                    source_opportunity_type="event",
                    source_opportunity_id=event_id,
                    source_event_id=event_id,
                    source_ticker=event_id,
                    source_title=event.get("title"),
                    source_category=event.get("kind"),
                    source_subcategory=event.get("type"),
                    product_type_source=event.get("market_format"),
                    market_status_source=event.get("status"),
                    source_event_time=event.get("event_date"),
                    contract_count_source=count,
                )
            )
            for cidx, raw_contract in enumerate(contracts):
                contract = _mapping_item(
                    raw_contract, self.candidate_id, f"{eidx}.contracts[{cidx}]"
                )
                contract_id = _required_text(
                    contract.get("id"),
                    f"crypto_com.data[{eidx}].contracts[{cidx}].id",
                )
                market_type = contract.get("market_type")
                if isinstance(market_type, Mapping):
                    contract_type = (
                        market_type.get("name")
                        or market_type.get("title")
                        or market_type.get("period")
                    )
                else:
                    contract_type = None
                contract_rows.append(
                    _contract_row(
                        self.candidate_id,
                        observation,
                        source_event_id=event_id,
                        source_contract_id=contract_id,
                        source_contract_ticker=contract.get("symbol"),
                        source_contract_title=contract.get("title"),
                        source_contract_status=contract.get("status"),
                        source_contract_type=contract_type,
                        quote_semantics_source="crypto_com_display_yes_no_chance",
                        yes_price_source=contract.get("yes"),
                        no_price_source=contract.get("no"),
                        reference_probability_source=contract.get("chance"),
                        payout_per_100_source=contract.get("payout_per_100"),
                    )
                )
        pagination = payload.get("pagination")
        if not isinstance(pagination, Mapping):
            raise CensusAdapterError("crypto_com pagination must be an object")
        has_more = pagination.get("has_more")
        if not isinstance(has_more, bool):
            raise CensusAdapterError("crypto_com pagination.has_more must be boolean")
        if not has_more:
            return PageResult(tuple(rows), None, tuple(contract_rows))
        cursor = pagination.get("next_cursor")
        if not isinstance(cursor, str) or not cursor:
            raise CensusAdapterError(
                "crypto_com has_more=true requires a non-empty next_cursor"
            )
        next_params = dict(params)
        next_params["cursor"] = cursor
        return PageResult(tuple(rows), next_params, tuple(contract_rows))


ADAPTER_TYPES = {
    "kalshi": KalshiDiscoveryAdapter,
    "gemini_predictions": GeminiDiscoveryAdapter,
    "polymarket_us": PolymarketUSDiscoveryAdapter,
    "crypto_com_predictions": CryptoComDiscoveryAdapter,
}


def build_public_discovery_adapters(catalog: Mapping[str, Any]) -> list[DiscoveryAdapter]:
    """Build adapters in catalog order and reject silent public-source omissions."""
    venues = catalog.get("event_venue_candidates")
    if not isinstance(venues, list):
        raise CensusAdapterError("catalog.event_venue_candidates must be a list")
    public_ids = [
        item.get("candidate_id")
        for item in venues
        if isinstance(item, Mapping) and item.get("public_discovery") == "available"
    ]
    missing = [candidate_id for candidate_id in public_ids if candidate_id not in ADAPTER_TYPES]
    extra = sorted(set(ADAPTER_TYPES) - set(public_ids))
    if missing:
        raise CensusAdapterError(
            f"Public discovery candidates are missing adapters: {missing}"
        )
    if extra:
        raise CensusAdapterError(
            f"Adapters exist for candidates not marked public in catalog: {extra}"
        )
    return [ADAPTER_TYPES[candidate_id]() for candidate_id in public_ids]


def _row(venue_id: str, obs: ObservationContext, **values: Any) -> dict[str, Any]:
    return _fixed_row(
        DISCOVERY_COLUMNS,
        DISCOVERY_SCHEMA_VERSION,
        venue_id,
        obs,
        values,
        row_kind="discovery",
    )


def _contract_row(
    venue_id: str,
    obs: ObservationContext,
    **values: Any,
) -> dict[str, Any]:
    return _fixed_row(
        CONTRACT_SNAPSHOT_COLUMNS,
        CONTRACT_SNAPSHOT_SCHEMA_VERSION,
        venue_id,
        obs,
        values,
        row_kind="contract snapshot",
    )


def _fixed_row(
    columns: tuple[str, ...],
    schema_version: str,
    venue_id: str,
    obs: ObservationContext,
    values: Mapping[str, Any],
    *,
    row_kind: str,
) -> dict[str, Any]:
    row = {column: "" for column in columns}
    row.update(
        {
            "schema_version": schema_version,
            "venue_id": venue_id,
            "raw_source": obs.raw_source,
            "raw_session_id": obs.raw_session_id,
            "raw_request_id": obs.raw_request_id,
            "local_request_start_utc": obs.request_started_at_utc,
            "local_request_start_monotonic_ns": obs.request_started_monotonic_ns,
            "local_receive_utc": obs.received_at_utc,
            "local_receive_monotonic_ns": obs.received_monotonic_ns,
        }
    )
    for key, value in values.items():
        if key not in row:
            raise CensusAdapterError(f"Unknown {row_kind} column {key!r}")
        if value is not None:
            row[key] = value
    return row


def _amount_value(value: Any, location: str) -> Any:
    """Preserve a source amount object's value without inventing conversion."""
    if value in (None, ""):
        return None
    if not isinstance(value, Mapping):
        raise CensusAdapterError(f"{location} must be an object when present")
    return value.get("value")


def _list_field(payload: Mapping[str, Any], key: str, venue: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise CensusAdapterError(f"{venue} response field {key!r} must be a list")
    return value


def _mapping_item(value: Any, venue: str, index: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CensusAdapterError(f"{venue} item {index} must be an object")
    return value


def _required_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise CensusAdapterError(f"{location} must be non-empty text")
    return value


def _positive_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CensusAdapterError(f"{location} must be a positive integer")
    return value


def _nonnegative_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CensusAdapterError(f"{location} must be a non-negative integer")
    return value


def _polymarket_status(item: Mapping[str, Any]) -> str:
    if item.get("archived") is True:
        return "archived"
    if item.get("closed") is True:
        return "closed"
    if item.get("active") is True:
        return "active"
    return "inactive_or_unknown"
