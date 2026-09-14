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


def validate_research_stop_gate(ledger: dict) -> list[str]:
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
    if route == "listed_disclosure":
        if not isinstance(rounds, list) or not rounds:
            errors.append("上市公司尚未完成法定披露集中研究，不能结束一般性企业研究")
    elif not isinstance(rounds, list) or len(rounds) < 2:
        errors.append("能力发现不足两轮，不能结束一般性企业研究")
    else:
        last_two = rounds[-2:]
        if any(item.get("high_value_candidate_ids") for item in last_two):
            errors.append("连续两轮仍发现高价值业务候选，不能结束一般性企业研究")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate whether enterprise research may enter policy discovery")
    parser.add_argument("research_ledger")
    args = parser.parse_args()
    errors = validate_research_stop_gate(load_data(Path(args.research_ledger)))
    if errors:
        print("\n".join(errors))
        return 1
    print("通过：企业研究已完成必要处置，可进入落地业务和政策阶段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
