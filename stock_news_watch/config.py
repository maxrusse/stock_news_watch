from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CodexSettings:
    exe: str = "codex"
    model: str = "gpt-5.4-mini"
    reasoning_effort: str = "medium"
    web_search_mode: str = "auto"
    network_access_enabled: bool = True
    sandbox: str = "workspace-write"
    skip_git_repo_check: bool = True
    timeout_sec: int = 180


@dataclass(frozen=True)
class RuntimeSettings:
    poll_seconds: int = 60
    run_interval_seconds: int = 3600
    schedule_mode: str = "market_hours"
    stop_when_outside_market_hours: bool = False
    market_timezone: str = "America/New_York"
    preopen_start: str = "08:30"
    market_open: str = "09:30"
    market_close: str = "16:00"


@dataclass(frozen=True)
class DashboardSettings:
    host: str = "127.0.0.1"
    port: int = 8765
    refresh_seconds: int = 20


@dataclass(frozen=True)
class SourceSettings:
    news_google_rss_base: str
    yahoo_rss_base: str
    google_queries: dict[str, list[str]]
    sec_forms: list[str]
    company_pages: dict[str, str]


@dataclass(frozen=True)
class AppConfig:
    workspace_root: Path
    runtime_dir: Path
    codex: CodexSettings = field(default_factory=CodexSettings)
    runtime: RuntimeSettings = field(default_factory=RuntimeSettings)
    dashboard: DashboardSettings = field(default_factory=DashboardSettings)
    sources: SourceSettings = field(
        default_factory=lambda: SourceSettings(
            news_google_rss_base="https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
            yahoo_rss_base="https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
            google_queries={
                "MSFT": [
                    "MSFT Reuters",
                    "MSFT AP News",
                    "Microsoft site:news.microsoft.com/source/press-releases",
                    "Microsoft site:news.microsoft.com",
                ],
                "AAPL": [
                    "AAPL Reuters",
                    "AAPL AP News",
                    "Apple site:apple.com/newsroom",
                    "Apple site:investor.apple.com",
                ],
                "GOOGL": [
                    "GOOGL Reuters",
                    "GOOGL AP News",
                    "Alphabet site:abc.xyz/investor/news",
                    "Alphabet site:blog.google",
                ],
            },
            sec_forms=["8-K", "10-Q", "10-K", "424B", "S-3", "13D", "13G"],
            company_pages={
                "MSFT": "https://news.microsoft.com/source/tag/press-releases/",
                "AAPL": "https://www.apple.com/newsroom/topics/company-news/",
                "GOOGL": "https://abc.xyz/investor/news/",
            },
        )
    )
    watch_terms: tuple[str, ...] = (
        "guidance cut",
        "investigation",
        "SEC",
        "lawsuit",
        "antitrust",
        "data breach",
        "outage",
        "recall",
        "downgrade",
        "misses estimates",
        "revenue decline",
        "profit warning",
        "CEO exit",
        "CFO exit",
        "mass layoff",
    )

    @property
    def runtime_path(self) -> Path:
        return (self.workspace_root / self.runtime_dir).resolve()

    @classmethod
    def from_file(cls, path: Path) -> "AppConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        workspace_root = Path(raw["workspace_root"]).resolve()
        runtime_dir = Path(raw.get("runtime_dir", ".runtime"))

        codex_raw = raw.get("codex", {})
        runtime_raw = raw.get("runtime", {})
        dashboard_raw = raw.get("dashboard", {})
        sources_raw = raw.get("sources", {})

        return cls(
            workspace_root=workspace_root,
            runtime_dir=runtime_dir,
            codex=CodexSettings(
                exe=str(codex_raw.get("exe", "codex")),
                model=str(codex_raw.get("model", "gpt-5.4-mini")),
                reasoning_effort=str(codex_raw.get("reasoning_effort", "medium")),
                web_search_mode=str(codex_raw.get("web_search_mode", "auto")),
                network_access_enabled=bool(codex_raw.get("network_access_enabled", True)),
                sandbox=str(codex_raw.get("sandbox", "workspace-write")),
                skip_git_repo_check=bool(codex_raw.get("skip_git_repo_check", True)),
                timeout_sec=int(codex_raw.get("timeout_sec", 180) or 180),
            ),
            runtime=RuntimeSettings(
                poll_seconds=int(runtime_raw.get("poll_seconds", 60) or 60),
                run_interval_seconds=int(runtime_raw.get("run_interval_seconds", 3600) or 3600),
                schedule_mode=str(runtime_raw.get("schedule_mode", "market_hours")),
                stop_when_outside_market_hours=bool(runtime_raw.get("stop_when_outside_market_hours", False)),
                market_timezone=str(runtime_raw.get("market_timezone", "America/New_York")),
                preopen_start=str(runtime_raw.get("preopen_start", "08:30")),
                market_open=str(runtime_raw.get("market_open", "09:30")),
                market_close=str(runtime_raw.get("market_close", "16:00")),
            ),
            dashboard=DashboardSettings(
                host=str(dashboard_raw.get("host", "127.0.0.1")),
                port=int(dashboard_raw.get("port", 8765) or 8765),
                refresh_seconds=int(dashboard_raw.get("refresh_seconds", 20) or 20),
            ),
            sources=SourceSettings(
                news_google_rss_base=str(
                    sources_raw.get(
                        "news_google_rss_base",
                        "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
                    )
                ),
                yahoo_rss_base=str(
                    sources_raw.get(
                        "yahoo_rss_base",
                        "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US",
                    )
                ),
                google_queries={k: [str(item) for item in v] for k, v in dict(sources_raw.get("google_queries", {})).items()},
                sec_forms=[str(item) for item in sources_raw.get("sec_forms", ["8-K", "10-Q", "10-K"])],
                company_pages={str(k): str(v) for k, v in dict(sources_raw.get("company_pages", {})).items()},
            ),
            watch_terms=tuple(str(x) for x in raw.get("watch_terms", list(AppConfig.__dataclass_fields__["watch_terms"].default))),
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root),
            "runtime_dir": str(self.runtime_dir),
            "codex": self.codex.__dict__,
            "runtime": self.runtime.__dict__,
            "dashboard": self.dashboard.__dict__,
            "sources": {
                "news_google_rss_base": self.sources.news_google_rss_base,
                "yahoo_rss_base": self.sources.yahoo_rss_base,
                "google_queries": self.sources.google_queries,
                "sec_forms": self.sources.sec_forms,
                "company_pages": self.sources.company_pages,
            },
            "watch_terms": list(self.watch_terms),
        }


def default_config_path(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[1]
    return (root / "config" / "stock_news_watch.json").resolve()
