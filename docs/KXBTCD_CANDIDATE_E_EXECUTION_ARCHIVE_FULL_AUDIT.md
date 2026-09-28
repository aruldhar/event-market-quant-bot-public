# Checkpoint 21K-B4B ? Candidate-E Full Execution Archive Readiness Audit

## Status

**PASS WITH LIMITATIONS**

The full reusable Candidate-E execution archive is structurally valid and adequate
to proceed into a separately predeclared Entry Model v1 research phase.

No strategy P&L was calculated.
No settlement outcomes were inspected during the readiness audits.
The protected historical reserve was not accessed.

## Frozen archive

Run:

`collect_kxbtcd_candidate_e_execution_archive_20260818T132034933844Z_f8b08b83`

Universe:

- 4,070 Candidate-E OOF/OOS events
- 20,236 KXBTCD markets
- H1_OOF: 1,070 events / 5,334 markets
- H2: 750 / 3,750
- H3: 750 / 3,750
- C1: 500 / 2,491
- C2: 500 / 2,441
- C3: 500 / 2,470
- protected reserve accessed: no
- strategy P&L calculated: no
- authentication used: no
- orders placed: 0

## Structural audit

All frozen-universe structural checks passed.

- market metadata rows: 20,236
- event metadata rows: 4,070
- coverage rows: 20,236
- series metadata rows: 1
- candle CSV rows matched coverage accounting
- trade CSV rows matched coverage accounting
- all market closes were minute aligned
- all returned candles had two-sided YES bid/ask closes

Full-lifecycle candle coverage was intentionally not treated as the primary
strategy-readiness metric:

- expected lifecycle periods: 4,583,795
- observed candle periods: 2,418,338
- missing periods: 2,165,457
- aggregate lifecycle coverage: 52.7584%

## Exact Strategy-v1 decision-state coverage

Market-level signal+next-minute two-sided coverage:

- T-55: 10,009 / 20,236
- T-50: 18,108 / 20,236
- T-45: 12,134 / 20,236
- T-40: 16,752 / 20,236
- T-35: 11,025 / 20,236
- T-30: 15,636 / 20,236

Additional coverage:

- markets with all six entry pairs: 8,359
- markets with at least one entry pair: 19,282
- events with at least one usable market at all six anchors: 3,668 / 4,070
- events with at least one usable T-5 through T-1 force state: 4,067 / 4,070

Missing executable states remain missing. They must not be imputed.

## Historical relative-minute regime

A systematic relative-minute availability pattern was detected.

Across the six Candidate-E anchors:

- T-50/T-40/T-30 mean signal availability: 85.845%
- T-55/T-45/T-35 mean signal availability: 67.706%
- difference: +18.139 percentage points

The effect:

- appears across every Candidate-E evidence stage;
- appears in normal <=60-minute markets as well as longer-lived markets;
- varies substantially by chronological month;
- is therefore not explained by long-lived market structure alone.

The effect strengthened materially through portions of 2025 and later weakened.
Calendar month is not therefore authorized as an Entry Model v1 predictor merely
because it identifies historical archive regimes.

## Activity-versus-archive diagnostic

Last-60-minute public trade activity:

- zero trades: 17,508 markets / 86.52%
- 1-2 trades: 515 / 2.54%
- 3-10 trades: 479 / 2.37%
- 11-50 trades: 592 / 2.93%
- 51+ trades: 1,142 / 5.64%

Mean T-59 through T-1 candle density increased monotonically with activity:

- zero trades: 81.10%
- 1-2 trades: 89.08%
- 3-10 trades: 94.92%
- 11-50 trades: 98.05%
- 51+ trades: 99.59%

Therefore real public trading activity is associated with denser historical
candlestick coverage.

However:

- every one of the 17,508 zero-trade markets still had at least one returned candle;
- 94.30% of returned last-60-minute candle rows had zero reported volume;
- the zero-trade subset retained a +20.526 percentage-point
  T-50/T-40/T-30 versus T-55/T-45/T-35 availability gap.

Therefore historical candlestick missingness cannot be interpreted as a pure
economic liquidity/activity signal. It contains both market-activity effects and
historical archive/representation effects.

## Entry Model v1 data consequence

The initial Entry Model must distinguish observed economic state from archive
availability.

Permitted causal economic inputs may include:

- frozen Candidate-E probability and executable edge;
- contemporaneous executable bid, ask, midpoint, and spread;
- independently synchronized BTC state;
- BTC distance, return, momentum, and realized-volatility features;
- reported volume and open interest;
- observed public-trade count, size, and direction features where available;
- causal quote/candle movement features when their required lookback observations
  are actually available;
- TTC and contract/strike state.

Initial Entry Model v1 must not use:

- raw historical candle missingness as an economic predictor;
- calendar month/year merely as a proxy for archival availability;
- forward-filled, interpolated, or manufactured Kalshi quote states.

If a required contemporaneous executable state or required feature history is
unavailable, the state is ineligible/abstained under the frozen feature contract
rather than imputed.

Public-trade features must be optional state variables rather than mandatory
eligibility requirements because 86.52% of markets had zero public trades in the
last hour.

## Fee observation

The archive returned:

- event fee-change rows: 0
- current event fee overrides: 0
- series fee-change rows: 0
- current KXBTCD series fee type: quadratic
- current fee multiplier: 1

These observations do not by themselves prove that the current fee schedule applied
unchanged throughout the entire historical archive. Exact historical fee semantics
must still be resolved from official Kalshi documentation before any P&L evaluator
is allowed to score economics.

## Decision

Checkpoint 21K-B4B closes **PASS WITH LIMITATIONS**.

The reusable archive is accepted for causal Entry Model research subject to the
missing-data rules above.

The next research step is to predeclare Entry Model v1 before opening Strategy-v1
P&L or fitting the entry model.

The 4,676-event protected historical reserve remains untouched.
