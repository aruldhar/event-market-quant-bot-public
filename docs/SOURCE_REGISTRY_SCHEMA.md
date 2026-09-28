# Source Registry Schema

## Purpose

`configs/source_registry.json` is the machine-readable inventory of every external source that may affect this project. It prevents a source from silently acquiring authority merely because data is available or because a collector happened to work.

The registry is validated offline by `src/source_registry.py` and `validate_source_registry.py`. Validation checks the registry contract only; it does not contact external systems, test credentials, or prove current reachability.

## Version

The current schema identifier is:

```text
source_registry.v1
```

A schema change requires a new version, tests, and a decision-log entry.

## Top-level fields

- `schema`: exact schema identifier;
- `registry_id`: stable project-level registry identifier;
- `reviewed_at_utc`: UTC timestamp for the official-source review represented by the file;
- `sources`: source records;
- `quality_policies`: fail-closed policies referenced by source records.

## Source identity

Each source record has a stable `source_id`. Endpoint identity is separated into:

- owner;
- roles;
- market scope;
- transport;
- base URL;
- method or subscription classification;
- path or channel template;
- official evidence URLs.

Separate IDs are used for the Kalshi market list, single-market metadata, REST order book, written KXBTC15M rules, authenticated CF Benchmarks WebSocket channel, and underlying CF Benchmarks BRTI. They have different responsibilities and must not be treated as interchangeable.

## Transport and method rules

Allowed transports are:

- `https_rest`;
- `https_web`;
- `documentation`;
- `wss`.

The validator enforces these pairs:

- `https_rest` → `GET` and an `https://` base URL;
- `https_web` or `documentation` → `DOCUMENT` and an `https://` base URL;
- `wss` → `SUBSCRIBE` and a `wss://` base URL.

A WebSocket source's `path_template` identifies its channel and subscription parameters rather than an HTTP path.

## Validation states

Allowed source and evidence states are:

- `unresolved`: official evidence is insufficient or contradictory;
- `observed`: behavior was seen, but official documentation or operational validation is incomplete;
- `documented`: an official source describes the behavior, but the project has not fully validated it operationally;
- `validated`: official evidence and applicable project tests or observations support the specific claim;
- `rejected`: the source or claim must not be used.

`validated` never means profitable, complete, or suitable for trading.

## Collection states

- `active`: currently used by read-only collectors;
- `documented_not_collected`: identified and documented but not collected;
- `proposed`: candidate source not yet accepted;
- `rejected`: prohibited from use.

The authenticated CF Benchmarks WebSocket and REST sources are `documented_not_collected`.

## Authentication

Authentication is recorded separately from source validation. Current modes are:

- `none`;
- `kalshi_signed`;
- `kalshi_signed_entitlement`;
- `not_applicable`.

A source may be officially documented but remain outside the current authorization. Registry presence never authorizes a credential, entitlement, or collector.

## Timestamp fields

`expected_timestamp_fields` records only official or carefully bounded meanings. Each entry includes:

- JSON path or decoded nested-field notation;
- plain-language meaning;
- whether the field is required for the current collector;
- validation state.

A timestamp entry does not automatically establish freshness. Market `updated_time`, for example, is not an order-book observation timestamp. The representative KXBTC15M response also demonstrated that `expiration_time` is not the 15-minute comparison boundary.

## Settlement roles

- `none`: no direct settlement authority;
- `contract_rule_authority`: defines the written market contract;
- `numerical_index_authority`: supplies the numerical reference used by the rules.

The Kalshi WebSocket delivery source has `settlement_role: none` because it transports values and documented averages but does not replace CF Benchmarks as the numerical index authority.

A complete settlement model requires written-rule authority, numerical index authority, exact comparison and timing procedures, rounding, corrections, missing-data behavior, and fallback rules.

## Quality-policy contract

Every source references a policy. The current policy must include all of these fail-closed states:

- `stale_data`;
- `clock_error`;
- `incomplete_response`;
- `schema_drift`;
- `source_unavailable`;
- `settlement_authority_unresolved`.

Every state must set `decision_action` to `block`. Collection may continue only as archive-only research when the policy says preserving evidence is still safe.

## Validation command

```powershell
.\.venv\Scripts\python.exe validate_source_registry.py
```

A pass proves that:

- the JSON is valid;
- required fields and enums are present;
- IDs are unique;
- endpoint transport and method are consistent;
- HTTPS evidence and WSS endpoint schemes are correct;
- policy references resolve;
- every policy contains the mandatory fail-closed states;
- no quality condition permits decision use.

It does not prove current availability, source freshness, credential access, complete settlement semantics, executable fills, or profitability.
