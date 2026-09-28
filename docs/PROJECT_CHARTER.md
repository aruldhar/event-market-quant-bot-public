# Project Charter

## Project name

Event-Market Quant Bot

## Purpose

Build an explainable, testable, and auditable quantitative trading research system. The current research scope studies Kalshi Bitcoin markets using read-only Kalshi market data together with public external Bitcoin reference feeds. The system should determine whether any apparent edge survives realistic fees, spreads, slippage, available depth, latency, partial fills, missed fills, funding where applicable, and model uncertainty.

## Primary learning goals

1. Understand event-contract settlement, perpetual-market mechanics, and order-book behavior.
2. Build reliable real-time and historical data pipelines.
3. Develop calibrated state and price-distribution models rather than relying only on one-shot terminal predictions.
4. Evaluate product-specific valuation and entry/exit policies with chronological out-of-sample testing.
5. Implement realistic paper execution and risk controls only after the applicable future phase gate is passed and separately authorized.
6. Learn professional software engineering, documentation, and version control.

## Current research scope

- Venue: Kalshi
- Asset family: Bitcoin-related markets
- Kalshi products under comparison: KXBTCD daily Bitcoin event contracts and Kalshi BTC perpetual futures market data
- External reference feeds: public Coinbase and Kraken Bitcoin market data
- Mode: read-only collection and offline research
- Kalshi access: public endpoints plus authenticated read-only endpoints using the existing locally configured API credentials when required and supported by the account/key
- Language: Python
- Environment: Windows, VS Code, local virtual environment
- Repository: private GitHub repository

## Credential boundary

- Credentials must remain environment-managed in an ignored local `.env` or secure secret store.
- API keys, private keys, signatures, authorization headers, and other secrets must never be logged, written to research artifacts, committed to Git, or pasted into chat.
- Authenticated access in the current phase is limited to read-only collection and metadata needed for the authorized research scope.

## Explicit non-goals for the current phase

- No real-money order creation or execution
- No demo order creation or execution
- No paper execution
- No order cancellation or automated order management
- No portfolio transfers
- No leveraged or margined positions
- No production trading
- No claim of guaranteed profitability
- No expansion to additional assets or venues before the Bitcoin research path is evidence-based and stable

Read-only observation of BTC perpetual market data is permitted even though perpetual futures are leveraged instruments. This does not authorize opening, managing, or closing a perpetual position.

## Definition of success for research

Success is not merely a positive backtest. A strategy must demonstrate:

- Positive net expected value after realistic costs
- Calibrated probability or return-distribution estimates appropriate to the product
- Chronological out-of-sample performance
- Robustness across multiple market conditions
- Realistic fill assumptions
- Controlled drawdowns and exposure in simulation before any later execution discussion
- Reproducible results
- Stable demo execution only after future gates are passed and demo execution is separately authorized

## Operating principle

Collect data broadly when useful, but trade narrowly. Every expansion in venue, asset, product, or strategy requires its own evidence and risk limits. During the current phase, all live integrations remain read-only.
