from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import ppa


class ParallelGateTests(unittest.TestCase):
    def test_independent_checks_overlap_and_all_errors_survive(self):
        barrier = threading.Barrier(2)
        def validate(script, *args):
            if script in ('validate_report_data.py', 'validate_text_quality.py'):
                barrier.wait(timeout=2)
                return [script + ': intentional failure']
            return []
        with tempfile.TemporaryDirectory() as tmp, patch.object(ppa, '_validator_errors', side_effect=validate):
            with self.assertRaises(ValueError) as failure:
                ppa._validate_final_suite(Path(tmp))
        self.assertIn('validate_report_data.py: intentional failure', str(failure.exception))
        self.assertIn('validate_text_quality.py: intentional failure', str(failure.exception))
