"""
Payment gateway integration - SRS FR-09.

Razorpay, Cashfree and Stripe are all wired (create_payment_link + webhook
routes in app/routes/frontend.py). Each provider's keys are stored in their
own columns on platform_settings, so switching the active provider on the
Integrations page never overwrites another provider's saved keys.

`mark_invoice_paid` is what a real webhook handler (or a manual "Mark as
Paid" button) calls - it's the one place that updates both the Invoice and
the Organization consistently.
"""

import logging

from app.extensions import db
from app.models import Invoice
from app.utils.platform_settings import get_platform_settings

logger = logging.getLogger(__name__)

PROVIDERS = ("stripe", "razorpay", "cashfree")


def get_payment_gateway_config():
    """Returns (provider, key_id, key_secret, webhook_secret) of the ACTIVE
    provider only. Each provider's keys live in their own columns
    (payment_gateway_<provider>_key_id / _key_secret / _webhook_secret).
    All may be None if nothing is configured yet - callers must check
    before attempting to create a payment link."""
    settings = get_platform_settings()
    p = settings.payment_gateway_provider
    if p not in PROVIDERS:
        return None, None, None, None
    return (
        p,
        getattr(settings, f"payment_gateway_{p}_key_id", None),
        getattr(settings, f"payment_gateway_{p}_key_secret", None),
        getattr(settings, f"payment_gateway_{p}_webhook_secret", None),
    )


def is_gateway_configured():
    settings = get_platform_settings()
    provider, key_id, key_secret, _ = get_payment_gateway_config()
    if not (settings.payment_gateway_enabled and provider and key_secret):
        return False
    # Stripe's backend only needs the secret key; Razorpay/Cashfree need both.
    if provider == "stripe":
        return True
    return bool(key_id)


def create_payment_link(invoice: Invoice):
    """Returns a checkout URL the organization can be sent to pay this
    invoice. Raises RuntimeError if no gateway is configured, or
    NotImplementedError for a configured provider whose SDK call hasn't
    been filled in yet.

    Each branch below shows the shape (invoice.amount in the provider's
    expected unit, a reference id to correlate the webhook back to this
    Invoice, etc.).
    """
    provider, key_id, key_secret, _ = get_payment_gateway_config()

    if not is_gateway_configured():
        raise RuntimeError(
            "No payment gateway is configured. Set one up on the Integrations page first."
        )

    if provider == "razorpay":
        import razorpay

        client = razorpay.Client(auth=(key_id, key_secret))

        # A payment link for this invoice may already exist (e.g. the user
        # clicked "Pay Online" once before) - Razorpay rejects a second
        # create_link call with the same reference_id, so fetch and reuse
        # the existing link instead of erroring.
        if invoice.gateway_reference:
            try:
                existing = client.payment_link.fetch(invoice.gateway_reference)
                if existing.get("status") != "expired":
                    return existing.get("short_url")
            except Exception:
                pass  # fetch failed - fall through and try creating a new one

        try:
            payment_link = client.payment_link.create({
                "amount": int(round(float(invoice.amount) * 100)),
                "currency": "INR",
                "description": f"Invoice {invoice.invoice_number}",
                "reference_id": invoice.invoice_number,
                "notes": {"invoice_id": invoice.id, "organization_id": invoice.organization_id},
                "callback_method": "get",
            })
        except Exception as exc:
            logger.exception("payment_gateway: Razorpay payment link creation failed for invoice %s", invoice.invoice_number)
            raise RuntimeError(f"Could not create Razorpay payment link: {exc}") from exc

        invoice.gateway_reference = payment_link.get("id")
        invoice.payment_gateway = "razorpay"
        db.session.commit()
        return payment_link.get("short_url")

    elif provider == "cashfree":
        from cashfree_pg.api_client import Cashfree
        from cashfree_pg.models.create_link_request import CreateLinkRequest
        from cashfree_pg.models.link_customer_details_entity import LinkCustomerDetailsEntity

        x_api_version = "2023-08-01"
        cashfree_instance = Cashfree(
            XClientId=key_id,
            XClientSecret=key_secret,
            XEnvironment=Cashfree.PRODUCTION if key_id.upper().startswith("PROD") else Cashfree.SANDBOX,
        )

        # A payment link for this invoice may already exist - fetch and reuse
        # it instead of erroring on a duplicate link_id (mirrors Razorpay above).
        if invoice.gateway_reference:
            try:
                existing = cashfree_instance.PGFetchLink(
                    invoice.gateway_reference, x_api_version=x_api_version
                ).data
                if existing.link_status == "ACTIVE":
                    return existing.link_url
            except Exception:
                pass  # fetch failed - fall through and try creating a new one

        # Cashfree's Payment Links API requires a customer phone number.
        # Our Invoice model doesn't carry one directly, so fall back to the
        # Organization's mobile number.
        from app.models import Organization as _Org
        _inv_org = _Org.query.get(invoice.organization_id)
        _digits = "".join(ch for ch in ((_inv_org.mobile if _inv_org else "") or "") if ch.isdigit())[-10:]
        customer_phone = _digits if (len(_digits) == 10 and _digits[0] in "6789") else "9876543210"

        customer_details = LinkCustomerDetailsEntity(
            customer_phone=customer_phone,
            customer_name=invoice.organization.organization_name,
        )
        create_link_request = CreateLinkRequest(
            link_id=invoice.invoice_number,
            link_amount=float(invoice.amount),
            link_currency="INR",
            link_purpose=f"Invoice {invoice.invoice_number}",
            customer_details=customer_details,
            link_notes={"invoice_id": str(invoice.id), "organization_id": str(invoice.organization_id)},
        )

        try:
            import requests as _rq
            from types import SimpleNamespace as _NS
            _base = ("https://sandbox.cashfree.com/pg/links" if str(key_id).upper().startswith("TEST")
                     else "https://api.cashfree.com/pg/links")
            _h = {"x-client-id": key_id, "x-client-secret": key_secret,
                  "x-api-version": x_api_version, "Content-Type": "application/json"}
            _body = {
                "link_id": invoice.invoice_number,
                "link_amount": float(invoice.amount),
                "link_currency": "INR",
                "link_purpose": f"Invoice {invoice.invoice_number}",
                "customer_details": {"customer_phone": customer_phone,
                                     "customer_name": invoice.organization.organization_name},
                "link_notes": {"invoice_id": str(invoice.id), "organization_id": str(invoice.organization_id)},
            }
            _r = _rq.post(_base, json=_body, headers=_h, timeout=30)
            if not _r.ok and "already" in _r.text.lower():
                _r = _rq.get(_base + "/" + invoice.invoice_number, headers=_h, timeout=30)
            if not _r.ok:
                raise RuntimeError(_r.text[:300])
            _d = _r.json()
            payment_link = _NS(link_id=_d["link_id"], link_url=_d["link_url"])
        except Exception as exc:
            logger.exception("payment_gateway: Cashfree payment link creation failed for invoice %s", invoice.invoice_number)
            raise RuntimeError(f"Could not create Cashfree payment link: {exc}") from exc

        invoice.gateway_reference = payment_link.link_id
        invoice.payment_gateway = "cashfree"
        db.session.commit()
        return payment_link.link_url

    elif provider == "stripe":
        import stripe

        stripe.api_key = key_secret

        # A Checkout Session for this invoice may already exist and still be
        # open - reuse it instead of creating a duplicate (mirrors the
        # Razorpay/Cashfree reuse pattern above).
        if invoice.gateway_reference:
            try:
                existing = stripe.checkout.Session.retrieve(invoice.gateway_reference)
                if existing.status == "open" and existing.url:
                    return existing.url
            except Exception:
                pass  # fetch failed - fall through and create a new one

        from flask import url_for

        try:
            checkout_session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": "inr",
                        "product_data": {"name": f"Invoice {invoice.invoice_number}"},
                        "unit_amount": int(round(float(invoice.amount) * 100)),
                    },
                    "quantity": 1,
                }],
                metadata={
                    "invoice_id": str(invoice.id),
                    "invoice_number": invoice.invoice_number,
                    "organization_id": str(invoice.organization_id),
                },
                success_url=url_for("frontend.organization_billing", _external=True),
                cancel_url=url_for("frontend.organization_billing", _external=True),
            )
        except Exception as exc:
            logger.exception("payment_gateway: Stripe checkout session creation failed for invoice %s", invoice.invoice_number)
            raise RuntimeError(f"Could not create Stripe checkout session: {exc}") from exc

        invoice.gateway_reference = checkout_session.id
        invoice.payment_gateway = "stripe"
        db.session.commit()
        return checkout_session.url
    else:
        raise RuntimeError(f"Unknown payment gateway provider: {provider!r}")


def mark_invoice_paid(invoice: Invoice, gateway=None, gateway_reference=None, raw_response=None, actor_id=None):
    """The single place that should ever flip an invoice + its organization
    to paid - called either by a webhook handler or a manual 'Mark as Paid'
    action in the UI (pass gateway='manual' for the latter)."""
    from datetime import datetime

    from app.models import Organization

    prior_status = invoice.status

    invoice.status = "PAID"
    invoice.paid_at = datetime.utcnow()
    invoice.payment_gateway = gateway
    invoice.gateway_reference = gateway_reference
    invoice.gateway_raw_response = raw_response
    invoice.modified_by = actor_id

    org = Organization.query.get(invoice.organization_id)
    if org:
        if prior_status not in ("PAID", "CANCELLED"):
            activate_self_serve_purchase(invoice, org)
        org.payment_status = "PAID"
        org.modified_at = datetime.utcnow()

    # Notify super admins the same way other platform events do (new
    # organization, new candidate, etc.) - see app/routes/frontend.py
    # _create_notification for the pattern this mirrors.
    from app.models import Notification
    notif = Notification(
        title=f"Invoice paid: {invoice.invoice_number}",
        message=f"{org.organization_name if org else 'Organization'} paid invoice {invoice.invoice_number} (Rs. {invoice.amount:,.2f}) via {gateway or 'manual'}.",
        type="success",
        organization_id=str(invoice.organization_id),
    )
    db.session.add(notif)

    db.session.commit()
    return invoice


def activate_self_serve_purchase(invoice, org):
    """Applies a plan purchase made from the organization's own Plan & Billing
    page. Called by mark_invoice_paid (so the webhook and the manual 'Mark as
    Paid' button behave the same) BEFORE it flips the organization to PAID.

    Only invoices whose proration_note starts with '[self-serve:new|renew|upgrade]'
    are touched - invoices from the scheduled billing job are left exactly as
    they always were.

      new      plan set, expiry = end of the new period, plan credits ADDED,
               candidate limit + AI allowance set to the plan's
      renew    same as new (period starts at the old expiry)
      upgrade  plan set, expiry unchanged, only the extra credits over the
               old plan are added
    """
    import re
    from datetime import datetime

    from app.models import Plan

    match = re.match(r"\[self-serve:(new|renew|upgrade)\]", invoice.proration_note or "")
    if not match or org is None or not invoice.plan_id:
        return False

    plan = Plan.query.get(invoice.plan_id)
    if plan is None:
        logger.warning(
            "payment_gateway: self-serve invoice %s points to a missing plan %s",
            invoice.invoice_number, invoice.plan_id,
        )
        return False

    kind = match.group(1)
    old_plan = Plan.query.get(org.subscription_plan_id) if org.subscription_plan_id else None

    def _extra(new_value, old_value=0):
        return max(0, int(new_value or 0) - int(old_value or 0))

    org.subscription_plan_id = plan.id
    org.billing_cycle = invoice.billing_cycle or plan.default_billing_cycle
    org.candidate_limit = plan.candidate_limit or 0

    if kind in ("new", "renew"):
        period_end = invoice.period_end
        org.subscription_expiry_date = period_end.date() if isinstance(period_end, datetime) else period_end
        org.whatsapp_credits = (org.whatsapp_credits or 0) + _extra(plan.whatsapp_credits)
        org.sms_credits = (org.sms_credits or 0) + _extra(plan.sms_credits)
        org.email_credits = (org.email_credits or 0) + _extra(plan.email_credits)
        org.ai_call_allowance = plan.ai_call_allowance or 0
        # An organization that was auto-suspended for a lapsed subscription is
        # switched back on once it pays (a manually suspended one is not).
        if org.status == 0 and org.payment_status == "OVERDUE":
            org.status = 1
    else:
        org.whatsapp_credits = (org.whatsapp_credits or 0) + _extra(plan.whatsapp_credits, old_plan.whatsapp_credits if old_plan else 0)
        org.sms_credits = (org.sms_credits or 0) + _extra(plan.sms_credits, old_plan.sms_credits if old_plan else 0)
        org.email_credits = (org.email_credits or 0) + _extra(plan.email_credits, old_plan.email_credits if old_plan else 0)
        org.ai_call_allowance = max(org.ai_call_allowance or 0, plan.ai_call_allowance or 0)

    logger.info("payment_gateway: activated %s purchase of plan %s for organization %s", kind, plan.id, org.id)

    try:
        from app.utils.report_cache import invalidate_report_cache

        invalidate_report_cache("dashboard:super_admin")
    except Exception:
        pass
    return True


def sync_cashfree_invoice(invoice):
    """Asks Cashfree if this invoice's payment link is PAID and, if so,
    marks the invoice paid (same as the webhook would). Works without a
    public webhook URL. Returns True if the invoice was marked paid."""
    import requests

    if invoice.status == "PAID" or invoice.payment_gateway != "cashfree" or not invoice.gateway_reference:
        return False
    try:
        key_id, key_secret = _provider_keys("cashfree")
        base = ("https://sandbox.cashfree.com/pg/links/" if str(key_id).upper().startswith("TEST")
                else "https://api.cashfree.com/pg/links/")
        r = requests.get(
            base + str(invoice.gateway_reference),
            headers={"x-client-id": key_id, "x-client-secret": key_secret, "x-api-version": "2025-01-01"},
            timeout=15,
        )
        if not r.ok:
            return False
        data = r.json()
        if data.get("link_status") == "PAID":
            mark_invoice_paid(
                invoice,
                gateway="cashfree",
                gateway_reference=invoice.gateway_reference,
                raw_response=str(data)[:2000],
            )
            return True
    except Exception:
        logger.exception("sync_cashfree_invoice failed for %s", invoice.invoice_number)
    return False

def _provider_keys(provider):
    s = get_platform_settings()
    return (getattr(s, f"payment_gateway_{provider}_key_id", None),
            getattr(s, f"payment_gateway_{provider}_key_secret", None))


def sync_razorpay_invoice(invoice):
    """Asks Razorpay if this invoice's payment link is paid; if so marks it paid."""
    import requests

    if invoice.status == "PAID" or invoice.payment_gateway != "razorpay" or not invoice.gateway_reference:
        return False
    try:
        key_id, key_secret = _provider_keys("razorpay")
        r = requests.get(
            f"https://api.razorpay.com/v1/payment_links/{invoice.gateway_reference}",
            auth=(key_id, key_secret),
            timeout=15,
        )
        if not r.ok:
            return False
        data = r.json()
        if data.get("status") == "paid":
            mark_invoice_paid(
                invoice,
                gateway="razorpay",
                gateway_reference=invoice.gateway_reference,
                raw_response=str(data)[:2000],
            )
            return True
    except Exception:
        logger.exception("sync_razorpay_invoice failed for %s", invoice.invoice_number)
    return False


def sync_stripe_invoice(invoice):
    """Asks Stripe if this invoice's Checkout Session is paid; if so marks it paid."""
    if invoice.status == "PAID" or invoice.payment_gateway != "stripe" or not invoice.gateway_reference:
        return False
    try:
        import stripe

        _key_id, key_secret = _provider_keys("stripe")
        stripe.api_key = key_secret
        sess = stripe.checkout.Session.retrieve(invoice.gateway_reference)
        if sess.payment_status == "paid":
            mark_invoice_paid(
                invoice,
                gateway="stripe",
                gateway_reference=sess.payment_intent or invoice.gateway_reference,
                raw_response=str(sess)[:2000],
            )
            return True
    except Exception:
        logger.exception("sync_stripe_invoice failed for %s", invoice.invoice_number)
    return False


def sync_pending_invoice(invoice):
    return (
        sync_cashfree_invoice(invoice)
        or sync_razorpay_invoice(invoice)
        or sync_stripe_invoice(invoice)
    )
