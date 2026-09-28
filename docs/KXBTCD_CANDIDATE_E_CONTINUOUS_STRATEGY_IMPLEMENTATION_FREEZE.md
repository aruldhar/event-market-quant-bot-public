# KXBTCD Candidate-E Continuous Strategy Implementation Freeze

## Checkpoint 21N-U-A

This checkpoint freezes the implementation for `kxbtcd_candidate_e_continuous_convergence_reentry_v1` **before** any real continuous July 10 Candidate-E path is opened.

The implementation is split deliberately: U-A freezes code; U-B fetches and binds only the required Coinbase source rows; the later path run may then expose outcome-blind continuous signals/fills. Settlement outcomes remain closed.

### BTC source contract
Each T-55 through T-2 decision uses the immediately preceding fully completed Coinbase UTC minute. That requires **54 exact candles per event, 216 total**, from close-56m through close-3m. Missing exact minutes fail closed. Raw HTTP responses are preserved by the existing recorder before the deterministic CSV is written.

### Decision clock
Entry evaluation occurs at T-55/T-2 boundaries, structural best bid/ask price or quantity changes, new causal Coinbase-minute boundaries, and verified replay segment starts. Segment starts are availability transitions, not interpolation across gaps. Deep-book changes with unchanged best entry levels do not manufacture new entry attempts; liquidation still sees all reconstructed book-state changes.

### Execution and re-entry
Candidate E, q10/q30/q50/q70/q90, 0/1/2/3/5c margins, 0/500/1000ms latency, one-contract sizing, fixed-point fees, and 21N-R liquidation are retained. Only one entry IOC may be pending. Misses do not consume the two-filled-entry cap. A second filled trade requires full exit, then a later evaluable false state of the first trade's exact market-side signal, then a still-later qualifying signal. Trade-1 history is logged but cannot influence Trade 2.

### Safety gate
The real path runner requires `configs/kxbtcd_candidate_e_continuous_july10_source_binding.json`. U-A does not create it, so the runner fails closed until U-B pins the Coinbase materialization hash to this implementation.

Continuous July 10 strategy results: **NOT RUN**. Settlement outcomes: **NOT ACCESSED**. Settlement-dependent P&L: **NOT RUN**. Orders: **0**.

Next: **21N-U-B — Continuous Coinbase Source Materialization and Binding**.
