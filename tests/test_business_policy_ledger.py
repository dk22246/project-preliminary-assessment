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

    def test_accepts_not_applicable_as_distinct_from_not_triggered(self):
        data = valid_data()
        data["policy_research"][-1]["outcome"] = "not_applicable"
        data["policy_research"][-1]["conclusion"] = "已核验现有主体不符合该政策的适用条件。"
        self.assertEqual(validate_business_policy_ledger(data), [])

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
            policy_section = html.split('<section id="s五"', 1)[1].split("</section>", 1)[0]
            self.assertIn("重点政策匹配清单", policy_section)
            self.assertIn("相邻经营活动", policy_section)
            self.assertIn("<th>匹配政策或工具</th><th>匹配原因</th>", policy_section)
            self.assertIn("实际税负15%封顶", policy_section)
            self.assertIn("EF账户（多功能自由贸易账户）", policy_section)
            self.assertIn("ODI境外投资备案与外汇登记", policy_section)
            self.assertIn("新增境外直接投资所得企业所得税免征", policy_section)
            self.assertNotIn("待核政策事项", policy_section)
            self.assertNotIn("海南省财政厅等五部门关于落实", policy_section)
            table_body = policy_section.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
            expected_groups = {item.get("report_group") or item["source_id"] for item in FLYCO["policies"]}
            self.assertEqual(table_body.count("<tr>"), len(expected_groups))
            self.assertIn("官方原文", html)

    def test_pdf_renderer_uses_only_one_page_number_mechanism(self):
        source = (ROOT / "scripts" / "render_report_pdf.mjs").read_text(encoding="utf-8")
        self.assertIn("displayHeaderFooter: false", source)

    def test_equity_relationship_labels_have_an_opaque_halo(self):
        from report_core import equity_svg

        svg = equity_svg(FLYCO["equity"])
        self.assertIn("paint-order:stroke", svg)

    def test_equity_svg_wraps_long_node_text_and_deduplicates_shared_relationship_labels(self):
        from report_core import equity_svg

        equity = {
            "nodes": [
                {"id": "parent", "name": "Logitech International S.A.", "entity_type": "上市公司", "role": "分析主体／集团控制平台", "level": 0},
                {"id": "eu", "name": "Logitech Europe S.A.", "entity_type": "合并子公司", "role": "欧洲及集团知识产权相关经营", "level": 1},
                {"id": "us", "name": "Logitech Inc.", "entity_type": "合并子公司", "role": "美国经营主体", "level": 1},
                {"id": "cn", "name": "中国经营主体（3家）", "entity_type": "合并子公司组", "role": "中国销售、咨询与苏州制造", "level": 1},
            ],
            "edges": [
                {"from": "parent", "to": "eu", "relationship": "合并控制；比例未披露"},
                {"from": "parent", "to": "us", "relationship": "合并控制；比例未披露"},
                {"from": "parent", "to": "cn", "relationship": "合并控制；比例未披露"},
            ],
        }

        svg = equity_svg(equity)
        self.assertIn('width="100%"', svg)
        self.assertIn('viewBox="0 0 640 ', svg)
        self.assertIn("<tspan", svg)
        self.assertEqual(svg.count("合并控制；比例未披露"), 1)
        self.assertNotRegex(svg, r"<tspan[^>]*>[^<]{1}</tspan>")

    def test_browser_layout_gate_checks_equity_svg_bounds(self):
        source = (ROOT / "scripts" / "verify_html_layout.mjs").read_text(encoding="utf-8")
        self.assertIn("股权图元素越出 SVG 画布", source)

    def test_browser_layout_gate_covers_every_report_table_and_page_width(self):
        source = (ROOT / "scripts" / "verify_html_layout.mjs").read_text(encoding="utf-8")
        self.assertIn('document.querySelectorAll(".report-table")', source)
        self.assertIn("页面出现横向越界", source)

    def test_report_pipeline_runs_layout_gate_before_any_optional_conversion(self):
        source = (ROOT / "scripts" / "run_report_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('"verify_html_layout.mjs"', source)
        self.assertIn("HTML 版式验收失败", source)

    def test_html_table_renderer_rejects_rows_with_more_or_fewer_cells_than_headers(self):
        from render_report_html import report_table

        with self.assertRaisesRegex(ValueError, "列数"):
            report_table(["时间", "事项类型", "来源编号"], [["FY2026", "诉讼", "持续", "R02"]])

    def test_word_renderer_uses_the_same_policy_match_table_without_pending_table(self):
        source = (ROOT / "scripts" / "render_report_word.py").read_text(encoding="utf-8")
        self.assertIn("重点政策匹配清单", source)
        self.assertNotIn("待核政策事项", source)
        self.assertIn("匹配政策或工具", source)
        self.assertIn("匹配原因", source)


if __name__ == "__main__":
    unittest.main()
