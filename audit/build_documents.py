"""Render the two audit documents and scientific figures; originals untouched."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import mathtext
from matplotlib.font_manager import FontProperties
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import LETTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image, Table, TableStyle, KeepTogether, Preformatted

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "tmp/pdfs/liquidity_on_trial"
FIGURES = ROOT / "audit/figures"
INK, ACCENT, MUTED = "#1b2738", "#95452d", "#586573"


def figures():
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": INK, "text.color": INK, "axes.titleweight": "bold"})
    incentive = json.loads((ROOT / "audit/incentives/evidence.json").read_text())
    rows = incentive["exact_markov_persistence_and_delay"]
    fig, ax = plt.subplots(figsize=(6.5, 3.05), constrained_layout=True)
    for rho, color in [(0.25, "#95452d"), (0.5, "#9aa3ad"), (0.75, "#245577"), (1, "#1d7b65")]:
        selected = [r for r in rows if r["stay_probability"] == rho]
        ax.plot([r["delay_epochs"] for r in selected], [r["targeted_minus_random"] for r in selected],
                marker="o", label=f"Stay probability {rho:g}", color=color)
    ax.axhline(0, color="#697887", linewidth=.6)
    ax.set(xlabel="Deployment delay (epochs)", ylabel="Additional services vs random", xticks=[0, 2, 4, 8])
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    fig.savefig(FIGURES / "forecast_delay.png", dpi=220)
    plt.close(fig)
    import csv
    with (ROOT / "audit/testnet4/results/headers.csv").open(newline="") as stream:
        headers = list(csv.DictReader(stream))
    deltas = [int(b["timestamp"])-int(a["timestamp"]) for a,b in zip(headers, headers[1:])]
    fig, ax = plt.subplots(figsize=(6.5, 2.65), constrained_layout=True)
    heights = [int(r["height"]) for r in headers[1:]]
    ax.scatter(heights, deltas, s=8, color=[ACCENT if d<=0 else "#245577" for d in deltas], alpha=.65)
    ax.axhline(0, color=INK, linewidth=.7)
    ax.set(xlabel="Historical testnet4 height", ylabel="Header timestamp change (s)")
    ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    fig.savefig(FIGURES / "header_clock.png", dpi=220)
    plt.close(fig)


def inline(text):
    value = html.escape(text.strip())
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", value)
    value = re.sub(r"`([^`]+)`", r'<font name="Courier" size="9">\1</font>', value)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#245577">\1</link>', value)


def styles():
    body = ParagraphStyle("Body", fontName="Times-Roman", fontSize=10.7, leading=14.1,
                          spaceAfter=7.5, textColor=colors.HexColor(INK), alignment=TA_JUSTIFY)
    return {"body": body,
            "title": ParagraphStyle("Title", parent=body, fontName="Helvetica-Bold", fontSize=26, leading=30,
                                    alignment=TA_CENTER, spaceBefore=15, spaceAfter=12),
            "subtitle": ParagraphStyle("Subtitle", parent=body, fontName="Helvetica", fontSize=13.5, leading=18,
                                       alignment=TA_CENTER, spaceAfter=15, textColor=colors.HexColor(ACCENT)),
            "meta": ParagraphStyle("Meta", parent=body, fontName="Helvetica", fontSize=8.4, leading=11,
                                   alignment=TA_CENTER, spaceAfter=4, textColor=colors.HexColor(MUTED)),
            "h1": ParagraphStyle("H1", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=17,
                                 spaceBefore=15, spaceAfter=7, keepWithNext=True, textColor=colors.HexColor(ACCENT)),
            "h2": ParagraphStyle("H2", parent=body, fontName="Helvetica-Bold", fontSize=10.5, leading=14,
                                 spaceBefore=10, spaceAfter=6, keepWithNext=True),
            "caption": ParagraphStyle("Caption", parent=body, fontName="Helvetica", fontSize=8.2,
                                      leading=10.8, alignment=0, textColor=colors.HexColor(MUTED), spaceAfter=11),
            "table": ParagraphStyle("Cell", parent=body, fontName="Helvetica", fontSize=8.2, leading=10.4, alignment=0, spaceAfter=0),
            "header": ParagraphStyle("CellHeader", parent=body, fontName="Helvetica-Bold", fontSize=8.2,
                                     leading=10.4, alignment=0, textColor=colors.white),
            "code": ParagraphStyle("Code", fontName="Courier", fontSize=8, leading=10, spaceAfter=8)}


def table(lines, st, width):
    rows = [[c.strip() for c in line.strip("|").split("|")] for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r":?-+:?", c) for c in row)]
    n = len(rows[0])
    fractions = [.14, .34, .52] if n == 3 and rows[0][0] == "ID" else [1/n] * n
    data = [[Paragraph(inline(c), st["header" if index==0 else "table"]) for c in row] for index,row in enumerate(rows)]
    out = Table(data, colWidths=[width*f for f in fractions], repeatRows=1, hAlign="LEFT")
    out.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(INK)),
                             ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#f1f3f5"),colors.white]),
                             ("VALIGN",(0,0),(-1,-1),"TOP"), ("LINEBELOW",(0,-1),(-1,-1),.6,colors.HexColor("#bbc5cf")),
                             ("LEFTPADDING",(0,0),(-1,-1),6), ("RIGHTPADDING",(0,0),(-1,-1),6),
                             ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    return out


def parse(path, width):
    st, story, para = styles(), [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    first, subtitle, index, eq_count = True, True, 0, 0
    def flush():
        if para:
            content = " ".join(para)
            kind = "meta" if content.startswith(("**Authors:","**Program:","**Version:")) else "body"
            story.append(Paragraph(inline(content), st[kind]))
            para.clear()
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            flush(); index += 1; continue
        if line == "\\pagebreak":
            flush(); story.append(PageBreak()); index += 1; continue
        if line.startswith("```"):
            flush(); language = line[3:]; block=[]; index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.append(lines[index]); index += 1
            if language == "math":
                eq_count += 1
                file = SCRATCH / f"{path.stem}_eq{eq_count}.png"
                mathtext.math_to_image("$"+" ".join(block)+"$", file, prop=FontProperties(size=14), dpi=300)
                with PILImage.open(file) as im:
                    w,h = im.size
                draw_w = min(width-20, w*72/300)
                story.append(KeepTogether([Spacer(1,4), Image(str(file), draw_w, draw_w*h/w, hAlign="CENTER"), Spacer(1,10)]))
            else:
                story.append(Preformatted("\n".join(block),st["code"],maxLineLength=90))
            index += 1; continue
        match = re.fullmatch(r"!\[([^\]]+)\]\(([^)]+)\)",line)
        if match:
            flush(); caption, ref = match.groups(); file=ROOT/ref
            with PILImage.open(file) as im:
                w,h=im.size
            story.append(KeepTogether([Image(str(file),width,width*h/w),Paragraph(inline(caption),st["caption"])]))
            index+=1; continue
        if line.startswith("|"):
            flush(); block=[]
            while index<len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index].strip()); index+=1
            story.extend([table(block,st,width),Spacer(1,10)]); continue
        match = re.match(r"^(#{1,3})\s+(.+)$",line)
        if match:
            flush(); level, text = len(match[1]),match[2]
            if first:
                kind="title"; first=False
            elif subtitle and level==2:
                kind="subtitle"; subtitle=False
            else:
                kind="h2" if level==3 else "h1"
            story.append(Paragraph(inline(text),st[kind])); index+=1; continue
        para.append(line); index+=1
    flush()
    return story


def render(source, title, output):
    doc=SimpleDocTemplate(str(output),pagesize=LETTER, leftMargin=56,rightMargin=56,topMargin=47,bottomMargin=46,
                         title=title,author="Dugan",subject="Exploratory adversarial audit; author-review draft")
    def page(canvas, document):
        canvas.saveState(); canvas.setFont("Helvetica",7.2); canvas.setFillColor(colors.HexColor(MUTED))
        canvas.drawString(56,LETTER[1]-29,title.upper())
        canvas.drawRightString(LETTER[0]-56,LETTER[1]-29,"SPIRAL  /  RESEARCH AUDIT")
        canvas.setStrokeColor(colors.HexColor("#c4ccd3"));canvas.setLineWidth(.5)
        canvas.line(56,LETTER[1]-35,LETTER[0]-56,LETTER[1]-35)
        canvas.drawString(56,27,"11 SEPTEMBER 2026  |  DRAFT FOR AUTHOR REVIEW")
        canvas.drawRightString(LETTER[0]-56,27,str(document.page));canvas.restoreState()
    doc.build(parse(source,500),onFirstPage=page,onLaterPages=page)


def main():
    SCRATCH.mkdir(parents=True,exist_ok=True)
    output=ROOT/"output/pdf";output.mkdir(parents=True,exist_ok=True)
    figures()
    for stem,title in [("liquidity_on_trial","Liquidity on Trial"),("connector_calculus_critique","Connector Calculus: Critique")]:
        target=output/f"{stem}.pdf"
        render(ROOT/"paper"/f"{stem}.md",title,target)
        print(target)


if __name__=="__main__":
    main()
