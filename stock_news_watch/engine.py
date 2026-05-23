from __future__ import annotations

import json
import threading
import time
from datetime import datetime, time as dt_time, timedelta, tzinfo, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .codex_client import CodexReviewer
from .config import AppConfig, default_config_path
from .news import NewsItem, collect_news_bundle
from .policy import AutoApprovalPolicy
from .state import RuntimePaths, append_jsonl, default_state, load_json, utc_now, write_json


def parse_hhmm(value: str) -> dt_time:
    hour, minute = [int(part) for part in value.split(":", 1)]
    return dt_time(hour=hour, minute=minute)


class EasternTime(tzinfo):
    """Self-contained US/Eastern timezone with DST rules for demo purposes."""

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return self.standard_offset(dt) + self.dst(dt)

    def dst(self, dt: datetime | None) -> timedelta:
        if dt is None:
            return timedelta(0)
        if self._is_dst(dt):
            return timedelta(hours=1)
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "EDT" if self._is_dst(dt) else "EST"

    def standard_offset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=-5)

    def _is_dst(self, dt: datetime) -> bool:
        year = dt.year
        dst_start = self._second_sunday(year, 3).replace(hour=2, minute=0, second=0, microsecond=0)
        dst_end = self._first_sunday(year, 11).replace(hour=2, minute=0, second=0, microsecond=0)
        naive = dt.replace(tzinfo=None)
        return dst_start <= naive < dst_end

    def _first_sunday(self, year: int, month: int) -> datetime:
        dt = datetime(year, month, 1)
        offset = (6 - dt.weekday()) % 7
        return dt + timedelta(days=offset)

    def _second_sunday(self, year: int, month: int) -> datetime:
        return self._first_sunday(year, month) + timedelta(days=7)


class StockNewsWatchEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.paths = RuntimePaths.ensure(config.runtime_path)
        self.policy = AutoApprovalPolicy(self.paths.root)
        self.state_lock = threading.Lock()
        self.state_file = self.paths.state_file
        self.heartbeat_file = self.paths.heartbeat_file
        self.assessment_file = self.paths.assessment_file
        self.events_file = self.paths.events_file
        self._state = load_json(self.state_file, default_state())
        self._state = self._normalize_state(self._state)
        self._save_state()

    @classmethod
    def from_default_config(cls, config_path: Path | None = None) -> "StockNewsWatchEngine":
        path = config_path or default_config_path()
        return cls(AppConfig.from_file(path))

    def _normalize_state(self, state: dict[str, Any]) -> dict[str, Any]:
        base = default_state()
        base.update(state or {})
        base["cycle_count"] = int(base.get("cycle_count", 0) or 0)
        base["alert_count"] = int(base.get("alert_count", 0) or 0)
        base["source_count"] = int(base.get("source_count", 0) or 0)
        base["revision"] = int(base.get("revision", 0) or 0)
        if str(base.get("overall_label", "")).strip().lower() == "wait and see":
            base["overall_label"] = "Mixed / watch"
        return base

    def _save_state(self) -> None:
        decision = self.policy.approve("write_state", self.state_file)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
        write_json(self.state_file, self._state)

    def _write_heartbeat(self, heartbeat: dict[str, Any]) -> None:
        decision = self.policy.approve("write_heartbeat", self.heartbeat_file)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
        write_json(self.heartbeat_file, heartbeat)

    def _write_assessment(self, assessment: dict[str, Any]) -> None:
        decision = self.policy.approve("write_assessment", self.assessment_file)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
        write_json(self.assessment_file, assessment)

    def _append_event(self, event: dict[str, Any]) -> None:
        decision = self.policy.approve("append_event", self.events_file)
        if not decision.allowed:
            raise RuntimeError(decision.reason)
        append_jsonl(self.events_file, event)

    def _market_zone(self) -> tzinfo:
        try:
            return ZoneInfo(self.config.runtime.market_timezone)
        except Exception:
            if self.config.runtime.market_timezone == "America/New_York":
                return EasternTime()
            raise

    def _market_window(self, now: datetime | None = None) -> tuple[bool, datetime]:
        if str(self.config.runtime.schedule_mode).strip().lower() in {"always_on", "24x7", "24/7", "always"}:
            now = now or datetime.now(self._market_zone())
            return True, now.astimezone(self._market_zone())
        now = now or datetime.now(self._market_zone())
        local = now.astimezone(self._market_zone())
        if local.weekday() >= 5:
            return False, local
        preopen = parse_hhmm(self.config.runtime.preopen_start)
        close = parse_hhmm(self.config.runtime.market_close)
        local_time = local.time()
        return preopen <= local_time < close, local

    def _due_for_cycle(self, now_utc: datetime | None = None) -> bool:
        now_utc = now_utc or datetime.now(timezone.utc)
        last_check = self._state.get("last_check_utc") or ""
        if not last_check:
            return True
        try:
            last_dt = datetime.fromisoformat(str(last_check).replace("Z", "+00:00"))
        except Exception:
            return True
        delta = (now_utc - last_dt).total_seconds()
        return delta >= int(self.config.runtime.run_interval_seconds)

    def run_cycle(self, force: bool = False) -> dict[str, Any]:
        with self.state_lock:
            now_utc = datetime.now(timezone.utc)
            market_active, local_now = self._market_window(now_utc)
            if not market_active and not force:
                self._state["status"] = "waiting_market_hours"
                self._state["current_summary"] = "Outside active market window"
                self._state["revision"] = int(self._state.get("revision", 0)) + 1
                self._state["model"] = self.config.codex.model
                self._save_state()
                self._write_heartbeat(self._heartbeat_payload(local_now, source_count=0))
                return self.snapshot()

            if not force and not self._due_for_cycle(now_utc):
                self._state["status"] = "waiting_interval"
                self._state["current_summary"] = "Waiting for the next hourly check"
                self._state["revision"] = int(self._state.get("revision", 0)) + 1
                self._state["model"] = self.config.codex.model
                self._save_state()
                self._write_heartbeat(self._heartbeat_payload(local_now, source_count=int(self._state.get("source_count", 0) or 0)))
                return self.snapshot()

            bundle = collect_news_bundle(
                symbols=list(self.config.sources.google_queries.keys()),
                sources_cfg={
                    "news_google_rss_base": self.config.sources.news_google_rss_base,
                    "yahoo_rss_base": self.config.sources.yahoo_rss_base,
                    "google_queries": self.config.sources.google_queries,
                    "sec_forms": self.config.sources.sec_forms,
                    "company_pages": self.config.sources.company_pages,
                },
            )

            reviewer = CodexReviewer(
                exe=self.config.codex.exe,
                model=self.config.codex.model,
                reasoning_effort=self.config.codex.reasoning_effort,
                web_search_mode=self.config.codex.web_search_mode,
                network_access_enabled=self.config.codex.network_access_enabled,
                sandbox=self.config.codex.sandbox,
                skip_git_repo_check=self.config.codex.skip_git_repo_check,
                timeout_sec=self.config.codex.timeout_sec,
            )
            review = reviewer.review(
                items=bundle,
                symbols=list(self.config.sources.google_queries.keys()),
                codex_home=self.paths.root / "codex_home",
                thread_file=self.paths.codex_thread_file,
                trace_dir=self.paths.codex_trace_dir,
            )

            self._state["status"] = "alerting" if review.alert else "clean"
            self._state["last_check_utc"] = utc_now()
            self._state["source_count"] = len({item.source for item in bundle})
            self._state["cycle_count"] = int(self._state.get("cycle_count", 0) or 0) + 1
            self._state["revision"] = int(self._state.get("revision", 0) or 0) + 1
            self._state["model"] = review.model
            self._state["overall_score"] = int(review.overall_score)
            self._state["overall_label"] = review.overall_label
            self._state["current_summary"] = f"{review.overall_label}: {review.summary}"
            if review.alert:
                self._state["alert_count"] = int(self._state.get("alert_count", 0) or 0) + 1
                self._state["last_alert_utc"] = self._state["last_check_utc"]

            self._save_state()

            assessment = {
                "updated_utc": utc_now(),
                "status": review.overall_status,
                "alert": review.alert,
                "overall_score": review.overall_score,
                "overall_label": review.overall_label,
                "summary": review.summary,
                "reasons": review.reasons,
                "signals": review.signals,
                "sources_reviewed": review.sources_reviewed,
                "decision_source": review.decision_source,
                "model": review.model,
                "briefs": review.briefs,
                "items": [item.to_dict() for item in bundle[:80]],
            }
            self._write_assessment(assessment)

            event = {
                "ts_utc": utc_now(),
                "kind": "cycle",
                "severity": review.overall_status,
                "score": review.overall_score,
                "label": review.overall_label,
                "summary": review.summary,
                "symbols": list(self.config.sources.google_queries.keys()),
                "source_count": len({item.source for item in bundle}),
                "urls": [signal["url"] for signal in review.signals],
                "decision_source": review.decision_source,
            }
            self._append_event(event)
            self._write_heartbeat(self._heartbeat_payload(local_now, source_count=len({item.source for item in bundle})))
            return self.snapshot()

    def _heartbeat_payload(self, local_now: datetime, source_count: int) -> dict[str, Any]:
        payload = {
            "updated_utc": utc_now(),
            "status": self._state.get("status", "idle"),
            "last_check_utc": self._state.get("last_check_utc", ""),
            "last_alert_utc": self._state.get("last_alert_utc", ""),
            "last_summary": self._state.get("current_summary", ""),
            "cycle_count": int(self._state.get("cycle_count", 0) or 0),
            "source_count": int(source_count),
            "model": self._state.get("model", self.config.codex.model),
            "revision": int(self._state.get("revision", 0) or 0),
            "market_time_local": local_now.isoformat(),
            "clean": self._state.get("status") == "clean",
            "alert": self._state.get("status") == "alerting",
            "overall_score": int(self._state.get("overall_score", 3) or 3),
            "overall_label": self._state.get("overall_label", "Mixed / watch"),
        }
        return payload

    def snapshot(self) -> dict[str, Any]:
        state = load_json(self.state_file, default_state())
        heartbeat = load_json(self.heartbeat_file, {})
        assessment = load_json(self.assessment_file, {})
        events = []
        if self.events_file.exists():
            events = self.events_file.read_text(encoding="utf-8", errors="replace").splitlines()
            events = [json.loads(line) for line in events[-50:] if line.strip()]
        return {
            "config": {
                "workspace_root": str(self.config.workspace_root),
                "model": self.config.codex.model,
                "timezone": self.config.runtime.market_timezone,
            },
            "state": state,
            "heartbeat": heartbeat,
            "assessment": assessment,
            "recent_events": events,
            "runtime_root": str(self.paths.root),
        }

    def run_forever(self) -> None:
        while not self.paths.stop_file.exists():
            try:
                self.run_cycle(force=False)
            except Exception as exc:
                with self.state_lock:
                    self._state["status"] = "error"
                    self._state["current_summary"] = f"error: {exc}"
                    self._state["revision"] = int(self._state.get("revision", 0) or 0) + 1
                    self._save_state()
                    self._write_heartbeat(
                        {
                            "updated_utc": utc_now(),
                            "status": "error",
                            "last_check_utc": self._state.get("last_check_utc", ""),
                            "last_alert_utc": self._state.get("last_alert_utc", ""),
                            "last_summary": str(exc),
                            "cycle_count": int(self._state.get("cycle_count", 0) or 0),
                            "source_count": int(self._state.get("source_count", 0) or 0),
                            "model": self.config.codex.model,
                            "revision": int(self._state.get("revision", 0) or 0),
                            "clean": False,
                            "alert": False,
                            "overall_score": int(self._state.get("overall_score", 3) or 3),
                        }
                    )
            time.sleep(max(5, self.config.runtime.poll_seconds))
