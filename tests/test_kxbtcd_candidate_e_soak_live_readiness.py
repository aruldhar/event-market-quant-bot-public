from src import kxbtcd_candidate_e_soak_live_readiness as readiness


def test_live_sampler_composes_identity_clock_and_both_source_evidence(monkeypatch):
    captured = {}
    class Coordinator:
        def __init__(self, **kwargs): captured["boot"] = kwargs["expected_boot_id"]
        def evaluate(self, **kwargs): captured.update(kwargs); return "result"
    monkeypatch.setattr(readiness, "SoakReadinessCoordinator", Coordinator)
    identity = type("Identity", (), {"boot_id": "boot", "time_namespace_id": "time:[1]"})()
    producers = type("Producers", (), {"identity_resolver": lambda self: identity,
        "clock_evidence_path": "clock", "clock_file_evaluator": lambda *args, **kwargs: "clock"})()
    def websocket_evidence_must_not_be_used(*args, **kwargs):
        raise AssertionError("V2 readiness must not evaluate Coinbase WebSocket evidence")
    core = type("Core", (), {"evaluate_v2_coinbase_rest_candle": lambda self, **kwargs: "coinbase",
        "evaluate_coinbase": websocket_evidence_must_not_be_used,
        "evaluate_kalshi": lambda self, **kwargs: "kalshi"})()
    sample = readiness.build_live_readiness_sampler(core=core, producers=producers,
        expected_boot_id="boot", epoch_seconds=lambda: 9)
    assert sample(7) == "result"
    assert captured["identity"] is identity
    assert captured["clock"] == "clock"
    assert captured["coinbase"] == "coinbase"
    assert captured["kalshi"] == "kalshi"


def test_live_sampler_resamples_monotonic_time_immediately_before_each_source_evaluation(monkeypatch):
    # Identity/clock evaluation happens first and takes real wall-clock time.
    # The Coinbase and Kalshi worker threads each record their own monotonic
    # timestamps (a fetched REST candle's availability, a WS pong)
    # concurrently with this sampling cycle, so reusing the cycle's initial
    # now_monotonic_ns snapshot for either comparison can go stale and falsely
    # trip V2_REST_CANDLE_MONOTONIC_INVARIANT_FAILURE or
    # KALSHI_TRANSPORT_MONOTONIC_INVARIANT_FAILURE. Both Coinbase and Kalshi
    # must always be evaluated against a freshly sampled monotonic time, not
    # the stale cycle-start snapshot -- a prior version of this fix only
    # covered Kalshi and left Coinbase's call site on the stale snapshot,
    # which is exactly what killed the 24-hour run kxbtcd_soak_20260911_24h_4.
    captured = {}
    monkeypatch.setattr(readiness, "SoakReadinessCoordinator",
        lambda **kwargs: type("C", (), {"evaluate": lambda self, **kw: "result"})())
    identity = type("Identity", (), {"boot_id": "boot", "time_namespace_id": "time:[1]"})()
    producers = type("Producers", (), {"identity_resolver": lambda self: identity,
        "clock_evidence_path": "clock", "clock_file_evaluator": lambda *args, **kwargs: "clock"})()

    def evaluate_v2_coinbase_rest_candle(self, **kwargs):
        captured["coinbase_now_monotonic_ns"] = kwargs["now_monotonic_ns"]
        return "coinbase"

    def evaluate_kalshi(self, **kwargs):
        captured["kalshi_now_monotonic_ns"] = kwargs["now_monotonic_ns"]
        return "kalshi"

    core = type("Core", (), {"evaluate_v2_coinbase_rest_candle": evaluate_v2_coinbase_rest_candle,
        "evaluate_kalshi": evaluate_kalshi})()

    # Simulate both worker threads advancing the clock between the cycle's
    # initial snapshot (100) and the moment each source is actually evaluated.
    fresh_monotonic_values = iter([400, 500])
    sample = readiness.build_live_readiness_sampler(
        core=core, producers=producers, expected_boot_id="boot", epoch_seconds=lambda: 9,
        monotonic_ns=lambda: next(fresh_monotonic_values),
    )
    sample(100)
    assert captured["coinbase_now_monotonic_ns"] == 400
    assert captured["kalshi_now_monotonic_ns"] == 500
