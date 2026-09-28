# KXBTCD Candidate-E C2 Evaluator Implementation Freeze

## Checkpoint

21F-A — Candidate-E C2 evaluator implementation freeze.

## Purpose

Freeze the only code path that may later open C2 outcomes, before any C2 label
is requested.

This checkpoint itself opens **zero** C2 outcomes and makes **zero** network
requests.

## Frozen parent state

- Checkpoint-21A lifecycle fingerprint:
  `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
- Checkpoint-21E-C closeout receipt commit:
  `faf013b928bedd94d8e75bf09f3cbf29ad938f97`
- Champion-R1 fingerprint:
  `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- Champion-R1 `beta_distance`:
  `0.014529004270980883`
- C2 validation fingerprint:
  `b984017e17da9de2859d43b78f1218d7333eda45eb1ebb0ed3a6a884eb3746f1`
- C2 cohort fingerprint:
  `446854d2511a942fff560ffe78bbd96863b06d9046de85ff7a8605c868654258`
- C2 pre-outcome row fingerprint:
  `525477c08178f1bd97f58fee0e22f6e5352494cb38210c433a0df7a2af57c9b3`

## Frozen C2 identity

- 500 eligible events
- five chronological 100-event blocks
- 14,007 scored pre-outcome rows
- 2,441 unique outcome-market requests
- 516 candidate identities inspected
- strict queue range `[3706,4222)`
- 5,209 never-materialized historical events remain
- protected floor: 4,500
- remaining buffer: 709

## Evaluator contract

The future one-time evaluator must:

1. apply exactly Champion-R1;
2. use the raw Kalshi midpoint as benchmark;
3. compute event-equal log loss and Brier score;
4. apply the existing Checkpoint-21A confirmation gate;
5. perform no fit, tuning, selection, feature change, or hyperparameter search;
6. request outcomes only for the exact 2,441-market C2 allow-list;
7. accept only finalized YES/NO results;
8. preserve raw responses before transformation;
9. hard-deny all H1/H2/H3/C1 event and market identities;
10. prohibit C3 materialization/outcome access and all execution.

## Exposure rule

Before the future HTTP client is constructed, the runner writes an attempt
receipt declaring the entire C2 cohort permanently exposed.

A fresh second C2 attempt is prohibited. If the one-time run is interrupted,
only the same recognized manifested attempt may be resumed, reusing validated
journaled outcomes.

## Gate

C2 passes only if all frozen conditions hold:

- pooled raw-minus-champion event-equal log-loss delta > 0;
- pooled raw-minus-champion Brier delta >= 0;
- at least 4/5 chronological blocks are strict log-loss wins;
- newest B4 is a strict log-loss win;
- median event raw-minus-champion log-loss delta > 0;
- frozen Champion-R1 is converged with finite positive `beta_distance`;
- all five structural roles and all six TTC targets remain represented;
- policy, lineage, source, timing, and evidence firewall checks pass.

Primary ties fail.

## Safety at 21F-A

- C2 outcomes opened: 0
- model fits: 0
- network requests: 0
- C3 materialized/opened: 0
- execution/orders: disabled / 0

Only after this implementation is safely closed and pushed may the one-time
C2 outcome evaluation be run.
