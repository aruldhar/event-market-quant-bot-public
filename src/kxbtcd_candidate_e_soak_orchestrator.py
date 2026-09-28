"""The sole observed lifecycle entry point for the read-only soak runtime."""
from __future__ import annotations

from .kxbtcd_candidate_e_soak_observability import run_observed_soak
from .kxbtcd_candidate_e_soak_package import SoakPackageError


class SoakOrchestratorError(RuntimeError):
    pass


def run_packaged_observed_soak(*, core, producers, observability, close_runtime_artifacts,
                              run_coinbase_supervisor, run_kalshi_supervisor, **kwargs):
    """Start sources only through the mandatory durable observed lifecycle."""
    if core is None or producers is None or observability is None:
        raise SoakOrchestratorError("core, producers, and observability are required")
    if core.metric_producers is not producers or core.observability is not observability:
        raise SoakOrchestratorError("runtime core is not bound to required observability")
    if observability.sample_metrics is not producers.sample:
        # Bound methods are distinct objects on access; compare their owners.
        if getattr(observability.sample_metrics, "__self__", None) is not producers:
            raise SoakOrchestratorError("observer does not sample runtime producers")
    if not callable(close_runtime_artifacts):
        raise SoakOrchestratorError("verified raw closure is required")
    return run_observed_soak(observability=observability,
        close_runtime_artifacts=close_runtime_artifacts,
        run_coinbase_supervisor=run_coinbase_supervisor,
        run_kalshi_supervisor=run_kalshi_supervisor, **kwargs)
