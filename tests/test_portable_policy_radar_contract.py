import copy
import importlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import validate_report_data
from render_report_html import policy_match_table
from runtime_state import capability_errors


REPORT = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8"))


class PortablePolicyRadarContractTests(unittest.TestCase):
    def test_policy_table_has_only_policy_and_reason_columns(self):
        html = policy_match_table(REPORT["policies"])
        self.assertEqual(html.count("<th>"), 2)
        self.assertIn("<th>匹配政策或工具</th>", html)
        self.assertIn("<th>匹配原因</th>", html)
        for removed in ("拟落地业务", "企业能获得什么", "享受前提及三亚承接", "适用定位"):
            self.assertNotIn(f"<th>{removed}</th>", html)

    def test_partial_direct_shareholding_requires_a_remainder_node(self):
        data = copy.deepcopy(REPORT)
        data["equity"]["nodes"] = [
            node for node in data["equity"]["nodes"] if node["id"] != "other_shareholders"
        ]
        data["equity"]["edges"] = [
            edge for edge in data["equity"]["edges"] if edge["from"] != "other_shareholders"
        ]
        errors = validate_report_data(data)
        self.assertTrue(any("股权比例未闭合" in error for error in errors), errors)

    def test_equity_edge_cannot_reference_a_missing_node(self):
        data = copy.deepcopy(REPORT)
        data["equity"]["nodes"] = [
            node for node in data["equity"]["nodes"] if node["id"] != "other_shareholders"
        ]
        errors = validate_report_data(data)
        self.assertTrue(any("股权连接引用不存在节点" in error for error in errors), errors)

    def test_shareholder_edge_cannot_omit_numeric_ownership(self):
        data = copy.deepcopy(REPORT)
        edge = next(edge for edge in data["equity"]["edges"] if edge["from"] == "holding")
        edge["relationship"] = "控股股东持股"
        edge.pop("ownership_percent")
        errors = validate_report_data(data)
        self.assertTrue(any("必须提供ownership_percent" in error for error in errors), errors)

    def test_industry_position_rejects_unqualified_reputation_language(self):
        data = copy.deepcopy(REPORT)
        data["industry_position"] = {
            "statement": "国内个护电器知名品牌",
            "category": "个护电器",
            "position": "知名品牌",
            "period": "2025",
            "source_ids": ["E01"],
        }
        errors = validate_report_data(data)
        self.assertTrue(any("行业地位" in error for error in errors), errors)

    def test_overseas_signal_requires_disposition_for_adjacent_policy_tools(self):
        data = copy.deepcopy(REPORT)
        data["policy_opportunity_radar"] = {
            "signals": [{
                "id": "S01",
                "signal_type": "overseas_business",
                "fact": "企业已有海外产品和渠道布局。",
                "source_ids": ["E01"],
                "opportunities": [{
                    "topic": "ef_account",
                    "disposition": "surfaced",
                    "reason": "海外收付可触发跨境账户工具研究。",
                    "policy_source_ids": ["P06"],
                }],
            }]
        }
        errors = validate_report_data(data)
        self.assertTrue(any("海外业务信号缺少机会处置" in error for error in errors), errors)

    def test_overseas_channel_alias_also_triggers_the_full_radar(self):
        data = copy.deepcopy(REPORT)
        data["policy_opportunity_radar"] = {
            "signals": [{
                "id": "S01",
                "signal_type": "overseas_channel",
                "fact": "企业已有境外渠道。",
                "source_ids": ["E01"],
                "opportunities": [{
                    "topic": "foreign_trade",
                    "disposition": "merged",
                    "reason": "境外渠道触发外贸研究。",
                    "policy_source_ids": ["P06"],
                }],
            }]
        }
        errors = validate_report_data(data)
        self.assertTrue(any("海外业务信号缺少机会处置" in error for error in errors), errors)

    def test_portable_bootstrap_modules_exist(self):
        for module in ("runtime_state", "bootstrap", "doctor"):
            with self.subTest(module=module):
                self.assertTrue((ROOT / "scripts" / f"{module}.py").is_file())
                importlib.import_module(module)

    def test_runtime_rejects_an_old_node_version(self):
        state = {
            "node": {"path": "C:/runtime/node.exe", "version": "v16.20.2"},
            "node_modules": "C:/runtime/node_modules",
            "playwright": True,
            "chrome": {"path": "C:/runtime/chrome.exe", "version": "Chrome 140"},
            "python_docx": True,
        }
        errors = capability_errors(state)
        self.assertTrue(any("Node.js版本不满足" in error for error in errors), errors)

    def test_runtime_discovery_does_not_execute_the_browser(self):
        source = (ROOT / "scripts" / "runtime_state.py").read_text(encoding="utf-8")
        self.assertNotIn('_version([str(chrome_path), "--version"])', source)


if __name__ == "__main__":
    unittest.main()
