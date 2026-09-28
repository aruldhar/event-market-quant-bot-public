from decimal import Decimal

from src.kxbtcd_candidate_e_shadow_micro_hybrid_scenario import (
    ShadowHybridExitObservation,
)
from src.kxbtcd_candidate_e_shadow_scenario_cli import main, parse_args
from src.kxbtcd_candidate_e_v2_micro_hybrid_state_machine_offline import HybridProbeState


def test_parser_requires_explicit_archived_inputs_and_parses_fixed_point_values():
    args = parse_args((
        "--descriptor", "one.descriptor.json", "--subscribed-ticker", "T1",
        "--market-ticker", "T1", "--remaining-quantity", "0.01",
        "--realized-net-proceeds", "0", "--supplied-exit-fee", "0.0001",
        "--required-total-net-proceeds", "0.008",
    ))
    assert args.descriptor == ["one.descriptor.json"]
    assert args.remaining_quantity == Decimal("0.01")


def test_cli_prints_observations_only_and_never_requires_a_venue(monkeypatch, capsys):
    captured = {}
    observation = ShadowHybridExitObservation(
        market_ticker="T1", received_utc="2026-09-08T00:00:00Z",
        received_monotonic_ns=7,
        state=HybridProbeState.CANCEL_RECONCILIATION_REQUIRED,
        full_exit_eligible=True, worst_price_required=Decimal("0.80"),
        total_net_proceeds_if_filled=Decimal("0.008"),
    )

    def fake_runner(*args, **kwargs):
        captured.update(kwargs)
        return iter((observation,))

    import src.kxbtcd_candidate_e_shadow_scenario_cli as cli
    monkeypatch.setattr(cli, "iter_verified_hybrid_exit_observations", fake_runner)
    assert main((
        "--descriptor", "one.descriptor.json", "--subscribed-ticker", "T1",
        "--market-ticker", "T1", "--remaining-quantity", "0.01",
        "--realized-net-proceeds", "0", "--supplied-exit-fee", "0.0001",
        "--required-total-net-proceeds", "0.008",
    )) == 0
    assert captured["market_ticker"] == "T1"
    assert '"full_exit_eligible": true' in capsys.readouterr().out
