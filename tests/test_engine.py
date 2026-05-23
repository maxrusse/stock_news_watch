from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_news_watch.codex_client import ReviewResult
from stock_news_watch.config import AppConfig
from stock_news_watch.engine import StockNewsWatchEngine
from stock_news_watch.news import NewsItem


class FakeReviewer:
    def __init__(self, result: ReviewResult) -> None:
        self.result = result

    def review(self, **kwargs):
        return self.result


class EngineTests(unittest.TestCase):
    def test_cycle_writes_heartbeat_and_event(self) -> None:
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

            def fake_collect(*args, **kwargs):
                return [
                    NewsItem(symbol="MSFT", title="Microsoft warns of guidance cut", source="rss", url="https://example.com/1", summary="guidance cut"),
                    NewsItem(symbol="AAPL", title="Apple launches new product", source="rss", url="https://example.com/2", summary=""),
                ]

            engine.policy.approve("write_state", engine.paths.state_file)
            engine.policy.approve("write_heartbeat", engine.paths.heartbeat_file)

            import stock_news_watch.engine as engine_mod

            original_collect = engine_mod.collect_news_bundle
            original_reviewer = engine_mod.CodexReviewer
            try:
                engine_mod.collect_news_bundle = lambda *args, **kwargs: fake_collect()

                class _FakeReviewer:
                    def __init__(self, *args, **kwargs):
                        pass

                    def review(self, **kwargs):
                        return ReviewResult(
                            overall_status="critical",
                            alert=True,
                            overall_score=5,
                            overall_label="Critical sell",
                            summary="critical negative flags detected",
                            reasons=["MSFT guidance cut"],
                            signals=[{"symbol": "MSFT", "severity": "critical", "title": "Microsoft warns of guidance cut", "url": "https://example.com/1", "why": "guidance cut"}],
                            sources_reviewed=["rss"],
                            decision_source="codex",
                            model="gpt-5.4-mini",
                            briefs=[{"symbol": "MSFT", "score": 5, "label": "Critical sell", "summary": "MSFT is critical sell.", "source_count": 1, "item_count": 1, "themes": ["guidance cut"], "sources": ["rss"], "top_headlines": []}],
                        )

                engine_mod.CodexReviewer = _FakeReviewer

                snapshot = engine.run_cycle(force=True)
                self.assertEqual(snapshot["state"]["status"], "alerting")
                self.assertTrue(snapshot["heartbeat"]["alert"])
                self.assertGreaterEqual(snapshot["state"]["cycle_count"], 1)
            finally:
                engine_mod.collect_news_bundle = original_collect
                engine_mod.CodexReviewer = original_reviewer


if __name__ == "__main__":
    unittest.main()
