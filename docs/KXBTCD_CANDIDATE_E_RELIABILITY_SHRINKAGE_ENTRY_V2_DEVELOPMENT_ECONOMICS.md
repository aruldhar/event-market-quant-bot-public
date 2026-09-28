# Candidate-E Reliability-Shrinkage Strategy-v2 — Opportunity Result Freeze and Development Economics Predeclaration

## Checkpoint

**Checkpoint 21N-G — Freeze Strategy-v2 Opportunity Audit and Development Economics**

## Frozen opportunity-audit result

The 21N-F outcome-independent audit completed successfully.

- audit fingerprint: `b0971d51ac76fc26402dfbab49fde85167cb0bb4153069b80d1db2dbaccdcf20`
- result directory: `data/analysis/kxbtcd_candidate_e_reliability_shrinkage_entry_v2_opportunity_audit/20260831T061534Z`
- alpha-event selection SHA-256: `ff4aa15a61f8b98506a35626113bd60e4cc9c1758a3504065ed452074e6e6790`
- exact Strategy-v1 reproduction SHA-256: `3c43d7c489dac9d761f442f594af24e1a52d478fe2e3bfdfc9e92eb84e636121`
- Strategy-v1 alpha=1 reproduction: exact
- settlement outcomes used by opportunity audit: no
- realized P&L calculated by opportunity audit: no

Frozen opportunity counts:

| alpha | entries | H1_OOF | H2 | H3 | changed vs alpha=1 | opportunity status |
|---|---:|---:|---:|---:|---:|---|
| 0.25 | 15 | 3 | 6 | 6 | 99.39% | sample-ineligible |
| 0.50 | 276 | 75 | 102 | 99 | 82.68% | economics-eligible |
| 0.75 | 591 | 203 | 191 | 197 | 46.83% | economics-eligible |
| 1.00 | 820 | 308 | 254 | 258 | 0% | prior Strategy-v1 reference |

The materiality hypothesis is therefore resolved: moderate shrinkage is not a
cosmetic change. Alpha 0.50 and 0.75 materially change the decision set and have
enough development opportunity coverage to justify a frozen economic comparison.

Opportunity-audit result-closeout fingerprint:

`ff2a021063155c6fdfd012818363faccc2906468471d61b49e61572740606dcd`

## Which alphas may now be scored

Exactly two:

- `alpha = 0.50`
- `alpha = 0.75`

No other alpha may be scored in this development experiment.

### Alpha 0.25

**Outcome scoring is prohibited.**

Reason: only 15 total entries and 3/6/6 across H1_OOF/H2/H3. It failed the
predeclared opportunity-coverage gate before outcomes were opened.

### Alpha 1.00

**Outcome rescoring is prohibited.**

Reason: alpha=1 exactly reproduces Strategy-v1's zero-cent opportunity policy.
Its development economics are already exposed and Strategy-v1 failed. The frozen
reference is:

- base mean P&L/event: `-0.004836575875486381322957198444`
- +1c mean P&L/event: `-0.007972762645914396887159533074`

It is a reference, not a Strategy-v2 candidate.

## Frozen economic calculation

For a selected one-contract entry, hold to settlement.

Base purchase price is the quote already frozen in the 21N-F selection artifact.

For each adverse-price stress `s`:

`P_stress = quoted_purchase_price + s`

Recalculate the standard Kalshi entry fee at `P_stress`:

`fee = ceil_cent(0.07 * P_stress * (1 - P_stress))`

Payout:

- YES: `outcome`
- NO: `1 - outcome`

Realized quoted-screening P&L:

`PnL = payout - P_stress - fee`

Abstentions contribute zero P&L and zero deployed capital.

Stress menu:

- +0c
- +1c
- +2c
- +3c

+1c is the advancement stress. +2c and +3c are diagnostics.

If any selected trade produces a stressed purchase price outside `[0,1]`, that
alpha/stress scenario fails closed as invalid. Trades may not be capped, omitted,
or imputed.

## Primary metric

**Mean net P&L per all 2,570 development events, including abstentions as zero.**

This keeps a selective strategy honest: abstaining more often cannot make the
primary denominator disappear.

Secondary diagnostics include total P&L, P&L/trade, deployed capital, return on
deployed capital, win rate, maximum chronological drawdown, worst trade,
stage results, five chronological blocks, side/TTC/role composition, and stress
results.

## Chronological development gate

Sort the 2,570 events by:

1. `event_close_time_utc` ascending;
2. `event_ticker` ascending.

Split into five fixed blocks of 514 events: B0-B4.

An alpha passes development only if **all five** are true:

1. base pooled mean P&L/event > 0;
2. +1c stressed pooled mean P&L/event > 0;
3. base mean P&L/event > 0 in at least 4 of 5 blocks;
4. base newest block B4 mean P&L/event > 0;
5. base H3 mean P&L/event > 0.

Zero is not positive.

## Winner rule

If neither alpha passes: `FAIL_NO_ALPHA`.

If exactly one passes: select it.

If both pass: choose the alpha with the **higher +1c stressed pooled mean
P&L/event**.

Exact numeric tie: choose the **lower alpha**, because it is the more
conservative reliability adjustment.

No post-outcome alpha repair is permitted. Do not inspect 0.60, 0.65, 0.70,
0.80, intermediate values, new thresholds, TTC filters, side filters, roles,
price bands, or edge buckets and call them validated.

## Future C1+C2 confirmation

C1+C2 Strategy-v2 economics are **not authorized now**.

Only after one alpha passes development, is selected by the frozen rule, and the
development result is separately frozen may a future checkpoint authorize one
C1+C2 strategy-economic confirmation.

The selected alpha must remain fixed.

Future confirmation gate:

1. base pooled mean P&L/event > 0;
2. +1c stressed pooled mean P&L/event > 0;
3. at least 4/5 chronological 200-event blocks positive at base;
4. newest block positive at base.

If confirmation fails, reject Strategy-v2. Do not repair it on C1+C2.

C1+C2 is fresh **strategy-economic** evidence only; its outcomes were previously
used for other model research.

## Interpretation boundary

This experiment is a **quoted-entry economic screening**, not a historical fill
simulation. It does not model complete depth, queue priority, latency,
partial fills, missed fills, or live order behavior. Therefore even a PASS does
not satisfy the project's paper-strategy eligibility gate and does not establish
profitability.

## Safety

- C1+C2 Strategy-v2 P&L: closed
- C3: sealed
- protected 4,676-event reserve: sealed
- network: none
- paper broker: none
- demo execution: none
- real execution: none
- orders: none

Development-economics predeclaration fingerprint:

`139435ffb43d51d09afa4154aeba2fe9c22cb82b5b7edd435516d4ab71e2c55f`
