#!/usr/bin/env python3
"""Reject a policy report when mandatory Hainan/Sanya policy search lanes vanish."""

import json
import sys
from pathlib import Path


TOPICS = {
    "corporate_income_tax_15": "企业所得税15%",
    "offshore_trade_stamp_tax": "离岸贸易印花税",
    "free_trade_account_ef": "EF账户",
    "outbound_direct_investment": "ODI/境外直接投资",
    "headquarters_recognition": "总部认定",
    "new_odi_income_cit_exemption": "新增境外直接投资所得免征企业所得税",
}
ALLOWED_REGIONS = {"海南省", "三亚市", "三亚中央商务区"}
ALLOWED_STATUSES = {"matched", "not_applicable", "no_current_policy_found"}


def validate_item(item):
    errors = []
    topic = str(item.get("topic", "")).strip()
    label = TOPICS.get(topic, topic or "未命名主题")
    status = str(item.get("search_status", "")).strip()

    if topic not in TOPICS:
        errors.append(f"{label}: 非法或未知政策主题")
    if status not in ALLOWED_STATUSES:
        errors.append(f"{label}: 检索结论必须为 {', '.join(sorted(ALLOWED_STATUSES))}")
    for key, label_name in (
        ("official_source_url", "官方原文链接"),
        ("policy_name", "政策名称"),
        ("conclusion", "企业适用结论"),
    ):
        if not str(item.get(key, "")).strip():
            errors.append(f"{label}: 缺少{label_name}")
    region = str(item.get("region", "")).strip()
    if region not in ALLOWED_REGIONS:
        errors.append(f"{label}: 地域不在允许范围 ({region})")
    return errors


def main(argv):
    if len(argv) != 2:
        print("用法: validate_policy_coverage.py <coverage.json>", file=sys.stderr)
        return 2
    try:
        coverage = json.loads(Path(argv[1]).read_text(encoding="utf-8-sig"))["coverage"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
        print(f"无法读取政策覆盖 JSON: {error}", file=sys.stderr)
        return 2

    seen = {str(item.get("topic", "")).strip() for item in coverage if isinstance(item, dict)}
    errors = [f"缺少必检政策主题：{label}" for key, label in TOPICS.items() if key not in seen]
    errors.extend(
        message
        for item in coverage
        if isinstance(item, dict)
        for message in validate_item(item)
    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"通过：已逐项留痕 {len(TOPICS)} 个必检政策主题")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
