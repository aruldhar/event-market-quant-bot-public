from decimal import Decimal
import unittest

from src.kalshi_public import extract_best_prices


class ExtractBestPricesTests(unittest.TestCase):
    def test_converts_bid_only_book_to_quotes(self) -> None:
        orderbook = {
            "yes_dollars": [["0.4000", "5.00"], ["0.4200", "3.00"]],
            "no_dollars": [["0.5500", "8.00"], ["0.5600", "2.00"]],
        }

        result = extract_best_prices(orderbook)

        self.assertEqual(result.yes_bid, Decimal("0.4200"))
        self.assertEqual(result.yes_ask, Decimal("0.4400"))
        self.assertEqual(result.yes_spread, Decimal("0.0200"))
        self.assertEqual(result.no_bid, Decimal("0.5600"))
        self.assertEqual(result.no_ask, Decimal("0.5800"))
        self.assertEqual(result.no_spread, Decimal("0.0200"))

    def test_handles_empty_book(self) -> None:
        result = extract_best_prices({"yes_dollars": [], "no_dollars": []})
        self.assertIsNone(result.yes_bid)
        self.assertIsNone(result.yes_ask)
        self.assertIsNone(result.no_bid)
        self.assertIsNone(result.no_ask)


if __name__ == "__main__":
    unittest.main()
