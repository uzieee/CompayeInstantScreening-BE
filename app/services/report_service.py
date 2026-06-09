"""Generate PDF compliance reports."""
from __future__ import annotations
from datetime import datetime
from io import BytesIO

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


BRAND_BLUE   = (32/255, 56/255, 100/255)
BRAND_ORANGE = (247/255, 88/255, 53/255)
LIGHT_GRAY   = (0.95, 0.95, 0.95)

RESULT_COLORS = {
    "hit":           (0.95, 0.2, 0.2),
    "possible_match":(0.95, 0.6, 0.1),
    "clear":         (0.1,  0.7, 0.3),
}


def generate_pdf_report(session, user) -> bytes:
    if not REPORTLAB_AVAILABLE:
        return _text_fallback(session, user)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    story = []

    def heading(text, size=14, color=BRAND_BLUE, bold=True):
        style = ParagraphStyle("h", fontSize=size, textColor=colors.Color(*color),
                               fontName="Helvetica-Bold" if bold else "Helvetica",
                               spaceAfter=4)
        return Paragraph(text, style)

    def body(text, size=9, color=(0.2, 0.2, 0.2)):
        style = ParagraphStyle("b", fontSize=size, textColor=colors.Color(*color),
                               fontName="Helvetica", leading=14)
        return Paragraph(text, style)

    # ── Header
    story.append(heading("COMPLAYE INSTANT SCREENING", size=18, color=BRAND_ORANGE))
    story.append(body("Compliance Report — Confidential", size=10, color=(0.4, 0.4, 0.4)))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.Color(*BRAND_BLUE)))
    story.append(Spacer(1, 0.4*cm))

    # ── Summary table
    overall = "HIT" if session.hit_count else ("POSSIBLE MATCH" if session.possible_count else "CLEAR")
    overall_color = RESULT_COLORS.get(
        "hit" if session.hit_count else ("possible_match" if session.possible_count else "clear"),
        (0.1, 0.7, 0.3)
    )

    meta = [
        ["Reference",     str(session.id)[:8].upper()],
        ["Entity Queried", session.query_name],
        ["Date",          datetime.utcnow().strftime("%d %B %Y %H:%M UTC")],
        ["Screened by",   getattr(user, "full_name", "System")],
        ["Organisation",  getattr(user, "tenant_name", "")],
        ["Sources",       ", ".join(session.sources_checked or [])],
        ["Overall result", overall],
        ["Hits found",    str(session.hit_count)],
        ["Possible matches", str(session.possible_count)],
    ]

    t = Table(meta, colWidths=[4.5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.Color(*LIGHT_GRAY)),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.Color(0.97, 0.97, 0.97)]),
        ("TEXTCOLOR",  (1, 6), (1, 6), colors.Color(*overall_color)),
        ("FONTNAME",   (1, 6), (1, 6), "Helvetica-Bold"),
        ("BOX",        (0, 0), (-1, -1), 0.5, colors.Color(0.8, 0.8, 0.8)),
        ("INNERGRID",  (0, 0), (-1, -1), 0.25, colors.Color(0.85, 0.85, 0.85)),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.6*cm))

    # ── Results
    story.append(heading("Screening Results", size=12))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.Color(*BRAND_BLUE)))
    story.append(Spacer(1, 0.3*cm))

    if not session.results:
        story.append(body("No matches found. Entity is CLEAR against all screened lists."))
    else:
        for i, r in enumerate(sorted(session.results, key=lambda x: -x.score), 1):
            rc = RESULT_COLORS.get(r.match_result.value if r.match_result else "clear", (0.1, 0.7, 0.3))
            story.append(heading(f"{i}. {r.matched_name or '—'}", size=10, color=BRAND_BLUE))

            detail = r.match_detail or {}
            rows = [
                ["Result",    r.match_result.value.upper().replace("_", " ") if r.match_result else "CLEAR"],
                ["Score",     f"{r.score:.1f} / 100"],
                ["Source",    r.matched_source or ""],
                ["Type",      r.matched_type or ""],
                ["Country",   r.matched_country or ""],
                ["Program",   r.matched_program or ""],
                ["DOB",       detail.get("date_of_birth") or ""],
                ["Source ID", detail.get("source_id") or ""],
            ]
            rows = [row for row in rows if row[1]]

            rt = Table(rows, colWidths=[3.5*cm, 13*cm])
            rt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.Color(*LIGHT_GRAY)),
                ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
                ("TEXTCOLOR",  (1, 0), (1, 0),  colors.Color(*rc)),
                ("FONTNAME",   (1, 0), (1, 0),  "Helvetica-Bold"),
                ("BOX",        (0, 0), (-1, -1), 0.5, colors.Color(0.85, 0.85, 0.85)),
                ("INNERGRID",  (0, 0), (-1, -1), 0.25, colors.Color(0.9, 0.9, 0.9)),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ]))
            story.append(rt)
            story.append(Spacer(1, 0.35*cm))

    # ── Disclaimer
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.Color(0.7, 0.7, 0.7)))
    story.append(Spacer(1, 0.2*cm))
    disclaimer = (
        "This report is generated by Complaye Instant Screening and is intended solely for compliance "
        "and due-diligence purposes. Results are based on publicly available sanctions data from official "
        "government sources (OFAC, EU, UN, OFSI). Complaye Consulting assumes no liability for decisions "
        "made based solely on this report. Always combine screening results with additional KYC procedures."
    )
    story.append(body(disclaimer, size=7, color=(0.5, 0.5, 0.5)))

    doc.build(story)
    return buf.getvalue()


def _text_fallback(session, user) -> bytes:
    lines = [
        "COMPLAYE INSTANT SCREENING — Compliance Report",
        "=" * 60,
        f"Entity: {session.query_name}",
        f"Date:   {datetime.utcnow().strftime('%d %B %Y %H:%M UTC')}",
        f"User:   {getattr(user, 'full_name', 'System')}",
        f"Hits:   {session.hit_count}  Possible: {session.possible_count}",
        "",
        "Results:",
    ]
    for r in (session.results or []):
        lines.append(f"  - {r.matched_name} [{r.matched_source}] score={r.score:.1f} → {r.match_result}")
    lines += ["", "Install reportlab for full PDF: pip install reportlab"]
    return "\n".join(lines).encode()
