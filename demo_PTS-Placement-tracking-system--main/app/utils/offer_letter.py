"""Offer letter (PDF), built on demand from the candidate's placement data
and the organization's profile (name, logo, authority, signature).
Nothing is stored in the database. Same approach as app/utils/certificate.py.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from app.utils.certificate import _draw_image


def is_offer_letter_eligible(candidate):
    return bool(candidate and candidate.employer_name and candidate.joining_date)


def _fmt(dt):
    return dt.strftime("%d-%m-%Y") if dt else "-"


def _para(c, text, x, y, max_w, font="Helvetica", size=11, leading=16):
    c.setFont(font, size)
    for line in simpleSplit(text, font, size, max_w):
        c.drawString(x, y, line)
        y -= leading
    return y


def build_offer_letter_pdf(candidate, organization):
    """Returns the offer letter as PDF bytes. Raises ValueError if the
    candidate has no employer / joining date yet."""
    if not is_offer_letter_eligible(candidate):
        raise ValueError("Offer letter needs the employer name and joining date.")

    org_name = getattr(organization, "organization_name", None) or str(organization or "")
    width, height = A4
    left = 60
    text_w = width - 2 * left
    dark = colors.HexColor("#1f2937")
    grey = colors.HexColor("#6b7280")
    accent = colors.HexColor("#2563eb")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Offer Letter - {candidate.full_name}")

    # Letterhead
    _draw_image(c, getattr(organization, "logo", None), left, height - 95, 90, 55)
    c.setFillColor(dark)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width / 2, height - 65, org_name)
    c.setFont("Helvetica", 10)
    c.setFillColor(grey)
    c.drawCentredString(width / 2, height - 82, "Placement Tracking System")
    c.setStrokeColor(accent)
    c.setLineWidth(1.5)
    c.line(left, height - 108, width - left, height - 108)

    # Title + date
    c.setFillColor(dark)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 145, "OFFER LETTER")
    c.setFont("Helvetica", 11)
    c.drawString(left, height - 180, f"Date: {_fmt(datetime.utcnow())}")

    # Body
    role = candidate.job_role or "the offered position"
    employer = candidate.employer_name
    location = getattr(candidate, "location", None)
    y = height - 210
    c.setFillColor(dark)
    c.setFont("Helvetica", 11)
    c.drawString(left, y, f"Dear {candidate.full_name},")
    y -= 24
    body = f"We are pleased to confirm that you have been offered the position of {role} at {employer}"
    if location:
        body += f", based at {location}"
    body += f". This offer is made through the placement program of {org_name}."
    y = _para(c, body, left, y, text_w)
    y -= 14

    # Details table
    rows = [
        ("Candidate Name", candidate.full_name or "-"),
        ("Employer", employer),
        ("Job Role", candidate.job_role or "-"),
        ("Location", location or "-"),
        ("Joining Date", _fmt(candidate.joining_date)),
        ("Working Status", candidate.working_status or "-"),
    ]
    row_h, col = 26, 160
    c.setStrokeColor(colors.HexColor("#d1d5db"))
    c.setLineWidth(0.8)
    for label, value in rows:
        c.setFillColor(colors.HexColor("#f3f4f6"))
        c.rect(left, y - row_h + 6, col, row_h, fill=1, stroke=1)
        c.setFillColor(colors.white)
        c.rect(left + col, y - row_h + 6, text_w - col, row_h, fill=1, stroke=1)
        c.setFillColor(dark)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left + 8, y - 12, label)
        c.setFont("Helvetica", 10)
        c.drawString(left + col + 8, y - 12, str(value)[:70])
        y -= row_h
    y -= 20

    y = _para(c, "Please note that this offer is subject to the terms and conditions "
                 "communicated by the employer. We wish you a successful career.",
              left, y, text_w)

    # Signature block
    y -= 30
    c.setFont("Helvetica", 11)
    c.setFillColor(dark)
    c.drawString(left, y, "Regards,")
    sig_y = y - 62
    _draw_image(c, getattr(organization, "signature_url", None), left, sig_y + 4, 140, 50)
    c.setStrokeColor(dark)
    c.setLineWidth(0.8)
    c.line(left, sig_y, left + 190, sig_y)
    name = getattr(organization, "authority_name", None)
    desig = getattr(organization, "authority_designation", None)
    if name:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, sig_y - 15, name)
        if desig:
            c.setFont("Helvetica", 9)
            c.setFillColor(grey)
            c.drawString(left, sig_y - 28, desig)
        c.setFillColor(dark)
        c.setFont("Helvetica", 9)
        c.drawString(left, sig_y - 41, org_name)
    else:
        c.setFont("Helvetica", 11)
        c.drawString(left, sig_y - 15, "Authorized Signatory")
        c.setFont("Helvetica", 9)
        c.drawString(left, sig_y - 28, org_name)

    c.showPage()
    c.save()
    return buf.getvalue()
