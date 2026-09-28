# KXBTCD Candidate-E Final Historical Fit

## Checkpoint 21I

C1, C2, and C3 have all passed their frozen historical confirmation gates.
Those outcomes are now permanently exposed. The next step is therefore not
another validation experiment: it is a deterministic final parameter fit.

### 21I-A — implementation freeze

Freeze the exact offline procedure before running the final fit.

The frozen procedure must:

- use the unchanged candidate
  `kxbtcd_btc_distance_offset_logistic.v1`;
- use exactly H1 + H2 + H3 + C1 + C2 + C3;
- use exactly 4,500 events and 123,520 rows;
- use event-equal fitting, as in the frozen Candidate-E fit contract;
- use the same deterministic damped-Newton optimizer;
- fit exactly one free parameter, `beta_distance`;
- not fit momentum;
- perform no feature selection, candidate selection, or hyperparameter search;
- make no fresh-validation claim;
- use no rows or outcomes from the remaining 4,676-event historical reserve;
- perform no network requests or execution.

### 21I-B — Champion-Final fit

After 21I-A is safely closed and pushed, run the frozen final fit once.

The resulting tracked model artifact is:

`configs/kxbtcd_candidate_e_champion_final.json`

This artifact is a final historical parameter estimate for downstream
forecasting and strategy research. It does not create new out-of-sample
evidence. C3 remains the last fresh historical confirmation result.

## Interpretation

The purpose of the final fit is simple: once validation is complete, use all
accepted exposed information to estimate the one allowed coefficient as
precisely as possible.

This does not establish trading profitability. Strategy and execution research
must separately account for bid/ask, fees, depth, latency, fills, exits,
sizing, and uncertainty.

<!-- CHECKPOINT21I_B_CHAMPION_FINAL_20260818 -->
## Final fit result

Checkpoint 21I-B completed the frozen Champion-Final fit.

- Champion-Final fingerprint: `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- closeout fingerprint: `1dd79bc396f1dee8afed150930bf5a78ee0581275193545dcde1d579d5b9c43a`
- beta_distance: `0.014939489324405949`
- fit objective: `0.050195791036485929`
- iterations: 10
- converged: true
- fit scope: 4,500 exposed events / 123,520 rows
- remaining historical reserve used: 0
- network requests: 0
- execution/orders: disabled / 0

This artifact is the accepted final historical parameter estimate.
It does not supersede C3 as the final fresh historical confirmation.
