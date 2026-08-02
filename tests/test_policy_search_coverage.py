import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "validate_policy_search_coverage.py"
PATHS = (
    "theme_search",
    "department_documents",
    "normative_documents",
    "application_notices",
    "award_publicity",
    "invalidity_catalog",
    "document_graph",
)


def report(outcome="conditional_opportunity"):
    return {
        "landing_businesses": [{"id": "L01", "business": "赛事活动运营"}],
        "policy_research": [{
            "landing_business_id": "L01",
            "topic": "体育赛事和大型活动支持",
            "searched_departments": ["三亚市旅游和文化广电体育局"],
            "outcome": outcome,
            "conclusion": "测试结论",
            "evidence_source_ids": ["P01"],
            "policy_ids": ["P01"] if outcome == "conditional_opportunity" else [],
        }],
        "sources": [{"id": "P01"}],
    }


def research_ledger():
    return {
        "enterprise": "测试企业",
        "fact_ledger": [{"id": "FA01", "source_id": "E01", "action": "主办", "object": "电竞嘉年华", "enterprise_role": "运营者", "confidence": "high"}],
        "business_candidates": [{"id": "BC01", "name": "赛事运营", "fact_ids": ["FA01"], "disposition": "include", "disposition_target": "L01", "disposition_reason": "测试"}],
        "department_routes": [{"id": "DR01", "landing_business_id": "L01", "candidate_ids": ["BC01"], "matter": "体育赛事组织与运营", "route_rule_id": "sports_event_operation", "department": "三亚市旅游和文化广电体育局", "route_type": "matched_static_rule", "status": "matched_static_rule"}],
        "policy_candidates": [],
    }


def coverage_ledger():
    runs = [
        {
            "path": name,
            "status": "complete",
            "entry_url": f"https://lwj.sanya.gov.cn/lwjsite/zcwj/{name}.shtml",
            "receipt_id": f"R-{index:02d}",
            "result_summary": "已完成官方目录或原文检索。",
        }
        for index, name in enumerate(PATHS, 1)
    ]
    return {
        "version": "1.0",
        "enterprise": "测试企业",
        "landing_business_hypotheses": [{
            "id": "PH01",
            "landing_business_id": "L01",
            "fact_ids": ["FA01"],
            "actions": ["主办", "运营"],
            "roles": ["赛事主办方"],
            "forms": ["电竞嘉年华"],
            "effects": ["客流和消费"],
            "government_matters": [
                {"name": "体育赛事", "disposition": "route", "route_ids": ["DR01"]},
                {"name": "大型活动", "disposition": "route", "route_ids": ["DR01"]},
                {"name": "文化旅游", "disposition": "route", "route_ids": ["DR01"]},
            ],
            "policy_instruments": ["赛事奖励", "活动资金支持"],
        }],
        "searches": [{
            "id": "PS01",
            "landing_business_id": "L01",
            "topic": "体育赛事和大型活动支持",
            "route_ids": ["DR01"],
            "fact_ids": ["FA01"],
            "department_searches": [{
                "department": "三亚市旅游和文化广电体育局",
                "department_role": "primary_regulator",
                "routing_basis": "静态规则 sports_event_operation",
                "runs": runs,
            }],
            "candidate_policy_ids": ["PSC01"],
            "coverage_status": "complete",
        }],
        "policy_candidates": [{
            "id": "PSC01",
            "search_id": "PS01",
            "title": "三亚市体育赛事活动支持办法",
            "status": "current",
            "eligibility_status": "unknown",
            "disposition": "include",
            "formal_policy_source_ids": ["P01"],
            "attachment_status": "complete",
        }],
    }


def run_validation(report_data, research, coverage):
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        report_path = directory / "report.json"
        research_path = directory / "research.json"
        coverage_path = directory / "coverage.json"
        for path, data in ((report_path, report_data), (research_path, research), (coverage_path, coverage)):
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), str(coverage_path), "--research-ledger", str(research_path), "--report-data", str(report_path)],
            text=True,
            capture_output=True,
        )


class PolicySearchCoverageTests(unittest.TestCase):
    def test_accepts_complete_dynamic_search_and_conditional_opportunity(self):
        result = run_validation(report(), research_ledger(), coverage_ledger())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_homepage_as_department_document_scan(self):
        ledger = coverage_ledger()
        run = next(item for item in ledger["searches"][0]["department_searches"][0]["runs"] if item["path"] == "department_documents")
        run["entry_url"] = "https://lwj.sanya.gov.cn/"
        result = run_validation(report(), research_ledger(), ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("首页", result.stdout)

    def test_rejects_missing_required_discovery_path(self):
        ledger = coverage_ledger()
        ledger["searches"][0]["department_searches"][0]["runs"] = [
            item for item in ledger["searches"][0]["department_searches"][0]["runs"] if item["path"] != "department_documents"
        ]
        result = run_validation(report(), research_ledger(), ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("department_documents", result.stdout)

    def test_rejects_no_current_policy_when_current_policy_exists_but_eligibility_is_unknown(self):
        ledger = coverage_ledger()
        result = run_validation(report("no_current_policy"), research_ledger(), ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conditional_opportunity", result.stdout)

    def test_rejects_relevant_attachment_failure_as_research_incomplete(self):
        ledger = coverage_ledger()
        ledger["policy_candidates"][0]["attachment_status"] = "failed"
        result = run_validation(report(), research_ledger(), ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("research_incomplete", result.stdout)

    def test_rejects_failed_collection_path_instead_of_silently_producing_a_negative_result(self):
        ledger = coverage_ledger()
        ledger["searches"][0]["department_searches"][0]["runs"][0]["status"] = "failed"
        result = run_validation(report(), research_ledger(), ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("research_incomplete", result.stdout)

    def test_accepts_no_current_policy_only_after_full_completed_coverage(self):
        ledger = coverage_ledger()
        ledger["searches"][0]["candidate_policy_ids"] = []
        ledger["policy_candidates"] = []
        result = run_validation(report("no_current_policy"), research_ledger(), ledger)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_requires_each_semantic_government_matter_to_be_routed_or_explicitly_excluded(self):
        ledger = coverage_ledger()
        ledger["landing_business_hypotheses"][0]["government_matters"][2].pop("route_ids")
        result = run_validation(report(), research_ledger(), ledger)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("文化旅游", result.stdout)

    def test_pipeline_never_renders_html_when_dynamic_policy_search_is_incomplete(self):
        ledger = json.loads((ROOT / "examples" / "flyco-policy-search-ledger.json").read_text(encoding="utf-8"))
        ledger["department_scan_profiles"][0]["runs"][0]["status"] = "failed"
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            ledger_path = directory / "incomplete-policy-search.json"
            output_dir = directory / "output"
            ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, "-X", "utf8", str(ROOT / "scripts" / "run_report_pipeline.py"),
                    str(ROOT / "examples" / "flyco-report-data.json"),
                    "--equity-evidence", str(ROOT / "examples" / "flyco-equity-evidence.json"),
                    "--research-ledger", str(ROOT / "examples" / "flyco-research-ledger.json"),
                    "--policy-search-ledger", str(ledger_path),
                    "--out-dir", str(output_dir),
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("research_incomplete", result.stdout)
            self.assertFalse((output_dir / "report.html").exists())


if __name__ == "__main__":
    unittest.main()
