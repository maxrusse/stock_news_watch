from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from stock_news_watch.config import AppConfig
from stock_news_watch.dashboard import render_dashboard_html
from stock_news_watch.engine import StockNewsWatchEngine


class DashboardTests(unittest.TestCase):
    def test_render_contains_heartbeat_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_config = AppConfig.from_file(Path("config/stock_news_watch.json"))
            config = AppConfig(
                workspace_root=Path(tmp),
                runtime_dir=Path(".runtime"),
                codex=base_config.codex,
                runtime=base_config.runtime,
                dashboard=base_config.dashboard,
                sources=base_config.sources,
                watch_terms=base_config.watch_terms,
            )
            engine = StockNewsWatchEngine(config)
            snapshot = engine.snapshot()
            html = render_dashboard_html(snapshot, refresh_seconds=10)
            self.assertIn("stock_news_watch", html)
            self.assertIn("Select stock", html)
            self.assertIn("weekly and monthly read", html)
            self.assertIn("Mixed / watch", html)


if __name__ == "__main__":
    unittest.main()
