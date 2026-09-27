"""Resolve role paths from explicit entries or actual official navigation links."""
from __future__ import annotations

from urllib.parse import urlsplit

PATH_LABELS = {
    "department_documents": ("部门文件", "政策文件", "政策法规"),
    "normative_documents": ("规范性文件", "行政规范性文件"),
    "application_notices": ("办事指南", "办理指南", "申报通知", "业务指南", "政务服务"),
    "award_publicity": ("奖补公示", "资金公示", "奖励公示"),
    "invalidity_catalog": ("失效", "废止", "清理结果", "有效文件目录", "现行有效法规目录"),
}


def official_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host.endswith(".gov.cn")


def resolve_paths(required, links, *, entry_url, entry_kind, explicit=None):
    """Never invent URLs or claim a homepage is a scanned document directory."""
    result = {}
    explicit = explicit or {}
    for path in required:
        value = explicit.get(path)
        if isinstance(value, str) and official_url(value):
            result[path] = value
            continue
        if path in {"theme_search", "department_documents"} and entry_kind == "policy_directory":
            result[path] = entry_url
            continue
        for url, title in links:
            if official_url(url) and any(label in title for label in PATH_LABELS.get(path, ())):
                result[path] = url
                break
    return result
