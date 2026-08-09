#!/usr/bin/env python3
"""Normalize browser-captured QCC or Tianyancha equity evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


WEB_PROVIDERS = {"qcc_web", "tianyancha_web"}
RECORD_TYPES = {
    "current_shareholder",
    "actual_controller",
    "beneficial_owner",
    "historical_shareholder",
    "historical_change",
    "subsidiary",
}
ASSERTION_TYPES = {"registry_fact", "provider_calculation"}
CALCULATION_QUALIFIERS = ("推定", "疑似", "平台穿透")


def _text(value: object) -> str:
    return str(value or "").strip()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _validate_capture(payload: dict, legal_entity: str) -> None:
    required = (
        "page_url",
        "captured_at",
        "legal_entity",
        "records",
        "unified_social_credit_code",
        "registration_status",
        "page_locator",
    )
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise SystemExit("网页取证JSON缺少字段：" + "、".join(missing))
    if not isinstance(payload["records"], list) or not payload["records"]:
        raise SystemExit("网页取证JSON的records必须是非空数组")
    if _text(payload["legal_entity"]) != _text(legal_entity):
        raise SystemExit("网页取证主体与命令指定法律主体不一致")

    for index, record in enumerate(payload["records"], 1):
        if not isinstance(record, dict):
            raise SystemExit(f"网页取证records第{index}项必须是对象")
        record_type = _text(record.get("record_type"))
        if record_type not in RECORD_TYPES:
            raise SystemExit(f"网页取证records第{index}项record_type无效：{record_type or '空'}")
        for field in ("entity_name", "entity_type", "page_locator", "assertion_type"):
            if not _text(record.get(field)):
                raise SystemExit(f"网页取证records第{index}项缺少{field}")
        assertion_type = _text(record.get("assertion_type"))
        if assertion_type not in ASSERTION_TYPES:
            raise SystemExit(f"网页取证records第{index}项assertion_type无效：{assertion_type}")
        relationship = _text(record.get("relationship"))
        if assertion_type == "provider_calculation" and not any(marker in relationship for marker in CALCULATION_QUALIFIERS):
            raise SystemExit(f"网页取证records第{index}项平台推算关系必须标明推定、疑似或平台穿透")


def _relationship(record: dict) -> tuple[str, str, str]:
    record_type = record["record_type"]
    relationship = _text(record.get("relationship"))
    if record_type == "subsidiary":
        return "subject", "entity", relationship or "主要子公司"
    defaults = {
        "current_shareholder": "当前股东",
        "actual_controller": "实际控制人",
        "beneficial_owner": "受益人",
        "historical_shareholder": "历史股东",
        "historical_change": "历史股东或历史变更",
    }
    return "entity", "subject", relationship or defaults[record_type]


def normalize_web_capture(payload: dict, provider: str) -> dict:
    source_id = "EWEB01"
    default_as_of = _text(payload.get("data_as_of")) or _text(payload["captured_at"])
    source = {
        "id": source_id,
        "provider": provider,
        "page_url": payload["page_url"],
        "page_locator": payload["page_locator"],
        "captured_at": payload["captured_at"],
        "data_as_of": default_as_of,
        "record_count": len(payload["records"]),
    }
    nodes = [{
        "id": "subject",
        "name": payload["legal_entity"],
        "entity_type": "法律主体",
        "unified_social_credit_code": payload["unified_social_credit_code"],
        "registration_status": payload["registration_status"],
        "assertion_type": "registry_fact",
        "source_id": source_id,
        "as_of_date": default_as_of,
        "record_locator": payload["page_locator"],
    }]
    node_ids: dict[str, str] = {payload["legal_entity"]: "subject"}
    edges = []
    for record in payload["records"]:
        name = _text(record["entity_name"])
        as_of_date = _text(record.get("data_as_of")) or default_as_of
        node_id = node_ids.get(name)
        if not node_id:
            node_id = f"entity_{len(node_ids):03d}"
            node_ids[name] = node_id
            nodes.append({
                "id": node_id,
                "name": name,
                "entity_type": record["entity_type"],
                "assertion_type": record["assertion_type"],
                "source_id": source_id,
                "as_of_date": as_of_date,
                "record_locator": record["page_locator"],
            })
        direction_from, direction_to, relationship = _relationship(record)
        edge = {
            "from": node_id if direction_from == "entity" else "subject",
            "to": node_id if direction_to == "entity" else "subject",
            "entity_name": name,
            "record_type": record["record_type"],
            "relationship": relationship,
            "assertion_type": record["assertion_type"],
            "source_id": source_id,
            "as_of_date": as_of_date,
            "record_locator": record["page_locator"],
        }
        ratio = _text(record.get("shareholding_ratio"))
        if ratio:
            edge["shareholding_ratio"] = ratio
        edges.append(edge)
    return {
        "provider": provider,
        "legal_entity": payload["legal_entity"],
        "unified_social_credit_code": payload["unified_social_credit_code"],
        "registration_status": payload["registration_status"],
        "source": source,
        "nodes": nodes,
        "edges": edges,
        "captured_at": payload["captured_at"],
    }


def collect_web_capture(legal_entity: str, out_dir: Path, provider: str, input_json: Path) -> int:
    if provider not in WEB_PROVIDERS:
        raise SystemExit(f"不支持的网页取证提供方：{provider}")
    payload = json.loads(input_json.read_text(encoding="utf-8-sig"))
    _validate_capture(payload, legal_entity)
    fragment = normalize_web_capture(payload, provider)
    raw_path = out_dir / f"{provider}-capture.json"
    fragment_path = out_dir / "normalized-equity-fragment.json"
    _write_json(raw_path, payload)
    _write_json(fragment_path, fragment)
    _write_json(out_dir / "provider-query-bundle.json", {
        "provider": provider,
        "legal_entity": legal_entity,
        "calls": [{
            "query": legal_entity,
            "queried_at": payload["captured_at"],
            "status": "success",
            "page_url": payload["page_url"],
            "page_locator": payload["page_locator"],
            "raw_path": raw_path.name,
            "normalized_fragment_path": fragment_path.name,
            "record_count": len(payload["records"]),
        }],
    })
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize authenticated browser equity evidence for later merging and validation.")
    parser.add_argument("legal_entity")
    parser.add_argument("--provider", required=True, choices=("qcc-web", "tianyancha-web"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--input-json", required=True, type=Path, help="standardized browser capture JSON")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    return collect_web_capture(args.legal_entity, args.out_dir, args.provider.replace("-", "_"), args.input_json)


if __name__ == "__main__":
    raise SystemExit(main())
