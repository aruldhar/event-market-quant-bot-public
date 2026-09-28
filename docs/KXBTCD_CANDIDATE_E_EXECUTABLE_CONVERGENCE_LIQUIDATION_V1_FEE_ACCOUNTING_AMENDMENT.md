# Candidate-E Executable Convergence Liquidation v1 — Fee-Accounting Amendment

## Checkpoint

**Checkpoint 21N-Q1 — Outcome-Blind Fixed-Point Fee-Accounting Correction**

Amendment fingerprint:

`5f44a9ee001c7854416da46a4db19cb1d53b8b25edd7f7247fd72a032eab64d1`

Base strategy predeclaration fingerprint:

`61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`

Parent 21N-Q checkpoint:

`b281be1f32e59578cf0464e2d82178b19d394d2d`

Parent 21N-Q receipt:

`09caa0a00be69112ecef83bb1e4e91751d5dc081`

## Why this amendment exists

The 21N-Q strategy logic remains accepted. During 21N-R implementation review, the official Kalshi fixed-point
fee documentation exposed an accounting-specification error in three descriptive fields of the base
predeclaration.

The base document said, in effect:

- round each synthetic-fill trade fee directly to `$0.0001`;
- floor each cash change to `$0.01`;
- use `$0.01` accumulator rebates.

That is not the exact direct-member fixed-point accounting path.

Before any July 10 settlement outcome or strategy P&L was opened, this amendment corrects only that arithmetic.

## What does **not** change

This amendment does **not** change:

- Candidate E;
- q10/q30/q50/q70/q90;
- T-55/T-50/T-45/T-40/T-35/T-30;
- one-contract intended entry size;
- 0c/1c/2c/3c/5c edge-margin menu;
- first-qualifying-anchor selection;
- 0/500/1000 ms latency scenarios;
- IOC entry limit;
- frozen entry-time Candidate-E liquidation target;
- one liquidation attempt;
- partial/missed-fill behavior;
- settlement fallback;
- matched hold control;
- replay continuity rules;
- the four-event exploratory interpretation.

## Historical applicability

The July 10, 2026 evidence occurs after the relevant fixed-point rollout:

- fractional trading began rolling out in March 2026;
- by April 17, active market responses supported fractional trading unconditionally;
- direct-member balance precision became `$0.0001` on May 28, 2026;
- the applicable fee schedule was updated July 7, 2026.

The simulator baseline models **direct exchange/API execution**, therefore the primary counterfactual member
precision is frozen to `$0.0001`.

This is an architecture assumption for the simulator. It is not a claim about an unidentified historical
customer's clearing arrangement. Any future non-direct/FCM execution path must use a separately versioned
accounting regime.

## Correct trade-fee arithmetic

For one synthetic fill of quantity `C` at price `P`:

`model_fee = 0.07 * C * P * (1-P)`

The trade-fee component is:

`trade_fee = ceil_to_0.000001(model_fee)`

Prices are exact fixed-point dollars; quantities are exact fixed-point contracts; all calculations use
`Decimal`.

## Correct direct-member cash alignment

Let signed revenue be:

- buy: `revenue = -P*C`;
- sell: `revenue = +P*C`.

For each synthetic fill:

1. `trade_fee = ceil_6dp(model_fee)`
2. `aligned_change = floor_to_0.0001(revenue - trade_fee)`
3. `rounding_fee = (revenue - trade_fee) - aligned_change`
4. add `rounding_fee` to the **order-local** accumulator
5. rebate accumulated rounding in `$0.0001` increments, capped so the current fill's net fee is never negative
6. carry the unreimbursed accumulator remainder to the next fill of the same counterfactual order

For economic accounting:

`net_fee = trade_fee + rounding_fee - rebate`

and:

`net_counterfactual_cash_change = aligned_change + rebate`

The accumulator resets between the entry IOC and the later exit IOC because they are separate orders.

## Synthetic fill partition

Predexon provides aggregate resting quantity by price level, not the partition into individual resting orders.

The already-frozen deterministic approximation remains:

> one synthetic fill per consumed price level.

The fee accumulator is carried across those synthetic fills within one IOC order.

This limitation must remain explicitly reported as execution uncertainty; it cannot be tuned from the July 10
economics.

## Signal-fee implication

At decision time the intended signal size is exactly `1.00` contract at one displayed price level.

The implementation must evaluate that hypothetical one-fill entry using the same direct-member accounting
algorithm. It must not call the old whole-cent `standard_entry_fee()` helper from quoted-entry/hold v1.

## Settlement

For a simple binary YES/NO market with quantity granularity `0.01`, a winning `$1.00 * quantity` payout is
cent-aligned. The simple binary settlement fee remains zero.

Sub-cent scalar settlement is outside this strategy's scope.

## Outcome firewall

At amendment freeze:

- July 10 strategy outcomes accessed: **0**
- strategy P&L calculated: **no**
- orders submitted: **0**
- C1/C2/C3/protected reserve access: **no**
- new Predexon purchase: **no**

This correction must be committed before 21N-R simulator implementation is frozen.
