# KXBTCD Post-H3 Champion Lifecycle, Reserve Strategy, and Prospective Validation

**Checkpoint:** 21A — protocol/design freeze
**Status:** accepted design; no post-H3 refit; no C1/C2/C3 outcomes opened
**Champion specification:** `kxbtcd_btc_distance_offset_logistic.v1`
**Parent H3 result fingerprint:** `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`
**Protocol fingerprint:** `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
**Machine-readable contract:** `configs/kxbtcd_post_h3_champion_lifecycle.v1.json`

The protocol fingerprint is the SHA-256 of the contract serialized as canonical JSON with sorted keys and compact separators.

## 1. Purpose

Candidate E has completed the frozen H1/H2/H3 historical generalization program and passed all three stages. The next problem is no longer candidate selection. It is how to use the remaining fresh evidence without destroying the project's ability to evaluate future challengers.

This document freezes the post-H3 evidence architecture before any post-H3 Candidate-E refit or reserve outcome access.

It separates five questions:

1. **Champion confirmation:** does the same Distance specification keep generalizing as time advances?
2. **Strategy research:** can a fixed model probability be turned into a plausible decision policy after realistic costs and executable-price constraints?
3. **Untouched reserve:** how much fresh historical evidence remains protected for future challenger evaluation?
4. **Prospective live shadow:** does a frozen model + frozen strategy behave well on newly occurring events using real live feeds and a local mock execution layer?
5. **Later execution research:** are any future demo or production gates met? This remains separate and is not authorized here.

A forecasting PASS is not a profitability PASS. A historical strategy backtest is not a fresh profitability test. A live shadow PASS would still not authorize real orders.

## 2. Starting evidence state

Accepted historical evidence:

- H1: 1,500 events — exposed development evidence.
- H2: 750 events — exposed validation evidence.
- H3: 750 events — exposed locked-test evidence.
- Total exposed Candidate-E events: 3,000.
- H3 fixed beta entering the locked test: `0.013805016135330063`.
- Candidate-E H1/H2/H3 historical generalization program: PASS.

Strict untouched historical tail from the 19H-C freeze:

- approximately 6,231 events.

The word **strict** matters. In this project, an event can cease to belong to the strict untouched tail after outcome-blind historical materialization even if its settlement label remains unopened. Therefore reserve protection must account for raw chronological candidates consumed by materialization, not only the number of labels eventually scored.

## 3. Accepted post-H3 champion confirmation design

The champion remains exactly:

`kxbtcd_btc_distance_offset_logistic.v1`

No new feature, interaction, regularization value, optimizer, source substitution, or model family is introduced in the champion path.

The same Candidate-E historical construction remains authoritative:

- Coinbase is the required independent BTC source.
- Kraken is nonblocking diagnostic evidence.
- the six TTC targets remain 55m, 50m, 45m, 40m, 35m, and 30m;
- the five structural strike roles remain required at evaluation-block level;
- no future information, interpolation, or outcome-driven eligibility change is permitted.

### C1 — first confirmation block

After this protocol is safely closed:

1. fit the same Distance specification once on all 3,000 exposed H1+H2+H3 events;
2. freeze that model artifact before C1 outcomes;
3. starting from the first strict untouched chronological tail identity after the accepted 19H-C materialized prefix, apply the unchanged outcome-blind Candidate-E eligibility rules until exactly 500 eligible C1 events are frozen;
4. split those 500 eligible events chronologically into five contiguous 100-event subblocks;
5. freeze C1 identities, rows, market-label allow-list, subblock map, source/materialization lineage, and evaluation procedure before any C1 outcome access;
6. score C1 exactly once.

The implementation must derive and validate the actual starting queue identity from the canonical 19H-C artifacts. It must not rely on a chat-only index assumption.

### C2 — second confirmation block

C2 is not materialized or outcome-opened unless C1 passes.

After C1 PASS:

1. C1 becomes exposed;
2. refit the unchanged Distance specification once on H1+H2+H3+C1 = 3,500 exposed events;
3. freeze that model;
4. continue the exact same deterministic chronological outcome-blind eligibility scan from the first unconsumed strict-tail identity;
5. freeze the next 500 eligible events as C2 in five 100-event chronological subblocks;
6. score C2 exactly once.

### C3 — third confirmation block

C3 is not materialized or outcome-opened unless C2 passes.

After C2 PASS:

1. C2 becomes exposed;
2. refit the unchanged Distance specification once on 4,000 exposed events;
3. freeze that model;
4. continue the exact same chronological eligibility scan;
5. freeze the next 500 eligible events as C3 in five 100-event chronological subblocks;
6. score C3 exactly once.

After C3 PASS:

- C3 becomes exposed;
- the champion may be fit once on all 4,500 exposed H1+H2+H3+C1+C2+C3 events;
- that 4,500-event artifact becomes the historical champion entering strategy research.

## 4. Frozen C1/C2/C3 advancement gate

Every confirmation block must satisfy all conditions below.

### Primary pooled metric

Event-equal raw-minus-Champion log-loss delta must be strictly positive:

`raw event-equal log loss - Champion event-equal log loss > 0`

An exact primary tie fails.

### Secondary pooled metric

Event-equal raw-minus-Champion Brier delta must be nonnegative:

`raw event-equal Brier - Champion event-equal Brier >= 0`

### Chronological stability

- Champion must win event-equal log loss in at least 4 of 5 100-event chronological subblocks.
- Champion must win the newest fifth subblock.

### Event-level robustness

Median event-level raw-minus-Champion log-loss delta must be strictly positive.

### Model validity

The model entering the block must:

- be finite;
- have converged under the unchanged fitting procedure;
- have `beta_distance > 0`.

### Structural and evidence validity

The scored block must preserve:

- all five structural strike roles;
- all six TTC targets;
- exact source/materialization lineage;
- frozen timing/causality rules;
- outcome firewall integrity;
- no execution or order path.

Any material source, lineage, timing, firewall, or policy violation fails closed.

## 5. Stopping rule

Any C-block failure stops the champion-confirmation sequence immediately.

Examples:

- C1 FAIL => do not materialize or open C2/C3.
- C2 FAIL => do not materialize or open C3.
- C3 FAIL => do not advance Candidate E into strategy research as the accepted champion.

A failed block may later be studied only as exposed evidence under a separately documented failure-analysis checkpoint. It may not be repaired, retuned, rescored, or used to change the gate and then be presented as fresh confirmation.

## 6. Strict untouched reserve rule

The current strict historical tail contains approximately 6,231 events.

The champion path may consume only enough chronological raw candidates to freeze C1/C2/C3, and it must fail closed before fewer than **4,500 strict untouched historical events** would remain.

Therefore:

- minimum strict reserve preserved for future challenger evaluation: 4,500 events;
- maximum strict-tail candidates the champion path may consume across C1+C2+C3 materialization: approximately 1,731 events;
- target scored confirmation events: exactly 1,500 eligible events.

Why the floor is 4,500 rather than simply `6,231 - 1,500 = 4,731`:

- the eligibility scanner may need to inspect additional ineligible chronological candidates;
- those inspected candidates no longer belong to the strict never-materialized tail under the project's existing reserve definition;
- a 4,500 hard floor gives the frozen three-block design room to complete without weakening eligibility rules while still preserving more than 72% of the current strict tail.

If 1,500 eligible C events cannot be obtained before the 4,500 strict-tail floor would be crossed, the confirmation program fails closed. Do not relax source, TTC, structural, or eligibility requirements to rescue it.

## 7. What C1-C3 do and do not prove

If all three pass, the project may conclude:

> The unchanged Candidate-E Distance specification demonstrated additional chronological historical confirmation beyond H1/H2/H3 under sequential expanding-window refits.

It still may not conclude:

- the model is guaranteed to remain accurate forever;
- the model identifies an executable trading edge;
- a particular betting strategy is profitable;
- historical midpoint improvement survives fees, spread, depth, latency, or fills;
- demo or real-money trading is authorized.

## 8. Post-C3 historical strategy-research checkpoint

Historical strategy research is authorized only after:

1. C1 PASS;
2. C2 PASS;
3. C3 PASS;
4. the final 4,500-event Distance champion is fit and frozen.

The strategy-development dataset is **exposed evidence only**.

Permitted development evidence can include:

- H1/H2/H3;
- C1/C2/C3 after they have been scored and exposed;
- other already exposed engineering/execution evidence that is valid for the strategy question.

The 4,500-event strict untouched reserve may not be used to choose strategy thresholds, TTC windows, entry rules, exit rules, sizing rules, or execution assumptions.

### Required first step: execution-data adequacy audit

Before choosing a strategy, determine what historical data actually supports executable economics.

Audit whether exposed evidence contains, for the required times:

- executable YES/NO bid and ask rather than midpoint only;
- spread;
- quoted size/depth;
- fee schedule applicable to the hypothetical action;
- timestamps and ordering needed for latency assumptions;
- enough states to model exits;
- enough information to distinguish full fills, partial fills, and missed fills.

If historical evidence does not contain enough execution detail, the project may still research decision signals, but it must not present midpoint-only or perfect-fill P&L as realistic profitability evidence.

### Strategy variables that may be researched later

Examples include:

- model probability minus executable YES ask or analogous NO-side edge;
- minimum edge threshold;
- explicit cost buffer;
- model-uncertainty buffer;
- TTC entry window;
- spread/depth eligibility;
- hold-to-settlement versus predeclared exit logic;
- fixed or risk-capped sizing;
- maximum event exposure;
- no-trade regions.

The exact strategy is **not** selected in Checkpoint 21A.

Martingale, loss-chasing, manipulative behavior, and real order submission remain prohibited.

### Historical strategy metrics

A later frozen strategy-development procedure should report at minimum:

- net counterfactual P&L after modeled fees and execution costs;
- event count and trade count;
- capital deployed / turnover;
- mean and median P&L per trade and per event;
- win/loss distribution;
- maximum drawdown;
- lower-tail loss diagnostics;
- realized or assumed spread cost;
- simulated latency cost;
- fill ratio, partial-fill rate, and missed-fill rate where the data support them;
- performance by chronological block;
- performance by TTC and model-edge band.

Because the strategy will be designed on exposed evidence, this is development evidence, not fresh profitability validation.

## 9. Prospective full live shadow phase

The prospective phase should eventually run the complete read-only research stack, not only collect probabilities.

It begins only after:

1. C1-C3 PASS;
2. final 4,500-event champion freeze;
3. historical strategy research;
4. one strategy/decision policy is selected and frozen;
5. the execution-simulation assumptions and failure semantics are frozen and tested;
6. `docs/RISK_POLICY.md` is explicitly amended to authorize a local live shadow/paper broker if the project decides to permit that phase.

The current risk policy does **not** authorize this live mock-execution engine yet.

### Layer A — immutable forecasting ledger

For every eligible live state/event, persist before settlement:

- exact champion model fingerprint;
- feature-contract/source-policy versions;
- raw-source lineage;
- UTC and local monotonic timing where applicable;
- Kalshi raw benchmark probability;
- Candidate-E probability;
- eligibility/abstention reason;
- later settlement label joined without rewriting the original prediction.

The first formal prospective forecasting cohort is frozen at:

- 1,000 newly occurring eligible KXBTCD events;
- five contiguous chronological blocks of 200 events each;
- one immutable champion model for the entire 1,000-event cohort.

Forecasting PASS requires:

1. pooled raw-minus-Champion event-equal log-loss delta > 0;
2. pooled raw-minus-Champion event-equal Brier delta >= 0;
3. Champion log-loss wins in at least 4 of 5 chronological blocks;
4. Champion wins newest block P4;
5. median event-level raw-minus-Champion log-loss delta > 0;
6. no model, feature, source-policy, or gate change during the cohort;
7. immutable prediction/abstention records for every scheduled eligible decision state under the frozen live contract;
8. no source, timing, lineage, or policy violation.

Calibration diagnostics, TTC slices, strike-role slices, volatility slices, spread slices, source-disagreement diagnostics, and coverage should also be reported. They are diagnostics unless a later pre-outcome protocol explicitly promotes one into a gate.

### Layer B — local decision/execution shadow

The same live stream may later drive a frozen local mock execution engine.

Conceptual path:

`live Coinbase/Kraken/Kalshi feeds`

`-> synchronized state`

`-> frozen Candidate-E probability`

`-> frozen strategy decision`

`-> local MOCK order intent only`

`-> latency model`

`-> observed live Kalshi book/depth`

`-> simulated full/partial/missed fill`

`-> mock position state`

`-> frozen hold/exit logic`

`-> mock realized P&L`

No order, cancel, transfer, or portfolio write may be sent to Kalshi.

A realistic live shadow must account for:

- actual bid/ask rather than midpoint;
- fees;
- available depth;
- latency;
- slippage;
- partial fills;
- missed fills;
- stale-feed and sequence-gap failure semantics;
- clock health;
- duplicate-action protection;
- model uncertainty;
- exposure/risk caps.

The exact prospective economic PASS/FAIL thresholds are deliberately **not frozen yet**. They must be selected only after the historical strategy-development checkpoint and must be frozen before the first live shadow trade decision is generated.

## 10. Challenger research path

Richer models remain challengers, not silent champion edits.

Permitted future research families include:

- TTC effects;
- recent BTC momentum;
- realized volatility;
- Kalshi spread;
- distance × TTC;
- distance × volatility;
- market-probability × independent-BTC interactions;
- small spline or other constrained nonlinear models;
- small tree/boosting baselines if simpler challengers justify them.

Checkpoint 21A does not fit or select any challenger.

Before a challenger is frozen, research must use exposed evidence only. The 4,500-event strict untouched reserve is not a feature-shopping or hyperparameter-tuning resource.

A future challenger must have its own predeclared training/selection procedure and fresh champion-vs-challenger evaluation allocation before any protected outcomes are opened.

## 11. When fitting on all exposed evidence is scientifically reasonable

It is reasonable to fit the unchanged Distance specification on all currently exposed evidence only after the next test it will face has been frozen.

Therefore:

- after Checkpoint 21A closeout, fit once on H1+H2+H3 = 3,000 before C1;
- after C1 PASS, refit once on 3,500 before C2;
- after C2 PASS, refit once on 4,000 before C3;
- after C3 PASS, refit once on 4,500 before strategy research.

It is **not** scientifically justified to consume the protected historical reserve merely to shrink estimation error in a one-parameter model before challengers have had access to fresh evidence.

During the 1,000-event prospective live cohort, do not refit the champion. After that cohort is fully scored and recorded, those prospective outcomes become exposed and may enter a later separately frozen retraining/challenger cycle.

## 12. State-transition summary

`H3 PASS`

`-> Checkpoint 21A protocol freeze`

`-> 3,000-event fit + C1 freeze`

`-> C1 PASS`

`-> 3,500-event fit + C2 freeze`

`-> C2 PASS`

`-> 4,000-event fit + C3 freeze`

`-> C3 PASS`

`-> final 4,500-event champion fit`

`-> historical strategy/execution-data research on exposed evidence only`

`-> freeze one strategy + realistic shadow-execution contract`

`-> explicit risk-policy authorization for local live shadow broker`

`-> 1,000-event full live shadow: forecasting + decision/execution simulation`

`-> only later, and only under separate gates and explicit approval, discuss demo execution`

Any failure stops advancement at that layer. Passing one layer does not silently authorize the next execution phase.

## 13. Checkpoint 21A implementation boundary

This checkpoint freezes design only.

At 21A closeout:

- post-H3 Candidate-E refits performed: 0;
- C1 outcomes opened: 0;
- C2 outcomes opened: 0;
- C3 outcomes opened: 0;
- protected reserve outcomes opened: 0;
- challenger fit/selection: 0;
- historical strategy selected: no;
- live shadow broker enabled: no;
- demo orders: 0;
- real orders: 0.

The next implementation checkpoint is outcome-blind C1 preparation only.
