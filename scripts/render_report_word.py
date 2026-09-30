"""Optional editable Word renderer from the same report-data.json used by HTML/PDF."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys

from stdlib_docx import Document

from report_core import financial_change_notes, financial_headers, load_data, require_fixture_authorization, risk_presentation, validate_report_data, validate_text
from word_report_builder import add_body, add_cover_line, add_heading, add_native_toc_with_cache, add_standard_table, configure_report_document, try_update_fields_with_word


def format_date(value: object) -> str:
    raw = str(value)
    try:
        return datetime.fromisoformat(raw).strftime("%Y年%m月%d日")
    except ValueError:
        return raw


def rows(items, fields):
    return [[str(item.get(field, "未公开披露")) for field in fields] for item in items]


def h1(doc, title):
    doc.add_page_break()
    add_heading(doc, title, 1)


def add_equity_conflict_disclosures(doc, items):
    if not items:
        return
    add_heading(doc, "股权数据差异说明", 3)
    for item in items:
        status = "已核实" if item.get("status") == "resolved" else "待核实"
        add_body(doc, f"{item.get('title', '未命名差异')}（{status}）")
        add_body(doc, f"差异情况：{item.get('difference', '未说明')}")
        add_body(doc, f"可能原因：{item.get('reason', '未说明')}")
        add_body(doc, f"本报告处理口径：{item.get('adopted_basis', '未说明')}")
        add_body(doc, f"对招商判断的影响：{item.get('impact', '未说明')}")
        add_body(doc, f"后续核实：{item.get('next_action', '未说明')}")
        add_body(doc, "证据来源：" + "、".join(str(source_id) for source_id in item.get("evidence_source_ids", [])))


def add_equity_evidence_summary(doc, equity):
    summary = equity.get("evidence_summary", {})
    add_body(doc, f"股权来源：{summary.get('display_source_title', '需补充股权来源')}（{summary.get('display_source_id', 'E?')}），数据时点{summary.get('as_of_date', '需补充')}。")


def add_risk_section(doc, risks):
    presentation = risk_presentation(risks)
    if presentation["mode"] == "prose":
        for paragraph in presentation["paragraphs"]:
            add_body(doc, paragraph)
        return
    if presentation["regulatory"]:
        add_heading(doc, "（一）行政处罚及监管风险", 2)
        add_standard_table(doc, ["时间", "风险类型", "具体事项", "处理结果", "是否已整改", "对招商的影响", "来源编号"], presentation["regulatory"], [1.0, 1.7, 5.0, 1.5, 1.5, 3.2, 1.0])
    if presentation["litigation"]:
        add_heading(doc, "（二）诉讼、执行及失信情况", 2)
        add_standard_table(doc, ["时间", "事项类型", "涉及对象或金额", "当前状态", "对招商的影响", "来源编号"], presentation["litigation"], [1.2, 2.2, 4.8, 2.2, 4.0, 1.0])


def encouraged_industry_rows(assessment):
    labels = {"direct_match": "明确符合", "potential_match": "存在相近可能", "no_match": "暂未发现明确匹配"}
    rendered = []
    for item in assessment.get("business_assessments", []):
        matched = "；".join(
            f"{candidate.get('catalog_item_no', '—')}．{candidate.get('catalog_item', '未注明条目')}｜{candidate.get('detailed_item', '未注明细化目录')}"
            for candidate in item.get("matched_items", [])
        ) or "完成三条目录路径检索后，未发现可合理对应的具体条目"
        rendered.append([item.get("activity_name", item.get("business", "未命名经营活动")), labels.get(item.get("judgment"), "研究未完成"), matched, item.get("reason", "未说明"), item.get("verification_needed", "无")])
    return rendered


def source_ids_text(item):
    return "、".join(str(source_id) for source_id in item.get("source_ids", [])) or "未注明来源"


def top500_rows(items):
    status_labels = {"listed": "已入选", "group_listed": "集团入选", "not_listed": "未入选", "research_incomplete": "核验未完成"}
    relationship_labels = {
        "same_entity": "研究对象（同一主体）",
        "parent_group": "集团关系：研究对象的母集团",
        "ultimate_group": "集团关系：研究对象的最终控制集团",
        "not_applicable": "不适用",
    }
    rendered = []
    for item in items:
        status = str(item.get("status", "research_incomplete"))
        if status == "research_incomplete":
            ranking_result = str(item.get("reason") or "未说明核验原因")
        elif status == "not_listed":
            ranking_result = "—"
        else:
            rank = item.get("rank")
            rank_text = f"第{rank}名" if rank else "名次未披露"
            ranking_result = f"{rank_text}｜{item.get('listed_entity') or '入选主体未注明'}"
        rendered.append([
            str(item.get("ranking_label", "未命名榜单")), str(item.get("year", "未注明")),
            status_labels.get(status, "核验未完成"), ranking_result,
            relationship_labels.get(str(item.get("relationship_to_target")), "关系未注明"), source_ids_text(item),
        ])
    return rendered


def representative_enterprises_text(items):
    return "；".join(
        str(item.get("name", "未命名企业"))
        + (f"（{item.get('note')}）" if item.get("note") else "")
        + f"（来源：{source_ids_text(item)}）"
        for item in items
    ) or "本轮未发现可靠代表企业"


def industry_chain_rows(chain):
    rendered = [["产业链定位", str(chain.get("positioning", {}).get("summary", "需企业补充"))]]
    for item in chain.get("peer_enterprises", []):
        rendered.append(["同类型企业", "；".join([
            str(item.get("name", "未命名企业")), str(item.get("core_business", "未说明")),
            str(item.get("scale_or_position", "未说明")), "相似维度：" + "、".join(item.get("similarity_dimensions", [])),
            str(item.get("similarity", "未说明")), str(item.get("reason", "未说明")), "来源：" + source_ids_text(item),
        ])])
    for label, section in (("上游产业环节", "upstream"), ("下游产业及渠道", "downstream")):
        for item in chain.get(section, []):
            rendered.append([label, "；".join([
                str(item.get("activity", "未命名环节")), str(item.get("function", "未说明")),
                "代表企业：" + representative_enterprises_text(item.get("representative_enterprises", [])),
                "关系口径：" + str(item.get("relationship_scope", "未说明")),
            ])])
    for item in chain.get("industry_common_needs", []):
        rendered.append(["行业共性需求（行业推断）", "；".join([
            str(item.get("need", "未命名需求")), "行业推断", str(item.get("basis", "未说明")),
            "来源：" + source_ids_text(item), "不是企业事实，不得作为政策触发依据。",
        ])])
    return rendered


def add_industry_chain(doc, chain):
    add_standard_table(doc, ["部分", "内容"], industry_chain_rows(chain), [3.2, 12.7])


def policy_match_rows(policies):
    """Keep the editable Word table aligned with the HTML decision table."""
    groups = {}
    for item in policies:
        group = str(item.get("report_group") or item.get("source_id") or item.get("name"))
        groups.setdefault(group, []).append(item)
    rendered = []
    for group in groups.values():
        item = group[0]
        references = "；".join(f"{policy.get('document_number', '未公开披露')}（{policy.get('source_id', 'P')}）" for policy in group)
        rendered.append([
            f"{item.get('report_title') or item.get('name', '未命名政策')}\n政策依据：{references}",
            str(item.get("report_reason", "未公开披露")),
        ])
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--out", required=True)
    parser.add_argument("--equity-image")
    parser.add_argument("--fixture-mode", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    data = load_data(args.report_data)
    try:
        fixture_only = require_fixture_authorization(data, allow_fixture=args.fixture_mode)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    errors = validate_report_data(data) + validate_text(data)
    if errors:
        raise SystemExit("\n".join(errors))
    equity_has_graph = data["equity"].get("data_status") in {"available", "partial"}
    image = Path(args.equity_image) if args.equity_image else None
    if equity_has_graph and (image is None or not image.exists()):
        raise SystemExit("有股权关系时缺少股权图 PNG，Word 不得用文本框替代图形")
    doc = Document()
    configure_report_document(doc, data["meta"].get("report_short_name", "招商项目整体落地研判报告"))
    if fixture_only:
        add_cover_line(doc, "【自动化测试夹具 · 禁止交付】")
    add_cover_line(doc, data["meta"]["report_title"], title=True)
    add_cover_line(doc, f"编制单位：{data['meta'].get('unit', '三亚中央商务区管理局')}")
    add_cover_line(doc, f"编制日期：{data['meta']['generated_at']}")
    doc.add_page_break(); add_heading(doc, "目录", 1)
    add_native_toc_with_cache(doc, [(x, 1) for x in ("一、企业基本情况", "二、近三年经营数据", "三、风险与合规情况", "四、三亚落地业务及落地方式", "五、企业政策匹配", "六、综合评估", "七、参考资料")])
    h1(doc, "一、企业基本情况")
    add_heading(doc, "（一）企业主体认定与企业概况", 2)
    entity = data["entity_resolution"]
    overview = data["enterprise_overview"]
    entity_rows = [["企业主体", entity.get("legal_entity", "未公开披露")], ["成立时间", overview["established_at"]], ["注册地", overview["registered_location"]], ["企业性质", overview["listing_status"]], ["主营业务", overview["main_business"]], ["分析口径", entity.get("financial_scope", "未公开披露")]]
    add_standard_table(doc, ["基本事项", "企业情况"], entity_rows, [4.2, 11.7])
    add_body(doc, "企业概况：" + overview["profile"])
    add_body(doc, "经营表现：" + overview["operating_summary"])
    add_body(doc, "员工规模：" + overview["employee_scale"])
    industry = data.get("industry_position", {})
    if isinstance(industry, dict):
        industry_text = f"{industry.get('category', '相关行业')}品类定位：{industry.get('position', '未取得可靠排名')}；统计时点：{industry.get('period', '未注明时点')}。{industry.get('statement', '需企业补充')}"
    else:
        industry_text = str(industry or "需企业补充")
    add_body(doc, "行业地位：" + industry_text)
    add_heading(doc, "（二）500强核验", 2); add_standard_table(doc, ["榜单", "年度", "状态", "名次/入选主体", "与研究对象关系", "来源"], top500_rows(data["top500_status"]), [2.7, 1.1, 1.6, 3.3, 4.3, 1.9])
    add_heading(doc, "（三）股权架构拆解", 2)
    if equity_has_graph:
        doc.add_picture(str(image), width_cm=15); add_body(doc, entity.get("equity_summary", "需企业补充")); add_equity_evidence_summary(doc, data["equity"]); add_equity_conflict_disclosures(doc, data["equity"].get("conflict_disclosures", []))
    else:
        add_body(doc, "股权公开信息不足：" + data["equity"].get("availability_note", "本轮公开检索未发现可靠股权数据，需企业补充。"))
        add_body(doc, "本轮检索依据：" + ("、".join(str(item) for item in data["equity"].get("search_source_ids", [])) or "未记录"))
    add_heading(doc, "（四）主要业务及产品拆解", 2); add_standard_table(doc, ["业务板块", "主要产品或服务", "主要承载主体", "销售渠道", "国内外业务布局"], rows(data["businesses"], ("segment", "products", "entity", "sales_channels", "footprint")), [2.4, 3.5, 3.0, 3.8, 3.2])
    add_heading(doc, "（五）海南自由贸易港鼓励类产业目录匹配", 2); add_body(doc, "总体判断：" + data["encouraged_industry_assessment"].get("summary", "未说明")); add_standard_table(doc, ["企业具体经营活动", "匹配结论", "对应目录条目", "判断依据", "相近可能或待核事项"], encouraged_industry_rows(data["encouraged_industry_assessment"]), [2.5, 1.7, 4.0, 4.8, 3.0])
    add_heading(doc, "（六）产业链上下游", 2); add_industry_chain(doc, data["industry_chain"])
    h1(doc, "二、近三年经营数据")
    headers = financial_headers(data["meta"])
    add_heading(doc, "（一）营业收入、利润、纳税及政府补助情况", 2); add_standard_table(doc, headers, rows(data["financials"], ("year", "revenue", "revenue_change", "profit", "profit_change", "tax_value", "tax_basis", "government_support", "source")), [1.1, 1.55, 0.9, 1.45, 0.9, 1.5, 1.5, 1.6, 1.0])
    change_notes = financial_change_notes(data["financials"])
    if change_notes:
        add_body(doc, "注：" + "；".join(change_notes))
    add_heading(doc, "政府补助及财政支持明细表", 3); add_standard_table(doc, ["年度", "名称", "发放部门", "金额", "用途", "附带条件", "来源"], rows(data.get("government_support", []), ("year", "name", "department", "amount", "purpose", "conditions", "source")) or [["—", "本轮公开检索未发现可确认明细", "—", "—", "需企业补充", "需企业补充", "—"]], [1.1, 2.5, 2.0, 1.3, 3.0, 3.0, 1.0])
    add_heading(doc, "（二）经营数据分析", 2); add_body(doc, data.get("financial_analysis", "需企业补充"))
    h1(doc, "三、风险与合规情况")
    add_risk_section(doc, data["risks"])
    h1(doc, "四、三亚落地业务及落地方式"); add_standard_table(doc, ["建议落地业务", "企业现有事实基础", "三亚具体承接方式", "可形成的业务及价值", "可行性"], rows(data["landing_businesses"], ("business", "fact_basis", "sanya_path", "value", "feasibility")), [3.0, 4.0, 4.0, 4.0, 1.0])
    h1(doc, "五、企业政策匹配")
    add_heading(doc, "（一）重点政策匹配清单", 2)
    add_body(doc, "本节依据企业已公开的业务、组织和境内外布局，展示在三亚承接相邻经营活动时可重点沟通的现行政策或办理工具。完整检索、失效政策及排除理由保留在后台台账。")
    add_standard_table(doc, ["匹配政策或工具", "匹配原因"], policy_match_rows(data["policies"]), [5.2, 10.7])
    h1(doc, "六、综合评估"); add_body(doc, data.get("comprehensive_assessment", "需企业补充"))
    h1(doc, "七、参考资料"); add_standard_table(doc, ["编号", "类型", "资料名称", "发布主体", "日期", "网址或文件定位", "使用位置"], rows(data["sources"], ("id", "type", "name", "issuer", "date", "location", "used_in")), [1.0, 1.1, 3.0, 2.3, 1.4, 5.0, 2.0])
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); doc.save(out)
    try_update_fields_with_word(out); print(out); return 0


if __name__ == "__main__":
    raise SystemExit(main())
