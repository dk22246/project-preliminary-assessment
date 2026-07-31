import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import load_data
from validate_research_ledger import validate_research_ledger


REPORT = load_data(ROOT / "examples" / "flyco-report-data.json")


def valid_ledger():
    return {
        "enterprise": "上海飞科电器股份有限公司",
        "fact_ledger": [
            {"id": "FA01", "source_id": "E01", "action": "管理", "object": "品牌与区域经营", "enterprise_role": "运营者", "confidence": "high"},
            {"id": "FA02", "source_id": "E02", "action": "运营", "object": "自营电商", "enterprise_role": "运营者", "confidence": "high"},
            {"id": "FA03", "source_id": "E03", "action": "结算", "object": "供应链贸易", "enterprise_role": "运营者", "confidence": "high"},
            {"id": "FA04", "source_id": "E04", "action": "投资", "object": "海外市场", "enterprise_role": "管理者", "confidence": "high"},
        ],
        "business_candidates": [
            {"id": "BC01", "name": "总部与品牌运营", "fact_ids": ["FA01"], "disposition": "include", "disposition_target": "L01", "disposition_reason": "可由三亚主体承接"},
            {"id": "BC02", "name": "自营电商与数字营销", "fact_ids": ["FA02"], "disposition": "include", "disposition_target": "L02", "disposition_reason": "可由三亚主体承接"},
            {"id": "BC03", "name": "供应链贸易与结算", "fact_ids": ["FA03"], "disposition": "include", "disposition_target": "L03", "disposition_reason": "可由三亚主体承接"},
            {"id": "BC04", "name": "海外投资运营支持", "fact_ids": ["FA04"], "disposition": "include", "disposition_target": "L04", "disposition_reason": "可由三亚主体承接"},
        ],
        "department_routes": [
            {"id": "DR01", "landing_business_id": "L01", "candidate_ids": ["BC01"], "matter": "总部及经营管理", "route_rule_id": "headquarters_management", "department": "三亚市投资促进局", "route_type": "matched_static_rule", "status": "matched_static_rule"},
            {"id": "DR02", "landing_business_id": "L02", "candidate_ids": ["BC02"], "matter": "数字商业运营", "route_rule_id": "digital_commerce_operation", "department": "海南省商务厅", "route_type": "matched_static_rule", "status": "matched_static_rule"},
            {"id": "DR03", "landing_business_id": "L03", "candidate_ids": ["BC03"], "matter": "跨境贸易与结算", "route_rule_id": "cross_border_trade", "department": "中国人民银行海南省分行", "route_type": "matched_static_rule", "status": "matched_static_rule"},
            {"id": "DR04", "landing_business_id": "L04", "candidate_ids": ["BC04"], "matter": "境外投资管理", "route_rule_id": "overseas_investment", "department": "海南省商务厅", "route_type": "matched_static_rule", "status": "matched_static_rule"},
        ],
        "policy_candidates": [
            {"id": "PC01", "route_id": "DR01", "policy_name": "税收与人才政策", "status": "current_conditional", "disposition": "include", "formal_policy_source_ids": ["P01", "P03", "P04"]},
            {"id": "PC02", "route_id": "DR02", "policy_name": "数字商业税收政策", "status": "current_conditional", "disposition": "include", "formal_policy_source_ids": ["P01"]},
            {"id": "PC03", "route_id": "DR03", "policy_name": "跨境资金与贸易便利", "status": "current_conditional", "disposition": "include", "formal_policy_source_ids": ["P06", "P07"]},
            {"id": "PC04", "route_id": "DR04", "policy_name": "境外投资政策检索", "status": "not_applicable", "disposition": "exclude", "disposition_reason": "本轮公开资料未确认新增投资项目", "formal_policy_source_ids": []},
        ],
    }


class ResearchLedgerTests(unittest.TestCase):
    def test_accepts_a_complete_traceable_ledger(self):
        self.assertEqual(validate_research_ledger(valid_ledger(), REPORT), [])

    def test_rejects_candidate_without_disposition(self):
        ledger = valid_ledger()
        ledger["business_candidates"][0]["disposition"] = ""
        errors = validate_research_ledger(ledger, REPORT)
        self.assertTrue(any("BC01: 候选处置只能为" in error for error in errors))

    def test_rejects_fact_without_traceable_source(self):
        ledger = valid_ledger()
        ledger["fact_ledger"][0].pop("source_id")
        errors = validate_research_ledger(ledger, REPORT)
        self.assertTrue(any("FA01: 缺少source_id" in error for error in errors))

    def test_rejects_landing_business_without_department_route(self):
        ledger = valid_ledger()
        ledger["department_routes"].pop()
        errors = validate_research_ledger(ledger, REPORT)
        self.assertTrue(any("L04: 缺少主管部门路由" in error for error in errors))

    def test_rejects_expired_candidate_used_by_formal_policy(self):
        ledger = valid_ledger()
        ledger["policy_candidates"][1]["status"] = "expired_relevant"
        errors = validate_research_ledger(ledger, REPORT)
        self.assertTrue(any("PC02: 非现行候选政策不得支撑正式报告政策" in error for error in errors))

    def test_rejects_confirmed_department_without_policy_candidate_record(self):
        ledger = valid_ledger()
        ledger["policy_candidates"] = [item for item in ledger["policy_candidates"] if item["route_id"] != "DR02"]
        errors = validate_research_ledger(ledger, REPORT)
        self.assertTrue(any("DR02: 缺少候选政策或无政策检索记录" in error for error in errors))

    def test_static_sports_route_can_route_unknown_event_business_without_industry_patch(self):
        ledger = valid_ledger()
        ledger["fact_ledger"].append({"id": "FA05", "source_id": "E05", "action": "主办赛事", "object": "嘉年华", "enterprise_role": "运营者", "confidence": "high"})
        ledger["business_candidates"].append({"id": "BC05", "name": "赛事活动运营", "fact_ids": ["FA05"], "disposition": "merge", "disposition_target": "L02", "disposition_reason": "并入品牌及数字运营"})
        ledger["department_routes"].append({"id": "DR05", "landing_business_id": "L02", "candidate_ids": ["BC05"], "matter": "体育赛事组织与运营", "route_rule_id": "sports_event_operation", "department": "三亚市旅游和文化广电体育局", "route_type": "matched_static_rule", "status": "matched_static_rule"})
        ledger["policy_candidates"].append({"id": "PC05", "route_id": "DR05", "policy_name": "体育赛事政策目录检索", "status": "no_current_policy", "disposition": "exclude", "disposition_reason": "示例仅验证路由，尚未纳入现行政策", "formal_policy_source_ids": []})
        report = copy.deepcopy(REPORT)
        next(item for item in report["policy_research"] if item["landing_business_id"] == "L02")["searched_departments"].append("三亚市旅游和文化广电体育局")
        self.assertEqual(validate_research_ledger(ledger, report), [])


if __name__ == "__main__":
    unittest.main()
