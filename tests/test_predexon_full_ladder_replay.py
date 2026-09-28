import pytest
from src.predexon_full_ladder_replay import PredexonFullLadderReplayError, rows_by_snapshot_pair

def test_pair_slices_inclusive_boundaries():
    snapshots=[{"timestamp":100},{"timestamp":200},{"timestamp":300}]
    rows=[{"timestamp":99,"sequence":1},{"timestamp":100,"sequence":2},{"timestamp":150,"sequence":3},{"timestamp":200,"sequence":4},{"timestamp":250,"sequence":5},{"timestamp":300,"sequence":6},{"timestamp":301,"sequence":7}]
    out=rows_by_snapshot_pair(snapshots,rows)
    assert [r["timestamp"] for r in out[0]]==[100,150,200]
    assert [r["timestamp"] for r in out[1]]==[200,250,300]

def test_same_timestamp_snapshots():
    out=rows_by_snapshot_pair([{"timestamp":100},{"timestamp":100}],[{"timestamp":100,"sequence":1},{"timestamp":100,"sequence":2}])
    assert len(out)==1 and len(out[0])==2

def test_paid_rows_must_be_chronological():
    with pytest.raises(PredexonFullLadderReplayError):
        rows_by_snapshot_pair([{"timestamp":100},{"timestamp":200}],[{"timestamp":150,"sequence":2},{"timestamp":120,"sequence":1}])

def test_single_snapshot_has_zero_pairs():
    assert rows_by_snapshot_pair([{"timestamp":100}],[])==[]
