# KXBTCD Candidate-C Checkpoint-17 Transport Amendment

<!-- CHECKPOINT17_TRANSPORT_AMENDMENT_20260815 -->

## Purpose

This document records a transport-only repair after the one-time terminal test
had already begun. It does not authorize any model or scoring change.

## Failure record

- Original terminal fingerprint: `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa`
- Failed manifest: `data\manifests\2026\08\15\collect_kxbtcd_candidate_c_locked_test_20260815T224506878886Z_31832daa.json`
- Failed manifest SHA-256: `9cbf18cc44933330c8d27ed000aa2c04015f1fb660aca13979ae6ec4253c5627`
- Persisted labels before interruption: 9
- Frozen market request count: 304
- Failed endpoint: `/historical/markets/KXBTCD-26AUG0202-T55499.99`
- Observed Kalshi market-settlement cutoff: `2026-06-16T00:00:00Z`

Only the number of persisted labels was inspected during diagnosis. Label
values were not used to design this repair.

## Frozen invariants

Candidate C, final-model fingerprint, preprocessing fingerprint, lambda,
optimizer, features, locked-test membership, event weighting, raw-midpoint
benchmark, primary log-loss rule, secondary Brier metric, and tie-fails rule
remain unchanged.

## Transport-only amendment

Amendment fingerprint: `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`

The original implementation files bound by the Stage-A freeze are not edited.
A separate resume-only adapter:

1. validates the original frozen terminal procedure;
2. validates this separate amendment;
3. recovers already opened labels from raw archives across the resume chain;
4. skips all recovered tickers;
5. queries `/markets/{ticker}` for each missing frozen ticker;
6. on HTTP 404 only, retries the same ticker at
   `/historical/markets/{ticker}`;
7. passes the complete recovered+new label set to the unchanged frozen scorer.

Any non-404 transport error fails closed.

## Statistical interpretation

The terminal block remains a one-time, permanently exposed test set. The
predeclared model and primary gate were not changed after exposure, so the final
comparison remains informative as a predeclared terminal evaluation. However,
the execution record must explicitly state that collection was interrupted and
resumed under a transport-only amendment; it is not a pristine single-run
terminal collection.

No paper trading, demo execution, order placement, cancellation, transfers, or
real-money execution are enabled.
