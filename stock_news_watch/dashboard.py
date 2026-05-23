from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .engine import StockNewsWatchEngine


HUMAN_LEVELS = {
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
    events = snapshot.get("recent_events", []) or []
    briefs = assessment.get("briefs", []) or []

    def esc(value: Any) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    def icon_svg(kind: str) -> str:
        icons = {
            "brand": '<svg viewBox="0 0 48 48" aria-hidden="true"><defs><linearGradient id="b" x1="0" x2="1" y1="0" y2="1"><stop offset="0%" stop-color="#2563eb"/><stop offset="100%" stop-color="#0f766e"/></linearGradient></defs><circle cx="24" cy="24" r="21" fill="#fff" stroke="url(#b)" stroke-width="1.8"/><path d="M12 27c4-1 7-5 9-11 1 7 5 12 10 14 3 1 5 1 8 0" fill="none" stroke="url(#b)" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="32" cy="16" r="2.4" fill="#0f766e"/></svg>',
            "clock": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            "shield": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l7 3v6c0 4.2-2.7 7.6-7 9-4.3-1.4-7-4.8-7-9V6l7-3z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
            "trend": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 16l5-5 4 4 7-8" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 7h4v4" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/></svg>',
            "alert": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l9 16H3L12 4z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M12 9v5" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="17" r="1" fill="currentColor"/></svg>',
            "news": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h10v14H5z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M15 8h4v11H7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 9h6M8 12h6M8 15h4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
            "tabs": '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="14" rx="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M4 10h16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
        }
        return icons.get(kind, icons["news"])

    def score_class(score: int) -> str:
        if score >= 6:
            return "score-urgent"
        if score == 5:
            return "score-concerning"
        if score == 4:
            return "score-watch"
        if score == 3:
            return "score-hype"
        if score == 2:
            return "score-ok"
        return "score-positive"

    def level_text(score: int) -> str:
        return HUMAN_LEVELS.get(score, "Mixed / watch")

    def tab_label(brief: dict[str, Any]) -> str:
        symbol = esc(brief.get("symbol", ""))
        score = int(brief.get("score", 3) or 3)
        return f"{symbol} · {level_text(score)}"

    if briefs:
        active_symbol = str(briefs[0].get("symbol", ""))
    else:
        active_symbol = ""

    tab_buttons: list[str] = []
    panels: list[str] = []

    for brief in briefs:
        symbol = esc(brief.get("symbol", ""))
        score = int(brief.get("score", 3) or 3)
        active = "active" if str(brief.get("symbol", "")) == active_symbol else ""
        title_label = esc(level_text(score))
        summary = esc(brief.get("summary", ""))
        critical_count = int(brief.get("critical_count", 0) or 0)
        routine_count = int(brief.get("routine_count", 0) or 0)
        item_count = int(brief.get("item_count", 0) or 0)
        source_count = int(brief.get("source_count", 0) or 0)

        tag_pills = "".join(f'<span class="mini-pill">{esc(theme)}</span>' for theme in brief.get("themes", [])[:4])
        if not tag_pills:
            tag_pills = '<span class="mini-pill soft">No major theme</span>'

        source_pills = "".join(f'<span class="mini-pill soft">{esc(source)}</span>' for source in brief.get("sources", [])[:4])
        if not source_pills:
            source_pills = '<span class="mini-pill soft">No source yet</span>'

        notes: list[str] = []
        if score >= 4:
            notes = brief.get("critical_notes", [])[:4]
        elif routine_count:
            notes = brief.get("routine_notes", [])[:4]
        if not notes:
            notes = [brief.get("summary", "Nothing clearly market-moving here.")]

        note_items = "".join(f"<li>{esc(note)}</li>" for note in notes)

        headlines: list[str] = []
        for headline in brief.get("top_headlines", [])[:4]:
            tone = esc(headline.get("tone", "neutral"))
            why = esc(headline.get("why", ""))
            source = esc(headline.get("source", ""))
            title = esc(headline.get("title", ""))
            url = esc(headline.get("url", "#"))
            reading = "routine" if "Routine filing" in why else ("watch" if tone == "negative" and score < 5 else "important" if tone == "negative" else ("hype" if score == 3 else "context"))
            headlines.append(
                f"""
                <li class="headline {tone}">
                  <div class="headline-top">
                    <a href="{url}" target="_blank" rel="noreferrer">{title}</a>
                    <span class="headline-chip">{reading}</span>
                  </div>
                  <div class="headline-meta">{source}{f" · {why}" if why else ""}</div>
                </li>
                """
            )

        tab_buttons.append(
            f"""
            <button class="tab-button {active}" type="button" data-symbol="{symbol}">
              <span class="tab-symbol">{symbol}</span>
              <span class="tab-score {score_class(score)}">{score}</span>
              <span class="tab-text">{title_label}</span>
            </button>
            """
        )

        panels.append(
            f"""
            <section class="panel {active}" data-panel="{symbol}">
              <div class="panel-header">
                <div>
                  <div class="panel-symbol">{symbol}</div>
                  <div class="panel-label">{title_label}</div>
                </div>
                <div class="score-box {score_class(score)}">
                  <div class="score-number">{score}</div>
                  <div class="score-caption">week / month</div>
                </div>
              </div>

              <p class="panel-summary">{summary}</p>

              <div class="panel-grid">
                <div class="panel-main">
                  <div class="section-card">
                    <div class="section-title">{icon_svg("alert")} What this means</div>
                    <div class="section-copy">
                      This score is about whether the story could become a real issue over the next week or month, not about tiny intraday swings.
                    </div>
                    <ul class="note-list">{note_items}</ul>
                  </div>

                  <div class="section-card">
                    <div class="section-title">{icon_svg("news")} What we found</div>
                    <div class="chip-row">{tag_pills}</div>
                    <div class="chip-row">{source_pills}</div>
                    <ul class="headline-list">
                      {''.join(headlines) if headlines else '<li class="headline neutral"><div class="headline-meta">No headlines yet.</div></li>'}
                    </ul>
                  </div>
                </div>

                <aside class="panel-side">
                  <div class="side-card">
                    <div class="side-title">Quick read</div>
                    <div class="big-read">{level_text(score)}</div>
                    <div class="side-copy">
                      {'This looks like a real concern over the next few weeks.' if score >= 5 else 'This looks mostly okay, mixed, or just short-term hype.'}
                    </div>
                  </div>
                  <div class="side-card">
                    <div class="side-title">Counts</div>
                    <div class="count-grid">
                      <div><span>Items</span><strong>{item_count}</strong></div>
                      <div><span>Sources</span><strong>{source_count}</strong></div>
                      <div><span>Flags</span><strong>{critical_count}</strong></div>
                      <div><span>Routine</span><strong>{routine_count}</strong></div>
                    </div>
                  </div>
                </aside>
              </div>
            </section>
            """
        )

    event_rows = []
    for event in reversed(events[-6:]):
        event_rows.append(
            f"""
            <li class="event-row">
              <span class="event-time">{esc(event.get('ts_utc', ''))}</span>
              <span class="event-label">{esc(event.get('label', event.get('severity', '')))}</span>
              <span class="event-summary">{esc(event.get('summary', ''))}</span>
            </li>
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
      --panel: rgba(255, 255, 255, 0.97);
      --panel-soft: #f8fafc;
      --text: #101828;
      --muted: #667085;
      --accent: #2563eb;
      --accent2: #0f766e;
      --danger: #dc2626;
      --warning: #d97706;
      --good: #16a34a;
      --border: rgba(16, 24, 40, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(37, 99, 235, 0.04), transparent 30%),
        radial-gradient(circle at 80% 0%, rgba(15, 118, 110, 0.04), transparent 24%),
        linear-gradient(180deg, #fbfcfe 0%, #ffffff 100%);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    a {{ color: inherit; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 28px; }}
    .hero {{
      display: grid;
      grid-template-columns: 1.6fr 0.9fr;
      gap: 18px;
      padding: 24px;
      border: 1px solid var(--border);
      border-radius: 28px;
      background: rgba(255, 255, 255, 0.88);
      box-shadow: 0 18px 50px rgba(16, 24, 40, 0.05);
      backdrop-filter: blur(12px);
    }}
    .brandline {{ display: flex; align-items: center; gap: 14px; margin-bottom: 12px; }}
    .brand-mark {{ width: 46px; height: 46px; flex: 0 0 auto; }}
    .brand-copy {{ display: grid; gap: 4px; }}
    .brand-kicker {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-weight: 700;
    }}
    .brand-title {{
      margin: 0;
      font-size: 42px;
      line-height: 1;
      letter-spacing: -0.05em;
    }}
    .subtitle {{
      margin: 0;
      max-width: 820px;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.7;
    }}
    .pillbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid var(--border);
      color: var(--text);
      font-size: 13px;
    }}
    .pill svg {{ width: 14px; height: 14px; }}
    .panel {{
      padding: 18px;
      border-radius: 24px;
      background: var(--panel);
      border: 1px solid var(--border);
      box-shadow: 0 10px 34px rgba(16, 24, 40, 0.05);
    }}
    .status-card {{
      display: grid;
      gap: 14px;
      align-content: start;
    }}
    .metric-card {{
      padding: 16px;
      border-radius: 18px;
      background: var(--panel-soft);
      border: 1px solid var(--border);
    }}
    .metric-label {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }}
    .metric-value {{
      margin-top: 8px;
      font-size: 22px;
      font-weight: 800;
    }}
    .metric-copy {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }}
    .topline {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 18px;
      margin-top: 18px;
    }}
    .tabs-panel {{
      padding: 14px;
    }}
    .tabbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 16px;
    }}
    .tab-button {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 11px 14px;
      border-radius: 16px;
      border: 1px solid var(--border);
      background: #ffffff;
      color: var(--text);
      cursor: pointer;
      box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
    }}
    .tab-button.active {{
      border-color: rgba(37, 99, 235, 0.25);
      box-shadow: 0 8px 22px rgba(37, 99, 235, 0.08);
    }}
    .tab-symbol {{ font-weight: 800; letter-spacing: -0.02em; }}
    .tab-score {{
      min-width: 28px;
      height: 28px;
      display: inline-grid;
      place-items: center;
      border-radius: 999px;
      font-weight: 800;
      color: #fff;
      font-size: 13px;
    }}
    .tab-text {{ color: var(--muted); font-size: 13px; }}
    .tab-score.score-positive {{ background: var(--good); }}
    .tab-score.score-ok {{ background: #2563eb; }}
    .tab-score.score-hype {{ background: #d97706; }}
    .tab-score.score-watch {{ background: #7c3aed; }}
    .tab-score.score-concerning {{ background: #b45309; }}
    .tab-score.score-urgent {{ background: var(--danger); }}
    .panel-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
      gap: 16px;
      margin-top: 16px;
    }}
    .panel[hidden] {{ display: none; }}
    .panel-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
    }}
    .panel-symbol {{ font-size: 26px; font-weight: 900; letter-spacing: -0.04em; }}
    .panel-label {{ margin-top: 4px; color: var(--muted); font-size: 14px; }}
    .score-box {{
      min-width: 96px;
      padding: 12px 14px;
      border-radius: 18px;
      text-align: center;
      border: 1px solid var(--border);
      background: var(--panel-soft);
    }}
    .score-box.score-positive {{ border-color: rgba(22, 163, 74, 0.2); }}
    .score-box.score-ok {{ border-color: rgba(37, 99, 235, 0.2); }}
    .score-box.score-hype {{ border-color: rgba(217, 119, 6, 0.25); }}
    .score-box.score-watch {{ border-color: rgba(124, 58, 237, 0.2); }}
    .score-box.score-concerning {{ border-color: rgba(180, 83, 9, 0.25); }}
    .score-box.score-urgent {{ border-color: rgba(220, 38, 38, 0.25); }}
    .score-number {{ font-size: 32px; line-height: 1; font-weight: 900; }}
    .score-caption {{ margin-top: 6px; color: var(--muted); font-size: 12px; }}
    .panel-summary {{
      margin: 14px 0 0;
      color: var(--text);
      font-size: 15px;
      line-height: 1.65;
    }}
    .section-card {{
      margin-top: 16px;
      padding: 16px;
      border-radius: 20px;
      border: 1px solid var(--border);
      background: #ffffff;
    }}
    .section-title {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      font-weight: 800;
    }}
    .section-title svg {{ width: 14px; height: 14px; color: var(--accent); }}
    .section-copy {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}
    .note-list {{
      margin: 12px 0 0;
      padding-left: 18px;
      color: var(--text);
      line-height: 1.55;
      font-size: 14px;
    }}
    .note-list li {{ margin: 6px 0; }}
    .chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .mini-pill {{
      display: inline-flex;
      align-items: center;
      padding: 5px 10px;
      border-radius: 999px;
      background: rgba(123, 223, 242, 0.16);
      border: 1px solid rgba(123, 223, 242, 0.24);
      font-size: 12px;
      color: var(--text);
    }}
    .mini-pill.soft {{
      background: #f8fafc;
      border-color: var(--border);
      color: var(--muted);
    }}
    .headline-list {{
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }}
    .headline {{
      padding: 12px 14px;
      border-radius: 16px;
      background: #f8fafc;
      border-left: 4px solid transparent;
    }}
    .headline.negative {{ border-left-color: var(--danger); }}
    .headline.neutral {{ border-left-color: var(--warning); }}
    .headline.positive {{ border-left-color: var(--good); }}
    .headline-top {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
    }}
    .headline a {{ font-weight: 800; color: var(--text); }}
    .headline-chip {{
      flex: 0 0 auto;
      padding: 4px 8px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.8);
      border: 1px solid var(--border);
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .headline-meta {{
      margin-top: 5px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    .panel-side {{
      display: grid;
      gap: 12px;
      align-content: start;
    }}
    .side-card {{
      padding: 16px;
      border-radius: 18px;
      border: 1px solid var(--border);
      background: #ffffff;
    }}
    .side-title {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      font-weight: 800;
    }}
    .big-read {{
      margin-top: 8px;
      font-size: 22px;
      font-weight: 900;
      letter-spacing: -0.03em;
    }}
    .side-copy {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}
    .count-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .count-grid div {{
      padding: 10px 12px;
      border-radius: 14px;
      background: var(--panel-soft);
      border: 1px solid var(--border);
    }}
    .count-grid span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }}
    .count-grid strong {{ font-size: 20px; }}
    .overview-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .overview-tile {{
      padding: 14px;
      border-radius: 18px;
      background: #ffffff;
      border: 1px solid var(--border);
    }}
    .overview-label {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 800;
    }}
    .overview-value {{
      margin-top: 8px;
      font-size: 22px;
      font-weight: 900;
    }}
    .overview-copy {{
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.55;
    }}
    .event-list {{
      margin-top: 10px;
      display: grid;
      gap: 10px;
    }}
    .event-row {{
      display: grid;
      grid-template-columns: 160px 150px 1fr;
      gap: 10px;
      padding: 12px 0;
      border-bottom: 1px solid rgba(16, 24, 40, 0.08);
    }}
    .event-time, .event-label {{
      color: var(--muted);
      font-size: 12px;
    }}
    .event-label {{ font-weight: 800; color: var(--accent2); }}
    .footer {{
      margin: 16px 0 30px;
      color: var(--muted);
      font-size: 12px;
    }}
    .alert-note {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }}
    @media (max-width: 980px) {{
      .hero, .topline, .panel-grid {{ grid-template-columns: 1fr; }}
      .overview-grid {{ grid-template-columns: 1fr 1fr; }}
      .event-row {{ grid-template-columns: 1fr; }}
      .brand-title {{ font-size: 32px; }}
      .panel-header {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div>
        <div class="brandline">
          <div class="brand-mark">{icon_svg("brand")}</div>
          <div class="brand-copy">
            <div class="brand-kicker">Live market briefing</div>
            <h1 class="brand-title">stock_news_watch</h1>
          </div>
        </div>
        <p class="subtitle">
          This page is tuned for a weekly and monthly read, not for tiny intraday moves.
          It groups the live news into one tab per stock so you can see if the story is just noise, worth watching, or likely to turn bad.
        </p>
        <div class="pillbar">
          <span class="pill">{icon_svg("clock")} Refresh {refresh_seconds}s</span>
          <span class="pill">{icon_svg("shield")} Status <strong>{esc(heartbeat.get('status') or state.get('status') or 'idle')}</strong></span>
          <span class="pill">{icon_svg("trend")} Overall <strong>{esc(assessment.get('overall_score', heartbeat.get('overall_score', 3)))}</strong>/5</span>
          <span class="pill">{icon_svg("news")} {esc(assessment.get('overall_label') or state.get('overall_label') or 'Mixed / watch')}</span>
        </div>
      </div>
      <div class="status-card">
        <div class="metric-card">
          <div class="metric-label">Overall read</div>
          <div class="metric-value">{esc(assessment.get('overall_label') or state.get('overall_label') or 'Mixed / watch')}</div>
          <div class="metric-copy">
            This is the combined view across all watched stocks, focused on whether anything looks likely to matter in the next week or month.
          </div>
        </div>
        <div class="metric-card">
          <div class="metric-label">Current briefing</div>
          <div class="metric-value" style="font-size: 18px; line-height: 1.45;">{esc(heartbeat.get('last_summary') or state.get('current_summary') or 'No data yet')}</div>
          <div class="metric-copy">
            Last check: {esc(heartbeat.get('last_check_utc') or state.get('last_check_utc') or 'n/a')}<br/>
            Last alert: {esc(heartbeat.get('last_alert_utc') or state.get('last_alert_utc') or 'n/a')}
          </div>
        </div>
      </div>
    </section>

    <section class="topline">
      <div class="panel">
        <div class="overview-grid">
          <div class="overview-tile">
            <div class="overview-label">{icon_svg("clock")} Cycle count</div>
            <div class="overview-value">{esc(heartbeat.get('cycle_count', 0))}</div>
            <div class="overview-copy">How many live checks have run so far.</div>
          </div>
          <div class="overview-tile">
            <div class="overview-label">{icon_svg("news")} Sources</div>
            <div class="overview-value">{esc(heartbeat.get('source_count', 0))}</div>
            <div class="overview-copy">How many distinct live sources were used.</div>
          </div>
          <div class="overview-tile">
            <div class="overview-label">{icon_svg("alert")} Alerts</div>
            <div class="overview-value">{esc(heartbeat.get('alert_count', state.get('alert_count', 0)))}</div>
            <div class="overview-copy">Only real concern flags, not routine noise.</div>
          </div>
          <div class="overview-tile">
            <div class="overview-label">{icon_svg("tabs")} Stocks</div>
            <div class="overview-value">{esc(len(briefs))}</div>
            <div class="overview-copy">One tab per stock for a quick read.</div>
          </div>
        </div>
        <div class="alert-note">
          The score is a horizon score. A 5 or 6 means the story could become a real problem in the next week or month. A 1 to 4 usually means it is okay, hype, mixed, or still just watchable.
        </div>
      </div>

      <div class="panel">
        <div class="metric-label">Recent events</div>
        <div class="event-list">
          {''.join(event_rows) if event_rows else '<div class="overview-copy">No events yet.</div>'}
        </div>
      </div>
    </section>

    <section class="panel tabs-panel" style="margin-top: 18px;">
      <div class="metric-label">Select stock</div>
      <div class="tabbar">
        {''.join(tab_buttons) if tab_buttons else '<div class="overview-copy">No stock briefs yet. Run a cycle to populate the page.</div>'}
      </div>
      {''.join(panels) if panels else '<div class="overview-copy">No stock briefs yet. Run a cycle to populate the page.</div>'}
    </section>

    <div class="footer">
      Runtime root: {esc(snapshot.get('runtime_root', 'n/a'))}
    </div>
  </div>
  <script>
    const buttons = Array.from(document.querySelectorAll('.tab-button'));
    const panels = Array.from(document.querySelectorAll('.panel[data-panel]'));
    function show(symbol) {{
      buttons.forEach(btn => btn.classList.toggle('active', btn.dataset.symbol === symbol));
      panels.forEach(panel => panel.hidden = panel.dataset.panel !== symbol);
      const data = window.__SNAPSHOT__ || {{}};
      document.title = 'stock_news_watch · ' + symbol;
    }}
    buttons.forEach(btn => btn.addEventListener('click', () => show(btn.dataset.symbol)));
    if (buttons.length) {{
      show(buttons.find(btn => btn.classList.contains('active'))?.dataset.symbol || buttons[0].dataset.symbol);
    }}
    async function refreshSnapshot() {{
      try {{
        const res = await fetch('/api/state', {{ cache: 'no-store' }});
        const data = await res.json();
        window.__SNAPSHOT__ = data;
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
            self._send_html(
                render_dashboard_html(
                    self.server.engine.snapshot(),
                    self.server.engine.config.dashboard.refresh_seconds,
                )
            )
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
