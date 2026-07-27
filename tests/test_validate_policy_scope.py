import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_policy_scope.py"


def run_validator(policies):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "policies.json"
        source.write_text(
            json.dumps({"policies": policies}, ensure_ascii=False), encoding="utf-8"
        )
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(source)], text=True, capture_output=True
        )


def policy_card(**overrides):
    card = {
        "name": "海南自贸港鼓励类产业企业所得税优惠",
        "region": "海南省",
        "region_evidence": "适用于海南自由贸易港",
        "source_type": "official",
        "source_url": "https://www.chinatax.gov.cn/example",
        "status": "current",
        "enterprise_business": "海南主体承接电子商务运营",
        "landing_action": "将电商运营、管理和结算实质迁入海南",
    }
    card.update(overrides)
    return card


class PolicyCardTests(unittest.TestCase):
    def test_allows_complete_current_official_hainan_or_sanya_cards(self):
        result = run_validator(
            [
                policy_card(region="海南省"),
                policy_card(region="三亚市"),
                policy_card(region="三亚中央商务区"),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blocks_outside_hainan_region(self):
        result = run_validator([policy_card(region="广东省")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("地域不在允许范围", result.stderr)

    def test_blocks_missing_region_evidence(self):
        result = run_validator([policy_card(region_evidence="")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少地域适用依据", result.stderr)

    def test_blocks_policy_card_without_official_source(self):
        result = run_validator([policy_card(source_type="secondary")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("必须引用官方原始文件", result.stderr)

    def test_blocks_policy_card_without_source_url(self):
        result = run_validator([policy_card(source_url="")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少官方原文链接", result.stderr)

    def test_blocks_draft_policy_card(self):
        result = run_validator([policy_card(status="draft")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("不得写入现行政策清单", result.stderr)

    def test_blocks_policy_card_without_enterprise_path(self):
        result = run_validator([policy_card(enterprise_business="")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少企业承接业务", result.stderr)

    def test_blocks_policy_card_without_landing_action(self):
        result = run_validator([policy_card(landing_action="")])
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少企业落地动作", result.stderr)
