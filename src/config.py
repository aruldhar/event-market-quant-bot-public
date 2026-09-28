"""Project configuration.

Phase 1 deliberately uses only Kalshi's public production market-data API.
It does not use an API key and cannot place orders.
"""

from pathlib import Path


KALSHI_PUBLIC_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_PAGE_LIMIT = 1000
BTC_KEYWORDS = ("bitcoin", "btc")

PRIMARY_BTC_SERIES_TICKER = "KXBTC15M"
DEFAULT_RAW_LOG_ROOT = Path("data/raw/kalshi_rest")
DEFAULT_MANIFEST_ROOT = Path("data/manifests")
DEFAULT_RUNTIME_EVENT_ROOT = Path("logs/runtime")
