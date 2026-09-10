from __future__ import annotations
import argparse
from report_core import load_data, validate_report_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--fixture-mode", action="store_true")
    args = parser.parse_args()
    data = load_data(args.report_data)
    errors = validate_report_data(data)
    fixture = data.get("fixture_metadata") or {}
    if fixture.get("fixture_only") and not args.fixture_mode:
        errors.append("正式报告不得使用fixture底稿；发布测试必须显式传入--fixture-mode")
    if errors:
        print("\n".join(errors))
        return 1
    print("通过：报告结构化数据完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
