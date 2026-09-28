# KXBTCD Candidate-E Alpha-Reliability Entry Diagnostic v1 — Implementation

## Status

**IMPLEMENTATION FROZEN — REAL DIAGNOSTIC NOT RUN**

Implementation fingerprint:

`2bc7d625fa7889ee071322a3d3785becc49fd66fcf409e47713de8dc2405bc0d`

Parent predeclaration:

`2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e`

## What the code does

The implementation reconstructs a Candidate-E-valued quoted-entry opportunity
for each H2/H3 event using the frozen first-qualifying-anchor rule.

Candidate E alone supplies the settlement probability used in quoted edge:

- YES: `pE - yes_ask - fee(yes_ask)`
- NO: `(1-pE) - (1-yes_bid) - fee(1-yes_bid)`

Only after the Candidate-E opportunity has been selected does the code attach
that row's `conditional_alpha`.

Thus alpha cannot change side, market, TTC anchor, quoted price, or Candidate-E
edge.

## Quartiles

Among ENTER events pooled across H2+H3:

1. sort by alpha ascending;
2. tie by event ticker;
3. market ticker;
4. YES before NO;
5. split into Q1-Q4 equal-count rank groups, giving any remainder to earlier
   quartiles.

Outcomes are not used to form quartiles.

## Economics

For the later diagnostic run only:

- base P&L = settlement payoff - quoted purchase price - fee;
- +1c stress adds one cent to purchase price and recomputes the fee;
- one whole contract per selected event;
- ABSTAIN events do not enter P&L-per-entry denominators.

The implementation reports pooled/H2/H3 quartiles, upper/lower halves, and
Spearman alpha-vs-base-P&L ranking.

## Safety and interpretation

This implementation does not run the real diagnostic.

The real CLI rejects any closeout receipt that is not Checkpoint 21N-N-B.
Therefore the implementation must be tested, committed, and pushed before real
H2/H3 P&L can be produced.

Even after the later run, the triage label is exploratory only. It cannot pass a
strategy, select an alpha threshold, claim fresh validation, or authorize
execution.

C1/C2, C3, protected reserve, network access, and execution remain prohibited.
