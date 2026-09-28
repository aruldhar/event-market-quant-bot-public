from decimal import Decimal
import pytest

from src.kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel,
    BookState,
    VerifiedSegmentTimeline,
    VerifiedTickerTimeline,
)
from src.kxbtcd_candidate_e_v2_execution_quantity_transport_amendment import (
    V2QuantityTransportAmendmentError,
    canonicalize_execution_quantity,
    canonicalize_verified_ticker_timeline,
)
from src.kxbtcd_candidate_e_v2_execution_quantity_transport_amendment_freeze import (
    EXPECTED_AMENDMENT_FINGERPRINT,
    canonical_fingerprint,
    validate_amendment,
)


def test_amendment_freeze_exact():
    p = validate_amendment(".")
    assert p["amendment_fingerprint"] == EXPECTED_AMENDMENT_FINGERPRINT
    assert canonical_fingerprint(p) == EXPECTED_AMENDMENT_FINGERPRINT


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("250.00000000000068", "250.00"),
        ("237.48000000000002", "237.48"),
        ("224.63000000000466", "224.63"),
        ("1486.8000000000002", "1486.80"),
        ("724.6300000000047", "724.63"),
        ("0", "0.00"),
        ("1.00", "1.00"),
    ],
)
def test_known_transport_residues_canonicalize(raw, expected):
    assert canonicalize_execution_quantity(Decimal(raw)) == Decimal(expected)


def test_exact_boundary_residue_is_accepted():
    assert canonicalize_execution_quantity(
        Decimal("10.010000001")
    ) == Decimal("10.01")


@pytest.mark.parametrize(
    "raw",
    [
        "10.0100000011",
        "1.005",
        "-0.0000000001",
        "NaN",
        "Infinity",
    ],
)
def test_material_or_invalid_quantity_fails_closed(raw):
    with pytest.raises(V2QuantityTransportAmendmentError):
        canonicalize_execution_quantity(Decimal(raw))


def test_timeline_adapter_preserves_segments_timestamps_prices_and_only_changes_quantity():
    original = VerifiedTickerTimeline(
        ticker="KXBTCD-TEST",
        segments=(
            VerifiedSegmentTimeline(
                segment_index=3,
                start_timestamp_ms=1000,
                end_timestamp_ms=2000,
                states=(
                    BookState(
                        timestamp_ms=1000,
                        yes_bids=(
                            BookLevel(
                                price=Decimal("0.23"),
                                quantity=Decimal("250.00000000000068"),
                            ),
                        ),
                        yes_asks=(
                            BookLevel(
                                price=Decimal("0.24"),
                                quantity=Decimal("224.63000000000466"),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )

    amended = canonicalize_verified_ticker_timeline(original)

    assert amended.ticker == original.ticker
    assert len(amended.segments) == 1
    seg = amended.segments[0]
    assert seg.segment_index == 3
    assert seg.start_timestamp_ms == 1000
    assert seg.end_timestamp_ms == 2000
    assert seg.states[0].timestamp_ms == 1000
    assert seg.states[0].yes_bids[0].price == Decimal("0.23")
    assert seg.states[0].yes_bids[0].quantity == Decimal("250.00")
    assert seg.states[0].yes_asks[0].price == Decimal("0.24")
    assert seg.states[0].yes_asks[0].quantity == Decimal("224.63")


def test_failed_yb_exposure_is_recorded_honestly():
    p = validate_amendment(".")
    f = p["observed_failure"]
    assert f["candidate_e_nonstructural_scoring_started"] is True
    assert f["completed_path_artifact_created"] is False
    assert f["settlement_outcomes_accessed"] is False
