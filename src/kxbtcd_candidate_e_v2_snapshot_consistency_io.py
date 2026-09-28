"""Pinned source I/O and exact pair instrumentation for the Y-A4 coverage gate."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from .kxbtcd_candidate_e_v2_snapshot_consistency import ReplayWorkBound, RULES


PATH_SHA = "3b1bfadd61f003343d385fc1f62b6192ce5b53fda87d3f1977d84f604ebb4780"

COVERAGE_SHA = "5b78812350bbcd3cea77f9c109dac2cce636de9577426edbaf523179859da1ab"

AMENDMENT = "82c4d05994cf97c723672b82428a7a139e20f96ae5aeea622e6dfaf1429a1370"

PAID_SHA = "43e9c5d99fb4001b866ae3e60021c8c10123dc1fb6248df96084446face68509"

MEMORY = "f7a590cb0f8415e3330fa82077d16b6b93105717f573e69e8580a3f3ac1ffe03"

QUANTITY = "2cbd8836045ae811eb4c52d48834953a54b1be3afac094be4cf349b8cac2abce"

BASE = Path("data/analysis/predexon_credit_efficiency")

PATH_FILE = BASE / "july10_candidate_e_v2_outcome_blind_paths_replay_precision.json"

CACHE = BASE / "v2_y_a3_replay_precision_cache"

PAID_FILE = Path("data/raw/predexon_ticks/2026/07/10/kalshi_orderbook_deltas_2026-07-10_part00017_raw.zstd.parquet")

SNAPSHOTS = Path("data/raw/predexon_orderbook_subcent_backfill/2026/07/10")

REPLAYS = Path("data/analysis/predexon_full_ladder_replay/tickers")

PAID_COLUMNS = ["ticker", "timestamp", "sequence", "side", "price_dollars", "delta_fp"]

CODE_HASHES = {
    "src/predexon_segment_safe_replay.py": "94cd67ad0fae50c7b60fe90a89b17449f8813717889647e32be847a62f6ad8b4",
    "src/predexon_full_ladder_replay.py": "340191f6b4c8ccef893c329ca9bdb5c198986576b8b7a5f388e271175a13b477",
    "src/predexon_subcent_backfill.py": "e3a2ad65f180a3e3cf01d88d001c3b8fd31a2e15ebf9378e1937ebc8310bab32",
    "src/kxbtcd_candidate_e_v2_replay_precision.py": "5800adf3ce3602762c88b7c68410d713ce5f4f434eeac035feab6823d835eea4",
    "src/kxbtcd_candidate_e_v2_execution_quantity_transport_amendment.py": "a4d5cdbd383a3cbd969020bd746588e8e26ce06fae734f2345d5f478b8b8b353",
    "src/kxbtcd_candidate_e_v2_replay_precision_freeze.py": "86506b9ddd1c0b6760fed9f12fdf560b61000a0658c9b0205575fddc1b2a8981",
}

MAX_CUTS = 10000

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def check_hash(path, expected):
    observed = sha256(path)
    require(observed == expected, "Source/hash mismatch: " + str(path))
    return observed

def level_differences(bids, asks, expected_bids, expected_asks, epsilon):
    output = []
    for side, actual, expected in (("yes_bids", bids, expected_bids),
                                  ("yes_asks", asks, expected_asks)):
        for price in sorted(set(actual) | set(expected)):
            a, b = actual.get(price, Decimal(0)), expected.get(price, Decimal(0))
            if abs(a - b) > epsilon:
                output.append({"book_side": side, "price_dollars": str(price),
                               "replayed_quantity": str(a), "snapshot_quantity": str(b),
                               "replayed_minus_snapshot": str(a - b)})
    return output

def inspect_pair(start, end, nearby_rows, replay, *, epsilon):
    """Instrument every legal cut without relaxing or changing frozen replay."""
    lo, hi = int(start["timestamp"]), int(end["timestamp"])
    rows = sorted((r for r in nearby_rows if lo <= int(r["timestamp"]) <= hi),
                  key=lambda r: (int(r["timestamp"]), int(r["sequence"])))
    start_bids, start_asks = replay.snapshot_book(start)
    end_bids, end_asks = replay.snapshot_book(end)
    first = [r for r in rows if int(r["timestamp"]) == lo]
    middle = [r for r in rows if lo < int(r["timestamp"]) < hi]
    last = [r for r in rows if int(r["timestamp"]) == hi]
    ncuts = ((len(first) + 1) * (len(first) + 2) // 2 if lo == hi
             else (len(first) + 1) * (len(last) + 1))
    require(ncuts <= MAX_CUTS, "Boundary cut count exceeds diagnostic bound")
    frozen = asdict(replay.reconcile_pair(start, end, rows, epsilon=epsilon))
    candidates, best, best_differences = [], None, None
    for sc in range(len(first) + 1):
        for ec in range(sc if lo == hi else 0, len(last) + 1):
            applied = first[sc:ec] if lo == hi else first[sc:] + middle + last[:ec]
            bids, asks = dict(start_bids), dict(start_asks)
            result = {"start_cut": sc, "end_cut": ec, "selected_delta_count": len(applied)}
            for row in applied:
                price = Decimal(str(row["price_dollars"]))
                book_side = "yes_bids" if row["side"] == "yes" else "yes_asks"
                level = price if row["side"] == "yes" else Decimal(1) - price
                before = (bids if row["side"] == "yes" else asks).get(level, Decimal(0))
                try:
                    replay.apply_delta(bids, asks, row)
                except ValueError as error:
                    result.update({"executable": False, "error": str(error),
                                   "failed_row": row, "book_side": book_side,
                                   "book_price_dollars": str(level),
                                   "quantity_before": str(before),
                                   "quantity_after": str(before + Decimal(str(row["delta_fp"])))})
                    break
            else:
                differences = level_differences(bids, asks, end_bids, end_asks, epsilon)
                bm = sum(d["book_side"] == "yes_bids" for d in differences)
                am = len(differences) - bm
                score = (bm + am, bm, am, sc, ec)
                result.update({"executable": True, "exact": not differences,
                               "bid_mismatches": bm, "ask_mismatches": am,
                               "total_mismatches": bm + am})
                if best is None or score < best:
                    best, best_differences = score, differences
            candidates.append(result)
    require(len(candidates) == ncuts, "Diagnostic cut enumeration count mismatch")
    if best is None:
        require(frozen["total_mismatches"] == -1, "Instrumented replay disagrees with frozen replay")
    else:
        require(best == (frozen["total_mismatches"], frozen["bid_mismatches"],
                         frozen["ask_mismatches"], frozen["start_cut"], frozen["end_cut"]),
                "Instrumented best cut disagrees with frozen replay")
    return {"frozen_reconciliation": frozen, "comparison_epsilon": str(epsilon),
            "cut_count": ncuts, "executable_cut_count": sum(c["executable"] for c in candidates),
            "exact_cut_count": sum(c.get("exact", False) for c in candidates),
            "all_legal_cuts": candidates, "best_cut_level_differences": best_differences}

def write_report(path, payload):
    raw = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False, default=str) + "\n").encode()
    # Exclusive creation: never overwrite an existing report or source file.
    with Path(path).open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return hashlib.sha256(raw).hexdigest()

def validate_output_location(repo, output):
    require(not output.is_relative_to(repo), "Choose a report path outside the repository (for example Downloads)")
    require(output.suffix.lower() == ".json", "Output must be a .json file")
    require(output.parent.is_dir(), "Output directory does not exist")
    require(not output.exists(), "Report already exists; preserve/upload it or choose a new output filename")

EXPECTED_TICKERS = 47

EXPECTED_FAILURES = 748

class Progress:
    def __enter__(self):
        import threading
        self.started = time.monotonic()
        self.stage = "starting"
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.thread.start()
        return self

    def __call__(self, message):
        self.stage = message
        print(f"[{time.monotonic() - self.started:.0f}s] {message}", flush=True)

    def heartbeat(self):
        while not self.stop.wait(15):
            print(f"[{time.monotonic() - self.started:.0f}s] Working: {self.stage}", flush=True)

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=1)

def build_paid_index(path, connection, tickers, validate_quantities, progress):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    # This is a disposable index of source rows, never a replay cache.
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA cache_size=-32768")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute("CREATE TABLE ticks(ticker TEXT,ts INTEGER,seq INTEGER,source_row INTEGER,side TEXT,price TEXT,delta TEXT)")
    values = pa.array(tickers, type=pa.string())
    scanned = retained = 0
    counts = defaultdict(int)
    with pq.ParquetFile(path) as parquet:
        expected = parquet.metadata.num_rows
        for batch in parquet.iter_batches(batch_size=131072, columns=PAID_COLUMNS):
            column = batch.column(batch.schema.get_field_index("ticker"))
            mask = pc.fill_null(pc.is_in(column, value_set=values), False)
            rows = batch.filter(mask).to_pylist()
            indices = pc.indices_nonzero(mask).to_pylist()
            validate_quantities(rows)
            records = []
            for r, index in zip(rows, indices):
                ticker = str(r["ticker"])
                counts[ticker] += 1
                records.append((ticker, int(r["timestamp"]), int(r["sequence"]),
                    scanned + int(index) + 1, str(r["side"]), str(r["price_dollars"]), str(r["delta_fp"])))
            connection.executemany("INSERT INTO ticks VALUES (?,?,?,?,?,?,?)", records)
            connection.commit()
            scanned += batch.num_rows
            retained += len(rows)
            if scanned % 524288 == 0:
                progress(f"Source rows scanned: {scanned:,}; selected ticker rows indexed: {retained:,}")
        require(scanned == expected, "Incomplete source scan")
    progress("Indexing timestamps in disposable source workspace")
    connection.execute("CREATE INDEX lookup ON ticks(ticker,ts,seq,source_row)")
    connection.commit()
    require(set(counts) == set(tickers), "Selected tickers missing from paid source")
    return {"source_rows_scanned": scanned, "indexed_row_count": retained, "counts_by_ticker": dict(counts)}


class CoveragePairs:
    def __init__(self, ticker, snapshots, coverage, connection, replay):
        self.ticker, self.snapshots, self.connection, self.replay = ticker, snapshots, connection, replay
        self.expected = {p['pair_index']: p['result'] for p in coverage['remaining_unreconciled_pairs']}
        self.cache = {}

    def __call__(self, i, j):
        if (i, j) in self.cache:
            return self.cache[i, j]
        a, b = self.snapshots[i], self.snapshots[j]
        lo, hi = int(a['timestamp']), int(b['timestamp'])
        require(lo <= hi, 'Timestamp reversal')
        if hi - lo > RULES['maximum_context_span_ms']:
            raise ReplayWorkBound('pair_time_span')
        data = self.connection.execute(
            'SELECT ts,seq,source_row,side,price,delta FROM ticks WHERE ticker=? AND ts>=? AND ts<=? '
            'ORDER BY ts,seq,source_row LIMIT ?',
            (self.ticker, lo, hi, RULES['maximum_pair_rows'] + 1)).fetchall()
        if len(data) > RULES['maximum_pair_rows']:
            raise ReplayWorkBound('pair_row_count')
        rows = [{'ticker': self.ticker, 'timestamp': ts, 'sequence': seq, 'source_row_number_1based': number,
                 'side': side, 'price_dollars': price, 'delta_fp': delta}
                for ts, seq, number, side, price, delta in data]
        sn, en = sum(r['timestamp'] == lo for r in rows), sum(r['timestamp'] == hi for r in rows)
        cuts = (sn + 1) * (sn + 2) // 2 if lo == hi else (sn + 1) * (en + 1)
        if cuts > RULES['maximum_pair_cuts'] or max(len(rows), 1) * cuts > RULES['maximum_pair_rows_times_cuts']:
            raise ReplayWorkBound('pair_cut_work')
        detail = inspect_pair(a, b, rows, self.replay, epsilon=Decimal(0))
        frozen = detail['frozen_reconciliation']
        if j == i + 1:
            if i in self.expected:
                require(frozen == self.expected[i], 'Original failed pair changed')
            else:
                require(frozen['exact'], 'Original verified control changed')
        result = {'start_snapshot_index': i, 'end_snapshot_index': j,
                  'frozen_reconciliation': frozen, 'paid_row_count': len(rows),
                  'exact_cuts': [[c['start_cut'], c['end_cut']] for c in detail['all_legal_cuts'] if c.get('exact')]}
        self.cache[i, j] = result
        return result
