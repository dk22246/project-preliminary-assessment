#!/usr/bin/env python3
"""Compile two lean Agent inputs into the five formal audit ledgers."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import tempfile

from init_report_workspace import build_payloads
from findings_contract import resolve_catalog_match, validate_enterprise_findings, validate_findings_contracts
from search_industry_catalog import classify_catalog_entry


ENTERPRISE_INPUT = "enterprise-findings.json"
POLICY_INPUT = "policy-findings.json"
EQUITY_ASSERTION_TYPES = {"registry_fact", "legal_disclosure", "provider_calculation", "consolidation_scope"}


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


def _assign(
    rows: list[dict],
    prefix: str,
    *,
    key_name: str = "key",
    reserved_ids: set[str] | None = None,
) -> tuple[list[dict], dict[str, str]]:
    output: list[dict] = []
    mapping: dict[str, str] = {}
    used_ids = set(reserved_ids or ())
    for index, original in enumerate(rows, 1):
        row = deepcopy(original)
        key = str(row.pop(key_name, "") or row.get("id", "")).strip()
        if not key:
            raise ValueError(f"{prefix}第{index}条缺少稳定key")
        if key in mapping:
            raise ValueError(f"{prefix}稳定key重复：{key}")
        supplied_id = str(row.get("id", "")).strip()
        identifier = supplied_id or f"{prefix}{index:02d}"
        if not supplied_id:
            serial = 1
            while f"{prefix}{serial:02d}" in used_ids:
                serial += 1
            identifier = f"{prefix}{serial:02d}"
        if identifier in used_ids:
            raise ValueError(f"{prefix}统一ID重复：{identifier}")
        row["id"] = identifier
        mapping[key] = identifier
        output.append(row)
        used_ids.add(identifier)
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


def _source_rows(rows: list[dict], prefix: str, *, reserved_ids: set[str] | None = None) -> tuple[list[dict], dict[str, str]]:
    assigned, mapping = _assign(rows, prefix, reserved_ids=reserved_ids)
    return assigned, mapping


def _without_round_ids(rows: list[dict]) -> list[dict]:
    result = []
    for row in rows:
        item = deepcopy(row)
        item.pop("id", None)
        if not item.get("key") and item.get("stable_key"):
            item["key"] = item["stable_key"]
        item.pop("stable_key", None)
        result.append(item)
    return result


def migrate_legacy_equity(findings: dict) -> dict:
    """Explicitly bridge pre-canonical report.equity input during migration.

    New input must keep equity at the top level.  The bridge is deliberately
    strict: two populated locations must be identical, otherwise compilation
    stops instead of choosing one silently.
    """
    report = findings.get("report") if isinstance(findings.get("report"), dict) else {}
    legacy = report.get("equity")
    canonical = findings.get("equity")
    if not isinstance(legacy, dict) or not any(legacy.values()):
        return findings
    canonical_content = {
        key: value for key, value in (canonical.items() if isinstance(canonical, dict) else ())
        if key not in {"data_status", "review_status"} and value not in (None, "", [], {})
    }
    if isinstance(canonical, dict) and canonical.get("review_status") not in {None, "", "incomplete"}:
        canonical_content["review_status"] = canonical.get("review_status")
    if not isinstance(canonical, dict) or not canonical_content:
        migrated = deepcopy(findings)
        migrated["equity"] = deepcopy(legacy)
        _normalize_migrated_equity(migrated["equity"])
        migrated["report"] = deepcopy(report)
        migrated["report"].pop("equity", None)
        return migrated
    def semantic_graph(value: dict) -> tuple[dict[str, dict], dict[tuple[str, str, str], dict]]:
        nodes = {str(row.get("name", "")): row for row in value.get("nodes", []) if isinstance(row, dict) and row.get("name")}
        edges: dict[tuple[str, str, str], dict] = {}
        by_id = {str(row.get("id")): str(row.get("name")) for row in value.get("nodes", []) if isinstance(row, dict) and row.get("id")}
        for row in value.get("edges", []):
            if isinstance(row, dict):
                key = (by_id.get(str(row.get("from")), str(row.get("from"))), by_id.get(str(row.get("to")), str(row.get("to"))), str(row.get("relationship", "")))
                edges[key] = row
        return nodes, edges
    canonical_nodes, canonical_edges = semantic_graph(canonical)
    legacy_nodes, legacy_edges = semantic_graph(legacy)
    conflicts: list[str] = []
    if canonical.get("review_status") not in (None, "", "incomplete") and legacy.get("review_status") not in (None, "", "incomplete") and canonical.get("review_status") != legacy.get("review_status"):
        conflicts.append(f"复核状态不一致：{canonical.get('review_status')} != {legacy.get('review_status')}")
    for name in sorted(set(canonical_nodes) & set(legacy_nodes)):
        for field in ("entity_type", "assertion_type", "as_of_date", "shareholding_ratio"):
            left, right = canonical_nodes[name].get(field), legacy_nodes[name].get(field)
            if left not in (None, "") and right not in (None, "") and str(left) != str(right):
                conflicts.append(f"节点{ name }字段{ field }不一致：{left} != {right}")
    for edge in sorted(set(canonical_edges) & set(legacy_edges)):
        left, right = canonical_edges[edge], legacy_edges[edge]
        for field in ("shareholding_ratio", "as_of_date", "assertion_type"):
            if left.get(field) not in (None, "") and right.get(field) not in (None, "") and str(left.get(field)) != str(right.get(field)):
                conflicts.append(f"连接{edge}字段{field}不一致：{left.get(field)} != {right.get(field)}")
    if canonical_edges and legacy_edges and set(canonical_edges) != set(legacy_edges):
        conflicts.append("股权连接的主体、关系或持股口径存在冲突")
    if conflicts:
        raise ValueError("股权迁移冲突（按同名节点和实际共同字段核对）：\n" + "\n".join(conflicts))
    migrated = deepcopy(findings)
    canonical_out = deepcopy(canonical)
    canonical_by_name = {str(row.get("name")): row for row in canonical_out.get("nodes", []) if isinstance(row, dict) and row.get("name")}
    for name, legacy_row in legacy_nodes.items():
        target = canonical_by_name.get(name)
        if target is not None:
            for field, value in legacy_row.items():
                if field not in target and field not in {"id", "key"}:
                    target[field] = deepcopy(value)
    _normalize_migrated_equity(canonical_out)
    migrated["equity"] = canonical_out
    migrated["report"] = deepcopy(report)
    migrated["report"].pop("equity", None)
    return migrated


def _normalize_migrated_equity(equity: dict) -> None:
    """Convert legacy node/edge identifiers to the canonical key references."""
    nodes = [row for row in equity.get("nodes", []) if isinstance(row, dict)]
    node_keys: dict[str, str] = {}
    for index, row in enumerate(nodes, 1):
        key = str(row.get("key") or row.get("id") or row.get("name") or f"node-{index}").strip()
        row["key"] = key
        for alias in (row.get("id"), row.get("name"), key):
            if alias not in (None, ""):
                node_keys[str(alias)] = key
    for index, row in enumerate(equity.get("edges", []), 1):
        if not isinstance(row, dict):
            continue
        row["key"] = str(row.get("key") or row.get("id") or f"edge-{index}").strip()
        source = row.get("from_key", row.get("from"))
        target = row.get("to_key", row.get("to"))
        if str(source) in node_keys and str(target) in node_keys:
            row["from_key"] = node_keys[str(source)]
            row["to_key"] = node_keys[str(target)]
    equity.pop("edge_key_map", None)


def migrate_legacy_policy_findings(policy: dict, enterprise: dict) -> dict:
    """Cross-check old report/search policy views before creating new records."""
    report = policy.get("report") if isinstance(policy.get("report"), dict) else {}
    search = policy.get("search") if isinstance(policy.get("search"), dict) else {}
    old_policies = report.get("policies", [])
    old_candidates = search.get("policy_candidates", [])
    if not old_policies and not old_candidates:
        migrated = deepcopy(policy)
        migrated.pop("report", None)
        return migrated
    sources = {}
    for row in policy.get("sources", []):
        if isinstance(row, dict) and row.get("key"):
            sources[str(row.get("id", row.get("key")))] = str(row["key"])
            sources[str(row["key"])] = str(row["key"])
    researches = report.get("policy_research", [])
    search_rows = search.get("searches", [])
    search_aliases = {str(row.get("id", row.get("key"))): str(row.get("key", row.get("id"))) for row in search_rows if isinstance(row, dict)}
    fact_rows = (enterprise.get("research") or {}).get("facts", []) if isinstance(enterprise.get("research"), dict) else []
    fact_aliases = {str(row.get("id", row.get("key"))): str(row.get("key", row.get("id"))) for row in fact_rows if isinstance(row, dict)}
    landing_rows = ((enterprise.get("report") or {}).get("landing_businesses", [])) if isinstance(enterprise.get("report"), dict) else []
    landing_aliases = {str(row.get("id", row.get("key"))): str(row.get("key", row.get("id"))) for row in landing_rows if isinstance(row, dict)}
    errors: list[str] = []
    records: list[dict] = []
    for index, old in enumerate(old_policies, 1):
        source_id = str(old.get("source_id", ""))
        matched = next((row for row in researches if isinstance(row, dict) and source_id in [str(item) for item in row.get("policy_ids", [])]), None)
        if source_id not in sources or not matched:
            errors.append(f"旧政策{source_id or index}无法与来源及政策检索结论交叉核对")
            continue
        def resolve_refs(old_field: str, aliases: dict[str, str], label: str) -> list[str]:
            raw = old.get(old_field, old.get(old_field.replace("_keys", "_ids"), []))
            values = raw if isinstance(raw, list) else ([raw] if raw not in (None, "") else [])
            resolved = [aliases.get(str(item)) for item in values]
            if any(item is None for item in resolved):
                errors.append(f"旧政策{source_id or index}的{label}引用无法解析，待补：{values}")
            return [item for item in resolved if item]
        search_keys = resolve_refs("search_keys", search_aliases, "search")
        fact_keys = resolve_refs("fact_keys", fact_aliases, "fact")
        landing_keys = resolve_refs("landing_business_keys", landing_aliases, "landing_business")
        if not search_keys:
            matched_searches = matched.get("search_ids", matched.get("search_keys", [])) if isinstance(matched, dict) else []
            search_keys = [search_aliases[str(item)] for item in matched_searches if str(item) in search_aliases]
        records.append({
            "key": f"migrated-{index}",
            "source_keys": [sources[source_id]],
            "search_keys": search_keys, "fact_keys": fact_keys, "landing_business_keys": landing_keys,
            "topic": matched.get("topic", old.get("name", "")),
            "match_reason": old.get("report_reason", matched.get("conclusion", "")),
            "eligibility_status": "unknown",
            "disposition": "conditional",
            "conditions": old.get("conditions", ""),
            "handling_route": old.get("handling_route", ""),
            "report_group": old.get("report_group", source_id),
            "policy": deepcopy(old),
        })
    if errors:
        raise ValueError("旧政策输入迁移冲突：\n" + "\n".join(errors))
    migrated = deepcopy(policy)
    migrated["policy_records"] = records
    migrated.pop("report", None)
    migrated["search"].pop("policy_candidates", None)
    return migrated


def _derive_equity_views(equity: dict) -> tuple[dict, dict]:
    """Return report and evidence views from the one canonical equity record."""
    evidence = deepcopy(equity)
    evidence.pop("edge_key_map", None)
    for row in evidence.get("nodes", []):
        row.pop("key", None)
    for row in evidence.get("edges", []):
        row.pop("key", None)
    node_fields = ("id", "name", "entity_type", "as_of_date", "assertion_type", "evidence_source_ids", "role", "level", "shareholding_ratio", "calculation_basis")
    edge_fields = ("id", "from", "to", "relationship", "assertion_type", "as_of_date", "evidence_source_ids", "role", "level", "shareholding_ratio", "ownership_percent", "is_remainder", "calculation_basis")
    report = {
        key: deepcopy(equity[key])
        for key in (
            "data_status", "nodes", "edges", "conflict_disclosures", "availability_note",
            "search_source_ids", "evidence_summary",
        )
        if key in equity
    }
    report["nodes"] = [{key: row[key] for key in node_fields if key in row} for row in equity.get("nodes", [])]
    report["edges"] = [{key: row[key] for key in edge_fields if key in row} for row in equity.get("edges", [])]
    report["conflict_disclosures"] = deepcopy(equity.get("conflicts", []))
    return report, evidence


def _compile_equity_graph(equity_input: dict, maps: dict[str, dict[str, str]]) -> dict:
    """Compile canonical keyed equity graph into stable IDs and ID references."""
    result = deepcopy(equity_input)
    nodes_input = _rows(equity_input.get("nodes", []), "股权节点")
    nodes, node_map = _assign(nodes_input, "EN")
    for source, original in zip(nodes, nodes_input):
        if str(original.get("assertion_type", "")).strip() not in EQUITY_ASSERTION_TYPES:
            raise ValueError(f"股权节点断言类型无效：{original.get('assertion_type', '')}")
        source["key"] = str(original.get("key") or original.get("id") or "").strip()
        if not source["key"]:
            raise ValueError("股权节点缺少稳定key")
        source.update(_replace_refs({"source_keys": original.get("source_keys", [])}, maps))
        if "source_ids" in source:
            source["evidence_source_ids"] = source.pop("source_ids")
    edge_rows = _rows(equity_input.get("edges", []), "股权连接")
    edges, edge_map = _assign(edge_rows, "EE")
    for edge, original in zip(edges, edge_rows):
        if str(original.get("assertion_type", "")).strip() not in EQUITY_ASSERTION_TYPES:
            raise ValueError(f"股权连接断言类型无效：{original.get('assertion_type', '')}")
        edge["key"] = str(original.get("key") or original.get("id") or "").strip()
        if not edge["key"]:
            raise ValueError("股权连接缺少稳定key")
        from_key = str(original.get("from_key", "")).strip()
        to_key = str(original.get("to_key", "")).strip()
        if from_key not in node_map or to_key not in node_map:
            raise ValueError(f"股权连接引用未知节点key：{from_key or '空'}->{to_key or '空'}")
        edge.pop("from_key", None)
        edge.pop("to_key", None)
        edge["from"] = node_map[from_key]
        edge["to"] = node_map[to_key]
        edge.update(_replace_refs({"source_keys": original.get("source_keys", [])}, maps))
        if "source_ids" in edge:
            edge["evidence_source_ids"] = edge.pop("source_ids")
    result["nodes"] = nodes
    result["edges"] = edges
    result["edge_key_map"] = edge_map
    summary = result.get("evidence_summary")
    if isinstance(summary, dict) and "display_source_key" in summary:
        summary.update(_replace_refs({"display_source_key": summary.pop("display_source_key")}, maps))
    return result


def _compile_equity_evidence_summary(equity: dict, sources: list[dict]) -> None:
    """Fill the final display title from the canonical enterprise source row."""
    summary = equity.get("evidence_summary")
    if not isinstance(summary, dict) or not summary.get("display_source_id"):
        return
    source_by_id = {str(row.get("id", "")): row for row in sources}
    source_id = str(summary["display_source_id"])
    source = source_by_id.get(source_id)
    if source is None or not str(source.get("name", "")).strip():
        raise ValueError(f"股权evidence_summary引用来源无法生成展示标题：{source_id}")
    summary["display_source_title"] = str(source["name"]).strip()


def _enrich_catalog_assessment(assessment: object) -> object:
    """Copy exact catalog text from the bundled JSON by entry and detail index."""
    if not isinstance(assessment, dict):
        return assessment
    catalog_path = Path(__file__).resolve().parents[1] / "references" / "catalogs" / "complete-industry-catalog-library.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    entries = {str(item.get("id")): item for item in catalog.get("entries", [])}
    result = deepcopy(assessment)
    overall_names = {"明确符合": "direct_match", "存在相近可能": "potential_match_only", "暂未发现明确匹配": "no_match"}
    judgment_names = {"明确符合": "direct_match", "存在相近可能": "potential_match", "暂未发现明确匹配": "no_match"}
    result["overall_judgment"] = overall_names.get(result.get("overall_judgment"), result.get("overall_judgment"))
    for row in result.get("business_assessments", []):
        if not isinstance(row, dict):
            continue
        row["judgment"] = judgment_names.get(row.get("judgment"), row.get("judgment"))
        for matched in row.get("matched_items", []):
            if not isinstance(matched, dict):
                continue
            resolved = resolve_catalog_match(matched)
            matched.clear()
            matched.update(resolved)
            entry = entries[str(matched["catalog_entry_id"])]
            matched["catalog_classification"] = classify_catalog_entry(entry)["classification"]
    return result


def _display_amount(value: object, unit: str) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format(Decimal(str(value)), "f")
    text = str(value or "").strip()
    return text[:-len(unit)].strip() if unit and text.endswith(unit) else text


def _display_converted_amount(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded == 0:
        return "0"
    return format(rounded.normalize(), "f")


def _normalize_financials(report: dict) -> None:
    meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    unit = str(meta.get("financial_unit") or "").strip()
    raw_unit = str(meta.get("financial_raw_unit") or unit).strip()
    scales = {"元": Decimal(1), "万元": Decimal(10000), "亿元": Decimal(100000000)}
    converting = raw_unit != unit
    if converting and (raw_unit not in scales or unit not in scales):
        raise ValueError("财务单位转换只支持明确的元、万元、亿元；不得猜测原始单位")
    def amount(value):
        if value == "未公开披露":
            return value
        if not converting:
            return _display_amount(value, unit)
        try:
            if isinstance(value, bool):
                raise InvalidOperation
            number = Decimal(str(value))
            if not number.is_finite():
                raise InvalidOperation
            return _display_converted_amount(number * scales[raw_unit] / scales[unit])
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"单位转换要求原始纯数值，不能猜测金额：{value}") from error
    for row in report.get("financials", []):
        if not isinstance(row, dict):
            continue
        for alias, canonical in (("net_profit", "profit"), ("revenue_yoy", "revenue_change"), ("profit_yoy", "profit_change")):
            if alias in row:
                if canonical in row and row[canonical] != row[alias]:
                    raise ValueError(f"财务字段冲突：{canonical}与{alias}不同，需核实原始口径")
                row[canonical] = row.pop(alias)
        for field in ("revenue", "profit", "tax_value"):
            if field in row and unit:
                row[field] = amount(row[field])
        components = row.get("government_support_components")
        if not isinstance(components, list):
            continue
        try:
            total = sum((Decimal(str(item["amount"])) for item in components if isinstance(item, dict)), Decimal("0"))
        except (InvalidOperation, KeyError) as error:
            raise ValueError(f"政府补助组成金额无效：{error}") from error
        names = "、".join(str(item.get("name", "")).strip() for item in components if isinstance(item, dict) and str(item.get("name", "")).strip())
        row["government_support"] = f"合计{amount(total)}{unit}" + (f"（{names}）" if names else "")
        if converting:
            for component in components:
                if isinstance(component, dict):
                    component["amount"] = amount(component["amount"])
    # The rendered values now use the display unit; do not allow a second conversion.
    if "financial_raw_unit" in meta:
        meta["financial_raw_unit"] = unit


def _compile_risks(value: object) -> dict:
    """Normalize the findings risk list into the renderer's two-table contract."""
    if isinstance(value, dict):
        result = deepcopy(value)
        result.setdefault("regulatory", [])
        result.setdefault("litigation", [])
        return result
    result = {"regulatory": [], "litigation": []}
    if not isinstance(value, list):
        return result
    litigation_terms = ("诉讼", "案件", "执行", "失信", "裁判", "仲裁")
    for item in value:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("category") or item.get("risk_type") or "待核风险事项").strip()
        detail = str(item.get("description") or item.get("detail") or item.get("matter") or "需企业补充").strip()
        source_ids = item.get("source_ids", [])
        if not isinstance(source_ids, list):
            source_ids = [source_ids] if source_ids else []
        source = "、".join(str(source_id) for source_id in source_ids if str(source_id).strip()) or "—"
        date = str(item.get("date") or item.get("time") or item.get("occurred_at") or "—")
        impact = str(item.get("impact") or item.get("investment_impact") or item.get("level") or "需结合落地方案进一步核验")
        if any(term in title + detail for term in litigation_terms):
            result["litigation"].append([
                date,
                title,
                str(item.get("object_or_amount") or item.get("amount") or detail),
                str(item.get("status") or item.get("result") or "待核验"),
                impact,
                source,
            ])
        else:
            result["regulatory"].append([
                date,
                title,
                detail,
                str(item.get("result") or item.get("status") or "待核验"),
                str(item.get("rectified") or item.get("rectification") or "需企业补充"),
                impact,
                source,
            ])
    return result


def _compile_enterprise_findings(findings: dict, workspace: Path) -> tuple[dict[str, dict], dict[str, dict[str, str]]]:
    enterprise = str(findings.get("enterprise", "")).strip()
    if not enterprise:
        raise ValueError("enterprise-findings.json缺少enterprise")
    payloads = build_payloads(enterprise)
    source_rows = _rows(findings.get("sources", []), "企业来源")
    # Official catalog references are enterprise-stage sources but retain P IDs
    # because downstream policy sources must not collide with them.
    catalog_serial = 0
    for row in source_rows:
        if str(row.get("type", "")).strip() == "industry_catalog" and not str(row.get("id", "")).strip():
            catalog_serial += 1
            row["id"] = f"P{catalog_serial:02d}"
    sources, source_map = _source_rows(source_rows, "E")
    research_input = deepcopy(findings.get("research", {}))
    report_input = deepcopy(findings.get("report", {}))
    # Translate unambiguous input vocabulary once; do not manufacture missing facts.
    def rename(row, old, new):
        if old not in row:
            return
        if new in row and row[new] != row[old]:
            raise ValueError(f"输入字段冲突：{old}与{new}不同")
        row[new] = row.pop(old)
    overview = report_input.get("enterprise_overview", {})
    if isinstance(overview, dict):
        rename(overview, "employees", "employee_scale")
        rename(overview, "summary", "profile")
    for candidate in research_input.get("business_candidates", []):
        rename(candidate, "candidate", "name")
    for route in research_input.get("department_routes", []):
        rename(route, "role", "department_role")
        # Accept the former authoring alias but emit the single validator contract.
        # Keeping both spellings caused real workspaces to compile successfully and
        # then fail only at finalization because the static rule looked blank.
        rename(route, "routing_rule_id", "route_rule_id")
    equity_input = deepcopy(findings.get("equity", {}))
    if "equity" in report_input and any(report_input.get("equity", {}).values()):
        raise ValueError("旧版report.equity必须先通过显式migrate_legacy_equity迁移；编译器不自动兼容双结构")

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
    assessment = report_input.get("encouraged_industry_assessment")
    if isinstance(assessment, dict):
        for item in assessment.get("business_assessments", []):
            if isinstance(item, dict) and str(item.get("business_id", "")) in business_map:
                item["business_id"] = business_map[str(item["business_id"])]
    report_input["businesses"] = businesses
    report_input["landing_businesses"] = landings
    report = _merge(payloads["report-data.json"], _replace_refs(report_input, maps))
    report["risks"] = _compile_risks(report.get("risks"))
    _normalize_financials(report)
    report["encouraged_industry_assessment"] = _enrich_catalog_assessment(report.get("encouraged_industry_assessment"))
    report["sources"] = sources
    report["meta"]["reporting_entity"] = enterprise
    report["meta"]["report_title"] = f"{enterprise}招商落地前期评估报告"

    research = _merge(payloads["research-ledger.json"], _replace_refs(research_input, maps))
    research["enterprise"] = enterprise
    compiled_facts = _replace_refs(facts, maps)
    for fact in compiled_facts:
        source_ids = fact.pop("source_ids", [])
        if len(source_ids) != 1:
            raise ValueError("企业事实source_keys必须恰好一项，无法无歧义派生正式研究台账source_id")
        fact["source_id"] = source_ids[0]
    research["fact_ledger"] = compiled_facts
    research["business_candidates"] = _replace_refs(candidates, maps)
    for candidate in research["business_candidates"]:
        if candidate.get("disposition") in {"include", "merge"} and candidate.get("landing_business_id"):
            rename(candidate, "landing_business_id", "disposition_target")
    research["department_routes"] = _replace_refs(routes, maps)

    equity_input = _compile_equity_graph(equity_input, maps)
    _compile_equity_evidence_summary(equity_input, sources)
    equity = _merge(payloads["equity-evidence.json"], _replace_refs(equity_input, maps))
    equity["subject"]["legal_entity"] = str(report.get("entity_resolution", {}).get("legal_entity") or enterprise)
    equity_report, equity = _derive_equity_views(equity)
    report["equity"] = _merge(report.get("equity", {}), equity_report)
    return {
        "report-data.json": report,
        "research-ledger.json": research,
        "equity-evidence.json": equity,
    }, maps


def compile_enterprise_findings(findings: dict, workspace: Path) -> dict[str, dict]:
    contract_errors = validate_enterprise_findings(findings)
    if contract_errors:
        raise ValueError("企业输入契约错误：\n" + "\n".join(contract_errors))
    compiled, _ = _compile_enterprise_findings(findings, workspace)
    return compiled


def _derive_policy_candidates(records: list[dict], search_by_id: dict[str, dict]) -> list[dict]:
    candidates: list[dict] = []
    for record in records:
        search_ids = record.get("search_ids", [])
        search_id = search_ids[0] if search_ids else ""
        search = search_by_id.get(search_id, {})
        route_ids = [str(value) for value in search.get("route_ids", []) if str(value)] or [""]
        policy = record.get("policy", {}) if isinstance(record.get("policy"), dict) else {}
        eligibility = str(record.get("eligibility_status", "unknown"))
        disposition = str(record.get("disposition", "pending"))
        raw_status = str(policy.get("status") or disposition)
        if raw_status == "current":
            status = "current_conditional" if eligibility == "unknown" else "current_no_open_call"
        else:
            status = {
                "conditional": "current_conditional",
                "include": "current_no_open_call",
                "merge": "current_conditional",
                "excluded": "not_applicable",
                "expired": "expired_relevant",
                "pending": "insufficient_evidence",
            }.get(raw_status, raw_status)
        candidate_disposition = {
            "conditional": "include",
            "included": "include",
            "excluded": "exclude",
            "expired": "exclude",
            "pending": "exclude",
        }.get(disposition, disposition)
        for route_id in route_ids:
            candidates.append({
                "id": f"PC{len(candidates) + 1:02d}",
                "search_id": search_id,
                "route_id": route_id,
                "title": policy.get("name") or record.get("topic", ""),
                "policy_name": policy.get("name") or record.get("topic", ""),
                "status": status,
                "eligibility_status": eligibility,
                "disposition": candidate_disposition,
                "disposition_reason": record.get("match_reason", ""),
                "attachment_status": policy.get("attachment_status", "pending"),
                "formal_policy_source_ids": record.get("source_ids", []),
            })
    return candidates


def _derive_opportunity_radar(research: dict, report: dict, records: list[dict], maps: dict[str, dict[str, str]]) -> dict:
    records_by_fact: dict[str, list[dict]] = {}
    landing_refs_by_fact: dict[str, list[str]] = {}
    for candidate in research.get("business_candidates", []):
        if candidate.get("disposition") not in {"include", "merge"}:
            continue
        landing = candidate.get("disposition_target") or candidate.get("landing_business_id")
        if landing:
            for fact_id in candidate.get("fact_ids", []):
                landing_refs_by_fact.setdefault(str(fact_id), []).append(str(landing))
    for record in records:
        for fact_id in record.get("fact_ids", []):
            records_by_fact.setdefault(str(fact_id), []).append(record)
            landing_refs_by_fact.setdefault(str(fact_id), []).extend(record.get("landing_business_ids", []))
    signals: list[dict] = []
    overseas_topics = ("foreign_trade", "ef_account", "cross_border_settlement", "odi", "overseas_income_tax", "cross_border_fund_pool", "offshore_trade_stamp_duty")
    def topic_key(topic):
        text = str(topic)
        aliases = (
            ("overseas_income_tax", ("境外直接投资所得", "境外投资所得", "境外所得")),
            ("offshore_trade_stamp_duty", ("离岸转手买卖", "离岸贸易印花税")),
            ("cross_border_fund_pool", ("资金池",)),
            ("ef_account", ("ef账户", "多功能自由贸易账户")),
            ("cross_border_settlement", ("跨境人民币", "外汇结算", "跨境结算")),
            ("odi", ("odi", "境外投资备案", "境外投资外汇登记")),
            ("foreign_trade", ("跨境电商", "外贸")),
        )
        return next((key for key, terms in aliases if any(term in text.lower() for term in terms)), text)
    for signal_index, fact in enumerate(research.get("fact_ledger", []), 1):
        if not isinstance(fact, dict) or not fact.get("signal_type"):
            continue
        fact_id = str(fact.get("id", ""))
        linked = records_by_fact.get(fact_id, [])
        by_topic: dict[str, list[dict]] = {}
        for item in linked:
            by_topic.setdefault(topic_key(item.get("topic")), []).append(item)
        from report_core import is_overseas_business_signal
        fact_text = fact.get("fact") or "".join(str(fact.get(field, "")) for field in ("action", "object"))
        topics = tuple(dict.fromkeys((*overseas_topics, *by_topic))) if is_overseas_business_signal(fact.get("signal_type"), fact_text) else tuple(by_topic)
        opportunities: list[dict] = []
        for topic in topics:
            topic_records = by_topic.get(topic, [])
            if topic_records:
                dispositions = [{"include": "surfaced", "merge": "merged", "conditional": "surfaced", "excluded": "excluded", "expired": "expired", "pending": "pending_evidence"}.get(str(record.get("disposition")), "pending_evidence") for record in topic_records]
                disposition = next(value for value in ("surfaced", "merged", "pending_evidence", "excluded", "expired") if value in dispositions)
                opportunities.append({"topic": topic, "disposition": disposition,
                                      "reason": "；".join(dict.fromkeys(str(record.get("match_reason", "")) for record in topic_records)),
                                      "policy_source_ids": list(dict.fromkeys(source for record in topic_records for source in record.get("source_ids", [])))})
            else:
                opportunities.append({"topic": topic, "disposition": "pending_evidence", "reason": "本轮尚未形成该主题的政策判断，需继续检索和人工处置。", "policy_source_ids": []})
        refs = fact.get("business_ids") or fact.get("landing_business_ids") or list(dict.fromkeys(landing_refs_by_fact.get(fact_id, [])))
        if not refs:
            continue
        signals.append({
            "id": f"S{signal_index:02d}",
            "signal_type": fact.get("signal_type"),
            "fact": fact_text,
            "source_ids": [fact["source_id"]] if fact.get("source_id") else fact.get("source_ids", []),
            "source_kinds": fact.get("source_kinds", []),
            "basis_type": "enterprise_fact",
            "enterprise_fact_refs": refs,
            "opportunities": opportunities,
        })
    return {"signals": signals}


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
    reserved_source_ids = {str(row.get("id", "")) for row in report.get("sources", []) if str(row.get("id", ""))}
    policy_source_rows = _without_round_ids(_rows(findings.get("sources", []), "政策来源"))
    for source in policy_source_rows:
        if not source.get("name") and source.get("title"):
            source["name"] = source["title"]
    policy_sources, policy_source_map = _source_rows(policy_source_rows, "P", reserved_ids=reserved_source_ids)
    report["sources"] = list(report.get("sources", [])) + policy_sources
    report["meta"]["policy_researched_at"] = researched_at
    report["meta"]["policy_search_mode"] = "realtime"

    search_input = deepcopy(findings.get("search", {}))
    hypotheses, hypothesis_map = _assign(_rows(search_input.pop("landing_business_hypotheses", []), "落地业务假设"), "H")
    profiles, profile_map = _assign(_without_round_ids(_rows(search_input.pop("department_scan_profiles", []), "部门扫描档案")), "DSP")
    draft_rows = _rows(search_input.pop("discovered_candidates", []), "发现候选草稿")
    for row in draft_rows:
        if not row.get("key"):
            row["key"] = row.get("stable_key") or row.get("id", "")
    drafts, draft_map = _assign(_without_round_ids(draft_rows), "DC")
    raw_search_rows = _rows(search_input.pop("searches", []), "政策搜索")
    for row in raw_search_rows:
        if row.get("discovered_candidate_ids") and not row.get("discovered_candidate_keys"):
            row["discovered_candidate_keys"] = [
                next((key for key, identifier in draft_map.items() if identifier == str(candidate_id)), str(candidate_id))
                for candidate_id in row.get("discovered_candidate_ids", [])
            ]
    searches, search_map = _assign(_without_round_ids(raw_search_rows), "PS")
    evidence, evidence_map = _assign(_without_round_ids(_rows(findings.get("evidence", []), "政策证据")), "PE")
    policy_records, policy_record_map = _assign(_rows(findings.get("policy_records", []), "政策主记录"), "POL")

    enterprise_maps = enterprise_maps or {}
    landing_map = enterprise_maps.get("landing_business") or {str(row.get("id")): str(row.get("id")) for row in report.get("landing_businesses", [])}
    fact_map = enterprise_maps.get("fact") or {str(row.get("id")): str(row.get("id")) for row in research.get("fact_ledger", [])}
    route_map = enterprise_maps.get("route") or {str(row.get("id")): str(row.get("id")) for row in research.get("department_routes", [])}
    enterprise_source_map = (enterprise_maps or {}).get("source", {})
    source_map = {**enterprise_source_map, **policy_source_map}
    maps = {
        "source": source_map, "formal_policy_source": source_map, "policy_source": source_map,
        "landing_business": landing_map, "fact": fact_map, "route": route_map, "profile": profile_map,
        "search": search_map, "result_source": source_map, "draft_candidate": draft_map, "policy_record": policy_record_map, "evidence": evidence_map, "evidence_record": evidence_map,
        "all": {**source_map, **landing_map, **fact_map, **route_map, **profile_map, **search_map, **draft_map, **policy_record_map, **evidence_map},
    }
    compiled_searches = _replace_refs(searches, maps)
    search_by_id = {str(row.get("id")): row for row in compiled_searches}
    record_rows = _replace_refs(policy_records, maps)
    visible_records: list[dict] = []
    policy_research: list[dict] = []
    for record in record_rows:
        if record.get("review_status") == "changed_source_pending_review" and record.get("disposition") in {"include", "merge", "conditional"}:
            record["disposition"] = "pending"
            record["match_reason"] = str(record.get("match_reason", "")).rstrip() + "；来源已变化，待重新复核"
        policy = deepcopy(record.get("policy", {}))
        source_ids = list(record.get("source_ids", []))
        landing_ids = list(record.get("landing_business_ids", []))
        search_ids = list(record.get("search_ids", []))
        record_id = str(record.get("id"))
        if record.get("disposition") in {"include", "merge", "conditional"}:
            policy.setdefault("source_id", source_ids[0] if source_ids else "")
            policy.setdefault("name", policy.get("title") or record.get("topic", ""))
            policy.setdefault("report_title", policy.get("name", ""))
            policy.setdefault("report_reason", record.get("match_reason", ""))
            policy.setdefault("conditions", record.get("conditions", ""))
            policy.setdefault("handling_route", record.get("handling_route", ""))
            policy.setdefault("enterprise_business", record.get("topic", ""))
            policy.setdefault("landing_action", record.get("handling_route", ""))
            source_rows_by_id = {str(row.get("id")): row for row in report.get("sources", [])}
            for source_id in source_ids or [""]:
                policy_copy = deepcopy(policy)
                policy_copy["source_id"] = source_id
                source_row = source_rows_by_id.get(str(source_id), {})
                for field, source_field in (("source_url", "location"), ("issuer", "issuer"), ("document_number", "document_number"), ("published_at", "date")):
                    if source_row.get(source_field):
                        policy_copy[field] = source_row[source_field]
                policy_copy["report_group"] = record.get("report_group", policy_copy.get("report_group", ""))
                visible_records.append(policy_copy)
        search_departments: list[str] = []
        for search_id in search_ids:
            search = search_by_id.get(search_id, {})
            for item in search.get("department_searches", []):
                if isinstance(item, dict) and item.get("department"):
                    search_departments.append(str(item["department"]))
        outcome = {"include": "direct_match", "merge": "conditional_opportunity", "conditional": "conditional_opportunity", "excluded": "not_applicable", "expired": "no_current_policy", "pending": "conditional_opportunity"}.get(str(record.get("disposition")), "conditional_opportunity")
        # A policy may be worth including while enterprise eligibility is still
        # unverified.  Such a record must remain a conditional opportunity in the
        # report instead of being promoted to a direct match merely because its
        # editorial disposition is ``include``.
        if outcome == "direct_match" and str(record.get("eligibility_status", "unknown")) != "eligible":
            outcome = "conditional_opportunity"
        for landing_id in landing_ids or [""]:
            policy_research.append({
            "landing_business_id": landing_id,
            "topic": record.get("topic", ""),
            "searched_departments": sorted(set(search_departments)),
            "outcome": outcome,
            "conclusion": record.get("match_reason", ""),
            "evidence_source_ids": source_ids,
            "policy_ids": source_ids if record.get("disposition") in {"include", "merge", "conditional"} else [],
            "next_evidence": record.get("conditions", "") or record.get("handling_route", "") or "继续核验正式条件",
            })
    report["policies"] = visible_records
    report["policy_research"] = policy_research
    report["policy_opportunity_radar"] = _derive_opportunity_radar(research, report, record_rows, maps)
    compiled_candidates = _derive_policy_candidates(record_rows, search_by_id)
    candidate_ids_by_search: dict[str, list[str]] = {}
    for candidate in compiled_candidates:
        candidate_ids_by_search.setdefault(str(candidate.get("search_id", "")), []).append(str(candidate["id"]))
    for search in compiled_searches:
        search["candidate_policy_ids"] = candidate_ids_by_search.get(str(search.get("id", "")), [])
    research["policy_candidates"] = deepcopy(compiled_candidates)
    search_ledger = {
        "version": "1.0", "enterprise": enterprise, "researched_at": researched_at, "search_mode": "realtime",
        "landing_business_hypotheses": _replace_refs(hypotheses, maps),
        "department_scan_profiles": _replace_refs(profiles, maps),
        "searches": compiled_searches,
        "discovered_candidates": _replace_refs(drafts, maps),
        **_replace_refs(search_input, maps),
        "policy_candidates": compiled_candidates,
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
    contract_errors = validate_findings_contracts(enterprise_findings, policy_findings)
    if contract_errors:
        raise ValueError("输入契约错误（未覆盖旧五台账）：\n" + "\n".join(contract_errors))
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
