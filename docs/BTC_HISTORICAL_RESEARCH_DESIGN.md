# Checkpoint 10 — BTC-Specific Historical Research Design

Status: **pre-outcome design accepted; structure inventory implementation pending canonical validation**

## Purpose

Checkpoint 10 defines the statistical/evaluation unit for Kalshi BTC research before any final outcome analysis, predictive feature selection, external feed selection, or model training.

This checkpoint remains public and read-only.

## Core methodological decision

A Kalshi market ticker is not automatically an independent research observation.

The primary evaluation object is a **settlement cluster**: all contracts whose payouts depend on the same set of underlying settlement primitives.

A **settlement primitive** is one underlying measurement needed to determine settlement. Examples include a particular pre-boundary BRTI average or a particular price observation/window used by a family of strike contracts.

Consequences:

- multiple strikes that use the same underlying settlement value are one cluster, not many independent trials;
- one-minute quote/candle rows are repeated observations, not independent outcomes;
- source `event_ticker` remains important lineage, but it is not assumed to be a universal independence unit;
- train/development/holdout splits must keep each settlement cluster intact;
- if two clusters share an exact settlement primitive, the split boundary must keep that primitive on one side or embargo the boundary clusters.

## KXBTC15M special case

Earlier project validation established that KXBTC15M compares two 60-second CF Benchmarks BRTI averages associated with the market open and market close boundaries.

For Checkpoint 10 structural grouping, a KXBTC15M market therefore receives two primitive identities:

1. the pre-open BRTI 60-second boundary primitive;
2. the pre-close BRTI 60-second boundary primitive.

The settlement cluster ID is a deterministic hash of the two primitive identities.

The structural inventory does **not** claim exact settlement-engine replication. Rounding, corrections, missing ticks, outages, and other exceptional semantics remain unresolved under the existing settlement-validation documents.

### Shared-boundary leakage rule

If consecutive KXBTC15M contracts share the same boundary timestamp, then one contract's closing primitive can be the next contract's opening primitive. The inventory records this as a `shared_settlement_primitive` overlap edge.

Future chronological splitting must satisfy:

```text
primitive_ids(development) ∩ primitive_ids(holdout) = ∅
```

or explicitly embargo the boundary clusters that would violate it.

## Other BTC contract families

Checkpoint 10 must not infer settlement primitives merely because contracts share a series, event, title, close time, or strike structure.

Until rule semantics are validated, non-KXBTC15M contracts are grouped only into **candidate clusters** by:

```text
series_ticker + event_ticker + close_time
```

This captures obvious contract fan-out without claiming that the candidate group is already a scientifically valid independence unit.

Candidate groups are labeled `candidate_requires_rule_validation`. Missing close-time structures are labeled `unresolved`.

## Outcome-blind boundary

The structure inventory may use:

- event and series identifiers;
- category and titles;
- market type;
- open/close/expiration/settlement timestamps;
- strike metadata;
- written rules (or hashes of written rules);
- raw request lineage.

It must not use or materialize:

- final `result`;
- settlement/expiration values;
- quote or trade prices;
- bid/ask state;
- volume/open interest/liquidity;
- candlestick observations;
- external predictive feeds.

Raw public market responses may naturally contain final fields. They remain preserved in the raw archive but are not read into the derived inventory.

## First Checkpoint-10 dataset

Dataset family:

```text
btc_research_unit_inventory.v1
```

Derived tables:

1. BTC events;
2. BTC markets;
3. settlement clusters;
4. shared primitive overlap edges;
5. series-level structural summaries.

## Discovery/routing

The implementation reuses already-registered public Kalshi sources:

- `GET /events` for settled Event metadata;
- `GET /historical/cutoff` for current routing boundaries;
- `GET /historical/markets` for archived markets;
- `GET /markets` for recent settled markets.

Kalshi documents that Events remain on the normal Event endpoints even when older associated Markets have moved behind the historical cutoff.

No new authenticated source or external BTC feed is introduced.

## What the inventory can decide

After canonical validation and a live run, the project can measure:

- which BTC-involving series actually exist in the settled historical universe;
- event and market fan-out per series;
- how many settlement clusters are resolved versus candidate/unresolved;
- strike-type diversity;
- chronology and historical support;
- whether KXBTC15M shared-boundary dependence occurs in practice;
- which families need additional rule parsing before any outcome experiment can be predeclared.

## What it cannot decide

The inventory cannot establish:

- prediction accuracy;
- calibration/miscalibration;
- trading edge;
- expected value;
- profitability;
- executable fills;
- which external BTC feed should be selected.

Sports V2 and project/token FDV remain qualified secondary branches, not rejected branches.

## Next gate

Do not select a model or external predictive feed after merely running the collector.

First inspect the outcome-blind series/cluster summary and decide which BTC family has a coherent validated settlement unit plus sufficient historical support. Only then predeclare the first BTC hypothesis and chronological development/holdout rule.

## Checkpoint-10 BTC family selection

The outcome-blind family quote-feasibility comparison is complete.

Accepted run:

```text
collect_btc_family_quote_feasibility_20260809T114516450822Z_a232d26c
```

Disposition:

1. `KXBTCD` is selected for the first BTC historical baseline pilot.
2. The eligible settlement regime is `brti_60s_simple_mean_untrimmed`.
3. The first pilot uses the already selected 20 settlement clusters and three structural probes per cluster (`q25`, `q50`, `q75`).
4. A pre-outcome synchronization and chronological split must be frozen before any final result is opened.
5. The first baseline compares raw same-time quote midpoints with an outcome-blind nonincreasing cross-strike isotonic projection.
6. Cluster-weighted log loss is the primary outcome metric. Brier score is secondary because L2 projection has a structural squared-error non-worsening property against a coherent monotone realized threshold vector.
7. No external BTC reference feed is selected yet. The simple internal market-structure baseline comes first under D-021.
8. KXBTC15M remains a qualified secondary benchmark. KXBTC remains deferred after its 45% ladder-breadth result failed the frozen 50% gate.

The full predeclared contract is in `docs/KXBTCD_BASELINE_EXPERIMENT.md`.

### KXBTCD pre-outcome synchronization result

The frozen pre-outcome command passed with 12/20 (60%) primary synchronized clusters, above the predeclared 50% minimum. The 12 clusters are chronologically partitioned into eight development and four untouched holdout clusters under design fingerprint:

```text
bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4
```

The next authorized research step is development-only label materialization and scoring for the eight frozen development clusters. Holdout results remain blocked from that command. No external predictive feed is introduced.

### KXBTCD development result and holdout gate

The frozen KXBTCD v1 development set has now been scored from eight settlement clusters and 72 predeclared predictions. The raw-vs-monotone development log-loss delta was positive but very small:

```text
raw log loss:      0.1229517749838280758888888889
monotone log loss: 0.1226068974322313537500000000
delta:             0.0003448775515967221388888889
```

Raw ladders violated threshold-probability monotonicity in 37.5% of the 24 development cluster-band cross-sections. The average absolute isotonic adjustment was below one percentage point. These are development diagnostics only; they do not establish predictive edge or profitability.

No v1 model, metric, sample, synchronization, weighting, or decision threshold is changed after viewing the development result. Therefore the next required research action is the untouched four-cluster holdout evaluation under the original design fingerprint. The holdout implementation is limited to executing that already-frozen procedure and includes an offline recovery path before any holdout label is exposed.

## Final Checkpoint-10 KXBTCD v1 result

The untouched four-cluster holdout was opened exactly once under the original frozen design fingerprint, with no model or metric change after development:

```text
holdout clusters: 4
holdout labels: 12
scored predictions: 36
raw log loss:      0.03832137791396992041666666668
monotone log loss: 0.03832137791396992041666666668
delta log loss:    0
raw Brier:         0.01129722222222222222222222222
monotone Brier:    0.01129722222222222222222222222
delta Brier:       0
raw monotonicity violation rate: 0
mean absolute adjustment: 0
max absolute adjustment: 0
```

The development improvement therefore did **not** replicate out of sample. The v1 hypothesis that simple nonincreasing isotonic post-processing adds predictive value beyond the raw three-probe KXBTCD quote midpoints is **not supported by this untouched holdout**.

This is a narrow result. It does not imply that the KXBTCD ladder contains no useful information, that Kalshi markets are efficient, or that another predeclared BTC model cannot work. It also does not establish trading economics or profitability. The sample is deliberately small, quote midpoints are not executable fills, and no fees, depth, latency, adverse selection, or external predictive feed were modeled.

Checkpoint 10 should close without tuning the v1 monotone baseline against the now-open holdout. The next milestone should reassess whether to expand the KXBTCD sample, introduce a simple external-information baseline under D-021, or compare another already-qualified BTC family.
