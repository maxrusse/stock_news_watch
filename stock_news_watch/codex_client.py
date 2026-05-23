from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .news import NewsItem, build_symbol_bundles


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

        payload = {
            "symbols": symbols,
            "items": [item.to_dict() for item in items[:80]],
            "bundles": build_symbol_bundles(items),
            "instruction": (
                "You are reviewing live stock-market news for MSFT, AAPL, and GOOGL. "
                "Return only JSON with overall_status, alert, overall_score, overall_label, summary, reasons, signals, sources_reviewed, briefs. "
                "You will be given raw items and grouped bundles per symbol. Decide the buckets and scores yourself. "
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
        return ReviewResult(
            overall_status=str(parsed.get("overall_status", "clean")),
            alert=bool(parsed.get("alert", False)),
            overall_score=int(parsed.get("overall_score", 3) or 3),
            overall_label=str(parsed.get("overall_label", "Mixed / watch")),
            summary=str(parsed.get("summary", "")).strip(),
            reasons=[str(x) for x in parsed.get("reasons", [])],
            signals=[dict(x) for x in parsed.get("signals", []) if isinstance(x, dict)],
            sources_reviewed=[str(x) for x in parsed.get("sources_reviewed", [])],
            decision_source="codex",
            model=self.model,
            briefs=[dict(x) for x in parsed.get("briefs", []) if isinstance(x, dict)],
        )


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
