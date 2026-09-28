# Candidate-E H2 Historical Validation

**Checkpoint:** 20C
**Status:** pre-H2-outcome procedure freeze
**Selected candidate:** `kxbtcd_btc_distance_offset_logistic.v1`
**H1 result fingerprint:** `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`
**Final H1 model fingerprint:** `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
**H2 validation fingerprint:** `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`

## Fixed model entering H2

The H1-selected Distance model is now fitted once on all 1,500 exposed H1 events:

`logit(p) = logit_clip_0.001(q_market) + beta_distance * d_BTC`

Frozen `beta_distance = 0.012310034918384302`.

H2 does not fit this coefficient. H2 only scores it.

## Frozen H2 evidence

- 750 untouched H2 events
- 22,354 frozen pre-outcome rows
- 3750 unique frozen market labels
- chronological B0-B4, 150 events per block
- raw Kalshi midpoint is the benchmark
- H3 is hard denied and remains outcome-sealed

## H2 PASS gate

All conditions are required:

1. pooled raw-minus-Distance event-equal log-loss delta > 0;
2. pooled raw-minus-Distance event-equal Brier delta >= 0;
3. Distance wins log loss in at least 4 of 5 H2 blocks;
4. Distance wins the newest H2 block B4;
5. median event-level raw-minus-Distance log-loss delta > 0;
6. the frozen H1 fit is finite/converged and beta_distance > 0;
7. every H2 block retains all five structural strike roles and all six TTC targets;
8. no source, timing, lineage, evidence, outcome-firewall, or execution violation.

Primary ties fail.

## Sequential rule

A H2 FAIL stops Candidate E and preserves H3. A H2 PASS authorizes only a later final fit of the same Distance specification on H1+H2, followed by a separate H3 freeze. No H2 result establishes profitability or execution suitability.

<!-- CHECKPOINT20D_CANDIDATE_E_H2_IMPLEMENTATION_20260817 -->
## Checkpoint 20D implementation freeze

The outcome-opening implementation is now frozen under `0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e`. It consumes only the existing 20C H2 request plan, uses raw-first public historical market retrieval, journals each finalized YES/NO label, and scores the fixed H1 Distance model without calling the Candidate-E fitting routine.

A fresh second H2 attempt is prohibited. If the first attempt is interrupted, only resume from the recognized failed/running H2 manifest. H3 remains hard denied. No H2 outcome was accessed while creating this implementation freeze.

<!-- CHECKPOINT20F_CANDIDATE_E_H2_RESULT_20260817 -->
## Checkpoint 20F — Candidate-E H2 historical validation PASS

The one-time frozen H2 validation completed from a clean synchronized checkout and its manifest/result artifacts validate successfully.

- H2: 750 events / 22,354 rows / 3,750 finalized market labels
- H2 result fingerprint: `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`
- H2 validation fingerprint: `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`
- H2 implementation fingerprint: `0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e`
- final H1 model fingerprint: `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
- frozen beta_distance: `0.012310034918384302`
- raw Kalshi event-equal log loss: `0.11774919111369225`
- Distance event-equal log loss: `0.035893546124196762`
- raw-minus-Distance log-loss delta: `0.081855644989495491`
- raw Kalshi event-equal Brier: `0.022327771656461513`
- Distance event-equal Brier: `0.0099357895512881093`
- raw-minus-Distance Brier delta: `0.012391982105173404`
- median event raw-minus-Distance log-loss delta: `0.07528266021513054`
- chronological H2 block log-loss wins: 5 / 5
- newest B4: win
- frozen H2 gate: PASS

H2 is permanently outcome-exposed and may not be reused as untouched validation evidence for a future candidate influenced by this result. No H2 parameter fitting, candidate selection, feature change, hyperparameter search, post-hoc repair, or execution occurred. H3 outcomes remain sealed.

This is predictive-scoring evidence only. It does not establish trading profitability or execution suitability.
