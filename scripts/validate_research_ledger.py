#!/usr/bin/env python3
"""Enforce traceable business discovery and policy routing before report rendering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from report_core import load_data


ROOT = Path(__file__).resolve().parents[1]
ROUTING = json.loads((ROOT / "references" / "department-routing.json").read_text(encoding="utf-8"))
DISPOSITIONS = {"include", "merge", "exclude"}
ROUTE_STATUSES = {"matched_static_rule", "verified_dynamic_route", "rejected_route", "unresolved"}
CURRENT_POLICY_STATUSES = {"current_open", "current_no_open_call", "current_conditional"}
POLICY_STATUSES = CURRENT_POLICY_STATUSES | {"expired_relevant", "renewal_pending", "not_applicable", "insufficient_evidence", "no_current_policy"}


def _index(rows: list[dict], label: str, errors: list[str]) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        identifier = str(row.get("id", "")).strip()
        if not identifier:
            errors.append(f"{label}: 缺少id")
        elif identifier in indexed:
            errors.append(f"{label}: id重复：{identifier}")
        else:
            indexed[identifier] = row
    return indexed


def validate_research_ledger(ledger: dict, report_data: dict) -> list[str]:
    errors: list[str] = []
    for field in ("enterprise", "fact_ledger", "business_candidates", "department_routes"):
        if not ledger.get(field):
            errors.append(f"研究底稿缺少{field}")
    if errors:
        return errors
    facts = _index(ledger["fact_ledger"], "企业事实", errors)
    candidates = _index(ledger["business_candidates"], "业务候选", errors)
    routes = _index(ledger["department_routes"], "主管部门路由", errors)
    policies = _index(ledger.get("policy_candidates", []), "候选政策", errors)
    landing_by_id = {str(item.get("id", "")).strip(): item for item in report_data.get("landing_businesses", [])}
    research_by_landing: dict[str, list[dict]] = {}
    for item in report_data.get("policy_research", []):
        research_by_landing.setdefault(str(item.get("landing_business_id", "")).strip(), []).append(item)

    for fact_id, fact in facts.items():
        for field in ("source_id", "action", "object", "enterprise_role", "confidence"):
            if not str(fact.get(field, "")).strip():
                errors.append(f"{fact_id}: 缺少{field}")
        if str(fact.get("confidence", "")).strip() not in {"high", "medium", "low"}:
            errors.append(f"{fact_id}: confidence只能为 high、medium 或 low")

    candidate_targets: dict[str, list[str]] = {}
    for candidate_id, candidate in candidates.items():
        fact_ids = candidate.get("fact_ids", [])
        if not str(candidate.get("name", "")).strip():
            errors.append(f"{candidate_id}: 缺少候选名称")
        if not fact_ids:
            errors.append(f"{candidate_id}: 缺少事实依据")
        for fact_id in fact_ids:
            if fact_id not in facts:
                errors.append(f"{candidate_id}: 引用了不存在的企业事实：{fact_id}")
        disposition = str(candidate.get("disposition", "")).strip()
        if disposition not in DISPOSITIONS:
            errors.append(f"{candidate_id}: 候选处置只能为 include、merge 或 exclude")
            continue
        target = str(candidate.get("disposition_target", "")).strip()
        reason = str(candidate.get("disposition_reason", "")).strip()
        if disposition in {"include", "merge"}:
            if target not in landing_by_id:
                errors.append(f"{candidate_id}: 纳入或合并目标不是有效落地业务：{target}")
            else:
                candidate_targets.setdefault(target, []).append(candidate_id)
        if not reason:
            errors.append(f"{candidate_id}: 候选处置必须说明原因")

    for landing_id, landing in landing_by_id.items():
        if landing_id not in candidate_targets:
            errors.append(f"{landing_id}: 缺少已处置业务候选的承接关系")
        if landing_id not in research_by_landing:
            errors.append(f"{landing_id}: 缺少政策检索结论")

    routes_by_landing: dict[str, list[dict]] = {}
    for route_id, route in routes.items():
        landing_id = str(route.get("landing_business_id", "")).strip()
        routes_by_landing.setdefault(landing_id, []).append(route)
        if landing_id not in landing_by_id:
            errors.append(f"{route_id}: 未关联有效落地业务")
        linked_candidates = route.get("candidate_ids", [])
        if not linked_candidates:
            errors.append(f"{route_id}: 缺少业务候选关联")
        for candidate_id in linked_candidates:
            candidate = candidates.get(candidate_id)
            if not candidate:
                errors.append(f"{route_id}: 关联候选不存在：{candidate_id}")
            elif str(candidate.get("disposition_target", "")).strip() != landing_id:
                errors.append(f"{route_id}: 候选与落地业务承接关系不一致：{candidate_id}")
        status = str(route.get("status", "")).strip()
        if status not in ROUTE_STATUSES:
            errors.append(f"{route_id}: 路由状态不合法")
            continue
        department = str(route.get("department", "")).strip()
        if status == "matched_static_rule":
            rule_id = str(route.get("route_rule_id", "")).strip()
            rule = ROUTING.get(rule_id)
            if not rule:
                errors.append(f"{route_id}: 未匹配有效静态路由规则：{rule_id}")
            elif department not in rule["departments"]:
                errors.append(f"{route_id}: 主管部门不属于静态路由规则：{department}")
        elif status == "verified_dynamic_route" and not str(route.get("department_duty_source", "")).strip():
            errors.append(f"{route_id}: 动态路由缺少部门职责依据")
        elif status == "unresolved":
            if not str(route.get("reason", "")).strip() or not str(route.get("next_action", "")).strip():
                errors.append(f"{route_id}: 未解决路由必须说明原因和下一步")
        if status in {"matched_static_rule", "verified_dynamic_route"}:
            searched = {department_name for item in research_by_landing.get(landing_id, []) for department_name in item.get("searched_departments", [])}
            if department not in searched:
                errors.append(f"{route_id}: 主管部门未进入对应落地业务的政策检索记录：{department}")

    for landing_id in landing_by_id:
        if not routes_by_landing.get(landing_id):
            errors.append(f"{landing_id}: 缺少主管部门路由")

    formal_source_ids = {str(policy.get("source_id", "")).strip() for policy in report_data.get("policies", []) if str(policy.get("source_id", "")).strip()}
    supported_formal_sources: set[str] = set()
    policy_by_route: dict[str, list[dict]] = {}
    for policy_id, policy in policies.items():
        route_id = str(policy.get("route_id", "")).strip()
        policy_by_route.setdefault(route_id, []).append(policy)
        if route_id not in routes:
            errors.append(f"{policy_id}: 未关联有效主管部门路由")
        status = str(policy.get("status", "")).strip()
        if status not in POLICY_STATUSES:
            errors.append(f"{policy_id}: 候选政策状态不合法")
        disposition = str(policy.get("disposition", "")).strip()
        if disposition not in DISPOSITIONS:
            errors.append(f"{policy_id}: 候选政策处置只能为 include、merge 或 exclude")
        source_ids = {str(item).strip() for item in policy.get("formal_policy_source_ids", []) if str(item).strip()}
        if disposition == "include":
            if status not in CURRENT_POLICY_STATUSES:
                errors.append(f"{policy_id}: 非现行候选政策不得支撑正式报告政策")
            if not source_ids:
                errors.append(f"{policy_id}: 纳入正式报告的候选政策缺少正式政策来源")
            supported_formal_sources.update(source_ids)
        if disposition == "exclude" and not str(policy.get("disposition_reason", "")).strip():
            errors.append(f"{policy_id}: 排除候选政策必须说明原因")
    for route_id, route in routes.items():
        if str(route.get("status", "")).strip() in {"matched_static_rule", "verified_dynamic_route"} and not policy_by_route.get(route_id):
            errors.append(f"{route_id}: 缺少候选政策或无政策检索记录")
    for source_id in formal_source_ids - supported_formal_sources:
        errors.append(f"{source_id}: 正式报告政策无法回溯至现行且已纳入的候选政策")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate business discovery and department routing research ledger")
    parser.add_argument("research_ledger")
    parser.add_argument("--report-data", required=True)
    args = parser.parse_args()
    errors = validate_research_ledger(load_data(args.research_ledger), load_data(args.report_data))
    if errors:
        print("\n".join(errors))
        return 1
    print("通过：企业事实、业务候选、主管部门路由及候选政策均可追溯")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
