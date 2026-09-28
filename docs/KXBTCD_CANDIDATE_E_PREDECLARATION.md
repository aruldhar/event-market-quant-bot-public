# KXBTCD Candidate-E Predeclaration

**Checkpoint:** 19E
**Status:** FROZEN DESIGN — NO E1 OUTCOMES / NO CANDIDATE-E FIT
**Family:** `kxbtcd_independent_btc_offset_successor.v1`
**Predeclaration fingerprint:** `9775be58f01375ca6f2b04212a63578ce5e8cf7084498e6ce9d3ae68685d59a9`
**Parent 19A protocol:** `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`
**Parent 19D-B source policy:** `6b0d98c16a65b2e638b36991d5006031e1bd37048bd04a47a3f67d936df0ee18`

## Purpose

Candidates C and D showed why another probability-only recalibration is not enough. Candidate E tests a narrower, independently sourced question:

> After keeping Kalshi's own midpoint as the fixed probability anchor, does contemporaneous BTC state add incremental settlement information?

The raw Kalshi midpoint remains the benchmark. Candidate E does not replace it with a standalone BTC model.

## Why the constant 10,000 appears

Both independent-BTC features use natural-log ratios. A raw log ratio is numerically small. For example, a roughly 0.10% move produces `ln(1.001) ~= 0.001`.

Multiplying by `10,000` expresses that log move in approximately basis-point units:

```text
10,000 * ln(1.001) ~= 9.995
```

This is a unit choice, not a source of information. Without the factor, the same fitted correction could be represented by a coefficient 10,000 times larger.

Because this predeclaration uses **no regularization and no feature standardization**, the 10,000 factor does not alter the unpenalized model family. It only fixes the coefficient units before E1 outcomes exist. If regularization were present, feature scaling would affect the penalty and could not be treated as merely cosmetic.

## Frozen source construction

Checkpoint 19D-B remains controlling.

Live prospective E1/E2/E3 states require:

- Coinbase Exchange BTC-USD level-1 book as the primary source;
- Kraken Spot BTC/USD PreTrade as the mandatory verifier;
- all frozen local-first-seen, source-event freshness, receive-skew, cross-source disagreement, and clock gates;
- no single-source fallback;
- no source substitution;
- no historical reconstruction to rescue a missing prospective live state.

The current feature price is the Coinbase best-bid/ask midpoint from the latest source-policy-eligible pair locally available at or before decision time `T`, with no more than the frozen 5-second target gap.

For the five-minute lookback, the Coinbase primary observation must come from a source-policy-eligible Coinbase/Kraken pair available at or before `T-300s`, again with no more than the frozen 5-second target gap. Future interpolation, nearest-absolute sampling, and carry-forward are prohibited.

## Frozen KXBTCD state materialization

Reuse the bounded structural design established in Checkpoint 12:

- five strike roles: q10, q30, q50, q70, q90;
- deterministic numeric-strike nearest-rank half-up selection;
- six scored TTC targets: 55m, 50m, 45m, 40m, 35m, 30m;
- one extra 60m external-BTC target used only as the causal seed for the 55m five-minute lookback.

For a scheduled decision target `T`, the KXBTCD midpoint must come from a valid, uncrossed two-sided YES quote observed at or before `T` and no more than 60 seconds old. A future quote is never allowed and a quote older than 60 seconds is never filled forward.

The model decision time is the scheduled target `T`. This means every model input must have been locally available by `T`.

## Frozen independent-BTC features

### 1. BTC strike log-distance

```text
d_BTC = 10,000 * ln(S_t / K)
```

where:

- `S_t` is the frozen live Coinbase-primary midpoint at decision time `T`;
- `K` is the validated KXBTCD strike in dollars.

Interpretation:

- positive: independent BTC spot is above the strike;
- zero: spot equals the strike;
- negative: spot is below the strike.

### 2. Five-minute BTC log return

```text
r_5m = 10,000 * ln(S_t / S_t-300s)
```

The lookback is strictly causal. The model may not use an observation first seen after the exact five-minute target.

## Frozen candidate menu

Exactly two candidates are authorized for the future one-time E1 design evaluation.

### E-distance

ID:

`kxbtcd_btc_distance_offset_logistic.v1`

Model:

```text
logit(p) = market_logit_offset + beta_distance * d_BTC
```

### E-distance-momentum

ID:

`kxbtcd_btc_distance_momentum_offset_logistic.v1`

Model:

```text
logit(p) =
    market_logit_offset
    + beta_distance * d_BTC
    + beta_momentum * r_5m
```

For the model transform only, the Kalshi midpoint is clipped to `[0.001, 0.999]` before computing the fixed market-logit offset. The raw benchmark for metrics remains the original midpoint probability.

Both candidates nest the raw-market offset at all free coefficients equal to zero.

No intercept, free market-logit slope, spread feature, TTC interaction, polynomial feature, regime switch, neural network, feature standardization, regularization, or hyperparameter search is allowed.

## Why there is no regularization grid

Candidate E has only one or two free correction coefficients. Adding a lambda grid would create another model-selection degree of freedom and would make the feature-unit choice interact with the penalty.

Instead, each rolling fit starts exactly at the raw benchmark and uses unregularized event-equal log loss. Non-convergence, singular Hessian, or nonfinite values fail closed.

Frozen optimizer:

```text
deterministic damped Newton
max iterations = 100
gradient L2 tolerance = 1e-8
Armijo constant = 1e-4
minimum step = 2^-40
```

## Common row universe

Both candidates are scored on exactly the same OOF rows.

Therefore a scored row must have:

- a valid KXBTCD midpoint;
- an eligible current Coinbase/Kraken pair;
- an eligible causal five-minute Coinbase/Kraken lookback pair.

The simpler distance-only candidate does not get extra rows merely because it does not mathematically need `r_5m`. This prevents candidate selection from being confounded by different samples.

## E1 cohort freeze

E1 is genuinely new prospective design evidence.

The first eligible event must have its entire required feature window after the Candidate-E predeclaration freeze. Concretely, its 60-minute lookback-seed target must occur strictly after the freeze timestamp.

Minimum readiness remains inherited from 19D-B:

```text
168 eligible events
7 distinct UTC dates
168 chronological hours
all 24 UTC hour-of-day bins
>= 90% tier source-eligible scheduled-state rate
>= 4 of 6 source-eligible scored anchors for each counted event
```

The cohort stops at the first chronological point where all outcome-blind readiness gates are satisfied. If they are not satisfied, collection extends prospectively **without opening outcomes**. Thresholds may not be relaxed after collection starts.

## Outcome firewall

Before any E1 settlement outcome is opened, the project must freeze and fingerprint:

1. the complete pre-outcome E1 cohort;
2. exact row lineage;
3. the seven-block chronological map;
4. source-policy validation;
5. tier-readiness validation.

E0 outcomes may not become E1 scoring rows. Checkpoint-17 terminal data remain prohibited.

## Seven-block rolling-origin E1 evaluation

After the E1 cohort is frozen without outcomes:

1. sort eligible E1 events chronologically;
2. divide them into seven contiguous blocks whose event counts differ by at most one;
3. earlier blocks receive any remainder.

Frozen score folds:

```text
fit B0+B1                -> score B2
fit B0+B1+B2             -> score B3
fit B0+B1+B2+B3          -> score B4
fit B0+B1+B2+B3+B4       -> score B5
fit B0+B1+B2+B3+B4+B5    -> score B6
```

At the 168-event minimum, each block contains exactly 24 events.

Every score block must represent all five structural strike roles and all six TTC targets.

## Fit objective

For every fit:

- each event receives equal total weight;
- all scored rows inside that event share the event's weight equally;
- objective is binary log loss;
- initialize all free coefficients at zero;
- no regularization;
- no hyperparameter tuning.

This prevents an event with more available market/anchor rows from dominating the objective.

## Raw-benchmark advancement gate

Each candidate independently passes only if **all** conditions hold:

1. pooled raw-minus-candidate event-equal log-loss delta is strictly positive;
2. pooled raw-minus-candidate event-equal Brier delta is nonnegative;
3. candidate beats raw log loss in at least 4 of 5 score blocks;
4. candidate beats raw in latest block B6;
5. median event-level raw-minus-candidate log-loss delta is strictly positive;
6. all five fits converge and every parameter, prediction, and metric is finite;
7. `beta_distance > 0` in every fold;
8. every score block covers all five strike roles and six TTC targets;
9. no source-policy, timing, lineage, tier, or outcome-firewall violation occurs.

A negative distance coefficient is rejected because, holding the Kalshi anchor fixed, the first independent-BTC successor is not allowed to learn an anti-monotone spot-versus-strike correction.

## Frozen model-selection rule

Both candidates are evaluated exactly once on the same E1 OOF rows.

- Neither passes raw gate -> Candidate-E family **FAIL**.
- Exactly one passes -> select that candidate.
- Both pass -> default to the simpler distance-only candidate unless momentum also clears the nested complexity gate.

The nested momentum gate requires all of:

1. pooled distance-minus-momentum log-loss delta > 0;
2. pooled distance-minus-momentum Brier delta >= 0;
3. momentum beats distance in at least 4 of 5 score blocks;
4. momentum beats distance in latest B6;
5. median event-level distance-minus-momentum log-loss delta > 0.

This means the second coefficient must earn its complexity with temporally consistent evidence, not merely a tiny pooled improvement.

## What happens after E1

A PASS does not produce a final model.

If E1 selects one specification:

- freeze that one exact specification;
- begin new chronological E2 evidence only afterward;
- use E2 only to estimate final parameters;
- fingerprint the final model;
- begin E3 only after the final-model freeze.

E1 can never be relabeled E2 or E3, and E1 cannot be repaired/rescored after its design result.

## Safety

Checkpoint 19E freezes design only.

It authorizes:

- no Candidate-E fit;
- no E1 outcome access;
- no Checkpoint-17 terminal access;
- no paper execution;
- no demo execution;
- no real-money execution;
- no order creation or cancellation;
- no transfers.

Passing a future E1 gate would establish only successor-design evidence. It would not establish profitability or execution viability.
