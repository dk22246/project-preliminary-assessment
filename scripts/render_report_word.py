"""Optional editable Word renderer from the same report-data.json used by HTML/PDF."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from docx import Document
from docx.enum.text import WD_BREAK
from docx.shared import Cm

from report_core import financial_change_notes, financial_headers, load_data, validate_report_data, validate_text
from word_report_builder import add_body, add_cover_line, add_heading, add_native_toc_with_cache, add_standard_table, configure_report_document, try_update_fields_with_word


def rows(items, fields):
    return [[str(item.get(field, "未公开披露")) for field in fields] for item in items]


def h1(doc, title):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    add_heading(doc, title, 1)


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
            str(item.get("report_business") or item.get("enterprise_business", "未公开披露")),
            f"{item.get('report_title') or item.get('name', '未命名政策')}\n政策依据：{references}",
            str(item.get("report_value") or item.get("policy_value", "未公开披露")),
            f"享受前提：{item.get('report_conditions') or item.get('conditions', '未公开披露')}\n三亚承接：{item.get('report_landing_action') or item.get('landing_action', '未公开披露')}",
            str(item.get("report_judgment") or "整体落地情景下重点政策"),
        ])
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_data")
    parser.add_argument("--out", required=True)
    parser.add_argument("--equity-image", required=True)
    args = parser.parse_args()
    data = load_data(args.report_data)
    errors = validate_report_data(data) + validate_text(data)
    if errors:
        raise SystemExit("\n".join(errors))
    image = Path(args.equity_image)
    if not image.exists():
        raise SystemExit("缺少股权图 PNG，Word 不得用文本框替代图形")
    doc = Document()
    configure_report_document(doc, data["meta"].get("report_short_name", "招商项目整体落地研判报告"))
    add_cover_line(doc, data["meta"]["report_title"], title=True)
    add_cover_line(doc, f"编制单位：{data['meta'].get('unit', '三亚中央商务区招商研判组')}")
    add_cover_line(doc, f"编制日期：{data['meta']['generated_at']}")
    doc.add_page_break(); add_heading(doc, "目录", 1)
    add_native_toc_with_cache(doc.add_paragraph(), [(x, 1) for x in ("一、项目整体判断", "二、企业基本情况", "三、近三年经营数据", "四、风险与合规情况", "五、三亚落地业务及落地方式", "六、企业政策匹配", "七、综合评估", "八、参考资料")])
    h1(doc, "一、项目整体判断")
    add_standard_table(doc, ["研判事项", "初步结论"], data["overall_judgment"], [4.2, 11.7])
    h1(doc, "二、企业基本情况")
    add_heading(doc, "（一）企业主体认定", 2)
    entity = data["entity_resolution"]
    entity_rows = [[label, entity.get(key, "未公开披露")] for label, key in (("用户输入名称", "user_input"), ("名称性质", "name_type"), ("对应法律主体", "legal_entity"), ("直接控股股东", "direct_shareholder"), ("最终控制方", "ultimate_controller"), ("本报告分析主体", "analysis_entity"))]
    add_standard_table(doc, ["认定事项", "认定结果"], entity_rows, [4.2, 11.7])
    add_heading(doc, "（二）股权架构拆解", 2); doc.add_picture(str(image), width=Cm(15)); add_body(doc, entity.get("equity_summary", "需企业补充"))
    add_heading(doc, "（三）主要业务及产品拆解", 2); add_standard_table(doc, ["业务板块", "主要产品或服务", "主要承载主体", "客户及收入来源", "国内外业务布局", "与三亚的潜在结合点"], rows(data["businesses"], ("segment", "products", "entity", "revenue_model", "footprint", "sanya_fit")), [2.2, 2.6, 2.2, 2.6, 2.5, 3.8])
    add_heading(doc, "（四）行业地位及竞争位置", 2); add_body(doc, data.get("industry_position", "需企业补充"))
    add_heading(doc, "（五）上下游及国内外业务", 2); add_body(doc, data.get("upstream_downstream", "需企业补充"))
    h1(doc, "三、近三年经营数据")
    headers = financial_headers(data["meta"])
    add_heading(doc, "（一）营业收入、利润、纳税及政府补助情况", 2); add_standard_table(doc, headers, rows(data["financials"], ("year", "revenue", "revenue_change", "profit", "profit_change", "tax_value", "tax_basis", "government_support", "source")), [1.1, 1.55, 0.9, 1.45, 0.9, 1.5, 1.5, 1.6, 1.0])
    change_notes = financial_change_notes(data["financials"])
    if change_notes:
        add_body(doc, "注：" + "；".join(change_notes))
    add_heading(doc, "政府补助及财政支持明细表", 3); add_standard_table(doc, ["年度", "名称", "发放部门", "金额", "用途", "附带条件", "来源"], rows(data.get("government_support", []), ("year", "name", "department", "amount", "purpose", "conditions", "source")) or [["—", "本轮公开检索未发现可确认明细", "—", "—", "需企业补充", "需企业补充", "—"]], [1.1, 2.5, 2.0, 1.3, 3.0, 3.0, 1.0])
    add_heading(doc, "（二）经营数据分析", 2); add_body(doc, data.get("financial_analysis", "需企业补充"))
    h1(doc, "四、风险与合规情况")
    add_body(doc, data["risks"].get("summary", "截至公开检索未发现重大记录，仍需企业及主管部门核验。"))
    h1(doc, "五、三亚落地业务及落地方式"); add_standard_table(doc, ["建议落地业务", "企业现有事实基础", "三亚具体承接方式", "可形成的业务及价值", "可行性"], rows(data["landing_businesses"], ("business", "fact_basis", "sanya_path", "value", "feasibility")), [3.0, 4.0, 4.0, 4.0, 1.0])
    h1(doc, "六、企业政策匹配")
    add_heading(doc, "（一）重点政策匹配清单", 2)
    add_body(doc, "本节按企业在三亚设立并实质运营主体、承接总部管理、品牌电商、贸易结算和海外运营功能的整体落地情景呈现。仅保留直接影响招商谈判的重点政策；同一项优惠的政策原文与执行公告合并展示，具体资格以正式申报材料为准。")
    add_standard_table(doc, ["拟落地业务", "重点政策", "企业能获得什么", "享受前提及三亚承接", "适用定位"], policy_match_rows(data["policies"]), [2.6, 3.0, 3.0, 5.8, 2.1])
    h1(doc, "七、综合评估"); add_body(doc, data.get("comprehensive_assessment", "需企业补充"))
    h1(doc, "八、参考资料"); add_standard_table(doc, ["编号", "类型", "资料名称", "发布主体", "日期", "网址或文件定位", "使用位置"], rows(data["sources"], ("id", "type", "name", "issuer", "date", "location", "used_in")), [1.0, 1.1, 3.0, 2.3, 1.4, 5.0, 2.0])
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); doc.save(out)
    try_update_fields_with_word(out); print(out); return 0


if __name__ == "__main__":
    raise SystemExit(main())
