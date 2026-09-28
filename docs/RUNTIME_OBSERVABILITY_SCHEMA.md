# Runtime Observability Event Schema

## Purpose

The runtime event log records what a collector did while it was running. It is an operational audit stream, not a copy of the source API payload.

The project now keeps four responsibilities separate:

- Raw JSONL preserves the exact public API exchange.
- Runtime-event JSONL records collector and validation behavior.
- Derived CSV stores normalized quote observations with raw-request lineage.
- The run manifest identifies the run and hashes every declared artifact.

This separation prevents terminal messages, operational state, and source payloads from being mixed into one ambiguous file.

## Storage layout

```text
logs/runtime/YYYY/MM/DD/
└── <run_id>.jsonl
```

One current collector run writes one runtime-event file. Runtime output remains ignored by Git.

## Schema version

Current event envelope: `runtime_event.v1`

Every line is one JSON object with these fields:

- `schema_version`: Runtime-event envelope version.
- `event_id`: Unique event identifier.
- `sequence`: One-based sequence number within the run.
- `event_name`: Stable lowercase dot-separated event name.
- `severity`: `info`, `warning`, `error`, or `critical`.
- `occurred_at_utc`: Local UTC wall-clock timestamp.
- `occurred_monotonic_ns`: Local monotonic clock reading.
- `run_id`: Manifest run identifier.
- `collector`: Collector name.
- `message`: Short controlled human-readable description.
- `correlation`: Raw-record identity or `null`.
- `context`: Sanitized structured event details.
- `error`: Structured error type and message or `null`.

## Ordering and clocks

`sequence` is the authoritative local event order for one run. UTC time supports comparison with other systems. Monotonic time supports local ordering and elapsed-time analysis without relying on wall-clock corrections.

Monotonic values must not be compared across machines, operating-system restarts, or unrelated runs. Within one event file, monotonic readings must not move backward.

## Severity policy

- `info`: Expected lifecycle or successful request activity.
- `warning`: A recoverable or bounded failure where the collector may continue.
- `error`: A request or endpoint condition that invalidates the current operation.
- `critical`: A terminal run failure or required persistence failure.

Severity does not estimate trading risk or profitability. It describes operational impact only.

## Current stable event names

### Collector lifecycle

- `collector.started`: The collector has a durable running manifest and runtime logging has begun.
- `collector.iteration.failed`: One bounded polling iteration failed, but the recorder will continue.
- `collector.completed`: The collector workload reached its normal end and is ready for manifest finalization.
- `collector.failed`: The run terminated through an exception.

`collector.completed` does not supersede the manifest. A run is fully complete only when its manifest reaches `status: completed`. If manifest finalization fails after the workload event, the manifest remains `running` or is finalized as `failed`.

### Public API boundary

- `api.request.succeeded`: The response was archived and passed transport, HTTP, JSON, and top-level object checks.
- `api.request.failed`: The attempted request was archived but failed transport, HTTP, JSON, or top-level validation.
- `api.raw.persistence.failed`: The required raw exchange record could not be written.

### Endpoint validation

- `endpoint.validation.failed`: A top-level JSON object was safely archived, but a documented endpoint container or level shape was invalid.

Current validation codes include market-list, pagination cursor, market-object, order-book object, side-list, level-shape, fixed-point-string, numeric-string, and finite-numeric checks. These are structural checks only. They do not assign undocumented settlement meaning to fields.

## Raw-record correlation

When an event refers to a successfully persisted raw exchange, `correlation` contains exactly:

```json
{
  "raw_source": "kalshi_public_rest",
  "raw_session_id": "...",
  "raw_request_id": "..."
}
```

This is the same logical key carried by derived order-book CSV rows. No absolute raw-file path or line number is required.

Events about failed raw persistence use `correlation: null` because no durable raw record exists. The attempted request identifier may appear in sanitized event context for diagnosis.

## Redaction and content limits

Credential-like context keys are replaced with `[REDACTED]`. Runtime events must be strict JSON; non-finite numbers such as `NaN` and infinity are rejected. Runtime events must not contain response bodies, request headers, API keys, private keys, signatures, or account state.

The current project is public and unauthenticated, but the no-secret event contract is established before any later credentialed phase is considered.

## Fail-closed rule

Runtime-event persistence is required for current command-line collectors. If an event cannot be appended and fsynced, the collector stops and the run manifest is finalized as failed when possible.

An event-log failure cannot reliably log itself. The exception and failed or incomplete manifest are therefore the remaining evidence.

## Manifest relationship

Current collectors create `collection_run_manifest.v2` manifests. A completed v2 manifest must reference exactly one `runtime_event_log` artifact whose records:

- Use `runtime_event.v1`.
- Have contiguous sequence numbers beginning at 1.
- Use unique event IDs.
- Match the manifest run ID and collector.
- Contain `collector.started` and `collector.completed`.
- Contain no `collector.failed` or `critical` event.
- Correlate every persisted raw request to exactly one `api.request.succeeded` or `api.request.failed` event whose success/failure state matches the raw record.
- Resolve every non-null event correlation to a raw record declared by the run.

The manifest stores the event file's SHA-256, size, count, error-event count, observed event names, severity counts, run IDs, and collectors.

The offline validator continues to support historical `collection_run_manifest.v1` files, which have no runtime-event requirement.

## Current limitations

- There is no external log aggregation service, metrics backend, dashboard, or alerting system.
- There is no retention or rotation policy beyond one file per run.
- Exception text is operational diagnostic data and must continue to be reviewed before any authenticated phase.
- Runtime events do not prove source freshness, official settlement authority, market-data completeness, executable fills, or profitability.
