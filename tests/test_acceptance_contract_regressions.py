from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from compile_workspace import _compile_enterprise_findings, _enrich_catalog_assessment
from init_report_workspace import build_findings
from report_core import _has_unsupported_transaction_claim
from validate_encouraged_industry_assessment import validate_assessment


class AcceptanceContractRegressions(unittest.TestCase):
    def test_aliases_do_not_change_facts_or_roles(self):
        findings = build_findings('测试主体')['enterprise-findings.json']
        findings['report'] = {'enterprise_overview': {'employees': '未公开', 'summary': '真实简介'}, 'landing_businesses': [{'key': 'landing'}]}
        findings['research'] = {'business_candidates': [{'key': 'candidate', 'candidate': '服务', 'disposition': 'include', 'landing_business_key': 'landing'}], 'department_routes': [{'key': 'route', 'role': 'provincial_counterpart'}]}
        with tempfile.TemporaryDirectory() as tmp:
            compiled, _ = _compile_enterprise_findings(findings, Path(tmp))
        self.assertEqual(compiled['report-data.json']['enterprise_overview']['employee_scale'], '未公开')
        research = compiled['research-ledger.json']
        self.assertEqual(research['business_candidates'][0]['disposition_target'], 'L01')
        self.assertEqual(research['department_routes'][0]['department_role'], 'provincial_counterpart')

    def test_catalog_bad_shape_is_diagnostic_not_crash(self):
        errors = validate_assessment({'businesses': [], 'encouraged_industry_assessment': {'catalogs_checked': ['目录名']}})
        self.assertTrue(any('对象数组' in e for e in errors))

    def test_chinese_judgments_translate_without_claiming_a_match(self):
        result = _enrich_catalog_assessment({'overall_judgment': '暂未发现明确匹配', 'business_assessments': [{'judgment': '存在相近可能', 'matched_items': []}]})
        self.assertEqual(result['overall_judgment'], 'no_match')
        self.assertEqual(result['business_assessments'][0]['judgment'], 'potential_match')

    def test_disclaimer_is_not_a_transaction_claim(self):
        self.assertFalse(_has_unsupported_transaction_claim('不作为已确认供应商'))
        self.assertTrue(_has_unsupported_transaction_claim('甲是供应商；乙不作为已确认供应商'))
