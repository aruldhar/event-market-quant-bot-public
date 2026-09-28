# Decision Log

## D-001 — Use a private GitHub repository as the canonical project record

- Date: 2026-08-02
- Status: accepted
- Reason: code, documentation, tests, and change history must persist outside a single chat.
- Consequence: meaningful work sessions end with documentation updates and a commit.

## D-002 — Use a ChatGPT Project for ongoing discussion

- Date: 2026-08-02
- Status: accepted
- Reason: related chats and selected reference files should share project context while remaining separated by milestone.
- Consequence: long phases use separate chats and the repository handoff files.

## D-003 — Begin with read-only Kalshi BTC data

- Date: 2026-08-02
- Status: accepted
- Reason: market mechanics and data quality must be understood before authentication or execution.
- Consequence: no API keys or account access in the initial phase.

## D-004 — Collect broadly later, trade narrowly

- Date: 2026-08-02
- Status: accepted
- Reason: observing multiple markets can support comparison, but each traded strategy requires independent validation.
- Consequence: expansion does not automatically authorize trades in new assets or venues.

## D-005 — Establish the verified local setup as the baseline checkpoint

- Date: 2026-08-02
- Status: accepted
- Context: the user completed the Windows development setup and verified the current read-only scanner before beginning data-foundation changes.
- Decision: treat the Python 3.11 environment, working virtual environment, three passing unit tests, public Kalshi API access, KXBTC15M discovery, and published private GitHub repository as the reproducible setup baseline.
- Alternatives considered: continue treating setup as incomplete; begin feature work without recording a milestone.
- Reason: a named baseline makes later regressions easier to identify and gives future sessions a precise starting point.
- Consequences: subsequent material changes must preserve or intentionally replace this baseline, include tests, update the project-state files, and end with a Git checkpoint. This decision does not authorize authentication, demo trading, or production trading.
- Evidence or references: user-reported local verification on 2026-08-02 and the committed setup checkpoint.

## D-006 — Persist raw REST exchanges before transformation

- Date: 2026-08-03
- Status: accepted
- Context: the baseline client returned parsed dictionaries and retained only terminal output or transformed CSV fields. Request context, source payloads, timing, and error bodies were lost, preventing reliable replay and audit.
- Decision: archive every attempted Kalshi public REST exchange as an append-only JSON Lines record before endpoint-specific transformation. Store the original decoded body text, exact byte length and SHA-256 digest, request context, selected non-sensitive response metadata, local UTC and monotonic timing, source timestamp indexes, and structured collection errors. Stop the request path if the required raw record cannot be written.
- Alternatives considered: log only transformed CSV rows; write one JSON file per response; store only parsed payload objects; continue when archive writes fail; include request headers.
- Reason: JSON Lines provides a simple testable baseline for incremental collection without creating one file per poll. Preserving body text and a byte digest supports replay and integrity checks. Centralizing the rule at the HTTP boundary prevents inconsistent endpoint behavior. Failing closed prevents silent, unauditable data gaps.
- Consequences: current client requests create ignored runtime files under `data/raw/kalshi_rest`; storage failures cause collection failures; raw archives require later retention policy; derived CSV is not the source of truth; authenticated phases must retain the no-secret logging rule.
- Evidence or references: `src/raw_json_log.py`, `src/kalshi_public.py`, `docs/RAW_DATA_SCHEMA.md`, local tests, and live raw collection evidence.

## D-007 — Use atomic per-run manifests and offline integrity validation

- Date: 2026-08-03
- Status: accepted
- Context: raw JSONL preservation established the source-of-truth payload, but the project still lacked a durable receipt connecting one collector invocation to its arguments, code identity, artifacts, counts, and completion state. Equal raw/CSV counts also could not detect later file alteration.
- Decision: create one `collection_run_manifest.v1` JSON receipt before every CLI collection run. Record sanitized arguments, UTC lifecycle times, Git commit and tracked-worktree dirty state, environment details, raw source sessions, collector results, and final artifact hashes/counts. Update lifecycle state through atomic file replacement. Treat `running` as incomplete, `failed` as an interrupted run, and `completed` as normal process completion even when individual API requests were preserved as errors. Provide an offline command that recomputes hashes, counts, raw-envelope invariants, and CSV structure.
- Alternatives considered: infer runs from filenames; write a manifest only after successful completion; append lifecycle events to the raw API file; store hashes without a validator; mark any request error as a failed collector run.
- Reason: a start-state receipt makes crashes visible, atomic replacement avoids partial manifest JSON, and recomputation detects missing or modified artifacts. Separating collector completion from request success preserves operational truth without hiding recoverable API errors. Git dirty-state capture prevents a commit hash from falsely implying that uncommitted code was absent.
- Consequences: collectors fail if a required manifest cannot be created or finalized; runtime manifests remain outside Git; interrupted runs require explicit review; a passing validator establishes byte and baseline-structure integrity but not economic or endpoint-semantic correctness.
- Evidence or references: `src/run_manifest.py`, `src/data_integrity.py`, `src/run_validation.py`, `validate_run_manifest.py`, `docs/RUN_MANIFEST_SCHEMA.md`, tests, and live manifest validation.

## D-008 — Carry exact raw-request lineage into derived order-book rows

- Date: 2026-08-03
- Status: accepted
- Context: run manifests connected a collector invocation to raw and derived files, but equal counts could not prove which exact API response produced a specific CSV row. The client discarded the raw `request_id` before derived transformation.
- Decision: pair successfully persisted API payloads with an immutable raw-record reference containing `source`, `session_id`, and `request_id`. Preserve existing plain-dictionary interfaces for compatibility, add a lineage-aware order-book method, and write `run_id`, `raw_source`, `raw_session_id`, and `raw_request_id` into every order-book CSV row. For `record_orderbook` runs, reconcile raw and derived records by exact identifiers in both directions.
- Alternatives considered: rely on matching counts and timestamps; store only a raw line number; use mutable `client.last_request_id`; embed absolute raw file paths in every CSV row; change every existing public client method to return a new type.
- Reason: immutable provenance traveling with its payload prevents retries, future concurrency, or intervening calls from overwriting lineage state. Logical identifiers remain portable across machines. Additive client interfaces minimize regression risk. Bidirectional reconciliation detects nonexistent, duplicated, omitted, unrelated, or mismatched source records.
- Consequences: the order-book CSV schema gains four required lineage columns; `record_orderbook` manifests receive stricter semantic validation; previously generated CSVs without lineage cannot pass the new `record_orderbook` lineage validator; raw and manifest envelope versions remain unchanged because their stored structures did not change.
- Evidence or references: `src/kalshi_public.py`, `record_orderbook.py`, `src/run_validation.py`, `tests/test_raw_json_logging.py`, `tests/test_record_orderbook.py`, `tests/test_run_manifest.py`, twenty passing tests on Windows, and live reconciliation of 10 raw records to 10 derived rows with zero raw errors.

## D-009 — Separate structured runtime observability from raw source archives

- Date: 2026-08-03
- Status: accepted
- Context: raw API archives and manifests preserve source exchanges and run receipts, but terminal output did not provide a durable machine-readable account of collector lifecycle, recoverable failures, endpoint-specific validation, or required persistence failures.
- Decision: write one append-only `runtime_event.v1` JSONL stream per current collector run under `logs/runtime`. Use stable dot-separated event names, four operational severity levels, UTC and monotonic clocks, run-local sequence numbers, sanitized context, and optional exact raw-request correlation. Keep response bodies and request headers out of the operational stream. Treat runtime-event persistence as required and fail closed when it cannot be written.
- Alternatives considered: add operational events to immutable raw API records; rely only on terminal output; use Python's unstructured text logging; introduce an external logging service immediately; continue collection when event persistence fails.
- Reason: raw payloads and collector behavior have different audit purposes. A small local JSONL contract is testable, replayable, portable on Windows, and sufficient before adding infrastructure. Sequence numbers and logical identifiers provide deterministic local ordering and correlation without depending on timestamps or absolute paths.
- Consequences: current CLI collectors create `collection_run_manifest.v2` receipts containing one integrity-tracked runtime-event artifact; the validator remains backward compatible with historical v1 manifests. Endpoint structural failures are logged only after raw persistence and are terminal for the order-book recorder. Event-log write failures stop collection. The change adds observability but does not establish source freshness, settlement authority, executable fills, or profitability.
- Evidence or references: `src/runtime_events.py`, `src/kalshi_public.py`, `src/data_integrity.py`, `src/run_manifest.py`, `src/run_validation.py`, `scan_btc_markets.py`, `record_orderbook.py`, `tests/test_runtime_observability.py`, `docs/RUNTIME_OBSERVABILITY_SCHEMA.md`, 35 passing Windows tests, successful live scanner and 10-snapshot recorder manifest validation, implementation commit `0c34e0f`, and Kalshi's official `GET /markets`, `GET /markets/{ticker}`, and order-book documentation reviewed on 2026-08-03.

## D-010 — Require final documentation closeout at every meaningful checkpoint

- Date: 2026-08-03
- Status: accepted
- Context: preliminary documentation was included with implementation bundles, but live Windows validation, final commit hashes, and clean-push evidence occurred afterward. As a result, a later chat could read attached handoff files that accurately described the pre-validation state but were stale relative to the canonical Git repository.
- Decision: treat documentation closeout as a mandatory checkpoint acceptance condition. After canonical tests and live validation, update `PROJECT_STATE.md`, `AI_HANDOFF.md`, `BACKLOG.md`, and `EXPERIMENT_LOG.md`; update `DECISIONS.md` whenever an accepted decision changes; update `RISK_POLICY.md` only when authorization or gates change. Include the final documents before the checkpoint's final clean commit whenever possible. If validation necessarily occurs after an implementation commit, create a small documentation-only closeout commit before starting the next milestone chat.
- Alternatives considered: rely on preliminary implementation-bundle documentation; ask the user to edit results manually; reconstruct state from chat history in every new conversation; treat ChatGPT Project attachments as automatically synchronized with GitHub.
- Reason: the Git repository and its `docs/` files must provide a self-contained, auditable continuation record. Exact test results, live artifact evidence, accepted limitations, and next actions should not depend on one chat's history. ChatGPT Project reference files are snapshots and do not automatically update when Git changes.
- Consequences: a checkpoint is not fully handed off until the documentation matches accepted code and evidence, the documentation is committed and pushed, and the latest reference copies are made available to the next chat. The assistant writes the documentation; the user only needs to install the replacement ZIP, run the requested local commands, commit/push, and replace Project reference-file snapshots when starting a new milestone.
- Evidence or references: structured runtime observability validation on 2026-08-03, implementation commit `0c34e0f`, the subsequent need for this documentation-only closeout, and the user's explicit request that handoff files be updated at every necessary checkpoint.

## New decision template

### D-XXX — Decision title

- Date:
- Status: proposed / accepted / superseded / rejected
- Context:
- Decision:
- Alternatives considered:
- Reason:
- Consequences:
- Evidence or references:

<!-- PRESELECTION_ARCHITECTURE_DECISION_20260814 -->
## D-011 - Use a shared BTC-state layer with separate KXBTCD and KXBTCPERP heads

- Date: 2026-08-14
- Status: accepted
- Context: The project predeclared a comparison between KXBTCD and Kalshi BTC perpetuals before selecting the next BTC research branch. Read-only audits established current data access, historical coverage, fees/funding mechanics, leverage metadata, full books, paired same-window microstructure, and conservative regime/effective-sample diagnostics.
- Decision: Use one shared BTC-state data/feature layer, but keep product targets, models, calibration, economics, and decision policies separate. KXBTCD is the first modeling/validation head. KXBTCPERP is retained as a secondary read-only return/volatility/microstructure head. Do not begin with a joint multitask model or shared product loss.
- Alternatives considered:
  - KXBTCD-only: rejected because it would discard a materially tighter continuous BTC market and a useful read-only microstructure/economics benchmark.
  - KXBTCPERP-only: rejected because the product currently has only about 71 daily history units in the reachable sample, versus at least 172 KXBTCD day blocks and more than 4,000 labeled settled events in the bounded event audit; perps also add funding, margin, liquidation, and maintenance-state complexity.
  - Immediate joint/multitask model: rejected as unnecessary complexity before separate baselines prove incremental value.
- Reason: This preserves the broadest useful BTC evidence without conflating fundamentally different labels. KXBTCD provides stronger labeled regime coverage for first validation. KXBTCPERP provides tighter continuous microstructure and materially different prospective execution economics. Separate heads make failure attribution, calibration, and cost modeling testable.
- Consequences:
  - Build a minimal shared BTC-state feature contract first.
  - KXBTCD baseline must explicitly include strike and time-to-close.
  - Perp baseline must use predeclared forward horizons and include funding/basis state where applicable.
  - Report outcome/event counts and conservative time blocks; never treat adjacent hourly events or minute candles as IID.
  - Forecasting, valuation, and decision policy remain separate components.
  - No execution is authorized by this decision.
  - Sub-second lead/lag modeling remains blocked until clock-health policy is improved or an explicit offset-correction method is validated.
- Evidence or references:
  - `analysis/kxbtcd_preselection_audit/kxbtcd_audit_20260814T034948Z_summary.json`
  - `analysis/kxbtcd_open_horizon_audit/kxbtcd_open_horizons_20260814T045134Z_summary.json`
  - `analysis/kalshi_perps_market_audit/kxbtcperp_audit_20260814T033452Z_summary.json`
  - `analysis/btc_preselection_paired_capture/20260814T050145Z/paired_capture_analysis.json`
  - `analysis/btc_preselection_effective_sample_audit.json`
  - paired live capture: 60/60 two-sided cycles for the perp and selected KXBTCD targets
  - KXBTCD: 4,000-event lower bound, 172 UTC day blocks, 25 UTC week blocks
  - KXBTCPERP: 71 daily history units; complete 214-record / 213-interval eight-hour funding sequence

## D-012 - Accept KXBTCD pre-outcome materialization v3 and freeze the dataset

- Date: 2026-08-15
- Status: accepted
- Decision: Replace the old 16h-to-30m anchor grid with 55m, 50m, 45m, 40m, 35m, and 30m TTC anchors, retain the 60-second quote-staleness limit, and freeze the accepted materialization-v3 dataset and split fingerprints.
- Reason: 1,410 of 1,480 selected markets (95.27%) had an approximately 60-minute open-to-close lifecycle, making the old long-horizon anchors structurally unavailable for most markets. The v3 grid produced 6,378 available states from 8,880 attempts (71.82%) while remaining outcome-blind.
- Frozen run: collect_kxbtcd_preoutcome_dataset_20260814T202930946581Z_7e58170d
- Split fingerprint: 28801122054bbc82b06b7c038a265377685ef017f9861fb435aa40fdaa07f503
- Dataset fingerprint: d78a9956b7ba48ec2fda2998396defcd0b5a62d5f13ea01dab1b68a67c66379a
- Consequences:
  - Do not rerun or redesign this materialization using locked-test feature density.
  - Locked-test outcome labels remain unopened.
  - Candidate B must use the exact frozen dataset and split.
  - No execution, paper trading, or order placement is authorized.

## D-013 - Permit controlled adaptive research, not live self-rewriting

- Date: 2026-08-15
- Status: accepted
- Decision: Future adaptive research may use regime tagging, error analysis, automated hypothesis generation, and champion/challenger evaluation, but no model or rule may silently rewrite or promote itself from recent outcomes.
- Reason: Regime-conditioned behavior may contain useful information, but automatic mutation from small recent samples creates severe overfitting, feedback-loop, and reproducibility risk.
- Required process: observe -> tag regime -> evaluate frozen model -> propose hypothesis -> freeze candidate -> test offline -> apply predeclared acceptance gates -> explicitly version or reject.
- Any accepted change must be recorded as a new version with supporting evidence in DECISIONS.md and EXPERIMENT_LOG.md.
- Initial regime work should prefer simple, testable state variables over large indicator sets.
- Win rate alone is not an acceptance metric; proper scoring, calibration, economics, tail risk, and sample uncertainty must be considered as appropriate to the research stage.
- This decision does not modify Candidate B, the frozen CP12 dataset, or the locked-test gate.
- No execution, paper trading, demo trading, or real-money trading is authorized.

<!-- CHECKPOINT13_DECISION_20260815 -->
## D-014 - Reject Candidate B at validation and keep the locked test sealed

- Date: 2026-08-15
- Status: accepted
- Context: Checkpoint 13 attached outcomes only to the frozen train and validation partitions, fit the four predeclared Candidate-B regularization values on train, selected lambda by event-weighted validation log loss, and compared the selected model against the raw Kalshi midpoint under the frozen strict-improvement gate.
- Decision: Candidate B does not advance. The selected `lambda=0.1` model had validation event-weighted log loss `0.14556019289436192`, worse than the raw midpoint's `0.14231643239449182`. The raw-minus-Candidate-B delta was `-0.003243760499870102`, so the strict-improvement gate fails. Do not open the locked-test outcomes for Candidate B and do not refit Candidate B on train+validation.
- Alternatives considered:
  - Open the locked test despite the validation miss: rejected because it would violate the predeclared gate.
  - Use the slightly worse Brier score or other secondary diagnostics to override log loss: rejected because secondary metrics cannot override the primary gate.
  - Retune Candidate B after seeing validation results: rejected because the 56-event validation partition is now exposed and such retuning would convert the gate into post-hoc tuning.
  - Automatically authorize Candidate C: rejected because Checkpoint 13 explicitly prohibited Candidate C and D-013 requires a separately frozen candidate and acceptance process.
- Reason: The validation protocol was declared before labels were opened specifically to prevent post-hoc model promotion. Preserving that rule is more important than rescuing a model that missed the benchmark.
- Consequences:
  - Locked-test outcomes opened remain 0.
  - The 56-event validation partition is no longer untouched for future model design.
  - The 64-event locked-test partition remains sealed; its future role must be explicitly predeclared before any access.
  - Candidate-B coefficients and validation results are a completed negative experiment and must not be rewritten by later research.
  - Future regime-conditioned/adaptive work may proceed only under D-013 as a separately versioned, offline, predeclared research checkpoint.
  - No execution, paper trading, demo trading, or real-money trading is authorized.
- Evidence or references:
  - Run `collect_kxbtcd_candidate_b_train_validation_20260815T204357940542Z_8af72631`
  - `docs/KXBTCD_CANDIDATE_B_TRAIN_VALIDATION_EVALUATION.md`
  - final pre-collection regression: `631 passed, 22 subtests passed in 16.10s`
  - zero-network preflight: 822 train requests, 228 validation requests, 0 locked-test requests, 320 locked-test deny-list markets
  - selected lambda: `0.1`
  - raw validation log loss: `0.14231643239449182`
  - Candidate-B validation log loss: `0.14556019289436192`
  - locked-test outcomes opened: `0`

<!-- CHECKPOINT14_DECISION_20260815 -->
## D-015 - Freeze Candidate-C v2 as probability-dependent spread recalibration and preserve the locked test

- Date: 2026-08-15
- Status: accepted
- Context: D-014 rejected Candidate B on the predeclared validation gate. D-013 permits offline error/regime diagnostics and separately versioned future hypotheses, but prohibits silent post-hoc mutation. Checkpoint 14 analyzed only the already exposed 231 development events and kept all 64 locked-test event outcomes sealed.
- Decision: Accept the Checkpoint-14 failure-analysis interpretation and freeze future Candidate C as `kxbtcd_market_spread_interaction_logistic.v1`, contract `kxbtcd_candidate_c_predeclaration.v2`, fingerprint `d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322`. Its learned features are continuous `market_logit`, `spread`, and `market_logit_x_spread`. Do not include the earlier draft TTC interaction. Candidate C is predeclared only; it was not fit in Checkpoint 14.
- Reason: Candidate-B error was concentrated rather than broad. All six TTC-anchor slices were directionally favorable, providing no direct support for TTC as the principal failure dimension. The latest B4 block was negative only in the tightest spread bucket, while probability Ã— spread slices showed materially different signs across probability regions. A small market-logit Ã— spread interaction is therefore the simplest feature change directly supported by the exposed-development diagnostics.
- Frozen development protocol:
  - use only the 231 already exposed train+validation events;
  - derive five contiguous chronological UTC-week blocks without outcomes and fingerprint the exact map before fitting;
  - use four rolling-origin score folds;
  - fit-fold-only standardization;
  - L2 grid `0.01, 0.1, 1, 10`;
  - choose lambda by pooled OOF event-weighted log loss;
  - require strictly lower pooled OOF log loss, no-worse pooled OOF Brier, and log-loss wins in at least 3/4 score blocks to advance.
- Locked-test rule: the 64-event locked test remains outcome-sealed. It cannot be opened during Candidate-C development evaluation. A later one-time terminal test requires a passed development gate, frozen final development fit, and a separate explicit checkpoint.
- Alternatives considered:
  - retain the draft market-logit Ã— TTC interaction: rejected because every TTC slice was positive and the diagnostic evidence did not identify TTC as the failure driver;
  - use spread alone without interaction: rejected as the only Candidate-C change because probability Ã— spread cells changed sign materially, indicating that a single global spread coefficient may be insufficient;
  - hard-code diagnostic probability/spread buckets: rejected because those bins are post-hoc descriptive slices and would convert exploratory boundaries directly into learned policy;
  - add external BTC momentum/volatility features now: rejected because the frozen historical CP12 states do not contain source-aligned external BTC features;
  - open the locked test to choose among these variants: rejected as contamination.
- Consequences:
  - Checkpoint 15 may evaluate Candidate C only under the frozen v2 development contract after the week-block map is frozen outcome-blind.
  - Candidate B remains rejected under D-014; pooled exploratory improvement does not rewrite its failed validation gate.
  - Candidate C is not evidence of profitability and has not yet demonstrated out-of-fold improvement.
  - Locked-test outcomes opened remain 0.
  - No execution, paper trading, demo trading, or real-money trading is authorized.
- Evidence or references:
  - `docs/KXBTCD_CANDIDATE_B_FAILURE_ANALYSIS_AND_CANDIDATE_C_PREDECLARATION.md`
  - final diagnostic directory `data/analysis/kxbtcd_candidate_b_failure_analysis/20260815T214404Z`
  - exposed development: 231 events / 5,364 rows
  - raw-minus-Candidate-B development log-loss delta: `+0.010757837962989569`
  - Candidate-B event signs: `215/16/0`
  - B4 tight-spread `(0,0.01]` delta: approximately `-0.007979`
  - `q=[0.4,0.5)|spread=(0.02,0.05]` delta: approximately `-0.032191`
  - `q=[0.4,0.5)|spread=>0.05` delta: approximately `-0.022122`
  - final full regression before closeout: `638 passed, 22 subtests passed in 17.24s`
  - network requests: 0; locked-test outcomes opened: 0; Candidate C fits: 0; orders: 0

<!-- CHECKPOINT15_DECISION_20260815 -->
## D-016 - Accept Candidate-C development-gate pass and require a separate final-fit freeze before terminal test

- Date: 2026-08-15
- Status: accepted
- Context: D-015 froze Candidate C and its five-block rolling-origin development protocol before any Candidate-C fitting. Checkpoint 15 derived the exact week map outcome-blind, then evaluated all four frozen lambdas across the four predeclared rolling folds without accessing the 64-event locked test.
- Decision: Accept the Checkpoint-15 development-gate PASS for `kxbtcd_market_spread_interaction_logistic.v1`. Freeze the development-selected lambda at `0.01`. Candidate C is eligible for a later full-development freeze/final-fit checkpoint, but is **not** yet eligible to open or score the locked test. Candidate B remains rejected under D-014.
- Evidence:
  - Candidate-C fingerprint `d9d673299b3c764b9791d2c43c5be03b8cff18c420196c04ebba17723db5a322`;
  - week-map fingerprint `6c6527c7551be3e9aa622ad2caaaa711917e976b97160bef217116067c8dede4` derived without outcomes;
  - 184 OOF events / 4,442 rows;
  - raw versus Candidate-C pooled OOF log loss `0.14654989561790596` vs `0.076775557277925191`;
  - raw-minus-Candidate-C log-loss delta `+0.069774338339980771`;
  - raw versus Candidate-C Brier `0.035093720284958003` vs `0.019029926328616251`;
  - score-block wins `4/4`;
  - development advancement gate PASS.
- Lambda interpretation: `0.01` is the only frozen lambda that improves pooled OOF log loss versus raw. `0.1`, `1`, and `10` are worse. Do not search smaller penalties, interpolate, or alter the grid after observing these results.
- Consequences:
  - Checkpoint 16 must freeze full-development scaling and exactly one final 231-event fit under `lambda=0.01`.
  - Checkpoint 16 must keep all locked-test outcomes sealed.
  - A separate Checkpoint 17 is required for the one-time terminal locked-test evaluation.
  - Once the locked test is opened, it becomes exposed and cannot support redesign or another candidate's untouched test claim.
  - This development result does not establish profitability, executable edge, or permission for paper/demo/real execution.
- Safety evidence: 0 locked-test outcomes, 0 network requests, 0 orders, no execution; full-development final fit not performed.

<!-- CHECKPOINT16_DECISION_20260815 -->
## D-017 - Freeze the final Candidate-C development model before terminal test

- Date: 2026-08-15
- Status: accepted
- Context: D-016 accepted Candidate C's rolling-origin development-gate pass and froze `lambda=0.01`, while requiring a separate full-development preprocessing/model freeze before any terminal locked-test access.
- Decision: Accept the Checkpoint-16 full-development preprocessing freeze and exactly one final Candidate-C fit. The final inference object is now frozen under model fingerprint `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f`, with preprocessing freeze fingerprint `d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3`. Checkpoint 16 does not authorize or perform locked-test evaluation.
- Frozen scaler:
  - means: `0.053181741488340019`, `0.17633482475764356`, `0.006538779033484236`;
  - population standard deviations: `3.2168919026338747`, `0.21442166056343254`, `0.32259958139407791`.
- Frozen coefficients in order `intercept`, `market_logit_z`, `spread_z`, `market_logit_x_spread_z`:
  - `0.10194908608881083`;
  - `2.0752015786995628`;
  - `0.017616475889079299`;
  - `1.9669079012140323`.
- Fit evidence: 231 development events / 5,364 rows; selected `lambda=0.01`; convergence in 6 deterministic damped-Newton iterations; penalized development objective `0.1226739682345051`.
- Interpretation boundary: the final-fit objective is an exposed-development training quantity, not a new validation result. The Checkpoint-15 rolling-origin evidence remains the basis for advancement. Coefficient magnitudes are standardized interaction-model parameters and are not isolated causal effects.
- Alternatives considered:
  - search below `lambda=0.01`: rejected as post-result tuning and contrary to D-016;
  - change preprocessing or optimizer for the final fit: rejected because it would break the frozen Candidate-C contract;
  - add BTC momentum/volatility or other features: rejected because that would create a new candidate after the development gate;
  - score the locked test in Checkpoint 16: rejected because D-016 requires a separate explicit terminal-test checkpoint.
- Consequences:
  - A separate Checkpoint 17 may perform the one-time locked-test evaluation using only this frozen inference artifact.
  - No post-test redesign on those 64 events is permitted.
  - Once their outcomes are opened, the 64 events become exposed permanently.
  - Candidate B remains rejected under D-014.
  - No paper, demo, or real-money execution is authorized.
- Safety evidence: focused tests `15 passed`; full regression `653 passed, 22 subtests passed`; source registry PASS; final artifact validation PASS; exactly one completed final-fit attempt; locked-test outcomes opened 0; network requests 0; orders 0; execution disabled.

<!-- CHECKPOINT17_PREOUTCOME_FREEZE_20260815 -->
## D-018 - Freeze the one-time Candidate-C terminal evaluation procedure before outcome access

- Date: 2026-08-15
- Status: accepted
- Context: D-017 froze the final Candidate-C inference object and required a separate checkpoint before opening the 64-event terminal locked test.
- Decision: Freeze Checkpoint-17 terminal evaluation under procedure fingerprint `bb37e9d5f9e5eb856e971fc9cb3464d567d3d088e8eead71ff171b0a171e8daa` before any locked-test label access. The procedure also binds the exact SHA-256 hashes of the terminal Stage-B implementation files so terminal logic cannot change while reusing the same freeze. The exact request allow-list is derived from locked-test event/market identifiers only and contains 304 markets covering the frozen 64-event / 1,014-row terminal scoring block. Candidate C must remain exactly model `13013c606586f68689be20fda143314d968d918ef8e26fca2fee75987768724f` with preprocessing `d0c996311554b86f3ae234dcdce803b2bfb2c3460403a1518199c4a4c1bd8fa3`.
- Metrics: raw midpoint and Candidate C are scored on identical rows. Each event contributes equal total weight by averaging row loss within event and then averaging across 64 events. Primary metric is log loss; Brier is secondary.
- Gate: Candidate-C locked-test event-weighted log loss must be strictly lower than raw midpoint. A tie fails. Brier cannot override the primary rule.
- Exposure policy: before the first terminal request, mark the full 64-event test set permanently exposed. No fresh second terminal attempt is allowed. An interrupted run may only use the pre-frozen recovery/resume path. After exposure, the set cannot support redesign or another untouched-test claim.
- Alternatives rejected:
  - retune or recalibrate after Checkpoint 16;
  - change features, lambda, scaling, optimizer, or model form;
  - inspect locked-test feature density to redesign the procedure;
  - score additional post-hoc slices as advancement criteria;
  - run terminal outcome collection from a dirty or unsynchronized worktree;
  - treat an interrupted exposure as a new untouched test.
- Safety: Stage-A procedure freeze uses zero outcome labels, zero network requests, zero orders, and no execution.

<!-- CHECKPOINT17_TRANSPORT_AMENDMENT_20260815 -->
### D-019 — Checkpoint-17 post-exposure transport-only resume amendment
**Status:** Accepted.

The first one-time terminal attempt failed after 9 labels were
persisted because the outcome collector incorrectly assumed every settled
market belonged to `/historical/markets/{ticker}`. The observed Kalshi market
cutoff was `2026-06-16T00:00:00Z`, while the failed August ticker belonged to the
live tier.

Decision: keep the original Candidate-C model, preprocessing, request
membership, scoring procedure, primary gate, tie rule, and Stage-A terminal
freeze unchanged. Introduce only a separately fingerprinted resume-only
transport adapter (`79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`) that recovers existing raw labels and
routes each missing ticker to `/markets/{ticker}`, falling back to the
historical endpoint only on HTTP 404.

Consequence: this is an interrupted-and-resumed terminal evaluation with a
documented transport amendment, not a pristine single-run execution. The full
64-event set is permanently exposed and cannot support later redesign or a new
untouched-test claim.

<!-- CHECKPOINT17_TERMINAL_RESULT_20260815 -->
## D-020 — Reject Candidate C at the one-time terminal locked-test gate

- Date: 2026-08-15
- Status: accepted
- Context: D-018 froze the one-time terminal procedure and D-019 allowed only a
  separately fingerprinted transport repair after the first exposure was
  interrupted. No label values were used to design that transport repair.
- Decision: Candidate C **does not advance** because its locked-test
  event-weighted log loss `0.068502780828836138` is higher than the raw
  midpoint log loss `0.052191564366640519`. The frozen raw-minus-Candidate-C
  delta is `-0.016311216462195618`. The predeclared rule required strict
  Candidate-C improvement; therefore the terminal gate is FAIL.
- Secondary evidence: Candidate-C Brier `0.014602932515903819` is also
  worse than raw midpoint Brier `0.014139546080841911`.
- Transport qualification: the score was completed by resuming the same exposed
  attempt under transport amendment
  `79069ec5a1b2d3622bca026d8987d390f0abda6d8433a970ed4530eee7630c33`. The amendment changed retrieval
  routing only; model and scoring invariants remained frozen.
- Consequences:
  - Candidate C is rejected for terminal advancement.
  - The 64-event test block is permanently exposed.
  - No retuning, recalibration, feature changes, or successor design may use
    these 64 events as optimization evidence.
  - A later candidate requires a new predeclared untouched evaluation set.
  - No paper, demo, order, transfer, or real-money execution is authorized.

<!-- CHECKPOINT18A_DESIGN_20260815 -->
## Checkpoint 18A decision — development-only generalization-risk review before successor fitting

- Date: 2026-08-15
- Status: accepted
- Context: Candidate C passed its Checkpoint-15 rolling-origin development gate but failed the permanently closed Checkpoint-17 one-time terminal gate. The 64-event / 1,014-row terminal block is permanently exposed and cannot become optimization or successor-design evidence.
- Decision: perform a separate Checkpoint-18A diagnostic using only outcomes exposed before the terminal test. Read the canonical Checkpoint-15 OOF artifacts and canonical Checkpoint-13 train+validation development context. Do not load the Checkpoint-17 result artifact or any terminal row, label, feature, prediction, residual, or slice.
- Diagnostic scope: B1-B4 log-loss/Brier stability; event/week improvement concentration; leave-one-block-out sensitivity; stored-fold coefficient conversion to raw feature space; stored-fold fixed-grid prediction stability; market-sharpening behavior; feature correlation/conditioning; weekly dependence diagnostics; and outcome-blind 6/7/8-block successor-layout support.
- Model boundary: Checkpoint 18A fits no successor, searches no successor hyperparameter, and does not refit Candidate C. Reconstructing predictions from already-stored Checkpoint-15 fold coefficients is permitted.
- Protocol conclusion to test: Checkpoint-15 coefficients were chronological OOF, but Candidate C's feature hypothesis came from the same 231 exposed development events and the same pooled OOF blocks selected lambda and assessed advancement. Checkpoint 18B must therefore predeclare a stricter nested chronological protocol before any successor fit.
- Candidate boundary: raw midpoint remains the benchmark. Later successor comparison may consider only a small set of market-anchored corrections first: intercept/slope recalibration and, if supported, tightly regularized additive spread adjustment. The Candidate-C interaction is not automatically retained.
- Future test boundary: any future untouched terminal test must use genuinely new data collected after the successor design is frozen. The Checkpoint-17 block can never serve that role again.
- Safety: read-only/offline analysis only; no network request is required by the 18A diagnostic; no paper/demo/order/transfer/real-money execution is authorized.

<!-- CHECKPOINT18B_CANDIDATE_D_DESIGN_20260815 -->
## D-021 — Freeze Candidate D as calibration-only successor with a stricter development screen

- Date: 2026-08-15
- Status: accepted / pre-fit
- Candidate: `kxbtcd_market_logit_recalibration.v1`
- Predeclaration fingerprint: `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`
- Evidence: Checkpoint-18A development-only diagnostics. Candidate C's pooled development gain was broad, but late-period stability deteriorated; B4 improvement fell sharply, 7 of 11 B4 weeks had negative log-loss delta, only lambda 0.01 of the four frozen lambdas beat raw, the standalone spread slope decayed across folds, and wide-spread states produced very large corrections without an independent BTC-state feature.
- Decision: do not carry spread or the market-logit × spread interaction into the successor. Candidate D uses only 0.001-clipped market logit with two correction parameters: `logit(p_D)=market_logit+alpha+delta*market_logit`. Raw midpoint is nested at `alpha=0, delta=0`.
- Preprocessing: no feature scaling. No additional features.
- Selection complexity: no regularization, no hyperparameter grid, and no hyperparameter search.
- Fit rule: event-weighted binary log loss; equal total weight per event and equal row share within event; deterministic damped Newton with the frozen Checkpoint-18B optimizer settings; initialization at the raw benchmark.
- Development protocol: use the outcome-blind seven-block UTC-week layout and five rolling-origin score folds B2-B6, exactly 32 scored events per block and 160 scored events total.
- Advancement: all seven predeclared conditions in `docs/KXBTCD_CANDIDATE_D_PREDECLARATION.md` are required, including strict pooled log-loss improvement, Brier no worse, at least 4/5 block wins, a B6 win, positive median event delta, successful finite fits, and positive market-logit slope in every fold.
- Interpretation: this is an exposed-development stability screen, not an untouched test.
- Future test: any legitimate terminal evaluation requires genuinely new future events; Checkpoint-17 data remain prohibited.
- Safety: this decision freezes design only. Candidate-D fitting and all execution remain unauthorized until a later implementation step explicitly follows this contract.

<!-- CHECKPOINT18C_CANDIDATE_D_DEVELOPMENT_20260815 -->
## D-022 — Implement and run Candidate D only under the frozen Checkpoint-18B development contract

- Date: 2026-08-15
- Status: accepted / result pending
- Candidate: `kxbtcd_market_logit_recalibration.v1`
- Required predeclaration fingerprint: `a42e70b678fc93a4a3084581f60c5b8d7b651f21afc5d302fb78f669cbb21537`
- Decision: authorize the Checkpoint-18C exposed-development stability screen exactly as frozen in D-021. This authorizes five deterministic rolling-origin Candidate-D fits on the already-exposed 231-event development pool; it does not authorize any model-family change, feature addition, scaling, regularization, hyperparameter search, or terminal reuse.
- Chronology: validate the committed seven-block week map from the frozen pre-outcome dataset before loading development outcomes. Week-map fingerprint: `ba93f6a063c616a34437d6f9d208e39b85c993868c71ea78db8b40a70ec23dff`.
- Fit/scoring: event-equal binary log loss, raw market nested at zero correction, deterministic damped Newton, score only B2-B6, and apply every frozen advancement condition.
- Failure boundary: implementation/convergence/lineage/nonfinite failures fail closed. A statistical gate FAIL ends Candidate D's advancement under this contract; results must not be post-hoc repaired by changing the frozen specification on the same development evidence.
- Interpretation: even a PASS remains an exposed-development result. A later untouched test requires a separately frozen final model and genuinely future data.
- Safety: offline/read-only only; no terminal data, network collection, paper/demo/live execution, orders, or transfers.

<!-- CHECKPOINT18C_CANDIDATE_D_RESULT_20260815 -->
## D-023 — Reject Candidate D at the frozen Checkpoint-18C development stability gate

- Date: 2026-08-15
- Status: accepted
- Run: `20260815T234004Z`
- Evaluation-result fingerprint: `b72617517d7bbc3bc1e01ff332496efaf5ba0c64c5eb445f82574e63fa4a47ab`
- Decision: Candidate D **does not advance**. Although pooled event-weighted log loss improved by `+0.002975566899699328`, pooled Brier improved by `+0.011467623803289244`, and 149/160 scored events improved on log loss, Candidate D won only 3/5 chronological score blocks and failed latest block B6.
- Frozen failure reasons: `fewer_than_4_of_5_score_block_log_loss_wins`; `latest_B6_log_loss_not_strictly_better`.
- Block chronology: B2/B3/B4 log-loss deltas were positive; B5 was `-0.029863425409502709`; B6 was `-0.13112910239515319`.
- Model behavior: all five fitted slopes were positive and exceeded 1, so Candidate D consistently sharpened the raw market. This is descriptive only; no post-hoc slope cap or regularization change is authorized on this same screen.
- Consequence: no final Candidate-D fit and no Candidate-D prospective terminal evaluation.
- Research boundary: a later successor may use this exposed development failure as design evidence, but any advancement claim still requires a newly frozen protocol and genuinely new untouched evidence.
- Safety: no terminal data, network requests, orders, transfers, demo, paper, or real-money execution.

<!-- CHECKPOINT19A_SUCCESSOR_PROTOCOL_20260815 -->
## D-024 — Require independent BTC state and four-tier fresh evidence for the next advancing KXBTCD successor

- Date: 2026-08-15
- Status: accepted / protocol freeze
- Context: Candidate D is permanently closed as a development FAIL. The 231-event / 5,364-row development pool has influenced Candidate B, Candidate C, Candidate D, and multiple failure analyses, so it is fully exposed exploratory evidence. The 64-event / 1,014-row Checkpoint-17 terminal block is permanently exposed and prohibited from successor design, fitting, tuning, or future untouched-test claims.
- Decision: any future KXBTCD successor eligible for advancement must include at least one contemporaneous BTC-state feature from an information source independent of Kalshi's own KXBTCD market probability. Raw Kalshi midpoint remains the benchmark. A Kalshi-probability-only recalibration is not eligible as the next advancing successor.
- Evidence protocol: E0 = fully exposed exploratory evidence; E1 = genuinely new successor-design evidence; E2 = later final-parameter fitting evidence after successor freeze; E3 = genuinely prospective untouched test evidence after final-model freeze. Outcome-exposed evidence cannot be upgraded to a stronger evidentiary role.
- Initial feasibility source families: Coinbase and Kraken. Exact source IDs, alignment/staleness rules, feature formulas, cohort sizes, and advancement thresholds remain unfrozen until an outcome-blind feasibility audit is completed.
- Timing boundary: no sub-second lead/lag feature is authorized. Outcome-blind coarse lookback coverage may be audited.
- Checkpoint-19A scope: protocol/feasibility only; Candidate E formula not frozen; Candidate E fitting not authorized; outcome access not authorized.
- Safety: read-only research only; no paper, demo, order, transfer, or real-money execution.

<!-- CHECKPOINT19B_INDEPENDENT_BTC_FEASIBILITY_20260815 -->
## D-025 — Freeze the Checkpoint-19B outcome-blind independent-BTC feasibility collector before live evidence

- Date: 2026-08-15
- Status: accepted / implementation freeze
- Parent protocol fingerprint: `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`.
- Audit design fingerprint: `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`.
- Decision: run one bounded 420-second public/read-only engineering pilot using Coinbase Exchange BTC-USD level-1 book snapshots, Kraken BTC/USD Pre-Trade snapshots, and open KXBTCD market snapshots. Alternate Coinbase/Kraken request order; request KXBTCD only after both external attempts; preserve raw-first lineage and local monotonic receipt timing.
- Purpose: test source availability, auditable causal alignment, cross-source disagreement observability, and five-minute first-seen history coverage. This is engineering feasibility, not model evidence.
- Source identity boundary: the Coinbase/Kraken source IDs in the pilot are provisional engineering identifiers. D-025 does not register or freeze an E1 model-feature source, choose a source consensus, or approve source substitution.
- Timing boundary: local monotonic first-seen ordering controls causal attachment. Row age uses local monotonic first-seen time; no staleness threshold is selected. No sub-second lead/lag claim is authorized.
- Model/evidence boundary: Candidate E formula remains unfrozen; no outcome access, candidate fit, score, threshold selection, E1/E2/E3 cohort-size choice, or advancement decision is authorized.
- Follow-up: if the bounded pilot validates instrumentation, freeze a longer outcome-blind availability collection before selecting source-quality rules or any Candidate-E menu.
- Safety: no Checkpoint-17 use; no paper/demo/order/transfer/real-money execution.

<!-- CHECKPOINT19B_PILOT_RESULT_20260816 -->
## D-026 — Treat the Checkpoint-19B bounded pilot as engineering feasibility only

- Date: 2026-08-16
- Status: accepted
- Evidence: frozen 420-second run `collect_kxbtcd_independent_btc_feasibility_20260816T003652267319Z_b123b960` under audit fingerprint `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`.
- Result: 210/210 Coinbase requests, 210/210 Kraken requests, and 42/42 Kalshi snapshots succeeded; all 13,356 feasibility rows had both external sources and were structurally usable; structural exclusions were zero.
- Timing diagnostics: snapshot-level Coinbase age p50/p95/max = 0.1875/0.297/1.282 seconds; Kraken = 0.133/0.63395/0.75 seconds; Coinbase/Kraken disagreement p50/p95/max = 0.719803/1.087145/1.089605 bps.
- Decision: this is a PASS for engineering feasibility only. Do not select permanent staleness or cross-source disagreement thresholds, a consensus-price rule, E1/E2/E3 cohort sizes, or Candidate-E formula from this seven-minute pilot.
- Required next evidence: a longer outcome-blind collection with broader calendar and KXBTCD TTC coverage before those items are frozen.
- Safety: Candidate-E fitting, outcome access, Checkpoint-17 terminal reuse, paper/demo/live execution, orders, and transfers remain prohibited.

<!-- CHECKPOINT19C_EXTENDED_AVAILABILITY_20260816 -->
## D-027 — Freeze a 24-hour outcome-blind independent-BTC availability audit before E1 source/model choices

- Date: 2026-08-16
- Status: accepted / design freeze
- Parent protocol fingerprint: `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8`.
- Parent 19B audit fingerprint: `41c9601c4316fea62b8a7993d871429434282ddf8ce60ca30fd76729db4536be`.
- 19C audit design fingerprint: `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d`.
- Decision: collect one continuous 24-hour window with Coinbase/Kraken every 15 seconds and open KXBTCD every 5 minutes. Keep full protocol-valid state rows plus one-row-per-external-cycle and one-row-per-KXBTCD-snapshot diagnostics.
- Rationale: the 19B seven-minute pilot proved instrumentation but missed material TTC bands and could not characterize a full UTC day. The slower 19C cadence reduces redundant volume while retaining dense five-minute-history evidence.
- Failure semantics: raw-preserved transport/API unavailability is measured; parser/schema ambiguity, partial-ladder pagination, monotonic-time violations, and raw-persistence ambiguity fail closed.
- Evidence boundary: no source-quality threshold, consensus price, Candidate E, E1/E2/E3 size, outcome access, or advancement rule is selected here.
- Safety: Checkpoint-17, fitting, paper/demo/live execution, orders, and transfers remain prohibited.

<!-- LEARNING_GUIDE_POLICY_20260816 -->
## D-028 — Maintain a cumulative zero-prior-knowledge learning guide

- Date: 2026-08-16
- Status: accepted
- Context: the project is education-first, but the growing modeling, statistics, data-engineering, optimization, validation, and market-microstructure vocabulary is too large to retain reliably from chat explanations alone.
- Decision: add `docs/LEARNING_GUIDE.md` as a permanent cumulative educational companion. At every meaningful checkpoint, review it and add genuinely new concepts using intuition -> tiny numerical example -> equation/formal definition -> project application -> failure modes -> practice. New topics must assume no prior knowledge and define notation and jargon.
- Reason: the project should build durable ML/statistics/quantitative skills for future work and interviews, not merely produce code and experiment results. A cumulative repository document supports spaced review, notes, self-testing, and continuity across future chats.
- Consequences:
  - checkpoint closeout should update the guide when new concepts are introduced;
  - the guide's synchronization point should track the latest meaningful checkpoint it covers;
  - no guide expansion is required when a checkpoint introduces no new learning concept;
  - canonical state, evidence, authorization, and decisions remain in their dedicated documents;
  - future assistants should teach newly introduced project concepts from zero prior knowledge before assuming familiarity.
- Safety: documentation/teaching workflow only; no modeling, data-access, outcome-access, or execution authorization changes.

<!-- CHECKPOINT19C_RESULT_CLOSEOUT_20260817 -->
## D-029 — Accept 19C as extended engineering feasibility and separate source-quality dimensions

- Date: 2026-08-17
- Status: accepted
- Context: the frozen 24-hour 19C audit completed under protocol `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2a57fb1a13c01681291f8` and audit design `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d` with 5,758 external cycles, 288 KXBTCD snapshots, and 90,288 feasibility rows. Manifest integrity validation passed with 11,804 raw records, zero raw errors, 11,806 runtime events, and zero runtime errors.
- Decision: treat Coinbase and Kraken as technically viable **provisional** independent-BTC source families for the next source-quality/materialization design stage, not as frozen E1 model-feature sources yet. Treat source quality as multiple distinct dimensions rather than one availability flag: (1) request/transport availability, (2) local monotonic first-seen age relative to the modeled KXBTCD state, (3) exchange/source-event or publication freshness, (4) cross-source price disagreement, and (5) causal lookback alignment.
- Evidence: all collected Coinbase/Kraken/Kalshi requests succeeded; both external sources were available on every collected external cycle; all 90,288 feasibility rows were structurally usable; five-minute lookback row availability was 99.6478% for each source; cross-source disagreement p50/p95/max was approximately 0.727/2.753/5.348 bp; receive skew p50/p95/max was 156/234/9,687 ms; all TTC bands were observed.
- Tail interpretation: the full-day run exposed timing/disagreement tails not visible in 19B. A successful request can also return a top-book level with an older source publication timestamp, so HTTP success must not be treated as proof of source-state freshness.
- Consequence: the next checkpoint may freeze source-quality/materialization rules using outcome-blind 19B/19C evidence. It must not select thresholds from settlement outcomes. Candidate E, consensus-price construction, E1/E2/E3 cohort requirements, and the exact feature formula remain unfrozen until separately predeclared.
- Future architecture note: prospective prediction ledgers and champion/challenger retraining are a research direction under consideration and remain governed by D-013; no silent live self-rewriting or auto-promotion is accepted here.
- Safety: no outcome access, Checkpoint-17 reuse, Candidate-E fitting, paper/demo/live execution, orders, transfers, or real-money authorization changes.

<!-- CHECKPOINT19D_A_HISTORICAL_MATERIALIZATION_20260817 -->
## D-030 — Freeze an outcome-blind historical-materialization audit before final Candidate-E source rules

- Date: 2026-08-17
- Status: accepted / implementation freeze
- Parent protocol: `b6c020f76a89703f737cc2e57e0fdbafb3a13966dfc2e57fb1a13c01681291f8`.
- Parent 19C audit: `4cdb9b8f2cd5d4396d470df04e4c3f88ff1e3f91cce25cd3e57543ea97c8490d`.
- 19D-A audit fingerprint: `023ca51e1e21180b9adecd1d4b78fd4c3372f1aab3a986988c8eb4bc4806721c`.
- Context: 19C established 24-hour live collection feasibility but did not establish that historical candles reproduce live BBO or provide enough evidence to choose permanent staleness/disagreement rules. A successful HTTP request was also shown to be distinct from source-event freshness.
- Decision: before final E1 source/quality rules, run one outcome-blind historical reconstruction audit on the exact 288 canonical 19C KXBTCD state timestamps. Coinbase candidate primitive is official BTC-USD one-minute Exchange candles. Kraken candidate primitive is official BTC/USD PostTrade history with `trade_ts` and `publication_ts`. Current state uses only the last fully completed one-minute bucket; lookback uses the exact bucket five minutes earlier. Missing buckets are excluded; no interpolation or carry-forward is permitted. Coinbase candles do not expose a comparable bucket publication timestamp, so 19D-A treats completed-bucket end time as the causal boundary while explicitly leaving exact Coinbase first-publication timing unresolved.
- Live-quality correction: re-read preserved 19C Kraken raw responses and evaluate bid and ask publication ages separately. Whole-BBO conservative publication age is the maximum of the two side ages. Do not interpret the newer side's timestamp as freshness for the entire midpoint.
- Alternatives rejected: historical BBO reconstruction without an official archive; treating candles as if they were BBO; choosing Coinbase or Kraken from outcomes; learned source weights; a third-party historical provider before native-data adequacy is tested; selecting a permanent threshold directly from 19C BBO maxima.
- Consequence: 19D-A may measure coverage, timestamp tails, historical cross-source disagreement, and historical-vs-live gaps only. Final E1 source IDs/allow-list, source priority/consensus, numerical quality thresholds, evidence-cohort sizes, Candidate-E features, and advancement rules remain for 19D-B.
- Safety: Candidate E remains unfitted; outcomes remain unopened; Checkpoint-17 remains prohibited; no paper/demo/live execution, orders, cancellations, transfers, or real-money trading.

<!-- CHECKPOINT19D_A_RESULTS_20260817 -->
## D-031 — Accept 19D-A source-quality evidence; retain exact-minute/no-imputation boundary

**Status:** accepted for the 19D-A -> 19D-B research transition.

The completed 19D-A audit establishes high historical reconstructibility for
the independent BTC-state candidates without using outcomes. One Kraken target
minute had zero trades; the preserved raw response was successful HTTP 200 with
an empty trade set. The missing exact minute remains unavailable rather than
being filled from an older trade or future observation.

This decision does **not** choose Coinbase versus Kraken, does not freeze a
consensus formula, and does not select numerical freshness/disagreement
thresholds. Those choices are deferred to 19D-B and must be based only on
outcome-blind source-quality evidence.

Transport/request freshness must remain distinct from source-event freshness.
For Kraken live BBOs, whole-BBO freshness is conservatively governed by the
older side, not the newer side or request receive time.

Candidate E remains unfitted and its final formula remains unfrozen.

<!-- CHECKPOINT19D_B_SOURCE_POLICY_20260817 -->
## D-032 — Freeze Coinbase-primary / Kraken-verifier source policy for Candidate-E research

- Date: 2026-08-17
- Status: accepted
- Decision: Use Coinbase Exchange BTC-USD level-1 BBO as the deterministic live
  independent-BTC primary and Kraken BTC/USD PreTrade as a mandatory verifier.
  Do not average the venues, learn venue weights, substitute a failed source, or
  fall back to one source. Historical reconstruction uses Coinbase exact
  one-minute close plus Kraken exact-minute PostTrade with publication
  causality.
- Source-quality gates: local first-seen <=5 s per source; Coinbase source-event
  age <=10 s; conservative Kraken BBO publication age <=60 s; cross-source
  receive skew <=1 s; midpoint disagreement <=5 bp; absolute local clock offset
  <=1 s.
- Evidence gates: E1 >=168 eligible events / 7 UTC days; E2 >=168 / 7 days; E3
  >=336 / 14 days; all 24 UTC hour bins; >=90% scheduled-state source
  eligibility; >=2/3 source-eligible scheduled states per counted event.
- Reason: 19C/19D-A showed high availability and tight ordinary cross-source
  agreement, but Kraken's whole-BBO publication freshness has a heavy tail and
  Coinbase had cleaner exact-minute reconstruction. Primary+verifier preserves
  independent validation without injecting stale verifier state into the
  feature.
- Consequence: these source thresholds cannot be loosened after E1 outcomes are
  opened. Candidate E's exact formula/model remains separately unfrozen.
- Evidence: Checkpoint-19C extended availability audit and Checkpoint-19D-A
  historical materialization audit; no KXBTCD outcomes used.

<!-- CHECKPOINT19E_CANDIDATE_E_PREDECLARATION_20260817 -->
## D-033 — Freeze Candidate E as a market-offset independent-BTC successor family

- Date: 2026-08-17
- Status: accepted / pre-fit
- Predeclaration fingerprint: `9775be58f01375ca6f2b04212a63578ce5e8cf7084498e6ce9d3ae68685d59a9`
- Evidence boundary: E0 may generate hypotheses; no E1 outcome, Checkpoint-17 terminal row, or successor fit was used to select this specification.
- Decision: keep raw Kalshi midpoint as the fixed probability anchor and permit only two nested independent-BTC corrections: `d_BTC` alone, or `d_BTC + r_5m`.
- Feature units: `d_BTC = 10000*ln(S_t/K)` and `r_5m = 10000*ln(S_t/S_t-300s)`. The 10,000 factor expresses log ratios in approximately basis-point units and is frozen before outcomes.
- Source rule: prospective tier states use live Coinbase primary with mandatory Kraken verification under Checkpoint 19D-B; historical reconstruction cannot rescue missing live tier states.
- Fit rule: event-equal binary log loss, all coefficients initialized at zero, no regularization, no standardization, no tuning grid, deterministic damped Newton.
- Chronology: E1 minimum 168 eligible events / 7 UTC dates / 168h; seven contiguous balanced event blocks; score B2-B6 rolling-origin.
- Advancement: each candidate must pass the frozen raw benchmark stability gate. If both pass, the momentum model is selected only if it also passes the frozen nested complexity gate against distance-only on identical OOF rows.
- Monotonicity guard: `beta_distance > 0` in every fold.
- Safety: design freeze only; no Candidate-E fit, E1 outcome access, paper/demo/live execution, orders, cancellations, transfers, or real-money execution is authorized.

<!-- CHECKPOINT19F_HISTORICAL_EVIDENCE_AMENDMENT_20260817 -->
## D-034 — Use historical train/validation/locked-test evidence before live confirmation

- Date: 2026-08-17
- Status: accepted / pre-outcome amendment
- Decision: Before any Candidate-E fit or new Candidate-E outcome access, supersede the prospective E1/E2/E3 timing requirement with a historical-first H1/H2/H3 pipeline. H1 uses 1,500 eligible untouched events for fit and the already-frozen 19E rolling-origin candidate-selection gate; H2 uses the next 750 eligible untouched events for one-time validation; after H2 PASS the selected fixed specification is refit once on H1+H2 and frozen; H3 uses the next 750 eligible untouched events for one-time locked historical testing. Prospective live confirmation occurs only after H3 PASS.
- Evidence boundary: the modern census contains 9,738 events; 307 prior outcome-exposed event tickers are denied; 9,431 remain untouched. The amendment was selected without opening any new Candidate-E outcomes and before fitting Candidate E.
- Source realization: historical Candidate-E features use the frozen 19D-B historical Coinbase/Kraken roles with exact-minute causal construction, no imputation/substitution, and a 5 bp verifier-disagreement cap. Later live confirmation uses the separate 19D-B live BBO construction.
- Reserve rule: initial raw allocation is 3,000 events with 6,431 nominally unallocated; eligibility-based extension may occur only outcome-blind and must fail closed before fewer than 5,000 outcome-unopened events would remain.
- Reason: Candidate E has only one or two free coefficients, while prior B/C/D failures show that generalization evidence is more valuable than spending most clean history on parameter estimation. Historical train/validation/test gives faster evidence while preserving a majority of untouched modern-regime history for successor models.
- Consequence: 19A/19D-B/19E remain immutable records, but their prospective timing clauses no longer govern Candidate-E evidence after this amendment. Candidate-E formulas, scoring family, safety rules, and execution prohibition remain unchanged.
- Fingerprint: `b5b0ed3eb743a8dc6ced854098140ad27440a46382a511a131e22e94497e94fb`

<!-- CHECKPOINT19G_HISTORICAL_MATERIALIZATION_20260817 -->
## D-035 — Freeze Candidate-E historical materialization as chunked, outcome-invariant pre-outcome collection

- Date: 2026-08-17
- Status: accepted / pre-collection design
- Contract fingerprint: `cc3e3326455fce2abbf7e39bdb8858d0d4cea67415ea90ece091259780de9145`
- Decision: After this 19G engineering freeze closes, materialize Candidate-E H1/H2/H3 in Checkpoint 19H from the exact 19F untouched chronological queue using separately manifested contiguous chunks and an offline final freezer. A scored anchor is eligible only when exact historical Coinbase/Kraken current and 5m-lookback pairs pass the frozen 5 bp verifier gates and at least one structural KXBTCD quote is valid. An event needs at least 4/6 eligible anchors. Do not add an all-five-strikes-per-anchor rule; enforce five-role/six-TTC representation at the frozen score/evaluation block level instead.
- Outcome firewall: historical market API payloads may contain result/settlement fields. Preserve raw responses unchanged, then immediately project onto a frozen metadata allow-list. Forbidden source outcome fields may not affect branching, selection, derived artifacts, or fingerprints; flipping those values with identical allowed metadata must be regression-invariant.
- Reserve: canonical collection may consume at most 4,431 queue events, preserving at least 5,000 events outside Candidate-E canonical materialization. Count every canonically materialized queue event, including any extra tail of the last chunk.
- Reason: this preserves the 19F contamination boundary while making a large historical collection resumable, raw-first, and auditable. It avoids both an all-or-nothing giant request run and a new post-hoc quote-density threshold.
- Consequence: Candidate-E outcomes and fitting remain prohibited until the final pre-outcome cohort/row universe is frozen. H2/H3 stay sealed under 19F. Execution authorization does not change.

<!-- CHECKPOINT19HB_COINBASE_PRIMARY_20260817 -->
## D-036 — Candidate-E Coinbase-primary source policy

**Decision:** Make Coinbase the sole required independent BTC-state source for Candidate E. Kraken becomes optional nonblocking diagnostic evidence and cannot veto historical or later live Candidate-E state solely because of cross-venue disagreement.

**Evidence:** The first 600 outcome-unopened queue identities produced 303/600 eligible events under the original 5 bp Coinbase/Kraken veto, versus 459/600 when that veto was removed; Coinbase-only eligibility was also 459/600. Kraken availability itself was nearly complete. The amendment is therefore driven by source-coverage/architecture evidence, not model performance.

**Preserved invariants:** Candidate-E formulas and variants, raw midpoint benchmark, six TTC anchors, five structural roles, 4-of-6 event gate, 1500/750/750 partitions, chronological gates, 4431-event cap, 5000-event reserve, outcome firewall, and execution prohibition.

**Fingerprint:** `b08da00a8f66817d9e3b600ccf091c8a4fc1ee92a0bed1c821d23bc321d9faba`.

<!-- CHECKPOINT20A_H1_PROCEDURE_FREEZE_20260817 -->
## Checkpoint 20A — freeze H1-only Candidate-E outcome/evaluation path

Accepted: separate Checkpoint 20 into an outcome-blind Stage 20A procedure freeze and a later one-time Stage 20B H1 exposure/evaluation. The H1 allow-list is derived only from the frozen 19H-C H1 rows; H2/H3 event and market identities are explicit hard-deny sets. The existing 19H-C H1 block assignments are authoritative and are validated rather than regenerated. The evaluator is bound to exactly the two 19E Candidate-E variants, the frozen 7-block/5-fold rolling-origin procedure, raw advancement gate, nested complexity gate, and implementation SHA-256 hashes.

H1 evaluation procedure fingerprint: `cbbca76de2dd87edd6c6bc4f21ae1005fbd1402a3bb85374e7699c8fb5fb7d14`.

This decision opens no outcomes and authorizes no execution.

<!-- CHECKPOINT20B_CANDIDATE_E_H1_RESULT_20260817 -->
## Checkpoint 20B — Candidate-E H1 historical development result

The one-time frozen H1 evaluation completed from a clean synchronized checkout and validated successfully.

- H1: 1,500 events / 36,314 rows
- OOF scored events: 1,070
- H1 result fingerprint: `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`
- raw Kalshi event-equal log loss: `0.10494755188081126`
- Distance event-equal log loss: `0.03379679620851983`
- raw-minus-Distance log-loss delta: `0.071150755672291427`
- raw Kalshi event-equal Brier: `0.020374750709011895`
- Distance event-equal Brier: `0.0090293992615540601`
- raw-minus-Distance Brier delta: `0.011345351447457835`
- Distance raw advancement gate: PASS
- Distance+Momentum raw advancement gate: PASS
- Distance+Momentum nested complexity gate: FAIL
- nested chronological block wins: 2 / 5
- frozen H1 selection: `kxbtcd_btc_distance_offset_logistic.v1`

The more complex Distance+Momentum model was microscopically better in pooled metrics but won only two of five chronological score blocks, so the frozen complexity gate rejected it and the simpler Distance specification was selected.

H1 is permanently development-exposed. H2 outcomes opened: 0. H3 outcomes opened: 0. No post-hoc H1 repair or feature change is authorized. Execution remains prohibited.

<!-- CHECKPOINT20C_CANDIDATE_E_H2_PREPARATION_20260817 -->
## Checkpoint 20C — full-H1 Distance fit and H2 validation freeze

Checkpoint 20B selected exactly `kxbtcd_btc_distance_offset_logistic.v1` under H1 result fingerprint `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`. Checkpoint 20C then performed the single final parameter fit for that already-selected specification on all 1,500 exposed H1 events / 36,314 H1 rows.

- frozen beta_distance: `0.012310034918384302`
- final H1 model fingerprint: `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
- H2 validation fingerprint: `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`
- H2: 750 events / 22,354 rows
- frozen H2 chronological blocks: B0-B4, exactly 150 events each
- H2 unique market labels in frozen request plan: 3750
- H2 outcomes opened: 0
- H3 outcomes opened: 0
- network requests during Checkpoint 20C: 0
- execution/orders: disabled / 0

H2 may not fit parameters, select another candidate, change features, or tune hyperparameters. It must score the frozen full-H1 Distance model exactly once against raw Kalshi midpoint using the predeclared event-equal log-loss/Brier gate. H3 identities remain hard denied. If H2 fails, Candidate E stops and H3 remains untouched. If H2 passes, the same fixed specification may be refit once on H1+H2 and frozen before H3.

<!-- CHECKPOINT20D_CANDIDATE_E_H2_IMPLEMENTATION_20260817 -->
## Checkpoint 20D — Candidate-E H2 evaluator implementation frozen

The network-capable H2 collector/evaluator implementation is frozen before any H2 outcome access.

- parent H2 validation fingerprint: `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`
- final H1 model fingerprint: `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
- H2 implementation fingerprint: `0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e`
- H2 allow-list: 750 events / 22,354 pre-outcome rows / 3,750 market labels
- H2 blocks: B0-B4, 150 events each
- H3 event/market identities: hard denied
- H2 model fitting/tuning/candidate selection: prohibited
- H2 outcomes opened during 20D: 0
- H3 outcomes opened: 0
- network requests during 20D: 0
- execution/orders: disabled / 0

After this checkpoint is safely closed and pushed, the only authorized next action is the one-time H2 outcome exposure/evaluation through `collect_kxbtcd_candidate_e_h2.py`. The collector may resume an interrupted same attempt, but may not start a fresh second H2 attempt.

<!-- CHECKPOINT20F_CANDIDATE_E_H2_RESULT_20260817 -->
## Checkpoint 20F — Candidate-E H2 historical validation PASS

The one-time frozen H2 validation completed from a clean synchronized checkout and its manifest/result artifacts validate successfully.

- H2: 750 events / 22,354 rows / 3,750 finalized market labels
- H2 result fingerprint: `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`
- H2 validation fingerprint: `57f14a37106e376cf124130396a4e51e1b9aaf22d1064eeedeecacf34225d5e9`
- H2 implementation fingerprint: `0710fb65abdd5e2bf3e8d1947227d0450f41d295ba99a16c0b5f7be3623a608e`
- final H1 model fingerprint: `d193275147b8e8a83a52b03928a2f4746b2daee890c472517952488be751a31a`
- frozen beta_distance: `0.012310034918384302`
- raw Kalshi event-equal log loss: `0.11774919111369225`
- Distance event-equal log loss: `0.035893546124196762`
- raw-minus-Distance log-loss delta: `0.081855644989495491`
- raw Kalshi event-equal Brier: `0.022327771656461513`
- Distance event-equal Brier: `0.0099357895512881093`
- raw-minus-Distance Brier delta: `0.012391982105173404`
- median event raw-minus-Distance log-loss delta: `0.07528266021513054`
- chronological H2 block log-loss wins: 5 / 5
- newest B4: win
- frozen H2 gate: PASS

H2 is permanently outcome-exposed and may not be reused as untouched validation evidence for a future candidate influenced by this result. No H2 parameter fitting, candidate selection, feature change, hyperparameter search, post-hoc repair, or execution occurred. H3 outcomes remain sealed.

This is predictive-scoring evidence only. It does not establish trading profitability or execution suitability.

<!-- CHECKPOINT20G_CANDIDATE_E_H3_PREPARATION_20260817 -->
## Checkpoint 20G — Candidate-E H1+H2 final fit and H3 freeze

Candidate E remains exactly `kxbtcd_btc_distance_offset_logistic.v1`. After validated H2 PASS `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`, the same frozen one-parameter specification was fit once on all exposed H1+H2 evidence.

- H1 result fingerprint: `3fef1404d55c70893715bbe318fe664658309b7497bf03add57b1783ea01b906`
- H2 result fingerprint: `eca7c30b1f0d0177ff4025d743031697f13cdc95ce92958dff5a32be390afcf7`
- final fit: 2,250 events / 58,668 rows
- final beta_distance: `0.013805016135330063`
- final H1+H2 model fingerprint: `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
- H3: 750 untouched events / 22,409 pre-outcome rows / 3750 frozen market labels
- H3 blocks: B0-B4, exactly 150 events each
- H3 validation fingerprint: `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`
- H3 outcomes opened: 0
- network requests: 0
- execution/orders: disabled / 0

No feature, candidate, optimizer, hyperparameter, or validation-gate change was made after H2. H3 will score only this fixed H1+H2 model against raw Kalshi midpoint. H3 must pass the same frozen gate shape: positive pooled log-loss delta, non-worse Brier, at least 4/5 chronological block wins, newest-B4 win, positive median event delta, valid final model, full structural coverage, and no policy/firewall violation.

Checkpoint 20G does not contain a network-capable H3 collector. The H3 outcome-opening implementation must be frozen, tested, safely closed, and pushed in a separate checkpoint before any H3 label is requested.

<!-- CHECKPOINT20H_CANDIDATE_E_H3_IMPLEMENTATION_20260817 -->
## Checkpoint 20H — Candidate-E H3 evaluator implementation frozen

The network-capable H3 locked-test collector/evaluator implementation is frozen before any H3 outcome access.

- parent H3 validation fingerprint: `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`
- final H1+H2 model fingerprint: `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
- H3 implementation fingerprint: `6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc`
- H3 allow-list: 750 events / 22,409 pre-outcome rows / 3,750 market labels
- H3 blocks: B0-B4, exactly 150 events each
- H1/H2 event and market identities: hard denied
- H3 model fitting/tuning/candidate selection: prohibited
- H3 outcomes opened during 20H: 0
- network requests during 20H: 0
- execution/orders: disabled / 0

After this checkpoint is safely closed and pushed, the only authorized next action is the one-time H3 locked-test exposure/evaluation through `collect_kxbtcd_candidate_e_h3.py`. The collector may resume an interrupted same attempt, but may not start a fresh second H3 attempt.

<!-- CHECKPOINT20J_CANDIDATE_E_H3_RESULT_20260817 -->
## Checkpoint 20J — Candidate-E H3 locked-test PASS

The one-time frozen H3 historical locked test completed from a clean synchronized checkout and its manifest/result artifacts validate successfully.

- H3: 750 events / 22,409 rows / 3,750 finalized market labels
- H3 result fingerprint: `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`
- H3 validation fingerprint: `a2c1bba22c330a7177e37978b33b85be8d2ad0286525c2e53a7be7e470333197`
- H3 implementation fingerprint: `6a81ad76b5e3b7152169a88b9219e9e8f26fb7854bd58dc17a5f0dfb58563fcc`
- final H1+H2 model fingerprint: `1c6346422247f026d75032bb74fe648ce93e40329b18726500da9276f40bf842`
- frozen beta_distance: `0.013805016135330063`
- raw Kalshi event-equal log loss: `0.13793316358637769`
- Distance event-equal log loss: `0.038920564033036092`
- raw-minus-Distance log-loss delta: `0.099012599553341601`
- raw Kalshi event-equal Brier: `0.027664663135376771`
- Distance event-equal Brier: `0.01025442810344244`
- raw-minus-Distance Brier delta: `0.017410235031934333`
- median event raw-minus-Distance log-loss delta: `0.085591053297719571`
- chronological H3 block log-loss wins: 5 / 5
- newest B4: win
- frozen H3 gate: PASS
- Candidate-E historical H1/H2/H3 generalization program: PASS

H3 is permanently outcome-exposed and may not be reused as untouched evidence for a future model influenced by this result. No H3 fitting, candidate selection, feature change, hyperparameter search, post-hoc repair, or execution occurred.

This establishes strong historical predictive-generalization evidence for the frozen Candidate-E Distance specification. It does not establish trading profitability or execution suitability.

<!-- CHECKPOINT21A_POST_H3_LIFECYCLE_20260817 -->
## D-037 — Freeze the post-H3 champion lifecycle, strict reserve floor, strategy handoff, and prospective full-shadow architecture

- Date: 2026-08-17
- Status: accepted / design freeze
- Parent H3 result fingerprint: `436ea27539ed1bd2b30f96cc892bc5fc4b87cecd37035da8a45ca2583e59af54`
- Protocol fingerprint: `88d1880c026fe8cecf67cbbb8839a6d4acfb463b0871f4ef60db329f50a6ef00`
- Decision: keep `kxbtcd_btc_distance_offset_logistic.v1` as the unchanged champion specification and run at most three sequential expanding-window historical confirmation blocks C1/C2/C3, each containing 500 eligible events divided into five chronological 100-event subblocks.
- Sequential fitting rule: after this protocol closes, fit once on the 3,000 exposed H1+H2+H3 events before C1; after C1 PASS refit once on 3,500 exposed events before C2; after C2 PASS refit once on 4,000 exposed events before C3; after C3 PASS refit once on all 4,500 exposed events before strategy research. No C-block may fit on its own outcomes before scoring.
- Confirmation gate: each C block requires strict pooled raw-minus-Champion event-equal log-loss improvement, non-worse Brier, at least 4/5 chronological subblock log-loss wins, a newest-subblock win, positive median event-level log-loss delta, finite/converged positive `beta_distance`, required structural/TTC coverage, and no source/timing/lineage/firewall/policy violation. Primary ties fail.
- Stopping rule: any C failure stops the sequence immediately. Later C blocks are not materialized or outcome-opened after a prior failure, and a failed block cannot be repaired/rescored as fresh confirmation.
- Reserve rule: start from the strict 6,231-event post-19H-C untouched tail. The champion path must fail closed before fewer than 4,500 strict never-materialized historical events would remain. This leaves room for outcome-blind eligibility exclusions while protecting more than 72% of the current strict tail for future challenger evidence.
- Strategy handoff: historical betting/decision-policy research is authorized only after C1+C2+C3 PASS and a final 4,500-event champion fit. Strategy thresholds, TTC windows, entry/exit logic, sizing, and cost assumptions must use exposed evidence only; the protected strict reserve is prohibited from strategy tuning. Historical strategy P&L is development evidence, not fresh profitability validation.
- Strategy first step: audit whether exposed history actually contains executable bid/ask, depth, fees, timestamps, exit states, and fill-relevant information. Midpoint-only or perfect-fill simulations cannot be represented as realistic profitability evidence.
- Prospective architecture: after a strategy and execution simulator are separately frozen, the intended live phase is a complete read-only shadow stack: live feeds -> synchronized state -> frozen champion probability -> frozen strategy -> local mock order intent -> latency/depth/fee/partial/missed-fill simulation -> mock position and P&L. No exchange write action is permitted.
- Prospective forecasting gate: first formal live cohort is 1,000 newly occurring eligible events in five chronological 200-event blocks under one immutable champion. It must preserve the same pooled log-loss/Brier, 4/5 block, newest-block, positive-median-delta, immutable-ledger, and source/timing/lineage requirements.
- Economic live-shadow thresholds: deliberately deferred until historical strategy research. They must be frozen before the first live mock trade decision. The current `RISK_POLICY.md` still prohibits a live paper/shadow broker, so a separate explicit authorization amendment is required before Layer-B mock execution can run.
- Challenger rule: TTC, momentum, volatility, spread, interactions, and small nonlinear models may be researched only as challengers. Before challenger freeze, use exposed evidence only; the protected strict reserve is not a feature-shopping or hyperparameter-tuning resource.
- Consequence: Checkpoint 21A opens no reserve outcomes, performs no post-H3 refit, selects no strategy, enables no paper broker, and authorizes no demo or real orders.

<!-- CHECKPOINT21B_A_C1_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## Checkpoint 21B-A — C1 preparation implementation freeze

Implementation fingerprint: `b69b13a6d0db89be98229f34a946cbdfa24a7280ddbc8bff968f641714a93672`.

The code path that will later (1) fit the unchanged Candidate-E Distance champion on all 3,000 already-exposed H1/H2/H3 events and (2) sequentially materialize only C1 from the strict queue tail is frozen before reserve access. The C1 collector begins at queue index 3200, has no arbitrary start-index argument, stops exactly at the 500th eligible event, and enforces the Checkpoint-21A 4,500-candidate strict-tail floor.

This checkpoint performs no Champion-R0 fit, no network collection, no C1/C2/C3 outcome access, no C2/C3 materialization, and no execution. After safe closeout, the next action is Checkpoint 21B-B: deterministically create and freeze Champion-R0 on exposed H1/H2/H3 only. C1 materialization begins only after that R0 artifact is safely closed.

<!-- CHECKPOINT21B_B_CHAMPION_R0_20260818 -->
## D-038 ? Freeze Champion-R0 before C1 reserve access

Accepted.

The unchanged Candidate-E champion specification
`kxbtcd_btc_distance_offset_logistic.v1` was deterministically refit once on
all already-exposed H1+H2+H3 evidence before any C1 materialization.

- fit scope: 3,000 events / 81,077 rows
- `beta_distance`: `0.014447239079794087`
- Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- model artifact file SHA-256: `811a2776684f130d8b36f1ffb9253e90d678ffda9faf237815282fb67619c8d3`
- parent 21B-A implementation fingerprint: `b69b13a6d0db89be98229f34a946cbdfa24a7280ddbc8bff968f641714a93672`
- feature selection: none
- hyperparameter search: none
- C1 rows/outcomes used: 0
- network requests: 0
- execution/orders: disabled / 0

This is an expanding-evidence parameter refit of the already-selected one-
parameter Distance specification, not a new model-selection experiment.

C1 materialization is authorized only after this Champion-R0 artifact is safely
closed and pushed. C2/C3 remain unauthorized.

<!-- CHECKPOINT21B_C_C1_PREOUTCOME_FREEZE_20260818 -->
## D-039 ? Freeze C1 before outcome access

Accepted.

Checkpoint 21B-C freezes the first post-H3 champion-confirmation cohort before
any C1 outcome access.

- champion: `kxbtcd_btc_distance_offset_logistic.v1`
- Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- C1 eligible events: 500
- chronological blocks: B0-B4, exactly 100 events each
- candidate identities inspected: 506
- strict-tail queue range consumed: `[3200, 3706)`
- C1 pre-outcome rows: 14887
- unique C1 markets: 2491
- C1 cohort fingerprint: `7f53764ca50d4a5e00a4d12d0cebda566a1333a6951b2686b2c9d06631c1ca36`
- C1 row fingerprint: `6d02d8b484813760a87a7daea05ecf994e18ae875e7e066e9b097ac830e01af8`
- C1 validation fingerprint: `76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`
- strict never-materialized tail remaining: 5725
- hard floor: 4500
- remaining buffer above floor: 1225
- C1 outcomes opened: 0
- C2/C3 materialized: no
- candidate/model/hyperparameter change: none
- execution/orders: disabled / 0

The generated freeze document retains internal `checkpoint_id = 21B-B` because
that literal was part of the implementation frozen in 21B-A. The operational
project stage for reserve materialization/freeze is 21B-C. No code or frozen
research rule is changed merely to rename that inherited metadata.

C1 outcome evaluation must be implemented and frozen in a separate checkpoint
before any C1 labels are requested.

<!-- CHECKPOINT21C_C1_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## D-040 — Freeze C1 evaluator before outcome exposure

Accepted.

The exact C1 outcome collector/evaluator implementation is frozen before any C1
label is opened.

- C1 evaluator implementation fingerprint: `2719cef9c5180014f3230c724be76bf959d71882a2f0c84e386a5169392773af`
- C1 validation fingerprint: `76bc00a2aa6804a789924a3f1ffa6e8890c8e25030ac80d5226db3270b0bc191`
- Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- C1 scope: 500 events / 14887 rows / 2491 market labels
- H1/H2/H3 event and market identities: hard denied
- C1 fresh second attempt: prohibited
- interrupted same-attempt resume: allowed only through validated manifest/journal
- model fitting/tuning/selection on C1: prohibited
- C2/C3 materialization/outcome access: prohibited
- C1 outcomes opened during 21C: 0
- network requests during 21C: 0
- execution/orders: disabled / 0

The full C1 cohort must be marked permanently exposed before the first future
outcome request. This prevents partial network failure from creating a false
second untouched-test claim.

<!-- CHECKPOINT21D_C1_RESULT_20260818 -->
## D-041 ? Candidate-E C1 confirmation PASS

Accepted.

The one-time fresh C1 confirmation completed under the exact frozen
Champion-R0 and Checkpoint-21A gate.

- C1 result fingerprint: `5cd56b6c4711e5a6846e6ea90bb6e004358844585f56fbe663a9d0a0ec17cd19`
- Champion-R0 fingerprint: `ffde1747dbd60a05f6cffb6e970ae47088edeb77c0a67d16a225b2e38b90a0fa`
- beta_distance: `0.014447239079794087`
- C1 scope: 500 events / 14,887 rows / 2,491 finalized market labels
- raw event-equal log loss: `0.17078339823721184`
- Distance event-equal log loss: `0.053151764629610743`
- raw-minus-Distance log-loss delta: `0.11763163360760109`
- raw event-equal Brier: `0.039207186965517601`
- Distance event-equal Brier: `0.01515132922607266`
- raw-minus-Distance Brier delta: `0.024055857739444943`
- median event log-loss improvement: `0.10189307395366344`
- block log-loss deltas: `B0=0.10373801818068928, B1=0.13986583525420937, B2=0.10756039058421205, B3=0.10359083325320459, B4=0.13340309076568999`
- chronological wins: 5 / 5
- newest B4: win
- frozen C1 gate: PASS
- model fitting/tuning on C1: none
- C2/C3 materialized or opened: no
- execution/orders: disabled / 0

C1 is permanently exposed and may never again be represented as untouched
evidence for a model influenced by this result.

Under the frozen Checkpoint-21A lifecycle, C1 PASS authorizes the next
expanding-window preparation step: refit the unchanged Distance specification
on H1+H2+H3+C1 = 3,500 exposed events, freeze that model, and only then
materialize C2 outcome-blind. C3 remains protected.

This is strong predictive-generalization evidence. It is not evidence of
executable trading profitability.

<!-- CHECKPOINT21E_A_C2_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## D-042 — Freeze C2 preparation implementation before Champion-R1 fit

Accepted.

Implementation fingerprint: `c2be562e2476995dd4adb712a035ac69eca8ca6b4b7fa93c53106758286dc327`.

The C2 preparation code is frozen before either the 3,500-event Champion-R1
refit or any C2 reserve access. The unchanged Distance specification is the only
model allowed on the champion path.

Frozen sequence:
1. safely close 21E-A;
2. fit Champion-R1 once on exposed H1+H2+H3+C1 = 3,500 events / 95,964 rows;
3. safely close Champion-R1;
4. materialize C2 outcome-blind starting at strict queue index 3706;
5. stop exactly at 500 eligible C2 events and freeze five 100-event subblocks;
6. keep C2 outcomes sealed;
7. keep C3 untouched.

The absolute historical reserve boundary remains queue index 4931, preserving
at least 4,500 never-materialized events. C2+C3 therefore have at most 1,225
candidate identities of runway after C1.

21E-A performs zero model fits, zero network requests, zero C2/C3 access, and
zero orders.

<!-- CHECKPOINT21E_B_CHAMPION_R1_20260818 -->
## D-043 ? Freeze Champion-R1 before C2 reserve access

Accepted.

After the fresh C1 PASS, the unchanged Candidate-E Distance specification was
fit exactly once on all now-exposed H1+H2+H3+C1 evidence.

- candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- fit scope: 3,500 exposed events / 95,964 rows
- Champion-R1 fingerprint: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- literal artifact SHA-256: `8ecbeb9b14e618d616dabfe5f88d39b78a893d3f5b596f88579e15a236d22201`
- beta_distance: `0.014529004270980883`
- fit objective: `0.053921466611488181`
- optimizer iterations: 10
- converged: true
- specification change: none
- feature selection: none
- hyperparameter search: none
- C2 rows/outcomes used: 0 / 0
- C2 outcomes opened: 0
- C3 materialized/opened: 0
- execution/orders: disabled / 0

The movement from Champion-R0 beta `0.014447239079794087` to Champion-R1 beta
`0.014529004270980883` is an expanding-evidence refit using C1 after C1 became
permanently exposed. It is not an additional validation result.

C2 may be materialized only after this exact Champion-R1 artifact is safely
closed and pushed.

<!-- CHECKPOINT21E_C_C2_PREOUTCOME_FREEZE_20260818 -->
## D-044 ? Freeze C2 before outcome access

Accepted.

Checkpoint 21E-C freezes the second post-H3 champion-confirmation cohort before
any C2 outcome access.

- champion: `kxbtcd_btc_distance_offset_logistic.v1`
- Champion-R1 fingerprint: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- C2 eligible events: 500
- chronological blocks: B0-B4, exactly 100 events each
- candidate identities inspected: 516
- ineligible identities: 16
- strict-tail queue consumed: `[3706, 4222)`
- C2 pre-outcome rows: 14007
- unique C2 markets: 2441
- C2 cohort fingerprint: `446854d2511a942fff560ffe78bbd96863b06d9046de85ff7a8605c868654258`
- C2 row fingerprint: `525477c08178f1bd97f58fee0e22f6e5352494cb38210c433a0df7a2af57c9b3`
- C2 validation fingerprint: `b984017e17da9de2859d43b78f1218d7333eda45eb1ebb0ed3a6a884eb3746f1`
- strict never-materialized tail remaining: 5209
- hard floor: 4500
- remaining buffer above floor: 709
- C2 outcomes opened: 0
- C3 materialized: no
- candidate/model/hyperparameter change: none
- execution/orders: disabled / 0

This checkpoint freezes identities and model inputs only. It is not a C2
predictive PASS or FAIL.

The next task must be an implementation-only C2 outcome evaluator freeze.
That evaluator must bind Champion-R1 and this exact C2
cohort/row/request-plan fingerprint and prohibit refitting, tuning, candidate
selection, C3 access, and execution.

Only after that evaluator implementation is safely closed may C2 outcomes be
opened once.

<!-- CHECKPOINT21F_A_C2_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## D-045 — Freeze C2 evaluator before outcome exposure

Accepted.

The only C2 outcome-opening implementation is frozen under fingerprint
`a958b843a5504507b598f05fba79f57691b21ffe9aee6be8148ca12fd38ab3c2` before any C2 label is requested.

It binds:

- Champion-R1 `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`;
- C2 validation freeze `b984017e17da9de2859d43b78f1218d7333eda45eb1ebb0ed3a6a884eb3746f1`;
- 500 C2 events / 14,007 rows / 2,441 market requests;
- the existing Checkpoint-21A confirmation gate.

The evaluator hard-denies all H1/H2/H3/C1 event and market identities and has
no C3 materialization/outcome path. It performs no fitting, tuning, feature
change, candidate selection, hyperparameter search, or execution.

Before future request #1, the complete C2 cohort must be marked permanently
exposed. A fresh second attempt is prohibited; an interrupted run may resume
only the same validated manifested attempt.

Checkpoint 21F-A opens zero C2 outcomes, makes zero network requests, and
places zero orders.

<!-- CHECKPOINT21F_B_C2_RESULT_20260818 -->
## D-046 ? Candidate-E C2 confirmation PASS

Accepted.

The one-time fresh C2 confirmation completed under the exact frozen
Champion-R1 and Checkpoint-21A gate.

- C2 result fingerprint: `ee6cd30b32a9445096f25934d67dfa34046504ee83889947be8c8a40377a8f62`
- C2 result closeout fingerprint: `5660e4d04856f534543f0fdd53a1b687b07666ffd52d59e8e80fcefe6ddc87cf`
- Champion-R1 fingerprint: `863711cab07ed18784045d657e8ec20e8eb3dfea8d1c74dbcf2076f0399224ee`
- beta_distance: `0.014529004270980883`
- C2 scope: 500 events / 14,007 rows / 2,441 finalized market labels
- raw event-equal log loss: `0.16763671430199342`
- Distance event-equal log loss: `0.05064447819587261`
- raw-minus-Distance log-loss delta: `0.11699223610612081`
- raw event-equal Brier: `0.03957031952485842`
- Distance event-equal Brier: `0.015191801215127898`
- raw-minus-Distance Brier delta: `0.024378518309730521`
- median event log-loss improvement: `0.13555827126142961`
- block deltas:
  `B0=0.13947804627980334`,
  `B1=0.12660541888180846`,
  `B2=0.12982186853271965`,
  `B3=0.084476671344659388`,
  `B4=0.10457917549161326`
- chronological wins: 5 / 5
- newest B4: win
- structural coverage: PASS
- policy/lineage/source/timing firewall: PASS
- frozen C2 gate: PASS
- model fitting/tuning on C2: none
- C3 materialized/opened: no
- execution/orders: disabled / 0

C2 is permanently exposed and may never again be represented as untouched
evidence for a model influenced by this result.

Under the frozen Checkpoint-21A lifecycle, C2 PASS authorizes the next
expanding-window preparation step: refit the unchanged Distance specification
on H1+H2+H3+C1+C2 = 4,000 exposed events / 109,971 rows, freeze that resulting
Champion-R2 model, and only then materialize C3 outcome-blind.

This is strong predictive-generalization evidence. It is not evidence of
executable trading profitability.

<!-- CHECKPOINT21G_A_C3_PREPARATION_IMPLEMENTATION_FREEZE_20260818 -->
## D-047 — Freeze Champion-R2/C3 preparation before C3 reserve access

Accepted.

Checkpoint 21G-A freezes the implementation for the final historical
confirmation transition before any Champion-R2 fit or C3 reserve access.

Frozen implementation fingerprint:
`76db878cbc62662b4f5c372f9dad73767c3bee356a9765e6204c2a0091d92357`.

Champion-R2 must fit the exact unchanged
`kxbtcd_btc_distance_offset_logistic.v1` specification once on the already
exposed H1+H2+H3+C1+C2 evidence:

- 4,000 events
- 109,971 rows
- C3 rows used: 0
- C3 outcomes used: 0
- feature selection: none
- candidate selection: none
- hyperparameter search: none

C3 begins at strict queue index 4222. The absolute Checkpoint-21A boundary
remains end-exclusive 4931, so C3 has at most 709 candidate identities of
runway to obtain exactly 500 eligible events. The reserve budget is not reset.

Checkpoint 21G-A itself performs no fit, no network requests, no C3
materialization, no C3 outcome access, and no execution.

After safe closeout, Champion-R2 fit is authorized. C3 materialization remains
prohibited until Champion-R2 is separately frozen and safely closed.

<!-- CHECKPOINT21G_B_CHAMPION_R2_20260818 -->
## D-048 ? Freeze Champion-R2 before C3 reserve access

Accepted.

Champion-R2 is the deterministic expanding-window refit of the unchanged
`kxbtcd_btc_distance_offset_logistic.v1` specification on all currently
exposed confirmation evidence.

- fit stages: H1 + H2 + H3 + C1 + C2
- fit scope: 4,000 events / 109,971 rows
- beta_distance: `0.014501283346050064`
- fit objective: `0.053511817851523945`
- iterations: 10
- converged: yes
- Champion-R2 fingerprint: `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- literal artifact SHA-256: `d5c99e0099f37eb69921934a850d1778690d53ad7045a394fa91c0e3362b2d14`
- C3 rows/outcomes used: 0 / 0
- C3 outcomes opened: 0
- feature selection: none
- candidate selection: none
- hyperparameter search: none
- momentum term: none
- network requests during fit: 0
- execution/orders: disabled / 0

Champion-R2 must now remain frozen for C3.

Only after this checkpoint is safely closed and pushed may C3 be materialized
outcome-blind from strict queue index 4222. The absolute end-exclusive reserve
boundary remains 4931, leaving at most 709 candidate identities.

This fit objective is training/refit evidence on already exposed outcomes. It
is not a fresh predictive score and not trading-profitability evidence.

<!-- CHECKPOINT21G_C_C3_PREOUTCOME_20260818 -->
## D-049 ? Freeze final historical C3 cohort before outcome access

Accepted.

Checkpoint 21G-C freezes the final historical C3 confirmation cohort
outcome-blind before any C3 settlement labels are opened.

Frozen evidence identity:

- candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- entering model: Champion-R2 `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- C3 eligible events: 500
- chronological subblocks: B0-B4, 100 events each
- candidate identities inspected: 533
- outcome-blind exclusions: 33
- queue range: `[4222, 4755)`
- pre-outcome rows: 13,549
- unique markets / frozen outcome requests: 2,470
- cohort fingerprint: `08add4c28831c0d460dff706b0cc425550a4d5d3f486d3ec7f14622586101f6b`
- row fingerprint: `898400f7401ef9a96a9c1a0a6d2c99479395ff9fb0a13d93ea7c5fbc3dad51db`
- validation fingerprint: `44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0`
- literal freeze SHA-256: `4e1402c6fc15ea24427524ef04d3c14105a7a4b76f75fc6e5cda54ad908965d4`

The strict untouched reserve remaining after C3 materialization is 4,676
events. The predeclared minimum is 4,500, so the reserve-floor buffer is
176 events.

No C3 outcome was opened during cohort construction. No candidate selection,
feature change, hyperparameter search, or model refit occurred. Execution
remains disabled and orders remain zero.

The C3 outcome evaluator must be implemented and frozen in a separate
checkpoint before these labels may be accessed.

<!-- CHECKPOINT21H_A_C3_EVALUATOR_IMPLEMENTATION_FREEZE_20260818 -->
## D-050 — Freeze C3 evaluator before final historical outcome exposure

Accepted.

The final historical C3 evaluator is implementation-frozen before any C3
outcome is opened.

- implementation fingerprint: `8f84f299f21b132ffd2db93aeb1f23dc586d5d11a189a271ef707be94d15455f`
- C3 validation fingerprint:
  `44271afd92e26dcbdcfa0cea099a36f5246a7b135097c56dfd7d2b4bc4738ed0`
- Champion-R2:
  `2e87b3d1f6f6f9b169f04500b95fc8c83d5ddda4b5f9ef43b11c451f5e6d7964`
- fixed beta_distance: `0.014501283346050064`
- C3: 500 events / 13,549 rows / 2,470 market requests
- prior exposed events hard-denied: 4,000
- full C3 cohort becomes permanently exposed before HTTP client construction
  when the evaluation is later run
- fresh second C3 attempt: prohibited
- interruption resume: only the same recognized manifested attempt
- remaining 4,676-event historical reserve: inaccessible to this evaluator
- model fitting/tuning/selection: prohibited
- C3 outcomes opened during 21H-A: 0
- network requests during 21H-A: 0
- execution/orders: disabled / 0

The evaluator uses the unchanged Checkpoint-21A gate. A C3 failure is terminal
for this historical confirmation sequence; it may not be repaired or rescored
and represented as fresh evidence.

<!-- CHECKPOINT21H_B_C3_RESULT_20260818 -->
## D-051 ? Accept Candidate-E C3 as final historical confirmation PASS

Accepted.

The frozen Candidate-E Champion-R2 passed the final C3 historical
confirmation gate without any C3 fitting, tuning, candidate selection,
feature change, hyperparameter search, post-hoc repair, or reserve access.

- C3 result fingerprint: `b37d5f5f299cf338a2bdf730f114a61b1bea25f3af820c21f81bd1fe13072b08`
- C3 result-closeout fingerprint: `2a9ff681973608f2cdd44371eda8bf4208021610e4f3e74f887a173de1447ede`
- C3: 500 events / 13,549 rows / 2,470 labels
- raw event-equal log loss: `0.12097454402315916`
- Champion-R2 log loss: `0.023718447966231782`
- raw-minus-Champion delta: `0.09725609605692738`
- raw event-equal Brier: `0.025969129033350857`
- Champion-R2 Brier: `0.0064734297442716375`
- Brier delta: `0.019495699289079221`
- median event log-loss delta: `0.11153336786189344`
- chronological log-loss wins: 5 / 5
- newest B4: win
- gate: PASS

C1, C2, and C3 have therefore all passed their frozen post-H3
historical confirmation gates.

All 4,500 historical confirmation/development events are now
outcome-exposed. The next exact champion refit may use those 4,500
events / 123,520 rows, but that refit is not fresh confirmation evidence.

The untouched 4,676-event historical reserve remains inaccessible to
post-hoc repair of this result.

Forecast-quality confirmation does not establish executable trading
profitability.

<!-- CHECKPOINT21I_A_FINAL_FIT_IMPLEMENTATION_FREEZE_20260818 -->
## D-052 — Freeze Candidate-E Champion-Final historical fit

Accepted.

After C1, C2, and C3 all passed, the final historical parameter fit is frozen
as an offline deterministic refit of the unchanged Distance champion.

- implementation fingerprint: `902bdd1888bb998fd67902cbfe7bf4f82b036ab32bdd41813f4012133cebf023`
- fit pool: 4,500 exposed events / 123,520 rows
- stages: H1 + H2 + H3 + C1 + C2 + C3
- candidate: `kxbtcd_btc_distance_offset_logistic.v1`
- free parameters: 1 (`beta_distance`)
- momentum: excluded
- optimizer: unchanged deterministic damped Newton
- feature/candidate/hyperparameter selection: none
- fresh-validation claim: none
- remaining historical reserve: 4,676 events, inaccessible
- network/execution/orders: 0 / disabled / 0

The output will be called Champion-Final, not R3, because C3 completed the
historical confirmation sequence and there is no new validation round here.

<!-- CHECKPOINT21I_B_CHAMPION_FINAL_20260818 -->
## D-053 ? Accept Candidate-E Champion-Final

Accepted.

After the complete C1/C2/C3 historical confirmation sequence passed,
the unchanged Distance champion was deterministically refit on all
4,500 outcome-exposed events / 123,520 rows.

- Champion-Final fingerprint: `b45478594c088c09086d55d14e70aa7a22a62dc546cf0f2d9a1e3bb2f296b8dc`
- closeout fingerprint: `1dd79bc396f1dee8afed150930bf5a78ee0581275193545dcde1d579d5b9c43a`
- beta_distance: `0.014939489324405949`
- objective: `0.050195791036485929`
- iterations: 10
- converged: yes
- free parameters: 1
- momentum: none
- specification change after C3: no
- feature/candidate/hyperparameter selection: none
- fresh-validation claim: no
- remaining historical reserve: 4,676
- reserve rows/outcomes used: 0 / 0
- network/execution/orders: 0 / disabled / 0

Champion-Final is the accepted historical parameter estimate for the
next research phase. C3 remains the final fresh historical validation
evidence.

Predictive confirmation does not establish executable profitability.

## Checkpoint 21K-A — Candidate-E Strategy Replay v1 Predeclaration

Accepted decision: freeze `kxbtcd_candidate_e_strategy_replay_v1` as the first baseline historical strategy replay before any strategy P&L is inspected.

Frozen predeclaration fingerprint:

`afc1b397c850e8b2a2dfd32d6656e05f4622c59f1596f5b91295e96debb0d046`

Primary evidence universe is 4,070 genuinely OOS/OOF events / 118,862 prediction rows:
- H1 rolling-origin OOF: 1,070 events / 31,656 Distance-candidate rows.
- H2: 750 events / 22,354 rows.
- H3: 750 events / 22,409 rows.
- C1: 500 events / 14,887 rows.
- C2: 500 events / 14,007 rows.
- C3: 500 events / 13,549 rows.

The 4,676-event untouched historical reserve remains untouched and unavailable for post-hoc strategy tuning.

Strategy v1 rules are frozen before historical execution backfill or P&L scoring:
- evaluate TTC anchors 55m, 50m, 45m, 40m, 35m, 30m in chronological order;
- at each anchor evaluate the frozen structural strikes and YES/NO executable edge;
- one position maximum per event; no re-entry, averaging down, Martingale, or loss chasing;
- fixed size: 10 contracts;
- primary minimum net edge: 0.04 dollars/contract after entry fee;
- predeclared sensitivity thresholds: 0.03 and 0.05, with 0.04 remaining primary regardless of observed performance;
- next-minute execution delay; entry is missed if the hypothetical executable price is more than 0.01 dollars worse than the signal-time ask;
- primary cash-out target captures 50% of initial model surplus; if not achieved, force liquidation around T-5m;
- identical entries are also valued to settlement only as a benchmark, not as an after-the-fact replacement policy;
- historical fee type/multiplier must be resolved by effective transaction time and exact Kalshi fee/rounding rules; unresolved fees fail closed;
- base and conservative execution cases are predeclared; conservative sizing uses a 10% minute-volume participation cap as a historical liquidity proxy and may produce partial or missed fills;
- model-uncertainty stress shrinks Candidate-E's adjustment away from raw market probability by 25%;
- missing, stale, crossed, invalid, or otherwise unresolved market states fail closed.

Future strategy variants are explicitly allowed regardless of Strategy v1 outcome, but each must receive a separate version/predeclaration. Strategy v1 may not be mutated after its economics are inspected. Once Strategy v1 P&L is inspected, the 4,070-event pool is strategy-development evidence and may not be represented as fresh strategy validation evidence.

No demo, paper, or real-money execution is authorized by this decision.

## Checkpoint 21K-B1 — Reusable historical execution archive contract

Accepted decision: freeze `kxbtcd_candidate_e_reusable_execution_archive.v1` before the first 21K-B network request and before any strategy P&L is calculated.

Archive predeclaration fingerprint:

`4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea`

Allow-list fingerprint:

`85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1`

Frozen universe:
- 4,070 OOS/OOF Candidate-E events.
- 20,236 unique KXBTCD markets.
- 118,862 prediction rows.
- Zero cross-stage event overlap.
- Zero cross-stage market overlap.
- The 4,676-event untouched historical reserve remains excluded.

Archive scope is strategy-agnostic. For each allow-listed market, collect the available full tradable lifecycle from `open_time` through `close_time`, including one-minute Kalshi candlesticks, all available public trades, market metadata, historical-cutoff snapshots, KXBTCD series fee history, and event-level fee-change history.

Later separately versioned strategies may reuse this archive without recollection whenever their required inputs are already contained in it. New collection is required only for data outside the frozen scope, such as markets outside the allow-list, times outside the archived lifecycle, or unavailable sub-minute/full-depth history.

Kalshi live/historical cutoffs must be treated as dynamic routing controls rather than hard-coded constants. Raw responses must be preserved before semantic use. Collection must be resumable and must revalidate the frozen allow-list fingerprint on resume.

The exact-applicable-fee requirement for Strategy v1 is clarified to include both parent-series fee history and event-level fee overrides when applicable. This is an execution-cost implementation clarification only; it does not change Strategy v1 entry, exit, threshold, sizing, or model rules.

No P&L scoring, model refit, reserve access, paper broker, demo execution, or real-money execution is authorized by this decision.

<!-- CHECKPOINT21K_B2_COLLECTOR_CLOSEOUT_20260818 -->
## Checkpoint 21K-B2 — raw-first resumable archive collector

Accepted implementation decisions:

- Keep the existing `PublicCensusHttpClient` / append-only raw JSONL path as the
  source-of-truth HTTP layer. Do not create a parallel collector transport.
- Use an ignored local SQLite file only as a transactional resume index and
  normalized working cache. A task is committed only after its complete
  response/pagination chain validates.
- Preserve the frozen B1 archive/allow-list identities unchanged:
  - archive fingerprint
    `4f4ec77deee789b2368bfeeb540270501b3ed0ef10afe637fc245407042739ea`
  - allow-list fingerprint
    `85c74bc868822603d545805b316d01828852f3bfe0a9d72b5e62fef5e61010d1`
  - 4,070 OOS/OOF events / 20,236 markets / 118,862 prediction rows.
- Keep dynamic historical cutoffs. Do not hard-code live/historical routing.
- Reconcile allowed market metadata across live and historical tiers.
- Collect one-minute full-lifecycle candles and complete public trade cursor
  chains. A repeated cursor fails closed.
- If a market lifecycle straddles the trades cutoff, query both trade tiers and
  deduplicate exact duplicate `trade_id` records.
- Query trade boundaries with a one-second cushion and filter locally back to
  the exact market lifecycle rather than relying on undocumented boundary
  inclusivity.
- Missing candle periods are explicit coverage gaps and are never imputed,
  forward-filled, or manufactured.
- Preserve KXBTCD series metadata/fee history and per-event fee-change history.
- Restrict the collector wrapper to approved public GET paths and explicitly
  reject portfolio/order/order-group/communications/transfer paths.
- Treat a live-to-historical candle route transition as a recoverable routing
  event only after the failed response has already been raw-preserved; refresh
  the cutoff once and retry the newly resolved tier.
- Resume lineage must be complete across runs. The resume index is versioned
  `kxbtcd_execution_archive_resume.v2`, backfills inherited raw sessions from
  digest-validated legacy v1 cached tasks, and a completed manifest must
  inventory every raw JSONL file contributing to resumed derived outputs.
  Missing contributing raw lineage fails closed.
- Smoke scopes such as `--max-markets 5` are explicitly non-full and cannot be
  interpreted as completion of the frozen 20,236-market archive.

These decisions are execution-data engineering only. They do not change
Strategy Replay v1, Candidate-E, the protected 4,676-event historical reserve,
or execution authorization.

<!-- CHECKPOINT21K_B3_BOUNDED_PILOT_CLOSEOUT_20260818 -->
## Checkpoint 21K-B3 — bounded 100-market archive pilot

Accepted decisions:

- The 100-market non-full pilot is an engineering PASS for the frozen B2 collector.
- Do not interpret full-lifecycle candle completeness as the replay sufficiency metric.
  Kalshi historical one-minute candles are empirically sparse; missing periods remain
  explicit and are never imputed, forward-filled, or manufactured.
- Replay sufficiency must be evaluated on the exact Strategy-v1 decision states:
  T-55/T-50/T-45/T-40/T-35/T-30 signal states, their next-minute hypothetical
  execution states, and T-5..T-1 force-exit states.
- A missing signal or next-minute state is a missed opportunity, not an imputed fill.
- A missing T-5..T-1 force-exit state uses only the already-frozen settlement fallback;
  no synthetic liquidation price may be invented.
- Historical candle sparsity is therefore an execution constraint and evidence-quality
  property, not by itself a collector failure.
- The pilot does not open Strategy-v1 P&L and does not authorize paper/demo/real execution.
- The protected 4,676-event historical reserve remains untouched.
- The full 20,236-market archive may be considered only as the next collection step;
  its eventual coverage must be audited before replay scoring.

<!-- CHECKPOINT21K_B4A_CANDLE_CHUNKING_DECISION_20260818 -->
## Checkpoint 21K-B4A — historical candle-range transport amendment

During the first full reusable execution-archive attempt, Kalshi returned HTTP
400 for `KXBTCD-25AUG0117-T104999.99` because the requested one-minute candle
range spanned 10,140 periods while the response stated a maximum of 5,000
candlesticks per request.

Accepted transport decision:

- Keep the frozen 4,070-event / 20,236-market archive universe unchanged.
- Keep the full market lifecycle as the requested archive scope.
- Keep one-minute candles (`period_interval=1`).
- Split candle lifecycles into deterministic request windows whose elapsed
  one-minute span is at most 5,000 periods.
- Adjacent windows share the exact boundary timestamp.
- Merge normalized candles by `end_period_ts`.
- Accept duplicate boundary periods only when all normalized market-data fields
  agree; conflicting duplicate values fail closed.
- Preserve raw lineage for every candle request window.
- Store `candles:{ticker}` in the resume database only after all request windows
  for that market validate successfully.
- Markets whose lifecycle is at most 5,000 periods retain single-request
  behavior.
- Reuse the existing scope-bound `full.sqlite`; do not discard completed tasks
  because of this transport-only amendment.

This decision does not change Candidate E, Strategy Replay v1, the missing
candle policy, the protected reserve policy, fee logic, or execution
authorization.

## Checkpoint 21K-B4B ? execution-archive readiness decision

The full 4,070-event / 20,236-market Candidate-E execution archive passed its
structural and model-readiness audit with limitations.

Historical candlestick availability is associated with real trading activity but
also contains a strong archive/representation regime that persists in zero-trade
markets. Entry Model v1 therefore may use directly observed causal activity and
microstructure variables, but must not use raw candle missingness or calendar date
as economic predictors. Missing required states remain ineligible and are never
imputed.

Entry Model v1 must be predeclared before Strategy-v1 P&L is opened.

## D-021L-01 ? Entry Model v1 target and architecture

Accepted for Checkpoint 21L.

Entry Model v1 is a downstream incremental settlement-probability model on top
of frozen Candidate E.

The frozen structural form is:

`logit(p_entry) = logit(p_candidate_e) + g(X_entry_state)`

where:

- `p_candidate_e` is the causally valid Candidate-E OOF/OOS probability for the
  event/state;
- `X_entry_state` contains only predeclared causal entry-state features available
  at the decision timestamp;
- Model 2 learns incremental information beyond Candidate E rather than relearning
  the entire settlement problem from scratch.

Primary statistical target:

- binary KXBTCD settlement outcome.

Model 2 does not directly predict historical trade P&L.

Economic value is computed deterministically after inference from:

- Model-2 settlement probability;
- executable side-specific entry price;
- exact applicable transaction fees.

Conceptually:

`EV_YES = p_entry - all_in_yes_entry_cost`

`EV_NO = (1 - p_entry) - all_in_no_entry_cost`

Exit timing, holding decisions, adding exposure, averaging, and other
position-management actions are explicitly outside Entry Model v1. Those belong
to a later separately validated Position Management model.

Candidate E alone remains the mandatory benchmark. Entry Model v1 earns its place
only if its incremental features improve genuinely out-of-sample performance
under a separately frozen evaluation procedure.

Strategy-v1 P&L remains unopened. The protected historical reserve remains
untouched.

## D-021L-02 ? Candidate-E Entry Model v1 feature contract

**Status:** ACCEPTED / FROZEN for Checkpoint 21L.

Model 2 retains frozen Candidate E as a fixed logit offset and learns only incremental conditional information.

The v1 learned feature families are:
- Coinbase-primary `r_5m`
- categorical TTC anchor
- categorical structural strike role
- contemporaneous spread
- same-minute quote midpoint movement
- same-minute spread change
- same-minute YES-bid range
- same-minute YES-ask range
- `log1p` minute volume
- `log1p` open interest
- `log1p` trailing-5m public trade count
- `log1p` trailing-5m contracts traded
- trailing-5m YES-vs-NO taker-contract imbalance

`q_market` and `d_BTC` are deliberately excluded from the learned residual because they already define frozen Candidate E. Absolute BTC prices, absolute strike, raw bid/ask levels, trade-price OHLC, archive missingness, calendar proxies, identities, fees, future state, P&L, and manufactured quotes are excluded.

Block-trade features are excluded because the reusable archive contains no observed block trades.

The exact current one-minute quote candle is required. Public-trade zeros are valid observations and are not grounds for exclusion.

This decision does not authorize fitting, paper execution, demo execution, or real-money execution.

## D-021L-03 ? Model-2 whole-event chronological evidence roles

**Status:** ACCEPTED / FROZEN for Checkpoint 21L.

The 4,070-event Candidate-E downstream universe is assigned as follows:

- Development: H1_OOF + H2 + H3
  - 2,570 events
  - 76,419 rows

- Validation: C1 + C2
  - 1,000 events
  - 28,894 rows

- Model-2 locked test: C3
  - 500 events
  - 13,549 rows

An outcome-blind chronology audit confirmed:
- 4,070 unique events
- zero multi-stage event assignments
- zero inconsistent event close times
- every adjacent stage boundary is strictly chronological

Whole events are the indivisible evidence unit. Rows from the same event may never cross evidence-role boundaries.

C3 is locked specifically against Model-2 development. It must not influence feature design, preprocessing, model-family selection, regularization, hyperparameters, thresholds, or advancement gates before its one-time Model-2 evaluation.

The 4,070-event pool is not described as globally fresh because it has already participated in Candidate-E research.

The protected 4,676-event historical reserve remains untouched.

## D-021L-04 ? Model-2 residual-logistic family, preprocessing, and tuning

**Status:** ACCEPTED / FROZEN for Checkpoint 21L.

Candidate:

`kxbtcd_candidate_e_entry_residual_logistic.v1`

Form:

    logit(p2) = logit(pE) + g(X_entry)

Candidate E is an exact fixed offset with coefficient 1.

`g` is a 21-parameter L2-regularized logistic residual:
- 1 residual intercept
- 11 frozen continuous features
- 5 TTC reference-coded indicators, T-55 reference
- 4 structural-role indicators, q50 reference

All 21 residual coefficients, including the intercept, are L2-penalized. This deliberately shrinks the learned correction toward zero and therefore toward frozen Candidate E.

Continuous predictors use fit-partition-only event-equal weighted z-scaling. Score-partition statistics may not influence scaling.

No interactions, feature searches, tree models, nonlinear challengers, random shuffling, class weighting, or imputation are permitted in v1.

Frozen lambda grid:

`0.001, 0.01, 0.1, 1, 10`

Development tuning:
- Fold 1: H1_OOF -> H2
- Fold 2: H1_OOF + H2 -> H3

Select the lambda with minimum pooled H2+H3 event-equal log loss. Exact ties choose the larger lambda.

After selection, fit one development model on H1_OOF+H2+H3 only. Validation C1+C2 remains outside the fit.

The exact Candidate-E probability is converted to its stable logit without any new clipping. Non-finite or non-interior Candidate-E probabilities fail closed.

Optimization is deterministic damped Newton with zero initialization, deterministic dense Cholesky Newton solves, Armijo backtracking, and fail-closed numerical behavior.

This decision authorizes no fitting yet; fitting remains prohibited until the complete Checkpoint-21L evaluation and advancement contract is frozen and closed.

## D-021L-05 ? Model-2 statistical validation and locked-test gates

**Status:** ACCEPTED / FROZEN for Checkpoint 21L.

Candidate E is the mandatory Model-2 benchmark.

Primary metric:
- event-equal binary log loss

Secondary metric:
- event-equal Brier score

Validation:
- C1+C2
- 1,000 events / 28,894 rows
- five contiguous chronological 200-event blocks

Validation PASS requires all:
1. pooled Model-2 log loss < Candidate-E log loss;
2. pooled Model-2 Brier <= Candidate-E Brier;
3. Model 2 wins log loss in >=4/5 chronological blocks;
4. Model 2 wins the newest block;
5. median event-level Candidate-E-minus-Model-2 log-loss delta > 0.

If validation fails, Model-2 v1 is rejected and C3 remains sealed against Model-2 evaluation.

If validation passes:
- keep the selected lambda fixed;
- refit exactly once on H1_OOF+H2+H3+C1+C2;
- 3,570 events / 105,313 rows;
- recompute only the frozen fit-data scaling parameters;
- freeze/fingerprint the final fit before C3.

Locked test:
- C3
- 500 events / 13,549 rows
- five contiguous chronological 100-event blocks

C3 PASS requires the same five conditions relative to Candidate E.

C3 PASS validates only incremental probability performance. It does not establish trading profitability or execution readiness.

No post-hoc v1 repair may be rescored on the same validation or C3 evidence.

The protected 4,676-event reserve remains untouched.

## D-021L-06 ? Strategy-neutral Model-2 economic-value contract

**Status:** ACCEPTED / FROZEN for Checkpoint 21L.

Model 2 does not implement an entry strategy.

For each eligible state it provides probability information that may be translated into:

- quoted YES purchase price = YES ask
- quoted NO purchase price = 1 - YES bid
- gross YES/NO settlement-value edge
- standard-fee net EV as a function of hypothetical quantity

Frozen standard fee function:

    F(C,P)
      = ceil_cent(0.07 * C * P * (1-P))

The archive audit passed:
- all 20,236 markets are binary `linear_cent`
- zero event fee overrides
- zero historical event fee-change rows
- KXBTCD fee type is quadratic
- multiplier is 1
- zero historical KXBTCD series fee-change rows

No fixed quantity is selected because fee rounding makes per-contract cost quantity-dependent.

No EV threshold is frozen.

Positive EV is a candidate opportunity, not an automatic buy instruction.

No anchor-selection, strike-selection, side-selection, sizing, ranking, bankroll, exit, hold, add, averaging, or stop policy belongs to Model 2.

Quoted-entry values are economic diagnostics, not fill simulations.

D-021L-05 remains the Model-2 statistical advancement gate.

A later separately predeclared entry-policy phase will study whether and when estimated EV is sufficiently reliable to act upon.
<!-- D-021M-01_OUTCOME_BLIND_PREPARATION_GATE_20260819 -->
## Checkpoint 21L closeout metadata clarification

Commit `b65e03ceaab2c5c404bf363ad28ba180f5eb16d9` was accidentally given a
Checkpoint-21M message, but its contents are the completed Checkpoint-21L
predeclaration closeout. Receipt `cf3c2613a2a06350cf3ef7fa67ff11214e1bf72d`
correctly identifies the checkpoint as 21L. This is a naming-only metadata issue.
Do not rewrite Git history.

## D-021M-01 — Freeze Model-2 development features before attaching outcomes

**Status:** ACCEPTED implementation procedure for Checkpoint 21M; canonical
Windows validation remains pending.

The deterministic Model-2 preparation path must create and independently validate
an outcome-free H1_OOF/H2/H3 feature universe and whole-event chronology map before
any real development labels are attached or Model 2 is fit.

The preparation freeze binds:
- exact source-file hashes;
- implementation-file hashes;
- persisted feature/event-map file hashes;
- deterministic row and event-map fingerprints;
- explicit no-P&L/no-C3/no-reserve/no-execution safety flags.

Development labels may later be attached only by exact `state_id` equality to the
already-frozen feature universe. Outcomes may not influence row eligibility,
feature construction, preprocessing feasibility, chronology, or preparation
fingerprints.

Reason: this makes the outcome firewall mechanically testable and ensures the
frozen D-021L feature universe can be reproduced independently before fitting.

This decision changes no D-021L-01 through D-021L-06 model, feature, evidence-role,
tuning, statistical-gate, or economic specification. It authorizes no Strategy-v1
P&L, C3 evaluation, protected-reserve access, or execution.
<!-- D-021M-02_FROZEN_QUOTE_TIMESTAMP_ALIGNMENT_20260819 -->
## D-021M-02 — Reconstruct the exact frozen Candidate-E Kalshi quote timestamp

**Status:** ACCEPTED outcome-blind pre-fit implementation clarification.

For Model-2 historical feature materialization, `decision_target_utc` remains the
scheduled decision time. Kalshi one-minute quote-candle features are reconstructed
from the exact `kalshi_quote_end_period_ts` already frozen on the Candidate-E
preoutcome row.

Required integrity conditions:
- quote timestamp is minute-aligned and no later than decision time;
- `decision_time - quote_time` exactly equals frozen
  `kalshi_quote_staleness_seconds`;
- staleness is 0 through 60 seconds inclusive;
- the execution archive contains the exact market candle at that quote timestamp;
- the exact candle close matches the frozen Candidate-E YES bid and ask;
- no nearest/later/forward-filled/interpolated/manufactured quote is permitted.

Public-trade features remain anchored to the scheduled decision time, not the
possibly 0-60-second-stale quote timestamp.

Reason: Candidate E's already-frozen historical source contract selected the latest
valid real two-sided quote with `end_period_ts <= scheduled target` and staleness
<=60 seconds, and explicitly distinguished scheduled decision time from selected
Kalshi candle time. The initial 21M implementation incorrectly collapsed those two
timestamps. The first real preparation attempt exposed the mismatch before outputs,
labels, fitting, or economic evaluation existed.

This is not a feature redesign and does not widen the Candidate-E state universe.
It clarifies the imprecise D-021L-02 wording "candle ending at the decision
timestamp" by binding Model-2 features to the actual already-frozen Candidate-E
quote state. D-021L-01 through D-021L-06 otherwise remain unchanged.
<!-- D-021M-03_ACCEPT_OUTCOME_BLIND_PREPARATION_FREEZE_20260819 -->
## D-021M-03 — Accept the independently reproduced outcome-blind development freeze

**Status:** ACCEPTED.

The exact H1_OOF+H2+H3 Model-2 development feature universe is frozen before real
Model-2 label attachment or fitting:
- 2,570 whole events / 76,419 feature rows;
- feature fingerprint `a726785e667dc42cef75a7b1f9c0b42ae81a4906b1d72ff5eb0f58ed5083b2a7`;
- event-map fingerprint `36bd74d8576cf8656a4d4a352330fabd2294c322c5cd91854ed47892fe04a266`;
- preparation fingerprint `2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`.

Acceptance requires and has received:
- successful canonical post-correction regression;
- persisted source/code/output hash binding;
- independent source-to-feature rematerialization;
- independent implementation-hash verification;
- explicit persisted false safety flags for outcomes-in-features, P&L, C3 access,
  protected-reserve access, and execution; plus independent-validator evidence that
  Model-2 fitting had not been performed.

Consequently, the already-exposed H1_OOF/H2/H3 settlement labels may now be attached
only by exact state identity to these frozen rows for the predeclared rolling-origin
development evaluation. No outcome may alter feature construction, eligibility,
chronology, preprocessing design, lambda grid, optimizer, or preparation hashes.

This decision does not open C1/C2 validation, C3, Strategy-v1 P&L, the protected
reserve, or execution. It does not imply that Model 2 improves Candidate E or is
profitable; those are unresolved empirical questions.

<!-- D-021M-04_FREEZE_DEVELOPMENT_EVALUATION_ORCHESTRATION_20260819 -->
## D-021M-04 — Freeze development-evaluation orchestration before reading exposed labels

**Status:** ACCEPTED implementation-control procedure; no scientific rule change.

Before the real Model-2 development evaluation is executed, the orchestration code
that binds frozen feature rows to already-exposed H1_OOF/H2/H3 labels must be
implemented, canonically tested, committed, and pushed.

The orchestration must:
- require the accepted preparation fingerprint and source/core hashes;
- attach labels only by exact `state_id` equality to the frozen feature universe;
- filter non-Candidate-E rows from H1 OOF rather than letting them alter eligibility;
- execute D-021L-04 exactly with no lambda/feature/scaling/optimizer changes;
- persist deterministic result and implementation/output hash evidence;
- support an independent full deterministic recomputation validator;
- expose no C1/C2/C3/reserve/economics/execution input surface.

Reason: the model mathematics was already frozen before outcomes, but a new
real-data orchestration layer could itself become a degree of freedom if it were
written or changed after seeing Model-2 development results. Freezing that layer
first closes that procedural leakage path.

<!-- D-021M-05_EVENT_EQUAL_WEIGHT_PRECISION_GUARD_20260819 -->
## D-021M-05 — Use accurate summation for the unchanged event-equal unit-mass invariant

**Status:** ACCEPTED post-outcome implementation repair; canonical validation pending.

After H1_OOF/H2/H3 outcomes were exposed by the first real development-evaluation
attempt, the run failed because `event_equal_weights()` checked a mathematically
correct weight vector using ordinary sequential `sum()`. The observed ordinary
unit-mass error was `1.317168596415285720e-12`, just beyond the frozen `1e-12`
tolerance, while `math.fsum()` returned exactly `1.0` on the same vector.

The repair is restricted to replacing `sum(weights)` with `math.fsum(weights)` in
the existing invariant assertion. It does **not** change any individual weight or
the scientific definition `1 / (E * n_e)`. It does not change features, row
eligibility, event chronology, scaler formulas, lambda selection, regularization,
optimizer behavior, metrics, or the D-021L-04 evaluation protocol.

Reason: `math.fsum` evaluates the already-required unit-mass invariant with greater
floating-point accuracy, eliminating a false fail-closed trigger without weakening
the invariant or introducing a result-dependent scientific degree of freedom.

Because development outcomes are already exposed, no empirical result may be used
to redesign this repair. C1/C2, C3, reserve, Strategy-v1 P&L, and execution remain closed.

<!-- D-021M-06_EXACT_REPAIRED_CORE_HASH_CHAIN_20260819 -->
## D-021M-06 — Preserve the original preparation hash and bind exactly the accepted repaired core

**Status:** ACCEPTED implementation-control amendment; no scientific-rule change.

The outcome-blind preparation freeze remains immutable and must continue to bind
the original pre-outcome Model-2 core SHA-256:

`1e56a207e72a96a4425d0c6c6796d9781eac363baef5bb0dab3b3b58daa34a1b`.

After development outcomes were exposed, D-021M-05 accepted exactly one numerical
core repair: ordinary `sum(weights)` to `math.fsum(weights)` in the existing
event-equal unit-mass invariant. That repaired core SHA-256 is:

`ce54846f85f3d338bc0f3aadd64d8cc8b9828c0c2ac2b5454f97771ec1a89ee1`.

Development evaluation may proceed only when both facts hold simultaneously:
1. the preparation freeze still contains the original core hash; and
2. the current core file exactly equals the accepted repaired hash.

This is deliberately not an allow-list of arbitrary future revisions and does not
rewrite historical evidence. Any other current core hash fails closed.

Reason: the original binding correctly detected a post-preparation code change, but
could not distinguish the explicitly documented D-021M-05 numerical repair from an
unauthorized scientific modification. The dual binding preserves both provenance
and the narrow accepted repair.

No features, weights, scaling definition, lambda grid, optimizer, metrics, or
D-021L-04 procedure change. C1/C2, C3, reserve, Strategy-v1 P&L, and execution
remain closed.

<!-- D-021M-07_DEVELOPMENT_RESULT_FREEZE_20260819 -->
## D-021M-07 — Freeze selected Model-2 development fit before C1+C2 validation

**Status:** ACCEPTED.

Independent deterministic recomputation validated the complete H1_OOF/H2/H3
development evaluation. The frozen selected lambda is `0.01`.

The development evidence is mixed but slightly favorable in aggregate:
- H2 Candidate-E-minus-Model-2 log-loss delta:
  `+0.00010360998900234286`;
- H3 delta: `-0.000021257901207466512`;
- pooled H2+H3 delta: `+0.0000411760438973896`.

This justifies proceeding to the already-predeclared C1+C2 validation gate but does
not constitute a Model-2 generalization PASS and does not support a profitability
claim.

Before any C1/C2 outcome access, freeze:
- selected lambda and all lambda scores;
- exact full-development 21-coefficient residual fit;
- fit-only 11-feature scaler;
- H2/H3/pooled development diagnostics;
- development/evaluation fingerprints;
- source, implementation, output, and receipt hashes.

Development-freeze fingerprint:
`a3efd1d52255467dd374d32992880344428dccae01de1a97363b43e318595a9e`.

C1/C2 may evaluate this frozen model only. It may not retune lambda, refit on
validation outcomes, change features/scaling, or repair Model-2 post hoc. C3 remains
sealed unless all D-021L-05 validation conditions pass.

<!-- D-021M-08_C1C2_OUTCOME_BLIND_VALIDATION_PREPARATION -->
## D-021M-08 — Reconstruct stage-native Candidate-E baselines outcome-blind for C1+C2

**Status:** ACCEPTED.

For Model-2 validation preparation, Candidate-E probabilities are reconstructed
from frozen pre-outcome rows and stage-native champion contracts:
- C1 uses Champion-R0, beta_distance `0.014447239079794087`;
- C2 uses Champion-R1, beta_distance `0.014529004270980883`;
- formula: `sigmoid(market_logit_offset(q_market) + beta_distance*d_BTC)`;
- historical C1/C2 prediction CSV rows are prohibited during preparation
  because those files include an `outcome` field.

The duplicate historical `stage` and `block_id` columns must agree on every row
before normalization. The combined 1,000 validation events are sorted by
`event_close_time_utc`, then `event_ticker`, and assigned contiguously to five
200-event blocks V0..V4.

Validation-preparation fingerprint:
`25c42d62f3f74814c9665b71628e866aa428fd55fd67d8a1ad65cd337a8caa22`.

This changes no Model-2 feature, coefficient, scaler, lambda, metric, or gate.

<!-- D-021M-09_FINITE_CANDIDATE_E_VALIDATION_OFFSET -->
## D-021M-09 — Preserve finite Candidate-E latent logits when historical probabilities saturate

**Status:** ACCEPTED pre-validation numerical-representation amendment; no scientific-model change.

Outcome-blind C1+C2 preparation discovered six C2 states whose exact finite
Candidate-E latent logits are approximately 37.58 through 37.87. The historical
stable sigmoid therefore rounds their double-precision `candidate_probability`
to exactly `1.0`.

Model-2 v1 requires Candidate E as a fixed logit offset. Clipping those six
probabilities below one would materially alter their offsets, while rejecting
them would discard already-frozen eligible states.

Therefore validation uses the outcome-blind finite-logit sidecar frozen at
`7fdc2127c081894be97a96c4c930c06634a96f19cf13d4fd18c5b95458c978c1`.

Rules:
- preserve the historical Candidate-E probability representation, including six
  values equal to `1.0`;
- introduce no clipping;
- use the exact finite Candidate-E latent logit as Model-2's coefficient-1 offset;
- calculate binary log loss stably from the finite logit;
- calculate Brier from `stable_sigmoid(finite_logit)`;
- change no feature, residual coefficient, scaler, lambda, block, metric, or gate.

This issue was identified and repaired before any C1/C2 outcome row was read for
Model-2 validation.

<!-- D-021M-10_FREEZE_C1C2_VALIDATION_EVALUATOR -->
## D-021M-10 — Freeze the C1+C2 Model-2 evaluator before outcome access

**Status:** ACCEPTED implementation-control freeze.

The exact evaluator that may open C1+C2 outcomes is frozen at implementation
fingerprint:

`8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`.

It may only:
1. attach the two already-frozen C1/C2 outcome artifacts to the frozen
   28,894-row feature universe;
2. apply the exact frozen 21 development coefficients and 11 scaler statistics;
3. use the finite Candidate-E validation-offset sidecar;
4. score pooled event-equal log loss/Brier and the five preassigned 200-event blocks;
5. apply all five D-021L-05 conditions without tolerance or post-hoc repair.

It may not refit, rescale, retune, search features, open C3/reserve data, calculate
Strategy-v1 P&L, or execute orders.

A persistent attempt journal must mark C1+C2 opened for Model-2 before the first
outcome CSV row is read. Interrupted evaluation may resume only under the exact
same frozen implementation.

<!-- D-021M-11_VALIDATION_PREPARATION_SAFETY_PATH_REPAIR -->
## D-021M-11 — Repair nested validation-preparation safety-field lookup after C1+C2 exposure

**Status:** ACCEPTED post-outcome implementation repair; no scientific-rule change.

The first frozen Model-2 C1+C2 validation attempt permanently opened the exact
predeclared C1/C2 outcome artifacts, then failed before scoring because the
evaluator checked `historical_prediction_csv_rows_read` at the preparation-freeze
top level. The accepted preparation freeze stores that flag correctly under
`candidate_e_baseline.historical_prediction_csv_rows_read`.

The persisted attempt journal records:
- status `OUTCOMES_OPENED_FOR_MODEL2_VALIDATION`;
- original evaluator fingerprint `8bc89ebbd97f19245e802217733a89f369bfdae465a9f90c581c90c4dc9f1ec7`;
- C1/C2 opened for Model-2: true;
- C3/reserve/P&L/execution: false.

No validation result directory existed and no Model-2 validation metric had been
calculated when the error occurred.

Accepted repair:
- read only the already-frozen nested field
  `candidate_e_baseline.historical_prediction_csv_rows_read`;
- change no model formula, feature, coefficient, scaler, lambda, validation block,
  metric, or D-021L-05 condition;
- preserve the original attempt and original evaluator fingerprint;
- permit only `--resume` of that exact attempt/output directory;
- prohibit a fresh attempt;
- bind every unchanged evaluator/dependency hash and the one repaired runtime hash.

Repaired validation-runtime SHA-256:
`938286c96f4f717e62e0248ec731b860ce49e6ab7dd36fce0b0719ac2b8eefb2`.

Validation resume-repair fingerprint:
`fee1063a637c99749e47d67bbb553a480d3e72037be1cb9015b26b67f2275aed`.

<!-- D-021M-12_MODEL2_VALIDATION_FAIL_CLOSEOUT -->
## D-021M-12 — Reject Candidate-E Entry Model v1 after frozen C1+C2 validation FAIL

**Status:** ACCEPTED.

The frozen Model-2 C1+C2 validation is complete and independently validated.
`kxbtcd_candidate_e_entry_residual_logistic.v1` is permanently rejected under
its frozen specification.

Validation evaluation fingerprint: `15a6557736204ca58039906434f8b7e83bca719f14cd0a3b4c9b9094e42ce033`.
Validation receipt fingerprint: `5e37a7abab6065414be00761ac79e09e853e587ab3ccf153e9f5a74081b11e2a`.
Result closeout fingerprint: `f27dba7fc5fcf9726a3699b8e611646d0d93b77a3dfdb8050048767a97c36ff7`.

The five-condition gate passed only the positive median-event-delta condition.
Model-2 was worse on pooled log loss and pooled Brier, won only 1/5 chronological
blocks, and lost the newest block.

Consequences:
- no repair, retune, or rescore on C1+C2;
- C3 remains sealed for Model-2 v1;
- protected reserve remains untouched;
- no Strategy-v1 P&L or execution work is authorized by this result;
- a successor requires a separate predeclaration and evidence plan.

<!-- CHECKPOINT21N_A_QUOTED_ENTRY_HOLD_DECISION -->
## D-021N-01 — Replace the unused 21K-A replay design with a simpler Candidate-E quoted-entry/hold strategy family before economic scoring

- Date: 2026-08-22
- Status: accepted
- Context: Model-2 v1 failed its frozen C1+C2 probability-validation gate. Candidate E remains Champion-Final. The project now needs to determine whether Candidate E's validated settlement probabilities translate into useful economic entry opportunities before researching another probability model.
- Decision: Preserve `kxbtcd_candidate_e_strategy_replay_v1` and fingerprint `afc1b397c850e8b2a2dfd32d6656e05f4622c59f1596f5b91295e96debb0d046` as immutable history, but mark that unused design `superseded_before_economic_scoring`. Freeze a distinct strategy family, `kxbtcd_candidate_e_quoted_entry_hold_v1`, fingerprint `5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6`.
- Strategy: at T-55/T-50/T-45/T-40/T-35/T-30, translate frozen Candidate-E YES/NO probabilities through contemporaneous quoted purchase prices and the standard one-contract fee; for each frozen threshold 0c/1c/2c/3c/5c, select the highest net edge at the first qualifying anchor; maximum one entry per event; otherwise abstain; later authorized entries hold to settlement.
- Initial quantity: one whole contract. No Kelly sizing, bankroll optimization, averaging, adding, re-entry, side switching, stop loss, profit target, or early cash-out.
- Evidence firewall: H1_OOF+H2+H3 may first support only an outcome-independent opportunity audit. C1+C2 Strategy-v1 P&L is not authorized until the development-P&L evaluator, threshold-selection rule, and confirmation gate are separately frozen. C3 and the protected 4,676-event reserve remain sealed.
- Interpretation: historical quote economics are standard-fee quoted-entry screening, not proof of historical fills because full-depth/queue history is unavailable.
- Consequence: do not fit a new probability model in 21N-A. Do not calculate realized Strategy-v1 P&L until a later separately frozen evaluator authorizes outcome access.

<!-- D-021N-B-01 -->
## D-021N-B-01 — Strategy-v1 development economic selection protocol

Accepted 2026-08-30.

Bind Strategy-v1 development economics to 21N-A fingerprint
`5abea8adcaa782a57c9f69ef96b638fe1779370774e9f1c99a81b4340d42a8a6`
and opportunity-audit fingerprint
`7175175f11bb2714d4bbfc9dc59d9d23d7be721fa0295d7ed664d598a1036ae0`.

Score exactly 0c/1c/2c/3c/5c threshold policies. Only 0c/1c/2c/3c may be selected;
5c is diagnostic-only because the outcome-independent audit produced 33 entries.

Primary metric is mean net P&L per event including abstentions as zero.

A selection-eligible threshold passes only if:
- displayed-quote pooled mean P&L/event > 0;
- +1c stressed pooled mean P&L/event > 0;
- at least 4/5 chronological 514-event blocks have displayed-quote mean P&L/event > 0;
- newest block B4 is positive;
- H3 displayed-quote mean P&L/event is positive.

Among passers, choose highest +1c stressed pooled mean P&L/event; exact tie chooses
the higher threshold. If none pass, Strategy-v1 development is FAIL.

Predeclaration fingerprint: `692b7239067b3024db908fc0e0809f33f900f685faec97c45743195e19d364e5`.

<!-- D-021N-B-02 -->
## D-021N-B-02 — Adverse-price stress and invalid-boundary rule

Accepted 2026-08-30.

Rescore each already-selected trade at +0c/+1c/+2c/+3c purchase-price stress and
recalculate the standard entry fee at the stressed price. +1c is part of the gate;
+2c/+3c are diagnostics.

If quoted price plus stress exits [0,1], mark that threshold/stress scenario invalid
as a whole. Do not cap, drop, interpolate, or impute the trade.

These are sensitivity scenarios, not empirical slippage/latency/depth estimates.

<!-- D-021N-B-03 -->
## D-021N-B-03 — Historical probability provenance and C1+C2 firewall

Accepted 2026-08-30.

Historical economics must preserve original out-of-sample probability provenance:
H1_OOF uses OOF Candidate-E predictions, H2/H3 use their frozen OOS predictions.
A later C1+C2 confirmation must use Champion-R0 for C1 and Champion-R1 for C2.

C1+C2 Strategy-v1 P&L is not authorized during 21N-B. It may be opened only after
one development threshold is selected and frozen. C3 and protected reserve remain sealed.

<!-- D-021N-C-01 -->
## D-021N-C-01 — Reject quoted-entry/hold Strategy-v1 after development economic gate FAIL

Accepted 2026-08-30.

The frozen `kxbtcd_candidate_e_quoted_entry_hold_v1` development evaluator completed on H1_OOF+H2+H3 under evaluation fingerprint `8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc` and returned `FAIL_NO_THRESHOLD`.

No threshold may be promoted. In particular, the 3c policy had positive pooled displayed-quote and +1c-stress P&L and 4/5 positive chronological blocks, but failed both the newest-block and H3 conditions. The development family is therefore rejected exactly under the predeclared D-021N-B gate; do not rescue it by changing thresholds, TTC anchors, structural-role filters, side rules, sizing, or hold behavior on these same development outcomes.

C1+C2 Strategy-v1 economics remain unopened and are not authorized for this rejected strategy family. C3 and the protected 4,676-event reserve remain sealed. Candidate E remains the forecasting Champion-Final; this result rejects only the tested downstream strategy translation, not Candidate E's probability model.

Next research must begin with a development-only failure analysis on already-exposed H1_OOF/H2/H3 Strategy-v1 evidence before any successor strategy is specified. No new strategy fit or threshold search is authorized by this decision.

<!-- D-021N-C-02 -->
## D-021N-C-02 — Canonical no-threshold representation validator repair

Accepted 2026-08-30 after the 21N-C result-freeze validation attempt.

The frozen 21N-B evaluator serializes `selection.selected_threshold` as empty text when no threshold passes; the 21N-C closeout config normalizes the same semantic state to JSON `null`. The first standalone 21N-C validator incorrectly required only `null` when re-reading the evaluation artifact.

Repair: accept exactly `null` or empty text as equivalent representations of **no selected threshold**. Any actual threshold value remains rejected. This is a validator-only representation repair: evaluation fingerprint `8fa076035ed55cd950d744190b4c88cdacfce07bd57bfe5f7b9ff6f9e76a25bc`, `FAIL_NO_THRESHOLD`, all P&L metrics, gate conditions, evidence exposure, and safety boundaries are unchanged. No new evidence is accessed.

<!-- CHECKPOINT21N_D_FAILURE_ANALYSIS_DESIGN_20260830 -->
## D-021N-D-01 — Freeze bounded Strategy-v1 development failure analysis before slice inspection

**Status:** ACCEPTED / DESIGN FREEZE.

Checkpoint 21N-C rejected `kxbtcd_candidate_e_quoted_entry_hold_v1` with
`FAIL_NO_THRESHOLD`. 21N-D may inspect only the already-exposed H1_OOF/H2/H3
development economics and may generate descriptive successor hypotheses only.

Primary diagnostic population is exactly the frozen 3c threshold at displayed
quotes: 159 selected trades. Detailed diagnostics are predeclared by stage,
chronological block, side, TTC, structural role, purchase-price bucket,
Candidate-E selected-side fair-probability bucket, and quoted-net-edge bucket.

Economic decomposition includes selected-side calibration gap, purchase price,
entry fee, gross pre-fee P&L, net P&L, win/loss severity, and fixed loss-tail
concentration diagnostics. Fixed regime comparisons are H2 vs H3 and B3 vs B4.

No slice may be promoted into a new trade rule from this analysis. No threshold,
TTC, role, side, price bucket, or edge bucket selection is authorized. No
successor model/strategy fit is authorized.

21N-D predeclaration fingerprint: `33fb68841a174d50971d40aefae73ab564f96adcb8aefafcf5e86aa16d21bc8b`.

C1+C2 Strategy-v1 economics remain unopened. C3 and the protected 4,676-event
reserve remain sealed. No paper/demo/real execution is authorized.

<!-- CHECKPOINT21N_E_FAILURE_RESULT_AND_SUCCESSOR_DIRECTION_20260830 -->
## D-021N-E-01 — Freeze failure analysis and preselect successor direction

21N-D analysis `e9b88ded9fe1db1f89e234ad626023c67038bbea84ae35863b817c3858f4a3ef` is accepted as permanent exploratory evidence. The primary diagnosis is reliability/calibration deterioration rather than quote-price/fee deterioration.

Preselect a deterministic reliability-adjusted entry/abstention baseline as the next research family while Candidate E remains unchanged. A learned entry/meta-model is deferred as a later challenger; it is not permanently rejected. No exact Strategy-v2 adjustment is selected and no successor fit is authorized.

Result-closeout fingerprint: `bdbdf4db9b83410b3e9689a4ed5ed66ba995be507c5bacea32a6b59c74678dad`. C1+C2 strategy economics, C3 strategy economics, protected reserve, and execution remain closed.

<!-- CHECKPOINT21N_F_RELIABILITY_SHRINKAGE_DESIGN_20260830 -->
## D-021N-F-01 — Freeze reliability-shrinkage Strategy-v2 before opportunity inspection

**Status:** ACCEPTED / DESIGN FREEZE.

Strategy-v2 keeps Candidate E unchanged and shrinks only its disagreement with
the contemporaneous Kalshi midpoint:

`p_adj_side = q_side + alpha * (pE_side - q_side)`.

Candidate alphas are exactly 0.25, 0.50, and 0.75. Alpha 1.00 is diagnostic
reference only. Adjusted net edge must be >= 0; there is no new threshold grid.
All Strategy-v1 anchor, role, side, tie-break, one-contract, and one-entry rules
remain fixed.

Before any Strategy-v2 P&L, an outcome-independent audit must exactly reproduce
the frozen Strategy-v1 full selection SHA and alpha=1's 820-entry 0c policy.

To avoid spending outcome-aware research budget on a cosmetic change, a candidate
alpha must have >=100 total opportunities, >=20 per development stage, and change
at least 10% of alpha=1 decisions (removed events plus changed chosen states)
before a later economics design may even be considered.

No alpha is selected in 21N-F.

Strategy-v2 predeclaration fingerprint: `b3fd3a3c71c5750604ef4e6eddd23043a75952d2c06a48cbb39ae6ef1066bd50`.

C1+C2 strategy economics remain unopened; C3/reserve/execution remain closed.

<!-- CHECKPOINT21N_G_SHRINKAGE_ECONOMICS_20260831 -->
## D-021N-G-01 — Freeze Strategy-v2 opportunity result and two-alpha economics protocol

**Status:** ACCEPTED / PRE-OUTCOME FREEZE.

The 21N-F opportunity audit is frozen under fingerprint `b0971d51ac76fc26402dfbab49fde85167cb0bb4153069b80d1db2dbaccdcf20`.
Alpha 0.50 (276 entries) and alpha 0.75 (591 entries) passed the predeclared
sample/materiality screen. Alpha 0.25 has only 15 entries and is permanently
sample-ineligible for this experiment. Alpha 1.00 is the already-exposed
Strategy-v1 reference and will not be rescored.

Only alpha 0.50 and 0.75 may be scored on already-exposed H1_OOF/H2/H3 outcomes.
Both use the exact frozen 21N-F event selections.

Development gate mirrors Strategy-v1: positive base pooled, positive +1c pooled,
>=4/5 positive base chronological blocks, positive newest B4, and positive H3.
Among full-gate passers, highest +1c stressed P&L/event wins; exact tie -> lower
alpha. No pass -> FAIL_NO_ALPHA.

No intermediate alpha, threshold, TTC, side, role, price, or edge-bucket repair
is allowed after outcomes are opened.

Audit-result closeout fingerprint: `ff2a021063155c6fdfd012818363faccc2906468471d61b49e61572740606dcd`.
Economics predeclaration fingerprint: `139435ffb43d51d09afa4154aeba2fe9c22cb82b5b7edd435516d4ab71e2c55f`.

C1+C2 strategy economics remain closed until a selected development PASS is
separately frozen. C3, reserve, paper/demo/live execution remain closed.

<!-- CHECKPOINT21N_H_CONDITIONAL_ALPHA_ARCHITECTURE_20260831 -->
## D-021N-H-01 — Close global-alpha Strategy-v2 and accept conditional-alpha successor architecture

**Status:** ACCEPTED.

Strategy-v2 development evaluation `97ccad587cbfd32c9a390e91800b52da91f5b53e1a273cbecca39b802ab51e21`
is frozen as `FAIL_NO_ALPHA`.

Alpha .50 was economically positive at base and +1c stress but passed only 3/5
chronological blocks, below the frozen 4/5 requirement. Alpha .75 failed pooled,
stress, newest-block, H3, and block-stability conditions.

The simple global-alpha family is therefore closed. No alpha .25 rescue,
intermediate-alpha search, or post-hoc side/TTC/role filter repair is permitted
on the same exposed evidence.

Accepted successor architecture:

`alpha_i = sigmoid(gamma_0 + gamma^T X_i)`

`p_adj_i = q_i + alpha_i * (pE_i - q_i)`

This learns state-conditional trust in Candidate E's disagreement with Kalshi
while constraining adjusted probability to remain between the market midpoint
and Candidate E.

The new candidate must not directly fit realized trade P&L. Settlement outcomes
may supervise reliability only after an exact objective/evidence protocol is
predeclared. Quote/fee economics remain downstream.

H1/H2/H3 are fully exposed development evidence. C1/C2 outcomes are already
exposed for prior Model2 research and are not globally fresh. C3 remains locked
against conditional-alpha development; protected reserve remains sealed.

No conditional-alpha fit is authorized in 21N-H.

Strategy-v2 result closeout fingerprint: `02b8aab23161419abd1cdf02c79072f070067ed28f16ef186959e6fc5b3f5ee4`.
Conditional-alpha architecture fingerprint: `bb7ebb7b12a9b817465e9e522d65b2f5a129f9e5aaa12a1c8ac6e5fd666a6742`.

<!-- CHECKPOINT21N_I_CONDITIONAL_ALPHA_EXACT_PREDECLARATION_20260831 -->
## D-021N-I-01 — Freeze the exact conditional-alpha reliability v1 baseline before fitting

**Status:** ACCEPTED / PREDECLARATION FREEZE.

Candidate: `kxbtcd_candidate_e_conditional_alpha_reliability.v1`.

The first learned reliability model has exactly four standardized causal features:
absolute Candidate-E/market disagreement, contemporaneous spread, absolute
five-minute BTC return, and continuous TTC minutes. No side, structural-role,
Kalshi-movement/range, activity, open-interest, TTC-bucket, calendar/block, or
interaction feature is included in v1.

`alpha_i = sigmoid(gamma_0 + gamma^T X_i)` and
`p_adj_i = q_i + alpha_i * (pE_i - q_i)`.

All five gamma parameters start at zero, so every state starts at alpha .50.
All five parameters including the intercept are L2-regularized; the exact lambda
grid is .001/.01/.1/1/10. This makes global alpha .50 the nested zero-parameter
reference while allowing training to learn a different alpha for each state.

Historical supervision must use the already-frozen OOF/OOS Candidate-E
prediction artifacts, not retroactively regenerated Champion-Final in-sample
predictions. Candidate E is not refit.

Lambda selection uses H1_OOF->H2 and H1_OOF+H2->H3 rolling-origin folds,
selecting minimum pooled H2+H3 event-equal log loss; exact tie chooses larger
lambda.

Development economics use only those H2/H3 rolling-origin predictions: 1,500
OOF score events split into five contiguous 300-event blocks. Full-development
in-sample economics are prohibited.

The model must pass both the frozen probability gate versus Kalshi, Candidate E,
and alpha .50 and the frozen quoted-entry economic gate before a full H1/H2/H3
fit can be frozen for later C1+C2 confirmation.

C1+C2 are outcome-exposed and later non-fresh confirmation only; C3 remains
locked against conditional-alpha development; protected reserve remains sealed.
No conditional-alpha fit or outcome scoring is authorized in 21N-I.

Predeclaration fingerprint: `742ff487d63e247a4a14d31d9105977b0755ef38d30ad255e85dd77a741ef4d3`.
Parent architecture fingerprint: `bb7ebb7b12a9b817465e9e522d65b2f5a129f9e5aaa12a1c8ac6e5fd666a6742`.
Parent Strategy-v2 result closeout fingerprint: `02b8aab23161419abd1cdf02c79072f070067ed28f16ef186959e6fc5b3f5ee4`.

<!-- CHECKPOINT21N_J_A_CONDITIONAL_ALPHA_IMPLEMENTATION_20260831 -->
## D-021N-J-01 — Reuse the exact frozen 21M causal state universe

**Status:** ACCEPTED.

Conditional-alpha v1 materialization must project the exact frozen 21M Model-2
development feature CSV rather than build a new historical state universe.

Parent preparation fingerprint:
`2e5d71c0af8ea9204003eea44bc8494aeb7a8afd6eef0ea16effb99ca54f7e7d`.

Parent feature-file SHA-256:
`0d52f0cffa30f73c05c820f9f1e9f297a195e9ecb9f2d6193f079767e0b4489c`.

The exact preoutcome quote file is revalidated against the parent preparation
receipt. Candidate-E probability and r_5m are not regenerated.

This prevents timestamp/materialization drift from being mistaken for
conditional-alpha model improvement.

## D-021N-J-02 — BFGS frozen requirement is fail-closed

**Status:** ACCEPTED.

All lambda fits initialize gamma at zero and the inverse-Hessian approximation
at identity. After each accepted Armijo step, convergence is checked before the
BFGS curvature update. If not converged and y^T s <= 1e-12, the fit fails closed.
The implementation does not silently skip or reset the update.

21N-J-A contains no real-data fit or outcome-scoring command.
Implementation fingerprint: `566f085ef78e8045a75a1dc3781255a2dcae30f23d04ba317ab56e87ac18f5a6`.

<!-- CHECKPOINT21N_J_B_CONDITIONAL_ALPHA_PREPARATION_20260831 -->
## D-021N-J-B — accept outcome-blind conditional-alpha preparation

Accepted the deterministic 2,570-event / 76,419-row conditional-alpha development
projection under preparation fingerprint
`a5a1901d9cdd18458bd8de6371c01d0e635d81f4c02b2f9167a5b30c9e42db46`.

Independent rematerialization PASS reproduced the same rows from the exact frozen
21M parent feature/preoutcome lineage.

This decision freezes provenance only. It does not authorize outcome attachment,
gamma fitting, lambda selection, probability scoring, P&L, C1/C2/C3/reserve
access, or execution.

Next: separately freeze the H-development label-attachment and rolling-origin
evaluation orchestration before any real conditional-alpha outcome scoring.

<!-- CHECKPOINT21N_K_CONDITIONAL_ALPHA_DEVELOPMENT_EVALUATOR_20260831 -->
## D-021N-K — freeze conditional-alpha H-development evaluator

Accepted evaluator design: bind exact J-B preparation plus exact H1_OOF/H2/H3
Candidate-E label sources; use the frozen two-fold rolling-origin lambda procedure;
evaluate the probability gate first; expose conditional-alpha economics only after
probability PASS; fit H1+H2+H3 only after both gates PASS.

Implementation fingerprint: `02530cdd8ba58b45cde85c0ba40f681355ce5b14c4a3ad53ee5f1072fff156a8`.

21N-K itself opens no outcomes and performs no real fit or P&L. C1+C2/C3/reserve
and execution remain closed.

<!-- CHECKPOINT21N_L_CONDITIONAL_ALPHA_FAILURE_RECORDING_REPAIR_20260831 -->
## D-021N-L — optimizer-contract failure is terminal for conditional-alpha v1

Accept the first required-fit BFGS curvature failure as a predeclared development
failure. The only authorized post-outcome code change is deterministic failure
recording.

Repair fingerprint: `276fdf07803d083a67d94e6c5b923fcbf06392c4db4fb33cd1d9c1f3a954a865`.

No optimizer/tolerance/lambda/feature/gate change and no fallback/skip/rescue is
authorized.

<!-- CHECKPOINT21N_M_A_CONDITIONAL_ALPHA_V2_PREDECLARATION_20260831 -->
## D-021N-M-A — version conditional-alpha v2 with an optimizer-only Newton replacement

**Status:** ACCEPTED / PREDECLARATION FREEZE.

Do not modify or rescue v1. Create `kxbtcd_candidate_e_conditional_alpha_reliability.v2` and inherit the complete v1 scientific contract except its BFGS optimizer. Replace BFGS with exact-Hessian damped Newton using deterministic Cholesky, unchanged `1e-8` gradient convergence, Armijo backtracking, no numerical fallback, and fail-closed positive-definiteness/direction/line-search/convergence rules.

Reason: v1 BFGS failed its frozen absolute curvature guard, while independently checked exact derivatives plus the project-native damped-Newton pattern passed all 10 lambda/fold fit cases in at most 9 iterations. This is numerical solvability evidence, not predictive or profitability evidence.

Predeclaration fingerprint: `6fdc0421ea2f416b48bb41498cd3c48db6e581ff5364eae5cfa3916a4fa149f8`.

<!-- CHECKPOINT21N_M_B_CONDITIONAL_ALPHA_V2_IMPLEMENTATION_20260831 -->
## D-021N-M-B — implement v2 as an optimizer-only exact-Hessian Newton successor

**Status:** ACCEPTED FOR IMPLEMENTATION VALIDATION.

Reuse the frozen v1 feature/scaling/objective primitives and replace only BFGS
with deterministic exact-Hessian damped Newton. Cholesky failure is terminal;
no jitter, diagonal loading, pseudoinverse, or fallback optimizer is allowed.

Implementation fingerprint: `459d88306ac1d120efebbd8c3c675b4b7b72a6137b915074c2c9abccc8c595fd`.

This does not reclassify the permanent v1 optimizer failure and does not
authorize a real v2 development fit.

<!-- CHECKPOINT21N_M_C_CONDITIONAL_ALPHA_V2_EVALUATOR_20260831 -->
## D-021N-M-C — reuse frozen v1 evaluation machinery; replace only the fitter path

**Status:** ACCEPTED FOR IMPLEMENTATION VALIDATION.

The v2 evaluator reuses the accepted state/label bindings, event-equal metrics,
probability gate, fee logic, quoted-entry policy, stress rules, and economic gate.
Every learned fit is routed through the frozen v2 exact-Hessian Newton fitter.

Evaluator fingerprint: `bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`.

No scientific threshold/gate/evidence-role change is authorized.

<!-- CHECKPOINT21N_M_C_R1_TEST_HARNESS_REPAIR_20260831 -->
### D-021N-M-C-R1 — accept pre-outcome test-harness/exception repair

Accept two non-scientific repairs discovered by focused tests before closeout: deterministic nonconstant synthetic spread data, and a normal mutable contextual exception class. No numerical/model/evidence/gate rule changes. Updated evaluator fingerprint: `bca7dfb15c86c6af33eb208ae3bac65e953b19ab2ac09ac30ee2e56e723a641a`.

<!-- CHECKPOINT21N_M_C_R2_SYNTHETIC_ORCHESTRATION_TEST_REPAIR_20260831 -->
### D-021N-M-C-R2 — do not require global Hessian positive-definiteness from arbitrary synthetic fixtures

**Status:** ACCEPTED TEST-DESIGN REPAIR.

Conditional-alpha's exact Hessian is not globally guaranteed positive definite.
The v2 scientific contract already requires fail-closed Cholesky behavior rather
than jitter/fallback. Therefore synthetic orchestration tests must not redefine
successful fitting as a universal property of arbitrary synthetic rows.

Test numerical convergence separately from evaluator routing.

<!-- CHECKPOINT21N_N_A_ALPHA_ENTRY_DIAGNOSTIC_PREDECLARATION_20260831 -->
## D-021N-N-A — Separate probability quality from entry-ranking utility

**Accepted.**

Conditional-alpha v2's probability-gate failure remains final. It does not
logically answer whether its alpha score contains useful economic ranking
information among Candidate-E-positive-edge opportunities.

For the diagnostic, Candidate E remains the sole valuation probability and alpha
is ranking/filter information only. No H P&L threshold selection is permitted.

Predeclaration fingerprint: `2d8db11742b4f88deb61b810266111b246faf7164ea0c019ad5528cf7326b55e`.

<!-- CHECKPOINT21N_N_B_ALPHA_ENTRY_DIAGNOSTIC_IMPLEMENTATION_20260831 -->
## D-021N-N-B — preserve Candidate-E valuation before alpha attachment

**Accepted implementation rule.**

The diagnostic must select Candidate-E opportunities without using alpha or
outcome. Only the already-chosen row's alpha may be attached for ranking.

This prevents the failed conditional-alpha probability model from silently
becoming the valuation model again.

Implementation fingerprint: `2bc7d625fa7889ee071322a3d3785becc49fd66fcf409e47713de8dc2405bc0d`.

<!-- CHECKPOINT21N_N_C_A_INCREMENTAL_ALPHA_SCORE_PREDECLARATION_20260831 -->
## D-021N-N-C-A — alpha must demonstrate incremental value beyond Candidate-E edge

**Accepted.**

Do not infer alpha's usefulness from alpha quartiles alone because alpha and
Candidate-E quoted edge are correlated.

Use the one-parameter score:
`z(edge) + beta*z(logit(alpha))`.

Beta 0 is the required edge-only benchmark. Alpha remains in the architecture
only if a frozen positive beta beats beta 0 under the predeclared development
comparisons.

Predeclaration fingerprint: `bb341361f191621564459fef3f68d893181498cb687e131e39183441a3eb27fa`.

<!-- CHECKPOINT21N_N_C_B_INCREMENTAL_ALPHA_SCORE_IMPLEMENTATION_20260831 -->
## D-021N-N-C-B — implement the incremental score without outcome leakage

**Accepted implementation rule.**

Scaling and score ranking may use only Candidate-E net edge and logit(alpha).
Outcomes and realized P&L enter only after each beta's top-128 set has been fixed.

Beta 0 remains the required edge-only comparator; no coverage or absolute
threshold search is implemented.

Implementation fingerprint: `8c88bb386e0ba13b3ab8761e67a73dd7105637d3667d5fc7394d163259b5471b`.

<!-- CHECKPOINT21N_N_C_RESULT_CLOSEOUT_20260831 -->
## D-021N-N-C — preserve forecasting/strategy separation; close alpha entry branch

**Accepted.**

1. Close `kxbtcd_candidate_e_incremental_alpha_entry_score.v1` as
   `NO_INCREMENTAL_ALPHA_SIGNAL`.
2. Do not rescue it on exposed H2/H3 using new betas, coverage, thresholds,
   TTC/side/role slices, or additional score terms.
3. Candidate E remains the frozen forecasting/valuation layer.
4. Do not convert Candidate E into a P&L-trained all-in-one betting model.
5. A downstream strategy layer may use Candidate-E probability/edge together
   with executable-market and realizability features.
6. Candidate-E refinements must target forecast quality under separately frozen
   evidence; strategy refinements target economic decision quality.

Rationale: probability estimation and trade profitability are different
objectives. Keeping them separate preserves calibration, interpretability,
reusability, and cleaner failure attribution.

<!-- D-021N-O_PREDEXON_RECONCILIATION_AUTHORITY_20260901 -->
## D-021N-O — make full-book reconciliation authoritative for Predexon replay

**Accepted.**

1. Predexon displayed snapshot sequence numbers are diagnostic metadata, not a
   universal continuity key across `live_early` and `websocket` sources.
2. Continuity is accepted only when exact ordered paid deltas reconstruct the
   next trusted full snapshot, with `1e-9` tolerance used only for snapshot JSON
   quantity serialization noise.
3. An unreconciled adjacent snapshot pair is a hard boundary. Book state is
   never carried, forward-filled, interpolated, or repaired across the pair.
4. A paid delta that would create negative resting quantity fails closed.
5. The 2026-07-10 paid shard is accepted as exploratory/development sandbox
   evidence only: 623 contracts but only 4 independent hourly events.
6. No additional Predexon purchase is needed for development. Future fresh-event
   acquisitions require a frozen protocol and may use only user-available
   promotional/free credit without knowingly incurring a card charge/top-up.
7. Candidate E remains the frozen valuation layer. This source result authorizes
   only later read-only historical execution/realizability research, not order
   execution or a profitability claim.

Rationale: the frozen 20-contract sample reconstructed 8,210/8,273 adjacent book
transitions exactly (99.2385%). On the worst inspected contract, all 585
cross-source sequence decreases reconstructed exactly, proving that sequence
decrease alone is not a valid boundary rule.

<!-- CHECKPOINT21N_P_REPLAY_CLOSEOUT_20260901 -->
## 2026-09-01 — Predexon full-ladder replay and anchor-local eligibility

Accepted decisions:
1. Full replay uses one sequential scan of the paid Parquet because ticker blocks are contiguous and internally ordered.
2. Displayed sequence changes are not continuity authority; exact ordered delta reconstruction is authoritative.
3. An unreconciled adjacent snapshot pair creates a hard segment boundary.
4. Historical execution research uses anchor-local source eligibility rather than ticker-level or event-level coverage cutoffs.
5. A ticker-at-anchor state is eligible only when the exact decision timestamp lies inside a continuously verified segment.
6. Missing/unverified execution state is unavailable; there is no interpolation, carry-forward, nearest-time substitution, or cross-strike substitution.
7. Once latency is predeclared, the complete decision-to-execution interval must remain inside the same verified segment.
8. The four July 10 hourly events are exploratory methodology-development evidence only. The 623 strikes are not independent observations.
9. Strategy P&L remains sealed until the executable-entry methodology is frozen.

<!-- CHECKPOINT21N_Q_EXECUTABLE_CONVERGENCE_LIQUIDATION_PREDECLARATION_20260901 -->
## Checkpoint 21N-Q decision — executable convergence liquidation is the first microstructure strategy baseline

Hold-to-settlement is the matched control. The primary branch attempts to monetize convergence to the frozen
entry-time Candidate-E fair value using exact reconstructed bid depth, latency, IOC fills, fees, partial/missed
fills, and fail-closed replay continuity. Arbitrary take-profit grids, dynamic fair-value retargeting, retries,
forced exits, and arbitrary non-structural strike mining are excluded from v1.

The four July 10 events may debug methodology but may not select a strategy winner.

<!-- CHECKPOINT21N_Q1_FEE_ACCOUNTING_AMENDMENT_20260901 -->
## Checkpoint 21N-Q1 decision — correct fee ledger without changing strategy

Accepted an outcome-blind amendment to replace three coarse fee/cash-rounding descriptions in 21N-Q. The research
baseline models direct exchange/API execution at $0.0001 balance precision. Trade-fee components are ceiled to
$0.000001 per synthetic fill, with Kalshi-style balance alignment and an order-local rebate accumulator.

This is bookkeeping correction only; it does not reopen or alter entry, liquidation, threshold, latency, sizing,
Candidate-E, or evidence-selection decisions.

<!-- CHECKPOINT21N_R_SIMULATOR_IMPLEMENTATION_20260901 -->
## Checkpoint 21N-R decision — deterministic historical execution-state semantics

Accepted implementation fingerprint `6877bf440c88e72e3dd103b55a64f935bc937eeff84ae4cf7af7a6f60d86b4bf` without changing the 21N-Q strategy or 21N-Q1 accounting.

For millisecond timestamp ambiguity, use one right-continuous final reconstructable state per millisecond.
Do not expose same-millisecond transient states to decision or liquidation logic.

For counterfactual market impact, consume visible depth for the IOC being simulated but leave later historical
book states exogenous. This is a small-order modeling assumption required by historical counterfactual replay,
not a factual zero-impact claim.

Latency/source failure does not trigger fallback to a later TTC anchor. Trigger scanning includes the entry-arrival
state and then later distinct reconstructed millisecond states. After-close book data remains prohibited.

## Checkpoint 21N-S-A — Outcome-Blind Real-Data Binder Implementation Freeze

**Decision:** split 21N-S into implementation freeze (S-A) and real outcome-blind materialization (S-B). The code that binds structural roles, BTC states, replay timelines, signals, and execution paths must be committed before the real July 10 signal/path diagnostics are visible.

**Rationale:** this prevents implementation choices from being adapted to observed real path behavior. The binder must reuse the frozen Candidate-E model and 21N-R strategy/simulator rather than introduce a new model or entry rule.

**Binding decision:** the full frozen 623-market July 10 ladder determines structural strike roles; `coinbase_current_price` is the frozen Candidate-E BTC input; exact decision timestamps must lie inside verified replay segments; no interpolation/nearest/carry/cross-strike proxy is allowed.

**Safety decision:** settlement-fallback quantities are permitted as position-state diagnostics, but settlement labels/values and realized P&L remain prohibited until a later explicitly frozen evaluator phase.

<!-- CHECKPOINT21N_S_B_OUTCOME_BLIND_MATERIALIZATION_RESULT_20260901 -->
## 2026-09-01 — Do not open July 10 outcomes after non-evaluable S-B

Accepted decision: classify Checkpoint 21N-S-B as
`NON_EVALUABLE_NO_VALID_TWO_SIDED_DECISION_STATE`.

Rationale: none of 120 frozen role-anchor states reached Candidate-E signal generation. The failure split is
47 source-unavailable, 40 missing YES bid, 33 missing YES ask, with 0 crossed and 0 valid two-sided books.
Settlement labels therefore cannot evaluate executable strategy economics for this sample.

Do not rescue, loosen, interpolate, carry, change structural roles, alter thresholds, or reinterpret one-sided
states after viewing these diagnostics. Keep July 10 outcomes closed. Move to fresh prospective read-only
execution-data collection.

<!-- CHECKPOINT21N_T_CONTINUOUS_CONVERGENCE_REENTRY_PREDECLARATION_20260901 -->
## 2026-09-01 — New continuous strategy version after fixed-anchor non-evaluable result

Accepted: create `kxbtcd_candidate_e_continuous_convergence_reentry_v1`; do not alter or reinterpret the closed
fixed-anchor strategy.

Reason: fixed anchors are useful for controlled model validation but operationally artificial for execution because
liquidity can appear between anchors. Candidate E itself has no TTC coefficient, so the successor deliberately
stress-tests the frozen model at causal non-anchor timestamps while labeling those uses extrapolation.

Permit one re-armed re-entry after full cash-out. Record Trade-1 history but forbid it from influencing Trade 2 in
v1. No tuning from four July 10 events.

<!-- CHECKPOINT21N_U_A_CONTINUOUS_IMPLEMENTATION_FREEZE_20260901 -->
## 2026-09-01 — Freeze continuous implementation before real continuous path evidence

Accepted: split 21N-U. U-A freezes collector/simulator code first. U-B later materializes and binds Coinbase source data. A verified segment start is a causal availability transition; one entry IOC may be pending at a time; missed entry scanning resumes only after arrival. These are implementation conventions, not post-result tuning.

<!-- CHECKPOINT21N_U_B_RECOVERED_COINBASE_BINDING_20260902 -->
## 2026-09-02 — Recover completed source artifact after post-collection manifest failure

Accepted: a collection run whose source requests and deterministic derived artifact
completed before a manifest-finalization infrastructure failure may be recovered only
when the failed manifest remains unchanged, runtime evidence establishes pre-failure
completion, and the derived artifact passes its exact frozen offline validation and
hash check.

For U-B, do not issue redundant Coinbase requests solely to obtain a completed manifest.

<!-- CHECKPOINT21N_V_CONTINUOUS_NON_EVALUABLE_CLOSEOUT_20260902 -->
## 2026-09-02 — Close continuous v1 as non-evaluable structural-universe mismatch

Accepted: `kxbtcd_candidate_e_continuous_convergence_reentry_v1` is permanently
`CLOSED_NON_EVALUABLE`.

Reason: zero of 17,550 frozen structural-market evaluations were evaluable, yet the same
full-ladder replay contains 45 two-sided tickers and more than one million valid
two-sided reconstructed states.

The five statistical structural roles are therefore not automatically a valid execution
universe. Do not rescue v1 by post-hoc rank expansion or threshold tuning.

A future strategy version may use a different liquidity-aware market universe only after
an outcome-blind causal universe design is predeclared. First test whether observed
liquidity is spot/ATM-relative.

<!-- CHECKPOINT21N_W_SPOT_ATM_LIQUIDITY_GEOMETRY_20260902 -->
## 2026-09-02 — Accept spot/ATM-relative liquidity geometry as exploratory architecture evidence

Accepted: July 10 outcome-blind evidence supports using contemporaneous causal
BTC spot / ATM as the organizing variable for future KXBTCD execution-universe
research rather than fixed event-wide quantile roles.

Not accepted yet: an exact v2 rank envelope, nonstructural Candidate-E validity,
or any profitability claim.

Continuous v1 stays permanently closed and may not be rescued by changing its
market universe. Any future liquidity-first universe must be a separately
versioned strategy predeclared before scoring/economics.

<!-- CHECKPOINT21N_X_SPOT_RELATIVE_V2_PREDECLARATION_20260902 -->
## 2026-09-02 — Predeclare liquidity-first spot-relative Strategy V2

Accepted new strategy version:
`kxbtcd_candidate_e_spot_relative_liquidity_convergence_reentry_v2`.

The tradable universe is causal ATM±5 numeric strike ranks, clipped at ladder
boundaries, maximum 11 markets. This is a new version; continuous v1 remains
permanently closed and is not repaired.

Candidate E remains exactly frozen. Nonstructural scoring is an explicit domain
extension and must pass a fixed post-Champion-Final fresh validation gate before
being treated as generalized predictive evidence.

Fresh targets are fixed to 24 August 19/21/23/25/27/29 hourly events at
17/18/19/20 UTC with no replacements. Source adequacy must pass before outcomes.
Fresh strategy economics require a later separately frozen single policy.

No network collection, purchases, outcomes, or execution occur in 21N-X.

<!-- CHECKPOINT21N_Y_A_V2_IMPLEMENTATION_FREEZE_20260902 -->
## 2026-09-02 — Freeze V2 dynamic-universe simulator before nonstructural scoring

Accepted implementation fingerprint:
`b8f66b2f392df2c8711e7d6e25e64c54921b16f8f7866c243a6375aaec778949`.

The dynamic decision clock treats source-segment start as an availability/top-book
transition, recomputes ATM at every causal Coinbase minute boundary, and ignores
outside-window/deep-book-only changes for entry decisions.

Historical replay optimization is accepted: validate all 623 source identities,
precompute the causal ATM±5 ticker union, and reconstruct only that union. This
does not alter which markets may be selected.

All execution mechanics below market-universe selection continue to reuse frozen
21N-R primitives. No real July 10 nonstructural Candidate-E evidence was exposed
during implementation freeze.

<!-- CHECKPOINT21N_Y_A1_QUANTITY_TRANSPORT_AMENDMENT_20260902 -->
## 2026-09-02 — Canonicalize tiny snapshot quantity residue at V2 execution boundary

Accepted narrow transport repair: preserve frozen replay exactly, but before V2
decision/execution use canonicalize a reconstructed quantity to nearest 0.01
only when absolute residue is <=1e-9. Residue >1e-9 remains fail-closed.

Reason: exhaustive diagnostics found 763,392 snapshot quantities with floating
serialization residue, all within 1e-9 of 0.01, while all 5,644,964 paid deltas
were exact-grid.

The IOC 0.01 quantity invariant is not relaxed. No strategy/model/economic rule
changes.


<!-- CHECKPOINT21N_Y_A2_MEMORY_STORAGE_AMENDMENT_20260902 -->
## Checkpoint 21N-Y-A2 — memory/storage amendment

The Y-A1-amended Y-B attempt failed with MemoryError in
VerifiedSegmentTimeline.__post_init__ while canonicalize_timeline_map was
constructing a second in-memory timeline map. The user later interrupted the
foreground command with Ctrl+C. The traceback occurs before this attempt's
policy loop. It did not write a completed path artifact; settlement outcomes and
strategy P&L remain unopened. Earlier Y-B scoring exposure remains recorded.

Y-A2 fingerprint: `f7a590cb0f8415e3330fa82077d16b6b93105717f573e69e8580a3f3ac1ffe03`.

The repair stages replay states in SQLite one ticker at a time, retains the
original reconciliation/delta functions, performs the same last-write-wins
millisecond collapse and raw-state compression, then applies exact Y-A1
quantity normalization. Raw sources and frozen Y-A/Y-A1 files are preserved.
Disk queries preserve right-continuous lookup, full-depth liquidation changes,
and verified-segment availability. The policy function body is AST-identical
to Y-A; only the decision-clock state scan uses indexed disk reads.

Completed ticker caches are bound to raw snapshot, replay, paid-shard, and
amendment hashes. Cache corruption or changed identities stop the run. An
interruption retains sealed tickers and removes only the active temporary
build when cleanup succeeds. An orphan cache or stale run lock requires
inspection, never silent acceptance. Atomic final output refuses a different
existing artifact.

Default runner mode prepares caches only. `--simulate` explicitly requests
all 60 frozen policies after complete preparation; partial-ticker preparation
cannot score. A 15-second heartbeat reports the current stage.

This is an implementation repair, not a strategy retune or successful Y-B
result. Candidate E, ATM+/-5, thresholds, fees, quantities, latencies,
liquidation/re-entry rules, fresh-evidence gates, and execution authorization
remain unchanged. N=4 July 10 events remain development/mechanics evidence.

Local synthetic verification covers exact replay+quantity equivalence,
same-millisecond cuts, source gaps, normalization duplicates, clock equivalence,
YES/NO IOC paths, partial/missed fills, liquidation, re-entry, cache integrity,
interruption/resume, and atomic outcome-blind output. It is not a real-data
completion claim. The full Windows suite is required by safe closeout.

Next after A2 closeout: bounded preparation with `--max-tickers 1`, inspect
resource behavior, then prepare the remaining cache. Score only through a
separate explicit `--simulate` invocation after preparation succeeds.

Accepted storage choice: on-disk timestamp staging and immutable sealed per-ticker caches. Memory is proportional to the current ticker source/audit rows plus current books, not all reconstructed full-depth states; this is not a fixed whole-process memory guarantee. Disk space and runtime remain data dependent.


<!-- CHECKPOINT21N_Y_A3_REPLAY_PRECISION_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A3 replay precision repair

User's Y-A2-backed Y-B run completed: 47 caches and 60 outcome-blind policy paths,
SHA256 21dd58066b040f8bc897815f722cad9bb90b0ff6b9a6d18d6e9416279c85bc9f.
This supersedes the earlier INCOMPLETE run status, but its premature exit-monitoring
boundaries are implementation-affected. Preserve the original result.

The uploaded 25ms diagnostic (SHA256
47caf2f93c736538db9a896a469f6a25fcdb247d2e67e89cf538675e4c8eeac5) reproduces
snapshot residue leading to a -2E-14 reconstructed balance. Normalize snapshot
quantities within 1e-9 of 0.01 before replay, then retain exact paid deltas and
strict reconciliation. A separate additive adapter, source-bound caches and output
path version this semantic correction. Original frozen replay, model and strategy
files remain unchanged. Real gaps still stop monitoring.

Correction: all nine normalized cut combinations are numerically executable,
but only cut (1,1) reconciles exactly. Both adjacent control pairs still pass.
The roughly 33-minute discontinuity remains unresolved until full source re-audit.

Implementation and local regression prepared; canonical Windows tests, safe closeout,
full cache rebuild and revised paths pending. See
KXBTCD_CANDIDATE_E_V2_REPLAY_PRECISION_AMENDMENT.md for exact evidence, rule,
failure modes and paths. Next: install/validate Y-A3; safe closeout then prepare
new caches with materialize_kxbtcd_candidate_e_v2_paths_replay_precision.py.
Review coverage_full.json before --simulate. Outcomes/P&L stay unopened; n=4
remains exploratory mechanics evidence. No execution authorization changes.

Y-A3 amendment fingerprint: `4c3e7ea2b730f548d9be5640602d8b81551ac647f7a09ea31051a61db6ff6127`. Assistant focused verification: **60 passed in 2.98s** (Python 3.12/Linux); Windows full suite pending.


<!-- CHECKPOINT21N_Y_A3_WINDOWS_FOCUSED_VALIDATION -->
## Checkpoint 21N-Y-A3 — Canonical Windows focused validation

User-reported canonical terminal evidence:
- replay precision amendment validator: PASS;
- fingerprint: 4c3e7ea2b730f548d9be5640602d8b81551ac647f7a09ea31051a61db6ff6127;
- frozen parents: unchanged;
- focused regression: 60 passed in 7.54s;
- git diff --check: PASS (no output);
- strategy: NOT RUN; settlement outcomes: NOT ACCESSED; orders: 0.

PowerShell blocked the downloaded unsigned validation wrapper before execution.
The user ran its Python validator, pytest and Git checks directly without changing
the execution policy. This is a wrapper-loading issue, not a replay/test failure.

The ZIP was apparently extracted into the repository root before the guarded
installer ran. Closeout preparation verifies the exact delivered files, backs up
extraction leftovers outside the repository, restores README only if it exactly
matches the bundle README, and archives the standalone inspector for retention.
No arbitrary untracked files or project edits are discarded.

The 60 focused tests are accepted. Full-suite validation, commit/push and receipt
are handled by the existing safe closeout engine; this entry does not claim they
have completed. After successful closeout, prepare the new Y-A3 caches and review
coverage_full.json before running the 60 revised outcome-blind scenarios. The
full-data rebuild, larger-gap diagnosis, revised paths and P&L remain pending.


<!-- CHECKPOINT21N_Y_A3_EOF_FORMAT_CLOSEOUT_REPAIR -->
## Checkpoint 21N-Y-A3 — Precommit formatting correction

The first safe closeout attempt passed the source registry and the full canonical
Windows suite: **1302 passed, 22 subtests passed in 57.77s**. After staging, Git's
whitespace check rejected one additional blank line at EOF in
materialize_kxbtcd_candidate_e_v2_paths_replay_precision.py (line 297). The earlier
unstaged diff check had not inspected this new untracked file. Closeout stopped
before a checkpoint commit or push; its helper unstaged the approved files.

The correction removes exactly that single trailing blank line. The runner's
Python AST is identical. No model, strategy, replay rule, source binding, quantity
normalization tolerance, fee, execution authorization or outcome firewall changes.

Old uncommitted amendment fingerprint (superseded for formatting only):
4c3e7ea2b730f548d9be5640602d8b81551ac647f7a09ea31051a61db6ff6127
Current amendment fingerprint:
82c4d05994cf97c723672b82428a7a139e20f96ae5aeea622e6dfaf1429a1370
The config pins the corrected runner hash, and the validator pins the new config
fingerprint. Its normalized validator-template hash is unchanged. Original parent
freezes remain intact; no corrected cache or path has been generated under either
Y-A3 fingerprint. Full closeout is retried through the existing engine and records
its own fresh validator/test evidence in the managed receipt.

Next after successful closeout: prepare Y-A3 caches and inspect coverage_full.json
before revised outcome-blind strategy paths. Settlement outcomes/P&L remain closed.

## 2026-09-03 — Checkpoint 21N-Y-A4 snapshot consistency repair and coverage gate

This entry supersedes earlier statements that the Y-A3 caches and paths were still
pending. Y-A3 closed at checkpoint 35b778a4f68d7d221536358599683706019230d8 and
receipt 1116a023cac865a9aeac13db041e710e4632395e; the canonical Windows suite passed
1302 tests plus 22 subtests, with clean synchronized main. The completed 47-ticker
coverage hash is 5b78812350bbcd3cea77f9c109dac2cce636de9577426edbaf523179859da1ab;
the completed 60-scenario outcome-blind path hash is
3b1bfadd61f003343d385fc1f62b6192ce5b53fda87d3f1977d84f604ebb4780.

The comprehensive forensic report hash is
a9bfe9d389611b192a186024c1301563d71bdcd649a891401a223434c03bd188. It reproduced
748 failures (236 negative-resting-size failures, 512 snapshot mismatches).
125 isolated-snapshot endpoint experiments and 15 ordering cases support further
review, not blanket acceptance. Large clusters remain unresolved.

Y-A4 fingerprint: 31df5185c3840092eaae09f82fd0139cf46db37dc5bfd9bd067d6dcfa758c92a.
The frozen specification is KXBTCD_CANDIDATE_E_V2_SNAPSHOT_CONSISTENCY_AMENDMENT.md.
Ordering and isolated-snapshot quarantine are separate rules; both require a unique
consistent exact local replay. Quarantine requires five strictly increasing times,
verified outer controls and at most 120 seconds of context. Overlapping proposals
are rejected; long and unsupported cases remain gaps. Source labels alone do not
establish authority. All proposals originate from the unchanged Y-A3 view.

Local isolated validation: 79 focused tests passed, including 19 new tests and the
60 existing precision/memory tests. Eight bounded real-source fixtures cover the
six earlier/later repair examples and both unresolved clusters. The coverage-runner
file-flow test used synthetic source/cache envelopes around three real extracts;
it is not a full 47-ticker execution on the user's PC. Canonical Windows closeout
and the real-data Y-A4 coverage gate remain pending until their terminal evidence.

No model refit, strategy rule changes, new execution cache, strategy rerun,
settlement outcomes, strategy P&L, or orders were produced by this amendment.

Decision: accept a strictly bounded isolated-snapshot rule based on exact surrounding
replay evidence, including same-source conflicts. Retain the prior two-minute bound
and strict timestamps instead of expanding the rule to every successful endpoint
experiment. Record quarantine in a separate index view while retaining original raw
snapshots. Source sequence drops remain diagnostic metadata, not an exclusion rule.

Decision: export required cut chains and stop at an incremental coverage gate.
Do not silently reuse the old cache builder with different snapshot inputs. A later
implementation must reconcile boundary-cut choices with its chronological state
stream before any strategy path is regenerated. Remaining clusters and long gaps
are preserved, and no financial result is used to choose among repair variants.

<!-- CHECKPOINT21N_Y_A5_REPAIR_CACHE_IMPLEMENTATION_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A5 repair-cache decisions

Decision: freeze the maximum currently supported repair set as **203 of 748** failed
Y-A3 adjacent pairs. The 545 unsupported pairs remain explicit hard segment
boundaries. Do not infer or impute through them.

Decision: compose the 105 A4 operations, three supported A5 tied-outer-control
quarantines and two supported joint same-timestamp orderings because their original
repair contexts are pairwise disjoint. The frozen plan contains 110 operations and
93 quarantined snapshots; no iterative repair discovery is permitted during cache
construction.

Decision: implement a new additive repair-aware cache builder instead of modifying
the frozen Y-A3 replay/disk modules. The builder must preserve Y-A3 snapshot
normalization and use each repair's exact snapshot order and exact cut chain.

Decision: make A4's paid-row authority explicit in executable materialization:
`timestamp`, then `sequence`, then original `source_row`. Do not rely on incidental
Parquet stability for equal timestamp/sequence rows.

Decision: every changed adjacency must independently reconstruct its endpoint
snapshot with zero comparison tolerance. A pinned plan is permission to test a
specific path, not permission to bypass endpoint verification.

Decision: forbid any repair context from crossing an undeclared parent failed pair.
Any unsupported residual failure must remain a segment boundary.

Decision: the repair-cache runner is preparation-only and has no simulation flag.
It requires the implementation files to be committed before real-data cache
construction. Build one ticker first, audit it, then consider all 47. Strategy paths
remain closed until full repaired-cache validation.

<!-- CHECKPOINT21N_Y_A6_REPAIR203_PATH_READINESS_20260903 -->
## 2026-09-03 — Checkpoint 21N-Y-A6 repaired-path runner decisions

Decision: do not reuse the old Y-A3 `--simulate` command for post-repair evidence.
That runner is bound to the old replay-precision cache namespace. Use a new additive
runner bound exclusively to the sealed repair-203 caches.

Decision: before any repaired policy scoring, validate all 47 cache seals and
require exact agreement with the frozen repair coverage artifact
`b8b535d6131f01250690d1015861a4737fd0cd4888251f1cbf4941eb7dceeab0`.

Decision: require the repaired runner to prove that the dynamic ticker union and
ordered 60-scenario event/threshold/latency grid are unchanged from the superseded
Y-A3 outcome-blind artifact.

Decision: compare scenario identity in the simulator's canonical JSON
representation. Decimal thresholds are serialized by `jsonable()`; validator
comparisons must not treat equivalent Decimal and JSON-string representations as
different policy specifications.

Decision: the repaired 60-path run remains outcome-blind. Settlement outcomes and
strategy P&L stay closed until the resulting paths are inspected for residual
monitoring censorship.

<!-- CHECKPOINT21N_Y_C_PNL_FREEZE_DECISION_20260903 -->
## Checkpoint 21N-Y-C — July-10 P&L evaluation contract frozen before outcomes

Accepted decision:
- Freeze repaired outcome-blind path SHA-256 `cd49f0c72548c7715f1025a828b7af1321c02139af926e970e7816945bd69daa` and censorship refinement SHA-256 `e4722f37bc001e40b84654d230dccf914f13bf98430aef833fd9efb1e6767439`.
- Preserve all 60 scenarios as 15 threshold/latency settings x 4 events; path identifiability is 27 EXACT / 33 CENSORED.
- EXACT paths may receive point historical P&L from frozen synthetic-fill cash plus authoritative binary settlement only when an exact settlement fallback remains open.
- CENSORED paths receive no point estimate; freeze a universal structural interval of **[-$2.0700, +$2.00] per scenario**.
- The bound uses at most two 1-contract filled entries, at most four filled IOCs, and maximum per-fill fee $0.0175 under the frozen 7% fee formula.
- For each policy setting, retain all four events and classify ROBUST_POSITIVE iff event-equal mean lower bound > 0, ROBUST_NEGATIVE iff upper bound < 0, otherwise INCONCLUSIVE.
- July 10 is development/mechanics evidence, not an advancement gate. Outcome-driven policy selection or retuning is forbidden.
- Settlement scoring fails closed unless the Kalshi market is finalized, binary, non-provisional, result yes/no, settlement value exactly 0/1 consistent with result, and settlement_ts populated.
- Future outcome access is minimum-necessary and raw-first: only fallback tickers required by EXACT scenarios.

This freeze accessed no outcomes, calculated no P&L, reran no strategy, made no network requests, and placed no orders.

<!-- CHECKPOINT21N_Y_D_SETTLEMENT_SCORER_IMPLEMENTATION_20260903 -->
## Checkpoint 21N-Y-D — minimal settlement reader/scorer implementation

Accepted implementation design:

- Keep the already-frozen 27 EXACT / 33 CENSORED classification unchanged.
- Derive the future settlement request set mechanically from EXACT scenarios whose
  liquidation status is `EXIT_MISSED_SETTLEMENT_FALLBACK`.
- Do not independently request outcomes needed only by CENSORED scenarios.
- If the same market ticker is needed by both an exact and censored scenario, one
  market-level outcome may be incidentally known, but the censored scenario still
  receives no point P&L.
- Use only the public Kalshi historical-market endpoint and preserve every HTTP
  response in the existing append-only raw HTTP archive before normalization.
- Require finalized binary settlement, populated settlement timestamp, yes/no
  result, 0/1 settlement value consistent with that result, and non-provisional
  state; otherwise fail closed.
- Cache each normalized exact-required settlement immediately after its raw
  response is safely archived, so a partially interrupted run can resume without
  re-requesting outcomes already opened.
- Score EXACT paths with the frozen accounting module; keep CENSORED paths at the
  frozen `[-2.0700, 2.00]` interval.
- Report all 15 threshold/latency settings across all four events without ranking,
  selecting, or retuning a policy from July-10 outcomes.
- Real `--collect` remains blocked until this implementation checkpoint is itself
  committed and pushed through the safe closeout workflow.

This checkpoint is implementation/readiness only: outcomes not accessed, P&L not
calculated, strategy not rerun, network requests 0, orders 0.

## Checkpoint 21N-Y-D1 — historical-market list transport amendment

Accepted transport amendment after the first authorized settlement attempt
failed closed with HTTP 404 on:

`GET /historical/markets/KXBTCD-26JUL1015-T63699.99`

The failed response was raw-preserved by the existing raw-first HTTP client.
No normalized settlement cache, settlement manifest, P&L report, strategy rerun,
or order was produced.

Current official Kalshi documentation presents two relevant routes: the singular
historical-market endpoint and the historical-markets list endpoint. Historical
cutoff guidance directs archived-market reads to the list endpoint, which
supports a `tickers` filter.

Use:
`GET /historical/markets?tickers=<exact ticker>`.

One exact ticker is requested per call for resumability. The response must
contain exactly one market object and its ticker must exactly match the request.
Zero matches, multiple matches, or ticker mismatch fail closed.

No evaluation, censorship, accounting, policy-selection, or execution rule
changes.

## Checkpoint 21N-Y-D2 — partition-aware settlement transport

The D1 historical-list request returned HTTP 200 with zero markets for
`KXBTCD-26JUL1015-T63699.99`.

Root cause: Kalshi partitions settled markets between a recent/live tier and an
older historical tier. "Settled" does not imply "historical". Official
historical-data guidance states that markets older than the moving settlement
cutoff migrate to historical storage while newer markets remain on normal
market endpoints.

Frozen exact-ticker resolution is therefore:
1. query `/markets?tickers=<exact ticker>`;
2. if exactly one exact match exists, use it;
3. only if the live/recent response contains zero markets, query
   `/historical/markets?tickers=<same exact ticker>`;
4. require exactly one exact match there or fail closed.

Every HTTP response remains raw-preserved. Settlement validation remains
unchanged: binary, REST `finalized`, populated `settlement_ts`, non-provisional,
yes/no result, and exact 0/1 settlement value consistent with the result.

No strategy, censorship, accounting, policy-ranking, or execution rule changes.

<!-- CHECKPOINT21N_Y_E1_SETTLEMENT_SENSITIVITY_PREDECLARATION_20260903 -->
## Checkpoint 21N-Y-E1 — settlement sensitivity predeclaration

Accepted a post-outcome exploratory sensitivity program without changing the
official July-10 result: 27 EXACT / 33 CENSORED / 15 INCONCLUSIVE.

Frozen analyses:
1. Preserve all 27 exact official P&Ls; for the 3 liquidation-only censored
   scenarios, preserve known cash and settle only known residual quantity.
2. For all censored scenarios, allow descriptive observed-trace terminal values,
   but do not call selection/re-arm-censored traces complete strategy P&L.
3. Evaluate each of the 93 observed fills independently to settlement as an
   entry-quality diagnostic; do not sum these as a causal hold-all policy.

The exact future settlement ticker universe is frozen from the outcome-blind
path before any additional outcome request. No policy ranking, retuning, or
execution is authorized.

<!-- CHECKPOINT21N_Y_E2_SETTLEMENT_SENSITIVITY_EVALUATOR_20260903 -->
## Checkpoint 21N-Y-E2 — settlement sensitivity evaluator

Accepted the implementation design for the E1-predeclared post-outcome sensitivity.

E2 reuses the already-validated D2 live/recent-first, historical-fallback settlement
transport. It may request only the 12 tickers frozen by E1 and preserves every new
HTTP response raw before normalization.

Scoring rules remain exactly separated:
- 27 exact scenarios use the official frozen P&L unchanged;
- 3 liquidation-only censored scenarios preserve known cash and settle only known
  residual quantity, yielding coherent sensitivity point values;
- 30 scenarios with selection/re-arm censorship remain incomplete at strategy
  level and retain the universal interval for hybrid aggregation;
- all censored observed traces may be terminalized descriptively;
- each of 93 observed fills may be evaluated independently to settlement, but the
  entry rows are not summed as a causal hold-all strategy.

Policy ranking/selection, retuning, strategy rerun, and execution remain forbidden.
Real additional settlement access is blocked until E2 is safely closed/pushed.

<!-- CHECKPOINT21N_Z_A_PROSPECTIVE_WEEK_PREDECLARATION_20260903 -->
## Checkpoint 21N-Z-A — prospective one-week strategy freeze

Freeze Candidate-E Champion-Final unchanged with primary net edge `.02`, selected mechanically as the midpoint of the already-frozen threshold grid and not from July-10 P&L. Retain V2 T-55 to T-2 dynamic ATM-window, convergence exit, and maximum one re-entry after complete first exit plus exact V2 re-arm. Freeze a non-extendable 168-hour prospective cohort. Remove the artificial latency grid from the primary prospective design and measure live internal timing instead. Production remains read-only in this checkpoint.

<!-- CHECKPOINT21N_Z_B_LIVE_COLLECTOR_20260903 -->
## Checkpoint 21N-Z-B — prospective live collector architecture

Use Kalshi's authenticated production `orderbook_delta` WebSocket for prospective
KXBTCD path capture. Subscribe to the entire selected event ladder so ATM-window
changes do not create subscription blind spots. Preserve every raw frame before
transformation.

Treat any WebSocket sequence discontinuity as a hard validity failure for the
whole subscription. Request documented `get_snapshot` recovery and block all
Candidate-E signals until all subscribed markets have fresh snapshots.

Z-B is smoke-only. It does not arm the 168-hour cohort and adds no order path.

<!-- D_021N_ZB_LIVE_SCHEMA_REPAIR_20260903 -->
## D-021N-ZB-R1 ? Live Kalshi schema normalization

Accepted after direct live production evidence:

- Keep REST discovery query `status=open`.
- Require returned open-market lifecycle rows to be `status="active"`.
- For `orderbook_snapshot` only, an omitted `yes_dollars_fp` or `no_dollars_fp` property means an empty side.
- Do not generalize this normalization to explicit null or malformed values; those remain fail-closed errors.
- Preserve full-ladder subscription and authoritative-snapshot recovery semantics.

Rationale: these rules match directly observed live Kalshi behavior while preserving strict validation for malformed data.

<!-- D_021N_ZB_ANCESTRY_GATE_20260903 -->
## D-021N-ZB-R2 ? Closed-checkpoint authorization uses Git ancestry

After Z-B has been safely closed, later legitimate checkpoints must not disable read-only network smoke merely because `LAST_CHECKPOINT_CLOSEOUT.json` points to a newer checkpoint.

Accepted rule:
- require closed Z-B receipt `e82a3f4957be73db39cfdb36617e4ead3bbb78bf` to remain an ancestor of current HEAD;
- Git return code 0 = accepted ancestry;
- return code 1 = not an ancestor;
- unexpected Git errors fail closed.

This changes checkpoint-lifecycle authorization only. It does not authorize trading or change Candidate-E strategy semantics.

<!-- D_021N_ZC_PRODUCTION_RUNTIME_ARCHITECTURE -->
## D-021N-ZC-01 ? Production-shaped runtime architecture

Accepted architecture fingerprint:
`3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`

Freeze the permanent Candidate-E runtime boundary as:
Coinbase public matches+heartbeat WS -> exact completed-minute builder ->
Kalshi full-ladder WS -> frozen Candidate E/strategy -> durable state/risk boundary.

Use a separate read-only dashboard and a separately authorized future execution
worker. The strategy runtime may never directly call Kalshi write endpoints.

Deployment target is Linux cloud VM + Docker Compose. AWS us-east-1 is only the
first connectivity benchmark target; Kalshi hosting location is not assumed.

Current execution mode remains disabled and RISK_POLICY authorization is unchanged.

<!-- CHECKPOINT21N_Z_D_COINBASE_RUNTIME_RECOVERY_20260904 -->
## Checkpoint 21N-Z-D ? Coinbase runtime/recovery decisions

Accepted for the continuing read-only production-runtime implementation:

- Coinbase `matches + heartbeat` general sequence deltas remain diagnostic;
  BTC-USD trade-ID plus heartbeat continuity is the primary missing-match
  signal.
- A REST recovery may not paginate older until the unpaginated latest REST
  page has reached the frozen WebSocket recovery target.
- Current bounded latest-visibility validation policy is 10 attempts spaced
  0.5 seconds apart; exhaustion remains fail-closed.
- Recovery coverage requires the exact known pre-gap boundary and exact target
  to be covered by the authoritative REST page sequence.
- Cross-transport WS/REST corroboration requires exact trade ID, numeric
  price, numeric size, side, <=1 us timestamp difference, and identical UTC
  minute assignment.
- The <=1 us envelope is an intentionally conservative acceptance bound based
  on observed evidence, not a claim about Coinbase's universal timestamp
  behavior.
- Cross-transport corroboration never overwrites the first accepted canonical
  trade record.
- Same-transport duplicates continue to require exact evidence.
- Any timestamp discrepancy that changes UTC-minute assignment fails closed.

Detailed evidence:
`docs/KXBTCD_CANDIDATE_E_COINBASE_RUNTIME_RECOVERY_VALIDATION.md`

<!-- CHECKPOINT21N_Z_E_A_RESTART_DURABLE_DESIGN_20260904 -->
## Checkpoint 21N-Z-E-A — Restart/durable-state design decisions

Design fingerprint: `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`

Accepted:
- every process starts signal-disabled;
- process restart inside an already-armed cohort is operational recovery, not a new cohort;
- cohort arm/end times never move;
- downtime is never replaced or backfilled;
- exact arm Git commit must match on restart;
- SQLite uses WAL + `synchronous=FULL`;
- every process gets a new runtime session ID and production Linux `boot_id`;
- old Coinbase freshness/continuity and old Kalshi books/SID/sequence state are never restored;
- fresh Coinbase continuity and exact current Kalshi full ladder are mandatory before `READY_READ_ONLY`;
- every process opens new raw segments;
- crash-damaged evidence becomes an explicit gap rather than a reconstructed live decision;
- current phase persists no order/fill/position state;
- execution remains disabled.

Next: implement exactly this contract in Z-E-B.

<!-- CHECKPOINT21N_Z_E_B1_SQLITE_CORE_20260904 -->
## Checkpoint 21N-Z-E-B1 — SQLite durable-core implementation decisions

Accepted implementation behavior under frozen design `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`:

- B1 may open only explicitly noncanonical validation databases;
- B1 refuses paths under `data/prospective/candidate_e`;
- B1 requires `validation_mode=True`;
- the exact seven frozen tables are created;
- SQLite must report `journal_mode=wal` and numeric `synchronous=2` (`FULL`);
- every process start creates a new runtime session ID even on the same boot;
- monotonic time may reset across sessions but cannot regress inside a session;
- a prior session left `RUNNING` is changed to `UNCLEAN_DETECTED` by its
  successor;
- unclean process-gap start is the prior durable heartbeat, not a fabricated
  exact crash timestamp;
- database constraints keep `canonical_backfill_allowed=0`;
- B1 contains no canonical arm path, source connection, signal path, or
  execution state.

<!-- CHECKPOINT21N_Z_E_B2_RECONCILIATION_20260904 -->
## Checkpoint 21N-Z-E-B2 — Identity/raw reconciliation decisions

Accepted under frozen restart design `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`:

- a restart-session raw segment is create-exclusive and may never append to a
  prior process's segment;
- every raw record carries runtime-session ID, segment ID, one-based record
  index, payload hash, and exact line hash;
- decisions reference exact raw records rather than only source timestamps;
- synthetic validation decision + source-watermark advancement commit in one
  SQLite transaction;
- pending decisions become `VERIFIED` only when every referenced raw record is
  present with matching identity/hash;
- missing/damaged referenced evidence becomes `RAW_EVIDENCE_GAP`;
- raw evidence without a committed decision remains raw evidence only and is
  never converted into a backfilled live decision;
- partial trailing raw bytes are preserved byte-for-byte, hashed, and never
  silently truncated;
- B2 arm-manifest handling is noncanonical validation-only;
- exact arm Git identity remains mandatory;
- Linux parent-directory fsync for real arm creation remains required later and
  is not claimed by Windows validation;
- canonical prospective paths, cohort arm, signals, and execution remain
  prohibited.

<!-- CHECKPOINT21N_Z_E_B3_RESTART_GATE_20260904 -->
## Checkpoint 21N-Z-E-B3 — Restart gate-state implementation decisions

Accepted implementation behavior under frozen restart design `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda`:

- the runtime starts `STARTUP_DISABLED`;
- the exact frozen state set is implemented without additional actionable
  states;
- fail-closed readiness precedence is identity -> cohort -> durability ->
  clock -> Coinbase -> Kalshi -> strategy reconciliation;
- any fatal frozen condition or execution-mode enablement resolves to `FATAL`;
- a known fixed cohort end resolves to `COHORT_ENDED`;
- unknown clock health is blocking;
- `abs(clock_offset_ms) <= 250` passes the clock gate;
- `abs(clock_offset_ms) > 250` blocks;
- `READY_READ_ONLY` requires every frozen gate to pass;
- readiness only permits a fresh signal recomputation; it never restores or
  reuses a prior signal;
- `READY_READ_ONLY` -> blocked immediately removes eligibility and records a
  no-backfill `PROSPECTIVE_OBSERVATION_GAP`;
- recovery requires fresh full gate reevaluation and creates a new readiness
  generation;
- B3 Coinbase/Kalshi readiness is injected offline only;
- no cohort arm, Candidate-E signal computation, or execution path is added.

<!-- CHECKPOINT21N_Z_E_B4_SOURCE_READINESS_20260904 -->
## Checkpoint 21N-Z-E-B4 — Current-source readiness decisions

Accepted under frozen restart design `40496ce5a4274367c8098dd90d0f0c74d2bae24ba91aaab1e95d14356e0ccdda` and runtime architecture `3061000e53226bcb9f87f61469b42790bc3c2db176f064df95d32d62594891e7`:

- production boot identity is Linux `/proc/sys/kernel/random/boot_id`; Windows boot identity is never inferred for production readiness and may be supplied only as explicit synthetic validation evidence;
- production clock readiness is derived from chrony tracking and remains fail-closed when evidence is missing, malformed, or beyond the frozen absolute 250 ms threshold;
- Coinbase readiness is bound to both runtime session identity and WebSocket connection generation; a builder from a prior connection in the same process cannot authorize readiness;
- Kalshi book correctness and transport liveness are separate gates;
- Kalshi book correctness still requires authoritative full-ladder snapshot state, current generation, exact book-set identity, and uninterrupted sequence state;
- Kalshi transport liveness is proven by current-connection Ping/Pong evidence, not by an arbitrary assumption that a quiet market must emit deltas;
- keep the frozen client Ping interval at 15 seconds and Pong timeout at 5 seconds; derive a maximum accepted Pong age of 20 seconds from those values rather than tuning a new trading threshold;
- missing/stale Pong blocks Kalshi readiness, but Pong never heals `resync_required`, a sequence gap, or stale/wrong-generation book state;
- old-session and old-connection source state is rejected and cannot seed a new readiness generation;
- B4 remains read-only/offline and does not arm the cohort, create the canonical prospective DB, compute Candidate-E signals, or add execution behavior.

B4-R2 was a fixture-only repair to match the committed six-field `LadderMarket` dataclass; it did not alter runtime readiness semantics.

<!-- CHECKPOINT21N_Z_E_B5_R1_CREDENTIAL_BOUNDARY_20260904 -->
## Checkpoint 21N-Z-E-B5-R1 — Credential-boundary decisions

Accepted before bounded live restart testing:

- `request_identity` is not an arbitrary persistence surface;
- raw-journal request metadata uses an explicit fail-closed allowlist;
- credential/header/signing names and credential-like values are rejected
  before serialization;
- nested request params receive the same sensitive-name/value checks;
- URLs stored as request identity may not carry user-info, query strings, or
  fragments;
- unknown top-level request metadata is rejected rather than copied;
- existing benign Coinbase runtime metadata is admitted only through explicit
  field/value contracts, not a generic relaxation;
- `phase` is exactly `latest_visibility` or `older_pagination`;
- `product_id` is exactly `BTC-USD`;
- Kalshi auth headers remain ephemeral direct connection inputs and must never
  be passed to raw-journal request metadata.

B5-R1-R2 is a compatibility repair, not a weakening of the credential
boundary. No cohort arm or execution authorization changes.

<!-- CHECKPOINT21N_Z_E_B5_R2_DECISIONS_20260904 -->
## B5-R2 accepted restart-source lifecycle decisions

1. WebSocket connection generation is a first-class current-state identity.
   Every Coinbase/Kalshi connect or reconnect receives a new positive
   generation.
2. A reconnect creates fresh source-state objects. Coinbase minute-builder state
   and Kalshi cache/subscription/sequence/Pong state are never inherited across
   connection generations.
3. Explicit transport disconnect revokes readiness immediately; the runtime
   does not wait for an application stale timer to expire.
4. Old-generation source objects are retained only as historical evidence and
   are ineligible to authorize current readiness.
5. Kalshi transport liveness and order-book exactness remain independent.
   Current-generation Pong cannot populate, repair, refresh, or heal book
   sequence state.
6. The frozen Kalshi keepalive contract remains 15-second client Ping /
   5-second Pong timeout.
7. B5-R2 live validation is deliberately signal-free. Connection/restart
   engineering is validated separately from Candidate-E economics.
8. The live run is accepted as bounded reconnect evidence only. It does not
   substitute for process-crash restart, host reboot, long-duration runtime,
   Linux clock/boot validation, or profitability evidence.

<!-- CHECKPOINT21N_Z_E_B5_R3_A_DECISIONS_20260904 -->
## B5-R3 process restart and strategy reconciliation decisions

1. Do not add a persisted strategy-state table in the current read-only phase.
2. Treat prior decision rows as audit evidence only, never actionable restart state.
3. Separate durability reconciliation from read-only strategy reconciliation.
4. Durability may PASS after missing raw evidence is permanently classified as
   RAW_EVIDENCE_GAP and excluded; fresh recovery is allowed.
5. Strategy reconciliation requires explicit neutral state and
   prior_signal_reusable=false.
6. Current ATM window, Candidate-E probability, signal selection and all source
   freshness must be rebuilt after restart.
7. B5-R3 implementation remains offline-first and execution-disabled.

Design fingerprint: `0623977817c055b5557296b6e9a58ea371c0ea680728c6a68a52a1c5abfdffea`.

<!-- CANDIDATE_E_MICRO_PRODUCTION_PATH_POLICY_20260904 -->
## Candidate-E micro-production roadmap decision

Accepted roadmap:

1. Keep current phase read-only while runtime/restart/order-risk safety is built.
2. Complete stable demo execution of the exact production-shaped path.
3. Make the first intended real-money step a separately predeclared and directly
   approved micro-production validation.
4. Define "$0.01 contract run" as one contract per order at a $0.01 purchase
   limit price on the selected side, plus fees and hard run-level caps.
5. Do not require a separate 168-hour read-only precursor unless explicitly
   reauthorized.
6. Do not silently increase price, size, duration, or exposure to force a fill.
7. Do not automatically scale after a successful micro-run.

Policy-path fingerprint:
`57e7e5c88bd296128927362119c0f3705d4be9ce5f0d8a13c1fd652ddd2e2677`.

<!-- CHECKPOINT21N_Z_E_B5_R4_A_DESIGN_20260904 -->
## Operational-safety completeness rule and B5-R4 design

Accepted:

- No single test may be treated as proof of every imaginable operational
  failure.
- Before micro-production, each known/predeclared operational category requires
  explicit passing evidence or remains a blocker.
- B5-R4 is a bounded two-process live read-only crash/restart probe.
- Process 1 is deliberately terminated uncleanly after reaching
  `READY_READ_ONLY`.
- Process 2 must start blocked, classify the old session, rebuild fresh
  Coinbase/Kalshi state under a new runtime session, and only then regain
  readiness.
- B5-R4 does not authorize execution and does not close later host-reboot,
  long-soak, or order/risk/demo operational categories.

- Initial readiness has a 300-second deadline. Timeout means measurement never
  starts and the attempt cannot qualify.
- Every run is bound to an atomic manifest containing Git, design, Docker-image,
  boot, duration, artifact-integrity, and terminal-classification identity.
- The free-disk formula is frozen before evidence:
  `max(10 GiB, ceil(1.5 * (24*C + 2*U) + 2 GiB))`, where `U` and `C` come from
  the accepted one-hour shakedown.
- Closed raw segments use verified lossless compression before raw deletion.
- The runtime container is non-privileged, has no Docker-socket/host-network
  shortcut, receives the Kalshi private key only as a read-only secret file,
  and must access real host chrony through a narrowly frozen control boundary.
- An implementation/image change after shakedown invalidates that shakedown.

Design fingerprint:
`17f4626e09c7231c0d65002d3e9f7f05d3046ccf054d59407619adea667aa0a9`.

<!-- CHECKPOINT21N_Z_E_B5_R4_C_KALSHI_LIVENESS_REPAIR_20260904 -->
## Decision — B5-R4 manual Pong misses defer to frozen B4 Pong-age policy

Accepted 2026-09-04.

B5-R4 must not introduce an independent immediate-fatal rule for a single
manual Pong timeout.

The frozen B4 Kalshi transport-liveness contract remains authoritative:

- Ping interval: 15 seconds;
- Pong timeout: 5 seconds;
- only a successful current-connection Pong refreshes liveness;
- missed Pong does not refresh liveness;
- no proven current-connection Pong remains blocked;
- latest proven Pong age <=20 seconds may remain live;
- latest proven Pong age >20 seconds is `KALSHI_PONG_STALE`.

B5-R4 manual Pings use unique attempt payloads and exist only to create
observable current-connection Pong evidence. They do not update order-book
state, heal sequence gaps, or create a second liveness policy.

Reason:
the first live B5-R4 successor received 9,955 fresh Kalshi application frames
but was terminated by one later manual Pong timeout while the frozen B4 age
contract had not necessarily expired.

<!-- CHECKPOINT21N_Z_E_B5_R5_A_AWS_LINUX_HOST_VALIDATION_20260904 -->
## B5-R5-A — AWS operational baseline decisions

Accepted 2026-09-04:

1. Use AWS `us-east-1` as the production-shaped hosting baseline.
2. Use physical AZ `use1-az4` for the current host; the account-local AZ label is
   `us-east-1c`.
3. Cross-cloud comparison is no longer a mandatory prerequisite. Reopen GCP,
   Azure, or another AWS placement only if measured AWS latency, jitter,
   reliability, capacity, or operational behavior is unacceptable.
4. This decision does not claim AWS is globally fastest or that Kalshi is hosted
   in the same region.
5. Keep the current production-shaped host SSM-administered with zero inbound
   security-group rules, no EC2 login key pair, and IMDSv2 required.
6. Keep repository access on this host read-only through a repo-scoped deploy key.
7. Do not populate the production host with Git-ignored historical
   outcome/research archives solely to satisfy historical integration tests.
   Production-host validation should distinguish source-contained/runtime tests
   from historical-artifact-dependent research tests.
8. The successful real Linux reboot plus application boot-ID/chrony adapters
   closes the `host_reboot_and_clock_boot_identity` operational category.
9. Do not infer long-soak stability, source-latency adequacy, execution safety, or
   profitability from this host validation.
10. Execution authorization remains read-only.

The frozen historical production-runtime architecture file is not rewritten by
this later operational deployment decision.

<!-- DECISION_B5_R5_A_R2_CLOSEOUT_UTF8_20260904 -->
## B5-R5-A-R2 — Explicitly decode checkpoint-closeout Git output as UTF-8

- Date: 2026-09-04
- Status: accepted
- Context: the Windows closeout helper inherited `cp1252` for text-mode
  subprocess decoding, while Git produced UTF-8 staged-diff output containing
  a byte not representable by that decoder.
- Decision: retain platform-default decoding for generic validator/test
  subprocesses, but require `encoding="utf-8"` for all commands routed through
  the closeout helper's Git wrapper.
- Reason: this fixes the observed Git-output boundary without globally changing
  unrelated subprocess semantics.
- Test evidence: focused closeout tests `28 passed`; real Git reproduction with
  `PYTHONUTF8=0` PASS; full repository `1619 passed, 22 subtests passed`.
- Self-modification boundary: because the engine and its test are protected
  safety-critical tooling, the repair was reviewed, validated, selectively
  staged, secret-scanned, committed, and pushed manually rather than
  self-certified.
- Consequence: normal future non-tooling checkpoints may again use the committed
  closeout helper without requiring the temporary `PYTHONUTF8=1` workaround.
- Scope: repository engineering only; no market-data, strategy, execution, or
  risk-policy change.

<!-- CHECKPOINT21N_Z_E_B5_R5_B_A_AWS_READ_ONLY_SOAK_DESIGN_20260904 -->
## B5-R5-B-A — Freeze the AWS read-only soak program

Accepted 2026-09-04.

- Use a dedicated production-shaped soak runner rather than stretching the
  5–300 second prospective smoke collector or the bounded B5-R4 restart probe.
- Run a 3,600-second shakedown before any 86,400-second canonical soak.
- Start each active-duration timer only after first `READY_READ_ONLY`, but never
  pause it for later source/clock blocked intervals.
- Use the same Docker Compose packaging for shakedown and canonical soak.
- Exercise hourly KXBTCD event rollover through fresh Kalshi generations.
- Use real Linux boot-ID and chrony evidence; synthetic clock evidence is
  prohibited.
- Preserve source-specific hourly raw segments before transformation, fsync at
  least once per second, and losslessly compress/hash closed segments.
- Freeze the final minimum-free-disk gate only after empirical shakedown
  bytes/hour are known.
- Treat correctly enforced source/clock blocking as safety-correct but still
  include the downtime in operational adequacy metrics.
- Run one controlled unclean process restart only after the full 24-hour
  continuous window.
- Keep Candidate-E signal computation, settlement outcomes, P&L, order intents,
  orders, and production writes out of this infrastructure soak.

Design fingerprint:
`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`.

This decision does not change `docs/RISK_POLICY.md` or execution authorization.

<!-- CHECKPOINT21N_Z_E_B5_R5_B_B_A_CLOCK_EVIDENCE_BRIDGE_20260904 -->
## B5-R5-B-B-A — Replace direct chronyd socket access with a host evidence bridge

Accepted design amendment pending checkpoint closeout.

Parent soak design fingerprint:
`715b55824746fe59467d7484599d1a92894e0810d5bc9be972d81577005c1ed6`

Amendment fingerprint:
`eaf9525f726f4beaad6f7f4bc3e3704534459a1033ec28a1c4656def7121813f`

AWS diagnostics disproved direct container use of the bind-mounted chronyd
control socket: both normal bridge networking and host networking returned
`506 Cannot talk to daemon`.

Use a host systemd publisher that records real `chronyc -n tracking`, real boot
identity, time-namespace identity, and monotonic capture time into an atomic
evidence file. Mount only that evidence directory read-only into the runtime
container.

The container must validate boot ID, time namespace, nonnegative monotonic age,
maximum age 5 seconds, publisher status, chronyc return code, and the existing
chrony tracking parser before clock readiness can pass.

The publisher and Docker runtime must be independent of the SSM terminal
lifecycle.

The closed B5-R5-B-A config/fingerprint is preserved unchanged. This amendment
changes only the chrony evidence transport and does not alter execution
authorization.

<!-- B5_R5_B_PROSPECTIVE_RESEARCH_DATA_ARCHIVE_20260904 -->
## B5-R5-B — Preserve a strategy-independent prospective research archive

Accepted 2026-09-04.

Prospective KXBTCD collection is a reusable research-data program, not merely
temporary input for the current Candidate-E strategy.

For every accepted runtime collection window:

- preserve the complete selected KXBTCD event ladder subscribed by the runtime,
  not only tickers the current champion would enter or score;
- preserve raw Kalshi order-book snapshots and deltas before transformation;
- preserve the independent Coinbase BTC-USD source evidence required to
  reconstruct the corresponding BTC state;
- retain source timestamps, local UTC receive timestamps, local monotonic
  timestamps, runtime/session identity, connection generation, sequence state,
  reconnect/recovery evidence, and integrity manifests;
- keep raw evidence immutable;
- retain gaps and recovery markers explicitly rather than silently treating a
  partially observed interval as complete;
- attach settlement labels later as separate derived evidence rather than
  modifying raw market-data files.

The same hourly lossless-zstd/hash/descriptor format frozen for B5-R5-B is the
initial canonical archival unit.

The archive must remain independent of Candidate-E decisions so that future
champion candidates can be researched against the same prospective market
history.

Newly accumulated data does not authorize automatic Candidate-E retraining.
Observed degradation first triggers diagnosis and a predeclared research
lifecycle. Any retraining/refit must separate development evidence from genuinely
untouched later validation evidence.

The AWS instance root volume is not accepted as the permanent long-term archive.
A durable off-host archival destination and verified transfer/retention policy
must be designed before indefinite continuous collection or local-space cleanup.

This decision does not authorize settlement access, model refitting, P&L
selection, paper/demo/real orders, or production writes.


<!-- SOAK_OBSERVABILITY_COMPONENT_20260906 -->
## 21N-Z-F observability component — 2026-09-06

Implementation choices for the offline observability component: exclusive run-owned JSONL artifacts; exact latency quantiles via bounded-memory on-disk SQLite indexing; strict required fields and explicit unknown/zero-count evidence; source-stop then raw-close then telemetry-seal then manifest-hash ordering. Legacy lifecycle hooks remain optional for component compatibility; future production packaging must require run_observed_soak and verified real producers. No frozen threshold or clock-transport amendment changed. See SOAK_OBSERVABILITY_IMPLEMENTATION.md for limits.

<!-- B5_R5_B_R16_ACCEPTED_SHAKEDOWN_20260907 -->
## B5-R5-B-C R16 accepted one-hour shakedown — 2026-09-07

Compose-packaged AWS run `kxbtcd_shakedown_20260907_r16` completed its full 3,600-second active window with a terminal manifest and safety status `PASS`. Read-only boundaries held: orders, signals, and production writes were all zero. Coinbase stayed on generation 1 with no reconnects. Kalshi recorded 339 Pings and 339 Pongs, no Pong timeout, no sequence gap, and 10 safe `ConnectionClosedError` records across 14 reconnect attempts. Availability was 95.6776% (3,444.39 ready seconds; 155.61 blocked seconds).

The original frozen design remains immutable. The library keepalive amendment `5a52b3f6cf8b2a22983e130969f82ad5b1e0303e237a220ef4322594c3c58e3b` records the effective 10-second Ping / 10-second timeout implementation. R16 is the qualifying empirical input for the immutable 24-hour storage-gate receipt. No 24-hour run has started.

<!-- B5_R5_B_24H_1_REJECTED_COINBASE_CANDLE_PUBLICATION_20260907 -->
## B5-R5-B-D first 24-hour launch rejected before measurement — 2026-09-07

Run `kxbtcd_soak_20260907_24h_1` terminalized before first readiness after a public Coinbase candle request returned HTTP 200 with an empty `[]` body at the exact minute boundary. The prior implementation classified the temporarily unpublished completed-minute candle as `ProspectiveLiveCollectorError`, causing a fail-closed hard failure. Active duration was zero, so this is not 24-hour evidence. Orders, signals, and production writes remained zero.

The narrow repair persists the raw `[]` response, classifies only this typed condition as a recoverable Coinbase transport condition, and uses the existing reconnect backoff while readiness remains blocked. It does not accept an empty candle or permit stale Coinbase state. Targeted regression: 25 passed in 3.79 seconds. A new one-hour shakedown is required because runtime code changed; the existing R16 storage receipt cannot arm a new image.

<!-- B5_R5_B_R17_REQUALIFICATION_20260907 -->
## B5-R5-B-C R17 fixed-image requalification — 2026-09-07

Run `kxbtcd_shakedown_20260907_r17` completed the full 3,600-second active window using image `sha256:fa4aa1649cd1d0752842e4ef588c2068e1c418ba374a4268123c9c7fb64ec609`. It reached `READY_READ_ONLY`, terminalized with manifest `MEASUREMENT_COMPLETE`, and passed all hard safety invariants: orders, signals, and production writes were zero; clock and identity remained PASS; Coinbase had no reconnects; Kalshi had zero sequence gaps. This requalifies the corrected Coinbase unpublished-candle behavior for the deployed image.

Availability was 72.3108% (2,603.19 ready seconds; 996.81 blocked seconds), with 76 Kalshi reconnect attempts and zero observed Pong timeouts. The frozen design has no numeric availability threshold, so the run satisfies its mandatory shakedown gate while preserving this reliability evidence for the 24-hour interpretation. The R16 receipt is superseded because the runtime image changed. Freeze a new receipt from R17 immediately before the canonical arm.

<!-- V2_MICRO_HYBRID_OFFLINE_FREEZE_20260907 -->
## Candidate-E V2 hybrid micro-probe offline freeze

The future Candidate-E V2 micro probe is frozen in `configs/kxbtcd_candidate_e_v2_micro_hybrid_probe_freeze_v1.json`: `0.01` contracts per order only after verifying the target market increment; bounded IOC entry attempts; one reduce-only GTC protection exit; continuous full-ladder monitoring; then cancel, authoritative reconciliation, and one full-remainder reduce-only FOK handoff. The hybrid has one exit writer and fails closed on stale/gapped feeds, unhealthy clock evidence, ambiguous venue state, or insufficient full depth.

`src/kxbtcd_candidate_e_v2_micro_hybrid_exit_offline.py` is offline-only and has no network, credentials, order outbox, order creation, cancellation, or production write. It evaluates confirmed resting-fill proceeds plus exact remaining ladder proceeds. Shadow scenarios must read closed immutable segments in a separate process and directory, with no shared sockets, credentials, order state, or event loop.

The active `kxbtcd_soak_20260907_24h_2` read-only container is unchanged. A terminal 24-hour review and controlled restart evidence remain required before any exact micro-probe authorization; a demo is optional for isolated API mechanics, not a mandatory week-long predecessor.

<!-- CANDIDATE_E_LIVE_SHADOW_DASHBOARD_20260909 -->
## Candidate-E live-shadow dashboard contract — 2026-09-09

The next accepted 24-hour read-only soak may carry a separate, read-only
**live-shadow simulator** for operational and dashboard validation. The
collector remains the source of immutable market evidence and keeps its existing
no-signal/no-order/no-production-write safety boundary. The simulator receives
only one-way, sanitized causal market snapshots and writes only a separate
append-only simulation ledger and atomic dashboard snapshot. A simulator or
dashboard fault must never block the soak collector.

The shadow simulator may record frozen V2 entry/exit decisions and hypothetical
immediate IOC book-walk results against observed full ladders. Dashboard P&L is
therefore labelled `SIMULATED_OBSERVED_DEPTH_NOT_VENUE_REALIZED`, never realized
P&L. It must state that it cannot prove venue queue priority, hidden liquidity,
cancellation races, or a resting-order fill. A resting GTC exit remains an
unproven counterfactual from archived books; only an observed-depth immediate
fill model may be shown as a hypothetical result.

Each live-shadow entry uses an all-in simulated budget of **$100.00**, including
the frozen fee and rounding calculation. The requested quantity is the largest
`0.01`-contract increment whose visible immediate book walk remains within that
budget; thin displayed depth may therefore yield a smaller simulated fill. This
is solely a dashboard scenario size and does not amend the separately frozen
`0.01`-contract production micro-probe policy.

The dashboard sidecar runs without a network, `.env`, Kalshi key, clock mount,
or collector write access. It reads the atomic snapshot from `soak_raw` as
read-only and writes its SQLite event ledger and atomic dashboard export only
to the separate `shadow_dashboard` volume. For each source snapshot, the event
batch and simulator checkpoint commit in one SQLite transaction. A restart can
therefore resume without duplicating a simulated trade; re-reading the last
snapshot merely regenerates the derived dashboard JSON.

The dashboard ledger and its read model retain multiple runs. Their replay
cursors are partitioned by `(run_id, scenario_id)`, so a new run begins at its
own snapshot sequence without overwriting or being confused with a prior run.
Overview totals are cumulative across retained runs; individual trade and
event rows always show their originating run ID, and the latest-snapshot panel
shows both the current run ID and its snapshot sequence.

For the shadow-only full-exit comparison, retain an entry-time target equal to
the simulated entry outlay plus the selected frozen V2 net edge per contract
times the actually simulated filled quantity. That target never changes after
entry. This supplies one deterministic dashboard comparison without claiming it
is a venue order price or changing the future micro-probe's separately frozen
production order contract.

This is an instrumentation and causal-decision test, not a paper broker, demo
trading, or real-money execution. It does not alter the separate explicit
authorization required for the eventual capped micro-production probe.

<!-- DECISION_POST_PROOF_PORTFOLIO_EXPANSION_20260907 -->
## Deferred re-entry and equal-edge multi-market research

Decision: do not add re-entry or concurrent multi-market positions to the first
Candidate-E V2 fractional micro probe. After a frozen base policy has sufficient
prospective and execution evidence to justify further research, open a separate
predeclared development program for: (1) re-entry after a fully reconciled exit,
and (2) allocation across multiple simultaneously qualifying markets with equal
or comparable net edge. That program must model correlated exposure, shared
capital/loss caps, available depth, queue/partial-fill risk, fee effects,
priority/tie-breaking, and how one position changes the remaining opportunity
set. It must use held-out evidence and cannot silently alter the frozen base
policy or increase exposure.
