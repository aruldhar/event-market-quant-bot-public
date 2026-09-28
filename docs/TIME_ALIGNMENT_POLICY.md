# Time Alignment Policy

Status: checkpoint-07 venue-neutral design. This document defines causal timing rules for future multi-source research. It does not enable decision use.

## Core principle

> **Local monotonic first-seen receipt time defines causal availability on one machine. Source timestamps are preserved for source semantics and diagnostics. Absolute cross-clock comparisons require explicit clock-health evidence.**

This rule applies regardless of venue, category, or strategy.

## Why this matters

A backtest can accidentally use information that existed at a remote source but had not reached the local process yet.

For any candidate feature observation `F` and decision-market observation `D`, a live-causal join may use `F` only when:

```text
F.local_receive_monotonic_ns <= D.local_available_monotonic_ns
```

The source event timestamp alone cannot satisfy this condition.

## Timestamp layers

### Source event time

Timestamp assigned by the upstream source to the underlying event/message/snapshot.

Use for:

- source semantics;
- source-order analysis;
- diagnostics;
- event-time reconstruction.

Do not use as proof of local causal availability.

### Relay/intermediary time

Some sources add an intermediary receive/publication timestamp.

Preserve it as a separate field. Do not merge it with source event time or local receipt time.

### Local receive UTC

Wall-clock UTC captured as close as practical to receipt.

Use for:

- human-readable audit;
- across-run correlation;
- apparent source-to-local timing diagnostics after clock health is established.

Wall time may be adjusted and therefore is not the primary same-machine causal ordering mechanism.

### Local receive monotonic time

Capture `time.monotonic_ns()` as close as practical to receipt.

Use for:

- same-process causal ordering;
- elapsed-time measurements;
- as-of joins;
- staleness on one machine.

The monotonic clock has no portable absolute UTC meaning; compare differences and ordering only.

## Request/response sources

For a polled REST response without a documented remote observation timestamp, preserve at least:

```text
request_start_utc
request_start_monotonic_ns
response_receive_utc
response_receive_monotonic_ns
elapsed_monotonic_ns
```

Conservative causal availability is:

```text
local_available_monotonic_ns = response_receive_monotonic_ns
```

Do not backdate the snapshot to request-start time.

The request interval remains uncertainty about when the remote state was formed.

## Streaming sources

For each received frame/message, preserve receipt timing before venue-specific transformation:

```text
source_message_time_utc     # when supplied
relay_or_publication_time   # when supplied
local_receive_utc
local_receive_monotonic_ns
connection/session_id
alignment_epoch_id
```

Normalized observations inherit exact raw-message lineage.

## Recovered or replayed data is not retroactively live-available

If a gap is detected and missing records are later recovered from REST, replay, or another official recovery mechanism:

- analytical/event-time reconstruction may place them at original source event time;
- live-causal reconstruction must make them available only at the first local recovery receipt time.

Formally:

```text
recovered.live_available_monotonic_ns
    = recovery_first_seen_monotonic_ns
```

Never let a backtest benefit from recovered information before the live system actually learned it.

## Two dataset views

### First-seen / live-causal view

Use for:

- chronological prediction tests;
- paper decision reconstruction;
- live-equivalent feature generation.

Rules:

- order by local monotonic first-seen time;
- no retroactive insertion;
- continuity gaps block affected decision periods;
- recovered data becomes available only when recovered.

### Event-time / reconstructed analytical view

Use for:

- diagnostics;
- source-latency studies;
- gap reconstruction;
- provider-history analysis.

This view may order by source time/sequence/ID when semantics are established, but it must never be silently substituted for the live-causal dataset.

## Alignment epochs

`alignment_epoch_id` identifies a period where local timing and source continuity are considered compatible.

Start a new epoch after any material timing/continuity reset such as:

- process restart;
- streaming reconnect;
- unresolved sequence/trade/message gap;
- ambiguous out-of-order behavior;
- source-health failure;
- schema drift;
- local clock-health failure;
- detected wall-clock discontinuity.

Do not silently join causal observations across incompatible epochs.

## Continuity rules are source-specific

Do not assume every feed uses consecutive sequence numbers or trade IDs.

Before using a field as a completeness check, official documentation and bounded live evidence must establish its semantics for the exact subscription/endpoint.

Preserve source identifiers and sequences even when they are not yet sufficient to prove completeness.

## Apparent source-to-local latency

When local UTC health is acceptable:

```text
apparent_source_to_local_ms
    = local_receive_utc - source_event_or_publication_utc
```

This can include:

- remote clock error;
- publication/relay delay;
- network delay;
- local clock error;
- runtime scheduling delay.

Therefore it is an **apparent latency diagnostic**, not direct one-way network latency.

Negative or surprising values are evidence to preserve and investigate, not values to clamp.

## Windows clock-health evidence

The canonical environment is Windows.

A future synchronized sub-second experiment should first inspect the configured Windows time source, then preserve clock-health evidence such as:

```powershell
w32tm /query /source
w32tm /query /status
w32tm /stripchart /computer:<reported-time-source> /dataonly /samples:5 /rdtsc
```

Preserve:

- source identity;
- probe UTC/monotonic timing;
- NTP offset samples;
- round-trip-delay samples;
- command/parse status;
- derived uncertainty proxy;
- pass/fail result.

## Proposed uncertainty proxy

This is a project engineering hypothesis, not a Microsoft guarantee:

```text
sample_uncertainty_proxy_i
    = abs(NtpOffset_i) + RoundtripDelay_i / 2

clock_uncertainty_proxy
    = max(sample_uncertainty_proxy_i)
```

Initial proposed sub-second research gate:

- at least 5 valid samples;
- `clock_uncertainty_proxy <= 250 ms`;
- evidence age <= 15 minutes;
- no later wall-clock discontinuity.

The 250 ms value is a starting bound to measure, not an accepted universal threshold. Tighten or relax only with documented evidence appropriate to the strategy horizon.

## Wall-clock discontinuity detection

At a healthy anchor:

```text
anchor_utc_ns
anchor_monotonic_ns
```

Later:

```text
expected_utc_ns
    = anchor_utc_ns
      + (current_monotonic_ns - anchor_monotonic_ns)

wall_clock_deviation_ns
    = observed_current_utc_ns - expected_utc_ns
```

For a sub-second synchronized experiment, an initial proposed trigger is:

```text
abs(wall_clock_deviation) > 250 ms -> clock_error
```

On failure:

- end the current alignment epoch;
- block synchronized causal decision use;
- preserve raw data where safe;
- require fresh clock-health evidence before a new epoch.

## Staleness is source- and strategy-specific

A 5-second old quote may be unusable for a 15-second strategy but perfectly adequate for a multi-day census statistic.

Therefore there is no global `max_age`.

Every later strategy/source contract must declare:

- what object becomes stale;
- which clock measures age;
- threshold;
- evidence for threshold;
- collection action;
- decision action.

Until a threshold exists, decision use requiring freshness remains blocked.

## Opportunity census timing

The first opportunity census is **not** a latency-arbitrage experiment.

It should still capture local UTC and monotonic receipt timing, but it may compare slower market-quality metrics without claiming physical simultaneity across venues.

Examples appropriate for census v1:

- market availability;
- spread distributions from repeated snapshots;
- depth/size distributions where available;
- activity/volume/open-interest metadata;
- data completeness;
- lifecycle/settlement evidence.

Claims such as `venue A reprices 120 ms slower than venue B` require a later synchronized-clock experiment and must not be inferred from unsynchronized census snapshots.

## Cross-source as-of join for later research

For decision observation `D`:

1. verify target-market source health;
2. verify feature-source health;
3. verify compatible alignment epochs;
4. verify clock-health gate if absolute UTC comparison is needed;
5. select only feature observations first-seen locally at or before `D.local_available_monotonic_ns`;
6. carry raw lineage and timing uncertainty into the derived row;
7. block on continuity ambiguity instead of interpolating silently.

## Failure states

### `clock_error`

Clock probe failure, uncertainty over accepted bound, stale clock evidence, or wall-clock discontinuity.

Decision action: block affected synchronized use.

### `source_unavailable`

Required source cannot be reached or required raw persistence fails.

Decision action: block affected use; no silent substitute.

### `stale_data`

Required observation exceeds the strategy-specific age bound.

Decision action: block.

### `continuity_gap`

Source sequence/message/trade continuity becomes ambiguous under the source's declared rules.

Decision action: block affected interval until a new healthy epoch.

### `schema_drift`

Required source field changes name/type/units/container/meaning unexpectedly.

Action: preserve raw first, then stop/block transformation until reviewed.

## What this policy does not claim

It does not claim:

- any venue clock is perfectly accurate;
- UTC timestamps prove simultaneity;
- 250 ms is final;
- every strategy requires sub-second synchronization;
- a source sequence is necessarily consecutive;
- synchronized data creates profitability.

## Implementation order

1. build the opportunity census without latency claims;
2. identify a specific market/strategy hypothesis;
3. select the minimum required sources;
4. document exact timing/continuity semantics for those sources;
5. implement source-specific health/epoch rules;
6. run bounded synchronized collection;
7. only then perform causal lead/lag or external-feature experiments.

No step authorizes trading.

## Primary documentation references

- Python 3.11 `time`: `https://docs.python.org/3.11/library/time.html`
- Microsoft Windows Time Service tools/settings: `https://learn.microsoft.com/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings`
- Existing project source-quality policy: `docs/SOURCE_QUALITY_POLICY.md`
