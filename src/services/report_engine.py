"""
WealthMap – PDF Report Engine
Generates branded, multi-page PDF reports using ReportLab Platypus.
"""

import os
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from reportlab.lib.pagesizes import A4, letter
from reportlab.lib import colors
from reportlab.lib.units import mm, inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, Flowable
)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Wedge, Circle, Polygon
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics import renderPDF

# ── Brand colours ──────────────────────────────────────────────────────────────
C_BG        = colors.HexColor("#0D1117")
C_CARD      = colors.HexColor("#161B22")
C_ACCENT    = colors.HexColor("#58A6FF")
C_GREEN     = colors.HexColor("#3FB950")
C_RED       = colors.HexColor("#F85149")
C_GOLD      = colors.HexColor("#E3B341")
C_TEXT      = colors.HexColor("#E6EDF3")
C_MUTED     = colors.HexColor("#8B949E")
C_BORDER    = colors.HexColor("#30363D")
C_WHITE     = colors.white
C_BLACK     = colors.black

CHART_PALETTE = [
    colors.HexColor("#58A6FF"),
    colors.HexColor("#3FB950"),
    colors.HexColor("#E3B341"),
    colors.HexColor("#F85149"),
    colors.HexColor("#9B59B6"),
    colors.HexColor("#1ABC9C"),
    colors.HexColor("#E67E22"),
    colors.HexColor("#E91E63"),
]

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


# ── Styles ────────────────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()
    styles = {}

    def s(name, parent="Normal", **kw):
        styles[name] = ParagraphStyle(name, parent=base[parent], **kw)

    s("ReportTitle",   fontSize=28, textColor=C_ACCENT,  fontName="Helvetica-Bold",
      spaceAfter=4,    spaceBefore=0)
    s("ReportSubtitle",fontSize=12, textColor=C_MUTED,   fontName="Helvetica",
      spaceAfter=16)
    s("SectionHead",   fontSize=14, textColor=C_ACCENT,  fontName="Helvetica-Bold",
      spaceBefore=12,  spaceAfter=6)
    s("SubHead",       fontSize=11, textColor=C_TEXT,    fontName="Helvetica-Bold",
      spaceBefore=6,   spaceAfter=4)
    s("Body",          fontSize=9,  textColor=C_TEXT,    fontName="Helvetica",
      spaceAfter=4,    leading=14)
    s("BodyMuted",     fontSize=8,  textColor=C_MUTED,   fontName="Helvetica",
      spaceAfter=2)
    s("TableHeader",   fontSize=8,  textColor=C_WHITE,   fontName="Helvetica-Bold",
      alignment=TA_LEFT)
    s("TableCell",     fontSize=8,  textColor=C_TEXT,    fontName="Helvetica",
      alignment=TA_LEFT)
    s("TableCellRight",fontSize=8,  textColor=C_TEXT,    fontName="Helvetica",
      alignment=TA_RIGHT)
    s("GreenVal",      fontSize=9,  textColor=C_GREEN,   fontName="Helvetica-Bold")
    s("RedVal",        fontSize=9,  textColor=C_RED,     fontName="Helvetica-Bold")
    s("GoldVal",       fontSize=11, textColor=C_GOLD,    fontName="Helvetica-Bold")
    s("FootNote",      fontSize=7,  textColor=C_MUTED,   fontName="Helvetica",
      alignment=TA_CENTER)
    return styles


STYLES = _build_styles()

# ── Custom Flowables ──────────────────────────────────────────────────────────

class ColorBar(Flowable):
    """Thin full-width horizontal rule with colour."""
    def __init__(self, color=C_ACCENT, height=2, width=None):
        super().__init__()
        self._color = color
        self._h = height
        self._w = width

    def wrap(self, avW, avH):
        self.width = self._w or avW
        self.height = self._h
        return self.width, self.height

    def draw(self):
        self.canv.setFillColor(self._color)
        self.canv.rect(0, 0, self.width, self._h, stroke=0, fill=1)


class StatBox(Flowable):
    """Single stat card: label + big value + sub-label."""
    def __init__(self, label, value, sub="", value_color=C_ACCENT, w=110, h=52):
        super().__init__()
        self._label = label
        self._value = value
        self._sub   = sub
        self._vc    = value_color
        self.width  = w * mm
        self.height = h

    def wrap(self, avW, avH):
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        # Card background
        c.setFillColor(C_CARD)
        c.roundRect(0, 0, w, h, 4, stroke=0, fill=1)
        # Border
        c.setStrokeColor(C_BORDER)
        c.setLineWidth(0.5)
        c.roundRect(0, 0, w, h, 4, stroke=1, fill=0)
        # Label
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(C_MUTED)
        c.drawString(8, h - 14, self._label.upper())
        # Value
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(self._vc)
        c.drawString(8, h - 32, str(self._value))
        # Sub
        if self._sub:
            c.setFont("Helvetica", 7)
            c.setFillColor(C_MUTED)
            c.drawString(8, h - 44, str(self._sub))


# ── Table helpers ─────────────────────────────────────────────────────────────

def _tbl_style(col_count: int, has_header=True, zebra=True) -> TableStyle:
    cmds = [
        ("BACKGROUND",  (0, 0), (-1, 0 if has_header else -1), C_CARD),
        ("TEXTCOLOR",   (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING",(0,0), (-1, 0), 6),
        ("TOPPADDING",  (0, 0), (-1, 0), 6),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_BG, C_CARD] if zebra else [C_BG]),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 7.5),
        ("TEXTCOLOR",   (0, 1), (-1, -1), C_TEXT),
        ("TOPPADDING",  (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING",(0,1),(-1, -1), 4),
        ("LINEBELOW",   (0, 0), (-1, 0), 0.5, C_ACCENT),
        ("LINEBELOW",   (0, 1), (-1, -2), 0.3, C_BORDER),
        ("GRID",        (0, 0), (-1, -1), 0.2, C_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",(0, 0), (-1, -1), 6),
    ]
    return TableStyle(cmds)


def _money_cell(value: float, symbol: str = "", decimals: int = 2) -> Paragraph:
    """Return a right-aligned coloured Paragraph for a monetary value."""
    style = STYLES["GreenVal"] if value >= 0 else STYLES["RedVal"]
    style = ParagraphStyle(
        "MC", parent=style, alignment=TA_RIGHT, fontSize=7.5
    )
    sign = "" if value >= 0 else ""
    text = f"{sign}{symbol}{abs(value):,.{decimals}f}"
    return Paragraph(text, style)


def _pct_cell(value: float) -> Paragraph:
    style_name = "GreenVal" if value >= 0 else "RedVal"
    style = ParagraphStyle("PCT", parent=STYLES[style_name],
                           alignment=TA_RIGHT, fontSize=7.5)
    return Paragraph(f"{value:+.2f}%", style)


# ── Header / Footer callbacks ─────────────────────────────────────────────────

class _HeaderFooter:
    def __init__(self, report_title: str, subtitle: str, logo_text: str = "💰 WealthMap"):
        self.report_title = report_title
        self.subtitle     = subtitle
        self.logo_text    = logo_text

    def on_page(self, canvas, doc):
        canvas.saveState()
        w = doc.pagesize[0]

        # Header bar
        canvas.setFillColor(C_CARD)
        canvas.rect(0, PAGE_H - 18*mm, w, 18*mm, stroke=0, fill=1)

        # Accent strip
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, PAGE_H - 19*mm, w, 1*mm, stroke=0, fill=1)

        # Logo
        canvas.setFont("Helvetica-Bold", 11)
        canvas.setFillColor(C_ACCENT)
        canvas.drawString(MARGIN, PAGE_H - 12*mm, "WealthMap")

        # Report title (right side)
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(C_MUTED)
        canvas.drawRightString(w - MARGIN, PAGE_H - 12*mm, self.report_title)

        # Footer
        canvas.setFillColor(C_CARD)
        canvas.rect(0, 0, w, 10*mm, stroke=0, fill=1)
        canvas.setFillColor(C_ACCENT)
        canvas.rect(0, 10*mm, w, 0.5*mm, stroke=0, fill=1)

        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(MARGIN, 3.5*mm,
                         f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}  •  WealthMap Local Edition  •  Confidential")
        canvas.drawRightString(w - MARGIN, 3.5*mm, f"Page {doc.page}")

        canvas.restoreState()


# ── Base Report Builder ───────────────────────────────────────────────────────

class ReportBuilder:
    """
    Orchestrates building a single PDF report.
    Usage:
        rb = ReportBuilder("My Report", "Subtitle", ctx)
        rb.add_cover(...)
        rb.add_section(...)
        path = rb.save("/path/to/output.pdf")
    """

    def __init__(self, title: str, subtitle: str, ctx, output_path: str):
        self.title       = title
        self.subtitle    = subtitle
        self.ctx         = ctx
        self.output_path = output_path
        self._story: List = []
        self._hf = _HeaderFooter(title, subtitle)

        self._doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=MARGIN, rightMargin=MARGIN,
            topMargin=22*mm, bottomMargin=14*mm,
            title=title,
            author="WealthMap",
        )

    # ── Story helpers ──────────────────────────────────────────────────────────

    def add_cover(self, extra_lines: Optional[List[str]] = None):
        s = self._story
        s.append(Spacer(1, 30))
        s.append(ColorBar(C_ACCENT, height=3))
        s.append(Spacer(1, 16))
        s.append(Paragraph(self.title, STYLES["ReportTitle"]))
        s.append(Paragraph(self.subtitle, STYLES["ReportSubtitle"]))
        if extra_lines:
            for line in extra_lines:
                s.append(Paragraph(line, STYLES["BodyMuted"]))
        s.append(Spacer(1, 8))
        s.append(ColorBar(C_BORDER, height=0.5))
        s.append(Spacer(1, 6))
        base = self.ctx.settings.get("base_currency", "USD")
        s.append(Paragraph(
            f"Base currency: <b>{base}</b>  •  "
            f"Generated: <b>{datetime.now().strftime('%d %B %Y at %H:%M')}</b>  •  "
            f"WealthMap Local Edition",
            STYLES["BodyMuted"]
        ))
        s.append(Spacer(1, 20))

    def section(self, title: str, subtitle: str = ""):
        self._story.append(Paragraph(title, STYLES["SectionHead"]))
        if subtitle:
            self._story.append(Paragraph(subtitle, STYLES["BodyMuted"]))
        self._story.append(ColorBar(C_ACCENT, height=1))
        self._story.append(Spacer(1, 8))

    def sub_section(self, title: str):
        self._story.append(Spacer(1, 6))
        self._story.append(Paragraph(title, STYLES["SubHead"]))

    def paragraph(self, text: str, style="Body"):
        self._story.append(Paragraph(text, STYLES[style]))

    def spacer(self, h=10):
        self._story.append(Spacer(1, h))

    def page_break(self):
        self._story.append(PageBreak())

    def divider(self, color=C_BORDER):
        self._story.append(Spacer(1, 4))
        self._story.append(ColorBar(color, height=0.5))
        self._story.append(Spacer(1, 4))

    def stat_row(self, stats: List[Tuple[str, str, str, Any]]):
        """
        stats: [(label, value, sub, color), ...]
        Renders a horizontal row of StatBox flowables.
        """
        count = len(stats)
        box_w = (PAGE_W - 2*MARGIN - (count - 1)*4*mm) / count / mm
        row = []
        for label, value, sub, color in stats:
            row.append(StatBox(label, value, sub, color, w=box_w))
        # Wrap in a Table so they sit side-by-side
        col_w = [box_w * mm] * count
        t = Table([row], colWidths=col_w)
        t.setStyle(TableStyle([
            ("ALIGN",  (0,0), (-1,-1), "CENTER"),
            ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
            ("LEFTPADDING",  (0,0), (-1,-1), 2),
            ("RIGHTPADDING", (0,0), (-1,-1), 2),
        ]))
        self._story.append(t)
        self._story.append(Spacer(1, 10))

    def data_table(self, headers: List[str], rows: List[List],
                   col_widths: Optional[List] = None):
        """Generic styled table. Rows may contain strings or Paragraph objects."""
        header_row = [Paragraph(h, STYLES["TableHeader"]) for h in headers]
        data = [header_row]
        for row in rows:
            processed = []
            for cell in row:
                if isinstance(cell, str):
                    processed.append(Paragraph(cell, STYLES["TableCell"]))
                else:
                    processed.append(cell)  # Paragraph/Flowable already
            data.append(processed)

        avail_w = PAGE_W - 2*MARGIN
        if col_widths is None:
            col_widths = [avail_w / len(headers)] * len(headers)
        else:
            # Scale to available width
            total = sum(col_widths)
            col_widths = [w / total * avail_w for w in col_widths]

        tbl = Table(data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(_tbl_style(len(headers)))
        self._story.append(tbl)
        self._story.append(Spacer(1, 8))

    def pie_chart(self, data: List[float], labels: List[str],
                  title: str = "", width: float = 140, height: float = 110) -> Drawing:
        """Return a Drawing with a pie chart."""
        d = Drawing(width * mm, height * mm)
        pie = Pie()
        pie.x = 20 * mm
        pie.y = 10 * mm
        pie.width  = 60 * mm
        pie.height = 60 * mm
        pie.data   = [max(v, 0.001) for v in data]
        pie.labels = labels
        pie.slices.strokeWidth   = 0.5
        pie.slices.strokeColor   = C_BG
        for i, _ in enumerate(data):
            pie.slices[i].fillColor = CHART_PALETTE[i % len(CHART_PALETTE)]
        pie.sideLabels     = True
        pie.sideLabelsOffset = 0.1
        pie.simpleLabels   = False
        if title:
            d.add(String(width * mm / 2, height * mm - 8,
                         title, fontSize=9, fillColor=C_TEXT,
                         fontName="Helvetica-Bold", textAnchor="middle"))
        d.add(pie)
        return d

    def bar_chart(self, data: List[List[float]], labels: List[str],
                  series_names: Optional[List[str]] = None,
                  title: str = "", width: float = 160, height: float = 90) -> Drawing:
        d = Drawing(width * mm, height * mm)
        bc = VerticalBarChart()
        bc.x = 18 * mm
        bc.y = 16 * mm
        bc.height = (height - 26) * mm
        bc.width  = (width  - 24) * mm
        bc.data   = data
        bc.categoryAxis.categoryNames = labels
        bc.categoryAxis.labels.fontName  = "Helvetica"
        bc.categoryAxis.labels.fontSize  = 6
        bc.categoryAxis.labels.fillColor = C_MUTED
        bc.categoryAxis.labels.angle     = 30 if len(labels) > 6 else 0
        bc.valueAxis.labels.fontName  = "Helvetica"
        bc.valueAxis.labels.fontSize  = 6
        bc.valueAxis.labels.fillColor = C_MUTED
        bc.valueAxis.strokeColor      = C_BORDER
        bc.categoryAxis.strokeColor   = C_BORDER
        bc.groupSpacing = 4
        for i, _ in enumerate(data):
            bc.bars[i].fillColor   = CHART_PALETTE[i % len(CHART_PALETTE)]
            bc.bars[i].strokeColor = colors.transparent
        if title:
            d.add(String(width * mm / 2, height * mm - 6,
                         title, fontSize=9, fillColor=C_TEXT,
                         fontName="Helvetica-Bold", textAnchor="middle"))
        d.add(bc)
        return d

    def add_drawing(self, drawing: Drawing, align: str = "LEFT"):
        from reportlab.platypus import Image
        from reportlab.graphics import renderPM
        self._story.append(drawing)
        self._story.append(Spacer(1, 8))

    def save(self) -> str:
        """Build and write the PDF. Returns the output path."""
        self._doc.build(
            self._story,
            onFirstPage=self._hf.on_page,
            onLaterPages=self._hf.on_page,
        )
        return self.output_path
