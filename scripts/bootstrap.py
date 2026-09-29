#!/usr/bin/env python3
"""One-time or version-change deployment verification for any agent platform."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys

from runtime_state import capability_errors, discover, load_verified_state, state_is_current, write_verified_state


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify dependencies and browser on first deployment or dependency changes")
    parser.add_argument("--node", help="Node.js executable path")
    parser.add_argument("--chrome", help="Chrome/Chromium executable path")
    parser.add_argument("--force", action="store_true", help="rerun dependency and browser verification")
    args = parser.parse_args()

    discovered = discover(args.node, args.chrome)
    errors = capability_errors(discovered, need_node=True, need_pdf=True)
    if errors:
        print("部署能力检查失败：", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    previous = load_verified_state()
    if not args.force and state_is_current(previous):
        print("通过：运行依赖未变化，复用既有部署验证")
        return 0

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["REPORT_NODE_EXECUTABLE"] = discovered["node"]["path"]
    env["REPORT_NODE_MODULES"] = discovered["node_modules"]
    env["REPORT_CHROME_EXECUTABLE"] = discovered["chrome"]["path"]
    # Software/release tests belong to maintenance, not every user's installation.
    command = [discovered["node"]["path"], "-e", "const {chromium}=require(require('path').join(process.env.REPORT_NODE_MODULES,'playwright')); (async()=>{const b=await chromium.launch({headless:true,executablePath:process.env.REPORT_CHROME_EXECUTABLE});const p=await b.newPage();await p.setContent('<p>runtime ready</p>');if(await p.textContent('p')!=='runtime ready')throw Error('render failed');await b.close()})().catch(e=>{console.error(e);process.exit(1)})"]
    result = subprocess.run(command, cwd=ROOT, env=env, check=False, timeout=45)
    if result.returncode:
        print("浏览器运行验证失败，未写入可用状态", file=sys.stderr)
        return result.returncode
    discovered["verified_at"] = datetime.now(timezone.utc).isoformat()
    write_verified_state(discovered)
    print("通过：首次部署或版本变化验证完成；后续正常报告只运行快速doctor")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
