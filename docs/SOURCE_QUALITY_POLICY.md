# Source Quality Policy

## Principle

Raw data may be preserved for engineering investigation even when it is not safe for model or trading decisions. Decision use is blocked by default and becomes eligible only when every required source is healthy under an accepted, tested policy.

The machine-readable policy is stored in `configs/source_registry.json` under `read_only_source_quality.v1`.

## Fail-closed states

| State | Trigger | Current collection behavior | Decision behavior | Current enforcement |
|---|---|---|---|---|
| `stale_data` | Observation exceeds an approved maximum age, or no approved threshold exists | Archive-only may continue | Block | Defined, not implemented |
| `clock_error` | UTC or monotonic timing is invalid, local clock health is unknown, or cross-source uncertainty exceeds an approved bound | Stop | Block | Defined, not implemented as a complete clock-health gate |
| `incomplete_response` | Required container, field, page, level, rule, index input, or settlement input is missing or inconsistent | Stop | Block | Partially implemented through endpoint and artifact validation |
| `schema_drift` | Name, type, units, container, transport, or interpretation changes | Stop after raw preservation | Block | Partially implemented for current REST structures and registry contracts |
| `source_unavailable` | Network, HTTP, WebSocket, raw persistence, authorization, or entitlement failure | Stop or fail the affected source | Block | Implemented for current public REST and required persistence paths only |
| `settlement_authority_unresolved` | Any required settlement authority or procedure remains unconfirmed | Archive-only may continue | Block | Defined; modeling does not exist |

## Public REST staleness

The REST order-book response has no documented source observation timestamp. A later staleness gate may therefore use local monotonic receive age for a single process, but the threshold must be declared and tested before decision use.

Market `updated_time` is metadata time, not order-book freshness.

## CF Benchmarks WebSocket staleness

Kalshi documents roughly one update per second for the authenticated `cfbenchmarks_value` channel and states that duplicate or out-of-order upstream source timestamps are ignored. This is descriptive evidence, not an approved project threshold.

Before any later collector can use that channel, the project must define and test:

- maximum allowed time since the upstream source timestamp;
- maximum allowed local receive age;
- behavior when `received_at` and upstream `data.time` disagree;
- reconnect and continuity requirements;
- sequence-gap and missed-tick behavior;
- whether the quarter-hour average has all required observations;
- shutdown behavior before and during the settlement window.

No authenticated collector is authorized in the current phase.

## Clock health

UTC time supports comparison across systems. Monotonic time supports local elapsed duration and ordering. A valid collector needs both, but monotonic values cannot be compared across restarts or machines.

A future synchronized-source checkpoint must define:

- acceptable system-clock offset;
- acceptable clock uncertainty;
- detection method;
- behavior after a backward or discontinuous wall-clock change;
- restart requirements;
- source-to-local and source-to-source alignment rules.

Until then, cross-source decisions are blocked.

## Incomplete response and schema drift

The existing REST client preserves the raw response first, then validates the structures used by the current collectors. Unknown or changed structures are not coerced into the old schema.

The source registry separately validates documented transport identities. An HTTPS REST source must use `GET`; a WebSocket source must use `SUBSCRIBE` and a `wss://` endpoint. This prevents a source from silently changing transport or access mode in the registry.

A versioned parser, registry update, and tests are required before reusing changed fields.

## Settlement-specific incompleteness

The representative KXBTC15M rules establish the two 60-second windows, `>=` comparison, and tie outcome. Decision use remains blocked because rounding order, corrections, missing observations, outages, fallback behavior, and exact settlement-engine equivalence are unresolved.

A source may be structurally valid while settlement authority is still incomplete.

## No silent fallback

No alternate exchange, public spot price, cached value, inferred field, or previous tick may replace a failed settlement source automatically. A fallback is allowed only when the official contract rules identify it and the project records and tests it.

## Scope boundary

This policy does not implement WebSocket collection, sequence checks, external-feed synchronization, model uncertainty, paper execution, or trading risk. It defines the blocking states that those later systems must enforce.
