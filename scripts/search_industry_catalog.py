#!/usr/bin/env python3
"""Recall subject-specific encouraged-industry candidates and separate conflicts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "catalogs" / "complete-industry-catalog-library.json"
SUBJECTS = {"domestic": "domestic_positive", "foreign": "foreign_positive"}
ACTIVITY_KEYWORDS = {
    "research": ("研发", "研究", "技术开发", "设计"),
    "manufacturing": ("制造", "生产"),
    "processing": ("加工", "洗选", "冶炼"),
    "mining": ("开采", "采矿", "采煤", "勘探", "抽采"),
    "sales": ("销售", "零售", "批发", "交易"),
    "trade": ("贸易", "进出口", "跨境电子商务", "跨境电商"),
    "operation": ("运营", "经营"),
    "technical_service": ("检验", "检测", "维修", "咨询", "技术服务"),
    "logistics": ("物流", "运输", "仓储", "配送", "储运"),
    "investment": ("投资",),
    "management": ("管理",),
}
CONDITION_MARKERS = ("≥", "≤", "以上", "以下", "不得", "不含", "不包括", "仅限", "必须", "资质", "认证", "产能", "设计生产能力")


def _terms(queries: list[str]) -> list[str]:
    result: list[str] = []
    for query in queries:
        normalized = query.strip().lower()
        if normalized:
            result.append(normalized)
        result.extend(term for term in normalized.replace("、", " ").replace("/", " ").replace("，", " ").split() if term)
    return list(dict.fromkeys(result))


def _haystack(entry: dict) -> str:
    details = " ".join(
        f"{item.get('detail_title', '')} {item.get('definition', '')}"
        for item in entry.get("detail_entries", [])
    )
    return " ".join(str(entry.get(key, "")) for key in ("section", "subsection", "item_title", "region")) + " " + details


def classify_catalog_entry(entry: dict) -> dict:
    """Derive stable action boundaries from the packaged catalog text."""
    text = _haystack(entry)
    activity_types = sorted({kind for kind, words in ACTIVITY_KEYWORDS.items() if any(word in text for word in words)})
    has_condition = any(marker in text for marker in CONDITION_MARKERS)
    classification = "action_condition" if has_condition else "action_boundary" if activity_types else "broad_category"
    return {"classification": classification, "activity_types": activity_types}


def activity_is_compatible(entry: dict, activity_type: str) -> bool:
    derived = classify_catalog_entry(entry)
    return derived["classification"] == "broad_category" or activity_type in derived["activity_types"]


def _rank(entries: list[dict], terms: list[str], limit: int) -> list[dict]:
    scored: list[tuple[int, dict, list[str]]] = []
    for entry in entries:
        haystack = _haystack(entry).lower()
        title = str(entry.get("item_title", "")).lower()
        detail_titles = " ".join(str(item.get("detail_title", "")) for item in entry.get("detail_entries", [])).lower()
        hits = [term for term in terms if term and term in haystack]
        if not hits:
            continue
        score = sum(8 if term == title else 5 if term in title else 3 if term in detail_titles else 1 for term in hits)
        if entry.get("catalog_scope") == "hainan_added_2024":
            score += 1
        scored.append((score, entry, hits))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("catalog_scope")), int(item[1].get("source_row") or 99999)))
    return [dict(entry, recall_score=score, matched_terms=hits) for score, entry, hits in scored[:limit]]


def search(
    queries: list[str],
    subject_type: str,
    limit: int = 12,
    include_conflicts: bool = True,
) -> dict:
    if subject_type not in SUBJECTS:
        raise ValueError("subject_type 必须为 domestic 或 foreign")
    payload = json.loads(CATALOG.read_text(encoding="utf-8-sig"))
    by_id = {entry["id"]: entry for entry in payload.get("entries", [])}
    terms = _terms(queries)
    candidates = _rank([by_id[item_id] for item_id in payload["routes"][SUBJECTS[subject_type]]], terms, limit)
    conflicts = []
    if include_conflicts:
        conflicts = _rank([by_id[item_id] for item_id in payload["routes"]["industrial_conflicts"]], terms, limit)
    return {
        "subject_type": subject_type,
        "decision": None,
        "candidates": candidates,
        "conflicts": conflicts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="按企业主体性质召回鼓励类候选，并单列限制类、淘汰类冲突；不代替资格认定。")
    parser.add_argument("query", nargs="+")
    parser.add_argument("--subject-type", choices=sorted(SUBJECTS), required=True)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--no-conflicts", action="store_true")
    args = parser.parse_args()
    print(json.dumps(search(args.query, args.subject_type, args.limit, not args.no_conflicts), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
