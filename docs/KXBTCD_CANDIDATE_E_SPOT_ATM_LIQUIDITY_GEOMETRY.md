# KXBTCD Candidate-E Spot/ATM-Relative Liquidity Geometry

## Checkpoint 21N-W

Classification:

`EXPLORATORY_SUPPORT_SPOT_ATM_RELATIVE_LIQUIDITY_STRUCTURE`

Artifact SHA-256:

`b2448067c525aaaa6e2f076bed321fb9e55621fcb1319f9a2c282d24d1e31393`

This checkpoint formalizes the outcome-blind July 10 diagnostic that followed
the non-evaluable continuous-v1 closeout. It does not score Candidate E on
nonstructural strikes and does not inspect settlement outcomes.

## Design

- 4 independent July 10 KXBTCD events.
- Full owned 623-ticker ladder.
- 54 exact minute cross-sections/event from T-55 through T-2.
- 216 cross-sections total.
- BTC state is the immediately preceding fully completed Coinbase one-minute
  candle.
- ATM is the ladder strike closest to that causal BTC spot value.
- A valid two-sided market requires a verified YES bid and YES ask with bid <
  ask.

## Result

177 / 216 cross-sections contained at least one valid two-sided market.

Among those 177 active cross-sections:

- exact ATM ticker two-sided: 62;
- nearest valid two-sided <= 1 rank from ATM: 132;
- <= 2 ranks: 161;
- <= 3 ranks: 174;
- <= 5 ranks: 177;
- median nearest distance: 1 rank;
- maximum nearest distance: 4 ranks.

Across 755 active ticker-minute instances:

- median absolute rank distance from ATM: 3;
- median absolute strike distance from spot: $286.25;
- median absolute BTC/strike log distance: about 44.81 bps;
- 735 / 755 were within five ranks of ATM.

## Interpretation

This four-event exploratory evidence supports the hypothesis that KXBTCD
two-sided liquidity is organized around contemporaneous BTC spot / ATM rather
than fixed event-wide quantiles.

This does **not** establish a production or validated tradable universe. In
particular:

- 21N-W does not choose a v2 rank envelope;
- Candidate E has not been validated or scored on arbitrary nonstructural
  strikes here;
- the evidence contains only four independent events;
- no profitability or generalization claim is permitted.

Continuous v1 remains permanently closed as non-evaluable.

## Next

Checkpoint 21N-X should predeclare a new, separately versioned liquidity-first,
spot-relative tradable-universe strategy and its fresh-evidence validation
protocol before any Candidate-E scoring on nonstructural strikes.
