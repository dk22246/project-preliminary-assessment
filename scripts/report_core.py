"""Portable report-data validation and HTML construction for the assessment Skill."""
from __future__ import annotations

from html import escape
from pathlib import Path
import json
import re
from urllib.parse import urlparse


REQUIRED_TOP = ("meta", "entity_resolution", "equity", "businesses", "financials", "risks", "landing_businesses", "policy_research", "policies", "sources")
REQUIRED_ENTITY = ("user_input", "name_type", "legal_entity", "analysis_entity", "financial_scope", "risk_scope")
REQUIRED_POLICY = ("name", "region", "region_evidence", "source_type", "source_url", "status", "enterprise_business", "landing_action")
POLICY_EVIDENCE_FIELDS = ("source_id", "issuer", "document_number", "published_at", "validity_evidence", "applicable_object", "plain_language", "conditions", "policy_value", "handling_route")
POLICY_EVIDENCE_LABELS = {"source_id": "来源编号", "issuer": "发文机关", "document_number": "文号", "published_at": "发布日期", "validity_evidence": "现行状态依据", "applicable_object": "适用对象", "plain_language": "政策一句话说明", "conditions": "核心条件", "policy_value": "政策实际价值", "handling_route": "办理方式"}
LEDGER_OUTCOMES = {"direct_match", "conditional_opportunity", "not_triggered", "no_current_policy"}
LEDGER_LABELS = {"direct_match": "可适用（条件待核）", "conditional_opportunity": "条件型政策机会", "not_triggered": "暂未触发", "no_current_policy": "未发现现行政策"}
TERMS = ("实质性运营", "拟落地主体", "核心经营主体", "控股股东", "政府补助及财政支持")


def load_data(path: str | Path) -> dict:
    # Accept UTF-8 with or without BOM: several Windows-based agents add a BOM
    # when saving JSON, while the generated report data remains UTF-8.
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate_report_data(data: dict) -> list[str]:
    errors = [f"缺少顶层字段：{name}" for name in REQUIRED_TOP if not data.get(name)]
    entity = data.get("entity_resolution", {})
    errors.extend(f"主体认定缺少字段：{name}" for name in REQUIRED_ENTITY if not str(entity.get(name, "")).strip())
    nodes = data.get("equity", {}).get("nodes", [])
    edges = data.get("equity", {}).get("edges", [])
    node_ids = {node.get("id") for node in nodes}
    if not nodes or not edges:
        errors.append("股权关系至少需要节点和连接线")
    for node in nodes:
        for field in ("id", "name", "entity_type", "role"):
            if not str(node.get(field, "")).strip():
                errors.append(f"股权节点缺少{field}：{node}")
    for edge in edges:
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            errors.append(f"股权连接引用不存在节点：{edge}")
        if not str(edge.get("relationship", "")).strip():
            errors.append(f"股权连接缺少relationship：{edge}")
    if len(data.get("businesses", [])) > 6:
        errors.append("核心业务板块不得超过6项")
    for item in data.get("businesses", []):
        for field in ("segment", "products", "entity", "revenue_model", "footprint", "sanya_fit"):
            if not str(item.get(field, "")).strip():
                errors.append(f"业务拆解缺少{field}：{item.get('segment', '未命名业务')}")
    if len(data.get("financials", [])) != 3:
        errors.append("财务数据必须恰好包含最近三个完整年度")
    for row in data.get("financials", []):
        for field in ("year", "revenue", "profit", "tax_value", "tax_basis", "government_support", "source"):
            if not str(row.get(field, "")).strip():
                errors.append(f"财务行缺少{field}：{row}")
        if row.get("tax_basis") not in ("纳税总额", "支付的各项税费", "所得税费用", "税金及附加", "其他公开税费口径", "需企业补充"):
            errors.append(f"纳税口径不规范：{row.get('tax_basis')}")
    for item in data.get("landing_businesses", []):
        for field in ("id", "business", "fact_basis", "sanya_path", "value", "feasibility"):
            if not str(item.get(field, "")).strip():
                errors.append(f"落地业务缺少{field}：{item.get('business', '未命名业务')}")
    for policy in data.get("policies", []):
        errors.extend(f"政策卡缺少{field}：{policy.get('name', '未命名政策')}" for field in REQUIRED_POLICY if not str(policy.get(field, "")).strip())
        if policy.get("source_type") != "official" or policy.get("status") != "current":
            errors.append(f"政策卡未满足正式现行条件：{policy.get('name')}")
    errors.extend(validate_business_policy_ledger(data))
    return errors


def _is_official_policy_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    return parsed.scheme == "https" and (host.endswith(".gov.cn") or host in {"gov.cn", "chinatax.gov.cn", "customs.gov.cn", "pbc.gov.cn", "safe.gov.cn"})


def validate_business_policy_ledger(data: dict) -> list[str]:
    """Require a research conclusion for every landing business without a fixed policy checklist."""
    errors: list[str] = []
    landings = data.get("landing_businesses", [])
    landings_by_id = {str(item.get("id", "")).strip(): item for item in landings if str(item.get("id", "")).strip()}
    if len(landings_by_id) != len(landings):
        errors.append("落地业务编号必须唯一且不得为空")
    source_by_id = {str(item.get("id", "")).strip(): item for item in data.get("sources", [])}
    policy_by_id = {str(item.get("source_id", "")).strip(): item for item in data.get("policies", [])}
    ledger = data.get("policy_research", [])
    covered: set[str] = set()
    for item in ledger:
        landing_id = str(item.get("landing_business_id", "")).strip()
        topic = str(item.get("topic", "")).strip() or "未命名政策主题"
        label = f"{landing_id or '未关联业务'} / {topic}"
        if landing_id not in landings_by_id:
            errors.append(f"{label}: 未关联有效落地业务")
        else:
            covered.add(landing_id)
        if not item.get("searched_departments"):
            errors.append(f"{label}: 缺少检索主管部门")
        outcome = str(item.get("outcome", "")).strip()
        if outcome not in LEDGER_OUTCOMES:
            errors.append(f"{label}: 检索结论必须为 {', '.join(sorted(LEDGER_OUTCOMES))}")
        if not str(item.get("conclusion", "")).strip():
            errors.append(f"{label}: 缺少检索结论说明")
        evidence_ids = item.get("evidence_source_ids", [])
        if not evidence_ids:
            errors.append(f"{label}: 缺少检索依据来源")
        for source_id in evidence_ids:
            if source_id not in source_by_id or not str(source_id).startswith("P"):
                errors.append(f"{label}: 检索依据不是有效P类参考资料：{source_id}")
        if outcome in {"direct_match", "conditional_opportunity"} and not item.get("policy_ids"):
            errors.append(f"{label}: 可适用或条件型机会必须关联正式政策")
        if outcome in {"not_triggered", "no_current_policy"} and not str(item.get("next_evidence", "")).strip():
            errors.append(f"{label}: 缺少未触发或无政策的原因及下一步核实事项")
        for policy_id in item.get("policy_ids", []):
            if policy_id not in policy_by_id:
                errors.append(f"{label}: 关联政策不存在：{policy_id}")
    for landing_id, landing in landings_by_id.items():
        if landing_id not in covered:
            errors.append(f"{landing.get('business', landing_id)}: 缺少政策检索结论")
    for policy_id, policy in policy_by_id.items():
        label = str(policy.get("name", policy_id)).strip() or policy_id
        for field in POLICY_EVIDENCE_FIELDS:
            if not str(policy.get(field, "")).strip():
                errors.append(f"{label}: 缺少{POLICY_EVIDENCE_LABELS[field]}")
        source = source_by_id.get(policy_id)
        if not source or not policy_id.startswith("P"):
            errors.append(f"{label}: 缺少对应P类参考资料")
        else:
            if str(source.get("location", "")).strip() != str(policy.get("source_url", "")).strip():
                errors.append(f"{label}: 政策原文链接与P类参考资料不一致")
        if not _is_official_policy_url(str(policy.get("source_url", "")).strip()):
            errors.append(f"{label}: 政策原文链接不是可识别的官方HTTPS地址")
    return errors


def validate_text(data: dict) -> list[str]:
    payload = json.dumps(data, ensure_ascii=False)
    errors = []
    if chr(0xFFFD) in payload:
        errors.append("发现乱码替代字符：U+FFFD")
    if re.search(r"\?{2,}", payload):
        errors.append("发现连续问号，需人工检查乱码或残缺文本")
    names = {data.get("entity_resolution", {}).get("legal_entity", ""), data.get("entity_resolution", {}).get("analysis_entity", "")}
    names.discard("")
    for node in data.get("equity", {}).get("nodes", []):
        if node.get("name") in (None, ""):
            errors.append("股权图存在空名称节点")
    return errors


def equity_svg(equity: dict) -> str:
    nodes = equity["nodes"]
    levels: dict[int, list[dict]] = {}
    for node in nodes:
        levels.setdefault(int(node.get("level", 0)), []).append(node)
    width, height = 980, max(320, 180 + len(levels) * 150)
    positions: dict[str, tuple[int, int]] = {}
    for level, items in sorted(levels.items()):
        gap = width // (len(items) + 1)
        for index, node in enumerate(items, 1):
            positions[node["id"]] = (gap * index, 100 + level * 145)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">', '<style>.n{fill:#fff;stroke:#4b5563;stroke-width:1.5}.t{font:14px Arial,"Microsoft YaHei",sans-serif;fill:#111827}.s{font:12px Arial,"Microsoft YaHei",sans-serif;fill:#4b5563}.e{stroke:#6b7280;stroke-width:1.5}.l{font:12px Arial,"Microsoft YaHei",sans-serif;fill:#374151;paint-order:stroke;stroke:#f5f9f9;stroke-width:4px;stroke-linejoin:round}</style>']
    for edge in equity["edges"]:
        x1, y1 = positions[edge["from"]]; x2, y2 = positions[edge["to"]]
        parts.append(f'<line class="e" x1="{x1}" y1="{y1 + 36}" x2="{x2}" y2="{y2 - 36}"/>')
        parts.append(f'<text class="l" x="{(x1+x2)//2}" y="{(y1+y2)//2 - 5}" text-anchor="middle">{escape(edge["relationship"])}</text>')
    for node in nodes:
        x, y = positions[node["id"]]
        name = escape(node["name"]); entity_type = escape(node["entity_type"]); role = escape(node["role"])
        parts.append(f'<rect class="n" x="{x-125}" y="{y-36}" width="250" height="72" rx="8"/>')
        parts.append(f'<text class="t" x="{x}" y="{y-9}" text-anchor="middle">{name}</text><text class="s" x="{x}" y="{y+12}" text-anchor="middle">{entity_type}｜{role}</text>')
    return "".join(parts) + "</svg>"


def table(headers: list[str], rows: list[list[str]], classes: str = "") -> str:
    head = "".join(f"<th>{escape(str(x))}</th>" for x in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(x))}</td>" for x in row) + "</tr>" for row in rows)
    return f'<table class="{classes}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def source_map(data: dict) -> dict[str, dict]:
    return {item["id"]: item for item in data["sources"]}


def policy_plan(data: dict) -> list[dict]:
    mapping = []
    for landing in data["landing_businesses"]:
        mapping.append({"business": landing["business"], "official_sources": landing.get("policy_departments", []), "status": "待检索"})
    return mapping
