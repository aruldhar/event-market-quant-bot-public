from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from src.kalshi_public import RawRecordReference, SourcedApiResponse
from src.settled_market_evidence import (
    SETTLED_MARKET_CSV_FIELDS,
    SettledMarketEvidenceClient,
    SettledMarketEvidenceError,
    SourcedMarket,
    build_settled_market_row,
    evaluate_settled_market_rows,
    normalize_rule_text,
    select_recent_settled_tickers,
    validate_settled_market_evidence_manifest,
)


def _rule_boundary(value: str, *, long_month: bool) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone(timedelta(hours=-4))
    )
    hour = parsed.hour % 12 or 12
    minute = f"{parsed.minute:02d}"
    am_pm = "AM" if parsed.hour < 12 else "PM"
    month = parsed.strftime("%B" if long_month else "%b")
    return f"{hour}:{minute} {am_pm} EDT on {month} {parsed.day}, {parsed.year}"


def _primary_rule(*, open_time: str, close_time: str) -> str:
    return (
        "If the simple average of the sixty seconds of CF Benchmarks' BRTI before "
        f"{_rule_boundary(close_time, long_month=False)} is at least the simple "
        "average of the sixty seconds of CF Benchmarks' BRTI before "
        f"{_rule_boundary(open_time, long_month=True)}, then the market resolves to Yes."
    )


def market(
    ticker: str,
    *,
    close_time: str,
    result: str = "yes",
    settlement_ts: str = "2026-08-08T12:16:00Z",
    rules_primary: str | None = None,
    rules_secondary: str = "Average 60 RTI prices and round to two decimals.",
    open_time: str = "2026-08-08T12:00:00Z",
) -> dict[str, object]:
    if rules_primary is None:
        rules_primary = _primary_rule(open_time=open_time, close_time=close_time)
    return {
        "ticker": ticker,
        "status": "finalized",
        "result": result,
        "settlement_ts": settlement_ts,
        "open_time": open_time,
        "close_time": close_time,
        "expected_expiration_time": close_time,
        "expiration_time": "2026-08-15T12:15:00Z",
        "latest_expiration_time": "2026-08-15T12:15:00Z",
        "occurrence_datetime": close_time,
        "expiration_value": "123456.78",
        "settlement_value_dollars": "1.0000" if result == "yes" else "0.0000",
        "rules_primary": rules_primary,
        "rules_secondary": rules_secondary,
    }


def sourced(item: dict[str, object], request_id: str = "req-1") -> SourcedMarket:
    return SourcedMarket(
        market=item,
        raw_record=RawRecordReference("kalshi_public_rest", "session-1", request_id),
    )


def test_normalize_rule_text_changes_whitespace_only() -> None:
    assert normalize_rule_text(" A\n  B\tC ") == "A B C"


def test_select_recent_settled_tickers_is_deterministic() -> None:
    items = [
        market("KX-1", close_time="2026-08-08T12:15:00Z"),
        market("KX-3", close_time="2026-08-08T12:45:00Z"),
        market("KX-2", close_time="2026-08-08T12:30:00Z"),
    ]
    assert select_recent_settled_tickers(items, count=2) == ["KX-3", "KX-2"]


def test_select_recent_settled_tickers_rejects_malformed_frame() -> None:
    item = market("KX-1", close_time="2026-08-08T12:15:00Z")
    item["status"] = "closed"
    with pytest.raises(SettledMarketEvidenceError, match="not terminal status='finalized'"):
        select_recent_settled_tickers([item], count=1)


def test_build_row_preserves_fields_and_exact_lineage() -> None:
    row = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-08T12:20:00+00:00",
        sourced_market=sourced(market("KX-1", close_time="2026-08-08T12:15:00Z")),
    )
    assert list(row) == SETTLED_MARKET_CSV_FIELDS
    assert row["run_id"] == "run-1"
    assert row["raw_request_id"] == "req-1"
    assert row["status"] == "finalized"
    assert row["result"] == "yes"
    assert len(row["rules_primary_sha256"]) == 64
    assert len(row["rules_primary_template_sha256"]) == 64
    assert row["rules_primary_template_state"] == "validated"
    assert json.loads(row["market_field_names_json"])[0] == "close_time"


def test_evaluation_accepts_consistent_observable_sample() -> None:
    rows = [
        build_settled_market_row(
            run_id="run-1",
            observed_at_utc="2026-08-08T12:20:00+00:00",
            sourced_market=sourced(
                market("KX-1", close_time="2026-08-08T12:15:00Z"), "req-1"
            ),
        ),
        build_settled_market_row(
            run_id="run-1",
            observed_at_utc="2026-08-08T12:35:00+00:00",
            sourced_market=sourced(
                market(
                    "KX-2",
                    close_time="2026-08-08T12:30:00Z",
                    settlement_ts="2026-08-08T12:31:00Z",
                ),
                "req-2",
            ),
        ),
    ]
    evaluation = evaluate_settled_market_rows(rows)
    assert evaluation["decision_use_blocked"] is False
    assert evaluation["rules_primary_consistent"] is True
    assert evaluation["rules_secondary_consistent"] is True


def test_evaluation_blocks_unrecognized_primary_rule_without_coercing_text() -> None:
    first = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-08T12:20:00+00:00",
        sourced_market=sourced(market("KX-1", close_time="2026-08-08T12:15:00Z")),
    )
    second = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-08T12:35:00+00:00",
        sourced_market=sourced(
            market(
                "KX-2",
                close_time="2026-08-08T12:30:00Z",
                settlement_ts="2026-08-08T12:31:00Z",
                rules_primary="A materially different rule.",
            ),
            "req-2",
        ),
    )
    evaluation = evaluate_settled_market_rows([first, second])
    assert evaluation["decision_use_blocked"] is True
    assert "row_1_rules_primary_template_unrecognized" in evaluation["blockers"]
    assert evaluation["rules_primary_consistent"] is False


def test_time_specific_primary_rules_share_validated_template() -> None:
    first = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-09T01:22:36+00:00",
        sourced_market=sourced(
            market(
                "KXBTC15M-26AUG082115-15",
                open_time="2026-08-09T01:00:00Z",
                close_time="2026-08-09T01:15:00Z",
                settlement_ts="2026-08-09T01:15:05.498919Z",
            ),
            "req-1",
        ),
    )
    second = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-09T01:22:36+00:00",
        sourced_market=sourced(
            market(
                "KXBTC15M-26AUG082100-00",
                open_time="2026-08-09T00:45:00Z",
                close_time="2026-08-09T01:00:00Z",
                settlement_ts="2026-08-09T01:00:05.549772Z",
            ),
            "req-2",
        ),
    )

    assert first["rules_primary_normalized_sha256"] != second["rules_primary_normalized_sha256"]
    assert first["rules_primary_template_sha256"] == second["rules_primary_template_sha256"]
    assert first["rules_primary_template_state"] == "validated"
    assert second["rules_primary_template_state"] == "validated"

    evaluation = evaluate_settled_market_rows([first, second])
    assert evaluation["decision_use_blocked"] is False
    assert evaluation["rules_primary_consistent"] is True


def test_evaluation_blocks_primary_rule_boundary_mismatch() -> None:
    wrong_rule = _primary_rule(
        open_time="2026-08-09T00:30:00Z",
        close_time="2026-08-09T00:45:00Z",
    )
    row = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-09T01:22:36+00:00",
        sourced_market=sourced(
            market(
                "KXBTC15M-26AUG082100-00",
                open_time="2026-08-09T00:45:00Z",
                close_time="2026-08-09T01:00:00Z",
                settlement_ts="2026-08-09T01:00:05.549772Z",
                rules_primary=wrong_rule,
            )
        ),
    )
    evaluation = evaluate_settled_market_rows([row])
    assert evaluation["decision_use_blocked"] is True
    assert "row_0_rules_primary_template_boundary_mismatch" in evaluation["blockers"]
    assert evaluation["rules_primary_consistent"] is False


def test_evaluation_blocks_market_field_set_drift() -> None:
    first_market = market("KX-1", close_time="2026-08-08T12:15:00Z")
    second_market = market(
        "KX-2",
        close_time="2026-08-08T12:30:00Z",
        settlement_ts="2026-08-08T12:31:00Z",
    )
    second_market["unexpected_new_field"] = "present"

    rows = [
        build_settled_market_row(
            run_id="run-1",
            observed_at_utc="2026-08-08T12:20:00+00:00",
            sourced_market=sourced(first_market, "req-1"),
        ),
        build_settled_market_row(
            run_id="run-1",
            observed_at_utc="2026-08-08T12:35:00+00:00",
            sourced_market=sourced(second_market, "req-2"),
        ),
    ]

    evaluation = evaluate_settled_market_rows(rows)
    assert evaluation["field_name_sets_consistent"] is False
    assert evaluation["decision_use_blocked"] is True
    assert "market_field_set_drift" in evaluation["blockers"]


def test_evaluation_blocks_missing_settlement_timestamp() -> None:
    row = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-08T12:20:00+00:00",
        sourced_market=sourced(
            market(
                "KX-1",
                close_time="2026-08-08T12:15:00Z",
                settlement_ts="",
            )
        ),
    )
    evaluation = evaluate_settled_market_rows([row])
    assert evaluation["decision_use_blocked"] is True
    assert "row_0_settlement_ts_missing" in evaluation["blockers"]


def test_list_settled_markets_uses_official_settlement_filters(tmp_path: Path) -> None:
    client = SettledMarketEvidenceClient(raw_log_root=tmp_path)
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(path: str, params: dict[str, object] | None = None) -> SourcedApiResponse:
        calls.append((path, params or {}))
        return SourcedApiResponse(
            payload={
                "markets": [market("KX-1", close_time="2026-08-08T12:15:00Z")],
                "cursor": "",
            },
            raw_record=RawRecordReference("kalshi_public_rest", "session-1", "req-list"),
        )

    client._get_with_lineage = fake_get  # type: ignore[method-assign]
    items = client.list_settled_markets(
        series_ticker="KXBTC15M",
        min_settled_ts=123,
    )
    assert len(items) == 1
    assert calls == [
        (
            "/markets",
            {
                "status": "settled",
                "series_ticker": "KXBTC15M",
                "min_settled_ts": 123,
                "limit": 1000,
            },
        )
    ]


def test_list_settled_markets_refuses_truncated_pagination(tmp_path: Path) -> None:
    client = SettledMarketEvidenceClient(raw_log_root=tmp_path)

    def fake_get(path: str, params: dict[str, object] | None = None) -> SourcedApiResponse:
        return SourcedApiResponse(
            payload={
                "markets": [market("KX-1", close_time="2026-08-08T12:15:00Z")],
                "cursor": "more",
            },
            raw_record=RawRecordReference("kalshi_public_rest", "session-1", "req-list"),
        )

    client._get_with_lineage = fake_get  # type: ignore[method-assign]
    with pytest.raises(SettledMarketEvidenceError, match="truncated window"):
        client.list_settled_markets(
            series_ticker="KXBTC15M",
            min_settled_ts=123,
            max_pages=1,
        )


def test_get_market_with_lineage_preserves_raw_reference(tmp_path: Path) -> None:
    client = SettledMarketEvidenceClient(raw_log_root=tmp_path)
    expected = market("KX-1", close_time="2026-08-08T12:15:00Z")

    def fake_get(path: str, params: dict[str, object] | None = None) -> SourcedApiResponse:
        assert path == "/markets/KX-1"
        return SourcedApiResponse(
            payload={"market": expected},
            raw_record=RawRecordReference("kalshi_public_rest", "session-1", "req-1"),
        )

    client._get_with_lineage = fake_get  # type: ignore[method-assign]
    result = client.get_market_with_lineage("KX-1")
    assert result.market == expected
    assert result.raw_record.request_id == "req-1"


def test_offline_validator_detects_derived_tampering(tmp_path: Path) -> None:
    repo = tmp_path
    raw_path = repo / "data" / "raw.jsonl"
    csv_path = repo / "logs" / "evidence.csv"
    raw_path.parent.mkdir(parents=True)
    csv_path.parent.mkdir(parents=True)

    item = market("KX-1", close_time="2026-08-08T12:15:00Z")
    raw_record = {
        "source": "kalshi_public_rest",
        "session_id": "session-1",
        "request": {
            "request_id": "req-1",
            "method": "GET",
            "path": "/markets/KX-1",
        },
        "response": {
            "status_code": 200,
            "json_parse_error": None,
            "body_text": json.dumps({"market": item}),
        },
        "error": None,
    }
    raw_path.write_text(json.dumps(raw_record) + "\n", encoding="utf-8")

    row = build_settled_market_row(
        run_id="run-1",
        observed_at_utc="2026-08-08T12:20:00+00:00",
        sourced_market=sourced(item),
    )
    row["result"] = "no"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SETTLED_MARKET_CSV_FIELDS)
        writer.writeheader()
        writer.writerow(row)

    manifest_path = repo / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "collector": {"name": "collect_settled_market_evidence"},
                "status": "completed",
                "files": [
                    {
                        "role": "raw_api_archive",
                        "path": {
                            "kind": "repository_relative",
                            "value": raw_path.relative_to(repo).as_posix(),
                        },
                    },
                    {
                        "role": "derived_csv",
                        "path": {
                            "kind": "repository_relative",
                            "value": csv_path.relative_to(repo).as_posix(),
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SettledMarketEvidenceError, match="does not match raw evidence"):
        validate_settled_market_evidence_manifest(
            manifest_path,
            repository_root=repo,
        )
