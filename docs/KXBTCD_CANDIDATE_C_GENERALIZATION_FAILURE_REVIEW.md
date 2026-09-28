# KXBTCD Candidate-C Generalization Failure Review and Successor Research Design

Status: **Checkpoint 18A design accepted — development-only diagnostic implementation; successor fitting prohibited**

## Purpose

Checkpoint 17 is permanently closed. Candidate C failed its frozen one-time
terminal advancement gate. That aggregate failure is a historical fact only.

The exposed Checkpoint-17 64-event / 1,014-row terminal block is not an input to
Checkpoint 18A. Its labels, predictions, residuals, feature values,
feature distributions, slices, and individual event results may not be used to
diagnose Candidate C or design a successor.

Checkpoint 18A therefore asks a narrower question:

> How strong and stable was the apparent Candidate-C improvement inside the
> already-exposed development evidence, and was the Checkpoint-15 development
> protocol sufficiently conservative for only 231 development events?

No successor candidate is fit in this stage.

## Allowed evidence

Only evidence whose outcomes were exposed before the terminal test:

- the canonical Checkpoint-13 train+validation development predictions;
- the frozen Checkpoint-12 train+validation pre-outcome context joined through
  the existing canonical development loader;
- the canonical Checkpoint-15 rolling-origin artifacts at
  `data/analysis/kxbtcd_candidate_c_development/20260815T220714Z`;
- the frozen Checkpoint-15 week map.

The diagnostic implementation contains no HTTP client and makes zero network
requests.

## Diagnostic A — rolling-origin block stability

For the selected frozen `lambda=0.01`, report B1-B4 separately:

- raw midpoint and Candidate-C event-weighted log loss;
- raw midpoint and Candidate-C event-weighted Brier;
- raw-minus-Candidate-C deltas;
- event and row counts;
- median event delta;
- share of gross positive improvement.

Also report:

- event-level delta distribution;
- 10%-trimmed mean;
- top-1, top-5, and top-10 event concentration;
- week-level deltas;
- leave-one-score-block-out pooled deltas.

Plain-language interpretation: pooled improvement is less trustworthy when a
small number of events, weeks, or blocks supply most of its magnitude.

## Diagnostic B — coefficient and prediction stability

Checkpoint 15 used fold-specific z-scaling. Standardized coefficients therefore
cannot be compared naively.

For each stored fold model, convert

`beta_j * ((x_j - mean_j) / std_j)`

back to the raw feature representation. For a non-intercept feature:

`raw_slope_j = beta_j / std_j`

and the raw-space intercept is adjusted by the corresponding
`beta_j * mean_j / std_j` terms.

The raw market benchmark corresponds to:

- intercept `0`;
- market-logit slope `1`;
- spread slope `0`;
- market-logit x spread slope `0`.

The review also reconstructs predictions from the already-stored fold
coefficients on an outcome-blind fixed grid formed from development feature
quantiles. This is prediction reconstruction, not refitting.

Instability is indicated by large fold-to-fold probability ranges or correction
sign reversals for the same development-supported market state.

## Diagnostic C — sharpening / recalibration behavior

Candidate C contains no independent external BTC-price feature. Its learned
inputs are only:

1. market log-odds;
2. Kalshi spread;
3. market log-odds x spread.

The diagnostic therefore measures:

- fraction of OOF rows moved farther from 0.50 than the raw midpoint;
- mean confidence change;
- mean absolute probability adjustment;
- fraction of adjustments crossing 0.50;
- descriptive market-probability x spread correction cells.

Those cells are diagnostic only. Their boundaries may not be copied directly
into a successor policy without a separate predeclaration.

## Diagnostic D — complexity and conditioning

For each historical fit fold:

- reconcile the stored scaler against the canonical fit rows;
- calculate feature correlations;
- calculate the correlation-matrix eigenvalues and condition number;
- track interaction-feature dependence on its parent variables.

A small parameter count does not eliminate model risk when the features are
strongly dependent or the earliest fit contains only a small number of events.

## Diagnostic E — temporal dependence and protocol risk

The review reports:

- weekly mean event-delta lag-1 autocorrelation;
- a conservative positive-lag-1 AR(1)-style effective-week-count heuristic;
- candidate 6-, 7-, and 8-block contiguous UTC-week layouts constructed using
  event/week identifiers only.

The ESS quantity is explicitly a diagnostic, not a certified effective sample
size.

Checkpoint 15 remains a valid completed development experiment. However, its
evidence had two optimism risks that Checkpoint 18 must address:

1. the Candidate-C feature hypothesis was discovered from the same 231 exposed
   development events later used for rolling-origin scoring;
2. the same pooled OOF score blocks were used to select lambda and then assess
   the selected lambda's advancement rule.

The coefficient fits were chronological and out-of-fold, but the model family
was not untouched with respect to the later score blocks.

## Successor options retained for later comparison

No option is selected or fit in Checkpoint 18A.

### Benchmark 0 — raw midpoint

`p = q_market`

Zero fitted parameters.

### Candidate option 1 — market-anchored intercept/slope recalibration

`logit(p) = logit(q_market) + a + d * logit(q_market)`

The raw market is nested at `a=0, d=0`. Any regularization should shrink the
correction terms toward zero, meaning shrinkage is toward the market rather than
toward a 50% model.

### Candidate option 2 — tightly regularized additive spread correction

`logit(p) = logit(q_market) + a + d * logit(q_market) + c * spread`

Again the raw market is nested when `a=d=c=0`.

The Candidate-C interaction is not automatically carried forward. It remains a
diagnostic reference until the development-only stability review is complete.

## Successor protocol direction — not yet frozen

Checkpoint 18B will use the completed 18A evidence to freeze one successor
specification and its exact protocol before fitting.

The intended stricter protocol is nested chronological evaluation:

- outer chronological blocks estimate candidate generalization;
- tuning occurs only inside earlier inner development history;
- an outer score block cannot select its own hyperparameter;
- event remains the primary scoring unit;
- week-level dependence is explicitly reported;
- advancement must require more than pooled mean improvement alone.

Exact block count and numerical advancement thresholds are intentionally not
selected before the 18A diagnostic is reviewed.

## Failure / instability concepts to formalize in Checkpoint 18B

The later predeclaration must define numerical thresholds for:

- insufficient pooled log-loss improvement;
- Brier degradation;
- weak median block performance;
- too few positive outer blocks;
- severe worst-block degradation;
- excessive coefficient or prediction instability;
- materially concentrated improvement;
- hyperparameter knife-edge behavior.

These thresholds must be frozen before successor fitting.

## Safety and contamination boundary

Checkpoint 18A:

- performs no Candidate-C refit;
- performs no successor fit;
- performs no successor hyperparameter search;
- loads no Checkpoint-17 result artifact;
- loads zero terminal rows, labels, features, predictions, or residuals;
- makes zero network requests;
- places zero orders;
- enables no paper, demo, or real-money execution.

A future untouched test must be genuinely new data collected after the
successor design is frozen. The exposed Checkpoint-17 block can never become an
untouched holdout again.

<!-- CHECKPOINT18A_RESULT_ACCEPTED_20260815 -->
## Checkpoint 18A result — accepted interpretation

The zero-network development-only review completed on run `20260815T231543Z`.

Key facts:
- pooled raw-minus-Candidate-C OOF log-loss delta: `+0.06977433833998076`;
- median event delta: `+0.03752869270657104`;
- 10%-trimmed event mean: `+0.05603263551768059`;
- Candidate C remained positive under every leave-one-score-block-out diagnostic;
- weekly delta lag-1 autocorrelation was `0.2745465399596292`, with a conservative positive-lag ESS heuristic of about `26.18` across 46 scored weeks;
- latest block B4 improvement fell to `+0.012732044125987746`, and 7 of its 11 scored weeks had negative log-loss delta;
- only frozen lambda `0.01` beat raw;
- standalone raw-space spread slope decayed across folds from roughly `0.325/0.412` to `0.190/0.091`;
- raw-space market-logit slope remained around `0.66-0.70`;
- wide-spread grid states permitted large Candidate-C probability corrections without an independent BTC-state feature.

Accepted interpretation: the Candidate-C development advantage was broad, but its spread-conditioned correction was temporally weakening and too regime-sensitive to justify carrying spread or the interaction term into the next successor. This is a hypothesis about the failure mechanism, not proof that spread can never be useful.

The review loaded zero terminal rows/labels/features, made zero network requests, and fit neither Candidate C nor a successor.
