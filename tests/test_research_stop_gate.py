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
            ],
        },
        "business_candidates": [
            {"id": "BC01", "disposition": "include", "disposition_reason": "已有事实基础"},
            {"id": "BC02", "disposition": "exclude", "disposition_reason": "不适合三亚承接"},
        ],
    }


def complete_nonlisted_checks():
    no_record = "本轮官方公开检索未发现相关记录"
    return {
        "business_evidence": {
            "company_self_statement": {"status": "completed", "source_ids": ["E01"]},
            "government_operating_records": {"status": "completed", "source_ids": ["E02"]},
            "counterparty_disclosure": {"status": "not_available", "reason": "本轮未发现客户或合作方正式公告"},
        },
        "financial_boundary": {
            "status": "not_public",
            "proxy_inference_used": False,
            "operating_evidence_source_ids": ["E02"],
            "reason": "本轮公开检索未发现可靠数据，需企业补充",
        },
        "industry_500": {
            "status": "not_listed",
            "report_statement": "本轮未发现可核验的行业500强入选记录",
            "reason": "本轮未发现可核验的行业500强入选记录",
        },
        "government_support": {
            "status": "not_found",
            "reason": "本轮公开检索未发现可确认的政府补助或政策支持记录",
        },
        "risk_checks": {
            "administrative_and_abnormal": {"status": "not_available", "reason": no_record},
            "tax_violations": {"status": "not_available", "reason": no_record},
            "litigation_and_enforcement": {"status": "not_available", "reason": no_record},
            "dishonesty_and_credit": {"status": "not_available", "reason": no_record},
        },
    }


def make_nonlisted(ledger):
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
    ledger["research_stop_gate"]["nonlisted_evidence_checks"] = complete_nonlisted_checks()
    return ledger


class ResearchStopGateTests(unittest.TestCase):
    def test_listed_route_accepts_one_concentrated_disclosure_round(self):
        ledger = complete_ledger()
        ledger["research_stop_gate"]["discovery_rounds"] = [
            {"round": 1, "high_value_candidate_ids": ["BC01"]},
        ]
        self.assertEqual(validate_research_stop_gate(ledger), [])

    def test_nonlisted_route_accepts_one_targeted_gap_round(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["discovery_rounds"] = [
            {"round": 1, "high_value_candidate_ids": []},
        ]
        self.assertEqual(validate_research_stop_gate(ledger), [])

    def test_nonlisted_route_requires_at_least_one_targeted_gap_round(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["discovery_rounds"] = []
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("一次定向补查" in item for item in errors), errors)

    def test_listed_route_rejects_repeated_research_rounds(self):
        self.assertIsNotNone(validate_research_stop_gate, "validate_research_stop_gate.py must provide validate_research_stop_gate")
        ledger = complete_ledger()
        ledger["research_stop_gate"]["discovery_rounds"].extend([
            {"round": 2, "high_value_candidate_ids": []},
            {"round": 3, "high_value_candidate_ids": []},
        ])
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("上市公司只能执行一轮集中研究" in item for item in errors), errors)

    def test_nonlisted_route_rejects_more_than_fixed_ladder_and_one_gap_round(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["discovery_rounds"] = [
            {"round": "fixed_source_ladder", "high_value_candidate_ids": []},
            {"round": "targeted_gap_check", "high_value_candidate_ids": []},
            {"round": "repeated_search", "high_value_candidate_ids": []},
        ]
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("非上市公司最多执行固定来源阶梯和一次定向补查" in item for item in errors), errors)

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
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["required_topics"]["three_year_financials"] = {
            "status": "not_available",
            "reason": "本轮公开检索未发现可靠数据，需企业补充",
        }
        self.assertEqual(validate_research_stop_gate(ledger), [])

    def test_nonlisted_route_cannot_skip_business_registry_channel(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["source_channels"] = {
            "company_official": {"status": "completed", "source_ids": ["E01"]},
            "government_regulatory": {"status": "completed", "source_ids": ["E02"]},
            "risk_records": {"status": "completed", "source_ids": ["R01"]},
        }
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("business_registry" in item for item in errors), errors)

    def test_nonlisted_route_requires_the_fixed_evidence_contract(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"].pop("nonlisted_evidence_checks")
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("nonlisted_evidence_checks" in item for item in errors), errors)

    def test_nonlisted_route_rejects_financial_proxy_inference(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["nonlisted_evidence_checks"]["financial_boundary"]["proxy_inference_used"] = True
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("proxy_inference_used" in item for item in errors), errors)

    def test_nonlisted_industry_500_hit_requires_exact_ranking_fields(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["nonlisted_evidence_checks"]["industry_500"] = {
            "status": "listed",
            "report_statement": "入选某行业500强",
        }
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("industry_500命中时缺少" in item for item in errors), errors)

    def test_nonlisted_support_rejects_application_as_confirmed_support(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["nonlisted_evidence_checks"]["government_support"] = {
            "status": "confirmed",
            "items": [{"name": "某专项资金申报", "evidence_type": "application", "source_ids": ["E02"]}],
        }
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("证据类型不属于正式支持凭证" in item for item in errors), errors)

    def test_nonlisted_route_requires_all_four_official_risk_checks(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["nonlisted_evidence_checks"]["risk_checks"].pop("tax_violations")
        errors = validate_research_stop_gate(ledger)
        self.assertTrue(any("risk_checks.tax_violations" in item for item in errors), errors)

    def test_nonlisted_report_must_surface_industry_and_risk_boundaries(self):
        ledger = make_nonlisted(complete_ledger())
        report = {
            "industry_position": {"statement": "本轮未发现可核验的行业500强入选记录", "evidence_status": "not_public"},
            "government_support": [],
            "risks": {"summary": "本轮官方公开检索未发现相关记录"},
        }
        self.assertEqual(validate_research_stop_gate(ledger, report), [])
        report["industry_position"]["statement"] = "公开资料不足"
        errors = validate_research_stop_gate(ledger, report)
        self.assertTrue(any("行业500强结论未写入" in item for item in errors), errors)

    def test_nonlisted_report_cannot_replace_industry_500_with_market_share(self):
        ledger = make_nonlisted(complete_ledger())
        report = {
            "industry_position": {
                "statement": "本轮未发现可核验的行业500强入选记录",
                "evidence_status": "market_share",
            },
            "government_support": [],
            "risks": {"summary": "本轮官方公开检索未发现相关记录"},
        }
        errors = validate_research_stop_gate(ledger, report)
        self.assertTrue(any("evidence_status必须为not_public" in item for item in errors), errors)

    def test_confirmed_nonlisted_support_must_reach_existing_report_table(self):
        ledger = make_nonlisted(complete_ledger())
        ledger["research_stop_gate"]["nonlisted_evidence_checks"]["government_support"] = {
            "status": "confirmed",
            "items": [{
                "name": "产业发展专项资金",
                "evidence_type": "government_award_notice",
                "source_ids": ["E02"],
            }],
        }
        report = {
            "industry_position": {"statement": "本轮未发现可核验的行业500强入选记录", "evidence_status": "not_public"},
            "government_support": [],
            "risks": {"summary": "本轮官方公开检索未发现相关记录"},
        }
        errors = validate_research_stop_gate(ledger, report)
        self.assertTrue(any("产业发展专项资金" in item for item in errors), errors)
        report["government_support"] = [{"name": "产业发展专项资金"}]
        self.assertEqual(validate_research_stop_gate(ledger, report), [])


if __name__ == "__main__":
    unittest.main()
