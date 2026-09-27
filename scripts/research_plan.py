#!/usr/bin/env python3
"""Build a bounded research action list from the confirmed disclosure route."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


LISTED_ACTIONS = (
    ("latest_annual_report", "exchange_disclosure", "required", "最新年度报告集中提取主体、业务、产品、近三年财务、股权、政府补助和重大风险"),
    ("historical_gap_fill", "exchange_disclosure", "only_if_gap", "只对最新年报未解决的历史年度字段定向补缺"),
    ("company_current_delta", "company_official", "required", "只核验当前产品、最近一年重大变化、近期战略和海外布局缺口"),
    ("regulatory_risk_delta", "government_regulatory", "required", "只核验年报后发生或法定披露未解决的重要处罚、诉讼和监管事项"),
)

NONLISTED_ACTIONS = (
    ("company_self_statement", "company_official", "required", "核验企业官网、官方公众号或正式材料中的产品、服务、解决方案和项目"),
    ("government_operating_records", "government_regulatory", "required", "核验政府项目、备案、行政许可、采购和招投标记录"),
    ("counterparty_disclosure", "counterparty_official", "required", "核验客户或合作方正式公告中的经营事实"),
    ("business_registry", "business_registry", "required", "核验公开登记、股权和主体关系"),
    ("risk_records", "risk_records", "required", "核验行政处罚与异常、税务违法、诉讼执行、失信信用四类官方记录"),
    ("targeted_gap_check", "authoritative_supplement", "only_if_material_gap", "固定路径结束后，只补查一个会改变招商结论的事实缺口"),
)


def build_research_plan(findings: dict) -> dict:
    enterprise = str(findings.get("enterprise", "")).strip()
    profile = findings.get("research", {}).get("enterprise_profile", {})
    route = str(profile.get("research_route", "")).strip()
    listing_status = str(profile.get("listing_status", "")).strip()
    expected = {
        "listed_disclosure": "listed",
        "nonlisted_public_evidence": "nonlisted",
    }
    if route not in expected or listing_status != expected[route]:
        raise ValueError("请先在enterprise-findings.json确认listing_status与research_route")
    actions = LISTED_ACTIONS if route == "listed_disclosure" else NONLISTED_ACTIONS
    return {
        "version": "1.0",
        "enterprise": enterprise,
        "research_route": route,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dedupe_key": "canonical_url",
        "execution": {
            "collection_mode": "batch_parallel",
            "max_research_rounds": 1 if route == "listed_disclosure" else 2,
            "same_document_rule": "同一规范化URL在同一run_id内只抓取和解析一次",
            "conditional_action_rule": "only_if_gap或only_if_material_gap没有明确缺口时直接标记skipped，不得执行泛搜",
        },
        "actions": [
            {"id": f"RA{index:02d}", "action": action, "channel": channel, "mode": mode, "purpose": purpose, "status": "pending"}
            for index, (action, channel, mode, purpose) in enumerate(actions, 1)
        ],
        "stop_rule": (
            "最新年报集中研究完成、条件型历史缺口已处置、官网和监管增量已处置后停止；法定披露已解决的事实不再重复证明"
            if route == "listed_disclosure"
            else "固定五类来源和一次重大缺口补查完成后停止；公开信息缺失写明需企业补充，不转向无关网站泛搜"
        ),
    }


def write_research_plan(findings_path: Path, output_path: Path) -> dict:
    findings = json.loads(Path(findings_path).read_text(encoding="utf-8-sig"))
    plan = build_research_plan(findings)
    temporary = Path(output_path).with_suffix(".tmp")
    temporary.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return plan
