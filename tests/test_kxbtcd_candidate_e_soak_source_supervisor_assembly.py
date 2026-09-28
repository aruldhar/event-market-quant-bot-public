import threading

from src import kxbtcd_candidate_e_soak_source_supervisor_assembly as assembly
from src.kxbtcd_candidate_e_soak_runtime_core import SoakSourceRuntimeCore


def test_supervisor_assembly_binds_both_workers_to_one_core(tmp_path, monkeypatch):
    core = SoakSourceRuntimeCore(runtime_session_id="run", archive_root=tmp_path)
    captured = {}
    monkeypatch.setattr(assembly, "run_coinbase_reconnect_supervisor", lambda **kw: captured.update(cb=kw) or "cb")
    monkeypatch.setattr(assembly, "run_kalshi_reconnect_supervisor", lambda **kw: captured.update(ka=kw) or "ka")
    cb, ka = assembly.assemble_read_only_supervisors(
        core=core, run_coinbase_generation=lambda worker, stop: "coinbase",
        run_kalshi_generation=lambda worker, stop: "kalshi",
        rediscover_current_event=lambda supplied: "discovered")
    try:
        assert cb(threading.Event()) == "cb"
        assert ka(threading.Event()) == "ka"
        assert captured["cb"]["worker"].core is core
        assert captured["ka"]["worker"].core is core
        assert captured["cb"]["run_generation"]() == "coinbase"
        assert captured["ka"]["run_generation"]() == "kalshi"
        assert captured["ka"]["rediscover_current_event"]() == "discovered"
    finally:
        core.close()
