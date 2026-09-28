# Experiment Log

The first outcome-analysis experiment is recorded below as EXP-001. Earlier entries include engineering/source validation and blocked pre-analysis work. No entry establishes executable market edge or profitability.

## Engineering validation checkpoints

### ENG-001 — Raw REST archive isolated unit validation
- Date: 2026-08-03
- Result: 8 tests passed.
- Scope: raw HTTP preservation, timing, hashes, source timestamps, errors, and fail-closed persistence.

### ENG-002 — Raw REST archive canonical Windows validation
- Date: 2026-08-03
- Result: 9 tests passed.
- Interpretation: raw-preservation changes worked in the user's Python 3.11 environment.

### ENG-003 — Live raw REST smoke validation
- Date: 2026-08-03
- Result: successful market discovery plus a 60-second order-book run with 30 raw records, 30 derived rows, and zero raw errors.
- Safety: public read-only; no orders.

### ENG-004 — Run-manifest and integrity-validator validation
- Date: 2026-08-03
- Result: lifecycle/tamper tests passed; checkpoint committed at `3ad29ba`.
- Interpretation: runs can be tied to arguments, code identity, artifacts, hashes, counts, and completion state.

### ENG-005 — Raw-to-derived lineage unit validation
- Date: 2026-08-03
- Command: `.\.venv\Scripts\python.exe -m pytest -q`
- Result: 20 tests passed in 0.77 seconds.
- Interpretation: accepted derived rows can be reconciled to exact persisted raw request records.

### ENG-006 — Live raw-to-derived lineage reconciliation
- Date: 2026-08-03
- Ticker: `KXBTC15M-26AUG030700-00`
- Result: 10 raw records, 10 derived rows, zero raw errors; semantic validation completed without error.
- Safety: no orders.

### ENG-007 — Structured runtime observability isolated validation
- Date: 2026-08-03
- Result: 35 tests passed in isolated generation.
- Covered behavior: runtime event sequencing, clocks, correlation, redaction, persistence failure, endpoint validation, terminal lifecycle, manifest-v2 checks, and historical v1 compatibility.

### ENG-008 — Structured runtime observability canonical Windows validation
- Date: 2026-08-03
- Result: 35 tests passed in 25.71 seconds.

### ENG-009 — Live scanner runtime-observability validation
- Date: 2026-08-03 local / 2026-08-04 UTC artifacts
- Run ID: `scan_btc_markets_20260804T031830261714Z_30886e6c`
- Result: 1 raw record, 3 runtime events, zero runtime error events, offline validation PASS.
- Safety: public read-only; no orders.

### ENG-010 — Live order-book runtime-observability validation
- Date: 2026-08-03 local / 2026-08-04 UTC artifacts
- Ticker: `KXBTC15M-26AUG032330-30`
- Run ID: `record_orderbook_20260804T032038103539Z_5993bd6f`
- Result: 10 raw records, 10 derived rows, 12 runtime events, zero errors, offline validation PASS.
- Safety: no orders.

### ENG-011 — Structured runtime observability Git closeout
- Date: 2026-08-03
- Commit: `0c34e0f` — `Add structured runtime observability`
- Result: local and remote `main` synchronized and worktree clean.

### ENG-012 — Source registry and settlement-validation candidate
- Date: 2026-08-03 local / 2026-08-04 UTC
- Result: registry PASS with initial 5-source contract; candidate regression 43 passed.
- Interpretation: source authority/authentication/quality contracts became machine-readable; complete settlement remained unresolved.

### ENG-013 — Source registry canonical Windows validation and live rule inspection
- Date: 2026-08-03 local / 2026-08-04 UTC
- Ticker: `KXBTC15M-26AUG040000-00`
- Registry: PASS.
- Regression: 43 passed in 4.16 seconds.
- Live rule result: later 60-second BRTI average `>=` earlier 60-second BRTI average resolves Yes; exact tie therefore Yes.
- Timing: `open_time=2026-08-04T03:45:00Z`, `close_time=2026-08-04T04:00:00Z`, `expiration_time=2026-08-11T04:00:00Z`.
- Safety: no credentials or orders.

### ENG-014 — Authenticated CF Benchmarks WebSocket registry candidate
- Date: 2026-08-03 local / 2026-08-04 UTC
- Change: registered `kalshi.cfbenchmarks_value.websocket.v1` as documented authenticated delivery, not collected.
- Result: 6-source registry PASS; regression 46 passed in isolated validation.
- Safety: no WebSocket connection or credentials.

### ENG-015 — Source registry final canonical Windows validation
- Date: 2026-08-08
- Registry: PASS; 6 sources, 1 quality policy, 4 validated sources, 0 unresolved sources, 1 unresolved settlement source.
- Regression: 46 passed in 1.34 seconds.
- Safety: no credentials or execution.

### ENG-016 — Source registry and settlement-validation Git closeout
- Date: 2026-08-08
- Commit: `9805f8f` — `Complete source registry and settlement validation`
- Result: synchronized clean `main`.
- Interpretation: remaining settlement uncertainty is explicit and intentional.

### ENG-017 — Safe Git closeout automation candidate
- Date: 2026-08-08
- Result: 73 tests passed in isolated validation.
- Scope: exact changed-file verification, blocked paths, secret scan, validators/tests, receipt generation, branch synchronization, and helper self-modification prohibition.

### ENG-018 — Safe Git closeout automation canonical Windows acceptance
- Date: 2026-08-08
- Regression: 73 passed in 5.24 seconds.
- Registry: PASS.
- Commit: `7fa2121` — `Add safe Git checkpoint closeout automation`
- Result: clean synchronized `main`.

### ENG-019 — GitHub live-read continuity verification
- Date: 2026-08-08
- Result: private GitHub `main` successfully served current handoff files.
- Decision carried forward: live GitHub reads; local safe-helper writes.

### ENG-020 — Settled-market evidence and rule-consistency canonical validation
- Date: 2026-08-08 local / 2026-08-09 UTC artifacts
- Environment: user's canonical Windows repository, Python 3.11.
- Final regression before closeout: 87 tests.
- Accepted run: `collect_settled_market_evidence_20260809T012935685909Z_3f32c571`.
- Tickers:
  - `KXBTC15M-26AUG082115-15`
  - `KXBTC15M-26AUG082100-00`
  - `KXBTC15M-26AUG082045-45`
  - `KXBTC15M-26AUG082030-30`
  - `KXBTC15M-26AUG082015-15`
- All five: `status=finalized`, `result=yes`, populated `settlement_ts`, `expiration_value`, and `settlement_value_dollars`.
- Observed `expiration_value`: `64930.83`, `64923.68`, `64919.28`, `64915.79`, `64911.32`.
- Independent validation:
  - artifact integrity and raw-to-derived evidence PASS;
  - primary and secondary rule consistency true;
  - settlement-value fields present 5/5;
  - market field-set consistency true;
  - evidence consistency PASS.
- Public-field conclusion: the public settled object does not expose separately named opening and closing BRTI average operands.
- Closeout: `docs/LAST_CHECKPOINT_CLOSEOUT.json` records substantive commit `ac6020ce350d343df057676a8aeafcac834c5869`, source-registry PASS, and 87 tests passed in 7.43 seconds.
- Strategy conclusion: none.

### ENG-021 — Settlement edge-case and reference-data design review

- Date: 2026-08-08 local Pacific / 2026-08-09 UTC source review
- Scope: official-source review of unresolved KXBTC15M edge cases; separation of provider-index behavior from Kalshi settlement behavior; reference-data architecture; canonical regression.
- Repository baseline: checkpoint-05 closeout receipt on GitHub `main`, substantive commit `ac6020ce350d343df057676a8aeafcac834c5869`.
- Runtime/code change: none.
- Source-registry/config change: none.
- New documents:
  - `docs/SETTLEMENT_EDGE_CASES.md`
  - `docs/REFERENCE_DATA_DESIGN.md`

#### Provider-level findings

- Current reviewed BRTI methodology documents an effective calculation capability of 200 milliseconds.
- Current BRTI retrieval-lag threshold is 10 seconds for constituent order-book freshness.
- Delayed/unusable constituent data can be excluded under the methodology.
- If the real-time index cannot be calculated for a calculation time, the provider does not publish an index value for that calculation time.
- Provider value documentation allows exceptional delayed publication and amendments and exposes amendment metadata.

Interpretation: these findings resolve provider/index behavior only. They do not establish how Kalshi forms a KXBTC15M operand when an expected observation is absent, late, or amended.

#### Kalshi relay findings

- `cfbenchmarks_value` remains documented authenticated delivery, not collected.
- Roughly one-second relay cadence is distinct from provider calculation capability.
- The quarter-hour final-minute accumulator covers `(close - 60s, close]`, start excluded and close included.
- Duplicate/out-of-order upstream timestamps are documented as ignored.
- The generic trailing `avg_60s_data` current-tick fallback must not be inferred to apply to the separate final-minute settlement accumulator.

#### Remaining unresolved settlement cases

- exact averaging/rounding/comparison order;
- identical versus asymmetric operand rounding;
- missing provider observations within a required window;
- late observation inclusion;
- amendment/correction cutoff and settlement revision behavior;
- fewer-than-expected observation handling;
- official outage/fallback procedure;
- exact settlement-engine equivalence of convenience averages;
- authenticated reconnect/replay continuity for future collection.

Decision: keep all unresolved cases fail-closed; do not impute settlement truth.

#### Reference-data design conclusion

No auxiliary source was selected.

Future source selection must precede implementation with a scorecard covering:

- role/authority;
- raw preservation;
- source/relay/local UTC/local monotonic timestamps;
- sequence, gap, duplicate, reconnect, and replay semantics;
- freshness thresholds;
- correction/amendment handling;
- missing-data policy;
- schema drift;
- access/licensing.

Auxiliary feeds remain predictive/reference sources only.

#### Canonical Windows validation

Source registry:

```text
Source registry: configs\source_registry.json
Schema: source_registry.v1
Registry ID: event_market_quant_bot.sources
Sources: 6
Quality policies: 1
Validated sources: 4
Unresolved sources: 0
Unresolved settlement sources: 1
Validation: PASS
```

Full regression:

```text
....................................................................................... [100%]
87 passed in 5.13s
```

- Safety result: no credentials, authenticated source access, external collector, settlement-label generation, orders, demo execution, or real funds.
- Strategy conclusion: none; this checkpoint is source/architecture research, not evidence of predictive edge or profitability.
- Decision: accept checkpoint 06 for safe Git closeout while keeping exact settlement replication blocked.
- Follow-up: checkpoint 07 — Reference Feed Selection and Time Alignment.

### ENG-022 — Opportunity-census live granularity and pagination validation

- Date: 2026-08-08 local Pacific / 2026-08-09 UTC artifacts.
- Scope: first live read-only neutral opportunity-census attempts; Kalshi rate-limit handling; market-versus-event discovery granularity.
- Deterministic gate before the final live retry: 112 tests passed plus 3 subtests in the user's canonical Windows Python 3.11 environment.
- Safety: public unauthenticated GET requests only; raw-first preservation; zero orders; no credentials; ranking disabled.

#### Live observations

1. Initial broad Kalshi discovery returned HTTP 429. The collector failed closed. The HTTP layer was corrected to preserve every 429 raw record and use bounded exponential backoff, and Kalshi market pages were increased to the documented 1000-result maximum.
2. Broad contract-level discovery then reached 50 full pages / 50,000 rows and still received a next cursor. The collector correctly rejected the partial universe.
3. Adding `mve_filter=exclude` did not materially reduce the contract count: the next live attempt again returned 50 full pages / 50,000 rows with a continuation cursor.
4. Raw-archive inspection confirmed every request carried `status=open`, `limit=1000`, and `mve_filter=exclude`.
5. Python inspection of the preserved run confirmed:
   - 50 successful pages;
   - 50,000 total rows;
   - 50,000 unique market tickers;
   - 5,935 unique event tickers within those first 50,000 markets;
   - 50 unique response cursors and 49 unique request cursors, exactly consistent with advancing cursor pagination from an initial cursorless request;
   - all 50 pages contained 1,000 rows;
   - several single events exposed hundreds of separate contracts, including multiple 400-contract NASDAQ-100 events.

#### Interpretation

- The Kalshi pagination mechanism was functioning; the 50-page guard was not failing because of a repeated cursor.
- Excluding MVE/combo markets does not solve the baseline-comparability problem because ordinary events can still fan out into hundreds of binary strike/line contracts.
- Raw contract count is therefore not a neutral proxy for independent opportunity count and would systematically overweight venues/products that generate many line variants.
- Official Kalshi terminology independently aligns with this result: `Event` is the basic interaction unit and `Market` is a low-level binary object; `Series` is the recurring template above events.

#### Decision

Adopt event-first baseline discovery across public census venues. Emit one normalized opportunity row per source event, retain series/category identifiers, and treat contract count as metadata. Defer contract-level quotes/depth to a second-stage snapshot only after an event/series/strategy candidate survives census screening. See D-023.

- Strategy conclusion: none. This validates census architecture only and does not establish market edge or profitability.
- Follow-up: register the event-discovery endpoints required by the event-first adapters, run deterministic validation, then perform a bounded event-first live census.

### ENG-023 — Universal event+contract census validation and strategy-class screening

- Date: 2026-08-08 local Pacific / 2026-08-09 UTC artifacts.
- Scope: final checkpoint-07 public multi-venue census, nested contract snapshot validation, current-tradability diagnostics, and first historical research-target selection.
- Safety: public unauthenticated read-only collection only; no credentials; no orders; no demo or production execution.

#### Deterministic validation

After the final contract-snapshot extension, the user's canonical Windows environment reported:

```text
117 passed, 5 subtests
```

#### Accepted live census

Run ID:

`collect_opportunity_census_20260809T042743550002Z_4ba09728`

Collector output:

```text
Opportunity census event rows: 12198
Opportunity census contract snapshot rows: 107293
  crypto_com_predictions: 442 events, 7460 contracts from 10 pages
  gemini_predictions: 502 events, 4549 contracts from 2 pages
  kalshi: 9146 events, 78204 contracts from 46 pages
  polymarket_us: 2108 events, 17080 contracts from 43 pages
```

Independent manifest validation:

```text
Status: completed
Raw files: 4
Raw records: 101
Raw error records: 0
Derived CSV files: 2
Derived rows: 119491
Runtime event files: 1
Runtime events: 111
Runtime error events: 0
Validation: PASS
```

The derived row total reconciled exactly: `12,198 + 107,293 = 119,491`.

Additional diagnostics:

- 107,293 unique contract composite keys;
- 0 duplicate contract rows;
- 0 orphan contract rows;
- all 12,198 events with contract-count metadata checked;
- 0 contract-count mismatches;
- 0 crossed bid/ask pairs among source fields treated as genuine bid/ask.

#### Source-field correction

Kalshi's official API changelog marks Market `liquidity` / `liquidity_dollars` deprecated and returning zero on affected Market/Event responses. The observed all-zero `liquidity_source` field is therefore not evidence of zero real market liquidity and must not be used as an activity gate. The source value remains preserved for audit.

#### Current-tradability screen

A deeper Kalshi diagnostic used current source fields that were available in the same nested event crawl:

```text
YES midpoint in [0.10, 0.90]
volume_24h > 0
best YES bid size > 0
best YES ask size > 0
```

At the 1–7 day horizon:

| Category | Contracts | Unique events | <=2c spread | Median spread | Median 24h volume | Median bid size | Median ask size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Crypto | 38 | 9 | 55.3% | 0.0200 | 1386.185 | 444.50 | 943.925 |
| Climate and Weather | 117 | 42 | 74.4% | 0.0100 | 811.15 | 9.00 | 13.72 |
| Commodities | 130 | 12 | 81.5% | 0.0100 | 128.435 | 205.50 | 145.00 |
| Sports | 2144 | 1077 | 69.0% | 0.0200 | 59.535 | 300.00 | 568.50 |

#### Research decision

Select **Kalshi Sports, 1–7 days to close, calibration / behavioral structure** as the first historical strategy-research class because it provides by far the largest independent-event sample while retaining measurable two-sided market quality.

This is not a profitability result and does not establish Kalshi as the globally best venue. Crypto, Climate & Weather, and Commodities remain secondary research candidates for strategy families better matched to their information structure.

- Strategy experiment completed: none.
- Follow-up: close checkpoint 07, then implement the predeclared historical Sports calibration dataset/experiment described in `docs/SPORTS_CALIBRATION_EXPERIMENT.md`.

### ENG-024 — Kalshi Sports historical-data path and outcome-blind freshness validation

- Date: 2026-08-08 local Pacific / 2026-08-09 UTC artifacts.
- Scope: public historical/live endpoint validation, source registration, raw-first Sports historical collector, manifest reconciliation, and outcome-blind quote-age/missingness gate.
- Safety: public unauthenticated read-only access only; no credentials; no orders; no paper/demo/production execution; outcomes kept unmaterialized for the staleness decision.

#### Endpoint and registry validation

Representative endpoint validation completed with:

```text
Historical Sports market: KXITFMATCH-26JUN08LEGBRA-LEG
Historical 1m candles: 59 (59 complete bid/ask pairs)
Historical trades: 47
Live Sports market: KXWC-30-MEX
Live 1m candles: 7 (7 complete bid/ask pairs)
Raw records: 10
Raw errors: 0
```

The source registry was migrated and independently validated at:

```text
Sources: 18
Quality policies: 1
Validated sources: 12
Unresolved sources: 0
Unresolved settlement sources: 1
Validation: PASS
```

#### Collector validation

A 3-event smoke run and a 25-event pilot run both completed and passed independent manifest reconciliation.

The final accepted outcome-blind collection was:

`collect_sports_historical_20260809T060907842728Z_94ad3820`

```text
Sports events: 100
Markets: 1200
Anchor rows: 3600
Real 1m candle rows: 288210
Anchors with any bid/ask pair: 2646
Anchors with no bid/ask pair: 954
Cross-tier list observations: 84
Canonical recovery fetches: 0
Unclassifiable settled events skipped: 1
```

Independent reconciliation:

```text
Event rows: 100
Market rows: 1200
Anchor rows: 3600
Candle rows: 288210
Raw records indexed: 4718
Outcomes materialized: no
Validation: PASS
```

Two source behaviors were learned and handled fail-closed: some old markets appeared on the live list despite cutoff timing, and one settled Event had a blank category. The collector preserves these observations raw, derives only from cutoff-canonical market evidence, and never infers Sports membership from a blank category.

#### Outcome-blind staleness result

The predeclared candidates were `1m`, `5m`, `15m`, `30m`, and `1h`.

The 100-event pilot reported:

```text
Quote availability: 73.500%
Quote-age p50/p75/p90/p95/max seconds:
1588 / 10403 / 50183 / 70192 / 86238

7d: 704/1200 = 58.667%; p90 age=31922s
3d: 986/1200 = 82.167%; p90 age=56893s
1d: 956/1200 = 79.667%; p90 age=50183s

Pilot status:
blocked_no_freshness_candidate_meets_retention_gates

Candidate threshold: none
Threshold eligible to freeze: no
```

- Engineering conclusion: the current fixed-anchor historical reconstruction fails its predeclared freshness/retention gate.
- Strategy conclusion: none; outcomes were not opened and calibration was not run.
- Profitability conclusion: none.
- Latest full user-side regression before final documentation closeout: `166 passed, 23 subtests`.

### EXP-001 — Kalshi Sports 1–7d calibration / behavioral structure

- Date: 2026-08-08 local Pacific / 2026-08-09 UTC.
- Status: **BLOCKED BEFORE OUTCOME ANALYSIS**.
- Hypothesis: quoted Kalshi Sports YES probabilities at fixed 7d/3d/1d pre-close anchors may exhibit systematic calibration error that is stable in chronological holdout after accounting for within-event dependence.
- Data period: historical settled Sports events available through the public Kalshi historical/live data tiers in the accepted Checkpoint-08 collection; this log does not infer a broader period beyond the source records.
- Markets: 100 unique Sports events, 1,200 finalized binary markets, 3,600 fixed anchor observations in the accepted data-quality sample.
- Method: raw-first collection; exact event/market/anchor/candle lineage; real one-minute bid/ask candles only; no lookahead; outcome-blind quote-age/missingness gate before materializing final outcomes.
- Costs and execution assumptions: not reached. No executable-price, fee, depth, latency, fill, or profitability analysis was performed because the data-quality gate failed first.
- Metrics reached: quote availability, quote-age quantiles, horizon-specific availability, and predeclared staleness-candidate retention.
- Result: no maximum quote-age candidate at or below one hour satisfied the predeclared >=90% overall / >=80% per-horizon retention rule in the required 100-event sample. No staleness threshold was frozen. Final YES/NO outcomes were not opened by the pilot, and calibration error/ECE/Brier/holdout analysis was not run.
- Limitations: the result establishes failure of this specific historical reconstruction rule, not failure of Sports calibration research in general. A different observation definition may be studied only as a new predeclared experiment. The result does not establish calibration, miscalibration, market efficiency, or profitability.
- Decision: block the current experiment before outcome analysis under D-027.
- Follow-up: safely close Checkpoint 08, then reassess historical feasibility and strategy branches before selecting another outcome-analysis path.

### ENG-025 — Checkpoint-09 exact-time historical feasibility collection and validation

- Date: 2026-08-09 local Pacific / 2026-08-09 UTC artifacts.
- Scope: outcome-blind historical quote feasibility across Sports, Crypto, Climate and Weather, and Commodities using real one-minute source candles at exact candle-end `time_to_close_seconds`.
- Engineering findings: the initial six-day one-minute request for `KXNFLRETIRE-RWILSON3-2728` failed HTTP 400 with source detail `requested time range with candlesticks: 8640.000000, max candlesticks: 5000`. The collector was corrected to deterministic non-overlapping <=24-hour transport chunks. A separate smoke-run logic defect that allowed the CLI sample size to lower the 25-event qualification gate was also corrected; smoke runs thereafter reported `insufficient_event_sample`.
- Accepted run: `collect_historical_feasibility_20260809T072159989703Z_6ae075ee`.
- Result: 100 events, 161 markets, 966 request chunks, 46,972 real one-minute observations, 46,972 valid uncrossed quote observations, 1,473 indexed raw records, manifest validation PASS.
- Category feasibility: Sports 96% event quote coverage PASS with concentration warning; Crypto 96% PASS with concentration warning; Climate and Weather 32% FAIL; Commodities 4% FAIL.
- Safety: public unauthenticated collection only; outcomes unmaterialized; no calibration/model analysis; zero orders.
- Interpretation: Sports and Crypto have sufficient public historical quote support for further outcome-blind design work. Weather and Commodities are blocked only under this historical quote path.

### ENG-026 — Sports V2 exact-time scalability, heterogeneity, and subgroup-support validation

- Date: 2026-08-09 local Pacific / 2026-08-09 UTC artifacts.
- Scope: pre-outcome Sports scalability at 100 events, hierarchical dependence design, outcome-blind sport/product profiling, and frozen subgroup support gates.
- Accepted run: `collect_sports_v2_scalability_20260809T074813046311Z_68eb260c`.
- Independent validation: PASS.
- Result: 100 events, 169 markets, 1,014 request chunks, 52,331 real/valid quote observations, 1,532 raw records; event quote coverage 97.0%; market quote coverage 96.4497%; early/middle/late event coverage 79%/87%/90%; dominant series event share 10%; largest-event observation share 9.5488%; top-decile observation share 52.2138%; status `scalability_gate_pass`.
- Heterogeneity: 66/100 high-confidence sport classification; 59/100 high-confidence product-family classification.
- Frozen eligible robustness strata: MLB, NFL, NBA; product family `coach_or_manager_status`; no eligible sport x product-family cell.
- Safety: outcomes unmaterialized; no calibration/model analysis; zero orders.
- Interpretation: the Sports exact-time data path scales, but broad Sports is not treated as one homogeneous predictive population. The predeclared Sports V2 calibration remains deferred before outcomes.

### ENG-027 — Crypto outcome-blind heterogeneity and subgroup-support validation

- Date: 2026-08-09 local Pacific / 2026-08-09 UTC artifacts.
- Source run: `collect_historical_feasibility_20260809T072159989703Z_6ae075ee` filtered to the 25 Crypto events.
- Heterogeneity result: 21/25 (84%) high-confidence asset/driver classification and 23/25 (92%) high-confidence template classification.
- Composition: 13 ProjectOrTokenSpecific events, including 12 `fdv_family`; plus BTC, ETH, BNB, ZEC, launch/deployment, relative/ATH, and other structures.
- Frozen subgroup-eligibility result: `ProjectOrTokenSpecific` eligible as an asset/driver robustness stratum; no general template family eligible; `ProjectOrTokenSpecific | fdv_family` eligible as a specific cross-stratum with 12 events, 100% quote coverage, and 91.667% all-three-band event coverage.
- Safety: outcomes unmaterialized; no calibration/model analysis; no strategy edge conclusion; zero orders.
- Interpretation: broad Crypto is heterogeneous but more cleanly classifiable in this pilot. The 12-event FDV cell is a qualified research subgroup, not evidence of predictive edge or profitability.

### EXP-002 — Checkpoint-09 historical feasibility and strategy-branch reassessment

- Date: 2026-08-09 local Pacific / 2026-08-09 UTC.
- Status: **COMPLETED OUTCOME-BLIND; NO STRATEGY OUTCOME ANALYSIS**.
- Hypothesis: before opening outcomes, public historical quote data and the candidate's dependence structure can identify which research populations are scientifically supportable without post-hoc relaxation.
- Data period: historical settled Kalshi events accessible through the validated public historical/live tiers in the Checkpoint-09 runs; no broader time period is inferred beyond preserved source records.
- Markets: 25 events/category across Sports, Crypto, Climate and Weather, and Commodities for the common feasibility screen; a separate validated 100-event Sports scalability sample.
- Method: real one-minute source candlesticks at actual timestamps; exact `time_to_close_seconds`; deterministic market selection; raw-first lineage; <=24-hour transport chunking; frozen quote-coverage gates; outcome-blind concentration/heterogeneity/subgroup diagnostics.
- Costs and execution assumptions: not reached. No fee, depth, latency, fill, or executable-return analysis was performed.
- Result: Sports and Crypto passed the historical quote-feasibility layer. Weather and Commodities failed this layer. Sports scaled to 100 events but remained heterogeneous; Crypto produced one eligible 12-event project/token FDV cross-stratum. No final outcome, calibration, prediction, or profitability metric was computed.
- Methodological result: nominal Kalshi event count is not a universal cross-domain sample-size metric; every future strategy must define its own dependence/evaluation cluster. Raw candle rows and correlated contracts are not independent trials.
- Decision: stop the broad branch tournament before outcomes. Preserve Sports V2 and project/token FDV as qualified secondary branches. Begin Checkpoint 10 with BTC-specific historical research design because of its coherent common underlying process, while explicitly clustering correlated contracts/settlement periods. No external reference feed is selected yet.
- Limitations: this experiment establishes data and research-design feasibility only. It does not establish market efficiency, mispricing, calibration error, model accuracy, expected value, or profitability.
- Follow-up: safely close Checkpoint 09, then begin `10 - BTC-Specific Historical Research Design` from current GitHub `main` and the new closeout receipt.

### EXP-003 — Checkpoint-10 BTC settlement-structure and quote-feasibility study

- Date: 2026-08-09 local Pacific / 2026-08-09 UTC.
- Status: **COMPLETED; OUTCOME-BLIND THROUGH FAMILY SELECTION**.
- Hypothesis: before opening strategy outcomes, BTC market families can be compared on validated settlement/dependence semantics and real historical quote support without using contract count as independent sample size.
- Inventory run: `collect_btc_research_unit_inventory_20260809T100753813114Z_5d03b78e`.
- Inventory result: 64 BTC Series, 44,958 settled BTC events discovered, 136 outcome-blind structure-sampled events, 5,670 sampled markets, 262 settlement clusters.
- Rule-regime result: sampled KXBTC contained 300-second trimmed, 60-second trimmed, and 60-second simple-mean regimes; sampled KXBTCD contained 60-second trimmed and 60-second simple-mean regimes.
- All-market semantic result: 2,393 KXBTC contracts -> 25 resolved sampled primitives; 2,915 KXBTCD contracts -> 25 resolved sampled primitives; zero sampled shared primitive groups.
- Quote-feasibility run: `collect_btc_family_quote_feasibility_20260809T114516450822Z_a232d26c`.
- Quote result: 60 clusters, 140 probe markets, 9,648 real one-minute observations, all 9,648 valid uncrossed quote observations.
- Family result: KXBTC15M base pass; KXBTC base pass but 45% ladder breadth failed frozen 50%; KXBTCD base pass plus 75% ladder breadth.
- Disposition: select modern `brti_60s_simple_mean_untrimmed` KXBTCD for the first structural baseline; retain KXBTC15M as a qualified secondary benchmark; do not relax KXBTC gate.
- Safety: no outcomes used for family selection; no authentication, external predictive feed, execution, or orders.
- Profitability conclusion: none.

### EXP-004 — KXBTCD three-probe monotone baseline v1

- Date: 2026-08-09 local Pacific / 2026-08-09 UTC.
- Status: **COMPLETED; UNTOUCHED HOLDOUT DOES NOT SUPPORT INCREMENTAL PREDICTIVE IMPROVEMENT**.
- Experiment ID: `kxbtcd_three_probe_monotone_baseline.v1`.
- Design fingerprint: `bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4`.
- Hypothesis: enforcing the logically required nonincreasing threshold-probability structure with a simple PAVA projection may improve cluster-weighted predictive log loss relative to raw same-time KXBTCD quote midpoints.
- Pre-outcome sample: 20 modern-regime KXBTCD settlement clusters; three structural probes; exact same-minute q25/q50/q75 quote synchronization across normalized early/middle/late bands.
- Frozen synchronization gate: >=50% clusters; observed 12/20 = 60%.
- Frozen split: eight chronological development clusters and four untouched holdout clusters with zero settlement-primitive overlap.
- Primary metric: cluster-weighted log loss. Secondary: Brier and structural monotonicity/adjustment diagnostics.
- Development exposure: 24 labels / 72 predictions. A post-request metadata-join failure was recovered offline from exact preserved raw records with zero repeat API requests and zero holdout exposure.
- Development result: raw log loss `0.1229517749838280758888888889`; monotone `0.1226068974322313537500000000`; raw-minus-monotone delta `0.0003448775515967221388888889`; raw monotonicity violation rate 37.5%; mean absolute adjustment about 0.00965.
- Untouched holdout run: `collect_kxbtcd_holdout_outcomes_20260809T121952744398Z_ec29a2ab`.
- Holdout result: four clusters / 12 labels / 36 predictions; raw log loss = monotone log loss = `0.03832137791396992041666666668`; raw Brier = monotone Brier = `0.01129722222222222222222222222`; both deltas exactly zero; monotonicity violation rate zero; no PAVA adjustments.
- Interpretation: the tiny favorable development result did not replicate out of sample. v1 does not provide evidence that monotone post-processing adds predictive value beyond raw midpoints.
- Limitations: very small pilot, three probes rather than a full distribution, quote midpoints rather than executable fills, no fees/depth/latency/adverse-selection model, no external predictive information, no statistical-significance or profitability claim.
- Follow-up rule: do not tune v1 against the opened holdout. Any follow-on experiment requires a new design version and new untouched evaluation set.

### EXP-005 — KXBTC15M causal-native H3 development and sealed-holdout program

- Date: 2026-08-11 through 2026-08-13 America/Chicago / closeout prepared 2026-08-14 UTC.
- Status: **COMPLETED; SEALED HOLDOUT NOT SUPPORTED; ALL 122 MARKETS OPENED**.
- Hypothesis: a high-probability favored-side KXBTC15M entry can earn executable short-horizon profit when timing, band, native observation frequency, latency, fees, depth, protected targets, and fallback exits are modeled causally.
- Data period: 122 locally archived chronological KXBTC15M markets; 96 used for adaptive development and 26 reserved once as a sealed holdout. Exact source periods remain in the preserved local raw/manifests rather than being inferred by this log.
- Frozen confirmatory rule: first causal native favored midpoint from 90% to below 98% during four to five minutes remaining; one-second delayed unprotected full-depth entry; `$100` maximum deployment with fees; protected 50%-of-maximum-profit full exit; ten-second preclose fallback.
- Development result: 57 fills on 96 eligible markets; `$2.32` mean P&L per market; `$3.90` per fill; 100% profitable and target-filled; zero full-capital losses; worst `$1.10`. This was adaptive evidence after multiple diagnostics.
- Holdout experiment: `kxbtc15m_h3_native_4_5m_protected50_holdout.v1`; design fingerprint `4b3edf6f39be338f4fd6149cdea3de4ce54a7410aa1a105a187c6619d82d7aff`.
- Holdout result: 14 fills on 26 markets; `-$46.55` total; `-$1.79` mean per market; 95% bootstrap interval `-$10.16` to `$2.83`; one `-$99.83` full-capital loss; decision `NOT_SUPPORTED`.
- Known loss: `KXBTC15M-26AUG121945-45`, 104 YES contracts at `$0.957`, no target signal, preclose liquidity failure, losing settlement, `-$99.828` P&L.
- Adaptive follow-up: the full-five-minute policy introduced three full losses; early-persistence gates all failed; fixed and conditional stops destroyed more winner recovery than they saved; runner and bounded re-entry did not materially improve the policy; no robust velocity/acceleration candidate passed.
- Partial-timeout frontier: 90-second 25%/50%/75%/100% sales changed combined opened-data P&L by `+$2.71`, `+$0.67`, `-$3.93`, and `-$8.82`, respectively. Every combined paired interval crossed zero. All policies cost money in the original 96 and both chronological development diagnostics.
- Costs and execution assumptions: archived full depth; conservative fees; one-second signal-to-execution delay; progressive liquidation where applicable; no optimistic partial fill; no external BTC data; no authentication or orders.
- Limitations: extensive adaptive multiple comparisons; only one observed baseline loser; opened holdout unavailable for confirmation; native snapshots are correlated repeated states; results cannot estimate stable future loss frequency or unbiased expected return.
- Decision: close H3 under D-037. Do not promote any overlay and do not reuse any of the 122 markets as a new holdout. Return the primary branch to KXBTCD model readiness under D-038.
- Follow-up: publish the branch through the safe closeout workflow, then start Checkpoint 11 with a new KXBTCD target/feature design and chronological outcome firewall.
- Full report: `docs/KXBTC15M_H3_RESEARCH_CLOSEOUT.md`.

## Experiment template

### EXP-XXX — Title

- Date:
- Hypothesis:
- Data period:
- Markets:
- Method:
- Costs and execution assumptions:
- Metrics:
- Result:
- Limitations:
- Decision:
- Follow-up:

<!-- PRESELECTION_EXPERIMENT_LOG_20260814 -->
## 2026-08-14 - KXBTCD vs. KXBTCPERP preselection audit

### Question

Before committing the next BTC research phase, should the project focus on KXBTCD, Kalshi BTC perpetuals, or a shared architecture?

### Method

Read-only only. No order, cancellation, transfer, demo execution, paper broker, or real-money endpoint was used.

Evidence stages:

1. authenticated read-only KXBTCPERP capability probe;
2. bounded perp history/book/fee/funding audit;
3. KXBTCD full-ladder and open-horizon liquidity audits;
4. 120-second paired same-window capture with KXBTCD, KXBTCPERP, BRTI, Coinbase, and Kraken;
5. offline cadence/regime/effective-sample diagnostics.

The predeclared KXBTCD monotone v1 holdout experiment was not tuned or rerun.

### Key results

KXBTCD:
- at least 4,000 unique settled events in saved bounded pages;
- 172 UTC day blocks / 25 week blocks across about 171 days;
- 99.3748% exact one-hour adjacent-event cadence;
- live liquidity concentrated into economically relevant strikes as time-to-close shrinks;
- same-window selected strikes remained two-sided in 60/60 cycles.

KXBTCPERP:
- 71 daily candles / 71 day units;
- 1,322 minute candles in the 24-hour bounded sample;
- 214 historical funding observations with 213/213 exact eight-hour gaps;
- one-minute squared returns exhibited more serial dependence than raw returns;
- same-window book remained two-sided in 60/60 cycles;
- median spread 0.3157 bp, p95 0.4736 bp.

Timing:
- paired REST order was balanced 30/30;
- median request-start skew was 391 ms;
- BRTI had 120 ticks and zero sequence gaps;
- local Windows wall clock was about 170 ms behind `time.windows.com`, so sub-second cross-feed causality remains blocked.

### Result

**Accepted: shared BTC-state layer with separate product heads.**

KXBTCD is the first modeling/validation head. KXBTCPERP remains a secondary read-only model/microstructure head. No joint multitask model is approved yet.

### Limits

- The 4,000 KXBTCD count is a lower bound and not an IID effective sample size.
- The perp ESS calculation is a bounded diagnostic from one day of minute candles, not a universal ESS estimate.
- The paired live capture lasted two minutes; it establishes feasibility and relative microstructure in one synchronized window, not all-regime execution behavior.
- Current wall-clock synchronization is inadequate for sub-second lead/lag claims.
- Profitability remains unproven.

### ENG-028 — KXBTCD pre-outcome materialization v3

- Date: 2026-08-15
- Status: accepted
- Run: collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d
- Selected events: 296
- Structural markets: 1,480
- Attempted states: 8,880
- Available states: 6,378 (71.82%)
- Dataset events: 295
- Train: 175 events / 4,645 rows
- Validation: 56 events / 719 rows
- Locked test: 64 events / 1,014 rows
- Result: the 55m-to-30m anchor grid materially improved usable pre-outcome coverage versus the superseded long-horizon grid while preserving the frozen 60-second staleness rule.
- Locked-test outcome labels opened: 0
- Split fingerprint: 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
- Dataset fingerprint: d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a
- No model fitting, execution, paper trading, or order placement occurred.

<!-- CHECKPOINT13_EXPERIMENT_20260815 -->
### EXP-001 — KXBTCD Candidate-B train/validation evaluation

- Date: 2026-08-15
- Status: completed — validation gate **FAIL**
- Model: `kxbtcd_market_context_logistic.v1`
- Run: `collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631`
- Frozen pre-outcome run: `collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d`
- Dataset fingerprint: `d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a`
- Split fingerprint: `28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503`
- Candidate-B specification fingerprint: `e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3`

#### Engineering gate before labels

The canonical Windows repository passed:

```text
631 passed, 22 subtests passed in 16.10s
```

The zero-network preflight then passed with:

```text
train market requests planned = 822
validation market requests planned = 228
locked-test market requests planned = 0
locked-test deny-list markets = 320
prior CP13 exposure manifests = 0
network requests made = 0
locked-test outcomes opened = 0
```

Before that final gate, two implementation defects were detected without opening labels: a too-strict Newton gradient tolerance on a synthetic regularization test, and incorrect handling of structured manifest path descriptors. Both were fixed and regression-tested before outcome collection.

#### Outcome exposure

```text
train/validation market labels = 1050
new HTTP requests = 1050
recovered prior outcomes = 0
authentication used = no
orders placed = 0
```

Every request was limited to the predeclared train/validation allow-list. Locked-test outcomes remained sealed.

#### Raw-midpoint benchmark

```text
validation event-weighted log loss = 0.14231643239449182
validation event-weighted Brier = 0.04007408198822001
```

#### Candidate-B lambda results

| lambda | train event-weighted log loss | validation event-weighted log loss | raw - candidate validation log loss | validation Brier | raw - candidate validation Brier | selected |
|---:|---:|---:|---:|---:|---:|:---:|
| 0.01 | 0.097722256260416168 | 0.20069619446600914 | -0.058379762071517322 | 0.04150269119776246 | -0.0014286092095424502 | no |
| 0.1 | 0.14432974690271924 | 0.14556019289436192 | -0.003243760499870102 | 0.040404125365432336 | -0.00033004337721232596 | yes |
| 1 | 0.3026909148854055 | 0.19863291694477292 | -0.056316484550281098 | 0.048076601719423288 | -0.0080025197312032781 | no |
| 10 | 0.57003399865276405 | 0.50457707592618672 | -0.3622606435316949 | 0.15774281591527359 | -0.11766873392705357 | no |

Selected coefficients at `lambda=0.1`:

```text
beta0 = 0.094997254017608834
beta1_market_logit = 1.1149509916339024
beta2_strike_log_ratio = -0.060557892307059664
beta3_time_log1p_hours = -0.001891300947166137
iterations = 6
converged = true
train objective = 0.20666907435698761
train event-weighted log loss = 0.14432974690271924
train event-weighted Brier = 0.033560200054487024
```

#### Gate decision

The frozen primary gate required:

```text
Candidate-B validation event-weighted log loss
<
raw-midpoint validation event-weighted log loss
```

Observed:

```text
0.14556019289436192 > 0.14231643239449182
```

Result: **FAIL**.

The Brier score also worsened slightly, but that secondary metric was not needed to decide the gate.

#### Interpretation

- `lambda=0.01` produced a much lower training loss but a materially worse validation loss, consistent with overfitting within this fixed candidate family.
- `lambda=1` and `lambda=10` were progressively more regularized and also materially worse than the raw benchmark on validation.
- The selected `lambda=0.1` model was the best of the four Candidate-B settings on validation, but it still did not improve on the raw market midpoint.
- The fitted model was dominated by the market-logit term; strike and time coefficients were comparatively small. This is diagnostic only and must not be used to post-hoc retune Candidate B on the exposed validation set.

#### Safety/result boundary

- Locked-test outcomes opened: **0**.
- Locked-test final refit performed: no.
- Candidate C authorized: no.
- No execution, paper broker, demo trading, or real-money trading occurred.
- This experiment does not establish profitability or executable trading edge.

<!-- CHECKPOINT14_EXPERIMENT_20260815 -->
### EXP-002 â€” Candidate-B failure/regime diagnostic and Candidate-C v2 predeclaration

- Date: 2026-08-15
- Status: completed â€” diagnostic/design checkpoint; **no Candidate-C fit**
- Source model: `kxbtcd_market_context_logistic.v1`
- Source run: `collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631`
- Frozen pre-outcome run: `collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d`
- Final diagnostic directory: `data/analysis/kxbtcd_candidate_b_failure_analysis/20260815T214404Z`
- Dataset fingerprint: `d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a`
- Split fingerprint: `28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503`
- Candidate-B fingerprint: `e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3`

#### Engineering validation

```text
focused Checkpoint-14 tests = 7 passed in 0.14s
full repository regression = 638 passed, 22 subtests passed in 17.24s
```

A CP14 lineage guard initially rejected `q_market=0.72` versus the CP13 round-trip representation `0.71999999999999997`. Inspection showed the same CP12 state and the analogous strike representation `83749.99` versus `83749.990000000005`. The guard was corrected to require exact equality after both values pass through the same Python binary-float conversion used by CP13, and a regression test was added. This accepts serialization-only differences while still rejecting genuine numeric mismatches.

#### Diagnostic scope

Only the already outcome-exposed train+validation predictions were analyzed:

```text
development events = 231
development rows = 5364
development weeks = 58
network requests = 0
locked-test outcomes opened = 0
Candidate C fit performed = no
execution enabled = no
orders placed = 0
```

Dimensions:

- original partition;
- five chronological week blocks;
- six TTC anchors;
- structural role;
- raw `q_market` bands;
- spread bands;
- `q_market` Ã— spread;
- chronological block Ã— spread.

#### Combined development result

```text
raw log loss = 0.15538587480307692
Candidate-B log loss = 0.14462803684008735
raw - Candidate B = +0.010757837962989569

raw Brier = 0.037913401220456798
Candidate-B Brier = 0.035219333463201045
raw - Candidate B Brier = +0.0026940677572557525

Candidate-B better/worse/tie events = 215/16/0
```

This is exploratory pooled-development evidence and does not reverse EXP-001's validation-gate failure.

#### Key failure/regime findings

- Original validation: log-loss delta `-0.003243760499870102`; Candidate B better/worse events `51/5`.
- Chronology: B0-B3 positive; B4 `-0.006348`.
- TTC: all six anchors positive.
- Spread: `(0,0.01]` negative at `-0.006090`; `>0.05` positive at `+0.021420`.
- B4 Ã— spread:
  - `(0,0.01]`: `-0.007979`;
  - `(0.01,0.02]`: `+0.011286`;
  - `(0.02,0.05]`: `+0.011765`;
  - `>0.05`: `+0.031467`.
- Probability Ã— spread:
  - `q=[0.4,0.5)|spread=(0.02,0.05]`: `-0.032191`;
  - `q=[0.4,0.5)|spread=>0.05`: `-0.022122`;
  - `q=[0.5,0.6)|spread=>0.05`: `+0.043191`;
  - `q=[0.6,0.7)|spread=>0.05`: `+0.051828`;
  - `q=[0.7,0.8)|spread=>0.05`: `+0.052443`.

Interpretation: spread matters, but its effect is conditional on the market's own probability. TTC is not supported as the principal error dimension.

#### Frozen future Candidate C

```text
model = kxbtcd_market_spread_interaction_logistic.v1
contract = kxbtcd_candidate_c_predeclaration.v2
fingerprint = d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322
features = market_logit, spread, market_logit_x_spread
```

No Candidate-C coefficient was fit and no Candidate-C performance result exists yet.

#### Safety/result boundary

- Locked-test outcomes opened: **0**.
- Candidate C fits: **0**.
- Network requests in final diagnostic: **0**.
- No execution, paper broker, demo trading, order placement, cancellation, transfer, or real-money trading occurred.
- This diagnostic does not establish profitability or executable trading edge.

<!-- CHECKPOINT15_EXPERIMENT_20260815 -->
### EXP-003 — Candidate-C rolling-origin development evaluation

- Date: 2026-08-15
- Status: **COMPLETED — DEVELOPMENT GATE PASS; LOCKED TEST SEALED**.
- Candidate: `kxbtcd_market_spread_interaction_logistic.v1`.
- Candidate predeclaration fingerprint: `d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322`.
- Week-map fingerprint: `6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4`.
- Canonical result directory: `data/analysis/kxbtcd_candidate_c_development/20260815T220714Z`.
- Development data: 231 already outcome-exposed events / 5,364 rows / 58 UTC weeks.
- OOF scoring data: 184 events / 4,442 rows across B1-B4.
- Method: outcome-blind chronological week-map freeze; four rolling-origin folds; fit-fold-only population z-scaling; deterministic damped Newton; equal event weighting; frozen L2 grid `0.01, 0.1, 1, 10`; lambda selected by pooled OOF event-weighted log loss.
- Selected lambda: `0.01`.
- Raw pooled OOF log loss: `0.14654989561790596`.
- Candidate-C pooled OOF log loss: `0.076775557277925191`.
- Raw-minus-Candidate-C log-loss delta: `+0.069774338339980771`.
- Raw pooled OOF Brier: `0.035093720284958003`.
- Candidate-C pooled OOF Brier: `0.019029926328616251`.
- Raw-minus-Candidate-C Brier delta: `+0.016063793956341752`.
- Score-block log-loss wins: `4/4`.
- Event-level Candidate-C better/worse/tie signs: `119/65/0`; this sign count is diagnostic and was not the gate metric.
- Gate result: all three predeclared development conditions passed.
- Regularization result: lambda `0.1` OOF log loss `0.16990493205584381`, lambda `1` `0.46448575643664897`, lambda `10` `0.65920459562432876`; all three are worse than raw. No post-result retuning is authorized.
- Validation: focused `9 passed in 0.14s`; full regression `647 passed, 22 subtests passed in 16.15s`; source registry PASS.
- Safety: locked-test outcomes opened 0; locked-test evaluation no; full-development final fit no; network requests 0; orders 0; execution no.
- Interpretation: Candidate C has passed its internal chronological development-selection gate. This is not the terminal test, not an execution backtest, and not evidence of guaranteed or executable profitability.
- Follow-up: Checkpoint 16 freezes full-development scaling and one final fit at `lambda=0.01` while keeping the locked test sealed; Checkpoint 17 is the separately authorized one-time terminal test.

<!-- CHECKPOINT16_EXPERIMENT_20260815 -->
### EXP-004 — Candidate-C full-development freeze and final fit

- Date: 2026-08-15.
- Status: **COMPLETED — FINAL DEVELOPMENT MODEL FROZEN; LOCKED TEST SEALED**.
- Candidate: `kxbtcd_market_spread_interaction_logistic.v1`.
- Candidate predeclaration fingerprint: `d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322`.
- Week-map fingerprint: `6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4`.
- Development data: 231 already outcome-exposed events / 5,364 rows.
- Selected lambda: `0.01`, frozen from Checkpoint 15 with no new search.
- Method: full-development row-level population z-scaling; unchanged equal-event-weighted penalized logistic objective; unchanged deterministic damped Newton; exactly one final fit.
- Frozen scaler means: `0.053181741488340019`, `0.17633482475764356`, `0.006538779033484236`.
- Frozen scaler population stds: `3.2168919026338747`, `0.21442166056343254`, `0.32259958139407791`.
- Full-development freeze fingerprint: `d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3`.
- Frozen coefficients: intercept `0.10194908608881083`; market-logit-z `2.0752015786995628`; spread-z `0.017616475889079299`; market-logit-x-spread-z `1.9669079012140323`.
- Fit convergence: 6 Newton iterations.
- Penalized full-development objective: `0.1226739682345051`.
- Final model fingerprint: `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`.
- Validation: focused `15 passed in 0.73s`; full regression `653 passed, 22 subtests passed in 19.49s`; source registry PASS; final artifact validation PASS.
- Safety: one completed final-fit attempt; locked-test outcomes opened 0; locked-test evaluation no; network requests 0; orders 0; execution no.
- Interpretation: this checkpoint freezes the model required for a future terminal test. It does not provide a new out-of-sample score because the final fit uses the full exposed development pool. The Checkpoint-15 rolling-origin result remains the advancement evidence.
- Follow-up: a separately authorized Checkpoint 17 may open the 64-event locked test once and apply the frozen strict event-weighted log-loss acceptance rule. Once opened, the test becomes exposed and cannot be reused for redesign or another untouched-test claim.

<!-- CHECKPOINT17_PREOUTCOME_FREEZE_20260815 -->
### KXBTCD Candidate-C Checkpoint-17 terminal-procedure freeze

- Date: 2026-08-15.
- Status: **STAGE A COMPLETE — TERMINAL PROCEDURE FROZEN; LOCKED TEST STILL SEALED**.
- Candidate: `kxbtcd_market_spread_interaction_logistic.v1`.
- Full-development preprocessing fingerprint: `d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3`.
- Final model fingerprint: `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`.
- Terminal evaluation procedure fingerprint: `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`.
- The procedure fingerprint binds the exact Stage-B implementation SHA-256 hashes.
- Frozen terminal scope: 64 events / 1,014 rows.
- Exact outcome-blind market request allow-list: 304.
- Primary comparison: Candidate-C vs raw Kalshi midpoint on identical rows.
- Frozen primary metric/rule: event-weighted log loss; Candidate C must be strictly lower; tie fails.
- Frozen secondary metric: event-weighted Brier; cannot override primary rule.
- Procedure derivation used outcomes: no.
- Locked-test feature-density redesign: no.
- Locked-test outcomes opened: 0.
- Network requests: 0.
- Model fit/tune/recalibration: 0.
- Orders/execution: 0 / no.
- Follow-up: close and verify the Stage-A procedure-freeze commit/receipt. Only a clean synchronized Stage-B invocation may open the terminal outcomes.

<!-- CHECKPOINT17_TRANSPORT_AMENDMENT_20260815 -->
## Checkpoint 17 — terminal exposure interruption

- Original terminal-evaluation fingerprint: `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`
- First failed manifest: `data\manifests\2026\08\15\collect_kxbtcd_candidate_c_locked_test_20260815T224506878886Z_31832daa.json`
- Failed manifest SHA-256: `9cbf18cc44933330c8d27ed000aa2c04015f1fb660aca13979ae6ec4253c5627`
- Persisted labels before failure: 9 of 304
- Failure: HTTP 404 on `/historical/markets/KXBTCD-26AUG0202-T55499.99`
- Observed Kalshi `market_settled_ts` cutoff: `2026-06-16T00:00:00Z`
- Label values used to design transport repair: no
- Candidate/model/preprocessing/lambda/optimizer changes: none
- Metric/gate/tie-rule changes: none
- Locked-test membership changes: none
- Transport amendment fingerprint: `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`
- Execution/orders: disabled / 0

The next permitted experiment action is a resume of the same permanently
exposed terminal attempt under the committed transport-only amendment.

<!-- CHECKPOINT17_TERMINAL_RESULT_20260815 -->
## Checkpoint 17 — Candidate-C one-time terminal locked-test evaluation

- Date: 2026-08-15
- Completed run: `collect_kxbtcd_candidate_c_locked_test_20260815T225546640797Z_54081035`
- Terminal result fingerprint: `70bb11f4c32213a5bdd7173c790e082e3c0b2a634e0a4a91e4d4a6a8eaf31cdd`
- Terminal procedure fingerprint: `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`
- Transport amendment fingerprint: `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`
- Model fingerprint: `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`
- Frozen sample: 64 events / 1014 rows /
  304 labels
- Recovered labels from interrupted attempt: 9
- Newly collected labels: 295
- Live market requests: 295
- Historical fallback requests: 103
- Raw midpoint log loss: `0.052191564366640519`
- Candidate-C log loss: `0.068502780828836138`
- Raw-minus-Candidate-C log-loss delta: `-0.016311216462195618`
- Raw midpoint Brier: `0.014139546080841911`
- Candidate-C Brier: `0.014602932515903819`
- Primary gate: **FAIL**
- Locked test permanently exposed: yes
- Model refit/tune/recalibration: no/no/no
- Orders: 0

Result: Candidate C failed its predeclared terminal advancement criterion.
No post-test redesign is authorized from this block.

<!-- CHECKPOINT18A_DESIGN_20260815 -->
### Checkpoint 18A — Candidate-C development-only generalization-risk review

- Date: 2026-08-15
- Status: **DESIGNED / IMPLEMENTATION PREPARED — RESULT NOT YET ACCEPTED**
- Evidence scope: canonical pre-terminal development evidence only.
- Candidate-C refit: prohibited.
- Successor fit or hyperparameter search: prohibited.
- Terminal result artifact: not an analysis input.
- Terminal rows/labels/features/predictions/residuals: prohibited.
- Planned outputs: block stability, event/week concentration, leave-one-block-out sensitivity, raw-space fold coefficients, stored-fold prediction grid, sharpening/correction diagnostics, feature conditioning, lambda sensitivity, weekly dependence diagnostics, and outcome-blind successor block-layout candidates.
- Interpretation boundary: this experiment may motivate a later predeclared successor but cannot itself advance one.
- Execution: prohibited.

<!-- CHECKPOINT18A_RESULT_ACCEPTED_20260815 -->
### Checkpoint 18A — Candidate-C generalization-risk review result

- Date: 2026-08-15
- Status: **COMPLETED / ACCEPTED AS SUCCESSOR-DESIGN EVIDENCE**
- Run: `data/analysis/kxbtcd_candidate_c_generalization_review/20260815T231543Z`
- Scope: 231 development events / 5,364 rows; 184 OOF events / 4,442 rows.
- Pooled raw-minus-Candidate-C OOF log-loss delta: `+0.06977433833998076`.
- Median event delta: `+0.03752869270657104`.
- 10%-trimmed event-delta mean: `+0.05603263551768059`.
- Top-10 share of gross positive improvement: `0.24857063237091065`.
- Weekly delta lag-1 autocorrelation: `0.2745465399596292`; positive-lag AR(1)-style ESS heuristic: `26.182534819728172` across 46 scored weeks.
- Latest Candidate-C score block B4 log-loss delta: `+0.012732044125987746`, far weaker than B1-B3.
- B4 week-level behavior: 7 of 11 scored weeks had negative log-loss delta.
- Frozen lambda diagnostic: only `0.01` of four lambdas strictly beat raw.
- Raw-space standalone spread slope path: approximately `0.325, 0.412, 0.190, 0.091`.
- Raw-space market-logit slope path: approximately `0.664, 0.697, 0.683, 0.680`.
- Fixed-grid wide-spread example at q_market≈0.585 and spread=0.60: mean Candidate-C probability≈0.848, a ≈+0.263 correction.
- Interpretation: Candidate C's development advantage was broad but temporally weakening and its spread-based corrections were too regime-sensitive to justify carrying that structure forward.
- Candidate-C refit: no. Successor fit/search: no/no. Terminal rows/labels/features loaded: 0/0/0. Network requests: 0. Orders: 0.

<!-- CHECKPOINT18B_CANDIDATE_D_DESIGN_20260815 -->
### Checkpoint 18B — Candidate-D calibration-only predeclaration

- Date: 2026-08-15
- Status: **FROZEN DESIGN — NO FIT**
- Candidate: `kxbtcd_market_logit_recalibration.v1`
- Predeclaration fingerprint: `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`
- Formula: `logit(p_D)=market_logit+alpha+delta*market_logit`.
- Inputs: q_market only; 0.001 clip for the logit transform.
- Excluded: spread, interaction, all other features, scaling, regularization, hyperparameter search.
- Development protocol: outcome-blind seven-block UTC-week layout; rolling score blocks B2-B6; 32 events each.
- Gate: strict pooled log-loss improvement; Brier no worse; at least 4/5 block wins; B6 win; positive median event delta; all fits finite/converged; all fitted slopes positive.
- Interpretation boundary: development stability screen only.
- Terminal firewall: unchanged; genuinely new future test required.
- Execution: prohibited.

<!-- CHECKPOINT18C_CANDIDATE_D_DEVELOPMENT_20260815 -->
### Checkpoint 18C — Candidate-D frozen exposed-development stability screen

- Date: 2026-08-15
- Status: **IMPLEMENTATION PREPARED — RESULT PENDING**
- Candidate: `kxbtcd_market_logit_recalibration.v1`
- Predeclaration fingerprint: `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`
- Week-map fingerprint: `ba93f6a063c616a34437d6f9d208e39b85c993868c71ea78db8b40a70ec23dff`
- Development evidence: canonical 231-event / 5,364-row pre-terminal development pool.
- Score protocol: five rolling-origin folds B2-B6, 32 scored events per block.
- Model: q_market-only intercept/slope logit calibration; raw nested at zero correction.
- Search: no hyperparameter search, regularization, scaling, spread, interaction, or additional feature.
- Primary/secondary metrics and advancement conditions: unchanged from Checkpoint 18B.
- Terminal evidence: prohibited.
- Network/execution: prohibited.
- Result: pending.

<!-- CHECKPOINT18C_CANDIDATE_D_RESULT_20260815 -->
### Checkpoint 18C — Candidate-D frozen development result

- Date: 2026-08-15
- Status: **FAIL**
- Run: `20260815T234004Z`
- Evaluation-result fingerprint: `b72617517d7bbc3bc1e01ff332496efaf5ba0c64c5eb445f82574e63fa4a47ab`
- OOF scope: 160 events / 3,726 rows.
- Raw / Candidate-D log loss: `0.15456664732282768 / 0.15159108042312835`.
- Raw-minus-D log-loss delta: `+0.002975566899699328`.
- Raw / Candidate-D Brier: `0.037893942261917626 / 0.026426318458628383`.
- Raw-minus-D Brier delta: `+0.011467623803289244`.
- Median event delta: `+0.04671924978445033`.
- Better / worse / tie events: `149 / 11 / 0`.
- Block wins: `3/5`.
- B2/B3/B4/B5/B6 log-loss deltas: `+0.093203479823316726`, `+0.0061807888233462449`, `+0.076486093656489507`, `-0.029863425409502709`, `-0.13112910239515319`.
- Latest B6 strictly better: no.
- Frozen failure reasons: fewer than 4/5 block wins; latest B6 not strictly better.
- All fits converged/finite: yes.
- All slopes positive: yes.
- Final Candidate-D fit authorized: no.
- Terminal evidence used: none.
- Network/execution: none.

<!-- CHECKPOINT19A_SUCCESSOR_PROTOCOL_20260815 -->
## Checkpoint 19A — successor research protocol freeze

- Date: 2026-08-15
- Type: outcome-blind protocol / feasibility design; no model fit.
- Input evidence classification: the 231-event development pool is E0 fully exposed exploratory evidence only; Checkpoint-17 terminal evidence is prohibited.
- Research decision: the next successor eligible for advancement must add at least one independent BTC-state signal rather than relying only on transformations of Kalshi market probability.
- Fresh-evidence sequence: E1 successor design -> successor freeze -> E2 final fit -> final-model freeze -> E3 prospective untouched test.
- Initial independent source families for feasibility: Coinbase and Kraken.
- Sample-size boundary: E1/E2/E3 minimum event and calendar coverage will be frozen from outcome-blind availability evidence, not from model outcomes.
- Model result: none. Candidate E is not fit and its exact formula is not frozen.
- Safety: zero outcome access authorized; zero execution authorized.

<!-- CHECKPOINT19B_INDEPENDENT_BTC_FEASIBILITY_20260815 -->
## Checkpoint 19B — independent-BTC source-alignment collector freeze

- Date: 2026-08-15
- Type: outcome-blind engineering feasibility; result not yet collected.
- Parent: Checkpoint-19A protocol fingerprint `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`.
- Frozen pilot: 420 seconds; Coinbase/Kraken target interval 2 seconds; KXBTCD target interval 10 seconds; alternate external-source request order; KXBTCD requested after external attempts; no burst catch-up.
- Descriptive measurements: request/row availability, local first-seen age, cross-source BBO-midpoint disagreement, five-minute causal-history coverage, local receive skew, and KXBTCD TTC coverage.
- Interpretation rule: a pilot PASS means only that the collection/alignment machinery is usable for a longer outcome-blind availability audit. It is not predictive evidence and cannot set E1/E2/E3 sample sizes.
- Model result: none. Candidate E remains unfrozen and unfitted.
- Outcome access: zero authorized. Execution: zero authorized.

<!-- CHECKPOINT19B_PILOT_RESULT_20260816 -->
## Checkpoint 19B — bounded independent-BTC feasibility pilot result

- Run: `collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960`
- Protocol fingerprint: `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`
- Audit design fingerprint: `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`
- Type: outcome-blind source/timing feasibility; no model fit.
- Raw records: 462 total = 210 Coinbase + 210 Kraken + 42 Kalshi; raw errors 0.
- Feasibility: 13,356 rows, 42 KXBTCD snapshots, 318 markets per snapshot, 3 events, both-source availability 100%, structural usability 100%, exclusions 0.
- Snapshot diagnostics: Coinbase age p50 0.1875 s / p95 0.297 s / max 1.282 s; Kraken age p50 0.133 s / p95 0.63395 s / max 0.75 s; cross-source disagreement p50 0.719803 bp / p95 1.087145 bp / max 1.089605 bp.
- Five-minute causal lookback: 11/42 snapshots for each external source, consistent with the bounded warm-up.
- Limitation: only about seven minutes and three KXBTCD events; zero rows in the 30–60m and 1–4h TTC bands.
- Result: PASS for engineering feasibility only. No source-quality threshold, cohort size, Candidate-E formula, model performance, or profitability conclusion is authorized.
- Outcomes accessed: false. Candidate-E fitting: false. Execution: false.

<!-- CHECKPOINT19C_EXTENDED_AVAILABILITY_20260816 -->
## Checkpoint 19C — extended independent-BTC availability design freeze

- Type: outcome-blind source/timing/calendar/TTC evidence only.
- Parent 19B result: engineering-feasibility PASS from `collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960`; not model evidence.
- Frozen collection: 24 hours; 15-second Coinbase/Kraken targets; 5-minute KXBTCD targets; balanced external request order; KXBTCD after external attempts.
- New diagnostics: one row per external cycle, one row per KXBTCD snapshot, UTC-hour coverage, and five-minute lookback target-gap distributions.
- Thresholds selected: none.
- Candidate E: unfrozen and unfitted.
- Outcomes accessed: false.
- Execution: false.

<!-- CHECKPOINT19C_RESULT_CLOSEOUT_20260817 -->
## Checkpoint 19C — extended independent-BTC availability result

- Date: 2026-08-17 local closeout; live collection spans UTC 2026-08-16 to 2026-08-17.
- Type: outcome-blind engineering/source-quality evidence; no model fit.
- Run: `collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250`.
- Manifest: `data/manifests/2026/08/16/collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250.json`.
- Protocol fingerprint: `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`.
- Audit design fingerprint: `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d`.
- Collection-start Git commit: `86019fe76ead50d2cc41daf03d5fa5a1b2a75c7c`; worktree dirty at start: false.
- Integrity: 6 raw files / 11,804 raw records / 0 raw errors; 6 derived CSVs / 96,405 total derived rows; 1 runtime file / 11,806 runtime events / 0 runtime errors; manifest validation PASS.
- Collection: 5,758 external cycles; 288 KXBTCD snapshots; 90,288 feasibility rows; 27 unique events; 4,722 unique markets; 25 UTC-hour buckets; 2 UTC dates touched.
- Availability: Coinbase request success 1.0; Kraken 1.0; Kalshi 1.0; both-source external-cycle availability 1.0; both-source row availability 1.0; structurally usable rows 90,288/90,288; exclusions 0; longest failure streak 0 for all three source families.
- Five-minute lookback row availability: Coinbase = 0.996477937267411; Kraken = 0.996477937267411.
- Five-minute target-gap p50/p95/max: Coinbase = 1.297/2.2359/13.735 s; Kraken = 1.109/2.0377/15.75 s.
- Local first-seen source age p50/p95/max at KXBTCD snapshots: Coinbase = 1.297/2.203/41.422 s; Kraken = 1.109/1.985/40.406 s.
- External-cycle cross-source disagreement p50/p95/max: 0.7268472244022195 / 2.7526752145628617 / 5.347777694885947 bp.
- External receive skew p50/p95/max: 156 / 234 / 9,687 ms.
- TTC row counts: 0–30m = 26,424; 30–60m = 26,424; 1–4h = 2,880; 4–24h = 19,200; >24h = 15,360.
- Tail review: the maximum receive skew was isolated around 09:05 UTC near the only visibly reduced hourly cadence; requests remained successful and subsequent cycles recovered. Manual timestamp inspection also showed that local request success and exchange-level publication freshness are distinct diagnostics.
- Result: **PASS for extended engineering feasibility only**.
- Model evidence: none. Candidate E formula frozen = false; Candidate E fit = false; outcomes accessed = false; Checkpoint-17 used = false.
- Execution: false; orders = 0.
- Decision boundary: do not infer predictive edge or profitability. Freeze exact source-quality/materialization rules and fresh-evidence requirements before E1 outcome access or Candidate-E fitting.

<!-- CHECKPOINT19D_A_HISTORICAL_MATERIALIZATION_20260817 -->
## Checkpoint 19D-A — historical materialization audit design freeze

- Date: 2026-08-17.
- Type: outcome-blind source/timestamp/historical-reconstruction evidence; no model fit.
- Parent 19C run: `collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250`.
- Parent snapshots: 288 exact KXBTCD state timestamps.
- Audit fingerprint: `023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c`.
- Coinbase candidate historical source: `coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1`.
- Kraken candidate historical source: `kraken.spot.public_rest.posttrade.btc_usd.v1`.
- Causal current state: last fully completed one-minute UTC bucket only.
- Causal lookback: exact completed one-minute bucket 300 seconds earlier.
- Historical missing-data rule: exclude; no future interpolation, nearest-absolute replacement, or carry-forward.
- Kraken historical causality: selected trade must satisfy `publication_ts <= original KXBTCD as_of_utc`.
- Live 19C timestamp reanalysis: Coinbase source-event age plus Kraken bid/ask publication ages and conservative older-side age.
- Thresholds selected: none.
- Candidate E: unfrozen/unfitted.
- Outcomes accessed: false.
- Checkpoint-17 used: false.
- Execution/orders: false / 0.

<!-- CHECKPOINT19D_A_RESULTS_20260817 -->
## 2026-08-17 — Checkpoint 19D-A independent-BTC historical materialization audit

**Run:** `collect_kxbtcd_independent_btc_historical_materialization_20260817T061908727611Z_f90d93fc`

**Design fingerprint:** `023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c`

**Result:** COMPLETE / outcome-blind source-quality evidence only.

- 288 frozen 19C snapshots; 291 unique target minutes.
- Coinbase exact-minute current/lookback coverage: 100% / 100%.
- Kraken exact-minute current/lookback coverage: 287/288 / 287/288.
- Both-source current coverage: 287/288.
- Both-source current + exact-5m-pair coverage: 286/288.
- The two exclusions trace to one Kraken minute, 2026-08-16 09:09–09:10 UTC.
  Preserved raw PostTrade response: HTTP 200, `count=0`, `trades=[]`; genuine
  no-trade minute, not transport/parser/publication-causality failure.
- Current cross-source disagreement (`n=287`): p50 0.7216 bp, p95 2.9591 bp,
  p99 4.4667 bp, max 6.0368 bp.
- Exact-5m lookback disagreement (`n=287`): p50 0.7302 bp, p95 2.9591 bp,
  p99 4.4667 bp, max 6.0368 bp.
- Kraken 19C conservative BBO publication age: p50 22.012 s, p95 49.175 s,
  p99 354.472 s, max 6120.316 s despite local-first-seen p50 1.109 s.
- No outcomes accessed; no Candidate-E fit/formula freeze; no thresholds or
  evidence cohort sizes selected; no execution.
- Audit-time parser compatibility fix: blank Kraken `last_ts` is no cursor;
  full-page missing cursor still fails closed.
- Validation/regression: focused 7 passed; full suite 732 passed + 22 subtests;
  source registry PASS.

**Interpretation:** historical independent-BTC reconstruction is operationally
feasible at very high coverage under the frozen exact-minute/no-imputation
contract. Predictive value and final source gates remain unresolved for 19D-B.

<!-- CHECKPOINT19D_B_SOURCE_POLICY_20260817 -->
## 2026-08-17 — Checkpoint 19D-B outcome-blind source-policy freeze

No model fit or outcome evaluation was performed.

Policy fingerprint:
`6b0d98c16a65b2e638b36991d5006031e1bd37048bd04a47a3f67d936df0ee18`

Input evidence was limited to 19C/19D-A source availability, timestamp,
historical reconstruction, cross-source disagreement, and calendar/TTC
diagnostics.

Frozen operational gates:
- local first-seen <=5 s on Coinbase and Kraken;
- Coinbase source-event age <=10 s;
- Kraken conservative BBO publication age <=60 s;
- cross-source receive skew <=1 s;
- midpoint disagreement <=5 bp;
- absolute local clock offset <=1 s.

Frozen evidence minimums:
- E1: 168 eligible events / 7 UTC days;
- E2: 168 eligible events / 7 UTC days;
- E3: 336 eligible events / 14 UTC days;
- all 24 UTC hour bins;
- >=90% scheduled-state source eligibility;
- >=2/3 scheduled-state source eligibility per counted event.

Candidate-E formula frozen: false.
Candidate-E fitting performed: false.
Outcomes accessed for policy selection: false.
Checkpoint-17 terminal used: false.
Execution performed: false.

<!-- CHECKPOINT19E_CANDIDATE_E_PREDECLARATION_20260817 -->
## Checkpoint 19E — Candidate-E predeclaration freeze

Status: **DESIGN FROZEN / NO E1 OUTCOMES / NO FIT**

Fingerprint: `9775be58f01375ca6f2b04212a63578ce5e8cf7084498e6ce9d3ae68685d59a9`

Frozen hypothesis:
- raw Kalshi midpoint remains a fixed logit offset;
- independent BTC strike distance may add incremental information;
- a causal five-minute BTC return is the only additional complexity candidate.

Frozen menu:
- `kxbtcd_btc_distance_offset_logistic.v1`
- `kxbtcd_btc_distance_momentum_offset_logistic.v1`

Feature formulas:
- `d_BTC = 10000*ln(S_t/K)`
- `r_5m = 10000*ln(S_t/S_t-300s)`

No fit, score, lambda search, E1 outcome access, Checkpoint-17 terminal access, network experiment, or execution was performed by this design-freeze step.

<!-- CHECKPOINT19F_HISTORICAL_EVIDENCE_AMENDMENT_20260817 -->
## 2026-08-17 — Checkpoint 19F historical evidence amendment (design only)

No Candidate-E fit and no new Candidate-E outcome access occurred. Outcome-blind inventory found 9,738 modern-regime KXBTCD events, 307 unique prior outcome-exposed events, and 9,431 untouched events. Source hashes and the untouched chronological universe were frozen; untouched-universe SHA-256 is `d0b61b7688e54ff4cdeb4cc4652a8ecd5a0a5031b14ad7666b1a8b5b0b5fda90`.

Predeclared historical evidence targets: H1=1,500 eligible events, H2=750, H3=750. Nominal unallocated reserve=6,431 events; minimum protected outcome-unopened reserve after Candidate-E materialization=5,000. H2 remains sealed unless H1 passes; H3 remains sealed unless H2 passes and final parameters are frozen.

Amendment fingerprint: `b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb`. This is a protocol/design record, not predictive or profitability evidence.

<!-- CHECKPOINT19F_FINAL_CLOSEOUT_20260817 -->
## 2026-08-17 ? Checkpoint 19F historical evidence amendment validation

Purpose: replace the frozen prospective-only Candidate-E evidence timing with a historical-first sequential evidence protocol before opening any new Candidate-E labels.

Frozen universe validation:
- census events: 9,738
- prior outcome-exposed events: 307
- untouched events: 9,431
- untouched-universe SHA-256: `d0b61b7688e54ff4cdeb4cc4652a8ecd5a0a5031b14ad7666b1a8b5b0b5fda90`

Frozen allocation:
- H1 train 1,500
- H2 validation 750
- H3 locked test 750
- nominal reserve 6,431
- minimum protected outcome-unopened reserve 5,000

Amendment fingerprint:
`b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb`

Validation result:
- local universe validator PASS
- focused tests: 6 passed
- full regression: 759 passed + 22 subtests
- git diff check PASS
- new Candidate-E outcomes: zero
- Candidate-E fits: zero
- execution: prohibited

An initial Windows path-separator mismatch in the universe validator was corrected through portable path normalization. A regression test was added. No evidence hash, model rule, outcome boundary, or amendment fingerprint changed.

Result: PASS for protocol amendment and frozen-universe verification only. No predictive-performance claim is made.

<!-- CHECKPOINT19F_STAGED_DIFF_REPAIR_20260817 -->
### 2026-08-17 ? 19F staged-diff sanitation

The safe checkpoint helper blocked the first closeout attempt because `tests/test_kxbtcd_candidate_e_historical_evidence_amendment.py` contained an extra blank line at EOF. No commit or push occurred. The file was normalized and closeout validation was repeated. This was a whitespace-only packaging repair with no research-semantic change.

<!-- CHECKPOINT19G_HISTORICAL_MATERIALIZATION_20260817 -->
## 2026-08-17 — Checkpoint 19G pre-collection materialization freeze

19G freezes only historical source/materialization mechanics under `cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145`. No new Candidate-E outcomes are accessed and no model is fit.

Frozen rule: process the exact 19F untouched queue chronologically; an event counts only with >=4/6 eligible anchors. Each counted anchor requires exact eligible Coinbase/Kraken current + exact 5m-lookback pairs and >=1 valid structural Kalshi quote row. Valid common rows are preserved individually. Final required blocks must cover all five structural roles and six TTC targets.

The historical-market source outcome-field issue is made explicit: raw source responses remain immutable, while research metadata is allow-list projected and result/settlement values are regression-invariant and forbidden from downstream influence.

Next evidence is engineering validation and closeout of the frozen 19G collector; then Checkpoint 19H performs the canonical outcome-blind chunk collection and offline cohort/row freeze.

<!-- CHECKPOINT19H_SMOKE_VALIDATION_20260817 -->
## 2026-08-17 ? Candidate-E historical materialization smoke

Purpose: verify the frozen 19G collector against real historical Kalshi, Coinbase, and Kraken sources before canonical H1/H2/H3 materialization.

Initial attempt:
- failed at derived CSV creation due effective Windows path length
- API/data semantics were not the cause
- no Candidate-E outcomes or fits occurred

Implementation-only repair:
- removed redundant smoke run_id directory component
- preserved run_id in filenames, manifests, runtime logs, and row lineage
- added regression coverage for the Windows path construction

Successful smoke:
- run `collect_kxbtcd_candidate_e_historical_materialization_chunk_20260817T082547653987Z_48b89ca0`
- queue [0,2)
- 2/2 eligible events
- 30 common pre-outcome rows
- 0 outcomes
- 0 fits
- 0 orders

Validation:
- focused tests: 10 passed
- full suite: 769 passed + 22 subtests
- diff check: PASS

Interpretation: engineering smoke PASS only. This is not predictive-performance evidence.

<!-- CHECKPOINT19HB_COINBASE_PRIMARY_20260817 -->
## 2026-08-17 — Outcome-blind Kraken-veto counterfactual audit

Scope: first 600 canonical Candidate-E historical queue identities; 3,600 scheduled anchors. No network requests were made by the counterfactual audit, no Candidate-E outcomes were accessed, and no Candidate-E model was fit.

Results:
- current Coinbase+Kraken+5bp event eligibility: 303/600 = 50.50%;
- both sources with no disagreement veto: 459/600 = 76.50%;
- Coinbase-only: 459/600 = 76.50%;
- events rescued by removing 5bp veto: 156;
- current disagreement >5bp anchor flags: 570;
- lookback disagreement >5bp anchor flags: 570;
- missing Kraken current/lookback: 3/3 anchors.

Interpretation: the cross-venue disagreement veto, not Kraken availability, was the dominant source of avoidable coverage loss. This is source-policy evidence only, not predictive-performance evidence.

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
## Checkpoint 20A — Candidate-E H1 procedure freeze

Outcome-blind procedure validation/freeze only. H1 outcomes opened: 0. Candidate-E fits performed: 0. H2 outcomes opened: 0. H3 outcomes opened: 0. Orders placed: 0.

Frozen H1: 1500 events / 36314 rows / 6631 unique market outcome requests. H2 and H3 identities remain sealed and hard denied.

Procedure fingerprint: `cbbca76de2dd87edd6c6bc4f21ae1005fbd1402a3bb85374e7699c8fb5fb7d14`.

<!-- CHECKPOINT20B_CANDIDATE_E_H1_RESULT_20260817 -->
## Checkpoint 20B — Candidate-E H1 historical development result

The one-time frozen H1 evaluation completed from a clean synchronized checkout and validated successfully.

- H1: 1,500 events / 36,314 rows
- OOF scored events: 1,070
- H1 result fingerprint: `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`
- raw Kalshi event-equal log loss: `0.10494755188081126`
- Distance event-equal log loss: `0.03379679620851983`
- raw-minus-Distance log-loss delta: `0.071150755672291427`
- raw Kalshi event-equal Brier: `0.020374750709011895`
- Distance event-equal Brier: `0.0090293992615540601`
- raw-minus-Distance Brier delta: `0.011345351447457835`
- Distance raw advancement gate: PASS
- Distance+Momentum raw advancement gate: PASS
- Distance+Momentum nested complexity gate: FAIL
- nested chronological block wins: 2 / 5
- frozen H1 selection: `kxbtcd_btc_distance_offset_logistic.v1`

The more complex Distance+Momentum model was microscopically better in pooled metrics but won only two of five chronological score blocks, so the frozen complexity gate rejected it and the simpler Distance specification was selected.

H1 is permanently development-exposed. H2 outcomes opened: 0. H3 outcomes opened: 0. No post-hoc H1 repair or feature change is authorized. Execution remains prohibited.

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
## Checkpoint 20F — Candidate-E H2 historical validation PASS

The one-time frozen H2 validation completed from a clean synchronized checkout and its manifest/result artifacts validate successfully.

- H2: 750 events / 22,354 rows / 3,750 finalized market labels
- H2 result fingerprint: `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`
- H2 validation fingerprint: `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`
- H2 implementation fingerprint: `0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e`
- final H1 model fingerprint: `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
- frozen beta_distance: `0.012310034918384302`
- raw Kalshi event-equal log loss: `0.11774919111369225`
- Distance event-equal log loss: `0.035893546124196762`
- raw-minus-Distance log-loss delta: `0.081855644989495491`
- raw Kalshi event-equal Brier: `0.022327771656461513`
- Distance event-equal Brier: `0.0099357895512881093`
- raw-minus-Distance Brier delta: `0.012391982105173404`
- median event raw-minus-Distance log-loss delta: `0.07528266021513054`
- chronological H2 block log-loss wins: 5 / 5
- newest B4: win
- frozen H2 gate: PASS

H2 is permanently outcome-exposed and may not be reused as untouched validation evidence for a future candidate influenced by this result. No H2 parameter fitting, candidate selection, feature change, hyperparameter search, post-hoc repair, or execution occurred. H3 outcomes remain sealed.

This is predictive-scoring evidence only. It does not establish trading profitability or execution suitability.

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
## Checkpoint 20J — Candidate-E H3 locked-test PASS

The one-time frozen H3 historical locked test completed from a clean synchronized checkout and its manifest/result artifacts validate successfully.

- H3: 750 events / 22,409 rows / 3,750 finalized market labels
- H3 result fingerprint: `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`
- H3 validation fingerprint: `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`
- H3 implementation fingerprint: `6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc`
- final H1+H2 model fingerprint: `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
- frozen beta_distance: `0.013805016135330063`
- raw Kalshi event-equal log loss: `0.13793316358637769`
- Distance event-equal log loss: `0.038920564033036092`
- raw-minus-Distance log-loss delta: `0.099012599553341601`
- raw Kalshi event-equal Brier: `0.027664663135376771`
- Distance event-equal Brier: `0.01025442810344244`
- raw-minus-Distance Brier delta: `0.017410235031934333`
- median event raw-minus-Distance log-loss delta: `0.085591053297719571`
- chronological H3 block log-loss wins: 5 / 5
- newest B4: win
- frozen H3 gate: PASS
- Candidate-E historical H1/H2/H3 generalization program: PASS

H3 is permanently outcome-exposed and may not be reused as untouched evidence for a future model influenced by this result. No H3 fitting, candidate selection, feature change, hyperparameter search, post-hoc repair, or execution occurred.

This establishes strong historical predictive-generalization evidence for the frozen Candidate-E Distance specification. It does not establish trading profitability or execution suitability.

<!-- CHECKPOINT21A_POST_H3_LIFECYCLE_20260817 -->
## 2026-08-17 — Checkpoint 21A post-H3 champion lifecycle protocol freeze

Status: **DESIGN FROZEN / NO POST-H3 FIT / NO RESERVE OUTCOMES**

Parent historical result:
- Candidate E: `kxbtcd_btc_distance_offset_logistic.v1`
- H3 result fingerprint: `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`
- H1/H2/H3 exposed events: 3,000
- historical generalization program: PASS

New protocol:
- fingerprint: `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
- strict untouched tail entering protocol: approximately 6,231 events
- C1/C2/C3: 500 eligible events each
- each block: five chronological 100-event subblocks
- strict untouched-tail floor: 4,500 events
- fit sizes before C1/C2/C3: 3,000 / 3,500 / 4,000 exposed events
- final historical fit after all three PASS: 4,500 exposed events
- immediate stop on any confirmation failure

C-block PASS requires strict pooled event-equal log-loss improvement over raw Kalshi midpoint, non-worse Brier, >=4/5 chronological subblock wins, newest-subblock win, positive median event-level improvement, valid positive Distance fit, structural/TTC coverage, and no source/timing/lineage/firewall violation.

Post-confirmation architecture:
- strategy research only after C1+C2+C3 PASS;
- strategy design uses exposed evidence only;
- protected strict reserve cannot tune strategy or challengers before their procedures are frozen;
- first strategy task is an execution-data adequacy audit;
- later live phase is intended to combine immutable forecasting with a full local mock decision/fill/P&L stack;
- prospective forecasting cohort: 1,000 new eligible events in five 200-event blocks under one immutable model;
- exact economic shadow gates remain deferred until strategy research and must be frozen before live mock decisions;
- current risk policy still prohibits a live paper/shadow broker.

Evidence produced by Checkpoint 21A:
- new predictive score: none;
- post-H3 Candidate-E fit: none;
- C1/C2/C3 outcomes: 0 / 0 / 0;
- strategy P&L result: none;
- execution: none.

This entry is a protocol decision, not predictive or profitability evidence.

<!-- CHECKPOINT21B_A_C1_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21B-A — C1 preparation implementation freeze

Implementation fingerprint: `b69b13a6d0db89be98229f34a946cbdfa24a7280ddbc8bff968f641714a93672`.

The code path that will later (1) fit the unchanged Candidate-E Distance champion on all 3,000 already-exposed H1/H2/H3 events and (2) sequentially materialize only C1 from the strict queue tail is frozen before reserve access. The C1 collector begins at queue index 3200, has no arbitrary start-index argument, stops exactly at the 500th eligible event, and enforces the Checkpoint-21A 4,500-candidate strict-tail floor.

This checkpoint performs no Champion-R0 fit, no network collection, no C1/C2/C3 outcome access, no C2/C3 materialization, and no execution. After safe closeout, the next action is Checkpoint 21B-B: deterministically create and freeze Champion-R0 on exposed H1/H2/H3 only. C1 materialization begins only after that R0 artifact is safely closed.

<!-- CHECKPOINT21B_B_CHAMPION_R0_20260818 -->
## Checkpoint 21B-B ? Champion-R0 deterministic fit

Purpose: freeze the exact Candidate-E model entering C1 without consuming fresh
reserve evidence.

Input evidence:
- H1: 1,500 exposed events / 36,314 rows
- H2: 750 exposed events / 22,354 rows
- H3: 750 exposed events / 22,409 rows
- total: 3,000 exposed events / 81,077 rows

Result:
- candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- `beta_distance`: `0.014447239079794087`
- objective: event-equal binary log loss
- optimizer: deterministic damped Newton
- converged: yes
- iterations: 10
- fit objective: `0.054050012863507545`
- Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- artifact SHA-256: `811a2776684f130d8b36f1ffb9253e90d678ffda9faf237815282fb67619c8d3`

Research firewall:
- C1 rows used: 0
- C1 outcomes opened: 0
- network requests: 0
- feature/hyperparameter search: none
- execution/orders: disabled / 0

Interpretation: this is a model-artifact freeze, not fresh predictive evidence
and not profitability evidence.

<!-- CHECKPOINT21B_C_C1_PREOUTCOME_FREEZE_20260818 -->
## Checkpoint 21B-C ? C1 outcome-blind materialization

Purpose:
construct the first fresh post-H3 confirmation cohort without allowing its
outcomes to influence selection, fitting, eligibility, or allocation.

Frozen result:
- entering model fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- eligible C1 events: 500
- candidate identities inspected: 506
- ineligible identities encountered: 6
- strict-tail queue range: `[3200, 3706)`
- C1 pre-outcome rows: 14887
- C1 unique markets: 2491
- cohort fingerprint: `7f53764ca50d4a5e00a4d12d0cebda566a1333a6951b2686b2c9d06631c1ca36`
- row fingerprint: `6d02d8b484813760a87a7daea05ecf994e18ae875e7e066e9b097ac830e01af8`
- validation fingerprint: `76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`
- strict untouched tail remaining: 5725
- reserve floor: 4500
- reserve buffer: 1225

Research firewall:
- C1 outcomes opened: 0
- C2/C3 materialized: 0
- candidate selection: none
- feature/hyperparameter changes: none
- execution/orders: disabled / 0

Interpretation:
this checkpoint establishes fresh evidence identities only. It provides no
information yet about whether Champion-R0 passes C1 and provides no evidence of
trading profitability.

<!-- CHECKPOINT21C_C1_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21C — C1 evaluator implementation freeze

Purpose: freeze the exact software that may later open C1 labels, while C1 is
still outcome-sealed.

Frozen lineage:
- Champion-R0: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- C1 validation: `76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`
- evaluator implementation: `2719cef9c5180014f3230c724be76bf959d71882a2f0c84e386a5169392773af`
- C1 scope: 500 events / 14887 rows / 2491 unique market labels

Frozen behavior:
- exact C1 allow-list only;
- H1/H2/H3 hard deny;
- raw-first public historical outcome retrieval;
- full-C1 exposure receipt before first request;
- resume-only same attempt after interruption;
- fixed Champion-R0 prediction, no fit/tune/select;
- event-equal log loss and Brier plus five chronological block diagnostics;
- exact Checkpoint-21A C1 advancement gate;
- no C2/C3 access and no execution.

Evidence firewall at freeze:
- C1 outcomes opened: 0
- network requests: 0
- model fits: 0
- orders: 0

This checkpoint is engineering/protocol evidence only, not a predictive or
profitability result.

<!-- CHECKPOINT21D_C1_RESULT_20260818 -->
## Checkpoint 21D ? Candidate-E C1 fresh confirmation

Run:
`collect_kxbtcd_candidate_e_c1_20260818T032929566587Z_5a689483`

Result:
- C1 result fingerprint: `5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19`
- C1 events / rows / labels: 500 / 14,887 / 2,491
- beta_distance: `0.014447239079794087`
- raw event-equal log loss: `0.17078339823721184`
- Candidate-E log loss: `0.053151764629610743`
- raw-minus-Candidate-E log-loss delta: `0.11763163360760109`
- raw event-equal Brier: `0.039207186965517601`
- Candidate-E Brier: `0.01515132922607266`
- raw-minus-Candidate-E Brier delta: `0.024055857739444943`
- median event log-loss delta: `0.10189307395366344`
- block deltas: `B0=0.10373801818068928, B1=0.13986583525420937, B2=0.10756039058421205, B3=0.10359083325320459, B4=0.13340309076568999`
- block wins: 5 / 5
- newest B4: win
- C1 gate: PASS

Research firewall:
- C1 permanently exposed: yes
- model fit/tuning on C1: no / no
- feature/candidate/hyperparameter change: none
- C2/C3 materialized or opened: no
- execution/orders: disabled / 0

Interpretation:
The unchanged champion generalized strongly to the first fresh 500-event
post-H3 confirmation block. This is predictive evidence only and does not
establish transaction-cost-adjusted profitability.

<!-- CHECKPOINT21E_A_C2_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21E-A — C2 preparation implementation freeze

Purpose: freeze implementation before the next model/evidence transition.

- implementation fingerprint: `c2be562e2476995dd4adb712a035ac69eca8ca6b4b7fa93c53106758286dc327`
- entering evidence state: H1/H2/H3/C1 exposed; C2/C3 untouched
- future Champion-R1 fit scope: 3,500 events / 95,964 rows
- C2 strict start: 3706
- absolute max end-exclusive: 4931
- remaining candidate-identity runway across C2+C3: 1,225
- minimum never-materialized tail: 4,500
- Champion-R1 fits during freeze: 0
- network requests during freeze: 0
- C2 outcomes opened: 0
- C3 materialized/opened: 0
- orders: 0

This checkpoint contains no new predictive result and no profitability result.

<!-- CHECKPOINT21E_B_CHAMPION_R1_20260818 -->
## Checkpoint 21E-B ? Champion-R1 expanding fit

Purpose:
update the unchanged champion coefficient using newly exposed C1 evidence
without accessing C2.

Result:
- candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- fit events: 3,500
- fit rows: 95,964
- Champion-R1 fingerprint: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- beta_distance: `0.014529004270980883`
- objective: `0.053921466611488181`
- deterministic Newton iterations: 10
- converged: true

Evidence firewall:
- all fit outcomes already exposed: yes
- C2 rows used: 0
- C2 outcomes used/opened: 0
- C3 materialized/opened: 0
- feature/candidate/hyperparameter change: none
- network requests: 0
- execution/orders: disabled / 0

Interpretation:
this is a parameter refresh under the frozen expanding-window protocol, not a
new predictive-performance measurement and not trading-profitability evidence.

<!-- CHECKPOINT21E_C_C2_PREOUTCOME_FREEZE_20260818 -->
## Checkpoint 21E-C ? C2 outcome-blind materialization

Purpose:
construct the second fresh champion-confirmation cohort without allowing its
outcomes to influence fitting, selection, eligibility, or scoring.

Frozen result:
- entering Champion-R1: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- eligible C2 events: 500
- candidate identities inspected: 516
- ineligible identities: 16
- strict-tail queue range: `[3706, 4222)`
- C2 pre-outcome rows: 14007
- unique markets: 2441
- cohort fingerprint: `446854d2511a942fff560ffe78bbd96863b06d9046de85ff7a8605c868654258`
- row fingerprint: `525477c08178f1bd97f58fee0e22f6e5352494cb38210c433a0df7a2af57c9b3`
- validation fingerprint: `b984017e17da9de2859d43b78f1218d7333eda45eb1ebb0ed3a6a884eb3746f1`
- strict untouched tail remaining: 5209
- reserve floor: 4500
- reserve buffer: 709

Research firewall:
- C2 outcomes opened: 0
- C3 materialized: 0
- candidate selection: none
- feature/hyperparameter changes: none
- execution/orders: disabled / 0

Interpretation:
this checkpoint creates fresh evidence identities only. It contains no C2
performance result and no trading-profitability evidence.

<!-- CHECKPOINT21F_A_C2_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21F-A — C2 evaluator implementation freeze

Purpose:
freeze the complete C2 outcome-opening/scoring procedure before C2 outcomes
can influence any research choice.

Frozen implementation fingerprint:
`a958b843a5504507b598f05fba79f57691b21ffe9aee6be8148ca12fd38ab3c2`.

Bound inputs:
- Champion-R1 fingerprint:
  `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- C2 validation fingerprint:
  `b984017e17da9de2859d43b78f1218d7333eda45eb1ebb0ed3a6a884eb3746f1`
- C2 cohort: 500 events / 14,007 rows / 2,441 markets
- gate: unchanged Checkpoint-21A gate

Research firewall:
- C2 outcomes opened: 0
- network requests: 0
- model fit/tuning/selection: 0
- C3 materialization/outcome access: 0
- execution/orders: disabled / 0

This checkpoint contains no predictive result and no profitability result.

<!-- CHECKPOINT21F_B_C2_RESULT_20260818 -->
## Checkpoint 21F-B ? Candidate-E C2 fresh confirmation

Run:
`collect_kxbtcd_candidate_e_c2_20260818T041938751430Z_ed2d9d54`

Result:
- C2 result fingerprint: `ee6cd30b32a9445096f25934d67dfa34046504ee83889947be8c8a40377a8f62`
- result closeout fingerprint: `5660e4d04856f534543f0fdd53a1b687b07666ffd52d59e8e80fcefe6ddc87cf`
- C2 events / rows / labels: 500 / 14,007 / 2,441
- beta_distance: `0.014529004270980883`
- raw event-equal log loss: `0.16763671430199342`
- Candidate-E log loss: `0.05064447819587261`
- raw-minus-Candidate-E log-loss delta: `0.11699223610612081`
- raw event-equal Brier: `0.03957031952485842`
- Candidate-E Brier: `0.015191801215127898`
- raw-minus-Candidate-E Brier delta: `0.024378518309730521`
- median event log-loss delta: `0.13555827126142961`
- block deltas:
  `B0=0.13947804627980334`,
  `B1=0.12660541888180846`,
  `B2=0.12982186853271965`,
  `B3=0.084476671344659388`,
  `B4=0.10457917549161326`
- block wins: 5 / 5
- newest B4: win
- C2 gate: PASS

Research firewall:
- C2 permanently exposed: yes
- model fit/tuning on C2: no / no
- feature/candidate/hyperparameter change: none
- C3 materialized/opened: no
- execution/orders: disabled / 0

Interpretation:
The unchanged champion again generalized strongly on a second independent
500-event confirmation block. This is predictive evidence only and does not
establish transaction-cost-adjusted profitability.

<!-- CHECKPOINT21G_A_C3_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21G-A — Champion-R2/C3 preparation implementation freeze

Purpose:
freeze the exact expanding-window refit and C3 materialization procedure before
the final historical confirmation reserve is touched.

Frozen implementation fingerprint:
`76db878cbc62662b4f5c372f9dad73767c3bee356a9765e6204c2a0091d92357`.

R2 fit contract:
- unchanged Distance candidate only;
- H1+H2+H3+C1+C2;
- 4,000 exposed events / 109,971 rows;
- C3 rows/outcomes: 0 / 0;
- no feature/candidate/hyperparameter selection.

C3 materialization contract:
- start queue index: 4222;
- target: 500 eligible events;
- five chronological 100-event blocks;
- absolute end-exclusive boundary: 4931;
- maximum candidate identities available: 709;
- protected tail floor: 4,500;
- no arbitrary start index;
- outcome-blind only.

Research firewall at 21G-A:
- Champion-R2 fit: 0
- C3 materialization: 0
- C3 outcomes: 0
- network requests: 0
- execution/orders: disabled / 0

This checkpoint is protocol/engineering evidence only.

<!-- CHECKPOINT21G_B_CHAMPION_R2_20260818 -->
## Checkpoint 21G-B ? Champion-R2 deterministic refit

Purpose:
produce the exact frozen model that will enter the final historical C3
confirmation block.

Fit evidence:
- H1: 1,500 events / 36,314 rows
- H2: 750 events / 22,354 rows
- H3: 750 events / 22,409 rows
- C1: 500 events / 14,887 rows
- C2: 500 events / 14,007 rows
- total: 4,000 events / 109,971 rows

Result:
- Champion-R2 fingerprint: `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- literal artifact SHA-256: `d5c99e0099f37eb69921934a850d1778690d53ad7045a394fa91c0e3362b2d14`
- beta_distance: `0.014501283346050064`
- fit objective: `0.053511817851523945`
- iterations: 10
- converged: yes

Research firewall:
- all fit outcomes were previously exposed
- C3 rows used: 0
- C3 outcomes used/opened: 0
- candidate/feature/hyperparameter changes: none
- network requests: 0
- execution/orders: disabled / 0

Interpretation:
this is an expanding-window refit, not a fresh performance evaluation.
Champion-R2 becomes the immutable entering model for C3 after safe closeout.

<!-- CHECKPOINT21G_C_C3_PREOUTCOME_20260818 -->
## Checkpoint 21G-C ? C3 outcome-blind materialization and freeze

C3 materialization began at untouched-queue index 4222.

Chunk progression:

- `[4222, 4322)`: 100 inspected, 100 eligible; cumulative 100
- `[4322, 4422)`: 100 inspected, 100 eligible; cumulative 200
- `[4422, 4522)`: 100 inspected, 100 eligible; cumulative 300
- `[4522, 4622)`: 100 inspected, 100 eligible; cumulative 400
- `[4622, 4722)`: 100 inspected, 80 eligible; cumulative 480
- `[4722, 4755)`: 33 inspected, 20 eligible; cumulative 500

Final:
- 533 identities inspected
- 500 eligible
- 33 outcome-blind exclusions
- 13,549 frozen rows
- 2,470 unique markets
- C3 validation fingerprint: `44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0`
- cohort fingerprint: `08add4c28831c0d460dff706b0cc425550a4d5d3f486d3ec7f14622586101f6b`
- row fingerprint: `898400f7401ef9a96a9c1a0a6d2c99479395ff9fb0a13d93ea7c5fbc3dad51db`
- untouched tail after C3: 4,676
- reserve-floor buffer: 176

No outcome labels were opened and no scoring or fitting occurred.

<!-- CHECKPOINT21H_A_C3_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21H-A — C3 evaluator implementation freeze

Purpose: freeze the one-time C3 outcome procedure before label access.

Frozen scope:
- C3 500 events
- 13,549 pre-outcome rows
- 2,470 market outcome requests
- Champion-R2 beta_distance `0.014501283346050064`
- implementation fingerprint `8f84f299f21b132ffd2db93aeb1f23dc586d5d11a189a271ef707be94d15455f`
- unchanged 21A gate
- 4,000 prior exposed events hard denied
- remaining historical reserve inaccessible

Evidence at implementation freeze:
- C3 outcomes opened: 0
- model fits: 0
- network requests: 0
- execution/orders: 0

This checkpoint is procedural evidence only. The next one-time run is the
actual final historical C3 confirmation.

<!-- CHECKPOINT21H_B_C3_RESULT_20260818 -->
## Checkpoint 21H-B ? C3 final historical confirmation

Run:
`collect_kxbtcd_candidate_e_c3_20260818T051417765823Z_e29fd0d7`

Frozen inputs:
- Champion-R2 `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- C3 validation `44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0`
- C3 implementation `8f84f299f21b132ffd2db93aeb1f23dc586d5d11a189a271ef707be94d15455f`
- C3 cohort `08add4c28831c0d460dff706b0cc425550a4d5d3f486d3ec7f14622586101f6b`
- C3 rows `898400f7401ef9a96a9c1a0a6d2c99479395ff9fb0a13d93ea7c5fbc3dad51db`

Result:
- 500 events
- 13,549 rows
- 2,470 finalized labels
- raw LL `0.12097454402315916`
- Distance LL `0.023718447966231782`
- LL delta `0.09725609605692738`
- raw Brier `0.025969129033350857`
- Distance Brier `0.0064734297442716375`
- Brier delta `0.019495699289079221`
- median event LL delta `0.11153336786189344`
- B0 `0.11705584191021109`
- B1 `0.10853666904712572`
- B2 `0.073016083955376551`
- B3 `0.073951959006454432`
- B4 `0.11371992636546907`
- wins 5 / 5
- newest block win: yes
- C3 gate: PASS
- result fingerprint `b37d5f5f299cf338a2bdf730f114a61b1bea25f3af820c21f81bd1fe13072b08`
- closeout fingerprint `2a9ff681973608f2cdd44371eda8bf4208021610e4f3e74f887a173de1447ede`

No C3 model fitting, tuning, selection, feature change, hyperparameter
search, post-hoc repair, reserve access, authentication, or execution
occurred.

<!-- CHECKPOINT21I_A_FINAL_FIT_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21I-A — Final historical fit implementation freeze

Frozen procedure:
- implementation fingerprint `902bdd1888bb998fd67902cbfe7bf4f82b036ab32bdd41813f4012133cebf023`
- exact rows: 123,520
- exact events: 4,500
- stages H1/H2/H3/C1/C2/C3
- Distance-only model
- deterministic damped Newton
- one free parameter
- no selection/search
- no reserve access
- no network or execution

No final fit was performed during 21I-A.

<!-- CHECKPOINT21I_B_CHAMPION_FINAL_20260818 -->
## Checkpoint 21I-B ? Champion-Final fit

Fit scope:
- H1 + H2 + H3 + C1 + C2 + C3
- 4,500 events
- 123,520 rows
- all labels previously exposed

Result:
- Champion-Final fingerprint `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- closeout fingerprint `1dd79bc396f1dee8afed150930bf5a78ee0581275193545dcde1d579d5b9c43a`
- beta_distance `0.014939489324405949`
- objective `0.050195791036485929`
- iterations 10
- converged true
- beta_momentum null
- one free parameter

Controls:
- specification changed after C3: no
- selection/search: none
- fresh-validation claim: no
- reserve rows used: 0
- reserve outcomes accessed: no
- network requests: 0
- orders: 0

## Checkpoint 21K-A — Strategy Replay v1 freeze validation

Purpose: freeze the first Candidate-E historical entry/exit baseline before viewing strategy P&L.

Evidence-lineage inventory completed before the freeze:
- H1 Distance-candidate rolling-origin OOF artifact: 31,656 rows, 1,070 events, 5,334 markets.
- Deterministic H1 state join reconstructed `state_id` as `{event_ticker}|{market_ticker}|TTC{ttc_target_minutes}|{structural_role}`.
- H1 join result: 31,656 / 31,656 rows matched; 0 missing states; 0 identity mismatches; 0 duplicate frozen states.
- H1 OOF coverage includes all six TTC anchors and all five frozen structural roles.
- H2/H3/C1/C2/C3 frozen prediction artifacts are locally present and together with H1 define 4,070 OOS/OOF events / 118,862 prediction rows.

Strategy predeclaration validation:
- strategy ID: `kxbtcd_candidate_e_strategy_replay_v1`
- fingerprint: `afc1b397c850e8b2a2dfd32d6656e05f4622c59f1596f5b91295e96debb0d046`
- dedicated validator: PASS
- dedicated tests: 9 passed
- full regression: 881 passed, 22 subtests passed
- orders/demo/paper execution: disabled
- historical strategy P&L inspected: no
- new historical execution backfill performed before freeze: no

Interpretation: this checkpoint validates the strategy specification and evidence lineage only. It makes no profitability claim.

## Checkpoint 21K-B1 — Reusable execution archive predeclaration validation

Purpose: freeze the reusable historical execution-data archive contract before collection or strategy scoring.

Observed archive universe:
- H1 OOF: 1,070 events / 5,334 markets / 31,656 rows.
- H2: 750 events / 3,750 markets / 22,354 rows.
- H3: 750 events / 3,750 markets / 22,409 rows.
- C1: 500 events / 2,491 markets / 14,887 rows.
- C2: 500 events / 2,441 markets / 14,007 rows.
- C3: 500 events / 2,470 markets / 13,549 rows.
- aggregate: 4,070 events / 20,236 markets / 118,862 rows.
- cross-stage event overlap: 0.
- cross-stage market overlap: 0.

Frozen identities:
- archive ID: `kxbtcd_candidate_e_reusable_execution_archive.v1`
- archive fingerprint: `4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea`
- allow-list fingerprint: `85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1`

Validation evidence:
- archive predeclaration validator: PASS
- dedicated tests: 9 passed
- full regression: 890 passed, 22 subtests passed
- network collection performed by this checkpoint: no
- strategy P&L inspected: no
- reserve accessed: no
- execution authorized: no

Interpretation: this checkpoint validates collection scope, identity, safety, and reuse rules only. It makes no claim about archive coverage, fill realism, strategy profitability, or execution readiness.

<!-- CHECKPOINT21K_B2_COLLECTOR_EVIDENCE_20260818 -->
## Checkpoint 21K-B2 — collector implementation and smoke evidence

### Offline validation

Initial B2 collector:
- archive predeclaration validator: PASS
- dedicated collector tests: 10 passed
- full regression: 900 passed + 22 subtests

After resume-lineage amendment:
- dedicated collector tests: 13 passed
- final full regression: 903 passed + 22 subtests in 26.41 s

### First five-market smoke attempt

Command scope:
- deterministic `--max-markets 5`
- public/read-only
- 0.10 s request spacing
- no strategy P&L
- no reserve access
- no authentication
- no orders

The first attempt failed closed before the historical-trades request because
the local approved-GET guard omitted `/historical/trades`. This was an
implementation allow-list omission, not a Kalshi HTTP failure. The documented
read-only historical-trades route was added to the guard and regression-tested.

### Successful resumed five-market smoke

Run:
`collect_kxbtcd_candidate_e_execution_archive_20260818T071803469431Z_2c962db2`

Result:
- scope `smoke_5`
- 1 event / 5 markets
- 10 tasks completed in the resumed run
- 8 previously completed tasks reused
- 9 derived CSV files / 544 derived rows
- 293 one-minute candle rows
- 234 public trade rows
- 0 raw error records
- strategy P&L: not calculated
- reserve access: no
- authentication: no
- orders: 0

Candle audit:
- lifecycle expectation: 60 one-minute end periods per sampled market
- observed counts: 58, 58, 58, 60, 59
- all returned candles had two-sided close quotes
- four markets lacked the 18:29 UTC end-period candle
- three of those also lacked the 19:00 UTC close-period candle
- no unexpected/out-of-window candle timestamps
- gaps remain explicit; no imputation was performed

Trade audit:
- one sampled strike had 234 public trades
- four sampled strikes had 0 returned public trades
- all five trade tasks completed through their cursor chains

### Resume-lineage defect and repair

The successful resumed smoke derived rows referenced 2 raw sessions, and both
raw JSONL files existed, but the completed manifest initially inventoried only
the newest run session/file. No raw data was lost; the defect was incomplete
receipt-level cross-run lineage.

The resume index was amended from v1 to v2 to transactionally index contributing
raw sessions, migrate/backfill legacy cached tasks after digest validation, and
require every contributing raw JSONL file during successful finalization.

### End-to-end lineage validation

Validation run:
`collect_kxbtcd_candidate_e_execution_archive_20260818T072801523739Z_6c152eb7`

Result:
- scope `smoke_5`
- 1 task completed
- 17 tasks skipped/reused from resume
- 3 source sessions in completed manifest
- 2 inherited source sessions
- 3 contributing raw JSONL files
- 19 raw records total
- 0 raw error records
- all 3 raw files SHA-256 inventoried by the completed manifest
- 9 derived CSV files / 544 derived rows
- 3 runtime events / 0 runtime errors
- strategy P&L: not calculated
- reserve access: no
- authentication: no
- orders: 0

Conclusion: B2's raw-first, resumable, cross-run-lineage collector path is
validated on a bounded live read-only smoke. This does not establish full
archive completeness or strategy profitability.

<!-- CHECKPOINT21K_B3_BOUNDED_PILOT_EVIDENCE_20260818 -->
## Checkpoint 21K-B3 — 100-market bounded pilot evidence

Primary pilot run:
`collect_kxbtcd_candidate_e_execution_archive_20260818T073532996950Z_c3f5d471`

Scope:
- `smoke_100`
- 20 events
- 100 markets
- H1_OOF deterministic prefix
- 322 tasks completed
- 0 resume skips on first run
- 253 raw API records
- 0 raw errors
- 0 runtime errors
- 9 derived CSV files
- no Strategy-v1 P&L
- no reserve access
- no authentication
- 0 orders

Materialized rows:
- 100 allow-list rows
- 100 market metadata rows
- 20 event metadata rows
- 1 series metadata row
- 10,864 one-minute candle rows
- 1,356 public trade rows
- 0 event fee-change rows
- 0 series fee-change rows
- 100 coverage rows

Trade evidence:
- 14/100 markets had >=1 public trade
- 86/100 had zero returned trades
- 1,356 total trades reconciled exactly
- maximum 292 trades in one market
- all markets used exactly one trade route
- duplicate trade IDs removed: 0

Full-lifecycle candle coverage:
- expected periods: 20,400
- observed periods: 10,864
- missing periods: 9,536
- raw full-lifecycle coverage: 53.2549%
- every returned candle had a two-sided close quote
- 82/100 markets had >=1 missing candle

Long-lifecycle diagnostics:
- no fixed returned-row ceiling was observed
- large-gap markets returned heterogeneous row counts from 453 to 920
- gaps were primarily internal rather than simple leading truncation
- last-55-minute aggregate coverage: 5,031/5,500 = 91.4727%
- last-60-minute aggregate coverage: 5,449/6,000 = 90.8167%
- markets complete in last55: 24/100
- markets complete in last60: 19/100

Exact Strategy-v1 anchor coverage:
- all 6 signal anchors present: 71/100 markets
- all 6 signal+next-minute pairs present: 64/100
- at least 1 usable entry pair: 100/100
- at least 1 T-5..T-1 force-exit candle: 95/100

Signal+next-minute pair availability:
- T-55: 78/100
- T-50: 79/100
- T-45: 81/100
- T-40: 92/100
- T-35: 88/100
- T-30: 94/100

Force-exit availability:
- T-5: 95/100
- T-4: 95/100
- T-3: 95/100
- T-2: 94/100
- T-1: 94/100

Entry-pair distribution:
- 1/6 pairs: 4 markets
- 2/6 pairs: 7
- 3/6 pairs: 4
- 4/6 pairs: 7
- 5/6 pairs: 14
- 6/6 pairs: 64

Event-level exceptions:
- 19/20 sampled events retained at least one usable market at every entry anchor.
- `KXBTCD-25APR2915` had zero usable T-55 market.
- 19/20 sampled events retained at least one force-exit market.
- `KXBTCD-25APR2913` had zero T-5..T-1 force-exit markets and therefore would
  require the frozen settlement fallback if a position existed.

Resume/lineage validation run:
`collect_kxbtcd_candidate_e_execution_archive_20260818T074121445450Z_a4e2cf72`

Result:
- 1 fresh task
- 321 tasks reused from `smoke_100.sqlite`
- 2 source sessions
- 1 inherited source session
- 2 contributing raw JSONL files
- 254 raw records total
- 0 raw errors
- 0 runtime errors
- both raw files SHA-256 inventoried in the completed manifest
- 9 derived CSV files / 12,541 derived rows
- no Strategy-v1 P&L
- no reserve access
- no authentication
- 0 orders

Conclusion:
B3 validates bounded-scale collection, resumability, and cross-run lineage. It also
demonstrates material historical candle sparsity that must be handled fail-closed in
replay rather than repaired by imputation. This is not a profitability result.

<!-- CHECKPOINT21K_B4A_CANDLE_CHUNKING_EXPERIMENT_20260818 -->
## Checkpoint 21K-B4A — full-archive candle-range failure and repair validation

The first Checkpoint 21K-B4 full archive collection stopped fail-closed on:

`/historical/markets/KXBTCD-25AUG0117-T104999.99/candlesticks`

Archived request:
- `start_ts=1753473600`
- `end_ts=1754082000`
- `period_interval=1`
- requested one-minute span: 10,140 periods

Archived Kalshi response:
- HTTP 400 Bad Request
- code `bad_request`
- detail: `requested time range with candlesticks: 10140.000000, max candlesticks: 5000`

Interpretation:
- deterministic collector/API request-window incompatibility;
- not a Candidate-E result;
- not a Strategy-v1 P&L result;
- not authentication failure;
- not a rate-limit failure;
- the failed candle task was not committed to the resume database;
- prior completed `full` tasks remain reusable.

Repair:
- cap each candle request window at 5,000 elapsed one-minute periods;
- overlap exact request boundaries;
- merge by `end_period_ts`;
- fail closed if overlapping normalized candle values disagree;
- preserve raw lineage for every chunk.

Validation:
- focused candle-chunking + collector tests: 16 passed;
- full regression suite: 906 passed, 22 subtests passed;
- no Strategy-v1 P&L calculated;
- protected reserve access: 0;
- no order/demo/real execution introduced.

## Checkpoint 21K-B4B ? full execution archive readiness audit

Result: PASS WITH LIMITATIONS.

Full universe: 4,070 events / 20,236 markets.
Observed candles: 2,418,338 / 4,583,795 expected lifecycle periods (52.7584%).
Returned candles with two-sided closes: 100%.

Exact signal+next market coverage:
T-55 10,009; T-50 18,108; T-45 12,134; T-40 16,752;
T-35 11,025; T-30 15,636.

19,282 markets had at least one usable entry pair.
3,668/4,070 events had at least one usable market at all six anchors.
4,067/4,070 events retained a T-5..T-1 force state.

Activity diagnostic:
zero-trade markets had 81.10% mean last-hour candle density versus 96.45% for
markets with at least one public trade. Density increased monotonically with trade
activity. Nevertheless zero-trade markets retained a +20.526pp alternating
relative-minute availability gap, showing that candle missingness is not a pure
liquidity signal.

No P&L, settlement-outcome access, protected-reserve access, authentication, or
orders occurred.

## E-021L-01 ? Outcome-blind Model-2 feature availability and quality audit

**Purpose:** determine which causal Candidate-E/BTC/Kalshi state variables can be frozen for Entry Model v1 before any Model-2 fitting or Strategy-v1 P&L inspection.

Selected Candidate-E Distance downstream universe:
- H1 OOF: 31,656 rows
- H2: 22,354
- H3: 22,409
- C1: 14,887
- C2: 14,007
- C3: 13,549
- total: 118,862

Normalization result:
- 118,862 / 118,862 canonical states recovered
- 0 conflicting duplicate source rows
- 0 `q_market` mismatches
- exact decision candle: 118,862 / 118,862

Exact-decision-candle availability:
- YES bid OHLC: 100%
- YES ask OHLC: 100%
- volume: 100%
- open interest: 100%
- trade-price OHLC: 5.29%
- previous trade price: 12.76%

Trailing-five-minute public-trade aggregates:
- defined for all 118,862 states
- >=1 public trade: 10,252 states / 8.63%
- zero trades: 108,610 states; treated as valid observed zero

Archive-wide quote/candle quality diagnostic:
- usable candle rows: 2,418,338
- bid > ask violations: 0
- invalid OHLC ranges: 0
- quote-dynamic fields have nonzero variation
- volume and open interest are heavily zero-inflated but observed, not missing

Archive-wide public-trade quality:
- 363,978 public trades
- invalid/nonpositive trade sizes: 0
- taker outcome sides consist only of YES/NO
- block-trade flag is false for all 363,978 trades

Result: PASS for freezing the causal Model-2 v1 feature contract, with trade-price OHLC and block-trade features excluded.

Outcomes were not used for feature selection.
No Model-2 fit was performed.
Strategy-v1 P&L was not calculated.
The protected historical reserve was not accessed.

## E-021L-02 ? Outcome-blind whole-event chronology audit

Purpose:
verify whether the six Candidate-E downstream stages can support a strictly chronological Model-2 development / validation / locked-test split without event overlap.

Result: PASS.

Stage event counts and ranges:

- H1_OOF:
  - 1,070 events
  - 2025-04-28T19:00:00Z through 2025-07-07T14:00:00Z

- H2:
  - 750 events
  - 2025-07-07T15:00:00Z through 2025-08-25T04:00:00Z

- H3:
  - 750 events
  - 2025-08-25T13:00:00Z through 2025-10-12T22:00:00Z

- C1:
  - 500 events
  - 2025-10-16T14:00:00Z through 2025-11-18T03:00:00Z

- C2:
  - 500 events
  - 2025-11-18T04:00:00Z through 2025-12-21T20:00:00Z

- C3:
  - 500 events
  - 2025-12-21T21:00:00Z through 2026-01-22T17:00:00Z

Adjacent-boundary checks:
- H1_OOF -> H2: PASS
- H2 -> H3: PASS
- H3 -> C1: PASS
- C1 -> C2: PASS
- C2 -> C3: PASS

Identity checks:
- unique events: 4,070
- events with multiple stages: 0
- events with multiple close times: 0

Frozen Model-2 evidence-role proposal:
- development: 2,570 events / 76,419 rows
- validation: 1,000 events / 28,894 rows
- locked test: 500 events / 13,549 rows

Outcomes inspected for this audit: NO.
Model-2 fit performed: NO.
Strategy-v1 P&L calculated: NO.
Protected reserve accessed: NO.

## E-021L-03 ? Outcome-blind Model-2 preprocessing feasibility audit

Purpose:
verify that the exact D-021L-02 feature vector is numerically usable under the proposed chronological development folds before freezing Model-2 preprocessing.

Result: PASS.

Development state coverage:
- H1_OOF: 31,656 / 31,656
- H2: 22,354 / 22,354
- H3: 22,409 / 22,409
- total: 76,419 / 76,419

Exact decision candles:
- 76,419 / 76,419

Materialization checks:
- spread mismatches between frozen Candidate-E state and exact candle close: 0
- non-finite feature rows: 0

Fit-feasibility partitions audited:
1. H1_OOF
   - 1,070 events / 31,656 rows
2. H1_OOF + H2
   - 1,820 events / 54,010 rows
3. H1_OOF + H2 + H3
   - 2,570 events / 76,419 rows

All 11 continuous frozen features had finite, nonzero event-equal weighted standard deviation in every audited fit partition.

All six TTC categories were present in every audited fit partition.

All five structural-role categories were present in every audited fit partition.

Frozen Candidate-E probabilities remained strictly between zero and one in every audited fit partition, including very extreme probabilities.

Overall preprocessing feasibility: PASS.

Outcomes inspected for this audit: NO.
Model fitting performed: NO.
Strategy-v1 P&L calculated: NO.
Protected reserve accessed: NO.

## E-021L-04 ? Statistical advancement-gate design freeze

No new outcomes or P&L were opened for this step.

Frozen statistical comparison:
- benchmark = Candidate E
- primary = event-equal binary log loss
- secondary = event-equal Brier

Validation evidence:
- C1+C2
- 1,000 events / 28,894 rows
- five contiguous chronological 200-event blocks

Required validation PASS:
- pooled log-loss improvement
- non-worse pooled Brier
- >=4/5 chronological block wins
- newest-block win
- positive median event-level log-loss delta

If validation passes, final Model-2 fitting scope becomes:
- H1_OOF+H2+H3+C1+C2
- 3,570 events / 105,313 rows
- selected lambda fixed
- no retuning

C3 locked test:
- 500 events / 13,549 rows
- five contiguous chronological 100-event blocks
- identical five-condition gate

Statistical PASS is explicitly separated from economic/trading validation.

Model fitting performed: NO.
Strategy P&L calculated: NO.
Protected reserve accessed: NO.

## E-021L-05 ? KXBTCD historical fee-metadata audit

Purpose:
verify the frozen archive's price structure and fee metadata before defining strategy-neutral Model-2 economic quantities.

Result: PASS.

Market metadata:
- markets: 20,236
- `price_level_structure = linear_cent`: 20,236
- binary markets: 20,236

Event metadata:
- events: 4,070
- fee-type overrides: 0
- fee-multiplier overrides: 0
- historical event fee-change rows: 0

Series metadata:
- ticker: KXBTCD
- fee type: quadratic
- fee multiplier: 1
- historical series fee-change rows: 0

The official standard fee schedule and archive metadata support use of the standard quadratic fee formula for strategy-neutral historical diagnostics.

The audit does not establish account-specific rebates or incentives.

Outcomes inspected for this audit: NO.
Model fitting performed: NO.
Strategy P&L calculated: NO.
Protected reserve accessed: NO.
<!-- E-021M-01_SYNTHETIC_IMPLEMENTATION_VALIDATION_20260819 -->
## E-021M-01 — Synthetic validation of Model-2 preparation/evaluator machinery

Purpose:
validate the deterministic Checkpoint-21M implementation before any real project
development fit is allowed.

Environment:
- isolated container
- Python 3.13.5
- pytest 9.0.2

Result:
- 25 focused tests passed
- Python byte-compilation PASS

Covered implementation properties include:
- event-equal weighting and fit-only scaling;
- exact 21-parameter reference coding;
- deterministic Cholesky/Newton optimization;
- L2 shrinkage including the residual intercept;
- Candidate-E no-clipping behavior;
- exact larger-lambda tie resolution;
- synthetic rolling-origin H1_OOF->H2 / H1_OOF+H2->H3 execution;
- exact one-minute candle feature formulas;
- strict `(t-300s, t]` public-trade aggregation;
- selected trade stage/event identity and exact decision-minute enforcement;
- exact-candle missingness fail-closed behavior;
- outcome-firewall invariance;
- protected/unrecognized stage rejection;
- CSV round-trip-stable scientific fingerprints;
- persisted-output SHA-256 binding;
- independent source-to-feature rematerialization of persisted preparation artifacts;
- tamper rejection.

Evidence boundaries:
- real project outcomes used for this validation: NO
- real Model-2 development fit performed: NO
- Strategy-v1 P&L calculated: NO
- C3 opened for Model-2 evaluation: NO
- protected 4,676-event reserve accessed: NO
- paper/demo/real execution: NO

Interpretation:
this is implementation validation only. It does not show that Model 2 improves
forecasting, has positive expected value, or is profitable. Canonical Windows
Python 3.11 integration tests and a real outcome-blind preparation freeze are
still required before project-data development fitting.
<!-- E-021M-02_REAL_PREPARATION_FAIL_CLOSED_TIMESTAMP_DIAGNOSIS_20260819 -->
## E-021M-02 — First real preparation fail-closed and timestamp diagnosis

Purpose: attempt the first outcome-blind H1_OOF+H2+H3 feature materialization after
canonical implementation tests, while keeping labels/fitting/economics closed.

Pre-attempt canonical Windows validation:
- focused: 25 passed
- full repository: 931 passed + 22 subtests

Result: FAIL CLOSED before output creation.

First failing state:
`KXBTCD-25APR2823|KXBTCD-25APR2823-T93999.99|TTC30|q50`.

Observed source/archive facts:
- decision target: 2025-04-29T02:30:00Z / unix 1745893800
- frozen quote timestamp: 1745893740 / 02:29:00Z
- frozen quote staleness: 60 seconds
- archive allow-list matches: 1
- market archive candles: 58
- exact candle at decision unix: 0
- nearest prior archive candle: 1745893740, exactly the frozen quote timestamp
- nearest later candle: 1745893860, which is future relative to the decision

Interpretation: the archive is not missing the Candidate-E state. The initial 21M
join key was wrong. Candidate E's frozen parent contract permits the latest valid
real quote at/before target with <=60 seconds staleness. D-021M-02 corrects the
implementation to reconstruct that exact frozen quote timestamp while retaining
the scheduled decision time for causal trade aggregation.

Corrected isolated focused validation: 29 passed.

Safety:
- outcomes attached: NO
- Model-2 fit performed: NO
- Strategy-v1 P&L calculated: NO
- C3 opened for Model-2: NO
- protected reserve accessed: NO
- execution: NO
<!-- E-021M-03_REAL_PREPARATION_FREEZE_ACCEPTANCE_20260819 -->
## E-021M-03 — Real outcome-blind development preparation and independent reproduction

Purpose: freeze and independently validate the exact real H1_OOF+H2+H3 Model-2
feature universe before development outcomes are attached or the model is fit.

Canonical Windows evidence after D-021M-02:
- focused Checkpoint-21M tests: 29 passed in 1.27s
- full regression: 935 passed + 22 subtests in 30.75s

Preparation result:
- feature rows: 76,419
- events: 2,570
- H1_OOF: 31,656 rows / 1,070 events
- H2: 22,354 / 750
- H3: 22,409 / 750
- feature fingerprint: `a726785e667dc42cef75a7b1f9c0b42ae81a4906b1d72ff5eb0f58ed5083b2a7`
- event-map fingerprint: `36bd74d8576cf8656a4d4a352330fabd2294c322c5cd91854ed47892fe04a266`
- preparation fingerprint: `2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`
- feature CSV SHA-256: `0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c`
- event-map CSV SHA-256: `fe627d8bf3c91ef77e811a83f75f3a3b0542ba0df755cf34cc78f8d9e617bddd`

Independent validator result: PASS.
- source rematerialization: PASS
- implementation hashes: PASS
- model2_fit_performed=false
- strategy_v1_pnl_calculated=false
- c3_opened_for_model2=false
- protected_reserve_accessed=false

Frozen source SHA-256 values:
- preoutcome: `32ce45e30d2b8c9d57fe68940e4bc791fec76e061ae01b5f07f042f4a9169028`
- H1 predictions: `867a77cbbf034a574983cb6fb301a77614674d3254297f8e15db377d5c34df16`
- H2 predictions: `4aa6efe3c3bdc231fc8289f11fe01e1ad5a65910ae0ea92d2586447fd6b7d3d6`
- H3 predictions: `091affc5ac088aa61db43a5df18f15178bceeea2ee26bd266b61fd059fd08380`
- archive allow-list: `cd80fb8a891c30127f8cc0404a7b525238c3c3d06f2f105825b8541399f3443a`
- archive candles: `fef40a30cb2d61229676a3927873d90cda449c83167ab8dc7226b966b787b73f`
- archive trades: `8af2f184f7181b2cb7cef1873559bcfb96c0121065265172c1505dd671bb59a1`

Frozen implementation SHA-256 values:
- preparation CLI: `cc1c1113c1a4762f0586f283b203882a0cc228ba81f49624f7ba68c60af5169d`
- model/evaluator: `1e56a207e72a96a4425d0c6c6796d9781eac363baef5bb0dab3b3b58daa34a1b`
- materializer: `97344145aed5489638361182df54ad66cf78ff160479bec7cc172ef27dd32916`
- independent validator: `526b389f83fba5cb1bb2843f98fe17e36b660816ecb3e8967515f49b24e228ed`

Interpretation: this establishes deterministic reproducibility and an outcome
firewall for the development inputs. It is not a predictive-performance or
profitability result.

Safety: no outcomes in feature rows, no Model-2 fit, no Strategy-v1 P&L, no C3,
no protected-reserve access, and no paper/demo/real execution.

<!-- E-021M-03_DEVELOPMENT_EVALUATION_IMPLEMENTATION_20260819 -->
## E-021M-03 — Development-evaluation orchestration implementation

**Evidence role:** implementation/synthetic only. No real Model-2 development
outcomes are evaluated by this entry.

Base pre-outcome commit:
`cc91a15ae65954370279025d1afe6c857c8d899b`.

Accepted preparation fingerprint:
`2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`.

Implemented:
- exact H1_OOF/H2/H3 Candidate-E label projection;
- H1 rejected-challenger filtering;
- frozen preparation/source/core hash binding;
- D-021L-04 orchestration and selected-lambda development diagnostics;
- deterministic JSON/CSV result receipt;
- independent deterministic result recomputation;
- synthetic/contract tests.

Canonical Windows test evidence is pending. No C1/C2/C3, protected reserve,
Strategy-v1 P&L, or execution access occurred in this implementation step.

<!-- E-021M-04_FIRST_REAL_DEVELOPMENT_ATTEMPT_NUMERICAL_GUARD_FAILURE_20260819 -->
## E-021M-04 — First real Model-2 development attempt: numerical guard FAIL, no accepted result

**Evidence role:** exposed development execution / implementation diagnosis only.

The first real evaluation used the frozen 76,419-row / 2,570-event feature universe
and the already-existing H1_OOF/H2/H3 Candidate-E outcome sources. Therefore those
development outcomes are now exposed for Model-2 research.

The run did not complete. It failed in the final full-development fit while
constructing event-equal weights:
`CandidateEEntryModelV1Error: event-equal weights do not sum to 1`.

Targeted diagnostic on the exact frozen feature rows:
- rows: 76,419;
- events: 2,570;
- ordinary sum: `1.000000000001317169`;
- ordinary absolute error: `1.317168596415285720e-12`;
- current tolerance: `1e-12`;
- `math.fsum`: `1.000000000000000000`;
- `math.fsum` absolute error: `0`.

Interpretation: false numerical integrity failure from accumulation order, not an
invalid scientific weight vector. No persisted development evaluation/receipt was
reached by the runner, and no development metric or selected lambda from this failed
attempt is accepted or used to alter the model specification.

Repair under D-021M-05 is limited to accurate summation in the invariant check plus
a real-scale regression test. C1/C2, C3, protected reserve, Strategy-v1 P&L, and
execution were not opened by this failure analysis.

<!-- E-021M-05_POST_REPAIR_CORE_HASH_BINDING_FAILURE_20260819 -->
## E-021M-05 — Post-repair development retry: core-hash binding FAIL, no result

**Evidence role:** exposed-development implementation diagnosis only.

After D-021M-05 was canonically validated (`942 passed + 22 subtests`) and pushed
at commit `80afd386c805f80505bc33174ad7b8ff8cdf1c70`, the unchanged real
development-evaluation command was attempted again.

The command failed closed in `validate_preparation_binding()` before a development
result was produced because the original preparation receipt still bound the
pre-repair core implementation hash.

Diagnostic:
- original frozen core hash:
  `1e56a207e72a96a4425d0c6c6796d9781eac363baef5bb0dab3b3b58daa34a1b`;
- current D-021M-05 repaired core hash:
  `ce54846f85f3d338bc0f3aadd64d8cc8b9828c0c2ac2b5454f97771ec1a89ee1`;
- equality: false;
- output directory: exists;
- output item count: 0.

No development metric, selected lambda, or receipt is accepted from this failed
attempt. Under D-021M-06 the original freeze will remain unchanged while the
evaluator separately requires the exact repaired current core hash.

C1/C2, C3, protected reserve, Strategy-v1 P&L, and execution were not opened.

<!-- E-021M-06_VALIDATED_DEVELOPMENT_RESULT_20260819 -->
## E-021M-06 — Candidate-E Entry Model v1 development evaluation: validated

**Evidence role:** exposed development selection only.

The repaired and hash-amended `development_evaluation_v2` run completed on:
- 76,419 feature rows;
- 2,570 events;
- H1_OOF + H2 + H3 only.

Independent validator result: PASS with deterministic recomputation.

Selected lambda: `0.01`.

Pooled H2+H3 selected-lambda diagnostics:
- Model-2 event-equal log loss: `0.03736587903471904`;
- Candidate-E event-equal log loss: `0.03740705507861643`;
- Candidate-E-minus-Model-2 delta: `+0.0000411760438973896`;
- Model-2 Brier: `0.010091977884008856`;
- Candidate-E Brier: `0.010095108827365279`;
- Candidate-E-minus-Model-2 Brier delta: `+0.0000031309433564229855`;
- median event log-loss delta: `+0.00012469097768141543`.

H2 log-loss delta was positive (`+0.00010360998900234286`), while H3 was slightly
negative (`-0.000021257901207466512`). This is a very small aggregate development
gain and is not interpreted as robust generalization.

Evaluation fingerprint:
`78de7bf612830c7fbbeb14b56a34bd1a582f8e69738672d420314b1c4ff79aac`.

Receipt SHA-256:
`14c75f8f0ccbef081e841fd75e6adab500b459e1fcdcee3d002c328c1bf11523`.

Development-freeze fingerprint:
`a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e`.

Safety remained:
C1/C2 unopened, C3 unopened, protected reserve untouched, Strategy-v1 P&L not
calculated, execution disabled.

<!-- E-021M-07_C1C2_VALIDATION_PREPARATION -->
## E-021M-07 — C1+C2 outcome-blind Model-2 validation preparation

Prepared 1,000 events / 28,894 rows under the unchanged Model-2 feature contract.
C1 used Champion-R0; C2 used Champion-R1. Historical prediction CSV rows were
not read. No Model-2 validation outcome or score was read/calculated.

Feature fingerprint: `d5d70331d1ccf6ce823a9820bfefc9267db6f84b13bd0040133dfe759ffae228`.
Event-map fingerprint: `682c3007e2c360d10aada786e83050516990c36c1de87d6988b70c49c38f4199`.
Validation-preparation fingerprint: `25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22`.

C3, protected reserve, Strategy-v1 P&L, and execution remained closed.

<!-- E-021M-08_VALIDATION_EVALUATOR_IMPLEMENTATION_FREEZE -->
## E-021M-08 — C1+C2 Model-2 validation evaluator implementation freeze

The D-021L-05 evaluator implementation has been frozen before Model-2 reads any
C1/C2 outcome row.

Validation implementation fingerprint:
`8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`.

Inputs are predeclared but not opened during this freeze:
- C1 outcome SHA-256:
  `badefb7087de6b07a5c968b78564858e7e9c060652836aba7f366de0788a259b`;
- C2 outcome SHA-256:
  `6a898266ce961b3d812ac1e6c5b430a01e9449bb41d06a42e61e69d2fccf38e6`.

No validation score was calculated. C3, protected reserve, Strategy-v1 P&L, and
execution remain closed.

<!-- E-021M-09_VALIDATION_FIRST_ATTEMPT_TRANSPORT_FAILURE -->
## E-021M-09 — First Model-2 C1+C2 validation attempt opened outcomes then failed before scoring

The frozen evaluator created its attempt journal before reading C1/C2 outcome rows,
as designed. Therefore C1+C2 are permanently exposed to Model-2 research.

The run then failed before any score/result was produced because the implementation
looked for `historical_prediction_csv_rows_read` at the wrong JSON nesting level.

Observed state at failure:
- attempt status: `OUTCOMES_OPENED_FOR_MODEL2_VALIDATION`;
- result directory existed: false;
- validation scores calculated: false;
- C3/reserve/Strategy-v1 P&L/execution: untouched.

This is an orchestration/validation-schema failure, not evidence that Model-2
passed or failed the statistical gate.

Resume-repair fingerprint:
`fee1063a637c99749e47d67bbb553a480d3e72037be1cb9015b26b67f2275aed`.

<!-- E-021M-10_MODEL2_C1C2_VALIDATION_RESULT -->
## E-021M-10 — Candidate-E Entry Model v1 C1+C2 validation

Scope: 1,000 C1+C2 events / 28,894 rows.

Candidate E:
- event-equal log loss `0.0518981214127418`;
- event-equal Brier `0.015171565220600291`.

Model-2:
- event-equal log loss `0.051982434232278454`;
- event-equal Brier `0.01519915292120419`.

Candidate-E-minus-Model2:
- log loss `-8.431281953665687e-05`;
- Brier `-2.7587700603898604e-05`.

Median event log-loss delta:
`2.3452135462756008e-05`.

Chronological block wins: `1/5`.
Newest block win: `False`.

Frozen validation gate: **FAIL**.
Independent artifact validation: **PASS**.

Evaluation fingerprint: `15a6557736204ca58039906434f8b7e83bca719f14cd0a3b4c9b9094e42ce033`.
Receipt fingerprint: `5e37a7abab6065414be00761ac79e09e853e587ab3ccf153e9f5a74081b11e2a`.
Result closeout fingerprint: `f27dba7fc5fcf9726a3699b8e611646d0d93b77a3dfdb8050048767a97c36ff7`.

C3/reserve/Strategy-v1 P&L/execution remained untouched.

<!-- CHECKPOINT21N_A_OPPORTUNITY_AUDIT_RESULT_20260830 -->
## 2026-08-30 — 21N-A outcome-independent Strategy-v1 opportunity audit

Run directory:
`data/analysis/kxbtcd_candidate_e_quoted_entry_hold_v1_opportunity_audit/20260830T081928Z`

Audit fingerprint:
`7175175f11bb2714d4bbfc9dc59d9d23d7be721fa0295d7ed664d598a1036ae0`

Scope:
- H1_OOF + H2 + H3
- 2,570 events
- 76,419 Candidate-E probability rows
- 152,838 side states

Entry counts:
- >=0c: 820 (31.91%)
- >=1c: 542 (21.09%)
- >=2c: 306 (11.91%)
- >=3c: 159 (6.19%)
- >=5c: 33 (1.28%)

Mean selected predicted post-fee edge:
- 0c: 0.013846474688786194
- 1c: 0.021990790904102192
- 2c: 0.031012173501541056
- 3c: 0.04004151651833997
- 5c: 0.06149150949214755

The audit used no settlement outcomes and calculated no realized P&L.
No threshold winner was selected. C1/C2/C3/reserve economics remained closed.

Interpretation: opportunity frequency is sufficient to justify a separately frozen
historical economic evaluation. Later-stage opportunity frequency was materially
higher at stronger thresholds, so chronological stability is required in 21N-B.

<!-- CHECKPOINT21N_B_EXPERIMENT_PREDECLARATION_20260830 -->
## 2026-08-30 — 21N-B Strategy-v1 development economic evaluation predeclaration

Predeclaration fingerprint:
`692b7239067b3024db908fc0e0809f33f900f685faec97c45743195e19d364e5`

The development P&L evaluator is to be implemented/tested/committed before real
Strategy-v1 P&L is opened. No economic result exists at this entry.

<!-- CHECKPOINT21N_C_DEVELOPMENT_RESULT_EXPERIMENT_20260830 -->
## 2026-08-30 — Checkpoint 21N-C Strategy-v1 development economics

Frozen evaluation fingerprint: `8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc`.

Result: `FAIL_NO_THRESHOLD`.

Threshold summary (mean net P&L/event, abstentions=0):
- 0c: base -0.004836575875486381322957198444; +1c -0.007972762645914396887159533074; 2/5 positive blocks.
- 1c: base -0.0008132295719844357976653696498; +1c -0.00286381322957198443579766537; 1/5 positive blocks.
- 2c: base -0.000381322957198443579766536965; +1c -0.001552529182879377431906614786; 2/5 positive blocks.
- 3c: base +0.001027237354085603112840466926; +1c +0.0004124513618677042801556420233; 4/5 positive blocks; B4 negative; H3 negative; gate FAIL.
- 5c: diagnostic-only; base -0.0009066147859922178988326848249; +1c -0.001031128404669260700389105058; 2/5 positive blocks.

3c detail: 159 trades, base total +$2.64, +1c total +$1.06, B4 total -$2.50, H3 total -$0.63, +2c pooled total -$0.46. The strategy family therefore does not advance to C1+C2 confirmation.

Safety: C1+C2 Strategy-v1 P&L unopened; C3 unopened for this work; protected reserve untouched; no network access; no paper/demo/real execution; no orders.

<!-- CHECKPOINT21N_C_VALIDATOR_REPAIR_20260830 -->
### 21N-C validator representation repair

The first post-freeze standalone validation stopped on a representation mismatch only: the canonical evaluation encodes no selected threshold as `""`, while the closeout config uses `null`. The validator was repaired to accept exactly those two no-selection encodings and reject all threshold values. No result artifact, evaluation fingerprint, P&L, gate, or evidence boundary changed.

<!-- CHECKPOINT21N_D_FAILURE_ANALYSIS_DESIGN_20260830 -->
## Checkpoint 21N-D — Strategy-v1 failure-analysis predeclaration

**Status:** analyzer design frozen; real diagnostic not yet run.

Parent result: 21N-C `FAIL_NO_THRESHOLD`, evaluation
`8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc`.

Primary diagnostic population is fixed at the 159 3c/displayed-quote entries.
The analysis will decompose calibration, price, fees, realized P&L, fixed
regime slices, and loss-tail concentration. It will not optimize a replacement
strategy.

Predeclaration fingerprint: `33fb68841a174d50971d40aefae73ab564f96adcb8aefafcf5e86aa16d21bc8b`.

No new economic outcomes are opened by this design because H1_OOF/H2/H3
Strategy-v1 outcomes are already exposed. C1+C2 strategy economics, C3,
protected reserve, and execution remain unopened/prohibited.

<!-- CHECKPOINT21N_E_FAILURE_RESULT_AND_SUCCESSOR_DIRECTION_20260830 -->
## Checkpoint 21N-E — failure-analysis result

Analysis fingerprint `e9b88ded9fe1db1f89e234ad626023c67038bbea84ae35863b817c3858f4a3ef`. H2 P&L +2.68 vs H3 -0.63; B3 +2.47 vs B4 -2.50. Mean prices were broadly stable while selected-side calibration deteriorated materially.

Research preselection: deterministic reliability-adjusted entry first; learned entry/meta-model deferred. No successor scoring/fitting occurred.

<!-- CHECKPOINT21N_F_RELIABILITY_SHRINKAGE_DESIGN_20260830 -->
## Checkpoint 21N-F — Strategy-v2 predeclaration

**Status:** design frozen; real opportunity audit not yet run.

The experiment tests whether conservative shrinkage of Candidate E toward the
Kalshi midpoint materially changes entry decisions before any new P&L is opened.

Candidate alphas: 0.25, 0.50, 0.75. Alpha 1 is reference only.
No outcome labels or realized P&L are authorized in this audit.

Continuation requires both minimum opportunity coverage and at least 10% decision
change versus alpha=1.

Predeclaration fingerprint: `b3fd3a3c71c5750604ef4e6eddd23043a75952d2c06a48cbb39ae6ef1066bd50`.

<!-- CHECKPOINT21N_G_SHRINKAGE_ECONOMICS_20260831 -->
## Checkpoint 21N-G — opportunity result freeze and economics predeclaration

21N-F audit fingerprint: `b0971d51ac76fc26402dfbab49fde85167cb0bb4153069b80d1db2dbaccdcf20`.

Outcome-independent opportunity counts:
- .25: 15 (3/6/6 H1/H2/H3), sample-ineligible;
- .50: 276 (75/102/99), 82.68% decision change vs alpha 1;
- .75: 591 (203/191/197), 46.83% decision change vs alpha 1;
- 1.00: 820, exact Strategy-v1 reference.

No settlement outcomes or P&L were used to choose .50/.75 eligibility.

Frozen next experiment scores only .50 and .75 under the same one-contract
hold-to-settlement quote-screening accounting and +0/+1/+2/+3c stress policy.
Development winner selection is predeclared before opening outcomes.

Economics fingerprint: `139435ffb43d51d09afa4154aeba2fe9c22cb82b5b7edd435516d4ab71e2c55f`.

<!-- CHECKPOINT21N_H_CONDITIONAL_ALPHA_ARCHITECTURE_20260831 -->
## Checkpoint 21N-H — Strategy-v2 result freeze

Canonical Strategy-v2 development evaluation:
`97ccad587cbfd32c9a390e91800b52da91f5b53e1a273cbecca39b802ab51e21`.

Alpha .50:
276 entries; +$4.75 base; +$2.02 +1c; H3 +$3.02; B4 positive; 3/5 positive
base blocks; FAIL only the frozen 4/5 block-stability condition.

Alpha .75:
591 entries; -$0.29 base; -$6.05 +1c; H3 -$2.43; B4 negative; 2/5 positive
blocks; FAIL.

Final status: `FAIL_NO_ALPHA`.

Accepted next hypothesis: state-conditional alpha between market midpoint and
frozen Candidate E. No fit or new outcome scoring performed in this checkpoint.

Result closeout fingerprint: `02b8aab23161419abd1cdf02c79072f070067ed28f16ef186959e6fc5b3f5ee4`.
Architecture fingerprint: `bb7ebb7b12a9b817465e9e522d65b2f5a129f9e5aaa12a1c8ac6e5fd666a6742`.

<!-- CHECKPOINT21N_I_CONDITIONAL_ALPHA_EXACT_PREDECLARATION_20260831 -->
## Checkpoint 21N-I — conditional-alpha v1 exact predeclaration

Design-only checkpoint. No conditional-alpha model was fit and no outcome was
scored.

Frozen candidate: `kxbtcd_candidate_e_conditional_alpha_reliability.v1`.

The baseline starts from alpha .50 because all five gamma coefficients initialize
at zero. Training will later be allowed to produce a distinct continuous alpha
for each state using exactly four causal features.

A key anti-leakage refinement is frozen: learned-model development economics must
use only rolling-origin H2/H3 predictions (1,500 score events), not a model refit
on all H1/H2/H3 and rescored in-sample. The 1,500 events are split into five
contiguous 300-event economic blocks.

Historical probability supervision is cross-fitted using existing OOF/OOS
Candidate-E stage predictions. Champion-Final is not regenerated in-sample.

C1+C2 conditional-alpha access: no. C3 access: no. Reserve: sealed. Network,
orders, paper/demo/live execution: none.

Predeclaration fingerprint: `742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`.

<!-- CHECKPOINT21N_J_A_CONDITIONAL_ALPHA_IMPLEMENTATION_20260831 -->
## Checkpoint 21N-J-A — implementation-only preparation

No empirical conditional-alpha experiment is run in this checkpoint.

Implementation under test:
- predeclaration `742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`;
- implementation `566f085ef78e8045a75a1dc3781255a2dcae30f23d04ba317ab56e87ac18f5a6`.

Only synthetic/unit evidence is permitted before safe closeout. Real H1/H2/H3
outcomes are not attached and no project-data gamma fit, lambda selection, or
strategy P&L is performed.

The next empirical artifact, after J-A closeout, is outcome-blind row
materialization in 21N-J-B.

<!-- CHECKPOINT21N_J_B_CONDITIONAL_ALPHA_PREPARATION_20260831 -->
## Checkpoint 21N-J-B — outcome-blind preparation reproducibility result

Result: **PASS — deterministic preparation reproduced independently**.

- events / rows: 2,570 / 76,419
- feature fingerprint: `590ab13567821839fb0d404ed4813d328fc4e68ee1a61fd39038d3f8624a42fe`
- output SHA-256: `268c756f82f6be2b53f5fee1f212ad0ecd1d02459547861cc5c3b3623357472f`
- preparation fingerprint: `a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46`
- independent rematerialization: PASS
- settlement outcomes used: 0
- real gamma fits: 0
- lambda selections: 0
- conditional-alpha P&L evaluations: 0

Interpretation: the frozen feature projection is reproducible. No forecasting or
economic performance conclusion is supported by this checkpoint.

<!-- CHECKPOINT21N_K_CONDITIONAL_ALPHA_DEVELOPMENT_EVALUATOR_20260831 -->
## Checkpoint 21N-K — evaluator implementation only

No scientific conditional-alpha result was opened.

- implementation fingerprint: `02530cdd8ba58b45cde85c0ba40f681355ce5b14c4a3ad53ee5f1072fff156a8`
- real project outcomes read: 0
- real gamma fits: 0
- real lambda selections: 0
- real probability gates: 0
- real conditional-alpha P&L evaluations: 0
- C1+C2/C3/reserve access: 0
- execution/orders: 0

This checkpoint freezes experiment mechanics; it is not performance evidence.

<!-- CHECKPOINT21N_L_CONDITIONAL_ALPHA_FAILURE_RECORDING_REPAIR_20260831 -->
## 21N-L first real conditional-alpha H-development attempt

Outcome-exposed development attempt reached the frozen fitter.

- lambda 0.001 / fold 1: converged, 40 iterations
- lambda 0.001 / fold 2: `FAIL`
- error: `BFGS positive-curvature requirement y^T s > 1e-12 failed`
- partial persisted artifacts: 0
- lambda selection: not performed
- probability gate: not performed
- conditional-alpha P&L: not calculated
- full H-development fit: not performed
- C1+C2/C3/reserve/execution: untouched

Scientific status is optimizer-contract failure; canonical persistence follows
only after the recordkeeping repair is safely closed.

<!-- CHECKPOINT21N_M_A_CONDITIONAL_ALPHA_V2_PREDECLARATION_20260831 -->
## 21N-M-A — post-v1 optimizer diagnostics and v2 predeclaration

Purpose: isolate the numerical failure mechanism without scoring conditional-alpha predictive/economic performance.

Evidence:
- v1 hard case lambda .001 / Fold2: BFGS failed at iteration 31 with `y^T s=7.506486991135465e-13` and gradient/tolerance `132.3469`;
- skip-small-curvature: FAIL_MAX_ITER, 500 iterations / 470 skips;
- reset inverse Hessian to identity: FAIL_MAX_ITER, 500 / 470 resets;
- exploratory nonlinear-CG path: reported beta 0 and behaved as slow steepest descent, FAIL_MAX_ITER;
- analytic gradient finite-difference check: PASS;
- exact analytic Hessian finite-difference check: PASS, symmetry error 0; Cholesky PASS at origin and near v1 failure;
- damped Newton hard case: PASS in 8 iterations;
- full Newton numerical matrix: 10/10 PASS, max 9 iterations, one fit required one half-step backtrack.

No lambda selected; no H2/H3 prediction metrics, probability gate, conditional-alpha P&L, C1/C2/C3 score, reserve access, or execution.

v2 predeclaration fingerprint: `6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8`.

<!-- CHECKPOINT21N_M_B_CONDITIONAL_ALPHA_V2_IMPLEMENTATION_20260831 -->
## 21N-M-B conditional-alpha v2 implementation freeze

Engineering implementation only.

- scientific model/objective change: none
- optimizer change: BFGS -> exact-Hessian damped Newton
- linear solver: deterministic dense Cholesky
- Hessian jitter/loading/pseudoinverse/fallback: none
- implementation fingerprint: `459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd`
- real H fit: not performed
- lambda selection: not performed
- probability gate: not performed
- conditional-alpha P&L: not calculated
- C1/C2/C3/reserve/execution: untouched

<!-- CHECKPOINT21N_M_C_CONDITIONAL_ALPHA_V2_EVALUATOR_20260831 -->
## 21N-M-C v2 development evaluator implementation

Implementation only.

- evaluator fingerprint: `bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`
- parent v2 Newton fingerprint: `459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd`
- prepared H universe: inherited exact 2,570 events / 76,419 rows
- H label hashes: unchanged
- formal v2 fit: not run
- lambda selection: not run
- probability gate: not run
- conditional-alpha economics: not run
- C1/C2/C3/reserve/execution: untouched

<!-- CHECKPOINT21N_M_C_R1_TEST_HARNESS_REPAIR_20260831 -->
### 21N-M-C focused-test failure and repair

Initial implementation validator PASS, then focused tests: 2 failed / 3 passed. Root causes were synthetic zero-variance `spread_t` and a frozen exception masking the original failure with `FrozenInstanceError`. No real H data were fit or scored. Repair frozen under evaluator fingerprint `bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`.

<!-- CHECKPOINT21N_M_C_R2_SYNTHETIC_ORCHESTRATION_TEST_REPAIR_20260831 -->
### 21N-M-C-R2 focused-test diagnosis

Observed: synthetic lambda .001 / Fold1 produced
`Newton Hessian is not positive definite; Cholesky failed`.

Interpretation: expected fail-closed numerical behavior on an arbitrary synthetic
fixture, not evidence about the formal H run.

Repair scope: test only. No runtime source, optimizer rule, lambda grid, gate,
evidence role, probability metric, or economics changed. Formal H run remains 0.

<!-- CHECKPOINT21N_N_A_ALPHA_ENTRY_DIAGNOSTIC_PREDECLARATION_20260831 -->
## Formal conditional-alpha v2 H-development result

Canonical run output directory supplied locally:
`data/analysis/kxbtcd_candidate_e_conditional_alpha_reliability_v2_development/20260831T104032Z`

Result:
- overall status: `FAIL_PROBABILITY_GATE`
- selected lambda: `0.001`
- evaluation fingerprint: `fa1f6f34ec830ea6c2520a1513f27c3ca1f0d69bf2ddc73e1c90660abfc3efe0`
- receipt fingerprint: `cafcae196ccaa7f352e3685a9d3132e2d0d5356bb5f041c9035adc27db8d90eb`
- result validator: PASS
- conditional-alpha pooled LL: `0.0399305936385185`
- Candidate-E pooled LL: `0.037407055078616434`
- conditional-alpha pooled Brier: `0.01010785922741806`
- Candidate-E pooled Brier: `0.010095108827365279`
- H2 conditional-alpha LL: `0.03854944010550837`
- H2 Candidate-E LL: `0.03589354612419675`
- H3 conditional-alpha LL: `0.04131174717152863`
- H3 Candidate-E LL: `0.03892056403303612`

The probability gate failed specifically against Candidate E on pooled log loss
and pooled Brier. Economics did not run. No C evidence or reserve was accessed.

The alpha-entry diagnostic is predeclared but has not run; no entry P&L from this
new diagnostic has been inspected.

<!-- CHECKPOINT21N_N_B_ALPHA_ENTRY_DIAGNOSTIC_IMPLEMENTATION_20260831 -->
## 21N-N-B implementation evidence

Implementation only. Synthetic tests exercise Candidate-E-only selection,
first-anchor behavior, outcome-blind quartiles, deterministic remainder
assignment, +1c fee recomputation, Spearman ranking, and the closeout lock.

No real H2/H3 diagnostic P&L has been calculated in 21N-N-B.
No threshold search, C evidence, reserve access, network access, or execution.

<!-- CHECKPOINT21N_N_C_A_INCREMENTAL_ALPHA_SCORE_PREDECLARATION_20260831 -->
## Validated alpha-entry exploratory result

Result validation: PASS.

- triage: `PROMISING_EXPLORATORY_SIGNAL`
- result fingerprint: `54d2a3588c1e06d4a6cd79234b91c59e4aafecff95e33a7a218e2fac85811d3b`
- receipt fingerprint: `513a27890e5921f7d95b6abd2ddb89bcc5b10e82386124fde050dc44e59a9845`
- Candidate-E qualifying entries: 512
- pooled all-entry base P&L/entry: -0.01765625
- pooled all-entry +1c P&L/entry: -0.027421875
- pooled Spearman alpha vs base P&L: 0.2162067809028479
- Q1 base P&L/entry: -0.052734375
- Q4 base P&L/entry: +0.0090625
- Q4 +1c P&L/entry: -0.000703125
- Q4-Q1 base contrast: +0.061796875
- Q4-Q1 +1c contrast: +0.061953125

Q4 was base-positive in H2 and H3, but alpha was not monotonically ordered across
Q1-Q4 and mean quoted Candidate-E edge increased with alpha. Therefore this
result motivates, but does not answer, the incremental-value question.

No threshold search, C3 access, reserve access, or execution occurred.

<!-- CHECKPOINT21N_N_C_B_INCREMENTAL_ALPHA_SCORE_IMPLEMENTATION_20260831 -->
## 21N-N-C-B implementation evidence

Implementation only.

Synthetic tests cover:
- beta=0 exact edge-only ordering;
- positive beta changing ranking through alpha;
- outcome/P&L-blind selection invariance;
- population-standard-deviation scaling;
- +1c beta-selection metric with smaller-beta tie-break;
- strict incremental-alpha gate;
- closeout lock.

No real incremental-score H2/H3 P&L was calculated.
No coverage/threshold search, C evidence, reserve access, network access, or execution.

<!-- CHECKPOINT21N_N_C_RESULT_CLOSEOUT_20260831 -->
## Incremental-alpha entry-score diagnostic — validated FAIL

Result fingerprint: `df58a6b8b24a35f059e046025d528c02490f2efc70e10c634b0edce1a44212db`.
Receipt fingerprint: `3ff1ed184b014a15819c499b698e66425012966af28685b6e0b2b167999870fd`.
Selected beta: `0.5`.
Status: `NO_INCREMENTAL_ALPHA_SIGNAL`.

| beta | entries | mean edge | mean alpha | pooled base P&L/entry | pooled +1c P&L/entry | H2 base | H3 base |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | 128 | 0.0359081517159741 | 0.8799168473122904 | -0.014453125 | -0.024296875 | -0.01507692307692307692307692308 | -0.01380952380952380952380952381 |
| 0.25 | 128 | 0.03566017301525219 | 0.8824417835634382 | -0.014140625 | -0.02390625 | -0.006086956521739130434782608696 | -0.02355932203389830508474576271 |
| 0.5 | 128 | 0.03518524090844749 | 0.8839432917847794 | -0.013828125 | -0.023515625 | -0.0056 | -0.02547169811320754716981132075 |
| 1.0 | 128 | 0.03216173515704316 | 0.8882159356991759 | -0.03234375 | -0.041953125 | -0.01088607594936708860759493671 | -0.06693877551020408163265306122 |
| 2.0 | 128 | 0.029069171834281975 | 0.8907580204017204 | -0.024921875 | -0.034609375 | -0.01559523809523809523809523810 | -0.04272727272727272727272727273 |

Frozen gate:
- selected beta > 0: PASS
- pooled base > edge-only: PASS
- pooled +1c > edge-only: PASS
- H2 base > edge-only: PASS
- H3 base > edge-only: FAIL
- selected pooled base > 0: FAIL
- selected pooled +1c > 0: FAIL

Interpretation: alpha did not demonstrate incremental economic value strong
enough to justify inclusion. Edge-only was also negative, so no simple
largest-edge strategy is accepted from this test.

No coverage/threshold search, C evidence, reserve access, network access, or
execution occurred.

<!-- EXP-021N-O_PREDEXON_SOURCE_QUALIFICATION_20260901 -->
## EXP-021N-O — Predexon KXBTCD historical microstructure source qualification

**Question:** can the already-purchased Predexon 2026-07-10 KXBTCD delta shard
support deterministic fail-closed book replay?

**Scope:** source/replay qualification only. No strategy fit, threshold search,
new P&L evaluation, C1/C2/C3/reserve access, paper broker, demo execution, or
real execution.

**Owned shard:** 5,644,964 rows / 35,648,337 compressed bytes / 623 KXBTCD
contracts / 4 hourly events. Paid shard SHA-256:
`43E9C5D99FB4001B866AE3E60021C8C10123DC1FB6248DF96084446FACE68509`.

**Free seed census:** 623/623 contract streams had at least one snapshot.

**Frozen stratified sample:** 20 contracts, five per event, selected before replay
quality inspection.

**Result:**
- adjacent pairs: 8,273;
- exact pairs: 8,210;
- failed/hard-boundary pairs: 63;
- exact pair rate: 99.2385%;
- verified-time diagnostic: 88.4224%.

By event:
- `KXBTCD-26JUL1013`: 99.379% exact, 74.607% verified time, 32 failed,
  largest excluded gap 33.255m, longest verified segment 47.821m;
- `KXBTCD-26JUL1014`: 98.744% exact, 98.862% verified time, 10 failed,
  largest excluded gap 0.775m, longest verified segment 41.196m;
- `KXBTCD-26JUL1015`: 98.739% exact, 80.434% verified time, 11 failed,
  largest excluded gap 15.379m, longest verified segment 48.740m;
- `KXBTCD-26JUL1016`: 99.309% exact, 98.024% verified time, 10 failed,
  largest excluded gap 2.022m, longest verified segment 54.886m.

**Sequence diagnostic:** on worst inspected contract
`KXBTCD-26JUL1013-T64099.99`, 585/585 `live_early -> websocket` sequence-decrease
pairs reconstructed exactly. Sequence decrease is therefore not authoritative.

**Accepted conclusion:** PASS for exploratory/development historical replay under
reconciliation-authoritative segment masking. These data are not fresh strategy
validation evidence and the 623 contracts are not independent events.

**Implementation validation:** 8 focused replay tests PASS; 1121 full-suite tests
+ 22 subtests PASS; source registry PASS with 23 sources / 17 validated / 0
unresolved.

<!-- CHECKPOINT21N_P_REPLAY_CLOSEOUT_20260901 -->
## 2026-09-01 — Predexon free backfill and full-ladder replay audit

Free sub-cent backfill:
- requested tickers: 623;
- completed tickers: 623;
- pages: 679;
- paid purchases: 0;
- outcomes accessed: 0;
- strategy P&L: not run.

Paid-shard diagnostic:
- rows: 5,644,964;
- unique tickers: 623;
- global timestamp reversals: 619;
- per-ticker order violations: 0;
- ticker blocks: 623;
- ticker reentries: 0;
- event blocks: 4.

Three-ticker replay smoke:
- paid deltas: 620,668;
- snapshots: 12,985;
- pairs: 12,982;
- exact: 12,941;
- failed: 41;
- exact-pair rate: 99.684178%;
- verified time: 67.807686%.

The first ticker exactly reproduced the prior canonical audit:
- `KXBTCD-26JUL1013-T64099.99`;
- snapshots 4,398;
- pairs 4,397;
- exact 4,376;
- failed 21;
- verified time 31.8733%.

Full 623-contract replay:
- independent events: 4;
- tickers: 623;
- paid deltas: 5,644,964;
- snapshots: 269,441;
- adjacent pairs: 268,818;
- exact pairs: 266,034;
- failed pairs: 2,784;
- exact-pair rate: 98.964355%;
- verified time: 80.088503%;
- network requests: 0;
- paid purchases: 0;
- outcomes accessed: 0;
- strategy P&L: not run.

By event:
- 1013: 78 tickers, 39,551 pairs, 39,251 exact, 300 failed, 70.5961% verified time;
- 1014: 188 tickers, 89,221 pairs, 88,297 exact, 924 failed, 77.5552% verified time;
- 1015: 188 tickers, 76,482 pairs, 75,627 exact, 855 failed, 88.1905% verified time;
- 1016: 169 tickers, 63,564 pairs, 62,859 exact, 705 failed, 77.6139% verified time.

Frozen Candidate-E exact-anchor coverage diagnostic:
- possible ticker-at-anchor states: 3,738;
- eligible states: 2,304;
- eligibility: 61.64%.

By event:
- 1013: 55m 9/78, 50m 46/78, 45m 51/78, 40m 42/78, 35m 40/78, 30m 42/78;
- 1014: 55m 23/188, 50m 142/188, 45m 94/188, 40m 86/188, 35m 104/188, 30m 131/188;
- 1015: 55m 136/188, 50m 148/188, 45m 141/188, 40m 156/188, 35m 156/188, 30m 164/188;
- 1016: 55m 91/169, 50m 89/169, 45m 102/169, 40m 99/169, 35m 101/169, 30m 111/169.

No outcomes or P&L were used in these source-engineering decisions.

<!-- CHECKPOINT21N_Q_EXECUTABLE_CONVERGENCE_LIQUIDATION_PREDECLARATION_20260901 -->
## 2026-09-01 — Checkpoint 21N-Q outcome-blind predeclaration

Strategy: `kxbtcd_candidate_e_executable_convergence_liquidation_v1`
Fingerprint: `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`

Frozen before July 10 strategy outcome/P&L access: q10/q30/q50/q70/q90; 55/50/45/40/35/30m; one contract;
0/1/2/3/5c margins; 0/500/1000 ms latency; IOC entry; entry-time fair-value convergence trigger; one IOC exit
attempt; matched hold control; continuous verified replay; exact historical fee/fixed-point policy.

Result: PREDECLARATION ONLY. Outcomes not accessed. Strategy P&L not run. Orders 0.

<!-- CHECKPOINT21N_Q1_FEE_ACCOUNTING_AMENDMENT_20260901 -->
## 2026-09-01 — Checkpoint 21N-Q1 outcome-blind accounting amendment

Amendment fingerprint: `5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1`.
Base strategy fingerprint: `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`.

Reason: exact fixed-point fee review found that the base predeclaration's fill-level $0.0001 fee rounding and
$0.01 cash alignment were too coarse for the direct-member July 2026 execution baseline.

Correction frozen before results: trade fee ceil $0.000001; direct-member balance grid $0.0001; order-local
rounding accumulator/rebate $0.0001; Decimal arithmetic; one synthetic fill per price level.

Outcomes: 0. Strategy P&L: NOT RUN. Orders: 0.

<!-- CHECKPOINT21N_R_SIMULATOR_IMPLEMENTATION_20260901 -->
## 2026-09-01 — Checkpoint 21N-R outcome-blind simulator implementation

Implementation fingerprint: `6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf`.

Bound parents:
- strategy `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`
- fee amendment `5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1`
- Champion-Final `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`

Implementation scope only: replay timeline semantics, fixed-point order accounting, normalized YES/NO ladders,
IOC entry/exit, latency, partial/missed fills, convergence trigger, source-unavailable states, settlement-fallback
quantity, matched hold quantity.

No July 10 outcome label was read and no realized strategy P&L was calculated. No network request, Predexon
purchase, order, paper broker, demo execution, reserve access, model refit, or Model2 use is part of 21N-R.

## Checkpoint 21N-S-A — Outcome-Blind Real-Data Binder Implementation Freeze

**Type:** outcome-blind implementation freeze; no strategy result.

**Input preflight facts frozen before implementation:** 4 events, 623 paid tickers, 623 replay ticker artifacts, 623 backfill files, 0 missing ticker mappings, 24 source-eligible BTC anchors, 5,644,964 paid deltas, 269,441 snapshots, 268,818 replay pairs, 266,034 exact pairs, and 2,784 unreconciled pairs.

**What was not run:** no real July 10 Candidate-E signal materialization, no real execution scenario materialization, no settlement outcome access, no realized P&L, no model refit, no network request, no new purchase, and no order.

**Interpretation:** implementation/methodology only. N=4 cannot support threshold selection, profitability validation, or production advancement.

<!-- CHECKPOINT21N_S_B_OUTCOME_BLIND_MATERIALIZATION_RESULT_20260901 -->
## 2026-09-01 — Checkpoint 21N-S-B outcome-blind July 10 materialization

Artifact SHA-256:
`624dab514bfffbe1969b87bfa8d7a7bf63dfb14177666cc5d08029c056287f9a`.

Deterministic rerun: PASS, identical hash.

Inputs remained the frozen four July 10 events / 623-market ladder / 24 BTC anchors.
Materialized 20 structural markets, 120 role-anchor decision states, and 20 event-threshold selections.

Decision-state audit:
- source unavailable at exact timestamp: 47;
- missing YES bid: 40;
- missing YES ask: 33;
- crossed two-sided: 0;
- valid two-sided: 0.

Signal candidates: 0. Selected signals: 0. Execution scenarios: 0.
Outcomes accessed: 0. Strategy P&L: NOT RUN. Candidate E refit: NO. Orders/purchases/network: 0.

Result: NON-EVALUABLE due to execution-data adequacy, not an economic pass/fail.

<!-- CHECKPOINT21N_T_CONTINUOUS_CONVERGENCE_REENTRY_PREDECLARATION_20260901 -->
## 2026-09-01 — Checkpoint 21N-T continuous-strategy predeclaration

Predeclared `kxbtcd_candidate_e_continuous_convergence_reentry_v1` before any continuous July 10 path run.

Entry scan T-55 through T-2; decision clock is structural best-level changes + new causal Coinbase 1m states +
window boundaries. Candidate E remains frozen. Maximum filled entries is 2 after full-exit/re-arm.

Comparison branches: matched first-entry hold; liquidate once; liquidate + one re-entry.
Continuous results: NOT RUN. Outcomes accessed: 0. Settlement-dependent P&L: NOT RUN. Orders: 0.

<!-- CHECKPOINT21N_U_A_CONTINUOUS_IMPLEMENTATION_FREEZE_20260901 -->
## 2026-09-01 — Checkpoint 21N-U-A implementation freeze

Implemented but did not run on the real continuous July 10 path: 216-row Coinbase source contract/collector; event-driven decision clock; arbitrary-timestamp Candidate-E signal construction; one-pending-IOC entry state; inherited 21N-R liquidation; full-exit re-arm and maximum one re-entry; settlement-blind output firewall. Continuous paths: NOT RUN. Outcomes: NOT ACCESSED. Settlement P&L: NOT RUN. Orders: 0.

<!-- CHECKPOINT21N_U_B_RECOVERED_COINBASE_BINDING_20260902 -->
## 2026-09-02 — 21N-U-B continuous Coinbase materialization recovery

Run `collect_kxbtcd_candidate_e_continuous_btc_materialization_20260902T053628200857Z_f7b9153a`:
- Coinbase HTTP successes: 4;
- runtime collector.completed: yes;
- rows: 216;
- events: 4;
- derived SHA-256: `ecc83bc5a95c65d05063e06df6d5c9aab04895577c3ef5d8ad1cc99ab62f7d1d`;
- later manifest atomic replace: WinError 5 / RunManifestError;
- manifest retained failed;
- recovery Coinbase requests: 0;
- Candidate E scored: no;
- continuous Predexon path run: no;
- outcomes accessed: no;
- strategy P&L: not run;
- orders: 0.

<!-- CHECKPOINT21N_V_CONTINUOUS_NON_EVALUABLE_CLOSEOUT_20260902 -->
## 2026-09-02 — 21N-V outcome-blind continuous July 10 result

Path SHA-256: `b46281f5b7877c26b2b310e874f0f04aa7679ba02e9876800c6e2af1b1f195bf`.

Frozen policy:
- independent events: 4;
- policy scenarios: 60;
- entry attempts: 0;
- filled trades: 0;
- fully closed round trips: 0;
- terminal `NO_FILLED_ENTRY`: 60 / 60.

Entry-gate diagnostic:
- market evaluations: 17,550;
- invalid two-sided: 13,436;
- Kalshi source unavailable: 4,114;
- evaluable: 0.

Full ladder:
- tickers: 623;
- any valid two-sided: 45;
- per event: 7 / 14 / 12 / 12;
- valid two-sided reconstructed states: 1,060,685;
- frozen structural tickers with any valid two-sided state: 0 / 20.

Rank geometry:
- <=2 ranks from frozen role: 1 / 45;
- <=5: 5 / 45;
- <=10: 17 / 45;
- max absolute displacement: 18.

Classification: `NON_EVALUABLE_STRUCTURAL_UNIVERSE_LIQUIDITY_MISMATCH`.
Outcomes accessed: no. Settlement P&L: not run. Orders: 0.

<!-- CHECKPOINT21N_W_SPOT_ATM_LIQUIDITY_GEOMETRY_20260902 -->
## 2026-09-02 — 21N-W spot/ATM-relative liquidity geometry

Artifact SHA-256: `b2448067c525aaaa6e2f076bed321fb9e55621fcb1319f9a2c282d24d1e31393`.

Design:
- 4 events;
- 54 minute cross-sections/event;
- 216 total;
- full 623-market ladder;
- causal immediately preceding completed Coinbase 1m BTC state;
- Candidate E not scored.

Result:
- active cross-sections: 177 / 216;
- exact ATM two-sided: 62 / 177;
- nearest <=1 rank: 132 / 177;
- nearest <=2 ranks: 161 / 177;
- nearest <=3 ranks: 174 / 177;
- nearest <=5 ranks: 177 / 177;
- median nearest rank: 1;
- maximum nearest rank: 4;
- active ticker-minute instances: 755;
- median instance rank distance: 3;
- median absolute strike distance: $286.25;
- median absolute BTC/strike distance: 44.80983821395667 bps.

Interpretation: exploratory support for spot/ATM-relative liquidity structure.
No v2 envelope selected. Outcomes/P&L unopened. Orders 0.

<!-- CHECKPOINT21N_X_SPOT_RELATIVE_V2_PREDECLARATION_20260902 -->
## 2026-09-02 — 21N-X V2 predeclaration only

Predeclared `kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2` under fingerprint `3e44c6ce3b9e420db3cf0dd52c2b64030ae99901c491d9cf0bc15617930ef8ae`.

No experiment result was run.

Frozen design:
- dynamic causal ATM±5 strike ranks; max 11 markets;
- Candidate-E Champion-Final unchanged;
- inherited one-contract continuous IOC/cashout/max-two-entry mechanics;
- re-arm additionally allowed when completed prior reference market leaves ATM±5;
- July 10 remains N=4 development only;
- fresh fixed target set = 24 post-freeze events;
- fresh source gate = 20/24 materialized, 16 with >=27/54 usable, >=778/1296 pooled;
- fresh predictive gate = better event-equal LL, non-worse Brier, >=4/6 block wins,
  newest Aug29 win.

Candidate-E nonstructural scoring performed: no.
Fresh outcomes accessed: no.
Network requests: 0.
Predexon purchases: 0.
Orders: 0.

<!-- CHECKPOINT21N_Y_A_V2_IMPLEMENTATION_FREEZE_20260902 -->
## 2026-09-02 — 21N-Y-A implementation freeze only

Strategy: `kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2`.
Predeclaration: `3e44c6ce3b9e420db3cf0dd52c2b64030ae99901c491d9cf0bc15617930ef8ae`.
Implementation: `b8f66b2f392df2c8711e7d6e25e64c54921b16f8f7866c243a6375aaec778949`.

No empirical V2 result was run.

Synthetic/unit testing is permitted to exercise implementation mechanics.
Real July 10 nonstructural Candidate-E scoring: no.
July 10 V2 paths: not run.
July 10/fresh outcomes: not accessed.
Strategy P&L: not run.
Network requests: 0.
Predexon purchases: 0.
Orders: 0.

Next experiment: 21N-Y-B outcome-blind July 10 V2 development path only.

<!-- CHECKPOINT21N_Y_A1_QUANTITY_TRANSPORT_AMENDMENT_20260902 -->
## 2026-09-02 — Failed first 21N-Y-B attempt and Y-A1 transport diagnosis

First Y-B attempt:
- nonstructural Candidate-E scoring started: yes;
- failure stage: entry IOC;
- example error: `level.quantity=250.00000000000068 is not aligned to 0.01`;
- completed path artifact: no;
- outcomes accessed: no;
- strategy P&L: not run;
- orders: 0.

Diagnostics:
- paid deltas checked: 5,644,964;
- paid off-grid: 0;
- snapshot levels checked: 13,695,870;
- snapshot off-grid: 763,392;
- snapshot off-grid within 1e-9 of cent: 763,392;
- materially off-cent: 0.

Y-A1 amendment `2cbd8836045ae811eb4c52d48834953a54b1be3afac094be4cf349b8cac2abce` freezes execution-boundary canonicalization only.
No economic result is inferred from the failed attempt.


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

User diagnostic after interruption: 64-bit Python; 15.55 GB visible RAM, 3.95 GB available; Windows reported 56.64 GB total virtual and 29.51 GB available. These are post-interruption readings, not failed-run peaks. A controlled 1,800-delta synthetic fixture measured 4,416,508 bytes original versus 272,321 bytes disk-builder peak tracemalloc allocation (about 94% reduction); tracemalloc excludes SQLite/native memory and is not a real-data RAM benchmark.


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

Evidence review: the Y-A3 paths contain 81 filled entries across alternative policy
scenarios, 53 full exits, 21 positions interrupted by monitoring gaps and seven
missed-exit carry positions. These are simulated alternatives, not independent live
trades or a combined portfolio. Settlement-dependent performance remains unopened.

The forensic inspection found exact local bridges at all three later boundaries:
16:10:00.440 UTC (1013-T64099.99), 17:24:57.646 (1014-T63799.99), and
17:08:05.580 (1014-T63899.99). The full report contains 125 isolated-snapshot
endpoint hypotheses; the production rule is narrower. No new coverage counts are
claimed here before the user runs the frozen gate. Previously shown individual
closed-trade cash examples were not aggregated or used to select repair rules.

<!-- CHECKPOINT21N_Y_A5_REPAIR_CACHE_IMPLEMENTATION_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A5 pre-cache implementation evidence

Repair-plan freeze:
- 110 repair operations
- A4 105 / A5 3 / JOINT 2
- 203 unique original failed pairs addressed
- 545 residual failures
- zero cross-repair context overlaps
- 93 quarantined snapshots
- exact accounting `748 = 203 + 545`
- plan SHA256
  `e95fe1c8d170dad1da9a51fe11e892c1efa70a124f52bbe9acf687c50edbb32b`

The first standalone plan-freeze validator failed closed because its checker
incorrectly expected an N-snapshot exact cut chain to contain N-1 values. Inspection
of the existing `exact_chain` representation showed that it records one boundary
cut value per snapshot, so an N-snapshot order carries N cut values. The validator
alone was corrected; the repair evidence was unchanged. The corrected freeze passed.

The initial repair-aware implementation then passed the pre-cache gate and five
focused tests. A review found one execution-lineage subtlety before commit: A4's
diagnostic row authority was timestamp/sequence/source-row, while the draft builder
only made timestamp/sequence ordering explicit. The builder was tightened to carry
the original Parquet source-row number as the final tie-break and a focused test was
added.

Final pre-cache evidence:
- pre-cache gate: PASS
- repair operations: 110
- addressed failed pairs: 203
- residual hard boundaries: 545
- quarantined snapshots: 93
- focused tests: **6 passed**
- full regression: **1327 passed, 22 subtests passed in 78.23 s**
- HEAD and origin/main before documentation: both
  `0b3bc919e56506f34124e3293f356a1d25f9c5dc`.

No real repaired cache was built during these tests. Strategy was not rerun,
outcomes were not accessed, P&L was not calculated, network requests/purchases were
not made, and orders remained zero.

<!-- CHECKPOINT21N_Y_A6_REPAIR203_PATH_READINESS_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A6 repaired-path readiness evidence

The completed full repair cache reported:
- 47/47 tickers
- 110 repair operations
- 203 original failed pairs addressed
- 545 residual hard boundaries
- coverage SHA256
  `b8b535d6131f01250690d1015861a4737fd0cd4888251f1cbf4941eb7dceeab0`.

A new additive 60-scenario runner and readiness validator were installed without
running strategy scoring.

First readiness attempt: **FAIL CLOSED** with
`frozen 60-scenario grid differs from superseded Y-A3 artifact`.

Diagnosis: the new validator compared the live threshold menu's Decimal values
against threshold values already serialized as JSON strings in the frozen Y-A3
artifact. Existing simulator code intentionally serializes Decimal values via
`jsonable()`. The scenario specifications themselves were unchanged.

Correction: normalize both live and artifact scenario keys through the canonical
JSON representation and add a focused Decimal-to-JSON-string regression test.

Final evidence:
- readiness: PASS
- sealed repair caches: 47
- frozen policy scenarios: 60
- repair operations: 110
- addressed: 203
- residual: 545
- focused tests: 5 passed
- full regression: 1332 passed, 22 subtests passed in 77.32 s
- strategy not run
- outcomes not accessed
- P&L not calculated
- orders 0.

<!-- CHECKPOINT21N_Y_C_PNL_FREEZE_EXPERIMENT_20260903 -->
## Checkpoint 21N-Y-C — pre-outcome evaluation freeze

Frozen repaired path SHA-256: `cd49f0c72548c7715f1025a828b7af1321c02139af926e970e7816945bd69daa`.
Frozen censorship refinement SHA-256: `e4722f37bc001e40b84654d230dccf914f13bf98430aef833fd9efb1e6767439`.
Grid: 60 scenarios = 15 settings x 4 events; 27 exact / 33 censored.

Predeclared treatment: exact fully exited trades use entry+exit net cash; exact settlement fallbacks add authoritative winning-side binary settlement cash; exact no-trade paths are zero; censored paths have no point estimate and use `[-2.0700, 2.00]`. Policy settings are reported as four-event intervals and robust-positive/robust-negative/inconclusive.

Safety: outcomes not accessed; P&L not calculated; strategy not rerun; network 0; orders 0.

<!-- CHECKPOINT21N_Y_D_SETTLEMENT_SCORER_EXPERIMENT_20260903 -->
## Checkpoint 21N-Y-D — settlement scorer readiness

Implemented a zero-network preflight plus a future guarded outcome collector.

Readiness invariants:
- frozen repaired paths and P&L evaluation contract are revalidated;
- request set is derived only from exact settlement-fallback trades;
- censored-only fallback tickers are not independently requested;
- raw-first public HTTP persistence is mandatory;
- per-ticker normalized outcome cache is resumable and immutable;
- finalized binary settlement validation fails closed;
- exact point P&L and censored intervals use the frozen Checkpoint-21N-Y-C
  accounting module;
- no policy ranking/selection is produced.

At this checkpoint: outcome access 0, P&L calculation 0, strategy reruns 0,
network requests 0, orders 0.

## Checkpoint 21N-Y-D1 — first settlement transport attempt and amendment

Authorized outcome run:
- parent closeout:
  `6059704cde4708b18ef1c8d02c152dd7aa5e120a`;
- frozen exact settlement request set: two tickers.

Observed first request:
- ticker: `KXBTCD-26JUL1015-T63699.99`;
- singular historical-market endpoint: HTTP 404;
- collector: FAIL CLOSED;
- normalized settlements: 0;
- P&L: not calculated;
- strategy rerun: no;
- orders: 0.

D1 changes transport only to `/historical/markets` with one exact `tickers`
filter and a strict singleton/exact-ticker response check.

The first D1 patch script partially amended the evaluator, collector, and
readiness validator, then failed while patching duplicated test text. A first
repair attempt also failed before writing anything because its porcelain-status
parser stripped the leading status space from the first filename. This v2 repair
uses `git diff --name-only` plus a separate untracked-file check and completes
only the previously untouched tests/docs.

No settlement outcome was normalized or scored during these patch operations.

## Checkpoint 21N-Y-D2 — storage-tier diagnosis and implementation

D1 real retry:
- parent receipt:
  `b33384cdb6fd84261419cb01af6fb13a3483569e`;
- frozen request scope: two exact settlement tickers;
- first historical-list request returned HTTP 200;
- exact historical matches for
  `KXBTCD-26JUL1015-T63699.99`: 0;
- collector: FAIL CLOSED;
- normalized settlements: 0;
- P&L: not calculated;
- orders: 0.

Kalshi's market-data partition explains the zero historical match: recent
settled markets can remain on normal `/markets` endpoints until they cross the
moving historical cutoff.

D2 implements live/recent exact lookup first and historical exact fallback only
when live returns zero. The first D2 installer successfully modified the
evaluator, collector, and readiness validator, then stopped before writing tests
or docs because its large test-block patch target no longer matched after
in-memory text mutations. The D2 repair preserves those implementation edits,
replaces the untouched focused test file deterministically, and appends the
project documentation.

No outcome was normalized or scored during D2 installation/repair.

<!-- CHECKPOINT21N_Y_E1_SETTLEMENT_SENSITIVITY_EXPERIMENT_20260903 -->
## Checkpoint 21N-Y-E1 — sensitivity freeze before additional settlement access

Parent receipt:
`7151b9f5fa7a712b743176a29ac6d2d2119a7199`

Official outcome artifacts already observed and bound by SHA:
- settlement manifest:
  `e13e9b6236ed21a6f6b921ddecfec0773c7a6ae43bb2a27d8aaf55cb7d3a83c9`;
- P&L report:
  `f070a57c9ea323c4448c9e1fadaf199417f79d9ef9da3a44df177999c3a7feb4`.

E1 derives the observed-entry manifest solely from the frozen outcome-blind path
artifact, freezes the exact unique ticker list needed for later sensitivity,
and makes zero network requests. No additional settlement outcome is accessed.
Strategy is not rerun. Orders: 0.

<!-- CHECKPOINT21N_Y_E2_SETTLEMENT_SENSITIVITY_EVALUATOR_EXPERIMENT_20260903 -->
## Checkpoint 21N-Y-E2 — sensitivity evaluator implementation

Parent E1 checkpoint:
`2a780112f3480a647f89def800b9e2c09fce59ea`

Parent receipt:
`0b3acf6e720d5ee8ee11e7ddee66a79452663a59`

E1 frozen evidence:
- 93 observed filled trades;
- 12 unique settlement tickers;
- 27 exact / 27 selection-rearm-only / 3 liquidation-only / 3 both;
- official result remains 27 exact / 33 censored / 15 inconclusive.

E2 implements the raw-first 12-ticker collector and the three frozen sensitivity
analyses. Implementation/readiness validation must remain zero-network and must not
open any additional settlement before E2 closeout.

Orders: 0. Strategy rerun: no. Policy ranking: forbidden.

<!-- CHECKPOINT21N_Z_A_E2_RESULT_AND_PROSPECTIVE_PREDECLARATION_20260903 -->
## Checkpoint 21N-Z-A — E2 result recording + prospective freeze

E2 settlement SHA `fd830587b393b90f787674bad9a0ecf9a83aac54b4c2410110a97b40533fab46`; sensitivity SHA `aff1847d70b9dc945c5575295a3f3d3e0b2ecc54011d37fa30c57aa3e88bdf22`. Censored traces: 24 positive / 3 negative / 6 zero. Independent observed fills to settlement: 60 positive / 33 negative. Three liquidation-only rows were one JUL14/.05 case across 0/500/1000 ms, each -0.7921. Official result remains 27 EXACT / 33 CENSORED / 15 INCONCLUSIVE. Z-A freezes .02 + one-reentry V2 for 168 prospective hours. No new network/outcomes/orders in Z-A.

<!-- CHECKPOINT21N_Z_B_LIVE_COLLECTOR_IMPLEMENTATION_20260903 -->
## Checkpoint 21N-Z-B — live collector implementation

Implemented a zero-order production live-data smoke harness for the frozen Z-A
prospective Candidate-E policy.

Inputs: open KXBTCD market metadata, authenticated production orderbook WebSocket,
and exact completed Coinbase BTC-USD one-minute close.

Outputs: append-only raw JSONL, derived decision JSONL, and a smoke manifest.
Decision rows include monotonic feed→model and model→signal timing.

No 168-hour run, settlement scoring, P&L, demo order, paper order, or production
order occurs in this implementation checkpoint.

<!-- EXP_21N_ZB_LIVE_SMOKES_20260903 -->
## 2026-09-03 local / 2026-09-04 UTC ? Candidate-E Z-B live production read-only smokes

### Transport-only smoke

Run:
`candidate_e_smoke_20260904T015852Z`

Result:
- PASS
- event `KXBTCD-26SEP0322`
- 188 subscribed markets
- 7,515 Kalshi WS messages
- 2,190 decision calls
- all 2,190 `OUTSIDE_ENTRY_WINDOW`
- 0 sequence gaps
- 0 orders
- 0 production writes

Hashes:
- raw `2429fef630f5dd5b96ec830300a5c934b6ef5ea0f6da5c6a32508add49c924c4`
- decisions `5e7431eae7f6c79663b817f9a0a45c641148116b03cfcf2bc9e165eb3170bbc8`
- manifest `7a01eb337a3742a4cf75c38fd81c1070bc1bc39ab5ab8e9825c2672571a76686`

Interpretation:
transport/book reconstruction validated; strategy economics not evaluated because run was inside final T-2 exclusion.

### In-window live signal smoke

Run:
`candidate_e_smoke_20260904T020640Z`

Result:
- PASS
- event `KXBTCD-26SEP0323`
- 188 subscribed markets
- 11,502 Kalshi WS messages
- 2,890 decision calls
- 187 `KALSHI_BOOKS_NOT_EXACT`
- 2,703 `EVALUABLE`
- 2,703 primary `.02` signal-bearing reevaluations
- 3 unique selected ticker/side pairs
- 15 selection transitions
- 0 sequence gaps
- 0 orders
- 0 production writes

Net-edge distribution:
- min `0.03768211334724974`
- p50 `0.04218642600278958`
- p95 `0.04658905110545961`
- max `0.04658905110545961`

Available selected-level depth:
- min 1
- p50 389
- max 2171

Coinbase exact completed-minute states used:
- 80,870.97
- 80,872.78

Representative arithmetic audit:
- NO `KXBTCD-26SEP0323-T81099.99`: accounting difference `6.94e-18`
- YES `KXBTCD-26SEP0323-T80599.99`: accounting difference `-6.94e-18`
- YES `KXBTCD-26SEP0323-T80699.99`: accounting difference `-1.39e-17`

Hashes:
- raw `1bb6f842a0125e21e596a378ff224f165023b469d391535befcbbcff14d5d200`
- decisions `3e6cb894191163de83b8f251224bf793a31c0d9efe32211e68633a322bf3b82a`
- manifest `78b8df5a8abde32a3a8e7d3449cfec87986222cacdfc21e4d51c4d48f76b38c0`

Interpretation boundary:
the 2,703 signal-bearing rows are highly correlated live state reevaluations from one event, not 2,703 independent trades. The smoke validates engineering and arithmetic, not profitability.

<!-- CHECKPOINT21N_Z_D_COINBASE_RUNTIME_RECOVERY_20260904 -->
## Checkpoint 21N-Z-D ? Coinbase live minute/recovery validation

D2 completed-minute live smoke:

- run: `candidate_e_coinbase_ws_smoke_20260904T032221Z`
- 162 frames
- 123 trade observations including `last_match`
- 38 heartbeats
- completed close: `80927.01`
- close trade ID: `1088541458`
- trade-ID gaps: 0
- heartbeat-ahead observations: 0
- sequence regressions: 0
- non-unit general sequence transitions: 160 / 160
- independent raw close reconstruction: PASS
- raw SHA-256:
  `AAC2B2B1CD3A34F8B39FB00A0F61ACE2E58E458A124DB7EA4553CCF936399E1B`
- manifest SHA-256:
  `9F6260102F174BB4E13E49A75DA472A4C18463B8FC0B15CC414FD78091721450`

D3 intentionally induced one missing builder match while preserving its raw WS
frame.

Observed engineering failures and repairs:

1. REST latest view lagged the WS recovery target by 11 trade IDs; paginator
   repaired to retry latest before older pagination.
2. Same trade ID had equivalent economic fields but WS/REST timestamp
   serialization differed by +1 us; conservative same-minute cross-transport
   identity rule added.
3. REST recovery revisited an already-recorded WS trigger trade; builder
   repaired to treat compatible cross-transport duplicates as corroborative
   no-ops while retaining the first canonical trade.

Canonical final recovery run:

- run: `candidate_e_coinbase_recovery_smoke_20260904T040632Z`
- boundary: `1088550189`
- suppressed trade: `1088550190`
- target: `1088550191`
- REST requests: 5
- latest-visibility requests: 5
- older-pagination requests: 0
- coverage: PASS
- suppressed trade recovery: PASS
- cross-transport identity: PASS
- builder unblocked after proof: PASS
- Kalshi connected: no
- orders: 0
- production writes: 0
- raw SHA-256:
  `8198AEBAFBA03E4331009CC2F62E0CCC27F13FA57E347A5359F81FAC18194F7F`
- manifest SHA-256:
  `A1BC96364BBB35298DC83F295EF867B98F3565AF1E06C488D76205AE23523B19`

Focused regression after final repair:

`38 passed in 1.32s`

Interpretation: Coinbase minute-state and bounded missing-trade recovery are
validated as read-only engineering behavior. No profitability conclusion is
authorized.

<!-- CHECKPOINT21N_Z_E_A_RESTART_DURABLE_DESIGN_20260904 -->
## Checkpoint 21N-Z-E-A — Design-only restart freeze

No live experiment was run.

Design fingerprint: `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

Network requests: 0.
Orders: 0.
Production writes: 0.

Z-E-B must implement the frozen contract and pass all 17 predeclared crash/restart cases.

<!-- CHECKPOINT21N_Z_E_B1_SQLITE_CORE_20260904 -->
## Checkpoint 21N-Z-E-B1 — Offline SQLite durable-core validation

Focused validator: PASS.

Evidence:

- SQLite journal mode: `wal`
- SQLite synchronous: `2` (`FULL`)
- validation sessions: 3
- clean process-discontinuity gaps: 1
- unclean process-discontinuity gaps: 1
- cross-session monotonic reset: accepted
- canonical prospective DB created: no
- 168-hour cohort armed: no
- Coinbase connected: no
- Kalshi connected: no
- signals: 0
- orders: 0
- production writes: 0

Focused regression:

`17 passed in 0.64s`

`py_compile`: PASS.

`git diff --check`: PASS.

Interpretation: validates only the offline SQLite/session-lifecycle slice of the
frozen restart design. It does not yet validate the complete restart state
machine or profitability.

<!-- CHECKPOINT21N_Z_E_B2_RECONCILIATION_20260904 -->
## Checkpoint 21N-Z-E-B2 — Offline identity/raw-reference validation

Focused validator: PASS.

Evidence:

- synthetic arm/SQLite identity: PASS
- exact arm Git identity: PASS
- raw session identity: PASS
- raw segments create-exclusive: yes
- exact raw-reference reconciliation: VERIFIED
- missing raw evidence classification: `RAW_EVIDENCE_GAP`
- partial trailing bytes: preserved / never truncated
- backfill allowed: no
- canonical prospective path: refused
- cohort armed: no
- Coinbase/Kalshi connected: no
- signals: 0
- orders: 0
- production writes: 0

Focused regression:

`14 passed in 1.26s`

`py_compile`: PASS.

`git diff --check`: PASS.

Interpretation: validates offline identity/evidence reconciliation only. It does
not validate full restart readiness or Candidate-E profitability.

<!-- CHECKPOINT21N_Z_E_B3_RESTART_GATE_20260904 -->
## Checkpoint 21N-Z-E-B3 — Offline restart-gate validation

Focused validator: PASS.

Evidence:

- frozen state set: implemented
- startup state: `STARTUP_DISABLED`
- unhealthy/unknown clock: blocks
- absolute clock-offset threshold: 250 ms
- exact 250 ms boundary: pass
- all frozen gates required for `READY_READ_ONLY`: yes
- ready-gate regression immediately removes eligibility: yes
- regression observation gap recorded: yes
- canonical backfill allowed: no
- recovery requires fresh full gate reevaluation: yes
- prior signal reusable: no
- canonical prospective DB created: no
- 168-hour cohort armed: no
- Coinbase/Kalshi connected: no
- Candidate-E signal computation run: no
- orders: 0
- production writes: 0

Focused regression:

`18 passed in 1.10s`

`py_compile`: PASS.

`git diff --check`: PASS.

Interpretation: validates restart-readiness mechanics only. The source readiness
inputs remain synthetic/offline and this does not establish profitability.

<!-- CHECKPOINT21N_Z_E_B4_SOURCE_READINESS_20260904 -->
## Checkpoint 21N-Z-E-B4 — Offline current-source readiness validation

Purpose: validate that fresh current-source evidence can drive the frozen B3 restart gates without reusing stale process/connection state.

Frozen restart-design fingerprint:
`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`.

Runtime-architecture fingerprint:
`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`.

Validator result: **PASS**.

Observed validator assertions:

- boot identity adapter: PASS;
- Windows validation boot ID: explicit synthetic only;
- production boot ID: Linux kernel only;
- chrony tracking adapter: PASS;
- frozen absolute clock threshold: 250 ms;
- accepted Coinbase minute builder wired: yes;
- exact current completed minute: required;
- Coinbase recovery/heartbeat failures: block;
- Coinbase old connection generation: rejected;
- accepted Kalshi full-ladder cache wired: yes;
- Kalshi sequence gap: invalidates / blocks;
- Kalshi transport Ping/Pong liveness: required;
- Kalshi stale/missing Pong: block;
- Kalshi Pong does not heal book state: yes;
- old-session source state: rejected;
- old-connection source state: rejected;
- combined synthetic current sources: `READY_READ_ONLY`;
- network requests in validator: 0;
- canonical prospective DB: not created;
- 168-hour cohort: not armed;
- Candidate-E signal computation: not run;
- orders: 0;
- production writes: 0.

Focused B4 regression:
`33 passed in 4.30s`.

Adjacent B1/B2/B3/live-collector regression:
`67 passed in 2.75s`.

Full repository regression:
`1508 passed, 22 subtests passed in 157.37s`.

Source registry:
23 sources; 1 quality policy; 17 validated; 0 unresolved sources; 1 unresolved settlement source; PASS.

Post-validation file hashes:
- `src/kxbtcd_candidate_e_restart_source_readiness.py`: `9583a90a2b45d65b79881121d53adea6d647251bcf13da255156a00be2514b0c`;
- `tests/test_kxbtcd_candidate_e_restart_source_readiness.py`: `45110d3a9936e1f124cd6cfb8310bca40ae8393be76a35f44e01bbfd9620e9cd`;
- `validate_kxbtcd_candidate_e_restart_source_readiness.py`: `97c7d752c6e27f88e2ce60b214c84c1da13d17b0643a898fd795ceb1ed224ef0`.

Repair notes:
- B4-R1 added missing explicit Kalshi transport-liveness and same-process reconnect generation tests. This prevented a sequence-correct cache from remaining ready after the underlying current WebSocket connection was no longer proven alive.
- B4-R2 repaired only synthetic `LadderMarket` fixtures after validation first failed with a constructor-schema mismatch. Runtime readiness code was unchanged by R2.

Interpretation: this is engineering readiness evidence only. It does not validate profitability, arm the prospective cohort, or authorize execution.

<!-- CHECKPOINT21N_Z_E_B5_R1_CREDENTIAL_BOUNDARY_20260904 -->
## Checkpoint 21N-Z-E-B5-R1 — Credential persistence-boundary validation

Purpose: prove that authentication/signing material cannot enter Candidate-E
raw journals through `request_identity` before any bounded live restart test.

Initial offline validator: PASS.
Focused regression: `59 passed in 2.28s`.
Adjacent B1-B4 restart/readiness regression: `78 passed in 4.39s`.

First full repository regression:
`8 failed, 1537 passed, 22 subtests passed in 156.36s`.

All eight failures shared one root cause: the initial explicit allowlist omitted
safe metadata already used by the committed Coinbase runtime paths. Seven
Coinbase REST recovery tests first failed on `phase`; the same request contract
also contains `latest_attempt_index`, `cb_before`, and `cb_after`. One Coinbase
WS test failed on `product_id`.

B5-R1-R2 repair added only those existing fields with bounded validation and
retained sensitive-name/value rejection plus unknown-field rejection.

Repaired offline validator: PASS.
Targeted repaired regression: `56 passed in 1.70s`.
Final repository regression:
`1553 passed, 22 subtests passed in 108.72s`.

Synthetic secrets persisted: 0.
Validator network requests: 0.
Canonical prospective DB: not created.
Cohort: not armed.
Signals: 0.
Orders: 0.

Interpretation: this is engineering safety and compatibility evidence only. It
does not test live reconnect behavior or establish profitability.

<!-- CHECKPOINT21N_Z_E_B5_R2_EXPERIMENT_20260904 -->
## Checkpoint 21N-Z-E-B5-R2 — bounded live reconnect validation

Purpose: validate the already-frozen current-connection generation contract
against real read-only Coinbase/Kalshi transports without arming the prospective
cohort or computing signals.

Implementation/repair chronology:
- initial offline validator exposed a stale expected Kalshi reason;
- correct frozen B4 precedence is `KALSHI_SUBSCRIPTION_SID_MISSING`;
- R1 repaired validator + one test expectation only;
- corrected validator PASS;
- first combined focused run: 54 passed / 1 failed due one remaining stale
  `before_snapshot` expectation;
- R2 repair installer refused safely and changed nothing;
- R3 repaired only the remaining test assertion;
- final focused B5-R2+B4: `55 passed in 0.61s`;
- full Windows regression: `1575 passed, 22 subtests passed in 79.19s`;
- zero-network live preflight: PASS.

Live run:
`candidate_e_b5_r2_20260904T072848Z`

Selected market:
- event `KXBTCD-26SEP0404`;
- 188 markets;
- 8-second dwell per generation.

Coinbase:
- g1: 1 subscriptions + 1 last_match + 26 matches + 8 heartbeats = 36;
- g2: 1 subscriptions + 1 last_match + 46 matches + 8 heartbeats = 56;
- total 92 raw WS frames;
- both seeded, sequence healthy, recovery_required false;
- disconnect immediately blocked;
- g1 builder rejected after g2 opened.

Kalshi:
- g1: 1 subscribed + 188 snapshots + 1221 deltas = 1410;
- g2: 1 subscribed + 188 snapshots + 834 deltas = 1023;
- total 2433 raw WS frames;
- full-ladder readiness PASS in both generations;
- sequence-gap count 0 in both;
- disconnect immediately blocked;
- g1 cache rejected after g2 opened.

Raw evidence:
- Kalshi REST discovery: 1;
- total = 92 + 2433 + 1 = 2526;
- JSON-valid records: 2526 / 2526;
- manifest count: 2526;
- manifest SHA:
  `F64B7669223518F36AE326B8F04D67CF8C24620F0437A2E1FA9319866267B6B6`;
- raw SHA:
  `C555C91708C788B8404360CB2DBCE954E6C15B4C50B8BAB37EF3572B620EE600`;
- high-confidence secret markers scanned:
  Authorization, Bearer, KALSHI-ACCESS-KEY,
  KALSHI-ACCESS-SIGNATURE, BEGIN PRIVATE KEY,
  BEGIN RSA PRIVATE KEY;
- hits: 0 for all six.

Safety:
- validation_only true;
- canonical prospective DB false;
- cohort armed false;
- signals 0;
- orders 0;
- production writes 0.

Interpretation:
B5-R2 supports the engineering hypothesis that connection-generation rollover
properly invalidates old source state and requires fresh current-connection
rebuilds. It does not test profitability and does not yet complete the
process-crash/host-restart matrix.

<!-- CHECKPOINT21N_Z_E_B5_R3_VALIDATION_20260904 -->
## 2026-09-04 — B5-R3 offline process-restart validation

Purpose:
verify the frozen B5-R3 process-restart reconciliation design without network
access, signal generation, cohort arming, or execution.

Parent receipt:
`3041a628329c94914c297553139d0e52a7a5d94d`.

Design fingerprint:
`0623977817c055b5557296b6e9a58ea371c0ea680728c6a68a52a1c5abfdffea`.

Observed results:

- offline validator: PASS;
- focused B5-R3: 13/13 passed;
- adjacent restart stack: 162/162 passed;
- full repository: 1588 passed + 22 subtests;
- full-suite exit code: 0;
- network requests in validator: 0;
- Candidate-E signals: 0;
- orders: 0;
- production writes: 0.

Interpretation:
the integrated restart path behaves consistently with the previously frozen
durability, raw-evidence, readiness, and source-generation contracts in the
offline validation environment. This is engineering reliability evidence, not
profitability evidence and not authorization for demo or real-money execution.

Next experiment:
a separately bounded live read-only whole-process restart probe after safe
closeout.

<!-- CHECKPOINT21N_Z_E_B5_R4_B_OFFLINE_VALIDATION_20260904 -->
## 2026-09-04 — B5-R4 implementation offline validation

Purpose:
validate the frozen B5-R4 live whole-process restart implementation before any
network-enabled run.

Parent receipt:
`7bad4d50def3e44744347aedb11dfabe3d21c1ba`.

Design fingerprint:
`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`.

Results:
- implementation contract validator: PASS;
- focused tests: 25 passed in 1.19s;
- integrated restart-stack tests: 187 passed in 2.95s;
- zero-network CLI preflight: PASS;
- full repository: 1613 passed + 22 subtests in 65.90s;
- pytest exit code: 0;
- network in preflight: 0;
- credentials accessed in preflight: no;
- signals: 0;
- orders: 0;
- production writes: 0.

Interpretation:
the orchestration is ready for a separately bounded live read-only validation
after safe code closeout. This is engineering reliability evidence only.

<!-- CHECKPOINT21N_Z_E_B5_R4_C_FAILED_LIVE_AND_REPAIR_20260904 -->
## 2026-09-04 — B5-R4 first live attempt FAIL and liveness repair

Run:
`candidate_e_b5_r4_20260904T084136Z_85f2b505`

Purpose:
prove whole-process crash/restart source rebuilding across two actual OS
processes.

Process 1:
- PID 524;
- initial state `BLOCKED_COINBASE`;
- final state `READY_READ_ONLY`;
- Coinbase reason `PASS`;
- Kalshi reason `PASS`;
- Coinbase: 1 subscriptions, 1 last_match, 164 match, 20 heartbeat;
- Kalshi: 1 subscribed, 188 snapshots, 10,860 deltas;
- sequence gaps: 0;
- supervisor then induced unclean termination.

Process 2 failure:
`B5R4LiveProbeError: Kalshi current-connection Pong not received`.

Preserved process-2 source evidence:
- discovery raw records: 1;
- Coinbase raw: 146 records
  (1 subscriptions, 1 last_match, 114 match, 30 heartbeat);
- Kalshi raw: 9,955 records
  (1 subscribed, 188 snapshots, 9,766 deltas).

Interpretation:
fresh process-2 application data was flowing. Since the worker requires its
first manual Pong before entering the receive loop, the failure was a later
periodic Pong miss.

Root cause:
B5-R4 accidentally used a 10-second manual Ping cadence and made any one
5-second manual Pong timeout immediately fatal. This was stricter than the
frozen B4 15s+5s / 20-second Pong-age liveness contract.

Repair:
- manual cadence 15s;
- unique Ping payload per attempt;
- missed Pong never refreshes liveness;
- no prior Pong remains blocked;
- B4 age evaluator determines PASS vs `KALSHI_PONG_STALE`.

Post-repair offline evidence:
- focused B5-R4: 30 passed in 1.32s;
- integrated restart stack: 192 passed in 2.09s;
- full repository: 1618 passed + 22 subtests in 72.01s;
- exit code 0.

Safety:
signals 0; orders 0; production writes 0; execution authorization remains
read-only.

<!-- CHECKPOINT21N_Z_E_B5_R4_LIVE_PASS_20260904 -->
## 2026-09-04 — B5-R4 repaired live whole-process restart PASS

Run:
`candidate_e_b5_r4_20260904T090313Z_c3ff9837`

Command:
`.\.venv\Scripts\python.exe .\collect_kxbtcd_candidate_e_b5_r4_live_process_restart.py --live --source-wait-seconds 120`

Result:
`CANDIDATE-E Z-E-B5-R4 WHOLE-PROCESS LIVE RESTART: PASS`

Process evidence:
- PIDs `26580 -> 41280`;
- process 1 prior status `UNCLEAN_DETECTED`;
- process 2 initial state `BLOCKED_COINBASE`;
- durability `1 examined / 1 verified / 0 pending`;
- fresh Coinbase `PASS`;
- fresh Kalshi `PASS`;
- process 2 final state `READY_READ_ONLY`;
- process 2 shutdown `CLEAN`;
- prior signal reusable `False`;
- process 1/2 Kalshi sequence gaps `0 / 0`.

Transport diagnostics:
- process 1 manual Ping attempts/successes/timeouts: `3 / 3 / 0`;
- process 2 manual Ping attempts/successes/timeouts: `4 / 4 / 0`;
- final manual Pong reason in both:
  `PONG_RECEIVED_RECORD_CURRENT_TIME`.

Integrity and safety:
- raw secret marker hits `0`;
- artifact hash mismatches `0`;
- artifact hash entries checked `18`;
- canonical prospective DB false;
- cohort false;
- signals `0`;
- orders `0`;
- production writes `0`.

Interpretation:
the repaired live runtime passed the intended actual-process crash/restart
sequence. The run did not live-exercise a manual Pong timeout; that repaired
branch remains covered by the focused offline regression suite.

No profitability conclusion is drawn.

<!-- CHECKPOINT21N_Z_E_B5_R5_A_AWS_LINUX_HOST_VALIDATION_20260904 -->
## 2026-09-04 — B5-R5-A AWS/Linux host validation

Purpose:
validate the intended Linux cloud-host environment, Python/runtime compatibility,
real Linux boot identity, chrony state, and controlled host-reboot recovery
without arming a cohort or enabling execution.

Host:
- AWS `us-east-1`;
- physical AZ `use1-az4`;
- local AZ label `us-east-1c`;
- `m7i-flex.large`;
- Amazon Linux 2023 x86_64;
- 100 GiB gp3;
- SSM access;
- zero inbound security-group rules;
- no EC2 key pair;
- IMDSv2 token required.

Repository:
- HEAD:
  `bed0796cf0f85d375635f0acb2088b221fccce9b`;
- origin/main:
  `bed0796cf0f85d375635f0acb2088b221fccce9b`;
- worktree: clean.

Runtime dependency validation:
- Python `3.11.16`;
- required imports: PASS;
- pip dependency consistency: PASS.

Initial full Linux pytest:
- `1603 passed`;
- `11 failed`;
- `4 skipped`;
- total regular test population: 1,618.

Failure/skip diagnosis:
all 15 non-passing tests depended on canonical historical artifacts under
Git-ignored `data/analysis`, `data/derived`, or `data/manifests` paths. No
Linux-specific code failure was identified.

Production-contained/portable suite:
- command deselected exactly those 15 historical-artifact-dependent tests;
- result:
  `1603 passed, 15 deselected in 11.69s`;
- exit code: 0;
- Git status: clean.

Pre-reboot:
- UTC observation: `2026-09-04T10:51:44Z`;
- boot ID:
  `ca870b4a-9490-4328-8f1a-c55fe2046117`;
- system clock synchronized: yes;
- NTP service: active;
- chrony reference: AWS Time Sync `169.254.169.123`;
- chrony system-time offset: `0.002688 ms` fast;
- leap status: Normal;
- chronyd / amazon-ssm-agent / docker: active.

Controlled action:
`sudo reboot`.

Post-reboot:
- observation approximately 1 minute after boot;
- boot ID:
  `0d6faadc-2fae-40bd-aa78-5d86807f8702`;
- boot-ID change: PASS;
- synchronized UTC/NTP: PASS;
- shell-level chrony offset: `0.032553 ms` fast;
- leap status: Normal;
- chronyd / amazon-ssm-agent / docker: active;
- repository identity unchanged and clean.

Application production adapters after reboot:
- `resolve_boot_identity(validation_mode=False)`:
  status PASS,
  source `linux_kernel_boot_id`,
  validation_only false,
  boot ID matched the post-reboot kernel ID;
- `read_production_chrony_tracking()`:
  status PASS,
  signed offset `+0.002674 ms`,
  absolute offset `0.002674 ms`,
  leap status Normal;
- frozen maximum absolute clock offset: `250 ms`.

Classification:
`HOST_REBOOT_AND_CLOCK_BOOT_IDENTITY_PASS`.

Safety:
- historical research archives were not copied to the AWS host for test
  convenience;
- no Coinbase/Kalshi live source run was started during this checkpoint;
- canonical prospective cohort not armed;
- signals: 0;
- orders: 0;
- production writes: 0;
- execution authorization remained read-only.

Interpretation:
this closes host-level Linux reboot/boot-ID/chrony deployment evidence. It does
not establish long-duration runtime stability, source-latency adequacy,
production execution correctness, or profitability.

<!-- EXPERIMENT_B5_R5_A_R2_CLOSEOUT_UTF8_20260904 -->
### ENG — B5-R5-A-R2 Windows Git UTF-8 closeout regression

- Date: 2026-09-04
- Baseline:
  `0d5e53fa70599ef6ccb2ec0b204b5d252fee4971`
- Protected-tooling commit:
  `f5dd81a2edbc4a0d2075c28b62289c1e7ce38ed6`
- Original observed failure:
  `UnicodeDecodeError` from Windows `cp1252` while decoding Git diff output;
  failing byte `0x9d`.
- Repair:
  generic `run()` gained an optional encoding parameter; `git()` now supplies
  explicit UTF-8.
- Focused regression:
  `28 passed in 7.38s`.
- Real subprocess regression:
  PASS with `PYTHONUTF8=0`; staged Git diff containing U+201D decoded to Python
  `str` correctly.
- Source registry:
  PASS.
- Full canonical Windows regression:
  `1619 passed, 22 subtests passed in 72.05s`.
- Manual protected-tooling closeout:
  exact two-file staging PASS; staged whitespace PASS; added-line secret scan
  PASS; remote divergence before commit `0 0`; after push `HEAD == origin/main`
  and divergence `0 0`.
- Strategy/outcome access:
  none.
- Orders/writes:
  none.
- Interpretation:
  engineering-control-plane repair only; no predictive or profitability claim.

<!-- CHECKPOINT21N_Z_E_B5_R5_B_B_A_CLOCK_EVIDENCE_BRIDGE_20260904 -->
## 2026-09-04 — B5-R5-B-B-A AWS chrony container-boundary experiments

Parent receipt:
`6b8148823b1eddfd8c894547c14f8500c2dd8553`

Frozen B5-R5-B-A design:
`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`

Measured AWS host facts:
- Amazon Linux 2023 host chronyd was running;
- `/run/chrony` was mode `0750`, owned by `chrony:chrony`;
- host control socket was `/run/chrony/chronyd.sock`;
- direct socket `chronyc tracking` succeeded as root and as the `chrony` user.

Container diagnostics:
- normal Docker bridge network + single read-only socket bind:
  FAIL, `506 Cannot talk to daemon`;
- Docker host network + the same socket bind:
  FAIL, `506 Cannot talk to daemon`;
- host-generated atomic chrony evidence file + normal bridge container read-only
  mount: PASS;
- attempted write from the container to the evidence mount:
  rejected with read-only filesystem;
- host and ordinary Docker container reported the same Linux time namespace;
- sequential `/proc/uptime` readings were consistent, differing by about
  0.57 seconds.

Conclusion:
the direct chronyd socket transport is not accepted. The evidence-file bridge is
the supported B5-R5-B-B implementation direction, subject to offline tests and
packaged-runtime validation.

These diagnostics did not access Kalshi or Coinbase market-data endpoints,
settlement outcomes, or strategy P&L. Disposable Docker/package infrastructure
network access did occur. Orders: 0. Production writes: 0.

Amendment fingerprint:
`eaf9525f726f4beaad6f7f4bc3e3704534459a1033ec28a1c4656def7121813f`.


<!-- SOAK_OBSERVABILITY_COMPONENT_20260906 -->
## 21N-Z-F observability component — 2026-09-06

Offline observability integration: 50 new tests passed; combined soak/clock bridge/publisher suite: 227 passed in 10.58 seconds. Python 3.12.14 / pytest 9.1.1 / pyarrow 25.0.1 on Windows. Socket connections prohibited by the test harness. Dependency installation used PyPI only. Fixed external-append overwrite detection during testing, excluded shutdown time from run timing, and preserved shutdown source errors as hard failures. Source/host metric producers remain injected, not production-certified. No outcomes/P&L/signals/orders/production writes or AWS run.

<!-- CHECKPOINT21N_Z_F_PACKAGED_CLOCK_PREFLIGHT_20260906 -->
## 2026-09-06 — packaged host-clock preflight

- Windows regression after preflight hardening: `23 passed in 4.17 seconds`.
- AWS image `kxbtcd-candidate-e-soak:dc010d8` passed preflight with Docker
  network disabled, read-only root filesystem, uid/gid `10001`, all capabilities
  dropped, and no-new-privileges enabled.
- A separate malformed mounted evidence file produced
  `SoakPackageError: host clock evidence is not PASS`, exit status `1`.
- No market endpoints, settlement, signals, P&L, orders, or production writes
  were accessed.

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

<!-- KALSHI_STRUCTURAL_ARBITRAGE_SCREEN_20260927 -->
## Kalshi structural arbitrage screened exhaustively and closed - 2026-09-27

Two families of riskless structural arbitrage were screened across the exchange. Strike ladders: 177,450 relations over 38,484 open markets in 3,432 series produced exactly one violation worth $0.13. Multi-outcome events: 4,425 sell-all tests and 53,068 exclusive-pair tests across 5,021 mutually-exclusive events produced zero. Gross violations of the hundred-cent line are routine - the sum of bids across fully-quoted partitions runs median 92, p90 99, maximum 105.0 - and the fee load beats them by roughly a cent. Worked example: an eleven-leg partition at sum_bid 105 carries a ~6.0c fee load against a 5.0c gross.

Four schema misreadings produced confident phantom arbitrage before being corrected, each recorded in KALSHI_API_SCHEMA_REFERENCE.md. The governing one is that strike_type is authoritative and floor_strike equals cap_strike on threshold markets, so inferring "bucket" from both fields being populated classified nested CPI thresholds as mutually exclusive. Detail in KALSHI_STRUCTURAL_ARBITRAGE_SCREEN.md.

<!-- KALSHI_WEATHER_SETTLEMENT_RETRACTION_20260926 -->
## Weather settlement finding retracted - 2026-09-26

A reported +1.00F definitional edge with t +10.6, which had survived a tail-sensitivity sweep, an independent physical measurement and a low-temperature sign-flip falsification passing eight of eight series, was an artifact of an unvalidated settlement proxy. Measured against the bucket Kalshi actually settled, the implied mean is -0.056 with t -0.86: the market is calibrated. The proxy error is exactly the size of the reported edge, at +0.989F on highs and -0.473F on lows, and a strike-convention check reproduced Kalshi's own result on only 55.1% of station-days.

Kalshi settles daily temperature markets on the CONTINUOUS daily extremum, not a sample of hourly observations. The sign-flip falsification constrained only the implied-mean side of the comparison; a sampled extremum is biased low for maxima and high for minima by construction and produces that flip on its own. Full retraction in KALSHI_WEATHER_SETTLEMENT_RETRACTION.md.

<!-- KALSHI_WEATHER_MARKET_MAKING_20260927 -->
## Weather market making measured on 2.33M real trades and closed - 2026-09-27

Across 3,357 markets, 2,326,029 trades and 78,540 quoted hours, two-sided market making returns -0.124c per quoted hour at queue depth 0 and -0.762c at depth 50, with maker fees correctly at zero. Adverse selection, not cost, is binding - the same verdict reached earlier on KXBTC15M. The spread captured when both sides fill is 2.33c but the one-sided hours lose more than that.

Every positive cell in the ask-only grid is a queue-position-0 artifact. The 0-20c band goes +0.524c at queue 0, +0.124c at queue 50 and -0.022c at queue 200, and the time-to-close ordering inverts with queue depth. A rule frozen from the queue-0 ordering consequently failed in both date halves. The surviving cell was not re-fitted; it is preregistered instead. Detail in KALSHI_WEATHER_MARKET_MAKING_RESULT.md.

<!-- KALSHI_MAKER_FEE_CORRECTION_20260927 -->
## Correction: makers pay nothing on 98.9% of Kalshi - 2026-09-27

The /series field fee_type is "quadratic" on 14,235 of 14,398 series, meaning takers pay and makers pay zero. The published schedule charges makers a coefficient of 0.0175 against the taker's 0.07, with the maker multiplier defaulting to zero. Prior analysis in this project charged the taker coefficient to maker activity, understating every ask-only market-making cell by roughly 0.63c per fill at a 10c quote.

This corrects the market-making grid but does not rescue it - two-sided quoting still fails at zero fee. It does not affect the arbitrage screens, which needed executable crossing prices. The general consequence is that every "the fee killed it" conclusion in this project is a statement about taker strategies only. Detail in KALSHI_MAKER_FEE_CORRECTION.md.

<!-- KALSHI_WEATHER_MAKER_PREREGISTRATION_20260927 -->
## Ask-only maker rule frozen with its evaluator - 2026-09-27

One hypothesis survives the edge search and is preregistered: rest an ask only, on weather buckets with a midpoint below 20c, more than twelve hours from close, at queue depth 50, maker fee zero, held to settlement. Point prediction is +0.28c per quoted hour. PASS requires mean above zero with t greater than 2.0 on at least 20,000 forward quoted hours; a positive mean with t below 2.0 is a FAIL.

The cell was chosen after seeing the grid, so the holdout is time itself: wxmmf.py pulls settled markets, and any event settling after the freeze date is data that did not exist when the rule was written. Both the rule and the evaluator scripts/kalshi_research/wxholdout.py are frozen and committed before any holdout data exists - freezing the evaluator removes the room to adjust the analysis once numbers are visible, which is where this project's weighting artifacts came from. Run today it prints NO HOLDOUT DATA YET, confirming the cutoff logic. Evaluate no earlier than 2026-11-01. Detail in KALSHI_WEATHER_MAKER_PREREGISTRATION.md.

<!-- KALSHI_EDGE_SEARCH_CLOSEOUT_20260928 -->
## Kalshi edge search closed after eleven directions - 2026-09-28

Eleven directions are closed with a single mechanism rather than eleven separate explanations: every observable inefficiency measured on Kalshi was real and was sized at or just under the cost of trading it. Sports favourite bias at 3.5c gross against roughly 3.2c of spread and fees; weather longshot overpricing at 1.57c against a 1.11c spread; a six-leg ladder dutch book at roughly 3c gross against a 4.8c fee load; a genuinely 40% too-wide weather distribution sitting entirely inside a 4-7c spread.

The most transferable output is methodological. Six times a weighted or normalised measure showed a large edge and an executable simulation erased it: crypto minute-weighted +5c to entry-once +2c; sports contract-weighted +4.64c to a backtest at -2.75c; an in-game "56% of the move remains" measure to an event study at -3.4c; a 32-game logloss win reversing on a 271-game holdout; a weather implied mean resting on a broken settlement proxy; and a maker grid positive only at queue position zero. Any statistic that weights by volume or time, or normalises by a future value, is not evidence of a tradeable edge. Detail in KALSHI_EDGE_SEARCH_CLOSEOUT.md.

<!-- CROSS_VENUE_PERP_FUNDING_SURVEY_20260928 -->
## Cross-venue perpetual funding survey opened - 2026-09-28

A delta-neutral carry hypothesis is under measurement with no capital committed. Venue reachability from us-east-1 was verified: OKX, Hyperliquid and Kraken Futures respond, Binance returns HTTP 451, and Kalshi's own perpetual series resolve at /series/{ticker} while every markets and events endpoint returns empty, so the Kalshi leg is currently unmeasurable.

The observed structural payer is Hyperliquid rather than Kalshi. Its funding read 0.0000125 for both BTC and ETH simultaneously while its premium was negative on both, which annualises to 10.95% and indicates a rate pinned at an interest-rate floor rather than a market opinion. OKX, which exposes premium and interestRate separately, computed to -1.7% on BTC and +4.6% on ETH over the same snapshot. The question the logger answers is whether Hyperliquid's funding stays pinned while its premium moves. Legal access to a high-funding venue must be settled before any capital, and at an accessible venue's differential the realistic return is roughly 4-5% annualised. Detail in CROSS_VENUE_PERP_FUNDING_SURVEY.md.
