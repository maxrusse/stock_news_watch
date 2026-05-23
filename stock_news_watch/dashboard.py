from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .engine import StockNewsWatchEngine


def render_dashboard_html(snapshot: dict[str, Any], refresh_seconds: int) -> str:
    heartbeat = snapshot.get("heartbeat", {}) or {}
    state = snapshot.get("state", {}) or {}
    assessment = snapshot.get("assessment", {}) or {}
    events = snapshot.get("recent_events", []) or []

    def esc(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    events_html = []
    for event in reversed(events[-20:]):
        urls = "".join(f'<li><a href="{esc(url)}" target="_blank" rel="noreferrer">{esc(url)}</a></li>' for url in event.get("urls", []))
        events_html.append(
            f"""
            <article class="event {esc(event.get('severity', ''))}">
              <div class="meta">{esc(event.get('ts_utc', ''))} · {esc(event.get('severity', ''))} · {esc(event.get('kind', ''))}</div>
              <h3>{esc(event.get('summary', ''))}</h3>
              <div class="sub">{esc(event.get('decision_source', ''))}</div>
              <ul>{urls}</ul>
            </article>
            """
        )

    signals = assessment.get("signals", []) or []
    signal_html = "".join(
        f'<li><a href="{esc(signal.get("url", ""))}" target="_blank" rel="noreferrer">{esc(signal.get("symbol", ""))}: {esc(signal.get("title", ""))}</a> <span>{esc(signal.get("why", ""))}</span></li>'
        for signal in signals
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
      --bg: #0b1020;
      --panel: rgba(19, 25, 46, 0.92);
      --panel2: rgba(23, 31, 58, 0.92);
      --text: #e9ecf5;
      --muted: #aeb7d0;
      --accent: #4fd1c5;
      --danger: #ff6b6b;
      --good: #51d88a;
      --border: rgba(255,255,255,0.09);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(79, 209, 197, 0.14), transparent 24%),
        radial-gradient(circle at 80% 10%, rgba(255, 107, 107, 0.10), transparent 20%),
        linear-gradient(180deg, #0b1020 0%, #11162b 100%);
      color: var(--text);
      min-height: 100vh;
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    .hero {{
      display: flex; justify-content: space-between; gap: 20px; align-items: flex-start;
      padding: 24px; border: 1px solid var(--border); border-radius: 24px; background: rgba(10,15,30,0.72); backdrop-filter: blur(18px);
    }}
    .title {{ font-size: 40px; line-height: 1; margin: 0 0 10px 0; letter-spacing: -0.04em; }}
    .subtitle {{ color: var(--muted); max-width: 760px; margin: 0; font-size: 15px; line-height: 1.6; }}
    .pillbar {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .pill {{
      display: inline-flex; gap: 8px; align-items: center; padding: 8px 12px; border-radius: 999px;
      background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: var(--text); font-size: 13px;
    }}
    .grid {{ display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 18px; margin-top: 18px; }}
    .card {{
      padding: 18px; border-radius: 22px; background: var(--panel); border: 1px solid var(--border);
    }}
    .card h2 {{ margin: 0 0 12px 0; font-size: 18px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    .metric {{
      padding: 14px; border-radius: 18px; background: var(--panel2); border: 1px solid var(--border);
    }}
    .metric .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .metric .value {{ font-size: 24px; font-weight: 700; margin-top: 8px; }}
    .status-good {{ color: var(--good); }}
    .status-danger {{ color: var(--danger); }}
    .status-muted {{ color: var(--muted); }}
    .event, .signalbox {{ margin-top: 12px; padding: 14px; border-radius: 16px; background: rgba(255,255,255,0.04); border: 1px solid var(--border); }}
    .event h3 {{ margin: 8px 0; font-size: 16px; }}
    .meta, .sub {{ color: var(--muted); font-size: 12px; }}
    .stack {{ display: grid; gap: 12px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    ul {{ margin: 10px 0 0 18px; padding: 0; }}
    li {{ margin: 8px 0; }}
    .footer {{ margin: 16px 0 30px; color: var(--muted); font-size: 12px; }}
    @media (max-width: 940px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .metrics {{ grid-template-columns: 1fr; }}
      .hero {{ flex-direction: column; }}
      .title {{ font-size: 32px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div>
        <h1 class="title">stock_news_watch</h1>
        <p class="subtitle">
          Hourly Codex-backed live news monitoring for MSFT, AAPL, and GOOGL. The loop writes a heartbeat after each cycle,
          logs events, and stays alert-only.
        </p>
        <div class="pillbar">
          <span class="pill">Model: {esc(heartbeat.get('model') or state.get('model') or 'n/a')}</span>
          <span class="pill">Status: <strong class="{ 'status-danger' if heartbeat.get('alert') else 'status-good' if heartbeat.get('clean') else 'status-muted' }">{esc(heartbeat.get('status') or state.get('status') or 'idle')}</strong></span>
          <span class="pill">Revision: {esc(heartbeat.get('revision', state.get('revision', 0)))}</span>
          <span class="pill">Refresh: {refresh_seconds}s</span>
        </div>
      </div>
      <div class="card" style="min-width: 280px;">
        <h2>Current Summary</h2>
        <div>{esc(heartbeat.get('last_summary') or state.get('current_summary') or 'No data yet')}</div>
        <div class="meta" style="margin-top: 10px;">Last check: {esc(heartbeat.get('last_check_utc') or state.get('last_check_utc') or 'n/a')}</div>
        <div class="meta">Last alert: {esc(heartbeat.get('last_alert_utc') or state.get('last_alert_utc') or 'n/a')}</div>
      </div>
    </section>

    <section class="grid">
      <div class="stack">
        <div class="card">
          <h2>Heartbeat</h2>
          <div class="metrics">
            <div class="metric"><div class="label">Cycle Count</div><div class="value">{esc(heartbeat.get('cycle_count', 0))}</div></div>
            <div class="metric"><div class="label">Source Count</div><div class="value">{esc(heartbeat.get('source_count', 0))}</div></div>
            <div class="metric"><div class="label">Alert State</div><div class="value">{'ALERT' if heartbeat.get('alert') else 'CLEAR'}</div></div>
          </div>
        </div>
        <div class="card">
          <h2>Recent Events</h2>
          <div class="stack">
            {''.join(events_html) if events_html else '<div class="signalbox">No events yet.</div>'}
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <h2>Signals</h2>
          <div class="signalbox">
            <ul>{signal_html or '<li>No critical signals</li>'}</ul>
          </div>
        </div>
        <div class="card">
          <h2>Assessment</h2>
          <div class="meta">Decision source: {esc(assessment.get('decision_source', 'n/a'))}</div>
          <div style="margin-top: 10px;">{esc(assessment.get('summary', 'No assessment yet'))}</div>
        </div>
      </div>
    </section>

    <div class="footer">
      Runtime root: {esc(snapshot.get('runtime_root', 'n/a'))}
    </div>
  </div>
  <script>
    const REFRESH_SECONDS = {int(refresh_seconds)};
    async function refreshSnapshot() {{
      try {{
        const res = await fetch('/api/state', {{cache: 'no-store'}});
        const data = await res.json();
        const title = data.heartbeat?.status || data.state?.status || 'idle';
        document.title = 'stock_news_watch · ' + title;
        if (data.heartbeat?.revision !== {int(heartbeat.get('revision', state.get('revision', 0)) or 0)}) {{
          window.location.reload();
        }}
      }} catch (err) {{
        console.warn('refresh failed', err);
      }}
    }}
    setInterval(refreshSnapshot, REFRESH_SECONDS * 1000);
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
