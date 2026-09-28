import pytest

from src.kxbtcd_candidate_e_coinbase_rest_recovery import (
    CoinbaseRestRecoveryError,
    build_recovery_evidence,
)


def _trade(trade_id, price=None):
    return {
        "trade_id": trade_id,
        "time": "2026-09-04T03:22:00Z",
        "price": str(
            price if price is not None else 80000 + trade_id
        ),
        "size": "0.01",
        "side": "sell",
    }


def test_recovery_coverage_requires_exact_boundary_and_target():
    complete = build_recovery_evidence(
        pages=[[
            _trade(105),
            _trade(103),
            _trade(100),
        ]],
        start_exclusive_trade_id=100,
        target_inclusive_trade_id=105,
    )

    assert complete.coverage_proven is True
    assert complete.boundary_trade_seen is True
    assert complete.target_trade_seen is True

    # Numeric gaps are allowed. REST page coverage, not integer enumeration,
    # is the authoritative recovery proof.
    assert [
        row["trade_id"]
        for row in complete.interval_rows
    ] == [103, 105]


def test_recovery_without_boundary_is_incomplete():
    evidence = build_recovery_evidence(
        pages=[[
            _trade(105),
            _trade(104),
        ]],
        start_exclusive_trade_id=100,
        target_inclusive_trade_id=105,
    )

    assert evidence.coverage_proven is False
    assert evidence.boundary_trade_seen is False
    assert evidence.target_trade_seen is True


def test_recovery_without_target_is_incomplete():
    evidence = build_recovery_evidence(
        pages=[[
            _trade(104),
            _trade(100),
        ]],
        start_exclusive_trade_id=100,
        target_inclusive_trade_id=105,
    )

    assert evidence.coverage_proven is False
    assert evidence.boundary_trade_seen is True
    assert evidence.target_trade_seen is False


def test_identical_pagination_overlap_is_allowed():
    row = _trade(103)

    evidence = build_recovery_evidence(
        pages=[
            [_trade(105), row],
            [row, _trade(100)],
        ],
        start_exclusive_trade_id=100,
        target_inclusive_trade_id=105,
    )

    assert evidence.coverage_proven is True
    assert [
        r["trade_id"]
        for r in evidence.interval_rows
    ] == [103, 105]


def test_conflicting_duplicate_trade_fails_closed():
    with pytest.raises(CoinbaseRestRecoveryError):
        build_recovery_evidence(
            pages=[
                [_trade(105), _trade(103, "80001")],
                [_trade(103, "90001"), _trade(100)],
            ],
            start_exclusive_trade_id=100,
            target_inclusive_trade_id=105,
        )
