import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKFLOW_FILES = (
    ROOT / "SKILL.md",
    ROOT / "references" / "policy-scope.md",
    ROOT / "references" / "report-template.md",
    ROOT / "references" / "word-delivery.md",
)


class BusinessTriggeredPolicyLogicTests(unittest.TestCase):
    def test_active_workflow_has_no_fixed_coverage_gate(self):
        for path in WORKFLOW_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("validate_policy_coverage.py", text, path)
            self.assertNotIn("coverage.json", text, path)
            self.assertNotIn("政策覆盖台账", text, path)
            self.assertNotIn("政策覆盖审查表", text, path)

    def test_active_workflow_requires_business_to_policy_mapping(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        scope = (ROOT / "references" / "policy-scope.md").read_text(encoding="utf-8")
        template = (ROOT / "references" / "report-template.md").read_text(encoding="utf-8")
        self.assertIn("拟落地业务", skill)
        self.assertIn("不得因海南存在某项政策而反向虚构业务", skill)
        self.assertIn("每项拟落地业务", scope)
        self.assertIn("建议落地业务 | 企业现有事实基础 | 三亚具体承接方式", template)

    def test_report_uses_required_eight_part_structure(self):
        template = (ROOT / "references" / "report-template.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = (
            "一、项目整体判断",
            "二、企业基本情况",
            "三、近三年经营数据",
            "四、风险与合规情况",
            "五、三亚落地业务及落地方式",
            "六、企业政策匹配",
            "七、综合评估",
            "八、参考资料",
        )
        for heading in required:
            self.assertIn(heading, template)
        self.assertIn("八部分固定目录", skill)
        self.assertIn("不得自行调整章节结构", skill)

    def test_report_requires_toc_sources_and_personal_income_tax_check(self):
        template = (ROOT / "references" / "report-template.md").read_text(encoding="utf-8")
        delivery = (ROOT / "references" / "word-delivery.md").read_text(encoding="utf-8")
        self.assertIn("高端和紧缺人才个人所得税15%", template)
        self.assertIn("| 研判事项 | 初步结论 |", template)
        self.assertIn("| 建议落地业务 | 企业现有事实基础 | 三亚具体承接方式 | 可形成的业务及价值 | 可行性 |", template)
        self.assertIn("| 对接业务 | 政策名称 | 政策一句话说明 | 企业匹配逻辑 | 核心条件或办理方式 | 当前判断 | 来源编号 |", template)
        self.assertIn("| 编号 | 资料类型", template)
        self.assertIn("自动目录", delivery)
        self.assertIn("一级标题统一使用“一、二、三……”", delivery)
        self.assertIn("跨页表格必须重复显示表头", delivery)
        self.assertIn("页脚显示连续页码", delivery)


if __name__ == "__main__":
    unittest.main()
