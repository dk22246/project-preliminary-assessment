#!/usr/bin/env python3
"""Single public controller for setup, ordered research gates, and delivery."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from doctor import check as check_runtime
from init_report_workspace import build_findings, build_payloads
from runtime_state import capability_errors, discover, load_verified_state, package_fingerprint, resolve_node, state_is_current
import workflow_state


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(command: list[str], *, env: dict[str, str] | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        check=False,
    )
    if result.returncode:
        detail = ((result.stdout or "") + (result.stderr or "")).strip()
        raise ValueError(detail or f"命令失败（exit {result.returncode}）：{' '.join(command)}")
    return result


def _npm_candidate(node: Path, explicit: str | None = None) -> str | None:
    candidates = [explicit, os.environ.get("REPORT_NPM_EXECUTABLE")]
    if sys.platform == "win32":
        candidates.extend((str(node.parent / "npm.cmd"), shutil.which("npm.cmd"), shutil.which("npm")))
    else:
        candidates.extend((str(node.parent / "npm"), shutil.which("npm")))
    for candidate in candidates:
        if candidate and (Path(candidate).is_file() or shutil.which(candidate)):
            return str(Path(candidate).resolve()) if Path(candidate).is_file() else str(candidate)
    return None


def setup_commands(*, node: Path, with_word: bool, npm: str | None = None) -> list[list[str]]:
    npm_command = npm or ("npm.cmd" if sys.platform == "win32" else "npm")
    commands = [
        [npm_command, "ci", "--ignore-scripts"],
        [str(node), str(ROOT / "node_modules" / "playwright" / "cli.js"), "install", "chromium"],
    ]
    if with_word:
        commands.append([sys.executable, "-X", "utf8", "-m", "pip", "install", "-r", str(ROOT / "requirements-word.txt")])
    return commands


def _verified_hints(node: str | None, chrome: str | None) -> tuple[str | None, str | None]:
    verified = load_verified_state() or {}
    return (
        node or str(verified.get("node", {}).get("path", "")) or None,
        chrome or str(verified.get("chrome", {}).get("path", "")) or None,
    )


def require_ready_runtime(node: str | None = None, chrome: str | None = None, *, need_word: bool = False) -> dict:
    node, chrome = _verified_hints(node, chrome)
    state, errors = check_runtime(node=node, chrome=chrome, need_word=need_word, require_verified=True)
    if errors:
        raise ValueError("运行环境尚未完成一次性配置：\n" + "\n".join(f"- {error}" for error in errors) + "\n请运行：python -X utf8 scripts/ppa.py setup")
    return state


def command_setup(args: argparse.Namespace) -> int:
    if sys.version_info < (3, 10):
        raise ValueError("Python版本必须>=3.10")
    previous = load_verified_state()
    hinted_node, hinted_chrome = _verified_hints(args.node, args.chrome)
    if not args.force and state_is_current(previous):
        _, current_errors = check_runtime(
            node=hinted_node, chrome=hinted_chrome, need_word=args.with_word, require_verified=True,
        )
        if not current_errors:
            print("通过：当前Skill与运行环境已经完成一次性配置；未重复下载或运行完整测试")
            return 0
    node = resolve_node(hinted_node)
    if not node:
        raise ValueError("未找到Node.js >=18；安装Node.js后重试，或用--node提供真实可执行文件")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    discovered = discover(str(node), hinted_chrome)
    base_errors = capability_errors(discovered, need_node=True, need_word=False)
    node_errors = [error for error in base_errors if "Node.js" in error or "Python" in error]
    if node_errors:
        raise ValueError("\n".join(node_errors))
    install_commands: list[list[str]] = []
    if not discovered.get("playwright") or not discovered.get("chrome", {}).get("path"):
        npm = _npm_candidate(node, args.npm)
        if not npm:
            raise ValueError("缺少Playwright/Chromium且未找到npm；请安装带npm的Node.js，或用--npm提供npm/npm.cmd路径")
        install_commands.extend(setup_commands(node=node, with_word=False, npm=npm))
    if args.with_word and not discovered.get("python_docx"):
        install_commands.append([sys.executable, "-X", "utf8", "-m", "pip", "install", "-r", str(ROOT / "requirements-word.txt")])
    for command in install_commands:
        _run(command, env=env)
    discovered = discover(str(node), hinted_chrome)
    chrome = str(discovered.get("chrome", {}).get("path", ""))
    if not chrome:
        raise ValueError("Playwright Chromium安装完成后仍无法定位浏览器；请用--chrome提供真实路径")
    bootstrap = [sys.executable, "-X", "utf8", str(SCRIPTS / "bootstrap.py"), "--node", str(node), "--chrome", chrome, "--force"]
    if args.with_word:
        bootstrap.append("--word")
    _run(bootstrap, env=env)
    print("通过：一次性运行环境安装与版本验证完成；日常报告不会重复下载依赖")
    return 0


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_start(args: argparse.Namespace) -> int:
    runtime = require_ready_runtime(args.node, args.chrome)
    enterprise = args.enterprise.strip()
    if not enterprise:
        raise ValueError("企业名称不能为空")
    work_dir = Path(args.work_dir).resolve()
    if work_dir.exists():
        raise ValueError(f"工作目录已存在，拒绝覆盖：{work_dir}")
    work_dir.mkdir(parents=True)
    try:
        for name, payload in {**build_payloads(enterprise), **build_findings(enterprise)}.items():
            _write_json(work_dir / name, payload)
        workflow_state.create(work_dir, enterprise, str(runtime.get("fingerprint") or package_fingerprint()))
    except Exception:
        if work_dir.exists() and not any(path for path in work_dir.iterdir() if path.name not in {*workflow_state.REPORT_ARTIFACTS, workflow_state.STATE_FILE}):
            shutil.rmtree(work_dir)
        raise
    print(f"已创建正式项目：{work_dir}\n当前阶段：environment_ready；下一步：完成主体确认后运行 ppa.py advance")
    return 0


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取{path.name}：{error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}必须是JSON对象")
    return value


def _validator(script: str, *arguments: str) -> None:
    _run([sys.executable, "-X", "utf8", str(SCRIPTS / script), *arguments], capture=True)


def _current_workspace(work_dir: str | Path, *, minimum_stage: str | None = None) -> tuple[Path, dict]:
    root = Path(work_dir).resolve()
    state = workflow_state.load(root)
    if state.get("skill_fingerprint") != package_fingerprint():
        raise ValueError("该项目由其他Skill版本创建；为防旧规则混入，请用当前版本重新start正式工作区")
    current = str(state.get("current_stage", ""))
    if minimum_stage and (
        current not in workflow_state.STAGES
        or workflow_state.STAGES.index(current) < workflow_state.STAGES.index(minimum_stage)
    ):
        raise ValueError(f"当前阶段为{current or '空'}；此操作至少需要完成{minimum_stage}")
    return root, state


def command_collect_web(args: argparse.Namespace) -> int:
    command = [
        sys.executable, "-X", "utf8", str(SCRIPTS / "collect_web_evidence.py"),
        args.enterprise, args.topic, "--out-dir", str(Path(args.out_dir).resolve()),
        "--purpose", args.purpose, "--timeout", str(args.timeout), "--retries", str(args.retries),
    ]
    for url in args.url:
        command.extend(["--url", url])
    for domain in args.allow_domain:
        command.extend(["--allow-domain", domain])
    result = _run(command, capture=True)
    ledger = Path(args.out_dir).resolve() / "evidence.json"
    _validator("validate_evidence.py", str(ledger))
    print((result.stdout or str(ledger)).strip())
    return 0


def command_collect_equity(args: argparse.Namespace) -> int:
    _run([
        sys.executable, "-X", "utf8", str(SCRIPTS / "collect_equity_provider.py"),
        args.legal_entity, "--provider", args.provider, "--input-json", str(Path(args.input_json).resolve()),
        "--out-dir", str(Path(args.out_dir).resolve()),
    ])
    print(Path(args.out_dir).resolve() / "normalized-equity-fragment.json")
    return 0


def command_search_catalog(args: argparse.Namespace) -> int:
    from search_industry_catalog import search

    result = search(args.query, args.subject_type, args.limit, not args.no_conflicts)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_compile(args: argparse.Namespace) -> int:
    from compile_workspace import compile_workspace

    work_dir, _ = _current_workspace(args.work_dir)
    compiled = compile_workspace(work_dir)
    print(json.dumps({"work_dir": str(work_dir), "generated": sorted(compiled)}, ensure_ascii=False))
    return 0


def command_research_plan(args: argparse.Namespace) -> int:
    from research_plan import write_research_plan

    work_dir, _ = _current_workspace(args.work_dir)
    plan = write_research_plan(work_dir / "enterprise-findings.json", work_dir / "research-plan.json")
    print(json.dumps({"work_dir": str(work_dir), "research_route": plan["research_route"], "actions": len(plan["actions"])}, ensure_ascii=False))
    return 0


def command_discover_policies(args: argparse.Namespace) -> int:
    from discover_current_policies import discover_current_policies

    work_dir, _ = _current_workspace(args.work_dir, minimum_stage="landing_businesses_complete")
    out_dir = Path(args.out_dir).resolve() if args.out_dir else work_dir / "evidence" / "policy-discovery"
    result = discover_current_policies(
        _load_json(work_dir / "research-ledger.json"),
        _load_json(work_dir / "report-data.json"),
        out_dir,
        max_concurrency=args.max_concurrency,
        max_retries=args.max_retries,
    )
    print(json.dumps({"out_dir": str(out_dir), **result["metrics"]}, ensure_ascii=False))
    return 0 if not result["metrics"]["failed_requests"] else 1


def _validate_stage(work_dir: Path, stage: str) -> dict:
    report = work_dir / "report-data.json"
    equity = work_dir / "equity-evidence.json"
    research = work_dir / "research-ledger.json"
    search = work_dir / "policy-search-ledger.json"
    policy = work_dir / "policy-evidence.json"
    data = _load_json(report)
    ledger = _load_json(research)
    if stage == "entity_confirmed":
        entity = data.get("entity_resolution", {})
        required = ("name_type", "legal_entity", "analysis_entity", "financial_scope", "risk_scope")
        missing = [field for field in required if not str(entity.get(field, "")).strip()]
        profile = ledger.get("enterprise_profile", {})
        if missing:
            raise ValueError("主体确认未完成，缺少：" + "、".join(missing))
        if profile.get("analysis_entity") != entity.get("analysis_entity"):
            raise ValueError("research-ledger分析主体与report-data不一致")
        if (profile.get("listing_status"), profile.get("research_route")) not in {
            ("listed", "listed_disclosure"), ("nonlisted", "nonlisted_public_evidence")
        }:
            raise ValueError("上市/非上市研究路由尚未锁定")
        return {"analysis_entity": entity["analysis_entity"], "research_route": profile["research_route"]}
    if stage == "enterprise_research_complete":
        _validator("validate_research_stop_gate.py", str(research))
        if not ledger.get("fact_ledger"):
            raise ValueError("企业事实台账为空")
        return {"validator": "validate_research_stop_gate.py", "fact_count": len(ledger["fact_ledger"])}
    if stage == "equity_financial_complete":
        _validator("validate_equity_evidence.py", str(equity), "--report-data", str(report), "--research-ledger", str(research))
        financials = data.get("financials", [])
        if len(financials) != 3:
            raise ValueError("必须完成最近三个完整年度的财务行或明确未公开状态")
        allowed = {"available", "partial", "not_public", "inaccessible"}
        if any(str(row.get("data_status", "")) not in allowed or not str(row.get("year", "")).strip() for row in financials):
            raise ValueError("财务年度或data_status未完成")
        return {"validator": "validate_equity_evidence.py", "financial_years": [row["year"] for row in financials]}
    if stage == "industry_catalog_complete":
        _validator("validate_encouraged_industry_assessment.py", str(report))
        return {"validator": "validate_encouraged_industry_assessment.py"}
    if stage == "landing_businesses_complete":
        landings = data.get("landing_businesses", [])
        required = ("id", "business", "fact_basis", "sanya_path", "value", "feasibility", "policy_departments")
        if not landings or any(any(not item.get(field) for field in required) for item in landings):
            raise ValueError("三亚落地业务及承接路径尚未完整填写")
        return {"landing_business_ids": [item["id"] for item in landings]}
    if stage == "policy_research_complete":
        _validator("validate_policy_search_coverage.py", str(search), "--research-ledger", str(research), "--report-data", str(report))
        _validator("validate_policy_evidence.py", str(policy), "--report-data", str(report), "--policy-search-ledger", str(search))
        _validator("validate_business_policy_ledger.py", str(report))
        return {"validators": ["validate_policy_search_coverage.py", "validate_policy_evidence.py", "validate_business_policy_ledger.py"]}
    if stage == "report_ready":
        _validator("validate_report_data.py", str(report))
        _validator("validate_text_quality.py", str(report))
        _validator("validate_encouraged_industry_assessment.py", str(report))
        _validator("validate_equity_evidence.py", str(equity), "--report-data", str(report), "--research-ledger", str(research))
        _validator("validate_research_ledger.py", str(research), "--report-data", str(report))
        _validator("validate_research_stop_gate.py", str(research), "--report-data", str(report))
        _validator("validate_policy_search_coverage.py", str(search), "--research-ledger", str(research), "--report-data", str(report))
        _validator("validate_policy_evidence.py", str(policy), "--report-data", str(report), "--policy-search-ledger", str(search))
        _validator("validate_business_policy_ledger.py", str(report))
        with tempfile.TemporaryDirectory() as temporary:
            cards = Path(temporary) / "policy-cards.json"
            _validator("export_policy_cards.py", str(report), "--out", str(cards))
            _validator("validate_policy_scope.py", str(cards))
        return workflow_state.artifact_hashes(work_dir)
    raise ValueError(f"阶段不允许由advance完成：{stage}")


def command_advance(args: argparse.Namespace) -> int:
    require_ready_runtime(args.node, args.chrome)
    work_dir = Path(args.work_dir).resolve()
    state = workflow_state.load(work_dir)
    if state.get("skill_fingerprint") != package_fingerprint():
        raise ValueError("该项目由其他Skill版本创建；为防旧规则混入，请用当前版本重新start正式工作区")
    if state.get("current_stage") in {"report_ready", "html_accepted"}:
        stale = workflow_state.ready_state_errors(work_dir, package_fingerprint())
        changed = any("发生变化" in error or "五台账指纹" in error for error in stale)
        if changed:
            receipt = _validate_stage(work_dir, "report_ready")
            workflow_state.refresh_report_ready(work_dir, receipt)
            print("通过：修订后的五份台账已重新完成report_ready门禁；下一步：ppa.py deliver")
            return 0
    completed: list[str] = []
    while True:
        stage = workflow_state.next_stage(workflow_state.load(work_dir))
        if stage is None:
            break
        if stage == "html_accepted":
            break
        try:
            receipt = _validate_stage(work_dir, stage)
        except ValueError as error:
            prefix = f"已连续通过：{'、'.join(completed)}\n" if completed else ""
            raise ValueError(prefix + f"当前停在{stage}：{error}") from error
        workflow_state.complete_stage(work_dir, stage, receipt)
        completed.append(stage)
        if stage == "report_ready":
            break
    following = workflow_state.next_stage(workflow_state.load(work_dir))
    if completed:
        print(f"通过：{'、'.join(completed)}" + (f"；下一阶段：{following}" if following else ""))
    elif following == "html_accepted":
        print("当前已到report_ready；下一步：ppa.py deliver")
    else:
        print("流程已经完成")
    return 0


def command_status(args: argparse.Namespace) -> int:
    runtime = require_ready_runtime(args.node, args.chrome, need_word=args.word)
    print(f"环境通过：Node={runtime['node']['path']}；Chromium={runtime['chrome']['path']}")
    if args.work_dir:
        state = workflow_state.load(args.work_dir)
        print(f"项目：{state.get('enterprise')}；run_id={state.get('run_id')}；当前阶段={state.get('current_stage')}；下一阶段={workflow_state.next_stage(state) or '无'}")
        if state.get("skill_fingerprint") != package_fingerprint():
            print("警告：项目状态来自其他Skill版本，正式交付前必须重新start")
    return 0


def command_deliver(args: argparse.Namespace) -> int:
    runtime = require_ready_runtime(args.node, args.chrome, need_word=args.word)
    work_dir = Path(args.work_dir).resolve()
    errors = workflow_state.ready_state_errors(work_dir, package_fingerprint())
    if errors:
        raise ValueError("正式交付门禁失败：\n" + "\n".join(f"- {error}" for error in errors))
    from run_report_pipeline import main as pipeline

    out = Path(args.out_dir).resolve()
    call = [
        str(work_dir / "report-data.json"), "--equity-evidence", str(work_dir / "equity-evidence.json"),
        "--research-ledger", str(work_dir / "research-ledger.json"), "--policy-search-ledger", str(work_dir / "policy-search-ledger.json"),
        "--policy-evidence", str(work_dir / "policy-evidence.json"), "--workflow-state", str(work_dir / workflow_state.STATE_FILE),
        "--out-dir", str(out), "--node", runtime["node"]["path"],
    ]
    if args.evidence:
        call.extend(["--evidence", args.evidence])
    if args.pdf:
        call.append("--pdf")
    if args.word:
        call.append("--word")
    result = pipeline(call, trusted_workflow=True)
    if result:
        return result
    state = workflow_state.mark_html_accepted(work_dir, out / "report.html")
    receipt = {
        "schema_version": "1.0",
        "run_id": state.get("run_id"),
        "enterprise": state.get("enterprise"),
        "skill_fingerprint": state.get("skill_fingerprint"),
        "artifact_hashes": state.get("ready_artifact_hashes"),
        "html": state.get("delivery"),
    }
    _write_json(out / "delivery-receipt.json", receipt)
    print(f"通过：HTML已生成并完成浏览器版式验收：{out / 'report.html'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="项目前期评估唯一执行入口")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="首次部署或版本变化时一次性安装并验证运行环境")
    setup.add_argument("--node")
    setup.add_argument("--npm")
    setup.add_argument("--chrome")
    setup.add_argument("--with-word", action="store_true")
    setup.add_argument("--force", action="store_true")
    setup.set_defaults(handler=command_setup)
    start = sub.add_parser("start", help="创建新企业五台账和强制流程状态")
    start.add_argument("enterprise")
    start.add_argument("--work-dir", required=True)
    start.add_argument("--node")
    start.add_argument("--chrome")
    start.set_defaults(handler=command_start)
    status = sub.add_parser("status", help="查看环境和项目下一阶段")
    status.add_argument("--work-dir")
    status.add_argument("--node")
    status.add_argument("--chrome")
    status.add_argument("--word", action="store_true")
    status.set_defaults(handler=command_status)
    advance = sub.add_parser("advance", help="按顺序连续通过全部已满足阶段并停在第一个缺口")
    advance.add_argument("--work-dir", required=True)
    advance.add_argument("--node")
    advance.add_argument("--chrome")
    advance.set_defaults(handler=command_advance)
    compile_command = sub.add_parser("compile", help="将两份精简输入原子编译为五份正式台账")
    compile_command.add_argument("--work-dir", required=True)
    compile_command.set_defaults(handler=command_compile)
    research_plan = sub.add_parser("research-plan", help="按上市或非上市路由生成最小企业研究行动清单")
    research_plan.add_argument("--work-dir", required=True)
    research_plan.set_defaults(handler=command_research_plan)
    collect_web = sub.add_parser("collect-web", help="采集并校验公开网页证据")
    collect_web.add_argument("enterprise")
    collect_web.add_argument("topic")
    collect_web.add_argument("--url", action="append", required=True)
    collect_web.add_argument("--out-dir", required=True)
    collect_web.add_argument("--allow-domain", action="append", default=[])
    collect_web.add_argument("--purpose", default="企业或政策公开事实核验")
    collect_web.add_argument("--timeout", type=int, default=15)
    collect_web.add_argument("--retries", type=int, default=1)
    collect_web.set_defaults(handler=command_collect_web)
    collect_equity = sub.add_parser("collect-equity", help="归一化可合法访问的企查查或天眼查网页取证")
    collect_equity.add_argument("legal_entity")
    collect_equity.add_argument("--provider", required=True, choices=("qcc-web", "tianyancha-web"))
    collect_equity.add_argument("--input-json", required=True)
    collect_equity.add_argument("--out-dir", required=True)
    collect_equity.set_defaults(handler=command_collect_equity)
    catalog = sub.add_parser("search-catalog", help="按主体性质召回鼓励类目录候选并列出冲突")
    catalog.add_argument("query", nargs="+")
    catalog.add_argument("--subject-type", choices=("domestic", "foreign"), required=True)
    catalog.add_argument("--limit", type=int, default=12)
    catalog.add_argument("--no-conflicts", action="store_true")
    catalog.set_defaults(handler=command_search_catalog)
    discover_policy = sub.add_parser("discover-policies", help="按已确认落地业务和主管部门路由实时抓取政策入口草案")
    discover_policy.add_argument("--work-dir", required=True)
    discover_policy.add_argument("--out-dir")
    discover_policy.add_argument("--max-concurrency", type=int, default=4)
    discover_policy.add_argument("--max-retries", type=int, default=2)
    discover_policy.set_defaults(handler=command_discover_policies)
    deliver = sub.add_parser("deliver", help="在全部阶段和五台账指纹通过后生成报告")
    deliver.add_argument("--work-dir", required=True)
    deliver.add_argument("--out-dir", required=True)
    deliver.add_argument("--node")
    deliver.add_argument("--chrome")
    deliver.add_argument("--evidence")
    deliver.add_argument("--pdf", action="store_true")
    deliver.add_argument("--word", action="store_true")
    deliver.set_defaults(handler=command_deliver)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
