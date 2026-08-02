#!/usr/bin/env python3
"""Recall candidates from the bundled Hainan 2024 industry guide; never decide eligibility."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "references" / "catalogs" / "hainan-encouraged-industries-2024.json"


def search(queries: list[str], limit: int = 12) -> list[dict]:
    payload = json.loads(CATALOG.read_text(encoding="utf-8-sig"))
    terms = [term.strip().lower() for query in queries for term in query.replace("、", " ").replace("/", " ").split() if term.strip()]
    scored = []
    for entry in payload.get("entries", []):
        haystack = " ".join(str(entry.get(key, "")) for key in ("item_title", "detail_title", "definition")).lower()
        hits = sorted({term for term in terms if term in haystack})
        if not hits:
            continue
        score = sum(3 if term in str(entry.get("detail_title", "")).lower() else 1 for term in hits)
        scored.append((score, entry, hits))
    scored.sort(key=lambda item: (-item[0], int(item[1].get("item_no") or 9999), int(item[1].get("source_row") or 9999)))
    return [dict(entry, recall_score=score, matched_terms=hits) for score, entry, hits in scored[:limit]]


def main() -> int:
    parser = argparse.ArgumentParser(description="召回海南新增鼓励类产业目录候选，不输出资格结论。")
    parser.add_argument("query", nargs="+")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    print(json.dumps({"decision": None, "candidates": search(args.query, args.limit)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
