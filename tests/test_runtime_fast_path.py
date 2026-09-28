from __future__ import annotations

import unittest
from unittest.mock import patch
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class RuntimeFastPathTests(unittest.TestCase):
    def test_doctor_current_fingerprint_does_not_launch_release_or_tests(self):
        import doctor

        runtime = {
            "fingerprint": "same", "python": {"path": "python", "version": "3.12"},
            "node": {"path": "node", "version": "v22"}, "node_modules": "modules",
            "playwright": True, "chrome": {"path": "chrome", "version": "detected"}, "python_docx": True,
        }
        with patch.object(doctor, "discover", return_value=runtime), patch.object(doctor, "capability_errors", return_value=[]), patch.object(doctor, "load_verified_state", return_value={"verified": True, "fingerprint": "same"}), patch.object(doctor, "state_is_current", return_value=True), patch("subprocess.run") as run:
            _, errors = doctor.check(node="node")
        self.assertEqual(errors, [])
        run.assert_not_called()

    def test_pipeline_source_never_calls_release_gate_and_layout_gate_occurs_once(self):
        text = (ROOT / "scripts" / "run_report_pipeline.py").read_text(encoding="utf-8")
        self.assertNotIn("verify_skill.py", text)
        self.assertEqual(text.count('SCRIPTS / "verify_html_layout.mjs"'), 1)

    def test_runtime_requirements_define_shared_network_limits(self):
        import json

        payload = json.loads((ROOT / "runtime-requirements.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["network"], {
            "connect_timeout_seconds": 10,
            "read_timeout_seconds": 30,
            "max_retries": 2,
            "max_concurrency": 4,
            "per_host_concurrency": 2,
        })


if __name__ == "__main__":
    unittest.main()
