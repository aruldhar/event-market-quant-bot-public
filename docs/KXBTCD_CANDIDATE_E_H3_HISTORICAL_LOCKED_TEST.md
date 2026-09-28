# Candidate-E H3 Historical Locked Test

**Checkpoint:** 20G
**Status:** pre-H3-outcome final-model/procedure freeze
**Candidate:** `kxbtcd_btc_distance_offset_logistic.v1`
**H2 result fingerprint:** `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`
**Final H1+H2 model fingerprint:** `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
**H3 validation fingerprint:** `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`

## Fixed model entering H3

`logit(p) = logit_clip_0.001(q_market) + beta_distance * d_BTC`

Frozen `beta_distance = 0.013805016135330063`.

The coefficient was fit once on all 2,250 exposed H1+H2 events / 58,668 rows. H3 does not fit it.

## Frozen H3 evidence

- 750 untouched events
- 22,409 frozen pre-outcome rows
- 3750 frozen market labels
- chronological B0-B4, 150 events per block
- raw Kalshi midpoint is the benchmark

## H3 PASS gate

All conditions are required:

1. pooled raw-minus-Distance event-equal log-loss delta > 0;
2. pooled raw-minus-Distance event-equal Brier delta >= 0;
3. Distance wins log loss in at least 4 of 5 H3 blocks;
4. Distance wins newest H3 block B4;
5. median event-level raw-minus-Distance log-loss delta > 0;
6. frozen H1+H2 fit is finite/converged and beta_distance > 0;
7. every H3 block retains all five structural strike roles and all six TTC targets;
8. no source, timing, lineage, evidence, outcome-firewall, or execution violation.

Primary ties fail.

## Sequential rule

H3 FAIL permanently closes Candidate E under this specification. H3 PASS establishes historical predictive-generalization evidence only and permits at most a later separately designed read-only prospective confirmation phase. Neither result establishes profitability or execution suitability.

H3 outcomes opened at this freeze: 0.

<!-- CHECKPOINT20H_CANDIDATE_E_H3_IMPLEMENTATION_20260817 -->
## Checkpoint 20H implementation freeze

The H3 outcome-opening implementation is now frozen under `6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc`. It consumes only the existing 20G H3 request plan, uses raw-first public historical-market retrieval, journals each finalized YES/NO label, and scores the fixed H1+H2 Distance model without calling the Candidate-E fitting routine.

A fresh second H3 attempt is prohibited. If the first attempt is interrupted, only resume from the recognized failed/running H3 manifest. No H3 outcome was accessed while creating this implementation freeze.

<!-- CHECKPOINT20J_CANDIDATE_E_H3_RESULT_20260817 -->
## Checkpoint 20J — Candidate-E H3 locked-test PASS

The one-time frozen H3 historical locked test completed from a clean synchronized checkout and its manifest/result artifacts validate successfully.

- H3: 750 events / 22,409 rows / 3,750 finalized market labels
- H3 result fingerprint: `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`
- H3 validation fingerprint: `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`
- H3 implementation fingerprint: `6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc`
- final H1+H2 model fingerprint: `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
- frozen beta_distance: `0.013805016135330063`
- raw Kalshi event-equal log loss: `0.13793316358637769`
- Distance event-equal log loss: `0.038920564033036092`
- raw-minus-Distance log-loss delta: `0.099012599553341601`
- raw Kalshi event-equal Brier: `0.027664663135376771`
- Distance event-equal Brier: `0.01025442810344244`
- raw-minus-Distance Brier delta: `0.017410235031934333`
- median event raw-minus-Distance log-loss delta: `0.085591053297719571`
- chronological H3 block log-loss wins: 5 / 5
- newest B4: win
- frozen H3 gate: PASS
- Candidate-E historical H1/H2/H3 generalization program: PASS

H3 is permanently outcome-exposed and may not be reused as untouched evidence for a future model influenced by this result. No H3 fitting, candidate selection, feature change, hyperparameter search, post-hoc repair, or execution occurred.

This establishes strong historical predictive-generalization evidence for the frozen Candidate-E Distance specification. It does not establish trading profitability or execution suitability.
