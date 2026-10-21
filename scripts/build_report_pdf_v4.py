"""Create the local Russian project report from its reviewed Markdown source."""

import hashlib
import json
import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/PROJECT_REPORT_V4.md"
OUT = ROOT / "output/pdf/SafeTrace-KZ-report-v4.pdf"


def inline(text):
    text = escape(text.replace("—", "-").replace("–", "-").replace("‑", "-"))
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`([^`]+)`", r"\1", text)


def main():
    source = SOURCE.read_text(encoding="utf-8")
    assert "<!--" not in source, "Finish the report before PDF export"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
    pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
    pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial", boldItalic="Arial-Bold")
    body = ParagraphStyle("Body", fontName="Arial", fontSize=10.5, leading=15.2, textColor=colors.HexColor("#24354B"), spaceAfter=8, alignment=TA_LEFT)
    title = ParagraphStyle("Title", parent=body, fontName="Arial-Bold", fontSize=23, leading=28, spaceAfter=18, textColor=colors.HexColor("#14243D"))
    heading = ParagraphStyle("Heading", parent=body, fontName="Arial-Bold", fontSize=14.5, leading=19, spaceBefore=15, spaceAfter=8, keepWithNext=True)
    list_style = ParagraphStyle("List", parent=body, leftIndent=16, firstLineIndent=-16, spaceAfter=7)
    story = []
    for block in source.strip().split("\n\n"):
        if block.startswith("# "):
            story.append(Paragraph(inline(block[2:]), title))
            story.append(Paragraph("ОТЧЁТ О ПРОДУКТЕ И НОВОЙ ПРОВЕРКЕ · 22 ОКТЯБРЯ 2026", ParagraphStyle("Eyebrow", parent=body, fontSize=8.5, leading=12, textColor=colors.HexColor("#4C678C"))))
            story.append(Spacer(1, 8))
        elif block.startswith("## "):
            story.append(Paragraph(inline(block[3:]), heading))
        elif re.match(r"\d+\. ", block):
            for line in block.splitlines():
                story.append(Paragraph(inline(line), list_style))
        else:
            story.append(Paragraph(inline(block.replace("\n", " ")), body))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E1EB"))
        canvas.line(54, 42, A4[0] - 54, 42)
        canvas.setFont("Arial", 8)
        canvas.setFillColor(colors.HexColor("#62738A"))
        canvas.drawString(54, 29, "SafeTrace KZ · авторская синтетическая оценка · локальный MVP")
        canvas.drawRightString(A4[0] - 54, 29, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=54, rightMargin=54, topMargin=48, bottomMargin=57, title="SafeTrace KZ — отчёт о продукте v4", author="SafeTrace KZ project", subject="Работа программы, сравнение версий, ограничения и следующий этап")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    print(json.dumps({"path": str(OUT), "bytes": OUT.stat().st_size, "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "pdf_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
