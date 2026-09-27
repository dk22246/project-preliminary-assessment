import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from policy_cache import PolicyCache
except ModuleNotFoundError:
    PolicyCache = None


class PolicyCacheTests(unittest.TestCase):
    def test_revalidation_preserves_original_artifact_and_records_a_fresh_receipt(self):
        self.assertIsNotNone(PolicyCache, "policy_cache.py must provide PolicyCache")
        with tempfile.TemporaryDirectory() as directory:
            cache = PolicyCache(Path(directory))
            first = cache.store(
                "https://dofcom.hainan.gov.cn/dofcom/policy.html",
                b"official policy text",
                {"ETag": '"v1"', "Content-Type": "text/html"},
                retrieved_at="2026-08-27T08:00:00+08:00",
            )
            calls = []

            def conditional_fetch(url, headers):
                calls.append((url, headers))
                return {"status": 304, "headers": {"ETag": '"v1"'}}

            # 超过 24 小时：不得直接复用，须发条件请求走 304 复验路径
            receipt = cache.revalidate(
                "https://dofcom.hainan.gov.cn/dofcom/policy.html",
                conditional_fetch,
                revalidated_at="2026-08-28T09:00:00+08:00",
            )

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]["If-None-Match"], '"v1"')
            self.assertEqual(receipt["artifact_sha256"], hashlib.sha256(b"official policy text").hexdigest())
            self.assertEqual(receipt["cached_artifact_created_at"], first["cached_artifact_created_at"])
            self.assertEqual(receipt["revalidated_at"], "2026-08-28T09:00:00+08:00")
            self.assertNotEqual(receipt["retrieved_at"], "2026-08-27T08:00:00+08:00")

    def test_fresh_cache_within_24h_is_reused_across_runs_without_refetch(self):
        self.assertIsNotNone(PolicyCache, "policy_cache.py must provide PolicyCache")
        with tempfile.TemporaryDirectory() as directory:
            # 跨 run 复用：round_id 不同时，24 小时内仍应复用缓存，不重新请求
            cache = PolicyCache(Path(directory), round_id="run-A")
            cache.store(
                "https://dofcom.hainan.gov.cn/dofcom/policy.html",
                b"official policy text",
                {"ETag": '"v1"', "Content-Type": "text/html"},
                retrieved_at="2026-08-27T08:00:00+08:00",
            )
            cache2 = PolicyCache(Path(directory), round_id="run-B")
            calls = []

            def fetch_should_not_be_called(url, headers):
                calls.append((url, headers))
                return {"status": 200, "body": b"should not refetch", "headers": {"Content-Type": "text/html"}}

            receipt = cache2.revalidate(
                "https://dofcom.hainan.gov.cn/dofcom/policy.html",
                fetch_should_not_be_called,
                revalidated_at="2026-08-27T09:00:00+08:00",
            )

            self.assertEqual(len(calls), 0)
            self.assertTrue(receipt.get("reused_in_round"))
            self.assertEqual(receipt["artifact_sha256"], hashlib.sha256(b"official policy text").hexdigest())

    def test_dynamic_notice_always_retrieves_fresh_content_instead_of_accepting_304(self):
        self.assertIsNotNone(PolicyCache, "policy_cache.py must provide PolicyCache")
        with tempfile.TemporaryDirectory() as directory:
            cache = PolicyCache(Path(directory))
            cache.store(
                "https://hainan.chinatax.gov.cn/notice.html", b"old notice", {"ETag": '"old"'},
                retrieved_at="2026-08-27T08:00:00+08:00",
            )
            received_headers = []

            def fresh_fetch(url, headers):
                received_headers.append(headers)
                return {"status": 200, "body": b"new notice", "headers": {"ETag": '"new"', "Content-Type": "text/html"}}

            receipt = cache.revalidate(
                "https://hainan.chinatax.gov.cn/notice.html", fresh_fetch,
                dynamic=True, revalidated_at="2026-08-27T09:00:00+08:00",
            )

            self.assertEqual(received_headers, [{}])
            self.assertEqual(receipt["artifact_sha256"], hashlib.sha256(b"new notice").hexdigest())
            self.assertTrue(receipt["fresh_retrieval"])


if __name__ == "__main__":
    unittest.main()
