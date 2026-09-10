from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from report_core import load_ranking_registry, validate_report_data


REPORT = json.loads((ROOT / "examples" / "flyco-report-data.json").read_text(encoding="utf-8-sig"))


class RankingRegistryTests(unittest.TestCase):
    def test_packaged_registry_is_complete_and_verified(self):
        registry = load_ranking_registry()
        self.assertEqual(set(registry), {"fortune_global_500", "china_enterprise_500", "china_private_enterprise_500"})

    def test_missing_broken_or_unverified_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            with self.assertRaises(ValueError):
                load_ranking_registry(path)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_ranking_registry(path)

    def test_duplicate_or_nonofficial_registry_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            payload = {
                "version": "1.0", "verified_at": "2026-08-27",
                "rankings": [
                    {"ranking_name": "fortune_global_500", "year": 2026, "official_url": "https://example.com/x", "allowed_issuers": ["X"], "source_type": "博客"},
                    {"ranking_name": "fortune_global_500", "year": 2026, "official_url": "https://example.com/y", "allowed_issuers": ["Y"], "source_type": "官方榜单"},
                ],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_ranking_registry(path)

    def test_updated_registry_year_is_used_without_python_change(self):
        registry_payload = json.loads((ROOT / "references" / "ranking-registry.json").read_text(encoding="utf-8"))
        registry_payload["rankings"]["fortune_global_500"]["year"] = 2027
        registry_payload["rankings"]["fortune_global_500"]["official_url"] = "https://fortune.com/ranking/global500/2027/"
        data = copy.deepcopy(REPORT)
        data["top500_status"][0]["year"] = 2027
        source_id = data["top500_status"][0]["source_ids"][0]
        source = next(item for item in data["sources"] if item["id"] == source_id)
        source["location"] = "https://fortune.com/ranking/global500/2027/"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            path.write_text(json.dumps(registry_payload, ensure_ascii=False), encoding="utf-8")
            with patch.dict(os.environ, {"REPORT_RANKING_REGISTRY": str(path)}):
                errors = validate_report_data(data)
        self.assertFalse(any("最新正式年度" in error or "官方榜单" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
