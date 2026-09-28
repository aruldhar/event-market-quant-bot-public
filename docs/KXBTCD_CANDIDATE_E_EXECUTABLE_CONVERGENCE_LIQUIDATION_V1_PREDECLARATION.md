# Candidate-E Executable Convergence Liquidation v1 — Exact Predeclaration

## Checkpoint
**Checkpoint 21N-Q — Candidate-E Executable Entry + Liquidation Strategy Exact Predeclaration**

## Status
Outcome-blind methodology freeze.

Strategy ID: `kxbtcd_candidate_e_executable_convergence_liquidation_v1`

Predeclaration fingerprint: `61ede2de623d2ffca6b303895a860fa78de40ea36f0da7fe6b57835ac98d52f6`

Parent 21N-P receipt: `21bb2bb6d38295411aa8381dc176e5841072e422`

No July 10 strategy outcome or P&L is used to choose any rule below.

## Research question
After frozen Candidate E generates a qualifying entry, can realistic executable liquidation monetize convergence toward Candidate E's **entry-time fair value**, after spread, depth, latency, partial fills, missed fills, and fees, compared with holding the identical realized entry fill to settlement?

The liquidation branch is primary. Hold-to-settlement is the matched control.

## Candidate/model scope
Candidate E remains `kxbtcd_btc_distance_offset_logistic.v1`, Champion-Final fingerprint
`b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`, with
`beta_distance = 0.014939489324405949`.

At an exact anchor:
`q_market = (YES best bid + YES best ask)/2`

`logit(pE) = logit(clip(q_market,0.001,0.999)) + beta_distance * 10000*ln(S_t/K)`

YES fair value is `pE`; NO fair value is `1-pE`.

Candidate E is not refit, recalibrated, or dynamically recomputed after entry to move the exit target.

## Allowed strikes and anchors
The 623-contract ladder may be used only to identify the exact five frozen structural roles using
`numeric_strike_nearest_rank_half_up`:

`q10, q30, q50, q70, q90`

Only those five strikes may generate decisions.

Anchors, in order:

`T-55, T-50, T-45, T-40, T-35, T-30`

No arbitrary strike mining, neighboring-strike substitution, interpolation, nearest-time substitution, carry-forward, or cross-strike proxy is allowed.

## Entry signal
A state requires a valid, uncrossed, two-sided reconstructed book and at least `1.00` contract displayed at the decision-time executable price level.

YES purchase price = reconstructed YES best ask.

NO purchase price = `1 - reconstructed YES best bid`.

Planned size = `1.00 contract`.

Signal trade fee:
`ceil_to_0.0001(0.07 * 1.00 * P * (1-P))`

Signal net edge:
`side_fair_probability - purchase_price - signal_trade_fee`

Parallel frozen edge-margin policies:

`0c, 1c, 2c, 3c, 5c`

Qualification:
`signal_net_edge >= threshold`

For each threshold independently: scan 55m toward 30m, stop at the first qualifying anchor, choose the largest edge, then break an exact tie by ticker ascending and YES before NO. Maximum one entry per event per threshold.

The four-event sandbox may not select a winning threshold.

## Entry execution
Latency scenarios:

`0 ms, 500 ms, 1000 ms`

One scenario uses the same latency on entry and exit.

Counterfactual entry = `1.00-contract IOC limit buy`.

Limit = decision-time executable ask.

Arrival = `decision_time + latency`.

The complete decision-to-arrival interval must remain inside the same verified replay segment.

At arrival, consume asks best-to-worst only at prices no worse than the limit.

- 1.00 = full fill
- 0 < fill < 1.00 = partial fill
- 0 = missed fill
- price improvement allowed
- worsening beyond limit prohibited
- unfilled IOC remainder canceled

## Primary liquidation rule
When any entry quantity fills, freeze:

`target fair value per contract = entry-time Candidate-E side fair probability`

Example: if the selected YES fair value is 0.72, the target remains 0.72. It does not move later with BTC or market changes.

Monitor every reconstructed post-entry book state in chronological order.

YES liquidation uses the YES bid ladder.

NO liquidation uses the equivalent NO bid ladder:
`NO bid = 1 - YES ask`, with the same quantities.

At each verified state, hypothetically liquidate the **entire open quantity** through bid depth using the exact fee/cash policy.

The first trigger occurs only when:

1. enough bid depth exists to liquidate the entire open quantity immediately; and
2. `hypothetical net liquidation cash proceeds >= entry-time fair value * open quantity`.

The exit limit is the worst bid price consumed by that trigger-time hypothetical full liquidation.

At `trigger_time + latency`, attempt exactly one IOC limit sell.

The full trigger-to-arrival interval must remain inside the same verified segment.

At arrival, consume bids best-to-worst only at prices at or above the frozen exit limit.

- full fill closes the position
- partial fill closes that quantity and the remainder settles
- zero fill means the entire quantity settles
- there is no second liquidation attempt
- there is no forced exit, stop loss, or take-profit grid

A source-invalid trigger-to-arrival interval is not called a missed exit; the liquidation branch is source-unavailable.

## Continuous-path rule
From realized entry arrival until either a valid trigger occurs or the event closes, the path must remain continuously replay-verified.

A replay boundary before the trigger makes the liquidation branch source-unavailable because the target could have been reached inside the missing interval.

If no trigger occurs and the verified path remains continuous through close, the position settles.

The hold control does not need post-entry market continuity because it never uses the path.

## Matched hold control
For every realized entry fill, hold uses the exact same event, threshold, latency, ticker, side, decision time, fill quantity, fill prices, and entry fee/cash rounding.

Only the post-entry liquidation behavior differs.

## Fee and fixed-point accounting
The official Kalshi fee schedule effective **2026-07-07** gives the general immediately matched event-contract fee:

`fee = round up(M * 0.07 * C * P * (1-P))`

KXBTCD is not listed among the non-standard fee series, so `M=1` is used. The schedule states there is no settlement fee.

Official fixed-point documentation requires exact prices, 0.01-contract quantity granularity, trade-fee rounding to `0.0001`, cent-aligned cash rounding, and the per-order rounding accumulator/rebate mechanism.

All accounting must use `Decimal`.

Predexon reconstructs aggregate depth by price level but not the individual resting-order partition inside each level. The deterministic historical assumption is **one synthetic fill per consumed price level**, with the rounding accumulator carried across fills of the same IOC order. This fill-partition limitation must be reported as execution uncertainty.

Official references:
- https://kalshi.com/docs/kalshi-fee-schedule.pdf
- https://docs.kalshi.com/getting_started/fixed_point_migration
- https://docs.kalshi.com/getting_started/fee_rounding

## Model uncertainty
No new uncertainty/reliability model is fit on July 10.

The `0c/1c/2c/3c/5c` edge margins are deterministic margin-of-safety sensitivity against Candidate-E valuation error, not statistical confidence intervals.

All five are reported. None is selected as a winner from four events.

## Evaluation boundary
Required later outputs include full/partial/missed entry counts, entry VWAP and fees, trigger count, full/partial/missed exits, source-unavailable exit paths, time to trigger, exit VWAP and fees, settlement fallback quantity, liquidation P&L, matched-hold P&L, and liquidation-minus-hold by threshold/latency/event/side/role/anchor.

Primary paired comparison uses only entries for which both branches are evaluable.

Statistical unit = hourly event. `N=4`.

Therefore this sandbox has **no advancement gate** and cannot establish profitability or generalization.

No threshold, latency, side, role, TTC subset, sizing rule, or exit variation may be selected from July 10 and then called validated.

## Safety
This checkpoint remains read-only and historical-counterfactual only. It authorizes no order, paper broker, demo execution, real-money execution, transfer, new Predexon purchase, C1/C2/C3 strategy-economics access, or protected-reserve access.

No July 10 strategy outcome or P&L may be opened until this predeclaration is safely committed and pushed.
