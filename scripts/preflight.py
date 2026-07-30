#!/usr/bin/env python3
"""Verify that this Skill can be safely installed and run by another agent."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from report_core import load_data, validate_business_policy_ledger, validate_report_data, validate_text
from validate_evidence import validate_ledger
from validate_policy_scope import validate_policy


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "flyco-report-data.json"
EVIDENCE_SAMPLE = ROOT / "examples" / "evidence-sample.json"
REQUIRED = (
    "SKILL.md", "agents/openai.yaml", ".editorconfig", ".gitattributes",
    "references/policy-scope.md", "references/report-template.md", "references/html-delivery.md",
    "references/source-registry.md", "schemas/report.schema.json", "schemas/evidence.schema.json",
    "scripts/run_report_pipeline.py", "scripts/render_report_html.py", "scripts/collect_web_evidence.py", "scripts/validate_evidence.py",
    "scripts/evidence_collectors/__init__.py", "scripts/evidence_collectors/registry.py", "scripts/evidence_collectors/html_extract.py",
    "scripts/validate_policy_scope.py", "scripts/validate_report_data.py", "scripts/validate_text_quality.py",
    "tests/test_business_triggered_policy_logic.py", SAMPLE.relative_to(ROOT).as_posix(),
    EVIDENCE_SAMPLE.relative_to(ROOT).as_posix(), "examples/evidence-sample/official-policy.md",
)
TEXT_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".mjs", ".ps1", ".html", ".css"}


def text_files() -> list[Path]:
    ignored = {".git", "outputs", "__pycache__", ".pytest_cache"}
    return [path for path in ROOT.rglob("*") if path.is_file() and not ignored.intersection(path.parts) and path.suffix.lower() in TEXT_SUFFIXES]


def static_errors() -> list[str]:
    errors = [f"缺少部署文件：{path}" for path in REQUIRED if not (ROOT / path).is_file()]
    for path in text_files():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            errors.append(f"非UTF-8文本：{path.relative_to(ROOT)} ({error})")
            continue
        if chr(0xFFFD) in text:
            errors.append(f"发现乱码替代字符：{path.relative_to(ROOT)}")
    editorconfig = (ROOT / ".editorconfig").read_text(encoding="utf-8-sig") if (ROOT / ".editorconfig").is_file() else ""
    if "charset = utf-8" not in editorconfig:
        errors.append(".editorconfig 未锁定 UTF-8")
    if SAMPLE.is_file():
        try:
            data = load_data(SAMPLE)
        except (OSError, ValueError) as error:
            errors.append(f"示例数据无法按UTF-8读取：{error}")
        else:
            errors.extend(validate_report_data(data))
            errors.extend(validate_text(data))
            errors.extend(validate_business_policy_ledger(data))
            errors.extend(message for index, policy in enumerate(data.get("policies", [])) for message in validate_policy(policy, index))
    if EVIDENCE_SAMPLE.is_file():
        try:
            evidence = load_data(EVIDENCE_SAMPLE)
        except (OSError, ValueError) as error:
            errors.append(f"网页证据示例无法按UTF-8读取：{error}")
        else:
            errors.extend(validate_ledger(evidence, EVIDENCE_SAMPLE.parent))
    return errors


def smoke(out_dir: Path) -> int:
    command = [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "run_report_pipeline.py"), str(SAMPLE), "--out-dir", str(out_dir)]
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate portable UTF-8 Skill packaging and optionally render HTML.")
    parser.add_argument("--smoke", action="store_true", help="Run the sample through the full HTML pipeline.")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "qa_preflight", help="Output directory for --smoke.")
    args = parser.parse_args()
    errors = static_errors()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.smoke and smoke(args.out_dir) != 0:
        print("HTML 冒烟测试失败", file=sys.stderr)
        return 1
    print("通过：Skill 目录完整、文本均为UTF-8、示例数据及政策门禁有效、网页证据台账有效" + ("，HTML 冒烟测试通过" if args.smoke else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
