#!/usr/bin/env python3
import json
import sys
from pathlib import Path


ALLOWED_REGIONS = {"海南省", "三亚市", "三亚中央商务区"}
REQUIRED_FIELDS = ("name", "source_url", "enterprise_business", "landing_action")
FIELD_LABELS = {
    "name": "政策名称",
    "source_url": "官方原文链接",
    "enterprise_business": "企业承接业务",
    "landing_action": "企业落地动作",
}


def validate_policy(policy, index):
    errors = []
    region = str(policy.get("region", "")).strip()
    evidence = str(policy.get("region_evidence", "")).strip()
    label = str(policy.get("name", "")).strip() or f"第{index + 1}条政策"

    for field in REQUIRED_FIELDS:
        if not str(policy.get(field, "")).strip():
            errors.append(f"{label}: 缺少{FIELD_LABELS[field]}")

    if not evidence:
        errors.append(f"{label}: 缺少地域适用依据")
    if region not in ALLOWED_REGIONS:
        errors.append(f"{label}: 地域不在允许范围 ({region})")
    if policy.get("source_type") != "official":
        errors.append(f"{label}: 必须引用官方原始文件")
    if policy.get("status") != "current":
        errors.append(f"{label}: 非现行或征求意见政策不得写入现行政策清单")
    return errors


def main(argv):
    if len(argv) != 2:
        print("用法: validate_policy_scope.py <policies.json>", file=sys.stderr)
        return 2

    try:
        payload = json.loads(Path(argv[1]).read_text(encoding="utf-8-sig"))
        policies = payload["policies"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"无法读取政策 JSON: {error}", file=sys.stderr)
        return 2

    errors = [
        message
        for index, policy in enumerate(policies)
        for message in validate_policy(policy, index)
    ]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(f"通过：已校验 {len(policies)} 条政策")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
