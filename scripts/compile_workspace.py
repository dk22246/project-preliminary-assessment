#!/usr/bin/env python3
"""Compile two lean Agent inputs into the five formal audit ledgers."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile

from init_report_workspace import build_payloads


ENTERPRISE_INPUT = "enterprise-findings.json"
POLICY_INPUT = "policy-findings.json"


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取{path.name}：{error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}必须是JSON对象")
    return value


def _rows(value: object, label: str) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label}必须是对象数组")
    return deepcopy(value)


def _assign(rows: list[dict], prefix: str, *, key_name: str = "key") -> tuple[list[dict], dict[str, str]]:
    output: list[dict] = []
    mapping: dict[str, str] = {}
    for index, original in enumerate(rows, 1):
        row = deepcopy(original)
        key = str(row.pop(key_name, "") or row.get("id", "")).strip()
        if not key:
            raise ValueError(f"{prefix}第{index}条缺少稳定key")
        if key in mapping:
            raise ValueError(f"{prefix}稳定key重复：{key}")
        identifier = str(row.get("id", "")).strip() or f"{prefix}{index:02d}"
        row["id"] = identifier
        mapping[key] = identifier
        output.append(row)
    return output, mapping


def _replace_refs(value: object, maps: dict[str, dict[str, str]]) -> object:
    if isinstance(value, list):
        return [_replace_refs(item, maps) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict = {}
    for field, item in value.items():
        if field.endswith("_keys"):
            target = field[:-5] + "_ids"
            category = field[:-5]
            mapping = maps.get(category) or maps.get(target) or maps.get("all", {})
            values = item if isinstance(item, list) else [item]
            missing = [str(key) for key in values if str(key) not in mapping]
            if missing:
                raise ValueError(f"{field}存在未知key：{'、'.join(missing)}")
            result[target] = [mapping[str(key)] for key in values]
        elif field.endswith("_key"):
            target = field[:-4] + "_id"
            category = field[:-4]
            mapping = maps.get(category) or maps.get(target) or maps.get("all", {})
            key = str(item)
            if key not in mapping:
                raise ValueError(f"{field}存在未知key：{key}")
            result[target] = mapping[key]
        else:
            result[field] = _replace_refs(item, maps)
    return result


def _merge(target: dict, overlay: dict) -> dict:
    result = deepcopy(target)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _source_rows(rows: list[dict], prefix: str) -> tuple[list[dict], dict[str, str]]:
    assigned, mapping = _assign(rows, prefix)
    return assigned, mapping


def _compile_enterprise_findings(findings: dict, workspace: Path) -> tuple[dict[str, dict], dict[str, dict[str, str]]]:
    enterprise = str(findings.get("enterprise", "")).strip()
    if not enterprise:
        raise ValueError("enterprise-findings.json缺少enterprise")
    payloads = build_payloads(enterprise)
    sources, source_map = _source_rows(_rows(findings.get("sources", []), "企业来源"), "E")
    research_input = deepcopy(findings.get("research", {}))
    report_input = deepcopy(findings.get("report", {}))
    equity_input = deepcopy(findings.get("equity", {}))

    facts, fact_map = _assign(_rows(research_input.pop("facts", []), "企业事实"), "F")
    candidates, candidate_map = _assign(_rows(research_input.pop("business_candidates", []), "业务候选"), "BC")
    businesses, business_map = _assign(_rows(report_input.pop("businesses", []), "业务"), "B")
    landings, landing_map = _assign(_rows(report_input.pop("landing_businesses", []), "落地业务"), "L")
    routes, route_map = _assign(_rows(research_input.pop("department_routes", []), "部门路由"), "DR")
    maps = {
        "source": source_map, "evidence_source": source_map, "basis_source": source_map,
        "relationship_source": source_map, "fact": fact_map, "business": business_map,
        "landing_business": landing_map, "candidate": candidate_map, "route": route_map,
        "all": {**source_map, **fact_map, **business_map, **landing_map, **candidate_map, **route_map},
    }
    report_input["businesses"] = businesses
    report_input["landing_businesses"] = landings
    report = _merge(payloads["report-data.json"], _replace_refs(report_input, maps))
    report["sources"] = sources
    report["meta"]["reporting_entity"] = enterprise
    report["meta"]["report_title"] = f"{enterprise}招商落地前期评估报告"

    research = _merge(payloads["research-ledger.json"], _replace_refs(research_input, maps))
    research["enterprise"] = enterprise
    research["fact_ledger"] = _replace_refs(facts, maps)
    research["business_candidates"] = _replace_refs(candidates, maps)
    research["department_routes"] = _replace_refs(routes, maps)

    equity = _merge(payloads["equity-evidence.json"], _replace_refs(equity_input, maps))
    equity["subject"]["legal_entity"] = str(report.get("entity_resolution", {}).get("legal_entity") or enterprise)
    return {
        "report-data.json": report,
        "research-ledger.json": research,
        "equity-evidence.json": equity,
    }, maps


def compile_enterprise_findings(findings: dict, workspace: Path) -> dict[str, dict]:
    compiled, _ = _compile_enterprise_findings(findings, workspace)
    return compiled


def compile_policy_findings(
    findings: dict,
    workspace: Path,
    report: dict,
    research: dict,
    enterprise_maps: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict]:
    enterprise = str(findings.get("enterprise", "")).strip()
    if enterprise != str(report.get("meta", {}).get("reporting_entity", "")).strip():
        raise ValueError("policy-findings.json企业主体与企业研究输入不一致")
    researched_at = str(findings.get("researched_at", "")).strip()
    if not researched_at:
        raise ValueError("policy-findings.json缺少researched_at")
    policy_sources, policy_source_map = _source_rows(_rows(findings.get("sources", []), "政策来源"), "P")
    report["sources"] = [row for row in report.get("sources", []) if not str(row.get("id", "")).startswith("P")] + policy_sources
    report["meta"]["policy_researched_at"] = researched_at
    report["meta"]["policy_search_mode"] = "realtime"

    search_input = deepcopy(findings.get("search", {}))
    hypotheses, hypothesis_map = _assign(_rows(search_input.pop("landing_business_hypotheses", []), "落地业务假设"), "H")
    profiles, profile_map = _assign(_rows(search_input.pop("department_scan_profiles", []), "部门扫描档案"), "DSP")
    searches, search_map = _assign(_rows(search_input.pop("searches", []), "政策搜索"), "PS")
    candidates, policy_candidate_map = _assign(_rows(search_input.pop("policy_candidates", []), "政策候选"), "PC")
    evidence, evidence_map = _assign(_rows(findings.get("evidence", []), "政策证据"), "PE")

    enterprise_maps = enterprise_maps or {}
    landing_map = enterprise_maps.get("landing_business") or {str(row.get("id")): str(row.get("id")) for row in report.get("landing_businesses", [])}
    fact_map = enterprise_maps.get("fact") or {str(row.get("id")): str(row.get("id")) for row in research.get("fact_ledger", [])}
    route_map = enterprise_maps.get("route") or {str(row.get("id")): str(row.get("id")) for row in research.get("department_routes", [])}
    maps = {
        "source": policy_source_map, "formal_policy_source": policy_source_map, "policy_source": policy_source_map,
        "landing_business": landing_map, "fact": fact_map, "route": route_map, "profile": profile_map,
        "search": search_map, "candidate_policy": policy_candidate_map, "evidence_record": evidence_map,
        "all": {**policy_source_map, **landing_map, **fact_map, **route_map, **profile_map, **search_map, **policy_candidate_map, **evidence_map},
    }
    policy_report = _replace_refs(deepcopy(findings.get("report", {})), maps)
    report = _merge(report, policy_report)
    search_ledger = {
        "version": "1.0", "enterprise": enterprise, "researched_at": researched_at, "search_mode": "realtime",
        "landing_business_hypotheses": _replace_refs(hypotheses, maps),
        "department_scan_profiles": _replace_refs(profiles, maps),
        "searches": _replace_refs(searches, maps),
        "policy_candidates": _replace_refs(candidates, maps),
        **_replace_refs(search_input, maps),
    }
    evidence_ledger = {
        "version": "1.0", "enterprise": enterprise, "researched_at": researched_at, "mode": "formal",
        "records": _replace_refs(evidence, maps),
    }
    return {
        "report-data.json": report,
        "policy-search-ledger.json": search_ledger,
        "policy-evidence.json": evidence_ledger,
    }


def compile_workspace(workspace: Path) -> dict[str, dict]:
    workspace = Path(workspace).resolve()
    enterprise_findings = _load(workspace / ENTERPRISE_INPUT)
    policy_findings = _load(workspace / POLICY_INPUT)
    compiled, enterprise_maps = _compile_enterprise_findings(enterprise_findings, workspace)
    compiled.update(compile_policy_findings(
        policy_findings, workspace, compiled["report-data.json"], compiled["research-ledger.json"], enterprise_maps
    ))
    with tempfile.TemporaryDirectory(dir=workspace) as temporary:
        temp_root = Path(temporary)
        for name, payload in compiled.items():
            (temp_root / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for name in compiled:
            (temp_root / name).replace(workspace / name)
    return compiled
