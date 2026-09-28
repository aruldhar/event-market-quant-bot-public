import json
from pathlib import Path


def _dashboard(name: str):
    return json.loads(Path(f"deploy/grafana/dashboards/{name}").read_text(encoding="utf-8"))


def test_overview_dashboard_has_five_policy_leaderboard_and_scenario_drilldown():
    dashboard = _dashboard("candidate-e-shadow-overview.json")
    assert dashboard["uid"] == "candidate-e-shadow"
    assert dashboard["editable"] is False
    assert "scenario-lab" in dashboard["tags"]
    panel = next(item for item in dashboard["panels"] if item["id"] == 5)
    query = panel["targets"][0]["rawQueryText"]
    assert "scenario_catalog" in query
    assert "LEFT JOIN trades" in query
    assert "${run_id:sqlstring}" in query
    assert "ORDER BY c.edge_threshold" in query
    links = panel["fieldConfig"]["overrides"][0]["properties"][0]["value"]
    assert links[0]["url"].startswith("/d/candidate-e-scenario/")
    assert "${__value.raw}" in links[0]["url"]


def test_overview_dashboard_compares_cumulative_pnl_across_all_five_scenarios():
    dashboard = _dashboard("candidate-e-shadow-overview.json")
    panel = next(item for item in dashboard["panels"] if item["id"] == 8)
    assert panel["title"] == "All Five Scenarios — Cumulative Simulated P&L"
    query = panel["targets"][0]["rawQueryText"]
    assert "PARTITION BY scenario_id" in query
    assert "scenario_id AS metric" in query
    assert "simulated_flat = 1" in query


def test_scenario_detail_dashboard_filters_every_query_by_escaped_selected_scenario():
    dashboard = _dashboard("candidate-e-scenario-detail.json")
    assert dashboard["uid"] == "candidate-e-scenario"
    variables = dashboard["templating"]["list"]
    assert len(variables) == 2
    assert variables[0]["name"] == "run_id"
    assert variables[0]["current"]["value"] == "__current__"
    assert variables[0]["includeAll"] is True
    assert variables[1]["name"] == "scenario_id"
    assert variables[1]["current"]["value"] == "edge_002"
    queries = [
        target["rawQueryText"]
        for panel in dashboard["panels"]
        if panel["id"] != 4
        for target in panel.get("targets", [])
    ]
    assert any("Cumulative Simulated P&L" == panel["title"].split(" — ")[-1] for panel in dashboard["panels"])
    assert all("${scenario_id:sqlstring}" in query for query in queries)
    assert all("${run_id:sqlstring}" in query for query in queries)
    assert all("scenario_id = '$scenario_id'" not in query for query in queries)
    assert any("shadow_events" in query for query in queries)
    assert any("trades" in query for query in queries)


def test_overview_defaults_to_the_current_run_but_can_select_retained_history():
    dashboard = _dashboard("candidate-e-shadow-overview.json")
    variable = dashboard["templating"]["list"][0]
    assert variable["name"] == "run_id"
    assert variable["current"]["value"] == "__current__"
    assert variable["includeAll"] is True
    assert "Current run" in variable["query"]
    assert all(
        "${run_id:sqlstring}" in target["rawQueryText"]
        for panel in dashboard["panels"]
        if panel["id"] != 4
        for target in panel.get("targets", [])
    )


def test_trade_tables_show_simulated_entry_and_remaining_position_size():
    overview = _dashboard("candidate-e-shadow-overview.json")
    scenario = _dashboard("candidate-e-scenario-detail.json")

    for dashboard in (overview, scenario):
        panel = next(item for item in dashboard["panels"] if item["id"] == 6)
        query = panel["targets"][0]["rawQueryText"]
        assert "Entry Qty" in query
        assert "Open Qty" in query
        assert "Simulated Entry Outlay" in query
        assert "shadow_events" in query
        assert "e.side = 'buy'" in query


def test_shadow_health_dashboard_exposes_snapshot_liveness_without_claiming_source_readiness():
    dashboard = _dashboard("candidate-e-shadow-health.json")
    assert dashboard["uid"] == "candidate-e-shadow-health"
    assert dashboard["editable"] is False
    assert "health" in dashboard["tags"]

    panels = {item["title"]: item for item in dashboard["panels"]}
    assert {"Current Shadow Run", "Latest Shadow Input Age", "Shadow Input Status"} <= set(panels)
    status_query = panels["Shadow Input Status"]["targets"][0]["rawQueryText"]
    assert "LIVE" in status_query
    assert "STALE" in status_query
    assert "STOPPED OR STALE" in status_query
    assert "generated_utc" in status_query
    metadata_description = panels["Shadow Pipeline Metadata"]["description"]
    assert "shadow path only" in metadata_description


def test_scenario_detail_audits_observed_probability_and_exit_requirement():
    dashboard = _dashboard("candidate-e-scenario-detail.json")
    panel = next(
        item for item in dashboard["panels"]
        if item["title"] == "Decision Audit — Observed Probability and Exit Requirement"
    )
    query = panel["targets"][0]["rawQueryText"]
    assert "Observed Market Probability" in query
    assert "Simulated Fill Probability" in query
    assert "Entry Limit Probability" in query
    assert "Hypothetical Resting Exit Limit Probability (Not Placed)" in query
    assert "Entry Number" in query
    assert "Re-arm Reason" in query
    assert "Required Net Exit Proceeds" in query
    assert "Visible Net Exit Proceeds" in query
    assert "json_extract(payload_json" in query
    assert "no resting order is placed" in panel["description"]
    assert "at most once" in panel["description"]


def test_scenario_detail_explains_zero_trade_snapshots_from_bounded_diagnostics():
    dashboard = _dashboard("candidate-e-scenario-detail.json")
    panel = next(
        item for item in dashboard["panels"]
        if item["title"] == "Decision-Rejection Diagnostics"
    )
    query = panel["targets"][0]["rawQueryText"]
    assert "decision_diagnostics" in query
    assert "Outside T-55 to T-10" in query
    assert "Edge Below Threshold" in query
    assert "Closest Edge Deficit" in query
    assert "${scenario_id:sqlstring}" in query
    assert "${run_id:sqlstring}" in query
