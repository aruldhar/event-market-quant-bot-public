"""Offline validation for the project's machine-readable source registry.

The registry records source identity, authority, authentication, timestamps, and
fail-closed quality policy. It does not perform network requests or promote a
source to trading use.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


REGISTRY_SCHEMA = "source_registry.v1"
DEFAULT_SOURCE_REGISTRY_PATH = Path("configs/source_registry.json")

VALIDATION_STATES = {
    "unresolved",
    "observed",
    "documented",
    "validated",
    "rejected",
}
COLLECTION_STATES = {
    "active",
    "documented_not_collected",
    "proposed",
    "rejected",
}
AUTHENTICATION_MODES = {
    "none",
    "api_key_header",
    "kalshi_signed",
    "kalshi_signed_entitlement",
    "not_applicable",
}
TRANSPORTS = {
    "https_rest",
    "https_web",
    "documentation",
    "wss",
}
SETTLEMENT_ROLES = {
    "none",
    "contract_rule_authority",
    "numerical_index_authority",
}
REQUIRED_QUALITY_STATES = {
    "stale_data",
    "clock_error",
    "incomplete_response",
    "schema_drift",
    "source_unavailable",
    "settlement_authority_unresolved",
}
COLLECTION_ACTIONS = {
    "continue_archive_only",
    "stop_collection",
    "not_applicable",
}
ENFORCEMENT_STATES = {
    "defined_not_implemented",
    "partially_implemented",
    "implemented",
}

_IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


class SourceRegistryError(RuntimeError):
    """Raised when the source registry violates its declared contract."""


def load_source_registry(
    path: str | Path = DEFAULT_SOURCE_REGISTRY_PATH,
) -> dict[str, Any]:
    """Load and validate a source registry JSON document."""

    registry_path = Path(path)
    try:
        with registry_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except OSError as exc:
        raise SourceRegistryError(
            f"Could not read source registry {registry_path}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SourceRegistryError(
            f"Source registry {registry_path} is not valid JSON: {exc}"
        ) from exc

    validate_source_registry_document(data)
    return data


def validate_source_registry_document(data: Any) -> None:
    """Validate one decoded source-registry document.

    The validator is intentionally strict about identity, evidence, references,
    and fail-closed policy. It does not attempt to contact any external source.
    """

    root = _mapping(data, "registry")
    _exact_required_keys(
        root,
        {
            "schema",
            "registry_id",
            "reviewed_at_utc",
            "sources",
            "quality_policies",
        },
        "registry",
    )

    if root["schema"] != REGISTRY_SCHEMA:
        raise SourceRegistryError(
            f"registry.schema must be {REGISTRY_SCHEMA!r}"
        )
    _identifier(root["registry_id"], "registry.registry_id")
    _utc_timestamp(root["reviewed_at_utc"], "registry.reviewed_at_utc")

    sources = _list(root["sources"], "registry.sources", nonempty=True)
    policies = _list(
        root["quality_policies"],
        "registry.quality_policies",
        nonempty=True,
    )

    source_ids: set[str] = set()
    source_policy_refs: dict[str, str] = {}
    for index, source_value in enumerate(sources):
        location = f"registry.sources[{index}]"
        source = _mapping(source_value, location)
        _validate_source(source, location)
        source_id = source["source_id"]
        if source_id in source_ids:
            raise SourceRegistryError(f"Duplicate source_id {source_id!r}")
        source_ids.add(source_id)
        source_policy_refs[source_id] = source["quality_policy_id"]

    policy_ids: set[str] = set()
    policy_scopes: dict[str, set[str]] = {}
    for index, policy_value in enumerate(policies):
        location = f"registry.quality_policies[{index}]"
        policy = _mapping(policy_value, location)
        scope = _validate_quality_policy(policy, location)
        policy_id = policy["policy_id"]
        if policy_id in policy_ids:
            raise SourceRegistryError(f"Duplicate policy_id {policy_id!r}")
        policy_ids.add(policy_id)
        policy_scopes[policy_id] = scope

    for source_id, policy_id in source_policy_refs.items():
        if policy_id not in policy_ids:
            raise SourceRegistryError(
                f"Source {source_id!r} references unknown quality policy "
                f"{policy_id!r}"
            )
        if source_id not in policy_scopes[policy_id]:
            raise SourceRegistryError(
                f"Quality policy {policy_id!r} does not include source "
                f"{source_id!r} in its scope"
            )

    for policy_id, scope in policy_scopes.items():
        unknown = scope - source_ids
        if unknown:
            raise SourceRegistryError(
                f"Quality policy {policy_id!r} references unknown sources: "
                f"{sorted(unknown)}"
            )


def summarize_source_registry(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact deterministic summary for CLI and tests."""

    sources = data["sources"]
    policies = data["quality_policies"]
    return {
        "schema": data["schema"],
        "registry_id": data["registry_id"],
        "source_count": len(sources),
        "quality_policy_count": len(policies),
        "validated_source_count": sum(
            1 for source in sources if source["validation_state"] == "validated"
        ),
        "unresolved_source_count": sum(
            1 for source in sources if source["validation_state"] == "unresolved"
        ),
        "unresolved_settlement_source_count": sum(
            1
            for source in sources
            if source["settlement_role"] != "none"
            and source["settlement_validation_state"] == "unresolved"
        ),
    }


def _validate_source(source: Mapping[str, Any], location: str) -> None:
    _exact_required_keys(
        source,
        {
            "source_id",
            "name",
            "owner",
            "roles",
            "market_scope",
            "transport",
            "endpoint_identity",
            "official_urls",
            "authentication",
            "expected_timestamp_fields",
            "settlement_role",
            "settlement_validation_state",
            "collection_state",
            "validation_state",
            "quality_policy_id",
            "raw_source_name",
            "evidence",
            "notes",
        },
        location,
    )

    _identifier(source["source_id"], f"{location}.source_id")
    _nonempty_string(source["name"], f"{location}.name")
    _nonempty_string(source["owner"], f"{location}.owner")
    _string_list(source["roles"], f"{location}.roles", nonempty=True)
    _string_list(source["market_scope"], f"{location}.market_scope", nonempty=True)
    _enum(source["transport"], TRANSPORTS, f"{location}.transport")
    _identifier(source["quality_policy_id"], f"{location}.quality_policy_id")
    _nullable_nonempty_string(
        source["raw_source_name"],
        f"{location}.raw_source_name",
    )
    _nonempty_string(source["notes"], f"{location}.notes")

    endpoint = _mapping(source["endpoint_identity"], f"{location}.endpoint_identity")
    _exact_required_keys(
        endpoint,
        {"method", "base_url", "path_template"},
        f"{location}.endpoint_identity",
    )
    method = endpoint["method"]
    if method not in {"GET", "DOCUMENT", "SUBSCRIBE"}:
        raise SourceRegistryError(
            f"{location}.endpoint_identity.method must be GET, DOCUMENT, "
            "or SUBSCRIBE"
        )

    transport = source["transport"]
    base_url_location = f"{location}.endpoint_identity.base_url"
    if transport == "wss":
        if method != "SUBSCRIBE":
            raise SourceRegistryError(
                f"{location}.endpoint_identity.method must be SUBSCRIBE "
                "when transport is 'wss'"
            )
        _wss_url(endpoint["base_url"], base_url_location)
    else:
        if transport == "https_rest" and method != "GET":
            raise SourceRegistryError(
                f"{location}.endpoint_identity.method must be GET when "
                "transport is 'https_rest'"
            )
        if transport in {"https_web", "documentation"} and method != "DOCUMENT":
            raise SourceRegistryError(
                f"{location}.endpoint_identity.method must be DOCUMENT when "
                f"transport is {transport!r}"
            )
        _https_url(endpoint["base_url"], base_url_location)

    path_template = endpoint["path_template"]
    _nonempty_string(path_template, f"{location}.endpoint_identity.path_template")
    if method == "GET" and not path_template.startswith("/"):
        raise SourceRegistryError(
            f"{location}.endpoint_identity.path_template must start with '/'"
        )

    official_urls = _list(
        source["official_urls"],
        f"{location}.official_urls",
        nonempty=True,
    )
    for index, url in enumerate(official_urls):
        _https_url(url, f"{location}.official_urls[{index}]")

    authentication = _mapping(
        source["authentication"],
        f"{location}.authentication",
    )
    _exact_required_keys(
        authentication,
        {"mode", "validation_state", "conflict_status", "notes"},
        f"{location}.authentication",
    )
    _enum(
        authentication["mode"],
        AUTHENTICATION_MODES,
        f"{location}.authentication.mode",
    )
    _enum(
        authentication["validation_state"],
        VALIDATION_STATES,
        f"{location}.authentication.validation_state",
    )
    _nonempty_string(
        authentication["conflict_status"],
        f"{location}.authentication.conflict_status",
    )
    _nonempty_string(
        authentication["notes"],
        f"{location}.authentication.notes",
    )

    timestamps = _list(
        source["expected_timestamp_fields"],
        f"{location}.expected_timestamp_fields",
    )
    timestamp_paths: set[str] = set()
    for index, timestamp_value in enumerate(timestamps):
        timestamp_location = f"{location}.expected_timestamp_fields[{index}]"
        timestamp = _mapping(timestamp_value, timestamp_location)
        _exact_required_keys(
            timestamp,
            {"json_path", "meaning", "required", "validation_state"},
            timestamp_location,
        )
        json_path = timestamp["json_path"]
        _nonempty_string(json_path, f"{timestamp_location}.json_path")
        if not json_path.startswith("$"):
            raise SourceRegistryError(
                f"{timestamp_location}.json_path must start with '$'"
            )
        if json_path in timestamp_paths:
            raise SourceRegistryError(
                f"Duplicate timestamp json_path {json_path!r} in {source['source_id']!r}"
            )
        timestamp_paths.add(json_path)
        _nonempty_string(timestamp["meaning"], f"{timestamp_location}.meaning")
        if not isinstance(timestamp["required"], bool):
            raise SourceRegistryError(
                f"{timestamp_location}.required must be a boolean"
            )
        _enum(
            timestamp["validation_state"],
            VALIDATION_STATES,
            f"{timestamp_location}.validation_state",
        )

    _enum(
        source["settlement_role"],
        SETTLEMENT_ROLES,
        f"{location}.settlement_role",
    )
    _enum(
        source["settlement_validation_state"],
        VALIDATION_STATES,
        f"{location}.settlement_validation_state",
    )
    _enum(
        source["collection_state"],
        COLLECTION_STATES,
        f"{location}.collection_state",
    )
    _enum(
        source["validation_state"],
        VALIDATION_STATES,
        f"{location}.validation_state",
    )

    evidence = _list(source["evidence"], f"{location}.evidence")
    for index, evidence_value in enumerate(evidence):
        evidence_location = f"{location}.evidence[{index}]"
        item = _mapping(evidence_value, evidence_location)
        _exact_required_keys(
            item,
            {"url", "claim", "reviewed_at_utc"},
            evidence_location,
        )
        _https_url(item["url"], f"{evidence_location}.url")
        _nonempty_string(item["claim"], f"{evidence_location}.claim")
        _utc_timestamp(
            item["reviewed_at_utc"],
            f"{evidence_location}.reviewed_at_utc",
        )

    if source["validation_state"] in {"documented", "validated"} and not evidence:
        raise SourceRegistryError(
            f"{location}.evidence must not be empty when validation_state is "
            f"{source['validation_state']!r}"
        )
    if (
        source["settlement_role"] != "none"
        and source["settlement_validation_state"] in {"documented", "validated"}
        and not evidence
    ):
        raise SourceRegistryError(
            f"{location} requires evidence for a documented settlement role"
        )


def _validate_quality_policy(
    policy: Mapping[str, Any],
    location: str,
) -> set[str]:
    _exact_required_keys(
        policy,
        {
            "policy_id",
            "name",
            "scope_source_ids",
            "decision_use_default",
            "conditions",
            "notes",
        },
        location,
    )
    _identifier(policy["policy_id"], f"{location}.policy_id")
    _nonempty_string(policy["name"], f"{location}.name")
    scope_values = _string_list(
        policy["scope_source_ids"],
        f"{location}.scope_source_ids",
        nonempty=True,
    )
    scope = set(scope_values)
    if len(scope) != len(scope_values):
        raise SourceRegistryError(
            f"{location}.scope_source_ids must not contain duplicates"
        )
    if policy["decision_use_default"] != "blocked":
        raise SourceRegistryError(
            f"{location}.decision_use_default must be 'blocked'"
        )
    _nonempty_string(policy["notes"], f"{location}.notes")

    conditions = _list(
        policy["conditions"],
        f"{location}.conditions",
        nonempty=True,
    )
    states: set[str] = set()
    for index, condition_value in enumerate(conditions):
        condition_location = f"{location}.conditions[{index}]"
        condition = _mapping(condition_value, condition_location)
        _exact_required_keys(
            condition,
            {
                "state",
                "trigger",
                "collection_action",
                "decision_action",
                "enforcement_state",
                "resolution_requirement",
            },
            condition_location,
        )
        state = condition["state"]
        _nonempty_string(state, f"{condition_location}.state")
        if state in states:
            raise SourceRegistryError(
                f"Duplicate quality state {state!r} in {policy['policy_id']!r}"
            )
        states.add(state)
        _nonempty_string(condition["trigger"], f"{condition_location}.trigger")
        _enum(
            condition["collection_action"],
            COLLECTION_ACTIONS,
            f"{condition_location}.collection_action",
        )
        if condition["decision_action"] != "block":
            raise SourceRegistryError(
                f"{condition_location}.decision_action must be 'block'"
            )
        _enum(
            condition["enforcement_state"],
            ENFORCEMENT_STATES,
            f"{condition_location}.enforcement_state",
        )
        _nonempty_string(
            condition["resolution_requirement"],
            f"{condition_location}.resolution_requirement",
        )

    missing_states = REQUIRED_QUALITY_STATES - states
    if missing_states:
        raise SourceRegistryError(
            f"{location}.conditions is missing fail-closed states: "
            f"{sorted(missing_states)}"
        )
    return scope


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SourceRegistryError(f"{location} must be an object")
    return value


def _list(value: Any, location: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        raise SourceRegistryError(f"{location} must be a list")
    if nonempty and not value:
        raise SourceRegistryError(f"{location} must not be empty")
    return value


def _string_list(
    value: Any,
    location: str,
    *,
    nonempty: bool = False,
) -> list[str]:
    values = _list(value, location, nonempty=nonempty)
    for index, item in enumerate(values):
        _nonempty_string(item, f"{location}[{index}]")
    return values


def _exact_required_keys(
    value: Mapping[str, Any],
    required: set[str],
    location: str,
) -> None:
    missing = required - set(value)
    extra = set(value) - required
    if missing:
        raise SourceRegistryError(
            f"{location} is missing required keys: {sorted(missing)}"
        )
    if extra:
        raise SourceRegistryError(
            f"{location} contains unsupported keys: {sorted(extra)}"
        )


def _identifier(value: Any, location: str) -> None:
    _nonempty_string(value, location)
    if not _IDENTIFIER_RE.fullmatch(value):
        raise SourceRegistryError(
            f"{location} must use lowercase letters, numbers, dots, dashes, or underscores"
        )


def _nonempty_string(value: Any, location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SourceRegistryError(f"{location} must be a non-empty string")


def _nullable_nonempty_string(value: Any, location: str) -> None:
    if value is None:
        return
    _nonempty_string(value, location)


def _enum(value: Any, allowed: set[str], location: str) -> None:
    if value not in allowed:
        raise SourceRegistryError(
            f"{location} must be one of {sorted(allowed)}; observed {value!r}"
        )


def _https_url(value: Any, location: str) -> None:
    _nonempty_string(value, location)
    if not value.startswith("https://"):
        raise SourceRegistryError(f"{location} must be an https URL")


def _wss_url(value: Any, location: str) -> None:
    _nonempty_string(value, location)
    if not value.startswith("wss://"):
        raise SourceRegistryError(f"{location} must be a wss URL")


def _utc_timestamp(value: Any, location: str) -> None:
    _nonempty_string(value, location)
    if not value.endswith("Z"):
        raise SourceRegistryError(f"{location} must end with 'Z'")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SourceRegistryError(
            f"{location} must be an ISO-8601 UTC timestamp"
        ) from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise SourceRegistryError(f"{location} must be UTC")
