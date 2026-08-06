"""Generate PDF compliance reports and send them by email."""
from __future__ import annotations
from datetime import datetime
from io import BytesIO
import smtplib
import email.mime.multipart as mp
import email.mime.base as mb
import email.mime.text as mt
from email import encoders

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False


BRAND_BLUE   = (32, 56, 100)
BRAND_ORANGE = (247, 88, 53)

RESULT_COLORS = {
    "hit":           (220, 38, 38),
    "possible_match":(217, 119, 6),
    "clear":         (22, 163, 74),
}


def generate_pdf_report(session, user) -> bytes:
    if not FPDF_AVAILABLE:
        return _text_fallback(session, user)

    def safe(s: str) -> str:
        return s.replace("—", "-").replace("–", "-").replace("’", "'").encode("latin-1", "replace").decode("latin-1")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Header
    r, g, b = BRAND_ORANGE
    pdf.set_text_color(r, g, b)
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, "COMPLAYE INSTANT SCREENING", ln=True)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, "Compliance Report - Confidential", ln=True)

    r, g, b = BRAND_BLUE
    pdf.set_draw_color(r, g, b)
    pdf.set_line_width(0.8)
    pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
    pdf.ln(6)

    # ── Summary box
    overall_key = "hit" if session.hit_count else ("possible_match" if session.possible_count else "clear")
    overall_label = {"hit": "HIT", "possible_match": "POSSIBLE MATCH", "clear": "CLEAR"}[overall_key]
    oc = RESULT_COLORS[overall_key]

    def meta_row(label: str, value: str, bold_value: bool = False, color=None):
        pdf.set_fill_color(240, 242, 246)
        pdf.set_text_color(60, 60, 60)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(40, 7, safe(label), border=1, fill=True, ln=False)
        pdf.set_font("Helvetica", "B" if bold_value else "", 8)
        if color:
            pdf.set_text_color(*color)
        else:
            pdf.set_text_color(30, 30, 30)
        pdf.cell(150, 7, safe(value[:120]), border=1, ln=True)

    meta_row("Reference", str(session.id)[:8].upper())
    meta_row("Entity Queried", session.query_name or "")
    meta_row("Date", datetime.utcnow().strftime("%d %B %Y  %H:%M UTC"))
    meta_row("Screened by", getattr(user, "full_name", "System") or "")
    meta_row("Sources", ", ".join(session.sources_checked or []))
    meta_row("Overall Result", overall_label, bold_value=True, color=oc)
    meta_row("Hits found", str(session.hit_count))
    meta_row("Possible matches", str(session.possible_count))
    pdf.ln(6)

    # ── Results section
    pdf.set_text_color(*BRAND_BLUE)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Screening Results", ln=True)
    pdf.set_draw_color(*BRAND_BLUE)
    pdf.set_line_width(0.4)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    if not session.results:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 7, "No matches found. Entity is CLEAR against all screened lists.", ln=True)
    else:
        for i, r in enumerate(sorted(session.results, key=lambda x: -x.score), 1):
            rc = RESULT_COLORS.get(r.match_result.value if r.match_result else "clear", (22, 163, 74))
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*BRAND_BLUE)
            pdf.cell(0, 7, safe(f"{i}. {r.matched_name or '-'}"), ln=True)

            detail = r.match_detail or {}
            rows = [
                ("Result",    (r.match_result.value.upper().replace("_", " ") if r.match_result else "CLEAR"), rc),
                ("Score",     f"{r.score:.1f} / 100", None),
                ("Source",    r.matched_source or "", None),
                ("Type",      r.matched_type or "", None),
                ("Country",   r.matched_country or "", None),
                ("Program",   r.matched_program or "", None),
                ("DOB",       detail.get("date_of_birth") or "", None),
                ("Source ID", detail.get("source_id") or "", None),
            ]
            for label, value, color in rows:
                if not value:
                    continue
                pdf.set_fill_color(240, 242, 246)
                pdf.set_text_color(60, 60, 60)
                pdf.set_font("Helvetica", "B", 8)
                pdf.cell(30, 6, safe(label), border=1, fill=True, ln=False)
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(*(color if color else (30, 30, 30)))
                pdf.cell(160, 6, safe(str(value)[:120]), border=1, ln=True)
            pdf.ln(3)

    # ── Disclaimer
    pdf.ln(4)
    pdf.set_draw_color(180, 180, 180)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(130, 130, 130)
    pdf.multi_cell(0, 4,
        "This report is generated by Complaye Instant Screening and is intended solely for compliance and due-diligence purposes. "
        "Results are based on publicly available sanctions data from official government sources (OFAC, EU, UN, OFSI). "
        "Complaye Consulting assumes no liability for decisions made based solely on this report. "
        "Always combine screening results with additional KYC procedures."
    )

    return bytes(pdf.output())


async def send_report_email(to: str, session, pdf_bytes: bytes, sender_name: str = "Complaye CIS") -> None:
    """Send a PDF compliance report by email (TC-RPT-03)."""
    from app.config import settings
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        raise ValueError("SMTP credentials not configured (SMTP_USER / SMTP_PASSWORD env vars missing)")

    overall = "HIT" if session.hit_count else ("POSSIBLE MATCH" if session.possible_count else "CLEAR")
    subject = f"CIS Compliance Report — {session.query_name} [{overall}]"
    body = (
        f"Please find attached the Complaye Instant Screening compliance report for:\n\n"
        f"  Entity:  {session.query_name}\n"
        f"  Result:  {overall}\n"
        f"  Hits:    {session.hit_count}\n"
        f"  Possible matches: {session.possible_count}\n\n"
        f"Generated by {sender_name} via Complaye Instant Screening.\n"
        f"This report is confidential and for compliance purposes only."
    )

    msg = mp.MIMEMultipart()
    msg["From"] = f"Complaye CIS <{settings.SMTP_USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(mt.MIMEText(body, "plain"))

    attachment = mb.MIMEBase("application", "pdf")
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", f"attachment; filename=CIS_Report_{str(session.id)[:8]}.pdf")
    msg.attach(attachment)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_USER, to, msg.as_string())


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
        lines.append(f"  - {r.matched_name} [{r.matched_source}] score={r.score:.1f} -> {r.match_result}")
    lines += ["", "Install fpdf2 for full PDF: pip install fpdf2"]
    return "\n".join(lines).encode()
