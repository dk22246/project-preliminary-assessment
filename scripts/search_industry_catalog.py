#!/usr/bin/env python3
"""Recall subject-specific encouraged-industry candidates and separate conflicts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "catalogs" / "complete-industry-catalog-library.json"
SUBJECTS = {"domestic": "domestic_positive", "foreign": "foreign_positive"}


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
