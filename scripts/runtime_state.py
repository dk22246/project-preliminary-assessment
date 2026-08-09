#!/usr/bin/env python3
"""Portable runtime discovery and versioned verification state."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".runtime"
STATE_FILE = STATE_DIR / "verification.json"
REQUIREMENTS_FILE = ROOT / "runtime-requirements.json"


def _load_requirements() -> dict:
    return json.loads(REQUIREMENTS_FILE.read_text(encoding="utf-8-sig"))


def package_fingerprint() -> str:
    digest = hashlib.sha256()
    requirements = _load_requirements()
    relatives = set(requirements.get("fingerprint_files", []))
    ignored_parts = {"__pycache__", ".pytest_cache", "outputs", ".runtime"}
    for root_name in requirements.get("fingerprint_roots", []):
        root = ROOT / root_name
        if root.is_dir():
            relatives.update(
                path.relative_to(ROOT).as_posix()
                for path in root.rglob("*")
                if path.is_file() and not ignored_parts.intersection(path.parts) and path.suffix.lower() not in {".pyc", ".pyo"}
            )
    for relative in sorted(relatives):
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if not path.is_file():
            digest.update(b"MISSING")
        else:
            digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def resolve_node(explicit: str | None = None) -> Path | None:
    candidates = [explicit, os.environ.get("REPORT_NODE_EXECUTABLE"), shutil.which("node")]
    for candidate in candidates:
        if candidate and Path(candidate).expanduser().is_file():
            return Path(candidate).expanduser().resolve()
    return None


def resolve_node_modules(node: Path | None) -> Path | None:
    candidates = [
        os.environ.get("REPORT_NODE_MODULES"),
        str(ROOT / "node_modules"),
        str(node.parent.parent / "node_modules") if node else None,
    ]
    for candidate in candidates:
        if candidate and (Path(candidate).expanduser() / "playwright" / "package.json").is_file():
            return Path(candidate).expanduser().resolve()
    return None


def resolve_chrome(explicit: str | None = None) -> Path | None:
    candidates = [explicit, os.environ.get("REPORT_CHROME_EXECUTABLE")]
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
            if base:
                candidates.append(str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"))
    elif sys.platform == "darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    else:
        candidates.extend((shutil.which("google-chrome"), shutil.which("google-chrome-stable"), shutil.which("chromium"), shutil.which("chromium-browser")))
    for candidate in candidates:
        if candidate and Path(candidate).expanduser().is_file():
            return Path(candidate).expanduser().resolve()
    return None


def _version(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    return (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else "unknown"


def discover(node: str | None = None, chrome: str | None = None) -> dict:
    node_path = resolve_node(node)
    modules = resolve_node_modules(node_path)
    chrome_path = resolve_chrome(chrome)
    return {
        "fingerprint": package_fingerprint(),
        "python": {"path": str(Path(sys.executable).resolve()), "version": sys.version.split()[0]},
        "node": {"path": str(node_path) if node_path else "", "version": _version([str(node_path), "--version"]) if node_path else "unavailable"},
        "node_modules": str(modules) if modules else "",
        "playwright": bool(modules),
        # On Windows, invoking chrome.exe --version can launch a GUI process and
        # stall the fast doctor. The browser layout gate proves executability.
        "chrome": {"path": str(chrome_path) if chrome_path else "", "version": "detected" if chrome_path else "unavailable"},
        "python_docx": importlib.util.find_spec("docx") is not None,
    }


def capability_errors(state: dict, *, need_node: bool = True, need_word: bool = False) -> list[str]:
    errors: list[str] = []
    if sys.version_info < (3, 10):
        errors.append("Python版本低于3.10")
    if need_node and not state.get("node", {}).get("path"):
        errors.append("未找到真实Node.js可执行文件；请安装Node.js或向 --node 传入完整路径")
    node_version = str(state.get("node", {}).get("version", ""))
    node_match = re.search(r"v?(\d+)(?:\.\d+){0,2}", node_version)
    if need_node and state.get("node", {}).get("path") and (not node_match or int(node_match.group(1)) < 18):
        errors.append(f"Node.js版本不满足>=18：{node_version or '无法识别'}")
    if need_node and not state.get("playwright"):
        errors.append("未找到Playwright；请在Skill根目录运行 npm install，或设置 REPORT_NODE_MODULES")
    if need_node and not state.get("chrome", {}).get("path"):
        errors.append("未找到Google Chrome/Chromium；请安装浏览器或设置 REPORT_CHROME_EXECUTABLE")
    if need_word and not state.get("python_docx"):
        errors.append("生成Word需要python-docx；请安装 requirements-word.txt")
    return errors


def load_verified_state() -> dict | None:
    if not STATE_FILE.is_file():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def state_is_current(state: dict | None) -> bool:
    return bool(state and state.get("verified") is True and state.get("fingerprint") == package_fingerprint())


def write_verified_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(state)
    payload["verified"] = True
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
