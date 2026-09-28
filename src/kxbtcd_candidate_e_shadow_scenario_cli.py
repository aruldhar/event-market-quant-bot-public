"""Command-line access to the descriptor-verified offline scenario runner."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from typing import Sequence

from .kxbtcd_candidate_e_shadow_scenario_runner import (
    iter_verified_hybrid_exit_observations,
)
from .kxbtcd_candidate_e_v2_micro_hybrid_exit_offline import ReconciledPosition


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("must be a decimal") from exc
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("must be finite")
    return parsed


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate verified archived Kalshi books without venue access"
    )
    parser.add_argument("--descriptor", action="append", required=True)
    parser.add_argument("--subscribed-ticker", action="append", required=True)
    parser.add_argument("--market-ticker", required=True)
    parser.add_argument("--remaining-quantity", required=True, type=_decimal)
    parser.add_argument("--realized-net-proceeds", required=True, type=_decimal)
    parser.add_argument("--supplied-exit-fee", required=True, type=_decimal)
    parser.add_argument("--required-total-net-proceeds", required=True, type=_decimal)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    observations = iter_verified_hybrid_exit_observations(
        args.descriptor,
        subscribed_tickers=args.subscribed_ticker,
        market_ticker=args.market_ticker,
        position=ReconciledPosition(
            remaining_quantity=args.remaining_quantity,
            realized_net_proceeds=args.realized_net_proceeds,
        ),
        supplied_exit_fee=args.supplied_exit_fee,
        required_total_net_proceeds=args.required_total_net_proceeds,
    )
    for item in observations:
        print(json.dumps({
            "market_ticker": item.market_ticker,
            "received_utc": item.received_utc,
            "received_monotonic_ns": item.received_monotonic_ns,
            "state": item.state.value,
            "full_exit_eligible": item.full_exit_eligible,
            "worst_price_required": (
                None if item.worst_price_required is None
                else format(item.worst_price_required, "f")
            ),
            "total_net_proceeds_if_filled": (
                None if item.total_net_proceeds_if_filled is None
                else format(item.total_net_proceeds_if_filled, "f")
            ),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
