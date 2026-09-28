"""Read-only settled-market evidence helpers for KXBTC15M.

This module deliberately records Kalshi's public settled-market fields without
turning them into settlement labels or inferred economic semantics. Raw REST
responses remain the source of truth; derived rows carry exact raw lineage.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .config import DEFAULT_PAGE_LIMIT
from .kalshi_public import (
    KalshiPublicClient,
    RawRecordReference,
    SourcedApiResponse,
)
from .run_manifest import resolve_stored_path


SETTLED_MARKET_CSV_FIELDS = [
    "run_id",
    "raw_source",
    "raw_session_id",
    "raw_request_id",
    "observed_at_utc",
    "ticker",
    "status",
    "result",
    "settlement_ts",
    "open_time",
    "close_time",
    "expected_expiration_time",
    "expiration_time",
    "latest_expiration_time",
    "occurrence_datetime",
    "expiration_value",
    "settlement_value_dollars",
    "rules_primary_present",
    "rules_secondary_present",
    "rules_primary_sha256",
    "rules_secondary_sha256",
    "rules_primary_normalized_sha256",
    "rules_secondary_normalized_sha256",
    "rules_primary_template_sha256",
    "rules_primary_template_state",
    "market_field_names_json",
]


_PRIMARY_RULE_PATTERN = re.compile(
    r"^If the simple average of the sixty seconds of CF Benchmarks' BRTI before "
    r"(?P<later_time>\d{1,2}:\d{2} [AP]M) "
    r"(?P<later_zone>EST|EDT) on "
    r"(?P<later_date>[A-Za-z]+ \d{1,2}, \d{4}) "
    r"is at least the simple average of the sixty seconds of CF Benchmarks' BRTI before "
    r"(?P<earlier_time>\d{1,2}:\d{2} [AP]M) "
    r"(?P<earlier_zone>EST|EDT) on "
    r"(?P<earlier_date>[A-Za-z]+ \d{1,2}, \d{4}), "
    r"then the market resolves to Yes\.$"
)

_PRIMARY_RULE_TEMPLATE = (
    "If the simple average of the sixty seconds of CF Benchmarks' BRTI before "
    "<close_boundary> is at least the simple average of the sixty seconds of "
    "CF Benchmarks' BRTI before <open_boundary>, then the market resolves to Yes."
)

_ZONE_OFFSETS = {
    "EDT": timezone(timedelta(hours=-4)),
    "EST": timezone(timedelta(hours=-5)),
}


class SettledMarketEvidenceError(RuntimeError):
    """Raised when settled-market evidence cannot be selected or validated."""


@dataclass(frozen=True)
class SourcedMarket:
    """One public market object paired with its exact persisted raw record."""

    market: dict[str, Any]
    raw_record: RawRecordReference


class SettledMarketEvidenceClient(KalshiPublicClient):
    """Narrow public client extension for recent settled-market evidence.

    The base client's raw-preservation and runtime-event behavior is reused
    unchanged. No authenticated endpoint is added.
    """

    def list_settled_markets(
        self,
        *,
        series_ticker: str,
        min_settled_ts: int,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Return recent settled markets from the public current-market surface."""

        if not series_ticker:
            raise ValueError("series_ticker must be non-empty")
        if min_settled_ts < 0:
            raise ValueError("min_settled_ts must be non-negative")
        if max_pages <= 0:
            raise ValueError("max_pages must be positive")

        markets: list[dict[str, Any]] = []
        cursor: str | None = None

        for _ in range(max_pages):
            params: dict[str, Any] = {
                "status": "settled",
                "series_ticker": series_ticker,
                "min_settled_ts": min_settled_ts,
                "limit": DEFAULT_PAGE_LIMIT,
            }
            if cursor:
                params["cursor"] = cursor

            response = self._get_with_lineage("/markets", params=params)
            payload = response.payload
            page_markets = payload.get("markets")
            if not isinstance(page_markets, list):
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="list_settled_markets",
                    validation_code="markets_field_not_list",
                    field="markets",
                    expected="list",
                    actual=page_markets,
                )

            for index, market in enumerate(page_markets):
                if not isinstance(market, dict):
                    self._raise_endpoint_validation(
                        response=response,
                        endpoint="list_settled_markets",
                        validation_code="market_item_not_object",
                        field=f"markets[{index}]",
                        expected="object",
                        actual=market,
                    )
                markets.append(market)

            cursor = payload.get("cursor")
            if cursor is not None and not isinstance(cursor, str):
                self._raise_endpoint_validation(
                    response=response,
                    endpoint="list_settled_markets",
                    validation_code="cursor_not_text_or_null",
                    field="cursor",
                    expected="text or null",
                    actual=cursor,
                )
            if not cursor:
                break
        else:
            if cursor:
                raise SettledMarketEvidenceError(
                    "Settled-market discovery reached max_pages with another "
                    "cursor still present; refusing to treat a truncated window "
                    "as a complete reproducible sample frame"
                )

        return markets

    def get_market_with_lineage(self, ticker: str) -> SourcedMarket:
        """Return one public market plus the exact raw exchange that produced it."""

        if not ticker:
            raise ValueError("ticker must be non-empty")
        response = self._get_with_lineage(f"/markets/{ticker}")
        market = response.payload.get("market")
        if not isinstance(market, dict):
            self._raise_endpoint_validation(
                response=response,
                endpoint="get_market_with_lineage",
                validation_code="market_field_not_object",
                field="market",
                expected="object",
                actual=market,
            )
        return SourcedMarket(market=market, raw_record=response.raw_record)


def select_recent_settled_tickers(
    markets: Sequence[Mapping[str, Any]],
    *,
    count: int,
) -> list[str]:
    """Choose a deterministic recent sample by close_time, then ticker.

    Selection uses only market objects whose terminal REST status is ``finalized``.
    Kalshi uses ``settled`` as the GET /markets filter value, but settled market
    objects themselves are returned with status ``finalized``. A missing or
    malformed ticker/close_time blocks selection instead of being silently
    skipped, because silently skipping malformed members would change the sample
    frame without an audit trail.
    """

    if count <= 0:
        raise ValueError("count must be positive")

    candidates: list[tuple[datetime, str]] = []
    seen: set[str] = set()
    for index, market in enumerate(markets):
        if market.get("status") != "finalized":
            raise SettledMarketEvidenceError(
                f"Discovery item {index} is not terminal status='finalized'"
            )
        ticker = market.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            raise SettledMarketEvidenceError(
                f"Discovery item {index} has no non-empty ticker"
            )
        if ticker in seen:
            raise SettledMarketEvidenceError(
                f"Duplicate ticker in discovery frame: {ticker}"
            )
        seen.add(ticker)

        close_time = _parse_iso8601(market.get("close_time"), field="close_time")
        candidates.append((close_time, ticker))

    if len(candidates) < count:
        raise SettledMarketEvidenceError(
            f"Requested {count} settled markets but discovery returned only "
            f"{len(candidates)}"
        )

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [ticker for _, ticker in candidates[:count]]


def build_settled_market_row(
    *,
    run_id: str,
    observed_at_utc: str,
    sourced_market: SourcedMarket,
) -> dict[str, str]:
    """Build one derived evidence row without inventing missing semantics."""

    market = sourced_market.market
    raw = sourced_market.raw_record
    ticker = _text_or_blank(market.get("ticker"))
    primary = market.get("rules_primary")
    secondary = market.get("rules_secondary")
    primary_template_sha256, primary_template_state = _primary_rule_template_evidence(
        primary,
        open_time=market.get("open_time"),
        close_time=market.get("close_time"),
    )

    return {
        "run_id": run_id,
        "raw_source": raw.source,
        "raw_session_id": raw.session_id,
        "raw_request_id": raw.request_id,
        "observed_at_utc": observed_at_utc,
        "ticker": ticker,
        "status": _text_or_blank(market.get("status")),
        "result": _text_or_blank(market.get("result")),
        "settlement_ts": _text_or_blank(market.get("settlement_ts")),
        "open_time": _text_or_blank(market.get("open_time")),
        "close_time": _text_or_blank(market.get("close_time")),
        "expected_expiration_time": _text_or_blank(
            market.get("expected_expiration_time")
        ),
        "expiration_time": _text_or_blank(market.get("expiration_time")),
        "latest_expiration_time": _text_or_blank(
            market.get("latest_expiration_time")
        ),
        "occurrence_datetime": _text_or_blank(market.get("occurrence_datetime")),
        "expiration_value": _text_or_blank(market.get("expiration_value")),
        "settlement_value_dollars": _text_or_blank(
            market.get("settlement_value_dollars")
        ),
        "rules_primary_present": _bool_text(isinstance(primary, str) and bool(primary)),
        "rules_secondary_present": _bool_text(
            isinstance(secondary, str) and bool(secondary)
        ),
        "rules_primary_sha256": _hash_text(primary),
        "rules_secondary_sha256": _hash_text(secondary),
        "rules_primary_normalized_sha256": _hash_normalized_text(primary),
        "rules_secondary_normalized_sha256": _hash_normalized_text(secondary),
        "rules_primary_template_sha256": primary_template_sha256,
        "rules_primary_template_state": primary_template_state,
        "market_field_names_json": json.dumps(
            sorted(str(key) for key in market.keys()),
            separators=(",", ":"),
        ),
    }


def evaluate_settled_market_rows(
    rows: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Evaluate observable consistency while keeping interpretation conservative."""

    blockers: list[str] = []
    if not rows:
        return {
            "row_count": 0,
            "decision_use_blocked": True,
            "blockers": ["empty_sample"],
            "rules_primary_consistent": False,
            "rules_secondary_consistent": False,
            "expiration_value_present_count": 0,
            "settlement_value_dollars_present_count": 0,
            "field_name_sets_consistent": False,
        }

    primary_hashes: set[str] = set()
    primary_templates_valid = True
    secondary_hashes: set[str] = set()
    field_name_sets: set[str] = set()
    expiration_value_present = 0
    settlement_value_present = 0

    for index, row in enumerate(rows):
        if row.get("status") != "finalized":
            blockers.append(f"row_{index}_status_not_finalized")
        if row.get("result") not in {"yes", "no"}:
            blockers.append(f"row_{index}_result_not_yes_or_no")
        if not row.get("ticker"):
            blockers.append(f"row_{index}_ticker_missing")
        if not row.get("settlement_ts"):
            blockers.append(f"row_{index}_settlement_ts_missing")
        if not row.get("close_time"):
            blockers.append(f"row_{index}_close_time_missing")
        if row.get("rules_primary_present") != "true":
            blockers.append(f"row_{index}_rules_primary_missing")
        if row.get("rules_secondary_present") != "true":
            blockers.append(f"row_{index}_rules_secondary_missing")

        settlement_ts = row.get("settlement_ts", "")
        close_time = row.get("close_time", "")
        if settlement_ts:
            try:
                parsed_settlement = _parse_iso8601(
                    settlement_ts, field="settlement_ts"
                )
            except SettledMarketEvidenceError:
                blockers.append(f"row_{index}_settlement_ts_invalid")
                parsed_settlement = None
        else:
            parsed_settlement = None
        if close_time:
            try:
                parsed_close = _parse_iso8601(close_time, field="close_time")
            except SettledMarketEvidenceError:
                blockers.append(f"row_{index}_close_time_invalid")
                parsed_close = None
        else:
            parsed_close = None
        if (
            parsed_settlement is not None
            and parsed_close is not None
            and parsed_settlement < parsed_close
        ):
            blockers.append(f"row_{index}_settlement_before_close")

        if row.get("expiration_value"):
            expiration_value_present += 1
        if row.get("settlement_value_dollars"):
            settlement_value_present += 1

        primary_template_state = row.get("rules_primary_template_state", "")
        if primary_template_state != "validated":
            primary_templates_valid = False
            blockers.append(
                f"row_{index}_rules_primary_template_{primary_template_state or 'missing'}"
            )
        primary_hash = row.get("rules_primary_template_sha256", "")
        secondary_hash = row.get("rules_secondary_normalized_sha256", "")
        if primary_hash:
            primary_hashes.add(primary_hash)
        if secondary_hash:
            secondary_hashes.add(secondary_hash)
        field_name_sets.add(row.get("market_field_names_json", ""))

    primary_consistent = primary_templates_valid and len(primary_hashes) == 1
    secondary_consistent = len(secondary_hashes) == 1
    field_name_sets_consistent = len(field_name_sets) == 1
    if len(primary_hashes) > 1:
        blockers.append("rules_primary_drift")
    if not secondary_consistent:
        blockers.append("rules_secondary_drift")
    if not field_name_sets_consistent:
        blockers.append("market_field_set_drift")

    return {
        "row_count": len(rows),
        "decision_use_blocked": bool(blockers),
        "blockers": sorted(set(blockers)),
        "rules_primary_consistent": primary_consistent,
        "rules_secondary_consistent": secondary_consistent,
        "expiration_value_present_count": expiration_value_present,
        "settlement_value_dollars_present_count": settlement_value_present,
        "field_name_sets_consistent": field_name_sets_consistent,
    }


def validate_settled_market_evidence_manifest(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> dict[str, Any]:
    """Reconcile derived settled-market rows to exact raw single-market records."""

    path = Path(manifest_path)
    repo_root = Path(repository_root).resolve()
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SettledMarketEvidenceError(
            f"Could not read settled-market manifest {path}: {exc}"
        ) from exc

    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != (
        "collect_settled_market_evidence"
    ):
        raise SettledMarketEvidenceError(
            "Manifest is not for collect_settled_market_evidence"
        )
    if manifest.get("status") != "completed":
        raise SettledMarketEvidenceError(
            "Settled-market evidence validation requires a completed manifest"
        )

    raw_records = _load_raw_records(manifest, repo_root)
    derived_files = [
        item for item in manifest.get("files", []) if item.get("role") == "derived_csv"
    ]
    if len(derived_files) != 1:
        raise SettledMarketEvidenceError(
            "Settled-market evidence manifest must contain exactly one derived CSV"
        )

    csv_path = resolve_stored_path(derived_files[0]["path"], repo_root)
    rows: list[dict[str, str]] = []
    seen_raw_keys: set[tuple[str, str, str]] = set()
    try:
        with csv_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != SETTLED_MARKET_CSV_FIELDS:
                raise SettledMarketEvidenceError(
                    f"Unexpected settled-market CSV columns: {reader.fieldnames!r}"
                )
            for row_number, row in enumerate(reader, start=2):
                _validate_derived_row(
                    row=row,
                    row_number=row_number,
                    manifest=manifest,
                    raw_records=raw_records,
                    seen_raw_keys=seen_raw_keys,
                )
                rows.append(dict(row))
    except (OSError, csv.Error) as exc:
        raise SettledMarketEvidenceError(
            f"Could not read settled-market CSV {csv_path}: {exc}"
        ) from exc

    derivable_keys = {
        key
        for key, record in raw_records.items()
        if _market_from_raw_record(record) is not None
    }
    missing_rows = derivable_keys.difference(seen_raw_keys)
    if missing_rows:
        raise SettledMarketEvidenceError(
            "Successful raw single-market evidence records are missing derived "
            f"rows; examples: {sorted(missing_rows)[:3]!r}"
        )

    evaluation = evaluate_settled_market_rows(rows)
    return {
        "manifest_path": str(path),
        "run_id": manifest.get("run_id"),
        "row_count": len(rows),
        "evaluation": evaluation,
    }


def _validate_derived_row(
    *,
    row: Mapping[str, str],
    row_number: int,
    manifest: Mapping[str, Any],
    raw_records: Mapping[tuple[str, str, str], Mapping[str, Any]],
    seen_raw_keys: set[tuple[str, str, str]],
) -> None:
    for field in ("run_id", "raw_source", "raw_session_id", "raw_request_id", "ticker"):
        if not row.get(field):
            raise SettledMarketEvidenceError(
                f"Derived row {row_number} has blank required field {field}"
            )
    if row["run_id"] != manifest.get("run_id"):
        raise SettledMarketEvidenceError(
            f"Derived row {row_number} run_id does not match manifest"
        )

    raw_key = (
        row["raw_source"],
        row["raw_session_id"],
        row["raw_request_id"],
    )
    if raw_key in seen_raw_keys:
        raise SettledMarketEvidenceError(
            f"Derived row {row_number} duplicates raw reference {raw_key!r}"
        )
    raw_record = raw_records.get(raw_key)
    if raw_record is None:
        raise SettledMarketEvidenceError(
            f"Derived row {row_number} references unknown raw record {raw_key!r}"
        )
    market = _market_from_raw_record(raw_record)
    if market is None:
        raise SettledMarketEvidenceError(
            f"Derived row {row_number} raw record is not a successful single-market response"
        )

    request_path = raw_record["request"]["path"]
    expected_path = f"/markets/{row['ticker']}"
    if request_path != expected_path:
        raise SettledMarketEvidenceError(
            f"Derived row {row_number} ticker/path mismatch: {request_path!r}"
        )

    raw_ref = RawRecordReference(*raw_key)
    rebuilt = build_settled_market_row(
        run_id=row["run_id"],
        observed_at_utc=row["observed_at_utc"],
        sourced_market=SourcedMarket(market=dict(market), raw_record=raw_ref),
    )
    for field in SETTLED_MARKET_CSV_FIELDS:
        if rebuilt[field] != row[field]:
            raise SettledMarketEvidenceError(
                f"Derived row {row_number} field {field!r} does not match raw evidence"
            )

    _parse_iso8601(row["observed_at_utc"], field="observed_at_utc")
    seen_raw_keys.add(raw_key)


def _load_raw_records(
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> dict[tuple[str, str, str], Mapping[str, Any]]:
    records: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for descriptor in manifest.get("files", []):
        if descriptor.get("role") != "raw_api_archive":
            continue
        raw_path = resolve_stored_path(descriptor["path"], repository_root)
        try:
            with raw_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    record = json.loads(line)
                    key = (
                        record["source"],
                        record["session_id"],
                        record["request"]["request_id"],
                    )
                    if key in records:
                        raise SettledMarketEvidenceError(
                            f"Duplicate raw key at {raw_path}:{line_number}: {key!r}"
                        )
                    records[key] = record
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise SettledMarketEvidenceError(
                f"Could not index raw evidence file {raw_path}: {exc}"
            ) from exc
    if not records:
        raise SettledMarketEvidenceError(
            "Settled-market evidence manifest contains no raw API records"
        )
    return records


def _market_from_raw_record(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if record.get("error") is not None:
        return None
    request = record.get("request")
    response = record.get("response")
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        return None
    path = request.get("path")
    if request.get("method") != "GET" or not isinstance(path, str):
        return None
    if not path.startswith("/markets/") or path.count("/") != 2:
        return None
    status_code = response.get("status_code")
    if not isinstance(status_code, int) or isinstance(status_code, bool):
        return None
    if not 200 <= status_code < 300 or response.get("json_parse_error") is not None:
        return None
    body_text = response.get("body_text")
    if not isinstance(body_text, str):
        return None
    try:
        payload = json.loads(body_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping):
        return None
    market = payload.get("market")
    return market if isinstance(market, Mapping) else None


def _primary_rule_template_evidence(
    value: Any,
    *,
    open_time: Any,
    close_time: Any,
) -> tuple[str, str]:
    """Return a validated structural-template hash and parse state.

    Only the exact observed KXBTC15M grammar is recognized. Contract-specific
    EST/EDT date-time phrases are treated as variable boundaries only after
    they parse successfully and match the market's open_time and close_time.
    Any wording or boundary mismatch remains fail-closed evidence.
    """

    if not isinstance(value, str) or not value:
        return "", "unrecognized"

    normalized = normalize_rule_text(value)
    match = _PRIMARY_RULE_PATTERN.fullmatch(normalized)
    if match is None:
        return "", "unrecognized"

    try:
        later = _parse_rule_boundary(
            match.group("later_date"),
            match.group("later_time"),
            match.group("later_zone"),
        )
        earlier = _parse_rule_boundary(
            match.group("earlier_date"),
            match.group("earlier_time"),
            match.group("earlier_zone"),
        )
        parsed_open = _parse_iso8601(open_time, field="open_time")
        parsed_close = _parse_iso8601(close_time, field="close_time")
    except SettledMarketEvidenceError:
        return "", "boundary_invalid"

    if later != parsed_close or earlier != parsed_open:
        return "", "boundary_mismatch"

    return sha256(_PRIMARY_RULE_TEMPLATE.encode("utf-8")).hexdigest(), "validated"


def _parse_rule_boundary(date_text: str, time_text: str, zone_text: str) -> datetime:
    zone = _ZONE_OFFSETS.get(zone_text)
    if zone is None:
        raise SettledMarketEvidenceError(
            f"Unsupported KXBTC15M rule timezone: {zone_text!r}"
        )

    parsed_local: datetime | None = None
    for date_format in ("%b %d, %Y", "%B %d, %Y"):
        try:
            parsed_local = datetime.strptime(
                f"{date_text} {time_text}",
                f"{date_format} %I:%M %p",
            )
            break
        except ValueError:
            continue
    if parsed_local is None:
        raise SettledMarketEvidenceError(
            f"Unsupported KXBTC15M rule date/time: {date_text!r} {time_text!r}"
        )
    return parsed_local.replace(tzinfo=zone).astimezone(timezone.utc)


def normalize_rule_text(value: str) -> str:
    """Normalize whitespace only; do not rewrite contract semantics."""

    return " ".join(value.split())


def _hash_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return sha256(value.encode("utf-8")).hexdigest()


def _hash_normalized_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return sha256(normalize_rule_text(value).encode("utf-8")).hexdigest()


def _text_or_blank(value: Any) -> str:
    return "" if value is None else str(value)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _parse_iso8601(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SettledMarketEvidenceError(f"{field} must be non-empty ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SettledMarketEvidenceError(
            f"{field} is not valid ISO-8601 text: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise SettledMarketEvidenceError(f"{field} must include a timezone")
    return parsed
