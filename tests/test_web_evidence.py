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
    @staticmethod
    def _pdf_with_text(text: str) -> bytes:
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        result = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for number, body in enumerate(objects, 1):
            offsets.append(len(result))
            result.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
        xref = len(result)
        result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
        result.extend(b"".join(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:]))
        result.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
        return bytes(result)

    def _cached_pdf_record(self, directory: str, body: bytes, digest: str | None = None, final_url: str = "https://hainan.chinatax.gov.cn/report.pdf") -> dict:
        root = Path(directory)
        raw = root / "raw.pdf"
        raw.write_bytes(body)

        class Cache:
            round_id = "test-round"

            @staticmethod
            def _paths(_url):
                return root / "receipt.json", raw

        raw_hash = digest or hashlib.sha256(body).hexdigest()
        receipt = {
            "http_status": 200,
            "final_url": final_url,
            "content_type": "application/pdf",
            "retrieved_at": "2026-09-21T00:00:00+00:00",
            "artifact_sha256": raw_hash,
            "reused_in_round": True,
        }
        with patch.object(collector, "workspace_cache", return_value=Cache()), patch.object(collector, "_request_with_retry", return_value=(receipt, 1, "")):
            return collector.collect(
                "https://hainan.chinatax.gov.cn/report.pdf", purpose="年报", out_dir=root,
                explicit_hosts=set(), timeout=1, retries=0, index=1,
            )

    def test_cached_pdf_extracts_text_once_and_reuses_same_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            body = self._pdf_with_text("Annual Report")
            first = self._cached_pdf_record(directory, body)
            self.assertEqual(first["extraction_status"], "success")
            self.assertEqual(first["title"], "report")
            content = Path(directory) / first["content_path"]
            self.assertIn("Annual Report", content.read_text(encoding="utf-8"))
            initial_mtime = content.stat().st_mtime_ns
            second = self._cached_pdf_record(directory, body)
            self.assertEqual(second["content_path"], first["content_path"])
            self.assertEqual(content.stat().st_mtime_ns, initial_mtime)

    def test_cached_pdf_reextracts_when_raw_hash_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self._cached_pdf_record(directory, self._pdf_with_text("First"))
            second = self._cached_pdf_record(directory, self._pdf_with_text("Second"))
            self.assertEqual(first["extraction_status"], "success")
            self.assertEqual(second["extraction_status"], "success")
            self.assertNotEqual(first["content_path"], second["content_path"])
            self.assertIn("Second", (Path(directory) / second["content_path"]).read_text(encoding="utf-8"))

    def test_cached_scanned_pdf_requires_ocr(self):
        with tempfile.TemporaryDirectory() as directory:
            record = self._cached_pdf_record(directory, self._pdf_with_text(""))
        self.assertEqual(record["extraction_status"], "failed")
        self.assertIn("OCR", record["error"])

    def test_cached_pdf_redirect_to_unregistered_host_never_extracts_or_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(collector, "extract_pdf", wraps=collector.extract_pdf) as extract:
                record = self._cached_pdf_record(
                    directory, self._pdf_with_text("Private"), final_url="https://example.com/report.pdf",
                )
        self.assertEqual(record["extraction_status"], "failed")
        self.assertIn("重定向", record["error"])
        extract.assert_not_called()

    def test_pdf_text_cache_reuses_shared_raw_cache_across_evidence_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / ".cache" / "policies" / "annual.bin"
            raw.parent.mkdir(parents=True)
            body = self._pdf_with_text("Annual Report")
            raw.write_bytes(body)
            digest = hashlib.sha256(body).hexdigest()
            with patch.object(collector, "extract_pdf", wraps=collector.extract_pdf) as extract:
                first, error = collector._cached_pdf_content(raw, digest, root / "topic-a")
                second, second_error = collector._cached_pdf_content(raw, digest, root / "topic-b")
            self.assertEqual(error, "")
            self.assertEqual(second_error, "")
            self.assertEqual(first, second)
            self.assertEqual(extract.call_count, 1)
            self.assertTrue((root / "topic-a" / first).is_file())
            self.assertTrue((root / "topic-b" / second).is_file())

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
