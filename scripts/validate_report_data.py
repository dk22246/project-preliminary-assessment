from __future__ import annotations
import argparse
from report_core import load_data, validate_report_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    args = parser.parse_args()
    errors = validate_report_data(load_data(args.report_data))
    if errors:
        print("\n".join(errors))
        return 1
    print("通过：报告结构化数据完整")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
