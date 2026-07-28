import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKFLOW_FILES = (ROOT / "SKILL.md", ROOT / "references" / "policy-scope.md", ROOT / "references" / "report-template.md", ROOT / "references" / "word-delivery.md")


class BusinessTriggeredPolicyLogicTests(unittest.TestCase):
    def test_no_fixed_policy_coverage_gate(self):
        for path in WORKFLOW_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("validate_policy_coverage.py", text, path)
            self.assertNotIn("coverage.json", text, path)
            self.assertNotIn("\u653f\u7b56\u8986\u76d6\u53f0\u8d26", text, path)

    def test_business_must_precede_policy_search(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        scope = (ROOT / "references" / "policy-scope.md").read_text(encoding="utf-8")
        self.assertIn("\u4e0d\u5f97\u7531\u653f\u7b56\u53cd\u5411\u865a\u6784\u4e1a\u52a1", skill)
        self.assertIn("\u6bcf\u9879\u62df\u843d\u5730\u4e1a\u52a1", scope)

    def test_eight_sections_and_data_delivery(self):
        template = (ROOT / "references" / "report-template.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        for numeral in "\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b":
            self.assertIn(f"## {numeral}\u3001", template)
        self.assertIn("report-data.json", skill)
        self.assertIn("HTML", skill)
        self.assertIn("PDF", skill)

    def test_template_has_required_business_policy_and_source_tables(self):
        template = (ROOT / "references" / "report-template.md").read_text(encoding="utf-8")
        for phrase in ("\u80a1\u6743\u67b6\u6784\u62c6\u89e3", "\u5efa\u8bae\u843d\u5730\u4e1a\u52a1", "\u91cd\u70b9\u653f\u7b56", "\u4f01\u4e1a\u80fd\u83b7\u5f97\u4ec0\u4e48", "\u53c2\u8003\u8d44\u6599"):
            self.assertIn(phrase, template)

    def test_html_delivery_is_template_driven(self):
        renderer = (ROOT / "scripts" / "render_report_html.py").read_text(encoding="utf-8")
        guidance = (ROOT / "references" / "html-templates.md").read_text(encoding="utf-8")
        self.assertIn("html_template", renderer)
        self.assertIn("sanya-cbd-editorial", renderer)
        self.assertIn("prefers-reduced-motion", renderer)
        self.assertIn("模板只改变视觉变量和组件", guidance)

    def test_html_is_default_and_conversions_are_opt_in(self):
        pipeline = (ROOT / "scripts" / "run_report_pipeline.py").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        agent_metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        word_rules = (ROOT / "references" / "word-delivery.md").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--pdf", action="store_true"', pipeline)
        self.assertIn('parser.add_argument("--word", action="store_true"', pipeline)
        self.assertIn("if args.pdf:", pipeline)
        self.assertIn("if args.word:", pipeline)
        self.assertIn("默认只生成", skill)
        self.assertIn("verified HTML report", agent_metadata)
        self.assertNotIn("deliver a verified Word report", agent_metadata)
        self.assertIn("默认只交付 HTML", word_rules)


if __name__ == "__main__":
    unittest.main()
