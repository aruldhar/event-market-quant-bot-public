# KXBTC15M H3 gated velocity and acceleration-stop specification

## Research status

This is a final bounded adaptive diagnostic over the original 96 development
markets and the permanently opened 26-market partition. All 122 markets are
development evidence. The result cannot validate or repair H3 and cannot be
used to reuse the opened partition as a holdout.

The command is public, local, and read-only. It makes no HTTP request and uses
no authentication, external BTC feed, demo order, or real order.

## Required reproduction

Before candidate evidence is accepted, the command must reproduce:

- the frozen causal-native 4-to-5-minute, 90%-to-below-98% H3 entry;
- one-second delayed full-depth entry, $100 cap, and fees;
- protected 50%-of-maximum target and original ten-second fallback;
- 57 entries and approximately $2.32 mean P&L on the original 96 markets;
- the saved opened-holdout scenarios market by market;
- 14 opened-partition entries, approximately -$46.55 total P&L, and one
  full-capital loss; and
- the fixed 90-second no-target comparator with approximately $167.18 combined
  P&L and zero full-capital losses.

Any mismatch stops the command.

## Causal measurements

Every mark attempts to sell the full position through archived favored-side
bid depth after fees. A measurement exists only when the full position is
executable.

The primary adverse velocity uses the latest causal full-depth mark at or
before the 20-second lookback boundary and divides the P&L decline by actual
elapsed time. Positive values mean deterioration.

Acceleration is represented by a stable change in adverse slope rather than a
raw numerical second derivative. At time `t`:

- recent adverse velocity compares the mark near `t - 10s` with `t`;
- previous adverse velocity compares the mark near `t - 20s` with the mark
  near `t - 10s`; and
- adverse-rate increase is recent adverse velocity minus previous adverse
  velocity.

All references are received before the decision. There is no interpolation or
future observation.

## Bounded candidate surface

Two fixed comparators are retained: original H3 and the simple 90-second
no-target cash exit. The 90-second rule is not combined with fitted candidates.

Twelve age/persistence candidates use:

- entry-age activation: 45 or 60 seconds;
- 20-second adverse velocity: at least $0.50/s or $0.75/s;
- executable P&L: at or below -$15; and
- uninterrupted qualifying observations for 0, 10, or 20 seconds.

Four acceleration candidates use:

- entry-age activation: 45 or 60 seconds;
- 20-second adverse velocity of at least $0.50/s;
- executable P&L at or below -$15;
- the base condition persisting for 10 seconds; and
- adverse 10-second velocity increasing by at least $0.25/s or $0.50/s over
  the preceding 10-second slope.

This is 16 candidates plus two comparators. A nonqualifying full-depth
observation resets persistence. The protected target has priority at a shared
observation. Every risk signal waits one second and progressively liquidates
until flat or settlement.

## Path diagnostic

For each filled market, the command preserves causal per-snapshot values for:

- entry age and seconds remaining;
- executable P&L;
- continuous time nonpositive and below -$5, -$10, and -$15;
- 20-second adverse velocity;
- previous and recent 10-second adverse velocities; and
- the adverse-rate increase.

Winner-versus-loser separation is summarized within 0-to-below-30,
30-to-below-45, 45-to-below-60, and 60-second-plus entry-age phases. With only
one loser, this is descriptive hypothesis generation rather than a classifier
estimate.

## Evidence screen

A basic candidate must stop the known loser, save at least $25, improve total
combined P&L versus original H3, keep gross winner opportunity cost to no more
than 50% of loser savings, create zero full-capital losses, and fully liquidate
every signal.

A robust candidate additionally requires a passing adjacent setting in the
same family. No candidate is selected automatically. Any favorable result is
adaptively fitted and requires a newly collected chronological confirmation
sample before H3 v2 can be supported.
