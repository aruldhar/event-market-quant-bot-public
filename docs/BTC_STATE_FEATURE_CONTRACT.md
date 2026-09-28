# Shared BTC-State Feature Contract

Status: **Checkpoint 12 initial contract design — read-only, model-free, execution-free**
Schema family: `btc_state_feature_contract.v1`

## Purpose

Checkpoint 11 accepted a shared BTC-state research architecture with separate product heads:

- **KXBTCD** is the primary modeling/validation head.
- **KXBTCPERP** is a secondary read-only return/volatility/microstructure head.
- Raw/reference BTC observations and carefully defined BTC-state features may be shared.
- Product labels, model outputs, valuation/economics, and decision policies remain separate.
- No joint multitask model is authorized.

This document defines the minimum data contract before any new Checkpoint-12 model is implemented.

The guiding rule is:

> **BTC facts may be shared; product meaning must not be shared implicitly.**

A Coinbase BTC observation can describe BTC state for multiple research heads. A KXBTCD settlement label cannot become a KXBTCPERP label, and a KXBTCPERP future return cannot become a contemporaneous KXBTCD feature.

## Six-layer separation

### 1. Raw/source observations

Raw data must be persisted before transformation under the project's existing raw-first rules.

The shared contract does not replace the raw archive. It defines an immutable reference descriptor carrying at least:

```text
raw_observation_id
source_id
instrument_id
source_session_id
source_sequence_or_message_id      # nullable when unavailable
source_event_time_utc              # nullable when unavailable
relay_or_publication_time_utc      # nullable when unavailable
local_receive_utc
local_receive_monotonic_ns
raw_payload_reference
raw_payload_sha256
```

Source identity must remain explicit. A Coinbase-derived feature and a Kraken-derived feature are not interchangeable just because both describe BTC/USD.

### 2. Synchronized BTC state with explicit availability view

A state row must say whether it is a live first-seen state or an offline historical reconstruction. This prevents a historical candle downloaded today from being mistaken for evidence that the live system actually observed it at that historical instant.

Required common fields:

```text
state_id
product_head
state_view
as_of_utc
as_of_local_monotonic_ns
alignment_epoch_id
state_quality
clock_health_status
raw_observation_refs[]
btc_features[]
source_age_seconds_by_source{}
product_context{}
```

Every feature carries its own:

```text
feature_id
source_id
instrument_id
feature_class
value
source_observation_refs[]
lookback_seconds
lead_lag_seconds
```

The feature's raw references must be included in the parent state's raw lineage.

#### State availability view

Exactly two views are allowed in the first contract:

```text
live_first_seen
historical_reconstructed
```

`live_first_seen` means the row represents information first observed by the running system. For that view, local monotonic receipt time remains the controlling same-machine causal ordering mechanism.

`historical_reconstructed` means the row was reconstructed later from preserved or historical source data. Its `as_of_utc` is the source event/candle time being analyzed, while `as_of_local_monotonic_ns` records when the historical information became available to the reconstruction process. That monotonic value must **not** be interpreted as proof of historical live availability.

This distinction lets offline historical modeling proceed without weakening the existing live-causal timing policy. `validate_state_for_live_causal_use()` rejects every `historical_reconstructed` state.

#### Causal timing rule

The existing time-alignment policy remains controlling. A live feature observation can be used only after it was locally available. Local monotonic time is the primary same-machine causal ordering mechanism for the live first-seen view.

No state contract field allows a future label, settlement outcome, model prediction, economics result, or decision action to masquerade as a state feature.

#### State quality

A state may be preserved for audit with a blocked condition such as:

```text
blocked_clock_health
blocked_continuity_gap
blocked_stale_data
blocked_source_unavailable
blocked_schema_drift
blocked_incomplete_state
```

However, `validate_state_for_model_use()` fails closed unless:

```text
state_quality == "usable"
```

This separates "we preserved the observation" from "the observation is eligible for modeling."

### KXBTCD product context

For KXBTCD, the following are explicit state variables:

```text
event_ticker
market_ticker
settlement_regime_id
strike_dollars
time_to_close_seconds
yes_bid
yes_ask
midpoint
spread
```

`market_ticker`, `strike_dollars`, and `time_to_close_seconds` are mandatory. `market_ticker` is the exact binary-contract identity inside the event and is required so later labels cannot be joined only at event level. They must not be inferred only from ticker text or hidden inside later model code.

The quote fields must satisfy:

```text
yes_bid <= yes_ask
midpoint = (yes_bid + yes_ask) / 2
spread = yes_ask - yes_bid
```

This gives the first KXBTCD baseline a clean market-implied probability benchmark while keeping quote validation separate from labels.

### KXBTCPERP product context

The first shared contract intentionally keeps the secondary head minimal:

```text
instrument_id
mark_or_mid_price
```

Funding, basis, leverage, margin, liquidation, fee, depth, and microstructure fields can be added later only when the KXBTCPERP baseline question requires them. This avoids letting the secondary product expand the first KXBTCD contract unnecessarily.

### Sub-second lead/lag block

Sub-second lead/lag features are explicitly rejected by `btc_state_feature_contract.v1`.

For example, the following is invalid while the clock-health policy remains unresolved:

```text
feature_class = "lead_lag"
lead_lag_seconds = 0.25
```

This does **not** claim that a 250 ms relationship is absent. It means the current project timing evidence is not sufficient to make that causal feature claim safely.

Slower source-specific contemporaneous returns or volatility features may be represented when they satisfy the existing local-causal timing and source-quality rules.

### 3. Product-specific labels

Labels are separate objects and are prohibited from the synchronized state schema.

#### KXBTCD

The first supported label is:

```text
label_type = "kxbtcd_settled_yes"
value in {0, 1}
```

Required context includes:

```text
event_ticker
market_ticker
settlement_primitive_id
settlement_regime_id
```

The label source remains Kalshi's finalized market result with exact raw lineage. Coinbase, Kraken, BRTI, or another auxiliary source does not inherit settlement-label authority.

#### KXBTCPERP

The contract reserves separate labels for:

```text
forward_return
realized_volatility
```

with an explicit horizon. Exact horizons are **not selected by this contract**.

### 4. Model outputs

Model output objects are separate from both state and labels.

For KXBTCD, the first supported output is:

```text
output_type = "p_yes"
0 <= value <= 1
```

The output also carries:

```text
model_id
model_version
state_id
training_window_id
created_at_utc
```

KXBTCPERP output types remain separately named (`expected_forward_return`, `expected_realized_volatility`) so a generic `prediction` field cannot silently change meaning across heads.

### 5. Product-specific valuation/economics

Forecasting and economics remain distinct.

A KXBTCD model may estimate:

```text
p_yes = 0.63
```

A downstream economics layer may compare that forecast with an actual executable-side price and later account for:

```text
fees
spread
available depth
latency
partial fills
missed fills
slippage
model uncertainty
```

Those items affect economic attractiveness. They do not become probability labels merely because they matter for trading.

The KXBTCPERP economics layer will additionally need funding, margin/leverage, and liquidation mechanics when that head reaches its own economic evaluation.

No execution fields or broker actions are authorized by this contract.

### 6. Decision policy

The current decision layer is read-only research classification only.

Allowed examples include:

```text
no_signal
research_yes_candidate
research_no_candidate
research_long_candidate
research_short_candidate
blocked_data_quality
blocked_clock_health
blocked_policy
```

`place_order`, cancellation, transfers, demo execution, paper-broker actions, and real-money execution are outside the schema and remain prohibited.

## What this first implementation does

`src/btc_state_feature_contract.py` provides deterministic validators for all six layers and a contract fingerprint.

It does **not**:

- collect new data;
- alter the current raw archive;
- open KXBTCD labels;
- reuse the Checkpoint-10 holdout;
- fit a model;
- select a Coinbase/Kraken/BRTI feature set;
- implement a KXBTCPERP model;
- calculate trading P&L;
- place, cancel, or simulate orders.

## Tests required by this slice

`tests/test_btc_state_feature_contract.py` verifies that:

- the contract fingerprint is deterministic;
- raw lineage is required;
- feature source identity is required;
- feature raw references must exist in parent state lineage;
- KXBTCD strike is mandatory;
- KXBTCD time-to-close is mandatory;
- future/label leakage is rejected;
- blocked data-quality states fail closed for model use;
- sub-second lead/lag features are rejected;
- slow contemporaneous source features do not require a false sub-second clock claim;
- KXBTCD quote arithmetic is internally consistent;
- KXBTCD labels remain separate and binary;
- KXBTCD model probabilities remain within `[0, 1]`;
- decision objects cannot become order actions.

## Facts, assumptions, hypotheses, and unresolved questions

### Accepted facts / architecture

- The BTC product preselection gate selected a shared BTC-state layer with separate KXBTCD and KXBTCPERP heads.
- KXBTCD is the primary modeling/validation head.
- KXBTCPERP remains a secondary read-only head.
- The Checkpoint-10 monotone v1 holdout has been opened and must not be reused as a new untouched test set.
- Current clock evidence does not support sub-second cross-source lead/lag claims.
- The project remains read-only.

### Contract assumptions

- Product-specific market context can coexist beside shared BTC features as long as the namespace and schema boundary remain explicit.
- A strict exact-key validator is preferable in this first version because silent schema expansion would weaken leakage protection.

### Hypotheses for later evaluation

- A simple KXBTCD state-aware model may improve proper scoring relative to the raw market midpoint.
- Slow external BTC-state variables may add incremental information beyond KXBTCD market state, strike, and time-to-close.

Neither hypothesis has been validated by this contract.

### Unresolved

- the final Checkpoint-12 KXBTCD observation schedule;
- the new chronological train/validation/locked-test boundaries;
- the exact external reference source set, if any;
- source-specific staleness thresholds for those features;
- the first KXBTCPERP forward-return / volatility horizons;
- the clock-health policy required before sub-second lead/lag research can be enabled.

## Next implementation step after acceptance

Freeze a **new KXBTCD chronological dataset and evaluation split contract** that:

1. excludes all Checkpoint-10 source clusters from the new evaluation universe;
2. groups every strike from the same settlement primitive/event into one partition;
3. uses chronological time blocks rather than random row splitting;
4. declares train, validation, embargo, and locked-test boundaries before outcomes are used for model selection;
5. fingerprints the split before implementing the first learned KXBTCD baseline.

No model should be implemented before that split contract is accepted.

## Checkpoint-12 identity refinement before canonical closeout

While wiring the first KXBTCD pre-outcome dataset, the uncommitted v1 draft was found to need two refinements before becoming canonical: exact binary-contract identity (`market_ticker`) and an explicit `state_view` separating `live_first_seen` from `historical_reconstructed`.

Frozen contract fingerprint after that correction:

```text
2739be9af27200a4a2ca8d189bc93d2f3d3349f6b3524f6b919e632fcf9d3668
```

These corrections do not expand modeling scope or authorization. They prevent an event-level join from being mistaken for a market-level label join and prevent reconstruction-time receipt from being mistaken for historical live causality.
