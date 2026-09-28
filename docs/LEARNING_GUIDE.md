# Event-Market Quant Bot — Learning Guide

**Purpose:** Cumulative teaching notebook and workbook for the Event-Market Quant Bot project.

**Current synchronization point:** Checkpoint 21N-A — Candidate-E Quoted-Entry Hold Strategy design freeze.

**Core rule:** Do not try to memorize this document. Use it to build intuition, work small examples, revisit equations, take notes, and practice explaining the ideas.

---

# 1. How this guide should be maintained

Whenever a meaningful checkpoint introduces a new concept, update this guide in this order:

1. **Intuition** — explain the idea as if the reader has never seen it.
2. **Tiny example** — use small numbers.
3. **Equation or formal definition** — only after the intuition.
4. **Symbols** — define every variable.
5. **Project connection** — explain where the concept appears in Event-Market Quant Bot.
6. **Failure modes** — explain how the concept can be misused.
7. **Practice** — add questions that require recall and calculation.
8. **Checkpoint lesson** — record what the actual evidence taught us.

This learning guide explains the project. It does **not** replace the canonical state, decision, experiment, handoff, backlog, or risk-policy documents.

---

# 2. The project in one picture

The current primary modeling target is **KXBTCD**, a family of Kalshi Bitcoin event contracts.

A binary event eventually settles:

\[
Y =
\begin{cases}
1 & \text{YES}\\
0 & \text{NO}
\end{cases}
\]

Our central forecasting question is:

\[
P(Y=1\mid X)
\]

Read that as:

> What is the probability that the contract settles YES, given the information \(X\) available now?

Possible information \(X\) includes:

- Kalshi market midpoint;
- strike;
- time-to-close;
- spread;
- independent BTC price;
- recent BTC return;
- volatility;
- data-quality information.

The project deliberately separates:

1. **Raw observations**
2. **Causally synchronized state**
3. **Settlement label**
4. **Model probability**
5. **Execution economics**
6. **Decision policy**
7. **Risk/execution**

The current phase remains read-only. A good probability model is not automatically a profitable trading strategy.

---

# 3. Mathematical notation you should recognize

## Variables

Examples:

\[
q=\text{Kalshi midpoint}
\]

\[
S=\text{independent BTC price}
\]

\[
K=\text{strike}
\]

\[
T=\text{time-to-close}
\]

\[
Y=\text{settlement outcome}
\]

## Subscript

\[
q_i
\]

means the midpoint for observation \(i\).

## Prediction hat

\[
\hat p
\]

means an estimated or predicted probability.

## Summation

\[
\sum_{i=1}^{n}x_i
\]

means:

\[
x_1+x_2+\cdots+x_n
\]

## Function

\[
y=f(x)
\]

means that function \(f\) transforms input \(x\) into output \(y\).

Machine-learning models are functions:

\[
\hat y=f(X)
\]

---

# 4. Event-market basics

## Binary settlement

The target is:

\[
Y\in\{0,1\}
\]

The market can trade at a probability-like price such as:

\[
q=0.62
\]

Our benchmark interprets this as the market's current settlement-probability estimate.

That does not mean price is a perfect probability. Spread, fees, liquidity, risk preferences, and market microstructure can affect the tradable price.

## Strike

Let:

\[
K=\text{contract threshold}
\]

An external BTC price is useful only relative to the strike.

A BTC price of \$120,000 means different things for:

- a \$118,000 strike;
- a \$120,000 strike;
- a \$122,000 strike.

## Time-to-close

Let:

\[
T=\text{time remaining}
\]

A \$300 distance from strike is not equally important with 55 minutes and 2 minutes remaining.

### Project lesson

KXBTCD history showed that the selected markets were mostly about one hour in lifecycle. The project therefore replaced an earlier long-horizon materialization grid with:

- 55m
- 50m
- 45m
- 40m
- 35m
- 30m

The lesson was structural: model design has to respect how the actual product exists.

---

# 5. Bid, ask, midpoint, spread, and depth

## Bid

Highest currently quoted buying price.

## Ask

Lowest currently quoted selling price.

If:

\[
bid=0.48,\quad ask=0.50
\]

then the midpoint is:

\[
q=\frac{0.48+0.50}{2}=0.49
\]

and the spread is:

\[
spread=0.50-0.48=0.02
\]

## Depth

Depth is the amount of quantity available at different prices.

A tight spread does not necessarily mean large depth.

A large depth does not necessarily mean a tight spread.

### Why models care

Spread can potentially reflect uncertainty or liquidity conditions.

Candidate C tested whether the effect of the market probability depended on spread.

---

# 6. Raw data, derived data, and lineage

A large part of this project was spent building trustworthy data infrastructure before modeling.

That is necessary because a model result is worthless if we cannot verify what data created it.

## Raw data

The original API response, preserved before transformation.

## Derived data

Values calculated from raw data.

Examples:

- midpoint;
- spread;
- TTC;
- synchronized BTC state;
- model features.

## Lineage

Lineage answers:

> Which exact raw observation produced this derived row?

The project carries raw request/session identifiers into derived artifacts.

## Run manifest

A run manifest is a receipt for one program run.

It records items such as:

- run ID;
- arguments;
- code state;
- artifacts;
- counts;
- hashes;
- success/failure state.

## Fingerprint

A SHA-256 fingerprint provides a deterministic identity for frozen content.

If the specification changes, the fingerprint changes.

### Why this matters

Before opening stronger evidence, we want to know:

> The model, data rules, and scoring procedure really were frozen.

---

# 7. Wall-clock time, monotonic time, and causal availability

## Wall-clock time

Calendar time reported by the operating system.

Example:

`2026-08-16T01:30:00Z`

Wall clocks can be slightly wrong or can jump.

## Monotonic time

A clock designed for ordering and elapsed durations.

If:

\[
t_2^{mono}>t_1^{mono}
\]

then event 2 happened later on the local machine.

## First-seen causality

For live modeling, a feature is valid only if our process had received it by the state being modeled.

Conceptually:

\[
t_{\text{feature received}}
\le
t_{\text{decision}}
\]

## No future interpolation

Suppose a prediction is made at 8:31:20.

A full candle covering 8:31:00–8:32:00 contains 40 seconds of future information.

Using that complete candle leaks the future.

## Project clock lesson

A Windows wall-clock audit showed roughly 170 ms of offset.

Therefore the project allows local monotonic ordering, but does not authorize sub-second cross-feed lead/lag claims.

---

# 8. Probability foundations

## Probability

\[
0\le p\le1
\]

Examples:

- 0.10 = 10%
- 0.50 = 50%
- 0.90 = 90%

## Conditional probability

Our target:

\[
P(Y=1\mid X)
\]

means:

> probability of YES conditional on the currently available state.

## Expectation

For a discrete random variable:

\[
E[X]=\sum_x xP(X=x)
\]

Expectation is a probability-weighted average.

## Variance

\[
Var(X)=E[(X-E[X])^2]
\]

Variance measures dispersion around the mean.

These ideas later connect to:

- model uncertainty;
- volatility;
- expected value;
- risk.

---

# 9. The baseline: Kalshi's raw midpoint

Our baseline is:

\[
\hat p_{\text{raw}}=q
\]

A new model is useful only if it improves on this benchmark on genuinely new evidence.

Why is this hard?

Because market prices already aggregate information from many participants.

A model that predicts outcomes well is not enough.

It needs to answer:

> Does it add information beyond what the market already knows?

---

# 10. Training, validation, and test

## Training

Used to learn model parameters.

Examples:

\[
\beta_0,\beta_1,\beta_2
\]

## Validation

Used for limited predeclared model selection.

Examples:

- selecting a regularization value;
- choosing among a tiny frozen model menu.

Once validation outcomes influence a choice, the set is exposed.

## Test

Used to evaluate the fully frozen procedure.

A clean test should not be used to redesign the model afterward.

## Chronological split

Financial modeling should usually respect time:

> fit on earlier data, score on later data.

A random split can let similar or future regimes leak into the training side.

---

# 11. Rolling-origin evaluation

A rolling-origin design looks like:

- fit B1 → score B2
- fit B1+B2 → score B3
- fit B1+B2+B3 → score B4

This asks:

> Does the model continue working as time advances?

It is much more informative than only looking at one pooled average.

---

# 12. Leakage and contamination

## Feature leakage

Future information enters a current feature.

Example:

> using the rest of a candle that had not happened yet.

## Test contamination

A test result influences the model that is then rescored on the same test.

Bad workflow:

1. score final test;
2. inspect failures;
3. change features;
4. score same test again;
5. call it untouched.

The second score is not an untouched test.

## Why we freeze things

The project freezes:

- splits;
- feature formulas;
- model family;
- hyperparameter grid;
- scoring metrics;
- advancement rules;
- final model artifact.

Then stronger evidence is opened.

---

# 13. Effective sample size and dependence

Suppose one market gives us 1,000 quote rows.

Those are not 1,000 independent settlements.

They all eventually share one event outcome.

## Event-equal weighting

For event \(e\) with \(n_e\) rows:

\[
L_e=\frac{1}{n_e}\sum_{i\in e}L_i
\]

Then across \(E\) events:

\[
L=\frac{1}{E}\sum_{e=1}^{E}L_e
\]

This gives every event equal total weight.

## Serial correlation

Nearby financial observations are related.

BTC at 10:00:01 is usually similar to BTC at 10:00:00.

Therefore:

\[
\text{row count}\neq\text{independent sample count}
\]

This is why the project focuses on chronological blocks and event counts rather than bragging about huge raw-row counts.

---

# 14. Logistic regression from zero

Logistic regression is a simple binary probability model.

## Step 1: calculate a score

\[
z=
\beta_0+
\beta_1x_1+
\beta_2x_2+
\cdots+
\beta_kx_k
\]

## Step 2: convert it to probability

\[
\hat p=\sigma(z)
\]

where:

\[
\sigma(z)=\frac{1}{1+e^{-z}}
\]

Examples:

\[
z=0\Rightarrow\hat p=0.5
\]

\[
z=2\Rightarrow\hat p\approx0.881
\]

\[
z=-2\Rightarrow\hat p\approx0.119
\]

## Coefficients

If:

\[
\beta_j>0
\]

increasing feature \(x_j\), holding others fixed, pushes the prediction toward YES.

If:

\[
\beta_j<0
\]

it pushes toward NO.

Important:

> A coefficient is not a bet size.

It is a learned contribution to the model score.

---

# 15. Odds and logit

## Odds

\[
odds=\frac{p}{1-p}
\]

If:

\[
p=0.75
\]

then:

\[
odds=3
\]

## Logit

\[
logit(p)=
\ln\left(\frac{p}{1-p}\right)
\]

Examples:

\[
logit(0.5)=0
\]

\[
logit(0.9)\approx2.197
\]

\[
logit(0.1)\approx-2.197
\]

## Why it is useful for Kalshi

A simple recalibration model can be:

\[
\hat p=
\sigma\left(
\beta_0+
\beta_1logit(q)
\right)
\]

If:

\[
\beta_0=0,\quad\beta_1=1
\]

then:

\[
\hat p=q
\]

So the raw market is naturally nested inside the model.

---

# 16. Log loss

For one binary observation:

\[
L_i=
-\left[
y_i\ln(\hat p_i)
+
(1-y_i)\ln(1-\hat p_i)
\right]
\]

If YES occurs:

\[
L=-\ln(\hat p)
\]

If NO occurs:

\[
L=-\ln(1-\hat p)
\]

Lower is better.

## Example

YES occurs.

Prediction:

\[
\hat p=0.70
\]

Loss:

\[
-\ln(0.70)\approx0.357
\]

Now suppose the model predicts 99% YES but NO occurs:

\[
-\ln(0.01)\approx4.605
\]

Log loss heavily punishes confident mistakes.

That makes it a strong metric for probability forecasts.

---

# 17. Brier score

\[
B_i=(\hat p_i-y_i)^2
\]

If YES occurs and we predict 0.80:

\[
(0.8-1)^2=0.04
\]

If NO occurs:

\[
(0.8-0)^2=0.64
\]

Lower is better.

Our project commonly uses:

- primary: event-weighted log loss;
- secondary: event-weighted Brier score.

The secondary metric does not override the frozen primary gate.

---

# 18. Calibration

A probability model should mean what it says.

If a well-calibrated model makes many predictions around 70%, roughly 70% of comparable cases should settle YES over a sufficiently large representative sample.

Calibration asks:

> When the model says \(p\), do outcomes behave like \(p\)?

Prediction markets make calibration especially important because the model output itself is a probability.

---

# 19. How training mathematically learns the beta values

The model is:

\[
\hat p_i=\sigma(X_i\beta)
\]

The feature values are known.

The outcomes are known in training.

The beta values are unknown.

Training chooses:

\[
\beta^*
=
\arg\min_{\beta}L(\beta)
\]

Read this as:

> Find the beta values that minimize training loss.

For logistic regression:

\[
L(\beta)=
-\sum_i
\left[
y_i\ln(\hat p_i)
+
(1-y_i)\ln(1-\hat p_i)
\right]
\]

## Gradient

For coefficient \(\beta_j\):

\[
\frac{\partial L}{\partial\beta_j}
=
\sum_i
(\hat p_i-y_i)x_{ij}
\]

Intuition:

\[
\text{gradient}
\approx
\text{prediction error}
\times
\text{feature value}
\]

summed across observations.

If the model repeatedly underpredicts YES when a feature is positive, the optimizer receives pressure to increase that feature's coefficient.

---

# 20. Tiny gradient example

Use one feature:

\[
\hat p=\sigma(\beta_0+\beta_1x)
\]

Training observations:

| \(x\) | \(y\) |
|---:|---:|
| -1 | 0 |
| 0 | 0 |
| +1 | 1 |

Start:

\[
\beta_0=0,\quad\beta_1=0
\]

All predictions are:

\[
0.5
\]

Gradient for \(\beta_1\):

\[
(0.5-0)(-1)
+
(0.5-0)(0)
+
(0.5-1)(1)
\]

\[
=-0.5+0-0.5=-1
\]

A negative gradient tells the optimizer that increasing \(\beta_1\) reduces loss.

The model learns:

> larger \(x\) should increase YES probability.

---

# 21. Gradient descent, Newton's method, and Hessian

## Gradient descent

\[
\beta_{new}
=
\beta_{old}
-
\eta\nabla L
\]

Where:

- \(\nabla L\) = gradient;
- \(\eta\) = step size.

The gradient tells us which direction is downhill.

## Hessian

\[
H=\nabla^2L
\]

The Hessian measures local curvature.

For standard logistic regression:

\[
H=X^TWX
\]

where \(W\) contains terms involving:

\[
\hat p_i(1-\hat p_i)
\]

## Newton update

\[
\beta_{new}
=
\beta_{old}
-
H^{-1}g
\]

Plain English:

> Use the slope and the local shape of the loss surface to decide the coefficient update.

The project's logistic fits have used deterministic damped Newton methods.

## Convergence

Near a mathematical optimum:

\[
\nabla L(\beta)\approx0
\]

But remember:

\[
\boxed{\text{training optimum}\neq\text{real-world optimum}}
\]

Validation is still required.

---

# 22. Parameters vs hyperparameters

## Parameters

Learned directly from training data.

Examples:

\[
\beta_0,\beta_1,\beta_2
\]

## Hyperparameters

Settings controlling the model or training procedure.

Examples:

- regularization \(\lambda\);
- tree depth;
- number of trees;
- neural-network width;
- learning rate.

Training learns parameters.

Validation usually helps choose hyperparameters.

---

# 23. Regularization

A model can overfit by using unnecessarily large coefficients.

L2 regularization adds:

\[
L_{total}
=
L_{data}
+
\lambda\sum_j\beta_j^2
\]

Larger:

\[
\lambda
\]

means stronger shrinkage.

Smaller:

\[
\lambda
\]

allows more flexibility.

## Project lesson

Candidate B and Candidate C used predeclared regularization choices.

After results were visible, the project did not expand the grid merely to rescue a candidate.

That is important scientific discipline.

---

# 24. Standardization

Standardization transforms:

\[
z=\frac{x-\mu}{\sigma}
\]

Where:

- \(\mu\) = mean;
- \(\sigma\) = standard deviation.

Why?

Features can have radically different scales.

Important anti-leakage rule:

> Fit \(\mu\) and \(\sigma\) on fitting data only.

Do not use future/test data to compute scaling.

---

# 25. Interaction terms

An additive model:

\[
z=
\beta_0+
\beta_1x_1+
\beta_2x_2
\]

assumes the effect of one feature does not depend on the other.

Add an interaction:

\[
z=
\beta_0+
\beta_1x_1+
\beta_2x_2+
\beta_3x_1x_2
\]

Now the effect of \(x_1\) can depend on \(x_2\).

Candidate C used:

- market logit;
- spread;
- market-logit × spread interaction.

The hypothesis was mathematically reasonable.

It still failed the one-time terminal test.

That is why mathematical plausibility is not enough.

---

# 26. Candidate B: what we tried and learned

Candidate B asked:

> Can simple market context improve the raw Kalshi midpoint?

Its validation event-weighted log loss was approximately:

- raw midpoint: 0.142316
- Candidate B: 0.145560

Candidate B was worse.

## Learning lesson

A simple contextual model does not automatically improve a market price.

More importantly, the frozen validation rule prevented us from opening the locked test just because we wanted another chance.

---

# 27. Candidate C: what we tried and learned

Candidate C asked:

> Does spread change the relationship between the market's log-odds and settlement?

Features:

- market logit;
- spread;
- market-logit × spread interaction.

It passed rolling-origin development and selected:

\[
\lambda=0.01
\]

It won all four development score blocks.

Then the final frozen model went to a one-time terminal test.

Terminal log loss:

- raw midpoint: approximately 0.052192
- Candidate C: approximately 0.068503

Candidate C lost.

## Learning lesson

A model can look excellent during development and fail genuinely new evidence.

This is one of the clearest demonstrations in the project of overfitting/generalization risk.

---

# 28. Candidate D: what we tried and learned

After Candidate C failed, the project simplified.

Candidate D was essentially a market-logit recalibration:

\[
logit(p_D)
=
logit(q)
+
\alpha
+
\delta logit(q)
\]

It improved pooled development metrics and improved 149 of 160 scored events.

But it won only 3 of 5 chronological score blocks.

Its newest block B6 was especially poor.

## Learning lesson

Pooled performance can hide temporal instability.

A model that looks good “on average” may be deteriorating in later regimes.

---

# 29. Why the next successor uses independent BTC state

Candidate B/C/D mostly transformed information already contained in Kalshi's own market state.

The next research question is different:

> Does an independent observation of Bitcoin contain information about settlement that Kalshi's probability has not fully incorporated?

The initial source families are:

- Coinbase;
- Kraken.

The exact Candidate E formula is not frozen yet.

This is important:

> We are changing the information source, not just making the same market-price model more complicated.

---

# 30. Candidate external-BTC feature: distance from strike

Let:

- \(S_t\) = independent BTC price;
- \(K\) = strike.

A useful candidate transformation is:

\[
d_t=
\ln\left(\frac{S_t}{K}\right)
\]

Interpretation:

- \(d_t=0\): BTC at strike;
- \(d_t>0\): BTC above strike;
- \(d_t<0\): BTC below strike.

Example:

\[
S=119850,\quad K=120000
\]

\[
d\approx\ln(119850/120000)\approx-0.00125
\]

approximately -0.125%.

Why this is attractive:

- directly tied to contract economics;
- scale normalized;
- naturally centered at zero.

This is still a candidate idea, not a frozen Candidate E feature.

---

# 31. Candidate external-BTC feature: recent return

A five-minute log return:

\[
r_{5m}
=
\ln\left(
\frac{S_t}{S_{t-5m}}
\right)
\]

Example:

BTC rises from 119,500 to 119,800.

\[
r_{5m}
=
\ln(119800/119500)
\approx0.00251
\]

approximately +0.251%.

This distinguishes:

> below strike and rising

from:

> below strike and falling.

Again, predictive value must be tested rather than assumed.

---

# 32. Candidate external-BTC feature: volatility

For recent returns \(r_1,\dots,r_n\), sample standard deviation is:

\[
s=
\sqrt{
\frac{1}{n-1}
\sum_{i=1}^{n}
(r_i-\bar r)^2
}
\]

This is a simple measure of recent dispersion.

Intuition:

> A fixed distance from strike may have a different crossing probability during high volatility than low volatility.

But adding volatility also adds complexity, so it should be justified by evidence.

---

# 33. Source disagreement and staleness

## Cross-source disagreement

If Coinbase and Kraken differ:

\[
disagreement
\propto
|S_C-S_K|
\]

Often normalized and expressed in basis points.

One basis point:

\[
1bp=0.01\%=0.0001
\]

Initially, disagreement is more naturally a **data-quality diagnostic** than a predictive feature.

## Source age

Conceptually:

\[
age
=
t_{decision}^{mono}
-
t_{source\ first-seen}^{mono}
\]

A permanent staleness threshold is not yet frozen.

---

# 34. Why logarithms appear often in finance

We use formulas such as:

\[
\ln(S/K)
\]

and:

\[
\ln(S_t/S_{t-5m})
\]

for several reasons.

## Relative scale

A \$500 move means different things when BTC is \$20,000 versus \$120,000.

A ratio handles scale better.

## Sign symmetry

Above the reference:

\[
\ln(S/K)>0
\]

Below:

\[
\ln(S/K)<0
\]

## Additivity

\[
\ln(S_2/S_0)
=
\ln(S_1/S_0)
+
\ln(S_2/S_1)
\]

This is mathematically convenient.

---

# 35. Historical data vs live data

Historical and live data answer different questions.

## Historical data is strong for

- many events;
- model training;
- regime coverage;
- chronological evaluation;
- features that can be causally reconstructed.

## Live data is uniquely strong for

- local first-seen timing;
- real request failures;
- transport availability;
- actual source age;
- local receive skew;
- exact live states that are not historically archived.

## Prospective does not mean continuously streamed

A future test can remain prospective if:

1. the model/protocol is frozen first;
2. the events happen later;
3. their outcomes remain untouched;
4. data is downloaded afterward;
5. all features are reconstructed using only information available by the original state time.

Therefore:

\[
\boxed{prospective\neq must\ be\ live-streamed}
\]

---

# 36. Checkpoint 19B

19B was a 420-second outcome-blind engineering pilot.

It showed that the project could attach Coinbase and Kraken observations to KXBTCD states with:

- raw lineage;
- local monotonic first-seen timing;
- source-availability tracking;
- cross-source disagreement;
- five-minute-history diagnostics.

It was an engineering feasibility PASS.

It was not evidence that external BTC improves prediction.

---

# 37. Checkpoint 19C

19C is a frozen 24-hour outcome-blind availability audit.

External source cadence:

- Coinbase/Kraken every 15 seconds.

KXBTCD cadence:

- every 5 minutes.

Questions:

- Are both sources available across a full day?
- How stale are observations?
- How much do sources disagree?
- Can five-minute causal history be reconstructed?
- What failure streaks occur?
- Which KXBTCD TTC/calendar states are observed?

19C intentionally does **not** choose:

- Candidate E formula;
- permanent source IDs for E1 modeling;
- consensus price;
- staleness threshold;
- disagreement threshold;
- E1/E2/E3 sample sizes;
- advancement gate.

---

# 38. E0 / E1 / E2 / E3 evidence

## E0 — exploratory

Already exposed data.

Use for:

- diagnostics;
- learning;
- hypotheses;
- engineering.

Do not call it untouched.

## E1 — successor-design evidence

New chronological events after the successor protocol freeze.

May help select among a small predeclared model menu.

Once used, it becomes exposed.

## E2 — final fitting

Begins only after one successor specification is frozen.

Can estimate final parameters.

Cannot redesign the model family.

## E3 — untouched prospective test

Begins after the final E2 model is frozen.

Used once to judge the final frozen procedure.

Central rule:

\[
\boxed{\text{exposed evidence cannot later become stronger evidence}}
\]

---

# 39. Bias and variance

## Bias

Error caused by a model being too restrictive.

A straight-line relationship may miss a nonlinear truth.

## Variance

Sensitivity to quirks in the training sample.

Highly flexible models can fit noise.

Conceptual decomposition:

\[
test\ error
\approx
bias^2
+
variance
+
irreducible\ noise
\]

The exact formal decomposition depends on the setting, but the intuition is fundamental.

---

# 40. Why complex models can be better

Complex models are not usually better because they have “more precise optimization formulas.”

They are better when they can represent real relationships that simpler models cannot.

Examples of possible nonlinear structure:

- BTC distance matters only near expiry;
- momentum matters only near the strike;
- volatility changes the meaning of distance;
- market spread matters differently at 50% than at 95%.

More flexibility can capture these.

But the same flexibility can also fit noise.

---

# 41. Decision trees

A decision tree creates rules such as:

```text
BTC above strike?
├── YES: TTC < 10m?
│   ├── YES: ...
│   └── NO: ...
└── NO: 5m return positive?
    ├── YES: ...
    └── NO: ...
```

Trees naturally represent:

- thresholds;
- nonlinear effects;
- interactions.

---

# 42. Gradient boosting

Gradient boosting builds many small trees sequentially.

Each tree tries to improve errors left by the current ensemble.

Examples of model families:

- XGBoost;
- LightGBM.

Advantages:

- strong nonlinear modeling;
- automatic interactions;
- flexible feature relationships.

Risks:

- more hyperparameters;
- overfitting;
- validation overuse;
- reduced interpretability.

For this project, boosting should come only after simpler independent-BTC baselines establish that useful incremental information exists.

---

# 43. Neural networks

A neural-network layer often looks like:

\[
h=f(Wx+b)
\]

Where:

- \(x\) = input;
- \(W\) = learned weight matrix;
- \(b\) = learned bias;
- \(f\) = nonlinear activation;
- \(h\) = representation.

A deep network repeats this:

\[
h_1=f_1(W_1x+b_1)
\]

\[
h_2=f_2(W_2h_1+b_2)
\]

\[
\hat y=f_3(W_3h_2+b_3)
\]

Experts do not understand millions of individual weights one by one.

They understand the building blocks and how information flows through the architecture.

---

# 44. Backpropagation

Backpropagation efficiently applies the chain rule.

If:

\[
y=f_3(f_2(f_1(x)))
\]

then derivatives propagate backward through the composition.

The conceptual loop is still:

\[
prediction
\rightarrow
loss
\rightarrow
gradient
\rightarrow
parameter\ update
\]

A CNN may be huge, but it still rests on:

- linear algebra;
- calculus;
- probability;
- optimization.

---

# 45. CNN intuition

CNN means convolutional neural network.

A convolution applies a learned local filter across spatial data such as an image.

Early layers often detect simple local patterns.

Deeper layers combine them into higher-level patterns.

You do not need to understand every learned weight.

You need to understand:

- why convolution exploits spatial locality;
- how layers build representations;
- how loss generates gradients;
- how backpropagation updates parameters;
- how overfitting is controlled.

---

# 46. Forecasting is not trading

Suppose:

\[
\hat p_{model}=0.61
\]

and a tradable price appears to be 0.55.

It is tempting to call this a 6-cent edge.

That is incomplete.

A decision would eventually need to account for:

- model uncertainty;
- fees;
- spread;
- depth;
- slippage;
- latency;
- partial fills;
- missed fills;
- exposure;
- risk limits.

The current project intentionally separates forecasting from execution.

---

# 47. Expected value — future economics concept

For learning only; this does not authorize execution.

Suppose a YES contract costs \(c\), pays 1 if YES and 0 if NO, with no fees.

If true YES probability is \(p\):

\[
EV=p(1-c)+(1-p)(-c)
\]

Simplify:

\[
EV=p-c
\]

In an unrealistic frictionless world:

\[
p>c
\]

would imply positive theoretical EV.

Real trading is harder because \(p\) is uncertain and execution has costs.

---

# 48. Spread, fees, depth, slippage, latency, fills

## Fees

Directly reduce economics.

## Spread

Buying at the ask is worse than assuming the midpoint.

## Depth

Determines how much can execute near the quoted price.

## Slippage

Larger orders can move through worse price levels.

## Latency

State can change between observation and action.

## Partial fill

Only some quantity executes.

## Missed fill

No execution occurs at the assumed level.

Any future paper trading must model all of these rather than assume perfect fills.

---

# 49. Fail closed

Fail closed means:

> If required state cannot be established as valid, stop rather than guess.

Examples:

- stale feed;
- sequence gap;
- parser/schema ambiguity;
- clock problem;
- incomplete raw persistence;
- unclear settlement rule;
- incomplete risk state.

This is an engineering safety principle.

---

# 50. Testing and reproducibility

Quantitative conclusions depend on software correctness.

## Unit test

Tests a small component.

Example:

> Does a log-return function produce the expected number?

## Integration test

Tests components together.

Example:

> Does a raw source observation become the correct synchronized state with lineage?

## Regression suite

Checks that new work did not break existing behavior.

At the Checkpoint 19C design closeout:

- 722 tests passed;
- 22 subtests passed.

That is engineering evidence, not proof of predictive edge.

---

# 51. Why we freeze before testing

Without a freeze:

1. try model;
2. test;
3. lose;
4. change feature;
5. retest;
6. change hyperparameter;
7. retest;
8. eventually find something that wins.

If only the last result is reported, the experiment exaggerates evidence.

Freezing means:

> Decide what counts as success before seeing the evidence that judges it.

That makes both wins and failures meaningful.

---

# 52. Optimization vs generalization

## Optimization

\[
\text{Find parameters that minimize training loss.}
\]

## Generalization

\[
\text{Determine whether the learned relationship works on new data.}
\]

A model can be optimized perfectly and still generalize badly.

Candidate C is the clearest project example.

---

# 53. Why simple models come first

Simple models give:

- interpretability;
- fewer degrees of freedom;
- easier debugging;
- clearer failure attribution;
- lower overfitting risk.

A more complex model is justified when:

1. useful information has been established;
2. the relationship appears nonlinear;
3. the amount of independent data supports more flexibility;
4. a frozen validation protocol can evaluate the extra complexity.

---

# 54. The five mathematical foundations

## Algebra

Know:

- equations;
- functions;
- exponents;
- logarithms.

## Linear algebra

Know:

- vectors;
- matrices;
- dot products;
- matrix multiplication;
- transpose.

## Calculus

Know:

- derivative;
- partial derivative;
- gradient;
- chain rule;
- second derivative.

## Probability/statistics

Know:

- conditional probability;
- expectation;
- variance;
- likelihood;
- sampling;
- dependence;
- estimation;
- uncertainty.

## Optimization

Know:

- objective;
- gradient descent;
- Newton's method;
- convexity;
- regularization.

These foundations make advanced ML much less mysterious.

---

# 55. How to study efficiently with this project

Use two tracks.

## Track A — project-driven learning

When a concept appears:

1. read its guide section;
2. work one tiny example by hand;
3. explain it without notes;
4. find where it appears in the project;
5. answer the practice questions.

## Track B — foundations

Suggested order:

1. algebra and logarithms;
2. probability basics;
3. vectors and matrices;
4. derivatives and partial derivatives;
5. expectation, variance, likelihood;
6. regression;
7. gradients and optimization;
8. regularization;
9. trees and boosting;
10. neural networks and backpropagation.

---

# 56. Mastery levels

For each topic, ask which level you have reached.

## Level 1 — Recognize

I know the vocabulary.

## Level 2 — Explain

I can explain it in plain English.

## Level 3 — Calculate

I can work a small example manually.

## Level 4 — Implement

I can code a simple version.

## Level 5 — Diagnose

I can identify when it is being used incorrectly.

For professional work and interviews, Level 5 is extremely valuable.

---

# 57. Practice set A — market and probability basics

### A1

Bid = 0.46, ask = 0.50.

Find midpoint and spread.

### A2

Model predicts 0.80 YES and YES occurs.

Find Brier score.

### A3

Same prediction, but NO occurs.

Find Brier score.

### A4

Why does log loss punish a wrong 99% prediction more than a wrong 55% prediction?

### A5

Why do 500 rows from one contract not equal 500 independent settlement outcomes?

---

# 58. Practice set B — logistic regression

### B1

Given:

\[
z=-0.5+1.2x
\]

and:

\[
x=1
\]

find \(z\) and estimate \(\sigma(z)\).

### B2

What does a positive coefficient on BTC distance-from-strike mean?

### B3

Why can raw coefficient magnitudes be misleading when features have different scales?

### B4

Which values make:

\[
\sigma(\beta_0+\beta_1logit(q))
\]

exactly equal to \(q\)?

---

# 59. Practice set C — optimization

### C1

Parameter vs hyperparameter?

### C2

What does the gradient tell us?

### C3

What does the Hessian add?

### C4

Why does minimum training loss not prove generalization?

### C5

What happens as L2 \(\lambda\) becomes larger?

---

# 60. Practice set D — validation

### D1

If validation chooses lambda, is validation still untouched?

### D2

If you redesign after seeing final test failures and reuse the same test, what happened?

### D3

Why use chronological validation for financial data?

### D4

Why can the full candle containing the prediction timestamp leak future information?

### D5

If pooled performance is positive but the newest blocks lose, what concern arises?

---

# 61. Practice set E — external BTC state

### E1

\[
S=120300,\quad K=120000
\]

Is:

\[
\ln(S/K)
\]

positive or negative?

### E2

BTC moves from 119,000 to 119,595.

Approximately what percentage move is that?

### E3

Why is distance-from-strike more natural than raw BTC price for a threshold contract?

### E4

Why should Coinbase/Kraken disagreement first be treated as a quality diagnostic?

### E5

How can a future E3 test remain prospective if the data is downloaded historically after the events occur?

---

# 62. Practice set F — our experiments

### F1

Why did Candidate B fail?

### F2

Why is Candidate C's terminal failure important even though its development results were strong?

### F3

What did Candidate D teach us about pooled metrics?

### F4

Why does the successor protocol require independent BTC state?

### F5

What unique information is the 19C live audit collecting that historical candles cannot fully recreate?

---

# 63. Short answer key

## A

**A1**

\[
midpoint=(0.46+0.50)/2=0.48
\]

\[
spread=0.04
\]

**A2**

\[
(0.8-1)^2=0.04
\]

**A3**

\[
(0.8-0)^2=0.64
\]

**A4**

Log loss is designed to punish confident incorrect probabilities heavily.

**A5**

The rows share one terminal event outcome and are dependent.

## B

**B1**

\[
z=0.7
\]

\[
\sigma(0.7)\approx0.668
\]

**B2**

Larger positive distance pushes YES probability upward, other variables held fixed.

**B3**

The practical contribution is \(\beta_jx_j\), not \(\beta_j\) alone.

**B4**

\[
\beta_0=0,\quad\beta_1=1
\]

## C

**C1**

Parameters are fitted from training data; hyperparameters control the model/training procedure.

**C2**

Local direction and rate of loss change.

**C3**

Local curvature.

**C4**

Training fit measures seen data, not unseen future performance.

**C5**

Stronger coefficient shrinkage.

## D

**D1**

No. Validation influenced model selection.

**D2**

The test became contaminated.

**D3**

It better represents learning from the past and predicting the future.

**D4**

Part of the candle occurs after the prediction time.

**D5**

Temporal instability, regime dependence, or overfitting.

## E

**E1**

Positive. BTC is above strike.

**E2**

About +0.5%.

**E3**

It represents the economically relevant threshold position and normalizes scale.

**E4**

Disagreement may reflect source uncertainty or transport/market differences; predictive value has not been established.

**E5**

The model and cohort rules were frozen before the events happened; later download does not contaminate design if outcomes remained untouched and features are causally reconstructed.

## F

**F1**

Its validation log loss was worse than the raw midpoint under the frozen strict-improvement gate.

**F2**

It showed that strong development performance did not generalize to a genuinely untouched chronological block.

**F3**

Positive pooled performance can hide deterioration in later chronological blocks.

**F4**

Repeated market-only transformations did not establish robust improvement; independent BTC state creates a different information hypothesis.

**F5**

Local first-seen timing, real source availability, request failures, source age, receive skew, and live causal alignment.

---

# 64. Interview questions to practice

Practice answering each in 30–90 seconds.

1. Why start with logistic regression?
2. What does the sigmoid do?
3. What is a logit?
4. How does logistic regression training choose beta values?
5. What is the difference between gradient and Hessian?
6. Parameter vs hyperparameter?
7. Why use regularization?
8. What is calibration?
9. Log loss vs Brier score?
10. Why use event-equal weighting?
11. Why chronological validation?
12. What is leakage?
13. What is test contamination?
14. Why did Candidate C fail despite strong development results?
15. What did Candidate D teach you?
16. Why add Coinbase/Kraken?
17. Why not jump directly to XGBoost or a neural network?
18. What does fail closed mean?
19. Why preserve raw data and lineage?
20. What has to happen before execution can even be discussed?

---

# 65. A concise project explanation

You should eventually be able to recreate this naturally without memorizing it:

> I am building a read-only quantitative research system for Kalshi Bitcoin event markets. I first built the data and audit infrastructure so model rows can be traced to raw observations. Then I tested simple probability models against Kalshi's own midpoint with chronological train, validation, and untouched-test procedures. Some models looked strong in development but failed later temporal or terminal gates, which taught me how easily market models can overfit. The current question is whether independent Bitcoin state from Coinbase and Kraken adds settlement information beyond Kalshi's own probability. I am validating source quality and causal alignment before fitting that successor.

---

# 66. Glossary

**Ask:** Lowest current quoted selling price.

**Baseline:** Reference model a candidate must beat.

**Basis point:** 0.01 percentage point.

**Beta coefficient:** Learned regression weight.

**Bias:** Error caused by restrictive model assumptions.

**Bid:** Highest current quoted buying price.

**Brier score:** Squared probability error.

**Calibration:** Agreement between predicted probabilities and observed frequencies.

**Candidate:** Frozen proposed model/specification being evaluated.

**Causal feature:** Feature containing only information available by prediction time.

**Chronological split:** Fit earlier data, score later data.

**Contamination:** Evaluation evidence influences the model it is supposed to judge.

**Depth:** Quantity available across order-book levels.

**Derived data:** Data calculated from raw source observations.

**Event-equal weighting:** Each event receives equal total scoring weight.

**Feature:** Model input.

**Fingerprint:** Deterministic hash identifying frozen content.

**Gradient:** Vector of first derivatives of loss.

**Hessian:** Matrix of second derivatives / local curvature.

**Hyperparameter:** Model/training setting chosen outside ordinary parameter fitting.

**IID:** Independent and identically distributed.

**Interaction:** Term allowing the effect of one feature to depend on another.

**Label:** Supervised-learning target.

**Leakage:** Future/unavailable information enters a model feature.

**Lineage:** Trace from derived data to exact raw observations.

**Log loss:** Probability scoring rule strongly penalizing confident errors.

**Log return:** Logarithm of a price ratio across time.

**Logit:** Log-odds transform.

**Manifest:** Run receipt containing identity, artifacts, counts, hashes, and status.

**Midpoint:** Average of best bid and best ask.

**Monotonic clock:** Clock useful for local ordering and elapsed time.

**Newton's method:** Optimizer using gradient and curvature.

**Overfitting:** Learning sample-specific noise that does not generalize.

**Parameter:** Model value fitted from training data.

**Prospective test:** Test on events occurring after model/protocol freeze.

**Raw data:** Original preserved source observation.

**Regularization:** Penalty discouraging excessive model complexity.

**Serial correlation:** Dependence between observations through time.

**Sigmoid:** Function mapping real scores to probabilities.

**Slippage:** Worse execution price due to depth or market movement.

**Spread:** Ask minus bid.

**Standardization:** Transform \((x-\mu)/\sigma\).

**Staleness:** Age of an observation relative to the modeled state.

**Test set:** Evaluation evidence not used in model selection.

**Time-to-close (TTC):** Remaining time in the contract state.

**Training set:** Data used to fit parameters.

**Validation set:** Data used for limited model/hyperparameter selection.

**Variance:** Statistical dispersion, or in model-complexity context, sensitivity to training-sample variation.

---

# 67. Personal notes area

## Concepts I can explain confidently

- _(add notes here)_

## Concepts I can calculate by hand

- _(add notes here)_

## Concepts I want to revisit

- _(add notes here)_

## Questions for the next checkpoint

- _(add notes here)_

## My own hypotheses

You can write hypotheses here, but anything that affects formal model selection still has to go through the project's frozen research protocol before relevant outcomes are used.

- _(add notes here)_

---

# 68. Future checkpoint maintenance checklist

Before closing a meaningful checkpoint, review this guide.

If the checkpoint introduced a genuinely new concept, add:

- [ ] zero-prior-knowledge explanation;
- [ ] equation or formal definition;
- [ ] symbol definitions;
- [ ] tiny numerical example;
- [ ] project-specific application;
- [ ] common failure modes;
- [ ] practice questions;
- [ ] checkpoint-specific lesson;
- [ ] glossary terms, if useful.

Also update the synchronization point near the top.

Do not add repetitive material merely to make the document longer.

---

# 69. More data does not fix every model problem

## Intuition

A model can fail for at least three different reasons:

1. **Too little data** — the model structure may be reasonable, but fitted parameters are noisy.
2. **Model misspecification** — the model cannot represent the real relationship, even with unlimited data.
3. **Missing information** — the inputs simply do not contain enough predictive information.

More representative data mainly helps the first problem. It can also reveal the second and third problems more clearly, but it does not automatically solve them.

## Tiny example

Suppose the true relationship is:

\[
y=x^2
\]

but we insist on fitting a straight line:

\[
\hat y=a+bx
\]

With 10 observations, the fitted line may be noisy. With 1,000,000 observations, the line becomes very stable — but it is still a line trying to represent a curve.

That is the difference between **estimation error** and **model bias**.

## Formal idea

A useful conceptual decomposition is:

\[
\text{prediction error}
\approx
\text{model/representation error}
+
\text{estimation error}
+
\text{irreducible uncertainty}
\]

- **Model/representation error:** the model or features cannot express the real relationship well enough.
- **Estimation error:** finite data causes uncertainty in fitted parameters.
- **Irreducible uncertainty:** future randomness or unobserved information cannot be eliminated by fitting.

## Project connection

Candidate C may have failed its terminal test because of noisy parameter estimates, unstable temporal relationships, overfitting to development structure, insufficient information in its Kalshi-derived features, or some combination of these.

Its failure does **not** prove that the market-logit/spread model family could never work with more independent data. It also does not justify repeatedly retraining the same frozen Candidate C on its exposed terminal set.

The correct lesson is:

> Before abandoning or expanding a model family, ask whether the observed failure looks data-limited, representation-limited, or information-limited.

## Failure modes

- Treating more rows from the same event as equivalent to more independent events.
- Assuming more old-regime data fixes current-regime drift.
- Reusing an exposed test set to retrain and then calling the result validated.
- Assuming a larger dataset compensates for missing causal features.

## Practice

1. If validation keeps improving as event count grows, which error source may still be important?
2. If train and validation performance both flatten at poor levels, what might that suggest?
3. Why can 50,000 rows from 200 events be less informative than 5,000 rows from 1,000 independent events?

---

# 70. Learning curves and data scaling

## Intuition

A **learning curve** asks:

> How does model performance change as the amount of training evidence grows?

This helps distinguish a model that is still data-hungry from one that may have reached a structural ceiling.

## Tiny example

Imagine the same model trained on increasingly many independent events:

| Training events | Train log loss | Validation log loss |
|---:|---:|---:|
| 50 | 0.05 | 0.20 |
| 100 | 0.07 | 0.16 |
| 200 | 0.09 | 0.13 |
| 500 | 0.10 | 0.115 |

Validation loss continues to fall. That suggests more data may still help.

Now imagine:

| Training events | Train log loss | Validation log loss |
|---:|---:|---:|
| 50 | 0.15 | 0.17 |
| 100 | 0.15 | 0.165 |
| 200 | 0.15 | 0.162 |
| 500 | 0.15 | 0.161 |
| 1,000 | 0.15 | 0.160 |

Both curves have nearly flattened. More data may have diminishing returns unless the representation changes.

## Formal definition

Let:

\[
L_{train}(N)
\]

be training loss after fitting on \(N\) training events, and:

\[
L_{val}(N)
\]

be validation loss on later untouched development evidence.

A learning curve studies these functions as \(N\) increases.

## Project connection

A future exploratory analysis could study permissible learning curves for a model family on non-terminal evidence. It must not reuse the permanently exposed Checkpoint-17 terminal block as a new validation set.

For this project, \(N\) should be interpreted primarily in terms of **independent events and chronological coverage**, not merely row count.

## Failure modes

- Changing features or hyperparameters while pretending only sample size changed.
- Reusing the same validation block so many times that it becomes another training signal.
- Ignoring chronology and regime coverage.
- Measuring scaling only by rows instead of independent events.

## Practice

1. What curve pattern suggests high variance and possible benefit from more data?
2. What pattern suggests a likely representation ceiling?
3. Why should event count and calendar diversity be reported alongside row count?

---

# 71. Feature justification and ablation

## Intuition

Adding a feature should represent a **specific new information hypothesis**, not a reaction to a failed model.

For example:

> BTC distance from the contract strike may contain incremental settlement information beyond Kalshi's own midpoint.

That is a mechanistic hypothesis.

By contrast:

> Add RSI because Candidate C failed.

is not sufficient justification by itself.

## Tiny example

Suppose we compare:

\[
M_0: \operatorname{logit}(q)
\]

\[
M_1: \operatorname{logit}(q)+d_{BTC}
\]

\[
M_2: \operatorname{logit}(q)+d_{BTC}+r_{5m}
\]

If \(M_1\) improves over \(M_0\), but \(M_2\) does not improve over \(M_1\), the evidence suggests BTC distance may add information while five-minute momentum may not.

## Formal definition

An **ablation study** removes or adds one component while keeping the rest of the experiment as comparable as possible.

For feature \(x_j\), one simple incremental comparison is:

\[
\Delta_j = L(M_{without\ j}) - L(M_{with\ j})
\]

where \(L\) is a scoring loss such as event-weighted log loss.

If \(\Delta_j>0\), the model containing the feature has lower loss in that comparison.

That does not by itself prove causality or permanent value; chronology and fresh evaluation still matter.

## Project connection

The Candidate-E direction is justified not because “more features are better,” but because it tests a **new independent information channel**: Coinbase/Kraken BTC state rather than another transformation of Kalshi's probability.

Potential simple hypotheses include:

\[
d_{BTC}=\ln(S/K)
\]

and later, if predeclared:

\[
r_{5m}=\ln(S_t/S_{t-5m})
\]

The exact Candidate-E formula remains unfrozen after Checkpoint 19C.

## Failure modes

- Trying dozens of indicators until one wins by chance.
- Adding several correlated features at once and then claiming each helped.
- Choosing features after looking at the same outcomes used to score them.
- Confusing feature availability with predictive value.

## Practice

1. What mechanism connects \(\ln(S/K)\) to KXBTCD settlement?
2. Why is a Coinbase/Kraken price feature more informationally distinct from \(q\) than \([\operatorname{logit}(q)]^2\)?
3. What would an ablation comparison for five-minute return look like?

---

# 72. Online learning, continual learning, and true labels

## Intuition

A deployed forecasting model can keep collecting new examples. After a KXBTCD event settles, the system finally knows the true label:

\[
Y\in\{0,1\}
\]

So a prediction made earlier can become a new labeled training example later.

This general family of adaptation is often called **online learning** or **continual learning**.

Important terminology: **self-training** often means training from one's own pseudo-labels. That is not what we mean here. KXBTCD eventually provides a real settlement label.

## Tiny example

Before settlement, the frozen model recorded:

\[
X=(q=0.42,\ d_{BTC}=-0.0012,\ r_{5m}=0.0025)
\]

and predicted:

\[
\hat p=0.46
\]

Later the event settles YES:

\[
Y=1
\]

The stored record can now become a labeled example:

\[
(X,Y)=(X,1)
\]

for a future retraining cycle.

## Formal update example

For a simple logistic model, one gradient-descent-style update could look like:

\[
\beta_{new}
=
\beta_{old}
-
\eta(\hat p-y)x
\]

where:

- \(\beta\) = model coefficients;
- \(\eta\) = learning rate;
- \(\hat p\) = current prediction;
- \(y\) = observed label;
- \(x\) = feature vector.

This equation shows that automatic per-example updating is technically possible. It does **not** mean it is the best governance design for this project.

## Project connection

The project already has an accepted rule against silent live self-rewriting. A safer future architecture is:

\[
\text{collect continuously}
\rightarrow
\text{retrain offline periodically}
\rightarrow
\text{test challenger}
\rightarrow
\text{promote explicitly if gates pass}
\]

That preserves adaptation without giving up reproducibility.

## Failure modes

- Updating heavily from one unusual event.
- Treating many rows from one event as many independent labels.
- Changing the live model without version tracking.
- Training immediately on an outcome and then evaluating on that same outcome.

## Practice

1. Why is a settled KXBTCD outcome a true label rather than a pseudo-label?
2. What is the statistical danger of updating from every row of one event as if rows were IID?
3. Why might periodic retraining be preferable to per-event coefficient updates?

---

# 73. Data drift and concept drift

## Intuition

Markets do not have to behave the same way forever.

Two different things can change:

### Data drift

The distribution of inputs changes:

\[
P_t(X) \neq P_{t+1}(X)
\]

Example: BTC volatility becomes much higher, so the distribution of five-minute returns changes.

### Concept drift

The relationship between inputs and outcomes changes:

\[
P_t(Y\mid X) \neq P_{t+1}(Y\mid X)
\]

Example: the same BTC distance from strike may imply a different settlement probability because Kalshi participants, liquidity, or market efficiency changed.

## Tiny example

Suppose successive model versions estimate the BTC-distance coefficient as:

\[
4.1\rightarrow3.8\rightarrow3.2
\]

That does not automatically prove concept drift. The change could come from:

- genuine market change;
- different sample composition;
- estimation noise;
- feature scaling changes;
- implementation differences.

The system must investigate rather than narrate coefficient movement as fact.

## Project connection

Future live prospective data could support monitoring of:

- feature distributions;
- source availability/staleness;
- calibration;
- event-weighted log loss;
- Brier score;
- residual patterns;
- coefficients for interpretable models;
- feature importance for more complex models.

## Failure modes

- Calling every parameter movement “regime change.”
- Retraining automatically because one metric moved for a short period.
- Comparing coefficients across versions that used different scaling or features.
- Ignoring the uncertainty of coefficient estimates.

## Practice

1. Give one KXBTCD example of data drift.
2. Give one example of concept drift.
3. Why does a changing coefficient not by itself prove concept drift?

---

# 74. Champion/challenger model architecture

## Intuition

A **champion** is the frozen model currently trusted to generate prospective predictions.

A **challenger** is a newly trained model that must prove itself against the champion before replacement.

The central idea is:

> Learn from new data without silently changing the model that is currently being evaluated live.

## Tiny example

Model v1 is frozen through October 1 and generates 500 prospective forecasts during October.

After those markets settle, a challenger v2 may be trained using eligible newly labeled data.

Then v2 is compared with v1 on a later chronological block that v2 did not train on.

If v2 fails the promotion gate:

\[
\text{Champion remains v1}
\]

If v2 passes every predeclared gate:

\[
\text{Champion becomes v2}
\]

## Formal architecture

\[
M_t
\rightarrow
\text{prospective prediction ledger}
\rightarrow
\text{new settlements}
\rightarrow
D_{new}
\rightarrow
\text{offline challenger }M_{t+1}
\rightarrow
\text{fresh promotion evaluation}
\]

The exact future promotion gate is **not yet frozen**.

## Project connection

A future prospective prediction ledger should preserve at least:

- exact model version/fingerprint;
- feature-contract version;
- source IDs and raw lineage;
- prediction timestamp and local monotonic timing where applicable;
- input features;
- raw Kalshi midpoint benchmark;
- model probability;
- eventual settlement label attached only after settlement.

Most importantly:

\[
\boxed{\text{Never rewrite the prediction a historical model actually made.}}
\]

That lets us compare model generations prospectively.

## Failure modes

- Promoting a challenger because training loss improved.
- Letting the challenger influence the supposedly untouched promotion set.
- Overwriting old predictions after a new model version exists.
- Changing model, features, and evaluation gate simultaneously without versioning.

## Practice

1. What is the difference between a champion and a challenger?
2. Why should old predictions remain immutable?
3. Why is a prospective prediction ledger stronger evidence than a purely retrospective backtest?

---

# 75. Expanding windows, rolling windows, and recency weighting

## Intuition

When retraining over time, we must decide how much history to keep.

### Expanding window

Use all eligible history:

\[
D_t=\{1,2,\ldots,t\}
\]

Advantage: maximum sample size.

Risk: very old regimes may dominate a changing market.

### Rolling window

Use only the most recent \(N\) observations/events:

\[
D_t=\{t-N+1,\ldots,t\}
\]

Advantage: adapts faster.

Risk: throws away potentially useful history and increases variance.

### Recency weighting

Keep history but weight older observations less:

\[
w_i=e^{-\lambda \Delta t_i}
\]

where:

- \(w_i\) = weight for observation \(i\);
- \(\lambda>0\) = decay rate;
- \(\Delta t_i\) = age of the observation.

## Tiny example

Suppose an expanding fit uses 2,000 events while a rolling fit uses the latest 500.

If the market is stable, the 2,000-event model may estimate parameters more precisely.

If the relationship changed recently, the 500-event model may adapt faster.

Neither is automatically superior.

## Project connection

If the project eventually adopts champion/challenger retraining, expanding vs rolling vs recency-weighted training should be tested as **separate frozen challenger policies**, not changed ad hoc after poor results.

## Failure modes

- Selecting the window length by repeatedly scoring the same future block.
- Assuming recent data is always better.
- Assuming all old data is always relevant.
- Ignoring effective independent-event count after shortening the window.

## Practice

1. Why does an expanding window usually reduce estimation variance?
2. Why might a rolling window handle concept drift better?
3. What new hyperparameter appears in recency weighting?

---

# 76. Checkpoint 19C lesson — typical behavior versus tails

## What happened

Checkpoint 19B's seven-minute pilot showed very tight Coinbase/Kraken timing and disagreement, but it was too short to characterize rare behavior.

Checkpoint 19C then ran a frozen 24-hour outcome-blind audit.

Canonical completed run:

`collect_kxbtcd_extended_btc_availability_20260816T010538080066Z_64fb4250`

Integrity validation passed:

- 11,804 raw records;
- 0 raw error records;
- 6 derived CSV files;
- 96,405 total derived rows across those files;
- 11,806 runtime events;
- 0 runtime errors;
- clean worktree at collection start.

Core feasibility evidence:

- 5,758 external cycles;
- 288 KXBTCD snapshots;
- 90,288 feasibility rows;
- 27 unique events;
- 4,722 unique markets;
- 25 UTC hour buckets across portions of two UTC dates;
- 100% Coinbase/Kraken/Kalshi request success;
- 100% both-source cycle availability;
- 100% structurally usable feasibility rows;
- 0 structural exclusions.

Five-minute causal lookback availability was:

\[
99.6478\%
\]

for each external source at the row level.

Typical local first-seen source ages at KXBTCD snapshots were approximately:

\[
\text{Coinbase p50}=1.297s,\quad p95=2.203s
\]

\[
\text{Kraken p50}=1.109s,\quad p95=1.985s
\]

External-cycle cross-source disagreement was:

\[
p50\approx0.727\text{ bp},\quad p95\approx2.753\text{ bp},\quad max\approx5.348\text{ bp}
\]

The receive-skew distribution was usually small:

\[
p50=156\text{ ms},\quad p95=234\text{ ms}
\]

but one observed maximum reached:

\[
9687\text{ ms}
\]

around 09:05 UTC, near the only hour with visibly reduced cycle count.

## The key statistical lesson

A short pilot can describe the **center** of a distribution while missing the **tails**.

If a latency variable is \(Z\), statistics such as:

\[
\operatorname{median}(Z)
\]

and:

\[
Q_{0.95}(Z)
\]

say something about common behavior, while:

\[
\max(Z)
\]

shows the most extreme observed value in that sample.

None of these alone defines the correct future threshold.

## A second lesson: freshness has multiple meanings

The project must distinguish at least:

1. **Transport/request availability** — did the request succeed?
2. **Local first-seen age** — how long ago did our machine receive the observation used for the KXBTCD state?
3. **Source-event/publication age** — how old is the exchange's own timestamp for the quoted level/state?
4. **Cross-source disagreement** — do independent venues currently disagree materially?

A request can succeed while an unchanged best bid/ask level carries an older source publication timestamp. Therefore:

\[
\boxed{\text{HTTP success} \neq \text{proof that market state itself is fresh}}
\]

The next source-quality design should keep these diagnostics conceptually separate.

## Evidence boundary

Checkpoint 19C is an **engineering-feasibility PASS**, not predictive evidence.

It does not establish:

- Candidate-E predictive improvement;
- a profitable strategy;
- a source-staleness threshold;
- a cross-source disagreement threshold;
- a Coinbase/Kraken consensus formula;
- E1/E2/E3 cohort sizes;
- an execution policy.

Those require later frozen decisions and fresh evidence.

## Practice

1. Why did the seven-minute pilot underestimate tail disagreement?
2. What does 100% request success fail to tell us about source-state freshness?
3. Why should a 9.687-second single maximum not automatically become the staleness threshold?
4. Why is a full-day availability PASS still not model evidence?

---

# 77. New glossary terms after Checkpoint 19C

**Ablation:** Controlled comparison that adds or removes one model component to estimate its incremental contribution.

**Champion:** Frozen model currently used as the reference live/prospective model.

**Challenger:** Newly trained candidate that must pass a promotion evaluation before replacing the champion.

**Concept drift:** Change over time in \(P(Y\mid X)\), the relationship between inputs and outcomes.

**Continual learning:** Updating or periodically retraining a model as new labeled evidence arrives over time.

**Data drift:** Change over time in the distribution \(P(X)\) of model inputs.

**Expanding window:** Retraining dataset that includes all eligible history accumulated so far.

**Learning curve:** Plot or table of model performance as training sample size increases.

**Model misspecification:** Model structure does not adequately represent the real relationship.

**Online learning:** Learning procedure that can update sequentially as new observations/labels arrive.

**Prospective prediction ledger:** Immutable record of predictions, exact model versions, inputs, timing, lineage, and later outcomes created during real future operation.

**Rolling window:** Retraining dataset restricted to a recent fixed-size history window.

**Source-event freshness:** Age implied by the source/exchange timestamp for the quoted observation or level, distinct from local receipt age.

---

# 78. Practice set G — data scaling and adaptive model systems

1. Explain why more data reduces estimation variance but may not eliminate model bias.
2. Sketch two hypothetical learning curves: one suggesting more data may help and one suggesting a structural ceiling.
3. Design an ablation sequence for market midpoint, BTC distance to strike, and five-minute BTC return.
4. Explain the difference between online learning and the champion/challenger architecture proposed for future consideration.
5. Give one example each of data drift and concept drift in KXBTCD.
6. Compare expanding-window and rolling-window retraining in terms of sample size and adaptability.
7. Explain why the exact model version must be stored with every prospective prediction.
8. Explain why Checkpoint 19C's 100% request success does not imply every exchange-level quote timestamp was always recent.
9. Explain why the 19C 9.687-second receive-skew maximum is evidence to investigate, but not sufficient by itself to choose a future fail-closed threshold.
10. State what Checkpoint 19C did and did not prove.

<!-- CHECKPOINT19D_A_HISTORICAL_MATERIALIZATION_20260817 -->
# Checkpoint 19D-A learning additions

## Data availability versus data quality

### Intuition

**Availability** asks whether data arrived. **Quality** asks whether the arrived data is fit for the intended use. A successful API response can contain an old market state.

### Tiny example

Suppose Kraken responds successfully at 12:00:10. The ask was updated at 12:00:09.8, but the bid was last updated at 11:59:50.

The request is available, but a midpoint using both sides contains one 20-second-old side.

### Formal definition

Request availability can be represented as an indicator:

`A_request = 1` if the required request and parser succeed, otherwise `0`.

This is separate from an age variable such as:

`age_source = t_decision - t_source_event`.

### Project application

19D-A keeps request success, local first-seen age, exchange/source-event age, cross-source disagreement, and lookback alignment as separate fields.

### Failure modes

- calling every HTTP 200 response "fresh";
- hiding a stale side of a two-sided book behind a newer timestamp on the other side;
- combining unrelated quality checks into one opaque flag.

### Practice

If an API returns HTTP 200 but its required source timestamp is 30 seconds old, which dimension passed and which may have failed?

---

## Timestamp semantics and conservative BBO freshness

### Intuition

Different timestamps answer different questions. Local receipt time says when our machine saw something. Exchange publication time says when the source published it.

For a midpoint, both bid and ask matter, so the older side determines the conservative freshness of the pair.

### Tiny example

Bid age = 8 seconds. Ask age = 0.5 seconds.

Conservative BBO age = 8 seconds, not 0.5 seconds.

### Equation

`age_BBO = max(age_bid, age_ask)`.

### Project application

19C previously carried one Kraken source-event timestamp derived from the newer of the two level timestamps. 19D-A re-reads raw data and measures both sides separately before any threshold is selected.

### Failure modes

- using `min(age_bid, age_ask)` and making a partly stale midpoint look fresh;
- comparing exchange clock time to local monotonic time directly;
- assuming timestamp names mean the same thing across venues.

### Practice

Bid publication age is 12 s and ask publication age is 2 s. What conservative BBO age should a fail-closed quality check use?

---

## Causal historical reconstruction

### Intuition

A historical feature is causal only if every piece of information in it existed by the original decision time.

### Tiny example

Decision time = 12:34:37. A one-minute candle for 12:34:00–12:35:00 will eventually contain trades from 12:34:38 onward. Using its final close would leak future data.

The last fully completed candle is 12:33:00–12:34:00.

### Formal rule

For decision time `T`, use a bucket `[b, b+60s)` only if:

`b + 60s <= T`.

### Project application

19D-A uses the last fully completed minute and never the incomplete current minute.

### Failure modes

- using the final close of a candle that contains the decision timestamp;
- reconstructing a feature with data downloaded later without checking original event times;
- allowing revisions or late publications to move backward in time silently.

### Practice

At 09:17:12, which one-minute bucket is the most recent fully completed bucket?

---

## Interpolation versus nearest-prior sampling

### Intuition

Interpolation estimates a value between observations. In time-series prediction, using a later observation to interpolate an earlier state can leak the future.

### Tiny example

Known prices: 10:00 = 100 and 10:02 = 102. Estimating 10:01 as 101 uses the 10:02 future observation.

### Formal distinction

Causal nearest-prior sampling requires:

`t_selected <= t_decision`.

Two-sided interpolation generally uses points on both sides of the target and is therefore not automatically causal.

### Project application

19D-A is stricter than generic nearest-prior sampling: the exact completed minute must exist. Missing exact buckets are excluded.

### Failure modes

- nearest **absolute** timestamp chooses a future point;
- carry-forward hides source outages or missing buckets;
- interpolation makes historical coverage look better than the live system could achieve.

### Practice

Why is "closest observation" an unsafe rule unless its direction in time is constrained?

---

## Live/historical feature parity

### Intuition

Training and future inference should mean the same thing. A model trained on one-minute trade closes should not silently receive live BBO midpoints under the same feature name.

### Tiny example

Historical feature = 12:00 minute close at $120,000. Live feature = current midpoint at $120,180. They are both BTC prices, but they represent different market states.

### Formal requirement

A feature contract should bind its source, transformation, time boundary, missing-data behavior, and causal timestamp semantics.

### Project application

19D-A measures historical-vs-live price gaps explicitly rather than assuming candle close equals BBO midpoint.

### Failure modes

- training/serving skew;
- hidden source substitution;
- changing timing semantics without versioning the model input.

### Practice

Name three parts of a feature definition that must stay fixed between historical training and prospective inference.

---

## Source disagreement and deterministic consensus

### Intuition

Two reputable venues can quote slightly different BTC prices. Their disagreement is first a data-quality measurement, not automatically a predictive feature.

### Tiny example

Coinbase = 120,000. Kraken = 120,012. Midpoint denominator = 120,006. The difference is 12 / 120,006, about 1 basis point.

### Equation

`D_bps = |S_C - S_K| / ((S_C + S_K)/2) * 10000`.

### Project application

19D-A measures this distribution for historically reproducible completed-minute prices. It does not yet choose whether Candidate E uses one source or an arithmetic consensus.

### Failure modes

- choosing the source that happened to improve outcomes;
- learning source weights on a small exposed cohort;
- setting a disagreement cutoff from model performance instead of source-quality evidence.

### Practice

Why is an equal-weight consensus simpler to validate than learned Coinbase/Kraken weights?

---

## Distribution tails and percentile-based quality rules

### Intuition

A median describes a typical observation, but fail-closed systems also care about rare bad cases.

### Tiny example

Ages: 1, 1, 1, 1, 20 seconds. Median = 1 second, but the 20-second tail matters for a staleness rule.

### Formal idea

The `p95` percentile is a value at or below which approximately 95% of observations fall. `max` records the most extreme observed value but can be unstable in small samples.

### Project application

19D-A records p50, p90, p95, p99, and max for quality diagnostics. A later freeze can use these outcome-blind tails without consulting Candidate-E scores.

### Failure modes

- using only averages;
- treating one observed maximum as a universal physical limit;
- choosing a percentile after seeing which threshold makes the model look best.

### Practice

Why might p95 and p99 both be useful when evaluating source freshness?

---

## Outcome-blind threshold selection

### Intuition

A data-quality threshold should answer "when is the source trustworthy enough?" rather than "which cutoff makes my prediction score improve?"

### Tiny example

Suppose disagreement thresholds of 2, 5, and 10 bp are possible. Trying all three against settlement outcomes and keeping the best model score makes the threshold a tuned model hyperparameter.

### Formal boundary

Let `Q` be source-quality evidence and `Y` settlement outcomes. In 19D, threshold selection must be a function of `Q` only:

`threshold = f(Q)`

not:

`threshold = f(Q, Y)`.

### Project application

19D-A collects only `Q`. Outcomes remain inaccessible until source/materialization rules and the later Candidate-E experiment are frozen.

### Failure modes

- calling an outcome-tuned cutoff a "data cleaning" rule;
- repeatedly changing missing-data rules after seeing model scores;
- allowing E1/E2/E3 sample sizes to depend on whether results look favorable.

### Practice

If a 3 bp disagreement cutoff gives the best log loss on E1 outcomes, why can it no longer be described as an outcome-blind source-quality threshold?

<!-- CHECKPOINT19D_A_RESULTS_20260817 -->
## Learning note — why a successful API request is not necessarily a fresh market state

Checkpoint 19D-A reinforces three separate notions of freshness:

1. **Transport/local receive freshness** — how recently our program received a
   successful response.
2. **Source-event freshness** — how old the exchange event or quoted level is.
3. **Historical reconstructibility** — whether a causally valid observation
   exists for the exact historical bucket required by the research contract.

Kraken illustrated the distinction clearly. Local-first-seen age was usually
about a second, yet the conservative age of the older BBO side was often tens
of seconds and occasionally much older. A fast HTTP response therefore cannot
be used as proof that both quoted sides are current.

The one historical 09:09–09:10 UTC hole illustrates a different issue:
Kraken's API responded successfully but reported zero trades for the exact
minute. Under an exact-minute feature contract, that state is unavailable.
Carrying an older price forward would silently change the feature definition
and can make historical coverage look better than the real data supports.

Cross-source disagreement was generally small in this audit, but the observed
distribution is descriptive evidence, not a predictive or trading threshold.
Thresholds belong in the predeclared 19D-B source-quality freeze.

<!-- CHECKPOINT19D_B_SOURCE_POLICY_20260817 -->
## Learning note — a verifier can block a state without becoming part of the feature

A **primary source** supplies the numerical value a model may eventually use.
A **verifier source** independently checks whether that state looks trustworthy.

Checkpoint 19D-B uses Coinbase as the primary and Kraken as the verifier. If
Coinbase says BTC is 63,000 and Kraken says roughly the same thing with a fresh
enough book, the Coinbase value may be eligible. If Kraken is stale or differs
by more than the frozen 5 bp limit, the whole state is rejected. We do not
average Kraken into the feature just because it is available.

This matters because averaging is itself a modeling choice. If one venue can
contain an old quoted side, averaging can silently contaminate a clean primary
measurement. A verifier-only design is simpler: it changes the decision from
"use this number or not" rather than changing the number.

The evidence-tier calendar rules are also source-quality rules rather than
profit rules. Requiring at least a week for E1/E2 and two weeks for E3 forces
the experiment to see multiple hours and days instead of stopping after a
convenient short streak. Outcomes are not used to decide when those minimums
have been met.

<!-- CHECKPOINT19E_CANDIDATE_E_PREDECLARATION_20260817 -->
## Why Candidate E uses 10,000-times log ratios

A natural-log price ratio is convenient because multiplicative price moves become additive:

`ln(S/K)` measures relative spot-versus-strike distance and `ln(S_t/S_t-5m)` measures a five-minute return.

These values are small in raw decimal form. Multiplying by 10,000 expresses them in approximately basis-point units. A roughly +0.10% move becomes about +10 log-bp.

This does not create predictive information. In an unregularized logistic model, changing the feature by a fixed scale simply changes the reciprocal scale of its coefficient. Candidate E freezes the scale before E1 outcomes anyway because changing units after looking at results would weaken reproducibility, and feature scaling would matter materially if a coefficient penalty were later introduced.

Candidate E also uses Kalshi's market logit as a fixed offset. That means it asks whether independent BTC state can justify an additive log-odds correction rather than relearning Kalshi's entire probability mapping again.

<!-- CHECKPOINT19F_HISTORICAL_EVIDENCE_AMENDMENT_20260817 -->
## Historical does not mean exposed: train, validation, test, and reserve

A dataset can have happened in the past and still be statistically untouched if its outcomes have not influenced the current model/design decision. The key concept is **information exposure**, not calendar age.

- Training data is allowed to influence fitted parameters and candidate selection; after use it is exposed.
- Validation data stays sealed until the training-stage model/specification is fixed enough to evaluate. Once validation results influence advancement, validation is exposed.
- Locked test data stays sealed until the final model is frozen and is opened once. If the model fails, that test becomes exposed and cannot be reused as an untouched test for a successor.
- Reserve data is held outside the current experiment so a failed candidate does not consume the project's entire future evidence supply.

For Candidate E, H1/H2/H3 target 1,500/750/750 eligible events while protecting at least 5,000 outcome-unopened events. This allocation reflects the model's low parameter count and the project's greater need for generalization evidence after earlier failures.

<!-- CHECKPOINT19G_HISTORICAL_MATERIALIZATION_20260817 -->
## Historical pre-outcome materialization: source fields versus statistical labels

A data source can return more information than a research step is allowed to use. Historical market metadata is a good example: one response may contain both structural fields needed for reconstruction and settlement fields that would reveal the label.

A **raw-first archive** preserves the original source response for auditability. A separate **research projection** then keeps only an explicit allow-list of fields permitted for the current experiment. The important statistical protection is that forbidden label fields cannot affect selection, branching, features, or model decisions. A useful regression test changes only the forbidden source value and proves that the projected research data stay exactly the same.

Chunking is an engineering control rather than a statistical trick. Each bounded chunk gets its own manifest, so a later network failure does not require treating one giant collection as an indivisible unit. The final statistical cohort is still defined by one frozen chronological rule, not by which chunks happened to succeed first.

<!-- CHECKPOINT19HB_COINBASE_PRIMARY_20260817 -->
## Basis points and blocking verifier design

### Basis points
A **basis point (bp)** is 0.01 percentage points. Therefore 100 bp = 1%, 10 bp = 0.10%, and 5 bp = 0.05%. If BTC is $100,000, a 5 bp price difference is about $50.

Basis points are useful for expressing small relative price differences because saying "5 bp" is less ambiguous than saying "0.05 percent" in market microstructure work.

### Blocking verifier vs diagnostic monitor
A second data source can be used in two different ways. A **blocking verifier** can reject the primary source when the two disagree. A **diagnostic monitor** records disagreement but does not stop the model. Blocking verification can improve fault detection, but it also creates another availability dependency and can selectively remove volatile or venue-dislocated states. A diagnostic monitor preserves observability without automatically changing the research sample.

In Candidate E, Coinbase now supplies the required BTC state while Kraken is nonblocking diagnostic evidence. This keeps the statistical question focused on whether Coinbase BTC state adds information beyond Kalshi while retaining the option to monitor cross-venue anomalies separately.

<!-- CHECKPOINT20C_CANDIDATE_E_H2_PREPARATION_20260817 -->
# Checkpoint 20C lesson — selection, refit, and validation are different jobs

## Intuition

H1 did two jobs: it estimated temporary fold coefficients and used future-like H1 blocks to choose between the two predeclared Candidate-E specifications. Once Distance won that model-selection contest, those fold coefficients were not the final coefficient.

Checkpoint 20C now uses **all H1 evidence** to estimate one coefficient for the already-selected Distance formula. H2 then judges that fixed coefficient without changing it.

## Tiny example

Suppose rolling H1 folds estimate distance coefficients 0.008, 0.010, and 0.011. Those are evidence that the relationship is reasonably stable, but they correspond to different training windows.

After Distance is selected, we fit one coefficient on all H1, say beta = 0.0105. H2 receives exactly that 0.0105. If H2 results tempt us to change it to 0.009, H2 would stop being untouched validation.

## Formal distinction

Model selection:
`choose specification using development evidence`

Final H1 parameter fit:
`beta_H1 = argmin_beta L_H1(beta)` for the already-selected specification

Validation:
`evaluate beta_H1 on H2 without optimizing beta on H2`

## Project application

Candidate E selected the one-feature Distance model on H1. Checkpoint 20C freezes its all-H1 `beta_distance = 0.012310034918384302` under model fingerprint `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`. H2 has 750 untouched events in five chronological 150-event blocks.

## Failure modes

- fitting beta on H2 before scoring it;
- trying momentum-only on H2 because H1 made it interesting;
- changing the gate after seeing H2;
- treating a strong H2 forecasting result as proof of profitable trading.

## Practice

1. Why are H1 fold coefficients not the final coefficient?
2. If H2 is used to adjust beta, what evidence role has H2 become?
3. Why can the selected specification be refit on all H1 without contaminating H2?
4. What must happen before H3 can be opened?

<!-- CHECKPOINT21A_POST_H3_LIFECYCLE_20260817 -->
# Checkpoint 21A lesson — model confirmation, strategy development, and live shadow answer different questions

## Intuition

A forecasting model can be good without a trading strategy being profitable.
A historical strategy can look profitable after we tune it without that profit being fresh evidence.
A live shadow system can test the frozen model and frozen strategy together without sending a real order.

These are three different scientific questions:

1. **Forecasting:** are the model probabilities better than the market benchmark?
2. **Decision economics:** can those probabilities support a rule that survives executable prices and costs?
3. **Prospective operation:** does the frozen rule still work when real future feeds, timing, depth, and missed fills are encountered?

## Tiny example

Suppose the model says:

`p_model = 0.67`

and the executable YES ask is:

`ask = 0.58`

The naive probability-price difference is:

`0.67 - 0.58 = 0.09`

or 9 percentage points.

That still does not tell us to trade. A future strategy may require buffers for:

- fees;
- spread/slippage;
- model uncertainty;
- latency;
- minimum desired edge.

If those combined buffers are 0.07, the remaining estimated margin is only:

`0.09 - 0.07 = 0.02`.

If we choose the 0.07 buffer by repeatedly testing many values on the same historical events, that historical P&L becomes **strategy-development evidence**. A later frozen live-shadow cohort is needed for a stronger economic claim.

## Expanding-window confirmation

Checkpoint 21 uses the same champion specification repeatedly:

`fit H1+H2+H3 -> score C1`

`fit H1+H2+H3+C1 -> score C2`

`fit H1+H2+H3+C1+C2 -> score C3`

The important order is:

`fit on exposed past -> freeze -> score fresh future block -> only then add that block to training`.

This is sometimes called prequential or sequential out-of-sample evaluation.

## Why the strict reserve floor is 4,500

The current strict tail is about 6,231 events. C1+C2+C3 need 1,500 **eligible** events, but the frozen eligibility scanner may inspect some chronological candidates that fail source/quote requirements.

An inspected-but-ineligible event can remain outcome-unopened while still no longer belonging to the project's strict never-materialized tail.

Therefore reserve arithmetic is not simply:

`6231 - 1500 = 4731`.

The protocol instead says:

> Stop before strict untouched history falls below 4,500 events.

That preserves more than 72% of the current strict tail for future challenger evidence while allowing bounded eligibility exclusions.

## Full live shadow versus real execution

A future live shadow system should behave like the real research bot until the final action boundary:

`live feeds -> model -> strategy -> MOCK order intent -> simulated fill -> mock position/P&L`.

The word **MOCK** is essential. No order is transmitted to Kalshi.

A realistic shadow fill should use:

- live bid/ask;
- available depth;
- fees;
- latency;
- partial fills;
- missed fills;
- stale-feed and sequence-gap rules.

The current risk policy does not yet authorize such a live paper/shadow broker. That authorization must be changed explicitly later; it is not implied by a model PASS.

## Project-specific lesson

Candidate E passed H1, H2, and H3. Checkpoint 21 deliberately spends only a bounded part of the remaining historical reserve on C1-C3 before moving to strategy research.

If C1-C3 pass, the project will first develop the betting/decision policy on exposed evidence. Only after that policy and the execution simulator are frozen should a prospective full live shadow phase judge both forecasting and simulated economics.

This preserves the distinction:

`good probabilities != proven profitable strategy != permission to trade`.

## Failure modes

- tuning a strategy on C1-C3 and then calling the same C1-C3 P&L untouched;
- consuming the entire reserve just to make a one-parameter coefficient slightly more precise;
- using midpoint as if it were an executable price;
- assuming a touched quote guarantees a fill;
- changing the champion halfway through the prospective cohort;
- letting a historical strategy result silently authorize live paper or real execution.

## Practice

1. Why can C1 be added to training only after C1 is scored?
2. Why is historical strategy P&L on H1/H2/H3/C1/C2/C3 not a fresh profitability test if those data helped choose the strategy?
3. What is the difference between a strict untouched reserve event and an outcome-unopened event whose source metadata has already been materialized?
4. Why should live shadow fills use the bid/ask and depth rather than midpoint?
5. If the forecasting layer passes but the simulated strategy loses after costs, what conclusion should the project make?
6. Why does a successful full live shadow still not automatically authorize demo or real-money orders?

<!-- CHECKPOINT21B_A_C1_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
# Checkpoint 21B-A learning note — freeze the mechanism before touching the evidence

C1 is valuable because it is still fresh relative to the champion. That value would be weakened if we first inspected C1 and only afterward decided how the entering champion, selection order, or block boundaries should work. 21B-A therefore freezes the mechanism first.

A second idea is **candidate runway**. The 6,231-event strict tail is not the same as 6,231 guaranteed eligible C1/C2/C3 events. Ineligible candidates still consume chronological runway when inspected. With a 4,500-candidate hard floor, the full C1-C3 path may inspect at most 1,731 strict-tail identities. The implementation counts inspected candidates, not only accepted eligible events.

Finally, chunk size is an engineering bound rather than a statistical block. The collector may be asked to inspect up to 100 candidates, but it stops early when the 500th C1-eligible event is reached so it does not accidentally expose the start of C2.

<!-- CHECKPOINT21B_B_CHAMPION_R0_20260818 -->
## Champion-R0: refitting versus redesigning

A **refit** keeps the mathematical model fixed and only re-estimates its
coefficient using a larger accepted evidence set. Here, the model remained

`logit(p) = logit(q_market) + beta_distance * d_BTC`

and only `beta_distance` was re-estimated after H3 became legitimately exposed.

The earlier H1+H2 value was `0.013805016135330063`; the H1+H2+H3 Champion-R0
value is `0.014447239079794087`.

That coefficient movement is not itself evidence of improvement or failure.
The fresh test is C1, which remains untouched. The scientific protection comes
from freezing Champion-R0 **before** materializing or opening C1.

Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`.

<!-- CHECKPOINT21B_C_C1_PREOUTCOME_FREEZE_20260818 -->
## Why C1 is frozen before looking at outcomes

C1 is useful as fresh evidence only if its identities and scoring rules are
fixed before anyone knows whether the champion wins or loses.

The scanner had to inspect 506 chronological candidate identities to
obtain exactly 500 eligible events. The six rejected identities were excluded
by rules frozen before their outcomes were opened, not because of how they
settled.

The result is five chronological 100-event blocks with validation fingerprint
`76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`.

There are still 5725 never-materialized historical events left. The protocol's
hard floor is 4500, so C1 leaves a 1225-event safety buffer for possible
C2/C3 confirmation.

At this point C1 says **nothing yet about model performance**. Outcomes remain
sealed. The next protection is to freeze the evaluator itself before opening
those outcomes.

<!-- CHECKPOINT21C_C1_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Why freeze the evaluator before opening C1

Freezing the data is not enough. If scoring code, outcome identity rules, or
failure/retry behavior could change after labels are seen, the test could still
be adapted to its own answers.

Checkpoint 21C therefore freezes the exact evaluator bytes under fingerprint
`2719cef9c5180014f3230c724be76bf959d71882a2f0c84e386a5169392773af` before C1 is opened. The future runner can request only the frozen
2491 markets, applies the already-fixed Champion-R0 model, and uses the
already-fixed C1 gate.

The full 500-event C1 cohort is declared exposed before the first outcome
request. That rule is intentionally conservative: if the network dies halfway
through, the unfinished portion cannot later be presented as a brand-new fresh
C1 test. The system may only resume the same attempt and preserve the same
journaled labels.

C1 remains outcome-sealed at this synchronization point.

<!-- CHECKPOINT21D_C1_RESULT_20260818 -->
## What the C1 PASS tells us

C1 was the first fresh 500-event confirmation block after the H1/H2/H3 model
development program. Its identities, inputs, model coefficient, and scoring
rules were all frozen before its outcomes were opened.

Raw Kalshi event-equal log loss was
`0.17078339823721184`. The fixed Candidate-E champion's
log loss was `0.053151764629610743`.

That is a reduction of approximately
`68.88%`.

Raw Brier was `0.039207186965517601` versus
`0.01515132922607266` for Candidate E, an improvement
of approximately `61.36%`.

More importantly than the pooled averages, Candidate E won all five
chronological 100-event blocks, including the newest B4. That reduces the
chance that the pooled result came only from one especially favorable period.

C1 is now exposed. We cannot adjust the model and call C1 fresh again.
The frozen protocol therefore moves forward: refit the unchanged model using
the newly exposed C1 evidence, freeze it, and evaluate it only on a later
untouched C2 block.

None of these forecast scores include fees, bid-ask spread, depth, latency,
partial fills, missed fills, or position-management economics. Forecasting
quality and trading profitability remain separate questions.

<!-- CHECKPOINT21E_A_C2_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Why the reserve boundary does not reset after C1

Before C1, the strict never-materialized tail began at queue index 3200 and the
hard maximum end-exclusive index for all C1/C2/C3 materialization was 4931.

C1 inspected 506 identities, so C2 starts at 3706. The hard maximum is still
4931—not 3706 plus a new allowance. That leaves only 1,225 candidate identities
for C2 and C3 combined.

This matters because eligibility is not guaranteed. A 500-event confirmation
block can require more than 500 inspected identities. The collector therefore
checks the absolute reserve boundary on every event and fails closed rather than
borrowing from the protected 4,500-event tail.

The model transition is also kept separate from reserve access: first freeze
implementation, then fit/freeze Champion-R1 on already-exposed evidence, and
only afterward inspect C2.

<!-- CHECKPOINT21E_B_CHAMPION_R1_20260818 -->
## Champion-R1 is a refit, not another test

After C1 passed, its 500 events became permanently exposed. The frozen lifecycle
therefore allows those events to join the training evidence for the model that
will enter C2.

Champion-R1 uses exactly the same one-parameter formula. Only the estimate of
`beta_distance` changes:

- Champion-R0: `0.014447239079794087`
- Champion-R1: `0.014529004270980883`

No feature, objective, optimizer, regularization rule, or hyperparameter was
changed.

This does not tell us whether Champion-R1 is better than Champion-R0. C1 can no
longer answer that question because C1 influenced the new coefficient.

The next genuinely fresh evidence is C2. That is why Champion-R1 must be frozen
before C2 identities are materialized and long before C2 outcomes are opened.

<!-- CHECKPOINT21E_C_C2_PREOUTCOME_FREEZE_20260818 -->
## Why C2 still tells us nothing about performance yet

C2 now contains exactly 500 eligible events, but their outcomes remain sealed.

The materializer inspected 516 chronological candidate
identities to obtain those 500 eligible events. The 16
excluded identities were rejected using rules fixed before their outcomes were
known.

Champion-R1 was also frozen before C2 was materialized. That prevents C2 from
changing the model that will eventually be tested on it.

The strict historical queue moved from index 3706 to 4222, leaving
5209 never-materialized events. Since the protected floor is
4500, only 709 candidate identities remain available
for a possible C3 stage.

At this point C2 is equivalent to a sealed exam. We have selected the questions
and frozen the grading rule, but we have not looked at the answer key.

<!-- CHECKPOINT21F_A_C2_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Why we freeze the evaluator before opening C2

Freezing the model before C2 is not enough. We also need to freeze the way C2
will be scored.

Otherwise, after seeing outcomes, we could accidentally choose a different
metric, block definition, exclusion rule, or scoring convention that makes the
result look better.

The frozen evaluator now knows exactly:

- which 500 events belong to C2;
- which 14,007 probability rows will be scored;
- which 2,441 finalized market outcomes may be requested;
- the exact Champion-R1 coefficient;
- the exact log-loss/Brier calculations;
- the five chronological 100-event blocks;
- every condition required for PASS.

No C2 answer has been opened yet. This is the last procedural freeze before the
one-time C2 test.

<!-- CHECKPOINT21F_B_C2_RESULT_20260818 -->
## What the C2 PASS adds to the evidence

C2 was a second fresh 500-event confirmation block. Champion-R1, the C2
identities, the input rows, the evaluator, and the scoring rules were all
frozen before C2 outcomes were opened.

Raw Kalshi event-equal log loss was `0.16763671430199342`.
The fixed Candidate-E model's log loss was `0.05064447819587261`.

That is a reduction of approximately `69.79%`.

Raw Brier was `0.03957031952485842` versus `0.015191801215127898` for
Candidate E, a reduction of approximately `61.61%`.

The result was not driven by one lucky period. Candidate E beat the raw
midpoint in every chronological 100-event block:

- B0: `+0.13947804627980334`
- B1: `+0.12660541888180846`
- B2: `+0.12982186853271965`
- B3: `+0.084476671344659388`
- B4: `+0.10457917549161326`

The median event-level log-loss improvement was
`+0.13555827126142961`.

C1 and C2 therefore provide two separate fresh 500-event confirmations with
very similar low Candidate-E log loss. C2 is now exposed, so it cannot be used
again as fresh evidence after influencing a refit.

The frozen lifecycle next adds C2 to the expanding fit set, producing a
4,000-event / 109,971-row exposed pool. The model specification must remain
unchanged and the resulting Champion-R2 must be frozen before C3 is touched.

None of these forecasting metrics include executable entry prices, spread,
depth, latency, partial fills, missed fills, fees, exit mechanics, or position
economics. Those remain separate later research questions.

<!-- CHECKPOINT21G_A_C3_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Why C3 has only 709 candidate identities of runway

The protected historical reserve is governed by one absolute queue boundary,
not a new budget at every confirmation stage.

After C2, the next untouched queue index is 4222. The protocol says the
confirmation process may never inspect index 4931 or later.

So the remaining C3 candidate budget is:

`4931 - 4222 = 709`

C3 still needs 500 eligible events. That leaves room for at most 209 ineligible
candidate identities.

If exclusions are unusually frequent and the 500th eligible event cannot be
reached before index 4931, the correct result is to stop. We do not consume the
protected 4,500-event tail just to force C3 to reach its target.

Before any of those 709 identities are touched, Champion-R2 must first be fit
on the 4,000 already exposed H1+H2+H3+C1+C2 events and frozen separately.
That sequencing prevents C3 from influencing the model it is meant to test.

<!-- CHECKPOINT21G_B_CHAMPION_R2_20260818 -->
## What Champion-R2 means

Champion-R2 is not a new test result.

C2 has already been scored, so its outcomes are now allowed to join H1, H2,
H3, and C1 in the expanding fit set. That creates 4,000 exposed events and
109,971 probability rows.

The exact same one-parameter model was then refit:

`logit(p) = logit(q_market) + beta_distance * d_BTC`

The coefficient changed from Champion-R1's `0.014529004270980883` to
Champion-R2's `0.014501283346050064`. That is a very small change, which indicates
the fitted relationship is currently fairly stable as more exposed data are
added.

The new fit objective is `0.053511817851523945`. Because that value is measured
on data used to fit the parameter, it should not be interpreted as another
fresh validation score.

The next fresh evidence will be C3. Champion-R2 must therefore be frozen before
C3 identities are touched.

C3 begins at queue index 4222 and has only 709 candidate identities available
before the protected 4,500-event reserve floor is reached.

<!-- CHECKPOINT21G_C_C3_PREOUTCOME_20260818 -->
## Why C3 needed 533 identities for 500 events

C3's target was not simply the next 500 names in the historical queue.

Every candidate identity first had to satisfy the already-frozen,
outcome-blind source, timing, market-structure, and feature-availability
requirements. An identity that failed those requirements was excluded without
using its settlement outcome.

The first 400 C3 events happened to be eligible consecutively. In the next
133 identities, 100 were eligible and 33 were excluded. Therefore the final
cohort required:

`533 inspected - 33 excluded = 500 eligible`

This is the correct behavior. Allowing outcomes to influence which identities
were kept would contaminate the test.

The resulting cohort consumes queue indices `[4222, 4755)` and leaves 4,676
untouched identities. Since the protocol required at least 4,500 to remain,
the final buffer is:

`4676 - 4500 = 176`

C3 is still unscored. Freezing its features and membership before labels are
opened preserves its role as fresh historical confirmation evidence.

<!-- CHECKPOINT21H_A_C3_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## Why the C3 evaluator is frozen separately

C3 is the final fresh historical confirmation block. The scoring code itself
therefore has to be fixed before labels are opened.

The evaluator knows exactly which 2,470 market outcomes it may
request and which 4,000 earlier events it must reject. It also
knows the exact Champion-R2 coefficient and PASS gate in advance.

Before the first network request, the runner writes a receipt saying the full
C3 cohort is permanently exposed. That prevents an interrupted or unfavorable
partial run from being discarded and restarted as if C3 were still fresh.

The remaining 4,676 historical identities are outside
this evaluator. They cannot be used to repair a C3 result.

Checkpoint 21H-A itself does not test forecast quality because it opens zero
outcomes. It only makes the later test auditable and one-time.

<!-- CHECKPOINT21H_B_C3_RESULT_20260818 -->
## What the C3 PASS means

C3 was the last fresh historical confirmation set in the predeclared
sequence.

Champion-R2's event-equal log loss was about `0.02372`, compared with
about `0.12097` for the raw market midpoint. Because lower log loss is
better, the frozen model improved the primary metric by about `0.09726`.

The result was also consistent across time: all five chronological
100-event blocks favored the model, including the newest block.

That is strong historical evidence that the independent BTC-distance
signal generalized beyond the evidence used to fit Champion-R2.

It does **not** mean a trade at any quoted price is profitable. Forecast
quality and execution economics are separate questions.

C3 is now exposed forever. The next final 4,500-event fit may use C3
because it is no longer being treated as a test set. That fit produces
the final historical parameter estimate; it does not create another
independent validation result.

The remaining 4,676 historical identities stay untouched and cannot be
used to repair or reinterpret C3.

<!-- CHECKPOINT21I_A_FINAL_FIT_IMPLEMENTATION_FREEZE_20260818 -->
## Why we refit after the final historical test

A validation set should stay untouched while it is being used to judge a
model. C3 has now completed that job and is permanently exposed.

That means C3 can be included in a final parameter estimate without changing
the already-recorded C3 result. The final fit uses all 4,500 exposed events so
the one distance coefficient is estimated from the largest accepted historical
sample.

This is **not another test**. There is no new PASS/FAIL claim from the final
fit itself. C3 remains the last fresh historical confirmation.

The remaining 4,676 historical identities are still kept outside this fit.

<!-- CHECKPOINT21I_B_CHAMPION_FINAL_20260818 -->
## Champion-Final

Champion-Final is the final historical parameter estimate after the
validation sequence finished.

The coefficient is:

`beta_distance = 0.014939489324405949`

Champion-R2 used `0.014501283346050064`, so adding the now-exposed C3
evidence increased the fitted coefficient by about 3.02%.

That change does not mean the model became 3.02% more profitable or
3.02% more accurate. The coefficient is a log-odds sensitivity
parameter, not a return percentage.

The important distinction is:

- C3 supplied fresh validation evidence before it was opened.
- Champion-Final uses C3 after it became exposed.
- therefore Champion-Final is a better-informed parameter estimate,
  but not another independent test.

The next research question is whether the available historical data is
rich enough to evaluate executable trading economics realistically.

<!-- CHECKPOINT21N_A_QUOTED_ENTRY_HOLD_LEARNING -->
## Checkpoint 21N-A lesson — forecasting edge and entry policy are different problems

Candidate E answers a forecasting question: what is the probability that a KXBTCD contract settles YES?

A strategy must answer a separate economic question: is the contract cheap enough, after costs and uncertainty, to justify acting on that probability?

For a quoted YES purchase:

`net quoted edge = Candidate-E YES probability - YES ask - standard fee`

For NO, use `1 - Candidate-E probability` and the quoted NO purchase price `1 - YES bid`.

A feature can be useful for execution or trade selection even if it does not improve settlement probability. Conversely, a statistically better probability model is not automatically tradable.

The 21N-A baseline intentionally avoids another ML layer. It first tests whether a simple deterministic mapping from Candidate E to ENTER/ABSTAIN is economically interesting.

Historical displayed quotes are useful screening evidence, but they do not reconstruct historical depth, queue position, latency, partial fills, or missed fills. Therefore a positive quoted-entry result is a reason to perform prospective execution-aware validation, not a claim of executable profit.

<!-- CHECKPOINT21N_B_LEARNING_GUIDE_20260830 -->
## Strategy research lesson — edge frequency is not economic validation

The 21N-A audit found that Candidate E often disagreed with displayed KXBTCD purchase
prices by enough to produce positive model-implied post-fee edge. That establishes
opportunity frequency, not profitability.

A historical economic test needs a frozen trade definition and a metric that includes
the cost of abstaining. For this reason, Strategy-v1 uses:

`mean net P&L per event`

with no-trade events contributing zero.

`mean P&L per trade` is still useful, but by itself it can make a very selective
strategy look stronger than the overall opportunity process really is.

The +1-cent entry-price stress asks a robustness question:

> Would the historical economics remain positive if each selected purchase were one
> cent worse than the displayed quote?

It is not an estimate that actual slippage equals one cent.

Chronological block gates matter because a pooled average can hide a strategy that
worked only in one historical regime. Requiring 4/5 positive blocks, the newest block,
and H3 positivity makes the strategy demonstrate broader historical stability before
C1+C2 confirmation is opened.

Even a PASS remains quoted-entry historical evidence, not proof of fillability or
future profitability. Prospective depth, latency, missed-fill, partial-fill, and queue
evidence is still required later.

<!-- CHECKPOINT21N_C_LEARNING_20260830 -->
## Lesson from Checkpoint 21N-C — pooled profit is not enough

Candidate E can be a strong probability forecaster without every downstream betting rule being robust. The 3c policy made money overall and under a +1c adverse-price stress, yet it lost in the newest chronological block and in H3. That means the pooled gain depended too much on earlier regimes.

This is why the strategy gate required chronology and newest-regime checks in addition to total P&L. The gate prevented a positive aggregate backtest from being mistaken for stable trading evidence.

Another important lesson is that win rate is not the objective. Binary contracts can show a high win rate and still lose money when losing positions are expensive enough. P&L after price and fees is the economic target.

<!-- CHECKPOINT21N_D_FAILURE_ANALYSIS_DESIGN_20260830 -->
## Learning note — forecast edge can fail through calibration, price, or tail losses

After a forecasting model disagrees with a market, a trade can still fail for
different reasons. 21N-D separates three useful questions:

1. **Calibration:** did the selected side win less often than the model's
   probability implied?
2. **Economics:** did later trades require paying higher prices or more fee
   relative to their settlement payoff?
3. **Tail risk:** did a few large losses erase many smaller wins?

The analysis is diagnostic rather than prescriptive. Finding that a subgroup
performed better does not make that subgroup a validated trading rule. A new
rule must be frozen and tested separately.

<!-- CHECKPOINT21N_E_FAILURE_RESULT_AND_SUCCESSOR_DIRECTION_20260830 -->
## Learning note — expected-return entry models often reduce back to probability

For a binary contract held to settlement, `E[P&L] = p_side - purchase_price - fee`. Price and fee are known at entry, so the uncertain term is still settlement probability/reliability. A learned expected-P&L entry model can therefore become another probability model.

A simpler benchmark is to keep the validated probability model fixed and require its apparent edge to survive a predeclared uncertainty/reliability haircut. A later learned meta-model must beat that simpler benchmark.

<!-- CHECKPOINT21N_F_RELIABILITY_SHRINKAGE_DESIGN_20260830 -->
## Learning note — shrinkage is a trust adjustment, not a new forecast model

If Candidate E says 90% and the market midpoint says 80%, alpha=0.5 behaves as
though only half of the disagreement is dependable: 85%.

This does **not** refit Candidate E and does not assert that 85% is the true
probability. It is a conservative decision-layer transformation.

A flat 2c or 3c haircut would mostly repeat threshold tuning. Shrinking the
model-market disagreement instead tests the specific hypothesis raised by H3/B4:
Candidate E's incremental confidence may be less reliable than its point
probability suggests.

We first ask whether this transformation materially changes decisions at all.
Only then is another outcome-aware economic test worth considering.

<!-- CHECKPOINT21N_G_SHRINKAGE_ECONOMICS_20260831 -->
## Learning note — sample eligibility comes before profitability

Alpha .25 changed almost every Strategy-v1 decision, but it left only 15 trades.
That is not enough evidence to estimate a stable economic mean, so the correct
scientific response is **not to look at its P&L**.

Alpha .50 and .75 have materially different opportunity sets and substantially
more observations. They can now be compared under one frozen economic protocol.

This prevents a common backtest error: inspecting many tiny strategy variants,
then promoting whichever small sample happened to look best.

<!-- CHECKPOINT21N_H_CONDITIONAL_ALPHA_ARCHITECTURE_20260831 -->
## Learning note — global shrinkage versus conditional reliability

A global alpha asks one question for every state: "what fraction of Candidate
E's disagreement with Kalshi should we trust?"

Conditional alpha asks a more specific question: "given this state, how much of
that disagreement should we trust?"

Constraining alpha to (0,1) keeps the adjusted probability between the market
and Candidate E. This is more conservative than an unrestricted probability
residual.

The key scientific protection is that exposed failures cannot simply become
hardcoded rules. The next model's exact features and training protocol must be
frozen before it is fit.

<!-- CHECKPOINT21N_I_CONDITIONAL_ALPHA_EXACT_PREDECLARATION_20260831 -->
## Learning note — why alpha starts at .50 but is not fixed at .50

The reliability model learns `alpha = sigmoid(gamma_0 + gamma^T X)`.
Initializing every gamma at zero makes the initial alpha exactly .50. This gives
a deterministic nested reference, not a rule that the learned model must stay at
.50.

After fitting, different causal states can receive different alphas because the
intercept and four feature slopes are learned jointly.

For a learned model, development economics must be out-of-fold. Scoring a model
on the same events used to fit its reliability coefficients would make economic
results look more convincing than true chronological generalization warrants.

<!-- CHECKPOINT21N_J_A_CONDITIONAL_ALPHA_IMPLEMENTATION_20260831 -->
## Learning note — freeze code before rerunning history

A predeclaration says what an experiment means mathematically. An implementation
freeze says exactly how the computer will carry out that meaning.

For conditional alpha, we also reuse the same old causal state rows instead of
constructing new ones. That matters because otherwise a performance change could
come from different timestamps or missing-data rules rather than from the new
reliability model.

21N-J-A therefore tests code only. 21N-J-B may later create the outcome-blind
feature table. Outcome fitting comes after both are frozen.

<!-- CHECKPOINT21N_J_B_CONDITIONAL_ALPHA_PREPARATION_20260831 -->
## Why 21N-J-B freezes rows before fitting

A model comparison is cleaner when the competing model uses the same historical
states rather than silently changing timestamps or missing-data rules.

21N-J-B therefore projects the four conditional-alpha features from the already
frozen 21M state universe and independently rematerializes them before any label
is attached. This separates two questions:

1. Did we construct the intended inputs reproducibly?
2. Does the model later improve proper scoring and economic gates?

Only question 1 was answered here. The answer was PASS. Question 2 remains
unanswered until a separately frozen development evaluator is run.

<!-- CHECKPOINT21N_K_CONDITIONAL_ALPHA_DEVELOPMENT_EVALUATOR_20260831 -->
## Why probability is gated before conditional-alpha P&L

The predeclaration requires both forecasting-quality and economic gates. If the
model already fails the required probability gate, it cannot advance regardless
of its historical quoted P&L.

Therefore 21N-K freezes a conservative sequence: test the probability requirement
first and only inspect new conditional-alpha economics if probability passes.
This reduces unnecessary exposure to outcome-derived trading diagnostics and
limits post-hoc temptation without weakening any advancement requirement.

<!-- CHECKPOINT21N_L_CONDITIONAL_ALPHA_FAILURE_RECORDING_REPAIR_20260831 -->
## Why a numerical optimizer guard can be a scientific gate

An optimizer can take an acceptable step yet still fail a mathematical condition
needed for the next BFGS update. Here the frozen rule required `y^T s > 1e-12`
unless convergence had already occurred.

Because that rule was declared before the real H-development fit, weakening it
after seeing the failure would change the experiment. The clean response is to
record the failure, not alter the optimizer until it passes.

<!-- CHECKPOINT21N_M_A_CONDITIONAL_ALPHA_V2_PREDECLARATION_20260831 -->
## BFGS vs gradient descent vs Newton in this experiment

All three methods minimize the same frozen loss; they differ in how they choose a step. BFGS estimates curvature from prior moves, gradient descent uses only the current slope, and Newton calculates local curvature directly from the exact Hessian.

BFGS was fast but its frozen curvature-update guard became numerically too small before convergence. The first-order diagnostic was stable but very slow. Newton worked cleanly because the problem has only five parameters, making the exact 5x5 curvature calculation and solve cheap.

A different optimizer does not automatically produce a better statistical model. If two methods genuinely converge on the same objective, they should reach essentially the same optimum. Here v2 changes the route to the optimum, not the definition of the optimum.

<!-- CHECKPOINT21N_M_B_CONDITIONAL_ALPHA_V2_IMPLEMENTATION_20260831 -->
## BFGS versus exact-Hessian Newton in this project

Both methods minimize the same conditional-alpha loss. BFGS estimates curvature
from successive gradients. Newton calculates the exact local curvature directly.

Because conditional alpha has only five parameters, the exact Hessian is a small
5x5 matrix. v2 solves that matrix by Cholesky and still uses Armijo backtracking
to prevent an overly aggressive Newton step. Better numerical navigation is not
a new prediction target or a profitability claim.

<!-- CHECKPOINT21N_M_C_CONDITIONAL_ALPHA_V2_EVALUATOR_20260831 -->
## Why evaluator wiring is frozen before a model run

Even when the model and optimizer are fixed, the surrounding evaluation code can
change results by changing data joins, folds, weighting, benchmarks, or gate order.

21N-M-C therefore freezes the *experiment plumbing* before the formal v2 run:
same H rows, same labels, same folds, same lambda rule, same probability gate,
and economics only after probability PASS. This keeps the optimizer change from
quietly becoming a broader strategy redesign.

<!-- CHECKPOINT21N_M_C_R1_TEST_HARNESS_REPAIR_20260831 -->
### A failing test can validate the guard rather than the model

The scaler failure was expected behavior: a z-score feature with zero fit-partition variance is invalid under the frozen contract. The bug was the synthetic fixture, not the scaler. Separately, Python exceptions must remain mutable enough for traceback bookkeeping; freezing an exception dataclass can mask the real error.

<!-- CHECKPOINT21N_M_C_R2_SYNTHETIC_ORCHESTRATION_TEST_REPAIR_20260831 -->
### A failed Cholesky test can mean the guard is working

Newton needs a positive-definite Hessian for this frozen Cholesky solver. The
conditional-alpha objective is not globally convex, so arbitrary fake data can
produce an indefinite Hessian. In v2, that is intentionally a hard stop.

A unit test should not force the implementation to violate its safety contract.
We test Newton convergence on a suitable synthetic case, and test evaluator
routing independently with a controlled fitter.

<!-- CHECKPOINT21N_N_A_ALPHA_ENTRY_DIAGNOSTIC_PREDECLARATION_20260831 -->
## Forecast accuracy and trade selection are different questions

Log loss evaluates probability quality across scored observations. A downstream
entry filter can still be useful if it ranks Candidate-E-positive-edge trades,
even when replacing Candidate E with its probability output would worsen log loss.

To test that distinction cleanly, Candidate E must remain the valuation model.
The conditional-alpha score can be tested as ranking information only, with the
economic diagnostic frozen before P&L is inspected.

<!-- CHECKPOINT21N_N_B_ALPHA_ENTRY_DIAGNOSTIC_IMPLEMENTATION_20260831 -->
## Why alpha is attached after the trade is chosen

If alpha were allowed to change the probability used to choose a side, market,
or anchor, this would again be a conditional probability strategy.

Instead, Candidate E first determines whether a quoted opportunity has positive
net edge. Alpha is attached afterward. That makes the diagnostic answer the
narrow question: does alpha rank Candidate-E opportunities by realized economic
quality?

<!-- CHECKPOINT21N_N_C_A_INCREMENTAL_ALPHA_SCORE_PREDECLARATION_20260831 -->
## Testing whether a second signal adds anything

If two signals move together, looking at one signal's best group can be
misleading. High alpha trades also had larger Candidate-E quoted edge.

A simple way to test incremental information is to put both on comparable scales:

`score = z(edge) + beta*z(logit(alpha))`.

Setting beta to zero gives the edge-only model. A positive beta earns its place
only if it improves economic ranking relative to that simpler benchmark.

<!-- CHECKPOINT21N_N_C_B_INCREMENTAL_ALPHA_SCORE_IMPLEMENTATION_20260831 -->
## Standardizing signals before combining them

Candidate-E edge and logit(alpha) have different units and scales. Converting
each to a z-score makes one unit mean one population standard deviation.

`S = z(edge) + beta*z(logit(alpha))`

then gives beta a clear interpretation: beta is the relative weight of a
one-standard-deviation alpha-reliability change compared with a
one-standard-deviation Candidate-E-edge change.

Outcome-blind scaling is important because the ranking rule must be fixed before
realized P&L is used to judge it.

<!-- CHECKPOINT21N_N_C_RESULT_CLOSEOUT_20260831 -->
## Forecast models and strategy models solve different problems

A probability model estimates an outcome such as `P(YES | state)`.
A trading strategy asks whether buying at a specific executable price is worth
the cost and uncertainty.

A strong forecaster can still produce a poor strategy if:
- the market price already reflects the information;
- fees/spread consume the edge;
- apparent edge is unstable;
- execution happens at worse prices;
- the model's errors concentrate exactly where trades are selected.

Therefore Candidate E remains a forecasting/valuation component. Downstream
strategy logic should be evaluated separately on economic and execution criteria.

<!-- CHECKPOINT21N_R_SIMULATOR_IMPLEMENTATION_20260901 -->
## Execution replay concepts added in Checkpoint 21N-R

### IOC limit order

An **immediate-or-cancel (IOC)** limit order tries to fill immediately at prices no worse than its limit.
Any unfilled quantity is canceled. Historical simulation therefore needs the full visible depth at arrival,
not just the best bid/ask.

Example: a YES buy limit of $0.40 can consume asks at $0.39 and $0.40, but not $0.41.

### Partial and missed fills

If only 0.40 contracts are available at acceptable prices for a 1.00-contract IOC, the simulated fill is 0.40
and the remaining 0.60 is canceled. If nothing is available at or better than the limit, the order is missed.

This is why a signal can look attractive at decision time but fail to become a trade after latency.

### Fixed-point fee ledger

Kalshi fixed-point accounting is not the same as simply rounding a final fee to a cent. In the frozen direct-member
counterfactual, each synthetic fill computes the model fee, rounds its trade-fee component upward to $0.000001,
aligns the balance change to $0.0001, and carries sub-grid overpayment in an order-local accumulator that can be
rebated in later fills of the same order.

The project uses `Decimal` so these rules are deterministic rather than dependent on binary floating-point error.

### Right-continuous millisecond replay

Historical snapshots may be captured inside a group of deltas sharing one millisecond timestamp. The archive
cannot tell us a more precise wall-clock instant inside that millisecond.

The frozen conservative solution is to expose only the final reconstructable book state for each millisecond.
This prevents the strategy from exploiting same-millisecond transient states whose exact timing is not identifiable.

### Counterfactual market impact

A historical replay can observe what the market actually did, but not what it would have done after our hypothetical
order. The simulator therefore consumes arrival depth for the order itself, then treats later historical books as
exogenous.

That is an assumption, not proof of zero market impact. It must be stress-tested or replaced with stronger evidence
before any production discussion.

<!-- CHECKPOINT21N_Z_E_A_RESTART_DURABLE_DESIGN_20260904 -->
## Restart safety: durable state versus live state

Durable audit state may survive restart; live freshness state must be rebuilt.
SQLite WAL + synchronous FULL provides transactional durability. Runtime
session ID and Linux boot ID separate process/boot contexts. Monotonic
timestamps are session-scoped. Crash-damaged evidence is recorded as an
explicit gap rather than reconstructed, and the prospective calendar clock
does not pause.
