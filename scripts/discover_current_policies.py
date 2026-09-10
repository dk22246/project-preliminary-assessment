#!/usr/bin/env python3
"""Discover current official policy material from business-triggered department routes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import sleep as default_sleep
from threading import Lock
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from policy_cache import PolicyCache
from report_core import load_data


TRANSIENT_STATUS = {429, 502, 503, 504}
BLOCKED_STATUS = {401, 403}


def _timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _default_fetch(url: str, headers: dict[str, str]) -> dict:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=40) as response:  # nosec B310: official URLs are routed by the skill.
            return {"status": response.status, "final_url": response.geturl(), "body": response.read(), "headers": dict(response.headers.items())}
    except Exception as exc:  # urllib exposes HTTP errors as exceptions.
        status = int(getattr(exc, "code", 0) or 0)
        return {"status": status, "final_url": url, "headers": {}, "error": str(exc)}


def _request_with_retry(url: str, cache: PolicyCache, fetch: Callable, *, dynamic: bool, max_retries: int, sleep: Callable) -> tuple[dict | None, int, str | None]:
    retries = 0
    for attempt in range(max_retries + 1):
        checked_at = _timestamp()
        try:
            receipt = cache.revalidate(url, fetch, dynamic=dynamic, revalidated_at=checked_at)
            return receipt, retries, None
        except RuntimeError as exc:
            message = str(exc)
            status_text = message.rsplit(" ", 1)[-1]
            try:
                status = int(status_text)
            except ValueError:
                status = 0
            if status in TRANSIENT_STATUS and attempt < max_retries:
                retries += 1
                sleep(2 ** attempt)
                continue
            if status in BLOCKED_STATUS:
                return None, retries, "官方页面要求登录、验证码或拒绝访问，未尝试绕过"
            return None, retries, f"官方页面获取失败：{message}"
    return None, retries, "官方页面获取失败"


def _route_tasks(research_ledger: dict, report_data: dict) -> list[dict]:
    landing_by_id = {str(item.get("id", "")): item for item in report_data.get("landing_businesses", [])}
    tasks: dict[tuple[str, str], dict] = {}
    for route in research_ledger.get("department_routes", []):
        landing_id = str(route.get("landing_business_id", "")).strip()
        department = str(route.get("department", "")).strip()
        entry_url = str(route.get("entry_url") or route.get("department_entry_url") or "").strip()
        if not landing_id or not department or not entry_url:
            continue
        business = landing_by_id.get(landing_id, {})
        topic = str(business.get("business") or business.get("name") or route.get("matter") or "政策检索")
        key = (department, entry_url)
        task = tasks.setdefault(key, {"department": department, "entry_url": entry_url, "routes": []})
        task["routes"].append({"route": route, "landing_id": landing_id, "topic": topic})
    return list(tasks.values())


def _run_host_limited(task: dict, host_locks: dict[str, Lock], cache: PolicyCache, fetch: Callable, max_retries: int, sleep: Callable) -> tuple[dict | None, int, str | None]:
    host = urlsplit(task["entry_url"]).netloc.lower()
    with host_locks[host]:
        return _request_with_retry(task["entry_url"], cache, fetch, dynamic=False, max_retries=max_retries, sleep=sleep)


def discover_current_policies(
    research_ledger: dict,
    report_data: dict,
    out_dir: Path,
    *,
    fetch: Callable[[str, dict[str, str]], dict] | None = None,
    max_concurrency: int = 4,
    max_retries: int = 2,
    sleep: Callable[[float], None] = default_sleep,
) -> dict:
    """Collect each unique routed department entry once; policy eligibility remains undecided."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = PolicyCache(out_dir.parent / ".cache" / "policies")
    fetch = fetch or _default_fetch
    tasks = _route_tasks(research_ledger, report_data)
    host_locks = {urlsplit(task["entry_url"]).netloc.lower(): Lock() for task in tasks}
    outcomes: dict[tuple[str, str], tuple[dict | None, int, str | None]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_concurrency, 4))) as executor:
        future_map = {
            executor.submit(_run_host_limited, task, host_locks, cache, fetch, max_retries, sleep): (task["department"], task["entry_url"])
            for task in tasks
        }
        for future in as_completed(future_map):
            outcomes[future_map[future]] = future.result()
    evidence_records: list[dict] = []
    searches: list[dict] = []
    metrics = {"requests": 0, "successful_requests": 0, "failed_requests": 0, "retries": 0}
    source_counter = 0
    for task in tasks:
        key = (task["department"], task["entry_url"])
        receipt, retries, failure = outcomes[key]
        metrics["retries"] += retries
        metrics["requests"] += retries + 1
        evidence_id = ""
        source_id = ""
        if receipt:
            metrics["successful_requests"] += 1
            source_counter += 1
            evidence_id = f"PE{source_counter:02d}"
            source_id = f"P{source_counter:02d}"
            body_path = out_dir / f"{evidence_id}.bin"
            cached_path = cache._paths(task["entry_url"])[1]
            body = cached_path.read_bytes()
            body_path.write_bytes(body)
            evidence_records.append({
                "id": evidence_id, "policy_source_id": source_id, "requested_url": task["entry_url"],
                "final_url": receipt.get("final_url", task["entry_url"]), "retrieved_at": receipt["retrieved_at"],
                "revalidated_at": receipt["revalidated_at"], "http_status": 200,
                "revalidation_http_status": receipt["http_status"],
                "content_type": str(receipt.get("content_type", "application/octet-stream")).split(";", 1)[0].strip(), "artifact_path": str(body_path),
                "artifact_sha256": hashlib.sha256(body).hexdigest(), "issuer": task["department"],
                "title": f"{task['department']}政策目录入口", "document_number": "目录入口，无单独文号",
                "published_at": datetime.now(timezone.utc).date().isoformat(),
                "validity_status": "unknown", "validity_basis": "目录入口仅用于发现正式政策，不据此判断政策现行有效",
                "validity_locator": "目录页", "application_status": "unknown", "application_basis": "待定位正式文件后核验", "application_locator": "目录页",
                "cached_artifact_created_at": receipt["cached_artifact_created_at"],
            })
        else:
            metrics["failed_requests"] += 1
        for item in task["routes"]:
            search_id = f"PS{len(searches) + 1:02d}"
            run = {
                "path": "department_documents", "status": "complete" if receipt else "failed", "entry_url": task["entry_url"],
                "query": item["topic"], "checked_at": receipt.get("revalidated_at") if receipt else _timestamp(),
                "result_count": 1 if receipt else 0, "result_source_ids": [source_id] if source_id else [],
                "evidence_record_ids": [evidence_id] if evidence_id else [], "receipt_id": evidence_id or f"FAIL-{search_id}",
                "result_summary": "已完成官方目录入口实时复验。" if receipt else failure,
            }
            searches.append({
                "id": search_id, "landing_business_id": item["landing_id"], "topic": item["topic"],
                "route_ids": [str(item["route"].get("id", ""))], "department_searches": [{
                    "department": task["department"], "department_role": "routed_department", "routing_basis": "研究底稿主管部门路由", "runs": [run],
                }], "candidate_policy_ids": [], "coverage_status": "research_incomplete",
            })
    result = {
        "policy_evidence": {"version": "1.0", "enterprise": research_ledger.get("enterprise", ""), "researched_at": _timestamp(), "mode": "formal", "records": evidence_records},
        "policy_search_ledger": {"version": "1.0", "enterprise": research_ledger.get("enterprise", ""), "researched_at": _timestamp(), "search_mode": "realtime", "landing_business_hypotheses": [], "searches": searches, "policy_candidates": []},
        "metrics": metrics,
    }
    (out_dir.parent / "policy-evidence.json").write_text(json.dumps(result["policy_evidence"], ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir.parent / "policy-search-ledger.json").write_text(json.dumps(result["policy_search_ledger"], ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover current official policy material from routed departments")
    parser.add_argument("research_ledger")
    parser.add_argument("--report-data", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--read-timeout", type=int, default=30)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args()
    result = discover_current_policies(load_data(args.research_ledger), load_data(args.report_data), Path(args.out_dir), max_concurrency=args.max_concurrency, max_retries=args.max_retries)
    print(json.dumps(result["metrics"], ensure_ascii=False))
    return 0 if not result["metrics"]["failed_requests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
