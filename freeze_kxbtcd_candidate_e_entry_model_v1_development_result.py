from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_HEAD = "77421809b847e3f4c6cdc8e75aa0a0c8955882e9"
EXPECTED_EVALUATION_FINGERPRINT = "78de7bf612830c7fbbeb14b56a34bd1a582f8e69738672d420314b1c4ff79aac"
EXPECTED_EVALUATION_SHA256 = "2f32edeef294a6769c9d49a456c493771a76ce5aebefafc1bc11d375765b3365"
EXPECTED_LAMBDA_SHA256 = "54cf07059498683895fba674f1ee94163e9cea3f4a597822df7e31093d253f51"
EXPECTED_RECEIPT_SHA256 = "14c75f8f0ccbef081e841fd75e6adab500b459e1fcdcee3d002c328c1bf11523"
EXPECTED_FREEZE_FINGERPRINT = "a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e"
OUTPUT = Path("configs/kxbtcd_candidate_e_entry_model_v1_development_freeze.json")

EXPECTED_FREEZE = {'schema_version': 'kxbtcd_candidate_e_entry_model_v1_development_freeze.v1', 'checkpoint_id': '21M', 'model_id': 'kxbtcd_candidate_e_entry_residual_logistic.v1', 'status': 'DEVELOPMENT_SELECTED_FOR_C1_C2_VALIDATION', 'development_evidence': {'feature_rows': 76419, 'events': 2570, 'preparation_fingerprint': '2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d', 'development_label_fingerprint': 'a41f3f31d9df31119cfe0232052166b478714d68ebed1aed699227262edb3572', 'evaluation_fingerprint': '78de7bf612830c7fbbeb14b56a34bd1a582f8e69738672d420314b1c4ff79aac'}, 'selection': {'lambda_grid': [0.001, 0.01, 0.1, 1.0, 10.0], 'selected_lambda': 0.01, 'selection_metric': 'pooled_H2_H3_event_equal_log_loss', 'exact_tie_rule': 'larger_lambda', 'lambda_scores': [{'lambda': 0.001, 'pooled_event_equal_brier': 0.010120217189634696, 'pooled_event_equal_log_loss': 0.03750794245585257}, {'lambda': 0.01, 'pooled_event_equal_brier': 0.010091977884008856, 'pooled_event_equal_log_loss': 0.03736587903471904}, {'lambda': 0.1, 'pooled_event_equal_brier': 0.010091838114726602, 'pooled_event_equal_log_loss': 0.037396716582858855}, {'lambda': 1.0, 'pooled_event_equal_brier': 0.010092266527927092, 'pooled_event_equal_log_loss': 0.03739969196514396}, {'lambda': 10.0, 'pooled_event_equal_brier': 0.010094571043219456, 'pooled_event_equal_log_loss': 0.03740562789591962}]}, 'rolling_origin_diagnostics': {'H2': {'candidate_e_event_equal_brier': 0.00993578955128811, 'candidate_e_event_equal_log_loss': 0.035893546124196776, 'candidate_e_minus_model2_brier': 1.944132021273158e-05, 'candidate_e_minus_model2_log_loss': 0.00010360998900234286, 'median_event_candidate_e_minus_model2_log_loss': 0.00011629529712325263, 'model2_event_equal_brier': 0.009916348231075378, 'model2_event_equal_log_loss': 0.03578993613519443}, 'H3': {'candidate_e_event_equal_brier': 0.01025442810344244, 'candidate_e_event_equal_log_loss': 0.0389205640330361, 'candidate_e_minus_model2_brier': -1.317943349994112e-05, 'candidate_e_minus_model2_log_loss': -2.1257901207466512e-05, 'median_event_candidate_e_minus_model2_log_loss': 0.00012704643913592355, 'model2_event_equal_brier': 0.010267607536942381, 'model2_event_equal_log_loss': 0.038941821934243566}, 'pooled_H2_H3': {'candidate_e_event_equal_brier': 0.010095108827365279, 'candidate_e_event_equal_log_loss': 0.03740705507861643, 'candidate_e_minus_model2_brier': 3.1309433564229855e-06, 'candidate_e_minus_model2_log_loss': 4.11760438973896e-05, 'median_event_candidate_e_minus_model2_log_loss': 0.00012469097768141543, 'model2_event_equal_brier': 0.010091977884008856, 'model2_event_equal_log_loss': 0.03736587903471904}}, 'full_development_fit': {'lambda': 0.01, 'iterations': 3, 'objective': 0.03580632990339692, 'coefficients': {'ask_range_1m': -0.042127167641594805, 'bid_range_1m': 0.06960640572382862, 'intercept': 0.02485156246153858, 'log1p_contracts_5m': 0.022430167811378236, 'log1p_open_interest': -0.02712793629324421, 'log1p_trade_count_5m': 0.015485895477844635, 'log1p_volume_1m': -0.018101341774114113, 'mid_move_1m': -0.011780127947546222, 'r_5m': -0.0016684975147639594, 'role_q10': 0.008358898888790328, 'role_q30': 0.00324970584133779, 'role_q70': 0.007042100245105669, 'role_q90': -0.007655039051359103, 'spread_change_1m': -0.005076511662581685, 'spread_t': -0.03447286421017788, 'taker_imbalance_5m': -0.0014675063045773915, 'ttc_30': 0.012375444852910221, 'ttc_35': 0.01011391780542563, 'ttc_40': 0.006674577607294016, 'ttc_45': -0.0012583120243283544, 'ttc_50': 0.00025920745209560007}, 'scaler': {'ask_range_1m': {'mean': 0.0323259652682312, 'std': 0.09298219119664357}, 'bid_range_1m': {'mean': 0.0335924811958386, 'std': 0.09601851184890985}, 'log1p_contracts_5m': {'mean': 0.41950208333777056, 'std': 1.5624573093584808}, 'log1p_open_interest': {'mean': 0.712723028715934, 'std': 2.1180816476730664}, 'log1p_trade_count_5m': {'mean': 0.14444158410885788, 'std': 0.567858481027302}, 'log1p_volume_1m': {'mean': 0.1878310876982865, 'std': 0.9593453292339567}, 'mid_move_1m': {'mean': -0.00014231897754665119, 'std': 0.0409088142906593}, 'r_5m': {'mean': 0.1136146573350855, 'std': 11.626042353148252}, 'spread_change_1m': {'mean': -0.0007295775914526802, 'std': 0.0792314563903787}, 'spread_t': {'mean': 0.16079388196320404, 'std': 0.16945760040410893}, 'taker_imbalance_5m': {'mean': 0.0055309055706147595, 'std': 0.21270359750012333}}}, 'provenance': {'source_sha256s': {'feature_rows': '0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c', 'h1_predictions': '867a77cbbf034a574983cb6fb301a77614674d3254297f8e15db377d5c34df16', 'h2_predictions': '4aa6efe3c3bdc231fc8289f11fe01e1ad5a65910ae0ea92d2586447fd6b7d3d6', 'h3_predictions': '091affc5ac088aa61db43a5df18f15178bceeea2ee26bd266b61fd059fd08380', 'preparation_freeze': 'd104dba962421ed7785cedafa9ca8bdbb94b686123da9b327684b775e72a8d16'}, 'implementation_sha256s': {'evaluate_kxbtcd_candidate_e_entry_model_v1_development.py': '273a67bdcb8a643129fefb0d2c55914b5277c29a22625c80263ffbcba5978a8a', 'src/kxbtcd_candidate_e_entry_model_v1.py': 'ce54846f85f3d338bc0f3aadd64d8cc8b9828c0c2ac2b5454f97771ec1a89ee1', 'src/kxbtcd_candidate_e_entry_model_v1_development.py': 'e794eafbaff43a01d669f8e294e7f22ff1788fc699f14c316579a8672900c4c3'}, 'output_sha256s': {'evaluation': '2f32edeef294a6769c9d49a456c493771a76ce5aebefafc1bc11d375765b3365', 'lambda_scores': '54cf07059498683895fba674f1ee94163e9cea3f4a597822df7e31093d253f51', 'receipt': '14c75f8f0ccbef081e841fd75e6adab500b459e1fcdcee3d002c328c1bf11523'}}, 'interpretation': {'development_selection_only': True, 'eligible_to_open_c1_c2_validation': True, 'validation_gate_evaluated': False, 'model2_generalization_pass_claim': False, 'profitability_claim': False, 'notes': ['H2 selected-lambda log loss improved versus Candidate E.', 'H3 selected-lambda log loss worsened slightly versus Candidate E.', 'Pooled H2+H3 development log loss improved only slightly.', 'C1+C2 remains the predeclared five-condition validation gate.']}, 'safety': {'c1_c2_opened_for_model2': False, 'c3_opened_for_model2': False, 'protected_reserve_accessed': False, 'strategy_v1_pnl_calculated': False, 'execution_enabled': False}, 'development_freeze_fingerprint': 'a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e'}

def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()

def canonical_fingerprint(value: dict[str, Any]) -> str:
    copy = dict(value)
    copy.pop("development_freeze_fingerprint", None)
    payload = json.dumps(copy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--lambda-scores", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()

    if git("rev-parse", "HEAD") != EXPECTED_HEAD:
        raise RuntimeError(f"expected HEAD {EXPECTED_HEAD}; found {git('rev-parse', 'HEAD')}")
    if OUTPUT.exists():
        raise RuntimeError(f"freeze output already exists: {OUTPUT}")

    evaluation_path = Path(args.evaluation)
    lambda_path = Path(args.lambda_scores)
    receipt_path = Path(args.receipt)
    for path in (evaluation_path, lambda_path, receipt_path):
        if not path.is_file():
            raise RuntimeError(f"required development artifact missing: {path}")

    if sha256_file(evaluation_path) != EXPECTED_EVALUATION_SHA256:
        raise RuntimeError("development evaluation SHA-256 mismatch")
    if sha256_file(lambda_path) != EXPECTED_LAMBDA_SHA256:
        raise RuntimeError("development lambda-score SHA-256 mismatch")
    if sha256_file(receipt_path) != EXPECTED_RECEIPT_SHA256:
        raise RuntimeError("development receipt SHA-256 mismatch")

    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("evaluation_fingerprint") != EXPECTED_EVALUATION_FINGERPRINT:
        raise RuntimeError("development receipt evaluation fingerprint mismatch")
    if evaluation.get("selected_lambda") != 0.01 or receipt.get("selected_lambda") != 0.01:
        raise RuntimeError("selected lambda is not the accepted 0.01")
    if evaluation.get("full_development_fit") != EXPECTED_FREEZE["full_development_fit"]:
        raise RuntimeError("full development fit differs from accepted freeze")
    if evaluation.get("lambda_scores") != EXPECTED_FREEZE["selection"]["lambda_scores"]:
        raise RuntimeError("lambda scores differ from accepted freeze")
    if evaluation.get("selected_rolling_origin_diagnostics") != EXPECTED_FREEZE["rolling_origin_diagnostics"]:
        raise RuntimeError("rolling-origin diagnostics differ from accepted freeze")
    if receipt.get("source_sha256s") != EXPECTED_FREEZE["provenance"]["source_sha256s"]:
        raise RuntimeError("source hashes differ from accepted freeze")
    if receipt.get("implementation_sha256s") != EXPECTED_FREEZE["provenance"]["implementation_sha256s"]:
        raise RuntimeError("implementation hashes differ from accepted freeze")
    output_hashes = dict(receipt.get("output_sha256s", {}))
    if output_hashes != {
        "evaluation": EXPECTED_EVALUATION_SHA256,
        "lambda_scores": EXPECTED_LAMBDA_SHA256,
    }:
        raise RuntimeError("receipt output hashes differ from accepted development outputs")
    if receipt.get("safety") != EXPECTED_FREEZE["safety"]:
        raise RuntimeError("development safety flags differ from accepted freeze")
    if canonical_fingerprint(EXPECTED_FREEZE) != EXPECTED_FREEZE_FINGERPRINT:
        raise RuntimeError("embedded development freeze fingerprint mismatch")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(EXPECTED_FREEZE, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print("Checkpoint 21M development-result freeze: WRITTEN")
    print(f"selected_lambda={EXPECTED_FREEZE['selection']['selected_lambda']}")
    print(f"development_freeze_fingerprint={EXPECTED_FREEZE_FINGERPRINT}")
    print("eligible_to_open_c1_c2_validation=true")
    print("validation_gate_evaluated=false")
    print("model2_generalization_pass_claim=false")
    print("profitability_claim=false")
    print("c1_c2_opened_for_model2=false")
    print("c3_opened_for_model2=false")
    print("protected_reserve_accessed=false")
    print("strategy_v1_pnl_calculated=false")
    print("execution_enabled=false")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
