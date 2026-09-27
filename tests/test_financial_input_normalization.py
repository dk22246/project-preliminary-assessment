from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from compile_workspace import _normalize_financials


class FinancialInputTests(unittest.TestCase):
    def test_explicit_raw_unit_and_aliases_normalize_without_new_facts(self):
        report = {'meta': {'financial_unit': '亿元', 'financial_raw_unit': '元'},
                  'financials': [{'year': '2025', 'revenue': 200000000,
                                 'net_profit': 30000000, 'revenue_yoy': '5%', 'profit_yoy': '-2%'}]}
        _normalize_financials(report)
        row = report['financials'][0]
        self.assertEqual(row['revenue'], '2')
        self.assertEqual(row['profit'], '0.3')
        self.assertEqual(row['revenue_change'], '5%')
        self.assertNotIn('net_profit', row)
        self.assertNotIn('tax_value', row)

    def test_conflicting_alias_is_not_silently_selected(self):
        report = {'meta': {'financial_unit': '亿元'}, 'financials': [{'profit': 2, 'net_profit': 3}]}
        with self.assertRaisesRegex(ValueError, 'profit'):
            _normalize_financials(report)

    def test_unit_conversion_never_guesses_text_amounts(self):
        report = {'meta': {'financial_unit': '亿元', 'financial_raw_unit': '元'}, 'financials': [{'revenue': '约两亿元'}]}
        with self.assertRaises(ValueError):
            _normalize_financials(report)

    def test_missing_disclosure_is_not_an_amount_to_convert(self):
        report = {'meta': {'financial_unit': '亿元', 'financial_raw_unit': '元'},
                  'financials': [{'revenue': 200000000, 'profit': '未公开披露',
                                 'tax_value': '未公开披露', 'availability_note': '需企业补充'}]}
        _normalize_financials(report)
        self.assertEqual(report['financials'][0]['revenue'], '2')
        self.assertEqual(report['financials'][0]['profit'], '未公开披露')
        self.assertEqual(report['financials'][0]['tax_value'], '未公开披露')
        self.assertEqual(report['financials'][0]['availability_note'], '需企业补充')

    def test_converted_amounts_are_capped_at_two_decimals_for_report_layout(self):
        report = {'meta': {'financial_unit': '亿元', 'financial_raw_unit': '元'},
                  'financials': [{'revenue': 28873380466.76, 'profit': 7038465194.15}]}
        _normalize_financials(report)
        self.assertEqual(report['financials'][0]['revenue'], '288.73')
        self.assertEqual(report['financials'][0]['profit'], '70.38')
