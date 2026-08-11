#!/usr/bin/env python3
"""Validate complete per-business encouraged-industry judgments before rendering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from report_core import load_data


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "references" / "catalogs" / "complete-industry-catalog-library.json"
JUDGMENTS = {"direct_match", "potential_match", "no_match", "research_incomplete"}
OVERALL = {"direct_match", "potential_match_only", "no_match", "research_incomplete"}
SCOPES = {"hainan_added_2024", "industrial_restructuring_current", "foreign_investment_current"}
BANNED = ("已经认定", "保证享受", "自动符合", "必然享受")


def _text(value: object) -> str:
    return str(value or "").strip()


def _expected_overall(judgments: list[str]) -> str:
    if "research_incomplete" in judgments:
        return "research_incomplete"
    if "direct_match" in judgments:
        return "direct_match"
    if "potential_match" in judgments:
        return "potential_match_only"
    return "no_match"


def validate_assessment(data: dict) -> list[str]:
    errors: list[str] = []
    businesses = data.get("businesses", [])
    business_ids = [_text(item.get("id")) for item in businesses]
    if any(not item for item in business_ids) or len(set(business_ids)) != len(business_ids):
        errors.append("主要业务必须具有唯一且非空的B类id")
    assessment = data.get("encouraged_industry_assessment")
    if not isinstance(assessment, dict):
        return errors + ["缺少海南自由贸易港鼓励类产业目录判定模块"]
    if not _text(assessment.get("catalog_version")) or not _text(assessment.get("summary")):
        errors.append("目录判定缺少版本或总体说明")
    overall = _text(assessment.get("overall_judgment"))
    if overall not in OVERALL:
        errors.append("目录总体判断值无效")

    sources = {_text(item.get("id")) for item in data.get("sources", [])}
    checked = assessment.get("catalogs_checked", [])
    checked_scopes = {_text(item.get("catalog_scope")) for item in checked}
    if checked_scopes != SCOPES:
        errors.append("目录检索必须覆盖海南新增、产业结构调整和外商投资三条路径")
    for item in checked:
        scope = _text(item.get("catalog_scope"))
        status = _text(item.get("status"))
        if status == "checked":
            source_id = _text(item.get("source_id"))
            if not source_id.startswith("P") or source_id not in sources:
                errors.append(f"目录路径{scope}缺少报告P类官方来源")
        elif status == "not_applicable":
            if scope != "foreign_investment_current" or not _text(item.get("reason")):
                errors.append(f"目录路径{scope}不适用时必须说明合法原因")
        else:
            errors.append(f"目录路径{scope}检索状态未完成")

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8-sig"))
    hainan_keys = {
        (_text(item.get("item_no")), _text(item.get("item_title")), _text(detail.get("detail_title")))
        for item in catalog.get("entries", [])
        if item.get("catalog_scope") == "hainan_added_2024"
        for detail in item.get("detail_entries", [])
    }
    rows = assessment.get("business_assessments", [])
    row_ids = [_text(item.get("business_id")) for item in rows]
    if sorted(row_ids) != sorted(business_ids) or len(row_ids) != len(set(row_ids)):
        errors.append("每项主要业务必须有且只有一条目录主判断")
    judgments: list[str] = []
    for item in rows:
        business_id = _text(item.get("business_id")) or "未知业务"
        judgment = _text(item.get("judgment"))
        judgments.append(judgment)
        if judgment not in JUDGMENTS:
            errors.append(f"{business_id}: 目录判断值无效")
            continue
        if judgment == "research_incomplete":
            errors.append(f"{business_id}: 目录研究未完成，禁止交付")
        if not _text(item.get("business")) or not _text(item.get("reason")):
            errors.append(f"{business_id}: 缺少业务名称或判断依据")
        items = item.get("matched_items", [])
        if judgment in {"direct_match", "potential_match"} and not items:
            errors.append(f"{business_id}: 明确或相近判断必须列出具体目录条目")
        if judgment == "no_match" and items:
            errors.append(f"{business_id}: 暂未匹配不得保留伪匹配条目")
        if judgment in {"potential_match", "no_match"} and not _text(item.get("verification_needed")):
            errors.append(f"{business_id}: 相近或未匹配结论必须说明缺口或后续核实")
        enterprise_sources = item.get("enterprise_source_ids", [])
        catalog_sources = item.get("catalog_source_ids", [])
        if not enterprise_sources or any(not _text(source).startswith("E") or source not in sources for source in enterprise_sources):
            errors.append(f"{business_id}: 缺少有效E类企业证据")
        if judgment in {"direct_match", "potential_match"} and (not catalog_sources or any(not _text(source).startswith("P") or source not in sources for source in catalog_sources)):
            errors.append(f"{business_id}: 缺少有效P类目录来源")
        for matched in items:
            required = ("catalog_scope", "catalog_item_no", "catalog_item", "detailed_item", "match_type")
            if any(not _text(matched.get(field)) for field in required):
                errors.append(f"{business_id}: 目录条目字段不完整")
                continue
            if _text(matched.get("catalog_scope")) == "hainan_added_2024":
                key = (_text(matched.get("catalog_item_no")), _text(matched.get("catalog_item")), _text(matched.get("detailed_item")))
                if key not in hainan_keys:
                    errors.append(f"{business_id}: 海南新增目录条目与内置界定指引不一致")
            if judgment == "direct_match" and _text(matched.get("match_type")) != "direct":
                errors.append(f"{business_id}: 明确符合必须包含direct条目")
    if overall in OVERALL and overall != _expected_overall(judgments):
        errors.append("目录总体判断与逐业务判断不一致")
    payload = json.dumps(assessment, ensure_ascii=False)
    for phrase in BANNED:
        if phrase in payload:
            errors.append(f"目录判定存在越权表述：{phrase}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    args = parser.parse_args()
    errors = validate_assessment(load_data(args.report_data))
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("通过：鼓励类产业目录三路径、逐业务三档判断及来源均已校验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
