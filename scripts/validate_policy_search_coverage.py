#!/usr/bin/env python3
"""Fail closed when business-triggered policy discovery has incomplete coverage."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlparse

from report_core import load_data


DISCOVERY_PATHS = (
    "theme_search",
    "department_documents",
    "normative_documents",
    "application_notices",
    "award_publicity",
    "invalidity_catalog",
    "document_graph",
)
RUN_STATUSES = {"complete", "not_available", "failed", "partial"}
SEARCH_STATUSES = {"complete", "research_incomplete"}
DEPARTMENT_ROLES = {
    "primary_regulator",
    "funding_authority",
    "co_issuer",
    "application_authority",
    "execution_authority",
    "provincial_counterpart",
    "municipal_counterpart",
}
CURRENT_POLICY_STATUSES = {"current", "current_open", "current_no_open_call", "current_conditional"}
ELIGIBILITY_STATUSES = {"unknown", "eligible", "ineligible", "not_triggered"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _index(rows: object, label: str, errors: list[str]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    if not isinstance(rows, list):
        errors.append(f"{label}: 必须为数组")
        return indexed
    for row in rows:
        if not isinstance(row, dict):
            errors.append(f"{label}: 存在非对象记录")
            continue
        identifier = _text(row.get("id"))
        if not identifier:
            errors.append(f"{label}: 缺少id")
        elif identifier in indexed:
            errors.append(f"{label}: id重复：{identifier}")
        else:
            indexed[identifier] = row
    return indexed


def _specific_url(value: object) -> bool:
    parsed = urlparse(_text(value))
    return parsed.scheme == "https" and bool(parsed.netloc) and parsed.path not in {"", "/"}


def _report_items(report_data: dict) -> dict[tuple[str, str], dict]:
    items: dict[tuple[str, str], dict] = {}
    for item in report_data.get("policy_research", []):
        key = (_text(item.get("landing_business_id")), _text(item.get("topic")))
        if all(key):
            items[key] = item
    return items


def validate_policy_search_coverage(coverage: dict, research_ledger: dict, report_data: dict, *, allow_stale_fixture: bool = False) -> list[str]:
    """Validate semantic expansion, seven-path receipts and report conclusion boundaries."""
    errors: list[str] = []
    for field in ("enterprise", "researched_at", "search_mode", "landing_business_hypotheses", "searches", "policy_candidates"):
        if field not in coverage or coverage.get(field) is None or (field != "policy_candidates" and not coverage.get(field)):
            errors.append(f"政策检索台账缺少{field}")
    if errors:
        return errors

    researched_at = _text(coverage.get("researched_at"))
    report_researched_at = _text(report_data.get("meta", {}).get("policy_researched_at"))
    if _text(coverage.get("search_mode")) != "realtime" or _text(report_data.get("meta", {}).get("policy_search_mode")) != "realtime":
        errors.append("政策检索必须标记为realtime")
    if researched_at != report_researched_at:
        errors.append("政策检索台账时间与报告policy_researched_at不一致")
    try:
        researched_dt = datetime.fromisoformat(researched_at.replace("Z", "+00:00"))
    except ValueError:
        errors.append("政策检索时间必须为ISO 8601日期时间")
    else:
        if researched_dt.tzinfo is None:
            errors.append("政策检索时间必须包含时区")
        elif not allow_stale_fixture:
            age_seconds = (datetime.now(timezone.utc) - researched_dt.astimezone(timezone.utc)).total_seconds()
            if age_seconds < -600 or age_seconds > 86400:
                errors.append("政策检索结果已超过24小时或时间异常，必须重新实时核验")

    routes = _index(research_ledger.get("department_routes", []), "研究底稿主管部门路由", errors)
    facts = _index(research_ledger.get("fact_ledger", []), "研究底稿企业事实", errors)
    landings = {_text(item.get("id")) for item in report_data.get("landing_businesses", []) if _text(item.get("id"))}
    report_items = _report_items(report_data)
    hypotheses = _index(coverage.get("landing_business_hypotheses"), "业务语义假设", errors)
    searches = _index(coverage.get("searches"), "政策检索任务", errors)
    candidates = _index(coverage.get("policy_candidates"), "政策候选", errors)
    scan_profiles = _index(coverage.get("department_scan_profiles", []), "部门检索回执档案", errors)
    sources = {_text(item.get("id")) for item in report_data.get("sources", []) if _text(item.get("id"))}

    hypotheses_by_landing: dict[str, list[dict]] = {}
    for hypothesis_id, hypothesis in hypotheses.items():
        landing_id = _text(hypothesis.get("landing_business_id"))
        if landing_id not in landings:
            errors.append(f"{hypothesis_id}: 未关联有效落地业务")
        else:
            hypotheses_by_landing.setdefault(landing_id, []).append(hypothesis)
        for field in ("actions", "roles", "forms", "effects", "government_matters", "policy_instruments"):
            if not hypothesis.get(field):
                errors.append(f"{hypothesis_id}: 缺少{field}")
        for fact_id in hypothesis.get("fact_ids", []):
            if _text(fact_id) not in facts:
                errors.append(f"{hypothesis_id}: 引用了不存在的企业事实：{fact_id}")
        for matter in hypothesis.get("government_matters", []):
            if not isinstance(matter, dict) or not _text(matter.get("name")):
                errors.append(f"{hypothesis_id}: 政府管理事项必须有名称")
                continue
            disposition = _text(matter.get("disposition"))
            label = f"{hypothesis_id} / {matter.get('name')}"
            if disposition == "route":
                route_ids = matter.get("route_ids", [])
                if not route_ids:
                    errors.append(f"{label}: 必须对应至少一个主管部门路由")
                for route_id in route_ids:
                    if _text(route_id) not in routes:
                        errors.append(f"{label}: 引用了不存在的主管部门路由：{route_id}")
            elif disposition == "exclude":
                if not _text(matter.get("exclusion_reason")):
                    errors.append(f"{label}: 排除事项必须说明原因")
            else:
                errors.append(f"{label}: 必须路由或明确排除")

    candidates_by_search: dict[str, list[dict]] = {}
    for candidate_id, candidate in candidates.items():
        search_id = _text(candidate.get("search_id"))
        if search_id not in searches:
            errors.append(f"{candidate_id}: 未关联有效政策检索任务")
            continue
        candidates_by_search.setdefault(search_id, []).append(candidate)
        for field in ("title", "status", "eligibility_status", "disposition", "attachment_status"):
            if not _text(candidate.get(field)):
                errors.append(f"{candidate_id}: 缺少{field}")
        if _text(candidate.get("eligibility_status")) not in ELIGIBILITY_STATUSES:
            errors.append(f"{candidate_id}: eligibility_status 不合法")
        if _text(candidate.get("status")) in CURRENT_POLICY_STATUSES:
            if _text(candidate.get("attachment_status")) != "complete":
                errors.append(f"{candidate_id}: 相关政策附件未完成，必须标记 research_incomplete")
            source_ids = candidate.get("formal_policy_source_ids", [])
            if not source_ids:
                errors.append(f"{candidate_id}: 现行政策候选缺少正式政策来源")
            for source_id in source_ids:
                if _text(source_id) not in sources:
                    errors.append(f"{candidate_id}: 正式政策来源不存在：{source_id}")

    search_by_report_key: dict[tuple[str, str], dict] = {}
    all_route_ids_seen: set[str] = set()
    for search_id, search in searches.items():
        landing_id = _text(search.get("landing_business_id"))
        topic = _text(search.get("topic"))
        label = f"{search_id} / {landing_id or '未关联业务'} / {topic or '未命名主题'}"
        if landing_id not in landings:
            errors.append(f"{label}: 未关联有效落地业务")
        if not topic:
            errors.append(f"{label}: 缺少topic")
        key = (landing_id, topic)
        if key in search_by_report_key:
            errors.append(f"{label}: 与另一政策检索任务重复关联同一报告主题")
        else:
            search_by_report_key[key] = search
        for route_id in search.get("route_ids", []):
            route_id = _text(route_id)
            if route_id not in routes:
                errors.append(f"{label}: 引用了不存在的主管部门路由：{route_id}")
            else:
                all_route_ids_seen.add(route_id)
                if _text(routes[route_id].get("landing_business_id")) != landing_id:
                    errors.append(f"{label}: 路由不属于该拟落地业务：{route_id}")
        if not search.get("route_ids"):
            errors.append(f"{label}: 缺少业务—部门路由")
        for fact_id in search.get("fact_ids", []):
            if _text(fact_id) not in facts:
                errors.append(f"{label}: 引用了不存在的企业事实：{fact_id}")
        if not search.get("fact_ids"):
            errors.append(f"{label}: 缺少企业事实基础")
        status = _text(search.get("coverage_status"))
        if status not in SEARCH_STATUSES:
            errors.append(f"{label}: coverage_status 必须为 complete 或 research_incomplete")
        if status == "research_incomplete":
            errors.append(f"{label}: research_incomplete，禁止生成正式报告")

        expected_report = report_items.get(key)
        expected_departments = {_text(value) for value in (expected_report or {}).get("searched_departments", []) if _text(value)}
        department_searches = search.get("department_searches", [])
        department_names: set[str] = set()
        for department_search in department_searches:
            if not isinstance(department_search, dict):
                errors.append(f"{label}: 存在非对象的部门检索记录")
                continue
            department = _text(department_search.get("department"))
            department_label = f"{label} / {department or '未命名部门'}"
            if not department:
                errors.append(f"{department_label}: 缺少department")
                continue
            department_names.add(department)
            if _text(department_search.get("department_role")) not in DEPARTMENT_ROLES:
                errors.append(f"{department_label}: 缺少或错误的部门角色")
            if not _text(department_search.get("routing_basis")):
                errors.append(f"{department_label}: 缺少路由依据")
            runs = department_search.get("runs")
            profile_id = _text(department_search.get("profile_id"))
            if profile_id:
                profile = scan_profiles.get(profile_id)
                if not profile:
                    errors.append(f"{department_label}: 引用了不存在的部门检索回执档案：{profile_id}")
                    runs = []
                else:
                    if _text(profile.get("department")) != department:
                        errors.append(f"{department_label}: 回执档案所属部门不一致")
                    runs = profile.get("runs", [])
            run_by_path: dict[str, dict] = {}
            for run in runs or []:
                if not isinstance(run, dict):
                    errors.append(f"{department_label}: 存在非对象的检索回执")
                    continue
                path = _text(run.get("path"))
                if path in run_by_path:
                    errors.append(f"{department_label}: 检索路径重复：{path}")
                run_by_path[path] = run
            for path in DISCOVERY_PATHS:
                run = run_by_path.get(path)
                if not run:
                    errors.append(f"{department_label}: 缺少强制检索路径：{path}")
                    continue
                run_label = f"{department_label} / {path}"
                run_status = _text(run.get("status"))
                if run_status not in RUN_STATUSES:
                    errors.append(f"{run_label}: 状态必须为 complete、not_available、failed 或 partial")
                    continue
                if run_status == "complete":
                    if not _specific_url(run.get("entry_url")):
                        errors.append(f"{run_label}: 完成检索必须提供具体官方入口地址，不得以首页替代目录扫描")
                    if not _text(run.get("receipt_id")) or not _text(run.get("result_summary")):
                        errors.append(f"{run_label}: 完成检索必须记录回执和结果摘要")
                elif run_status == "not_available":
                    if not _text(run.get("not_available_basis")):
                        errors.append(f"{run_label}: not_available 必须说明官方路径不存在或不适用的依据")
                else:
                    errors.append(f"{run_label}: {run_status}，必须标记 research_incomplete，禁止生成正式报告")
        missing_departments = expected_departments - department_names
        for department in sorted(missing_departments):
            errors.append(f"{label}: 缺少报告所列主管部门的检索回执：{department}")

        candidate_ids = [_text(value) for value in search.get("candidate_policy_ids", []) if _text(value)]
        actual_candidate_ids = {_text(candidate.get("id")) for candidate in candidates_by_search.get(search_id, [])}
        if set(candidate_ids) != actual_candidate_ids:
            errors.append(f"{label}: candidate_policy_ids 与候选政策归属不一致")

        if expected_report:
            outcome = _text(expected_report.get("outcome"))
            linked_candidates = candidates_by_search.get(search_id, [])
            current_candidates = [item for item in linked_candidates if _text(item.get("status")) in CURRENT_POLICY_STATUSES]
            if outcome == "research_incomplete":
                errors.append(f"{label}: report-data 不得把 research_incomplete 写入正式报告")
            if outcome == "no_current_policy":
                if current_candidates:
                    errors.append(f"{label}: 已发现现行政策，资格未知时必须输出 conditional_opportunity，不得输出 no_current_policy")
                if status != "complete":
                    errors.append(f"{label}: 未完成完整动态检索，不得输出 no_current_policy")
            for candidate in current_candidates:
                eligibility = _text(candidate.get("eligibility_status"))
                source_ids = {_text(value) for value in candidate.get("formal_policy_source_ids", []) if _text(value)}
                report_policy_ids = {_text(value) for value in expected_report.get("policy_ids", []) if _text(value)}
                if eligibility == "unknown" and outcome != "conditional_opportunity":
                    errors.append(f"{label}: 现行政策资格条件尚未确认，必须输出 conditional_opportunity")
                if eligibility == "ineligible" and outcome != "not_applicable":
                    errors.append(f"{label}: 已确认企业不适用时必须输出 not_applicable")
                if eligibility == "not_triggered" and outcome != "not_triggered":
                    errors.append(f"{label}: 业务事实未触发时必须输出 not_triggered")
                if eligibility in {"unknown", "eligible"} and not source_ids.issubset(report_policy_ids):
                    errors.append(f"{label}: 正式报告未关联已发现现行政策的正式来源")

    for key in report_items:
        if key not in search_by_report_key:
            errors.append(f"{key[0]} / {key[1]}: 缺少动态政策检索覆盖记录")
    for route_id, route in routes.items():
        if _text(route.get("status")) in {"matched_static_rule", "verified_dynamic_route"} and route_id not in all_route_ids_seen:
            errors.append(f"{route_id}: 已确认主管部门路由未进入任何政策检索任务")
    for landing_id in landings:
        if not hypotheses_by_landing.get(landing_id):
            errors.append(f"{landing_id}: 缺少业务语义展开记录")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="validate business-triggered dynamic policy search coverage")
    parser.add_argument("policy_search_ledger")
    parser.add_argument("--research-ledger", required=True)
    parser.add_argument("--report-data", required=True)
    args = parser.parse_args()
    coverage = load_data(args.policy_search_ledger)
    research_ledger = load_data(args.research_ledger)
    report_data = load_data(args.report_data)
    canonical_fixture = (
        Path(args.policy_search_ledger).resolve() == (Path(__file__).resolve().parents[1] / "examples" / "flyco-policy-search-ledger.json").resolve()
        and Path(args.report_data).resolve() == (Path(__file__).resolve().parents[1] / "examples" / "flyco-report-data.json").resolve()
    )
    errors = validate_policy_search_coverage(
        coverage,
        research_ledger,
        report_data,
        allow_stale_fixture=canonical_fixture,
    )
    if errors:
        print("政策检索覆盖校验失败：")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("政策检索覆盖校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
