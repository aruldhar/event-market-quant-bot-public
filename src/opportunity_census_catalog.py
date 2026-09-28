"""Offline validation for the neutral opportunity-census candidate catalog."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

SCHEMA_VERSION = "opportunity_census_catalog.v1"
DEFAULT_CATALOG_PATH = Path("configs/opportunity_census_catalog.json")
_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_ACCESS_STATES = {"available", "authentication_required", "not_verified"}
_COLLECTION_STATES = {
    "existing_project_source_only",
    "candidate_not_collected",
    "catalog_only",
    "blocked_pending_authorization",
}


class OpportunityCensusCatalogError(RuntimeError):
    """Raised when the candidate catalog violates its neutral contract."""


def load_opportunity_census_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> dict[str, Any]:
    catalog_path = Path(path)
    try:
        with catalog_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise OpportunityCensusCatalogError(f"Could not read {catalog_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OpportunityCensusCatalogError(f"Catalog is not valid JSON: {exc}") from exc
    validate_opportunity_census_catalog(data)
    return data


def validate_opportunity_census_catalog(value: Any) -> None:
    root = _mapping(value, "catalog")
    _exact_keys(root, {"schema", "catalog_id", "reviewed_at_utc", "selection_policy", "event_venue_candidates", "comparison_classes"}, "catalog")
    if root["schema"] != SCHEMA_VERSION:
        raise OpportunityCensusCatalogError(f"catalog.schema must be {SCHEMA_VERSION!r}")
    _identifier(root["catalog_id"], "catalog.catalog_id")
    _text(root["reviewed_at_utc"], "catalog.reviewed_at_utc")

    policy = _mapping(root["selection_policy"], "catalog.selection_policy")
    _exact_keys(policy, {"preferred_candidate_id", "ranking_score_enabled", "execution_default", "notes"}, "catalog.selection_policy")
    if policy["preferred_candidate_id"] is not None:
        raise OpportunityCensusCatalogError("Neutral census must not preselect a preferred candidate")
    if policy["ranking_score_enabled"] is not False:
        raise OpportunityCensusCatalogError("Arbitrary ranking scores are disabled in census v1")
    if policy["execution_default"] != "blocked":
        raise OpportunityCensusCatalogError("Execution must remain blocked by default")
    _text(policy["notes"], "catalog.selection_policy.notes")

    venues = _list(root["event_venue_candidates"], "catalog.event_venue_candidates", nonempty=True)
    venue_ids: set[str] = set()
    for idx, raw in enumerate(venues):
        loc = f"catalog.event_venue_candidates[{idx}]"
        item = _mapping(raw, loc)
        _exact_keys(item, {"candidate_id", "name", "legal_entity", "regulatory_state", "designation_date", "operational_research_state", "public_discovery", "public_snapshot", "public_stream", "collection_state", "execution_state", "evidence_urls", "notes"}, loc)
        candidate_id = _identifier(item["candidate_id"], f"{loc}.candidate_id")
        if candidate_id in venue_ids:
            raise OpportunityCensusCatalogError(f"Duplicate candidate_id {candidate_id!r}")
        venue_ids.add(candidate_id)
        for field in ("name", "legal_entity", "regulatory_state", "designation_date", "operational_research_state", "notes"):
            _text(item[field], f"{loc}.{field}")
        for field in ("public_discovery", "public_snapshot", "public_stream"):
            if item[field] not in _ACCESS_STATES:
                raise OpportunityCensusCatalogError(f"{loc}.{field} has unsupported state {item[field]!r}")
        if item["collection_state"] not in _COLLECTION_STATES:
            raise OpportunityCensusCatalogError(f"{loc}.collection_state has unsupported state")
        if item["execution_state"] != "blocked":
            raise OpportunityCensusCatalogError(f"{loc}.execution_state must remain 'blocked'")
        urls = _list(item["evidence_urls"], f"{loc}.evidence_urls", nonempty=True)
        for uidx, url in enumerate(urls):
            _https_url(url, f"{loc}.evidence_urls[{uidx}]")

    classes = _list(root["comparison_classes"], "catalog.comparison_classes", nonempty=True)
    class_ids: set[str] = set()
    for idx, raw in enumerate(classes):
        loc = f"catalog.comparison_classes[{idx}]"
        item = _mapping(raw, loc)
        _exact_keys(item, {"class_id", "name", "research_state", "execution_state"}, loc)
        class_id = _identifier(item["class_id"], f"{loc}.class_id")
        if class_id in class_ids:
            raise OpportunityCensusCatalogError(f"Duplicate class_id {class_id!r}")
        class_ids.add(class_id)
        _text(item["name"], f"{loc}.name")
        _text(item["research_state"], f"{loc}.research_state")
        if item["execution_state"] != "blocked":
            raise OpportunityCensusCatalogError(f"{loc}.execution_state must remain 'blocked'")

    required_classes = {
        "event_markets", "crypto_spot", "crypto_perpetuals", "crypto_options",
        "traditional_futures", "traditional_options", "sports_exchange_betting",
        "weather_event_contracts", "macro_event_contracts",
    }
    missing = required_classes - class_ids
    if missing:
        raise OpportunityCensusCatalogError(f"Catalog omits required comparison classes: {sorted(missing)}")


def summarize_opportunity_census_catalog(data: Mapping[str, Any]) -> dict[str, Any]:
    venues = list(data["event_venue_candidates"])
    classes = list(data["comparison_classes"])
    return {
        "schema": data["schema"],
        "catalog_id": data["catalog_id"],
        "event_venue_candidate_count": len(venues),
        "comparison_class_count": len(classes),
        "public_discovery_available_count": sum(v["public_discovery"] == "available" for v in venues),
        "candidate_not_collected_count": sum(v["collection_state"] == "candidate_not_collected" for v in venues),
        "execution_enabled_count": sum(v["execution_state"] != "blocked" for v in venues),
        "preferred_candidate_id": data["selection_policy"]["preferred_candidate_id"],
        "ranking_score_enabled": data["selection_policy"]["ranking_score_enabled"],
    }


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpportunityCensusCatalogError(f"{location} must be an object")
    return value


def _list(value: Any, location: str, *, nonempty: bool = False) -> list[Any]:
    if not isinstance(value, list):
        raise OpportunityCensusCatalogError(f"{location} must be a list")
    if nonempty and not value:
        raise OpportunityCensusCatalogError(f"{location} must not be empty")
    return value


def _exact_keys(value: Mapping[str, Any], keys: set[str], location: str) -> None:
    actual = set(value)
    if actual != keys:
        raise OpportunityCensusCatalogError(f"{location} keys mismatch; missing={sorted(keys-actual)}, extra={sorted(actual-keys)}")


def _identifier(value: Any, location: str) -> str:
    _text(value, location)
    if not _ID_RE.fullmatch(value):
        raise OpportunityCensusCatalogError(f"{location} must be a stable lowercase identifier")
    return value


def _text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpportunityCensusCatalogError(f"{location} must be non-empty text")
    return value


def _https_url(value: Any, location: str) -> None:
    _text(value, location)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise OpportunityCensusCatalogError(f"{location} must be an https URL")
