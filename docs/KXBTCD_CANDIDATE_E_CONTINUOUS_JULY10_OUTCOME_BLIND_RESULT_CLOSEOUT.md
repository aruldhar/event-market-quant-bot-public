# KXBTCD Candidate-E Continuous July 10 Outcome-Blind Result Closeout

## Checkpoint 21N-V

Strategy: `kxbtcd_candidate_e_continuous_convergence_reentry_v1`

Final classification:

`NON_EVALUABLE_STRUCTURAL_UNIVERSE_LIQUIDITY_MISMATCH`

The frozen outcome-blind continuous path materialized successfully under exact
implementation fingerprint `cf93bbdd7704ae46954feba8ce73e15a734f117a1791837d87a130e50a15764f` and source-binding fingerprint
`8cf8ead70da5f56def1a0d67619b2cda75316e6345383e8ebdcf79f9c4cf62b7`.

Path artifact SHA-256:

`b46281f5b7877c26b2b310e874f0f04aa7679ba02e9876800c6e2af1b1f195bf`

## Frozen strategy result

- 4 independent July 10 events.
- 60 policy scenarios = 4 events × 5 frozen entry thresholds × 3 frozen latencies.
- Decision clocks: 706 / 1,122 / 1,077 / 605.
- Entry attempts: **0**.
- Filled trades: **0**.
- Fully closed round trips: **0**.
- Terminal state: `NO_FILLED_ENTRY` in all 60 scenarios.
- Settlement outcomes remained closed.
- Settlement-dependent P&L was not calculated.

This is not an edge, fee, latency, liquidation, or re-entry failure because the
strategy never reached those stages.

## Entry-gate diagnosis

Across 17,550 structural-market evaluations:

- `INVALID_TWO_SIDED_BOOK`: 13,436
- `KALSHI_SOURCE_UNAVAILABLE`: 4,114
- `EVALUABLE`: **0**

Therefore Candidate E never reached probability/edge evaluation on the frozen
q10/q30/q50/q70/q90 execution universe.

## Full-ladder explanatory diagnostic

The same owned July 10 replay contains 623 total KXBTCD tickers.

- 45 tickers had at least one valid two-sided state.
- Per event: 7 / 14 / 12 / 12.
- Full-ladder valid two-sided reconstructed states: 1,060,685.
- Frozen structural tickers with any valid two-sided state: **0 / 20**.

Thus the replay/source is not generally devoid of two-sided microstructure. The
frozen structural market selection is misaligned with where July 10 liquidity
appeared.

## Rank geometry

The 45 two-sided tickers were not small rank perturbations around the frozen
roles:

- within 2 ranks: 1 / 45
- within 3 ranks: 2 / 45
- within 5 ranks: 5 / 45
- within 10 ranks: 17 / 45
- maximum displacement: 18 ranks

Nearest-role counts were q10=7, q30=0, q50=20, q70=18, q90=0.

Therefore a small fixed-rank structural neighborhood is not supported by this
four-event exploratory evidence.

## Consequence

Continuous v1 is permanently closed as non-evaluable. Do not tune its
thresholds, open settlement outcomes for it, or silently replace its frozen
market universe.

Checkpoint 21N-W should remain outcome-blind and first determine whether the
moving two-sided liquidity band is causally organized around BTC spot / ATM.
Only after that diagnostic should a new liquidity-aware market-universe strategy
version be predeclared.
