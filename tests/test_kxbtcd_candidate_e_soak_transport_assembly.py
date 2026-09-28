import threading

from src import kxbtcd_candidate_e_soak_transport_assembly as assembly


def test_transport_assembly_defers_all_transport_calls_until_supervisor_invocation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(assembly, "run_one_coinbase_generation", lambda **kw: calls.append(("coinbase", kw)) or "cb")
    monkeypatch.setattr(assembly, "run_one_kalshi_generation", lambda **kw: calls.append(("kalshi", kw)) or "ka")
    monkeypatch.setattr(assembly, "fetch_current_kxbtcd_event", lambda **kw: calls.append(("rest", kw)) or "rest")
    cb, ka, rediscover = assembly.assemble_read_only_transport_callbacks(
        http_session="session", repo_root=tmp_path, monotonic_ns=lambda: 7, epoch_seconds=lambda: 9)
    assert calls == []
    assert cb("worker", threading.Event()) == "cb"
    assert ka("worker", threading.Event()) == "ka"
    assert rediscover("core") == "rest"
    assert [name for name, _ in calls] == ["coinbase", "kalshi", "rest"]
    assert calls[2][1]["now_timestamp_ms"] == 9000


def test_v2_uses_independent_rest_poller_not_websocket_repair_http(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(assembly, "run_one_coinbase_generation", lambda **kw: captured.update(kw) or "cb")
    cb, _, _ = assembly.assemble_read_only_transport_callbacks(
        http_session="session", repo_root=tmp_path, enable_coinbase_ws_rest_repairs=False)
    assert cb("worker", threading.Event()) == "cb"
    assert captured["http_session"] is None
