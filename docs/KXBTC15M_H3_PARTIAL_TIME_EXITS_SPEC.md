# KXBTC15M H3 bounded partial time-exit specification

## Research status

This is an adaptive risk-frontier diagnostic over the original 96 development
markets and the permanently opened 26-market partition. All 122 markets are
development evidence. It cannot validate or repair H3, and it must not be
described as another holdout test.

The command is public, local, and read-only. It makes no HTTP request and uses
no authentication, external BTC feed, demo order, or real order.

## Required reproduction

Before partial-exit results are accepted, the command reproduces:

- the frozen first causal-native 90%-to-below-98% entry during 4-to-5 minutes;
- one-second delayed, full-depth, fee-aware, $100-capped entry;
- the protected 50%-of-maximum whole-position target;
- the original ten-second preclose fallback;
- 57 entries and approximately $2.32 mean P&L on the original 96 markets;
- the saved opened-holdout scenarios market by market;
- 14 opened-partition entries, approximately -$46.55 total P&L, and one
  full-capital loss; and
- the full 90-second cash exit with approximately $167.18 combined P&L and no
  full-capital loss.

Any mismatch stops the command.

## Bounded surface

The twelve candidate policies are the Cartesian product of:

- time remaining: 75, 90, and 105 seconds; and
- whole-contract position fraction: 25%, 50%, 75%, and 100%.

The original H3 policy is the thirteenth row and fixed comparator. The 100% at
90-second cell is the previously accepted simple risk comparator. There is no
search over every second or arbitrary percentage.

## Causal execution

The protected target has priority if it and the timeout occur on the same
native observation. If no protected full sale executes first, the timeout
requests at least the declared fraction of the entry quantity, rounded up to a
whole contract and capped at the total position.

Execution waits one second, crosses archived bid depth, includes separately
rounded fees, and repeats delayed attempts for an unfilled part of the declared
tranche. No future snapshot is used at a decision.

## Remainder and target accounting

After a partial timeout sale, the remaining position continues monitoring. A
later target is accepted only when:

`timeout net inflow + delayed net inflow from all remaining contracts - original cash outflow >= original target amount`

Thus a partial sale at a loss must be repaid before the trade is called a
protected target exit. The target is not reset on the smaller position and
realized losses are never ignored.

If the cumulative target is not filled, the original ten-second preclose cash
fallback is attempted for the entire remainder. If that full sale is
unavailable, the remainder settles. Positions never overlap and there is no
re-entry, runner, or compounding.

## Reporting and interpretation

Every row reports total P&L, paired changes versus original H3 and the full
90-second rule, target recovery, loser savings, gross winner opportunity cost,
full-capital losses, fifth-percentile P&L, worst P&L, tranche completion, and
residual settlement.

The report also marks the descriptive two-dimensional Pareto frontier. A policy
is non-dominated when no tested policy has both higher combined P&L and an
equal-or-better worst filled-trade P&L.

The frontier is not an automatic selection rule. It contains only one baseline
loser and is subject to adaptive multiple-comparison bias. Any selected H3 v2
rule requires a newly collected chronological confirmation sample.
