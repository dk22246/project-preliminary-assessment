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


def python_command(script: Path, *args: str) -> list[str]:
    """Keep every nested validator on UTF-8, even when the caller is PowerShell."""
    return [sys.executable, "-X", "utf8", str(script), *args]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pdf", action="store_true", help="also convert the generated HTML to PDF")
    parser.add_argument("--word", action="store_true", help="also generate an editable Word report from the same data")
    parser.add_argument("--node", help="Node executable; mandatory after data and policy validation for the browser layout gate and optional PDF/Word conversion")
    parser.add_argument("--evidence", help="optional validated public-web evidence ledger used in this report")
    parser.add_argument("--equity-evidence", required=True, help="validated provider-backed equity evidence ledger")
    parser.add_argument("--research-ledger", required=True, help="validated business discovery and policy routing ledger")
    parser.add_argument("--policy-search-ledger", required=True, help="validated dynamic policy-search coverage ledger")
    args = parser.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = Path(args.report_data)
    if args.evidence:
        run(python_command(SCRIPTS / "validate_evidence.py", args.evidence))
    run(python_command(SCRIPTS / "validate_report_data.py", str(data)))
    run(python_command(SCRIPTS / "validate_text_quality.py", str(data)))
    run(python_command(SCRIPTS / "validate_encouraged_industry_assessment.py", str(data)))
    run(python_command(SCRIPTS / "validate_equity_evidence.py", args.equity_evidence, "--report-data", str(data)))
    run(python_command(SCRIPTS / "validate_research_ledger.py", args.research_ledger, "--report-data", str(data)))
    run(python_command(SCRIPTS / "validate_policy_search_coverage.py", args.policy_search_ledger, "--research-ledger", args.research_ledger, "--report-data", str(data)))
    run(python_command(SCRIPTS / "validate_business_policy_ledger.py", str(data)))
    if not args.node:
        raise SystemExit("所有数据与政策校验通过后，仍必须提供 --node 运行 HTML 版式验收。")
    cards = out / "policy-cards.json"
    run(python_command(SCRIPTS / "export_policy_cards.py", str(data), "--out", str(cards)))
    run(python_command(SCRIPTS / "validate_policy_scope.py", str(cards)))
    run(python_command(SCRIPTS / "render_equity_chart.py", str(data), "--out", str(out / "equity-chart.svg")))
    html = out / "report.html"
    run(python_command(SCRIPTS / "render_report_html.py", str(data), "--out", str(html)))
    node_path = Path(args.node).resolve()
    if not node_path.is_file():
        raise SystemExit(f"未找到 Node 可执行文件：{node_path}")
    runtime_modules = node_path.parent.parent / "node_modules"
    env: dict[str, str] = dict(os.environ)
    if runtime_modules.exists():
        env.setdefault("REPORT_NODE_MODULES", str(runtime_modules))
    layout = subprocess.run([args.node, str(SCRIPTS / "verify_html_layout.mjs"), str(html)], env=env, check=False)
    if layout.returncode:
        raise SystemExit("HTML 版式验收失败，禁止生成或交付后续文件。")
    if args.pdf:
        run([args.node, str(SCRIPTS / "render_report_pdf.mjs"), str(html), str(out / "report.pdf")], env=env)
    if args.word:
        image = out / "equity-chart.png"
        run([args.node, str(SCRIPTS / "render_svg_png.mjs"), str(out / "equity-chart.svg"), str(image)], env=env)
        run(python_command(SCRIPTS / "render_report_word.py", str(data), "--out", str(out / "report.docx"), "--equity-image", str(image)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
