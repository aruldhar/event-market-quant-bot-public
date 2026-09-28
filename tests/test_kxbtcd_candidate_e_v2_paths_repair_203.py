import copy

import pytest

import materialize_kxbtcd_candidate_e_v2_paths_repair_203 as target


def synthetic_audit(ticker, *, original=2, addressed=(0,), residual=1, operations=1,
                    quarantined=(1,), changed=3):
    return {
        "ticker": ticker,
        "original_failed_pair_count": original,
        "original_failed_pairs_addressed": list(addressed),
        "remaining_unreconciled_pair_count": residual,
        "repair_operation_count": operations,
        "quarantined_snapshot_indices": list(quarantined),
        "repaired_adjacency_count": changed,
        "repair_plan_sha256": target.EXPECTED_PLAN_SHA256,
        "pinned_changed_adjacencies": [{"exact": True}] * changed,
        "safety": {
            "candidate_e_scored": False,
            "raw_snapshots_mutated": False,
            "paid_rows_mutated": False,
            "strategy_run": False,
            "outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "network_requests": 0,
            "orders_placed": 0,
        },
    }


def synthetic_coverage():
    audits = []
    # Construct totals exactly: 47 tickers, 748 original, 203 addressed,
    # 545 residual, 110 ops, 93 quarantined, 364 changed adjacencies.
    for i in range(47):
        audits.append(
            synthetic_audit(
                f"T{i:02d}",
                original=16 if i < 43 else 15,
                addressed=tuple(range(5 if i < 15 else 4)),
                residual=11,
                operations=3 if i < 16 else 2,
                quarantined=(0, 1) if i < 46 else (0,),
                changed=8 if i < 35 else 7,
            )
        )
    # Fix aggregate totals deterministically.
    # originals currently 748 exactly.
    assert sum(a["original_failed_pair_count"] for a in audits) == 748
    # addressed currently 203 exactly.
    assert sum(len(a["original_failed_pairs_addressed"]) for a in audits) == 203
    # residual must be original-addressed per ticker.
    for a in audits:
        a["remaining_unreconciled_pair_count"] = (
            a["original_failed_pair_count"] - len(a["original_failed_pairs_addressed"])
        )
    assert sum(a["remaining_unreconciled_pair_count"] for a in audits) == 545
    # operations currently 110 exactly.
    assert sum(a["repair_operation_count"] for a in audits) == 110
    # quarantined currently 93 exactly.
    assert sum(len(a["quarantined_snapshot_indices"]) for a in audits) == 93
    # changed currently 364 exactly.
    assert sum(a["repaired_adjacency_count"] for a in audits) == 364
    return {
        "schema_version": "candidate_e_v2_repair_203_coverage.v1",
        "checkpoint_id": "21N-Y-A5",
        "prepared_ticker_count": 47,
        "full_ticker_count": 47,
        "repair_operation_count": 110,
        "original_failed_pairs_addressed": 203,
        "remaining_unreconciled_pair_count": 545,
        "repair_plan_sha256": target.EXPECTED_PLAN_SHA256,
        "parent_replay_precision_coverage_sha256": (
            target.EXPECTED_PARENT_REPLAY_PRECISION_COVERAGE_SHA256
        ),
        "ticker_audits": audits,
        "safety": {
            "candidate_e_scored": False,
            "strategy_run": False,
            "outcomes_accessed": False,
            "strategy_pnl_calculated": False,
            "network_requests": 0,
            "orders_placed": 0,
        },
    }


def test_validate_coverage_payload_accepts_exact_frozen_totals():
    by_ticker = target.validate_coverage_payload(synthetic_coverage())
    assert len(by_ticker) == 47


def test_validate_coverage_payload_rejects_nonexact_pinned_edge():
    payload = synthetic_coverage()
    payload["ticker_audits"][0]["pinned_changed_adjacencies"][0]["exact"] = False
    with pytest.raises(target.RepairPathError, match="non-exact"):
        target.validate_coverage_payload(payload)


def test_validate_coverage_payload_rejects_residual_accounting_drift():
    payload = synthetic_coverage()
    payload["ticker_audits"][0]["remaining_unreconciled_pair_count"] += 1
    with pytest.raises(target.RepairPathError, match="accounting mismatch"):
        target.validate_coverage_payload(payload)


def test_scenario_specs_are_exactly_sixty_for_four_frozen_events():
    ladders = {f"E{i}": object() for i in range(4)}
    specs = target.scenario_specs(ladders)
    assert len(specs) == 60
    assert len(set(specs)) == 60


def test_scenario_identity_normalizes_decimal_threshold_to_frozen_json_string():
    from decimal import Decimal
    specs = [("E", Decimal("0.0100"), 500)]
    payload = {
        "policy_results": [
            {"event_ticker": "E", "threshold_dollars": "0.01", "latency_ms": 500}
        ]
    }
    assert target.scenario_keys_from_specs(specs) == target.scenario_keys_from_payload(payload)
