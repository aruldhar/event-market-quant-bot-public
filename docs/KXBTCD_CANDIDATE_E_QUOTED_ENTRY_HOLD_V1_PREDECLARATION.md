# KXBTCD Candidate-E Quoted-Entry Hold Strategy v1 Predeclaration

## Checkpoint

**Checkpoint 21N-A — Candidate-E Quoted-Entry Hold Strategy Design and Outcome-Independent Opportunity Audit**

## Status

Design frozen before Strategy-v1 realized P&L is calculated.

Strategy ID:

`kxbtcd_candidate_e_quoted_entry_hold_v1`

Strategy predeclaration fingerprint:

`5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6`

Frozen probability engine:

- Candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- Candidate-E Champion-Final fingerprint:
  `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`

Candidate E is not refit, recalibrated, or modified by this strategy.

## Why this strategy exists

Checkpoint 21M permanently rejected
`kxbtcd_candidate_e_entry_residual_logistic.v1` as an incremental settlement-probability model.
The failure does not imply that Candidate E lacks economic value. It means that the tested residual
feature family did not reliably improve Candidate E's probability estimate.

The next simpler question is therefore:

> Given frozen Candidate-E probabilities and the contemporaneous quoted purchase price, is the
> estimated settlement-value advantage large and frequent enough to justify a later execution-aware
> strategy study?

That is a different question from fitting another probability model.

## Relationship to the old Checkpoint-21K-A strategy replay

Checkpoint 21K-A previously froze
`kxbtcd_candidate_e_strategy_replay_v1`, fingerprint
`afc1b397c850e8b2a2dfd32d6656e05f4622c59f1596f5b91295e96debb0d046`.

That design used 10-contract sizing, next-minute fill proxies, and an early cash-out rule. No
Strategy-v1 P&L was opened under that design.

21N-A therefore marks that old strategy design:

`superseded_before_economic_scoring`

The old config/code/fingerprint remain immutable audit history. They are not edited or reused under
the new strategy identity.

## Strategy question

For each KXBTCD event, starting at T-55 and moving toward T-30:

1. Does any Candidate-E state have enough **standard-fee quoted net edge** to meet a frozen threshold?
2. If yes, which single state/side has the largest net edge at the **first qualifying anchor**?
3. If an entry is selected, what would a one-contract hold-to-settlement policy later imply under
   authorized outcome evaluation?
4. If nothing qualifies by T-30, abstain.

Checkpoint 21N-A answers only the outcome-independent opportunity part. It does **not** calculate
realized P&L.

## Frozen quoted economics

At a valid frozen two-sided quote:

```text
P_YES = yes_ask
P_NO  = 1 - yes_bid
```

Candidate-E fair settlement probabilities are:

```text
fair_YES = pE
fair_NO  = 1 - pE
```

For one whole contract, the standard historical KXBTCD entry fee is:

```text
fee(P) = ceil_cent(0.07 * P * (1-P))
```

The quoted net edge per contract is:

```text
net_edge = side_fair_probability - quoted_purchase_price - fee
```

There is no settlement fee in this contract.

These are **standard-fee quoted-entry diagnostics**. They are not exact historical account P&L and
do not assert that a contract actually would have filled at the displayed quote.

## Frozen strategy mechanics

Decision anchors, in order:

`T-55, T-50, T-45, T-40, T-35, T-30`

Eligible structural roles:

`q10, q30, q50, q70, q90`

Eligible sides:

`YES, NO`

Quantity:

`1 whole contract`

Threshold menu, after the standard fee:

`0¢, 1¢, 2¢, 3¢, 5¢`

Qualification is:

```text
net_edge_per_contract >= threshold
```

The 0¢ threshold is a diagnostic nonnegative-edge policy.

At each anchor:

- evaluate all eligible Candidate-E strike/side states;
- if none qualify, continue to the next anchor;
- if one or more qualify, select the largest net edge;
- exact numerical ties are broken by market ticker ascending, then YES before NO;
- stop looking for later entries after the first qualifying anchor.

Per event:

- maximum one entry;
- if no candidate qualifies by T-30, `ABSTAIN`.

After a later authorized entry:

- hold to settlement;
- no early exit;
- no re-entry;
- no adding;
- no averaging;
- no switching sides;
- no stop loss;
- no profit target;
- no Kelly sizing;
- no bankroll optimization.

This keeps the first economic question aligned with the settlement-probability target Candidate E
was actually validated to predict.

## Evidence firewall

### Development

Only these stages may be used by the 21N-A opportunity audit:

| Stage | Events | Candidate-E rows |
|---|---:|---:|
| H1_OOF | 1,070 | 31,656 |
| H2 | 750 | 22,354 |
| H3 | 750 | 22,409 |
| **Total** | **2,570** | **76,419** |

The opportunity audit may inspect frozen Candidate-E probabilities and contemporaneous quote fields.
It may not calculate realized settlement P&L.

### Historical confirmation

C1+C2 contain:

- 1,000 events
- 28,894 Candidate-E rows

These outcomes are already exposed elsewhere in the project, so they are not globally fresh evidence.
However, Strategy-v1 P&L has not been opened.

C1+C2 are **not authorized for Strategy-v1 economic scoring yet**. Before using them, the complete
development-P&L evaluator, threshold-selection procedure, and historical-confirmation gate must be
separately frozen.

### C3

- 500 events
- 13,549 rows
- remains sealed for Strategy-v1 economics.

Model-2 failure does not justify opening C3.

### Protected historical reserve

- 4,676 events
- remains sealed.

It may not be used for threshold selection, strategy tuning, or convenience.

## 21N-A opportunity audit

The audit is deliberately outcome-independent.

It produces:

1. `candidate_side_states.csv`
   - one row for each development Candidate-E state and side;
   - probability, quote, one-contract standard fee, and quoted net edge only.

2. `threshold_event_selections.csv`
   - one row per development event per frozen threshold;
   - the first qualifying-anchor selection or `ABSTAIN`.

3. `opportunity_audit_summary.json`
   - entry/abstain counts and rates;
   - side mix;
   - TTC mix;
   - structural-role mix;
   - stage mix;
   - selected net-edge summaries;
   - source hashes and deterministic audit fingerprint.

The audit must report all five threshold policies. It does not select a winning threshold.

The audit may not emit or calculate:

- settlement outcomes;
- realized P&L;
- win rate;
- return on capital;
- drawdown;
- stressed realized P&L;
- C1/C2 Strategy-v1 economics;
- C3 economics;
- protected-reserve economics.

## Later development P&L stage — not yet authorized

If the opportunity audit establishes enough opportunity frequency to make economic evaluation
meaningful, a later 21N slice may freeze a realized-P&L evaluator on H1_OOF/H2/H3.

Before that evaluator runs, it must predeclare:

- the threshold-selection rule;
- chronological stability requirements;
- primary and secondary economic metrics;
- the +0¢/+1¢/+2¢/+3¢ adverse purchase-price stress calculations;
- the exact development acceptance gate;
- the one-time C1+C2 historical-confirmation gate.

No outcome-driven threshold selection is permitted before that freeze.

## Execution limitation

The reusable historical archive contains enough exact entry-state quote information for this
quoted-entry screen, but it does not reconstruct historical full-depth order books or queue position.

Therefore a later positive historical result would mean only:

> Candidate E showed promising standard-fee quoted settlement-value economics under frozen
> one-contract entry assumptions.

It would **not** prove:

- the historical contract would have filled;
- adequate depth existed;
- latency would preserve the quote;
- partial/missed fills were acceptable;
- paper/demo/real execution is ready.

A prospective execution-aware test remains necessary before any paper-strategy eligibility claim.

## Safety

Checkpoint 21N-A remains read-only.

It does not authorize:

- order creation or cancellation;
- demo execution;
- paper execution or a live paper broker;
- real-money execution;
- portfolio transfers;
- leverage;
- martingale or loss-chasing sizing.

C3 and the protected reserve remain sealed.
