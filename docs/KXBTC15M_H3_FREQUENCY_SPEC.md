# KXBTC15M H3 monitoring-frequency diagnostic

## Question

Does checking the already-frozen H3 entry condition more often than every five
seconds materially change opportunity capture or realized economics on the
frozen 96-market development set?

This is a monitoring-mechanics diagnostic. It does not alter or reopen the H3
strategy selection and it does not inspect the 26-market holdout.

## Frozen elements

- Development population: the same 96 eligible markets.
- Entry window: `240 < seconds_remaining <= 300`.
- Entry condition: favored midpoint `>= 0.90` and `< 0.98`.
- Maximum cash budget: $100 per filled entry.
- Entry latency: minimum one second; the first archived response at or after
  that time is used.
- Execution: archived full depth with whole-contract fills.
- Fees: frozen quadratic KXBTC15M schedule, multiplier 1, conservative
  rounding.
- Exit: protected target equal to 50% of maximum net settlement profit.
- Fallback: delayed full-depth sale beginning ten seconds before close, then
  settlement only if the archived book cannot support a complete cash exit.
- One filled entry at most per market and scenario.

## Monitoring schedules

The matched causal comparison uses raw HTTP `timing.received_at_utc`, because a
response cannot be acted on before it is received.

- `native`: every archived response, nominally about 0.5 seconds with jitter;
- `1s`: first causally available response at or after each one-second anchor;
- `2s`: first causally available response at or after each two-second anchor;
- `5s`: first causally available response at or after each frozen five-second
  anchor.

Grid anchors with more than two seconds of missing-data lag are not carried
forward. Duplicate responses selected by adjacent anchors are counted once.

The report also contains one `legacy_csv_loop_time` 5-second row. It must
reproduce the accepted 52-trigger, $3.728403846 mean-P&L baseline exactly. It
uses the historical derived-CSV observation clock and is not a causal
frequency comparator.

## Entry-latency modes

- `unprotected`: after the first qualifying signal, execute after the frozen
  one-second delay at the available full-depth price. This reproduces the
  accepted behavior.
- `state_protected`: after the delay, require that the favored side is
  unchanged and its midpoint is still in the frozen 90%-to-below-98% band. If
  not, reject that signal and resume the same monitoring schedule. No new
  threshold is introduced.

The protected mode deliberately does not impose a new average-fill-price cap.
Doing so would change the economic rule rather than isolate delayed-state
persistence.

## Primary comparison

The primary metric is mean P&L per eligible market, assigning $0 to a market
that does not trade. This preserves the economic consequence of a frequency
changing which markets trigger. The paired difference is computed market by
market against causal 5-second monitoring with the same entry-latency mode.

Conditional mean P&L per filled entry, trigger rate, fill rate, profitable
rate, protected-target fill rate, fallback rate, full-capital-loss rate, 5%
tail, worst P&L, realized delay, and entry-rejection counts are secondary.

Chronological earlier-64/later-32 rows are retained. Scenario rows record
whether the triggering state came from above 98%, below 90%, an already
eligible state, a side change, or the initial observed state.

## Decision boundary

This diagnostic can justify choosing a monitoring implementation for
prospective collection. It cannot establish a new strategy edge, select a new
entry band, expand the entry window, or open the holdout. Any later time-window
study keeps the 90%-to-below-98% band fixed first; band search is a separate,
explicitly multiplicity-exposed step.
