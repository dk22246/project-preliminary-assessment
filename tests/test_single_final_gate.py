from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class SingleFinalGateTests(unittest.TestCase):
    def test_finalize_calls_full_suite_once_and_advances_all_receipts(self):
        import ppa
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            for name in workflow_state.REPORT_ARTIFACTS:
                (work_dir / name).write_text("{}\n", encoding="utf-8")
            workflow_state.create(work_dir, "测试企业", "fingerprint")
            args = type("Args", (), {"work_dir": str(work_dir), "node": None, "chrome": None})()
            hashes = workflow_state.artifact_hashes(work_dir)
            with patch.object(ppa, "require_ready_runtime"), patch.object(ppa, "package_fingerprint", return_value="fingerprint"), patch.object(ppa, "_validate_lightweight_stage", return_value={"compiled": True}) as light, patch.object(ppa, "_validate_final_suite", return_value=hashes) as final:
                self.assertEqual(ppa.command_finalize(args), 0)
            self.assertEqual(final.call_count, 1)
            self.assertEqual(light.call_count, 6)
            self.assertEqual(workflow_state.load(work_dir)["current_stage"], "report_ready")

    def test_deliver_trusted_path_does_not_repeat_formal_validators(self):
        text = (ROOT / "scripts" / "run_report_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("if not trusted_workflow or args.fixture_mode", text)
        self.assertIn("pipeline(call, trusted_workflow=True)", (ROOT / "scripts" / "ppa.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
