# Raw Kalshi REST Archive Schema

## Purpose

The raw archive preserves each Kalshi public REST exchange before any market filtering, order-book extraction, quote calculation, or CSV transformation. It is the audit source from which later normalized datasets must be reproducible.

## Storage layout

```text
data/raw/kalshi_rest/YYYY/MM/DD/
└── kalshi_public_rest_<UTC session time>_<session id>.jsonl
```

Each client run has one session ID. Every line is one complete JSON object representing one attempted HTTP request. JSON Lines was selected because it supports append-only writes, incremental reading, and recovery of all complete records if a process stops mid-run.

## Schema version

Current envelope version: `raw_http_exchange.v1`

### Top-level fields

- `schema_version`: Version of the outer archive envelope.
- `source`: Stable source identifier, currently `kalshi_public_rest`.
- `session_id`: Groups records created by one client instance.
- `request`: Request identity, endpoint, parameters, and start clocks.
- `timing`: Local receive clocks and monotonic elapsed duration.
- `response`: HTTP metadata and original body text, or `null` for a transport failure.
- `source_timestamps`: An index of timestamp-like fields copied from the decoded JSON payload.
- `error`: Structured collection error details, or `null` for a valid response.

### Request fields

- `request_id`: Unique identifier for one attempted request.
- `method`: HTTP method.
- `base_url`: Configured API base URL.
- `path`: Endpoint path before query-string expansion.
- `params`: Query parameters sent to the endpoint, with credential-like names redacted.
- `started_at_utc`: Local UTC wall-clock time immediately before the request.
- `started_monotonic_ns`: Local monotonic clock reading immediately before the request.

### Timing fields

- `received_at_utc`: Local UTC wall-clock time immediately after a response or transport failure.
- `received_monotonic_ns`: Local monotonic clock reading at receipt or failure.
- `elapsed_monotonic_ns`: `received_monotonic_ns - started_monotonic_ns`.

Wall-clock timestamps allow comparison with source timestamps and other systems. Monotonic timestamps are used for local duration because they cannot move backward when the system clock is corrected. Monotonic values are meaningful only within the same operating-system boot and should not be compared across machines or restarts.

### Response fields

- `status_code`: HTTP status code.
- `reason`: HTTP reason phrase.
- `url`: Final response URL with credential-like query parameters redacted.
- `headers`: Selected operational response headers only, such as content type, source date, request ID, cache metadata, and rate-limit metadata.
- `body_text`: Original decoded response body text. Parsing this field reconstructs the source JSON semantics.
- `body_size_bytes`: Size of the received response body in bytes.
- `body_sha256`: SHA-256 digest of the exact received response bytes.
- `json_parse_error`: JSON decoder error text, or `null` when decoding succeeded.

The byte digest detects accidental alteration. The current archive stores decoded JSON text rather than a second base64 copy of the bytes to avoid unnecessary size growth. Because Kalshi JSON is expected to be text, this is an appropriate baseline; exact reconstruction of malformed non-text bytes is not yet supported.

### Source timestamp index

`source_timestamps` contains entries such as:

```json
{"json_path":"$.markets[0].close_time","value":"2026-08-03T08:15:00Z"}
```

This is only a search index. Values are copied without normalization or interpretation. It does not identify the official settlement timestamp or assert that any one field is authoritative. The untouched `body_text` remains the source of truth.

### Error stages

- `transport`: No HTTP response was received.
- `http_status`: A non-success HTTP status was returned; the error body is still preserved.
- `json_decode`: The response body could not be decoded as JSON.
- `shape_validation`: The top-level JSON value was not an object.

Endpoint-specific structural validation occurs only after raw preservation. Those higher-level failures are written to the separate `runtime_event.v1` operational stream with exact raw-request correlation; they do not change the immutable raw envelope.

## Required invariants

1. One raw record is attempted for every HTTP request, including failures.
2. Raw files are append-only runtime artifacts and remain ignored by Git.
3. A successful payload is not returned to transformation code until its raw record is persisted.
4. A raw-write failure stops the request path instead of creating an unaudited derived record.
5. Request headers are not archived, credential-like query values are redacted, and only selected operational response headers are retained.
6. Derived CSV files are convenience outputs, not the permanent source of truth.

## Current limitations

- No cross-process file locking is implemented; each client instance writes to its own session file.
- No raw-data retention, compression, or rotation policy is implemented.
- No stale-feed threshold or sequence-gap policy exists for REST polling.
- The source-timestamp index uses name matching and does not replace endpoint-specific schema definitions.
- Endpoint validation currently checks structural containers and order-book level shape, not settlement meaning.
- No external BTC reference feed is synchronized with these records yet.

## Relationship to run manifests

`RawJsonlRecorder.written_paths` exposes only paths that were successfully appended during the current source session. Current CLI collectors use those paths when finalizing `collection_run_manifest.v2`. Historical v1 manifests remain valid. The manifest stores full-file hashes and record counts; it does not alter or replace raw records.

A source session can produce more than one JSONL file if it crosses a UTC date boundary. The run manifest therefore records a list of raw files rather than assuming one file per run.

See `RUN_MANIFEST_SCHEMA.md` for lifecycle and integrity-validation rules and `RUNTIME_OBSERVABILITY_SCHEMA.md` for the separate operational event contract.
