"""Independent validator for a future 21N-J-B outcome-blind materialization."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1_materialization import (
    canonical_rows_fingerprint,
    materialize_conditional_alpha_rows,
    read_csv,
    sha256_file,
    validate_parent_preparation,
    validate_preparation_freeze,
)

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--parent-preparation-freeze", required=True)
    p.add_argument("--parent-feature-rows", required=True)
    p.add_argument("--preoutcome", required=True)
    p.add_argument("--prepared-feature-rows", required=True)
    p.add_argument("--preparation-freeze", required=True)
    return p

def main() -> int:
    args = parser().parse_args()
    validate_parent_preparation(
        preparation_freeze_path=args.parent_preparation_freeze,
        feature_rows_path=args.parent_feature_rows,
        preoutcome_path=args.preoutcome,
    )
    expected = materialize_conditional_alpha_rows(
        parent_feature_rows=read_csv(args.parent_feature_rows),
        preoutcome_rows=read_csv(args.preoutcome),
        enforce_frozen_counts=True,
    )
    persisted = read_csv(args.prepared_feature_rows)
    if canonical_rows_fingerprint(expected) != canonical_rows_fingerprint(persisted):
        raise SystemExit("independent rematerialization mismatch")
    freeze = json.loads(Path(args.preparation_freeze).read_text(encoding="utf-8"))
    validate_preparation_freeze(
        freeze, rows=persisted, output_feature_rows_path=args.prepared_feature_rows
    )
    if freeze["parent_feature_file_sha256"] != sha256_file(args.parent_feature_rows):
        raise SystemExit("parent feature SHA mismatch")
    print("Conditional-alpha outcome-blind preparation validation: PASS")
    print(f"feature_rows={len(persisted)}")
    print(f"feature_rows_fingerprint={freeze['feature_rows_fingerprint']}")
    print(f"preparation_fingerprint={freeze['preparation_fingerprint']}")
    print("outcomes_attached=false")
    print("gamma_fit_performed=false")
    print("lambda_selected=false")
    print("c1_c2_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
