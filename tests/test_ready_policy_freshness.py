from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import workflow_state as state


class ReadyFreshnessTests(unittest.TestCase):
    def test_unchanged_hash_does_not_keep_expired_evidence_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state.create(root, '企业', 'v1')
            old = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            for name in state.REPORT_ARTIFACTS:
                (root / name).write_text('{}', encoding='utf-8')
            (root / 'report-data.json').write_text(json.dumps({'meta': {'policy_researched_at': old}}), encoding='utf-8')
            hashes = state.artifact_hashes(root)
            payload = state.load(root)
            payload.update(current_stage='report_ready', completed_stages=list(state.STAGES[:state.STAGES.index('report_ready') + 1]), ready_artifact_hashes=hashes)
            state.save(root, payload)
            self.assertTrue(any('24小时' in e for e in state.ready_state_errors(root, 'v1')))
