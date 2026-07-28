"""Export report policy cards for the standalone policy-scope gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from report_core import load_data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    Path(args.out).write_text(json.dumps({"policies": load_data(args.report_data)["policies"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
