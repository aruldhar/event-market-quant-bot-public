# Candidate-E Reliability-Shrinkage Entry Strategy v2 — Predeclaration

## Checkpoint

**Checkpoint 21N-F — Strategy-v2 Design and Outcome-Independent Opportunity Audit**

## Why this checkpoint exists

Strategy-v1 failed because Candidate E's selected-side reliability deteriorated in
H3/B4 while quoted purchase prices and fees were broadly stable. 21N-E therefore
preselected a simple deterministic reliability adjustment before returning to a
learned entry/meta-model.

The user's skepticism that simple shrinkage may change little is treated as a
testable hypothesis, not an assumption. **No Strategy-v2 P&L is opened in 21N-F.**

## Frozen Strategy-v2 rule

Candidate E is unchanged.

At a contemporaneous two-sided Kalshi quote:

`q_yes = (yes_bid + yes_ask) / 2`

For YES:
- `q_side = q_yes`
- `pE_side = pE`

For NO:
- `q_side = 1 - q_yes`
- `pE_side = 1 - pE`

Reliability adjustment:

`p_adj_side = q_side + alpha * (pE_side - q_side)`

Thus `alpha` is the fraction of Candidate E's disagreement with the Kalshi
midpoint that the decision rule is willing to trust.

Candidate alphas:
- `0.25`
- `0.50`
- `0.75`

Diagnostic reference only:
- `1.00`

`alpha=1.00` is Strategy-v1's unshrunk Candidate-E probability and is **not**
eligible to become the Strategy-v2 winner.

Quoted economics remain:

- YES purchase = `yes_ask`
- NO purchase = `1 - yes_bid`
- fee = `ceil_cent(0.07 * P * (1-P))`
- adjusted net edge = `p_adj_side - purchase_price - fee`

Qualification is exactly:

`adjusted_net_edge >= 0`

There is no second edge-threshold grid.

## Everything else remains frozen

- anchors: T-55, T-50, T-45, T-40, T-35, T-30;
- roles: q10/q30/q50/q70/q90;
- sides: YES/NO;
- one contract;
- maximum one entry per event;
- first qualifying anchor;
- within that anchor choose largest adjusted edge;
- exact tie: market ticker ascending, then YES before NO;
- otherwise abstain;
- no early exit, re-entry, averaging, side switching, sizing optimization, or
  post-hoc TTC/role/side/price filters.

## Why shrink toward the midpoint instead of subtracting a flat haircut

A flat edge haircut is effectively another edge threshold. Strategy-v1 already
tested a frozen threshold menu and the family failed.

Shrinkage instead targets the observed problem directly: it reduces how much of
Candidate E's **incremental disagreement with the contemporaneous market** is
trusted, while keeping quote cost and fees explicit.

This does not claim the market midpoint is true. It is a conservative anchor.

## Outcome-independent opportunity audit

Before any Strategy-v2 realized P&L may be calculated, run the same frozen
H1_OOF/H2/H3 causal states through all four alpha values.

The audit reports:

- entry/abstention counts and rates;
- counts by stage, side, TTC, and role;
- retained entry-event fraction versus alpha=1;
- removed and newly added events versus alpha=1;
- unchanged versus changed chosen state among retained events.

No settlement outcome or realized P&L is used.

## Exact Strategy-v1 reproduction guard

Before any shrinkage result is accepted, the audit must:

1. rebuild the same 21N-A side states with the existing frozen Strategy-v1 code;
2. reconstruct the complete Strategy-v1 0/1/2/3/5c selection CSV;
3. reproduce SHA-256
   `3c43d7c489dac9d761f442f594af24e1a52d478fe2e3bfdfc9e92eb84e636121`;
4. prove alpha=1 reproduces Strategy-v1's 0c event actions and chosen
   market/side/anchor exactly;
5. reproduce 820 alpha=1 entries.

A failure aborts the audit.

## Opportunity coverage screen

A candidate alpha may be considered for a later economics predeclaration only if
the outcome-independent audit shows at least:

- 100 total entries;
- 20 entries in each of H1_OOF, H2, and H3.

This is only a minimum sample/opportunity coverage screen. It says nothing about
profitability.

## Materiality screen — test the skepticism before P&L

For each candidate alpha define:

`changed decisions = removed alpha=1 entry events + changed chosen states among retained events`

To justify spending additional outcome-aware research budget, at least one
sample-eligible candidate alpha must change **at least 10% of the 820 alpha=1
entry decisions**.

If no candidate alpha passes this screen, the simple-shrinkage branch stops
without another P&L evaluation.

If at least one passes, 21N-F still selects no alpha. A separate later checkpoint
must predeclare development economics before any Strategy-v2 P&L is inspected.

## Evidence boundaries

H1_OOF/H2/H3 strategy economics are already exposed from Strategy-v1, but 21N-F
does not use those outcomes.

C1+C2 Strategy-v1 and Strategy-v2 economics remain unopened.
C3 remains sealed.
The protected 4,676-event reserve remains sealed.
No network access, paper broker, demo execution, real execution, or orders are
authorized.

## Frozen identity

Strategy:
`kxbtcd_candidate_e_reliability_shrinkage_entry_v2`

Predeclaration fingerprint:
`b3fd3a3c71c5750604ef4e6eddd23043a75952d2c06a48cbb39ae6ef1066bd50`
