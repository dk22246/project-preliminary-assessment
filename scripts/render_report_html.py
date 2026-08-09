"""Render the assessment report as a stable, print-first A4 HTML document."""
from __future__ import annotations

import argparse
from html import escape
from pathlib import Path

from report_core import equity_svg, financial_change_notes, financial_headers, load_data, validate_report_data, validate_text


CSS = r'''
/* === TEMPLATE: sanya-cbd-editorial (print-first report, not a slide deck) === */
:root{--ink:#172a45;--text:#26384e;--muted:#66778a;--accent:#0b6c73;--accent-soft:#e8f1f1;--line:#bdcbd4;--paper:#fff;--canvas:#eef2f4;--font-body:"Microsoft YaHei","Microsoft YaHei UI","PingFang SC",sans-serif;--font-heading:"Microsoft YaHei","Microsoft YaHei UI","PingFang SC",sans-serif}
@page{size:A4;margin:17mm 15mm 18mm 17mm;@bottom-center{content:counter(page);font:9pt "Microsoft YaHei";color:#6a7b8b}}
*{box-sizing:border-box}html{background:var(--canvas)}body{margin:0;background:var(--paper);color:var(--text);font-family:var(--font-body);font-size:10.5pt;line-height:1.62}main{max-width:210mm;margin:0 auto;background:var(--paper);padding:0 0 1mm}h1,h2,h3,p{margin-top:0}p{margin-bottom:8pt;text-align:justify;text-indent:2em}h1{margin-bottom:9pt;color:var(--ink);font-family:var(--font-heading);font-size:18pt;line-height:1.25;font-weight:700;letter-spacing:.01em}h2{margin:13pt 0 6pt;color:var(--ink);font-size:13.5pt;line-height:1.35;font-weight:700;break-after:avoid}h3{margin:11pt 0 5pt;color:var(--accent);font-size:11pt;font-weight:700;break-after:avoid}
/* Cover and contents deliberately use restrained report typography. */
.cover{min-height:260mm;display:flex;align-items:center;padding:22mm 20mm;position:relative;background:linear-gradient(120deg,#f1f7f7 0%,#fff 52%,#f7fafb 100%)}.cover::before{content:"";position:absolute;top:18mm;bottom:18mm;left:17mm;width:5px;background:var(--accent)}.cover-inner{max-width:145mm;padding-left:14mm}.cover-kicker{margin:0 0 9mm;text-indent:0;color:var(--accent);font-size:10pt;font-weight:700;letter-spacing:.1em}.cover h1{margin:0 0 12mm;font-size:27pt;line-height:1.28;letter-spacing:.02em}.cover-meta{display:grid;gap:5pt;font-size:11pt}.cover-meta p{margin:0;text-indent:0}.cover-meta strong{color:var(--ink)}.cover-stamp{display:inline-block;margin-top:12mm;padding:3pt 8pt;border:1px solid var(--accent);color:var(--accent);font-size:8.5pt;letter-spacing:.08em}
.toc{break-before:page;page-break-before:always;page-break-after:always;padding:13mm 17mm}.toc h1{font-size:22pt;margin-bottom:8pt}.toc-intro{margin:0 0 14pt;color:var(--muted);font-size:9.5pt;text-indent:0}.toc-grid{display:grid;grid-template-columns:1fr 1fr;gap:4pt 18pt}.toc a{display:grid;grid-template-columns:25pt 1fr 12pt;gap:6pt;align-items:center;min-height:30pt;padding:4pt 0;border-bottom:1px solid var(--line);color:var(--ink);font-size:11pt;text-decoration:none}.toc-index{color:var(--accent);font-weight:700}.toc-arrow{color:var(--accent);font-weight:700;text-align:right}@media screen{.toc a:hover{color:var(--accent);border-bottom-color:var(--accent)}}
/* Let the report flow naturally; headings never detach from following content. */
.report-section{padding:0 17mm}.section-head{margin:16pt 0 10pt;padding:0 0 7pt;border-bottom:2px solid var(--accent);break-after:avoid;page-break-after:avoid}.section-head h1{margin:0}.section-mark{display:none}
/* Fixed-layout tables prevent column drift and visual overflow. */
table.report-table{width:100%;table-layout:fixed;border-collapse:collapse;margin:7pt 0 13pt;font-size:9.2pt;line-height:1.48;break-inside:auto}table.report-table th,table.report-table td{border:1px solid var(--line);padding:6pt 6.5pt;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}.financial-table th,.financial-table td{min-width:0;max-width:100%;overflow:hidden}table.report-table th{background:var(--accent-soft);color:var(--ink);font-weight:700;text-align:center;vertical-align:middle}table.report-table tbody tr:nth-child(even){background:#f8fafb}table.report-table tr{break-inside:avoid;page-break-inside:avoid}table.report-table td:first-child{text-align:center;vertical-align:middle}.wide{font-size:8.55pt}.financial-table td:nth-child(1),.financial-table td:nth-child(2),.financial-table td:nth-child(4),.financial-table td:nth-child(9){white-space:nowrap;text-align:center;font-variant-numeric:tabular-nums}.financial-table td:nth-child(3),.financial-table td:nth-child(5){white-space:normal;overflow-wrap:anywhere;word-break:break-word;text-align:center;font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums}.support-table td:first-child{white-space:nowrap;font-variant-numeric:tabular-nums}.source-table{font-size:8.45pt}.source-table a{color:#006e7a;text-decoration:underline;text-underline-offset:2px;word-break:break-all}.svg-wrap{margin:7pt 0 12pt;padding:8pt;border:1px solid var(--line);background:#f5f9f9;overflow:hidden}.svg-wrap svg{display:block;width:100%;max-width:100%;height:auto}.equity-conflicts{margin:9pt 0 13pt;padding:8pt 10pt;border:1px solid #d4b16a;border-left:4px solid #b7791f;background:#fffaf0}.equity-conflicts h3{margin:0 0 6pt;color:#7a4b00}.equity-conflict{padding:6pt 0;border-top:1px solid #ead7ae;break-inside:avoid}.equity-conflict:first-of-type{border-top:0}.equity-conflict h4{margin:0 0 4pt;color:var(--ink);font-size:10pt}.equity-conflict p{margin:2pt 0;text-indent:0;font-size:8.9pt;line-height:1.48}.equity-conflict .conflict-status{display:inline-block;margin-left:5pt;padding:1pt 5pt;border-radius:8pt;background:#f4e7c9;color:#7a4b00;font-size:7.8pt;vertical-align:1pt}.summary-note{margin:8pt 0 12pt;padding:8pt 10pt;border-left:3px solid var(--accent);background:#f0f7f7;color:var(--text);font-size:9.5pt;text-indent:0}.table-note{margin:-5pt 0 10pt;padding:6pt 8pt;border-left:2px solid var(--accent);background:#f5f9f9;color:var(--muted);font-size:8.7pt;line-height:1.45;text-indent:0}
/* Policy matching is a decision table. Internal research controls remain in
   validation data and never displace the actual policy results in the report. */
.policy-note{margin:0 0 7pt;color:var(--muted);font-size:8.8pt;line-height:1.45;text-indent:0}.policy-match-table{font-size:8.55pt}.policy-match-table td:first-child{text-align:left;vertical-align:top}.policy-match-table td:nth-child(2){white-space:pre-line}.policy-match-table a{color:#006e7a;font-weight:700;text-decoration:underline;text-underline-offset:2px}.policy-ref{display:block;margin-top:2pt;color:var(--muted);font-size:7.8pt;line-height:1.35}.policy-match-table .status{display:block;font-weight:700;color:var(--accent);line-height:1.4}.pending-policy-table{font-size:8.65pt}.pending-policy-table td:first-child{text-align:left;vertical-align:top}
.catalog-summary,.equity-evidence-summary{margin:7pt 0 9pt;padding:7pt 9pt;border-left:3px solid var(--accent);background:#f0f7f7;text-indent:0}.catalog-table td:nth-child(2){font-weight:700;color:var(--accent)}.catalog-table td:first-child{text-align:left;vertical-align:top}
@media screen{body{padding:24px 0;background:var(--canvas)}main{box-shadow:0 8px 28px rgba(23,42,69,.12)}.report-section{animation:fade-in .2s ease both}}@keyframes fade-in{from{opacity:.96;transform:translateY(2px)}to{opacity:1;transform:none}}@media (max-width:760px){body{padding:0}.toc-grid{grid-template-columns:1fr}.cover{min-height:100vh}.cover h1{font-size:21pt}.report-section,.toc{padding-left:11mm;padding-right:11mm}.wide{font-size:7.8pt}}@media (prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}@media print{html,body{background:#fff}main{max-width:none;box-shadow:none}.cover{min-height:260mm}.report-section{padding-left:0;padding-right:0}.toc{padding-left:0;padding-right:0}}
'''


def validate_table_shape(headers: list[str], rows: list[list[str]], widths: list[int] | None = None) -> None:
    if widths and (len(widths) != len(headers) or sum(widths) != 100):
        raise ValueError(f"表格列宽配置无效：表头 {len(headers)} 列，列宽 {len(widths)} 列，合计 {sum(widths)}%")
    for index, row in enumerate(rows, start=1):
        if len(row) != len(headers):
            raise ValueError(f"表格第 {index} 行列数不匹配：表头 {len(headers)} 列，数据 {len(row)} 列")


def report_table(headers: list[str], rows: list[list[str]], table_class: str = "", widths: list[int] | None = None) -> str:
    validate_table_shape(headers, rows, widths)
    cols = "" if not widths else "<colgroup>" + "".join(f'<col style="width:{width}%">' for width in widths) + "</colgroup>"
    head = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(item))}</td>" for item in row) + "</tr>" for row in rows)
    return f'<table class="report-table {escape(table_class)}">{cols}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def source_table(rows: list[dict[str, str]]) -> str:
    header = ["编号", "资料类型", "资料名称", "发布主体", "发布日期", "具体网址或文件定位", "主要使用位置"]
    rendered = []
    for item in rows:
        location = str(item.get("location", ""))
        safe_location = escape(location)
        if location.startswith(("https://", "http://")):
            safe_location = f'<a href="{safe_location}">{safe_location}</a>'
        rendered.append([item.get(k, "") for k in ("id", "type", "name", "issuer", "date")] + [safe_location, item.get("used_in", "")])
    widths = (6, 7, 19, 18, 9, 29, 12)
    validate_table_shape(header, rendered, list(widths))
    head = "".join(f"<th>{escape(item)}</th>" for item in header)
    body = "".join("<tr>" + "".join(f"<td>{value if i == 5 else escape(str(value))}</td>" for i, value in enumerate(row)) + "</tr>" for row in rendered)
    columns = "".join(f'<col style="width:{width}%">' for width in widths)
    return f'<table class="report-table source-table"><colgroup>{columns}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def policy_reporting_groups(policies: list[dict]) -> list[list[dict]]:
    """Merge a benefit's primary policy and its operating notice into one row."""
    groups: dict[str, list[dict]] = {}
    for item in policies:
        group = str(item.get("report_group") or item.get("source_id") or item.get("name"))
        groups.setdefault(group, []).append(item)
    return list(groups.values())


def policy_match_table(policies: list[dict]) -> str:
    """Render a concise, decision-facing policy/tool and reason table."""
    headers = ["匹配政策或工具", "匹配原因"]
    rows = []
    for group in policy_reporting_groups(policies):
        lead = group[0]
        url = escape(str(lead.get("source_url", "")), quote=True)
        name = escape(str(lead.get("report_title") or lead.get("name", "未命名政策")))
        references = "；".join(
            f'<a href="{escape(str(item.get("source_url", "")), quote=True)}">{escape(str(item.get("document_number", "未公开披露")))}（{escape(str(item.get("source_id", "P")))}）</a>'
            for item in group
        )
        policy = f'<a href="{url}">{name}</a><span class="policy-ref">政策依据：{references} · 官方原文</span>'
        rows.append([
            policy,
            escape(str(lead.get("report_reason", "未公开披露"))),
        ])
    widths = (34, 66)
    validate_table_shape(headers, rows, list(widths))
    head = "".join(f"<th>{escape(item)}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>" for row in rows)
    columns = "".join(f'<col style="width:{width}%">' for width in widths)
    return f'<table class="report-table wide policy-match-table"><colgroup>{columns}</colgroup><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def equity_conflict_disclosures(items: list[dict]) -> str:
    """Keep uncertain platform differences out of the graph and explain them in prose."""
    if not items:
        return ""
    blocks = []
    for item in items:
        status = "已核实" if item.get("status") == "resolved" else "待核实"
        blocks.append(
            '<article class="equity-conflict">'
            f'<h4>{escape(str(item.get("title", "未命名差异")))}<span class="conflict-status">{status}</span></h4>'
            f'<p><strong>差异情况：</strong>{escape(str(item.get("difference", "未说明")))}</p>'
            f'<p><strong>可能原因：</strong>{escape(str(item.get("reason", "未说明")))}</p>'
            f'<p><strong>本报告处理口径：</strong>{escape(str(item.get("adopted_basis", "未说明")))}</p>'
            f'<p><strong>对招商判断的影响：</strong>{escape(str(item.get("impact", "未说明")))}</p>'
            f'<p><strong>后续核实：</strong>{escape(str(item.get("next_action", "未说明")))}</p>'
            f'<p><strong>证据来源：</strong>{escape("、".join(str(source_id) for source_id in item.get("evidence_source_ids", [])))}</p>'
            '</article>'
        )
    return '<div class="equity-conflicts"><h3>股权数据差异说明</h3>' + "".join(blocks) + "</div>"


def equity_evidence_summary(equity: dict) -> str:
    summary = equity.get("evidence_summary", {})
    title = str(summary.get("display_source_title", "需补充股权来源"))
    source_id = str(summary.get("display_source_id", "E?"))
    as_of_date = str(summary.get("as_of_date", "需补充数据时点"))
    return (
        '<div class="equity-evidence-summary"><strong>股权来源：</strong>'
        + escape(f"{title}（{source_id}），数据时点{as_of_date}。")
        + "</div>"
    )


def industry_position_text(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("statement", "本轮公开检索未发现可靠行业地位数据，需企业补充。"))
    return str(value)


def encouraged_industry_table(assessment: dict) -> str:
    labels = {"direct_match": "明确符合", "potential_match": "存在相近可能", "no_match": "暂未发现明确匹配"}
    rows = []
    for item in assessment.get("business_assessments", []):
        matched = []
        for candidate in item.get("matched_items", []):
            matched.append(
                f"{candidate.get('catalog_item_no', '—')}．{candidate.get('catalog_item', '未注明条目')}"
                f"｜{candidate.get('detailed_item', '未注明细化目录')}"
            )
        matched_text = "；".join(matched) or "完成三条目录路径检索后，未发现可合理对应的具体条目"
        verification = str(item.get("verification_needed", "无"))
        rows.append([
            str(item.get("business", "未命名业务")),
            labels.get(str(item.get("judgment")), "研究未完成"),
            matched_text,
            str(item.get("reason", "未说明")),
            verification,
        ])
    summary = '<p class="catalog-summary"><strong>总体判断：</strong>' + escape(str(assessment.get("summary", "未说明"))) + '</p>'
    return summary + report_table(
        ["企业业务", "匹配结论", "对应目录条目", "判断依据", "相近可能或待核事项"],
        rows,
        "wide catalog-table",
        [15, 11, 25, 29, 20],
    )


def section(title: str, body: str) -> str:
    anchor = title.split("、", 1)[0]
    return f'<section id="s{anchor}" class="report-section"><div class="section-head"><h1>{escape(title)}</h1></div>{body}</section>'


def paragraph(value: str) -> str:
    return f"<p>{escape(value)}</p>"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    data = load_data(args.report_data)
    errors = validate_report_data(data) + validate_text(data)
    if errors:
        raise SystemExit("\n".join(errors))
    template = data["meta"].get("html_template", "sanya-cbd-editorial")
    if template != "sanya-cbd-editorial":
        raise SystemExit(f"不支持的 HTML 模板：{template}")

    entity = data["entity_resolution"]
    toc = [("一、项目整体判断", "一"), ("二、企业基本情况", "二"), ("三、近三年经营数据", "三"), ("四、风险与合规情况", "四"), ("五、三亚落地业务及落地方式", "五"), ("六、企业政策匹配", "六"), ("七、综合评估", "七"), ("八、参考资料", "八")]
    sections = [section("一、项目整体判断", report_table(["研判事项", "初步结论"], data["overall_judgment"], "judgment-table", [16, 84]))]
    entity_rows = [[label, entity.get(key, "未公开披露")] for label, key in [("用户输入名称", "user_input"), ("名称性质", "name_type"), ("对应法律主体", "legal_entity"), ("证券简称及代码", "security"), ("直接控股股东", "direct_shareholder"), ("最终控制方", "ultimate_controller"), ("核心经营主体", "core_operators"), ("本报告分析主体", "analysis_entity"), ("财务数据口径", "financial_scope"), ("风险检索范围", "risk_scope")]]
    business_rows = [[item[key] for key in ("segment", "products", "entity", "revenue_model", "footprint", "sanya_fit")] for item in data["businesses"]]
    basic = "<h2>（一）企业主体认定</h2>" + report_table(["认定事项", "认定结果"], entity_rows, "entity-table", [16, 84]) + "<h2>（二）股权架构拆解</h2><div class=\"svg-wrap\">" + equity_svg(data["equity"]) + "</div>" + paragraph(entity.get("equity_summary", "需企业补充")) + equity_evidence_summary(data["equity"]) + equity_conflict_disclosures(data["equity"].get("conflict_disclosures", [])) + "<h2>（三）主要业务及产品拆解</h2>" + report_table(["业务板块", "主要产品或服务", "主要承载主体", "客户及收入来源", "国内外业务布局", "与三亚的潜在结合点"], business_rows, "wide business-table", [12, 22, 16, 18, 14, 18]) + "<h2>（四）海南自由贸易港鼓励类产业目录匹配</h2>" + encouraged_industry_table(data["encouraged_industry_assessment"]) + "<h2>（五）行业地位及竞争位置</h2>" + paragraph(industry_position_text(data.get("industry_position", {}))) + "<h2>（六）上下游及国内外业务</h2>" + paragraph(data.get("upstream_downstream", "本轮公开检索未发现可靠数据，需企业补充。"))
    sections.append(section("二、企业基本情况", basic))
    financial_rows = [[item.get(key, "未公开披露") for key in ("year", "revenue", "revenue_change", "profit", "profit_change", "tax_value", "tax_basis", "government_support", "source")] for item in data["financials"]]
    support_rows = [[item.get(key, "未公开披露") for key in ("year", "name", "department", "amount", "purpose", "conditions", "source")] for item in data.get("government_support", [])] or [["—", "本轮公开检索未发现可确认的政府补助明细", "—", "—", "需企业补充", "需企业补充", "—"]]
    notes = financial_change_notes(data["financials"])
    note_html = "" if not notes else '<p class="table-note">注：' + escape("；".join(notes)) + "</p>"
    finance = "<h2>（一）营业收入、利润、纳税及政府补助情况</h2>" + report_table(financial_headers(data["meta"]), financial_rows, "wide financial-table", [10, 11, 11, 11, 11, 9, 10, 20, 7]) + note_html + "<h3>政府补助及财政支持明细表</h3>" + report_table(["年度", "补助或支持名称", "发放部门", "金额", "对应项目或用途", "附带条件或履约要求", "来源编号"], support_rows, "wide support-table", [8, 16, 12, 12, 16, 28, 8]) + "<h2>（二）经营数据分析</h2>" + paragraph(data.get("financial_analysis", "需企业补充"))
    sections.append(section("三、近三年经营数据", finance))
    risk = data["risks"]
    risk_body = "<h2>（一）行政处罚及监管风险</h2>" + report_table(["时间", "风险类型", "具体事项", "处理结果", "是否已整改", "对招商的影响", "来源编号"], risk.get("regulatory", []), "wide risk-table", [6, 12, 33, 10, 10, 21, 8]) + "<h2>（二）诉讼、执行及失信情况</h2>" + report_table(["时间", "事项类型", "涉及对象或金额", "当前状态", "对招商的影响", "来源编号"], risk.get("litigation", []), "wide risk-table", [9, 18, 32, 16, 17, 8]) + "<h2>（三）风险综合判断</h2>" + paragraph(risk.get("summary", "需企业补充"))
    sections.append(section("四、风险与合规情况", risk_body))
    landing_rows = [[item[key] for key in ("business", "fact_basis", "sanya_path", "value", "feasibility")] for item in data["landing_businesses"]]
    sections.append(section("五、三亚落地业务及落地方式", report_table(["建议落地业务", "企业现有事实基础", "三亚具体承接方式", "可形成的业务及价值", "可行性"], landing_rows, "wide landing-table", [14, 25, 29, 24, 8])))
    policy_body = '<h2>（一）重点政策匹配清单</h2><p class="policy-note">本节依据企业已公开的业务、组织和境内外布局，展示在三亚承接相邻经营活动时可重点沟通的现行政策或办理工具。政策名称直接说明利益或功能，匹配原因同时交代企业事实和触发条件；完整检索、失效政策及排除理由保留在后台台账。</p>' + policy_match_table(data["policies"])
    sections.append(section("六、企业政策匹配", policy_body))
    sections.append(section("七、综合评估", '<div class="summary-note">' + escape(data.get("comprehensive_assessment", "需企业补充")) + "</div>"))
    visible_policy_sources = {str(item.get("source_id", "")) for item in data["policies"]}
    visible_policy_sources.update(str(item.get("source_id", "")) for item in data["encouraged_industry_assessment"].get("catalogs_checked", []))
    for item in data["encouraged_industry_assessment"].get("business_assessments", []):
        visible_policy_sources.update(str(source_id) for source_id in item.get("catalog_source_ids", []))
    visible_sources = [item for item in data["sources"] if not str(item.get("id", "")).startswith("P") or str(item.get("id", "")) in visible_policy_sources]
    sections.append(section("八、参考资料", source_table(visible_sources)))
    toc_html = "".join(f'<a href="#s{anchor}"><span class="toc-index">{anchor}</span><span>{escape(title.split("、", 1)[1])}</span><span class="toc-arrow">→</span></a>' for title, anchor in toc)
    cover = '<section class="cover"><div class="cover-inner"><p class="cover-kicker">三亚中央商务区 · 招商前期研判</p><h1>' + escape(data["meta"]["report_title"]) + '</h1><div class="cover-meta"><p><strong>编制单位：</strong>' + escape(data["meta"].get("unit", "三亚中央商务区招商研判组")) + '</p><p><strong>报告性质：</strong>内部招商前期研判</p><p><strong>编制日期：</strong>' + escape(data["meta"]["generated_at"]) + '</p></div><span class="cover-stamp">内部使用</span></div></section>'
    toc_block = '<nav class="toc" aria-label="报告目录"><p class="cover-kicker">报告目录</p><h1>目录</h1><p class="toc-intro">点击章节名称可跳转至对应内容。</p><div class="toc-grid">' + toc_html + "</div></nav>"
    html = '<!doctype html><html lang="zh-CN" class="template-' + template + '"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(data["meta"]["report_title"]) + "</title><style>" + CSS + "</style></head><body><main>" + cover + toc_block + "".join(sections) + "</main></body></html>"
    Path(args.out).write_text(html, encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
