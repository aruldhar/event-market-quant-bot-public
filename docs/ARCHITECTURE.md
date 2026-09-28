# Architecture

## Current Phase 1 flow

```text
Kalshi public REST API
        ↓
HTTP request/response boundary
        ↓
Append-only raw JSONL archive
(request context + response body + clocks + transport/HTTP/JSON errors)
        ↓ only after successful raw persistence
Structured API runtime event
(success, request failure, or raw-persistence failure)
        ↓
Endpoint-specific structural validation
        ↓ on invalid structure
Correlated endpoint.validation.failed runtime event
        ↓ on valid structure
Market discovery / order-book extraction
        ↓
Best bid and implied ask calculation
        ↓
Terminal output and derived CSV snapshots
```

The raw archive is the source-payload audit record. Runtime events explain collector behavior. Derived CSV is a normalized convenience product. These three artifacts are intentionally separate and are tied together by the run manifest and logical identifiers.

## Raw logging boundary

`KalshiPublicClient._get_with_lineage` is the single raw logging boundary for all current REST endpoints. Centralizing the boundary prevents the scanner and order-book recorder from applying inconsistent persistence rules.

The boundary follows this order:

1. Capture UTC and monotonic request-start clocks.
2. Attempt the HTTP request.
3. Capture UTC and monotonic receive clocks immediately after response or failure.
4. Decode JSON without applying endpoint-specific transformation.
5. Persist the raw exchange record.
6. Emit a structured API success or failure event linked to the raw request when one exists.
7. Raise any transport, HTTP, JSON, or top-level shape error.
8. Return the decoded object and immutable raw-record identity for endpoint validation.

A raw-write error stops the path at step 5. A structured `api.raw.persistence.failed` event is attempted without claiming that a durable raw record exists.

## Endpoint validation boundary

Endpoint methods validate only structural expectations currently required by the collectors:

- `/markets` returns a market list and a text-or-null cursor.
- Each market-list item is an object.
- `/markets/{ticker}` returns a market object.
- `/markets/{ticker}/orderbook` returns an `orderbook_fp` object.
- Present YES and NO sides are lists.
- Each order-book level is a two-value array of fixed-point numeric strings.

If one of these checks fails, the already archived raw record remains unchanged. The client emits `endpoint.validation.failed` with a stable validation code and the exact raw lineage key, then raises `EndpointValidationError`. The bounded order-book loop treats that condition as terminal rather than repeatedly transforming an unknown schema.

These checks do not define official settlement fields, source freshness, price authority, or economic meaning beyond the existing quote-conversion baseline.

## Structured runtime events

Each current CLI collector writes one append-only file under:

```text
logs/runtime/YYYY/MM/DD/<run_id>.jsonl
```

Events include a run-local sequence, UTC and monotonic clocks, stable name, severity, collector, run ID, sanitized context, optional error details, and optional raw-request correlation.

The current severity policy is:

- `info`: expected lifecycle and successful requests
- `warning`: bounded request failures where the recorder may continue
- `error`: invalid request or endpoint conditions
- `critical`: terminal collector or required persistence failures

Runtime-event persistence is required. If it fails, the collector stops. See `RUNTIME_OBSERVABILITY_SCHEMA.md` for the full contract.

## Collection run receipt

Each CLI collector creates a separate run manifest before network work begins:

```text
Collector start
        ↓
Atomic `running` manifest v2
(arguments + code/environment + source session)
        ↓
collector.started runtime event
        ↓
Raw API records + runtime events + optional derived CSV
        ↓
collector.completed or collector.failed event
        ↓
Artifact inspection
(hashes + sizes + counts + baseline schemas + event relationship)
        ↓
Atomic `completed` or `failed` manifest
        ↓
Offline `validate_run_manifest.py` recomputation
```

The manifest identifies which exact artifact bytes belonged to the run. A process crash may leave a valid raw prefix, a valid runtime-event prefix, and a `running` manifest; that run is incomplete until explicitly investigated.

Current collectors create `collection_run_manifest.v2`. The validator remains backward compatible with historical v1 manifests.

`completed` describes successful run finalization, not perfect network service. Individual recoverable request failures remain visible in raw records, runtime events, and result counts.

## Raw-to-derived lineage

Every current order-book CSV row carries:

```text
run_id
raw_source
raw_session_id
raw_request_id
```

The raw tuple identifies the source exchange. The manifest identifies the run and artifact files. Runtime request and endpoint events use the same raw tuple when they refer to a persisted exchange.

The offline validator reconciles successful derivable order-book raw records and CSV rows in both directions.

## Planned venue-independent architecture

```text
External and venue feeds
        ↓
Venue adapters and source validation
        ↓
Synchronized raw event log + manifests + runtime observability
        ↓
Feature engine
        ↓
Probability / fair-value models
        ↓
Cost and uncertainty adjustment
        ↓
Risk engine
        ↓
Paper broker → Demo broker → Production broker
        ↓
Audit log and performance reports
```

## Planned modules

```text
src/
├── venues/       Platform-specific API adapters
├── data/         Collection, synchronization, manifests, and storage
├── features/     Market and settlement-aware feature calculations
├── models/       Probability models and calibration
├── strategies/   Decision rules independent of account execution
├── execution/    Paper, demo, and eventual live order handling
├── risk/         Exposure, loss, stale-feed, and kill-switch logic
└── analysis/     Backtests, diagnostics, and reports
```

The current modules remain intentionally small. They establish durable contracts before the repository is reorganized into the planned venue-independent layout.

## Design constraints

- Strategies should consume common normalized data objects.
- Venue-specific details remain inside venue adapters.
- Raw data is append-only and treated as immutable after collection.
- Operational events remain separate from source payloads.
- Source timestamps and local receive timestamps must remain distinguishable.
- Monotonic clocks are used for local elapsed duration and ordering, not cross-run chronology.
- Heavy training and analysis remain outside the live path.
- Collection and eventual trading must fail closed when required audit state, data, clocks, or account state are uncertain.
- Request headers must not be archived; credential-like context values must be redacted; response bodies must not enter runtime events.

## Source registry and authority gate

Before a source can enter a model or trading decision path, it must exist in `configs/source_registry.json` and pass `validate_source_registry.py`.

```text
Official source evidence
        ↓
Versioned source registry
(identity + owner + transport + auth + timestamps + authority + evidence)
        ↓
Offline registry validation
        ↓
Fail-closed source-quality state
        ↓ only when every required state is healthy
Collector / synchronized feature path
```

The registry is a control-plane contract, not a network client. It performs no live health checks and grants no authorization.

Endpoint identities are separate even when they share a base URL. The market list, single-market metadata, REST order book, written rules, authenticated CF Benchmarks delivery channel, and numerical settlement index have different trust roles.

Transport validation currently supports:

- HTTPS REST `GET` sources;
- HTTPS documents;
- WSS `SUBSCRIBE` sources.

The registry rejects a WSS source with an HTTPS URL or a non-subscription method, preventing access-mode drift from being hidden in configuration.

Current authority boundary:

- Kalshi public REST order books are execution-market data, not settlement truth.
- Kalshi single-market `rules_primary` and `rules_secondary` are written contract evidence.
- CF Benchmarks BRTI is the numerical index authority.
- Kalshi's authenticated `cfbenchmarks_value` WebSocket channel is a documented delivery path, not a new authority.
- Auxiliary BTC feeds may become model inputs but cannot become settlement authority through convenience or correlation.

## Settlement-rule boundary

The representative public response for `KXBTC15M-26AUG040000-00` established the following rule shape:

```text
simple_average(BRTI, 60 seconds before close)
    >=
simple_average(BRTI, 60 seconds before open)
```

An exact tie therefore resolves Yes. The observed `close_time` matched the comparison boundary, while `expiration_time` was one week later. Code must not derive the comparison window from `expiration_time`.

Kalshi's documented `cfbenchmarks_value` channel narrows the final-minute tick window to start-exclusive and close-inclusive. No authenticated collector exists, and the documented average is not yet accepted as an exact settlement-engine replica because rounding, corrections, outages, missing observations, and fallback behavior remain unresolved.

## Future authenticated-stream boundary

Any later WebSocket collector requires a separate accepted design covering:

1. explicit authorization and secure local credential storage;
2. raw message preservation before transformation;
3. source and local timestamp handling;
4. subscription sequence continuity;
5. reconnect, duplicate, and out-of-order behavior;
6. staleness and clock-health gates;
7. final-minute completeness checks;
8. fail-closed shutdown behavior.

No such collector is part of the current checkpoint.

Current flow remains read-only. Unresolved settlement authority, stale data, clock uncertainty, incomplete responses, schema drift, or source unavailability must block model and execution decisions even when raw archival can safely continue.


## Git checkpoint-closeout control plane

Repository closeout is intentionally separate from market-data runtime behavior.

```text
Working tree
    ↓
Committed closeout policy + repository identity checks
    ↓
Exact changed-file approval
    ↓
Validators + full tests
    ↓
Exact selective staging + diff/secret checks
    ↓
User-supplied checkpoint commit message
    ↓
Checkpoint commit
    ↓
Generated LAST_CHECKPOINT_CLOSEOUT receipt
    ↓
Deterministic receipt commit
    ↓
Single explicit push approval
    ↓
Remote synchronization + clean-worktree verification
```

The closeout helper reads its policy from committed `HEAD`, not from an uncommitted policy file. It also refuses to certify changes to its own engine, wrapper, policy, or tests. This prevents a normal feature checkpoint from silently weakening the verifier that certifies it.

The generated receipt solves the documentation-hash timing problem: the substantive checkpoint commit is created first, then a documentation-only child commit records that exact checkpoint SHA. The receipt commit does not self-reference its own SHA.

This tooling is a development control plane only. It does not sit in the market-data collection or future trading decision path.
