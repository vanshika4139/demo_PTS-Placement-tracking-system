"""Training completion certificate (PDF).

Built on demand from the candidate's existing data - nothing is stored in the
database. A certificate is only available while the candidate's
training_status is "training_completed", so if the status is moved back the
certificate stops being available automatically.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

COMPLETED_STATUS = "training_completed"


def is_certificate_eligible(candidate):
    return bool(candidate and candidate.training_status == COMPLETED_STATUS)


def certificate_number(candidate):
    """Stable, unique number: CERT-<first 8 chars of candidate id>-<YYYYMM of end date>."""
    cid = str(candidate.id).replace("-", "")[:8].upper()
    end = candidate.training_end_date
    stamp = end.strftime("%Y%m") if end else "000000"
    return f"CERT-{cid}-{stamp}"


def _fmt(dt):
    return dt.strftime("%d %b %Y") if dt else ""


def _fit_font_size(text, font, max_size, max_width, min_size=14):
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def build_certificate_pdf(candidate, organization_name):
    """Returns the certificate as PDF bytes. Raises ValueError if the
    candidate has not completed training."""
    if not is_certificate_eligible(candidate):
        raise ValueError("Certificate is available only after training is completed.")

    buf = io.BytesIO()
    width, height = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(width, height))
    c.setTitle(f"Training Certificate - {candidate.full_name}")

    dark = colors.HexColor("#1f2937")
    accent = colors.HexColor("#2563eb")
    grey = colors.HexColor("#6b7280")

    # Double border
    c.setStrokeColor(accent)
    c.setLineWidth(4)
    c.rect(24, 24, width - 48, height - 48)
    c.setLineWidth(1)
    c.rect(34, 34, width - 68, height - 68)

    cx = width / 2
    max_w = width - 160

    # Organization + title
    c.setFillColor(grey)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(cx, height - 85, (organization_name or "").upper())

    c.setFillColor(dark)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(cx, height - 140, "CERTIFICATE OF COMPLETION")

    c.setFillColor(grey)
    c.setFont("Helvetica", 14)
    c.drawCentredString(cx, height - 185, "This is to certify that")

    # Candidate name (shrinks for long names)
    name = candidate.full_name or ""
    c.setFillColor(accent)
    size = _fit_font_size(name, "Helvetica-Bold", 38, max_w)
    c.setFont("Helvetica-Bold", size)
    c.drawCentredString(cx, height - 240, name)
    c.setStrokeColor(grey)
    c.setLineWidth(0.5)
    c.line(cx - 200, height - 250, cx + 200, height - 250)

    c.setFillColor(dark)
    c.setFont("Helvetica", 14)
    c.drawCentredString(cx, height - 285, "has successfully completed the training program")

    course = candidate.course or "Training Program"
    c.setFont("Helvetica-Bold", _fit_font_size(course, "Helvetica-Bold", 22, max_w, 12))
    c.drawCentredString(cx, height - 320, course)

    # Details line
    parts = []
    if candidate.course_duration:
        parts.append(f"Duration: {candidate.course_duration}")
    if candidate.training_start_date or candidate.training_end_date:
        parts.append(f"Period: {_fmt(candidate.training_start_date)} to {_fmt(candidate.training_end_date)}")
    if parts:
        c.setFont("Helvetica", 12)
        c.setFillColor(grey)
        c.drawCentredString(cx, height - 350, "   |   ".join(parts))

    parts2 = []
    if candidate.training_center:
        parts2.append(f"Training Center: {candidate.training_center}")
    if candidate.training_batch:
        parts2.append(f"Batch: {candidate.training_batch}")
    if parts2:
        c.setFont("Helvetica", 12)
        c.drawCentredString(cx, height - 370, "   |   ".join(parts2))

    # Footer: number, date, signature
    c.setFillColor(grey)
    c.setFont("Helvetica", 10)
    c.drawString(70, 70, f"Certificate No: {certificate_number(candidate)}")
    c.drawString(70, 55, f"Issued on: {_fmt(datetime.utcnow())}")

    c.setStrokeColor(dark)
    c.setLineWidth(0.8)
    c.line(width - 260, 85, width - 70, 85)
    c.setFillColor(dark)
    c.setFont("Helvetica", 11)
    c.drawCentredString(width - 165, 70, "Authorized Signatory")

    c.showPage()
    c.save()
    return buf.getvalue()