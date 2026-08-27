import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import validate_report_data


REPORT = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8-sig"))
TOP500_SOURCES = [
    {"id": "E90", "type": "官方榜单", "name": "Fortune Global 500 2026", "issuer": "Fortune", "date": "2026-08-01", "location": "https://fortune.com/ranking/global500/2026/", "used_in": "企业基本情况/500强核验"},
    {"id": "E91", "type": "权威转载榜单", "name": "2025中国企业500强", "issuer": "央视新闻客户端", "date": "2025-09-15", "location": "https://news.cnr.cn/native/gd/kx/20250915/t20250915_527362516.shtml", "used_in": "企业基本情况/500强核验"},
    {"id": "E92", "type": "官方榜单", "name": "2025中国民营企业500强", "issuer": "中华全国工商业联合会", "date": "2025-08-28", "location": "https://www.acfic.org.cn/qlyw/202508/t20250827_319997.html", "used_in": "企业基本情况/500强核验"},
]


def report_with_top500_contract() -> dict:
    data = copy.deepcopy(REPORT)
    data["sources"].extend(copy.deepcopy(TOP500_SOURCES))
    data["top500_status"] = [
        {"year": 2026, "ranking_name": "fortune_global_500", "ranking_label": "Fortune Global 500", "status": "not_listed", "rank": None, "listed_entity": None, "relationship_to_target": "not_applicable", "relationship_source_ids": [], "relationship_evidence": None, "reason": None, "source_ids": ["E90"]},
        {"year": 2025, "ranking_name": "china_enterprise_500", "ranking_label": "中国企业500强", "status": "not_listed", "rank": None, "listed_entity": None, "relationship_to_target": "not_applicable", "relationship_source_ids": [], "relationship_evidence": None, "reason": None, "source_ids": ["E91"]},
        {"year": 2025, "ranking_name": "china_private_enterprise_500", "ranking_label": "中国民营企业500强", "status": "not_listed", "rank": None, "listed_entity": None, "relationship_to_target": "not_applicable", "relationship_source_ids": [], "relationship_evidence": None, "reason": None, "source_ids": ["E92"]},
    ]
    return data


def representative(name: str) -> dict:
    return {"name": name, "source_ids": ["E01"]}


def report_with_full_new_contract() -> dict:
    data = report_with_top500_contract()
    data["industry_chain"] = {
        "positioning": {"summary": "研究对象位于个人护理电器的品牌、产品与制造组织环节。"},
        "peer_enterprises": [
            {"name": name, "core_business": "个人护理电器", "scale_or_position": "行业代表样本", "similarity_dimensions": ["产品品类", "品牌渠道"], "similarity": "同属个人护理电器品牌制造环节。", "reason": "用于横向比较，不代表交易关系。", "source_ids": ["E01"]}
            for name in ("飞利浦", "博朗", "松下")
        ],
        "upstream": [
            {"activity": activity, "function": "提供行业通用投入。", "representative_enterprises": [representative(company)], "relationship_scope": "行业代表样本，不代表已确认供应商。"}
            for activity, company in (("微型电机", "万宝至马达"), ("电子控制", "日本电产"), ("消费电池", "鹏辉能源"))
        ],
        "downstream": [
            {"activity": activity, "function": "提供零售触达和消费者服务。", "representative_enterprises": [representative(company)], "relationship_scope": "行业代表样本，不代表已确认客户或合作伙伴。"}
            for activity, company in (("综合电商", "淘宝天猫"), ("自营零售", "京东"), ("社交电商", "拼多多"))
        ],
        "industry_common_needs": [
            {"need": need, "status": "industry_inference", "basis": "基于行业环节概括，不是研究对象已发生的企业事实。", "source_ids": ["E01"]}
            for need in ("供应链协同", "产品研发", "渠道运营")
        ],
    }
    return data


class Top500AndSupplyChainContractTests(unittest.TestCase):
    def assert_contract_error(self, data: dict, marker: str) -> None:
        errors = validate_report_data(data)
        self.assertTrue(any(marker in error for error in errors), errors)

    def test_valid_new_contract_is_accepted(self):
        self.assertFalse(validate_report_data(report_with_full_new_contract()))

    def test_top500_status_rejects_missing_required_ranking(self):
        data = report_with_top500_contract()
        data["top500_status"].pop()
        self.assert_contract_error(data, "top500_status")

    def test_top500_status_rejects_duplicate_ranking(self):
        data = report_with_top500_contract()
        data["top500_status"][-1]["ranking_name"] = "china_enterprise_500"
        self.assert_contract_error(data, "top500_status")

    def test_top500_status_rejects_extra_ranking(self):
        data = report_with_top500_contract()
        data["top500_status"].append({"year": 2025, "ranking_name": "regional_top_500", "status": "not_listed", "relationship_to_target": "not_applicable", "source_ids": ["E90"]})
        self.assert_contract_error(data, "top500_status")

    def test_top500_status_rejects_illegal_status(self):
        data = report_with_top500_contract()
        data["top500_status"][0]["status"] = "unknown"
        self.assert_contract_error(data, "status")

    def test_listed_requires_year_entity_same_entity_relationship_and_official_source(self):
        data = report_with_top500_contract()
        listed = data["top500_status"][1]
        listed["status"] = "listed"
        listed["listed_entity"] = "假想入选企业"
        listed.pop("year")
        listed.pop("listed_entity")
        listed["relationship_to_target"] = "parent_group"
        listed["source_ids"] = ["E01"]
        self.assert_contract_error(data, "listed")

    def test_group_listed_requires_entity_group_relationship_and_official_source(self):
        data = report_with_top500_contract()
        listed = data["top500_status"][2]
        listed["status"] = "group_listed"
        listed["listed_entity"] = "假想入选集团"
        listed.pop("listed_entity")
        listed["relationship_to_target"] = "same_entity"
        listed["source_ids"] = ["E01"]
        self.assert_contract_error(data, "group_listed")

    def test_not_listed_requires_latest_official_ranking_source(self):
        data = report_with_top500_contract()
        data["top500_status"][0]["source_ids"] = ["E01"]
        self.assert_contract_error(data, "not_listed")

    def test_research_incomplete_requires_year_reason_and_official_source(self):
        data = report_with_top500_contract()
        item = data["top500_status"][0]
        item["status"] = "research_incomplete"
        item.pop("year")
        item["source_ids"] = []
        self.assert_contract_error(data, "research_incomplete")

    def test_not_listed_rejects_rank_or_listed_entity(self):
        data = report_with_top500_contract()
        data["top500_status"][0]["rank"] = 499
        data["top500_status"][0]["listed_entity"] = "错误夹带实体"
        self.assert_contract_error(data, "名次和入选实体必须为空")

    def test_group_listed_requires_relationship_evidence(self):
        data = report_with_top500_contract()
        item = data["top500_status"][0]
        item.update({"status": "group_listed", "rank": 100, "listed_entity": "示例集团", "relationship_to_target": "parent_group"})
        self.assert_contract_error(data, "集团关系")

    def test_group_relationship_rejects_unrelated_e_source(self):
        data = report_with_top500_contract()
        item = data["top500_status"][0]
        target = data["entity_resolution"]["analysis_entity"]
        item.update({"status": "group_listed", "rank": 100, "listed_entity": "示例集团", "relationship_to_target": "parent_group", "relationship_source_ids": ["E01"], "relationship_evidence": {"claim": f"{target}由示例集团控制", "as_of_date": "2026-08-27", "source_ids": ["E01"]}})
        self.assert_contract_error(data, "未声明用于股权")

    def test_relationship_to_target_rejects_unknown_enum(self):
        data = report_with_top500_contract()
        data["top500_status"][2]["relationship_to_target"] = "affiliate"
        self.assert_contract_error(data, "relationship_to_target")

    def test_industry_chain_requires_all_five_sections(self):
        data = report_with_full_new_contract()
        data["industry_chain"].pop("industry_common_needs")
        self.assert_contract_error(data, "industry_common_needs")

    def test_positioning_requires_summary(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["positioning"] = {}
        self.assert_contract_error(data, "positioning.summary")

    def test_peer_enterprises_rejects_fewer_than_three(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["peer_enterprises"] = data["industry_chain"]["peer_enterprises"][:2]
        self.assert_contract_error(data, "peer_enterprises")

    def test_peer_enterprises_rejects_more_than_six(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["peer_enterprises"].extend(copy.deepcopy(data["industry_chain"]["peer_enterprises"][:1]) * 4)
        self.assert_contract_error(data, "peer_enterprises")

    def test_upstream_rejects_fewer_than_three(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["upstream"] = data["industry_chain"]["upstream"][:2]
        self.assert_contract_error(data, "industry_chain.upstream")

    def test_upstream_rejects_more_than_six(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["upstream"].extend(copy.deepcopy(data["industry_chain"]["upstream"][:1]) * 4)
        self.assert_contract_error(data, "industry_chain.upstream")

    def test_downstream_rejects_fewer_than_three(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["downstream"] = data["industry_chain"]["downstream"][:2]
        self.assert_contract_error(data, "industry_chain.downstream")

    def test_downstream_rejects_more_than_six(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["downstream"].extend(copy.deepcopy(data["industry_chain"]["downstream"][:1]) * 4)
        self.assert_contract_error(data, "industry_chain.downstream")

    def test_upstream_rejects_duplicate_activities(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["upstream"][1]["activity"] = data["industry_chain"]["upstream"][0]["activity"]
        self.assert_contract_error(data, "重复activity")

    def test_industry_common_needs_rejects_fewer_than_three(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["industry_common_needs"] = data["industry_chain"]["industry_common_needs"][:2]
        self.assert_contract_error(data, "industry_common_needs")

    def test_industry_common_needs_rejects_more_than_six(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["industry_common_needs"].extend(copy.deepcopy(data["industry_chain"]["industry_common_needs"][:1]) * 4)
        self.assert_contract_error(data, "industry_common_needs")

    def test_industry_common_needs_rejects_duplicate_needs(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["industry_common_needs"][1]["need"] = data["industry_chain"]["industry_common_needs"][0]["need"]
        self.assert_contract_error(data, "重复need")

    def test_policy_radar_requires_enterprise_fact_basis(self):
        data = report_with_full_new_contract()
        data["policy_opportunity_radar"]["signals"][0].pop("basis_type")
        self.assert_contract_error(data, "basis_type")

    def test_policy_radar_rejects_inference_disguised_without_enterprise_fact_ref(self):
        data = report_with_full_new_contract()
        data["policy_opportunity_radar"]["signals"][0]["enterprise_fact_refs"] = ["N01"]
        self.assert_contract_error(data, "不得以行业共性需求替代")

    def test_transaction_evidence_rejects_unrelated_e_source(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["upstream"][0]["relationship_scope"] = "已确认供应商"
        data["industry_chain"]["upstream"][0]["transaction_evidence"] = {"relationship": "供应商", "evidence_text": "声称存在供应关系", "as_of_date": "2026-08-27", "source_ids": ["E03"]}
        self.assert_contract_error(data, "未声明用于直接交易关系核验")

    def test_peer_enterprise_requires_two_similarity_dimensions(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["peer_enterprises"][0]["similarity_dimensions"] = ["产品品类"]
        self.assert_contract_error(data, "similarity_dimensions")

    def test_peer_enterprise_requires_all_descriptive_fields(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["peer_enterprises"][0].pop("reason")
        self.assert_contract_error(data, "peer_enterprises")

    def test_peer_enterprise_requires_evidence_source_ids(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["peer_enterprises"][0]["source_ids"] = []
        self.assert_contract_error(data, "peer_enterprises")

    def test_upstream_item_requires_activity_function_representatives_and_scope(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["upstream"][0].pop("function")
        self.assert_contract_error(data, "industry_chain.upstream")

    def test_downstream_item_requires_activity_function_representatives_and_scope(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["downstream"][0].pop("relationship_scope")
        self.assert_contract_error(data, "industry_chain.downstream")

    def test_upstream_representative_enterprise_requires_object_name_and_source(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["upstream"][0]["representative_enterprises"][0] = {"name": "万宝至马达", "source_ids": []}
        self.assert_contract_error(data, "representative_enterprises")

    def test_downstream_representative_enterprise_requires_object_name_and_source(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["downstream"][0]["representative_enterprises"][0] = "淘宝天猫"
        self.assert_contract_error(data, "representative_enterprises")

    def test_upstream_without_transaction_evidence_cannot_claim_supplier(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["upstream"][0]["relationship_scope"] = "研究对象供应商样本"
        self.assert_contract_error(data, "直接交易证据")

    def test_downstream_without_transaction_evidence_cannot_claim_customer(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["downstream"][0]["relationship_scope"] = "研究对象客户样本"
        self.assert_contract_error(data, "直接交易证据")

    def test_downstream_without_transaction_evidence_cannot_claim_partner(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["downstream"][0]["relationship_scope"] = "研究对象合作伙伴样本"
        self.assert_contract_error(data, "直接交易证据")

    def test_industry_chain_rejects_cluster_implications(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["cluster_implications"] = "不应恢复的集群结论"
        self.assert_contract_error(data, "cluster_implications")

    def test_industry_chain_rejects_investment_lead(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["investment_lead"] = "不应恢复的招商线索"
        self.assert_contract_error(data, "investment_lead")

    def test_industry_common_need_requires_industry_inference_status(self):
        data = report_with_full_new_contract()
        data["industry_chain"]["industry_common_needs"][0]["status"] = "enterprise_fact"
        self.assert_contract_error(data, "industry_inference")

    def test_industry_common_need_cannot_trigger_policy_radar_as_enterprise_fact(self):
        data = report_with_full_new_contract()
        data["policy_opportunity_radar"]["signals"].append({
            "id": "S-industry-inference",
            "signal_type": "industry_common_need",
            "fact": "行业共性需求触发确定政策。",
            "source_ids": ["E01"],
            "opportunities": [{"topic": "supply_chain", "disposition": "surfaced", "reason": "不应将行业推断作为企业事实。", "policy_source_ids": [data["policies"][0]["source_id"]]}],
        })
        self.assert_contract_error(data, "industry_common_needs")


if __name__ == "__main__":
    unittest.main()
