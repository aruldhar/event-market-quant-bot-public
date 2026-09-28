# KXBTC15M H3 causal-native path and stop-feasibility specification

## Status and purpose

Adaptive development-only diagnostic. The prior 26-market H3 holdout is open,
failed, prohibited as an input, and must not be reused for threshold selection.

The diagnostic answers two questions using only the original 96 eligible
development markets:

1. Did the 57 eventual protected-target exits rise cleanly, or did they first
   suffer executable drawdowns and recover?
2. How often would simple delayed progressive-loss exits have stopped those
   eventual winners?

It does not select, validate, or authorize H3 v2.

## Frozen baseline reproduction

Before producing any diagnostic result, regenerate the accepted H3 baseline:

- every causal native HTTP response receipt;
- first favored midpoint satisfying `0.90 <= midpoint < 0.98`;
- `240 < seconds_remaining <= 300`;
- one-second unprotected entry delay;
- archived full-depth execution and frozen fees;
- $100 maximum budget;
- protected target at 50% of maximum settlement profit;
- ten-second preclose fallback; and
- one cycle with no re-entry, runner, or compounding.

The analyzer must reproduce 57 filled development entries, mean P&L per
eligible market within one cent of $2.32, 57 protected-target exits, and zero
full-capital losses. Each market must also agree with the independent native
frequency implementation on status, trigger, entry, exit, and P&L.

## Executable path definition

From each entry execution through its baseline protected-target execution,
evaluate every subsequent causal native response. At each response:

- sweep the entire held quantity through the archived bid side;
- include conservative exit fees;
- record full-liquidation P&L only if all contracts are executable;
- otherwise record sellable quantity and fraction without inventing a full
  mark;
- record best bid, average executable bid, time since entry, and time to close.

Per-entry outputs include minimum executable P&L, time to minimum, time from
minimum to target, estimated time underwater, peak-to-trough drawdown, whether
the executable path was nondecreasing, and whether full-position exit depth
ever disappeared.

The pre-target minimum categories are fixed descriptively as: never negative,
0 to -$2, -$2 to -$5, -$5 to -$10, -$10 to -$20, and -$20 or worse.

## Descriptive stop surface

Compare only:

- no stop;
- executable full-position P&L at or below -$2;
- at or below -$5;
- at or below -$10;
- at or below -$15;
- at or below -$20; and
- first loss of full-position liquidation depth.

At every observation, the protected profit target has priority. A loss stop can
signal only when the whole position is executable through observed depth. The
liquidity guard signals when it is not.

After a risk signal:

1. wait one second;
2. sell every contract then available through archived bid depth;
3. observe the next causal response;
4. wait another second and repeat for any remainder; and
5. mark any residual contracts at their actual settlement payout.

This conservative repeated-order model charges fees separately for each
partial execution. It does not assume that displayed liquidity persists or
that missing depth can be filled.

## Interpretation

All 57 development fills ultimately reached the baseline target. Therefore,
every observed stop is a false stop in this sample. The surface measures damage
to ordinary recoveries and execution feasibility; it cannot estimate how often
a stop saves a genuine loser.

Report mean P&L per eligible market with no-trades as $0, market bootstrap
intervals, paired changes from baseline, chronological-segment differences,
profitability, full liquidation after stops, residual settlement, 5% tail, and
worst P&L.

No row is selected. Any H3 v2 rule must be preregistered and developed on newly
collected chronological markets, followed by a separate future holdout. No
external BTC data, authentication, order, or opened-holdout observation is
allowed.
