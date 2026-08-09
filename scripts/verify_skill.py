#!/usr/bin/env python3
"""Run fast checks normally and the full suite only for release/bootstrap."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def commands(release: bool, smoke: bool, out_dir: str | None) -> list[tuple[str, list[str]]]:
    if not release and not smoke:
        return [("doctor", [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "doctor.py")])]
    preflight = [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "preflight.py")]
    if smoke:
        preflight.append("--smoke")
    if out_dir:
        preflight.extend(["--out-dir", out_dir])
    tests = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"]
    return [("preflight", preflight), ("tests", tests)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fast checks or the maintainer release gate with Python only.")
    parser.add_argument("--release", action="store_true", help="run packaging preflight and the complete offline test suite")
    parser.add_argument("--smoke", action="store_true", help="release gate plus the Flyco HTML sample")
    parser.add_argument("--out-dir", help="optional preflight smoke output directory")
    args = parser.parse_args()
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    for label, command in commands(args.release or args.smoke, args.smoke, args.out_dir):
        print(f"[verify] running {label}: {command}")
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        if result.returncode:
            print(f"[verify] failed: {label} (exit {result.returncode})", file=sys.stderr)
            return result.returncode
        print(f"[verify] passed: {label}")
    print("[verify] passed: " + ("portable release gate" if args.release or args.smoke else "fast runtime gate"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
