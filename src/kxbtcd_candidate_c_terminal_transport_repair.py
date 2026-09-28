"""Resume-only transport amendment for Checkpoint-17 terminal evaluation.

This module does not change Candidate C, preprocessing, features, lambda,
optimizer, locked-test membership, scoring metrics, or the predeclared gate.

It exists only because the original terminal collector assumed every settled
market was available at /historical/markets/{ticker}. Kalshi partitions recent
settled markets between live and historical tiers. The repair keeps the original
frozen request membership and identity checks, but routes each not-yet-recovered
ticker live-first with historical fallback on HTTP 404.

The original Stage-A terminal freeze and its implementation-bound files remain
untouched. This amendment is separately fingerprinted and may only be used to
resume an already interrupted, permanently exposed terminal attempt.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .kxbtcd_candidate_c_terminal_evaluation import (
    CP17_COLLECTOR_NAME,
    DEFAULT_TERMINAL_ATTEMPT_PATH,
    DEFAULT_TERMINAL_FREEZE_PATH,
    FROZEN_DATASET_FINGERPRINT,
    FROZEN_FINAL_MODEL_FINGERPRINT,
    FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
    FROZEN_PREOUTCOME_RUN_ID,
    FROZEN_SPLIT_FINGERPRINT,
    KxbtcdCandidateCTerminalEvaluationError,
    TERMINAL_OUTCOME_SCHEMA_VERSION,
    load_and_validate_terminal_evaluation_freeze,
)
from .public_census_http import PublicCensusHttpError
from .run_manifest import resolve_stored_path


TRANSPORT_AMENDMENT_SCHEMA_VERSION = (
    "kxbtcd_candidate_c_terminal_transport_amendment.v1"
)
DEFAULT_TRANSPORT_AMENDMENT_PATH = Path(
    "configs/kxbtcd_candidate_c_terminal_transport_amendment.json"
)
TRANSPORT_REPAIR_IMPLEMENTATION_FILES = (
    "src/kxbtcd_candidate_c_terminal_transport_repair.py",
    "resume_kxbtcd_candidate_c_locked_test_transport_repair.py",
)
LIVE_MARKET_PREFIX = "/markets/"
HISTORICAL_MARKET_PREFIX = "/historical/markets/"


class TerminalTransportRepairError(RuntimeError):
    """Raised when the resume-only transport amendment cannot fail closed."""


class _RawReference(Protocol):
    source: str
    session_id: str
    request_id: str


class _JsonResponse(Protocol):
    payload: dict[str, Any]
    raw_record: _RawReference


class _JsonClient(Protocol):
    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> _JsonResponse:
        ...


@dataclass(frozen=True)
class TransportRecovery:
    outcomes: tuple[dict[str, str], ...]
    manifest_chain: tuple[Path, ...]


def _error(message: str) -> None:
    raise TerminalTransportRepairError(message)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalTransportRepairError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"expected JSON object at {path}")
    return value


def _write_json_atomic(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(dict(document), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _resolve(repo: Path, path: str | Path) -> Path:
    target = Path(path)
    return target.resolve() if target.is_absolute() else (repo / target).resolve()


def _implementation_sha256s(repo: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in TRANSPORT_REPAIR_IMPLEMENTATION_FILES:
        path = repo / relative
        if not path.is_file():
            _error(f"missing transport repair implementation file {relative}")
        result[relative] = _sha256(path)
    return result


def _manifest_collector_name(manifest: Mapping[str, Any]) -> str:
    collector = manifest.get("collector")
    if not isinstance(collector, Mapping):
        _error("resume manifest missing collector object")
    name = collector.get("name")
    if not isinstance(name, str) or not name:
        _error("resume manifest missing collector name")
    return name


def _manifest_run_id(manifest: Mapping[str, Any]) -> str:
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        _error("resume manifest missing run_id")
    return run_id


def _find_outcome_journal(repo: Path, run_id: str) -> Path:
    root = repo / "data" / "derived" / "kxbtcd_candidate_c_terminal_evaluation"
    matches = tuple(
        root.rglob(f"{run_id}_kxbtcd_candidate_c_terminal_outcome_journal.csv")
    ) if root.exists() else ()
    if len(matches) != 1:
        _error(
            "expected exactly one interrupted terminal outcome journal for "
            f"{run_id}; found {len(matches)}"
        )
    return matches[0].resolve()


def _count_csv_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except OSError as exc:
        raise TerminalTransportRepairError(
            f"cannot count outcome journal rows at {path}: {exc}"
        ) from exc


def build_transport_amendment_document(
    *,
    repository_root: str | Path,
    resume_manifest: str | Path,
) -> dict[str, Any]:
    """Build the outcome-value-blind transport amendment document.

    This function reads the failed manifest and counts journal rows, but it does
    not inspect or use the outcome values in those rows.
    """

    repo = Path(repository_root).resolve()
    terminal_freeze, _, _ = load_and_validate_terminal_evaluation_freeze(
        path=DEFAULT_TERMINAL_FREEZE_PATH,
        repository_root=repo,
    )

    manifest_path = _resolve(repo, resume_manifest)
    manifest = _read_json(manifest_path)
    if _manifest_collector_name(manifest) != CP17_COLLECTOR_NAME:
        _error("resume manifest is not the CP17 terminal collector")
    if manifest.get("status") != "failed":
        _error(
            "transport amendment requires the original interrupted manifest "
            "to have status 'failed'"
        )
    arguments = manifest.get("arguments")
    if not isinstance(arguments, Mapping):
        _error("resume manifest missing arguments")
    expected_args = {
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "terminal_evaluation_fingerprint": terminal_freeze[
            "terminal_evaluation_fingerprint"
        ],
    }
    for key, expected in expected_args.items():
        if arguments.get(key) != expected:
            _error(f"resume manifest {key} mismatch")

    attempt_path = _resolve(repo, DEFAULT_TERMINAL_ATTEMPT_PATH)
    attempt = _read_json(attempt_path)
    if attempt.get("status") != "terminal_exposure_interrupted":
        _error("terminal attempt is not marked interrupted")
    if attempt.get("locked_test_permanently_exposed") is not True:
        _error("terminal attempt must remain permanently exposed")
    if attempt.get("terminal_evaluation_fingerprint") != terminal_freeze[
        "terminal_evaluation_fingerprint"
    ]:
        _error("attempt receipt terminal evaluation fingerprint mismatch")

    run_id = _manifest_run_id(manifest)
    journal_path = _find_outcome_journal(repo, run_id)
    persisted_label_count = _count_csv_rows(journal_path)
    if persisted_label_count <= 0:
        _error(
            "transport amendment expected at least one persisted label from the "
            "interrupted attempt"
        )
    if persisted_label_count >= int(terminal_freeze["locked_test_market_request_count"]):
        _error("terminal outcome set is already complete; repair is inappropriate")

    document: dict[str, Any] = {
        "schema_version": TRANSPORT_AMENDMENT_SCHEMA_VERSION,
        "candidate_id": terminal_freeze["candidate_id"],
        "terminal_evaluation_fingerprint": terminal_freeze[
            "terminal_evaluation_fingerprint"
        ],
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "full_development_freeze_fingerprint": (
            FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT
        ),
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "failed_manifest": str(manifest_path.relative_to(repo)),
        "failed_manifest_sha256": _sha256(manifest_path),
        "failed_run_id": run_id,
        "persisted_label_count_before_repair": persisted_label_count,
        "locked_test_market_request_count": int(
            terminal_freeze["locked_test_market_request_count"]
        ),
        "locked_test_event_count": int(terminal_freeze["locked_test_event_count"]),
        "locked_test_row_count": int(terminal_freeze["locked_test_row_count"]),
        "locked_test_permanently_exposed": True,
        "label_values_used_to_design_repair": False,
        "repair_scope": "transport_routing_only",
        "transport_strategy": {
            "request_membership_change_allowed": False,
            "for_each_not_yet_recovered_ticker": (
                "query /markets/{ticker}; on HTTP 404 only, retry "
                "/historical/markets/{ticker}"
            ),
            "identity_validation_unchanged": True,
            "raw_first_persistence_required": True,
            "existing_recovered_labels_are_not_re_requested": True,
            "manifest_chain_recovery_required": True,
        },
        "frozen_invariants": {
            "model_change_allowed": False,
            "feature_change_allowed": False,
            "lambda_change_allowed": False,
            "preprocessing_change_allowed": False,
            "optimizer_change_allowed": False,
            "recalibration_allowed": False,
            "metric_change_allowed": False,
            "gate_change_allowed": False,
            "tie_rule_change_allowed": False,
            "locked_test_membership_change_allowed": False,
        },
        "implementation_sha256s": _implementation_sha256s(repo),
        "orders_placed": 0,
        "execution_enabled": False,
    }
    document["transport_amendment_fingerprint"] = _canonical_sha256(document)
    return document


def validate_transport_amendment_document(
    document: Mapping[str, Any],
    *,
    repository_root: str | Path,
    resume_manifest: str | Path,
) -> None:
    repo = Path(repository_root).resolve()
    if document.get("schema_version") != TRANSPORT_AMENDMENT_SCHEMA_VERSION:
        _error("transport amendment schema mismatch")
    stored_fingerprint = document.get("transport_amendment_fingerprint")
    if not isinstance(stored_fingerprint, str) or len(stored_fingerprint) != 64:
        _error("transport amendment fingerprint missing or malformed")

    fingerprint_payload = dict(document)
    del fingerprint_payload["transport_amendment_fingerprint"]
    if _canonical_sha256(fingerprint_payload) != stored_fingerprint:
        _error("transport amendment canonical fingerprint mismatch")

    expected = build_transport_amendment_document(
        repository_root=repo,
        resume_manifest=resume_manifest,
    )
    if dict(document) != expected:
        _error(
            "stored transport amendment differs from deterministic repair derivation"
        )


def write_or_validate_transport_amendment(
    *,
    resume_manifest: str | Path,
    path: str | Path = DEFAULT_TRANSPORT_AMENDMENT_PATH,
    repository_root: str | Path = ".",
) -> tuple[Path, dict[str, Any]]:
    repo = Path(repository_root).resolve()
    target = _resolve(repo, path)
    derived = build_transport_amendment_document(
        repository_root=repo,
        resume_manifest=resume_manifest,
    )
    if target.exists():
        existing = _read_json(target)
        validate_transport_amendment_document(
            existing,
            repository_root=repo,
            resume_manifest=resume_manifest,
        )
        if existing != derived:
            _error("existing transport amendment differs; refusing overwrite")
        return target, existing
    _write_json_atomic(target, derived)
    return target, derived


class LiveFirstHistoricalFallbackClient:
    """Adapt the frozen historical-market call to Kalshi's two data tiers.

    The frozen collector still asks for /historical/markets/{ticker}. This
    adapter does not change the ticker or request membership. It first queries
    /markets/{ticker}; only an HTTP 404 causes a historical-tier retry.
    """

    def __init__(self, client: _JsonClient) -> None:
        self.client = client
        self.live_requests = 0
        self.historical_fallback_requests = 0

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> _JsonResponse:
        if not path.startswith(HISTORICAL_MARKET_PREFIX):
            return self.client.get_json(path, params=params)
        ticker = path[len(HISTORICAL_MARKET_PREFIX):]
        if not ticker or "/" in ticker:
            _error(f"invalid frozen market path {path!r}")
        live_path = f"{LIVE_MARKET_PREFIX}{ticker}"
        try:
            self.live_requests += 1
            return self.client.get_json(live_path, params=params)
        except PublicCensusHttpError as exc:
            if "HTTP 404" not in str(exc):
                raise
        self.historical_fallback_requests += 1
        return self.client.get_json(path, params=params)


def _raw_paths_for_manifest(
    *,
    manifest: Mapping[str, Any],
    repository_root: Path,
) -> tuple[Path, ...]:
    paths: set[Path] = set()
    files = manifest.get("files")
    if isinstance(files, list):
        for descriptor in files:
            if (
                not isinstance(descriptor, Mapping)
                or descriptor.get("role") != "raw_api_archive"
            ):
                continue
            stored = descriptor.get("path")
            if isinstance(stored, Mapping):
                resolved = resolve_stored_path(stored, repository_root)
                if resolved.is_file():
                    paths.add(resolved)
    sessions = manifest.get("source_sessions")
    if isinstance(sessions, list):
        for session in sessions:
            if not isinstance(session, Mapping):
                continue
            session_id = session.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                continue
            for raw_root in (
                repository_root / "data" / "raw" / "kalshi_rest",
                repository_root / "data" / "raw",
            ):
                if raw_root.exists():
                    paths.update(
                        path
                        for path in raw_root.rglob(f"{session_id}.jsonl")
                        if path.is_file()
                    )
    return tuple(sorted(paths))


def _manifest_chain(
    *,
    repository_root: Path,
    manifest_path: Path,
) -> tuple[Path, ...]:
    chain: list[Path] = []
    seen: set[Path] = set()
    current = manifest_path.resolve()
    while True:
        if current in seen:
            _error("resume manifest chain contains a cycle")
        seen.add(current)
        manifest = _read_json(current)
        if _manifest_collector_name(manifest) != CP17_COLLECTOR_NAME:
            _error("resume manifest chain contains a non-CP17 collector")
        chain.append(current)
        arguments = manifest.get("arguments")
        source = arguments.get("resume_source_manifest") if isinstance(arguments, Mapping) else ""
        if not isinstance(source, str) or not source:
            break
        candidate = Path(source)
        current = (
            candidate.resolve()
            if candidate.is_absolute()
            else (repository_root / candidate).resolve()
        )
        if not current.is_file():
            _error(f"resume source manifest not found: {current}")
    return tuple(chain)


def recover_terminal_outcomes_from_manifest_chain(
    *,
    terminal_freeze: Mapping[str, Any],
    repository_root: str | Path,
    manifest_path: str | Path,
) -> TransportRecovery:
    """Recover already-opened labels across an interrupted resume chain.

    Both live and historical market paths are recognized. Only archived 2xx
    responses with the exact frozen ticker/event identity and finalized yes/no
    result are converted to outcome rows.
    """

    repo = Path(repository_root).resolve()
    first = _resolve(repo, manifest_path)
    chain = _manifest_chain(repository_root=repo, manifest_path=first)

    plan_rows = terminal_freeze.get("request_plan")
    if not isinstance(plan_rows, list):
        _error("terminal freeze request plan missing")
    planned: dict[str, str] = {}
    for item in plan_rows:
        if not isinstance(item, Mapping):
            _error("terminal freeze request plan row malformed")
        event = item.get("event_ticker")
        market = item.get("market_ticker")
        if not isinstance(event, str) or not isinstance(market, str):
            _error("terminal freeze request plan identity malformed")
        planned[market] = event

    fingerprint = terminal_freeze.get("terminal_evaluation_fingerprint")
    if not isinstance(fingerprint, str):
        _error("terminal freeze fingerprint missing")

    recovered: dict[str, dict[str, str]] = {}
    for path in reversed(chain):
        manifest = _read_json(path)
        for raw_path in _raw_paths_for_manifest(
            manifest=manifest,
            repository_root=repo,
        ):
            with raw_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise TerminalTransportRepairError(
                            f"invalid raw JSON at {raw_path}:{line_number}"
                        ) from exc
                    if not isinstance(record, Mapping):
                        continue
                    request = record.get("request")
                    response = record.get("response")
                    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
                        continue
                    request_path = request.get("path")
                    if not isinstance(request_path, str):
                        continue
                    ticker = ""
                    if request_path.startswith(HISTORICAL_MARKET_PREFIX):
                        ticker = request_path[len(HISTORICAL_MARKET_PREFIX):]
                    elif request_path.startswith(LIVE_MARKET_PREFIX):
                        ticker = request_path[len(LIVE_MARKET_PREFIX):]
                    else:
                        continue
                    expected_event = planned.get(ticker)
                    if expected_event is None:
                        continue
                    if record.get("error") is not None:
                        continue
                    try:
                        status_code = int(response.get("status_code"))
                    except (TypeError, ValueError):
                        continue
                    if not 200 <= status_code < 300:
                        continue
                    body_text = response.get("body_text")
                    if not isinstance(body_text, str):
                        continue
                    try:
                        payload = json.loads(body_text)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, Mapping):
                        continue
                    market = payload.get("market")
                    if not isinstance(market, Mapping):
                        continue
                    if market.get("ticker") != ticker:
                        _error(f"terminal raw recovery ticker mismatch for {ticker}")
                    if market.get("event_ticker") != expected_event:
                        _error(f"terminal raw recovery event mismatch for {ticker}")
                    status = str(market.get("status") or "").lower()
                    result_text = str(market.get("result") or "").lower()
                    if status != "finalized" or result_text not in {"yes", "no"}:
                        continue
                    source = record.get("source")
                    session_id = record.get("session_id")
                    request_id = request.get("request_id")
                    if not all(
                        isinstance(value, str) and value
                        for value in (source, session_id, request_id)
                    ):
                        _error(f"terminal raw recovery lineage missing for {ticker}")
                    row = {
                        "schema_version": TERMINAL_OUTCOME_SCHEMA_VERSION,
                        "candidate_id": terminal_freeze["candidate_id"],
                        "terminal_evaluation_fingerprint": fingerprint,
                        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
                        "preoutcome_run_id": FROZEN_PREOUTCOME_RUN_ID,
                        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
                        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
                        "partition": "locked_test",
                        "event_ticker": expected_event,
                        "market_ticker": ticker,
                        "raw_source": source,
                        "raw_session_id": session_id,
                        "raw_request_id": request_id,
                        "market_status": status,
                        "result_text": result_text,
                        "outcome": "1" if result_text == "yes" else "0",
                    }
                    previous = recovered.get(ticker)
                    if previous is not None:
                        if (
                            previous["outcome"] != row["outcome"]
                            or previous["result_text"] != row["result_text"]
                        ):
                            _error(
                                f"conflicting recovered terminal outcomes for {ticker}"
                            )
                        continue
                    recovered[ticker] = row

    return TransportRecovery(
        outcomes=tuple(recovered[key] for key in sorted(recovered)),
        manifest_chain=chain,
    )
