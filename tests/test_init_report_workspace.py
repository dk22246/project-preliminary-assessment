from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "init_report_workspace.py"
FILES = {
    "report-data.json",
    "equity-evidence.json",
    "research-ledger.json",
    "policy-search-ledger.json",
    "policy-evidence.json",
}


class InitReportWorkspaceTests(unittest.TestCase):
    def run_init(self, enterprise: str, out_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), enterprise, "--out-dir", str(out_dir), *extra],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_creates_five_parseable_blank_ledgers_without_fixture_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "catl"
            result = self.run_init("宁德时代新能源科技股份有限公司", out)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual({path.name for path in out.iterdir()}, FILES)
            combined = ""
            for name in FILES:
                payload = json.loads((out / name).read_text(encoding="utf-8"))
                combined += json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("飞科", combined)
            self.assertNotIn("剃须刀", combined)
            self.assertNotIn("示例：已完成", combined)

    def test_blank_report_cannot_pass_formal_report_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "blank"
            self.assertEqual(self.run_init("测试企业", out).returncode, 0)
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "validate_report_data.py"), str(out / "report-data.json")],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_refuses_existing_directory_and_force_only_accepts_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty"
            empty.mkdir()
            self.assertNotEqual(self.run_init("测试企业", empty).returncode, 0)
            self.assertEqual(self.run_init("测试企业", empty, "--force").returncode, 0)
            self.assertNotEqual(self.run_init("测试企业", empty, "--force").returncode, 0)

    def test_formal_validator_rejects_packaged_fixture_without_explicit_mode(self):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "validate_report_data.py"), str(ROOT / "examples" / "flyco-report-data.json")],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        allowed = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "validate_report_data.py"), str(ROOT / "examples" / "flyco-report-data.json"), "--fixture-mode"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)


if __name__ == "__main__":
    unittest.main()
