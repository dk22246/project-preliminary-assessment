import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EncouragedIndustryContractTest(unittest.TestCase):
    def test_skill_has_machine_enforced_module_contract(self):
        self.assertTrue((ROOT / "scripts" / "validate_encouraged_industry_assessment.py").is_file())
        schema = json.loads((ROOT / "schemas" / "report.schema.json").read_text(encoding="utf-8"))
        self.assertIn("encouraged_industry_assessment", schema["required"])
        pipeline = (ROOT / "scripts" / "run_report_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("validate_encouraged_industry_assessment.py", pipeline)

    def test_report_template_requires_visible_three_way_judgment(self):
        template = (ROOT / "references" / "report-template.md").read_text(encoding="utf-8")
        self.assertIn("海南自由贸易港鼓励类产业目录匹配", template)
        self.assertIn("明确符合", template)
        self.assertIn("存在相近可能", template)
        self.assertIn("暂未发现明确匹配", template)

    def test_html_always_renders_the_module(self):
        renderer = (ROOT / "scripts" / "render_report_html.py").read_text(encoding="utf-8")
        self.assertIn("海南自由贸易港鼓励类产业目录匹配", renderer)
        self.assertIn("encouraged_industry_table", renderer)


if __name__ == "__main__":
    unittest.main()
