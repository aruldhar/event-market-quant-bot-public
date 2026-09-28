# KXBTCD Independent-BTC Source Quality and Historical Materialization Audit

**Checkpoint:** 19D-A
**Status:** FROZEN DESIGN â€” OUTCOME-BLIND AUDIT ONLY
**Parent protocol fingerprint:** `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`
**Parent 19C audit fingerprint:** `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d`
**19D-A audit design fingerprint:** `023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c`

## Objective

Checkpoint 19C established that Coinbase and Kraken can be collected alongside KXBTCD for a continuous 24-hour window. That was an engineering-feasibility result, not a feature-source freeze.

Checkpoint 19D-A asks a narrower outcome-blind question before any Candidate-E fit or outcome access:

> Can simple independent-BTC state be reconstructed causally and reproducibly from official native Coinbase/Kraken historical data at the exact already-observed 19C KXBTCD state times, and what source-quality/timestamp distributions should inform a later 19D-B freeze?

19D-A does **not** select a Candidate-E formula, source-quality threshold, consensus-price rule, E1/E2/E3 cohort size, or advancement gate.

## Source facts from official documentation

### Coinbase Exchange

Candidate historical source ID:

`coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1`

Endpoint:

`GET https://api.exchange.coinbase.com/products/BTC-USD/candles`

Official documentation:

`https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles`

Documented properties relevant to 19D-A:

- one-minute granularity is supported with `granularity=60`;
- each returned bucket contains time, low, high, open, close, and volume;
- `close` is the closing/last trade price in the bucket;
- a request returns at most 300 candles;
- intervals with no ticks may be omitted;
- Coinbase explicitly distinguishes historical candles from real-time trade/book/WebSocket data.

The Exchange candle response is a top-level JSON array. The repository's raw-first public HTTP client therefore receives one additive opt-in capability in 19D-A: existing callers remain object-only by default, while this endpoint explicitly requests `top_level_container="array"`.

The candle endpoint does **not** provide an exchange publication timestamp for the completed bucket comparable to Kraken PostTrade `publication_ts`. Therefore 19D-A can test deterministic completed-bucket reconstruction for Coinbase, but it does not claim that the historical candle reveals the exact moment that final bucket value first became visible live. The completed-bucket end-time rule is the frozen causal boundary under audit; publication-time parity remains an explicit limitation.

### Kraken Spot

Candidate historical source ID:

`kraken.spot.public_rest.posttrade.btc_usd.v1`

Endpoint:

`GET https://api.kraken.com/0/public/PostTrade`

Official documentation:

`https://docs.kraken.com/api/docs/rest-api/get-post-trade`

Documented properties relevant to 19D-A:

- `symbol=BTC/USD` filters the pair;
- `from_ts` and `to_ts` bound the requested trade history;
- up to 1,000 trades are returned per request;
- trades are returned in ascending timestamp order;
- `last_ts` is documented as the cursor for the next batch;
- each trade includes both engine `trade_ts` and market-data `publication_ts`.

The live 19C Kraken source remains the PreTrade BBO endpoint documented at:

`https://docs.kraken.com/api/docs/rest-api/get-pre-trade`

Each bid and ask price level carries its own `publication_ts`. Therefore 19D-A re-reads preserved 19C raw records and measures bid-age and ask-age separately instead of treating a successful request or the newer side's timestamp as sufficient evidence of whole-midpoint freshness.

## Historical reconstruction semantics

For a KXBTCD decision state at UTC timestamp `T`, define the most recent **fully completed** one-minute bucket.

Example:

`T = 12:34:37 UTC`

The current minute `[12:34:00, 12:35:00)` is still incomplete and is prohibited.

The current historical materialization bucket is:

`[12:33:00, 12:34:00)`

The exact five-minute lookback bucket is:

`[12:28:00, 12:29:00)`

The bucket starts therefore differ by exactly 300 seconds.

No observation from the incomplete current minute may be used.

### Coinbase materialization

Use the official one-minute candle whose start exactly equals the required bucket start.

Price semantic:

`S_CB = candle close = documented last trade in the completed bucket`

If the exact bucket is absent, Coinbase is unavailable for that required minute. Do not interpolate or carry an older candle forward.

### Kraken materialization

Fetch the exact one-minute trade window from PostTrade and preserve every request raw-first.

Within the required bucket, select the latest trade by `trade_ts` only among trades satisfying:

`publication_ts <= KXBTCD decision timestamp`

This prevents a trade that existed in engine time but was not yet published to market data by the decision state from leaking backward into the historical feature.

If no such trade exists, Kraken is unavailable for that required minute.

## Sampling frame

19D-A deliberately reuses the exact **288 outcome-blind KXBTCD snapshot times** from canonical 19C run:

`collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250`

This gives a direct live-versus-historical source-quality comparison without opening outcomes or inventing a new timing grid.

For each snapshot, the audit requests/materializes:

1. the last fully completed one-minute bucket; and
2. the exact one-minute bucket five minutes earlier.

Repeated target minutes are fetched once and reused with immutable raw lineage.

## Source-quality dimensions kept separate

### 1. Request/transport availability

A network/API request must succeed and its raw archive must persist before transformation.

For 19D-A, transport/API failure aborts the audit rather than being counted as missing historical market data. The purpose is to test native historical reconstruction, not to confound it with a transient audit-run transport failure.

### 2. Local first-seen freshness

Local first-seen age is meaningful for data received live by the machine and is measured with local monotonic time.

19D-A reuses the 19C local-first-seen ages for the exact 288 live states. It does **not** fabricate local-first-seen timestamps for historical downloads performed after the fact.

A numerical live staleness threshold remains unfrozen until 19D-B.

### 3. Exchange/source-event freshness

For Coinbase live 19C data, measure age from the source `time` field to the KXBTCD state.

For Kraken live 19C data, recover best-bid and best-ask `publication_ts` separately from the preserved raw response.

Conservative Kraken BBO publication age is:

`max(bid publication age, ask publication age)`

This is intentionally different from using the more recently updated side.

For historical Kraken trades, also record:

`publication lag = publication_ts - trade_ts`

and require publication by the original KXBTCD decision timestamp.

### 4. Cross-source agreement

When both historical sources materialize the same required minute, measure:

`D_bps = |S_CB - S_KR| / ((S_CB + S_KR)/2) * 10000`

19D-A records the distribution. It does **not** choose the final disagreement threshold.

### 5. Causal five-minute alignment

The lookback bucket must be the exact completed one-minute bucket five minutes before the current completed bucket.

Frozen 19D-A rules:

- exact bucket only;
- no future interpolation;
- no nearest-absolute observation;
- no carry-forward of a missing bucket;
- no use of an incomplete current minute.

This is stricter and more reproducible than a generic nearest-observation tolerance.

## Live versus historical comparison

19D-A also compares each reconstructed current-minute price with the contemporaneous 19C live BBO midpoint from the same source family.

This diagnostic answers:

> How different is the simple historically reproducible price definition from the live BBO definition we previously audited?

A small or large gap is descriptive only. It is not a model score and cannot be used to tune Candidate E in 19D-A.

## Exact outputs

The collector writes:

- `historical_materialization_rows.csv` â€” one row per 19C KXBTCD snapshot;
- `structural_exclusions.csv` â€” exact source/minute reconstruction failures;
- `summary.csv` â€” coverage and percentile diagnostics;
- raw Coinbase historical responses;
- raw Kraken historical responses;
- runtime events;
- standard collection manifest.

Summary distributions include p50, p90, p95, p99, and max for relevant quality variables so tails remain visible.

## Fail-closed conditions

The audit stops rather than guessing on:

- changed 19D-A design fingerprint;
- missing canonical 19C parent artifacts;
- wrong parent snapshot count or ordering;
- missing required 19C raw references;
- malformed or ambiguous parent raw responses;
- API/transport errors during historical collection;
- raw-persistence failure;
- malformed Coinbase candles;
- conflicting duplicate candle data;
- malformed Kraken PostTrade response;
- non-chronological Kraken trades;
- Kraken `publication_ts < trade_ts`;
- non-advancing/repeated Kraken pagination cursor;
- pagination exceeding the bounded safety guard;
- runtime-event persistence failure;
- manifest failure;
- any outcome/model/execution field appearing in derived materialization rows.

Missing native market data for an exact required minute is recorded as a structural exclusion rather than imputed.

## Deliberately not frozen in 19D-A

19D-A does not freeze:

- final E1 source allow-list;
- Coinbase-primary vs Kraken-primary vs deterministic consensus;
- local-first-seen staleness threshold;
- source-event/publication freshness threshold;
- cross-source disagreement threshold;
- Candidate-E formula;
- Candidate-E feature set;
- E1/E2/E3 event counts;
- E1/E2/E3 calendar requirements;
- model advancement gate;
- execution rules.

Those choices belong to 19D-B after this audit is complete and reviewed outcome-blind.

## Facts, assumptions, hypotheses, unresolved questions

### Facts

- 19C completed with 288 KXBTCD snapshots and no outcome access.
- Coinbase officially provides one-minute historical product candles whose `close` is the bucket's last trade.
- Coinbase warns that historical candle intervals with no ticks may be absent.
- Kraken PostTrade provides bounded historical trades with both execution and publication timestamps.
- Kraken PreTrade top-book levels carry separate bid/ask publication timestamps.
- Neither official source establishes that historical candles/trades are identical to a historical BBO snapshot.
- Coinbase historical candles do not expose a bucket publication timestamp, so exact historical first-publication timing is not reconstructible from that endpoint alone.

### Assumptions

- A fully completed one-minute bucket is a sufficiently conservative first historical baseline for Candidate-E research.
- The official endpoint responses remain consistent with the reviewed documentation during the audit.

### Hypotheses

- Exact completed-minute BTC state will be available for nearly all 19C snapshot times on both exchanges.
- Historical Coinbase/Kraken completed-minute prices will agree closely enough to support a simple independent-BTC baseline without third-party historical microstructure data.

These hypotheses are not accepted until measured.

### Unresolved questions

- Which exact source or deterministic consensus should Candidate E use?
- What quality thresholds are defensible from the observed tails?
- Is one-minute completed-bucket state sufficiently close to live state for the first independent-BTC hypothesis?
- What minimum E1/E2/E3 calendar/event coverage should be frozen?
- Should `d_BTC`, `r_5m`, both, or a smaller menu be frozen after source semantics are accepted?

## Safety

Checkpoint 19D-A remains read-only.

Prohibited:

- Candidate-E fitting;
- outcome access;
- Checkpoint-17 terminal use;
- paper execution;
- demo execution;
- real-money execution;
- order placement/cancellation;
- transfers;
- silent live model rewriting.

A successful 19D-A audit establishes only source-quality/historical-materialization evidence. It cannot establish predictive value, edge, profitability, calibration quality, or execution suitability.

<!-- CHECKPOINT19D_A_RESULTS_20260817 -->
## Completed outcome-blind audit result â€” 2026-08-17

Run: `collect_kxbtcd_independent_btc_historical_materialization_20260817T061908727611Z_f90d93fc`

Frozen protocol fingerprint:
`b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`

Frozen audit-design fingerprint:
`023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c`

The audit completed across all 288 frozen Checkpoint-19C snapshots and 291 unique
completed-minute targets. It remained outcome-blind: no KXBTCD outcomes were
accessed, Candidate E was not fitted, no Candidate-E formula was frozen, no
predictive threshold or evidence-cohort size was selected, and no execution was
performed.

### Historical reconstructibility

- Coinbase current completed-minute coverage: 288/288 = 100%.
- Coinbase exact five-minute lookback coverage: 288/288 = 100%.
- Kraken current completed-minute coverage: 287/288 = 99.6528%.
- Kraken exact five-minute lookback coverage: 287/288 = 99.6528%.
- Both-source current coverage: 287/288 = 99.6528%.
- Both-source current + exact-five-minute-pair coverage: 286/288 = 99.3056%.

The two row-level exclusions came from one unique Kraken minute:
`2026-08-16T09:09:00Z` through `09:10:00Z`. The preserved raw Kraken PostTrade
response for that exact window returned HTTP 200 with `count=0` and `trades=[]`.
Therefore the hole was a genuine no-trade minute, not a transport failure,
parser failure, or publication-causality rejection. The frozen rule remains:
an exact missing minute is unavailable; do not carry an older trade forward and
do not interpolate.

### Cross-source agreement

For current completed-minute prices where both sources were available
(`n=287`), absolute Coinbase/Kraken disagreement was:

- p50: 0.7216 bp
- p90: 2.2931 bp
- p95: 2.9591 bp
- p99: 4.4667 bp
- max: 6.0368 bp

For exact five-minute lookback prices (`n=287`):

- p50: 0.7302 bp
- p90: 2.2931 bp
- p95: 2.9591 bp
- p99: 4.4667 bp
- max: 6.0368 bp

These are descriptive source-quality measurements only. They do not select a
final disagreement threshold.

### Historical-versus-live comparison

Coinbase historical completed-minute close versus the 19C live BBO midpoint
(`n=288`): p50 0.2960 bp, p95 4.1034 bp, p99 7.3645 bp, max 23.0664 bp.

Kraken historical last trade versus the 19C live BBO midpoint (`n=287`):
p50 0.00794 bp, p95 3.7229 bp, p99 6.6930 bp, max 27.0957 bp.

These are not expected to be identical constructions. Coinbase historical
candles and Kraken historical trades are not historical BBO archives.

### Live freshness lesson carried forward from 19C raw data

Kraken local request freshness was superficially strong
(local-first-seen age p50 1.109 s), but conservative whole-BBO publication age
was materially older: p50 22.012 s, p95 49.175 s, p99 354.472 s, and max
6120.316 s. Therefore transport/request success and local receive freshness must
not be treated as equivalent to source-event freshness.

### Implementation hotfix discovered during the audit

Kraken PostTrade can return an empty pagination cursor (`last_ts=""`) on a
non-full/empty page. The parser now normalizes blank `last_ts` to no cursor.
Malformed non-string cursors still fail closed, and a full 1000-trade page
without a usable cursor still fails closed. This changed parser compatibility,
not the frozen research design.

Focused regression after the fix: 7 passed.
Repository-wide regression after the fix: 732 passed, 22 subtests passed.
Source-registry validation remained PASS with 18 registered sources.

### 19D-A interpretation

19D-A establishes that outcome-blind independent-BTC historical
materialization is highly feasible under the frozen exact-minute construction.
It does **not** establish predictive value, trading edge, profitability, or a
final Candidate-E source policy. Checkpoint 19D-B must freeze the exact E1
source allow-list/construction and source-quality gates using only this
outcome-blind source/history evidence before any E1 outcomes are used.
