# Reference Feed Selection

Status: **no predictive/reference feed selected**. The earlier checkpoint-07 Coinbase-first selection is superseded.

Current trigger: modern-regime KXBTCD is the primary Checkpoint-11 model-readiness family under D-038. This selects the research target, not an auxiliary source. Coinbase, Kraken, BRTI, options, futures, and event-market-only features remain candidates until a causal information hypothesis, timing contract, access/licensing review, and incremental evaluation are frozen.

## Corrected decision

Predictive/reference source selection is downstream of market and strategy selection.

Use this order:

```text
execution/research market
    -> strategy hypothesis
    -> required information
    -> candidate sources
    -> source-quality/timing/access review
    -> implementation
```

A convenient or technically attractive data source must not determine what strategy the project tries to trade.

## Why the earlier Coinbase-first decision was superseded

Checkpoint 07 initially compared Kraken public trade data with Coinbase Exchange public WebSocket data for short-horizon BTC research. Coinbase was selected to avoid training/live distribution shift if the project later used Coinbase operationally.

That reasoning remains valid **conditional on already knowing that a Coinbase-informed crypto strategy is the target**.

Broader research removed that condition. The project may ultimately find a better opportunity in:

- another crypto event horizon;
- sports event-market microstructure;
- macro contracts;
- weather contracts;
- cross-venue relative value;
- another event category or product structure.

A crypto spot WebSocket would be irrelevant infrastructure for several of those winners.

Therefore D-020 is superseded before collector implementation.

## What remains valid from the earlier work

### Source identity must remain explicit

A model trained with one venue's data must not silently use another venue live.

Bad feature name:

```text
btc_return_1s
```

Better feature names:

```text
coinbase_btcusd_return_1s
kraken_btcusd_return_1s
```

If a source changes, the dataset/feature contract changes and requires re-validation.

### Auxiliary data never inherits settlement authority

A predictive source may correlate strongly with the event outcome and still be invalid as an official settlement label.

Contract-rule authority, numerical settlement authority, official delivery channels, and auxiliary predictive data remain separate roles.

### One simple baseline before unnecessary aggregation

After a market/strategy is selected, begin with the smallest source set that can test the hypothesis.

Add another source only when it has a predeclared incremental hypothesis and can be tested out of sample.

## Source-selection scorecard after a strategy is selected

For each candidate source, document before decision use:

- exact owner and endpoint identity;
- source role;
- symbol/instrument/payoff basis;
- public/private authentication state;
- licensing and permitted research/model use;
- source timestamp semantics;
- publication/relay timestamp semantics when available;
- local receive timing;
- sequence/gap/duplicate behavior;
- reconnect/replay/recovery behavior;
- historical/live consistency;
- raw replayability;
- correction/amendment behavior;
- freshness/staleness threshold;
- schema-drift policy;
- missing-data policy;
- cost and rate limits.

No source receives a `selected` state merely because its API is easy to use.

## Domain-specific examples, not rankings

### If short-horizon crypto wins

Possible information classes include:

- public spot trades;
- public spot BBO/order books;
- futures/perpetual prices and basis;
- options-implied distributions;
- official settlement-index delivery if authorized/licensed;
- event-market state itself.

Coinbase and Kraken remain examples of public crypto source candidates already reviewed. They are not selected by this document.

### If sports wins

Candidate sources must include official/contract settlement rules and lawful auditable sports-state/statistics feeds. A sportsbook price is not automatically an unbiased probability label.

### If macro wins

Prefer official release authorities for realized labels. Consensus/forecast sources require separate licensing and timestamp review.

### If weather wins

Prefer official settlement-station/rule evidence for labels and official meteorological observations/forecast products for features where permitted.

## Relationship to the opportunity census

The census itself should avoid specialized predictive feeds.

Its purpose is to observe the **market opportunity surface**:

- what markets exist;
- their categories and horizons;
- quoted/executable market quality;
- cost/incentive structure;
- settlement clarity;
- data quality and availability.

Only after that evidence identifies a strategy candidate should this document be updated with a selected feature source.

## Facts, hypotheses, and unresolved items

### Accepted facts/design principles

- Source substitution can create distribution shift.
- Auxiliary predictive data is distinct from settlement authority.
- First-seen local timing must be preserved for causal research.
- Feed selection now follows market/strategy selection.

### Hypotheses to test later

- A second crypto venue may add predictive information beyond a first one.
- Options/futures may contain useful probability information for threshold event contracts.
- External data may or may not beat the information already contained in the event-market book.

### Unresolved

- whether modern-regime KXBTCD supports any predictive or executable edge;
- the exact KXBTCD model horizon and decision schedule;
- the minimum feature set that can improve on executable market-implied probabilities;
- required external source set;
- acceptable source-specific freshness thresholds.

## Official source examples reviewed during checkpoint 07

These links document candidate capabilities only; they are not endorsements:

- CFTC designated contract markets: `https://www.cftc.gov/IndustryOversight/IndustryFilings/TradingOrganizations?Status=Designated`
- Kalshi public market data: `https://docs.kalshi.com/getting_started/quick_start_market_data`
- Kalshi WebSocket connection: `https://docs.kalshi.com/websockets/websocket-connection`
- Gemini Prediction Markets: `https://developer.gemini.com/prediction-markets/prediction-markets`
- Gemini prediction-market streams: `https://developer.gemini.com/trading/websocket/streams`
- Polymarket US API: `https://docs.polymarket.us/api-reference/introduction`
- Crypto.com Predictions API: `https://data-api.crypto.com/docs`
