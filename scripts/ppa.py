#!/usr/bin/env python3
"""Single public controller for setup, ordered research gates, and delivery."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
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
    print(f"已创建正式项目：{work_dir}\n当前阶段：environment_ready；下一步：在 enterprise-findings.json 确认主体和研究路由，再运行 ppa.py research-plan")
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


def _validator_errors(script: str, *arguments: str) -> list[str]:
    result = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / script), *arguments],
        cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False,
    )
    if not result.returncode:
        return []
    detail = ((result.stdout or "") + (result.stderr or "")).strip()
    return [f"{script}: {detail or f'exit {result.returncode}'}"]


def _current_workspace(work_dir: str | Path, *, minimum_stage: str | None = None) -> tuple[Path, dict]:
    root = Path(work_dir).resolve()
    state = workflow_state.load(root)
    if state.get("skill_fingerprint") != package_fingerprint():
        raise ValueError("项目版本已变化；请运行 ppa.py resume --work-dir 原目录，保留资料后重新编译核验")
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

    work_dir, state = _current_workspace(args.work_dir)
    inputs = {
        "enterprise": _file_sha256(work_dir / "enterprise-findings.json"),
        "policy": _file_sha256(work_dir / "policy-findings.json"),
    }
    fingerprint = package_fingerprint()
    receipt = state.get("compile_receipt", {})
    artifacts_exist = all((work_dir / name).is_file() for name in workflow_state.REPORT_ARTIFACTS)
    if (
        receipt.get("skill_fingerprint") == fingerprint
        and receipt.get("inputs") == inputs
        and state.get("findings_input_sha256") == inputs
        and artifacts_exist
        and receipt.get("outputs") == workflow_state.artifact_hashes(work_dir)
    ):
        print(json.dumps({"work_dir": str(work_dir), "generated": [], "reused": True}, ensure_ascii=False))
        return 0
    compiled = compile_workspace(work_dir)
    state = workflow_state.load(work_dir)
    state["findings_input_sha256"] = inputs
    state["compile_receipt"] = {
        "skill_fingerprint": fingerprint,
        "inputs": inputs,
        "outputs": workflow_state.artifact_hashes(work_dir),
    }
    workflow_state.save(work_dir, state)
    _refresh_enterprise_prepare_receipt(work_dir)
    print(json.dumps({"work_dir": str(work_dir), "generated": sorted(compiled)}, ensure_ascii=False))
    return 0


def command_migrate_findings(args: argparse.Namespace) -> int:
    from compile_workspace import migrate_legacy_equity, migrate_legacy_policy_findings

    work_dir = Path(args.work_dir).resolve()
    enterprise_path = work_dir / "enterprise-findings.json"
    policy_path = work_dir / "policy-findings.json"
    enterprise = _load_json(enterprise_path)
    policy = _load_json(policy_path)
    migrated_enterprise = migrate_legacy_equity(enterprise)
    migrated_policy = migrate_legacy_policy_findings(policy, migrated_enterprise)
    from findings_contract import validate_findings_contracts
    errors = validate_findings_contracts(migrated_enterprise, migrated_policy)
    if errors:
        raise ValueError("迁移后输入契约错误：\n" + "\n".join(errors))
    with tempfile.TemporaryDirectory(dir=work_dir) as temporary:
        root = Path(temporary)
        _write_json(root / enterprise_path.name, migrated_enterprise)
        _write_json(root / policy_path.name, migrated_policy)
        (root / enterprise_path.name).replace(enterprise_path)
        (root / policy_path.name).replace(policy_path)
    print(json.dumps({"work_dir": str(work_dir), "migrated": [enterprise_path.name, policy_path.name], "workflow_state": "unchanged"}, ensure_ascii=False))
    return 0


def _enterprise_input_fingerprint(work_dir: Path) -> str:
    return hashlib.sha256((work_dir / "enterprise-findings.json").read_bytes()).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _enterprise_view_hashes(work_dir: Path) -> dict[str, str]:
    """Hash only enterprise-owned views, excluding policy-derived report fields."""
    report = _load_json(work_dir / "report-data.json")
    report = json.loads(json.dumps(report, ensure_ascii=False))
    report.pop("policy_research", None)
    report.pop("policy_opportunity_radar", None)
    report.pop("policies", None)
    if isinstance(report.get("meta"), dict):
        report["meta"].pop("policy_researched_at", None)
        report["meta"].pop("policy_search_mode", None)
    values = {
        "report-data.json": report,
        "research-ledger.json": _load_json(work_dir / "research-ledger.json"),
        "equity-evidence.json": _load_json(work_dir / "equity-evidence.json"),
    }
    return {
        name: hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        for name, value in values.items()
    }


def _refresh_enterprise_prepare_receipt(work_dir: Path) -> None:
    state = workflow_state.load(work_dir)
    if (
        state.get("enterprise_input_sha256") == _enterprise_input_fingerprint(work_dir)
        and all((work_dir / name).is_file() for name in ("report-data.json", "research-ledger.json", "equity-evidence.json"))
    ):
        state["enterprise_prepare_artifact_hashes"] = _enterprise_view_hashes(work_dir)
        workflow_state.save(work_dir, state)


def _findings_input_errors(work_dir: Path, state: dict) -> list[str]:
    bound = state.get("findings_input_sha256")
    if not isinstance(bound, dict):
        return ["尚无成功compile的输入绑定；请先修正输入并运行compile，不执行后续整套校验"]
    errors: list[str] = []
    for kind, name in (("enterprise", "enterprise-findings.json"), ("policy", "policy-findings.json")):
        expected = str(bound.get(kind, ""))
        path = work_dir / name
        if not expected:
            errors.append(f"缺少{kind} findings输入绑定SHA")
        elif not path.is_file():
            errors.append(f"缺少{ name }")
        elif _file_sha256(path) != expected:
            errors.append(f"{name}已变化，必须重新compile并finalize")
    return errors


def _validate_enterprise_payloads(work_dir: Path, compiled: dict[str, dict]) -> list[tuple[str, dict]]:
    """Validate only the ordered enterprise stages against candidate ledgers."""
    with tempfile.TemporaryDirectory(dir=work_dir) as temporary:
        candidate = Path(temporary)
        (candidate / "report-data.json").write_text(
            json.dumps(compiled["report-data.json"], ensure_ascii=False), encoding="utf-8"
        )
        (candidate / "research-ledger.json").write_text(
            json.dumps(compiled["research-ledger.json"], ensure_ascii=False), encoding="utf-8"
        )
        receipts: list[tuple[str, dict]] = []
        errors: list[str] = []
        for stage in workflow_state.STAGES[1 : workflow_state.STAGES.index("landing_businesses_complete") + 1]:
            try:
                receipts.append((stage, _validate_lightweight_stage(candidate, stage)))
            except ValueError as error:
                errors.append(f"{stage}: {error}")
        if errors:
            raise ValueError("企业轻量阶段校验失败：\n" + "\n".join(errors))
        return receipts


def command_prepare_enterprise(args: argparse.Namespace) -> int:
    """Compile and complete the enterprise-only chain without reading policy input."""
    from compile_workspace import compile_enterprise_findings

    work_dir, state = _current_workspace(args.work_dir)
    input_path = work_dir / "enterprise-findings.json"
    if not input_path.is_file():
        raise ValueError("缺少enterprise-findings.json")
    findings = _load_json(input_path)
    if str(findings.get("enterprise", "")).strip() != str(state.get("enterprise", "")).strip():
        raise ValueError("enterprise-findings.json企业主体与流程状态不一致")
    fingerprint = _enterprise_input_fingerprint(work_dir)
    required_names = ("report-data.json", "research-ledger.json", "equity-evidence.json")
    prepared_hashes = state.get("enterprise_prepare_artifact_hashes")
    fast_path_valid = (
        state.get("enterprise_input_sha256") == fingerprint
        and isinstance(prepared_hashes, dict)
        and all((work_dir / name).is_file() for name in required_names)
        and prepared_hashes == _enterprise_view_hashes(work_dir)
        and workflow_state.STAGES.index(str(state.get("current_stage"))) >= workflow_state.STAGES.index("landing_businesses_complete")
    )
    if fast_path_valid:
        print("通过：企业准备阶段已按相同输入完成，未重复编译或改变政策台账")
        return 0

    compiled = compile_enterprise_findings(findings, work_dir)
    receipts = _validate_enterprise_payloads(work_dir, compiled)
    # Only after every enterprise stage passes, replace the three enterprise ledgers.
    with tempfile.TemporaryDirectory(dir=work_dir) as temporary:
        temporary_root = Path(temporary)
        for name in required_names:
            _write_json(temporary_root / name, compiled[name])
        for name in required_names:
            (temporary_root / name).replace(work_dir / name)

    current = str(state.get("current_stage", ""))
    if current not in workflow_state.STAGES:
        raise ValueError(f"未知流程阶段：{current or '空'}")
    # Any changed enterprise input invalidates an earlier report_ready receipt.
    state["current_stage"] = "environment_ready"
    state["completed_stages"] = ["environment_ready"]
    state["history"] = [row for row in state.get("history", []) if row.get("stage") == "environment_ready"]
    state["ready_artifact_hashes"] = {}
    state["delivery"] = {}
    state["enterprise_input_sha256"] = fingerprint
    state["enterprise_prepare_artifact_hashes"] = _enterprise_view_hashes(work_dir)
    workflow_state.save(work_dir, state)
    for stage, receipt in receipts:
        workflow_state.complete_stage(work_dir, stage, receipt)
    print(json.dumps({"work_dir": str(work_dir), "current_stage": "landing_businesses_complete", "policy_input": "not_required"}, ensure_ascii=False))
    return 0


def command_research_plan(args: argparse.Namespace) -> int:
    from research_plan import write_research_plan

    work_dir, _ = _current_workspace(args.work_dir)
    plan = write_research_plan(work_dir / "enterprise-findings.json", work_dir / "research-plan.json")
    print(json.dumps({"work_dir": str(work_dir), "research_route": plan["research_route"], "actions": len(plan["actions"])}, ensure_ascii=False))
    return 0


def command_discover_policies(args: argparse.Namespace) -> int:
    work_dir, _ = _current_workspace(args.work_dir, minimum_stage="landing_businesses_complete")
    state = workflow_state.load(work_dir)
    expected_input_sha = str(state.get("enterprise_input_sha256", ""))
    if not expected_input_sha or _enterprise_input_fingerprint(work_dir) != expected_input_sha:
        raise ValueError("企业输入已变化或缺少prepare-enterprise回执；请先重新运行prepare-enterprise")
    from discover_current_policies import discover_current_policies, merge_discovery_fragment
    out_dir = Path(args.out_dir).resolve() if args.out_dir else work_dir / "evidence" / "policy-discovery"
    result = discover_current_policies(
        _load_json(work_dir / "research-ledger.json"),
        _load_json(work_dir / "report-data.json"),
        out_dir,
        max_concurrency=args.max_concurrency,
        max_retries=args.max_retries,
        request_timeout=args.request_timeout,
    )
    merge_discovery_fragment(work_dir / "policy-findings.json", out_dir / "policy-findings-fragment.json")
    print(json.dumps({"out_dir": str(out_dir), **result["metrics"]}, ensure_ascii=False))
    return 0 if not result["metrics"]["failed_requests"] else 1


def _validate_lightweight_stage(work_dir: Path, stage: str) -> dict:
    """Check stage presence only; formal semantic validators run once in finalize."""
    report = _load_json(work_dir / "report-data.json")
    research = _load_json(work_dir / "research-ledger.json")
    if stage == "entity_confirmed":
        entity = report.get("entity_resolution", {})
        profile = research.get("enterprise_profile", {})
        required = ("name_type", "legal_entity", "analysis_entity", "financial_scope", "risk_scope")
        missing = [field for field in required if not str(entity.get(field, "")).strip()]
        if missing:
            raise ValueError("主体确认未完成，缺少：" + "、".join(missing))
        if (profile.get("listing_status"), profile.get("research_route")) not in {
            ("listed", "listed_disclosure"), ("nonlisted", "nonlisted_public_evidence")
        }:
            raise ValueError("上市/非上市研究路由尚未锁定")
        return {"analysis_entity": entity["analysis_entity"], "research_route": profile["research_route"]}
    if stage == "enterprise_research_complete":
        if not research.get("fact_ledger") or not research.get("business_candidates"):
            raise ValueError("企业事实或业务候选尚未编译")
        return {"compiled": True, "fact_count": len(research["fact_ledger"])}
    if stage == "equity_financial_complete":
        financials = report.get("financials", [])
        years = [str(row.get("year", "")).strip() for row in financials if isinstance(row, dict)]
        if len(financials) != 3 or len(years) != 3 or not all(years) or len(set(years)) != 3:
            raise ValueError("最近三个完整年度财务尚未完成")
        return {"compiled": True, "financial_years": years}
    if stage == "industry_catalog_complete":
        assessments = report.get("encouraged_industry_assessment")
        if not isinstance(assessments, dict):
            raise ValueError("鼓励类产业目录判断模块尚未编译")
        required = ("catalog_version", "catalogs_checked", "business_assessments")
        if any(not assessments.get(field) for field in required):
            raise ValueError("鼓励类产业目录判断模块字段不完整")
        business_ids = {str(item.get("id", "")) for item in report.get("businesses", []) if isinstance(item, dict)}
        assessed_ids = {str(item.get("business_id", "")) for item in assessments.get("business_assessments", []) if isinstance(item, dict)}
        if not business_ids or not business_ids.issubset(assessed_ids):
            raise ValueError("鼓励类产业目录判断未覆盖全部企业业务")
        source_ids = {str(item.get("id", "")) for item in report.get("sources", [])}
        if not any(source_id.startswith("P") for source_id in source_ids):
            raise ValueError("鼓励类产业目录判断缺少P类官方目录来源")
        return {"compiled": True}
    if stage == "landing_businesses_complete":
        landings = report.get("landing_businesses", [])
        required = ("id", "business", "fact_basis", "sanya_path", "value", "feasibility", "policy_departments")
        if not isinstance(landings, list) or not landings or any(
            not isinstance(item, dict) or any(not item.get(field) for field in required) for item in landings
        ):
            raise ValueError("三亚落地业务及承接路径尚未完整填写")
        return {"compiled": True, "landing_business_ids": [item["id"] for item in landings]}
    if stage == "policy_research_complete":
        coverage = _load_json(work_dir / "policy-search-ledger.json")
        evidence = _load_json(work_dir / "policy-evidence.json")
        if not coverage.get("searches") or not coverage.get("researched_at"):
            raise ValueError("实时政策检索结果尚未编译")
        if not evidence.get("records"):
            raise ValueError("正式政策证据尚未编译")
        return {"compiled": True, "search_count": len(coverage["searches"]), "evidence_count": len(evidence["records"])}
    raise ValueError(f"未知轻量阶段：{stage}")


def _validate_final_suite(work_dir: Path) -> dict:
    """Run every formal semantic gate exactly once and bind the five ledgers."""
    report = work_dir / "report-data.json"
    equity = work_dir / "equity-evidence.json"
    research = work_dir / "research-ledger.json"
    search = work_dir / "policy-search-ledger.json"
    policy = work_dir / "policy-evidence.json"
    errors: list[str] = []
    checks = (
        ("validate_report_data.py", (str(report),)),
        ("validate_text_quality.py", (str(report),)),
        ("validate_encouraged_industry_assessment.py", (str(report),)),
        ("validate_equity_evidence.py", (str(equity), "--report-data", str(report), "--research-ledger", str(research))),
        ("validate_research_ledger.py", (str(research), "--report-data", str(report))),
        ("validate_research_stop_gate.py", (str(research), "--report-data", str(report))),
        ("validate_policy_search_coverage.py", (str(search), "--research-ledger", str(research), "--report-data", str(report), "--policy-evidence", str(policy))),
        ("validate_policy_evidence.py", (str(policy), "--report-data", str(report), "--policy-search-ledger", str(search))),
        ("validate_business_policy_ledger.py", (str(report),)),
    )
    # Read-only gates share immutable compiled artifacts, not mutable output files.
    # Collect in declaration order so parallel execution cannot scramble diagnostics.
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(_validator_errors, script, *arguments) for script, arguments in checks]
        for future in futures:
            errors.extend(future.result())
    with tempfile.TemporaryDirectory() as temporary:
        cards = Path(temporary) / "policy-cards.json"
        errors.extend(_validator_errors("export_policy_cards.py", str(report), "--out", str(cards)))
        if cards.is_file():
            errors.extend(_validator_errors("validate_policy_scope.py", str(cards)))
    if errors:
        raise ValueError("最终语义门禁失败（已汇总独立错误）：\n" + "\n".join(errors))
    return workflow_state.artifact_hashes(work_dir)


def command_finalize(args: argparse.Namespace) -> int:
    require_ready_runtime(args.node, args.chrome)
    work_dir = Path(args.work_dir).resolve()
    state = workflow_state.load(work_dir)
    if state.get("skill_fingerprint") != package_fingerprint():
        raise ValueError("项目版本已变化；请先运行 ppa.py resume --work-dir 原目录")
    input_errors = _findings_input_errors(work_dir, state)
    if input_errors:
        raise ValueError("findings输入绑定失败：\n" + "\n".join(input_errors))
    current = str(state.get("current_stage", ""))
    if current in {"report_ready", "html_accepted"}:
        stale = workflow_state.ready_state_errors(work_dir, package_fingerprint())
        if not stale:
            print("通过：最终门禁及五台账哈希仍然有效；下一步：ppa.py deliver")
            return 0
    receipts: list[tuple[str, dict]] = []
    current_index = workflow_state.STAGES.index(current)
    for stage in workflow_state.STAGES[current_index + 1: workflow_state.STAGES.index("report_ready")]:
        try:
            receipts.append((stage, _validate_lightweight_stage(work_dir, stage)))
        except ValueError as error:
            receipts.append((stage, {"validation_error": str(error)}))
    lightweight_errors = [
        f"{stage}: {receipt['validation_error']}"
        for stage, receipt in receipts if "validation_error" in receipt
    ]
    formal_errors: list[str] = []
    hashes: dict[str, str] | None = None
    try:
        hashes = _validate_final_suite(work_dir)
    except ValueError as error:
        formal_errors.append(str(error))
    if lightweight_errors or formal_errors:
        sections = []
        if lightweight_errors:
            sections.append("轻量阶段校验失败（独立汇总）：\n" + "\n".join(lightweight_errors))
        if formal_errors:
            sections.append("正式语义门禁失败（独立汇总）：\n" + "\n".join(formal_errors))
        raise ValueError("\n".join(sections))
    assert hashes is not None
    if current in {"report_ready", "html_accepted"}:
        workflow_state.refresh_report_ready(work_dir, hashes)
    else:
        for stage, receipt in receipts:
            workflow_state.complete_stage(work_dir, stage, receipt)
        workflow_state.complete_stage(work_dir, "report_ready", hashes)
    print("通过：一次最终完整门禁已完成并绑定五份台账；下一步：ppa.py deliver")
    return 0


def command_advance(args: argparse.Namespace) -> int:
    print("提示：advance为兼容别名，当前执行一次最终门禁finalize")
    return command_finalize(args)


def command_status(args: argparse.Namespace) -> int:
    runtime = require_ready_runtime(args.node, args.chrome, need_word=args.word)
    print(f"环境通过：Node={runtime['node']['path']}；Chromium={runtime['chrome']['path']}")
    if args.work_dir:
        state = workflow_state.load(args.work_dir)
        print(f"项目：{state.get('enterprise')}；run_id={state.get('run_id')}；当前阶段={state.get('current_stage')}；下一阶段={workflow_state.next_stage(state) or '无'}")
        if state.get("skill_fingerprint") != package_fingerprint():
            print("项目版本已变化：运行 ppa.py resume --work-dir 原目录保留资料接续")
    return 0


def command_resume(args: argparse.Namespace) -> int:
    """Keep compatible inputs and evidence; invalidate approvals from old code."""
    from findings_contract import validate_enterprise_findings
    root = Path(args.work_dir).resolve()
    state = workflow_state.load(root)
    findings = _load_json(root / "enterprise-findings.json")
    if findings.get("version") != "1.0" or findings.get("enterprise") != state.get("enterprise"):
        raise ValueError("输入契约版本或主体不兼容；资料保留，需显式迁移")
    errors = validate_enterprise_findings(findings)
    if errors:
        raise ValueError("原工作区输入需修正，资料未改动：\n" + "\n".join(errors))
    fingerprint = package_fingerprint()
    if state.get("skill_fingerprint") == fingerprint:
        print("工作区版本一致，保留当前进度；按status继续")
        return 0
    backup = root / ("workflow-state.before-resume-" + str(state.get("skill_fingerprint", "unknown"))[:12] + ".json")
    if not backup.exists():
        _write_json(backup, state)
    state["skill_fingerprint"] = fingerprint
    state["current_stage"] = "environment_ready"
    state["completed_stages"] = ["environment_ready"]
    state["ready_artifact_hashes"] = {}
    state["delivery"] = {}
    for key in ("enterprise_input_sha256", "enterprise_prepare_artifact_hashes", "findings_input_sha256"):
        state.pop(key, None)
    workflow_state.save(root, state)
    print("已接续兼容工作区；输入与证据保留。下一步prepare-enterprise、compile、finalize，不必重新start。")
    return 0


def command_deliver(args: argparse.Namespace) -> int:
    runtime = require_ready_runtime(args.node, args.chrome, need_word=args.word)
    work_dir = Path(args.work_dir).resolve()
    errors = workflow_state.ready_state_errors(work_dir, package_fingerprint())
    errors.extend(_findings_input_errors(work_dir, workflow_state.load(work_dir)))
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
    advance = sub.add_parser("advance", help="兼容旧调用；等同于 finalize，不再逐阶段运行正式校验")
    advance.add_argument("--work-dir", required=True)
    advance.add_argument("--node")
    advance.add_argument("--chrome")
    advance.set_defaults(handler=command_advance)
    finalize = sub.add_parser("finalize", help="对编译后的五份台账执行唯一一次完整正式门禁")
    finalize.add_argument("--work-dir", required=True)
    finalize.add_argument("--node")
    finalize.add_argument("--chrome")
    finalize.set_defaults(handler=command_finalize)
    compile_command = sub.add_parser("compile", help="将两份精简输入原子编译为五份正式台账")
    compile_command.add_argument("--work-dir", required=True)
    compile_command.set_defaults(handler=command_compile)
    migrate = sub.add_parser("migrate-findings", help="显式迁移旧版双写输入为canonical findings契约")
    migrate.add_argument("--work-dir", required=True)
    migrate.set_defaults(handler=command_migrate_findings)
    prepare = sub.add_parser("prepare-enterprise", help="企业侧三台账编译与落地阶段准备；不依赖政策输入")
    prepare.add_argument("--work-dir", required=True)
    prepare.set_defaults(handler=command_prepare_enterprise)
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
    discover_policy.add_argument("--request-timeout", type=float, default=10)
    discover_policy.set_defaults(handler=command_discover_policies)
    resume = sub.add_parser("resume", help="兼容版本更新后保留资料接续；重新编译核验")
    resume.add_argument("--work-dir", required=True)
    resume.set_defaults(handler=command_resume)
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
