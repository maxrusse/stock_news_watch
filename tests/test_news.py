from __future__ import annotations

import unittest

from stock_news_watch.news import parse_rss_feed


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


if __name__ == "__main__":
    unittest.main()

