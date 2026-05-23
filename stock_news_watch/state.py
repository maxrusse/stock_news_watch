from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True))
        handle.write("\n")


def read_jsonl_tail(path: Path, limit: int = 25) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-limit:]
    records: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


@dataclass
class RuntimePaths:
    root: Path

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    @property
    def heartbeat_file(self) -> Path:
        return self.root / "heartbeat.json"

    @property
    def assessment_file(self) -> Path:
        return self.root / "latest_assessment.json"

    @property
    def events_file(self) -> Path:
        return self.root / "events.jsonl"

    @property
    def stop_file(self) -> Path:
        return self.root / "STOP"

    @property
    def codex_thread_file(self) -> Path:
        return self.root / "codex_thread_id.txt"

    @property
    def codex_trace_dir(self) -> Path:
        return self.root / "codex_traces"

    @classmethod
    def ensure(cls, root: Path) -> "RuntimePaths":
        root.mkdir(parents=True, exist_ok=True)
        (root / "codex_traces").mkdir(parents=True, exist_ok=True)
        return cls(root=root)


def default_state() -> dict[str, Any]:
    return {
        "status": "idle",
        "run_id": "",
        "started_utc": "",
        "last_check_utc": "",
        "last_alert_utc": "",
        "cycle_count": 0,
        "alert_count": 0,
        "source_count": 0,
        "current_summary": "idle",
        "revision": 0,
        "model": "",
    }

