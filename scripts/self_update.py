#!/usr/bin/env python3
"""Self-update guard: safely fast-forward the installed skill before running.

Design goals (简单清晰):
- Triggered once at the ppa.py entry, before the real command runs.
- A 24h TTL avoids hitting the network on every invocation.
- Only standard Git fast-forward operations are allowed. Never write `.git`
  internals directly and never overwrite a dirty worktree.
- If an update is installed, the caller stops the current command so one
  report run never mixes old imports with newly checked-out code.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TTL_SECONDS = 24 * 60 * 60
REMOTE = "origin"
BRANCH = "main"


def _run(*args: str, cwd: Path | None = None) -> str:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git 不可用")
    result = subprocess.run(
        [git, *args], cwd=cwd or ROOT, text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=False,
    )
    if result.returncode:
        detail = ((result.stdout or "") + (result.stderr or "")).strip()
        raise RuntimeError(detail or f"git {' '.join(args)} 失败")
    return (result.stdout or "").strip()


def _mark_checked(marker: Path) -> None:
    try:
        marker.write_text(str(int(time.time())), encoding="utf-8")
    except OSError:
        pass


def ensure_fresh(quiet: bool = False, root: str | Path | None = None) -> str | None:
    """Check origin/main and fast-forward if a newer version exists.

    Return ``updated`` after a successful fast-forward or ``blocked`` when a
    newer remote version exists but cannot be installed safely. Offline and
    non-git deployments keep using the local version and return ``None``.
    """
    base = Path(root).resolve() if root else ROOT
    marker = base / ".self-update-marker"
    if not (base / ".git").exists():
        return  # 非 git 部署（如解压 zip），跳过自更新
    try:
        if marker.exists() and time.time() - marker.stat().st_mtime < TTL_SECONDS:
            return  # 24h 内已查过
        local = _run("rev-parse", "HEAD", cwd=base)
        current_branch = _run("rev-parse", "--abbrev-ref", "HEAD", cwd=base)
        remote_line = _run("ls-remote", REMOTE, f"refs/heads/{BRANCH}", cwd=base)
        remote = remote_line.split()[0]
        if remote == local:
            _mark_checked(marker)
            return  # 已是最新
        if current_branch != BRANCH:
            if not quiet:
                print(f"[自更新] 远程有新版 {remote[:7]}，但当前在 {current_branch} 分支，无法安全更新")
            return "blocked"
        if _run("status", "--porcelain", cwd=base):
            if not quiet:
                print("[自更新] 检测到未提交改动，已暂停运行；请先处理本地改动")
            return "blocked"
        _run("fetch", REMOTE, BRANCH, cwd=base)
        fetched = _run("rev-parse", "FETCH_HEAD", cwd=base)
        if fetched == local:
            _mark_checked(marker)
            return
        try:
            _run("merge-base", "--is-ancestor", local, fetched, cwd=base)
        except RuntimeError:
            try:
                _run("merge-base", "--is-ancestor", fetched, local, cwd=base)
            except RuntimeError:
                if not quiet:
                    print("[自更新] 本地版本与GitHub已分叉，已暂停运行；禁止自动覆盖")
                return "blocked"
            _mark_checked(marker)
            return  # 本地提交领先远端；不得自动降级
        try:
            _run("merge", "--ff-only", "FETCH_HEAD", cwd=base)
        except RuntimeError as error:
            if not quiet:
                print(f"[自更新] 快进失败，已暂停运行且未覆盖本地内容（{error}）")
            return "blocked"
        _mark_checked(marker)
        if not quiet:
            print(f"[自更新] 已更新 {local[:7]} -> {fetched[:7]}；当前命令已暂停，重新执行后使用最新版")
        return "updated"
    except Exception as error:
        _mark_checked(marker)
        if not quiet:
            print(f"[自更新] 跳过（{error}）")
        return None


if __name__ == "__main__":
    ensure_fresh()
