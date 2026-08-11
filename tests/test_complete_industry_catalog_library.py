import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
CATALOG_DIR = ROOT / "references" / "catalogs"
WORKBOOK = CATALOG_DIR / "hainan-ftz-encouraged-industry-complete-library.xlsx"
LIBRARY = CATALOG_DIR / "complete-industry-catalog-library.json"


class CompleteIndustryCatalogLibraryTests(unittest.TestCase):
    def load_library(self):
        self.assertTrue(LIBRARY.is_file(), "缺少统一结构化目录库")
        return json.loads(LIBRARY.read_text(encoding="utf-8-sig"))

    def load_search_module(self):
        path = ROOT / "scripts" / "search_industry_catalog.py"
        spec = importlib.util.spec_from_file_location("search_industry_catalog", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_canonical_workbook_and_portable_build_validation_scripts_are_packaged(self):
        self.assertTrue(WORKBOOK.is_file(), "缺少新的统一主工作簿")
        self.assertTrue((ROOT / "scripts" / "build_industry_catalog_library.py").is_file())
        self.assertTrue((ROOT / "scripts" / "validate_industry_catalog_library.py").is_file())

    def test_library_preserves_all_catalog_counts_and_hainan_detail_guide(self):
        data = self.load_library()
        self.assertEqual(data["counts"]["industrial_restructuring_2024"], {
            "total": 1005,
            "encouraged": 352,
            "restricted": 231,
            "eliminated": 422,
        })
        self.assertEqual(data["counts"]["foreign_investment_national_2025"], 619)
        self.assertEqual(data["counts"]["foreign_investment_regional_2025"], 1060)
        self.assertEqual(data["counts"]["foreign_investment_hainan_2025"], 102)
        self.assertEqual(data["counts"]["hainan_added_2024"], 176)
        self.assertEqual(data["counts"]["hainan_added_guide_details"], 352)
        hainan_entries = [item for item in data["entries"] if item["catalog_scope"] == "hainan_added_2024"]
        self.assertEqual(len(hainan_entries), 176)
        self.assertTrue(all(item.get("detail_entries") for item in hainan_entries))

    def test_hainan_applicable_routes_are_subject_specific_and_do_not_double_count_views(self):
        data = self.load_library()
        self.assertEqual(len(data["routes"]["domestic_positive"]), 528)
        self.assertEqual(len(data["routes"]["foreign_positive"]), 721)
        self.assertEqual(len(data["routes"]["industrial_conflicts"]), 653)
        entries = {item["id"]: item for item in data["entries"]}
        self.assertEqual(
            {entries[item_id]["catalog_scope"] for item_id in data["routes"]["domestic_positive"]},
            {"industrial_restructuring_2024", "hainan_added_2024"},
        )
        self.assertEqual(
            {entries[item_id]["catalog_scope"] for item_id in data["routes"]["foreign_positive"]},
            {"foreign_investment_national_2025", "foreign_investment_regional_2025"},
        )
        self.assertTrue(all(entries[item_id].get("region") == "海南省" for item_id in data["routes"]["foreign_positive"] if entries[item_id]["catalog_scope"] == "foreign_investment_regional_2025"))

    def test_search_routes_by_subject_and_surfaces_negative_conflicts_separately(self):
        module = self.load_search_module()
        domestic = module.search(["电子商务"], subject_type="domestic", limit=30)
        self.assertTrue(any(item["catalog_scope"] == "hainan_added_2024" for item in domestic["candidates"]))
        self.assertFalse(any(item["catalog_scope"].startswith("foreign_investment") for item in domestic["candidates"]))
        foreign = module.search(["农作物"], subject_type="foreign", limit=30)
        self.assertTrue(any(item["catalog_scope"] == "foreign_investment_national_2025" for item in foreign["candidates"]))
        data = self.load_library()
        entries = {item["id"]: item for item in data["entries"]}
        conflict = entries[data["routes"]["industrial_conflicts"][0]]
        checked = module.search([conflict["item_title"]], subject_type="domestic", limit=30, include_conflicts=True)
        self.assertTrue(any(item["policy_category"] in {"restricted", "eliminated"} for item in checked["conflicts"]))

    def test_skill_and_preflight_require_the_complete_library(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        preflight = (ROOT / "scripts" / "preflight.py").read_text(encoding="utf-8")
        contract = (ROOT / "references" / "module-contract.json").read_text(encoding="utf-8")
        for marker in (
            "hainan-ftz-encouraged-industry-complete-library.xlsx",
            "complete-industry-catalog-library.json",
            "validate_industry_catalog_library.py",
        ):
            self.assertIn(marker, skill + preflight + contract)
        self.assertIn("限制类、淘汰类", skill)
        self.assertIn("外商投资企业", skill)


if __name__ == "__main__":
    unittest.main()
