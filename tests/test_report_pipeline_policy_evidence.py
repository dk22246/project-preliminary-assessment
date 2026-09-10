import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ReportPipelinePolicyEvidenceTests(unittest.TestCase):
    def test_preflight_smoke_uses_packaged_policy_evidence_in_explicit_fixture_mode(self):
        import preflight

        self.assertTrue(hasattr(preflight, "smoke_arguments"), "preflight must expose deterministic smoke arguments")
        if not hasattr(preflight, "smoke_arguments"):
            return
        command = preflight.smoke_arguments(Path("out"), Path("node.exe"))
        self.assertIn("--fixture-mode", command)
        index = command.index("--policy-evidence")
        self.assertTrue(str(command[index + 1]).endswith("flyco-policy-evidence.json"))

    def test_formal_pipeline_requires_policy_evidence_argument(self):
        from run_report_pipeline import main

        with self.assertRaises(SystemExit) as raised:
            main([
                "report-data.json", "--equity-evidence", "equity-evidence.json",
                "--research-ledger", "research-ledger.json", "--policy-search-ledger", "policy-search-ledger.json",
                "--out-dir", "outputs/test", "--node", "node.exe",
            ])
        self.assertEqual(raised.exception.code, 2)

    def test_fixture_mode_is_explicitly_forwarded_to_policy_evidence_validator(self):
        import run_report_pipeline as pipeline

        with tempfile.TemporaryDirectory() as value:
            node = Path(value) / "node.exe"
            node.write_text("placeholder", encoding="utf-8")
            commands = []

            class Result:
                returncode = 0

            with patch.object(pipeline, "check_runtime", return_value=({"node": {"path": str(node)}}, [])), patch.object(pipeline, "run", side_effect=lambda command, **_: commands.append(command)), patch.object(pipeline.subprocess, "run", return_value=Result()):
                result = pipeline.main([
                    "report-data.json", "--equity-evidence", "equity-evidence.json",
                    "--research-ledger", "research-ledger.json", "--policy-search-ledger", "policy-search-ledger.json",
                    "--policy-evidence", "policy-evidence.json", "--fixture-mode",
                    "--out-dir", str(Path(value) / "out"), "--node", str(node),
                ])
            self.assertEqual(result, 0)
            policy_command = next(command for command in commands if any(str(part).endswith("validate_policy_evidence.py") for part in command))
            self.assertIn("--fixture-mode", policy_command)
            self.assertTrue(any(any(str(part).endswith("validate_research_stop_gate.py") for part in command) for command in commands))
            metrics = json.loads((Path(value) / "out" / "run-metrics.json").read_text(encoding="utf-8"))
            self.assertFalse(metrics["full_release_tests_run"])
            self.assertIn("local_validation_seconds", metrics)
            self.assertIn("render_and_layout_seconds", metrics)


if __name__ == "__main__":
    unittest.main()
