#!/usr/bin/env python3
"""Machine-enforced ordered workflow state for formal assessment reports."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid


STATE_FILE = "workflow-state.json"
REPORT_ARTIFACTS = (
    "report-data.json",
    "equity-evidence.json",
    "research-ledger.json",
    "policy-search-ledger.json",
    "policy-evidence.json",
)
STAGES = (
    "environment_ready",
    "entity_confirmed",
    "enterprise_research_complete",
    "equity_financial_complete",
    "industry_catalog_complete",
    "landing_businesses_complete",
    "policy_research_complete",
    "report_ready",
    "html_accepted",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def phase_seconds(payload: dict, start_stage: str, end_stage: str) -> float:
    """Return wall-clock workflow time between two completed stage receipts."""
    completed = {
        str(row.get("stage", "")): _parse_time(row.get("completed_at"))
        for row in payload.get("history", [])
        if isinstance(row, dict)
    }
    start = completed.get(start_stage)
    end = completed.get(end_stage)
    if not start or not end:
        return 0.0
    return round(max(0.0, (end - start).total_seconds()), 3)


def state_path(work_dir: Path | str) -> Path:
    return Path(work_dir).resolve() / STATE_FILE


def load(work_dir: Path | str) -> dict:
    path = state_path(work_dir)
    if not path.is_file():
        raise ValueError(f"缺少流程状态文件：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"流程状态文件无法读取：{error}") from error
    if not isinstance(payload, dict):
        raise ValueError("流程状态文件必须是JSON对象")
    return payload


def save(work_dir: Path | str, payload: dict) -> Path:
    path = state_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def create(work_dir: Path | str, enterprise: str, skill_fingerprint: str) -> dict:
    path = state_path(work_dir)
    if path.exists():
        raise ValueError(f"流程状态已存在，拒绝覆盖：{path}")
    now = _now()
    payload = {
        "schema_version": "1.0",
        "run_id": str(uuid.uuid4()),
        "enterprise": enterprise.strip(),
        "skill_fingerprint": skill_fingerprint,
        "created_at": now,
        "updated_at": now,
        "current_stage": STAGES[0],
        "completed_stages": [STAGES[0]],
        "history": [{"stage": STAGES[0], "completed_at": now, "receipt": {"runtime": "verified"}}],
        "ready_artifact_hashes": {},
        "delivery": {},
    }
    save(work_dir, payload)
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hashes(work_dir: Path | str) -> dict[str, str]:
    root = Path(work_dir).resolve()
    missing = [name for name in REPORT_ARTIFACTS if not (root / name).is_file()]
    if missing:
        raise ValueError("缺少同轮正式台账：" + "、".join(missing))
    return {name: _sha256(root / name) for name in REPORT_ARTIFACTS}


def next_stage(payload: dict) -> str | None:
    current = str(payload.get("current_stage", ""))
    if current not in STAGES:
        raise ValueError(f"未知流程阶段：{current or '空'}")
    index = STAGES.index(current)
    return STAGES[index + 1] if index + 1 < len(STAGES) else None


def complete_stage(work_dir: Path | str, stage: str, receipt: dict) -> dict:
    payload = load(work_dir)
    expected = next_stage(payload)
    if expected != stage:
        raise ValueError(f"不得跳步或重复完成；当前阶段为{payload.get('current_stage')}，下一阶段只能是{expected or '无'}")
    now = _now()
    previous_completed_at = payload.get("history", [{}])[-1].get("completed_at", payload.get("created_at", now))
    started = _parse_time(previous_completed_at) or datetime.now(timezone.utc)
    completed = _parse_time(now) or started
    payload["current_stage"] = stage
    payload.setdefault("completed_stages", []).append(stage)
    payload.setdefault("history", []).append({
        "stage": stage,
        "started_at": previous_completed_at,
        "completed_at": now,
        "elapsed_seconds": round(max(0.0, (completed - started).total_seconds()), 3),
        "receipt": receipt,
    })
    payload["updated_at"] = now
    if stage == "report_ready":
        expected_names = set(REPORT_ARTIFACTS)
        if set(receipt) != expected_names or any(not str(receipt.get(name, "")).strip() for name in expected_names):
            raise ValueError("report_ready必须绑定五份同轮台账的SHA-256")
        payload["ready_artifact_hashes"] = dict(receipt)
    save(work_dir, payload)
    return payload


def refresh_report_ready(work_dir: Path | str, receipt: dict) -> dict:
    """Revalidate a corrected report without permitting an arbitrary stage rewind."""
    payload = load(work_dir)
    if payload.get("current_stage") not in {"report_ready", "html_accepted"}:
        raise ValueError("只有已到达report_ready的项目可以重新验证最终台账")
    expected_names = set(REPORT_ARTIFACTS)
    if set(receipt) != expected_names or any(not str(receipt.get(name, "")).strip() for name in expected_names):
        raise ValueError("重新验证report_ready必须绑定五份同轮台账的SHA-256")
    now = _now()
    payload["current_stage"] = "report_ready"
    payload["completed_stages"] = list(STAGES[: STAGES.index("report_ready") + 1])
    payload["ready_artifact_hashes"] = dict(receipt)
    payload["delivery"] = {}
    payload.setdefault("history", []).append({"stage": "report_ready", "completed_at": now, "receipt": receipt, "revalidated": True})
    payload["updated_at"] = now
    save(work_dir, payload)
    return payload


def ready_state_errors(work_dir: Path | str, skill_fingerprint: str) -> list[str]:
    try:
        payload = load(work_dir)
    except ValueError as error:
        return [str(error)]
    errors: list[str] = []
    current = str(payload.get("current_stage", ""))
    if current not in {"report_ready", "html_accepted"}:
        errors.append(f"流程尚未到达report_ready：当前为{current or '空'}")
    if current in STAGES:
        expected_completed = list(STAGES[: STAGES.index(current) + 1])
        if payload.get("completed_stages") != expected_completed:
            errors.append("流程阶段记录不完整或顺序被修改")
    if not str(payload.get("run_id", "")).strip() or not str(payload.get("enterprise", "")).strip():
        errors.append("流程状态缺少run_id或企业主体")
    if payload.get("skill_fingerprint") != skill_fingerprint:
        errors.append("Skill版本已变化，必须重新开始本轮正式报告或重新完成阶段门禁")
    expected = payload.get("ready_artifact_hashes")
    if not isinstance(expected, dict) or set(expected) != set(REPORT_ARTIFACTS):
        errors.append("缺少report_ready五台账指纹回执")
        return errors
    try:
        current_hashes = artifact_hashes(work_dir)
    except ValueError as error:
        errors.append(str(error))
        return errors
    for name in REPORT_ARTIFACTS:
        if current_hashes.get(name) != expected.get(name):
            errors.append(f"report_ready后{name}发生变化，必须重新完成最终门禁")
    return errors


def artifact_path_errors(work_dir: Path | str, supplied: dict[str, str | Path]) -> list[str]:
    root = Path(work_dir).resolve()
    errors: list[str] = []
    for name in REPORT_ARTIFACTS:
        actual = Path(supplied.get(name, "")).resolve()
        expected = (root / name).resolve()
        if actual != expected:
            errors.append(f"{name}必须来自workflow-state.json所在工作目录：{expected}")
    return errors


def mark_html_accepted(work_dir: Path | str, html_path: Path | str) -> dict:
    payload = load(work_dir)
    errors = ready_state_errors(work_dir, str(payload.get("skill_fingerprint", "")))
    if errors:
        raise ValueError("；".join(errors))
    html = Path(html_path).resolve()
    if not html.is_file():
        raise ValueError(f"HTML交付物不存在：{html}")
    if payload.get("current_stage") == "html_accepted":
        now = _now()
        receipt = {"html_path": str(html), "sha256": _sha256(html)}
        payload["delivery"] = receipt
        payload.setdefault("history", []).append({"stage": "html_accepted", "completed_at": now, "receipt": receipt, "revalidated": True})
        payload["updated_at"] = now
        save(work_dir, payload)
        return payload
    payload = complete_stage(work_dir, "html_accepted", {"html_path": str(html), "sha256": _sha256(html)})
    payload["delivery"] = payload["history"][-1]["receipt"]
    save(work_dir, payload)
    return payload
