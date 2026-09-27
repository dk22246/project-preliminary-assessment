from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from compile_workspace import _derive_opportunity_radar


class RadarTransferTests(unittest.TestCase):
    def test_primary_fact_source_and_export_action_survive_derivation(self):
        research = {'fact_ledger': [{'id': 'F01', 'source_id': 'E01', 'signal_type': 'sales', 'action': '产品出口', 'business_ids': ['B01']}]}
        radar = _derive_opportunity_radar(research, {}, [], {})
        signal = radar['signals'][0]
        self.assertEqual(signal['source_ids'], ['E01'])
        self.assertIn('odi', [o['topic'] for o in signal['opportunities']])
        self.assertTrue(all(o['disposition'] == 'pending_evidence' for o in signal['opportunities']))

    def test_existing_candidate_link_supplies_reverse_fact_link(self):
        research = {'fact_ledger': [{'id': 'F01', 'source_id': 'E01', 'signal_type': 'overseas', 'action': '出口'}],
                    'business_candidates': [{'fact_ids': ['F01'], 'disposition': 'include', 'disposition_target': 'L01'}]}
        radar = _derive_opportunity_radar(research, {}, [], {})
        self.assertEqual(radar['signals'][0]['enterprise_fact_refs'], ['L01'])
        self.assertTrue(all(o['disposition'] == 'pending_evidence' for o in radar['signals'][0]['opportunities']))

    def test_excluded_candidate_does_not_invent_landing_link(self):
        research = {'fact_ledger': [{'id': 'F01', 'source_id': 'E01', 'signal_type': 'overseas', 'action': '出口'}],
                    'business_candidates': [{'fact_ids': ['F01'], 'disposition': 'exclude', 'disposition_target': 'L01'}]}
        self.assertEqual(_derive_opportunity_radar(research, {}, [], {})['signals'], [])

    def test_chinese_policy_titles_and_nonstandard_topics_are_not_dropped(self):
        research = {'fact_ledger': [{'id': 'F01', 'source_id': 'E01', 'signal_type': 'overseas', 'action': '出口', 'business_ids': ['B01']}]}
        records = [dict(fact_ids=['F01'], topic=topic, disposition='conditional', source_ids=[source], match_reason='满足条件后办理')
                   for topic, source in [('EF账户', 'P01'), ('多功能自由贸易账户办理办法', 'P02'), ('食品出口专项支持', 'P03')]]
        rows = _derive_opportunity_radar(research, {}, records, {})['signals'][0]['opportunities']
        by_topic = {row['topic']: row for row in rows}
        self.assertEqual(len(rows), len(by_topic))
        self.assertEqual(by_topic['ef_account']['policy_source_ids'], ['P01', 'P02'])
        self.assertEqual(by_topic['ef_account']['disposition'], 'surfaced')
        self.assertEqual(by_topic['食品出口专项支持']['policy_source_ids'], ['P03'])
        self.assertEqual(by_topic['odi']['disposition'], 'pending_evidence')
