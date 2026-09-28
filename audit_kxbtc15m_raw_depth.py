#!/usr/bin/env python3
"""Outcome-blind raw-depth feasibility audit for frozen KXBTC15M development data.

This command proves whether the existing full-depth raw archives are sufficient
for a bounded pooled-position simulator. It reads only the first 100
chronological markets (the frozen development partition), applies the same
quality rule as the H1 analysis, and never opens a holdout raw archive.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable, Sequence


FIRST_TICKER = "KXBTC15M-26AUG111345-45"
DEVELOPMENT_LAST_TICKER = "KXBTC15M-26AUG121430-30"
HOLDOUT_FIRST_TICKER = "KXBTC15M-26AUG121445-45"
EXPECTED_DEVELOPMENT_MARKETS = 100
EXPECTED_ELIGIBLE_MARKETS = 96
EXPECTED_EPISODES = 217
FROZEN_TICKER_TIMEZONE = timezone(timedelta(hours=-4), name="EDT")
TICKER_RE = re.compile(r"KXBTC15M-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})-\d{2}")
MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
REPORT_SCHEMA = "kxbtc15m_raw_depth_audit.v1"


class AuditError(RuntimeError):
    """Raised when the frozen audit cannot be completed safely."""


@dataclass(frozen=True)
class DevelopmentMarket:
    index: int
    ticker: str
    manifest: dict[str, Any]
    csv_path: Path
    rows: list[dict[str, str]]
    eligible: bool
    exclusion_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ParsedBook:
    yes_levels: tuple[tuple[Decimal, Decimal], ...]
    no_levels: tuple[tuple[Decimal, Decimal], ...]

    def bid_levels(self, side: str) -> tuple[tuple[Decimal, Decimal], ...]:
        return self.yes_levels if side == "YES" else self.no_levels

    def ask_levels(self, side: str) -> tuple[tuple[Decimal, Decimal], ...]:
        opposite = self.no_levels if side == "YES" else self.yes_levels
        return tuple(sorted(((Decimal("1") - price, qty) for price, qty in opposite)))


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise AuditError(f"Naive timestamp is not allowed: {value!r}")
    return parsed.astimezone(timezone.utc)


def market_close_utc(ticker: str) -> datetime:
    match = TICKER_RE.fullmatch(ticker)
    if not match:
        raise AuditError(f"Unsupported ticker: {ticker}")
    yy, month, day, hour, minute = match.groups()
    year, month_number = 2000 + int(yy), MONTHS[month]
    if (year, month_number) != (2026, 8):
        raise AuditError("Frozen audit accepts only August 2026 tickers")
    local_close = datetime(
        year, month_number, int(day), int(hour), int(minute),
        tzinfo=FROZEN_TICKER_TIMEZONE,
    )
    return local_close.astimezone(timezone.utc)


def decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise AuditError(f"Invalid decimal value: {value!r}") from exc
    if not result.is_finite():
        raise AuditError(f"Non-finite decimal value: {value!r}")
    return result


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def one_descriptor(manifest: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [item for item in manifest.get("files", []) if item.get("role") == role]
    if len(matches) != 1:
        raise AuditError(
            f"{manifest.get('run_id')}: expected one {role} descriptor; got {len(matches)}"
        )
    return matches[0]


def one_or_more_descriptors(
    manifest: dict[str, Any], role: str
) -> list[dict[str, Any]]:
    """Return every descriptor for a splittable artifact role.

    A single recorder session can cross a UTC date boundary. RawJsonlRecorder
    then preserves the same session in one JSONL file per UTC date, and the run
    manifest correctly declares both files.
    """

    matches = [item for item in manifest.get("files", []) if item.get("role") == role]
    if not matches:
        raise AuditError(f"{manifest.get('run_id')}: expected at least one {role} descriptor")
    return matches


def safe_extract_zip(source: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            target = (root / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise AuditError(f"Unsafe ZIP member: {member.filename!r}") from exc
        archive.extractall(root)


def file_by_basename(root: Path, basename: str) -> Path:
    matches = [path for path in root.rglob(basename) if path.is_file()]
    if len(matches) != 1:
        raise AuditError(f"Expected one {basename!r} in audit source; got {len(matches)}")
    return matches[0]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {
            "run_id", "raw_source", "raw_session_id", "raw_request_id",
            "observed_at_utc", "ticker", "yes_bid", "yes_ask", "no_bid", "no_ask",
        }
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise AuditError(f"{path}: missing CSV columns {sorted(missing)}")
        return list(reader)


def select_development_manifests(root: Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    for path in root.rglob("record_orderbook_*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        ticker = document.get("arguments", {}).get("ticker")
        if ticker and document.get("status") == "completed":
            manifests.append(document)
    manifests.sort(key=lambda item: parse_time(item["started_at_utc"]))

    selected: list[dict[str, Any]] = []
    active = False
    for manifest in manifests:
        ticker = manifest["arguments"]["ticker"]
        if ticker == FIRST_TICKER:
            active = True
        if active:
            selected.append(manifest)
        if ticker == DEVELOPMENT_LAST_TICKER:
            break

    if len(selected) != EXPECTED_DEVELOPMENT_MARKETS:
        raise AuditError(
            f"Expected {EXPECTED_DEVELOPMENT_MARKETS} frozen development markets; "
            f"found {len(selected)}"
        )
    if selected[0]["arguments"]["ticker"] != FIRST_TICKER:
        raise AuditError("Frozen development partition did not start at its first ticker")
    if selected[-1]["arguments"]["ticker"] != DEVELOPMENT_LAST_TICKER:
        raise AuditError("Frozen development partition did not end at its last ticker")
    if any(item["arguments"]["ticker"] == HOLDOUT_FIRST_TICKER for item in selected):
        raise AuditError("Holdout ticker entered the development partition")
    return selected


def assess_market(
    index: int,
    manifest: dict[str, Any],
    audit_root: Path,
) -> DevelopmentMarket:
    ticker = manifest["arguments"]["ticker"]
    descriptor = one_descriptor(manifest, "derived_csv")
    basename = Path(descriptor["path"]["value"].replace("\\", "/")).name
    csv_path = file_by_basename(audit_root, basename)
    rows = load_csv(csv_path)
    reasons: list[str] = []

    if sha256_path(csv_path) != descriptor.get("sha256"):
        reasons.append("derived_sha256_mismatch")
    if len(rows) != descriptor.get("data_row_count"):
        reasons.append("derived_row_count_mismatch")
    if any(row["ticker"] != ticker for row in rows):
        reasons.append("derived_ticker_mismatch")
    if any(row["run_id"] != manifest.get("run_id") for row in rows):
        reasons.append("derived_run_id_mismatch")

    close = market_close_utc(ticker)
    open_time = close - timedelta(minutes=15)
    preclose_times: list[datetime] = []
    valid_times: list[datetime] = []
    for row in rows:
        observed = parse_time(row["observed_at_utc"])
        if open_time <= observed < close:
            preclose_times.append(observed)
            quote_values = (row["yes_bid"], row["yes_ask"], row["no_bid"], row["no_ask"])
            if any(value != "" for value in quote_values):
                valid_times.append(observed)

    if manifest.get("status") != "completed":
        reasons.append("manifest_not_completed")
    result, summary = manifest.get("result", {}), manifest.get("summary", {})
    if result.get("orders_placed") != 0:
        reasons.append("orders_placed_not_zero")
    if result.get("request_failures") != 0:
        reasons.append("request_failures")
    if summary.get("raw_error_record_count") != 0:
        reasons.append("raw_errors")
    if summary.get("runtime_error_event_count") != 0:
        reasons.append("runtime_errors")
    if not valid_times:
        reasons.append("no_valid_preclose_quotes")
    else:
        if (min(valid_times) - open_time).total_seconds() > 45:
            reasons.append("late_first_valid_quote")
        if (max(valid_times) - close).total_seconds() < -5:
            reasons.append("early_last_valid_quote")
    gaps = [
        (later - earlier).total_seconds()
        for earlier, later in zip(preclose_times, preclose_times[1:])
    ]
    if not gaps or max(gaps) > 5:
        reasons.append("preclose_gap_over_5s")

    return DevelopmentMarket(
        index=index,
        ticker=ticker,
        manifest=manifest,
        csv_path=csv_path,
        rows=rows,
        eligible=not reasons,
        exclusion_reasons=tuple(reasons),
    )


def parse_levels(value: Any, label: str) -> tuple[tuple[Decimal, Decimal], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise AuditError(f"{label} is not a list or null")
    parsed: list[tuple[Decimal, Decimal]] = []
    for index, level in enumerate(value):
        if not isinstance(level, list) or len(level) != 2:
            raise AuditError(f"{label}[{index}] is not a two-item level")
        if not all(isinstance(item, str) for item in level):
            raise AuditError(f"{label}[{index}] does not use fixed-point strings")
        price, quantity = decimal_or_none(level[0]), decimal_or_none(level[1])
        assert price is not None and quantity is not None
        if not (Decimal("0") <= price <= Decimal("1")):
            raise AuditError(f"{label}[{index}] price is outside [0, 1]")
        if quantity <= 0:
            raise AuditError(f"{label}[{index}] quantity is not positive")
        parsed.append((price, quantity))
    if any(later[0] < earlier[0] for earlier, later in zip(parsed, parsed[1:])):
        raise AuditError(f"{label} is not ordered by ascending price")
    return tuple(parsed)


def parse_book(record: dict[str, Any], ticker: str) -> ParsedBook:
    if record.get("schema_version") != "raw_http_exchange.v1":
        raise AuditError("Unexpected raw exchange schema")
    request = record.get("request")
    if not isinstance(request, dict):
        raise AuditError("Raw record is missing request object")
    expected_path = f"/markets/{ticker}/orderbook"
    if request.get("method") != "GET" or request.get("path") != expected_path:
        raise AuditError(f"Raw request is not GET {expected_path}")
    response = record.get("response")
    if not isinstance(response, dict) or response.get("status_code") != 200:
        raise AuditError("Raw order-book response is missing or not HTTP 200")
    if record.get("error") is not None:
        raise AuditError("Raw order-book response contains an error")
    body = response.get("body_text")
    if not isinstance(body, str):
        raise AuditError("Raw response body_text is missing")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AuditError("Raw response body_text is not JSON") from exc
    orderbook = payload.get("orderbook_fp") if isinstance(payload, dict) else None
    if not isinstance(orderbook, dict):
        raise AuditError("Raw payload is missing orderbook_fp")
    return ParsedBook(
        yes_levels=parse_levels(orderbook.get("yes_dollars"), "yes_dollars"),
        no_levels=parse_levels(orderbook.get("no_dollars"), "no_dollars"),
    )


def best_quotes(book: ParsedBook) -> dict[str, Decimal | None]:
    yes_bid = book.yes_levels[-1][0] if book.yes_levels else None
    no_bid = book.no_levels[-1][0] if book.no_levels else None
    return {
        "yes_bid": yes_bid,
        "yes_ask": None if no_bid is None else Decimal("1") - no_bid,
        "no_bid": no_bid,
        "no_ask": None if yes_bid is None else Decimal("1") - yes_bid,
    }


def resolve_raw_path(repository_root: Path, descriptor: dict[str, Any]) -> Path:
    path_spec = descriptor.get("path", {})
    if path_spec.get("kind") != "repository_relative":
        raise AuditError("Frozen audit accepts only repository-relative raw paths")
    value = path_spec.get("value")
    if not isinstance(value, str) or not value:
        raise AuditError("Raw path descriptor is empty")
    root = repository_root.resolve()
    candidate = (root / Path(value.replace("\\", "/"))).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AuditError(f"Raw path escapes repository root: {value!r}") from exc
    return candidate


def quote_matches(row: dict[str, str], book: ParsedBook) -> bool:
    reconstructed = best_quotes(book)
    return all(
        decimal_or_none(row[field]) == reconstructed[field]
        for field in ("yes_bid", "yes_ask", "no_bid", "no_ask")
    )


def load_episodes(path: Path) -> list[dict[str, str]]:
    rows = load_plain_csv(path)
    required = {"market_index", "ticker", "side", "entry_time", "entry_ask", "entry_bid"}
    if rows:
        missing = required.difference(rows[0])
        if missing:
            raise AuditError(f"Episode CSV is missing columns {sorted(missing)}")
    if len(rows) != EXPECTED_EPISODES:
        raise AuditError(f"Expected {EXPECTED_EPISODES} H1 episodes; found {len(rows)}")
    for row in rows:
        index = int(row["market_index"])
        if index < 1 or index > EXPECTED_DEVELOPMENT_MARKETS:
            raise AuditError("Episode CSV contains a non-development market index")
        if row["ticker"] == HOLDOUT_FIRST_TICKER:
            raise AuditError("Episode CSV contains the first holdout ticker")
        if row["side"] not in {"YES", "NO"}:
            raise AuditError(f"Unexpected episode side: {row['side']!r}")
    return rows


def load_plain_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def episode_key(row: dict[str, str]) -> tuple[int, str, str]:
    return int(row["market_index"]), row["ticker"], parse_time(row["entry_time"]).isoformat()


def audit_one_market(
    market: DevelopmentMarket,
    repository_root: Path,
    episodes: Sequence[dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    descriptors = one_or_more_descriptors(market.manifest, "raw_api_archive")

    csv_ids = [row["raw_request_id"] for row in market.rows]
    if len(set(csv_ids)) != len(csv_ids):
        raise AuditError(f"{market.ticker}: duplicate raw_request_id in derived CSV")
    rows_by_id = {row["raw_request_id"]: row for row in market.rows}
    raw_records: list[tuple[datetime, int, str, ParsedBook]] = []
    seen_raw_ids: set[str] = set()
    quote_match_count = 0
    raw_path_values: list[str] = []
    expected_record_count = 0

    for descriptor in descriptors:
        raw_path = resolve_raw_path(repository_root, descriptor)
        raw_path_values.append(descriptor["path"]["value"])
        if not raw_path.is_file():
            raise AuditError(f"Raw archive is missing: {raw_path}")
        if sha256_path(raw_path) != descriptor.get("sha256"):
            raise AuditError(f"Raw SHA-256 mismatch: {raw_path}")
        file_record_count = 0
        with raw_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AuditError(f"{raw_path}:{line_number}: invalid JSON") from exc
                request = record.get("request")
                request_id = request.get("request_id") if isinstance(request, dict) else None
                if not isinstance(request_id, str) or not request_id:
                    raise AuditError(f"{raw_path}:{line_number}: missing request_id")
                if request_id in seen_raw_ids:
                    raise AuditError(f"{raw_path}:{line_number}: duplicate request_id")
                started_at = request.get("started_at_utc")
                monotonic_ns = request.get("started_monotonic_ns")
                if not isinstance(started_at, str) or not isinstance(monotonic_ns, int):
                    raise AuditError(
                        f"{raw_path}:{line_number}: missing raw request ordering fields"
                    )
                book = parse_book(record, market.ticker)
                seen_raw_ids.add(request_id)
                raw_records.append(
                    (parse_time(started_at), monotonic_ns, request_id, book)
                )
                file_record_count += 1
                row = rows_by_id.get(request_id)
                if row is not None and quote_matches(row, book):
                    quote_match_count += 1
        if file_record_count != descriptor.get("record_count"):
            raise AuditError(
                f"{market.ticker}: raw record count does not match manifest for {raw_path}"
            )
        expected_record_count += int(descriptor.get("record_count", 0))

    raw_records.sort(key=lambda item: (item[0], item[1], item[2]))
    raw_ids = [item[2] for item in raw_records]
    books_by_id = {item[2]: item[3] for item in raw_records}
    if len(raw_ids) != expected_record_count:
        raise AuditError(f"{market.ticker}: combined raw record count does not match manifest")
    if raw_ids != csv_ids:
        raise AuditError(f"{market.ticker}: raw/derived request-id sequences differ")
    if quote_match_count != len(market.rows):
        raise AuditError(f"{market.ticker}: reconstructed quotes do not all match CSV")

    episode_outputs: list[dict[str, Any]] = []
    indexed_rows = {
        parse_time(row["observed_at_utc"]).isoformat(): row for row in market.rows
    }
    for episode in episodes:
        entry_time = parse_time(episode["entry_time"]).isoformat()
        row = indexed_rows.get(entry_time)
        if row is None:
            raise AuditError(f"{market.ticker}: episode entry has no exact CSV row")
        request_id = row["raw_request_id"]
        book = books_by_id[request_id]
        side = episode["side"]
        asks, bids = book.ask_levels(side), book.bid_levels(side)
        if not asks or not bids:
            raise AuditError(f"{market.ticker}: episode entry lacks executable bid/ask depth")
        if decimal_or_none(episode["entry_ask"]) != asks[0][0]:
            raise AuditError(f"{market.ticker}: episode ask does not match raw best ask")
        if decimal_or_none(episode["entry_bid"]) != bids[-1][0]:
            raise AuditError(f"{market.ticker}: episode bid does not match raw best bid")
        episode_outputs.append({
            "market_index": market.index,
            "ticker": market.ticker,
            "side": side,
            "entry_time": episode["entry_time"],
            "raw_session_id": row["raw_session_id"],
            "raw_request_id": request_id,
            "buy_ask_level_count": len(asks),
            "best_ask": str(asks[0][0]),
            "best_ask_quantity": str(asks[0][1]),
            "sell_bid_level_count": len(bids),
            "best_bid": str(bids[-1][0]),
            "best_bid_quantity": str(bids[-1][1]),
        })

    return ({
        "market_index": market.index,
        "ticker": market.ticker,
        "derived_rows": len(market.rows),
        "raw_records": len(raw_ids),
        "lineage_sequence_match": True,
        "reconstructed_quote_rows_match": quote_match_count,
        "episode_entries": len(episode_outputs),
        "raw_archive_count": len(descriptors),
        "raw_paths": ";".join(raw_path_values),
    }, episode_outputs)


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise AuditError(f"Refusing to write empty CSV: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    exclusions = result["development_exclusions"]
    lines = [
        "# KXBTC15M raw-depth feasibility audit",
        "",
        f"**Gate: {result['gate']}**",
        "",
        "This audit was outcome-blind and development-only. It did not open any raw archive "
        "from the frozen 26-market holdout.",
        "",
        "## Result",
        "",
        f"- Frozen development markets: {summary['development_markets']}",
        f"- Eligible development markets audited: {summary['eligible_markets']}",
        f"- Raw/derived quote rows verified: {summary['verified_quote_rows']:,}",
        f"- H1 episode entries reconstructed with price and quantity: {summary['episode_entries']}",
        f"- Holdout raw archives opened: {summary['holdout_raw_archives_opened']}",
        "",
        "## Interpretation",
        "",
        "A PASS means the existing data are sufficient to build the next component: a bounded, "
        "depth-aware pooled-position simulator. It does not mean the strategy is profitable, "
        "and it does not select ladder sizes, thresholds, or exits.",
        "",
        "## Predeclared development exclusions",
        "",
    ]
    for item in exclusions:
        lines.append(
            f"- Market {item['market_index']} `{item['ticker']}`: "
            + ", ".join(item["reasons"])
        )
    lines.extend([
        "",
        "## Next gate",
        "",
        "Only after this audit passes should we preregister one bounded H1 ladder and simulate "
        "fills, pooled cost, depth-adjusted liquidation, fees, and the fixed exposure/time stop.",
        "",
    ])
    return "\n".join(lines)


def run_audit(
    audit_root: Path,
    repository_root: Path,
    episodes_csv: Path,
    output_dir: Path,
) -> dict[str, Any]:
    manifests = select_development_manifests(audit_root)
    markets = [
        assess_market(index, manifest, audit_root)
        for index, manifest in enumerate(manifests, start=1)
    ]
    eligible = [market for market in markets if market.eligible]
    if len(eligible) != EXPECTED_ELIGIBLE_MARKETS:
        raise AuditError(
            f"Expected {EXPECTED_ELIGIBLE_MARKETS} eligible development markets; "
            f"found {len(eligible)}"
        )
    episodes = load_episodes(episodes_csv)
    eligible_indices = {market.index for market in eligible}
    if any(int(row["market_index"]) not in eligible_indices for row in episodes):
        raise AuditError("Episode CSV contains an ineligible development market")

    episodes_by_index: dict[int, list[dict[str, str]]] = {}
    for row in episodes:
        episodes_by_index.setdefault(int(row["market_index"]), []).append(row)

    market_outputs: list[dict[str, Any]] = []
    episode_outputs: list[dict[str, Any]] = []
    for market in eligible:
        market_result, market_episodes = audit_one_market(
            market,
            repository_root,
            episodes_by_index.get(market.index, ()),
        )
        market_outputs.append(market_result)
        episode_outputs.extend(market_episodes)

    if len(episode_outputs) != EXPECTED_EPISODES:
        raise AuditError("Not every H1 episode entry was reconstructed")
    verified_rows = sum(item["reconstructed_quote_rows_match"] for item in market_outputs)
    total_rows = sum(item["derived_rows"] for item in market_outputs)
    if verified_rows != total_rows:
        raise AuditError("Not every derived quote row was reconstructed")

    exclusions = [
        {
            "market_index": market.index,
            "ticker": market.ticker,
            "reasons": list(market.exclusion_reasons),
        }
        for market in markets if not market.eligible
    ]
    result = {
        "schema_version": REPORT_SCHEMA,
        "gate": "PASS",
        "outcome_blind": True,
        "holdout_read": False,
        "summary": {
            "development_markets": len(markets),
            "eligible_markets": len(eligible),
            "excluded_markets": len(exclusions),
            "verified_quote_rows": verified_rows,
            "episode_entries": len(episode_outputs),
            "holdout_raw_archives_opened": 0,
        },
        "development_exclusions": exclusions,
        "markets": market_outputs,
        "episodes": episode_outputs,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "kxbtc15m_raw_depth_audit.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "KXBTC15M_RAW_DEPTH_AUDIT.md").write_text(
        markdown_report(result), encoding="utf-8"
    )
    write_csv(output_dir / "kxbtc15m_raw_depth_episode_entries.csv", episode_outputs)
    write_csv(output_dir / "kxbtc15m_raw_depth_markets.csv", market_outputs)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_source", type=Path, help="126-market audit ZIP or extracted directory")
    parser.add_argument(
        "--repo-root", type=Path, default=Path("."),
        help="Repository root containing data/raw (default: current directory)",
    )
    parser.add_argument(
        "--episodes-csv", type=Path,
        default=Path("analysis/kxbtc15m_h1/kxbtc15m_h1_development_episodes.csv"),
        help="Frozen H1 development episode CSV",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("analysis/kxbtc15m_raw_depth_audit"),
        help="Directory for audit outputs",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.audit_source.exists():
        raise AuditError(f"Audit source does not exist: {args.audit_source}")
    if not args.episodes_csv.is_file():
        raise AuditError(f"Episode CSV does not exist: {args.episodes_csv}")
    if not args.repo_root.is_dir():
        raise AuditError(f"Repository root does not exist: {args.repo_root}")

    if args.audit_source.is_dir():
        result = run_audit(
            args.audit_source, args.repo_root, args.episodes_csv, args.output_dir
        )
    else:
        with TemporaryDirectory(prefix="kxbtc15m_raw_depth_") as temp_dir:
            extracted = Path(temp_dir)
            safe_extract_zip(args.audit_source, extracted)
            result = run_audit(extracted, args.repo_root, args.episodes_csv, args.output_dir)

    summary = result["summary"]
    print(f"Gate: {result['gate']}")
    print(f"Eligible development markets audited: {summary['eligible_markets']}")
    print(f"Raw/derived quote rows verified: {summary['verified_quote_rows']}")
    print(f"H1 episode entries reconstructed: {summary['episode_entries']}")
    print(f"Holdout raw archives opened: {summary['holdout_raw_archives_opened']}")
    print(f"Report: {args.output_dir / 'KXBTC15M_RAW_DEPTH_AUDIT.md'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AuditError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
