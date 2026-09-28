# KXBTCD Chronological Dataset and Split Contract

Status: **Checkpoint 12 predeclared design — outcome-blind, read-only, model-free**
Contract: `kxbtcd_chronological_split_contract.v1`
Experiment family: `kxbtcd_market_context_probability_baseline.v1`
Frozen design fingerprint: `fc3d7303afb259fc7b39a2657240835a0dd4a4c1b7a7c7b99bbf258f162f3cd4`

## Why this contract exists

Checkpoint 10 tested `kxbtcd_three_probe_monotone_baseline.v1`. Its development outcomes and original holdout have now been viewed. The original holdout therefore cannot become the untouched test set for a newly designed model.

The new experiment starts with a separate chronological firewall. The split is frozen before new labels are opened and before any learned model is fit.

## Checkpoint-10 quarantine

The new experiment excludes **all 20 Checkpoint-10 source events**, not only the four events that were in the old holdout.

The frozen Checkpoint-10 identifiers are:

- experiment: `kxbtcd_three_probe_monotone_baseline.v1`
- design fingerprint: `bad1eab3f36f3b1ed0accbf39926a5e48065fd58c79050355f6ac960c496edd4`
- source event count: `20`

The caller must supply all 20 source event tickers from the preserved Checkpoint-10 pre-outcome artifact. The split builder rejects a quarantine list with any other count.

The caller must also supply the settlement primitive identifiers represented by those source events. A candidate event is quarantined when either:

1. its event ticker is one of the 20 Checkpoint-10 source events; or
2. one of its settlement primitive identifiers intersects the Checkpoint-10 primitive set.

This is intentionally conservative. The project has thousands of later KXBTCD events, so there is little benefit in risking accidental reuse of the old experiment.

## Outcome-blind event unit

Partitioning occurs at the event level, not at individual strike/time rows.

Every input event carries only:

```text
event_ticker
close_time_utc
settlement_regime_id
settlement_primitive_ids[]
source_lineage_refs[]
```

Outcome, label, model-output, economics, and decision fields are forbidden.

All KXBTCD strike observations and state snapshots derived from one event inherit that event's partition later. Repeated rows from one event are therefore not allowed to leak across train, validation, or locked test.

## Settlement regime

The first expanded baseline remains restricted to:

```text
brti_60s_simple_mean_untrimmed
```

Mixing legacy or unknown settlement regimes into this experiment fails closed. If another regime is researched later, it requires a separately declared experiment.

## Chronological block split

After Checkpoint-10 quarantine:

1. sort events by `close_time_utc` ascending;
2. map each event to its UTC ISO week starting Monday `00:00:00Z`;
3. sort the unique week blocks chronologically;
4. allocate whole week blocks using:
   - train: `floor(0.60 * n_weeks)`
   - validation: `floor(0.20 * n_weeks)`
   - locked test: all remaining weeks;
5. require every partition to contain at least one week and require at least five eligible unique weeks overall.

For the currently observed 25-week KXBTCD history scale, this rule would produce **15 train weeks, 5 validation weeks, and 5 locked-test weeks** before any boundary embargo removes event rows.

This is a rule, not a guarantee that the future eligible universe will contain exactly 25 weeks.

## 24-hour boundary embargo

The earlier design phrase “24-hour embargo around the boundary” is made precise here.

After whole-week assignment, events closing during the **first 24 hours beginning at each new-partition boundary** are excluded from modeling:

```text
train -> validation boundary: [boundary, boundary + 24h)
validation -> locked test boundary: [boundary, boundary + 24h)
```

The rows remain present in the split manifest for audit, but:

```text
embargoed = true
eligible_for_modeling = false
```

This creates a deterministic temporal buffer without reassigning an event to another partition.

## Settlement-primitive leakage rule

A settlement primitive may not appear in more than one eligible partition.

If the same primitive appears in train and validation, train and locked test, or validation and locked test, split construction fails closed. The builder does not silently move rows to repair the conflict because that would change the predeclared partition semantics.

## Locked-test rule

Locked-test outcomes may be opened **once only** after all of the following are frozen:

1. shared BTC-state feature contract;
2. chronological split and split fingerprint;
3. candidate model specification;
4. permitted hyperparameter search space;
5. validation selection rule;
6. primary and secondary metrics;
7. dataset/pre-outcome fingerprint.

If the model or feature design changes after locked-test outcomes are viewed, the locked test is consumed and a new chronological experiment must be declared.

## First KXBTCD baseline sequence

The simplest evidence-based order remains:

### Benchmark A — raw market midpoint

No training.

```text
q_market = (yes_bid + yes_ask) / 2
```

This is the mandatory benchmark. A learned model should demonstrate incremental predictive value over the market's own contemporaneous implied probability before complexity is justified.

### Candidate B — regularized market-context logistic model

This is the first learned candidate to specify next.

Minimum conceptual inputs:

```text
market implied probability
strike
explicit time_to_close_seconds
```

A stable transformed representation may be used only after it is frozen in the model specification. For example, logit transformation of the market midpoint can be useful for calibration, but clipping rules must be predeclared before fitting.

The first learned model should remain low-dimensional and regularized. Its purpose is to test whether simple strike/time context improves calibration or proper scoring relative to the raw midpoint.

### Candidate C — slow shared BTC-state augmentation

Deferred until Candidate B is frozen and evaluated on validation.

Potential additions are small, source-specific, causally available features such as slower Coinbase/Kraken returns or realized-volatility state. Source identity must remain explicit. Sub-second cross-feed lead/lag features remain prohibited under the current clock policy.

## Evaluation contract

The primary metric for later outcome scoring is:

```text
event-weighted log loss
```

Secondary metrics are:

```text
event-weighted Brier score
calibration by predeclared probability bin
delta log loss vs raw midpoint
delta Brier vs raw midpoint
performance by time-to-close bucket
performance by predeclared moneyness/strike-context bucket when defined
unique event/day/week counts
```

### Why event weighting matters

One KXBTCD event can create many strike and time-state observations. Treating every row as IID would let events with more sampled rows dominate the score and would exaggerate the apparent sample size.

The later scorer must therefore:

1. calculate the relevant row-level loss inside an event;
2. aggregate to one event-level loss;
3. equal-weight events at the top level.

Day/week counts must also be reported because adjacent hourly KXBTCD events are serially related and are not independent experimental units.

## What this slice does not do

It does not:

- fetch or materialize new settlement labels;
- fit logistic regression or any other model;
- inspect the new locked-test outcomes;
- add KXBTCPERP modeling;
- add a paper broker;
- place, cancel, or simulate orders;
- authorize sub-second lead/lag analysis;
- claim profitability.

The next implementation slice is the **pre-outcome KXBTCD dataset builder/model specification**, not model evaluation.
