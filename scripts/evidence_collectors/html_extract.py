"""Extract a readable, deterministic text view and document links from HTML."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse


IGNORED_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header"}
DOCUMENT_TYPES = {".pdf": "pdf", ".doc": "doc", ".docx": "docx"}


@dataclass(frozen=True)
class ExtractedHtml:
    title: str
    text: str
    attachments: list[dict[str, str]]


class _EvidenceParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.attachments: list[dict[str, str]] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in IGNORED_TAGS:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                url = urljoin(self.base_url, href)
                suffix = re.search(r"\.(pdf|docx?|PDF|DOCX?)(?:$|[?#])", url)
                if suffix:
                    self.attachments.append({"url": url, "file_type": suffix.group(1).lower()})

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if not self._ignored_depth:
            self.text_parts.append(data)


def _clean(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def extract_html(html: str, base_url: str) -> ExtractedHtml:
    parser = _EvidenceParser(base_url)
    parser.feed(html)
    parser.close()
    seen: set[tuple[str, str]] = set()
    attachments = []
    for item in parser.attachments:
        key = (item["url"], item["file_type"])
        if key not in seen:
            seen.add(key)
            attachments.append(item)
    title = _clean(parser.title_parts) or urlparse(base_url).hostname or "未命名网页"
    return ExtractedHtml(title=title, text=_clean(parser.text_parts), attachments=attachments)
