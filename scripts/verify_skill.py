#!/usr/bin/env python3
"""Run the portable deployment gate without relying on a shell wrapper."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def commands(smoke: bool, out_dir: str | None) -> list[tuple[str, list[str]]]:
    preflight = [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "preflight.py")]
    if smoke:
        preflight.append("--smoke")
    if out_dir:
        preflight.extend(["--out-dir", out_dir])
    tests = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"]
    return [("preflight", preflight), ("tests", tests)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run project-preliminary-assessment deployment checks with Python only.")
    parser.add_argument("--smoke", action="store_true", help="also render the Flyco HTML sample")
    parser.add_argument("--out-dir", help="optional preflight smoke output directory")
    args = parser.parse_args()
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    for label, command in commands(args.smoke, args.out_dir):
        print(f"[verify] running {label}: {command}")
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode:
            print(f"[verify] failed: {label} (exit {result.returncode})", file=sys.stderr)
            return result.returncode
        print(f"[verify] passed: {label}")
    print("[verify] passed: portable deployment gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
