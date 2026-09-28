# KXBTCD Candidate-B Train/Validation Evaluation

Status: **Checkpoint 13 accepted result — Candidate B failed validation; locked test sealed**

Model: `kxbtcd_market_context_logistic.v1`

## Frozen inputs

Checkpoint 13 accepts exactly this Checkpoint-12 pre-outcome materialization:

```text
run_id = collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d
split_fingerprint = 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
dataset_fingerprint = d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a
Candidate-B specification fingerprint = e4d608b42193ac1cf97bf940400a34e16ae60b6019df1fee48e21b625c4a5be3
dataset-design fingerprint = adc0e6a05ec6a61c114a7d49cb0ad5e271321fe0e8c3c80b76fed81b98025286
materialization fingerprint = f9a2459f81b1bb90e1ff55d099e837cb47c78c6586195759d55b5029d676bdb5
```

Expected frozen partition counts:

```text
train:       175 events / 4,645 rows
validation:   56 events /   719 rows
locked_test:  64 events / 1,014 rows
all:         295 events / 6,378 rows
```

The materialization remains `kxbtcd_preoutcome_materialization.v3` with TTC anchors:

```text
55m, 50m, 45m, 40m, 35m, 30m
```

and maximum quote staleness of 60 seconds.

Checkpoint 13 does not rerun or redesign any of these inputs.

## Outcome firewall

Outcome attachment is market-specific because one KXBTCD event contains multiple strike contracts with different final YES/NO results.

Before the first result request, the implementation:

1. validates the exact Checkpoint-12 run manifest and all referenced artifact hashes;
2. verifies the frozen dataset/split/model/materialization fingerprints;
3. verifies exact partition row/event counts and event-level partition separation;
4. constructs a unique allow-list from `train` and `validation` market tickers only;
5. constructs a unique deny-list from every `locked_test` market ticker;
6. requires zero allow/deny overlap; and
7. refuses any result row whose market is not in the allow-list.

Each network request is an exact read-only historical market request:

```text
GET /historical/markets/{market_ticker}
```

No event-wide or series-wide outcome request is used. The returned market must match both the expected `market_ticker` and `event_ticker`, have `status=finalized`, and have result exactly `yes` or `no`.

The raw HTTP response is persisted before the result is transformed. Outcome rows retain the raw source/session/request lineage.

Locked-test outcomes remain unopened throughout Checkpoint 13, even when the validation gate passes.

## Partial-run recovery

A prior Checkpoint-13 outcome exposure prevents a fresh all-market rerun.

The resume path reads successful finalized results from the preserved raw archives of the prior CP13 manifest. Those already exposed market tickers are supplied as existing outcomes and are not requested again. Only still-missing train/validation market tickers may be requested.

This matters because a network or process failure must not silently turn into repeated label collection with ambiguous provenance.

## Event weighting

The frozen pre-outcome dataset assigns:

```text
event_row_weight = 1 / eligible_rows_in_event
```

so row weights sum to one inside each event.

For a partition with `E` events, predictive loss is:

```text
(1 / E) * sum_rows(event_row_weight * row_loss)
```

which is exactly equivalent to:

```text
mean_over_events(mean_row_loss_within_event)
```

An event with many available strike/time observations therefore does not dominate an event with fewer observations.

## Benchmark A

The mandatory benchmark is the raw market midpoint:

```text
q_market = (yes_bid + yes_ask) / 2
```

It is not refit or recalibrated before comparison.

## Candidate B

The frozen features are:

```text
q_clip = clip(q_market, 0.001, 0.999)
market_logit = ln(q_clip / (1 - q_clip))
strike_log_ratio = ln(strike_dollars / 100000)
time_log1p_hours = ln(1 + time_to_close_seconds / 3600)
```

The model is:

```text
z = b0
    + b1 * market_logit
    + b2 * strike_log_ratio
    + b3 * time_log1p_hours

p_yes = 1 / (1 + exp(-z))
```

The four allowed regularization values are:

```text
0.01, 0.1, 1, 10
```

For each lambda, the train-only objective is:

```text
event_weighted_mean_log_loss
+ lambda / 2 * (b1^2 + b2^2 + b3^2)
```

`b0` is unpenalized. There are no class weights.

The implementation uses a deterministic damped Newton solver for this four-coefficient convex objective. This avoids translating the frozen lambda into a package-specific inverse-regularization convention such as `C`.

## Lambda selection

All four lambdas are fit on train only.

For each fitted model, validation is scored without the L2 penalty. The selected lambda is the one with the lowest validation event-weighted log loss. An exact tie selects the larger lambda.

Validation is never used to refit coefficients before lambda selection.

## Validation gate

Candidate B advances only when:

```text
Candidate-B validation event-weighted log loss
<
raw-midpoint validation event-weighted log loss
```

A tie fails.

Checkpoint 13 records the gate result but does not open locked-test outcomes. If the gate passes, the next authorized action is to freeze the selected lambda and perform the already-declared train+validation refit before a single locked-test evaluation. If the gate fails, the locked test stays sealed for Candidate B.

Candidate C is not authorized by this checkpoint.

## Reported metrics

Primary metric:

```text
validation event-weighted log loss
```

Secondary diagnostics:

- event-weighted Brier score;
- raw-minus-Candidate-B delta log loss;
- raw-minus-Candidate-B delta Brier;
- fixed 0.10-wide probability calibration bins;
- exact TTC-anchor slices;
- frozen structural strike-role slices when the selected-market artifact provides them;
- unique row, event, day, and week counts.

Secondary diagnostics cannot override the primary validation gate.

## Fail-closed conditions

The evaluation stops before label collection or fitting when any required invariant cannot be proved, including:

- wrong or missing frozen run manifest;
- failed run-manifest artifact-integrity validation;
- changed dataset, split, Candidate-B, dataset-design, or materialization fingerprint;
- changed frozen row/event counts;
- outcome/downstream fields present in pre-outcome rows;
- duplicate state IDs;
- an event or market crossing partitions;
- event-row weights not summing to one;
- any train/validation allow-list overlap with the locked-test deny-list;
- an unplanned outcome ticker;
- returned ticker/event mismatch;
- a market that is not finalized;
- a finalized result other than `yes` or `no`;
- incomplete train/validation labels at fit time;
- a singular or non-convergent Candidate-B optimization;
- a lambda outside the frozen grid.

## Safety boundary

This checkpoint is read-only research.

It does not add:

- order placement;
- order cancellation;
- transfers;
- demo execution;
- paper execution or a paper broker;
- real-money execution;
- Candidate C;
- regime-conditioned changes to Candidate B.

D-013 remains future research only. Regime tagging/adaptive hypotheses cannot change the frozen Candidate-B model or the frozen Checkpoint-12 dataset in this experiment.

## Canonical run command

After installing the checkpoint replacement files and before opening any labels:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Then run the zero-network preflight before opening labels:

```powershell
.\.venv\Scripts\python.exe .\validate_kxbtcd_candidate_b_preflight.py
```

Only after both the test suite and preflight pass, run the train/validation collector:

```powershell
.\.venv\Scripts\python.exe .\collect_kxbtcd_candidate_b_train_validation.py
```

If the collector fails after any label exposure, do **not** rerun the fresh command. Use the failed/running manifest reported by the command:

```powershell
.\.venv\Scripts\python.exe .\collect_kxbtcd_candidate_b_train_validation.py `
  --resume-from-manifest "<manifest path>"
```

The resume path recovers already exposed successful labels from raw archives and requests only missing train/validation markets.

## Known Checkpoint-12 provenance-text cleanup

The accepted v3 implementation and frozen fingerprint use the six 55m-to-30m anchors. An older descriptive `anchor_rule` string in `collect_kxbtcd_preoutcome_dataset.py`, plus two superseded prose references in the materialization-plan document, still mention the earlier 16h-to-30m draft grid.

Those stale strings did not drive the accepted materialization. They were corrected during the Checkpoint-13 closeout without changing the frozen materialization algorithm, dataset, split, or fingerprints.

<!-- CHECKPOINT13_CANONICAL_RESULT_20260815 -->
## Canonical Checkpoint-13 result

Canonical run:

```text
collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631
```

Pre-label engineering evidence:

```text
final regression = 631 passed, 22 subtests passed in 16.10s
zero-network preflight = PASS
train market requests planned = 822
validation market requests planned = 228
locked-test market requests planned = 0
locked-test deny-list markets = 320
prior CP13 exposure manifests = 0
```

Outcome collection:

```text
train/validation market labels = 1050
new HTTP requests = 1050
recovered prior outcomes = 0
locked-test outcomes opened = 0
authentication used = no
orders placed = 0
```

### Benchmark and selected model

Raw Kalshi midpoint validation metrics:

```text
event-weighted log loss = 0.14231643239449182
event-weighted Brier = 0.04007408198822001
```

Candidate-B lambda table:

| lambda | train log loss | validation log loss | raw - candidate validation log loss | validation Brier | raw - candidate validation Brier | selected |
|---:|---:|---:|---:|---:|---:|:---:|
| 0.01 | 0.097722256260416168 | 0.20069619446600914 | -0.058379762071517322 | 0.04150269119776246 | -0.0014286092095424502 | no |
| 0.1 | 0.14432974690271924 | 0.14556019289436192 | -0.003243760499870102 | 0.040404125365432336 | -0.00033004337721232596 | yes |
| 1 | 0.3026909148854055 | 0.19863291694477292 | -0.056316484550281098 | 0.048076601719423288 | -0.0080025197312032781 | no |
| 10 | 0.57003399865276405 | 0.50457707592618672 | -0.3622606435316949 | 0.15774281591527359 | -0.11766873392705357 | no |

Selected `lambda=0.1` coefficients:

```text
beta0 = 0.094997254017608834
beta1_market_logit = 1.1149509916339024
beta2_strike_log_ratio = -0.060557892307059664
beta3_time_log1p_hours = -0.001891300947166137
iterations = 6
converged = true
train objective = 0.20666907435698761
train event-weighted log loss = 0.14432974690271924
train event-weighted Brier = 0.033560200054487024
```

### Gate

The frozen gate required Candidate B to have strictly lower validation event-weighted log loss than the raw midpoint.

Observed:

```text
Candidate B = 0.14556019289436192
raw midpoint = 0.14231643239449182
raw - Candidate B = -0.003243760499870102
```

Result: **FAIL**.

The validation Brier score also moved in the wrong direction by `-0.00033004337721232596` on the raw-minus-candidate convention.

### Interpretation

The four-lambda table shows a clear negative result rather than a tie. `lambda=0.01` fits train much more aggressively but generalizes poorly to validation; `lambda=1` and `lambda=10` are progressively more regularized and also worse. `lambda=0.1` is the best Candidate-B setting on validation but still loses to the unmodified market midpoint.

The selected coefficients show that the market logit remains the dominant model term. The strike and time coefficients are comparatively small. That diagnostic may motivate later hypotheses, but it cannot be used to rewrite or retune this completed Candidate-B experiment on the exposed validation partition.

### Final Checkpoint-13 decision

- Candidate B does not advance.
- No train+validation final refit is performed.
- Locked-test outcomes opened remain **0**.
- Candidate C remains unauthorized inside Checkpoint 13.
- The old validation partition is now label-exposed for future research.
- The locked-test partition remains label-sealed.
- Any later regime-conditioned or adaptive research must follow D-013 as a separately predeclared candidate process.
- No claim of profitability or executable edge is supported by this result.
