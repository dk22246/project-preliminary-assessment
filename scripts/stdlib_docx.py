"""Pure-standard-library OOXML (.docx) writer.

Replaces python-docx so the Word renderer has zero third-party runtime
dependencies.  A .docx file is just a ZIP of XML parts; this module builds
those parts with `zipfile` + string templating (no lxml, no C extensions),
which keeps deployment identical across OS / Python versions.
"""
from __future__ import annotations

from pathlib import Path
import struct
from xml.sax.saxutils import escape
import zipfile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def cm_to_dxa(cm: float) -> int:
    """Centimetres -> twentieths of a point (dxa/twips), the OOXML page unit."""
    return round(cm * 567)


def pt_to_half(pt: float) -> int:
    """Points -> half-points, the OOXML font-size unit."""
    return round(pt * 2)


def _fonts(chinese: str = "宋体", ascii_font: str = "Arial") -> str:
    return (
        '<w:rFonts w:ascii="' + ascii_font + '" w:hAnsi="' + ascii_font + '" '
        + 'w:eastAsia="' + chinese + '" w:cs="' + ascii_font + '"/>'
    )


class Font:
    def __init__(self, chinese: str = "宋体", ascii_font: str = "Arial", size: float = 12, bold: bool = False):
        self.chinese = chinese
        self.ascii_font = ascii_font
        self.size = size
        self.bold = bold


class Run:
    def __init__(self, text: str = "", font: Font | None = None):
        self.text = text
        self.font = font or Font()

    def xml(self) -> str:
        sz = str(pt_to_half(self.font.size))
        bold = "<w:b/><w:bCs/>" if self.font.bold else ""
        return (
            "<w:r><w:rPr>"
            + _fonts(self.font.chinese, self.font.ascii_font)
            + '<w:sz w:val="' + sz + '"/><w:szCs w:val="' + sz + '"/>' + bold + '</w:rPr>'
            + '<w:t xml:space="preserve">' + escape(self.text or "") + '</w:t></w:r>'
        )


class PageBreakRun:
    def xml(self) -> str:
        return '<w:r><w:br w:type="page"/></w:r>'


class FieldRun:
    """A simple begin/instrText/separate/end field (e.g. PAGE)."""

    def __init__(self, instruction: str, cached: str = ""):
        self.instruction = instruction
        self.cached = cached

    def xml(self) -> str:
        return (
            '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            + '<w:r><w:instrText xml:space="preserve">' + escape(self.instruction) + '</w:instrText></w:r>'
            + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            + '<w:r><w:t xml:space="preserve">' + escape(self.cached) + '</w:t></w:r>'
            + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
        )


class Paragraph:
    def __init__(
        self,
        *,
        style: str | None = None,
        alignment: str | None = None,  # left | center | right | both
        first_line_indent: int | None = None,
        line_spacing: int | None = None,  # 240 = single, 360 = 1.5x
        space_before: int | None = None,
        space_after: int | None = None,
        keep_next: bool = False,
    ):
        self.style = style
        self.alignment = alignment
        self.first_line_indent = first_line_indent
        self.line_spacing = line_spacing
        self.space_before = space_before
        self.space_after = space_after
        self.keep_next = keep_next
        self.runs: list = []

    def add_run(self, text: str = "", font: Font | None = None) -> Run:
        run = Run(text, font)
        self.runs.append(run)
        return run

    def add_page_break(self) -> None:
        self.runs.append(PageBreakRun())

    def xml(self) -> str:
        parts = ["<w:pPr>"]
        if self.style:
            parts.append('<w:pStyle w:val="' + escape(self.style) + '"/>')
        if self.alignment:
            parts.append('<w:jc w:val="' + self.alignment + '"/>')
        if self.first_line_indent is not None:
            parts.append('<w:ind w:firstLine="' + str(self.first_line_indent) + '" w:firstLineChars="200"/>')
        spacing_attrs = []
        if self.line_spacing is not None:
            spacing_attrs.append('w:line="' + str(self.line_spacing) + '" w:lineRule="auto"')
        if self.space_before is not None:
            spacing_attrs.append('w:before="' + str(self.space_before) + '"')
        if self.space_after is not None:
            spacing_attrs.append('w:after="' + str(self.space_after) + '"')
        if spacing_attrs:
            parts.append("<w:spacing " + " ".join(spacing_attrs) + "/>")
        if self.keep_next:
            parts.append("<w:keepNext/>")
        parts.append("</w:pPr>")
        parts.append("".join(run.xml() for run in self.runs))
        return "<w:p>" + "".join(parts) + "</w:p>"


class Table:
    def __init__(
        self,
        headers: list[str],
        rows: list[list[str]],
        widths_cm: list[float],
        *,
        centered_columns: set[int] = (),
        numeric_columns: set[int] = (),
        header_fill: str = "E7E6E6",
        border_color: str = "595959",
    ):
        self.headers = headers
        self.rows = rows
        self.widths_cm = widths_cm
        self.centered = set(centered_columns)
        self.numeric = set(numeric_columns)
        self.header_fill = header_fill
        self.border_color = border_color

    def _cell(self, text: str, *, width_dxa: int, bold: bool = False, fill: str | None = None, align: str = "left") -> str:
        sz = str(pt_to_half(10.5))
        bold_tag = "<w:b/><w:bCs/>" if bold else ""
        fill_xml = '<w:shd w:val="clear" w:color="auto" w:fill="' + fill + '"/>' if fill else ""
        return (
            '<w:tc><w:tcPr><w:tcW w:w="' + str(width_dxa) + '" w:type="dxa"/>'
            + '<w:vAlign w:val="center"/>'
            + '<w:tcMar><w:top w:w="90" w:type="dxa"/><w:start w:w="110" w:type="dxa"/>'
            + '<w:bottom w:w="90" w:type="dxa"/><w:end w:w="110" w:type="dxa"/></w:tcMar>'
            + fill_xml
            + '</w:tcPr><w:p><w:pPr><w:jc w:val="' + align + '"/>'
            + '<w:spacing w:line="240" w:lineRule="auto" w:before="0" w:after="0"/></w:pPr>'
            + '<w:r><w:rPr>' + _fonts("宋体", "Arial")
            + '<w:sz w:val="' + sz + '"/><w:szCs w:val="' + sz + '"/>' + bold_tag + '</w:rPr>'
            + '<w:t xml:space="preserve">' + escape(text) + '</w:t></w:r></w:p></w:tc>'
        )

    def xml(self) -> str:
        widths = [cm_to_dxa(w) for w in self.widths_cm]
        total = sum(widths)
        grid = "".join('<w:gridCol w:w="' + str(w) + '"/>' for w in widths)
        border_sides = ("top", "left", "bottom", "right", "insideH", "insideV")
        borders = "<w:tblBorders>" + "".join(
            '<w:' + side + ' w:val="single" w:sz="4" w:space="0" w:color="' + self.border_color + '"/>'
            for side in border_sides
        ) + "</w:tblBorders>"
        tbl_pr = (
            '<w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="' + str(total) + '" w:type="dxa"/>'
            + '<w:tblLayout w:type="fixed"/>' + borders + '<w:tblLook w:val="04A0"/></w:tblPr>'
        )
        header_cells = "".join(
            self._cell(h, width_dxa=widths[i], bold=True, fill=self.header_fill, align="center")
            for i, h in enumerate(self.headers)
        )
        header_row = "<w:tr><w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>" + header_cells + "</w:tr>"
        data_rows = []
        for values in self.rows:
            cells = []
            for i, value in enumerate(values):
                if i in self.numeric:
                    align = "right"
                elif i in self.centered:
                    align = "center"
                else:
                    align = "left"
                cells.append(self._cell(str(value), width_dxa=widths[i], align=align))
            data_rows.append("<w:tr><w:trPr><w:cantSplit/></w:trPr>" + "".join(cells) + "</w:tr>")
        return "<w:tbl>" + tbl_pr + "<w:tblGrid>" + grid + "</w:tblGrid>" + header_row + "".join(data_rows) + "</w:tbl>"


class Picture:
    def __init__(self, image_bytes: bytes, rel_id: str, width_cm: float):
        self.image_bytes = image_bytes
        self.rel_id = rel_id
        self.width_cm = width_cm
        self.doc_pr_id = int(rel_id.replace("rIdImage", "") or "1")
        self.width_emu, self.height_emu = self._scaled_emu()

    @staticmethod
    def _png_size(data: bytes) -> tuple[int, int]:
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return 800, 600
        width, height = struct.unpack(">II", data[16:24])
        return width, height

    def _scaled_emu(self) -> tuple[int, int]:
        w_px, h_px = self._png_size(self.image_bytes)
        width_emu = int(self.width_cm * 360000)
        height_emu = int(width_emu * h_px / max(1, w_px))
        return width_emu, height_emu

    def xml(self) -> str:
        w = str(self.width_emu)
        h = str(self.height_emu)
        pid = str(self.doc_pr_id)
        return (
            '<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            + '<wp:inline distT="0" distB="0" distL="0" distR="0">'
            + '<wp:extent cx="' + w + '" cy="' + h + '"/>'
            + '<wp:docPr id="' + pid + '" name="Picture ' + pid + '"/>'
            + '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            + '<pic:pic><pic:nvPicPr><pic:cNvPr id="' + pid + '" name="Picture ' + pid + '"/><pic:cNvPicPr/></pic:nvPicPr>'
            + '<pic:blipFill><a:blip r:embed="' + self.rel_id + '"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            + '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="' + w + '" cy="' + h + '"/></a:xfrm>'
            + '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            + '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
        )


class RawBlock:
    """Arbitrary pre-built OOXML body fragment (e.g. TOC field)."""

    def __init__(self, xml: str):
        self.xml_fragment = xml

    def xml(self) -> str:
        return self.xml_fragment


class Document:
    def __init__(self):
        self._body: list = []
        self._media: list[tuple[str, bytes]] = []
        self.header_text: str = ""
        self.header_alignment: str = "right"
        self.has_footer_page: bool = False
        self.page_w_dxa = cm_to_dxa(21.0)
        self.page_h_dxa = cm_to_dxa(29.7)
        self.margins = {"top": cm_to_dxa(2.5), "bottom": cm_to_dxa(2.5), "left": cm_to_dxa(2.8), "right": cm_to_dxa(2.5), "header": cm_to_dxa(1.5), "footer": cm_to_dxa(1.5)}
        self.title_page = False

    # ---- content builders -------------------------------------------------
    def add_paragraph(self, **kwargs) -> Paragraph:
        p = Paragraph(**kwargs)
        self._body.append(p)
        return p

    def add_heading(self, text: str, level: int) -> Paragraph:
        p = Paragraph(style="Heading" + str(level), keep_next=True)
        p.add_run(text, Font(chinese="黑体" if level <= 2 else "宋体", size=16 if level == 1 else 14 if level == 2 else 12, bold=True))
        self._body.append(p)
        return p

    def add_page_break(self) -> Paragraph:
        p = Paragraph()
        p.add_page_break()
        self._body.append(p)
        return p

    def add_table(self, headers, rows, widths_cm, **kwargs) -> Table:
        t = Table(headers, rows, widths_cm, **kwargs)
        self._body.append(t)
        return t

    def add_picture(self, image_path: str, width_cm: float) -> None:
        data = Path(image_path).read_bytes()
        filename = "image" + str(len(self._media) + 1) + ".png"
        self._media.append((filename, data))
        rel_id = "rIdImage" + str(len(self._media))
        self._body.append(Picture(data, rel_id, width_cm))

    def add_toc_field(self, entries: list[tuple[str, int]]) -> None:
        lines = []
        for i, (label, page) in enumerate(entries):
            line = str(label) + (" " * max(2, 44 - len(label))) + str(page)
            if i < len(entries) - 1:
                line += "<w:br/>"
            lines.append('<w:r><w:t xml:space="preserve">' + escape(line) + '</w:t></w:r>')
        xml = (
            '<w:p><w:fldSimple w:instr="TOC \\o &quot;1-2&quot; \\h \\z \\u">'
            + "".join(lines)
            + "</w:fldSimple></w:p>"
        )
        self._body.append(RawBlock(xml))

    # ---- section helpers ---------------------------------------------------
    def configure_section(self, *, landscape: bool = False, top=2.5, bottom=2.5, left=2.8, right=2.5, header=1.5, footer=1.5) -> None:
        if landscape:
            self.page_w_dxa, self.page_h_dxa = cm_to_dxa(29.7), cm_to_dxa(21.0)
        else:
            self.page_w_dxa, self.page_h_dxa = cm_to_dxa(21.0), cm_to_dxa(29.7)
        self.margins = {"top": cm_to_dxa(top), "bottom": cm_to_dxa(bottom), "left": cm_to_dxa(left), "right": cm_to_dxa(right), "header": cm_to_dxa(header), "footer": cm_to_dxa(footer)}

    def set_header(self, text: str, alignment: str = "right") -> None:
        self.header_text = text
        self.header_alignment = alignment

    def set_footer_page_number(self) -> None:
        self.has_footer_page = True

    # ---- serialization ------------------------------------------------------
    def _body_xml(self) -> str:
        return "".join(block.xml() for block in self._body)

    def _sect_pr(self) -> str:
        parts = []
        if self.header_text:
            parts.append('<w:headerReference w:type="default" r:id="rIdHeader"/>')
        if self.has_footer_page:
            parts.append('<w:footerReference w:type="default" r:id="rIdFooter"/>')
        parts.append('<w:pgSz w:w="' + str(self.page_w_dxa) + '" w:h="' + str(self.page_h_dxa) + '"/>')
        m = self.margins
        parts.append(
            '<w:pgMar w:top="' + str(m["top"]) + '" w:right="' + str(m["right"]) + '" w:bottom="' + str(m["bottom"]) + '" '
            + 'w:left="' + str(m["left"]) + '" w:header="' + str(m["header"]) + '" w:footer="' + str(m["footer"]) + '" w:gutter="0"/>'
        )
        if self.title_page:
            parts.append("<w:titlePg/>")
        return "<w:sectPr>" + "".join(parts) + "</w:sectPr>"

    def _document_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<w:document xmlns:w="' + W_NS + '" xmlns:r="' + R_NS + '" '
            + 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            + 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            + 'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            + "<w:body>" + self._body_xml() + self._sect_pr() + "</w:body></w:document>"
        )

    def _header_xml(self) -> str:
        run = Run(self.header_text, Font(chinese="宋体", ascii_font="Arial", size=10.5))
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<w:hdr xmlns:w="' + W_NS + '">'
            + '<w:p><w:pPr><w:jc w:val="' + self.header_alignment + '"/></w:pPr>' + run.xml() + '</w:p></w:hdr>'
        )

    def _footer_xml(self) -> str:
        font = Font(chinese="宋体", ascii_font="Arial", size=10.5)
        pre = Run("第 ", font)
        page = FieldRun(" PAGE ", "1")
        post = Run(" 页", font)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<w:ftr xmlns:w="' + W_NS + '">'
            + '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>' + pre.xml() + page.xml() + post.xml() + '</w:p></w:ftr>'
        )

    def _styles_xml(self) -> str:
        def heading_style(style_id: str, outline: int, size_pt: float, chinese: str) -> str:
            sz = str(pt_to_half(size_pt))
            before = {0: 240, 1: 160, 2: 120}[outline]
            after = {0: 120, 1: 80, 2: 60}[outline]
            return (
                '<w:style w:type="paragraph" w:styleId="' + style_id + '">'
                + '<w:name w:val="' + style_id + '"/>'
                + '<w:basedOn w:val="Normal"/>'
                + '<w:pPr><w:keepNext/><w:spacing w:before="' + str(before) + '" w:after="' + str(after) + '"/>'
                + '<w:outlineLvl w:val="' + str(outline) + '"/></w:pPr>'
                + '<w:rPr><w:b/><w:bCs/>' + _fonts(chinese, "Arial")
                + '<w:sz w:val="' + sz + '"/><w:szCs w:val="' + sz + '"/></w:rPr>'
                + '</w:style>'
            )

        border_sides = ("top", "left", "bottom", "right", "insideH", "insideV")
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<w:styles xmlns:w="' + W_NS + '">'
            + '<w:docDefaults><w:rPrDefault><w:rPr>' + _fonts("宋体", "Arial")
            + '<w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults>'
            + '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
            + '<w:pPr><w:spacing w:line="360" w:lineRule="auto" w:after="120"/>'
            + '<w:ind w:firstLine="420" w:firstLineChars="200"/></w:pPr>'
            + '<w:rPr>' + _fonts("宋体", "Arial") + '<w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>'
            + heading_style("Heading1", 0, 16, "黑体")
            + heading_style("Heading2", 1, 14, "黑体")
            + heading_style("Heading3", 2, 12, "宋体")
            + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
            + '<w:tblPr><w:tblBorders>' + "".join(
                '<w:' + side + ' w:val="single" w:sz="4" w:space="0" w:color="auto"/>' for side in border_sides
            ) + '</w:tblBorders></w:tblPr></w:style>'
            + '</w:styles>'
        )

    def _settings_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<w:settings xmlns:w="' + W_NS + '"><w:updateFields w:val="true"/></w:settings>'
        )

    def _content_types_xml(self) -> str:
        overrides = [
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>',
            '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>',
        ]
        if self.header_text:
            overrides.append('<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>')
        if self.has_footer_page:
            overrides.append('<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            + '<Default Extension="xml" ContentType="application/xml"/>'
            + '<Default Extension="png" ContentType="image/png"/>'
            + "".join(overrides)
            + '</Types>'
        )

    def _rels_xml(self) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            + '</Relationships>'
        )

    def _document_rels_xml(self) -> str:
        parts = [
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
            '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>',
        ]
        if self.header_text:
            parts.append('<Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>')
        if self.has_footer_page:
            parts.append('<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>')
        for i, (filename, _) in enumerate(self._media, 1):
            parts.append('<Relationship Id="rIdImage' + str(i) + '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/' + filename + '"/>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(parts)
            + '</Relationships>'
        )

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self._content_types_xml())
            zf.writestr("_rels/.rels", self._rels_xml())
            zf.writestr("word/document.xml", self._document_xml())
            zf.writestr("word/_rels/document.xml.rels", self._document_rels_xml())
            zf.writestr("word/styles.xml", self._styles_xml())
            zf.writestr("word/settings.xml", self._settings_xml())
            if self.header_text:
                zf.writestr("word/header1.xml", self._header_xml())
            if self.has_footer_page:
                zf.writestr("word/footer1.xml", self._footer_xml())
            for filename, data in self._media:
                zf.writestr("word/media/" + filename, data)


def set_update_fields(path: str | Path) -> None:
    """Ensure settings.xml carries updateFields=true by rewriting the ZIP in place."""
    path = Path(path)
    tmp = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(path, "r") as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "word/settings.xml":
                text = data.decode("utf-8")
                if "updateFields" not in text:
                    text = text.replace("</w:settings>", '<w:updateFields w:val="true"/></w:settings>')
                data = text.encode("utf-8")
            dst.writestr(item, data)
    tmp.replace(path)
