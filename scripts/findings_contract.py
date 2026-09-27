"""Small, portable contract checker for the two editable findings inputs.

This intentionally implements only the repository's used structural rules; it
is not presented as a general JSON-Schema implementation.
"""
from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path


POLICY_DISPOSITIONS = {"include", "merge", "conditional", "excluded", "expired", "pending"}
POLICY_ELIGIBILITY = {"unknown", "eligible", "ineligible", "not_triggered"}
ASSERTION_TYPES = {"registry_fact", "legal_disclosure", "provider_calculation", "consolidation_scope"}
SUPPORTED_SCHEMA_KEYS = {"type", "required", "properties", "items", "additionalProperties", "enum", "const", "minLength", "minItems", "uniqueItems", "minimum", "maxProperties", "title", "$schema"}
SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas"
CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "catalogs" / "complete-industry-catalog-library.json"


def _text(value: object) -> str:
    return str(value or "").strip()


def _rows(value: object, label: str, errors: list[str]) -> list[dict]:
    if not isinstance(value, list):
        errors.append(f"{label}必须是对象数组")
        return []
    rows: list[dict] = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict):
            errors.append(f"{label}第{index}项必须是对象")
        else:
            rows.append(row)
    return rows


def _refs(value: object, label: str, errors: list[str]) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{label}必须是数组")
        return []
    return value


def _unique_keys(rows: Iterable[dict], label: str, errors: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for index, row in enumerate(rows, 1):
        key = _text(row.get("key"))
        if not key:
            errors.append(f"{label}第{index}项缺少稳定key")
        elif key in result:
            errors.append(f"{label}稳定key重复：{key}")
        else:
            result[key] = row
    return result


def _schema_validate(value: object, schema: dict, path: str, errors: list[str]) -> None:
    unknown = set(schema) - SUPPORTED_SCHEMA_KEYS
    if unknown:
        errors.append(f"{path}: schema含未支持关键字：{', '.join(sorted(unknown))}")
        return
    expected = schema.get("type")
    types = expected if isinstance(expected, list) else [expected] if expected else []
    type_ok = True
    if types:
        type_ok = any({
            "object": isinstance(value, dict), "array": isinstance(value, list), "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool), "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool), "null": value is None,
        }.get(kind, False) for kind in types)
        if not type_ok:
            errors.append(f"{path}: 类型错误，期望{types}")
            return
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 不等于const值")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 不在enum允许值内")
    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: 长度小于minLength")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: 数量小于minItems")
        if schema.get("uniqueItems") and len({json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value}) != len(value):
            errors.append(f"{path}: uniqueItems不满足")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _schema_validate(item, item_schema, f"{path}[{index}]", errors)
    if isinstance(value, (int, float)) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: 小于minimum")
    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list):
            errors.append(f"{path}: schema.required必须是数组")
            required = []
        for required in required:
            if required not in value:
                errors.append(f"{path}: 缺少required字段{required}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            errors.append(f"{path}: schema.properties必须是对象")
            properties = {}
        for key, child in properties.items():
            if key in value and isinstance(child, dict):
                _schema_validate(value[key], child, f"{path}.{key}", errors)
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: 未允许字段{key}")
        if isinstance(schema.get("maxProperties"), int) and len(value) > schema["maxProperties"]:
            errors.append(f"{path}: 超过maxProperties")


def _load_schema(name: str, errors: list[str]) -> dict:
    path = SCHEMA_ROOT / name
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"无法读取契约schema {name}：{error}")
        return {}


def _schema_errors(value: object, name: str) -> list[str]:
    errors: list[str] = []
    schema = _load_schema(name, errors)
    if schema:
        _schema_validate(value, schema, "$", errors)
    return errors


@lru_cache(maxsize=1)
def _catalog_index(path: str, mtime_ns: int, size: int) -> dict:
    catalog = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return {str(item.get("id")): item for item in catalog.get("entries", []) if isinstance(item, dict)}


def resolve_catalog_match(match: object) -> dict:
    """Resolve one editable catalog reference using the compiler's rules.

    This is intentionally import-safe: the contract checker owns catalog input
    parsing, while the compiler only adds its presentation classification.
    """
    if not isinstance(match, dict):
        raise ValueError("必须是对象")
    entry_id = _text(match.get("catalog_entry_id"))
    if not entry_id:
        raise ValueError("缺少catalog_entry_id")
    try:
        stat = CATALOG_PATH.stat()
        entries = _catalog_index(str(CATALOG_PATH), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取目录库：{error}") from error
    entry = entries.get(entry_id)
    if not entry:
        raise ValueError(f"catalog_entry_id不存在：{entry_id}")
    details = entry.get("detail_entries", [])
    if not isinstance(details, list):
        raise ValueError(f"{entry_id}的detail_entries必须是数组")
    resolved = deepcopy(match)
    if details:
        if "detail_index" not in match:
            if len(details) > 1:
                raise ValueError(f"{entry_id}存在多个detail_entries，必须明确detail_index")
            detail_index = 0
        else:
            detail_index = match.get("detail_index")
        if not isinstance(detail_index, int) or isinstance(detail_index, bool) or detail_index < 0 or detail_index >= len(details):
            raise ValueError(f"{entry_id}的detail_index无效：{detail_index}")
        detail = details[detail_index]
        if not isinstance(detail, dict):
            raise ValueError(f"{entry_id}的detail_index未指向对象")
        resolved["detail_index"] = detail_index
        resolved["detailed_item"] = detail.get("detail_title", "")
        resolved["detail_definition"] = detail.get("definition", "")
    elif "detail_index" in match:
        raise ValueError(f"{entry_id}没有detail_entries，不得填写detail_index")
    else:
        resolved["detailed_item"] = entry.get("item_title", "")
        resolved["detail_definition"] = ""
    resolved["catalog_item_no"] = str(entry.get("item_no", ""))
    resolved["catalog_item"] = entry.get("item_title", "")
    resolved["catalog_scope"] = entry.get("catalog_scope", "")
    return resolved


def validate_enterprise_findings(data: object) -> list[str]:
    errors: list[str] = _schema_errors(data, "enterprise-findings.schema.json")
    if not isinstance(data, dict):
        return ["enterprise-findings.json必须是JSON对象"]
    for field in ("version", "enterprise", "report", "research", "equity", "sources"):
        if field not in data:
            errors.append(f"企业输入缺少{field}")
    report = data.get("report") if isinstance(data.get("report"), dict) else {}
    if report.get("equity"):
        errors.append("旧版report.equity不得与顶层equity并存；请先显式迁移")
    sources = _unique_keys(_rows(data.get("sources"), "企业来源", errors), "企业来源", errors)
    source_keys = set(sources)
    research = data.get("research") if isinstance(data.get("research"), dict) else {}
    facts = _unique_keys(_rows(research.get("facts", []), "企业事实", errors), "企业事实", errors)
    candidates = _unique_keys(_rows(research.get("business_candidates", []), "业务候选", errors), "业务候选", errors)
    businesses = _unique_keys(_rows(report.get("businesses", []), "业务", errors), "业务", errors)
    landings = _unique_keys(_rows(report.get("landing_businesses", []), "落地业务", errors), "落地业务", errors)
    routes = _unique_keys(_rows(research.get("department_routes", []), "部门路由", errors), "部门路由", errors)
    report_businesses = _rows(report.get("businesses", []), "业务概况", errors)
    for label, rows in (("企业事实", facts.values()), ("业务概况", report_businesses), ("落地业务", landings.values())):
        for row in rows:
            for key in _refs(row.get("source_keys", []), f"{label}source_keys", errors):
                if _text(key) not in source_keys:
                    errors.append(f"{label}引用未知source key：{key}")
    for key, row in facts.items():
        fact_sources = _refs(row.get("source_keys", []), f"企业事实{key}source_keys", errors)
        if len(fact_sources) != 1:
            errors.append(f"企业事实{key}的source_keys必须恰好一项；正式研究台账只接受单一source_id")
        elif _text(fact_sources[0]) in sources and _text(sources[_text(fact_sources[0])].get("type")) == "industry_catalog":
            errors.append(f"企业事实{key}不能引用industry_catalog；正式研究台账事实来源必须编译为E类source_id")
    for row in candidates.values():
        for key in _refs(row.get("fact_keys", []), "业务候选fact_keys", errors):
            if _text(key) not in facts:
                errors.append(f"业务候选引用未知fact key：{key}")
    for row in routes.values():
        if _text(row.get("landing_business_key")) not in landings:
            errors.append(f"部门路由引用未知landing business key：{row.get('landing_business_key', '')}")
        for key in _refs(row.get("candidate_keys", []), "部门路由candidate_keys", errors):
            if _text(key) not in candidates:
                errors.append(f"部门路由引用未知candidate key：{key}")
    assessment = report.get("encouraged_industry_assessment") if isinstance(report.get("encouraged_industry_assessment"), dict) else {}
    for assessment_index, assessment_row in enumerate(_rows(assessment.get("business_assessments", []), "目录业务判断", errors)):
        for match_index, match in enumerate(_rows(assessment_row.get("matched_items", []), f"目录业务判断[{assessment_index}]matched_items", errors)):
            try:
                resolve_catalog_match(match)
            except ValueError as error:
                errors.append(f"report.encouraged_industry_assessment.business_assessments[{assessment_index}].matched_items[{match_index}].detail_index: {error}")
    equity = data.get("equity") if isinstance(data.get("equity"), dict) else {}
    for index, source in enumerate(equity.get("sources", [])):
        if not isinstance(source, dict):
            errors.append(f"equity.sources[{index}]必须为取证记录对象，不是来源编号；节点和连线的来源编号填写source_keys")
    node_rows = _rows(equity.get("nodes", []), "股权节点", errors)
    nodes = _unique_keys(node_rows, "股权节点", errors)
    for row in node_rows:
        if _text(row.get("assertion_type")) not in ASSERTION_TYPES:
            errors.append(f"股权节点断言类型无效：{row.get('assertion_type', '')}")
        if not _text(row.get("role")):
            errors.append(f"股权节点{_text(row.get('key')) or '（未命名）'}缺少role；正式报告必须明确节点角色")
        for key in _refs(row.get("source_keys", []), "股权节点source_keys", errors):
            if _text(key) not in source_keys:
                errors.append(f"股权节点引用未知source key：{key}")
    edge_rows = _rows(equity.get("edges", []), "股权连接", errors)
    _unique_keys(edge_rows, "股权连接", errors)
    for row in edge_rows:
        if _text(row.get("assertion_type")) not in ASSERTION_TYPES:
            errors.append(f"股权连接断言类型无效：{row.get('assertion_type', '')}")
        for field in ("from_key", "to_key"):
            if _text(row.get(field)) not in nodes:
                errors.append(f"股权连接引用未知节点key：{row.get(field, '')}")
        for key in _refs(row.get("source_keys", []), "股权连接source_keys", errors):
            if _text(key) not in source_keys:
                errors.append(f"股权连接引用未知source key：{key}")
        percentage = row.get("ownership_percent")
        if percentage is not None and (not isinstance(percentage, (int, float)) or isinstance(percentage, bool) or percentage <= 0 or percentage > 100):
            errors.append(f"股权连接ownership_percent必须为大于0且不超过100的数值：{percentage}")
        if row.get("assertion_type") == "provider_calculation" or row.get("is_remainder") is True:
            if not _text(row.get("calculation_basis")):
                errors.append("股权连接使用计算或其他股东合计时必须提供calculation_basis")
    equity_status = _text(equity.get("data_status"))
    if equity_status in {"available", "partial"}:
        summary = equity.get("evidence_summary") if isinstance(equity.get("evidence_summary"), dict) else {}
        display_source_key = _text(summary.get("display_source_key"))
        if not display_source_key:
            errors.append("可公开股权缺少evidence_summary.display_source_key；正式报告必须展示取证来源")
        elif display_source_key not in source_keys:
            errors.append(f"股权evidence_summary引用未知source key：{display_source_key}")
        elif _text(sources[display_source_key].get("type")) == "industry_catalog":
            errors.append("股权evidence_summary不得引用industry_catalog；正式报告展示来源必须是E类")
        if not _text(summary.get("as_of_date")):
            errors.append("可公开股权缺少evidence_summary.as_of_date；正式报告必须展示数据时点")
    financial_meta = report.get("meta") if isinstance(report.get("meta"), dict) else {}
    currency, unit = _text(financial_meta.get("financial_currency")), _text(financial_meta.get("financial_unit"))
    if bool(currency) != bool(unit):
        errors.append("report.meta.financial_currency和financial_unit必须同时填写或同时缺省")
    for index, row in enumerate(_rows(report.get("financials", []), "财务数据", errors)):
        components = row.get("government_support_components")
        if components is None:
            continue
        if not unit:
            errors.append(f"report.financials[{index}].government_support_components要求meta.financial_unit")
        for component_index, component in enumerate(_rows(components, f"财务数据[{index}]补助组成", errors)):
            amount = component.get("amount")
            if not isinstance(amount, (int, float)) or isinstance(amount, bool):
                errors.append(f"report.financials[{index}].government_support_components[{component_index}].amount必须是数值")
    return errors


def validate_policy_findings(data: object) -> list[str]:
    errors: list[str] = _schema_errors(data, "policy-findings.schema.json")
    if not isinstance(data, dict):
        return ["policy-findings.json必须是JSON对象"]
    for field in ("version", "enterprise", "researched_at", "policy_records", "search", "evidence", "sources"):
        if field not in data:
            errors.append(f"政策输入缺少{field}")
    records = _unique_keys(_rows(data.get("policy_records", []), "政策主记录", errors), "政策主记录", errors)
    sources = _unique_keys(_rows(data.get("sources", []), "政策来源", errors), "政策来源", errors)
    search = data.get("search") if isinstance(data.get("search"), dict) else {}
    if search.get("policy_candidates"):
        errors.append("search.policy_candidates已废弃；只能由policy_records编译派生")
    if "report" in data:
        errors.append("policy-findings.json不得包含废弃report字段；政策只允许写入policy_records")
    searches = _unique_keys(_rows(search.get("searches", []), "政策检索任务", errors), "政策检索任务", errors)
    profiles = _unique_keys(_rows(search.get("department_scan_profiles", []), "部门检索档案", errors), "部门检索档案", errors)
    discovered = _rows(search.get("discovered_candidates", []), "发现候选草稿", errors)
    discovered_keys: dict[str, dict] = {}
    for index, row in enumerate(discovered, 1):
        key = _text(row.get("key") or row.get("stable_key"))
        if not key:
            errors.append(f"发现候选草稿第{index}项缺少key或stable_key")
        elif key in discovered_keys:
            errors.append(f"发现候选草稿稳定key重复：{key}")
        else:
            discovered_keys[key] = row
    evidence = _unique_keys(_rows(data.get("evidence", []), "政策证据", errors), "政策证据", errors)
    for key, row in evidence.items():
        source_key = _text(row.get("policy_source_key"))
        if source_key and source_key not in sources:
            errors.append(f"政策证据{key}引用未知policy source key：{source_key}")
    for key, row in profiles.items():
        for run in _rows(row.get("runs", []), f"部门检索档案{key} runs", errors):
            if not isinstance(run, dict):
                errors.append(f"部门检索档案{key}存在非对象run")
                continue
            for ref in _refs(run.get("result_source_keys", []), f"部门检索档案{key} result_source_keys", errors):
                if _text(ref) not in sources:
                    errors.append(f"部门检索档案{key}的run引用未知result source key：{ref}")
            for ref in _refs(run.get("evidence_record_keys", []), f"部门检索档案{key} evidence_record_keys", errors):
                if _text(ref) not in evidence:
                    errors.append(f"部门检索档案{key}的run引用未知evidence key：{ref}")
    for key, row in searches.items():
        profile_key = _text(row.get("profile_key"))
        if profile_key and profile_key not in profiles:
            errors.append(f"政策检索任务{key}引用未知profile key：{profile_key}")
    for key, row in records.items():
        for field, known in (("source_keys", sources), ("search_keys", searches), ("evidence_keys", evidence)):
            for ref in _refs(row.get(field, []), f"政策主记录{key}{field}", errors):
                if _text(ref) not in known:
                    errors.append(f"政策主记录{key}引用未知{field}：{ref}")
        if _text(row.get("eligibility_status")) not in POLICY_ELIGIBILITY:
            errors.append(f"政策主记录{key}eligibility_status无效")
        if _text(row.get("disposition")) not in POLICY_DISPOSITIONS:
            errors.append(f"政策主记录{key}disposition无效")
        for field in ("topic", "match_reason", "report_group"):
            if not _text(row.get(field)):
                errors.append(f"政策主记录{key}缺少{field}")
    return errors


def validate_findings_contracts(enterprise: object, policy: object) -> list[str]:
    return validate_enterprise_findings(enterprise) + validate_policy_findings(policy)
