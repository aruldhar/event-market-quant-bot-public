# Reference Data Design

Status: checkpoint 06 design candidate. This document defines source roles and acceptance requirements only. It does not authorize or implement a new collector.

## Purpose

The project eventually needs synchronized data beyond the Kalshi order book if it is going to test whether short-duration Bitcoin event prices contain a measurable predictive edge.

The central design rule is:

> **Reference data must be classified by role before it is collected. Correlation with the settlement index does not make a feed settlement authority.**

This checkpoint therefore defines the source classes, timing requirements, failure rules, and decision sequence before choosing an external BTC feed or enabling authenticated BRTI delivery.

## Current boundary

Current implementation remains:

- public Kalshi REST only;
- read-only;
- credential-free;
- raw-preserving;
- no external BTC collector;
- no authenticated WebSocket;
- no settlement-label generator;
- no model or paper execution.

The existing source registry already identifies Kalshi contract rules, CF Benchmarks BRTI, and documented authenticated delivery channels. This design does not replace that registry.

## Source classes

### 1. Execution-market source

Purpose: describe the market being priced and eventually traded.

Current example:

- Kalshi market metadata and order book.

Typical data:

- contract identity;
- rules;
- lifecycle times;
- bids/asks;
- available depth;
- market trades when later collected.

This source answers **what the event market is pricing**, not what the underlying Bitcoin settlement index is numerically doing.

### 2. Contract-rule authority

Purpose: define the event's legal/economic resolution rule.

Current authority:

- Kalshi KXBTC15M written rules.

This source controls:

- comparison windows;
- comparison operator;
- tie treatment;
- named resolution source;
- any official fallback procedure if one exists.

No other feed can override it.

### 3. Settlement numerical authority

Purpose: provide the numerical index named by the contract rule.

Current authority:

- CF Benchmarks BRTI.

The provider's methodology defines the underlying real-time index calculation. It is distinct from any one constituent exchange price.

### 4. Official settlement-index delivery channel

Purpose: transport the numerical authority to the project.

Documented options:

- Kalshi `cfbenchmarks_value` WebSocket;
- Kalshi CF Benchmarks REST passthrough;
- direct licensed CF Benchmarks API/WebSocket.

A delivery channel may add transport timestamps, sequence identifiers, or convenience averages. Those additions do not change the underlying authority.

### 5. Auxiliary predictive/reference source

Purpose: provide information that might help predict the authoritative settlement index or market probability before settlement.

Possible future examples:

- one or more public BTC/USD or BTC/USDT exchange feeds;
- an institutional or oracle feed such as Pyth if available and appropriate;
- cross-exchange aggregates;
- futures basis or other market microstructure features in a later expanded scope.

These are **predictive features only** unless an official KXBTC15M rule names them as resolution sources.

### 6. Clock-health source

Purpose: establish whether local timestamps are trustworthy enough for cross-source alignment.

A future synchronized collector needs evidence about:

- local wall-clock offset;
- clock uncertainty;
- monotonic-clock continuity;
- discontinuities or backward wall-clock jumps.

Clock health is a data-quality dependency, not a market predictor.

## Why no external feed is selected yet

Selecting Coinbase, Kraken, Pyth, or another feed immediately would be premature because the project has not yet accepted the operational contract that any candidate must satisfy.

A source should be chosen only after its role, timestamp behavior, raw payload, continuity semantics, access terms, and failure behavior are known.

Price correlation alone is not a sufficient selection criterion.

## Requirements for every future reference collector

### Raw preservation

Every source message or response must be preserved before transformation.

Minimum raw evidence should include, where available:

- source identity;
- subscription/request identity;
- exact payload;
- source timestamp;
- local UTC receive timestamp;
- local monotonic receive timestamp;
- sequence or update identifier;
- transport state and reconnect boundaries;
- parse/validation error without discarding the source payload.

### Timestamp model

Every derived observation must keep separate concepts separate:

- **source event/calculation time** — when the upstream source says the value belongs;
- **relay receive time** — when an intermediary such as Kalshi says it received the value, if provided;
- **local receive UTC** — local wall-clock receipt;
- **local monotonic time** — ordering and elapsed-time measurement within the running process.

The system must never overwrite one timestamp with another merely because they are numerically close.

### Sequence and continuity

If a source publishes sequence numbers or equivalent identifiers, the collector must define:

- expected ordering;
- duplicate handling;
- gap detection;
- whether replay/resend is supported;
- reconnect behavior;
- the condition under which the source becomes healthy again.

If continuity cannot be proven after a disconnect, decision use must remain blocked even if new messages are arriving.

### Staleness

A source-specific staleness threshold must be declared **before** decision use.

The threshold must identify which time is authoritative for the check. Examples include source calculation time, relay receipt time, or local monotonic receive age.

No generic one-size-fits-all threshold is allowed.

### Correction and amendment handling

If a source can amend or correct previously published values:

- preserve the original observation;
- preserve the amended observation;
- record the amendment relationship and amendment time when available;
- never silently rewrite history in the raw archive;
- define whether derived research datasets use first-seen, latest-known, or both views.

Settlement-label construction has an additional requirement: it must use the version prescribed by the official contract/settlement procedure, not whichever version is easiest to obtain.

### Missing-data behavior

No future collector may silently fill a missing authoritative observation with:

- previous value;
- next value;
- interpolation;
- exchange spot;
- another oracle;
- cached data.

Any imputation used for a **research sensitivity experiment** must be explicitly declared, stored as a derived assumption, and never mislabeled as official settlement data.

### Schema drift

Unknown fields may be preserved. Required fields may not be silently renamed, retyped, or coerced.

A material schema or unit change requires:

- raw preservation;
- a versioned parser or registry update;
- tests;
- updated documentation;
- revalidation before decision use.

### Access and credential boundary

A future authenticated source requires a separate explicit authorization decision.

Credentials must:

- never be pasted into chat;
- live only in an ignored local `.env` or secure secret store;
- never appear in raw logs, runtime events, manifests, test fixtures, ZIP bundles, or Git history.

This design does not authorize credentials.

## Authoritative BRTI delivery options

### Option A — Kalshi `cfbenchmarks_value` WebSocket

Role: official BRTI delivery through Kalshi.

Documented strengths:

- raw upstream frame is included;
- roughly one-second updates;
- upstream source timestamp is present inside the raw frame;
- Kalshi receive time is present;
- WebSocket `seq` is present;
- final-minute quarter-hour convenience average is exposed;
- duplicate/out-of-order upstream timestamps are documented as ignored.

Current blockers:

- authenticated Kalshi WebSocket required;
- account access has not been authorized;
- reconnect/replay guarantees for this channel have not been established by the reviewed documentation;
- settlement treatment of amendments/missing ticks remains unresolved;
- exact settlement-engine equivalence of the convenience average remains unresolved.

This is the strongest future candidate for **live official-index research**, but no implementation should begin until authorization and continuity rules are accepted.

### Option B — Kalshi CF Benchmarks REST passthrough

Role: official CF Benchmarks REST delivery through Kalshi.

Documented strengths:

- forwards supported CF Benchmarks REST paths and query parameters;
- returns the upstream response inside a Kalshi `data` envelope;
- can query `values?id=BRTI`.

Current blockers/tradeoffs:

- authenticated Kalshi request required;
- appropriate account entitlement required;
- passthrough requests cost more read-budget tokens than ordinary requests;
- polling is not a substitute for a sequence-aware live stream;
- upstream errors/timeouts can be mapped to Kalshi service errors.

This may later be useful for reconciliation or bounded historical/recent queries, not automatically as the primary live collection path.

### Option C — Direct CF Benchmarks API/WebSocket

Role: direct authoritative provider delivery.

Documented strengths:

- direct value stream;
- `PER_SECOND` and, for BRTI, `PER_200MS` capability;
- amendment metadata in the provider API;
- direct provider timestamp semantics.

Current blockers:

- CF Benchmarks API key/license required;
- no license or key is authorized;
- separate commercial/access terms would have to be evaluated.

The project should not pursue this simply to bypass the current authorization boundary.

## Auxiliary predictive/reference options

No auxiliary source is selected in checkpoint 06. A later source-selection experiment should compare candidates against the same requirements.

### Public exchange spot feeds

Potential role: low-latency predictive feature.

Advantages may include public access, high update frequency, and direct market microstructure.

Risks:

- one exchange is not BRTI;
- BTC/USDT is not automatically equivalent to BTC/USD;
- venue-specific outages, wash activity, local liquidity, and timestamp semantics can create basis or lag;
- historical and live formats may differ;
- a feed that is excellent for prediction can still be invalid for settlement labels.

### Pyth or other oracle feeds

Kalshi currently documents an authenticated `pyth_value` WebSocket with source and receive timestamps for configured underlyings.

It may eventually be evaluated as a predictive/reference source if an appropriate BTC underlying is available. It is not KXBTC15M settlement authority under the current rule evidence.

The project should not add it merely because it is already available through the Kalshi WebSocket stack.

### Multi-source aggregate

A later research model may benefit from multiple auxiliary sources, but aggregation should be postponed until a single-source baseline is understood.

Adding more feeds increases:

- clock-alignment complexity;
- missing-data states;
- schema surface;
- licensing/access complexity;
- risk of accidental look-ahead or inconsistent historical reconstruction.

The default remains: **simple, testable baseline first**.

## Source-selection scorecard for the later implementation checkpoint

Any candidate reference feed should be evaluated on the following dimensions before code is written:

| Dimension | Required question |
|---|---|
| Role | Settlement authority, official delivery, execution data, predictive reference, or clock health? |
| Instrument definition | Exactly what asset, quote currency, index, or venue does the value represent? |
| Authentication | Public, signed, entitled, licensed, or otherwise restricted? |
| Source timestamp | Is there an authoritative source/event/calculation timestamp? |
| Receive timestamp | Does an intermediary provide a receive timestamp? |
| Sequence | Is there a monotonic sequence/update identifier? |
| Replay | Can missed data be replayed or queried exactly? |
| Reconnect | What proves continuity after reconnect? |
| Cadence | Expected and maximum publication/update rate? |
| Correction policy | Can values be amended or restated? |
| Missing-data policy | What does the source publish when it cannot calculate? |
| Historical availability | Can the exact live representation be reproduced later? |
| Raw fidelity | Can the project preserve the exact source message/response? |
| Schema stability | Is there official versioned documentation? |
| Rate limits | Can the intended collection cadence operate safely? |
| Terms/license | Is the intended research use allowed? |
| Clock alignment | Can source-to-local uncertainty be bounded? |
| Testability | Can disconnects, duplicates, gaps, stale data, and drift be exercised in tests? |

A candidate that fails a mandatory dimension may still be archived for investigation but cannot become decision-eligible.

## Proposed collection sequence

When the project later authorizes a new source, the safest order is:

1. Record the exact source and role in the source registry.
2. Document access terms and official schemas.
3. Define raw record format and timing fields.
4. Define freshness, sequence, reconnect, and clock-health gates.
5. Implement raw-only collection first.
6. Add deterministic parser and derived lineage.
7. Add offline integrity/reconciliation validation.
8. Run bounded live collection.
9. Only then design synchronized features against Kalshi data.
10. Only after settlement-label semantics are sufficiently established may settlement-aware supervised modeling begin.

No step authorizes trading.

## Recommended next implementation decision

Checkpoint 06 should stop after the edge-case and reference-data contracts are accepted and documented.

The next code-bearing milestone should **not** begin by choosing an exchange feed. It should first decide which of these two research paths is justified:

- **Official-index collection path:** explicitly authorize and design authenticated BRTI collection, with secure local credentials and fail-closed continuity controls; or
- **Auxiliary-predictor path:** choose one public BTC reference feed for prediction research while keeping settlement labels separately sourced and blocked until authoritative semantics are sufficient.

That decision should be based on the research question and access constraints, not convenience.

## Official sources reviewed

- Kalshi CF Benchmarks Value Feed: `https://docs.kalshi.com/websockets/cfbenchmarks-value`
- Kalshi Pyth Value Feed: `https://docs.kalshi.com/websockets/pyth-value`
- Kalshi CF Benchmarks REST Passthrough: `https://docs.kalshi.com/cfbenchmarks/rest-passthrough`
- Kalshi Quick Start: WebSockets: `https://docs.kalshi.com/getting_started/quick_start_websockets`
- Kalshi Quick Start: Market Data: `https://docs.kalshi.com/getting_started/quick_start_market_data`
- CF Benchmarks REST API authentication: `https://docs.cfbenchmarks.com/api/`
- CF Benchmarks WebSocket API authentication: `https://docs.cfbenchmarks.com/api/websocket/intro/`
- CF Benchmarks value REST API: `https://docs.cfbenchmarks.com/api/rest/values/`
- CF Benchmarks value WebSocket: `https://docs.cfbenchmarks.com/api/websocket/value/`
- CF Benchmarks CME CF Cryptocurrency Real Time Indices Methodology Guide, v16.8: `https://docs.cfbenchmarks.com/CME%20CF%20Real%20Time%20Indices%20Methodology.pdf`
- Existing project source contracts: `configs/source_registry.json`, `docs/SOURCE_QUALITY_POLICY.md`, `docs/SETTLEMENT_VALIDATION.md`, and `docs/SETTLED_MARKET_EVIDENCE.md`
