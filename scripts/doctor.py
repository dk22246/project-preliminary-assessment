#!/usr/bin/env python3
"""Fast pre-run capability check; never runs the full test suite."""
from __future__ import annotations

import argparse
import sys

from runtime_state import capability_errors, discover, load_verified_state, state_is_current


def check(*, node: str | None = None, chrome: str | None = None, need_word: bool = False, require_verified: bool = True) -> tuple[dict, list[str]]:
    state = discover(node, chrome)
    errors = capability_errors(state, need_node=True, need_word=need_word)
    verified = load_verified_state()
    if require_verified and not state_is_current(verified):
        errors.append("Skill尚未通过当前版本部署验证；请先运行 scripts/bootstrap.py")
    return state, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast runtime doctor for project-preliminary-assessment")
    parser.add_argument("--node")
    parser.add_argument("--chrome")
    parser.add_argument("--word", action="store_true")
    parser.add_argument("--allow-unverified", action="store_true")
    args = parser.parse_args()
    state, errors = check(node=args.node, chrome=args.chrome, need_word=args.word, require_verified=not args.allow_unverified)
    if errors:
        print("运行环境自检失败：", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"通过：运行环境可用；Node={state['node']['path']}；Chrome={state['chrome']['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
