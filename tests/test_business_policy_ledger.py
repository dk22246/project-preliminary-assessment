import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import validate_business_policy_ledger


FLYCO = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8"))


def valid_data():
    data = copy.deepcopy(FLYCO)
    for index, item in enumerate(data["landing_businesses"], 1):
        item["id"] = f"L{index:02d}"
    for policy in data["policies"]:
        policy.update(
            {
                "issuer": "海南省有关主管部门",
                "document_number": "示例文号",
                "published_at": "2025-01-24",
                "validity_evidence": "官方文件明确现行适用。",
                "applicable_object": "满足条件的海南自由贸易港经营主体或人才",
                "policy_value": "提供税收优惠或跨境资金结算便利。",
                "handling_route": "按主管部门或经办银行要求办理。",
            }
        )
    policy_urls = {policy["source_id"]: policy["source_url"] for policy in data["policies"]}
    for source in data["sources"]:
        if source.get("id") in policy_urls:
            source["location"] = policy_urls[source["id"]]
    data["policy_research"] = [
        {
            "landing_business_id": "L01",
            "topic": "总部认定、企业所得税及人才个人所得税",
            "searched_departments": ["三亚市投资促进局", "国家税务总局海南省税务局"],
            "outcome": "conditional_opportunity",
            "conclusion": "总部团队实质迁入后可进一步核验相关政策条件。",
            "next_evidence": "需确认管理人员、合同、收入和利润迁入规模。",
            "evidence_source_ids": ["P01", "P03"],
            "policy_ids": ["P01", "P03"],
        },
        {
            "landing_business_id": "L02",
            "topic": "企业所得税15%及数字贸易支持",
            "searched_departments": ["海南省商务厅", "国家税务总局海南省税务局"],
            "outcome": "conditional_opportunity",
            "conclusion": "需先核验鼓励类目录对应业务和主营收入占比。",
            "next_evidence": "需确认业务目录归类、收入及实质运营。",
            "evidence_source_ids": ["P01"],
            "policy_ids": ["P01"],
        },
        {
            "landing_business_id": "L03",
            "topic": "EF账户、跨境人民币、外汇便利及离岸贸易印花税",
            "searched_departments": ["中国人民银行海南省分行", "国家外汇管理局海南省分局"],
            "outcome": "conditional_opportunity",
            "conclusion": "真实跨境贸易和结算进入三亚主体后可申请相应便利。",
            "next_evidence": "需确认跨境合同、收付款、贸易模式及离岸转手买卖事实。",
            "evidence_source_ids": ["P06"],
            "policy_ids": ["P06"],
        },
        {
            "landing_business_id": "L04",
            "topic": "ODI及新增境外直接投资所得优惠",
            "searched_departments": ["海南省商务厅", "国家外汇管理局海南省分局"],
            "outcome": "not_triggered",
            "conclusion": "现有公开信息不足以确认新增ODI项目和境外投资所得，暂不写作可享受权益。",
            "next_evidence": "需企业提供拟投国别、主体、项目、金额和收益安排。",
            "evidence_source_ids": ["P01"],
            "policy_ids": [],
        },
    ]
    return data


class BusinessPolicyLedgerTests(unittest.TestCase):
    def test_requires_a_research_result_for_every_landing_business(self):
        data = valid_data()
        data["policy_research"].pop()
        errors = validate_business_policy_ledger(data)
        self.assertIn("海外市场投资与运营支持: 缺少政策检索结论", errors)

    def test_requires_evidence_for_each_linked_formal_policy(self):
        data = valid_data()
        data["policies"][0].pop("document_number")
        errors = validate_business_policy_ledger(data)
        self.assertIn("海南自由贸易港鼓励类产业企业所得税15%优惠: 缺少文号", errors)

    def test_requires_an_official_evidence_source_for_a_negative_conclusion(self):
        data = valid_data()
        data["policy_research"][-1].pop("evidence_source_ids")
        errors = validate_business_policy_ledger(data)
        self.assertIn("L04 / ODI及新增境外直接投资所得优惠: 缺少检索依据来源", errors)

    def test_accepts_all_outcomes_when_each_business_is_accounted_for(self):
        self.assertEqual(validate_business_policy_ledger(valid_data()), [])

    def test_html_renderer_prioritizes_grouped_policies_under_the_landing_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "render_report_html.py"), str(ROOT / "examples" / "flyco-report-data.json"), "--out", str(output)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            html = output.read_text(encoding="utf-8")
            policy_section = html.split('<section id="s六"', 1)[1].split("</section>", 1)[0]
            self.assertIn("重点政策匹配清单", policy_section)
            self.assertIn("整体落地情景", policy_section)
            self.assertIn("实际税负15%封顶", policy_section)
            self.assertIn("EF账户（多功能自由贸易账户）", policy_section)
            self.assertNotIn("待核政策事项", policy_section)
            self.assertNotIn("海南省财政厅等五部门关于落实", policy_section)
            table_body = policy_section.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
            self.assertEqual(table_body.count("<tr>"), 4)
            self.assertIn("官方原文", html)

    def test_pdf_renderer_uses_only_one_page_number_mechanism(self):
        source = (ROOT / "scripts" / "render_report_pdf.mjs").read_text(encoding="utf-8")
        self.assertIn("displayHeaderFooter: false", source)

    def test_equity_relationship_labels_have_an_opaque_halo(self):
        from report_core import equity_svg

        svg = equity_svg(FLYCO["equity"])
        self.assertIn("paint-order:stroke", svg)

    def test_word_renderer_uses_the_same_policy_match_table_without_pending_table(self):
        source = (ROOT / "scripts" / "render_report_word.py").read_text(encoding="utf-8")
        self.assertIn("重点政策匹配清单", source)
        self.assertNotIn("待核政策事项", source)
        self.assertIn("企业能获得什么", source)


if __name__ == "__main__":
    unittest.main()
