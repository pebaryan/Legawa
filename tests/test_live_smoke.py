from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from typer.testing import CliRunner

SRC = Path(__file__).resolve().parents[1] / "src"
ROOT = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from legawa.cli import app


LIVE_SMOKE = os.environ.get("LEGAWA_LIVE_SMOKE", "").strip().lower() in {"1", "true", "yes", "on"}


@unittest.skipUnless(LIVE_SMOKE, "set LEGAWA_LIVE_SMOKE=1 to run against real local endpoints")
class LiveSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_health_against_real_services(self) -> None:
        result = self.runner.invoke(app, ["health"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("OK pasal.id", result.output)
        self.assertIn("OK big", result.output)
        self.assertIn("OK small", result.output)

    def test_draft_against_real_services(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "ibam-it-audit-perspective.txt").read_text(encoding="utf-8")
        result = self.runner.invoke(
            app,
            [
                "draft",
                "memo_kebijakan",
                "audit teknis dan tata kelola perangkat digital pada Kasus Ibam",
                "--no-research",
                "--instruksi",
                source,
            ],
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertGreater(len(result.output.strip()), 200)
        self.assertIn("TL;DR", result.output)


if __name__ == "__main__":
    unittest.main()
