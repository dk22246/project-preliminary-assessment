import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from validate_research_stop_gate import validate_research_stop_gate
except ModuleNotFoundError:
    validate_research_stop_gate = None


def complete_ledger():
    return {
        "enterprise_profile": {
            "analysis_entity": "上海飞科电器股份有限公司",
            "listing_status": "listed",
            "research_route": "listed_disclosure",
            "basis_source_ids": ["E01"],
        },
        "research_stop_gate": {
            "source_channels": {
                "exchange_disclosure": {"status": "completed", "source_ids": ["E01"]},
                "company_official": {"status": "completed", "source_ids": ["E02"]},
                "government_regulatory": {"status": "completed", "source_ids": ["E03"]},
            },
            "required_topics": {
                "entity": {"status": "completed", "source_ids": ["E01"]},
                "core_business": {"status": "completed", "source_ids": ["E01"]},
                "industry_position": {"status": "not_available", "reason": "公开资料未披露统一排名口径"},
                "domestic_overseas": {"status": "completed", "source_ids": ["E02"]},
                "three_year_financials": {"status": "completed", "source_ids": ["E03"]},
                "equity": {"status": "completed", "source_ids": ["E04"]},
                "risk": {"status": "inaccessible", "reason": "官方查询系统本轮维护"},
            },
            "discovery_rounds": [
                {"round": 1, "high_value_candidate_ids": ["BC01"]},
                {"round": 2, "high_value_candidate_ids": []},
                {"round": 3, "high_value_candidate_ids": []},
            ],
        },
        "business_candidates": [
            {"id": "BC01", "disposition": "include", "disposition_reason": "已有事实基础"},
            {"id": "BC02", "disposition": "exclude", "disposition_reason": "不适合三亚承接"},
        ],
    }


class ResearchStopGateTests(unittest.TestCase):
    def test_complete_dispositions_and_two_empty_rounds_allow_policy_phase(self):
        self.assertIsNotNone(validate_research_stop_gate, "validate_research_stop_gate.py must provide validate_research_stop_gate")
        self.assertEqual(validate_research_stop_gate(complete_ledger()), [])

    def test_missing_required_topic_blocks_stop_gate_and_requires_enterprise_supplement(self):
        self.assertIsNotNone(validate_research_stop_gate, "validate_research_stop_gate.py must provide validate_research_stop_gate")
        ledger = complete_ledger()
        ledger["research_stop_gate"]["required_topics"].pop("three_year_financials")
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("three_year_financials" in item and "需企业补充" in item for item in errors))

    def test_unresolved_business_candidate_blocks_stop_gate(self):
        self.assertIsNotNone(validate_research_stop_gate, "validate_research_stop_gate.py must provide validate_research_stop_gate")
        ledger = copy.deepcopy(complete_ledger())
        ledger["business_candidates"][0]["disposition"] = "pending"
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("BC01" in item and "处置" in item for item in errors))

    def test_missing_disclosure_route_blocks_policy_phase(self):
        ledger = complete_ledger()
        ledger.pop("enterprise_profile")
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("enterprise_profile" in item for item in errors), errors)

    def test_nonlisted_route_accepts_explicitly_unavailable_financials(self):
        ledger = complete_ledger()
        ledger["enterprise_profile"] = {
            "analysis_entity": "非上市测试企业有限公司",
            "listing_status": "nonlisted",
            "research_route": "nonlisted_public_evidence",
            "basis_source_ids": ["E01"],
        }
        ledger["research_stop_gate"]["source_channels"] = {
            "company_official": {"status": "completed", "source_ids": ["E01"]},
            "government_regulatory": {"status": "completed", "source_ids": ["E02"]},
            "business_registry": {"status": "completed", "source_ids": ["E03"]},
            "risk_records": {"status": "completed", "source_ids": ["R01"]},
        }
        ledger["research_stop_gate"]["required_topics"]["three_year_financials"] = {
            "status": "not_available",
            "reason": "本轮公开检索未发现可靠数据，需企业补充",
        }
        self.assertEqual(validate_research_stop_gate(ledger), [])

    def test_nonlisted_route_cannot_skip_business_registry_channel(self):
        ledger = complete_ledger()
        ledger["enterprise_profile"] = {
            "analysis_entity": "非上市测试企业有限公司",
            "listing_status": "nonlisted",
            "research_route": "nonlisted_public_evidence",
            "basis_source_ids": ["E01"],
        }
        ledger["research_stop_gate"]["source_channels"] = {
            "company_official": {"status": "completed", "source_ids": ["E01"]},
            "government_regulatory": {"status": "completed", "source_ids": ["E02"]},
            "risk_records": {"status": "completed", "source_ids": ["R01"]},
        }
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("business_registry" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
