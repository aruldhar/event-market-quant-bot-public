"""Validate readiness for the 60 frozen outcome-blind scenarios over repair-203 caches."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True

from materialize_kxbtcd_candidate_e_v2_paths_repair_203 import (
    EXPECTED_REPAIR_COVERAGE_SHA256,
    EXPECTED_SUPERSEDED_Y_A3_PATH_SHA256,
    validate_readiness,
)


def main() -> int:
    try:
        ready = validate_readiness(Path("."), verify_cache_hashes=True)
    except Exception as error:
        print("CANDIDATE-E REPAIR-203 60-PATH READINESS: FAIL CLOSED")
        print(f"{type(error).__name__}: {error}")
        return 1
    coverage = ready["coverage"]
    print("CANDIDATE-E REPAIR-203 60-PATH READINESS: PASS")
    print("Sealed repair caches:", len(ready["dynamic_tickers"]))
    print("Frozen policy scenarios:", len(ready["scenario_specs"]))
    print("Repair operations:", coverage["repair_operation_count"])
    print("Failed pairs addressed:", coverage["original_failed_pairs_addressed"])
    print("Residual hard boundaries:", coverage["remaining_unreconciled_pair_count"])
    print("Repair coverage SHA256:", EXPECTED_REPAIR_COVERAGE_SHA256)
    print("Superseded Y-A3 path SHA256:", EXPECTED_SUPERSEDED_Y_A3_PATH_SHA256)
    print("Strategy: NOT RUN | Outcomes: NOT ACCESSED | P&L: NOT CALCULATED | Orders: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
