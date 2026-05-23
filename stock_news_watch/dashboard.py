from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .engine import StockNewsWatchEngine


LEVEL_COPY = {
    1: "Strong positive",
    2: "Okay",
    3: "Beware / short-term hype",
    4: "Mixed / watch",
    5: "Concerning over weeks",
    6: "Likely bad within weeks",
}


def render_dashboard_html(snapshot: dict[str, Any], refresh_seconds: int) -> str:
    heartbeat = snapshot.get("heartbeat", {}) or {}
    state = snapshot.get("state", {}) or {}
    assessment = snapshot.get("assessment", {}) or {}
    briefs = assessment.get("briefs", []) or []

    def esc(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def tab_id(symbol: str) -> str:
        return f"panel-{symbol.lower()}"

    if not briefs:
        briefs = []

    active_symbol = str(briefs[0].get("symbol", "")) if briefs else ""
    tabs: list[str] = []
    panels: list[str] = []

    for brief in briefs:
        symbol = str(brief.get("symbol", "")).upper()
        score = int(brief.get("score", 3) or 3)
        label = esc(brief.get("label", LEVEL_COPY.get(score, "Mixed / watch")))
        takeaway = esc(brief.get("takeaway") or brief.get("summary", ""))
        why_it_matters = esc(brief.get("why_it_matters") or brief.get("summary", ""))
        summary = esc(brief.get("summary", ""))
        source_count = int(brief.get("source_count", 0) or 0)
        item_count = int(brief.get("item_count", 0) or 0)
        sources = ", ".join(str(s) for s in brief.get("sources", [])[:4]) or "No sources yet"
        top_headlines = brief.get("top_headlines", [])[:3]
        themes = [esc(theme) for theme in (brief.get("themes", []) or [])[:4]]
        critical_notes = [esc(note) for note in (brief.get("critical_notes", []) or [])[:4]]
        routine_notes = [esc(note) for note in (brief.get("routine_notes", []) or [])[:4]]
        headlines = []
        for item in top_headlines:
            headlines.append(
                f"""
                <li class="evidence">
                  <a href="{esc(item.get('url', '#'))}" target="_blank" rel="noreferrer">{esc(item.get('title', ''))}</a>
                  <div class="meta">{esc(item.get('source', ''))}{f" · {esc(item.get('why', ''))}" if item.get('why') else ""}</div>
                </li>
                """
            )

        is_active = "active" if symbol == active_symbol else ""
        tabs.append(
            f"""
            <button class="tab {is_active}" type="button" data-target="{tab_id(symbol)}">
              <span class="sym">{symbol}</span>
              <span class="score score-{score}">{score}</span>
              <span class="lab">{label}</span>
            </button>
            """
        )
        panels.append(
            f"""
            <section class="panel {is_active}" id="{tab_id(symbol)}" data-panel="{tab_id(symbol)}">
              <div class="panel-head">
                <div>
                  <div class="panel-symbol">{symbol}</div>
                  <div class="panel-label">{label}</div>
                </div>
                <div class="panel-score score-{score}">{score}/6</div>
              </div>
              <p class="summary">{takeaway}</p>
              <div class="detail-grid">
                <div class="detail-card">
                  <div class="detail-kicker">Why it matters</div>
                  <div class="detail-body">{why_it_matters}</div>
                </div>
                <div class="detail-card">
                  <div class="detail-kicker">How to read it</div>
                  <div class="detail-body">1-2 means mostly fine. 3 means hype or noise. 4 means mixed. 5-6 means watch closely because it could hurt over weeks.</div>
                </div>
              </div>
              <div class="quick">
                <span>{item_count} items</span>
                <span>{source_count} sources</span>
                <span>{sources}</span>
              </div>
              <div class="section-title">Themes</div>
              <div class="theme-row">
                {''.join(f'<span class="theme-pill">{theme}</span>' for theme in themes) if themes else '<span class="theme-pill muted">No clear theme yet</span>'}
              </div>
              <div class="section-title">Important vs routine</div>
              <div class="note-columns">
                <div>
                  <div class="note-heading">Important</div>
                  <ul class="note-list">
                    {''.join(f'<li>{note}</li>' for note in critical_notes) if critical_notes else '<li class="muted">Nothing clearly critical in the current bundle.</li>'}
                  </ul>
                </div>
                <div>
                  <div class="note-heading">Probably routine</div>
                  <ul class="note-list">
                    {''.join(f'<li>{note}</li>' for note in routine_notes) if routine_notes else '<li class="muted">No obvious routine note yet.</li>'}
                  </ul>
                </div>
              </div>
              <div class="section-title">What Codex saw</div>
              <ul class="list">
                {''.join(headlines) if headlines else '<li class="evidence muted">No headlines yet.</li>'}
              </ul>
            </section>
            """
        )

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>stock_news_watch</title>
  <style>
    :root {{
      --bg: #fbfcfe;
      --panel: #ffffff;
      --text: #101828;
      --muted: #667085;
      --border: rgba(16,24,40,0.08);
      --good: #16a34a;
      --info: #2563eb;
      --hype: #d97706;
      --watch: #7c3aed;
      --concern: #b45309;
      --bad: #dc2626;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(37,99,235,.04), transparent 30%),
        linear-gradient(180deg, #fbfcfe 0%, #ffffff 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
    }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 28px; }}
    .hero {{
      padding: 24px;
      border: 1px solid var(--border);
      border-radius: 26px;
      background: rgba(255,255,255,.94);
      box-shadow: 0 16px 40px rgba(16,24,40,.05);
    }}
    .eyebrow {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .16em;
      font-size: 11px;
      font-weight: 800;
    }}
    h1 {{
      margin: 8px 0 10px;
      font-size: 40px;
      line-height: 1;
      letter-spacing: -.05em;
    }}
    .sub {{
      margin: 0;
      max-width: 780px;
      color: var(--muted);
      line-height: 1.7;
      font-size: 15px;
    }}
    .meta-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
      font-size: 13px;
    }}
    .score {{
      min-width: 28px;
      height: 28px;
      display: inline-grid;
      place-items: center;
      border-radius: 999px;
      color: #fff;
      font-weight: 800;
      font-size: 13px;
    }}
    .score-1, .score-2 {{ background: var(--good); }}
    .score-3 {{ background: var(--hype); }}
    .score-4 {{ background: var(--watch); }}
    .score-5 {{ background: var(--concern); }}
    .score-6 {{ background: var(--bad); }}
    .board {{
      margin-top: 18px;
      padding: 18px;
      border: 1px solid var(--border);
      border-radius: 24px;
      background: var(--panel);
      box-shadow: 0 10px 30px rgba(16,24,40,.05);
    }}
    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 16px;
    }}
    .tab {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 11px 14px;
      border-radius: 16px;
      border: 1px solid var(--border);
      background: #fff;
      color: var(--text);
      cursor: pointer;
    }}
    .tab.active {{
      border-color: rgba(37,99,235,.22);
      box-shadow: 0 10px 24px rgba(37,99,235,.08);
    }}
    .tab .sym {{ font-weight: 900; }}
    .tab .lab {{ color: var(--muted); font-size: 13px; }}
    .panel {{ display: none; }}
    .panel.active {{ display: block; }}
    .panel-head {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: flex-start;
    }}
    .panel-symbol {{ font-size: 26px; font-weight: 900; letter-spacing: -.04em; }}
    .panel-label {{ color: var(--muted); margin-top: 4px; }}
    .panel-score {{
      min-width: 76px;
      padding: 12px;
      border-radius: 18px;
      color: #fff;
      text-align: center;
      font-weight: 900;
      font-size: 28px;
      line-height: 1;
    }}
    .summary {{
      margin: 14px 0 0;
      font-size: 16px;
      line-height: 1.7;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .detail-card {{
      padding: 14px;
      border-radius: 18px;
      background: #f8fafc;
      border: 1px solid var(--border);
    }}
    .detail-kicker {{
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .08em;
      font-size: 11px;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .detail-body {{
      line-height: 1.65;
      font-size: 14px;
    }}
    .quick {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }}
    .quick span {{
      padding: 5px 10px;
      border-radius: 999px;
      background: #f8fafc;
      border: 1px solid var(--border);
    }}
    .theme-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .theme-pill {{
      padding: 6px 10px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
      font-size: 12px;
      color: var(--text);
    }}
    .theme-pill.muted,
    .muted {{
      color: var(--muted);
    }}
    .note-columns {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 10px;
    }}
    .note-heading {{
      font-size: 13px;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .note-list {{
      margin: 0;
      padding-left: 18px;
      color: var(--text);
      line-height: 1.6;
      display: grid;
      gap: 6px;
    }}
    .section-title {{
      margin-top: 18px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: .1em;
      font-size: 11px;
      font-weight: 800;
    }}
    .list {{
      display: grid;
      gap: 10px;
      margin-top: 10px;
      padding: 0;
      list-style: none;
    }}
    .evidence {{
      padding: 12px 14px;
      border-radius: 16px;
      background: #f8fafc;
      border-left: 4px solid var(--border);
    }}
    .evidence a {{ font-weight: 800; color: var(--text); }}
    .evidence .meta {{ color: var(--muted); margin-top: 4px; font-size: 12px; line-height: 1.45; }}
    .evidence.muted {{ color: var(--muted); }}
    .footer {{
      margin: 14px 0 30px;
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 860px) {{
      h1 {{ font-size: 32px; }}
      .panel-head {{ flex-direction: column; }}
      .panel-score {{ align-self: flex-start; }}
      .detail-grid,
      .note-columns {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">Live market briefing</div>
      <h1>stock_news_watch</h1>
      <p class="sub">
        One tab per stock. Codex reads the live evidence and decides whether the story is strong, hype, mixed, watch-worthy, or actually bad over the next week or month.
      </p>
      <div class="meta-row">
        <span class="chip">Status <strong>{esc(heartbeat.get('status') or state.get('status') or 'idle')}</strong></span>
        <span class="chip">Overall <strong>{esc(assessment.get('overall_label') or state.get('overall_label') or 'Mixed / watch')}</strong></span>
        <span class="chip">Score <strong>{esc(assessment.get('overall_score', heartbeat.get('overall_score', 3)))}</strong>/6</span>
        <span class="chip">Refresh {refresh_seconds}s</span>
      </div>
    </section>

    <section class="board">
      <div class="tabs">
        {''.join(tabs) if tabs else '<span class="chip">No stock briefs yet. Run one cycle to populate.</span>'}
      </div>
      {''.join(panels) if panels else '<div class="chip">No stock briefs yet. Run one cycle to populate.</div>'}
    </section>

    <div class="footer">
      Last check: {esc(heartbeat.get('last_check_utc') or state.get('last_check_utc') or 'n/a')} · Runtime root: {esc(snapshot.get('runtime_root', 'n/a'))}
    </div>
  </div>
  <script>
    const tabs = Array.from(document.querySelectorAll('.tab'));
    const panels = Array.from(document.querySelectorAll('.panel'));
    function activate(targetId) {{
      tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.target === targetId));
      panels.forEach(panel => panel.classList.toggle('active', panel.id === targetId));
    }}
    tabs.forEach(tab => tab.addEventListener('click', () => activate(tab.dataset.target)));
    if (tabs.length) {{
      activate(tabs[0].dataset.target);
    }}
    async function refreshSnapshot() {{
      try {{
        const res = await fetch('/api/state', {{ cache: 'no-store' }});
        const data = await res.json();
        if (data.heartbeat?.revision !== {int(heartbeat.get('revision', state.get('revision', 0)) or 0)}) {{
          window.location.reload();
        }}
      }} catch (err) {{
        console.warn('refresh failed', err);
      }}
    }}
    setInterval(refreshSnapshot, {int(refresh_seconds)} * 1000);
  </script>
</body>
</html>
"""
    return html


class DashboardHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], engine: StockNewsWatchEngine) -> None:
        self.engine = engine
        super().__init__(server_address, DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(render_dashboard_html(self.server.engine.snapshot(), self.server.engine.config.dashboard.refresh_seconds))
            return
        if parsed.path == "/api/state":
            self._send_json(self.server.engine.snapshot())
            return
        if parsed.path == "/api/events":
            snapshot = self.server.engine.snapshot()
            self._send_json({"recent_events": snapshot.get("recent_events", [])})
            return
        if parsed.path == "/health":
            self._send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "not found")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body_text: str) -> None:
        body = body_text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_dashboard(engine: StockNewsWatchEngine, host: str, port: int) -> ThreadingHTTPServer:
    server = DashboardHTTPServer((host, port), engine)
    thread = threading.Thread(target=server.serve_forever, name="stock_news_watch_dashboard", daemon=True)
    thread.start()
    return server
