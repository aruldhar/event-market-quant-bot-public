from datetime import datetime, timedelta, timezone
from decimal import Decimal

from analyze_kxbtc15m_bounded_simulation import Snapshot
from analyze_kxbtc15m_entry_states import (
    depth_balance_band,
    entry_features,
    path_features,
    signed_move_band,
    state_30s,
)
from audit_kxbtc15m_raw_depth import ParsedBook


def book(yes_bid: str, no_bid: str, quantity: str = "100") -> ParsedBook:
    return ParsedBook(
        ((Decimal(yes_bid), Decimal(quantity)),),
        ((Decimal(no_bid), Decimal(quantity)),),
    )


def test_path_features_directional_fall():
    result = path_features([
        (-2.0, Decimal("0.40")),
        (-1.0, Decimal("0.30")),
        (0.0, Decimal("0.20")),
    ])
    assert result["move"] == -0.2
    assert result["efficiency"] == -1.0
    assert result["drawdown"] == 0.2


def test_path_features_choppy_counts_turns():
    result = path_features([
        (-3.0, Decimal("0.20")), (-2.0, Decimal("0.30")),
        (-1.0, Decimal("0.20")), (0.0, Decimal("0.30")),
    ])
    assert result["direction_changes"] == 2.0
    assert abs(result["efficiency"] - (1 / 3)) < 1e-12


def test_entry_features_use_only_prior_snapshots():
    start = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    values = [
        Snapshot(start, "0", book("0.20", "0.60")),
        Snapshot(start + timedelta(seconds=10), "1", book("0.20", "0.70")),
        Snapshot(start + timedelta(seconds=20), "2", book("0.90", "0.05")),
    ]
    features = entry_features(values, 1)
    assert features["decision_side"] == "YES"
    assert features["decision_ask"] == 0.30
    # The future t=20 book must not affect the trailing move at decision t=10.
    assert features["move_30s"] == -0.1


def test_state_detects_deep_drawdown_rebound():
    assert state_30s({"drawdown_30s": 0.08, "move_10s": 0.02}) == "deep_drawdown_rebounding"


def test_bands_have_stable_boundaries():
    assert signed_move_band(-0.05) == "01_down_5c_plus"
    assert signed_move_band(0.0) == "03_flat_within_2c"
    assert depth_balance_band(0.3) == "03_bid_heavy"
