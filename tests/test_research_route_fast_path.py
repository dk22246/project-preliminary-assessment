from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ResearchRouteFastPathTests(unittest.TestCase):
    def test_listed_route_has_one_concentrated_disclosure_pass(self):
        from research_plan import build_research_plan

        plan = build_research_plan({
            "enterprise": "测试上市公司",
            "research": {"enterprise_profile": {"listing_status": "listed", "research_route": "listed_disclosure"}},
        })
        self.assertEqual([row["action"] for row in plan["actions"]], [
            "latest_annual_report", "historical_gap_fill", "company_current_delta", "regulatory_risk_delta",
        ])
        self.assertEqual(plan["actions"][1]["mode"], "only_if_gap")
        self.assertNotIn("media_search", {row["action"] for row in plan["actions"]})
        self.assertEqual(plan["execution"]["max_research_rounds"], 1)
        self.assertEqual(plan["execution"]["collection_mode"], "batch_parallel")

    def test_nonlisted_route_never_creates_exchange_or_annual_report_action(self):
        from research_plan import build_research_plan

        plan = build_research_plan({
            "enterprise": "测试非上市公司",
            "research": {"enterprise_profile": {"listing_status": "nonlisted", "research_route": "nonlisted_public_evidence"}},
        })
        actions = {row["action"] for row in plan["actions"]}
        self.assertEqual(actions, {
            "company_self_statement", "government_operating_records", "counterparty_disclosure",
            "business_registry", "risk_records", "targeted_gap_check",
        })
        self.assertFalse(any(row["channel"] == "exchange_disclosure" for row in plan["actions"]))
        self.assertEqual(plan["execution"]["max_research_rounds"], 2)
        self.assertEqual(plan["execution"]["collection_mode"], "batch_parallel")

    def test_mismatched_listing_route_is_rejected(self):
        from research_plan import build_research_plan

        with self.assertRaisesRegex(ValueError, "listing_status"):
            build_research_plan({
                "enterprise": "错误主体",
                "research": {"enterprise_profile": {"listing_status": "nonlisted", "research_route": "listed_disclosure"}},
            })


if __name__ == "__main__":
    unittest.main()
