#!/usr/bin/env python3
"""Validate an auditable public-web evidence ledger before it informs a report."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from evidence_collectors.registry import is_allowed_url


SUCCESS_FIELDS = (
    "source_url", "canonical_url", "title", "publisher", "source_category", "purpose",
    "fetched_at", "content_path", "content_sha256",
)
COMMON_FIELDS = ("source_url", "canonical_url", "source_category", "purpose", "fetched_at", "extraction_status")


def validate_ledger(ledger: dict, base_dir: Path) -> list[str]:
    errors: list[str] = []
    if not str(ledger.get("enterprise", "")).strip():
        errors.append("证据台账缺少企业名称")
    if not str(ledger.get("topic", "")).strip():
        errors.append("证据台账缺少检索主题")
    records = ledger.get("evidence")
    if not isinstance(records, list) or not records:
        return errors + ["证据台账至少需要一条证据记录"]
    explicit_hosts = set(ledger.get("allowed_domains", []))
    canonical_seen: set[str] = set()
    hash_seen: set[str] = set()
    for index, item in enumerate(records, 1):
        label = f"第{index}条证据"
        if not isinstance(item, dict):
            errors.append(f"{label}: 记录必须是对象")
            continue
        for field in COMMON_FIELDS:
            if not str(item.get(field, "")).strip():
                errors.append(f"{label}: 缺少{field}")
        source_url = str(item.get("source_url", "")).strip()
        canonical_url = str(item.get("canonical_url", "")).strip()
        if source_url and not is_allowed_url(source_url, explicit_hosts):
            errors.append(f"{label}: 来源不在允许来源白名单：{source_url}")
        if canonical_url:
            if canonical_url in canonical_seen:
                errors.append(f"{label}: 规范链接重复：{canonical_url}")
            canonical_seen.add(canonical_url)
        status = item.get("extraction_status")
        if status == "success":
            for field in SUCCESS_FIELDS:
                if not str(item.get(field, "")).strip():
                    errors.append(f"{label}: 成功记录缺少{field}")
            if not isinstance(item.get("http_status"), int) or not 200 <= item["http_status"] < 300:
                errors.append(f"{label}: 成功记录HTTP状态异常")
            content_path = str(item.get("content_path", "")).strip()
            if content_path:
                content = (base_dir / content_path).resolve()
                if not content.is_file():
                    errors.append(f"{label}: 正文文件不存在：{content_path}")
                else:
                    content_hash = hashlib.sha256(content.read_bytes()).hexdigest()
                    if content_hash != str(item.get("content_sha256", "")).strip():
                        errors.append(f"{label}: 正文哈希不一致")
                    if content_hash in hash_seen:
                        errors.append(f"{label}: 正文内容重复")
                    hash_seen.add(content_hash)
        elif status == "failed":
            if not str(item.get("error", "")).strip():
                errors.append(f"{label}: 抓取失败记录缺少错误信息")
        else:
            errors.append(f"{label}: extraction_status 仅可为 success 或 failed")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("用法: validate_evidence.py <evidence.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"无法读取证据台账: {error}", file=sys.stderr)
        return 2
    errors = validate_ledger(ledger, path.parent)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"通过：已校验 {len(ledger['evidence'])} 条网页证据")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
