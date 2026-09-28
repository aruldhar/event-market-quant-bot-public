# Kalshi Historical Endpoint Validation

## Status

**Checkpoint-08 validation design. Live evidence not yet accepted.**

This document defines the first implementation slice of Checkpoint 08 — Sports Historical Data Validation and Calibration. It validates Kalshi's public historical-data routing before the project builds a reusable Sports historical collector.

The command is intentionally read-only:

- no authentication;
- no API/private keys;
- no orders or cancellations;
- no paper/demo/production execution;
- no profitability claim;
- no final-outcome analysis.

Raw historical market payloads may contain final `result` fields because they are source-native terminal objects. The validation logic does not read those fields. The later staleness pilot must remain outcome-blind when choosing the maximum quote-age rule.

## Why this validation exists

Kalshi partitions older exchange data into a historical tier. The cutoff moves over time. A historical collector must therefore route based on a freshly captured cutoff rather than hard-coding a date or assuming that one endpoint contains all records.

The first validation run must establish four things before collection logic is expanded:

1. the cutoff response is reachable and parseable;
2. a Sports market settling before the captured cutoff can be recovered through historical market endpoints while its Event/Series identity remains available through normal event metadata;
3. historical 1-minute candlesticks and historical trades return structurally usable public data;
4. a current Sports market in REST status `active` with positive 24-hour volume can return a non-empty live candlestick response, including at least one real candle with both YES bid and YES ask close values, with synthetic-candle insertion explicitly disabled.

## Official endpoint identities under validation

Base URL:

```text
https://external-api.kalshi.com/trade-api/v2
```

Public GET endpoints:

```text
/historical/cutoff
/historical/markets
/historical/markets/{ticker}
/historical/markets/{ticker}/candlesticks
/historical/trades
/events/{event_ticker}
/events
/series/{series_ticker}/markets/{ticker}/candlesticks
```

Official documentation reviewed on 2026-08-08 local Pacific / 2026-08-09 UTC:

- https://docs.kalshi.com/getting_started/historical_data
- https://docs.kalshi.com/api-reference/historical/get-historical-cutoff-timestamps
- https://docs.kalshi.com/api-reference/historical/get-historical-markets
- https://docs.kalshi.com/api-reference/historical/get-historical-market
- https://docs.kalshi.com/api-reference/historical/get-historical-market-candlesticks
- https://docs.kalshi.com/api-reference/historical/get-historical-trades
- https://docs.kalshi.com/api-reference/events/get-events
- https://docs.kalshi.com/api-reference/events/get-event
- https://docs.kalshi.com/api-reference/market/get-market-candlesticks

These are documentation facts only until a project run archives and validates representative responses.

### Historical-trade documentation inconsistency

The general Historical Data guide, the dedicated `GET /historical/trades` reference, and the March 2026 changelog direct trades older than `trades_created_ts` to `/historical/trades`. The dedicated cutoff-reference prose still describes that timestamp in terms of historical user fills. Checkpoint 08 therefore treats `/historical/trades` as the documented public trade endpoint but requires live raw-first validation before accepting that routing in the project registry.

## Routing contract

### Markets and candlesticks

`market_settled_ts` from `GET /historical/cutoff` is the routing boundary.

A candidate used as historical evidence must satisfy:

```text
market.settlement_ts < captured market_settled_ts
```

The probe fails closed if `/historical/markets` returns a candidate at or after the captured cutoff.

### Trades

`trades_created_ts` is recorded separately. The validation command uses `GET /historical/trades` only for the selected historical ticker. No trade is silently substituted from a live endpoint.

### Event and Series identity

Kalshi documents that Event and Series metadata remain available on their original endpoints even when old Markets have moved to historical storage.

The probe therefore links:

```text
historical market.event_ticker
    -> GET /events/{event_ticker}
    -> event.category == Sports
    -> event.series_ticker
```

The selected market must keep the same `event_ticker` between the historical list and historical single-market response.

## Candlestick schema behavior

The current official documentation shows different field-name families.

Historical examples use:

```text
yes_bid.close
yes_ask.close
price.close
price.mean
price.previous
volume
open_interest
```

Live examples use:

```text
yes_bid.close_dollars
yes_ask.close_dollars
price.close_dollars
price.mean_dollars
price.previous_dollars
volume_fp
open_interest_fp
```

The validation layer keeps these source-native forms separate. It does not silently rename historical fields to live names or vice versa.

For each response it records:

- candle count;
- number of candles with both bid/ask close values;
- missing bid-close count;
- missing ask-close count;
- crossed bid/ask-close count;
- first and last `end_period_ts`;
- observed field-name sets.

Missing/crossed quotes are measured, not imputed. They are not yet converted into a staleness rule.

The official endpoint documentation does not promise a response sort order. The validation report therefore records whether `end_period_ts` values arrive ascending, descending, mixed, or duplicated rather than silently assuming ascending order. The later collector must define a deterministic ordering rule before anchor extraction.

## Synthetic live candles

The live candlestick endpoint documents `include_latest_before_start`. When enabled, it can prepend a synthetic continuity candle whose OHLC values are null.

Checkpoint 08's predeclared calibration experiment requires the latest **real** one-minute candlestick ending at or before each anchor. The validation command therefore sends:

```text
include_latest_before_start=false
```

The future Sports collector must keep synthetic rows out of anchor selection.

## Probe windows

This first command is a schema/routing probe, not the staleness pilot.

For the selected historical Sports market it requests a bounded one-minute-candle window covering up to the final six hours before `close_time`.

For the selected live Sports market it requests up to the most recent 24 hours available before the current time/market close. The selector considers only currently open `active` Sports markets with positive `volume_24h_fp` and chooses the highest-volume candidate inside the bounded search. The live validation fails closed if that candidate still returns zero candles or if none of its returned candles carries both YES bid and YES ask close values.

The 24-hour live window aligns the schema probe with the source's 24-hour activity field. It is chosen only to obtain a representative non-empty endpoint response; it is **not** a staleness threshold, does not change the predeclared 7d/3d/1d experiment anchors, and is not used in the later calibration analysis.

## Raw-first and lineage requirements

The command reuses `PublicCensusHttpClient`, which already:

- begins a raw request record before the network call;
- captures local UTC and monotonic start/receive timing;
- writes the original response body before transformation;
- records source timestamp-like fields;
- preserves HTTP/JSON/transport errors;
- archives every HTTP-429 attempt before bounded retry;
- fails closed if required raw persistence fails.

Each accepted validation-report row stores:

```text
raw_source
raw_session_id
raw_request_id
request_started_at_utc
received_at_utc
method
path
```

Before the run is marked complete, the command rereads the raw JSONL archive and proves that each accepted report row maps to one exact HTTP-200 raw exchange with matching request path and timestamps.

The normal run manifest then hashes/counts the raw, derived CSV, and runtime-event artifacts.

## What this command does not validate yet

This first slice does not yet establish:

- 7d/3d/1d Sports historical coverage;
- the quote-age distribution;
- a maximum staleness threshold;
- final eligible-event sample size;
- calibration quality;
- a structural signal;
- executable economics;
- fees, fills, latency, or profitability.

Those remain later Checkpoint-08 steps and must occur in the predeclared order.

## Acceptance sequence

Run the deterministic test suite first. If it passes, run the live public validation command.

Only after the live output and generated manifest/raw report are inspected should this project:

1. register/mark the historical source identities in `configs/source_registry.json` using the observed evidence;
2. define the versioned Sports historical-data schema;
3. build the full raw-first historical collector;
4. run the outcome-blind staleness pilot.

## Accepted Checkpoint-08 endpoint evidence — 2026-08-09 UTC

After the initial live-candle probe exposed an empty six-hour sample, the validator was tightened to require a currently open active Sports market with positive 24-hour volume, use a matching 24-hour live probe, and fail closed on an empty live candle set or on a set with no complete YES bid/ask close pair.

The corrected run completed successfully with:

```text
Historical Sports market: KXITFMATCH-26JUN08LEGBRA-LEG
Historical series: KXITFMATCH
Captured market cutoff: 2026-06-09T00:00:00Z
Historical 1m candles: 59
Historical complete bid/ask close pairs: 59
Historical trades: 47
Live Sports market: KXWC-30-MEX
Live series: KXWC
Live 1m candles: 7
Live complete bid/ask close pairs: 7
Raw records: 10
Raw errors: 0
Authentication used: no
Final YES/NO outcomes inspected by validation logic: no
Orders placed: 0
```

Canonical local artifacts reported by the run:

```text
logs/kalshi_historical_endpoint_validation_20260809T051848Z.csv
data/manifests/2026/08/09/validate_kalshi_historical_endpoints_20260809T051848822590Z_d7e4d237.json
```

After that run, the complete repository test suite passed:

```text
130 passed, 5 subtests passed in 5.08s
```

This evidence validates the public endpoint path and the current representative historical/live candlestick schema behavior. It does not validate population-wide Sports coverage or any staleness/calibration conclusion.
