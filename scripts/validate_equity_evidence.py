#!/usr/bin/env python3
"""Validate provider-backed equity evidence against the rendered report graph."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from collect_equity_provider import CaptureContractError, is_valid_provider_url, validate_web_capture
from report_core import load_data


PROVIDERS = {
    "qcc_web",
    "tianyancha_web",
    "legal_disclosure",
    "official_registry",
}
COMMERCIAL_PROVIDERS = {"qcc_web", "tianyancha_web"}
ATTEMPT_STATUSES = {"success", "unavailable", "error"}
ASSERTION_TYPES = {"registry_fact", "legal_disclosure", "provider_calculation", "consolidation_scope"}
CONFLICT_SEVERITIES = {"general", "material_local", "subject_critical"}
CONFLICT_STATUSES = {"resolved", "unresolved"}
GRAPH_ACTIONS = {"keep_confirmed_part", "omit_disputed_part"}
CONFLICT_TEXT_FIELDS = (
    "field",
    "title",
    "difference",
    "reason",
    "adopted_basis",
    "impact",
    "next_action",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_affirmative_claim(statement: str, phrase: str) -> bool:
    """Return true when a verification phrase is not negated in its current clause."""
    start = 0
    delimiters = "，,；;。.!！?？\n"
    while True:
        index = statement.find(phrase, start)
        if index < 0:
            return False
        clause_start = max((statement.rfind(delimiter, 0, index) for delimiter in delimiters), default=-1) + 1
        prefix = statement[clause_start:index]
        if not any(marker in prefix for marker in ("未", "不", "无", "尚未", "不得", "不能")):
            return True
        start = index + len(phrase)


def _claims_verified_without_receipt(statement: str) -> bool:
    """Reject affirmative verification claims, without flagging explicit negations."""
    return any(
        _is_affirmative_claim(statement, phrase)
        for phrase in ("企查查网页已核验", "天眼查网页已核验", "商业平台网页已核验")
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_artifact_path(base_dir: Path, value: object) -> Path | None:
    raw = _text(value)
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return None
    resolved_base = base_dir.resolve()
    resolved = (resolved_base / candidate).resolve()
    try:
        resolved.relative_to(resolved_base)
    except ValueError:
        return None
    return resolved


def _validate_web_artifact_chain(source: dict, base_dir: Path, legal_entity: str, errors: list[str]) -> None:
    source_id = _text(source.get("id")) or "未编号"
    for field in ("artifact_path", "artifact_sha256", "bundle_path", "bundle_sha256"):
        if not _text(source.get(field)):
            errors.append(f"股权网页来源{source_id}缺少可验证artifact字段：{field}")
    artifact_path = _safe_artifact_path(base_dir, source.get("artifact_path"))
    bundle_path = _safe_artifact_path(base_dir, source.get("bundle_path"))
    if not artifact_path:
        errors.append(f"股权网页来源{source_id}的artifact_path不合法")
        return
    if not artifact_path.is_file():
        errors.append(f"股权网页来源{source_id}的artifact不存在")
        return
    if _sha256(artifact_path) != _text(source.get("artifact_sha256")):
        errors.append(f"股权网页来源{source_id}的artifact SHA-256不匹配")
        return
    if not bundle_path or not bundle_path.is_file():
        errors.append(f"股权网页来源{source_id}的bundle artifact不存在或路径不合法")
        return
    if _sha256(bundle_path) != _text(source.get("bundle_sha256")):
        errors.append(f"股权网页来源{source_id}的bundle SHA-256不匹配")
        return
    try:
        capture = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
        bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"股权网页来源{source_id}的artifact JSON不可读取：{error}")
        return
    provider = _text(source.get("provider"))
    if not isinstance(capture, dict) or not isinstance(bundle, dict):
        errors.append(f"股权网页来源{source_id}的artifact结构无效")
        return
    try:
        validate_web_capture(capture, legal_entity, provider)
    except CaptureContractError as error:
        errors.append(f"股权网页来源{source_id}的capture合同无效：{error}")
    expected = {
        "legal_entity": legal_entity,
        "captured_at": _text(source.get("captured_at")),
        "page_url": _text(source.get("page_url")),
    }
    if not is_valid_provider_url(provider, expected["page_url"]):
        errors.append(f"股权网页来源{source_id}的provider与HTTPS页面URL不匹配")
    if any(_text(capture.get(key)) != value for key, value in expected.items()):
        errors.append(f"股权网页来源{source_id}与capture artifact主体、时点或URL不一致")
    records = capture.get("records")
    if not isinstance(records, list) or len(records) != source.get("record_count"):
        errors.append(f"股权网页来源{source_id}与capture artifact记录数量不一致")
    calls = bundle.get("calls")
    matching_call = next((item for item in calls if isinstance(item, dict) and _text(item.get("capture_path")) == _text(source.get("artifact_path"))), None) if isinstance(calls, list) else None
    if _text(bundle.get("provider")) != provider or _text(bundle.get("legal_entity")) != legal_entity or not matching_call:
        errors.append(f"股权网页来源{source_id}与query bundle不一致")
        return
    for field, expected_value in {
        "capture_sha256": _text(source.get("artifact_sha256")),
        "record_count": source.get("record_count"),
        "legal_entity": legal_entity,
        "captured_at": _text(source.get("captured_at")),
        "page_url": _text(source.get("page_url")),
    }.items():
        if matching_call.get(field) != expected_value:
            errors.append(f"股权网页来源{source_id}与query bundle的{field}不一致")


def validate_equity_evidence(ledger: dict, report: dict, base_dir: Path | None = None) -> list[str]:
    errors: list[str] = []
    subject = ledger.get("subject", {})
    legal_entity = _text(report.get("entity_resolution", {}).get("legal_entity"))
    analysis_entity = _text(report.get("entity_resolution", {}).get("analysis_entity"))
    if _text(subject.get("legal_entity")) not in {legal_entity, analysis_entity}:
        errors.append("股权证据主体与报告法律主体不一致")

    attempts = ledger.get("provider_attempts", [])
    commercial_attempts = [item for item in attempts if _text(item.get("provider")) in COMMERCIAL_PROVIDERS]
    if not commercial_attempts:
        errors.append("缺少企查查或天眼查接入尝试回执")
    for item in attempts:
        provider = _text(item.get("provider"))
        status = _text(item.get("status"))
        if provider not in COMMERCIAL_PROVIDERS:
            errors.append(f"未知股权平台接入回执：{provider or '空'}")
        if status not in ATTEMPT_STATUSES:
            errors.append(f"股权平台接入状态无效：{provider} / {status or '空'}")
        if not _text(item.get("queried_at")):
            errors.append(f"股权平台接入回执缺少查询时间：{provider}")
        if status != "success" and not _text(item.get("reason")):
            errors.append(f"股权平台未成功但缺少原因：{provider}")

    sources = ledger.get("sources", [])
    source_by_id: dict[str, dict] = {}
    for source in sources:
        source_id = _text(source.get("id"))
        provider = _text(source.get("provider"))
        if not source_id or source_id in source_by_id:
            errors.append(f"股权证据来源编号为空或重复：{source_id or '空'}")
            continue
        source_by_id[source_id] = source
        if provider not in PROVIDERS:
            errors.append(f"股权证据来源平台无效：{provider or '空'}")
        for field in ("method", "queried_at", "query", "status", "record_locator"):
            if not _text(source.get(field)):
                errors.append(f"股权证据来源{source_id}缺少{field}")
        if provider in COMMERCIAL_PROVIDERS:
            for field in ("page_url", "captured_at"):
                if not _text(source.get(field)):
                    errors.append(f"股权网页来源{source_id}缺少{field}")
            if not isinstance(source.get("record_count"), int) or source.get("record_count", 0) <= 0:
                errors.append(f"股权网页来源{source_id}缺少非空记录")
            if _text(source.get("status")) == "success":
                if not is_valid_provider_url(provider, _text(source.get("page_url"))):
                    errors.append(f"股权网页来源{source_id}的provider与HTTPS页面URL不匹配")
                if base_dir is not None:
                    _validate_web_artifact_chain(source, base_dir, legal_entity, errors)

    successful_commercial = {
        _text(source.get("provider"))
        for source in sources
        if _text(source.get("provider")) in COMMERCIAL_PROVIDERS
        and _text(source.get("status")) == "success"
        and isinstance(source.get("record_count"), int)
        and source.get("record_count", 0) > 0
    }
    successful_attempts = {
        _text(item.get("provider")) for item in commercial_attempts if _text(item.get("status")) == "success"
    }
    if successful_attempts - successful_commercial:
        errors.append("平台接入标记成功但未登记对应成功来源")

    summary = report.get("equity", {}).get("evidence_summary", {})
    if not isinstance(summary, dict):
        errors.append("报告缺少股权取证渠道与采用口径")
    else:
        attempted_channels = {_text(item) for item in summary.get("attempted_channels", [])}
        successful_channels = {_text(item) for item in summary.get("successful_channels", [])}
        expected_attempted = {_text(item.get("provider")) for item in commercial_attempts}
        expected_successful = {
            _text(source.get("provider")) for source in sources if _text(source.get("status")) == "success"
        }
        if attempted_channels != expected_attempted:
            errors.append("报告显示的股权尝试渠道与证据台账不一致")
        if successful_channels != expected_successful:
            errors.append("报告显示的股权成功来源与证据台账不一致")
        for field in ("adopted_basis", "status_statement"):
            if not _text(summary.get(field)):
                errors.append(f"报告股权取证口径缺少{field}")
        statement = _text(summary.get("status_statement"))
        if not successful_commercial and _claims_verified_without_receipt(statement):
            errors.append("没有网页成功回执及非空记录时不得声称网页已核验")
        claims = {
            "qcc_web": "企查查网页已核验",
            "tianyancha_web": "天眼查网页已核验",
        }
        for provider, phrase in claims.items():
            if _is_affirmative_claim(statement, phrase) and provider not in successful_commercial:
                errors.append(f"{phrase}必须有本轮成功回执及非空记录")
    if not successful_commercial:
        if not all(_text(item.get("status")) in {"unavailable", "error"} for item in commercial_attempts):
            errors.append("商业股权平台无成功来源且降级状态不完整")
        if not any(_text(source.get("provider")) in {"legal_disclosure", "official_registry"} and _text(source.get("status")) == "success" for source in sources):
            errors.append("商业股权平台不可用时必须有法定披露或官方登记替代来源")

    report_sources = {_text(item.get("id")) for item in report.get("sources", [])}
    for source_id in source_by_id:
        if source_id not in report_sources:
            errors.append(f"股权证据来源未进入报告参考资料：{source_id}")

    ledger_nodes = {_text(item.get("id")): item for item in ledger.get("nodes", []) if _text(item.get("id"))}
    ledger_edges = {(_text(item.get("from")), _text(item.get("to"))): item for item in ledger.get("edges", [])}

    for item in ledger.get("nodes", []):
        label = _text(item.get("name")) or _text(item.get("id")) or "未命名节点"
        if _text(item.get("assertion_type")) not in ASSERTION_TYPES:
            errors.append(f"股权节点断言类型无效：{label}")
        if not _text(item.get("as_of_date")):
            errors.append(f"股权节点缺少数据时点：{label}")
        _validate_source_ids(item, source_by_id, f"股权节点{label}", errors)
    for item in ledger.get("edges", []):
        label = f"{_text(item.get('from'))}->{_text(item.get('to'))}"
        assertion_type = _text(item.get("assertion_type"))
        relationship = _text(item.get("relationship"))
        if assertion_type not in ASSERTION_TYPES:
            errors.append(f"股权连接断言类型无效：{label}")
        if not _text(item.get("as_of_date")):
            errors.append(f"股权连接缺少数据时点：{label}")
        if assertion_type == "provider_calculation" and "推定" not in relationship and "疑似" not in relationship and "平台穿透" not in relationship:
            errors.append(f"平台计算关系必须标明推定、疑似或平台穿透：{label}")
        _validate_source_ids(item, source_by_id, f"股权连接{label}", errors)

    for node in report.get("equity", {}).get("nodes", []):
        node_id = _text(node.get("id"))
        evidence = ledger_nodes.get(node_id)
        if not evidence or _text(evidence.get("name")) != _text(node.get("name")):
            errors.append(f"报告股权节点缺少证据台账对应关系：{node_id}")
            continue
        if not set(node.get("evidence_source_ids", [])).issubset(set(evidence.get("evidence_source_ids", []))):
            errors.append(f"报告股权节点引用了台账未支持的来源：{node_id}")
    for edge in report.get("equity", {}).get("edges", []):
        key = (_text(edge.get("from")), _text(edge.get("to")))
        evidence = ledger_edges.get(key)
        if not evidence or _text(evidence.get("relationship")) != _text(edge.get("relationship")):
            errors.append(f"报告股权连接缺少证据台账对应关系：{key[0]}->{key[1]}")
            continue
        if not set(edge.get("evidence_source_ids", [])).issubset(set(evidence.get("evidence_source_ids", []))):
            errors.append(f"报告股权连接引用了台账未支持的来源：{key[0]}->{key[1]}")

    report_nodes = {_text(item.get("id")) for item in report.get("equity", {}).get("nodes", [])}
    report_edges = {
        (_text(item.get("from")), _text(item.get("to")))
        for item in report.get("equity", {}).get("edges", [])
    }
    report_disclosures = {
        _text(item.get("id")): item
        for item in report.get("equity", {}).get("conflict_disclosures", [])
        if _text(item.get("id"))
    }
    ledger_conflict_ids: set[str] = set()
    unresolved: list[dict] = []
    for item in ledger.get("conflicts", []):
        conflict_id = _text(item.get("id"))
        if not conflict_id or conflict_id in ledger_conflict_ids:
            errors.append(f"股权冲突编号为空或重复：{conflict_id or '空'}")
            continue
        ledger_conflict_ids.add(conflict_id)
        severity = _text(item.get("severity"))
        status = _text(item.get("status"))
        graph_action = _text(item.get("graph_action"))
        if severity not in CONFLICT_SEVERITIES:
            errors.append(f"股权冲突{conflict_id}的severity无效")
        if status not in CONFLICT_STATUSES:
            errors.append(f"股权冲突{conflict_id}的status无效")
        if graph_action not in GRAPH_ACTIONS:
            errors.append(f"股权冲突{conflict_id}的graph_action无效")
        for field in CONFLICT_TEXT_FIELDS:
            if not _text(item.get(field)):
                errors.append(f"股权冲突{conflict_id}缺少{field}")
        _validate_source_ids(item, source_by_id, f"股权冲突{conflict_id}", errors)
        disclosure = report_disclosures.get(conflict_id)
        if not disclosure:
            errors.append(f"股权冲突{conflict_id}未进入报告文字说明")
        elif not _same_conflict_disclosure(item, disclosure):
            errors.append(f"股权冲突{conflict_id}的报告文字说明与证据台账不一致")
        if graph_action == "omit_disputed_part":
            affected_nodes = {_text(node_id) for node_id in item.get("affected_node_ids", []) if _text(node_id)}
            affected_edges = {
                (_text(edge.get("from")), _text(edge.get("to")))
                for edge in item.get("affected_edges", [])
            }
            if not affected_nodes and not affected_edges:
                errors.append(f"股权冲突{conflict_id}要求隐藏争议关系但未声明影响范围")
            for node_id in sorted(affected_nodes & report_nodes):
                errors.append(f"股权冲突{conflict_id}的争议节点仍进入股权图：{node_id}")
            for edge in sorted(affected_edges & report_edges):
                errors.append(f"股权冲突{conflict_id}的争议连接仍进入股权图：{edge[0]}->{edge[1]}")
        if status == "unresolved":
            unresolved.append(item)

    for conflict_id in sorted(set(report_disclosures) - ledger_conflict_ids):
        errors.append(f"报告股权差异说明缺少证据台账对应项：{conflict_id}")

    critical = [item for item in unresolved if _text(item.get("severity")) == "subject_critical"]
    noncritical_unresolved = [item for item in unresolved if _text(item.get("severity")) != "subject_critical"]
    review_status = _text(ledger.get("review_status"))
    if critical:
        errors.append(f"主体或核心控制关系存在未解决冲突，禁止生成报告：{len(critical)}项")
        if review_status != "blocked":
            errors.append("主体或核心控制关系未解决时review_status必须为blocked")
    elif noncritical_unresolved and review_status != "qualified_complete":
        errors.append("存在非根本性未解决差异时review_status必须为qualified_complete")
    if not unresolved and review_status not in {"complete", "fallback_complete"}:
        errors.append("股权证据复核状态未完成")
    return errors


def _same_conflict_disclosure(ledger_item: dict, report_item: dict) -> bool:
    scalar_fields = ("id", "severity", "status", "graph_action", *CONFLICT_TEXT_FIELDS)
    if any(_text(ledger_item.get(field)) != _text(report_item.get(field)) for field in scalar_fields):
        return False
    if set(ledger_item.get("evidence_source_ids", [])) != set(report_item.get("evidence_source_ids", [])):
        return False
    if set(ledger_item.get("affected_node_ids", [])) != set(report_item.get("affected_node_ids", [])):
        return False
    ledger_edges = {(_text(item.get("from")), _text(item.get("to"))) for item in ledger_item.get("affected_edges", [])}
    report_edges = {(_text(item.get("from")), _text(item.get("to"))) for item in report_item.get("affected_edges", [])}
    return ledger_edges == report_edges


def _validate_source_ids(item: dict, source_by_id: dict[str, dict], label: str, errors: list[str]) -> None:
    source_ids = item.get("evidence_source_ids", [])
    if not source_ids:
        errors.append(f"{label}缺少证据来源")
        return
    for source_id in source_ids:
        if source_id not in source_by_id:
            errors.append(f"{label}引用不存在来源：{source_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate equity evidence and its one-to-one match with the report graph.")
    parser.add_argument("equity_evidence", type=Path)
    parser.add_argument("--report-data", required=True, type=Path)
    args = parser.parse_args()
    errors = validate_equity_evidence(load_data(args.equity_evidence), load_data(args.report_data), args.equity_evidence.resolve().parent)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("通过：股权主体、平台回执、节点、连线、来源及时点均已校验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
