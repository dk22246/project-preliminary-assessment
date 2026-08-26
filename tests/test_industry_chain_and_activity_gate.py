import copy
import json
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import validate_report_data
from search_industry_catalog import classify_catalog_entry
from validate_encouraged_industry_assessment import validate_assessment
import render_report_html
import render_report_word


class IndustryChainAndActivityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8-sig"))
        catalog = json.loads((ROOT / "references" / "catalogs" / "complete-industry-catalog-library.json").read_text(encoding="utf-8-sig"))
        cls.catalog = {item["id"]: item for item in catalog["entries"]}

    def test_example_uses_sales_channels_and_new_industry_chain_contract(self):
        self.assertTrue(all("sales_channels" in item and "revenue_model" not in item for item in self.data["businesses"]))
        self.assertEqual(
            {"positioning", "peer_enterprises", "upstream", "downstream", "industry_common_needs"},
            set(self.data["industry_chain"]),
        )
        self.assertGreaterEqual(len(self.data["industry_chain"]["peer_enterprises"]), 3)
        self.assertGreaterEqual(len(self.data["industry_chain"]["upstream"][0]["representative_enterprises"]), 1)
        chain_text = json.dumps(self.data["industry_chain"], ensure_ascii=False)
        self.assertNotRegex(chain_text, r"第一|第二|第三|第[一二三]名|销量第一|占有率第一")

    def test_html_and_word_render_the_same_top500_and_industry_chain_semantics(self):
        self.assertTrue(hasattr(render_report_html, "top500_table"))
        self.assertTrue(hasattr(render_report_word, "top500_rows"))
        html_top500 = render_report_html.top500_table(self.data["top500_status"])
        html_chain = render_report_html.industry_chain_block(self.data["industry_chain"])
        word_top500 = render_report_word.top500_rows(self.data["top500_status"])
        word_chain = render_report_word.industry_chain_rows(self.data["industry_chain"])

        for marker in ("Fortune Global 500", "中国企业500强", "中国民营企业500强", "未入选", "E90"):
            self.assertIn(marker, html_top500)
            self.assertIn(marker, "\n".join(" | ".join(row) for row in word_top500))
        for marker in ("产业链定位", "同类型企业", "上游产业环节", "下游产业及渠道", "行业共性需求", "行业推断"):
            self.assertIn(marker, html_chain)
            self.assertIn(marker, "\n".join(" | ".join(row) for row in word_chain))
        for forbidden in ("stages", "regional_ecosystem", "招商与产业集群启示", "潜在线索", "评分"):
            self.assertNotIn(forbidden, html_chain)

        group_listed = copy.deepcopy(self.data["top500_status"])
        group_listed[0].update({"status": "group_listed", "rank": 12, "listed_entity": "示例集团", "relationship_to_target": "ultimate_group"})
        incomplete = copy.deepcopy(self.data["top500_status"])
        incomplete[1].update({"status": "research_incomplete", "reason": "官方榜单页面待复核"})
        for rendered in (render_report_html.top500_table(group_listed), "\n".join(" | ".join(row) for row in render_report_word.top500_rows(group_listed))):
            self.assertIn("第12名｜示例集团", rendered)
            self.assertIn("集团关系：研究对象的最终控制集团", rendered)
        for rendered in (render_report_html.top500_table(incomplete), "\n".join(" | ".join(row) for row in render_report_word.top500_rows(incomplete))):
            self.assertIn("核验未完成", rendered)
            self.assertIn("官方榜单页面待复核", rendered)

    def test_html_removes_risk_summary_section(self):
        renderer = (ROOT / "scripts" / "render_report_html.py").read_text(encoding="utf-8")
        word_renderer = (ROOT / "scripts" / "render_report_word.py").read_text(encoding="utf-8")
        self.assertNotIn("风险综合判断", renderer)
        self.assertNotIn('data["risks"].get("summary"', word_renderer)

    def test_renderers_do_not_restore_legacy_chain_fields_or_treat_industry_inference_as_facts(self):
        renderer = (ROOT / "scripts" / "render_report_html.py").read_text(encoding="utf-8")
        word_renderer = (ROOT / "scripts" / "render_report_word.py").read_text(encoding="utf-8")
        for source in (renderer, word_renderer):
            self.assertNotIn('chain.get("stages"', source)
            self.assertNotIn('chain.get("regional_ecosystem"', source)
            self.assertIn("行业推断", source)

    def test_missing_chain_is_rejected(self):
        data = copy.deepcopy(self.data)
        del data["industry_chain"]
        self.assertTrue(any("industry_chain" in error or "产业链" in error for error in validate_report_data(data)))

    def test_catalog_entry_classification_is_deterministic(self):
        result = classify_catalog_entry(self.catalog["industrial_restructuring_2024:36"])
        self.assertEqual("action_condition", result["classification"])
        self.assertIn("mining", result["activity_types"])
        self.assertNotIn("sales", result["activity_types"])

    def test_coal_sales_cannot_direct_match_mining_entry(self):
        data = copy.deepcopy(self.data)
        row = data["encouraged_industry_assessment"]["business_assessments"][-1]
        row.update({"activity_name": "煤炭销售", "activity_type": "sales", "activity_object": "煤炭商品", "condition_status": "met", "judgment": "direct_match"})
        row["matched_items"] = [{"catalog_entry_id": "industrial_restructuring_2024:36", "catalog_scope": "industrial_restructuring_current", "catalog_item_no": "36", "catalog_item": self.catalog["industrial_restructuring_2024:36"]["item_title"], "detailed_item": "煤矿开采及清洁利用", "match_type": "direct", "catalog_classification": "action_condition"}]
        data["encouraged_industry_assessment"]["overall_judgment"] = "direct_match"
        self.assertTrue(any("行为边界不一致" in error for error in validate_assessment(data)))


if __name__ == "__main__":
    unittest.main()
