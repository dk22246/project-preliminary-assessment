import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import validate_report_data


REPORT = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8"))


class ReportStructureSimplificationTests(unittest.TestCase):
    def render_html(self) -> str:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(ROOT / "scripts" / "render_report_html.py"),
                    str(ROOT / "examples" / "flyco-report-data.json"),
                    "--out",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return output.read_text(encoding="utf-8")

    def test_report_starts_with_enterprise_basics_and_has_no_overall_judgment_section(self):
        html = self.render_html()
        self.assertNotIn("项目整体判断", html)
        first_report_section = html.split('<section id="s一"', 1)[1].split("</section>", 1)[0]
        self.assertIn("一、企业基本情况", first_report_section)

    def test_business_table_has_only_five_enterprise_fact_columns(self):
        html = self.render_html()
        business_part = html.split("（三）主要业务及产品拆解", 1)[1].split("</table>", 1)[0]
        self.assertEqual(business_part.count("<th>"), 5)
        self.assertNotIn("与三亚的潜在结合点", business_part)
        self.assertNotIn("sanya_fit", json.dumps(REPORT, ensure_ascii=False))

    def test_enterprise_basics_use_a_small_table_plus_profile_text(self):
        html = self.render_html()
        basics = html.split('<section id="s一"', 1)[1].split("</section>", 1)[0]
        profile = REPORT["enterprise_overview"]
        for marker in ("企业概况", "成立时间", "注册地", "主营业务", "员工规模", profile["employee_scale"]):
            self.assertIn(marker, basics)
        self.assertIn(REPORT["industry_position"]["position"], basics)

    def test_deprecated_overall_judgment_and_sanya_fit_are_rejected(self):
        data = copy.deepcopy(REPORT)
        data["overall_judgment"] = [["招商建议", "重点推进"]]
        data["businesses"][0]["sanya_fit"] = "旧字段"
        errors = validate_report_data(data)
        self.assertTrue(any("overall_judgment" in error for error in errors), errors)
        self.assertTrue(any("sanya_fit" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
