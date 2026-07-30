import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from evidence_collectors.html_extract import extract_html
from evidence_collectors.registry import is_allowed_url
import collect_web_evidence as collector
from validate_evidence import validate_ledger


class WebEvidenceTests(unittest.TestCase):
    def test_allows_registered_official_policy_source(self):
        self.assertTrue(is_allowed_url("https://hainan.chinatax.gov.cn/policy", set()))

    def test_rejects_unregistered_commercial_source(self):
        self.assertFalse(is_allowed_url("https://example.com/article", set()))

    def test_extracts_visible_text_and_document_links(self):
        result = extract_html(
            "<html><head><title>政策正文</title></head><body><nav>导航</nav><p>政策内容</p>"
            "<script>ignore()</script><a href='/files/notice.pdf'>附件</a></body></html>",
            "https://hainan.chinatax.gov.cn/policy",
        )
        self.assertEqual(result.title, "政策正文")
        self.assertIn("政策内容", result.text)
        self.assertNotIn("ignore", result.text)
        self.assertEqual(result.attachments, [{"url": "https://hainan.chinatax.gov.cn/files/notice.pdf", "file_type": "pdf"}])

    def test_validator_rejects_unregistered_source(self):
        with tempfile.TemporaryDirectory() as directory:
            errors = validate_ledger(
                {"enterprise": "样例企业", "topic": "税收", "evidence": [{"source_url": "https://example.com/x"}]},
                Path(directory),
            )
        self.assertTrue(any("不在允许来源" in error for error in errors))

    def test_validator_accepts_complete_success_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = root / "official.md"
            content.write_text("# 正式政策\n\n政策正文", encoding="utf-8")
            ledger = {
                "enterprise": "样例企业",
                "topic": "税收",
                "evidence": [{
                    "source_url": "https://hainan.chinatax.gov.cn/policy",
                    "canonical_url": "https://hainan.chinatax.gov.cn/policy",
                    "title": "正式政策",
                    "publisher": "国家税务总局海南省税务局",
                    "source_category": "government",
                    "purpose": "政策线索",
                    "fetched_at": "2026-07-30T00:00:00+00:00",
                    "http_status": 200,
                    "extraction_status": "success",
                    "content_path": "official.md",
                    "content_sha256": hashlib.sha256(content.read_bytes()).hexdigest(),
                    "attachments": [],
                    "error": "",
                }],
            }
            self.assertEqual(validate_ledger(ledger, root), [])

    def test_validator_requires_error_for_failed_record(self):
        with tempfile.TemporaryDirectory() as directory:
            errors = validate_ledger(
                {"enterprise": "样例企业", "topic": "税收", "evidence": [{
                    "source_url": "https://hainan.chinatax.gov.cn/policy",
                    "canonical_url": "https://hainan.chinatax.gov.cn/policy",
                    "title": "",
                    "publisher": "",
                    "source_category": "government",
                    "purpose": "政策线索",
                    "fetched_at": "2026-07-30T00:00:00+00:00",
                    "http_status": 503,
                    "extraction_status": "failed",
                    "content_path": "",
                    "content_sha256": "",
                    "attachments": [],
                    "error": "",
                }]},
                Path(directory),
            )
        self.assertTrue(any("抓取失败记录缺少错误信息" in error for error in errors))

    def test_collector_rejects_redirect_to_unregistered_host(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(collector, "fetch_html", return_value=(200, "https://example.com/article", "<title>网页</title><p>正文</p>", "")):
                record = collector.collect(
                    "https://hainan.chinatax.gov.cn/policy",
                    purpose="政策线索",
                    out_dir=Path(directory),
                    explicit_hosts=set(),
                    timeout=1,
                    retries=0,
                    index=1,
                )
        self.assertEqual(record["extraction_status"], "failed")
        self.assertIn("重定向", record["error"])

    def test_collector_records_the_final_allowed_redirect_source(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(collector, "fetch_html", return_value=(200, "https://www.sse.com.cn/article", "<title>公告</title><p>正文</p>", "")):
                record = collector.collect(
                    "https://hainan.chinatax.gov.cn/policy",
                    purpose="企业公告",
                    out_dir=Path(directory),
                    explicit_hosts=set(),
                    timeout=1,
                    retries=0,
                    index=1,
                )
        self.assertEqual(record["extraction_status"], "success")
        self.assertEqual(record["publisher"], "www.sse.com.cn")
        self.assertEqual(record["source_category"], "disclosure")


if __name__ == "__main__":
    unittest.main()
