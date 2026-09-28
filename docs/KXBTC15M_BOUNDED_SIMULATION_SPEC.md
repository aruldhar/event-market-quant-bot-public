# KXBTC15M bounded pooled-reversion simulation specification

Status: frozen before running the development economics simulation.

## Question

Does bounded averaging improve depth- and fee-adjusted liquidation economics
relative to a single buy-in when every policy has the same maximum cash budget?

## Scenario grid

- Development markets only: the 96 already-eligible markets in indices 1–100.
- Holdout markets 101–126 remain sealed.
- One decision anchor per elapsed minute from minute 0 through minute 12.
- Entry side: the side with the lower executable best ask at the decision time.
- Policies: one, two, and three maximum buy-ins.
- Maximum cash budget: $100 per scenario, including entry/addition fees.
- Allocation: $100 / maximum buy-in count per tranche.
- Addition step: same-side ask 5 cents below the first executed ask; for the
  third buy-in, another 5 cents below.
- Quantity: whole contracts only and never more than archived displayed depth.
- Execution delay: first archived snapshot at least one second after each
  decision or trigger.
- Missed additions remain missed if the delayed ask no longer satisfies the
  trigger.
- Exit: first delayed full-depth liquidation producing at least $1 net profit.
- Risk stop: begin full liquidation attempts with 120 seconds remaining.
- If displayed depth never permits full liquidation before close, value the
  residual at the official finalized outcome and label it as settlement fallback.

## Fee model

The collected series evidence says `fee_type=quadratic`, `fee_multiplier=1`,
with zero historical changes. Marketable entry, addition, and exit orders use:

`0.07 × multiplier × contracts × price × (1 − price)`

Each archived price-level fill is rounded up to $0.0001. The total fee for the
hypothetical order is then conservatively rounded up to the non-direct account
balance precision of $0.01. No fee is applied to settlement payout.

## Interpretation

Minute-anchor scenarios overlap and are not simultaneous portfolio trades.
Report P&L per fixed $100 maximum budget, deployed capital, fill utilization,
fees, missed triggers, exit reason, and equal-market-weighted clustered
uncertainty. This development result may select at most one policy for a newly
frozen holdout test; it cannot itself establish out-of-sample profitability.
