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


class IndustryChainAndActivityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8-sig"))
        catalog = json.loads((ROOT / "references" / "catalogs" / "complete-industry-catalog-library.json").read_text(encoding="utf-8-sig"))
        cls.catalog = {item["id"]: item for item in catalog["entries"]}

    def test_example_uses_sales_channels_and_structured_chain(self):
        self.assertFalse(validate_report_data(self.data))
        self.assertTrue(all("sales_channels" in item and "revenue_model" not in item for item in self.data["businesses"]))
        self.assertEqual(["upstream", "midstream", "downstream"], [item["stage"] for item in self.data["industry_chain"]["stages"]])

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
