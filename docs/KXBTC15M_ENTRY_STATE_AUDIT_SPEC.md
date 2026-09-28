# KXBTC15M causal entry-state audit

Status: frozen before inspecting state-conditioned economic results.

## Fixed economic policy

- The 96 eligible development markets only; the 26-market holdout stays sealed.
- First-five-minute elapsed-minute anchors.
- Three equal-dollar tranches within a $100 maximum budget.
- Five-cent addition steps, full displayed depth, quadratic fees, and one-second latency.
- $1 net-profit target.
- Immediate executable -$5 stop, the least-negative simple exit policy observed.

## Causal features

Only information timestamped at or before the entry decision may be used:

- cheaper-side executable ask, bid, and spread;
- displayed bid and ask quantity within five cents of the best price;
- near-book depth balance;
- trailing 10/30/60-second ask move, range, directional efficiency, drawdown,
  rebound, and direction-change count;
- elapsed minute;
- a predeclared 30-second path-state label.

No official outcome, post-decision quote, external BTC value, or holdout record
may enter a feature. Summaries are univariate and descriptive. An earlier-64 /
later-32 chronological split is reported as a stability diagnostic, not a
pristine internal holdout, because all development markets informed earlier
strategy-level work.
