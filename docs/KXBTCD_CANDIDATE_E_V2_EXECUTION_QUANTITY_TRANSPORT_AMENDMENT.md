# KXBTCD Candidate-E V2 Execution-Quantity Transport Amendment

## Checkpoint 21N-Y-A1

Classification:

`NUMERIC_TRANSPORT_REPRESENTATION_REPAIR`

Amendment fingerprint:

`2cbd8836045ae811eb4c52d48834953a54b1be3afac094be4cf349b8cac2abce`

Parent Y-A implementation fingerprint:

`b8f66b2f392df2c8711e7d6e25e64c54921b16f8f7866c243a6375aaec778949`

## Failure being repaired

The first 21N-Y-B attempt began real July 10 nonstructural Candidate-E scoring
but crashed during entry IOC simulation before any completed path artifact was
written.

Observed error example:

`level.quantity=250.00000000000068 is not aligned to 0.01`

Settlement outcomes remained closed and strategy P&L was not calculated.

## Diagnostic evidence

Paid Predexon delta parquet:

- rows checked: 5,644,964;
- `delta_fp` type: exact string;
- off-grid deltas: 0.

Preserved free snapshots:

- order-book levels checked: 13,695,870;
- off-grid snapshot quantities: 763,392;
- all 763,392 were within `1e-9` of an exact 0.01 quantity;
- materially off-cent quantities: 0.

Examples include:

- `250.00000000000068 -> 250.00`;
- `237.48000000000002 -> 237.48`;
- `224.63000000000466 -> 224.63`.

This is therefore treated as numeric transport/serialization residue rather
than economically fractional contract depth.

## Frozen repair rule

The verified replay itself remains unchanged.

Only after replay reconstruction, immediately before V2 decision/execution use:

1. find the nearest `0.01` contract quantity;
2. measure absolute residue;
3. if residue `<= 1e-9`, replace the representation with that exact Decimal;
4. if residue `> 1e-9`, fail closed.

Negative and non-finite quantities also fail closed.

The strict 0.01 IOC invariant is **not weakened**.

## Explicit non-changes

This amendment does not modify:

- raw snapshots;
- paid ticks;
- replay reconciliation;
- verified segment boundaries;
- frozen replay hashes;
- original Y-A files or fingerprint;
- Candidate E;
- ATM±5;
- thresholds;
- fees;
- latency;
- IOC rules;
- liquidation;
- re-entry.

The amended Y-B runner is a new wrapper on the frozen Y-A implementation.

## Evidence bookkeeping

The first failed Y-B attempt is permanently recorded as:

- Candidate-E nonstructural scoring: **started**;
- completed path artifact: **no**;
- settlement outcomes accessed: **no**;
- strategy P&L calculated: **no**.

No economic inference is permitted from that failed partial computation.

## Next

After Y-A1 is committed and remotely verified, rerun Y-B using:

`materialize_kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_paths_amended.py`

Settlement outcomes remain closed.
