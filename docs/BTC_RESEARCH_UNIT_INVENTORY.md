# BTC Research-Unit Inventory

Status: implementation candidate for Checkpoint 10.

## Command

```powershell
.\.venv\Scripts\python.exe collect_btc_research_unit_inventory.py
```

## Safety contract

The command is public/read-only and uses no credentials. It does not collect quotes/candles, inspect final outcomes, select an external feed, train a model, simulate execution, or place orders.

## Discovery design

The inventory uses a **series-first BTC discovery path**:

1. `GET /series?category=Crypto` discovers Crypto series templates.
2. BTC-identifiable series are selected from outcome-blind Series metadata: ticker, title, and tags.
3. `GET /events?status=settled&series_ticker=<BTC_SERIES>` completely retrieves settled events separately for each selected BTC series.
4. Up to 25 events per series are selected deterministically by ascending `SHA-256(event_ticker)`.
5. Historical/live Market metadata is retrieved by exact `event_ticker` for those sampled events across the current historical cutoff.

This replaces the initial global `GET /events?status=settled` crawl. The first live attempt reached the global event-page safety guard while Kalshi still returned a continuation cursor. That failure was expected fail-closed behavior, but the discovery path was inefficient because unrelated Sports, Weather, politics, and other settled events consumed the BTC inventory's pagination budget.

The corrected path does **not** merely increase the global page cap. Kalshi's documented Series category filter and Event `series_ticker` filter let the collector narrow the universe before deep pagination.

Per-series **event** pagination still fails closed if a selected BTC series remains incomplete at its configured guard. Each sampled event also has its own Market-pagination guard.

### Event category compatibility field

The first series-first live retry exposed a source-shape assumption: a settled event returned by the exact `series_ticker=KXBTC15M` filter did not report `category=Crypto`. Kalshi's glossary defines category as a **Series-level** grouping, and the API changelog marks `EventData.category` deprecated.

The collector therefore uses exact returned `event.series_ticker == queried_series_ticker` as the membership check. The event's legacy `category` value is preserved verbatim for audit and a mismatch counter is recorded, but that deprecated field no longer rejects an otherwise valid event from a selected Crypto series. A wrong returned `series_ticker` still fails closed.

## Outputs

Under `data/derived/btc_research_unit/YYYY/MM/DD/`:

- `*_btc_events.csv`
- `*_btc_markets.csv`
- `*_btc_settlement_clusters.csv`
- `*_btc_primitive_overlaps.csv`
- `*_btc_series_summary.csv`

Every source-derived Event and Market row carries exact raw request lineage. Aggregate cluster/series rows carry the contributing lineage set as JSON.

## Cluster states

### `resolved`

Currently reserved for KXBTC15M where the project's existing settlement validation supports the two pre-boundary BRTI primitives needed for structural grouping.

### `candidate_requires_rule_validation`

Contracts share `series_ticker + event_ticker + close_time`, but Checkpoint 10 has not yet validated that they truly use the same underlying settlement primitive.

### `unresolved`

Required grouping metadata is absent or ambiguous. These rows cannot be treated as independent evaluation units.

## Primitive overlap

Resolved clusters are compared for shared primitive IDs. Any overlap produces a row with split policy:

```text
same_partition_or_boundary_embargo
```

This prevents a shared settlement measurement from leaking across future chronological development/holdout boundaries.

## Acceptance sequence

1. Apply the replacement bundle.
2. Run the full canonical test suite.
3. Only after tests pass, rerun the public inventory collector.
4. Validate the generated collection manifest with the existing manifest validator.
5. Inspect series/cluster counts before choosing a BTC hypothesis.

No outcome analysis is authorized by a successful inventory run.

## Historical market filter compatibility

The historical market-list endpoint states that its selection filters are mutually
exclusive. The inventory therefore uses exact `event_ticker` as the sole
historical selection filter. The live `/markets` request for the same sampled
event may additionally use `status=settled` and `mve_filter=exclude`.

This is a transport/query-shape rule only. It does not change settlement-cluster
meaning, outcome blindness, or strategy eligibility.

## KXBTC contract-fanout correction

A later live retry established that the valid series-scoped historical request for
`KXBTC` still returned a continuation cursor after 100 pages of 1,000-market
pages. The collector failed closed rather than accepting a truncated series.

This is not evidence that the source is unusable. It shows that **complete
contract enumeration across an entire large BTC series is the wrong unit of work
for this design checkpoint**. Checkpoint 10 currently needs representative
contract structure and dependence, not every historical contract ever listed.

The inventory therefore now separates two levels:

1. **Complete event discovery per selected BTC series.** The event cursor must be
   exhausted; otherwise the run fails closed.
2. **Bounded structural Market sample.** After complete event discovery, select up
   to 25 events per series by ascending `SHA-256(event_ticker)`. This selection
   uses no outcome, quote, price, volume, liquidity, or settlement-value field.

For each sampled event the collector requests Markets by exact `event_ticker`:

```text
GET /historical/markets?event_ticker=<EVENT>
GET /markets?event_ticker=<EVENT>&status=settled&mve_filter=exclude
```

Kalshi documents `event_ticker` on both Market-list endpoints. Historical filters
are mutually exclusive, so `event_ticker` is the sole historical selection
filter. Each sampled event has its own pagination guard; incomplete event-level
Market retrieval is rejected.

The series summary records both the complete discovered settled-event count and
the sampled event count. Thus the structural sample cannot be mistaken for the
series' effective historical sample size.

This bounded structural sample is **not** the later strategy evaluation dataset.
Once a specific BTC family and hypothesis are selected, Checkpoint 10 must
separately predeclare the historical coverage/evaluation sample and its
chronological split rules before opening outcomes.


## Candidate-cluster label invariant

For non-KXBTC15M families whose exact settlement primitive has not yet been
validated, the inventory uses one conservative cluster-level family label:
`same_event_close_candidate`. Markets remain grouped by selected Series, source
Event, and canonical close boundary even if source strike metadata is populated
inconsistently across contracts. Market-level `strike_type`, floor/cap strike,
functional strike, and custom-strike fields remain preserved separately.

This prevents a metadata-presence difference from falsely splitting correlated
contracts. It does **not** declare the grouped contracts economically identical;
the cluster remains `candidate_requires_rule_validation`.

## Ladder settlement-rule regime gate

The first outcome-blind temporal rule check found a **real settlement-rule
change**, so `KXBTC` and `KXBTCD` must not be treated as one stationary rule
template across their full histories.

Direct raw-rule evidence from the completed Checkpoint-10 inventory showed:

- an early sampled `KXBTC` contract (2024-10-31 close) used a **five-minute
  BRTI average with the top 20% and bottom 20% removed**;
- another observed 2024 `KXBTC` contract used a **60-second BRTI average with
  the top/bottom 20% removed**;
- sampled 2025-2026 `KXBTC` contracts used a **simple 60-second BRTI/RTI
  average** with no trimming stated;
- an early sampled `KXBTCD` contract (2024-12-20 UTC close) used the
  **60-second trimmed-average** mechanism; and
- sampled 2026 `KXBTCD` contracts used the **simple 60-second average**
  mechanism.

Accordingly, the validator no longer asks whether one rule signature is stable
across only early/middle/late samples. It now inspects **one deterministic
representative market from every event already selected by the outcome-blind
Checkpoint-10 structure sample** and classifies each into a narrowly recognized
semantic regime.

Currently recognized mechanisms are:

1. five-minute BRTI trimmed mean, dropping top/bottom 20%;
2. 60-second BRTI trimmed mean, dropping top/bottom 20%;
3. 60-second simple BRTI/RTI mean using 60 final-minute RTI observations.

A sampled 2025 `KXBTC` contract exposed a wording-only variant of mechanism 2:
the primary rule states the 60-second BRTI window and 20%/20% trimming, while
the secondary rule describes 60 final-minute RTI observations and says the
average excludes the top 20% (12) and bottom 20% (12) of collected prices. The
source text also contained the whitespace defect `prices arecollected`. This is
classified as the same 60-second trimmed regime because both rule fields prove
the same measurement semantics; the parser tolerates only that observed
whitespace defect and still rejects unknown windows or trim percentages.

The payoff relation remains separate from the measurement mechanism. `KXBTC`
events can contain lower-tail (`less` / rule wording `below`), interior
(`between`), and upper-tail (`greater` / rule wording `above`) contracts in the
same ladder. `KXBTCD` uses the `greater` / `above` threshold relation. These
payoff shapes do not create separate settlement primitives when the underlying
BRTI measurement is the same.

Any unrecognized window/statistic/trimming wording, inconsistent clock label,
missing exact raw lineage, or raw/derived rule-hash mismatch fails closed.
A validator PASS means all sampled event representatives were lineage-verified
and assigned to a recognized regime. It **does not** mean the Series is
stationary, that every unsampled historical event has been classified, or that
an exact production rule-change timestamp has been established.

When chronology shows different signatures, the report records only the last
sampled event seen in the old regime and the first sampled event seen in the new
regime. These are **sample-observed transition brackets**, not exact rule-change
boundaries.

Future historical modeling must partition observations by validated settlement
regime (or explicitly exclude incompatible regimes) rather than pooling all
`KXBTC` or all `KXBTCD` history under one settlement definition.

### All-market ladder cluster semantic gate

Before KXBTC or KXBTCD sampled candidate clusters may be promoted to resolved,
`validate_btc_ladder_cluster_semantics.py` must validate every sampled market
against its exact raw request. A passing event requires one recognized **settlement measurement regime**
across all of its strikes, exact rule-hash lineage, and an explicit EST/EDT
rule clock that maps exactly to the derived UTC close time. Payoff relations are
validated contract-by-contract from the preserved primary rule text and are
cross-checked against derived/raw `strike_type` whenever that optional metadata
is present. Historical markets with missing `strike_type` may still resolve only
when the primary rule uniquely proves `below`, `between`, or `above`; ambiguous
wording remains fail-closed. Lower-tail, interior, and upper-tail contracts may
coexist in one event without splitting the settlement primitive.

The resolved settlement primitive identity is based on the validated BRTI
measurement itself: index provider/name, window length, statistic, trimming
policy, and exact UTC measurement end. The payoff relation or strike boundary
is deliberately excluded from primitive identity. Therefore different ladder
payoffs can share one settlement primitive, including across Series, if they
reference the exact same validated BRTI observation.

## Accepted all-market ladder semantic result

The all-market semantic resolver passed on the complete sampled ladder set already selected outcome-blind by the Checkpoint-10 inventory:

```text
KXBTC:  2,393 sampled markets -> 25 resolved event clusters -> 25 unique primitives
KXBTCD: 2,915 sampled markets -> 25 resolved event clusters -> 25 unique primitives
Shared primitive groups within ladder sample: 0
Cross-series shared primitive groups: 0
```

Observed sampled rule-regime counts were:

```text
KXBTC
  brti_300s_trimmed_mean_trim20_20: 1 cluster
  brti_60s_trimmed_mean_trim20_20:  2 clusters
  brti_60s_simple_mean_untrimmed:   22 clusters

KXBTCD
  brti_60s_trimmed_mean_trim20_20:  1 cluster
  brti_60s_simple_mean_untrimmed:   24 clusters
```

This resolves the **50 sampled KXBTC/KXBTCD ladder clusters only**. It does not authorize treating every unsampled historical event in either Series as resolved. Any larger historical dataset must rerun the same semantic proof or otherwise restrict itself to already validated clusters/regimes.
