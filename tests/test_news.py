from __future__ import annotations

import unittest

from stock_news_watch.news import NewsItem, aggregate_symbol_briefs, parse_rss_feed


RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Microsoft warns of revenue decline in key unit</title>
      <link>https://example.com/microsoft-warning</link>
      <description>Revenue decline and guidance cut</description>
      <pubDate>Mon, 12 May 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class NewsParsingTests(unittest.TestCase):
    def test_parse_rss_feed(self) -> None:
        items = parse_rss_feed(RSS_SAMPLE, symbol="MSFT", source="rss")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Microsoft warns of revenue decline in key unit")
        self.assertEqual(items[0].source, "rss")

    def test_aggregate_symbol_briefs(self) -> None:
        items = [
            NewsItem(symbol="MSFT", title="Microsoft faces lawsuit over cloud licenses", source="reuters", url="https://example.com/1", summary="lawsuit"),
            NewsItem(symbol="MSFT", title="Microsoft restores service after outage", source="ap", url="https://example.com/2", summary="outage"),
            NewsItem(symbol="AAPL", title="Apple reports results and raises guidance", source="apple", url="https://example.com/3", summary="raises guidance"),
        ]
        briefs = aggregate_symbol_briefs(items)
        self.assertEqual(briefs[0]["symbol"], "MSFT")
        self.assertGreaterEqual(briefs[0]["score"], 4)
        self.assertIn("Likely bad", briefs[0]["label"])
        self.assertIn("lawsuit", briefs[0]["summary"])
        self.assertEqual(briefs[-1]["symbol"], "AAPL")
        self.assertLessEqual(briefs[-1]["score"], 3)


if __name__ == "__main__":
    unittest.main()
