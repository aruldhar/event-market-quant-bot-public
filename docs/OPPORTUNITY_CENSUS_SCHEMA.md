# Opportunity Census Schema

Status: checkpoint-07 event-first discovery contract. One complete public read-only multi-venue event census has passed independent manifest validation; a source-native nested contract-snapshot extension is the current candidate.

## Purpose

Create a venue-neutral, append-only evidence layer that answers:

- what markets/products are available;
- what market quality is observable;
- what costs/settlement/data-quality constraints apply;
- which market/strategy hypotheses deserve deeper collection.

The census is **not** a trading engine and **not** a predictive feature store.

## Design principles

1. Preserve venue-native raw data before normalization.
2. Never synthesize unavailable fields.
3. Store source identity and semantic provenance with every normalized value.
4. Capture local UTC and monotonic receipt timing.
5. Separate slowly changing metadata from market snapshots.
6. Separate fees/incentives from prices because commercial terms can change independently.
7. Keep settlement/payoff semantics explicit.
8. Do not infer one venue's field meaning from another venue's similarly named field.
9. Do not require one universal market taxonomy at ingestion time.
10. No order/authentication behavior in census v1.


## Accepted baseline discovery granularity

Checkpoint-07 live evidence showed that **one binary market contract is too low-level to be the primary opportunity unit**. In a preserved Kalshi run, the first 50,000 open non-MVE market contracts represented only 5,935 unique event tickers, and individual events exposed hundreds of line/strike contracts. Pagination was healthy, so this was genuine contract fan-out rather than a cursor bug.

Census v1 therefore uses three logical layers:

```text
Stage 1:  venue -> series/category -> event/opportunity identity
Stage 1b: same raw discovery response -> source-native nested contract snapshots
Stage 2:  shortlisted event/series -> dedicated BBO/book/history/high-cadence collection
```

Stage 1 is the neutral screening layer. It emits one row per source event/occurrence and may retain `contract_count_source` where officially exposed. It does **not** count every strike, total, spread, or outcome contract as an independent high-level opportunity.

Stage 1b captures contract/market objects only when they are already embedded in the same event-discovery response (or, for Kalshi, can be enabled on the same paginated endpoint). These rows are a separate artifact and never increase the high-level opportunity count.

Stage 2 remains deferred until the Stage-1 evidence identifies event/series/strategy candidates worth deeper collection. Stage 2 may then use dedicated BBO/order-book/price/history endpoints and source-appropriate cadence to measure depth, fill realism, fee economics, and update behavior.

This rule is venue-neutral: Gemini event responses, Polymarket US events, Crypto.com prediction events, and Kalshi events are all normalized first at their event/occurrence layer. Venue-native hierarchy remains preserved; no source is forced to invent a series ID or contract count it does not expose.

### `opportunity_identity.v1`

The implemented Stage-1 CSV schema is `census_opportunity_identity.v1`. Conceptual fields are:

```text
schema_version
venue_id
source_opportunity_type
source_opportunity_id
source_event_id
source_series_id
source_ticker
source_title
source_subtitle
source_category
source_subcategory
product_type_source
market_status_source
source_event_time
source_start_time
source_end_time
contract_count_source
volume_source
liquidity_source
open_interest_source
raw_source
raw_session_id
raw_request_id
local_request_start_utc
local_request_start_monotonic_ns
local_receive_utc
local_receive_monotonic_ns
```

Important semantics:

- `contract_count_source` is metadata, not an opportunity score.
- Missing hierarchy or economics fields remain blank rather than guessed.
- Contract-level prices are deliberately absent from the Stage-1 event identity row. When nested contracts are available, they are written to the separate Stage-1b contract-snapshot artifact.
- A source event date is not silently relabeled as a market open/close/settlement timestamp.
- Raw HTTP response persistence still precedes normalization.


### `census_contract_snapshot.v1`

The Stage-1b contract artifact preserves source-native market/contract fields from the **same raw discovery response**. It is descriptive screening evidence, not a normalized execution model.

```text
schema_version
venue_id
source_event_id
source_contract_id
source_contract_ticker
source_contract_title
source_contract_status
source_contract_type
quote_semantics_source
best_bid_source
best_ask_source
last_trade_price_source
yes_bid_source
yes_ask_source
yes_bid_size_source
yes_ask_size_source
no_bid_source
no_ask_source
yes_price_source
no_price_source
reference_probability_source
payout_per_100_source
total_shares_source
volume_source
volume_24h_source
open_interest_source
liquidity_source
fee_coefficient_source
source_start_time
source_end_time
source_updated_time
raw_source
raw_session_id
raw_request_id
local_request_start_utc
local_request_start_monotonic_ns
local_receive_utc
local_receive_monotonic_ns
```

Semantics remain intentionally asymmetric:

- Kalshi: explicit source YES/NO quote fields remain `yes_*` / `no_*`; they are not silently relabeled as another venue's generic contract BBO.
- Kalshi: current official API documentation marks Market `liquidity` / `liquidity_dollars` deprecated and returning zero. `liquidity_source` is preserved as source evidence but must be classified as deprecated/unavailable for economic screening, not interpreted as observed zero liquidity.
- Gemini: documented `prices.bestBid`, `prices.bestAsk`, and `lastTradePrice` map to the generic source-defined best-bid/ask/last fields.
- Polymarket US: nested `bestBidQuote.value` and `bestAskQuote.value` map to the source-defined best-bid/ask fields. `feeCoefficient` is preserved only as `fee_coefficient_source`; its effective fee economics are unresolved until the formula is separately validated.
- Crypto.com: nested `yes`, `no`, `chance`, and `payout_per_100` remain source-native display/reference fields. They are **not** relabeled as executable bid/ask. The venue's dedicated contract-price endpoint defines separate `bid`, `ask`, `mid`, `probability`, and `spread` fields and is reserved for later targeted collection.

Blank values mean the nested discovery payload did not safely expose that metric. No complement, spread, midpoint, fee, or probability transformation is performed in Stage 1b.

## Proposed record families

The implementation may use JSON/JSONL/CSV as appropriate, but logical records should remain separable.

### `venue_capability.v1`

One versioned observation of a venue/source capability.

Required conceptual fields:

```text
schema_version
observed_at_utc
observed_monotonic_ns
venue_id
legal_entity_or_exchange_name
regulatory_status
regulatory_source_url
execution_eligibility_state
public_research_eligibility_state
api_documentation_url
public_discovery_available
public_snapshot_available
public_stream_available
stream_authentication_mode
historical_data_available
rate_limit_summary
licensing_notes
capability_evidence[]
raw_lineage
```

`execution_eligibility_state` and `public_research_eligibility_state` are separate. A venue may be research-observable without being an execution candidate.

Unknown/unclear states must remain explicit.

### `market_identity.v1`

**Stage 2 only.** Stable identity/lifecycle metadata for one source market/contract after an event/series candidate survives baseline screening.

Conceptual fields:

```text
schema_version
venue_id
source_market_id
source_event_id
source_series_id
source_contract_id
source_ticker
source_title
source_subtitle
source_category
source_subcategory
normalized_category_version
normalized_category
contract_type_source
payout_currency_or_unit
open_time_source
close_time_source
expiration_time_source
settlement_time_source
market_status_source
settlement_source_name
settlement_rule_url
contract_rule_text_or_reference
source_payload_fields_present[]
raw_lineage
first_seen_utc
first_seen_monotonic_ns
```

Normalization may add `normalized_category`, but the exact source category/title fields are preserved.

### `market_snapshot.v1`

One locally observed market-state snapshot.

Required envelope:

```text
schema_version
snapshot_id
venue_id
source_market_id
source_ticker
source_observation_time_utc
source_publication_time_utc
local_request_start_utc
local_request_start_monotonic_ns
local_receive_utc
local_receive_monotonic_ns
alignment_epoch_id
raw_lineage
```

Market fields, only where officially defined/available:

```text
yes_best_bid
yes_best_ask
yes_best_bid_size
yes_best_ask_size
no_best_bid
no_best_ask
no_best_bid_size
no_best_ask_size
spread_yes
spread_no
mid_yes
near_touch_depth_yes
near_touch_depth_no
total_displayed_depth_yes
total_displayed_depth_no
volume_source
volume_units
open_interest_source
open_interest_units
last_trade_price
last_trade_size
market_status_source
```

The normalized binary fields may not exist for non-binary products. In those cases use product-specific extensions rather than forcing a fake YES/NO representation.

### `market_metric_unavailable.v1`

For important comparison fields that cannot be observed, record why rather than silently using null with no explanation.

```text
venue_id
source_market_id
snapshot_id_or_capability_id
metric_name
reason_code
source_evidence
observed_at_utc
```

Initial reason codes:

```text
not_exposed_by_source
requires_auth_not_authorized
requires_paid_or_licensed_data
not_applicable_product_type
ambiguous_semantics
endpoint_unavailable
rate_limited
schema_drift
collection_error
```

### `cost_schedule.v1`

Fees and incentives are versioned separately from market data.

Conceptual fields:

```text
schema_version
venue_id
product_scope
market_scope
maker_fee_rule
taker_fee_rule
settlement_fee_rule
rebate_rule
liquidity_incentive_rule
effective_start_utc
effective_end_utc
source_url
observed_at_utc
raw_evidence_reference
notes
```

Never assume an incentive remains active after `effective_end_utc` or an undocumented change.

### `resolved_outcome.v1`

Officially observed resolved/settled outcome evidence.

Conceptual fields:

```text
schema_version
venue_id
source_market_id
source_contract_id
result_source
settlement_value_source
settled_at_source
local_receive_utc
local_receive_monotonic_ns
settlement_source_name
rule_reference
raw_lineage
validation_state
```

This is the label source for calibration research. Auxiliary predictive prices must not overwrite official outcome fields.

## Derived analytical fields

Derived values are not raw source truth and must identify their formula/version.

Examples:

```text
time_to_close_seconds
contract_lifetime_seconds
spread_yes
mid_yes
near_touch_depth_yes
quote_age_monotonic_ms
```

Every derived dataset should retain the raw identifiers needed to reproduce it.

## BBO derivation for complementary binary books

Some binary venues may expose bids on both YES and NO rather than explicit asks.

If and only if venue mechanics officially establish the complementary payoff relation, an ask may be derived from the opposite-side bid using the venue's payout unit.

Record:

```text
ask_derivation_method
ask_derivation_source_rule
```

Do not apply this transformation to every venue merely because another binary exchange uses it.

## Product-type extensions

The census must support non-identical contract designs.

Possible extensions include:

- range/bucket contracts;
- spread/total sports contracts;
- threshold contracts;
- multi-leg/parlay products;
- scalar/continuous payoff products;
- futures/options/reference products used for relative value.

Do not coerce a multi-leg or scalar payoff into a binary single-contract schema unless the transformation is mathematically valid and recorded.

## Horizon representation

Store exact timestamps and derive continuous horizon metrics.

Do not store `15m` as the only supported horizon.

Optional analysis buckets are created downstream and versioned.

## Snapshot cadence

Stage-1 event discovery uses bounded source-appropriate pagination rather than a latency cadence. Stage-2 market snapshots, once authorized by the census result, should use a conservative source-appropriate cadence designed to compare market quality, not win a latency race.

Cadence must respect:

- documented rate limits;
- public access terms;
- expected contract duration;
- source cost;
- storage volume.

The exact cadence is an implementation decision per adapter and must be recorded in the run manifest.

## Raw preservation

Every source request/response or received frame used by the census must be persisted before normalization.

Existing `raw_http_exchange.v1` can be reused for public REST sources where its envelope fits.

Streaming sources require a separately versioned raw-message schema before implementation; do not fake streaming frames as HTTP responses.

## Run manifests and runtime events

Every census collector run should use the existing project lifecycle concepts:

- running/completed/failed manifest state;
- exact Git/worktree identity;
- artifact hashes/counts;
- structured runtime events;
- raw source sessions;
- fail-closed required persistence.

Material schema extensions require tests and documentation.

## Source registry

Do not pre-register every researched venue as an active collected source.

When an adapter is implemented, add exact source identities to `configs/source_registry.json` or a versioned successor with:

- owner;
- transport;
- endpoint identity;
- roles;
- authentication;
- timestamps;
- collection state;
- validation state;
- quality policy;
- official evidence.

If the current source-registry schema cannot represent non-Kalshi market scope cleanly, propose a versioned schema change rather than overloading KXBTC15M fields.

## Fail-closed behavior

### Raw persistence failure

Stop that source path. No normalization without durable raw evidence.

### Ambiguous field semantics

Preserve raw, mark metric unavailable/ambiguous, and do not normalize by guess.

### Schema drift

Preserve raw, emit runtime error, stop or block the affected adapter until reviewed.

### Rate-limit or transport error

Preserve the error according to the raw schema, mark observation missing, and never forward-fill as if live market state were observed.

### Stale data

Use source/strategy-specific age rules. Census analysis may report staleness distributions before any decision-use threshold is accepted.

## Census outputs

The first analysis should produce descriptive evidence, not trading recommendations:

- venue capability matrix;
- market counts by source category and horizon;
- quote availability rates;
- spread distributions;
- depth/activity distributions where available;
- missing-data and error rates;
- settlement/rule/outcome availability;
- cost/incentive schedule inventory;
- list of candidates that fail hard gates;
- shortlist of hypotheses requiring deeper collection.

## Explicit non-goals for census v1

- no profitability claim;
- no model training;
- no order placement/cancellation;
- no authenticated source unless separately authorized;
- no full BRTI replication;
- no cross-venue arbitrage label without payoff equivalence;
- no sub-second lead/lag conclusion from unsynchronized snapshots;
- no arbitrary weighted platform ranking.

## Acceptance tests for the future implementation

At minimum test:

- raw-before-transform ordering;
- source identity and lineage retention;
- metric-unavailable reason handling;
- venue-specific field mapping without cross-venue inference;
- binary complement derivation only when explicitly enabled;
- timestamp preservation;
- no silent missing-data fill;
- schema-drift failure;
- rate-limit/transport error preservation;
- manifest artifact counts/hashes;
- legacy Kalshi collectors remain unchanged unless intentionally migrated.

## Checkpoint-07 public discovery implementation state

The accepted live event-first census uses four unauthenticated public sources:

- Kalshi public `GET /events`;
- Gemini Predictions public `GET /v1/prediction-markets/events`;
- Polymarket US public `GET /v1/events`;
- Crypto.com Predictions public `GET /api/v1/predictions/events`.

The accepted run `collect_opportunity_census_20260809T040935362418Z_2f06e911` produced 12,160 unique event rows and independently validated raw/runtime/derived artifacts. Its 109 raw HTTP records contained 100 successful responses and 9 preserved HTTP 429 attempts that later recovered under bounded retry; runtime error events were zero.

The final accepted event+contract run `collect_opportunity_census_20260809T042743550002Z_4ba09728` produced 12,198 event rows and 107,293 `census_contract_snapshot.v1` rows. Its manifest recorded 101 raw records, 0 raw errors, 119,491 total derived rows, 111 runtime events, 0 runtime errors, and validation PASS. Independent diagnostics found 0 duplicate contract composite keys, 0 orphan contract rows, and 0 event/contract-count mismatches.

The current extension changes Kalshi to `with_nested_markets=true` and writes source-native nested contract/market rows for all four venues into a separate `census_contract_snapshot.v1` CSV. This does not change the event-first opportunity count and does not call dedicated per-contract detail or book endpoints.

### HTTP 429 handling

Public discovery attempts preserve every HTTP response before any retry decision. For HTTP 429, the census client uses bounded exponential backoff and fails closed if the retry budget is exhausted. A successful retry never deletes or replaces the earlier 429 raw record.

The earlier 50,000-market Kalshi runs remain engineering evidence explaining the event-first design. The current event endpoint excludes multivariate events; MVE/combo products remain a separate future product-family census rather than being mixed into the standalone event baseline.
