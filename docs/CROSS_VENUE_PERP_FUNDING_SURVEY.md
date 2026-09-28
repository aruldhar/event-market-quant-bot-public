# Cross-Venue Perpetual Funding — Survey and Logger

Last updated: 2026-09-28. Status: **data collection, no capital committed, nothing established.**

A delta-neutral carry hypothesis: hold a perpetual long on a venue with low or negative funding
and an equal-notional short on a venue with high funding, collecting the differential. This is
a carry trade with a mechanical cause rather than a statistical pattern, which is what makes it
worth measuring after eleven statistical directions closed.

Logger: `scripts/kalshi_research/fund.py`, five-minute polls to `/data/funding.jsonl`.

## Venue reachability from us-east-1 — verified 2026-09-27

| venue | status | notes |
|---|---|---|
| OKX | works | best feed: exposes `premium`, `interestRate` and `fundingRate` **separately** |
| Hyperliquid | works | public `info` endpoint, no auth |
| Kraken Futures | works | `markPrice`, `bid`, `ask`, sizes, `openInterest` |
| Binance | **HTTP 451** | geo-blocked, off the table |
| Coinbase Intl | instrument metadata only | not available to US retail |
| **Kalshi perps** | **unreachable** | see below |

## The Kalshi leg is currently unmeasurable

`KXBTCPERP`, `KXETHPERP`, `KXSOLPERP`, `KXXRPPERP` and `KXDOGEPERP` all resolve at
`/series/{ticker}` with `fee_type: margin_market_maker_program_fees` and `fee_multiplier: 0`,
but they are absent from `/series?limit=1000` and **every markets and events endpoint returns
empty**. Perps data is not on `trade-api/v2`.

This matters because a third-party aggregator reported Kalshi BTC funding at **0.0%** against a
+4.1% cross-venue average, and that number cannot currently be reproduced from the API. It may
be a real zero or an absent feed. The logger re-probes the endpoints every cycle so we learn
the moment they start returning markets.

Kalshi's published perps mechanics, for when they do: funding every 8 hours at 00:00, 08:00 and
16:00 ET, computed from a TWAP of 480 one-minute premiums against a CF Benchmarks index,
clamped to +/-2% per interval, with any rate below 0.01% forced to zero. Notably it is a
**premium component only** — no interest-rate term — which is the structural difference from
the Binance-family formula. Minimum position is about $8 (against ~$80 on Binance and ~$800 on
Coinbase's US product), maximum leverage about 5.9x on BTC, and margin cash earns 3.25%.

## The observed structural payer is Hyperliquid, not Kalshi

Snapshot 2026-09-27:

- **Hyperliquid funding is 0.0000125 for both BTC and ETH — identical — while its premium is
  negative on both** (-0.0002 and -0.000033). Funding is hourly, so
  `0.0000125 x 24 x 365 = 10.95% annualised`. That is **pinned at the interest-rate floor**,
  paying shorts about 11%/yr even when the perp trades below spot.
- OKX, which exposes `interestRate: 0.0001` and `premium` separately, computes to
  **-1.7%/yr on BTC** and **+4.6%/yr on ETH**.

Gross differential on BTC that day: **~12.7% annualised.** This reframes the original
hypothesis — the durable gap is Hyperliquid's floor against everyone else's premium-driven
rate, not a Kalshi-versus-world story.

Kraken's `fundingRate` (0.17283 on BTC against an 84,561 index) is in absolute units that were
**not** verified, so the logger stores the raw value plus both candidate normalisations rather
than guessing.

## The question the logger answers

**Does Hyperliquid's funding stay pinned at 0.0000125 while its premium moves?**

If it does, shorts there collect ~11%/yr mechanically and the differential against OKX is a
durable carry. If it tracks premium and drifts, the 12.7% was a snapshot and this closes like
the rest. Roughly two weeks of five-minute data answers it.

## What must be settled before any capital

1. **Legal access.** Hyperliquid pays the most and is the least clearly available to a US
   person. Coinbase International is not open to US retail. The realistic pairing may be Kalshi
   against Kraken's US-regulated futures arm at a smaller differential. **If no high-funding
   venue is legally accessible, the lane closes on paperwork rather than economics — so check
   this first, not last.**
2. **Cross-venue margin management.** Long on one venue and short on another means a sharp move
   gains on one leg and loses on the other, and the losing leg can liquidate while the winning
   leg's profit sits stranded elsewhere. These trades die from margin calls, not from the
   thesis being wrong.
3. **Persistence.** One snapshot is not a rate.
4. **Fees and spreads on both legs**, which the logger captures alongside funding.

## Scale, stated plainly

At a 5.9% annualised differential through an accessible venue, net of fees, the return is
roughly 4-5%. On $5,000 that is about $20 a month. This is worth running as a real system that
forces cross-venue execution and margin management to be solved with live money at stake — not
as income.

## Context: the usual spot-versus-perp funding trade is in an adverse regime

BTC perpetual funding has been **negative through most of 2026**, the longest sustained
negative streak since November 2022, reaching -0.005% on the seven-day average in April. The
standard long-spot / short-perp carry therefore *pays* rather than collects, and the inverted
version is the side that was destroyed on 2026-08-20 in $1.74bn of short liquidations. The
cross-venue trade documented here is a different structure: it needs only the **difference**
between venues to be non-zero, not the absolute level to be positive.
