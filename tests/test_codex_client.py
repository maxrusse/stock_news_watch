from __future__ import annotations

import unittest

from stock_news_watch.codex_client import _normalize_review
from stock_news_watch.news import NewsItem, build_symbol_bundles


class CodexClientTests(unittest.TestCase):
    def test_normalize_review_fills_missing_briefs(self) -> None:
        items = [
            NewsItem(symbol="MSFT", title="Microsoft faces guidance cut", source="reuters", url="https://example.com/msft", summary="guidance cut"),
            NewsItem(symbol="AAPL", title="Apple launches product update", source="ap", url="https://example.com/aapl", summary="product update"),
        ]
        bundles = build_symbol_bundles(items)
        parsed = {
            "overall_status": "watch",
            "alert": False,
            "overall_score": 9,
            "overall_label": "",
            "summary": "",
            "reasons": ["MSFT guidance cut"],
            "signals": [],
            "sources_reviewed": [],
            "briefs": [
                {
                    "symbol": "MSFT",
                    "score": 8,
                    "label": "",
                    "summary": "MSFT is mixed.",
                    "source_count": 1,
                    "item_count": 1,
                    "themes": [],
                    "sources": [],
                    "top_headlines": [],
                }
            ],
        }

        result = _normalize_review(parsed, items=items, symbols=["MSFT", "AAPL"], bundles=bundles, model="gpt-5.4-mini")

        self.assertEqual(result.overall_score, 6)
        self.assertEqual(result.overall_label, "Likely bad within weeks")
        self.assertEqual(len(result.briefs), 2)
        self.assertEqual(result.briefs[0]["symbol"], "MSFT")
        self.assertEqual(result.briefs[0]["score"], 6)
        self.assertEqual(result.briefs[0]["label"], "Likely bad within weeks")
        self.assertIn("why_it_matters", result.briefs[0])
        self.assertEqual(result.briefs[1]["symbol"], "AAPL")
        self.assertEqual(result.briefs[1]["score"], 3)
        self.assertEqual(result.briefs[1]["label"], "Mixed / watch")
        self.assertGreater(len(result.briefs[1]["top_headlines"]), 0)


if __name__ == "__main__":
    unittest.main()
