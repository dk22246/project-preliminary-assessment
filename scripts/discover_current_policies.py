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
from policy_roles import required_paths_for_roles
from report_core import load_data


TRANSIENT_STATUS = {429, 502, 503, 504}
BLOCKED_STATUS = {401, 403}
ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = ROOT / "references" / "policy-source-registry.json"


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


def _source_registry() -> dict[str, dict]:
    payload = json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8-sig"))
    return {str(row.get("department", "")).strip(): row for row in payload.get("departments", [])}


def _route_tasks(research_ledger: dict, report_data: dict) -> list[dict]:
    landing_by_id = {str(item.get("id", "")): item for item in report_data.get("landing_businesses", [])}
    candidates = {str(item.get("id", "")): item for item in research_ledger.get("business_candidates", [])}
    registry = _source_registry()
    tasks: dict[tuple[str, str], dict] = {}
    for route in research_ledger.get("department_routes", []):
        landing_id = str(route.get("landing_business_id", "")).strip()
        department = str(route.get("department", "")).strip()
        registered = registry.get(department, {})
        entry_url = str(route.get("entry_url") or route.get("department_entry_url") or registered.get("entry_url") or "").strip()
        if not landing_id or not department or not entry_url:
            continue
        business = landing_by_id.get(landing_id, {})
        topic = str(business.get("business") or business.get("name") or route.get("matter") or "政策检索")
        key = (department, entry_url)
        task = tasks.setdefault(key, {
            "department": department,
            "entry_url": entry_url,
            "entry_kind": str(registered.get("entry_kind") or "policy_directory"),
            "routes": [],
            "roles": set(),
        })
        role = str(route.get("department_role") or "primary_regulator")
        task["roles"].add(role)
        fact_ids: set[str] = set()
        for candidate_id in route.get("candidate_ids", []):
            fact_ids.update(str(value) for value in candidates.get(str(candidate_id), {}).get("fact_ids", []))
        task["routes"].append({"route": route, "landing_id": landing_id, "topic": topic, "fact_ids": sorted(fact_ids), "role": role})
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
    scan_profiles: list[dict] = []
    search_groups: dict[tuple[str, str], dict] = {}
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
        profile_id = f"DSP{len(scan_profiles) + 1:02d}"
        required_paths = required_paths_for_roles(set(task["roles"]))
        profile_runs: list[dict] = []
        for path in required_paths:
            is_machine_complete = bool(receipt) and path == "department_documents" and task["entry_kind"] != "homepage"
            status = "complete" if is_machine_complete else "failed" if not receipt else "partial"
            profile_runs.append({
                "path": path,
                "status": status,
                "entry_url": task["entry_url"],
                "query": "；".join(sorted({item["topic"] for item in task["routes"]})),
                "checked_at": receipt.get("revalidated_at") if receipt else _timestamp(),
                "result_count": 1 if is_machine_complete else 0,
                "result_source_ids": [source_id] if is_machine_complete and source_id else [],
                "evidence_record_ids": [evidence_id] if is_machine_complete and evidence_id else [],
                "receipt_id": f"{profile_id}-{path}",
                "result_summary": (
                    "本轮已实时复验官方政策文件目录入口。"
                    if is_machine_complete
                    else failure or "统一入口已复验；该角色路径仍需定位具体官方目录或检索结果后补全。"
                ),
            })
        scan_profiles.append({"id": profile_id, "department": task["department"], "runs": profile_runs})
        for item in task["routes"]:
            group_key = (item["landing_id"], item["topic"])
            group = search_groups.setdefault(group_key, {
                "landing_business_id": item["landing_id"], "topic": item["topic"],
                "route_ids": [], "fact_ids": [], "department_searches": [],
                "candidate_policy_ids": [], "coverage_status": "research_incomplete",
            })
            route_id = str(item["route"].get("id", ""))
            if route_id and route_id not in group["route_ids"]:
                group["route_ids"].append(route_id)
            for fact_id in item["fact_ids"]:
                if fact_id not in group["fact_ids"]:
                    group["fact_ids"].append(fact_id)
            if not any(row.get("department") == task["department"] for row in group["department_searches"]):
                group["department_searches"].append({
                    "department": task["department"],
                    "department_role": item["role"],
                    "routing_basis": str(item["route"].get("routing_basis") or item["route"].get("route_rule_id") or "研究底稿主管部门路由"),
                    "profile_id": profile_id,
                })
    searches = [{"id": f"PS{index:02d}", **row} for index, row in enumerate(search_groups.values(), 1)]
    result = {
        "policy_evidence": {"version": "1.0", "enterprise": research_ledger.get("enterprise", ""), "researched_at": _timestamp(), "mode": "formal", "records": evidence_records},
        "policy_search_ledger": {"version": "1.0", "enterprise": research_ledger.get("enterprise", ""), "researched_at": _timestamp(), "search_mode": "realtime", "draft_only": True, "landing_business_hypotheses": [], "department_scan_profiles": scan_profiles, "searches": searches, "policy_candidates": []},
        "metrics": metrics,
    }
    # Discovery is a non-destructive first pass. It must never overwrite the
    # formal ledgers maintained in the project root.
    (out_dir / "policy-evidence-draft.json").write_text(json.dumps(result["policy_evidence"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "policy-search-ledger-draft.json").write_text(json.dumps(result["policy_search_ledger"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "policy-findings-fragment.json").write_text(json.dumps({
        "version": "1.0",
        "enterprise": research_ledger.get("enterprise", ""),
        "researched_at": result["policy_search_ledger"]["researched_at"],
        "sources": [
            {"key": record["policy_source_id"], "type": "policy_search_receipt", "name": record["title"], "issuer": record["issuer"], "date": record["published_at"], "location": record["final_url"], "used_in": "后台实时政策检索回执"}
            for record in evidence_records
        ],
        "search": {
            "department_scan_profiles": scan_profiles,
            "searches": searches,
            "policy_candidates": [],
        },
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def merge_discovery_fragment(policy_findings_path: Path, fragment_path: Path) -> dict:
    """Merge machine scan receipts without overwriting Agent policy judgments."""
    current = json.loads(Path(policy_findings_path).read_text(encoding="utf-8-sig"))
    fragment = json.loads(Path(fragment_path).read_text(encoding="utf-8-sig"))
    if str(current.get("enterprise", "")).strip() != str(fragment.get("enterprise", "")).strip():
        raise ValueError("政策发现片段与policy-findings.json企业主体不一致")
    current["researched_at"] = fragment["researched_at"]
    retained_sources = [row for row in current.get("sources", []) if row.get("type") != "policy_search_receipt"]
    current["sources"] = retained_sources + fragment.get("sources", [])
    search = current.setdefault("search", {})
    search["department_scan_profiles"] = fragment.get("search", {}).get("department_scan_profiles", [])
    previous = {
        (str(row.get("landing_business_key") or row.get("landing_business_id") or ""), str(row.get("topic", ""))): row
        for row in search.get("searches", [])
    }
    refreshed = []
    for row in fragment.get("search", {}).get("searches", []):
        key = (str(row.get("landing_business_key") or row.get("landing_business_id") or ""), str(row.get("topic", "")))
        old = previous.get(key, {})
        if old.get("candidate_policy_keys"):
            row["candidate_policy_keys"] = old["candidate_policy_keys"]
        elif old.get("candidate_policy_ids"):
            row["candidate_policy_ids"] = old["candidate_policy_ids"]
        row["coverage_status"] = "research_incomplete"
        refreshed.append(row)
    search["searches"] = refreshed
    temporary = Path(policy_findings_path).with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(policy_findings_path)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover current official policy material from routed departments")
    parser.add_argument("research_ledger")
    parser.add_argument("--report-data", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args()
    result = discover_current_policies(load_data(args.research_ledger), load_data(args.report_data), Path(args.out_dir), max_concurrency=args.max_concurrency, max_retries=args.max_retries)
    print(json.dumps(result["metrics"], ensure_ascii=False))
    return 0 if not result["metrics"]["failed_requests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
