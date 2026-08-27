"""Render the reconstructed Markdown paper to a polished ReportLab PDF."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#556070")
ACCENT = colors.HexColor("#0f766e")
PALE = colors.HexColor("#e8f3f1")
GRID = colors.HexColor("#c7d2d9")


def _inline(text: str) -> str:
    value = html.escape(text.strip())
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', value)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#0f766e">\1</link>', value)
    return value


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PaperTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=27,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "PaperSubtitle",
            parent=base["Heading2"],
            fontName="Helvetica",
            fontSize=13,
            leading=17,
            textColor=ACCENT,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            textColor=INK,
            spaceBefore=12,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=ACCENT,
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-BoldOblique",
            fontSize=10.5,
            leading=13,
            textColor=INK,
            spaceBefore=7,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=9.4,
            leading=12.1,
            alignment=TA_JUSTIFY,
            textColor=INK,
            spaceAfter=5.5,
            splitLongWords=True,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            alignment=TA_CENTER,
            textColor=MUTED,
            spaceAfter=2,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["BodyText"],
            fontName="Times-Roman",
            fontSize=9.3,
            leading=11.8,
            leftIndent=17,
            firstLineIndent=-8,
            textColor=INK,
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.7,
            leading=10,
            leftIndent=7,
            rightIndent=7,
            textColor=INK,
            backColor=colors.HexColor("#f3f6f8"),
            borderColor=GRID,
            borderWidth=0.5,
            borderPadding=7,
            spaceBefore=4,
            spaceAfter=7,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8.2,
            leading=10,
            alignment=TA_CENTER,
            textColor=MUTED,
            spaceAfter=8,
        ),
        "table": ParagraphStyle(
            "TableCell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.7,
            leading=9.5,
            alignment=TA_LEFT,
            textColor=INK,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.8,
            leading=9.5,
            textColor=colors.white,
        ),
    }


def _page(canvas, doc) -> None:
    canvas.saveState()
    width, height = LETTER
    canvas.setStrokeColor(colors.HexColor("#d8e0e5"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, height - 0.47 * inch, width - doc.rightMargin, height - 0.47 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, height - 0.37 * inch, "CONNECTOR CALCULUS")
    canvas.drawRightString(width - doc.rightMargin, 0.39 * inch, f"{doc.page}")
    canvas.restoreState()


def _table(lines: list[str], styles: dict[str, ParagraphStyle], usable_width: float) -> Table:
    raw = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(raw) > 1 and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in raw[1]):
        raw.pop(1)
    columns = max(len(row) for row in raw)
    normalized = [row + [""] * (columns - len(row)) for row in raw]
    data = []
    for row_index, row in enumerate(normalized):
        style = styles["table_header"] if row_index == 0 else styles["table"]
        data.append([Paragraph(_inline(cell), style) for cell in row])
    table = Table(data, colWidths=[usable_width / columns] * columns, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f8f9")]),
            ]
        )
    )
    return table


def parse_markdown(markdown_path: Path, usable_width: float) -> list[object]:
    styles = _styles()
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    story: list[object] = []
    paragraph: list[str] = []
    first_heading = True
    subtitle_pending = True

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(part.strip() for part in paragraph).replace("  ", " ")
            style = styles["meta"] if text.startswith(("**Authors:**", "**Program:**", "**Version:**")) else styles["body"]
            story.append(Paragraph(_inline(text), style))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        if stripped == "\\pagebreak":
            flush_paragraph()
            story.append(PageBreak())
            index += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            block: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index].rstrip())
                index += 1
            label = "Equation" if language == "math" else None
            items: list[object] = []
            if label:
                items.append(Paragraph(label, styles["caption"]))
            items.append(Preformatted("\n".join(block), styles["code"], maxLineLength=105))
            story.append(KeepTogether(items))
            index += 1
            continue
        image_match = re.fullmatch(r"!\[([^\]]+)\]\(([^)]+)\)", stripped)
        if image_match:
            flush_paragraph()
            caption, image_ref = image_match.groups()
            image_path = Path(image_ref)
            if not image_path.is_absolute():
                image_path = Path.cwd() / image_path
            if image_path.exists():
                from PIL import Image as PILImage

                with PILImage.open(image_path) as source:
                    w, h = source.size
                draw_width = min(usable_width * 0.88, 6.2 * inch)
                draw_height = draw_width * h / w
                story.append(KeepTogether([Image(str(image_path), draw_width, draw_height), Paragraph(f"Figure. {html.escape(caption)}.", styles["caption"])]))
            else:
                story.append(Paragraph(f"[Missing figure: {html.escape(caption)}]", styles["caption"]))
            index += 1
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|") and lines[index].strip().endswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            story.append(_table(table_lines, styles, usable_width))
            story.append(Spacer(1, 7))
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level, text = len(heading.group(1)), heading.group(2)
            if first_heading:
                story.extend([Spacer(1, 0.35 * inch), Paragraph(_inline(text), styles["title"]), HRFlowable(width="42%", thickness=2, color=ACCENT, spaceAfter=10)])
                first_heading = False
            elif subtitle_pending and level == 2:
                story.append(Paragraph(_inline(text), styles["subtitle"]))
                subtitle_pending = False
            else:
                story.append(Paragraph(_inline(text), styles[{1: "h1", 2: "h1", 3: "h2"}[level]]))
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        numbered = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if bullet or numbered:
            flush_paragraph()
            text = bullet.group(1) if bullet else numbered.group(2)
            marker = "-" if bullet else f"{numbered.group(1)}."
            story.append(Paragraph(f"{marker} {_inline(text)}", styles["bullet"]))
            index += 1
            continue
        paragraph.append(stripped)
        index += 1
    flush_paragraph()
    return story


def render(input_path: str | Path, output_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        rightMargin=0.72 * inch,
        leftMargin=0.72 * inch,
        topMargin=0.62 * inch,
        bottomMargin=0.62 * inch,
        title="Connector Calculus",
        author="Rubio, Dugan, and Pizarro",
        subject="Ghost-node rewrites, bonded liquidity, and adversarial agent routing on the Lightning Network",
    )
    story = parse_markdown(input_path, LETTER[0] - document.leftMargin - document.rightMargin)
    document.build(story, onFirstPage=_page, onLaterPages=_page)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="paper/manuscript.md")
    parser.add_argument("--output", default="output/pdf/connector_calculus.pdf")
    args = parser.parse_args()
    print(render(args.input, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

