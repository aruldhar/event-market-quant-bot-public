# KXBTCD Candidate-E Spot-Relative Liquidity Convergence/Re-entry V2

## Checkpoint 21N-X — Exact Predeclaration

Strategy ID:

`kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2`

Predeclaration fingerprint:

`3e44c6ce3b9e420db3cf0dd52c2b64030ae99901c491d9cf0bc15617930ef8ae`

## Why V2 exists

Continuous v1 is permanently closed as non-evaluable. Its five frozen statistical
structural roles never produced a valid two-sided execution state on the owned
July 10 replay.

Checkpoint 21N-W then found that two-sided liquidity was organized around causal
BTC spot / ATM: among 177 active minute cross-sections, the nearest two-sided
market was within five strike ranks of ATM in 177/177.

V2 therefore changes the **tradable market universe**, not Candidate E.

## Frozen market universe

At every causal decision timestamp:

1. use the immediately preceding fully completed Coinbase BTC-USD one-minute close;
2. sort the full KXBTCD event ladder by numeric strike;
3. define ATM as the strike closest to BTC spot, with ties going to the lower
   strike and then ticker;
4. admit ATM plus at most five strike ranks below and five above;
5. clip at ladder boundaries without replacement.

Maximum live candidate markets: **11**.

Liquidity does not choose ATM or window membership. It is used only after the
causal universe is known to determine whether a market is actually evaluable and
executable.

The ±5 radius is a simple coverage-oriented development choice. It is not claimed
optimal and was not selected from Candidate-E economics.

## Candidate E

Candidate E remains exactly frozen:

- candidate `kxbtcd_btc_distance_offset_logistic.v1`;
- Champion-Final fingerprint `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`;
- beta distance `0.014939489324405949`;
- no refit;
- no recalibration;
- no new features.

A scored market outside the old q10/q30/q50/q70/q90 roles is explicitly labeled
`nonstructural_spot_window_domain_extension`.

## Execution policy

V2 inherits the continuous-v1 mechanics:

- entry scan T-55 through T-2;
- 1 contract;
- valid uncrossed two-sided YES book;
- at least 1 contract at the relevant purchase level;
- exact fixed-point fees;
- thresholds 0/1/2/3/5 cents as parallel **development sensitivities**;
- 0/500/1000 ms latency scenarios;
- IOC limit entry;
- entry-time fair-value convergence liquidation;
- one exit attempt;
- no stop loss;
- no force exit;
- no averaging or top-up;
- maximum two filled entries.

The only re-entry extension is that a fully exited reference trade may re-arm
when its reference market causally leaves the current ATM±5 window. Missing BTC
or an unavailable/invalid reference book while the market remains inside the
window does not count as re-arm.

## July 10 development

The four owned July 10 events remain development/mechanics evidence only.

V2 may score the newly allowed nonstructural markets there only **after a separate
implementation freeze**.

The required order is outcome-blind path first, then a separately frozen outcome
evaluator before any July 10 settlement labels are opened. No July 10 result may
be called fresh validation or generalized profitability evidence.

## Fixed fresh Candidate-E domain-extension set

Fresh targets are strictly post Champion-Final freeze and are fixed before
source acquisition or scoring:

- August 19, 21, 23, 25, 27, 29, 2026;
- four hourly closes per date at 17:00, 18:00, 19:00, 20:00 UTC;
- 24 events total;
- no replacement events.

If a target identity or expected close does not match, or the source cannot
support it, that target is unavailable and counts against the gate.

### Source adequacy gate

Each target has 54 exact minute cross-sections from T-55 through T-2.

Before **any fresh outcome access**, require:

- at least 20/24 materialized events;
- at least 16 events with >=27/54 usable **nonstructural domain-extension**
  cross-sections;
- at least 60% of the fixed 1,296 cross-sections usable, i.e. >=778.

A usable domain-extension cross-section requires causal Coinbase state plus at
least one nonstructural ATM±5 market with a verified valid uncrossed two-sided
book.

Failure stops before fresh outcomes.

### Fresh predictive gate

Primary scored rows are nonstructural ATM±5 rows only. Old structural-role rows
are diagnostics.

Candidate E advances only if:

- pooled event-equal log loss is strictly lower than raw midpoint;
- pooled event-equal Brier is non-worse than raw midpoint;
- Candidate E wins log loss in at least 4/6 fixed date blocks;
- the newest August 29 block has at least one predictive-eligible event and is
  a log-loss win.

No refit or recalibration is permitted.

This gate validates only the Candidate-E **domain extension**. It does not by
itself establish executable strategy profitability.

## Future economic validation

21N-X does not authorize fresh strategy P&L.

After July development, one threshold/latency economic policy must be separately
selected and frozen before any fresh strategy-economics claim.

Historical replay must continue to account for fees, spread, available depth,
latency, partial fills, missed fills, and model uncertainty.

## Source acquisition and safety

No network collection or source purchase occurs in 21N-X.

For the fixed fresh targets, future Predexon acquisition may use promo/free
credit only unless the user separately authorizes a charge. Missing target data
may not be replaced.

The project remains read-only. Orders, cancellations, paper broker behavior,
demo execution, and real-money execution remain prohibited.
