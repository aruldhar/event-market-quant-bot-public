from src import kxbtcd_candidate_e_soak_live_dependencies as dependencies


def test_live_dependencies_compose_existing_factories_without_invoking_them(monkeypatch):
    calls = []
    monkeypatch.setattr(dependencies, "assemble_read_only_transport_callbacks", lambda **kw: calls.append(("transport", kw)) or ("cb", "ka", "rest"))
    monkeypatch.setattr(dependencies, "assemble_read_only_supervisors", lambda **kw: calls.append(("supervisor", kw)) or ("cb-supervisor", "ka-supervisor"))
    monkeypatch.setattr(dependencies, "run_v2_coinbase_input_supervisor", lambda **kw: calls.append(("v2", kw)) or "v2")
    coinbase, kalshi = dependencies.build_read_only_supervisors(core="core", http_session="http", repo_root="repo")
    assert kalshi == "ka-supervisor"
    assert calls[0][0] == "transport"
    assert calls[0][1]["http_session"] == "http"
    assert calls[0][1]["repo_root"] == "repo"
    assert calls[0][1]["enable_coinbase_ws_rest_repairs"] is False
    assert calls[0][1]["settlement_http_session"] != "http"
    assert calls[1][1]["run_coinbase_generation"] == "cb"
    assert coinbase("stop") == "v2"
    assert calls[2][0] == "v2"
    assert calls[2][1]["run_ws_archive_supervisor"] == "cb-supervisor"
