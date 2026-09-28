# KXBTC15M executable stop-loss diagnostic

Status: frozen before running the stop-loss development study.

## Fixed policy

- The 96 eligible development markets only; holdout markets remain sealed.
- First-five-minute elapsed-minute anchors only.
- Three maximum buy-ins, $100 maximum budget, and 5-cent addition steps.
- One-second decision-to-execution latency.
- Full displayed depth, partial entry fills, and conservative quadratic taker fees.
- $1 net-profit target and forced liquidation beginning 120 seconds before close.

## Stop surface

Compare matched scenarios with no loss stop and executable net-P&L thresholds
of -$5, -$10, -$15, and -$20. A threshold uses the proceeds available from
selling the entire pooled position into current displayed bid depth after the
exit fee. A trigger does not receive that price: execution waits one second and
uses the later archived book. If full liquidation is unavailable, record a
missed stop and retain the position under the existing rules.

## Metrics

- Equal-market-weighted mean P&L and market-clustered 95% interval.
- Profitable and profit-target rates.
- Stop execution rate and realized stopped P&L.
- Five-percent tail and worst P&L.
- Matched P&L change versus no stop.
- Fraction of stopped scenarios whose no-stop counterpart later recovered.

This is a coarse development diagnostic, not proof of a profitable strategy.
At most one stop rule may be selected and frozen before any holdout access.
