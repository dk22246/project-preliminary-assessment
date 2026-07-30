"""Allow only public official, disclosure, or explicitly reviewed enterprise hosts."""
from __future__ import annotations

from urllib.parse import urlparse


DISCLOSURE_HOSTS = {
    "www.cninfo.com.cn",
    "www.sse.com.cn",
    "www.szse.cn",
    "www.hkexnews.hk",
    "www.sec.gov",
    "www.nasdaq.com",
    "www.nyse.com",
}


def normalise_host(value: str) -> str:
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return parsed.hostname.lower() if parsed.hostname else ""


def is_allowed_url(url: str, explicit_hosts: set[str]) -> bool:
    """Permit HTTPS government/disclosure hosts or an explicitly reviewed host."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = {normalise_host(item) for item in explicit_hosts}
    return parsed.scheme == "https" and bool(host) and (
        host == "gov.cn"
        or host.endswith(".gov.cn")
        or host in DISCLOSURE_HOSTS
        or host in allowed
    )


def source_category(url: str, explicit_hosts: set[str]) -> str:
    host = normalise_host(url)
    if host == "gov.cn" or host.endswith(".gov.cn"):
        return "government"
    if host in DISCLOSURE_HOSTS:
        return "disclosure"
    if host in {normalise_host(item) for item in explicit_hosts}:
        return "enterprise"
    return "unknown"
