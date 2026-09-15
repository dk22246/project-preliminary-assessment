from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class CompileWorkspaceTests(unittest.TestCase):
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
                    "landing_businesses": [{"key": "trade", "business": "贸易结算"}],
                },
                "research": {
                    "enterprise_profile": {"analysis_entity": enterprise, "listing_status": "listed", "research_route": "listed_disclosure", "basis_source_keys": ["annual"]},
                    "research_stop_gate": {},
                    "facts": [{"key": "overseas", "source_keys": ["annual"], "action": "海外销售"}],
                    "business_candidates": [{"key": "trade_candidate", "name": "贸易结算", "fact_keys": ["overseas"]}],
                    "department_routes": [{"key": "trade_route", "landing_business_key": "trade", "candidate_keys": ["trade_candidate"], "department": "海南省商务厅"}],
                },
                "equity": {"provider_attempts": [], "sources": [], "nodes": [], "edges": [], "conflicts": [], "review_status": "incomplete"},
            }
            policy_findings = {
                "version": "1.0", "enterprise": enterprise, "researched_at": "2026-09-15T10:00:00+08:00",
                "sources": [{"key": "policy", "type": "policy", "name": "政策原文"}],
                "report": {"policy_research": [], "policy_opportunity_radar": {"signals": []}, "policies": []},
                "search": {"landing_business_hypotheses": [], "department_scan_profiles": [], "searches": [], "policy_candidates": []},
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


if __name__ == "__main__":
    unittest.main()
