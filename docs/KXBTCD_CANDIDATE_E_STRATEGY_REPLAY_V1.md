# KXBTCD Candidate-E Strategy Replay v1

## Checkpoint 21K-A — baseline policy freeze

This checkpoint freezes the first historical strategy/economics baseline before
strategy-specific historical execution data are backfilled and before any strategy
P&L is calculated.

The purpose is not to prove profitability. It is to test whether the previously
validated Candidate-E forecasting signal can survive a coarse, causal, minute-level
entry/exit replay after spread, historical fees, missed/partial-fill proxies, and
model uncertainty are considered.

## Primary evidence scope

The primary strategy replay uses only predictions that were genuinely out-of-sample
or rolling-origin when they were created:

- H1 Distance-candidate OOF: 1,070 events / 31,656 rows
- H2: 750 events / 22,354 rows
- H3: 750 events / 22,409 rows
- C1: 500 events / 14,887 rows
- C2: 500 events / 14,007 rows
- C3: 500 events / 13,549 rows
- total: 4,070 events / 118,862 prediction rows

The remaining 4,676-event historical reserve stays untouched. Champion-Final may
later be replayed as an exploratory downstream model, but it is not relabeled as
fresh OOS strategy evidence on events used to fit it.

## Baseline entry rule

Evaluate anchors in causal order: 55m, 50m, 45m, 40m, 35m, 30m TTC.
At each anchor evaluate q10/q30/q50/q70/q90 and both YES and NO.

For YES:

`signal price = YES ask`

For NO:

`signal price = 1 - YES bid`

For each side:

`net edge = model side probability - signal price - exact signal-time fee per contract`

The primary threshold is 4 cents net edge per contract. 3-cent and 5-cent
thresholds are frozen sensitivity checks and all must be reported; the best one
may not be selected post hoc.

If multiple choices qualify at one anchor, choose the largest edge, then lower
spread, then market ticker, then YES before NO. There is at most one entry per
event. Size is fixed at 10 contracts. No compounding, averaging down, loss chasing,
or side switching is allowed.

## Coarse historical execution assumptions

The signal cannot fill in the same minute used to create it. Earliest fill is the
next one-minute interval.

Entry may be no more than 1 cent worse than the signal executable price. A worse
price is a missed entry, not unlimited slippage.

Base replay uses next-minute executable quote closes. Conservative replay uses the
adverse next-minute one-minute quote extreme and caps filled quantity at 10% of
reported minute volume. This volume rule is intentionally labeled a proxy: minute
volume is not queue position or full depth.

Missing executable quotes are never imputed.

## Exit rule

The primary strategy attempts to capture 50% of the initial model surplus.

`initial surplus = model side probability - all-in actual entry cost per contract`

`target net liquidation value = all-in entry cost + 0.50 * initial surplus`

When an observed after-fee executable side bid reaches the target, an exit is
attempted in the next one-minute interval. It fills only if the after-fee liquidation
value still reaches the target; otherwise it is a missed target exit and monitoring
continues.

If the target is not filled, attempt forced liquidation using the first valid
executable quote in the 5m, 4m, 3m, 2m, 1m TTC window. If no force-exit quote exists,
the still-owned contracts settle and the event is explicitly tagged
`forced_exit_unavailable_settlement_fallback`.

The exact same entries are also reported under a hold-to-settlement benchmark. That
benchmark is a comparison only and may not replace the primary cash-out policy after
results are known.

## Fees

The replay must bind each transaction to the KXBTCD fee type and multiplier effective
at that transaction time using official Kalshi series metadata and historical series
fee changes. Official rounding rules must be reproduced. Unresolved fee metadata
fails closed for the affected transaction.

## Uncertainty stress

A diagnostic stress shrinks Candidate E's adjustment toward the market midpoint:

`p_stress = q_market + 0.75 * (candidate_probability - q_market)`

This stress cannot select, tune, or refit the model.

## Advancement gate

The primary 4-cent strategy under conservative execution assumptions requires:

- at least 200 conservative filled entries;
- positive aggregate after-fee P&L;
- positive aggregate H2-through-C3 after-fee P&L; and
- positive results in at least 3 of H2, H3, C1, C2, C3.

Passing this research gate does not authorize demo execution.

## Future strategy research

Strategy v1 is intentionally only a baseline. Additional strategies may be researched
regardless of its outcome, but each must be separately versioned. Strategy v1 may not
be silently repaired after its P&L is seen. Once v1 economics are inspected, this
4,070-event pool is strategy-development evidence; later variants on the same pool
cannot honestly claim fresh strategy validation.

## Safety state

This checkpoint performs no network requests, model fitting, strategy backfill,
paper broker behavior, demo execution, real-money execution, or order placement.
