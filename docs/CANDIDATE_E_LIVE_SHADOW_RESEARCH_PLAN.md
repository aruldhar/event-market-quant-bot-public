# Candidate-E live-shadow research plan

## Status and boundary

This document records future **read-only live-shadow** research ideas. It does
not change the frozen Candidate-E V2 entry policy, authorize an order, or
authorize a paper broker. Every prospective policy must use causal inputs,
observed order-book depth, documented fees, and official settlement evidence.

The existing five-policy edge grid remains the control:

| Scenario | Required net edge per contract |
| --- | ---: |
| `edge_000` | $0.00 |
| `edge_001` | $0.01 |
| `edge_002` | $0.02 (primary) |
| `edge_003` | $0.03 |
| `edge_005` | $0.05 |

`edge_000` removes only the positive-edge threshold. It still requires a
causal BTC reference, a complete valid candidate universe, qualifying visible
entry depth, an entry-window state, and no open-position or re-entry block.

## Current live-shadow observability

The Scenario Detail dashboard has bounded, per-run/per-scenario decision
diagnostics. They classify processed snapshots as outside the entry window, no
evaluable market, insufficient visible depth, below the edge threshold,
eligible selection, position open, or event/re-entry state. It also records
the best observed YES/NO edge and closest edge miss. These are aggregates, not
one verbose record per polling interval.

Use this evidence to explain a zero-trade run before changing any threshold.
Do not reduce an entry gate simply to create more trades.

## Stop-loss comparison: planned shadow experiment

Do not add a stop rule to the frozen baseline. After enough retained
live-shadow observations exist, compare these policies in a separate,
predeclared experiment:

1. Keep the five existing no-stop edge policies as controls.
2. At the primary $0.02 edge threshold only, add four variants with an
   executable-loss cap of 10%, 20%, 30%, or 40% of actual entry outlay.
3. The existing primary policy is the no-stop control, producing nine unique
   policies rather than a poorly powered 25-policy edge-by-stop matrix.

A stop is triggered only when the fee-aware proceeds from an immediate IOC
sale of the **entire remaining quantity** at the observed bid ladder are at or
below the cap. A displayed midpoint or a single shallow price level is not a
valid stop trigger.

If a stop condition is met but full visible liquidation is not available, the
position remains open and the stop stays armed. It is evaluated again on each
later complete book update. Official settlement finalizes any quantity that
remains open at market close; it never substitutes for continued stop
monitoring while the market is open. Every trigger, failed full-depth attempt,
successful exit, and settlement fallback must be auditable.

## Mid-range swing challenger: research hypothesis

The proposed mid-range challenger is a separate strategy family, not a
Candidate-E threshold change. Its entry condition would require an
**executable entry ask** between $0.30 and $0.70, plus the normal causal-data,
valid-book, visible-depth, fee, and positive-edge gates.

Its question differs from Candidate-E's outcome-probability question:

> Given a valid entry, can the complete position reach a specified executable
> exit level before market close after fees and visible-depth constraints?

Before choosing a profit target or stop, use archived shadow paths to measure:

- maximum executable favorable and adverse excursion after entry;
- time to a full executable exit at each proposed target;
- spread, depth, and fee impact at entry and exit;
- profit-target, stop, and settlement outcomes; and
- results by entry price band, time-to-close bucket, volatility, and liquidity
  regime.

Only after that outcome review should a small, frozen grid be deployed in
live-shadow, for example two profit-target levels crossed with two executable
stop levels. It must be compared with its no-stop/no-extended-hold control on
the same causal paths.

## Other useful challenger families

These are hypotheses for later offline or read-only shadow experiments, not
implementation authorization:

| Challenger | What it tests | Keep fixed while testing |
| --- | --- | --- |
| Entry-window comparison | Whether a narrower T-55 to T-10 or other predeclared window improves executable outcomes | Candidate-E price model, fees, depth, and exit policy |
| Liquidity filter | Whether minimum full-depth and maximum spread rules avoid unexitable positions | Entry threshold and position size |
| Time-to-close regime | Whether the same edge has different outcomes early versus late in the event | Model, market universe, and execution assumptions |
| Model-disagreement filter | Whether a larger model-versus-market gap improves results after costs | Feature definition and calibration version |
| Mid-range swing model | Whether target-before-close probability is predictable separately from settlement probability | Labels, target/stop definitions, and causal data lineage |

Do not select a champion from a small number of 24-hour runs. Preserve raw
books, causal BTC inputs, candidate evaluations, shadow decisions, simulated
fills, settlement evidence, and the exact code/configuration/image lineage.
Use archived runs for chronological offline replay and reserve later, unseen
live-shadow periods for comparison.

## Future real micro-probe sizing: unresolved policy conflict

The project currently contains two incompatible definitions of the future
"$0.01 contract run":

- `docs/KXBTCD_CANDIDATE_E_MICRO_PRODUCTION_VALIDATION_PATH.md` defines one
  whole contract with a $0.01 purchase limit.
- `docs/RISK_POLICY.md` and `docs/V2_MICRO_PROBE_RUNBOOK.md` define a 0.01
  fractional-contract quantity after market-specific increment verification.

No execution design may rely on either interpretation until this conflict is
resolved in a reviewed predeclaration. Fractional quantities can produce
sub-cent trade values that Kalshi rounds through its fee/rounding mechanism, so
they are unsuitable for interpreting tiny live P&L. A later explicitly
authorized operational probe may use one whole contract to validate the
order/fill/reconciliation path; a later economics probe may use a separately
approved whole-contract quantity large enough that one-cent price moves and
fees are legible. Neither statement authorizes an order or a scale-up.
