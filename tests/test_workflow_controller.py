from __future__ import annotations

import json
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class WorkflowControllerTests(unittest.TestCase):
    def test_resume_preserves_evidence_and_rejects_old_final_approval(self):
        import ppa
        import workflow_state
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_state.create(root, "企业", "old")
            findings = self._enterprise_input("企业")
            (root / "enterprise-findings.json").write_text(json.dumps(findings, ensure_ascii=False), encoding="utf-8")
            (root / "policy-findings.json").write_text('{"evidence": "preserve"}', encoding="utf-8")
            evidence = root / "original.pdf"
            evidence.write_bytes(b"original evidence")
            with patch.object(ppa, "package_fingerprint", return_value="new"):
                self.assertEqual(ppa.main(["resume", "--work-dir", str(root)]), 0)
            state = workflow_state.load(root)
            self.assertEqual(state["skill_fingerprint"], "new")
            self.assertEqual(state["ready_artifact_hashes"], {})
            self.assertEqual(evidence.read_bytes(), b"original evidence")
            self.assertEqual((root / "policy-findings.json").read_text(), '{"evidence": "preserve"}')
            self.assertTrue((root / "workflow-state.before-resume-old.json").exists())

    def _enterprise_input(self, enterprise: str, *, landing: bool = True) -> dict:
        import init_report_workspace

        findings = init_report_workspace.build_findings(enterprise)["enterprise-findings.json"]
        findings["sources"] = [{"key": "catalog", "type": "industry_catalog", "name": "官方目录"}, {"key": "annual", "type": "annual_report", "name": "年度报告"}]
        findings["report"] = {
            "entity_resolution": {"name_type": "legal_entity", "legal_entity": enterprise, "analysis_entity": enterprise, "financial_scope": enterprise, "risk_scope": enterprise},
            "businesses": [{"key": "b1", "segment": "贸易"}],
            "financials": [{"year": "2023"}, {"year": "2024"}, {"year": "2025"}],
            "encouraged_industry_assessment": {"catalog_version": "v1", "catalogs_checked": [{"catalog_scope": "hainan_added_2024", "status": "checked", "source_key": "catalog"}], "business_assessments": [{"business_id": "B01"}]},
            "landing_businesses": ([{"key": "l1", "business": "贸易结算", "fact_basis": "公开业务", "sanya_path": "设立贸易结算主体", "value": "结算", "feasibility": "可行", "policy_departments": ["商务"]}] if landing else []),
        }
        findings["research"] = {
            "enterprise_profile": {"analysis_entity": enterprise, "listing_status": "listed", "research_route": "listed_disclosure"},
            "facts": [{"key": "f1", "action": "境内外贸易", "object": "产品", "enterprise_role": "销售方", "confidence": "high", "source_keys": ["annual"]}],
            "business_candidates": [{"key": "bc1", "name": "贸易结算", "fact_keys": ["f1"]}],
        }
        return findings

    def test_prepare_enterprise_is_policy_independent_and_reaches_discovery_fetch(self):
        import ppa
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "company"
            with patch.object(ppa, "require_ready_runtime", return_value={"fingerprint": "tested"}), patch.object(ppa, "package_fingerprint", return_value="tested"):
                ppa.main(["start", "测试企业有限公司", "--work-dir", str(work_dir)])
                (work_dir / "enterprise-findings.json").write_text(json.dumps(self._enterprise_input("测试企业有限公司"), ensure_ascii=False), encoding="utf-8")
                self.assertEqual(ppa.main(["prepare-enterprise", "--work-dir", str(work_dir)]), 0)
                self.assertEqual(workflow_state.load(work_dir)["current_stage"], "landing_businesses_complete")
                self.assertEqual(json.loads((work_dir / "policy-findings.json").read_text(encoding="utf-8"))["researched_at"], "")
                fake_policy_module = types.SimpleNamespace(
                    discover_current_policies=unittest.mock.Mock(return_value={"metrics": {"failed_requests": 0}}),
                    merge_discovery_fragment=unittest.mock.Mock(),
                )
                with patch.dict(sys.modules, {"discover_current_policies": fake_policy_module}):
                        self.assertEqual(ppa.main(["discover-policies", "--work-dir", str(work_dir)]), 0)
                fake_policy_module.discover_current_policies.assert_called_once()

    def test_prepare_missing_landing_fails_without_stage_success(self):
        import ppa
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "company"
            with patch.object(ppa, "require_ready_runtime", return_value={"fingerprint": "tested"}), patch.object(ppa, "package_fingerprint", return_value="tested"):
                ppa.main(["start", "测试企业有限公司", "--work-dir", str(work_dir)])
                (work_dir / "enterprise-findings.json").write_text(json.dumps(self._enterprise_input("测试企业有限公司", landing=False), ensure_ascii=False), encoding="utf-8")
                self.assertEqual(ppa.main(["prepare-enterprise", "--work-dir", str(work_dir)]), 1)
                self.assertEqual(workflow_state.load(work_dir)["current_stage"], "environment_ready")

    def test_discovery_rejects_changed_enterprise_input(self):
        import ppa
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "company"
            with patch.object(ppa, "require_ready_runtime", return_value={"fingerprint": "tested"}), patch.object(ppa, "package_fingerprint", return_value="tested"):
                ppa.main(["start", "测试企业有限公司", "--work-dir", str(work_dir)])
                (work_dir / "enterprise-findings.json").write_text(json.dumps(self._enterprise_input("测试企业有限公司"), ensure_ascii=False), encoding="utf-8")
                ppa.main(["prepare-enterprise", "--work-dir", str(work_dir)])
                (work_dir / "enterprise-findings.json").write_text((work_dir / "enterprise-findings.json").read_text(encoding="utf-8") + "\n", encoding="utf-8")
                self.assertEqual(ppa.main(["discover-policies", "--work-dir", str(work_dir)]), 1)
                self.assertEqual(workflow_state.load(work_dir)["current_stage"], "landing_businesses_complete")

    def test_compile_then_same_prepare_preserves_policy_judgment(self):
        import ppa
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "company"
            with patch.object(ppa, "require_ready_runtime", return_value={"fingerprint": "tested"}), patch.object(ppa, "package_fingerprint", return_value="tested"):
                ppa.main(["start", "测试企业有限公司", "--work-dir", str(work_dir)])
                (work_dir / "enterprise-findings.json").write_text(json.dumps(self._enterprise_input("测试企业有限公司"), ensure_ascii=False), encoding="utf-8")
                ppa.main(["prepare-enterprise", "--work-dir", str(work_dir)])
                policy = json.loads((work_dir / "policy-findings.json").read_text(encoding="utf-8"))
                policy["researched_at"] = "2026-09-15T10:00:00+08:00"
                policy["sources"] = [{"key": "policy-source", "type": "policy", "name": "政策原文"}]
                policy["policy_records"] = [{"key": "policy-judgment", "source_keys": ["policy-source"], "search_keys": [], "fact_keys": [], "landing_business_keys": ["l1"], "topic": "贸易", "match_reason": "保留", "eligibility_status": "unknown", "disposition": "conditional", "conditions": "待核", "handling_route": "待核", "report_group": "g", "policy": {"name": "保留政策", "region": "海南", "region_evidence": "原文", "source_type": "official", "source_url": "https://example.com/policy", "status": "current", "enterprise_business": "贸易", "landing_action": "待核"}}]
                (work_dir / "policy-findings.json").write_text(json.dumps(policy, ensure_ascii=False), encoding="utf-8")
                ppa.main(["compile", "--work-dir", str(work_dir)])
                before = json.loads((work_dir / "report-data.json").read_text(encoding="utf-8"))["policy_research"]
                self.assertEqual(ppa.main(["prepare-enterprise", "--work-dir", str(work_dir)]), 0)
                after = json.loads((work_dir / "report-data.json").read_text(encoding="utf-8"))["policy_research"]
                self.assertEqual(after, before)
                self.assertEqual(workflow_state.load(work_dir)["current_stage"], "landing_businesses_complete")

    def test_agent_instructions_use_lean_inputs_and_single_final_gate(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        combined = skill + "\n" + agents
        self.assertIn("enterprise-findings.json", combined)
        self.assertIn("policy-findings.json", combined)
        self.assertIn("ppa.py compile", combined)
        self.assertIn("ppa.py finalize", combined)
        self.assertNotIn("研究人员填充五份台账", combined)
        self.assertNotIn("下一步：完成主体确认后运行 ppa.py advance", combined)

    def test_public_cli_exposes_one_setup_and_report_entry(self):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "ppa.py"), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for command in (
            "setup", "start", "status", "advance", "collect-web",
            "collect-equity", "search-catalog", "discover-policies", "research-plan", "compile", "finalize", "deliver",
        ):
            self.assertIn(command, result.stdout)

    def test_start_creates_five_ledgers_and_machine_state(self):
        import ppa

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp) / "company"
            with patch.object(ppa, "require_ready_runtime", return_value={"fingerprint": "tested"}):
                result = ppa.main(["start", "测试企业有限公司", "--work-dir", str(work_dir)])
            self.assertEqual(result, 0)
            self.assertEqual(
                {path.name for path in work_dir.iterdir()},
                {
                    "report-data.json",
                    "equity-evidence.json",
                    "research-ledger.json",
                    "policy-search-ledger.json",
                    "policy-evidence.json",
                    "enterprise-findings.json",
                    "policy-findings.json",
                    "workflow-state.json",
                },
            )
            state = json.loads((work_dir / "workflow-state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["current_stage"], "environment_ready")
            self.assertTrue(state["run_id"])
            self.assertEqual(state["enterprise"], "测试企业有限公司")

    def test_stage_order_cannot_be_skipped(self):
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            workflow_state.create(work_dir, "测试企业有限公司", "fingerprint")
            with self.assertRaisesRegex(ValueError, "下一阶段"):
                workflow_state.complete_stage(work_dir, "enterprise_research_complete", {})

    def test_ready_receipt_detects_any_ledger_change(self):
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            for name in workflow_state.REPORT_ARTIFACTS:
                (work_dir / name).write_text("{}\n", encoding="utf-8")
            state = workflow_state.create(work_dir, "测试企业有限公司", "fingerprint")
            state["current_stage"] = "policy_research_complete"
            state["completed_stages"] = workflow_state.STAGES[: workflow_state.STAGES.index("policy_research_complete") + 1]
            workflow_state.save(work_dir, state)
            workflow_state.complete_stage(work_dir, "report_ready", workflow_state.artifact_hashes(work_dir))
            self.assertEqual(workflow_state.ready_state_errors(work_dir, "fingerprint"), [])
            (work_dir / "report-data.json").write_text('{"changed": true}\n', encoding="utf-8")
            self.assertTrue(any("发生变化" in message for message in workflow_state.ready_state_errors(work_dir, "fingerprint")))

    def test_ready_receipt_rejects_tampered_stage_history(self):
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            for name in workflow_state.REPORT_ARTIFACTS:
                (work_dir / name).write_text("{}\n", encoding="utf-8")
            state = workflow_state.create(work_dir, "测试企业有限公司", "fingerprint")
            state["current_stage"] = "report_ready"
            state["completed_stages"] = ["environment_ready", "report_ready"]
            state["ready_artifact_hashes"] = workflow_state.artifact_hashes(work_dir)
            workflow_state.save(work_dir, state)
            self.assertTrue(any("阶段记录" in message for message in workflow_state.ready_state_errors(work_dir, "fingerprint")))

    def test_formal_artifact_paths_must_use_canonical_names(self):
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            supplied = {name: work_dir / name for name in workflow_state.REPORT_ARTIFACTS}
            supplied["report-data.json"] = work_dir / "alternate-report.json"
            self.assertTrue(workflow_state.artifact_path_errors(work_dir, supplied))

    def test_runtime_can_resolve_playwright_owned_chromium(self):
        import runtime_state

        with tempfile.TemporaryDirectory() as tmp:
            browser = Path(tmp) / "chromium.exe"
            browser.write_text("placeholder", encoding="utf-8")

            class Result:
                returncode = 0
                stdout = str(browser)

            with patch.object(runtime_state.subprocess, "run", return_value=Result()):
                resolved = runtime_state.resolve_playwright_chromium(Path(tmp) / "node.exe", Path(tmp) / "node_modules")
            self.assertEqual(resolved, browser.resolve())

    def test_setup_plan_installs_project_runtime_once_and_word_only_on_request(self):
        import ppa

        node = Path("C:/runtime/node.exe")
        commands = ppa.setup_commands(node=node, with_word=False)
        flattened = [" ".join(str(part) for part in command) for command in commands]
        self.assertTrue(any("npm" in command and "ci" in command for command in flattened))
        self.assertTrue(any("playwright" in command and "install" in command and "chromium" in command for command in flattened))
        self.assertFalse(any("requirements-word.txt" in command for command in flattened))
        # Word 已改为纯标准库生成（stdlib_docx），不再依赖 python-docx / requirements-word.txt
        word_commands = ppa.setup_commands(node=node, with_word=True)
        self.assertFalse(any("requirements-word.txt" in " ".join(str(part) for part in command) for command in word_commands))

    def test_setup_does_not_reuse_stale_receipt_when_runtime_is_missing(self):
        import ppa

        args = argparse.Namespace(force=False, with_word=False, node=None, npm=None, chrome=None)
        receipt = {"verified": True, "fingerprint": "same", "node": {"path": "missing-node"}, "chrome": {"path": "missing-chrome"}}
        with patch.object(ppa, "load_verified_state", return_value=receipt), patch.object(ppa, "state_is_current", return_value=True), patch.object(ppa, "check_runtime", return_value=({}, ["runtime missing"])), patch.object(ppa, "resolve_node", return_value=None):
            with self.assertRaisesRegex(ValueError, "Node.js"):
                ppa.command_setup(args)

    def test_agent_instructions_expose_only_the_controller_as_public_entry(self):
        instructions = "\n".join(
            path.read_text(encoding="utf-8-sig")
            for path in (ROOT / "SKILL.md", ROOT / "AGENTS.md", *sorted((ROOT / "references").glob("*.md")))
        )
        self.assertIn("scripts/ppa.py", instructions)
        import re

        public_commands = re.findall(r"(?:&\s+\S+|python(?:\.exe)?)\s+(?:-X\s+utf8\s+)?scripts/([\w.-]+\.py)", instructions)
        self.assertTrue(public_commands)
        self.assertEqual(set(public_commands), {"ppa.py"})

    def test_advance_continues_across_ready_stages_until_report_ready(self):
        import ppa
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            workflow_state.create(work_dir, "测试企业有限公司", "fingerprint")
            for name in workflow_state.REPORT_ARTIFACTS:
                (work_dir / name).write_text("{}\n", encoding="utf-8")
            args = argparse.Namespace(work_dir=str(work_dir), node=None, chrome=None)
            hashes = workflow_state.artifact_hashes(work_dir)
            for name in ("enterprise-findings.json", "policy-findings.json"):
                (work_dir / name).write_text("{}", encoding="utf-8")
            bound_state = workflow_state.load(work_dir)
            bound_state["findings_input_sha256"] = {
                "enterprise": ppa._file_sha256(work_dir / "enterprise-findings.json"),
                "policy": ppa._file_sha256(work_dir / "policy-findings.json"),
            }
            workflow_state.save(work_dir, bound_state)
            with patch.object(ppa, "require_ready_runtime"), patch.object(ppa, "package_fingerprint", return_value="fingerprint"), patch.object(ppa, "_validate_lightweight_stage", return_value={"compiled": True}) as light, patch.object(ppa, "_validate_final_suite", return_value=hashes) as final:
                result = ppa.command_advance(args)
            self.assertEqual(result, 0)
            self.assertEqual(workflow_state.load(work_dir)["current_stage"], "report_ready")
            self.assertEqual(light.call_count, 6)
            self.assertEqual(final.call_count, 1)

    def test_packaged_runtime_is_locked_and_not_described_as_optional(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertNotIn("optional", package["description"].lower())
        self.assertTrue((ROOT / "package-lock.json").is_file())

    def test_final_coverage_gate_receives_policy_evidence_for_documented_fallbacks(self):
        import ppa
        import workflow_state

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            for name in workflow_state.REPORT_ARTIFACTS:
                (work_dir / name).write_text("{}\n", encoding="utf-8")
            with patch.object(ppa, "_validator_errors", return_value=[]) as validate:
                ppa._validate_final_suite(work_dir)
            coverage = next(arguments for arguments in (call.args for call in validate.call_args_list) if arguments[0] == "validate_policy_search_coverage.py")
            self.assertIn("--policy-evidence", coverage)
            self.assertIn(str(work_dir / "policy-evidence.json"), coverage)


if __name__ == "__main__":
    unittest.main()
