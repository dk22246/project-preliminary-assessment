from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class PolicyRoleScanCompilerTests(unittest.TestCase):
    def test_role_paths_cannot_regress_to_mechanical_seven_path_scan(self):
        from policy_roles import required_paths_for_role

        self.assertEqual(required_paths_for_role("co_issuer"), (
            "theme_search", "department_documents", "normative_documents", "invalidity_catalog",
        ))
        self.assertNotIn("award_publicity", required_paths_for_role("execution_authority"))
        self.assertNotIn("document_graph", required_paths_for_role("primary_regulator"))
        self.assertEqual(len(required_paths_for_role("funding_authority")), 6)

    def test_registry_supplies_missing_department_entry_and_profile_is_shared(self):
        from discover_current_policies import discover_current_policies

        research = {
            "enterprise": "测试企业",
            "fact_ledger": [{"id": "F01"}],
            "business_candidates": [
                {"id": "BC01", "fact_ids": ["F01"]},
                {"id": "BC02", "fact_ids": ["F01"]},
            ],
            "department_routes": [
                {"id": "DR01", "landing_business_id": "L01", "candidate_ids": ["BC01"], "department": "海南省商务厅", "department_role": "primary_regulator"},
                {"id": "DR02", "landing_business_id": "L02", "candidate_ids": ["BC02"], "department": "海南省商务厅", "department_role": "primary_regulator"},
            ],
        }
        report = {"landing_businesses": [{"id": "L01", "business": "贸易"}, {"id": "L02", "business": "跨境电商"}]}
        calls = []

        def fetch(url, headers):
            calls.append(url)
            return {"status": 200, "final_url": url, "body": b"official", "headers": {"Content-Type": "text/html"}}

        with tempfile.TemporaryDirectory() as directory:
            result = discover_current_policies(research, report, Path(directory), fetch=fetch)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result["policy_search_ledger"]["department_scan_profiles"]), 1)
        self.assertEqual(len(result["policy_search_ledger"]["searches"]), 2)
        self.assertEqual(result["policy_search_ledger"]["searches"][0]["fact_ids"], ["F01"])


if __name__ == "__main__":
    unittest.main()
