#!/usr/bin/env python3
"""Build the portable JSON industry-catalog library from the canonical XLSX."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = ROOT / "references" / "catalogs" / "hainan-ftz-encouraged-industry-complete-library.xlsx"
DEFAULT_OUTPUT = ROOT / "references" / "catalogs" / "complete-industry-catalog-library.json"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - 64
    return value - 1


def _value(cell: ET.Element, shared: list[str]) -> object:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", NS))
    node = cell.find("m:v", NS)
    if node is None or node.text is None:
        return ""
    raw = node.text
    if cell_type == "s":
        return shared[int(raw)]
    if cell_type in {"str", "b", "e"}:
        return raw
    try:
        number = float(raw)
        return int(number) if number.is_integer() else number
    except ValueError:
        return raw


def read_xlsx(workbook_path: Path) -> dict[str, list[list[object]]]:
    with zipfile.ZipFile(workbook_path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.text or "" for node in item.findall(".//m:t", NS)) for item in root.findall("m:si", NS)]

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {item.attrib["Id"]: item.attrib["Target"] for item in rels.findall("r:Relationship", REL_NS)}
        sheets: dict[str, list[list[object]]] = {}
        for item in workbook.findall("m:sheets/m:sheet", NS):
            name = item.attrib["name"]
            target = targets[item.attrib[DOC_REL]].lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            root = ET.fromstring(archive.read(target))
            rows: list[list[object]] = []
            for row in root.findall("m:sheetData/m:row", NS):
                values: list[object] = []
                for cell in row.findall("m:c", NS):
                    index = _column_index(cell.attrib["r"])
                    if len(values) <= index:
                        values.extend([""] * (index + 1 - len(values)))
                    values[index] = _value(cell, shared)
                rows.append(values)
            sheets[name] = rows
    return sheets


def _text(value: object) -> str:
    return str(value or "").strip()


def _number(value: object) -> int:
    return int(float(str(value)))


def build_library(workbook_path: Path) -> dict:
    sheets = read_xlsx(workbook_path)
    required = {
        "产业结构2024", "外商投资全国2025", "外商投资地区2025",
        "海南外资2025", "海南新增2024", "海南新增界定指引", "海南适用检索",
    }
    missing = sorted(required - sheets.keys())
    if missing:
        raise ValueError("统一工作簿缺少Sheet：" + "、".join(missing))

    details_by_item: dict[int, list[dict]] = {}
    for row_number, row in enumerate(sheets["海南新增界定指引"][1:], start=2):
        item_no = _number(row[1])
        details_by_item.setdefault(item_no, []).append({
            "detail_title": _text(row[3]),
            "definition": _text(row[4]),
            "source_row": _number(row[5]),
        })

    entries: list[dict] = []
    domestic_positive: list[str] = []
    foreign_positive: list[str] = []
    industrial_conflicts: list[str] = []
    category_map = {"鼓励类": "encouraged", "限制类": "restricted", "淘汰类": "eliminated"}

    for row_number, row in enumerate(sheets["产业结构2024"][1:], start=2):
        category = category_map[_text(row[0])]
        entry_id = f"industrial_restructuring_2024:{row_number}"
        entry = {
            "id": entry_id,
            "catalog_scope": "industrial_restructuring_2024",
            "policy_category": category,
            "section": _text(row[2]),
            "subsection": _text(row[1]),
            "item_no": _number(row[3]),
            "item_title": _text(row[4]),
            "region": "全国",
            "source_sheet": "产业结构2024",
            "source_row": row_number,
            "source_url": _text(row[5]),
        }
        entries.append(entry)
        (domestic_positive if category == "encouraged" else industrial_conflicts).append(entry_id)

    for row_number, row in enumerate(sheets["海南新增2024"][1:], start=2):
        item_no = _number(row[1])
        entry_id = f"hainan_added_2024:{item_no}"
        entries.append({
            "id": entry_id,
            "catalog_scope": "hainan_added_2024",
            "policy_category": "encouraged",
            "section": _text(row[0]),
            "subsection": "",
            "item_no": item_no,
            "item_title": _text(row[2]),
            "region": "海南省",
            "detail_entries": details_by_item.get(item_no, []),
            "source_sheet": "海南新增2024",
            "source_row": row_number,
            "source_url": _text(row[3]),
        })
        domestic_positive.append(entry_id)

    for row_number, row in enumerate(sheets["外商投资全国2025"][1:], start=2):
        item_no = _number(row[3])
        entry_id = f"foreign_investment_national_2025:{item_no}"
        entries.append({
            "id": entry_id,
            "catalog_scope": "foreign_investment_national_2025",
            "policy_category": "encouraged",
            "section": _text(row[1]),
            "subsection": _text(row[2]),
            "item_no": item_no,
            "item_title": _text(row[4]),
            "region": "全国",
            "source_sheet": "外商投资全国2025",
            "source_row": row_number,
            "source_url": _text(row[5]),
        })
        foreign_positive.append(entry_id)

    hainan_regional_ids: list[str] = []
    for row_number, row in enumerate(sheets["外商投资地区2025"][1:], start=2):
        region = _text(row[1])
        item_no = _number(row[2])
        entry_id = f"foreign_investment_regional_2025:{region}:{item_no}"
        entries.append({
            "id": entry_id,
            "catalog_scope": "foreign_investment_regional_2025",
            "policy_category": "encouraged",
            "section": "地区优势产业",
            "subsection": "",
            "item_no": item_no,
            "item_title": _text(row[3]),
            "region": region,
            "source_sheet": "外商投资地区2025",
            "source_row": row_number,
            "source_url": _text(row[4]),
        })
        if region == "海南省":
            hainan_regional_ids.append(entry_id)
            foreign_positive.append(entry_id)

    hainan_view = [(_number(row[1]), _text(row[2])) for row in sheets["海南外资2025"][1:]]
    regional_view = [
        (item["item_no"], item["item_title"])
        for item in entries
        if item["catalog_scope"] == "foreign_investment_regional_2025" and item["region"] == "海南省"
    ]
    if hainan_view != regional_view:
        raise ValueError("海南外资2025视图与外商投资地区2025中的海南省条目不一致")

    counts = {
        "industrial_restructuring_2024": {
            "total": 1005,
            "encouraged": len(domestic_positive) - len(sheets["海南新增2024"]) + 1,
            "restricted": sum(item["policy_category"] == "restricted" for item in entries),
            "eliminated": sum(item["policy_category"] == "eliminated" for item in entries),
        },
        "foreign_investment_national_2025": len(sheets["外商投资全国2025"]) - 1,
        "foreign_investment_regional_2025": len(sheets["外商投资地区2025"]) - 1,
        "foreign_investment_hainan_2025": len(hainan_regional_ids),
        "hainan_added_2024": len(sheets["海南新增2024"]) - 1,
        "hainan_added_guide_details": sum(len(value) for value in details_by_item.values()),
    }
    return {
        "schema_version": "1.0",
        "generated_from": workbook_path.name,
        "source_workbook_sha256": hashlib.sha256(workbook_path.read_bytes()).hexdigest(),
        "subject_routes": {
            "domestic": "产业结构调整指导目录鼓励类 + 海南新增鼓励类",
            "foreign": "全国鼓励外商投资产业目录 + 海南省外商投资优势产业",
            "conflict_check": "产业结构调整指导目录限制类、淘汰类",
        },
        "counts": counts,
        "routes": {
            "domestic_positive": domestic_positive,
            "foreign_positive": foreign_positive,
            "industrial_conflicts": industrial_conflicts,
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_library(args.workbook.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": payload["counts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
