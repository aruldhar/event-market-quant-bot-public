# Sports V2 Outcome-Blind Scalability Pilot

## Status

Predeclared before the 100-event Sports V2 scalability collection. Public/read-only only. Final YES/NO outcomes remain hidden.

## Purpose

Checkpoint 09 established that the redesigned exact-time Sports data path passes the 25-event historical quote-feasibility gate, but the 25-event sample also showed severe one-minute observation concentration. The next question is not whether Sports is profitable or calibrated. It is whether the redesigned data contract scales to at least 100 independent Sports events while retaining enough real quote coverage for a later 1,000-event calibration experiment.

## Frozen collection contract

- Category: Kalshi `Sports` only.
- Event target: at least 100 unique eligible events.
- Markets: at most 2 per event.
- Market selection: ascending SHA-256 hash of ticker; never price, spread, volume, quote availability, or result.
- Observation region: exact T-7d through T-1d relative to each market `close_time`.
- Candles: source-returned 1-minute candlesticks only.
- Transport: the analysis region is fetched as non-overlapping <=24-hour request chunks because Kalshi rejects requests exceeding 5,000 one-minute candlesticks. Request chunking is transport only and does not create analytical anchors.
- Live candlesticks: `include_latest_before_start=false`.
- Every observation retains exact `time_to_close_seconds`.
- No forward filling, nearest-anchor substitution, synthetic continuity, imputation, or staleness-rule relaxation.
- No final `result` field may enter the derived path or scalability decision.

The dedicated scalability collector refuses a requested event target below 100. Smaller engineering smoke tests must use the generic historical-feasibility collector and cannot qualify this gate.

## Frozen pre-outcome gates

The 100-event scalability sample passes only if all of the following hold:

1. at least 100 unique Sports events were collected;
2. independent raw-to-derived manifest validation passes;
3. event-level any-valid-quote coverage is >=80%;
4. sampled-market any-valid-quote coverage is >=60%;
5. event coverage is >=50% separately in each existing diagnostic band: 5-7d, 3-5d, and 1-3d;
6. source-series and event-observation concentration are reported;
7. no synthetic candle, fixed-anchor substitution, outcome filtering, or result-derived selection entered the path.

The existing bands remain descriptive coverage strata, not observation anchors.

## Series concentration rule

Let a source series' event share be:

```text
series_event_share = events_in_series / all_selected_events
```

- if the largest series exceeds 25% of selected events, issue a generalization warning;
- if it exceeds 50%, block a general-Sports conclusion and classify the scalability result as series-concentration blocked.

`series_ticker` is a source identity, not assumed to be a complete economic product-family taxonomy.

## Observation concentration

Continue reporting:

- largest-event share of valid one-minute observations;
- top-decile event share of valid one-minute observations.

These are diagnostics, not sample-size measures. Later calibration inference will use the already predeclared hierarchical event -> market -> observation weights so dense events cannot dominate.

## Decision boundary

A scalability pass authorizes only planning the 1,000-event outcome-blind collection. It does not authorize materializing outcomes, calibration analysis, strategy claims, paper trading, authentication, or order execution.

If any frozen data-quality gate fails, stop and record the failure before any outcome analysis.

## Accepted 100-event validation evidence

Accepted local public/read-only run:

```text
collect_sports_v2_scalability_20260809T074813046311Z_68eb260c
```

Independent manifest validation: **PASS**.

Observed outcome-blind facts:

- 100 event rows;
- 169 sampled markets;
- 1,014 candle request chunks;
- 52,331 real one-minute observations;
- 52,331 valid uncrossed quote observations;
- 1,532 indexed raw records;
- event any-quote coverage 0.970000;
- market any-quote coverage 0.964497;
- early/middle/late event coverage 0.790000 / 0.870000 / 0.900000;
- 66 unique source series;
- dominant source series `KXNEXTTEAMNFL`, event share 0.100000;
- largest-event observation share 0.095488;
- top-decile event observation share 0.522138;
- pre-outcome status `scalability_gate_pass`;
- outcomes materialized: no.

Interpretation: the exact-time Sports historical data path scales successfully to the frozen 100-event gate. This is a data-feasibility result only. Because Sports is heterogeneous across sports/leagues and product structures, the next pre-outcome step is the separately predeclared heterogeneity profile rather than outcome materialization.
