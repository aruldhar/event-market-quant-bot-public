from decimal import Decimal

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel,
    BookState,
    VerifiedSegmentTimeline,
    VerifiedTickerTimeline,
)
from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator import (
    NONSTRUCTURAL_DOMAIN_LABEL,
    STRUCTURAL_DOMAIN_LABEL,
    LadderMarket,
    _rearmed,
    spot_window,
)
from src.kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2_simulator_freeze import (
    EXPECTED_IMPLEMENTATION_FINGERPRINT,
    canonical_fingerprint,
    validate_freeze,
)


def _ladder(n=20, structural_rank=None):
    rows = []
    for rank in range(n):
        rows.append(
            LadderMarket(
                event_ticker="KXBTCD-TEST",
                market_ticker=f"KXBTCD-TEST-T{10000 + 100*rank}",
                strike=Decimal(10000 + 100*rank),
                strike_rank_zero_based=rank,
                event_market_count=n,
                historical_structural_role=(
                    "q50" if structural_rank == rank else None
                ),
            )
        )
    return tuple(rows)


def test_implementation_freeze_exact():
    payload = validate_freeze(".")
    assert payload["implementation_fingerprint"] == EXPECTED_IMPLEMENTATION_FINGERPRINT
    assert canonical_fingerprint(payload) == EXPECTED_IMPLEMENTATION_FINGERPRINT


def test_interior_atm_window_is_exact_plus_minus_five():
    ladder = _ladder()
    window = spot_window(
        event_ticker="KXBTCD-TEST",
        btc_spot=Decimal("11025"),
        event_ladder=ladder,
    )
    # Closest strike is rank 10 / 11000.
    assert len(window) == 11
    assert window[0].strike_rank_zero_based == 5
    assert window[-1].strike_rank_zero_based == 15
    assert [x.rank_from_atm for x in window] == list(range(-5, 6))


def test_atm_tie_break_is_lower_strike_and_boundary_clips_without_replacement():
    ladder = _ladder()
    # Exactly halfway between 10000 and 10100 -> lower strike rank 0.
    window = spot_window(
        event_ticker="KXBTCD-TEST",
        btc_spot=Decimal("10050"),
        event_ladder=ladder,
    )
    assert window[0].atm_rank_zero_based == 0
    assert window[0].atm_strike == Decimal("10000")
    assert len(window) == 6
    assert [x.strike_rank_zero_based for x in window] == list(range(0, 6))


def test_domain_label_is_structural_only_for_frozen_historical_role():
    ladder = _ladder(structural_rank=10)
    window = spot_window(
        event_ticker="KXBTCD-TEST",
        btc_spot=Decimal("11000"),
        event_ladder=ladder,
    )
    labels = {x.strike_rank_zero_based: x.market_domain_label for x in window}
    assert labels[10] == STRUCTURAL_DOMAIN_LABEL
    assert labels[9] == NONSTRUCTURAL_DOMAIN_LABEL
    assert labels[11] == NONSTRUCTURAL_DOMAIN_LABEL


def test_reference_leaving_window_rearms_without_reference_book():
    # _rearmed should not require an evaluable reference book once causal BTC
    # moves the reference market outside ATM±5.
    ladder = _ladder()
    current = spot_window(
        event_ticker="KXBTCD-TEST",
        btc_spot=Decimal("11900"),
        event_ladder=ladder,
    )

    class Reference:
        market_ticker = "KXBTCD-TEST-T10000"
        side = "YES"

    yes, reason = _rearmed(
        evaluations=(),
        current_window=current,
        btc_available=True,
        reference=Reference(),
        threshold=Decimal("0.01"),
    )
    assert yes is True
    assert reason == "REFERENCE_LEFT_SPOT_WINDOW"
