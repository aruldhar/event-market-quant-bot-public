# Candidate-E Executable Convergence-Liquidation v1 — Simulator Implementation

## Checkpoint 21N-R

**Purpose:** implement and freeze the already-predeclared historical execution simulator **without opening July 10 settlement outcomes and without calculating realized P&L**.

Implementation fingerprint:

`6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf`

Bound parents:

- 21N-Q strategy fingerprint: `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`
- 21N-Q1 fee-accounting amendment: `5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1`
- Champion-Final: `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- parent checkpoint: `7a8a041b85f32952a734324d214804ece3c88c88`
- parent receipt: `78b86fa0cc18c3a7a232fc65be593229fd7bc092`

## What is being implemented

The simulator converts a frozen Candidate-E signal plus a verified historical Predexon book path into a deterministic execution path:

`verified decision book`
→ `Candidate-E fair probability`
→ `threshold-qualified side`
→ `latency`
→ `IOC entry`
→ `full / partial / missed fill`
→ `verified post-entry monitoring`
→ `fair-value convergence trigger`
→ `one IOC liquidation attempt`
→ `settlement-fallback quantity`

The module deliberately stops there. It has no settlement-label reader and no realized-P&L function.

## Inputs

The pure simulator accepts:

1. a verified ticker replay built from free snapshots plus paid Predexon deltas;
2. validated KXBTCD structural market identity and strike;
3. an exact Candidate-E TTC decision timestamp;
4. the frozen Coinbase-primary BTC spot state for that anchor;
5. one of the frozen thresholds `0c / 1c / 2c / 3c / 5c`;
6. one of the frozen latency scenarios `0 / 500 / 1000 ms`;
7. the event close timestamp.

Real July 10 input binding is **not** performed in 21N-R. That is the next outcome-blind checkpoint.

## Reused frozen logic

21N-R does not invent a new probability model or strike sampler.

It reuses:

- Candidate-E `market_logit_offset()` and BTC-distance feature helpers;
- Champion-Final `beta_distance = 0.014939489324405949`;
- the existing nearest-rank-half-up structural strike function;
- the existing Predexon snapshot/delta reconciliation and verified-segment logic.

Candidate-E probability remains:

`logit(pE) = logit_clipped(q_market) + beta_distance * 10000 * ln(S/K)`

where the market logit clip remains `0.001`.

## Exact book-side mapping

For a reconstructed YES book:

- buy YES consumes YES asks;
- sell YES consumes YES bids;
- buy NO consumes `1 - YES bid` levels;
- sell NO consumes `1 - YES ask` levels.

The NO quantities are inherited from their complementary YES levels.

A signal requires a valid uncrossed two-sided YES book. The **best decision-time purchase price level itself** must display at least `1.00` contract. Deeper cumulative depth cannot rescue a shallow best level for signal eligibility.

## Signal edge

For each side:

`signal edge = entry-time side fair probability - decision purchase price - direct-member one-fill entry fee`

The signal fee is calculated with the same amended fixed-point accounting used by the IOC engine. The old whole-cent quoted-entry fee helper is not reused.

Thresholds remain parallel sensitivity policies. No threshold is selected from the four July 10 events.

## IOC entry

The decision-time best purchase ask is the IOC limit.

At arrival:

- consume visible purchase asks best to worse;
- fill only at prices equal to or better than the decision limit;
- price improvement is allowed;
- worsening beyond the limit is prohibited;
- stop after `1.00` contract or available eligible depth is exhausted;
- cancel the unfilled remainder;
- report `FULL`, `PARTIAL`, or `MISSED`.

If the complete decision→arrival interval is not inside one verified replay segment, entry is `SOURCE_UNAVAILABLE`. The strategy does **not** fall through to a later TTC anchor.

## Fixed-point fee and cash ledger

For every synthetic fill of quantity `C` at price `P`:

`model_fee = 0.07 * C * P * (1-P)`

`trade_fee = ceil_to_$0.000001(model_fee)`

Signed gross revenue is:

- buy: `-P*C`
- sell: `+P*C`

Then the direct-member cash change is aligned to `$0.0001` with the 21N-Q1 order-local rounding accumulator and rebate.

The accumulator:

- carries across price levels within one IOC;
- resets between the entry IOC and exit IOC.

Predexon does not reveal individual resting-order partitions. The frozen deterministic approximation remains **one synthetic fill per consumed price level**. This is execution uncertainty, not an observed fact about matching-engine fill partitioning.

## Historical replay state convention

### Right-continuous millisecond state

Predexon timestamps are millisecond-granular, while snapshots can occur inside a same-millisecond delta batch.

21N-R freezes this ambiguity resolution:

> For each verified segment, collapse all reconstructable evidence with the same millisecond timestamp to one final book state. A query at timestamp `t` sees that final state for `t`.

The strategy therefore cannot exploit transient same-millisecond states whose exact timing relative to the decision instant is not identifiable.

Snapshots remain authoritative boundary states. Failed adjacent reconciliation remains a hard boundary.

## Historical market-impact assumption

A counterfactual IOC consumes the visible arrival depth used to determine its own fill.

After that order, later observed historical book states remain unchanged.

This is the frozen **small-order non-impacting future-book assumption**. It is required because the historical archive cannot reveal the counterfactual market path that would have followed our hypothetical order.

This assumption is **not** evidence that one contract has zero market impact. It must remain reported as execution-model uncertainty.

## Liquidation trigger

After a nonzero entry fill, the trigger scan starts at the **entry-arrival book state**, then checks each later distinct reconstructed millisecond state through event close or the end of the current verified segment.

At each state, the simulator hypothetically sells the **entire open position** through visible side bids with no artificial price floor.

A trigger exists only when:

1. the entire position can be filled from visible depth; and
2. net hypothetical cash after exit fees/rounding is at least:

`entry-time side fair probability * open quantity`

The first state meeting both requirements is frozen as the trigger.

The actual exit limit equals the worst bid consumed by that full hypothetical liquidation.

## Actual liquidation

Actual exit arrival is:

`trigger time + the same scenario latency used for entry`

The entire trigger→arrival interval must remain within one verified segment and arrival may not occur after event close.

At arrival:

- submit one IOC sell;
- consume bids best to worse only at prices at or above the trigger-time limit;
- report full / partial / missed exit;
- no retry is permitted.

Any unfilled remainder is marked as settlement-fallback quantity.

If no trigger occurs and the verified segment reaches event close, the full open quantity falls to settlement.

If a replay boundary occurs before a trigger can be established and before close, the liquidation branch is `SOURCE_UNAVAILABLE`, not assumed hold and not assumed missed.

## Matched hold control

Every source-valid realized entry fill gets a hold control with exactly the same filled quantity.

Thus the future economic comparison can isolate:

`same entry + liquidation policy`

versus:

`same entry + hold to settlement`

No settlement result is attached in this checkpoint.

## Failure modes

The implementation fails closed or marks source-unavailable for:

- crossed or one-sided decision book;
- structural role outside the frozen five roles;
- invalid TTC / threshold / latency;
- off-grid price or quantity;
- negative reconstructed resting depth;
- decision or execution interval outside one unique verified segment;
- monitoring gap before close;
- trigger→exit arrival segment failure;
- exit arrival after close;
- parent fingerprint drift;
- Champion-Final drift;
- fixed-point accounting identity failure.

It never interpolates an unavailable book state and never skips a replay boundary.

## Testing plan

Dedicated synthetic tests cover:

- direct-member single-fill fee arithmetic;
- multi-fill accumulator/rebate behavior;
- IOC full/partial/missed book walking;
- YES/NO complementary book mapping;
- structural nearest-rank-half-up selection;
- Candidate-E nesting at zero BTC/strike distance;
- one-level decision depth requirement;
- first-anchor / maximum-edge / deterministic tie selection;
- latency gap failure;
- price improvement versus worsening beyond limit;
- full-depth liquidation trigger;
- partial exit with settlement fallback;
- no-trigger hold when the verified path reaches close;
- monitoring-gap source failure;
- matched-hold quantity identity;
- right-continuous same-millisecond replay collapse;
- implementation-freeze parent, safety, and accounting invariants.

## Facts, assumptions, hypotheses, unresolved questions

### Facts

- Candidate E is frozen and is not refit.
- The 21N-Q strategy and 21N-Q1 accounting amendment are frozen.
- The July 10 archive contains only four independent hourly events.
- Failed replay reconciliation creates hard source boundaries.
- Outcomes and strategy P&L remain unopened at 21N-R.

### Assumptions

- direct-member `$0.0001` balance accounting is the primary counterfactual account regime;
- one synthetic fill per consumed price level approximates unknown resting-order partitions;
- later historical books are exogenous after a one-contract counterfactual IOC;
- final state per millisecond is the conservative deterministic treatment of same-ms timing ambiguity.

### Hypothesis

The executable convergence-liquidation policy may change economics relative to matched hold after realistic spread, depth, latency, fees, partial fills, missed fills, and source gaps.

This is not yet tested in 21N-R.

### Unresolved

Four events cannot establish profitability or generalization. A fresh-event protocol remains necessary before any advancement discussion.

## Next checkpoint

**21N-S — July 10 Outcome-Blind Strategy Input and Execution-Path Materialization**

21N-S may bind the four real events to this frozen simulator and produce selected signals/fill/trigger/path diagnostics.

It must still keep settlement outcomes closed and P&L unrun.

Only after the real execution-path artifact is independently frozen should a later one-time checkpoint attach settlement labels and score economics.
