# KXBTCD Candidate-E Quoted-Entry Hold v1 — Development Failure Analysis Predeclaration

## Checkpoint

**Checkpoint 21N-D — Strategy-v1 Development Failure Analysis**

## Purpose

Checkpoint 21N-C permanently rejected `kxbtcd_candidate_e_quoted_entry_hold_v1`
with `FAIL_NO_THRESHOLD`. Candidate E remains the forecasting Champion-Final.

21N-D asks one bounded diagnostic question:

> Why did the closest frozen policy (3c net quoted edge) make money in earlier
> development periods but fail H3 and the newest chronological block B4?

This is an outcome-aware **failure analysis on already-exposed development evidence**.
It is not a new strategy search.

## Frozen bindings

- Strategy fingerprint:
  `5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6`
- Development-economics fingerprint:
  `692b7239067b3024db908fc0e0809f33f900f685faec97c45743195e19d364e5`
- Development evaluation fingerprint:
  `8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc`
- 21N-C result-closeout fingerprint:
  `9837823342eeb7b7c7d44a264b1507cd718310c2dccb83c837f9bb0bc4d1b392`
- 21N-D analysis-predeclaration fingerprint:
  `33fb68841a174d50971d40aefae73ab564f96adcb8aefafcf5e86aa16d21bc8b`

## Primary diagnostic population

The primary diagnostic population is frozen before slice inspection:

- threshold: exactly **3c**
- stress: exactly **displayed quote / +0c**
- entries: exactly **159**
- abstentions are excluded from trade-composition diagnostics because the question
  is why selected trades succeeded or failed.
- no alternative threshold is promoted or searched.

The other frozen thresholds may appear only as already-known aggregate context from
the 21N-C result. Detailed slice mining is limited to the 3c policy.

## Predeclared comparisons

The analyzer reports the same metric set for:

1. stages: H1_OOF, H2, H3;
2. chronological blocks: B0, B1, B2, B3, B4;
3. side: YES, NO;
4. TTC: 55, 50, 45, 40, 35, 30 minutes;
5. structural role: q10, q30, q50, q70, q90;
6. purchase-price buckets:
   - [0.00,0.25)
   - [0.25,0.50)
   - [0.50,0.75)
   - [0.75,1.00]
7. Candidate-E selected-side fair-probability buckets:
   - <0.60
   - [0.60,0.75)
   - [0.75,0.90)
   - >=0.90
8. quoted net-edge buckets:
   - [0.03,0.04)
   - [0.04,0.05)
   - [0.05,0.07)
   - >=0.07

Two regime contrasts are frozen before inspection:

- H2 versus H3;
- B3 versus B4.

## Economic decomposition

For every slice, report:

- entries and wins;
- win rate;
- mean purchase price;
- mean Candidate-E selected-side fair probability;
- `win_rate - mean_fair_probability` as a descriptive calibration-gap diagnostic;
- mean quoted net edge;
- mean entry fee;
- gross P&L before entry fee;
- total entry fee;
- total net P&L;
- mean net P&L/trade;
- mean winning trade;
- mean losing trade;
- worst trade.

This distinguishes three broad mechanisms without fitting anything:

1. forecast/calibration deterioration;
2. more expensive or otherwise different selected entries;
3. loss-tail concentration where a few expensive misses erase many small wins.

## Tail concentration

For ALL 3c trades, H3 3c trades, and B4 3c trades:

- list the 10 worst trades by realized net P&L;
- measure the share of total negative-loss magnitude contributed by the worst
  1, 3, and 5 losing trades.

This is descriptive. Removing those trades is **not** a permitted counterfactual
strategy and does not authorize a stop/filter.

## Interpretation firewall

21N-D may generate hypotheses such as:

- Candidate E became overconfident in H3;
- selected prices shifted upward;
- a side/TTC/role mix changed;
- predicted edge stopped ranking realized economics;
- the failure was dominated by a small loss tail.

It may not:

- select a new threshold;
- declare a TTC/role/side/price/edge bucket tradable;
- optimize a subset;
- fit a meta-model;
- fit or score a successor strategy;
- open C1+C2 Strategy-v1 economics;
- access C3;
- access the protected 4,676-event reserve;
- perform paper/demo/real execution.

Any successor rule suggested by the diagnostic must later receive a separate
predeclaration and evidence plan before fitting or scoring.

## Outputs

The frozen analyzer writes:

1. `failure_analysis_summary.json`
2. `failure_analysis_slices.csv`
3. `failure_analysis_tail_trades.csv`
4. `failure_analysis_regime_comparisons.csv`

The output fingerprint binds the complete descriptive result.

## Safety

Read-only/offline only. No network calls and no order surface.
