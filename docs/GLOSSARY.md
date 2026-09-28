# Glossary

**Ask:** Lowest price at which someone is currently willing to sell.

**Bid:** Highest price at which someone is currently willing to buy.

**Calibration:** Whether events assigned a probability such as 70% occur approximately 70% of the time across many comparable predictions.

**Edge:** Estimated expected value remaining after price, costs, uncertainty, and execution effects.

**Fill:** Execution of some or all of an order.

**Latency:** Delay between an external event, receipt of information, a decision, order submission, and acknowledgement/fill.

**Order book:** Current resting buy and sell interest at different prices and quantities.

**Out-of-sample:** Data not used to design, train, or tune the strategy.

**Paper trading:** Simulated trading that records decisions and realistic hypothetical executions without real orders.

**Settlement source:** Official data or authority used to determine the contract outcome.

**Slippage:** Difference between the expected execution price and the actual or realistically simulated fill price.

**Spread:** Difference between the best bid and best ask.

## Collection run manifest

A JSON receipt created before one collector invocation. It records lifecycle state, sanitized arguments, code/environment identity, source sessions, and integrity descriptors for the files produced by that run.

## Artifact integrity

Evidence that a stored file still matches recorded bytes and baseline structure, usually checked with file size, SHA-256, parsing, schema invariants, and record counts. Integrity does not establish economic meaning or correctness of the source.

## Runtime event

A structured operational record describing collector lifecycle, request outcome, persistence state, or endpoint validation. It does not replace the raw source payload.

## Event correlation

The logical link from an operational event to a persisted raw exchange using `raw_source`, `raw_session_id`, and `raw_request_id`.

## Severity

An operational impact label: `info`, `warning`, `error`, or `critical`. It does not represent market confidence or expected profitability.

## Fail closed

Stop collection or trading when a required state, data source, clock, persistence path, or risk check is uncertain instead of continuing with incomplete evidence.
