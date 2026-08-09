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

from report_core import validate_report_data


REPORT = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8"))


def evidence_ledger():
    return {
        "schema_version": "1.0",
        "subject": {
            "legal_entity": REPORT["entity_resolution"]["legal_entity"],
            "unified_social_credit_code": "91310000735470911B",
        },
        "provider_attempts": [
            {"provider": "qcc_web", "status": "success", "queried_at": "2026-08-02T12:00:00+08:00"},
            {"provider": "tianyancha_web", "status": "unavailable", "queried_at": "2026-08-02T12:01:00+08:00", "reason": "网页访问受登录状态限制"},
        ],
        "sources": [
            {
                "id": "E01",
                "provider": "qcc_web",
                "method": "browser_capture",
                "queried_at": "2026-08-02T12:00:00+08:00",
                "query": REPORT["entity_resolution"]["legal_entity"],
                "status": "success",
                "record_locator": "企查查企业详情页/股东信息",
                "page_url": "https://www.qcc.com/firm/example.html",
                "captured_at": "2026-08-02T12:00:00+08:00",
                "record_count": 1,
            }
        ],
        "nodes": [],
        "edges": [],
        "conflicts": [],
        "review_status": "complete",
    }


def attach_graph(ledger, report):
    sync_summary(ledger, report)
    ledger["nodes"] = [
        {
            "id": node["id"],
            "name": node["name"],
            "entity_type": node["entity_type"],
            "assertion_type": "registry_fact",
            "as_of_date": "2026-08-02",
            "evidence_source_ids": ["E01"],
        }
        for node in report["equity"]["nodes"]
    ]
    ledger["edges"] = [
        {
            "from": edge["from"],
            "to": edge["to"],
            "relationship": edge["relationship"],
            "assertion_type": "registry_fact",
            "as_of_date": "2026-08-02",
            "evidence_source_ids": ["E01"],
        }
        for edge in report["equity"]["edges"]
    ]


def sync_summary(ledger, report):
    source = next(item for item in ledger["sources"] if item["status"] == "success")
    report["equity"]["evidence_summary"] = {
        "display_source_id": source["id"],
        "display_source_title": "测试证据台账中的成功来源",
        "as_of_date": "2026-08-02",
    }


def write_web_artifact_chain(directory, ledger, *, corrupt_hash=False, mutate_capture=None):
    capture = json.loads((ROOT / "examples" / "equity-web-capture-valid.json").read_text(encoding="utf-8"))
    if mutate_capture:
        mutate_capture(capture)
    capture_path = directory / "qcc_web-capture.json"
    capture_path.write_text(json.dumps(capture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    capture_sha256 = hashlib.sha256(capture_path.read_bytes()).hexdigest()
    bundle = {
        "provider": "qcc_web",
        "legal_entity": capture["legal_entity"],
        "calls": [{
            "capture_path": capture_path.name,
            "capture_sha256": capture_sha256,
            "record_count": len(capture["records"]),
            "legal_entity": capture["legal_entity"],
            "captured_at": capture["captured_at"],
            "page_url": capture["page_url"],
        }],
    }
    bundle_path = directory / "provider-query-bundle.json"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source = ledger["sources"][0]
    source.update({
        "page_url": capture["page_url"],
        "captured_at": capture["captured_at"],
        "record_count": len(capture["records"]),
        "artifact_path": capture_path.name,
        "artifact_sha256": "0" * 64 if corrupt_hash else capture_sha256,
        "bundle_path": bundle_path.name,
        "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
    })


def validate_via_cli(directory, ledger, report):
    ledger_path = directory / "equity-evidence.json"
    report_path = directory / "report-data.json"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "validate_equity_evidence.py"), str(ledger_path), "--report-data", str(report_path)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )


def conflict(conflict_id="C01", severity="general", graph_action="keep_confirmed_part"):
    return {
        "id": conflict_id,
        "field": "shareholding_ratio",
        "severity": severity,
        "status": "unresolved",
        "title": "直接股东持股比例存在差异",
        "difference": "企查查显示60%，天眼查显示55%。",
        "reason": "可能源于数据更新时间或工商变更同步口径不同。",
        "adopted_basis": "本报告仅确认直接股东关系，争议比例不绘入股权图。",
        "impact": "暂不影响主营业务和一般招商价值判断，但影响控制比例认定。",
        "next_action": "需企业补充最新公司章程或工商股东名册。",
        "graph_action": graph_action,
        "affected_node_ids": [],
        "affected_edges": [{"from": REPORT["equity"]["edges"][0]["from"], "to": REPORT["equity"]["edges"][0]["to"]}],
        "evidence_source_ids": ["E01"],
    }


class EquityEvidenceTests(unittest.TestCase):
    def test_report_data_requires_evidence_ids_on_every_equity_node_and_edge(self):
        data = copy.deepcopy(REPORT)
        data["equity"]["nodes"][0].pop("evidence_source_ids")
        data["equity"]["edges"][0].pop("evidence_source_ids")
        errors = validate_report_data(data)
        self.assertTrue(any("股权节点缺少evidence_source_ids" in item for item in errors), errors)
        self.assertTrue(any("股权连接缺少evidence_source_ids" in item for item in errors), errors)

    def test_equity_ledger_must_match_every_rendered_node_and_edge(self):
        try:
            validator = importlib.import_module("validate_equity_evidence")
        except ModuleNotFoundError as error:
            self.fail(f"缺少股权证据校验器：{error}")
        report = copy.deepcopy(REPORT)
        for item in report["equity"]["nodes"] + report["equity"]["edges"]:
            item["evidence_source_ids"] = ["E01"]
        ledger = evidence_ledger()
        sync_summary(ledger, report)
        ledger["nodes"] = [
            {
                "id": node["id"],
                "name": node["name"],
                "entity_type": node["entity_type"],
                "assertion_type": "registry_fact",
                "as_of_date": "2026-08-02",
                "evidence_source_ids": ["E01"],
            }
            for node in report["equity"]["nodes"]
        ]
        ledger["edges"] = [
            {
                "from": edge["from"],
                "to": edge["to"],
                "relationship": edge["relationship"],
                "assertion_type": "registry_fact",
                "as_of_date": "2026-08-02",
                "evidence_source_ids": ["E01"],
            }
            for edge in report["equity"]["edges"]
        ]
        self.assertEqual(validator.validate_equity_evidence(ledger, report), [])
        ledger["edges"].pop()
        errors = validator.validate_equity_evidence(ledger, report)
        self.assertTrue(any("报告股权连接缺少证据台账对应关系" in item for item in errors), errors)

    def test_general_unresolved_conflict_is_disclosed_in_text_without_blocking_report(self):
        try:
            validator = importlib.import_module("validate_equity_evidence")
        except ModuleNotFoundError as error:
            self.fail(f"缺少股权证据校验器：{error}")
        report = copy.deepcopy(REPORT)
        for item in report["equity"]["nodes"] + report["equity"]["edges"]:
            item["evidence_source_ids"] = ["E01"]
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        item = conflict()
        ledger["conflicts"] = [copy.deepcopy(item)]
        ledger["review_status"] = "qualified_complete"
        report["equity"]["conflict_disclosures"] = [copy.deepcopy(item)]
        self.assertEqual(validator.validate_equity_evidence(ledger, report), [])

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report-data.json"
            html_path = Path(directory) / "report.html"
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "render_report_html.py"), str(report_path), "--out", str(html_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            html = html_path.read_text(encoding="utf-8")
            self.assertIn("股权数据差异说明", html)
            self.assertIn(item["difference"], html)
            self.assertLess(html.index("</svg>"), html.index("股权数据差异说明"))

    def test_material_local_conflict_requires_disputed_relation_to_be_omitted_from_graph(self):
        validator = importlib.import_module("validate_equity_evidence")
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        item = conflict(severity="material_local", graph_action="omit_disputed_part")
        ledger["conflicts"] = [copy.deepcopy(item)]
        ledger["review_status"] = "qualified_complete"
        report["equity"]["conflict_disclosures"] = [copy.deepcopy(item)]
        errors = validator.validate_equity_evidence(ledger, report)
        self.assertTrue(any("争议连接仍进入股权图" in error for error in errors), errors)

    def test_subject_critical_conflict_blocks_report_but_calculated_control_remains_separate_error(self):
        validator = importlib.import_module("validate_equity_evidence")
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        ledger["edges"][0]["assertion_type"] = "provider_calculation"
        ledger["edges"][0]["relationship"] = "实际控制"
        item = conflict(severity="subject_critical", graph_action="omit_disputed_part")
        item["field"] = "ultimate_controller"
        ledger["conflicts"] = [copy.deepcopy(item)]
        ledger["review_status"] = "blocked"
        report["equity"]["conflict_disclosures"] = [copy.deepcopy(item)]
        errors = validator.validate_equity_evidence(ledger, report)
        self.assertTrue(any("平台计算关系必须标明推定" in item for item in errors), errors)
        self.assertTrue(any("主体或核心控制关系存在未解决冲突" in item for item in errors), errors)
        self.assertFalse(any("review_status" in item for item in errors), errors)

    def test_conflict_disclosure_is_required_to_match_equity_ledger(self):
        validator = importlib.import_module("validate_equity_evidence")
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        ledger["conflicts"] = [conflict()]
        ledger["review_status"] = "qualified_complete"
        report["equity"]["conflict_disclosures"] = []
        errors = validator.validate_equity_evidence(ledger, report)
        self.assertTrue(any("未进入报告文字说明" in error for error in errors), errors)

    def test_provider_collector_only_exposes_web_routes(self):
        try:
            collector = importlib.import_module("collect_equity_provider")
        except ModuleNotFoundError as error:
            self.fail(f"缺少股权平台采集器：{error}")
        self.assertEqual(collector.WEB_PROVIDERS, {"qcc_web", "tianyancha_web"})

    def test_web_verified_claim_requires_success_receipt_with_nonempty_records(self):
        validator = importlib.import_module("validate_equity_evidence")
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        ledger["sources"][0]["record_count"] = 0
        errors = validator.validate_equity_evidence(ledger, report)
        self.assertTrue(any("股权网页来源" in item and "非空记录" in item for item in errors), errors)

    def test_cli_rejects_success_web_source_without_verifiable_artifact(self):
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            result = validate_via_cli(Path(directory), ledger, report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("artifact", result.stderr)

    def test_cli_rejects_success_web_source_with_mismatched_artifact_hash(self):
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        with tempfile.TemporaryDirectory(dir=ROOT) as raw_directory:
            directory = Path(raw_directory)
            write_web_artifact_chain(directory, ledger, corrupt_hash=True)
            result = validate_via_cli(directory, ledger, report)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256", result.stderr)

    def test_cli_rejects_hash_valid_artifact_that_violates_capture_contract(self):
        def remove_shareholder_field(field):
            def mutate(capture):
                shareholder = next(item for item in capture["records"] if item["record_type"] == "current_shareholder")
                shareholder.pop(field)
            return mutate

        cases = {
            "missing_page_locator": lambda capture: capture.pop("page_locator"),
            "missing_coverage_dispositions": lambda capture: capture.pop("coverage_dispositions"),
            "missing_one_coverage_category": lambda capture: capture["coverage_dispositions"].pop("major_subsidiary"),
            "shareholder_missing_ratio": remove_shareholder_field("shareholding_ratio"),
            "shareholder_missing_locator": remove_shareholder_field("page_locator"),
            "provider_url_mismatch": lambda capture: capture.update({"page_url": "https://www.tianyancha.com/company/example"}),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                report = copy.deepcopy(REPORT)
                ledger = evidence_ledger()
                attach_graph(ledger, report)
                with tempfile.TemporaryDirectory(dir=ROOT) as raw_directory:
                    directory = Path(raw_directory)
                    write_web_artifact_chain(directory, ledger, mutate_capture=mutate)
                    result = validate_via_cli(directory, ledger, report)
                self.assertNotEqual(result.returncode, 0, f"{name} unexpectedly passed")
                self.assertIn("capture", result.stderr.lower())

    def test_cli_accepts_complete_web_artifact_chain(self):
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        with tempfile.TemporaryDirectory(dir=ROOT) as raw_directory:
            directory = Path(raw_directory)
            write_web_artifact_chain(directory, ledger)
            result = validate_via_cli(directory, ledger, report)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicitly_negated_web_verification_claim_is_allowed_for_fallback(self):
        validator = importlib.import_module("validate_equity_evidence")
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        ledger["provider_attempts"] = [
            {"provider": "qcc_web", "status": "unavailable", "queried_at": "2026-08-02T12:00:00+08:00", "reason": "登录态失效"},
            {"provider": "tianyancha_web", "status": "unavailable", "queried_at": "2026-08-02T12:01:00+08:00", "reason": "验证码阻断"},
        ]
        ledger["sources"][0]["provider"] = "legal_disclosure"
        ledger["review_status"] = "fallback_complete"
        attach_graph(ledger, report)
        report["equity"]["evidence_summary"] = {
            "display_source_id": "E01",
            "display_source_title": "上市公司法定披露",
            "as_of_date": "2026-08-02",
        }
        self.assertEqual(validator.validate_equity_evidence(ledger, report), [])

    def test_equity_nodes_require_data_timestamp(self):
        validator = importlib.import_module("validate_equity_evidence")
        report = copy.deepcopy(REPORT)
        ledger = evidence_ledger()
        attach_graph(ledger, report)
        ledger["nodes"][0].pop("as_of_date")
        errors = validator.validate_equity_evidence(ledger, report)
        self.assertTrue(any("股权节点缺少数据时点" in item for item in errors), errors)

    def test_main_pipeline_requires_equity_evidence_before_rendering(self):
        source = (ROOT / "scripts" / "run_report_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--equity-evidence", required=True', source)
        self.assertIn('"validate_equity_evidence.py"', source)
        self.assertLess(source.index('"validate_equity_evidence.py"'), source.index('"render_equity_chart.py"'))

    def test_skill_documents_provider_priority_and_non_overstatement_rules(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        reference_path = ROOT / "references" / "equity-evidence.md"
        self.assertTrue(reference_path.is_file(), "缺少股权证据接入规则")
        reference = reference_path.read_text(encoding="utf-8")
        self.assertIn("企查查网页", skill)
        self.assertIn("equity-evidence.json", skill)
        self.assertIn("不得把平台计算结果直接写成已确认的实际控制人", reference)
        self.assertIn("法定披露优先", reference)


if __name__ == "__main__":
    unittest.main()
