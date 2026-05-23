from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from stock_news_watch.policy import AutoApprovalPolicy


class PolicyTests(unittest.TestCase):
    def test_runtime_writes_are_auto_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            policy = AutoApprovalPolicy(runtime)
            self.assertTrue(policy.approve("write_heartbeat", runtime / "heartbeat.json").allowed)
            self.assertTrue(policy.approve("append_event", runtime / "events.jsonl").allowed)

    def test_outside_runtime_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp)
            policy = AutoApprovalPolicy(runtime)
            self.assertFalse(policy.approve("write_heartbeat", Path(tmp).parent / "bad.json").allowed)


if __name__ == "__main__":
    unittest.main()

