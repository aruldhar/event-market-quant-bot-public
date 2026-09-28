# KXBTC15M full-market dynamics census

Status: frozen exploratory development analysis.

## Purpose

Determine how volatility, executable gross recovery, and bounded pooling mechanics vary across the entire 15-minute KXBTC15M market. The user's first-five-minute observation is evaluated, not assumed.

## Evidence boundary

- Frozen markets 1–100 only; 96 pass the existing primary quality gate.
- Final 26-market holdout remains sealed.
- No outcomes are read.
- Entry anchors use a uniform five-second grid across all 15 elapsed minutes. The first observation at or after each grid point must arrive within two seconds.
- Exact observation time and exact seconds remaining are retained.
- Every later recorded quote, including half-second observations, may establish a recovery.
- Equal-contract pooled averages are descriptive counterfactuals using displayed top-of-book prices. They exclude fees, depth, latency, and material-size slippage.

## Measurements

1. Five-second absolute YES midpoint movement by elapsed minute.
2. At every non-tied grid anchor, select the side with the lower executable ask.
3. Report whether a later executable bid exceeds the entry ask within 30, 60, 120 seconds and before close.
4. Stratify by exact time remaining, elapsed minute, first-five versus later, and entry-ask bands spanning the full lower-side range.
5. For 2¢, 5¢, and 10¢ declines from entry, evaluate equal-contract two- and three-tranche pooled averages and later gross recovery before close.
6. Because anchors overlap, primary displayed rates weight each contributing market equally and use a 2,000-replicate market-level bootstrap interval. Raw anchor-weighted counts remain descriptive.
7. Report a joint time-phase × entry-price-band surface so price convergence near close is not mistaken for an independent clock effect.

## Interpretation

This is an opportunity census, not a profitability backtest. Its overlapping anchors are exploratory and highly dependent within market. It may identify a small bounded rule family for the next full-depth, fee-aware simulation, but it cannot support holdout inspection or a trading claim by itself.
