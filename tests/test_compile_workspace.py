from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class CompileWorkspaceTests(unittest.TestCase):
    def test_policy_candidates_are_route_complete_and_use_validator_statuses(self):
        import compile_workspace

        records = [{
            "search_ids": ["PS01"],
            "topic": "企业所得税15%优惠",
            "eligibility_status": "unknown",
            "disposition": "conditional",
            "match_reason": "落地主体满足条件后可申请",
            "source_ids": ["P01"],
            "policy": {"name": "企业所得税15%优惠", "status": "current", "attachment_status": "complete"},
        }]
        candidates = compile_workspace._derive_policy_candidates(
            records,
            {"PS01": {"route_ids": ["DR01", "DR02"]}},
        )

        self.assertEqual([item["route_id"] for item in candidates], ["DR01", "DR02"])
        self.assertTrue(all(item["status"] == "current_conditional" for item in candidates))
        self.assertTrue(all(item["disposition"] == "include" for item in candidates))
        self.assertTrue(all(item["formal_policy_source_ids"] == ["P01"] for item in candidates))

    def test_policy_compile_copies_candidates_to_research_and_search_ledgers(self):
        import compile_workspace

        findings = {
            "enterprise": "测试企业有限公司",
            "researched_at": "2026-09-26T10:00:00+08:00",
            "sources": [{"key": "policy", "type": "official_policy", "name": "政策原文"}],
            "evidence": [],
            "search": {
                "landing_business_hypotheses": [],
                "department_scan_profiles": [],
                "searches": [{"key": "search", "landing_business_key": "landing", "route_keys": ["route"], "fact_keys": ["fact"], "topic": "企业所得税15%优惠"}],
            },
            "policy_records": [{
                "key": "record", "source_keys": ["policy"], "search_keys": ["search"],
                "fact_keys": ["fact"], "landing_business_keys": ["landing"],
                "topic": "企业所得税15%优惠", "match_reason": "满足条件后可申请",
                "eligibility_status": "unknown", "disposition": "conditional", "conditions": "待核",
                "handling_route": "税务办理", "report_group": "企业所得税",
                "policy": {"name": "企业所得税15%优惠", "status": "current", "attachment_status": "complete"},
            }],
        }
        report = {"meta": {"reporting_entity": "测试企业有限公司"}, "sources": [], "landing_businesses": [{"id": "L01"}]}
        research = {"fact_ledger": [{"id": "F01"}], "business_candidates": [], "department_routes": [{"id": "DR01"}]}
        result = compile_workspace.compile_policy_findings(
            findings, Path("."), report, research,
            {"landing_business": {"landing": "L01"}, "fact": {"fact": "F01"}, "route": {"route": "DR01"}, "source": {}},
        )

        self.assertEqual(research["policy_candidates"][0]["route_id"], "DR01")
        self.assertEqual(result["policy-search-ledger.json"]["searches"][0]["candidate_policy_ids"], ["PC01"])
        self.assertEqual(result["report-data.json"]["policy_research"][0]["outcome"], "conditional_opportunity")

    def test_enterprise_compile_normalizes_legacy_routing_rule_alias(self):
        import compile_workspace

        findings = {
            "version": "1.0",
            "enterprise": "测试企业有限公司",
            "sources": [{"key": "annual", "type": "annual_report", "name": "年度报告"}],
            "report": {
                "entity_resolution": {"legal_entity": "测试企业有限公司", "analysis_entity": "测试企业有限公司"},
                "enterprise_overview": {"source_keys": ["annual"]},
                "landing_businesses": [{
                    "key": "landing", "business": "贸易结算", "fact_basis": "已有海外销售",
                    "sanya_path": "设立贸易结算主体", "value": "形成贸易和结算贡献",
                    "feasibility": "待核", "policy_departments": ["海南省商务厅"],
                }],
            },
            "research": {
                "enterprise_profile": {"analysis_entity": "测试企业有限公司", "basis_source_keys": ["annual"]},
                "facts": [],
                "business_candidates": [{"key": "candidate", "name": "贸易结算"}],
                "department_routes": [{
                    "key": "route",
                    "landing_business_key": "landing",
                    "candidate_keys": ["candidate"],
                    "department": "海南省商务厅",
                    "status": "matched_static_rule",
                    "routing_rule_id": "cross_border_trade",
                }],
            },
            "equity": {"nodes": [], "edges": []},
        }
        compiled = compile_workspace.compile_enterprise_findings(findings, Path("."))["research-ledger.json"]
        route = compiled["department_routes"][0]
        self.assertEqual(route["route_rule_id"], "cross_border_trade")
        self.assertNotIn("routing_rule_id", route)

    def test_enterprise_compile_normalizes_risk_list_for_all_renderers(self):
        import compile_workspace

        risks = [
            {"title": "行政监管待核", "description": "本轮未取得完整查询结果", "source_ids": ["E01"]},
            {"category": "重大诉讼", "description": "涉及金额待核", "source_ids": ["E02"]},
        ]
        compiled = compile_workspace._compile_risks(risks)
        self.assertEqual(len(compiled["regulatory"]), 1)
        self.assertEqual(compiled["regulatory"][0][1], "行政监管待核")
        self.assertEqual(len(compiled["litigation"]), 1)
        self.assertEqual(compiled["litigation"][0][1], "重大诉讼")

    def test_policy_sources_avoid_all_enterprise_p_ids(self):
        import compile_workspace
        import init_report_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enterprise = "测试企业有限公司"
            for name, payload in {**init_report_workspace.build_payloads(enterprise), **init_report_workspace.build_findings(enterprise)}.items():
                (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            findings = init_report_workspace.build_findings(enterprise)["enterprise-findings.json"]
            findings["sources"] = [
                {"key": "catalog", "type": "industry_catalog", "name": "官方目录"},
                {"key": "annual", "type": "annual_report", "name": "年报"},
            ]
            findings["report"] = {
                "entity_resolution": {"legal_entity": enterprise, "analysis_entity": enterprise},
                "enterprise_overview": {"source_keys": ["catalog", "annual"]},
            }
            (root / "enterprise-findings.json").write_text(json.dumps(findings, ensure_ascii=False), encoding="utf-8")
            policy = init_report_workspace.build_findings(enterprise)["policy-findings.json"]
            policy["researched_at"] = "2026-09-15T10:00:00+08:00"
            policy["sources"] = [
                {"key": "p1", "type": "policy", "name": "政策一"},
                {"key": "p2", "type": "policy", "name": "政策二"},
            ]
            (root / "policy-findings.json").write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
            compiled = compile_workspace.compile_workspace(root)
            ids = [item["id"] for item in compiled["report-data.json"]["sources"]]
            self.assertEqual(ids, ["P01", "E01", "P02", "P03"])

    def test_canonical_equity_graph_derives_matching_views(self):
        import compile_workspace
        import init_report_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enterprise = "测试企业有限公司"
            for name, payload in {**init_report_workspace.build_payloads(enterprise), **init_report_workspace.build_findings(enterprise)}.items():
                (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            findings = init_report_workspace.build_findings(enterprise)["enterprise-findings.json"]
            findings["sources"] = [{"key": "official", "type": "legal_disclosure", "name": "法定披露"}]
            findings["equity"] = {
                "data_status": "available",
                "review_status": "complete",
                "evidence_summary": {"display_source_key": "official", "as_of_date": "2025-12-31"},
                "nodes": [
                    {"key": "subject", "name": enterprise, "entity_type": "法律主体", "role": "被投企业", "assertion_type": "legal_disclosure", "as_of_date": "2025-12-31", "source_keys": ["official"]},
                    {"key": "holder", "name": "股东甲", "entity_type": "股东", "role": "直接股东", "assertion_type": "registry_fact", "as_of_date": "2025-12-31", "source_keys": ["official"]},
                ],
                "edges": [{"key": "holder-owns", "from_key": "holder", "to_key": "subject", "relationship": "持股16.11%", "ownership_percent": 16.11, "assertion_type": "registry_fact", "as_of_date": "2025-12-31", "source_keys": ["official"]}],
            }
            (root / "enterprise-findings.json").write_text(json.dumps(findings, ensure_ascii=False), encoding="utf-8")
            report = compile_workspace.compile_enterprise_findings(findings, root)["report-data.json"]
            evidence = compile_workspace.compile_enterprise_findings(findings, root)["equity-evidence.json"]
            self.assertEqual([node["id"] for node in report["equity"]["nodes"]], [node["id"] for node in evidence["nodes"]])
            self.assertNotIn("key", report["equity"]["nodes"][0])
            self.assertNotIn("edge_key_map", evidence)
            self.assertEqual(report["equity"]["edges"][0]["from"], evidence["edges"][0]["from"])
            self.assertEqual(report["equity"]["edges"][0]["from"], "EN02")
            self.assertEqual(report["equity"]["edges"][0]["ownership_percent"], 16.11)
            self.assertEqual(report["equity"]["edges"][0]["ownership_percent"], evidence["edges"][0]["ownership_percent"])
            self.assertEqual(report["equity"]["evidence_summary"]["display_source_id"], "E01")
            self.assertEqual(report["equity"]["evidence_summary"]["display_source_title"], "法定披露")

    def test_legacy_equity_requires_explicit_migration_and_rejects_conflict(self):
        import compile_workspace
        import init_report_workspace

        enterprise = "测试企业有限公司"
        findings = init_report_workspace.build_findings(enterprise)["enterprise-findings.json"]
        findings["equity"] = {"review_status": "complete"}
        findings["report"]["equity"] = {"review_status": "not_public"}
        with self.assertRaisesRegex(ValueError, "显式迁移"):
            compile_workspace.compile_enterprise_findings(findings, Path("."))
        with self.assertRaisesRegex(ValueError, "股权迁移冲突"):
            compile_workspace.migrate_legacy_equity(findings)
    def test_compiler_assigns_ids_and_resolves_human_keys(self):
        import compile_workspace
        import init_report_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enterprise = "测试企业有限公司"
            for name, payload in {**init_report_workspace.build_payloads(enterprise), **init_report_workspace.build_findings(enterprise)}.items():
                (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            enterprise_findings = {
                "version": "1.0", "enterprise": enterprise,
                "sources": [{"key": "annual", "type": "annual_report", "name": "2025年年度报告"}],
                "report": {
                    "entity_resolution": {"user_input": enterprise, "name_type": "legal_entity", "legal_entity": enterprise, "analysis_entity": enterprise, "financial_scope": enterprise, "risk_scope": enterprise},
                    "enterprise_overview": {"source_keys": ["annual"]},
                    "businesses": [{"key": "beer", "segment": "啤酒"}],
                    "landing_businesses": [{"key": "trade", "business": "贸易结算", "fact_basis": "海外销售事实", "sanya_path": "设立贸易结算主体", "value": "结算便利", "feasibility": "待核", "policy_departments": ["海南省商务厅"]}],
                },
                "research": {
                    "enterprise_profile": {"analysis_entity": enterprise, "listing_status": "listed", "research_route": "listed_disclosure", "basis_source_keys": ["annual"]},
                    "research_stop_gate": {},
                    "facts": [{"key": "overseas", "source_keys": ["annual"], "action": "海外销售", "object": "境外客户", "enterprise_role": "出口方", "confidence": "high"}],
                    "business_candidates": [{"key": "trade_candidate", "name": "贸易结算", "fact_keys": ["overseas"]}],
                    "department_routes": [{"key": "trade_route", "landing_business_key": "trade", "candidate_keys": ["trade_candidate"], "department": "海南省商务厅"}],
                },
                "equity": {"provider_attempts": [], "sources": [], "nodes": [], "edges": [], "conflicts": [], "review_status": "incomplete"},
            }
            policy_findings = {
                "version": "1.0", "enterprise": enterprise, "researched_at": "2026-09-15T10:00:00+08:00",
                "sources": [{"key": "policy", "type": "policy", "name": "政策原文"}],
                "policy_records": [],
                "search": {"landing_business_hypotheses": [], "department_scan_profiles": [], "searches": []},
                "evidence": [],
            }
            (root / "enterprise-findings.json").write_text(json.dumps(enterprise_findings, ensure_ascii=False), encoding="utf-8")
            (root / "policy-findings.json").write_text(json.dumps(policy_findings, ensure_ascii=False), encoding="utf-8")
            compiled = compile_workspace.compile_workspace(root)

            report = compiled["report-data.json"]
            research = compiled["research-ledger.json"]
            self.assertEqual(report["businesses"][0]["id"], "B01")
            self.assertEqual(report["landing_businesses"][0]["id"], "L01")
            self.assertEqual(research["fact_ledger"][0]["id"], "F01")
            self.assertEqual(research["department_routes"][0]["landing_business_id"], "L01")
            self.assertEqual(research["department_routes"][0]["candidate_ids"], ["BC01"])
            self.assertEqual(research["enterprise_profile"]["basis_source_ids"], ["E01"])
            self.assertEqual(research["fact_ledger"][0]["source_id"], "E01")
            self.assertNotIn("source_ids", research["fact_ledger"][0])
            self.assertEqual(report["sources"][0]["id"], "E01")
            self.assertEqual(report["sources"][1]["id"], "P01")

    def test_compiler_rejects_unknown_reference_before_overwriting_ledgers(self):
        import compile_workspace
        import init_report_workspace

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enterprise = "测试企业有限公司"
            for name, payload in {**init_report_workspace.build_payloads(enterprise), **init_report_workspace.build_findings(enterprise)}.items():
                (root / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            before = (root / "report-data.json").read_text(encoding="utf-8")
            bad = init_report_workspace.build_findings(enterprise)["enterprise-findings.json"]
            bad["sources"] = [{"key": "known", "type": "annual_report", "name": "年报"}]
            bad["report"]["enterprise_overview"] = {"source_keys": ["missing"]}
            policy = init_report_workspace.build_findings(enterprise)["policy-findings.json"]
            policy["researched_at"] = "2026-09-15T10:00:00+08:00"
            (root / "enterprise-findings.json").write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            (root / "policy-findings.json").write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "未知key"):
                compile_workspace.compile_workspace(root)
            self.assertEqual((root / "report-data.json").read_text(encoding="utf-8"), before)

    def test_financial_rows_use_one_display_unit_and_derive_support_total_from_components(self):
        import compile_workspace

        enterprise = {
            "version": "1.0", "enterprise": "测试企业有限公司", "sources": [], "research": {}, "equity": {"nodes": [], "edges": []},
            "report": {"meta": {"financial_currency": "CNY", "financial_unit": "亿元"}, "financials": [{
                "year": "2025", "revenue": "12.50亿元", "profit": 1.25, "tax_value": "0.75亿元",
                "government_support_components": [{"name": "当期损益", "amount": 0.12}, {"name": "递延收益", "amount": 0.08}],
            }]},
        }
        with tempfile.TemporaryDirectory() as directory:
            report = compile_workspace.compile_enterprise_findings(enterprise, Path(directory))["report-data.json"]
        row = report["financials"][0]
        self.assertEqual(row["revenue"], "12.50")
        self.assertEqual(row["profit"], "1.25")
        self.assertEqual(row["tax_value"], "0.75")
        self.assertEqual(row["government_support"], "合计0.20亿元（当期损益、递延收益）")


if __name__ == "__main__":
    unittest.main()
