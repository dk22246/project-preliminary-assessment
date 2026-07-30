import codecs
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from report_core import load_data


class DeploymentPreflightTests(unittest.TestCase):
    def test_report_data_loader_accepts_utf8_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "bom.json"
            target.write_bytes(codecs.BOM_UTF8 + b'{"name":"\xe5\x8d\x97\xe5\xad\x9a"}')
            self.assertEqual(load_data(target)["name"], "南孚")

    def test_preflight_validates_packaging_without_rendering(self):
        result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "preflight.py")], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("文本均为UTF-8", result.stdout)

    def test_preflight_validates_web_evidence_sample(self):
        result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "preflight.py")], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("网页证据台账有效", result.stdout)

    def test_windows_utf8_launcher_sets_console_and_python_encoding(self):
        launcher = (ROOT / "scripts" / "run_utf8.ps1").read_text(encoding="utf-8")
        self.assertIn("[Console]::OutputEncoding", launcher)
        self.assertIn('$env:PYTHONUTF8 = "1"', launcher)
        self.assertIn("-X utf8 @PythonArgs", launcher)
        self.assertIn("SKILL_PYTHON", launcher)
        self.assertIn("py -ErrorAction", launcher)


if __name__ == "__main__":
    unittest.main()
