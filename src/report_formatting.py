"""Lightweight Markdown formatting for Tk previews and PDF exports."""
import re
from dataclasses import dataclass
from typing import List, Sequence, Tuple


INLINE_PATTERN = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`)")


@dataclass
class MarkdownBlock:
    kind: str
    text: str


def parse_markdown(markdown: str) -> List[MarkdownBlock]:
    blocks: List[MarkdownBlock] = []
    for raw_line in markdown.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            blocks.append(MarkdownBlock("blank", ""))
            continue
        if stripped.startswith("### "):
            blocks.append(MarkdownBlock("heading3", stripped[4:].strip()))
        elif stripped.startswith("## "):
            blocks.append(MarkdownBlock("heading2", stripped[3:].strip()))
        elif stripped.startswith("# "):
            blocks.append(MarkdownBlock("heading1", stripped[2:].strip()))
        elif stripped.startswith(("- ", "* ")):
            blocks.append(MarkdownBlock("bullet", stripped[2:].strip()))
        elif re.match(r"^\d+\.\s+", stripped):
            blocks.append(MarkdownBlock("numbered", stripped))
        else:
            blocks.append(MarkdownBlock("paragraph", stripped))
    return _compress_paragraphs(blocks)


def strip_inline_markdown(text: str) -> str:
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text


def inline_segments(text: str) -> List[Tuple[str, str]]:
    segments: List[Tuple[str, str]] = []
    parts = INLINE_PATTERN.split(text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            segments.append(("bold", part[2:-2]))
        elif part.startswith("`") and part.endswith("`"):
            segments.append(("code", part[1:-1]))
        else:
            segments.append(("text", part))
    return segments or [("text", text)]


def render_markdown_to_textbox(textbox, markdown: str):
    text_widget = getattr(textbox, "_textbox", textbox)
    _configure_text_tags(text_widget)
    textbox.configure(state="normal")
    text_widget.delete("1.0", "end")
    current_section = "body"

    for block in parse_markdown(markdown):
        if block.kind == "blank":
            text_widget.insert("end", "\n")
            continue

        prefix = ""
        block_tag = "body"
        if block.kind == "heading1":
            block_tag = "heading1"
        elif block.kind == "heading2":
            block_tag = _semantic_heading_tag(block.text)
            current_section = block_tag
        elif block.kind == "heading3":
            block_tag = _semantic_heading_tag(block.text, level=3)
        elif block.kind == "bullet":
            prefix = "• "
            block_tag = _section_body_tag(current_section)
        elif block.kind == "numbered":
            prefix = ""
            block_tag = _section_body_tag(current_section)
        else:
            block_tag = _section_body_tag(current_section)

        if prefix:
            text_widget.insert("end", prefix, (block_tag, "bullet_prefix"))

        for inline_kind, segment in inline_segments(block.text):
            tags: Sequence[str] = (block_tag,)
            if inline_kind == "bold":
                tags = (block_tag, "bold")
            elif inline_kind == "code":
                tags = (block_tag, "code")
            text_widget.insert("end", segment, tags)
        text_widget.insert("end", "\n\n" if block.kind.startswith("heading") else "\n")

    textbox.configure(state="disabled")


def _configure_text_tags(text_widget):
    text_widget.tag_config(
        "body", spacing1=4, spacing3=4, lmargin1=12, lmargin2=12,
        foreground="#1e293b", font=("Segoe UI", 11)
    )
    text_widget.tag_config(
        "heading1", font=("Segoe UI", 19, "bold"), spacing1=14, spacing3=6,
        foreground="#0f172a", lmargin1=8, lmargin2=8
    )
    text_widget.tag_config(
        "heading2", font=("Segoe UI", 15, "bold"), spacing1=10, spacing3=4,
        foreground="#0f172a", lmargin1=10, lmargin2=10
    )
    text_widget.tag_config(
        "heading3", font=("Segoe UI", 13, "bold"), spacing1=8, spacing3=3,
        foreground="#0f172a", lmargin1=10, lmargin2=10
    )
    text_widget.tag_config(
        "heading_summary", font=("Segoe UI", 15, "bold"), spacing1=10, spacing3=4,
        foreground="#0f766e", lmargin1=10, lmargin2=10
    )
    text_widget.tag_config(
        "heading_findings", font=("Segoe UI", 15, "bold"), spacing1=10, spacing3=4,
        foreground="#b45309", lmargin1=10, lmargin2=10
    )
    text_widget.tag_config(
        "heading_risks", font=("Segoe UI", 15, "bold"), spacing1=10, spacing3=4,
        foreground="#b91c1c", lmargin1=10, lmargin2=10
    )
    text_widget.tag_config(
        "heading_actions", font=("Segoe UI", 15, "bold"), spacing1=10, spacing3=4,
        foreground="#166534", lmargin1=10, lmargin2=10
    )
    text_widget.tag_config(
        "body_summary", spacing1=4, spacing3=4, lmargin1=16, lmargin2=16,
        foreground="#134e4a", font=("Segoe UI", 11)
    )
    text_widget.tag_config(
        "body_findings", spacing1=4, spacing3=4, lmargin1=16, lmargin2=16,
        foreground="#78350f", font=("Segoe UI", 11)
    )
    text_widget.tag_config(
        "body_risks", spacing1=4, spacing3=4, lmargin1=16, lmargin2=16,
        foreground="#7f1d1d", font=("Segoe UI", 11)
    )
    text_widget.tag_config(
        "body_actions", spacing1=4, spacing3=4, lmargin1=16, lmargin2=16,
        foreground="#14532d", font=("Segoe UI", 11)
    )
    text_widget.tag_config("bold", font=("Segoe UI", 11, "bold"))
    text_widget.tag_config("code", font=("Consolas", 10), background="#eef2f7", foreground="#0f172a")
    text_widget.tag_config("bullet_prefix", font=("Segoe UI", 11, "bold"))


def semantic_section_key(text: str) -> str:
    normalized = text.strip().lower()
    if any(token in normalized for token in ("resumen", "summary", "resume", "zusammenfassung", "resum", "laburpen")):
        return "summary"
    if any(token in normalized for token in ("hallazgo", "finding", "constat", "befund", "troball", "aurkikuntza")):
        return "findings"
    if any(token in normalized for token in ("riesgo", "risk", "risque", "risiko", "risc", "arrisku")):
        return "risks"
    if any(token in normalized for token in ("acci", "recomend", "action", "recommend", "aktion", "recoman", "ekintza", "gomend")):
        return "actions"
    return "default"


def _semantic_heading_tag(text: str, level: int = 2) -> str:
    key = semantic_section_key(text)
    if key == "summary":
        return "heading_summary"
    if key == "findings":
        return "heading_findings"
    if key == "risks":
        return "heading_risks"
    if key == "actions":
        return "heading_actions"
    return "heading3" if level == 3 else "heading2"


def _section_body_tag(heading_tag: str) -> str:
    mapping = {
        "heading_summary": "body_summary",
        "heading_findings": "body_findings",
        "heading_risks": "body_risks",
        "heading_actions": "body_actions",
    }
    return mapping.get(heading_tag, "body")


def _compress_paragraphs(blocks: List[MarkdownBlock]) -> List[MarkdownBlock]:
    result: List[MarkdownBlock] = []
    paragraph_parts: List[str] = []

    def flush_paragraph():
        if paragraph_parts:
            result.append(MarkdownBlock("paragraph", " ".join(paragraph_parts)))
            paragraph_parts.clear()

    for block in blocks:
        if block.kind == "paragraph":
            paragraph_parts.append(block.text)
        else:
            flush_paragraph()
            result.append(block)
    flush_paragraph()
    return result
