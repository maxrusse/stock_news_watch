from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .news import NewsItem, build_symbol_bundles


LEVEL_LABELS = {
    1: "Strong positive",
    2: "Okay",
    3: "Beware / short-term hype",
    4: "Mixed / watch",
    5: "Concerning over weeks",
    6: "Likely bad within weeks",
}


@dataclass(frozen=True)
class ReviewResult:
    overall_status: str
    alert: bool
    overall_score: int
    overall_label: str
    summary: str
    reasons: list[str]
    signals: list[dict[str, Any]]
    sources_reviewed: list[str]
    decision_source: str
    model: str
    briefs: list[dict[str, Any]] = field(default_factory=list)


class HeuristicReviewer:
    def review(self, items: list[NewsItem], model: str = "heuristic") -> ReviewResult:
        bundles = build_symbol_bundles(items)
        reviewed_sources = sorted({item.source for item in items})
        summary = f"Packed {len(items)} live items into {len(bundles)} stock buckets." if bundles else "No live items collected."
        return ReviewResult(
            overall_status="watch" if bundles else "clean",
            alert=False,
            overall_score=3,
            overall_label="Mixed / watch",
            summary=summary,
            reasons=[],
            signals=[],
            sources_reviewed=reviewed_sources,
            decision_source="heuristic",
            model=model,
            briefs=[self._placeholder_brief(bundle) for bundle in bundles],
        )

    def _placeholder_brief(self, bundle: dict[str, Any]) -> dict[str, Any]:
        items = list(bundle.get("items", []) or [])
        note = "Raw evidence collected. LLM scoring unavailable."
        return {
            "symbol": bundle.get("symbol", ""),
            "score": 3,
            "label": "Mixed / watch",
            "takeaway": note,
            "why_it_matters": note,
            "summary": note,
            "source_count": int(bundle.get("source_count", 0) or 0),
            "item_count": int(bundle.get("item_count", 0) or 0),
            "themes": [],
            "sources": list(bundle.get("sources", []) or []),
            "top_headlines": [
                {
                    "title": item.get("title", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "published_utc": item.get("published_utc", ""),
                    "kind": item.get("kind", "news"),
                    "tone": "neutral",
                    "why": note,
                }
                for item in items[:4]
            ],
            "critical_notes": [note] if items else [],
            "routine_notes": ["Raw evidence only. LLM scoring unavailable."] if items else [],
        }


class CodexReviewer:
    def __init__(
        self,
        exe: str,
        model: str,
        reasoning_effort: str,
        web_search_mode: str,
        network_access_enabled: bool,
        sandbox: str,
        skip_git_repo_check: bool,
        timeout_sec: int,
    ) -> None:
        self.exe = exe
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.web_search_mode = web_search_mode
        self.network_access_enabled = network_access_enabled
        self.sandbox = sandbox
        self.skip_git_repo_check = skip_git_repo_check
        self.timeout_sec = timeout_sec

    def available(self) -> bool:
        from shutil import which

        return which(self.exe) is not None

    def review(
        self,
        *,
        items: list[NewsItem],
        symbols: list[str],
        prompt_suffix: str = "",
        codex_home: Path | None = None,
        thread_file: Path | None = None,
        trace_dir: Path | None = None,
    ) -> ReviewResult:
        if not self.available():
            return HeuristicReviewer().review(items, model=self.model)

        codex_home = codex_home or Path.home() / ".codex"
        thread_file = thread_file or Path(".runtime/codex_thread_id.txt")
        trace_dir = trace_dir or Path(".runtime/codex_traces")
        trace_dir.mkdir(parents=True, exist_ok=True)
        bundles = build_symbol_bundles(items)

        payload = {
            "symbols": symbols,
            "items": [item.to_dict() for item in items[:80]],
            "bundles": bundles,
            "instruction": (
                "You are reviewing live stock-market news for MSFT, AAPL, and GOOGL. "
                "Return only JSON with overall_status, alert, overall_score, overall_label, summary, reasons, signals, sources_reviewed, briefs. "
                "You will be given raw items and grouped bundles per symbol. Decide exactly one brief per symbol and keep the symbols aligned to the provided buckets. "
                "Use a 6-class horizon scale where 1 is strongly positive, 3 is beware / short-term hype, 4 is mixed / watch, 5 is concerning over weeks, and 6 is likely bad within weeks. "
                "Do not use keyword counting or string matching as the decision rule. Read the evidence and judge the story. "
                "Only call something concerning if it could matter over the next week or month. "
                "Do not recommend trading or liquidation; this is informational only. "
                "For each symbol brief, write in plain language. Include a one-sentence takeaway, a one-sentence why_it_matters, a few short themes, and short critical_notes versus routine_notes so the dashboard can show what is actually important versus what is probably routine. "
                + prompt_suffix
            ),
        }

        schema = {
            "type": "object",
            "properties": {
                "overall_status": {"type": "string", "enum": ["clean", "watch", "critical"]},
                "alert": {"type": "boolean"},
                "overall_score": {"type": "integer"},
                "overall_label": {"type": "string"},
                "summary": {"type": "string"},
                "reasons": {"type": "array", "items": {"type": "string"}},
                "signals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "severity": {"type": "string"},
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "why": {"type": "string"},
                        },
                        "required": ["symbol", "severity", "title", "url", "why"],
                        "additionalProperties": False,
                    },
                },
                "sources_reviewed": {"type": "array", "items": {"type": "string"}},
                "briefs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string"},
                            "score": {"type": "integer"},
                            "label": {"type": "string"},
                            "takeaway": {"type": "string"},
                            "why_it_matters": {"type": "string"},
                            "summary": {"type": "string"},
                            "source_count": {"type": "integer"},
                            "item_count": {"type": "integer"},
                            "themes": {"type": "array", "items": {"type": "string"}},
                            "sources": {"type": "array", "items": {"type": "string"}},
                            "top_headlines": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "source": {"type": "string"},
                                        "url": {"type": "string"},
                                        "published_utc": {"type": "string"},
                                        "kind": {"type": "string"},
                                        "tone": {"type": "string"},
                                        "why": {"type": "string"},
                                    },
                                    "required": ["title", "source", "url", "published_utc", "kind", "tone", "why"],
                                    "additionalProperties": False,
                                },
                            },
                            "critical_notes": {"type": "array", "items": {"type": "string"}},
                            "routine_notes": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["symbol", "score", "label", "summary", "source_count", "item_count", "themes", "sources", "top_headlines"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["overall_status", "alert", "overall_score", "overall_label", "summary", "reasons", "signals", "sources_reviewed", "briefs"],
            "additionalProperties": False,
        }

        schema_path = trace_dir / "codex_review_schema.json"
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")

        cmd = [
            self.exe,
            "exec",
            "--json",
            "--model",
            self.model,
            "--sandbox",
            self.sandbox,
            "--output-schema",
            str(schema_path),
            "--config",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "--config",
            f'web_search="{self.web_search_mode}"',
            "--config",
            "sandbox_workspace_write.network_access=" + ("true" if self.network_access_enabled else "false"),
        ]
        if self.skip_git_repo_check:
            cmd.append("--skip-git-repo-check")

        thread_id = ""
        if thread_file.exists():
            thread_id = thread_file.read_text(encoding="utf-8", errors="ignore").strip()
        if thread_id:
            cmd.extend(["resume", thread_id])

        env = {**os.environ, "CODEX_HOME": str(codex_home)}
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(payload, ensure_ascii=True),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(10, self.timeout_sec),
                env=env,
            )
        except FileNotFoundError:
            return HeuristicReviewer().review(items, model=self.model)
        except OSError:
            return HeuristicReviewer().review(items, model=self.model)
        trace_file = trace_dir / "codex_review_trace.jsonl"
        trace_file.write_text(proc.stdout or "", encoding="utf-8")

        parsed = _parse_codex_jsonl(proc.stdout or "")
        if parsed is None:
            return HeuristicReviewer().review(items, model=self.model)
        return _normalize_review(parsed, items=items, symbols=symbols, bundles=bundles, model=self.model)


def _parse_codex_jsonl(stdout_text: str) -> dict[str, Any] | None:
    parsed: dict[str, Any] | None = None
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        try:
            obj = json.loads(text)
        except Exception:
            continue
        if isinstance(obj, dict):
            parsed = obj
    return parsed


def _score_to_label(score: int) -> str:
    return LEVEL_LABELS.get(score, "Mixed / watch")


def _clamp_score(value: Any, default: int = 3) -> int:
    try:
        score = int(value)
    except Exception:
        score = default
    return max(1, min(6, score))


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for entry in value:
        text = str(entry).strip()
        if text:
            result.append(text)
    return result


def _brief_from_bundle(bundle: dict[str, Any], *, note: str, score: int = 3, label: str = "Mixed / watch") -> dict[str, Any]:
    items = list(bundle.get("items", []) or [])
    themes = _as_str_list(bundle.get("themes", []))
    top_headlines = []
    for item in items[:4]:
        top_headlines.append(
            {
                "title": str(item.get("title", "")),
                "source": str(item.get("source", "")),
                "url": str(item.get("url", "")),
                "published_utc": str(item.get("published_utc", "")),
                "kind": str(item.get("kind", "news")),
                "tone": "neutral",
                "why": note,
            }
        )
    return {
        "symbol": str(bundle.get("symbol", "")).upper(),
        "score": score,
        "label": label,
        "takeaway": note,
        "why_it_matters": note,
        "summary": note,
        "source_count": int(bundle.get("source_count", 0) or 0),
        "item_count": int(bundle.get("item_count", 0) or 0),
        "themes": themes,
        "sources": _as_str_list(bundle.get("sources", [])),
        "top_headlines": top_headlines,
        "critical_notes": [note] if items else [],
        "routine_notes": ["Raw evidence only. LLM scoring unavailable."] if items else [],
    }


def _normalize_brief(brief: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    score = _clamp_score(brief.get("score", 3))
    label = _score_to_label(score)
    summary = str(brief.get("summary", "")).strip() or str(brief.get("takeaway", "")).strip()
    takeaway = str(brief.get("takeaway", "")).strip() or summary
    why_it_matters = str(brief.get("why_it_matters", "")).strip() or summary or takeaway
    if not summary:
        summary = "LLM review produced a bucket with no summary."
    if not takeaway:
        takeaway = summary
    if not why_it_matters:
        why_it_matters = summary

    sources = _as_str_list(brief.get("sources", [])) or _as_str_list(bundle.get("sources", []))
    themes = _as_str_list(brief.get("themes", []))
    source_count = int(brief.get("source_count", bundle.get("source_count", 0)) or 0)
    item_count = int(brief.get("item_count", bundle.get("item_count", 0)) or 0)
    top_headlines_raw = brief.get("top_headlines", [])
    top_headlines: list[dict[str, Any]] = []
    if isinstance(top_headlines_raw, list):
        for item in top_headlines_raw[:4]:
            if not isinstance(item, dict):
                continue
            top_headlines.append(
                {
                    "title": str(item.get("title", "")),
                    "source": str(item.get("source", "")),
                    "url": str(item.get("url", "")),
                    "published_utc": str(item.get("published_utc", "")),
                    "kind": str(item.get("kind", "news")),
                    "tone": str(item.get("tone", "neutral")),
                    "why": str(item.get("why", summary or takeaway)),
                }
            )
    if not top_headlines:
        top_headlines = _brief_from_bundle(bundle, note=why_it_matters, score=score, label=label)["top_headlines"]

    critical_notes = _as_str_list(brief.get("critical_notes", []))
    routine_notes = _as_str_list(brief.get("routine_notes", []))
    if not critical_notes and score >= 5:
        critical_notes = [why_it_matters]
    if not routine_notes and score <= 3:
        routine_notes = [takeaway]

    return {
        "symbol": str(brief.get("symbol", bundle.get("symbol", ""))).upper(),
        "score": score,
        "label": label,
        "takeaway": takeaway,
        "why_it_matters": why_it_matters,
        "summary": summary,
        "source_count": source_count,
        "item_count": item_count,
        "themes": themes,
        "sources": sources,
        "top_headlines": top_headlines,
        "critical_notes": critical_notes,
        "routine_notes": routine_notes,
    }


def _normalize_review(
    parsed: dict[str, Any],
    *,
    items: list[NewsItem],
    symbols: list[str],
    bundles: list[dict[str, Any]],
    model: str,
) -> ReviewResult:
    bundle_map = {str(bundle.get("symbol", "")).upper(): bundle for bundle in bundles}
    parsed_briefs = [dict(x) for x in parsed.get("briefs", []) if isinstance(x, dict)]
    brief_map = {str(brief.get("symbol", "")).upper(): brief for brief in parsed_briefs if str(brief.get("symbol", "")).strip()}

    normalized_briefs: list[dict[str, Any]] = []
    for symbol in symbols:
        symbol_key = str(symbol).upper()
        bundle = bundle_map.get(symbol_key, {"symbol": symbol_key, "item_count": 0, "source_count": 0, "sources": [], "items": []})
        raw_brief = brief_map.get(symbol_key)
        if raw_brief is None:
            normalized_briefs.append(_brief_from_bundle(bundle, note="Raw evidence collected. LLM did not return a usable brief for this symbol."))
        else:
            normalized_briefs.append(_normalize_brief(raw_brief, bundle))

    overall_score = _clamp_score(parsed.get("overall_score", 3))
    overall_label = _score_to_label(overall_score)
    summary = str(parsed.get("summary", "")).strip() or "Codex returned a market summary."
    reasons = _as_str_list(parsed.get("reasons", []))
    signals = [dict(x) for x in parsed.get("signals", []) if isinstance(x, dict)]
    sources_reviewed = _as_str_list(parsed.get("sources_reviewed", []))
    if not sources_reviewed:
        sources_reviewed = sorted({item.source for item in items})

    if overall_score >= 5:
        overall_status = "critical"
    elif overall_score >= 3:
        overall_status = "watch"
    else:
        overall_status = "clean"
    alert = bool(parsed.get("alert", False)) or overall_status == "critical"

    return ReviewResult(
        overall_status=overall_status,
        alert=alert,
        overall_score=overall_score,
        overall_label=overall_label,
        summary=summary,
        reasons=reasons,
        signals=signals,
        sources_reviewed=sources_reviewed,
        decision_source="codex",
        model=model,
        briefs=normalized_briefs,
    )
