import copy
import hashlib
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

LEGAL_ENTITY = "上海飞科电器股份有限公司"
CAPTURED_AT = "2026-08-08T10:30:00+08:00"


def web_capture():
    return {
        "legal_entity": LEGAL_ENTITY,
        "unified_social_credit_code": "91310000735470911B",
        "registration_status": "存续",
        "page_url": "https://www.qcc.com/firm/example.html",
        "page_locator": "企业详情页：工商信息、股东信息、实际控制人、主要人员及变更记录",
        "captured_at": CAPTURED_AT,
        "data_as_of": "2026-08-08",
        "records": [
            {
                "record_type": "current_shareholder",
                "entity_name": "上海飞科投资有限公司",
                "entity_type": "企业股东",
                "shareholding_ratio": "80.99%",
                "data_as_of": "2026-08-08",
                "page_locator": "股东信息第1行",
                "assertion_type": "registry_fact",
            },
            {
                "record_type": "current_shareholder",
                "entity_name": "其他登记股东",
                "entity_type": "企业股东",
                "shareholding_ratio": "页面未披露",
                "data_as_of": "2026-08-08",
                "page_locator": "股东信息第2行，页面未显示持股比例",
                "assertion_type": "registry_fact",
            },
            {
                "record_type": "actual_controller",
                "entity_name": "李丐腾",
                "entity_type": "自然人",
                "relationship": "平台穿透推定实际控制人",
                "data_as_of": "2026-08-08",
                "page_locator": "股权穿透图/实际控制人",
                "assertion_type": "provider_calculation",
            },
            {
                "record_type": "subsidiary",
                "entity_name": "芜湖飞科电器有限公司",
                "entity_type": "主要子公司",
                "data_as_of": "2026-08-08",
                "page_locator": "对外投资第1行",
                "assertion_type": "registry_fact",
            },
            {
                "record_type": "historical_change",
                "entity_name": "历史股东甲",
                "entity_type": "历史股东",
                "relationship": "历史股东（2024-01-01变更退出）",
                "data_as_of": "2024-01-01",
                "page_locator": "变更记录：股东变更第1条",
                "assertion_type": "registry_fact",
            },
        ],
        "coverage_dispositions": {
            "company_identity": {"status": "captured"},
            "current_shareholder": {"status": "captured"},
            "controller_or_beneficial_owner": {"status": "captured"},
            "historical_change": {"status": "captured"},
            "major_subsidiary": {"status": "captured"},
        },
    }


class EquityWebCaptureContractTests(unittest.TestCase):
    def run_collector(self, provider, payload):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            capture_path = root / "capture.json"
            out_dir = root / "out"
            capture_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(ROOT / "scripts" / "collect_equity_provider.py"),
                    LEGAL_ENTITY,
                    "--provider",
                    provider.replace("_", "-"),
                    "--input-json",
                    str(capture_path),
                    "--out-dir",
                    str(out_dir),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            outputs = {
                path.name: json.loads(path.read_text(encoding="utf-8"))
                for path in out_dir.glob("*.json")
            } if out_dir.exists() else {}
            return result, outputs

    def assert_normalized_fragment(self, provider, fragment):
        self.assertEqual(fragment["provider"], provider)
        self.assertEqual(fragment["legal_entity"], LEGAL_ENTITY)
        self.assertEqual(fragment["captured_at"], CAPTURED_AT)
        self.assertEqual(fragment["source"]["provider"], provider)
        self.assertEqual(fragment["source"]["record_count"], 5)
        self.assertTrue(fragment["nodes"])
        self.assertTrue(fragment["edges"])
        for item in fragment["nodes"] + fragment["edges"]:
            self.assertEqual(item["source_id"], fragment["source"]["id"])
            self.assertTrue(item["assertion_type"])
            self.assertTrue(item["as_of_date"])
            self.assertTrue(item["record_locator"])

        controller = next(edge for edge in fragment["edges"] if "实际控制人" in edge["relationship"])
        self.assertEqual(controller["assertion_type"], "provider_calculation")
        self.assertTrue(any(marker in controller["relationship"] for marker in ("推定", "疑似", "平台穿透")))

        unknown_ratio = next(edge for edge in fragment["edges"] if edge.get("entity_name") == "其他登记股东")
        self.assertEqual(unknown_ratio["shareholding_ratio"], "页面未披露")

    def test_qcc_web_capture_generates_query_bundle_and_normalized_fragment(self):
        result, outputs = self.run_collector("qcc_web", web_capture())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("provider-query-bundle.json", outputs)
        self.assertIn("normalized-equity-fragment.json", outputs)
        self.assert_normalized_fragment("qcc_web", outputs["normalized-equity-fragment.json"])

    def test_tianyancha_web_uses_the_same_normalization_contract(self):
        payload = web_capture()
        payload["page_url"] = "https://www.tianyancha.com/company/example"
        result, outputs = self.run_collector("tianyancha_web", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("provider-query-bundle.json", outputs)
        self.assertIn("normalized-equity-fragment.json", outputs)
        self.assert_normalized_fragment("tianyancha_web", outputs["normalized-equity-fragment.json"])

    def test_required_capture_fields_and_nonempty_records_fail_closed(self):
        for field in ("page_url", "captured_at", "legal_entity", "records"):
            with self.subTest(field=field):
                payload = web_capture()
                payload.pop(field)
                result, _ = self.run_collector("qcc_web", payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(field, result.stderr)

        payload = web_capture()
        payload["records"] = []
        result, _ = self.run_collector("qcc_web", payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("records", result.stderr)

    def test_capture_requires_all_coverage_dispositions(self):
        cases = {
            "only_historical_change": lambda payload: payload.update({
                "records": [record for record in payload["records"] if record["record_type"] == "historical_change"],
                "coverage_dispositions": {"historical_change": {"status": "captured"}},
            }),
            "missing_current_shareholder": lambda payload: payload.update({
                "records": [record for record in payload["records"] if record["record_type"] != "current_shareholder"],
                "coverage_dispositions": {**payload["coverage_dispositions"], "current_shareholder": {"status": "not_disclosed", "reason": "页面未披露"}},
            }),
            "missing_non_captured_disposition": lambda payload: payload.update({
                "records": [record for record in payload["records"] if record["record_type"] not in {"actual_controller", "subsidiary", "historical_change"}],
                "coverage_dispositions": {
                    "company_identity": {"status": "captured"},
                    "current_shareholder": {"status": "captured"},
                },
            }),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                payload = web_capture()
                mutate(payload)
                result, _ = self.run_collector("qcc_web", payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("coverage_dispositions", result.stderr)

    def test_current_shareholder_requires_explicit_ratio_field(self):
        payload = web_capture()
        payload["records"][0].pop("shareholding_ratio")
        result, _ = self.run_collector("qcc_web", payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shareholding_ratio", result.stderr)

    def test_provider_requires_its_own_https_domain(self):
        cases = (("qcc_web", "https://www.tianyancha.com/company/example"), ("qcc_web", "http://www.qcc.com/firm/example"), ("qcc_web", "https://example.com/firm/example"), ("tianyancha_web", "https://www.qcc.com/firm/example"))
        for provider, page_url in cases:
            with self.subTest(provider=provider, page_url=page_url):
                payload = web_capture()
                payload["page_url"] = page_url
                result, _ = self.run_collector(provider, payload)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("URL", result.stderr)

    def test_outputs_bind_capture_and_bundle_hashes(self):
        result, outputs = self.run_collector("qcc_web", web_capture())
        self.assertEqual(result.returncode, 0, result.stderr)
        bundle = outputs["provider-query-bundle.json"]
        fragment = outputs["normalized-equity-fragment.json"]
        capture = outputs["qcc_web-capture.json"]
        capture_sha256 = hashlib.sha256(json.dumps(capture, ensure_ascii=False, indent=2).encode("utf-8") + b"\n").hexdigest()
        call = bundle["calls"][0]
        for field in ("capture_path", "capture_sha256", "record_count", "legal_entity", "captured_at", "page_url"):
            self.assertIn(field, call)
        self.assertEqual(call["capture_sha256"], capture_sha256)
        for field in ("capture_path", "capture_sha256", "record_count", "legal_entity", "captured_at", "page_url", "bundle_path", "bundle_sha256"):
            self.assertIn(field, fragment["source"])

    def test_capture_legal_entity_must_match_command_anchor(self):
        payload = web_capture()
        payload["legal_entity"] = "上海飞科个人护理电器有限公司"
        result, _ = self.run_collector("qcc_web", payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("主体", result.stderr)
        self.assertIn("不一致", result.stderr)

    def test_provider_calculation_requires_qualified_relationship(self):
        payload = web_capture()
        payload["records"][2]["relationship"] = "实际控制人"
        result, _ = self.run_collector("qcc_web", payload)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("推定", result.stderr)

    def test_runtime_files_remove_unsupported_routes_but_keep_web_evidence(self):
        runtime_files = [
            ROOT / "SKILL.md",
            *sorted((ROOT / "references").glob("*.md")),
            *sorted((ROOT / "schemas").glob("*.json")),
            *sorted((ROOT / "scripts").glob("*.py")),
            *sorted((ROOT / "examples").glob("*.json")),
        ]
        corpus = "\n".join(path.read_text(encoding="utf-8-sig") for path in runtime_files)
        forbidden = (
            "qcc_mcp",
            "qcc_cli",
            "qcc_api",
            "qcc-company",
            "get_company_by_query",
            "get_shareholder_info",
            "tianyancha_api",
            "TYC_API_TOKEN",
            "企查查 MCP",
            "企查查 CLI",
            "天眼查 API",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, corpus)
        for marker in ("qcc_web", "tianyancha_web", "企查查网页", "天眼查网页"):
            with self.subTest(marker=marker):
                self.assertIn(marker, corpus)

    def test_web_capture_schema_is_registered_for_preflight(self):
        schema_path = ROOT / "schemas" / "equity-web-capture.schema.json"
        self.assertTrue(schema_path.is_file())
        preflight = (ROOT / "scripts" / "preflight.py").read_text(encoding="utf-8")
        self.assertIn("schemas/equity-web-capture.schema.json", preflight)

    def test_valid_web_capture_example_is_packaged_and_collectible(self):
        example_path = ROOT / "examples" / "equity-web-capture-valid.json"
        self.assertTrue(example_path.is_file(), "缺少合规网页取证示例")
        payload = json.loads(example_path.read_text(encoding="utf-8"))
        result, _ = self.run_collector("qcc_web", payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        preflight = (ROOT / "scripts" / "preflight.py").read_text(encoding="utf-8")
        self.assertIn("examples/equity-web-capture-valid.json", preflight)


if __name__ == "__main__":
    unittest.main()
