#!/usr/bin/env python3
"""Validate that every landing business has a complete policy-research conclusion."""
from __future__ import annotations

import argparse

from report_core import load_data, validate_business_policy_ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    args = parser.parse_args()
    errors = validate_business_policy_ledger(load_data(args.report_data))
    if errors:
        print("\n".join(errors))
        return 1
    print("通过：每项落地业务均有完整政策检索结论")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
