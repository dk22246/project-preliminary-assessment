"""统一的《招商项目整体落地研判报告》Word 样式与表格构建组件（纯标准库实现）。

原版依赖 python-docx（进而依赖 lxml C 扩展），换 OS / Python 版本会失效。
本模块改用 stdlib_docx（zipfile + 字符串模板），零第三方运行时依赖，
保证任意电脑部署后 Word 生成行为一致。
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from typing import Iterable, Sequence

from stdlib_docx import Document, Font, pt_to_half, set_update_fields


PAGE = {"top": 2.5, "bottom": 2.5, "left": 2.8, "right": 2.5, "header": 1.5, "footer": 1.5}
TABLE_HEADER_FILL = "E7E6E6"
TABLE_BORDER = "595959"


def configure_report_document(doc: Document, report_short_name: str) -> None:
    """应用统一A4版式、原生标题样式及页眉页脚。"""
    doc.configure_section(**PAGE)
    doc.title_page = True
    doc.set_header(report_short_name, alignment="right")
    doc.set_footer_page_number()


def add_heading(doc: Document, text: str, level: int):
    return doc.add_heading(text, level)


def add_body(doc: Document, text: str, *, centered: bool = False, role: str = "body"):
    alignment = "center" if centered else "both"
    if role == "source":
        paragraph = doc.add_paragraph(alignment=alignment, first_line_indent=0, line_spacing=240, space_after=pt_to_half(4))
        paragraph.add_run(text, Font(chinese="宋体", size=10.5))
    else:
        paragraph = doc.add_paragraph(alignment=alignment)
        paragraph.add_run(text)
    return paragraph


def add_cover_line(doc: Document, text: str, *, title: bool = False):
    paragraph = doc.add_paragraph(alignment="center", first_line_indent=0, space_before=0, space_after=pt_to_half(8 if title else 6))
    paragraph.add_run(text, Font(chinese="黑体" if title else "宋体", size=22 if title else 12, bold=title))
    return paragraph


def add_native_toc_with_cache(doc: Document, entries: Sequence[tuple[str, int]]) -> None:
    """插入可更新的Word原生TOC域，并给无自动更新环境提供可见缓存。"""
    doc.add_toc_field(list(entries))


def try_update_fields_with_word(path: Path, timeout_seconds: int = 30) -> bool:
    """用本机 Word 刷新 TOC、页码及交叉引用；不可用时保留可见 TOC 缓存。"""
    script = r'''
param([string]$DocumentPath)
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open($DocumentPath, $false, $false)
    foreach ($toc in $document.TablesOfContents) { $toc.Update() }
    foreach ($field in $document.Fields) { $field.Update() }
    $document.Save()
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if ($document -ne $null) { $document.Close(0) }
    if ($word -ne $null) { $word.Quit() }
}
'''
    temporary = tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", encoding="utf-8", delete=False)
    try:
        temporary.write(script)
        temporary.close()
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", temporary.name, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if result.returncode == 0:
            set_update_fields(path)
            return True
        return False
    except (OSError, subprocess.TimeoutExpired):
        return False
    finally:
        Path(temporary.name).unlink(missing_ok=True)


def add_standard_table(
    doc: Document,
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    widths_cm: Sequence[float],
    *,
    centered_columns: Iterable[int] = (),
    numeric_columns: Iterable[int] = (),
):
    table = doc.add_table(
        list(headers),
        [list(values) for values in rows],
        list(widths_cm),
        centered_columns=set(centered_columns),
        numeric_columns=set(numeric_columns),
        header_fill=TABLE_HEADER_FILL,
        border_color=TABLE_BORDER,
    )
    spacer = doc.add_paragraph(first_line_indent=0, space_after=pt_to_half(4))
    spacer.add_run("")
    return table
