from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


USER_AGENT = "stock_news_watch/0.1 (+https://github.com/)"
SEC_HEADERS = {
    "User-Agent": "stock_news_watch demo contact@openai.com",
    "Accept-Encoding": "gzip, deflate",
    "Host": "www.sec.gov",
}

SCALE_LABELS = {
    1: "Strong positive",
    2: "Okay",
    3: "Beware / short-term hype",
    4: "Mixed / watch",
    5: "Concerning over weeks",
    6: "Likely bad within weeks",
}

SEVERE_NEGATIVE_TERMS = (
    "guidance cut",
    "investigation",
    "lawsuit",
    "antitrust",
    "data breach",
    "outage",
    "recall",
    "downgrade",
    "misses estimates",
    "revenue decline",
    "profit warning",
    "ceo exit",
    "cfo exit",
    "mass layoff",
    "probe",
    "fine",
    "charges",
    "subpoena",
    "settlement",
)

MODERATE_NEGATIVE_TERMS = (
    "scrutiny",
    "appeal",
    "complaint",
    "warning",
    "pressure",
    "decline",
    "slump",
    "drop",
    "lawsuit",
    "probe",
    "delays",
    "delay",
    "pushback",
    "recall",
    "downgrade",
)

POSITIVE_TERMS = (
    "beats estimates",
    "beat estimates",
    "raises guidance",
    "raised guidance",
    "restored",
    "recovers",
    "upgrade",
    "approval",
    "wins",
    "record",
    "expands",
    "launches",
    "partnership",
    "agreement",
    "strong growth",
)

HYPE_TERMS = (
    "launches",
    "launch",
    "expands",
    "expansion",
    "partnership",
    "agreement",
    "record",
    "wins",
    "approval",
    "upgrade",
    "strong growth",
    "rollout",
)


@dataclass(frozen=True)
class NewsItem:
    symbol: str
    title: str
    source: str
    url: str
    published_utc: str = ""
    summary: str = ""
    kind: str = "news"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def match_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = normalize_text(text)
    return [term for term in terms if term in lowered]


def item_impact(item: NewsItem) -> tuple[int, list[str], list[str]]:
    text = f"{item.title} {item.summary}"
    severe = match_terms(text, SEVERE_NEGATIVE_TERMS)
    moderate = match_terms(text, MODERATE_NEGATIVE_TERMS)
    positive = match_terms(text, POSITIVE_TERMS)

    if item.kind in {"sec", "company_page"} and not severe and not moderate:
        delta = -1 if positive else 0
        return delta, [], positive

    delta = 0
    if severe:
        delta += 2
    elif moderate:
        delta += 1
    if positive:
        delta -= 1
    return delta, severe or moderate, positive


def _headline_is_plausible(text: str) -> bool:
    cleaned = normalize_text(text)
    if len(cleaned) < 12:
        return False
    if any(token in cleaned for token in ("background:", "url(", "{", "}", ".image-", "@media")):
        return False
    alpha_count = sum(1 for char in cleaned if char.isalpha())
    return alpha_count >= 8


def parse_rss_feed(xml_bytes: bytes, symbol: str, source: str) -> list[NewsItem]:
    root = ET.fromstring(xml_bytes)
    items: list[NewsItem] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        summary = (item.findtext("description") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        items.append(
            NewsItem(
                symbol=symbol,
                title=html.unescape(title),
                source=source,
                url=link,
                published_utc=published,
                summary=html.unescape(re.sub("<[^>]+>", "", summary)),
                kind="rss",
            )
        )
    return items


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_map = {k.lower(): v for k, v in attrs}
        href = attrs_map.get("href")
        if href:
            self._href = href
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        text = "".join(self._text_parts).strip()
        if text:
            self.links.append((self._href, text))
        self._href = None
        self._text_parts = []


def parse_company_page(html_bytes: bytes, symbol: str, source: str, base_url: str) -> list[NewsItem]:
    parser = _AnchorCollector()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    items: list[NewsItem] = []
    for href, text in parser.links:
        if not href or not text:
            continue
        if not _headline_is_plausible(text):
            continue
        abs_url = urllib.parse.urljoin(base_url, href)
        if abs_url.startswith("mailto:"):
            continue
        if symbol == "MSFT" and "news.microsoft.com" not in abs_url:
            continue
        if symbol == "AAPL" and "apple.com/newsroom" not in abs_url:
            continue
        if symbol == "GOOGL" and "abc.xyz" not in abs_url and "blog.google" not in abs_url:
            continue
        items.append(
            NewsItem(
                symbol=symbol,
                title=re.sub(r"\s+", " ", text).strip(),
                source=source,
                url=abs_url,
                summary="",
                kind="company_page",
            )
        )
    return items[:12]


def fetch_google_news(query: str, symbol: str, rss_base: str) -> list[NewsItem]:
    url = rss_base.format(query=urllib.parse.quote_plus(query))
    raw = http_get(url)
    return parse_rss_feed(raw, symbol=symbol, source=f"google-news:{query}")


def fetch_yahoo_news(symbol: str, rss_base: str) -> list[NewsItem]:
    url = rss_base.format(symbol=urllib.parse.quote_plus(symbol))
    raw = http_get(url)
    return parse_rss_feed(raw, symbol=symbol, source="yahoo-finance")


def fetch_sec_company_filings(symbol: str, cik: int, forms: list[str], max_items: int = 8) -> list[NewsItem]:
    cik_padded = f"{int(cik):010d}"
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    raw = http_get(url, headers=SEC_HEADERS)
    data = json.loads(raw.decode("utf-8"))
    recent = data.get("filings", {}).get("recent", {})
    accession_numbers = recent.get("accessionNumber", [])
    forms_seen = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])
    items: list[NewsItem] = []
    for form, accession, filing_date, primary_doc in zip(forms_seen, accession_numbers, filing_dates, primary_docs):
        if form not in forms:
            continue
        accession_no = accession.replace("-", "")
        archive_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_no}/{primary_doc}"
        items.append(
            NewsItem(
                symbol=symbol,
                title=f"{symbol} filed {form} on {filing_date}",
                source="sec-filings",
                url=archive_url,
                published_utc=filing_date,
                summary=form,
                kind="sec",
            )
        )
        if len(items) >= max_items:
            break
    return items


def resolve_sec_cik(symbol: str) -> int | None:
    ticker_url = "https://www.sec.gov/files/company_tickers.json"
    raw = http_get(ticker_url, headers=SEC_HEADERS)
    payload = json.loads(raw.decode("utf-8"))
    for row in payload.values():
        if str(row.get("ticker", "")).upper() == symbol.upper():
            return int(row["cik_str"])
    return None


def collect_company_page(symbol: str, url: str) -> list[NewsItem]:
    raw = http_get(url)
    return parse_company_page(raw, symbol=symbol, source="company-page", base_url=url)


def collect_news_bundle(symbols: list[str], sources_cfg: dict[str, Any]) -> list[NewsItem]:
    rss_base = str(sources_cfg["news_google_rss_base"])
    yahoo_rss_base = str(sources_cfg.get("yahoo_rss_base", ""))
    google_queries = dict(sources_cfg.get("google_queries", {}))
    sec_forms = [str(x) for x in sources_cfg.get("sec_forms", [])]
    company_pages = dict(sources_cfg.get("company_pages", {}))

    items: list[NewsItem] = []
    for symbol in symbols:
        if yahoo_rss_base:
            try:
                items.extend(fetch_yahoo_news(symbol=symbol, rss_base=yahoo_rss_base))
            except Exception:
                pass

        for query in google_queries.get(symbol, []):
            try:
                items.extend(fetch_google_news(query=query, symbol=symbol, rss_base=rss_base))
            except Exception:
                continue

        try:
            cik = resolve_sec_cik(symbol)
            if cik is not None:
                items.extend(fetch_sec_company_filings(symbol, cik, sec_forms))
        except Exception:
            pass

        page_url = company_pages.get(symbol)
        if page_url:
            try:
                items.extend(collect_company_page(symbol, page_url))
            except Exception:
                pass

    deduped: list[NewsItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.title.lower(), item.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def aggregate_symbol_briefs(items: list[NewsItem]) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        by_symbol[item.symbol].append(item)

    briefs: list[dict[str, Any]] = []
    for symbol in sorted(by_symbol):
        symbol_items = by_symbol[symbol]
        if not symbol_items:
            continue

        positive_count = 0
        hype_count = 0
        severe_count = 0
        moderate_count = 0
        routine_count = 0
        theme_counter: Counter[str] = Counter()
        source_counter: Counter[str] = Counter()
        critical_notes: list[str] = []
        routine_notes: list[str] = []
        scored_items: list[tuple[int, NewsItem, list[str], list[str]]] = []

        for item in symbol_items:
            delta, negative_hits, positive_hits = item_impact(item)
            severe_hits = [term for term in negative_hits if term in SEVERE_NEGATIVE_TERMS]
            moderate_hits = [term for term in negative_hits if term in MODERATE_NEGATIVE_TERMS and term not in severe_hits]
            hype_hits = [term for term in positive_hits if term in HYPE_TERMS]
            severe_count += len(severe_hits)
            moderate_count += len(moderate_hits)
            positive_count += len(positive_hits)
            hype_count += len(hype_hits)
            if item.kind in {"sec", "company_page"} and not negative_hits:
                routine_count += 1
            for term in negative_hits:
                theme_counter[term] += 1
            for term in positive_hits:
                theme_counter[term] += 1
            source_counter[item.source] += 1
            scored_items.append((delta, item, negative_hits, positive_hits))
            if severe_hits:
                critical_notes.append(f"{item.title} ({', '.join(severe_hits[:2])})")
            elif moderate_hits:
                routine_notes.append(f"{item.title} ({', '.join(moderate_hits[:2])})")
            elif item.kind in {"sec", "company_page"}:
                routine_notes.append(f"{item.title} (routine filing/update)")

        if severe_count >= 2 or (severe_count >= 1 and moderate_count >= 1):
            score = 6
        elif severe_count >= 1 or moderate_count >= 2:
            score = 5
        elif positive_count > 0 and severe_count == 0 and moderate_count == 0 and hype_count > 0:
            score = 3
        elif positive_count > 0 and severe_count == 0 and moderate_count == 0:
            score = 2
        elif positive_count == 0 and severe_count == 0 and moderate_count == 0:
            score = 4
        else:
            score = 4

        label = SCALE_LABELS[score]

        if score >= 6:
            headline = f"{symbol} looks like it could become a real problem over the next few weeks."
        elif score == 5:
            headline = f"{symbol} has a concern that may matter over the next week or month, but not every item is serious."
        elif score == 4:
            headline = f"{symbol} looks mixed: probably not a big deal yet, but worth watching over the next week or month."
        elif score == 3:
            headline = f"{symbol} looks exciting on the surface, but some items may just be short-term hype."
        elif score == 2:
            headline = f"{symbol} looks mostly okay over the next few weeks."
        else:
            headline = f"{symbol} looks constructive and not like a near-term problem."

        themes = [theme for theme, _count in theme_counter.most_common(3)]
        if themes:
            headline += f" Main topics: {', '.join(themes)}."
        if source_counter:
            top_sources = ", ".join(source for source, _count in source_counter.most_common(3))
            headline += f" Main sources: {top_sources}."
        if routine_count and score <= 4:
            headline += f" {routine_count} items look routine."

        scored_items.sort(key=lambda entry: (-entry[0], entry[1].published_utc, entry[1].title))
        top_headlines = []
        for _delta, item, negative_hits, positive_hits in scored_items[:5]:
            if negative_hits:
                tone = "negative"
            elif positive_hits:
                tone = "positive"
            else:
                tone = "neutral"

            if item.kind in {"sec", "company_page"} and not negative_hits:
                why = "Routine filing or company update; usually not market-moving by itself."
            elif negative_hits:
                why = f"Matched {', '.join(negative_hits[:3])}."
            elif positive_hits:
                why = f"Matched {', '.join(positive_hits[:3])}."
            else:
                why = "No strong signal either way."
            top_headlines.append(
                {
                    "title": item.title,
                    "source": item.source,
                    "url": item.url,
                    "published_utc": item.published_utc,
                    "kind": item.kind,
                    "tone": tone,
                    "why": why,
                }
            )

        briefs.append(
            {
                "symbol": symbol,
                "score": score,
                "label": label,
                "summary": headline,
                "source_count": len(source_counter),
                "item_count": len(symbol_items),
                "critical_count": severe_count,
                "routine_count": routine_count,
                "hype_count": hype_count,
                "themes": themes,
                "sources": [source for source, _count in source_counter.most_common(4)],
                "top_headlines": top_headlines,
                "critical_notes": critical_notes[:5],
                "routine_notes": routine_notes[:5],
            }
        )

    briefs.sort(key=lambda brief: (-int(brief["score"]), brief["symbol"]))
    return briefs
