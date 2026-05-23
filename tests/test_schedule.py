from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
import tempfile

from stock_news_watch.config import AppConfig
from stock_news_watch.engine import StockNewsWatchEngine


class ScheduleTests(unittest.TestCase):
    def test_market_window_weekday_preopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig.from_file(Path("config/stock_news_watch.json"))
            config = AppConfig(
                workspace_root=Path(tmp),
                runtime_dir=Path(".runtime"),
                codex=config.codex,
                runtime=config.runtime,
                dashboard=config.dashboard,
                sources=config.sources,
                watch_terms=config.watch_terms,
            )
            engine = StockNewsWatchEngine(config)
            dt = datetime(2026, 5, 22, 8, 45, tzinfo=engine._market_zone())
            active, local = engine._market_window(dt)
            self.assertTrue(active)
            self.assertEqual(local.tzname(), "EDT")

    def test_always_on_mode_opens_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = AppConfig.from_file(Path("config/stock_news_watch.json"))
            config = AppConfig(
                workspace_root=Path(tmp),
                runtime_dir=Path(".runtime"),
                codex=base.codex,
                runtime=type(base.runtime)(
                    poll_seconds=base.runtime.poll_seconds,
                    run_interval_seconds=base.runtime.run_interval_seconds,
                    schedule_mode="always_on",
                    stop_when_outside_market_hours=base.runtime.stop_when_outside_market_hours,
                    market_timezone=base.runtime.market_timezone,
                    preopen_start=base.runtime.preopen_start,
                    market_open=base.runtime.market_open,
                    market_close=base.runtime.market_close,
                ),
                dashboard=base.dashboard,
                sources=base.sources,
                watch_terms=base.watch_terms,
            )
            engine = StockNewsWatchEngine(config)
            dt = datetime(2026, 5, 24, 3, 0, tzinfo=engine._market_zone())
            active, _ = engine._market_window(dt)
            self.assertTrue(active)


if __name__ == "__main__":
    unittest.main()
