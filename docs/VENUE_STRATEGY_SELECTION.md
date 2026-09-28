# Venue and Strategy Selection

Status: checkpoint-07 accepted research design. No venue, category, horizon, or strategy has been selected for trading or modeling.

## Research question

The project now asks:

> **Across markets that can be lawfully and reproducibly researched, where is there the strongest evidence of an executable, repeatable edge after fees, spread/slippage, depth, latency, fills, adverse selection, settlement uncertainty, and model uncertainty?**

The answer may be crypto or non-crypto, short horizon or long horizon, and on any venue that passes the project's access, data-quality, and safety gates.

## Why this precedes feature-feed selection

A predictive feed is useful only relative to a declared strategy.

Examples:

- BTC spot data may matter for a crypto threshold contract;
- official meteorological forecasts may matter for a weather contract;
- official macro releases and forecast vintages may matter for economic contracts;
- sports-state data may matter for in-game sports contracts;
- no external feed may be needed for a pure calibration or maker/microstructure strategy.

Therefore feed-first architecture risks optimizing the wrong problem.

## Market universe

### 1. Regulated U.S. event/prediction exchanges

Use the current CFTC Designated Contract Market list as the regulator-level discovery source, then separately verify operational status, product availability, public data access, and exact API terms from each venue.

Current examples reviewed during checkpoint 07 include, among others:

- Kalshi;
- North American Derivatives Exchange / Crypto.com;
- ForecastEx;
- QCX / Polymarket US;
- Gemini Titan;
- ProphetX;
- newer 2026 DCMs such as Xchange Alpha, Ludlow Exchange, Optex Markets, Water Street Labs, and Juice Exchange.

Appearance on the DCM list is **not** evidence of current liquidity, public API availability, suitable products, or project eligibility. Those are census fields to verify.

Primary discovery source:

`https://www.cftc.gov/IndustryOversight/IndustryFilings/TradingOrganizations?Status=Designated`

### 2. Research-only external event markets

A market that is not an execution candidate may still be useful as a public research/reference source if access is lawful and terms permit the intended use.

Execution eligibility and reference-data eligibility must remain separate fields.

### 3. Continuous crypto markets

Spot, perpetual futures, dated futures, and options are part of the opportunity screen.

They can serve as:

- direct strategy candidates in a later separately scoped project;
- feature/reference markets for event contracts;
- cross-market probability or basis references.

They do not receive priority merely because they are liquid.

### 4. Traditional financial markets

Futures, options, equities, rates, commodities, and volatility strategies remain candidate opportunity classes for comparison.

The project should account for data cost, margin/leverage, hedging complexity, market maturity, and execution infrastructure before deciding they dominate event markets.

### 5. Sports betting/exchange markets

Sportsbooks, betting exchanges, and sports event contracts are conceptually relevant, but legal/access/API structure and pricing mechanics differ sharply.

A bookmaker quote with embedded margin is not automatically comparable to a binary CLOB probability. Any sportsbook-based research needs a separately declared normalization and access policy.

## Event-market domain universe

Do not hard-code categories. Preserve source categories when available and map them later into a versioned taxonomy.

Expected high-level groups may include:

- crypto;
- sports;
- macro/economics;
- weather/climate;
- politics/elections/policy;
- entertainment/culture;
- technology/business;
- commodities/financial thresholds;
- other/uncategorized.

A new category can be added without changing the raw source record.

## Horizon universe

Do not make `15m` a schema assumption.

Store exact open, close, expiration, settlement, and observation timestamps where available and derive:

```text
time_to_close_seconds
contract_lifetime_seconds
```

Analysis may create horizon buckets later. Example analytical buckets—not source truth—might include:

- under 10 minutes;
- 10–60 minutes;
- 1–24 hours;
- 1–7 days;
- 1–4 weeks;
- over 4 weeks.

Bucket boundaries must remain configurable and sensitivity-tested.

## Strategy families

### A. Calibration / behavioral structure

Question:

> Does the realized outcome frequency systematically differ from quoted probability conditional on venue, price, domain, horizon, product type, and other observable state?

Baseline metrics:

- reliability/calibration curves;
- Brier score;
- log loss;
- realized return by price bucket after costs;
- stability through time and across folds.

Published research motivates this hypothesis but does not prove a future exploitable effect.

### B. Maker / microstructure economics

Question:

> Can passive liquidity provision earn positive expected value after adverse selection, queue/fill uncertainty, fees, inventory exposure, missed fills, and expiring incentive programs?

Required later simulator components:

- price-time/queue approximation where possible;
- available displayed depth;
- partial fills;
- cancellations and stale quote risk in paper only;
- adverse movement after fill;
- maker/taker fees;
- incentive/rebate versioning;
- inventory/exposure constraints.

Do not treat a temporary liquidity program as permanent alpha.

### C. Relative value

Question:

> Are two economically comparable state-contingent payoffs priced differently enough, for long enough, to survive settlement-basis differences and executable costs?

Before comparison, explicitly map:

- underlying;
- threshold/range;
- observation window;
- expiration;
- settlement source;
- payout definition;
- rounding/tie rules;
- fees;
- executable side/depth.

If any material payoff difference is unresolved, call the observation a `pricing_difference`, not `arbitrage`.

### D. External-feature directional prediction

Question:

> Does external information improve out-of-sample probability estimates beyond the event market's own contemporaneous state?

The event-market midpoint/book is a mandatory baseline.

External features are added only after the target market is selected and must retain exact source identity.

## Evidence motivating the event-market focus

The latest research layer found multiple large-sample studies documenting structured prediction-market effects, including:

- favorite–longshot and maker/taker differences on Kalshi;
- domain × horizon calibration structure across Kalshi and Polymarket;
- sports time-to-expiry and parlay-pricing effects;
- persistent Bitcoin prediction-market versus option-implied probability wedges.

These are **research hypotheses**, not guaranteed edges. Several are working papers/preprints and may not be peer-reviewed.

References:

- `https://www.ifo.de/en/cesifo/publications/2026/working-paper/makers-and-takers-economics-kalshi-prediction-market`
- `https://arxiv.org/abs/2602.19520`
- `https://arxiv.org/abs/2607.14430`
- `https://arxiv.org/abs/2606.19517`

The same review also found recent evidence that a synchronized short-horizon BTC prediction-market/spot model can detect reaction lag yet still fail to beat the event-market probability after realistic evaluation. This weakens any assumption that latency alone guarantees profit.

## Census unit of analysis

Checkpoint-07 live evidence established that individual binary contracts cannot be treated as independent high-level opportunities. A single event may expose hundreds of thresholds, strikes, totals, spreads, or outcome variants.

Stage-1 availability therefore uses **event/opportunity count** as the primary discovery unit and records contract multiplicity separately. Series/category coverage sits above events when the source exposes it. Individual markets/contracts become Stage-2 units only after an event/series candidate survives screening.

This prevents venues with aggressive line/strike fan-out from appearing to have more independent opportunities merely because they instantiate more contracts per underlying occurrence.

## Census hard gates

A candidate may be observed but cannot graduate to a strategy experiment unless the required gates are met.

### Access gate

- data access is lawful for the intended project use;
- terms/licensing permit the intended collection/research;
- required authentication is separately authorized if needed later;
- no geoblock/account-evasion behavior.

### Data-quality gate

- source identity is verified;
- raw data can be preserved;
- required market IDs and lifecycle fields are available;
- missing fields are explicit;
- timestamp semantics are documented enough for the intended analysis;
- stale/gap/schema failures can be detected or bounded.

### Economic observability gate

For the proposed strategy, enough of the following must be measurable:

- executable bid/ask;
- displayed size/depth;
- trades or activity;
- fees;
- incentives/rebates;
- settlement payout;
- realized outcome.

If costs/fills cannot be modeled honestly, strategy eligibility remains blocked.

### Settlement gate

- payoff and official settlement source/rules are documented enough to know what outcome the contract represents;
- unresolved material basis differences are not hidden.

### Sample gate

- enough independent resolved observations exist for uncertainty estimates appropriate to the hypothesis;
- chronological train/test or pre/post splits are possible;
- one promotional regime or one news episode cannot dominate the entire result.

No universal minimum sample count is declared before observing market recurrence and dependence structure.

## Census comparison vector

Census v1 retains separate metrics rather than one arbitrary score.

### Market availability

- number of active events/opportunities;
- contract count per event as a separate fan-out metric;
- number and coverage of recurring series/templates;
- category coverage;
- horizon distribution;
- resolved-outcome availability.

### Liquidity/execution observability

- best bid;
- best ask;
- spread;
- depth near touch;
- total displayed depth where available;
- trade/update activity where available;
- volume/open interest where defined;
- stale/no-quote frequency.

### Cost structure

- maker fee;
- taker fee;
- settlement/other fees;
- rebates/incentives;
- effective date/version/source.

### Data engineering quality

- public discovery access;
- streaming/snapshot capability;
- source timestamps;
- sequence/recovery semantics;
- raw replayability;
- rate limits;
- schema stability;
- historical access.

### Contract/settlement clarity

- source of truth;
- payoff grammar;
- close/settlement timestamps;
- tie/rounding rules where relevant;
- outcome publication;
- amendment/correction rules where relevant.

## No one-number ranking in census v1

Do not assign arbitrary weights such as `40% liquidity + 30% API + 30% edge`.

First identify:

- candidates that fail hard gates;
- candidates that are Pareto-dominated on relevant measured dimensions;
- candidates that require different strategy families and therefore are not directly comparable yet.

A composite score may be introduced later only with documented weights and sensitivity analysis.

## Graduation from census to experiment

The census selects **hypotheses**, not winners.

A candidate graduates when it can state:

```text
market/venue/product
strategy family
expected source of edge
required data
cost/fill model
settlement definition
predeclared evaluation metric
failure/rejection criteria
```

Only then should specialized data collectors or modeling work begin.

## Facts vs hypotheses

### Facts

- The CFTC currently lists multiple designated contract markets, including several event/prediction-oriented venues and several newer 2025–2026 entrants.
- Public API capabilities differ materially by venue.
- The current project runtime remains Kalshi-only and read-only.

### Accepted design choices

- venue/category/horizon neutrality;
- hard gates before strategy experiments;
- no arbitrary weighted score in census v1;
- four separate strategy families;
- feed selection after strategy selection.

### Hypotheses

- event-market structural effects may be more durable for this project than pure sub-second BTC forecasting;
- some domain/horizon/product combinations may be materially less efficient than others;
- maker or relative-value approaches may outperform directional forecasting in some venues;
- a niche market may dominate a high-volume market after costs.

### Unresolved

Everything economic: actual best venue, category, horizon, product, strategy family, capacity, and net edge.

## Checkpoint-07 measured result and first experiment selection

The final accepted census run produced 12,198 high-level event rows and 107,293 separate source-native contract snapshots across Kalshi, Gemini Predictions, Polymarket US, and Crypto.com Predictions. The manifest and row-level relationship checks passed with zero raw/runtime errors, zero duplicate contract composite keys, zero orphan contracts, and zero event/contract-count mismatches.

Cross-venue baseline discovery remains important, but the deepest current-tradability diagnostic was performed on Kalshi because its nested Market objects exposed the required bid/ask, top-size, 24h-volume, open-interest, and timing fields in the same public crawl. This is an observability reason for the deeper diagnostic, not proof that Kalshi is economically superior.

The final Kalshi screen required a central YES midpoint `[0.10, 0.90]`, positive 24h volume, and positive best-bid and best-ask size. Kalshi's deprecated `liquidity` field was explicitly excluded.

For the 1–7d slice:

| Category | Contracts | Unique events | <=2c spread | Median spread | Median 24h volume | Median bid size | Median ask size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Crypto | 38 | 9 | 55.3% | 0.0200 | 1386.185 | 444.50 | 943.925 |
| Climate and Weather | 117 | 42 | 74.4% | 0.0100 | 811.15 | 9.00 | 13.72 |
| Commodities | 130 | 12 | 81.5% | 0.0100 | 128.435 | 205.50 | 145.00 |
| Sports | 2144 | 1077 | 69.0% | 0.0200 | 59.535 | 300.00 | 568.50 |

### Selection

Checkpoint 07 selects **Kalshi Sports, 1–7 days before close, calibration / behavioral structure** as the first historical strategy-research class.

The decision optimizes for an experimental property: a large number of independent underlying events while retaining observable two-sided market quality. It does not mean Sports has the highest expected profit, nor does it select Kalshi for eventual production execution.

Secondary branches remain active:

- Crypto 1–7d for external-feature directional or relative-value hypotheses;
- Climate & Weather 1–7d for official-reference/settlement-data hypotheses;
- Commodities 1–7d for scheduled/reference-value hypotheses.

The predeclared protocol is `docs/SPORTS_CALIBRATION_EXPERIMENT.md`. Historical data collection and outcome analysis must follow that document rather than adapting the primary hypothesis after results are visible.
