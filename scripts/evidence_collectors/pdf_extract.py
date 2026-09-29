"""Extract reusable page-separated UTF-8 text from text-based PDFs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXTRACTOR_VERSION = "pypdf-text-v1"


@dataclass(frozen=True)
class PdfExtraction:
    text: str
    page_count: int
    error: str = ""


def extract_pdf(path: Path) -> PdfExtraction:
    """Return embedded PDF text; a textless document is explicitly an OCR case."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return PdfExtraction("", 0, "PDF文本提取依赖缺失：请运行 scripts/ppa.py setup 完成一次性配置")
    try:
        reader = PdfReader(str(path))
        pages = []
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"--- 第 {number} 页 ---\n\n{text}")
    except Exception as error:
        return PdfExtraction("", 0, f"PDF文本提取失败：{error}")
    if not pages:
        return PdfExtraction("", len(reader.pages), "PDF未提取到可用文本；可能为扫描件，需要OCR后再取证")
    return PdfExtraction("\n\n".join(pages) + "\n", len(reader.pages))
