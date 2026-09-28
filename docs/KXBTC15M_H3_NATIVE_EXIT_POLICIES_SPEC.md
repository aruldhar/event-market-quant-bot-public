# KXBTC15M H3 Causal-Native Exit-Policy Reassessment

## Question

After native response-by-response monitoring changed H3's development entry set
from 52 legacy-clock entries to 57 causal entries, which bounded cash-exit rule
performs best on the updated, otherwise frozen strategy?

## Frozen entry mechanics

- Same 96 eligible development markets.
- Separate 26-market holdout remains sealed.
- Clock: raw HTTP response receipt time.
- Monitoring: every archived response.
- Entry window: more than 4 minutes through 5 minutes remaining.
- Favored midpoint: at least 90% and below 98%.
- First qualifying state only.
- Entry mode: unprotected after a one-second delay.
- At most $100 using whole contracts, full archived depth, and conservative fees.
- No external BTC data, authentication, API keys, or orders.

## Matched exit policies

All target policies monitor every causal response after the identical entry.
When a full-depth sale hypothetically meets a target, execution waits at least
one second. The sale completes only if the delayed full-position result still
meets the target after fees; otherwise the signal is rejected and monitoring
continues.

| Policy | Target | Fallback |
|---|---:|---|
| `protected_fixed_1usd` | $1 net P&L | Cash exit beginning 10s before close |
| `protected_25pct_max` | 25% of maximum settlement profit | Same |
| `protected_50pct_max` | 50% of maximum settlement profit | Same |
| `protected_75pct_max` | 75% of maximum settlement profit | Same |
| `hold_to_settlement` | None | Settlement |

Maximum settlement profit is contracts minus total entry cash outflow. The
hold-to-settlement row is a risk/upside counterfactual, not a cash-out rule.

## Primary comparison

Mean realized P&L per all 96 eligible markets, assigning $0 to the 39 markets
with no H3 entry. Every row is paired market-by-market against protected 50%.
Report a deterministic paired-bootstrap 95% interval.

Secondary diagnostics include P&L per filled entry, target/fallback/settlement
rates, favored-side outcome, full-capital-loss rate, exposure duration, 5% tail,
and worst P&L.

## Required gates

1. Exactly 96 development markets and matching finalized development outcomes.
2. Exactly 57 causal-native entries.
3. The protected-50% result exactly reproduces the accepted native frequency
   result for status, trigger, fill, decision, entry, exit reason, and P&L on
   every market.
4. All policies use the identical entry context within each market.
5. Output explicitly records no holdout, external BTC input, authentication, or
   orders.

## Interpretation boundary

This is an adaptive development reassessment required by the clock and entry-set
change. It can choose a coherent cash-out candidate before prospective or
sealed-holdout evaluation, but its best row is not an unbiased estimate of
future return and cannot guarantee profitability.
