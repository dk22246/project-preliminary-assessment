import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import validate_report_data


FLYCO = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8"))


def usd_data():
    data = copy.deepcopy(FLYCO)
    data["meta"].update({"financial_currency": "USD", "financial_unit": "亿美元"})
    for row in data["financials"]:
        row["revenue"] = str(row["revenue"]).replace("亿元", "")
        row["profit"] = str(row["profit"]).replace("亿元", "")
    data["financials"][-1].update({
        "revenue_change": "—",
        "profit_change": "—",
        "change_note": "FY2024未纳入FY2023基数，未计算同比。",
    })
    return data


class FinancialRenderingTests(unittest.TestCase):
    def test_every_financial_row_requires_an_explicit_data_status(self):
        data = copy.deepcopy(FLYCO)
        data["financials"][0].pop("data_status", None)
        errors = validate_report_data(data)
        self.assertTrue(any("data_status" in error for error in errors), errors)

    def test_nonlisted_report_accepts_three_explicit_not_public_financial_rows(self):
        data = copy.deepcopy(FLYCO)
        data["enterprise_overview"]["listing_status"] = "非上市"
        for row in data["financials"]:
            row.update({
                "data_status": "not_public",
                "revenue": "未公开披露",
                "revenue_change": "未公开披露",
                "profit": "未公开披露",
                "profit_change": "未公开披露",
                "tax_value": "未公开披露，需企业补充",
                "tax_basis": "需企业补充",
                "government_support": "未公开披露，需企业补充",
                "source": "本轮公开检索未发现可靠数据",
                "availability_note": "本轮公开检索未发现可靠数据，需企业补充",
            })
        errors = validate_report_data(data)
        self.assertFalse(any("财务行" in error for error in errors), errors)

    def test_unavailable_financial_row_requires_a_reason(self):
        data = copy.deepcopy(FLYCO)
        row = data["financials"][0]
        row.update({
            "data_status": "not_public",
            "revenue": "未公开披露",
            "revenue_change": "未公开披露",
            "profit": "未公开披露",
            "profit_change": "未公开披露",
        })
        row.pop("availability_note", None)
        errors = validate_report_data(data)
        self.assertTrue(any("availability_note" in error for error in errors), errors)

    def test_html_displays_the_unavailable_financial_reason(self):
        data = copy.deepcopy(FLYCO)
        data["financials"][0].update({
            "data_status": "not_public",
            "revenue": "未公开披露",
            "revenue_change": "未公开披露",
            "profit": "未公开披露",
            "profit_change": "未公开披露",
            "availability_note": "本轮公开检索未发现可靠数据，需企业补充",
        })
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nonlisted-report-data.json"
            output = Path(directory) / "report.html"
            source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "render_report_html.py"), str(source), "--out", str(output)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("本轮公开检索未发现可靠数据，需企业补充", output.read_text(encoding="utf-8"))

    def test_rejects_explanatory_sentence_in_yoy_cell(self):
        data = usd_data()
        data["financials"][-1]["revenue_change"] = "—（本报告未纳入FY2023基数）"
        errors = validate_report_data(data)
        self.assertTrue(any("revenue_change" in error and "同比" in error for error in errors), errors)

    def test_requires_currency_and_display_unit_to_appear_together(self):
        data = usd_data()
        data["meta"].pop("financial_unit")
        errors = validate_report_data(data)
        self.assertIn("财务币种和显示单位必须同时填写或同时缺省", errors)

    def test_html_uses_configured_unit_and_places_change_note_below_financial_table(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "usd-report-data.json"
            output = directory / "report.html"
            source.write_text(json.dumps(usd_data(), ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "render_report_html.py"), str(source), "--out", str(output)],
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            html = output.read_text(encoding="utf-8")
            financial_section = html.split('<section id="s二"', 1)[1].split("</section>", 1)[0]
            self.assertIn("营业收入（亿美元）", financial_section)
            self.assertIn("净利润（亿美元）", financial_section)
            self.assertIn("FY2024未纳入FY2023基数，未计算同比。", financial_section)
            self.assertNotIn("营业收入（亿元）", financial_section)

    def test_html_supports_euro_or_generic_financial_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for label, meta, expected_header in (
                ("eur", {"financial_currency": "EUR", "financial_unit": "百万欧元"}, "营业收入（百万欧元）"),
                ("generic", {"financial_currency": None, "financial_unit": None}, "营业收入</th>"),
            ):
                data = usd_data()
                for key, value in meta.items():
                    if value is None:
                        data["meta"].pop(key, None)
                    else:
                        data["meta"][key] = value
                source = directory / f"{label}-report-data.json"
                output = directory / f"{label}.html"
                source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "render_report_html.py"), str(source), "--out", str(output)],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(expected_header, output.read_text(encoding="utf-8"))

    def test_html_does_not_force_yoy_columns_to_remain_on_one_line(self):
        source = (ROOT / "scripts" / "render_report_html.py").read_text(encoding="utf-8")
        self.assertIn(".financial-table td:nth-child(3),.financial-table td:nth-child(5){white-space:normal", source)
        self.assertIn(".financial-table th,.financial-table td{min-width:0;max-width:100%;overflow:hidden", source)

    def test_preflight_smoke_includes_browser_layout_gate(self):
        source = (ROOT / "scripts" / "preflight.py").read_text(encoding="utf-8")
        self.assertIn("verify_html_layout.mjs", source)

    def test_word_renderer_uses_the_same_dynamic_financial_headers_and_notes(self):
        source = (ROOT / "scripts" / "render_report_word.py").read_text(encoding="utf-8")
        self.assertIn("financial_headers", source)
        self.assertIn("financial_change_notes", source)


if __name__ == "__main__":
    unittest.main()
