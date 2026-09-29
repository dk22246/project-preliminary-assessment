from __future__ import annotations

import unittest
from unittest.mock import patch
import tempfile
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
            "playwright": True, "chrome": {"path": "chrome", "version": "detected"}, "pypdf": True,
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
        self.assertIn("requirements-runtime.txt", payload["fingerprint_files"])
        policy_rules = (ROOT / "references" / "policy-search-coverage.md").read_text(encoding="utf-8")
        self.assertIn("同域名并发2路", policy_rules)
        self.assertNotIn("同域名并发1路", policy_rules)

    def test_pdf_extraction_is_a_required_verified_runtime_capability(self):
        import runtime_state

        state = {
            "node": {"path": "node", "version": "v22"},
            "playwright": True,
            "chrome": {"path": "chrome", "version": "detected"},
            "pypdf": False,
        }
        errors = runtime_state.capability_errors(state)
        self.assertTrue(any("pypdf" in error for error in errors), errors)
        self.assertTrue((ROOT / "requirements-runtime.txt").is_file())
        self.assertIn("requirements-runtime.txt", runtime_state.dependency_fingerprint_files())
        public_runtime_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "scripts" / "runtime_state.py", ROOT / "scripts" / "evidence_collectors" / "pdf_extract.py", ROOT / "README.md")
        )
        self.assertNotIn("pip install pypdf", public_runtime_text)

    def test_release_smoke_reuses_the_verified_node_instead_of_guessing_from_python(self):
        import preflight

        with tempfile.TemporaryDirectory() as directory:
            node = Path(directory) / "node.exe"
            node.write_text("placeholder", encoding="utf-8")
            verified = {"node": {"path": str(node)}}
            with patch.dict("os.environ", {"REPORT_NODE_EXECUTABLE": ""}, clear=False), patch.object(preflight, "load_verified_state", return_value=verified):
                self.assertEqual(preflight.resolve_smoke_node(), node.resolve())


if __name__ == "__main__":
    unittest.main()
