import json
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_kxbtc15m_raw_depth import (
    AuditError,
    ParsedBook,
    best_quotes,
    parse_book,
    parse_levels,
    quote_matches,
    resolve_raw_path,
    one_or_more_descriptors,
)


def raw_record() -> dict:
    payload = {
        "orderbook_fp": {
            "yes_dollars": [["0.1000", "5.00"], ["0.4200", "3.00"]],
            "no_dollars": [["0.5500", "8.00"], ["0.5600", "2.00"]],
        }
    }
    return {
        "schema_version": "raw_http_exchange.v1",
        "request": {
            "request_id": "request-1",
            "method": "GET",
            "path": "/markets/TEST/orderbook",
        },
        "response": {"status_code": 200, "body_text": json.dumps(payload)},
        "error": None,
    }


class RawDepthAuditTests(unittest.TestCase):
    def test_bid_only_book_reconstructs_both_asks(self) -> None:
        book = parse_book(raw_record(), "TEST")
        self.assertEqual(best_quotes(book), {
            "yes_bid": Decimal("0.4200"),
            "yes_ask": Decimal("0.4400"),
            "no_bid": Decimal("0.5600"),
            "no_ask": Decimal("0.5800"),
        })
        self.assertEqual(
            book.ask_levels("YES")[0],
            (Decimal("0.4400"), Decimal("2.00")),
        )
        self.assertEqual(
            book.ask_levels("NO")[0],
            (Decimal("0.5800"), Decimal("3.00")),
        )

    def test_quote_match_uses_exact_decimal_values(self) -> None:
        book = parse_book(raw_record(), "TEST")
        row = {
            "yes_bid": "0.4200", "yes_ask": "0.4400",
            "no_bid": "0.5600", "no_ask": "0.5800",
        }
        self.assertTrue(quote_matches(row, book))
        row["yes_ask"] = "0.4500"
        self.assertFalse(quote_matches(row, book))

    def test_nonascending_levels_fail_closed(self) -> None:
        with self.assertRaisesRegex(AuditError, "ascending"):
            parse_levels([["0.50", "1"], ["0.40", "1"]], "yes_dollars")

    def test_nonpositive_quantity_fails_closed(self) -> None:
        with self.assertRaisesRegex(AuditError, "positive"):
            parse_levels([["0.50", "0"]], "yes_dollars")

    def test_raw_path_cannot_escape_repository(self) -> None:
        descriptor = {
            "path": {"kind": "repository_relative", "value": "../secret.jsonl"}
        }
        with TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(AuditError, "escapes"):
                resolve_raw_path(Path(temp_dir), descriptor)

    def test_wrong_endpoint_fails_closed(self) -> None:
        record = raw_record()
        record["request"]["path"] = "/markets/OTHER/orderbook"
        with self.assertRaisesRegex(AuditError, "not GET"):
            parse_book(record, "TEST")

    def test_utc_boundary_session_accepts_multiple_raw_archives(self) -> None:
        manifest = {
            "run_id": "record_orderbook_boundary",
            "files": [
                {"role": "raw_api_archive", "path": {"value": "2026/08/11/a.jsonl"}},
                {"role": "derived_csv", "path": {"value": "quotes.csv"}},
                {"role": "raw_api_archive", "path": {"value": "2026/08/12/a.jsonl"}},
            ],
        }
        descriptors = one_or_more_descriptors(manifest, "raw_api_archive")
        self.assertEqual(len(descriptors), 2)
        self.assertEqual(
            [item["path"]["value"] for item in descriptors],
            ["2026/08/11/a.jsonl", "2026/08/12/a.jsonl"],
        )

    def test_raw_archive_role_requires_at_least_one_descriptor(self) -> None:
        with self.assertRaisesRegex(AuditError, "at least one"):
            one_or_more_descriptors({"run_id": "missing", "files": []}, "raw_api_archive")

    def test_empty_side_is_valid_but_has_no_complementary_ask(self) -> None:
        book = ParsedBook(
            yes_levels=((Decimal("0.30"), Decimal("2")),),
            no_levels=(),
        )
        self.assertIsNone(best_quotes(book)["yes_ask"])
        self.assertEqual(book.ask_levels("YES"), ())


if __name__ == "__main__":
    unittest.main()
