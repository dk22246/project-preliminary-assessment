#!/usr/bin/env python3
"""Collect raw QCC CLI or Tianyancha API equity responses without exposing secrets."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TIANYANCHA_ENDPOINTS = {
    "shareholders": "https://open.api.tianyancha.com/services/open/ic/holderList/2.0",
    "equity_graph": "https://open.api.tianyancha.com/services/v4/open/equityRatio",
    "beneficial_owners": "https://open.api.tianyancha.com/services/open/ic/humanholding/2.0",
    "historical_shareholders": "https://open.api.tianyancha.com/services/open/hi/holder/2.0",
}


def qcc_commands(legal_entity: str, executable: str = "qcc") -> list[list[str]]:
    return [
        [executable, "company", "get_company_by_query", legal_entity],
        [executable, "company", "get_shareholder_info", legal_entity],
    ]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def collect_qcc(legal_entity: str, out_dir: Path, executable: str) -> int:
    resolved = shutil.which(executable) if not Path(executable).is_file() else executable
    if not resolved:
        raise SystemExit("未找到 qcc-agent-cli。先按企查查官方指南安装并执行 qcc init，密钥不得写入 Skill。")
    calls = []
    failed = False
    for index, command in enumerate(qcc_commands(legal_entity, str(resolved)), 1):
        result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, check=False)
        raw_path = out_dir / f"qcc-{index}.json"
        raw_path.write_text(result.stdout, encoding="utf-8")
        calls.append({
            "command": command[1:-1],
            "query": legal_entity,
            "queried_at": _now(),
            "status": "success" if result.returncode == 0 else "error",
            "returncode": result.returncode,
            "raw_path": raw_path.name,
            "error": result.stderr.strip()[:1000],
        })
        failed = failed or result.returncode != 0
    _write_json(out_dir / "provider-query-bundle.json", {"provider": "qcc_cli", "legal_entity": legal_entity, "calls": calls})
    return 1 if failed else 0


def _fetch_json(url: str, token: str) -> dict:
    request = Request(url, headers={"Authorization": token, "User-Agent": "project-preliminary-assessment-equity/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def collect_tianyancha(legal_entity: str, out_dir: Path, include_history: bool) -> int:
    token = os.environ.get("TYC_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("缺少 TYC_API_TOKEN。令牌只允许通过环境变量提供，不得写入 Skill、命令参数或输出文件。")
    names = ["shareholders", "equity_graph", "beneficial_owners"]
    if include_history:
        names.append("historical_shareholders")
    calls = []
    failed = False
    for name in names:
        query = {"keyword": legal_entity}
        if name in {"shareholders", "beneficial_owners", "historical_shareholders"}:
            query.update({"pageNum": 1, "pageSize": 20})
        url = f"{TIANYANCHA_ENDPOINTS[name]}?{urlencode(query)}"
        try:
            payload = _fetch_json(url, token)
            error_code = payload.get("error_code")
            status = "success" if error_code == 0 else "error"
            failed = failed or status == "error"
            error = "" if status == "success" else str(payload.get("reason", "provider error"))
        except Exception as exc:  # preserve a failed acquisition receipt without leaking the token
            payload = {"error": type(exc).__name__, "message": str(exc)}
            status = "error"
            error = str(exc)
            failed = True
        raw_path = out_dir / f"tianyancha-{name}.json"
        _write_json(raw_path, payload)
        calls.append({"endpoint": name, "query": legal_entity, "queried_at": _now(), "status": status, "raw_path": raw_path.name, "error": error[:1000]})
    _write_json(out_dir / "provider-query-bundle.json", {"provider": "tianyancha_api", "legal_entity": legal_entity, "calls": calls})
    return 1 if failed else 0


def collect_web_capture(legal_entity: str, out_dir: Path, provider: str, input_json: Path) -> int:
    payload = json.loads(input_json.read_text(encoding="utf-8-sig"))
    required = ("page_url", "captured_at", "legal_entity", "records")
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise SystemExit("网页取证JSON缺少字段：" + "、".join(missing))
    if str(payload["legal_entity"]).strip() != legal_entity.strip():
        raise SystemExit("网页取证主体与命令指定法律主体不一致")
    raw_path = out_dir / f"{provider}-capture.json"
    _write_json(raw_path, payload)
    _write_json(out_dir / "provider-query-bundle.json", {
        "provider": provider,
        "legal_entity": legal_entity,
        "calls": [{
            "query": legal_entity,
            "queried_at": payload["captured_at"],
            "status": "success",
            "page_url": payload["page_url"],
            "raw_path": raw_path.name,
            "record_count": len(payload.get("records", [])),
        }],
    })
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect raw commercial-provider equity evidence for later normalization and validation.")
    parser.add_argument("legal_entity")
    parser.add_argument("--provider", required=True, choices=("qcc-cli", "tianyancha-api", "qcc-web", "tianyancha-web"))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--qcc-bin", default="qcc")
    parser.add_argument("--include-history", action="store_true")
    parser.add_argument("--input-json", type=Path, help="standardized browser/crawler capture for qcc-web or tianyancha-web")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.provider == "qcc-cli":
        return collect_qcc(args.legal_entity, args.out_dir, args.qcc_bin)
    if args.provider == "tianyancha-api":
        return collect_tianyancha(args.legal_entity, args.out_dir, args.include_history)
    if not args.input_json:
        raise SystemExit("网页取证渠道必须提供 --input-json")
    return collect_web_capture(args.legal_entity, args.out_dir, args.provider.replace("-", "_"), args.input_json)


if __name__ == "__main__":
    raise SystemExit(main())
