# KXBTCD Candidate-C Rolling-Origin Development Evaluation

Status: **Checkpoint 15 completed — Candidate C passes the frozen development gate; locked test remains sealed**

## Purpose and frozen identity

Checkpoint 15 evaluated only the Candidate-C specification frozen in Checkpoint 14:

```text
model = kxbtcd_market_spread_interaction_logistic.v1
contract = kxbtcd_candidate_c_predeclaration.v2
fingerprint = d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322
features = market_logit, spread, market_logit_x_spread
```

Candidate B remains rejected under its original Checkpoint-13 validation gate. Its later pooled development improvement is diagnostic only and does not reverse D-014.

Frozen data lineage:

```text
CP12 pre-outcome run = collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d
CP13 exposed-development run = collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631
dataset fingerprint = d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a
split fingerprint = 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
Checkpoint-15 canonical result directory = data/analysis/kxbtcd_candidate_c_development/20260815T220714Z
```

The 64-event locked test remained outcome-sealed throughout Checkpoint 15.

## Outcome-blind week-map freeze

Before any Candidate-C fit, the exact UTC-week mapping was derived only from the frozen CP12 pre-outcome train+old-validation rows. No outcomes were used.

```text
development weeks = 58
B0/B1/B2/B3/B4 week counts = 12/12/12/11/11
week-map fingerprint = 6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4
derivation outcomes used = no
locked-test outcomes opened = 0
```

Tracked map:

`configs/kxbtcd_candidate_c_week_blocks.json`

Development composition after applying that frozen map:

| Block | Events | Rows |
|---|---:|---:|
| B0 | 47 | 922 |
| B1 | 48 | 1436 |
| B2 | 48 | 1426 |
| B3 | 44 | 1104 |
| B4 | 44 | 476 |

The evaluator independently re-derived and validated the map before loading the exposed CP13 outcomes.

## Frozen model and evaluation protocol

Candidate C used exactly the predeclared continuous features:

1. `market_logit`;
2. `spread`;
3. `market_logit_x_spread`.

Each rolling-origin fold computed population-variance z-scaling from fit-fold rows only. The deterministic damped-Newton optimizer, event weighting, L2 grid `0.01, 0.1, 1, 10`, metrics, and tie-breaking rule were unchanged.

Only these folds were scored:

- B0 -> B1;
- B0+B1 -> B2;
- B0+B1+B2 -> B3;
- B0+B1+B2+B3 -> B4.

Exactly 16 Candidate-C fits were performed: four lambdas in each of four folds.

## Lambda selection

All lambdas were evaluated on the same 184 OOF events / 4,442 OOF rows.

| Lambda | Candidate OOF log loss | Raw-minus-candidate log loss | Candidate OOF Brier | Raw-minus-candidate Brier | Selected |
|---:|---:|---:|---:|---:|:---:|
| 0.01 | 0.076775557277925191 | 0.069774338339980771 | 0.019029926328616251 | 0.016063793956341752 | yes |
| 0.1 | 0.16990493205584381 | -0.023355036437937848 | 0.032024385218828867 | 0.0030693350661291363 | no |
| 1 | 0.46448575643664897 | -0.31793586081874303 | 0.13871728591686566 | -0.10362356563190767 | no |
| 10 | 0.65920459562432876 | -0.51265470000642277 | 0.23308396741037829 | -0.19799024712542029 | no |

`lambda=0.01` is the unique selected value. The exact-tie rule was not needed. The other three frozen lambdas all had worse pooled OOF log loss than the raw midpoint. No interpolation, smaller-lambda search, or post-result retuning is authorized.

## Selected Candidate-C development result

Pooled score-block evidence on B1-B4:

```text
OOF events = 184
OOF rows = 4442
raw midpoint log loss = 0.14654989561790596
Candidate-C log loss = 0.076775557277925191
raw - Candidate C log-loss delta = 0.069774338339980771

raw midpoint Brier = 0.035093720284958003
Candidate-C Brier = 0.019029926328616251
raw - Candidate C Brier delta = 0.016063793956341752

Candidate-C better/worse/tie events = 119/65/0
score-block log-loss wins = 4/4
```

Per-fold selected-lambda evidence:

| Score block | Fit blocks | Score events | Score rows | Raw log loss | Candidate C log loss | Raw-minus-C | Raw Brier | Candidate C Brier |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| B1 | B0 | 48 | 1436 | 0.093945026725310535 | 0.031705630723558795 | 0.06223939600175174 | 0.015144609802613576 | 0.0048525839930431891 |
| B2 | B0+B1 | 48 | 1426 | 0.17827477694329749 | 0.071670652506793109 | 0.10660412443650438 | 0.041660623204022987 | 0.016576489508244221 |
| B3 | B0+B1+B2 | 44 | 1104 | 0.16310990216151713 | 0.068251280980228368 | 0.094858621181288766 | 0.040421972712592326 | 0.0154484523879176 |
| B4 | B0+B1+B2+B3 | 44 | 476 | 0.1527680573294263 | 0.14003601320343856 | 0.012732044125987746 | 0.044364239744537619 | 0.040754068439436825 |

The event sign count is a diagnostic, not an acceptance metric. Proper scoring can improve materially even when a model does not improve every individual event because log loss depends on the magnitude and calibration of probability errors.

## Frozen development gate

The predeclared gate required all three conditions:

1. pooled OOF Candidate-C log loss strictly below raw midpoint;
2. pooled OOF Candidate-C Brier no worse than raw midpoint; and
3. log-loss wins in at least 3 of 4 score blocks.

Observed:

```text
pooled OOF log-loss condition = PASS
pooled OOF Brier condition = PASS
score-block condition = PASS (4/4)
development advancement gate = PASS
```

Candidate C therefore becomes **eligible for a later freeze/final-fit checkpoint**. This is not terminal out-of-sample evidence and does not establish profitability or executable edge.

## Canonical Windows validation

```text
focused Checkpoint-15 tests = 9 passed in 0.14s
full repository regression = 647 passed, 22 subtests passed in 16.15s
source-registry validation = PASS
```

Source-registry evidence remained:

```text
Sources: 18
Quality policies: 1
Validated sources: 12
Unresolved sources: 0
Unresolved settlement sources: 1
```

## Safety and stopping rule

Canonical Checkpoint-15 result:

```text
Candidate-C development fits performed = 16
full-development final fit performed = no
full-development scaler frozen = no
locked-test feature density inspected for design = no
locked-test outcomes opened = 0
locked-test evaluation performed = no
network requests = 0
execution enabled = no
orders placed = 0
```

No paper broker, demo execution, order placement, cancellation, transfers, leveraged position management, or real-money execution was authorized or performed.

## Next checkpoint boundary

Checkpoint 16 may do only the next predeclared step:

1. freeze selected `lambda=0.01` without any new search;
2. compute and freeze full-development feature-scaling parameters from all 231 exposed development events;
3. perform exactly one final Candidate-C fit on all 231 development events under the frozen optimizer/objective;
4. serialize and fingerprint the final-fit provenance, scaler, and coefficients; and
5. keep all 64 locked-test outcomes sealed.

Checkpoint 16 must **not** evaluate the locked test. A separate Checkpoint 17 is required to authorize the one-time terminal locked-test evaluation after the final development fit is frozen.
