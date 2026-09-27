from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class FindingsContractTests(unittest.TestCase):
    def test_report_container_types_survive_enterprise_compile(self):
        from tempfile import TemporaryDirectory
        from compile_workspace import compile_enterprise_findings

        chain = {"positioning": {"summary": "制冷设备制造"}, "peer_enterprises": [], "upstream": [], "downstream": [], "industry_common_needs": []}
        rankings = [{"ranking_name": "fortune_global_500", "status": "research_incomplete"}]
        enterprise = {
            "version": "1.0", "enterprise": "珠海格力电器股份有限公司",
            "report": {"industry_chain": chain, "top500_status": rankings},
            "research": {}, "equity": {"nodes": [], "edges": []}, "sources": [],
        }
        with TemporaryDirectory() as directory:
            compiled = compile_enterprise_findings(enterprise, Path(directory))
        self.assertEqual(compiled["report-data.json"]["industry_chain"], chain)
        self.assertEqual(compiled["report-data.json"]["top500_status"], rankings)

    def test_rejects_reversed_report_container_types(self):
        from findings_contract import validate_enterprise_findings

        enterprise = {
            "version": "1.0", "enterprise": "甲",
            "report": {"industry_chain": [], "top500_status": {}},
            "research": {}, "equity": {"nodes": [], "edges": []}, "sources": [],
        }
        errors = validate_enterprise_findings(enterprise)
        self.assertTrue(any("industry_chain" in error and "类型错误" in error for error in errors))
        self.assertTrue(any("top500_status" in error and "类型错误" in error for error in errors))

    def test_reports_independent_key_ref_and_assertion_errors_together(self):
        from findings_contract import validate_findings_contracts

        enterprise = {
            "version": "1.0", "enterprise": "甲", "report": {"businesses": [], "landing_businesses": []},
            "research": {"facts": [], "business_candidates": [], "department_routes": []},
            "sources": [], "equity": {"nodes": [{"key": "n1", "name": "甲", "assertion_type": "bad", "source_keys": ["missing"]}], "edges": [{"key": "e1", "from_key": "missing", "to_key": "n1", "assertion_type": "registry_fact", "source_keys": []}]},
        }
        policy = {
            "version": "1.0", "enterprise": "甲", "sources": [], "evidence": [],
            "policy_records": [{"key": "p1", "source_keys": ["unknown-source"], "search_keys": ["unknown-search"], "fact_keys": [], "landing_business_keys": [], "topic": "税收", "match_reason": "事实", "eligibility_status": "unknown", "disposition": "conditional", "conditions": "待核", "handling_route": "待核", "report_group": "g", "policy": {}}],
            "search": {"searches": []},
        }
        errors = validate_findings_contracts(enterprise, policy)
        self.assertGreaterEqual(len(errors), 3)
        self.assertTrue(any("断言类型" in error for error in errors))
        self.assertTrue(any("未知source" in error for error in errors))
        self.assertTrue(any("未知search" in error for error in errors))

    def test_discovery_drafts_have_keys_without_becoming_policy_records(self):
        from findings_contract import validate_policy_findings

        policy = {
            "version": "1.0", "enterprise": "甲", "researched_at": "",
            "policy_records": [], "sources": [{"key": "s1", "type": "official", "name": "原文"}],
            "evidence": [{"key": "ev1", "policy_source_key": "s1", "sha256": "abc", "captured_at": "2026-01-01T00:00:00+00:00"}],
            "search": {"department_scan_profiles": [{"key": "profile1", "runs": [{"result_source_keys": ["s1"], "evidence_record_keys": ["ev1"]}]}], "searches": [{"key": "search1", "profile_key": "profile1"}], "discovered_candidates": [{"key": "draft1", "title": "草稿"}], "failures": [], "decode_warnings": []},
        }
        self.assertEqual(validate_policy_findings(policy), [])
        self.assertEqual(policy["policy_records"], [])

    def test_catalog_detail_choice_and_equity_percentage_are_validated_before_compile(self):
        from findings_contract import validate_enterprise_findings

        enterprise = {
            "version": "1.0", "enterprise": "甲", "sources": [{"key": "s1", "type": "annual_report", "name": "年报"}],
            "report": {"encouraged_industry_assessment": {"business_assessments": [{"business_id": "b1", "matched_items": [{"catalog_entry_id": "hainan_added_2024:1"}]}]}},
            "research": {},
            "equity": {"nodes": [
                {"key": "holder", "name": "股东", "entity_type": "企业", "assertion_type": "registry_fact", "as_of_date": "2025-12-31", "source_keys": ["s1"]},
                {"key": "subject", "name": "甲", "entity_type": "企业", "assertion_type": "registry_fact", "as_of_date": "2025-12-31", "source_keys": ["s1"]},
            ], "edges": [{"key": "owns", "from_key": "holder", "to_key": "subject", "relationship": "持股", "ownership_percent": 120, "assertion_type": "provider_calculation", "as_of_date": "2025-12-31", "source_keys": ["s1"]}]},
        }
        errors = validate_enterprise_findings(enterprise)
        self.assertTrue(any("business_assessments[0].matched_items[0].detail_index" in error for error in errors), errors)
        self.assertTrue(any("ownership_percent" in error and "100" in error for error in errors), errors)
        self.assertTrue(any("calculation_basis" in error for error in errors), errors)

    def test_reports_unambiguous_fact_source_and_equity_report_fields_before_prepare(self):
        from findings_contract import validate_enterprise_findings

        enterprise = {
            "version": "1.0", "enterprise": "甲", "sources": [
                {"key": "annual", "type": "annual_report", "name": "年报"},
                {"key": "notice", "type": "official_notice", "name": "公告"},
            ],
            "report": {},
            "research": {"facts": [{"key": "overseas", "source_keys": ["annual", "notice"], "action": "销售", "object": "产品", "enterprise_role": "出口方", "confidence": "high"}]},
            "equity": {"data_status": "available", "nodes": [{"key": "subject", "name": "甲", "entity_type": "企业", "assertion_type": "registry_fact", "as_of_date": "2025-12-31", "source_keys": ["annual"]}], "edges": []},
        }
        errors = validate_enterprise_findings(enterprise)
        self.assertTrue(any("恰好一项" in error and "source_id" in error for error in errors), errors)
        self.assertTrue(any("缺少role" in error for error in errors), errors)
        self.assertTrue(any("evidence_summary.display_source_key" in error for error in errors), errors)
        self.assertTrue(any("evidence_summary.as_of_date" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
