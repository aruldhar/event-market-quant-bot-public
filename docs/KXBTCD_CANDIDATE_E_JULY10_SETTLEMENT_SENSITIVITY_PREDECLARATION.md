# Candidate-E July-10 Settlement Sensitivity Predeclaration

## Status

Checkpoint 21N-Y-E1 is **post-outcome exploratory sensitivity only**.

It does not alter the frozen official July-10 outcome evaluation:

- 60 policy-event scenarios;
- 27 EXACT;
- 33 CENSORED;
- all 15 threshold/latency policy settings officially `INCONCLUSIVE`;
- no policy ranking or selection.

The official settlement manifest and official P&L report are bound by SHA-256.

## Analysis A — coherent liquidation-only hybrid

For all 27 EXACT scenarios, use the frozen official point P&L unchanged.

For the 3 scenarios whose only censorship is liquidation, preserve all known
cash flows and terminalize only the known residual open quantity at binary
settlement. Selection and re-arm are not censored in these three scenarios.

The remaining 30 scenarios with selection/re-arm censorship stay incomplete at
strategy level and retain the frozen universal interval for strategy-level
aggregation.

This sensitivity cannot replace the official `INCONCLUSIVE` result.

## Analysis B — observed-trace terminal value

For each censored scenario:

- retain known entry cash;
- retain any known exit cash;
- settle only the known residual open quantity.

For selection/re-arm-censored scenarios this is a descriptive value for the
observed trace only. It is not complete policy P&L because an unobserved interval
could contain a different or additional action.

## Analysis C — independent entry settlement diagnostic

Each frozen observed filled entry is evaluated independently as if that actual
filled quantity were held from its actual entry to settlement:

`entry net cash + terminal binary cash for the filled quantity`.

This is an entry-quality diagnostic, not a causal hold-all policy. A later
observed trade can depend on an earlier exit/re-arm, so holding trade 1 while
also retaining trade 2 could violate chronology.

## Frozen future settlement universe

E1 derives every unique market ticker appearing in the 93 observed filled
trades from the already-frozen outcome-blind path artifact. The exact ticker
list is frozen before any additional settlement access.

Future collection may request only this ticker set, using the existing
partition-aware, raw-first, finalized-binary settlement transport.

## Interpretation firewall

This work is post-outcome development/mechanics evidence only. It cannot:

- override the official July-10 result;
- rank/select threshold or latency settings;
- retune Candidate E or the execution policy;
- authorize paper, demo, or real-money execution.
