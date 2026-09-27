from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class FastPathMetricsTests(unittest.TestCase):
    def test_phase_seconds_are_derived_from_workflow_history(self):
        import workflow_state

        start = datetime(2026, 9, 15, 1, 0, tzinfo=timezone.utc)
        payload = {
            "created_at": start.isoformat(),
            "history": [
                {"stage": "entity_confirmed", "completed_at": start.isoformat()},
                {"stage": "enterprise_research_complete", "completed_at": (start + timedelta(seconds=125)).isoformat()},
                {"stage": "landing_businesses_complete", "completed_at": (start + timedelta(seconds=180)).isoformat()},
                {"stage": "policy_research_complete", "completed_at": (start + timedelta(seconds=390)).isoformat()},
            ],
        }
        self.assertEqual(workflow_state.phase_seconds(payload, "entity_confirmed", "enterprise_research_complete"), 125.0)
        self.assertEqual(workflow_state.phase_seconds(payload, "landing_businesses_complete", "policy_research_complete"), 210.0)

    def test_completed_stage_records_elapsed_seconds(self):
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            workflow_state.create(work_dir, "测试企业有限公司", "fingerprint")
            payload = workflow_state.complete_stage(work_dir, "entity_confirmed", {"ok": True})
            row = payload["history"][-1]
            self.assertIn("started_at", row)
            self.assertIn("elapsed_seconds", row)
            self.assertGreaterEqual(row["elapsed_seconds"], 0)

    def test_report_pipeline_does_not_publish_zero_placeholder_metrics(self):
        text = (ROOT / "scripts" / "run_report_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn('"enterprise_research_seconds": 0', text)
        self.assertNotIn('"policy_discovery_seconds": 0', text)
        self.assertIn('"enterprise_research_seconds": None', text)
        self.assertIn('"timing_scope"', text)
        self.assertIn('"phase_seconds"', text)
        self.assertIn('"full_release_tests_run": False', text)


if __name__ == "__main__":
    unittest.main()
