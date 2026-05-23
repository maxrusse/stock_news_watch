from __future__ import annotations

import unittest

from stock_news_watch.news import NewsItem, build_symbol_bundles, parse_rss_feed


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

    def test_build_symbol_bundles(self) -> None:
        items = [
            NewsItem(symbol="MSFT", title="Microsoft faces lawsuit over cloud licenses", source="reuters", url="https://example.com/1", summary="lawsuit"),
            NewsItem(symbol="MSFT", title="Microsoft restores service after outage", source="ap", url="https://example.com/2", summary="outage"),
            NewsItem(symbol="AAPL", title="Apple reports results and raises guidance", source="apple", url="https://example.com/3", summary="raises guidance"),
        ]
        bundles = build_symbol_bundles(items)
        self.assertEqual(bundles[0]["symbol"], "AAPL")
        self.assertEqual(bundles[1]["symbol"], "MSFT")
        self.assertEqual(bundles[1]["item_count"], 2)
        self.assertEqual(bundles[1]["source_count"], 2)
        self.assertIn("https://example.com/1", {item["url"] for item in bundles[1]["items"]})


if __name__ == "__main__":
    unittest.main()
