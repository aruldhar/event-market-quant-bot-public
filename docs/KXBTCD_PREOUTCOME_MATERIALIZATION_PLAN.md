# KXBTCD Pre-Outcome Historical Materialization Plan

Status: **Checkpoint 12 materialization v3 — accepted read-only, outcome-blind, model-free pre-outcome dataset**
Contract: `kxbtcd_preoutcome_materialization.v3`

Frozen fingerprints:

```text
BTC-state contract: 2739be9af27200a4a2ca8d189bc93d2f3d3349f6b3524f6b919e632fcf9d3668
chronological split design: fc3d7303afb259fc7b39a2657240835a0dd4a4c1b7a7c7b99bbf258f162f3cd4
Candidate-B specification: e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3
dataset design: adc0e6a05ec6a61c114a7d49cb0ad5e271321fe0e8c3c80b76fed81b98025286
materialization design: f9a2459f81b1bb90e1ff55d099e837cb47c78c6586195759d55b5029d676bdb5
```

## Purpose

The previous Checkpoint-12 slices defined the experiment rules. This document freezes how the project will build the **actual historical feature rows** without opening any new KXBTCD outcomes.

In plain language, this stage answers:

> Which historical events, strikes, and times do we copy into the first real Candidate-B dataset?

It still does **not** answer whether those markets eventually settled Yes or No.

## Important historical-vs-live distinction

Historical candlesticks are downloaded during the current research run, but the prices inside them describe earlier market times.

Therefore every state produced by this materialization must use:

```text
state_view = historical_reconstructed
```

For those rows:

- `as_of_utc` is the historical candle timestamp being analyzed;
- local monotonic receipt time records when the historical payload was received/reconstructed now;
- that local receipt time does **not** prove the live system observed the quote at the historical instant;
- the state may be used for offline model research;
- the state may not be passed as `live_first_seen` causal evidence.

This preserves the existing `TIME_ALIGNMENT_POLICY.md` separation between historical reconstruction and live first-seen causality.

## Stage 1 — Conservative modern-regime sampling frame

Materialization v1 attempted to prove settlement-rule semantics for every hourly Event before event sampling. Two outcome-blind live failures showed that this was the wrong collection unit:

- bulk KXBTCD historical Market pagination returned 500,000 contract rows yet only reached back to 2026-01-06, and the saved page stream had 245 chronological ordering violations;
- an exact-event one-market witness design then discovered 11,093 Events in the bounded period, exceeding its 6,000-event safety guard.

Neither failure opened outcomes or fit a model. They demonstrated that exhaustive pre-sampling market-rule validation is unnecessarily expensive for an hourly event family.

Checkpoint-10 already contains outcome-blind rule evidence bracketing the historical rule change:

```text
last sampled old regime:   2024-12-20T01:00:00Z
first sampled modern regime: 2025-03-22T17:00:00Z
```

The March timestamp is **not** claimed to be the exact production rule-change time. It is used as a conservative lower bound: potentially usable modern observations between the unknown true transition and 2025-03-22 are deliberately discarded.

A Checkpoint-12 offline audit of the already-preserved Event data then established:

```text
post-start KXBTCD Events with usable strike_date: 9,737
missing strike_date: 0
duplicated strike_date timestamps: 0
Checkpoint-10 sampled KXBTCD Events joined: 25/25
Event strike_date == independently validated market close_time: 25/25
maximum absolute timestamp difference: 0 seconds
```

Therefore v3 uses this bounded, outcome-blind sampling-frame rule:

1. load the preserved Checkpoint-10 rule-regime report and require the exact old->modern sample bracket above;
2. query settled KXBTCD Events beginning at `2025-03-22T17:00:00Z`;
3. require every returned Event to have a non-null UTC `strike_date`;
4. require `strike_date` values to be unique and at/after the frozen conservative start;
5. use `strike_date` as the sampling-frame chronology;
6. construct a **provisional** target-regime settlement primitive ID from the frozen simple-60-second BRTI signature plus that timestamp, solely so the unchanged quarantine/split machinery can operate;
7. apply the frozen Checkpoint-10 quarantine, chronological split, 24-hour embargo, and weekly SHA-256 event selection;
8. fetch the **complete strike ladder for every selected Event** and validate every market's rule semantics, close time, and settlement primitive;
9. fail the entire materialization if any selected Event disagrees with its provisional sampling-frame identity.

The project does **not** claim that every unsampled post-start Event has individually proven settlement semantics. A successful run proves the semantics of every Event that actually contributes candidate states, while retaining broad chronological coverage without thousands of unnecessary witness requests.

This revision changes the materialization contract and therefore intentionally changes the materialization fingerprint. It does **not** change the BTC-state contract, chronological split algorithm, Candidate-B model specification, dataset row design, weekly event cap, strike quantiles, time anchors, label policy, or execution authorization.

## Stage 2 — Bounded event sampling

From rows already marked `eligible_for_modeling` by the frozen split:

```text
maximum events per UTC week = 4
selection = SHA-256(event_ticker) ascending within the week
```

Selection does **not** use:

- outcome;
- settlement result;
- market price;
- spread;
- volume;
- liquidity;
- quote availability;
- future model score.

### Why four events per week?

This is a deliberately small first research baseline. The goal is to preserve coverage across many UTC weeks without treating every adjacent hourly event as independent evidence or issuing thousands of unnecessary historical requests.

Four is a bounded engineering/research choice, **not** a claim that four events per week is statistically optimal. If the outcome-blind materialization audit later shows inadequate coverage, the plan can be revised under a new fingerprint **before labels are opened**.

## Stage 3 — Five structural strike positions per selected event

For each selected modern-regime KXBTCD event, first normalize and validate all candidate markets as simple `greater` / above-threshold strike contracts.

Sort them by numeric strike, then choose five deterministic structural positions:

```text
q10
q30
q50
q70
q90
```

The exact quantiles are:

```text
0.10, 0.30, 0.50, 0.70, 0.90
```

The ordinal rank uses deterministic nearest-rank half-up rounding.

The selection is based only on market structure. It does not inspect outcomes or quotes.

An event with fewer than five distinct validated strike markets cannot silently substitute a different rule; it fails/excludes under an explicit reason in the future collector.

## Stage 4 — Six explicit time-to-close checkpoints

For each selected market, request real one-minute historical candlesticks through its active period and search for these time-to-close targets:

```text
55 minutes
50 minutes
45 minutes
40 minutes
35 minutes
30 minutes
```

In seconds:

```text
3300, 3000, 2700, 2400, 2100, 1800
```

These are deliberately sparse checkpoints. Candidate B already treats time-to-close as a continuous feature, so we do not need every neighboring minute to dominate the dataset.

The 55-to-30-minute grid is grounded in the observed KXBTCD market lifecycle: most selected markets are active for about 60 minutes, so these anchors target usable pre-outcome states without relying on stale or nonexistent earlier candles.

## Quote-selection rule

At each target time:

1. consider only real one-minute quote observations;
2. require a valid, uncrossed YES bid/ask pair;
3. require the candle timestamp to be **at or before** the target;
4. choose the latest such candle;
5. require it to be no more than 60 seconds before the target.

Formally:

```text
selected_end_period_ts <= target_ts
0 <= target_ts - selected_end_period_ts <= 60 seconds
```

A candle after the target is never allowed.

A quote older than 60 seconds is never filled forward.

If the exact target candle is invalid but a valid candle 60 seconds earlier exists, the 60-second-earlier observation may be used and its **actual** timestamp becomes the state `as_of_utc`.

Therefore a nominal 55-minute target can legitimately produce:

```text
time_to_close_seconds = 3360
```

when the selected real quote is 60 seconds before the nominal target. Candidate B receives the actual time-to-close, not a fabricated 3600-second value.

## Maximum planned row density

The bounded design allows at most:

```text
4 events / UTC week
x 5 strike markets / event
x 6 time checkpoints / market
= 120 pre-outcome states / represented UTC week
```

Actual counts will be lower whenever events are quarantined/embargoed, have insufficient validated strikes, do not span a requested horizon, or lack a valid quote within the 60-second source window.

The actual dataset size is **unresolved until collection**.

## Raw-first requirements

The future collector must reuse the project's existing raw-first behavior:

- persist every source response before transformation;
- keep exact raw source/session/request lineage;
- keep source timestamps and local UTC/monotonic receipt timestamps;
- preserve request failures rather than hiding them;
- fail closed if required raw persistence fails;
- emit run manifest and runtime observability artifacts;
- never log credentials.

The first materialization is expected to use public/read-only historical KXBTCD data. Existing authenticated read-only access remains authorized where necessary, but this plan itself adds no authentication requirement.

## Outputs of the future live/read-only materialization run

The collector should produce, at minimum:

1. the validated event universe and frozen split rows;
2. bounded selected-event rows;
3. selected structural-market rows;
4. selected anchor-observation audit rows, including missing-anchor reasons;
5. `historical_reconstructed` BTC-state rows;
6. Candidate-B pre-outcome dataset rows;
7. a summary containing event/week/partition/strike/time coverage;
8. raw archives, runtime log, and run manifest.

No output may contain a new KXBTCD settlement label in this stage.

## What we will inspect before opening training labels

The next audit is still outcome-blind. We will check:

- number of eligible UTC weeks;
- selected events by train/validation/locked-test partition;
- number of events lost to Checkpoint-10 quarantine or primitive overlap;
- number lost to the 24-hour embargo;
- number of selected events with five valid strike positions;
- coverage at each 55m/50m/45m/40m/35m/30m checkpoint;
- missing/invalid/crossed quote counts;
- raw-lineage completeness;
- duplicate state IDs or market identities;
- actual time-to-close distribution;
- final pre-outcome dataset fingerprint.

If these checks reveal a structural data problem, the design may be revised only under a **new materialization fingerprint before any new labels are opened**.

## Facts, design choices, hypotheses, unresolved questions

### Facts

- The old Checkpoint-10 quote dataset contains only a small deterministic sample and its 20 source events are quarantined from the new experiment.
- Historical KXBTCD candlesticks can provide real bid/ask observations at source timestamps.
- The current clock evidence does not support sub-second cross-feed lead/lag claims.
- No new Candidate-B labels have been opened.

### Design choices frozen here

- split before bounded sample;
- at most four events per eligible UTC week;
- five structural strike positions q10/q30/q50/q70/q90;
- six time-to-close anchors from 55m to 30m;
- real one-minute quotes only;
- no future candle;
- maximum 60-second backward staleness;
- historical states explicitly tagged `historical_reconstructed`.

### Hypothesis

A sparse, broad, event-balanced sample should be sufficient to test the simple Candidate-B calibration question without relying on massive numbers of highly correlated neighboring rows.

That is a hypothesis to evaluate, not a guarantee.

### Still unresolved

- exact number of usable weeks/events/rows after the real collection;
- whether the historical API provides adequate quote coverage at every anchor;
- whether the bounded event sample is sufficiently broad for the intended validation;
- Candidate-B coefficients and validation performance;
- whether Candidate B earns access to the locked test.

## Next engineering step

Implement the **raw-first, read-only materialization collector** around this frozen pure contract. Run it without requesting or transforming outcome fields, validate its manifest and coverage summary, and freeze the resulting pre-outcome dataset fingerprint before attaching training labels.

## Accepted materialization-v3 run

Run: collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d

- selected events: 296
- structural markets: 1,480
- attempted states: 8,880
- available states: 6,378 (71.82%)
- dataset events: 295
- locked-test outcome labels opened: 0
- train: 175 events / 4,645 rows
- validation: 56 events / 719 rows
- locked test: 64 events / 1,014 rows
- split instance fingerprint: 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
- dataset instance fingerprint: d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a