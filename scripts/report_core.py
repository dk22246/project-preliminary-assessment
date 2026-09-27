"""Portable report-data validation and HTML construction for the assessment Skill."""
from __future__ import annotations

from html import escape
from pathlib import Path
import json
import os
import re
from urllib.parse import urlparse


REQUIRED_TOP = ("meta", "entity_resolution", "enterprise_overview", "equity", "businesses", "top500_status", "industry_chain", "encouraged_industry_assessment", "industry_position", "financials", "risks", "landing_businesses", "policy_research", "policy_opportunity_radar", "policies", "sources")
REQUIRED_ENTITY = ("user_input", "name_type", "legal_entity", "analysis_entity", "financial_scope", "risk_scope")
REQUIRED_POLICY = ("name", "region", "region_evidence", "source_type", "source_url", "status", "enterprise_business", "landing_action")
POLICY_EVIDENCE_FIELDS = ("source_id", "issuer", "document_number", "published_at", "validity_evidence", "applicable_object", "plain_language", "conditions", "policy_value", "handling_route")
POLICY_EVIDENCE_LABELS = {"source_id": "来源编号", "issuer": "发文机关", "document_number": "文号", "published_at": "发布日期", "validity_evidence": "现行状态依据", "applicable_object": "适用对象", "plain_language": "政策一句话说明", "conditions": "核心条件", "policy_value": "政策实际价值", "handling_route": "办理方式"}
LEDGER_OUTCOMES = {"direct_match", "conditional_opportunity", "not_triggered", "not_applicable", "no_current_policy", "research_incomplete"}
LEDGER_LABELS = {"direct_match": "可适用（条件待核）", "conditional_opportunity": "条件型政策机会", "not_triggered": "暂未触发", "not_applicable": "现有条件不适用", "no_current_policy": "未发现现行政策", "research_incomplete": "检索未完成（禁止交付）"}
TERMS = ("实质性运营", "拟落地主体", "核心经营主体", "控股股东", "政府补助及财政支持")
YOY_PATTERN = re.compile(r"(?:[+-]?\d+(?:\.\d+)?%|—|未计算|未公开披露)")
FINANCIAL_VALUE_PATTERN = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
FINANCIAL_UNAVAILABLE = "未公开披露"
FINANCIAL_DATA_STATUSES = {"available", "partial", "not_public", "inaccessible"}
INDUSTRY_EVIDENCE_STATUSES = {"ranked", "market_share", "tier", "qualitative_only", "not_public"}
EQUITY_CONFLICT_FIELDS = (
    "id",
    "field",
    "severity",
    "status",
    "title",
    "difference",
    "reason",
    "adopted_basis",
    "impact",
    "next_action",
    "graph_action",
)
EQUITY_CONFLICT_SEVERITIES = {"general", "material_local", "subject_critical"}
EQUITY_CONFLICT_STATUSES = {"resolved", "unresolved"}
EQUITY_GRAPH_ACTIONS = {"keep_confirmed_part", "omit_disputed_part"}
EQUITY_DATA_STATUSES = {"available", "partial", "not_public", "inaccessible"}
OPPORTUNITY_DISPOSITIONS = {"surfaced", "merged", "excluded", "expired", "not_current", "pending_evidence", "research_incomplete"}
OVERSEAS_OPPORTUNITY_TOPICS = {
    "foreign_trade",
    "ef_account",
    "cross_border_settlement",
    "odi",
    "overseas_income_tax",
    "cross_border_fund_pool",
    "offshore_trade_stamp_duty",
}
RANKING_NAMES = {"fortune_global_500", "china_enterprise_500", "china_private_enterprise_500"}
RANKING_SOURCE_TYPES = {"官方榜单", "权威转载榜单"}
TOP500_STATUSES = {"listed", "group_listed", "not_listed", "research_incomplete"}
TOP500_RELATIONSHIPS = {"same_entity", "parent_group", "ultimate_group", "not_applicable"}
TRANSACTION_TERMS = re.compile(r"供应商|供货商|客户|采购方|经销商|合作伙伴|合作方|supplier|vendor|customer|client|dealer|partner", re.IGNORECASE)
NEGATED_TRANSACTION_TERMS = re.compile(
    r"(?:不(?:代表|是|属于|作为)?|非|未(?:确认|证实)?)(?:已确认)?(?:供应商|客户|合作伙伴)(?:或(?:供应商|客户|合作伙伴))*|"
    r"(?:not|no)\s+(?:a\s+)?(?:confirmed\s+)?(?:supplier|customer|client|partner)",
    re.IGNORECASE,
)


def load_data(path: str | Path) -> dict:
    # Accept UTF-8 with or without BOM: several Windows-based agents add a BOM
    # when saving JSON, while the generated report data remains UTF-8.
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def load_ranking_registry(path: str | Path | None = None) -> dict[str, dict]:
    """Load the current ranking contract from data, failing closed on drift."""
    registry_path = Path(path or os.environ.get("REPORT_RANKING_REGISTRY") or Path(__file__).parents[1] / "references" / "ranking-registry.json")
    try:
        payload = load_data(registry_path)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"500强榜单注册表不可读取：{registry_path}") from exc
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(payload.get("verified_at", ""))):
        raise ValueError("500强榜单注册表缺少有效verified_at")
    raw = payload.get("rankings")
    if not isinstance(raw, dict) or set(raw) != RANKING_NAMES:
        raise ValueError("500强榜单注册表必须恰好包含三类榜单且不得重复")
    for name, item in raw.items():
        if not isinstance(item, dict):
            raise ValueError(f"500强榜单注册表/{name}必须为对象")
        if not isinstance(item.get("year"), int) or item["year"] < 2000:
            raise ValueError(f"500强榜单注册表/{name}年度无效")
        if not str(item.get("official_url", "")).startswith("https://"):
            raise ValueError(f"500强榜单注册表/{name}缺少HTTPS正式来源")
        if item.get("source_type") not in RANKING_SOURCE_TYPES:
            raise ValueError(f"500强榜单注册表/{name}来源类型不是官方榜单或权威转载榜单")
        issuers = item.get("allowed_issuers")
        if not isinstance(issuers, list) or not issuers or any(not str(value).strip() for value in issuers):
            raise ValueError(f"500强榜单注册表/{name}缺少允许发布机构")
    return raw


def financial_headers(meta: dict) -> list[str]:
    """Use the explicitly declared display unit; never infer it from cell text."""
    unit = str(meta.get("financial_unit", "")).strip()
    suffix = f"（{unit}）" if unit else ""
    return ["年度", f"营业收入{suffix}", "同比", f"净利润{suffix}", "同比", "纳税相关数据", "纳税数据口径", "政府补助及财政支持", "来源编号"]


def financial_change_notes(financials: list[dict]) -> list[str]:
    """Keep change and public-data availability explanations below the table."""
    notes: list[str] = []
    for row in financials:
        year = str(row.get("year", "未注明年度")).strip()
        note = str(row.get("change_note", "")).strip()
        if note:
            notes.append(f"{year}：{note}")
        availability_note = str(row.get("availability_note", "")).strip()
        if availability_note:
            notes.append(f"{year}数据可得性：{availability_note}")
    return notes


def validate_report_data(data: dict) -> list[str]:
    errors = [
        f"缺少顶层字段：{name}" if name not in data else f"顶层字段为空：{name}（检查输入及处置结果，不是编译字段丢失）"
        for name in REQUIRED_TOP if not data.get(name)
    ]
    if "overall_judgment" in data:
        errors.append("已停用顶层字段overall_judgment：报告不得恢复项目整体判断章节")
    entity = data.get("entity_resolution", {})
    errors.extend(f"主体认定缺少字段：{name}" for name in REQUIRED_ENTITY if not str(entity.get(name, "")).strip())
    overview = data.get("enterprise_overview", {})
    for field in ("established_at", "registered_location", "listing_status", "main_business", "employee_scale", "profile", "operating_summary"):
        if not str(overview.get(field, "")).strip():
            errors.append(f"企业概况缺少{field}")
    risks = data.get("risks")
    if not isinstance(risks, dict):
        errors.append("风险数据必须编译为包含regulatory与litigation的结构化对象，禁止将原始风险列表直接交给渲染器")
    else:
        for field, columns in (("regulatory", 7), ("litigation", 6)):
            rows = risks.get(field)
            if not isinstance(rows, list):
                errors.append(f"风险数据缺少{field}数组")
                continue
            for index, row in enumerate(rows, 1):
                if not isinstance(row, list) or len(row) != columns:
                    errors.append(f"风险数据{field}第{index}行必须包含{columns}列")
    equity = data.get("equity", {})
    equity_status = str(equity.get("data_status", "")).strip()
    if equity_status not in EQUITY_DATA_STATUSES:
        errors.append("股权数据缺少有效data_status：只能为available、partial、not_public或inaccessible")
    nodes = equity.get("nodes", [])
    edges = equity.get("edges", [])
    node_ids = {node.get("id") for node in nodes}
    has_graph = bool(nodes or edges)
    if equity_status in {"available", "partial"} and (not nodes or not edges):
        errors.append("股权data_status为available或partial时至少需要一个已核实节点和一条连接线")
    if equity_status in {"not_public", "inaccessible"}:
        if has_graph:
            errors.append("股权公开信息不足时不得生成占位节点或连接线")
        if not str(equity.get("availability_note", "")).strip():
            errors.append("股权公开信息不足时必须填写availability_note")
        search_source_ids = equity.get("search_source_ids", [])
        if not search_source_ids:
            errors.append("股权公开信息不足时必须列出实际查验的search_source_ids")
    for node in nodes:
        for field in ("id", "name", "entity_type", "role"):
            if not str(node.get(field, "")).strip():
                errors.append(f"股权节点缺少{field}：{node}")
        if not node.get("evidence_source_ids"):
            errors.append(f"股权节点缺少evidence_source_ids：{node.get('name', node)}")
    for edge in edges:
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            errors.append(f"股权连接引用不存在节点：{edge}")
        if not str(edge.get("relationship", "")).strip():
            errors.append(f"股权连接缺少relationship：{edge}")
        if not edge.get("evidence_source_ids"):
            errors.append(f"股权连接缺少evidence_source_ids：{edge}")
        relationship = str(edge.get("relationship", ""))
        if any(marker in relationship.lower() for marker in ("持股", "股东", "shareholder", "ownership")) and "ownership_percent" not in edge:
            if equity_status != "partial" or "比例未公开" not in relationship:
                errors.append(f"直接股东或持股连接必须提供ownership_percent；部分披露时须明确写比例未公开：{edge}")
        if "ownership_percent" in edge:
            try:
                percentage = float(edge["ownership_percent"])
            except (TypeError, ValueError):
                errors.append(f"股权连接ownership_percent必须为数值：{edge}")
            else:
                if percentage <= 0 or percentage > 100:
                    errors.append(f"股权连接ownership_percent必须大于0且不超过100：{edge}")
    ownership_by_target: dict[str, list[dict]] = {}
    for edge in edges:
        if "ownership_percent" in edge:
            ownership_by_target.setdefault(str(edge.get("to", "")), []).append(edge)
    for target, ownership_edges in ownership_by_target.items():
        try:
            total = sum(float(edge["ownership_percent"]) for edge in ownership_edges)
        except (TypeError, ValueError):
            continue
        if equity_status == "available" and abs(total - 100.0) > 0.02:
            target_name = next((str(node.get("name")) for node in nodes if node.get("id") == target), target)
            errors.append(f"股权比例未闭合：{target_name}已展示直接股东合计{total:.2f}%，必须补充其他股东合计或修正重复计算")
    report_source_ids = {str(item.get("id", "")).strip() for item in data.get("sources", [])}
    for item in [*nodes, *edges]:
        for source_id in item.get("evidence_source_ids", []):
            if source_id not in report_source_ids or not str(source_id).startswith("E"):
                errors.append(f"股权证据不是有效E类参考资料：{source_id}")
    for source_id in equity.get("search_source_ids", []):
        if source_id not in report_source_ids or not str(source_id).startswith("E"):
            errors.append(f"股权检索依据不是有效E类参考资料：{source_id}")
    if "conflict_disclosures" not in equity or not isinstance(equity.get("conflict_disclosures"), list):
        errors.append("股权数据必须包含conflict_disclosures数组；无差异时填写空数组")
    evidence_summary = equity.get("evidence_summary")
    if equity_status in {"available", "partial"} and not isinstance(evidence_summary, dict):
        errors.append("有股权图时必须包含evidence_summary并显示采用来源")
    elif isinstance(evidence_summary, dict):
        for field in ("display_source_id", "display_source_title", "as_of_date"):
            if not str(evidence_summary.get(field, "")).strip():
                errors.append(f"股权取证口径缺少{field}")
        display_source_id = str(evidence_summary.get("display_source_id", "")).strip()
        if display_source_id and (display_source_id not in report_source_ids or not display_source_id.startswith("E")):
            errors.append(f"股权显示来源不是有效E类参考资料：{display_source_id}")
    disclosure_ids: set[str] = set()
    for item in equity.get("conflict_disclosures", []):
        conflict_id = str(item.get("id", "")).strip()
        if not conflict_id or conflict_id in disclosure_ids:
            errors.append(f"股权差异说明编号为空或重复：{conflict_id or '空'}")
        disclosure_ids.add(conflict_id)
        for field in EQUITY_CONFLICT_FIELDS:
            if not str(item.get(field, "")).strip():
                errors.append(f"股权差异说明{conflict_id or '未编号'}缺少{field}")
        if item.get("severity") not in EQUITY_CONFLICT_SEVERITIES:
            errors.append(f"股权差异说明{conflict_id or '未编号'}的severity无效")
        if item.get("status") not in EQUITY_CONFLICT_STATUSES:
            errors.append(f"股权差异说明{conflict_id or '未编号'}的status无效")
        if item.get("graph_action") not in EQUITY_GRAPH_ACTIONS:
            errors.append(f"股权差异说明{conflict_id or '未编号'}的graph_action无效")
        if not isinstance(item.get("affected_node_ids"), list) or not isinstance(item.get("affected_edges"), list):
            errors.append(f"股权差异说明{conflict_id or '未编号'}缺少结构化影响范围")
        evidence_source_ids = item.get("evidence_source_ids", [])
        if not evidence_source_ids:
            errors.append(f"股权差异说明{conflict_id or '未编号'}缺少证据来源")
        for source_id in evidence_source_ids:
            if source_id not in report_source_ids or not str(source_id).startswith("E"):
                errors.append(f"股权差异说明引用无效E类参考资料：{source_id}")
    if len(data.get("businesses", [])) > 6:
        errors.append("核心业务板块不得超过6项")
    business_ids = [str(item.get("id", "")).strip() for item in data.get("businesses", [])]
    if any(not item for item in business_ids) or len(set(business_ids)) != len(business_ids):
        errors.append("主要业务必须具有唯一且非空的B类id")
    for source_id in overview.get("source_ids", []):
        if source_id not in report_source_ids or not str(source_id).startswith(("E", "F")):
            errors.append(f"企业概况引用无效E/F类来源：{source_id}")
    if not overview.get("source_ids"):
        errors.append("企业概况缺少source_ids")
    for item in data.get("businesses", []):
        if "sanya_fit" in item:
            errors.append(f"已停用业务字段sanya_fit：{item.get('segment', '未命名业务')}")
        if "revenue_model" in item:
            errors.append(f"已停用业务字段revenue_model，请使用sales_channels：{item.get('segment', '未命名业务')}")
        for field in ("segment", "products", "entity", "sales_channels", "footprint"):
            if not str(item.get(field, "")).strip():
                errors.append(f"业务拆解缺少{field}：{item.get('segment', '未命名业务')}")
    errors.extend(validate_top500_status(data, report_source_ids))
    errors.extend(validate_industry_chain(data, report_source_ids))
    industry = data.get("industry_position", {})
    if not isinstance(industry, dict):
        errors.append("行业地位必须使用结构化对象，包含结论、品类、位置、时点和来源")
    else:
        for field in ("statement", "category", "position", "period", "evidence_status", "source_ids"):
            if not industry.get(field):
                errors.append(f"行业地位缺少{field}")
        position = str(industry.get("position", "")).strip()
        evidence_status = str(industry.get("evidence_status", "")).strip()
        if evidence_status not in INDUSTRY_EVIDENCE_STATUSES:
            errors.append("行业地位evidence_status只能为ranked、market_share、tier、qualitative_only或not_public")
        elif evidence_status in {"ranked", "market_share", "tier"} and position and not re.search(r"(?:第\s*1|第一|头部|第一梯队|TOP\s*1|Top\s*1|top\s*1|市场份额|排名)", position):
            errors.append("行业地位必须写明经证据支持的排名、份额或第一梯队定位，不得只写知名品牌")
        elif evidence_status in {"qualitative_only", "not_public"} and not re.search(r"(?:未发现|未公开|不足|无法|不形成|不认定)", str(industry.get("statement", "")) + position):
            errors.append("行业地位缺少公开排名时必须明确证据边界，不得改写为头部或知名品牌")
        for source_id in industry.get("source_ids", []):
            if source_id not in report_source_ids or not str(source_id).startswith("E"):
                errors.append(f"行业地位引用无效E类来源：{source_id}")
    if len(data.get("financials", [])) != 3:
        errors.append("财务数据必须恰好包含最近三个完整年度")
    meta = data.get("meta", {})
    if str(meta.get("policy_search_mode", "")).strip() != "realtime":
        errors.append("政策检索模式必须为realtime")
    if not str(meta.get("policy_researched_at", "")).strip():
        errors.append("报告缺少policy_researched_at实时检索时间")
    currency = str(meta.get("financial_currency", "")).strip()
    unit = str(meta.get("financial_unit", "")).strip()
    if bool(currency) != bool(unit):
        errors.append("财务币种和显示单位必须同时填写或同时缺省")
    if currency and not re.fullmatch(r"[A-Z]{3}", currency):
        errors.append("financial_currency 必须为三位大写 ISO 币种代码")
    if unit and len(unit) > 20:
        errors.append("financial_unit 过长，必须使用简短统一显示单位")
    for row in data.get("financials", []):
        for field in ("year", "data_status", "revenue", "revenue_change", "profit", "profit_change", "tax_value", "tax_basis", "government_support", "source"):
            if not str(row.get(field, "")).strip():
                errors.append(f"财务行缺少{field}：{row}")
        data_status = str(row.get("data_status", "")).strip()
        if data_status not in FINANCIAL_DATA_STATUSES:
            errors.append(f"财务行data_status不规范：{data_status or '缺失'}")
        for field in ("revenue", "profit"):
            value = str(row.get(field, "")).strip()
            if value and value != FINANCIAL_UNAVAILABLE and not FINANCIAL_VALUE_PATTERN.fullmatch(value):
                errors.append(f"财务行{field}必须为不含币种和单位的数值或“未公开披露”：{value}")
        availability = [str(row.get(field, "")).strip() != FINANCIAL_UNAVAILABLE for field in ("revenue", "profit")]
        if data_status == "available" and not all(availability):
            errors.append(f"财务行data_status为available时收入和利润必须都有可靠数值：{row.get('year', '')}")
        elif data_status == "partial" and (all(availability) or not any(availability)):
            errors.append(f"财务行data_status为partial时收入和利润必须仅有一项可得：{row.get('year', '')}")
        elif data_status in {"not_public", "inaccessible"} and any(availability):
            errors.append(f"财务行data_status为{data_status}时收入和利润均应标为未公开披露：{row.get('year', '')}")
        if data_status in {"partial", "not_public", "inaccessible"} and not str(row.get("availability_note", "")).strip():
            errors.append(f"财务行{row.get('year', '未注明年度')}缺少availability_note")
        for field in ("revenue_change", "profit_change"):
            value = str(row.get(field, "")).strip()
            if value and not YOY_PATTERN.fullmatch(value):
                errors.append(f"财务行{field}同比字段格式不规范，必须为百分比、—、未计算或未公开披露：{value}")
        if any(str(row.get(field, "")).strip() in {"—", "未计算"} for field in ("revenue_change", "profit_change")) and not str(row.get("change_note", "")).strip():
            errors.append(f"财务行{row.get('year', '未注明年度')}未计算同比时必须填写change_note")
        if len(str(row.get("change_note", "")).strip()) > 160:
            errors.append(f"财务行{row.get('year', '未注明年度')}change_note 过长，应移入经营分析")
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
    policy_groups: dict[str, list[dict]] = {}
    for policy in data.get("policies", []):
        group = str(policy.get("report_group") or policy.get("source_id") or policy.get("name", "")).strip()
        policy_groups.setdefault(group, []).append(policy)
    for group, policies in policy_groups.items():
        lead = policies[0]
        if not str(lead.get("report_title", "")).strip():
            errors.append(f"政策展示组{group}缺少利益可读的report_title")
        if not str(lead.get("report_reason", "")).strip():
            errors.append(f"政策展示组{group}缺少事实与条件合并后的report_reason")
    errors.extend(validate_policy_opportunity_radar(data, report_source_ids))
    errors.extend(validate_business_policy_ledger(data))
    return errors


def validate_policy_opportunity_radar(data: dict, report_source_ids: set[str] | None = None) -> list[str]:
    """Require every observed signal to receive an auditable policy-opportunity disposition."""
    errors: list[str] = []
    radar = data.get("policy_opportunity_radar", {})
    signals = radar.get("signals", []) if isinstance(radar, dict) else []
    if not signals:
        return ["政策机会雷达缺少企业事实信号"]
    seen_ids: set[str] = set()
    visible_policy_ids = {str(item.get("source_id", "")).strip() for item in data.get("policies", []) if str(item.get("source_id", "")).strip()}
    radar_positive_ids: set[str] = set()
    enterprise_fact_ids = {
        str(item.get("id", "")).strip()
        for section in ("businesses", "landing_businesses")
        for item in data.get(section, [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    for signal in signals:
        signal_id = str(signal.get("id", "")).strip()
        label = signal_id or "未编号信号"
        if not signal_id or signal_id in seen_ids:
            errors.append(f"政策机会雷达信号编号为空或重复：{label}")
        seen_ids.add(signal_id)
        for field in ("signal_type", "fact", "source_ids", "opportunities"):
            if not signal.get(field):
                errors.append(f"政策机会雷达{label}缺少{field}")
        if report_source_ids is not None:
            for source_id in signal.get("source_ids", []):
                if source_id not in report_source_ids or not str(source_id).startswith(("E", "F")):
                    errors.append(f"政策机会雷达{label}引用无效企业事实来源：{source_id}")
        topics: set[str] = set()
        for opportunity in signal.get("opportunities", []):
            topic = str(opportunity.get("topic", "")).strip()
            disposition = str(opportunity.get("disposition", "")).strip()
            if not topic or topic in topics:
                errors.append(f"政策机会雷达{label}的机会主题为空或重复：{topic or '空'}")
            topics.add(topic)
            if disposition not in OPPORTUNITY_DISPOSITIONS:
                errors.append(f"政策机会雷达{label}/{topic or '未命名主题'}的disposition无效")
            if not str(opportunity.get("reason", "")).strip():
                errors.append(f"政策机会雷达{label}/{topic or '未命名主题'}缺少处置原因")
            if disposition == "research_incomplete":
                errors.append(f"政策机会雷达{label}/{topic or '未命名主题'}检索未完成，禁止交付")
            policy_source_ids = {str(value).strip() for value in opportunity.get("policy_source_ids", []) if str(value).strip()}
            if disposition in {"surfaced", "merged"}:
                radar_positive_ids.update(policy_source_ids)
            if disposition == "surfaced" and not (policy_source_ids & visible_policy_ids):
                errors.append(f"政策机会雷达{label}/{topic or '未命名主题'}标记surfaced但没有进入正式政策表")
        signal_type = str(signal.get("signal_type", "")).strip().lower()
        basis_type = str(signal.get("basis_type", "")).strip().lower()
        enterprise_fact_refs = signal.get("enterprise_fact_refs", [])
        source_kinds = {str(value).strip().lower() for value in signal.get("source_kinds", [])}
        if basis_type != "enterprise_fact":
            errors.append(f"政策机会雷达{label}的basis_type必须为enterprise_fact")
        if not isinstance(enterprise_fact_refs, list) or not enterprise_fact_refs or any(str(ref) not in enterprise_fact_ids for ref in enterprise_fact_refs):
            errors.append(f"政策机会雷达{label}必须引用已存在的企业业务或拟落地业务ID，不得以行业共性需求替代企业事实")
        if signal_type == "industry_common_need" or "industry_inference" in source_kinds:
            errors.append(f"政策机会雷达{label}不得以industry_common_needs或industry_inference作为企业事实触发")
        signal_fact = str(signal.get("fact", ""))
        is_overseas_signal = is_overseas_business_signal(signal_type, signal_fact)
        if is_overseas_signal:
            missing = sorted(OVERSEAS_OPPORTUNITY_TOPICS - topics)
            if missing:
                errors.append(f"海外业务信号缺少机会处置：{', '.join(missing)}")
    missing_from_radar = sorted(visible_policy_ids - radar_positive_ids)
    if missing_from_radar:
        errors.append(f"正式政策表存在未由企业事实信号触发的政策：{', '.join(missing_from_radar)}")
    return errors


def is_overseas_business_signal(signal_type: object, fact: object) -> bool:
    return (
        any(marker in str(signal_type).lower() for marker in ("overseas", "foreign_trade", "cross_border", "global"))
        or any(marker in str(fact) for marker in ("海外", "境外", "跨境", "出口", "国际市场", "境外投资"))
    )


def validate_top500_status(data: dict, report_source_ids: set[str]) -> list[str]:
    """Require exactly the latest official result for each mandated ranking."""
    errors: list[str] = []
    try:
        requirements = load_ranking_registry()
    except ValueError as exc:
        return [str(exc)]
    items = data.get("top500_status", [])
    if not isinstance(items, list):
        return ["top500_status必须为列表"]
    names = [item.get("ranking_name") for item in items if isinstance(item, dict)]
    if set(names) != set(requirements) or len(names) != len(requirements):
        errors.append("top500_status必须恰好覆盖三类指定500强榜单，且不得重复或额外添加")
    sources = {str(item.get("id", "")).strip(): item for item in data.get("sources", [])}
    for item in items:
        if not isinstance(item, dict):
            errors.append("top500_status条目必须为对象")
            continue
        name = item.get("ranking_name")
        status = item.get("status")
        label = name or "未命名榜单"
        if not str(item.get("ranking_label", "")).strip():
            errors.append(f"top500_status/{label}缺少ranking_label")
        if name not in requirements:
            continue
        requirement = requirements[name]
        expected_year = requirement["year"]
        expected_url = requirement["official_url"]
        expected_issuers = set(requirement["allowed_issuers"])
        expected_source_type = requirement["source_type"]
        if item.get("year") != expected_year:
            errors.append(f"top500_status/{label}/{status or 'unknown'}必须使用最新正式年度{expected_year}")
        if status not in TOP500_STATUSES:
            errors.append(f"top500_status/{label}的status无效")
        relationship = item.get("relationship_to_target")
        if relationship not in TOP500_RELATIONSHIPS:
            errors.append(f"top500_status/{label}的relationship_to_target无效")
        source_ids = item.get("source_ids", [])
        valid_official_source = any(
            source_id in report_source_ids and str(source_id).startswith("E")
            and str(sources.get(str(source_id), {}).get("location", "")).strip() == expected_url
            and str(sources.get(str(source_id), {}).get("type", "")).strip() == expected_source_type
            and str(sources.get(str(source_id), {}).get("issuer", "")).strip() in expected_issuers
            for source_id in source_ids
        )
        if not valid_official_source:
            errors.append(f"top500_status/{label}/{status or 'unknown'}必须引用对应最新官方榜单E类来源")
        if status == "listed":
            if not isinstance(item.get("rank"), int) or not str(item.get("listed_entity", "")).strip() or relationship != "same_entity":
                errors.append(f"top500_status/{label}的listed必须有名次、入选实体且relationship_to_target为same_entity")
        elif status == "group_listed":
            relationship_source_ids = item.get("relationship_source_ids", [])
            relationship_evidence = item.get("relationship_evidence")
            if not isinstance(item.get("rank"), int) or not str(item.get("listed_entity", "")).strip() or relationship not in {"parent_group", "ultimate_group"}:
                errors.append(f"top500_status/{label}的group_listed必须有名次、集团实体及集团关系")
            _validate_e_sources(relationship_source_ids, report_source_ids, f"top500_status/{label}/集团关系", errors)
            if not isinstance(relationship_evidence, dict):
                errors.append(f"top500_status/{label}/集团关系必须提供结构化relationship_evidence")
            else:
                claim = str(relationship_evidence.get("claim", "")).strip()
                target = str(data.get("entity_resolution", {}).get("analysis_entity", "")).strip()
                listed_entity = str(item.get("listed_entity", "")).strip()
                if not claim or not str(relationship_evidence.get("as_of_date", "")).strip() or target not in claim or listed_entity not in claim:
                    errors.append(f"top500_status/{label}/集团关系证据必须同时点名研究对象、入选集团和证据时点")
                evidence_ids = relationship_evidence.get("source_ids", [])
                _validate_e_sources(evidence_ids, report_source_ids, f"top500_status/{label}/集团关系证据", errors)
                for source_id in evidence_ids if isinstance(evidence_ids, list) else []:
                    used_in = str(sources.get(str(source_id), {}).get("used_in", ""))
                    if not re.search(r"股权|控制|集团关系|主体关系", used_in):
                        errors.append(f"top500_status/{label}/集团关系来源{source_id}未声明用于股权、控制或集团关系核验")
        elif status == "not_listed":
            if relationship != "not_applicable" or item.get("rank") is not None or item.get("listed_entity") is not None:
                errors.append(f"top500_status/{label}的not_listed必须使用not_applicable关系，且名次和入选实体必须为空")
        elif status == "research_incomplete":
            if not str(item.get("reason", "")).strip() or item.get("rank") is not None or item.get("listed_entity") is not None:
                errors.append(f"top500_status/{label}的research_incomplete必须说明reason，且不得填写名次或入选实体")
    return errors


def _has_unsupported_transaction_claim(value: str) -> bool:
    remaining = NEGATED_TRANSACTION_TERMS.sub("", value)
    return bool(TRANSACTION_TERMS.search(remaining))


GENERIC_REPRESENTATIVE_NAMES = {
    "原料生产与初加工主体", "食品包装材料生产主体", "食品制造装备与检测服务主体",
    "零售终端", "餐饮经营主体", "食品加工企业", "上游企业", "下游企业",
    "相关企业", "行业企业", "供应商", "客户", "合作伙伴",
}
GENERIC_REPRESENTATIVE_PATTERN = re.compile(
    r"^(?:原料|材料|设备|渠道|零售|餐饮|食品|行业|上游|下游|相关).*(?:主体|企业|机构|平台|终端|供应商|客户)$"
)


def _is_generic_representative_name(value: object) -> bool:
    name = str(value or "").strip()
    return not name or name in GENERIC_REPRESENTATIVE_NAMES or bool(GENERIC_REPRESENTATIVE_PATTERN.fullmatch(name))


def validate_industry_chain(data: dict, report_source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    chain = data.get("industry_chain", {})
    if not isinstance(chain, dict):
        return ["industry_chain必须为对象"]
    required = ("positioning", "peer_enterprises", "upstream", "downstream", "industry_common_needs")
    for field in required:
        if field not in chain:
            errors.append(f"industry_chain缺少{field}")
    for forbidden in ("cluster_implications", "investment_lead"):
        if forbidden in chain:
            errors.append(f"industry_chain禁止{forbidden}")
    positioning = chain.get("positioning", {})
    if not isinstance(positioning, dict) or not str(positioning.get("summary", "")).strip():
        errors.append("industry_chain.positioning.summary不能为空")
    peers = chain.get("peer_enterprises", [])
    if not isinstance(peers, list) or not 3 <= len(peers) <= 6:
        errors.append("peer_enterprises必须为3-6项")
    for peer in peers if isinstance(peers, list) else []:
        if not isinstance(peer, dict) or any(not str(peer.get(field, "")).strip() for field in ("name", "core_business", "scale_or_position", "similarity", "reason")):
            errors.append("peer_enterprises缺少必填说明字段")
            continue
        if not isinstance(peer.get("similarity_dimensions"), list) or len(peer["similarity_dimensions"]) < 2:
            errors.append("peer_enterprises的similarity_dimensions至少两项")
        _validate_e_sources(peer.get("source_ids", []), report_source_ids, "peer_enterprises", errors)
    for section in ("upstream", "downstream"):
        entries = chain.get(section, [])
        if not isinstance(entries, list) or not 3 <= len(entries) <= 6:
            errors.append(f"industry_chain.{section}必须为3-6项")
            continue
        for entry in entries:
            if not isinstance(entry, dict) or any(not str(entry.get(field, "")).strip() for field in ("activity", "function", "relationship_scope")):
                errors.append(f"industry_chain.{section}缺少activity、function或relationship_scope")
                continue
            representatives = entry.get("representative_enterprises")
            if not isinstance(representatives, list) or not representatives:
                errors.append(f"industry_chain.{section}缺少representative_enterprises")
                continue
            claim_text = [str(entry.get("relationship_scope", ""))]
            for representative in representatives:
                if not isinstance(representative, dict) or not str(representative.get("name", "")).strip():
                    errors.append(f"industry_chain.{section}的representative_enterprises必须为含name和source_ids的对象")
                    continue
                if _is_generic_representative_name(representative.get("name")):
                    errors.append(f"industry_chain.{section}代表企业不得使用行业类别或占位词：{representative.get('name')}")
                _validate_e_sources(representative.get("source_ids", []), report_source_ids, "representative_enterprises", errors)
                claim_text.extend(str(representative.get(field, "")) for field in ("name", "note"))
            if not entry.get("transaction_evidence") and any(_has_unsupported_transaction_claim(value) for value in claim_text):
                errors.append(f"industry_chain.{section}未提供transaction_evidence，不得声称供应商、客户或合作伙伴；需直接交易证据")
            transaction_evidence = entry.get("transaction_evidence")
            if transaction_evidence is not None:
                if not isinstance(transaction_evidence, dict) or not str(transaction_evidence.get("relationship", "")).strip() or not str(transaction_evidence.get("evidence_text", "")).strip() or not str(transaction_evidence.get("as_of_date", "")).strip():
                    errors.append(f"industry_chain.{section}.transaction_evidence必须包含relationship、evidence_text、as_of_date和source_ids")
                else:
                    evidence_ids = transaction_evidence.get("source_ids", [])
                    _validate_e_sources(evidence_ids, report_source_ids, f"industry_chain.{section}.transaction_evidence", errors)
                    relationship_text = str(transaction_evidence.get("relationship", ""))
                    evidence_text = str(transaction_evidence.get("evidence_text", ""))
                    if not TRANSACTION_TERMS.search(relationship_text + evidence_text):
                        errors.append(f"industry_chain.{section}.transaction_evidence未说明具体交易关系")
                    for source_id in evidence_ids if isinstance(evidence_ids, list) else []:
                        used_in = str({str(item.get('id', '')).strip(): item for item in data.get('sources', [])}.get(str(source_id), {}).get("used_in", ""))
                        if not re.search(r"交易关系|供应商|客户|采购|经销|合作", used_in):
                            errors.append(f"industry_chain.{section}.transaction_evidence来源{source_id}未声明用于直接交易关系核验")
        activities = [str(entry.get("activity", "")).strip() for entry in entries if isinstance(entry, dict)]
        if len(set(activities)) != len(activities):
            errors.append(f"industry_chain.{section}不得用重复activity凑足3-6项")
    needs = chain.get("industry_common_needs", [])
    if not isinstance(needs, list) or not 3 <= len(needs) <= 6:
        errors.append("industry_common_needs必须为3-6项")
    for need in needs if isinstance(needs, list) else []:
        if not isinstance(need, dict) or not str(need.get("need", "")).strip() or not str(need.get("basis", "")).strip():
            errors.append("industry_common_needs缺少need或basis")
            continue
        if need.get("status") != "industry_inference":
            errors.append("industry_common_needs的status必须为industry_inference")
        _validate_e_sources(need.get("source_ids", []), report_source_ids, "industry_common_needs", errors)
    need_names = [str(need.get("need", "")).strip() for need in needs if isinstance(need, dict)]
    if len(set(need_names)) != len(need_names):
        errors.append("industry_common_needs不得用重复need凑足3-6项")
    return errors


def _validate_e_sources(source_ids: object, report_source_ids: set[str], label: str, errors: list[str]) -> None:
    if not isinstance(source_ids, list) or not source_ids:
        errors.append(f"{label}缺少有效E类source_ids")
        return
    for source_id in source_ids:
        if source_id not in report_source_ids or not str(source_id).startswith("E"):
            errors.append(f"{label}引用无效E类来源：{source_id}")


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
        if outcome in {"not_triggered", "not_applicable", "no_current_policy", "research_incomplete"} and not str(item.get("next_evidence", "")).strip():
            errors.append(f"{label}: 缺少未触发、不适用、无政策或未完成检索的原因及下一步核实事项")
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


def _svg_text_lines(value: str, limit: float, max_lines: int = 0) -> list[str]:
    """Wrap mixed Chinese/Latin labels before emitting SVG text nodes.

    When ``max_lines`` is positive the wrapped output is truncated to that many
    visual lines and an ellipsis is appended to the final line so callers can
    guarantee that long labels never inflate node heights or overlap neighbours.
    """
    raw_lines = _wrap_svg_text_lines(value, limit)
    if max_lines <= 0 or len(raw_lines) <= max_lines:
        return raw_lines
    truncated = raw_lines[:max_lines]
    last = truncated[-1]
    if last.endswith("…"):
        pass  # already truncated marker
    elif len(last) > 1:
        truncated[-1] = last[:-1] + "…"
    else:
        truncated[-1] = "…"
    return truncated


def _wrap_svg_text_lines(value: str, limit: float) -> list[str]:
    """Wrap mixed Chinese/Latin labels before emitting SVG text nodes."""
    lines: list[str] = []
    current = ""
    current_width = 0.0
    for character in str(value):
        width = 0.58 if ord(character) < 128 else 1.0
        if current and current_width + width > limit:
            lines.append(current)
            current, current_width = character, width
        else:
            current += character
            current_width += width
    if current:
        lines.append(current)
    if len(lines) > 1 and len(lines[-1]) == 1 and len(lines[-2]) > 1:
        # Avoid an orphan Chinese character on its own visual line by moving
        # one character from the preceding line into the final line.
        lines[-1] = lines[-2][-1] + lines[-1]
        lines[-2] = lines[-2][:-1]
    return lines or [""]


def _svg_text(class_name: str, x: int, first_y: int, lines: list[str], line_height: int) -> str:
    spans = "".join(
        f'<tspan x="{x}" y="{first_y + index * line_height}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'<text class="{class_name}" text-anchor="middle">{spans}</text>'


def equity_svg(equity: dict) -> str:
    """Build a responsive, wrapped ownership chart that cannot escape its panel."""
    nodes = equity["nodes"]
    if not nodes or not equity.get("edges"):
        return ""
    levels: dict[int, list[dict]] = {}
    node_width, horizontal_gap, margin, max_columns = 250, 30, 55, 2
    node_layout: dict[str, dict] = {}
    for node in nodes:
        levels.setdefault(int(node.get("level", 0)), []).append(node)
        name_lines = _svg_text_lines(node["name"], 22, max_lines=2)
        detail_lines = _svg_text_lines(f'{node["entity_type"]}｜{node["role"]}', 18, max_lines=2)
        node_layout[node["id"]] = {
            "name_lines": name_lines,
            "detail_lines": detail_lines,
            "height": 28 + len(name_lines) * 18 + 5 + len(detail_lines) * 16,
        }

    width = max(640, margin * 2 + max_columns * node_width + (max_columns - 1) * horizontal_gap)
    positions: dict[str, tuple[int, int]] = {}
    cursor_y = 60
    for _, items in sorted(levels.items()):
        for row_start in range(0, len(items), max_columns):
            row = items[row_start:row_start + max_columns]
            row_height = max(node_layout[node["id"]]["height"] for node in row)
            occupied = len(row) * node_width + (len(row) - 1) * horizontal_gap
            start_x = (width - occupied) // 2 + node_width // 2
            for index, node in enumerate(row):
                positions[node["id"]] = (start_x + index * (node_width + horizontal_gap), cursor_y + row_height // 2)
            cursor_y += row_height + (36 if row_start + max_columns < len(items) else 0)
        cursor_y += 92
    height = max(300, cursor_y - 32)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" role="img">', '<style>.n{fill:#fff;stroke:#4b5563;stroke-width:1.5}.t{font:14px Arial,"Microsoft YaHei",sans-serif;fill:#111827}.s{font:12px Arial,"Microsoft YaHei",sans-serif;fill:#4b5563}.e{stroke:#6b7280;stroke-width:1.5}.l{font:12px Arial,"Microsoft YaHei",sans-serif;fill:#374151;paint-order:stroke;stroke:#f5f9f9;stroke-width:4px;stroke-linejoin:round}</style>']
    relationship_groups: dict[tuple[str, str], list[dict]] = {}
    for edge in equity["edges"]:
        relationship_groups.setdefault((edge["from"], edge["relationship"]), []).append(edge)
        x1, y1 = positions[edge["from"]]; x2, y2 = positions[edge["to"]]
        source_height = node_layout[edge["from"]]["height"]
        target_height = node_layout[edge["to"]]["height"]
        parts.append(f'<line class="e" x1="{x1}" y1="{y1 + source_height // 2}" x2="{x2}" y2="{y2 - target_height // 2}"/>')
    for (source_id, relationship), grouped_edges in relationship_groups.items():
        x1, y1 = positions[source_id]
        source_height = node_layout[source_id]["height"]
        if len(grouped_edges) > 1:
            label_x, label_y = x1, y1 + source_height // 2 + 27
        else:
            edge = grouped_edges[0]
            x2, y2 = positions[edge["to"]]
            label_x = (x1 + x2) // 2
            label_y = (y1 + source_height // 2 + y2 - node_layout[edge["to"]]["height"] // 2) // 2
        label_lines = _svg_text_lines(relationship, 18, max_lines=2)
        parts.append(_svg_text("l", label_x, label_y - (len(label_lines) - 1) * 7, label_lines, 14))
    for node in nodes:
        x, y = positions[node["id"]]
        layout = node_layout[node["id"]]
        node_height = layout["height"]
        top = y - node_height // 2
        parts.append(f'<rect class="n" x="{x-node_width//2}" y="{top}" width="{node_width}" height="{node_height}" rx="8"/>')
        parts.append(_svg_text("t", x, top + 20, layout["name_lines"], 18))
        detail_start = top + 28 + len(layout["name_lines"]) * 18 + 12
        parts.append(_svg_text("s", x, detail_start, layout["detail_lines"], 16))
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
