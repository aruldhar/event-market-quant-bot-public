# KXBTCD Predexon Anchor-Local Execution-State Eligibility

Status: accepted source-engineering design, 2026-09-01.

## Purpose

Define which historical KXBTCD ticker-at-decision-time states may be used by the later Candidate-E executable-entry simulator.

This document does not score Candidate E, inspect outcomes, calculate P&L, or define a profitable strategy.

## Frozen inputs

- Candidate-E TTC grid: 55m, 50m, 45m, 40m, 35m, 30m;
- four July 10 hourly KXBTCD events;
- all 623 owned strike contracts;
- completed free sub-cent snapshot histories;
- paid Predexon delta shard;
- full-ladder fail-closed verified replay segments.

## Eligibility rule

A ticker-at-anchor state is source-eligible only when the exact Candidate-E decision timestamp lies inside one continuously verified replay segment for that ticker.

If no such segment contains the anchor, the state is unavailable.

The simulator must not:
- interpolate across a failed pair;
- carry a book through an unreconciled boundary;
- use nearest-time substitution;
- use another strike's book as a proxy;
- infer availability from ticker-level average coverage;
- infer availability from event-level average coverage.

## Latency extension

The current source rule validates the decision instant only.

Before execution simulation, latency must be predeclared. For any non-zero latency assumption, the complete interval from decision timestamp through simulated execution timestamp must remain inside the same verified replay segment. Otherwise the attempted state is unavailable under that latency scenario.

## Observed source availability

Across 623 contracts and 24 event/TTC anchor combinations:
- possible ticker-at-anchor states: 3,738;
- source-eligible states: 2,304;
- eligibility fraction: 61.64%.

This is not an effective sample size. The statistical unit remains the hourly event, of which there are only four.

## Interpretation

Source eligibility means the historical execution book can be reconstructed under the accepted continuity contract at that decision state.

It does not imply:
- positive edge;
- sufficient executable quantity;
- a post-latency fill;
- Candidate-E correctness;
- profitability;
- generalization from four events.
