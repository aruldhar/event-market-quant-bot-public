# KXBTCD vs. Kalshi BTC Perpetuals — Preselection Gate

Date: 2026-08-13

Status: comparison designed; target selection deferred pending a same-window local audit

## Authorization boundary

This is read-only research. The existing environment-managed Kalshi key may be used for authenticated read-only REST and WebSocket collection, including BTC perpetual-market endpoints if supported by the account. Public Coinbase and Kraken feeds are permitted. Credentials must never be logged or committed. Orders, cancellations, transfers, demo trading, paper execution, leveraged execution, and real-money execution are prohibited.

## What is being compared

KXBTCD is a sequence of expiring binary event contracts. Each contract produces a probability-like price and one eventual yes/no outcome.

Kalshi BTC perpetuals are a separate margin product. The contract has no expiry, tracks BTC price continuously, supports long/short exposure and leverage, and uses funding plus margin/liquidation mechanics. Its price is not a probability.

They therefore support different questions:

- KXBTCD: estimate the probability that a defined BTC event settles yes.
- BTC perpetual: forecast returns, basis, funding, or order-book behavior over a chosen horizon.

## Officially documented facts

- Kalshi exposes perps under the `/margin` REST namespace and a separate margin WebSocket host.
- The documented BTC perpetual ticker is `KXBTCPERP` on the web market page, but code must discover and verify the live ticker instead of assuming it.
- Margin market metadata includes bid, ask, price, volume, 24-hour volume, open interest, reference price, settlement mark, liquidation mark, and leverage estimates.
- Read-only market endpoints include market metadata, full-depth order book, paginated trades, and 1-minute/1-hour/1-day candlesticks.
- Funding endpoints provide estimated and historical rates. Kalshi describes funding as occurring every eight hours.
- The authenticated fee-tier endpoint returns account-specific maker and taker rates as fractions of notional.
- Kalshi's API overview says separate historical-data endpoints are not available for margin, so actual reachable history through trades, candles, and funding must be measured.
- Perpetual execution uses margin and can be liquidated. This remains a material model/economic distinction even though execution is prohibited.

## Preliminary comparison

| Criterion | KXBTCD | Kalshi BTC perpetual | Preselection implication |
| --- | --- | --- | --- |
| Market-data availability | Existing project evidence supports event metadata, trades/candles where available, order books, and settlement-linked outcomes. | Official REST and WebSocket surfaces provide metadata, order book, trades, ticker/marks, candles, and funding. Account rollout may gate access. | Verify both from the same local environment; a documented endpoint is not proof of account access or reliable collection. |
| Historical coverage | The project has already established usable modern-regime KXBTCD history, subject to the current repository evidence. | Product launched in 2026. No separate historical archive API is documented; reachable trades/candles/funding history is unknown until probed. Historical order-book depth exists only if locally collected. | KXBTCD currently has the stronger evidenced historical base. |
| Liquidity | Varies by daily contract and time-to-close; one market's volume can fragment across related strikes/contracts. | One continuous BTC instrument may concentrate activity, but current volume, trade rate, and open interest must be measured. | Do not infer superiority from product type or website headline volume. |
| Spread | Binary prices are bounded from $0 to $1; cents must also be evaluated as probability and payout-relative cost. | Dollar-price ticks and spread should be expressed in dollars and basis points. | Compare normalized and executable spreads, not raw tick counts. |
| Depth | Must measure both sides and fixed-dollar slippage at relevant probability bands and time-to-close. | Full bid/ask book is documented; measure depth within fixed basis-point bands and fixed-notional slippage. | Use matched notionals and several depth bands. |
| Fees | Prediction-event fees depend on the applicable Kalshi schedule/market; verify the exact current rule. | Maker/taker fees are charged on notional on both entry and exit and are account-tier specific. | Query the permitted read-only fee-tier endpoint; never use an example rate as the user's rate. |
| Funding | None. | Longs may pay shorts or vice versa every eight hours; funding can accumulate and must be modeled. | Funding is both a feature and a holding cost. |
| Leverage/liquidation | A fully paid binary contract has bounded contract loss and no futures-margin liquidation. | Margin, leverage, maintenance thresholds, mark prices, and liquidation are core mechanics. | Perps require a substantially different risk and execution model; read-only research does not authorize using leverage. |
| Effective sample size | One settlement supplies roughly one independent label; many intraday quotes from the same contract do not create new outcomes. | Continuous observations are numerous but serially correlated and share one market regime; row count greatly overstates independence. | Report block/autocorrelation-adjusted effective samples, not raw rows. |
| Model suitability | Natural fit for calibrated binary probability, log loss, Brier score, and settlement-aware features. | Natural fit for return, volatility, basis/funding, and microstructure models; binary calibration metrics do not transfer directly. | KXBTCD better matches the project's current event-probability objective; perps may be a reference or a separate research branch. |

## Same-window audit design

1. Call the read-only margin-enabled endpoint and retain only a sanitized enabled/disabled result.
2. Discover the live BTC perpetual ticker and retrieve market metadata, order book, recent trades, candles, historical funding, estimated funding, and account-specific fee tiers where permitted.
3. Collect KXBTCD and BTC-perpetual order books/trades concurrently over identical UTC windows, alongside Coinbase and Kraken.
4. Preserve raw source payloads before transformation while excluding all request headers and secrets.
5. Measure availability, stale intervals, gaps/reconnects, trade/message rates, median and tail spreads, depth bands, and fixed-notional slippage by time of day.
6. Determine earliest and latest retrievable timestamps, missing intervals, pagination behavior, and local order-book history for both products.
7. Estimate effective sample size: market-clustered outcomes for KXBTCD; autocorrelation-aware time blocks and regime splits for perps.
8. Compare net research economics with exact applicable fees. Add funding only to the perpetual branch. Do not simulate orders or fills in this checkpoint.
9. Select KXBTCD, BTC perpetuals, or neither only after predeclared minimum data-quality gates pass.

## Current conclusion

Do not select either branch yet. Based on currently documented evidence, KXBTCD is ahead for historical outcome-based modeling and alignment with the project's calibrated-probability objective. BTC perpetuals are ahead in continuous market-state richness and may have greater concentrated activity, but their actual accessible history, liquidity, spreads, depth, and account-specific costs remain unmeasured. The next action is the paired read-only audit, not model tuning and not execution.

## Official sources reviewed

- Kalshi Perps API overview: https://docs.kalshi.com/margin
- Margin markets: https://docs.kalshi.com/margin-rest/market/get-markets
- Margin order book: https://docs.kalshi.com/margin-rest/market/get-market-orderbook
- Margin candlesticks: https://docs.kalshi.com/margin-rest/market/get-market-candlesticks
- Margin trades: https://docs.kalshi.com/margin-rest/market/get-trades
- Historical funding rates: https://docs.kalshi.com/margin-rest/funding/get-historical-funding-rates
- Funding estimate: https://docs.kalshi.com/margin-rest/funding/get-funding-rate-estimate
- Account-specific fee tiers: https://docs.kalshi.com/margin-rest/fees/get-fee-tiers
- Perpetual product mechanics and risks: https://help.kalshi.com/en/articles/14679970-what-are-perpetual-futures

<!-- PRESELECTION_GATE_RESULT_20260814 -->
## Gate result - 2026-08-14

**Status: PASS for architecture selection; execution remains out of scope.**

### Selection

Proceed with a **shared BTC-state research layer with separate product heads**.

1. KXBTCD is the primary validation/modeling head.
2. KXBTCPERP is retained as a secondary read-only return/volatility/microstructure head.
3. No joint multitask model is approved yet.
4. No execution authorization changes.

### Why

- KXBTCD: at least 4,000 saved settled events, 172 UTC day blocks, 25 week blocks, broader labeled regime coverage, simpler binary settlement target.
- KXBTCPERP: materially tighter continuous book and attractive live microstructure, but only 71 daily history units in the current reachable audit and additional funding/margin/liquidation complexity.
- Same-window evidence: 60 paired cycles, both products continuously two-sided for selected states, balanced REST request order.
- Timing limitation: local wall-clock offset prevents sub-second cross-feed lead/lag conclusions.

### Required next gate

Before any complex or execution-oriented strategy work:

- define the shared BTC-state feature contract;
- predeclare new chronological evaluation splits;
- validate KXBTCD and KXBTCPERP heads separately;
- maintain a fail-closed clock-health policy;
- keep execution prohibited until the explicit risk-policy gates are met.
