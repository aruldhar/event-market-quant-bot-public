"""Checkpoint 21N-J-B outcome-blind conditional-alpha materialization CLI.

Do not run this real-data command until 21N-J-A implementation is safely closed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1_materialization import (
    FEATURE_FIELDS,
    build_preparation_freeze,
    materialize_conditional_alpha_rows,
    read_csv,
    sha256_file,
    validate_j_a_closeout_receipt,
    validate_parent_preparation,
    write_csv,
)

IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_e_conditional_alpha_reliability_v1.py",
    "src/kxbtcd_candidate_e_conditional_alpha_reliability_v1_materialization.py",
    "prepare_kxbtcd_candidate_e_conditional_alpha_reliability_v1.py",
    "validate_kxbtcd_candidate_e_conditional_alpha_reliability_v1_preparation.py",
)

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--j-a-closeout-receipt", default="docs/LAST_CHECKPOINT_CLOSEOUT.json")
    p.add_argument("--parent-preparation-freeze", required=True)
    p.add_argument("--parent-feature-rows", required=True)
    p.add_argument("--preoutcome", required=True)
    p.add_argument("--output-dir", required=True)
    return p

def main() -> int:
    args = parser().parse_args()
    repo = Path(__file__).resolve().parent
    validate_j_a_closeout_receipt(args.j_a_closeout_receipt)
    validate_parent_preparation(
        preparation_freeze_path=args.parent_preparation_freeze,
        feature_rows_path=args.parent_feature_rows,
        preoutcome_path=args.preoutcome,
    )
    rows = materialize_conditional_alpha_rows(
        parent_feature_rows=read_csv(args.parent_feature_rows),
        preoutcome_rows=read_csv(args.preoutcome),
        enforce_frozen_counts=True,
    )
    out = Path(args.output_dir)
    feature_path = out / "conditional_alpha_reliability_v1_development_features.csv"
    freeze_path = out / "conditional_alpha_reliability_v1_preparation_freeze.json"
    write_csv(feature_path, FEATURE_FIELDS, rows)
    implementation_hashes = {name: sha256_file(repo / name) for name in IMPLEMENTATION_FILES}
    freeze = build_preparation_freeze(
        rows,
        parent_preparation_path=args.parent_preparation_freeze,
        parent_feature_rows_path=args.parent_feature_rows,
        preoutcome_path=args.preoutcome,
        output_feature_rows_path=feature_path,
        implementation_sha256s=implementation_hashes,
        enforce_frozen_counts=True,
    )
    freeze_path.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"feature_rows={len(rows)}")
    print(f"feature_rows_fingerprint={freeze['feature_rows_fingerprint']}")
    print(f"prepared_output_sha256={freeze['prepared_output_sha256']}")
    print(f"preparation_fingerprint={freeze['preparation_fingerprint']}")
    print("outcomes_attached=false")
    print("gamma_fit_performed=false")
    print("lambda_selected=false")
    print("strategy_pnl_calculated=false")
    print("c1_c2_accessed=false")
    print("c3_accessed=false")
    print("protected_reserve_accessed=false")
    print("network_accessed=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
