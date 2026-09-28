# KXBTCD Candidate-E Incremental Alpha Entry Score v1 — Predeclaration

## Status

**PREDECLARED — NOT RUN**

Diagnostic ID:

`kxbtcd_candidate_e_incremental_alpha_entry_score.v1`

Fingerprint:

`bb341361f191621564459fef3f68d893181498cb687e131e39183441a3eb27fa`

## Why this is the next test

The frozen alpha-entry diagnostic returned `PROMISING_EXPLORATORY_SIGNAL`, but
alpha and Candidate-E quoted edge rise together. Therefore the important unresolved
question is not whether high alpha trades did better. It is:

> Does alpha improve entry ranking after Candidate-E net edge is already included?

The parent exploratory result remains **not a strategy PASS**.

## Score

For each of the already-selected 512 Candidate-E H2/H3 ENTER opportunities:

`e_i = Candidate-E net quoted edge after the frozen standard fee`

`a_i = log(alpha_i / (1-alpha_i))`

Using outcome-blind pooled H2+H3 ENTER-population scaling:

`z_e,i = (e_i - mean(e))/sd(e)`

`z_a,i = (a_i - mean(a))/sd(a)`

Then:

`S_i(beta) = z_e,i + beta * z_a,i`

`beta=0` is the exact edge-only benchmark.

The alpha logit is used because alpha is a sigmoid output compressed near the
upper end of (0,1); logit(alpha) recovers its latent reliability score before
that compression.

## Frozen beta menu

`0, 0.25, 0.5, 1, 2`

No negative beta. No continuous optimizer. No feature additions.

For each beta, select exactly the top 25% of the 512 opportunities by score:
128 entries.

The 25% coverage is frozen now because the prior diagnostic examined alpha
quartiles. It is explicitly a development choice, not fresh validation. Coverage
must not be searched.

## Development selection metric

Choose beta by the highest pooled H2+H3 **+1 cent stressed realized P&L per
selected entry**.

Exact tie -> smaller beta.

This is exploratory development tuning on already-exposed H outcomes.

## Required incremental-alpha signal

The selected beta must satisfy all:

1. beta > 0;
2. pooled base P&L/entry > beta=0;
3. pooled +1c P&L/entry > beta=0;
4. H2 base P&L/entry > beta=0;
5. H3 base P&L/entry > beta=0;
6. pooled base P&L/entry > 0;
7. pooled +1c P&L/entry > 0.

If all pass: `INCREMENTAL_ALPHA_SIGNAL`.

Otherwise: `NO_INCREMENTAL_ALPHA_SIGNAL`.

This is deliberately stricter than simply finding one beta with positive P&L.
Alpha must beat the much simpler edge-only ranking.

## Evidence boundary

H2/H3 are fully exposed development evidence.

This diagnostic must not access C1/C2, C3, protected reserve, network data, or
execution.

No result here is a strategy PASS or a guarantee of profitability.

If alpha wins, the next checkpoint may design a formal entry strategy and its
next evidence gate. If alpha does not win, remove alpha from the entry architecture.
