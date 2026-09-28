# Project State

Last updated: 2026-08-17 (America/Chicago; live evidence timestamps use UTC)

## Current research arc (added 2026-09-28)

The sections below describe the Phase 1 data foundation as of 2026-08-17 and remain accurate
for that scope. Since then the project ran a broad search for a tradeable edge on Kalshi and
closed it. That arc is documented separately and supersedes any strategy-direction statement
below:

- `KALSHI_EDGE_SEARCH_CLOSEOUT.md` - eleven closed directions, the single mechanism behind
  them, and the six weighting/normalisation artifacts that are the most reusable output.
- `KALSHI_API_SCHEMA_REFERENCE.md` - verified API field semantics. Read before writing any
  new Kalshi analysis; five of its entries were guessed wrong first and each produced a
  confident false result.
- `KALSHI_WEATHER_SETTLEMENT_RETRACTION.md` - a +1.00F "edge" retracted as a proxy error.
- `KALSHI_MAKER_FEE_CORRECTION.md` - makers pay nothing on 98.9% of the exchange.
- `KALSHI_STRUCTURAL_ARBITRAGE_SCREEN.md` and `KALSHI_WEATHER_MARKET_MAKING_RESULT.md`.
- `KALSHI_WEATHER_MAKER_PREREGISTRATION.md` - **the one live hypothesis.** Rule and evaluator
  both frozen 2026-09-27. Evaluate no earlier than 2026-11-01. Costs no capital.
- `CROSS_VENUE_PERP_FUNDING_SURVEY.md` - open survey, no capital committed.

Scripts: `scripts/kalshi_research/` (standard library only, no dependency on `src/`).

No document in that arc establishes executable market edge or profitability.

## Current phase

Phase 1 — Read-only Kalshi Data Foundation.

The raw REST archive, run-manifest integrity, raw-to-derived lineage, and structured runtime observability checkpoints are implemented, validated on the user's Windows Python 3.11 environment, committed, and pushed.

## Canonical implementation checkpoint

- Branch: `main`
- Implementation commit: `0c34e0f` — `Add structured runtime observability`
- At implementation closeout, local `main`, `origin/main`, and `origin/HEAD` all pointed to `0c34e0f`.
- `git status --short` returned no output after the push.
- This documentation closeout is a follow-up to that implementation commit and does not change runtime behavior.
- Runtime raw data, runtime-event logs, derived CSV outputs, and run manifests remain outside Git.

## What currently works

### Public read-only collection

- Public, unauthenticated Kalshi REST market discovery
- KXBTC15M market-family filtering
- Public order-book retrieval
- Conversion of bid-only YES/NO levels into derived best bids, asks, and spreads

### Raw preservation and timing

- Append-only raw JSONL persistence before transformation
- UTC and monotonic request timing
- Raw preservation of successful responses and transport, HTTP, JSON, and top-level shape errors
- Response body byte counts and SHA-256 digests
- Source timestamp indexing
- Fail-closed behavior when required raw persistence fails

### Run manifests and artifact integrity

- Atomic per-run lifecycle manifests
- Sanitized arguments, Git/environment identity, source sessions, artifact hashes, counts, and lifecycle state
- Backward-compatible validation of historical `collection_run_manifest.v1`
- Current collectors produce `collection_run_manifest.v2`
- Offline validation of raw archives, derived CSV files, runtime-event files, and manifest reconciliation

### Raw-to-derived lineage

- Exact immutable raw-record references carried with successful API responses
- `run_id`, `raw_source`, `raw_session_id`, and `raw_request_id` in every derived order-book row
- Bidirectional identifier-level reconciliation between raw order-book records and derived rows

### Structured runtime observability

- One append-only `runtime_event.v1` JSONL stream per collector run under `logs/runtime/YYYY/MM/DD/<run_id>.jsonl`
- Stable event names and `info`, `warning`, `error`, and `critical` severities
- UTC and monotonic timestamps
- One-based run-local event sequence numbers
- Run ID, collector identity, sanitized context, optional structured errors, and optional exact raw-request correlation
- Collector lifecycle events
- API request success and failure events
- Required raw-persistence failure events
- Endpoint-specific structural validation failure events
- Fail-closed behavior when required runtime-event persistence fails

### Endpoint structural validation

After successful raw persistence, the current client validates the documented structures needed by the collectors:

- `/markets` market-list container
- Market-list item object shape
- Pagination cursor text-or-null shape
- `/markets/{ticker}` market object
- `/markets/{ticker}/orderbook` `orderbook_fp` object
- Present YES/NO side list shape
- Two-value fixed-point string order-book level shape

These checks validate structure only. They do not establish settlement authority or assign undocumented economic meaning.

## Accepted observability evidence

### Canonical automated test

- Date: 2026-08-03 local
- Environment: user's Windows repository, Python 3.11 virtual environment
- Command: `.\.venv\Scripts\python.exe -m pytest -q`
- Result: `35 passed in 25.71s`

### Live scanner smoke run

- Local date: 2026-08-03
- UTC artifact date: 2026-08-04
- Run ID: `scan_btc_markets_20260804T031830261714Z_30886e6c`
- Returned ticker: `KXBTC15M-26AUG032330-30`
- Result: 1 raw record, 0 raw error records, 1 runtime-event file, 3 runtime events, 0 runtime error events
- Derived CSV files: 0
- Offline validation: `PASS`

### Live order-book smoke run

- Local date: 2026-08-03
- UTC artifact date: 2026-08-04
- Ticker: `KXBTC15M-26AUG032330-30`
- Run ID: `record_orderbook_20260804T032038103539Z_5993bd6f`
- Duration and interval: 20 seconds at 2-second intervals
- Result: 10 raw records, 0 raw error records, 1 derived CSV, 10 derived rows, 1 runtime-event file, 12 runtime events, 0 runtime error events
- Offline validation: `PASS`
- Safety result: no orders were placed

The recorder manifest recorded `git_worktree_dirty_at_start: true` because the live validation occurred after applying the replacement files but before committing them. The subsequent clean push at `0c34e0f` resolved that expected implementation-validation state.

## Current safety state

- Public, read-only data access only
- No authentication or account access
- No API keys or private keys
- No order placement or cancellation
- No demo execution
- No real funds

## Known limitations

- No complete source registry exists.
- The official KXBTC15M settlement authority and exact settlement-index procedure have not yet been confirmed and recorded.
- The official Kalshi documentation currently presents an order-book authentication inconsistency that requires explicit reconciliation.
- Endpoint checks cover only structures used by the current collectors; there is no full endpoint-schema registry.
- No synchronized external BTC reference feed exists.
- No WebSocket streaming, sequence-gap detection, stale-feed policy, or clock-health gate exists.
- No runtime-log retention, compression, rotation, dashboard, metrics service, or alerting exists.
- No fee, depth, slippage, latency, partial-fill, or missed-fill model exists.
- No probability model, calibration report, chronological backtest, or paper execution exists.

## Next three tasks

1. Review current repository code and representative KXBTC15M source fields, then define a minimal source-registry contract without assigning undocumented semantics.
2. Confirm and document the official KXBTC15M settlement source and reconcile the order-book authentication-documentation inconsistency using official Kalshi sources.
3. Define fail-closed source-quality states for stale feeds, clock errors, incomplete responses, and schema drift before designing an external BTC reference-feed collector.

## Current blocker

No active engineering blocker prevents source-registry work. Modeling remains blocked by the unresolved official settlement authority, incomplete source-quality policy, and absence of a synchronized external BTC reference source.

<!-- PRESELECTION_CLOSEOUT_20260814 -->
## 2026-08-14 - KXBTCD vs. BTC perpetual preselection closeout

The read-only preselection gate comparing KXBTCD with Kalshi BTC perpetuals is complete enough to choose the next research architecture.

### Accepted architecture

Use a **shared BTC-state research layer with separate product heads**, implemented sequentially.

- **Primary validation head: KXBTCD.**
  - Target: settlement probability conditioned on BTC state, strike, and time-to-close.
  - Reason: substantially broader labeled regime coverage and simpler terminal-risk semantics.
- **Secondary read-only head: KXBTCPERP.**
  - Target: forward return / volatility / basis behavior at predeclared horizons.
  - Reason: materially tighter continuous microstructure and lower observed taker transaction costs, but shorter product history plus funding, margin, and liquidation mechanics.
- Share only raw/reference feeds and clearly defined BTC-state features at first.
- Do **not** use a joint multitask loss, share product labels, or assume one product's model calibrates the other.
- Keep valuation/forecasting separate from product-specific decision and execution-economics layers.
- Current phase remains read-only; no order placement, cancellation, transfers, demo execution, paper broker, or real-money execution is authorized.

### Evidence accepted

#### KXBTCD historical/regime coverage

Saved read-only event pages produced a lower bound of:

- 4,000 unique settled event tickers
- 4,000 events with `strike_date`
- 2026-02-24 08:00 UTC through 2026-08-14 03:00 UTC
- 172 distinct UTC day blocks
- 25 distinct UTC week blocks
- 7 UTC month blocks
- 99.3748% of adjacent saved events separated by exactly one hour
- 25 observed five-hour gaps

The 4,000 count is a lower bound because the bounded pagination audit stopped with a cursor still present. It is **not** treated as an effective IID sample size.

#### KXBTCPERP historical/regime coverage

Read-only perp evidence produced:

- 71 daily candles spanning 71 unique UTC days
- 1,322 minute candles in the bounded 24-hour sample
- 214 funding records with all 213 adjacent intervals exactly eight hours
- one-minute return ACF: lag 1 = 0.0412, lag 5 = 0.0114, lag 15 = -0.0237, lag 60 = 0.0092
- one-minute squared-return ACF: lag 1 = 0.1278, lag 5 = 0.1927, lag 15 = 0.0690, lag 60 = 0.0149
- positive-ACF ESS diagnostics of about 506.5 for minute returns and about 174.9 for squared returns from 1,321 return observations

Those ESS values are diagnostics only; they are not certified effective sample sizes and must not be generalized beyond the bounded sample.

#### Same-window live capture

Run:

`analysis/btc_preselection_paired_capture/20260814T050145Z`

completed:

- 120-second synchronized window
- 60 paired REST cycles
- 30 perp-first / 30 KXBTCD-first cycles
- Coinbase/Kraken child probe return code 0
- BRTI child probe return code 0
- KXBTCPERP two-sided in 60/60 cycles
- both selected KXBTCD targets two-sided in 60/60 cycles
- median paired REST request-start skew: 391 ms

KXBTCPERP during the window:

- median spread: 0.3157 bp
- p95 spread: 0.4736 bp
- max spread: 0.7893 bp
- BTC-equivalent mid range: $14.50

Selected KXBTCD states during the same window:

- about 1-hour target: 1-cent spread in all 60 cycles; midpoint range 7 percentage points
- about 16-hour target: median 1-cent spread, p95/max 2 cents; midpoint range 0.5 percentage points
- both targets retained substantial quoted contract size throughout the bounded window

This confirms that KXBTCD liquidity is strongly **time-to-close and strike dependent**, while the perp offers a continuously concentrated book.

### Clock-health finding

The BRTI stream had 120 ticks and zero sequence gaps. Its apparent negative Kalshi-to-local latency was traced to the Windows wall clock: `w32tm /stripchart` showed the local PC roughly 0.17 seconds behind `time.windows.com`.

Therefore:

- sequence/order evidence based on local monotonic time remains usable;
- broad same-window product comparison remains usable;
- sub-second cross-feed lead/lag claims are **not authorized** from the current wall-clock setup;
- future latency/lead-lag research must either improve clock synchronization or explicitly estimate/correct clock offset with an accepted policy.

### Preselection conclusion

Neither product is rejected.

KXBTCD is selected as the **first modeling/validation target** because its historical labeled outcome coverage is materially broader and the binary settlement task is easier to validate cleanly.

KXBTCPERP is retained as a **second read-only product head and microstructure benchmark** because the live book is consistently tighter and its prospective transaction-cost structure is more favorable for frequent entry/exit research. Perp modeling must explicitly include funding, margin, liquidation risk, maintenance windows, and shorter-history uncertainty.

The next modeling work must begin with simple separately testable baselines rather than a joint complex model.

## Checkpoint 12 authoritative state — 2026-08-15

KXBTCD pre-outcome materialization v3 is accepted and frozen.

- Materialization contract: kxbtcd_preoutcome_materialization.v3
- TTC anchors: 55m, 50m, 45m, 40m, 35m, 30m
- Quote-staleness limit: 60 seconds
- Selected events: 296
- Structural markets: 1,480
- Attempted states: 8,880
- Available states: 6,378 (71.82%)
- Dataset events: 295
- Train: 175 events / 4,645 rows
- Validation: 56 events / 719 rows
- Locked test: 64 events / 1,014 rows
- Locked-test outcome labels opened: 0
- Split fingerprint: 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
- Dataset fingerprint: d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a

The earlier long-horizon anchor design is superseded because most selected KXBTCD markets have an approximately 60-minute lifecycle.

Next work must use this exact frozen dataset and split, attach outcomes only to train and validation first, fit the predeclared raw-midpoint baseline and Candidate B, and apply the frozen validation gate before any locked-test outcomes are opened.

Execution remains out of scope.

<!-- CHECKPOINT13_CANDIDATE_B_RESULT_20260815 -->
## Checkpoint 13 authoritative state — 2026-08-15

Checkpoint 13 completed the predeclared KXBTCD Candidate-B train/validation evaluation against the frozen Checkpoint-12 dataset. Candidate B **failed** its validation gate, so the locked test remains sealed.

### Canonical evaluation run

- Run: `collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631`
- Frozen pre-outcome run: `collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d`
- Dataset fingerprint: `d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a`
- Split fingerprint: `28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503`
- Candidate-B fingerprint: `e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3`
- Train/validation market labels attached: 1,050
- New HTTP requests: 1,050
- Recovered prior outcomes: 0
- Authentication used: no
- Orders placed: 0

### Pre-label safety evidence

- Final canonical regression before outcome collection: `631 passed, 22 subtests passed in 16.10s`
- Zero-network preflight: PASS
- Planned train market requests: 822
- Planned validation market requests: 228
- Planned locked-test market requests: 0
- Locked-test deny-list markets: 320
- Prior CP13 exposure manifests before collection: 0
- Locked-test outcomes opened before collection: 0

Two implementation defects were found and corrected before outcome collection:

1. the deterministic Newton solver used a gradient tolerance stricter than practical double-precision accumulation on a synthetic shrinkage test; the tolerance was relaxed from `1e-10` to `1e-8` without changing the frozen objective, features, lambda grid, or gate;
2. the preflight initially treated manifest path descriptors as plain strings instead of the repository's structured stored-path objects; artifact and recovery readers were corrected and regression-tested.

Neither defect exposed any train, validation, or locked-test outcomes.

### Validation result

Raw Kalshi midpoint benchmark:

- event-weighted validation log loss: `0.14231643239449182`
- event-weighted validation Brier: `0.04007408198822001`

Selected Candidate B (`lambda = 0.1`):

- event-weighted validation log loss: `0.14556019289436192`
- event-weighted validation Brier: `0.040404125365432336`
- raw-minus-Candidate-B log-loss delta: `-0.003243760499870102`
- raw-minus-Candidate-B Brier delta: `-0.00033004337721232596`

The primary gate required Candidate B to have **strictly lower** validation event-weighted log loss than the raw midpoint. It did not. Candidate B therefore fails.

Selected coefficients:

```text
beta0 = 0.094997254017608834
beta1_market_logit = 1.1149509916339024
beta2_strike_log_ratio = -0.060557892307059664
beta3_time_log1p_hours = -0.001891300947166137
```

The selected fit converged in 6 Newton iterations.

### Consequences

- Candidate B does not advance to the locked test.
- Locked-test outcomes opened: **0**.
- No train+validation final refit was performed.
- Candidate C was not authorized by Checkpoint 13.
- The 56-event validation partition is now outcome-exposed and must not be described as untouched for future candidate design.
- The 64-event locked-test partition remains outcome-sealed.
- Any future candidate or regime-conditioned research must be separately predeclared under D-013 and must define a new development/selection protocol before any locked-test labels are opened.
- This result is evidence about predictive scoring for this frozen Candidate-B specification only. It does not establish trading profitability or execution edge.

<!-- CHECKPOINT14_STATE_20260815 -->
## Checkpoint 14 authoritative state â€” 2026-08-15

Checkpoint 14 completed Candidate-B failure/regime diagnostics using only the already outcome-exposed Checkpoint-13 train+validation rows and froze a future Candidate-C development specification. Candidate C was **not fit** and the 64-event locked test remains outcome-sealed.

### Canonical diagnostic evidence

Final local analysis directory:

`data/analysis/kxbtcd_candidate_b_failure_analysis/20260815T214404Z`

Frozen identities:

```text
CP13 run = collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631
CP12 pre-outcome run = collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d
dataset = d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a
split = 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
Candidate B = e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3
Candidate-C predeclaration = d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322
```

Development-only diagnostic scope:

- 231 already outcome-exposed events / 5,364 rows;
- 58 UTC-week units;
- raw development log loss: `0.15538587480307692`;
- Candidate-B development log loss: `0.14462803684008735`;
- raw-minus-Candidate-B delta: `+0.010757837962989569`;
- raw development Brier: `0.037913401220456798`;
- Candidate-B development Brier: `0.035219333463201045`;
- raw-minus-Candidate-B Brier delta: `+0.0026940677572557525`;
- Candidate-B better/worse/tie event signs: `215 / 16 / 0`.

This pooled development improvement does **not** reverse D-014 or the Checkpoint-13 validation failure. The 56-event validation block was the predeclared selection/gate block and is now exposed development data.

### Failure-pattern interpretation

The diagnostics show concentrated, regime-dependent errors rather than broad Candidate-B underperformance:

- original validation remained negative despite Candidate B being better on 51/56 events;
- chronological blocks B0-B3 were positive, while B4 was negative;
- every TTC-anchor slice was directionally positive, so TTC was not supported as the main failure dimension;
- the B4 failure was concentrated in the tightest spread bucket: `(0,0.01]` had log-loss delta `-0.007979`, while all wider B4 spread buckets were positive;
- probability-band behavior depended on spread. In particular, `q_market=[0.4,0.5)` remained materially negative at wider spreads, while several `q_market>0.5` wide-spread cells were strongly positive.

The evidence therefore supports testing probability-dependent spread recalibration rather than the earlier draft TTC interaction. These are exploratory diagnostics only; they do not establish profitability or execution edge.

### Final Candidate-C predeclaration

Frozen future model:

`kxbtcd_market_spread_interaction_logistic.v1`

Learned continuous features:

1. `market_logit`;
2. `spread`;
3. `market_logit_x_spread`.

Candidate C uses fit-fold-only standardization, deterministic damped Newton, and the frozen L2 grid `0.01, 0.1, 1, 10`.

Future development selection is predeclared as five contiguous chronological UTC-week blocks with four rolling-origin score folds. Lambda is selected by pooled out-of-fold event-weighted log loss. Advancement requires all of:

1. strictly lower pooled OOF log loss than raw midpoint;
2. pooled OOF Brier no worse than raw midpoint; and
3. strictly lower log loss than raw midpoint in at least 3 of 4 score blocks.

Before any Candidate-C fit, the exact outcome-blind week-to-block mapping must be serialized and SHA-256 fingerprinted.

### Validation and safety

Final canonical Windows evidence before closeout:

```text
focused CP14 tests: 7 passed in 0.14s
full regression: 638 passed, 22 subtests passed in 17.24s
network requests during final diagnostic: 0
locked-test outcomes opened: 0
Candidate C fit performed: no
orders placed: 0
execution enabled: no
```

`RISK_POLICY.md` is unchanged. Read-only authorization remains unchanged.

### Next checkpoint

Checkpoint 15 may implement and run **Candidate-C development evaluation only** under the exact frozen predeclaration. It must freeze the deterministic week-to-block map before fitting. The locked test remains sealed unless a later explicit checkpoint follows a passed development gate and authorizes the one-time terminal evaluation.

<!-- CHECKPOINT15_STATE_20260815 -->
## Checkpoint 15 authoritative state — 2026-08-15

Checkpoint 15 completed the frozen Candidate-C rolling-origin development evaluation. Candidate C **passes the development gate**, but the 64-event locked test remains outcome-sealed.

### Frozen provenance

- Starting `main`: `6f619cedd4b76197e21086290c3eb27db8f6c521`.
- Candidate C: `kxbtcd_market_spread_interaction_logistic.v1`.
- Candidate-C predeclaration fingerprint: `d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322`.
- Exact outcome-blind week-map fingerprint: `6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4`.
- Development scope: 231 exposed events / 5,364 rows / 58 UTC weeks.
- Week blocks: 12/12/12/11/11 weeks in B0-B4.
- Block event counts: B0=47, B1=48, B2=48, B3=44, B4=44.
- Block row counts: B0=922, B1=1436, B2=1426, B3=1104, B4=476.

### Development result

- Selected lambda: `0.01`.
- OOF score scope: 184 events / 4,442 rows across B1-B4.
- Raw pooled OOF log loss: `0.14654989561790596`.
- Candidate-C pooled OOF log loss: `0.076775557277925191`.
- Raw-minus-Candidate-C log-loss delta: `+0.069774338339980771`.
- Raw pooled OOF Brier: `0.035093720284958003`.
- Candidate-C pooled OOF Brier: `0.019029926328616251`.
- Raw-minus-Candidate-C Brier delta: `+0.016063793956341752`.
- Score-block log-loss wins: `4/4`.
- Candidate-C better/worse/tie events: `119/65/0`.
- Frozen development advancement gate: **PASS**.

The sign count is diagnostic only; it does not replace proper scoring. Candidate B remains rejected under D-014.

### Validation and safety

```text
focused CP15 tests: 9 passed in 0.14s
full regression: 647 passed, 22 subtests passed in 16.15s
source registry: PASS
rolling-origin Candidate-C fits: 16
network requests: 0
locked-test outcomes opened: 0
locked-test evaluation: no
full-development final fit: no
orders placed: 0
execution enabled: no
```

`RISK_POLICY.md` is unchanged.

### Next checkpoint

Checkpoint 16 may freeze `lambda=0.01`, freeze full-development scaling, and perform/fingerprint exactly one final Candidate-C fit on all 231 exposed development events. It must keep the locked test sealed. A separate Checkpoint 17 is required for the one-time terminal locked-test evaluation.

<!-- CHECKPOINT16_STATE_20260815 -->
## Checkpoint 16 authoritative state — 2026-08-15

Checkpoint 16 completed the Candidate-C full-development preprocessing freeze and exactly one final fit on all 231 already outcome-exposed development events. The 64-event locked test remains outcome-sealed.

### Frozen final-fit provenance

- Candidate: `kxbtcd_market_spread_interaction_logistic.v1`.
- Candidate-C predeclaration fingerprint: `d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322`.
- Frozen week-map fingerprint: `6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4`.
- Selected lambda: `0.01`; no further lambda search was performed.
- Development scope: 231 events / 5,364 rows.
- Full-development freeze fingerprint: `d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3`.
- Final model fingerprint: `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`.

### Frozen full-development scaler

Feature order:

`market_logit`, `spread`, `market_logit_x_spread`

Means:

`0.053181741488340019`, `0.17633482475764356`, `0.006538779033484236`

Population standard deviations:

`3.2168919026338747`, `0.21442166056343254`, `0.32259958139407791`

Scaling is ordinary row-level population z-scaling over the full development rows. Event weighting remains an objective/metric rule and was not applied to preprocessing.

### Frozen final coefficients

Coefficient order:

`intercept`, `market_logit_z`, `spread_z`, `market_logit_x_spread_z`

Coefficients:

`0.10194908608881083`, `2.0752015786995628`, `0.017616475889079299`, `1.9669079012140323`

The deterministic damped-Newton fit converged in 6 iterations with penalized development objective `0.1226739682345051`. This is an in-development penalized training objective, not a new out-of-sample score.

### Validation and safety

```text
focused CP16 tests: 15 passed in 0.73s
full regression: 653 passed, 22 subtests passed in 19.49s
source registry: PASS
final artifact validation: PASS
final-fit attempts: exactly 1 completed
network requests: 0
locked-test outcomes opened: 0
locked-test evaluation: no
orders placed: 0
execution enabled: no
```

Candidate B remains rejected under D-014. Checkpoint 16 adds no terminal evidence and does not establish profitability or executable edge.

### Next checkpoint

A separate Checkpoint 17 may authorize the one-time terminal evaluation of the 64 locked-test events using only the already frozen final model and preprocessing state. No redesign or retuning is permitted after the locked test is opened.

<!-- CHECKPOINT17_PREOUTCOME_FREEZE_20260815 -->
## Checkpoint 17 Stage A authoritative state — 2026-08-15

The one-time Candidate-C terminal locked-test **procedure is frozen**, but no locked-test outcome has been opened.

- Source baseline before Stage-A changes: `9c82518285c9684636469cafd50fea8cca1ac4aa`.
- Candidate: `kxbtcd_market_spread_interaction_logistic.v1`.
- Full-development preprocessing fingerprint: `d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3`.
- Final model fingerprint: `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`.
- Terminal evaluation procedure fingerprint: `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`.
- The procedure fingerprint binds the exact Stage-B implementation SHA-256 hashes.
- Frozen terminal scope: 64 locked-test events / 1,014 pre-outcome rows.
- Exact outcome-blind market request allow-list count: 304.
- Benchmark: raw Kalshi midpoint `q_market`.
- Candidate inference inputs: frozen `q_market` and `spread` only.
- Primary metric: event-weighted log loss.
- Secondary metric: event-weighted Brier.
- Primary rule: Candidate-C terminal event-weighted log loss must be **strictly lower** than raw midpoint; an exact tie fails.
- Both models must be scored on the same locked-test rows.
- No refit, retuning, recalibration, feature change, preprocessing change, optimizer change, or lambda change is permitted.
- Stage-B collection must fail closed unless local `main` is clean and equals freshly fetched `origin/main`.
- Before the first terminal request, the full 64-event set is conservatively marked permanently exposed.
- A fresh second terminal attempt is prohibited; only recovery/resume of the same interrupted exposure is allowed.
- After exposure, these 64 events cannot be used for redesign or another untouched-test claim.
- Stage-A locked-test outcomes opened: **0**.
- Stage-A network requests: **0**.
- Orders placed: **0**.
- Execution remains prohibited.

Next action: close Stage A through the safe checkpoint closeout workflow, verify the new receipt plus clean synchronized repository, and only then authorize the Stage-B one-time terminal outcome opening.

<!-- CHECKPOINT17_TRANSPORT_AMENDMENT_20260815 -->
## Checkpoint 17 — interrupted terminal exposure and transport-only amendment

Stage B began from a clean synchronized repository under terminal-evaluation
fingerprint `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`. The original collector persisted 9
locked-test market labels, then failed closed when `/historical/markets/KXBTCD-26AUG0202-T55499.99` returned
HTTP 404. The terminal set remains permanently exposed. The operator diagnostic
reported only the persisted-label count; no label values were used to design
the repair.

Kalshi's observed `market_settled_ts` cutoff was `2026-06-16T00:00:00Z`. The frozen
request plan contains markets on both sides of that boundary, so the original
single historical-endpoint assumption was a transport bug.

Accepted repair:
- preserve the original Stage-A terminal freeze and its implementation-bound
  files unchanged;
- use separate amendment fingerprint `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`;
- recover already opened labels from raw archives and do not re-request them;
- for each still-missing frozen ticker, query `/markets/{ticker}` first and
  use `/historical/markets/{ticker}` only after HTTP 404;
- retain the exact 64 events, 1,014 rows, 304 market tickers, Candidate-C
  model, preprocessing, lambda, optimizer, event-weighted metrics, strict
  log-loss gate, and tie-fails rule.

The interrupted manifest is `data\manifests\2026\08\15\collect_kxbtcd_candidate_c_locked_test_20260815T224506878886Z_31832daa.json` with SHA-256
`9cbf18cc44933330c8d27ed000aa2c04015f1fb660aca13979ae6ec4253c5627`. No paper/demo/order/transfer/real-money path is enabled.

<!-- CHECKPOINT17_TERMINAL_RESULT_20260815 -->
## Checkpoint 17 terminal locked-test result — 2026-08-15

Checkpoint 17 is complete. The frozen Candidate-C terminal evaluation **FAILED**
the predeclared primary gate.

- Completed terminal run: `collect_kxbtcd_candidate_c_locked_test_20260815T225546640797Z_54081035`
- Terminal evaluation fingerprint: `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`
- Transport amendment fingerprint: `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`
- Final Candidate-C model fingerprint: `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`
- Locked test: 64 events / 1014 rows / 304 market labels
- Raw midpoint event-weighted log loss: `0.052191564366640519`
- Candidate-C event-weighted log loss: `0.068502780828836138`
- Raw-minus-Candidate-C log-loss delta: `-0.016311216462195618`
- Raw midpoint event-weighted Brier: `0.014139546080841911`
- Candidate-C event-weighted Brier: `0.014602932515903819`
- Primary gate: **FAIL**
- Tie rule: fail
- Locked-test set permanently exposed: yes
- Model refit / retune / recalibration: no / no / no
- Execution enabled: no
- Orders placed: 0

The first terminal attempt was interrupted after 9 labels because the original
collector used the historical-market endpoint for a live-tier August market.
The separately frozen transport-only amendment recovered those 9 labels and
collected the remaining 295 labels without changing model, preprocessing,
features, lambda, optimizer, scoring rows, metric definitions, primary gate,
tie rule, or test membership. The completed resume used 295
live-market requests and 103 historical
fallback requests.

**Interpretation boundary:** Candidate C does not advance under the frozen
terminal criterion. This result does not establish that no predictive signal
exists, and it does not establish profitability or execution suitability.
The 64-event terminal set is now permanently exposed and must not be used to
retune Candidate C, design a successor model, or support another untouched-test
claim.

### Next research boundary

Checkpoint 18, if started, must be designed without using the exposed 64-event
terminal block for tuning or advancement. Any successor candidate must rely on
development-only evidence and a genuinely new future holdout or other
predeclared untouched evaluation set. The project remains read-only.

<!-- CHECKPOINT18A_DESIGN_20260815 -->
## Checkpoint 18A started — Candidate-C development-only generalization-risk review

Checkpoint 17 remains permanently closed as a Candidate-C terminal FAIL. The exposed terminal block is not an input to Checkpoint 18.

Accepted Checkpoint-18A scope:
- use canonical Checkpoint-13 train+validation development evidence and canonical Checkpoint-15 rolling-origin artifacts only;
- analyze block/event/week stability, improvement concentration, stored-fold coefficient and prediction stability, sharpening behavior, feature conditioning, and temporal dependence;
- construct successor protocol layout candidates from development event/week identifiers only;
- perform no Candidate-C refit, successor fit, or successor hyperparameter search;
- load no Checkpoint-17 terminal rows, labels, features, predictions, residuals, or result artifact.

Exact successor features, tuning rules, nested chronological folds, instability thresholds, and advancement gates remain unresolved until the Checkpoint-18A diagnostic is reviewed. Execution authorization is unchanged.

<!-- CHECKPOINT18B_CANDIDATE_D_DESIGN_20260815 -->
## Checkpoint 18B — Candidate-D design frozen before fitting

Checkpoint-18A development-only review is accepted as design evidence. The successor is now frozen as `kxbtcd_market_logit_recalibration.v1` with predeclaration fingerprint `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`.

Candidate D is calibration-only:
- input: `q_market` only;
- model transform: 0.001-clipped market logit;
- formula: `logit(p_D)=market_logit+alpha+delta*market_logit`;
- raw benchmark nested at `alpha=0, delta=0`;
- no scaling, spread, interaction, regularization, or hyperparameter search.

The frozen development screen uses the outcome-blind seven-block UTC-week layout and five rolling-origin score folds B2-B6. All five score blocks contain 32 events. Passing requires strict pooled log-loss improvement, Brier no worse, at least four block wins, a latest-B6 win, positive median event delta, successful finite fits, and positive fitted market-logit slope in every fold.

No Candidate-D fit has been performed at this checkpoint. The 64-event Checkpoint-17 terminal block remains prohibited. Execution authorization is unchanged.

<!-- CHECKPOINT18C_CANDIDATE_D_DEVELOPMENT_20260815 -->
## Checkpoint 18C started — frozen Candidate-D development evaluation

Checkpoint 18B is closed and remotely synchronized. Candidate D remains `kxbtcd_market_logit_recalibration.v1` with predeclaration fingerprint `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`.

Checkpoint 18C is implementation/evaluation only:
- validate the outcome-blind seven-block map from frozen pre-outcome data first;
- fit exactly five rolling-origin Candidate-D folds;
- perform no hyperparameter search or specification change;
- score the seven frozen development conditions;
- load no Checkpoint-17 terminal data and make no network or execution calls.

A Checkpoint-18C PASS, if observed, is only an exposed-development stability result and cannot be represented as untouched validation.

<!-- CHECKPOINT18C_CANDIDATE_D_RESULT_20260815 -->
## Checkpoint 18C result — Candidate D fails the frozen development advancement gate

Run: `data/analysis/kxbtcd_candidate_d_development/20260815T234004Z`
Evaluation-result fingerprint: `b72617517d7bbc3bc1e01ff332496efaf5ba0c64c5eb445f82574e63fa4a47ab`

The frozen Candidate-D exposed-development screen completed without implementation, lineage, convergence, terminal-firewall, network, or execution failures.

### Pooled result

- development scope: 231 events / 5,364 rows
- scored OOF scope: 160 events / 3,726 rows
- raw event-weighted log loss: `0.15456664732282768`
- Candidate-D event-weighted log loss: `0.15159108042312835`
- raw-minus-D log-loss delta: `+0.002975566899699328`
- raw event-weighted Brier: `0.037893942261917626`
- Candidate-D event-weighted Brier: `0.026426318458628383`
- raw-minus-D Brier delta: `+0.011467623803289244`
- median event raw-minus-D log-loss delta: `+0.04671924978445033`
- better / worse / tie events: `149 / 11 / 0`

### Chronological block result

- B2 log-loss delta: `+0.093203479823316726`
- B3 log-loss delta: `+0.0061807888233462449`
- B4 log-loss delta: `+0.076486093656489507`
- B5 log-loss delta: `-0.029863425409502709`
- B6 log-loss delta: `-0.13112910239515319`

Candidate D therefore won only `3/5` score blocks. The latest B6 block also failed. These are exactly the two frozen advancement failures:
- `fewer_than_4_of_5_score_block_log_loss_wins`
- `latest_B6_log_loss_not_strictly_better`

B5 still improved Brier by `+0.0084444935043224527` while losing log loss, whereas B6 worsened Brier by `-0.0067525021571954863` as well as log loss. This is consistent with increasingly costly confidence errors and a stronger late-period breakdown by B6, but that mechanism is an interpretation rather than a separately validated causal claim.

### Coefficient stability

All five fits converged and all market-logit slopes were positive:

`3.1982462074078875, 3.4689767579266322, 2.6971700475935849, 2.7317860853200795, 2.3714201483058033`

The fitted model consistently sharpened the raw market because every slope exceeded the raw benchmark slope of `1`. This descriptive fact does not authorize a post-hoc slope cap, regularization change, or Candidate-D retune on this same screen.

### Decision

**Candidate D development advancement result: FAIL.**

Candidate D does not advance to a final development fit or prospective terminal evaluation under this specification. Do not repair, retune, regularize, cap, or otherwise modify Candidate D and then claim the same 160-event score set as a fresh advancement test.

This result does not establish that all market calibration is useless. It establishes only that this frozen two-parameter successor did not meet its predeclared temporal-stability requirement.

Checkpoint-17 terminal data remained unused: 0 terminal rows / labels / features; network requests 0; execution disabled; orders 0.

<!-- CHECKPOINT19A_SUCCESSOR_PROTOCOL_20260815 -->
## Checkpoint 19A authoritative design state — 2026-08-15

Candidate D remains permanently closed as a development FAIL. The 231-event / 5,364-row development pool is now classified as fully exposed E0 exploratory evidence only. The Checkpoint-17 64-event / 1,014-row terminal block is permanently prohibited from successor design, fitting, tuning, or future untouched-test claims.

The next KXBTCD successor eligible for advancement must include at least one contemporaneous independent BTC-state feature. Raw Kalshi midpoint remains the benchmark. Probability-only Kalshi recalibration is not eligible as the next advancing successor.

Fresh evidence is separated irreversibly into E1 successor-design evidence, E2 final-fit evidence after successor freeze, and E3 genuinely prospective untouched test evidence after final-model freeze. Outcome-exposed evidence cannot be promoted to a stronger role.

Checkpoint 19A is protocol and outcome-blind feasibility only. Candidate E's exact formula is not frozen; Candidate E fitting and outcome access are not authorized. Initial independent feasibility source families are Coinbase and Kraken. Exact source IDs, staleness/disagreement rules, feature formulas, cohort sizes, and future advancement gates remain to be frozen after the outcome-blind availability audit.

Execution remains prohibited.

<!-- CHECKPOINT19B_INDEPENDENT_BTC_FEASIBILITY_20260815 -->
## Checkpoint 19B implementation state — 2026-08-15

Checkpoint 19A is closed at checkpoint commit `e0420da9f0827621fe6a81e5b6320dede8a13a85` with receipt commit `6edb87292defd75c7bc37aa0853352b067f02cbf`.

Checkpoint 19B freezes a bounded outcome-blind engineering collector under audit-design fingerprint `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`. The exact pilot is 420 seconds with 2-second Coinbase/Kraken targets and 10-second open-KXBTCD targets. External request order alternates; each KXBTCD snapshot occurs after the current external attempts.

The pilot uses provisional Coinbase Exchange BTC-USD level-1 BBO and Kraken BTC/USD Pre-Trade BBO source identifiers. They are not yet E1-frozen feature sources. Derived external price is a BBO midpoint diagnostic only. Row age uses local monotonic first-seen time; no staleness threshold is selected, and local monotonic first-seen timing controls causal attachment. No sub-second lead/lag is authorized.

Candidate E remains unfrozen and unfitted. Outcomes, Checkpoint-17 terminal evidence, source-quality thresholds, consensus-price rules, E1/E2/E3 cohort sizes, advancement rules, and execution remain outside this checkpoint.

A successful 420-second pilot will justify only a longer outcome-blind availability audit, not Candidate-E fitting or a predictive claim.

<!-- CHECKPOINT19B_PILOT_RESULT_20260816 -->
## Checkpoint 19B bounded-pilot state — 2026-08-16

The frozen 420-second independent-BTC feasibility pilot completed successfully under audit fingerprint `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`.

Run `collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960` produced 210 Coinbase observations, 210 Kraken observations, and 42 Kalshi KXBTCD snapshots with zero raw/runtime errors. All 13,356 feasibility rows had both independent sources available and were structurally usable; exclusions were zero. Every Kalshi snapshot contained exactly 318 KXBTCD market rows.

Snapshot-level source-age and cross-source disagreement diagnostics were operationally small in this one bounded window, but the evidence spans only about seven minutes and three KXBTCD events and misses the 30–60m and 1–4h TTC bands.

Therefore Checkpoint 19B passes **engineering feasibility only**. No permanent staleness threshold, disagreement threshold, consensus-price rule, E1/E2/E3 sample size, or Candidate-E formula is frozen from this pilot. Candidate-E fitting and outcome access remain prohibited. The next evidence step is a longer outcome-blind availability collection with broader calendar/TTC coverage. Execution remains prohibited.

<!-- CHECKPOINT19C_EXTENDED_AVAILABILITY_20260816 -->
## Checkpoint 19C design state — 2026-08-16

Checkpoint 19B is closed at checkpoint commit `0d837d862c6d57908a7886d67b71785090c87335` with receipt `382913e25b718ded10dd049c85c9b5c8b1f27779` and 711 tests + 22 subtests passing.

19C freezes a separate 24-hour outcome-blind availability audit under fingerprint `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d`. Coinbase/Kraken are sampled every 15 seconds and KXBTCD every 5 minutes. The source IDs remain provisional audit identities rather than E1-frozen model sources.

The audit adds one-row-per-external-cycle and one-row-per-snapshot diagnostics so availability/disagreement estimates are not inflated by the number of strikes in each KXBTCD ladder. It also measures UTC-hour coverage and the causal gap to the five-minute lookback target.

No staleness threshold, disagreement threshold, consensus price, Candidate-E formula, E1/E2/E3 requirement, outcome access, or execution is authorized by this design.

<!-- LEARNING_GUIDE_POLICY_20260816 -->
## Cumulative learning guide

`docs/LEARNING_GUIDE.md` is part of the permanent project record as the cumulative educational companion to the research system. It explains mathematical, statistical, machine-learning, quantitative-finance, data-engineering, and software-engineering concepts introduced by the project from zero prior knowledge, with examples and practice.

Meaningful checkpoint closeout now includes reviewing this guide and updating it when new learning concepts are introduced. The guide does not replace the canonical state, decision, experiment, handoff, backlog, or risk-policy documents.

<!-- CHECKPOINT19C_RESULT_CLOSEOUT_20260817 -->
## Checkpoint 19C authoritative result — 2026-08-17

Checkpoint 19C completed the frozen 24-hour outcome-blind independent-BTC availability audit and is accepted as an **engineering-feasibility PASS only**.

Canonical run:

`collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250`

Frozen identities:

```text
protocol = b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8
audit design = 4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d
collection-start git commit = 86019fe76ead50d2cc41daf03d5fa5a1b2a75c7c
```

Integrity validation:

```text
manifest status = completed
worktree dirty at start = false
raw files = 6
raw records = 11,804
raw error records = 0
derived CSV files = 6
derived rows = 96,405
runtime event files = 1
runtime events = 11,806
runtime error events = 0
validation = PASS
```

Outcome-blind feasibility evidence:

```text
external cycles = 5,758
KXBTCD snapshots = 288
feasibility rows = 90,288
unique events = 27
unique markets = 4,722
UTC hour buckets = 25
Coinbase request success = 100%
Kraken request success = 100%
Kalshi request success = 100%
both-source external-cycle availability = 100%
structurally usable rows = 90,288 / 90,288
structural exclusions = 0
Coinbase 5m lookback row rate = 0.996477937267411
Kraken 5m lookback row rate = 0.996477937267411
```

Local first-seen ages at KXBTCD snapshots:

```text
Coinbase p50/p95/max = 1.297 / 2.203 / 41.422 seconds
Kraken p50/p95/max = 1.109 / 1.985 / 40.406 seconds
```

Five-minute target-gap diagnostics:

```text
Coinbase p50/p95/max = 1.297 / 2.2359 / 13.735 seconds
Kraken p50/p95/max = 1.109 / 2.0377 / 15.75 seconds
```

External-cycle cross-source disagreement:

```text
p50 = 0.7268472244022195 bp
p95 = 2.7526752145628617 bp
max = 5.347777694885947 bp
```

External receive skew:

```text
p50 = 156 ms
p95 = 234 ms
max = 9,687 ms
```

The 9.687-second receive-skew maximum occurred around 09:05 UTC inside the only visibly reduced hourly cadence bucket; requests remained successful and the following cycles recovered. The audit therefore exposed an operational tail that the seven-minute 19B pilot did not show.

A separate diagnostic also showed that successful Kraken requests can return top-book levels whose exchange publication timestamps have not changed for an extended period. This must not be confused with the protocol's local-first-seen age. Future source-quality policy must distinguish transport/request availability, local receipt age, source-event/publication freshness, and cross-source disagreement.

TTC coverage included all frozen bands: 0–30m, 30–60m, 1–4h, 4–24h, and >24h.

### Interpretation boundary

19C establishes extended causal/source-alignment feasibility only. It does **not** establish Candidate-E predictive value, profitability, source-quality thresholds, a Coinbase/Kraken consensus-price formula, five-minute-return alignment tolerance, E1/E2/E3 cohort sizes, or any execution policy.

Candidate E remains unfrozen and unfitted. Outcomes remained unopened. Checkpoint-17 terminal evidence remained unused. Execution/orders remained zero.

### Next research step

Freeze the exact independent-BTC source-quality and historical-materialization rules **before E1 outcomes or Candidate-E fitting**. The design should keep separate quality dimensions for request availability, local first-seen age, source-event/publication freshness, cross-source disagreement, and causal lookback alignment. Then freeze a very small Candidate-E feature menu and E1/E2/E3 evidence requirements before any outcome-driven selection.

A future, non-current architecture direction is also recorded for consideration: immutable prospective prediction storage, frozen champion models, offline challengers, controlled promotion gates, and monitoring of feature/parameter/calibration drift. This does not authorize live self-rewriting or execution.

<!-- CHECKPOINT19D_A_HISTORICAL_MATERIALIZATION_20260817 -->
## Checkpoint 19D-A design state — 2026-08-17

Checkpoint 19C is fully closed at checkpoint commit `c3bb8eaa20db8d89f536f1a3fb968a6ed04bc0e5` with receipt commit `097eb42bc475339fe832b6627c29c3fcbf2390dd`. The Checkpoint-19D entry preflight was clean and synchronized at that receipt commit.

19D-A freezes an **outcome-blind source-quality and historical-materialization audit**, not Candidate E. Audit fingerprint: `023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c`.

The audit reuses the exact 288 KXBTCD `as_of_utc` states from canonical 19C run `collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250`. For each state it reconstructs only the last fully completed UTC one-minute bucket and the exact bucket five minutes earlier.

Historical source candidates under audit:

- `coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1` — Coinbase Exchange BTC-USD one-minute candle close;
- `kraken.spot.public_rest.posttrade.btc_usd.v1` — Kraken BTC/USD PostTrade, selecting the latest bucket trade whose `publication_ts` was no later than the original KXBTCD state.

No interpolation, nearest-future sampling, or missing-bucket carry-forward is permitted. Missing exact native data is an exclusion.

19D-A also re-reads the preserved 19C raw books. Kraken best-bid and best-ask `publication_ts` are measured separately and conservative BBO publication age is the older-side age, not the newer-side timestamp previously carried as the single diagnostic source time.

19D-A deliberately does **not** freeze the E1 source allow-list, source priority/consensus rule, staleness thresholds, source-event freshness thresholds, disagreement threshold, Candidate-E formula/features, E1/E2/E3 cohort requirements, advancement gate, or execution. Outcomes remain unopened; Candidate E remains unfitted; Checkpoint-17 remains prohibited.

Next: validate and close the 19D-A implementation from a clean synchronized repository, run the exact audit once, inspect only outcome-blind source/history distributions, and then use a separate 19D-B freeze for final source-quality/materialization/evidence-cohort decisions.

<!-- CHECKPOINT19D_A_RESULTS_20260817 -->
## Checkpoint 19D-A result — independent-BTC historical materialization

Checkpoint 19D-A is complete as an outcome-blind source-quality audit.

Canonical run:
`collect_kxbtcd_independent_btc_historical_materialization_20260817T061908727611Z_f90d93fc`

The run reconstructed 288 frozen 19C snapshots over 291 unique target minutes.
Coinbase achieved 100% exact current/lookback coverage. Kraken achieved 287/288
for each role; both exclusions trace to the same 09:09–09:10 UTC minute, whose
preserved Kraken PostTrade response was HTTP 200 with zero trades. Both-source
current + exact-five-minute-pair coverage was 286/288 (99.3056%).

Where both historical sources were present, current disagreement was p50
0.7216 bp, p95 2.9591 bp, max 6.0368 bp. These are descriptive and do not freeze
a threshold.

A source-quality distinction is now empirically important: Kraken local receive
freshness can look healthy while one BBO side is old. The 19C conservative
Kraken BBO publication-age distribution was p50 22.012 s, p95 49.175 s,
p99 354.472 s, max 6120.316 s.

No outcomes were accessed and Candidate E remains unfitted/unfrozen. The next
research gate is Checkpoint 19D-B: freeze the E1 source allow-list,
deterministic construction, quality thresholds, historical-causality rules, and
minimum evidence coverage using outcome-blind evidence only.

<!-- CHECKPOINT19D_B_SOURCE_POLICY_20260817 -->
## Checkpoint 19D-B authoritative source-policy freeze — 2026-08-17

Checkpoint 19D-B freezes the independent-BTC source policy before Candidate-E
specification or E1 outcome access.

Policy fingerprint:
`6b0d98c16a65b2e638b36991d5006031e1bd37048bd04a47a3f67d936df0ee18`

Frozen roles:
- Coinbase Exchange BTC-USD level-1 book = live primary;
- Kraken BTC/USD PreTrade = live verifier;
- Coinbase one-minute candle close = historical primary;
- Kraken PostTrade latest causally published exact-minute trade = historical verifier.

No consensus average, learned venue weighting, source substitution, or
single-source fallback is allowed.

Frozen live quality gates: local first-seen <=5 s per source, Coinbase
source-event age <=10 s, Kraken conservative best-side publication age <=60 s,
cross-source receive skew <=1 s, midpoint disagreement <=5 bp, and absolute
local clock-offset bound <=1 s. All required gates must pass.

Evidence minimums are E1 168 events/7 UTC days, E2 168 events/7 UTC days, and
E3 336 events/14 UTC days, with all 24 UTC hour-of-day bins, >=90% scheduled
state source eligibility, and >=2/3 source-eligible scheduled states per counted
event. Cohorts extend prospectively without outcome access if those gates are
not met.

Candidate E remains formula-unfrozen and unfitted. The next Checkpoint-19
substep must freeze the tiny Candidate-E menu, TTC materialization, chronological
E1 scoring layout, metrics, and advancement gate before any E1 outcomes are used.
Execution authorization is unchanged.

<!-- CHECKPOINT19E_CANDIDATE_E_PREDECLARATION_20260817 -->
## Checkpoint 19E — Candidate-E predeclaration freeze

Candidate E is now specification-frozen but remains **unfitted**.

- family: `kxbtcd_independent_btc_offset_successor.v1`
- predeclaration fingerprint: `9775be58f01375ca6f2b04212a63578ce5e8cf7084498e6ce9d3ae68685d59a9`
- candidates: `kxbtcd_btc_distance_offset_logistic.v1` and `kxbtcd_btc_distance_momentum_offset_logistic.v1`
- independent features: `d_BTC = 10000*ln(S_t/K)` and `r_5m = 10000*ln(S_t/S_t-300s)`
- Kalshi midpoint is a fixed logit offset; no intercept or free market-logit slope
- no regularization, standardization, lambda grid, or hyperparameter search
- scored TTC targets: 55m, 50m, 45m, 40m, 35m, 30m
- E1: minimum 168 eligible events / 7 UTC dates / 168h / all 24 UTC hours
- seven chronological blocks and five rolling-origin score folds B2-B6
- both candidates use identical OOF rows
- raw midpoint remains the benchmark
- momentum is selected over distance only if it clears the separately frozen nested complexity gate
- E1 outcomes remain unopened
- Checkpoint-17 terminal data remain prohibited
- execution remains prohibited

Next work is implementation/validation of the prospective E1 pre-outcome collector and cohort freezer under this exact fingerprint. No Candidate-E fitting or E1 outcome access is authorized yet.

<!-- CHECKPOINT19F_HISTORICAL_EVIDENCE_AMENDMENT_20260817 -->
## Checkpoint 19F — historical-first Candidate-E evidence amendment

Checkpoint 19F supersedes only the prospective timing architecture of 19A/19D-B/19E before any Candidate-E fit or new Candidate-E outcome access. Candidate E's formulas and source identities remain frozen under 19E/19D-B.

Frozen amendment fingerprint: `b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb`.

Outcome-blind census audit: 9,738 modern-regime events, 307 prior outcome-exposed events, 9,431 untouched events. Untouched chronological-universe fingerprint: `d0b61b7688e54ff4cdeb4cc4652a8ecd5a0a5031b14ad7666b1a8b5b0b5fda90`.

New evidence sequence: H1 = first 1,500 eligible untouched historical events for fit + frozen 19E rolling-origin candidate selection; H2 = next 750 eligible untouched events for one-time validation; after H2 PASS refit the selected fixed specification once on H1+H2 and freeze final parameters; H3 = next 750 eligible untouched events for one-time locked historical test. H2 remains sealed until H1 PASS; H3 remains sealed until H2 PASS and final-model freeze. A historical-test PASS permits prospective live confirmation only.

Historical Candidate-E states use Coinbase exact completed-minute close as primary and Kraken exact-minute causally published trade as mandatory verifier, with no interpolation/imputation/substitution and <=5 bp historical cross-source disagreement. Later live confirmation returns to the frozen 19D-B live BBO policy. Historical primitives are not claimed identical to live BBO.

Nominal raw reserve after the first 3,000 untouched events is 6,431; outcome-blind eligibility extension is allowed only with frozen thresholds and must fail closed before the remaining outcome-unopened reserve would fall below 5,000 events.

No new Candidate-E outcomes were used to choose this amendment. Candidate E remains unfitted at the 19F design freeze. Execution remains prohibited.

Next: validate the 19F amendment and exact local universe, then implement/freeze the outcome-blind historical H1/H2/H3 materializer before opening H1 labels.

<!-- CHECKPOINT19F_FINAL_CLOSEOUT_20260817 -->
## Checkpoint 19F authoritative closeout ? 2026-08-17

Checkpoint 19F replaces the prospective-only Candidate-E evidence sequencing with a historical-first, sequentially sealed evidence protocol before any new Candidate-E outcome access.

Frozen historical universe:
- modern-regime census: 9,738 events
- prior outcome-exposed deny-list: 307 events
- outcome-untouched universe: 9,431 events
- exposed-event-set SHA-256: `d7e115bf5566630fdff0fb75a740701f1080c0d385a707617fcfc65dde159817`
- untouched chronological universe SHA-256: `d0b61b7688e54ff4cdeb4cc4652a8ecd5a0a5031b14ad7666b1a8b5b0b5fda90`

Frozen Candidate-E historical allocation:
- H1 TRAIN: 1,500 eligible events
- H2 VALIDATION: 750 eligible events
- H3 LOCKED TEST: 750 eligible events
- nominal untouched reserve: 6,431 events
- hard reserve floor: 5,000 outcome-unopened events
- L1 prospective live confirmation occurs only after H3 historical PASS

Sequential firewall:
- H2 outcomes remain sealed unless H1 passes.
- H3 outcomes remain sealed unless H2 passes and the final model is frozen.
- A source-eligibility failure may extend a cohort only under the frozen outcome-blind extension rule.
- Candidate-C terminal evidence remains prohibited.
- Candidate E remains unfitted at this closeout.

Amendment fingerprint:
`b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb`

Final local validation:
- exact local frozen-universe validation: PASS
- focused Checkpoint-19F tests: 6 passed
- full repository regression: 759 passed + 22 subtests
- `git diff --check`: PASS
- Candidate-E new outcomes accessed: zero
- Candidate-E fits performed: zero
- execution authorization: unchanged / prohibited

A Windows path-separator mismatch found during local validation was repaired by canonical repository-path normalization and regression-tested. The repair changed no frozen data hash, amendment fingerprint, Candidate-E formula, evidence allocation, or outcome boundary.

Next: construct the historical Candidate-E pre-outcome eligibility/materialization layer using only frozen source and causality rules. Do not open H1 outcomes until that pre-outcome materialization and partition map are frozen.

<!-- CHECKPOINT19F_STAGED_DIFF_REPAIR_20260817 -->
### Checkpoint 19F closeout sanitation

The first safe-closeout attempt correctly blocked before commit because the newly added 19F test file contained one extra blank line at EOF. The file was normalized to exactly one terminal newline and the closeout was rerun. This was packaging/whitespace only: no amendment fingerprint, evidence hash, allocation, model rule, outcome boundary, or authorization changed.

<!-- CHECKPOINT19G_HISTORICAL_MATERIALIZATION_20260817 -->
## Checkpoint 19G design state — historical Candidate-E pre-outcome materialization

Checkpoint 19F is closed at checkpoint `4107f6506617369fad38b058e15f9f612c2232bb` with receipt `1fa3504b84ae7ab840d54be6e1f50b9853614150`.

19G freezes the data/materialization contract under fingerprint `cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145` before large-scale Candidate-E historical source collection. The exact 9,431-event outcome-untouched queue remains the only canonical event order. H1/H2/H3 target sizes remain 1,500/750/750 and the protected unallocated tail remains at least 5,000 events.

An eligible anchor requires an eligible exact-minute Coinbase/Kraken current pair, an eligible exact five-minute lookback pair, <=5 bp disagreement for each pair, and at least one valid structural KXBTCD quote row at the scheduled TTC target. The contract does not add a new all-five-strikes-per-anchor requirement; final score/evaluation blocks must still cover all five structural roles and all six TTC targets.

Historical market payloads may unavoidably contain result/settlement fields. Raw archives remain unchanged, but 19G freezes an explicit metadata allow-list before semantic processing and prohibits result/settlement fields from influencing selection, branching, derived output, or fingerprints. Dedicated Candidate-E labels remain unopened.

After 19G closeout, Checkpoint 19H will use separately manifested contiguous chunks and an offline final freezer. Smoke artifacts are segregated and cannot enter the canonical freeze. Candidate E remains unfitted. Execution remains prohibited.

<!-- CHECKPOINT19H_SMOKE_VALIDATION_20260817 -->
## Checkpoint 19H Stage A ? historical materialization smoke validation

The first noncanonical Candidate-E historical materialization smoke exposed a Windows path-length defect in smoke artifact naming. The collector repeated its long run_id as both a directory component and filename prefix, which exceeded the effective Windows path limit in the user's OneDrive repository.

The repair removed only the redundant smoke run_id directory component. Run identity remains preserved in artifact filenames, manifests, row lineage, and runtime logs. Canonical materialization naming, Candidate-E formulas, eligibility rules, source construction, evidence partitions, fingerprints, and outcome firewalls were not changed.

Post-repair noncanonical smoke run:
- run: `collect_kxbtcd_candidate_e_historical_materialization_chunk_20260817T082547653987Z_48b89ca0`
- queue range: [0, 2)
- events processed: 2
- eligible events: 2
- ineligible events: 0
- common Candidate-E rows: 30
- new Candidate-E outcomes accessed: 0
- Candidate-E fits: 0
- orders: 0
- focused materialization tests: 10 passed
- full regression: 769 passed + 22 subtests
- git diff check: PASS

Next: after committing this implementation-only repair from a clean synchronized repository, begin canonical Checkpoint-19H materialization at untouched queue index 0. H1/H2/H3 labels remain sealed.

<!-- CHECKPOINT19HB_COINBASE_PRIMARY_20260817 -->
## Checkpoint 19H-B — Coinbase-primary source amendment

An outcome-blind coverage audit of the first 600 Candidate-E historical queue identities showed 303/600 (50.50%) event eligibility under the original mandatory Coinbase+Kraken 5 bp disagreement veto, versus 459/600 (76.50%) when the disagreement veto was removed. Coinbase-only eligibility was also 459/600 (76.50%). No Candidate-E outcomes were opened and no Candidate-E fit was performed.

Accepted amendment: Coinbase is the sole required Candidate-E BTC-state source. Kraken is optional diagnostic evidence and cannot veto anchor/event eligibility. The canonical Coinbase-primary materializer performs zero Kraken requests. Candidate-E formulas, 4-of-6 anchor rule, 1,500/750/750 H1/H2/H3 sizes, 4,431-event materialization cap, and 5,000-event reserve floor remain unchanged.

Source-amendment fingerprint: `b08da00a8f66817d9e3b600ccf091c8a4fc1ee92a0bed1c821d23bc321d9faba`.

The original 19G chunks for queue 0-599 are preserved as superseded feasibility evidence and cannot enter the Coinbase-primary final freeze. Re-materialization restarts at queue index 0 under a separate canonical root. Outcomes and fitting remain prohibited.

<!-- CHECKPOINT19HC_FINAL_HISTORICAL_FREEZE_20260817 -->
## Checkpoint 19H-C ? final Candidate-E historical pre-outcome freeze

Checkpoint 19H historical materialization is complete under the frozen
Coinbase-primary source amendment.

Final freeze:
- canonical raw queue events materialized: 3200
- H1 train events: 1500
- H2 validation events: 750
- H3 locked-test events: 750
- ineligible events before the 3,000th eligible event: 147
- actual untouched tail remaining: 6231
- cohort-map fingerprint: `09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa`
- row-universe fingerprint: `e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5`
- exclusion fingerprint: `dd2877579bb800fc1d15ee3c05754947658dfdb552858d67f39b260e32aaf9c4`
- required BTC source: Coinbase
- Kraken required: False
- Candidate-E outcomes accessed: False
- Candidate-E fit performed: False
- execution authorized: False

Frozen stage boundaries:

- H1: 1500 events / 36314 rows; `2025-03-22T17:00:00Z` `KXBTCD-25MAR2213` through `2025-07-07T14:00:00Z` `KXBTCD-25JUL0710`; queue indices 0 through 1641.
- H2: 750 events / 22354 rows; `2025-07-07T15:00:00Z` `KXBTCD-25JUL0711` through `2025-08-25T04:00:00Z` `KXBTCD-25AUG2500`; queue indices 1642 through 2396.
- H3: 750 events / 22409 rows; `2025-08-25T13:00:00Z` `KXBTCD-25AUG2509` through `2025-10-12T22:00:00Z` `KXBTCD-25OCT1218`; queue indices 2397 through 3146.

Interpretation:
- Checkpoint 19H is a data/cohort freeze, not a predictive result.
- H1 labels may be opened only in the next explicitly authorized development checkpoint.
- H2 labels remain sealed until H1 selects exactly one Candidate-E specification.
- H3 labels remain sealed until H2 passes and the final H1+H2 parameters are frozen.
- The 6,231-event untouched tail remains protected for future evidence.

<!-- CHECKPOINT20A_H1_PROCEDURE_FREEZE_20260817 -->
## Checkpoint 20A — Candidate-E H1 evaluation procedure frozen

The H1-only outcome/evaluation path is implemented and frozen under `cbbca76de2dd87edd6c6bc4f21ae1005fbd1402a3bb85374e7699c8fb5fb7d14`. It revalidates the 19H-C cohort/row fingerprints, accepts only frozen H1 identities, hard-denies H2/H3 identities, binds the existing H1 B0-B6 map and five rolling-origin folds, evaluates exactly the two predeclared Candidate-E variants, and preserves the raw/nested gates without post-hoc repair.

No Candidate-E outcome has been opened by Stage 20A and no Candidate-E fit has been performed. Stage 20B may begin only after this freeze is committed/pushed and the local repository is freshly verified clean and synchronized. H2/H3 remain sealed. Execution remains prohibited.

<!-- CHECKPOINT20B_CANDIDATE_E_H1_RESULT_20260817 -->
## Checkpoint 20B — H1 complete; Distance selected

Candidate E passed its frozen H1 development screen. The selected specification is exactly `kxbtcd_btc_distance_offset_logistic.v1` under H1 result fingerprint `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`. H1 is permanently exposed. H2 and H3 remain outcome-sealed.

Next authorized work is a new outcome-blind H2-preparation checkpoint: fit the selected Distance specification once on all exposed H1 events, freeze that H1 parameter artifact, freeze the H2-only validation procedure/allow-list and H3 deny-list, test the firewall, and close that preparation checkpoint before H2 outcomes are opened. No H1 redesign, post-hoc repair, or execution is authorized.

<!-- CHECKPOINT20C_CANDIDATE_E_H2_PREPARATION_20260817 -->
## Checkpoint 20C — full-H1 Distance fit and H2 validation freeze

Checkpoint 20B selected exactly `kxbtcd_btc_distance_offset_logistic.v1` under H1 result fingerprint `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`. Checkpoint 20C then performed the single final parameter fit for that already-selected specification on all 1,500 exposed H1 events / 36,314 H1 rows.

- frozen beta_distance: `0.012310034918384302`
- final H1 model fingerprint: `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
- H2 validation fingerprint: `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`
- H2: 750 events / 22,354 rows
- frozen H2 chronological blocks: B0-B4, exactly 150 events each
- H2 unique market labels in frozen request plan: 3750
- H2 outcomes opened: 0
- H3 outcomes opened: 0
- network requests during Checkpoint 20C: 0
- execution/orders: disabled / 0

H2 may not fit parameters, select another candidate, change features, or tune hyperparameters. It must score the frozen full-H1 Distance model exactly once against raw Kalshi midpoint using the predeclared event-equal log-loss/Brier gate. H3 identities remain hard denied. If H2 fails, Candidate E stops and H3 remains untouched. If H2 passes, the same fixed specification may be refit once on H1+H2 and frozen before H3.

<!-- CHECKPOINT20D_CANDIDATE_E_H2_IMPLEMENTATION_20260817 -->
## Checkpoint 20D — Candidate-E H2 evaluator implementation frozen

The network-capable H2 collector/evaluator implementation is frozen before any H2 outcome access.

- parent H2 validation fingerprint: `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`
- final H1 model fingerprint: `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
- H2 implementation fingerprint: `0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e`
- H2 allow-list: 750 events / 22,354 pre-outcome rows / 3,750 market labels
- H2 blocks: B0-B4, 150 events each
- H3 event/market identities: hard denied
- H2 model fitting/tuning/candidate selection: prohibited
- H2 outcomes opened during 20D: 0
- H3 outcomes opened: 0
- network requests during 20D: 0
- execution/orders: disabled / 0

After this checkpoint is safely closed and pushed, the only authorized next action is the one-time H2 outcome exposure/evaluation through `collect_kxbtcd_candidate_e_h2.py`. The collector may resume an interrupted same attempt, but may not start a fresh second H2 attempt.

<!-- CHECKPOINT20F_CANDIDATE_E_H2_RESULT_20260817 -->
## Checkpoint 20F — Candidate-E H2 PASS

Candidate E's fixed Distance model passed the untouched H2 validation under result fingerprint `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`. The frozen H1 coefficient `0.012310034918384302` reduced event-equal H2 log loss from `0.11774919111369225` to `0.035893546124196762` and won all five chronological H2 blocks, including newest B4.

H2 is now permanently outcome-exposed. H3 remains outcome-sealed. The next authorized modeling action is not redesign: fit the same fixed `kxbtcd_btc_distance_offset_logistic.v1` specification exactly once on the combined H1+H2 evidence (2,250 events), freeze the resulting parameter artifact, then separately freeze and close the H3 locked-test procedure before any H3 outcome access. No new features/candidates/tuning or execution are authorized.

<!-- CHECKPOINT20G_CANDIDATE_E_H3_PREPARATION_20260817 -->
## Checkpoint 20G — Candidate-E H1+H2 final fit and H3 freeze

Candidate E remains exactly `kxbtcd_btc_distance_offset_logistic.v1`. After validated H2 PASS `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`, the same frozen one-parameter specification was fit once on all exposed H1+H2 evidence.

- H1 result fingerprint: `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`
- H2 result fingerprint: `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`
- final fit: 2,250 events / 58,668 rows
- final beta_distance: `0.013805016135330063`
- final H1+H2 model fingerprint: `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
- H3: 750 untouched events / 22,409 pre-outcome rows / 3750 frozen market labels
- H3 blocks: B0-B4, exactly 150 events each
- H3 validation fingerprint: `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`
- H3 outcomes opened: 0
- network requests: 0
- execution/orders: disabled / 0

No feature, candidate, optimizer, hyperparameter, or validation-gate change was made after H2. H3 will score only this fixed H1+H2 model against raw Kalshi midpoint. H3 must pass the same frozen gate shape: positive pooled log-loss delta, non-worse Brier, at least 4/5 chronological block wins, newest-B4 win, positive median event delta, valid final model, full structural coverage, and no policy/firewall violation.

Checkpoint 20G does not contain a network-capable H3 collector. The H3 outcome-opening implementation must be frozen, tested, safely closed, and pushed in a separate checkpoint before any H3 label is requested.

<!-- CHECKPOINT20H_CANDIDATE_E_H3_IMPLEMENTATION_20260817 -->
## Checkpoint 20H — Candidate-E H3 evaluator implementation frozen

The network-capable H3 locked-test collector/evaluator implementation is frozen before any H3 outcome access.

- parent H3 validation fingerprint: `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`
- final H1+H2 model fingerprint: `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
- H3 implementation fingerprint: `6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc`
- H3 allow-list: 750 events / 22,409 pre-outcome rows / 3,750 market labels
- H3 blocks: B0-B4, exactly 150 events each
- H1/H2 event and market identities: hard denied
- H3 model fitting/tuning/candidate selection: prohibited
- H3 outcomes opened during 20H: 0
- network requests during 20H: 0
- execution/orders: disabled / 0

After this checkpoint is safely closed and pushed, the only authorized next action is the one-time H3 locked-test exposure/evaluation through `collect_kxbtcd_candidate_e_h3.py`. The collector may resume an interrupted same attempt, but may not start a fresh second H3 attempt.

<!-- CHECKPOINT20J_CANDIDATE_E_H3_RESULT_20260817 -->
## Checkpoint 20J — Candidate-E historical generalization PASS

Candidate E's fixed `kxbtcd_btc_distance_offset_logistic.v1` model passed the one-time untouched H3 test under result fingerprint `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`. The frozen H1+H2 model reduced event-equal H3 log loss from `0.13793316358637769` to `0.038920564033036092` and won all five chronological H3 blocks, including newest B4.

H1, H2, and H3 are now all outcome-exposed. The Candidate-E historical generalization program is complete and passed. The remaining untouched historical reserve must not be casually consumed. Before any post-H3 refit, freeze a new champion/prospective-confirmation protocol specifying how much reserve remains untouched, how expanding-window historical confirmation would work if used, and how immutable read-only live shadow predictions will be evaluated. Execution remains prohibited.

<!-- CHECKPOINT21A_POST_H3_LIFECYCLE_20260817 -->
## Checkpoint 21A — post-H3 champion lifecycle and reserve protocol freeze

The post-H3 evidence architecture is now frozen before any Candidate-E refit or reserve outcome access.

- parent H3 result fingerprint: `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`
- protocol fingerprint: `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
- champion specification remains: `kxbtcd_btc_distance_offset_logistic.v1`
- currently exposed champion evidence: H1+H2+H3 = 3,000 events
- strict post-19H-C untouched historical tail entering Checkpoint 21: approximately 6,231 events
- C1/C2/C3 target: 500 eligible events each
- each C block: five chronological 100-event subblocks
- strict untouched-tail floor after confirmation materialization: 4,500 events
- C1 fit size: 3,000 exposed events
- C2 fit size after C1 PASS: 3,500 exposed events
- C3 fit size after C2 PASS: 4,000 exposed events
- final historical champion fit after C3 PASS: 4,500 exposed events

Every C block uses the unchanged Distance specification and frozen Candidate-E historical source/materialization rules. Each block must strictly improve pooled event-equal log loss versus raw midpoint, be non-worse on Brier, win at least 4/5 chronological subblocks including the newest, have positive median event-level improvement, retain valid positive `beta_distance`, preserve structural/TTC coverage, and pass source/timing/lineage/firewall checks. Primary ties fail.

Any C failure stops advancement and preserves later reserve evidence. Later C blocks are not materialized or outcome-opened after a prior failure.

If all C blocks pass, the next research layer is **historical strategy development on exposed evidence only**. Before selecting entry/exit/size thresholds, audit whether exposed history supports executable bid/ask, depth, fees, timestamps, latency assumptions, and fill semantics. A strong forecasting model is not yet an executable edge.

The intended later prospective phase is a full live read-only shadow system, not probability collection alone. It will preserve an immutable 1,000-event forecasting ledger and, only after separate risk-policy authorization, run a local mock order/fill engine driven by the same live feeds, model, and frozen strategy. Economic live-shadow gates remain to be frozen after historical strategy research.

Current safety state is unchanged:

- post-H3 refit performed: no;
- C1/C2/C3 outcomes opened: 0 / 0 / 0;
- strategy selected: no;
- live paper/shadow broker enabled: no;
- demo orders: 0;
- real orders: 0.

Next checkpoint: Checkpoint 21B — outcome-blind C1 preparation. Validate the canonical strict-tail start, fit the unchanged champion once on H1+H2+H3, freeze that model, deterministically materialize/freeze C1 only, and keep C1 outcomes sealed.

<!-- CHECKPOINT21B_A_C1_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21B-A — C1 preparation implementation freeze

Implementation fingerprint: `b69b13a6d0db89be98229f34a946cbdfa24a7280ddbc8bff968f641714a93672`.

The code path that will later (1) fit the unchanged Candidate-E Distance champion on all 3,000 already-exposed H1/H2/H3 events and (2) sequentially materialize only C1 from the strict queue tail is frozen before reserve access. The C1 collector begins at queue index 3200, has no arbitrary start-index argument, stops exactly at the 500th eligible event, and enforces the Checkpoint-21A 4,500-candidate strict-tail floor.

This checkpoint performs no Champion-R0 fit, no network collection, no C1/C2/C3 outcome access, no C2/C3 materialization, and no execution. After safe closeout, the next action is Checkpoint 21B-B: deterministically create and freeze Champion-R0 on exposed H1/H2/H3 only. C1 materialization begins only after that R0 artifact is safely closed.

<!-- CHECKPOINT21B_B_CHAMPION_R0_20260818 -->
## Checkpoint 21B-B ? Champion-R0 frozen

The post-H3 Champion-R0 fit is complete.

- candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- fit evidence: H1+H2+H3, all previously outcome-exposed
- fit size: 3,000 events / 81,077 rows
- `beta_distance`: `0.014447239079794087`
- optimizer convergence: PASS
- Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- artifact SHA-256: `811a2776684f130d8b36f1ffb9253e90d678ffda9faf237815282fb67619c8d3`
- C1 outcomes opened: 0
- C1 rows used in fit: 0
- network requests: 0
- orders: 0

No feature, candidate, objective, optimizer, hyperparameter, or source-policy
change occurred. This checkpoint freezes the exact model that will enter C1.

Next: after safe closeout of 21B-B, begin Checkpoint 21B-C and materialize only
C1 from strict-tail queue index 3200 using the already-frozen collector. Do not
open C1 outcomes and do not materialize C2/C3.

<!-- CHECKPOINT21B_C_C1_PREOUTCOME_FREEZE_20260818 -->
## Checkpoint 21B-C ? C1 pre-outcome cohort frozen

The first post-H3 fresh confirmation cohort is now fully materialized and frozen
without outcomes.

- fixed entering model: Champion-R0 `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- C1: 500 eligible events
- C1 blocks: five chronological blocks of 100 events
- candidate identities inspected: 506
- strict-tail queue consumed: `[3200, 3706)`
- C1 pre-outcome rows: 14887
- C1 unique markets: 2491
- C1 cohort fingerprint: `7f53764ca50d4a5e00a4d12d0cebda566a1333a6951b2686b2c9d06631c1ca36`
- C1 row fingerprint: `6d02d8b484813760a87a7daea05ecf994e18ae875e7e066e9b097ac830e01af8`
- C1 validation fingerprint: `76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`
- strict never-materialized historical tail remaining: 5725
- minimum protected tail: 4500
- reserve buffer: 1225
- C1 outcomes opened: 0
- C2/C3 materialized: 0
- execution/orders: disabled / 0

This is a dataset/protocol freeze only, not a predictive PASS or FAIL.

Next: implement and freeze the one-time C1 outcome collector/evaluator against
Champion-R0. Do not open C1 labels until that evaluator implementation is
tested, frozen, safely closed, and pushed. C2 remains untouched unless C1
eventually passes its predeclared gate.

<!-- CHECKPOINT21C_C1_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21C — C1 evaluator implementation frozen

The one-time C1 outcome evaluation path is now implementation-frozen without
opening C1 outcomes.

- implementation fingerprint: `2719cef9c5180014f3230c724be76bf959d71882a2f0c84e386a5169392773af`
- C1 validation fingerprint: `76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`
- Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- C1: 500 events / 14887 pre-outcome rows / 2491 outcome markets
- blocks: B0-B4, exactly 100 events each
- H1/H2/H3 identities: hard denied
- fresh second C1 attempt: prohibited
- model fit/tuning/candidate selection: prohibited
- C2/C3 access: prohibited
- C1 outcomes opened: 0
- network requests at implementation freeze: 0
- orders: 0

Next: after safe closeout of Checkpoint 21C, run the frozen C1 evaluator exactly
once. If the run is interrupted, resume only that same exposure attempt from its
recognized manifest. Do not materialize C2 unless C1 eventually passes.

<!-- CHECKPOINT21D_C1_RESULT_20260818 -->
## Checkpoint 21D ? Candidate-E C1 confirmation PASS

The first post-H3 fresh champion confirmation has passed.

- result fingerprint: `5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19`
- fixed entering Champion-R0: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- fixed beta_distance: `0.014447239079794087`
- C1: 500 events / 14,887 rows / 2,491 labels
- raw log loss: `0.17078339823721184`
- Champion log loss: `0.053151764629610743`
- raw-minus-Champion log-loss delta: `0.11763163360760109`
- raw Brier: `0.039207186965517601`
- Champion Brier: `0.01515132922607266`
- raw-minus-Champion Brier delta: `0.024055857739444943`
- median event log-loss delta: `0.10189307395366344`
- chronological block wins: 5 / 5
- newest B4 win: yes
- C1 gate: PASS
- C1 is permanently outcome-exposed
- strict never-materialized tail still remaining: 5,725
- C2/C3 materialized/opened: no / no
- execution/orders: disabled / 0

Next, after this result is safely closed and pushed, begin C2 preparation.
Refit the unchanged Distance champion once on the 3,500 exposed
H1+H2+H3+C1 events and freeze that parameter artifact before accessing C2.
Do not materialize C3.

<!-- CHECKPOINT21E_A_C2_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21E-A — C2 preparation implementation frozen

Implementation fingerprint: `c2be562e2476995dd4adb712a035ac69eca8ca6b4b7fa93c53106758286dc327`.

C1 is permanently exposed and passed under result fingerprint
`5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19`.

The implementation for the next expanding-window transition is now frozen:
Champion-R1 may later fit only the unchanged Distance specification on
H1+H2+H3+C1 = 3,500 exposed events / 95,964 rows. It may use zero C2 rows or
outcomes.

C2 materialization is also bounded in frozen code but is not yet authorized to
run. It begins exactly at strict queue index 3706, has no arbitrary start
argument, stops at exactly 500 eligible events, and may never cross absolute
end-exclusive index 4931.

Checkpoint 21E-A itself:
- Champion-R1 fit: not performed;
- C2 materialization: not performed;
- C2 outcomes opened: 0;
- C3 materialized/opened: 0;
- network requests: 0;
- execution/orders: disabled / 0.

Next: safely close 21E-A, then create/freeze Champion-R1 network-free. Do not
start the C2 collector until Champion-R1 is separately closed and pushed.

<!-- CHECKPOINT21E_B_CHAMPION_R1_20260818 -->
## Checkpoint 21E-B ? Champion-R1 frozen

Champion-R1 has been fit exactly once using only exposed evidence.

- model: `kxbtcd_btc_distance_offset_logistic.v1`
- fit stages: H1 + H2 + H3 + C1
- fit scope: 3,500 events / 95,964 rows
- Champion-R1 fingerprint: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- beta_distance: `0.014529004270980883`
- fit objective: `0.053921466611488181`
- iterations: 10
- converged: yes
- C2 rows/outcomes used: 0 / 0
- C2 outcomes opened: 0
- C3 materialized/opened: 0
- network requests: 0
- execution/orders: disabled / 0

Strict untouched historical tail remains 5,725 events because Champion-R1
fitting consumed no reserve identities.

After safe closeout, the next authorized step is Checkpoint 21E-C:
outcome-blind C2 materialization beginning exactly at queue index 3706.
Stop at exactly 500 eligible C2 events and never cross absolute end-exclusive
index 4931. Do not open C2 outcomes and do not materialize C3.

<!-- CHECKPOINT21E_C_C2_PREOUTCOME_FREEZE_20260818 -->
## Checkpoint 21E-C ? C2 pre-outcome cohort frozen

C2 has been fully materialized and frozen without outcomes.

- entering model: Champion-R1 `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- C2: 500 eligible events
- five chronological 100-event blocks
- identities inspected: 516
- ineligible identities: 16
- queue consumed: `[3706, 4222)`
- C2 pre-outcome rows: 14007
- unique markets: 2441
- C2 validation fingerprint: `b984017e17da9de2859d43b78f1218d7333eda45eb1ebb0ed3a6a884eb3746f1`
- strict untouched tail remaining: 5209
- protected floor: 4500
- remaining buffer: 709
- C2 outcomes opened: 0
- C3 materialized/opened: 0
- execution/orders: disabled / 0

This establishes the identities for the next fresh confirmation test. It does
not reveal whether Champion-R1 passes C2.

Next: implement, test, and freeze the C2-only outcome evaluator. Do not request
C2 labels until that evaluator implementation has been safely closed and
pushed. Do not materialize C3.

<!-- CHECKPOINT21F_A_C2_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21F-A — C2 evaluator implementation frozen

C2 remains fully outcome-sealed while its one-time evaluator is now
implementation-frozen.

- C2 implementation fingerprint: `a958b843a5504507b598f05fba79f57691b21ffe9aee6be8148ca12fd38ab3c2`
- Champion-R1: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- C2 validation fingerprint: `b984017e17da9de2859d43b78f1218d7333eda45eb1ebb0ed3a6a884eb3746f1`
- C2: 500 events / 14,007 rows / 2,441 market requests
- H1/H2/H3/C1 identities: hard denied
- model fit/tuning/selection: prohibited
- C3 materialization/outcome access: prohibited
- fresh second C2 attempt: prohibited
- C2 outcomes opened during 21F-A: 0
- network requests during 21F-A: 0
- execution/orders: disabled / 0

After safe closeout, the only authorized next action is the one-time C2
outcome exposure/evaluation through `collect_kxbtcd_candidate_e_c2.py`.

The runner permanently exposes the full C2 cohort before request #1. If the
run is interrupted, resume only the same recognized manifested attempt.

<!-- CHECKPOINT21F_B_C2_RESULT_20260818 -->
## Checkpoint 21F-B ? Candidate-E C2 confirmation PASS

The second fresh post-H3 champion confirmation passed.

- C2 result fingerprint: `ee6cd30b32a9445096f25934d67dfa34046504ee83889947be8c8a40377a8f62`
- result closeout fingerprint: `5660e4d04856f534543f0fdd53a1b687b07666ffd52d59e8e80fcefe6ddc87cf`
- fixed Champion-R1: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- beta_distance: `0.014529004270980883`
- C2: 500 events / 14,007 rows / 2,441 labels
- raw event-equal log loss: `0.16763671430199342`
- Distance log loss: `0.05064447819587261`
- raw-minus-Distance delta: `0.11699223610612081`
- raw Brier: `0.03957031952485842`
- Distance Brier: `0.015191801215127898`
- Brier delta: `0.024378518309730521`
- median event log-loss delta: `0.13555827126142961`
- chronological wins: 5 / 5
- newest B4: win
- C2 gate: PASS
- C2 permanently exposed: yes
- model fitting/tuning on C2: no / no
- C3 materialized/opened: no
- strict never-materialized tail: 5,209
- protected floor: 4,500
- remaining reserve buffer: 709
- execution/orders: disabled / 0

The exposed expanding-fit pool is now 4,000 events / 109,971 rows:
H1 + H2 + H3 + C1 + C2.

After this result is safely closed and pushed, the next authorized step is
Champion-R2 preparation and fit only. Refit the exact unchanged
`kxbtcd_btc_distance_offset_logistic.v1` specification on those 4,000 exposed
events, freeze the resulting R2 model, and only afterward materialize C3
outcome-blind.

Do not materialize C3 before Champion-R2 is separately frozen.

<!-- CHECKPOINT21G_A_C3_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21G-A — Champion-R2/C3 preparation implementation frozen

The final historical confirmation transition is implementation-frozen before
C3 reserve access.

- implementation fingerprint: `76db878cbc62662b4f5c372f9dad73767c3bee356a9765e6204c2a0091d92357`
- parent C2 result:
  `ee6cd30b32a9445096f25934d67dfa34046504ee83889947be8c8a40377a8f62`
- parent C2 result closeout:
  `5660e4d04856f534543f0fdd53a1b687b07666ffd52d59e8e80fcefe6ddc87cf`
- parent Champion-R1:
  `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- R2 fit scope: H1+H2+H3+C1+C2
- R2 events / rows: 4,000 / 109,971
- C3 rows/outcomes in R2 fit: 0 / 0
- C3 strict-tail start: 4222
- absolute end-exclusive boundary: 4931
- maximum C3 candidate identities: 709
- protected untouched-tail floor: 4,500
- Champion-R2 fit during 21G-A: no
- C3 materialized/opened during 21G-A: no / no
- network requests: 0
- execution/orders: disabled / 0

Next: safely close 21G-A, then fit/freeze Champion-R2 network-free. Do not
start the C3 collector until Champion-R2 has its own safe closeout.

<!-- CHECKPOINT21G_B_CHAMPION_R2_20260818 -->
## Checkpoint 21G-B ? Champion-R2 frozen

Champion-R2 has been fit exactly once using the unchanged Distance
specification and only already exposed evidence.

- model: `kxbtcd_btc_distance_offset_logistic.v1`
- fit stages: H1 + H2 + H3 + C1 + C2
- fit scope: 4,000 events / 109,971 rows
- Champion-R2 fingerprint: `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- artifact SHA-256: `d5c99e0099f37eb69921934a850d1778690d53ad7045a394fa91c0e3362b2d14`
- beta_distance: `0.014501283346050064`
- fit objective: `0.053511817851523945`
- iterations: 10
- converged: yes
- C3 rows/outcomes used: 0 / 0
- C3 outcomes opened: 0
- network requests: 0
- execution/orders: disabled / 0

Champion-R1 beta_distance was `0.014529004270980883`; Champion-R2 is
`0.014501283346050064`, showing only a small coefficient change after adding
the exposed C2 evidence.

The strict historical reserve has not moved:
- next C3 queue index: 4222
- untouched tail entering C3: 5,209
- protected floor: 4,500
- maximum C3 candidate identities: 709
- absolute end-exclusive boundary: 4931

After safe closeout, the next authorized step is C3 outcome-blind
materialization only. Do not open C3 outcomes.

<!-- CHECKPOINT21G_C_C3_PREOUTCOME_20260818 -->
## Checkpoint 21G-C ? C3 pre-outcome cohort frozen

The final historical C3 confirmation cohort has been materialized and frozen
without opening outcomes.

- entering model: Champion-R2 `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- C3 events: 500
- blocks: 5 x 100
- candidate identities inspected: 533
- ineligible identities: 33
- strict queue range: `[4222, 4755)`
- pre-outcome rows: 13,549
- unique markets: 2,470
- cohort fingerprint: `08add4c28831c0d460dff706b0cc425550a4d5d3f486d3ec7f14622586101f6b`
- pre-outcome row fingerprint: `898400f7401ef9a96a9c1a0a6d2c99479395ff9fb0a13d93ea7c5fbc3dad51db`
- C3 validation fingerprint: `44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0`
- literal config SHA-256: `4e1402c6fc15ea24427524ef04d3c14105a7a4b76f75fc6e5cda54ad908965d4`
- untouched tail remaining: 4,676
- protected floor: 4,500
- reserve buffer: 176
- C3 outcomes opened: 0
- execution/orders: disabled / 0

The materializer stopped exactly when the 500th eligible event was obtained.
The first 400 eligible events required 400 identities; the next 100 eligible
events required 133 identities because 33 identities failed frozen
outcome-blind eligibility rules.

Next work must be a separate C3 evaluator implementation freeze. C3 outcomes
must remain sealed until that evaluator is safely closed and pushed.

<!-- CHECKPOINT21H_A_C3_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21H-A — C3 evaluator implementation frozen

The exact one-time evaluator that may open C3 labels is now frozen.

- implementation fingerprint: `8f84f299f21b132ffd2db93aeb1f23dc586d5d11a189a271ef707be94d15455f`
- fixed Champion-R2:
  `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- fixed beta_distance: `0.014501283346050064`
- C3 validation fingerprint:
  `44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0`
- 500 events / 13,549 rows / 2,470 market labels
- H1/H2/H3/C1/C2 hard-deny events: 4,000
- C3 outcomes opened: 0
- network requests: 0
- model fits/tuning: 0
- remaining reserve accessed: 0
- execution/orders: disabled / 0

After safe closeout, the next authorized action is the one-time C3 evaluation
through `collect_kxbtcd_candidate_e_c3.py`. Do not perform any additional
historical materialization or model repair before that run.

<!-- CHECKPOINT21H_B_C3_RESULT_20260818 -->
## Checkpoint 21H-B ? Candidate-E C3 historical confirmation PASS

The final fresh historical C3 confirmation is complete.

- run: `collect_kxbtcd_candidate_e_c3_20260818T051417765823Z_e29fd0d7`
- fixed Champion-R2: `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- C3 result fingerprint: `b37d5f5f299cf338a2bdf730f114a61b1bea25f3af820c21f81bd1fe13072b08`
- result-closeout fingerprint: `2a9ff681973608f2cdd44371eda8bf4208021610e4f3e74f887a173de1447ede`
- C3 events / rows / labels: 500 / 13,549 / 2,470
- raw log loss: `0.12097454402315916`
- Champion-R2 log loss: `0.023718447966231782`
- improvement: `0.09725609605692738`
- raw Brier: `0.025969129033350857`
- Champion-R2 Brier: `0.0064734297442716375`
- Brier improvement: `0.019495699289079221`
- median event improvement: `0.11153336786189344`
- blocks: 5 / 5 wins
- newest B4: win
- C3 gate: PASS
- fitting/tuning on C3: none
- post-hoc repair: none
- remaining reserve accessed: no
- orders: 0

The historical outcome-exposed pool is now 4,500 events / 123,520 rows:
H1 + H2 + H3 + C1 + C2 + C3.

The strict never-opened historical tail remains 4,676 identities.

Next, after safe closeout, deterministically fit the unchanged Distance
champion on the complete 4,500-event exposed pool. Do not use the
remaining reserve for that refit.

<!-- CHECKPOINT21I_A_FINAL_FIT_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21I-A — Final historical fit implementation frozen

The post-confirmation Champion-Final fit procedure is frozen.

- implementation fingerprint: `902bdd1888bb998fd67902cbfe7bf4f82b036ab32bdd41813f4012133cebf023`
- exact exposed fit pool: 4,500 events / 123,520 rows
- one unchanged Distance coefficient only
- no momentum
- no selection/search
- no fresh-validation claim
- untouched historical reserve: 4,676
- reserve rows/outcomes used: 0 / 0
- network requests: 0
- execution/orders: disabled / 0

After safe closeout, run
`fit_kxbtcd_candidate_e_final_champion.py` once to produce the final
historical parameter estimate.

<!-- CHECKPOINT21I_B_CHAMPION_FINAL_20260818 -->
## Checkpoint 21I-B ? Candidate-E Champion-Final fitted

Champion-Final is now fitted and frozen.

- fingerprint: `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- closeout: `1dd79bc396f1dee8afed150930bf5a78ee0581275193545dcde1d579d5b9c43a`
- beta_distance: `0.014939489324405949`
- fit objective: `0.050195791036485929`
- fit events / rows: 4,500 / 123,520
- stages: H1 + H2 + H3 + C1 + C2 + C3
- converged in 10 iterations
- one free parameter
- no momentum
- no specification or selection changes
- no fresh-validation claim
- remaining historical reserve: 4,676
- reserve accessed: no
- network requests: 0
- execution/orders: disabled / 0

The historical forecasting lifecycle is now complete through final
parameter estimation.

Next research task: execution-data adequacy audit using exposed
historical evidence only.

## Checkpoint 21K-A — Candidate-E Historical Strategy Replay v1 frozen

Checkpoint 21K-A is complete at the strategy-predeclaration layer.

Frozen strategy:
- ID: `kxbtcd_candidate_e_strategy_replay_v1`
- fingerprint: `afc1b397c850e8b2a2dfd32d6656e05f4622c59f1596f5b91295e96debb0d046`
- primary OOS/OOF evidence: 4,070 events / 118,862 prediction rows
- fixed baseline size: 10 contracts
- primary net-entry edge threshold: 0.04 dollars/contract
- one position maximum per event
- causal next-minute execution delay
- maximum adverse entry movement: 0.01 dollars or missed entry
- primary exit: 50% initial model-surplus capture; forced liquidation around T-5m
- hold-to-settlement: benchmark only
- base + conservative execution assumptions frozen
- exact historical fees required
- 25% Candidate-E-adjustment shrink stress frozen

H1 OOF lineage was independently reconciled against the frozen pre-outcome materialization: 31,656 / 31,656 rows matched, with zero missing or identity mismatch.

Validation:
- predeclaration validator PASS
- 9 dedicated tests passed
- full suite: 881 passed, 22 subtests passed

No historical strategy P&L has been inspected. No execution data backfill was used to tune these rules. The 4,676-event untouched historical reserve remains untouched.

Current authorization remains read-only. No demo, paper, or real-money execution is permitted.

Next checkpoint slice: 21K-B Historical Execution Data Backfill and Replay Materialization.

## Checkpoint 21K-B1 — Reusable historical execution archive contract frozen

Checkpoint 21K-B1 is complete at the archive-predeclaration layer.

Frozen archive:
- ID: `kxbtcd_candidate_e_reusable_execution_archive.v1`
- archive fingerprint: `4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea`
- allow-list fingerprint: `85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1`
- 4,070 OOS/OOF events
- 20,236 unique KXBTCD markets
- 118,862 prediction rows
- zero cross-stage event or market overlap
- untouched reserve: 4,676 events, still excluded

The archive is intentionally broader than Strategy v1's six signal anchors: it covers the available full tradable lifecycle of each allow-listed market so later separately versioned strategy variants can reuse the same offline data when their requirements stay inside the archived scope.

Frozen data classes include market metadata, one-minute candlesticks, public trades, dynamic historical-cutoff snapshots, KXBTCD series fee history, and event-level fee-change history.

Validation:
- predeclaration validator PASS
- 9 dedicated tests passed
- full suite: 890 passed, 22 subtests passed

No 21K-B network collection has yet occurred. No strategy P&L has been inspected. Current authorization remains read-only; no paper, demo, or real-money execution is permitted.

Next checkpoint slice: 21K-B2 Raw-first Resumable Archive Collector.

<!-- CHECKPOINT21K_B2_PROJECT_STATE_20260818 -->
## Checkpoint 21K-B2 — reusable execution archive collector implemented

The frozen Candidate-E execution archive now has a validated public/read-only
raw-first resumable collector implementation.

Frozen archive identity remains unchanged:
- archive `kxbtcd_candidate_e_reusable_execution_archive.v1`
- archive fingerprint
  `4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea`
- allow-list fingerprint
  `85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1`
- 4,070 OOS/OOF events / 20,236 markets / 118,862 prediction rows

Implemented:
- existing append-only raw JSONL transport reused as source of truth
- transactional SQLite resume/cache index
- dynamic historical cutoff routing
- market metadata live/historical reconciliation
- one-minute full-lifecycle candles
- paginated public trades and cross-tier trade-ID deduplication
- series and event fee-history collection
- explicit candle-missingness coverage
- bounded smoke scopes
- fail-closed approved-GET guard
- resume database v2 with inherited raw-session lineage
- completed-manifest inventory of every contributing raw JSONL file

Five-market smoke validation passed after two implementation findings were
corrected:
1. `/historical/trades` was missing from the local read-only path guard;
2. completed resumed manifests initially omitted inherited raw files from the
   receipt even though row-level lineage and raw JSONL files were preserved.

Final lineage-validation run:
`collect_kxbtcd_candidate_e_execution_archive_20260818T072801523739Z_6c152eb7`

It reused 17 tasks, completed only 1 new task, and finalized with 3 contributing
source sessions / 3 raw files / 19 raw records / 0 raw errors.

Final regression:
- 13 dedicated collector tests passed
- 903 full-suite tests + 22 subtests passed

Current safety/governance:
- Strategy v1 P&L remains unopened.
- Candidate-E/model specification unchanged.
- 4,676-event historical reserve remains untouched.
- no paper/demo/real execution is authorized.
- `docs/RISK_POLICY.md` is unchanged.

Next checkpoint: 21K-B3 bounded 100-market archive pilot from a clean
synchronized B2 closeout. Full 20,236-market collection remains deferred until
that pilot's coverage/lineage audit passes.

<!-- CHECKPOINT21K_B3_PROJECT_STATE_20260818 -->
## Checkpoint 21K-B3 — bounded 100-market archive pilot PASS

The frozen reusable execution-archive collector has passed a bounded 100-market
public/read-only pilot across 20 H1_OOF events.

Primary run:
`collect_kxbtcd_candidate_e_execution_archive_20260818T073532996950Z_c3f5d471`

Key engineering evidence:
- 100/100 market tasks materialized
- 322 tasks completed
- 253 raw records
- 0 raw errors
- 0 runtime errors
- 100 market metadata rows
- 20 event metadata rows
- 10,864 one-minute candle rows
- 1,356 public trade rows
- all returned candles had two-sided close quotes
- trade rows reconciled exactly with per-market coverage counts

Historical candles are materially sparse:
- full-lifecycle coverage: 53.2549%
- last-55-minute coverage: 91.4727%
- last-60-minute coverage: 90.8167%
- 64/100 markets had all six Strategy-v1 signal+next-minute entry pairs
- 100/100 had at least one usable entry pair
- 95/100 had at least one T-5..T-1 force-exit candle
- 19/20 events had at least one usable market at every entry anchor
- `KXBTCD-25APR2915` lacked T-55 entirely
- `KXBTCD-25APR2913` lacked all T-5..T-1 force-exit markets

Missing decision states remain fail-closed:
- no candle imputation
- no synthetic entry fill
- no synthetic exit price
- settlement fallback only where already frozen by Strategy v1

Resume validation:
`collect_kxbtcd_candidate_e_execution_archive_20260818T074121445450Z_a4e2cf72`
reused 321 tasks, completed 1 fresh task, and finalized with 2 source sessions /
2 raw files / 254 raw records / 0 raw errors.

Current governance:
- Strategy-v1 P&L remains unopened.
- Candidate-E/model unchanged.
- 4,676-event protected reserve untouched.
- no paper/demo/real execution is authorized.
- `RISK_POLICY.md` unchanged.

Next checkpoint: 21K-B4 — full 20,236-market reusable execution archive collection
from a clean synchronized B3 closeout, followed by a full-universe coverage/fee/
lineage audit before any strategy P&L scoring.

<!-- CHECKPOINT21K_B4A_CANDLE_CHUNKING_STATE_20260818 -->
## Checkpoint 21K-B4A — candle-range transport repair validated

The first Checkpoint 21K-B4 full execution-archive run stopped fail-closed on
historical candlesticks for `KXBTCD-25AUG0117-T104999.99`.

Kalshi's archived HTTP 400 response reported a 10,140-period requested range
against a 5,000-candlestick maximum.

The collector now:
- keeps the original full market lifecycle;
- splits long one-minute candle lifecycles into deterministic <=5,000-period
  request windows;
- overlaps exact boundaries and de-duplicates them by `end_period_ts`;
- fails closed on inconsistent duplicate boundary candles;
- preserves raw lineage for every request window;
- commits the candle resume task only after the complete window chain validates.

Validation status:
- dedicated collector/chunking tests: 16 passed;
- full regression suite: 906 passed, 22 subtests passed.

The archive universe, Candidate E, Strategy Replay v1, risk authorization, and
protected reserve policy are unchanged. Strategy-v1 P&L remains unopened.

Next after safe B4A closeout:
resume the same full archive collection from the existing scope-bound
`full.sqlite`; do not restart completed work.

## Checkpoint 21K-B4B state

The full Candidate-E reusable execution archive is complete and has passed its
readiness audit with limitations.

The archive contains 4,070 OOF/OOS events and 20,236 markets. Structural integrity
passed. Exact entry-state coverage is sufficient for separately predeclared causal
Entry Model research, but historical one-minute candle availability is sparse and
contains a strong archive-regime component.

Accepted rule: Entry Model v1 may use directly observed market activity and
microstructure variables, but raw candle missingness and calendar-date proxies are
not initial predictive features. Missing required states are abstentions, not
imputed observations.

Strategy P&L remains unopened. The protected 4,676-event reserve remains untouched.
Next: Entry Model v1 predeclaration.

## Checkpoint 21L ? Entry Model v1 architecture accepted

Entry Model v1 will use frozen Candidate E as a probability baseline/offset and
learn only an incremental settlement-probability adjustment from causal
entry-state features.

Primary target: binary settlement outcome.

Economic expected value will be calculated deterministically from the resulting
probability, executable entry price, and exact fees rather than learned directly
as a P&L target.

Position management remains a separate future modeling problem.

Next design task: freeze the Entry Model v1 feature contract before fitting,
feature screening, Strategy-v1 P&L inspection, or protected-reserve access.

## Checkpoint 21L ? feature contract frozen

D-021L-01 target/architecture and D-021L-02 feature contract are now frozen.

The exact 118,862-row Candidate-E downstream state universe normalizes without conflict, and every row has the exact contemporaneous quote candle required by Entry Model v1.

Model-2 fitting remains prohibited until the whole-event chronological split, model-family/tuning contract, evaluation metrics, and advancement gates are predeclared and closed.

Strategy-v1 P&L remains unopened. The protected 4,676-event reserve remains untouched.

## Checkpoint 21L ? chronological evidence roles frozen

D-021L-03 freezes the whole-event chronological Model-2 evidence roles:

- development = H1_OOF + H2 + H3
- validation = C1 + C2
- Model-2 locked test = C3

Counts:
- development: 2,570 events / 76,419 rows
- validation: 1,000 events / 28,894 rows
- locked test: 500 events / 13,549 rows

The chronology audit passed with no event-stage conflicts and strict temporal ordering across all six stages.

C3 is locked against Model-2 development but is not described as globally untouched evidence because the 4,070-event pool has already participated in Candidate-E research.

The protected 4,676-event historical reserve remains untouched.

Model-2 fitting remains prohibited until the model-family/tuning contract, preprocessing, evaluation metrics, and advancement gates are frozen.

## Checkpoint 21L ? Model-2 model family frozen

D-021L-04 freezes Candidate-E Entry Model v1 as:

`kxbtcd_candidate_e_entry_residual_logistic.v1`

The model is a small L2-regularized logistic residual around frozen Candidate E.

Key frozen mechanics:
- Candidate-E probability is a fixed exact logit offset
- 21 learned residual coefficients
- all residual coefficients including intercept are L2-penalized
- fit-only event-equal weighted z-scaling
- no interactions or nonlinear model family
- lambda grid = 0.001, 0.01, 0.1, 1, 10
- tuning Fold 1: H1_OOF -> H2
- tuning Fold 2: H1_OOF+H2 -> H3
- primary lambda selection = pooled H2+H3 event-equal log loss
- exact tie chooses larger lambda
- deterministic damped Newton / Cholesky implementation
- no C1/C2/C3 use in tuning

Outcome-blind preprocessing feasibility passed on all 76,419 development rows.

Model-2 fitting remains prohibited until evaluation metrics, validation/locked-test advancement gates, and deterministic economic evaluation are frozen.

## Checkpoint 21L ? statistical gates frozen

D-021L-05 freezes the Model-2 statistical validation and locked-test gates.

Validation:
- C1+C2
- 1,000 events
- five chronological 200-event blocks

All required:
- pooled event-equal log loss beats Candidate E
- pooled Brier is no worse
- >=4/5 block log-loss wins
- newest-block win
- positive median event-level log-loss improvement

Only after validation PASS may the selected-lambda model be refit on:
- H1_OOF+H2+H3+C1+C2
- 3,570 events / 105,313 rows

C3 remains outside that fit.

C3:
- 500 events
- five chronological 100-event blocks
- same five-condition statistical gate

A C3 PASS establishes only historical incremental probability validation over Candidate E.

Economic-entry validity remains unresolved and separate.

The protected 4,676-event reserve remains untouched.

## Checkpoint 21L ? strategy-neutral economics frozen

D-021L-06 freezes only the economic translation from probability and quotes.

Model 2 does not contain a trading strategy.

Frozen outputs include:
- quoted YES/NO purchase-price references
- gross settlement-value edge
- standard-fee net EV as a function of hypothetical quantity

No fixed quantity or EV threshold is selected.

Positive EV is not an automatic entry instruction.

No anchor, strike, side, sizing, ranking, bankroll, position-management, or fill policy is frozen in Checkpoint 21L.

The archive fee-metadata audit passed:
- 20,236 binary linear-cent markets
- no event fee overrides
- no historical event or KXBTCD series fee-change rows
- KXBTCD quadratic multiplier = 1

D-021L-05 remains the statistical Model-2 advancement gate.

The complete Checkpoint-21L Model-2 predeclaration is now design-complete but remains uncommitted and unfitted pending safe checkpoint closeout.
<!-- CHECKPOINT21M_IMPLEMENTATION_PREPARATION_20260819 -->
## Checkpoint 21M — Entry Model v1 implementation preparation

Canonical start state verified before design/implementation:
- `main`: `cf3c2613a2a06350cf3ef7fa67ff11214e1bf72d`
- Checkpoint-21L content commit: `b65e03ceaab2c5c404bf363ad28ba180f5eb16d9`
- Checkpoint-21L receipt commit: `cf3c2613a2a06350cf3ef7fa67ff11214e1bf72d`
- prior receipt regression evidence: 906 passed + 22 subtests

Bookkeeping clarification: commit `b65e03ceaab2c5c404bf363ad28ba180f5eb16d9`
was accidentally given the message `Checkpoint 21M — Candidate-E Entry Model v1
Implementation and Development Evaluation Preparation`, but its contents are the
completed Checkpoint-21L predeclaration closeout. This is a naming-only metadata
mistake. Git history must not be rewritten; receipt `cf3c2613...` remains the
canonical 21L closeout receipt.

Checkpoint 21M does not redesign D-021L-01 through D-021L-06. It implements:
- deterministic H1_OOF/H2/H3 outcome-blind Model-2 feature materialization;
- exact-candle and strict causal five-minute trade aggregation;
- deterministic whole-event development event map and fingerprints;
- a preparation freeze binding source, implementation, and persisted-output hashes;
- separate exact-state label attachment after feature freezing;
- the frozen 21-parameter event-equal residual-logistic mechanics;
- deterministic damped-Newton/Cholesky fitting machinery;
- the frozen H1_OOF->H2 and H1_OOF+H2->H3 tuning machinery;
- an independent persisted-preparation validator.

Validation before canonical integration used synthetic fixtures only:
- Python 3.13.5 / pytest 9.0.2
- 25 focused tests passed
- byte-compilation PASS

This is implementation evidence, not a predictive result. No real Model-2 fit was
performed by the preparation step. Strategy-v1 P&L remains unopened. C3 remains
closed for Model-2 evaluation. The protected 4,676-event reserve remains untouched.
No paper, demo, or real execution was added. `docs/RISK_POLICY.md` is unchanged.

Canonical Windows validation and the real outcome-blind development preparation
freeze remain pending before any development outcomes are attached or Model 2 is
fit on project data.
<!-- CHECKPOINT21M_TIMESTAMP_ALIGNMENT_CLARIFICATION_20260819 -->
### Checkpoint 21M pre-fit timestamp-alignment correction

Canonical Windows implementation validation completed before the first real-data
preparation attempt:
- focused 21M tests: 25 passed
- full repository regression: 931 passed + 22 subtests

The first real outcome-blind materialization then failed closed before producing an
output directory. Failing state:
`KXBTCD-25APR2823|KXBTCD-25APR2823-T93999.99|TTC30|q50`.

Diagnosis:
- scheduled decision: `2025-04-29T02:30:00Z`
- frozen Candidate-E `kalshi_quote_end_period_ts`: `1745893740` = 02:29:00Z
- frozen staleness: 60 seconds
- archive allow-list contains the market
- archive contains the exact 02:29 candle
- archive has no 02:30 candle for that market

The initial 21M code had incorrectly required a candle at the scheduled decision
minute. Candidate E's pre-existing frozen historical contract instead selects the
latest valid real two-sided Kalshi quote at or before the scheduled target with at
most 60 seconds of staleness. The decision time remains the scheduled TTC target.

21M therefore reconstructs the exact already-frozen Candidate-E quote timestamp.
It does not select a nearest/later replacement. Quote timestamp must be <= decision
time, stated staleness must equal the timestamp difference and lie in [0,60], and
the exact archive candle close must match the frozen Candidate-E YES bid/ask.

This clarification occurred before outcome attachment, Model-2 fitting, Strategy-v1
P&L, C3 Model-2 evaluation, or protected-reserve access. D-021L-01 through D-021L-06
are not redesigned; the imprecise 21L phrase "candle ending at the decision
timestamp" is clarified against Candidate E's already-frozen source-state semantics.
<!-- CHECKPOINT21M_PREPARATION_ACCEPTANCE_20260819 -->
### Checkpoint 21M outcome-blind development preparation — ACCEPTED

Canonical Windows validation after the D-021M-02 timestamp-alignment correction:
- focused Checkpoint-21M tests: 29 passed in 1.27s
- full repository regression: 935 passed + 22 subtests in 30.75s

Real outcome-blind development preparation then completed and independently
rematerialized PASS:
- H1_OOF: 1,070 events / 31,656 rows
- H2: 750 events / 22,354 rows
- H3: 750 events / 22,409 rows
- total: 2,570 events / 76,419 rows
- feature-row fingerprint: `a726785e667dc42cef75a7b1f9c0b42ae81a4906b1d72ff5eb0f58ed5083b2a7`
- development event-map fingerprint: `36bd74d8576cf8656a4d4a352330fabd2294c322c5cd91854ed47892fe04a266`
- preparation fingerprint: `2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`
- persisted feature CSV SHA-256: `0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c`
- persisted event-map CSV SHA-256: `fe627d8bf3c91ef77e811a83f75f3a3b0542ba0df755cf34cc78f8d9e617bddd`
- independent source rematerialization: PASS
- independent implementation-hash verification: PASS

The preparation freeze binds all seven source-file hashes, the four relevant
implementation-file hashes, persisted output hashes, scientific fingerprints, and
explicit persisted safety flags. The feature rows contain no outcomes. The independent
validator additionally reported `model2_fit_performed=false`; that status is
procedural evidence and is intentionally not a field in the preparation-freeze schema.

Safety at acceptance:
- outcomes in feature rows: false
- Model-2 fit performed: false (independent validator evidence; not a freeze-JSON field)
- Strategy-v1 P&L calculated: false
- C3 opened for Model-2: false
- protected 4,676-event reserve accessed: false
- execution enabled: false

This accepts the 21M preparation gate only; it is not a forecasting result and does
not establish market edge or profitability. Checkpoint 21M remains open for the
frozen development-label attachment and rolling-origin development evaluation.
C1/C2 validation, C3, Strategy-v1 economics, the protected reserve, and execution
remain outside the current step.

<!-- CHECKPOINT21M_DEVELOPMENT_EVALUATION_IMPLEMENTATION_20260819 -->
### Checkpoint 21M development-evaluation orchestration — implementation frozen before outcomes

The accepted outcome-blind preparation boundary is commit
`cc91a15ae65954370279025d1afe6c857c8d899b` with preparation fingerprint
`2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`.

A narrow development-only orchestration layer is now implemented for the already
frozen D-021L-04 procedure. It accepts only the frozen 76,419-row feature file,
its preparation freeze, and the already-exposed H1_OOF/H2/H3 Candidate-E
prediction/evaluation sources. It filters H1 non-Candidate-E challenger rows,
attaches outcomes only by exact `state_id`, executes the frozen two-fold lambda
procedure, persists deterministic results/receipt hashes, and has an independent
full deterministic recomputation validator.

This implementation is to be committed/pushed before real Model-2 development
outcomes are evaluated. C1/C2, C3, the protected reserve, Strategy-v1 P&L, and all
execution remain closed.

<!-- CHECKPOINT21M_EVENT_EQUAL_WEIGHT_PRECISION_REPAIR_20260819 -->
### Checkpoint 21M development evaluation — post-outcome numerical guard repair

The first real Model-2 H1_OOF/H2/H3 development-evaluation attempt crossed the
predeclared development-outcome boundary but failed before a result receipt was
persisted. The failure occurred during the final full-development scaler setup:
`event_equal_weights()` rejected a mathematically correct event-equal weight vector
because ordinary floating-point `sum(weights)` differed from 1 by
`1.317168596415285720e-12`, slightly beyond the existing `1e-12` integrity guard.

A direct diagnostic on the frozen 76,419 rows / 2,570 events showed:
- ordinary sum = `1.000000000001317169`;
- ordinary absolute error = `1.317168596415285720e-12`;
- `math.fsum(weights)` = `1.000000000000000000`;
- `math.fsum` absolute error = `0`.

Therefore H1_OOF/H2/H3 development labels are now considered exposed. No Model-2
development result from the failed attempt is accepted. The permitted repair changes
only the numerical summation used by the invariant check from `sum` to `math.fsum`.
The event-equal weight formula, row universe, features, scaling definition, lambda
grid, optimizer, metrics, and predeclared rolling-origin procedure are unchanged.

Canonical validation of this repair is pending before any development-evaluation
rerun. C1/C2, C3, protected reserve, Strategy-v1 P&L, and execution remain closed.

<!-- CHECKPOINT21M_POST_OUTCOME_CORE_HASH_AMENDMENT_20260819 -->
### Checkpoint 21M development evaluation — exact repaired-core hash amendment

After the accepted D-021M-05 `math.fsum` repair was committed and pushed at
`80afd386c805f80505bc33174ad7b8ff8cdf1c70`, the next development-evaluation
attempt failed closed before fitting because the evaluator still required the
current Model-2 core file to equal the original preparation-freeze implementation
hash.

Targeted diagnostic:
- preparation-frozen core SHA-256:
  `1e56a207e72a96a4425d0c6c6796d9781eac363baef5bb0dab3b3b58daa34a1b`;
- current accepted repaired core SHA-256:
  `ce54846f85f3d338bc0f3aadd64d8cc8b9828c0c2ac2b5454f97771ec1a89ee1`;
- hashes equal: false;
- attempted output directory existed but contained 0 items.

The original preparation freeze remains immutable. The development binding is
amended to require BOTH:
1. the freeze still contains the original pre-outcome core hash; and
2. the current core exactly equals the one D-021M-05 repaired hash above.

No arbitrary changed core is accepted. No scientific model/evaluation rule changes.
The empty `development_evaluation_v1` directory is retained as failed-attempt
evidence; a later accepted rerun must use a fresh output directory.

C1/C2, C3, protected reserve, Strategy-v1 P&L, and execution remain closed.

<!-- CHECKPOINT21M_DEVELOPMENT_RESULT_FREEZE_20260819 -->
### Checkpoint 21M — Candidate-E Entry Model v1 development result frozen

The independently validated Model-2 development evaluation is accepted as
development-selection evidence.

Frozen identity:
- model: `kxbtcd_candidate_e_entry_residual_logistic.v1`;
- development universe: 2,570 events / 76,419 rows;
- development label fingerprint:
  `a41f3f31d9df31119cfe0232052166b478714d68ebed1aed699227262edb3572`;
- evaluation fingerprint:
  `78de7bf612830c7fbbeb14b56a34bd1a582f8e69738672d420314b1c4ff79aac`;
- selected lambda: `0.01`;
- development-freeze fingerprint:
  `a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e`.

Selected rolling-origin pooled H2+H3:
- Model-2 event-equal log loss: `0.03736587903471904`;
- Candidate-E event-equal log loss: `0.03740705507861643`;
- Candidate-E-minus-Model-2 delta: `+0.0000411760438973896`;
- Model-2 event-equal Brier: `0.010091977884008856`;
- Candidate-E event-equal Brier: `0.010095108827365279`;
- Candidate-E-minus-Model-2 Brier delta: `+0.0000031309433564229855`;
- median event Candidate-E-minus-Model-2 log-loss delta:
  `+0.00012469097768141543`.

H2 improved versus Candidate E; H3 worsened slightly. Therefore this is a narrow
development-selection result, not a generalization PASS. The exact selected
development fit (21 residual coefficients plus fit-only scaler) is now frozen in
`configs/kxbtcd_candidate_e_entry_model_v1_development_freeze.json`.

The next permitted scientific step is the already-predeclared C1+C2 validation
gate using this frozen model without retuning. C3, protected reserve, Strategy-v1
P&L, and execution remain closed.

<!-- CHECKPOINT21M_C1C2_VALIDATION_PREPARATION -->
### Checkpoint 21M — C1+C2 Model-2 validation preparation frozen outcome-blind

The exact 1,000-event / 28,894-row C1+C2 validation universe is prepared
outcome-blind and assigned to five chronological 200-event blocks.

Validation-preparation fingerprint: `25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22`.

Next permitted step: freeze and commit the C1+C2 validation evaluator that scores
the already-frozen development Model-2 against Candidate E under D-021L-05.
Do not read C1/C2 outcome rows for Model-2 before that evaluator is committed.

<!-- CHECKPOINT21M_VALIDATION_EVALUATOR_IMPLEMENTATION_FREEZE -->
### Checkpoint 21M — C1+C2 Model-2 validation evaluator frozen before outcomes

The only implementation permitted to perform the D-021L-05 C1+C2 validation gate
is frozen at:

`8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`.

The evaluator uses the exact development-selected residual model and scaler plus
the outcome-blind finite Candidate-E offset sidecar. It has no fitting, retuning,
C3, reserve, P&L, or execution surface.

C1/C2 outcome rows have still not been read for Model-2. The next permitted step
after this implementation is committed and pushed is one deterministic C1+C2
validation evaluation under the frozen attempt journal.

<!-- CHECKPOINT21M_VALIDATION_RESUME_REPAIR -->
### Checkpoint 21M — C1+C2 outcomes opened; validation pending exact resume repair

C1+C2 are now permanently opened for Model-2 under the original evaluator
fingerprint `8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`.

No validation score exists yet. The first attempt stopped on a deterministic
preparation-freeze safety-field nesting bug before scoring.

The only authorized continuation is the exact D-021M-11 resume repair:
`fee1063a637c99749e47d67bbb553a480d3e72037be1cb9015b26b67f2275aed`.

Fresh attempts are prohibited. After this repair is tested, committed, pushed, and
remotely verified, resume the same attempt with `--resume`. C3, protected reserve,
Strategy-v1 P&L, and execution remain closed.

<!-- CHECKPOINT21M_MODEL2_VALIDATION_FAIL_CLOSEOUT -->
## Checkpoint 21M — Model-2 C1+C2 validation closed as FAIL

Candidate-E Entry Model v1,
`kxbtcd_candidate_e_entry_residual_logistic.v1`, has completed the frozen C1+C2
validation gate and is **REJECTED**.

- C1+C2 scope: 1,000 events / 28,894 rows.
- Candidate E log loss: `0.0518981214127418`.
- Model-2 log loss: `0.051982434232278454`.
- Candidate E Brier: `0.015171565220600291`.
- Model-2 Brier: `0.01519915292120419`.
- Model-2 block wins: `1/5`.
- Newest-block win: `False`.
- Validation gate: FAIL.
- Deterministic independent result validation: PASS.
- Evaluation fingerprint: `15a6557736204ca58039906434f8b7e83bca719f14cd0a3b4c9b9094e42ce033`.
- Result closeout fingerprint: `f27dba7fc5fcf9726a3699b8e611646d0d93b77a3dfdb8050048767a97c36ff7`.

C1+C2 are now exposed Model-2 evidence. No post-hoc repair/retune/rescore is
permitted on them. C3 remains sealed for Model-2 v1. The protected reserve,
Strategy-v1 P&L, and execution remain untouched.

Next research must begin with a separate successor predeclaration/evidence design;
do not open C3 merely because Model-2 failed.

<!-- CHECKPOINT21N_A_QUOTED_ENTRY_HOLD_STATE -->
## Checkpoint 21N-A — Candidate-E quoted-entry/hold strategy design frozen before P&L

The project has pivoted from another immediate probability-model search to the simpler downstream economic question: can frozen Candidate E identify useful quoted settlement-value opportunities?

New strategy identity:
- `kxbtcd_candidate_e_quoted_entry_hold_v1`
- predeclaration fingerprint: `5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6`

The earlier `kxbtcd_candidate_e_strategy_replay_v1` design is preserved but is now `superseded_before_economic_scoring`. No P&L was opened under it.

21N-A freezes:
- Candidate E unchanged as the probability engine;
- one-contract standard-fee quoted YES/NO economics;
- anchors T-55 through T-30 in five-minute steps;
- threshold menu 0c/1c/2c/3c/5c after fees;
- first qualifying anchor, largest edge within anchor, deterministic tie break;
- maximum one entry per event;
- later hold to settlement only;
- H1_OOF+H2+H3 as the only authorized outcome-independent opportunity-audit evidence;
- C1+C2 Strategy-v1 economics still closed;
- C3 and the protected reserve still sealed.

No Strategy-v1 realized P&L has been calculated. No execution is authorized.

Next: validate/commit the 21N-A design and audit implementation, then run only the outcome-independent H1_OOF+H2+H3 opportunity audit. Its purpose is to measure opportunity frequency and composition before any settlement P&L is opened.

<!-- CHECKPOINT21N_B_DEVELOPMENT_ECONOMICS_PREDECLARATION_20260830 -->
## Checkpoint 21N-B — Strategy-v1 development economics predeclaration prepared

Checkpoint 21N-A is safely closed at checkpoint commit
`95b5bfa0e386c1391e6b176c990bcd049e083850` with receipt
`730fd3a79574951d7501ad7f12f67f673fdba523`.

The outcome-independent opportunity audit completed on H1_OOF+H2+H3:
- audit fingerprint: `7175175f11bb2714d4bbfc9dc59d9d23d7be721fa0295d7ed664d598a1036ae0`
- 2,570 events / 76,419 Candidate-E probability rows
- threshold entries: 0c=820, 1c=542, 2c=306, 3c=159, 5c=33
- no settlement outcomes used
- no realized Strategy-v1 P&L calculated
- C1/C2 Strategy-v1 economics unopened
- C3 and protected reserve unopened

21N-B freezes the development economic evaluator before P&L:
- one-contract hold-to-settlement realized economics;
- +0c/+1c/+2c/+3c adverse purchase-price stress;
- primary metric: mean net P&L per event including abstentions as zero;
- five chronological 514-event development blocks;
- 0c/1c/2c/3c eligible for selection; 5c diagnostic-only;
- five-condition development gate;
- winner = highest +1c stressed mean P&L/event among passing eligible thresholds;
- exact tie -> higher threshold;
- no passing threshold -> FAIL.

21N-B predeclaration fingerprint:
`692b7239067b3024db908fc0e0809f33f900f685faec97c45743195e19d364e5`.

Canonical Windows validation and safe closeout of this implementation remain pending.
Do not run the real development P&L evaluator until this implementation is committed and pushed.
C1/C2 Strategy-v1 P&L, C3, protected reserve, paper/demo/real execution remain closed.

<!-- CHECKPOINT21N_C_DEVELOPMENT_RESULT_20260830 -->
## Checkpoint 21N-C — Strategy-v1 development economics closed as FAIL

The frozen Candidate-E quoted-entry/hold Strategy-v1 development evaluation is complete and is a **FAIL**.

- strategy: `kxbtcd_candidate_e_quoted_entry_hold_v1`
- strategy fingerprint: `5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6`
- opportunity-audit fingerprint: `7175175f11bb2714d4bbfc9dc59d9d23d7be721fa0295d7ed664d598a1036ae0`
- development-economics predeclaration fingerprint: `692b7239067b3024db908fc0e0809f33f900f685faec97c45743195e19d364e5`
- evaluation fingerprint: `8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc`
- status: `FAIL_NO_THRESHOLD`
- selected threshold: none

Closest policy: 3c after standard fee.
- 159 entries / 2,570 events
- base total P&L: +$2.64
- base mean P&L/event: +$0.001027237354085603112840466926
- +1c total P&L: +$1.06
- +1c mean P&L/event: +$0.0004124513618677042801556420233
- positive base chronological blocks: 4/5
- newest B4 total P&L: -$2.50
- newest B4 mean P&L/event: -$0.00486381322957198443579766537
- H3 total P&L: -$0.63
- H3 mean P&L/event: -$0.00084
- +2c pooled total P&L: -$0.46

The 3c policy therefore failed the predeclared newest-block and H3 conditions despite positive pooled economics. No other selection-eligible threshold passed.

H1_OOF/H2/H3 Strategy-v1 economics are now exposed development evidence. C1+C2 Strategy-v1 economics remain unopened; C3 and the protected 4,676-event reserve remain sealed. No execution is authorized.

Next: perform a separately bounded failure analysis using only already-exposed development Strategy-v1 evidence to understand the B4/H3 degradation before specifying any successor strategy. Do not tune a replacement strategy on this checkpoint result.

<!-- CHECKPOINT21N_D_FAILURE_ANALYSIS_DESIGN_20260830 -->
## Checkpoint 21N-D — development failure-analysis design frozen

21N-C is closed as `FAIL_NO_THRESHOLD`. Candidate E remains Champion-Final;
the rejected object is the simple quoted-entry/hold Strategy-v1 family.

21N-D freezes a development-only diagnostic on the 159 already-selected 3c
displayed-quote trades. It will compare H2 vs H3 and B3 vs B4 and report
predeclared stage/block/side/TTC/role/price/fair-probability/edge slices plus
gross-vs-fee decomposition and loss-tail concentration.

Failure-analysis predeclaration fingerprint:
`33fb68841a174d50971d40aefae73ab564f96adcb8aefafcf5e86aa16d21bc8b`.

This analysis is descriptive only. It may generate successor hypotheses but
cannot select or fit a successor or mutate Strategy-v1.

Immediate next action after safe closeout: run the frozen analyzer once against
the canonical 21N-B result directory and inspect the deterministic outputs.
C1+C2 strategy P&L, C3, reserve, and execution remain closed.

<!-- CHECKPOINT21N_E_FAILURE_RESULT_AND_SUCCESSOR_DIRECTION_20260830 -->
## Checkpoint 21N-E — failure result frozen; successor direction preselected

Failure-analysis fingerprint: `e9b88ded9fe1db1f89e234ad626023c67038bbea84ae35863b817c3858f4a3ef`. Result-closeout fingerprint: `bdbdf4db9b83410b3e9689a4ed5ed66ba995be507c5bacea32a6b59c74678dad`.

Candidate E remains Champion-Final. Strategy-v1 remains rejected. Next research family is a deterministic reliability-adjusted entry/abstention baseline; learned entry/meta-model work is deferred until it can challenge that simpler baseline.

Immediate next task: freeze Strategy-v2's exact non-post-hoc reliability adjustment and fresh-evidence protocol before scoring.

<!-- CHECKPOINT21N_F_RELIABILITY_SHRINKAGE_DESIGN_20260830 -->
## Checkpoint 21N-F — Strategy-v2 reliability-shrinkage design frozen

Next candidate family:
`kxbtcd_candidate_e_reliability_shrinkage_entry_v2`.

Candidate E is unchanged. The decision probability is shrunk toward the
contemporaneous Kalshi midpoint with alpha 0.25/0.50/0.75; alpha 1 is reference
only. Qualification is adjusted net edge >= 0.

The next action after safe closeout is an **outcome-independent opportunity
audit**, not P&L. It must exactly reproduce Strategy-v1 at alpha=1 and quantify
how much lower alpha values actually change the decision set.

A 10% decision-materiality screen is frozen. If no sample-eligible alpha changes
at least 10% of alpha=1 decisions, stop simple shrinkage before another
outcome-aware evaluation.

Predeclaration fingerprint: `b3fd3a3c71c5750604ef4e6eddd23043a75952d2c06a48cbb39ae6ef1066bd50`.

<!-- CHECKPOINT21N_G_SHRINKAGE_ECONOMICS_20260831 -->
## Checkpoint 21N-G — Strategy-v2 opportunity result and economics evaluator frozen

21N-F audit fingerprint: `b0971d51ac76fc26402dfbab49fde85167cb0bb4153069b80d1db2dbaccdcf20`.

Opportunity result:
- alpha .25: 15 entries — sample-ineligible; do not score outcomes;
- alpha .50: 276 entries — development economics eligible;
- alpha .75: 591 entries — development economics eligible;
- alpha 1: 820 entries — exact Strategy-v1 reference; do not rescore.

Only .50 and .75 may be evaluated economically after 21N-G is safely
closed/pushed. The frozen gate requires positive base and +1c pooled P&L/event,
>=4/5 positive blocks, positive newest block, and positive H3.

Economics fingerprint: `139435ffb43d51d09afa4154aeba2fe9c22cb82b5b7edd435516d4ab71e2c55f`.

C1+C2/C3/reserve/execution remain closed.

<!-- CHECKPOINT21N_H_CONDITIONAL_ALPHA_ARCHITECTURE_20260831 -->
## Checkpoint 21N-H — Strategy-v2 closed; conditional-alpha architecture accepted

Strategy-v2 final status: `FAIL_NO_ALPHA`.

- alpha .50: 276 entries, +$4.75 base, +$2.02 at +1c, H3/B4 positive, but only 3/5 positive base blocks -> FAIL.
- alpha .75: 591 entries, -$0.29 base, -$6.05 at +1c, 2/5 positive blocks, H3/B4 negative -> FAIL.

Global-alpha repair is closed.

Next research architecture learns a state-conditional reliability weight:

`alpha_i = sigmoid(gamma_0 + gamma^T X_i)`

and adjusts between Kalshi midpoint and frozen Candidate E.

This checkpoint does not fit the model. Exact features, objective, weighting,
regularization, tuning, evidence roles, entry rule, and gates remain for 21N-I.

C1/C2 conditional-alpha use is not authorized. C3 and protected reserve remain
closed.

Result closeout fingerprint: `02b8aab23161419abd1cdf02c79072f070067ed28f16ef186959e6fc5b3f5ee4`.
Architecture fingerprint: `bb7ebb7b12a9b817465e9e522d65b2f5a129f9e5aaa12a1c8ac6e5fd666a6742`.

<!-- CHECKPOINT21N_I_CONDITIONAL_ALPHA_EXACT_PREDECLARATION_20260831 -->
## Checkpoint 21N-I — conditional-alpha exact predeclaration frozen

The smallest conditional-alpha v1 design is now frozen before fitting.

- candidate: `kxbtcd_candidate_e_conditional_alpha_reliability.v1`
- four features: absolute Candidate-E/market disagreement, spread, absolute 5m BTC return, continuous TTC
- five learned gamma parameters including intercept
- initialization: all gamma=0 -> alpha=.50 for every state
- all gamma parameters L2-regularized
- lambda grid: .001/.01/.1/1/10
- deterministic full-batch BFGS predeclared
- rolling origin: H1_OOF->H2 and H1_OOF+H2->H3
- probability selection score: pooled H2+H3 event-equal log loss
- development economics: H2+H3 rolling-origin predictions only, 1,500 events / five 300-event blocks
- no full-development in-sample economic gate
- C1+C2 later non-fresh confirmation only after complete development PASS and separate full-fit freeze
- C3 remains locked against conditional-alpha development
- reserve remains sealed
- no fit/outcome scoring/execution in 21N-I

Historical reliability supervision must use frozen stage OOF/OOS Candidate-E
predictions rather than regenerated Champion-Final in-sample predictions.

Predeclaration fingerprint: `742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`.

<!-- CHECKPOINT21N_J_A_CONDITIONAL_ALPHA_IMPLEMENTATION_20260831 -->
## Checkpoint 21N-J-A — conditional-alpha implementation prepared

The exact 21N-I design is now represented by deterministic, network-free code.

Implemented:
- four-feature projection contract;
- event-equal fit-partition scaler;
- bounded alpha/probability transform;
- five-parameter L2 objective/gradient;
- deterministic full-batch BFGS mechanics;
- frozen quote-entry selection mechanics;
- outcome-blind projection from the exact frozen 21M state universe;
- independent rematerialization validator;
- executable J-A closeout-receipt gate before the real J-B materializer can run.

Scientific results remain unopened. No real gamma fit, lambda selection, outcome
score, conditional-alpha P&L, C1/C2/C3 access, reserve access, or execution is
performed by 21N-J-A.

Canonical Windows validation is still required before this implementation is
accepted. Real outcome-blind materialization belongs to 21N-J-B only after this
implementation is safely closed/pushed.

Predeclaration fingerprint: `742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`.
Implementation fingerprint: `566f085ef78e8045a75a1dc3781255a2dcae30f23d04ba317ab56e87ac18f5a6`.

<!-- CHECKPOINT21N_J_B_CONDITIONAL_ALPHA_PREPARATION_20260831 -->
## Checkpoint 21N-J-B — outcome-blind conditional-alpha preparation accepted

The exact frozen 21M development universe has been projected into the four-feature
conditional-alpha v1 representation and independently rematerialized.

- events / rows: 2,570 / 76,419
- feature fingerprint: `590ab13567821839fb0d404ed4813d328fc4e68ee1a61fd39038d3f8624a42fe`
- persisted CSV SHA-256: `268c756f82f6be2b53f5fee1f212ad0ecd1d02459547861cc5c3b3623357472f`
- preparation fingerprint: `a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46`
- independent rematerialization: PASS
- outcomes attached: no
- gamma fit / lambda selection: no / no
- conditional-alpha P&L: no
- C1+C2 / C3 / reserve: closed / closed / sealed
- execution: prohibited

Next checkpoint: freeze exact H1_OOF/H2/H3 label attachment and rolling-origin
development-evaluation orchestration. Do not run the real conditional-alpha
development evaluation before that checkpoint is safely closed.

<!-- CHECKPOINT21N_K_CONDITIONAL_ALPHA_DEVELOPMENT_EVALUATOR_20260831 -->
## Checkpoint 21N-K — conditional-alpha development evaluator prepared

Implementation fingerprint: `02530cdd8ba58b45cde85c0ba40f681355ce5b14c4a3ad53ee5f1072fff156a8`.

The evaluator binds the accepted 76,419-row J-B preparation and the exact frozen
H1_OOF/H2/H3 Candidate-E prediction/outcome artifacts. It implements the exact
21N-I rolling-origin lambda selection and gates.

Evidence-minimizing sequence: probability gate first; economic gate only after
probability PASS; full H-development fit only after both gates PASS.

No real outcomes were read, no gamma fit/lambda selection/P&L was run, and
C1+C2/C3/reserve/execution remain closed in 21N-K.

Next: canonical validation and safe closeout of this implementation. Only then may
the frozen one-time H-development evaluation run.

<!-- CHECKPOINT21N_L_CONDITIONAL_ALPHA_FAILURE_RECORDING_REPAIR_20260831 -->
## Checkpoint 21N-L — conditional-alpha optimizer-contract failure pending canonical recording

The first real conditional-alpha H-development attempt failed at lambda `0.001`,
fold 2 (`H1_OOF+H2` fit -> H3 score) because the frozen BFGS positive-curvature
requirement `y^T s > 1e-12` failed before convergence.

No output artifact, lambda selection, probability gate, conditional-alpha P&L,
or full-development fit was produced.

A recordkeeping-only repair is frozen at `276fdf07803d083a67d94e6c5b923fcbf06392c4db4fb33cd1d9c1f3a954a865`. It does not modify the
optimizer or any scientific gate. After safe closeout, rerun once to persist
`FAIL_OPTIMIZER_CONTRACT` and independently validate it.

<!-- CHECKPOINT21N_M_A_CONDITIONAL_ALPHA_V2_PREDECLARATION_20260831 -->
## Checkpoint 21N-M-A — conditional-alpha v2 optimizer predeclaration

Conditional-alpha v1 remains permanently closed as `FAIL_OPTIMIZER_CONTRACT`. Post-failure numerical diagnostics found no basis to weaken the v1 BFGS contract. Instead, a separately versioned v2 is predeclared under fingerprint `6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8`.

v2 inherits every v1 scientific rule except the optimizer. The replacement optimizer is exact-Hessian damped Newton with deterministic dense Cholesky solve, Armijo backtracking, the unchanged `1e-8` gradient tolerance, and strict fail-closed behavior.

Numerical design evidence only: exact gradient and Hessian finite-difference checks passed; damped Newton passed all 10 frozen lambda/fold fit cases in at most 9 iterations. No lambda was selected and no H2/H3 predictive metrics or conditional-alpha economics were scored.

Next: implement/test v2 Newton mechanics only. C1+C2 unauthorized; C3 locked; reserve sealed; execution prohibited.

<!-- CHECKPOINT21N_M_B_CONDITIONAL_ALPHA_V2_IMPLEMENTATION_20260831 -->
## Checkpoint 21N-M-B — conditional-alpha v2 Newton implementation freeze

The optimizer-only v2 mechanics are now implemented but not authorized for a real
development fit. v2 inherits the v1 scientific contract and replaces only BFGS
with exact-Hessian damped Newton using deterministic dense Cholesky.

Implementation fingerprint: `459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd`.

No lambda was selected, no H2/H3 conditional-alpha predictions were scored, no
probability/economic gate was run, and C1/C2/C3/reserve/execution remain closed.

<!-- CHECKPOINT21N_M_C_CONDITIONAL_ALPHA_V2_EVALUATOR_20260831 -->
## Checkpoint 21N-M-C — conditional-alpha v2 H-development evaluator freeze

The v2 H-development evaluator is implemented but the formal real-data v2
evaluation has not been run.

Evaluator fingerprint: `bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`.

The evaluator inherits the exact v1 development evidence/gates and routes every
fit through the frozen v2 Newton fitter. Real execution is locked until a valid
21N-M-C closeout receipt exists.

No lambda selection, probability gate, conditional-alpha P&L, C1/C2/C3/reserve
access, or execution occurred in 21N-M-C.

<!-- CHECKPOINT21N_M_C_R1_TEST_HARNESS_REPAIR_20260831 -->
### 21N-M-C-R1 — pre-closeout focused-test repair

Focused synthetic tests exposed two implementation-test defects before any formal v2 H run: a constant synthetic `spread_t` caused the frozen scaler to fail on zero variance, and the contextual fit exception was incorrectly frozen, causing traceback assignment to raise `FrozenInstanceError`.

Both are repaired without changing model science. New evaluator fingerprint: `bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`. Formal H fit/scoring/economics remain unrun.

<!-- CHECKPOINT21N_M_C_R2_SYNTHETIC_ORCHESTRATION_TEST_REPAIR_20260831 -->
### 21N-M-C-R2 — synthetic orchestration test expectation repair

The remaining focused-test failure was not a Newton implementation failure.
An arbitrary synthetic low-lambda fit produced an indefinite exact Hessian, and
the frozen v2 Cholesky contract correctly failed closed.

R2 changes only the test expectation: one synthetic case continues to exercise
real Newton convergence, while the 5-lambda x 2-fold test now verifies evaluator
routing with a controlled fitter stub. The v2 implementation fingerprint remains
`bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`.

No real H evaluation or scientific rule changed.

<!-- CHECKPOINT21N_N_A_ALPHA_ENTRY_DIAGNOSTIC_PREDECLARATION_20260831 -->
## 21N-N-A — Conditional-alpha-as-entry-ranking diagnostic predeclaration

The formal conditional-alpha v2 H-development result is validated and closed
scientifically as `FAIL_PROBABILITY_GATE`.

- selected lambda: `0.001`
- evaluation fingerprint: `fa1f6f34ec830ea6c2520a1513f27c3ca1f0d69bf2ddc73e1c90660abfc3efe0`
- receipt fingerprint: `cafcae196ccaa7f352e3685a9d3132e2d0d5356bb5f041c9035adc27db8d90eb`
- result validator: PASS
- v2 economics: not run
- C1/C2/C3/reserve: untouched by v2
- execution: disabled

A separate exploratory diagnostic is now predeclared:
`kxbtcd_candidate_e_alpha_reliability_entry_diagnostic.v1`
fingerprint `2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e`.

Candidate E remains valuation; alpha is ranking only. The diagnostic has not run.

<!-- CHECKPOINT21N_N_B_ALPHA_ENTRY_DIAGNOSTIC_IMPLEMENTATION_20260831 -->
## 21N-N-B — alpha-reliability entry diagnostic implementation freeze

The predeclared exploratory diagnostic is implemented but has not been run on
real H2/H3 economics.

Implementation fingerprint:
`2bc7d625fa7889ee071322a3d3785becc49fd66fcf409e47713de8dc2405bc0d`.

Candidate E remains the sole valuation probability. Conditional alpha is attached
only after Candidate-E event/anchor/market/side selection and is used only for
ranking.

The real CLI is locked until 21N-N-B is safely closed. No diagnostic P&L,
threshold search, C evidence, reserve access, network access, or execution
occurred in this checkpoint.

<!-- CHECKPOINT21N_N_C_A_INCREMENTAL_ALPHA_SCORE_PREDECLARATION_20260831 -->
## 21N-N-C-A — incremental alpha score predeclaration

The validated parent alpha-entry diagnostic returned
`PROMISING_EXPLORATORY_SIGNAL` with 512 Candidate-E opportunities, but it remains
not a strategy PASS.

Parent result fingerprint:
`54d2a3588c1e06d4a6cd79234b91c59e4aafecff95e33a7a218e2fac85811d3b`.

Observed parent development facts include pooled Candidate-E-all-entry P&L
`-0.01765625` per entry and Q4 alpha base P&L `+0.0090625` per entry. Q4 becomes
approximately break-even under +1c stress (`-0.000703125` per entry).

Because mean Candidate-E quoted edge also rises with alpha, the next frozen
question is whether alpha adds ranking value after edge is explicitly controlled.

New diagnostic:
`kxbtcd_candidate_e_incremental_alpha_entry_score.v1`

Predeclaration fingerprint:
`bb341361f191621564459fef3f68d893181498cb687e131e39183441a3eb27fa`.

No incremental score P&L has been run yet.

<!-- CHECKPOINT21N_N_C_B_INCREMENTAL_ALPHA_SCORE_IMPLEMENTATION_20260831 -->
## 21N-N-C-B — incremental alpha score implementation freeze

The exact C-A score family is implemented but has not been run on real H2/H3
incremental-score economics.

Implementation fingerprint:
`8c88bb386e0ba13b3ab8761e67a73dd7105637d3667d5fc7394d163259b5471b`.

The implementation fixes the parent 512 Candidate-E opportunities, computes
outcome-blind pooled z-scaling for Candidate-E edge and logit(alpha), evaluates
only beta `0/.25/.5/1/2`, and selects exactly 128 entries per beta.

The real CLI is locked until 21N-N-C-B is safely closed. No incremental-score
P&L, coverage search, threshold search, C evidence, reserve access, network
access, or execution occurred in this checkpoint.

<!-- CHECKPOINT21N_N_C_RESULT_CLOSEOUT_20260831 -->
## 21N-N-C — incremental-alpha entry score result

Validated result:
- status `NO_INCREMENTAL_ALPHA_SIGNAL`
- selected beta `0.5`
- result fingerprint `df58a6b8b24a35f059e046025d528c02490f2efc70e10c634b0edce1a44212db`
- receipt fingerprint `3ff1ed184b014a15819c499b698e66425012966af28685b6e0b2b167999870fd`
- strategy PASS `false`.

The selected beta beat beta=0 on pooled base/+1c P&L and H2 base P&L, but failed
to beat beta=0 in H3 and remained negative in pooled base and +1c economics.

Edge-only beta=0 also remained negative, so this result does not justify simply
dropping alpha and trading the largest Candidate-E quoted edges.

No beta/coverage/threshold rescue is authorized on H2/H3. C1/C2/C3 and the
protected reserve remain untouched by this diagnostic. No execution occurred.

Architecture decision: Candidate E remains the forecasting/valuation layer.
Economic entry policy remains a separate downstream strategy layer.

<!-- CHECKPOINT21N_O_PREDEXON_SOURCE_QUALIFICATION_CLOSEOUT_20260901 -->
## Checkpoint 21N-O — Predexon historical microstructure source qualification

Checkpoint 21N-O qualifies Predexon paid KXBTCD tick history for conservative
**exploratory/development historical replay** when restricted to
reconciliation-verified book segments.

Accepted evidence from the already-purchased 2026-07-10 shard:
- 5,644,964 paid KXBTCD delta rows;
- 623 strike contracts across only 4 independent hourly events;
- free snapshot existence census: 623/623 contracts;
- frozen 20-contract stratified audit: 8,210/8,273 exact adjacent transitions
  (99.2385%);
- verified-time diagnostic across sampled snapshot spans: 88.4224%;
- every sampled event contained a longest continuous verified segment of at
  least 41.196 minutes.

Replay contract v2 is reconciliation-authoritative. Displayed snapshot sequence
decreases are diagnostics only; exact ordered A->B book reconstruction decides
continuity. Any unreconciled adjacent pair is a hard boundary and book state is
never carried across it.

Implementation validation:
- focused replay tests: 8 passed;
- full suite: 1121 passed, 22 subtests passed in 46.04s;
- source registry: 23 sources / 17 validated / 0 unresolved / PASS.

The four 2026-07-10 events are development sandbox evidence only, not final
strategy validation evidence. No more Predexon purchase is needed now. Future
paid-data acquisitions require a frozen fresh-event protocol and may use only
user-available promotional/free credit without knowingly incurring a card
charge or top-up.

Next: design an exploratory Candidate-E executable-edge / realizability baseline
using only verified replay windows from this shard. Candidate E remains frozen.
No C1/C2/C3/reserve access and no execution are authorized.

<!-- CHECKPOINT21N_P_REPLAY_CLOSEOUT_20260901 -->
## 2026-09-01 — Checkpoint 21N-P replay-source closeout

The Predexon 2026-07-10 KXBTCD historical microstructure source-engineering stage is accepted as an exploratory execution-research sandbox.

### Accepted evidence

Free sub-cent backfill:
- 623 / 623 owned contracts complete;
- 679 pages;
- zero paid purchases;
- zero outcomes accessed;
- no Candidate-E scoring or strategy P&L.

Paid-shard structure:
- 5,644,964 paid delta rows;
- 623 contiguous ticker blocks;
- zero ticker reentries;
- zero per-ticker `(timestamp, sequence)` order violations;
- four chronological event blocks: KXBTCD-26JUL1013 through KXBTCD-26JUL1016.

Full-ladder segment-safe replay:
- 623 tickers;
- 269,441 free snapshots;
- 268,818 adjacent snapshot pairs;
- 266,034 exact reconciliations;
- 2,784 unreconciled pairs;
- exact-pair rate: 98.964355%;
- time-weighted verified coverage: 80.088503%;
- network requests during replay: 0;
- paid purchases during replay: 0;
- outcomes accessed: 0;
- strategy P&L: not run.

Event-level verified-time coverage:
- KXBTCD-26JUL1013: 70.5961%;
- KXBTCD-26JUL1014: 77.5552%;
- KXBTCD-26JUL1015: 88.1905%;
- KXBTCD-26JUL1016: 77.6139%.

### Accepted source-eligibility rule

For the frozen Candidate-E TTC grid `(55m, 50m, 45m, 40m, 35m, 30m)`, a ticker-at-anchor state is source-eligible only when its exact decision timestamp lies inside one continuously verified replay segment for that ticker.

Unverified state is unavailable. It is not interpolated, carried across a failed boundary, substituted from another strike, or rescued by a ticker-level/event-level coverage threshold.

Across the full strike ladder:
- eligible ticker-at-anchor states: 2,304 / 3,738;
- source eligibility: 61.64%.

When latency is introduced, the complete decision-to-execution interval must remain inside the same verified segment.

This remains exploratory source evidence only. The 623 strike contracts are nested within only four independent hourly events and cannot establish generalization or profitability.

<!-- CHECKPOINT21N_Q_EXECUTABLE_CONVERGENCE_LIQUIDATION_PREDECLARATION_20260901 -->
## 2026-09-01 — Checkpoint 21N-Q executable convergence-liquidation predeclaration

The outcome-blind Candidate-E executable entry + liquidation methodology is frozen under fingerprint
`61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`.

Accepted: frozen Candidate E; q10/q30/q50/q70/q90 only; TTC 55/50/45/40/35/30; one-contract IOC entry;
0/500/1000 ms latency; 0c/1c/2c/3c/5c parallel edge margins; entry-time Candidate-E fair value as the
liquidation target; one IOC exit attempt; verified-segment fail-closed path rules; partial/missed exit remainder
to settlement; matched hold control; four-event exploratory sandbox with no advancement gate.

No July 10 strategy outcome or P&L was opened to choose these rules. No execution or new Predexon purchase is authorized.

<!-- CHECKPOINT21N_Q1_FEE_ACCOUNTING_AMENDMENT_20260901 -->
## 2026-09-01 — Checkpoint 21N-Q1 fixed-point fee-accounting correction

Before any July 10 strategy outcomes or P&L were opened, the 21N-Q fee/cash bookkeeping description was corrected
under amendment fingerprint `5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1`.

The strategy itself is unchanged. The direct-exchange counterfactual now uses Kalshi's fixed-point mechanics:
per-synthetic-fill model trade fee rounded up to $0.000001, direct-member balance alignment to $0.0001, and an
order-local $0.0001 rounding accumulator/rebate. One synthetic fill per consumed price level remains the frozen
historical approximation and must be reported as execution uncertainty.

21N-R implementation must validate both the base strategy fingerprint `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6` and this amendment before any
strategy outcome/P&L evaluation.

<!-- CHECKPOINT21N_R_SIMULATOR_IMPLEMENTATION_20260901 -->
## 2026-09-01 — Checkpoint 21N-R simulator implementation freeze

The outcome-blind executable convergence/liquidation simulator is frozen under implementation fingerprint
`6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf`.

It binds the 21N-Q strategy fingerprint `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`, the 21N-Q1 fixed-point accounting amendment
`5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1`, and Champion-Final `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`.

Implemented mechanics include deterministic structural-role selection, Candidate-E anchor valuation, exact
direct-member Decimal fee/cash accounting, YES/NO book normalization, IOC depth walking, 0/500/1000 ms latency,
full/partial/missed entry, continuous verified-segment monitoring, entry-time-fair-value liquidation trigger,
one IOC exit attempt, settlement-fallback quantity, and matched hold quantity.

New outcome-blind implementation conventions are frozen: one right-continuous final reconstructed state per
millisecond, and a small-order non-impacting future-book assumption after each counterfactual IOC. Neither is
treated as observed market truth.

July 10 settlement outcomes accessed: 0. Strategy P&L: NOT RUN. Orders: 0.

Next: 21N-S outcome-blind binding of the four July 10 events to this frozen simulator. Keep outcomes closed.

## Checkpoint 21N-S-A — Outcome-Blind Real-Data Binder Implementation Freeze

- 21N-R is closed at checkpoint `9c58d63e9faab98b486fdcbc374605abd1115d82`, receipt `b6ec6226374f90bae63784aee8cda28b81e7d67b`.
- 21N-S is split to preserve anti-tuning discipline: S-A freezes the real-data binder before S-B may expose actual July 10 signal/path diagnostics.
- Frozen local hashes: BTC materialization `022f6c6ce1b697bc67f7137f73e3f18cc0fe0198b347e5154a3063107299fb12`; paid tick shard `43e9c5d99fb4001b866ae3e60021c8c10123dc1fb6248df96084446face68509`; replay summary `b37ba7132baf086887e4b33e7c11e9de59decc5f0b387d7e6e5352a2570ebb48`.
- Source-layout preflight established an exact 623 paid / 623 replay / 623 backfill ticker-set match and the exact BTC/replay/backfill schemas without opening outcomes.
- S-A freezes full-ladder structural-role binding, exact BTC anchor binding, verified replay timeline construction, signal selection, and settlement-blind execution-path materialization.
- S-A does **not** run the real July 10 signal/path materialization. Outcomes remain unopened; strategy P&L remains unrun; Candidate E remains frozen; orders/purchases/network activity remain zero.
- Next only after S-A closeout: **21N-S-B — July 10 Outcome-Blind Strategy Input and Execution-Path Materialization Run**.

<!-- CHECKPOINT21N_S_B_OUTCOME_BLIND_MATERIALIZATION_RESULT_20260901 -->
## 2026-09-01 — Checkpoint 21N-S-B outcome-blind materialization result

July 10 outcome-blind materialization is complete and deterministic under artifact SHA-256
`624dab514bfffbe1969b87bfa8d7a7bf63dfb14177666cc5d08029c056287f9a`.

The four-event sample is **NON-EVALUABLE for executable strategy economics**:
120 role-anchor states produced 47 exact-timestamp replay-unavailable states, 40 states missing a YES bid,
33 states missing a YES ask, 0 crossed books, and 0 valid two-sided books. Candidate E therefore generated
0 signal candidates, all 20 event-threshold selections were empty, and 0 execution scenarios existed.

This is a data-adequacy result, not a Candidate-E or strategy P&L failure. July 10 outcomes remain unopened and
strategy P&L remains unrun. Do not tune the frozen strategy from these diagnostics.

Next: 21N-T prospective read-only execution-data adequacy and collection design.

<!-- CHECKPOINT21N_T_CONTINUOUS_CONVERGENCE_REENTRY_PREDECLARATION_20260901 -->
## 2026-09-01 — Checkpoint 21N-T continuous convergence + re-entry predeclaration

After 21N-S-B was permanently closed as non-evaluable, the accepted successor strategy is
`kxbtcd_candidate_e_continuous_convergence_reentry_v1`.

New-entry decisions are causal/event-driven from T-55 through T-2 rather than scheduled at six anchors.
Candidate E, q10/q30/q50/q70/q90 roles, one-contract size, 0/1/2/3/5-cent margins, 0/500/1000-ms latency,
21N-Q1 fee accounting, and the entry-time-fair-value cash-out rule remain frozen.

A fully exited first position may re-arm and permit one second entry. Trade-1 history is recorded but cannot
influence Trade 2 in v1. Comparison branches are matched first-entry hold, liquidate once, and liquidate + re-entry.

Non-anchor and sub-30-minute Candidate-E uses are extrapolation stress evidence. Four July 10 events remain
exploratory only. Continuous July 10 results and settlement outcomes remain unopened.

Next: 21N-U continuous Coinbase state materialization + simulator implementation freeze.

<!-- CHECKPOINT21N_U_A_CONTINUOUS_IMPLEMENTATION_FREEZE_20260901 -->
## 2026-09-01 — Checkpoint 21N-U-A continuous implementation freeze

21N-U is split so implementation is frozen before real continuous July 10 Candidate-E paths are exposed. U-A freezes the exact 216-row Coinbase requirement, raw-preserving collector, event-driven top-of-book/BTC clock, arbitrary-timestamp frozen Candidate-E valuation, one-pending-IOC semantics, inherited 21N-R cash-out, full-exit re-arm, and maximum two filled entries.

The real path runner is source-binding gated and must fail closed until U-B pins the continuous Coinbase materialization hash. Continuous July 10 strategy paths remain unopened; settlement outcomes remain closed.

Next: 21N-U-B continuous Coinbase source materialization and binding only.

<!-- CHECKPOINT21N_U_B_RECOVERED_COINBASE_BINDING_20260902 -->
## 2026-09-02 — Checkpoint 21N-U-B recovered Coinbase source binding

The frozen continuous Coinbase collector successfully completed four public HTTP requests
and wrote the exact 216-row / four-event derived source artifact before Windows/OneDrive
blocked the atomic manifest replacement with WinError 5.

The failed manifest remains failed. No source recollection was performed. The existing
artifact is accepted only by exact hash plus a full offline 216-row source-contract
validation.

Continuous Coinbase SHA-256: `ecc83bc5a95c65d05063e06df6d5c9aab04895577c3ef5d8ad1cc99ab62f7d1d`.
Continuous Predexon strategy paths remain unopened; settlement outcomes remain closed.

Next: run the already-frozen outcome-blind continuous July 10 Predexon path.

<!-- CHECKPOINT21N_V_CONTINUOUS_NON_EVALUABLE_CLOSEOUT_20260902 -->
## 2026-09-02 — Checkpoint 21N-V continuous v1 outcome-blind closeout

`kxbtcd_candidate_e_continuous_convergence_reentry_v1` is closed as
`NON_EVALUABLE_STRUCTURAL_UNIVERSE_LIQUIDITY_MISMATCH`.

The frozen 60-scenario July 10 continuous path completed with 0 entry attempts and
0 filled trades. Across 17,550 structural-market evaluations there were 0 evaluable
two-sided Candidate-E states.

This is not an edge/fee/latency/liquidation/re-entry failure: Candidate E never reached
edge calculation on the frozen five-role universe.

Outcome-blind full-ladder diagnostics found 45 / 623 tickers with valid two-sided
states and 1,060,685 valid two-sided reconstructed states, while the 20 frozen
q10/q30/q50/q70/q90 tickers had 0 with any valid two-sided state.

Settlement outcomes remain closed. Next checkpoint 21N-W: diagnose whether the moving
liquidity band is causally spot/ATM-relative before predeclaring a new market universe.

<!-- CHECKPOINT21N_W_SPOT_ATM_LIQUIDITY_GEOMETRY_20260902 -->
## 2026-09-02 — Checkpoint 21N-W spot/ATM liquidity geometry

Outcome-blind July 10 market-universe geometry supports a spot/ATM-relative
liquidity structure on the four-event exploratory sample.

Across 216 exact minute cross-sections, 177 contained at least one valid
two-sided market. Among those 177, the nearest valid two-sided contract was
within 1 / 2 / 3 / 5 strike ranks of causal ATM in 132 / 161 / 174 / 177
cross-sections respectively. Median nearest distance was 1 rank; maximum was 4.

Across 755 active ticker-minute instances, median absolute rank distance from ATM
was 3 and median absolute strike distance from spot was $286.25.

This does not choose a v2 envelope, validate Candidate E on nonstructural strikes,
or establish profitability. N=4 independent events. Continuous v1 remains closed.

Next: 21N-X predeclaration of a new liquidity-first, spot-relative tradable
universe and fresh-evidence validation protocol.

<!-- CHECKPOINT21N_X_SPOT_RELATIVE_V2_PREDECLARATION_20260902 -->
## 2026-09-02 — Checkpoint 21N-X V2 exact predeclaration

Frozen new strategy version:
`kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2`.

Predeclaration fingerprint:
`3e44c6ce3b9e420db3cf0dd52c2b64030ae99901c491d9cf0bc15617930ef8ae`.

V2 uses a causal dynamic ATM±5 strike-rank universe (maximum 11 markets), while
Candidate-E Champion-Final remains unchanged at beta_distance `0.014939489324405949`.

July 10 remains four-event development/mechanics evidence only. Candidate E may
not score nonstructural July 10 markets until V2 implementation is separately
frozen.

Fresh nonstructural-domain validation is fixed to 24 post-Champion-Final events:
August 19/21/23/25/27/29 at 17/18/19/20 UTC. No replacements.

Fresh source gate before outcomes: >=20/24 materialized events, >=16 events with
>=27/54 usable nonstructural cross-sections, and >=778/1296 pooled usable
cross-sections.

Fresh Candidate-E gate: strictly better event-equal log loss than raw midpoint,
non-worse Brier, >=4/6 date-block log-loss wins, and newest Aug-29 block win.
No refit/recalibration.

Fresh strategy P&L is not authorized by 21N-X. Next: 21N-Y-A implementation
freeze before any V2 nonstructural scoring.

<!-- CHECKPOINT21N_Y_A_V2_IMPLEMENTATION_FREEZE_20260902 -->
## 2026-09-02 — Checkpoint 21N-Y-A V2 implementation freeze

The exact simulator for
`kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2` is implemented and frozen before any real July 10
nonstructural Candidate-E scoring.

Implementation fingerprint:
`b8f66b2f392df2c8711e7d6e25e64c54921b16f8f7866c243a6375aaec778949`.

Implemented: causal ATM±5 dynamic universe, BTC-minute/window-best-level decision
clock, explicit structural/nonstructural domain labels, inherited 21N-R
IOC/fee/latency/liquidation mechanics, and the V2
`REFERENCE_LEFT_SPOT_WINDOW` re-arm rule.

The future path runner is included in the freeze but was not executed. It
validates the full 623-ticker source set, then reconstructs only the deterministic
union of tickers that can enter ATM±5 under the bound causal BTC minutes.

July 10 V2 paths: not run. Real nonstructural Candidate-E scoring: no.
Outcomes/P&L: unopened. Network/purchases/orders: 0/0/0.

Next: 21N-Y-B exact frozen July 10 V2 outcome-blind development path.

<!-- CHECKPOINT21N_Y_A1_QUANTITY_TRANSPORT_AMENDMENT_20260902 -->
## 2026-09-02 — Checkpoint 21N-Y-A1 execution-quantity transport amendment

The first 21N-Y-B attempt began nonstructural Candidate-E scoring but failed
during IOC simulation on `level.quantity=250.00000000000068` before a completed
path artifact existed.

Diagnostics established 0 off-grid paid deltas across 5,644,964 rows. Across
13,695,870 preserved snapshot levels, 763,392 quantities were off the exact
0.01 grid, but all 763,392 were within 1e-9 of that grid and 0 were materially
off-cent.

Frozen Y-A1 repair: after verified replay reconstruction and before V2
decision/execution use, quantities within 1e-9 of the nearest 0.01 are
canonicalized to exact 0.01-grid Decimal values; anything farther away fails
closed.

Original replay, Y-A implementation, Candidate E, ATM±5, fees, thresholds,
latencies, liquidation, and re-entry remain unchanged.

Amendment fingerprint: `2cbd8836045ae811eb4c52d48834953a54b1be3afac094be4cf349b8cac2abce`.

Next: after Y-A1 closeout, rerun Y-B with the amended runner. Outcomes remain
closed.


<!-- CHECKPOINT21N_Y_A2_MEMORY_STORAGE_AMENDMENT_20260902 -->
## Checkpoint 21N-Y-A2 — memory/storage amendment

The Y-A1-amended Y-B attempt failed with MemoryError in
VerifiedSegmentTimeline.__post_init__ while canonicalize_timeline_map was
constructing a second in-memory timeline map. The user later interrupted the
foreground command with Ctrl+C. The traceback occurs before this attempt's
policy loop. It did not write a completed path artifact; settlement outcomes and
strategy P&L remain unopened. Earlier Y-B scoring exposure remains recorded.

Y-A2 fingerprint: `f7a590cb0f8415e3330fa82077d16b6b93105717f573e69e8580a3f3ac1ffe03`.

The repair stages replay states in SQLite one ticker at a time, retains the
original reconciliation/delta functions, performs the same last-write-wins
millisecond collapse and raw-state compression, then applies exact Y-A1
quantity normalization. Raw sources and frozen Y-A/Y-A1 files are preserved.
Disk queries preserve right-continuous lookup, full-depth liquidation changes,
and verified-segment availability. The policy function body is AST-identical
to Y-A; only the decision-clock state scan uses indexed disk reads.

Completed ticker caches are bound to raw snapshot, replay, paid-shard, and
amendment hashes. Cache corruption or changed identities stop the run. An
interruption retains sealed tickers and removes only the active temporary
build when cleanup succeeds. An orphan cache or stale run lock requires
inspection, never silent acceptance. Atomic final output refuses a different
existing artifact.

Default runner mode prepares caches only. `--simulate` explicitly requests
all 60 frozen policies after complete preparation; partial-ticker preparation
cannot score. A 15-second heartbeat reports the current stage.

This is an implementation repair, not a strategy retune or successful Y-B
result. Candidate E, ATM+/-5, thresholds, fees, quantities, latencies,
liquidation/re-entry rules, fresh-evidence gates, and execution authorization
remain unchanged. N=4 July 10 events remain development/mechanics evidence.

Local synthetic verification covers exact replay+quantity equivalence,
same-millisecond cuts, source gaps, normalization duplicates, clock equivalence,
YES/NO IOC paths, partial/missed fills, liquidation, re-entry, cache integrity,
interruption/resume, and atomic outcome-blind output. It is not a real-data
completion claim. The full Windows suite is required by safe closeout.

Next after A2 closeout: bounded preparation with `--max-tickers 1`, inspect
resource behavior, then prepare the remaining cache. Score only through a
separate explicit `--simulate` invocation after preparation succeeds.

Current Y-B status: INCOMPLETE. The old outcome-blind path filename remains untouched. Future A2 output is data/analysis/predexon_credit_efficiency/july10_candidate_e_v2_outcome_blind_paths_memory_safe.json.


<!-- CHECKPOINT21N_Y_A3_REPLAY_PRECISION_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A3 replay precision repair

User's Y-A2-backed Y-B run completed: 47 caches and 60 outcome-blind policy paths,
SHA256 21dd58066b040f8bc897815f722cad9bb90b0ff6b9a6d18d6e9416279c85bc9f.
This supersedes the earlier INCOMPLETE run status, but its premature exit-monitoring
boundaries are implementation-affected. Preserve the original result.

The uploaded 25ms diagnostic (SHA256
47caf2f93c736538db9a896a469f6a25fcdb247d2e67e89cf538675e4c8eeac5) reproduces
snapshot residue leading to a -2E-14 reconstructed balance. Normalize snapshot
quantities within 1e-9 of 0.01 before replay, then retain exact paid deltas and
strict reconciliation. A separate additive adapter, source-bound caches and output
path version this semantic correction. Original frozen replay, model and strategy
files remain unchanged. Real gaps still stop monitoring.

Correction: all nine normalized cut combinations are numerically executable,
but only cut (1,1) reconciles exactly. Both adjacent control pairs still pass.
The roughly 33-minute discontinuity remains unresolved until full source re-audit.

Implementation and local regression prepared; canonical Windows tests, safe closeout,
full cache rebuild and revised paths pending. See
KXBTCD_CANDIDATE_E_V2_REPLAY_PRECISION_AMENDMENT.md for exact evidence, rule,
failure modes and paths. Next: install/validate Y-A3; safe closeout then prepare
new caches with materialize_kxbtcd_candidate_e_v2_paths_replay_precision.py.
Review coverage_full.json before --simulate. Outcomes/P&L stay unopened; n=4
remains exploratory mechanics evidence. No execution authorization changes.

Y-A3 amendment fingerprint: `4c3e7ea2b730f548d9be5640602d8b81551ac647f7a09ea31051a61db6ff6127`. Assistant focused verification: **60 passed in 2.98s** (Python 3.12/Linux); Windows full suite pending.


<!-- CHECKPOINT21N_Y_A3_WINDOWS_FOCUSED_VALIDATION -->
## Checkpoint 21N-Y-A3 — Canonical Windows focused validation

User-reported canonical terminal evidence:
- replay precision amendment validator: PASS;
- fingerprint: 4c3e7ea2b730f548d9be5640602d8b81551ac647f7a09ea31051a61db6ff6127;
- frozen parents: unchanged;
- focused regression: 60 passed in 7.54s;
- git diff --check: PASS (no output);
- strategy: NOT RUN; settlement outcomes: NOT ACCESSED; orders: 0.

PowerShell blocked the downloaded unsigned validation wrapper before execution.
The user ran its Python validator, pytest and Git checks directly without changing
the execution policy. This is a wrapper-loading issue, not a replay/test failure.

The ZIP was apparently extracted into the repository root before the guarded
installer ran. Closeout preparation verifies the exact delivered files, backs up
extraction leftovers outside the repository, restores README only if it exactly
matches the bundle README, and archives the standalone inspector for retention.
No arbitrary untracked files or project edits are discarded.

The 60 focused tests are accepted. Full-suite validation, commit/push and receipt
are handled by the existing safe closeout engine; this entry does not claim they
have completed. After successful closeout, prepare the new Y-A3 caches and review
coverage_full.json before running the 60 revised outcome-blind scenarios. The
full-data rebuild, larger-gap diagnosis, revised paths and P&L remain pending.


<!-- CHECKPOINT21N_Y_A3_EOF_FORMAT_CLOSEOUT_REPAIR -->
## Checkpoint 21N-Y-A3 — Precommit formatting correction

The first safe closeout attempt passed the source registry and the full canonical
Windows suite: **1302 passed, 22 subtests passed in 57.77s**. After staging, Git's
whitespace check rejected one additional blank line at EOF in
materialize_kxbtcd_candidate_e_v2_paths_replay_precision.py (line 297). The earlier
unstaged diff check had not inspected this new untracked file. Closeout stopped
before a checkpoint commit or push; its helper unstaged the approved files.

The correction removes exactly that single trailing blank line. The runner's
Python AST is identical. No model, strategy, replay rule, source binding, quantity
normalization tolerance, fee, execution authorization or outcome firewall changes.

Old uncommitted amendment fingerprint (superseded for formatting only):
4c3e7ea2b730f548d9be5640602d8b81551ac647f7a09ea31051a61db6ff6127
Current amendment fingerprint:
82c4d05994cf97c723672b82428a7a139e20f96ae5aeea622e6dfaf1429a1370
The config pins the corrected runner hash, and the validator pins the new config
fingerprint. Its normalized validator-template hash is unchanged. Original parent
freezes remain intact; no corrected cache or path has been generated under either
Y-A3 fingerprint. Full closeout is retried through the existing engine and records
its own fresh validator/test evidence in the managed receipt.

Next after successful closeout: prepare Y-A3 caches and inspect coverage_full.json
before revised outcome-blind strategy paths. Settlement outcomes/P&L remain closed.

## 2026-09-03 — Checkpoint 21N-Y-A4 snapshot consistency repair and coverage gate

This entry supersedes earlier statements that the Y-A3 caches and paths were still
pending. Y-A3 closed at checkpoint 35b778a4f68d7d221536358599683706019230d8 and
receipt 1116a023cac865a9aeac13db041e710e4632395e; the canonical Windows suite passed
1302 tests plus 22 subtests, with clean synchronized main. The completed 47-ticker
coverage hash is 5b78812350bbcd3cea77f9c109dac2cce636de9577426edbaf523179859da1ab;
the completed 60-scenario outcome-blind path hash is
3b1bfadd61f003343d385fc1f62b6192ce5b53fda87d3f1977d84f604ebb4780.

The comprehensive forensic report hash is
a9bfe9d389611b192a186024c1301563d71bdcd649a891401a223434c03bd188. It reproduced
748 failures (236 negative-resting-size failures, 512 snapshot mismatches).
125 isolated-snapshot endpoint experiments and 15 ordering cases support further
review, not blanket acceptance. Large clusters remain unresolved.

Y-A4 fingerprint: 31df5185c3840092eaae09f82fd0139cf46db37dc5bfd9bd067d6dcfa758c92a.
The frozen specification is KXBTCD_CANDIDATE_E_V2_SNAPSHOT_CONSISTENCY_AMENDMENT.md.
Ordering and isolated-snapshot quarantine are separate rules; both require a unique
consistent exact local replay. Quarantine requires five strictly increasing times,
verified outer controls and at most 120 seconds of context. Overlapping proposals
are rejected; long and unsupported cases remain gaps. Source labels alone do not
establish authority. All proposals originate from the unchanged Y-A3 view.

Local isolated validation: 79 focused tests passed, including 19 new tests and the
60 existing precision/memory tests. Eight bounded real-source fixtures cover the
six earlier/later repair examples and both unresolved clusters. The coverage-runner
file-flow test used synthetic source/cache envelopes around three real extracts;
it is not a full 47-ticker execution on the user's PC. Canonical Windows closeout
and the real-data Y-A4 coverage gate remain pending until their terminal evidence.

No model refit, strategy rule changes, new execution cache, strategy rerun,
settlement outcomes, strategy P&L, or orders were produced by this amendment.

Current next action: close out the implementation through the existing safe helper,
then run the coverage-only validator. It verifies all source identities and replays
changed neighborhoods, reusing pinned classifications for unchanged pairs. It emits
separate ordering-only, quarantine-only and combined reports. Review that output
before implementing the new cache builder and rerunning any of the 60 scenarios.

<!-- CHECKPOINT21N_Y_A5_REPAIR_CACHE_IMPLEMENTATION_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A5 — 203-pair repair-aware cache implementation

This entry supersedes earlier Y-A4 statements that the new cache builder and final
repair accounting were still pending. The original Y-A3 evidence remains immutable.

Outcome-blind reconstruction accounting is now frozen at:
- original Y-A3 failed adjacent pairs: **748**
- supported repaired pairs: **203**
- unresolved pairs retained as hard segment boundaries: **545**
- accounting: **748 = 203 + 545**
- repair operations: **110**
  - A4: 105
  - A5 tied-outer-control quarantine: 3
  - joint same-timestamp ordering: 2
- cross-repair context overlaps: **0**
- quarantined snapshots under the composed plan: **93**

Frozen materialization plan:
`configs/kxbtcd_candidate_e_v2_repair_materialization_plan_203.json`
SHA256:
`e95fe1c8d170dad1da9a51fe11e892c1efa70a124f52bbe9acf687c50edbb32b`.

Implementation is additive. Frozen Y-A3 replay modules are not weakened or edited.
The new builder:
- normalizes snapshots through the existing Y-A3 precision rule before applying
  original-index repair instructions;
- preserves exact paid-row order as timestamp, sequence, original source-row;
- uses each repair's pinned snapshot order and pinned cut chain;
- independently reconstructs every changed endpoint at zero tolerance;
- forbids a repair context from silently crossing an undeclared failed pair;
- leaves every unsupported residual pair as a hard verified-segment boundary;
- creates a new immutable sealed SQLite cache namespace rather than overwriting
  Y-A3 caches;
- contains no strategy-simulation mode.

Pre-cache validation passed:
- 110 repair operations
- 203 addressed failed pairs
- 545 residual hard boundaries
- 93 quarantined snapshots
- strategy not run; outcomes/P&L unopened; orders 0.

Focused repair-materialization tests: **6 passed**.
Canonical repository regression: **1327 passed, 22 subtests passed in 78.23 s**.

Current repository base before this checkpoint is
`0b3bc919e56506f34124e3293f356a1d25f9c5dc`, synchronized with `origin/main`.

No repaired real-data cache has been built yet. No 60-scenario strategy rerun,
settlement outcome access, strategy P&L, paper/demo execution or orders occurred.

Next after safe closeout: run the committed preparation-only repair-cache runner on
one deterministic ticker (`--max-tickers 1`). Review the sealed-cache audit and
source/hash lineage before preparing all 47 tickers. Only after the full repaired
cache coverage validates may the unchanged 60 outcome-blind scenarios be regenerated.

<!-- CHECKPOINT21N_Y_A6_REPAIR203_PATH_READINESS_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A6 — Repair-203 60-path readiness runner

The complete repair-aware cache preparation is now accepted as execution evidence
for the next outcome-blind path materialization step.

Full repair-cache evidence:
- prepared tickers: **47 / 47**
- repair operations: **110**
- original failed pairs addressed: **203**
- residual hard boundaries retained: **545**
- frozen repair coverage SHA256:
  `b8b535d6131f01250690d1015861a4737fd0cd4888251f1cbf4941eb7dceeab0`
- superseded Y-A3 outcome-blind path SHA256:
  `3b1bfadd61f003343d385fc1f62b6192ce5b53fda87d3f1977d84f604ebb4780`

An additive repair-203 path runner is implemented. It reads only the sealed
`v2_repair_203_cache` timelines, binds to the exact repair coverage SHA, verifies
all 47 cache seals and per-ticker repair audits, confirms the unchanged dynamic
ticker union and frozen 60-scenario grid, and refuses settlement/P&L access.

The initial readiness validation failed closed because the new checker compared
live Decimal threshold objects with their frozen JSON string representation.
The frozen simulator intentionally serializes Decimal values through `jsonable()`.
The validator was corrected to normalize both sides to the same frozen JSON
representation. No threshold, latency, policy rule, cache, or historical evidence
changed.

Final readiness evidence:
- repair-203 path readiness: **PASS**
- sealed repair caches validated: **47**
- frozen policy scenarios: **60**
- focused tests: **5 passed**
- canonical repository regression: **1332 passed, 22 subtests passed in 77.32 s**
- strategy not run
- outcomes not accessed
- P&L not calculated
- orders: 0

Next after safe closeout: run the committed repair-203 path runner with
`--simulate` to regenerate the exact frozen 60 outcome-blind policy scenarios
against the repaired caches. Inspect the resulting path states and any residual
monitoring censorship before any settlement-dependent P&L evaluation.

<!-- CHECKPOINT21N_Y_C_PNL_FREEZE_PROJECT_STATE_20260903 -->
## Checkpoint 21N-Y-C — Candidate-E July-10 P&L evaluation frozen pre-outcome

Evidence: repaired path `cd49f0c72548c7715f1025a828b7af1321c02139af926e970e7816945bd69daa`; censorship refinement `e4722f37bc001e40b84654d230dccf914f13bf98430aef833fd9efb1e6767439`; 60 scenarios = 15 settings x 4 July-10 events; 27 exact / 33 censored.

Exact paths may receive point P&L after authoritative settlement only when needed. Censored paths receive no point estimate and use `[-$2.0700,+$2.00]`. All four events remain in every setting; exact coverage is shown as n/4; robustness uses the four-event event-equal interval. Settlement must be a finalized, non-provisional binary Kalshi record with consistent yes/no result and 0/1 settlement value.

July 10 remains development/mechanics evidence only, not a fresh validation gate. Outcome-driven retuning/selection is forbidden. At freeze: outcomes not accessed, P&L not calculated, strategy not rerun, network 0, orders 0; execution remains unauthorized.

<!-- CHECKPOINT21N_Y_D_SETTLEMENT_SCORER_PROJECT_STATE_20260903 -->
## Checkpoint 21N-Y-D — settlement scorer implemented, outcomes still sealed

The July-10 P&L contract remains frozen at 27 EXACT / 33 CENSORED scenarios.
A minimal raw-first settlement reader/scorer is now implemented but real outcome
access remains gated.

The future collector:
- derives only exact-path settlement-fallback tickers;
- uses the public Kalshi historical-market endpoint;
- archives raw HTTP before transformation;
- validates only finalized non-provisional binary yes/no 0/1 settlements;
- caches normalized settlement evidence per ticker;
- scores exact paths using frozen cash accounting;
- leaves censored paths interval-valued;
- reports all 15 settings x 4 events without selecting a winner.

Real collection is fail-closed unless this implementation is clean, synchronized,
and recorded by the safe checkpoint closeout receipt.

Current safety state: outcomes not accessed, strategy P&L not calculated,
strategy not rerun, network requests 0, orders 0. Execution remains unauthorized.

## Checkpoint 21N-Y-D1 — historical-list settlement transport pending closeout

The first authorized settlement request failed closed with HTTP 404 on the
singular historical-market route. Raw HTTP evidence was preserved and no
normalized settlement or P&L artifact was created.

Settlement transport is amended to `/historical/markets` with one exact
`tickers` filter per call. A successful response must contain exactly one market
whose ticker exactly matches the request.

The D1 implementation edits are transport-only. Frozen evaluation remains:
- 27 EXACT / 33 CENSORED;
- two exact settlement tickers;
- censored interval `[-2.0700, 2.00]`;
- no July-10 policy ranking/selection or retuning;
- July 10 remains development/mechanics evidence.

Real outcome collection is blocked until D1 is validated, committed, and
pushed. Execution remains unauthorized.

## Checkpoint 21N-Y-D2 — partition-aware settlement resolver pending validation

D1 returned a valid historical-markets response with zero exact matches. This is
consistent with Kalshi's live/historical storage partition: recent settled
markets may remain on `/markets` until they pass the moving historical cutoff.

D2 resolves each frozen exact settlement ticker by querying live/recent
`/markets` first and querying `/historical/markets` only if the same exact
ticker is absent from live. Both tiers use the same exact `tickers` filter.
Multiple matches, wrong ticker, non-finalized market, provisional result, or
inconsistent binary settlement fail closed.

Frozen economics remain unchanged:
- 27 EXACT / 33 CENSORED;
- two exact settlement tickers;
- censored interval `[-2.0700, 2.00]`;
- no July-10 policy ranking/selection or retuning;
- no strategy rerun or execution.

Real outcome access is blocked until D2 passes validation and is safely pushed.

<!-- CHECKPOINT21N_Y_E1_SETTLEMENT_SENSITIVITY_PROJECT_STATE_20260903 -->
## Checkpoint 21N-Y-E1 — settlement sensitivity predeclaration

The official July-10 evaluation remains immutable: 27 EXACT / 33 CENSORED and
all 15 policy settings `INCONCLUSIVE`.

E1 freezes a separate post-outcome exploratory sensitivity:
- exact 27 keep official P&L unchanged;
- 3 liquidation-only censored scenarios may settle known residual positions;
- 30 selection/re-arm-censored scenarios remain incomplete at strategy level;
- all censored observed traces may receive descriptive terminal values;
- all 93 observed fills may receive independent settlement diagnostics.

The exact future settlement ticker universe is derived from the frozen
outcome-blind path before additional settlement access. E1 makes zero network
requests and accesses no new outcomes. No policy ranking, retuning, or execution
is authorized.

<!-- CHECKPOINT21N_Y_E2_SETTLEMENT_SENSITIVITY_EVALUATOR_PROJECT_STATE_20260903 -->
## Checkpoint 21N-Y-E2 — settlement sensitivity evaluator implementation

E1 is safely closed at checkpoint
`2a780112f3480a647f89def800b9e2c09fce59ea` with receipt
`0b3acf6e720d5ee8ee11e7ddee66a79452663a59`.

The official July-10 outcome evaluation remains immutable:
27 EXACT / 33 CENSORED; 15/15 official policy settings INCONCLUSIVE.

E2 implements a separate post-outcome exploratory sensitivity evaluator over the
12 settlement tickers frozen before additional outcome access. It reuses the D2
partition-aware raw-first transport and fails closed on wrong/multiple/missing or
non-finalized/non-binary market records.

The evaluator preserves exact official P&L, terminalizes only known residual
positions, keeps selection/re-arm-censored scenarios incomplete at strategy level,
and produces independent entry settlement diagnostics for the 93 observed fills.

Real additional settlement access remains blocked until E2 is safely closed and
pushed. No ranking, retuning, strategy rerun, or execution is authorized.

<!-- CHECKPOINT21N_Z_A_PROSPECTIVE_WEEK_PROJECT_STATE_20260903 -->
## Checkpoint 21N-Z-A — prospective one-week strategy predeclaration

E2 sensitivity is recorded: 24/33 censored observed traces positive, 3 negative, 6 zero; 60/93 observed fills positive if independently held to settlement; 3 liquidation-only cases terminalized; 30 selection/re-arm cases remain incomplete; official July-10 result remains INCONCLUSIVE. Next fresh policy is frozen before collector implementation: Candidate E unchanged, `.02` net-edge primary threshold, current V2 convergence exit, maximum one re-entry, and 168 consecutive hours. Production remains read-only; live timing may be measured but orders may not be submitted.

<!-- CHECKPOINT21N_Z_B_LIVE_COLLECTOR_PROJECT_STATE_20260903 -->
## Checkpoint 21N-Z-B — prospective live collector implementation

The next implementation layer is a production read-only KXBTCD live collector.
It consumes the frozen Z-A `.02` Candidate-E policy, reconstructs full event
order books from Kalshi snapshots/deltas, blocks decisions on sequence gaps until
fresh snapshot recovery, preserves raw input before transformation, and records
monotonic feed/model/signal timing.

Z-B itself does not arm the 168-hour cohort and does not authorize or implement
demo, paper, or production orders.

<!-- CHECKPOINT21N_ZB_LIVE_VALIDATION_REPAIR_20260903 -->
## Checkpoint 21N-Z-B live validation and repair closeout evidence ? 2026-09-03 local / 2026-09-04 UTC

The closed Z-B implementation was validated against live Kalshi production market data and Coinbase BTC-USD completed-minute data.

Two live-interface mismatches were discovered before successful signal evaluation:

1. `GET /markets?status=open` returned KXBTCD market lifecycle rows with `status="active"`. The collector had incorrectly required returned status `open` and discarded all 238 live markets. The parser now requires the observed lifecycle state `active`; the REST query remains `status=open`.
2. Live `orderbook_snapshot` frames may omit an empty `yes_dollars_fp` or `no_dollars_fp` property. Omission only is normalized to an empty side. Explicit null, wrong-type, malformed, invalid-price, or invalid-quantity values still fail closed.

A third lifecycle repair prevents later legitimate checkpoints from disabling Z-B network smoke authorization. The smoke gate now requires the immutable closed Z-B receipt
`e82a3f4957be73db39cfdb36617e4ead3bbb78bf`
to remain in current Git ancestry rather than requiring the latest closeout receipt message itself to be Z-B.

Prospective smoke artifacts are now excluded from Git under `data/prospective_smoke/`.

Transport smoke:
- run: `candidate_e_smoke_20260904T015852Z`
- event: `KXBTCD-26SEP0322`
- subscribed markets: 188
- Kalshi WebSocket messages: 7,515
- decision calls: 2,190
- decision status: 2,190 `OUTSIDE_ENTRY_WINDOW`
- unique snapshot tickers: 188 / 188
- sequence gaps: 0
- orders: 0
- production writes: 0
- raw SHA-256: `2429fef630f5dd5b96ec830300a5c934b6ef5ea0f6da5c6a32508add49c924c4`
- decisions SHA-256: `5e7431eae7f6c79663b817f9a0a45c641148116b03cfcf2bc9e165eb3170bbc8`
- manifest SHA-256: `7a01eb337a3742a4cf75c38fd81c1070bc1bc39ab5ab8e9825c2672571a76686`

The transport smoke occurred inside the final T-2 exclusion zone and therefore validates transport/book continuity only, not Candidate-E entry economics.

In-window signal smoke:
- run: `candidate_e_smoke_20260904T020640Z`
- event: `KXBTCD-26SEP0323`
- subscribed markets: 188
- Kalshi WebSocket messages: 11,502
- decision calls: 2,890
- `KALSHI_BOOKS_NOT_EXACT`: 187 startup/recovery-state evaluations
- `EVALUABLE`: 2,703
- primary `$0.02` signal-bearing evaluations: 2,703
- sequence gaps: 0
- orders: 0
- production writes: 0
- raw SHA-256: `1bb6f842a0125e21e596a378ff224f165023b469d391535befcbbcff14d5d200`
- decisions SHA-256: `3e6cb894191163de83b8f251224bf793a31c0d9efe32211e68633a322bf3b82a`
- manifest SHA-256: `78b8df5a8abde32a3a8e7d3449cfec87986222cacdfc21e4d51c4d48f76b38c0`

The 2,703 signal-bearing evaluations are highly correlated book-change reevaluations, not 2,703 independent trades. They collapsed to three ticker/side selections and 15 selection transitions.

Observed primary net-edge distribution:
- min: 0.03768211334724974
- median: 0.04218642600278958
- p95: 0.04658905110545961
- max: 0.04658905110545961

Observed selected-level depth:
- min: 1 contract
- median: 389 contracts
- max: 2,171 contracts

Two exact completed Coinbase minute states were used during the in-window smoke:
- 80,870.97
- 80,872.78

Representative YES/NO signal arithmetic was independently decomposed for all three selected ticker/side pairs. In every case:
`net edge = selected-side fair probability - executable entry price - entry fee`
reconciled to floating-point noise only, approximately `1e-17`.

This validates the live Candidate-E signal path from exact completed Coinbase minute state through BTC/strike distance, frozen Candidate-E probability, Kalshi book midpoint, YES/NO conversion, executable entry price, fee accounting, and frozen `$0.02` signal rule.

This is engineering/live-signal validation only. It is not evidence that 2,703 independent opportunities existed and does not establish profitability.

Current authorization remains read-only. Real-money, demo, and live paper execution remain prohibited until the separately frozen risk gates are satisfied and explicitly amended.

<!-- CHECKPOINT21N_ZC_RUNTIME_ARCHITECTURE_DESIGN -->
## Checkpoint 21N-Z-C ? production-shaped runtime architecture design

Design fingerprint:
`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`

Z-C freezes the permanent runtime boundaries before implementation:
- Coinbase public BTC-USD matches+heartbeat WebSocket with strict gap recovery;
- exact completed-minute Candidate-E semantics unchanged;
- validated Kalshi full-event-ladder production WebSocket;
- durable raw-before-transform journaling and restart reconciliation;
- Linux cloud/Docker deployment target with outcome-blind region benchmark;
- separate read-only dashboard;
- separate future execution-worker boundary.

No order code is added. The 168-hour prospective cohort is not armed.
RISK_POLICY remains unchanged and execution remains prohibited.

<!-- CHECKPOINT21N_Z_D_COINBASE_RUNTIME_RECOVERY_20260904 -->
## Checkpoint 21N-Z-D ? Coinbase runtime/recovery validation state

The production-shaped Coinbase component has now completed its focused local
implementation and live read-only recovery validation.

Accepted engineering evidence includes:

- exact completed-minute close from public `BTC-USD` matches;
- raw frame persistence before transformation;
- heartbeat/trade-ID missing-match detection;
- bounded REST latest-page visibility waiting;
- fail-closed REST coverage proof;
- conservative cross-transport duplicate identity checks;
- successful deliberately induced missing-match recovery.

Canonical recovery run:

`candidate_e_coinbase_recovery_smoke_20260904T040632Z`

Canonical recovery raw SHA-256:

`8198AEBAFBA03E4331009CC2F62E0CCC27F13FA57E347A5359F81FAC18194F7F`

Canonical recovery manifest SHA-256:

`A1BC96364BBB35298DC83F295EF867B98F3565AF1E06C488D76205AE23523B19`

The final recovery required five latest REST visibility requests and zero older
pagination requests before REST covered the WebSocket target.

Focused regression after final repair:

`38 passed in 1.32s`

Candidate-E model and strategy semantics remain frozen. The 168-hour
prospective cohort is not armed. Kalshi execution remains disabled and no
orders or production writes occurred.

Next production-runtime engineering priority:
restart-state and durable-state reconciliation validation.

<!-- CHECKPOINT21N_Z_E_A_RESTART_DURABLE_DESIGN_20260904 -->
## Checkpoint 21N-Z-E-A — Restart/durable-state design freeze

Design fingerprint: `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

Every new process starts signal-disabled. Old live-state freshness is never
reused. The fixed 168-hour cohort never pauses or extends, and downtime is
recorded as a prospective observation gap rather than backfilled.

SQLite is frozen to WAL + `synchronous=FULL`. Exact arm Git identity is
required. Current phase remains read-only with no order/fill/position state.

Next: Z-E-B implementation and crash/restart validation.

<!-- CHECKPOINT21N_Z_E_B1_SQLITE_CORE_20260904 -->
## Checkpoint 21N-Z-E-B1 — Offline SQLite durable-state core

The first implementation slice of Z-E-B is validated locally.

Frozen restart design fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

B1 now provides the offline persistence/session foundation:

- seven-table SQLite schema;
- WAL + synchronous FULL;
- runtime sessions;
- durable heartbeat updates;
- clean shutdown state;
- detection/classification of prior unclean sessions;
- conservative process-discontinuity gaps;
- cross-session monotonic reset without cross-session freshness reuse.

Focused validation: `17 passed in 0.64s`.

B1 deliberately refuses canonical prospective database paths and cannot arm the
168-hour cohort.

Coinbase/Kalshi restart gates, raw-reference reconciliation, and the complete
restart matrix remain unfinished.

Next implementation priority: continue Z-E-B with durable raw-reference and arm
identity reconciliation before source restart integration.

<!-- CHECKPOINT21N_Z_E_B2_RECONCILIATION_20260904 -->
## Checkpoint 21N-Z-E-B2 — Offline identity/raw-reference reconciliation

The second Z-E-B implementation slice is validated locally under restart-design
fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

B2 now provides:

- synthetic arm-manifest / SQLite identity reconciliation;
- exact armed Git identity;
- per-session create-exclusive raw segments;
- exact raw-record references for durable decisions;
- pending decision verification;
- explicit `RAW_EVIDENCE_GAP` classification;
- preservation of partial crash tails without truncation;
- no reconstruction of decisions missed during a crash.

Focused validation:

`14 passed in 1.26s`

B1+B2 together now cover offline session durability and crash-evidence
reconciliation.

The canonical prospective path remains refused, the 168-hour cohort remains
unarmed, and Coinbase/Kalshi/signals/execution remain untouched.

Next implementation priority:
startup/restart gate state machine and clock-health gate before live-source
restart integration.

<!-- CHECKPOINT21N_Z_E_B3_RESTART_GATE_20260904 -->
## Checkpoint 21N-Z-E-B3 — Offline restart gate state machine

The third Z-E-B implementation slice is validated locally under restart-design
fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

B3 now provides the frozen restart-readiness state machine and clock gate:

- exact frozen states;
- fail-closed readiness precedence;
- startup signal-disabled state;
- unknown/unhealthy clock blocking;
- exact 250 ms absolute clock-offset limit;
- all-gates-required `READY_READ_ONLY`;
- immediate eligibility revocation on gate regression;
- no-backfill prospective observation-gap recording;
- fresh full reevaluation before readiness recovery;
- no reuse of prior signals.

Focused validation:

`18 passed in 1.10s`

B1+B2+B3 together now cover offline process durability, raw-evidence crash
reconciliation, and restart-readiness state transitions.

The canonical prospective database remains uncreated, the 168-hour cohort
remains unarmed, and Coinbase/Kalshi/Candidate-E signal computation/execution
remain untouched.

Next implementation priority:
wire authoritative current source readiness into the frozen Coinbase and Kalshi
gates, while remaining read-only and keeping the cohort unarmed.

<!-- CHECKPOINT21N_Z_E_B4_SOURCE_READINESS_20260904 -->
## Checkpoint 21N-Z-E-B4 — Current-source restart readiness

The fourth Z-E-B implementation slice is validated locally under frozen restart-design fingerprint:

`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

and production-runtime architecture fingerprint:

`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`.

B4 now wires current-source evidence into the frozen restart gate without arming the prospective cohort or adding execution:

- Linux production boot identity is read only from `/proc/sys/kernel/random/boot_id`; Windows is permitted only for explicitly injected synthetic validation boot IDs;
- chrony tracking evidence is parsed against the frozen absolute clock-offset threshold of 250 ms;
- Coinbase readiness requires the accepted completed-minute builder, current runtime session, current WebSocket connection generation, heartbeat/recovery health, and the exact current fully completed UTC minute;
- Kalshi readiness requires the accepted full-ladder cache, authoritative current-generation snapshot/sequence state, and independent current-connection Ping/Pong liveness;
- client Ping interval remains 15 seconds and Pong timeout 5 seconds, yielding a derived maximum accepted current-connection Pong age of 20 seconds;
- transport liveness does not heal sequence gaps, snapshot recovery, or book correctness;
- old-session and old-connection Coinbase/Kalshi state is rejected.

B4 validation evidence:

- source-readiness validator: `PASS`;
- focused B4 tests: `33 passed in 4.30s`;
- adjacent restart/live-collector regression: `67 passed in 2.75s`;
- full repository regression: `1508 passed, 22 subtests passed in 157.37s`;
- source-registry validation: `PASS` with 23 sources, 17 validated, 0 unresolved sources, and 1 unresolved settlement source.

The tested B4 implementation files were hash-verified after validation:

- source: `9583a90a2b45d65b79881121d53adea6d647251bcf13da255156a00be2514b0c`;
- tests: `45110d3a9936e1f124cd6cfb8310bca40ae8393be76a35f44e01bbfd9620e9cd`;
- validator: `97c7d752c6e27f88e2ce60b214c84c1da13d17b0643a898fd795ceb1ed224ef0`.

B4 remains offline/read-only validation. Its validator makes zero network requests, creates no canonical prospective database, does not arm the 168-hour cohort, does not compute Candidate-E signals, and places no orders.

Next implementation priority: complete the remaining frozen crash/restart matrix and a bounded live read-only restart validation, including actual connection-generation rollover, source-loss/recovery, host-reboot behavior, credential/redaction safeguards, and strategy-state reconciliation. Additional repair slices are permitted if evidence requires them; the planned B5 label is not a deadline or cap.

<!-- CHECKPOINT21N_Z_E_B5_R1_CREDENTIAL_BOUNDARY_20260904 -->
## Checkpoint 21N-Z-E-B5-R1 — Credential-boundary hardening

The first B5 safety slice is validated locally on top of the closed B4 receipt
`faaab2930b1ae21b78cba62be7ec528fcfc0dd16`.

B5-R1 establishes a fail-closed persistence boundary for raw-journal request
metadata before bounded live restart testing:

- prospective `RawJournal`, production-shaped `RuntimeRawJournal`, and
  restart-aware `RestartSessionRawJournal` all validate `request_identity`
  before serialization;
- credential/header/signing material, including authorization, cookie, token,
  signature, API/access-key, private-key, and Kalshi-access metadata, is
  rejected rather than journaled;
- nested request parameters are recursively checked;
- request URLs may not contain user-info, query strings, or fragments;
- unknown top-level request-identity fields remain rejected;
- existing safe Coinbase recovery metadata is explicitly allowlisted and
  type/value constrained: `phase`, `latest_attempt_index`, `cb_before`,
  `cb_after`, and `product_id`;
- recovery `phase` is limited to `latest_visibility` or `older_pagination`;
- `product_id` is limited to `BTC-USD`;
- Kalshi authentication headers remain direct-to-WebSocket-connect and are not
  copied into journal request metadata.

Validation evidence:

- initial credential-boundary validator: PASS, zero network;
- focused credential/live/restart regression: `59 passed in 2.28s`;
- adjacent B1-B4 restart/readiness regression: `78 passed in 4.39s`;
- first full regression exposed an over-narrow safe-metadata allowlist:
  `8 failed, 1537 passed, 22 subtests passed`;
- B5-R1-R2 added only the already-existing benign Coinbase metadata contract;
- repaired credential-boundary validator: PASS, zero network;
- targeted security + Coinbase REST/WS regression: `56 passed in 1.70s`;
- final full repository regression:
  `1553 passed, 22 subtests passed in 108.72s`.

The eight intermediate failures were compatibility failures, not evidence of
credential persistence. The final implementation preserves the credential
rejection invariant while accepting the pre-existing safe Coinbase metadata.

No network request was made by the B5-R1/R2 validators, the canonical
prospective DB remains uncreated, the 168-hour cohort remains unarmed,
Candidate-E execution remains disabled, and orders remain zero.

Next implementation priority: actual live read-only connection-generation
rollover and source-loss/recovery validation under the frozen B4 readiness
contract. Live validation must remain bounded and must not arm the prospective
cohort.

<!-- CHECKPOINT21N_Z_E_B5_R2_LIVE_RECONNECT_20260904 -->
## Checkpoint 21N-Z-E-B5-R2 — bounded live reconnect accepted

B5-R2 validates production-shaped read-only connection generation lifecycle
against real Coinbase/Kalshi market-data transports.

Accepted evidence:
- final focused B5-R2+B4 regression: `55 passed in 0.61s`;
- full Windows suite before live validation:
  `1575 passed, 22 subtests passed in 79.19s`;
- live run `candidate_e_b5_r2_20260904T072848Z`;
- KXBTCD event `KXBTCD-26SEP0404`, 188-market full ladder;
- Coinbase generations `1 -> 2`, stale generation rejected;
- Kalshi generations `1 -> 2`, stale generation rejected;
- both Kalshi generations rebuilt all 188 snapshots with 0 sequence gaps;
- raw evidence 2,526 records, all 2,526 valid JSON;
- source reconciliation:
  92 Coinbase WS + 1 Kalshi REST + 2,433 Kalshi WS = 2,526;
- manifest SHA:
  `F64B7669223518F36AE326B8F04D67CF8C24620F0437A2E1FA9319866267B6B6`;
- raw SHA:
  `C555C91708C788B8404360CB2DBCE954E6C15B4C50B8BAB37EF3572B620EE600`;
- six high-confidence credential marker classes: 0 hits.

B5-R2 does not validate process-crash restart, host reboot, long-duration
stability, Linux chrony/boot-ID deployment, or strategy profitability.

Safety state:
canonical prospective DB not created; cohort unarmed; signals 0; orders 0;
production writes 0; execution authorization unchanged/read-only.

Next engineering slice:
B5-R3 offline-first process-restart orchestration and real durable
strategy-reconciliation integration into the frozen restart gate.

<!-- CHECKPOINT21N_Z_E_B5_R3_A_DESIGN_20260904 -->
## Checkpoint 21N-Z-E-B5-R3-A — process-restart reconciliation design frozen

Design fingerprint: `0623977817c055b5557296b6e9a58ea371c0ea680728c6a68a52a1c5abfdffea`.

Next implementation is offline-first process restart orchestration. No new
persisted strategy-state table is allowed: prior decisions remain audit-only
while current ATM/probability/signal state is rebuilt from fresh sources.

Durability must resolve all pending raw decisions to VERIFIED or
RAW_EVIDENCE_GAP. A classified raw gap is preserved/excluded but does not
permanently block fresh recovery. Strategy reconciliation separately proves
that no prior actionable signal or execution state is restored.

Current authorization remains read-only. Canonical prospective DB uncreated;
168-hour cohort unarmed; no signal or execution work is authorized in this
design freeze.

<!-- CANDIDATE_E_MICRO_PRODUCTION_PATH_POLICY_20260904 -->
## Candidate-E intended execution path clarified

Current phase remains read-only.

The intended first real-money step after safety hardening and stable demo
validation is a tightly capped **micro-production validation**: one contract per
order at a $0.01 purchase limit price on the selected side, with fees and exact
run-level caps included.

A separate 168-hour read-only shadow cohort is not a mandatory prerequisite
unless explicitly reauthorized. If the 168-hour prospective program is retained,
the intended post-demo cohort is the micro-production validation cohort.

No scale-up is automatic. Exact run caps and direct approval remain required.

Policy-path fingerprint:
`57e7e5c88bd296128927362119c0f3705d4be9ce5f0d8a13c1fd652ddd2e2677`.

<!-- CHECKPOINT21N_Z_E_B5_R3_IMPLEMENTATION_20260904 -->
## Checkpoint 21N-Z-E-B5-R3 — process-restart implementation validated

B5-R3 design fingerprint:
`0623977817c055b5557296b6e9a58ea371c0ea680728c6a68a52a1c5abfdffea`.

Implemented and locally validated:

- new runtime session on each process start;
- clean/unclean prior-session classification;
- pending raw durability reconciliation to VERIFIED or RAW_EVIDENCE_GAP;
- no reconstruction/backfill of damaged prior evidence;
- neutral read-only strategy restart state;
- no restored prior ATM/probability/signal/re-entry/execution state;
- old-process Coinbase/Kalshi source state rejected;
- fresh all-gate recovery to `READY_READ_ONLY`;
- immediate blocking on post-ready gate regression;
- cohort-ended and execution-enabled fail-closed behavior.

Validation evidence:
`13` focused tests, `162` restart-stack tests, and
`1588 passed + 22 subtests` full repository regression.

Current phase remains read-only. No canonical prospective DB, cohort arm,
signals, orders, or production writes were added.

Next: bounded live read-only whole-process restart validation before moving to
the production-shaped order/risk implementation.

<!-- CHECKPOINT21N_Z_E_B5_R4_A_DESIGN_20260904 -->
## B5-R4-A — bounded live whole-process restart planned

B5-R3 is closed. The next planned validation combines live source rebuilding
with a real OS-process crash/restart.

Frozen design fingerprint:
`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`.

Required sequence:
process 1 fresh-readiness -> induced unclean termination -> process 2 new
runtime session -> prior crash classification -> blocked before fresh sources ->
fresh Coinbase/Kalshi rebuild -> `READY_READ_ONLY`.

Current authorization remains read-only. No cohort arm, signals, orders, or
production writes are part of this design.

Operational safety is tracked as a coverage matrix; a successful B5-R4 does not
by itself close host-reboot, long-soak, or execution/order-risk categories.

<!-- CHECKPOINT21N_Z_E_B5_R4_B_IMPLEMENTATION_20260904 -->
## B5-R4-B — live whole-process restart implementation ready for closeout

Frozen B5-R4 design:
`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`.

The bounded two-process crash/restart probe is now implemented and has passed
offline validation.

Evidence:
- contract validator PASS;
- B5-R4 focused tests: 25 passed;
- full restart stack: 187 passed;
- zero-network preflight PASS;
- full repository: 1613 passed + 22 subtests.

The live path still requires an explicit `--live` flag and must not be invoked
until this implementation is safely committed and pushed.

Current authorization remains read-only. No signals, cohort arm, orders, or
production writes were added.

<!-- CHECKPOINT21N_Z_E_B5_R4_C_KALSHI_LIVENESS_REPAIR_20260904 -->
## B5-R4-C — Kalshi liveness repair ready for closeout

The first live B5-R4 process-restart probe exposed an implementation mismatch,
not a failed market-data reconnect.

Process 2 received 9,955 fresh Kalshi application frames, including all 188
order-book snapshots and 9,766 deltas, before a later manual Pong timeout
aborted the worker.

B5-R4 previously applied an immediate-fatal 5-second manual Pong rule and a
10-second manual Ping cadence. The frozen B4 contract is 15s Ping + 5s timeout,
with readiness determined by the age of the most recent successfully proven
Pong and `KALSHI_PONG_STALE` after 20 seconds.

The repair aligns B5-R4 to B4 without weakening fail-closed behavior.

Validation:
- 30 focused B5-R4 tests passed;
- 192 integrated restart-stack tests passed;
- 1618 full-repository tests + 22 subtests passed;
- exit code 0.

Next after safe closeout:
rerun the bounded B5-R4 live two-process crash/restart probe. Execution remains
disabled.

<!-- CHECKPOINT21N_Z_E_B5_R4_LIVE_PASS_20260904 -->
## B5-R4 live whole-process restart — PASS

Accepted run:
`candidate_e_b5_r4_20260904T090313Z_c3ff9837`.

The validation used two real OS processes. Process 1 reached fresh
`READY_READ_ONLY` and was deliberately killed without clean shutdown. Process
2 detected `UNCLEAN_DETECTED`, began blocked, verified the pending raw
durability evidence, rebuilt fresh Coinbase and Kalshi state, and reached
`READY_READ_ONLY`.

Evidence:
- PIDs `26580 -> 41280`;
- process 2 `1` pending examined, `1` verified, `0` pending after;
- both source gates PASS in both relevant final states;
- zero Kalshi sequence gaps in both processes;
- successor shutdown CLEAN;
- prior signal reusable false;
- process 1 Ping/Pong `3/3`, process 2 `4/4`, zero timeouts;
- raw secret hits 0;
- 18 artifact hash entries independently checked, 0 mismatches;
- canonical prospective DB false;
- cohort false;
- signals 0;
- orders 0;
- production writes 0.

B5-R4's declared whole-process restart category is therefore complete after
safe documentation closeout.

Still unresolved before micro-production:
production Linux boot/clock validation, soak stability, and the later
production-shaped order/risk/demo execution categories.

<!-- CHECKPOINT21N_Z_E_B5_R5_A_AWS_LINUX_HOST_VALIDATION_20260904 -->
## B5-R5-A — AWS production-shaped host and Linux reboot/clock validation PASS

The first production-shaped Linux host has been provisioned in AWS and the
previously open host-reboot / Linux boot-ID / chrony operational category now
has direct production-environment evidence.

Accepted AWS baseline:
- region: `us-east-1`;
- physical Availability Zone ID: `use1-az4`;
- account-local AZ name: `us-east-1c`;
- instance class: `m7i-flex.large`;
- OS: Amazon Linux 2023 x86_64;
- root storage: 100 GiB gp3;
- administration: AWS Systems Manager Session Manager;
- EC2 key pair: none;
- security-group inbound rules: none;
- IMDSv2: required;
- repository access: repo-scoped read-only GitHub deploy key;
- execution authorization: unchanged / read-only.

Installed production-shaped toolchain:
- Python `3.11.16`;
- Docker Engine active;
- Docker Compose `v5.5.1`;
- repository clone exactly matched
  `bed0796cf0f85d375635f0acb2088b221fccce9b`.

Linux compatibility evidence:
- fresh clone discovered the same 1,618 regular pytest tests;
- 11 initially failed and 4 skipped solely because Git-ignored historical
  `data/analysis`, `data/derived`, and `data/manifests` artifacts are intentionally
  absent from the production host;
- after deselecting exactly those 15 historical-artifact-dependent integration
  tests, the production-contained suite passed:
  `1603 passed, 15 deselected`;
- Git remained clean.

Controlled host reboot evidence:
- pre-reboot boot ID:
  `ca870b4a-9490-4328-8f1a-c55fe2046117`;
- post-reboot boot ID:
  `0d6faadc-2fae-40bd-aa78-5d86807f8702`;
- the changed boot ID proves a real Linux OS reboot occurred;
- `chronyd`, `amazon-ssm-agent`, and `docker` automatically returned active;
- post-reboot `timedatectl` reported synchronized UTC/NTP state;
- post-reboot shell-level chrony offset was `0.032553 ms`;
- the application's real production boot adapter returned `PASS`,
  `source=linux_kernel_boot_id`, `validation_only=False`;
- the application's real production chrony adapter returned `PASS` with
  absolute offset `0.002674 ms` and leap status `Normal`;
- both are far inside the frozen absolute 250 ms clock gate.

Operational conclusion:
`host_reboot_and_clock_boot_identity` now has explicit PASS evidence on the
intended Linux cloud host.

This does not establish:
- long-duration runtime/observability stability;
- source latency/jitter adequacy over time;
- empirical storage bytes/hour or the final free-disk gate;
- production container/service long-run recovery;
- dashboard runtime isolation;
- order submission, fills, cancellation, positions, cash reconciliation,
  exposure/loss limits, kill switch, partial fills, or demo qualification;
- profitability.

Current authorization remains read-only. No cohort was armed, no strategy signal
was generated during this host validation, and no order or production write was
performed.

Next operational category:
freeze and validate a bounded long-duration read-only AWS runtime/soak program
before production-shaped order/risk implementation.

<!-- CHECKPOINT21N_Z_E_B5_R5_A_R2_CLOSEOUT_UTF8_REPAIR_20260904 -->
## B5-R5-A-R2 — checkpoint-closeout Git UTF-8 repair PASS

During the B5-R5-A documentation closeout on Windows, the safe-closeout helper
failed after successful validation while reading a staged Git diff. Python's
platform-default `cp1252` text decoding could not decode UTF-8 byte `0x9d`,
which caused the Git reader thread to fail and the subsequent secret-scan path
to receive no decoded stdout.

The helper failed before commit/push and safely returned the approved files to
an unstaged working-tree state.

Accepted repair:
- protected tooling commit:
  `f5dd81a2edbc4a0d2075c28b62289c1e7ce38ed6`;
- generic subprocess behavior remains unchanged by default;
- only the closeout helper's Git wrapper explicitly requests UTF-8 decoding;
- focused closeout regression: `28 passed`;
- real Windows Git-diff reproduction with `PYTHONUTF8=0`: PASS;
- reproduction included U+201D whose UTF-8 representation contains byte
  `0x9d`, matching the original decode-failure byte;
- source-registry validation: PASS;
- full repository regression:
  `1619 passed, 22 subtests passed`;
- manual protected-tooling staging, whitespace check, secret scan, commit,
  push, remote synchronization, and clean-worktree verification: PASS.

This repair changes repository closeout tooling only. It does not modify market
data, strategy logic, execution authorization, AWS runtime behavior, or risk
policy.

Current authorization remains read-only.

<!-- CHECKPOINT21N_Z_E_B5_R5_B_A_AWS_READ_ONLY_SOAK_DESIGN_20260904 -->
## B5-R5-B-A — AWS read-only soak design frozen

The next production-host validation program is now predeclared.

Design fingerprint:
`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`.

Program:
- dedicated read-only soak runner;
- Docker Compose production-shaped packaging;
- 1-hour AWS shakedown;
- empirical storage-rate review and free-disk gate freeze;
- 24-hour continuous AWS soak;
- separate post-soak controlled unclean process restart.

The soak will exercise real Coinbase/Kalshi source generations, KXBTCD event
rollover, real Linux boot identity, real chrony state, source readiness,
reconnect/recovery, resource use, latency/jitter evidence, and storage growth.

The design also freezes the 300-second initial-readiness classification, atomic
run-manifest identity, empirical free-disk formula, crash-safe verified segment
closure, non-privileged container credential/chrony boundary, and exact
same-image/same-volume post-soak restart requirement.

No soak has run yet. No credentials were provisioned by this design checkpoint.

Current authorization remains read-only. Orders and production writes remain
prohibited.

<!-- CHECKPOINT21N_Z_E_B5_R5_B_B_A_CLOCK_EVIDENCE_BRIDGE_20260904 -->
## B5-R5-B-B-A — Clock-evidence transport amendment prepared

AWS diagnostics found that the frozen direct chronyd-socket container transport
is not viable: both bridge-network and host-network socket-bind tests returned
`506 Cannot talk to daemon`.

A replacement transport is now predeclared at amendment fingerprint:

`eaf9525f726f4beaad6f7f4bc3e3704534459a1033ec28a1c4656def7121813f`

The host will publish real chrony/boot/time-namespace evidence through an atomic
file managed independently of the SSM session. The Docker runtime consumes that
file through a read-only mount and fails closed on stale, invalid, mismatched, or
failed evidence.

The parent B5-R5-B-A design remains immutable at:

`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`

No market-data soak has run. Current authorization remains read-only. Orders and
production writes remain prohibited.

<!-- B5_R5_B_PROSPECTIVE_RESEARCH_DATA_ARCHIVE_20260904 -->
## Prospective research-data archive requirement

The production-shaped collector is now required to preserve a strategy-independent
prospective KXBTCD research corpus.

Collection scope is the complete selected KXBTCD event ladder plus the independent
Coinbase BTC source evidence needed to reconstruct market state. Raw evidence,
timestamps, connection generations, sequence/recovery state, and integrity
metadata must be retained regardless of whether Candidate E would trade a
particular ticker.

This turns successful prospective collection into reusable evidence for future
champions and controlled Candidate-E lifecycle research.

Automatic retraining after poor performance is not authorized. New data must
enter a predeclared development/validation lifecycle with genuinely untouched
later evidence.

The B5-R5-B hourly raw-segment format is the initial archival unit. Durable
off-host archival remains pending before indefinite continuous collection.

Current authorization remains read-only.


<!-- SOAK_OBSERVABILITY_COMPONENT_20260906 -->
## 21N-Z-F observability component — 2026-09-06

Durable observability consumer and lifecycle integration are offline-tested (227 infrastructure tests passed). This is a component milestone, not closure of B5-R5-B-B. Production metric producers, complete archive/recovery inventory, idle fsync verification, CLI/Compose integration, and AWS validation remain open. See SOAK_OBSERVABILITY_IMPLEMENTATION.md.
## 21N-Z-F offline producer/package checkpoint — 2026-09-06

The local untracked soak implementation now has producer wiring, fake-source
coverage, idle fsync, recovery inventory, package preflight, Compose files, and
an observed lifecycle orchestrator. Combined offline regression: **235 passed
in 12.51 seconds**. This is not Docker or AWS validation.

<!-- CHECKPOINT21N_Z_F_PACKAGED_CLOCK_PREFLIGHT_20260906 -->
## 21N-Z-F packaged clock-preflight evidence — 2026-09-06

The read-only container preflight is implemented and published through commit
`dc010d8`. It samples the real mounted host clock-evidence bridge before a
runtime can be constructed and rejects any result other than `PASS`.

AWS host evidence on the intended Amazon Linux instance:

- `chronyd` is active; the systemd-managed publisher writes
  `/var/lib/kxbtcd-soak/clock-evidence.json` every second;
- a non-root, read-only, capability-dropped container passed preflight against
  that file with Docker network mode `none`;
- the same command against a disposable `{}` file failed with
  `SoakPackageError: host clock evidence is not PASS` and exit status `1`;
- the container image was built directly because host Compose requires buildx
  `0.17+` while the installed buildx is `0.12.1`.

No Coinbase or Kalshi transport was started. No settlement, signal, P&L,
order, or production-write path ran. The dedicated source-runner CLI and the
1-hour shakedown remain open.

<!-- B5_R5_B_R16_ACCEPTED_SHAKEDOWN_20260907 -->
## B5-R5-B-C R16 accepted one-hour shakedown — 2026-09-07

Compose-packaged AWS run `kxbtcd_shakedown_20260907_r16` completed its full 3,600-second active window with a terminal manifest and safety status `PASS`. Read-only boundaries held: orders, signals, and production writes were all zero. Coinbase stayed on generation 1 with no reconnects. Kalshi recorded 339 Pings and 339 Pongs, no Pong timeout, no sequence gap, and 10 safe `ConnectionClosedError` records across 14 reconnect attempts. Availability was 95.6776% (3,444.39 ready seconds; 155.61 blocked seconds).

The original frozen design remains immutable. The library keepalive amendment `5a52b3f6cf8b2a22983e130969f82ad5b1e0303e237a220ef4322594c3c58e3b` records the effective 10-second Ping / 10-second timeout implementation. R16 is the qualifying empirical input for the immutable 24-hour storage-gate receipt. No 24-hour run has started.

<!-- B5_R5_B_24H_1_REJECTED_COINBASE_CANDLE_PUBLICATION_20260907 -->
## B5-R5-B-D first 24-hour launch rejected before measurement — 2026-09-07

Run `kxbtcd_soak_20260907_24h_1` terminalized before first readiness after a public Coinbase candle request returned HTTP 200 with an empty `[]` body at the exact minute boundary. The prior implementation classified the temporarily unpublished completed-minute candle as `ProspectiveLiveCollectorError`, causing a fail-closed hard failure. Active duration was zero, so this is not 24-hour evidence. Orders, signals, and production writes remained zero.

The narrow repair persists the raw `[]` response, classifies only this typed condition as a recoverable Coinbase transport condition, and uses the existing reconnect backoff while readiness remains blocked. It does not accept an empty candle or permit stale Coinbase state. Targeted regression: 25 passed in 3.79 seconds. A new one-hour shakedown is required because runtime code changed; the existing R16 storage receipt cannot arm a new image.

<!-- B5_R5_B_R17_REQUALIFICATION_20260907 -->
## B5-R5-B-C R17 fixed-image requalification — 2026-09-07

Run `kxbtcd_shakedown_20260907_r17` completed the full 3,600-second active window using image `sha256:fa4aa1649cd1d0752842e4ef588c2068e1c418ba374a4268123c9c7fb64ec609`. It reached `READY_READ_ONLY`, terminalized with manifest `MEASUREMENT_COMPLETE`, and passed all hard safety invariants: orders, signals, and production writes were zero; clock and identity remained PASS; Coinbase had no reconnects; Kalshi had zero sequence gaps. This requalifies the corrected Coinbase unpublished-candle behavior for the deployed image.

Availability was 72.3108% (2,603.19 ready seconds; 996.81 blocked seconds), with 76 Kalshi reconnect attempts and zero observed Pong timeouts. The frozen design has no numeric availability threshold, so the run satisfies its mandatory shakedown gate while preserving this reliability evidence for the 24-hour interpretation. The R16 receipt is superseded because the runtime image changed. Freeze a new receipt from R17 immediately before the canonical arm.

<!-- V2_MICRO_HYBRID_OFFLINE_FREEZE_20260907 -->
## Candidate-E V2 hybrid micro-probe offline freeze

The future Candidate-E V2 micro probe is frozen in `configs/kxbtcd_candidate_e_v2_micro_hybrid_probe_freeze_v1.json`: `0.01` contracts per order only after verifying the target market increment; bounded IOC entry attempts; one reduce-only GTC protection exit; continuous full-ladder monitoring; then cancel, authoritative reconciliation, and one full-remainder reduce-only FOK handoff. The hybrid has one exit writer and fails closed on stale/gapped feeds, unhealthy clock evidence, ambiguous venue state, or insufficient full depth.

`src/kxbtcd_candidate_e_v2_micro_hybrid_exit_offline.py` is offline-only and has no network, credentials, order outbox, order creation, cancellation, or production write. It evaluates confirmed resting-fill proceeds plus exact remaining ladder proceeds. Shadow scenarios must read closed immutable segments in a separate process and directory, with no shared sockets, credentials, order state, or event loop.

The active `kxbtcd_soak_20260907_24h_2` read-only container is unchanged. A terminal 24-hour review and controlled restart evidence remain required before any exact micro-probe authorization; a demo is optional for isolated API mechanics, not a mandatory week-long predecessor.

<!-- V2_MICRO_HYBRID_OFFLINE_TESTS_20260907 -->
## 2026-09-07 — Hybrid offline control suite

The hybrid exit evaluator, closed-segment shadow reader, and offline lifecycle
model passed 17 focused tests. The suite exercised full-depth accounting,
partial resting fills, cancel/reconcile re-evaluation, FOK eligibility ordering,
closed-segment verification, and bounded entry attempts. No network or execution
path ran.
