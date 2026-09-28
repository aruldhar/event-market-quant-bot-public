# Checkpoint 19F — Candidate-E Historical Evidence Protocol Amendment

**Status:** pre-outcome design freeze. No new Candidate-E outcomes have been accessed and Candidate E remains unfitted.

**Amendment fingerprint:** `b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb`

## Why this amendment exists

Checkpoint 19A/19D-B/19E originally required newly prospective E1/E2/E3 evidence. Before any Candidate-E fit or post-19E outcome access, the project changed the evidence strategy to a historical-first research pipeline. This amendment makes that change explicit rather than silently violating the earlier protocol.

The scientific objective is unchanged: determine whether the frozen Candidate-E family adds predictive information beyond the raw KXBTCD midpoint. This amendment changes **when and from which untouched evidence the model is trained/validated/tested**, not the frozen Candidate-E formulas.

## Frozen untouched universe

The canonical modern-regime KXBTCD census contains 9,738 events from 2025-03-22 17:00 UTC through 2026-08-14 20:00 UTC. Exactly 307 event tickers had outcomes previously exposed. Their union is excluded from all Candidate-E H1/H2/H3 evidence.

- untouched events: **9,431**
- census SHA-256: `07e48cc2bf996c395329e66a61263854a43fcacb8b98962bfcb906daf4e26481`
- exposed-event-set SHA-256: `d7e115bf5566630fdff0fb75a740701f1080c0d385a707617fcfc65dde159817`
- untouched chronological-universe SHA-256: `d0b61b7688e54ff4cdeb4cc4652a8ecd5a0a5031b14ad7666b1a8b5b0b5fda90`

"Untouched historical" means the event occurred in the past but its outcome has not been used by the current design/fit/selection/test process. Historical occurrence alone does not make evidence contaminated.

## Historical state realization

For H1/H2/H3, Candidate E keeps the same mathematical features but realizes `S_t` from the frozen historical sources:

- Kalshi `q`: latest valid real two-sided one-minute KXBTCD quote at/before the TTC target, at most 60 seconds old.
- Coinbase historical primary: exact last-fully-completed UTC one-minute candle close.
- Kraken historical verifier: latest trade in that exact minute whose `publication_ts` is no later than the decision time.
- exact five-minute lookback only; no interpolation, nearest-future sampling, carry-forward, or source substitution.
- both historical sources required and historical cross-source disagreement must be <= 5 bp.

Historical candle/trade primitives are **not claimed identical to the later live BBO primitives**. Checkpoints 19C/19D-A measured that transport difference outcome-blind. A historical PASS therefore earns a later prospective live confirmation; it does not establish live performance or profitability.

## Sequential evidence pipeline

### H1 — Historical TRAIN / candidate selection

Take the first **1,500 eligible untouched events** chronologically. Open H1 outcomes only after the 19F universe and outcome-blind materialization are frozen and validated.

Within H1, preserve the exact 19E seven-block/five-fold rolling-origin layout. Evaluate the two frozen Candidate-E variants once using the original raw-advancement and nested-complexity gates. If neither passes, Candidate E fails and H2/H3 outcomes remain unopened.

### H2 — Untouched historical VALIDATION

Take the next **750 eligible untouched events** strictly after H1. H2 outcomes remain sealed until H1 selects exactly one frozen Candidate-E specification.

Score the selected H1 specification once on H2. Split H2 into five contiguous chronological blocks for stability reporting. PASS requires pooled log-loss improvement over raw, non-worse pooled Brier, at least 4/5 block log-loss wins, a latest-block win, positive median event-level improvement, a finite/converged H1 fit with positive distance coefficient, required structural coverage, and no policy/firewall violation.

If H2 fails, Candidate E stops and H3 remains untouched.

### Final fit before H3

After H2 PASS, the selected specification is fixed. Refit its parameters once on H1+H2. No feature, candidate, optimizer, threshold, or hyperparameter change is allowed. Freeze the final parameter fingerprint before H3 outcomes are opened.

### H3 — LOCKED historical TEST

Take the next **750 eligible untouched events** strictly after H2. H3 outcomes remain sealed until the final H1+H2 model is frozen. Evaluate exactly once using the same numerical and structural gate shape as H2.

An H3 failure permanently exposes H3 and closes Candidate E. An H3 PASS permits only a later prospective live confirmation under the 19D-B live source policy. It does not authorize paper/demo/real-money execution.

## Reserve protection

The first 3,000 raw untouched events leave a nominal 6,431-event reserve (68.19%). Frozen eligibility failures may extend H1/H2/H3 forward without outcomes, but thresholds may not be relaxed. Candidate E must fail closed before its materialization would reduce the remaining outcome-unopened reserve below **5,000 events**.

If H1 fails before H2 outcomes open, H2 and H3 remain untouched for future protocols. If H2 fails before H3 outcomes open, H3 remains untouched.

## Nominal raw queue boundaries

These are outcome-blind reference boundaries only; final eligible boundaries may move later because ineligible events are skipped under frozen rules.

- H1 raw first 1,500: 2025-03-22 17:00 -> 2025-06-28 02:00 UTC
- H2 raw next 750: 2025-06-28 04:00 -> 2025-08-15 20:00 UTC
- H3 raw next 750: 2025-08-15 21:00 -> 2025-10-03 15:00 UTC
- nominal reserve: 2025-10-03 16:00 -> 2026-08-14 20:00 UTC

## What remains unchanged

Candidate IDs, formulas, 10,000 log-bp scaling, raw midpoint benchmark, fixed market-logit offset, optimizer, no-regularization/no-standardization/no-hyperparameter-search rules, TTC anchors, structural strike roles, causal no-lookahead rules, raw-first lineage, read-only authorization, and execution prohibition all remain in force.

<!-- CHECKPOINT19F_FINAL_CLOSEOUT_20260817 -->
## Final local validation evidence

Checkpoint 19F passed canonical local validation on 2026-08-17:

- amendment fingerprint: `b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb`
- census events: 9,738
- prior outcome-exposed events: 307
- outcome-untouched events: 9,431
- untouched chronological universe SHA-256: `d0b61b7688e54ff4cdeb4cc4652a8ecd5a0a5031b14ad7666b1a8b5b0b5fda90`
- focused regression: 6 passed
- full regression: 759 passed + 22 subtests
- diff check: PASS
- Candidate-E fits: zero
- new Candidate-E outcomes accessed: zero
- execution: prohibited

A Windows path-separator defect in the first local-universe validator implementation was repaired with portable repository-path normalization and a dedicated regression test. This implementation repair did not alter the frozen amendment fingerprint, source-file hashes, exposure set, untouched universe, allocation, model specification, or evidence firewall.
