import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from discover_current_policies import discover_current_policies
from policy_cache import PolicyCache


class PolicyPathExecutionTests(unittest.TestCase):
    def test_real_navigation_executes_paths_once_and_never_invents_missing_paths(self):
        root = "https://agency.gov.cn/"
        calls = []
        pages = {
            root: '<a href="/rules">规范性文件</a><a href="/apply">办理指南</a><a href="/invalid">废止目录</a>',
            root + "rules": "现行规范性文件目录",
            root + "apply": "办理事项与指南目录",
            root + "invalid": "2026年失效清单",
        }
        def fetch(url, headers):
            calls.append(url)
            return {"status": 200, "body": pages[url].encode(), "headers": {"Content-Type": "text/html"}}
        research = {"enterprise": "企业", "department_routes": [{"id": "D1", "department": "机关", "entry_url": root, "landing_business_id": "L1"}]}
        report = {"landing_businesses": [{"id": "L1", "business": "贸易"}]}
        with tempfile.TemporaryDirectory() as tmp:
            result = discover_current_policies(research, report, Path(tmp), fetch=fetch)
            runs = {r["path"]: r for r in result["policy_search_ledger"]["department_scan_profiles"][0]["runs"]}
        for path in ("normative_documents", "application_notices", "invalidity_catalog"):
            self.assertEqual(runs[path]["status"], "complete")
            self.assertTrue(runs[path]["evidence_record_keys"])
        self.assertEqual(len(calls), len(set(calls)))
        self.assertEqual(runs["theme_search"]["status"], "partial")

    def test_round_reuse_preserves_original_time_and_next_round_revalidates(self):
        calls = []
        def fetch(url, headers):
            calls.append(url)
            return {"status": 200, "body": b"policy", "headers": {"Content-Type": "text/html"}}
        with tempfile.TemporaryDirectory() as tmp:
            # 静态材料（dynamic=False）：24 小时内跨 run 复用，保留原始 retrieved_at
            first = PolicyCache(Path(tmp), "run1").revalidate("https://agency.gov.cn/a", fetch, dynamic=False, revalidated_at="2026-09-18T10:00:00+08:00")
            second = PolicyCache(Path(tmp), "run2").revalidate("https://agency.gov.cn/a", fetch, dynamic=False, revalidated_at="2026-09-18T10:05:00+08:00")
            self.assertEqual(first["retrieved_at"], second["retrieved_at"])
            self.assertEqual(len(calls), 1)
            # 动态材料（dynamic=True）：始终重新获取，即使 24 小时内
            PolicyCache(Path(tmp), "run3").revalidate("https://agency.gov.cn/a", fetch, dynamic=True, revalidated_at="2026-09-18T10:06:00+08:00")
            self.assertEqual(len(calls), 2)

    def test_cache_tampering_is_not_reused(self):
        calls = []
        def fetch(url, headers):
            calls.append(url)
            return {"status": 200, "body": b"real", "headers": {}}
        with tempfile.TemporaryDirectory() as tmp:
            cache = PolicyCache(Path(tmp), "run1")
            cache.revalidate("https://agency.gov.cn/a", fetch, revalidated_at="2026-09-18T10:00:00+08:00")
            cache._paths("https://agency.gov.cn/a")[1].write_bytes(b"tampered")
            cache.revalidate("https://agency.gov.cn/a", fetch, revalidated_at="2026-09-18T10:01:00+08:00")
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
