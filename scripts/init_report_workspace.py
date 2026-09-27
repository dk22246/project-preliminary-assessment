"""Create a clean five-ledger workspace for one formal assessment project."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_payloads(enterprise: str) -> dict[str, dict]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "report-data.json": {
            "meta": {
                "report_title": f"{enterprise}招商落地前期评估报告",
                "generated_at": now,
                "reporting_entity": enterprise,
                "policy_researched_at": "",
                "policy_search_mode": "realtime",
                "workspace_status": "blank",
            },
            "entity_resolution": {
                "user_input": enterprise,
                "name_type": "",
                "legal_entity": "",
                "analysis_entity": "",
                "financial_scope": "",
                "risk_scope": "",
            },
            "enterprise_overview": {},
            "equity": {"data_status": "", "nodes": [], "edges": [], "conflict_disclosures": [], "review_status": "incomplete"},
            "businesses": [],
            "top500_status": [],
            "industry_chain": {},
            "encouraged_industry_assessment": [],
            "industry_position": {},
            "financials": [],
            "risks": [],
            "landing_businesses": [],
            "policy_research": [],
            "policy_opportunity_radar": [],
            "policies": [],
            "sources": [],
        },
        "equity-evidence.json": {
            "schema_version": "1.0",
            "subject": {"legal_entity": enterprise, "unified_social_credit_code": ""},
            "provider_attempts": [],
            "sources": [],
            "nodes": [],
            "edges": [],
            "conflicts": [],
            "availability_note": "",
            "review_status": "incomplete",
        },
        "research-ledger.json": {
            "enterprise": enterprise,
            "enterprise_profile": {
                "analysis_entity": "",
                "listing_status": "",
                "research_route": "",
                "basis_source_ids": [],
            },
            "research_stop_gate": {
                "source_channels": {},
                "required_topics": {},
                "discovery_rounds": [],
                "nonlisted_evidence_checks": None,
            },
            "fact_ledger": [],
            "business_candidates": [],
            "department_routes": [],
            "policy_candidates": [],
        },
        "policy-search-ledger.json": {
            "version": "1.0",
            "enterprise": enterprise,
            "researched_at": "",
            "search_mode": "realtime",
            "landing_business_hypotheses": [],
            "department_scan_profiles": [],
            "searches": [],
            "policy_candidates": [],
        },
        "policy-evidence.json": {
            "version": "1.0",
            "enterprise": enterprise,
            "researched_at": "",
            "mode": "formal",
            "records": [],
        },
    }


def build_findings(enterprise: str) -> dict[str, dict]:
    return {
        "enterprise-findings.json": {
            "version": "1.0",
            "enterprise": enterprise,
            "report": {"entity_resolution": {}, "enterprise_overview": {}, "businesses": [], "landing_businesses": []},
            "research": {"enterprise_profile": {}, "research_stop_gate": {}, "facts": [], "business_candidates": [], "department_routes": []},
            "equity": {"data_status": "", "review_status": "incomplete", "provider_attempts": [], "sources": [], "nodes": [], "edges": [], "conflicts": []},
            "sources": [],
        },
        "policy-findings.json": {
            "version": "1.0",
            "enterprise": enterprise,
            "researched_at": "",
            "policy_records": [],
            "search": {"landing_business_hypotheses": [], "department_scan_profiles": [], "searches": [], "discovered_candidates": [], "failures": [], "decode_warnings": []},
            "evidence": [],
            "sources": [],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="initialize a blank project-preliminary-assessment workspace")
    parser.add_argument("enterprise")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--force", action="store_true", help="allow initialization only when the existing directory is empty")
    args = parser.parse_args()

    enterprise = args.enterprise.strip()
    if not enterprise:
        raise SystemExit("企业名称不能为空")
    out = Path(args.out_dir).resolve()
    if out.exists():
        if not args.force:
            raise SystemExit(f"目标目录已存在，拒绝覆盖：{out}")
        if not out.is_dir() or any(out.iterdir()):
            raise SystemExit(f"--force 只允许写入已存在的空目录：{out}")
    else:
        out.mkdir(parents=True)

    for name, payload in {**build_payloads(enterprise), **build_findings(enterprise)}.items():
        _write(out / name, payload)
    print(f"已初始化空白项目：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
