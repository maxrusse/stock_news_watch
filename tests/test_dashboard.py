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
            snapshot["heartbeat"] = {**snapshot.get("heartbeat", {}), "status": "running", "overall_label": "Mixed / watch", "overall_score": 3}
            snapshot["assessment"] = {
                **snapshot.get("assessment", {}),
                "overall_label": "Mixed / watch",
                "overall_score": 3,
                "briefs": [
                    {
                        "symbol": "MSFT",
                        "score": 3,
                        "label": "Mixed / watch",
                        "takeaway": "Microsoft looks mostly routine right now.",
                        "why_it_matters": "Nothing here reads like a near-term problem, so the stock is mostly in watch mode.",
                        "summary": "Microsoft looks mostly routine right now.",
                        "source_count": 2,
                        "item_count": 3,
                        "themes": ["product update", "analyst chatter"],
                        "sources": ["reuters", "apple.com/newsroom"],
                        "critical_notes": ["No clear material problem in the current bundle."],
                        "routine_notes": ["A lot of the items look like ordinary product or coverage noise."],
                        "top_headlines": [
                            {
                                "title": "Microsoft updates product roadmap",
                                "source": "reuters",
                                "url": "https://example.com/msft-1",
                                "published_utc": "2026-05-23T10:00:00Z",
                                "kind": "news",
                                "tone": "neutral",
                                "why": "Routine product news, not a direct warning.",
                            }
                        ],
                    }
                ],
            }
            html = render_dashboard_html(snapshot, refresh_seconds=10)
            self.assertIn("stock_news_watch", html)
            self.assertIn("One tab per stock", html)
            self.assertIn("Codex reads the live evidence", html)
            self.assertIn("Why it matters", html)
            self.assertIn("Important vs routine", html)
            self.assertIn("Mixed / watch", html)


if __name__ == "__main__":
    unittest.main()
