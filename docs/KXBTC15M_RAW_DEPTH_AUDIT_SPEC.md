# KXBTC15M raw-depth audit specification

Status: frozen development-only feasibility gate.

## Question

Can the existing KXBTC15M raw archives reconstruct executable price levels and quantities well enough to support a bounded pooled-position simulator?

This is not a profitability test and does not select a strategy.

## Frozen scope

- Development partition only: chronological markets 1–100, ending at `KXBTC15M-26AUG121430-30`.
- Primary quality rule: identical to the H1 development analysis (96 eligible markets).
- Episode linkage: all 217 frozen H1 development entries.
- Holdout: the final 26 markets are sealed; their raw archives and outcomes must not be opened.
- Outcomes: not read.

## Required checks

For each eligible development market:

1. Resolve every manifest-declared raw archive from the repository root. A recorder session crossing a UTC date boundary may correctly have multiple files.
2. Verify each archive's SHA-256 and record count, then combine records in request-time order.
3. Verify the combined raw request IDs exactly match the derived CSV sequence.
4. Parse every `raw_http_exchange.v1` body and validate the fixed-point order-book levels.
5. Reconstruct YES/NO best bids and complementary asks and match all four derived quotes exactly.
6. At every H1 entry, record the number of executable buy-ask and sell-bid levels and the best-level quantities.

## Pass condition

PASS requires all 96 eligible markets, every derived quote row in those markets, and all 217 H1 entries to reconstruct without ambiguity. It also requires zero holdout raw-archive reads.

## What PASS authorizes

PASS authorizes the next offline research component only: preregister and simulate one bounded H1 ladder with fixed maximum tranches, exposure, and time stop; depth-aware fills; pooled cost; fees; and depth-aware liquidation.

PASS does not authorize live, demo, paper, or production orders. It does not authorize unbounded averaging or adding until profitable.
