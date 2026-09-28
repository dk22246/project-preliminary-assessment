import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from discover_current_policies import discover_current_policies, merge_discovery_fragment
except ModuleNotFoundError:
    discover_current_policies = None
    merge_discovery_fragment = None


def research_ledger():
    return {
        "enterprise": "测试企业",
        "department_routes": [
            {"id": "DR01", "landing_business_id": "L01", "department": "海南省商务厅", "entry_url": "https://dofcom.hainan.gov.cn/dofcom/Policys/list.shtml"},
            {"id": "DR02", "landing_business_id": "L02", "department": "海南省商务厅", "entry_url": "https://dofcom.hainan.gov.cn/dofcom/Policys/list.shtml"},
        ],
        "business_candidates": [
            {"id": "BC01", "disposition": "include", "disposition_target": "L01"},
            {"id": "BC02", "disposition": "include", "disposition_target": "L02"},
        ],
    }


def report_data():
    return {"landing_businesses": [{"id": "L01", "business": "国际贸易"}, {"id": "L02", "business": "跨境电商"}]}


class PolicyDiscoveryRuntimeTests(unittest.TestCase):
    def test_chinese_route_matter_and_explicit_terms_select_official_titles(self):
        cases = [
            ({"matter": "外贸便利与离岸贸易"}, "关于离岸贸易便利化的通知"),
            ({"matter": "EF账户与跨境人民币"}, "多功能自由贸易账户EF业务管理办法"),
            ({"matter": "企业所得税及人才个人所得税"}, "关于延续实施海南自由贸易港企业所得税优惠政策的通知"),
            ({"matter": "境外投资备案"}, "ODI备案办理指南"),
            ({"matter": "企业事项", "policy_topics": ["企业所得税"]}, "关于延续企业所得税优惠政策的通知"),
            ({"matter": "企业事项", "query_terms": "EF业务"}, "EF业务管理办法"),
            ({"matter": "企业事项", "keywords": ["ODI"]}, "ODI备案办理指南"),
        ]
        for route_fields, title in cases:
            with self.subTest(route_fields=route_fields, title=title):
                entry = "https://dofcom.hainan.gov.cn/fixture/list.shtml"
                selected_url = "https://dofcom.hainan.gov.cn/fixture/selected.shtml"
                unrelated_url = "https://dofcom.hainan.gov.cn/fixture/unrelated.shtml"
                calls = []
                ledger = {
                    "enterprise": "测试企业",
                    "department_routes": [{
                        "id": "DR01", "landing_business_id": "L01",
                        "department": "海南省商务厅", "entry_url": entry,
                        **route_fields,
                    }],
                }

                def fetch(url, headers):
                    calls.append(url)
                    body = (
                        f'<a href="{selected_url}">{title}</a>'
                        f'<a href="{unrelated_url}">关于学校食堂食品安全的通知</a>'
                    ) if url == entry else "正式文件正文"
                    return {
                        "status": 200, "final_url": url,
                        "body": body.encode("utf-8"),
                        "headers": {"Content-Type": "text/html; charset=utf-8"},
                    }

                with tempfile.TemporaryDirectory() as directory:
                    result = discover_current_policies(
                        ledger, {"landing_businesses": [{"id": "L01", "business": "总部服务"}]},
                        Path(directory), fetch=fetch, sleep=lambda _: None,
                    )
                candidates = result["policy_search_ledger"]["discovered_candidates"]
                self.assertEqual([candidate["url"] for candidate in candidates], [selected_url])
                self.assertIn(selected_url, calls)
                self.assertNotIn(unrelated_url, calls)

    def test_deduplicates_one_department_entry_and_records_machine_receipt_fields(self):
        self.assertIsNotNone(discover_current_policies, "discover_current_policies.py must provide discover_current_policies")
        calls = []

        def fetch(url, headers):
            calls.append(url)
            return {"status": 200, "final_url": url, "body": b"official policy directory", "headers": {"Content-Type": "text/html"}}

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "discovery"
            formal_search = Path(directory) / "policy-search-ledger.json"
            formal_evidence = Path(directory) / "policy-evidence.json"
            formal_search.write_text('{"formal": true}', encoding="utf-8")
            formal_evidence.write_text('{"formal": true}', encoding="utf-8")
            result = discover_current_policies(research_ledger(), report_data(), out, fetch=fetch)
            self.assertTrue((out / "policy-search-ledger-draft.json").is_file())
            self.assertTrue((out / "policy-evidence-draft.json").is_file())
            self.assertTrue((out / "policy-findings-fragment.json").is_file())
            self.assertEqual(formal_search.read_text(encoding="utf-8"), '{"formal": true}')
            self.assertEqual(formal_evidence.read_text(encoding="utf-8"), '{"formal": true}')

        self.assertEqual(calls, ["https://dofcom.hainan.gov.cn/dofcom/Policys/list.shtml"])
        self.assertEqual(result["metrics"]["requests"], 1)
        self.assertEqual(result["metrics"]["successful_requests"], 1)
        searches = result["policy_search_ledger"]["searches"]
        profiles = result["policy_search_ledger"]["department_scan_profiles"]
        self.assertEqual(len(searches), 2)
        self.assertEqual(len(profiles), 1)
        self.assertEqual(len(profiles[0]["runs"]), 5)
        for item in searches:
            self.assertEqual(item["department_searches"][0]["department_role"], "primary_regulator")
            self.assertEqual(item["department_searches"][0]["profile_key"], profiles[0]["key"])
            self.assertNotIn("runs", item["department_searches"][0])
        complete = next(run for run in profiles[0]["runs"] if run["path"] == "department_documents")
        self.assertEqual(complete["status"], "complete")
        self.assertIn("checked_at", complete)
        self.assertIn("result_count", complete)
        self.assertIn("result_source_keys", complete)
        self.assertIn("evidence_record_keys", complete)

    def test_retries_transient_gateway_failure_at_most_two_times(self):
        self.assertIsNotNone(discover_current_policies, "discover_current_policies.py must provide discover_current_policies")
        attempts = []

        def fetch(url, headers):
            attempts.append(url)
            if len(attempts) < 3:
                return {"status": 503, "final_url": url, "headers": {}}
            return {"status": 200, "final_url": url, "body": b"ok", "headers": {"Content-Type": "text/html"}}

        with tempfile.TemporaryDirectory() as directory:
            result = discover_current_policies(research_ledger(), report_data(), Path(directory), fetch=fetch, sleep=lambda _: None)

        self.assertEqual(len(attempts), 3)
        self.assertEqual(result["metrics"]["retries"], 2)
        self.assertEqual(result["metrics"]["failed_requests"], 0)

    def test_serializes_different_department_entries_on_the_same_official_host(self):
        self.assertIsNotNone(discover_current_policies, "discover_current_policies.py must provide discover_current_policies")
        ledger = research_ledger()
        ledger["department_routes"][1]["department"] = "海南省发展和改革委员会"
        ledger["department_routes"][1]["entry_url"] = "https://dofcom.hainan.gov.cn/another-policy-list.shtml"
        active = 0
        peak = 0
        lock = threading.Lock()

        def fetch(url, headers):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1
            return {"status": 200, "final_url": url, "body": b"ok", "headers": {"Content-Type": "text/html"}}

        with tempfile.TemporaryDirectory() as directory:
            discover_current_policies(ledger, report_data(), Path(directory), fetch=fetch, max_concurrency=4)

        # 同域名最多 2 并发（防对同一官方站过载，但不强制串行）
        self.assertLessEqual(peak, 2)
        self.assertGreaterEqual(peak, 1)

    def test_persistent_discovery_fragment_contains_evidence_and_shared_url_contract(self):
        calls = []
        ledger = research_ledger()
        for route in ledger["department_routes"]:
            route["entry_url"] = "https://x.example/list"

        def fetch(url, headers):
            calls.append(url)
            bodies = {
                "https://x.example/list": '<a href="/policy.html">国际贸易政策实施办法</a>'.encode("gb18030"),
                "https://x.example/policy.html": '<a href="/files/apply公示.pdf">附件</a>'.encode("gb18030"),
                "https://x.example/files/apply公示.pdf": b"PDF",
            }
            return {"status": 200, "final_url": url, "body": bodies[url], "headers": {"Content-Type": "text/html; charset=gb18030"}}

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "discovery"
            result = discover_current_policies(ledger, report_data(), out, fetch=fetch, sleep=lambda _: None)
            fragment = __import__("json").loads((out / "policy-findings-fragment.json").read_text(encoding="utf-8"))

        self.assertEqual(calls.count("https://x.example/list"), 1)
        self.assertEqual(calls.count("https://x.example/policy.html"), 1)
        self.assertEqual(calls.count("https://x.example/files/apply公示.pdf"), 1)
        self.assertEqual({item["evidence_type"] for item in result["policy_evidence"]["records"]}, {"department_entry", "policy_candidate_page", "policy_attachment"})
        self.assertTrue(fragment["evidence"])
        self.assertTrue(all(item.get("key") and item.get("source_key") and item.get("policy_source_key") for item in fragment["evidence"]))
        self.assertTrue(all(item["eligibility_status"] == "unknown" for item in result["policy_search_ledger"]["discovered_candidates"]))

    def test_candidate_and_attachment_failures_are_persistent_and_attachment_not_complete(self):
        ledger = research_ledger()
        for route in ledger["department_routes"]:
            route["entry_url"] = "https://x.example/list"

        def fetch(url, headers):
            if url.endswith("/list"):
                body = '<a href="/policy.html">国际贸易政策实施办法</a>'.encode("utf-8")
                return {"status": 200, "final_url": url, "body": body, "headers": {"Content-Type": "text/html; charset=utf-8"}}
            return {"status": 503, "final_url": url, "headers": {}}

        with tempfile.TemporaryDirectory() as directory:
            result = discover_current_policies(ledger, report_data(), Path(directory), fetch=fetch, sleep=lambda _: None)

        self.assertTrue(result["policy_evidence"]["failures"])
        self.assertTrue(result["policy_search_ledger"]["discovered_candidates"])
        self.assertNotEqual(result["policy_search_ledger"]["discovered_candidates"][0]["attachment_status"], "complete")

    def test_merge_preserves_complete_profile_run_old_task_and_marks_same_url_sha_change(self):
        self.assertIsNotNone(merge_discovery_fragment)
        current = {
            "enterprise": "测试企业",
            "researched_at": "formal-old",
            "sources": [{"id": "P01", "key": "source:url", "stable_key": "source:url", "evidence_record_ids": ["PE01"], "artifact_sha256": "old-sha", "revalidated_at": "old-time"}],
            "search": {
                "department_scan_profiles": [{"id": "DSP01", "key": "profile:one", "runs": [{"path": "department_documents", "status": "complete", "source_keys": ["source:url"], "evidence_record_keys": ["evidence:old"]}]}],
                "searches": [{"id": "PS01", "key": "search:old", "coverage_status": "complete", "profile_keys": ["profile:one"]}],
                "discovered_candidates": [],
            },
        }
        fragment = {
            "enterprise": "测试企业",
            "researched_at": "round-new",
            "sources": [{"id": "P01", "key": "source:url", "stable_key": "source:url", "evidence_record_ids": ["PE02"], "artifact_sha256": "new-sha", "revalidated_at": "new-time"}],
            "evidence": [{"key": "evidence:new", "source_key": "source:url", "policy_source_key": "source:url", "id": "PE02", "artifact_sha256": "new-sha", "revalidated_at": "new-time"}],
            "search": {
                "department_scan_profiles": [{"id": "DSP01", "key": "profile:one", "runs": [{"path": "department_documents", "status": "partial", "source_keys": [], "evidence_record_keys": []}]}],
                "searches": [{"id": "PS01", "key": "search:old", "coverage_status": "partial", "profile_keys": ["profile:one"]}],
                "discovered_candidates": [],
            },
            "failures": [{"url": "https://x.example/missing", "error": "kept"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            findings = Path(directory) / "policy-findings.json"
            fragment_path = Path(directory) / "fragment.json"
            findings.write_text(__import__("json").dumps(current), encoding="utf-8")
            fragment_path.write_text(__import__("json").dumps(fragment), encoding="utf-8")
            merged = merge_discovery_fragment(findings, fragment_path)

        run = merged["search"]["department_scan_profiles"][0]["runs"][0]
        self.assertEqual(run["status"], "partial")
        self.assertEqual(run["historical_complete_run"]["status"], "complete")
        self.assertEqual(merged["search"]["searches"][0]["coverage_status"], "partial")
        self.assertEqual(merged["search"]["searches"][0]["previous_complete"]["coverage_status"], "complete")
        self.assertEqual(merged["researched_at"], "formal-old")
        self.assertEqual(merged["discovery_last_researched_at"], "round-new")
        self.assertEqual(merged["sources"][0]["review_status"], "changed_pending_review")
        self.assertIn("PE01", merged["sources"][0]["evidence_record_ids"])
        self.assertIn("PE02", merged["sources"][0]["evidence_record_ids"])
        self.assertEqual(merged["search"]["failures"][0]["url"], "https://x.example/missing")

    def test_refresh_keeps_old_artifact_bytes_and_uses_new_url_sha_artifact(self):
        ledger = research_ledger()
        for route in ledger["department_routes"]:
            route["entry_url"] = "https://x.example/list"
        round_number = [0]

        def fetch(url, headers):
            body = b"entry-v1" if round_number[0] == 0 else b"entry-v2"
            return {"status": 200, "final_url": url, "body": body, "headers": {"Content-Type": "text/html"}}

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "discovery"
            first = discover_current_policies(ledger, report_data(), out, fetch=fetch, sleep=lambda _: None)
            first_record = first["policy_evidence"]["records"][0]
            first_path = Path(first_record["artifact_path"])
            first_bytes = first_path.read_bytes()
            first_sha = first_record["artifact_sha256"]
            round_number[0] = 1
            second = discover_current_policies(ledger, report_data(), out, fetch=fetch, sleep=lambda _: None)
            second_record = second["policy_evidence"]["records"][0]

            self.assertEqual(first_path.read_bytes(), first_bytes)
            self.assertEqual(first_sha, __import__("hashlib").sha256(first_bytes).hexdigest())
            self.assertNotEqual(first_record["artifact_path"], second_record["artifact_path"])
            self.assertNotEqual(first_record["artifact_sha256"], second_record["artifact_sha256"])
            self.assertTrue(Path(second_record["artifact_path"]).is_file())

    def test_fragment_merge_compile_boundary_uses_keys_and_same_sha_refresh_is_not_changed(self):
        current = {
            "enterprise": "测试企业",
            "researched_at": "formal",
            "sources": [{"id": "P01", "key": "old-source", "artifact_sha256": "same-sha", "evidence_keys": ["old-evidence"]}],
            "evidence": [{"id": "PE01", "key": "old-evidence", "source_key": "old-source", "policy_source_key": "old-source", "artifact_sha256": "same-sha"}],
            "search": {
                "department_scan_profiles": [{"id": "DSP01", "key": "profile-key", "runs": [{"path": "department_documents", "status": "complete", "result_source_keys": ["old-source"], "evidence_record_keys": ["old-evidence"]}]}],
                "searches": [{"id": "PS01", "key": "search-key", "profile_key": "profile-key", "discovered_candidate_keys": ["candidate-key"], "coverage_status": "complete"}],
                "discovered_candidates": [{"id": "PC01", "key": "candidate-key", "search_key": "search-key", "formal_policy_source_keys": ["old-source"], "evidence_record_keys": ["old-evidence"]}],
            },
        }
        fragment = {
            "enterprise": "测试企业",
            "researched_at": "refresh",
            "sources": [{"id": "P01", "key": "new-source", "artifact_sha256": "same-sha", "evidence_keys": ["new-evidence"]}],
            "evidence": [{"id": "PE01", "key": "new-evidence", "source_key": "new-source", "policy_source_key": "new-source", "artifact_sha256": "same-sha"}],
            "search": {
                "department_scan_profiles": [{"id": "DSP01", "key": "new-profile", "runs": [{"path": "department_documents", "status": "complete", "result_source_keys": ["new-source"], "evidence_record_keys": ["new-evidence"]}]}],
                "searches": [{"id": "PS01", "key": "new-search", "profile_key": "new-profile", "discovered_candidate_keys": ["new-candidate"], "coverage_status": "complete"}],
                "discovered_candidates": [{"id": "PC01", "key": "new-candidate", "search_key": "new-search", "formal_policy_source_keys": ["new-source"], "evidence_record_keys": ["new-evidence"]}],
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            findings = Path(directory) / "policy-findings.json"
            fragment_path = Path(directory) / "fragment.json"
            findings.write_text(__import__("json").dumps(current), encoding="utf-8")
            fragment_path.write_text(__import__("json").dumps(fragment), encoding="utf-8")
            merged = merge_discovery_fragment(findings, fragment_path)

        self.assertEqual(len({source["id"] for source in merged["sources"]}), len(merged["sources"]))
        self.assertNotIn("review_status", next(source for source in merged["sources"] if source["key"] == "new-source"))
        self.assertTrue(all("result_source_keys" in run for profile in merged["search"]["department_scan_profiles"] for run in profile["runs"]))
        self.assertTrue(all("profile_key" in search and "key" in search for search in merged["search"]["searches"]))
        self.assertTrue(all("search_key" in candidate and "formal_policy_source_keys" in candidate for candidate in merged["search"]["discovered_candidates"]))

    def test_merge_marks_canonical_policy_record_when_source_sha_changes(self):
        current = {
            "enterprise": "测试企业",
            "researched_at": "formal",
            "sources": [{"id": "P01", "key": "source:policy", "artifact_sha256": "old-sha"}],
            "policy_records": [{"key": "policy-record:one", "source_keys": ["source:policy"], "status": "current"}],
            "search": {},
        }
        fragment = {
            "enterprise": "测试企业",
            "researched_at": "refresh",
            "sources": [{"id": "P01", "key": "source:policy", "artifact_sha256": "new-sha"}],
            "evidence": [],
            "search": {},
            "failures": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            findings = Path(directory) / "policy-findings.json"
            fragment_path = Path(directory) / "fragment.json"
            findings.write_text(__import__("json").dumps(current), encoding="utf-8")
            fragment_path.write_text(__import__("json").dumps(fragment), encoding="utf-8")
            merged = merge_discovery_fragment(findings, fragment_path)

        self.assertEqual(merged["policy_records"][0]["review_status"], "changed_source_pending_review")

    def test_real_discover_merge_compile_uses_key_refs_across_overlapping_round_ids(self):
        import compile_workspace
        import init_report_workspace

        enterprise = "测试企业有限公司"
        ledger = {
            "enterprise": enterprise,
            "department_routes": [{"id": "DR01", "landing_business_id": "L01", "department": "海南省商务厅", "entry_url": "https://x.example/list"}],
            "business_candidates": [],
        }
        report_data = {"landing_businesses": [{"id": "L01", "business": "国际贸易"}]}
        round_number = [0]

        def fetch(url, headers):
            if url.endswith("/list"):
                title = "国际贸易政策实施办法"
                href = "/policy-a.html" if round_number[0] == 0 else "/policy-b.html"
                body = f'<a href="{href}">{title}</a>'.encode("utf-8")
            else:
                body = b"<html>policy body</html>"
            return {"status": 200, "final_url": url, "body": body, "headers": {"Content-Type": "text/html; charset=utf-8"}}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in {**init_report_workspace.build_payloads(enterprise), **init_report_workspace.build_findings(enterprise)}.items():
                (root / name).write_text(__import__("json").dumps(payload, ensure_ascii=False), encoding="utf-8")
            enterprise_findings = init_report_workspace.build_findings(enterprise)["enterprise-findings.json"]
            enterprise_findings["report"] = {
                "entity_resolution": {"user_input": enterprise, "name_type": "legal_entity", "legal_entity": enterprise, "analysis_entity": enterprise, "financial_scope": enterprise, "risk_scope": enterprise},
                "enterprise_overview": {},
                "businesses": [{"key": "beer", "segment": "啤酒"}],
                "landing_businesses": [{"key": "trade", "business": "贸易结算", "fact_basis": "海外销售事实", "sanya_path": "设立贸易结算主体", "value": "结算便利", "feasibility": "待核", "policy_departments": ["海南省商务厅"]}],
            }
            enterprise_findings["research"] = {
                "enterprise_profile": {"analysis_entity": enterprise, "listing_status": "listed", "research_route": "listed_disclosure"},
                "research_stop_gate": {}, "facts": [], "business_candidates": [],
                "department_routes": [{"key": "trade-route", "landing_business_key": "trade", "department": "海南省商务厅"}],
            }
            (root / "enterprise-findings.json").write_text(__import__("json").dumps(enterprise_findings, ensure_ascii=False), encoding="utf-8")
            policy_path = root / "policy-findings.json"
            policy = init_report_workspace.build_findings(enterprise)["policy-findings.json"]
            policy["researched_at"] = "formal"
            policy_path.write_text(__import__("json").dumps(policy, ensure_ascii=False), encoding="utf-8")

            first = discover_current_policies(ledger, report_data, root / "round1", fetch=fetch, sleep=lambda _: None)
            merge_discovery_fragment(policy_path, root / "round1" / "policy-findings-fragment.json")
            first_ids = {record["id"] for record in first["policy_evidence"]["records"]}
            round_number[0] = 1
            second = discover_current_policies(ledger, report_data, root / "round2", fetch=fetch, sleep=lambda _: None)
            merge_discovery_fragment(policy_path, root / "round2" / "policy-findings-fragment.json")
            second_ids = {record["id"] for record in second["policy_evidence"]["records"]}
            self.assertTrue(first_ids & second_ids)
            compiled = compile_workspace.compile_workspace(root)

        search = compiled["policy-search-ledger.json"]
        profile = search["department_scan_profiles"][0]
        run = next(item for item in profile["runs"] if item["path"] == "department_documents")
        self.assertIn("result_source_ids", run)
        self.assertIn("evidence_record_ids", run)
        self.assertTrue(run["result_source_ids"])
        self.assertTrue(run["evidence_record_ids"])
        for candidate in search.get("discovered_candidates", []):
            self.assertNotIn("stable_key", candidate.get("formal_policy_source_ids", []))


if __name__ == "__main__":
    unittest.main()
