#!/usr/bin/env python3
"""Block policies that lack official, current, Hainan/Sanya applicability evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ALLOWED_REGIONS = {"\u6d77\u5357\u7701", "\u4e09\u4e9a\u5e02", "\u4e09\u4e9a\u4e2d\u592e\u5546\u52a1\u533a"}
REQUIRED_FIELDS = ("name", "source_url", "enterprise_business", "landing_action")
FIELD_LABELS = {
    "name": "\u653f\u7b56\u540d\u79f0",
    "source_url": "\u5b98\u65b9\u539f\u6587\u94fe\u63a5",
    "enterprise_business": "\u4f01\u4e1a\u627f\u63a5\u4e1a\u52a1",
    "landing_action": "\u4f01\u4e1a\u843d\u5730\u52a8\u4f5c",
}


def validate_policy(policy: dict, index: int) -> list[str]:
    errors: list[str] = []
    region = str(policy.get("region", "")).strip()
    evidence = str(policy.get("region_evidence", "")).strip()
    label = str(policy.get("name", "")).strip() or f"\u7b2c{index + 1}\u6761\u653f\u7b56"
    for field in REQUIRED_FIELDS:
        if not str(policy.get(field, "")).strip():
            errors.append(f"{label}: \u7f3a\u5c11{FIELD_LABELS[field]}")
    if not evidence:
        errors.append(f"{label}: \u7f3a\u5c11\u5730\u57df\u9002\u7528\u4f9d\u636e")
    if region not in ALLOWED_REGIONS:
        errors.append(f"{label}: \u5730\u57df\u4e0d\u5728\u5141\u8bb8\u8303\u56f4 ({region})")
    if policy.get("source_type") != "official":
        errors.append(f"{label}: \u5fc5\u987b\u5f15\u7528\u5b98\u65b9\u539f\u59cb\u6587\u4ef6")
    if policy.get("status") != "current":
        errors.append(f"{label}: \u975e\u73b0\u884c\u6216\u5f81\u6c42\u610f\u89c1\u653f\u7b56\u4e0d\u5f97\u5199\u5165\u73b0\u884c\u653f\u7b56\u6e05\u5355")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("\u7528\u6cd5: validate_policy_scope.py <policies.json>", file=sys.stderr)
        return 2
    try:
        policies = json.loads(Path(argv[1]).read_text(encoding="utf-8-sig"))["policies"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"\u65e0\u6cd5\u8bfb\u53d6\u653f\u7b56 JSON: {error}", file=sys.stderr)
        return 2
    errors = [message for index, policy in enumerate(policies) for message in validate_policy(policy, index)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"\u901a\u8fc7\uff1a\u5df2\u6821\u9a8c {len(policies)} \u6761\u653f\u7b56")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
