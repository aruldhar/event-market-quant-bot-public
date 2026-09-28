"""Zero-network readiness validator for Candidate-E July-10 settlement scoring."""
from __future__ import annotations

from pathlib import Path

from src import kxbtcd_candidate_e_v2_july10_settlement_evaluator as evaluator


def main() -> int:
    repo = Path.cwd().resolve()
    contract, paths = evaluator.load_frozen_inputs(repo)
    fallback = evaluator.fallback_tickers_by_class(contract, paths)

    # This implementation checkpoint must remain pre-outcome.
    require_absent = [
        repo / evaluator.SETTLEMENT_MANIFEST_PATH,
        repo / evaluator.PNL_REPORT_PATH,
    ]
    for path in require_absent:
        evaluator.require(not path.exists(), f"outcome artifact already exists during readiness freeze: {path}")

    cache_dir = repo / evaluator.SETTLEMENT_CACHE_DIR
    if cache_dir.exists():
        evaluator.require(
            not any(cache_dir.glob("*.json")),
            "settlement cache already contains outcome records during readiness freeze",
        )

    evaluator.require(
        all(t.startswith("KXBTCD-26JUL10") for t in fallback["exact_required"]),
        "unexpected exact fallback ticker outside July-10 KXBTCD scope",
    )
    for ticker in fallback["exact_required"]:
        evaluator.require(
            evaluator.market_filter_params(ticker) == {"tickers": ticker},
            "exact ticker-filter parameters changed",
        )
        evaluator.require(
            evaluator.market_source_endpoint(evaluator.LIVE_MARKETS_PATH, ticker)
            == f"/markets?tickers={ticker}",
            "live exact-filter endpoint changed",
        )
        evaluator.require(
            evaluator.market_source_endpoint(evaluator.HISTORICAL_MARKETS_PATH, ticker)
            == f"/historical/markets?tickers={ticker}",
            "historical exact-filter endpoint changed",
        )
    evaluator.require(evaluator.LIVE_MARKETS_PATH == "/markets", "live market path changed")
    evaluator.require(
        evaluator.HISTORICAL_MARKETS_PATH == "/historical/markets",
        "historical market path changed",
    )

    print("CANDIDATE-E JULY10 SETTLEMENT READINESS: PASS")
    print("Settlement transport: live exact-ticker filter -> historical exact-ticker fallback")
    print("Scenario classes: 27 EXACT / 33 CENSORED")
    print("Exact fallback tickers requiring future outcome access:", len(fallback["exact_required"]))
    for ticker in fallback["exact_required"]:
        print(" ", ticker)
    print("Censored fallback tickers not independently requested:", len(fallback["censored_fallback"]))
    print("Exact/censored ticker overlap:", len(fallback["overlap"]))
    print("Real --collect gate: BLOCKED UNTIL THIS IMPLEMENTATION IS CLOSED/PUSHED")
    print("Settlement outcomes: NOT ACCESSED")
    print("Strategy P&L: NOT CALCULATED | Network: 0 | Orders: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
