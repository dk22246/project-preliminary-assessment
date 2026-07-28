from __future__ import annotations
import argparse
from report_core import load_data, validate_text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    args = parser.parse_args()
    errors = validate_text(load_data(args.report_data))
    if errors:
        print("\n".join(errors))
        return 1
    print("通过：未发现乱码替代字符、连续问号或空股权节点")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
