"""21N-Y-A2: disk storage for the exact Y-A replay + Y-A1 quantities.

Replay reconciliation is imported unchanged. Last-write-wins millisecond states
are staged in SQLite instead of an all-history Python dictionary. Raw-book
compression occurs BEFORE the unchanged Y-A1 quantity adapter, in that order.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Callable, Iterator

from .kxbtcd_candidate_e_executable_convergence_liquidation_v1_simulator import (
    BookLevel, BookState, ExecutableConvergenceSimulatorError,
    _book_state_from_maps, _pair_replay_rows, _same_book,
)
from .kxbtcd_candidate_e_v2_execution_quantity_transport_amendment import canonicalize_book_state
from .predexon_full_ladder_replay import audit_ticker, rows_by_snapshot_pair
from .predexon_segment_safe_replay import apply_delta, mismatch_count, snapshot_book

SCHEMA = "kxbtcd_candidate_e_v2_disk_timeline.v1"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encode_book(state: BookState) -> str:
    # Decimal text is lossless; neither binary floats nor pickle are used.
    return json.dumps([
        [[str(x.price), str(x.quantity)] for x in state.yes_bids],
        [[str(x.price), str(x.quantity)] for x in state.yes_asks],
    ], separators=(",", ":"))


def decode_book(timestamp_ms: int, payload: str) -> BookState:
    bids, asks = json.loads(payload)
    return BookState(timestamp_ms,
                     tuple(BookLevel(Decimal(p), Decimal(q)) for p, q in bids),
                     tuple(BookLevel(Decimal(p), Decimal(q)) for p, q in asks))


def top_key(state: BookState) -> str:
    def number(value: Decimal) -> str:
        text = format(value, "f")
        return (text.rstrip("0").rstrip(".") if "." in text else text) or "0"
    values = []
    for levels in (state.yes_bids, state.yes_asks):
        values.extend([number(levels[0].price), number(levels[0].quantity)] if levels else [None, None])
    return json.dumps(values, separators=(",", ":"))


def configure(connection: sqlite3.Connection, *, writable: bool) -> None:
    connection.execute("PRAGMA cache_size=-1024")
    connection.execute("PRAGMA mmap_size=0")
    connection.execute("PRAGMA temp_store=FILE")
    if writable:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")


@dataclass(frozen=True)
class DiskSegment:
    connection: sqlite3.Connection
    segment_index: int
    start_timestamp_ms: int
    end_timestamp_ms: int
    state_count: int

    def contains_interval(self, start_ms: int, end_ms: int) -> bool:
        return (isinstance(start_ms, int) and isinstance(end_ms, int)
                and self.start_timestamp_ms <= start_ms <= end_ms <= self.end_timestamp_ms)

    def _check(self, start_ms: int, end_ms: int) -> None:
        if not self.contains_interval(start_ms, end_ms):
            raise ExecutableConvergenceSimulatorError("requested interval lies outside verified segment")

    def state_at(self, timestamp_ms: int) -> BookState:
        self._check(timestamp_ms, timestamp_ms)
        row = self.connection.execute(
            "SELECT book FROM states WHERE segment=? AND ts<=? ORDER BY ts DESC LIMIT 1",
            (self.segment_index, timestamp_ms),
        ).fetchone()
        if row is None:
            raise ExecutableConvergenceSimulatorError("no right-continuous state available at requested timestamp")
        return decode_book(timestamp_ms, row[0])

    @property
    def states(self) -> Iterator[BookState]:
        with closing(self.connection.execute(
            "SELECT ts,book FROM states WHERE segment=? ORDER BY ts", (self.segment_index,),
        )) as cursor:
            for timestamp_ms, payload in cursor:
                yield decode_book(timestamp_ms, payload)

    def state_changes(self, start_ms: int, end_ms: int) -> Iterator[BookState]:
        self._check(start_ms, end_ms)
        previous = self.state_at(start_ms)
        yield previous
        with closing(self.connection.execute(
            "SELECT ts,book FROM states WHERE segment=? AND ts>? AND ts<=? ORDER BY ts",
            (self.segment_index, start_ms, end_ms),
        )) as cursor:
            for timestamp_ms, payload in cursor:
                state = decode_book(timestamp_ms, payload)
                if not _same_book(previous, state):
                    previous = state
                    yield state

    def top_changes(self, start_ms: int, interval_end: int) -> Iterator[int]:
        # Match the frozen clock exactly, including its strict interval bounds.
        previous = top_key(self.state_at(start_ms))
        with closing(self.connection.execute(
            "SELECT ts,top FROM states WHERE segment=? AND ts>? AND ts<? ORDER BY ts",
            (self.segment_index, start_ms, interval_end),
        )) as cursor:
            for timestamp_ms, signature in cursor:
                if signature != previous:
                    previous = signature
                    yield timestamp_ms


class DiskTimeline:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            configure(self.connection, writable=False)
            self.metadata = json.loads(self.connection.execute("SELECT payload FROM metadata").fetchone()[0])
            if self.metadata.get("schema") != SCHEMA or self.metadata.get("complete") is not True:
                raise ValueError("incomplete or incompatible ticker cache")
            self.ticker = self.metadata["ticker"]
            self.segments = tuple(DiskSegment(self.connection, *row) for row in self.connection.execute(
                "SELECT segment,start,end,state_count FROM segments ORDER BY segment"))
        except BaseException:
            self.connection.close()
            raise

    def unique_segment_for_interval(self, start_ms: int, end_ms: int) -> DiskSegment | None:
        matches = [s for s in self.segments if s.contains_interval(start_ms, end_ms)]
        return matches[0] if len(matches) == 1 else None

    def close(self) -> None:
        self.connection.close()


def build_disk_timeline(*, path: Path, ticker: str, snapshots, paid_rows,
                        identity: dict, progress: Callable[[str], None] = lambda message: None) -> None:
    """Build a NEW unsealed cache; caller validates replay bounds before sealing.

Peak Python storage is the current ticker's source rows, audit metadata, and
current books, not the number of reconstructed book states. The frozen audit
still makes per-ticker row slices; this is not a hard whole-process RAM cap.
"""
    if path.exists():
        raise FileExistsError(f"refusing to overwrite cache: {path}")
    progress(f"{ticker}: auditing snapshot pairs")
    _, segments, results = audit_ticker(ticker=ticker, snapshots=snapshots, paid_rows=paid_rows)
    pair_rows = rows_by_snapshot_pair(snapshots, paid_rows)
    with closing(sqlite3.connect(path)) as db:
        configure(db, writable=True)
        db.executescript("""
            CREATE TABLE metadata(payload TEXT NOT NULL);
            CREATE TABLE segments(segment INTEGER PRIMARY KEY,start INTEGER,end INTEGER,state_count INTEGER);
            CREATE TABLE states(segment INTEGER,ts INTEGER,book TEXT NOT NULL,top TEXT NOT NULL,
                                PRIMARY KEY(segment,ts)) WITHOUT ROWID;
            CREATE TABLE staging(ts INTEGER PRIMARY KEY,book TEXT NOT NULL);
        """)
        total = 0
        for segment_index, segment in enumerate(segments):
            progress(f"{ticker}: reconstructing segment {segment_index + 1}/{len(segments)}")
            db.execute("DELETE FROM staging")
            def stage(state: BookState) -> None:
                nonlocal total
                db.execute("INSERT OR REPLACE INTO staging VALUES (?,?)", (state.timestamp_ms, encode_book(state)))
                total += 1
                if total % 10000 == 0:
                    progress(f"{ticker}: {total:,} raw state writes")

            first = snapshots[segment.start_snapshot_index]
            bids, asks = snapshot_book(first)
            stage(_book_state_from_maps(int(first["timestamp"]), bids, asks))
            for i in range(segment.start_snapshot_index, segment.end_snapshot_index):
                result = results[i]
                if not result.exact:
                    raise ExecutableConvergenceSimulatorError("verified segment contains a failed pair")
                a, b = snapshots[i], snapshots[i + 1]
                bids, asks = snapshot_book(a)
                stage(_book_state_from_maps(int(a["timestamp"]), bids, asks))
                for row in _pair_replay_rows(a, b, pair_rows[i], result):
                    apply_delta(bids, asks, row)
                    stage(_book_state_from_maps(int(row["timestamp"]), bids, asks))
                expected_bids, expected_asks = snapshot_book(b)
                if mismatch_count(bids, expected_bids) or mismatch_count(asks, expected_asks):
                    raise ExecutableConvergenceSimulatorError("exact replay pair failed independent reconstruction")
                stage(_book_state_from_maps(int(b["timestamp"]), expected_bids, expected_asks))

            previous_raw = None
            previous_ts = None
            count = 0
            for timestamp_ms, payload in db.execute("SELECT ts,book FROM staging ORDER BY ts"):
                if previous_ts is not None and timestamp_ms <= previous_ts:
                    raise ExecutableConvergenceSimulatorError("timestamps must be unique and increasing")
                if not segment.start_timestamp <= timestamp_ms <= segment.end_timestamp:
                    raise ExecutableConvergenceSimulatorError("timeline state outside verified segment")
                previous_ts = timestamp_ms
                raw = decode_book(timestamp_ms, payload)
                if previous_raw is None or not _same_book(previous_raw, raw):
                    canonical = canonicalize_book_state(raw)
                    db.execute("INSERT INTO states VALUES (?,?,?,?)",
                               (segment_index, timestamp_ms, encode_book(canonical), top_key(canonical)))
                    count += 1
                    previous_raw = raw
            if not count:
                raise ExecutableConvergenceSimulatorError("verified segment must contain at least one state")
            db.execute("INSERT INTO segments VALUES (?,?,?,?)",
                       (segment_index, segment.start_timestamp, segment.end_timestamp, count))
            db.commit()
        db.execute("DROP TABLE staging")
        metadata = {"schema": SCHEMA, "ticker": ticker, "complete": True, "identity": identity}
        db.execute("INSERT INTO metadata VALUES (?)", (json.dumps(metadata, sort_keys=True),))
        db.commit()
        # Compact away the reusable staging table before hashing/sealing.
        progress(f"{ticker}: compacting completed cache")
        db.execute("VACUUM")


def write_timeline_fixture(path: Path, timeline, identity: dict | None = None) -> None:
    """Synthetic equivalence-test helper; never used by the real-data runner."""
    with closing(sqlite3.connect(path)) as db:
        configure(db, writable=True)
        db.executescript("""
            CREATE TABLE metadata(payload TEXT NOT NULL);
            CREATE TABLE segments(segment INTEGER PRIMARY KEY,start INTEGER,end INTEGER,state_count INTEGER);
            CREATE TABLE states(segment INTEGER,ts INTEGER,book TEXT NOT NULL,top TEXT NOT NULL,
                                PRIMARY KEY(segment,ts)) WITHOUT ROWID;
        """)
        for segment in timeline.segments:
            db.execute("INSERT INTO segments VALUES (?,?,?,?)", (segment.segment_index,
                       segment.start_timestamp_ms, segment.end_timestamp_ms, len(segment.states)))
            db.executemany("INSERT INTO states VALUES (?,?,?,?)", (
                (segment.segment_index, state.timestamp_ms, encode_book(state), top_key(state)) for state in segment.states))
        db.execute("INSERT INTO metadata VALUES (?)", (json.dumps({"schema": SCHEMA, "ticker": timeline.ticker,
                   "complete": True, "identity": identity or {}}),))
        db.commit()
