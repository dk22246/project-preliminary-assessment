import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from discover_current_policies import discover_current_policies
except ModuleNotFoundError:
    discover_current_policies = None


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
            self.assertEqual(item["department_searches"][0]["profile_id"], profiles[0]["id"])
            self.assertNotIn("runs", item["department_searches"][0])
        complete = next(run for run in profiles[0]["runs"] if run["path"] == "department_documents")
        self.assertEqual(complete["status"], "complete")
        self.assertIn("checked_at", complete)
        self.assertIn("result_count", complete)
        self.assertIn("result_source_ids", complete)
        self.assertIn("evidence_record_ids", complete)

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

        self.assertEqual(peak, 1)


if __name__ == "__main__":
    unittest.main()
