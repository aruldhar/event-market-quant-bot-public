# Derived Order-Book CSV Schema

## Purpose

The derived order-book CSV is a convenient normalized view of selected quote fields. It is not the source of truth. The original API response remains in the raw JSONL archive.

The CSV schema carries explicit lineage so every row can identify the exact raw API record from which it was derived.

## Current schema

Logical version: `orderbook_snapshot.v2`

The version is documented rather than embedded in every row. Version 2 adds four required lineage columns to the prior quote snapshot layout.

## Required columns

| Column | Meaning |
|---|---|
| `run_id` | Unique collection-run manifest identifier. Current collectors create `collection_run_manifest.v2`; historical v1 runs remain valid. |
| `raw_source` | Raw source adapter name, currently `kalshi_public_rest`. |
| `raw_session_id` | Raw recorder session that owns the JSONL record. |
| `raw_request_id` | Exact request identifier stored at `request.request_id` in raw JSONL. |
| `observed_at_utc` | Local UTC wall-clock time captured by the derived recorder for the snapshot iteration. |
| `ticker` | Requested Kalshi market ticker. |
| `yes_bid` | Highest available YES bid in dollars, or blank when unavailable. |
| `yes_ask` | Implied YES ask, calculated as `1.0000 - best NO bid`, or blank. |
| `yes_spread` | `yes_ask - yes_bid`, or blank. |
| `no_bid` | Highest available NO bid in dollars, or blank. |
| `no_ask` | Implied NO ask, calculated as `1.0000 - best YES bid`, or blank. |
| `no_spread` | `no_ask - no_bid`, or blank. |

## Lineage key

The raw record is identified by the tuple:

```text
(raw_source, raw_session_id, raw_request_id)
```

`run_id` identifies the manifest that declares the source session and references the raw and derived artifact files.

Do not use timestamps or row positions as substitutes for this key. Poll intervals can drift, timestamps can collide, and files can be reorganized. Logical identifiers are the portable reference.

## Production rule for one row

A row may be written only after:

1. The HTTP exchange has been persisted to raw JSONL.
2. The top-level response is valid JSON object data.
3. The endpoint-specific payload contains an `orderbook_fp` object.
4. The row receives the immutable raw-record reference returned with that payload.

A raw-write failure prevents the derived row from being produced.

## Reconciliation invariants

For a completed `record_orderbook` run:

1. Every required lineage field is nonempty.
2. Every row's `run_id` equals the manifest `run_id`.
3. Every `(raw_source, raw_session_id)` pair is declared by the manifest.
4. Every lineage key matches exactly one raw record across all raw files in the run.
5. The referenced raw record has no recorded error.
6. The referenced request is a successful GET to `/markets/{ticker}/orderbook`.
7. The response body contains an `orderbook_fp` object.
8. The CSV ticker equals the ticker encoded in the raw request path.
9. No raw record is referenced by more than one derived row.
10. Every successful derivable raw order-book record appears in exactly one derived row.

## Compatibility boundary

CSV files created before `orderbook_snapshot.v2` do not contain lineage columns and therefore cannot pass the current semantic `record_orderbook` validator.

The raw schema remains `raw_http_exchange.v1`, and the derived CSV remains `orderbook_snapshot.v2`. Current collectors now create `collection_run_manifest.v2` because runtime-event artifacts were added; historical v1 lineage manifests remain valid.

## Current limitations

- The validator confirms source identity and baseline endpoint shape, not the economic correctness of quote interpretation.
- It does not independently verify Kalshi settlement rules.
- It does not compare against an external Bitcoin reference price.
- It does not establish freshness beyond the recorded request and receive times.
- It does not model fees, executable depth, latency, partial fills, missed fills, or market impact.
