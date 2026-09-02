"""Export Markdown reports to PDF without external runtime dependencies."""
from textwrap import wrap
from typing import List, Tuple

from .report_formatting import parse_markdown, strip_inline_markdown


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN_X = 54
TOP_Y = 750
BOTTOM_MARGIN = 54
BODY_FONT_SIZE = 11
TITLE_FONT_SIZE = 18
H2_FONT_SIZE = 14
H3_FONT_SIZE = 12
LINE_HEIGHT = 15
MAX_CHARS_PER_LINE = 90


def export_text_pdf(path: str, title: str, body: str):
    export_markdown_pdf(path, title, body)


def export_markdown_pdf(path: str, title: str, markdown: str):
    pages = _paginate(title, markdown)
    pdf_bytes = _build_pdf(title, pages)
    with open(path, "wb") as f:
        f.write(pdf_bytes)


def _paginate(title: str, markdown: str) -> List[List[Tuple[str, int, int]]]:
    blocks = parse_markdown(markdown)
    lines: List[Tuple[str, int, int]] = [(title, TITLE_FONT_SIZE, MARGIN_X), ("", BODY_FONT_SIZE, MARGIN_X)]

    for block in blocks:
        if block.kind == "blank":
            lines.append(("", BODY_FONT_SIZE, MARGIN_X))
            continue

        text = strip_inline_markdown(block.text)
        if block.kind == "heading1":
            lines.extend(_wrap_block(text, TITLE_FONT_SIZE, MARGIN_X))
            lines.append(("", BODY_FONT_SIZE, MARGIN_X))
        elif block.kind == "heading2":
            lines.extend(_wrap_block(text, H2_FONT_SIZE, MARGIN_X))
            lines.append(("", BODY_FONT_SIZE, MARGIN_X))
        elif block.kind == "heading3":
            lines.extend(_wrap_block(text, H3_FONT_SIZE, MARGIN_X))
        elif block.kind == "bullet":
            lines.extend(_wrap_block(f"• {text}", BODY_FONT_SIZE, MARGIN_X + 10))
        elif block.kind == "numbered":
            lines.extend(_wrap_block(text, BODY_FONT_SIZE, MARGIN_X + 6))
        else:
            lines.extend(_wrap_block(text, BODY_FONT_SIZE, MARGIN_X))
        lines.append(("", BODY_FONT_SIZE, MARGIN_X))

    lines_per_page = int((TOP_Y - BOTTOM_MARGIN) / LINE_HEIGHT)
    if lines_per_page < 1:
        lines_per_page = 1

    pages = []
    for idx in range(0, max(len(lines), 1), lines_per_page):
        chunk = lines[idx:idx + lines_per_page]
        if not chunk:
            chunk = [("", BODY_FONT_SIZE, MARGIN_X)]
        pages.append(chunk)
    return pages


def _wrap_block(text: str, font_size: int, x: int) -> List[Tuple[str, int, int]]:
    width = max(20, MAX_CHARS_PER_LINE - max(0, (x - MARGIN_X) // 4))
    wrapped = wrap(text, width=width, replace_whitespace=False) or [text]
    return [(line, font_size, x) for line in wrapped]


def _build_pdf(title: str, pages: List[List[Tuple[str, int, int]]]) -> bytes:
    objects: List[bytes] = []

    def add_object(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    catalog_id = add_object(b"")
    pages_id = add_object(b"")
    font_id = add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )

    page_ids = []
    for lines in pages:
        content = _page_stream(lines)
        content_obj = add_object(
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" +
            content + b"\nendstream"
        )
        page_obj = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode("latin-1")
        page_id = add_object(page_obj)
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids).encode("ascii")
    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii")
    objects[pages_id - 1] = (
        b"<< /Type /Pages /Count " + str(len(page_ids)).encode("ascii") +
        b" /Kids [" + kids + b"] >>"
    )
    info_id = add_object(
        b"<< /Title " + _pdf_string(title) + b" /Producer " + _pdf_string("Moodle Student Analyzer") + b" >>"
    )

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{idx} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        b"trailer\n<< /Size " + str(len(objects) + 1).encode("ascii") +
        b" /Root " + str(catalog_id).encode("ascii") + b" 0 R /Info " +
        str(info_id).encode("ascii") + b" 0 R >>\nstartxref\n" +
        str(xref_offset).encode("ascii") + b"\n%%EOF"
    )
    return bytes(pdf)


def _page_stream(lines: List[Tuple[str, int, int]]) -> bytes:
    commands = []
    y = TOP_Y
    for text, font_size, x in lines:
        commands.append(_text_command(text, x, y, font_size))
        y -= LINE_HEIGHT + (4 if font_size >= H2_FONT_SIZE else 0)
    return "\n".join(commands).encode("latin-1")


def _text_command(text: str, x: int, y: int, size: int) -> str:
    return f"BT /F1 {size} Tf 1 0 0 1 {x} {y} Tm {_pdf_string(text).decode('latin-1')} Tj ET"


def _pdf_string(text: str) -> bytes:
    encoded = text.encode("cp1252", errors="replace")
    escaped = (
        encoded.replace(b"\\", b"\\\\")
        .replace(b"(", b"\\(")
        .replace(b")", b"\\)")
    )
    return b"(" + escaped + b")"
