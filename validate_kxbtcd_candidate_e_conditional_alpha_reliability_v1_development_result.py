"""Independent validator for a completed conditional-alpha H-development run."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1 import canonical_sha256
from src.kxbtcd_candidate_e_conditional_alpha_reliability_v1_development import (
    ConditionalAlphaFitContractError,
    DEVELOPMENT_EVALUATION_SCHEMA,
    DEVELOPMENT_FAILURE_RECEIPT_SCHEMA,
    DEVELOPMENT_FAILURE_SCHEMA,
    DEVELOPMENT_RECEIPT_SCHEMA,
    ENTRY_DECISION_FIELDS,
    ROLLING_PREDICTION_FIELDS,
    build_development_evaluation,
    build_optimizer_failure_evaluation,
    project_development_labels,
    read_csv,
    sha256_file,
    validate_j_b_bindings,
    validate_label_source_hashes,
)

def parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser()
    p.add_argument("--prepared-feature-rows", required=True)
    p.add_argument("--preparation-freeze", required=True)
    p.add_argument("--preparation-closeout", required=True)
    p.add_argument("--h1-predictions", required=True)
    p.add_argument("--h2-predictions", required=True)
    p.add_argument("--h3-predictions", required=True)
    p.add_argument("--evaluation", required=True)
    p.add_argument("--rolling-predictions")
    p.add_argument("--entry-decisions")
    p.add_argument("--receipt", required=True)
    return p

def _load_inputs(args):
    feature_rows=read_csv(args.prepared_feature_rows)
    validate_j_b_bindings(
        feature_rows=feature_rows,
        feature_rows_path=args.prepared_feature_rows,
        preparation_freeze_path=args.preparation_freeze,
        preparation_closeout_path=args.preparation_closeout,
    )
    label_paths={"H1_OOF":args.h1_predictions,"H2":args.h2_predictions,"H3":args.h3_predictions}
    validate_label_source_hashes(label_paths)
    labels=project_development_labels({k:read_csv(v) for k,v in label_paths.items()}, enforce_frozen_counts=True)
    return feature_rows, labels

def _validate_fingerprint(doc, field):
    copy=dict(doc); supplied=copy.pop(field,None)
    if canonical_sha256(copy) != supplied:
        raise SystemExit(f"{field} does not recompute")

def main() -> int:
    args=parser().parse_args()
    feature_rows, labels=_load_inputs(args)
    persisted_eval=json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    receipt=json.loads(Path(args.receipt).read_text(encoding="utf-8"))

    if persisted_eval.get("schema_version")==DEVELOPMENT_FAILURE_SCHEMA:
        if args.rolling_predictions or args.entry_decisions:
            raise SystemExit("failure result must not have prediction/economic artifacts")
        try:
            build_development_evaluation(feature_rows, labels, enforce_frozen_counts=True)
        except ConditionalAlphaFitContractError as failure:
            expected=build_optimizer_failure_evaluation(
                feature_rows=feature_rows,
                label_rows=labels,
                failure=failure,
            )
        else:
            raise SystemExit("independent rerun did not reproduce frozen optimizer failure")
        if persisted_eval != expected:
            raise SystemExit("independent optimizer-failure evaluation mismatch")
        _validate_fingerprint(persisted_eval,"evaluation_fingerprint")
        if receipt.get("schema_version")!=DEVELOPMENT_FAILURE_RECEIPT_SCHEMA:
            raise SystemExit("failure receipt schema mismatch")
        _validate_fingerprint(receipt,"receipt_fingerprint")
        if receipt.get("overall_status")!="FAIL_OPTIMIZER_CONTRACT":
            raise SystemExit("failure receipt status mismatch")
        if receipt.get("evaluation_fingerprint")!=persisted_eval["evaluation_fingerprint"]:
            raise SystemExit("failure receipt/evaluation fingerprint mismatch")
        if receipt.get("output_sha256s",{}).get("evaluation_sha256")!=sha256_file(args.evaluation):
            raise SystemExit("failure receipt evaluation SHA mismatch")
        if receipt.get("output_sha256s",{}).get("rolling_predictions_sha256") is not None:
            raise SystemExit("failure receipt must record no rolling predictions")
        if receipt.get("output_sha256s",{}).get("entry_decisions_sha256") is not None:
            raise SystemExit("failure receipt must record no entry decisions")
        print("Conditional-alpha H-development optimizer-failure validation: PASS")
        print(f"overall_status={persisted_eval['overall_status']}")
        print(f"failure_lambda={persisted_eval['failure']['lambda']}")
        print(f"failure_fold={persisted_eval['failure']['fold']}")
        print(f"failure_message={persisted_eval['failure']['original_exception_message']}")
        print(f"evaluation_fingerprint={persisted_eval['evaluation_fingerprint']}")
        print(f"receipt_fingerprint={receipt['receipt_fingerprint']}")
        print("probability_gate=NOT_RUN_OPTIMIZER_CONTRACT_FAILED")
        print("economic_gate=NOT_RUN_OPTIMIZER_CONTRACT_FAILED")
        print("C1_C2_accessed=false")
        print("C3_accessed=false")
        print("protected_reserve_accessed=false")
        print("execution_enabled=false")
        return 0

    if persisted_eval.get("schema_version") != DEVELOPMENT_EVALUATION_SCHEMA:
        raise SystemExit("evaluation schema mismatch")
    expected_eval, expected_preds, expected_entries=build_development_evaluation(feature_rows, labels, enforce_frozen_counts=True)
    _validate_fingerprint(persisted_eval,"evaluation_fingerprint")
    if persisted_eval != expected_eval:
        raise SystemExit("independent development evaluation mismatch")
    if not args.rolling_predictions:
        raise SystemExit("rolling predictions required for normal evaluation")
    persisted_preds=read_csv(args.rolling_predictions)
    if tuple(persisted_preds[0].keys()) != tuple(ROLLING_PREDICTION_FIELDS):
        raise SystemExit("rolling prediction field order mismatch")
    if canonical_sha256(persisted_preds) != canonical_sha256([dict(r) for r in expected_preds]):
        raise SystemExit("rolling prediction mismatch")
    if expected_entries:
        if not args.entry_decisions:
            raise SystemExit("entry decisions required because economic gate ran")
        persisted_entries=read_csv(args.entry_decisions)
        if tuple(persisted_entries[0].keys()) != tuple(ENTRY_DECISION_FIELDS):
            raise SystemExit("entry decision field order mismatch")
        if canonical_sha256(persisted_entries) != canonical_sha256([dict(r) for r in expected_entries]):
            raise SystemExit("entry decision mismatch")
    elif args.entry_decisions:
        raise SystemExit("entry decisions supplied although economics did not run")
    if receipt.get("schema_version") != DEVELOPMENT_RECEIPT_SCHEMA:
        raise SystemExit("receipt schema mismatch")
    _validate_fingerprint(receipt,"receipt_fingerprint")
    if receipt.get("evaluation_fingerprint") != persisted_eval["evaluation_fingerprint"]:
        raise SystemExit("receipt/evaluation fingerprint mismatch")
    print("Conditional-alpha H-development result validation: PASS")
    print(f"overall_status={persisted_eval['overall_status']}")
    print(f"selected_lambda={persisted_eval['selected_lambda']}")
    print(f"evaluation_fingerprint={persisted_eval['evaluation_fingerprint']}")
    print(f"receipt_fingerprint={receipt['receipt_fingerprint']}")
    print(f"probability_gate={persisted_eval['probability_gate']['status']}")
    print(f"economic_gate={persisted_eval['economic_gate']['status']}")
    print("C1_C2_accessed=false")
    print("C3_accessed=false")
    print("protected_reserve_accessed=false")
    print("execution_enabled=false")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
