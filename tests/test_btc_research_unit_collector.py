from __future__ import annotations

import unittest
from pathlib import Path


class BtcResearchUnitCollectorReportingTests(unittest.TestCase):
    def test_manifest_terminal_output_uses_collection_manifest_attribute(self):
        repository_root = Path(__file__).resolve().parents[1]
        source = (
            repository_root / "collect_btc_research_unit_inventory.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'print(f"Manifest: {manifest.manifest_path}")',
            source,
        )
        self.assertNotIn(
            'print(f"Manifest: {manifest.path}")',
            source,
        )


if __name__ == "__main__":
    unittest.main()
