from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
from collect_web_evidence import collect_many


class CollectionParallelTests(unittest.TestCase):
    def test_cross_host_overlap_dedup_and_stable_order(self):
        barrier = threading.Barrier(2)
        def collect(url, index, **kwargs):
            barrier.wait(timeout=2)
            return {'url': url, 'index': index}
        with patch('collect_web_evidence.collect', side_effect=collect):
            rows = collect_many(['https://a.gov.cn/a', 'https://b.gov.cn/b', 'https://a.gov.cn/a#part'])
        self.assertEqual([row['url'] for row in rows], ['https://a.gov.cn/a', 'https://b.gov.cn/b'])
        self.assertEqual([row['index'] for row in rows], [1, 2])

    def test_one_host_backlog_does_not_starve_another_host(self):
        barrier = threading.Barrier(2)
        active = set()
        lock = threading.Lock()
        def collect(url, index, **kwargs):
            host = url.split('/')[2]
            with lock:
                self.assertNotIn(host, active)
                active.add(host)
            if index in (1, 5):
                barrier.wait(timeout=2)
            with lock:
                active.remove(host)
            return {'url': url, 'index': index}
        urls = [f'https://a.gov.cn/{i}' for i in range(4)] + ['https://b.gov.cn/b']
        with patch('collect_web_evidence.collect', side_effect=collect):
            rows = collect_many(urls)
        self.assertEqual([row['url'] for row in rows], urls)
