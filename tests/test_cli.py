from __future__ import annotations

import unittest

from stock_news_watch.cli import run_startup_cycle


class FakeEngine:
    def __init__(self) -> None:
        self.calls = []

    def run_cycle(self, force: bool = False):
        self.calls.append(force)
        return {"ok": True}


class CliTests(unittest.TestCase):
    def test_run_startup_cycle_runs_once(self) -> None:
        engine = FakeEngine()
        result = run_startup_cycle(engine)
        self.assertEqual(engine.calls, [True])
        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()

