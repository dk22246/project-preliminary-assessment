#!/usr/bin/env python3
"""Validate per-run official policy artifacts before policy cards reach a report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sys
from urllib.parse import urlparse

from report_core import load_data


OFFICIAL_SUFFIXES = (".gov.cn", ".chinatax.gov.cn", ".customs.gov.cn", ".pbc.gov.cn", ".safe.gov.cn")
CURRENT_CANDIDATE_STATUSES = {"current", "current_open", "current_no_open_call", "current_conditional"}
APPLICATION_STATUSES = {"open", "no_open_call", "not_application_based", "unknown"}
CONTENT_TYPES = {
    "text/html",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _parse_time(value: object, label: str, errors: list[str]) -> datetime | None:
    try:
        item = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label}: 必须为带时区的ISO 8601时间")
        return None
    if item.tzinfo is None:
        errors.append(f"{label}: 必须包含时区")
        return None
    return item.astimezone(timezone.utc)


def _official_url(url: object, expected_host: str) -> bool:
    parsed = urlparse(_text(url))
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        return False
    return host == expected_host or host.endswith(OFFICIAL_SUFFIXES)


def _source_ids_from_policy(policy: dict) -> set[str]:
    values = [policy.get("source_id"), *(policy.get("source_ids") or [])]
    return {_text(value) for value in values if _text(value).startswith("P")}


def validate_policy_evidence(evidence: dict, report_data: dict, policy_search_ledger: dict, *, base_dir: Path | None = None, allow_fixture: bool = False) -> list[str]:
    """Fail closed for formal policy cards lacking a fresh official artifact."""
    errors: list[str] = []
    base_dir = Path(base_dir or ".").resolve()
    for field in ("version", "enterprise", "researched_at", "mode", "records"):
        if field not in evidence or evidence.get(field) is None or (field != "records" and not evidence.get(field)):
            errors.append(f"政策取证台账缺少{field}")
    if errors:
        return errors
    mode = _text(evidence.get("mode"))
    if mode not in {"formal", "fixture"}:
        errors.append("政策取证台账mode必须为formal或fixture")
    fixture = evidence.get("fixture_metadata") or {}
    if mode == "formal" and (fixture or any("fixture" in _text(value).lower() or "示例" in _text(value) for value in evidence.values() if not isinstance(value, (dict, list)))):
        errors.append("正式政策取证台账不得含fixture或示例标记")
    if mode == "fixture" and not allow_fixture:
        errors.append("fixture政策取证仅可在显式--fixture-mode下使用")
    report_time = _text(report_data.get("meta", {}).get("policy_researched_at"))
    evidence_time = _text(evidence.get("researched_at"))
    if report_time != evidence_time:
        errors.append("政策取证台账时间与报告policy_researched_at不一致")
    _parse_time(evidence_time, "政策取证台账时间", errors)

    sources = {_text(item.get("id")): item for item in report_data.get("sources", []) if isinstance(item, dict)}
    frontend_source_ids = set().union(*(_source_ids_from_policy(policy) for policy in report_data.get("policies", []) if isinstance(policy, dict))) if report_data.get("policies") else set()
    records_by_source: dict[str, list[dict]] = {}
    seen_ids: set[str] = set()
    now = datetime.now(timezone.utc)
    for record in evidence.get("records", []) if isinstance(evidence.get("records"), list) else []:
        if not isinstance(record, dict):
            errors.append("政策取证台账存在非对象记录")
            continue
        record_id = _text(record.get("id"))
        label = record_id or "未编号政策取证"
        if not record_id or record_id in seen_ids:
            errors.append(f"{label}: id缺失或重复")
        seen_ids.add(record_id)
        source_id = _text(record.get("policy_source_id"))
        records_by_source.setdefault(source_id, []).append(record)
        for field in ("requested_url", "final_url", "retrieved_at", "issuer", "title", "document_number", "published_at", "validity_basis", "validity_locator", "application_basis", "application_locator"):
            if not _text(record.get(field)):
                errors.append(f"{label}: 缺少{field}")
        if record.get("http_status") != 200:
            errors.append(f"{label}: HTTP状态必须为200")
        if _text(record.get("content_type")) not in CONTENT_TYPES:
            errors.append(f"{label}: content_type不受支持")
        source = sources.get(source_id)
        if source is None:
            errors.append(f"{label}: policy_source_id不存在于报告来源：{source_id}")
        expected_host = (urlparse(_text((source or {}).get("location"))).hostname or "").lower()
        if not _official_url(record.get("final_url"), expected_host):
            errors.append(f"{label}: final_url不是允许的官方域名或与正式来源不一致")
        source_issuer = _text((source or {}).get("issuer"))
        if source_issuer and source_issuer != _text(record.get("issuer")):
            errors.append(f"{label}: 发文机关与报告正式来源不一致")
        retrieved = _parse_time(record.get("retrieved_at"), f"{label}/retrieved_at", errors)
        if retrieved and not (mode == "fixture" and allow_fixture) and abs((now - retrieved).total_seconds()) > 86400:
            errors.append(f"{label}: 本轮抓取超过24小时，必须重新实时核验")
        artifact_text = _text(record.get("artifact_path"))
        artifact = (base_dir / artifact_text).resolve()
        if not artifact_text or base_dir not in artifact.parents or not artifact.is_file():
            errors.append(f"{label}: artifact不存在或越出政策取证目录")
        else:
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if digest != _text(record.get("artifact_sha256")):
                errors.append(f"{label}: artifact SHA256不一致")
        if _text(record.get("validity_status")) != "current":
            errors.append(f"{label}: 只有现行政策证据可支撑前台政策")
        if _text(record.get("application_status")) not in APPLICATION_STATUSES:
            errors.append(f"{label}: application_status不合法")

    for source_id in sorted(frontend_source_ids):
        valid_records = records_by_source.get(source_id, [])
        if not valid_records:
            errors.append(f"前台政策来源{source_id}: 缺少本轮正式政策取证")

    for candidate in policy_search_ledger.get("policy_candidates", []) if isinstance(policy_search_ledger, dict) else []:
        if not isinstance(candidate, dict):
            continue
        candidate_sources = {_text(value) for value in candidate.get("formal_policy_source_ids", [])}
        if candidate_sources & frontend_source_ids and _text(candidate.get("status")) not in CURRENT_CANDIDATE_STATUSES:
            errors.append(f"{_text(candidate.get('id')) or '政策候选'}: 非现行候选不得支撑前台政策")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate fresh official policy evidence for report policy cards.")
    parser.add_argument("policy_evidence")
    parser.add_argument("--report-data", required=True)
    parser.add_argument("--policy-search-ledger", required=True)
    parser.add_argument("--fixture-mode", action="store_true")
    args = parser.parse_args(argv)
    target = Path(args.policy_evidence)
    try:
        errors = validate_policy_evidence(load_data(target), load_data(args.report_data), load_data(args.policy_search_ledger), base_dir=target.parent, allow_fixture=args.fixture_mode)
    except (OSError, ValueError) as error:
        print(f"无法读取政策取证台账：{error}", file=sys.stderr)
        return 2
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("通过：前台政策均有本轮官方原文或附件取证")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
