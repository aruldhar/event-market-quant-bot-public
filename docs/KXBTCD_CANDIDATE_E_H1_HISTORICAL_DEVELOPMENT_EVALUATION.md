# KXBTCD Candidate-E H1 Historical Development Evaluation

## Checkpoint 20 scope

Checkpoint 20 is the first Candidate-E checkpoint allowed to open historical outcomes, and only the frozen H1 development tier may be exposed. H2 and H3 remain sealed. Trading execution remains prohibited.

Checkpoint 20 is intentionally split into two stages:

- **20A — H1 evaluation procedure freeze:** outcome-blind validation, identity binding, evaluator implementation, synthetic tests, and deterministic procedure freeze.
- **20B — one-time H1 outcome exposure and evaluation:** permitted only after the 20A procedure freeze is committed, pushed, freshly fetched, and verified clean/synchronized.

## Frozen parents

The H1 procedure must require all of the following unchanged:

- Candidate-E predeclaration fingerprint: `9775be58f01375ca6f2b04212a63578ce5e8cf7084498e6ce9d3ae68685d59a9`
- 19G historical materialization contract fingerprint: `cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145`
- Coinbase-primary source amendment fingerprint: `b08da00a8f66817d9e3b600ccf091c8a4fc1ee92a0bed1c821d23bc321d9faba`
- 19H-C cohort-map fingerprint: `09ebc6553255e76e5cff2d134c1f5bbc239dc753b9080e2c052d418e49c69efa`
- 19H-C row-universe fingerprint: `e12375eeec4d81554f8008ea10e8c8e49be44ff40d8405c974de4ab8f69b2aa5`
- 19H-C exclusion fingerprint: `dd2877579bb800fc1d15ee3c05754947658dfdb552858d67f39b260e32aaf9c4`

The historical Candidate-E path uses Coinbase as the sole required BTC source. Kraken remains diagnostic only and may not block H1 eligibility.

## Frozen H1 universe

H1 contains exactly 1,500 events and 36,314 pre-outcome rows. The 19H-C cohort map already assigns the 1,500 H1 events to seven contiguous chronological blocks:

- B0: 215 events
- B1: 215 events
- B2: 214 events
- B3: 214 events
- B4: 214 events
- B5: 214 events
- B6: 214 events

The five frozen rolling-origin folds are:

1. fit B0+B1, score B2
2. fit B0+B1+B2, score B3
3. fit B0+B1+B2+B3, score B4
4. fit B0+B1+B2+B3+B4, score B5
5. fit B0+B1+B2+B3+B4+B5, score B6

Therefore 1,070 H1 events are scored out of fold. B0 and B1 are fit-only seed blocks.

## Outcome firewall

Before Stage 20B may construct an HTTP client, Stage 20A must freeze and validate:

1. the exact H1 event/market allow-list derived only from the frozen H1 rows;
2. independent H2 and H3 event/market identity fingerprints derived from the same frozen universe;
3. disjointness of H1, H2, and H3 identities;
4. hard denial of every H2/H3 event or market in collection, recovery, and scoring;
5. the exact implementation SHA-256 hashes for the H1 evaluator and collector;
6. the original 19H-C cohort and row-universe fingerprints;
7. the existing seven-block map and five folds;
8. the existing source-policy, lineage, structural coverage, and feature formulas.

Stage 20B has no arbitrary ticker or partition argument. It may only iterate the frozen H1 request plan.

Once Stage 20B begins, the full 1,500-event H1 tier is conservatively marked development-exposed before the first request. A failed/interrupted run may resume the same frozen attempt; a fresh second H1 attempt is prohibited.

## Frozen model menu

Exactly two Candidate-E variants are evaluated:

- `kxbtcd_btc_distance_offset_logistic.v1`
- `kxbtcd_btc_distance_momentum_offset_logistic.v1`

The raw Kalshi midpoint remains the benchmark and enters the model only as the frozen 0.001-clipped logit offset. No regularization, feature standardization, hyperparameter search, recalibration, coefficient cap, alternate momentum horizon, or post-hoc feature/model repair is allowed.

Both variants use the frozen deterministic damped-Newton optimizer with zero free-coefficient initialization and event-equal binary log-loss fitting.

## Metrics and gates

Both candidates are scored on identical OOF rows. Primary and secondary pooled metrics are event-equal log loss and event-equal Brier score.

A candidate passes the frozen raw advancement gate only if all conditions in the Candidate-E predeclaration hold, including:

- pooled raw-minus-candidate log-loss delta > 0;
- pooled raw-minus-candidate Brier delta >= 0;
- log-loss improvement in at least four of five score blocks;
- improvement in the latest B6 block;
- positive median event-level log-loss delta;
- all five fits and all predictions/metrics valid and finite;
- positive `beta_distance` in every fold;
- all score blocks contain all five strike roles and all six TTC targets;
- no source-policy, timing, lineage, evidence-tier, or outcome-firewall violation.

If both candidates pass raw, the momentum model may replace the distance-only model only if it also passes the frozen nested complexity gate against the distance-only model on identical OOF rows.

The possible H1 decisions are therefore exactly:

- `family_FAIL`
- `kxbtcd_btc_distance_offset_logistic.v1`
- `kxbtcd_btc_distance_momentum_offset_logistic.v1`

No H1 result may be repaired or rescored after it is observed.

## Safety state at Stage 20A freeze

Stage 20A itself opens zero Candidate-E outcomes and performs zero Candidate-E fits. H2 and H3 remain sealed. Order placement, cancellation, transfers, paper execution, demo execution, and real-money execution remain absent and prohibited.

<!-- CHECKPOINT20B_CANDIDATE_E_H1_RESULT_20260817 -->
## Checkpoint 20B — Candidate-E H1 historical development result

The one-time frozen H1 evaluation completed from a clean synchronized checkout and validated successfully.

- H1: 1,500 events / 36,314 rows
- OOF scored events: 1,070
- H1 result fingerprint: `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`
- raw Kalshi event-equal log loss: `0.10494755188081126`
- Distance event-equal log loss: `0.03379679620851983`
- raw-minus-Distance log-loss delta: `0.071150755672291427`
- raw Kalshi event-equal Brier: `0.020374750709011895`
- Distance event-equal Brier: `0.0090293992615540601`
- raw-minus-Distance Brier delta: `0.011345351447457835`
- Distance raw advancement gate: PASS
- Distance+Momentum raw advancement gate: PASS
- Distance+Momentum nested complexity gate: FAIL
- nested chronological block wins: 2 / 5
- frozen H1 selection: `kxbtcd_btc_distance_offset_logistic.v1`

The more complex Distance+Momentum model was microscopically better in pooled metrics but won only two of five chronological score blocks, so the frozen complexity gate rejected it and the simpler Distance specification was selected.

H1 is permanently development-exposed. H2 outcomes opened: 0. H3 outcomes opened: 0. No post-hoc H1 repair or feature change is authorized. Execution remains prohibited.
