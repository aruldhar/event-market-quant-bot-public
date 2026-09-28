# KXBTC15M H3 Strict Bounded Re-entry Diagnostic

## Question

Can H3 safely capture one additional same-market oscillation after completing
its first protected cash exit, without expanding the validated entry window,
lowering the probability band, overlapping exposure, or compounding profits?

## Frozen first cycle

- 96 development markets; separate 26-market holdout sealed.
- Raw HTTP response-receipt clock and every archived response.
- First qualifying favored midpoint from 90% inclusive to below 98%.
- Entry decision only during 4–5 minutes remaining.
- One-second full-depth entry latency; at most $100 including fees.
- Protected target at 50% of maximum settlement profit.
- Ten-second preclose cash fallback.

## Re-entry rule

At most one second cycle is allowed, and only when all conditions hold:

1. The first position has fully exited through the protected target.
2. The first cash exit occurs before four minutes remaining.
3. After that exit, the original favored side is observed outside the 90–98%
   band.
4. The same side then freshly returns to the band before four minutes remaining.
5. The one-second-delayed second fill also executes before four minutes remain.
6. The second cycle uses the same protected-50% exit and at most $100.

The second budget is fixed at $100; first-cycle profit is not compounded.
Positions cannot overlap. A side change, an already-in-band post-exit state, a
signal whose delayed fill crosses the cutoff, or missing full depth produces no
second entry.

## Policies and primary metric

- `single_cycle_baseline`: accepted H3 first cycle only.
- `one_strict_bounded_reentry`: identical first cycle plus the permitted second
  cycle when available.

Primary: paired incremental realized P&L per all 96 markets, assigning $0 to no
trade/no-reentry increments, with deterministic paired-bootstrap 95% interval.

Secondary: markets with post-exit search time, armed transitions, signals,
second entries, second-cycle P&L, profitable rate, full-loss rate, 5% tail, and
worst result.

## Gates and interpretation

The first cycle must reproduce the accepted 57-entry protected causal-native
strategy market by market. Markets without a second entry must retain exactly
the baseline P&L. No holdout, external feed, authentication, or orders may be
used.

This adaptive test may determine that the strict rule has no practical capacity
because first exits often occur after the entry window. Such a result is useful
and must not be relaxed post hoc by extending the window. Any positive result
is development evidence, not a guarantee or unbiased expected return.
