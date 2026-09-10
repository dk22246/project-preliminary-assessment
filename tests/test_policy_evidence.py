import copy
from datetime import datetime, timezone
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_policy_evidence import validate_policy_evidence


NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def report():
    return {
        "meta": {"policy_researched_at": NOW, "policy_search_mode": "realtime"},
        "policies": [{"name": "企业所得税15%优惠", "source_id": "P01"}],
        "sources": [{
            "id": "P01", "type": "正式政策", "name": "海南自由贸易港企业所得税优惠政策",
            "issuer": "国家税务总局海南省税务局",
            "location": "https://hainan.chinatax.gov.cn/policy/15percent.html",
        }],
    }


def policy_search_ledger(status="current_conditional"):
    return {"policy_candidates": [{"id": "PC01", "formal_policy_source_ids": ["P01"], "status": status}]}


def evidence(directory: Path, *, final_url="https://hainan.chinatax.gov.cn/policy/15percent.html", status="current", fixture=False, content_type="text/html"):
    artifact = directory / "artifacts" / "PE01.html"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("<html>official policy</html>", encoding="utf-8")
    record = {
        "id": "PE01", "policy_source_id": "P01",
        "requested_url": "https://hainan.chinatax.gov.cn/policy/15percent.html",
        "final_url": final_url, "retrieved_at": NOW, "http_status": 200,
        "content_type": content_type, "artifact_path": "artifacts/PE01.html",
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "issuer": "国家税务总局海南省税务局", "title": "海南自由贸易港企业所得税优惠政策",
        "document_number": "无文号说明", "published_at": "2025-01-01",
        "validity_status": status, "validity_basis": "正文明确规定政策仍在执行期内",
        "validity_locator": "正文第1条", "application_status": "not_application_based",
        "application_basis": "税收优惠按规定申报享受", "application_locator": "正文第2条",
    }
    payload = {"version": "1.0", "enterprise": "测试企业", "researched_at": NOW, "mode": "formal", "records": [record]}
    if fixture:
        payload["fixture_metadata"] = {"fixture_only": True, "fixture_name": "test"}
    return payload


class PolicyEvidenceTests(unittest.TestCase):
    def test_explicit_fixture_mode_does_not_expire_packaged_release_evidence(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory, fixture=True)
            payload.update({"mode": "fixture", "researched_at": "2020-01-01T00:00:00+00:00"})
            payload["records"][0]["retrieved_at"] = "2020-01-01T00:00:00+00:00"
            fixture_report = report()
            fixture_report["meta"]["policy_researched_at"] = payload["researched_at"]
            errors = validate_policy_evidence(
                payload,
                fixture_report,
                policy_search_ledger(),
                base_dir=directory,
                allow_fixture=True,
            )
            self.assertFalse(any("24小时" in item for item in errors), errors)

    def validate(self, payload, directory, *, ledger=None):
        return validate_policy_evidence(payload, report(), ledger or policy_search_ledger(), base_dir=directory)

    def test_valid_html_evidence_passes(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            self.assertEqual(self.validate(evidence(directory), directory), [])

    def test_policy_without_evidence_fails(self):
        with tempfile.TemporaryDirectory() as value:
            self.assertTrue(any("P01" in item and "取证" in item for item in self.validate({"version": "1.0", "enterprise": "测试企业", "researched_at": NOW, "mode": "formal", "records": []}, Path(value))))

    def test_url_and_time_without_artifact_and_hash_fails(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory)
            payload["records"][0].pop("artifact_path")
            payload["records"][0].pop("artifact_sha256")
            self.assertTrue(any("artifact" in item for item in self.validate(payload, directory)))

    def test_stale_evidence_fails(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory)
            payload["records"][0]["retrieved_at"] = "2020-01-01T00:00:00+00:00"
            self.assertTrue(any("24小时" in item for item in self.validate(payload, directory)))

    def test_non_official_domain_fails(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory, final_url="https://example.com/policy")
            self.assertTrue(any("官方" in item for item in self.validate(payload, directory)))

    def test_missing_or_mismatched_artifact_hash_fails(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory)
            payload["records"][0]["artifact_sha256"] = "0" * 64
            self.assertTrue(any("SHA256" in item for item in self.validate(payload, directory)))

    def test_formal_mode_rejects_fixture_metadata(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            self.assertTrue(any("fixture" in item.lower() for item in self.validate(evidence(directory, fixture=True), directory)))

    def test_pdf_evidence_can_support_policy(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory, content_type="application/pdf")
            self.assertEqual(self.validate(payload, directory), [])

    def test_expired_policy_cannot_support_frontend_card(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory, status="expired")
            self.assertTrue(any("现行" in item for item in self.validate(payload, directory, ledger=policy_search_ledger("expired_relevant"))))

    def test_one_policy_can_have_multiple_current_evidence_records(self):
        with tempfile.TemporaryDirectory() as value:
            directory = Path(value)
            payload = evidence(directory)
            extra = copy.deepcopy(payload["records"][0])
            extra["id"] = "PE02"
            extra["document_number"] = "实施细则第2号"
            payload["records"].append(extra)
            self.assertEqual(self.validate(payload, directory), [])


if __name__ == "__main__":
    unittest.main()
