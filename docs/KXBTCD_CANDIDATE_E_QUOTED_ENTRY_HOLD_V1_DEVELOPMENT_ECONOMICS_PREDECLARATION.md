# KXBTCD Candidate-E Quoted-Entry Hold Strategy v1 — Development Economic Evaluation Predeclaration

## Checkpoint

**Checkpoint 21N-B — Strategy-v1 Development Economic Evaluation Predeclaration and Implementation Freeze**

## Status

Design and evaluator implementation prepared **before any Strategy-v1 realized P&L is calculated**.

Strategy:

`kxbtcd_candidate_e_quoted_entry_hold_v1`

Parent Strategy-v1 fingerprint:

`5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6`

Outcome-independent opportunity-audit fingerprint:

`7175175f11bb2714d4bbfc9dc59d9d23d7be721fa0295d7ed664d598a1036ae0`

21N-B development-economics predeclaration fingerprint:

`692b7239067b3024db908fc0e0809f33f900f685faec97c45743195e19d364e5`

Candidate E remains:

`kxbtcd_btc_distance_offset_logistic.v1`

Champion-Final fingerprint:

`b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`

No probability model is refit or changed by this checkpoint.

## Why this checkpoint exists

21N-A answered an outcome-independent question: does Candidate E generate enough standard-fee quoted disagreement with Kalshi to make a historical economic test worth running?

The answer was yes.

Across 2,570 development events:

| Post-fee threshold | Enter | Abstain | Entry rate | Mean selected predicted edge |
|---|---:|---:|---:|---:|
| 0¢ | 820 | 1,750 | 31.91% | 1.38¢ |
| 1¢ | 542 | 2,028 | 21.09% | 2.20¢ |
| 2¢ | 306 | 2,264 | 11.91% | 3.10¢ |
| 3¢ | 159 | 2,411 | 6.19% | 4.00¢ |
| 5¢ | 33 | 2,537 | 1.28% | 6.15¢ |

Those figures use no settlement outcomes and no realized P&L.

The next question is:

> Under the already-frozen one-contract, first-qualifying-anchor, hold-to-settlement policy, do those displayed-quote opportunities have positive historical settlement economics after the standard entry fee, and are those economics chronologically robust enough to justify one later C1+C2 confirmation?

This checkpoint freezes that test before opening Strategy-v1 P&L.

## Facts from 21N-A

The audit is frozen under fingerprint:

`7175175f11bb2714d4bbfc9dc59d9d23d7be721fa0295d7ed664d598a1036ae0`

Frozen development scope:

- H1_OOF: 1,070 events / 31,656 Candidate-E rows
- H2: 750 events / 22,354 rows
- H3: 750 events / 22,409 rows
- total: 2,570 events / 76,419 Candidate-E rows
- side states: 152,838

Frozen threshold-selection CSV SHA-256:

`3c43d7c489dac9d761f442f594af24e1a52d478fe2e3bfdfc9e92eb84e636121`

The evaluator must consume exactly that already-selected event/threshold table. It may not reselect entries after outcomes are visible.

Observed opportunity rates increased materially in later stages, especially at higher thresholds. This is a reason to require chronological stability; it is not evidence of profitability.

## Historical probability provenance

Historical strategy evaluation must use the probability that was genuinely out-of-sample at that point in the Candidate-E lifecycle.

Development:

- H1_OOF -> original Candidate-E out-of-fold probability
- H2 -> frozen H2 out-of-sample probability
- H3 -> frozen H3 out-of-sample probability

Do **not** recompute Champion-Final probabilities on historical events that participated in the final fit and call those historical predictions.

For a later C1+C2 confirmation:

- C1 must use frozen Champion-R0 predictions created before C1 outcomes;
- C2 must use frozen Champion-R1 predictions created before C2 outcomes.

Champion-Final remains the current champion/deployment identity, while historical evaluation preserves out-of-sample lifecycle probability provenance.

## Frozen trade economics

For one selected side with binary market outcome `y`:

YES payout:

```text
payout_YES = y
```

NO payout:

```text
payout_NO = 1 - y
```

For one contract bought at price `P`:

```text
fee(P) = ceil_cent(0.07 * P * (1-P))
capital_deployed = P + fee(P)
realized_PnL = payout - P - fee(P)
```

An abstention contributes:

```text
PnL = 0
capital_deployed = 0
```

No settlement fee is added.

These remain **quoted-entry historical economics**. They do not establish that the displayed contract would have filled.

## Frozen adverse-price stress

Each already-selected trade is rescored at:

`+0¢, +1¢, +2¢, +3¢`

For stress `s`:

```text
P_stressed = P_quoted + s
fee_stressed = ceil_cent(0.07 * P_stressed * (1-P_stressed))
PnL_stressed = payout - P_stressed - fee_stressed
```

The fee is always recalculated at the stressed price.

If `P_stressed` is outside `[0,1]`:

- that trade is not capped;
- it is not dropped;
- it is not imputed;
- the entire threshold/stress scenario is marked invalid.

An invalid +1¢ scenario cannot satisfy the development gate.

The +1¢ stress is part of the advancement gate. +2¢ and +3¢ are diagnostics only.

These stresses are sensitivity scenarios, not empirical estimates of latency, queue position, depth, partial fills, or slippage.

## Frozen metrics

### Primary metric

**Mean net P&L per event, with abstentions counted as zero.**

This is primary because it prevents a very selective rule from looking strong merely because it reports only the small subset it traded.

### Secondary diagnostics

For every threshold and stress scenario:

- total net P&L;
- mean net P&L per trade;
- total capital deployed;
- return on deployed capital;
- win rate among entries;
- maximum drawdown;
- worst individual trade;
- entry count;
- abstention count.

Base-price diagnostics also report:

- H1_OOF/H2/H3 P&L per event;
- five chronological-block P&L-per-event values;
- side/TTC/structural-role fields in the event-level output.

Maximum drawdown is calculated on chronological event P&L, including abstentions as zero, with initial cumulative peak `0`.

Win rate is diagnostic only. A high win rate does not override negative expected economics.

## Frozen chronological blocks

Sort the unique 2,570 development events by:

1. `event_close_time_utc` ascending;
2. `event_ticker` ascending for an exact-time tie.

Then freeze:

- B0: events 1-514
- B1: events 515-1028
- B2: events 1029-1542
- B3: events 1543-2056
- B4: events 2057-2570

Exactly 514 events per block.

Blocks are outcome-independent and identical for all thresholds.

## Threshold eligibility

All frozen policies are scored:

`0¢, 1¢, 2¢, 3¢, 5¢`

Thresholds eligible to become the development winner:

`0¢, 1¢, 2¢, 3¢`

The `5¢` policy is **diagnostic-only** because the outcome-independent audit produced only 33 development entries. It may not win even if its realized P&L happens to look best.

This restriction is frozen before any Strategy-v1 P&L.

## Development advancement gate

For an eligible threshold to pass, **all five** conditions are required:

1. base displayed-quote pooled mean P&L per event is strictly `> 0`;
2. +1¢ stressed pooled mean P&L per event is strictly `> 0`;
3. base mean P&L per event is strictly `> 0` in at least 4 of 5 chronological blocks;
4. base mean P&L per event is strictly `> 0` in newest block B4;
5. base H3 mean P&L per event is strictly `> 0`.

Exact zero fails a positivity condition.

### Winner rule

If multiple eligible thresholds pass every condition:

1. choose the threshold with the highest **+1¢ stressed pooled mean P&L per event**;
2. exact numerical tie -> choose the higher threshold.

If no eligible threshold passes:

`FAIL_NO_THRESHOLD`

No post-outcome threshold repair, finer grid search, new anchor, new sizing rule, or re-entry/exit rule may be introduced and rescored on the same development outcomes as if predeclared.

## Why +1¢ selects the winner

Displayed-quote P&L is intentionally optimistic about actual execution.

Selecting by +1¢ stressed P&L rewards a strategy whose historical economics retain some margin after a small adverse price movement rather than choosing whichever threshold looks best at the displayed quote.

This does not mean actual slippage is 1¢.

## Later C1+C2 historical confirmation

C1+C2 strategy economics remain closed during the 21N-B development evaluator freeze.

Only if development selects exactly one threshold may a later checkpoint freeze and run C1+C2 historical confirmation.

Scope:

- C1+C2 combined: 1,000 events
- five chronological 200-event blocks
- exact selected development threshold only
- no threshold search
- no strategy redesign

Required confirmation conditions:

1. base pooled mean P&L per event `> 0`;
2. +1¢ stressed pooled mean P&L per event `> 0`;
3. base mean P&L per event `> 0` in at least 4/5 blocks;
4. newest base block mean P&L per event `> 0`.

Failure rejects this quoted-entry/hold Strategy-v1 family.

Do not repair the strategy using C1+C2 and then call the same evidence confirmation.

C1+C2 are historical confirmation, not globally fresh evidence.

## C3 and protected reserve

C3 remains sealed for Strategy-v1 economics.

The 4,676-event protected reserve remains sealed.

Neither may be used to rescue a weak development or C1+C2 result.

## Evaluator outputs

When later authorized after the implementation freeze is committed, the evaluator writes:

1. `development_economic_evaluation.json`
   - all threshold/stress metrics;
   - stage and chronological-block diagnostics;
   - frozen gate conditions;
   - selected threshold or FAIL;
   - deterministic evaluation fingerprint.

2. `development_event_pnl_scenarios.csv`
   - one event-level row per threshold/stress scenario;
   - selected trade identity;
   - outcome;
   - stressed price/fee/capital;
   - realized P&L;
   - block and stage.

3. `development_threshold_scores.csv`
   - concise gate table for all five thresholds.

4. `development_economic_receipt.json`
   - input hashes;
   - implementation hashes;
   - output hashes;
   - result fingerprint;
   - safety state.

## Failure modes

The evaluator fails closed if:

- Strategy-v1 config fingerprint/hash changes;
- opportunity-audit fingerprint changes;
- threshold-selection CSV hash changes;
- H1/H2/H3 prediction/outcome source hashes change;
- threshold/event counts differ from the 21N-A audit;
- a selected market lacks a unique consistent outcome;
- chronological event count is not exactly 2,570;
- block construction is not exactly 5 x 514 events;
- an unauthorized threshold/stage appears;
- a stress price exits `[0,1]` (that threshold/stress scenario becomes invalid);
- C1/C2/C3/reserve input is supplied through this evaluator.

## Interpretation boundary

A development PASS would mean:

> One frozen Candidate-E quoted-entry/hold threshold showed positive standard-fee historical settlement economics on H1_OOF/H2/H3 under the predeclared displayed-quote and +1¢ stress tests, with required chronological stability.

It would **not** prove:

- historical fills;
- full-depth availability;
- acceptable latency;
- queue priority;
- partial-fill behavior;
- missed-fill behavior;
- future profitability;
- paper/demo/real execution readiness.

The next evidence after a PASS is a separately frozen C1+C2 historical confirmation, followed—only if that passes—by prospective execution-aware collection/testing.

## Safety

21N-B remains offline and read-only.

It does not authorize:

- network collection during evaluation;
- order placement or cancellation;
- paper broker behavior;
- demo execution;
- real-money execution;
- transfers;
- leverage;
- sizing optimization.

`RISK_POLICY.md` is unchanged.
