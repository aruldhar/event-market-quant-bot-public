# KXBTCD Pre-Outcome Dataset and Candidate-B Specification

Status: **Checkpoint 12 frozen pre-outcome design — read-only, no model fit, no new labels opened**
Dataset contract: `kxbtcd_preoutcome_dataset_contract.v1`
Experiment family: `kxbtcd_market_context_probability_baseline.v1`
Candidate B: `kxbtcd_market_context_logistic.v1`

Frozen fingerprints:

```text
BTC-state contract: 2739be9af27200a4a2ca8d189bc93d2f3d3349f6b3524f6b919e632fcf9d3668
chronological split design: fc3d7303afb259fc7b39a2657240835a0dd4a4c1b7a7c7b99bbf258f162f3cd4
Candidate-B specification: e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3
dataset design: adc0e6a05ec6a61c114a7d49cb0ad5e271321fe0e8c3c80b76fed81b98025286
```

## Purpose

This slice bridges the shared BTC-state contract and the later labeled KXBTCD experiment without opening outcomes prematurely.

It answers two questions before fitting anything:

1. exactly what pre-outcome row is allowed to enter the first KXBTCD learned baseline; and
2. exactly what Candidate B is allowed to learn.

The module is deterministic and offline. It does not call Kalshi, Coinbase, Kraken, or any other network source. It does not fetch results, fit coefficients, calculate realized strategy PnL, simulate fills, or place orders.

## Important identity correction before checkpoint closeout

The first uncommitted draft of `btc_state_feature_contract.v1` identified KXBTCD state by `event_ticker`, strike, and timing context but omitted the exact `market_ticker`.

That is insufficient because a KXBTCD event can contain multiple binary strike contracts with different eventual outcomes.

Before the draft became canonical, the contract was corrected to require:

```text
event_ticker
market_ticker
```

for KXBTCD state context. Later KXBTCD label context must also carry `market_ticker`.

This makes the eventual join explicit:

```text
state.market_ticker == label.market_ticker
```

rather than accidentally assigning one event-level outcome to every strike contract.

## Builder inputs

`build_preoutcome_dataset()` consumes two already-derived inputs.

### 1. Synchronized KXBTCD states

Each state must validate under `btc_state_feature_contract.v1` and retain raw lineage.

For a state to become a modeling row:

```text
product_head == KXBTCD
state_view == historical_reconstructed
state_quality == usable
settlement_regime_id == brti_60s_simple_mean_untrimmed
```

The state must identify the exact event and exact market contract and must contain historical source bid/ask, strike, and time-to-close context. This offline dataset intentionally rejects `live_first_seen` rows so historical reconstruction and live causality cannot be mixed silently.

### 2. Frozen chronological split rows

The state event must exist in the already-frozen `kxbtcd_chronological_split_contract.v1` manifest.

The builder verifies that the split rows use the expected experiment family, regime, design fingerprint, and one consistent split fingerprint.

Checkpoint-10 quarantined events and partition-boundary embargo rows therefore remain visible for audit but cannot enter the modeling dataset.

## Time-to-close consistency

The model must not trust a detached `time_to_close_seconds` value blindly.

For each state the builder checks:

```text
computed_ttc = event_close_time_utc - state.as_of_utc
```

and requires:

```text
abs(computed_ttc - declared_time_to_close_seconds) <= 1 second
```

A state after event close or a larger disagreement fails closed.

The one-second tolerance permits harmless timestamp representation/rounding differences while still catching materially misaligned rows.

## Pre-outcome dataset row

A modeling-eligible row carries:

```text
state_id
state_view
event_ticker
market_ticker
partition
utc_week_start
event_close_time_utc
as_of_utc
as_of_local_monotonic_ns
alignment_epoch_id
settlement_regime_id
strike_dollars
time_to_close_seconds
yes_bid
yes_ask
spread
q_market
q_market_clipped_for_logit
candidate_b_market_logit
candidate_b_strike_log_ratio
candidate_b_time_log1p_hours
event_row_weight
raw_observation_refs[]
```

It also carries the state-contract, split, Candidate-B, dataset-design, and final dataset fingerprints.

It does **not** contain:

```text
result
outcome
label
y
settlement value
prediction
edge
PnL
decision
order fields
```

Locked-test feature rows may exist now because they are outcome-blind. Locked-test **labels do not**.

## Exclusion behavior

Known, structurally valid but non-usable states are preserved as exclusion records instead of being silently discarded.

Examples:

```text
state_quality:blocked_stale_data
checkpoint10_event_quarantine
checkpoint10_primitive_quarantine
partition_boundary_embargo
```

A malformed state, unknown event, inconsistent split, regime mismatch, duplicate state ID, or timing inconsistency is not treated as an ordinary exclusion. Those conditions fail dataset construction because they indicate a broken contract rather than a known quality state.

## Event weighting

A single KXBTCD event can contain many strike markets and many sampled timestamps. If every row received weight 1, an event with more captured rows would have more influence on training and evaluation.

The builder therefore assigns:

```text
event_row_weight = 1 / number_of_eligible_rows_for_that_event
```

so:

```text
sum(event_row_weight within each event) = 1
```

Later training and scoring use an equal-event top-level objective. This does not make events IID; day/week counts still need to be reported because nearby hourly BTC events can be serially dependent.

## Benchmark A — raw market midpoint

Benchmark A requires no training:

```text
q_market = (yes_bid + yes_ask) / 2
```

The raw midpoint is retained exactly in the pre-outcome dataset. Candidate B must beat this market-implied probability benchmark on the predeclared validation metric before the locked test is opened.

## Candidate B — exact learned specification

Candidate B is intentionally low dimensional:

```text
model_id = kxbtcd_market_context_logistic.v1
```

It has an intercept and exactly three learned inputs.

### Feature 1 — market logit

For numerical finiteness only:

```text
q_clip = clip(q_market, 0.001, 0.999)
market_logit = ln(q_clip / (1 - q_clip))
```

The original `q_market` remains separately preserved. The `0.001/0.999` clipping is part of the frozen Candidate-B transform and cannot be retuned after outcomes are viewed.

### Feature 2 — fixed-scale strike transform

```text
strike_log_ratio = ln(strike_dollars / 100000)
```

`100000` is a fixed numerical anchor, not a learned market forecast. Using a ratio and logarithm makes coefficient scale more stable than feeding a six-digit dollar strike directly into the optimizer.

The original strike remains explicit in every dataset row.

### Feature 3 — fixed time-to-close transform

```text
time_log1p_hours = ln(1 + time_to_close_seconds / 3600)
```

This preserves `0 -> 0`, compresses very long horizons, and gives the model an explicit smooth representation of time to settlement.

The original time-to-close remains explicit in every dataset row.

### Linear predictor

Candidate B is:

```text
z = beta0
    + beta1 * market_logit
    + beta2 * strike_log_ratio
    + beta3 * time_log1p_hours

p_yes = 1 / (1 + exp(-z))
```

There are no interactions, polynomial terms, tree splits, neural layers, or external reference-feed features in Candidate B.

## Regularization and training objective

Candidate B uses L2 regularization on the three non-intercept coefficients. The intercept is not penalized.

The only allowed penalty values are:

```text
lambda in {0.01, 0.1, 1, 10}
```

The later fitter must minimize:

```text
mean_over_events(
    mean_binary_log_loss_within_event
)
+ lambda / 2 * (
    beta1^2 + beta2^2 + beta3^2
)
```

There is no class reweighting.

Defining the objective rather than a package-specific `C` parameter prevents a library default from silently changing the meaning of regularization.

No fitting implementation is included in this slice.

## Validation selection rule

All four lambda candidates may be fit on the training partition later.

Validation chooses the lambda with the lowest:

```text
event-weighted log loss
```

If two or more lambda values have exactly the same validation loss, choose the **larger lambda**, meaning stronger regularization.

This tie-break is predeclared and deterministic.

## Locked-test entry gate

Candidate B may advance to the locked test only when:

```text
Candidate-B validation event-weighted log loss
<
raw-midpoint validation event-weighted log loss
```

A tie does not pass.

Brier score, calibration tables, time-to-close slices, and strike-context slices remain secondary diagnostics. They cannot override a failure on the primary validation gate after the fact.

If Candidate B fails this gate, locked-test outcomes stay closed for Candidate B and the result is recorded as a failed baseline hypothesis.

## Final refit rule

Only if the validation gate passes:

1. freeze the selected lambda;
2. refit the same unchanged Candidate-B specification using train + validation events;
3. open the new locked-test labels once;
4. perform one final locked-test evaluation.

Changing features, transforms, regularization grid, label rules, weighting, or model form after locked-test outcomes are opened consumes that test and requires a new chronological experiment.

## Why external BTC features are deliberately absent

The shared BTC-state layer remains useful architecture, but Candidate B is not allowed to use Coinbase, Kraken, or BRTI-return features yet.

This creates a clean causal research sequence:

```text
A: raw KXBTCD midpoint
B: midpoint + KXBTCD strike/time context
C: B + a small predeclared set of shared BTC-state features
```

If Candidate B cannot improve the market midpoint, adding many external signals immediately would make it harder to identify why a later model appears to work or fail.

Sub-second cross-feed lead/lag remains blocked regardless.

## Facts, hypotheses, and unresolved questions

### Facts fixed by the current project record

- Checkpoint-10's old development and holdout outcomes have been viewed.
- All 20 Checkpoint-10 source events are quarantined from this new experiment.
- KXBTCD is the first modeling/validation head.
- Raw preservation and exact lineage remain mandatory.
- The current clock evidence does not authorize sub-second cross-source lead/lag inference.
- Current authorization remains read-only.

### Hypothesis to test later

Candidate B tests whether a small amount of explicit KXBTCD strike/time context improves calibrated settlement probability relative to the raw market midpoint.

That is an empirical hypothesis, not an assumption and not a profitability claim.

### Unresolved until later slices

- exact results of the historical raw-first materialization run under the frozen materialization plan;
- number of eligible rows/events after raw quality gates and embargoes;
- fitted coefficients for each lambda;
- validation performance;
- whether the validation gate passes;
- locked-test performance, which remains unopened;
- whether external BTC-state Candidate C is justified.

## Implementation and tests

`src/kxbtcd_preoutcome_dataset.py` provides:

- deterministic Candidate-B feature transforms;
- exact Candidate-B specification and fingerprint;
- outcome-blind dataset construction;
- state/split/timing consistency checks;
- explicit exclusion auditing;
- equal-event row weighting;
- deterministic dataset fingerprinting;
- the frozen lambda selection rule;
- the frozen validation-to-locked-test gate.

The tests cover contract identity, market-level identity, explicit historical reconstruction view, rejection of live-view rows from the offline dataset, transform clipping/scaling, all three partitions, locked-test label absence, quarantine behavior, state-quality exclusion, timing consistency, duplicate IDs, outcome leakage, event weights, deterministic fingerprints, the exact lambda grid/tie-break, and the strict validation gate.

## Next step after canonical validation

Do **not** fit Candidate B immediately.

Use the separately frozen `KXBTCD_PREOUTCOME_MATERIALIZATION_PLAN.md` to implement the raw-first historical collector and produce these rows. Then freeze the resulting dataset fingerprint, coverage, and partition counts. Only after that artifact is validated should training labels be attached to the train partition.
