# KXBTCD Successor Research Protocol

**Checkpoint:** 19A
**Status:** PROTOCOL FREEZE — NO CANDIDATE FIT
**Benchmark:** raw Kalshi midpoint
**Authorization:** read-only / outcome-blind feasibility only

## Why this checkpoint exists

Candidate B, Candidate C, Candidate D, and multiple failure analyses have all used the 231-event development pool. That pool is therefore fully exposed exploratory evidence. Candidate D is permanently closed as a development FAIL and must not be repaired or rescored on its 160-event score set.

The 64-event Checkpoint-17 terminal block is also permanently exposed and is prohibited from successor design, fitting, tuning, or future untouched-test claims.

Checkpoint 19A therefore freezes the evidence protocol before any new candidate is fit.

## Direction decision

The next successor eligible for advancement must contain at least one contemporaneous BTC-state feature whose information source is independent of Kalshi's own KXBTCD market probability.

This does **not** claim that Coinbase, Kraken, or another BTC source will beat Kalshi. It creates a different testable hypothesis: whether independently observed BTC state contains incremental settlement information beyond Kalshi's probability.

Probability-only recalibration is not eligible as the next advancing successor. Candidate D already tested the simplest form of that hypothesis and failed its frozen temporal-stability gate.

The initial independent source families for outcome-blind feasibility work are Coinbase and Kraken. Exact source IDs, parsers, staleness thresholds, cross-source disagreement policy, and feature formulas must be frozen before E1 outcomes are used.

Sub-second lead/lag remains prohibited. Coarse historical lookbacks such as five-minute coverage may be audited outcome-blind.

## Evidence tiers

### E0 — exploratory evidence

The existing 231-event / 5,364-row development pool and its Candidate B/C/D artifacts are fully exposed.

Allowed: hypothesis generation, diagnostics, engineering validation, feasibility planning.

Not allowed: advancement claims, fresh validation claims, hyperparameter qualification, or untouched-test claims.

### E1 — successor-design evidence

E1 must contain genuinely new chronological events whose eligible state observations occur after this protocol is frozen.

Before E1 outcomes are used, freeze:

- exact source IDs and source-quality rules;
- state/TTC materialization rules;
- candidate menu;
- feature formulas and transforms;
- tuning grid, if any;
- chronological scoring layout;
- primary/secondary metrics;
- advancement gate.

E1 may select among the small predeclared successor menu. Once E1 outcomes are used, E1 is permanently exposed design evidence.

### E2 — final-model fitting evidence

E2 begins only after one successor specification is frozen from E1.

E2 may estimate the already-selected model's final parameters. It may not choose a new feature set, model family, hyperparameter grid, regime filter, or advancement rule.

The resulting preprocessing, parameters, provenance, and inference implementation must be fingerprinted as one immutable final-model artifact.

### E3 — genuinely untouched prospective test evidence

E3 begins only after the final E2 model is frozen.

The primary benchmark remains the raw Kalshi midpoint. The primary metric remains event-equal log loss, with event-equal Brier secondary. A temporal-stability condition is required in addition to pooled scoring; the exact terminal gate will be frozen later before any E3 outcome access.

Once E3 outcome access begins, the frozen E3 cohort is permanently exposed and cannot support redesign or a second untouched-test claim.

## Checkpoint-19A feasibility contract

This checkpoint is outcome-blind. The feasibility artifact may contain only contemporaneous/pre-state information needed to answer whether independent BTC features can be materialized safely and consistently.

For each KXBTCD state it may record:

- Kalshi state identity, strike, TTC, midpoint, and spread;
- exact raw lineage;
- Coinbase availability, timestamp, price, and age;
- Kraken availability, timestamp, price, and age;
- cross-source price disagreement when both sources exist;
- whether a five-minute causal lookback is available from each source;
- structural exclusion reasons.

It must not contain result/outcome fields, Candidate-E predictions, scores, or any execution field.

Reference observations must not come from the future relative to the KXBTCD state timestamp. No future interpolation is allowed.

## Sample-size rule

E1/E2/E3 minimum event counts and minimum calendar coverage are **not** selected from outcomes.

They will be frozen only after the outcome-blind feasibility audit measures source availability, missingness, chronology, and calendar coverage. The audit may determine whether a proposed data-quality threshold is operationally feasible, but it may not inspect outcome performance when choosing the cohort sizes.

## What is intentionally not frozen yet

Checkpoint 19A does not freeze:

- Candidate E's exact formula;
- a source consensus-price formula;
- a staleness threshold;
- a cross-source disagreement threshold;
- an E1/E2/E3 event count;
- a regularization grid;
- an advancement threshold;
- a final terminal cohort.

Those items require the outcome-blind feasibility evidence first.

## Safety

- Candidate-E fitting: prohibited in Checkpoint 19A.
- Outcome access: prohibited in Checkpoint 19A.
- Checkpoint-17 terminal use: prohibited permanently.
- Paper execution: prohibited.
- Demo execution: prohibited.
- Real-money execution: prohibited.
- Order creation/cancellation/transfers: prohibited.

Passing this protocol or feasibility audit is research-process evidence only. It does not establish predictive edge or profitability.
