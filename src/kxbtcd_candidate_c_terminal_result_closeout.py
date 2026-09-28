"""Checkpoint-17 terminal-result validation and canonical closeout helpers.

This module is post-evaluation bookkeeping only. It performs no network access,
model fitting, tuning, recalibration, prediction changes, or execution.

It validates the completed terminal manifest against the frozen Candidate-C
identities and the predeclared FAIL gate, verifies the durable attempt receipt,
and supplies idempotent documentation text for the permanent project record.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

CANDIDATE_ID = "kxbtcd_market_spread_interaction_logistic.v1"
FROZEN_DATASET_FINGERPRINT = (
    "d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a"
)
FROZEN_SPLIT_FINGERPRINT = (
    "28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503"
)
FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT = (
    "d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3"
)
FROZEN_FINAL_MODEL_FINGERPRINT = (
    "13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f"
)
FROZEN_TERMINAL_EVALUATION_FINGERPRINT = (
    "bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa"
)
FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT = (
    "79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33"
)
FAILED_TERMINAL_RUN_ID = (
    "collect_kxbtcd_candidate_c_locked_test_20260815T224506878886Z_31832daa"
)
EXPECTED_EVENTS = 64
EXPECTED_ROWS = 1014
EXPECTED_MARKET_LABELS = 304
EXPECTED_RECOVERED_LABELS = 9
EXPECTED_NEW_LABELS = 295
EXPECTED_LIVE_REQUESTS = 295
EXPECTED_HISTORICAL_FALLBACK_REQUESTS = 103

EXPECTED_RAW_LOG_LOSS = "0.052191564366640519"
EXPECTED_CANDIDATE_LOG_LOSS = "0.068502780828836138"
EXPECTED_DELTA_LOG_LOSS = "-0.016311216462195618"
EXPECTED_RAW_BRIER = "0.014139546080841911"
EXPECTED_CANDIDATE_BRIER = "0.014602932515903819"

DEFAULT_ATTEMPT_PATH = Path(
    "data/analysis/kxbtcd_candidate_c_terminal_evaluation/terminal_test_attempt.json"
)

TERMINAL_SUMMARY_FIELDS = (
    "schema_version",
    "candidate_id",
    "terminal_evaluation_fingerprint",
    "full_development_freeze_fingerprint",
    "final_model_fingerprint",
    "dataset_fingerprint",
    "split_fingerprint",
    "locked_test_event_count",
    "locked_test_row_count",
    "locked_test_market_label_count",
    "raw_midpoint_event_weighted_log_loss",
    "candidate_c_event_weighted_log_loss",
    "delta_log_loss_raw_minus_candidate_c",
    "raw_midpoint_event_weighted_brier",
    "candidate_c_event_weighted_brier",
    "delta_brier_raw_minus_candidate_c",
    "primary_rule",
    "tie_rule",
    "terminal_gate_passed",
    "locked_test_permanently_exposed",
    "model_refit_performed",
    "model_retuned",
    "model_recalibrated",
    "execution_enabled",
    "orders_placed",
)

DOC_PATHS = (
    Path("docs/PROJECT_STATE.md"),
    Path("docs/AI_HANDOFF.md"),
    Path("docs/DECISIONS.md"),
    Path("docs/EXPERIMENT_LOG.md"),
    Path("docs/BACKLOG.md"),
    Path("docs/KXBTCD_CANDIDATE_C_TERMINAL_LOCKED_TEST_EVALUATION.md"),
)

MARKER = "<!-- CHECKPOINT17_TERMINAL_RESULT_20260815 -->"


class TerminalResultCloseoutError(RuntimeError):
    """Raised when the completed terminal result does not match frozen invariants."""


@dataclass(frozen=True)
class ValidatedTerminalResult:
    manifest_path: Path
    run_id: str
    terminal_result_fingerprint: str
    raw_log_loss: str
    candidate_log_loss: str
    delta_log_loss: str
    raw_brier: str
    candidate_brier: str
    delta_brier: str
    gate_passed: bool
    recovered_labels: int
    new_labels: int
    live_requests: int
    historical_fallback_requests: int


def _error(message: str) -> None:
    raise TerminalResultCloseoutError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TerminalResultCloseoutError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        _error(f"expected JSON object at {path}")
    return value


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _as_false(value: Any, name: str) -> None:
    if value is not False:
        _error(f"{name} must be false")


def _as_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        _error(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise TerminalResultCloseoutError(f"{name} must be an integer") from exc
    return parsed


def _summary_from_manifest_result(result: Mapping[str, Any]) -> dict[str, str]:
    missing = [field for field in TERMINAL_SUMMARY_FIELDS if field not in result]
    if missing:
        _error(f"completed manifest result is missing terminal summary fields: {missing}")
    summary: dict[str, str] = {}
    for field in TERMINAL_SUMMARY_FIELDS:
        value = result[field]
        if field in {
            "model_refit_performed",
            "model_retuned",
            "model_recalibrated",
            "execution_enabled",
        }:
            if value is False:
                summary[field] = "false"
            elif value == "false":
                summary[field] = "false"
            else:
                _error(f"{field} must remain false")
        elif field == "orders_placed":
            if _as_int(value, field) != 0:
                _error("orders_placed must remain 0")
            summary[field] = "0"
        else:
            summary[field] = str(value)
    return summary


def validate_terminal_result(
    manifest_path: str | Path,
    *,
    repository_root: str | Path = ".",
) -> ValidatedTerminalResult:
    repo = Path(repository_root).resolve()
    manifest = _load_json(Path(manifest_path).resolve())

    if manifest.get("status") != "completed":
        _error(f"terminal manifest must be completed, got {manifest.get('status')!r}")
    collector = manifest.get("collector")
    if not isinstance(collector, Mapping) or collector.get("name") != (
        "collect_kxbtcd_candidate_c_locked_test"
    ):
        _error("unexpected terminal collector identity")

    run_id = str(manifest.get("run_id") or "")
    if not run_id.startswith("collect_kxbtcd_candidate_c_locked_test_"):
        _error("unexpected terminal run_id")

    arguments = manifest.get("arguments")
    result = manifest.get("result")
    if not isinstance(arguments, Mapping) or not isinstance(result, Mapping):
        _error("terminal manifest must contain arguments and result objects")

    expected_args = {
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "terminal_evaluation_fingerprint": FROZEN_TERMINAL_EVALUATION_FINGERPRINT,
        "transport_amendment_fingerprint": FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT,
        "transport_repair_mode": True,
        "partition_scope": "locked_test_only",
        "primary_metric": "event_weighted_log_loss",
        "tie_rule": "fail",
    }
    for key, expected in expected_args.items():
        if arguments.get(key) != expected:
            _error(f"terminal manifest argument {key} mismatch")

    resume_source = str(arguments.get("resume_source_manifest") or "")
    if FAILED_TERMINAL_RUN_ID not in resume_source:
        _error("terminal result is not bound to the original failed exposure manifest")

    expected_result_identity = {
        "candidate_id": CANDIDATE_ID,
        "dataset_fingerprint": FROZEN_DATASET_FINGERPRINT,
        "split_fingerprint": FROZEN_SPLIT_FINGERPRINT,
        "full_development_freeze_fingerprint": FROZEN_FULL_DEVELOPMENT_FREEZE_FINGERPRINT,
        "final_model_fingerprint": FROZEN_FINAL_MODEL_FINGERPRINT,
        "terminal_evaluation_fingerprint": FROZEN_TERMINAL_EVALUATION_FINGERPRINT,
        "transport_amendment_fingerprint": FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT,
    }
    for key, expected in expected_result_identity.items():
        if str(result.get(key)) != expected:
            _error(f"terminal result {key} mismatch")

    exact_counts = {
        "locked_test_event_count": EXPECTED_EVENTS,
        "locked_test_row_count": EXPECTED_ROWS,
        "locked_test_market_label_count": EXPECTED_MARKET_LABELS,
        "resume_recovered_outcomes": EXPECTED_RECOVERED_LABELS,
        "new_market_labels": EXPECTED_NEW_LABELS,
        "live_market_requests": EXPECTED_LIVE_REQUESTS,
        "historical_fallback_requests": EXPECTED_HISTORICAL_FALLBACK_REQUESTS,
    }
    for key, expected in exact_counts.items():
        if _as_int(result.get(key), key) != expected:
            _error(f"terminal result {key} mismatch")

    exact_metrics = {
        "raw_midpoint_event_weighted_log_loss": EXPECTED_RAW_LOG_LOSS,
        "candidate_c_event_weighted_log_loss": EXPECTED_CANDIDATE_LOG_LOSS,
        "delta_log_loss_raw_minus_candidate_c": EXPECTED_DELTA_LOG_LOSS,
        "raw_midpoint_event_weighted_brier": EXPECTED_RAW_BRIER,
        "candidate_c_event_weighted_brier": EXPECTED_CANDIDATE_BRIER,
    }
    for key, expected in exact_metrics.items():
        if str(result.get(key)) != expected:
            _error(f"terminal result {key} mismatch")

    raw_ll = float(result["raw_midpoint_event_weighted_log_loss"])
    candidate_ll = float(result["candidate_c_event_weighted_log_loss"])
    delta_ll = float(result["delta_log_loss_raw_minus_candidate_c"])
    raw_brier = float(result["raw_midpoint_event_weighted_brier"])
    candidate_brier = float(result["candidate_c_event_weighted_brier"])
    delta_brier = float(result["delta_brier_raw_minus_candidate_c"])
    if not all(
        math.isfinite(value)
        for value in (raw_ll, candidate_ll, delta_ll, raw_brier, candidate_brier, delta_brier)
    ):
        _error("terminal metrics must be finite")
    if not candidate_ll > raw_ll:
        _error("terminal FAIL record requires Candidate-C log loss to exceed raw midpoint")
    if not delta_ll < 0.0:
        _error("raw-minus-Candidate-C log-loss delta must be negative")
    if not candidate_brier > raw_brier:
        _error("Candidate-C Brier must match the observed worse terminal result")
    if str(result.get("terminal_gate_passed")).lower() != "false":
        _error("terminal primary gate must be recorded as FAIL")
    if str(result.get("tie_rule")) != "fail":
        _error("tie rule changed")
    if str(result.get("locked_test_permanently_exposed")).lower() != "true":
        _error("locked test must be permanently exposed")

    for name in (
        "authentication_used",
        "model_refit_performed",
        "model_retuned",
        "model_recalibrated",
        "execution_enabled",
    ):
        _as_false(result.get(name), name)
    if _as_int(result.get("orders_placed"), "orders_placed") != 0:
        _error("orders_placed must be 0")

    summary = _summary_from_manifest_result(result)
    computed_result_fp = _canonical_sha256(summary)
    stored_result_fp = str(result.get("terminal_result_fingerprint") or "")
    if not stored_result_fp or stored_result_fp != computed_result_fp:
        _error("terminal result fingerprint mismatch")

    attempt_path = repo / DEFAULT_ATTEMPT_PATH
    attempt = _load_json(attempt_path)
    if attempt.get("status") != "terminal_evaluation_completed":
        _error("terminal attempt receipt is not completed")
    if attempt.get("locked_test_permanently_exposed") is not True:
        _error("terminal attempt receipt must mark the test permanently exposed")
    if attempt.get("terminal_evaluation_fingerprint") != FROZEN_TERMINAL_EVALUATION_FINGERPRINT:
        _error("terminal attempt receipt procedure fingerprint mismatch")
    if attempt.get("final_model_fingerprint") != FROZEN_FINAL_MODEL_FINGERPRINT:
        _error("terminal attempt receipt model fingerprint mismatch")
    if attempt.get("result_fingerprint") != stored_result_fp:
        _error("terminal attempt receipt result fingerprint mismatch")
    latest_manifest = str(attempt.get("latest_manifest") or "").replace("\\", "/")
    if run_id not in latest_manifest:
        _error("terminal attempt receipt does not point to the completed resume manifest")

    return ValidatedTerminalResult(
        manifest_path=Path(manifest_path).resolve(),
        run_id=run_id,
        terminal_result_fingerprint=stored_result_fp,
        raw_log_loss=str(result["raw_midpoint_event_weighted_log_loss"]),
        candidate_log_loss=str(result["candidate_c_event_weighted_log_loss"]),
        delta_log_loss=str(result["delta_log_loss_raw_minus_candidate_c"]),
        raw_brier=str(result["raw_midpoint_event_weighted_brier"]),
        candidate_brier=str(result["candidate_c_event_weighted_brier"]),
        delta_brier=str(result["delta_brier_raw_minus_candidate_c"]),
        gate_passed=False,
        recovered_labels=_as_int(result["resume_recovered_outcomes"], "resume_recovered_outcomes"),
        new_labels=_as_int(result["new_market_labels"], "new_market_labels"),
        live_requests=_as_int(result["live_market_requests"], "live_market_requests"),
        historical_fallback_requests=_as_int(
            result["historical_fallback_requests"], "historical_fallback_requests"
        ),
    )


def documentation_sections(result: ValidatedTerminalResult) -> dict[Path, str]:
    common = f"""\
{MARKER}
## Checkpoint 17 terminal locked-test result — 2026-08-15

Checkpoint 17 is complete. The frozen Candidate-C terminal evaluation **FAILED**
the predeclared primary gate.

- Completed terminal run: `{result.run_id}`
- Terminal evaluation fingerprint: `{FROZEN_TERMINAL_EVALUATION_FINGERPRINT}`
- Transport amendment fingerprint: `{FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT}`
- Final Candidate-C model fingerprint: `{FROZEN_FINAL_MODEL_FINGERPRINT}`
- Locked test: {EXPECTED_EVENTS} events / {EXPECTED_ROWS} rows / {EXPECTED_MARKET_LABELS} market labels
- Raw midpoint event-weighted log loss: `{result.raw_log_loss}`
- Candidate-C event-weighted log loss: `{result.candidate_log_loss}`
- Raw-minus-Candidate-C log-loss delta: `{result.delta_log_loss}`
- Raw midpoint event-weighted Brier: `{result.raw_brier}`
- Candidate-C event-weighted Brier: `{result.candidate_brier}`
- Primary gate: **FAIL**
- Tie rule: fail
- Locked-test set permanently exposed: yes
- Model refit / retune / recalibration: no / no / no
- Execution enabled: no
- Orders placed: 0

The first terminal attempt was interrupted after 9 labels because the original
collector used the historical-market endpoint for a live-tier August market.
The separately frozen transport-only amendment recovered those 9 labels and
collected the remaining 295 labels without changing model, preprocessing,
features, lambda, optimizer, scoring rows, metric definitions, primary gate,
tie rule, or test membership. The completed resume used {result.live_requests}
live-market requests and {result.historical_fallback_requests} historical
fallback requests.

**Interpretation boundary:** Candidate C does not advance under the frozen
terminal criterion. This result does not establish that no predictive signal
exists, and it does not establish profitability or execution suitability.
The 64-event terminal set is now permanently exposed and must not be used to
retune Candidate C, design a successor model, or support another untouched-test
claim.
"""

    project_state = common + """
### Next research boundary

Checkpoint 18, if started, must be designed without using the exposed 64-event
terminal block for tuning or advancement. Any successor candidate must rely on
development-only evidence and a genuinely new future holdout or other
predeclared untouched evaluation set. The project remains read-only.
"""

    ai_handoff = common + """
### Handoff requirement

Do not rerun the Checkpoint-17 terminal score. Do not change Candidate C and
rescore these 64 events. Preserve the completed manifest and terminal result
fingerprint as the permanent terminal record. The next design conversation
must begin from the fact that raw midpoint outperformed Candidate C on the
primary terminal metric.
"""

    decisions = f"""\
{MARKER}
## D-020 — Reject Candidate C at the one-time terminal locked-test gate

- Date: 2026-08-15
- Status: accepted
- Context: D-018 froze the one-time terminal procedure and D-019 allowed only a
  separately fingerprinted transport repair after the first exposure was
  interrupted. No label values were used to design that transport repair.
- Decision: Candidate C **does not advance** because its locked-test
  event-weighted log loss `{result.candidate_log_loss}` is higher than the raw
  midpoint log loss `{result.raw_log_loss}`. The frozen raw-minus-Candidate-C
  delta is `{result.delta_log_loss}`. The predeclared rule required strict
  Candidate-C improvement; therefore the terminal gate is FAIL.
- Secondary evidence: Candidate-C Brier `{result.candidate_brier}` is also
  worse than raw midpoint Brier `{result.raw_brier}`.
- Transport qualification: the score was completed by resuming the same exposed
  attempt under transport amendment
  `{FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT}`. The amendment changed retrieval
  routing only; model and scoring invariants remained frozen.
- Consequences:
  - Candidate C is rejected for terminal advancement.
  - The 64-event test block is permanently exposed.
  - No retuning, recalibration, feature changes, or successor design may use
    these 64 events as optimization evidence.
  - A later candidate requires a new predeclared untouched evaluation set.
  - No paper, demo, order, transfer, or real-money execution is authorized.
"""

    experiment = f"""\
{MARKER}
## Checkpoint 17 — Candidate-C one-time terminal locked-test evaluation

- Date: 2026-08-15
- Completed run: `{result.run_id}`
- Terminal result fingerprint: `{result.terminal_result_fingerprint}`
- Terminal procedure fingerprint: `{FROZEN_TERMINAL_EVALUATION_FINGERPRINT}`
- Transport amendment fingerprint: `{FROZEN_TRANSPORT_AMENDMENT_FINGERPRINT}`
- Model fingerprint: `{FROZEN_FINAL_MODEL_FINGERPRINT}`
- Frozen sample: {EXPECTED_EVENTS} events / {EXPECTED_ROWS} rows /
  {EXPECTED_MARKET_LABELS} labels
- Recovered labels from interrupted attempt: {result.recovered_labels}
- Newly collected labels: {result.new_labels}
- Live market requests: {result.live_requests}
- Historical fallback requests: {result.historical_fallback_requests}
- Raw midpoint log loss: `{result.raw_log_loss}`
- Candidate-C log loss: `{result.candidate_log_loss}`
- Raw-minus-Candidate-C log-loss delta: `{result.delta_log_loss}`
- Raw midpoint Brier: `{result.raw_brier}`
- Candidate-C Brier: `{result.candidate_brier}`
- Primary gate: **FAIL**
- Locked test permanently exposed: yes
- Model refit/tune/recalibration: no/no/no
- Orders: 0

Result: Candidate C failed its predeclared terminal advancement criterion.
No post-test redesign is authorized from this block.
"""

    backlog = f"""\
{MARKER}
## Checkpoint 17 closeout / Checkpoint 18 boundary

Checkpoint 17 is complete and **FAIL**. Candidate C does not advance.

Completed:
- [x] freeze Candidate-C final model and preprocessing;
- [x] freeze terminal procedure before label access;
- [x] permanently expose the 64-event locked test at first terminal access;
- [x] document the interrupted first attempt and transport-only amendment;
- [x] recover 9 prior labels and collect 295 missing labels;
- [x] score Candidate C and raw midpoint on the identical frozen 1,014 rows;
- [x] apply the strict primary log-loss gate;
- [x] record terminal gate FAIL.

Next checkpoint may:
- use development-only evidence to diagnose candidate instability;
- define a simple successor hypothesis before collecting new validation data;
- create a genuinely new predeclared future holdout if another terminal claim
  will eventually be needed.

Do not use the exposed 64-event block for tuning, recalibration, feature
selection, model selection, or a new untouched-test claim. Execution remains
out of scope.
"""

    terminal_doc = common + """
### Final disposition

Candidate C is closed as a failed terminal candidate. The raw midpoint remains
the stronger probabilistic benchmark on this frozen terminal sample. This is a
model-validation conclusion only, not an execution or profitability claim.
"""

    return {
        Path("docs/PROJECT_STATE.md"): project_state,
        Path("docs/AI_HANDOFF.md"): ai_handoff,
        Path("docs/DECISIONS.md"): decisions,
        Path("docs/EXPERIMENT_LOG.md"): experiment,
        Path("docs/BACKLOG.md"): backlog,
        Path("docs/KXBTCD_CANDIDATE_C_TERMINAL_LOCKED_TEST_EVALUATION.md"): terminal_doc,
    }


def apply_documentation(
    result: ValidatedTerminalResult,
    *,
    repository_root: str | Path = ".",
) -> tuple[Path, ...]:
    repo = Path(repository_root).resolve()
    sections = documentation_sections(result)
    updated: list[Path] = []
    for relative_path in DOC_PATHS:
        path = repo / relative_path
        try:
            current = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TerminalResultCloseoutError(f"could not read {relative_path}: {exc}") from exc
        section = sections[relative_path]
        if MARKER in current:
            continue
        newline = "" if current.endswith("\n") else "\n"
        path.write_text(current + newline + "\n" + section.rstrip() + "\n", encoding="utf-8", newline="\n")
        updated.append(relative_path)
    return tuple(updated)
