"""Create an offline terminal-read-only-soak acceptance receipt from JSON evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .kxbtcd_candidate_e_read_only_soak_acceptance import accept_terminal_read_only_soak


def _load(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as source:
        parsed = json.load(source)
    if not isinstance(parsed, dict):
        raise ValueError("evidence JSON must be an object")
    return parsed


def create_acceptance_receipt(*, summary_path: Path, manifest_path: Path, output_path: Path) -> dict[str, str]:
    receipt = accept_terminal_read_only_soak(summary=_load(summary_path), manifest=_load(manifest_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps({"accepted_soak_run_id": receipt.run_id}, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return {"accepted_soak_run_id": receipt.run_id}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    create_acceptance_receipt(summary_path=args.summary, manifest_path=args.manifest, output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
