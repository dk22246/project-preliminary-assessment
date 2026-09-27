import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import ppa
import workflow_state


class CompileReuseTests(unittest.TestCase):
    def test_reuse_requires_unchanged_inputs_outputs_and_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow_state.create(root, '企业', 'version1')
            for name in ('enterprise-findings.json', 'policy-findings.json'):
                (root / name).write_text('{}', encoding='utf-8')
            calls = []
            def compile_once(work):
                calls.append(True)
                for name in workflow_state.REPORT_ARTIFACTS:
                    (work / name).write_text('{}', encoding='utf-8')
                return {name: {} for name in workflow_state.REPORT_ARTIFACTS}
            args = argparse.Namespace(work_dir=str(root))
            with patch.object(ppa, '_current_workspace', side_effect=lambda _: (root, workflow_state.load(root))), patch.object(ppa, 'package_fingerprint', return_value='version1') as version, patch.object(ppa, '_refresh_enterprise_prepare_receipt'), patch('compile_workspace.compile_workspace', side_effect=compile_once):
                ppa.command_compile(args)
                ppa.command_compile(args)
                self.assertEqual(len(calls), 1)
                (root / 'policy-findings.json').write_text('{"changed":true}', encoding='utf-8')
                ppa.command_compile(args)
                self.assertEqual(len(calls), 2)
                (root / 'report-data.json').write_text('{"tampered":true}', encoding='utf-8')
                ppa.command_compile(args)
                self.assertEqual(len(calls), 3)
                (root / 'equity-evidence.json').unlink()
                ppa.command_compile(args)
                self.assertEqual(len(calls), 4)
                version.return_value = 'version2'
                ppa.command_compile(args)
                self.assertEqual(len(calls), 5)
                self.assertEqual(workflow_state.load(root)['current_stage'], 'environment_ready')
