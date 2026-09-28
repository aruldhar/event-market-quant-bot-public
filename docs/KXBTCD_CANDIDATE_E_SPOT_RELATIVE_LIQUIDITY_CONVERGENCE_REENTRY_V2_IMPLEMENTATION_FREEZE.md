# KXBTCD Candidate-E Spot-Relative Liquidity V2 — Implementation Freeze

## Checkpoint 21N-Y-A

Strategy:

`kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2`

21N-X predeclaration:

`3e44c6ce3b9e420db3cf0dd52c2b64030ae99901c491d9cf0bc15617930ef8ae`

Implementation fingerprint:

`b8f66b2f392df2c8711e7d6e25e64c54921b16f8f7866c243a6375aaec778949`

## Purpose

21N-Y-A implements the frozen V2 architecture **before** real July 10
nonstructural Candidate-E scoring is allowed.

No July 10 V2 path is run in this checkpoint.

## Implemented mechanics

### Dynamic universe

At each causal decision time:

1. obtain the immediately preceding fully completed Coinbase one-minute close;
2. locate the nearest KXBTCD strike, with lower strike then ticker as tie-break;
3. construct ATM plus at most five numeric strike ranks below and five above;
4. clip at ladder boundaries without replacement;
5. evaluate only markets inside that current window.

Liquidity does not define ATM or window membership.

### Event-driven clock

BTC minute boundaries always create a decision timestamp.

Within each Coinbase minute, the ATM window is fixed by the causal BTC state at
that minute boundary. Only verified source-availability transitions or changes
to best YES bid/ask price or quantity for markets in that current window add
entry-decision timestamps.

Deep-book-only changes and book changes outside the current window do not create
entry decisions.

At the next BTC minute boundary the ATM window is recomputed before evaluation.

### Candidate E and execution

Candidate E is unchanged. Synthetic tests may call the frozen probability
function, but **real July 10 nonstructural states are not scored in Y-A**.

The implementation directly reuses the frozen 21N-R primitives for:

- Candidate-E probability;
- fixed-point fees;
- YES/NO normalization;
- IOC entry;
- latency;
- partial/missed fills;
- liquidation depth walk;
- verified replay-segment requirements.

### Re-entry

V1 edge/depth false-state re-arm is retained.

V2 adds the frozen 21N-X rule:

`REFERENCE_LEFT_SPOT_WINDOW`

After Trade 1 has fully exited, if causal BTC state is available and the
reference market is no longer inside current ATM±5, the strategy re-arms
without requiring that out-of-window reference book to be available.

If the reference remains inside the window, source-unavailable or invalid book
state does not count as re-arm.

### Efficient historical materialization

The future Y-B runner still validates the full 623-ticker paid/replay/backfill
source set.

It then computes the deterministic union of tickers that can enter ATM±5 from
the already-bound causal Coinbase minute states and reconstructs only that
subset. This is an implementation optimization; it does not alter the
predeclared universe.

## Safety

Y-A performs:

- no real July 10 nonstructural Candidate-E scoring;
- no July 10 V2 path run;
- no outcome access;
- no fresh 24-event acquisition;
- no network requests;
- no Predexon purchase;
- no order placement;
- no paper/demo/real execution.

## Next

Only after Y-A is tested, committed, pushed, and remotely verified may
**21N-Y-B** run the exact frozen July 10 V2 outcome-blind path.

Settlement outcomes must remain closed in Y-B.
