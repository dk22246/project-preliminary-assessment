from pathlib import Path
import ast
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from compile_workspace import compile_enterprise_findings
from init_report_workspace import build_findings
from report_core import validate_report_data


class RenderInputContractTests(unittest.TestCase):
    def test_optional_report_fields_renderers_read_are_allowed_inputs(self):
        schema = json.loads((ROOT / 'schemas/enterprise-findings.schema.json').read_text(encoding='utf-8'))
        allowed = schema['properties']['report']['properties']
        for script in ('render_report_html.py', 'render_report_word.py'):
            tree = ast.parse((ROOT / 'scripts' / script).read_text(encoding='utf-8'))
            fields = {n.args[0].value for n in ast.walk(tree)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                      and isinstance(n.func.value, ast.Name) and n.func.value.id == 'data'
                      and n.func.attr == 'get' and n.args and isinstance(n.args[0], ast.Constant)}
            self.assertFalse(fields - allowed.keys(), (script, fields - allowed.keys()))

    def test_analysis_and_support_survive_compile(self):
        data = build_findings('契约测试公司')['enterprise-findings.json']
        data['report'].update(financial_analysis='基于财报的经营分析',
                              comprehensive_assessment='基于企业事实的综合评估',
                              government_support=[{'name': '已披露补助', 'amount': '1万元'}])
        with tempfile.TemporaryDirectory() as tmp:
            result = compile_enterprise_findings(data, Path(tmp))['report-data.json']
        for field in ('financial_analysis', 'comprehensive_assessment', 'government_support'):
            self.assertEqual(result[field], data['report'][field])

    def test_final_report_validation_rejects_raw_risk_lists(self):
        errors = validate_report_data({'risks': []})
        self.assertTrue(any('风险数据必须编译' in error for error in errors), errors)
