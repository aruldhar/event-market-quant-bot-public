import unittest
from unittest.mock import patch

from src.kalshi_public import (
    KalshiPublicClient,
    RawRecordReference,
    SourcedApiResponse,
)


class ListOpenMarketsTests(unittest.TestCase):
    def test_passes_series_ticker_to_markets_endpoint(self) -> None:
        client = KalshiPublicClient()

        fake_response = {
            "markets": [
                {
                    "ticker": "KXBTC15M-TEST",
                    "series_ticker": "KXBTC15M",
                }
            ],
            "cursor": "",
        }

        sourced_response = SourcedApiResponse(
            payload=fake_response,
            raw_record=RawRecordReference(
                source="kalshi_public_rest",
                session_id="session-1",
                request_id="request-1",
            ),
        )

        with patch.object(
            client,
            "_get_with_lineage",
            return_value=sourced_response,
        ) as mocked_get:
            markets = client.list_open_markets(
                series_ticker="KXBTC15M"
            )

        self.assertEqual(len(markets), 1)
        self.assertEqual(
            markets[0]["series_ticker"],
            "KXBTC15M",
        )

        mocked_get.assert_called_once()

        called_path = mocked_get.call_args.args[0]
        called_params = mocked_get.call_args.kwargs["params"]

        self.assertEqual(called_path, "/markets")
        self.assertEqual(called_params["status"], "open")
        self.assertEqual(
            called_params["series_ticker"],
            "KXBTC15M",
        )


if __name__ == "__main__":
    unittest.main()