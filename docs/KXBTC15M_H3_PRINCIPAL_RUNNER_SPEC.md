# KXBTC15M H3 Principal-Recovery Runner Diagnostic

## Question

At the accepted protected-50% cash-exit opportunity, can H3 improve total P&L
by selling only enough contracts to recover all initial cash and retaining a
small residual runner without re-exposing principal?

## Frozen mechanics

- Same 96 development markets; separate 26-market holdout sealed.
- Causal-native 4–5-minute, 90%-to-below-98% first entry.
- One-second entry latency, full depth, $100 maximum including fees.
- Identical protected-50% target signal and delayed execution snapshot.
- No new entry, timing threshold, price threshold, compounding, external feed,
  authentication, or orders.

## Policies

1. `full_protected_50pct_cash_exit`: sell the full position at the accepted
   protected execution.
2. `principal_runner_preclose`: at that same snapshot, sell the minimum whole
   contracts whose net proceeds recover the complete entry cash outflow after
   the partial-sale fee. Attempt a full-depth cash exit of the residual runner
   beginning ten seconds before close.
3. `principal_runner_settlement`: make the identical principal-recovery sale and
   hold only the residual contracts to settlement.

If the preclose runner lacks full archived depth, settlement is the explicit
fallback. Principal recovery must be at least 100%; otherwise the analyzer
fails closed. Because contract quantities are whole, a small positive amount
may be locked immediately above the recovered principal.

## Metrics and gates

Primary: paired incremental P&L per all 96 markets versus the full protected
cash exit, counting no-trades as $0, with paired-bootstrap 95% interval.

Secondary: runner fraction, runner outcome, profitable and principal-recovery
rates, full-loss rate, 5% tail, and worst P&L.

The baseline must reproduce all 57 accepted causal-native protected exits. All
completed runner rows must recover principal and have nonnegative total P&L.
No holdout, external feed, authentication, or orders may be used.

## Interpretation

The runner may increase average return while changing the objective from a
complete cash exit to residual settlement exposure. Even though initial cash is
recovered, the runner has opportunity cost relative to selling it immediately.
This is adaptive development evidence, not a guarantee or unbiased estimate.
