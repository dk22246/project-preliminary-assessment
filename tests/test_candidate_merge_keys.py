from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from discover_current_policies import _merge_rows


class CandidateMergeTests(unittest.TestCase):
    def test_canonical_keys_preserve_distinct_candidates_and_update_in_place(self):
        old = [{'key': 'a', 'title': '甲'}, {'key': 'b', 'title': '乙'}]
        result = _merge_rows(old, [{'key': 'a', 'title': '更新甲'}, {'key': 'c', 'title': '丙'}])
        self.assertEqual([row['key'] for row in result], ['a', 'b', 'c'])
        self.assertEqual(result[0]['title'], '更新甲')

    def test_canonical_key_wins_over_regenerated_serial_id(self):
        result = _merge_rows([{'key': 'a', 'id': 'PC01'}], [{'key': 'a', 'id': 'PC02'}])
        self.assertEqual(len(result), 1)
