# KXBTC15M recovery-aware stop diagnostic

Status: frozen as the final simple-rule reversion diagnostic before execution.

## Fixed components

- 96 eligible development markets; the 26-market holdout remains sealed.
- First-five-minute elapsed-minute anchors.
- Three equal-dollar tranches within one fixed $100 maximum cash budget.
- Five-cent addition steps; additions are evaluated before loss stops.
- Full displayed depth, quadratic taker fees, one-second execution latency.
- $1 executable net-profit target and forced liquidation from two minutes left.

## Recovery-aware stop surface

- Grace after the latest filled tranche: 10, 20, or 30 seconds.
- Executable net-P&L stop: -$5 or -$10.
- Confirmation: the full-depth executable loss must remain at or beyond the
  threshold for at least two seconds.
- Execution: after confirmation, wait one second and sell into the later book.
- If the loss recovers or full liquidation depth disappears during
  confirmation, reset the breach clock.

Every policy is paired with the exact no-stop counterfactual. This expanded
development search is diagnostic. A promising result must be validated on new
prospective markets rather than used to justify opening the existing holdout.
