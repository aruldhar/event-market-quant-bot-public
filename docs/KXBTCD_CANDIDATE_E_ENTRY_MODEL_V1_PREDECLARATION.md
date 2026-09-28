# KXBTCD Candidate-E Entry Model v1 Predeclaration

## Status

Checkpoint 21L is in progress.

Frozen so far:
- target and architecture: Decision D-021L-01
- feature contract and causal eligibility: Decision D-021L-02

Still unresolved and therefore not yet authorized for fitting:
- whole-event chronological evidence split
- exact model family and regularization/tuning contract
- evaluation metrics and advancement gates
- deterministic economic-selection evaluation

No Model-2 fit has been performed.
Strategy-v1 P&L remains unopened.
The protected 4,676-event historical reserve remains denied.

## D-021L-01 ? Target and architecture

Model 2 estimates settlement probability conditionally beyond frozen Candidate E:

    logit(p2) = logit(pE) + g(X_entry)

`pE` is the frozen Candidate-E probability and is used as a fixed offset with coefficient 1.

The primary statistical target remains the binary KXBTCD settlement outcome.

Model 2 does not directly learn historical trade P&L. After inference, side-specific economics are computed deterministically from the predicted probability and executable costs.

Model 2 does not learn exit, hold, add, averaging, or other position-management behavior. Those remain Model-3 questions.

## D-021L-02 ? Frozen v1 feature contract

### Baseline offset

`candidate_probability` from frozen Candidate E is the fixed logit offset.

The learned residual does not receive `q_market` or `d_BTC` directly. Those variables already define the frozen Candidate-E baseline and allowing them into the residual would permit Model 2 to refit Candidate E under another name.

### Learned continuous features

1. `r_5m`
   - frozen Candidate-E Coinbase-primary five-minute BTC return in basis points.

2. `spread_t`
   - contemporaneous YES ask minus YES bid at the Candidate-E decision timestamp.

3. `mid_move_1m`
   - `((yes_bid_close + yes_ask_close) - (yes_bid_open + yes_ask_open)) / 2`
   - computed from the exact one-minute quote candle ending at the decision timestamp.

4. `spread_change_1m`
   - `(yes_ask_close - yes_bid_close) - (yes_ask_open - yes_bid_open)`.

5. `bid_range_1m`
   - `yes_bid_high - yes_bid_low`.

6. `ask_range_1m`
   - `yes_ask_high - yes_ask_low`.

7. `log1p_volume_1m`
   - `log(1 + volume_fp)` from the exact decision candle.

8. `log1p_open_interest`
   - `log(1 + open_interest_fp)` from the exact decision candle.

9. `log1p_trade_count_5m`
   - `log(1 + trailing_5m_public_trade_count)`.

10. `log1p_contracts_5m`
    - `log(1 + trailing_5m_public_contracts_traded)`.

11. `taker_imbalance_5m`
    - `(YES_taker_contracts - NO_taker_contracts) / (YES_taker_contracts + NO_taker_contracts)`
    - defined as `0` when the denominator is zero.

### Learned categorical context

- `ttc_target_minutes`: one of 55, 50, 45, 40, 35, 30.
- `structural_role`: one of the frozen q10/q30/q50/q70/q90 strike roles.

The exact numerical encoding of these categorical variables will be frozen with the Model-2 model-family specification before fitting.

### Explicit v1 exclusions

The learned residual must not use:

- `q_market` directly
- `d_BTC` directly
- raw `yes_bid` or `yes_ask` levels as separate predictors
- `coinbase_current_price`
- `coinbase_lookback_price`
- `strike_dollars`
- Kalshi trade-price OHLC / previous-trade-price fields
- raw candle-missingness indicators
- calendar month, year, date, or archive-regime proxies
- event ticker or market ticker identity
- quote-staleness as a predictive shortcut
- fee values as probability predictors
- future quotes, future BTC observations, outcomes as features, P&L, or execution results
- forward-filled, interpolated, or otherwise manufactured Kalshi states
- block-trade features in v1
- historical depth, queue, or imbalance features that are not actually present in the archive

Actual executable YES/NO bid and ask remain available after inference for deterministic economics; excluding raw levels from `g(X_entry)` does not remove them from economic evaluation.

### Causal timestamp rule

All quote-candle features come from the exact one-minute candle whose `end_period_ts` equals the frozen Candidate-E decision timestamp. No later candle or later trade may contribute.

Trailing public trades use the strict causal window:

    decision_time - 300 seconds < trade_time <= decision_time

A no-trade window is a legitimate observed zero, not missing data.

### Eligibility rule

A Model-2 row requires:
- a valid selected Candidate-E OOF/OOS state,
- the corresponding canonical BTC/contract state,
- the exact contemporaneous one-minute Kalshi quote candle.

No required state may be imputed.

Public-trade activity is not an eligibility requirement because zero trades is a valid economic state.

## D-021L-03 ? Whole-event chronological evidence roles

The Candidate-E downstream universe is assigned to Model-2 evidence roles by complete chronological stages.

### Development

Stages:
- H1_OOF
- H2
- H3

Counts:
- 2,570 whole events
- 76,419 prediction rows

Chronological range:
- first event close: 2025-04-28T19:00:00Z
- last event close: 2025-10-12T22:00:00Z

Development evidence may be used for Model-2 fitting and for development-only diagnostics permitted by the later frozen model-family contract.

The 430 H1 fit-only events / 4,658 non-OOF rows remain excluded from Model-2 evidence.

### Validation

Stages:
- C1
- C2

Counts:
- 1,000 whole events
- 28,894 prediction rows

Chronological range:
- first event close: 2025-10-16T14:00:00Z
- last event close: 2025-12-21T20:00:00Z

Validation evidence may be used only according to the later frozen model-selection and tuning procedure.

No individual rows from an event may be split across development and validation.

### Model-2 locked test

Stage:
- C3

Counts:
- 500 whole events
- 13,549 prediction rows

Chronological range:
- first event close: 2025-12-21T21:00:00Z
- last event close: 2026-01-22T17:00:00Z

C3 is locked against Model-2 development.

Before its one-time Model-2 evaluation, C3 must not influence:
- feature additions, removals, or transformations
- preprocessing choices
- scaling rules
- categorical encodings chosen from outcomes
- model-family selection
- interaction selection
- regularization choice
- hyperparameter choice
- probability thresholds
- economic-selection thresholds
- advancement gates
- post-hoc repair

C3 may be opened only after the complete Model-2 training, tuning, scoring, and advancement procedure has been frozen.

### Chronology and event-separation audit

Outcome-blind audit result: PASS.

Observed stage order:
1. H1_OOF
2. H2
3. H3
4. C1
5. C2
6. C3

All adjacent stage boundaries are strictly chronological.

Archive identity checks:
- 4,070 unique events
- events assigned to multiple stages: 0
- events with inconsistent close times: 0

No event crosses an evidence-role boundary.

### Evidence interpretation

These 4,070 events are not globally fresh historical evidence.

They were previously used in Candidate-E forecasting research and therefore constitute downstream strategy/model-development evidence.

The term `locked test` here means locked specifically against Model-2 development after this predeclaration.

The protected 4,676-event historical reserve remains untouched and is not opened by this decision.

### Safety

This evidence-role decision:
- performs no Model-2 fit
- calculates no Strategy-v1 P&L
- accesses no protected reserve
- authorizes no execution

## D-021L-04 ? Frozen Model-2 model family, preprocessing, and tuning

### Candidate identity

Candidate ID:

`kxbtcd_candidate_e_entry_residual_logistic.v1`

Model 2 is a single regularized logistic residual model:

    logit(p2_i) = logit(pE_i) + beta_0 + beta^T x_i

where:

- `pE_i` is the frozen Candidate-E probability
- the Candidate-E offset coefficient is fixed at exactly 1
- `x_i` contains only the features frozen in D-021L-02
- no direct `q_market` or `d_BTC` term is learned

The Candidate-E-only benchmark corresponds to every learned residual coefficient being exactly zero.

### Candidate-E offset

The offset is:

    logit(pE) = log(pE) - log1p(-pE)

using the exact frozen Candidate-E `candidate_probability`.

No new probability clipping is permitted.

Every offset probability must be finite and satisfy:

    0 < pE < 1

Otherwise the fit fails closed.

This preserves Candidate E exactly rather than changing its extreme probabilities through a second clipping rule.

### Continuous predictors

The 11 continuous predictors frozen in D-021L-02 are:

1. `r_5m`
2. `spread_t`
3. `mid_move_1m`
4. `spread_change_1m`
5. `bid_range_1m`
6. `ask_range_1m`
7. `log1p_volume_1m`
8. `log1p_open_interest`
9. `log1p_trade_count_5m`
10. `log1p_contracts_5m`
11. `taker_imbalance_5m`

No continuous feature screening or post-hoc removal is permitted after outcomes are opened.

### Continuous-feature scaling

Each continuous predictor is z-scored using only the events in the current fit partition.

For fit partition containing `E` events, a row `i` belonging to event `e` receives weight:

    w_i = 1 / (E * n_e)

where `n_e` is the number of eligible Model-2 rows for that event.

These weights sum to 1.

For feature `x`:

    mu_x = sum_i w_i * x_i

    sigma_x^2 = sum_i w_i * (x_i - mu_x)^2

and the transformed feature is:

    z_i = (x_i - mu_x) / sigma_x

The population weighted variance is used.

The same fit-partition `mu_x` and `sigma_x` must be applied unchanged to the corresponding score partition.

Score-partition statistics must never influence scaling.

A non-finite mean/variance or standard deviation <= 1e-12 fails closed.

No winsorization, clipping, rank transform, imputation, or nonlinear transformation beyond the already frozen feature formulas is permitted.

### Categorical encoding

`ttc_target_minutes` is encoded using fixed reference coding.

Reference:
- T-55 minutes

Learned indicators:
- T-50
- T-45
- T-40
- T-35
- T-30

`structural_role` is encoded using fixed reference coding.

Reference:
- q50

Learned indicators:
- q10
- q30
- q70
- q90

The references are outcome-blind design choices and cannot change after fitting.

Unexpected or missing categories fail closed.

Categorical indicators are not z-scored.

### Learned parameter count

The residual has exactly 21 learned coefficients:

- 1 residual intercept
- 11 standardized continuous-feature coefficients
- 5 TTC indicator coefficients
- 4 structural-role indicator coefficients

Candidate E itself has no learned Model-2 coefficient because its logit is a fixed offset.

### Interactions and nonlinear model families

Model-2 v1 includes no learned interaction terms.

The following are not candidates in v1:
- decision trees
- random forests
- gradient boosting
- neural networks
- splines
- generalized additive models
- feature-selection searches
- interaction searches
- post-hoc subgroup-specific models

A nonlinear challenger requires a later separately predeclared research phase.

### Training objective

Within each fit partition, minimize:

    L(beta)
      = sum_i w_i * binary_log_loss(y_i, p2_i)
        + lambda/2 * sum_j beta_j^2

where:
- event-equal row weights `w_i` are defined above
- the sum in the penalty covers all 21 learned residual coefficients
- the residual intercept is penalized
- Candidate E's fixed offset is never penalized or refit

Penalizing the residual intercept is intentional.

As regularization strengthens, every learned correction is pulled toward zero and the model is pulled toward frozen Candidate E rather than toward a separately recalibrated intercept.

Class weights: none.

Random sampling or shuffling: none.

### Frozen regularization grid

The exact L2 grid is:

- 0.001
- 0.01
- 0.1
- 1
- 10

No additional lambda values may be added after outcomes are inspected.

Lambda zero is not a candidate.

Candidate E alone remains the mandatory unmodified benchmark.

### Development rolling-origin tuning

Only the D-021L-03 development stages may select lambda.

Fold 1:
- fit: H1_OOF
- score: H2

Fold 2:
- fit: H1_OOF + H2
- score: H3

No H3 row may influence Fold-2 fitting or scaling.

No C1, C2, or C3 outcome may influence lambda selection.

For every lambda, score the pooled H2 + H3 out-of-fold predictions using event-equal binary log loss.

Each scored event receives equal total weight across the pooled 1,500 score events.

Selected lambda:

    lambda with minimum pooled H2+H3 event-equal log loss

Exact numerical tie:

    choose the larger lambda

No secondary metric may override the primary lambda-selection rule.

### Full-development fit after lambda selection

After the lambda is selected by the frozen rolling-origin procedure, one development model may be fit using:

- H1_OOF
- H2
- H3

Total:
- 2,570 events
- 76,419 rows

The scaler for that model must be recomputed using only those 2,570 development events and the frozen event-equal scaling formula.

That frozen development fit may later be evaluated on C1+C2 under the separately frozen validation gate.

C1+C2 may not be included in this development fit.

### Optimizer

Use deterministic damped Newton optimization.

Initial learned residual coefficients:

    beta = 0

Therefore the initial prediction is exactly frozen Candidate E.

Each lambda starts independently from beta=0; lambda warm-starting is prohibited.

Frozen optimizer rules:
- maximum iterations: 100
- gradient L2 tolerance: 1e-8
- Armijo constant: 1e-4
- initial step scale: 1
- rejected step scale multiplier: 0.5
- minimum step scale: 2^-40
- non-convergence: fail closed
- non-finite objective/gradient/Hessian: fail closed

Because lambda is strictly positive and every learned coefficient is penalized, the regularized Hessian is expected to be positive definite.

The Newton system must be solved with a deterministic dense Cholesky factorization implemented without introducing a new numerical/ML dependency.

Any non-finite or non-positive Cholesky diagonal fails closed.

Prediction probabilities and binary log loss must use numerically stable sigmoid/log-loss calculations.

### Reproducibility

No random seed is needed because the full procedure is deterministic.

Given identical:
- frozen input rows
- feature formulas
- evidence roles
- lambda
- scaling rules
- optimizer contract

the implementation must reproduce identical serialized coefficients and predictions to the project's declared floating-point tolerance.

### Model-2 v1 scientific burden

The question is not whether a flexible model can fit the 4,070-event archive.

The question is whether this small, frozen residual provides reliable chronological improvement beyond Candidate E.

If it does not satisfy the later frozen validation and locked-test gates, Model 2 v1 fails and Candidate E remains the probability benchmark.

No post-hoc repair of this v1 specification is permitted on the same validation or locked-test evidence.

## D-021L-05 ? Statistical evaluation and advancement gates

### Benchmark

The mandatory benchmark for every Model-2 evaluation is the exact frozen Candidate-E probability for the same state.

Model 2 must demonstrate incremental statistical value beyond Candidate E.

Raw Kalshi midpoint may be reported diagnostically but is not the Model-2 advancement benchmark.

### Primary metric

Primary metric:

`event_equal_binary_log_loss`

For each event:
1. calculate mean binary log loss across all eligible Model-2 rows in that event;
2. average those event means equally across the scored event set.

Therefore every event receives equal total weight regardless of its number of rows.

For outcome `y` and probability `p`:

    log_loss(y,p) = -y*log(p) - (1-y)*log(1-p)

Numerically stable evaluation is required.

### Secondary metric

Secondary metric:

`event_equal_Brier_score`

For each event:
1. calculate mean squared probability error across eligible rows;
2. average event means equally.

For outcome `y` and probability `p`:

    Brier(y,p) = (p-y)^2

Secondary metrics cannot override failure of the primary metric.

### Per-event improvement diagnostic

For each event:

    delta_event
      = CandidateE_event_log_loss
        - Model2_event_log_loss

Positive delta means Model 2 improved on Candidate E for that event.

The median of these event-level deltas is used as a required breadth-of-improvement condition.

### Validation evidence

Validation consists only of:
- C1
- C2

Counts:
- 1,000 events
- 28,894 rows

The frozen selected lambda and the frozen H1_OOF+H2+H3 development fit are evaluated on these rows.

C1/C2 may not be used to:
- change features
- change preprocessing
- change categorical encoding
- change model family
- change lambda
- add interactions
- alter the optimizer
- set a new statistical gate after seeing results

### Validation chronological blocks

The 1,000 validation events are sorted by:

1. event close timestamp ascending
2. event ticker ascending as deterministic tie-break

They are divided into exactly five contiguous blocks:

- V1: events 1-200
- V2: events 201-400
- V3: events 401-600
- V4: events 601-800
- V5: events 801-1000

The block map must be derived and fingerprinted before validation outcomes are scored by Model 2.

Block assignment uses no outcome or probability-performance information.

V5 is the newest validation block.

### Validation advancement gate

Model-2 v1 advances past validation only if **all** conditions pass:

1. pooled 1,000-event Model-2 event-equal log loss is strictly less than Candidate-E event-equal log loss;

2. pooled Model-2 event-equal Brier score is less than or equal to Candidate-E event-equal Brier score;

3. Model 2 has strictly lower event-equal log loss than Candidate E in at least 4 of the 5 chronological validation blocks;

4. Model 2 has strictly lower event-equal log loss than Candidate E in the newest validation block V5;

5. median per-event Candidate-E-minus-Model-2 log-loss delta is strictly greater than zero.

All conditions are mandatory.

Any tie on a condition requiring strict improvement is a failure.

No secondary statistic, subgroup result, economic result, or narrative judgment may override a failed statistical condition.

### Validation failure

If the validation gate fails:

- Model-2 v1 is rejected;
- no repair, feature change, retuning, recalibration, threshold adjustment, or alternative lambda may be attempted on the same C1/C2 evidence under the v1 identity;
- C3 remains sealed against Model-2 evaluation;
- Candidate E remains the probability benchmark.

Any successor Model-2 specification requires a new candidate identity and a separately predeclared research phase.

### Final-fit rule after validation PASS

Only if every validation condition passes may one final Model-2 v1 fit be created.

The selected lambda remains exactly fixed.

No retuning occurs.

Final-fit evidence:

- H1_OOF
- H2
- H3
- C1
- C2

Counts:
- 3,570 whole events
- 105,313 rows

The final-fit continuous-feature scaler is recomputed from those 3,570 events using the frozen event-equal scaling formula.

The categorical encoding, feature set, selected lambda, penalty, optimizer, and all other model rules remain unchanged.

C3 is not used in scaling or fitting.

The final-fit coefficients and preprocessing state must be serialized and fingerprinted before C3 Model-2 outcomes are scored.

### Model-2 locked test

The Model-2 locked test consists only of C3:

- 500 whole events
- 13,549 rows

C3 has prior Candidate-E research exposure and therefore is not globally fresh evidence.

It is, however, locked against the Model-2 v1 design, tuning, validation decisions, and final fit.

### C3 chronological blocks

The 500 C3 events are sorted by:

1. event close timestamp ascending
2. event ticker ascending as deterministic tie-break

They are divided into exactly five contiguous blocks:

- T1: events 1-100
- T2: events 101-200
- T3: events 201-300
- T4: events 301-400
- T5: events 401-500

The block map must be derived and fingerprinted before Model-2 C3 scoring.

T5 is the newest locked-test block.

### One-time C3 advancement gate

Model-2 v1 passes its statistical locked test only if **all** conditions pass:

1. pooled 500-event Model-2 event-equal log loss is strictly less than Candidate-E event-equal log loss;

2. pooled Model-2 event-equal Brier score is less than or equal to Candidate-E event-equal Brier score;

3. Model 2 has strictly lower event-equal log loss than Candidate E in at least 4 of the 5 chronological C3 blocks;

4. Model 2 has strictly lower event-equal log loss than Candidate E in newest block T5;

5. median per-event Candidate-E-minus-Model-2 log-loss delta is strictly greater than zero.

All conditions are mandatory.

Any primary tie is a failure.

C3 is opened once for this frozen Model-2 v1 evaluation.

After C3 is opened, no post-hoc Model-2 v1 repair may be rescored on C3.

### Interpretation of PASS

A C3 statistical PASS means only:

`Model-2 v1 demonstrated a reproducible historical probability improvement over Candidate E under its frozen statistical protocol.`

It does **not** establish:
- profitable trading
- executable edge
- realistic fills
- adequate liquidity
- fee-adjusted profitability
- demo readiness
- production readiness

Economic selection and execution validity remain separate required research gates.

### Interpretation of FAIL

A C3 statistical FAIL permanently rejects Model-2 v1 as a validated incremental probability model on this evidence.

Candidate E remains the probability benchmark.

The failure may be studied diagnostically, but the same C3 evidence cannot be reused as a fresh locked test for a repaired version of Model-2 v1.

### Protected reserve

The protected 4,676-event historical reserve remains excluded from:
- Model-2 development
- Model-2 validation
- Model-2 C3 testing
- threshold selection
- economic tuning

D-021L-05 does not authorize opening that reserve.

## D-021L-06 ? Strategy-neutral economic-value contract

### Purpose

Model 2 does not implement an entry strategy.

Its economic role is to translate its frozen probability estimate into strategy-neutral measures of market mispricing.

The output answers:

`What is the estimated settlement value of buying YES or NO at the currently observed quote, before any entry-policy decision?`

It does not answer:

`Should a trade be placed?`

That later decision belongs to a separately researched entry-policy layer.

### Fee provenance

The frozen Candidate-E execution archive contains:

- 20,236 KXBTCD markets
- all 20,236 with `price_level_structure = linear_cent`
- all 20,236 binary
- 4,070 events
- zero event fee-type overrides
- zero event fee-multiplier overrides
- zero historical event fee-change rows
- KXBTCD series fee type = `quadratic`
- KXBTCD series fee multiplier = 1
- zero historical KXBTCD series fee-change rows

The official general historical Kalshi fee schedule applicable to the evidence period defines immediately matched trading fees as:

    F(C,P) = ceil_cent(0.07 * C * P * (1-P))

where:

- `C` is the hypothetical whole-contract quantity
- `P` is contract purchase price in dollars
- `ceil_cent` rounds the total fee upward to the next cent

Simple binary YES/NO settlement has no settlement fee.

This contract represents the standard exchange fee schedule.

It does not claim reconstruction of account-specific rebates, promotional credits, fee-consideration programs, or other participant-specific incentives.

Therefore future values derived from this formula must be labeled:

`standard-fee economic diagnostics`

and not:

`exact historical account P&L`.

### Quoted-entry price references

At a frozen decision timestamp with a valid exact two-sided quote:

    P_YES = yes_ask

    P_NO = 1 - yes_bid

These are quoted immediate-purchase price references.

They are not assertions that any particular quantity historically would have filled at that price.

Missing, crossed, invalid, or unavailable required quote state fails closed for economic translation.

No quote interpolation or imputation is permitted.

### Gross settlement-value edge

For Model-2 probability `p2`:

    gross_edge_YES
      = p2 - P_YES

    gross_edge_NO
      = (1 - p2) - P_NO

These are per-contract settlement-value differences before fees.

Positive gross edge means the model estimates expected settlement value above the displayed purchase price.

Positive gross edge is not an automatic entry instruction.

### Standard-fee net expected value as a function of quantity

Because cent-rounded fees depend on quantity, D-021L-06 does not choose a contract quantity.

Instead, fee-adjusted EV is defined as a function of hypothetical quantity `C`.

For any permitted future whole-contract quantity `C > 0`:

    fee_YES(C)
      = ceil_cent(
            0.07 * C * P_YES * (1-P_YES)
        )

    fee_NO(C)
      = ceil_cent(
            0.07 * C * P_NO * (1-P_NO)
        )

Total standard-fee expected value:

    net_EV_YES(C)
      = C * (p2 - P_YES)
        - fee_YES(C)

    net_EV_NO(C)
      = C * ((1-p2) - P_NO)
        - fee_NO(C)

Per-contract standard-fee expected value:

    net_EV_per_contract_YES(C)
      = net_EV_YES(C) / C

    net_EV_per_contract_NO(C)
      = net_EV_NO(C) / C

Quantity remains an input to the economic function, not an output or policy choice of Model 2.

### Candidate-E benchmark economics

Candidate E must be translated through exactly the same price and fee formulas.

For frozen Candidate-E probability `pE`:

    CandidateE_gross_edge_YES
      = pE - P_YES

    CandidateE_gross_edge_NO
      = (1-pE) - P_NO

and, for hypothetical quantity `C`:

    CandidateE_net_EV_YES(C)
      = C * (pE-P_YES)
        - fee_YES(C)

    CandidateE_net_EV_NO(C)
      = C * ((1-pE)-P_NO)
        - fee_NO(C)

No economic advantage may be created by applying different costs or fees to Model 2 and Candidate E.

### Realized state-level settlement value

For research after outcome access is authorized, the realized standard-fee hold-to-settlement value of an individual quoted state may be defined as:

YES:

    realized_value_YES(C)
      = C * (y-P_YES)
        - fee_YES(C)

NO:

    realized_value_NO(C)
      = C * ((1-y)-P_NO)
        - fee_NO(C)

where `y` is the binary settlement outcome.

These formulas describe an individual hypothetical quoted entry held to settlement.

D-021L-06 does not authorize calculating a trading-strategy P&L series.

### No entry rule

Model-2 v1 has no frozen trading threshold.

In particular, D-021L-06 does not declare:

- EV > 0 as an automatic buy
- a 1-cent threshold
- a 2-cent threshold
- a 3-cent threshold
- a 4-cent threshold
- a 5-cent threshold
- any uncertainty-adjusted threshold

Positive EV means only:

`candidate opportunity for later entry-policy research`.

Whether estimated EV is sufficiently large and reliable to justify action remains unresolved by design.

### No anchor-selection policy

D-021L-06 does not define:

- first qualifying anchor
- last qualifying anchor
- best anchor
- wait-versus-enter logic
- fixed TTC preference
- anchor-specific thresholds

TTC remains an input to Model 2.

A later entry-policy study may determine whether waiting or acting at a particular time has incremental value.

### No strike/side-selection policy

D-021L-06 does not define:

- which strike to choose
- whether YES or NO must be preferred
- largest-edge-wins behavior
- one-candidate-per-event ranking

Model 2 may produce probability and economic-value estimates for every eligible state.

Selection among simultaneous opportunities belongs to the later entry-policy layer.

### No sizing policy

D-021L-06 does not define:

- contract quantity
- dollar stake
- bankroll fraction
- Kelly sizing
- compounding
- averaging
- Martingale behavior
- exposure limits

Sizing and exposure limits belong to later policy and deterministic risk-governor research.

### No position-management policy

D-021L-06 does not define:

- HOLD
- EXIT
- ADD
- profit targets
- stop losses
- averaging rules

Those belong to Model 3 and the deterministic risk governor.

### No fill claim

The execution archive lacks historical full-depth order books and queue position.

Therefore quoted-entry economics are not a realistic fill simulation.

The economic quantities defined here must not be described as proof that the hypothetical quantity would have executed at the displayed quote.

Future realistic paper execution must separately model:

- available depth
- spread
- latency
- price movement
- partial fills
- missed fills
- queue uncertainty
- fees
- model uncertainty

### Relationship to statistical validation

The D-021L-05 statistical gates remain the advancement gates for Model-2 probability quality.

D-021L-06 adds no new economic advancement threshold.

This is intentional.

First determine whether Model 2 predicts settlement probabilities more reliably than Candidate E.

Only after statistical validation should a separately predeclared entry-policy experiment ask:

`Given Model-2 probabilities and economic values through time, when is acting preferable to waiting or abstaining?`

### Checkpoint-21L boundary

Checkpoint 21L freezes:

1. Model-2 target and Candidate-E offset architecture
2. causal feature contract
3. chronological evidence roles
4. model family, preprocessing, and tuning
5. statistical validation and locked-test gates
6. strategy-neutral economic-value formulas

It deliberately does not freeze a trading strategy.

Model fitting remains prohibited until Checkpoint 21L is safely closed.
