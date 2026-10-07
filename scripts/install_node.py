#!/usr/bin/env python3
"""Portable Node.js installer for the one-time `ppa.py setup` deployment.

Design goal: `setup` must install EVERYTHING a fresh machine needs, including
Node.js itself, so deployment is a single run and later report runs never trip
over a missing runtime.

Node is fetched from the official nodejs.org dist, verified against the
official SHASUMS256 file, and unpacked under an agent-neutral user runtime
directory. Its path is written to the verified state by the normal setup flow
so subsequent runs resolve it without re-downloading.
The whole installer is idempotent and offline-tolerant (any failure returns
None and the caller reports a clear manual-install hint).
"""
from __future__ import annotations

import json
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = ROOT / "runtime-requirements.json"

DEFAULT_VERSION = "22.14.0"
DIST_BASE = "https://nodejs.org/dist"


def runtime_home() -> Path:
    configured = os.environ.get("PPA_RUNTIME_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".project-preliminary-assessment" / "runtime").resolve()


def node_home() -> Path:
    return runtime_home() / "node"


# Existing installations remain discoverable after migration to the neutral path.
LEGACY_NODE_HOME = Path.home() / ".workbuddy" / "binaries" / "node"


def dist_version() -> str:
    try:
        data = json.loads(REQUIREMENTS_FILE.read_text(encoding="utf-8-sig"))
        version = str(data.get("node_dist_version", "")).strip()
        if version:
            return version
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return os.environ.get("REPORT_NODE_VERSION", DEFAULT_VERSION)


def platform_key() -> str:
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64", "x64"):
        arch = "x64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = "x64"
    if sys.platform == "win32":
        return f"win-{arch}"
    if sys.platform == "darwin":
        return f"darwin-{arch}"
    return f"linux-{arch}"


def archive_suffix(plat_key: str | None = None) -> str:
    key = plat_key or platform_key()
    if key.startswith("win"):
        return "zip"
    if key.startswith("darwin"):
        return "tar.gz"
    return "tar.xz"


def dist_url(version: str | None = None) -> str:
    ver = version or dist_version()
    key = platform_key()
    return f"{DIST_BASE}/v{ver}/node-v{ver}-{key}.{archive_suffix(key)}"


def _node_executable(install_dir: Path) -> Path:
    if sys.platform == "win32":
        return install_dir / "node.exe"
    return install_dir / "bin" / "node"


def portable_node_candidates(home: Path | None = None) -> list[Path]:
    """Node executables already unpacked under the portable Node home."""
    results: list[Path] = []
    bases = [home] if home is not None else [node_home(), LEGACY_NODE_HOME]
    for base in bases:
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir(), reverse=True):
            exe = _node_executable(entry)
            if exe.is_file() and exe not in results:
                results.append(exe)
    return results


def _valid_version(exe: Path, minimum: int = 18) -> bool:
    try:
        result = subprocess.run(
            [str(exe), "--version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    text = (result.stdout or "").strip().lstrip("v")
    major = text.split(".")[0]
    return major.isdigit() and int(major) >= minimum


def _download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ppa-setup/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, dest.open("wb") as out:
        shutil.copyfileobj(response, out, length=1024 * 256)


def _verify_checksum(archive: Path, checksums: Path) -> bool:
    expected = None
    for line in checksums.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == archive.name:
            expected = parts[0].lower()
            break
    if not expected or len(expected) != 64:
        return False
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    return actual == expected


def _safe_member_path(base: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    if not normalized or normalized.startswith("/") or Path(normalized).is_absolute():
        raise ValueError(f"压缩包包含不安全路径：{member_name}")
    target = (base / normalized).resolve()
    resolved_base = base.resolve()
    if target != resolved_base and resolved_base not in target.parents:
        raise ValueError(f"压缩包路径越界：{member_name}")
    return target


def _extract(archive: Path, into: Path) -> None:
    into.mkdir(parents=True, exist_ok=True)
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                _safe_member_path(into, info.filename)
                mode = (info.external_attr >> 16) & 0o170000
                if stat.S_ISLNK(mode):
                    raise ValueError(f"压缩包包含符号链接：{info.filename}")
            zf.extractall(into)
        return
    mode = "r:xz" if archive.name.endswith(".tar.xz") else "r:gz"
    with tarfile.open(archive, mode=mode) as tf:
        members = tf.getmembers()
        for member in members:
            _safe_member_path(into, member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"压缩包包含不安全链接或设备：{member.name}")
        if sys.version_info >= (3, 12):
            tf.extractall(into, members=members, filter="data")
        else:
            tf.extractall(into, members=members)


def ensure_node(home: Path | None = None, version: str | None = None) -> Path | None:
    """Return a usable Node >=18, downloading a portable dist if necessary."""
    base = home or node_home()
    ver = version or dist_version()
    for exe in portable_node_candidates(base):
        if _valid_version(exe):
            return exe

    url = dist_url(ver)
    key = platform_key()
    archive_name = f"node-v{ver}-{key}.{archive_suffix(key)}"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary)
        archive = tmp / archive_name
        checksums = tmp / "SHASUMS256.txt"
        try:
            _download(url, archive)
            _download(f"{DIST_BASE}/v{ver}/SHASUMS256.txt", checksums)
        except Exception as error:
            print(f"[install-node] 下载失败（{url}）：{error}", file=sys.stderr)
            return None
        if not _verify_checksum(archive, checksums):
            print("[install-node] Node安装包SHA-256校验失败，已拒绝安装", file=sys.stderr)
            return None
        try:
            _extract(archive, tmp)
        except (OSError, ValueError, tarfile.TarError, zipfile.BadZipFile) as error:
            print(f"[install-node] 解压失败：{error}", file=sys.stderr)
            return None
        src = tmp / f"node-v{ver}-{key}"
        if not src.is_dir():
            # Some archives may lack the top folder; fall back to first dir.
            dirs = [p for p in tmp.iterdir() if p.is_dir() and p != base]
            src = dirs[0] if dirs else tmp
        exe = _node_executable(src)
        if not exe.is_file() or not _valid_version(exe):
            print("[install-node] 解压后未找到可用的 Node 可执行文件", file=sys.stderr)
            return None
        dest = base / f"node-v{ver}-{key}"
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(src), str(dest))
    exe = _node_executable(base / f"node-v{ver}-{key}")
    return exe if exe.is_file() and _valid_version(exe) else None


if __name__ == "__main__":
    node = ensure_node()
    if not node:
        raise SystemExit(1)
    print(node)
