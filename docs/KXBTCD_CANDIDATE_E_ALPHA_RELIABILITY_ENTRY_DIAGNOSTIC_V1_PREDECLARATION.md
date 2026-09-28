# KXBTCD Candidate-E Alpha-Reliability Entry Diagnostic v1 — Predeclaration

## Status

**PREDECLARED — NOT RUN**

Diagnostic ID: `kxbtcd_candidate_e_alpha_reliability_entry_diagnostic.v1`

Predeclaration fingerprint:

`2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e`

## Why this exists

Conditional-alpha v2 is permanently a **probability-gate FAIL**. Its formal H2/H3
evaluation selected lambda `0.001`, but its pooled log loss and pooled Brier were
worse than frozen Candidate E. That result is not being repaired or reinterpreted.

A separate question remains economically relevant:

> When Candidate E already shows positive quoted edge, does the already-learned
> conditional-alpha score rank those opportunities by realized trade quality?

This diagnostic tests that question only.

## Separation of responsibilities

Candidate E remains the probability/valuation model.

For a row:

- YES quoted purchase price = `yes_ask`.
- NO quoted purchase price = `1 - yes_bid`.
- Candidate-E YES edge =
  `pE - yes_ask - standard_entry_fee(yes_ask)`.
- Candidate-E NO edge =
  `(1-pE) - (1-yes_bid) - standard_entry_fee(1-yes_bid)`.

`conditional_alpha` is **not** substituted for Candidate E and
`adjusted_yes_probability` is not used for valuation.

Alpha is only attached to the Candidate-E opportunity selected by the frozen
event-selection rule.

## Evidence firewall

Allowed: the canonical selected-lambda rolling-origin predictions for H2 and H3
from formal conditional-alpha v2 evaluation fingerprint
`fa1f6f34ec830ea6c2520a1513f27c3ca1f0d69bf2ddc73e1c90660abfc3efe0`.

H2/H3 are already-exposed development evidence. This diagnostic is exploratory
and cannot create fresh validation evidence.

Prohibited: H1 economic scoring, C1/C2, C3, protected reserve, network access,
execution, refitting, new features, lambda changes, or threshold search.

## Candidate-E event selection

Maximum one whole-contract quoted-entry decision per event.

Use TTC anchors in the frozen order:

`55m, 50m, 45m, 40m, 35m, 30m`.

Take the first anchor containing at least one Candidate-E opportunity with
net edge >= 0. Within that anchor select maximum Candidate-E net edge. Ties:
market ticker ascending, then YES before NO. Otherwise ABSTAIN.

This establishes the Candidate-E trade before alpha is used.

## Alpha diagnostic

Among Candidate-E ENTER events only:

1. sort by conditional alpha ascending;
2. deterministic ties: event ticker, market ticker, YES before NO;
3. split into four equal-count rank groups Q1-Q4 without using outcomes.

Report pooled, H2, and H3:

- entries;
- mean alpha;
- mean Candidate-E quoted net edge;
- base hold-to-settlement P&L per entry;
- +1c stress P&L per entry;
- positive realized-P&L fraction.

Also report pooled Spearman rank correlation between alpha and base realized P&L,
Q4-Q1 contrasts, and upper-half minus lower-half contrasts.

## Predeclared exploratory triage

Label `PROMISING_EXPLORATORY_SIGNAL` only if all are true:

1. pooled Q4 base P&L/entry > pooled Q1;
2. pooled Q4 +1c P&L/entry > pooled Q1;
3. pooled upper-half base P&L/entry > pooled lower-half;
4. pooled upper-half +1c P&L/entry > pooled lower-half;
5. H2 Q4 base P&L/entry > H2 Q1;
6. H3 Q4 base P&L/entry > H3 Q1;
7. pooled Spearman(alpha, base realized P&L) > 0.

Otherwise label `NO_CLEAR_SIGNAL`.

This is **research triage, not a strategy gate**. Even a promising result cannot
authorize choosing the best alpha threshold on these same H outcomes.

## What happens next

If promising, separately predeclare an actual Candidate-E entry-filter strategy
and validation/evidence plan before opening additional evidence.

If no clear signal, close conditional-alpha-as-entry-filter on H and move to a
different simple entry-filter hypothesis.

No result from this diagnostic can guarantee profitability.
