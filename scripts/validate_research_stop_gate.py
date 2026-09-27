#!/usr/bin/env python3
"""Stop general enterprise research once every decision-critical topic is disposed."""
from __future__ import annotations

import argparse
from pathlib import Path

from report_core import load_data


REQUIRED_TOPICS = (
    "entity", "core_business", "industry_position", "domestic_overseas",
    "three_year_financials", "equity", "risk",
)
VALID_STATUSES = {"completed", "not_available", "inaccessible"}
VALID_DISPOSITIONS = {"include", "merge", "exclude"}
ROUTE_BY_LISTING_STATUS = {
    "listed": "listed_disclosure",
    "nonlisted": "nonlisted_public_evidence",
}
REQUIRED_SOURCE_CHANNELS = {
    "listed_disclosure": ("exchange_disclosure", "company_official", "government_regulatory"),
    "nonlisted_public_evidence": ("company_official", "government_regulatory", "business_registry", "risk_records"),
}
NONLISTED_BUSINESS_EVIDENCE = (
    "company_self_statement",
    "government_operating_records",
    "counterparty_disclosure",
)
NONLISTED_RISK_CHECKS = (
    "administrative_and_abnormal",
    "tax_violations",
    "litigation_and_enforcement",
    "dishonesty_and_credit",
)
INDUSTRY_500_STATUSES = {"listed", "group_listed", "not_listed"}
GOVERNMENT_SUPPORT_STATUSES = {"confirmed", "not_found", "inaccessible"}
GOVERNMENT_SUPPORT_EVIDENCE_TYPES = {
    "government_award_notice",
    "government_project_document",
    "company_formal_disclosure",
}
FINANCIAL_BOUNDARY_STATUSES = {"available", "partial", "not_public", "inaccessible"}
INDUSTRY_500_NOT_FOUND = "本轮未发现可核验的行业500强入选记录"
GOVERNMENT_SUPPORT_NOT_FOUND = "本轮公开检索未发现可确认的政府补助或政策支持记录"
RISK_NOT_FOUND = "本轮官方公开检索未发现相关记录"
RISK_INACCESSIBLE = "本轮无法核验"


def _validate_status_item(label: str, item: object, errors: list[str]) -> None:
    if not isinstance(item, dict):
        errors.append(f"{label}: 缺少处置")
        return
    status = str(item.get("status", "")).strip()
    if status not in VALID_STATUSES:
        errors.append(f"{label}: 状态只能为 completed、not_available 或 inaccessible")
    if status == "completed" and not item.get("source_ids"):
        errors.append(f"{label}: completed 缺少来源")
    if status in {"not_available", "inaccessible"} and not str(item.get("reason", "")).strip():
        errors.append(f"{label}: {status} 必须说明原因")


def _text(value: object) -> str:
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    return str(value or "")


def _validate_nonlisted_checks(gate: dict, errors: list[str], report_data: dict | None) -> None:
    checks = gate.get("nonlisted_evidence_checks")
    if not isinstance(checks, dict):
        errors.append("非上市公司缺少nonlisted_evidence_checks，不能结束企业研究")
        return

    business = checks.get("business_evidence")
    if not isinstance(business, dict):
        errors.append("nonlisted_evidence_checks缺少business_evidence")
    else:
        for name in NONLISTED_BUSINESS_EVIDENCE:
            _validate_status_item(f"business_evidence.{name}", business.get(name), errors)

    financial = checks.get("financial_boundary")
    if not isinstance(financial, dict):
        errors.append("nonlisted_evidence_checks缺少financial_boundary")
    else:
        status = str(financial.get("status", "")).strip()
        if status not in FINANCIAL_BOUNDARY_STATUSES:
            errors.append("financial_boundary.status只能为available、partial、not_public或inaccessible")
        if financial.get("proxy_inference_used") is not False:
            errors.append("非上市公司不得用注册资本、融资、产值、估值、项目金额或经营记录推算收入、利润和纳税；proxy_inference_used必须为false")
        if status in {"partial", "not_public", "inaccessible"} and not str(financial.get("reason", "")).strip():
            errors.append(f"financial_boundary为{status}时必须说明公开数据边界")

    industry = checks.get("industry_500")
    if not isinstance(industry, dict):
        errors.append("nonlisted_evidence_checks缺少industry_500")
    else:
        status = str(industry.get("status", "")).strip()
        if status not in INDUSTRY_500_STATUSES:
            errors.append("industry_500.status只能为listed、group_listed或not_listed")
        if not str(industry.get("report_statement", "")).strip():
            errors.append("industry_500缺少report_statement，无法写入企业概况")
        if status in {"listed", "group_listed"}:
            for field in ("ranking_name", "year", "rank", "listed_entity", "issuer", "source_ids"):
                if not industry.get(field):
                    errors.append(f"industry_500命中时缺少{field}")
            if status == "group_listed" and not str(industry.get("relationship_note", "")).strip():
                errors.append("母集团入选行业500强时必须说明与分析主体的关系")
        elif status == "not_listed":
            boundary = str(industry.get("report_statement", "")) + str(industry.get("reason", ""))
            if INDUSTRY_500_NOT_FOUND not in boundary:
                errors.append(f"行业500强未命中时必须写：{INDUSTRY_500_NOT_FOUND}")

    support = checks.get("government_support")
    if not isinstance(support, dict):
        errors.append("nonlisted_evidence_checks缺少government_support")
    else:
        status = str(support.get("status", "")).strip()
        if status not in GOVERNMENT_SUPPORT_STATUSES:
            errors.append("government_support.status只能为confirmed、not_found或inaccessible")
        items = support.get("items", [])
        if status == "confirmed":
            if not isinstance(items, list) or not items:
                errors.append("government_support为confirmed时必须列出已确认支持事项")
            else:
                for index, item in enumerate(items, 1):
                    if not isinstance(item, dict):
                        errors.append(f"government_support.items[{index}]必须为对象")
                        continue
                    if not str(item.get("name", "")).strip() or not item.get("source_ids"):
                        errors.append(f"government_support.items[{index}]缺少名称或来源")
                    if item.get("evidence_type") not in GOVERNMENT_SUPPORT_EVIDENCE_TYPES:
                        errors.append(f"government_support.items[{index}]证据类型不属于正式支持凭证")
        elif status == "not_found" and GOVERNMENT_SUPPORT_NOT_FOUND not in str(support.get("reason", "")):
            errors.append(f"未发现政府支持时必须写：{GOVERNMENT_SUPPORT_NOT_FOUND}")
        elif status == "inaccessible" and not str(support.get("reason", "")).strip():
            errors.append("government_support为inaccessible时必须说明无法核验原因")

    risk_checks = checks.get("risk_checks")
    if not isinstance(risk_checks, dict):
        errors.append("nonlisted_evidence_checks缺少risk_checks")
    else:
        for name in NONLISTED_RISK_CHECKS:
            item = risk_checks.get(name)
            _validate_status_item(f"risk_checks.{name}", item, errors)
            if isinstance(item, dict) and item.get("status") == "not_available" and RISK_NOT_FOUND not in str(item.get("reason", "")):
                errors.append(f"risk_checks.{name}未发现记录时必须写：{RISK_NOT_FOUND}")
            if isinstance(item, dict) and item.get("status") == "inaccessible" and RISK_INACCESSIBLE not in str(item.get("reason", "")):
                errors.append(f"risk_checks.{name}无法访问时必须写：{RISK_INACCESSIBLE}")

    if not isinstance(report_data, dict):
        return
    report_industry = _text(report_data.get("industry_position", {}))
    statement = str(industry.get("report_statement", "")).strip() if isinstance(industry, dict) else ""
    if statement and statement not in report_industry:
        errors.append("非上市公司行业500强结论未写入report-data.industry_position")
    if isinstance(industry, dict) and isinstance(report_data.get("industry_position"), dict):
        report_evidence_status = str(report_data["industry_position"].get("evidence_status", "")).strip()
        if industry.get("status") == "not_listed" and report_evidence_status != "not_public":
            errors.append("非上市公司未入选行业500强时，report-data.industry_position.evidence_status必须为not_public")
        if industry.get("status") in {"listed", "group_listed"}:
            if report_evidence_status != "ranked":
                errors.append("非上市公司命中行业500强时，report-data.industry_position.evidence_status必须为ranked")
            for field in ("ranking_name", "year", "rank", "listed_entity", "issuer"):
                value = str(industry.get(field, "")).strip()
                if value and value not in report_industry:
                    errors.append(f"非上市公司行业500强报告结论缺少{field}：{value}")
    if isinstance(support, dict) and support.get("status") == "confirmed":
        report_support = _text(report_data.get("government_support", []))
        for item in support.get("items", []):
            name = str(item.get("name", "")).strip()
            if name and name not in report_support:
                errors.append(f"已确认政府支持未写入报告明细表：{name}")
    if isinstance(support, dict) and support.get("status") == "not_found" and report_data.get("government_support"):
        errors.append("后台结论为未发现政府支持，但报告仍列出政府支持明细")
    report_risks = _text(report_data.get("risks", {}))
    if isinstance(risk_checks, dict):
        if any(isinstance(item, dict) and item.get("status") == "not_available" for item in risk_checks.values()) and RISK_NOT_FOUND not in report_risks:
            errors.append(f"非上市公司风险未发现结论必须在报告中写：{RISK_NOT_FOUND}")
        if any(isinstance(item, dict) and item.get("status") == "inaccessible" for item in risk_checks.values()) and RISK_INACCESSIBLE not in report_risks:
            errors.append(f"非上市公司风险无法核验结论必须在报告中写：{RISK_INACCESSIBLE}")


def validate_research_stop_gate(ledger: dict, report_data: dict | None = None) -> list[str]:
    errors: list[str] = []
    profile = ledger.get("enterprise_profile")
    route = ""
    if not isinstance(profile, dict):
        errors.append("缺少enterprise_profile：主体确认后必须锁定上市或非上市检索路由")
    else:
        for field in ("analysis_entity", "listing_status", "research_route", "basis_source_ids"):
            if not profile.get(field):
                errors.append(f"enterprise_profile缺少{field}")
        listing_status = str(profile.get("listing_status", "")).strip()
        route = str(profile.get("research_route", "")).strip()
        expected_route = ROUTE_BY_LISTING_STATUS.get(listing_status)
        if expected_route is None:
            errors.append("enterprise_profile.listing_status只能为listed或nonlisted")
        elif route != expected_route:
            errors.append(f"enterprise_profile.research_route与listing_status不一致：应为{expected_route}")
    gate = ledger.get("research_stop_gate")
    if not isinstance(gate, dict):
        return ["缺少research_stop_gate：需企业补充后才能结束一般性企业研究"]
    source_channels = gate.get("source_channels")
    if not isinstance(source_channels, dict):
        errors.append("research_stop_gate缺少source_channels：无法确认分路径必查来源已完成")
    elif route in REQUIRED_SOURCE_CHANNELS:
        for channel in REQUIRED_SOURCE_CHANNELS[route]:
            _validate_status_item(f"source_channels.{channel}", source_channels.get(channel), errors)
    topics = gate.get("required_topics")
    if not isinstance(topics, dict):
        return ["缺少required_topics：需企业补充后才能结束一般性企业研究"]
    for topic in REQUIRED_TOPICS:
        item = topics.get(topic)
        if not isinstance(item, dict):
            errors.append(f"{topic}: 缺少处置，需企业补充")
            continue
        _validate_status_item(topic, item, errors)
    for candidate in ledger.get("business_candidates", []):
        candidate_id = str(candidate.get("id", "未编号"))
        disposition = str(candidate.get("disposition", "")).strip()
        if disposition not in VALID_DISPOSITIONS:
            errors.append(f"{candidate_id}: 候选业务缺少有效处置")
        elif not str(candidate.get("disposition_reason", "")).strip():
            errors.append(f"{candidate_id}: 候选业务处置缺少原因")
    rounds = gate.get("discovery_rounds")
    if not isinstance(rounds, list) or not rounds:
        if route == "listed_disclosure":
            errors.append("上市公司尚未完成法定披露集中研究，不能结束一般性企业研究")
        elif route == "nonlisted_public_evidence":
            errors.append("非上市公司尚未完成固定来源阶梯和一次定向补查，不能结束一般性企业研究")
    elif route == "listed_disclosure" and len(rounds) != 1:
        errors.append("上市公司只能执行一轮集中研究；缺口应在同轮定向处置，不得重复泛搜")
    elif route == "nonlisted_public_evidence" and len(rounds) > 2:
        errors.append("非上市公司最多执行固定来源阶梯和一次定向补查，不得增加重复检索轮次")
    if route == "nonlisted_public_evidence":
        _validate_nonlisted_checks(gate, errors, report_data)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate whether enterprise research may enter policy discovery")
    parser.add_argument("research_ledger")
    parser.add_argument("--report-data")
    args = parser.parse_args()
    report_data = load_data(Path(args.report_data)) if args.report_data else None
    errors = validate_research_stop_gate(load_data(Path(args.research_ledger)), report_data)
    if errors:
        print("\n".join(errors))
        return 1
    print("通过：企业研究已完成必要处置，可进入落地业务和政策阶段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
