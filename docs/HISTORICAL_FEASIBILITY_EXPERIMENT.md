# Checkpoint 09 — Historical Feasibility Experiment

## Status

**Predeclared, outcome-blind data-feasibility design.**

This checkpoint does not select a profitable strategy, inspect Sports outcomes, or run the blocked Checkpoint-08 calibration experiment.

Checkpoint 08 remains frozen: its fixed `7d` / `3d` / `1d` reconstruction failed the predeclared <=1-hour staleness gate. Nothing in this checkpoint enlarges or weakens that rule.

## Research question

Before choosing the next strategy branch, ask:

> Which candidate branch has sufficiently complete and trustworthy public historical Kalshi quote data to justify a later predeclared outcome experiment?

Candidate categories:

```text
Sports
Crypto
Climate and Weather
Commodities
```

The first comparison is deliberately limited to **Kalshi historical market-data feasibility**. Branch-specific external reference feeds are a later feasibility layer only for categories that survive this quote-data screen.

## New Sports observation meaning

Checkpoint 09 does **not** ask a real quote to represent an artificial fixed timestamp.

Instead, every source-returned one-minute candlestick inside the research region keeps its own timestamp:

```text
time_to_close_seconds = market_close_ts - candle_end_period_ts
```

The research region is:

```text
1 day <= time_to_close <= 7 days
```

A quote at 3.45 days before close remains a quote at exactly 3.45 days before close. It is not relabeled as a `3d` quote.

**Timestamp precision boundary:** public historical data gives one-minute candlesticks with `end_period_ts`; it does not expose the timestamp of every underlying order-book quote update. Therefore `time_to_close_seconds` is exact relative to the source candle period end, not a claim that the bid/ask update itself occurred at that exact second. This is still materially more faithful than assigning the candle to an unrelated fixed 7d/3d/1d anchor.

This removes the Checkpoint-08 anchor-staleness problem by changing the observation definition. It is therefore a **new experiment**, not a post-hoc modification of the blocked experiment.

## Source observation rule

The probe requests official/public Kalshi one-minute market candlesticks from T-7d through T-1d. The analysis region is six days long, but it is **not** sent as one HTTP request.

A public smoke attempt on 2026-08-09 returned HTTP 400 with source detail that the requested six-day range implied 8,640 one-minute candlesticks while the endpoint maximum was 5,000. The collector therefore partitions the unchanged T-7d to T-1d analysis region into deterministic, non-overlapping 24-hour request chunks. Each chunk spans at most about 1,440 one-minute periods, is raw-preserved independently, and has its own lineage-bearing Window row. This is transport batching only; it does not change observation eligibility, time bands, or feasibility gates.

A valid quote observation requires:

1. a real source-returned candlestick;
2. `end_period_ts` inside the requested T-7d to T-1d region;
3. both YES bid close and YES ask close present;
4. both quote values in `[0, 1]`;
5. bid <= ask;
6. exact raw request lineage;
7. valid event/market identity and canonical historical/live routing.

Missing and crossed quotes are preserved and labeled. They are not repaired or imputed.

For live-tier candlesticks, `include_latest_before_start=false` is mandatory so Kalshi's synthetic continuity candle cannot satisfy the experiment.

## Probability-like fields

For a valid uncrossed pair:

```text
q_mid = (yes_bid_close + yes_ask_close) / 2
spread = yes_ask_close - yes_bid_close
```

These fields are descriptive market-state proxies only. They are not executable prices and are not used for outcome analysis in this checkpoint.

## Exact time-to-close and diagnostic bands

Every observation stores exact `time_to_close_seconds`.

For feasibility reporting only, observations are also grouped into three broad support bands:

```text
early:  5d <= time_to_close <= 7d
middle: 3d <= time_to_close < 5d
late:   1d <= time_to_close < 3d
```

These are **coverage diagnostics, not anchors**. No quote is shifted to a band center or boundary.

A later model may study continuous `time_to_close` only after the data-feasibility gate passes and a separate strategy experiment is predeclared.

## Balanced sampling rule

The default feasibility pilot targets:

```text
25 events per category
2 markets maximum per event
```

Markets are selected by ascending SHA-256 hash of the source ticker. Selection does not use:

- final result;
- price;
- spread;
- volume;
- open interest;
- quote availability;
- later feasibility status.

The market cap prevents high-fan-out events from consuming the request budget or making Sports appear to have more independent evidence merely because one event exposes many lines.

This is a screening sample, not the final strategy sample.

The 25-event requirement is a **fixed qualification gate**, not a CLI-dependent value. Smaller `--events-per-category` values are allowed only for engineering smoke tests; they must always report `insufficient_event_sample` even when their observed quote coverage is perfect.

## Outcome blinding

Raw historical market bodies may contain final `result` because the exchange returns it. Raw-first preservation therefore retains the immutable source response.

Checkpoint-09 collection and validation logic must never use that field.

Derived feasibility tables contain no `result` column.

The automated test suite must verify that changing a raw market's `result` from YES to NO leaves every feasibility output unchanged.

## Derived dataset

Dataset family:

```text
historical_feasibility_dataset.v1
```

Tables:

```text
historical_feasibility_event.v1
historical_feasibility_market.v1
historical_feasibility_window.v1
historical_feasibility_observation.v1
historical_feasibility_category_summary.v1
```

### Events

Preserve source event identity, series identity, category, and exact raw lineage.

### Markets

Preserve binary finalized market identity, event/category linkage, open/close/settlement timestamps, canonical route tier, and deterministic selection hash.

Multivariate/combo markets remain excluded from the baseline.

### Windows

Every sampled market has one logical T-7d to T-1d **analysis window**, represented by deterministic non-overlapping 24-hour **request-chunk rows**. Each chunk row carries the exact raw request lineage and its request start/end timestamps, including zero-candle responses. The chunk sequence must cover the logical analysis window exactly with no overlap or unrecorded gap. This prevents missing markets from disappearing from the feasibility denominator while keeping aggregate rows auditable to one raw response.

### Observations

Every real returned one-minute candle is retained with:

- exact timestamp;
- exact `time_to_close_seconds`;
- diagnostic time band;
- bid/ask close;
- midpoint/spread when valid;
- volume/open interest when supplied;
- crossed/missing validity state;
- exact raw lineage.

### Category summary

The summary is outcome-blind and is rebuilt from the four preceding tables during independent validation.

## Predeclared quote-feasibility gates

A category receives `quote_feasibility_pass=true` only when all of the following hold:

```text
sample target reached:             >= 25 selected events
any valid quote at event level:    >= 80% of selected events
any valid quote at market level:   >= 60% of sampled markets
early-band event coverage:         >= 50% of selected events
middle-band event coverage:        >= 50% of selected events
late-band event coverage:          >= 50% of selected events
```

These are engineering feasibility thresholds, not statistical evidence of an edge.

### Why event-level coverage matters

Raw candle count can be misleading. One highly active sporting event can generate far more observations than many quiet events combined.

The primary coverage gates therefore count whether independent **events** have usable data rather than allowing total candle rows to determine feasibility.

### Concentration warning

The report separately warns when either:

```text
one event contributes >20% of all valid observations
or
the most active 10% of events contribute >50%
```

Concentration is a warning, not an automatic block, because a later strategy experiment can use event-level weighting/subsampling. It must nevertheless be visible before outcome analysis.

## Possible category statuses

```text
insufficient_event_sample
quote_feasibility_gate_failed
quote_feasibility_pass_with_concentration_warning
quote_feasibility_pass
```

No one-number category ranking is produced.

Passing this screen means only that the category's Kalshi quote history is sufficiently observable to justify the next feasibility layer. It does not select a strategy, establish calibration, or establish profitability.

## Routing and raw preservation

Each run captures `/historical/cutoff` first.

For every accepted event, both historical and live settled-market list tiers are checked. Canonical tier is determined from `settlement_ts` relative to the captured `market_settled_ts` cutoff.

Known cross-tier overlap is preserved and measured. A canonical single-market recovery request is permitted only when the canonical list copy is absent. Identity/timestamp conflicts fail closed.

Every HTTP response is persisted before transformation using the project's existing public raw-first client.

## Independent validation

`validate_historical_feasibility_manifest.py` must:

1. require a completed `collect_historical_feasibility` manifest;
2. require `outcomes_materialized=false` and `strategy_analysis_run=false`;
3. index the manifest-declared raw archives;
4. reconcile every Event and Market row to exact raw evidence;
5. verify canonical historical/live market routing;
6. verify the request-chunk sequence exactly covers each market's T-7d/T-1d analysis window with deterministic non-overlapping <=24-hour chunks;
7. verify every raw candlestick request matches its Window row's exact request start/end parameters;
8. require `period_interval=1`;
9. require `include_latest_before_start=false` on live requests;
10. rebuild every Window and Observation row from raw response bodies;
11. recompute exact `time_to_close_seconds`;
12. rebuild the category summary from outcome-blind rows;
13. reject any unexpected outcome column or lineage mismatch.

## First execution sequence

Do not immediately run the full 25-event/category pilot.

First run a small public smoke sample:

```powershell
.\.venv\Scripts\python.exe collect_historical_feasibility.py --events-per-category 2 --markets-per-event 1
```

Then independently validate its emitted manifest.

Only after the smoke sample demonstrates correct endpoint behavior, response sizes, routing, and offline reconciliation should the default 25-event/category outcome-blind pilot be run.

## Facts, assumptions, hypotheses, unresolved questions

### Facts already established

- Checkpoint 08 validated the public Kalshi historical cutoff, historical market, historical candlestick, historical trade, and relevant live candlestick paths.
- The frozen fixed-anchor Sports experiment failed its <=1-hour outcome-blind staleness gate.
- Kalshi candlestick responses expose one-minute periods and source `end_period_ts` timestamps; the public historical endpoint does not provide per-quote order-book update timestamps.
- The live single-market candlestick endpoint supports `include_latest_before_start`; the project must keep it false for real-observation research.

### Accepted design choices

- Treat as-observed exact quote timing as a new experiment family.
- Preserve exact continuous `time_to_close_seconds`.
- Use broad time bands only for coverage diagnostics.
- Compare all four categories under the same event/market sampling budget.
- Keep outcomes hidden.
- Use event-level coverage as the primary anti-concentration safeguard.

### Hypothesis

Sports may become historically feasible once real quote observations are used at their actual timestamps rather than forced into exact anchors.

This remains untested until the new public smoke/pilot runs.

### Unresolved

- Whether deterministic 24-hour candlestick request chunking behaves reliably for representative markets across all four categories after the observed 5,000-candle source limit.
- Whether each category can reach the 25-event sample target within the bounded discovery crawl.
- Whether quote coverage spans early, middle, and late time-to-close regions.
- Whether quote observations are excessively concentrated in a few events.
- Whether Crypto, Climate & Weather, or Commodities have suitable branch-specific external historical reference data after passing the Kalshi quote-data screen.

## Safety

Unchanged:

- public unauthenticated GET data only;
- no API/private keys;
- no outcome analysis;
- no calibration experiment;
- no ML;
- no paper/demo/production execution;
- no orders or cancellations;
- no profitability claim.

## Accepted 25-event/category feasibility result

Accepted run:

```text
collect_historical_feasibility_20260809T072159989703Z_6ae075ee
```

Independent manifest/raw/derived validation passed with 100 events, 161 markets, 966 request chunks, 46,972 real one-minute observations, 46,972 valid uncrossed quote observations, and 1,473 indexed raw records. Outcomes remained unmaterialized.

Predeclared gate status:

```text
Sports               PASS with concentration warning
Crypto               PASS with concentration warning
Climate and Weather  FAIL quote-feasibility gate
Commodities          FAIL quote-feasibility gate
```

Sports event quote coverage was 96%, with 84% / 88% / 84% event coverage in the early/middle/late bands. Crypto event quote coverage was 96%, with 88% / 84% / 96% band coverage. Climate/Weather event quote coverage was 32%; Commodities was 4%.

Both passing branches showed severe raw-row concentration: one event supplied about 38–39% of valid observations and the top event decile supplied about 68%. Raw candle rows therefore cannot be treated as independent sample size.

Checkpoint 09 selects Sports as the primary continuation because the exact-time historical path now passes and Checkpoint 07 established a much larger independent live 1–7d event pool for Sports than Crypto. Crypto remains the qualified secondary branch. The next Sports experiment is separately predeclared in `docs/SPORTS_CALIBRATION_EXPERIMENT_V2.md`; the blocked Checkpoint-08 anchor experiment remains frozen.
