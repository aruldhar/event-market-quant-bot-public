"""Checkpoint 21N-U-B recovered continuous Coinbase source binding.

This module validates an already-collected 216-row Coinbase artifact after the
original collection run suffered a post-collection Windows/OneDrive manifest
finalization failure. It performs no network requests and does not run the
continuous Predexon strategy path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from src.kxbtcd_candidate_e_continuous_btc_materialization import load_materialization
from src.kxbtcd_candidate_e_continuous_convergence_reentry_v1_simulator_freeze import (
    validate_freeze,
)
from src.kxbtcd_candidate_e_july10_outcome_blind_binding import (
    EXPECTED_PAID_TICKS_SHA256,
    EXPECTED_REPLAY_SUMMARY_SHA256,
    sha256_file,
)

DEFAULT_BINDING_PATH = Path(
    "configs/kxbtcd_candidate_e_continuous_july10_source_binding.json"
)
EXPECTED_SCHEMA = "kxbtcd_candidate_e_continuous_july10_source_binding.v1"
EXPECTED_BINDING_FINGERPRINT = "8cf8ead70da5f56def1a0d67619b2cda75316e6345383e8ebdcf79f9c4cf62b7"
EXPECTED_IMPLEMENTATION_FINGERPRINT = "cf93bbdd7704ae46954feba8ce73e15a734f117a1791837d87a130e50a15764f"
EXPECTED_BTC_SHA256 = "ecc83bc5a95c65d05063e06df6d5c9aab04895577c3ef5d8ad1cc99ab62f7d1d"
EXPECTED_BTC_RELATIVE_PATH = Path("data/analysis/predexon_credit_efficiency/july10_candidate_e_continuous_coinbase_1m.csv")
EXPECTED_PARENT_CHECKPOINT = "c0045bb23b056e476eb6dc39f69f13e771880b4d"
EXPECTED_FAILED_RUN_ID = "collect_kxbtcd_candidate_e_continuous_btc_materialization_20260902T053628200857Z_f7b9153a"


class ContinuousSourceBindingError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise ContinuousSourceBindingError(message)


def canonical_fingerprint(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("source_binding_fingerprint", None)
    raw = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def binding_definition() -> dict[str, Any]:
    return {'schema_version': 'kxbtcd_candidate_e_continuous_july10_source_binding.v1', 'checkpoint_id': '21N-U-B', 'strategy_id': 'kxbtcd_candidate_e_continuous_convergence_reentry_v1', 'parent_checkpoint': {'checkpoint_id': '21N-U-A1', 'checkpoint_commit': 'c0045bb23b056e476eb6dc39f69f13e771880b4d'}, 'implementation_fingerprint': 'cf93bbdd7704ae46954feba8ce73e15a734f117a1791837d87a130e50a15764f', 'continuous_btc_materialization': {'source_id': 'coinbase.exchange.public_rest.product_candles.btc_usd.1m.v1', 'relative_path': 'data/analysis/predexon_credit_efficiency/july10_candidate_e_continuous_coinbase_1m.csv', 'sha256': 'ecc83bc5a95c65d05063e06df6d5c9aab04895577c3ef5d8ad1cc99ab62f7d1d', 'row_count': 216, 'event_count': 4, 'rows_per_event': 54, 'collection_run_id': 'collect_kxbtcd_candidate_e_continuous_btc_materialization_20260902T053628200857Z_f7b9153a', 'collection_manifest_relative_path': 'data/manifests/2026/09/02/collect_kxbtcd_candidate_e_continuous_btc_materialization_20260902T053628200857Z_f7b9153a.json', 'collection_manifest_status': 'failed', 'collection_manifest_failure_classification': 'POST_COLLECTION_MANIFEST_FINALIZATION_INFRASTRUCTURE_FAILURE', 'collection_manifest_failure_type': 'RunManifestError', 'collection_manifest_failure_detail': 'Windows WinError 5 access denied during atomic temp-file os.replace into manifest path', 'runtime_observed_api_success_count': 4, 'runtime_observed_collector_completed': True, 'runtime_observed_row_count': 216, 'runtime_observed_sha256': 'ecc83bc5a95c65d05063e06df6d5c9aab04895577c3ef5d8ad1cc99ab62f7d1d'}, 'paid_predexon_tick_shard_sha256': '43e9c5d99fb4001b866ae3e60021c8c10123dc1fb6248df96084446face68509', 'full_ladder_replay_summary_sha256': 'b37ba7132baf086887e4b33e7c11e9de59decc5f0b387d7e6e5352a2570ebb48', 'recovery_policy': {'coinbase_recollection_performed': False, 'failed_manifest_rewritten_as_completed': False, 'derived_artifact_reused': True, 'derived_artifact_must_hash_match': True, 'derived_artifact_must_load_and_validate_216_rows': True, 'reason': 'collector completed all four public Coinbase requests and wrote the exact 216-row derived artifact before manifest atomic replacement failed'}, 'safety': {'outcomes_accessed': False, 'strategy_pnl_calculated': False, 'candidate_e_refit': False, 'continuous_predexon_strategy_paths_run': False, 'orders_placed': 0, 'predexon_paid_purchases': 0, 'coinbase_recollection_requests': 0}, 'source_binding_fingerprint': '8cf8ead70da5f56def1a0d67619b2cda75316e6345383e8ebdcf79f9c4cf62b7'}


def validate_binding(
    repo_root: str | Path = ".",
    payload: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    repo = Path(repo_root)
    if payload is None:
        path = repo / DEFAULT_BINDING_PATH
        if not path.is_file():
            _fail(f"source binding missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        _fail("source-binding schema changed")
    if payload.get("source_binding_fingerprint") != EXPECTED_BINDING_FINGERPRINT:
        _fail("source-binding fingerprint field changed")
    if canonical_fingerprint(payload) != EXPECTED_BINDING_FINGERPRINT:
        _fail("source-binding canonical fingerprint changed")
    if dict(payload) != binding_definition():
        _fail("source-binding content differs from exact frozen definition")

    if payload.get("implementation_fingerprint") != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        _fail("continuous implementation fingerprint mismatch")
    freeze = validate_freeze(repo)
    if freeze.get("implementation_fingerprint") != EXPECTED_IMPLEMENTATION_FINGERPRINT:
        _fail("installed 21N-U-A implementation freeze changed")

    parent = payload.get("parent_checkpoint")
    if not isinstance(parent, Mapping) or parent.get("checkpoint_commit") != EXPECTED_PARENT_CHECKPOINT:
        _fail("source-binding parent checkpoint changed")

    btc = payload.get("continuous_btc_materialization")
    if not isinstance(btc, Mapping):
        _fail("continuous BTC block missing")
    if btc.get("relative_path") != EXPECTED_BTC_RELATIVE_PATH.as_posix():
        _fail("continuous BTC relative path changed")
    if btc.get("sha256") != EXPECTED_BTC_SHA256:
        _fail("continuous BTC expected SHA changed")
    if btc.get("row_count") != 216 or btc.get("event_count") != 4:
        _fail("continuous BTC frozen counts changed")
    if btc.get("collection_run_id") != EXPECTED_FAILED_RUN_ID:
        _fail("recovery collection run ID changed")
    if btc.get("collection_manifest_status") != "failed":
        _fail("failed source manifest must remain honestly classified failed")
    if btc.get("runtime_observed_collector_completed") is not True:
        _fail("runtime completion evidence missing")
    if btc.get("runtime_observed_row_count") != 216:
        _fail("runtime row count changed")
    if btc.get("runtime_observed_sha256") != EXPECTED_BTC_SHA256:
        _fail("runtime observed SHA changed")

    btc_path = repo / EXPECTED_BTC_RELATIVE_PATH
    if not btc_path.is_file():
        _fail(f"continuous BTC artifact missing: {btc_path}")
    observed_sha = sha256_file(btc_path)
    if observed_sha != EXPECTED_BTC_SHA256:
        _fail(f"continuous BTC SHA mismatch: {observed_sha}")

    rows = load_materialization(btc_path)
    if len(rows) != 216:
        _fail("continuous BTC materialization did not validate to 216 rows")
    if len({row.event_ticker for row in rows}) != 4:
        _fail("continuous BTC materialization event count is not 4")

    if payload.get("paid_predexon_tick_shard_sha256") != EXPECTED_PAID_TICKS_SHA256:
        _fail("frozen paid Predexon source hash changed")
    if payload.get("full_ladder_replay_summary_sha256") != EXPECTED_REPLAY_SUMMARY_SHA256:
        _fail("frozen replay summary hash changed")

    recovery = payload.get("recovery_policy")
    if not isinstance(recovery, Mapping):
        _fail("recovery policy missing")
    if recovery.get("coinbase_recollection_performed") is not False:
        _fail("recovery must not claim Coinbase recollection")
    if recovery.get("failed_manifest_rewritten_as_completed") is not False:
        _fail("failed manifest must not be rewritten as completed")
    if recovery.get("derived_artifact_reused") is not True:
        _fail("recovery must reuse the already-written source artifact")

    safety = payload.get("safety")
    if not isinstance(safety, Mapping):
        _fail("safety block missing")
    required = {
        "outcomes_accessed": False,
        "strategy_pnl_calculated": False,
        "candidate_e_refit": False,
        "continuous_predexon_strategy_paths_run": False,
        "orders_placed": 0,
        "predexon_paid_purchases": 0,
        "coinbase_recollection_requests": 0,
    }
    for key, expected in required.items():
        if safety.get(key) != expected:
            _fail(f"safety invariant changed: {key}")

    return payload
