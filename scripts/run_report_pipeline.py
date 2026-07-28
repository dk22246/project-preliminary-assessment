"""Portable same-data report pipeline: HTML by default; PDF/Word on demand."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(command, check=False, env=env)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pdf", action="store_true", help="also convert the generated HTML to PDF")
    parser.add_argument("--word", action="store_true", help="also generate an editable Word report from the same data")
    parser.add_argument("--node", help="Node executable; required only with --pdf and/or --word")
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = Path(args.report_data)
    run([sys.executable, str(SCRIPTS / "validate_report_data.py"), str(data)])
    run([sys.executable, str(SCRIPTS / "validate_text_quality.py"), str(data)])
    run([sys.executable, str(SCRIPTS / "validate_business_policy_ledger.py"), str(data)])
    cards = out / "policy-cards.json"
    run([sys.executable, str(SCRIPTS / "export_policy_cards.py"), str(data), "--out", str(cards)])
    run([sys.executable, str(SCRIPTS / "validate_policy_scope.py"), str(cards)])
    run([sys.executable, str(SCRIPTS / "render_equity_chart.py"), str(data), "--out", str(out / "equity-chart.svg")])
    html = out / "report.html"
    run([sys.executable, str(SCRIPTS / "render_report_html.py"), str(data), "--out", str(html)])
    env: dict[str, str] | None = None
    if args.pdf or args.word:
        if not args.node:
            raise SystemExit("--pdf 或 --word 需要提供 --node；HTML 已生成。")
        node_path = Path(args.node).resolve()
        runtime_modules = node_path.parent.parent / "node_modules"
        env = dict(os.environ)
        if runtime_modules.exists():
            env.setdefault("REPORT_NODE_MODULES", str(runtime_modules))
    if args.pdf:
        run([args.node, str(SCRIPTS / "render_report_pdf.mjs"), str(html), str(out / "report.pdf")], env=env)
    if args.word:
        image = out / "equity-chart.png"
        run([args.node, str(SCRIPTS / "render_svg_png.mjs"), str(out / "equity-chart.svg"), str(image)], env=env)
        run([sys.executable, str(SCRIPTS / "render_report_word.py"), str(data), "--out", str(out / "report.docx"), "--equity-image", str(image)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
