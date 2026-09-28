# Candidate-E Coinbase Runtime and Recovery Validation

<!-- CHECKPOINT21N_Z_D_COINBASE_RUNTIME_RECOVERY_20260904 -->

## Status

Checkpoint 21N-Z-D Coinbase transport/minute-state/recovery implementation has
completed its focused tests and live read-only validation.

This evidence validates engineering behavior only. It does not establish
Candidate-E profitability, executable Kalshi fills, demo readiness, or
production authorization.

Current execution state remains disabled.

## Frozen architecture parent

Production-runtime architecture fingerprint:

`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`

Parent Z-C checkpoint:

`6e40e1dc3a50e1323b9bb9bbeee18a297ee5e753`

Parent Z-C receipt:

`dfdab6da23302d2131266b3fb697c7432bd074e5`

## Implemented Coinbase components

- public Coinbase Exchange `BTC-USD` WebSocket transport;
- `matches + heartbeat` subscription;
- raw WebSocket frame persistence before transformation;
- exact completed-UTC-minute close builder;
- no-trade-minute fail-closed behavior;
- heartbeat freshness gating;
- heartbeat/trade-ID gap detection;
- raw-first REST trade recovery;
- bounded REST latest-page visibility retries;
- older-page `CB-AFTER` pagination only after the REST latest watermark has
  reached the frozen recovery target;
- cursor-coverage recovery proof;
- conservative WebSocket/REST cross-transport identity validation;
- first accepted trade evidence remains canonical;
- no Kalshi connection in Coinbase recovery tests;
- no order path.

## D2 live completed-minute evidence

Run:

`candidate_e_coinbase_ws_smoke_20260904T032221Z`

Observed:

- raw frames: 162
- subscriptions: 1
- `last_match`: 1
- `match`: 122
- heartbeat: 38
- trade observations including seed: 123
- completed minute start: `1788492120`
- completed-minute close: `80927.01`
- close trade ID: `1088541458`
- heartbeat trade ID: `1088541458`
- builder recovery required: false
- sequence regressions: 0
- non-unit sequence transitions: 160 / 160
- maximum positive sequence delta: 684
- BTC-USD trade-ID gaps: 0
- heartbeat-ahead observations: 0

Independent raw reconstruction reproduced exactly:

- close price: `80927.01`
- close trade ID: `1088541458`
- close source time: `2026-09-04T03:22:59.441987Z`

Hashes:

- raw JSONL SHA-256:
  `AAC2B2B1CD3A34F8B39FB00A0F61ACE2E58E458A124DB7EA4553CCF936399E1B`
- manifest SHA-256:
  `9F6260102F174BB4E13E49A75DA472A4C18463B8FC0B15CC414FD78091721450`

### D2 interpretation

General Coinbase sequence-number adjacency is not used as the primary
BTC-USD match-completeness proof for the selected `matches + heartbeat`
subscription.

Trade-ID/heartbeat continuity is the primary missing-trade signal.
Sequence regressions remain unhealthy and sequence deltas remain diagnostic.

## D3 induced-gap recovery experiment

The recovery smoke intentionally preserved a live WebSocket match in the raw
journal while withholding it from the minute builder.

The builder was required to detect the resulting missing interval and remain
unavailable until REST recovery was proven.

### Failure 1 ? REST visibility lag

Observed recovery interval:

- pre-gap trade ID: `1088545617`
- intentionally withheld trade ID: `1088545618`
- recovery target: `1088545619`

The first REST latest page ended at trade ID:

`1088545608`

REST was therefore 11 trade IDs behind the WebSocket recovery target.

Following `CB-AFTER` at that point moved only into older history and could not
recover the newer target.

Accepted repair:

1. remain recovery-blocked;
2. retry the unpaginated REST latest page;
3. require the latest REST watermark to reach or exceed the frozen recovery
   target;
4. only then paginate older with `CB-AFTER` if the known pre-gap boundary is
   outside the latest page;
5. fail closed if the bounded latest-page retry limit is exhausted.

Current bounded validation policy:

- maximum latest-page attempts: 10
- spacing: 0.5 seconds
- no weakening of recovery coverage proof.

## D3 cross-transport representation finding

For the same Coinbase trade ID, live evidence showed REST and WebSocket may
serialize fields differently.

Observed example:

Trade ID:

`1088547868`

WebSocket:

- price: `80923.31`
- time: `2026-09-04T03:54:47.742718Z`
- size: `0.00000026`
- side: `buy`

REST:

- price: `80923.31000000`
- time: `2026-09-04T03:54:47.742719Z`
- size: `0.00000026`
- side: `buy`

Observed REST-minus-WebSocket timestamp delta:

`+1 microsecond`

A two-trade WS/REST overlap audit found:

- economic-field mismatches: 0
- minute-assignment mismatches: 0
- timestamp deltas: one `0 us`, one `+1 us`
- maximum observed absolute delta: `1 us`

This evidence does not establish that Coinbase timestamps always differ by at
most one microsecond.

### Accepted conservative cross-transport identity envelope

A WebSocket/REST corroboration is compatible only when all of the following
hold:

- exact trade ID;
- numerically identical price;
- numerically identical size;
- identical side;
- absolute timestamp delta <= 1 microsecond;
- both timestamps belong to the same exact UTC minute.

Any larger discrepancy or minute-bucket disagreement fails closed.

A REST corroboration never replaces the first accepted canonical trade object.
In the normal live path, this preserves the original WebSocket timestamp.

Same-transport duplicate evidence remains exact; the cross-transport tolerance
is not applied to duplicate observations from the same transport.

## D3 duplicate-corroboration defect

A subsequent live run exposed a builder-level conflict for trade ID:

`1088548963`

That trade was already present from WebSocket as the recovery-trigger trade.
REST returned the same economic trade with a `+1 us` timestamp representation
difference.

The builder originally compared duplicate source timestamps exactly and
rejected the REST corroboration before the cross-transport identity rule could
be applied.

Accepted repair:

- retain `size` and `side` in `CoinbaseTrade`;
- apply the strict cross-transport identity rule inside the builder;
- compatible cross-transport duplicate = corroborative no-op;
- keep the first accepted trade object canonical;
- incompatible duplicate = fail closed.

## Canonical D3 end-to-end PASS

Run:

`candidate_e_coinbase_recovery_smoke_20260904T040632Z`

Recovery interval:

- pre-gap boundary: `1088550189`
- intentionally suppressed trade: `1088550190`
- recovery target: `1088550191`

Suppressed trade:

- price: `80874.01`
- source time: `2026-09-04T04:06:37.231109Z`

Final result:

- REST coverage proven: yes
- boundary seen: yes
- target seen: yes
- suppressed trade recovered: yes
- cross-transport identity compatible: yes
- REST-minus-WebSocket timestamp delta: `0 us`
- same UTC minute: yes
- builder recovery required afterward: false
- Kalshi connected: no
- orders: 0
- production writes: 0

Canonical raw/manifest hashes:

- raw JSONL SHA-256:
  `8198AEBAFBA03E4331009CC2F62E0CCC27F13FA57E347A5359F81FAC18194F7F`
- manifest SHA-256:
  `A1BC96364BBB35298DC83F295EF867B98F3565AF1E06C488D76205AE23523B19`

### REST visibility behavior in canonical PASS

REST requests: 5

All five were:

`latest_visibility`

There were:

`0`

older-pagination requests.

Attempts 1 through 4 returned a latest trade ID of:

`1088550189`

The fifth latest-page attempt returned a range ending at:

`1088550221`

and therefore covered both the frozen boundary and target.

The final latest page contained 1,000 trades with range:

`1088549222 -> 1088550221`

This is direct live evidence that the bounded latest-page retry state is
required before older pagination.

## Focused regression evidence

After the final builder corroboration repair:

`38 passed in 1.32s`

Covered components include:

- exact Coinbase minute builder;
- WebSocket transport;
- runtime raw journal;
- REST recovery proof;
- REST paginator;
- visibility-lag retry behavior;
- cross-transport identity;
- builder-level duplicate corroboration.

## Safety boundary

Throughout D1-D3:

- Candidate-E model coefficients were not changed;
- strategy threshold was not changed;
- Kalshi execution was not enabled;
- no orders were created;
- no cancellations were created;
- no account writes occurred;
- no real-money execution occurred;
- the 168-hour prospective cohort was not armed.

## Result

The Coinbase completed-minute and missing-trade recovery subsystem is accepted
as validated read-only engineering evidence for the continuing Z-D runtime
implementation.

This does not by itself establish the full runtime as arm-ready.

Remaining production-shaped read-only work still includes restart-state
validation, durable-state reconciliation, storage/free-disk validation,
deployment/region benchmarking, and dashboard runtime validation.
