# Collection Run Manifest Schema

## Purpose

A collection manifest is the durable receipt for one command-line data-collection run. It links the run configuration and code identity to the raw, runtime-event, and derived files produced by that run, then stores recomputable integrity metadata for those files.

The manifest does **not** replace the raw archive or runtime log. It answers a different question: which artifacts belonged to this run, did the process finish, and do those artifacts still match the recorded hashes and counts?

## Storage layout

```text
data/manifests/YYYY/MM/DD/
└── <collector>_<UTC start time>_<run id>.json
```

Manifest files are runtime data and remain ignored by Git.

## Schema versions

- Current collector version: `collection_run_manifest.v2`
- Historical supported version: `collection_run_manifest.v1`

Version 2 adds integrity-tracked structured runtime-event artifacts and runtime-event summary counts. The offline validator remains backward compatible with completed v1 manifests.

## Lifecycle

1. The collector writes a `running` manifest before making API requests.
2. The collector appends runtime lifecycle events and raw API exchanges.
3. The collector may produce derived CSV rows after raw persistence and endpoint validation.
4. On normal workload completion, it writes `collector.completed`.
5. It inspects every declared artifact and atomically replaces the manifest with `status: completed`.
6. On an exception, it writes `collector.failed` when possible and atomically replaces the manifest with `status: failed`.
7. If the process is terminated before either final update, the durable state remains `running`. The validator rejects that run as incomplete.

Atomic replacement means the program writes a complete temporary JSON file, flushes and fsyncs it, and then asks the operating system to replace the previous manifest. This avoids leaving a half-written JSON document when an update is interrupted.

## Top-level fields

- `schema_version`: Manifest envelope version.
- `run_id`: Unique identifier for the collector run.
- `collector.name`: Script or collector that created the run.
- `status`: `running`, `completed`, or `failed`.
- `started_at_utc`: Local UTC wall-clock start time.
- `completed_at_utc`: Local UTC completion/failure time, or `null` while running.
- `arguments`: Sanitized command arguments. Credential-like names are redacted.
- `code`: Git commit, tracked-worktree dirty state, and any Git lookup error.
- `environment`: Python implementation/version and operating-system platform string.
- `source_sessions`: Raw-source session identifiers associated with the run.
- `files`: Final integrity descriptors for raw, runtime-event, and derived artifacts.
- `summary`: Totals recomputed from the file descriptors.
- `result`: Collector-specific non-sensitive result counts.
- `failure`: Exception type/message and artifact-inspection errors for failed runs.

## Git identity

`code` contains:

- `git_commit`: The output of `git rev-parse HEAD`, or `null` if unavailable.
- `git_worktree_dirty`: Whether tracked files had staged or unstaged changes at run start. Ignored runtime data does not make the worktree dirty.
- `git_error`: Diagnostic text if Git identity could not be captured.

A dirty worktree is not hidden or automatically rejected. It is recorded because a commit hash alone cannot identify uncommitted code changes.

## Raw artifact descriptor

A `raw_api_archive` descriptor contains:

- `path`: Repository-relative or explicit absolute path descriptor.
- `size_bytes`: Exact file size.
- `sha256`: SHA-256 of the complete file bytes.
- `record_count`: Number of nonblank JSONL records.
- `error_record_count`: Number of records whose `error` field is non-null.
- `schema_versions`: Raw envelope versions observed in the file.
- `session_ids`: Source session IDs observed in the file.

During inspection, every line must parse as JSON, satisfy the required `raw_http_exchange.v1` envelope, have a nonnegative and internally consistent monotonic duration, and use a unique `request_id` within that file.

## Runtime-event artifact descriptor

A `runtime_event_log` descriptor contains:

- `path`: Repository-relative or explicit absolute path descriptor.
- `size_bytes`: Exact file size.
- `sha256`: SHA-256 of the complete file bytes.
- `event_count`: Number of event records.
- `error_event_count`: Number of `error` or `critical` severity events.
- `schema_versions`: Runtime-event envelope versions observed.
- `run_ids`: Run IDs observed in the file.
- `collectors`: Collector names observed in the file.
- `event_names`: Stable event names observed in the file.
- `severity_counts`: Count for each supported severity.

Inspection also requires valid UTC timestamps, lowercase dot-separated event names, nondecreasing monotonic readings, contiguous one-based sequences, and unique event IDs. Before a v2 manifest can be finalized as completed, its one runtime-event file must match the manifest run ID and collector, contain both `collector.started` and `collector.completed`, and contain no `collector.failed` or critical event.

Offline validation additionally proves that every persisted raw request has exactly one matching `api.request.succeeded` or `api.request.failed` event, that the event agrees with the raw record's error state, and that every non-null runtime correlation resolves to a raw record declared by the run.

See `RUNTIME_OBSERVABILITY_SCHEMA.md` for event semantics.

## Derived CSV descriptor

A `derived_csv` descriptor contains:

- `path`: Repository-relative or explicit absolute path descriptor.
- `size_bytes`: Exact file size.
- `sha256`: SHA-256 of the complete file bytes.
- `data_row_count`: Number of rows after the header.
- `columns`: Header names in stored order.

For `record_orderbook`, the validator additionally reconciles every CSV row to exactly one successful derivable raw request and proves that every successful derivable raw order-book record appears exactly once in the CSV.

## Summary fields

Both versions contain:

- `raw_file_count`
- `raw_record_count`
- `raw_error_record_count`
- `derived_csv_count`
- `derived_row_count`

Version 2 also contains:

- `runtime_event_file_count`
- `runtime_event_count`
- `runtime_error_event_count`

## Completion semantics

`status: completed` means the collector reached its normal end and successfully finalized the manifest. It does not mean every API request succeeded. Recoverable request failures remain visible in raw records, runtime events, and collector result counts.

`collector.completed` means the collector workload reached its normal end and was ready for manifest finalization. The manifest remains authoritative. If finalization fails, the run is not completed even if that workload event was written.

`status: failed` means the run ended through an exception. `status: running` after the process is gone indicates an interrupted or crashed run.

## Validation command

Validate a specific manifest:

```powershell
.\.venv\Scripts\python.exe .\validate_run_manifest.py `
    .\data\manifests\YYYY\MM\DD\<manifest>.json
```

Validate the newest manifest:

```powershell
.\.venv\Scripts\python.exe .\validate_run_manifest.py
```

A passing result requires:

- The manifest schema is supported.
- Run status is `completed`.
- Every referenced file exists.
- Every artifact parses and satisfies its baseline envelope.
- Recomputed hashes, sizes, counts, schemas, columns, sessions, run IDs, collectors, event names, and totals match the manifest.
- Current v2 lifecycle, severity, and runtime-to-raw correlation rules pass.
- `record_orderbook` raw-to-derived lineage rules pass.

A passing integrity check is not evidence that source fields have the assumed economic meaning, that the settlement source is correct, that fills are executable, or that a trading strategy is profitable.
