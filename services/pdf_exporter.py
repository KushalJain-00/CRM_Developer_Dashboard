from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, PageBreak
)
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.graphics import renderPDF
from io import BytesIO
from datetime import datetime
from typing import Any


NAVY    = colors.HexColor("#0F172A")
NAVY2   = colors.HexColor("#1E293B")
BLUE    = colors.HexColor("#3B82F6")
INDIGO  = colors.HexColor("#6366F1")
EMERALD = colors.HexColor("#10B981")
AMBER   = colors.HexColor("#F59E0B")
ROSE    = colors.HexColor("#F43F5E")
SLATE   = colors.HexColor("#64748B")
LIGHT   = colors.HexColor("#F0F4F8")
WHITE   = colors.white
BORDER  = colors.HexColor("#E2E8F0")


def _bar(pct: int, color: colors.HexColor, width=120, height=7) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=colors.HexColor("#E2E8F0"), strokeColor=None))
    if pct > 0:
        d.add(Rect(0, 0, width * pct / 100, height, fillColor=color, strokeColor=None))
    return d


def generate_pdf(payload: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm, bottomMargin=16*mm,
    )

    W = A4[0] - 36*mm

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22,
                                 textColor=WHITE, leading=28, spaceAfter=4)
    sub_style   = ParagraphStyle("sub",   fontName="Helvetica",      fontSize=9,
                                 textColor=colors.HexColor("#94A3B8"), leading=14)
    h2_style    = ParagraphStyle("h2",    fontName="Helvetica-Bold", fontSize=12,
                                 textColor=NAVY, spaceAfter=10, spaceBefore=18, leading=16)
    h3_style    = ParagraphStyle("h3",    fontName="Helvetica-Bold", fontSize=10,
                                 textColor=SLATE, spaceAfter=6, spaceBefore=10, leading=14)
    body_style  = ParagraphStyle("body",  fontName="Helvetica",      fontSize=9,
                                 textColor=NAVY2, leading=14)
    cell_style  = ParagraphStyle("cell",  fontName="Helvetica",      fontSize=8,
                                 textColor=NAVY2, leading=11, wordWrap="CJK")

    file_name   = payload.get("fileName", "Unknown")
    sheet_name  = payload.get("sheetName", "")
    total       = payload.get("total", 0)
    fields      = payload.get("fields", 0)
    completeness= payload.get("completeness", 0)
    with_email  = payload.get("withEmail")
    with_phone  = payload.get("withPhone")
    field_quality = payload.get("fieldQuality", [])
    records     = payload.get("records", [])
    columns     = payload.get("columns", [])
    generated   = datetime.now().strftime("%d %b %Y, %I:%M %p")

    story = []

    cover_data = [[
        Paragraph(f"CRM Intelligence Report", title_style),
    ]]
    cover_sub = f"Source: {file_name}   ·   Sheet: {sheet_name}   ·   Generated: {generated}"

    kpi_items = [
        (str(total), "Total Records"),
        (str(fields), "Fields Mapped"),
        (f"{completeness}%", "Data Quality"),
    ]
    if with_email is not None:
        kpi_items.append((str(with_email), "With Email"))
    if with_phone is not None:
        kpi_items.append((str(with_phone), "With Phone"))

    kpi_cell_style = ParagraphStyle("kpicell", fontName="Helvetica-Bold",
                                    fontSize=20, textColor=WHITE, leading=24, alignment=TA_CENTER)
    kpi_lbl_style  = ParagraphStyle("kpilbl",  fontName="Helvetica",
                                    fontSize=7, textColor=colors.HexColor("#93C5FD"),
                                    leading=10, alignment=TA_CENTER, spaceAfter=0)

    kpi_cells = [[Paragraph(v, kpi_cell_style), Paragraph(l, kpi_lbl_style)] for v, l in kpi_items]
    kpi_col_w = (W - 2) / max(len(kpi_items), 1)

    kpi_table_data = [[c[0] for c in kpi_cells], [c[1] for c in kpi_cells]]
    kpi_table = Table(kpi_table_data, colWidths=[kpi_col_w]*len(kpi_items))
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), colors.HexColor("#1E3A8A")),
        ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#2D4FA0")),
        ("TOPPADDING",  (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 6),
        ("ROUNDEDCORNERS", [4]),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
    ]))

    cover_bg = Table(
        [[Paragraph("CRM INTELLIGENCE  ·  REPORT", ParagraphStyle(
            "badge", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#60A5FA"),
            leading=12, spaceBefore=0, spaceAfter=4, letterSpacing=1.5))],
         [Paragraph(f"📊 {file_name}", title_style)],
         [Paragraph(cover_sub, sub_style)],
         [Spacer(1, 14)],
         [kpi_table]],
        colWidths=[W]
    )
    cover_bg.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), NAVY),
        ("TOPPADDING",  (0,0), (-1,-1), 14),
        ("BOTTOMPADDING",(0,0),(-1,-1), 14),
        ("LEFTPADDING", (0,0), (-1,-1), 18),
        ("RIGHTPADDING",(0,0), (-1,-1), 18),
        ("ROUNDEDCORNERS", [8]),
    ]))
    story.append(cover_bg)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Data Quality Report", h2_style))
    story.append(HRFlowable(width=W, thickness=1, color=BORDER, spaceAfter=12))

    qual_rows = [
        [Paragraph("Field", ParagraphStyle("qh", fontName="Helvetica-Bold", fontSize=8,
                    textColor=SLATE, leading=11)),
         Paragraph("Fill Rate", ParagraphStyle("qh", fontName="Helvetica-Bold", fontSize=8,
                    textColor=SLATE, leading=11)),
         Paragraph("%", ParagraphStyle("qh", fontName="Helvetica-Bold", fontSize=8,
                    textColor=SLATE, leading=11, alignment=TA_RIGHT))],
    ]
    for fq in field_quality:
        pct = fq.get("pct", 0)
        col_color = EMERALD if pct > 75 else AMBER if pct > 40 else ROSE
        qual_rows.append([
            Paragraph(fq.get("label", ""), ParagraphStyle("qc", fontName="Helvetica",
                        fontSize=8, textColor=NAVY2, leading=11)),
            _bar(pct, col_color, width=int(W * 0.55), height=6),
            Paragraph(f"{pct}%", ParagraphStyle("qv", fontName="Helvetica-Bold",
                        fontSize=8, textColor=col_color, leading=11, alignment=TA_RIGHT)),
        ])

    qual_table = Table(qual_rows, colWidths=[W*0.26, W*0.60, W*0.14])
    qual_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  LIGHT),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, colors.HexColor("#F8FAFC")]),
        ("GRID",          (0,0), (-1,-1), 0.4, BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROUNDEDCORNERS",[4]),
    ]))
    story.append(qual_table)
    story.append(PageBreak())

    story.append(Paragraph(f"CRM Data  —  {len(records)} Records", h2_style))
    story.append(HRFlowable(width=W, thickness=1, color=BORDER, spaceAfter=12))

    if columns and records:
        display_cols = columns[:8]
        col_w = W / len(display_cols)

        hdr_style = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=7.5,
                                   textColor=WHITE, leading=10, alignment=TA_CENTER)
        tbl_data = [[Paragraph(c, hdr_style) for c in display_cols]]
        for row in records:
            tbl_data.append([
                Paragraph(str(row.get(c, "") or "")[:80], cell_style)
                for c in display_cols
            ])

        data_table = Table(tbl_data, colWidths=[col_w]*len(display_cols), repeatRows=1)
        data_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0),  NAVY),
            ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, colors.HexColor("#F8FAFC")]),
            ("GRID",          (0,0), (-1,-1), 0.3, BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
            ("LEFTPADDING",   (0,0), (-1,-1), 5),
            ("RIGHTPADDING",  (0,0), (-1,-1), 5),
            ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ]))
        story.append(data_table)

    footer_style = ParagraphStyle("footer", fontName="Helvetica", fontSize=7.5,
                                  textColor=SLATE, leading=12, alignment=TA_CENTER,
                                  spaceBefore=20)
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER))
    story.append(Paragraph(
        f"CRM Intelligence Platform  ·  {generated}  ·  {file_name}",
        footer_style
    ))

    doc.build(story)
    return buf.getvalue()
