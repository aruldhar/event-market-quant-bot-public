"""Fail-closed command boundary for the eventual read-only soak runner.

This module deliberately contains no transport imports.  A caller must make a
visible, two-part choice before it may hand control to a live runner; ordinary
packaging and clock-preflight invocations remain network-free.
"""
from __future__ import annotations

import argparse
from typing import Callable


class SoakRuntimeCommandError(RuntimeError):
    pass


def parse_runtime_command(argv=None):
    parser = argparse.ArgumentParser(description="Candidate-E read-only soak command gate")
    parser.add_argument("--mode", choices=("preflight", "read-only-live"), default="preflight")
    parser.add_argument("--enable-read-only-live", action="store_true")
    return parser.parse_args(argv)


def dispatch_runtime_command(*, argv=None, run_preflight: Callable[[], object],
                             run_read_only_live: Callable[[], object]):
    """Dispatch only after an explicit live-read-only acknowledgement.

    The live callable is injected so this safety boundary is independently
    testable and cannot import or open a transport during argument validation.
    """
    # A programmatic caller must not accidentally inherit the parent process
    # arguments (for example pytest's ``-q`` and test paths). The executable
    # CLI passes its own explicit argv list.
    args = parse_runtime_command([] if argv is None else argv)
    if args.mode == "preflight":
        return run_preflight()
    if not args.enable_read_only_live:
        raise SoakRuntimeCommandError(
            "read-only-live mode requires --enable-read-only-live")
    return run_read_only_live()
