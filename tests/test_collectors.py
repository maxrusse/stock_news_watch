from __future__ import annotations

import unittest

import stock_news_watch.news as news_mod
from stock_news_watch.news import NewsItem


class CollectorTests(unittest.TestCase):
    def test_collect_news_bundle_includes_yahoo_items(self) -> None:
        original_fetch_yahoo = news_mod.fetch_yahoo_news
        original_fetch_google = news_mod.fetch_google_news
        original_resolve = news_mod.resolve_sec_cik
        original_fetch_sec = news_mod.fetch_sec_company_filings
        original_collect_company = news_mod.collect_company_page
        try:
            news_mod.fetch_yahoo_news = lambda symbol, rss_base: [
                NewsItem(symbol=symbol, title=f"{symbol} yahoo headline", source="yahoo-finance", url=f"https://example.com/{symbol}", summary="yahoo")
            ]
            news_mod.fetch_google_news = lambda query, symbol, rss_base: []
            news_mod.resolve_sec_cik = lambda symbol: None
            news_mod.fetch_sec_company_filings = lambda symbol, cik, forms, max_items=8: []
            news_mod.collect_company_page = lambda symbol, url: []

            bundle = news_mod.collect_news_bundle(
                ["MSFT"],
                {
                    "news_google_rss_base": "https://news.google.com/rss/search?q={query}",
                    "yahoo_rss_base": "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
                    "google_queries": {"MSFT": []},
                    "sec_forms": ["8-K"],
                    "company_pages": {},
                },
            )
            self.assertEqual(len(bundle), 1)
            self.assertEqual(bundle[0].source, "yahoo-finance")
        finally:
            news_mod.fetch_yahoo_news = original_fetch_yahoo
            news_mod.fetch_google_news = original_fetch_google
            news_mod.resolve_sec_cik = original_resolve
            news_mod.fetch_sec_company_filings = original_fetch_sec
            news_mod.collect_company_page = original_collect_company


if __name__ == "__main__":
    unittest.main()

