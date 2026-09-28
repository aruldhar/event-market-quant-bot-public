# KXBTCD Candidate-E C3 Evaluator Implementation Freeze

## Checkpoint

**21H-A — Candidate-E C3 Evaluator Implementation Freeze**

This checkpoint freezes the exact evaluator implementation that may later open
the final historical C3 outcomes. It does **not** open any C3 outcome and it
does not fit or tune a model.

## Frozen parent evidence

- Checkpoint-21G-C checkpoint:
  `c5243578e5a5dc08013ee13013f96f71f3290ddb`
- Checkpoint-21G-C receipt:
  `8e0c94ec66bcb6113afcab465b8a60b11c6acfac`
- C3 validation fingerprint:
  `44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0`
- C3 cohort fingerprint:
  `08add4c28831c0d460dff706b0cc425550a4d5d3f486d3ec7f14622586101f6b`
- C3 pre-outcome row fingerprint:
  `898400f7401ef9a96a9c1a0a6d2c99479395ff9fb0a13d93ea7c5fbc3dad51db`
- Champion-R2:
  `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- frozen beta_distance:
  `0.014501283346050064`

## Exact C3 identity

- 500 events
- five chronological 100-event blocks
- 13,549 scored pre-outcome rows
- 2,470 unique market outcome requests
- 533 candidate identities inspected outcome-blind
- queue range `[4222, 4755)`
- 4,676 untouched historical identities remain
- protected floor: 4,500
- buffer above floor: 176

## Evaluator contract

The one-time evaluator must:

1. validate the exact tracked C3 freeze and local frozen artifacts;
2. validate the exact Champion-R2 model;
3. hard-deny all H1/H2/H3/C1/C2 event and market identities;
4. mark the complete C3 cohort permanently exposed before constructing an HTTP
   client;
5. request only the 2,470 frozen C3 market identities from the public
   `/historical/markets/{market_ticker}` endpoint;
6. preserve each response raw-first;
7. accept only finalized `yes`/`no` results;
8. apply Champion-R2 without fitting, tuning, selection, or feature changes;
9. score raw midpoint and Champion-R2 with equal total weight per event;
10. apply the unchanged Checkpoint-21A gate;
11. prohibit a fresh second C3 attempt; permit only a recognized interrupted
    attempt to resume;
12. never materialize or outcome-open the remaining historical reserve;
13. keep all execution paths disabled.

## Gate

C3 passes only if all frozen requirements hold:

- pooled raw-minus-Champion log-loss delta `> 0`;
- pooled raw-minus-Champion Brier delta `>= 0`;
- at least 4 of 5 chronological blocks win on log loss;
- newest block B4 wins;
- median event raw-minus-Champion log-loss delta `> 0`;
- frozen Champion-R2 beta is finite, converged, and positive;
- structural role/TTC coverage is complete;
- policy, lineage, source, timing, and data-quality firewall passes.

A primary tie fails.

## Interpretation boundary

Checkpoint 21H-A validates procedure and contamination controls only. It is not
predictive evidence and not trading-profitability evidence.

After 21H-A is safely closed and pushed, the next and only authorized action is
the one-time C3 historical outcome evaluation.
