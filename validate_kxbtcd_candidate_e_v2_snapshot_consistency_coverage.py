"""Coverage-only validation for the frozen Y-A4 snapshot consistency amendment."""
from __future__ import annotations
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.dont_write_bytecode = True
from src.kxbtcd_candidate_e_v2_snapshot_consistency import repair_coverage
from src.kxbtcd_candidate_e_v2_snapshot_consistency_io import (
    AMENDMENT, BASE, CACHE, CODE_HASHES, COVERAGE_SHA, EXPECTED_FAILURES, EXPECTED_TICKERS,
    MEMORY, PAID_FILE, PAID_SHA, PATH_FILE, PATH_SHA, QUANTITY, REPLAYS, SNAPSHOTS,
    CoveragePairs, Progress, build_paid_index, check_hash, require, sha256,
    validate_output_location, write_report,
)
from src.kxbtcd_candidate_e_v2_snapshot_consistency_freeze import validate_snapshot_consistency_amendment


def run_coverage(repo, output):
    import tempfile
    from collections import Counter

    repo, output = Path(repo).resolve(), Path(output).resolve()
    validate_output_location(repo, output)
    require(not (repo / CACHE / "RUNNING.lock").exists(), "Cache runner lock exists; wait for the runner to finish")
    with Progress() as progress:
        inputs = {}

        def remember(relative, expected=None):
            path = repo / relative
            digest = sha256(path)
            if expected is not None:
                require(digest == expected, "Source/hash mismatch: " + str(relative))
            inputs[str(relative)] = digest
            return path

        amendment = validate_snapshot_consistency_amendment(repo)
        progress("Checking frozen code and completed evidence identities")
        for relative, expected in CODE_HASHES.items():
            p = remember(relative)
            require(hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == expected,
                    "Frozen diagnostic dependency changed: " + relative)
        sys.path.insert(0, str(repo))
        from src import predexon_segment_safe_replay as replay
        from src.predexon_full_ladder_replay import load_backfill_snapshots
        from src.kxbtcd_candidate_e_v2_replay_precision import normalize_snapshots, validate_paid_quantities
        from src.kxbtcd_candidate_e_v2_replay_precision_freeze import validate_precision_amendment

        require(validate_precision_amendment(repo)["amendment_fingerprint"] == AMENDMENT, "Unexpected amendment")
        paths = json.loads(remember(PATH_FILE, PATH_SHA).read_text(encoding="utf-8"))
        coverage = json.loads(remember(CACHE / "coverage_full.json", COVERAGE_SHA).read_text(encoding="utf-8"))
        require(paths["replay_precision_coverage_sha256"] == COVERAGE_SHA, "Path/coverage binding mismatch")
        require(paths["replay_precision_amendment_fingerprint"] == coverage["replay_precision_amendment_fingerprint"] == AMENDMENT,
                "Path/coverage amendment mismatch")
        reports = {r["ticker"]: r for r in coverage["ticker_reports"]}
        tickers = sorted(reports)
        require(len(tickers) == len(coverage["ticker_reports"]) == EXPECTED_TICKERS, "Unexpected ticker universe")
        require(set(tickers) == set(paths["dynamic_ticker_union"]), "Path/coverage ticker mismatch")
        require(sum(r["after"]["unreconciled_pair_count"] for r in reports.values()) == EXPECTED_FAILURES,
                "Unexpected failed-pair count")
        del paths
        progress("Checking the paid source shard")
        paid_path = remember(PAID_FILE, PAID_SHA)
        ticker_results = []
        with tempfile.TemporaryDirectory(prefix="candidate_e_snapshot_coverage_") as temporary:
            temp_root = Path(temporary).resolve()
            require(not temp_root.is_relative_to(repo), "Temporary workspace must be outside the repository")
            with closing(sqlite3.connect(temp_root / "paid_index.sqlite")) as index:
                progress("Building a disposable index of exact paid updates; existing caches are unchanged")
                index_info = build_paid_index(paid_path, index, tickers, validate_paid_quantities, progress)
                for number, ticker in enumerate(tickers, 1):
                    progress(f"Ticker {number}/{len(tickers)}: checking identities and snapshot evidence for {ticker}")
                    audit = reports[ticker]
                    cache = repo / CACHE / (ticker + ".sqlite")
                    for suffix in ("-wal", "-shm", "-journal"):
                        require(not Path(str(cache) + suffix).exists(), "Unexpected active SQLite sidecar")
                    seal = json.loads(remember(CACHE / (ticker + ".seal.json")).read_text(encoding="utf-8"))
                    remember(CACHE / cache.name, seal["sha256"])
                    with closing(sqlite3.connect(cache.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
                        metadata_rows = connection.execute("SELECT payload FROM metadata").fetchall()
                        require(len(metadata_rows) == 1, "Cache metadata count mismatch")
                        metadata = json.loads(metadata_rows[0][0])
                        bounds = [list(r) for r in connection.execute("SELECT start,end FROM segments ORDER BY segment")]
                    identity = seal["identity"]
                    require(metadata.get("complete") is True and metadata["ticker"] == ticker
                            and metadata["identity"] == identity, "Cache identity mismatch")
                    require(metadata["replay_precision_audit"] == audit and bounds == audit["after_bounds"],
                            "Cache differs from pinned coverage")
                    require(identity["ticker"] == ticker and identity["paid_sha256"] == PAID_SHA
                            and identity["replay_precision_amendment_fingerprint"] == AMENDMENT
                            and identity["memory_amendment_fingerprint"] == MEMORY
                            and identity["quantity_amendment_fingerprint"] == QUANTITY, "Source identity mismatch")
                    snapshot_file = remember(SNAPSHOTS / (ticker + "_raw_pages.jsonl"), identity["snapshot_sha256"])
                    remember(REPLAYS / (ticker + ".json"), identity["replay_sha256"])
                    snapshots = load_backfill_snapshots(snapshot_file, ticker=ticker)
                    require(len(snapshots) == audit["after"]["snapshot_count"], "Snapshot count mismatch")
                    require(index_info["counts_by_ticker"][ticker] == audit["after"]["paid_delta_count"], "Paid row count mismatch")
                    for p in audit["remaining_unreconciled_pairs"]:
                        i = p["pair_index"]
                        require(int(snapshots[i]["timestamp"]) == p["start_timestamp_ms"]
                                and int(snapshots[i + 1]["timestamp"]) == p["end_timestamp_ms"], "Failed-pair source indices mismatch")
                    normalized, normalization = normalize_snapshots(snapshots)
                    del snapshots
                    result = repair_coverage(normalized, audit, CoveragePairs(ticker, normalized, audit, index, replay))
                    result["ticker"] = ticker
                    result["source_identity"] = identity
                    result["normalization"] = normalization
                    ticker_results.append(result)
                    progress(f"{ticker}: accepted {result['accepted_counts']}; "
                             f"combined remaining failures {result['variants']['combined']['remaining_failed_pair_count']}")
                    del normalized
        progress("Verifying source and cache hashes remained unchanged")
        for relative, digest in inputs.items():
            check_hash(repo / relative, digest)
        validate_precision_amendment(repo)
        require(not (repo / CACHE / "RUNNING.lock").exists(), "Cache runner started during the audit")
        validate_snapshot_consistency_amendment(repo)
        totals = {}
        for name in ("ordering_only", "quarantine_only", "combined"):
            variants = [t["variants"][name] for t in ticker_results]
            totals[name] = {"remaining_failed_pair_count": sum(v["remaining_failed_pair_count"] for v in variants),
                            "original_failed_pairs_addressed": sum(len(v["original_failed_pairs_addressed"]) for v in variants),
                            "verified_ms": sum(v["verified_ms"] for v in variants),
                            "excluded_ms": sum(v["excluded_ms"] for v in variants)}
            require(totals[name]["remaining_failed_pair_count"] + totals[name]["original_failed_pairs_addressed"] == EXPECTED_FAILURES,
                    "Global failed-pair accounting mismatch")
        payload = {"schema_version": "kxbtcd_snapshot_consistency_coverage.v1",
            "checkpoint_id": "21N-Y-A4", "status": "PASS_INCREMENTAL_COVERAGE_GATE",
            "amendment_fingerprint": amendment["amendment_fingerprint"],
            "parent_coverage_sha256": COVERAGE_SHA, "parent_path_sha256": PATH_SHA,
            "ticker_count": len(ticker_results), "original_failed_pair_count": EXPECTED_FAILURES,
            "totals": totals, "ticker_results": ticker_results, "index_summary": index_info,
            "input_file_sha256": inputs,
            "scope": "all_source_identities_and_changed_neighborhoods_rechecked_unchanged_pair_classifications_reused",
            "next_gate": "review_report_then_implement_and_validate_a_new_cache_builder_using_required_local_cut_chains",
            "limitations": ["This is not a newly built execution cache or complete global cut-chain audit.",
                "Raw snapshots and historical paths remain unchanged; quarantine is recorded in a separate proposed view.",
                "Long, ambiguous, overlapping or unsupported cases remain unresolved.",
                "Coverage percentages refer to the recorded snapshot span, not continuous coverage through settlement.",
                "No causal guarantees for omitted snapshots or transfer to new markets are established."],
            "safety": {"strategy_run": False, "outcomes_accessed": False, "strategy_pnl_calculated": False,
                       "orders_placed": 0, "network_requests": 0, "existing_caches_modified": False,
                       "new_cache_built": False, "temporary_index_removed": True}}
        digest = write_report(output, payload)
        progress(f"COVERAGE GATE PASS: {len(ticker_results)} tickers; "
                 f"{totals['combined']['original_failed_pairs_addressed']} original failed pairs addressed in proposed view; "
                 f"{totals['combined']['remaining_failed_pair_count']} remain unresolved")
        print(f"Output: {output}\nSHA256: {digest}\nStrategy: NOT RUN | Outcomes: NOT ACCESSED | Orders: 0", flush=True)
        return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        run_coverage(args.repo, args.output)
    except KeyboardInterrupt:
        print("Coverage gate interrupted; existing caches and source files were not modified.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Coverage gate stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
