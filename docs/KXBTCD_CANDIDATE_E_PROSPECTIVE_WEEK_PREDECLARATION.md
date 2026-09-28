# Checkpoint 21N-Z-A — Candidate-E Prospective One-Week Predeclaration

## Result being closed

The E2 post-outcome sensitivity run completed with exact artifact hashes frozen in
this checkpoint. The official July-10 result remains 27 EXACT / 33 CENSORED / 15
INCONCLUSIVE. Separately, censored observed traces were 24 positive / 3 negative /
6 zero and 93 independently terminalized observed fills were 60 positive / 33
negative. The three liquidation-only point values were the same JUL14/.05 case at
0/500/1000 ms, each -0.7921. These are exploratory only and cannot select the next
policy.

## Fresh prospective primary policy

Candidate E Champion-Final remains frozen. Primary entry requires net edge >=
$0.02 per contract. The reason is mechanical: .02 is the midpoint of the already
frozen 0/.01/.02/.03/.05 menu, not a July-10 outcome choice. Other thresholds are
diagnostic only during the prospective window.

Retain exact V2 mechanics: T-55 through T-2, dynamic ±5-rank Coinbase-relative ATM
window, at most 11 markets, >=1 contract at the decision-time best purchase level,
and deterministic highest-net-edge signal selection.

Exit uses the existing convergence rule: first fully executable same-side sale
whose net cash is at least entry-time side fair probability times open quantity.
No trigger before close means settlement fallback.

Maximum two filled entries/event. A second entry requires a complete first exit,
then a genuine re-arm because the reference market leaves the window, its best
entry depth falls below 1 contract, or its net edge falls below .02. The re-arm
timestamp itself cannot also be the second-entry timestamp.

## Sources and timing

Coinbase remains the sole required independent BTC source. Candidate E consumes
the exact close of the last fully completed UTC Coinbase one-minute candle at the
decision time: no future interpolation, nearest-neighbor substitution, carry-forward,
or source substitution. Kraken is diagnostic only.

The primary cohort is the first 168 consecutive hours after one explicit future
collector arm timestamp. Operationally lost events are not replaced by extending
the window.

The historical 0/500/1000 ms latency grid is removed from the primary prospective
design. The live collector will preserve monotonic feed-receive -> model-ready ->
signal timing. Production order latency is not available until a later separately
authorized execution checkpoint.

## Safety

This is read-only. No order submission code, demo orders, paper broker, or
real-money orders are authorized. The future micro-production probe concept is
preserved but remains gated and must be implemented separately only after current
official Kalshi order constraints and the project's execution-risk gates are
reverified.
