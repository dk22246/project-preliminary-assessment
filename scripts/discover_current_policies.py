#!/usr/bin/env python3
"""Bounded official-policy discovery; policy judgment remains with the agent."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from time import sleep as default_sleep
from threading import Lock
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from policy_cache import PolicyCache, workspace_cache
from policy_roles import required_paths_for_roles
from policy_path_tasks import official_url, resolve_paths
from report_core import load_data

TRANSIENT_STATUS = {429, 502, 503, 504}
BLOCKED_STATUS = {401, 403}
ROOT = Path(__file__).resolve().parents[1]
SOURCE_REGISTRY = ROOT / "references" / "policy-source-registry.json"
FORMAL_CLUES = ("政策", "办法", "细则", "规定", "通知", "公告", "方案", "实施", "申报", "奖补", "资金", "指南")
NON_FORMAL_CLUES = ("新闻", "动态", "简报", "媒体", "解读", "转载")
ATTACHMENT_SUFFIXES = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")
MAX_CANDIDATES_PER_ENTRY = 8
MAX_ATTACHMENTS_PER_CANDIDATE = 4
TOPIC_ALIASES = {
    "国际贸易": ("国际贸易", "跨境贸易", "外贸", "进出口"),
    "跨境电商": ("跨境电商", "跨境电子商务", "电子商务"),
    "境外投资": ("境外投资", "对外投资", "odi"),
    "EF账户": ("EF账户", "EF业务", "多功能自由贸易账户"),
    "个人所得税": ("个人所得税",),
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _default_fetch(url: str, headers: dict[str, str], timeout: float = 20) -> dict:
    try:
        with urlopen(Request(url, headers=headers, method="GET"), timeout=timeout) as response:  # nosec B310
            if official_url(url) and not official_url(response.geturl()):
                return {"status": 403, "final_url": response.geturl(), "headers": {}, "error": "官方入口重定向到非官方地址"}
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "html" in content_type:
                text, _ = _decode_html(body, content_type)
                if any(marker in text.lower() for marker in ("访问过于频繁", "请输入验证码", "access denied", "人机验证")):
                    return {"status": 403, "final_url": response.geturl(), "headers": {}, "error": "访问拦截页不是政策证据"}
            return {
                "status": response.status,
                "final_url": response.geturl(),
                "body": body,
                "headers": dict(response.headers.items()),
            }
    except Exception as exc:
        return {
            "status": int(getattr(exc, "code", 0) or 0),
            "final_url": url,
            "headers": {},
            "error": str(exc),
        }


def _request_with_retry(
    url: str,
    cache: PolicyCache,
    fetch: Callable,
    *,
    dynamic: bool,
    max_retries: int,
    sleep: Callable,
) -> tuple[dict | None, int, str | None]:
    retries = 0
    for attempt in range(max_retries + 1):
        try:
            receipt = cache.revalidate(
                url,
                fetch,
                dynamic=dynamic,
                revalidated_at=_timestamp(),
            )
            return receipt, retries, None
        except RuntimeError as exc:
            message = str(exc)
            try:
                status = int(message.rsplit(" ", 1)[-1])
            except ValueError:
                status = 0
            if status in TRANSIENT_STATUS and attempt < max_retries:
                retries += 1
                sleep(2**attempt)
                continue
            if status in BLOCKED_STATUS:
                return None, retries, "官方页面要求登录、验证码或拒绝访问，未尝试绕过"
            return None, retries, f"官方页面获取失败：{message}"
    return None, retries, "官方页面获取失败"


def _source_registry() -> dict[str, dict]:
    payload = json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8-sig"))
    return {
        str(row.get("department", "")).strip(): row
        for row in payload.get("departments", [])
    }


def _normalise_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def _stable_key(prefix: str, *parts: str) -> str:
    value = "|".join(
        _normalise_url(part) if part.startswith(("http://", "https://")) else part.strip()
        for part in parts
    )
    return f"{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href.strip(), " ".join("".join(self._text).split())))
            self._href = None
            self._text = []


def _decode_html(body: bytes, content_type: str = "") -> tuple[str, str | None]:
    charset = None
    match = re.search(r"charset\s*=\s*[\"']?\s*([\w.-]+)", content_type, re.I)
    if match:
        charset = match.group(1)
    if body.startswith(b"\xef\xbb\xbf"):
        charset = "utf-8-sig"
    for encoding in ([charset] if charset else []) + ["utf-8", "gb18030", "big5"]:
        try:
            return body.decode(encoding), None
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace"), "网页字符集无法可靠解码，链接文字可能不完整"


def _links(body: bytes, base: str, content_type: str = "") -> tuple[list[tuple[str, str]], str | None]:
    text, decode_warning = _decode_html(body, content_type)
    parser = _LinkParser()
    parser.feed(text)
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for href, title in parser.links:
        url = _normalise_url(urljoin(base, href))
        if urlsplit(url).scheme not in {"http", "https"} or url in seen:
            continue
        seen.add(url)
        result.append((url, title))
    return result, decode_warning


def _route_tasks(research_ledger: dict, report_data: dict) -> list[dict]:
    landing = {str(x.get("id", "")): x for x in report_data.get("landing_businesses", [])}
    business_candidates = {
        str(x.get("id", "")): x for x in research_ledger.get("business_candidates", [])
    }
    facts = {str(x.get("id", "")): x for x in research_ledger.get("fact_ledger", [])}
    registry = _source_registry()
    tasks: dict[tuple[str, str], dict] = {}
    for route in research_ledger.get("department_routes", []):
        landing_id = str(route.get("landing_business_id", "")).strip()
        department = str(route.get("department", "")).strip()
        registered = registry.get(department, {})
        entry_url = str(
            route.get("entry_url")
            or route.get("department_entry_url")
            or registered.get("entry_url")
            or ""
        ).strip()
        if not landing_id or not department or not entry_url:
            continue
        entry_url = _normalise_url(entry_url)
        business = landing.get(landing_id, {})
        business_topic = str(business.get("business") or business.get("name") or "政策检索")
        route_topic = str(route.get("matter") or business_topic)
        task = tasks.setdefault(
            (department, entry_url),
            {
                "department": department,
                "entry_url": entry_url,
                "entry_kind": str(registered.get("entry_kind") or ("homepage" if urlsplit(entry_url).path in {"", "/"} else "policy_directory")),
                "routes": [],
                "roles": set(),
                "path_entries": dict(registered.get("path_entries", {})),
            },
        )
        role = str(route.get("department_role") or "primary_regulator")
        task["roles"].add(role)
        task["path_entries"].update(route.get("path_entries", {}))
        fact_ids: set[str] = set()
        for candidate_id in route.get("candidate_ids", []):
            fact_ids.update(
                str(value)
                for value in business_candidates.get(str(candidate_id), {}).get("fact_ids", [])
            )
        keywords = {business_topic, route_topic}
        for field in ("policy_topics", "query_terms", "keywords"):
            values = route.get(field, [])
            if isinstance(values, str):
                values = [values]
            if isinstance(values, (list, tuple, set)):
                keywords.update(
                    value.strip() for value in values
                    if isinstance(value, str) and value.strip()
                )
        for fact_id in fact_ids:
            fact = facts.get(fact_id, {})
            for field in ("action", "object", "enterprise_role", "name", "topic"):
                value = str(fact.get(field) or "").strip()
                if value:
                    keywords.add(value)
        task["routes"].append(
            {
                "route": route,
                "landing_id": landing_id,
                "topic": route_topic,
                "keywords": sorted(keywords),
                "fact_ids": sorted(fact_ids),
                "role": role,
            }
        )
    return list(tasks.values())


def _topic_terms(topic: str) -> list[str]:
    terms = [term for term in re.split(r"[\s、，,；;/:（）()与及]+", topic) if len(term) >= 2]
    aliases = [
        alias
        for term in terms
        for theme, theme_aliases in TOPIC_ALIASES.items()
        if theme.lower() in term.lower()
        for alias in theme_aliases
    ]
    return list(dict.fromkeys(terms + aliases)) or [topic]


def _candidate_links(
    entry_url: str,
    body: bytes,
    content_type: str,
    topics: set[str],
) -> tuple[list[dict], str | None]:
    host = urlsplit(entry_url).netloc.lower()
    links, decode_warning = _links(body, entry_url, content_type)
    scored = []
    terms = [term.lower() for topic in topics for term in _topic_terms(topic)]
    for url, title in links:
        parsed = urlsplit(url)
        if parsed.netloc.lower() != host or url == entry_url:
            continue
        text = f"{title} {parsed.path}".lower()
        attachment = parsed.path.lower().endswith(ATTACHMENT_SUFFIXES)
        topic_hits = sum(term in text for term in terms if term)
        formal_hits = sum(clue in text for clue in FORMAL_CLUES)
        if topic_hits == 0:
            continue
        if any(clue in text for clue in NON_FORMAL_CLUES) and not attachment:
            continue
        if not attachment and formal_hits == 0:
            continue
        scored.append(
            (
                topic_hits * 20 + formal_hits * 2 + int(attachment),
                url,
                title or "官方政策候选链接",
                attachment,
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    return (
        [
            {"url": url, "title": title, "is_attachment": attachment}
            for _, url, title, attachment in scored[:MAX_CANDIDATES_PER_ENTRY]
        ],
        decode_warning,
    )


def _is_dynamic_material(url: str, title: str) -> bool:
    text = f"{url} {title}"
    return any(clue in text for clue in ("申报", "失效", "公示", "公告", "动态"))


def _evidence(
    url: str,
    receipt: dict,
    body: bytes,
    out_dir: Path,
    *,
    issuer: str,
    title: str,
    kind: str,
    evidence_id: str,
    source_id: str,
    stable_key: str,
) -> dict:
    digest = hashlib.sha256(body).hexdigest()
    evidence_key = _stable_key("evidence", url, digest)
    artifact_name = _stable_key("artifact", url, digest).replace(":", "-") + ".bin"
    artifact_path = out_dir / artifact_name
    artifact_path.write_bytes(body)
    return {
        "id": evidence_id,
        "key": evidence_key,
        "stable_key": evidence_key,
        "policy_source_id": source_id,
        "source_key": stable_key,
        "policy_source_key": stable_key,
        "evidence_type": kind,
        "requested_url": url,
        "final_url": receipt.get("final_url", url),
        "retrieved_at": receipt.get("retrieved_at"),
        "revalidated_at": receipt.get("revalidated_at"),
        "http_status": receipt.get("http_status", 200),
        "content_type": str(receipt.get("content_type", "application/octet-stream")).split(";", 1)[0].strip(),
        "artifact_path": str(artifact_path),
        "artifact_sha256": digest,
        "issuer": issuer,
        "title": title,
        "document_number": None,
        "published_at": None,
        "validity_status": "unknown",
        "validity_basis": "机器仅保存官方来源证据；正式性、效力和适用资格待人工核验",
        "validity_locator": "待人工定位",
        "application_status": "unknown",
        "application_basis": "待人工核验，不由链接发现自动判定",
        "application_locator": "待人工定位",
        "cached_artifact_created_at": receipt.get("cached_artifact_created_at"),
    }


def _fetch_batch(
    urls: list[dict],
    cache: PolicyCache,
    fetch: Callable,
    *,
    max_workers: int,
    max_retries: int,
    sleep: Callable,
) -> dict[str, tuple[dict | None, int, str | None]]:
    host_locks = {
        urlsplit(item["url"]).netloc.lower(): Lock()
        for item in urls
    }
    results = {}

    def run(item: dict):
        url = item["url"]
        host = urlsplit(url).netloc.lower()
        lock = host_locks[host]
        with lock:
            return url, _request_with_retry(
                url,
                cache,
                fetch,
                dynamic=item.get("dynamic", False),
                max_retries=max_retries,
                sleep=sleep,
            )

    with ThreadPoolExecutor(max_workers=max(1, min(4, max_workers, len(urls)))) as executor:
        futures = [executor.submit(run, item) for item in urls]
        for future in as_completed(futures):
            url, result = future.result()
            results[url] = result
    return results


def discover_current_policies(
    research_ledger: dict,
    report_data: dict,
    out_dir: Path,
    *,
    fetch: Callable[[str, dict[str, str]], dict] | None = None,
    max_concurrency: int = 4,
    max_retries: int = 2,
    sleep: Callable[[float], None] = default_sleep,
    request_timeout: float = 20,
) -> dict:
    """Discover bounded same-host policy material with one fetch per URL per round."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = workspace_cache(out_dir)
    fetch = fetch or (lambda url, headers: _default_fetch(url, headers, request_timeout))
    tasks = _route_tasks(research_ledger, report_data)
    entry_items = []
    seen_entries = set()
    for task in tasks:
        if task["entry_url"] not in seen_entries:
            # 目录页是发现新政策的入口，必须本轮重新访问，不得跨轮复用缓存
            entry_items.append({"url": task["entry_url"], "dynamic": True})
            seen_entries.add(task["entry_url"])
    entry_results = _fetch_batch(
        entry_items,
        cache,
        fetch,
        max_workers=max_concurrency,
        max_retries=max_retries,
        sleep=sleep,
    )

    metrics = {"requests": 0, "successful_requests": 0, "failed_requests": 0, "retries": 0}
    fetched: dict[str, tuple[dict | None, int, str | None]] = entry_results
    for _, (_, retries, _) in entry_results.items():
        metrics["requests"] += retries + 1
        metrics["retries"] += retries
    for receipt, _, _ in entry_results.values():
        if receipt:
            metrics["successful_requests"] += 1
        else:
            metrics["failed_requests"] += 1

    # Resolve and fetch real role-specific directories, sharing identical URLs.
    path_items = {}
    for task in tasks:
        entry = task["entry_url"]
        receipt = entry_results[entry][0]
        links = _links(cache._paths(entry)[1].read_bytes(), entry, str(receipt.get("content_type", "")))[0] if receipt else []
        task["resolved_paths"] = resolve_paths(
            required_paths_for_roles(task["roles"]), links, entry_url=entry,
            entry_kind=task["entry_kind"], explicit=task["path_entries"],
        )
        for path, url in task["resolved_paths"].items():
            if url not in fetched:
                path_items[url] = {"url": url, "dynamic": True}
    path_results = _fetch_batch(list(path_items.values()), cache, fetch, max_workers=max_concurrency, max_retries=max_retries, sleep=sleep)
    for url, result in path_results.items():
        fetched[url] = result
        metrics["requests"] += result[1] + 1
        metrics["retries"] += result[1]
        metrics["successful_requests" if result[0] else "failed_requests"] += 1

    candidate_plans: dict[str, dict] = {}
    decode_warnings: list[dict] = []
    task_discovered: dict[str, list[dict]] = {}
    entry_keywords: dict[str, set[str]] = {}
    for task in tasks:
        entry_keywords.setdefault(task["entry_url"], set()).update(
            keyword
            for route in task["routes"]
            for keyword in route["keywords"]
        )
    for task in tasks:
        entry = task["entry_url"]
        receipt, _, failure = entry_results[entry]
        if not receipt:
            task_discovered[entry] = []
            continue
        body = cache._paths(entry)[1].read_bytes()
        discovered, warning = _candidate_links(
            entry,
            body,
            str(receipt.get("content_type", "")),
            entry_keywords[entry],
        )
        if warning:
            decode_warnings.append({"url": entry, "warning": warning})
        task["decode_warning"] = bool(warning)
        for path_url in set(task["resolved_paths"].values()) - {entry}:
            path_receipt = fetched.get(path_url, (None, 0, None))[0]
            if not path_receipt:
                continue
            extra, path_warning = _candidate_links(path_url, cache._paths(path_url)[1].read_bytes(), str(path_receipt.get("content_type", "")), entry_keywords[entry])
            seen = {item["url"] for item in discovered}
            discovered.extend(item for item in extra if item["url"] not in seen)
            if path_warning:
                decode_warnings.append({"url": path_url, "warning": path_warning})
        task_discovered[entry] = discovered
        for item in discovered:
            candidate_plans.setdefault(
                item["url"],
                {
                    **item,
                    "dynamic": _is_dynamic_material(item["url"], item["title"]),
                    "parents": [],
                },
            )
            candidate_plans[item["url"]]["parents"].append(entry)

    candidate_results = _fetch_batch(
        [item for url, item in candidate_plans.items() if url not in fetched],
        cache,
        fetch,
        max_workers=max_concurrency,
        max_retries=max_retries,
        sleep=sleep,
    )
    for url, (receipt, retries, error) in candidate_results.items():
        fetched[url] = (receipt, retries, error)
        metrics["requests"] += retries + 1
        metrics["retries"] += retries
        if receipt:
            metrics["successful_requests"] += 1
        else:
            metrics["failed_requests"] += 1
    candidate_results.update({url: fetched[url] for url in candidate_plans if url not in candidate_results and url in fetched})

    # A candidate正文 may point to supporting files.  Discover only direct
    # same-host attachments and fetch them in the same bounded batch.
    attachment_plans: dict[str, dict] = {}
    attachments_by_parent: dict[str, list[str]] = {}
    for url, item in candidate_plans.items():
        receipt, _, _ = candidate_results.get(url, (None, 0, None))
        if not receipt or item["is_attachment"]:
            continue
        body = cache._paths(url)[1].read_bytes()
        links, warning = _links(body, url, str(receipt.get("content_type", "")))
        if warning:
            decode_warnings.append({"url": url, "warning": warning})
        parent_attachments = []
        for attachment_url, title in links:
            if urlsplit(attachment_url).netloc.lower() != urlsplit(url).netloc.lower() and not official_url(attachment_url):
                continue
            if not urlsplit(attachment_url).path.lower().endswith(ATTACHMENT_SUFFIXES):
                continue
            if attachment_url not in parent_attachments and len(parent_attachments) < MAX_ATTACHMENTS_PER_CANDIDATE:
                parent_attachments.append(attachment_url)
                if attachment_url not in fetched:
                    attachment_plans.setdefault(
                        attachment_url,
                        {
                            "url": attachment_url,
                            "title": title or "政策相关附件",
                            "is_attachment": True,
                            "dynamic": _is_dynamic_material(attachment_url, title),
                        },
                    )
        if parent_attachments:
            attachments_by_parent[url] = parent_attachments
    attachment_results = _fetch_batch(
        list(attachment_plans.values()),
        cache,
        fetch,
        max_workers=max_concurrency,
        max_retries=max_retries,
        sleep=sleep,
    )
    for url, result in attachment_results.items():
        fetched[url] = result
        receipt, retries, _ = result
        metrics["requests"] += retries + 1
        metrics["retries"] += retries
        if receipt:
            metrics["successful_requests"] += 1
        else:
            metrics["failed_requests"] += 1

    records: list[dict] = []
    sources: dict[str, dict] = {}
    failures: list[dict] = []
    record_by_url: dict[str, dict] = {}
    source_numbers: dict[str, str] = {}
    for number, url in enumerate(sorted(fetched), 1):
        source_numbers[url] = f"P{number:02d}"

    def save_success(url: str, receipt: dict, issuer: str, title: str, kind: str) -> dict:
        if url in record_by_url:
            return record_by_url[url]
        source_id = source_numbers[url]
        stable_key = _stable_key("source", url)
        evidence_id = f"PE{len(records) + 1:02d}"
        body = cache._paths(url)[1].read_bytes()
        record = _evidence(
            url,
            receipt,
            body,
            out_dir,
            issuer=issuer,
            title=title,
            kind=kind,
            evidence_id=evidence_id,
            source_id=source_id,
            stable_key=stable_key,
        )
        records.append(record)
        record_by_url[url] = record
        sources[source_id] = {
            "id": source_id,
            "key": stable_key,
            "stable_key": stable_key,
            "policy_source_key": stable_key,
            "type": "policy_search_receipt" if kind == "department_entry" else "policy_source",
            "name": title,
            "issuer": issuer,
            "date": None,
            "location": record["final_url"],
            "evidence_record_ids": [evidence_id],
            "evidence_keys": [record["key"]],
            "artifact_sha256": record["artifact_sha256"],
            "revalidated_at": record["revalidated_at"],
            "used_in": "目录线索及机器复验回执" if kind == "department_entry" else "目录发现的具体官方路径，待人工确认正式性",
        }
        return record

    for task in tasks:
        entry = task["entry_url"]
        receipt, _, failure = entry_results[entry]
        if receipt:
            save_success(entry, receipt, task["department"], f"{task['department']}政策目录入口", "department_entry")
        else:
            failures.append({"url": entry, "error": failure or "官方页面获取失败", "evidence_type": "department_entry"})
        for path, path_url in task["resolved_paths"].items():
            path_receipt, _, path_failure = fetched.get(path_url, (None, 0, "未执行"))
            if path_receipt:
                save_success(path_url, path_receipt, task["department"], f"{task['department']}/{path}", "department_entry")
            elif path_url != entry:
                failures.append({"url": path_url, "error": path_failure, "evidence_type": "department_entry"})
        for item in task_discovered.get(entry, []):
            receipt, _, failure = candidate_results.get(item["url"], (None, 0, "未抓取"))
            if receipt:
                kind = "policy_attachment" if item["is_attachment"] else "policy_candidate_page"
                save_success(item["url"], receipt, task["department"], item["title"], kind)
            else:
                failures.append({"url": item["url"], "error": failure or "官方页面获取失败", "evidence_type": "policy_attachment" if item["is_attachment"] else "policy_candidate_page"})
        for candidate_url in [item["url"] for item in task_discovered.get(entry, []) if not item["is_attachment"]]:
            for attachment_url in attachments_by_parent.get(candidate_url, []):
                receipt, _, failure = fetched.get(attachment_url, (None, 0, "未抓取"))
                if receipt:
                    item = attachment_plans.get(attachment_url, {"title": "政策相关附件"})
                    save_success(attachment_url, receipt, task["department"], item["title"], "policy_attachment")
                else:
                    failures.append({"url": attachment_url, "error": failure or "官方页面获取失败", "evidence_type": "policy_attachment"})

    profiles = []
    groups: dict[tuple[str, str], dict] = {}
    for task in tasks:
        entry = task["entry_url"]
        receipt, _, failure = entry_results[entry]
        profile_id = f"DSP{len(profiles) + 1:02d}"
        runs = []
        discovered = task_discovered.get(entry, [])
        for path in required_paths_for_roles(set(task["roles"])):
            path_url = task["resolved_paths"].get(path)
            path_receipt, _, path_failure = fetched.get(path_url, (None, 0, "未定位到具体官方路径"))
            candidates_ok = all(
                candidate_results.get(item["url"], (None, 0, None))[0]
                for item in discovered
            )
            path_links, warning = _links(cache._paths(path_url)[1].read_bytes(), path_url, str(path_receipt.get("content_type", ""))) if path_receipt else ([], None)
            # Completion means this concrete page was inspected; it never proves eligibility.
            complete = bool(path_receipt) and not warning and (path_url != entry or (not task.get("decode_warning") and candidates_ok and task["entry_kind"] == "policy_directory"))
            results = [record_by_url[item["url"]]["source_key"] for item in discovered if item["url"] in record_by_url] if path_url == entry else []
            runs.append({
                "path": path,
                "status": "complete" if complete else "failed" if path_url and not path_receipt else "partial",
                "entry_url": path_url or entry,
                "query": "；".join(sorted({item["topic"] for item in task["routes"]})),
                "checked_at": path_receipt.get("revalidated_at") if path_receipt else _timestamp(),
                "result_count": len(results) if path_url == entry else len(path_links),
                "result_source_keys": results if complete else [],
                "evidence_record_keys": [record_by_url[path_url]["key"]] if complete and path_url in record_by_url else [],
                "scan_scope": "具体页面及可见链接；不代表网站全量历史或政策效力判断",
                "receipt_id": f"{profile_id}-{path}",
                "result_summary": "已实时访问本路径的具体官方页面并保存原始证据；政策现行状态和适用条件独立核验。" if complete else path_failure or "该路径仍需补充可核验官方入口。",
            })
        profile_key = _stable_key("profile", task["department"], entry)
        profiles.append({"id": profile_id, "key": profile_key, "stable_key": profile_key, "department": task["department"], "runs": runs})
        for route_item in task["routes"]:
            key = (route_item["landing_id"], route_item["topic"])
            group = groups.setdefault(key, {
                "stable_key": _stable_key("search", task["department"], entry, *key),
                "key": _stable_key("search", task["department"], entry, *key),
                "profile_key": profile_key,
                "landing_business_id": key[0],
                "topic": key[1],
                "route_ids": [],
                "fact_ids": [],
                "department_searches": [],
                "discovered_candidate_keys": [],
                "coverage_status": "research_incomplete",
            })
            route = route_item["route"]
            if route.get("id") and route["id"] not in group["route_ids"]:
                group["route_ids"].append(route["id"])
            for fact_id in route_item["fact_ids"]:
                if fact_id not in group["fact_ids"]:
                    group["fact_ids"].append(fact_id)
            if not any(x.get("department") == task["department"] for x in group["department_searches"]):
                group["department_searches"].append({
                    "department": task["department"],
                    "department_role": route_item["role"],
                    "routing_basis": str(route.get("routing_basis") or route.get("route_rule_id") or "研究底稿主管部门路由"),
                    "entry_url": entry,
                    "profile_key": profile_key,
                })
            for item in task_discovered.get(entry, []):
                if not item["is_attachment"]:
                    candidate_id = _stable_key("candidate", item["url"])
                    if candidate_id not in group["discovered_candidate_keys"]:
                        group["discovered_candidate_keys"].append(candidate_id)

    searches = []
    candidates = []
    for index, group in enumerate(groups.values(), 1):
        search_id = f"PS{index:02d}"
        search = {"id": search_id, **group}
        search["discovered_candidate_keys"] = []
        searches.append(search)
        for candidate_key in group["discovered_candidate_keys"]:
            url = next((item["url"] for item in candidate_plans.values() if _stable_key("candidate", item["url"]) == candidate_key), None)
            if not url:
                continue
            record = record_by_url.get(url)
            candidate_id = f"PC{len(candidates) + 1:02d}"
            candidate_key = _stable_key("candidate-judgment", candidate_key, search["key"])
            search["discovered_candidate_keys"].append(candidate_key)
            fetch_result = candidate_results.get(url, (None, 0, "未抓取"))
            required_attachments = attachments_by_parent.get(url, [])
            attachment_status = "no_required" if fetch_result[0] else "unknown"
            if required_attachments:
                attachment_status = "complete" if all(fetched.get(item, (None, 0, None))[0] for item in required_attachments) else "unknown"
            candidates.append({
                "id": candidate_id,
                "key": candidate_key,
                "stable_key": candidate_key,
                "search_id": search_id,
                "search_key": search["key"],
                "title": record["title"] if record else candidate_plans[url]["title"],
                "url": record["final_url"] if record else url,
                "status": "candidate",
                "fetch_status": "success" if fetch_result[0] else "failed",
                "failure": None if fetch_result[0] else fetch_result[2],
                "eligibility_status": "unknown",
                "disposition": "needs_agent_review",
                "attachment_status": attachment_status,
                "formal_policy_source_keys": [record["source_key"]] if record else [],
                "evidence_record_keys": [record["key"]] if record else [],
                "qualification_basis": "仅因主题匹配的官方具体链接入选；不自动判断正式性、现行有效或企业资格",
            })

    now = _timestamp()
    evidence = {"version": "1.0", "enterprise": research_ledger.get("enterprise", ""), "researched_at": now, "mode": "formal", "records": records, "failures": failures, "decode_warnings": decode_warnings}
    ledger = {"version": "1.0", "enterprise": research_ledger.get("enterprise", ""), "researched_at": now, "search_mode": "realtime", "draft_only": True, "landing_business_hypotheses": [], "department_scan_profiles": profiles, "searches": searches, "discovered_candidates": candidates}
    fragment = {"version": "1.0", "enterprise": research_ledger.get("enterprise", ""), "researched_at": now, "sources": list(sources.values()), "evidence": records, "search": {"department_scan_profiles": profiles, "searches": searches, "discovered_candidates": candidates}, "failures": failures, "decode_warnings": decode_warnings}
    for name, payload in (("policy-evidence-draft.json", evidence), ("policy-search-ledger-draft.json", ledger), ("policy-findings-fragment.json", fragment)):
        (out_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"policy_evidence": evidence, "policy_search_ledger": ledger, "metrics": metrics}


def _merge_rows(old: list[dict], new: list[dict], *, preserve_completed: bool = False) -> list[dict]:
    index = {str(row.get("key") or row.get("stable_key") or row.get("id")): row for row in old}
    order = list(index)
    for row in new:
        key = str(row.get("key") or row.get("stable_key") or row.get("id"))
        previous = index.get(key)
        if previous and preserve_completed and previous.get("coverage_status") == "complete":
            continue
        index[key] = {**previous, **row} if previous else row
        if not previous:
            order.append(key)
    return [index[key] for key in order]


def _merge_profiles(old: list[dict], new: list[dict]) -> list[dict]:
    """Merge profile metadata and runs by path; never downgrade a complete run."""
    profiles = {str(row.get("key") or row.get("stable_key") or row.get("id")): row for row in old}
    order = list(profiles)
    for incoming in new:
        key = str(incoming.get("key") or incoming.get("stable_key") or incoming.get("id"))
        previous = profiles.get(key)
        if not previous:
            profiles[key] = incoming
            order.append(key)
            continue
        previous_runs = {str(run.get("path")): run for run in previous.get("runs", [])}
        run_order = list(previous_runs)
        for run in incoming.get("runs", []):
            path = str(run.get("path"))
            old_run = previous_runs.get(path)
            if old_run and old_run.get("status") == "complete" and run.get("status") != "complete":
                retained = dict(run)
                retained["historical_complete_run"] = old_run
                retained["review_status"] = "changed_pending_review" if run.get("status") == "partial" else "failed_pending_review"
                previous_runs[path] = retained
                continue
            if old_run and old_run.get("status") == "complete" and run.get("status") == "complete":
                retained = {**old_run, **run}
                if (old_run.get("result_source_keys"), old_run.get("evidence_record_keys")) != (run.get("result_source_keys"), run.get("evidence_record_keys")):
                    retained["review_status"] = "changed_pending_review"
                previous_runs[path] = retained
                continue
            previous_runs[path] = {**old_run, **run} if old_run else run
            if not old_run:
                run_order.append(path)
        profiles[key] = {**previous, **incoming, "runs": [previous_runs[path] for path in run_order]}
    return [profiles[key] for key in order]


def _source_changed(previous: dict, incoming: dict) -> bool:
    return previous.get("artifact_sha256") != incoming.get("artifact_sha256")


def _merge_searches(old: list[dict], new: list[dict]) -> list[dict]:
    """Use the newest run for current coverage while retaining complete history."""
    index = {str(row.get("key") or row.get("stable_key") or row.get("id")): row for row in old}
    order = list(index)
    for incoming in new:
        key = str(incoming.get("key") or incoming.get("stable_key") or incoming.get("id"))
        previous = index.get(key)
        if previous and previous.get("coverage_status") == "complete" and incoming.get("coverage_status") != "complete":
            history = list(previous.get("coverage_history", []))
            history.append({
                "researched_at": previous.get("researched_at") or previous.get("checked_at"),
                "coverage_status": "complete",
                "key": previous.get("key") or previous.get("stable_key"),
            })
            incoming = {**incoming, "coverage_history": history, "previous_complete": previous}
        index[key] = {**previous, **incoming} if previous else incoming
        if not previous:
            order.append(key)
    return [index[key] for key in order]


def merge_discovery_fragment(policy_findings_path: Path, fragment_path: Path) -> dict:
    """Incrementally merge evidence while preserving completed agent judgments."""
    path = Path(policy_findings_path)
    current = json.loads(path.read_text(encoding="utf-8-sig"))
    fragment = json.loads(Path(fragment_path).read_text(encoding="utf-8-sig"))
    if str(current.get("enterprise", "")).strip() != str(fragment.get("enterprise", "")).strip():
        raise ValueError("政策发现片段与policy-findings.json企业主体不一致")

    sources = {str(row.get("key") or row.get("stable_key") or row.get("id")): row for row in current.get("sources", [])}
    used_source_ids = {str(row.get("id")) for row in sources.values() if row.get("id")}
    source_id_remaps = {}
    changed_source_keys = set()
    for row in fragment.get("sources", []):
        key = str(row.get("key") or row.get("stable_key") or row.get("id"))
        previous = sources.get(key)
        if previous is None and str(row.get("id")) in used_source_ids:
            serial = 1
            while f"P{serial:02d}" in used_source_ids:
                serial += 1
            source_id_remaps[key] = f"P{serial:02d}"
            row = {**row, "id": source_id_remaps[key]}
        used_source_ids.add(str(row.get("id")))
        if previous and _source_changed(previous, row):
            changed_source_keys.add(key)
            row = {
                **row,
                "review_status": "changed_pending_review",
                "previous_evidence_record_ids": previous.get("evidence_record_ids", []),
                "previous_evidence_keys": previous.get("evidence_keys", []),
                "evidence_record_ids": list(dict.fromkeys(previous.get("evidence_record_ids", []) + row.get("evidence_record_ids", []))),
                "evidence_keys": list(dict.fromkeys(previous.get("evidence_keys", []) + row.get("evidence_keys", []))),
            }
        sources[key] = row

    search = current.setdefault("search", {})
    incoming = fragment.get("search", {})
    search["department_scan_profiles"] = _merge_profiles(search.get("department_scan_profiles", []), incoming.get("department_scan_profiles", []))
    search["searches"] = _merge_searches(search.get("searches", []), incoming.get("searches", []))
    search["discovered_candidates"] = _merge_rows(search.get("discovered_candidates", []), incoming.get("discovered_candidates", []))
    old_failures = search.get("failures", [])
    search["failures"] = old_failures + [failure for failure in fragment.get("failures", []) if failure not in old_failures]
    current["sources"] = list(sources.values())
    evidence = {str(row.get("key") or row.get("stable_key") or row.get("id")): row for row in current.get("evidence", [])}
    for row in fragment.get("evidence", []):
        key = str(row.get("key") or row.get("stable_key") or row.get("id"))
        source_key = str(row.get("policy_source_key") or row.get("source_key") or "")
        if source_key in source_id_remaps:
            row = {**row, "policy_source_id": source_id_remaps[source_key]}
        previous = evidence.get(key)
        if previous and previous.get("artifact_sha256") != row.get("artifact_sha256"):
            row = {**row, "review_status": "changed_pending_review", "previous_artifact_sha256": previous.get("artifact_sha256")}
        evidence[key] = row
    current["evidence"] = list(evidence.values())
    for records_key in ("policy_records",):
        for record in current.get(records_key, []):
            referenced = set(record.get("source_keys", [])) | set(record.get("formal_policy_source_keys", [])) | set(record.get("policy_source_keys", []))
            if referenced & changed_source_keys:
                record["review_status"] = "changed_source_pending_review"
    current["discovery_last_researched_at"] = fragment.get("researched_at")

    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover current official policy material from routed departments")
    parser.add_argument("research_ledger")
    parser.add_argument("--report-data", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args()
    result = discover_current_policies(
        load_data(args.research_ledger),
        load_data(args.report_data),
        Path(args.out_dir),
        max_concurrency=args.max_concurrency,
        max_retries=args.max_retries,
    )
    print(json.dumps(result["metrics"], ensure_ascii=False))
    return 0 if not result["metrics"]["failed_requests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
