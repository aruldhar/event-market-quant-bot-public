"""Runtime-owned producers for the durable soak-observability consumer.

These counters are deliberately updated only by runtime-core ingress and
lifecycle calls.  They are not a fixture-shaped dictionary: tests drive them
through the same REST and WebSocket adapters used by the packaged runtime.
"""
from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import time
from typing import Callable

from .kxbtcd_candidate_e_clock_evidence_bridge import evaluate_clock_evidence_file
from .kxbtcd_candidate_e_soak_linux_runtime_identity import resolve_production_runtime_identity
from .kxbtcd_candidate_e_soak_observability import COUNTERS, GAUGES, SoakObservabilityError
from .kxbtcd_candidate_e_restart_gate_state_machine import GateStatus

try:  # resource is Linux/Unix-only; offline Windows tests inject a reader.
    import resource
except ImportError:  # pragma: no cover - platform boundary
    resource = None


class RuntimeMetricProducers:
    """Cumulative source/storage counters plus fail-closed host sampling."""

    def __init__(self, *, archive_root, clock_evidence_path, monotonic_ns=time.monotonic_ns,
                 identity_resolver=resolve_production_runtime_identity,
                 clock_file_evaluator=evaluate_clock_evidence_file,
                 getrusage=None, getloadavg=None,
                 disk_usage=None, sysconf=None, storage_totals=None):
        self.archive_root = Path(archive_root)
        self.clock_evidence_path = Path(clock_evidence_path)
        self.monotonic_ns = monotonic_ns
        self.identity_resolver = identity_resolver
        self.clock_file_evaluator = clock_file_evaluator
        self.getrusage = getrusage or (resource.getrusage if resource is not None else None)
        self.getloadavg = getloadavg or getattr(os, "getloadavg", None)
        self.disk_usage = disk_usage
        self.sysconf = sysconf or getattr(os, "sysconf", None)
        self.storage_totals = storage_totals
        self.counters = Counter({name: 0 for name in COUNTERS})
        self.generations = {"coinbase": None, "kalshi": None}

    def increment(self, name, amount=1):
        if name not in COUNTERS or not isinstance(amount, int) or amount < 0:
            raise SoakObservabilityError("invalid runtime metric increment")
        self.counters[name] += amount

    def generation_opened(self, source, generation):
        if source not in self.generations or not isinstance(generation, int) or generation < 1:
            raise SoakObservabilityError("invalid source generation")
        prior = self.generations[source]
        if prior is not None and generation <= prior:
            raise SoakObservabilityError("source generation regressed")
        self.generations[source] = generation

    def _storage_totals(self):
        if self.storage_totals is not None:
            return self.storage_totals()
        raw = compressed = 0
        if self.archive_root.exists():
            for path in self.archive_root.rglob("*"):
                if not path.is_file():
                    continue
                if path.name.endswith(".jsonl"):
                    raw += path.stat().st_size
                elif path.name.endswith(".jsonl.zst"):
                    compressed += path.stat().st_size
        return raw, compressed

    def sample(self, now_ns):
        identity = self.identity_resolver()
        if identity.status != GateStatus.PASS or not identity.boot_id or not identity.time_namespace_id:
            raise SoakObservabilityError("production Linux identity unavailable")
        # ``now_ns`` comes from the runner's current iteration, while the host
        # can atomically replace the clock file between that capture and this
        # read.  Evaluate against a fresh local monotonic reading and retry the
        # one benign replacement race once.  A persistent negative age remains
        # explicit blocked clock evidence; it is never invented as age zero.
        clock_now_ns = max(int(now_ns), int(self.monotonic_ns()))
        clock = self.clock_file_evaluator(self.clock_evidence_path, now_monotonic_ns=clock_now_ns,
            current_boot_id=identity.boot_id, current_time_namespace_id=identity.time_namespace_id)
        if getattr(clock, "reason", None) == "CLOCK_EVIDENCE_NEGATIVE_AGE":
            retry_now_ns = max(clock_now_ns, int(self.monotonic_ns()))
            clock = self.clock_file_evaluator(self.clock_evidence_path, now_monotonic_ns=retry_now_ns,
                current_boot_id=identity.boot_id, current_time_namespace_id=identity.time_namespace_id)
        raw, compressed = self._storage_totals()
        if self.getrusage is None or self.getloadavg is None or self.sysconf is None:
            raise SoakObservabilityError("Linux resource sampler unavailable")
        usage = self.getrusage(resource.RUSAGE_SELF if resource is not None else 0)
        load1, load5, load15 = self.getloadavg()
        available = int(self.sysconf("SC_AVPHYS_PAGES")) * int(self.sysconf("SC_PAGE_SIZE"))
        disk = self.disk_usage(self.archive_root) if self.disk_usage else os.statvfs(self.archive_root)
        free = int(disk.free if hasattr(disk, "free") else disk.f_bavail * disk.f_frsize)
        value = dict(self.counters)
        # Storage is sampled from the source-owned cumulative accounting (or,
        # before runtime-core binding, from the archive inventory).  It is not
        # a mutable fixture counter and must replace the initial zero values.
        value["raw_bytes_written"] = raw
        value["compressed_bytes_written"] = compressed
        value.update(process_cpu_seconds=float(usage.ru_utime + usage.ru_stime),
            process_memory_rss_bytes=int(usage.ru_maxrss) * 1024,
            host_memory_available_bytes=available, host_load_1m=float(load1), host_load_5m=float(load5),
            host_load_15m=float(load15), filesystem_free_bytes=free,
            coinbase_connection_generation=self.generations["coinbase"],
            kalshi_connection_generation=self.generations["kalshi"], linux_boot_id=identity.boot_id,
            time_namespace_id=identity.time_namespace_id, clock_status=("PASS" if clock.status == GateStatus.PASS else "FATAL" if clock.status == GateStatus.FATAL else "BLOCKED"),
            clock_evidence_age_ns=clock.evidence_age_ns,
            chrony_signed_offset_ms=clock.chrony.signed_system_time_offset_ms,
            chrony_absolute_offset_ms=clock.chrony.absolute_system_time_offset_ms,
            chrony_leap_status=clock.chrony.leap_status)
        return value
