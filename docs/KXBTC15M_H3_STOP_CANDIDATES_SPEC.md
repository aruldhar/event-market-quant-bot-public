# KXBTC15M H3 opened-evidence stop-candidate specification

## Status and purpose

This is an adaptive hypothesis-generation diagnostic. The original 96-market
development partition and the permanently opened 26-market partition are all
development evidence. The diagnostic may justify collecting a new sample; it
cannot validate, repair, or reopen the failed H3 holdout evaluation.

The analysis remains public and read-only. It uses no authentication, external
BTC feed, demo order, or real order.

## Frozen baseline

Every candidate must first reproduce the accepted causal-native H3 baseline:

- first favored midpoint from 90% to below 98%;
- 4-to-5 minutes remaining;
- one-second unprotected delayed entry;
- full archived depth, $100 maximum cash outflow, and conservative fees;
- protected 50%-of-maximum-profit target;
- ten-second preclose fallback;
- one position and one cycle.

The original partition must reproduce 96 eligible markets, 57 entries, no full
loss, and approximately $2.32 mean P&L per market. The opened partition must
reproduce its saved scenario CSV market by market, including 26 eligible
markets, 14 entries, total P&L of approximately -$46.55, and one full-capital
loss. Any mismatch stops the command before candidate results are written.

## Candidate surface

The bounded first-stage surface contains no hybrids and no partial exits:

1. Baseline control.
2. Fixed progressive exits at -$2, -$5, -$10, -$15, and -$20 executable P&L.
3. No-target progressive cash exits at 90, 60, and 30 seconds remaining.
4. Five-second persistent progressive exits at -$15 and -$20.
5. Deterioration confirmation: arm at -$10, stop on a later -$20 observation,
   and reset after recovery above -$5.
6. Late-loss ladder: stop at or below -$10 with at most 90 seconds remaining;
   with at most 60 seconds remaining, stop on any negative full-exit mark or
   loss of full-position depth.
7. Exit on the first loss of full-position depth.
8. Depth-buffer exits: after executable P&L reaches -$10, stop if displayed bid
   depth cannot cover 125% or 150% of the held quantity. Loss of 100% coverage
   also signals.

The protected target has priority when a target and risk signal share a native
observation. Each risk signal waits one second, sells all available contracts,
and repeats delayed attempts until flat or settlement. Outcome labels never
participate in a decision.

For persistence, a fully executable mark above the threshold resets the timer.
Loss of full depth after a breach cannot be interpreted as recovery and thus
does not reset the timer.

## Reporting

Every policy is reported for:

- original development 96;
- opened 26;
- combined 122;
- the prior earlier-64 and later-32 diagnostic segments.

Primary decomposition:

`net change = savings on baseline losers - cost imposed on baseline winners`

The report includes stop counts, winner and loser stops, total and mean P&L,
paired differences, full losses, progressive fill completion, residual
settlement, lower-tail results, and the known loser's execution details.

## Standalone evidence screen

A candidate is marked as a strong standalone screen only when all are true on
the combined opened evidence:

- it stops at least one baseline-losing entry;
- it saves at least $25 across baseline losers;
- total P&L improves versus the baseline;
- gross opportunity cost on baseline winners is no more than 50% of loser
  savings;
- it creates zero full-capital losses;
- every signaled position becomes fully liquidated.

This is a collection-justification screen, not a profitability or selection
gate. Parameter-neighborhood behavior and chronological stability must still
be reviewed.

## Hybrid boundary

No hybrid is searched in this stage. If two simple families remain strong
across nearby settings, one combined causal policy may be specified afterward.
The specification must declare signal priority, state transitions, target
accounting, partial-fill handling, and all parameters before it is replayed.

Any final H3 v2 candidate requires a newly collected chronological confirmation
sample that is not used for further tuning.
