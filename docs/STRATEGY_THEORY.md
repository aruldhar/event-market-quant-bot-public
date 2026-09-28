# Strategy Theory

## Core hypothesis

A contract may be tradable when its executable market price differs materially from a well-calibrated estimate of its settlement probability.

For a YES purchase, the conceptual edge is:

```text
estimated settlement probability
- executable YES price
- expected fees
- expected slippage
- latency allowance
- model-uncertainty buffer
= usable expected edge
```

A positive number does not automatically justify a trade. The estimate must be calibrated, the quote must be executable at the intended size, and all risk checks must pass.

## Baseline before complexity

The first probability model should be simple enough to understand and audit. Candidate inputs include:

- Distance between the reference price and strike
- Time remaining
- Recent realized volatility
- Settlement-window progress
- Bid-ask spread and depth

Complex machine-learning models are considered only after a transparent baseline and reliable data pipeline exist.

## Failure hypotheses to test

- Apparent edges disappear after fees.
- Displayed prices cannot be filled at useful size.
- The model is overfit to one volatility regime.
- Settlement-index behavior differs from auxiliary spot feeds.
- Latency causes adverse selection.
- Profits are concentrated in a small number of lucky trades.
