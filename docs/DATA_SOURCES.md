# Data Sources Register

Every source must be registered before it can influence a model or trade decision. The canonical machine-readable inventory is `configs/source_registry.json`; this document is the human-readable overview.

Validate the registry with:

```powershell
.\.venv\Scripts\python.exe validate_source_registry.py
```

## Registered sources

### `kalshi.public_rest.markets.v1`

- Owner: Kalshi
- Role: execution-market metadata and KXBTC15M discovery
- Endpoint: `GET https://external-api.kalshi.com/trade-api/v2/markets`
- Authentication: none
- Collection: active
- Settlement authority: none
- Raw source name: `kalshi_public_rest`
- Boundary: market metadata timestamps do not prove order-book freshness

### `kalshi.public_rest.market.v1`

- Owner: Kalshi
- Role: single-market metadata and official written-rule container
- Endpoint: `GET https://external-api.kalshi.com/trade-api/v2/markets/{ticker}`
- Authentication: none
- Collection: active
- Settlement role: Kalshi contract-rule authority
- Live evidence: `KXBTC15M-26AUG040000-00` was raw-archived and reviewed
- Important boundary: `close_time` matched the 15-minute comparison boundary, while `expiration_time` was seven days later
- Parser boundary: current code validates only the market-object container, not field-level settlement semantics

### `kalshi.public_rest.orderbook.v1`

- Owner: Kalshi
- Role: execution order book
- Endpoint: `GET https://external-api.kalshi.com/trade-api/v2/markets/{ticker}/orderbook`
- Authentication: none
- Collection: active
- Settlement authority: none
- Source timestamp: no documented observation timestamp in the current response
- Freshness boundary: only local request and receive time are available; no approved decision threshold exists

The authentication inconsistency is resolved for current behavior: Kalshi's narrative guides explicitly say no authentication is required, while generated API-reference examples include headers. Repeated project calls work without credentials. Reopen this conclusion if official documentation or live behavior changes.

### `kalshi.kxbtc15m.market_rules.v1`

- Owner: Kalshi
- Role: KXBTC15M written settlement contract
- Collection: documented through public market surfaces and the active single-market REST collector; no dedicated rule-history collector exists
- Confirmed from live rules:
  - 60-second BRTI average before open
  - 60-second BRTI average before close
  - later average `>=` earlier average resolves Yes
  - an exact tie resolves Yes
  - final value described as rounded to two decimals
- Overall settlement validation: unresolved because rounding order, corrections, missing observations, outages, fallback, and exact settlement-engine equivalence remain incomplete

### `kalshi.cfbenchmarks_value.websocket.v1`

- Owner: Kalshi
- Role: delivery of upstream CF Benchmarks frames and documented rolling/final-minute averages
- Endpoint: `wss://external-api-ws.kalshi.com/trade-api/ws/v2`
- Subscription: channel `cfbenchmarks_value`, selected with `index_ids` such as `BRTI`
- Authentication: signed Kalshi WebSocket handshake
- Collection: documented, not collected
- Documented cadence: roughly one tick per second
- Documented final-minute window: start excluded and quarter-hour close tick included
- Authority boundary: this is a delivery channel, not a replacement for CF Benchmarks as numerical index authority
- Authorization boundary: no API key, private key, or collector is authorized in the current phase

### `cfbenchmarks.brti.v1`

- Owner: CF Benchmarks
- Role: numerical settlement index authority
- Kalshi REST passthrough: `GET /cfbenchmarks/values?id=BRTI`
- Authentication: signed Kalshi request plus account entitlement
- Collection: documented, not collected
- Authorization boundary: the project has no API key or entitlement and must not request secrets in chat

## Representative source-field observation

For `KXBTC15M-26AUG040000-00`:

```text
open_time:       2026-08-04T03:45:00Z
close_time:      2026-08-04T04:00:00Z
expiration_time: 2026-08-11T04:00:00Z
result:          empty while active
settlement_ts:   absent while active
```

This observation prevents `expiration_time` from being silently interpreted as the 15-minute settlement window endpoint.

## Fail-closed policy

All registered sources reference `read_only_source_quality.v1`. It blocks decision use for stale data, clock error, incomplete response, schema drift, source unavailability, and unresolved settlement authority.

See:

- `SOURCE_REGISTRY_SCHEMA.md`
- `SETTLEMENT_VALIDATION.md`
- `SOURCE_QUALITY_POLICY.md`
- `RAW_DATA_SCHEMA.md`
