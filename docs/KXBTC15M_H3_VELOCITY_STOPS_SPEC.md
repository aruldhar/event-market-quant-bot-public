# KXBTC15M H3 causal multihorizon velocity-stop specification

## Research status

This is an adaptive hypothesis-generation diagnostic across the original 96
development markets and the permanently opened 26-market partition. All 122
markets are development evidence. The result cannot validate or repair H3 and
must not be described as a new holdout evaluation.

The command is public, local, and read-only. It makes no HTTP request and uses
no authentication, external BTC feed, demo order, or real order.

## Baseline reproduction

Before velocity results are accepted, the command reproduces:

- the frozen first causal-native 90%-to-below-98% entry during 4-to-5 minutes;
- one-second delayed, full-depth, fee-aware, $100-capped entry;
- the protected 50%-of-maximum target;
- the original ten-second preclose fallback;
- 96 development markets with 57 entries and approximately $2.32 mean P&L;
- the saved opened-holdout scenario rows market by market;
- 26 opened markets, 14 entries, approximately -$46.55 total P&L, and one
  full-capital loss.

Any mismatch stops the command.

## Executable-P&L velocity

At every causally received native response after entry, the command attempts a
full-position sale through archived favored-side bid depth and subtracts the
entry cash outflow. A velocity mark exists only when the entire position is
executable.

For lookback `W` and current time `t`, the reference is the latest earlier full
mark whose timestamp is at or before `t - W`. No interpolation or future mark
is allowed. Actual elapsed time is used:

`adverse_velocity = (reference_pnl - current_pnl) / elapsed_seconds`

Positive values mean P&L is deteriorating. A velocity stop requires both:

- adverse velocity at or above its threshold; and
- current executable P&L at or below its loss floor.

## Bounded surface

- Lookbacks: 5, 10, 20, and 30 seconds.
- Adverse rates: $0.50, $0.75, and $1.00 per second.
- Current loss floors: -$10 and -$15.
- Fallback modes: original ten-second fallback or fixed 90-second no-target
  fallback.

The two fixed comparators are original H3 and the simple 90-second exit. This
creates 48 velocity policies plus two comparators.

The protected target has priority at a shared observation. A risk signal waits
one second and then progressively sells all available contracts until flat or
settlement. The velocity-plus-90 mode gives velocity priority when both signals
occur simultaneously.

## Descriptive path analysis

For each filled market and horizon, the command preserves every calculated
velocity and summarizes each market's maximum adverse velocity within:

- 0-to-below-30 seconds after entry;
- 30-to-below-60 seconds after entry;
- 60 seconds or more after entry.

Winner medians, winner 95th percentiles, winner maxima, the known loser maximum,
and the number of winners matching or exceeding the loser are reported. With
only one loser, these are discrimination diagnostics rather than correlation or
classification estimates.

## Evidence and robustness screen

A basic velocity row must:

- stop the known loser through velocity, not merely the 90-second fallback;
- save at least $25 on baseline-losing entries;
- improve combined P&L versus original H3;
- keep gross opportunity cost on baseline winners at no more than 50% of loser
  savings;
- create zero full-capital losses;
- fully liquidate every signaled position.

A robust row must additionally have at least one passing adjacent parameter
neighbor under the same fallback mode. An adjacent neighbor changes exactly one
of lookback, rate, or loss floor by one grid step.

No rule is selected automatically. A broad robust region may motivate one
multiscale or staged H3 v2 candidate. That candidate must be frozen before a
new chronological confirmation sample is evaluated.
