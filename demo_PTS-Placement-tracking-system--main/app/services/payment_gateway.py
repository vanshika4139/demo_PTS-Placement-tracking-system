"""
Payment gateway integration - SRS FR-09.

This module is intentionally a thin, provider-agnostic shell. It cannot be
fully wired up without a real Razorpay/Cashfree/Stripe account and API keys
(entered on the Integrations page) - there is nothing to test end-to-end
without those.

What IS real here: the Invoice bookkeeping. `mark_invoice_paid` is what a
real webhook handler (or a manual "Mark as Paid" button) should call - it's
the one place that updates both the Invoice and the Organization consistently.

Razorpay and Cashfree are fully wired (create_payment_link + webhook route
in app/routes/frontend.py). Stripe is not - see the module docstring on
that branch below for what's needed to finish it.
"""

import logging

from app.extensions import db
from app.models import Invoice
from app.utils.platform_settings import get_platform_settings

logger = logging.getLogger(__name__)


def get_payment_gateway_config():
    """Returns (provider, key_id, key_secret, webhook_secret). All may be
    None/blank if the super admin hasn't configured a gateway yet - callers
    must check before attempting to create a payment link."""
    settings = get_platform_settings()
    return (
        settings.payment_gateway_provider,
        settings.payment_gateway_key_id,
        settings.payment_gateway_key_secret,
        settings.payment_gateway_webhook_secret,
    )


def is_gateway_configured():
    settings = get_platform_settings()
    return bool(
        settings.payment_gateway_enabled
        and settings.payment_gateway_provider
        and settings.payment_gateway_key_id
        and settings.payment_gateway_key_secret
    )


def create_payment_link(invoice: Invoice):
    """Returns a checkout URL the organization can be sent to pay this
    invoice. Raises RuntimeError if no gateway is configured, or
    NotImplementedError for a configured provider whose SDK call hasn't
    been filled in yet (see module docstring).

    Each branch below shows the shape (invoice.amount in the provider's
    expected unit, a reference id to correlate the webhook back to this
    Invoice, etc.) so wiring in the real SDK is a small, obvious diff
    rather than a redesign.
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
        customer_phone = (invoice.organization.mobile or "").strip() or "9999999999"

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
            api_response = cashfree_instance.PGCreateLink(
                create_link_request=create_link_request,
                x_api_version=x_api_version,
            )
            payment_link = api_response.data
        except Exception as exc:
            logger.exception("payment_gateway: Cashfree payment link creation failed for invoice %s", invoice.invoice_number)
            raise RuntimeError(f"Could not create Cashfree payment link: {exc}") from exc

        invoice.gateway_reference = payment_link.link_id
        invoice.payment_gateway = "cashfree"
        db.session.commit()
        return payment_link.link_url

    elif provider == "stripe":
        raise NotImplementedError(
            "Fill in with stripe.checkout.Session.create(...) using key_secret as the API key, "
            "invoice.amount * 100 (cents), and invoice.invoice_number in metadata."
        )
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
