# Sports Historical Quote-Age / Missingness Pilot

## Status

**Outcome-blind engineering analysis. No final YES/NO outcomes are loaded.**

This pilot is the required bridge between the raw-first Sports historical collector and the predeclared calibration experiment. Its purpose is to measure whether the latest real bid/ask quote near each fixed anchor is fresh enough to represent that anchor without arbitrary forward filling.

## Inputs

The pilot accepts one completed `collect_sports_historical` manifest and reads only these normalized tables:

- Events;
- Markets;
- Anchors.

It deliberately does **not** open:

- raw HTTP archives;
- candle CSVs;
- trade data;
- outcome/result data.

The exact collection manifest must be independently validated with `validate_sports_historical_manifest.py` before its data are used for the pilot.

## Measurement

For each market and each predeclared anchor (`7d`, `3d`, `1d`), the collector already records:

```text
latest_quote_age_seconds = anchor_ts - latest_quote_pair_ts
```

when at least one real 1-minute candlestick at or before the anchor contains both a YES bid close and YES ask close. If no such pair exists inside the engineering lookback window, quote age remains missing and the anchor is counted explicitly as missing.

No missing value is imputed.

## Predeclared candidate thresholds

The pilot evaluates exactly:

```text
1 minute
5 minutes
15 minutes
30 minutes
1 hour
```

The upper candidate is intentionally capped at one hour. This is a conservative baseline assumption, not a fact about market efficiency: the shortest research horizon is one day before close, and the project has no evidence justifying multi-hour-old quotes as faithful representations of a fixed one-day anchor.

## Retention rule

A threshold qualifies only if it retains:

```text
>= 90% of all anchors that have any quote pair
AND
>= 80% of quote-bearing anchors separately at 7d, 3d, and 1d
```

The recommended candidate is the **smallest** threshold satisfying all gates. This prefers fresher observations rather than maximizing sample size.

Missing anchors are reported separately and remain excluded regardless of threshold.

## Minimum sample before freezing

A candidate threshold cannot be frozen from fewer than:

```text
100 unique Sports events
```

A smaller sample may be used to test the pipeline and reveal likely quote-age behavior, but its recommendation status remains preliminary.

This is an engineering quality gate, not the final experiment's statistical evidence gate. The calibration experiment still requires at least 1,000 unique eligible events before a checkpoint-level calibration conclusion.

## Possible outcomes

### `preliminary_sample_too_small`

A retention-qualified threshold exists, but fewer than 100 unique events were analyzed. Collect a larger outcome-blind sample before freezing the threshold.

### `freeze_candidate_available`

The smallest qualifying threshold exists and at least 100 unique events were analyzed. Record that threshold in `docs/DECISIONS.md` before any outcome materialization or calibration analysis.

### `blocked_no_freshness_candidate_meets_retention_gates`

No threshold at or below one hour satisfies the predeclared retention gates. Do not silently expand the threshold. Treat the baseline historical reconstruction as blocked until a new design decision is explicitly reviewed.

## Outputs

The analysis writes:

- `<input_run_id>_staleness_pilot.json` — sample counts, quote-age quantiles, per-anchor missingness, the frozen decision rule, and recommendation status;
- `<input_run_id>_staleness_thresholds.csv` — retention at every predeclared candidate threshold.

The pilot does not freeze the threshold automatically. Freezing is a separate documented decision after reviewing the outcome-blind report.

## Command

```powershell
.\.venv\Scripts\python.exe analyze_sports_staleness.py <validated-collection-manifest>
```

## Safety boundary

This pilot performs no network access, authentication, trading, paper execution, calibration scoring, or outcome analysis. It cannot establish profitability.

## Accepted 100-event outcome-blind result

Input run:

`collect_sports_historical_20260809T060907842728Z_94ad3820`

The independently validated input contained:

```text
100 unique Sports events
1200 markets
3600 anchors
288210 real one-minute candle rows
4718 indexed raw records
outcomes materialized: no
```

Pilot result:

```text
Anchors with any bid/ask pair: 2646
Anchors with no bid/ask pair: 954
Quote availability: 73.500%

Quote-age seconds:
p50=1588
p75=10403
p90=50183
p95=70192
max=86238

7d: 704/1200 with quotes (58.667%); p90=31922s
3d: 986/1200 with quotes (82.167%); p90=56893s
1d: 956/1200 with quotes (79.667%); p90=50183s

recommendation_status=blocked_no_freshness_candidate_meets_retention_gates
candidate_threshold=none
threshold_eligible_to_freeze=no
```

No raw HTTP archive, candle CSV, or final YES/NO outcome table was opened by the pilot.

Decision D-027 therefore freezes no threshold and blocks the current fixed-anchor calibration reconstruction before outcome analysis. The candidate grid must not be silently expanded inside this experiment.
