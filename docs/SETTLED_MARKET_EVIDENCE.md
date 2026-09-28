# Settled-Market Evidence and Rule Consistency

Status: canonical Windows validation complete; accepted for safe Git checkpoint closeout.

## Purpose

Collect a small, reproducible, public REST sample of settled `KXBTC15M` markets and determine what Kalshi actually exposes after settlement before any settlement-label, external-feed, or authenticated-stream design is attempted.

This checkpoint is evidence gathering, not a profitability experiment.

## Source boundary

The collector uses only the existing unauthenticated Kalshi REST source.

Official Kalshi documentation currently supports:

- `GET /markets` with the query filter `status=settled`;
- Kalshi lifecycle semantics where that filter returns market objects in terminal REST status `finalized` (there is no returned `status=settled` object state);
- `series_ticker` filtering;
- `min_settled_ts` / `max_settled_ts` filters for settled markets;
- `GET /markets/{ticker}` for a single market;
- settled-market response fields including `result`, `expiration_value`, `settlement_value_dollars`, `settlement_ts`, rule text, and lifecycle timestamps;
- separate `/historical/markets` endpoints for markets older than Kalshi's current historical cutoff.

The candidate deliberately does not add historical fallback because a recent bounded sample is sufficient for this checkpoint. If recent settled data cannot supply the requested sample, collection fails closed instead of silently switching source surfaces.

### Lifecycle filter versus object status

Kalshi distinguishes the **query filter** from the **returned lifecycle state**. `GET /markets?status=settled` selects settled markets, while the returned `market.status` is `finalized` after settlement completes. The first canonical live attempt exposed this distinction and failed closed because the initial candidate incorrectly required returned `status=settled`. The corrected validator requires `finalized` and continues to use `status=settled` only as the discovery filter.

## Reproducible sampling

Default discovery:

```powershell
.\.venv\Scripts\python.exe .\collect_settled_market_evidence.py --count 5 --lookback-hours 24
```

The run records its discovery cutoff and the exact selected tickers. Selection is deterministic inside the returned discovery frame: newest `close_time` first, then ticker as a tie-breaker.

For exact reproduction, rerun the printed tickers directly:

```powershell
.\.venv\Scripts\python.exe .\collect_settled_market_evidence.py --tickers <TICKER1> <TICKER2> <TICKER3> <TICKER4> <TICKER5>
```

Discovery is not treated as eternal identity. The exact ticker list is the reproducible sample identity.

## Raw preservation and lineage

Every REST response is preserved through the existing raw JSONL recorder before transformation.

Each derived row stores:

- `run_id`;
- `raw_source`;
- `raw_session_id`;
- `raw_request_id`.

The offline evidence validator rebuilds deterministic row fields from the exact raw single-market response and rejects derived tampering, duplicate references, unknown raw records, ticker/path mismatches, and successful raw single-market responses that lack derived rows.

## Derived evidence fields

The CSV records observed fields without assigning undocumented meaning:

- `ticker`;
- `status`;
- `result`;
- `settlement_ts`;
- `open_time`;
- `close_time`;
- `expected_expiration_time`;
- `expiration_time`;
- `latest_expiration_time`;
- `occurrence_datetime`;
- `expiration_value`;
- `settlement_value_dollars`;
- exact and whitespace-normalized SHA-256 hashes for `rules_primary` and `rules_secondary`;
- a validated structural-template SHA-256 and parse state for `rules_primary`;
- the complete sorted set of returned market field names.

The raw archive remains the source of truth for the full rule text and response payload.

## Rule consistency

The first live five-market sample showed that whole-string comparison is too strict for `rules_primary`: Kalshi embeds each contract's own close and open clock times in an otherwise identical rule sentence. The five observed rules all retained the same economic structure and changed only those interval-specific boundaries.

The corrected primary-rule check therefore uses a fail-closed structural template:

1. preserve and hash the exact source string;
2. preserve the whitespace-normalized hash for audit;
3. recognize only the exact KXBTC15M grammar observed in the live sample;
4. parse the first embedded EST/EDT date-time as the close boundary and the second as the open boundary;
5. require those parsed instants to equal the market's `close_time` and `open_time`;
6. only after those checks, replace the two variable boundary phrases with named placeholders and hash the validated structural template;
7. compare validated template hashes across the sample.

This is deliberately narrower than generic date stripping. A wording change, unsupported timezone/date format, missing field, or embedded boundary that disagrees with `open_time` / `close_time` blocks decision use instead of being normalized away.

`rules_secondary` remains compared by whitespace-normalized hash because the first live investigation did not identify an expected contract-specific variable in that field.

## Observable consistency checks

The candidate marks evidence decision use blocked when any sampled row has:

- a returned market status other than terminal `finalized`;
- a result other than `yes` or `no`;
- missing ticker, settlement timestamp, close time, or rule text;
- malformed settlement or close timestamps;
- a settlement timestamp earlier than close time;
- an unrecognized primary-rule template;
- a primary-rule boundary that does not match `open_time` / `close_time`;
- validated primary-template drift or secondary rule drift;
- drift in the returned market field-name set across the sample.

`expiration_value` and `settlement_value_dollars` are counted but are not required in the candidate. Their actual presence and meaning are questions for the live sample, not assumptions embedded in the parser.

A consistency block does not erase the evidence run. The manifest can remain a valid completed record while the evidence evaluator reports `decision_use_blocked=true`.

## Offline validation

After collection, validate the printed manifest path:

```powershell
.\.venv\Scripts\python.exe .\validate_settled_market_evidence.py <MANIFEST_PATH>
```

The validator first runs the existing generic run-manifest integrity validation, then performs settled-market raw-to-derived reconciliation.

Expected outputs are separate:

- artifact integrity / lineage: `PASS` or validation error;
- evidence consistency: `PASS` or `BLOCKED`.

A `BLOCKED` consistency state exits nonzero so it cannot be overlooked, while the preserved run remains available for investigation.

## Questions the live sample must answer

1. Does `status=settled` discovery consistently return market objects with terminal REST `status=finalized` and `result` equal to `yes` or `no`?
2. Is `settlement_ts` present and how does it relate to `close_time`?
3. Is `expiration_value` present on every sample, and what format does it use?
4. Is `settlement_value_dollars` present, and is it merely the binary payout representation rather than the BRTI comparison operand?
5. Does `rules_primary` share one validated structural template once only verified open/close boundary phrases are parameterized, and does `rules_secondary` remain identical after whitespace normalization?
6. Do lifecycle fields preserve the previously observed separation between the 15-minute `close_time` and later expiration fields?
7. Does the public settled market object expose separate opening and closing BRTI averages, or only outcome / settlement fields?
8. Does the set of returned field names drift across the sample?

No answer should be inferred before the canonical live run.

## First canonical live evidence

Date: 2026-08-08 local Pacific / 2026-08-09 UTC.

The first successful live sample selected five recent settled contracts:

- `KXBTC15M-26AUG082115-15`;
- `KXBTC15M-26AUG082100-00`;
- `KXBTC15M-26AUG082045-45`;
- `KXBTC15M-26AUG082030-30`;
- `KXBTC15M-26AUG082015-15`.

All five returned:

- terminal `status=finalized`;
- `result=yes`;
- populated `settlement_ts`;
- populated `expiration_value`.

The initial evaluator reported `rules_primary_drift`. Manual review of the raw-preserved rule text showed that this was a validator false positive: the sentence structure and economic operator were identical, while the embedded close/open times advanced by 15 minutes with each contract. This evidence motivated the validated structural-template rule above.

The original run remains preserved evidence. A new run was required after the parser correction because the derived CSV schema records template validation fields.

### Corrected canonical run

Run ID: `collect_settled_market_evidence_20260809T012935685909Z_3f32c571`.

Derived CSV: `logs/settled_market_evidence_20260809T012935Z.csv`.

Manifest: `data/manifests/2026/08/09/collect_settled_market_evidence_20260809T012935685909Z_3f32c571.json`.

The same five tickers were selected. All five returned terminal `status=finalized`, `result=yes`, populated `settlement_ts`, populated `expiration_value`, and populated `settlement_value_dollars`. The validated primary-rule template and normalized secondary rule were consistent across all five. The collector reported `Evidence consistency: PASS`.

The independent offline validator then reported:

```text
Rows: 5
Artifact integrity and raw-to-derived evidence: PASS
Rule consistency: primary=True secondary=True
Observed settlement values: expiration_value=5/5, settlement_value_dollars=5/5
Market field-set consistency: True
Evidence consistency: PASS
```

This is evidence of public settled-market field and rule consistency for a small reproducible sample. It does not establish complete settlement-engine replication.

## Safety boundary

This checkpoint adds no:

- API key or private key;
- account access;
- authenticated REST or WebSocket connection;
- CF Benchmarks collector;
- external BTC feed;
- order placement or cancellation;
- settlement label generation;
- model, backtest, paper broker, or production behavior.

`docs/RISK_POLICY.md` therefore does not need an authorization change for this candidate.


## Final checkpoint conclusions

Final canonical Windows regression after all accepted fail-closed gates:

```text
87 passed
```

The accepted five-market field-name set was identical across all rows. It includes `result`, `settlement_ts`, `expiration_value`, `settlement_value_dollars`, rule text, lifecycle timestamps, prices, volume, and related metadata. It does **not** include separately named opening and closing BRTI average operands.

Therefore the public market object is sufficient for this checkpoint's lifecycle/rule consistency test, but not for independent reconstruction of both numerical operands used by the KXBTC15M settlement comparison. The project does not infer operand meaning from `expiration_value` or `settlement_value_dollars` without official evidence.

Complete settlement replication remains blocked by rounding order, corrections/revisions, missing observations, provider interruption, fallback behavior, exact settlement-engine equivalence, and future authenticated-source operational semantics.
