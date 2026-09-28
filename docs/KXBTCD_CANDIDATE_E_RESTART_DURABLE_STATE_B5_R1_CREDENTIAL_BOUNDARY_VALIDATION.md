# KXBTCD Candidate-E Restart/Durable State B5-R1 Credential-Boundary Validation

Date: 2026-09-04 (America/Chicago)

## Scope

B5-R1 hardens request-metadata persistence before bounded live restart testing.
It does not alter model logic, signal thresholds, order-book semantics,
connection authentication, cohort arming, or execution authorization.

Parent closeout receipt:
`faaab2930b1ae21b78cba62be7ec528fcfc0dd16`

Frozen restart-design fingerprint:
`40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

Frozen production-runtime architecture fingerprint:
`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`

## Security invariant

Credentials and signing material must never become durable research evidence.

The prospective `RawJournal`, production-shaped `RuntimeRawJournal`, and
restart-aware `RestartSessionRawJournal` now validate request metadata before
serialization.

The validator rejects authorization, cookie, token, signature, API/access-key,
private-key, and Kalshi-access metadata. Nested request params receive the same
checks. URLs containing user-info, query strings, or fragments are rejected.
Unknown top-level request-identity fields fail closed.

## Existing safe metadata compatibility

The initial implementation omitted benign metadata already used by committed
Coinbase runtime code. B5-R1-R2 therefore admits only:

- `phase`: `latest_visibility` or `older_pagination`;
- `latest_attempt_index`: positive integer or `None`;
- `cb_before`: bounded string or `None`;
- `cb_after`: bounded string or `None`;
- `product_id`: exactly `BTC-USD`.

This is a compatibility repair, not a generic relaxation.

## Validation chronology

Initial credential-boundary validator: PASS.
Focused regression: `59 passed in 2.28s`.
Adjacent restart/readiness regression: `78 passed in 4.39s`.

First full repository regression:
`8 failed, 1537 passed, 22 subtests passed in 156.36s`.

Failure diagnosis:
- seven Coinbase REST recovery tests failed first on `phase`;
- the same request contract also carries `latest_attempt_index`, `cb_before`,
  and `cb_after`;
- one Coinbase WS test failed on `product_id`;
- no failure showed a secret being persisted.

B5-R1-R2 repaired only that benign metadata compatibility contract.

Repaired credential-boundary validator: PASS.
Targeted repaired regression: `56 passed in 1.70s`.
Final full repository regression:
`1553 passed, 22 subtests passed in 108.72s`.
Exit code: `0`.

## Safety state

- synthetic secrets persisted: 0;
- network during B5-R1/R2 validators: 0;
- canonical prospective DB: not created;
- 168-hour prospective cohort: not armed;
- Candidate-E execution: disabled;
- demo/paper/real orders: 0;
- production writes: 0.

## Conclusion

B5-R1/R2 provides regression-clean evidence that request metadata is no longer
an arbitrary credential-persistence surface while preserving the committed
safe Coinbase recovery and WebSocket metadata contracts.

This is engineering safety evidence only. It does not establish profitability
and does not authorize execution.

The next bounded validation target is live read-only connection-generation
rollover and source-loss/recovery under the frozen B4 readiness contract.
