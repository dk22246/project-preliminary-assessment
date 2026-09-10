#!/usr/bin/env python3
"""Policy cache that always revalidates an official source before reuse."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable


class PolicyCache:
    """Persist policy artifacts beneath one workspaces's .cache/policies directory."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = self._key(url)
        return self.cache_dir / f"{key}.json", self.cache_dir / f"{key}.bin"

    def _read(self, url: str) -> dict | None:
        metadata_path, artifact_path = self._paths(url)
        if not metadata_path.exists() or not artifact_path.exists():
            return None
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["_artifact_path"] = artifact_path
        return metadata

    def store(self, url: str, body: bytes, headers: dict[str, str] | None = None, *, retrieved_at: str) -> dict:
        headers = headers or {}
        metadata_path, artifact_path = self._paths(url)
        artifact_path.write_bytes(body)
        record = {
            "url": url,
            "final_url": url,
            "artifact_sha256": hashlib.sha256(body).hexdigest(),
            "cached_artifact_created_at": retrieved_at,
            "retrieved_at": retrieved_at,
            "etag": headers.get("ETag") or headers.get("etag"),
            "last_modified": headers.get("Last-Modified") or headers.get("last-modified"),
            "content_type": headers.get("Content-Type") or headers.get("content-type") or "application/octet-stream",
        }
        metadata_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record

    def revalidate(
        self,
        url: str,
        fetch: Callable[[str, dict[str, str]], dict],
        *,
        dynamic: bool = False,
        revalidated_at: str,
    ) -> dict:
        """Fetch once per run and return a receipt; cached content never fakes a new fetch."""
        cached = self._read(url)
        request_headers: dict[str, str] = {}
        if cached and not dynamic:
            if cached.get("etag"):
                request_headers["If-None-Match"] = cached["etag"]
            elif cached.get("last_modified"):
                request_headers["If-Modified-Since"] = cached["last_modified"]
        response = fetch(url, request_headers)
        status = int(response.get("status", 0))
        headers = response.get("headers") or {}
        if status == 304 and cached and not dynamic:
            receipt = {key: value for key, value in cached.items() if key != "_artifact_path"}
            receipt.update({"revalidated_at": revalidated_at, "retrieved_at": revalidated_at, "fresh_retrieval": False, "http_status": 304})
            return receipt
        if status != 200 or not isinstance(response.get("body"), (bytes, bytearray)):
            raise RuntimeError(f"官方来源复验失败：HTTP {status}")
        record = self.store(url, bytes(response["body"]), headers, retrieved_at=revalidated_at)
        record.update({"revalidated_at": revalidated_at, "fresh_retrieval": True, "http_status": 200})
        return record
