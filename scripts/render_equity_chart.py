from __future__ import annotations
import argparse
from pathlib import Path
from report_core import equity_svg, load_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    Path(args.out).write_text(equity_svg(load_data(args.report_data)["equity"]), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
