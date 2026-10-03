#!/usr/bin/env python3
"""Self-update guard: pull the latest skill version from GitHub before running.

Design goals (简单清晰):
- Triggered once at the ppa.py entry, before the real command runs.
- A 24h TTL avoids hitting the network on every invocation.
- Only fast-forward updates (never lose local work); any failure degrades
  silently to the local version, so an offline machine still works.

The environment's git has a known quirk where `git reset` / `git update-ref`
corrupts branch refs, and `git fetch` does not persist remote-tracking refs.
So this script intentionally avoids both: it compares via `git ls-remote`,
downloads via `git fetch` (to FETCH_HEAD), then moves the branch pointer by
writing the ref file directly and syncing the worktree with `git checkout -f`.
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


def ensure_fresh(quiet: bool = False, root: str | Path | None = None) -> None:
    """Check origin/main and fast-forward if a newer version exists.

    Never raises: every branch of failure returns and keeps the local version,
    so the skill remains usable offline or on non-git deployments.
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
        try:
            marker.write_text(str(int(time.time())), encoding="utf-8")
        except OSError:
            pass
        if remote == local:
            return  # 已是最新
        if current_branch != BRANCH:
            if not quiet:
                print(f"[自更新] 远程有新版 {remote[:7]}，但当前在 {current_branch} 分支，切到 {BRANCH} 后自动更新")
            return
        if _run("status", "--porcelain", cwd=base):
            if not quiet:
                print("[自更新] 检测到未提交改动，跳过自动更新以免覆盖")
            return
        _run("fetch", REMOTE, BRANCH, cwd=base)
        fetched = _run("rev-parse", "FETCH_HEAD", cwd=base)
        if fetched == local:
            return
        # Fast-forward only: raise (and degrade) if local is not an ancestor.
        _run("merge-base", "--is-ancestor", local, fetched, cwd=base)
        ref_path = base / ".git" / "refs" / "heads" / BRANCH
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        ref_path.write_text(fetched + "\n", encoding="utf-8")
        _run("checkout", "-f", BRANCH, cwd=base)
        if not quiet:
            print(f"[自更新] 已更新 {local[:7]} -> {fetched[:7]}；本次命令继续，下次起为最新版")
    except Exception as error:
        if not quiet:
            print(f"[自更新] 跳过（{error}）")


if __name__ == "__main__":
    ensure_fresh()
