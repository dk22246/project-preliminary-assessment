#!/usr/bin/env python3
"""Policy cache that always revalidates an official source before reuse."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class PolicyCache:
    """Persist policy artifacts beneath one workspaces's .cache/policies directory."""

    def __init__(self, cache_dir: Path, round_id: str | None = None):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.round_id = round_id

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
        if cached and self.round_id and cached.get("round_id") == self.round_id:
            try:
                age = (datetime.fromisoformat(revalidated_at) - datetime.fromisoformat(cached["revalidated_at"])).total_seconds()
            except (ValueError, KeyError, TypeError):
                age = 86401
            if 0 <= age < 86400 and hashlib.sha256(cached["_artifact_path"].read_bytes()).hexdigest() == cached.get("artifact_sha256"):
                return {key: value for key, value in cached.items() if key != "_artifact_path"} | {"reused_in_round": True}
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
            if hashlib.sha256(cached["_artifact_path"].read_bytes()).hexdigest() != cached.get("artifact_sha256"):
                raise RuntimeError("缓存正文校验失败，不能采用304复验")
            receipt = {key: value for key, value in cached.items() if key != "_artifact_path"}
            receipt.update({"revalidated_at": revalidated_at, "retrieved_at": revalidated_at, "fresh_retrieval": False, "http_status": 304, "round_id": self.round_id})
            self._paths(url)[0].write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            return receipt
        if status != 200 or not isinstance(response.get("body"), (bytes, bytearray)):
            raise RuntimeError(f"官方来源复验失败：HTTP {status}")
        record = self.store(url, bytes(response["body"]), headers, retrieved_at=revalidated_at)
        record.update({"revalidated_at": revalidated_at, "fresh_retrieval": True, "http_status": 200, "round_id": self.round_id, "final_url": response.get("final_url", url)})
        self._paths(url)[0].write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return record


def workspace_cache(out_dir: Path) -> PolicyCache:
    """Share evidence only inside the actual run; preserve the original receipt time."""
    for parent in (Path(out_dir).resolve(), *Path(out_dir).resolve().parents):
        state_path = parent / "workflow-state.json"
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8-sig"))
            return PolicyCache(parent / "evidence" / ".cache" / "policies", str(state["run_id"]))
    return PolicyCache(Path(out_dir).parent / ".cache" / "policies")
