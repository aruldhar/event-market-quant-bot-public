from __future__ import annotations

import argparse
from pathlib import Path

from src.kxbtcd_candidate_e_entry_model_v1_validation import (
    DEPENDENCY_FILES,
    IMPLEMENTATION_FILES,
    IMPLEMENTATION_FREEZE_DEFAULT,
    read_json,
    sha256_file,
    validate_implementation_freeze_document,
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--freeze",
        default=str(IMPLEMENTATION_FREEZE_DEFAULT),
    )
    args = parser.parse_args()

    implementation_hashes = {
        relative: sha256_file(relative)
        for relative in IMPLEMENTATION_FILES
    }
    dependency_hashes = {
        relative: sha256_file(relative)
        for relative in DEPENDENCY_FILES
    }
    document = read_json(Path(args.freeze))
    validate_implementation_freeze_document(
        document,
        implementation_sha256s=implementation_hashes,
        dependency_sha256s=dependency_hashes,
    )

    print("Candidate-E Entry Model v1 validation implementation freeze validation: PASS")
    print(
        "validation_implementation_fingerprint="
        + document["validation_implementation_fingerprint"]
    )
    print("outcomes_read_during_validation=false")
    print("validation_scores_calculated=false")
    print("C3_reserve_PnL_execution=UNTOUCHED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
