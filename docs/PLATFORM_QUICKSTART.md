> This was the repository's original README, written during Phase 1 (August 2026). It is kept as the platform quick-start and safety reference. For the full project story, start with the root [README](../README.md) and [RESEARCH_HISTORY.md](RESEARCH_HISTORY.md).

# Event-Market Quant Bot

An education-first quantitative trading research project. The initial scope is a **read-only Kalshi Bitcoin market scanner**. The architecture and documentation are designed so other assets, venues, and strategies can be added later without mixing unvalidated ideas into the live decision path.

## Current safety state

- Public, read-only REST market data only
- No account authentication
- No API keys or private keys
- No order placement, cancellation, or account access
- No demo or real-money trading

The project must pass research, paper-trading, and demo-execution gates before production trading is considered.

## Current capabilities

1. Discover open Bitcoin-related Kalshi markets.
2. Retrieve a selected market's order book through public REST endpoints.
3. Convert Kalshi's YES/NO bid-only representation into best bids and implied asks.
4. Archive every raw REST exchange to append-only JSON Lines before transformation.
5. Record request context, source timestamps, HTTP/error details, and UTC/monotonic timing.
6. Carry exact raw-request lineage into every derived order-book CSV row.
7. Write separate structured runtime lifecycle, request, persistence, and endpoint-validation events.
8. Fail closed when required raw or runtime-event persistence fails.
9. Create atomic v2 run manifests with Git identity, artifact hashes, counts, runtime-event relationships, and completion state.
10. Validate completed v1 or v2 runs offline and detect missing, incomplete, altered, or semantically mismatched artifacts.
11. Maintain a versioned machine-readable source registry with authority, authentication, timestamp, evidence, and source-quality boundaries.
12. Validate the source registry offline before a source can enter later model or decision work.
13. Run tests for quote calculations, raw preservation, lineage, manifests, endpoint validation, runtime observability, and source-registry integrity.
14. Use a fail-closed checkpoint-closeout helper to verify, test, stage, commit, generate a closeout receipt, push, and confirm a clean synchronized branch.

## Repository map

```text
event-market-quant-bot/
├── README.md
├── SETUP_CHECKLIST.md
├── .env.example
├── requirements.txt
├── scan_btc_markets.py
├── record_orderbook.py
├── validate_run_manifest.py
├── validate_source_registry.py
├── configs/
│   └── source_registry.json
├── src/
│   ├── raw_json_log.py
│   ├── runtime_events.py
│   ├── run_manifest.py
│   ├── run_validation.py
│   ├── source_registry.py
│   └── data_integrity.py
├── tests/
├── docs/
├── data/
├── logs/
├── reports/
├── notebooks/
└── scripts/
```

The permanent project record is in `docs/`. Start with:

1. `docs/PROJECT_CHARTER.md`
2. `docs/PROJECT_STATE.md`
3. `docs/CANDIDATE_E_LIVE_SHADOW_RESEARCH_PLAN.md` for the current
   read-only shadow-policy comparison roadmap

## Quick start on Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -q
python validate_source_registry.py
python scan_btc_markets.py
```

Normal collectors write ignored raw exchanges under `data/raw/kalshi_rest/`, structured operational events under `logs/runtime/`, and run receipts under `data/manifests/`. See `docs/RAW_DATA_SCHEMA.md`, `docs/RUNTIME_OBSERVABILITY_SCHEMA.md`, and `docs/RUN_MANIFEST_SCHEMA.md` before changing these contracts.

Validate the newest completed run with:

```powershell
python validate_run_manifest.py
```

Validate source identities and fail-closed policy with:

```powershell
python validate_source_registry.py
```

## Safe Git checkpoint closeout

After the helper tooling itself has been manually reviewed, validated, committed, and pushed once, normal future checkpoints can be closed with:

```powershell
.\scripts\close_checkpoint.ps1
```

The helper discovers the complete changed-file set, asks you to approve it, runs configured validators and the full pytest suite, stages only the approved paths, scans for blocked paths and high-confidence secret material, asks for the checkpoint commit message, creates a generated closeout receipt commit, asks once before pushing both commits, and verifies remote synchronization plus a clean worktree.

To require an exact path list instead of approving auto-discovery:

```powershell
.\scripts\close_checkpoint.ps1 -Paths @(
    "src/example.py",
    "tests/test_example.py",
    "docs/PROJECT_STATE.md"
)
```

If a safe push was declined or a network push failed after both local commits were created:

```powershell
.\scripts\close_checkpoint.ps1 -PushExisting
```

The helper refuses to certify modifications to its own safety-critical files. Updates to the closeout helper/config/tests must be reviewed and Git-closed manually. See `docs/GIT_CHECKPOINT_CLOSEOUT.md`.

## Development phases

1. Project governance and read-only scanner
2. Raw REST logging, timing, manifests, lineage, and runtime validation
3. Source registry and settlement-rule validation
4. Public settled-market evidence and rule consistency
5. Synchronized reference-feed design after source authority is sufficient
6. Settlement-aware features and baseline probability modeling
7. Paper execution with realistic fills and costs
8. Chronological out-of-sample validation
9. Kalshi demo execution
10. Small production pilot only after all declared gates pass

## Core rule

The bot does not trade because it predicts that Bitcoin will rise or fall. It may act only when a calibrated probability estimate exceeds an executable market price by enough to cover fees, spread, depth, slippage, latency, missed fills, uncertainty, and risk limits. No such trading eligibility exists in the current phase.
