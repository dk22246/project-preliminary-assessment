#!/usr/bin/env python3
"""Validate the packaged industry-catalog workbook and generated JSON library."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "references" / "catalogs" / "hainan-ftz-encouraged-industry-complete-library.xlsx"
DEFAULT_LIBRARY = ROOT / "references" / "catalogs" / "complete-industry-catalog-library.json"
EXPECTED_COUNTS = {
    "industrial_restructuring_2024": {"total": 1005, "encouraged": 352, "restricted": 231, "eliminated": 422},
    "foreign_investment_national_2025": 619,
    "foreign_investment_regional_2025": 1060,
    "foreign_investment_hainan_2025": 102,
    "hainan_added_2024": 176,
    "hainan_added_guide_details": 352,
}


def validate(workbook: Path = DEFAULT_WORKBOOK, library: Path = DEFAULT_LIBRARY) -> list[str]:
    errors: list[str] = []
    if not workbook.is_file():
        return [f"缺少统一目录工作簿：{workbook}"]
    if not library.is_file():
        return [f"缺少结构化目录库：{library}"]
    payload = json.loads(library.read_text(encoding="utf-8-sig"))
    digest = hashlib.sha256(workbook.read_bytes()).hexdigest()
    if payload.get("source_workbook_sha256") != digest:
        errors.append("结构化目录库与统一工作簿校验值不一致，请重新运行构建脚本")
    if payload.get("counts") != EXPECTED_COUNTS:
        errors.append(f"目录条数不符：{payload.get('counts')}")
    entries = payload.get("entries", [])
    by_id = {item.get("id"): item for item in entries}
    if len(by_id) != len(entries) or None in by_id:
        errors.append("目录条目ID缺失或重复")
    routes = payload.get("routes", {})
    for route, expected in (("domestic_positive", 528), ("foreign_positive", 721), ("industrial_conflicts", 653)):
        ids = routes.get(route, [])
        if len(ids) != expected or any(item_id not in by_id for item_id in ids):
            errors.append(f"{route} 路由条数或引用无效")
    hainan = [item for item in entries if item.get("catalog_scope") == "hainan_added_2024"]
    if len(hainan) != 176 or any(not item.get("detail_entries") for item in hainan):
        errors.append("海南新增176项未全部关联界定指引细项")
    if any(not item.get("source_url", "").startswith("https://www.ndrc.gov.cn/") for item in entries):
        errors.append("存在缺少国家发展改革委正式来源的目录条目")
    conflict_categories = {by_id[item_id].get("policy_category") for item_id in routes.get("industrial_conflicts", []) if item_id in by_id}
    if conflict_categories != {"restricted", "eliminated"}:
        errors.append("冲突检查路由必须且只能包含限制类、淘汰类")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY)
    args = parser.parse_args()
    errors = validate(args.workbook.resolve(), args.library.resolve())
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("通过：统一产业目录库、主体分流、海南界定指引和限制/淘汰冲突路由均有效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
