from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


class AutoApprovalPolicy:
    """Auto-approves safe runtime writes and read-only checks only."""

    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root.resolve()

    def approve(self, action_type: str, target: Path | None = None) -> PolicyDecision:
        action = str(action_type).strip().lower()
        if action in {"noop", "read", "fetch", "collect", "analyze", "review"}:
            return PolicyDecision(True, "read_only")
        if target is None:
            return PolicyDecision(False, "missing_target")
        resolved = target.resolve()
        try:
            resolved.relative_to(self.runtime_root)
        except ValueError:
            return PolicyDecision(False, "outside_runtime_root")
        if action in {"write_heartbeat", "write_state", "write_assessment", "append_event", "append_log"}:
            return PolicyDecision(True, "auto_approved_runtime_write")
        return PolicyDecision(False, "blocked_action")

