# KXBTCD Predexon Free Sub-Cent Backfill Design — Checkpoint 21N-P1

## Purpose

Materialize the free full-book snapshot evidence needed to determine which
states of the already-owned 2026-07-10 Predexon paid-tick shard are safe for
segment-verified historical replay.

This is a source/data-engineering checkpoint only.

It does **not**:

- inspect settlement outcomes;
- fit or refit Candidate E;
- calculate Candidate-E probabilities;
- select an entry threshold;
- calculate P&L;
- simulate orders;
- call Predexon tick quote/purchase endpoints;
- spend paid Predexon credits.

## Frozen evidence boundary

The paid shard is already owned and contains:

- 5,644,964 KXBTCD tick rows;
- 623 strike contracts;
- four independent hourly events.

The 623 strike contracts are not 623 independent statistical observations.

## Exact request scope

Endpoint:

`GET /v2/kalshi/orderbooks-subcent`

For each owned ticker:

- `ticker`: exact paid-shard ticker;
- `start_time`: minimum paid-delta timestamp for that ticker;
- `end_time`: maximum paid-delta timestamp for that ticker;
- `limit`: 2000;
- `sources`: `spine`.

The 2000-page-size behavior is bound to already-preserved successful sub-cent
evidence, not inferred from the standard-cent orderbook endpoint.

## Pagination

The first request omits `pagination_key`.

If `has_more=true`, the returned `pagination_key` must be non-empty and is sent
back verbatim on the next request. The collector never decodes, constructs,
edits, or extrapolates the cursor.

Completion requires `has_more=false` and `pagination_key=null`.

The collector fails closed on:

- malformed response JSON;
- wrong ticker;
- nonchronological timestamps within or across pages;
- pagination count mismatch;
- changed returned page limit;
- `has_more=true` without a cursor;
- terminal page with a non-null cursor;
- repeated cursor;
- non-200 response after raw persistence;
- missing API credential;
- altered frozen paid-shard ticker/row count.

## Raw preservation and resumability

Every HTTP response body is written to a ticker-specific append-only JSONL raw
file and flushed/fsynced **before** semantic parsing.

The raw envelope stores request scope but never the API key.

On restart, every prior page is revalidated from disk. A ticker is skipped only
when the existing file ends in a valid terminal page. Otherwise collection
continues from the last returned opaque cursor.

## Rate limiting

The collector spaces requests by at least 1.05 seconds. HTTP 429 responses use
bounded backoff and fail closed if retries are exhausted.

## Evidence role after collection

Successful collection does not establish profitability or even replay validity.
It only provides the snapshot evidence required for the next offline step:
reconcile paid deltas against adjacent snapshots and construct a verified-state
mask across the owned strike ladder.

Only states inside verified replay segments may later enter exploratory
execution/realizability research.

## Safety

Current authorization remains read-only.

- orders: prohibited;
- paper broker: prohibited;
- demo execution: prohibited;
- real-money execution: prohibited;
- Predexon paid purchase calls: prohibited in this collector;
- settlement outcomes: not accessed;
- C1/C2/C3/reserve: untouched.
