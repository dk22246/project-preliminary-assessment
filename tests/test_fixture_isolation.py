import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import render_report_word


ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_FIXTURE = ROOT / "tests" / "fixtures" / "release" / "synthetic-report-data.json"


class FixtureIsolationTests(unittest.TestCase):
    def test_public_html_renderer_rejects_fixture_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "render_report_html.py"), str(SYNTHETIC_FIXTURE), "--out", str(output)],
                text=True,
                capture_output=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture", (result.stdout + result.stderr).lower())

    def test_public_word_renderer_rejects_fixture_data(self):
        # A valid tiny PNG ensures a failure comes from the fixture gate rather
        # than the renderer's separate equity-image requirement.
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z4dAAAAAASUVORK5CYII="
        )
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "equity.png"
            output = Path(directory) / "report.docx"
            image.write_bytes(png)
            argv = [
                "render_report_word.py",
                str(SYNTHETIC_FIXTURE),
                "--out",
                str(output),
                "--equity-image",
                str(image),
            ]
            with patch.object(sys, "argv", argv), patch.object(render_report_word, "try_update_fields_with_word"):
                with self.assertRaisesRegex(SystemExit, "fixture"):
                    render_report_word.main()

    def test_release_fixture_is_synthetic_and_not_packaged_as_an_example(self):
        examples = ROOT / "examples"
        self.assertFalse(examples.exists() and any(path.is_file() for path in examples.rglob("*")))
        self.assertTrue(SYNTHETIC_FIXTURE.is_file())
        payload = json.loads(SYNTHETIC_FIXTURE.read_text(encoding="utf-8"))
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertTrue(payload.get("fixture_metadata", {}).get("fixture_only"))
        self.assertIn("自动化测试", serialized)
        self.assertEqual(payload["meta"]["reporting_entity"], "示例测试企业股份有限公司")
        self.assertTrue(payload["meta"]["report_title"].startswith("【自动化测试夹具·禁止交付】"))


if __name__ == "__main__":
    unittest.main()
