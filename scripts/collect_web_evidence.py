#!/usr/bin/env python3
"""Collect approved public HTML and cached-PDF evidence into a UTF-8 ledger."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time
from urllib.parse import unquote, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evidence_collectors.html_extract import extract_html
from evidence_collectors.pdf_extract import EXTRACTOR_VERSION, extract_pdf
from evidence_collectors.registry import is_allowed_url, normalise_host, source_category
from policy_cache import workspace_cache
from discover_current_policies import _default_fetch, _request_with_retry, _decode_html


USER_AGENT = "project-preliminary-assessment-evidence/1.0 (+public-evidence-only)"


def normalise_url(url: str) -> str:
    return url.strip().split("#", 1)[0]


def _pdf_title(url: str) -> str:
    return Path(unquote(urlsplit(url).path)).stem


def _cached_pdf_content(raw_path: Path, raw_sha256: str, out_dir: Path) -> tuple[Path | None, str]:
    """Extract a cached PDF once for each original artifact and extractor version."""
    relative = Path("content") / "pdf" / f"{raw_sha256}-{EXTRACTOR_VERSION}.txt"
    target = out_dir / relative
    shared = raw_path.parent / "pdf-text" / relative.name
    if not shared.is_file():
        extracted = extract_pdf(raw_path)
        if extracted.error:
            return None, extracted.error
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text(extracted.text, encoding="utf-8", newline="\n")
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(shared, target)
    return relative, ""


def fetch_html(url: str, timeout: int, retries: int) -> tuple[int, str, str, str]:
    """Return HTTP status, final URL, decoded body and error text without retaining cookies."""
    last_error = ""
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
            with urlopen(request, timeout=timeout) as response:  # nosec B310: URL allowlist is checked by caller
                status = response.getcode()
                content_type = response.headers.get_content_type()
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset, errors="replace")
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    return status, response.geturl(), "", f"仅采集HTML页面，实际内容类型为 {content_type}"
                return status, response.geturl(), body, ""
        except HTTPError as error:
            last_error = f"HTTP {error.code}: {error.reason}"
            if error.code not in {429, 502, 503, 504}:
                return error.code, url, "", last_error
        except (URLError, OSError, TimeoutError) as error:
            last_error = str(error)
        if attempt < retries:
            time.sleep(0.4 * (attempt + 1))
    return 0, url, "", last_error or "抓取失败"


def collect(url: str, *, purpose: str, out_dir: Path, explicit_hosts: set[str], timeout: int, retries: int, index: int) -> dict:
    source_url = normalise_url(url)
    fetched_at = datetime.now(timezone.utc).isoformat()
    base = {
        "source_url": source_url,
        "canonical_url": source_url,
        "title": "",
        "publisher": normalise_host(source_url),
        "source_category": source_category(source_url, explicit_hosts),
        "purpose": purpose,
        "fetched_at": fetched_at,
        "http_status": 0,
        "extraction_status": "failed",
        "content_path": "",
        "content_sha256": "",
        "attachments": [],
        "error": "",
    }
    if not is_allowed_url(source_url, explicit_hosts):
        base["error"] = "来源不在允许来源白名单"
        return base
    cache = workspace_cache(out_dir)
    raw_path: Path | None = None
    cached_content_type = ""
    if cache.round_id:
        receipt, _, error = _request_with_retry(source_url, cache, lambda url, headers: _default_fetch(url, headers, timeout), dynamic=True, max_retries=retries, sleep=time.sleep)
        if receipt:
            status = receipt["http_status"]
            final_url = receipt.get("final_url", source_url)
            raw_path = cache._paths(source_url)[1]
            cached_content_type = receipt.get("content_type", "").split(";", 1)[0].lower()
            base["fetched_at"] = receipt["retrieved_at"]
            base["raw_artifact_path"] = str(raw_path)
            base["raw_artifact_sha256"] = receipt["artifact_sha256"]
            base["reused_in_round"] = receipt.get("reused_in_round", False)
        else:
            status, final_url, html = 0, source_url, ""
    else:
        status, final_url, html, error = fetch_html(source_url, timeout, retries)
    base["http_status"] = status
    base["canonical_url"] = normalise_url(final_url)
    if not is_allowed_url(base["canonical_url"], explicit_hosts):
        base["error"] = "重定向后的来源不在允许来源白名单"
        return base
    base["publisher"] = normalise_host(base["canonical_url"])
    base["source_category"] = source_category(base["canonical_url"], explicit_hosts)
    if raw_path:
        if cached_content_type in {"text/html", "application/xhtml+xml"}:
            html, decode_error = _decode_html(raw_path.read_bytes(), receipt.get("content_type", ""))
            error = decode_error or ""
        elif cached_content_type == "application/pdf":
            relative, pdf_error = _cached_pdf_content(raw_path, receipt["artifact_sha256"], out_dir)
            if relative:
                base.update({
                    "title": _pdf_title(final_url),
                    "extraction_status": "success",
                    "content_path": relative.as_posix(),
                    "content_sha256": hashlib.sha256((out_dir / relative).read_bytes()).hexdigest(),
                })
            else:
                error = pdf_error
        else:
            error = f"此入口仅提取HTML或PDF；原始文件已保存，实际内容类型为 {cached_content_type or 'unknown'}"
    if base["extraction_status"] == "success":
        return base
    if error or not html:
        base["error"] = error or "未提取到正文"
        return base
    extracted = extract_html(html, base["canonical_url"])
    if not extracted.text:
        base["error"] = "未提取到可用正文"
        return base
    relative = Path("content") / f"{index:03d}.md"
    target = out_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"# {extracted.title}\n\n{extracted.text}\n", encoding="utf-8", newline="\n")
    base.update({
        "title": extracted.title,
        "extraction_status": "success",
        "content_path": relative.as_posix(),
        "content_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "attachments": extracted.attachments,
    })
    return base


def collect_many(urls: list[str], **options) -> list[dict]:
    """Bounded cross-host collection; stable order and no same-host fan-out."""
    unique = list(dict.fromkeys(normalise_url(url) for url in urls if normalise_url(url)))
    groups: dict[str, list[tuple[int, str]]] = {}
    for index, url in enumerate(unique, 1):
        groups.setdefault(normalise_host(url), []).append((index, url))
    def run(group):
        return [(index, collect(url, index=index, **options)) for index, url in group]
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(groups)))) as executor:
        results = [item for group in executor.map(run, groups.values()) for item in group]
    return [record for _, record in sorted(results, key=lambda item: item[0])]


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect approved public-web evidence into evidence.json")
    parser.add_argument("enterprise")
    parser.add_argument("topic")
    parser.add_argument("--url", action="append", required=True, help="candidate public HTML or PDF URL; repeat as needed")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--allow-domain", action="append", default=[], help="enterprise host reviewed as official; repeat as needed")
    parser.add_argument("--purpose", default="企业或政策公开事实核验")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    explicit_hosts = {normalise_host(item) for item in args.allow_domain if normalise_host(item)}
    records: list[dict] = []
    canonical_seen: set[str] = set()
    for record in collect_many(args.url, purpose=args.purpose, out_dir=out_dir, explicit_hosts=explicit_hosts, timeout=max(1, args.timeout), retries=max(0, args.retries)):
        if record["extraction_status"] == "success" and record["canonical_url"] in canonical_seen:
            Path(out_dir / record["content_path"]).unlink(missing_ok=True)
            continue
        canonical_seen.add(record["canonical_url"])
        records.append(record)
    ledger = {"enterprise": args.enterprise, "topic": args.topic, "allowed_domains": sorted(explicit_hosts), "evidence": records}
    target = out_dir / "evidence.json"
    target.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
